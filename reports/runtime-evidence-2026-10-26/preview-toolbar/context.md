# Compact preview toolbar evidence

Date: 2026-10-26 (Asia/Tokyo). Dirty working tree based on
f82be21f28d3c1141adeabe2558c29808062727a; concurrent GUI work preserved.
Repository Python 3.11; QT_QPA_PLATFORM=offscreen, no controller/device connection.

Final commands and results:
- `python -u -m pytest tests/gui/test_dashboard.py -q -x -k 'preview_workspace or preview_toolbar or preview_timeline_visibility or video_previews_toggle or preview_selection_waits or preview_top_row or advanced_projector_toggles or preview_inline_controls' --basetemp=.pytest-preview-toolbar-pass`: 24 passed, 846 deselected in 21.63s.
- `python -u -m pytest tests/gui/test_preview_timeline.py -q -k retro_preview_controls --basetemp=.pytest-preview-toolbar-heading`: 1 passed, 90 deselected in 0.25s.
- Ruff check/format for previews.py, theme.py and both owning test files pass;
  Win32 mypy for both sources passes. Backend boundaries: 758 modules, zero violations;
  existing size advisories remain. Theme retains its cohesive shared palette/QSS role.

Earlier attempts: 19 passed/1 stale fixture failure (projector_names uses sources,
not synthetic cards). Corrected the fixture's explicit projector-name provider.
Three layout assertions initially sampled before Qt's queued layout settled;
process queued events before geometry checks. A broader run had 23 passed/2 failures
from old full-caption expectations; updated short visible/full accessible names.
One buffered Tee-Object attempt was interrupted without results. A documentation
edit attempt failed decoding UTF-8 with the platform default before writing;
explicit UTF-8 retry succeeded. CIM process inspection was unavailable.

Visual method: QApplication/apply_theme, DashboardWindow(sample=True), isolated
QSettings preview.ini, local review_program and three PreviewView sources, Running
view; Standard/Retro/Amber at 1920,1280,900 by1032, event processing then QWidget.grab.
Full Amber1920 image inspected, plus wide/narrow toolbar crops. Toolbar-only grabs
have transparent backgrounds; use the full dashboard for actual surface colors.
Measured wide height39px Retro/Amber,40px Standard; narrow70/72px respectively.
Automated layout test includes four projector choices, wide/narrow/wide reflow,
visible unclipped buttons, pending cancellation and disabled groups in all styles.
Existing tests cover close requests, authority/recording gates and preferences.
No native/DPI/hardware acceptance, application restart or experiment operation.

Source hashes at evidence recording:
- `src/cephvr/gui/previews.py`: `73ac3be1c14ad382565ec3eba5b81a4ad2e5f56dcc47cbfe1b7bd32fa2d5067e`
- `src/cephvr/gui/theme.py`: `7fdd8345b1a8ec88f955f2a1163e1f68af2f33a180b17f96d29a78f44ad68545`
