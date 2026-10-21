"""Read-only live runtime inventory; no control claim or device commands."""
import asyncio
import json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

async def main():
    root = default_runtime_root()
    endpoint = _existing_endpoint(root)
    store = CredentialStore(root, endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            snapshot = await HeadlessClient(channel, principal).get_snapshot()
            data = MessageToDict(snapshot, preserving_proto_field_name=True)
            assert snapshot.controller_generation == endpoint.controller_generation
            (Path(__file__).parent / "final-read-only-snapshot.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(json.dumps({"controller": data["controller_generation"], "session": data["session"]}))
    finally:
        store.remove_client(principal)

asyncio.run(main())


