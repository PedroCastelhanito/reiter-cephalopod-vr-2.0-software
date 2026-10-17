import json

import cv2
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.gui.review_preview import ReviewPreviews

app = QApplication([])
parent = QObject()
errors = []
viewer = ReviewPreviews(parent, lambda: rpc.PreviewWindowPlacement(x=60, y=80, side=320), lambda key: None, errors.append)
assert viewer.visibility("smoke", "Smoke check", True), errors
title, frame = viewer.windows["smoke"]
assert cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) >= 1
assert frame.shape == (320, 320, 3)

def finish():
    viewer.close()
    assert not viewer.windows and not viewer.timer.isActive()
    print(json.dumps({"native_visible": True, "image_shape": list(frame.shape), "closed": True, "errors": errors}), flush=True)
    app.quit()

QTimer.singleShot(500, finish)
app.exec()
