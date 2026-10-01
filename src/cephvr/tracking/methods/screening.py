"""T41 single-pass original-neighborhood normalized median screening."""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np

from cephvr.tracking.config.models.methods import LocalMedianSettings
from cephvr.tracking.config.models.records import FlowSampleCounts


def screen(
    displacement: Any,
    selected: Any,
    cost: Any,
    validity: Any,
    settings: LocalMedianSettings,
    scratch_bytes: int,
) -> tuple[Any, FlowSampleCounts]:
    shape = selected.shape
    eligible = selected.copy()
    unavailable = (
        eligible & (validity == 0)
        if validity is not None
        else np.zeros(shape, dtype=bool)
    )
    eligible &= ~unavailable
    nonfinite = eligible & ~np.isfinite(displacement).all(axis=-1)
    eligible &= ~nonfinite
    if settings.maximum_native_cost is not None:
        if cost is None:
            raise ValueError("configured cost screening requires promised native cost")
        rejected_cost = eligible & (cost > settings.maximum_native_cost)
    else:
        rejected_cost = np.zeros(shape, dtype=bool)
    eligible &= ~rejected_cost
    accepted = np.zeros(shape, dtype=bool)
    enough = np.zeros(shape, dtype=bool)
    r = settings.radius_cells
    neighbors = (2 * r + 1) ** 2 - 1
    batch = scratch_bytes // (neighbors * 2 * 8 * 4 + 128)
    if batch < 1:
        raise ValueError("local median neighborhood exceeds prepared scratch budget")
    row, col = np.nonzero(eligible)
    for first in range(0, len(row), batch):
        rr, cc = row[first : first + batch], col[first : first + batch]
        values = np.full((len(rr), neighbors, 2), np.nan)
        index = 0
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx == 0 and dy == 0:
                    continue
                y, x = rr + dy, cc + dx
                inside = (y >= 0) & (y < shape[0]) & (x >= 0) & (x < shape[1])
                positions = np.flatnonzero(inside)
                positions = positions[eligible[y[positions], x[positions]]]
                values[positions, index] = displacement[y[positions], x[positions]]
                index += 1
        valid = np.isfinite(values[:, :, 0]).sum(axis=1) >= settings.minimum_neighbors
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            median = np.nanmedian(values, axis=1)
            spread = np.nanmedian(np.abs(values - median[:, None, :]), axis=1)
        residual = (displacement[rr, cc] - median) / (spread + settings.noise_floor_px)
        score = np.hypot(residual[:, 0], residual[:, 1])
        enough[rr, cc] = valid
        accepted[rr, cc] = (
            valid & np.isfinite(score) & (score <= settings.maximum_normalized_residual)
        )
    counts = FlowSampleCounts(
        selected=int(selected.sum()),
        unavailable=int(unavailable.sum()),
        nonfinite=int(nonfinite.sum()),
        cost_rejected=int(rejected_cost.sum()),
        neighbor_unevaluable=int((eligible & ~enough).sum()),
        median_rejected=int((eligible & enough & ~accepted).sum()),
        accepted=int(accepted.sum()),
    )
    return accepted, counts
