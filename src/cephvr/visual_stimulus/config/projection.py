"""Validate file-owned clipping and geometry checks without device I/O."""

import math
from collections.abc import Mapping
from decimal import Decimal

from cephvr.shared.config import ConfigurationError
from cephvr.visual_stimulus.v1.runtime_pb2 import ProjectionLimits

PROJECTION_KEYS = (
    "near_mm",
    "far_mm",
    "positional_tolerance_mm",
    "orthogonality_tolerance",
)


def projection_values(values: Mapping[str, object]) -> dict[str, float]:
    result = {}
    for key in PROJECTION_KEYS:
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ConfigurationError(f"projection.{key} must be finite and positive")
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ConfigurationError(f"projection.{key} must be finite and positive")
        result[key] = number
    if result["near_mm"] >= result["far_mm"]:
        raise ConfigurationError("projection.near_mm must precede far_mm")
    if result["orthogonality_tolerance"] >= 1:
        raise ConfigurationError("projection.orthogonality_tolerance must be below 1")
    return result


def policy_projection(values: ProjectionLimits) -> dict[str, float]:
    return projection_values(
        {key: getattr(values, key) for key in PROJECTION_KEYS if values.HasField(key)}
    )
