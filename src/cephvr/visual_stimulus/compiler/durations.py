"""Versioned exact-duration resolution and Stafford fixed-sum sampling (V06)."""

from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from cephvr.visual_stimulus.config.models.program_model import (
    Fixed,
    Random,
    TargetTotal,
)
from cephvr.visual_stimulus.resources.budget import PreparationBudget

DURATION_IMPLEMENTATION = "cephvr-duration-python-v1"
DURATION_SAMPLER_ID = "stafford_continuous_ns_v1"
_INT64_MAX = (1 << 63) - 1


def stafford_workspace_bytes(count: int) -> int:
    """Conservative CPython workspace estimate for Stafford's O(n²) tables."""
    if count < 0:
        raise ValueError("count must be nonnegative")
    # Each table cell is a list reference plus a separately allocated float;
    # include row/list headers, transition storage and allocator slack.
    return 96 * count * count + 256 * count


@dataclass(frozen=True)
class DurationResult:
    """Resolved duration vector and per-occurrence origin labels."""

    durations_ns: tuple[int, ...]
    origins: tuple[Literal["fixed", "sampled", "uniquely_constrained"], ...]
    sampler_id: str
    variability_possible: bool


def duration_rng(seed_decimal: str) -> random.Random:
    """Create V06's private, reproducible duration stream."""
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)", seed_decimal):
        raise ValueError("seed must be canonical nonnegative decimal text")
    digest = hashlib.sha256(f"cephvr.duration.v1:{seed_decimal}".encode())
    return random.Random(int.from_bytes(digest.digest(), "big"))


def _stafford_unit_sum(
    count: int, total: float, rng: random.Random
) -> tuple[float, ...]:
    """Sample uniformly from the unit box intersected by the fixed-sum plane.

    This implements Stafford's simplex-volume decomposition. Dynamic weights select
    simplex types proportional to their volume; a point is then drawn within the
    selected simplex and uniformly permuted. It uses no rejection sampling.
    """
    if count < 2:
        raise ValueError("Stafford sampling requires at least two coordinates")
    if not math.isfinite(total) or not 0.0 < total < count:
        raise ValueError("Stafford normalized sum must be strictly inside its range")

    segment = min(max(math.floor(total), 0), count - 1)
    total = min(max(total, float(segment)), float(segment + 1))
    lower_terms = [total - (segment - index) for index in range(count)]
    upper_terms = [segment + count - index - total for index in range(count)]

    # Scale all dynamic-programming weights by a common large finite value; only
    # ratios matter, and this avoids overflow while retaining subnormal fallbacks.
    scale = 1e300
    weights = [[0.0] * (count + 1) for _ in range(count)]
    weights[0][1] = scale
    transitions = [[0.0] * count for _ in range(count - 1)]
    for dimension in range(2, count + 1):
        left = [
            weights[dimension - 2][column + 1] * lower_terms[column] / dimension
            for column in range(dimension)
        ]
        right_start = count - dimension
        right = [
            weights[dimension - 2][column]
            * upper_terms[right_start + column]
            / dimension
            for column in range(dimension)
        ]
        row = [a + b for a, b in zip(left, right, strict=True)]
        for column, value in enumerate(row):
            weights[dimension - 1][column + 1] = value
            denominator = value if value > 0.0 else math.ulp(0.0)
            # The two branches are selected by the orientation of adjacent
            # simplex facets; at zero-volume edges choose the only feasible side.
            if upper_terms[right_start + column] > lower_terms[column]:
                probability = right[column] / denominator
            else:
                probability = 1.0 - left[column] / denominator
            transitions[dimension - 2][column] = min(1.0, max(0.0, probability))

    # Reverse through the transition table while constructing barycentric values.
    running_sum = 0.0
    product = 1.0
    remaining = total
    column = segment
    point = [0.0] * count
    for dimension in range(count - 1, 0, -1):
        choose_upper = rng.random() <= transitions[dimension - 1][column]
        barycentric = rng.random() ** (1.0 / dimension)
        running_sum += (1.0 - barycentric) * product * remaining / (dimension + 1)
        product *= barycentric
        point[count - dimension - 1] = running_sum + product * int(choose_upper)
        if choose_upper:
            remaining -= 1.0
            column -= 1
    point[-1] = running_sum + product * remaining

    # Independent random keys provide an explicit, stable-random permutation.
    keys = [rng.random() for _ in range(count)]
    return tuple(
        point[index] for index in sorted(range(count), key=lambda i: (keys[i], i))
    )


