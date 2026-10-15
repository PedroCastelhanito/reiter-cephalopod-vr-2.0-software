"""Posttrial four-video collection using unchanged count/software decode commands."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("encoding_probe", ROOT / "tools/encoding_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
parser = argparse.ArgumentParser()
parser.add_argument("--directory", type=Path, required=True)
parser.add_argument("--diagnostics", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--timeout", type=int, default=1800)
args = parser.parse_args()
result = dict(directory=str(args.directory), videos={}, frame_logs={}, recording_metrics=[], errors=[],
              collection_complete=False, method="Four bounded parallel videos, unchanged tools.encoding_probe.probe_video ffprobe count + full software ffmpeg decode; after normal closure only",
              started_monotonic_ns=time.perf_counter_ns())


def save():
    probe.write_json(args.output, result)


with ThreadPoolExecutor(max_workers=4) as pool:
    futures = {pool.submit(probe.probe_video, path, args.timeout): path for path in sorted(args.directory.rglob("*.mp4"))}
    for future in as_completed(futures):
        path = futures[future]
        try:
            result["videos"][str(path.relative_to(args.directory))] = future.result()
        except Exception as error:
            result["errors"].append(f"{path}: {type(error).__name__}: {error}")
        save()
for path in sorted(args.directory.rglob("*_frames.jsonl")):
    try:
        result["frame_logs"][str(path.relative_to(args.directory))] = probe.frame_log(path)
    except Exception as error:
        result["errors"].append(f"{path}: {type(error).__name__}: {error}")
result["recording_metrics"] = [json.loads(line) for line in args.diagnostics.read_text().splitlines()]
if len(result["recording_metrics"]) != 1 or len(result["videos"]) != 4:
    result["errors"].append("Expected exactly four videos and one completed recorder metrics record")
for path, video in result["videos"].items():
    if any(video.get(key) for key in ("ffprobe_exit", "decode_exit", "ffprobe_error", "decode_error")):
        result["errors"].append(f"{path}: count/decode failed or emitted strict stderr error")
result["finished_monotonic_ns"] = time.perf_counter_ns()
result["collection_complete"] = True
save()
print(args.output)
if result["errors"]:
    raise SystemExit(1)
