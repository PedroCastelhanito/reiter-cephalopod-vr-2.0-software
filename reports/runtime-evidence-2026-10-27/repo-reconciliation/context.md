# Repository reconciliation — 2026-10-27

Source: `c7881b1f87a5d294383d310ebcb92630cd825099` plus the shared, dirty
working tree. These checks overlapped the two finishing implementation chats;
later final checks must be distinguished from this intermediate snapshot.

The monitoring chat observed both Update protocol stimulus types and Clarify
projector texture scaling active. The latter recovered from a model-capacity
failure and completed. The owner authorized reconciliation, cleanup, commit and
sync, with new runtime behavior/logic decisions deferred into TODO.

## Intermediate checks

- Acquisition cleanup and window coordinates: `python -m pytest
  tests/acquisition/test_cleanup_aggregation.py
  tests/platform/test_window_coordinates.py -q -m "not windows and not rig"
  --basetemp=.pytest-monitor-cleanup-permitted --timeout=60`: 71 passed,
  2 deselected. The sandbox attempt stalled after 21 cases and was interrupted;
  the same assertions passed with loopback access.
- The display-replacement fake did not isolate the new Windows shell operation.
  One monkeypatch alongside existing window mocks fixes only the test boundary.
  `python -m pytest tests/visual_stimulus/test_display_calibration_rendering.py
  -q -m "not windows and not rig" --basetemp=.pytest-monitor-display --timeout=30`:
  31 passed; scoped Ruff check/format passed.
- Full local `tests/visual_stimulus -q -m "not windows and not rig" --timeout=60`:
  617 passed, 55 deselected, 3 subtests passed, before the final Grating state change.
- Affected-owner Ruff check passed; format checked 431 files. Win32 mypy initially
  found a non-exported `SparseNoiseAppearance` import. Importing its defining module
  directly preserves behavior; all 406 affected source files then passed.
- 14 canonical schemas matched; boundaries checked 785 modules with zero violations.
  Size advisories remain recorded with the implementation owners.
- `git fetch origin` initially could not write sandboxed FETCH_HEAD; authorized
  elevated fetch succeeded and HEAD/origin/main were equal at that point.

## Incomplete serial GUI run

Command: `.venv/Scripts/python.exe -m pytest tests/gui -q -m "not windows and not rig"
--basetemp=C:/Users/ReiterU_PC/.codex/visualizations/2026/10/27/01a17c84-64d2-74e2-9a0f-fe29c34a12c1/pytest-gui
--timeout=60`, with `QT_QPA_PLATFORM=offscreen` and permitted loopback access.

The serial process progressed beyond 79%, emitted multiple `F` markers, then
returned exit code 1 with only progress dots in its final output chunk. No final
pytest summary, assertion traceback or reliable completed-case count was returned.
The reason for the early exit is unproven. The shared lastfailed cache contained
older renamed/deleted cases and cannot identify this run's failures reliably.
This is incomplete verification, not a full GUI pass. Other chats' parallel worker
crashes and focused passes remain separately assessed in their evidence.

No managed-app restart, hardware operation, physical projection, firmware change,
optical timing or full-load acceptance was performed by the monitoring chat.

## Final settled-tree checks

Both chats were idle before these checks. The final full local Visual Stimulus
command used the same arguments above with `pytest-backend-final`:620 passed,55
deselected,3 subtests passed. The final offscreen dashboard command used
`-k "media_family or inline_grating_pattern or sparse_noise_layer or protocol_category or category_first_visit or presentation_rows or protocol_type_switch or category_preview_modes or grating or inline_sparse_noise_discards"`
and `pytest-gui-final`:32 passed,1027 deselected.

Final Ruff check/format covered GUI, Generate Stimulus, Visual Stimulus, affected
acquisition/platform files and their tests plus tools/prepare_sparse_noise.py:
431 files formatted. Win32 mypy checked406 sources with no issues. All14 schemas
match; final boundary check covers785 modules with0 violations (cohesion advisories
remain in owning reports). `git diff --check` passes. These do not supersede the
incomplete broad GUI run or establish physical acceptance.

Cleanup preserved emergency/experiment/evidence data, normalized TODO spacing and
moved inactive preview acceptance to Next. New general runtime assignments remain
Deferred; profile policy inventory reconciliation remains Next. Final source
provenance is in [source-snapshot.json](source-snapshot.json).
