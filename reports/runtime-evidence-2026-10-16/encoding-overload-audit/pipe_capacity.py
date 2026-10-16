"""Matched synthetic three-stream NVENC/overlapped-pipe capacity experiment."""
import argparse
import concurrent.futures
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import numpy as np

from cephvr.platform.windows.byte_stream import OverlappedPipe, PipeConstructionOwner
from cephvr.platform.windows.nvidia_device import resolve_cuda_ordinal
from cephvr.shared.encoder_io import WindowsEncoderInputAdapter

parser = argparse.ArgumentParser()
parser.add_argument("label")
parser.add_argument("--seconds", type=int, default=5)
parser.add_argument("--preset", default="p4")
parser.add_argument("--filter-threads", type=int)
parser.add_argument("--immediate-poll", action="store_true")
parser.add_argument("--lossless-camera", action="store_true")
parser.add_argument("--camera-codec", choices=("h264_nvenc", "hevc_nvenc"), default="h264_nvenc")
args = parser.parse_args()
assert 1 <= args.seconds <= 10
root = Path(__file__).resolve().parents[3]
evidence = Path(__file__).parent / args.label
evidence.mkdir(exist_ok=False)
media = root / ".tmp" / "encoding-audit-20261016" / args.label
media.mkdir(parents=True, exist_ok=False)
assert shutil.disk_usage(media).free > 30_000_000_000
device = resolve_cuda_ordinal("GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc")
fixtures = {}
rng = np.random.default_rng(20261016)
for name, width, height, channels, rate, fmt, cq in (
    ("behavior", 1760, 1716, 3, 30, "rgb24", 23),
    ("tracking", 1588, 1344, 1, 60, "gray", 23),
    ("stimulus", 1280, 1000, 4, 60, "rgba", 18),
):
    frames = rng.integers(0, 256, (8, height, width, channels), dtype=np.uint8)
    if channels == 4:
        frames[..., 3] = 255
    buffers = [bytearray(frame.tobytes()) for frame in frames]
    fixtures[name] = (width, height, rate, fmt, cq, buffers)
provenance = {"scope": "Unpaced synthetic capacity, three simultaneous streams; eight precomputed high-entropy frames looped, no camera/renderer/scientific acceptance", "arguments": vars(args), "device": {"uuid": device.uuid, "ordinal": device.ordinal}, "seed": 20261016, "fixture_sha256": {name: [hashlib.sha256(b).hexdigest() for b in item[-1]] for name, item in fixtures.items()}}
(evidence / "fixture.json").write_text(json.dumps(provenance, indent=2))
barrier = threading.Barrier(3)


