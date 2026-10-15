"""Bounded post-soak standalone codec-input plane fidelity; no camera access."""
import argparse
import ctypes
from ctypes import wintypes
import dataclasses
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.platform.windows.nvidia_device import discover_encoder_device
from cephvr.platform.windows.nvenc_capabilities import NvencProbeOwner
from cephvr.shared.credentials import default_runtime_root
from cephvr.shared.encoder_probe import ProbeResult
from cephvr.shared.ffmpeg_capabilities import probe_nvenc_capabilities
from cephvr.shared.ffmpeg_validation import validate_arguments

out = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--run", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--exited-generation", required=True)
args = parser.parse_args()
run = args.run.resolve()
events = json.loads((run / "run.json").read_text())["events"]
final = next(row["value"] for row in events if row["label"] == "final")
assert final["session"]["outcome"] == "SESSION_OUTCOME_COMPLETED" and final["session"]["cleanup_confirmed"]
assert int(final["trial"]["actual_end_monotonic_ns"]) - int(final["trial"]["start_monotonic_ns"]) == 900_000_000_000
collection = json.loads((run / "collection.json").read_text())
assert collection["collection_complete"] and not collection["errors"] and len(collection["videos"]) == 4
assert all(row["ffprobe_exit"] == row["decode_exit"] == 0 and not row["decode_error"] and not row["ffprobe_error"] for row in collection["videos"].values())
assert all(row["ffprobe"]["streams"][0]["nb_read_frames"] == str(27000 if "behavioral_cam" in name else 54000) for name, row in collection["videos"].items())
receipt = json.loads((default_runtime_root() / "recovery" / f"application-exit-{args.exited_generation}.json").read_text())
assert receipt["controller_generation"] == args.exited_generation and receipt["all_owned_processes_absent"]
endpoint = _existing_endpoint(default_runtime_root()) if (default_runtime_root() / "launcher.json").exists() else None
assert endpoint is None or endpoint.controller_generation == args.exited_generation
inventory = subprocess.run(["pwsh", "-NoProfile", "-Command", "ConvertTo-Json -InputObject @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'cephvr\\.|start_runtime_gui' } | Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine) -Depth 3"], capture_output=True, text=True, check=True)
assert json.loads(inventory.stdout) == []
args.output.mkdir(parents=True, exist_ok=False)
record = dict(scope="Standalone harness-owned helper processes; losslessness of identical prepared8bit full-range planarYUV444 input only, not Bayer/RGB round-trip or raw SDK samples", commands=[], cases=[], receipt=receipt, native_runtime_processes=[])

def save():
    (args.output / "result.json").write_text(json.dumps(record, indent=2))
    (out / "lossless-feasibility.json").write_text(json.dumps(record, indent=2))

