"""Read-only bounded current managed-generation observation."""

import asyncio
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    print(f"endpoint={endpoint}", flush=True)
    if endpoint is None:
        return
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            snapshot = await asyncio.wait_for(
                HeadlessClient(channel, principal).get_snapshot(), 5
            )
        output = Path(__file__).parent
        (output / "initial-snapshot.pb").write_bytes(snapshot.SerializeToString())
        (output / "initial-snapshot.json").write_text(
            json.dumps(MessageToDict(snapshot, preserving_proto_field_name=True), indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(snapshot.session, flush=True)
        print(snapshot.participants, flush=True)
    finally:
        store.remove_client(principal)


asyncio.run(main())
