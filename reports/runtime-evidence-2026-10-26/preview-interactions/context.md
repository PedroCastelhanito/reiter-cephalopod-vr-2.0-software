# Preview interaction evidence — 2026-10-26

Source base f82be21f28d3c1141adeabe2558c29808062727a plus dirty concurrent workspace.
Governing rules: G01rev331, ARCH-002, E15. Native desktop screenshots via sky;
authenticated read-only snapshot helper; normal GUI Stop now.
Generation e8aa836b-4ee7-40ee-8a0b-114f7367354b, trial started11:29:24,
stopped about12:15:32 (~46m08s). Tool approval waiting extended runtime.
Output retained in output/20261026_ephys-pilot/SP0004-112838.

Observed50/50 initial split, manual divider drag, Advanced off/on restoring split,
Combined/Per-projector, both camera viewers, Video off/on. Video reappearance
changed proportion: final code stores the manual ratio explicitly; final fix
has offscreen coverage, not another live trial. Native camera caption drag/Snap
not exercised (blank-title windows not targetable); renderer approval timed out.
Old-stop-stale-preview.png captures obsolete window-update error fixed here.
manual-split-preserved.png and video-restored.png document native layouts.
stopped.json confirms Configuration, cleanup_confirmed true, no controller errors.
Application close logs in launch.stderr.txt report process inspection WinError5
and bool_dealloc at finalization. shutdown.json records later refused connection;
processes-after.json records empty managed inventory. Exit cause remains open.
No full file decode or full-load/alternate-DPI acceptance.

Validation:
- pytest tests/gui/test_dashboard.py -q -k 'preview_workspace or preview_video or video_previews_toggle or category_preview_modes or stimulus_preview_reclaims or stale_camera_layout or camera_connect_opens_only':30 passed,907 deselected8.82s.
- pytest same module -k 'per_projector_compact_layout_preserves_plots_and_fps or stimulus_preview_reclaims_camera_space':24 passed,913 deselected1.61s.
- Ruff check/format: previews.py, managed_device_commands.py, test_dashboard.py pass.
- Win32 mypy both changed source owners passes.
- check_backend_boundaries.py760 modules,zero violations; existing size advisories.
Tests used QT_QPA_PLATFORM=offscreen and unique repository basetemps.
Initial split flag and initial visibility fixture produced failures, subsequently fixed.
Original output roots restored; concurrent tracking recording selection preserved.
