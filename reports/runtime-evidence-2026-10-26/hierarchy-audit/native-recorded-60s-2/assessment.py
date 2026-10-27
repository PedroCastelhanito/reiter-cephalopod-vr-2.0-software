"""Read retained native evidence and collector output; no runtime or device access."""

import json
import statistics
from collections import Counter
from pathlib import Path

run = Path(__file__).resolve().parent
terminal = json.loads((run / "terminal.json").read_text())
collection = json.loads((run / "collection.json").read_text())
directory = Path(terminal["session"]["directory"])
start = int(terminal["trial"]["start_monotonic_ns"])
cutoff = int(terminal["trial"]["actual_end_monotonic_ns"])
trial_log = next(json.loads(path.read_text()) for path in directory.rglob("*_LOG.json")
                 if not path.name.endswith("_stimulus_LOG.json"))
assert trial_log["complete"] and trial_log["outcome"] == "completed"
assert not collection["errors"] and terminal["session"]["cleanup_confirmed"]
assert cutoff - start == 60_000_000_000
assert all(x["closure"] == "OUTPUT_CLOSURE_CLOSED" and x["artifact_present"]
           for x in trial_log["outputs"])
result = {
    "session_id": terminal["session"]["context"]["session_id"],
    "trial_id": terminal["trial"]["context"]["trial_id"],
    "duration_ns": cutoff - start,
    "closed_artifacts": len(trial_log["outputs"]),
    "cleanup_confirmed": True,
    "cameras": {},
    "stimulus": {},
    "videos": {},
    "unavailable": ["peak capture slots", "readback stage maxima", "queue stage maxima"],
}
for relative, video in collection["videos"].items():
    assert video["ffprobe_exit"] == video["decode_exit"] == 0
    assert not video["ffprobe_error"] and not video["decode_error"]
    stream = next(x for x in video["ffprobe"]["streams"] if x["codec_type"] == "video")
    result["videos"][relative] = {key: stream.get(key) for key in (
        "width", "height", "pix_fmt", "nb_read_frames", "avg_frame_rate", "duration"
    )}
for path in sorted(directory.rglob("*_frames.jsonl")):
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records = [row.get("payload", row) for row in records]
    closing = records[-1]
    assert closing.get("kind", closing.get("type")) == "completion"
    assert closing["outcome"] == "completed"
    video_name = str(path.relative_to(directory)).replace("_frames.jsonl", ".mp4")
    decoded = int(result["videos"][video_name]["nb_read_frames"])
    frames = [row for row in records if row.get("type") == "frame"]
    if frames:
        mappings = [row for row in records if row.get("type") == "video_frame"]
        assert len(frames) == len(mappings) == decoded == closing["video"]["recorded_frame_count"]
        assert closing["timing"]["accounting_complete"] and closing["post_cutoff"]["accounting_complete"]
        assert closing["video"]["duplicate_frame_count"] == 0
        assert closing["video"]["selected_source_frame_count"] == decoded
        assert all(row["frame_id"] == index and not row["invalid_code"] and not row["dropped"]
                   and start <= row["host_receipt_ns"] < cutoff
                   for index, row in enumerate(frames))
        assert all(row["encoded_frame_index"] == index and row["source_frame_id"] == index
                   and row["source_host_receipt_ns"] == frames[index]["host_receipt_ns"]
                   and row["disposition"] == "real" for index, row in enumerate(mappings))
        counters = [row["camera_frame_counter"] for row in frames]
        gaps = [b["host_receipt_ns"] - a["host_receipt_ns"] for a, b in zip(frames, frames[1:])]
        result["cameras"][records[0]["identity"]["camera_role"]] = {
            "source_frames": len(frames), "real_video_frames": len(mappings),
            "decoded_frames": decoded, "source_to_video_exact": True,
            "invalid_images": 0, "dropped_sources": 0, "duplicate_frames": 0,
            "native_counter_first_last": [counters[0], counters[-1]],
            "native_counters_contiguous": all(b == a + 1 for a, b in zip(counters, counters[1:])),
            "first_receipt_after_start_ms": (frames[0]["host_receipt_ns"] - start) / 1e6,
            "last_receipt_before_cutoff_ms": (cutoff - frames[-1]["host_receipt_ns"]) / 1e6,
            "median_receipt_gap_ms": statistics.median(gaps) / 1e6,
            "maximum_receipt_gap_ms": max(gaps) / 1e6,
            "completion": closing,
        }
    else:
        groups = [row for row in records if row.get("kind") == "render_group"]
        encoder = next(row for row in records if row.get("kind") == "encoder_outcome")
        assert encoder["encoded_frame_count"] == encoder["input_submitted_count"] == decoded == len(groups)
        assert encoder["exit_code"] == 0 and encoder["eof_sent"] and encoder["drain_confirmed"]
        assert not any(encoder[key] for key in ("duplicate_frame_count", "same_slot_omission_count", "capacity_drop_count"))
        assert closing["unresolved_attempt_count"] == 0
        stamps = [row["state"]["evaluation_host_ns"] for row in groups]
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        assert all(gap > 0 for gap in gaps)
        assert all(row["group_id"] == index for index, row in enumerate(groups))
        result["stimulus"] = {
            "render_groups": len(groups), "first_evaluation_after_start_ms": (stamps[0] - start) / 1e6,
            "last_evaluation_before_cutoff_ms": (cutoff - stamps[-1]) / 1e6,
            "median_evaluation_gap_ms": statistics.median(gaps) / 1e6,
            "maximum_evaluation_gap_ms": max(gaps) / 1e6,
            "evaluation_gaps_over_25ms": sum(gap > 25_000_000 for gap in gaps),
            "evaluation_gaps_over_50ms": sum(gap > 50_000_000 for gap in gaps),
            "evaluation_gaps_over_25ms_samples": [
                {"previous_group": a["group_id"], "next_group": b["group_id"],
                 "previous_group_after_start_s": (a["state"]["evaluation_host_ns"] - start) / 1e9,
                 "gap_ms": gap / 1e6}
                for a, b, gap in zip(groups, groups[1:], gaps) if gap > 25_000_000
            ],
            "maximum_individual_submission_ms": max(
                submission["return_host_ns"] - submission["entry_host_ns"]
                for row in records for submission in row.get("submissions", [])
                if submission["phase"] == "returned"
            ) / 1e6,
            "capture_observations": dict(Counter(capture["disposition"] for row in records
                for capture in row.get("captures", []))),
            "submission_observations": dict(Counter(submission["phase"] for row in records
                for submission in row.get("submissions", []))),
            "encoder_outcome": encoder, "completion": closing,
        }
result["limits"] = "Blank60s/two-camera current-settings check only. Source counts are received in-interval images, not nominal pulse guarantees. Software evaluation gaps are not optical timing or stall attribution. No Tracking processing or representative-scene/full-load acceptance. Stage/slot metrics are not exported by current runtime."
(run / "assessment.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
