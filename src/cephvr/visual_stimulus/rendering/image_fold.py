"""Physical unfolded image coordinates, shared by renderer and planning preview."""

from collections.abc import Mapping, Sequence
from math import dist, isfinite

from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.rendering.image_fit import screen_image_frame

Point = tuple[float, float]


def output_axes(profile: GeometricProfile) -> tuple[Point, Point, Point]:
    """Output pixel position and derivatives for surface UV coordinates."""
    screen_image_frame(profile)  # Reject unsupported affine/sheared mappings first.
    viewport = profile.viewport
    return affine_output_axes(
        [v.uv for v in profile.vertices],
        [
            (
                viewport.x + v.xy[0] * viewport.width,
                viewport.y + v.xy[1] * viewport.height,
            )
            for v in profile.vertices
        ],
    )


def affine_output_axes(
    source: Sequence[Point], target: Sequence[Point]
) -> tuple[Point, Point, Point]:
    """Recover an affine source-UV to output-pixel map from noncollinear points."""
    a, b = source[:2]
    du, dv = b[0] - a[0], b[1] - a[1]
    for index, c in enumerate(source[2:], 2):
        target_c = target[index]
        eu, ev = c[0] - a[0], c[1] - a[1]
        determinant = du * ev - dv * eu
        if abs(determinant) > 1e-12:
            break
    else:
        raise ValueError("Fold requires nondegenerate calibration")
    axes = []
    for axis in (0, 1):
        db, dc = (
            target[1][axis] - target[0][axis],
            target_c[axis] - target[0][axis],
        )
        u, v = (db * ev - dc * dv) / determinant, (dc * du - db * eu) / determinant
        axes.append((target[0][axis] - u * a[0] - v * a[1], u, v))
    return (axes[0][0], axes[1][0]), (axes[0][1], axes[1][1]), (axes[0][2], axes[1][2])


def fold_map(
    extents: Mapping[str, Point],
    front_pitch: Point,
    face: str,
    corners: Sequence[Point],
    axes: tuple[Point, Point, Point],
) -> tuple[float, ...]:
    """Top-left source pixels for local quad origin, horizontal and vertical axes.

    The net starts at the bounding rectangle's top left. Bottom sits below the
    top-aligned Left/Front/Right row in output orientation. Unused source is cropped.
    """
    if set(extents) != {"left", "front", "right", "bottom"} or any(
        not isfinite(v) or v <= 0
        for pair in (*extents.values(), front_pitch)
        for v in pair
    ):
        raise ValueError(
            "Fold requires four physical screen extents and Front pixel scale"
        )
    sizes = dict(extents)
    sizes["bottom"] = sizes["bottom"][::-1]
    lw, _ = sizes["left"]
    fw, _ = sizes["front"]
    bw, _ = sizes["bottom"]
    row_height = max(sizes[face][1] for face in ("left", "front", "right"))
    bx = lw + (fw - bw) / 2
    shift = max(0.0, -bx)
    positions = {
        "left": (shift, 0.0),
        "front": (shift + lw, 0.0),
        "right": (shift + lw + fw, 0.0),
        "bottom": (shift + bx, row_height),
    }
    origin, dx, dy = axes
    rotated = abs(dx[1]) > abs(dx[0])
    if rotated != (face == "bottom"):
        raise ValueError(
            "Fold requires portrait Bottom and landscape side calibration axes"
        )
    # Output offsets/flips affect presentation, but do not relocate the net.
    projected = [
        (origin[i] + dx[i] * u + dy[i] * v)
        for i in (0, 1)
        for u, v in ((0, 0), (1, 0), (0, 1), (1, 1))
    ]
    lows = (min(projected[:4]), min(projected[4:]))
    spans = (max(projected[:4]) - lows[0], max(projected[4:]) - lows[1])
    if min(spans) <= 0:
        raise ValueError("Fold calibration has empty projected extent")

    def sample(point: Point) -> Point:
        u, v = ((component + 1) / 2 for component in point)
        x, y = (
            (origin[i] + dx[i] * u + dy[i] * v - lows[i]) / spans[i] for i in (0, 1)
        )
        return (
            (positions[face][0] + x * sizes[face][0]) / front_pitch[0],
            (positions[face][1] + (1 - y) * sizes[face][1]) / front_pitch[1],
        )

    a, b, c = (sample(corners[i]) for i in (0, 1, 3))
    return (*a, b[0] - a[0], b[1] - a[1], c[0] - a[0], c[1] - a[1])


def calibrated_fold_map(
    geometry: Geometry,
    profiles: Sequence[GeometricProfile],
    profile: GeometricProfile,
) -> tuple[float, ...]:
    """Resolve Front reference scale from retained calibration, never output guesses."""
    fronts = [p for p in profiles if p.surface_id == "front"]
    if len(fronts) != 1:
        raise ValueError(
            "Fold requires exactly one prepared Front calibration; enable Front"
        )
    extents: dict[str, Point] = {
        s.surface_id: (
            dist(s.bottom_left_mm, s.bottom_right_mm),
            dist(s.bottom_left_mm, s.top_left_mm),
        )
        for s in geometry.surfaces
    }
    _, dx, dy = output_axes(fronts[0])
    if abs(dx[0]) < 1e-12 or abs(dy[1]) < 1e-12:
        raise ValueError("Fold Front reference requires landscape calibration axes")
    pitch = (extents["front"][0] / abs(dx[0]), extents["front"][1] / abs(dy[1]))
    corners, _ = screen_image_frame(profile)
    return fold_map(extents, pitch, profile.surface_id, corners, output_axes(profile))
