"""Validate saved pulse mappings against exact native stream readback."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import cast

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb
from cephvr.synchronization.v1 import spikeglx_pb2 as wire

from .channel_mapping import channel_type, digital_word_width
from .native import _FAMILY, _STREAMS

ROLE_BY_NAME = {
    "behavioral_camera": wire.PULSE_ROLE_BEHAVIORAL_CAMERA,
    "tracking_camera": wire.PULSE_ROLE_TRACKING_CAMERA,
    "photodiode": wire.PULSE_ROLE_PHOTODIODE,
}
FAMILY_NAMES = {int(value): name for name, value in _FAMILY.items()}


def validate_inventory(
    inventory: tuple[wire.PulseChannel, ...] | Mapping[str, Mapping[str, object]],
    streams: tuple[wire.NativeStream, ...],
    mapping: Mapping[str, object],
    *,
    required_roles: frozenset[int] | None = None,
) -> tuple[wire.PulseChannel, ...]:
    if required_roles is None:
        required_roles = frozenset(ROLE_BY_NAME.values())
    if isinstance(inventory, Mapping):
        channels: list[wire.PulseChannel] = []
        for role_name_input, row in inventory.items():
            role_id = ROLE_BY_NAME.get(role_name_input)
            if role_id is None:
                raise ValueError(
                    f"pulse_inventory.{role_name_input} has an unsupported role"
                )
            channel = wire.PulseChannel(
                role=role_id,
                family=_FAMILY[str(row.get("stream", ""))],
                stream_index=int(cast(int, row.get("stream_index", -1))),
                channel_index=int(cast(int, row.get("channel", -1))),
            )
            if "bit" in row:
                channel.bit = int(cast(int, row["bit"]))
            channels.append(channel)
        inventory_channels: tuple[wire.PulseChannel, ...] = tuple(channels)
    else:
        inventory_channels = tuple(inventory)
    present_roles = {item.role for item in inventory_channels}
    if not required_roles <= present_roles:
        missing = sorted(
            wire.PulseRole.Name(role) for role in required_roles - present_roles
        )
        raise ValueError(f"pulse_inventory is missing required active roles: {missing}")
    available = {(int(stream.family) - 1, stream.index): stream for stream in streams}
    result: list[wire.PulseChannel] = []
    used: set[tuple[int, int, int, int | None]] = set()
    identities: set[tuple[int, str]] = set()
    for channel in inventory_channels:
        role = channel.role
        role_name = wire.PulseRole.Name(role)
        family = FAMILY_NAMES.get(channel.family)
        if family is None or role not in {
            *ROLE_BY_NAME.values(),
            wire.PULSE_ROLE_TRIAL_STATE,
            wire.PULSE_ROLE_PROJECTOR_FLIP,
            wire.PULSE_ROLE_CUSTOM,
        }:
            raise ValueError("pulse_inventory contains an unsupported role or stream")
        source_id = channel.source_id if channel.HasField("source_id") else ""
        if role == wire.PULSE_ROLE_CUSTOM:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source_id):
                raise ValueError("custom pulse source requires a stable source_id")
        elif source_id:
            raise ValueError(f"pulse_inventory.{role_name} cannot use source_id")
        role_identity = (role, source_id)
        if role_identity in identities:
            raise ValueError("pulse_inventory repeats a source identity")
        identities.add(role_identity)
        if (
            role
            in {
                wire.PULSE_ROLE_BEHAVIORAL_CAMERA,
                wire.PULSE_ROLE_TRACKING_CAMERA,
            }
            and family != "onebox"
        ):
            raise ValueError(f"pulse_inventory.{role_name} must use a OneBox stream")
        stream_index, channel_index = channel.stream_index, channel.channel_index
        if stream_index < 0 or channel_index < 0:
            raise ValueError(f"pulse_inventory.{role_name} stream/channel is invalid")
        stream = available.get((_STREAMS[family], stream_index))
        saved = stream is not None and channel_index in stream.saved_channel_indices
        if not saved and role not in required_roles:
            if channel.HasField("bit") and stream is not None:
                try:
                    kind, _ = channel_type(mapping, stream, channel_index)
                except ValueError:
                    kind = ""
                digital_word = digital_word_width(mapping, family, kind)
                if digital_word is None or channel.bit not in digital_word[1]:
                    raise ValueError(
                        f"pulse_inventory.{role_name}.bit requires a known source-mapped digital word"
                    )
            elif channel.HasField("bit"):
                raise ValueError(
                    f"pulse_inventory.{role_name}.bit cannot be verified for an unmapped stream"
                )
            inactive_key = (
                _STREAMS[family],
                stream_index,
                channel_index,
                channel.bit if channel.HasField("bit") else None,
            )
            if inactive_key in used:
                raise ValueError(
                    "pulse_inventory cannot assign the same saved line twice"
                )
            used.add(inactive_key)
            result.append(wire.PulseChannel.FromString(channel.SerializeToString()))
            continue
        if not saved or stream is None:
            raise ValueError(f"pulse_inventory.{role_name} channel is not saved")
        kind, _ = channel_type(mapping, stream, channel_index)
        if channel.HasField("bit"):
            digital_word = digital_word_width(mapping, family, kind)
            if digital_word is None or channel.bit not in digital_word[1]:
                raise ValueError(
                    f"pulse_inventory.{role_name}.bit requires a supported source-mapped digital word"
                )
        bit = channel.bit if channel.HasField("bit") else None
        key = (_STREAMS[family], stream_index, channel_index, bit)
        if key in used:
            raise ValueError("pulse_inventory cannot assign the same saved line twice")
        used.add(key)
        result.append(wire.PulseChannel.FromString(channel.SerializeToString()))
    return tuple(result)


def required_inventory_roles(
    configuration: pb.ExperimentConfiguration,
) -> frozenset[int]:
    """Derive required mappings from the exact accepted active configuration."""
    required: set[int] = set()
    for backend in configuration.backends:
        if not backend.enabled:
            continue
        if (
            backend.backend_name == "acquisition"
            and backend.WhichOneof("settings") == "acquisition"
        ):
            acquisition = backend.acquisition
            for name, role in (
                ("behavioral", wire.PULSE_ROLE_BEHAVIORAL_CAMERA),
                ("tracking", wire.PULSE_ROLE_TRACKING_CAMERA),
            ):
                camera = getattr(acquisition, name)
                if (
                    camera.HasField("enabled")
                    and camera.enabled
                    and camera.device.frame_timing
                    == camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
                ):
                    required.add(role)
            if acquisition.HasField("pulses"):
                if (
                    acquisition.pulses.HasField("trial_state_enabled")
                    and acquisition.pulses.trial_state_enabled
                ):
                    required.add(wire.PULSE_ROLE_TRIAL_STATE)
                if (
                    acquisition.pulses.HasField("projector_flip_enabled")
                    and acquisition.pulses.projector_flip_enabled
                ):
                    required.add(wire.PULSE_ROLE_PROJECTOR_FLIP)
        if (
            backend.backend_name == "visual_stimulus"
            and backend.WhichOneof("settings") == "visual_stimulus"
        ):
            profile_json = backend.visual_stimulus.display.profile_json
            try:
                profile = json.loads(profile_json)
            except (TypeError, ValueError):
                continue
            if isinstance(profile, dict) and profile.get("photodiode_enabled") is True:
                required.add(wire.PULSE_ROLE_PHOTODIODE)
    return frozenset(required)
