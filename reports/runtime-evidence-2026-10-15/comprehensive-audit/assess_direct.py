"""Independent complete decode/count and observed source accounting."""

from concurrent.futures import ThreadPoolExecutor
import argparse
import json
from pathlib import Path
import statistics
import subprocess

import numpy as np
from PIL import Image

root = Path.cwd()
out = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument("--label", action="append")
options = parser.parse_args()
labels = options.label or ("direct-cq23-60-r1", "direct-cq18-60-r1", "direct-native4096-grating20-r1")


def assess(item):
    label, name, data = item
    media = root / ".tmp" / label / f"{name}.mp4"
    probe_command = ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,pix_fmt,avg_frame_rate,nb_read_frames,duration", "-of", "json", str(media)]
    probe = subprocess.run(probe_command, capture_output=True, text=True, timeout=180)
    decode_command = ["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(media), "-map", "0:v:0", "-f", "null", "-"]
    decode = subprocess.run(decode_command, capture_output=True, text=True, timeout=180)
    image_path = out / label / f"{name}-first-decoded.png"
    still_command = ["ffmpeg", "-hide_banner", "-v", "error", "-n", "-i", str(media), "-frames:v", "1", str(image_path)]
    still = subprocess.run(still_command, capture_output=True, text=True, timeout=30)
    stream = json.loads(probe.stdout)["streams"][0] if probe.returncode == 0 else {}
    ids = data.get("frame_ids", [])
    timestamps = data.get("host_ns", data.get("submission_ns", []))
    gaps = [(b-a)/1e6 for a,b in zip(timestamps,timestamps[1:])]
    pixels = np.asarray(Image.open(image_path).convert("RGB")) if still.returncode == 0 else None
    result = {"source_frames": data["frames"], "decoded_frames": int(stream.get("nb_read_frames", -1)), "count_matches": int(stream.get("nb_read_frames", -1)) == data["frames"], "stream": stream, "full_decode_exit": decode.returncode, "full_decode_error": decode.stderr, "probe_exit": probe.returncode, "probe_error": probe.stderr, "probe_command": probe_command, "decode_command": decode_command, "bytes": media.stat().st_size, "receipt_span_s": (timestamps[-1]-timestamps[0])/1e9, "observed_receipt_fps": (len(timestamps)-1)/((timestamps[-1]-timestamps[0])/1e9), "block_id_gaps": sum(b-a-1 for a,b in zip(ids,ids[1:]) if b>a), "block_id_nonincreases": sum(b<=a for a,b in zip(ids,ids[1:])), "failed_grabs": data.get("failed_grabs"), "interval_ms": {"mean": statistics.mean(gaps), "p95": float(np.percentile(gaps,95)), "max": max(gaps)}, "first_frame_mean_8bit": float(pixels.mean()) if pixels is not None else None, "first_frame_std_8bit": float(pixels.std()) if pixels is not None else None, "settings": {k:data[k] for k in ("width","height","actual_hz","pixel_format","exposure_us","renderer") if k in data}, "camera_closed": data.get("camera_closed"), "pfs_exact_restored": data.get("pfs_exact_restored"), "scope": "Observed SDK receipt IDs and direct encoder frames; no managed CFR/source-selection, physical trigger/timing or scene quality equivalence claim"}
    (out / label / f"{name}-assessment.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    assert result["count_matches"] and decode.returncode == probe.returncode == still.returncode == 0
    return label,name,result


items = []
for label in labels:
    data = json.loads((out / label / "summary.json").read_text())
    for name,result in data["sources"].items():
        items.append((label,name,result))
results = {}
with ThreadPoolExecutor(max_workers=3) as pool:
    for label,name,result in pool.map(assess,items):
        results.setdefault(label,{})[name] = result
(out / ("direct-final-assessment.json" if options.label else "direct-assessment.json")).write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
print(json.dumps({label:{name:{k:v for k,v in data.items() if k in ("source_frames","decoded_frames","count_matches","full_decode_exit","observed_receipt_fps","block_id_gaps","bytes","first_frame_mean_8bit","first_frame_std_8bit")} for name,data in sources.items()} for label,sources in results.items()},indent=2))
