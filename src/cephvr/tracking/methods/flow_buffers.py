"""T33 checked host views and nonoverlapping native grid mapping."""

from __future__ import annotations

import math
from typing import Any, cast
from uuid import uuid4

import numpy as np

from cephvr.tracking.types import FlowGridMapping, FlowLease, HostFlowView


def grid_mapping(width: int, height: int, step: int) -> FlowGridMapping:
    if min(width, height, step) <= 0:
        raise ValueError("invalid native grid")
    rows, cols = (height + step - 1) // step, (width + step - 1) // step
    y, x = np.mgrid[:rows, :cols]
    # Pixel centres are integers; cell footprints include their unit squares.
    footprints = np.stack(
        (
            x * step - 0.5,
            y * step - 0.5,
            np.minimum((x + 1) * step, width) - 0.5,
            np.minimum((y + 1) * step, height) - 0.5,
        ),
        axis=-1,
    ).astype(np.float64)
    positions = (footprints[..., :2] + footprints[..., 2:]) / 2
    positions.flags.writeable = footprints.flags.writeable = False
    return FlowGridMapping(
        str(uuid4()),
        cols,
        rows,
        memoryview(cast(Any, positions)),
        memoryview(cast(Any, footprints)),
    )


def _view(
    data: memoryview, rows: int, cols: int, pitch: int, dtype: Any, components: int
) -> Any:
    item = np.dtype(dtype).itemsize
    row = cols * components * item
    if (
        min(rows, cols) <= 0
        or pitch < row
        or not data.readonly
        or not data.c_contiguous
        or data.nbytes < (rows - 1) * pitch + row
    ):
        raise ValueError("invalid completed native buffer span/access/pitch")
    shape = (rows, cols, components) if components > 1 else (rows, cols)
    strides = (pitch, components * item, item) if components > 1 else (pitch, item)
    return np.ndarray(shape, dtype=dtype, buffer=data, strides=strides)


def host_arrays(lease: FlowLease, view: HostFlowView) -> tuple[Any, Any, Any]:
    if (
        lease.lease_id != view.lease_id
        or lease.memory_domain != "host"
        or not math.isfinite(lease.component_scale)
        or lease.component_scale <= 0
    ):
        raise ValueError("flow readback identity/domain/scale mismatch")
    endian = {"little": "<", "big": ">"}[lease.byte_order]
    dtype = (
        endian
        + {"int16x2": "i2", "float32x2": "f4", "float64x2": "f8"}[lease.storage_format]
    )
    vector = _view(
        view.displacement_bytes,
        lease.grid_height,
        lease.grid_width,
        lease.row_pitch_bytes,
        dtype,
        2,
    )
    optional: list[Any] = []
    for identity, pitch, data in (
        (lease.quality_buffer_id, lease.quality_row_pitch_bytes, view.quality_bytes),
        (lease.validity_buffer_id, lease.validity_row_pitch_bytes, view.validity_bytes),
    ):
        if identity is None and pitch is None and data is None:
            optional.append(None)
        elif identity and pitch is not None and data is not None:
            optional.append(
                _view(data, lease.grid_height, lease.grid_width, pitch, "u1", 1)
            )
        else:
            raise ValueError("incomplete optional native buffer")
    cost, valid = optional
    if (
        (cost is None) != (lease.quality_schema_id is None)
        or cost is not None
        and lease.quality_schema_id != "tracking.nvof-cost-u8.v1"
    ):
        raise ValueError("unsupported native cost schema")
    if valid is not None and np.any(valid > 1):
        raise ValueError("native validity must be zero or one")
    return vector, cost, valid
