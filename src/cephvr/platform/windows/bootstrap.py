"""Restricted inherited Windows pipes for bootstrap secrets and launcher control."""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes
from typing import Any, TypeVar

from cephvr.platform.windows.jobs import WindowsLaunchError


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


_T = TypeVar("_T")


async def run_pipe_io_daemon(operation: Callable[[], _T], *, timeout_s: float) -> _T:
    """Bound event-loop waiting without leaving an unjoinable default-executor thread."""
    loop = asyncio.get_running_loop()
    completion: asyncio.Future[_T] = loop.create_future()

    def worker() -> None:
        try:
            result = operation()
        except BaseException as exc:
            try:
                loop.call_soon_threadsafe(_finish_error, exc)
            except RuntimeError:
                pass  # Owning process/event loop already exited after the timeout.
        else:
            try:
                loop.call_soon_threadsafe(_finish_result, result)
            except RuntimeError:
                pass

    def _finish_error(error: BaseException) -> None:
        if not completion.done():
            completion.set_exception(error)

    def _finish_result(result: _T) -> None:
        if not completion.done():
            completion.set_result(result)

    threading.Thread(target=worker, daemon=True, name="cephvr-pipe-io").start()
    return await asyncio.wait_for(completion, timeout=timeout_s)


def create_bootstrap_pipe() -> tuple[int, int]:
    if sys.platform != "win32":
        raise WindowsLaunchError("Windows bootstrap pipes require Windows")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreatePipe.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(_SECURITY_ATTRIBUTES),
        wintypes.DWORD,
    ]
    api.CreatePipe.restype = wintypes.BOOL
    api.SetHandleInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    api.SetHandleInformation.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    read, write = wintypes.HANDLE(), wintypes.HANDLE()
    attrs = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, True)
    if not api.CreatePipe(
        ctypes.byref(read), ctypes.byref(write), ctypes.byref(attrs), 0
    ):
        raise WindowsLaunchError(f"CreatePipe failed: {ctypes.get_last_error()}")
    if not api.SetHandleInformation(write, 1, 0):
        api.CloseHandle(read)
        api.CloseHandle(write)
        raise WindowsLaunchError(
            f"SetHandleInformation failed: {ctypes.get_last_error()}"
        )
    if read.value is None or write.value is None:
        raise WindowsLaunchError("CreatePipe returned a null handle")
    return int(read.value), int(write.value)


def create_control_pipe() -> tuple[int, int]:
    """Return noninherited launcher read handle and inherited supervisor write handle."""
    if sys.platform != "win32":
        raise WindowsLaunchError("Windows control pipes require Windows")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreatePipe.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(_SECURITY_ATTRIBUTES),
        wintypes.DWORD,
    ]
    api.CreatePipe.restype = wintypes.BOOL
    api.SetHandleInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    api.SetHandleInformation.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    read, write = wintypes.HANDLE(), wintypes.HANDLE()
    attrs = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, True)
    if not api.CreatePipe(
        ctypes.byref(read), ctypes.byref(write), ctypes.byref(attrs), 0
    ):
        raise WindowsLaunchError(f"CreatePipe failed: {ctypes.get_last_error()}")
    if not api.SetHandleInformation(read, 1, 0):
        api.CloseHandle(read)
        api.CloseHandle(write)
        raise WindowsLaunchError(
            f"SetHandleInformation failed: {ctypes.get_last_error()}"
        )
    if read.value is None or write.value is None:
        raise WindowsLaunchError("CreatePipe returned a null handle")
    return int(read.value), int(write.value)


def close_handle(handle: int) -> None:
    if sys.platform != "win32":
        raise WindowsLaunchError("Windows handles require Windows")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    if not api.CloseHandle(wintypes.HANDLE(handle)):
        raise WindowsLaunchError(f"CloseHandle failed: {ctypes.get_last_error()}")


def write_bootstrap(handle: int, document: dict[str, Any]) -> None:
    if sys.platform != "win32":
        raise WindowsLaunchError("Windows bootstrap pipes require Windows")
    import msvcrt

    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 64 * 1024:
        raise WindowsLaunchError("bootstrap document exceeds 64 KiB")
    fd = msvcrt.open_osfhandle(handle, 0)
    try:
        framed = len(encoded).to_bytes(4, "little") + encoded
        offset = 0
        while offset < len(framed):
            written = os.write(fd, framed[offset:])
            if written <= 0:
                raise WindowsLaunchError("bootstrap pipe closed during write")
            offset += written
    finally:
        os.close(fd)


def read_bootstrap(handle: int) -> dict[str, Any]:
    if sys.platform != "win32":
        raise WindowsLaunchError("Windows bootstrap pipes require Windows")
    import msvcrt

    fd = msvcrt.open_osfhandle(handle, 0)
    with open(fd, "rb", buffering=0) as stream:
        length_bytes = bytearray()
        while len(length_bytes) < 4:
            chunk = stream.read(4 - len(length_bytes))
            if not chunk:
                raise WindowsLaunchError("bootstrap pipe closed before length")
            length_bytes.extend(chunk)
        size = int.from_bytes(length_bytes, "little")
        if not 0 < size <= 64 * 1024:
            raise WindowsLaunchError("bootstrap document length invalid")
        payload = bytearray()
        while len(payload) < size:
            chunk = stream.read(size - len(payload))
            if not chunk:
                raise WindowsLaunchError("bootstrap pipe closed during document")
            payload.extend(chunk)
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise WindowsLaunchError("bootstrap document must be an object")
    return value
