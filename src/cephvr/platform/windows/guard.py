"""Machine-wide OS single-instance guards for E08 process roles."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from cephvr.platform.windows.jobs import WindowsLaunchError


class SingleInstanceGuard:
    def __init__(self, role: str) -> None:
        if sys.platform != "win32":
            raise WindowsLaunchError("machine-wide process guards require Windows")
        if not role or not all(c.isalnum() or c in "-_" for c in role):
            raise ValueError("invalid guarded role")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self.api.CreateMutexW.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        ctypes.set_last_error(0)
        self.handle = self.api.CreateMutexW(None, False, f"Global\\CephVR2-{role}")
        if not self.handle:
            raise WindowsLaunchError(f"CreateMutexW failed: {ctypes.get_last_error()}")
        if ctypes.get_last_error() == 183:
            self.api.CloseHandle(self.handle)
            self.handle = None
            raise WindowsLaunchError(f"{role} instance already running")

    def close(self) -> None:
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> SingleInstanceGuard:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
