"""Isolated native presentation probe; no camera, controller or saved GUI state."""

import ctypes
import json
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from PyQt6.QtCore import QPoint, QSettings
from PyQt6.QtWidgets import QApplication

from cephvr.gui.preview_placement import preview_window_placement
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
from cephvr.platform.windows.window_coordinates import (
    client_point_to_screen,
    operator_window_geometry,
    physical_coordinates,
    position_preview_frame,
)

root = Path(__file__).resolve().parent
app = QApplication([])
apply_theme(app)
settings = QSettings(str(root / "probe.ini"), QSettings.Format.IniFormat)
window = DashboardWindow(settings=settings)
window.select_page(2)
api = ctypes.WinDLL("user32")
api.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
api.FindWindowW.restype = ctypes.c_void_p
api.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
title = f"CephVR isolated slot {uuid4()}"
results = []
try:
    for maximized, width in ((True, 1920), (False, 1200)):
        if maximized:
            window.showMaximized()
        else:
            window.showNormal()
            window.resize(width, 940)
        for _ in range(5):
            app.processEvents()
        placement = preview_window_placement(window)
        with physical_coordinates():
            cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)
            cv2.imshow(title, np.zeros((placement.side, placement.side), np.uint8))
            cv2.waitKey(20)
            position_preview_frame(title, placement.x, placement.y)
            window.raise_()
            window.activateWindow()
            app.processEvents()
            cv2.waitKey(20)
            hwnd = api.FindWindowW(None, title)
            frame, _, scale = operator_window_geometry(hwnd)
            target = window.preview_slot.target
            offset = target.mapTo(window, QPoint())
            expected = client_point_to_screen(
                int(window.winId()), round(offset.x() * scale), round(offset.y() * scale)
            )
            assert frame[:2] == expected == (placement.x, placement.y)
            assert frame[2:] == (
                round(target.width() * scale), round(target.height() * scale)
            )
            assert api.GetWindowLongW(hwnd, -20) & 8
            results.append({"maximized": maximized, "frame": frame, "side": placement.side,
                            "scale": scale, "topmost_after_gui_activation": True})
            window.grab().save(str(root / f"fitted-slot-{width}.png"))
            cv2.destroyWindow(title)
            cv2.waitKey(1)
    (root / "native-slot-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results))
finally:
    cv2.destroyAllWindows()
    window.close()
    app.processEvents()
