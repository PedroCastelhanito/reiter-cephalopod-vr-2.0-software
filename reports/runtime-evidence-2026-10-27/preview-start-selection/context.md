# Preview Start selection checks

Date: 2026-10-27 (Asia/Tokyo). Source: base83c7e81e plus uncommitted concurrent
work; this increment changes the deferred drain in previews.py, one availability
gate in managed_cameras.py and a two-case regression in test_dashboard.py.

Commands use `.venv/Scripts/python.exe`:

- `-m pytest tests/gui/test_dashboard.py -q -k 'preview_selection or preview_setup_selections or preview_controls_hide or managed_preview or managed_camera_projection or managed_camera_reconnect or running_navigation' --basetemp=.pytest_tmp_preview_start_final`:23 passed,978 deselected in8.75s.
- `-m ruff check src/cephvr/gui/previews.py src/cephvr/gui/managed_cameras.py tests/gui/test_dashboard.py`: passed.
- `-m ruff format --check src/cephvr/gui/previews.py src/cephvr/gui/managed_cameras.py tests/gui/test_dashboard.py`:3 already formatted.
- `-m mypy --platform win32 src/cephvr/gui/previews.py src/cephvr/gui/managed_cameras.py`: no issues in2 sources.
- `tools/check_backend_boundaries.py`:767 modules, zero violations; existing size/cohesion advisories.
- `git diff --check`: passed; Git emitted existing CRLF normalization warnings.

Initial regression fixture used a review-connected workspace, whose synthetic
visibility callback interfered with managed admission:2 failed,7 passed. Corrected
the fixture to use an isolated workspace with the real ManagedCameras admission
gate;10 focused checks passed before the broader23-case run. No rig/native pass
or full GUI suite claimed. No live application actions, capture or recording changes.
