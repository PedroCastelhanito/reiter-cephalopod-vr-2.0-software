"""Active-trial-only aggregate resource samples; device-wide GPU, not per-process."""
import csv
import json
from pathlib import Path

import numpy as np

out=Path(__file__).parent
labels=("saved-p4-baseline60-r1","p1-diagnostic60-r1","repaired-p4-3slots60-r2","repaired-p4-16slots60-r1","managed-rgb-gray-lossless60-r5","full-review-overload60-r1")

def summary(values):
    return {"count":len(values),"mean":float(np.mean(values)),"p50":float(np.percentile(values,50)),"p95":float(np.percentile(values,95)),"max":float(max(values))} if values else None

result={"scope":"Only active trial timestamps; GPU utilization is device-wide sampled ~1Hz. RSS sums double-count shared pages. Process I/O includes pipes and is not physical disk throughput. CPU uses cumulative Windows counters; no per-stage CPU/GPU attribution.","runs":{}}
for label in labels:
    run=json.loads((out/label/"run.json").read_text(encoding="utf-8"))
    final=next(e["value"] for e in run["events"] if e["name"]=="final")
    start=int(final["trial"]["start_monotonic_ns"])
    end=int(final["trial"]["scheduled_end_monotonic_ns"])
    samples=[json.loads(line) for line in (out/label/"monitor.jsonl").open(encoding="utf-8")]
    active=[s for s in samples if start<=s["host_monotonic_ns"]<=end]
    cpu=[];process_cpu=[];rss=[];io=[];gpu={}
    for sample in active:
        rss.append(sum(p["rss_bytes"] for p in sample["processes"]))
    for a,b in zip(samples,samples[1:]):
        if not(start<=a["host_monotonic_ns"]<b["host_monotonic_ns"]<=end):continue
        sa,sb=a["system"],b["system"]
        total=(sb["kernel_100ns"]+sb["user_100ns"])-(sa["kernel_100ns"]+sa["user_100ns"])
        idle=sb["idle_100ns"]-sa["idle_100ns"]
        if total>0:cpu.append(100*(total-idle)/total)
        prior={(p["pid"],p["creation_time_100ns"]):p for p in a["processes"]}
        process_ticks=sum(max(0,p["kernel_time_100ns"]+p["user_time_100ns"]-prior[(p["pid"],p["creation_time_100ns"])]["kernel_time_100ns"]-prior[(p["pid"],p["creation_time_100ns"])]["user_time_100ns"]) for p in b["processes"] if (p["pid"],p["creation_time_100ns"]) in prior)
        process_cpu.append(100*process_ticks/((b["host_monotonic_ns"]-a["host_monotonic_ns"])/100)/b["cpu_count"])
        delta=sum(max(0,p["write_bytes"]-prior[(p["pid"],p["creation_time_100ns"])]["write_bytes"]) for p in b["processes"] if (p["pid"],p["creation_time_100ns"]) in prior)
        io.append(delta/((b["host_monotonic_ns"]-a["host_monotonic_ns"])/1e9))
    for sample in samples:
        for observation in sample["gpu_samples"]:
            if not start<=observation["observed_monotonic_ns"]<=end:continue
            fields=next(csv.reader([observation["text"]],skipinitialspace=True))
            _,index,uuid,name,util,encoder,memory,power=fields
            target=gpu.setdefault(uuid,{"index":index,"name":name,"utilization_percent":[],"encoder_percent":[],"memory_MiB":[],"power_W":[]})
            for key,value in (("utilization_percent",util),("encoder_percent",encoder),("memory_MiB",memory),("power_W",power)):
                try:target[key].append(float(value))
                except ValueError:pass
    for target in gpu.values():
        for key in ("utilization_percent","encoder_percent","memory_MiB","power_W"):target[key]=summary(target[key])
    result["runs"][label]={"start_monotonic_ns":start,"end_monotonic_ns":end,"active_monitor_samples":len(active),"system_cpu_percent":summary(cpu),"observed_process_cpu_percent_of_machine":summary(process_cpu),"sum_process_working_set_bytes":summary(rss),"process_io_write_bytes_per_second_including_pipes":summary(io),"gpu":gpu}
(out/"resource-assessment.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,indent=2))
