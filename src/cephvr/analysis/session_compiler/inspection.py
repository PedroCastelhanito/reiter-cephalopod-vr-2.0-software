"""Marimo pre-processing inspection (AN01): ``marimo edit -m cephvr.analysis.session_compiler.inspection``.

Runs each compiler step on one session and shows what it decided: pulse
detection, Trial-state windows, the host anchor, camera frame/pulse offsets,
photodiode matches and the probe SY map. Tune the controls, then save the
settings or compile with them. Requires the ``analysis`` extra (plotly included).
"""

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def overview(mo):
    mo.md("""
    # Session pre-processing inspection

    Check every step that turns recorded files into OneBox times before compiling.
    Times ending in `_obx_s` are seconds from the first sample of the session's OneBox
    file; host times are `perf_counter_ns`. Rows without a recorded pulse stay
    unresolved (AN01): nothing here invents a time.
    """)
    return


@app.cell(hide_code=True)
def imports():
    import json
    from pathlib import Path

    import marimo as mo
    import numpy as np
    import plotly.graph_objects as go

    from cephvr.analysis.session_compiler import apply, compiler, sync
    from cephvr.analysis.session_compiler.session import discover_sessions, load_session
    from cephvr.analysis.session_compiler.settings import Settings

    return (
        Path,
        Settings,
        apply,
        compiler,
        discover_sessions,
        go,
        json,
        load_session,
        mo,
        np,
        sync,
    )


