"""Fresh saved-profile engineering trials; no MCU outputs or Tracking processing."""

import argparse
import asyncio
import dataclasses
import json
from pathlib import Path
import subprocess
import sys
import time

from google.protobuf.json_format import MessageToDict, ParseDict

from cephvr.acquisition.v1 import camera_pb2
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

parser = argparse.ArgumentParser()
parser.add_argument("case", choices=("textures60", "arena60", "combined60", "off60", "cq18", "threecam60", "p160", "lossless60", "abort60", "abort120", "restore"))
parser.add_argument("--label", required=True)
args = parser.parse_args()
root = Path.cwd()
out = Path(__file__).parent
run = out / args.label
run.mkdir(exist_ok=False)
record = {"case": args.case, "events": []}


def view(value):
    return MessageToDict(value, preserving_proto_field_name=True)


def keep(name, value):
    record["events"].append({"name": name, "monotonic_ns": time.perf_counter_ns(), "value": value})
    (run / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(name, json.dumps(value)[:1500], flush=True)


def candidate():
    saved = json.loads((out / "original-settings/last_configuration.json").read_text())
    config = ParseDict(saved["configuration"], pb.ExperimentConfiguration())
    config.subject = "DUMMY"
    config.experiment = "audit_" + args.label[:24]
    recording_root = root / ".tmp" / "encoding-audit-20261016"
    recording_root.mkdir(parents=True, exist_ok=True)
    config.recording_root = str(recording_root.resolve())
    config.mode = pb.SESSION_MODE_OPEN_LOOP
    del config.trials[1:]
    del config.gaps[:]
    for backend in config.backends:
        backend.enabled = backend.backend_name in {"acquisition", "visual_stimulus"}
        if backend.backend_name == "tracking":
            backend.tracking.save_tracking_data = False
    acquisition = next(b.acquisition for b in config.backends if b.backend_name == "acquisition")
    visual = next(b.visual_stimulus for b in config.backends if b.backend_name == "visual_stimulus")
    acquisition.pulses.trial_state_enabled = False
    acquisition.pulses.projector_flip_enabled = False
    for name in ("behavioral", "tracking", "eye_tracking"):
        camera = getattr(acquisition, name)
        camera.enabled = name != "eye_tracking" or args.case == "threecam60"
        camera.save_video = args.case != "off60"
        camera.device.frame_timing = camera_pb2.FRAME_TIMING_FREE_RUNNING
        camera.device.unaligned_free_running = True
        camera.device.settings.ClearField("trigger_source")
        camera.device.settings.ClearField("trigger_activation")
        if args.case == "cq18":
            values = camera.ffmpeg_args.values
            values[list(values).index("-cq") + 1] = "18"
    visual.save_visual_stimulus_data = args.case != "off60"
    if args.case == "p160":
        for name in ("behavioral", "tracking"):
            values = getattr(acquisition, name).ffmpeg_args.values
            values[list(values).index("-preset")+1] = "p1"
        values = visual.review_ffmpeg_args
        values[list(values).index("-preset")+1] = "p1"
    if args.case == "lossless60":
        for name in ("behavioral", "tracking"):
            camera = getattr(acquisition, name)
            values = list(camera.ffmpeg_args.values)
            for key in ("-rc", "-cq", "-b:v"):
                index = values.index(key)
                del values[index:index+2]
            values += ["-rc", "constqp", "-qp", "0", "-tune", "lossless"]
            del camera.ffmpeg_args.values[:]
            camera.ffmpeg_args.values.extend(values)
        # E13 review video remains lossy; camera probes do not change that policy.
    program = json.loads(config.trials[0].stimulus.program.program_json)
    if args.case in {"arena60", "combined60"}:
        fixture = json.loads((out / "arena-fixture.json").read_text())
        next(a for a in program["assets"] if a["asset_id"] == "circular")["logical_path"] = fixture["logical_path"]
    sequence = program["sequence"]
    if args.case in {"textures60", "off60", "cq18", "abort60", "abort120", "threecam60", "p160", "lossless60"}:
        sequence = [e for e in sequence if e.get("scene_id") == "textures"]
        program["assets"] = [a for a in program["assets"] if a["asset_id"] != "circular"]
        program["instances"] = [i for i in program["instances"] if i["family"] != "arena"]
        program["scenes"] = [s for s in program["scenes"] if s["scene_id"] == "textures"]
        config.trials[0].stimulus.arena_boundaries.boundaries_json = json.dumps({"format_version": 1, "bindings": []})
    elif args.case == "arena60":
        sequence = [e for e in sequence if e.get("scene_id") == "arena"]
    seconds = 120 if args.case == "abort120" else 60
    assert sequence and seconds % len(sequence) == 0
    for epoch in sequence:
        epoch["duration"]["duration"]["seconds"] = str(seconds // len(sequence))
    program["sequence"] = sequence
    config.trials[0].stimulus.program.program_json = json.dumps(program, separators=(",", ":"))
    (run / "program.json").write_text(json.dumps(program, indent=2) + "\n", encoding="utf-8")
    return config, seconds


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint is not None
    record["generation"] = endpoint.controller_generation
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    monitor = None
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                assert not client.snapshot.prompts
                (run / "before.pb").write_bytes(client.snapshot.SerializeToString())
                original = out / "runtime-original-configuration.pb"
                if not original.exists():
                    original.write_bytes(client.snapshot.configuration_values.current.SerializeToString())

                async def execute(name, request=None, timeout=90):
                    start = time.perf_counter_ns()
                    result = await asyncio.wait_for(client.execute(name, request) if request is not None else client.execute(name), timeout)
                    keep(name, {**dataclasses.asdict(result), "elapsed_ns": time.perf_counter_ns() - start})
                    assert result.succeeded, result.failure
                    return result

                config, seconds = (pb.ExperimentConfiguration.FromString(original.read_bytes()), 0) if args.case == "restore" else candidate()
                (run / "candidate.pb").write_bytes(config.SerializeToString())
                (run / "candidate.json").write_text(json.dumps(view(config), indent=2) + "\n", encoding="utf-8")
                await execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=client.snapshot.configuration.revision, proposed=config))
                if args.case == "restore":
                    return
                monitor = subprocess.Popen([sys.executable, str(root / "reports/runtime-evidence-2026-10-15/open-loop-soak/resume-1/monitor.py"), "--output", str(run / "monitor.jsonl"), "--stop", str(run / "monitor.stop")], creationflags=subprocess.CREATE_NO_WINDOW)
                await execute("Setup")
                (run / "ready.pb").write_bytes(client.snapshot.SerializeToString())
                keep("ready", view(client.snapshot))
                assert not any(p.process.role == "tracking" for p in client.snapshot.participants)
                intended = next(b.acquisition for b in config.backends if b.backend_name == "acquisition")
                adopted = next(b.acquisition for b in client.snapshot.configuration_values.current.backends if b.backend_name == "acquisition")
                assert not adopted.pulses.trial_state_enabled and not adopted.pulses.projector_flip_enabled
                for name in ("behavioral", "tracking", "eye_tracking"):
                    expected, actual = getattr(intended, name), getattr(adopted, name)
                    assert expected.enabled == actual.enabled
                    if actual.enabled:
                        assert actual.device.frame_timing == camera_pb2.FRAME_TIMING_FREE_RUNNING
                        assert actual.device.unaligned_free_running
                        assert actual.device.settings.roi == expected.device.settings.roi
                        assert actual.device.settings.pixel_format == expected.device.settings.pixel_format
                        assert abs(actual.device.settings.frame_rate_hz - expected.device.settings.frame_rate_hz) < 0.01
                        assert actual.ffmpeg_args == expected.ffmpeg_args
                await execute("StartSession", timeout=45)
                deadline = time.monotonic() + seconds + 95
                aborted = False
                while client.snapshot.session.phase != pb.SESSION_PHASE_ENDED:
                    if args.case in {"abort60", "abort120"} and not aborted and client.snapshot.trial.start_monotonic_ns and time.perf_counter_ns() - client.snapshot.trial.start_monotonic_ns >= 5_000_000_000:
                        aborted = True
                        keep("retired_trial_boundary_ns", client.snapshot.trial.start_monotonic_ns + seconds * 1_000_000_000)
                        await execute("AbortNow")
                    if client.snapshot.prompts or time.monotonic() >= deadline:
                        keep("unexpected", view(client.snapshot))
                        await execute("AbortNow")
                        raise RuntimeError("Incident or original completion deadline exceeded")
                    await asyncio.sleep(0.5)
                keep("final", view(client.snapshot))
                (run / "final.pb").write_bytes(client.snapshot.SerializeToString())
                await execute("NewSession")
                keep("released", view(client.snapshot))
    except BaseException as error:
        if "client" in locals() and client.views.current is not None:
            (run / "failure.pb").write_bytes(client.snapshot.SerializeToString())
            keep("failure_snapshot", view(client.snapshot))
        keep("error", f"{type(error).__name__}: {error}")
        raise
    finally:
        if monitor is not None:
            (run / "monitor.stop").write_text("complete\n")
            try:
                keep("monitor_exit", await asyncio.to_thread(monitor.wait, 10))
            except subprocess.TimeoutExpired:
                keep("monitor_exit", "unconfirmed; stop requested")
        store.remove_client(principal)


asyncio.run(main())
