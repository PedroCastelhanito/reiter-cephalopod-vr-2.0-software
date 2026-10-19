"""Actual local Review snap check; always close test windows on completion."""
import ctypes as ct
import json
from pathlib import Path
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from cephvr.gui import review


class SnapControls(review.ReviewControls):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.window.select_page(2)
        self.result = {}
        QTimer.singleShot(500, self.open_preview)

    def open_preview(self):
        try:
            self.key = next(p.key for p in self.window.dashboard.view.previews if p.active and p.key.startswith("camera"))
            self.preview_visibility(self.key, True)
            QTimer.singleShot(400, self.move_preview)
        except Exception as exc:
            self.finish(exc)

    def move_preview(self):
        try:
            owner = self.preview_windows.owners[self.key]
            self.original = owner.geometry()
            frame = owner._frame(owner.child)
            frame.origin.x += 80
            frame.size.width -= 20
            owner._send(None, owner.child, "setFrame:display:", frame, True, types=(type(frame), ct.c_bool))
            QTimer.singleShot(400, self.snap_preview)
        except Exception as exc:
            self.finish(exc)

    def snap_preview(self):
        try:
            self.result["manual_detected"] = self.preview_windows.guards[self.key].manual
            self.window.preview_slot.frames[self.key].snap_button.click()
            QTimer.singleShot(400, self.verify)
        except Exception as exc:
            self.finish(exc)

    def verify(self):
        try:
            self.result["geometry_restored"] = self.preview_windows.owners[self.key].geometry() == self.original
            self.result["automatic_restored"] = not self.preview_windows.guards[self.key].manual
            self.preview_visibility(self.key, False)
            self.preview_windows.snap(self.key)
            self.result["closed_not_reopened"] = self.key not in self.preview_windows.windows
            self.finish()
        except Exception as exc:
            self.finish(exc)

    def finish(self, error=None):
        if error is not None:
            self.result["error"] = str(error)
        self.preview_windows.close()
        self.result["test_previews_closed"] = not self.preview_windows.windows
        output = {"date": "2026-10-19", "source_revision": "uncommitted working tree", "scope": "macOS local Review only; no Windows/hardware acceptance", "checks": self.result}
        Path(__file__).with_suffix(".json").write_text(json.dumps(output, indent=2)+"\n")
        print(json.dumps(output), flush=True)
        self.window.close()
        QApplication.instance().quit()


review.ReviewControls = SnapControls
sys.argv = [sys.argv[0], "--review", "--simulated-devices"]
review.main()
