"""Recover only this test's unfinished reservation using its exact retained prompt."""
import asyncio
import argparse
import dataclasses
import json
from pathlib import Path
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

out = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--folder", default="DUMMY-125808")
parser.add_argument("--label", default="unpaired-run-1-recovery")
args = parser.parse_args()

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                state = await client.get_snapshot()
                prompt = next(p for p in state.prompts if args.folder in p.explanation)
                result = await client.execute("RespondToPrompt", rpc.PromptResponse(
                    command=client.operator_command(), prompt_id=prompt.prompt_id,
                    setup=prompt.setup, setup_operation=prompt.operation, choice="continue"))
                (out / f"{args.label}.json").write_text(
                    json.dumps(dataclasses.asdict(result), indent=2), encoding="utf-8")
                print(result)
    finally:
        store.remove_client(principal)

asyncio.run(main())
