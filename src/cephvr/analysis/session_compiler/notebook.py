"""Marimo front end (AN01): ``marimo edit -m cephvr.analysis.session_compiler.notebook``.

Requires the ``analysis`` extra. It only calls the library API.
"""

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    from cephvr.analysis.session_compiler import (
        Settings,
        compile_sessions,
        discover_sessions,
    )

    return Settings, compile_sessions, discover_sessions, mo


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # CephVR2.0 session compiler

    Compile one session, or every session below a folder, into `<session>/<session>.h5`.
    SpikeGLX runs must be inside each session's `spikeglx-data` folder.
    """)
    return


@app.cell
def _():
    SESSION_PATH = r""
    OVERWRITE = False
    WORKERS = 2
    PROBE_SYNC = True
    # Measured camera exposure->host receipt latency window in ms, e.g. (10, 30).
    # None leaves camera OneBox times unresolved (A09).
    CAMERA_LATENCY_MS = None
    return CAMERA_LATENCY_MS, OVERWRITE, PROBE_SYNC, SESSION_PATH, WORKERS


@app.cell(hide_code=True)
def _(SESSION_PATH, mo):
    from pathlib import Path

    def pick_folder() -> str:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return filedialog.askdirectory(title="Session folder or a parent") or ""
        finally:
            root.destroy()

    selected = SESSION_PATH.strip() or pick_folder()
    mo.stop(not selected or not Path(selected).is_dir(), mo.md("Choose a folder."))
    return Path, selected


@app.cell(hide_code=True)
def _(Path, discover_sessions, mo, selected):
    sessions = discover_sessions(Path(selected))
    mo.stop(not sessions, mo.md("No sessions found."))
    picker = mo.ui.multiselect(
        options={str(s): s for s in sessions},
        value=[str(s) for s in sessions],
        label="Sessions to compile",
        full_width=True,
    )
    run = mo.ui.run_button(label="Compile")
    mo.vstack([picker, run])
    return picker, run


@app.cell(hide_code=True)
def _(
    CAMERA_LATENCY_MS,
    OVERWRITE,
    PROBE_SYNC,
    Settings,
    WORKERS,
    compile_sessions,
    mo,
    picker,
    run,
):
    mo.stop(not run.value or not picker.value, mo.md("Select sessions, then Compile."))
    latency = CAMERA_LATENCY_MS
    settings = Settings(
        overwrite=OVERWRITE,
        probe_sync=PROBE_SYNC,
        camera_latency_s=(latency[0] / 1e3, latency[1] / 1e3) if latency else None,
    )
    reports = compile_sessions(list(picker.value), settings, max_workers=WORKERS)
    mo.md(
        "\n".join(
            f"- **{r.name}**: {r.status} ({r.duration_s:.1f} s) {r.error}"
            + "".join(f"\n    - {w}" for w in r.warnings)
            for r in reports
        )
    )
    return (reports,)


@app.cell(hide_code=True)
def _(mo, reports):
    import h5py

    outputs = [r.output for r in reports if r.status in ("written", "skipped_exists")]
    mo.stop(not outputs, mo.md("No compiled files."))

    def tree(node):
        return {
            name: tree(child)
            if isinstance(child, h5py.Group)
            else f"{child.shape} {child.dtype}"
            for name, child in node.items()
        }

    with h5py.File(outputs[0], "r") as h5:
        inventory = {"attributes": {k: str(v) for k, v in h5.attrs.items()}, **tree(h5)}
    mo.tree(inventory, label=outputs[0])
    return


if __name__ == "__main__":
    app.run()
