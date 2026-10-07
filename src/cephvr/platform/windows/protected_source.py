"""Protected Windows asset reads for Visual Stimulus and Tracking; never silently
fall back to pathname reads."""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import BinaryIO


class ProtectedSourceError(OSError):
    pass


class ProtectedWindowsSource:
    """Retains a non-shareable Windows read handle for the prepared lifetime."""

    def __init__(self, path: Path) -> None:
        if sys.platform != "win32":
            raise ProtectedSourceError(
                "protected Visual Stimulus assets require Windows"
            )
        self.path = path.resolve(strict=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        self._kernel = kernel
        self._handle = kernel.CreateFileW(
            str(self.path), 0x80000000, 0x1, None, 3, 0x80, None
        )
        if self._handle in (None, wintypes.HANDLE(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        self._closed = False
        try:
            self._identity = self._file_identity(self._handle)
        except BaseException:
            self._kernel.CloseHandle(self._handle)
            self._closed = True
            raise

    @staticmethod
    def _file_identity(handle: int) -> tuple[int, int, int]:
        class _Info(ctypes.Structure):
            _fields_ = [
                ("attributes", wintypes.DWORD),
                ("creation_low", wintypes.DWORD),
                ("creation_high", wintypes.DWORD),
                ("access_low", wintypes.DWORD),
                ("access_high", wintypes.DWORD),
                ("write_low", wintypes.DWORD),
                ("write_high", wintypes.DWORD),
                ("volume", wintypes.DWORD),
                ("size_high", wintypes.DWORD),
                ("size_low", wintypes.DWORD),
                ("links", wintypes.DWORD),
                ("index_high", wintypes.DWORD),
                ("index_low", wintypes.DWORD),
            ]

        info = _Info()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        fn = kernel.GetFileInformationByHandle
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Info)]
        fn.restype = wintypes.BOOL
        if not fn(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return info.volume, info.index_high, info.index_low

    @property
    def identity(self) -> tuple[int, int, int]:
        self._ensure_open()
        return self._identity

    def _ensure_open(self) -> None:
        if self._closed:
            raise ProtectedSourceError("protected source is closed")

    def independent_reader(self) -> BinaryIO:
        self._ensure_open()
        import msvcrt

        handle = self._kernel.CreateFileW(
            str(self.path), 0x80000000, 0x1, None, 3, 0x80, None
        )
        if handle in (None, wintypes.HANDLE(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if self._file_identity(handle) != self._identity:
                raise ProtectedSourceError("independent source identity changed")
            fd = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | os.O_BINARY)
        except BaseException:
            self._kernel.CloseHandle(handle)
            raise
        try:
            return os.fdopen(fd, "rb")
        except BaseException:
            os.close(fd)
            raise

    def close_after_consumers(self) -> None:
        if not self._closed:
            if not self._kernel.CloseHandle(self._handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._closed = True

    def __enter__(self) -> ProtectedWindowsSource:
        return self

    def __exit__(self, *_: object) -> None:
        self.close_after_consumers()
