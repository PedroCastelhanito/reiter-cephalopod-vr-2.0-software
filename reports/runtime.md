# Controller and supervisor status

Updated: 2026-10-01. Implementation/source review is recorded for the controller,
supervisor, launcher, headless client and shared/native helpers. Local results below
have their original scope; Windows and full-workload acceptance remain pending.
[ARCH-001/002](../architecture.md#arch-001) owns scope and structure;
[E04](../docs/architecture/supervisor.md#e04) and
[E05/E07](../docs/architecture/experiment.md) and
[E06/E08](../docs/architecture/system-contracts.md#e08) own behavior.

## Current scope and review

Final Windows repair and one-time elevated follow-up (2026-10-01, baseline HEAD
`826984255e0a8469afccbda2dcaf8c642b528b33` plus uncommitted repairs): controller
202 passed; supervisor 106; shared 52; platform 46; launcher 10 and client 6 passed.
Whole suite: 759 passed with zero failures/skips, all Windows and bounded rig markers,
using dedicated elevated scratch. The owner removed exactly two POSIX-only tests;
native unsafe-DACL rejection remains. Standard-token default-temp full suite passed
755 with four symlink privilege skips; actual one-time elevation executed those four.
Elevation exposed missing startup dependencies in prepared Python; finite matching-base
VCRUNTIME140.dll/optional zlib.dll preparation now verifies source/copy hashes before
planning. Exact executing PID/image, venv imports and bootstrap proof passes elevated
and Medium-token default-temp checks. No persistent OS privilege/policy change.
[Dated evidence](rig-audit-2026-10-01/README.md) preserves failed attempts, latest JUnit,
commands, startup provenance and scoped cleanup; full experiment acceptance remains open.
Setup Ready/failure and successful Start use the existing terminal completion
owner, preserving failure codes, publication order and active-session retention.
The native intrinsic helper repairs cross-process ring atomics. Verified prepared
Python images preserve the fresh virtual environment: a live native regression
confirms launched/code PID and OS image, one job member and inherited bootstrap.
E04 reservation guards preserve exclusive ownership while Windows closes the byte
lock for quarantine, including failure; default-path recovery persistence passes.
Fixtures now respect Windows sharing/permissions and await actual async outcomes.

Full managed launch remains gated by the unimplemented GUI. Automatic approval
review rejected the earlier proposed launcher invocation for potential managed
service/hardware effects; it was not executed. Focused checks do not establish
full E04/E08 application/device/workload acceptance. Capacity bypass was not
established; authorization checks the same capacity under the lifecycle lock.
ARCH-002 review keeps the 502-line reservation owner cohesive around namespace
ownership; native tests remain one platform-fixture module rather than per-fix files.

- Controller lifecycle, configuration validation, live control leases, RPC admission,
  output planning, serialized central metadata, preparation handoffs, incident handling,
  camera/preview forwarding, and headless control.
- Supervisor launch registration, health/evidence forwarding, cleanup obligations,
  independent emergency reporting, and bounded shutdown.
- Shared identity, command retention, ingress bounds, policy loading, credentials,
  resource/incident proof helpers; Windows jobs, process handles, guards, bootstrap
  pipes, private ACLs and publication helpers; persistent external launcher.
- One Python project with backend-owned packages, generated Protobuf bindings and
  type stubs, configured development tools, reproducible generation in package builds,
  and tests organized by code owner.

Components use focused typed records, peer operations and shared authoritative state.
Controller control/lifecycle/device/incident/metadata/transport owners and supervisor
registration/health/recovery/shutdown owners are assembled by their coordinators.
RPC adapters retain authentication and admission. Source review covered cleanup
fences, partial Setup, cancellation, original deadlines, command retention, durable
metadata and process ownership; static comparisons do not prove execution.

The module entry point calls the controller CLI. Mutable incident retention belongs
to `controller/incident/registry.py`; shared proof validation stays in `shared/`.
The acquisition-specific audit corrections are recorded in [acquisition.md](acquisition.md).

Supervisor simplification under ARCH-002 removes unreachable registry rejections,
shares worker channel revalidation/cache management and session/trial containment,
and separates native process exit evidence from shutdown outcome ownership. Camera
and persistent Visual Stimulus launch scopes remain distinct. Independent delivery still uses
bounded asyncio tasks; no additional package, public interface or policy change was
needed. E04/E06/E08 emergency reporting, original deadlines and cleanup/exit evidence
remain with their existing owners. Existing recovery/retention findings below remain
outside this refactor.

A second behavior-preserving pass gives the acquisition (`acquisition_worker.py`) and
Visual Stimulus worker controllers one interface (`WorkerControl`), so shutdown loops
over them instead of duplicating each step; acquisition's separate cleanup module was
merged into its controller. `shutdown_owned` is split into named steps with one bounded
polling helper and one outer-deadline expression. `GrpcOutbound` extends the worker
transport instead of re-declaring its methods, with one call helper and the port now
declaring channel retirement and close. Work scope, live launch phases and backend
role sets each have one definition, and the health monitor tick and tracking-release
forwarding are separate methods. Error codes/messages, lock scopes, deadlines and side-
effect order are unchanged; two observable differences are accepted: process-exit polling
sleeps are capped at the remaining deadline, and a registration with several faults can
report a different first error (single-fault errors are unchanged). Windows-only
`startup.py`/`main.py` and the registry `confirm()` state machine were intentionally left
alone.

Controller simplification under ARCH-002 shares bounded backend interruption delivery,
moves recovery-log draining and writer sealing into the existing metadata owner,
and consolidates camera-operation retirement in its retention owner. E04/E05/E06/E07/E08
lock scopes, original deadlines, terminal evidence, durable-write order and cleanup
outcomes remain unchanged. No dependency, schema, public RPC or policy change was
needed. Setup and manual camera readback keep distinct admission/adoption transactions:
their validator and ownership requirements differ, so merging them is not a safe
mechanical simplification.

A second controller pass removes unread wiring (constructor parameters, attributes and
three mirrored configuration fields), the static file-policy fallback and the
five-layer `recovery_log_done` hook, and gives repeated patterns one owner: bounded
warning retention (`ControlState.add_warning`), rejected receipts/admissions
(`controller/receipts.py`), affected-resource and reservation-unconfirmed predicates on
`Attempt`, and the backend-name set. Backend command wrappers, AbortNow/Shutdown
admission, reservation finish, trial-log documents, admission failure handling,
report-retention conflicts and the shared backend cleanup dispatch (Setup cancel and
finalize) each have one implementation. `ControllerRuntime` now keeps wiring and thin
delegators: startup-recovery installation moved to `OperatorPrompts`, authority status
capture to `AuthorityStatus`, the manual-cleanup warning to its cleanup owner, and the
AbortNow/Shutdown precondition to the one predicate in `SessionCommands`. Settings and
output resolution moved from `setup_execution.py` to `setup_resolution.py`, and
oversized Setup, interruption, completion and configuration functions were split into
named steps. Lock scopes, deadlines, durable-write order, identity checks and message
text are unchanged; one accepted observable difference is that warnings recorded at
sites that previously did not trim are now bounded in memory (published snapshots
already applied the same cap). The controller backend port keeps
`apply_camera_settings`/`apply_pulse_configuration` for the open owned-camera-edit task.
`startup/application.py` (Windows-only, untested here), `transport/ingress.py` (no direct
test), the authority-loss/evidence/recovery-inspection state machines and the Optional
fail-closed dependencies were intentionally left alone.

## Unresolved findings and limitations

The retained source review identifies these open items; they were not re-audited
during documentation consolidation. The controller does not yet apply camera/pulse
edits to owned editing/preview cameras (contracts/acquisition/configuration-control.md);
until it does, such edits are rejected while a camera is owned. Setup and manual
camera readback still use separate resolution/adoption paths. Supervisor worker
launches are never released, so their registry entries persist for the run.

Known low-severity limits left for a later pass: after accepted shutdown intent the
supervisor checks for controller loss at shutdown entry and before backend Shutdown,
not continuously; a pending backend-exit expiry or launch timeout can still raise a
safety fence during shutdown; a PlanLaunch replayed after its released entry is
pruned (only at registry capacity) plans anew; and a mid-session late-Finished
`recovery` event makes startup inspection treat an intact log as unconfirmed (the
safe fallback).

Remaining observations from the 2026-10-01 controller audit (not fixed):
`setup_admission.py` and `start.py` write `control.operations` entries directly,
bypassing `operation()`'s duplicate-ID helper; ingress duplicate handling still needs
review, and capacity is checked by `authorized()`. Terminal timestamp retention was
repaired and regression-tested in the authorized phase. A shutdown before activation does
not cancel pending Setup prompt futures the way `cancel_setup` does; and `cancel_attempt`
appends its reservation warning outside the lifecycle lock. Two state fields have no
reader in source and need an owner decision before removal: `default_intertrial_gap_ns`
(still validated from the configuration file) and `DeviceState.completed_camera_operation`
(only tests read it). `transport/ingress.py` has no direct test.

Recovery and native acceptance cases have one home in the
[rig worklist](rig-verification.md#runtime-recovery-and-regression-coverage).
Missing required participants fail explicitly; this report does not establish an
operational experiment or authorize firmware, GUI or tracking implementation.

## Cohesion and test organization

Reviewed size exceptions under ARCH-002: controller `assembly.py` (519 lines,
flat component wiring; `runtime.py` is now 422 lines),
supervisor `shutdown.py` (505 lines, retained intent/deadlines and ordered cleanup,
delivery and operation outcomes), shared `incidents.py` (topology/proof
checks) and native `jobs.py`/`security.py` (Windows ABI and exact handle ownership).
These boundaries do not permit unrelated additions; extract a separable responsibility
before extending them. Acquisition exceptions belong in its report.

Supervisor native exit ordering and final absence inspection now live in the focused
`process_exit.py`; it receives the registry, native interface and shutdown state,
and returns evidence without changing coordinator outcomes. The small
`worker_context.py` owns the work-scope comparison shared by registration, discovery and
transport. No
whole-runtime dependency or duplicate authoritative state was added. Registry,
worker-transport and shutdown regressions extend their existing behavior modules;
no additional test module was needed.

Controller `lifecycle/interruption.py` is now 444 lines (previously 525); finalization
outcomes and cleanup remain there, while the 360-line `metadata/coordination.py` owns
writer closure. Removing the lifecycle owner's direct metadata-state dependency
keeps one authoritative state owner. Camera retirement shares the existing device
state and adds no wrapper module. Regressions extend the existing metadata, safety,
camera-evidence and lifecycle behavior modules; admission tests use the real
retention component instead of a stale method-only stub.

Tests are grouped by behavior. The 2026-09-30 consolidation reduced 105 test modules
to 67 (acquisition 40→22, controller 37→23, supervisor 10→7, shared 7→7,
platform 7→5, launcher 2→1, client 2→2). All 24 fix-named modules were absorbed or
renamed by responsibility; test-to-test imports were removed. Controller's now
533-line lifecycle-command module retains its common interruption/finalization
fixture, including the regression that failed trial metadata cannot skip sealing;
acquisition's 591-line worker-foundations module was not extended.

The 2026-10-01 cross-backend ARCH-002 sweep rechecked controller and supervisor
package boundaries alongside acquisition, Visual Stimulus and Tracking. It found no
additional safe controller/supervisor extraction; retained size exceptions and
unresolved observations remain as recorded above.

## Verification evidence

Earlier rows retain historical results and were not rerun during report consolidation;
their uncommitted snapshots had no recorded source revision. The supervisor
simplification rows describe newly executed checks, based on HEAD
`7ae3767cea92bf7af94153d417e40df997e1fd05` plus pre-existing and new working-tree changes.
[Raw evidence](runtime-evidence-2026-09-30/supervisor-simplification.txt) retains commands,
results, scope and SHA256 hashes of supervisor source/tests; HEAD alone does not
identify that snapshot. Concurrent Visual Stimulus backend renaming was preserved;
the evidence includes revalidation and a refreshed source/test manifest after that
rename. Counts describe each run's snapshot. The second supervisor pass has its own
[raw evidence](runtime-evidence-2026-09-30/supervisor-simplification-pass2.txt)
(same HEAD, later working tree, new source/test hashes).

The controller simplification uses the same HEAD plus the dirty working tree.
[Controller raw evidence](runtime-evidence-2026-09-30/controller-simplification.txt)
records increment results, final commands, an unchanged source/test SHA256 manifest,
and the separate acquisition-preview fixture failure encountered by broader checks.
That fixture failure was subsequently corrected and verified in the
[acquisition simplification pass](acquisition.md#verification-record).

| Date / scope | Command or method | Recorded result and limits |
| --- | --- | --- |
| 2026-09-30, portable run before backend audit | `python -m pytest tests -q`, asyncio auto | Controller/supervisor/shared/platform/launcher/client passed except seven acquisition-loader-blocked tests; native Windows skipped. The later loader correction was not a rerun pass. |
| Same portable snapshot | `ruff check src tests tools`; `ruff format --check src tests tools`; `mypy --platform win32`; `python tools/check_backend_boundaries.py` | Passed; 323 source files typed; zero boundary violations. |
| 2026-09-30, backend source audit | Ruff lint/format, Windows-target mypy, boundary checker, Python compilation and TOML parsing | Passed: 439 formatted files; 325 source/regression modules typed; 269 backend modules, zero violations; 15 TOMLs parsed. |
| Same audit | `pip check`; wheel/sdist build with `--no-isolation`; pytest collection | Passed dependency consistency/build; 483 cases collected including 22 encoding/GPU regressions. No test bodies run. Driver/SDK compatibility untested. |
| 2026-09-30, test consolidation | Collection and AST comparison against pre-consolidation snapshot | All 483 collected cases, names, markers and fixture dependencies retained; 451 test functions, 678 top-level definitions and 3,218 module-binding comparisons preserved subject to reviewed helper merges/renames. Native/ring platform skips unchanged. |
| Same consolidation | Ruff, compile, Windows-target mypy, boundary checker | Passed: 74 test/support modules compiled; 323 runtime and 346 combined runtime/acquisition-test modules typed; 269 backend modules, zero violations. No test bodies run. |
| 2026-09-30, supervisor simplification increments | `.venv/bin/python -m pytest tests/supervisor -q -m 'not windows and not rig'` | Passed: registry increment 64, worker increment 96, shutdown increment 106 cases (audit baseline 55). Covers rejection/replay, work scope, stale/capacity-bound channels, independent delivery, native-boundary ordering/deadlines and distinct cleanup/exit outcomes. |
| Same refactor, integration | `pytest tests/supervisor tests/launcher tests/shared tests/client tests/controller/test_shutdown_handoff.py -q -m 'not windows and not rig'` | Initially 177 passed and two client RPC fixtures were blocked by sandbox loopback binding; network-permitted retry passed both. After concurrent renaming, reran the 177 non-listener cases and the two authenticated RPC cases separately: all passed. Combined coverage 179 passing cases; no native Windows/rig run. |
| Same refactor, static/source review | Scoped Ruff lint/format and `mypy --platform win32 src/cephvr/supervisor`; `python tools/check_backend_boundaries.py`; AST comparison of extracted native exit body | Passed: 30 source/test files formatted, 21 supervisor modules typed, 390 backend modules with zero boundary violations. Native exit control flow matches the pre-refactor working copy after dependency/backend-role renaming, excluding result packaging. Shutdown's remaining size warning is assessed above. |
| 2026-09-30, supervisor simplification second pass | `pytest tests/supervisor tests/visual_stimulus/test_transport.py -q -m 'not windows and not rig'` after each of four increments; scoped Ruff lint/format, `mypy --platform win32 src/cephvr/supervisor`, boundary checker, `git diff --check` | 110 passed throughout (106 supervisor plus 4 transport); 20 supervisor modules typed; 450 backend modules, zero violations; supervisor source 5,208 to 5,013 lines. Only `shutdown.py` (505) still exceeds the size warning. No test assertion changed; edits limited to renamed methods/modules and fake-port no-ops. |
| Same pass, integration | `pytest tests/supervisor tests/launcher tests/shared tests/client tests/controller/test_shutdown_handoff.py tests/tracking/test_runtime.py tests/visual_stimulus/test_transport.py -q -m 'not windows and not rig'` | 188 passed (three repeats). One earlier run had a tracking heartbeat-catalogue test fail while another session was editing the Tracking runtime; it reproduced against the pre-refactor supervisor and passes with the current tree (see raw evidence). No native Windows/rig run; E15 checks remain open. |
| 2026-10-01, controller simplification second pass | `pytest tests/controller tests/client tests/shared tests/launcher tests/supervisor tests/visual_stimulus/test_controller_communication.py -q -m 'not windows and not rig'` after each of seven increments; scoped Ruff lint/format, `mypy --platform win32 src/cephvr/controller`, boundary checker, `git diff --check`; whole repository `pytest tests -q -m 'not windows and not rig'` at the end | 379 passed throughout (200 controller cases collected before and after); whole repository 736 passed, 6 skipped, 2 deselected; 74 controller modules typed; 453 backend modules, zero violations. Controller source 16,494 to 16,297 lines (72 to 74 modules: `receipts.py`, `setup_resolution.py`), tests 7,069 to 6,991. No assertion changed; edits limited to removed dead fixtures/kwargs and shared fixture imports. `assembly.py` (519) remains the only controller size advisory. No native Windows/rig run; E15 checks remain open. [Raw evidence](runtime-evidence-2026-10-01/controller-simplification-pass2.txt). |
| 2026-09-30, controller simplification increments | `.venv/bin/python -m pytest tests/controller -q -m 'not windows and not rig'` | Baseline 187 passed; lifecycle/metadata regressions 195 passed; camera retirement regressions 199 passed. Final integration adds one finalization regression, bringing controller coverage to 200 cases. |
| Same controller refactor, integration | `pytest tests/controller tests/supervisor tests/shared tests/launcher tests/client -q -m 'not windows and not rig' --ignore=tests/client/test_controller_rpc.py`; separate network-permitted RPC run | 374 passed, plus two authenticated controller RPC tests passed: 376 total. Original deadlines, independent interruption delivery, metadata closure ordering/failure and camera result retention are covered. Native Windows/rig acceptance remains pending. |
| Same refactor, broader acquisition checks | Added `test_manual_devices.py`, `test_manual_preview.py`, `test_cleanup_aggregation.py` to the non-listener integration run | 386 passed, one existing acquisition-preview test failed and reproduced in isolation. Its fixture leaves `WorkerPreview.started=False`, so the pause path skips it. Both that test and its acquisition implementation are unchanged from HEAD; no acquisition fix is included here. |
| Same controller refactor, static/source review | Scoped Ruff lint/format, `mypy --platform win32 src/cephvr/controller`, boundary checker, AST comparison against pre-refactor working copy | Passed: 97 source/test files formatted, 72 controller source modules typed, 390 backend modules with zero violations. Extracted metadata closure, interruption delivery and camera-retirement bodies preserve statement order after dependency/deadline-name normalization. This source evidence does not establish rig equivalence. |

The consolidation's initial test-only mypy invocation omitted source discovery;
rerunning with `src/cephvr tests/acquisition` resolved it without suppression.
Earlier modular review compared moved storage classes by AST and lifecycle branch,
lock and await ordering against a working-tree snapshot; review corrected stale
limits injection, shadowed activity handling, warning retention and shutdown text.
This establishes reviewed source preservation, not behavioral equivalence on the rig.

The 2026-09-23 declaration audit compiled control/acquisition Protobuf with isolated
`grpcio-tools 1.84.0` / `protobuf 7.36.2` under `/tmp`; TOML, register revisions and
local links passed. Commands and source revision were not retained. Clock and
controller-loss declaration findings are owned by [host clock](../contracts/host-clock.md)
and [controller health](../contracts/controller-health.md). That historical schema
check is neither current runtime validation nor a second unresolved audit worklist.

Follow [E15](../docs/architecture/system-contracts.md#e15) for lightweight local
implementation/communication tests and native/device/full-workload rig checks.
Execution instructions and retained-result requirements are in
[rig verification](rig-verification.md#execution-and-results).
