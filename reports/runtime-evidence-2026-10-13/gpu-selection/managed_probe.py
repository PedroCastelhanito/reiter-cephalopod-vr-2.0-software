"""Bounded authorized managed checks, excluding Eye and remote mutations."""

import argparse
import asyncio
import dataclasses
import json
import hashlib
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=["snapshot", "devices", "shutdown", "setup", "calibration", "mcu"])
args = parser.parse_args()
record = {"scope": args.mode, "eye": "excluded", "checks": {}}
if args.mode == "snapshot":
    from time import time_ns

    args.mode = f"snapshot-{time_ns()}"

def keep(name, value):
    record["checks"][name] = value
    (OUT / f"managed-{args.mode}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    if endpoint is None:
        raise RuntimeError("No managed application endpoint")
    record["controller_generation"] = endpoint.controller_generation
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            state = await client.get_snapshot()
            (OUT / f"{args.mode}-original.pb").write_bytes(state.SerializeToString())
            for field in ("session", "visual_stimulus_display", "acquisition_devices", "configuration", "warnings", "errors"):
                value = getattr(state, field)
                keep(field, [MessageToDict(v, preserving_proto_field_name=True) for v in value] if field in ("warnings", "errors") else MessageToDict(value, preserving_proto_field_name=True))
            if args.mode.startswith("snapshot"):
                return
            async with client.control(takeover=True):
                state = await client.get_snapshot()
                if args.mode == "shutdown":
                    try:
                        keep("shutdown", dataclasses.asdict(await client.execute("ShutdownApplication")))
                    except Exception as exc:
                        keep("shutdown_watch", str(exc))
                    return
                if state.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                    raise RuntimeError("Configuration required")
                original = pb.ExperimentConfiguration.FromString(state.configuration_values.current.SerializeToString())
                if args.mode == "mcu":
                    for name, kind in (("connect", rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT), ("status", rpc.MICROCONTROLLER_COMMAND_KIND_STATUS)):
                        keep(name, await dispatch_device_action(client, "mcu", {"kind": kind}, principal))
                        current = await client.get_snapshot()
                        keep(name + "_evidence", MessageToDict(current.acquisition_devices, preserving_proto_field_name=True))
                        (OUT / f"mcu-{name}.pb").write_bytes(current.SerializeToString())
                    return
                if args.mode == "calibration":
                    from cephvr.gui.managed_display_operations import (
                        capture_display_calibration_intent,
                        close_display_calibration_request,
                        open_display_calibration_request,
                        update_display_calibration_request,
                    )
                    from cephvr.visual_stimulus.v1.messages_pb2 import DisplayCalibrationAdjustment

                    arena = Path(original.asset_root) / "calibration/rig_geometry_grid.glb"
                    # Retain the historical asset; use a distinct probe profile with
                    # the owner's accepted all-output pacing and identical geometry.
                    root = Path(original.asset_root)
                    source = root / "calibration/diagnostic_display_profile.json"
                    profile = json.loads(source.read_text())
                    profile["presentation_mode"] = "all_outputs_vsync"
                    profile["pacing_output_id"] = None
                    profile["calibration_view"] = "frame_grid"
                    probe = root / "calibration/rig_check_20261013_all_vsync.json"
                    raw = json.dumps(profile, indent=2).encode()
                    if probe.exists() and probe.read_bytes() != raw:
                        raise RuntimeError("Probe profile path already contains different content")
                    probe.write_bytes(raw)
                    (OUT / "calibration-probe-profile.json").write_bytes(raw)
                    request = rpc.OpenDisplayCalibrationRequest(
                        command=client.operator_command(),
                        expected_configuration_revision=state.configuration.revision,
                        diagnostic_id=__import__("uuid").uuid4().__str__(),
                        profile_asset_reference=probe.relative_to(root).as_posix(),
                        arena_asset_reference=arena.relative_to(root).as_posix(),
                        expected_profile_sha256=hashlib.sha256(raw).hexdigest(),
                        expected_arena_sha256=hashlib.sha256(arena.read_bytes()).hexdigest(),
                    )
                    try:
                        opened = await asyncio.wait_for(client.execute("OpenDisplayCalibration", request), 90)
                        keep("open", dataclasses.asdict(opened))
                        if not opened.succeeded:
                            return
                        state = await client.get_snapshot()
                        keep("active", MessageToDict(state.visual_stimulus_display, preserving_proto_field_name=True))
                        for sequence, coords in ((1, [0.05, 0.05, 0.95, 0.05, 0.05, 0.95, 0.95, 0.95]), (2, [0, 0, 1, 0, 0, 1, 1, 1])):
                            adjustments = tuple(DisplayCalibrationAdjustment(mapping_id=m["mapping_id"], destination_xy=coords).SerializeToString() for m in profile["mappings"])
                            update = update_display_calibration_request(client, expected_revision=state.configuration.revision, diagnostic_id=request.diagnostic_id, adjustment_sequence=sequence, adjustments=adjustments)
                            keep(f"update_{sequence}", dataclasses.asdict(await asyncio.wait_for(client.execute("UpdateDisplayCalibration", update), 30)))
                            state = await client.get_snapshot()
                            keep(f"update_{sequence}_evidence", MessageToDict(state.visual_stimulus_display, preserving_proto_field_name=True))
                            await asyncio.sleep(3)
                    finally:
                        state = await client.get_snapshot()
                        if state.visual_stimulus_display.HasField("calibration") and state.visual_stimulus_display.calibration.diagnostic_id == request.diagnostic_id:
                            close = close_display_calibration_request(client, expected_revision=state.configuration.revision, diagnostic_id=request.diagnostic_id)
                            keep("close", dataclasses.asdict(await asyncio.wait_for(client.execute("CloseDisplayCalibration", close), 90)))
                            state = await client.get_snapshot()
                            keep("idle_after_close", MessageToDict(state.visual_stimulus_display, preserving_proto_field_name=True))
                    keep("configuration_unchanged", state.configuration_values.current == original)
                    return
                if args.mode == "setup":
                    keep("setup", dataclasses.asdict(await asyncio.wait_for(client.execute("Setup"), 90)))
                    return
                acquisition = next(b.acquisition for b in original.backends if b.backend_name == "acquisition")
                cameras = [(role, getattr(acquisition, field).device.device_id) for role, field in ((1, "behavioral"), (2, "tracking")) if getattr(acquisition, field).enabled]
                for name, action, options in (
                    ("mcu_connect", "mcu", {"kind": rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT}),
                    ("mcu_status", "mcu", {"kind": rpc.MICROCONTROLLER_COMMAND_KIND_STATUS}),
                    ("spikeglx_readonly", "spikeglx_connection", {}),
                    ("camera_identity", "test_cameras", {"cameras": cameras}),
                ):
                    try:
                        keep(name, await dispatch_device_action(client, action, options, principal))
                    except Exception as exc:
                        keep(name, {"error": f"{type(exc).__name__}: {exc}"})
                for role, serial in cameras:
                    for cycle in (1, 2):
                        name = f"camera_{serial}_cycle_{cycle}"
                        try:
                            keep(name + "_start", await dispatch_device_action(client, "camera", {"role": role, "kind": rpc.CAMERA_COMMAND_KIND_START_PREVIEW}, principal))
                            await asyncio.sleep(3)
                            current = await client.get_snapshot()
                            view = current.acquisition_devices.behavioral if role == 1 else current.acquisition_devices.tracking
                            keep(name + "_state", MessageToDict(view, preserving_proto_field_name=True))
                        except Exception as exc:
                            keep(name + "_error", {"error": f"{type(exc).__name__}: {exc}"})
                        finally:
                            try:
                                keep(name + "_stop", await dispatch_device_action(client, "camera", {"role": role, "kind": rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW}, principal))
                            except Exception as exc:
                                keep(name + "_cleanup_error", {"error": f"{type(exc).__name__}: {exc}"})
                                raise
                current = await client.get_snapshot()
                keep("configuration_unchanged", current.configuration_values.current == original)
                keep("final_devices", MessageToDict(current.acquisition_devices, preserving_proto_field_name=True))
                (OUT / "devices-final.pb").write_bytes(current.SerializeToString())
    finally:
        store.remove_client(principal)

asyncio.run(main())
