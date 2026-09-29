"""Pure V24 heading-relative planar feedback increment; no renderer state or I/O.

Conventions (stimulus-schema.md): world +X right, +Y forward, +Z up; yaw is
counter-clockwise about +Z, so +yaw turns forward toward the observer's left.
Tracking sideways/turn are animal-left-positive (T36). V16 sliding follows separately.
"""
from __future__ import annotations
import math

def heading_vectors(yaw_rad: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """World-XY forward and left unit vectors at yaw psi."""
    s, c = math.sin(yaw_rad), math.cos(yaw_rad)
    return (-s, c), (-c, -s)

def planar_feedback_increment(*, yaw_before_deg: float, forward: float, sideways: float,
                              linear_gain_mm: float, turn: float, turn_gain_deg_per_rad: float,
                              turn_offset_deg_per_s: float, dt_s: float) -> tuple[float, float, float]:
    """Return (dx_mm, dy_mm, dyaw_deg) for one interval_average_rate result over dt_s.

    The yaw increment is the ordinary movement_integration rule; the planar increment
    uses the interval's midpoint heading because results are interval averages (T37).
    """
    values = (yaw_before_deg, forward, sideways, linear_gain_mm, turn,
              turn_gain_deg_per_rad, turn_offset_deg_per_s, dt_s)
    if not all(math.isfinite(v) for v in values) or dt_s <= 0:
        raise ValueError('finite values and a positive source interval required')
    dyaw = (turn_gain_deg_per_rad*turn + turn_offset_deg_per_s)*dt_s
    f, l = heading_vectors(math.radians(yaw_before_deg + dyaw/2))
    scale = linear_gain_mm*dt_s
    return (scale*(forward*f[0] + sideways*l[0]), scale*(forward*f[1] + sideways*l[1]), dyaw)