def _sample_bounded_fixed_sum(
    count: int,
    total_ns: int,
    lower_ns: int,
    upper_ns: int,
    rng: random.Random,
    budget: PreparationBudget | None = None,
) -> tuple[int, ...]:
    if count == 1:
        if lower_ns <= total_ns <= upper_ns:
            return (total_ns,)
        raise ValueError("single random duration is outside its bounds")
    width = upper_ns - lower_ns
    if width <= 0:
        raise ValueError("Stafford sampler requires a nonzero interval")
    residual = total_ns - count * lower_ns
    owner = f"visual_stimulus:stafford-sampler:{id(rng)}"
    workspace = stafford_workspace_bytes(count)
    if budget is not None:
        budget.check_cancelled_or_expired()
        budget.reserve(owner=owner, cpu_bytes=workspace, gpu_bytes=0)
    try:
        continuous = _stafford_unit_sum(count, residual / width, rng)
    finally:
        if budget is not None:
            budget.release(owner=owner)
    exact_values = [
        Decimal.from_float(value) * width + lower_ns for value in continuous
    ]
    floors = [
        int(value.to_integral_value(rounding="ROUND_FLOOR")) for value in exact_values
    ]
    fractions = [
        value - floor for value, floor in zip(exact_values, floors, strict=True)
    ]
    increments = total_ns - sum(floors)
    if increments < 0 or increments > count:
        raise ArithmeticError(
            "Stafford sample cannot be quantized within one nanosecond"
        )

    candidates = [i for i, value in enumerate(floors) if value < upper_ns]
    if increments > len(candidates):
        raise ArithmeticError("Stafford quantization exceeds the upper duration bound")
    tie_keys = {i: rng.random() for i in candidates}
    order = sorted(candidates, key=lambda i: (-fractions[i], tie_keys[i], i))
    for index in order[:increments]:
        floors[index] += 1
    if (
        sum(floors) != total_ns
        or any(value < lower_ns or value > upper_ns for value in floors)
        or any(
            value not in (int(x), int(x) + 1)
            for value, x in zip(floors, exact_values, strict=True)
        )
    ):
        raise ArithmeticError("Stafford nanosecond quantization failed exact bounds")
    return tuple(floors)


def resolve_durations(
    durations: tuple[Fixed | Random, ...],
    plan: TargetTotal | None,
    seed_decimal: str,
    *,
    budget: PreparationBudget | None = None,
) -> DurationResult:
    """Resolve fixed or target-total occurrence durations exactly in nanoseconds."""
    fixed = [
        item.duration.ns() if isinstance(item, Fixed) else None for item in durations
    ]
    if plan is None:
        if any(value is None for value in fixed):
            raise ValueError("random epochs require target-total duration mode")
        result = tuple(int(value) for value in fixed if value is not None)
        total = sum(result)
        if total > _INT64_MAX:
            raise OverflowError("expanded trial duration exceeds signed int64")
        return DurationResult(result, tuple("fixed" for _ in result), "", False)

    total = plan.total.ns()
    lower, upper = plan.minimum.ns(), plan.maximum.ns()
    fixed_total = sum(value for value in fixed if value is not None)
    random_count = sum(value is None for value in fixed)
    residual = total - fixed_total
    if random_count == 0:
        if residual != 0:
            raise ValueError("target trial total does not equal fixed epoch durations")
        sampled: tuple[int, ...] = ()
        unique = True
    else:
        minimum, maximum = random_count * lower, random_count * upper
        if residual < minimum or residual > maximum:
            raise ValueError(
                f"target total infeasible: random epochs require [{minimum}, {maximum}] ns"
            )
        unique = (
            random_count == 1
            or lower == upper
            or residual == minimum
            or residual == maximum
        )
        if unique:
            value = residual // random_count
            sampled = (value,) * random_count
        else:
            sampled = _sample_bounded_fixed_sum(
                random_count,
                residual,
                lower,
                upper,
                duration_rng(seed_decimal),
                budget,
            )

    iterator = iter(sampled)
    values: list[int] = []
    origins: list[Literal["fixed", "sampled", "uniquely_constrained"]] = []
    for fixed_value in fixed:
        if fixed_value is not None:
            values.append(fixed_value)
            origins.append("fixed")
        else:
            values.append(next(iterator))
            origins.append("uniquely_constrained" if unique else "sampled")
    if sum(values) != total:
        raise ArithmeticError("resolved duration sum does not match target total")
    if total > _INT64_MAX:
        raise OverflowError("resolved trial duration exceeds signed int64")
    return DurationResult(
        tuple(values), tuple(origins), DURATION_SAMPLER_ID, not unique
    )
