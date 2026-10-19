# Offscreen GUI verification context — 2026-10-19

Source: HEAD `5945f1708240929406f40c4def98dbcf50ff7947` plus the existing dirty
working tree and the focused corrections below. `gui-source-files.json` records
SHA256 hashes of GUI source/tests at final-run startup; `gui-tested-files.json`
records the edited source/test files and the independent tracking-live test.
These local checks do not establish physical GUI, camera, projector or rig acceptance.
The rig coordinator owns the separate native evidence and report reconciliation.

## Findings and corrections

- G02: the coordinator corrected the stale camera successful-completion console
  assertion. A second stale MCU assertion now checks exact edge/output evidence
  in its HUD and quiet routine console output. Existing error coverage is retained.
- G01: `CamerasPanel.refresh_inventory` now emits `drafts_changed` before
  `participation_changed`. Recording controls must be synchronized before the
  participation callback installs preview views. An unhandled `KeyError` previously
  ended ordinary Windows pytest at the mocked inventory test, after 201 cases.
  `gui-inventory-exception.log` captures the callback traceback using a diagnostic
  exception hook only. The new owning regression fails before the ordering fix
  (`gui-inventory-regression-before.log`) and passes after it with ordinary pytest
  (`gui-inventory-regression-after.log`). No exception hook is used for final checks.
- G01/V02/V14: `PreviewGeometry.artifact` now includes its existing top-right
  corner, required by the linked-motion resolver's calibrated-center calculation.
  Existing linked-preview cases exposed the missing field. The spin fixture now
  uses the accepted centered pivot; drift retains its off-center initial position.
- Existing fixtures now provide the action-progress/stimulus-preview peers, emit
  the normal draft-change signal after direct camera replacement, and initialize
  both hidden preview timelines before comparing their controls.

## Commands and intermediate evidence

Every pytest invocation used `QT_QPA_PLATFORM=offscreen`. Test execution required
elevated local socket permission for asyncio, without running native device tests.
Python: `.venv/Scripts/python.exe` (3.11.15).

- `python -m pytest tests/gui -vv -x -o faulthandler_timeout=60 --basetemp=.tmp/gui-offscreen-20261019`
  → abrupt exit 1 at inventory callback; `gui-offscreen-verbose.log`.
- Same command with `--basetemp=.tmp/gui-offscreen-fixed-20261019`
  → 222 passed, one stale MCU assertion failed; `gui-offscreen-fixed.log`.
- Full discovery without `-x`, `--basetemp=.tmp/gui-offscreen-all-20261019`
  → 740 passed, eight failed, three fixture errors in 365.65s;
  `gui-offscreen-all.log`. The generator deliberately rejects asset output inside
  the repository; the final invocation uses a unique external TEMP directory.
- Nine focused cases after corrections → nine passed, 741 deselected in 16.52s;
  `gui-collected-fixes-final.log`.
- `python -m ruff check src/cephvr/gui tests/gui` → pass (`gui-ruff-check.log`).
- `python -m ruff format --check src/cephvr/gui tests/gui` → 185 files formatted
  (`gui-ruff-format.log`).
- `python -m mypy --platform win32 src/cephvr/gui` → 183 source files pass
  (`gui-mypy.log`).
- `python tools/check_backend_boundaries.py` → 737 modules, zero violations
  (`gui-boundaries.log`). Existing size warnings remain. The camera source change
  only reorders two signals; no responsibility or dependency was added to the
  existing 646-line panel. The preview geometry helper remains focused and small.
- `git diff --check` → pass (`gui-diff-check.log`, existing CRLF notices only).

Final full suite: **751 passed in 363.98s**, exit 0; `gui-offscreen-final.log`.
Command: `python -m pytest tests/gui -vv -o faulthandler_timeout=60
--basetemp=<unique external TEMP/cephvr-gui-final-UUID>`.
