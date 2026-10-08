"""Bounded real-board diagnostics and supervised firmware acceptance; no session."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.microcontroller.firmware_source import read_firmware
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
ROOT = OUT.parents[1]
results = {"controller_generation": sys.argv[1], "checks": {}}


def record(name, value):
    results["checks"][name] = value
    (OUT / "managed-mcu.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)


async def run():
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    original = None
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                original = pb.ExperimentConfiguration()
                original.CopyFrom(client.snapshot.configuration_values.current)

                async def config(name, proposed):
                    request = rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=client.snapshot.configuration.revision, proposed=proposed)
                    outcome = await asyncio.wait_for(client.execute("UpdateConfiguration", request), 20)
                    record(name, asdict(outcome))
                    if not outcome.succeeded:
                        raise RuntimeError(outcome.failure)

                async def execute(name, kind, signal=0, path=None):
                    request = rpc.MicrocontrollerCommandRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, kind=kind, signal=signal)
                    if path:
                        selected = read_firmware(str(path.resolve()))
                        request.firmware_path = str(path.resolve())
                        request.firmware_sha256 = selected.digest
                        record(name + "_source", {"path": str(path.resolve()), "digest": selected.digest})
                    outcome = await asyncio.wait_for(client.execute("ExecuteMicrocontrollerCommand", request), 120)
                    record(name, asdict(outcome))
                    if outcome.succeeded is not True:
                        raise RuntimeError(outcome.failure)

                async def observation(name):
                    state = await client.get_snapshot()
                    record(name, MessageToDict(state.microcontroller, preserving_proto_field_name=True))

                disabled = pb.ExperimentConfiguration()
                disabled.CopyFrom(original)
                next(b for b in disabled.backends if b.backend_name == "acquisition").enabled = False
                try:
                    await config("disable_acquisition", disabled)
                    await execute("connect_without_acquisition", rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT)
                    await observation("connected")
                    for name, signal in (("trial", 1), ("behavioral", 3), ("tracking", 4)):
                        await execute(name + "_start", rpc.MICROCONTROLLER_COMMAND_KIND_START, signal)
                        try:
                            await asyncio.sleep(0.35)
                            await execute(name + "_status", rpc.MICROCONTROLLER_COMMAND_KIND_STATUS)
                            await observation(name + "_active")
                        finally:
                            await execute(name + "_stop", rpc.MICROCONTROLLER_COMMAND_KIND_STOP)
                            await observation(name + "_stopped")
                    await execute("trial_timeout_start", rpc.MICROCONTROLLER_COMMAND_KIND_START, 1)
                    await asyncio.sleep(2.1)
                    await execute("trial_timeout_status", rpc.MICROCONTROLLER_COMMAND_KIND_STATUS)
                    await observation("trial_timeout_stopped")
                    await execute("upload_hex", rpc.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE, path=ROOT / "reports/rig-wiring-evidence-2026-10-07/mcu-counted-firmware/cephvr2_mcu.ino.hex")
                    await observation("after_hex_upload")
                    await execute("compile_upload_ino", rpc.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE, path=ROOT / "firmware/uno/cephvr2_mcu/cephvr2_mcu.ino")
                    await observation("after_ino_upload")
                finally:
                    await config("restore_configuration", original)
            record("control_release_failure", client.release_failure)
    except Exception as exc:
        record("error", f"{type(exc).__name__}: {exc}")
        raise
    finally:
        store.remove_client(principal)


asyncio.run(run())
