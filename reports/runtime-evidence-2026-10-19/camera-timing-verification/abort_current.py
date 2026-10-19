"""Owner-authorized Abort of the current dummy session; preserve its files."""

import asyncio
import json
from pathlib import Path

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

from native_check import command, save


async def main():
    root = default_runtime_root()
    store = CredentialStore(root, _existing_endpoint(root).controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                assert client.snapshot.session.phase == pb.SESSION_PHASE_RUNNING
                assert client.snapshot.configuration_values.current.subject == "DUMMY_2"
                save("owner-dummy-before-abort.json", client.snapshot)
                await command(client, "AbortNow")
                save("owner-dummy-after-abort.json", client.snapshot)
                await command(client, "NewSession")
                await command(client, "ShutdownApplication")
    finally:
        store.remove_client(principal)


asyncio.run(main())
