"""Attach OneBox/probe times to compiled trial tables (AN01 timing rules)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .alignment import (
    INFERRED,
    MEASURED,
    CameraFit,
    HostMap,
    camera_correspondence,
    host_map,
    photodiode_match,
)
from .settings import Settings
from .streams import Stream
from .sync import Pulses
from .tables import INT_FILL, JSON, Table


@dataclass
class TrialData:
    number: int
    cameras: dict[str, Stream] = field(default_factory=dict)
    stimulus: Stream | None = None
    stimulus_log: JSON | None = None
    tracking: Stream | None = None
    camera_fits: dict[str, JSON] = field(default_factory=dict)
    photodiode: JSON = field(default_factory=dict)


def mark_unresolved(table: Table) -> None:
    n = len(next(iter(table.values()))) if table else 0
    table["time_obx_s"] = np.full(n, np.nan)
    table["timing_status"] = np.zeros(n, np.int8)


def trial_anchor(pulses: Pulses, trials: list[TrialData]) -> HostMap | None:
    """Trial-state edges bounded by the ON/OFF command dispatch and acknowledgement."""
    anchors = []
    for data in trials:
        window = pulses.window(data.number)
        completion = next(
            (s.completion for s in data.cameras.values() if s.completion), None
        )
        if window is None or not completion or not completion.get("pulses"):
            continue
        p = completion["pulses"]
        anchors.append(
            (
                window[0],
                p.get("on_dispatched_monotonic_ns"),
                p.get("on_acknowledged_monotonic_ns"),
            )
        )
        anchors.append(
            (
                window[1],
                p.get("off_dispatched_monotonic_ns"),
                p.get("off_acknowledged_monotonic_ns"),
            )
        )
    return host_map(anchors)


def align_cameras(
    pulses: Pulses,
    trials: list[TrialData],
    anchor: HostMap | None,
    settings: Settings,
) -> None:
    """One offset per (role, capture generation); v5 logs without a generation use the trial."""
    scopes: dict[tuple[str, str], list[TrialData]] = {}
    for data in trials:
        for role, stream in data.cameras.items():
            mark_unresolved(stream.tables["frames"])
            identity = stream.header.get("identity", {})
            scope = identity.get("capture_generation") or f"trial-{data.number}"
            scopes.setdefault((role, scope), []).append(data)
    for (role, scope), members in scopes.items():
        key = f"{role}_camera"
        frames = [m.cameras[role].tables["frames"] for m in members]
        if key not in pulses.edges:
            fit = CameraFit("no_pulse_role")
            index = np.full(sum(len(f["frame_id"]) for f in frames), -1)
        else:
            rises = pulses.edges[key][0]
            camera_ns = np.concatenate([f["camera_timestamp_ns"] for f in frames])
            host_ns = np.concatenate([f["host_receipt_ns"] for f in frames])
            index, fit = camera_correspondence(
                camera_ns,
                host_ns,
                rises,
                anchor,
                settings.camera_latency_s,
                settings.camera_min_margin_s,
            )
        offset = 0
        for member, table in zip(members, frames, strict=True):
            count = len(table["frame_id"])
            part = index[offset : offset + count]
            offset += count
            table["pulse_index"] = part
            ok = part >= 0
            if ok.any():
                table["time_obx_s"][ok] = pulses.edges[key][0][part[ok]]
                table["timing_status"][ok] = INFERRED
            window = pulses.window(member.number)
            table["in_trial_state"] = np.array(
                [
                    -1 if not k or window is None else int(window[0] <= t < window[1])
                    for k, t in zip(ok, table["time_obx_s"], strict=True)
                ],
                dtype=np.int8,
            )
            member.camera_fits[role] = {
                "scope": scope,
                "status": fit.status,
                "pulse_offset": fit.offset,
                "margin_ms": fit.margin_s * 1e3,
                "residual_ms": fit.residual_ms,
                "candidates": [
                    {"pulse_offset": k, "median_latency_ms": round(v * 1e3, 3)}
                    for k, v in fit.candidates
                    if -0.2 <= v <= 0.5
                ],
            }


def photodiode_output(stimulus_log: JSON | None) -> str | None:
    display = (stimulus_log or {}).get("display") or {}
    if not display.get("photodiode_enabled"):
        return None
    patches = display.get("photodiode_patches")
    outputs = list(patches) if patches else [display.get("photodiode_output_id")]
    outputs = [o for o in outputs if o]
    return outputs[0] if len(outputs) == 1 else None


def align_stimulus(pulses: Pulses, data: TrialData, tolerance_fraction: float) -> None:
    stream = data.stimulus
    if stream is None:
        return
    submissions, groups = stream.tables["submissions"], stream.tables["render_groups"]
    mark_unresolved(submissions)
    mark_unresolved(groups)
    output = photodiode_output(data.stimulus_log)
    window = pulses.window(data.number)
    data.photodiode = {"output_id": output or "", "status": "unresolved"}
    if output is None or window is None or "photodiode" not in pulses.edges:
        data.photodiode["status"] = "no_single_patch_window_or_role"
        return
    rows = np.flatnonzero(
        (submissions["output_id"] == output) & (submissions["marker_high"] >= 0)
    )
    # A GroupUpdate resolves an earlier attempt: keep each group's last observation.
    order = rows[
        np.lexsort((submissions["group_update"][rows], submissions["group_id"][rows]))
    ]
    last = np.r_[
        submissions["group_id"][order][1:] != submissions["group_id"][order][:-1], True
    ]
    order = order[last]
    host = submissions["return_host_ns"][order]
    host = np.where(host == INT_FILL, submissions["entry_host_ns"][order], host)
    rises, falls = pulses.edges["photodiode"]
    times = photodiode_match(
        host,
        submissions["marker_high"][order],
        rises,
        falls,
        window,
        tolerance_fraction,
    )
    matched = ~np.isnan(times)
    submissions["time_obx_s"][order[matched]] = times[matched]
    submissions["timing_status"][order[matched]] = MEASURED
    position = np.searchsorted(
        groups["group_id"], submissions["group_id"][order[matched]]
    )
    groups["time_obx_s"][position] = times[matched]
    groups["timing_status"][position] = MEASURED
    data.photodiode.update(
        status="matched",
        matched=int(matched.sum()),
        level_changes=int(
            np.count_nonzero(np.diff(np.r_[0, submissions["marker_high"][order]]))
        ),
    )


def align_tracking(data: TrialData) -> None:
    """Poses inherit their source frame's time from the tracking camera log (A09 IDs)."""
    if data.tracking is None:
        return
    poses = data.tracking.tables["poses"]
    mark_unresolved(poses)
    camera = data.cameras.get("tracking")
    if camera is None:
        return
    frames = camera.tables["frames"]
    lookup = {int(f): i for i, f in enumerate(frames["frame_id"])}
    for row, frame_id in enumerate(poses["source_frame_id"]):
        i = lookup.get(int(frame_id))
        if i is not None:
            poses["time_obx_s"][row] = frames["time_obx_s"][i]
            poses["timing_status"][row] = frames["timing_status"][i]


def add_probe_times(pulses: Pulses, tables: list[Table]) -> None:
    for probe in pulses.probes:
        fit = probe["map"]
        if fit.get("status") != "fitted":
            continue
        name = f"time_{probe_label(probe)}_s"
        for table in tables:
            if "time_obx_s" in table:
                table[name] = fit["slope"] * table["time_obx_s"] + fit["intercept_s"]


def probe_label(probe: JSON) -> str:
    """``imec0`` from ``run_g0_t0.imec0.ap.bin``."""
    return str(probe["path"].name.split(".")[-3])
