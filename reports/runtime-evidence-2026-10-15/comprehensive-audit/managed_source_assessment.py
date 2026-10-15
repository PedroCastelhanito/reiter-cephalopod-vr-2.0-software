"""Streaming source/cadence/linked-state assessment after a completed trial."""

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

parser = argparse.ArgumentParser()
parser.add_argument("run", type=Path)
args = parser.parse_args()
events = json.loads((args.run / "run.json").read_text())["events"]
final = next(row["value"] for row in events if row["name"] == "final")
folder = Path(final["session"]["directory"])
result = dict(session=final["session"], trial=final["trial"], errors=final.get("errors", []), sources={})


def distribution(values):
    return dict(count=len(values), minimum=min(values), mean=statistics.mean(values), median=statistics.median(values), p99=sorted(values)[int((len(values) - 1) * .99)], maximum=max(values)) if values else {}


for path in folder.rglob("*_frames.jsonl"):
    previous_time = previous_id = previous_counter = previous_group = None
    intervals, gaps, bad_ids = [], [], []
    group_gaps = []
    counts = Counter()
    frame_dispositions = Counter()
    video_dispositions = Counter()
    submissions = Counter()
    dropped = invalid = 0
    samples = {}
    endings = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            row = row.get("payload", row)
            kind = row.get("kind", row.get("type"))
            counts[kind] += 1
            if kind == "header":
                header = row
            if kind == "frame":
                frame_dispositions[str(row.get("video_disposition"))] += 1
                dropped += bool(row.get("dropped"))
                invalid += row.get("invalid_code") is not None
                if previous_id is not None and row["frame_id"] != previous_id + 1:
                    bad_ids.append([previous_id, row["frame_id"]])
                previous_id = row["frame_id"]
                counter = row.get("camera_frame_counter")
                if counter is not None and previous_counter is not None and counter != previous_counter + 1:
                    gaps.append([previous_counter, counter])
                previous_counter = counter
                stamp = row["host_receipt_ns"]
            elif kind == "render_group":
                if previous_group is not None and row["group_id"] != previous_group + 1:
                    group_gaps.append([previous_group, row["group_id"]])
                previous_group = row["group_id"]
                for submission in row["submissions"]:
                    submissions[f"{submission['output_id']}:{submission['phase']}"] += 1
                stamp = row["state"]["evaluation_host_ns"]
                epoch = str(row["state"]["epoch_occurrence"])
                sample = dict(group_id=row["group_id"], state=row["state"], submissions=row["submissions"])
                group = samples.setdefault(epoch, dict(first=sample, checkpoints=[]))
                group["last"] = sample
                if not group["checkpoints"] or stamp - group["checkpoints"][-1]["state"]["evaluation_host_ns"] >= 5_000_000_000:
                    group["checkpoints"].append(sample)
            else:
                stamp = None
            if kind == "video_frame":
                video_dispositions[str(row.get("disposition"))] += 1
            if stamp is not None:
                if previous_time is not None:
                    intervals.append((stamp - previous_time) / 1e6)
                previous_time = stamp
            if kind in {"completion", "encoder_outcome"}:
                endings[kind] = row
    result["sources"][str(path.relative_to(folder))] = dict(header=header, record_counts=dict(counts), intervals_ms=distribution(intervals), noncontiguous_source_ids=bad_ids, native_counter_discontinuities=gaps, native_counter_scope="raw discontinuities; interpret only with retained header counter semantics", final_records=endings, runtime_state_samples=samples, render_group_discontinuities=group_gaps, submission_phase_counts=dict(submissions), frame_video_dispositions=dict(frame_dispositions), video_frame_dispositions=dict(video_dispositions), source_records_marked_dropped=dropped, invalid_source_records=invalid)

monitor = [json.loads(row) for row in (args.run / "monitor.jsonl").read_text().splitlines()]
def monitor_summary(monitor):
    processes = {}
    previous = {}
    cpu = []
    for sample in monitor:
        system = sample["system"]
        old = previous.get("system")
        if old and system["valid"] and old["valid"]:
            total = system["kernel_100ns"] + system["user_100ns"] - old["kernel_100ns"] - old["user_100ns"]
            if total > 0:
                cpu.append(100 * (total - system["idle_100ns"] + old["idle_100ns"]) / total)
        previous["system"] = system
        for row in sample["processes"]:
            if "creation_time_100ns" not in row:
                continue
            key = f"{row['pid']}:{row['creation_time_100ns']}:{row.get('image', 'unknown')}"
            summary = processes.setdefault(key, dict(name=row["name"], rss_bytes=[], cpu_one_core_percent=[]))
            if "rss_bytes" in row:
                summary["rss_bytes"].append(row["rss_bytes"])
            old = previous.get(key)
            if old:
                dt = sample["host_monotonic_ns"] - old[0]
                elapsed = row["kernel_time_100ns"] + row["user_time_100ns"] - old[1]["kernel_time_100ns"] - old[1]["user_time_100ns"]
                if dt > 0:
                    summary["cpu_one_core_percent"].append(100 * elapsed * 100 / dt)
            previous[key] = sample["host_monotonic_ns"], row
    return dict(sample_count=len(monitor), overhead_ms=distribution([r["sample_duration_ns"] / 1e6 for r in monitor]), system_cpu_percent=distribution(cpu), processes={key: {name: distribution(value) if isinstance(value, list) else value for name, value in row.items()} for key, row in processes.items()}, gpu_samples=[g for r in monitor for g in r["gpu_samples"]], minimum_free_bytes=min((r["storage"]["free"] for r in monitor), default=None))

start = int(final["trial"]["start_monotonic_ns"])
cutoff = int(final["trial"].get("actual_end_monotonic_ns", final["trial"].get("interruption_issued_monotonic_ns", "0")))
assert cutoff > start
result["monitor_interval_scope"] = "T to actual normal end, or controller interruption issue time; per-source recording cutoffs remain in raw completion records"
active = [row for row in monitor if start <= row["host_monotonic_ns"] < cutoff]
result["monitor_whole_run"] = monitor_summary(monitor)
result["monitor_active_trial"] = monitor_summary(active)
(args.run / "assessment.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(args.run / "assessment.json")
