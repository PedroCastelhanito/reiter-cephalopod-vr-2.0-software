# Dashboard spacing and disabled fills — 2026-10-26

Source: current uncommitted workspace; no isolated revision attribution.
Method: offscreen PyQt6 QApplication with the standard application stylesheet,
sample DashboardWindow, Amber appearance,1920x980 and200ms event settling.
[Dashboard render](dashboard.png) visually inspected: aligned section edges,
compact group spacing, readable Browse control and single-line saving labels.
An initial probe omitted the application stylesheet and clipped Browse; corrected
setup gives40px actual versus39px hinted height. This was a probe setup limitation.

Separate Qt pixel sampling of primary/danger/compact/compact-stop/icon/preview-choice
buttons found enabled amber #443a2c or red #49332e and disabled #2c2b27 in all six.
No live app, device or rig acceptance is implied.

Checks: pytest tests/gui/test_dashboard.py -q -k
"configuration_groups_stay_unfilled or recording_checks_stay_next_to_labels or
amber_palette or amber_disabled_fields":6 passed/957 deselected. Ruff check/format
and Win32 mypy cover theme.py, dashboard.py and recordings.py; owning layout test
expectation updated. Boundaries760 modules/zero violations. Initial format check
requested formatting of the modified test expression; formatted before final check.
