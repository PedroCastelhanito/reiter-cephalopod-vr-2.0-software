"""Shared-memory mapping attachment with page-exact descriptor size checks (A03)."""

from __future__ import annotations

import ctypes
import mmap
import sys
from ctypes import wintypes
from functools import lru_cache
from multiprocessing.shared_memory import SharedMemory
from typing import Any

from cephvr.platform.windows.security import owner_only_security_attributes


class MappingError(RuntimeError):
    """A named mapping is not a valid resource for the requested descriptor."""


class SharedMapping:
    def __init__(
        self,
        mapping: SharedMemory,
        *,
        owner: bool,
        expected_size: int,
        creation_handle: int | None = None,
    ) -> None:
        # Windows reports a mapping's size rounded up to whole pages, so the
        # tightest checkable size is the page-rounded declared layout.
        if expected_size <= 0 or mapping.size != _page_rounded(expected_size):
            mapping.close()
            raise MappingError("mapping size does not match its declared layout")
        self._mapping = mapping
        self._owner = owner
        self._creation_handle = creation_handle
        self.expected_size = expected_size
        self._closed = False

    @classmethod
    def create(cls, name: str, size: int) -> SharedMapping:
        _require_windows()
        if not name.startswith("Local\\cephvr-") or size <= 0:
            raise MappingError("mapping name or allocation size is invalid")
        kernel = _kernel32()
        security, backing = owner_only_security_attributes(SECTION_ACCESS)
        _ = backing
        ctypes.set_last_error(0)
        native_handle = kernel.CreateFileMappingW(
            ctypes.c_void_p(-1),
            ctypes.byref(security),
            PAGE_READWRITE,
            (size >> 32) & 0xFFFFFFFF,
            size & 0xFFFFFFFF,
            name,
        )
        if not native_handle:
            raise MappingError(f"CreateFileMappingW failed: {ctypes.get_last_error()}")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel.CloseHandle(native_handle)
            raise MappingError("mapping name already exists")
        try:
            mapping = SharedMemory(name=name, create=False)
        except BaseException:
            kernel.CloseHandle(native_handle)
            raise
        return cls(
            mapping,
            owner=True,
            expected_size=size,
            creation_handle=int(native_handle),
        )

    @classmethod
    def attach(cls, name: str, expected_size: int) -> SharedMapping:
        _require_windows()
        if not name.startswith("Local\\cephvr-") or expected_size <= 0:
            raise MappingError("mapping name or expected size is invalid")
        kernel = _kernel32()
        # CPython opens, sizes and closes the name before mapping it by tag, and
        # that final step silently creates a fresh mapping if the creator has
        # closed in between. Holding an open-only handle keeps the object alive.
        guard = kernel.OpenFileMappingW(
            SECTION_MAP_READ | SECTION_MAP_WRITE, False, name
        )
        if not guard:
            raise MappingError(
                f"named mapping does not exist: OpenFileMappingW {ctypes.get_last_error()}"
            )
        try:
            try:
                mapping = SharedMemory(name=name, create=False)
            except FileNotFoundError as exc:
                raise MappingError("named mapping does not exist") from exc
            return cls(mapping, owner=False, expected_size=expected_size)
        finally:
            # The attached view holds its own reference to the section.
            kernel.CloseHandle(guard)

    @property
    def name(self) -> str:
        return self._mapping.name

    @property
    def buffer(self) -> memoryview:
        if self._closed:
            raise MappingError("mapping is closed")
        buffer = self._mapping.buf
        if buffer is None:
            raise MappingError("mapping has no attached view")
        return buffer[: self.expected_size]

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._mapping.close()
        except BaseException as exc:
            raise MappingError(
                "mapping close failed; ownership remains available for retry"
            ) from exc
        creation_handle = self._creation_handle
        if creation_handle is not None:
            if not _kernel32().CloseHandle(creation_handle):
                raise MappingError(
                    f"mapping creator handle close failed: {ctypes.get_last_error()}"
                )
            self._creation_handle = None
        self._closed = True

    def retire(self) -> None:
        """Record local retirement; Windows mappings end when all handles close."""
        self.close()


def _require_windows() -> None:
    if sys.platform != "win32":
        raise MappingError("shared camera mappings require Windows")


def _page_rounded(size: int) -> int:
    return -(-size // mmap.PAGESIZE) * mmap.PAGESIZE


PAGE_READWRITE = 0x04
SECTION_MAP_READ = 0x0004
SECTION_MAP_WRITE = 0x0002
SECTION_QUERY = 0x0001
# CPython SharedMemory attaches through mmap(tagname=...), which requests all
# non-execute file-mapping rights even when the caller only reads/writes pixels.
SECTION_ACCESS = 0xF001F
ERROR_ALREADY_EXISTS = 183


@lru_cache(maxsize=1)
def _kernel32() -> Any:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileMappingW.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPCWSTR,
    ]
    kernel.CreateFileMappingW.restype = wintypes.HANDLE
    kernel.OpenFileMappingW.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel.OpenFileMappingW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel
