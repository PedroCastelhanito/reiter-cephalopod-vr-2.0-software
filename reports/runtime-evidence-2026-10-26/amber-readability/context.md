# Amber readability evidence

- Date: 2026-10-26 (Asia/Tokyo).
- Source: working changes based on f82be21f28d3c1141adeabe2558c29808062727a.
- Method: repository Python 3.11, `QT_QPA_PLATFORM=offscreen`, QApplication with
  `apply_theme`, `DashboardWindow(sample=True)` and isolated QSettings in this
  directory; select `amber_phosphor` without persisting, show/process events,
  resize/grab at 1920×1032 and 1280×900. No controller/device connection.
- Results: dashboard.png and dashboard-1280.png visually inspected; form/saving
  labels fit or wrap. QLineEdit font reports IBM Plex Mono, 13px, weight600,
  absolute letter spacing0.59375px (Qt rounding of0.6px).
- Scope: offscreen sample rendering only; source styling takes effect on reopen.
  Native monitor appearance, alternate DPI and experiment behavior were not tested.
- Initial command: `python -m pytest tests/gui/test_dashboard.py -q -k
  'amber_palette or amber_disabled or phosphor or retro_family_switch'
  --basetemp=.pytest_tmp_amber_readability`: 12 passed, 2 failed,849 deselected.
  Failures were former palette-specific pixel thresholds; both updated for brighter
  border/coral. No behavioral or communication assertions were removed.
- Broader attempt: 15 passed,2 failed,846 deselected; failures were the old regular
  header-weight assertion and antialiased coral marker detection. Header expects600;
  coral detection uses hue separation from amber rather than the old green cutoff.
  Isolated header attempt confirmed the former assertion failure before its update.
- Final command: `.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q
  -k 'amber or phosphor or retro_family_switch or sidebar'
  --basetemp=.pytest_tmp_amber_readability_verified`: 17 passed,848 deselected,
  32.35s. Raw output: pytest.txt. Concurrent Motion source work added cases during
  this session; its source/test/report changes were preserved.
- Static commands: `python -m ruff check` and `python -m ruff format --check` for
  theme.py, retro_overlay.py and test_dashboard.py pass; `python -m mypy --platform
  win32` for both changed GUI sources passes; `python tools/check_backend_boundaries.py`
  checks758 modules with zero violations and existing cohesion warnings;
  `git diff --check` passes.
