"""Minimal NVENC capability query for the exact CUDA device selected by UUID.

ABI layout/version constants follow FFmpeg's pinned nv-codec-headers v12.2.72.0
(`NVENCAPI_MAJOR_VERSION=12`, `NVENCAPI_MINOR_VERSION=2`). This is a read-only
session: no encode/test workload is submitted.
"""

from __future__ import annotations

import ctypes
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass

from cephvr.platform.windows.nvenc_api import (
    _API_VERSION,
    NvencQueryError,
    _cuda_check,
    _function,
    _FunctionList,
    _nv_check,
    _OpenSessionEx,
    _struct_version,
)
from cephvr.platform.windows.nvenc_features import (
    NvencDeviceCapabilities,
    collect_capabilities,
)
from cephvr.platform.windows.nvidia_device import NvidiaDevice, resolve_cuda_ordinal

_CUDA_DEVICE_TYPE = 1
NV_ENC_PARAMS_RC_CONSTQP = 0x0
NV_ENC_PARAMS_RC_VBR = 0x1
NV_ENC_PARAMS_RC_CBR = 0x2


@dataclass
class _ProbeOwnership:
    cuda: object
    context: ctypes.c_void_p
    driver: object | None = None
    function_list: _FunctionList | None = None
    encoder: ctypes.c_void_p | None = None
    destroy_encoder: Callable[..., int] | None = None
    destroy_context: Callable[..., int] | None = None
    retained: bool = False


class NvencProbeOwner:
    """Explicit per-worker owner of one native capability-query resource graph."""

    def __init__(self) -> None:
        self._retained_probe: _ProbeOwnership | None = None

    def query(
        self, device: NvidiaDevice, *, deadline_ns: int
    ) -> NvencDeviceCapabilities:
        if self._retained_probe is not None:
            raise NvencQueryError("prior NVENC probe cleanup remains unresolved")
        return _query_nvenc_device(self, device, deadline_ns=deadline_ns)

    def retry_cleanup(self, *, deadline_ns: int) -> None:
        probe = self._retained_probe
        if probe is not None:
            _cleanup_probe(self, probe, deadline_ns=deadline_ns)


