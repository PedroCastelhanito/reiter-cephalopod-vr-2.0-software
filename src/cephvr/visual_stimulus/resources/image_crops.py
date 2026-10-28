"""Prepared Fold sample rectangles in the original surface framebuffer grid."""

from dataclasses import dataclass
from math import ceil, floor

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.rendering.image_fit import screen_image_frame
from cephvr.visual_stimulus.rendering.image_fold import calibrated_fold_map

from .image_source import ImageSource


@dataclass(frozen=True, slots=True)
class ImageCrop:
    output_id: str
    x: int
    y: int
    width: int
    height: int
    offset: int
    target: tuple[int, int]
    corners: tuple[tuple[float, float], ...]
    fold: tuple[float, ...]
    mapping_id: str


def fold_crop(
    artifact: PreparedTrial, mapping_id: str, source: ImageSource
) -> ImageCrop:
    """Preserve original sampling/rasterization; crop the resulting sample grid."""
    profile = next(
        p for p in artifact.geometric_calibration if p.mapping_id == mapping_id
    )
    corners, _ = screen_image_frame(profile)
    fold = calibrated_fold_map(
        artifact.display.geometry, artifact.geometric_calibration, profile
    )
    x, y, ux, uy, vx, vy = fold
    points = ((x, y), (x + ux, y + uy), (x + vx, y + vy), (x + ux + vx, y + uy + vy))
    if any(
        px < -1e-5
        or py < -1e-5
        or px > source.width + 1e-5
        or py > source.height + 1e-5
        for px, py in points
    ):
        raise ValueError(
            f"Fold source {source.width}x{source.height} does not cover {profile.surface_id}"
        )
    target = (profile.viewport.width, profile.viewport.height)
    if profile.valid_area is not None and profile.calibration_id.startswith(
        ("reference_", "diagnostic_")
    ):
        a, b, c, d = profile.valid_area
        target = (
            round((c - a) * profile.output_width),
            round((d - b) * profile.output_height),
        )
        if profile.vertices[1].uv[0] == profile.vertices[0].uv[0]:
            target = target[::-1]
    # Keep original viewport and include a pixel halo for clip-edge rounding.
    lo = tuple(
        max(0, floor((min(c[i] for c in corners) + 1) * target[i] / 2) - 1)
        for i in (0, 1)
    )
    hi = tuple(
        min(target[i], ceil((max(c[i] for c in corners) + 1) * target[i] / 2) + 1)
        for i in (0, 1)
    )
    if any(hi[i] <= lo[i] for i in (0, 1)):
        raise ValueError("Fold crop has no raster coverage")
    return ImageCrop(
        profile.output_id,
        lo[0],
        lo[1],
        hi[0] - lo[0],
        hi[1] - lo[1],
        0,
        target,
        tuple(corners),
        fold,
        mapping_id,
    )
