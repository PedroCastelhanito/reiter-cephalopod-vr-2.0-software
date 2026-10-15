"""Read-only inventories and original camera settings before managed ownership."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from pypylon import genicam, pylon
from serial.tools import list_ports

from cephvr.gui.calibration_profile import active_monitor_bindings

OUT = Path(__file__).resolve().parent
FIELDS = ("Width", "Height", "OffsetX", "OffsetY", "PixelFormat", "ExposureTime", "ExposureTimeAbs", "Gain", "GainRaw", "AcquisitionFrameRateEnable", "AcquisitionFrameRate", "AcquisitionFrameRateAbs", "TriggerSelector", "TriggerMode", "TriggerSource", "TriggerActivation", "DeviceLinkThroughputLimit")


def main():
    record = dict(source_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), python=sys.version,
                  captured_monotonic_ns=time.perf_counter_ns(), storage=shutil.disk_usage(Path.cwd())._asdict(),
                  displays=[asdict(row) for row in active_monitor_bindings()],
                  ports=[dict(device=p.device, description=p.description) for p in list_ports.comports()], cameras=[])
    factory = pylon.TlFactory.GetInstance()
    configured = {row["serial"] for row in json.loads(Path(r"C:\Users\ReiterU_PC\Desktop\Pedro\cameras_config.json").read_text())["cameras"]}
    def save():
        (OUT / "preflight.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    save()
    for device in factory.EnumerateDevices():
        row = dict(serial=device.GetSerialNumber(), model=device.GetModelName(), class_name=device.GetDeviceClass())
        record["cameras"].append(row)
        if row["serial"] not in configured:
            row["not_opened"] = "outside configured Pedro serials"
            save()
            continue
        camera = pylon.InstantCamera(factory.CreateDevice(device))
        try:
            camera.Open()
            pfs = pylon.FeaturePersistence.SaveToString(camera.GetNodeMap())
            path = OUT / (row["serial"] + "-baseline.pfs")
            if path.exists() and path.read_text(encoding="utf-8") != pfs:
                raise RuntimeError("Baseline already exists with different values; preserve originals")
            path.write_text(pfs, encoding="utf-8")
            row["pfs_sha256"] = hashlib.sha256(pfs.encode()).hexdigest()
            row["readback"] = {}
            for name in FIELDS:
                try:
                    node = camera.GetNodeMap().GetNode(name)
                    if node is not None and genicam.IsReadable(node):
                        row["readback"][name] = node.ToString()
                except genicam.GenericException as error:
                    row.setdefault("unavailable_fields", {})[name] = str(error)
        except Exception as error:
            row["error"] = f"{type(error).__name__}: {error}"
        finally:
            camera.Close()
            row["closed"] = not camera.IsOpen()
            save()
    for tool, arguments in (("ffmpeg", ["-version"]), ("ffprobe", ["-version"]), ("nvidia-smi", ["--query-gpu=index,uuid,name,driver_version", "--format=csv"])):
        run = subprocess.run([tool, *arguments], capture_output=True, text=True, timeout=15)
        record[tool] = dict(path=shutil.which(tool), returncode=run.returncode, stdout=run.stdout, stderr=run.stderr)
    save()
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
