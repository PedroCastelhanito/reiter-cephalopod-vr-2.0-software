"""Current sequential source-to-video accounting and independent media decode."""
import json
from pathlib import Path
import subprocess

import numpy as np

out=Path(__file__).parent
labels=("saved-p4-baseline60-r1","p1-diagnostic60-r1","abort-cleanup-diagnostic-r1","repaired-p4-3slots60-r2","repaired-p4-16slots60-r1","managed-rgb-gray-lossless60-r5","managed-save-off60-r1","managed-save-on-abort-r1","full-review-overload60-r1")
results={}
for label in labels:
    run=json.loads((out/label/"run.json").read_text(encoding="utf-8"))
    final=next(e["value"] for e in reversed(run["events"]) if e["name"] in {"final","failure_snapshot"})
    root=Path(final["session"]["directory"])/"protocol-data"
    row=results[label]={"generation":run["generation"],"session":final["session"],"trial":final.get("trial",{}),"directory":str(root),"videos":{},"camera_evidence":{},"stimulus_evidence":{}}
    for path in root.glob("*cam_frames.jsonl"):
        metadata={"path":str(path),"source_frames":0,"source_drop_flags":0,"invalid_images":0,"native_counter_gap_count":0,"video_records":0,"mapping_contiguous":True,"mapping_sources_unique":True,"headers":[],"completion":None}
        source_ids=set();video_sources=set();previous_counter=None;first_time=last_time=None
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                record=json.loads(line)
                if record["type"]=="header":metadata["headers"].append(record)
                elif record["type"]=="frame":
                    metadata["source_frames"]+=1
                    metadata["source_drop_flags"]+=bool(record.get("dropped"))
                    metadata["invalid_images"]+=bool(record.get("invalid_code"))
                    source_ids.add(record["frame_id"])
                    stamp=record["host_receipt_ns"]
                    first_time=stamp if first_time is None else first_time;last_time=stamp
                    counter=record.get("camera_frame_counter")
                    if counter is not None and previous_counter is not None and counter>previous_counter+1:metadata["native_counter_gap_count"]+=counter-previous_counter-1
                    if counter is not None:previous_counter=counter
                elif record["type"]=="video_frame":
                    metadata["mapping_contiguous"] &= record["encoded_frame_index"]==metadata["video_records"]
                    metadata["mapping_sources_unique"] &= record["source_frame_id"] not in video_sources
                    video_sources.add(record["source_frame_id"])
                    metadata["video_records"]+=1
                elif record["type"]=="completion":metadata["completion"]=record
        metadata["mapping_sources_present"]=video_sources.issubset(source_ids)
        metadata["received_span_ns"]=last_time-first_time if first_time is not None else None
        metadata["received_cadence_fps"]=(metadata["source_frames"]-1)/((last_time-first_time)/1e9) if last_time and last_time>first_time else None
        row["camera_evidence"][path.name]=metadata
    for path in root.glob("*stimulus_frames.jsonl"):
        metadata={"path":str(path),"groups":0,"input_submissions":0,"capacity_drop_groups":[],"mapping_contiguous":True,"mapping_sources_unique":True,"encoder_outcome":None,"completion":None}
        seen=set();times={}
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                record=json.loads(line)["payload"];kind=record["kind"];group=record.get("group_id")
                if kind=="header":metadata["header"]=record
                elif kind=="render_group":metadata["groups"]+=1;times[group]=record["state"]["evaluation_host_ns"]
                elif kind=="encoder_outcome":metadata["encoder_outcome"]=record
                elif kind=="completion":metadata["completion"]=record
                for capture in record.get("captures",[]):
                    if capture["disposition"]=="input_submitted":
                        metadata["mapping_contiguous"] &= capture["video_frame_index"]==metadata["input_submissions"]
                        metadata["mapping_sources_unique"] &= group not in seen
                        seen.add(group);metadata["input_submissions"]+=1
                    elif capture["disposition"]=="capacity_drop":metadata["capacity_drop_groups"].append(group)
        start=int(final.get("trial",{}).get("start_monotonic_ns",0))
        metadata["capacity_drop_seconds_from_start"]=[(times[g]-start)/1e9 for g in metadata["capacity_drop_groups"]]
        intervals=np.diff(list(times.values()))
        metadata["render_group_intervals_ns"]={"count":len(intervals),"mean":float(np.mean(intervals)),"p50":float(np.percentile(intervals,50)),"p95":float(np.percentile(intervals,95)),"max":int(max(intervals))} if len(intervals) else None
        row["stimulus_evidence"]=metadata
    for path in sorted(root.glob("*.mp4")):
        probe_command=["ffprobe","-v","error","-count_frames","-show_streams","-of","json",str(path)]
        probe=subprocess.run(probe_command,capture_output=True,timeout=90)
        video={"bytes":path.stat().st_size,"probe_command":probe_command,"probe_exit":probe.returncode,"probe":json.loads(probe.stdout),"probe_stderr":probe.stderr.decode(errors="replace")}
        decoded=subprocess.run(["ffmpeg","-hide_banner","-v","error","-threads","2","-i",str(path),"-f","null","-"],capture_output=True,timeout=120)
        video.update(decode_exit=decoded.returncode,decode_stderr=decoded.stderr.decode(errors="replace"))
        evidence=row["stimulus_evidence"] if path.name.endswith("_stimulus.mp4") else row["camera_evidence"][path.stem+"_frames.jsonl"]
        expected=evidence["input_submissions"] if path.name.endswith("_stimulus.mp4") else evidence["video_records"]
        video["expected_retained_count"]=expected
        video["count_matches"]=int(video["probe"]["streams"][0]["nb_read_frames"])==expected
        row["videos"][path.name]=video
        (out/"managed-assessment.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
    row["scientific_files"]=[path.name for path in root.iterdir() if path.suffix in {".json",".jsonl"}]
    if label=="managed-save-off60-r1":
        assert not row["videos"] and len(row["camera_evidence"])==2 and row["stimulus_evidence"]["completion"]
    print(label,len(row["videos"]),"videos;",final["session"].get("outcome"),"cleanup",final["session"].get("cleanup_confirmed",False),flush=True)
(out/"managed-assessment.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
assert all(v["decode_exit"]==0 and v["count_matches"] for r in results.values() for v in r["videos"].values())
assert all(m["mapping_contiguous"] and m["mapping_sources_unique"] and m["mapping_sources_present"] for r in results.values() for m in r["camera_evidence"].values())
assert all(r["stimulus_evidence"]["mapping_contiguous"] and r["stimulus_evidence"]["mapping_sources_unique"] for r in results.values())
