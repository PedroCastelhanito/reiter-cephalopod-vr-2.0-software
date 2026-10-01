"""Resolve a saved monitor interface identity through the active Windows display map."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class _DisplayDevice(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


def monitor_interface(adapter_name: str, monitor_name: str) -> str:
    """Return EDD_GET_DEVICE_INTERFACE_NAME identity, never a friendly-name match."""
    if sys.platform != "win32":
        raise RuntimeError("physical display identity requires Windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    enumerate_device = user32.EnumDisplayDevicesW
    enumerate_device.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(_DisplayDevice),
        wintypes.DWORD,
    ]
    enumerate_device.restype = wintypes.BOOL
    found = []
    index = 0
    while True:
        device = _DisplayDevice()
        device.cb = ctypes.sizeof(device)
        if not enumerate_device(adapter_name, index, ctypes.byref(device), 1):
            break
        if device.DeviceName.casefold() == monitor_name.casefold():
            found.append(str(device.DeviceID))
        index += 1
    if len(found) != 1 or not found[0]:
        raise RuntimeError(
            "active GLFW monitor lacks a unique Windows interface identity"
        )
    return found[0]
