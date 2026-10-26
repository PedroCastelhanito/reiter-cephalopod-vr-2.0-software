# Trial width evidence

2026-10-26, working changes based on f82be21f28d3c1141adeabe2558c29808062727a;
concurrent Amber/Motion source edits retained.

Repository Python3.11 with QT_QPA_PLATFORM=offscreen:
`python -m pytest tests/gui/test_dashboard.py -q -k
'trial_row_actions_scroll_target_and_align_cards'
--basetemp=.pytest_tmp_trial_add_width_final`:3 passed,863 deselected,8.16s.
Initial three cases failed: Standard/Retro compared a long row's unclipped logical
width, Amber expected title case. An isolated Standard run confirmed the former.
Final expectations compare viewport-clipped row geometry and Amber uppercase.
All action, scrolling, delete-confirmation and authority assertions remain.

Render method: QApplication/apply_theme, DashboardWindow(sample=True), isolated
QSettings preview.ini, select Amber without persisting, resize1920×1032, show,
select Protocol, process events, grab editor.trial_card. trials.png inspected.
Viewport176px, logical row218px (elided to viewport), + at(0,47)176×41px.
Offscreen sample only; no live controller/device operation or restart.

Ruff check/format trial_list.py and test_dashboard.py pass; Win32 mypy trial_list.py
passes; backend boundaries758/zero with existing size warnings; diff whitespace passes.
