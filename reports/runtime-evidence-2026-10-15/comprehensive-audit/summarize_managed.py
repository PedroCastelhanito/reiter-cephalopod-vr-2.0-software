"""Compact native scientific accounting, retaining the source assessments."""

import json
from pathlib import Path

root = Path(__file__).parent
collection = json.loads((root / "managed-collection-summary.json").read_text())
result = {}
for label, summary in collection["runs"].items():
    assessment = json.loads((root / label / "assessment.json").read_text())
    native_collection = json.loads((root / label / "collection.json").read_text())
    comparisons = {}
    for name, video in native_collection["videos"].items():
        source = assessment["sources"][name.removesuffix(".mp4")+"_frames.jsonl"]
        final = source["final_records"]
        expected = (final["encoder_outcome"]["encoded_frame_count"] if "encoder_outcome" in final else final["completion"]["video"]["recorded_frame_count"])
        decoded = int(video["ffprobe"]["streams"][0]["nb_read_frames"])
        assert decoded == expected, (label, name, decoded, expected)
        comparisons[name] = {"decoded_frames": decoded, "declared_frames": expected, "counts_match": True, "full_decode_exit": video["decode_exit"]}
    sources = {}
    for name, source in assessment.get("sources", {}).items():
        sources[name] = {
            key: source[key]
            for key in (
                "record_counts", "intervals_ms", "noncontiguous_source_ids",
                "native_counter_discontinuities", "final_records",
                "frame_video_dispositions", "video_frame_dispositions",
                "source_records_marked_dropped", "invalid_source_records",
            ) if key in source
        }
    result[label] = {**summary, "video_frame_comparisons": comparisons, "sources": sources, "errors": assessment["errors"]}
aborted = json.loads((root / "managed-boundary-abort60-r1/assessment.json").read_text())["trial"]
reused = json.loads((root / "managed-boundary-reuse60-r1/assessment.json").read_text())["trial"]
boundary = int(aborted["scheduled_end_monotonic_ns"])
result["retired_boundary"] = {
    "original_boundary_ns": boundary,
    "new_trial_start_ns": int(reused["start_monotonic_ns"]),
    "new_trial_end_ns": int(reused["actual_end_monotonic_ns"]),
    "boundary_after_new_start_seconds": (boundary-int(reused["start_monotonic_ns"]))/1e9,
    "new_trial_beyond_boundary_seconds": (int(reused["actual_end_monotonic_ns"])-boundary)/1e9,
}
(root / "managed-accounting-summary.json").write_text(json.dumps(result, indent=2)+"\n")
print(json.dumps(result["retired_boundary"], indent=2))
