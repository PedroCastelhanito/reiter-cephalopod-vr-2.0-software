"""Real serial and camera connection readback; no acquisition or pin tests."""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from pypylon import pylon
from serial.tools import list_ports

from cephvr.acquisition.configuration import load_file_policies
from cephvr.acquisition.microcontroller.owner import SerialOwner
from cephvr.shared.clock import host_time_ns

root = Path(__file__).resolve().parents[2]
result = {
    "captured_at": datetime.now().astimezone().isoformat(),
    "source_revision": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip(),
    "health_source_sha256": hashlib.sha256(
        (root / "src/cephvr/acquisition/coordinator/health.py").read_bytes()
    ).hexdigest(),
    "ports": [
        {"port": port.device, "description": port.description, "hardware_id": port.hwid}
        for port in list_ports.comports()
    ],
    "pylon_version": pylon.GetPylonVersionString(),
    "cameras": [],
}
owner = SerialOwner("COM8", load_file_policies(root))
try:
    result["microcontroller"] = MessageToDict(
        owner.connect(host_time_ns() + 5_000_000_000),
        preserving_proto_field_name=True,
    )
    result["malformed_replies"] = owner.malformed_replies
    result["unmatched_replies"] = owner.unmatched_replies
finally:
    owner.close(host_time_ns() + 1_000_000_000)
    result["microcontroller_closed"] = True

for info in pylon.TlFactory.GetInstance().EnumerateDevices():
    camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(info))
    row = {"serial": info.GetSerialNumber(), "model": info.GetModelName(), "settings": {}}
    try:
        camera.Open()
        row["opened"] = camera.IsOpen()
        for name in (
            "DeviceFirmwareVersion", "Width", "Height", "PixelFormat",
            "TriggerSelector", "TriggerMode", "TriggerSource", "TriggerActivation",
            "ExposureTime", "DeviceLinkThroughputLimit",
        ):
            try:
                row["settings"][name] = camera.GetNodeMap().GetNode(name).ToString()
            except Exception as exc:
                row["settings"][name] = {"unavailable": str(exc)}
    finally:
        camera.Close()
        row["closed"] = not camera.IsOpen()
    result["cameras"].append(row)

text = json.dumps(result, indent=2)
(Path(__file__).parent / "direct-connections.json").write_text(text, encoding="utf-8")
print(text)
