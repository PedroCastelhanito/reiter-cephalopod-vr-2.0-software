# Independent camera image preparation — 2026-10-26

Owner explicitly requests independent preparation with shared native operations.
A10rev73 and the preview-control contract record this split. Existing per-viewer
reader threads execute one private operation at a time: SDK preparer creation,
copy/recheck of the newest ring frame, conversion, channel ordering and viewport
resampling. Existing generator/dispatcher passes ReaderWork to the reader and
resumes only after completion. No added thread, executor, process, frame queue,
dependency or whole-runtime reference (ARCH-002). Native creation, callbacks,
geometry, presentation and closure stay on the existing shared window thread.
HighGUI remains a cohesive473-line single-view lifetime owner, below size advisory;
the small viewport owns its transform identity. SDK image failures are thrown back
into existing generator cleanup, preserving mapping/native release receipts.

Viewport snapshots isolate native input from worker image operations. Before imshow,
recheck native closure/minimization, stop, ring retirement, session-run identity and
viewport transform. Drop superseded pixels, redraw the current transform from cached
private pixels, and clear cached pixels on run change. One pending native step per
reader; source arrivals continue replacing the existing latest-frame slot. Old run
pixels cannot be presented after a detected run change. Capture/recording and20Hz
preview cadence stay unchanged. Ready is set after a valid display, or the existing
minimized first-preparation behavior; no release receipt precedes private completion.

Commands use `.venv/Scripts/python.exe`:
- `-m pytest tests/acquisition/test_manual_preview.py tests/platform/test_window_coordinates.py -q -m "not windows and not rig" --timeout=30`:181 passed,3 deselected in0.60s.
- `-m pytest tests/acquisition/test_manual_preview.py::test_native_highgui_windows_read_latest_and_close_without_stopping_producer -q --tb=short --timeout=25`:2 passed in0.85s.
- `-m ruff check src/cephvr/acquisition/preview tests/acquisition/test_manual_preview.py`:pass.
- `-m ruff format --check src/cephvr/acquisition/preview tests/acquisition/test_manual_preview.py`:5 files formatted.
- `-m mypy --platform win32 src/cephvr/acquisition/preview`:4 sources pass.
- `tools/check_backend_boundaries.py`:760 modules,zero violations; existing other-owner size advisories unchanged.
- `git diff --check`:pass.

Tests assert preparation/copy/resampling run on each reader, all native operations
stay on one distinct owner, and a blocked first-camera preparer does not prevent a
second real native window from becoming ready. Three native viewers retain shared
window-thread IDs, hidden initial placement, caption styles, cached zoom/pan/reset,
independent close and producer retention. Deterministic cases cover conversion/
render exceptions, close/stop/retirement/session change during conversion (no stale
imshow), and a native zoom during resampling (discard first image; redraw new view).
Existing release-failure test retains false closure evidence. No new test module.

Intermediate checks:24 then29 focused cases pass;179 local plus2 native pass before
adding final render-failure/viewport-invalidation coverage. Ruff initially flagged
late-bound lambda variables; replaced with an explicit partial. A documentation
script stopped at the root register's anchor-prefixed row; the matching register and
remaining contract amendment were applied afterward. No test assertion was weakened.
Six pypylon SWIG deprecation warnings accompany passing SDK/native tests.

Native tests use generated pixels/shared memory, no camera/MCU/projector devices or
recording. No live application restart, post-change camera FPS, full-load timing,
physical/mixed-DPI or long-run acceptance is claimed. See the single rig checklist.
