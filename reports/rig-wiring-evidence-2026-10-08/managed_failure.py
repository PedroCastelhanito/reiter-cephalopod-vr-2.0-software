"""Native compiler rejection and control-release safety without scientific recording."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.controller.microcontroller.firmware_source import read_firmware
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
result = {"controller_generation": sys.argv[1], "checks": {}}


def record(name, value):
    result["checks"][name] = value
    (OUT / "managed-failure.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)


async def run():
    directory = OUT / "rejected-sketch"
    directory.mkdir(exist_ok=True)
    path = directory / "rejected-sketch.ino"
    path.write_text('#error Deliberate_compile_rejection_for_rig_acceptance\nvoid setup() {}\nvoid loop() {}\n', encoding="utf-8")
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                async def execute(name, kind, signal=0, selected=None):
                    request = rpc.MicrocontrollerCommandRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, kind=kind, signal=signal)
                    if selected:
                        request.firmware_path = str(selected.path)
                        request.firmware_sha256 = selected.digest
                    outcome = await asyncio.wait_for(client.execute("ExecuteMicrocontrollerCommand", request), 90)
                    record(name, asdict(outcome))
                    return outcome

                await execute("connect", rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT)
                before = (await client.get_snapshot()).microcontroller
                record("before", MessageToDict(before, preserving_proto_field_name=True))
                selected = read_firmware(str(path.resolve()))
                failure = await execute("compile_rejection", rpc.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE, selected=selected)
                assert failure.complete and not failure.succeeded and "Deliberate_compile_rejection" in failure.failure
                after = (await client.get_snapshot()).microcontroller
                record("after", MessageToDict(after, preserving_proto_field_name=True))
                assert after.observation.connection_id == before.observation.connection_id
                assert not after.cleanup_pending
                await execute("trial_start_before_release", rpc.MICROCONTROLLER_COMMAND_KIND_START, 1)
            record("release_failure", client.release_failure)
            state = (await client.get_snapshot()).microcontroller
            record("released", MessageToDict(state, preserving_proto_field_name=True))
            assert not state.cleanup_pending and not state.HasField("observation")
    except Exception as exc:
        record("error", f"{type(exc).__name__}: {exc}")
        raise
    finally:
        store.remove_client(principal)


asyncio.run(run())
