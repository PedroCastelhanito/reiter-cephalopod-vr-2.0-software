# Embedded preview component comparison — 2026-10-26

Owner request: measure whether removing native preview positioning/following/resizing
cost outweighs GUI-GPU rendering/transfer cost. G01 revision335 permits this isolated
experiment; production preview ownership remains unchanged.

## Provenance and method

Initial checkout HEAD: `819f30e6e5e5bf4b840438c3ef3a7538d45ad192`, with concurrent
lifecycle work already dirty. `source-hashes.json` and `benchmark_snapshot.py` bind
the corrected measurements to source; no claim of a clean/exclusive checkout or
otherwise idle Windows machine. Normal development continued outside the probe.

Use the repository Python3.11 environment and installed Qt/OpenCV/OpenGL libraries.
The bounded tool issues no experiment, camera, projector or configuration commands.
It creates and closes only its own generated-frame preview windows/processes.

Corrected presentation files are **only** `separate-[0-2]-*.json`, with sibling
stdout/stderr `.log` and exit-code `.exit.txt`. Each mode runs in a fresh process,
with2s warmup and8s measurement. Three640x640 RGB streams change at20Hz, displayed
in the same1150x420 host layout. Movement/resizing uses the same deterministic
sinusoidal host geometry in every moving case. Actual monitor scaling must be100%.

- `off`: host geometry/layout/event-loop baseline.
- `native-fixed`: separate HighGUI process, fixed windows, no owner/follow machinery.
- `native-follow`: same separate HighGUI consumer plus production
  WindowsPreviewOwner, PreviewGeometryGuard, caption removal and positioning helpers.
  The GUI samples positions every200ms and sends small placement messages; the native
  loop targets10ms polling, including real `waitKey`, owner/geometry checks and
  size/position updates. Image presentation is independently capped at20Hz.
- `embedded`: QOpenGLWidget/QPainter RGB image drawing with private QImage copies,
  no native viewer, owner, follow, placement or geometry-command machinery.
  The reported actual GL renderer must be AMD Radeon(TM) Graphics.

Mode orders are off/fixed/follow/embedded, embedded/follow/fixed/off, then
follow/off/embedded/fixed. Each round runs stationary then moving; fixed moving
is omitted because it would no longer perform equivalent window-following work.
CPU is percentage of **one logical CPU core**, summing GUI and native child when
present. Native polling wall time includes waits; it is not CPU busy time.
`frame_callbacks`/root intervals measure GUI timer callbacks; native displayed-frame
submission cadence is separately recorded under `native_process.frame_intervals`.
OpenGL paint timings measure CPU submission, not completed GPU work.

Representative commands (run each case separately, sequentially):

```powershell
.venv/Scripts/cephvr-python.exe -m cephvr.platform.windows.python_entry tools.benchmark_preview_presentation --mode native-follow --seconds 8 --moving --output reports/runtime-evidence-2026-10-26/embedded-preview-comparison/separate-0-native-follow-True.json
.venv/Scripts/cephvr-python.exe -m cephvr.platform.windows.python_entry tools.benchmark_preview_presentation --mode embedded --seconds 8 --moving --output reports/runtime-evidence-2026-10-26/embedded-preview-comparison/separate-0-embedded-True.json
```

Readback runs use `cephvr-renderer.exe`, `--mode readback`, and the same module.
They clear/read an RGB framebuffer synchronously at20Hz on the reported RTX5060Ti.
This measures simple GPU-to-host readback, not IPC, GUI upload, full-scene rendering,
asynchronous transfer or end-to-end display latency. Do not add independently
measured times and call that an end-to-end result.

## Excluded attempts and limitations

Unprefixed numeric files are an exploratory same-process Qt/HighGUI batch. Its second
moving native run exits nonzero without stderr; no numeric exit code was preserved.
Discard that batch for the decision. The cause is unknown; the harness topology
differs from production, so this is not evidence of a production native-viewer bug.
Earlier smoke checks exposed cleanup after Qt exit; closure was moved before quit.
Separate-process smoke then exposed a managed executable base-name mismatch,
owner binding after title removal, and a GUI-message-pumping wait requirement.
The corrected harness uses the existing venv Python launcher for the HighGUI child,
binds before blanking its title, and pumps Qt events while awaiting readiness/exit.
One timed-out prototype was interrupted; it provides no measured result. Successful
corrected child shutdown requires exit0, not merely a received measurement message.

