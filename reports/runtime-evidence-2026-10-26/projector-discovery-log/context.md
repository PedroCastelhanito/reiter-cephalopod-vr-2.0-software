# Projector discovery messages — 2026-10-26

Source: dirty working tree based on f82be21f28d3c1141adeabe2558c29808062727a,
including concurrent GUI work. Final Projectors SHA-256:
DD7FF15403E397516B89F19530F8267B394EAE6BE2E86662824F560EA6E8630D.
Owning Dashboard test file hash sampled before final rerun:
5E679A1FB40D052AA117D3B1EA26FF1A5EDD6AD50A80CC2F28FEF64E27A467C2.
Concurrent edits may change that file after collection.

Windows repository Python 3.11; Qt offscreen fixtures. Commands:

```powershell
.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -k 'projectors_number_secondary or disconnected_projector_draft or projector_assignments_survive_restart or setup_without_projectors or review_projector_inventory' --basetemp=.test-tmp-projector-log-final
.venv/Scripts/python.exe -m ruff check src/cephvr/gui/projectors.py tests/gui/test_dashboard.py
.venv/Scripts/python.exe -m ruff format --check src/cephvr/gui/projectors.py tests/gui/test_dashboard.py
.venv/Scripts/python.exe -m mypy --platform win32 src/cephvr/gui/projectors.py
.venv/Scripts/python.exe tools/check_backend_boundaries.py
git diff --check
```

Final: 7 passed,863 deselected in18.77s; Ruff check/format and mypy pass.
Prior selection passed7 in14.35s. Boundary check between these runs:758 modules,
zero violations with existing cohesion advisories, including ProjectorsPanel.
Tests assert one outcome row, one guidance occurrence, truthful empty inventory,
retained missing faces, native identification warning, persistence and Setup gate.
Whitespace passes; Git reports existing CRLF normalization warnings.
No app restart, live displays, native DPI or hardware acceptance claimed.
