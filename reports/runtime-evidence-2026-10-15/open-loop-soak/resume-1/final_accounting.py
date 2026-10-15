"""Compact evidence index; durations normalize sizes, not scene complexity."""
import json
from pathlib import Path

out = Path(__file__).parent
result = {"scope": "Observed baseline900 versus camera-lossless60; different scene duration and time, not a controlled bitrate comparison", "runs": {}}
for label, seconds in (("combined900-final-r1", 900), ("lossless60-r1", 60)):
    run = out / label
    collection = json.loads((run / "collection.json").read_text())
    assert collection["collection_complete"] and not collection["errors"]
    assessment = json.loads((run / "assessment.json").read_text())
    rows = {}
    for name, value in assessment["sources"].items():
        rows[name] = dict(completion=value["final_records"], dispositions=value["frame_video_dispositions"],
                          source_id_gaps=value["noncontiguous_source_ids"], native_counter_gaps=value["native_counter_discontinuities"],
                          invalid=value["invalid_source_records"], submissions=value["submission_phase_counts"],
                          render_group_gaps=value["render_group_discontinuities"])
    result["runs"][label] = dict(seconds=seconds, sources=rows,
        videos={name: dict(bytes=value["size_bytes"], bytes_per_second=value["size_bytes"] / seconds,
                          mbps=value["size_bytes"] * 8 / seconds / 1e6, gib_per_hour=value["size_bytes"] / seconds * 3600 / 2**30,
                          frames=value["ffprobe"]["streams"][0]["nb_read_frames"], probe_exit=value["ffprobe_exit"], decode_exit=value["decode_exit"])
                for name, value in collection["videos"].items()},
        active_cpu=assessment["monitor_active_trial"]["system_cpu_percent"],
        monitor_analysis=str(run / "monitor-analysis.json"))
(out / "final-accounting.json").write_text(json.dumps(result, indent=2))
print(json.dumps({key: {"videos": value["videos"], "active_cpu": value["active_cpu"]} for key, value in result["runs"].items()}))
