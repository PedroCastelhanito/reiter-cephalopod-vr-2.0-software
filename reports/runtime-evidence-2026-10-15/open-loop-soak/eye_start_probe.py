"""Bounded native Eye startup latency only; no MCU, encoder or Tracking process."""

import json
from pathlib import Path
import time

from pypylon import pylon

OUT = Path(__file__).resolve().parent
record = dict(scope="three Eye native StartGrabbing latency probes after managed application exit; no acceptance or deadline changes", attempts=[])
factory = pylon.TlFactory.GetInstance()
device = next(d for d in factory.EnumerateDevices() if d.GetSerialNumber() == "40278236")
camera = pylon.InstantCamera(factory.CreateDevice(device))
try:
    camera.Open()
    before = pylon.FeaturePersistence.SaveToString(camera.GetNodeMap())
    (OUT / "eye-start-probe-before.pfs").write_text(before, encoding="utf-8")
    record["settings"] = {name: camera.GetNodeMap().GetNode(name).ToString() for name in ("TriggerSelector", "TriggerMode", "AcquisitionFrameRateEnable", "AcquisitionFrameRate", "Width", "Height", "PixelFormat", "ExposureTime")}
    assert record["settings"]["TriggerMode"] == "Off"
    assert record["settings"]["AcquisitionFrameRateEnable"] == "1"
    assert float(record["settings"]["AcquisitionFrameRate"]) == 60
    camera.MaxNumBuffer = 15
    for repeat in range(3):
        row = dict(repeat=repeat, start_call_ns=time.perf_counter_ns())
        record["attempts"].append(row)
        try:
            camera.StartGrabbing(pylon.GrabStrategy_OneByOne, pylon.GrabLoop_ProvidedByUser)
            row["start_return_ns"] = time.perf_counter_ns()
            grab = camera.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
            try:
                row.update(first_result_ns=time.perf_counter_ns(), valid=grab.GrabSucceeded(), width=grab.Width, height=grab.Height)
            finally:
                grab.Release()
        except Exception as error:
            row["error"] = f"{type(error).__name__}: {error}"
        finally:
            if camera.IsGrabbing():
                camera.StopGrabbing()
            row["stopped_ns"] = time.perf_counter_ns()
            (OUT / "eye-start-probe.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    after = pylon.FeaturePersistence.SaveToString(camera.GetNodeMap())
    record["persistent_settings_unchanged"] = before == after
    (OUT / "eye-start-probe-after.pfs").write_text(after, encoding="utf-8")
finally:
    camera.Close()
    record["closed"] = not camera.IsOpen()
    (OUT / "eye-start-probe.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))
