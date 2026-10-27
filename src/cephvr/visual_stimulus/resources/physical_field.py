"""Versioned, raster-independent physical texture fields and bounded point sampling."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from statistics import NormalDist
from typing import Any

import numpy as np

from cephvr.visual_stimulus.resources.texture_recipe import validate_color
from cephvr.visual_stimulus.resources.texture_recipe_geometry import mix_rgb, rgb_color
from cephvr.visual_stimulus.resources.texture_recipe_patterns import PALETTE

DEFAULTS: dict[str, dict[str, Any]] = {
    "grating": dict(
        spatial_period_mm=12.0, orientation_deg=90.0, feature_sharpness=1.0
    ),
    "polar_grating": dict(
        bar_count=24,
        bar_width_mm=8.0,
        inner_radius_mm=0.0,
        outer_radius_mm=0.0,
        phase_deg=0.0,
    ),
    "checker": dict(cell_size_mm=25.0, blur_mm=0.0),
    "dots_grid": dict(spacing_mm=25.0, dot_diameter_mm=6.0, blur_mm=0.0),
    "dots_rand": dict(density_per_cm2=1.0, dot_diameter_mm=6.0, blur_mm=0.0, seed=0),
    "noise_binary": dict(density=0.5, element_size_mm=1.0, blur_mm=0.0, seed=0),
    "noise_gray": dict(density=0.5, element_size_mm=1.0, blur_mm=0.0, seed=0),
    "filtered_noise": dict(
        scale_mm=25.0,
        bandwidth_octaves=1.0,
        black_fraction=0.5,
        edge_smooth_mm=0.0,
        seed=0,
    ),
    "bars_horizontal": dict(bar_width_mm=5.0, blur_mm=0.0),
    "bars_vertical": dict(bar_width_mm=5.0, blur_mm=0.0),
    "calibration_grid": dict(
        line_spacing_mm=25.0,
        line_width_mm=5.0,
        color_count=8,
        dash_length_mm=12.5,
        dash_gap_mm=12.5,
    ),
    "flat": {},
}


def candidate_assets(node: Any, setting: Any) -> tuple[object, ...]:
    """Base asset plus every Asset-rule candidate the setting's instance may draw."""
    base = getattr(
        getattr(setting, "pattern", None),
        "asset_id",
        getattr(setting, "asset_id", None),
    )
    rules = (
        rule
        for rule in getattr(node, "repetition_rules", ())
        if getattr(rule, "instance_id", None) == setting.instance_id
    )
    return (base, *(a for rule in rules for a in getattr(rule, "asset_ids", ())))


def epoch_settings(node: Any) -> Iterator[Any]:
    """Base settings and every per-repetition settings row of an epoch."""
    for settings in (node.settings, *getattr(node, "repetition_settings", ())):
        yield from settings


def validate_field_uses(nodes: Any, identities: set[str]) -> None:
    for node in nodes:
        if getattr(node, "kind", "epoch") == "group":
            validate_field_uses(node.body, identities)
            continue
        for setting in epoch_settings(node):
            if any(
                isinstance(asset_id, str) and asset_id in identities
                for asset_id in candidate_assets(node, setting)
            ) and (
                setting.kind != "texture" or setting.space.kind != "physical_surface"
            ):
                raise ValueError(
                    "Physical texture fields require physical-surface texture placement"
                )


