"""Estimator-owned T32/T33 exact geometry partition and represented-area cache."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from cephvr.tracking.methods.outline import project_sections
from cephvr.tracking.types import FlowGridMapping, ImageLayout, SamplingGeometry


class SamplingSettings(Protocol):
    sections: Any


@dataclass(frozen=True)
class Association:
    area: Any
    intended: Any
    visible: Any
    positions: Any


def associate(
    geometry: SamplingGeometry,
    mapping: FlowGridMapping,
    layout: ImageLayout,
    settings: SamplingSettings,
    maximum: int,
) -> Association:
    count = settings.sections.count
    cells = mapping.grid_width * mapping.grid_height
    pixels = geometry.width * geometry.height
    if cells * count * 8 + pixels * 80 + cells * 64 > maximum:
        raise ValueError("section association exceeds prepared native budget")
    mask = np.asarray(geometry.band_mask)
    rows, cols = np.nonzero(mask)
    points = np.stack(
        (cols + geometry.origin_xy_px[0], rows + geometry.origin_xy_px[1]), axis=-1
    ).astype(np.float64)
    basis = np.array([geometry.anterior_unit_xy, geometry.left_unit_xy]).T
    body = (points - np.array(geometry.centre_xy_px)) @ basis
    curve = (
        np.asarray(geometry.outline_xy_px) - np.array(geometry.centre_xy_px)
    ) @ basis
    labels = project_sections(body, curve, count, min(maximum // 8, 1024 * 1024))
    fin_region = getattr(settings, "fin_region", None)
    if fin_region is not None and fin_region.span_degrees < 360:
        angle = np.degrees(np.arctan2(body[:, 1], body[:, 0]))
        delta = (angle - fin_region.offset_degrees + 180) % 360 - 180
        selected = (
            (delta >= -fin_region.span_degrees / 2)
            & (delta < fin_region.span_degrees / 2)
            & np.any(body != 0, axis=1)
        )
        points, labels = points[selected], labels[selected]
    intended = np.bincount(labels, minlength=count).astype(np.float64)
    visible = (
        (points[:, 0] >= 0)
        & (points[:, 0] < layout.width)
        & (points[:, 1] >= 0)
        & (points[:, 1] < layout.height)
    )
    points, labels = points[visible], labels[visible]
    visible_area = np.bincount(labels, minlength=count).astype(np.float64)
    area = np.zeros((cells, count), dtype=np.float64)
    footprints = np.asarray(mapping.footprint_xyxy_px).reshape(-1, 4)
    # The prepared NVIDIA mapping has integer-cell edges at half-pixels. In that
    # case every pixel square contributes once, with no cells-by-pixels scan.
    grid = footprints.reshape(mapping.grid_height, mapping.grid_width, 4)
    x_edges = np.concatenate((grid[0, :, 0], grid[0, -1:, 2]))
    y_edges = np.concatenate((grid[:, 0, 1], grid[-1:, 0, 3]))
    regular = (
        np.all(grid[:, :, 0] == x_edges[:-1])
        and np.all(grid[:, :, 2] == x_edges[1:])
        and np.all(grid[:, :, 1] == y_edges[:-1, None])
        and np.all(grid[:, :, 3] == y_edges[1:, None])
        and np.all(np.diff(x_edges) > 0)
        and np.all(np.diff(y_edges) > 0)
        and np.all(np.remainder(x_edges + 0.5, 1) == 0)
        and np.all(np.remainder(y_edges + 0.5, 1) == 0)
    )
    if regular:
        x = np.searchsorted(x_edges, points[:, 0], side="right") - 1
        y = np.searchsorted(y_edges, points[:, 1], side="right") - 1
        inside = (
            (x >= 0) & (x < mapping.grid_width) & (y >= 0) & (y < mapping.grid_height)
        )
        np.add.at(
            area, (y[inside] * mapping.grid_width + x[inside], labels[inside]), 1.0
        )
    else:
        # Fractional footprints retain exact area intersections in bounded scratch.
        for index, (x0, y0, x1, y1) in enumerate(footprints):
            weight = np.maximum(
                0,
                np.minimum(points[:, 0] + 0.5, x1) - np.maximum(points[:, 0] - 0.5, x0),
            )
            weight *= np.maximum(
                0,
                np.minimum(points[:, 1] + 0.5, y1) - np.maximum(points[:, 1] - 0.5, y0),
            )
            area[index] = np.bincount(labels, weights=weight, minlength=count)
    positions = (
        np.asarray(mapping.sample_xy_px).reshape(-1, 2)
        - np.array(geometry.centre_xy_px)
    ) @ basis
    return Association(area, intended, visible_area, positions)
