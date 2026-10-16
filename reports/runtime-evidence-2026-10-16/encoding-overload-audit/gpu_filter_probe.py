"""Installed CUDA conversion feasibility; no production filter policy change."""
import json
from pathlib import Path
import subprocess

from cephvr.platform.windows.nvidia_device import resolve_cuda_ordinal

out=Path(__file__).parent
device=resolve_cuda_ordinal("GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc")
results={"scope":"Standalone format negotiation, GPU2080 UUID mapped; no throughput claim and no hwdownload", "device":{"uuid":device.uuid,"ordinal":device.ordinal},"cases":{}}
for source,stored in (("rgb24","yuv444p"),("rgb24","gbrp"),("gray","yuv420p")):
    command=["ffmpeg","-hide_banner","-v","error","-f","rawvideo","-pix_fmt",source,"-video_size","256x256","-framerate","60","-i","pipe:0","-vf",f"hwupload_cuda=device={device.ordinal},scale_cuda=format={stored}","-c:v","h264_nvenc","-gpu",str(device.ordinal),"-preset","p1","-frames:v","12","-f","null","-"]
    result=subprocess.run(command,input=(out/"pixel-roundtrip-r2"/(source+".raw")).read_bytes(),capture_output=True,timeout=20)
    results["cases"][source+"-"+stored]={"command":command,"exit":result.returncode,"stderr":result.stderr.decode(errors="replace")}
(out/"gpu-filter-probe.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
print(json.dumps(results,indent=2))
