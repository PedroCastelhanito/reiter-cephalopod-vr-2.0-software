"""Exact V05 function evaluation and V07 retained scalar motion anchors."""

from __future__ import annotations

import math
from typing import Any


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        result = float(value)
    elif getattr(value, "kind", None) == "condition":
        raise ValueError("condition references must be substituted during preparation")
    else:
        raise TypeError(f"unsupported numeric value: {value!r}")
    if not math.isfinite(result):
        raise ValueError("animation values must be finite")
    return result


def _time_ns(value: Any) -> int:
    if isinstance(value, int):
        return value
    if hasattr(value, "ns"):
        return int(value.ns())
    if hasattr(value, "seconds"):
        whole, _, fractional = value.seconds.partition(".")
        return int(whole) * 1_000_000_000 + int((fractional[:9] + "000000000")[:9])
    return int(value)


def evaluate_function(function: Any, elapsed_ns: int) -> float:
    if elapsed_ns < 0:
        raise ValueError("function elapsed time cannot be negative")
    kind = function.kind
    t = elapsed_ns / 1_000_000_000
    if kind == "constant":
        return _number(function.value)
    if kind == "ramp":
        return _number(function.initial) + _number(function.slope_per_s) * t
    if kind == "sine":
        return _number(function.mean) + _number(function.amplitude) * math.sin(
            math.tau
            * (_number(function.frequency_hz) * t + _number(function.phase_cycles))
        )
    if kind == "keyframes":
        knots = function.knots
        for left, right in zip(knots, knots[1:], strict=False):
            lt, rt = _time_ns(left.time), _time_ns(right.time)
            if elapsed_ns < rt:
                lv, rv = _number(left.value), _number(right.value)
                if function.interpolation == "step":
                    return lv
                return lv + (rv - lv) * ((elapsed_ns - lt) / (rt - lt))
        return _number(knots[-1].value)
    raise ValueError(f"unsupported function kind {kind!r}")


def integrate_function(function: Any, start_ns: int, end_ns: int) -> float:
    """Analytic integral over epoch-local seconds for rate-valued functions."""
    if start_ns < 0 or end_ns < start_ns:
        raise ValueError("invalid integration interval")
    if start_ns == end_ns:
        return 0.0
    scale = 1e-9
    a, b = start_ns * scale, end_ns * scale
    kind = function.kind
    if kind == "constant":
        return _number(function.value) * (b - a)
    if kind == "ramp":
        initial, slope = _number(function.initial), _number(function.slope_per_s)
        return initial * (b - a) + slope * (b * b - a * a) / 2
    if kind == "sine":
        mean, amplitude = _number(function.mean), _number(function.amplitude)
        freq, phase = _number(function.frequency_hz), _number(function.phase_cycles)
        base = mean * (b - a)
        if freq == 0:
            return base + amplitude * math.sin(math.tau * phase) * (b - a)
        return base + amplitude * (
            math.cos(math.tau * (freq * a + phase))
            - math.cos(math.tau * (freq * b + phase))
        ) / (math.tau * freq)
    if kind == "keyframes":
        knots = function.knots
        cuts = [a]
        cuts.extend(
            _time_ns(k.time) * scale for k in knots if a < _time_ns(k.time) * scale < b
        )
        cuts.append(b)
        total = 0.0
        for left, right in zip(cuts, cuts[1:], strict=False):
            la, lb = int(left / scale), int(right / scale)
            va, vb = evaluate_function(function, la), evaluate_function(function, lb)
            total += (va if function.interpolation == "step" else (va + vb) / 2) * (
                right - left
            )
        return total
    raise ValueError(f"unsupported function kind {kind!r}")
