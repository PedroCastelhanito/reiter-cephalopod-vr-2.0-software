# Missing startup assets — 2026-10-29

Source: current uncommitted working tree, including concurrent changes; no isolated
revision or native rig pass claimed. Owner terminal output and emergency report
`reports/emergency-1222218227600-04a76cf3-c4db-4260-8c45-539e52971c31.json`
show missing cephvr-assets/media escalated to renderer/supervisor shutdown.

Repository Python: `.venv/Scripts/python.exe`.

- `-m pytest tests/visual_stimulus/test_lifecycle.py -q -k startup_missing_output -m "not windows and not rig"`: 30 passed, 72 deselected.
- `-m pytest tests/visual_stimulus/test_controller_communication.py tests/visual_stimulus/test_lifecycle.py tests/visual_stimulus/test_coordinator.py -q -m "not windows and not rig"`: 183 passed, one deselected, outside sandbox for authenticated loopback.
- First unrestricted integration run: three passed, asset case failed because coordinator recognized only output-unavailable code. Fixed exact rejection-code matching, then combined run above passed.
- Sandbox lifecycle and communication attempts stalled; interrupted without results. CIM inspection denied by sandbox; no process inventory obtained.
- Ruff check/format and Win32 mypy cover native_display.py, worker/display_initialization.py, worker/runtime.py, coordinator/display.py; Ruff also covers the two edited test modules. Formatting check initially requested coordinator/display.py formatting, then corrected.
- `tools/check_backend_boundaries.py`: 802 modules, zero violations, existing size warnings. Changed modules remain focused and under 500 lines.
- `git diff --check`: no whitespace errors; existing line-ending warnings remain.

Tests verify missing root/file and denied/non-directory input, exact cleanup,
deadline/cancellation failure escalation, fresh Setup, and authenticated controller/
coordinator/renderer rejection without fencing/shutdown. Native GUI restart and
physical outputs have not been tested; see the single rig checklist.
