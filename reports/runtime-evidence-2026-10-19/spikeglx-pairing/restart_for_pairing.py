"""Confirm both applications idle before reloading CephVR's naming change."""

import asyncio
import dataclasses
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def main():
    root = default_runtime_root()
    store = CredentialStore(root, _existing_endpoint(root).controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                print(MessageToDict(client.snapshot.session, preserving_proto_field_name=True), flush=True)
                if client.snapshot.session.phase == pb.SESSION_PHASE_RUNNING:
                    assert client.snapshot.session.directory.endswith("DUMMY_2-165417")
                    outcome = await asyncio.wait_for(client.execute("AbortNow"), 90)
                    assert outcome.succeeded
                if client.snapshot.session.phase == pb.SESSION_PHASE_ENDED and client.snapshot.session.cleanup_confirmed:
                    outcome = await asyncio.wait_for(client.execute("NewSession"), 20)
                    assert outcome.succeeded
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                result = await client.stub.CheckSpikeGLXConnection(
                    rpc.SpikeGLXConnectionQuery(client_id=principal.generation),
                    metadata=principal.metadata(), timeout=8,
                )
                data = MessageToDict(result, preserving_proto_field_name=True)
                (Path(__file__).parent / "idle-connection.json").write_text(json.dumps(data, indent=2)+"\n")
                print(json.dumps(data), flush=True)
                assert result.connected and not result.running and not result.error
                outcome = await asyncio.wait_for(client.execute("ShutdownApplication"), 40)
                print(dataclasses.asdict(outcome), flush=True)
                assert outcome.succeeded
    finally:
        store.remove_client(principal)


asyncio.run(main())
