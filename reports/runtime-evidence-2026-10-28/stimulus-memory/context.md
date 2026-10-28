# Stimulus defaults validation — 2026-10-28

Source: current uncommitted working tree; concurrent GUI/backend changes present.
Governing decision: [G01](../../../docs/architecture/gui.md#g01), revision377.
Python: repository .venv/Scripts/python.exe; QT_QPA_PLATFORM=offscreen.

- pytest tests/gui/test_stimulus_authoring.py -q: 53 passed.
- pytest tests/gui/test_dashboard.py -q -k 'full_gui_config_round_trip or invalid_full_gui_config or runtime_gui_close_reopen or runtime_gui_save_failure or runtime_gui_unrestored': 11 passed, 1032 deselected.
- Scoped Ruff check/format on stimulus_memory.py, epoch_composer.py,
  gui_snapshot.py and test_stimulus_authoring.py passed.
- mypy --platform win32 on those three source modules passed after adding the
  TypeAdapter annotation identified by the initial check.
- tools/check_backend_boundaries.py: 792 modules, zero violations; existing
  cohesion advisories do not affect the three edited source modules.

Nine new cases cover shared latest settings, filename clearing, seven type-specific
parameter round trips, normal GuiHistory persistence, old snapshots and invalid
saved type rejection. Other owning tests cover asset-free generated stimuli,
seed placement and repetition/timing. These are offscreen/local results, not live
application restart, device Setup, performance or rig acceptance.
