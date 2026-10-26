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


def client_point_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Map a physical client offset without assuming monitor or frame origins."""
    with physical_coordinates():
        api = ctypes.WinDLL("user32", use_last_error=True)
        api.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        point = wintypes.POINT(x, y)
        if not api.ClientToScreen(hwnd, ctypes.byref(point)):
            raise ctypes.WinError(ctypes.get_last_error())
        return point.x, point.y


def preview_frame_extra(scale: float = 1.0) -> tuple[int, int]:
    """Visible Win32 HighGUI chrome around an autosized square image."""
    if sys.platform != "win32":
        return round(2 * scale), round(32 * scale)
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
    dpi = round(96 * scale)
    metric = api.GetSystemMetricsForDpi
    # Visible border, caption, and top resize frame; DWM hides the other padding.
    return 2 * metric(5, dpi), sum(metric(key, dpi) for key in (4, 33, 92, 6))


def preview_window_handle(title: str) -> int:
    """Return this process's window with an exact title; resolve before blanking it."""
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    api.FindWindowW.restype = wintypes.HWND
    api.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    handle = api.FindWindowW(None, title)
    owner = wintypes.DWORD()
    if not handle or not api.GetWindowThreadProcessId(handle, ctypes.byref(owner)):
        raise ctypes.WinError(ctypes.get_last_error())
    if owner.value != os.getpid():
        raise RuntimeError("Preview placement targets another process's window")
    return int(handle)


def blank_preview_caption(handle: int) -> None:
    """Clear caption text/icon while retaining native move/resize/close controls."""
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    api.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    api.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    api.SendMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    api.SendMessageW.restype = ctypes.c_ssize_t
    api.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    if not api.SetWindowTextW(handle, ""):
        raise ctypes.WinError(ctypes.get_last_error())
    style = api.GetWindowLongW(handle, -20)
    ctypes.set_last_error(0)
    # Suppress the default class-icon fallback without removing the system menu.
    if (
        not api.SetWindowLongW(handle, -20, style | 0x00000001)
        and ctypes.get_last_error()
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    api.SendMessageW(handle, 0x0080, 0, 0)  # WM_SETICON / ICON_SMALL
    api.SendMessageW(handle, 0x0080, 1, 0)  # ICON_BIG
    if not api.SetWindowPos(handle, None, 0, 0, 0, 0, 0x0037):
        raise ctypes.WinError(ctypes.get_last_error())


def position_preview_frame(
    window: str | int, x: int, y: int, *, topmost: bool = True
) -> None:
    """Place this process's visible preview corner, excluding invisible borders.

    A title resolves the window; once the caption is blank, callers pass its handle.
    """
    handle = preview_window_handle(window) if isinstance(window, str) else window
    with physical_coordinates():
        api = ctypes.WinDLL("user32", use_last_error=True)
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
        owner = wintypes.DWORD()
        if not api.GetWindowThreadProcessId(handle, ctypes.byref(owner)):
            raise ctypes.WinError(ctypes.get_last_error())
        if owner.value != os.getpid():
            raise RuntimeError("Preview placement targets another process's window")
        outer = wintypes.RECT()
        if not api.GetWindowRect(handle, ctypes.byref(outer)):
            raise ctypes.WinError(ctypes.get_last_error())
        visible = _visible_frame(handle)
        # HWND_TOPMOST keeps the detached viewer above the GUI without activation.
        if not api.SetWindowPos(
            handle,
            wintypes.HWND(-1 if topmost else -2),
            x - (visible.left - outer.left),
            y - (visible.top - outer.top),
            0,
            0,
            0x0011,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
