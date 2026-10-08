"""External count/decode and identity checks for a completed native dummy run."""
import argparse
import collections
import hashlib
import json
import statistics
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("label")
args = parser.parse_args()
run = json.loads((OUT / f"{args.label}.json").read_text())
session, trial = run["final_session"], run["final_trial"]
assert session["outcome"] == "SESSION_OUTCOME_COMPLETED"
assert session["cleanup_confirmed"]
assert trial["outcome"] == "TRIAL_OUTCOME_COMPLETED"
start, end = int(trial["start_monotonic_ns"]), int(trial["actual_end_monotonic_ns"])
assert end - start == 60_000_000_000
assert not run["final_reservation"].get("lock_held", False)
folder = Path(session["directory"]) / "protocol-data"
assert all(x["state"] == "METADATA_PERSISTENCE_SYNCED" for x in run["final_metadata"])
for file in folder.glob("*.json"):
    json.loads(file.read_text())
for file in folder.glob("*.jsonl"):
    for line in file.read_text().splitlines():
        json.loads(line)
assert not list(folder.glob("*velocit*"))
trial_log = json.loads(next(folder.glob("DUMMY_*_LOG.json")).read_text())
assert len(trial_log["outputs"]) == 7
assert all(x["closure"] == "OUTPUT_CLOSURE_CLOSED" and x["artifact_present"] for x in trial_log["outputs"])
result = {"session": session, "trial": trial, "metadata_synced": True,
          "reservation_unlocked": True, "expected_outputs_closed": 7, "velocities_absent": True, "videos": {}}
for video in sorted(folder.glob("*.mp4")):
    probe = subprocess.run(["C:/Dev/software/ffmpeg-4.3.2-2021/bin/ffprobe.exe", "-v", "error",
        "-count_frames", "-select_streams", "v:0", "-show_entries",
        "stream=codec_name,width,height,pix_fmt,r_frame_rate,duration,nb_read_frames", "-of", "json", str(video)],
        check=True, capture_output=True, text=True)
    stream = json.loads(probe.stdout)["streams"][0]
    count = int(stream["nb_read_frames"])
    if "stimulus" in video.name:
        rows = [json.loads(x)["payload"] for x in video.with_name(video.stem + "_frames.jsonl").read_text().splitlines()]
        completion = rows[-1]
        encoder = next(x for x in rows if x["kind"] == "encoder_outcome")
        header = rows[0]
        recipe = video.with_name(video.stem + "_LOG.json").read_bytes()
        assert hashlib.sha256(recipe).hexdigest() == header["recipe"]["sha256"]
        assert len(recipe) == header["recipe"]["byte_length"]
        assert header["identity"]["trial_id"] == trial["context"]["trial_id"]
        assert encoder["input_submitted_count"] == count == encoder["admitted_count"]
        assert encoder["exit_code"] == 0 and encoder["eof_sent"] and encoder["drain_confirmed"]
        assert completion["outcome"] == "completed" and not completion["unresolved_attempt_count"]
        times = [x["state"]["evaluation_host_ns"] for x in rows if x["kind"] == "render_group"]
        intervals = [(b-a)/1e6 for a,b in zip(times, times[1:])]
        details = {"completion": completion, "encoder": encoder, "recipe_digest_matches": True,
                   "render_interval_median_ms": statistics.median(intervals), "render_interval_max_ms": max(intervals)}
    else:
        rows = [json.loads(x) for x in video.with_name(video.stem + "_frames.jsonl").read_text().splitlines()]
        completion, header = rows[-1], rows[0]
        assert header["identity"]["trial_id"] == trial["context"]["trial_id"]
        assert completion["timing"]["recording_end_monotonic_ns"] == end
        assert completion["video"]["recorded_frame_count"] == count
        assert completion["outcome"] == "completed"
        assert completion["timing"]["accounting_complete"] and completion["post_cutoff"]["accounting_complete"]
        frames = [x for x in rows if x["type"] == "frame" and x["video_frame"] is not None]
        assert len(frames) == count and [x["video_frame"] for x in frames] == list(range(count))
        details = {"completion": completion, "nominal_fps": header["video"]["nominal_frame_rate_hz"]}
    decode = subprocess.run([str(Path.cwd() / ".tmp/dummy-tools/ffmpeg.exe"), "-v", "error",
        "-hwaccel", "none", "-i", str(video), "-map", "0:v:0", "-f", "null", "-"], capture_output=True, text=True)
    assert decode.returncode == 0 and not decode.stderr, decode.stderr
    result["videos"][video.name] = {"stream": stream, "full_cpu_decode": "passed",
        "delivered_fps_over_trial": count/60, **details}
    print(video.name, count, stream["duration"], "full decode passed", flush=True)
assert len(result["videos"]) == 3
(OUT / f"{args.label}-output-verification.json").write_text(json.dumps(result, indent=2))
print("All output checks passed", flush=True)