This is a component comparison, not the full managed GUI: no authenticated placement
RPCs, camera conversion/shared rings, hover captions/pan/zoom, realistic scene load,
recording, Tracking or complete Dashboard instruments. Native UI work is in a
separate process but generated frames replace capture. System compositor/driver CPU
outside the probe, GPU utilization and actual backend deadlines/loss are unmeasured.
Generated noise alternates between two frames; this is not a camera data benchmark.
The readback alternative is a simple synchronous implementation, not a selected
production transfer policy. Full-backend acceptance remains in the rig checklist.

## Owner-observed lag and presentation follow-up

During the component comparison the owner reports that embedded previews look very
laggy, affecting both images and window moving/resizing. Retain this as a usability
failure of the observed prototype; average CPU or timer cadence cannot overturn it.
Inspection finds no frame queue (each widget replaces its latest owned QImage),
but the first probe intentionally updated host geometry at20Hz along with frames.
That imposes stepped host motion and cannot establish real drag smoothness. The
alternating-noise content likewise provides no useful motion/latency reference.

`motion_snapshot.py` and `motion-source-hash.json` bind the follow-up tool revision.
`motion-[0-1]-*.json` uses a generated moving bar on a grid at20Hz, independently
updates host geometry on a16ms timer, and records per-widget frame-generation to
Qt `frameSwapped` age, unique-frame swap intervals and skipped generated sequences.
Each case uses2s warmup and6s measurement; compare native-follow and embedded both
stationary and moving, plus moving-off baseline, in reversed orders across two rounds.
The native child's displayed-frame submission timing remains separately recorded.
Qt swap signals are not physical scanout/photodiode evidence, and do not measure
camera-to-display latency. Do not merge this different workload with the earlier
noise/20Hz-geometry matrix. Process CPU sampling varies substantially across runs,
including zero-reported short-burst CPU; treat it as coarse evidence, not proof of
zero cost or a statistically established performance advantage.

Readback follow-up files `readback-[0-2]-*.json` use4s per case, with one1024x1024
RGB image or four640x640 RGB images per20Hz update. These are illustrative combined
and multi-image transfer sizes, not measured production resolution inventories.

## Current outcome

Completed/validated datasets:21 separate-process noise cases,8 moving-bar cases,
2 restricted readback cases and4 final unrestricted cases (35 result/exit pairs).
`summary.json` retains their selected measurements; every counted result has exit0.
Actual embedded renderer is AMD Radeon(TM) Graphics, readback renderer RTX5060Ti.
All recorded moving-bar embedded samples report zero skipped generated sequences.

The intended second matched moving-bar native round stops on a15s readiness timeout
(`motion-1-native-follow-False.log`); its subsequent native moving case is not run.
The restricted readback repeat `readback-1-1x1024` exits-1073741816 with empty stderr
and no result; later planned repeats are not run. Neither is silently retried or
counted as success. Following explicit tool escalation, one final native moving,
embedded moving and each readback-size case run outside the restricted environment;
all four exit0. This does not establish the cause of restricted-run failures.

| Final unrestricted6s sample | Result |
| --- | --- |
| Native following, continuous movement/resizing |10.86% of one CPU core, GUI + viewer |
| Embedded, same movement/resizing |27.39% of one CPU core |
| Embedded frame generation to Qt swap |4.10ms p95,12.05ms maximum; zero skipped sequences |
| One1024-square RGB readback |0.805ms mean,0.992ms p95 |
| Four640-square RGB readbacks |1.494ms mean,1.809ms p95 per batch |

These short/coarse CPU samples do not establish a reproducible ratio or the cost
to unrelated backends. They provide no demonstrated net advantage that would justify
accepting the owner's observed lag. Keep production native viewers; further
adoption work requires usability and matched full-load evidence under the rig list.

Validation: Ruff check/format check and Python compilation of the tool pass;
`tools/check_backend_boundaries.py` checks760 modules with zero violations and
existing size advisories on unchanged source.35 saved result/exit pairs, adapter
strings, embedded sequence counters and new documentation targets/anchors checked.
`git diff --check` passes. No production runtime suite was needed for this standalone
tool/documentation change; no full-backend slowdown or physical latency test claimed.
Final concurrent checkout HEAD is `2f3e073db9e7998ec48310315002a8140f394f21`;
source snapshots/hashes, rather than that separate lifecycle commit, bind the probes.
