# Camera hover caption — 2026-10-26

Working-tree implementation under G01rev328, based on revision
f82be21f28d3c1141adeabe2558c29808062727a.
Concurrent GUI edits preserved. No runtime restart/device/session changes.

ARCH-002: native style/hover responsibilities live in focused platform/windows/
preview_caption.py; existing HighGUI loop services them, no thread, dependency,
RPC or authoritative lifecycle added. Caption hides WS_CAPTION/WS_THICKFRAME;
hover restores native drag/close controls. Mouse-down pins current chrome state
until release. DWM-visible footprint is preserved without activation/Z-order
changes; automatic placement only resizes when side changes.

Validation:
- .venv/Scripts/python.exe -m pytest tests/platform/test_window_coordinates.py
  tests/acquisition/test_manual_preview.py -q --basetemp .test-tmp-hover-complete
  =>170 passed,6 existing SWIG deprecation warnings,1.63s (approved native/local
  permissions). Native test creates isolated windows, drives show/hide on their
  owner thread, checks exact visible bounds and style, native mouse pan/zoom/reset,
  X-close, producer independence and disposal. Mock hover tests cover enter/leave,
  unchanged-state no-op and mouse-button hold outside the window.
- Ruff check/format passes four changed Python files; Win32 mypy passes both
  implementation files. Backend boundaries759 modules/zero violations.
- Initial sandboxed suite stalled after63 cases and was interrupted. Native first
  attempt exposed a stale assertion requiring decorated256x256 client size; tests
  now require source-size minimum and separately retain exact outer bounds/style
  assertions for both states. Final full targeted suite passes.

Limits: native isolated-window tests, not an actual operator cursor drag in the
running experiment. Alternate DPI, multiscreen hover and full-load acceptance
remain unverified. Existing application needs restart to load implementation;
current user session was not interrupted.
