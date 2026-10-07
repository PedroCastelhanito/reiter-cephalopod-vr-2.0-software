"""Authorized real-controller camera/OpenCV checks, preserving saved settings."""

import asyncio
import ctypes
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
NAME = sys.argv[2] if len(sys.argv) > 2 else "mcu-update-managed"
result = {"controller_generation": sys.argv[1], "checks": {}}
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.FindWindowW.restype = ctypes.c_void_p
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]


def record(name, value):
    result["checks"][name] = value
    (OUT / f"{NAME}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)


def window(title):
    handle = user32.FindWindowW(None, title)
    pid = ctypes.c_ulong()
    if handle:
        user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    return {"handle": handle, "pid": pid.value, "visible": bool(handle and user32.IsWindowVisible(handle))}


async def run():
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                async def execute(name, method, request):
                    try:
                        outcome = await asyncio.wait_for(client.execute(method, request), 40)
                        record(name, asdict(outcome))
                        return outcome.succeeded is True
                    except Exception as exc:
                        record(name, {"error": f"{type(exc).__name__}: {exc}", "command_id": getattr(exc, "command_id", None)})
                        return False

                async def mcu(name, kind, signal=0):
                    return await execute(name, "ExecuteMicrocontrollerCommand", rpc.MicrocontrollerCommandRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, kind=kind, signal=signal))

                async def camera(name, role, kind, run_id=None):
                    request = rpc.CameraCommandRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, camera=role, kind=kind)
                    if run_id is not None:
                        request.preview_run_id = run_id
                    return await execute(name, "ExecuteCameraCommand", request)

                async def snapshot(name):
                    state = await client.get_snapshot()
                    raw = MessageToDict(state, preserving_proto_field_name=True)
                    raw.pop("configuration_values", None)
                    record(name, raw)
                    return state

                await snapshot("initial_snapshot")
                if not await mcu("mcu_connect", rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT):
                    return
                if NAME != "mcu-update-managed":
                    await mcu("mcu_trial_start", rpc.MICROCONTROLLER_COMMAND_KIND_START, 1)
                await mcu("mcu_status", rpc.MICROCONTROLLER_COMMAND_KIND_STATUS)
                await mcu("mcu_stop", rpc.MICROCONTROLLER_COMMAND_KIND_STOP)
                for role in (1, 2):
                    await camera(f"camera_{role}_connection", role, rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION)
                for role, title in ((1, "Behavior camera"), (2, "Tracking camera")):
                    if NAME != "mcu-update-managed" and role == 1:
                        continue
                    try:
                        if not await camera(f"camera_{role}_start", role, rpc.CAMERA_COMMAND_KIND_START_PREVIEW):
                            await snapshot(f"camera_{role}_failed_start")
                            continue
                        state = await snapshot(f"camera_{role}_started")
                        device = state.acquisition_devices.behavioral if role == 1 else state.acquisition_devices.tracking
                        run_id = device.preview_run_id
                        shown = await camera(f"camera_{role}_show", role, rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW, run_id)
                        record(f"camera_{role}_window", window(title))
                        await snapshot(f"camera_{role}_shown")
                        if shown:
                            await asyncio.sleep(1)
                            await camera(f"camera_{role}_hide", role, rpc.CAMERA_COMMAND_KIND_HIDE_PREVIEW, run_id)
                            await snapshot(f"camera_{role}_hidden_capture_continues")
                            if await camera(f"camera_{role}_reopen", role, rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW, run_id):
                                native = window(title)
                                record(f"camera_{role}_wm_close", {**native, "method": "PostMessageW WM_CLOSE to observed exact HighGUI title/handle"})
                                if not native["handle"] or not native["visible"]:
                                    raise RuntimeError("Expected visible native window missing")
                                if not user32.PostMessageW(native["handle"], 0x10, 0, 0):
                                    raise ctypes.WinError(ctypes.get_last_error())
                                await asyncio.sleep(0.5)
                                await snapshot(f"camera_{role}_native_closed_capture_continues")
                                record(f"camera_{role}_closed_window", window(title))
                                await camera(f"camera_{role}_show_after_x", role, rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW, run_id)
                    finally:
                        state = await client.get_snapshot()
                        device = state.acquisition_devices.behavioral if role == 1 else state.acquisition_devices.tracking
                        if device.preview_running and device.preview_run_id:
                            await camera(f"camera_{role}_stop", role, rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW, device.preview_run_id)
                        await snapshot(f"camera_{role}_final")
                        record(f"camera_{role}_final_window", window(title))
            record("control_release_failure", client.release_failure)
    except Exception as exc:
        record("probe_error", f"{type(exc).__name__}: {exc}")
    finally:
        store.remove_client(principal)


asyncio.run(run())
