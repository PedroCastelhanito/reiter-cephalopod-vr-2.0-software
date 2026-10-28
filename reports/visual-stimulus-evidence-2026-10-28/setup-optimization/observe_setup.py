"""Observe the operator's existing Setup without taking control or sending commands."""
import asyncio
import json
import time
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    out = Path(__file__).parent
    previous = None
    try:
        async with loopback_channel(50051,67_108_864) as channel:
            client = HeadlessClient(channel, principal)
            end = time.perf_counter() + 200
            while time.perf_counter() < end:
                snap = await asyncio.wait_for(client.get_snapshot(), 15)
                summary = dict(phase=pb.SessionPhase.Name(snap.session.phase),cleanup=snap.session.cleanup_confirmed,
                    operations=[dict(command=o.command,complete=o.complete,succeeded=o.succeeded,progress=o.progress,failure=o.failure.message) for o in snap.operations])
                if summary != previous:
                    print(json.dumps(summary), flush=True)
                    with (out/"observed-events.jsonl").open("a") as stream:
                        stream.write(json.dumps(dict(host_ns=time.perf_counter_ns(),**summary))+"\n")
                    previous = summary
                if snap.session.phase != pb.SESSION_PHASE_SETTING_UP:
                    (out/"observed-terminal.json").write_text(json.dumps(MessageToDict(snap,preserving_proto_field_name=True),indent=2))
                    return
                await asyncio.sleep(2)
            raise TimeoutError("observation limit; no commands issued")
    finally:
        store.remove_client(principal)
asyncio.run(main())
