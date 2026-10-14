"""Resolve declared arena-file geometry into the existing V16 convex solver input."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from cephvr.visual_stimulus.config.models.artifact_models import CompiledEpoch
from cephvr.visual_stimulus.config.models.program_model import (
    ArenaBoundary,
    ArenaFileRegion,
    ArenaSettings,
    ConvexPolygon,
    TrialArenaBoundaries,
)
from cephvr.visual_stimulus.feedback.arena import inset_convex_polygon
from cephvr.visual_stimulus.resources.budget import PreparationBudget


def geometry_vertices(source: str) -> tuple[tuple[float, float], ...]:
    geometry = json.loads(source)
    if not isinstance(geometry, dict):
        raise ValueError("Arena geometry must be an object")
    vertices: tuple[tuple[float, float], ...]
    shape = geometry.get("shape", "rectangular")
    if shape == "rectangular":
        try:
            width = float(geometry["width"])
            depth = float(
                geometry["depth"] if "depth" in geometry else geometry["height"]
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "Arena geometry requires numeric width and depth/height"
            ) from error
        if width <= 0 or depth <= 0:
            raise ValueError("Arena width/depth must be positive")
        vertices = (
            (-width / 2, -depth / 2),
            (width / 2, -depth / 2),
            (width / 2, depth / 2),
            (-width / 2, depth / 2),
        )
    elif shape == "convex_polygon":
        points = geometry.get("vertices_mm")
        if not isinstance(points, list) or not 3 <= len(points) <= 1024:
            raise ValueError("Declared convex geometry requires 3–1024 vertices")
        if any(not isinstance(point, list) or len(point) != 2 for point in points):
            raise ValueError("Arena geometry vertices must be XY pairs")
        vertices = tuple((float(point[0]), float(point[1])) for point in points)
    else:
        raise ValueError(
            f"Arena-file movement geometry {shape!r} is unsupported; use rectangular/convex geometry"
        )
    return ConvexPolygon(
        kind="convex_polygon_xy", vertices_mm=vertices, margin_mm=0
    ).vertices_mm


def validate_inset_area(region: ConvexPolygon) -> None:
    points = region.vertices_mm
    for (nx, ny), offset in inset_convex_polygon(points, region.margin_mm):
        clipped: list[tuple[float, float]] = []
        for a, b in zip(points, (*points[1:], points[0]), strict=True):
            da = nx * a[0] + ny * a[1] - offset
            db = nx * b[0] + ny * b[1] - offset
            if (da <= 0) != (db <= 0):
                fraction = da / (da - db)
                clipped.append(
                    (a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1]))
                )
            if db <= 0:
                clipped.append(b)
        points = tuple(clipped)
        if len(points) < 3:
            raise ValueError("Arena wall margin empties the movement region")
    area = sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(points, (*points[1:], points[0]), strict=True)
    )
    if area <= 0:
        raise ValueError("Arena wall margin leaves no positive-area movement region")


def resolve_arena_regions(
    boundaries: TrialArenaBoundaries,
    epochs: Sequence[CompiledEpoch],
    geometry_by_asset: Mapping[str, str],
    *,
    budget: PreparationBudget | None = None,
) -> TrialArenaBoundaries:
    resolved: list[ArenaBoundary] = []
    geometry_cache: dict[str, tuple[tuple[float, float], ...]] = {}
    for binding in boundaries.bindings:
        if budget is not None:
            budget.check_cancelled_or_expired()
        settings = [
            setting
            for epoch in epochs
            for setting in epoch.settings
            if isinstance(setting, ArenaSettings)
            and setting.instance_id == binding.instance_id
        ]
        region = binding.region
        if isinstance(region, ArenaFileRegion):
            candidates: list[ConvexPolygon] = []
            seen: set[tuple[object, object]] = set()
            for setting in settings:
                if budget is not None:
                    budget.check_cancelled_or_expired()
                if (
                    not isinstance(setting.asset_id, str)
                    or setting.asset_id not in geometry_by_asset
                ):
                    raise ValueError(
                        f"Arena {binding.instance_id} has no declared geometry in GLB extras.cephvr.metadata.geometry"
                    )
                recipe = (setting.asset_id, setting.asset_to_world)
                if recipe in seen:
                    continue
                seen.add(recipe)
                if setting.asset_id not in geometry_cache:
                    geometry_cache[setting.asset_id] = geometry_vertices(
                        geometry_by_asset[setting.asset_id]
                    )
                vertices = geometry_cache[setting.asset_id]
                matrix = setting.asset_to_world
                if matrix[3] != (0, 0, 0, 1) or matrix[2][:2] != (0, 0):
                    raise ValueError(
                        "Arena-file movement geometry requires a planar affine asset transform"
                    )
                transformed = tuple(
                    (
                        matrix[0][0] * x + matrix[0][1] * y + matrix[0][3],
                        matrix[1][0] * x + matrix[1][1] * y + matrix[1][3],
                    )
                    for x, y in vertices
                )
                area = sum(
                    a[0] * b[1] - b[0] * a[1]
                    for a, b in zip(
                        transformed, (*transformed[1:], transformed[0]), strict=True
                    )
                )
                if area < 0:
                    transformed = tuple(reversed(transformed))
                candidates.append(
                    ConvexPolygon(
                        kind="convex_polygon_xy",
                        vertices_mm=transformed,
                        margin_mm=region.margin_mm,
                    )
                )
            if not candidates or any(
                candidate != candidates[0] for candidate in candidates[1:]
            ):
                raise ValueError(
                    "Arena-file geometry must be present and constant for each trial instance"
                )
            region = candidates[0]
        if isinstance(region, ConvexPolygon):
            validate_inset_area(region)
            walls = inset_convex_polygon(region.vertices_mm, region.margin_mm)
            for setting in settings:
                if budget is not None:
                    budget.check_cancelled_or_expired()
                x, y = setting.initial.position_mm
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                    raise ValueError(
                        "Arena initial position must be resolved before region validation"
                    )
                if any(nx * x + ny * y > offset + 1e-9 for (nx, ny), offset in walls):
                    raise ValueError(
                        f"Arena {binding.instance_id} initial position lies outside its movement limits (or wall margin empties the region)"
                    )
        resolved.append(binding.model_copy(update={"region": region}))
    return TrialArenaBoundaries(format_version=1, bindings=tuple(resolved))
