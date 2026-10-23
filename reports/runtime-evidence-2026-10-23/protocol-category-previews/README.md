# Protocol categories and adaptive previews — 2026-10-23

Source base: `59a973ac`, concurrent dirty worktree (not an isolated commit).
Task: `protocol-category-preview-design`; user approved implementation after mockup review.
The source UI was rendered with Qt offscreen, sample canonical programs and local temporary
QSettings. No running application, settings, device or experiment session was controlled.
Screenshots show native-viewer placeholders; they do not establish rendered pixel correctness.

## Results

- Configuration/rendering:124 passed,1 deselected,3 subtests (`category-render-final-3.txt`).
- Controller admission/authenticated worker transport/communication:54 passed
  (`category-transport-last.txt`), using permission-approved local loopback fixtures.
- Broad selected Dashboard plus standalone timeline run:274 passed,13 failed
  (`category-gui-final-2.txt`). All202 selected Dashboard nodes passed. The13 timeline
  failures used missing elapsed time or a stationary reference while expecting visible
  instruments. Updated fixtures explicitly select a planned instant, move the source
  and allow queued Qt layout events to settle. No assertions were removed.
- Full standalone timeline rerun:85 passed (`category-timeline-complete.txt`).
- Final combined timeline/category/preview-preference selection after the last layout
  edits:98 passed,841 deselected (`category-final-acceptance.txt`). Includes image,
  texture and video fades, category import/undo/atomicity, arena plus overlays and
  repeated mode/ownership changes. Other focused results are overlapping coverage.
- Final category/trial-delete history regression selection also passes
  (`category-history-last.txt`); deleting the last trial preserves protocol category.
- Ruff check and format pass; Win32 mypy205 source files pass (`category-static.txt`).
- Boundary checker:755 modules,zero violations (`category-boundaries.txt`), existing
  size review advisories retained.11 generated JSON schemas checked with no drift.
- Offscreen rendering and clean process exit succeeded (`render-category.txt`).

## Methods

Repository Python: `.venv/Scripts/python.exe`; `QT_QPA_PLATFORM=offscreen` for GUI tests.
Pytest commands used `-q -m "not windows and not rig" --tb=short` and unique task-local
`--basetemp` paths. Module selections:

- `tests/visual_stimulus/test_configuration.py tests/visual_stimulus/test_rendering.py`
- `tests/controller/test_device_admission.py tests/visual_stimulus/test_transport.py tests/visual_stimulus/test_controller_communication.py`
- Broad: `tests/gui/test_dashboard.py tests/gui/test_preview_timeline.py -k "reference or preview or protocol or batch or drift_pairs or presentation_rows" --timeout=60`
- Final: same GUI modules with `-k "test_preview_timeline or category or presentation_rows or drift_pairs"`
- `.venv/Scripts/python.exe contracts/visual_stimulus/generate_schemas.py --check`
- `.venv/Scripts/python.exe tools/generate_contracts.py` regenerated19 protobuf modules
  from authoritative sources (generated source directories are ignored by Git).
- `.venv/Scripts/python.exe tools/check_backend_boundaries.py`
- `.venv/Scripts/python.exe -m mypy --platform win32 src/cephvr/gui` plus category,
  configuration, coordinator commands, native/preview/group and controller/shared placement owners.

Earlier retained failures include stale expected UI/source-schema assertions and the
corrected small-window caption clipping. One initial sandbox GUI run stalled at local
socket setup; authenticated tests subsequently ran with loopback permission. One broad
run was interrupted before reporting results and is not counted. The renderer trial
fixture was updated to implement the new layout-refresh operation. Temporary Qt-only
screenshots were reviewed; GPU fences/window placement are tested with doubles here.

## Limits

Native GLFW sharing, real camera/output frames, DPI/follow/drag/Snap, X-close/reopen,
full-load20Hz cost, optical timing and hardware cleanup remain unverified for this change.
See [the single rig checklist](../../rig-verification.md#protocol-category-previews).
No performance or rig-equivalence claim follows from these results.
