"""Bounded generated-image HighGUI pump cost; no cameras or experiment state."""
import json
import statistics
import time
import cv2
import numpy as np
from cephvr.platform.windows.preview_creation import StagedPreviewWindow

name = "CephVR isolated event-pump probe"
results = {}
try:
    with StagedPreviewWindow(name):
        cv2.namedWindow(name, cv2.WINDOW_NORMAL)
        cv2.imshow(name, np.zeros((128, 128), dtype=np.uint8))
        cv2.pollKey()
        for label, pump in (("waitKey1", lambda: cv2.waitKey(1)), ("pollKey", cv2.pollKey)):
            samples = []
            for _ in range(100):
                start = time.perf_counter_ns()
                pump()
                samples.append((time.perf_counter_ns() - start) / 1e6)
            results[label] = {"median_ms": statistics.median(samples), "max_ms": max(samples)}
finally:
    cv2.destroyWindow(name)
    cv2.pollKey()
print(json.dumps({"opencv": cv2.__version__, "pump_cost": results}, indent=2))
