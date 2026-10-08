"""Publish measured affine mappings as new assets without replacing imported warps."""

import hashlib
import json
from pathlib import Path
from typing import Any

from cephvr.gui.calibration_profile import MonitorBinding, face_mapping
from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
from cephvr.visual_stimulus.config.models.schema_common import parse_json


def measured_profiles(
    document: dict[str, Any], calibration: dict[str, object], asset_root: str
) -> dict[str, Any]:
    values = calibration["values"]
    assert isinstance(values, dict)
    selected = {
        face
        for face in ("Front", "Left", "Right", "Bottom")
        if any(
            values.get(f"screens.{face}.reference_{axis}_mm") is not None
            for axis in ("x", "y")
        )
    }
    if not selected:
        return document
    if not asset_root:
        raise ValueError(
            "Choose the Protocol Assets folder before applying reference measurements"
        )
    root = Path(asset_root).resolve()
    display = parse_display_json(
        json.dumps(document, allow_nan=False), max_bytes=16_777_216
    )
    outputs = {output.output_id: output for output in display.active_outputs}
    pending: list[tuple[str, bytes, dict[str, Any]]] = []
    for mapping in document["mappings"]:
        face = mapping["surface_id"].title()
        if face not in selected or mapping["output_id"] not in outputs:
            continue
        output = outputs[mapping["output_id"]]
        viewport = mapping["viewport"]
        if viewport != dict(x=0, y=0, width=output.width_px, height=output.height_px):
            raise ValueError(
                f"{face}: measured affine calibration requires a full-output viewport"
            )
        original = (root / mapping["geometric_profile"]["logical_path"]).resolve()
        if not original.is_relative_to(root):
            raise ValueError("Geometric profile escapes the accepted Assets folder")
        with original.open("rb") as stream:
            source = stream.read(1_048_577)
        if len(source) > 1_048_576:
            raise ValueError("Geometric profile exceeds the 1 MiB GUI limit")
        profile = parse_json(
            GeometricProfile, source.decode("utf-8"), max_bytes=1_048_576
        )
        if (
            not profile.calibration_id.startswith(("diagnostic_", "reference_"))
            or profile.rows != 2
            or profile.columns != 2
            or profile.mask is not None
            or profile.weight is not None
            or profile.overlap_group is not None
        ):
            raise ValueError(
                f"{face}: reference bars cannot replace an imported warp; load a GUI affine calibration profile"
            )
        monitor = MonitorBinding(
            output.device_identity,
            0,
            0,
            output.width_px,
            output.height_px,
            0,
            output.rgb_bits_per_channel,
        )
        vertices, mirrored = face_mapping(calibration, face, monitor)
        corners = tuple(vertices[i]["xy"] for i in (0, 1, 3, 2))
        if mirrored:
            corners = tuple(reversed(corners))
        content = profile.model_dump(mode="json")
        content.update(
            calibration_id=f"reference_{face.lower()}",
            mapping_id=mapping["mapping_id"],
            surface_id=mapping["surface_id"],
            output_id=output.output_id,
            output_width=output.width_px,
            output_height=output.height_px,
            viewport=viewport,
            vertices=vertices,
            orientation="mirrored" if mirrored else "preserving",
            intended_coverage=corners,
        )
        encoded = (
            GeometricProfile.model_validate_json(json.dumps(content))
            .model_dump_json()
            .encode("utf-8")
        )
        digest = hashlib.sha256(encoded).hexdigest()
        logical = f"calibration/reference_{face.lower()}_{digest}.json"
        pending.append((logical, encoded, mapping))
    # Validate every mapping first. Exclusive files never overwrite accepted assets.
    for logical, encoded, mapping in pending:
        destination = (root / logical).resolve()
        if not destination.is_relative_to(root):
            raise ValueError(
                "Generated reference profile escapes the accepted Assets folder"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            with destination.open("rb") as stream:
                existing = stream.read(len(encoded) + 1)
            if existing != encoded:
                raise ValueError("A generated reference calibration asset has changed")
        else:
            with destination.open("xb") as stream:
                stream.write(encoded)
        mapping["geometric_profile"] = dict(logical_path=logical)
    return document
