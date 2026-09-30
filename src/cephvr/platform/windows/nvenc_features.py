"""NVENC codec, profile, format and feature queries for one exact device."""

from __future__ import annotations

import ctypes
import time
from collections.abc import Callable
from dataclasses import dataclass

from cephvr.platform.windows.nvenc_api import (
    NvencQueryError,
    _CapsParam,
    _function,
    _FunctionList,
    _Guid,
    _nv_check,
    _struct_version,
)

NV_ENC_PARAMS_RC_VBR = 0x1
NV_ENC_PARAMS_RC_CBR = 0x2

_CODECS = {
    "h264_nvenc": "6bc82762-4e63-4ca4-aa85-1e50f321f6bf",
    "hevc_nvenc": "790cdc88-4522-4d7b-9425-bda9975f7603",
    "av1_nvenc": "0a352289-0aa7-4759-862d-5d15cd16d254",
}
_PROFILES = {
    "h264_nvenc": {
        "baseline": "0727bcaa-78c4-4c83-8c2f-ef3dff267c6a",
        "main": "60b5c1d4-67fe-4790-94d5-c4726d7b6e6d",
        "high": "e7cbc309-4f7a-4b89-af2a-d537c92be310",
        "high444p": "7ac663cb-a598-4960-b844-339b261a7d52",
        "stereo": "40847bf5-33f7-4601-9084-e8fe3c1db8b7",
        "progressive_high": "b405afac-f32b-417b-89c4-9abeed3e5978",
        "constrained_high": "aec1bd87-e85b-48f2-84c3-98bca6285072",
    },
    "hevc_nvenc": {
        "main": "b514c39a-b55b-40fa-878f-f1253b4dfdec",
        "main10": "fa4d2b6c-3a5b-411a-8018-0a3f5e3c9be5",
        "rext": "51ec32b5-1b4c-453c-9cbd-b616bd621341",
    },
    "av1_nvenc": {"main": "5f2a39f5-f14e-4f95-9a9e-b76d568fcf97"},
}
_BUFFER_FORMATS = {
    0x00000001: {"nv12"},
    0x00000010: {"yuv420p"},
    0x00000100: {"yuv420p"},
    0x00001000: {"yuv444p"},
    0x00010000: {"p010le"},
    0x00100000: {"yuv444p10le"},
}


@dataclass(frozen=True)
class NvencDeviceCapabilities:
    codec_pixel_formats: dict[str, frozenset[str]]
    codec_profiles: dict[str, frozenset[str]]
    codec_rate_controls: dict[str, frozenset[str]]
    codec_lookahead: dict[str, bool]
    codec_temporal_aq: dict[str, bool]
    codec_lossless: dict[str, bool]
    max_dimensions: dict[str, tuple[int, int]]


