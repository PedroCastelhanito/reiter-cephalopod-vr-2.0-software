"""Real camera Connect/Disconnect, native geometry and sustained idle preview checks."""

import asyncio
import ctypes
import json
import sys
from ctypes import wintypes
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QGuiApplication

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.device_requests import import_camera_preset
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.gui.preview_placement import square_preview_placement
from cephvr.platform.windows.window_coordinates import operator_window_geometry, physical_coordinates
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
result = {"controller_generation": sys.argv[1], "checks": {}}
api = ctypes.WinDLL("user32", use_last_error=True)
api.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
api.FindWindowW.restype = wintypes.HWND
api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
api.IsWindowVisible.argtypes = [wintypes.HWND]
api.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
qt_app = QGuiApplication([])


def record(name, value):
    result["checks"][name] = value
    (OUT / "managed-cameras.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)


def native(title):
    handle = api.FindWindowW(None, title)
    pid = wintypes.DWORD()
    if handle:
        api.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    visible = bool(handle and api.IsWindowVisible(handle))
    return {"handle": handle, "pid": pid.value, "visible": visible, "geometry": operator_window_geometry(handle)[0] if visible else None}


async def run():
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    gui = native("CephVR2.0 — Dashboard")
    original_bounds = wintypes.RECT()
    if gui["handle"]:
        with physical_coordinates():
            api.GetWindowRect(gui["handle"], ctypes.byref(original_bounds))
    record("gui", gui)
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                original = pb.ExperimentConfiguration()
                original.CopyFrom(client.snapshot.configuration_values.current)

                async def state(name):
                    s = await client.get_snapshot()
                    raw = MessageToDict(s, preserving_proto_field_name=True)
                    raw.pop("configuration_values", None)
                    record(name, raw)
                    return s

                async def configure(name, proposed):
                    outcome = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=client.snapshot.configuration.revision, proposed=proposed))
                    record(name, asdict(outcome))
                    if not outcome.succeeded:
                        raise RuntimeError(outcome.failure)

                async def camera(name, role, kind, **options):
                    try:
                        reply = await asyncio.wait_for(dispatch_device_action(client, "camera", {"role": role, "kind": kind, **options}, principal), 40)
                        record(name, reply)
                        return True
                    except Exception as exc:
                        record(name, {"error": f"{type(exc).__name__}: {exc}", "command_id": getattr(exc, "command_id", None)})
                        return False

                async def cycle(role, title, name, move=False):
                    if move and gui["handle"]:
                        with physical_coordinates():
                            if not api.SetWindowPos(gui["handle"], None, 24, 24, 0, 0, 0x15):
                                raise ctypes.WinError(ctypes.get_last_error())
                    if not gui["visible"]:
                        raise RuntimeError("Actual managed GUI missing; placement cannot be tested")
                    anchor, area, scale = operator_window_geometry(gui["handle"])
                    placement = square_preview_placement(QRect(*anchor), QRect(*area), scale)
                    record(name + "_placement", {"anchor": anchor, "area": area, "x": placement.x, "y": placement.y, "side": placement.side})
                    try:
                        started = await camera(name + "_connect", role, rpc.CAMERA_COMMAND_KIND_START_PREVIEW, show_preview=True, placement=placement.SerializeToString())
                        await state(name + "_after_connect")
                        window = native(title)
                        record(name + "_window", window)
                        if started:
                            assert window["visible"] and window["geometry"][:2] == (placement.x, placement.y)
                            await asyncio.sleep(0.5)
                            x, y, width, height = window["geometry"]
                            with physical_coordinates():
                                screen = qt_app.primaryScreen()
                                assert screen is not None
                                assert screen.grabWindow(0, x, y, width, height).save(str(OUT / (name + "-preview.png")))
                            await asyncio.sleep(5)
                            await state(name + "_sustained")
                    finally:
                        current = await client.get_snapshot()
                        device = current.acquisition_devices.behavioral if role == 1 else current.acquisition_devices.tracking
                        if device.preview_running and device.preview_run_id:
                            await camera(name + "_disconnect", role, rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW)
                        await state(name + "_after_disconnect")
                        record(name + "_window_after_disconnect", native(title))

                try:
                    for role in (1, 2):
                        await camera(f"camera_{role}_identity", role, rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION)
                    await cycle(1, "Behavior camera", "behavior")
                    await cycle(1, "Behavior camera", "behavior_moved", True)
                    proposed = pb.ExperimentConfiguration()
                    proposed.CopyFrom(client.snapshot.configuration_values.current)
                    next(b.acquisition for b in proposed.backends if b.backend_name == "acquisition").tracking.enabled = True
                    await configure("enable_tracking", proposed)
                    try:
                        await import_camera_preset(client, 2, "C:/Data/projects/reiter-cephalopod-vr/cephvr-assets/camera-configs/a2A2464-77umPRO_40747103_BehaviorSquid.pfs")
                        record("tracking_import", "completed")
                    except Exception as exc:
                        record("tracking_import", str(exc))
                        raise
                    await state("tracking_imported")
                    await cycle(2, "Tracking camera", "tracking")
                    await cycle(2, "Tracking camera", "tracking_repeat")
                finally:
                    await configure("restore_configuration", original)
            record("control_release_failure", client.release_failure)
    except Exception as exc:
        record("error", f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if gui["handle"]:
            with physical_coordinates():
                api.SetWindowPos(gui["handle"], None, original_bounds.left, original_bounds.top, 0, 0, 0x15)
        store.remove_client(principal)


asyncio.run(run())
