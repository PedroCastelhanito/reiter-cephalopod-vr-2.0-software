"""Owner-only, auto-reset Win32 named events for acquisition shared rings."""

from __future__ import annotations

import ctypes
import sys
import uuid
from ctypes import wintypes
from functools import lru_cache
from typing import Any

from cephvr.platform.windows.security import owner_only_security_attributes

SYNCHRONIZE = 0x00100000
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF
ERROR_ALREADY_EXISTS = 183
EVENT_MANUAL_RESET = 0x00000100


class NativeEventError(RuntimeError):
    """A named event could not be created, opened, signaled or waited on."""


def event_name(allocation_id: uuid.UUID) -> str:
    return f"Local\\cephvr-{allocation_id}-event"


class AutoResetEvent:
    def __init__(self, handle: int) -> None:
        self._handle = handle
        self._closed = False

    @classmethod
    def create(cls, allocation_id: uuid.UUID) -> AutoResetEvent:
        kernel = _kernel32()
        security, backing = owner_only_security_attributes(
            SYNCHRONIZE | EVENT_MODIFY_STATE
        )
        _ = backing
        ctypes.set_last_error(0)
        handle = kernel.CreateEventW(
            ctypes.byref(security), False, False, event_name(allocation_id)
        )
        if not handle:
            raise NativeEventError(f"CreateEventW failed: {ctypes.get_last_error()}")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel.CloseHandle(handle)
            raise NativeEventError("ring event name already exists")
        return cls(int(handle))

    @classmethod
    def open(cls, name: str, allocation_id: uuid.UUID) -> AutoResetEvent:
        if name != event_name(allocation_id):
            raise NativeEventError("event name does not match allocation identity")
        kernel = _kernel32()
        handle = kernel.OpenEventW(SYNCHRONIZE | EVENT_MODIFY_STATE, False, name)
        if not handle:
            raise NativeEventError(f"OpenEventW failed: {ctypes.get_last_error()}")
        return cls(int(handle))

    def set(self) -> None:
        kernel = _kernel32()
        if self._closed or not kernel.SetEvent(self._handle):
            raise NativeEventError(f"SetEvent failed: {ctypes.get_last_error()}")

    def wait(self, timeout_ns: int) -> bool:
        if timeout_ns < 0:
            raise ValueError("event wait timeout must be nonnegative")
        if self._closed:
            raise NativeEventError("event handle is closed")
        timeout_ms = min((timeout_ns + 999_999) // 1_000_000, INFINITE - 1)
        result = _kernel32().WaitForSingleObject(self._handle, timeout_ms)
        if result == WAIT_OBJECT_0:
            return True
        if result == WAIT_TIMEOUT:
            return False
        raise NativeEventError(f"WaitForSingleObject failed: {ctypes.get_last_error()}")

    def close(self) -> None:
        if self._closed:
            return
        if not _kernel32().CloseHandle(self._handle):
            raise NativeEventError(f"CloseHandle failed: {ctypes.get_last_error()}")
        self._closed = True

    def __enter__(self) -> AutoResetEvent:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class ManualResetEvent:
    """Private control wakeup shared by the camera owner and command handlers."""

    def __init__(self, handle: int) -> None:
        self._handle = handle
        self._closed = False

    @classmethod
    def create(cls) -> ManualResetEvent:
        kernel = _kernel32()
        security, backing = owner_only_security_attributes(
            SYNCHRONIZE | EVENT_MODIFY_STATE
        )
        _ = backing
        handle = kernel.CreateEventW(ctypes.byref(security), True, False, None)
        if not handle:
            raise NativeEventError(f"CreateEventW failed: {ctypes.get_last_error()}")
        return cls(int(handle))

    @property
    def native_handle(self) -> int:
        if self._closed:
            raise NativeEventError("event handle is closed")
        return self._handle

    def set(self) -> None:
        if self._closed or not _kernel32().SetEvent(self._handle):
            raise NativeEventError(f"SetEvent failed: {ctypes.get_last_error()}")

    def clear(self) -> None:
        if self._closed or not _kernel32().ResetEvent(self._handle):
            raise NativeEventError(f"ResetEvent failed: {ctypes.get_last_error()}")

    def wait(self, timeout_ns: int) -> bool:
        if timeout_ns < 0:
            raise ValueError("event wait timeout must be nonnegative")
        if self._closed:
            raise NativeEventError("event handle is closed")
        timeout_ms = min((timeout_ns + 999_999) // 1_000_000, INFINITE - 1)
        result = _kernel32().WaitForSingleObject(self._handle, timeout_ms)
        if result == WAIT_OBJECT_0:
            return True
        if result == WAIT_TIMEOUT:
            return False
        raise NativeEventError(f"WaitForSingleObject failed: {ctypes.get_last_error()}")

    def is_set(self) -> bool:
        if self._closed:
            raise NativeEventError("event handle is closed")
        result = _kernel32().WaitForSingleObject(self._handle, 0)
        if result == WAIT_OBJECT_0:
            return True
        if result == WAIT_TIMEOUT:
            return False
        raise NativeEventError(f"WaitForSingleObject failed: {ctypes.get_last_error()}")

    def close(self) -> None:
        if self._closed:
            return
        if not _kernel32().CloseHandle(self._handle):
            raise NativeEventError(f"CloseHandle failed: {ctypes.get_last_error()}")
        self._closed = True


@lru_cache(maxsize=1)
def _kernel32() -> Any:
    if sys.platform != "win32":
        raise NativeEventError("native ring events require Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateEventW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenEventW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.SetEvent.argtypes = [wintypes.HANDLE]
    kernel.SetEvent.restype = wintypes.BOOL
    kernel.ResetEvent.argtypes = [wintypes.HANDLE]
    kernel.ResetEvent.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    return kernel
