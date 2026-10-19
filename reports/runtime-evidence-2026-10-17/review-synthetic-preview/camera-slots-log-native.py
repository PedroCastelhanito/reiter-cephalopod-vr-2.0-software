"""Measure this process's Cocoa preview frame against the actual Qt frame."""

import ctypes as ct
import ctypes.util
import json
from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, QTimer
from PyQt6.QtWidgets import QApplication

from cephvr.gui.layouts import show_maximized
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow


class Point(ct.Structure):
    _fields_ = [("x", ct.c_double), ("y", ct.c_double)]


class Size(ct.Structure):
    _fields_ = [("width", ct.c_double), ("height", ct.c_double)]


class Rect(ct.Structure):
    _fields_ = [("origin", Point), ("size", Size)]


objc = ct.CDLL(ctypes.util.find_library("objc"))
objc.objc_getClass.argtypes = [ct.c_char_p]
objc.objc_getClass.restype = ct.c_void_p
objc.sel_registerName.argtypes = [ct.c_char_p]
objc.sel_registerName.restype = ct.c_void_p


def send(result, receiver, selector, *args, types=()):
    call = ct.CFUNCTYPE(result, ct.c_void_p, ct.c_void_p, *types)(
        ("objc_msgSend", objc)
    )
    return call(receiver, objc.sel_registerName(selector.encode()), *args)


def cocoa_frame(title):
    application = send(ct.c_void_p, objc.objc_getClass(b"NSApplication"), "sharedApplication")
    windows = send(ct.c_void_p, application, "windows")
    for index in range(send(ct.c_ulong, windows, "count")):
        native = send(ct.c_void_p, windows, "objectAtIndex:", index, types=(ct.c_ulong,))
        name = send(ct.c_void_p, native, "title")
        if send(ct.c_char_p, name, "UTF8String").decode() == title:
            frame = send(Rect, native, "frame")
            return QRect(round(frame.origin.x), round(window.screen().geometry().height() - frame.origin.y - frame.size.height), round(frame.size.width), round(frame.size.height))
    raise AssertionError("Native preview frame not found")



import sys
from cephvr.gui import review

REVIEW_PAGE = 2


class FollowControls(review.ReviewControls):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        global window
        window = self.window
        self.window.appearance.select("retro_console", persist=False)
        self.window.select_page(REVIEW_PAGE)
        self.result = {}
        QTimer.singleShot(500, self.open_sample)

    def open_sample(self):
        enabled = {camera.key for camera in self.window.devices.cameras.drafts if camera.enabled}
        self.keys = [p.key for p in self.window.dashboard.view.previews if p.active and p.key in enabled]
        self.console = self.window.devices.cameras.status_column.console
        self.console.setPlainText("\n".join(f"Native log entry {i}" for i in range(100)))
        for key in self.keys:
            self.preview_visibility(key, True)
        QTimer.singleShot(200, self.measure_open)

    def measure_open(self):
        from cephvr.gui.preview_placement import preview_window_placement
        scroll = self.console.verticalScrollBar()
        scroll.setValue(scroll.maximum())
        bottom = scroll.value()
        scroll.setValue(0)
        self.result.update({"camera_slots": list(self.window.preview_slot.frames), "enabled_cameras": [camera.key for camera in self.window.devices.cameras.drafts if camera.enabled], "log_scrollbar_visible": scroll.isVisible(), "log_scrollbar_width": scroll.width(), "log_scroll_range": scroll.maximum(), "log_can_scroll": bottom > scroll.value()})
        frames = []
        records = {}
        for key in self.keys:
            entry = self.preview_windows.windows.get(key)
            if entry is None:
                records[key] = {"failed": self.window.devices.cameras.console.toPlainText()}
                continue
            title, _ = entry
            target = self.window.preview_slot.target_for(key)
            bounds = QRect(target.mapToGlobal(QPoint()), target.size())
            frame = cocoa_frame(title)
            frames.append(frame)
            records[key] = {"target": bounds.getRect(), "native_frame": frame.getRect(), "contained": bounds.contains(frame)}
        self.result.update({"page": REVIEW_PAGE, "windows": records, "all_open": len(frames) == len(self.keys), "no_overlap": all(not a.intersects(b) for i, a in enumerate(frames) for b in frames[i+1:]), "maximized": self.window.isMaximized(), "gui_frame": self.window.frameGeometry().getRect(), "desktop": self.window.screen().availableGeometry().getRect()})
        self.window.preview_slot.grab().save(str(Path(__file__).with_name("camera-only-preview-frames-retro.png")))
        self.window.showMinimized()
        QTimer.singleShot(600, self.measure_minimized)

    def measure_minimized(self):
        self.result["all_hidden_minimized"] = all(not owner._send(ct.c_bool, owner.child, "isVisible") for owner in self.preview_windows.owners.values())
        self.result["retained"] = set(self.preview_windows.windows) == set(self.keys)
        self.window.showMaximized()
        QTimer.singleShot(600, self.measure_restored)

    def measure_restored(self):
        import cv2
        self.result["all_restored"] = all(cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) >= 1 for title, _ in self.preview_windows.windows.values())
        before = {key: cocoa_frame(title).getRect() for key, (title, _) in self.preview_windows.windows.items()}
        self.preview_visibility(self.keys[0], False)
        self.result["independent_close"] = set(self.preview_windows.windows) == set(self.keys[1:])
        self.result["remaining_positions_unchanged"] = all(cocoa_frame(title).getRect() == before[key] for key, (title, _) in self.preview_windows.windows.items())
        output = {"date": "2026-10-17", "source_revision": "uncommitted working tree", "method": "actual Retro Cameras Review; open enabled cameras, fill/scroll overflowing log, native frame/visibility queries, minimize/restore and close one", "scope": "local macOS Review only; no Windows-native or hardware acceptance", "result": self.result}
        Path(__file__).with_suffix(".json").write_text(json.dumps(output, indent=2)+"\n")
        print(json.dumps(output), flush=True)
        assert self.result["camera_slots"] == self.result["enabled_cameras"]
        assert self.result["log_scrollbar_visible"] and self.result["log_scrollbar_width"] > 0 and self.result["log_can_scroll"]
        assert self.result["all_open"] and self.result["no_overlap"]
        assert all(record["contained"] for record in self.result["windows"].values())
        assert self.result["all_hidden_minimized"] and self.result["retained"] and self.result["all_restored"]
        assert self.result["independent_close"] and self.result["remaining_positions_unchanged"]


import cephvr.gui.preview_placement as placement_module
original_place = placement_module._preview_window_placement

def diagnostic_place(main, slot):
    area = main.preview_slot
    status = area.parentWidget()
    print("GEOMETRY " + json.dumps({"area": area.geometry().getRect(), "status": status.geometry().getRect(), "hud": status.hud_card.geometry().getRect(), "log": status.log_card.geometry().getRect(), "log_min": status.console.minimumHeight(), "frames": {key: {"frame": f.geometry().getRect(), "minimum": f.minimumHeight(), "target": f.target.geometry().getRect(), "global": f.target.mapToGlobal(QPoint()).y()} for key, f in area.frames.items()}}), flush=True)
    return original_place(main, slot)

placement_module._preview_window_placement = diagnostic_place
review.ReviewControls = FollowControls
sys.argv = [sys.argv[0], "--review"]
review.main()
