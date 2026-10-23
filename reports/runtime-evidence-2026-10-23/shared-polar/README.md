# Shared polar table and preview layout — 2026-10-23

Source: dirty workspace based on59a973ac3ffc6fb331bbee1d93c6b283d6b90474;
concurrent GUI review changes preserved. Governing rule: [G01rev309](../../../docs/architecture/gui.md#g01).
Implementation scope/assessment: [Runtime](../../runtime.md#combined-space-and-shared-polar-table--2026-10-23).

Repository Python3.11 with QT_QPA_PLATFORM=offscreen:

```powershell
.venv/Scripts/python.exe -m pytest tests/gui/test_preview_timeline.py -q -x --basetemp=.pytest-tmp-shared-table
.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -s -x -k preview --timeout=30 --basetemp=.pytest-tmp-shared-table-dashboard
.venv/Scripts/python.exe reports/runtime-evidence-2026-10-23/shared-polar/render_layouts.py
```

Timeline91 passes; Dashboard125 passes with permitted local loopback access for Windows
asyncio. Logs are timeline-tests.log and dashboard-tests.log. Owning cases verify actual
linked-rate agreement against renderer bindings, canonical table rows/colors, static
Bottom, incompatible units, projector toggles, short/tall layout, camera collapse/restore
and initial-versus-visible native placement coordinates. No live device or trial runs.

Ruff check/format covers preview_motion_dial, preview_grouping, preview_timeline,
stimulus_preview_area, previews, preview_placement and the two owning test modules.
Win32 mypy covers those six source modules. Boundary checker:758 modules, zero
violations, existing cohesion advisories including timeline524 lines. No new dependency.

render_layouts.py captures real widgets at1500x500 Combined,1500x560 individual and
1500x438 compact individual (requested430 grows to its minimum). Captures and measured
targets are combined.png, per-projector.png, per-projector-compact.png and
layout-measurements.json. The native image frames are placeholders; these demonstrate
GUI geometry and table/plot readability only. Actual GPU shader fixture evidence remains
in the separate [GPU rig evidence](../gpu-rig-preview/README.md). Native viewer placement,
DPI, physical motion and full-load cost require the [rig checks](../../rig-verification.md#protocol-category-previews).

Historical attempts retained as raw .shared-polar-*.log files here: old four-card layout
assertions and short-window minimum were corrected for the accepted shared plot;
prospective camera placement exposed a4px splitter-handle allocation mismatch and was
fixed without relaxing exact placement assertions. One early failing-fixture run ended
with a Qt Windows access violation. Later complete suites passed. Sandbox Dashboard
attempts blocked in asyncio Windows socketpair and were interrupted before the permitted
run. These failed attempts are not successful runtime or rig evidence. The original app
and experiment state were not touched.