def _query_nvenc_device(
    owner: NvencProbeOwner, device: NvidiaDevice, *, deadline_ns: int
) -> NvencDeviceCapabilities:
    """Query supported codec GUIDs, input formats, and max dimensions via CUDA."""
    if sys.platform != "win32":
        raise NvencQueryError("NVENC device query requires Windows")
    _check_deadline(deadline_ns, "before adopted-device resolution")
    current_device = resolve_cuda_ordinal(device.uuid)
    _check_deadline(deadline_ns, "after adopted-device resolution")
    if current_device.ordinal != device.ordinal:
        raise NvencQueryError(
            "adopted NVIDIA device ordinal changed before capability query"
        )
    cuda = ctypes.WinDLL("nvcuda.dll")
    cuda.cuInit.argtypes = [wintypes.UINT]
    cuda.cuInit.restype = ctypes.c_int
    cuda.cuDeviceGet.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    cuda.cuDeviceGet.restype = ctypes.c_int
    cuda.cuCtxCreate_v2.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.UINT,
        ctypes.c_int,
    ]
    cuda.cuCtxCreate_v2.restype = ctypes.c_int
    cuda.cuCtxDestroy_v2.argtypes = [ctypes.c_void_p]
    cuda.cuCtxDestroy_v2.restype = ctypes.c_int
    _check_deadline(deadline_ns, "before cuInit")
    _cuda_check(cuda.cuInit(0), "cuInit")
    _check_deadline(deadline_ns, "after cuInit")
    cuda_device = ctypes.c_int()
    _check_deadline(deadline_ns, "before cuDeviceGet")
    _cuda_check(
        cuda.cuDeviceGet(ctypes.byref(cuda_device), device.ordinal), "cuDeviceGet"
    )
    _check_deadline(deadline_ns, "after cuDeviceGet")
    context = ctypes.c_void_p()
    _check_deadline(deadline_ns, "before cuCtxCreate_v2")
    _cuda_check(
        cuda.cuCtxCreate_v2(ctypes.byref(context), 0, cuda_device.value),
        "cuCtxCreate_v2",
    )
    probe = _ProbeOwnership(
        cuda=cuda, context=context, destroy_context=cuda.cuCtxDestroy_v2
    )
    owner._retained_probe = probe
    try:
        _check_deadline(deadline_ns, "after cuCtxCreate_v2")
        function_list = _FunctionList()
        probe.function_list = function_list
        function_list.version = _struct_version(2)
        driver = ctypes.WinDLL("nvEncodeAPI64.dll")
        probe.driver = driver
        driver.NvEncodeAPICreateInstance.argtypes = [ctypes.POINTER(_FunctionList)]
        driver.NvEncodeAPICreateInstance.restype = ctypes.c_int
        _check_deadline(deadline_ns, "before NvEncodeAPICreateInstance")
        _nv_check(
            driver.NvEncodeAPICreateInstance(ctypes.byref(function_list)),
            "NvEncodeAPICreateInstance",
        )
        _check_deadline(deadline_ns, "after NvEncodeAPICreateInstance")
        open_session = _function(
            function_list,
            29,
            [ctypes.POINTER(_OpenSessionEx), ctypes.POINTER(ctypes.c_void_p)],
        )
        encoder = ctypes.c_void_p()
        parameters = _OpenSessionEx()
        parameters.version = _struct_version(1)
        parameters.device_type = _CUDA_DEVICE_TYPE
        parameters.device = context
        parameters.api_version = _API_VERSION
        probe.destroy_encoder = _function(function_list, 27, [ctypes.c_void_p])
        _check_deadline(deadline_ns, "before NvEncOpenEncodeSessionEx")
        status = open_session(ctypes.byref(parameters), ctypes.byref(encoder))
        if encoder.value:
            probe.encoder = encoder
        _nv_check(status, "NvEncOpenEncodeSessionEx")
        _check_deadline(deadline_ns, "after NvEncOpenEncodeSessionEx")
        result = collect_capabilities(function_list, encoder, deadline_ns=deadline_ns)
        _cleanup_probe(owner, probe, deadline_ns=deadline_ns)
        _check_deadline(deadline_ns, "after NVENC capability cleanup")
        return result
    except BaseException:
        try:
            _cleanup_probe(owner, probe, deadline_ns=deadline_ns)
        except BaseException:
            # _cleanup_probe retained the complete ownership graph for retry.
            pass
        raise


def _cleanup_probe(
    owner: NvencProbeOwner, probe: _ProbeOwnership, *, deadline_ns: int
) -> None:
    try:
        if probe.encoder is not None:
            if probe.destroy_encoder is None:
                raise NvencQueryError("encoder cleanup function is unavailable")
            _check_deadline(deadline_ns, "before NvEncDestroyEncoder")
            _nv_check(probe.destroy_encoder(probe.encoder), "NvEncDestroyEncoder")
            probe.encoder = None
            _check_deadline(deadline_ns, "after NvEncDestroyEncoder")
        if probe.context.value:
            if probe.destroy_context is None:
                raise NvencQueryError("CUDA context cleanup function is unavailable")
            _check_deadline(deadline_ns, "before cuCtxDestroy_v2")
            _cuda_check(probe.destroy_context(probe.context), "cuCtxDestroy_v2")
            probe.context = ctypes.c_void_p()
            _check_deadline(deadline_ns, "after cuCtxDestroy_v2")
    except BaseException:
        probe.retained = True
        raise
    probe.retained = False
    if owner._retained_probe is probe:
        owner._retained_probe = None


def _check_deadline(deadline_ns: int, stage: str) -> None:
    if time.perf_counter_ns() >= deadline_ns:
        raise NvencQueryError(f"NVENC query deadline expired {stage}")