def validate_field(pattern: str, params: dict[str, object]) -> None:
    if pattern not in DEFAULTS:
        raise ValueError("Unsupported physical texture field")
    unknown = params.keys() - DEFAULTS[pattern].keys() - {"color_a", "color_b"}
    if unknown:
        raise ValueError(f"Unsupported physical field parameters: {sorted(unknown)}")
    for key in ("color_a", "color_b"):
        color = params.get(key)
        if color is not None:
            validate_color(list(color) if isinstance(color, tuple) else color, key)
    for key, default in DEFAULTS[pattern].items():
        value = params.get(key, default)
        if key == "seed":
            if type(value) is not int or not 0 <= value <= 2**64 - 1:
                raise ValueError("Field seed must be an unsigned 64-bit integer")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Field {key} must be numeric")
        if not math.isfinite(value) or abs(value) > 1e9:
            raise ValueError(f"Field {key} exceeds finite physical bounds")
        if key.endswith("_mm"):
            minimum = (
                0
                if key
                in {
                    "blur_mm",
                    "edge_smooth_mm",
                    "inner_radius_mm",
                    "outer_radius_mm",
                    "dash_gap_mm",
                }
                else 0.001
            )
            if value < minimum:
                raise ValueError(f"Field {key} must be at least {minimum} mm")
        if (
            key in {"density", "black_fraction", "feature_sharpness"}
            and not 0 <= value <= 1
        ):
            raise ValueError(f"Field {key} must be in [0,1]")
        if key in {"seed", "bar_count", "color_count"} and (
            value != int(value) or value < 0
        ):
            raise ValueError(f"Field {key} must be a nonnegative integer")
    p = parameters(pattern, params)
    if pattern == "dots_rand":
        if not 0 <= p["density_per_cm2"] <= 1e6:
            raise ValueError("Random-dot density exceeds physical field work limit")
        if dot_neighbours(p) > 8:
            raise ValueError(
                "Random-dot diameter/density exceeds physical field work limit"
            )
    if pattern == "polar_grating" and not 1 <= p["bar_count"] <= 10000:
        raise ValueError("Polar bar count must be in [1,10000]")
    if pattern == "calibration_grid" and not 2 <= p["color_count"] <= 16:
        raise ValueError("Grid color count must be in [2,16]")
    if pattern == "filtered_noise" and not 0 <= p["bandwidth_octaves"] <= 8:
        raise ValueError("Noise bandwidth must be in [0,8] octaves")
    if (
        pattern in {"noise_binary", "noise_gray"}
        and p["blur_mm"] > p["element_size_mm"] / 2
    ):
        raise ValueError("Noise blur must not exceed half its physical element size")


def parameters(pattern: str, params: dict[str, object]) -> dict[str, Any]:
    return {**DEFAULTS[pattern], **params}


def dot_neighbours(p: dict[str, Any]) -> int:
    pitch = math.sqrt(25 / max(p["density_per_cm2"], 1e-30))
    return int(math.ceil((p["dot_diameter_mm"] / 2 + p["blur_mm"]) / pitch)) + 1


def spectral_terms(p: dict[str, Any]) -> np.ndarray:
    """Fixed seed-owned waves: no FFT window, quantile or extent-dependent randomness."""
    rng = np.random.default_rng(int(p["seed"]))
    angle = rng.uniform(0, math.tau, 32)
    frequency = (
        np.exp2(rng.uniform(-0.5, 0.5, 32) * p["bandwidth_octaves"]) / p["scale_mm"]
    )
    return np.column_stack(
        (np.cos(angle) * frequency, np.sin(angle) * frequency, rng.uniform(0, 1, 32))
    )


def threshold(p: dict[str, Any]) -> float:
    return NormalDist().inv_cdf(min(1 - 1e-9, max(1e-9, p["black_fraction"])))


def _hash(x: np.ndarray, y: np.ndarray, seed: int) -> np.ndarray:
    # Via int64 so negative cells wrap modulo 2**32 like GLSL uint(ivec2); a direct
    # float->uint32 cast is undefined for negatives.
    with np.errstate(over="ignore"):
        h = (
            x.astype(np.int64).astype(np.uint32) * np.uint32(0x1F123BB5)
            ^ y.astype(np.int64).astype(np.uint32) * np.uint32(0x5F356495)
            ^ np.uint32(seed32(seed))
        )
        h = (h ^ (h >> np.uint32(16))) * np.uint32(0x7FEB352D)
        h = (h ^ (h >> np.uint32(15))) * np.uint32(0x846CA68B)
        h ^= h >> np.uint32(16)
    return np.asarray((h >> np.uint32(8)).astype(np.float64) / 16777216)


