"""Observe terminal state through WatchState without acquiring control."""
import asyncio
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def main():
    root = default_runtime_root()
    store = CredentialStore(root, _existing_endpoint(root).controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.observe():
                await asyncio.wait_for(client._wait(
                    lambda s: s.session.phase == pb.SESSION_PHASE_ENDED
                ), 180)
                data = MessageToDict(client.snapshot, preserving_proto_field_name=True)
                (Path(__file__).parent / "10-terminal.json").write_text(json.dumps(data, indent=2))
                print(json.dumps(data.get("session")), flush=True)
    finally:
        store.remove_client(principal)


asyncio.run(main())
