"""SYS-004 post hoc alignment to OneBox seconds (AN01, A09, V22).

OneBox time is seconds from the first sample of the session's OneBox file. Rows
only receive a time from a recorded pulse edge; everything else stays NaN.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .tables import JSON, Array

TIMING_CODES = {0: "unresolved", 1: "measured_pulse", 2: "inferred_correspondence"}
UNRESOLVED, MEASURED, INFERRED = 0, 1, 2
REFIT_EVERY, REFIT_SPAN = 200, 2000  # Photodiode running host->OneBox fit.
SEED_SKIP, SEED_SPAN = 60, 2000  # Level changes used to seed that fit.
SY_MATCH_S = 0.25  # SY is a 1 s square wave.


def match_windows(
    durations: list[float], windows: list[tuple[float, float]], tolerance_s: float
) -> dict[int, int]:
    """Ordered unique duration match of trials to Trial-state windows (from CephVR1.0).

    Earliest and latest feasible complete assignments agree only when unique; a trial
    without a unique window is left out instead of shifting later trials.
    """
    spans = np.array([b - a for a, b in windows])
    candidates = [np.flatnonzero(np.abs(spans - d) <= tolerance_s) for d in durations]
    earliest, previous = [], -1
    for c in candidates:
        c = c[c > previous]
        if not c.size:
            return {}
        previous = int(c[0])
        earliest.append(previous)
    latest, following = [], len(windows)
    for c in reversed(candidates):
        c = c[c < following]
        if not c.size:
            return {}
        following = int(c[-1])
        latest.append(following)
    pairs = zip(earliest, reversed(latest), strict=True)
    return {i: a for i, (a, b) in enumerate(pairs) if a == b}


@dataclass
class HostMap:
    """``obx_s = slope * (host_ns - origin_ns) / 1e9 + offset`` with offset in [low, high]."""

    origin_ns: int
    slope: float
    low: float
    high: float

    @property
    def offset(self) -> float:
        return (self.low + self.high) / 2

    @property
    def uncertainty_s(self) -> float:
        return (self.high - self.low) / 2

    def host_ns(self, obx_s: Array) -> Array:
        return self.origin_ns + (np.asarray(obx_s) - self.offset) / self.slope * 1e9


def host_map(anchors: list[tuple[float, int, int]]) -> HostMap | None:
    """Trial-state edges with their command dispatch/acknowledge host bounds (A11).

    The line changed between dispatch and acknowledgement, so each edge bounds the
    offset; intersecting all edges narrows it. Empty intersection means no anchor.
    """
    anchors = [a for a in anchors if a[1] is not None and a[2] is not None]
    if not anchors:
        return None
    origin = anchors[0][1]
    obx = np.array([a[0] for a in anchors])
    lo = np.array([(a[1] - origin) / 1e9 for a in anchors])
    hi = np.array([(a[2] - origin) / 1e9 for a in anchors])
    slope = 1.0
    if len(anchors) > 1 and np.ptp(obx) > 1:
        slope = float(np.polyfit((lo + hi) / 2, obx, 1)[0])
    low, high = float(np.max(obx - slope * hi)), float(np.min(obx - slope * lo))
    return HostMap(origin, slope, low, high) if low <= high else None


@dataclass
class CameraFit:
    status: str  # inferred | ambiguous | no_latency_window | no_anchor | invalid
    offset: int | None = None
    margin_s: float = float("nan")
    residual_ms: float = float("nan")
    candidates: list[tuple[int, float]] = field(default_factory=list)


def camera_correspondence(
    camera_ns: Array,
    host_ns: Array,
    pulses_s: Array,
    anchor: HostMap | None,
    latency_window_s: tuple[float, float] | None,
    min_margin_s: float,
) -> tuple[Array, CameraFit]:
    """Infer one integer frame-to-pulse offset for one capture generation (A09).

    Native exposure timestamps give each frame's pulse position relative to the
    first frame, including missed triggers. Every candidate offset fits equally
    well, so only the host anchor plus a known camera latency window can pick one.
    Returns per-frame pulse indices (-1 unresolved) and the fit summary.
    """
    pulse_index = np.full(camera_ns.size, -1, np.int64)
    valid = camera_ns != np.iinfo(np.int64).min
    if valid.sum() < 2 or pulses_s.size < 2:
        return pulse_index, CameraFit("invalid")
    c = camera_ns[valid]
    # Round each interval, not the cumulative time: the median sits on one
    # quantization mode (rig: 33.33/33.42 ms at 29.978 Hz), so a cumulative
    # division drifts into false missed-trigger steps.
    intervals = np.diff(c)
    period = float(np.median(intervals))
    step = np.rint(intervals / period).astype(np.int64) if period > 0 else intervals
    steps = np.concatenate([[0], np.cumsum(step)])
    if period <= 0 or np.any(step < 1):
        return pulse_index, CameraFit("invalid")
    if anchor is None:
        return pulse_index, CameraFit("no_anchor")
    pulse_host = anchor.host_ns(pulses_s)
    h = host_ns[valid]
    sample = slice(None, None, max(1, h.size // 500))
    first = np.searchsorted(pulse_host, h[0] - 2e9)
    last = np.searchsorted(pulse_host, h[0] + 1e9)
    candidates = []
    for k in range(first, min(last, pulses_s.size - int(steps[-1]))):
        latency = (h[sample] - pulse_host[k + steps[sample]]) / 1e9
        candidates.append((k, float(np.median(latency))))
    fit = CameraFit("no_latency_window", candidates=candidates)
    if latency_window_s is None or not candidates:
        return pulse_index, fit
    lo, hi = latency_window_s
    u = anchor.uncertainty_s

    def gap(latency: float) -> float:
        return max(lo - (latency + u), (latency - u) - hi, 0.0)

    inside = [k for k, latency in candidates if gap(latency) == 0.0]
    others = [gap(latency) for k, latency in candidates if k not in inside]
    fit.margin_s = min(others, default=float("inf"))
    if len(inside) != 1 or fit.margin_s < min_margin_s:
        fit.status = "ambiguous"
        return pulse_index, fit
    fit.status, fit.offset = "inferred", inside[0]
    matched = pulses_s[fit.offset + steps]
    line = np.polyfit((c - c[0]) / 1e9, matched, 1)
    residual = matched - np.polyval(line, (c - c[0]) / 1e9)
    fit.residual_ms = float(np.sqrt(np.mean(residual**2)) * 1e3)
    pulse_index[np.flatnonzero(valid)] = fit.offset + steps
    return pulse_index, fit


def photodiode_match(
    host_ns: Array,
    high: Array,
    rises_s: Array,
    falls_s: Array,
    window: tuple[float, float],
    tolerance_fraction: float,
) -> Array:
    """Match V22 marker level changes to measured transitions; returns edge time or NaN.

    Idle shows no marker, so the trial's first bright submission is anchored to the
    first rise inside the Trial-state window. Later changes are matched in order with
    a running host->OneBox fit; same-level submissions have no edge and stay NaN.
    """
    times = np.full(host_ns.size, np.nan)
    previous = np.concatenate([[0], high[:-1]])
    change = np.flatnonzero((high != previous) & (high >= 0))
    rises = rises_s[(rises_s >= window[0]) & (rises_s < window[1])]
    falls = falls_s[(falls_s >= window[0]) & (falls_s < window[1])]
    if change.size < 2 or not rises.size or high[change[0]] != 1:
        return times
    x = (host_ns[change] - host_ns[change[0]]) / 1e9
    tolerance = tolerance_fraction * float(np.median(np.diff(x)))
    # Seed the host->display offset by in-order pairing after the renderer's
    # start-up queue settles (rig data: early swaps return faster than vsync).
    sequence = np.sort(np.concatenate([rises, falls]))
    seed = slice(
        min(SEED_SKIP, change.size // 2), min(SEED_SPAN, change.size, sequence.size)
    )
    line = np.array([1.0, float(np.median(sequence[seed] - x[seed]))])
    used = {1: -1, 0: -1}
    pairs_x: list[float] = []
    pairs_y: list[float] = []
    for i, row in enumerate(change):
        level = int(high[row])
        edges = rises if level == 1 else falls
        predicted = np.polyval(line, x[i])
        j = int(np.searchsorted(edges, predicted))
        best = min(
            (k for k in (j - 1, j) if used[level] < k < edges.size),
            key=lambda k: abs(edges[k] - predicted),
            default=None,
        )
        if best is None or abs(edges[best] - predicted) > tolerance:
            continue
        used[level] = best
        times[row] = edges[best]
        pairs_x.append(x[i])
        pairs_y.append(edges[best])
        if len(pairs_x) % REFIT_EVERY == 0:
            line = np.polyfit(pairs_x[-REFIT_SPAN:], pairs_y[-REFIT_SPAN:], 1)
    return times


def probe_map(
    obx_rises_s: Array,
    obx_origin_s: float,
    imec_rises_s: Array,
    imec_origin_s: float,
) -> JSON:
    """OneBox->probe linear map from the shared SY wave.

    ``*_origin_s`` is each file's firstSample / rate: both streams count from one
    acquisition start, which seeds nearest matching of the 1 s edges.
    """
    a, b = obx_rises_s + obx_origin_s, imec_rises_s + imec_origin_s
    if a.size < 2 or b.size < 2:
        return {"status": "unmatched", "n_pairs": 0}
    j = np.clip(np.searchsorted(b, a), 1, b.size - 1)
    nearest = np.where(np.abs(b[j - 1] - a) <= np.abs(b[j] - a), j - 1, j)
    keep = np.abs(b[nearest] - a) < SY_MATCH_S
    if keep.sum() < 2:
        return {"status": "unmatched", "n_pairs": int(keep.sum())}
    x, y = obx_rises_s[keep], imec_rises_s[nearest[keep]]
    slope, intercept = np.polyfit(x, y, 1)
    residual = y - (slope * x + intercept)
    return {
        "status": "fitted",
        "slope": float(slope),
        "intercept_s": float(intercept),
        "residual_ms": float(np.sqrt(np.mean(residual**2)) * 1e3),
        "max_residual_ms": float(np.max(np.abs(residual)) * 1e3),
        "n_pairs": int(keep.sum()),
        "n_obx_edges": int(a.size),
        "n_imec_edges": int(b.size),
    }
