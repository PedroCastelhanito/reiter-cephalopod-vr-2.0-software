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
        self.window.appearance.select("retro_console", persist=False)
        self.result = {}
        QTimer.singleShot(500, self.open_sample)

    def open_sample(self):
        self.preview_visibility("stimulus", True)
        QTimer.singleShot(200, self.measure_open)

    def measure_open(self):
        if "stimulus" not in self.preview_windows.windows:
            print("OPEN FAILED: " + self.window.devices.cameras.console.toPlainText(), flush=True)
            QApplication.instance().quit()
            return
        title, _ = self.preview_windows.windows["stimulus"]
        self.title = title
        owner = self.preview_windows.owners["stimulus"]
        target = self.window.preview_slot.target
        bounds = QRect(target.mapToGlobal(QPoint()), target.size())
        native = cocoa_frame(title)
        self.window.preview_slot.grab().save(str(Path(__file__).with_name("preview-frame-retro.png")))
        self.result.update({"bracket_caption": self.window.preview_slot.caption.text(), "ordinary_card": self.window.preview_slot.property("role") == "card", "target": bounds.getRect(), "frame": native.getRect(), "contained": bounds.contains(native), "native_parent_matches_gui": owner._send(ct.c_void_p, owner.child, "parentWindow") == owner.parent})
        self.window.showMinimized()
        QTimer.singleShot(600, self.measure_minimized)

    def measure_minimized(self):
        import cv2
        self.result.update({"gui_minimized": self.window.isMinimized(), "preview_hidden_while_minimized": not self.preview_windows.owners["stimulus"]._send(ct.c_bool, self.preview_windows.owners["stimulus"].child, "isVisible"), "opencv_visible_property_while_minimized": cv2.getWindowProperty(self.title, cv2.WND_PROP_VISIBLE), "preview_retained": "stimulus" in self.preview_windows.windows, "show_retained": next(p for p in self.window.dashboard.view.previews if p.key == "stimulus").visible})
        self.window.showMaximized()
        self.window.activateWindow()
        QTimer.singleShot(600, self.measure_restored)

    def measure_restored(self):
        import cv2
        owner = self.preview_windows.owners["stimulus"]
        application = send(ct.c_void_p, objc.objc_getClass(b"NSApplication"), "sharedApplication")
        ordered = send(ct.c_void_p, application, "orderedWindows")
        order = [send(ct.c_void_p, ordered, "objectAtIndex:", i, types=(ct.c_ulong,)) for i in range(send(ct.c_ulong, ordered, "count"))]
        self.result.update({"gui_restored": not self.window.isMinimized(), "preview_visible_after_restore": cv2.getWindowProperty(self.title, cv2.WND_PROP_VISIBLE) >= 1, "preview_above_gui": order.index(owner.child) < order.index(owner.parent)})
        self.preview_visibility("stimulus", False)
        self.result["closed"] = not self.preview_windows.windows and not self.preview_windows.owners
        output = {"date": "2026-10-17", "source_revision": "uncommitted working tree", "method": "actual Review --review entry, own-process Cocoa parent/frame/order queries; native Qt minimize and restore", "scope": "local macOS Review only, no real devices or Windows-native acceptance", "result": self.result}
        Path(__file__).with_suffix(".json").write_text(json.dumps(output, indent=2)+"\n")
        print(json.dumps(output), flush=True)
        assert self.result["contained"] and self.result["native_parent_matches_gui"]
        assert self.result["gui_minimized"] and self.result["preview_hidden_while_minimized"]
        assert self.result["preview_retained"] and self.result["show_retained"]
        assert self.result["gui_restored"] and self.result["preview_visible_after_restore"] and self.result["preview_above_gui"]
        assert self.result["closed"]


review.ReviewControls = FollowControls
sys.argv = [sys.argv[0], "--review"]
review.main()