@app.cell(hide_code=True)
def helpers(go, np):
    MAX_POINTS = 200_000

    def thin(*arrays):
        """Stride every array equally so plots stay responsive."""
        step = max(1, arrays[0].size // MAX_POINTS)
        return [a[::step] for a in arrays]

    def scatter(x, y, name, mode="markers", **kwargs):
        x, y = thin(np.asarray(x), np.asarray(y))
        return go.Scattergl(x=x, y=y, mode=mode, name=name, **kwargs)

    def figure(traces, title, xaxis, yaxis, height=420):
        fig = go.Figure(traces)
        fig.update_layout(
            title=title,
            xaxis_title=xaxis,
            yaxis_title=yaxis,
            height=height,
            legend=dict(orientation="h", y=1.02, yanchor="bottom"),
        )
        return fig

    return figure, scatter, thin


@app.cell(hide_code=True)
def select_header(mo):
    mo.md("""
    ## Select a session

    Set `SESSION_PATH` or pick a folder. A parent folder lists every session below it.
    SpikeGLX runs must sit in the session's `spikeglx-data` folder.
    """)
    return


@app.cell
def session_path():
    SESSION_PATH = r""  # Leave empty to open the folder picker.
    return (SESSION_PATH,)


@app.cell(hide_code=True)
def pick_session(Path, SESSION_PATH, discover_sessions, mo):
    def _pick():
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return filedialog.askdirectory(title="Session folder or a parent") or ""
        finally:
            root.destroy()

    _root = SESSION_PATH.strip() or _pick()
    mo.stop(
        not _root or not Path(_root).is_dir(), mo.md("Choose a folder to continue.")
    )
    _sessions = discover_sessions(Path(_root))
    mo.stop(not _sessions, mo.md(f"No sessions under `{_root}`."))
    session_choice = mo.ui.dropdown(
        options={s.name: s for s in _sessions}, value=_sessions[0].name, label="Session"
    )
    session_choice
    return (session_choice,)


@app.cell(hide_code=True)
def load_inputs(compiler, load_session, mo, session_choice):
    input_warnings = []
    with mo.status.spinner(title="Reading trial files (stimulus evidence is large)..."):
        session = load_session(session_choice.value, input_warnings)
        trial_data = [
            (t, compiler.read_trial(session, t, input_warnings)) for t in session.trials
        ]
    spans = {
        t.number: _s
        for t, d in trial_data
        if (_s := compiler.trial_span_s(t, d)) is not None
    }
    return input_warnings, session, spans, trial_data


@app.cell(hide_code=True)
def inputs_header(mo):
    mo.md("""
    ## Inputs and integrity

    Files found per trial, whether each stream closed (a missing completion line means
    partial) and parsed counts against the trial LOG's output index. The expected
    Trial-state span comes from the ON/OFF command dispatch times when a camera
    recorded them, otherwise the stimulus cutoff, otherwise SESSION_LOG.
    """)
    return


@app.cell(hide_code=True)
def inputs_table(compiler, input_warnings, mo, spans, session, trial_data):
    _rows, _integrity = [], []
    for _trial, _data in trial_data:
        _streams = {f"{r} camera": s for r, s in _data.cameras.items()}
        if _data.stimulus is not None:
            _streams["stimulus"] = _data.stimulus
        if _data.tracking is not None:
            _streams["tracking"] = _data.tracking
        _rows.append(
            {
                "trial": _trial.number,
                "prefix": _trial.prefix,
                "outcome": _trial.outcome,
                "LOG complete": bool(_trial.log.get("complete")),
                "expected span (s)": round(spans.get(_trial.number, float("nan")), 4),
                "streams": ", ".join(
                    f"{k} v{s.version}{' PARTIAL' if s.partial else ''}"
                    for k, s in _streams.items()
                ),
            }
        )
        _integrity += [
            {"trial": _trial.number, **r}
            for r in compiler.integrity_rows(session, _trial, _data, [])
        ]
    mo.vstack(
        [
            mo.ui.table(_rows, selection=None, label="Trials"),
            mo.ui.table(_integrity, selection=None, label="Trial LOG output index"),
            mo.md("\n".join(f"- {w}" for w in input_warnings) or "No input warnings."),
        ]
    )
    return


@app.cell(hide_code=True)
def settings_header(mo):
    mo.md("""
    ## Pre-processing decisions

    These controls feed every step below and the final compile. Defaults come from rig
    data (2026-10-30). The camera latency window (exposure start to host receipt) must
    be measured on the rig; leave it off to keep camera OneBox times unresolved.
    """)
    return


@app.cell(hide_code=True)
def settings_controls(Settings, mo):
    _d = Settings()
    controls = mo.ui.dictionary(
        {
            "smooth_ms": mo.ui.number(
                0.1, 20, step=0.1, value=_d.smooth_s * 1e3, label="Box smoothing (ms)"
            ),
            "low_fraction": mo.ui.slider(
                0.05,
                0.5,
                step=0.01,
                value=_d.low_fraction,
                label="Schmitt low fraction",
            ),
            "high_fraction": mo.ui.slider(
                0.5,
                0.95,
                step=0.01,
                value=_d.high_fraction,
                label="Schmitt high fraction",
            ),
            "window_tolerance_s": mo.ui.number(
                0.001,
                5,
                step=0.001,
                value=_d.window_tolerance_s,
                label="Trial window tolerance (s)",
            ),
            "photodiode_tolerance": mo.ui.slider(
                0.1,
                0.5,
                step=0.05,
                value=_d.photodiode_tolerance,
                label="Photodiode tolerance (x interval)",
            ),
            "use_latency": mo.ui.checkbox(
                value=False, label="Use camera latency window"
            ),
            "latency_min_ms": mo.ui.number(
                -50, 500, step=0.5, value=10, label="Latency min (ms)"
            ),
            "latency_max_ms": mo.ui.number(
                -50, 500, step=0.5, value=30, label="Latency max (ms)"
            ),
            "margin_ms": mo.ui.number(
                0,
                20,
                step=0.5,
                value=_d.camera_min_margin_s * 1e3,
                label="Runner-up margin (ms)",
            ),
            "probe_sync": mo.ui.checkbox(
                value=_d.probe_sync, label="Probe SY map (reads each imec file)"
            ),
        }
    )
    controls
    return (controls,)


@app.cell(hide_code=True)
def build_settings(Settings, controls):
    _v = controls.value
    settings = Settings(
        smooth_s=_v["smooth_ms"] / 1e3,
        low_fraction=_v["low_fraction"],
        high_fraction=_v["high_fraction"],
        window_tolerance_s=_v["window_tolerance_s"],
        photodiode_tolerance=_v["photodiode_tolerance"],
        camera_latency_s=(_v["latency_min_ms"] / 1e3, _v["latency_max_ms"] / 1e3)
        if _v["use_latency"]
        else None,
        camera_min_margin_s=_v["margin_ms"] / 1e3,
        probe_sync=_v["probe_sync"],
    )
    return (settings,)


@app.cell(hide_code=True)
def onebox_header(mo):
    mo.md("""
    ## OneBox recording and pulse map

    Pulse roles come from the session's recorded `SESSION_CONFIG.spikeglx.pulse_channels`
    (E12). Only Trial state, photodiode and cameras with frame logs are read; an absent
    `bit` means an analog channel.
    """)
    return


@app.cell(hide_code=True)
def open_recording(mo, session, sync, trial_data):
    onebox_warnings = []
    _cameras = {r for _, d in trial_data for r in d.cameras}
    onebox = sync.open_onebox(session, _cameras, onebox_warnings)
    mo.stop(
        onebox is None,
        mo.md("No usable OneBox recording: " + "; ".join(onebox_warnings)),
    )
    with mo.status.spinner(title="Reading OneBox channels..."):
        signals = sync.read_signals(onebox)
    _rows = [
        {
            "role": r,
            "channel": int(m.get("channel_index", 0)),
            "bit": m.get("bit", "analog"),
            "file column": onebox.columns[r],
        }
        for r, m in onebox.roles.items()
    ]
    if sync.SY in onebox.columns:
        _rows.append(
            {
                "role": "sy",
                "channel": "SY word",
                "bit": "auto (6)",
                "file column": onebox.columns[sync.SY],
            }
        )
    mo.vstack(
        [
            mo.md(
                f"`{onebox.path.name}`: {onebox.rate_hz:g} Hz, "
                f"{next(iter(signals.values())).size / onebox.rate_hz:.1f} s, "
                f"syncSourceIdx={onebox.meta.get('syncSourceIdx')}"
            ),
            mo.ui.table(_rows, selection=None),
        ]
    )
    return onebox, signals


@app.cell(hide_code=True)
def edges_header(mo):
    mo.md("""
    ## Detect pulse edges

    Analog roles: box smoothing, a two-level fit, then a Schmitt trigger between the
    low/high fractions. Check that each role's edge count and intervals make sense:
    camera pulses at the trigger rate, the photodiode at the marker rate, two Trial-state
    edges per trial. Outlier intervals point to missed pulses or noise.
    """)
    return


@app.cell(hide_code=True)
def detect(mo, np, onebox, settings, signals, sync):
    edges = sync.detect_edges(onebox, signals, settings)
    _rows = []
    for _role, _e in edges.items():
        _dt = np.diff(_e.rises) / onebox.rate_hz * 1e3
        _median = float(np.median(_dt)) if _dt.size else float("nan")
        _rows.append(
            {
                "role": _role,
                "rises": _e.rises.size,
                "falls": _e.falls.size,
                "low level": round(_e.low, 1),
                "high level": round(_e.high, 1),
                "thresholds": "digital bit"
                if _role == sync.SY or "bit" in onebox.roles.get(_role, {})
                else f"{_e.lower_threshold:.0f} / {_e.upper_threshold:.0f}",
                "median interval (ms)": round(_median, 3),
                "min / max (ms)": f"{_dt.min():.3f} / {_dt.max():.3f}"
                if _dt.size
                else "",
                "intervals off median >20%": int(
                    np.count_nonzero(np.abs(_dt - _median) > 0.2 * _median)
                )
                if _dt.size
                else 0,
            }
        )
    mo.ui.table(_rows, selection=None)
    return (edges,)


@app.cell(hide_code=True)
def edge_plot_controls(edges, mo):
    plot_role = mo.ui.dropdown(
        options=list(edges), value=next(iter(edges)), label="Role"
    )
    plot_start = mo.ui.number(0, 1e6, step=0.1, value=1.6, label="Start (s)")
    plot_duration = mo.ui.number(0.01, 10, step=0.01, value=0.5, label="Duration (s)")
    mo.hstack([plot_role, plot_start, plot_duration], justify="start")
    return plot_duration, plot_role, plot_start


@app.cell(hide_code=True)
def edge_plot(
    edges,
    figure,
    go,
    mo,
    np,
    onebox,
    plot_duration,
    plot_role,
    plot_start,
    signals,
    sync,
):
    _role, _rate = plot_role.value, onebox.rate_hz
    _e = edges[_role]
    _lo = max(0, int(plot_start.value * _rate))
    _hi = min(signals[_role].size, _lo + int(plot_duration.value * _rate))
    _raw = signals[_role][_lo:_hi].astype(np.float64)
    _t = np.arange(_lo, _hi) / _rate
    _traces = [go.Scattergl(x=_t, y=_raw, mode="lines", name="raw")]
    if _role != sync.SY and "bit" not in onebox.roles.get(_role, {}):
        _w = _e.smooth_samples
        _s = np.convolve(_raw, np.ones(_w) / _w, mode="same") if _w > 1 else _raw
        _traces += [
            go.Scattergl(x=_t, y=_s, mode="lines", name=f"smoothed ({_w} samples)"),
            go.Scatter(
                x=[_t[0], _t[-1]],
                y=[_e.upper_threshold] * 2,
                mode="lines",
                name="upper threshold",
                line=dict(dash="dash"),
            ),
            go.Scatter(
                x=[_t[0], _t[-1]],
                y=[_e.lower_threshold] * 2,
                mode="lines",
                name="lower threshold",
                line=dict(dash="dash"),
            ),
        ]
    _y = float(_raw.max()) if _raw.size else 1.0
    for _name, _idx, _level in (("rise", _e.rises, _y), ("fall", _e.falls, 0.0)):
        _sel = _idx[(_idx >= _lo) & (_idx < _hi)] / _rate
        _traces.append(
            go.Scatter(x=_sel, y=np.full(_sel.size, _level), mode="markers", name=_name)
        )
    mo.ui.plotly(
        figure(
            _traces,
            f"{_role}: raw signal, thresholds and edges",
            "OneBox time (s)",
            "ADC counts",
        )
    )
    return


@app.cell(hide_code=True)
def interval_plot(edges, figure, mo, np, onebox, plot_role, scatter):
    _r = edges[plot_role.value].rises / onebox.rate_hz
    mo.stop(_r.size < 2, mo.md("Fewer than two rises."))
    mo.ui.plotly(
        figure(
            [scatter(_r[1:], np.diff(_r) * 1e3, "rise-to-rise")],
            f"{plot_role.value}: interval between rises over the recording",
            "OneBox time (s)",
            "interval (ms)",
            height=320,
        )
    )
    return


@app.cell(hide_code=True)
def windows_header(mo):
    mo.md("""
    ## Trial windows

    Each Trial-state rise pairs with the next fall. Trials are matched to windows by
    expected span within the tolerance; a trial without one unique window stays
    without OneBox times rather than shifting later trials.
    """)
    return


@app.cell(hide_code=True)
def windows(edges, mo, onebox, session, settings, spans, sync):
    window_warnings = []
    pulses = sync.to_pulses(onebox, edges)
    sync.assign_windows(
        pulses,
        spans,
        [t.number for t in session.trials],
        settings.window_tolerance_s,
        window_warnings,
    )
    _assigned = {w: n for n, w in pulses.trial_windows.items()}
    _rows = [
        {
            "window": i,
            "start (s)": round(a, 5),
            "stop (s)": round(b, 5),
            "span (s)": round(b - a, 5),
            "trial": _assigned.get(i, ""),
            "span - expected (ms)": round(((b - a) - spans[_assigned[i]]) * 1e3, 3)
            if i in _assigned
            else "",
        }
        for i, (a, b) in enumerate(pulses.windows)
    ]
    mo.vstack(
        [
            mo.ui.table(_rows, selection=None),
            mo.md(
                "\n".join(f"- {w}" for w in window_warnings)
                or "Every trial has a window."
            ),
        ]
    )
    return (pulses,)


@app.cell(hide_code=True)
def anchor_header(mo):
    mo.md("""
    ## Host-to-OneBox anchor

    Each Trial-state edge happened between its command dispatch and acknowledgement
    (camera completion lines). Intersecting all edges bounds the host-to-OneBox offset;
    its half-width limits how well camera latency candidates can be told apart.
    """)
    return


@app.cell(hide_code=True)
def anchor_cell(apply, mo, pulses, trial_data):
    _datas = [d for _, d in trial_data]
    anchor = apply.trial_anchor(pulses, _datas)
    mo.md(
        "No anchor: no camera completion pulses or empty intersection."
        if anchor is None
        else f"Slope {anchor.slope:.9f} (OneBox s per host s); offset interval "
        f"[{anchor.low:.6f}, {anchor.high:.6f}] s; uncertainty ±{anchor.uncertainty_s * 1e3:.2f} ms."
    )
    return (anchor,)


@app.cell(hide_code=True)
def camera_header(mo):
    mo.md("""
    ## Camera frame/pulse correspondence (A09)

    Native exposure timestamps place every frame relative to the first, including
    missed triggers. Each candidate pulse offset implies a host latency; only one
    candidate inside the latency window, with the runner-up beyond the margin, is
    accepted (status `inferred`). Pick the window from a rig measurement, not from
    this table.
    """)
    return


@app.cell(hide_code=True)
def cameras(anchor, apply, mo, pulses, settings, trial_data):
    _datas = [d for _, d in trial_data]
    mo.stop(not any(d.cameras for d in _datas), mo.md("No camera frame logs."))
    apply.align_cameras(pulses, _datas, anchor, settings)
    _window = settings.camera_latency_s
    _rows, _seen = [], set()
    for _d in _datas:
        for _role, _fit in _d.camera_fits.items():
            if (_role, _fit["scope"]) in _seen:
                continue
            _seen.add((_role, _fit["scope"]))
            for _c in _fit["candidates"]:
                _rows.append(
                    {
                        "camera": _role,
                        "generation": _fit["scope"][:8],
                        "status": _fit["status"],
                        "pulse offset": _c["pulse_offset"],
                        "median latency (ms)": _c["median_latency_ms"],
                        "chosen": _c["pulse_offset"] == _fit["pulse_offset"],
                        "in window": ""
                        if _window is None
                        else _window[0] * 1e3
                        <= _c["median_latency_ms"]
                        <= _window[1] * 1e3,
                    }
                )
    _summary = [
        {
            "trial": d.number,
            "camera": r,
            **{k: f[k] for k in ("status", "pulse_offset", "margin_ms", "residual_ms")},
        }
        for d in _datas
        for r, f in d.camera_fits.items()
    ]
    camera_done = True
    mo.vstack(
        [
            mo.ui.table(_summary, selection=None, label="Per trial"),
            mo.ui.table(
                _rows, selection=None, label="Candidates (latency -200..500 ms)"
            ),
        ]
    )
    return (camera_done,)


@app.cell(hide_code=True)
def camera_plot(camera_done, figure, mo, np, scatter, trial_data):
    _traces = []
    for _t, _d in trial_data:
        for _role, _s in _d.cameras.items():
            _c = _s.tables["frames"]["camera_timestamp_ns"]
            _ok = _c != np.iinfo(np.int64).min
            _host = _s.tables["frames"]["host_receipt_ns"][_ok]
            _traces.append(
                scatter(
                    (_host[1:] - _host[0]) / 1e9,
                    np.diff(_c[_ok]) / 1e6,
                    f"trial {_t.number} {_role}",
                )
            )
    mo.stop(not camera_done or not _traces, None)
    mo.ui.plotly(
        figure(
            _traces,
            "Camera exposure interval (doubled intervals = missed triggers)",
            "host time from trial's first frame (s)",
            "interval (ms)",
            height=320,
        )
    )
    return


@app.cell(hide_code=True)
def photodiode_header(mo):
    mo.md("""
    ## Photodiode matches (V22)

    Marker level changes on the photodiode output are matched to measured transitions,
    seeded after the renderer's start-up queue. Residuals are each match minus a
    straight host-to-OneBox line: steps mark held frames or display latency changes;
    unmatched changes stay unresolved.
    """)
    return


@app.cell(hide_code=True)
def photodiode(apply, figure, mo, np, pulses, scatter, settings, trial_data):
    _rows, _traces = [], []
    for _t, _d in trial_data:
        if _d.stimulus is None:
            continue
        apply.align_stimulus(pulses, _d, settings.photodiode_tolerance)
        _rows.append({"trial": _t.number, **_d.photodiode})
        _g = _d.stimulus.tables["render_groups"]
        _ok = ~np.isnan(_g["time_obx_s"])
        if _ok.sum() > 2:
            _x = (
                _g["evaluation_host_ns"][_ok] - _g["evaluation_host_ns"][_ok][0]
            ) / 1e9
            _y = _g["time_obx_s"][_ok]
            _line = np.polyfit(_x, _y, 1)
            _traces.append(
                scatter(
                    _y, (_y - np.polyval(_line, _x)) * 1e3, f"trial {_t.number} matched"
                )
            )
            _miss = (
                _g["evaluation_host_ns"][~_ok] - _g["evaluation_host_ns"][_ok][0]
            ) / 1e9
            _traces.append(
                scatter(
                    np.polyval(_line, _miss),
                    np.zeros(_miss.size),
                    f"trial {_t.number} unmatched",
                    marker=dict(symbol="x", size=8),
                )
            )
    mo.stop(not _rows, mo.md("No stimulus evidence."))
    mo.vstack(
        [
            mo.ui.table(_rows, selection=None),
            mo.ui.plotly(
                figure(
                    _traces,
                    "Photodiode match residual vs host line",
                    "OneBox time (s)",
                    "residual (ms)",
                    height=360,
                )
            )
            if _traces
            else mo.md("No matches."),
        ]
    )
    return


@app.cell(hide_code=True)
def probe_header(mo):
    mo.md("""
    ## Probe SY map

    When OneBox and a probe share the SY wave (`syncSourceIdx`), their 1 s edges give
    a linear OneBox-to-probe map. Reading each imec file takes about 45 s per 40 GB.
    """)
    return


@app.cell(hide_code=True)
def probe_button(mo, settings):
    run_probes = mo.ui.run_button(
        label="Read probe SY", disabled=not settings.probe_sync
    )
    run_probes
    return (run_probes,)


@app.cell(hide_code=True)
def probes(figure, mo, np, onebox, pulses, run_probes, scatter, session, sync):
    mo.stop(not run_probes.value, mo.md("Press **Read probe SY** to fit probe maps."))
    probe_warnings = []
    with mo.status.spinner(title="Reading imec SY channels..."):
        sync.probe_maps(session, onebox.run_name, pulses, probe_warnings)
    _traces = []
    for _p in pulses.probes:
        _m = _p["map"]
        if _m.get("status") == "fitted":
            _pred = _m["slope"] * pulses.sy_rises_s + _m["intercept_s"]
            _rises = _p["sy_rises_s"]
            _j = np.clip(np.searchsorted(_rises, _pred), 1, _rises.size - 1)
            _near = np.where(
                np.abs(_rises[_j - 1] - _pred) < np.abs(_rises[_j] - _pred), _j - 1, _j
            )
            _res = (_rises[_near] - _pred) * 1e3
            _keep = np.abs(_res) < 250
            _traces.append(
                scatter(pulses.sy_rises_s[_keep], _res[_keep], _p["path"].name)
            )
    mo.vstack(
        [
            mo.ui.table(
                [{"probe": p["path"].name, **p["map"]} for p in pulses.probes],
                selection=None,
            ),
            mo.md("\n".join(f"- {w}" for w in probe_warnings) or ""),
            mo.ui.plotly(
                figure(
                    _traces,
                    "Probe SY residual",
                    "OneBox time (s)",
                    "residual (ms)",
                    height=300,
                )
            )
            if _traces
            else mo.md(""),
        ]
    )
    return


@app.cell(hide_code=True)
def finish_header(mo):
    mo.md("""
    ## Save or compile

    Save these decisions as JSON (`python -m cephvr.analysis.session_compiler <folder>
    --settings <file>`), or compile this session now. The HDF5 records the settings it
    used under `metadata/settings`.
    """)
    return


@app.cell(hide_code=True)
def finish_controls(mo, session):
    settings_file = mo.ui.text(
        value=str(session.directory / "compile_settings.json"),
        label="Settings file",
        full_width=True,
    )
    overwrite = mo.ui.checkbox(value=False, label="Overwrite existing HDF5")
    save_button = mo.ui.run_button(label="Save settings")
    compile_button = mo.ui.run_button(label="Compile session")
    mo.vstack(
        [
            settings_file,
            mo.hstack([save_button, overwrite, compile_button], justify="start"),
        ]
    )
    return compile_button, overwrite, save_button, settings_file


@app.cell(hide_code=True)
def save_settings(Path, json, mo, save_button, settings, settings_file):
    mo.stop(not save_button.value)
    settings.save(Path(settings_file.value))
    mo.md(
        f"Saved `{settings_file.value}`:\n```json\n{json.dumps(settings.decisions(), indent=1)}\n```"
    )
    return


@app.cell(hide_code=True)
def compile_now(compile_button, compiler, mo, overwrite, session, settings):
    mo.stop(not compile_button.value)
    from dataclasses import replace

    with mo.status.spinner(title="Compiling..."):
        _report = compiler.compile_session(
            session.directory, replace(settings, overwrite=overwrite.value)
        )
    mo.md(
        f"**{_report.status}** `{_report.output}` ({_report.duration_s:.1f} s) {_report.error}\n\n"
        + "\n".join(f"- {w}" for w in _report.warnings)
    )
    return


if __name__ == "__main__":
    app.run()
