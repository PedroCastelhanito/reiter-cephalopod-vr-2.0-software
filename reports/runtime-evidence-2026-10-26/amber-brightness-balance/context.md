# Amber brightness balance

2026-10-26 (Asia/Tokyo), working changes based on
f82be21f28d3c1141adeabe2558c29808062727a. Prior and concurrent GUI changes preserved.
Palette-only refinement: slightly darker charcoal surfaces, softer gold/coral ink
and frames/hover fills; existing font metrics/weight and CRT opacity unchanged.

Repository Python3.11, QT_QPA_PLATFORM=offscreen:
`python -m pytest tests/gui/test_dashboard.py -q -k
'amber_palette or amber_disabled or retro_family_switch or phosphor_navigation or
phosphor_combo_popup' --basetemp=.pytest_tmp_amber_brightness_balance`:
5 passed,864 deselected in10.21s. No test changes or failures for this increment.
Ruff check/format theme.py, Win32 mypy theme.py, backend boundary check758/zero
(existing cohesion advisories), and git diff --check pass.

Render: QApplication/apply_theme, DashboardWindow(sample=True), isolated
QSettings preview.ini; select Amber without persisting, resize1280×900,
show/process events and grab dashboard.png. Visually inspected. No live GUI restart,
settings mutation, hardware operation, monitor/DPI or experiment acceptance.
