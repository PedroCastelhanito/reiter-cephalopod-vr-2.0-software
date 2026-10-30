"""Column tables: plain ``dict[str, numpy array]`` with explicit missing-value fills."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
from numpy.typing import NDArray

Array = NDArray[Any]
JSON = dict[str, Any]
Table = dict[str, Array]
# Missing integers use the int64 minimum (CephVR1.0 convention); a real 0 stays 0.
INT_FILL = int(np.iinfo(np.int64).min)
# Nullable booleans are int8: 1 true, 0 false, -1 unavailable.
BOOL_FILL = -1


def path_get(row: JSON, path: str) -> Any:
    value: Any = row
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def column(values: list[Any], kind: str) -> Array:
    if kind == "i8":
        return np.array([INT_FILL if v is None else v for v in values], dtype=np.int64)
    if kind == "f8":
        return np.array([np.nan if v is None else v for v in values], dtype=np.float64)
    if kind == "b":
        return np.array(
            [BOOL_FILL if v is None else int(bool(v)) for v in values], dtype=np.int8
        )
    if kind == "str":
        return np.array(["" if v is None else str(v) for v in values], dtype=object)
    if kind == "json":
        return np.array(
            [json.dumps(v, separators=(",", ":")) for v in values], dtype=object
        )
    raise ValueError(f"unknown column kind {kind}")


def build(rows: list[JSON], spec: dict[str, tuple[str, str]]) -> Table:
    """``spec`` maps output column -> (dotted source key, kind)."""
    return {
        name: column([path_get(row, key) for row in rows], kind)
        for name, (key, kind) in spec.items()
    }
