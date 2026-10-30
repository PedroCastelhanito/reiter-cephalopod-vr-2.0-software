"""AN01 compiled HDF5 layout. Paths stored in the file are relative to the session."""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np

from . import alignment, spikeglx
from .apply import TrialData, probe_label
from .hdf5io import session_view, write_array, write_json, write_table
from .session import Session, Trial, recorded_files
from .settings import Settings
from .streams import Stream
from .sync import Pulses
from .tables import JSON, build

COMPILED_SCHEMA_VERSION = 1
SESSION_LOG_SPEC = {
    "monotonic_ns": ("monotonic_ns", "i8"),
    "wall_time": ("wall_time", "str"),
    "event_type": ("event_type", "str"),
    "source": ("source", "str"),
    "trial_number": ("trial_number", "i8"),
    "outcome": ("outcome", "str"),
    "details": ("details", "json"),
}


def _relative(session: Session, path: Path) -> str:
    return Path(path).relative_to(session.directory).as_posix()


def _stream_group(group: h5py.Group, stream: Stream, session: Session) -> None:
    write_table(
        group,
        {},
        source_path=_relative(session, stream.path),
        version=int(stream.version),
        partial=stream.partial,
        truncated_final_line=stream.truncated,
    )
    write_json(group, "header", stream.header)
    write_json(group, "completion", stream.completion)
    for name, summary in stream.summaries.items():
        write_json(group, name, summary)
    for name, table in stream.tables.items():
        write_table(group.create_group(name), table)


def write_session(
    h5: h5py.File,
    session: Session,
    trials: list[tuple[Trial, TrialData]],
    pulses: Pulses | None,
    integrity: dict[int, list[JSON]],
    warnings: list[str],
    compiler_version: str,
    settings: Settings,
) -> None:
    config = session.config
    h5.attrs.update(
        compiled_schema_version=COMPILED_SCHEMA_VERSION,
        compiler_version=compiler_version,
        session_name=session.name,
        session_id=str(config.get("session_id", "")),
        session_setup_wall_time=str(config.get("session_setup_wall_time", "")),
        session_setup_monotonic_ns=int(config.get("session_setup_monotonic_ns") or 0),
        local_timezone=str(config.get("local_timezone", "")),
        timing_codes=json.dumps(alignment.TIMING_CODES),
        has_onebox=pulses is not None,
    )
    meta = h5.create_group("metadata")
    write_json(meta, "session_config", config)
    write_json(meta, "schema", session.schema)
    write_json(meta, "settings", settings.decisions())  # Pre-processing decisions used.
    write_table(
        meta.create_group("session_log"), build(session.events, SESSION_LOG_SPEC)
    )
    write_array(meta, "recovery_files", np.array(session.recovery_files, dtype=object))
    write_array(meta, "compilation_warnings", np.array(warnings, dtype=object))
    files = recorded_files(session.directory)
    provenance = meta.create_group("provenance")
    write_array(
        provenance,
        "relative_path",
        np.array([_relative(session, p) for p in files], dtype=object),
    )
    write_array(
        provenance,
        "size_bytes",
        np.array([p.stat().st_size for p in files], dtype=np.int64),
        unit="byte",
    )
    provenance.attrs["note"] = "File sizes only; not content checksums."

    views: dict[str, list[tuple[int, str]]] = {}
    for trial, data in trials:
        group = h5.create_group(f"trials/{trial.number:04d}")
        group.attrs.update(
            trial_number=trial.number,
            prefix=trial.prefix,
            outcome=trial.outcome,
            complete=bool(trial.log.get("complete")),
            start_host_ns=trial.start_ns or 0,
            stop_host_ns=trial.stop_ns or 0,
        )
        window = pulses.window(trial.number) if pulses else None
        group.attrs["trial_state_obx_s"] = window if window else (np.nan, np.nan)
        write_json(group, "trial_log", trial.log)
        write_table(
            group.create_group("integrity"),
            build(
                integrity.get(trial.number, []),
                {
                    "file": ("file", "str"),
                    "output_tag": ("output_tag", "str"),
                    "closure": ("closure", "str"),
                    "on_disk": ("on_disk", "b"),
                    "indexed_counts": ("indexed_counts", "json"),
                    "parsed_counts": ("parsed_counts", "json"),
                    "counts_match": ("counts_match", "b"),
                    "partial": ("partial", "b"),
                },
            ),
        )
        for role, stream in data.cameras.items():
            sub = group.create_group(f"cameras/{role}")
            _stream_group(sub, stream, session)
            write_json(sub, "alignment", data.camera_fits.get(role))
            video = trial.file(session.protocol, f"{role}_cam.mp4")
            sub.attrs["video_path"] = _relative(session, video) if video else ""
            views.setdefault(f"cameras/{role}/frames", []).append(
                (trial.number, sub.name + "/frames")
            )
        if data.stimulus is not None:
            sub = group.create_group("stimulus")
            _stream_group(sub, data.stimulus, session)
            write_json(sub, "stimulus_log", data.stimulus_log)
            write_json(sub, "photodiode", data.photodiode)
            video = trial.file(session.protocol, "stimulus.mp4")
            sub.attrs["video_path"] = _relative(session, video) if video else ""
            for name in ("render_groups", "submissions"):
                views.setdefault(f"stimulus/{name}", []).append(
                    (trial.number, f"{sub.name}/{name}")
                )
        if data.tracking is not None:
            sub = group.create_group("tracking")
            _stream_group(sub, data.tracking, session)
            views.setdefault("tracking/poses", []).append(
                (trial.number, sub.name + "/poses")
            )
    for path, parts in views.items():
        session_view(h5, f"session/{path}", parts)
    if pulses is not None:
        _write_spikeglx(h5, session, pulses)


def _write_spikeglx(h5: h5py.File, session: Session, pulses: Pulses) -> None:
    group = h5.create_group("spikeglx")
    group.attrs.update(
        onebox_path=_relative(session, pulses.path),
        sample_rate_hz=pulses.rate_hz,
        sy_bit=spikeglx.SY_BIT,
        time_origin="first sample of the OneBox file",
    )
    write_json(group, "onebox_meta", pulses.meta)
    for role, (rises, falls) in pulses.edges.items():
        edges = group.create_group(f"edges/{role}")
        write_array(edges, "rise_obx_s", rises, unit="s")
        write_array(edges, "fall_obx_s", falls, unit="s")
    write_array(
        group,
        "trial_state_windows_obx_s",
        np.array(pulses.windows, dtype=np.float64).reshape(-1, 2),
        unit="s",
    )
    if pulses.sy_rises_s is not None:
        write_array(group, "sy_rise_obx_s", pulses.sy_rises_s, unit="s")
    for probe in pulses.probes:
        sub = group.create_group(f"probes/{probe_label(probe)}")
        sub.attrs["ap_path"] = _relative(session, probe["path"])
        write_json(sub, "meta", probe["meta"])
        write_json(sub, "obx_to_probe", probe["map"])
        if "sy_rises_s" in probe:
            write_array(sub, "sy_rise_s", probe["sy_rises_s"], unit="s")
