"""Normal authenticated shutdown of the exclusively owned idle application."""
import asyncio
import json
from pathlib import Path
from google.protobuf.json_format import ParseDict
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
            baseline=Path(__file__).parent/"census-changing"
            expected=json.loads((baseline/"latest-baseline-snapshot.json").read_text(encoding="utf-8"))
            assert snapshot.controller_generation==expected["controller_generation"]
            assert not snapshot.session.HasField("context") and not snapshot.acquisition_devices.source.backend_generation
            assert snapshot.configuration_values.current==ParseDict(expected["configuration_values"]["current"],pb.ExperimentConfiguration())
            assert Path("config/last_configuration.json").read_bytes()==(baseline/"latest-baseline-history.json").read_bytes()
            async with client.control(takeover=True):
                assert client.snapshot.configuration_values.current==snapshot.configuration_values.current
                assert not client.snapshot.session.HasField("context") and not client.snapshot.acquisition_devices.source.backend_generation
                result = await client.execute("ShutdownApplication", wait=False)
                print("Graceful ShutdownApplication admitted", result)
    finally:
        store.remove_client(principal)

asyncio.run(main())
