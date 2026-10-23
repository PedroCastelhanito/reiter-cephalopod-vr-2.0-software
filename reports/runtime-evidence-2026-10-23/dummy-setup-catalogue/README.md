# All-saving-Off Setup catalogue failure — 2026-10-23

Source under test: dirty working tree based on
`59a973ac3ffc6fb331bbee1d93c6b283d6b90474`; concurrent unrelated changes preserved.
The running application's exact loaded revision is not independently established.
Governing rules: [E08](../../../docs/architecture/system-contracts.md#e08),
[E04](../../../docs/architecture/supervisor.md#e04),
[V01](../../../docs/architecture/visual_stimulus.md#v01),
[ARCH-002](../../../architecture.md#arch-002).

## Observed evidence and diagnosis

The owner's screenshot shows saving selections Off and Setup's retained
COMMAND_UNCONFIRMED error: `ReportHeartbeat: INVALID_CATALOGUE: cleanup catalogue
shrank or changed an obligation`. The matching repository emergency file is preserved
as [emergency.json](emergency.json), copied without editing from
`reports/emergency-762155356273900-33ae92b1-48c3-45c0-9431-4da589f39d9c.json`.
It identifies controller generation `bee6a0ce-26e7-4ff0-bee9-b37530072601`, supervisor
generation `6d3a95ea-58b8-4492-ba52-4baa1ef99539` and session
`3430d7e6-1e31-4d41-a71d-669cda078211`. No exact wall-clock event time is inferred
from its monotonic filename.

RecipeOwner.prepare registers revision0 empty, then previously advanced to revision1
even when recording selection produced zero recipe obligations. The E08 registry
requires each increased revision to append an obligation, so correctly rejects this
second empty catalogue. The new test reproduces this exact error without any native
renderer or GPU initialization. This does not require changing preview rendering,
supervisor validation, saved settings, deadlines or resource ownership.

The fix keeps revision0 and returns when the recipe-obligation list is empty.
Actual renderer resources subsequently advance the aggregate catalogue normally.

## Commands, outcomes and limitations

Repository Python3.11; unique repository-local basetemp paths.

- Before fix: `python -m pytest tests/visual_stimulus/test_coordinator.py -q
  -k recipe_setup_and_worker_growth --timeout=30`:1 failed (all-Off),1 passed
  (recording enabled),62 deselected. Failure is the exact ResourceCatalogueError
  above, raised by ResourceObligationRegistry.accept_heartbeat on revision1 empty.
- After fix: `python -m pytest tests/visual_stimulus/test_coordinator.py
  tests/supervisor/test_registration.py tests/supervisor/test_health.py -q --timeout=30`:
  **102 passed**, exit0. The new parameterized case validates real registry receipts,
  nonempty saved-mode recipe obligations, subsequent worker growth, unchanged
  heartbeats retaining revision and no fixture output writes.
- The initial sandbox asyncio run stalled without test output and was stopped.
  Subsequent test runs used approved local loopback access required by Windows
  asyncio socketpair initialization. No test assertions or transport checks weakened.
- Ruff check and format-check for `coordinator/recipes.py` and the owning
  `test_coordinator.py`:pass. Win32 mypy for recipes.py:pass. Backend boundaries:
  758 modules,zero violations,existing unrelated size advisories. The changed recipe
  owner stays cohesive; the fix adds no abstraction or dependency.

No current-process termination, restart, Setup/retry, cleanup request, recovery-state
edit, calibration/experiment mutation or failure-evidence clearing was performed.
The local regression fix does not establish cleanup of the observed failed session,
nor a successful corrected native Setup/experiment. These remain in the
[single rig checklist](../../rig-verification.md#dummy-session-no-output).
