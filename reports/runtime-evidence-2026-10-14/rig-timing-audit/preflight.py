"""Read-only current rig inventory; does not open cameras or start recording."""

import asyncio
import json
import subprocess
from pathlib import Path

import glfw
from google.protobuf.json_format import MessageToDict

from cephvr.platform.windows.display_identity import monitor_interface
from cephvr.synchronization.diagnostic import SpikeGLXDiagnostic

ROOT = Path(__file__).resolve().parents[3]
result = {"tracking_backend": "deferred by owner", "displays": []}
result["glfw_initialized"] = bool(glfw.init())
try:
    if result["glfw_initialized"]:
        for monitor in glfw.get_monitors():
            mode = glfw.get_video_mode(monitor)
            adapter = glfw.get_win32_adapter(monitor)
            name = glfw.get_win32_monitor(monitor)
            result["displays"].append({
                "adapter": adapter,
                "monitor": name,
                "interface": monitor_interface(adapter, name),
                "position": list(glfw.get_monitor_pos(monitor)),
                "size": [mode.size.width, mode.size.height],
                "refresh_hz": mode.refresh_rate,
                "content_scale": list(glfw.get_monitor_content_scale(monitor)),
            })
finally:
    glfw.terminate()
result["spikeglx"] = MessageToDict(
    asyncio.run(SpikeGLXDiagnostic(ROOT).check()),
    preserving_proto_field_name=True,
)
for name, command in {
    "gpus": ["nvidia-smi", "--query-gpu=index,name,uuid,driver_version", "--format=csv"],
    "ffmpeg": ["ffmpeg", "-version"],
    "ffprobe": ["ffprobe", "-version"],
}.items():
    completed = subprocess.run(command, capture_output=True, text=True, timeout=15)
    result[name] = {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
destination = Path(__file__).with_name("preflight.json")
destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
