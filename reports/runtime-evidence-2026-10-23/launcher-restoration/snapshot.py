"""Read-only native verification; no control claim or device commands."""

import asyncio
import json
import sys
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.platform.windows.events import AutoResetEvent, event_name
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from uuid import UUID


async def main():
    root = default_runtime_root()
    endpoint = _existing_endpoint(root)
    allocation = UUID(endpoint.gui_relaunch_event_id)
    with AutoResetEvent.open(event_name(allocation), allocation):
        pass
    store = CredentialStore(root, endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            snapshot = await HeadlessClient(channel, principal).get_snapshot()
            assert snapshot.controller_generation == endpoint.controller_generation
            full = MessageToDict(snapshot, preserving_proto_field_name=True)
            summary = {
                key: full.get(key)
                for key in (
                    "controller_generation", "captured_monotonic_ns", "state_revision",
                    "configuration", "session", "trial", "participants", "errors",
                    "warnings", "runtime_incidents",
                )
            }
            summary["launcher_event_opened"] = True
            path = Path(__file__).parent / sys.argv[1]
            path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps(summary, indent=2))
    finally:
        store.remove_client(principal)


asyncio.run(main())
