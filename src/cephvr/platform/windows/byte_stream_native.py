"""Cached Win32 ABI declarations shared by byte-stream construction and I/O."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

from cephvr.platform.windows.jobs import WindowsLaunchError
from cephvr.platform.windows.security import SecurityAttributes

ERROR_IO_PENDING = 997
ERROR_IO_INCOMPLETE = 996
ERROR_NOT_FOUND = 1168
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
WAIT_FAILED = 0xFFFFFFFF
_NATIVE_API: ctypes.WinDLL | None = None


class Overlapped(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


@dataclass
class NativePendingIO:
    event: int
    overlapped: Overlapped
    buffer: ctypes.Array[ctypes.c_char]
    writing: bool
    deadline_ns: int
    backing: bytearray | None = None
    completed: bool = False
    transferred: int | None = None
    error_code: int | None = None
    late: bool = False
    cancel_requested: bool = False


def native_api() -> ctypes.WinDLL:
    global _NATIVE_API
    if sys.platform != "win32":
        raise WindowsLaunchError("native byte stream requires Windows")
    if _NATIVE_API is not None:
        return _NATIVE_API
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateNamedPipeW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(SecurityAttributes),
    ]
    api.CreateNamedPipeW.restype = wintypes.HANDLE
    api.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(SecurityAttributes),
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    api.CreateFileW.restype = wintypes.HANDLE
    api.SetNamedPipeHandleState.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    api.SetNamedPipeHandleState.restype = wintypes.BOOL
    api.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    api.WaitNamedPipeW.restype = wintypes.BOOL
    api.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.POINTER(Overlapped)]
    api.ConnectNamedPipe.restype = wintypes.BOOL
    api.SetHandleInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    api.SetHandleInformation.restype = wintypes.BOOL
    api.CreateEventW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    api.CreateEventW.restype = wintypes.HANDLE
    api.WriteFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(Overlapped),
    ]
    api.WriteFile.restype = wintypes.BOOL
    api.ReadFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(Overlapped),
    ]
    api.ReadFile.restype = wintypes.BOOL
    api.GetOverlappedResult.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(Overlapped),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
    ]
    api.GetOverlappedResult.restype = wintypes.BOOL
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.WaitForMultipleObjects.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    api.WaitForMultipleObjects.restype = wintypes.DWORD
    api.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(Overlapped)]
    api.CancelIoEx.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    _NATIVE_API = api
    return api


def check(handle: int, name: str) -> None:
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise WindowsLaunchError(f"{name} failed: WinError {ctypes.get_last_error()}")


def wait_ms(remaining_ns: int) -> int:
    if remaining_ns <= 0:
        return 0
    return min((remaining_ns + 999_999) // 1_000_000, 0xFFFFFFFE)
