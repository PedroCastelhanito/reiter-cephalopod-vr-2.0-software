"""Stream completed scientific records; no device or runtime interaction."""
import collections
import json
import sys
from pathlib import Path

results = []
for root in sys.argv[1:]:
    for path in Path(root).rglob("*_stimulus_frames.jsonl"):
        count = mismatches = images = 0
        previous = None
        intervals = []
        captures = collections.Counter()
        failures = collections.Counter()
        per_output = {}
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)["payload"]
                if record["kind"] != "render_group":
                    continue
                count += 1
                state = record["state"]
                now = state["evaluation_host_ns"]
                if previous is not None:
                    assert now >= previous
                    intervals.append(now - previous)
                previous = now
                for image in state["images"]:
                    images += 1
                    mismatches += (image["requested_asset_id"], image["requested_image_index"]) != (image["asset_id"], image["image_index"])
                for capture in record["captures"]:
                    captures[capture["disposition"]] += 1
                for submission in record["submissions"]:
                    if submission["failure_code"]:
                        failures[submission["failure_code"]] += 1
                    entry = submission.get("entry_host_ns")
                    if entry is None:
                        continue
                    output = per_output.setdefault(submission["output_id"], {"previous": None, "maximum_interval_ns": 0, "over_100ms": 0})
                    if output["previous"] is not None:
                        interval = entry - output["previous"]
                        output["maximum_interval_ns"] = max(output["maximum_interval_ns"], interval)
                        output["over_100ms"] += interval > 100_000_000
                    output["previous"] = entry
        for output in per_output.values():
            del output["previous"]
        results.append({"path": str(path), "render_groups": count, "image_bindings": images,
                        "requested_actual_mismatches": mismatches, "captures": captures, "submission_failures": failures,
                        "maximum_state_interval_ns": max(intervals, default=0),
                        "state_intervals_over_100ms": sum(x > 100_000_000 for x in intervals), "outputs": per_output})
assert results, "No scientific stimulus records found"
print(json.dumps(results, indent=2))
