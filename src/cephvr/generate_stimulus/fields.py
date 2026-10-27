"""Human labels and numeric control limits for property forms, without widgets."""

from dataclasses import dataclass
from typing import Any, get_args

from pydantic import BaseModel

UNITS = (
    ("_per_cm2", " (/cm²)"),
    ("_mm", " (mm)"),
    ("_deg", " (°)"),
    ("_octaves", " (octaves)"),
)
# Wording shared with the epoch editor's grating and sparse-noise controls.
LABELS = {
    "color": "Color (linear RGBA)",
    "color_a": "Color A (linear RGB)",
    "color_b": "Color B (linear RGB)",
    "background_linear": "Background (linear)",
    "feature_sharpness": "Sharpness (0–1)",
    "min_active_cell_distance_mm": "Minimum distance (mm)",
    "active_probability": "Active probability",
    "alpha_cutoff": "Alpha cutoff (0–1)",
    "clustering": "Clustering (0–1)",
    "orientation_deg": "Orientation (°)",
    "texture_scale_mm": "Texture scale (mm)",
    "density_per_cm2": "Density (/cm²)",
    "model": "Model (GLB)",
}
SURFACE_NAMES = {
    "floor": "Floor",
    "roof": "Roof",
    "wall_n": "Wall N",
    "wall_s": "Wall S",
    "wall_e": "Wall E",
    "wall_w": "Wall W",
}
PATTERN_NAMES = {
    "grating": "Grating",
    "polar_grating": "Polar grating",
    "checker": "Checkerboard",
    "dots_grid": "Dot grid",
    "dots_rand": "Random dots",
    "noise_binary": "Binary noise",
    "noise_gray": "Gray noise",
    "filtered_noise": "Filtered noise",
    "bars_horizontal": "Horizontal bars",
    "bars_vertical": "Vertical bars",
    "calibration_grid": "Calibration grid",
    "flat": "Flat color",
    "image": "Image tile",
    "sparse_noise": "Sparse noise",
}
HINTS = {
    "active_probability": "Independent activation probability per eligible cell and pattern (0–1).",
    "min_active_cell_distance_mm": "Minimum center-to-center distance in mm. A new eligible layout is generated for each pattern; 0 allows all cells.",
    "feature_sharpness": "0 = sinusoidal; 1 = square bars; intermediate values soften the edges.",
    "clustering": "Probability that an object is placed beside the previous one instead of at random (0–1).",
}
ARRAY_HINT = "Values in brackets; colors are linear channels from 0 to 1"
# Control limits mirroring physical_field.validate_field; the backend stays the validator.
TEXTURE_LIMITS = {
    "density": (0.0, 1.0),
    "black_fraction": (0.0, 1.0),
    "feature_sharpness": (0.0, 1.0),
    "bar_count": (1.0, 10000.0),
    "color_count": (2.0, 16.0),
    "bandwidth_octaves": (0.0, 8.0),
    "density_per_cm2": (0.0, 1e6),
}
ZERO_MM = frozenset(
    {"blur_mm", "edge_smooth_mm", "inner_radius_mm", "outer_radius_mm", "dash_gap_mm"}
)
FINITE = 1e9


def humanize(text: str) -> str:
    """Capitalize a snake_case or UPPER identifier for display."""
    text = text.replace("_", " ")
    if text.isupper():
        text = text.lower()
    return text[:1].upper() + text[1:]


def label_for(key: str) -> str:
    if key in LABELS:
        return LABELS[key]
    for suffix, unit in UNITS:
        if key.endswith(suffix):
            return humanize(key[: -len(suffix)]) + unit
    return humanize(key)


@dataclass(frozen=True)
class NumberSpec:
    integer: bool
    minimum: float
    maximum: float
    step: float

    @property
    def decimals(self) -> int:
        return 0 if self.integer else 3


def submodel(model: type[BaseModel] | None, key: str) -> type[BaseModel] | None:
    """Nested model of a field, looking through list and optional wrappers."""
    info = None if model is None else model.model_fields.get(key)
    if info is None:
        return None
    for candidate in (info.annotation, *get_args(info.annotation)):
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    return None


def number_spec(model: type[BaseModel] | None, key: str, value: Any) -> NumberSpec:
    """Widget type and limits from the model's field metadata, else texture hints."""
    info = None if model is None else model.model_fields.get(key)
    low, high = -FINITE, FINITE
    exclusive = False
    if info is not None:
        integer = info.annotation is int
        for rule in info.metadata:
            for name in ("ge", "gt", "le", "lt"):
                bound = getattr(rule, name, None)
                if bound is None:
                    continue
                if name in {"ge", "gt"}:
                    low, exclusive = float(bound), name == "gt"
                else:
                    high = float(bound)
    else:
        integer = type(value) is int
        if key in TEXTURE_LIMITS:
            low, high = TEXTURE_LIMITS[key]
        elif key.endswith("_mm"):
            low = 0.0 if key in ZERO_MM else 0.001
    if exclusive:
        low += 1 if integer else 0.001
    step = 1.0 if integer or high - low > 1 else 0.05
    return NumberSpec(integer, low, high, step)
