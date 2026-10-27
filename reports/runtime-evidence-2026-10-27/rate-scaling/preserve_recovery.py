"""Recover only the explicitly identified failed audit session; preserve its files."""

import asyncio
import dataclasses
import json
import sys
import tomllib
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def main():
    generation, failed_session, old_generation, label = sys.argv[1:]
    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint.controller_generation == generation
    root = Path(__file__).resolve().parents[3]
    out = Path(__file__).parent / (label + ".json")
    assert not out.exists()
    settings = tomllib.loads((root / "config/backends/experiment_config.toml").read_text(encoding="utf-8"))
    store = CredentialStore(default_runtime_root(), generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(settings["rpc"]["port"], settings["rpc"]["max_message_bytes"]) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                assert client.snapshot.controller_generation == generation
                prompts = list(client.snapshot.prompts)
                assert len(prompts) == 1
                prompt = prompts[0]
                assert prompt.setup.session_id == failed_session
                assert prompt.setup.controller_generation == old_generation
                assert "recover" in prompt.permitted_choices
                before = MessageToDict(client.snapshot, preserving_proto_field_name=True)
                result = await asyncio.wait_for(client.execute("RespondToPrompt", rpc.PromptResponse(
                    command=client.operator_command(), prompt_id=prompt.prompt_id,
                    setup=prompt.setup, setup_operation=prompt.operation, choice="recover",
                )), 90)
                out.write_text(json.dumps({"before": before, "result": dataclasses.asdict(result),
                    "after": MessageToDict(client.snapshot, preserving_proto_field_name=True)}, indent=2), encoding="utf-8")
                assert result.succeeded and not result.needs_input
                assert not client.snapshot.prompts
                print("Preserving recovery confirmed; files retained")
    finally:
        store.remove_client(principal)


asyncio.run(main())
