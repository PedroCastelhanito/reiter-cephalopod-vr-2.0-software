"""HDF5 writing helpers: atomic files, typed tables with unit/clock attributes, views."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from .tables import BOOL_FILL, INT_FILL, JSON, Array, Table

STR_DTYPE = h5py.string_dtype(encoding="utf-8")
GZIP_LEVEL = 4
CHUNK_ROWS = 65_536
HOST_CLOCK = "cephvr.host.perf_counter_ns.v1"
CAMERA_CLOCK = "cephvr.camera.native.v1"
DURATION_NS = {"age_limit_ns"}


@contextmanager
def atomic_hdf5(output: Path) -> Iterator[h5py.File]:
    """Write a sibling ``.partial`` and rename: the destination is absent or complete."""
    output = Path(output)
    temporary = output.with_name(output.name + ".partial")
    temporary.unlink(missing_ok=True)
    handle = h5py.File(temporary, "w")
    try:
        yield handle
    except BaseException:
        handle.close()
        temporary.unlink(missing_ok=True)
        raise
    handle.close()
    os.replace(temporary, output)


def column_attrs(name: str, values: Array) -> JSON:
    attrs: JSON = {}
    if name.endswith("_ns"):
        attrs["unit"] = "ns"
        if name not in DURATION_NS:
            attrs["clock"] = CAMERA_CLOCK if name.startswith("camera_") else HOST_CLOCK
    elif name.startswith("time_obx"):
        attrs.update(unit="s", clock="spikeglx.onebox.file_seconds")
    elif name.startswith("time_imec"):
        attrs.update(unit="s", clock="spikeglx.imec.file_seconds")
    elif name.endswith("_s"):
        attrs["unit"] = "s"
    elif name.endswith("_ms"):
        attrs["unit"] = "ms"
    elif name.endswith("_px"):
        attrs["unit"] = "px"
    else:
        attrs["unit"] = "1"
    if values.dtype == np.int64:
        attrs["fill_value"] = INT_FILL
    elif values.dtype == np.int8:
        attrs["codes"] = json.dumps({"1": True, "0": False, str(BOOL_FILL): None})
    return attrs


def write_array(group: h5py.Group, name: str, values: Array, **attrs: Any) -> None:
    values = np.asarray(values)
    kwargs: JSON = {}
    if values.dtype == object:
        kwargs["dtype"] = STR_DTYPE
    if values.ndim and values.size:
        kwargs.update(
            compression="gzip",
            compression_opts=GZIP_LEVEL,
            chunks=(min(CHUNK_ROWS, len(values)),) + values.shape[1:],
        )
    dataset = group.create_dataset(name, data=values, **kwargs)
    dataset.attrs.update(column_attrs(name, values) | attrs)


def write_table(group: h5py.Group, table: Table, **attrs: Any) -> None:
    for name, values in table.items():
        write_array(group, name, values)
    group.attrs.update(attrs)


def write_json(group: h5py.Group, name: str, value: object) -> None:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    group.create_dataset(name, data=text, dtype=STR_DTYPE).attrs["format"] = "json"


def session_view(h5: h5py.File, output: str, parts: list[tuple[int, str]]) -> None:
    """Concatenate per-trial tables into one view (``parts`` = trial number, group path).

    Numeric columns are virtual datasets over the trial data (no copy); strings are
    copied. A column absent from some trial is skipped rather than padded.
    """
    groups = [(n, h5[p]) for n, p in parts if p in h5]
    if not groups:
        return
    rows = [len(next(iter(g.values()))) if len(g) else 0 for _, g in groups]
    if not sum(rows):
        return
    view = h5.create_group(output)
    names = [name for name in groups[0][1] if all(name in g for _, g in groups)]
    for name in names:
        datasets = [g[name] for _, g in groups]
        dtype, attrs = datasets[0].dtype, dict(datasets[0].attrs)
        if dtype.kind == "O" or any(d.dtype != dtype for d in datasets):
            write_array(view, name, np.concatenate([d[...] for d in datasets]))
            view[name].attrs.update(attrs)
            continue
        layout = h5py.VirtualLayout(shape=(sum(rows),), dtype=dtype)
        offset = 0
        for dataset, count in zip(datasets, rows, strict=True):
            if count:
                # "." keeps the source self-referencing after the .partial rename.
                layout[offset : offset + count] = h5py.VirtualSource(
                    ".", dataset.name, shape=dataset.shape, dtype=dtype
                )
            offset += count
        view.create_virtual_dataset(name, layout).attrs.update(attrs)
    numbers = [np.full(c, n, np.int64) for (n, _), c in zip(groups, rows, strict=True)]
    write_array(view, "trial_number", np.concatenate(numbers))
