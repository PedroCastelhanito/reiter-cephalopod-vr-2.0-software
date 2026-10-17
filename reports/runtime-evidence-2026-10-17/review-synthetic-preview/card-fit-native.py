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


app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, device_review=True)
controls = ReviewControls(window, simulate_projectors=True, fake_previews=True)
window.appearance.select("retro_console", persist=False)
show_maximized(window)
results = []


def open_preview():
    camera = window.devices.cameras.drafts[0]
    controls.preview_visibility(camera.key, True)
    QTimer.singleShot(150, measure)


def measure():
    viewer = controls.preview_windows
    title, _ = next(iter(viewer.windows.values()))
    slot = window.preview_slot.target
    target = QRect(slot.mapToGlobal(QPoint()), slot.size())
    frame = cocoa_frame(title)
    result = {"target": target.getRect(), "native_frame": frame.getRect(), "contained": target.contains(frame), "center_error": [frame.center().x() - target.center().x(), frame.center().y() - target.center().y()]}
    results.append(result)
    viewer.close()
    if len(results) == 1:
        window.showNormal()
        window.resize(1100, 850)
        window.select_page(2)
        QTimer.singleShot(150, open_preview)
    else:
        output = {"date": "2026-10-17", "source_revision": "uncommitted working tree", "scope": "isolated native macOS Retro Review, maximized Dashboard and restored Cameras, no real devices", "results": results}
        Path(__file__).with_suffix(".json").write_text(json.dumps(output, indent=2) + "\n")
        print(json.dumps(output), flush=True)
        app.quit()


QTimer.singleShot(500, open_preview)
app.exec()
assert all(result["contained"] for result in results)
