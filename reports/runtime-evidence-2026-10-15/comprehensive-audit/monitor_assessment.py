"""Assess only samples inside the observed direct-workload interval."""

import json
import argparse
from pathlib import Path

import numpy as np

out = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument("--label", default="direct-cq23-60-r1")
parser.add_argument("--managed", action="store_true")
options = parser.parse_args()
folder = out / options.label
if options.managed:
    result = json.loads((folder / "assessment.json").read_text())
    begin = int(result["trial"]["start_monotonic_ns"])
    end = int(result["trial"]["actual_end_monotonic_ns"])
else:
    result = json.loads((folder / "summary.json").read_text())
    stamps = result["sources"]["stimulus"]["submission_ns"]
    begin, end = stamps[0], stamps[-1]
rows = [json.loads(line) for line in (folder / "monitor.jsonl").read_text().splitlines()]
rows = [r for r in rows if begin <= r["host_monotonic_ns"] <= end]
cpu = []
for previous,current in zip(rows,rows[1:]):
    a,b = previous["system"],current["system"]
    total = b["kernel_100ns"]+b["user_100ns"]-a["kernel_100ns"]-a["user_100ns"]
    if a["valid"] and b["valid"] and total > 0:
        cpu.append(100*(total-b["idle_100ns"]+a["idle_100ns"])/total)
gpu = {}
for row in rows:
    for sample in row["gpu_samples"]:
        if not begin <= sample["observed_monotonic_ns"] <= end:
            continue
        fields = [v.strip() for v in sample["text"].split(",")]
        if len(fields) != 8:
            continue
        try:
            key = fields[2]
            record = gpu.setdefault(key,{"index":fields[1],"name":fields[3],"utilization_gpu":[],"utilization_encoder":[],"memory_mib":[],"power_w":[]})
            for name,field in zip(("utilization_gpu","utilization_encoder","memory_mib","power_w"),fields[4:]):
                record[name].append(float(field))
        except ValueError:
            pass


def stats(values):
    return {"samples":len(values),"mean":float(np.mean(values)),"p50":float(np.percentile(values,50)),"p95":float(np.percentile(values,95)),"maximum":max(values),"minimum":min(values)} if values else {}


assessment = {"scope":"Active managed trial only; system CPU and device-wide GPU samples, no per-process GPU attribution" if options.managed else "CQ23 direct workload only; original monitor begins after startup, no CQ18 CPU/GPU comparison; system CPU includes unrelated activity", "requested_interval_ns":[begin,end], "sample_interval_ns":[rows[0]["host_monotonic_ns"],rows[-1]["host_monotonic_ns"]],"cpu_percent":stats(cpu),"gpus":{key:{name:stats(values) if isinstance(values,list) else values for name,values in record.items()} for key,record in gpu.items()}}
assessment["monitored_process_rss_bytes"] = stats([sum(p.get("rss_bytes", 0) for p in row["processes"]) for row in rows])
assessment["memory_scope"] = "Sum of monitored Python/CephVR/FFmpeg/nvidia-smi working sets, including monitor; not system used RAM or deduplicated shared pages"
assessment["disk_free_bytes"] = {"first": rows[0]["storage"]["free"], "last": rows[-1]["storage"]["free"], "minimum": min(row["storage"]["free"] for row in rows)}
io = {}
for row in rows:
    for process in row["processes"]:
        key = (process["pid"], process.get("creation_time_100ns"), process.get("image"))
        values = io.setdefault(key, {"first": process, "last": process})
        values["last"] = process
assessment["monitored_process_io_bytes"] = {
    name: sum(max(0, pair["last"].get(name, 0)-pair["first"].get(name, 0)) for pair in io.values())
    for name in ("read_bytes", "write_bytes", "other_bytes")
}
assessment["io_scope"] = "Identity-fenced process IO counter deltas over sampled interval; not physical disk throughput"
(folder / "resource-assessment.json").write_text(json.dumps(assessment,indent=2)+"\n",encoding="utf-8")
print(json.dumps(assessment,indent=2))
