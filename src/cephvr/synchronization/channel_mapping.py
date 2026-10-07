"""Resolve native saved-channel indices against the pinned stream layouts."""

from __future__ import annotations

from collections.abc import Mapping

from cephvr.synchronization.v1 import spikeglx_pb2 as wire


def channel_type(
    mapping: Mapping[str, object], stream: wire.NativeStream, channel_index: int
) -> tuple[str, int]:
    """Return the native channel type and its type-local index."""
    family = _family_name(stream.family)
    layouts = mapping.get("channel_type_order")
    if not isinstance(layouts, Mapping):
        raise ValueError("SpikeGLX mapping omits channel type order")
    types = layouts.get(family)
    if (
        not isinstance(types, list)
        or any(not isinstance(value, str) or not value for value in types)
        or len(types) != len(stream.acquired_channel_counts)
    ):
        raise ValueError("SpikeGLX stream channel counts do not match pinned layout")
    if any(
        type(count) is not int or count < 0 for count in stream.acquired_channel_counts
    ):
        raise ValueError("SpikeGLX acquired channel counts are invalid")
    if channel_index < 0 or channel_index >= sum(stream.acquired_channel_counts):
        raise ValueError("pulse channel index is outside acquired stream channels")
    offset = 0
    for kind, count in zip(types, stream.acquired_channel_counts, strict=True):
        if channel_index < offset + count:
            return kind, channel_index - offset
        offset += count
    raise ValueError("pulse channel index is not present in acquired stream")


def digital_word_width(
    mapping: Mapping[str, object], family: str, kind: str
) -> tuple[int, frozenset[int]] | None:
    words = mapping.get("digital_word_layouts")
    if not isinstance(words, Mapping):
        return None
    layout = words.get(family)
    if not isinstance(layout, Mapping) or layout.get("channel_type") != kind:
        return None
    width = layout.get("width_bits")
    supported = layout.get("supported_bits")
    if (
        type(width) is not int
        or width <= 0
        or not isinstance(supported, list)
        or any(type(bit) is not int or bit < 0 or bit >= width for bit in supported)
    ):
        raise ValueError("SpikeGLX digital word layout is malformed")
    return width, frozenset(supported)


def supported_digital_bits(
    mapping: Mapping[str, object], family: str
) -> frozenset[int]:
    words = mapping.get("digital_word_layouts")
    if not isinstance(words, Mapping):
        return frozenset()
    layout = words.get(family)
    if not isinstance(layout, Mapping):
        return frozenset()
    kind = layout.get("channel_type")
    if not isinstance(kind, str):
        raise ValueError("SpikeGLX digital word layout is malformed")
    result = digital_word_width(mapping, family, kind)
    return result[1] if result is not None else frozenset()


def _family_name(family: int) -> str:
    if family == wire.STREAM_FAMILY_NI:
        return "ni"
    if family == wire.STREAM_FAMILY_ONEBOX:
        return "onebox"
    if family == wire.STREAM_FAMILY_IMEC:
        return "imec"
    raise ValueError("SpikeGLX stream family is unsupported")
