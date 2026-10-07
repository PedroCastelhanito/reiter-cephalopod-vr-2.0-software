"""Authenticated read-only state before any owner-authorized root migration."""

import asyncio
import json
import sys
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def run():
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            state = await client.get_snapshot()
            raw = MessageToDict(state, preserving_proto_field_name=True)
            raw.pop("configuration_values", None)
            output = Path(__file__).parent / "replacement-msix-before-state.json"
            output.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            print(json.dumps(raw, indent=2))
    finally:
        store.remove_client(principal)


asyncio.run(run())
