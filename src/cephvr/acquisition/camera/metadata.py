"""Documented optional Basler native timestamp and frame-ID provenance (A09)."""

from __future__ import annotations

import importlib
from fractions import Fraction
from typing import Any

from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.acquisition.camera.features import (
    enum_capability,
    get_node,
    read_value,
    set_enum,
    write_value,
)
from cephvr.acquisition.camera.types import (
    CameraClockDescriptor,
    NativeMetadataSupport,
    NativeMetadataWarning,
    TransportInterface,
)


def native_metadata(
    camera: Any, device_id: str, interface: TransportInterface
) -> NativeMetadataSupport:
    """Bind exact pylon result sources, known units and transport-specific block IDs."""
    try:
        nodes = camera.GetNodeMap()
        frequency = _positive_integer(read_value(nodes, "TimestampTickFrequency"))
        if frequency is None:
            frequency = _positive_integer(
                read_value(nodes, "GevTimestampTickFrequency")
            )
        chunk_timestamp = False
        chunk_counter = False
        genicam = importlib.import_module("pypylon.genicam")
        chunk_mode = get_node(nodes, "ChunkModeActive")
        if chunk_mode is not None:
            if read_value(nodes, "ChunkModeActive") is not True and genicam.IsWritable(
                chunk_mode
            ):
                write_value(nodes, "ChunkModeActive", True)
            if read_value(nodes, "ChunkModeActive") is True:
                choices = enum_capability(nodes, "ChunkSelector")
                chunk_timestamp = _enable_chunk(
                    nodes, choices, "Timestamp", "ChunkTimestamp", genicam
                )
                chunk_counter = _enable_chunk(
                    nodes, choices, "Framecounter", "ChunkFramecounter", genicam
                )
        ratio = Fraction(1_000_000_000, frequency) if frequency is not None else None
        warnings: list[NativeMetadataWarning] = []
        if ratio is None:
            warnings.append(
                NativeMetadataWarning(
                    "NATIVE_TIMESTAMP_UNAVAILABLE",
                    None,
                    "documented timestamp tick frequency is unavailable",
                )
            )
        counter_available = chunk_counter or interface in ("usb3", "gige")
        if not counter_available:
            warnings.append(
                NativeMetadataWarning(
                    "NATIVE_COUNTER_UNAVAILABLE",
                    None,
                    "Basler block ID transport semantics are unavailable",
                )
            )
        descriptor = CameraClockDescriptor(
            device_id=device_id,
            timestamp_source="ChunkTimestamp"
            if chunk_timestamp
            else "CGrabResultData.GetTimeStamp",
            conversion_available=ratio is not None,
            tick_period_ns_numerator=ratio.numerator if ratio is not None else None,
            tick_period_ns_denominator=ratio.denominator if ratio is not None else None,
            timestamp_semantics="exposure_start" if ratio is not None else "unknown",
            reset_semantics="unknown",
            wrap_semantics="unknown",
            unavailable_reason=""
            if ratio is not None
            else "timestamp tick frequency unavailable",
            counter_source="ChunkFramecounter"
            if chunk_counter
            else "CGrabResultData.GetBlockID"
            if counter_available
            else "unavailable",
            counter_semantics="frames" if counter_available else "unknown",
            counter_width_bits=_chunk_counter_width(nodes)
            if chunk_counter
            else 16
            if interface == "gige"
            else 64
            if interface == "usb3"
            else None,
            counter_wrap_semantics="unknown"
            if chunk_counter
            else "wraps_at_65535"
            if interface == "gige"
            else "unknown",
            counter_unavailable_reason=""
            if counter_available
            else "transport counter semantics unavailable",
        )
        return NativeMetadataSupport(
            ratio is not None, counter_available, tuple(warnings), descriptor
        )
    except CameraAdapterError:
        raise
    except Exception as exc:
        raise CameraAdapterError(
            "SDK_FAILURE", f"Basler metadata capability read failed: {exc}"
        ) from exc


def _positive_integer(value: Any) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else None
    )


def _enable_chunk(
    nodes: Any, choices: Any, selector: str, chunk_node: str, genicam: Any
) -> bool:
    if not any(choice.sdk_symbol == selector for choice in choices.choices):
        return False
    set_enum(nodes, "ChunkSelector", selector)
    enable = get_node(nodes, "ChunkEnable")
    if enable is None or not genicam.IsAvailable(enable):
        return False
    if read_value(nodes, "ChunkEnable") is not True:
        if not genicam.IsWritable(enable):
            return False
        write_value(nodes, "ChunkEnable", True)
    if read_value(nodes, "ChunkEnable") is not True:
        return False
    # Chunk values are exposed on each result's GetChunkNode map, not reliably
    # on the camera node map. The selector and enable readback bind capability;
    # grab.py validates the result-scoped node for every received image.
    return chunk_node in {"ChunkTimestamp", "ChunkFramecounter"}


def _chunk_counter_width(nodes: Any) -> int | None:
    # Result-scoped chunk nodes are authoritative; a camera nodemap node of the
    # same name cannot establish the width of values extracted from each result.
    _ = nodes
    return None
