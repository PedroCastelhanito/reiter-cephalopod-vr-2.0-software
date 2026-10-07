"""Two-second D11/Line2 receiver isolation after confirmed managed process exit."""

import json
import time
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from pypylon import pylon

from cephvr.acquisition.configuration import load_file_policies
from cephvr.acquisition.microcontroller.owner import SerialOwner
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.shared.clock import host_time_ns

OUT = Path(__file__).parent
ROOT = OUT.parents[1]
result = {"scope": "40747103 / BehaviorSquid readback / COM8 D11 -> Line2, two seconds; no recording"}
owner = SerialOwner("COM8", load_file_policies(ROOT))
device = None
configured = False
try:
    factory = pylon.TlFactory.GetInstance()
    info = next(i for i in factory.EnumerateDevices() if i.GetSerialNumber() == "40747103")
    device = pylon.InstantCamera(factory.CreateDevice(info))
    device.Open()
    device.TriggerSelector.Value = "FrameStart"
    result["readback"] = {
        "trigger": device.TriggerMode.Value, "source": device.TriggerSource.Value,
        "width": device.Width.Value, "height": device.Height.Value,
        "pixel_format": device.PixelFormat.Value, "exposure_us": device.ExposureTime.Value,
    }
    assert result["readback"]["source"] == "Line2"
    # Managed cleanup disables triggers. Restore the selected PFS's FrameStart mode.
    device.TriggerMode.Value = "On"
    result["capture_trigger_mode"] = device.TriggerMode.Value
    result["connect"] = MessageToDict(owner.connect(host_time_ns() + 5_000_000_000))
    requested = camera.CameraPulseConfiguration(port="COM8")
    requested.tracking.pin = "D11"
    requested.tracking.requested_frequency_hz = 60
    owner.configure(requested, host_time_ns() + 1_000_000_000, active_roles=(2,))
    configured = True
    device.StartGrabbing(pylon.GrabStrategy_OneByOne)
    result["on"] = MessageToDict(owner.on((2,), host_time_ns() + 1_000_000_000))
    end = time.monotonic() + 2
    frames = []
    while time.monotonic() < end:
        grab = device.RetrieveResult(150, pylon.TimeoutHandling_Return)
        if grab is not None:
            try:
                frames.append({"valid": grab.GrabSucceeded(), "id": grab.GetBlockID()})
            finally:
                grab.Release()
    result["frames"] = frames
except Exception as exc:
    result["error"] = f"{type(exc).__name__}: {exc}"
finally:
    if configured:
        try:
            result["off"] = MessageToDict(owner.off((2,), host_time_ns() + 1_000_000_000))
        except Exception as exc:
            result["off_error"] = str(exc)
    if device is not None:
        if device.IsGrabbing():
            device.StopGrabbing()
        device.Close()
        result["camera_closed"] = not device.IsOpen()
    owner.close(host_time_ns() + 1_000_000_000)
    result["serial_close_returned"] = True
    (OUT / "tracking-receiver.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "frames"}, indent=2))
    print("frames", len(result.get("frames", [])))
