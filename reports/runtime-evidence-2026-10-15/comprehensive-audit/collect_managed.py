"""Read-only postclosure managed output count/decode/source evidence collection."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("labels",nargs="+")
args = parser.parse_args()
root = Path.cwd()
out = Path(__file__).parent
spec = importlib.util.spec_from_file_location("audit_encoding_probe",root/"tools/encoding_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
source_path = root/"reports/runtime-evidence-2026-10-15/open-loop-soak/resume-1/assess.py"
source = source_path.read_text()
assert source.count('row["label"]') == 1
adapted = source.replace('row["label"]','row["name"]')
assessment_script = out/"managed_source_assessment.py"
assert not assessment_script.exists() or assessment_script.read_text() == adapted
assessment_script.write_text(adapted,encoding="utf-8")
summary = {"assessment_source":str(source_path),"source_sha256":hashlib.sha256(source.encode()).hexdigest(),"adaptation":"Only event index key label→name; same source/CFR/cadence/CPU/GPU assessment", "runs":{}}
existing_summary = out / "managed-collection-summary.json"
if existing_summary.exists():
    existing = json.loads(existing_summary.read_text())
    assert existing["source_sha256"] == summary["source_sha256"]
    summary["runs"].update(existing["runs"])
for label in args.labels:
    folder = out/label
    events = json.loads((folder/"run.json").read_text())["events"]
    final = next(e["value"] for e in events if e["name"]=="final")
    assert final["session"]["cleanup_confirmed"]
    recording = Path(final["session"]["directory"])
    videos = sorted(recording.rglob("*.mp4"))
    expected = 0 if "off" in label else 3
    assert len(videos) == expected,(label,len(videos))
    result = {"session":final["session"],"trial":final["trial"],"errors":final.get("errors",[]),"videos":{},"frame_logs":{},"files":[]}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for path,value in zip(videos,pool.map(lambda p:probe.probe_video(p,180),videos)):
            result["videos"][str(path.relative_to(recording))] = value
            assert not any(value.get(key) for key in ("ffprobe_exit","decode_exit","ffprobe_error","decode_error")),value
    for path in sorted(recording.rglob("*_frames.jsonl")):
        result["frame_logs"][str(path.relative_to(recording))] = probe.frame_log(path)
    for path in sorted(recording.rglob("*")):
        if path.is_file():
            result["files"].append({"path":str(path.relative_to(recording)),"bytes":path.stat().st_size})
    with (folder/"source-assessment.log").open("w") as log:
        subprocess.run([sys.executable,str(assessment_script),str(folder)],stdout=log,stderr=subprocess.STDOUT,timeout=90,check=True)
    (folder/"collection.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    summary["runs"][label] = {"outcome":final["trial"]["outcome"],"cleanup_confirmed":True,"video_count":len(videos),"all_count_decode_commands_passed":True,"recording_directory":str(recording)}
(out/"managed-collection-summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
print(json.dumps(summary,indent=2))
