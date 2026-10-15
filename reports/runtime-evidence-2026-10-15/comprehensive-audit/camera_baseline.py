"""Read and preserve actual camera feature state before managed ownership."""

import hashlib
import json
from pathlib import Path

from pypylon import genicam, pylon

out = Path(__file__).parent
factory = pylon.TlFactory.GetInstance()
records = []
for device in factory.EnumerateDevices():
    row = {"serial": device.GetSerialNumber(), "readback": {}}
    records.append(row)
    camera = pylon.InstantCamera(factory.CreateDevice(device))
    try:
        camera.Open()
        content = pylon.FeaturePersistence.SaveToString(camera.GetNodeMap()).encode()
        target = out / f"camera-{row['serial']}-baseline.pfs"
        if target.exists() and target.read_bytes() != content:
            raise RuntimeError("Baseline already exists with different values")
        target.write_bytes(content)
        row["pfs_sha256"] = hashlib.sha256(content).hexdigest()
        for name in ("Width", "Height", "OffsetX", "OffsetY", "PixelFormat", "ExposureTime", "ExposureTimeAbs", "Gain", "GainRaw", "AcquisitionFrameRateEnable", "AcquisitionFrameRate", "AcquisitionFrameRateAbs", "TriggerSelector", "TriggerMode", "TriggerSource", "TriggerActivation", "LineSelector", "DeviceLinkThroughputLimit"):
            try:
                node = camera.GetNodeMap().GetNode(name)
                if node is not None and genicam.IsReadable(node):
                    row["readback"][name] = node.ToString()
            except genicam.GenericException as error:
                row.setdefault("unavailable", {})[name] = str(error)
    finally:
        camera.Close()
        row["closed"] = not camera.IsOpen()
        (out / "camera-baseline.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
print(json.dumps(records, indent=2))
