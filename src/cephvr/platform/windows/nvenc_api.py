"""Pinned NVENC 12.2.72 ABI definitions and narrow function helpers."""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from typing import cast

_API_VERSION = 12 | (2 << 24)
_SUCCESS = 0


class NvencQueryError(RuntimeError):
    pass


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_text(cls, text: str) -> _Guid:
        import uuid

        parsed = uuid.UUID(text)
        raw = parsed.bytes_le
        return cls.from_buffer_copy(raw)

    def text(self) -> str:
        import uuid

        return str(uuid.UUID(bytes_le=bytes(self)))


class _OpenSessionEx(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("device_type", ctypes.c_int),
        ("device", ctypes.c_void_p),
        ("reserved", ctypes.c_void_p),
        ("api_version", ctypes.c_uint32),
        ("reserved1", ctypes.c_uint32 * 253),
        ("reserved2", ctypes.c_void_p * 64),
    ]


class _CapsParam(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("caps_to_query", ctypes.c_int),
        ("reserved", ctypes.c_uint32 * 62),
    ]


# Fields before/through lookahead in NV_ENCODE_API_FUNCTION_LIST v12.2.72.0.
# Using an opaque pointer array keeps this narrow binding independent of the
# signatures for functions that this module never calls.
class _FunctionList(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("functions", ctypes.c_void_p * 43),
        ("reserved2", ctypes.c_void_p * 275),
    ]


def _function(
    function_list: _FunctionList, index: int, argtypes: list[object]
) -> Callable[..., int]:
    address = function_list.functions[index]
    if not address:
        raise NvencQueryError(f"NVENC API function slot {index} is unavailable")
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int, *argtypes)  # type: ignore[arg-type]
    return cast(Callable[..., int], prototype(address))


def _struct_version(version: int) -> int:
    return _API_VERSION | (version << 16) | (0x7 << 28)


def _nv_check(status: int, operation: str) -> None:
    if status != _SUCCESS:
        raise NvencQueryError(f"{operation} failed with NVENC status {status}")


def _cuda_check(status: int, operation: str) -> None:
    if status:
        raise NvencQueryError(f"{operation} failed with CUDA status {status}")
