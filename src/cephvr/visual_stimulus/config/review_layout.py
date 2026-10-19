"""Calibrated screen crops and equal-cell review geometry, independent of pixels."""

from __future__ import annotations

from collections.abc import Mapping
from math import ceil, floor
from typing import Literal

from cephvr.visual_stimulus.config.models.artifact_models import (
    CompositeTile,
    GeometricProfile,
    PreparedTrial,
    ReviewLayout,
)
from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    PixelRect,
)

SURFACE_ORDER = ("left", "front", "right", "bottom")
LABEL_HEIGHT = 24


def screen_crops(
    display: DisplayProfile, profiles: Mapping[str, object] | None = None
) -> tuple[tuple[str, str, PixelRect], ...]:
    """Use declared valid-area/coverage bounds; black stimulus pixels never crop."""
    result = []
    for output in display.active_outputs:
        mappings = [
            m for m in display.active_mappings if m.output_id == output.output_id
        ]
        bounds = []
        for mapping in mappings:
            profile = profiles.get(mapping.mapping_id) if profiles is not None else None
            if profiles is not None and not isinstance(profile, GeometricProfile):
                raise ValueError(f"review crop lacks calibration: {mapping.mapping_id}")
            if isinstance(profile, GeometricProfile):
                area = profile.valid_area
                if area is None:
                    points = profile.intended_coverage
                    area = (
                        min(p[0] for p in points),
                        min(p[1] for p in points),
                        max(p[0] for p in points),
                        max(p[1] for p in points),
                    )
            else:
                area = (0.0, 0.0, 1.0, 1.0)
            if isinstance(profile, GeometricProfile) and profile.valid_area is not None:
                bounds.append(
                    (
                        ceil(area[0] * output.width_px - 0.5),
                        ceil(area[1] * output.height_px - 0.5),
                        ceil(area[2] * output.width_px - 0.5),
                        ceil(area[3] * output.height_px - 0.5),
                    )
                )
                continue
            viewport = mapping.viewport
            bounds.append(
                (
                    viewport.x + floor(area[0] * viewport.width),
                    viewport.y + floor(area[1] * viewport.height),
                    viewport.x + ceil(area[2] * viewport.width),
                    viewport.y + ceil(area[3] * viewport.height),
                )
            )
        x, y = min(b[0] for b in bounds), min(b[1] for b in bounds)
        right, top = max(b[2] for b in bounds), max(b[3] for b in bounds)
        crop = PixelRect(x=x, y=y, width=right - x, height=top - y)
        DisplayProfile._check_rect(crop, output)
        faces = sorted({m.surface_id for m in mappings}, key=SURFACE_ORDER.index)
        result.append((output.output_id, " / ".join(f.title() for f in faces), crop))
    result.sort(
        key=lambda item: (SURFACE_ORDER.index(item[1].split(" / ")[0].lower()), item[0])
    )
    return tuple(result)


def review_layout(
    display: DisplayProfile,
    scale: int = 1,
    profiles: Mapping[str, object] | None = None,
    *,
    layout_version: Literal[2, 3] = 3,
) -> ReviewLayout:
    crops = screen_crops(display, profiles)
    return layout_from_crops(display, crops, scale, layout_version=layout_version)


def recording_layout(
    display: DisplayProfile, scale: int = 1, *, layout_version: Literal[2, 3] = 3
) -> ReviewLayout:
    outputs = {o.output_id: o for o in display.active_outputs}
    crops = tuple(
        (
            identity,
            label,
            PixelRect(
                x=0,
                y=0,
                width=outputs[identity].width_px,
                height=outputs[identity].height_px,
            ),
        )
        for identity, label, _ in screen_crops(display)
    )
    return layout_from_crops(
        display, crops, scale, kind="recording", layout_version=layout_version
    )


