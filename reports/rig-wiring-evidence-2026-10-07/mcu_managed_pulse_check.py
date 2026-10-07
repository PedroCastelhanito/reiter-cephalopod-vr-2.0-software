"""Bounded protocol-3 camera pin checks through the normal controller owner."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
result = {"controller_generation": sys.argv[1], "checks": {}}


def record(name, value):
    result["checks"][name] = value
    (OUT / "mcu-handoff-diagnostics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)


async def run():
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                async def execute(name, kind, signal=0):
                    request = rpc.MicrocontrollerCommandRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, kind=kind, signal=signal)
                    outcome = await asyncio.wait_for(client.execute("ExecuteMicrocontrollerCommand", request), 15)
                    record(name, asdict(outcome))
                    if outcome.succeeded is not True:
                        raise RuntimeError(outcome.failure)

                async def observation(name):
                    state = await client.get_snapshot()
                    record(name, MessageToDict(state.acquisition_devices, preserving_proto_field_name=True))

                await execute("connect", rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT)
                for name, signal in (("behavioral", 3), ("tracking", 4)):
                    await execute(f"{name}_start", rpc.MICROCONTROLLER_COMMAND_KIND_START, signal)
                    try:
                        await asyncio.sleep(0.3)
                        await execute(f"{name}_status", rpc.MICROCONTROLLER_COMMAND_KIND_STATUS)
                        await observation(f"{name}_active")
                    finally:
                        await execute(f"{name}_stop", rpc.MICROCONTROLLER_COMMAND_KIND_STOP)
                        await observation(f"{name}_stopped")
                await execute("trial_timeout_start", rpc.MICROCONTROLLER_COMMAND_KIND_START, 1)
                await asyncio.sleep(2.1)
                await execute("trial_timeout_status", rpc.MICROCONTROLLER_COMMAND_KIND_STATUS)
                await observation("trial_timeout_readback")
            record("control_release_failure", client.release_failure)
    except Exception as exc:
        record("error", f"{type(exc).__name__}: {exc}")
    finally:
        store.remove_client(principal)


asyncio.run(run())
