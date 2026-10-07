"""Machine-independent screen profile references and explicit native rebinding."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from cephvr.gui.calibration_profile import MonitorBinding, active_monitor_bindings
from cephvr.gui.projector_geometry import FACES


def portable_profile(document: dict[str, Any]) -> dict[str, Any]:
    """Keep surface corrections and profile policy, dropping physical bindings."""
    json.dumps(document, allow_nan=False)
    profile = copy.deepcopy(document)
    outputs = profile.pop("outputs", None)
    profile.pop("photodiode_output_id", None)
    mappings = profile.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("Screen profile requires a mapping array")
    roles: dict[str, str] = {}
    for mapping in mappings:
        if not isinstance(mapping, dict) or mapping.get("surface_id") not in {
            face.lower() for face in FACES
        }:
            raise ValueError("Screen profile mappings require known rig surfaces")
        output_id = mapping.pop("output_id", None)
        if isinstance(output_id, str):
            role = roles.setdefault(output_id, mapping["surface_id"])
            mapping["projector_role"] = role
        if mapping.get("projector_role", mapping["surface_id"]) not in {
            face.lower() for face in FACES
        }:
            raise ValueError("Screen profile requires known logical projector roles")
    if isinstance(outputs, list):
        profile["output_settings"] = {
            roles[output["output_id"]]: {
                key: value
                for key, value in output.items()
                if key
                not in {
                    "output_id",
                    "device_identity",
                    "width_px",
                    "height_px",
                    "refresh_numerator",
                    "refresh_denominator",
                    "enabled",
                }
            }
            for output in outputs
            if isinstance(output, dict) and output.get("output_id") in roles
        }
    settings = profile.get("output_settings", {})
    if not isinstance(settings, dict) or any(
        role not in {face.lower() for face in FACES}
        or not isinstance(value, dict)
        or set(value)
        & {
            "output_id",
            "device_identity",
            "width_px",
            "height_px",
            "refresh_numerator",
            "refresh_denominator",
            "enabled",
        }
        for role, value in settings.items()
    ):
        raise ValueError("Output settings must exclude physical display bindings")
    return profile


def bind_profile(
    profile: dict[str, Any],
    outputs: list[dict[str, Any]],
    assignments: Mapping[str, str],
) -> dict[str, Any]:
    """Bind portable surface references to the current machine's explicit choices."""
    document = copy.deepcopy(profile)
    document["outputs"] = copy.deepcopy(outputs)
    settings = document.pop("output_settings", {})
    for output in document["outputs"]:
        role = assignments.get(output["device_identity"], "").lower()
        output.update(settings.get(role, {}))
    by_face = {
        assignments.get(output["device_identity"], "").lower(): output["output_id"]
        for output in outputs
    }
    for mapping in document["mappings"]:
        role = mapping.pop("projector_role", mapping["surface_id"])
        face = mapping["surface_id"] if mapping["surface_id"] in by_face else role
        if face not in by_face:
            raise ValueError(f"Assign a current display to {face.title()} first")
        mapping["output_id"] = by_face[face]
    return document


def current_outputs(
    known_outputs: list[dict[str, Any]],
    assignments: Mapping[str, str],
    participation: Mapping[str, bool],
    *,
    native: bool,
) -> list[dict[str, Any]]:
    """Retain explicit output properties; inspect new native bindings when needed."""
    known = {output["device_identity"]: output for output in known_outputs}
    identities = [key for key, face in assignments.items() if face != "Unassigned"]
    bindings: tuple[MonitorBinding, ...] = ()
    if any(key not in known for key in identities):
        if not native:
            raise ValueError(
                "Runtime screen profiles require actual native display properties"
            )
        bindings = active_monitor_bindings()
    monitors = {binding.interface: binding for binding in bindings}
    result = []
    for key in identities:
        if key in known:
            result.append(dict(known[key]))
        elif key in monitors:
            binding = monitors[key]
            result.append(
                dict(
                    output_id=f"gui-{assignments[key].lower()}",
                    device_identity=key,
                    enabled=participation.get(key, True),
                    width_px=binding.width,
                    height_px=binding.height,
                    refresh_numerator=binding.refresh_hz,
                    refresh_denominator=1,
                    rgb_bits_per_channel=binding.rgb_bits,
                )
            )
        else:
            raise ValueError(f"Assigned display is not available: {key}")
    return result
