"""Owner-authorized Abort of the observed stuck test, with exact generation/session guards."""
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

async def main():
    out=Path(__file__).parent / "twenty-minute"
    original=json.loads((out/"setup.json").read_text())
    endpoint=_existing_endpoint(default_runtime_root())
    assert endpoint.controller_generation==original["controller_generation"]
    store=CredentialStore(default_runtime_root(),endpoint.controller_generation)
    principal=store.provision_client("cli")
    try:
        async with loopback_channel(50051,67_108_864) as channel:
            client=HeadlessClient(channel,principal)
            async with client.control(takeover=True):
                snap=client.snapshot
                assert snap.session.context.session_id==original["session"]["context"]["session_id"]
                (out/"before-abort.json").write_text(json.dumps(MessageToDict(snap,preserving_proto_field_name=True),indent=2))
                result=await asyncio.wait_for(client.cancel_current_work(),90)
                print(json.dumps(asdict(result)),flush=True)
                await asyncio.wait_for(client._wait(lambda s:s.session.phase==pb.SESSION_PHASE_CONFIGURATION and s.session.cleanup_confirmed),90)
                (out/"after-abort.json").write_text(json.dumps(MessageToDict(client.snapshot,preserving_proto_field_name=True),indent=2))
                print("Configuration; cleanup confirmed",flush=True)
    finally:
        store.remove_client(principal)
asyncio.run(main())
