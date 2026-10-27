"""Polar-texture geometry using caller-supplied calibrated surface corners."""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

_FACES = ("front", "left", "right", "bottom")
_FACE_ALIASES = {
    "screen_front": "front",
    "screen_left": "left",
    "screen_right": "right",
    "screen_bottom": "bottom",
    "top": "bottom",
}


def _num(value: object, default: float) -> float:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return result if math.isfinite(result) else float(default)


def _smoothstep(low: float, high: float, values: np.ndarray) -> np.ndarray:
    t = np.clip((values - low) / max(1e-8, high - low), 0, 1)
    return t * t * (3 - 2 * t)


def _color(value: object, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) == 6:
            try:
                return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
            except ValueError:
                return default
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return tuple(
            int(min(1, max(0, _num(value[i], default[i] / 255))) * 255)
            for i in range(3)
        )  # type: ignore[return-value]
    return default


def _mix(
    a: tuple[int, int, int], b: tuple[int, int, int], alpha: np.ndarray
) -> np.ndarray:
    ca, cb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    return np.asarray(
        np.clip(np.rint(ca * (1 - alpha[..., None]) + cb * alpha[..., None]), 0, 255),
        dtype=np.uint8,
    )


def _polar_grating(
    params: dict[str, object], size: int, raw_corners: Mapping[str, object]
) -> np.ndarray:
    if params.get("tile_local", False):
        width = _num(params.get("tile_width_mm"), 100)
        height = _num(params.get("tile_height_mm"), width)
        if min(width, height) <= 0:
            raise ValueError("Polar tile dimensions must be positive")
        axis_a = (((np.arange(size, dtype=np.float32) + 0.5) / size) - 0.5)[
            None, :
        ] * width
        axis_b = (0.5 - ((np.arange(size, dtype=np.float32) + 0.5) / size))[
            :, None
        ] * height
    else:
        corners = _validated_corners(raw_corners)
        origin_face = _face(
            params.get("origin_screen", params.get("origin_face", "front"))
        )
        target_face = _face(
            params.get("target_screen", params.get("target_face", origin_face))
        )
        origin = corners[origin_face]
        target = corners[target_face]
        bl, br, tr, tl = target
        u = ((np.arange(size, dtype=np.float32) + 0.5) / size)[None, :]
        v = (1 - ((np.arange(size, dtype=np.float32) + 0.5) / size))[:, None]
        bottom = (
            bl[None, None, :] * (1 - u[:, :, None]) + br[None, None, :] * u[:, :, None]
        )
        top = (
            tl[None, None, :] * (1 - u[:, :, None]) + tr[None, None, :] * u[:, :, None]
        )
        points = bottom * (1 - v[:, :, None]) + top * v[:, :, None]
        center = np.mean(origin, axis=0)
        obl, obr, _otr, otl = origin
        ua, va = obr - obl, otl - obl
        ua /= np.linalg.norm(ua)
        va /= np.linalg.norm(va)
        relative = points - center
        axis_a = np.tensordot(relative, ua, axes=([2], [0]))
        axis_b = np.tensordot(relative, va, axes=([2], [0]))
    radius = np.sqrt(axis_a * axis_a + axis_b * axis_b)
    angle = np.degrees(np.arctan2(axis_b, axis_a))
    count = max(1, _num(params.get("bar_count"), 24))
    angular = _num(params.get("angular_period_deg"), 0)
    if angular > 0:
        count = max(1, 360 / angular)
    period = 360 / count
    delta = (
        np.mod(
            angle
            + _num(params.get("phase_deg", params.get("phase", 0)), 0)
            + period * 0.5,
            period,
        )
        - period * 0.5
    )
    width = max(
        0.001, _num(params.get("bar_width_mm", params.get("line_width_mm", 8)), 8)
    )
    sharp = min(
        1, max(0, _num(params.get("feature_sharpness", params.get("sharpness", 1)), 1))
    )
    distance = radius * np.abs(np.sin(np.radians(delta)))
    signed = width * 0.5 - distance
    edge = max(1e-5, (1 - sharp) * width * 0.5)
    bright = (
        (signed >= 0).astype(np.float32)
        if sharp >= 0.999
        else _smoothstep(-edge, edge, signed)
    )
    inner, outer = (
        max(0, _num(params.get("inner_radius_mm"), 0)),
        max(0, _num(params.get("outer_radius_mm"), 0)),
    )
    if inner > 0:
        bright = np.where(radius >= inner, bright, 0)
    if outer > 0:
        bright = np.where(radius <= outer, bright, 0)
    if "color_a" in params or "color_b" in params:
        return _mix(
            _color(params.get("color_a"), (255, 255, 255)),
            _color(params.get("color_b"), (0, 0, 0)),
            1 - bright,
        )
    lum = np.clip(
        min(1, max(0, _num(params.get("mean_luminance"), 0.5)))
        + min(1, max(0, _num(params.get("contrast"), 1))) * (bright - 0.5),
        0,
        1,
    )
    return np.repeat(np.round(lum * 255).astype(np.uint8)[:, :, None], 3, axis=2)


def _face(value: object) -> str:
    face = _FACE_ALIASES.get(
        str(value or "front").strip().lower(), str(value or "front").strip().lower()
    )
    if face not in _FACES:
        raise ValueError(f"Unknown polar texture surface: {value!r}.")
    return face


def _validated_corners(raw: Mapping[str, object]) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    aliases = {str(key).strip().lower(): value for key, value in raw.items()}
    for face in _FACES:
        value = aliases.get(face)
        if value is None:
            value = next(
                (
                    val
                    for key, val in aliases.items()
                    if _FACE_ALIASES.get(key, key) == face
                ),
                None,
            )
        try:
            array = np.asarray(value, dtype=np.float32)
        except (TypeError, ValueError):
            raise ValueError(f"Polar texture requires corners for {face}.") from None
        if array.shape != (4, 3) or not np.isfinite(array).all():
            raise ValueError(
                f"Polar texture corners for {face} must be finite (4, 3) coordinates."
            )
        if (
            np.linalg.norm(array[1] - array[0]) <= 1e-6
            or np.linalg.norm(array[3] - array[0]) <= 1e-6
        ):
            raise ValueError(f"Polar texture corners for {face} must span a surface.")
        result[face] = array
    return result