def layout_from_crops(
    display: DisplayProfile,
    crops: tuple[tuple[str, str, PixelRect], ...],
    scale: int,
    *,
    kind: Literal["recording", "preview"] = "preview",
    layout_version: Literal[2, 3] = 3,
) -> ReviewLayout:
    if type(scale) is not int or scale < 1:
        raise ValueError("review scale must be positive")
    if kind == "preview" and tuple(label for _, label, _ in crops) == (
        "Left",
        "Front",
        "Right",
        "Bottom",
    ):
        return display_layout(display, crops, scale, layout_version=layout_version)
    oriented_sizes = [
        (c.height, c.width)
        if kind == "recording" and label == "Bottom" and layout_version >= 3
        else (c.width, c.height)
        for _, label, c in crops
    ]
    cell_width = max(w for w, _ in oriented_sizes) // scale
    image_height = max(h for _, h in oriented_sizes) // scale
    if min(cell_width, image_height) < 1:
        raise ValueError("review scale leaves an empty cell")
    # Historical layouts aligned each cell; new two-cell rows align the frame
    # without adding a seam to odd-sized projector images.
    if layout_version == 2:
        cell_width += cell_width % 2
        image_height += image_height % 2
    cell_height = image_height + (LABEL_HEIGHT if layout_version == 2 else 0)
    columns = min(2, len(crops))
    rows = (len(crops) + columns - 1) // columns
    width, height = columns * cell_width, rows * cell_height
    outputs = {o.output_id: o for o in display.active_outputs}
    tiles = []
    for index, (output_id, label, crop) in enumerate(crops):
        row, column = divmod(index, columns)
        x, y = column * cell_width, height - (row + 1) * cell_height
        rotation: Literal[0, 90] = (
            90 if kind == "recording" and label == "Bottom" else 0
        )
        source_width, source_height = (
            (crop.height, crop.width) if rotation else (crop.width, crop.height)
        )
        fit = min(cell_width / source_width, image_height / source_height)
        w, h = max(1, round(source_width * fit)), max(1, round(source_height * fit))
        tiles.append(
            CompositeTile(
                output_id=output_id,
                label=label,
                source_rect=crop,
                rotation_clockwise_degrees=rotation,
                cell=PixelRect(x=x, y=y, width=cell_width, height=cell_height),
                rect=PixelRect(
                    x=x + (cell_width - w) // 2,
                    y=y + (image_height - h) // 2,
                    width=w,
                    height=h,
                ),
                source_code_bits=outputs[output_id].rgb_bits_per_channel,
            )
        )
    return ReviewLayout(
        layout_version=layout_version,
        layout_kind=kind,
        composite_width=width,
        composite_height=height,
        scale_denominator=scale,
        tiles=tuple(tiles),
    )


