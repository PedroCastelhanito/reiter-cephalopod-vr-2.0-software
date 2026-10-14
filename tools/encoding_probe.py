"""Synthetic encoder isolation and read-only collection; never starts rig devices."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import time
import tomllib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def command(
    profile: dict[str, Any], args: list[str], gpu: int, frames: int, output: Path
) -> list[str]:
    width, height, rate = profile["width"], profile["height"], profile["fps"]
    fmt = profile["input_pixel_format"]
    if any(type(v) is not int or v <= 0 for v in (width, height)):
        raise ValueError("width/height must be confirmed positive integers")
    if type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0:
        raise ValueError("fps must be a confirmed positive rate")
    if fmt not in {"rgba", "rgb24", "gray"}:
        raise ValueError(
            "this synthetic probe supports only explicitly confirmed 8-bit sources"
        )
    return [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-n",
        "-progress",
        "pipe:1",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={width}x{height}:rate={rate},format={fmt}",
        "-frames:v",
        str(frames),
        "-an",
        *args,
        "-gpu",
        str(gpu),
        "-bf",
        "0",
        "-force_key_frames",
        "expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+1))",
        "-movflags",
        "+frag_keyframe+empty_moov+default_base_moof",
        str(output),
    ]


def probe_video(path: Path, timeout: float) -> dict[str, Any]:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    decode = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-hwaccel",
            "none",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "size_bytes": path.stat().st_size,
        "ffprobe_exit": probe.returncode,
        "ffprobe": json.loads(probe.stdout) if probe.returncode == 0 else None,
        "ffprobe_error": probe.stderr,
        "decode_exit": decode.returncode,
        "decode_error": decode.stderr,
    }


def frame_log(path: Path) -> dict[str, Any]:
    types: Counter[str] = Counter()
    source: Counter[str] = Counter()
    video: Counter[str] = Counter()
    captures: Counter[str] = Counter()
    endings = {}
    first = last = None
    invalid = dropped = received = groups = 0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("record must be an object")
            row = row.get("payload", row)
            if not isinstance(row, dict):
                raise ValueError("payload must be an object")
            kind = row.get("kind", row.get("type", "unknown"))
            if not isinstance(kind, str):
                raise ValueError("record kind/type must be a string")
            types[kind] += 1
            if kind == "frame":
                received += 1
                invalid += row.get("invalid_code") is not None
                dropped += bool(row.get("dropped"))
                source[row.get("video_disposition", "unknown")] += 1
                stamp = row.get("host_receipt_ns")
            elif kind == "render_group":
                groups += 1
                stamp = row["state"]["evaluation_host_ns"]
                captures.update(c["disposition"] for c in row.get("captures", []))
            else:
                stamp = None
            if stamp is not None:
                first = stamp if first is None else first
                last = stamp
            if kind == "video_frame":
                video[row["disposition"]] += 1
            if kind in {"completion", "encoder_outcome"}:
                endings[kind] = row
    return {
        "record_types": dict(types),
        "received_frames": received,
        "invalid_images": invalid,
        "source_dropped_flags": dropped,
        "source_dispositions": dict(source),
        "video_dispositions": dict(video),
        "render_groups": groups,
        "initial_capture_dispositions": dict(captures),
        "first_source_ns": first,
        "last_source_ns": last,
        "final_records": endings,
        "completion_present": "completion" in endings,
    }


def benchmark(ns: argparse.Namespace) -> None:
    profiles = json.loads(ns.profiles.read_text(encoding="utf-8-sig"))
    names = ns.sources.split(",")
    if len(set(names)) != len(names) or not names or len(names) > 4:
        raise ValueError("select one to four distinct sources")
    acquisition = tomllib.loads(
        (ROOT / "config/backends/acquisition_config.toml").read_text()
    )
    stimulus = tomllib.loads(
        (ROOT / "config/backends/visual_stimulus_config.toml").read_text()
    )
    jobs = []
    for name in names:
        profile = profiles[name]
        args = list(
            stimulus["recording"]["ffmpeg_args"]
            if name == "stimulus"
            else acquisition["cameras"][name]["ffmpeg_args"]
        )
        args[args.index("-cq") + 1] = str(ns.cq)
        frames = math.ceil(profile["fps"] * ns.seconds)
        argv = command(profile, args, ns.gpu, frames, ns.output / f"{name}.mp4")
        jobs.append((name, frames, argv))
    ns.output.mkdir(parents=True, exist_ok=False)
    write_json(
        ns.output / "inputs.json",
        {
            "profiles": profiles,
            "sources": names,
            "cq": ns.cq,
            "gpu_ordinal": ns.gpu,
            "seconds": ns.seconds,
            "scope": "synthetic lavfi encoder throughput, not capture/pipes or scientific fidelity",
            "tool_paths": {
                tool: shutil.which(tool) for tool in ("ffmpeg", "ffprobe", "nvidia-smi")
            },
        },
    )
    for tool in ("ffmpeg", "ffprobe", "nvidia-smi"):
        (ns.output / f"{tool}-version.txt").write_text(
            subprocess.check_output(
                [tool, "--version" if tool == "nvidia-smi" else "-version"],
                text=True,
                timeout=ns.timeout,
            ),
            encoding="utf-8",
        )

    def run(job: tuple[str, int, list[str]]) -> dict[str, Any]:
        name, frames, argv = job
        write_json(ns.output / f"{name}-command.json", argv)
        started = time.perf_counter()
        error = None
        code = None
        with (
            (ns.output / f"{name}-progress.txt").open("w") as progress,
            (ns.output / f"{name}-stderr.txt").open("w") as errors,
        ):
            try:
                code = subprocess.run(
                    argv, stdout=progress, stderr=errors, timeout=ns.timeout
                ).returncode
            except subprocess.TimeoutExpired:
                error = "timeout; subprocess terminated; no successful throughput claim"
            except OSError as exc:
                error = f"launch failed: {exc}"
        elapsed = time.perf_counter() - started
        return {
            "source": name,
            "requested_frames": frames,
            "exit_code": code,
            "error": error,
            "elapsed_s": elapsed,
            "start_perf_counter_s": started,
            "requested_frames_per_elapsed_s": frames / elapsed if code == 0 else None,
        }

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(run, jobs))
    # Decode/probe only after all timed encoders finish, avoiding measurement interference.
    for result in results:
        path = ns.output / f"{result['source']}.mp4"
        if path.is_file():
            try:
                result["video"] = probe_video(path, ns.timeout)
                streams = (result["video"].get("ffprobe") or {}).get("streams", [])
                video: dict[str, Any] = next(
                    (s for s in streams if s.get("codec_type") == "video"), {}
                )
                result["frame_count_matches"] = str(video.get("nb_read_frames")) == str(
                    result["requested_frames"]
                )
            except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
                result["validation_error"] = f"probe/decode failed: {exc}"
        if (
            not result.get("frame_count_matches")
            or result.get("video", {}).get("decode_exit") != 0
            or result.get("video", {}).get("decode_error")
            or result.get("video", {}).get("ffprobe_error")
        ):
            result["requested_frames_per_elapsed_s"] = None
    write_json(ns.output / "summary.json", results)
    print(ns.output / "summary.json")
    if any(
        r["exit_code"] != 0
        or r.get("validation_error")
        or not r.get("frame_count_matches")
        or r.get("video", {}).get("decode_exit") != 0
        or r.get("video", {}).get("decode_error")
        or r.get("video", {}).get("ffprobe_error")
        for r in results
    ):
        raise SystemExit(1)


def collect(ns: argparse.Namespace) -> None:
    result: dict[str, Any] = {
        "directory": str(ns.directory.resolve()),
        "videos": {},
        "frame_logs": {},
        "recording_metrics": [],
        "errors": [],
    }
    for path in sorted(ns.directory.rglob("*.mp4")):
        try:
            result["videos"][str(path.relative_to(ns.directory))] = probe_video(
                path, ns.timeout
            )
        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            result["errors"].append(f"{path}: {exc}")
    for path in sorted(ns.directory.rglob("*_frames.jsonl")):
        try:
            result["frame_logs"][str(path.relative_to(ns.directory))] = frame_log(path)
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
            result["errors"].append(f"{path}: incomplete/invalid log: {exc}")
    if ns.diagnostics:
        try:
            with ns.diagnostics.open(encoding="utf-8-sig", errors="replace") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if (
                        isinstance(row, dict)
                        and row.get("event") == "recording_metrics"
                    ):
                        result["recording_metrics"].append(row)
            if not result["recording_metrics"]:
                result["errors"].append(
                    "requested diagnostics contain no recording_metrics"
                )
        except OSError as exc:
            result["errors"].append(f"{ns.diagnostics}: {exc}")
    if not result["videos"] and not result["frame_logs"]:
        result["errors"].append("no video or frame-log evidence found")
    for path, video in result["videos"].items():
        if any(
            video.get(key)
            for key in ("ffprobe_exit", "decode_exit", "ffprobe_error", "decode_error")
        ):
            result["errors"].append(
                f"{path}: probe/decode failed; inspect video diagnostics"
            )
    write_json(ns.output, result)
    print(ns.output)
    if result["errors"]:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    bench = subs.add_parser("bench")
    bench.add_argument("--profiles", type=Path, required=True)
    bench.add_argument(
        "--sources",
        required=True,
        help="comma-separated behavioral,tracking,eye_tracking,stimulus",
    )
    bench.add_argument("--cq", type=int, choices=(16, 23), required=True)
    bench.add_argument("--gpu", type=int, required=True)
    bench.add_argument("--seconds", type=int, default=60)
    bench.add_argument("--output", type=Path, required=True)
    bench.add_argument("--timeout", type=float, default=300)
    collector = subs.add_parser("collect")
    collector.add_argument("--directory", type=Path, required=True)
    collector.add_argument("--diagnostics", type=Path)
    collector.add_argument("--output", type=Path, required=True)
    collector.add_argument("--timeout", type=float, default=300)
    ns = parser.parse_args()
    if ns.timeout <= 0 or not math.isfinite(ns.timeout):
        parser.error("timeout must be positive and finite")
    if ns.output.exists():
        parser.error("output already exists; use a fresh run path")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            parser.error(f"{tool} must be available on PATH")
    if ns.mode == "bench":
        if ns.gpu < 0 or ns.seconds <= 0 or not shutil.which("nvidia-smi"):
            parser.error(
                "bench needs a nonnegative GPU, positive duration and nvidia-smi"
            )
        benchmark(ns)
    else:
        if not ns.directory.is_dir():
            parser.error("recording directory does not exist")
        collect(ns)


if __name__ == "__main__":
    main()
