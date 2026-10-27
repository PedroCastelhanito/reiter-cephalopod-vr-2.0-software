"""Read-only two-trial continuity and encoded/source identity assessment."""
import json
import sys
from pathlib import Path

run = Path(sys.argv[1]).resolve()
terminal = json.loads((run / "terminal.json").read_text(encoding="utf-8"))
collection = json.loads((run / "collection.json").read_text(encoding="utf-8"))
assert terminal["session"]["cleanup_confirmed"] and not collection["errors"]
directory = Path(terminal["session"]["directory"])
logs = [json.loads(p.read_text(encoding="utf-8")) for p in directory.rglob("*_LOG.json") if not p.name.endswith("_stimulus_LOG.json")]
assert len(logs) == 2
assert all(log["complete"] and log["outcome"] == "completed" for log in logs)
assert all(item["closure"] == "OUTPUT_CLOSURE_CLOSED" and item["artifact_present"] for log in logs for item in log["outputs"])
result = {"session_id": terminal["session"]["context"]["session_id"], "closed_artifacts": sum(len(log["outputs"]) for log in logs), "cameras": {}, "videos": {}, "physical_pulse_alignment": "unknown; no hardware anchor measured"}
for name, video in collection["videos"].items():
    assert video["ffprobe_exit"] == video["decode_exit"] == 0
    assert not video["ffprobe_error"] and not video["decode_error"]
    result["videos"][name] = int(next(s for s in video["ffprobe"]["streams"] if s["codec_type"] == "video")["nb_read_frames"])
for path in sorted(directory.rglob("*_frames.jsonl")):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if rows[0].get("type") != "header":
        continue
    header, end = rows[0], rows[-1]
    assert header["schema_version"] == 6 and end["type"] == "completion" and end["outcome"] == "completed"
    start = header["clocks"]["trial_start_monotonic_ns"]
    cutoff = end["timing"]["recording_end_monotonic_ns"]
    assert cutoff - start == 60_000_000_000
    frames = [r for r in rows if r.get("type") == "frame"]
    mappings = [r for r in rows if r.get("type") == "video_frame"]
    name = str(path.relative_to(directory)).replace("_frames.jsonl", ".mp4")
    assert len(frames) == len(mappings) == result["videos"][name] == end["video"]["recorded_frame_count"]
    assert all(f["frame_id"] == i and start <= f["host_receipt_ns"] < cutoff and not f["invalid_code"] and not f["dropped"] for i,f in enumerate(frames))
    assert all(m["encoded_frame_index"] == i and m["source_frame_id"] == i and m["source_host_receipt_ns"] == frames[i]["host_receipt_ns"] for i,m in enumerate(mappings))
    assert end["post_cutoff"]["scope"] == "admission_snapshot"
    assert end["boundary_context"]["absolute_pulse_offset"] is None
    counters = [f["camera_frame_counter"] for f in frames]
    entry = {"trial_number":header["identity"]["trial_number"],"capture_generation":header["identity"]["capture_generation"],"frame_count":len(frames),"native_first":counters[0],"native_last":counters[-1],"native_contiguous":all(b==a+1 for a,b in zip(counters,counters[1:])),"boundary_context":end["boundary_context"],"first_receipt_after_start_ns":frames[0]["host_receipt_ns"]-start,"completion":end}
    result["cameras"].setdefault(header["identity"]["camera_role"],[]).append(entry)
assert len(result["cameras"]) == 2 and len(result["videos"]) == 6
for trials in result["cameras"].values():
    trials.sort(key=lambda t:t["trial_number"])
    assert [t["trial_number"] for t in trials] == [1,2]
    assert trials[0]["capture_generation"] == trials[1]["capture_generation"]
    assert trials[1]["native_first"] > trials[0]["native_last"] + 1
(run / "assessment.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"closed_artifacts":result["closed_artifacts"],"decoded_videos":len(result["videos"]),"cameras":{role:[{k:t[k] for k in ("trial_number","frame_count","native_first","native_last","native_contiguous")} for t in trials] for role,trials in result["cameras"].items()}},indent=2))