def seed32(seed: int) -> int:
    return (seed ^ (seed >> 32)) & 0xFFFFFFFF


def sample_field(
    pattern: str,
    params: dict[str, object],
    x: Any,
    y: Any,
    *,
    check: Callable[[], None] = lambda: None,
) -> np.ndarray:
    """Sample physical points in mm; output rows follow the supplied coordinates."""
    validate_field(pattern, params)
    check()
    p = parameters(pattern, params)
    x, y = np.broadcast_arrays(
        np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    )
    if (
        not np.isfinite(x).all()
        or not np.isfinite(y).all()
        or max(np.max(np.abs(x)), np.max(np.abs(y))) > 1e8
    ):
        raise ValueError("Field sample coordinates exceed finite physical bounds")
    edge = p.get("blur_mm", 0)

    def mask(distance: Any, blur: float = edge) -> Any:
        if blur <= 0:
            return np.asarray(distance) >= 0
        t = np.clip(0.5 + np.asarray(distance) / (2 * blur), 0, 1)
        return t * t * (3 - 2 * t)

    if pattern == "grating":
        angle = math.radians(p["orientation_deg"])
        wave = np.sin(
            math.tau
            * (x * math.cos(angle) + y * math.sin(angle))
            / p["spatial_period_mm"]
        )
        alpha = 0.5 + 0.5 * wave
        sharp = p["feature_sharpness"]
        bright = alpha * (1 - sharp) + mask(alpha - 0.5, 0.5 * (1 - sharp)) * sharp
    elif pattern == "polar_grating":
        angle = np.arctan2(y, x) + math.radians(p["phase_deg"])
        period = math.tau / p["bar_count"]
        delta = np.mod(angle + period / 2, period) - period / 2
        radius = np.hypot(x, y)
        bright = mask(p["bar_width_mm"] / 2 - radius * np.abs(np.sin(delta)))
        bright &= (radius >= p["inner_radius_mm"]) & (
            (p["outer_radius_mm"] == 0) | (radius <= p["outer_radius_mm"])
        )
    elif pattern in {"checker", "bars_horizontal", "bars_vertical"}:
        cell = p.get("cell_size_mm", p.get("bar_width_mm", 5))
        a = np.cos(math.pi * x / cell)
        b = np.cos(math.pi * y / cell)
        distance = (
            (
                a * b
                if pattern == "checker"
                else b
                if pattern == "bars_horizontal"
                else a
            )
            * cell
            / math.pi
        )
        bright = mask(distance)
    elif pattern == "dots_grid":
        pitch = p["spacing_mm"]
        dx, dy = (
            np.mod(x + pitch / 2, pitch) - pitch / 2,
            np.mod(y + pitch / 2, pitch) - pitch / 2,
        )
        bright = mask(p["dot_diameter_mm"] / 2 - np.hypot(dx, dy))
    elif pattern == "dots_rand":
        bright = np.zeros(x.shape)
        if p["density_per_cm2"] > 0:
            pitch = math.sqrt(25 / p["density_per_cm2"])
            cx, cy = np.floor(x / pitch), np.floor(y / pitch)
            radius = p["dot_diameter_mm"] / 2
            reach = dot_neighbours(p)
            seed = int(p["seed"])
            for j in range(-reach, reach + 1):
                check()
                for i in range(-reach, reach + 1):
                    ix, iy = cx + i, cy + j
                    # Only the ~25% active cells need the jitter hashes and distance.
                    active = _hash(ix, iy, seed) < 0.25
                    ix, iy = ix[active], iy[active]
                    dx = x[active] - (ix + _hash(ix, iy, seed ^ 12345)) * pitch
                    dy = y[active] - (iy + _hash(ix, iy, seed ^ 67890)) * pitch
                    bright[active] = np.maximum(
                        bright[active], mask(radius - np.hypot(dx, dy))
                    )
    elif pattern in {"noise_binary", "noise_gray"}:
        cell = p["element_size_mm"]

        def noise(ix: Any, iy: Any) -> Any:
            value = _hash(ix, iy, int(p["seed"]))
            if pattern == "noise_binary":
                return (value < p["density"]).astype(float)
            return np.where(
                _hash(ix, iy, int(p["seed"]) ^ 54321) < p["density"], value, 0
            )

        if edge == 0:
            bright = noise(np.floor(x / cell), np.floor(y / cell))
        else:
            ix, iy = np.floor(x / cell - 0.5), np.floor(y / cell - 0.5)
            ux = mask((x / cell - 0.5 - ix - 0.5) * cell)
            uy = mask((y / cell - 0.5 - iy - 0.5) * cell)
            lo = noise(ix, iy) * (1 - ux) + noise(ix + 1, iy) * ux
            hi = noise(ix, iy + 1) * (1 - ux) + noise(ix + 1, iy + 1) * ux
            bright = lo * (1 - uy) + hi * uy
    elif pattern == "filtered_noise":
        value = np.zeros(x.shape)
        for fx, fy, phase in spectral_terms(p):
            check()
            value += np.cos(math.tau * (x * fx + y * fy + phase)) / 4
        bright = mask(value - threshold(p), p["edge_smooth_mm"] / p["scale_mm"])
        if p["black_fraction"] in (0, 1):
            bright = np.full(x.shape, 1 - p["black_fraction"])
    elif pattern == "calibration_grid":
        pitch = p["line_spacing_mm"]
        dx, dy = (
            np.abs(np.mod(x + pitch / 2, pitch) - pitch / 2),
            np.abs(np.mod(y + pitch / 2, pitch) - pitch / 2),
        )
        bright = np.minimum(dx, dy) <= p["line_width_mm"] / 2
        dash = p["dash_length_mm"] + p["dash_gap_mm"]
        bright &= np.mod(np.where(dx < dy, y, x), dash) < p["dash_length_mm"]
    else:
        bright = np.ones(x.shape)
    a = rgb_color(p.get("color_a"), (255, 255, 255))
    b = rgb_color(p.get("color_b"), (0, 0, 0))
    check()
    if pattern == "calibration_grid":
        index = np.floor(np.where(dx < dy, x, y) / pitch + 0.5).astype(int) % int(
            p["color_count"]
        )
        foreground = PALETTE[index].astype(float) * np.asarray(a) / 255
        return np.asarray(
            np.rint(
                np.asarray(b) + np.asarray(bright)[..., None] * (foreground - b)
            ).astype(np.uint8)
        )
    return mix_rgb(b, a, np.asarray(bright, dtype=np.float64))


def raster_field(
    pattern: str,
    params: dict[str, object],
    width_mm: float,
    height_mm: float,
    nx: int,
    ny: int,
    *,
    offset_mm: tuple[float, float] = (0, 0),
    check: Callable[[], None] = lambda: None,
) -> np.ndarray:
    if (
        not all(math.isfinite(v) and v > 0 for v in (width_mm, height_mm))
        or min(nx, ny) <= 0
    ):
        raise ValueError("Field sampling dimensions must be finite and positive")
    # Top-down image rows; physical Y points up, matching the live GL coordinates.
    x = (np.arange(nx) + 0.5) * width_mm / nx - width_mm / 2 + offset_mm[0]
    y = height_mm / 2 - (np.arange(ny) + 0.5) * height_mm / ny + offset_mm[1]
    result = np.empty((ny, nx, 3), dtype=np.uint8)
    for row in range(0, ny, 32):
        check()
        result[row : row + 32] = sample_field(
            pattern, params, x[None, :], y[row : row + 32, None], check=check
        )
    return result
