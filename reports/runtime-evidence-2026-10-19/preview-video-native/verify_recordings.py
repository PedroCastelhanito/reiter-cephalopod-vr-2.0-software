"""Decode every video and compare native receipts and frame accounting."""
import json
import subprocess
import sys
from pathlib import Path

root, output = Path(sys.argv[1]), Path(sys.argv[2])
trial = next(p for p in root.glob("*_LOG.json") if not p.name.endswith("stimulus_LOG.json"))
log = json.loads(trial.read_text())
result = {"method": "ffprobe full-frame decode/count and JSONL accounting", "trial": str(trial), "complete": log["complete"], "outcome": log["outcome"], "videos": []}
for receipt in log["outputs"]:
    if receipt["extension"] != "mp4":
        continue
    path = Path(receipt["path"])
    command = ["ffprobe", "-v", "error", "-threads", "2", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=codec_name,width,height,nb_read_frames,duration", "-of", "json", str(path)]
    probe = subprocess.run(command, capture_output=True, text=True)
    data = json.loads(probe.stdout)
    decoded = int(data["streams"][0]["nb_read_frames"])
    rows = [json.loads(line) for line in path.with_name(path.stem + "_frames.jsonl").open()]
    completion = rows[-1].get("payload", rows[-1])
    camera = receipt["output_tag"] != "stimulus"
    frame_rows = [r for r in rows if r.get("type") == "frame"]
    counters = [r["camera_frame_counter"] for r in frame_rows if r.get("camera_frame_counter") is not None]
    item = {"path": str(path), "command": command, "returncode": probe.returncode, "stderr": probe.stderr, "probe": data, "receipt": receipt, "completion": completion, "decoded_matches_receipt": decoded == receipt["counts"]["frames"]}
    if camera:
        item.update(native_counter_gaps=sum(b != a + 1 for a,b in zip(counters,counters[1:])), dropped_source_frames=sum(bool(r.get("dropped")) for r in frame_rows), recorded_matches_received=completion["video"]["recorded_frame_count"] == completion["timing"]["final_received_frame_count"])
    result["videos"].append(item)
    output.write_text(json.dumps(result, indent=2))
    print(path.name, decoded, "matches", item["decoded_matches_receipt"], "errors", bool(probe.stderr), flush=True)
