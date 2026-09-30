"""Exact-identity Windows frame-log and MP4 storage synchronization (A07/A08)."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast

from cephvr.platform.windows.jobs import WindowsLaunchError

GENERIC_WRITE = 0x40000000
DELETE = 0x00010000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_NATIVE_API: ctypes.WinDLL | None = None


class _BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]


class _FILE_DISPOSITION_INFO(ctypes.Structure):
    _fields_ = [("DeleteFile", ctypes.c_ubyte)]


@dataclass(frozen=True)
class WindowsFileIdentity:
    volume_serial: int
    file_index: int


@dataclass(eq=False)
class _OwnedHandle:
    value: int
    closed: bool = False


class WindowsFileSyncOwner:
    """Per-worker owner for storage handles whose close needs reconciliation."""

    def __init__(self) -> None:
        self._uncertain_handles: set[_OwnedHandle] = set()

    @property
    def cleanup_blocked(self) -> bool:
        return bool(self._uncertain_handles)

    def close_handle(self, handle: _OwnedHandle) -> None:
        if handle.closed:
            return
        if not _api().CloseHandle(handle.value):
            self._uncertain_handles.add(handle)
            raise WindowsLaunchError(
                f"closing recording handle failed: WinError {ctypes.get_last_error()}"
            )
        handle.closed = True
        self._uncertain_handles.discard(handle)

    def retry_cleanup(self) -> None:
        for handle in tuple(self._uncertain_handles):
            if not _api().CloseHandle(handle.value):
                raise WindowsLaunchError(
                    f"recording handle cleanup remains uncertain: WinError {ctypes.get_last_error()}"
                )
            handle.closed = True
            self._uncertain_handles.remove(handle)

    def identity_for_path(self, path: Path) -> WindowsFileIdentity | None:
        if self.cleanup_blocked:
            raise WindowsLaunchError("recording storage cleanup blocks new handles")
        return _identity_for_path(path, self)


class WindowsFrameLogSync:
    """Flush Python's buffered file, then the verified underlying Windows handle."""

    def sync(self, file_object: object) -> None:
        _require_windows()
        if not hasattr(file_object, "flush") or not hasattr(file_object, "fileno"):
            raise TypeError("frame-log sync requires an open binary file object")
        binary_file = cast(BinaryIO, file_object)
        binary_file.flush()
        import msvcrt

        handle = msvcrt.get_osfhandle(binary_file.fileno())
        _flush(int(handle))


class WindowsVideoSync:
    """Nontruncating sync handle for the exact MP4 file opened by FFmpeg."""

    def __init__(
        self, handle: int, identity: WindowsFileIdentity, owner: WindowsFileSyncOwner
    ) -> None:
        self._handle = _OwnedHandle(handle)
        self.file_identity = identity
        self.owner = owner

    @property
    def closed(self) -> bool:
        return self._handle.closed

    def sync(self) -> None:
        if self._handle.closed:
            raise WindowsLaunchError("video sync handle is closed")
        _flush(self._handle.value)

    def close(self) -> None:
        if not self._handle.closed:
            self.owner.close_handle(self._handle)


