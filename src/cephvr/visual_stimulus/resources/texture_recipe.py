"""Bounded JSON-only compatibility for legacy CephVR texture designs.

Pixel formulas follow ``protocol/src/vr_backend/rendering/texture_gen.py`` and
``builder/texture_designer.py`` from CephVR1.0 (source parity reference).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, RootModel

from cephvr.visual_stimulus.config.models.schema_common import (
    DEFAULT_DOCUMENT_BYTES,
    parse_json,
)

if TYPE_CHECKING:
    import numpy as np

DEFAULT_TEXTURE_RESOLUTION = 512


class _JsonObject(RootModel[dict[str, Any]]):
    model_config = ConfigDict(strict=True)


_ALIASES = {
    "substrate": "filtered_noise",
    "vertical_bars": "bars_vertical",
    "horizontal_bars": "bars_horizontal",
    "frustum_calibration_grid": "calibration_grid",
    "frustrum_calibration_grid": "calibration_grid",
    "sine": "grating",
    "sine_grating": "grating",
    "polar": "polar_grating",
    "radial_bars": "polar_grating",
    "radial_grating": "polar_grating",
    "solid": "flat",
}
_SUPPORTED = {
    "grating",
    "polar_grating",
    "checker",
    "dots_grid",
    "dots_rand",
    "noise_binary",
    "noise_gray",
    "filtered_noise",
    "bars_horizontal",
    "bars_vertical",
    "calibration_grid",
    "flat",
    "image",
}
_NUMERIC_PARAMS = {
    "texture_resolution",
    "size",
    "tile_width_mm",
    "tile_height_mm",
    "screen_width_mm",
    "density",
    "element_size",
    "blur",
    "orientation_deg",
    "contrast",
    "mean_luminance",
    "phase_cycles",
    "phase",
    "feature_sharpness",
    "sharpness",
    "cycles_per_texture",
    "spatial_freq_cpd",
    "spatial_period_px",
    "spatial_period_mm",
    "bar_count",
    "angular_period_deg",
    "bar_width_mm",
    "line_width_mm",
    "inner_radius_mm",
    "outer_radius_mm",
    "cell_size_mm",
    "spacing_mm",
    "dot_diameter_mm",
    "density_per_cm2",
    "tile_size_mm",
    "seed",
    "line_spacing_mm",
    "color_count",
    "style_cycle_count",
    "vertical_color_offset",
    "horizontal_color_offset",
    "dash_length_mm",
    "dash_gap_mm",
    "features_per_tile",
    "bandwidth_octaves",
    "scale_mm",
    "edge_smooth_mm",
    "black_fraction",
    "blur_mm",
}
_BOOL_PARAMS = {"tile_local", "fit_cycles_to_tile", "seamless", "seamless_texture"}
_COLOR_PARAMS = {"color_a", "color_b", "foreground", "background"}
_SURFACE_PARAMS = {"origin_screen", "origin_face", "target_screen", "target_face"}


@dataclass(frozen=True)
class TextureRecipe:
    pattern: str
    params: dict[str, object]
    resolution: int
    tile_width_mm: float | None
    tile_height_mm: float | None
    physical_field: bool = False


def parse_texture_recipe(
    raw: bytes,
    *,
    max_document_bytes: int = DEFAULT_DOCUMENT_BYTES,
    max_texture_pixels: int | None = None,
) -> TextureRecipe:
    """Parse a tagged export or legacy plain JSON design into a bounded recipe."""
    document_limit = _positive_integer(
        max_document_bytes, "Texture recipe document limit"
    )
    if not isinstance(raw, bytes) or len(raw) > document_limit:
        raise ValueError("Texture recipe exceeds the JSON document limit.")
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Texture recipe must be valid UTF-8 JSON.") from exc
    data = parse_json(_JsonObject, source, max_bytes=document_limit).root
    if data.get("kind") not in (None, "texture"):
        raise ValueError("Texture recipe kind must be 'texture'.")
    asset_type = data.get("cephvr_asset_type")
    field = asset_type == "texture_field"
    if field and (
        type(data.get("format_version")) is not int or data["format_version"] != 1
    ):
        raise ValueError("Unsupported physical texture field version")
    if asset_type not in (None, "texture_design", "texture_field"):
        raise ValueError(
            "Texture recipe asset type must be 'texture_design' or 'texture_field'."
        )
    if asset_type is None and not any(
        key in data for key in ("pattern", "params", "pattern_params", "preview_file")
    ):
        raise ValueError("Untagged JSON does not contain legacy texture recipe fields.")
    params_value = data.get("params", data.get("pattern_params", {}))
    if not isinstance(params_value, dict):
        raise ValueError("Texture recipe params must be an object.")
    params = dict(params_value)
    _validate_known_params(params)
    if "size" in data and data["size"] not in (None, ""):
        _positive_integer(data["size"], "Texture size")
    pattern_text = data.get("pattern", "grating")
    if not isinstance(pattern_text, str):
        raise ValueError("Texture recipe pattern must be a string.")
    pattern = pattern_text.strip().lower()
    pattern = _ALIASES.get(pattern, pattern)
    if pattern not in _SUPPORTED:
        raise ValueError(f"Unsupported legacy texture pattern: {pattern_text!r}.")
    if field:
        from cephvr.visual_stimulus.resources.physical_field import validate_field

        if (
            data.get("kind") != "texture"
            or "params" not in data
            or "pattern" not in data
        ):
            raise ValueError("Physical field requires kind, pattern and params")
        if data.keys() - {
            "cephvr_asset_type",
            "format_version",
            "kind",
            "pattern",
            "params",
        }:
            raise ValueError("Unsupported physical field document fields")
        validate_field(pattern, params)
        return TextureRecipe(
            pattern, params, DEFAULT_TEXTURE_RESOLUTION, None, None, True
        )
    resolution_raw = params.get(
        "texture_resolution",
        params.get("size", data.get("size", DEFAULT_TEXTURE_RESOLUTION)),
    )
    if resolution_raw in (None, ""):
        resolution_raw = DEFAULT_TEXTURE_RESOLUTION
    resolution = _positive_integer(resolution_raw, "Texture resolution")
    if max_texture_pixels is not None and resolution * resolution > _positive_integer(
        max_texture_pixels, "Texture pixel limit"
    ):
        raise ValueError("Texture resolution exceeds the configured allocation limit.")
    tile_width = _optional_positive_finite(params.get("tile_width_mm"), "Tile width")
    tile_height = _optional_positive_finite(params.get("tile_height_mm"), "Tile height")
    if tile_height is None and tile_width is not None:
        tile_height = tile_width
    for key, value in _walk_scalars(params):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Texture parameter {key!r} must be finite.")
    return TextureRecipe(pattern, params, resolution, tile_width, tile_height)


def estimated_working_bytes(recipe: TextureRecipe) -> int:
    """Conservative procedural scratch estimate; image bytes use source dimensions."""
    if recipe.physical_field or recipe.pattern == "image":
        return 0
    pixels = recipe.resolution * recipe.resolution
    # Covers coordinate grids, RGB mixes, and FFT fields that coexist at peaks.
    return pixels * 192


def generate_texture_recipe(
    recipe: TextureRecipe,
    *,
    surface_corners: Mapping[str, object] | None = None,
    image_pixels: np.ndarray | None = None,
    check: Callable[[], None] | None = None,
    extent_mm: tuple[float, float] = (100.0, 100.0),
    sample_size: tuple[int, int] | None = None,
    offset_mm: tuple[float, float] = (0.0, 0.0),
) -> np.ndarray:
    """Generate RGB8 pixels; image data must be supplied as decoded RGB pixels."""
    if check is not None:
        check()
    import numpy as np

    if recipe.physical_field:
        from cephvr.visual_stimulus.resources.physical_field import raster_field

        nx, ny = sample_size or (recipe.resolution, recipe.resolution)
        return raster_field(
            recipe.pattern,
            recipe.params,
            *extent_mm,
            nx,
            ny,
            offset_mm=offset_mm,
            check=check or (lambda: None),
        )

    if recipe.pattern == "image":
        if image_pixels is None:
            raise ValueError(
                "Image texture recipes require explicitly decoded image pixels."
            )
        image = np.asarray(image_pixels)
        if image.dtype != np.uint8 or image.ndim not in {2, 3}:
            raise ValueError(
                "Decoded image pixels must be an 8-bit grayscale, RGB, or RGBA array."
            )
        if image.shape[0] < 1 or image.shape[1] < 1:
            raise ValueError("Decoded image pixels must have positive dimensions.")
        if image.ndim == 2:
            image = np.repeat(image[:, :, None], 3, axis=2)
        elif image.shape[2] == 1:
            image = np.repeat(image, 3, axis=2)
        elif image.shape[2] == 4:
            image = image[:, :, :3]
        elif image.shape[2] != 3:
            raise ValueError("Decoded image pixels must have 1, 3, or 4 channels.")
        if check is not None:
            check()
        return np.ascontiguousarray(image)
    if recipe.pattern == "polar_grating" and not recipe.params.get("tile_local", False):
        if surface_corners is None:
            raise ValueError(
                "Polar texture generation requires explicit surface corners."
            )
    from cephvr.visual_stimulus.resources.texture_recipe_patterns import (
        generate_pattern,
    )

    result = generate_pattern(
        recipe.pattern,
        recipe.params,
        recipe.resolution,
        surface_corners=surface_corners,
        max_dot_primitives=recipe.resolution * recipe.resolution,
        check=check,
    )
    if check is not None:
        check()
    if result.dtype != np.uint8 or result.shape != (
        recipe.resolution,
        recipe.resolution,
        3,
    ):
        raise ValueError("Texture generator returned an invalid RGB8 image.")
    return np.ascontiguousarray(result)


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer.")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise ValueError(f"{name} must be a positive integer.")
    return int(number)


def _optional_positive_finite(value: object, name: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be finite and positive.") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive.")
    return number


def _walk_scalars(value: object, key: str = "") -> Iterator[tuple[str, float]]:
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _walk_scalars(child, str(child_key))
    elif isinstance(value, list):
        for child in value:
            yield from _walk_scalars(child, key)
    elif isinstance(value, float):
        yield key, value
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return
        if not math.isfinite(number):
            raise ValueError(f"Texture parameter {key!r} must be finite.")


def _validate_known_params(params: dict[str, object]) -> None:
    maps = [params]
    nested = params.get("pattern_params")
    if "pattern_params" in params and not isinstance(nested, dict):
        raise ValueError("Texture parameter 'pattern_params' must be an object.")
    if isinstance(nested, dict):
        maps.append(nested)
    for values in maps:
        for key, value in values.items():
            if key in _NUMERIC_PARAMS:
                if key in {"texture_resolution", "size"}:
                    if value not in (None, ""):
                        _positive_integer(value, f"Texture parameter {key}")
                else:
                    _finite_parameter_number(value, key)
            elif key in _BOOL_PARAMS:
                _validate_boolean(value, key)
            elif key in _COLOR_PARAMS:
                _validate_color(value, key)
            elif key in _SURFACE_PARAMS:
                if value is None:
                    continue
                if not isinstance(value, str):
                    raise ValueError(f"Texture parameter {key!r} must name a surface.")
                normalized = value.strip().lower()
                if normalized not in {
                    "front",
                    "left",
                    "right",
                    "bottom",
                    "screen_front",
                    "screen_left",
                    "screen_right",
                    "screen_bottom",
                    "top",
                }:
                    raise ValueError(
                        f"Texture parameter {key!r} names an unknown surface."
                    )


def _finite_parameter_number(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Texture parameter {name!r} must be numeric.")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Texture parameter {name!r} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"Texture parameter {name!r} must be finite.")
    return number


def _validate_boolean(value: object, name: str) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value in (0, 1):
            return
    if isinstance(value, str) and value.strip().lower() in {
        "0",
        "1",
        "true",
        "false",
        "yes",
        "no",
        "on",
        "off",
    }:
        return
    raise ValueError(f"Texture parameter {name!r} must be a boolean flag.")


def _validate_color(value: object, name: str) -> None:
    if isinstance(value, str):
        color = value.strip().lstrip("#")
        if len(color) == 6:
            try:
                int(color, 16)
                return
            except ValueError:
                pass
    elif isinstance(value, list) and len(value) >= 3:
        for channel in value[:3]:
            _finite_parameter_number(channel, name)
        return
    raise ValueError(
        f"Texture parameter {name!r} must be a six-digit hex or RGB color."
    )