def execute(argv, *, deadline_ns):
    number = len(record["commands"])
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    times = [(wintypes.FILETIME)() for _ in range(4)]
    native = ctypes.WinDLL("kernel32", use_last_error=True).GetProcessTimes
    native.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    native.restype = wintypes.BOOL
    ok = native(int(proc._handle), *(ctypes.byref(value) for value in times))
    row = dict(argv=argv, pid=proc.pid, observed_ns=time.perf_counter_ns(), creation_time_100ns=(times[0].dwHighDateTime << 32 | times[0].dwLowDateTime) if ok else None)
    record["commands"].append(row)
    stdout, stderr = b"", b""
    timeout_error = None
    try:
        stdout, stderr = proc.communicate(timeout=max(.01, (deadline_ns-time.perf_counter_ns())/1e9))
    except subprocess.TimeoutExpired as error:
        timeout_error = error
        row["timed_out"] = True
        proc.terminate()
        row["terminated_exact_owned_process_after_timeout"] = True
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired as cleanup_error:
            stdout, stderr = cleanup_error.output or b"", cleanup_error.stderr or b""
            row["cleanup_error"] = str(cleanup_error)
    finally:
        row["returncode"] = proc.poll()
        row["owned_process_still_live"] = proc.poll() is None
        row["end_ns"] = time.perf_counter_ns()
        (args.output / f"command-{number:02d}-stdout.txt").write_bytes(stdout)
        (args.output / f"command-{number:02d}-stderr.txt").write_bytes(stderr)
        save()
    if timeout_error is not None:
        raise timeout_error
    assert proc.returncode == 0, stderr.decode(errors="replace")[-2048:]
    return ProbeResult(proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace"))

class Probe:
    def run(self, executable, arguments, *, deadline_ns):
        return execute([executable, *arguments], deadline_ns=deadline_ns)

def lossless_arguments(values):
    result = []
    for name, value in zip(values[::2], values[1::2], strict=True):
        if name == "-cq":
            continue
        result.extend((name, "constqp" if name == "-rc" else value))
    result.extend(("-tune", "lossless", "-qp", "0"))
    return result

try:
    executable = shutil.which("ffmpeg")
    assert executable is not None
    device = discover_encoder_device()
    assert device.uuid == "GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc"
    record["device"] = dataclasses.asdict(device)
    owner = NvencProbeOwner()
    caps = probe_nvenc_capabilities(executable, codec="h264_nvenc", device=device, nvenc_owner=owner, probe=Probe(), deadline_ns=time.perf_counter_ns()+60_000_000_000)
    record["capabilities_repr"] = repr(caps)
    assert caps.device_lossless["h264_nvenc"]
    snapshot = pb.Snapshot.FromString((run / "final.pb").read_bytes())
    candidate = pb.ExperimentConfiguration.FromString(snapshot.configuration_values.current.SerializeToString())
    acquisition = next(row.acquisition for row in candidate.backends if row.backend_name == "acquisition")
    assessment = json.loads((run / "assessment.json").read_text())
    for field in ("behavioral", "tracking", "eye_tracking"):
        camera = getattr(acquisition, field)
        width, height = camera.device.settings.roi.width, camera.device.settings.roi.height
        rate = next(value["header"]["video"]["nominal_frame_rate_hz"] for name, value in assessment["sources"].items() if name.endswith(f"_{field}_cam_frames.jsonl"))
        baseline = list(camera.ffmpeg_args.values)
        values = lossless_arguments(baseline)
        effective = validate_arguments(values, capabilities=caps, input_pixel_format="gray" if camera.device.settings.pixel_format == "Mono8" else "rgb24", recording_bit_depth=8, input_width=width, input_height=height)
        row = dict(camera=field, device_id=camera.device.device_id, width=width, height=height, rate_hz=rate, frames=6, baseline_args=baseline, candidate_args=values, resolved=dataclasses.asdict(effective))
        record["cases"].append(row)
        original, encoded, decoded = [args.output / f"{field}{suffix}" for suffix in ("-input.yuv", "-lossless.mp4", "-decoded.yuv")]
        x, y = np.arange(width, dtype=np.uint32)[None,:], np.arange(height, dtype=np.uint32)[:,None]
        with original.open("xb") as stream:
            for frame in range(6):
                for plane in range(3):
                    stream.write(((x*(13+plane*2)+y*(7+plane*4)+frame*23+plane*67+(x//31)*(y//17)) & 255).astype(np.uint8).tobytes())
        codec_values = [value for pair in zip(values[::2], values[1::2], strict=True) if pair[0] != "-vf" for value in pair]
        result = execute([executable, "-v", "error", "-nostdin", "-n", "-f", "rawvideo", "-pixel_format", "yuv444p", "-video_size", f"{width}x{height}", "-framerate", str(rate), "-color_range", "pc", "-colorspace", "bt709", "-i", str(original), "-an", *codec_values, "-gpu", str(device.ordinal), "-bf", "0", "-frames:v", "6", "-fps_mode", "passthrough", str(encoded)], deadline_ns=time.perf_counter_ns()+60_000_000_000)
        assert not result.stderr.strip()
        result = execute([shutil.which("ffprobe"), "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(encoded)], deadline_ns=time.perf_counter_ns()+30_000_000_000)
        stream = json.loads(result.stdout)["streams"][0]
        row["encoded_stream"] = stream
        assert int(stream["nb_read_frames"]) == 6 and stream["width"] == width and stream["height"] == height
        assert stream["pix_fmt"] in {"yuv444p", "yuvj444p"} and stream["color_range"] == "pc"
        result = execute([executable, "-v", "error", "-nostdin", "-n", "-hwaccel", "none", "-i", str(encoded), "-map", "0:v:0", "-an", "-pix_fmt", "+"+stream["pix_fmt"], "-c:v", "rawvideo", "-f", "rawvideo", str(decoded)], deadline_ns=time.perf_counter_ns()+30_000_000_000)
        assert not result.stderr.strip()
        row.update(input_bytes=original.stat().st_size, decoded_bytes=decoded.stat().st_size, input_sha256=hashlib.sha256(original.read_bytes()).hexdigest(), decoded_sha256=hashlib.sha256(decoded.read_bytes()).hexdigest())
        row["identical_prepared_yuv_planes"] = row["input_sha256"] == row["decoded_sha256"] and row["input_bytes"] == row["decoded_bytes"] == width*height*3*6
        assert row["identical_prepared_yuv_planes"]
        del camera.ffmpeg_args.values[:]
        camera.ffmpeg_args.values.extend(values)
        save()
    program = json.loads((out / "program-combined120.json").read_text())
    for epoch in program["sequence"]:
        assert epoch["duration"]["duration"]["seconds"] == "40"
        epoch["duration"]["duration"]["seconds"] = "20"
    candidate.trials[0].stimulus.program.program_json = json.dumps(program, separators=(",", ":"))
    candidate.trials[0].stimulus.program.logical_source_reference = str(out / "program-lossless60.json")
    (out / "program-lossless60.json").write_text(json.dumps(program, indent=2))
    (out / "candidate-lossless60.pb").write_bytes(candidate.SerializeToString())
    record["passed"] = True
except BaseException as error:
    record["error"] = f"{type(error).__name__}: {error}"
    save()
    raise
save()
print(json.dumps(dict(passed=True, device=record["device"], cases=[dict(camera=row["camera"], identical_prepared_yuv_planes=row["identical_prepared_yuv_planes"]) for row in record["cases"]])))