class WindowsVideoSyncFactory:
    """Open one shared, nontruncating GENERIC_WRITE handle after encoder creation."""

    def __init__(self, owner: WindowsFileSyncOwner) -> None:
        self.owner = owner

    def identity(self, path: Path) -> WindowsFileIdentity | None:
        return self.owner.identity_for_path(path)

    def open(self, path: Path, expected_identity: object) -> WindowsVideoSync:
        _require_windows()
        if self.owner.cleanup_blocked:
            raise WindowsLaunchError("recording storage cleanup blocks new handles")
        if not isinstance(expected_identity, WindowsFileIdentity):
            raise TypeError("expected Windows file identity is required")
        if path.is_symlink():
            raise WindowsLaunchError("video sync refuses an output symlink")
        handle = _api().CreateFileW(
            str(path),
            GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            raise WindowsLaunchError(
                f"opening video synchronization handle failed: WinError {ctypes.get_last_error()}"
            )
        try:
            actual = identity_for_handle(int(handle))
            if actual != expected_identity:
                raise WindowsLaunchError(
                    "video path identity differs from encoder-owned file"
                )
            return WindowsVideoSync(int(handle), actual, self.owner)
        except BaseException as exc:
            try:
                self.owner.close_handle(_OwnedHandle(int(handle)))
            except BaseException as close_error:
                raise close_error from exc
            raise

    def delete_exact(
        self, path: Path, expected_identity: object, *, deadline_ns: int
    ) -> bool:
        """Delete only an exact observed file through its verified open handle."""
        _require_windows()
        if self.owner.cleanup_blocked:
            raise WindowsLaunchError("recording storage cleanup blocks deletion")
        if not isinstance(expected_identity, WindowsFileIdentity):
            raise TypeError("expected Windows file identity is required")
        if time.perf_counter_ns() >= deadline_ns:
            raise TimeoutError("exact output deletion deadline already expired")
        handle = _api().CreateFileW(
            str(path),
            DELETE,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            error = ctypes.get_last_error()
            if error in {2, 3}:
                if time.perf_counter_ns() > deadline_ns:
                    raise TimeoutError(
                        "exact output absence was observed after its deadline"
                    )
                return True
            raise WindowsLaunchError(
                f"opening exact output for deletion failed: WinError {error}"
            )
        owned = _OwnedHandle(int(handle))
        try:
            actual = identity_for_handle(owned.value)
            if actual != expected_identity:
                return False
            disposition = _FILE_DISPOSITION_INFO(True)
            if not _api().SetFileInformationByHandle(
                owned.value,
                4,  # FileDispositionInfo
                ctypes.byref(disposition),
                ctypes.sizeof(disposition),
            ):
                raise WindowsLaunchError(
                    "marking exact recording output for deletion failed: "
                    f"WinError {ctypes.get_last_error()}"
                )
        finally:
            self.owner.close_handle(owned)
        if time.perf_counter_ns() > deadline_ns:
            raise TimeoutError("exact output deletion completed after its deadline")
        absent = self.identity(path) is None
        if time.perf_counter_ns() > deadline_ns:
            raise TimeoutError("exact output absence check completed after deadline")
        return absent


def _identity_for_path(
    path: Path, owner: WindowsFileSyncOwner
) -> WindowsFileIdentity | None:
    _require_windows()
    handle = _api().CreateFileW(
        str(path),
        0,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        if error in {2, 3}:
            return None
        raise WindowsLaunchError(
            f"opening output for identity check failed: WinError {error}"
        )
    owned = _OwnedHandle(int(handle))
    try:
        actual = identity_for_handle(owned.value)
    except BaseException as exc:
        try:
            owner.close_handle(owned)
        except BaseException as close_error:
            raise close_error from exc
        raise
    owner.close_handle(owned)
    return actual


def identity_for_handle(handle: int) -> WindowsFileIdentity:
    information = _BY_HANDLE_FILE_INFORMATION()
    if not _api().GetFileInformationByHandle(handle, ctypes.byref(information)):
        raise WindowsLaunchError(
            f"GetFileInformationByHandle failed: WinError {ctypes.get_last_error()}"
        )
    if information.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT:
        raise WindowsLaunchError(
            "recording output handle resolves through a reparse point"
        )
    if information.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY:
        raise WindowsLaunchError("recording output handle is a directory")
    return WindowsFileIdentity(
        int(information.dwVolumeSerialNumber),
        (int(information.nFileIndexHigh) << 32) | int(information.nFileIndexLow),
    )


def _flush(handle: int) -> None:
    if not _api().FlushFileBuffers(handle):
        raise WindowsLaunchError(
            f"FlushFileBuffers failed: WinError {ctypes.get_last_error()}"
        )


def _api() -> ctypes.WinDLL:
    global _NATIVE_API
    _require_windows()
    if _NATIVE_API is not None:
        return _NATIVE_API
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    api.CreateFileW.restype = wintypes.HANDLE
    api.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_BY_HANDLE_FILE_INFORMATION),
    ]
    api.GetFileInformationByHandle.restype = wintypes.BOOL
    api.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    api.SetFileInformationByHandle.restype = wintypes.BOOL
    api.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    api.FlushFileBuffers.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    _NATIVE_API = api
    return api


def _require_windows() -> None:
    if sys.platform != "win32":
        raise WindowsLaunchError("recording storage sync requires Windows")
