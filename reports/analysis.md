# Analysis status

Current report for offline analysis software under [ARCH-001](../architecture.md#arch-001).
Only the [AN01](../docs/architecture/analysis.md#an01) session compiler is authorized;
V13 replay/export and sparse-noise regeneration stay deferred. Outstanding rig checks
live in the [rig checklist](rig-verification.md#session-compiler-timing).

## Session compiler — 2026-10-30

Task `session-compiler`. Package `cephvr.analysis.session_compiler`, with the optional
`analysis` extra (h5py, marimo, numpy, plotly). It provides:

- a library;
- the CLI `python -m cephvr.analysis.session_compiler <folder> [--settings file.json]`;
- the marimo batch compile notebook `notebook.py`;
- the marimo pre-processing inspection notebook `inspection.py`, the 2.0 counterpart of 1.0's `spikeglx_sync.py`. Run it with `marimo edit -m cephvr.analysis.session_compiler.inspection`.

The inspection notebook works through one session in order:

1. inputs and integrity;
2. pulse map;
3. edge detection, with thresholds, a raw/smoothed trace view and interval-over-time plots;
4. Trial-state windows;
5. the host anchor;
6. camera offset candidates and exposure intervals;
7. photodiode residuals;
8. the probe SY map.

Its controls set `Settings`; it can save them as JSON or compile the session with them, and every HDF5 stores the values used under `metadata/settings`.

### CephVR1.0 audit (what could not be reused)

The 1.0 compiler (`reiter-cephalopod-vr-software/analysis/data_processing/session_compiler`)
cannot read 2.0 sessions. These were rewritten:

- **Trial discovery:** the 1.0 `NNNN` log regex finds no 2.0 trial.
- **Input formats:** 1.0 reads pandas CSVs. 2.0 writes JSONL headers, rows and a completion line.
- **Time base:** 1.0 is anchored on wall-clock VR, with wall→OneBox fallback fits. 2.0 uses one host `perf_counter_ns` domain, and SYS-004 rejects those fits.
- **OneBox channels:** 1.0 hard-codes them (gate/flip/photodiode/behavior/tracking). 2.0 uses the session's recorded `pulse_channels`: trial_state/photodiode/behavioral/tracking/eye, with no flip input.
- **Camera alignment:** 1.0 aligns per trial and assumes the first pulse is the first frame. A09 rev19 continuous capture rules that out.
- **Photodiode:** 1.0 aligns on the photodiode's first tag. 2.0 uses V22 marker sequences.

Concepts kept from 1.0:
- atomic `.partial` write
- per-session reports and the process pool
- int64 fill sentinels and NaN rules
- unit/clock attributes
- timing status codes
- virtual session views
- the 1.0 window-matching uniqueness rule

Prior findings: [post hoc alignment review](runtime.md#post-hoc-alignment-compatibility-review).

### Implementation notes

- The compiler reads files by schema field names and does not import runtime packages. Generated protobuf modules are not needed.
- Supported versions:
  - camera frame logs v5/v6
  - stimulus evidence format 6
  - tracking v3
- Unsupported versions are skipped with a warning.
- Only compact stimulus tables are stored. The 300 MB per-trial evidence files are streamed line by line.
- Edges: 1 ms box smoothing, then two-level Schmitt thresholds. Rig photodiode data carries projector sub-frame ripple, which a plain midpoint threshold turned into about 1.8 M false edges.
- Photodiode: the host→OneBox offset is seeded by in-order pairing after the renderer's start-up swap queue settles. The first frames' swaps return about 10 ms apart, faster than vsync. The match then runs on a running linear fit.
- Camera: one integer pulse offset per capture generation. Each frame's step is its rounded native exposure interval, so a missed trigger counts as two steps.
  - Rig intervals are quantized at 33.33/33.42 ms, because the MCU runs at about 29.978 Hz. An earlier division of cumulative time by the median interval drifted into false gaps. That was fixed on 2026-10-30, and no missed triggers are seen in the real sessions.
  - With the fix, one camera-clock→pulse fit spans both SP0005-124641 trials at 0.048 ms RMS.
  - The offset is picked only by a supplied latency window (`--camera-latency-ms`) against the Trial-state ON/OFF dispatch/ACK anchor, accepted with a 2 ms margin (A09 rev19).
  - Without a latency window, camera rows stay unresolved, and the candidate table is stored.
- Interrupted trials: the Trial-state span comes from the camera completion ON/OFF dispatch times, because `trial_finished` follows the cutoff.
- ARCH-002: the library modules are all under 280 lines, with no boundary violations or size warnings.
  - Cohesion exception: `inspection.py` (819 lines) is one marimo app of independent cells that only call library steps, like 1.0's 1473-line notebook. The library keeps no notebook code.
- Discovery, probe lookup and provenance walk with `os.walk` and stop at each session. They inventory only `protocol-data` plus native SpikeGLX `.bin`/`.meta` files. A Kilosort output tree under `spikeglx-data` exceeded MAX_PATH with `rglob`.

### Validation

- **Commands and environment:**
  - Local commands: `pytest tests/analysis` (4 passed: aligned round trip with a missed trigger, quantized camera intervals, photodiode ripple, probe SY and a tracking record; unresolved camera without a latency window; unpaired session; truncated JSONL), `ruff check`, `ruff format --check`, win32 `mypy` (mypy 2.3.1 in a scratch target), `tools/check_backend_boundaries.py` (801 modules, 0 violations), `git diff --check`, `marimo check` on both notebooks.
  - The inspection notebook ran headless on SP0005-124641 (35 cells, no errors; values match the compiler) and was viewed through `marimo run`.
  - Environment: conda `CephVR` (Python 3.11.15, numpy 1.26.4, h5py 3.16.0, ruff 0.15.18 instead of the pinned 0.16.9).
  - `python -m build` was not run: `build`/`grpc_tools` are not installed.
- **Real sessions:** all six `F:\cephvr-data` sessions were compiled read-only through scratch directory junctions. Their SpikeGLX runs were still outside the sessions. [Summary](analysis-evidence-2026-10-30/real-sessions/summary.json).
  - All parsed counts match the trial LOG output index, and no stream is partial.
  - Trial-state windows were found for every trial, including SP0004's interrupted trial after the span fix.
  - Photodiode level changes matched to measured transitions:
    - SP0005: 99.9 %
    - SP0003-123824: 99.9 %
    - SP0003-145623: 98.8 % and 99.96 %
    - SP0004: 99.9 %
  - OneBox→imec0 SY maps:
    - SP0004 and SP0005: ≤0.05 ms RMS over 133–1804 edge pairs.
    - SP0003: no shared SY (`syncSourceIdx=0`), which is reported. This is a new finding for `pilot-shared-sync-verification`: shared SY is present from SP0004 (2026-10-22).
  - Compile time: 7–103 s per session, including a sequential imec read of about 41.7 GB in about 45 s.

### Unresolved findings and limits

- **Camera timing:** camera OneBox times stay unresolved in every real session.
  - The Trial-state anchor is ±14.9 ms; candidate latencies on SP0005-124641 are −15, 18 and 51 ms.
  - A measured latency window is needed (rig checklist), and an independent anchor is still needed to confirm it.
- **Photodiode limits:**
  - Matches measure display transitions under the stated detector thresholds; rising/falling delays and optical simultaneity across outputs are unverified.
  - Sessions with more than one photodiode patch stay unresolved by design.
- **Untested paths:**
  - Tracking records are covered only by a synthetic fixture (Tracking is paused; there are no real files).
  - Digital-bit pulse roles are untested on rig data.
- **Not yet run on the pinned stack:** packaging with the pinned numpy 2.4.4.
