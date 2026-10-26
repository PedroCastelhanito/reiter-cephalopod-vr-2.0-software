# Native camera captions — 2026-10-26

Base revision: e6210a3d545c490e10dffa4f7b5bbd0f9a474fa9 plus concurrent working-tree edits.
Scope: G01rev336, A10 viewer ownership and A03 latest-frame semantics. No cameras,
recording, settings or running application restart. ARCH-002: remove the custom
hover strip and reuse native chrome, existing frame sizing and placement transport;
no new dependency, timer or runtime back-reference. Existing size advisories are
unchanged owners, not new enlarged modules.

Commands use `.venv/Scripts/python.exe`:
- `tools/generate_contracts.py`: 19 Protobuf sources generated successfully.
- `-m pytest tests/acquisition/test_manual_preview.py tests/platform/test_window_coordinates.py -q -m "not windows and not rig" --timeout=30`: 169 passed, 2 deselected.
- `-m pytest tests/acquisition/test_manual_preview.py::test_native_highgui_windows_read_latest_and_close_without_stopping_producer -q --tb=short --timeout=25`: 1 passed (6 existing SWIG deprecation warnings). Final test includes native setter acceptance, three independent viewers, hidden placement/reveal, caption presence, cached pan/zoom/reset, close and producer retention.
- GUI test_dashboard selection: camera_preview_slots_only_include_enabled_cameras,
  multiple_review_previews_have_independent_source_frames, review_blank_preview,
  preview_workspace_frames_shown_streams_and_timeline, preview_slot_adapts_open_source_grid,
  preview_grid_retains_pending_footprints, preview_placement: 19 passed/944 deselected,
  not-windows/not-rig, timeout30. Earlier narrower selection: 16 passed.
- Platform tests after final native setter result assertion: 20 passed/1 deselected.
- Ruff check, Win32 mypy on five changed owners: pass. Boundary checker:760 modules,
  zero violations; existing size advisories. Final format/whitespace checked separately.

Failed attempts: two restricted acquisition runs stalled after44 cases at asyncio
Proactor loop creation, socket.py accept/_fallback_socketpair; second emitted a20s
faulthandler stack. Both interrupted. Same tests passed with loopback permission.
CIM process query was denied in sandbox; no process control used through it.
Native color readback assertion failed twice with E_INVALIDARG: caption color is a
set-only DWM attribute. Corrected the test to check supported setter acceptance;
final native test passes. One edit script stopped on default Windows decoding of
test_dashboard.py; remaining changes reapplied explicitly as UTF-8. Final format
check initially found highgui CRLF normalization, subsequently formatted.

`pump_probe.py` is the retained bounded generated-image timing method.100 calls per
variant show waitKey(1) median15.9835ms versus pollKey0.0002ms. This establishes
avoidable UI-thread sleep, not complete causality for the owner's9–10fps screenshot.
Both configured session publication and viewer cap remain20Hz. Source30/60fps is
independent; no recording frame-loss conclusion follows. Native color setter success
is not a visual theme/DPI acceptance. Actual session FPS, full GUI coloring and manual
move/resize/Snap remain in the rig checklist.

References: [Windows caption attributes](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute),
[OpenCV nonblocking pump](https://github.com/opencv/opencv/issues/19410).


## Follow-up: icon removal and measured conversion cost

Owner screenshot after restart reports11.8fps for both cameras. G01rev337 removes
caption icons using per-window icon clearing plus dialog-frame icon fallback
suppression, preserving native caption/system-menu/resize styles and ownership.
Native three-viewer test passes with style, client bounds, exact visible placement,
zoom/pan/reset, close and producer-retention assertions. Full GUI appearance remains
unverified after restart; no live application or device was changed.

`pipeline_probe.py` retains a baseline copy of HEAD's preparer and compares it to
current production preparation at the recorded2456x2568 BayerRG8 Behavior and
1588x1344 Mono8 Tracking layouts.25 generated-frame samples per variant; all output
bytes equal baseline. `pipeline-result.json` contains raw stage medians. Behavior:
preparation35.4944→6.1113ms; channel order16.6486/16.7233ms; viewport0.4641/0.4664ms.
Tracking preparation3.5767→1.23ms. Initial exploratory probe independently measured
Behavior35.361→6.2349ms. These are component measurements, excluding live capture,
shared-memory transfer, GUI owner operations and compositor/recording contention.

Current optimization copies already full-range8-bit preview bytes instead of
performing uint64 scaling. Preserve SDK conversion/validation, private storage,
higher-depth rounding and recording methods. Before change, Behavior's measured
processing alone exceeds the50ms target interval; the shared UI owner also serves
Tracking, explaining a concrete shared bottleneck. No live20fps result claimed.

History:6b03c405 (Oct19) introduced the shared HighGUI/native owner to serialize
window operations;25781b95 (Oct21) introduced20Hz viewer pacing;84d0d8b6 (Oct26)
added the hover overlay now removed. Earlier Oct26 recorder-fps-fix/running.json
already records Behavior11.2306fps versus Stimulus19.8647fps; preview-native-dummy-check
records10.5766fps camera versus19.8271fps stimulus. Reopened live retest records
Behavior9.6839/Tracking9.5560fps. No retained earlier20fps camera baseline was found;
do not claim a precise regression onset or dismiss the owner's recollection.

Validation:174 local preview/platform cases pass (2 native deselected), plus one
native three-viewer check;6 SWIG deprecation warnings only. Owning GUI tracking-frame
integration passes1. Pixel tests compare identity Mono8/BayerRG8/RGB8,8→16 and12→8
against the original full-range arithmetic and prove private source ownership.
Ruff check/format4 files, Win32mypy2 sources, boundaries760/zero and whitespace pass.
Existing boundary size advisories unchanged. ARCH-002: one branch in existing preview
preparation and existing caption helper; no dependency, thread or new backend policy.
