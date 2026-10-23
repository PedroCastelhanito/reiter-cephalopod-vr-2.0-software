"""Group compatible motion instruments without losing face identity or units."""

import json
from dataclasses import replace
from typing import Any

from cephvr.gui.preview_motion_samples import SourcePanel


def shared_panel_groups(panels: list[SourcePanel]) -> dict[tuple[str, str], set[str]]:
    faces = {panel.source.key[0] for panel in panels}
    eligible = {
        face
        for face in faces
        if all(
            p.form == "texture" and not p.arena and not p.driving
            for p in panels
            if p.source.key[0] == face
        )
    }
    groups: dict[tuple[str, str], set[str]] = {}
    for panel in panels:
        face = panel.source.key[0]
        if face in eligible:
            groups.setdefault((panel.form, panel.source.unit), set()).add(face)
    return groups


def combined_panels(panels: list[SourcePanel]) -> list[SourcePanel]:
    grouped: dict[str, list[SourcePanel]] = {}
    for panel in panels:
        values: list[dict[str, Any] | None] = []
        for setting in panel.source.settings:
            if setting is None:
                values.append(None)
                continue
            value = setting.model_dump(mode="json")
            # Keep coordinate transforms, units, feedback and phase/size functions.
            for key in (
                "asset_id",
                "opacity",
                "mean_linear_rgb",
                "modulation_linear_rgb",
                "contrast",
                "sampling",
                "fit",
            ):
                value.pop(key, None)
            values.append(value)
        # Face transforms and instance history can differ even with equal motions.
        key = json.dumps(
            (panel.source.key[0], panel.source.unit, panel.form, values), sort_keys=True
        )
        grouped.setdefault(key, []).append(panel)
    result = []
    for group in grouped.values():
        first = group[0]
        if len(group) == 1:
            result.append(first)
            continue
        names = " / ".join(panel.source.name for panel in group)
        source = replace(first.source, name=names)
        result.append(replace(first, source=source))
    return result
