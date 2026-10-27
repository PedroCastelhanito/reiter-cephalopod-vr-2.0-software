"""Prepare current-setting synthetic encoder cases; execute only with explicit GPU UUID."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import subprocess
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import ParseDict

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows.nvidia_device import discover_encoder_device
from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
from cephvr.visual_stimulus.config.review_layout import recording_layout
from cephvr.visual_stimulus.recording.encoding import ffmpeg_input_format

ROOT = Path(__file__).resolve().parents[3]


def plan(configuration):
    jobs = []
    for backend in configuration.backends:
        if backend.backend_name == "acquisition":
            for role in ("behavioral", "tracking", "eye_tracking"):
                settings = getattr(backend.acquisition, role)
                if not settings.enabled:
                    continue
                native = settings.device.settings
                formats = {"BayerRG8": "rgb24", "RGB8packed": "rgb24", "Mono8": "gray"}
                if native.pixel_format not in formats:
                    raise ValueError(
                        f"unconfirmed/unsupported synthetic source {native.pixel_format}"
                    )
                pulse = getattr(backend.acquisition.pulses, role)
                rate = (
                    pulse.requested_frequency_hz
                    if settings.device.frame_timing
                    == camera.FRAME_TIMING_EXTERNAL_TRIGGER
                    else native.frame_rate_hz
                )
                jobs.append(
                    {
                        "name": role,
                        "width": native.roi.width,
                        "height": native.roi.height,
                        "fps": rate,
                        "input_pixel_format": formats[native.pixel_format],
                        "ffmpeg_args": list(settings.ffmpeg_args.values),
                    }
                )
        elif backend.backend_name == "visual_stimulus":
            display = parse_display_json(
                backend.visual_stimulus.display.profile_json, max_bytes=16_777_216
            )
            options = tomllib.loads(
                (ROOT / "config/backends/visual_stimulus_config.toml").read_text()
            )
            layout = recording_layout(
                display, options["recording_runtime"]["review_scale_factor"]
            )
            numerator, denominator = display.review_refresh_rate()
            jobs.append(
                {
                    "name": "stimulus",
                    "width": layout.composite_width,
                    "height": layout.composite_height,
                    "fps": numerator / denominator,
                    "input_pixel_format": ffmpeg_input_format(display),
                    "ffmpeg_args": list(backend.visual_stimulus.review_ffmpeg_args),
                }
            )
    if not jobs or len(jobs) > 4:
        raise ValueError("expected one to four explicitly configured sources")
    return jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configuration", type=Path, default=ROOT / "config/last_configuration.json"
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-gpu-uuid")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seconds", type=int, choices=(5, 10), default=5)
    parser.add_argument("--rate-multiple", type=int, choices=(1, 2, 4), default=1)
    args = parser.parse_args()
    raw = json.loads(args.configuration.read_text())
    configuration = ParseDict(
        raw.get("configuration", raw), pb.ExperimentConfiguration()
    )
    jobs = plan(configuration)
    if not args.execute:
        print(
            json.dumps(
                {"execute": False, "gpu_resolved": False, "cases": jobs}, indent=2
            )
        )
        return
    if not args.expected_gpu_uuid or not args.output:
        raise ValueError(
            "execute requires an explicit expected GPU UUID and fresh output"
        )
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        raise ValueError("output must be a fresh path inside the workspace")
    gpu = discover_encoder_device()
    if gpu.uuid != args.expected_gpu_uuid:
        raise ValueError(
            "current unique RTX 2080 Ti UUID does not match the reviewed GPU"
        )
    spec = importlib.util.spec_from_file_location(
        "cephvr_encoding_probe", ROOT / "tools/encoding_probe.py"
    )
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    output.mkdir(parents=True)
    probe.write_json(
        output / "inputs.json",
        {
            "configuration": str(args.configuration.resolve()),
            "gpu": asdict(gpu),
            "seconds": args.seconds,
            "rate_multiple": args.rate_multiple,
            "scope": "unpaced synthetic source/filter/encoder throughput; saved quality/filter arguments retained; probe adds bf0, one-second keyframes and synthetic fragmented-MP4 mux flags; no capture/readback/storage durability or scientific fidelity claim",
            "cases": jobs,
        },
    )

    def encode(job):
        profile = {**job, "fps": job["fps"] * args.rate_multiple}
        frames = math.ceil(profile["fps"] * args.seconds)
        video = output / (job["name"] + ".mp4")
        argv = probe.command(profile, job["ffmpeg_args"], gpu.ordinal, frames, video)
        probe.write_json(output / (job["name"] + "-command.json"), argv)
        started = time.perf_counter()
        with (output / (job["name"] + "-stderr.log")).open("w") as stderr:
            try:
                result = subprocess.run(
                    argv, stdout=subprocess.PIPE, stderr=stderr, text=True, timeout=45
                )
                elapsed = time.perf_counter() - started
                (output / (job["name"] + "-progress.log")).write_text(result.stdout)
                return {
                    "name": job["name"],
                    "requested_frames": frames,
                    "exit_code": result.returncode,
                    "elapsed_s": elapsed,
                    "frames_per_elapsed_s": frames / elapsed
                    if result.returncode == 0
                    else None,
                }
            except subprocess.TimeoutExpired:
                return {
                    "name": job["name"],
                    "requested_frames": frames,
                    "exit_code": None,
                    "error": "45s bound reached; subprocess killed and reaped",
                    "frames_per_elapsed_s": None,
                }

    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        results = list(executor.map(encode, jobs))
    for result in results:
        video = output / (result["name"] + ".mp4")
        if video.exists():
            try:
                result["video"] = probe.probe_video(video, 45)
                streams = (result["video"].get("ffprobe") or {}).get("streams", [])
                stream = next(
                    (v for v in streams if v.get("codec_type") == "video"), {}
                )
                result["count_matches"] = str(stream.get("nb_read_frames")) == str(
                    result["requested_frames"]
                )
                result["validated"] = bool(
                    result["exit_code"] == 0
                    and result["count_matches"]
                    and result["video"]["decode_exit"] == 0
                    and not result["video"]["decode_error"]
                    and not result["video"]["ffprobe_error"]
                )
            except Exception as exc:
                result["validation_error"] = repr(exc)
        if not result.get("validated"):
            result["frames_per_elapsed_s"] = None
    probe.write_json(output / "summary.json", results)
    if any(not item.get("validated") for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
