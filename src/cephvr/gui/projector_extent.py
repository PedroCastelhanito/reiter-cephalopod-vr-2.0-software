"""Resolve centered usable screen extents at independently measured pixel pitches."""

import math
from collections.abc import Mapping, Sequence
from typing import cast

from cephvr.visual_stimulus.config.calibration_bars import reference_scale


def _number(values: Mapping[str, object], key: str, *, optional: bool = False) -> float:
    value = values.get(key)
    if value is None and optional:
        # Zero is not a valid configured length; caller substitutes native defaults.
        from cephvr.visual_stimulus.config.calibration_bars import reference_lengths

        prefix = key.rsplit(".", 1)[0] + "."
        lengths = reference_lengths(
            _number(values, prefix + "reference_width_px"),
            _number(values, prefix + "reference_height_px"),
        )
        return lengths[0 if key.endswith("x_px") else 1]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{key} must be positive and finite")
    return float(value)


def valid_pixels(
    values: Mapping[str, object], face: str, width: int, height: int
) -> tuple[int, int]:
    prefix = f"screens.{face}."
    defaults = [width, height]
    if any(
        values.get(prefix + f"reference_{axis}_mm") is not None for axis in ("x", "y")
    ):
        pitch = measured_pitch(values, face, width, height)
        defaults = [
            min(limit, max(1, round(_number(values, prefix + key) / mm)))
            for key, mm, limit in zip(
                ("width", "height"), pitch, (width, height), strict=True
            )
        ]
    result = []
    for key, default, limit in zip(
        ("valid_width_px", "valid_height_px"), defaults, (width, height), strict=True
    ):
        value = values.get(prefix + key)
        value = default if value is None else value
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not float(value).is_integer()
            or not 1 <= value <= limit
        ):
            raise ValueError(f"{face} {key} must be whole pixels within its display")
        result.append(int(value))
    return result[0], result[1]


def measured_pitch(
    values: Mapping[str, object], face: str, width: int, height: int
) -> tuple[float, float]:
    prefix = f"screens.{face}."
    if (
        values.get(prefix + "reference_width_px"),
        values.get(prefix + "reference_height_px"),
    ) != (width, height):
        raise ValueError(
            f"{face}: reference bars do not match the assigned output mode"
        )
    scale = reference_scale(
        width,
        height,
        _number(values, prefix + "reference_x_mm"),
        _number(values, prefix + "reference_y_mm"),
        x_px=_number(values, prefix + "reference_x_px", optional=True),
        y_px=_number(values, prefix + "reference_y_px", optional=True),
    )
    return scale.projected_width_mm / width, scale.projected_height_mm / height


def pixel_offsets(
    values: Mapping[str, object], face: str, width: int, height: int
) -> tuple[int, int]:
    """Center-relative pixel translations that keep the entire window in bounds."""
    pixels = valid_pixels(values, face, width, height)
    result = []
    for axis, native, size in zip(("x", "y"), (width, height), pixels, strict=True):
        value = values.get(f"screens.{face}.offset_{axis}_px")
        value = 0 if value is None else value
        limit = (native - size) // 2
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not float(value).is_integer()
            or not -limit <= value <= limit
        ):
            raise ValueError(
                f"{face} offset {axis.upper()} must fit its projection image"
            )
        result.append(int(value))
    return result[0], result[1]


def usable_corners(
    corners: Sequence[tuple[float, float, float]],
    values: Mapping[str, object],
    face: str,
    width: int,
    height: int,
) -> list[tuple[float, float, float]]:
    """Keep the measured plane center while cropping/extending its physical view."""
    pixels = valid_pixels(values, face, width, height)
    pitch = measured_pitch(values, face, width, height)
    center = tuple(sum(point[i] for point in corners) / 4 for i in range(3))
    axes = [tuple(corners[j][i] - corners[0][i] for i in range(3)) for j in (1, 3)]
    lengths = [math.sqrt(sum(v * v for v in axis)) for axis in axes]
    return [
        cast(
            tuple[float, float, float],
            tuple(
                center[i]
                + u * axes[0][i] / lengths[0] * pixels[0] * pitch[0] / 2
                + v * axes[1][i] / lengths[1] * pixels[1] * pitch[1] / 2
                for i in range(3)
            ),
        )
        for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]
