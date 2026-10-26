"""Image-overlay camera controls; native chrome never changes on hover."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

from cephvr.platform.windows.window_coordinates import (
    _visible_frame,
    physical_coordinates,
)


class HoverPreviewCaption:
    height = 28

    def __init__(self, handle: int) -> None:
        self.handle = handle
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        self.user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user.GetAsyncKeyState.restype = ctypes.c_short
        self.user.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        self.user.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        self.user.ReleaseCapture.argtypes = []
        style = self.user.GetWindowLongW(handle, -16)
        ctypes.set_last_error(0)
        if (
            not self.user.SetWindowLongW(handle, -16, style & ~0x00C40000)
            and ctypes.get_last_error()
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.user.SetWindowPos(handle, None, 0, 0, 0, 0, 0x0037):
            raise ctypes.WinError(ctypes.get_last_error())
        self.shown = False

    def sync(self) -> bool:
        with physical_coordinates():
            point = wintypes.POINT()
            if not self.user.GetCursorPos(ctypes.byref(point)):
                raise ctypes.WinError(ctypes.get_last_error())
            rect = _visible_frame(self.handle)
            hovered = (
                rect.left <= point.x < rect.right and rect.top <= point.y < rect.bottom
            )
            if self.user.GetAsyncKeyState(1) & 0x8000:
                return False
            return self._show(hovered)

    def _show(self, shown: bool) -> bool:
        changed = shown != self.shown
        self.shown = shown
        return changed

    def draw(self, image: Any, cv: Any) -> Any:
        """Paint only the private display image, without changing its dimensions."""
        if self.shown:
            side = image.shape[1]
            cv.rectangle(image, (0, 0), (side - 1, self.height - 1), (35, 35, 35), -1)
            cv.putText(
                image,
                "Drag",
                (8, 19),
                cv.FONT_HERSHEY_SIMPLEX,
                0.45,
                (230, 230, 230),
                1,
                cv.LINE_AA,
            )
            cv.putText(
                image,
                "X",
                (side - 21, 19),
                cv.FONT_HERSHEY_SIMPLEX,
                0.45,
                (230, 230, 230),
                1,
                cv.LINE_AA,
            )
        return image

    def press(self, x: int, y: int, side: int) -> bool:
        """Consume overlay clicks; dispatch move/close through the native owner."""
        if not self.shown or not 0 <= y < self.height:
            return False
        with physical_coordinates():
            point = wintypes.POINT()
            if not self.user.GetCursorPos(ctypes.byref(point)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.user.ReleaseCapture()
            message, hit = (0x0010, 0) if x >= side - self.height else (0x00A1, 2)
            position = (point.x & 0xFFFF) | ((point.y & 0xFFFF) << 16)
            if not self.user.PostMessageW(self.handle, message, hit, position):
                raise ctypes.WinError(ctypes.get_last_error())
        return True
