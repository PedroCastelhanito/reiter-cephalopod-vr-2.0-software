# ON/OFF only preview controls

2026-10-26 Asia/Tokyo; dirty working tree based on
f82be21f28d3c1141adeabe2558c29808062727a. Python3.11, offscreen Qt.
Supersedes the earlier four-state treatment/image in this directory.

`python -u -m pytest tests/gui/test_dashboard.py -q -x -k
'preview_controls_hide or preview_toolbar_wraps or preview_toggle_selection or
stimulus_preview_belongs or preview_selection_waits or video_previews_toggle or
advanced_projector_toggles' --basetemp=.pytest-preview-on-off`:
22 passed,861 deselected in15.61s.
Checks hide/restore for authority, participation, recording, pending request and
master-off gates; projector hide/restore, three-style ON/OFF/hover and wrapping,
independent masters and existing pre-Setup waiting cancellation.
Ruff check/format previews.py/theme.py/test_dashboard.py pass; Win32 mypy both
sources passes; backend boundaries758/zero with existing cohesion advisories.
Whitespace checks pass. No native/DPI/device execution or running-app restart.
