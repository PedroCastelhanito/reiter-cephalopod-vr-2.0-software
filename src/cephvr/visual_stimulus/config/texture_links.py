"""Reference texture motion validation and calibrated surface-vector transport."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cephvr.visual_stimulus.config.models.display_profile import Geometry, Surface
    from cephvr.visual_stimulus.config.models.program_model import (
        Settings,
        TextureSettings,
    )

Vector = tuple[float, float, float]
_MOTION_TARGETS = {"x", "y", "rotation", "phase_x", "phase_y", "period_x", "period_y"}


def validate_links(settings: Sequence[Settings], *, resolved: bool = False) -> None:
    from cephvr.visual_stimulus.config.models.program_model import TextureSettings

    by_id = {s.instance_id: s for s in settings}
    for target in settings:
        if not isinstance(target, TextureSettings) or target.linked_to is None:
            continue
        source = by_id.get(target.linked_to)
        if not isinstance(source, TextureSettings) or source is target:
            raise ValueError("Linked texture requires another active texture reference")
        if source.linked_to is not None:
            raise ValueError(
                "Linked textures must follow an independent reference; chains/cycles are invalid"
            )
        for item in (source, target):
            if (
                item.space.kind != "physical_surface"
                or len(item.space.mappings) != 1
                or item.pattern.kind != "image_tile"
            ):
                raise ValueError(
                    "Linked movement requires one physical screen per image-tile texture"
                )
            if item.motion.x.kind != "hold" or item.motion.y.kind != "hold":
                raise ValueError(
                    "Linked texture movement uses phase drift, not simultaneous layer translation"
                )
            if any(
                binding.target in _MOTION_TARGETS for binding in item.feedback
            ) or any(
                assignment.target in _MOTION_TARGETS for assignment in item.assignments
            ):
                raise ValueError(
                    "Linked movement owns motion and tile periods; motion feedback/assignments conflict"
                )
            for motion in (item.phase_x, item.phase_y, item.motion.rotation):
                if motion.kind != "hold" and (
                    motion.kind != "rate" or motion.function.kind != "constant"
                ):
                    raise ValueError(
                        "Linked movement requires constant speed and angular speed"
                    )
            for period in (item.pattern.period_x, item.pattern.period_y):
                if period.kind != "constant":
                    raise ValueError(
                        "Linked movement requires constant tile dimensions"
                    )
            if resolved:
                rates(item)
        assert (
            source.space.kind == "physical_surface"
            and target.space.kind == "physical_surface"
        )
        if source.space.frame_id != target.space.frame_id:
            raise ValueError("Linked textures must use the same physical frame")
        if source.space.mappings[0].surface_id == target.space.mappings[0].surface_id:
            raise ValueError("Choose a reference on another screen")
        if any(
            m.kind != "hold"
            for m in (target.phase_x, target.phase_y, target.motion.rotation)
        ):
            raise ValueError(
                "A linked texture cannot also own drift or rotation; edit its reference"
            )
        if resolved:
            vx, vy, angular = rates(source)
            if angular and (vx or vy):
                raise ValueError(
                    "Linked movement currently supports drift or rotation separately; use separate epochs for combined motion"
                )


def rates(item: TextureSettings) -> tuple[float, float, float]:
    from cephvr.visual_stimulus.config.models.program_model import ImageTile

    assert isinstance(item.pattern, ImageTile)
    values = []
    for motion in (item.phase_x, item.phase_y, item.motion.rotation):
        if motion.kind == "hold":
            values.append(0.0)
        elif (
            motion.kind == "rate"
            and motion.function.kind == "constant"
            and isinstance(motion.function.value, (int, float))
        ):
            values.append(float(motion.function.value))
        else:
            raise ValueError("Linked movement needs resolved constant rates")
    periods = []
    for period in (item.pattern.period_x, item.pattern.period_y):
        if (
            period.kind != "constant"
            or not isinstance(period.value, (float, int))
            or period.value <= 0
        ):
            raise ValueError("Linked movement needs resolved positive tile dimensions")
        periods.append(float(period.value))
    return -values[0] * periods[0], -values[1] * periods[1], values[2]


def _dot(a: Vector, b: Vector) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _cross(a: Vector, b: Vector) -> Vector:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _sub(a: Vector, b: Vector) -> Vector:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _unit(a: Vector) -> Vector:
    length = math.hypot(*a)
    return a[0] / length, a[1] / length, a[2] / length


def _basis(surface: Surface) -> tuple[Vector, Vector, Vector]:
    right = _unit(_sub(surface.bottom_right_mm, surface.bottom_left_mm))
    up = _unit(_sub(surface.top_left_mm, surface.bottom_left_mm))
    return right, up, _unit(_cross(right, up))


def _fold(vector: Vector, source: Vector, target: Vector) -> Vector:
    cosine = max(-1.0, min(1.0, _dot(source, target)))
    if cosine < -1 + 1e-10:
        raise ValueError(
            "Screen normal is opposite Bottom; unfolded movement is ambiguous"
        )
    axis = _cross(source, target)
    first, second = _cross(axis, vector), _cross(axis, _cross(axis, vector))
    return tuple(vector[i] + first[i] + second[i] / (1 + cosine) for i in range(3))  # type: ignore[return-value]


def _rotate(x: float, y: float, degrees: float) -> tuple[float, float]:
    a = math.radians(degrees)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def linked_rates(
    source: TextureSettings,
    target: TextureSettings,
    geometry: Geometry,
    *,
    source_rotation: float,
    target_rotation: float,
) -> tuple[float, float, float]:
    """Resolve follower phase/rotation rates at the epoch's retained orientations."""
    from cephvr.visual_stimulus.config.models.program_model import (
        ImageTile,
        PhysicalSpace,
    )

    assert isinstance(source.space, PhysicalSpace) and isinstance(
        target.space, PhysicalSpace
    )
    assert isinstance(target.pattern, ImageTile)
    surfaces = {s.surface_id: s for s in geometry.surfaces}
    sm, tm = source.space.mappings[0], target.space.mappings[0]
    sr, su, sn = _basis(surfaces[sm.surface_id])
    tr, tu, tn = _basis(surfaces[tm.surface_id])
    bn = _basis(surfaces["bottom"])[2]
    # Rotation semantics require a physical orientation-preserving similarity map.
    for mapping in (sm, tm):
        a, b = mapping.matrix
        sx, sy = math.hypot(a[0], b[0]), math.hypot(a[1], b[1])
        determinant = a[0] * b[1] - a[1] * b[0]
        if (
            min(sx, sy) <= 1e-12
            or determinant <= 0
            or not math.isclose(sx, sy, rel_tol=1e-9)
            or abs(a[0] * a[1] + b[0] * b[1]) > 1e-9 * sx * sy
        ):
            raise ValueError(
                "Linked movement needs an orientation-preserving uniform-scale surface map"
            )
    vx, vy, angular = rates(source)
    x, y = _rotate(vx, vy, source_rotation)
    a, b = sm.matrix
    determinant = a[0] * b[1] - a[1] * b[0]
    x, y = (b[1] * x - a[1] * y) / determinant, (-b[0] * x + a[0] * y) / determinant
    world: Vector = tuple(x * sr[i] + y * su[i] for i in range(3))  # type: ignore[assignment]
    folded = _fold(_fold(world, sn, bn), bn, tn)
    cosine = _dot(sn, tn)
    if angular and not (
        abs(cosine) < 1e-9 or math.isclose(abs(cosine), 1, abs_tol=1e-9)
    ):
        raise ValueError(
            "Linked rotation requires parallel or perpendicular screen planes"
        )
    if angular:
        cosine = 0.0 if abs(cosine) < 1e-9 else math.copysign(1.0, cosine)
    reference = surfaces[sm.surface_id]
    center: Vector = tuple(
        (a + b) / 2
        for a, b in zip(reference.bottom_left_mm, reference.top_right_mm, strict=True)
    )  # type: ignore[assignment]
    distance = _dot(_sub(center, surfaces[tm.surface_id].bottom_left_mm), tn)
    flow = (0.0, 0.0, 0.0) if angular and abs(cosine) == 1 else _cross(sn, tn)
    world = tuple(
        folded[i] + math.radians(angular) * distance * flow[i] for i in range(3)
    )  # type: ignore[assignment]
    x, y = _dot(world, tr), _dot(world, tu)
    a, b = tm.matrix
    x, y = _rotate(a[0] * x + a[1] * y, b[0] * x + b[1] * y, -target_rotation)
    px, py = target.pattern.period_x, target.pattern.period_y
    assert px.kind == "constant" and py.kind == "constant"
    assert isinstance(px.value, (float, int)) and isinstance(py.value, (float, int))
    result = -x / px.value, -y / py.value, angular * cosine
    if not all(math.isfinite(v) for v in result):
        raise ValueError("Linked texture rate is not finite")
    return result


def validate_spin_pivot(
    source: TextureSettings, geometry: Geometry, position: tuple[float, float] | None
) -> None:
    """Require the retained reference pivot at its calibrated screen center."""
    if not rates(source)[2]:
        return
    assert source.space.kind == "physical_surface"
    mapping = source.space.mappings[0]
    # Surface-local (0, 0) is the calibrated screen center, independent of observer.
    a, b = mapping.matrix
    pivot = (a[2], b[2])
    tolerance = geometry.positional_tolerance_mm * math.hypot(a[0], b[0])
    if position is None or math.dist(position, pivot) > tolerance:
        raise ValueError(
            f"Linked rotation requires reference {source.instance_id!r} centered on its calibrated screen at ({pivot[0]:g}, {pivot[1]:g}) mm; set its initial center and reset state. Drift linking is unaffected."
        )
