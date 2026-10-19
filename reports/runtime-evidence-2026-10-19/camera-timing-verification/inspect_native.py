"""Post-run source/terminal/cadence checks and full video decoding."""

import collections
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess

OUT = Path(__file__).resolve().parent


def jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def cadence(groups):
    gaps = []
    for a, b in zip(groups, groups[1:]):
        ta = a["state"]["evaluation_host_ns"]
        tb = b["state"]["evaluation_host_ns"]
        submissions = a["submissions"]
        gaps.append({
            "group_id": a["group_id"],
            "relative_s": (ta - groups[0]["state"]["evaluation_host_ns"]) / 1e9,
            "gap_ms": (tb - ta) / 1e6,
            "evaluation_to_first_swap_ms": (min(s["entry_host_ns"] for s in submissions) - ta) / 1e6,
            "max_swap_duration_ms": max((s["return_host_ns"] - s["entry_host_ns"]) / 1e6 for s in submissions),
            "last_swap_to_next_evaluation_ms": (tb - max(s["return_host_ns"] for s in submissions)) / 1e6,
        })
    values = sorted(g["gap_ms"] for g in gaps)
    return {"median_ms": statistics.median(values), "p99_ms": values[int(.99 * (len(values)-1))],
            "max_ms": max(values), "gaps_over_25ms": sum(g > 25 for g in values),
            "gaps_over_100ms": sum(g > 100 for g in values),
            "largest_gaps": sorted(gaps, key=lambda g: g["gap_ms"], reverse=True)[:8]}


results = []
for config_path in Path(".tmp/ctverify").rglob("SESSION_CONFIG.json"):
    directory = config_path.parent
    trial_path = next(p for p in directory.glob("*_LOG.json") if not p.name.endswith("stimulus_LOG.json"))
    trial = json.loads(trial_path.read_text())
    events = jsonl(directory / "SESSION_LOG.jsonl")
    cameras = {}
    for path in directory.glob("*cam_frames.jsonl"):
        rows = jsonl(path)
        frames = [r for r in rows if r["type"] == "frame"]
        mappings = [r for r in rows if r["type"] == "video_frame"]
        complete = rows[-1]
        assert complete["type"] == "completion"
        assert [f["frame_id"] for f in frames] == list(range(len(frames)))
        assert len(frames) == complete["timing"]["final_received_frame_count"]
        assert len(mappings) == complete["video"]["recorded_frame_count"]
        cameras[rows[0]["identity"]["camera_role"]] = {
            "identity": rows[0]["identity"], "completion": complete,
            "source_rows": len(frames), "mapping_rows": len(mappings),
            "dropped_rows": sum(f["dropped"] for f in frames),
            "invalid_rows": sum(f["invalid_code"] is not None for f in frames),
        }
    evidence = [r["payload"] for r in jsonl(next(directory.glob("*stimulus_frames.jsonl")))]
    groups = [r for r in evidence if r["kind"] == "render_group"]
    assert [r["group_id"] for r in groups] == list(range(len(groups)))
    result = {"session_directory": str(directory.parent.resolve()), "trial_outcome": trial["outcome"],
              "trial_complete": trial["complete"], "outputs": trial["outputs"], "events": events,
              "cameras": cameras, "stimulus": {"cadence": cadence(groups), "groups": len(groups),
              "record_types": dict(collections.Counter(r["kind"] for r in evidence)),
              "completion": evidence[-1], "encoder": [r for r in evidence if r["kind"] == "encoder_outcome"]},
              "videos": {}, "files": []}
    for path in directory.glob("*.mp4"):
        probe_cmd = [shutil.which("ffprobe"), "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)]
        probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=180)
        decode_cmd = [shutil.which("ffmpeg"), "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"]
        decode = subprocess.run(decode_cmd, capture_output=True, text=True, timeout=180)
        assert probe.returncode == 0 and decode.returncode == 0, path
        metadata = json.loads(probe.stdout)
        role = next((role for role in cameras if metadata["format"].get("tags", {}).get("cephvr_camera_role") == role), None)
        expected = next(r["encoded_frame_count"] for r in evidence if r["kind"] == "encoder_outcome")
        if role is not None:
            expected = cameras[role]["mapping_rows"]
            assert all(metadata["format"]["tags"]["cephvr_"+key] == str(cameras[role]["identity"][key])
                       for key in ("session_id", "trial_id", "camera_role", "device_id"))
        assert int(metadata["streams"][0]["nb_read_frames"]) == expected, path
        result["videos"][path.name] = {"probe_command": probe_cmd, "probe": metadata,
            "decode_command": decode_cmd, "decode_exit": decode.returncode, "decode_stderr": decode.stderr}
    for path in directory.iterdir():
        if path.is_file():
            result["files"].append({"name": path.name, "bytes": path.stat().st_size,
                                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    results.append(result)
    print(directory.parent.name, trial["outcome"], [(o["output_tag"], o["closure"]) for o in trial["outputs"]],
          "max_gap_ms", result["stimulus"]["cadence"]["max_ms"], flush=True)
    (OUT / "native-assessment.json").write_text(json.dumps(results, indent=2)+"\n")

historical = Path(r"C:\Users\ReiterU_PC\Desktop\20261019_gui_backend_dummy\DUMMY_2-160507\protocol-data")
groups = [r["payload"] for r in jsonl(next(historical.glob("*stimulus_frames.jsonl"))) if r["payload"]["kind"] == "render_group"]
(OUT / "historical-cadence.json").write_text(json.dumps(cadence(groups), indent=2)+"\n")
