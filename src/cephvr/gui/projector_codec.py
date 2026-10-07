"""Patch projector-owned fields in bounded imported experiment profiles."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from cephvr.visual_stimulus.v1 import runtime_pb2

_MAX_PROFILE_BYTES = 16_777_216
_FACES = frozenset({"front", "left", "right", "bottom"})


def _unique_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate display profile member: {key}")
        result[key] = value
    return result


def display_document(display: runtime_pb2.DisplayConfiguration) -> dict[str, Any]:
    """Read bounded JSON while leaving full canonical validation to the controller."""
    if not display.profile_json:
        raise ValueError("Import a display profile before configuring projectors")
    if len(display.profile_json.encode("utf-8")) > _MAX_PROFILE_BYTES:
        raise ValueError("Display profile exceeds the 16 MiB configuration limit")

    def invalid_constant(value: str) -> None:
        raise ValueError(f"nonfinite display profile number: {value}")

    value = json.loads(
        display.profile_json,
        object_pairs_hook=_unique_members,
        parse_constant=invalid_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("Display profile must be a JSON object")
    return value


def merge_projector_draft(
    base: runtime_pb2.DisplayConfiguration,
    *,
    assignments: Mapping[str, str],
    participation: Mapping[str, bool],
    pulse_enabled: bool,
    pulse_output_identity: str | None,
    presentation_mode: str,
    pulse_patch: Mapping[str, Any] | None,
    geometry: Mapping[str, object] | None,
) -> runtime_pb2.DisplayConfiguration:
    """Update this page's fields without normalizing unrelated calibration data."""
    document = display_document(base)
    outputs = document.get("outputs")
    mappings = document.get("mappings")
    if not isinstance(outputs, list) or not isinstance(mappings, list):
        raise ValueError("Display profile requires output and mapping arrays")
    outputs_by_identity = {
        item["device_identity"]: item
        for item in outputs
        if isinstance(item, dict) and isinstance(item.get("device_identity"), str)
    }
    for identity, enabled in participation.items():
        output = outputs_by_identity.get(identity)
        if output is not None:
            if type(enabled) is not bool:
                raise ValueError("Display participation must be true or false")
            output["enabled"] = enabled

    face_outputs: dict[str, str] = {}
    for identity, face in assignments.items():
        normalized = face.lower()
        if normalized not in _FACES:
            continue
        output = outputs_by_identity.get(identity)
        if output is None:
            raise ValueError(
                f"Assigned stable display identity is absent from imported profile: {identity}"
            )
        output_id = output.get("output_id")
        if not isinstance(output_id, str) or not output_id:
            raise ValueError(f"{face} output has no stable output ID")
        if normalized in face_outputs and face_outputs[normalized] != output_id:
            raise ValueError(f"More than one display is assigned to {face}")
        face_outputs[normalized] = output_id

    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        surface_id = mapping.get("surface_id")
        if surface_id in face_outputs:
            mapping["output_id"] = face_outputs[surface_id]

    if presentation_mode not in {"all_outputs_vsync", "photodiode_only_vsync"}:
        raise ValueError("Unsupported display presentation mode")
    document["presentation_mode"] = presentation_mode
    if type(pulse_enabled) is not bool:
        raise ValueError("Photodiode enable must be true or false")
    document["photodiode_enabled"] = pulse_enabled
    if pulse_output_identity is not None:
        output = outputs_by_identity.get(pulse_output_identity)
        if output is None or not isinstance(output.get("output_id"), str):
            raise ValueError("Photodiode display is absent from imported profile")
        document["photodiode_output_id"] = output["output_id"]
    if pulse_patch is not None:
        current_patch = document.get("photodiode_patch")
        merged_patch = dict(current_patch) if isinstance(current_patch, dict) else {}
        merged_patch.update(pulse_patch)
        document["photodiode_patch"] = merged_patch
    if geometry is not None:
        document["geometry"] = dict(geometry)

    result = runtime_pb2.DisplayConfiguration()
    result.profile_json = json.dumps(document, allow_nan=False, separators=(",", ":"))
    return result
