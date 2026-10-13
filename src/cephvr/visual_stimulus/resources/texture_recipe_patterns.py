"""Pure NumPy/Pillow port of CephVR1 texture preview pattern functions."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping

import numpy as np

from cephvr.visual_stimulus.resources.texture_recipe_geometry import _polar_grating

_FACES = ("front", "left", "right", "bottom")
_VERTICAL_FACES = ("left", "front", "right")
_FACE_ALIASES = {
    "screen_front": "front",
    "screen_left": "left",
    "screen_right": "right",
    "screen_bottom": "bottom",
    "top": "bottom",
}
_PALETTE = np.array(
    [
        (255, 32, 32),
        (32, 220, 255),
        (255, 220, 32),
        (255, 64, 220),
        (64, 255, 96),
        (96, 96, 255),
        (255, 144, 32),
        (255, 255, 255),
        (160, 96, 255),
        (160, 255, 32),
        (32, 144, 255),
        (255, 112, 160),
        (32, 255, 192),
        (255, 64, 112),
        (192, 192, 192),
        (255, 255, 96),
    ],
    dtype=np.uint8,
)


def generate_pattern(
    pattern: str,
    params: dict[str, object],
    size: int,
    *,
    surface_corners: Mapping[str, object] | None,
    max_dot_primitives: int,
    check: Callable[[], None] | None,
) -> np.ndarray:
    _check(check)
    color_a = _color(
        params.get("color_a", params.get("foreground", (1, 1, 1))), (255, 255, 255)
    )
    color_b = _color(
        params.get("color_b", params.get("background", (0, 0, 0))), (0, 0, 0)
    )
    if pattern == "grating":
        values = dict(params)
        if "spatial_period_mm" in values and "cycles_per_texture" not in values:
            width = _num(
                values.get("tile_width_mm", values.get("screen_width_mm", 104)), 104
            )
            period = max(0.001, _num(values.get("spatial_period_mm"), 12))
            values["cycles_per_texture"] = _safe_ratio(
                width, period, "grating cycle count"
            )
        return _grating(values, size)
    if pattern == "polar_grating":
        return _polar_grating(params, size, surface_corners or {})
    pattern_params = params.get("pattern_params", params)
    p = dict(pattern_params) if isinstance(pattern_params, Mapping) else params
    if pattern == "checker":
        tile = max(0.001, _num(p.get("tile_width_mm"), 104))
        cell_mm = max(0.001, _num(p.get("cell_size_mm"), 25))
        cell_ratio = _safe_ratio(tile, cell_mm, "checker cell count")
        cell_px = 1 if cell_ratio >= size else max(1, size // max(1, round(cell_ratio)))
        parity = (np.arange(size) // cell_px) % 2
        image = np.where(
            ((parity[:, None] + parity[None, :]) % 2 == 0)[:, :, None], color_a, color_b
        ).astype(np.uint8)
        blur_px = _safe_product(
            _safe_ratio(max(0, _num(p.get("blur_mm"), 0)), tile, "checker blur"),
            size,
            "checker blur",
        )
        return _blur(image, blur_px)
    if pattern in {"bars_vertical", "bars_horizontal"}:
        spacing = max(0.001, _num(p.get("line_spacing_mm"), 25))
        tile = max(0.001, _num(p.get("tile_width_mm"), spacing))
        count_value = _safe_ratio(tile, spacing, "bar count")
        if count_value > size:
            raise ValueError("Texture bar count exceeds the raster work limit.")
        count = max(1, round(count_value))
        width_fraction = min(
            1,
            max(
                0,
                _safe_ratio(
                    _num(p.get("line_width_mm"), 5), spacing, "bar width fraction"
                ),
            ),
        )
        indices = _line_indices(size, count, width_fraction, check=check)
        image = np.empty((size, size, 3), dtype=np.uint8)
        image[:] = color_b
        mask = indices >= 0
        if pattern == "bars_vertical":
            image[:, mask] = color_a
        else:
            image[mask, :] = color_a
        blur_px = _safe_product(
            _safe_ratio(max(0, _num(p.get("blur_mm"), 0)), tile, "bar blur"),
            size,
            "bar blur",
        )
        return _blur(image, blur_px)
    if pattern == "calibration_grid":
        return _calibration_grid(size, color_b, p, check=check)
    if pattern == "noise_binary":
        return _noise(size, color_a, color_b, p, binary=True)
    if pattern == "noise_gray":
        return _noise(size, color_a, color_b, p, binary=False)
    if pattern == "filtered_noise":
        return _filtered_noise(size, color_a, color_b, p)
    if pattern in {"dots_grid", "dots_rand"}:
        return _dots(
            size,
            pattern,
            color_a,
            color_b,
            p,
            max_dot_primitives,
            density=_num(params.get("density"), 0.5),
            element_size=_num(params.get("element_size"), 1),
            blur=_num(params.get("blur"), 0),
            check=check,
        )
    return np.full((size, size, 3), color_a, dtype=np.uint8)


def _check(check: Callable[[], None] | None) -> None:
    if check is not None:
        check()


def _num(value: object, default: float) -> float:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return result if math.isfinite(result) else float(default)


def _safe_ratio(numerator: float, denominator: float, name: str) -> float:
    result = numerator / denominator
    if not math.isfinite(result):
        raise ValueError(f"Texture {name} exceeds finite generation bounds.")
    return result


def _safe_product(left: float, right: float, name: str) -> float:
    result = left * right
    if not math.isfinite(result):
        raise ValueError(f"Texture {name} exceeds finite generation bounds.")
    return result


def _safe_sum(left: float, right: float, name: str) -> float:
    result = left + right
    if not math.isfinite(result):
        raise ValueError(f"Texture {name} exceeds finite generation bounds.")
    return result


def _integer(value: object, default: int) -> int:
    try:
        return round(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return default


def _flag(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if value is None:
        return default
    text = str(value).strip().lower()
    return (
        text in {"1", "true", "yes", "on"}
        if text in {"1", "true", "yes", "on", "0", "false", "no", "off"}
        else default
    )


def _color(value: object, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) == 6:
            try:
                return (
                    int(text[0:2], 16),
                    int(text[2:4], 16),
                    int(text[4:6], 16),
                )
            except ValueError:
                return default
    if isinstance(value, (tuple, list)) and len(value) >= 3:

        def channel(index: int) -> int:
            normalized = min(1, max(0, _num(value[index], default[index] / 255)))
            return int(normalized * 255)

        return (
            channel(0),
            channel(1),
            channel(2),
        )
    return default


def _smoothstep(low: float, high: float, values: np.ndarray) -> np.ndarray:
    t = np.clip((values - low) / max(1e-8, high - low), 0, 1)
    return t * t * (3 - 2 * t)


def _mix(
    a: tuple[int, int, int], b: tuple[int, int, int], alpha: np.ndarray
) -> np.ndarray:
    ca, cb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    return np.asarray(
        np.clip(np.rint(ca * (1 - alpha[..., None]) + cb * alpha[..., None]), 0, 255),
        dtype=np.uint8,
    )


def _blur(image: np.ndarray, pixels: float) -> np.ndarray:
    if pixels <= 0:
        return image
    if not math.isfinite(pixels) or pixels > max(image.shape[:2]):
        raise ValueError("Texture blur radius exceeds the raster work limit.")
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        raise ValueError(
            "This texture recipe uses blur_mm and requires Pillow during preparation."
        ) from None

    return np.asarray(
        Image.fromarray(image, mode="RGB").filter(
            ImageFilter.GaussianBlur(float(pixels))
        ),
        dtype=np.uint8,
    )


def _grating(params: dict[str, object], size: int) -> np.ndarray:
    orientation = math.radians(_num(params.get("orientation_deg"), 0))
    contrast = min(1, max(0, _num(params.get("contrast"), 1)))
    mean = min(1, max(0, _num(params.get("mean_luminance"), 0.5)))
    phase = _num(params.get("phase_cycles", params.get("phase", 0)), 0)
    sharpness = min(
        1, max(0, _num(params.get("feature_sharpness", params.get("sharpness", 0)), 0))
    )
    cycles = _num(
        params.get("cycles_per_texture", params.get("spatial_freq_cpd", 4)), 4
    )
    fit = _flag(
        params.get(
            "fit_cycles_to_tile",
            params.get("seamless", params.get("seamless_texture", True)),
        ),
        True,
    )
    if "spatial_period_px" in params:
        period = max(1, _num(params.get("spatial_period_px"), 64))
        if fit:
            cycles = max(1, math.floor(abs(size / period) + 0.5))
            period = max(1, size / cycles)
    elif "spatial_period_mm" in params and "tile_width_mm" in params:
        cycles = max(
            0.001,
            _safe_ratio(
                _num(params.get("tile_width_mm"), 100),
                max(0.001, _num(params.get("spatial_period_mm"), 12)),
                "grating cycle count",
            ),
        )
        if fit:
            cycles = max(1, math.floor(abs(cycles) + 0.5))
        period = max(1, size / max(0.01, abs(cycles)))
    else:
        if fit:
            cycles = max(1, math.floor(abs(cycles) + 0.5))
        period = max(1, size / max(0.01, abs(cycles)))
    coords = (np.arange(size, dtype=np.float32) + 0.5) - 0.5 * size
    x, y = np.meshgrid(coords, coords)
    wave = np.sin(
        2
        * math.pi
        * ((x * math.cos(orientation) + y * math.sin(orientation)) / period + phase)
    )
    alpha = 0.5 - 0.5 * wave
    if sharpness > 0:
        width = 0.5 * (1 - sharpness)
        shaped = (
            (alpha >= 0.5).astype(np.float32)
            if width <= 1e-4
            else _smoothstep(0.5 - width, 0.5 + width, alpha)
        )
        alpha = np.clip(alpha * (1 - sharpness) + shaped * sharpness, 0, 1)
    if "color_a" in params or "color_b" in params:
        return _mix(
            _color(params.get("color_a"), (255, 255, 255)),
            _color(params.get("color_b"), (0, 0, 0)),
            alpha,
        )
    luminance = np.clip(mean + 0.5 * contrast * (1 - 2 * alpha), 0, 1)
    return np.repeat(np.round(luminance * 255).astype(np.uint8)[:, :, None], 3, axis=2)


def _line_indices(
    size: int,
    count: int,
    width_fraction: float,
    *,
    check: Callable[[], None] | None,
) -> np.ndarray:
    indices = np.full(size, -1, dtype=np.int32)
    if width_fraction <= 0:
        return indices
    cell = size / count
    half = max(0.5, cell * min(1, width_fraction) * 0.5)
    for index in range(count):
        _check(check)
        center = (index + 0.5) * cell
        start, end = (
            max(0, int(np.floor(center - half))),
            min(size, int(np.ceil(center + half))),
        )
        if start >= end:
            indices[min(size - 1, max(0, round(center)))] = index
        else:
            indices[start:end] = index
    return indices


def _calibration_grid(
    size: int,
    background: tuple[int, int, int],
    params: dict[str, object],
    *,
    check: Callable[[], None] | None,
) -> np.ndarray:
    image = np.empty((size, size, 3), dtype=np.uint8)
    image[:] = background
    colors = min(16, max(2, _integer(params.get("color_count"), 8)))
    cycles = min(2, max(1, _integer(params.get("style_cycle_count"), 1)))
    count = colors * cycles
    spacing = max(0.001, _num(params.get("line_spacing_mm"), 25))
    width = min(
        1,
        max(
            0,
            _safe_ratio(
                _num(params.get("line_width_mm"), 5),
                spacing,
                "grid line width fraction",
            ),
        ),
    )
    ix = _line_indices(size, count, width, check=check)
    iy = _line_indices(size, count, width, check=check)
    vertical, horizontal = ix >= 0, iy >= 0
    palette = _PALETTE[:colors]
    vo, ho = (
        _integer(params.get("vertical_color_offset"), 0),
        _integer(params.get("horizontal_color_offset"), 3),
    )
    vertical_style, horizontal_style = (ix // colors) % 2, (iy // colors) % 2
    vs, vd = vertical & (vertical_style == 0), vertical & (vertical_style == 1)
    hs, hd = horizontal & (horizontal_style == 0), horizontal & (horizontal_style == 1)
    spacing_mm = max(0.001, _num(params.get("line_spacing_mm"), 25))
    tile_mm = _safe_product(spacing_mm, count, "calibration grid span")
    if tile_mm > np.finfo(np.float32).max:
        raise ValueError(
            "Texture calibration grid span exceeds finite raster coordinates."
        )
    dash_length = max(0.001, _num(params.get("dash_length_mm"), spacing_mm * 0.5))
    dash_gap = max(0.001, _num(params.get("dash_gap_mm"), spacing_mm * 0.5))
    dash_cycle = _safe_sum(dash_length, dash_gap, "calibration dash cycle")
    axis_mm = ((np.arange(size, dtype=np.float32) + 0.5) / size) * tile_mm
    dash_x = np.mod(axis_mm, dash_cycle) < dash_length
    dash_y = dash_x
    vertical_visible = np.zeros((size, size), dtype=bool)
    horizontal_visible = np.zeros((size, size), dtype=bool)
    if np.any(vs):
        image[:, vs] = palette[(ix[vs] + vo) % colors][None, :, :]
        vertical_visible[:, vs] = True
    if np.any(vd):
        image[np.ix_(dash_y, vd)] = palette[(ix[vd] + vo) % colors][None, :, :]
        vertical_visible[np.ix_(dash_y, vd)] = True
    if np.any(hs):
        image[hs, :] = palette[(iy[hs] + ho) % colors][:, None, :]
        horizontal_visible[hs, :] = True
    if np.any(hd):
        image[np.ix_(hd, dash_x)] = palette[(iy[hd] + ho) % colors][:, None, :]
        horizontal_visible[np.ix_(hd, dash_x)] = True
    both = vertical_visible & horizontal_visible
    if np.any(both):
        y, x = np.nonzero(both)
        a = palette[(ix[x] + vo) % colors].astype(np.uint16)
        b = palette[(iy[y] + ho) % colors].astype(np.uint16)
        image[y, x] = ((a + b) // 2).astype(np.uint8)
    return image


def _noise(
    size: int,
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    params: dict[str, object],
    *,
    binary: bool,
) -> np.ndarray:
    rng = np.random.default_rng(_integer(params.get("seed"), 0))
    noise = rng.random((size, size), dtype=np.float32)
    ca, cb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    if binary:
        return np.where((noise > 0.5)[:, :, None], ca, cb).astype(np.uint8)
    return np.clip(
        np.rint(noise[:, :, None] * ca + (1 - noise[:, :, None]) * cb), 0, 255
    ).astype(np.uint8)


def _filtered_noise(
    size: int,
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    params: dict[str, object],
) -> np.ndarray:
    rng = np.random.default_rng(_integer(params.get("seed"), 0))
    noise = rng.normal(0, 1, (size, size))
    spectrum = np.fft.fft2(noise)
    fx, fy = np.fft.fftfreq(size), np.fft.fftfreq(size)
    radius = np.sqrt(fx[None, :] ** 2 + fy[:, None] ** 2)
    radius[0, 0] = 1e-9
    features = max(1, _num(params.get("features_per_tile"), 32))
    center = features / size
    sigma = max(0.05, _num(params.get("bandwidth_octaves"), 1)) * 0.5
    band = np.exp(-0.5 * (np.log2(radius / center) / sigma) ** 2)
    band[0, 0] = 0
    field = np.fft.ifft2(spectrum * band).real
    tile_mm = _safe_product(
        max(0.001, _num(params.get("scale_mm"), 25)),
        features,
        "filtered-noise tile span",
    )
    smooth_px = _safe_product(
        _safe_ratio(
            max(0, _num(params.get("edge_smooth_mm"), 0)),
            tile_mm,
            "filtered-noise blur",
        ),
        size,
        "filtered-noise blur",
    )
    if smooth_px > 0:
        radius_sq = fx[None, :] ** 2 + fy[:, None] ** 2
        field = np.fft.ifft2(
            np.fft.fft2(field) * np.exp(-2 * np.pi**2 * smooth_px**2 * radius_sq)
        ).real
    fraction = min(0.99, max(0.01, _num(params.get("black_fraction"), 0.5)))
    threshold = float(np.quantile(field, fraction))
    gy = (np.roll(field, -1, axis=0) - np.roll(field, 1, axis=0)) * 0.5
    gx = (np.roll(field, -1, axis=1) - np.roll(field, 1, axis=1)) * 0.5
    distance = (field - threshold) / np.maximum(np.sqrt(gx * gx + gy * gy), 1e-8)
    return _mix(a, b, _smoothstep(-0.5, 0.5, distance))


def _dots(
    size: int,
    pattern: str,
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    params: dict[str, object],
    limit: int,
    *,
    density: float,
    element_size: float,
    blur: float,
    check: Callable[[], None] | None,
) -> np.ndarray:
    image = np.empty((size, size, 3), dtype=np.uint8)
    image[:] = b
    if pattern == "dots_grid" and "spacing_mm" in params:
        spacing = max(0.001, _num(params.get("spacing_mm"), 25))
        tile = max(0.001, _num(params.get("tile_width_mm"), spacing))
        ratio = _safe_ratio(tile, spacing, "dot grid count")
        if ratio > size:
            raise ValueError("Texture dot count exceeds the raster work limit.")
        count = max(1, round(ratio))
        primitive_count = count * count
        if primitive_count > min(limit, size * size):
            raise ValueError("Texture dot count exceeds the raster work limit.")
        radius = max(
            1,
            int(
                _safe_product(
                    _safe_ratio(
                        max(0, _num(params.get("dot_diameter_mm"), 6)),
                        tile,
                        "dot radius",
                    ),
                    size * 0.5,
                    "dot radius",
                )
            ),
        )
        blur = _safe_product(
            _safe_ratio(max(0, _num(params.get("blur_mm"), 0)), tile, "dot blur"),
            size,
            "dot blur",
        )
        centers = [
            int((i * (size / count)) + ((size / count) / 2)) for i in range(count)
        ]
    elif pattern == "dots_rand" and "density_per_cm2" in params:
        tile = max(0.001, _num(params.get("tile_size_mm"), 200))
        tile_cm = tile / 100
        area = _safe_product(tile_cm, tile_cm, "random dot area")
        total_value = _safe_product(
            max(0, _num(params.get("density_per_cm2"), 1)),
            area,
            "random dot count",
        )
        if total_value > min(limit, size * size):
            raise ValueError("Texture dot count exceeds the raster work limit.")
        total = round(total_value)
        radius = max(
            1,
            int(
                _safe_product(
                    _safe_ratio(
                        max(0, _num(params.get("dot_diameter_mm"), 6)),
                        tile,
                        "dot radius",
                    ),
                    size * 0.5,
                    "dot radius",
                )
            ),
        )
        blur = _safe_product(
            _safe_ratio(max(0, _num(params.get("blur_mm"), 0)), tile, "dot blur"),
            size,
            "dot blur",
        )
        centers = []
        primitive_count = total
    elif pattern == "dots_grid":
        grid_extent = _safe_sum(
            4, _safe_product(max(0, density), 20, "dot grid count"), "dot grid count"
        )
        if grid_extent > size + 1:
            raise ValueError("Texture dot count exceeds the raster work limit.")
        grid_count = max(1, int(grid_extent))
        primitive_count = grid_count * grid_count
        if primitive_count > min(limit, size * size):
            raise ValueError("Texture dot count exceeds the raster work limit.")
        step = size / grid_count
        centers = [int(index * step + step / 2) for index in range(grid_count)]
        radius_px = _safe_product(
            _safe_product(step, 0.35, "dot radius"),
            max(0.01, element_size),
            "dot radius",
        )
        radius = max(1, int(radius_px))
        blur = max(0, blur) * 10
    else:
        total_value = _safe_sum(
            20,
            _safe_product(max(0, density), 1000, "random dot count"),
            "random dot count",
        )
        if total_value > min(limit, size * size):
            raise ValueError("Texture dot count exceeds the raster work limit.")
        total = int(total_value)
        radius_px = _safe_product(size * 0.01, max(0.01, element_size), "dot radius")
        radius = max(2, int(radius_px))
        blur = max(0, blur) * 10
        centers = []
        primitive_count = total
    if primitive_count > min(limit, size * size):
        raise ValueError("Texture dot count exceeds the generation work limit.")
    if centers:
        for x in centers:
            for y in centers:
                _check(check)
                _circle(image, x, y, radius, a)
    else:
        rng = random.Random(_integer(params.get("seed"), 0))
        for _ in range(primitive_count):
            _check(check)
            _circle(
                image, rng.randint(0, size - 1), rng.randint(0, size - 1), radius, a
            )
    return _blur(image, blur)


def _circle(
    image: np.ndarray, cx: int, cy: int, radius: float, color: tuple[int, int, int]
) -> None:
    height, width = image.shape[:2]
    edge = 1.0
    margin = int(np.ceil(radius + edge + 1))
    x0, x1 = max(0, cx - margin), min(width, cx + margin + 1)
    y0, y1 = max(0, cy - margin), min(height, cy + margin + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.ogrid[y0:y1, x0:x1]
    distance = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    alpha = np.clip((radius + 0.5 - distance), 0, 1)
    patch = image[y0:y1, x0:x1].astype(np.float32)
    image[y0:y1, x0:x1] = np.clip(
        np.rint(
            patch * (1 - alpha[:, :, None])
            + np.asarray(color, dtype=np.float32) * alpha[:, :, None]
        ),
        0,
        255,
    ).astype(np.uint8)
