# Navigation marker render — 2026-10-23

Source: dirty working tree based on59a973ac3ffc6fb331bbee1d93c6b283d6b90474;
see the task's LOG entry for validation scope.
Method: repository Python3.11, PyQt6 offscreen QApplication; sample DashboardWindow
with isolated QSettings, Amber style,1920x1032; select Devices/Projectors/Rig geometry,
process Qt events and grab the window. [Render](amber.png).

Inspected all main/child leading markers, coral selected icons/labels and trailing
markers, plus Projector setup tabs. Existing long-label elision remains, with reserved
marker gutters. This sample render is not a live device, native interaction, DPI or
rig acceptance result.

G02rev134 follow-up uses the same source base/method/geometry and retains the
[corrected close-marker render](close-markers.png). Inspected Configure/Projectors
suffixes beside their labels and the elided Rig geometry tab suffix. The earlier
render documents the reported row-edge spacing and is historical evidence.

G02rev137 `tab-marker-equal-spacing`: [tab crop](equal-spacing-tabs.png) inspected
with the same offscreen sample method at1400x900; both chevrons use native title
bounds and equal6px gaps, including the shortened Rig geometry title and its icon.
Repository Python pytest `tests/gui/test_dashboard.py -q -k
phosphor_navigation_uses_chevron_markers_with_hover --tb=short`:1 passed,853 deselected.
Ruff check/format and Win32 mypy `src/cephvr/gui/retro_instruments.py` pass;
`tools/check_backend_boundaries.py`:755 modules,zero violations (existing advisories).
No live application interaction/restart or native/DPI acceptance.

Sidebar correction: the supplied owner screenshot showed the sidebar, outside the
previous tab-only fix. `equal-spacing-sidebar.png` uses repository Python/PyQt6,
offscreen sample Dashboard1920x1032 and isolated QSettings, cropped to the sidebar.
Source remains a concurrent dirty tree based on59a973ac. Updated existing navigation
test measures rendered title/marker pixels:1 passed,854 deselected. Initial rail gap
check failed by6px; native focus-frame text inset correction resolved it. Checks:
Ruff check/format components.py,devices_rail.py,test_dashboard.py; Win32 mypy the two
source owners; boundaries756/zero. No native/runtime interaction or restart.

Final icon/title-group correction (`sidebar-icon-title-spacing`): the previous
sidebar render measured title-only gaps and is superseded by
[icon-title-group-spacing.png](icon-title-group-spacing.png). Same offscreen sample
method at1920x1032,254px sidebar crop. Markers frame the icon/title group; transparent
icon padding and native text inset are included, icon width is not repeated on the
right. Updated pixel regression passes (1 passed,856 deselected), comparing leading
marker-to-icon against title-to-trailing-marker within2px, including short/long rows.
Earlier probe assertions exposed transparent icon padding and Qt selected-icon tint;
visible-ink threshold replaces coral-only icon detection. Ruff check/format3 files,
Win32 mypy2 sources and boundaries757/zero pass. No native restart/DPI acceptance.
