"""Normal authenticated shutdown of the exclusively owned idle application."""
import asyncio
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
            async with client.control(takeover=True):
                result = await client.execute("ShutdownApplication", wait=False)
                print("Graceful ShutdownApplication admitted", result)
    finally:
        store.remove_client(principal)

asyncio.run(main())
