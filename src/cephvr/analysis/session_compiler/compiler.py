"""Compile sessions: read trial streams, align to SpikeGLX pulses, write one HDF5 (AN01)."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from . import apply
from .apply import TrialData
from .hdf5io import atomic_hdf5
from .jsonl import read_json
from .session import Session, Trial, indexed_outputs, load_session
from .settings import Settings
from .streams import Stream, read_camera, read_stimulus, read_tracking
from .sync import Pulses, load_pulses
from .tables import JSON
from .writer import write_session

COMPILER_VERSION = "1"
logger = logging.getLogger(__name__)


@dataclass
class CompileReport:
    """Plain fields so a report survives a process-pool round trip."""

    session: str
    status: str = "written"  # written | skipped_exists | failed
    output: str = ""
    n_trials: int = 0
    has_onebox: bool = False
    duration_s: float = 0.0
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    stage_duration_s: dict[str, float] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return Path(self.session).name

    @property
    def ok(self) -> bool:
        return self.status != "failed"


def output_path(session_dir: Path, settings: Settings) -> Path:
    session_dir = Path(session_dir)
    return (settings.output_root or session_dir) / f"{session_dir.name}.h5"


def _read(
    reader: Callable[[Path], Stream], path: Path | None, warnings: list[str]
) -> Stream | None:
    if path is None:
        return None
    try:
        stream = reader(path)
    except (OSError, ValueError, KeyError) as error:
        warnings.append(f"{path.name}: not compiled ({error})")
        return None
    if stream.partial:
        warnings.append(f"{path.name}: partial (no completion line or truncated)")
    return stream


def read_trial(session: Session, trial: Trial, warnings: list[str]) -> TrialData:
    protocol = session.protocol
    data = TrialData(trial.number)
    for role in trial.camera_roles(protocol):
        stream = _read(
            read_camera, trial.file(protocol, f"{role}_cam_frames.jsonl"), warnings
        )
        if stream is not None:
            data.cameras[role] = stream
    data.stimulus = _read(
        read_stimulus, trial.file(protocol, "stimulus_frames.jsonl"), warnings
    )
    recipe = trial.file(protocol, "stimulus_LOG.json")
    data.stimulus_log = read_json(recipe) if recipe else None
    data.tracking = _read(
        read_tracking, trial.file(protocol, "tracking.jsonl"), warnings
    )
    return data


def trial_span_s(trial: Trial, data: TrialData) -> float | None:
    """Expected Trial-state HIGH span: ON/OFF dispatch (A11), else the recorded cutoff.

    An interrupted trial's ``trial_finished`` event follows its cutoff, so the log
    interval is only the last resort.
    """
    for stream in data.cameras.values():
        pulses = (stream.completion or {}).get("pulses") or {}
        on, off = (
            pulses.get("on_dispatched_monotonic_ns"),
            pulses.get("off_dispatched_monotonic_ns"),
        )
        if on is not None and off is not None:
            return float(off - on) / 1e9
    cutoff = (
        (data.stimulus.completion or {}).get("cutoff_host_ns")
        if data.stimulus
        else None
    )
    end = cutoff if cutoff is not None else trial.stop_ns
    if trial.start_ns is None or end is None:
        return None
    return float(end - trial.start_ns) / 1e9


def _parsed_counts(file: str, data: TrialData) -> JSON:
    for stream in data.cameras.values():
        if stream.path.name == file:
            return {
                "source_frames": len(stream.tables["frames"]["frame_id"]),
                "video_frames": len(stream.tables["video_map"]["encoded_frame_index"]),
            }
    if data.stimulus is not None and data.stimulus.path.name == file:
        return {"render_groups": len(data.stimulus.tables["render_groups"]["group_id"])}
    return {}


def integrity_rows(
    session: Session, trial: Trial, data: TrialData, warnings: list[str]
) -> list[JSON]:
    rows = []
    for file, item in indexed_outputs(trial).items():
        parsed = _parsed_counts(file, data)
        indexed = item.get("counts") or {}
        shared = set(parsed) & set(indexed)
        match = all(parsed[k] == indexed[k] for k in shared) if shared else None
        on_disk = (session.protocol / file).is_file()
        if match is False or not on_disk:
            warnings.append(
                f"Trial {trial.number} {file}: on_disk={on_disk} counts {parsed} vs LOG {indexed}"
            )
        stream = next(
            (
                s
                for s in [*data.cameras.values(), data.stimulus, data.tracking]
                if s is not None and s.path.name == file
            ),
            None,
        )
        rows.append(
            {
                "file": file,
                "output_tag": item.get("output_tag"),
                "closure": item.get("closure"),
                "on_disk": on_disk,
                "indexed_counts": indexed,
                "parsed_counts": parsed,
                "counts_match": match,
                "partial": None if stream is None else stream.partial,
            }
        )
    return rows


def compile_session(
    session_dir: Path, settings: Settings | None = None
) -> CompileReport:
    settings = settings or Settings()
    started = time.monotonic()
    session_dir = Path(session_dir)
    output = output_path(session_dir, settings)
    report = CompileReport(str(session_dir), output=str(output))
    if output.exists() and not settings.overwrite:
        report.status = "skipped_exists"
        return report
    warnings = report.warnings
    session = load_session(session_dir, warnings)
    stage = time.monotonic()
    trials = [(trial, read_trial(session, trial, warnings)) for trial in session.trials]
    report.stage_duration_s["read_streams"] = time.monotonic() - stage
    stage = time.monotonic()
    cameras = {role for _, data in trials for role in data.cameras}
    spans = {t.number: s for t, d in trials if (s := trial_span_s(t, d)) is not None}
    pulses = load_pulses(session, cameras, spans, warnings, settings)
    report.stage_duration_s["spikeglx"] = time.monotonic() - stage
    stage = time.monotonic()
    _align(pulses, [data for _, data in trials], settings, warnings)
    report.stage_duration_s["align"] = time.monotonic() - stage
    integrity = {t.number: integrity_rows(session, t, d, warnings) for t, d in trials}
    stage = time.monotonic()
    output.parent.mkdir(parents=True, exist_ok=True)
    with atomic_hdf5(output) as h5:
        write_session(
            h5, session, trials, pulses, integrity, warnings, COMPILER_VERSION, settings
        )
    report.stage_duration_s["write"] = time.monotonic() - stage
    report.n_trials = len(trials)
    report.has_onebox = pulses is not None
    report.duration_s = time.monotonic() - started
    return report


def _align(
    pulses: Pulses | None,
    trials: list[TrialData],
    settings: Settings,
    warnings: list[str],
) -> None:
    tables = []
    for data in trials:
        tables += [s.tables["frames"] for s in data.cameras.values()]
        if data.stimulus is not None:
            tables += [
                data.stimulus.tables["submissions"],
                data.stimulus.tables["render_groups"],
            ]
        if data.tracking is not None:
            tables.append(data.tracking.tables["poses"])
    if pulses is None:
        for table in tables:
            apply.mark_unresolved(table)
        return
    anchor = apply.trial_anchor(pulses, trials)
    apply.align_cameras(pulses, trials, anchor, settings)
    for data in trials:
        apply.align_stimulus(pulses, data, settings.photodiode_tolerance)
        apply.align_tracking(data)
        for role, fit in data.camera_fits.items():
            if fit["status"] != "inferred":
                warnings.append(
                    f"Trial {data.number} {role} camera: OneBox time unresolved ({fit['status']})"
                )
        if data.stimulus is not None and data.photodiode.get("status") != "matched":
            warnings.append(
                f"Trial {data.number} stimulus: photodiode {data.photodiode.get('status')}"
            )
    apply.add_probe_times(pulses, tables)


def _compile_one(arguments: tuple[Path, Settings]) -> CompileReport:
    """Worker entry point: never raises, so one bad session cannot stop a batch."""
    session_dir, settings = arguments
    try:
        return compile_session(session_dir, settings)
    except Exception as error:  # Reported per session; a batch continues.
        logger.exception("%s: compile failed", Path(session_dir).name)
        return CompileReport(
            str(session_dir), status="failed", error=f"{type(error).__name__}: {error}"
        )


def compile_sessions(
    sessions: Sequence[Path],
    settings: Settings | None = None,
    *,
    max_workers: int | None = None,
    on_report: Callable[[CompileReport], None] | None = None,
) -> list[CompileReport]:
    """Compile sessions, one process each when several run; reports arrive in completion order."""
    settings = settings or Settings()
    unique = list({Path(s).resolve(): Path(s) for s in sessions}.values())
    workers = min(len(unique), max_workers or min(os.cpu_count() or 1, 4))
    reports: list[CompileReport] = []
    if workers <= 1:
        for session in unique:
            reports.append(_compile_one((session, settings)))
            if on_report:
                on_report(reports[-1])
        return reports
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_compile_one, (s, settings)) for s in unique]
        for future in as_completed(futures):
            reports.append(future.result())
            if on_report:
                on_report(reports[-1])
    return reports
