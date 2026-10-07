"""Physical desktop coordinates without changing another thread's DPI policy."""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes


@contextmanager
def physical_coordinates() -> Iterator[None]:
    if sys.platform != "win32":
        yield
        return
    api = ctypes.WinDLL("user32", use_last_error=True)
    setter = api.SetThreadDpiAwarenessContext
    setter.argtypes = [ctypes.c_void_p]
    setter.restype = ctypes.c_void_p
    previous = setter(ctypes.c_void_p(-4))
    if not previous:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        setter(previous)


def operator_window_geometry(
    hwnd: int,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], float]:
    """Read the visible GUI frame and its monitor work area in physical pixels."""

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("monitor", wintypes.RECT),
            ("work", wintypes.RECT),
            ("flags", wintypes.DWORD),
        ]

    with physical_coordinates():
        api = ctypes.WinDLL("user32", use_last_error=True)
        api.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        api.MonitorFromWindow.restype = wintypes.HANDLE
        api.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        api.GetDpiForWindow.argtypes = [wintypes.HWND]
        api.GetDpiForWindow.restype = wintypes.UINT
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        monitor = api.MonitorFromWindow(hwnd, 2)
        if not api.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())

        def bounds(value: wintypes.RECT) -> tuple[int, int, int, int]:
            return (
                value.left,
                value.top,
                value.right - value.left,
                value.bottom - value.top,
            )

        return (
            bounds(_visible_frame(hwnd)),
            bounds(info.work),
            max(1.0, api.GetDpiForWindow(hwnd) / 96),
        )


def _visible_frame(hwnd: int) -> wintypes.RECT:
    api = ctypes.WinDLL("dwmapi", use_last_error=True)
    api.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    api.DwmGetWindowAttribute.restype = ctypes.c_long
    rect = wintypes.RECT()
    result = api.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    if result < 0:
        raise OSError(f"Cannot read visible window frame: HRESULT {result:#x}")
    return rect


def position_preview_frame(title: str, x: int, y: int) -> None:
    """Place this process's visible preview corner, excluding invisible borders."""
    with physical_coordinates():
        api = ctypes.WinDLL("user32", use_last_error=True)
        api.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        api.FindWindowW.restype = wintypes.HWND
        api.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        api.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        api.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        handle = api.FindWindowW(None, title)
        owner = wintypes.DWORD()
        if not handle or not api.GetWindowThreadProcessId(handle, ctypes.byref(owner)):
            raise ctypes.WinError(ctypes.get_last_error())
        if owner.value != os.getpid():
            raise RuntimeError("Preview placement targets another process's window")
        outer = wintypes.RECT()
        if not api.GetWindowRect(handle, ctypes.byref(outer)):
            raise ctypes.WinError(ctypes.get_last_error())
        visible = _visible_frame(handle)
        # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE preserves operator focus.
        if not api.SetWindowPos(
            handle,
            None,
            x - (visible.left - outer.left),
            y - (visible.top - outer.top),
            0,
            0,
            0x0015,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
