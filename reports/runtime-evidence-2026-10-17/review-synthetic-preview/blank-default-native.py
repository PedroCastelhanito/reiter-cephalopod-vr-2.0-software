"""Verify the real default Review entry point and leave its GUI open."""

import json
import sys
from pathlib import Path

import cv2
from PyQt6.QtCore import QTimer

from cephvr.gui import review


class CheckedControls(review.ReviewControls):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        QTimer.singleShot(500, self.open_sample)

    def open_sample(self):
        assert self.preview_windows is not None
        self.preview_visibility("stimulus", True)
        QTimer.singleShot(150, self.verify_sample)

    def verify_sample(self):
        title, frame = self.preview_windows.windows["stimulus"]
        result = {
            "date": "2026-10-17",
            "source_revision": "uncommitted working tree",
            "method": "actual review.main with --review only; active-source Show; native HighGUI visibility and blank frame checks",
            "visible": cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) >= 1,
            "black": not frame.any(),
            "shape": list(frame.shape),
            "scope": "local macOS simulated Review; no camera or managed runtime",
        }
        assert result["visible"] and result["black"]
        self.preview_visibility("stimulus", False)
        result["closed"] = not self.preview_windows.windows
        Path(__file__).with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)


review.ReviewControls = CheckedControls
sys.argv = [sys.argv[0], "--review"]
review.main()
