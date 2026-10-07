"""Bounded real-controller connection and configured Behavior preview checks."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
RESULT = {"controller_generation": sys.argv[1], "checks": {}}
NAME = sys.argv[2] if len(sys.argv) > 2 else "managed-check"


def record(name, value):
    RESULT["checks"][name] = value
    (OUT / f"{NAME}.json").write_text(json.dumps(RESULT, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)


def view(state):
    raw = MessageToDict(state, preserving_proto_field_name=True)
    raw.pop("configuration_values", None)
    return raw


async def run():
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            record("initial_snapshot", view(await client.get_snapshot()))
            if NAME == "managed-check":
                remote = await client.stub.CheckSpikeGLXConnection(
                    rpc.SpikeGLXConnectionQuery(client_id=principal.generation),
                    metadata=principal.metadata(), timeout=8,
                )
                record("spikeglx_connection", MessageToDict(remote, preserving_proto_field_name=True))
            async with client.control(takeover=NAME != "managed-check"):
                inventory = await client.stub.GetSpikeGLXInventory(
                    rpc.SpikeGLXInventoryRequest(
                        command=client.operator_command(),
                        expected_configuration_revision=client.snapshot.configuration.revision,
                    ), metadata=principal.metadata(), timeout=5,
                )
                record("spikeglx_inventory", MessageToDict(inventory, preserving_proto_field_name=True))

                async def execute(name, method, request):
                    try:
                        result = await asyncio.wait_for(client.execute(method, request), 40)
                        record(name, asdict(result))
                        return result.succeeded is True
                    except Exception as exc:
                        record(name, {"error": f"{type(exc).__name__}: {exc}",
                                      "command_id": getattr(exc, "command_id", "")})
                        return False

                async def mcu(name, kind):
                    return await execute(name, "ExecuteMicrocontrollerCommand", rpc.MicrocontrollerCommandRequest(
                        command=client.operator_command(),
                        expected_configuration_revision=client.snapshot.configuration.revision,
                        kind=kind,
                    ))

                async def camera(name, role, kind, run_id=None, path=None):
                    request = rpc.CameraCommandRequest(
                        command=client.operator_command(),
                        expected_configuration_revision=client.snapshot.configuration.revision,
                        camera=role, kind=kind,
                    )
                    if run_id is not None:
                        request.preview_run_id = run_id
                    if path is not None:
                        request.path = path
                    return await execute(name, "ExecuteCameraCommand", request)

                if await mcu("mcu_connect", rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT):
                    await mcu("mcu_status", rpc.MICROCONTROLLER_COMMAND_KIND_STATUS)
                    record("mcu_readback", view(await client.get_snapshot()))
                    await mcu("mcu_stop", rpc.MICROCONTROLLER_COMMAND_KIND_STOP)
                for role in (1, 2):
                    await camera(f"camera_{role}_connection", role, rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION)
                for cycle in range(2):
                    started = await camera(f"behavior_start_{cycle}", 1, rpc.CAMERA_COMMAND_KIND_START_PREVIEW)
                    state = await client.get_snapshot()
                    record(f"behavior_after_start_{cycle}", view(state))
                    if started:
                        await asyncio.sleep(2)
                        record(f"behavior_running_{cycle}", view(await client.get_snapshot()))
                    state = await client.get_snapshot()
                    device = state.acquisition_devices.behavioral
                    if device.preview_running and device.preview_run_id:
                        await camera(f"behavior_stop_{cycle}", 1, rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW, device.preview_run_id)
                    record(f"behavior_final_{cycle}", view(await client.get_snapshot()))
                    if not started or client.snapshot.acquisition_devices.behavioral.cleanup_pending:
                        break
                if NAME != "managed-check":
                    original = pb.ExperimentConfiguration()
                    original.CopyFrom(client.snapshot.configuration_values.current)
                    proposed = pb.ExperimentConfiguration()
                    proposed.CopyFrom(original)
                    settings = next(b.acquisition for b in proposed.backends if b.backend_name == "acquisition")
                    settings.tracking.enabled = True
                    enabled = await execute("tracking_enable", "UpdateConfiguration", rpc.UpdateConfigurationRequest(
                        command=client.operator_command(), expected_revision=client.snapshot.configuration.revision,
                        proposed=proposed,
                    ))
                    if enabled:
                        imported = await camera("tracking_import_pfs", 2, rpc.CAMERA_COMMAND_KIND_IMPORT_PFS,
                            path="C:/Data/projects/reiter-cephalopod-vr/cephvr-assets/camera-configs/a2A2464-77umPRO_40747103_BehaviorSquid.pfs")
                        record("tracking_pfs_readback", view(await client.get_snapshot()))
                        await camera("tracking_finish_editing", 2, rpc.CAMERA_COMMAND_KIND_FINISH_EDITING)
                        if imported:
                            started = await camera("tracking_start", 2, rpc.CAMERA_COMMAND_KIND_START_PREVIEW)
                            record("tracking_after_start", view(await client.get_snapshot()))
                            if started:
                                await asyncio.sleep(2)
                                record("tracking_running", view(await client.get_snapshot()))
                            state = await client.get_snapshot()
                            device = state.acquisition_devices.tracking
                            if device.preview_running and device.preview_run_id:
                                await camera("tracking_stop", 2, rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW, device.preview_run_id)
                            record("tracking_final", view(await client.get_snapshot()))
                        await execute("restore_original_configuration", "UpdateConfiguration", rpc.UpdateConfigurationRequest(
                            command=client.operator_command(), expected_revision=client.snapshot.configuration.revision,
                            proposed=original,
                        ))
            record("control_released", client.release_failure)
            record("final_snapshot", view(await client.get_snapshot()))
    except Exception as exc:
        record("probe_error", {"error": f"{type(exc).__name__}: {exc}"})
    finally:
        store.remove_client(principal)


asyncio.run(run())
