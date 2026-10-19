"""Measure this process's Cocoa preview frame against the actual Qt card."""

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


class VisibilityControls(review.ReviewControls):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        global window
        window = self.window
        QTimer.singleShot(500, self.open_sample)

    def open_sample(self):
        self.before = self.window.dashboard.log_console.height()
        self.result = {"initial_card_hidden": self.window.preview_slot.isHidden(), "log_before": self.before}
        self.preview_visibility("stimulus", True)
        QTimer.singleShot(150, self.measure_open)

    def measure_open(self):
        title, _ = self.preview_windows.windows["stimulus"]
        target = self.window.preview_slot.target
        bounds = QRect(target.mapToGlobal(QPoint()), target.size())
        native = cocoa_frame(title)
        self.result.update({"card_open": self.window.preview_slot.isVisible(), "log_open": self.window.dashboard.log_console.height(), "target": bounds.getRect(), "native_frame": native.getRect(), "native_contained": bounds.contains(native)})
        self.preview_visibility("stimulus", False)
        QTimer.singleShot(150, self.measure_closed)

    def measure_closed(self):
        self.result.update({"card_hidden_after_close": self.window.preview_slot.isHidden(), "log_after": self.window.dashboard.log_console.height(), "preview_closed": not self.preview_windows.windows})
        output = {"date": "2026-10-17", "source_revision": "f6cb9f4e plus uncommitted preview visibility changes", "method": "actual Review --review entry, native Cocoa frame queried from this process; Show/Hide through Review controls", "scope": "local macOS sample only; no real device or Windows acceptance", "result": self.result}
        Path(__file__).with_suffix(".json").write_text(json.dumps(output, indent=2)+"\n")
        print(json.dumps(output), flush=True)
        assert self.result["initial_card_hidden"] and self.result["card_open"] and self.result["native_contained"]
        assert self.result["log_open"] < self.result["log_before"]
        assert self.result["card_hidden_after_close"] and self.result["preview_closed"]
        assert self.result["log_after"] == self.result["log_before"]


review.ReviewControls = VisibilityControls
sys.argv = [sys.argv[0], "--review"]
review.main()
