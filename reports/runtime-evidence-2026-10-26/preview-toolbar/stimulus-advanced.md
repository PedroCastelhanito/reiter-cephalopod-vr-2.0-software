# Stimulus Advanced grouping

2026-10-26 Asia/Tokyo. Dirty working tree based on
f82be21f28d3c1141adeabe2558c29808062727a; concurrent GUI edits preserved.
Repository Python3.11, offscreen Qt, local view fixtures; no native/device execution.

Command: `python -u -m pytest tests/gui/test_dashboard.py -q -x -k
'stimulus_preview_belongs or preview_toolbar_wraps or video_previews_toggle or
preview_selection_waits or advanced_projector_toggles' --basetemp=.pytest-stimulus-advanced`.
Result:14 passed,859 deselected in8.70s. Ready and waiting stimulus requests survive
Video-Off, Advanced-Off closes/cancels only Stimulus, and selections/source rebuilds
stay in the intended group. Existing layout tests cover three styles and four
projector buttons at wide/narrow/wide sizes.

Ruff check/format previews.py and test_dashboard.py pass; Win32 mypy previews.py
passes; backend boundaries758/zero, pre-existing cohesion advisories remain.
No new abstraction, dependency or state. No running-app restart or rig/DPI claim.
