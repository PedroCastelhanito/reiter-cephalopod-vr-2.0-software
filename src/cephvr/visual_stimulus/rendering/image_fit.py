"""Centered image fit in authored bounds, before surface projection/calibration."""

from math import isfinite


def fitted_uv_scale(
    fit: str, source_aspect: float, target_aspect: float
) -> tuple[float, float]:
    """UV spans above one contain the image; spans below one crop its center."""
    if fit not in {"contain", "cover", "stretch"}:
        raise ValueError("Unsupported image fit")
    if not all(
        isfinite(value) and value > 0 for value in (source_aspect, target_aspect)
    ):
        raise ValueError("Image and target aspect ratios must be positive and finite")
    ratio = target_aspect / source_aspect
    if fit == "contain":
        return (max(1.0, ratio), max(1.0, 1.0 / ratio))
    if fit == "cover":
        return (min(1.0, ratio), min(1.0, 1.0 / ratio))
    return (1.0, 1.0)
