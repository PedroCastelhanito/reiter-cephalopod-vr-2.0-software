# Setup inactivity implementation validation - 2026-10-28

Source base: `e4dd8f2694aa075380fe6711a884fe5894763c6f`, with uncommitted
changes in a concurrently edited working tree. No commit, restart, Setup/Start,
device action or native/optical acceptance was performed by this chat.

Governing decisions: [E05](../../../docs/architecture/experiment.md#e05),
[E06](../../../docs/architecture/system-contracts.md#e06),
[E08](../../../docs/architecture/system-contracts.md#e08),
[V04](../../../docs/architecture/visual_stimulus.md#v04).

## Final methods and results

Repository Python 3.11 environment: `.venv/Scripts/python.exe`.

- `-m pytest tests/controller tests/visual_stimulus tests/client tests/supervisor
  tests/shared/test_invariants.py -q -m "not windows and not rig"
  --basetemp <external-temp> --timeout=30 --maxfail=3`: **1772 passed,
  4 skipped, 70 deselected, 5 subtests passed**, 21.98 s. Raw output:
  [pytest-final-verified.txt](pytest-final-verified.txt). External temporary root:
  `C:/Users/REITER~1/AppData/Local/Temp/cephvr-setup-inactivity-f65cd113b62f4042ac3b47eca9bb6bd9`.
  Ran with permitted loopback access, including authenticated transport coverage.
- Final current-source upload-bound assertion case: `-m pytest
  tests/visual_stimulus/test_rendering.py::test_full_resolution_four_output_upload_has_headroom_for_400ms_presentations
  -q --timeout=20 --basetemp=.tmp-setup-upload-assertion`: **1 passed**.
  This is an isolated repeat, not another unique test in the suite count.
- `-m mypy --platform win32 src/cephvr/controller src/cephvr/shared/deadlines.py
  src/cephvr/visual_stimulus`: **304 source files pass**;
  [output](mypy-final.txt). Windows-target static analysis is not rig acceptance.
- `-m ruff check src/cephvr/controller tests/controller src/cephvr/visual_stimulus
  tests/visual_stimulus src/cephvr/shared/deadlines.py tests/shared/test_invariants.py`:
  **passes**, [output](ruff-final.txt).
- Affected-path `-m ruff format --check`: **190 files already formatted**;
  [scoped output](format-scoped-final.txt). A broader format attempt flags two
  concurrently edited files (`visual_stimulus/configuration.py` and
  `tests/visual_stimulus/test_rendering.py`); no broad formatting rewrite applied.
  [Full broader output](format-final.txt).
- `tools/check_backend_boundaries.py`: **796 modules, zero violations**;
  [output and size advisories](boundaries-final.txt).
- `tools/generate_contracts.py`: **19 Protobuf sources regenerated successfully**.
  Added `OperationState.progress_sequence`; generated bindings were not hand-edited.
  Config/policy version 9 is parsed and checked by the passing controller loader tests.
- `git diff --check`: **passes** (CRLF normalization warnings only).

## Behavioral scope

Tests cover independent dispatched-backend deadlines, no renewal on duplicate
operation dispatch, CPU and GL work beyond the original total cutoff, resource
budget checks using the live cutoff, prepared-artifact publication with a fresh
inactivity allowance, increasing progress sequences, stale/duplicate/unchanged/
late/cancelled/recovery updates, Ready after the old total cutoff, one bounded
recovery query using the expired inactivity cutoff, and cancellation. Per-trial,
device, heartbeat, recording and cleanup clocks retain their existing tests.
No new dependency or process; renewal state is bounded per participant/operation.

ARCH-002 review: extracted coordinator Setup progress validation/relay into its
focused `coordinator/setup_progress.py` before extending oversized reports.
Existing assembly, state, acquisition resolution, native resource/driver and GL
adapter size advisories remain cohesive wiring/record/owner concerns for this
increment; only narrow deadline suppliers/operations are added there, without
runtime back-references or new ownership. Existing behavior test modules extended.

## Earlier attempts and corrections

Sandboxed asyncio tests blocked creating Windows' loopback socket pair before
test execution. [Faulthandler trace](sandbox-asyncio-trace.txt) identifies
`socket._fallback_socketpair`/`accept`; permitted loopback reruns worked. Only this
chat's two verified blocked Python test processes were stopped.

Intermediate failures were corrected: fixed-policy keys needed loader binding;
old tests expected an absolute original publication bound and optional progress;
a new dispatch fixture needed explicit backend/save settings; one text edit used
the Windows locale and corrupted three progress labels, which were restored to
UTF-8; a concurrent upload test renamed its loop counter but still asserted the
old name (corrected the assertion to preserve the existing bound). An initial
20 ms reservation-thread scheduling assertion failure did not reproduce in the
final suite. Demo-asset fixture errors from generating inside the repository were
resolved using the external temporary directory. A concurrent image-crop mapped
uniform failure disappeared after that area's source changes; final suite passes.
No weakened timing, identity, cleanup, payload or upload-bound assertions.

Native full-600-image Setup/publication/Cleanup, forced backend stalls and combined
load remain pending in the [rig checklist](../../rig-verification.md#setup-inactivity).
