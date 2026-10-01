"""Resolve an adopted physical NVIDIA GPU to the CUDA ordinal used by NVENC."""

from __future__ import annotations

import ctypes
import sys
import uuid
from ctypes import wintypes
from dataclasses import dataclass

from cephvr.platform.windows.jobs import WindowsLaunchError


@dataclass(frozen=True)
class NvidiaDevice:
    """Physical identity and the ordinal observed in this process's CUDA driver."""

    ordinal: int
    uuid: str
    name: str


class _CudaUuid(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]


def discover_encoder_device() -> NvidiaDevice:
    """Adopt the unique physical RTX 2080 Ti as the encoding device."""
    devices = _enumerate_cuda_devices()
    matches = [
        device for device in devices if device.name.endswith("GeForce RTX 2080 Ti")
    ]
    if len(matches) != 1:
        raise WindowsLaunchError(
            f"encoding adapter discovery found {len(matches)} RTX 2080 Ti devices"
        )
    return matches[0]


def verify_opengl_rendering_device(renderer: str, vendor: str) -> NvidiaDevice:
    """Resolve the OpenGL context to the unique SYS-002 renderer adapter.

    NVIDIA's OpenGL renderer string exposes the physical board model while CUDA
    supplies the stable UUID. Requiring one matching adapter and the exact model
    string avoids ordinal assumptions and refuses ambiguous/mismatched contexts.
    """
    if sys.platform != "win32":
        raise WindowsLaunchError("OpenGL adapter resolution requires Windows")
    devices = _enumerate_cuda_devices()
    matches = [
        device for device in devices if device.name.endswith("GeForce RTX 5060 Ti")
    ]
    if len(matches) != 1:
        raise WindowsLaunchError(
            f"render adapter discovery found {len(matches)} RTX 5060 Ti devices"
        )
    selected = matches[0]
    if "NVIDIA" not in vendor.upper() or selected.name not in renderer:
        raise WindowsLaunchError(
            f"OpenGL context {vendor!r}/{renderer!r} does not resolve to {selected.name!r}"
        )
    return selected


def verify_tracking_device(ordinal: int) -> NvidiaDevice:
    """SYS-002: verify the configured ordinal against the unique processing GPU."""
    matches = [
        device
        for device in _enumerate_cuda_devices()
        if device.name.endswith("GeForce RTX 5060 Ti")
    ]
    if len(matches) != 1 or matches[0].ordinal != ordinal:
        raise WindowsLaunchError(
            "tracking ordinal does not identify the unique RTX 5060 Ti"
        )
    return matches[0]


def resolve_cuda_ordinal(device_uuid: str) -> NvidiaDevice:
    """Require one exact UUID match; never fall back to another enumerated adapter."""
    if sys.platform != "win32":
        raise WindowsLaunchError("NVENC adapter resolution requires Windows")
    try:
        expected = uuid.UUID(device_uuid.removeprefix("GPU-")).bytes
    except ValueError as exc:
        raise WindowsLaunchError("adopted NVIDIA UUID is malformed") from exc
    matches = [
        device
        for device in _enumerate_cuda_devices()
        if uuid.UUID(device.uuid.removeprefix("GPU-")).bytes == expected
    ]
    if len(matches) != 1:
        raise WindowsLaunchError(
            f"adopted NVIDIA UUID resolved to {len(matches)} CUDA devices; encoder disabled"
        )
    selected = matches[0]
    if not selected.name.endswith("GeForce RTX 2080 Ti"):
        raise WindowsLaunchError(
            f"adopted encoding adapter is not the RTX 2080 Ti: {selected.name}"
        )
    return selected


def _enumerate_cuda_devices() -> list[NvidiaDevice]:
    """Return physical CUDA identities; callers must select by exact identity."""
    if sys.platform != "win32":
        raise WindowsLaunchError("NVENC adapter resolution requires Windows")
    try:
        cuda = ctypes.WinDLL("nvcuda.dll")
        cuda.cuInit.argtypes = [wintypes.UINT]
        cuda.cuInit.restype = ctypes.c_int
        cuda.cuDeviceGetCount.argtypes = [ctypes.POINTER(ctypes.c_int)]
        cuda.cuDeviceGetCount.restype = ctypes.c_int
        cuda.cuDeviceGet.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int]
        cuda.cuDeviceGet.restype = ctypes.c_int
        cuda.cuDeviceGetUuid_v2.argtypes = [ctypes.POINTER(_CudaUuid), ctypes.c_int]
        cuda.cuDeviceGetUuid_v2.restype = ctypes.c_int
        cuda.cuDeviceGetName.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        cuda.cuDeviceGetName.restype = ctypes.c_int
    except (OSError, AttributeError) as exc:
        # Driver absence and missing exports are preparation failures, not fallbacks.
        raise WindowsLaunchError(
            f"required CUDA driver API is unavailable: {exc}"
        ) from exc
    _check(cuda.cuInit(0), "cuInit")
    count = ctypes.c_int()
    _check(cuda.cuDeviceGetCount(ctypes.byref(count)), "cuDeviceGetCount")
    devices: list[NvidiaDevice] = []
    for ordinal in range(count.value):
        device = ctypes.c_int()
        _check(cuda.cuDeviceGet(ctypes.byref(device), ordinal), "cuDeviceGet")
        raw_uuid = _CudaUuid()
        _check(
            cuda.cuDeviceGetUuid_v2(ctypes.byref(raw_uuid), device.value),
            "cuDeviceGetUuid_v2",
        )
        name = ctypes.create_string_buffer(256)
        _check(cuda.cuDeviceGetName(name, len(name), device.value), "cuDeviceGetName")
        current = bytes(raw_uuid.bytes)
        devices.append(
            NvidiaDevice(
                ordinal,
                f"GPU-{uuid.UUID(bytes=current)}",
                name.value.decode("utf-8", "strict"),
            )
        )
    return devices


def _check(status: int, operation: str) -> None:
    if status:
        raise WindowsLaunchError(f"{operation} failed with CUDA status {status}")
