"""Apply normal recovery only to the exact failed audit session after absence proof."""

import asyncio
import argparse
import dataclasses
import json
from pathlib import Path

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

out = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument("--prior", default="saved-p4-baseline60-r1")
parser.add_argument("--receipt", default="failed-baseline-exit.json")
parser.add_argument("--label", default="owned-session-recovery")
options = parser.parse_args()
failed = json.loads((out/options.prior/"run.json").read_text())
final = next(e["value"] for e in reversed(failed["events"]) if e["name"] in {"final", "failure_snapshot"})
receipt = json.loads((out/options.receipt).read_text())
assert receipt["all_owned_processes_absent"] and receipt["controller_generation"] == failed["generation"]


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint is not None and endpoint.controller_generation != failed["generation"]
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                assert len(client.snapshot.prompts) == 1
                prompt = client.snapshot.prompts[0]
                assert prompt.setup.controller_generation == failed["generation"]
                assert prompt.setup.session_id == final["session"]["context"]["session_id"]
                assert final["session"]["directory"] in prompt.explanation
                response = rpc.PromptResponse(command=client.operator_command(), prompt_id=prompt.prompt_id, setup=prompt.setup, setup_operation=prompt.operation, choice="continue")
                result = await asyncio.wait_for(client.execute("RespondToPrompt", response), 30)
                destination = out/(options.label+".json")
                assert not destination.exists()
                destination.write_text(json.dumps({"generation": endpoint.controller_generation, "result": dataclasses.asdict(result), "prior_exit_receipt": receipt, "scope": "Normal recovery retains scientific outputs and unknown-output status; no pointer or scientific file edits by audit"}, indent=2)+"\n")
                assert result.succeeded and not client.snapshot.prompts
    finally:
        store.remove_client(principal)


asyncio.run(main())
