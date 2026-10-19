"""Read-only audit of the four retained Desktop sessions; writes assessment here."""

import collections
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(r"C:\Users\ReiterU_PC\Desktop\20261019_gui_backend_dummy")
DEST = Path(__file__).parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


results = []
for session in sorted(ROOT.iterdir()):
    directory = session / "protocol-data"
    if not (directory / "SESSION_CONFIG.json").exists():
        continue
    before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in session.rglob("*") if p.is_file()}
    config = read(directory / "SESSION_CONFIG.json")
    trial_path = next(p for p in directory.glob("*_LOG.json") if not p.name.endswith("stimulus_LOG.json"))
    trial = read(trial_path)
    events = [json.loads(line) for line in (directory / "SESSION_LOG.jsonl").open()]
    start = next(e["monotonic_ns"] for e in events if e["event_type"] == "trial_started")
    abort = next(e["monotonic_ns"] for e in events if e.get("details", {}).get("command") == "AbortNow")
    end = next(e["monotonic_ns"] for e in events if e["event_type"] == "session_ended")
    result = {"session": session.name, "trial_outcome": trial["outcome"], "trial_complete": trial["complete"],
              "duration_to_abort_s": (abort-start)/1e9, "abort_to_session_end_s": (end-abort)/1e9,
              "files": [], "outputs": trial["outputs"], "cameras": {}, "videos": {}}
    for path in before:
        if path.suffix in {".json", ".jsonl"}:
            raw = path.read_bytes()
            if path.suffix == ".json":
                json.loads(raw)
            else:
                assert raw.endswith(b"\n"), path
                for line in raw.splitlines():
                    json.loads(line)
        result["files"].append({"path": str(path), "bytes": before[path][0], "sha256": digest(path)})
    result["missing_planned_outputs"] = [o["path"] for o in trial["outputs"] if not Path(o["path"]).is_file()]
    assert {o["output_key"] for o in config["outputs"]} == {o["output_key"] for o in trial["outputs"]}
    for path in directory.glob("*cam_frames.jsonl"):
        rows = [json.loads(line) for line in path.open()]
        header, completion = rows[0], rows[-1]
        assert header["type"] == "header" and completion["type"] == "completion"
        assert header["identity"]["session_id"] == config["session_id"]
        assert header["identity"]["trial_id"] == trial["trial_id"]
        frames = [r for r in rows if r["type"] == "frame"]
        mappings = [r for r in rows if r["type"] == "video_frame"]
        assert [r["frame_id"] for r in frames] == list(range(len(frames)))
        assert len(frames) == completion["timing"]["final_received_frame_count"]
        assert len(mappings) == completion["video"]["recorded_frame_count"]
        assert [r["encoded_frame_index"] for r in mappings] == list(range(len(mappings)))
        by_id = {r["frame_id"]: r for r in frames}
        assert all(m["source_host_receipt_ns"] == by_id[m["source_frame_id"]]["host_receipt_ns"] for m in mappings)
        counters = [r["camera_frame_counter"] for r in frames]
        result["cameras"][header["identity"]["camera_role"]] = {
            "source_rows": len(frames), "mapping_rows": len(mappings), "video_enabled": header["video"]["enabled"],
            "dropped_rows": sum(r["dropped"] for r in frames), "invalid_rows": sum(r["invalid_code"] is not None for r in frames),
            "native_counter_nonunit_steps": sum(b-a != 1 for a,b in zip(counters,counters[1:]) if a is not None and b is not None),
            "completion": completion}
    path = next(directory.glob("*stimulus_frames.jsonl"))
    evidence = [json.loads(line)["payload"] for line in path.open()]
    header = evidence[0]
    recipe_path = directory / header["recipe"]["relative_path"]
    recipe = read(recipe_path)
    assert digest(recipe_path) == header["recipe"]["sha256"]
    assert recipe_path.stat().st_size == header["recipe"]["byte_length"]
    groups = [r for r in evidence if r["kind"] == "render_group"]
    assert [r["group_id"] for r in groups] == list(range(len(groups)))
    assert evidence[-1]["kind"] == "completion" and len(groups) == evidence[-1]["state_count"]
    times = [r["state"]["evaluation_host_ns"] for r in groups]
    gaps = [(b-a)/1e6 for a,b in zip(times,times[1:])]
    assets = []
    for resource in recipe["manifest"]["resources"]:
        fp = resource["fingerprint"]
        asset = Path(config["configuration"]["asset_root"]) / fp["logical_path"]
        assets.append({"resource_id": fp["resource_id"], "path": str(asset), "exists": asset.is_file(),
                       "hash_matches": asset.is_file() and digest(asset) == fp["sha256"]})
    result["stimulus"] = {"record_types": dict(collections.Counter(r["kind"] for r in evidence)),
        "completion": evidence[-1], "encoder": [r for r in evidence if r["kind"] == "encoder_outcome"],
        "max_group_gap_ms": max(gaps), "group_gaps_over_25ms": sum(g > 25 for g in gaps),
        "submission_failures": sum(s["failure_code"] is not None for r in groups for s in r["submissions"]),
        "assets": assets, "photometric_mode": recipe["display"]["photometric_mode"],
        "layout_version": recipe["review_encoding"].get("layout_version", 1)}
    for video in directory.glob("*.mp4"):
        probe_cmd = [shutil.which("ffprobe"), "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(video)]
        probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=180)
        decode_cmd = [shutil.which("ffmpeg"), "-v", "error", "-xerror", "-i", str(video), "-map", "0:v:0", "-f", "null", "-"]
        decode = subprocess.run(decode_cmd, capture_output=True, text=True, timeout=180)
        result["videos"][video.name] = {"probe_command": probe_cmd, "probe_exit": probe.returncode,
            "probe_stderr": probe.stderr, "probe": json.loads(probe.stdout) if probe.returncode == 0 else None,
            "decode_command": decode_cmd, "decode_exit": decode.returncode, "decode_stderr": decode.stderr}
        assert probe.returncode == 0 and decode.returncode == 0, video
        actual = int(json.loads(probe.stdout)["streams"][0]["nb_read_frames"])
        expected = len(groups) if video.name.endswith("stimulus.mp4") else result["cameras"]["behavioral"]["mapping_rows"]
        assert actual == expected, (video, actual, expected)
        if video.name.endswith("behavioral_cam.mp4"):
            frame_log = video.with_name(video.stem + "_frames.jsonl")
            with frame_log.open() as stream:
                identity = json.loads(stream.readline())["identity"]
            tags = json.loads(probe.stdout)["format"]["tags"]
            checks = {key: tags.get("cephvr_" + key) == str(identity[key])
                      for key in ("session_id", "trial_id", "camera_role", "device_id")}
            checks["identity_version"] = tags.get("cephvr_identity_version") == str(identity["recording_identity_version"])
            assert all(checks.values()), video
            result["videos"][video.name]["identity_checks"] = checks
    result["source_files_unchanged_during_audit"] = all(p.exists() and (p.stat().st_size,p.stat().st_mtime_ns) == stamp for p,stamp in before.items())
    assert result["source_files_unchanged_during_audit"]
    results.append(result)
    print(session.name, "OK", result["duration_to_abort_s"], result["stimulus"]["max_group_gap_ms"], flush=True)

assessment = {"date": "2026-10-19", "source_revision": "5945f1708240929406f40c4def98dbcf50ff7947",
              "provenance_limit": "Dirty concurrent checkout; recorded runtime source revision unknown. File fingerprints identify inspected artifacts.",
              "scope": "Four retained Desktop open-loop Abort sessions; read-only JSON, file identities, mappings, recipe/resource hashes, ffprobe frame count and full ffmpeg decode. No hardware or optical/electrical execution.",
              "sessions": results}
(DEST / "assessment.json").write_text(json.dumps(assessment, indent=2)+"\n", encoding="utf-8")
