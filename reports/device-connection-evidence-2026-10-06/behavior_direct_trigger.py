"""Two-second Behavior D10/Line4 receiver check; no recording or Tracking pulses."""
import json
import time
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from pypylon import pylon

from cephvr.acquisition.configuration import load_file_policies
from cephvr.acquisition.microcontroller.owner import SerialOwner
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.shared.clock import host_time_ns

folder = Path(__file__).parent
result = {"scope": "Behavior serial 40065509, COM8 D10 -> Line4, two seconds"}
owner = SerialOwner("COM8", load_file_policies(folder.parents[1]))
device = None
on = False
try:
    factory = pylon.TlFactory.GetInstance()
    info = next(i for i in factory.EnumerateDevices() if i.GetSerialNumber() == "40065509")
    device = pylon.InstantCamera(factory.CreateDevice(info))
    device.Open()
    device.TriggerSelector.Value = "FrameStart"
    device.TriggerSource.Value = "Line4"
    device.TriggerMode.Value = "On"
    result["settings"] = {"trigger": device.TriggerMode.Value,
                          "source": device.TriggerSource.Value,
                          "width": device.Width.Value, "height": device.Height.Value}
    result["connect"] = MessageToDict(owner.connect(host_time_ns()+5_000_000_000))
    requested = camera.CameraPulseConfiguration(port="COM8")
    requested.behavioral.pin = "D10"
    requested.behavioral.requested_frequency_hz = 30
    owner.configure(requested, host_time_ns()+1_000_000_000, active_roles=(1,))
    device.StartGrabbing(pylon.GrabStrategy_OneByOne)
    result["on"] = MessageToDict(owner.on((1,), host_time_ns()+1_000_000_000))
    on = True
    end = time.monotonic()+2
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
    if on:
        result["off"] = MessageToDict(owner.off((1,), host_time_ns()+1_000_000_000))
    if device is not None:
        if device.IsGrabbing(): device.StopGrabbing()
        device.Close()
    owner.close(host_time_ns()+1_000_000_000)
    result["closed"] = True
    folder.joinpath("behavior-direct-trigger.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k != "frames"}, indent=2))
    print("frames", len(result.get("frames", [])))
