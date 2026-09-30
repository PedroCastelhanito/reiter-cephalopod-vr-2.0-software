"""Public Win32 InterlockedCompareExchange64 operations for shared seqlock words."""

from __future__ import annotations

import ctypes
import sys
from typing import Any


class NativeAtomicError(RuntimeError):
    """The process cannot safely perform the required native atomic operation."""


_KERNEL32: Any = None


def _kernel32() -> Any:
    global _KERNEL32
    if sys.platform != "win32":
        raise NativeAtomicError("shared-ring atomics require Windows Interlocked APIs")
    if _KERNEL32 is None:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.InterlockedCompareExchange64.argtypes = [
            ctypes.POINTER(ctypes.c_longlong),
            ctypes.c_longlong,
            ctypes.c_longlong,
        ]
        kernel.InterlockedCompareExchange64.restype = ctypes.c_longlong
        _KERNEL32 = kernel
    return _KERNEL32


def _word(buffer: memoryview, offset: int) -> Any:
    if offset < 0 or offset + 8 > buffer.nbytes or offset % 8:
        raise NativeAtomicError("atomic word offset is out of range or unaligned")
    address = ctypes.addressof(ctypes.c_char.from_buffer(buffer, offset))
    if address % ctypes.alignment(ctypes.c_longlong):
        raise NativeAtomicError("atomic word address is not naturally aligned")
    return ctypes.cast(address, ctypes.POINTER(ctypes.c_longlong))


def atomic_load_u64(buffer: memoryview, offset: int) -> int:
    """Read atomically with the full fence supplied by InterlockedCompareExchange64."""
    value = int(_kernel32().InterlockedCompareExchange64(_word(buffer, offset), 0, 0))
    if value < 0:
        raise NativeAtomicError("native unsigned word exceeds supported signed range")
    return value


def atomic_compare_exchange_u64(
    buffer: memoryview, offset: int, expected: int, replacement: int
) -> bool:
    """Perform one documented full-fence CAS; never spin on an unexpected writer."""
    if not 0 <= expected <= 0x7FFFFFFFFFFFFFFF:
        raise NativeAtomicError("expected native word exceeds supported signed range")
    if not 0 <= replacement <= 0x7FFFFFFFFFFFFFFF:
        raise NativeAtomicError("replacement exceeds supported nonwrapping range")
    observed = int(
        _kernel32().InterlockedCompareExchange64(
            _word(buffer, offset), replacement, expected
        )
    )
    if observed < 0:
        raise NativeAtomicError("native word exceeds supported signed range")
    return observed == expected


def atomic_store_u64(
    buffer: memoryview, offset: int, expected: int, value: int
) -> None:
    """Store only if the caller's single-writer snapshot is still current."""
    if not atomic_compare_exchange_u64(buffer, offset, expected, value):
        raise NativeAtomicError("single-writer atomic value changed unexpectedly")


def atomic_increment_u64(buffer: memoryview, offset: int) -> int:
    """Increment a single-writer word with one bounded CAS."""
    observed = atomic_load_u64(buffer, offset)
    if observed >= 0x7FFFFFFFFFFFFFFF:
        raise NativeAtomicError("native atomic counter exhausted")
    replacement = observed + 1
    atomic_store_u64(buffer, offset, observed, replacement)
    return replacement
