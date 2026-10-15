"""Summarize retained monitor evidence inside actual trial boundaries."""

import argparse
import csv
import json
from pathlib import Path
import statistics

parser = argparse.ArgumentParser()
parser.add_argument("run", type=Path)
args = parser.parse_args()
events = json.loads((args.run / "run.json").read_text())["events"]
final = next(row["value"] for row in events if row["label"] == "final")
start, end = (int(final["trial"][key]) for key in ("start_monotonic_ns", "actual_end_monotonic_ns"))
samples = [json.loads(line) for line in (args.run / "monitor.jsonl").read_text().splitlines()]
samples = [row for row in samples if start <= row["host_monotonic_ns"] < end]


def summary(values):
    return dict(count=len(values), minimum=min(values), mean=statistics.mean(values),
                maximum=max(values), first=values[0], last=values[-1]) if values else {}


gpus, processes = {}, {}
for sample in samples:
    for observed in sample["gpu_samples"]:
        if not start <= observed["observed_monotonic_ns"] < end:
            continue
        fields = next(csv.reader([observed["text"]], skipinitialspace=True))
        if len(fields) != 8:
            continue
        uuid = fields[2]
        group = gpus.setdefault(uuid, dict(name=fields[3], epochs={}))
        epoch = str(int((observed["observed_monotonic_ns"] - start) // 300_000_000_000))
        metrics = group["epochs"].setdefault(epoch, {})
        for index, name in ((4, "gpu_percent"), (5, "encoder_percent"), (6, "memory_mib"), (7, "power_w")):
            try:
                metrics.setdefault(name, []).append(float(fields[index]))
            except ValueError:
                pass
    for process in sample["processes"]:
        if "creation_time_100ns" not in process:
            continue
        key = f"{process['pid']}:{process['creation_time_100ns']}"
        group = processes.setdefault(key, dict(image=process.get("image"), name=process["name"], rss=[]))
        if "rss_bytes" in process:
            group["rss"].append(process["rss_bytes"])
result = dict(scope="Actual active trial only; GPU sampled1s; RSS growth is observed variation, not a leak diagnosis; processIO retained raw, physicaldiskthroughput unavailable",
              start_ns=start, end_ns=end, sample_count=len(samples),
              gpus={uuid: dict(name=value["name"], epochs={epoch: {name: summary(values) for name, values in metrics.items()} for epoch, metrics in value["epochs"].items()}) for uuid, value in gpus.items()},
              processes={key: dict(image=value["image"], name=value["name"], rss_bytes=summary(value["rss"])) for key, value in processes.items()},
              free_bytes=summary([sample["storage"]["free"] for sample in samples]),
              sampling_ms=summary([sample["sample_duration_ns"] / 1e6 for sample in samples]))
(args.run / "monitor-analysis.json").write_text(json.dumps(result, indent=2))
print(args.run / "monitor-analysis.json")
