# Alignment correction — 2026-10-26

Uncommitted follow-up to context.json base revision; earlier captures remain historical.
Qt offscreen DashboardWindow(sample=True), isolated alignment.ini QSettings,
ReviewControls, Amber,1920x980; trial12 and role pins11/10/9 are presentation drafts.
Five processEvents calls before [MCU capture](mcu-alignment.png). No discovery,
controller/device commands, saved operator settings or native desktop verification.

- pytest tests/gui/test_dashboard.py -q -k 'configuration_groups_stay_unfilled or table_row_bands or projector_config_tabs_keep_column_width': [7 passed](alignment-tests.txt).
- Initial attempt:3 margin-assertion failures/4 passes; StageCard.body is its inner
  layout (zero margins), so assert the actual group.layout() inset instead.
- Ruff check/format on editing_card.py, microcontroller.py, test_dashboard.py: pass.
- mypy --platform win32 on editing_card.py and microcontroller.py: pass.
- [Boundaries](alignment-boundaries.txt):760 modules/zero violations; unchanged size advisories.
- git diff --check: pass. Theme/appearance source diff empty; no scale change.
