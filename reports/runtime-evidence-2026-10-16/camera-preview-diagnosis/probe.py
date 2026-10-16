"""Bounded exclusive SDK diagnostic after controller confirms camera released."""
import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from pypylon import pylon

from cephvr.acquisition.camera.features import read_value
from cephvr.acquisition.camera.metadata import native_metadata
from cephvr.acquisition.camera.native_formats import native_pixel_format
from cephvr.acquisition.preview.highgui import display_array
from cephvr.shared.pixels.preparer import PixelPreparer
from cephvr.shared.pixels.types import PixelLayout

out = Path(__file__).parent
factory = pylon.TlFactory.GetInstance()
info = next(d for d in factory.EnumerateDevices() if d.GetSerialNumber() == "40065509")
camera = pylon.InstantCamera(factory.CreateDevice(info))
result = {"serial": info.GetSerialNumber(), "model": info.GetModelName(), "frames": []}
baseline = None
try:
    camera.Open()
    nodes = camera.GetNodeMap()
    baseline = pylon.FeaturePersistence.SaveToString(nodes)
    (out / "before.pfs").write_text(baseline)
    names = ("DeviceModelName", "TimestampTickFrequency", "GevTimestampTickFrequency",
             "PixelFormat", "Width", "Height", "ExposureTime", "Gain", "Gamma",
             "TestImageSelector", "BalanceWhiteAuto", "LightSourcePreset")
    result["features"] = {n: read_value(nodes, n) for n in names}
    result["metadata"] = asdict(native_metadata(camera, info.GetSerialNumber(), "usb3"))
    camera.TriggerSelector.Value = "FrameStart"
    camera.TriggerSource.Value = "Software"
    camera.TriggerMode.Value = "On"
    camera.StartGrabbingMax(3)
    for i in range(3):
        camera.WaitForFrameTriggerReady(2000, pylon.TimeoutHandling_ThrowException)
        camera.ExecuteSoftwareTrigger()
        grab = camera.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
        try:
            assert grab.GrabSucceeded()
            fmt = native_pixel_format(pylon, int(grab.GetPixelType()))
            width, height = grab.GetWidth(), grab.GetHeight()
            stride = pylon.ComputeBufferSize(grab.GetPixelType(), width, 1) + grab.GetPaddingX()
            layout = PixelLayout(width, height, fmt, stride, stride * height)
            raw = bytes(memoryview(grab.GetBuffer())[:stride * height])
            preparer = PixelPreparer(layout)
            frame = display_array(preparer.prepare_preview(raw), np)
            converter = pylon.ImageFormatConverter()
            converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            converter.InconvertibleEdgeHandling = pylon.InconvertibleEdgeHandling_Extend
            direct = converter.Convert(grab)
            try:
                expected = direct.GetArray()
                difference = np.abs(frame.astype(np.int16) - expected.astype(np.int16))
                stats = {"index": i, "raw_min": min(raw), "raw_max": max(raw),
                         "bgr_mean": frame.mean(axis=(0, 1)).tolist(),
                         "bgr_std": frame.std(axis=(0, 1)).tolist(),
                         "direct_sdk_max_difference": int(difference.max()),
                         "timestamp_ticks": grab.GetTimeStamp()}
                result["frames"].append(stats)
                if i == 2:
                    cv2.imwrite(str(out / "preview.png"), frame)
                    np.save(out / "native.npy", grab.GetArray())
            finally:
                direct.Release()
        finally:
            grab.Release()
finally:
    if camera.IsGrabbing():
        camera.StopGrabbing()
    if baseline is not None:
        pylon.FeaturePersistence.LoadFromString(baseline, camera.GetNodeMap(), True)
        restored = pylon.FeaturePersistence.SaveToString(camera.GetNodeMap())
        (out / "restored.pfs").write_text(restored)
        result["pfs_restored_exact"] = restored == baseline
    camera.Close()
    result["closed"] = not camera.IsOpen()
    (out / "probe.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
