"""Explicit user stop: take control, abort active trial, preserve exact evidence."""

import asyncio
import dataclasses
import json
from pathlib import Path
import time

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint is not None
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    record = dict(reason="Explicit user request: stop the tests for now", observed_ns=time.perf_counter_ns())
    try:
        async with loopback_channel(50051, 16777216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                record["initial"] = MessageToDict(client.snapshot, preserving_proto_field_name=True)
                (OUT / "user-stop-initial.pb").write_bytes(client.snapshot.SerializeToString())
                if client.snapshot.session.phase in {pb.SESSION_PHASE_RUNNING, pb.SESSION_PHASE_READY, pb.SESSION_PHASE_FINALIZING}:
                    result = await asyncio.wait_for(client.execute("AbortNow"), 90)
                    record["abort"] = dataclasses.asdict(result)
                record["final"] = MessageToDict(client.snapshot, preserving_proto_field_name=True)
                (OUT / "user-stop-final.pb").write_bytes(client.snapshot.SerializeToString())
                print(json.dumps(dict(initial_session=record["initial"]["session"], abort=record.get("abort"), final_session=record["final"]["session"])), flush=True)
    finally:
        (OUT / "user-stop.json").write_text(json.dumps(record, indent=2))
        store.remove_client(principal)


asyncio.run(main())
