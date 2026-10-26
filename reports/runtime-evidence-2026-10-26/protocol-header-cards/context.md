# Protocol header cards — 2026-10-26

Source: current uncommitted workspace, not an isolated revision.
Method: offscreen PyQt6 QApplication with standard application stylesheet,
sample DashboardWindow, Amber appearance, Protocol page,1920x980 and200ms settling.
[Render](protocol.png) visually inspected: Configuration file, Protocol type and
Assets folder all have the shared main-card frame and heading treatment.

Validation: pytest tests/gui/test_dashboard.py -q -k
"protocol_cards_reflow or protocol_participation_and_asset or configuration_groups_stay_unfilled"
passes5 cases/958 deselected. Ruff check/format and Win32 mypy pass for protocol.py
and stimulus_assets.py. Boundaries760 modules/zero violations; existing size
advisories remain, with no new responsibility added to protocol.py.
No live restart, device commands or rig validation.
