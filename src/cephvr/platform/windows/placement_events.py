"""Observe operator move/resize completion on the native window's owning thread."""

import ctypes
from ctypes import wintypes


class PlacementEvents:
    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self.revision = 0
        self.api = ctypes.WinDLL("comctl32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
        )
        self.callback = callback_type(self._dispatch)
        self.api.SetWindowSubclass.argtypes = [
            wintypes.HWND,
            callback_type,
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        self.api.RemoveWindowSubclass.argtypes = [
            wintypes.HWND,
            callback_type,
            ctypes.c_size_t,
        ]
        self.api.DefSubclassProc.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        self.api.DefSubclassProc.restype = ctypes.c_ssize_t
        if not self.api.SetWindowSubclass(hwnd, self.callback, id(self), 0):
            raise ctypes.WinError(ctypes.get_last_error())

    def _dispatch(
        self,
        hwnd: int,
        message: int,
        wparam: int,
        lparam: int,
        subclass: int,
        reference: int,
    ) -> int:
        if message == 0x0232:  # WM_EXITSIZEMOVE; DPI/automatic layout does not emit it.
            self.revision += 1
        return int(self.api.DefSubclassProc(hwnd, message, wparam, lparam))

    def close(self, alive: bool) -> None:
        if alive and not self.api.RemoveWindowSubclass(
            self.hwnd, self.callback, id(self)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
