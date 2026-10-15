"""Authenticated bounded rig progression. Each invocation performs one reviewed step."""

import argparse
import asyncio
import dataclasses
import json
from pathlib import Path
import subprocess
import sys
import time

from google.protobuf.json_format import MessageToDict

from cephvr.acquisition.v1 import camera_pb2
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.gui.device_requests import import_camera_preset
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("snapshot", "initialize", "configure", "textures60", "arena60", "combined60", "combined120", "combined180", "combined900", "lossless60", "restore", "shutdown"))
parser.add_argument("--label", required=True)
parser.add_argument("--abort-after", type=float)
args = parser.parse_args()
destination = OUT / args.label
destination.mkdir(exist_ok=False)
record = dict(mode=args.mode, label=args.label, events=[])


def view(message):
    return MessageToDict(message, preserving_proto_field_name=True)


def keep(label, value):
    record["events"].append(dict(label=label, host_monotonic_ns=time.perf_counter_ns(), value=value))
    (destination / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(label, json.dumps(value), flush=True)


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    if endpoint is None:
        raise RuntimeError("No managed application endpoint")
    record["controller_generation"] = endpoint.controller_generation
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    monitor = None
    stop = destination / "monitor.stop"
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                state = client.snapshot
                (destination / "initial.pb").write_bytes(state.SerializeToString())
                keep("initial_session", view(state.session))
                keep("participants", [view(p) for p in state.participants])
                if any(p.process.role == "tracking" for p in state.participants):
                    raise RuntimeError("Strict no-Tracking launch violated: Tracking process registered")
                if args.mode == "snapshot":
                    keep("snapshot", view(state))
                    return
                if args.mode == "shutdown":
                    keep("shutdown", dataclasses.asdict(await asyncio.wait_for(client.execute("ShutdownApplication"), 90)))
                    return
                if state.session.phase != pb.SESSION_PHASE_CONFIGURATION or state.prompts:
                    raise RuntimeError("Idle Configuration without prompts required")

                async def execute(method, request=None, timeout=100):
                    begin = time.perf_counter_ns()
                    result = await asyncio.wait_for(client.execute(method, request) if request is not None else client.execute(method), timeout)
                    keep(method, dict(dataclasses.asdict(result), elapsed_ns=time.perf_counter_ns() - begin))
                    if not result.succeeded:
                        raise RuntimeError(result.failure or f"{method} unsuccessful")
                    return result

                async def update(value):
                    return await execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=client.snapshot.configuration.revision, proposed=value))

                if args.mode == "restore":
                    await update(pb.ExperimentConfiguration.FromString((OUT / "original-configuration.pb").read_bytes()))
                    keep("restored_original_configuration", client.snapshot.configuration_values.current.SerializeToString() == (OUT / "original-configuration.pb").read_bytes())
                    return
                if args.mode == "initialize":
                    keep("mcu_connect", await dispatch_device_action(client, "mcu", {"kind": rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT}, principal))
                    cameras = json.loads(Path(r"C:\Users\ReiterU_PC\Desktop\Pedro\cameras_config.json").read_text())["cameras"]
                    roles = {"Behavior cam": 1, "Tracking cam": 2, "Eye tracking": 3}
                    for row in cameras:
                        await asyncio.wait_for(import_camera_preset(client, roles[row["role"]], row["values"]["preset"]), 90)
                        keep("import_" + row["serial"], view(client.snapshot.configuration_values.current))
                    (OUT / "imported-configuration.pb").write_bytes(client.snapshot.configuration_values.current.SerializeToString())
                    return

                case = "combined120" if args.mode == "configure" else args.mode
                candidate = pb.ExperimentConfiguration.FromString((OUT / f"candidate-{case}.pb").read_bytes())
                imported = pb.ExperimentConfiguration.FromString((OUT / "imported-configuration.pb").read_bytes())
                source = next(b.acquisition for b in imported.backends if b.backend_name == "acquisition")
                acquisition = next(b.acquisition for b in candidate.backends if b.backend_name == "acquisition")
                for role in ("behavioral", "tracking", "eye_tracking"):
                    selected = getattr(acquisition, role)
                    desired = camera_pb2.CameraDeviceConfiguration.FromString(selected.device.SerializeToString())
                    selected.device.CopyFrom(getattr(source, role).device)
                    selected.device.frame_timing = desired.frame_timing
                    selected.device.unaligned_free_running = desired.unaligned_free_running
                    if desired.frame_timing == camera_pb2.FRAME_TIMING_FREE_RUNNING:
                        selected.device.settings.frame_rate_hz = 60
                        selected.device.settings.ClearField("trigger_source")
                        selected.device.settings.ClearField("trigger_activation")
                    else:
                        selected.device.settings.trigger_source = desired.settings.trigger_source
                (destination / "effective-candidate.pb").write_bytes(candidate.SerializeToString())
                (destination / "effective-candidate.json").write_text(json.dumps(view(candidate), indent=2) + "\n", encoding="utf-8")
                for backend in candidate.backends:
                    if backend.backend_name in {"tracking", "synchronization"} and backend.enabled:
                        raise RuntimeError("Excluded backend enabled in candidate")
                    if backend.backend_name == "tracking" and backend.tracking.save_tracking_data:
                        raise RuntimeError("Tracking data saving enabled")
                await update(candidate)
                if args.mode == "configure":
                    for role, field in ((1, "behavioral"), (2, "tracking"), (3, "eye_tracking")):
                        await execute("ExecuteCameraCommand", rpc.CameraCommandRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, camera=role, kind=rpc.CAMERA_COMMAND_KIND_EXPORT_PFS, path=str(destination / f"{field}-adopted.pfs")))
                        await execute("ExecuteCameraCommand", rpc.CameraCommandRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, camera=role, kind=rpc.CAMERA_COMMAND_KIND_FINISH_EDITING))
                    keep("configured", view(client.snapshot))
                    return
                monitor = subprocess.Popen([sys.executable, str(OUT / "monitor.py"), "--output", str(destination / "monitor.jsonl"), "--stop", str(stop)], creationflags=subprocess.CREATE_NO_WINDOW)
                await execute("Setup")
                keep("ready", view(client.snapshot))
                (destination / "ready.pb").write_bytes(client.snapshot.SerializeToString())
                if any(p.process.role == "tracking" for p in client.snapshot.participants):
                    raise RuntimeError("Tracking participant unexpectedly registered")
                adopted = next(b.acquisition for b in client.snapshot.configuration_values.current.backends if b.backend_name == "acquisition")
                for field, serial in (("behavioral", "40065509"), ("tracking", "40747103"), ("eye_tracking", "40278236")):
                    camera = getattr(adopted, field)
                    if not camera.enabled or camera.device.device_id != serial:
                        raise RuntimeError(f"{field}: adopted participation/serial differs")
                eye = adopted.eye_tracking.device
                if eye.frame_timing != camera_pb2.FRAME_TIMING_FREE_RUNNING or not eye.unaligned_free_running or abs(eye.settings.frame_rate_hz - 60) > .01:
                    raise RuntimeError("Eye free-running60Hz readiness differs")
                await execute("StartSession", timeout=45)
                async def process_commands():
                    begin = time.perf_counter_ns()
                    with (destination / "active-processes.json").open("w", encoding="utf-8") as stream:
                        observed = await asyncio.to_thread(subprocess.run, ["pwsh", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object {$_.Name -match 'python|cephvr|ffmpeg'} | Select-Object ProcessId,ParentProcessId,Name,CreationDate,ExecutablePath,CommandLine | ConvertTo-Json -Depth 3"], stdout=stream, stderr=subprocess.PIPE, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
                    keep("active_process_inventory", dict(returncode=observed.returncode, stderr=observed.stderr, elapsed_ns=time.perf_counter_ns() - begin))
                command_task = asyncio.create_task(process_commands())
                seconds = 900 if args.mode == "combined900" else 180 if args.mode == "combined180" else 120 if args.mode == "combined120" else 60
                until = time.monotonic() + seconds + 90
                abort_sent = False
                while client.snapshot.session.phase != pb.SESSION_PHASE_ENDED:
                    trial_start = client.snapshot.trial.start_monotonic_ns
                    if args.abort_after is not None and not abort_sent and trial_start and time.perf_counter_ns() >= trial_start + int(args.abort_after * 1e9):
                        abort_sent = True
                        keep("planned_abort_request", dict(observed_ns=time.perf_counter_ns(), trial_start_ns=trial_start, after_seconds=args.abort_after))
                        try:
                            await execute("AbortNow", timeout=90)
                        finally:
                            keep("abort_snapshot", view(client.snapshot))
                            (destination / "abort-snapshot.pb").write_bytes(client.snapshot.SerializeToString())
                    if time.monotonic() >= until:
                        await execute("AbortNow", timeout=45)
                        raise RuntimeError("Normal completion deadline exceeded")
                    await asyncio.sleep(1)
                    if client.snapshot.prompts:
                        keep("unexpected_prompt", view(client.snapshot))
                        await execute("AbortNow", timeout=45)
                        raise RuntimeError("Runtime incident requires diagnosis before continuation")
                keep("final", view(client.snapshot))
                await command_task
                (destination / "final.pb").write_bytes(client.snapshot.SerializeToString())
                await execute("NewSession")
                keep("released", view(client.snapshot))
    except BaseException as error:
        keep("error", f"{type(error).__name__}: {error}")
        raise
    finally:
        if monitor is not None:
            stop.write_text("complete\n", encoding="utf-8")
            try:
                keep("monitor_exit", await asyncio.to_thread(monitor.wait, 10))
            except subprocess.TimeoutExpired:
                keep("monitor_exit", "unconfirmed; stop file present, no termination attempted")
        store.remove_client(principal)


asyncio.run(main())
