"""Session pulse loading: OneBox role edges, Trial-state windows and probe SY maps.

Each step is a separate call so the inspection notebook can show and tune it;
``load_pulses`` runs them in order for the compiler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import spikeglx
from .alignment import match_windows, probe_map
from .session import Session
from .settings import Settings
from .tables import JSON, Array

ROLE_PREFIX = "PULSE_ROLE_"
SY = "sy"  # Signal key for the OneBox SY word.


@dataclass
class OneBox:
    path: Path
    meta: dict[str, str]
    rate_hz: float
    run_name: str
    roles: dict[str, JSON]  # role -> recorded pulse_channels mapping
    columns: dict[str, int]  # role (and "sy") -> file column


@dataclass
class Pulses:
    path: Path
    meta: dict[str, str]
    rate_hz: float
    edges: dict[str, tuple[Array, Array]] = field(default_factory=dict)
    sy_rises_s: Array | None = None
    windows: list[tuple[float, float]] = field(default_factory=list)
    trial_windows: dict[int, int] = field(default_factory=dict)  # trial -> window
    probes: list[JSON] = field(default_factory=list)

    @property
    def origin_s(self) -> float:
        return float(self.meta.get("firstSample", 0)) / self.rate_hz

    def window(self, trial: int) -> tuple[float, float] | None:
        index = self.trial_windows.get(trial)
        return None if index is None else self.windows[index]


def pulse_roles(config: JSON) -> dict[str, JSON]:
    """Role -> mapping from the session's recorded SpikeGLX preparation (E12).

    Protobuf JSON omits zero values: an absent channel/stream index means 0, while an
    absent ``bit`` means an analog channel, never bit 0.
    """
    roles = {}
    for item in (config.get("spikeglx") or {}).get("pulse_channels", ()):
        role = str(item.get("role", "")).removeprefix(ROLE_PREFIX).lower()
        roles[role] = item
    return roles


def open_onebox(
    session: Session, cameras: set[str], warnings: list[str]
) -> OneBox | None:
    """``cameras``: roles with frame logs; unused (possibly floating) inputs are skipped."""
    spikeglx_config = session.config.get("spikeglx")
    if not spikeglx_config:
        warnings.append("Unpaired session: no SpikeGLX timing (host times only)")
        return None
    run = str(spikeglx_config.get("run_name", ""))
    wanted = {"trial_state", "photodiode", *(f"{c}_camera" for c in cameras)}
    roles = {
        r: m
        for r, m in pulse_roles(session.config).items()
        if m.get("family") == "STREAM_FAMILY_ONEBOX" and r in wanted
    }
    indexes = {int(m.get("stream_index", 0)) for m in roles.values()}
    if len(indexes) != 1:
        warnings.append(
            f"Pulse roles span OneBox streams {sorted(indexes)}; unsupported"
        )
        return None
    files = spikeglx.onebox_file(session.directory, run, indexes.pop())
    if len(files) != 1:
        warnings.append(
            f"Expected one OneBox file for run {run} in spikeglx-data, found {len(files)}"
        )
        return None
    meta = spikeglx.parse_meta(files[0].with_suffix(".meta"))
    columns = {
        r: spikeglx.saved_column(meta, int(m.get("channel_index", 0)))
        for r, m in roles.items()
    }
    sy = spikeglx.sy_column(meta)
    if sy is not None:
        columns[SY] = sy
    return OneBox(files[0], meta, spikeglx.sample_rate(meta), run, roles, columns)


def read_signals(onebox: OneBox) -> dict[str, Array]:
    """One sequential pass over the OneBox file; role (and "sy") -> raw int16 samples."""
    data = spikeglx.read_columns(
        onebox.path,
        int(onebox.meta["nSavedChans"]),
        sorted(set(onebox.columns.values())),
    )
    return {key: data[column] for key, column in onebox.columns.items()}


def detect_edges(
    onebox: OneBox, signals: dict[str, Array], settings: Settings
) -> dict[str, spikeglx.Edges]:
    edges = {}
    for role, mapping in onebox.roles.items():
        if "bit" in mapping:
            edges[role] = spikeglx.digital_edges(signals[role], int(mapping["bit"]))
        else:
            edges[role] = spikeglx.analog_edges(
                signals[role],
                onebox.rate_hz,
                settings.smooth_s,
                settings.low_fraction,
                settings.high_fraction,
            )
    if SY in signals:
        bit = spikeglx.sy_bit(signals[SY])
        if bit is not None:
            edges[SY] = spikeglx.digital_edges(signals[SY], bit)
    return edges


def to_pulses(onebox: OneBox, edges: dict[str, spikeglx.Edges]) -> Pulses:
    pulses = Pulses(onebox.path, onebox.meta, onebox.rate_hz)
    for role, found in edges.items():
        times = (found.rises / onebox.rate_hz, found.falls / onebox.rate_hz)
        if role == SY:
            pulses.sy_rises_s = times[0]
        else:
            pulses.edges[role] = times
    return pulses


def assign_windows(
    pulses: Pulses,
    spans_s: dict[int, float],
    trials: list[int],
    tolerance_s: float,
    warnings: list[str],
) -> None:
    """Pair Trial-state rises with the next fall; match trials by expected span."""
    if "trial_state" not in pulses.edges:
        warnings.append("No trial_state pulse role; trials have no OneBox window")
        return
    rises, falls = pulses.edges["trial_state"]
    pulses.windows = []
    for rise in rises:
        later = falls[falls > rise]
        if later.size:
            pulses.windows.append((float(rise), float(later[0])))
    numbers = sorted(spans_s)
    mapping = match_windows([spans_s[n] for n in numbers], pulses.windows, tolerance_s)
    pulses.trial_windows = {numbers[i]: w for i, w in mapping.items()}
    for number in trials:
        if number not in pulses.trial_windows:
            warnings.append(f"Trial {number}: no unique Trial-state window")


def probe_maps(session: Session, run: str, pulses: Pulses, warnings: list[str]) -> None:
    pulses.probes = []
    for path in spikeglx.probe_files(session.directory, run):
        meta = spikeglx.parse_meta(path.with_suffix(".meta"))
        entry: JSON = {"path": path, "meta": meta, "map": {"status": "no_shared_sync"}}
        pulses.probes.append(entry)
        shared = meta.get("syncSourceIdx") == pulses.meta.get("syncSourceIdx") != "0"
        sy = spikeglx.sy_column(meta)
        if not shared or sy is None or pulses.sy_rises_s is None:
            warnings.append(
                f"{path.name}: no shared SY with OneBox; probe time unresolved"
            )
            continue
        word = spikeglx.read_columns(path, int(meta["nSavedChans"]), [sy])[sy]
        bit = spikeglx.sy_bit(word)
        if bit is None:
            warnings.append(f"{path.name}: SY bit not found")
            continue
        rate = spikeglx.sample_rate(meta)
        entry["sy_rises_s"] = spikeglx.digital_edges(word, bit).rises / rate
        origin = float(meta.get("firstSample", 0)) / rate
        entry["map"] = probe_map(
            pulses.sy_rises_s, pulses.origin_s, entry["sy_rises_s"], origin
        )
        if entry["map"]["status"] != "fitted":
            warnings.append(f"{path.name}: SY edges did not match OneBox")


def load_pulses(
    session: Session,
    cameras: set[str],
    spans_s: dict[int, float],
    warnings: list[str],
    settings: Settings,
) -> Pulses | None:
    """``spans_s``: each trial's expected Trial-state HIGH duration on the host clock."""
    onebox = open_onebox(session, cameras, warnings)
    if onebox is None:
        return None
    pulses = to_pulses(onebox, detect_edges(onebox, read_signals(onebox), settings))
    numbers = [t.number for t in session.trials]
    assign_windows(pulses, spans_s, numbers, settings.window_tolerance_s, warnings)
    if settings.probe_sync:
        probe_maps(session, onebox.run_name, pulses, warnings)
    return pulses
