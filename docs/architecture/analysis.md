# Analysis

[Overview and decision register](../../architecture.md) ·
[System contracts](system-contracts.md)

Offline analysis software outside the experiment runtime. Only the session compiler
is authorized ([ARCH-001](../../architecture.md#arch-001)); V13 replay/export and
sparse-noise regeneration remain deferred. Implementation status and validation are in
the [analysis report](../../reports/analysis.md).

## Decisions

<a id="an01"></a>
### AN01 — Offline session compiler

**Status:** Accepted · **Revision:** 2

- **Owner and scope:** `cephvr.analysis.session_compiler` reads one recorded session
  (E04 layout) and writes `<session>/<session>.h5` atomically (temporary `.partial`,
  then rename), or under an explicit output root. It is a library, CLI and marimo
  compile and inspection notebooks run after recording; it never runs inside, imports
  or controls the experiment runtime, and never modifies source files.
- **Pre-processing decisions:** pulse smoothing/thresholds, trial-window tolerance,
  photodiode tolerance and the camera latency window/margin are explicit settings,
  reviewed step by step in the inspection notebook, saved as JSON for the CLI and
  recorded in each compiled file.
- **Inputs:** `SESSION_CONFIG.json`, `SESSION_LOG.jsonl`, `SCHEMA.json`, trial
  `_LOG.json` output indexes and each indexed backend file, resolved by file name
  inside `protocol-data` (stored absolute paths are recording-host evidence only).
  SpikeGLX files come only from the session's `spikeglx-data/{run_name}_g*` folder
  (E09/E12). Readers are version-gated on each file's schema/format version, discard
  an incomplete final JSONL line, keep integers exact and mark files without a
  completion line partial.
- **Content:** per-trial camera frame logs and video maps, compact Visual Stimulus
  timing tables (render groups, per-output submissions/markers, captures, image
  selections, feedback, clipping, completion) and tracking records, plus session
  metadata and integrity checks against completion lines and LOG counts. Uniform
  words, poses and media state stay in the referenced source JSONL. Session views
  concatenate trial tables without copying.
- **Time:** every timed row keeps its exact host `perf_counter_ns` value and native
  device times. OneBox time comes only from recorded pulses under SYS-004, using the
  session's `pulse_channels`: Trial-state HIGH intervals gate camera rising edges
  after frame-to-pulse correspondence (A09); photodiode transitions match the
  recorded V22 marker levels, anchored by the first bright level after the Trial-state
  rise. Camera rows may use A09's inferred per-generation offset, labelled inferred
  with its margin. Unmatched, ambiguous or unpaired rows keep NaN OneBox
  time with status `unresolved`; no host-to-device fit, wall-clock fallback or
  interpolation between edges. Each table records a per-row timing status.
- **Probe alignment:** when the OneBox and an imec stream share the SpikeGLX SY wave
  (native metadata), store both edge sets and a per-probe OneBox-to-probe linear map
  with residuals, and derive probe time only for rows with OneBox time. Otherwise list
  the probe files unresolved. No spike or neural processing.
- **Failure:** unreadable required metadata or an unsupported version fails that
  session's compile with a report; other sessions continue. Missing, partial or
  inconsistent streams are compiled with explicit warnings and integrity flags.
  Compiled timing is analysis evidence, not rig validation; pulse wiring and optical
  timing remain in the [rig checklist](../../reports/rig-verification.md).
