"""Read-only authenticated runtime state; no control acquisition or commands."""
import asyncio
import json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(),endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051,67_108_864) as channel:
            snap = await asyncio.wait_for(HeadlessClient(channel,principal).get_snapshot(),15)
            (Path(__file__).parent / "pool-endurance" / "runtime-before.json").write_text(json.dumps(MessageToDict(snap,preserving_proto_field_name=True),indent=2))
            print(json.dumps(dict(generation=snap.controller_generation,phase=pb.SessionPhase.Name(snap.session.phase),cleanup=snap.session.cleanup_confirmed,has_session=snap.session.HasField("context"))),flush=True)
    finally:
        store.remove_client(principal)
asyncio.run(main())
