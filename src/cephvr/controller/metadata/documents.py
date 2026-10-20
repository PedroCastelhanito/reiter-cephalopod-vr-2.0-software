"""E04 active configuration and Protobuf metadata document construction."""

from __future__ import annotations

from copy import deepcopy

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.state import Attempt, SupervisorState


def message_dict(message: Message) -> dict[str, object]:
    return MessageToDict(message, preserving_proto_field_name=True)


def projector_brightness_schema() -> dict[str, object]:
    """Describe observed SDK evidence separately from calibration or live measurement."""
    return {
        "schema_version": 1,
        "scope": "latest admitted adjustment in this controller lifetime; all discovered USB interfaces, not display assignments",
        "unknown": "no observed adjustment; requested current and readbacks absent",
        "fields": {
            "controller_generation": "exact observer process generation",
            "command_id": "exact accepted operator/parent operation UUID",
            "configuration_revision": "revision at adjustment admission",
            "requested_ma": "requested equal RGB LED current in mA; not measured luminance",
            "started_monotonic_ns": "host monotonic ns at admission",
            "completed_monotonic_ns": "host monotonic ns at operator outcome observation",
            "started_utc": "UTC observation time at admission",
            "completed_utc": "UTC observation time at operator outcome",
            "outcome": "unknown | succeeded | failed | unconfirmed",
            "native_cleanup_confirmed": "exact process/job/pipe and supervisor release; not USB state or RGB current proof",
            "sdk_result": "null if no complete validated helper result; otherwise requested_ma, discovered_interfaces, success and interfaces",
            "sdk_result.interfaces": "ordered index/name/id, readback_ma RGB or null, clamped bool or null, confirmed, release_confirmed, error; every discovered interface accounted",
            "diagnostics": "human SDK diagnostics tail, at most6000 characters",
            "error": "overall failure/uncertainty detail; empty on success",
        },
        "clamp": "request above1023 with all RGB readbacks1023 is explicitly clamped, not requested=applied",
        "freshness": "historical observation; external TI tools or power changes are not monitored",
    }


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
