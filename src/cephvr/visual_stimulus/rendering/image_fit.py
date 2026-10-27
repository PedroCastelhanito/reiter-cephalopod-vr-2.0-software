"""Centered image fit in authored bounds, before surface projection/calibration."""

from collections.abc import Sequence
from math import ceil, isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile


SCREEN_IMAGE_FITS = frozenset({"resize", "source", "fold"})
SCREEN_CORNERS = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))


def valid_image_pixels(profile: "GeometricProfile") -> tuple[int, int]:
    """Valid output pixel counts in surface-image axes, including quarter turns."""
    area = profile.valid_area
    if area is None:
        width, height = profile.viewport.width, profile.viewport.height
    else:
        width, height = (
            ceil(area[2] * profile.output_width - 0.5)
            - ceil(area[0] * profile.output_width - 0.5),
            ceil(area[3] * profile.output_height - 0.5)
            - ceil(area[1] * profile.output_height - 0.5),
        )
    a, b = profile.vertices[0], profile.vertices[profile.columns - 1]
    if abs(b.uv[1] - a.uv[1]) > abs(b.uv[0] - a.uv[0]):
        width, height = height, width
    if min(width, height) <= 0:
        raise ValueError("Image target has no valid output pixels")
    return width, height


def valid_image_corners(
    source_uv: Sequence[tuple[float, float]],
    output_xy: Sequence[tuple[float, float]],
    area: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    """Fit the usable rectangle through an affine calibration, including cropped UVs."""
    a, b = output_xy[:2]
    for index, c in enumerate(output_xy[2:], 2):
        dx, dy = b[0] - a[0], b[1] - a[1]
        ex, ey = c[0] - a[0], c[1] - a[1]
        determinant = dx * ey - dy * ex
        if abs(determinant) > 1e-12:
            uc = source_uv[index]
            break
    else:
        raise ValueError("Image calibration has no nondegenerate surface")
    ua, ub = source_uv[:2]

    def inverse(x: float, y: float) -> tuple[float, float]:
        s = ((x - a[0]) * ey - (y - a[1]) * ex) / determinant
        t = (dx * (y - a[1]) - dy * (x - a[0])) / determinant
        return (
            ua[0] + s * (ub[0] - ua[0]) + t * (uc[0] - ua[0]),
            ua[1] + s * (ub[1] - ua[1]) + t * (uc[1] - ua[1]),
        )

    if any(
        max(abs(x - y) for x, y in zip(inverse(*xy), uv, strict=True)) > 1e-6
        for xy, uv in zip(output_xy, source_uv, strict=True)
    ):
        raise ValueError(
            "Resize/Source/Fold images require an affine valid-area calibration"
        )
    origin = inverse(0.0, 0.0)
    horizontal, vertical = inverse(1.0, 0.0), inverse(0.0, 1.0)
    if any(
        min(abs(point[i] - origin[i]) for i in (0, 1)) > 1e-6
        for point in (horizontal, vertical)
    ):
        raise ValueError(
            "Resize/Source/Fold images require rectangular calibration axes"
        )
    x0, y0, x1, y1 = area
    points = [inverse(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    u0, v0 = (min(p[i] for p in points) for i in (0, 1))
    u1, v1 = (max(p[i] for p in points) for i in (0, 1))
    return [(2 * u - 1, 2 * v - 1) for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]


def screen_image_frame(
    profile: "GeometricProfile",
) -> tuple[list[tuple[float, float]], tuple[int, int]]:
    viewport = profile.viewport
    x0, y0, x1, y1 = profile.valid_area or (
        viewport.x / profile.output_width,
        viewport.y / profile.output_height,
        (viewport.x + viewport.width) / profile.output_width,
        (viewport.y + viewport.height) / profile.output_height,
    )
    corners = valid_image_corners(
        [v.uv for v in profile.vertices],
        [v.xy for v in profile.vertices],
        (
            (x0 * profile.output_width - viewport.x) / viewport.width,
            (y0 * profile.output_height - viewport.y) / viewport.height,
            (x1 * profile.output_width - viewport.x) / viewport.width,
            (y1 * profile.output_height - viewport.y) / viewport.height,
        ),
    )
    return corners, valid_image_pixels(profile)


def source_rectangles(
    source: tuple[int, int], target: tuple[int, int]
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Integer source crop and destination padding, with odd surplus at right/bottom."""
    if min(*source, *target) <= 0:
        raise ValueError("Image and valid-area dimensions must be positive")
    width, height = min(source[0], target[0]), min(source[1], target[1])
    return (
        ((source[0] - width) // 2, (source[1] - height) // 2, width, height),
        ((target[0] - width) // 2, (target[1] - height) // 2, width, height),
    )


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
