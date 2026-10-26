# Preview toggle jitter — 2026-10-26

Source: working tree based on f82be21f28d3c1141adeabe2558c29808062727a,
including pre-existing concurrent edits. Offscreen Qt checks, no device commands.

Expanded the existing pending/visible placement regression to a1600x850 workspace.
Before repair: Standard/Advanced changed target QRect(8,32,380,410) to
QRect(10,45,375,405); one failure and three passes. Measuring text showed the
closing hint grew the heading from25 to45 pixels. An attempted header-width-only
repair still failed and was removed. The final fix keeps eligible selectors
visible but disabled during pending work and removes that misleading hint.

Commands use `.venv/Scripts/python.exe`:

- `-m pytest tests/gui/test_dashboard.py -q -k 'preview_workspace_pending_visible_update_preserves_placement or preview_controls_hide_when_unavailable or video_previews_toggle or preview_toolbar or stimulus_preview_reclaims or category_preview_modes or preview_workspace_frames or preview_inline_controls or preview_grid_retains or stimulus_preview_belongs' --basetemp=.pytest_tmp_jitter4 --timeout=30`:38 passed in33.91s.
- Final expanded assertions: `-m pytest tests/gui/test_dashboard.py -q -k 'preview_workspace_pending_visible_update_preserves_placement or preview_controls_hide_when_unavailable or preview_toolbar_wraps' --basetemp=.pytest_tmp_jitter_final --timeout=30`:14 passed; raw output in [tests.txt](tests.txt). Geometry includes workspace, top row, timeline, toolbar, splitter, slot and target, with Standard/Amber/Retro and repeated pending transitions. Toolbar checks retain wide/narrow positions.
- `-m ruff check src/cephvr/gui/previews.py tests/gui/test_dashboard.py`:pass.
- `-m ruff format --check src/cephvr/gui/previews.py tests/gui/test_dashboard.py`:pass.
- `-m mypy --platform win32 src/cephvr/gui/previews.py`:pass.
- `tools/check_backend_boundaries.py`:759 modules, zero violations; existing size advisories retained.
- `git diff --check`:pass, existing CRLF normalization warnings only.

No live GUI restart, native camera viewer or alternate-DPI/full-load verification.
This establishes the reproduced local layout repair, not rig acceptance.
