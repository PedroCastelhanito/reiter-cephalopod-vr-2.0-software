# Offline rig plot validation — 2026-10-26

Source: working tree based on f82be21f28d3c1141adeabe2558c29808062727a,
including concurrent GUI edits. SHA-256 at final validation:

- `src/cephvr/gui/projectors.py`: 13FC234B32919771003776D8ADBC95B052D4C57112DA3DE0C1B140A02B1A341B
- `tests/gui/test_dashboard.py`: F3CC7788B59B6F36C4508C6CDE3633BD0FCEF7D4F5616F8A1AB1C023D345C773

Windows Python 3.11 repository environment; Qt offscreen fixtures.
Initial owning test failed with KeyError Front after empty discovery.
Intermediate selection: 3 passed, 863 deselected in 4.98s. Final commands:

```powershell
.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -k 'centered_projection or tank_drag or tank_legend or bottom_optics' --basetemp=.test-tmp-rig-plot-final
.venv/Scripts/python.exe -m ruff check src/cephvr/gui/projectors.py tests/gui/test_dashboard.py
.venv/Scripts/python.exe -m ruff format --check src/cephvr/gui/projectors.py tests/gui/test_dashboard.py
.venv/Scripts/python.exe -m mypy --platform win32 src/cephvr/gui/projectors.py
.venv/Scripts/python.exe tools/check_backend_boundaries.py
git diff --check
```

Final results: 3 passed, 866 deselected in 3.04s; lint/format pass; mypy passes
one source; 758 backend modules, zero boundary violations, existing cohesion
advisories (including ProjectorsPanel); whitespace passes with existing CRLF
normalization warnings in shared documentation. Scope includes saved aspect,
invalid/missing reference dimensions, detected-mode precedence, view-only
rotation and Bottom mirror with Right disabled/disconnected. No app restart,
native output, physical geometry or rig acceptance claimed.
