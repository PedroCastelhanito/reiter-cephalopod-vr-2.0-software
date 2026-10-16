"""Bounded deterministic pixel fidelity probes, separate from managed acceptance."""

import hashlib
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np

from cephvr.platform.windows.nvidia_device import resolve_cuda_ordinal

parser = argparse.ArgumentParser()
parser.add_argument("--label", default="pixel-roundtrip")
options = parser.parse_args()
out = Path(__file__).parent / options.label
out.mkdir(exist_ok=False)
assert shutil.disk_usage(out).free > 2_000_000_000
device = resolve_cuda_ordinal("GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc")
width = height = 256
count = 12
rng = np.random.default_rng(20261016)
rgb = rng.integers(0, 256, (count, height, width, 3), dtype=np.uint8)
rgb[:, :32, :, :] = np.arange(width, dtype=np.uint8)[None, None, :, None]
rgb[2] = rgb[1]  # Real repeated content must remain a separate stored frame.
gray = rng.integers(0, 256, (count, height, width), dtype=np.uint8)
gray[:, :32, :] = np.arange(width, dtype=np.uint8)
gray10 = rng.integers(0, 1024, (count, height, width), dtype=np.uint16)
inputs = {"rgb24": rgb.tobytes(), "gray": gray.tobytes(), "gray10le": gray10.astype("<u2").tobytes()}
for name, content in inputs.items():
    (out/(name+".raw")).write_bytes(content)
cases = [
    ("rgb-h264-cq23", "rgb24", "yuv444p", "h264_nvenc", False),
    ("rgb-h264-lossless-yuv444", "rgb24", "yuv444p", "h264_nvenc", True),
    ("rgb-h264-lossless-gbr", "rgb24", "gbrp", "h264_nvenc", True),
    ("gray-h264-cq23", "gray", "yuv420p", "h264_nvenc", False),
    ("gray-h264-lossless", "gray", "yuv420p", "h264_nvenc", True),
    ("gray10-hevc-lossless", "gray10le", "p010le", "hevc_nvenc", True),
]
results = {"scope": "Standalone installed-build/device synthetic pixel probe; not production pipeline, source Bayer fidelity, throughput or default selection", "device": {"ordinal": device.ordinal, "uuid": device.uuid}, "seed": 20261016, "frames": count, "dimensions": [width, height], "input_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in inputs.items()}, "cases": {}}


def run(command, content=None):
    started = time.perf_counter_ns()
    result = subprocess.run(command, input=content, capture_output=True, timeout=30)
    return result, {"command": command, "exit": result.returncode, "stderr": result.stderr.decode(errors="replace"), "elapsed_ns": time.perf_counter_ns()-started}


def difference(original, decoded, dtype):
    a, b = np.frombuffer(original, dtype=dtype), np.frombuffer(decoded, dtype=dtype)
    if a.size != b.size:
        return {"size_matches": False, "expected_bytes": len(original), "actual_bytes": len(decoded)}
    delta = np.abs(a.astype(np.int32)-b.astype(np.int32))
    return {"size_matches": True, "byte_exact": original == decoded, "reference_sha256": hashlib.sha256(original).hexdigest(), "decoded_sha256": hashlib.sha256(decoded).hexdigest(), "maximum_absolute_error": int(delta.max()), "mean_absolute_error": float(delta.mean()), "changed_component_fraction": float(np.count_nonzero(delta)/delta.size)}


for label, source, stored, codec, lossless in cases:
    row = results["cases"][label] = {"input_format": source, "encoder_format": stored, "codec": codec, "lossless_tuning": lossless}
    path = out/(label+".mp4")
    transform = "scale=in_range=full:out_range=full:out_color_matrix=bt709,format=pix_fmts="+stored
    if stored == "gbrp":
        transform = "scale=in_range=full:out_range=full,format=pix_fmts=gbrp,setparams=colorspace=gbr:range=full"
    prefix = ["ffmpeg", "-hide_banner", "-v", "error", "-filter_threads", "1", "-f", "rawvideo", "-pix_fmt", source, "-video_size", f"{width}x{height}", "-framerate", "60", "-i", "pipe:0"]
    reference, row["reference_conversion"] = run([*prefix, "-vf", transform, "-frames:v", str(count), "-pix_fmt", stored, "-f", "rawvideo", "pipe:1"], inputs[source])
    if reference.returncode != 0:
        continue
    (out/(label+"-prepared.raw")).write_bytes(reference.stdout)
    if stored == "gbrp":
        manual = rgb.transpose(0, 3, 1, 2)[:, [1, 2, 0], :, :].tobytes()
        row["manual_rgb_to_gbr_reference"] = difference(manual, reference.stdout, "u1")
    options = ["-tune", "lossless", "-rc", "constqp", "-qp", "0"] if lossless else ["-rc", "vbr", "-cq", "23", "-b:v", "0"]
    encoded, row["encode"] = run([*prefix, "-vf", transform, "-c:v", codec, "-gpu", str(device.ordinal), "-pix_fmt", "+"+stored, "-preset", "p1", *options, "-color_range", "pc", "-colorspace", "rgb" if stored == "gbrp" else "bt709", "-rc-lookahead", "0", "-bf", "0", "-y", str(path)], inputs[source])
    if encoded.returncode != 0:
        (out/"results.json").write_text(json.dumps(results, indent=2)+"\n")
        continue
    row["bytes"] = path.stat().st_size
    for name, fmt, expected in (("encoder_plane_reference", stored, reference.stdout), ("original_pre_colorspace", source, inputs[source])):
        decode_transform = "scale=in_range=full:out_range=full:in_color_matrix=bt709:out_color_matrix=bt709,format=pix_fmts="+fmt
        if stored == "gbrp":
            decode_transform = "scale=in_range=full:out_range=full,format=pix_fmts="+fmt
        decoded, row[name+"_decode"] = run(["ffmpeg", "-hide_banner", "-v", "error", "-filter_threads", "1", "-i", str(path), "-vf", decode_transform, "-pix_fmt", fmt, "-f", "rawvideo", "pipe:1"])
        row[name] = difference(expected, decoded.stdout, "<u2" if "10" in fmt else "u1") if decoded.returncode == 0 else {"decode_failed": True}
        row[name]["error_units"] = "16-bit P010 container codes (10-bit planes shifted left6)" if fmt == "p010le" else "original sample codes"
        if name == "encoder_plane_reference" and source in {"gray", "gray10le"} and decoded.returncode == 0:
            dtype = "<u2" if source == "gray10le" else "u1"
            luma = np.frombuffer(decoded.stdout, dtype=dtype).reshape(count, -1)[:, :width*height]
            if source == "gray10le":
                luma = luma >> 6
            row["original_vs_stored_luma"] = difference(inputs[source], luma.astype(dtype).tobytes(), dtype)
    probe, row["probe"] = run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_read_frames,color_range,color_space", "-of", "json", str(path)])
    row["stream"] = json.loads(probe.stdout)["streams"][0]
    assert int(row["stream"]["nb_read_frames"]) == count
    (out/"results.json").write_text(json.dumps(results, indent=2)+"\n")
print(json.dumps({name: {k: v for k, v in row.items() if k in ("bytes", "stream", "encoder_plane_reference", "original_pre_colorspace")} for name, row in results["cases"].items()}, indent=2))
