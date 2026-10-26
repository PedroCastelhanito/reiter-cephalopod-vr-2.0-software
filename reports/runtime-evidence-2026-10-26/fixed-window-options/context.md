# Fixed window options evidence

2026-10-26, Asia/Tokyo. Working tree based on
f82be21f28d3c1141adeabe2558c29808062727a, including prior Amber/trial-width and
concurrent Motion source changes. No live GUI restart or devices.

Python: repository .venv/Scripts/python.exe; QT_QPA_PLATFORM=offscreen.
Behavior command: `python -m pytest tests/gui/test_dashboard.py -q -k
'review_controls or retro_family_switch or review_appearance_switch or
phosphor_popups or trial_preview_is_read_only or devices_side_rail or
all_pages_share_fitted or startup_splash'
--basetemp=.pytest_tmp_fixed_window_options_final`.
Raw final output is pytest.txt.
Final result:18 passed,848 deselected in77.66s.

Initial same-selection attempt:16 passed,2 failed,848 deselected in75.07s.
Removed navigation parameter was still referenced at the end of its test; corrected.
The preview assertion compared geometry-changing style switches, confirmed by
isolated failing preview run; use direct test-only film visibility changes to
check projected-pixel exclusion under one fixed style. Preserve pixel equality,
resource cleanup, control authority, saved-draft and navigation assertions.

Static checks: Ruff GUI source and owning test check; format-check6 changed files;
Win32 mypy appearance.py, window.py, retro_overlay.py, review.py, splash.py;
backend boundaries758 modules/zero violations (existing size advisories);
git diff --check. Initial Ruff found the removed test parameter; corrected.
Source search finds no refresh-band timer/state/painting or removed menu/preference
implementation; obsolete keys appear only in regression tests that verify ignoring
them. Native/DPI/hardware and running-app appearance are outside these results.

Visual QA method: QApplication/apply_theme, ManagedDashboardWindow(sample=True),
isolated render.ini with saved Amber and obsolete sidebar/CRT=False/band=True,
resize1280×900, show/process events and grab. managed-amber.png visually inspected;
render.json records menus=[Style], the three style choices, CRT visible and both
sidebar groups visible. Sample menu omits runtime Control wiring because no bridge
is connected. No real settings were changed. A read-only process-provenance query
via CIM was unavailable under sandbox permissions; no runtime process state changed.
