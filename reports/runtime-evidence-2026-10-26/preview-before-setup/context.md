# Preview layout before Setup — 2026-10-26

Source base: f82be21f28d3c1141adeabe2558c29808062727a plus dirty concurrent GUI
changes. Owner screenshot shows the current draft timeline and selected Advanced
views but only an empty Combined stimulus frame before Setup.

Cause: the draft, geometry, category and instrument plan already reached Monitor,
but current_epoch(None) hid every dial/map and left the shared table empty.
Use planned time0 for instrument sampling when playback time is absent; keep
elapsed time, current epoch label and timeline cursor unset. Existing feedback and
invalid geometry messages, native pixel/readiness gates and running clock remain.
ARCH-002 review reuses the cohesive timeline refresh owner with one call change;
no new state, dependency or renderer. Existing timeline size advisory remains.
G01rev316 records the requested pre-Setup presentation behavior.

Commands use repository Python3.11:

```text
python -m pytest tests/gui/test_dashboard.py -q -k "category_preview_modes_keep_camera_space or stimulus_preview_reclaims_camera_space or preview_window_supplies_current_profile or stimulus_preview_belongs_to_advanced or preview_timeline_visibility or preview_motion_reference or preview_motion_overlay_linked or drift_pairs_keep_face" --basetemp=.pytest_tmp_preview_before_setup_final --timeout=30
python -m pytest tests/gui/test_preview_timeline.py -q --basetemp=.pytest_tmp_preview_before_setup_timeline --timeout=30
```

Final results:14 passed,869 deselected in6.07s;91 timeline checks passed in1.33s.
Expanded existing owning tests cover pre-Setup/visible native states at830/1000px,
Combined shared values, Per-projector instruments, static Bottom, live-status
message retained, no elapsed/current-epoch claim, media hiding and arena map.
Existing geometry-edit, playback, linked-motion and Advanced tests pass.

Before source change both pre-Setup cases failed with empty shared samples.
The category fixture also exposed its stale camera-space assumption after recent
toolbar changes; it now declares the selected camera it intends to reserve.
The arena assertion needed the event loop to settle reparented instruments before
testing effective visibility. No production visibility gate was loosened.

Ruff check/format2 files, Win32 mypy1 source and boundaries758/zero pass; existing
unrelated size advisories remain. Whitespace passes. The persisted render script
creates a standalone real workspace without runtime/device calls. Run:

```text
python reports/runtime-evidence-2026-10-26/preview-before-setup/render.py
```

[Combined](combined.png) and [Per-projector](per-projector.png) inspected. Both
show configured instruments with elapsed=None and four active planned sources.
The first fixture omitted bundled font loading/background and produced square
glyphs; script now loads the real font and applies the window surface. Empty top
HUD/System-control space belongs to this isolated workspace fixture.
No native application restart, hardware, physical pixels or rig/DPI acceptance.
