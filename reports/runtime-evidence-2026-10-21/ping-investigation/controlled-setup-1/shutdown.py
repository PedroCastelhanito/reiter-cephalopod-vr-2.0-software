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
            assert snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION and snapshot.session.cleanup_confirmed
            prior = json.loads((Path(__file__).parent / "pre-snapshot.json").read_text())
            assert snapshot.controller_generation == prior["controller_generation"]
            from google.protobuf.json_format import Parse
            expected = pb.Snapshot()
            Parse(json.dumps(prior), expected)
            assert snapshot.configuration_values.current == expected.configuration_values.current
            for role in ("behavioral", "tracking", "eye_tracking"):
                camera = getattr(snapshot.acquisition_devices, role)
                assert not camera.device_open and not camera.preview_running and not camera.cleanup_pending
            (Path(__file__).parent / "immediate-pre-shutdown.json").write_text(json.dumps(MessageToDict(snapshot, preserving_proto_field_name=True), indent=2))
            async with client.control(takeover=True):
                result = await client.execute("ShutdownApplication", wait=False)
                print("Graceful ShutdownApplication admitted", result)
            return
    finally:
        store.remove_client(principal)

asyncio.run(main())
