"""Update a live COM write budget without reconfiguring baud or control lines."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from functools import lru_cache
from typing import Any


class _CommTimeouts(ctypes.Structure):
    _fields_ = [
        ("ReadIntervalTimeout", wintypes.DWORD),
        ("ReadTotalTimeoutMultiplier", wintypes.DWORD),
        ("ReadTotalTimeoutConstant", wintypes.DWORD),
        ("WriteTotalTimeoutMultiplier", wintypes.DWORD),
        ("WriteTotalTimeoutConstant", wintypes.DWORD),
    ]


def set_write_timeout(handle: int, seconds: float) -> None:
    """Keep read settings and bound an overlapped write to whole milliseconds."""
    milliseconds = int(seconds * 1000)
    if milliseconds < 1:
        raise TimeoutError("serial write budget is shorter than one native tick")
    kernel = _kernel32()
    timeouts = _CommTimeouts()
    if not kernel.GetCommTimeouts(handle, ctypes.byref(timeouts)):
        raise ctypes.WinError(ctypes.get_last_error())
    timeouts.WriteTotalTimeoutMultiplier = 0
    timeouts.WriteTotalTimeoutConstant = min(milliseconds, 0xFFFFFFFE)
    if not kernel.SetCommTimeouts(handle, ctypes.byref(timeouts)):
        raise ctypes.WinError(ctypes.get_last_error())


@lru_cache(maxsize=1)
def _kernel32() -> Any:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    for name in ("GetCommTimeouts", "SetCommTimeouts"):
        function = getattr(kernel, name)
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(_CommTimeouts)]
        function.restype = wintypes.BOOL
    return kernel