def collect_capabilities(
    function_list: _FunctionList, encoder: ctypes.c_void_p, *, deadline_ns: int
) -> NvencDeviceCapabilities:
    get_count = _function(
        function_list, 1, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    )
    get_profile_count = _function(
        function_list,
        2,
        [ctypes.c_void_p, _Guid, ctypes.POINTER(ctypes.c_uint32)],
    )
    get_profiles = _function(
        function_list,
        3,
        [
            ctypes.c_void_p,
            _Guid,
            ctypes.POINTER(_Guid),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ],
    )
    get_guids = _function(
        function_list,
        4,
        [
            ctypes.c_void_p,
            ctypes.POINTER(_Guid),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ],
    )
    get_format_count = _function(
        function_list, 5, [ctypes.c_void_p, _Guid, ctypes.POINTER(ctypes.c_uint32)]
    )
    get_formats = _function(
        function_list,
        6,
        [
            ctypes.c_void_p,
            _Guid,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ],
    )
    get_caps = _function(
        function_list,
        7,
        [
            ctypes.c_void_p,
            _Guid,
            ctypes.POINTER(_CapsParam),
            ctypes.POINTER(ctypes.c_int),
        ],
    )
    count = ctypes.c_uint32()
    _query_call(
        get_count, "NvEncGetEncodeGUIDCount", deadline_ns, encoder, ctypes.byref(count)
    )
    if count.value > 256:
        raise NvencQueryError("driver returned an unreasonable codec GUID count")
    guids = (_Guid * count.value)()
    actual_count = ctypes.c_uint32()
    _query_call(
        get_guids,
        "NvEncGetEncodeGUIDs",
        deadline_ns,
        encoder,
        guids,
        count.value,
        ctypes.byref(actual_count),
    )
    if actual_count.value > count.value:
        raise NvencQueryError(
            "driver reported more codec GUIDs than the allocated buffer"
        )
    available = {guid.text() for guid in guids[: actual_count.value]}
    formats_by_codec: dict[str, frozenset[str]] = {}
    profiles_by_codec: dict[str, frozenset[str]] = {}
    rate_controls_by_codec: dict[str, frozenset[str]] = {}
    lookahead_by_codec: dict[str, bool] = {}
    temporal_aq_by_codec: dict[str, bool] = {}
    lossless_by_codec: dict[str, bool] = {}
    dimensions: dict[str, tuple[int, int]] = {}
    for codec, guid_text in _CODECS.items():
        if guid_text not in available:
            continue
        guid = _Guid.from_text(guid_text)
        profile_count = ctypes.c_uint32()
        _query_call(
            get_profile_count,
            "NvEncGetEncodeProfileGUIDCount",
            deadline_ns,
            encoder,
            guid,
            ctypes.byref(profile_count),
        )
        if profile_count.value > 256:
            raise NvencQueryError("driver returned an unreasonable profile GUID count")
        profile_guids = (_Guid * profile_count.value)()
        actual_profiles = ctypes.c_uint32()
        _query_call(
            get_profiles,
            "NvEncGetEncodeProfileGUIDs",
            deadline_ns,
            encoder,
            guid,
            profile_guids,
            profile_count.value,
            ctypes.byref(actual_profiles),
        )
        if actual_profiles.value > profile_count.value:
            raise NvencQueryError(
                "driver returned more profiles than the allocated buffer"
            )
        available_profiles = {
            profile.text() for profile in profile_guids[: actual_profiles.value]
        }
        profile_names = frozenset(
            name
            for name, profile_guid in _PROFILES[codec].items()
            if profile_guid in available_profiles
        )
        if not profile_names:
            continue
        fmt_count = ctypes.c_uint32()
        _query_call(
            get_format_count,
            "NvEncGetInputFormatCount",
            deadline_ns,
            encoder,
            guid,
            ctypes.byref(fmt_count),
        )
        if fmt_count.value > 256:
            raise NvencQueryError("driver returned an unreasonable input format count")
        formats = (ctypes.c_int * fmt_count.value)()
        actual_formats = ctypes.c_uint32()
        _query_call(
            get_formats,
            "NvEncGetInputFormats",
            deadline_ns,
            encoder,
            guid,
            formats,
            fmt_count.value,
            ctypes.byref(actual_formats),
        )
        if actual_formats.value > fmt_count.value:
            raise NvencQueryError(
                "driver reported more input formats than the allocated buffer"
            )
        names = frozenset(
            name
            for value in formats[: actual_formats.value]
            for name in _BUFFER_FORMATS.get(value, set())
        )
        if not names:
            continue
        ten_bit = bool(
            _get_cap(
                get_caps, encoder, guid, 39, deadline_ns=deadline_ns, positive=False
            )
        )
        if not ten_bit:
            names = names.difference({"p010le", "yuv444p10le"})
        if not names:
            continue
        dimensions[codec] = (
            _get_cap(get_caps, encoder, guid, 16, deadline_ns=deadline_ns),
            _get_cap(get_caps, encoder, guid, 17, deadline_ns=deadline_ns),
        )
        rate_modes = _get_cap(
            get_caps,
            encoder,
            guid,
            1,
            deadline_ns=deadline_ns,
            positive=False,
        )
        rate_controls_by_codec[codec] = _rate_control_modes(rate_modes)
        lookahead_by_codec[codec] = bool(
            _get_cap(
                get_caps, encoder, guid, 37, deadline_ns=deadline_ns, positive=False
            )
        )
        temporal_aq_by_codec[codec] = bool(
            _get_cap(
                get_caps, encoder, guid, 38, deadline_ns=deadline_ns, positive=False
            )
        )
        lossless_by_codec[codec] = bool(
            _get_cap(
                get_caps, encoder, guid, 34, deadline_ns=deadline_ns, positive=False
            )
        )
        formats_by_codec[codec] = names
        profiles_by_codec[codec] = profile_names
    return NvencDeviceCapabilities(
        formats_by_codec,
        profiles_by_codec,
        rate_controls_by_codec,
        lookahead_by_codec,
        temporal_aq_by_codec,
        lossless_by_codec,
        dimensions,
    )


def _rate_control_modes(mask: int) -> frozenset[str]:
    # The pinned SDK declares a bitmask of enum VALUES. CONSTQP is enum value
    # zero and the API's baseline mode, so it has no representable bit here.
    supported = {"constqp"}
    if mask & NV_ENC_PARAMS_RC_VBR:
        supported.add("vbr")
    if mask & NV_ENC_PARAMS_RC_CBR:
        supported.add("cbr")
    return frozenset(supported)


def _get_cap(
    get_caps: Callable[..., int],
    encoder: ctypes.c_void_p,
    guid: _Guid,
    capability: int,
    *,
    deadline_ns: int,
    positive: bool = True,
) -> int:
    params = _CapsParam()
    params.version = _struct_version(1)
    params.caps_to_query = capability
    value = ctypes.c_int()
    _query_call(
        get_caps,
        "NvEncGetEncodeCaps",
        deadline_ns,
        encoder,
        guid,
        ctypes.byref(params),
        ctypes.byref(value),
    )
    if positive and value.value <= 0:
        raise NvencQueryError("NVENC returned a nonpositive max dimension")
    if value.value < 0:
        raise NvencQueryError("NVENC returned a negative capability value")
    return value.value


def _query_call(
    call: Callable[..., int], operation: str, deadline_ns: int, *args: object
) -> None:
    _check_deadline(deadline_ns, f"before {operation}")
    _nv_check(call(*args), operation)
    _check_deadline(deadline_ns, f"after {operation}")


def _check_deadline(deadline_ns: int, stage: str) -> None:
    if time.perf_counter_ns() >= deadline_ns:
        raise NvencQueryError(f"NVENC query deadline expired {stage}")
