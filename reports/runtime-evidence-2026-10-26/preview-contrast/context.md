# Preview toggle contrast

2026-10-26 Asia/Tokyo; dirty working tree based on
f82be21f28d3c1141adeabe2558c29808062727a. Repository Python3.11, offscreen Qt.

`python -u -m pytest tests/gui/test_dashboard.py -q -x -k
'preview_toggle_selection or preview_toolbar_wraps or stimulus_preview_belongs'
--basetemp=.pytest-preview-contrast`:8 passed,868 deselected in12.83s.
Actual widget pixel checks cover selection, hover and disabled selection in
Standard, Retro and Amber; existing checks cover geometry and independent masters.
Ruff check/format theme.py/test_dashboard.py pass; Win32 mypy theme.py passes;
backend boundaries758/zero, existing cohesion advisories; git diff --check passes.

[States](states.png) visually inspected. Method: isolated QWidget, four checkable
QPushButtons using preview-choice role, shared Amber stylesheet, packaged terminal
font and explicit panel background; QWidget.grab after processing events. Initial
capture lacked font registration/background; corrected before visual acceptance.
No application restart, native monitor/DPI or device behavior acceptance.
