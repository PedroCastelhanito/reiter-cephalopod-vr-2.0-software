"""E04 active configuration and Protobuf metadata document construction."""

from __future__ import annotations

from copy import deepcopy

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.state import Attempt, SupervisorState


def message_dict(message: Message) -> dict[str, object]:
    return MessageToDict(message, preserving_proto_field_name=True)


def software_provenance(
    attempt: Attempt, supervisor: SupervisorState
) -> dict[str, object]:
    """Use exact accepted Ready/status versions; missing versions remain unknown."""
    return {
        "supervisor": supervisor.software_version or None,
        "backends": {
            name: (attempt.ready[name].software_version or None)
            if name in attempt.ready
            else None
            for name in sorted(attempt.required)
        },
    }


def output_formats(
    schema: dict[str, object], expected: set[str]
) -> dict[str, tuple[str, int]]:
    """Freeze the format/version from each owning writer's Start schema."""
    entries = schema.get("outputs", [])
    if not isinstance(entries, list):
        raise ValueError("writer schema outputs must be a list")
    result: dict[str, tuple[str, int]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("writer schema output must be an object")
        key, format_name, version = (
            entry.get("output_key"),
            entry.get("format"),
            entry.get("schema_version"),
        )
        if (
            not isinstance(key, str)
            or key in result
            or not isinstance(format_name, str)
            or not format_name
            or type(version) is not int
            or version <= 0
        ):
            raise ValueError("writer schema output format/version is invalid")
        result[key] = (format_name, version)
    if set(result) != expected:
        raise ValueError("writer schema output set differs from reservations")
    return result


def active_configuration_document(
    configuration: pb.ExperimentConfiguration,
) -> dict[str, object]:
    """Persist effective active settings without reusable PFS payloads or dormant values."""
    public = deepcopy(configuration)
    selected = [deepcopy(item) for item in public.backends if item.enabled]
    public.ClearField("backends")
    for setting in selected:
        if setting.backend_name == "acquisition":
            for camera in (
                setting.acquisition.behavioral,
                setting.acquisition.tracking,
                setting.acquisition.eye_tracking,
            ):
                if not camera.HasField("enabled") or not camera.enabled:
                    camera.ClearField("device")
                    camera.ClearField("ffmpeg_args")
                    camera.ClearField("sdk_buffer_count")
                    camera.ClearField("recording_bit_depth")
                    camera.ClearField("save_video")
                else:
                    camera.device.ClearField("pfs_baseline")
        public.backends.add().CopyFrom(setting)
    return message_dict(public)
