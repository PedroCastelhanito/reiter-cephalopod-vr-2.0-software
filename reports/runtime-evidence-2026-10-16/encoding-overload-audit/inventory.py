"""Fresh read-only hardware, camera-state and installed-encoder inventory."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from pypylon import genicam, pylon
from serial.tools import list_ports

out = Path(__file__).parent
assert not (out/"inventory.json").exists()
record = {"observed_unix_time": time.time(), "python": sys.version, "disk": shutil.disk_usage(Path.cwd())._asdict(), "ports": [{"device": p.device, "description": p.description} for p in list_ports.comports()], "cameras": []}
for label, command in {
    "ffmpeg-version": ["ffmpeg", "-hide_banner", "-version"],
    "h264-capability": ["ffmpeg", "-hide_banner", "-h", "encoder=h264_nvenc"],
    "hevc-capability": ["ffmpeg", "-hide_banner", "-h", "encoder=hevc_nvenc"],
    "gpu-inventory": ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version,pci.bus_id", "--format=csv"],
}.items():
    result = subprocess.run(command, capture_output=True, timeout=15)
    (out/(label+".txt")).write_bytes(result.stdout+result.stderr)
    record[label] = {"command": command, "exit": result.returncode, "executable": shutil.which(command[0])}
factory = pylon.TlFactory.GetInstance()
for device in factory.EnumerateDevices():
    row = {"serial": device.GetSerialNumber(), "model": device.GetModelName(), "readback": {}}
    record["cameras"].append(row)
    camera = pylon.InstantCamera(factory.CreateDevice(device))
    try:
        camera.Open()
        content = pylon.FeaturePersistence.SaveToString(camera.GetNodeMap()).encode()
        (out/f"camera-{row['serial']}-baseline.pfs").write_bytes(content)
        row["pfs_sha256"] = hashlib.sha256(content).hexdigest()
        for name in ("Width", "Height", "OffsetX", "OffsetY", "PixelFormat", "ExposureTime", "ExposureTimeAbs", "Gain", "GainRaw", "AcquisitionFrameRateEnable", "AcquisitionFrameRate", "AcquisitionFrameRateAbs", "TriggerSelector", "TriggerMode", "TriggerSource", "TriggerActivation", "LineSelector", "DeviceLinkThroughputLimit", "TestImageSelector"):
            try:
                node = camera.GetNodeMap().GetNode(name)
                if node is not None and genicam.IsReadable(node):
                    row["readback"][name] = node.ToString()
            except genicam.GenericException:
                pass
    finally:
        camera.Close()
        row["closed"] = not camera.IsOpen()
        (out/"inventory.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"cameras": record["cameras"], "disk_free": record["disk"]["free"]}, indent=2))
