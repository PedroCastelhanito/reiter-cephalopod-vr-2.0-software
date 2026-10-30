"""Native SpikeGLX files: run lookup, metadata, channel reads and pulse edges (E09/E12).

Edge-detection parameters come from ``Settings`` (inspection-notebook decisions).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .session import SPIKEGLX_DIRNAME
from .tables import Array

SY_BIT = 6  # SpikeGLX imec/OneBox SY word sync bit (rig meta and data, 2026-10-30).
READ_BLOCK_ROWS = 2_000_000


def parse_meta(path: Path) -> dict[str, str]:
    meta = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            meta[key.strip()] = value.strip()
    return meta


def run_folders(session_dir: Path, run_name: str) -> list[Path]:
    root = Path(session_dir) / SPIKEGLX_DIRNAME
    return sorted(p for p in root.glob(f"{run_name}_g*") if p.is_dir())


def onebox_file(session_dir: Path, run_name: str, index: int) -> list[Path]:
    pattern = f"*.obx{index}.obx.bin"
    return sorted(
        p for f in run_folders(session_dir, run_name) for p in f.glob(pattern)
    )


def probe_files(session_dir: Path, run_name: str) -> list[Path]:
    """Native AP files; os.walk skips unreadable or over-long sorting-output paths."""
    return sorted(
        Path(folder, name)
        for run in run_folders(session_dir, run_name)
        for folder, _, names in os.walk(run)
        for name in names
        if ".imec" in name and name.endswith(".ap.bin")
    )


def sample_rate(meta: dict[str, str]) -> float:
    return float(meta.get("obSampRate") or meta["imSampRate"])


def saved_column(meta: dict[str, str], channel: int) -> int:
    """File column of an acquisition channel index (pulse inventory uses saved indices)."""
    subset = meta.get("snsSaveChanSubset", "all")
    if subset == "all":
        return channel
    saved: list[int] = []
    for part in subset.split(","):
        start, _, stop = part.partition(":")
        saved.extend(range(int(start), int(stop or start) + 1))
    return saved.index(channel)


def sy_column(meta: dict[str, str]) -> int | None:
    entries = meta.get("~snsChanMap", "").split(")(")[1:]
    for position, entry in enumerate(entries):
        if entry.lstrip("(").startswith("SY"):
            return position
    return None


def read_columns(path: Path, n_saved: int, columns: list[int]) -> dict[int, Array]:
    """Sequential block reads; one pass over the file serves every requested column."""
    flat = np.memmap(path, dtype=np.int16, mode="r")
    data = flat[: flat.size - flat.size % n_saved].reshape(-1, n_saved)
    out = {c: np.empty(data.shape[0], np.int16) for c in columns}
    for start in range(0, data.shape[0], READ_BLOCK_ROWS):
        block = np.asarray(data[start : start + READ_BLOCK_ROWS])
        for c in columns:
            out[c][start : start + len(block)] = block[:, c]
    return out


def _transitions(state: Array) -> tuple[Array, Array]:
    change = np.flatnonzero(state[1:] != state[:-1]) + 1
    rising = state[change]
    return change[rising], change[~rising]


def levels(signal: Array) -> tuple[float, float]:
    """Two-level fit (1D two-means) on a subsample; robust to ripple and rare levels."""
    sample = signal[:: max(1, signal.size // 2_000_000)].astype(np.float64)
    threshold = (sample.min() + sample.max()) / 2
    low = high = threshold
    for _ in range(8):
        below, above = sample[sample < threshold], sample[sample >= threshold]
        if not below.size or not above.size:
            break
        low, high = float(np.median(below)), float(np.median(above))
        threshold = (low + high) / 2
    return low, high


@dataclass
class Edges:
    """Edge sample indices plus the levels/thresholds that produced them."""

    rises: Array
    falls: Array
    low: float = 0.0
    high: float = 1.0
    lower_threshold: float = 0.5
    upper_threshold: float = 0.5
    smooth_samples: int = 1


def smooth(signal: Array, width: int) -> Array:
    """Box mean; sample i covers signal[i : i + width] (centre offset (width-1)//2)."""
    total = np.concatenate([[0], np.cumsum(signal, dtype=np.int64)])
    mean: Array = (total[width:] - total[:-width]) / width
    return mean


def analog_edges(
    signal: Array,
    rate_hz: float,
    smooth_s: float,
    low_fraction: float,
    high_fraction: float,
) -> Edges:
    """Rising/falling sample indices: box smoothing, then a Schmitt trigger."""
    empty = np.array([], np.int64)
    width = max(1, round(smooth_s * rate_hz))
    if signal.size <= width + 2:
        return Edges(empty, empty)
    smoothed = smooth(signal, width)
    low, high = levels(smoothed)
    lower, upper = low + (high - low) * low_fraction, low + (high - low) * high_fraction
    edges = Edges(empty, empty, low, high, lower, upper, width)
    if high - low <= 0:
        return edges
    marks = np.full(smoothed.size, -1, np.int8)
    marks[smoothed <= lower] = 0
    marks[smoothed >= upper] = 1
    last = np.where(marks >= 0, np.arange(smoothed.size), 0)
    np.maximum.accumulate(last, out=last)
    rises, falls = _transitions(marks[last] == 1)
    delay = (width - 1) // 2  # Centre the box window on the original samples.
    edges.rises, edges.falls = rises + delay, falls + delay
    return edges


def digital_edges(word: Array, bit: int) -> Edges:
    return Edges(*_transitions(((word >> bit) & 1).astype(bool)))


def sy_bit(word: Array) -> int | None:
    toggling = [
        b for b in range(16) if 0 < np.count_nonzero((word >> b) & 1) < word.size
    ]
    if SY_BIT in toggling:
        return SY_BIT
    return toggling[0] if len(toggling) == 1 else None