def display_layout(
    display: DisplayProfile,
    crops: tuple[tuple[str, str, PixelRect], ...],
    scale: int,
    *,
    layout_version: Literal[2, 3] = 3,
) -> ReviewLayout:
    """Unfold the calibrated screen areas; keep the Bottom output's displayed orientation."""
    label_height = LABEL_HEIGHT if layout_version == 2 else 0
    sizes = [(c.width // scale, c.height // scale) for _, _, c in crops]
    if any(min(size) < 1 for size in sizes):
        raise ValueError("review scale leaves an empty screen")
    left, front, right, bottom = sizes
    bottom_x = left[0] + (front[0] - bottom[0]) // 2
    offset = max(0, -bottom_x)
    width = max(sum(w for w, _ in sizes[:3]), bottom_x + bottom[0]) + offset
    height = bottom[1] + label_height + max(h for _, h in sizes[:3]) + label_height
    positions = (
        (offset, bottom[1] + label_height),
        (offset + left[0], bottom[1] + label_height),
        (offset + left[0] + front[0], bottom[1] + label_height),
        (offset + bottom_x, 0),
    )
    outputs = {o.output_id: o for o in display.active_outputs}
    tiles = tuple(
        CompositeTile(
            output_id=identity,
            label=label,
            source_rect=crop,
            source_code_bits=outputs[identity].rgb_bits_per_channel,
            rect=PixelRect(x=x, y=y, width=w, height=h),
            cell=PixelRect(x=x, y=y, width=w, height=h + label_height),
        )
        for (identity, label, crop), (w, h), (x, y) in zip(
            crops, sizes, positions, strict=True
        )
    )
    return ReviewLayout(
        layout_version=layout_version,
        layout_kind="preview",
        composite_width=width,
        composite_height=height,
        scale_denominator=scale,
        tiles=tiles,
    )


def validate_layout(display: DisplayProfile, layout: ReviewLayout) -> None:
    expected = screen_crops(display)
    if len(layout.tiles) != len(expected):
        raise ValueError("review layout output count differs")
    crops = []
    for tile, (output_id, label, _) in zip(layout.tiles, expected, strict=True):
        if (
            tile.output_id != output_id
            or tile.label != label
            or tile.source_rect is None
        ):
            raise ValueError("review layout requires ordered labels and source crops")
        output = next(o for o in display.active_outputs if o.output_id == output_id)
        DisplayProfile._check_rect(tile.source_rect, output)
        crops.append((output_id, label, tile.source_rect))
    canonical = (
        recording_layout(
            display,
            layout.scale_denominator,
            layout_version=2 if layout.layout_version == 2 else 3,
        )
        if layout.layout_kind == "recording"
        else layout_from_crops(
            display,
            tuple(crops),
            layout.scale_denominator,
            layout_version=2 if layout.layout_version == 2 else 3,
        )
    )
    if any(
        getattr(layout, key) != getattr(canonical, key)
        for key in ReviewLayout.model_fields
    ):
        raise ValueError("review crop layout differs from canonical equal-cell fit")


def validate_calibration_snapshot(plan: PreparedTrial) -> None:
    profiles = {p.mapping_id: p for p in plan.geometric_calibration}
    mappings = {m.mapping_id: m for m in plan.display.active_mappings}
    outputs = {o.output_id: o for o in plan.display.active_outputs}
    if (
        len(profiles) != len(plan.geometric_calibration)
        or profiles.keys() != mappings.keys()
    ):
        raise ValueError("calibration snapshot must cover every mapping exactly once")
    for identity, profile in profiles.items():
        mapping = mappings[identity]
        output = outputs[mapping.output_id]
        if (
            profile.output_id != mapping.output_id
            or profile.surface_id != mapping.surface_id
            or profile.viewport != mapping.viewport
            or (profile.output_width, profile.output_height)
            != (output.width_px, output.height_px)
        ):
            raise ValueError("calibration snapshot differs from the display")
    if plan.preview_layout is not None and plan.preview_layout != review_layout(
        plan.display,
        plan.preview_layout.scale_denominator,
        profiles,
        layout_version=2 if plan.preview_layout.layout_version == 2 else 3,
    ):
        raise ValueError("preview layout differs from retained calibration")
    photo_ids = [p.output.output_id for p in plan.photometric_calibration]
    expected = set(outputs) if plan.display.photometric_mode == "calibrated" else set()
    if len(photo_ids) != len(set(photo_ids)) or set(photo_ids) != expected:
        raise ValueError("photometric snapshot differs from active calibrated outputs")


def fit_review_layout(
    display: DisplayProfile,
    maximum: tuple[int, int],
    factor: int = 1,
) -> ReviewLayout:
    if type(factor) is not int or factor < 1 or min(maximum) < 1:
        raise ValueError(
            "positive integer review reduction and encoder dimensions required"
        )
    scale = 1
    while True:
        layout = recording_layout(display, scale)
        if (
            layout.composite_width <= maximum[0]
            and layout.composite_height <= maximum[1]
        ):
            return recording_layout(display, scale * factor)
        scale += 1
