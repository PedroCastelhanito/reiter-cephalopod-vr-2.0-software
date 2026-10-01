"""V04/V17/V21/V23 float32 color operations and explicit output quantization."""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence


def require_finite_rgba(value: Sequence[float]) -> tuple[float, float, float, float]:
    if len(value) != 4 or not all(math.isfinite(float(v)) for v in value):
        raise ValueError("finite RGBA values are required")
    return tuple(float(v) for v in value)  # type: ignore[return-value]


def clamp_with_flag(
    value: float, low: float = 0.0, high: float = 1.0
) -> tuple[float, bool]:
    if not math.isfinite(value) or low > high:
        raise ValueError("finite value and ordered clipping bounds are required")
    result = min(high, max(low, value))
    return result, result != value


def srgb_to_linear(channel: float) -> float:
    if not math.isfinite(channel):
        raise ValueError("sRGB channel must be finite")
    c = min(1.0, max(0.0, channel))
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(channel: float) -> float:
    if not math.isfinite(channel):
        raise ValueError("linear channel must be finite")
    c = min(1.0, max(0.0, channel))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def linearize_rgba(
    rgba: Sequence[float], *, transfer: str, alpha: float | None = None
) -> tuple[float, float, float, float]:
    """Decode the declared transfer, then return linear premultiplied float32 RGBA."""
    values = require_finite_rgba(rgba)
    a = values[3] if alpha is None else alpha
    if not math.isfinite(a):
        raise ValueError("alpha must be finite")
    a = min(1.0, max(0.0, a))
    if transfer == "srgb":
        rgb = tuple(srgb_to_linear(c) for c in values[:3])
    elif transfer in ("linear", "bt709"):
        if transfer == "bt709":

            def decode(c: float) -> float:
                c = min(1.0, max(0.0, c))
                return c / 4.5 if c < 0.081 else ((c + 0.099) / 1.099) ** (1 / 0.45)

            rgb = tuple(decode(c) for c in values[:3])
        else:
            rgb = values[:3]
    else:
        raise ValueError(f"unsupported transfer function {transfer!r}")
    return tuple(struct.unpack("=f", struct.pack("=f", c * a))[0] for c in rgb) + (a,)


def source_over(
    source: Sequence[float], destination: Sequence[float]
) -> tuple[float, float, float, float]:
    """Linear premultiplied-alpha source-over."""
    s = require_finite_rgba(source)
    d = require_finite_rgba(destination)
    inverse = 1.0 - min(1.0, max(0.0, s[3]))
    return (
        s[0] + d[0] * inverse,
        s[1] + d[1] * inverse,
        s[2] + d[2] * inverse,
        s[3] + d[3] * inverse,
    )


def interpolate_inverse_lut(curve: Sequence[float], value: float) -> float:
    if len(curve) < 2 or not math.isfinite(value):
        raise ValueError("a finite input and at least two LUT samples are required")
    if any(not math.isfinite(v) for v in curve) or any(
        a > b for a, b in zip(curve, curve[1:], strict=False)
    ):
        raise ValueError("inverse LUT must be finite and nondecreasing")
    x = min(1.0, max(0.0, value))
    scaled = x * (len(curve) - 1)
    index = min(int(scaled), len(curve) - 2)
    fraction = scaled - index
    return curve[index] * (1.0 - fraction) + curve[index + 1] * fraction


def quantize_device_code(value: float, bits: int) -> tuple[int, bool]:
    if bits not in (8, 10):
        raise ValueError("physical output precision must be RGB8 or RGB10")
    clipped, changed = clamp_with_flag(value)
    maximum = (1 << bits) - 1
    return math.floor(clipped * maximum + 0.5), changed
