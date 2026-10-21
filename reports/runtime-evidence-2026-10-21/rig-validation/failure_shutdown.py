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
            client = HeadlessClient(channel, principal)
            snapshot = await client.get_snapshot()
            from cephvr.control.v1 import types_pb2 as pb
            assert snapshot.controller_generation == "479b4165-98b5-4a92-a72f-a13a61239197"
            async with client.control(takeover=True):
                result = await client.execute("ShutdownApplication", wait=False)
                print("Graceful ShutdownApplication admitted", result)
            return
            data = MessageToDict(snapshot, preserving_proto_field_name=True)
            assert snapshot.controller_generation == endpoint.controller_generation
            (Path(__file__).parent / "initial-snapshot.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(json.dumps({k:v for k,v in data.items() if k != "configuration_values"}, indent=2))
    finally:
        store.remove_client(principal)

asyncio.run(main())
