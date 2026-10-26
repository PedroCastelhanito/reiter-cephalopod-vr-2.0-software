# Video preview card — 2026-10-26

Working tree based on f82be21f28d3c1141adeabe2558c29808062727a, with concurrent
changes preserved. Reuses Card for the camera host; no native viewer commands.

`.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -k 'preview_workspace_frames_shown or preview_workspace_pending_visible or video_previews_toggle or stimulus_preview_reclaims or category_preview_modes' --basetemp=.pytest_tmp_video_card3 --timeout=30`
passes23 cases in8.79s; [raw output](tests.txt). First run exposed a splitter test
starting at the new padded minimum width; adjusted it to expand before shrinking.
Second run exposed Amber's decorated caption; asserted its semantic label.
Final checks include equal card margins, heading positions, top/bottom alignment,
three styles, narrow grids, splitter resizing and pending-transition geometry.

Ruff check and format --check on previews.py/test_dashboard.py pass; Win32 mypy on
previews.py passes; backend boundaries759 modules/zero violations, existing size
advisories. Whitespace checked separately.

[Amber render](amber.png): offscreen1920x1032 DashboardWindow with ReviewControls,
pending camera/stimulus records, Advanced on. Inspected aligned Video/Stimulus
cards, contained bracketed placeholders and FPS. An initial standalone render
lacked bundled-font initialization; replaced it with this full-shell capture.
Not live camera pixels or native/DPI/full-load acceptance. Running app untouched.