def stream(name, fixture):
    width, height, rate, fmt, cq, buffers = fixture
    row = {"dimensions": [width, height], "source_format": fmt, "expected_frames": rate * args.seconds}
    endpoint = None
    process = None
    owner = PipeConstructionOwner()
    deadline = time.perf_counter_ns() + 40_000_000_000
    stderr = (evidence / (name + ".stderr")).open("wb")
    try:
        endpoint = OverlappedPipe.create_child_endpoint(parent_writable=True, owner=owner, deadline_ns=deadline)
        descriptor = msvcrt.open_osfhandle(endpoint.child_handle, os.O_RDONLY | os.O_BINARY)
        endpoint.child_handle = 0  # The CRT descriptor now owns this exact handle.
        stored = "gbrp" if args.lossless_camera and name == "behavior" else "yuv420p" if name == "tracking" else "yuv444p"
        transform = "scale=in_range=full:out_range=full" + ("" if stored == "gbrp" else ":out_color_matrix=bt709") + ",format=pix_fmts=" + stored
        command = ["ffmpeg", "-hide_banner", "-v", "error"]
        if args.filter_threads:
            command += ["-filter_threads", str(args.filter_threads)]
        command += ["-f", "rawvideo", "-pix_fmt", fmt, "-video_size", f"{width}x{height}", "-framerate", str(rate), "-i", "pipe:0", "-vf", transform, "-c:v", args.camera_codec if name != "stimulus" else "h264_nvenc", "-gpu", str(device.ordinal), "-pix_fmt", "+" + stored, "-preset", args.preset]
        command += ["-tune", "lossless", "-rc", "constqp", "-qp", "0"] if args.lossless_camera and name != "stimulus" else ["-rc", "vbr", "-cq", str(cq), "-b:v", "0"]
        command += ["-color_range", "pc", "-colorspace", "rgb" if stored == "gbrp" else "bt709", "-rc-lookahead", "0", "-spatial-aq", "0", "-temporal-aq", "0", "-bf", "0", "-y", str(media / (name + ".mp4"))]
        row["command"] = command
        try:
            process = subprocess.Popen(command, stdin=descriptor, stdout=subprocess.DEVNULL, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        finally:
            os.close(descriptor)
        row["pid"] = process.pid
        class Writer:
            def begin_write(self, data, *, deadline_ns):
                endpoint.parent.begin_write(data, deadline_ns=deadline_ns)
            def poll_write(self):
                return endpoint.parent.poll_write()
            def close_stdin(self, *, deadline_ns):
                endpoint.parent.close()
        writer = Writer()
        adapter = WindowsEncoderInputAdapter(writer, write_deadline_ns=lambda: deadline, close_deadline_ns=lambda: deadline)
        barrier.wait(timeout=10)
        started = time.perf_counter_ns()
        latencies = []
        calls = zeros = completed = 0
        for index in range(row["expected_frames"]):
            frame_start = time.perf_counter_ns()
            view = memoryview(buffers[index % 8])
            offset = 0
            while offset < len(view):
                if time.perf_counter_ns() >= deadline:
                    raise TimeoutError("owned benchmark deadline")
                was_pending = adapter._pending  # Experiment-only observation, no state mutation.
                amount = adapter.write_chunk(view[offset:])
                calls += 1
                if amount == 0 and args.immediate_poll and not was_pending:
                    amount = adapter.write_chunk(view[offset:])
                    calls += 1
                if amount:
                    offset += amount
                else:
                    zeros += 1
                    time.sleep(0.005)
            completed += 1
            latencies.append(time.perf_counter_ns() - frame_start)
        ended = time.perf_counter_ns()
        adapter.close_input()
        row.update(completed_frames=completed, input_elapsed_ns=ended-started, achieved_input_fps=completed/((ended-started)/1e9), write_calls=calls, wait_calls=zeros, frame_write_ns={"mean": float(np.mean(latencies)), "p50": float(np.percentile(latencies, 50)), "p95": float(np.percentile(latencies, 95)), "max": max(latencies)})
        row["exit"] = process.wait(timeout=max(0.1, (deadline-time.perf_counter_ns())/1e9))
    except Exception as exc:
        row["error"] = repr(exc)
        barrier.abort()
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if endpoint is not None:
            try:
                endpoint.close_child_copy()
                if endpoint.parent.has_pending_io:
                    endpoint.parent.request_cancel()
                    endpoint.parent.observe_cancelled(deadline_ns=time.perf_counter_ns()+2_000_000_000)
                endpoint.parent.close()
            except Exception as exc:
                row["pipe_cleanup_error"] = repr(exc)
        try:
            owner.retry_cleanup(deadline_ns=time.perf_counter_ns()+2_000_000_000)
        except Exception as exc:
            row["construction_cleanup_error"] = repr(exc)
        row["process_absent"] = process is None or process.poll() is not None
        row["construction_handles_retained"] = owner.cleanup_blocked
        stderr.close()
        row["media_bytes"] = (media / (name+".mp4")).stat().st_size if (media / (name+".mp4")).exists() else 0
    return name, row


with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results = dict(pool.map(lambda item: stream(*item), fixtures.items()))
(evidence / "results.json").write_text(json.dumps({**provenance, "streams": results}, indent=2)+"\n")
print(json.dumps(results, indent=2), flush=True)
assert all(row.get("exit") == 0 and row["process_absent"] and not row["construction_handles_retained"] and not any("error" in key for key in row) for row in results.values())

