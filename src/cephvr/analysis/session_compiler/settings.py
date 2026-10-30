"""Compile settings, including the pre-processing decisions made in the inspection notebook.

Defaults come from rig data (2026-10-30); the HDF5 stores the values actually used.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    overwrite: bool = False
    output_root: Path | None = None
    # Analog pulse detection: box smoothing removes projector sub-frame ripple on
    # the photodiode; Schmitt thresholds are fractions between the fitted levels.
    smooth_s: float = 0.001
    low_fraction: float = 0.25
    high_fraction: float = 0.75
    # Trial-state HIGH span vs expected host span when assigning trials to windows.
    window_tolerance_s: float = 0.1
    # Photodiode transition match tolerance, as a fraction of the marker interval.
    photodiode_tolerance: float = 0.4
    # Camera exposure-start -> host receipt latency (s) used to pick A09's frame/pulse
    # offset. Unset until measured on the rig; without it camera rows stay unresolved.
    camera_latency_s: tuple[float, float] | None = None
    # A09: the runner-up offset must sit at least this far outside the latency window.
    camera_min_margin_s: float = 0.002
    probe_sync: bool = True

    def decisions(self) -> dict[str, Any]:
        """JSON-ready pre-processing values (no output location or overwrite flag)."""
        values = asdict(self)
        values.pop("overwrite")
        values.pop("output_root")
        return values

    def save(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps(self.decisions(), indent=1) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    @classmethod
    def load(cls, path: Path, **overrides: Any) -> Settings:
        values = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {f.name for f in fields(cls)}
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"unknown settings {sorted(unknown)}")
        if values.get("camera_latency_s") is not None:
            values["camera_latency_s"] = tuple(values["camera_latency_s"])
        return cls(**(values | overrides))
