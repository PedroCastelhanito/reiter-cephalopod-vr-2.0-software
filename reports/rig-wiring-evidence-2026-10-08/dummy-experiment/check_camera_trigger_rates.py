"""Check existing 30/60 Hz firmware diagnostic counts without flashing or capture."""
import asyncio
import dataclasses
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    result = {"controller_generation": endpoint.controller_generation, "tests": []}
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                async def execute(kind, signal=0):
                    outcome = await client.execute("ExecuteMicrocontrollerCommand", rpc.MicrocontrollerCommandRequest(
                        command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision,
                        kind=kind, signal=signal))
                    assert outcome.succeeded, outcome.failure
                    return dataclasses.asdict(outcome)
                result["connect"] = await execute(rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT)
                for name, signal in (("behavioral", 3), ("tracking", 4)):
                    row = {"name": name, "start": await execute(rpc.MICROCONTROLLER_COMMAND_KIND_START, signal)}
                    try:
                        await asyncio.sleep(2.2)
                        row["status"] = await execute(rpc.MICROCONTROLLER_COMMAND_KIND_STATUS)
                        row["view"] = MessageToDict((await client.get_snapshot()).microcontroller, preserving_proto_field_name=True)
                    finally:
                        if client.snapshot.microcontroller.diagnostic.active:
                            row["stop"] = await execute(rpc.MICROCONTROLLER_COMMAND_KIND_STOP)
                        else:
                            row["stop"] = "firmware already completed the bounded diagnostic"
                        result["tests"].append(row)
                result["configuration_unchanged"] = True
    finally:
        store.remove_client(principal)
        (OUT / "camera-trigger-rate-diagnostics.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))

asyncio.run(main())
