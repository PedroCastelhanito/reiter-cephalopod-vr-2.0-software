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

class FollowControls(review.ReviewControls):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        global window
        window = self.window
        window.appearance.select("retro_console", persist=False)
        window.select_page(2)
        enabled = {c.key for c in window.devices.cameras.drafts if c.enabled}
        self.keys = [p.key for p in window.dashboard.view.previews if p.active and p.key in enabled][:2]
        self.result = {}
        QTimer.singleShot(600, self.one)

    def capture(self, stage):
        records = {}
        for key, (title, _) in self.preview_windows.windows.items():
            target = window.preview_slot.target_for(key)
            bounds = QRect(target.mapToGlobal(QPoint()), target.size())
            frame = cocoa_frame(title)
            records[key] = {"frame": frame.getRect(), "target": bounds.getRect(), "contained": bounds.contains(frame), "manual": self.preview_windows.guards[key].manual}
        self.result[stage] = records
        return records

    def one(self):
        self.preview_visibility(self.keys[0], True)
        QTimer.singleShot(500, self.two)

    def two(self):
        self.capture("one")
        self.preview_visibility(self.keys[1], True)
        QTimer.singleShot(500, self.shrink)

    def shrink(self):
        self.capture("two")
        self.preview_visibility(self.keys[1], False)
        QTimer.singleShot(500, self.move)

    def move(self):
        self.capture("one_again")
        owner = self.preview_windows.owners[self.keys[0]]
        frame = owner._frame(owner.child)
        frame.origin.x += 31
        owner._send(None, owner.child, "setFrame:display:", frame, True, types=(type(frame), ct.c_bool))
        QTimer.singleShot(400, self.moved)

    def moved(self):
        self.capture("moved")
        self.preview_visibility(self.keys[1], True)
        QTimer.singleShot(500, self.reopen)

    def reopen(self):
        self.capture("moved_two")
        self.preview_visibility(self.keys[0], False)
        self.preview_visibility(self.keys[0], True)
        QTimer.singleShot(500, self.resize)

    def resize(self):
        self.capture("reopened")
        import cv2
        title = self.preview_windows.windows[self.keys[0]][0]
        cv2.resizeWindow(title, 180, 180)
        cv2.waitKey(1)
        QTimer.singleShot(400, self.resized)

    def resized(self):
        self.capture("resized")
        self.preview_visibility(self.keys[1], False)
        QTimer.singleShot(500, self.dashboard)

    def dashboard(self):
        self.capture("resized_one")
        self.preview_visibility(self.keys[0], False)
        window.select_page(0)
        for source in window.dashboard.view.previews:
            if source.active:
                self.preview_visibility(source.key, True)
        QTimer.singleShot(600, self.finish)

    def finish(self):
        self.capture("dashboard")
        a, b = self.keys
        r = self.result
        checks = {
            "single_centered": abs((r["one"][a]["frame"][0] + r["one"][a]["frame"][2]/2) - (r["two"][a]["frame"][0] + r["two"][b]["frame"][0] + r["two"][b]["frame"][2])/2) <= 2,
            "grid_resizes": r["one"][a]["frame"][2] > r["dashboard"][a]["frame"][2],
            "one_restores": r["one"][a]["frame"] == r["one_again"][a]["frame"],
            "automatic_contained": all(item["contained"] and not item["manual"] for stage in ("one", "two", "one_again", "reopened", "dashboard") for item in r[stage].values()),
            "move_preserved": r["moved"][a]["frame"] == r["moved_two"][a]["frame"] and r["moved_two"][a]["manual"],
            "resize_preserved": r["resized"][a]["frame"] == r["resized_one"][a]["frame"] and r["resized_one"][a]["manual"],
            "dashboard_three": len(r["dashboard"]) == 3,
            "maximized": window.isMaximized(),
        }
        output = {"date": "2026-10-19", "source_revision": "uncommitted working tree", "scope": "actual local macOS Review; no Windows/hardware acceptance", "checks": checks, "result": r}
        Path(__file__).with_suffix(".json").write_text(json.dumps(output, indent=2)+"\n")
        print(json.dumps(output), flush=True)
        window.grab().save(str(Path(__file__).with_suffix(".png")))

review.ReviewControls = FollowControls
sys.argv = [sys.argv[0], "--review"]
review.main()
