"""Typed readback over the official SpikeGLX SDK wrapper."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from ctypes import byref, c_bool, c_char_p, c_int
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cephvr.synchronization.v1 import spikeglx_pb2 as wire

from .diagnostic import _load_sdk, _required, _sdk_package, _text
from .settings import HostSettings

_STREAMS = {"ni": 0, "onebox": 1, "imec": 2}
_FAMILY = {
    "ni": wire.STREAM_FAMILY_NI,
    "onebox": wire.STREAM_FAMILY_ONEBOX,
    "imec": wire.STREAM_FAMILY_IMEC,
}


@dataclass(frozen=True)
class Readback:
    version: str
    data_directory: str
    running: bool
    saving: bool
    run_name: str
    streams: tuple[wire.NativeStream, ...]
    params_digest: str
    gate_mode: str
    trigger_mode: str
    counts: tuple[tuple[int, int, int], ...]


def _read_strings(sdk: Any, handle: int, function: str, *args: int) -> tuple[str, ...]:
    count = c_int()
    _required(
        getattr(sdk, function)(byref(count), handle, *args), sdk, handle, function
    )
    if not 0 <= count.value <= 100_000:
        raise ValueError(f"{function} returned an invalid item count")
    return tuple(
        _text(sdk.c_sglx_getstr(byref(count), handle, index))
        for index in range(count.value)
    )


def _read_ints(sdk: Any, handle: int, function: str, *args: int) -> tuple[int, ...]:
    count = c_int()
    _required(
        getattr(sdk, function)(byref(count), handle, *args), sdk, handle, function
    )
    if not 0 <= count.value <= 100_000:
        raise ValueError(f"{function} returned an invalid item count")
    return tuple(int(sdk.c_sglx_getint(handle, index)) for index in range(count.value))


def _read_param_group(
    sdk: Any, handle: int, function: str, *args: int
) -> dict[str, str]:
    pairs = {}
    for item in _read_strings(sdk, handle, function, *args):
        key, separator, value = item.partition("=")
        if not separator or not key:
            raise ValueError(f"{function} returned a malformed parameter")
        if key in pairs:
            raise ValueError(f"{function} returned duplicate parameter {key}")
        pairs[key] = value
    return pairs


def read_sdk(
    software_root: Path, settings: HostSettings, *, writing: bool = False
) -> Readback:
    sdk = _load_sdk(_sdk_package(software_root))
    handle = sdk.c_sglx_createHandle()
    if not handle:
        raise RuntimeError("SpikeGLX SDK could not create a connection handle")
    try:
        _required(
            sdk.c_sglx_connect(handle, settings.address.encode("utf-8"), settings.port),
            sdk,
            handle,
            "connect",
        )
        version = _text(sdk.c_sglx_getVersion(handle))
        if not version:
            raise RuntimeError("SpikeGLX SDK returned no version")
        expected_version = str(settings.mapping.get("reported_version", ""))
        version_tokens = re.findall(r"v\d+(?:\.\d+)*", expected_version)
        if version_tokens and any(token not in version for token in version_tokens):
            raise RuntimeError(
                f"SpikeGLX version {version!r} has no matching source mapping"
            )
        running, saving = c_bool(), c_bool()
        _required(
            sdk.c_sglx_isRunning(byref(running), handle), sdk, handle, "isRunning"
        )
        _required(sdk.c_sglx_isSaving(byref(saving), handle), sdk, handle, "isSaving")
        name_pointer, dir_pointer = c_char_p(), c_char_p()
        has_name = sdk.c_sglx_getRunName(byref(name_pointer), handle)
        run_name = _text(name_pointer.value) if has_name else ""
        _required(
            sdk.c_sglx_getDataDir(byref(dir_pointer), handle, 0),
            sdk,
            handle,
            "getDataDir",
        )
        data_directory = _text(dir_pointer.value)
        if not data_directory:
            raise RuntimeError("SpikeGLX SDK returned no data directory")

        parameters: dict[str, str] = {}
        groups = [_read_param_group(sdk, handle, "c_sglx_getParams")]
        counts = []
        streams = []
        for family, code in _STREAMS.items():
            np = c_int()
            _required(
                sdk.c_sglx_getStreamNP(byref(np), handle, code),
                sdk,
                handle,
                "getStreamNP",
            )
            if not 0 <= np.value <= 256:
                raise ValueError(f"SpikeGLX returned invalid {family} stream count")
            for index in range(np.value):
                acquired = _read_ints(
                    sdk, handle, "c_sglx_getStreamAcqChans", code, index
                )
                saved = _read_ints(
                    sdk, handle, "c_sglx_getStreamSaveChans", code, index
                )
                sample_rate = float(sdk.c_sglx_getStreamSampleRate(handle, code, index))
                if not math.isfinite(sample_rate) or sample_rate <= 0:
                    raise ValueError("SpikeGLX returned an invalid sample rate")
                serial = ""
                if family in {"onebox", "imec"}:
                    slot_or_type, serial_pointer = c_int(), c_char_p()
                    _required(
                        sdk.c_sglx_getStreamSN(
                            byref(slot_or_type),
                            byref(serial_pointer),
                            handle,
                            code,
                            index,
                        ),
                        sdk,
                        handle,
                        "getStreamSN",
                    )
                    serial = _text(serial_pointer.value)
                streams.append(
                    wire.NativeStream(
                        family=_FAMILY[family],
                        index=index,
                        hardware_serial=serial,
                        sample_rate_hz=sample_rate,
                        acquired_channel_counts=acquired,
                        saved_channel_indices=saved,
                    )
                )
                if saved:
                    counts.append((code, index, 0))
                if family == "onebox":
                    groups.append(
                        _read_param_group(
                            sdk, handle, "c_sglx_getParamsOneBox", index, 0
                        )
                    )
                elif family == "imec":
                    groups.append(
                        _read_param_group(
                            sdk, handle, "c_sglx_getParamsImecProbe", index
                        )
                    )
        if any(stream.family == wire.STREAM_FAMILY_IMEC for stream in streams):
            groups.append(_read_param_group(sdk, handle, "c_sglx_getParamsImecCommon"))
        for index, group in enumerate(groups):
            for key, value in group.items():
                qualified = f"{index}:{key}"
                parameters[qualified] = value
        digest_values = dict(parameters)
        digest_values.pop("0:snsRunName", None)
        digest = hashlib.sha256(
            json.dumps(digest_values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        keys = settings.mapping.get("parameter_keys", {})
        gate_code = parameters.get(f"0:{keys.get('gate_mode', 'gateMode')}")
        trigger_code = parameters.get(f"0:{keys.get('trigger_mode', 'trigMode')}")
        gate_modes = settings.mapping.get("gate_modes", {})
        trigger_modes = settings.mapping.get("trigger_modes", {})
        gate_mode = str(gate_modes.get(gate_code, "unknown"))
        trigger_mode = str(trigger_modes.get(trigger_code, "unknown"))
        if writing and (not running.value or not saving.value):
            raise RuntimeError("SpikeGLX is not running and saving")
        return Readback(
            version,
            data_directory,
            running.value,
            saving.value,
            run_name,
            tuple(streams),
            digest,
            gate_mode,
            trigger_mode,
            tuple(counts),
        )
    finally:
        try:
            sdk.c_sglx_close(handle)
        finally:
            sdk.c_sglx_destroyHandle(handle)


def with_sdk(
    software_root: Path,
    settings: HostSettings,
    operation: Callable[[Any, int], Any],
) -> Any:
    sdk = _load_sdk(_sdk_package(software_root))
    handle = sdk.c_sglx_createHandle()
    if not handle:
        raise RuntimeError("SpikeGLX SDK could not create a connection handle")
    try:
        _required(
            sdk.c_sglx_connect(handle, settings.address.encode("utf-8"), settings.port),
            sdk,
            handle,
            "connect",
        )
        return operation(sdk, handle)
    finally:
        try:
            sdk.c_sglx_close(handle)
        finally:
            sdk.c_sglx_destroyHandle(handle)
