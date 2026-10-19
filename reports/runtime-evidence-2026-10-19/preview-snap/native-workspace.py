"""Actual local Review snap check; always close test windows on completion."""
import ctypes as ct
import json
from pathlib import Path
import sys

from PyQt6.QtCore import QTimer, QPoint, QRect
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
            self.workspace()
        except Exception as exc:
            self.finish(exc)

    def workspace(self):
        self.window.select_page(0)
        self.window.dashboard.show_previews()
        for source in self.window.dashboard.view.previews:
            if source.active:
                self.preview_visibility(source.key, True)
        QTimer.singleShot(600, self.workspace_check)

    def workspace_check(self):
        try:
            panel = self.window.dashboard.preview_dialog
            self.result["workspace_three"] = len(self.preview_windows.windows) == 3
            self.result["external_grid"] = self.window.preview_slot.window() is panel
            self.result["workspace_contained"] = self.contained()
            panel.move(panel.x() + 25, panel.y() + 20)
            QTimer.singleShot(400, self.workspace_moved)
        except Exception as exc:
            self.finish(exc)

    def contained(self):
        host = self.window.preview_slot.window()
        result = True
        records = {}
        for key, owner in self.preview_windows.owners.items():
            target = self.window.preview_slot.target_for(key)
            bounds = QRect(target.mapToGlobal(QPoint()), target.size())
            rect = QRect(*owner.geometry())
            rect.translate(host.frameGeometry().topLeft())
            records[key] = {"target": bounds.getRect(), "native": rect.getRect(), "manual": self.preview_windows.guards[key].manual}
            result = result and bounds.adjusted(-2, -2, 2, 2).contains(rect)
        self.result.setdefault("geometry", []).append(records)
        return result

    def workspace_moved(self):
        try:
            self.result["move_contained"] = self.contained()
            self.window.dashboard.preview_dialog.close()
            QTimer.singleShot(300, self.workspace_hidden)
        except Exception as exc:
            self.finish(exc)

    def workspace_hidden(self):
        try:
            self.result["hidden_retains_three"] = len(self.preview_windows.windows) == 3
            self.result["all_hidden"] = all(not owner._send(ct.c_bool, owner.child, "isVisible") for owner in self.preview_windows.owners.values())
            self.window.dashboard.show_previews()
            QTimer.singleShot(400, self.workspace_restored)
        except Exception as exc:
            self.finish(exc)

    def workspace_restored(self):
        try:
            self.result["all_restored"] = all(owner._send(ct.c_bool, owner.child, "isVisible") for owner in self.preview_windows.owners.values())
            self.result["restore_contained"] = self.contained()
            self.preview_visibility("stimulus", False)
            self.window.select_page(2)
            QTimer.singleShot(500, self.cameras_restored)
        except Exception as exc:
            self.finish(exc)

    def cameras_restored(self):
        try:
            self.result["cameras_retarget"] = self.window.preview_slot.window() is self.window and self.contained()
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
