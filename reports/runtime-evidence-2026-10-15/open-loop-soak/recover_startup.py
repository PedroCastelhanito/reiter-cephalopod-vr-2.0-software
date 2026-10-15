"""Use normal evidence-preserving startup recovery after exact managed exit."""

import asyncio
import dataclasses
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint is not None
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16777216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                record = dict(initial=MessageToDict(client.snapshot, preserving_proto_field_name=True))
                prompts = list(client.snapshot.prompts)
                if prompts:
                    assert len(prompts) == 1
                    prompt = prompts[0]
                    assert set(prompt.permitted_choices) == {"continue", "cancel"}
                    assert not prompt.HasField("runtime_incident")
                    response = rpc.PromptResponse(command=client.operator_command(), prompt_id=prompt.prompt_id,
                                                  setup=prompt.setup, setup_operation=prompt.operation, choice="continue")
                    result = await client.execute("RespondToPrompt", response)
                    record["outcome"] = dataclasses.asdict(result)
                    assert result.succeeded
                record["final"] = MessageToDict(client.snapshot, preserving_proto_field_name=True)
                path = OUT / f"startup-recovery-{endpoint.controller_generation}.json"
                path.write_text(json.dumps(record, indent=2))
                print(path)
    finally:
        store.remove_client(principal)


asyncio.run(main())
