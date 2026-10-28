# Projector tab hover repair — 2026-10-28

Source: working tree based on e4dd8f2694aa075380fe6711a884fe5894763c6f;
other chats have concurrent unrelated changes. User reported Projectors tab jitter.

Before repair, the owning layout regression recorded repeated tab Move events at
y=444 then y=466 for each hover (1175px Standard window). Final-position-only probes
missed these intermediate jumps. Hover icon refresh invalidates the parent layout;
that layout reset the manually centered bar before CenterTabsInGap moved it back.

Repair gives CenterTabsInGap sole tab geometry ownership, with a layout-managed
placeholder preserving the original row and card spacing. Theme height changes
update the placeholder; native tab input, text, icons and markers remain unchanged.
ARCH-002 review: reuse the existing focused helper; no dependency or backend change.

Validation command (repository Python 3.11):

```powershell
.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -k 'projector_config_tabs_keep_column_width_and_table_drafts or phosphor_navigation_uses_chevron_markers_with_hover' --basetemp <fresh workspace temp directory>
```

Offscreen: eight cases pass, covering three styles, two widths, all selected pages,
no intermediate hover moves, retained draft/column geometry and marker/icon colors.
Initial test timing also observed a pending page-change layout; the regression now
allows that transition to settle before observing hover. Initial default pytest
temporary-directory creation failed in the sandbox; workspace basetemp resolved it.

Native (`QT_QPA_PLATFORM=windows`): eight cases pass. The process emitted Windows
exception diagnostic 0x8001010d during fixture window.show(), then continued to the
passing summary. This diagnostic's cause is unverified; this is not a clean native
startup acceptance claim. See native.txt. No managed app restart or hardware action.

Scoped Ruff check/format and Win32 mypy pass. Backend boundaries:791 modules,
zero violations; existing size advisories concern unchanged modules. The edited
layouts helper remains cohesive. Final whitespace check passes. Tests extend the
owning Dashboard behavior module under ARCH-002. No architectural rule changed:
G02's centered tab spacing and hover styling are preserved.
