# Acquisition host test handoff

Status: host implementation and supervising source review completed; behavioral
acceptance remains pending on the rig. No acquisition behavioral, native Windows
or hardware tests have been executed during this local task.

[ARCH-001/002](../architecture.md#arch-001),
[A01–A11](../docs/architecture/acquisition.md) and
[E15](../docs/architecture/system-contracts.md#e15) govern this stage. The
[implementation review](acquisition-implementation-review.md) records code and
static-check status; the [rig worklist](rig-verification.md) retains hardware inputs
and workload deferrals. Firmware implementation/flashing and GUI, tracking and VR
runtimes remain outside this stage.

## Transfer and local checks

Transfer bundle: `dist/cephvr-acquisition-20260930.zip`; checksum:
`dist/cephvr-acquisition-20260930.zip.sha256`. The archive contains the current source,
contracts, defaults, prepared tests, built wheel/source distribution and static logs
under `verification/`. The source checkout is the rig-test entry point; the wheel
alone does not include the test suite or deployment settings.

| Local check | Result |
| --- | --- |
| Ruff lint / format | Passed; 412 Python files formatted |
| Strict Windows-target mypy | Passed; 370 runtime/test files in the selected scope |
| Compilation | Passed for source, tests, tools and contracts |
| Dependency boundaries | Passed; 268 backend modules, zero violations; cohesive size exceptions reviewed |
| Protobuf / contract syntax | 18 sources generated; 17 TOMLs parsed; all 12 frame-log field groups matched |
| Hardware-free imports | Six provider/entry modules imported without NumPy, pypylon or pySerial |
| Build / package contents | Wheel and sdist built; all 375 packaged Python/stub files match source bytes |
| Behavioral / native / hardware execution | **Not run locally — pending on the Windows rig** |

Mypy covered runtime sources, all acquisition tests and the touched integration
fixtures/regressions. An exploratory whole-test-tree check also exposed historical
typing errors in unchanged controller/shared/platform tests; this record does not
claim that the entire historical test tree passes strict mypy. The rig runner's
mandatory mypy step targets runtime sources.

## Environment and execution

Use a new Windows Python 3.11 environment in the transferred project. Preserve
rig-specific configurations and existing recordings. Do not transfer the local
`.venv`, caches or generated build products as a runtime environment.

From PowerShell in the project root:

```powershell
.\tools\test_on_rig.ps1 -Install
```

The runner installs `.[dev,acquisition]`, including implementation pins pypylon
26.3.1, NumPy 2.4.4 and pySerial 3.5. Installation and import success do not establish
camera, driver, firmware or encoder compatibility. FFmpeg and ffprobe must already
be discoverable through PATH. No tested production FFmpeg baseline is asserted.

Later runs reuse the environment:

```powershell
.\tools\test_on_rig.ps1
```

Hardware-marked tests require the explicit `-Rig` option. The runner fails that
selection when no such tests exist; a missing test is never a passing hardware
check. Inspect skips and retain the complete result directory, including logs,
pytest XML and `summary.json`.

## Required review of results

| Area | Evidence to retain |
| --- | --- |
| Configuration | Presence versus explicit zero/false, defaults and saved precedence, exact serial assignments, missing or unsupported SDK features |
| Capture | Joint wait wakeups and cancellation, command priority, early/normal cutoff membership, invalid frames and counter discontinuities |
| Buffers | Native layout round trips, overwrite/copy/recheck, exact run binding, retirement and partial allocation cleanup |
| Accounting | Queue drops, accounting exhaustion, empty and all-dropped trials, known versus unknown post-cutoff exclusions |
| Recording | Pre-start cancellation, pipe backpressure/stalls, negotiated format rejection, retained I/O cancellation, exact synchronization and output closure |
| MCU | Bounded malformed replies, stale request IDs, matched capabilities, requested/applied rates, watchdog/reconnect and scheduled stop budgets |
| Lifecycle | Setup cancellation, partial launches, stale/conflicting reports, original deadline boundaries, retained late closure and next-trial barriers |
| Recovery | Controller/worker loss, declared resource catalogues, consumer release proof, cleanup uncertainty and shutdown escalation |
| Manual control | Preview first usable frame, pulse acknowledgement, viewer-independent capture, settings/PFS confirmation and control-loss cleanup |

These rows are acceptance targets, not a claim that every scenario already has an
implemented automated test or has passed. The mapping below identifies prepared tests and the remaining hardware-only checks.

## Prepared test sources

All sources below remain unexecuted in this local task. The table identifies where
to inspect coverage; it does not replace review of the complete rig results.

| Area | Prepared sources |
| --- | --- |
| Configuration and adoption | `tests/acquisition/test_configuration.py`, `test_session_preparation.py` |
| Exact SDK selection and required features | `tests/acquisition/test_camera_adapter_contracts.py` |
| Capture, cutoffs, queue bounds and trial reset | `tests/acquisition/test_worker_foundations.py`, `test_pulse_evidence.py` |
| Ring overwrite, copy/recheck and retirement | `tests/acquisition/test_worker_ring_regressions.py` |
| Encoder negotiation, cancellation and closure | `tests/acquisition/test_recording_negotiation.py`, `test_recording_cleanup.py`, `test_recording_paths.py`, `test_recording_capabilities.py` |
| Retained recording faults and output scope | `tests/acquisition/test_recording_cleanup.py`, `test_worker_admission.py` |
| Serial protocol, cancellation, scheduled budgets and observation provenance | `tests/acquisition/test_microcontroller_protocol.py`, `test_microcontroller_owner.py`, `test_pulse_evidence.py` |
| Admission, partial launch and health | `tests/acquisition/test_transport_admission.py`, `test_coordinator.py` |
| Stop/Interrupt independence and session handoff | `tests/acquisition/test_trial_lifecycle.py`, `test_session_preparation.py` |
| Cleanup closure | `tests/acquisition/test_cleanup_aggregation.py`, `tests/shared/test_cleanup_outputs.py` |
| Manual status and controller cleanup | `tests/acquisition/test_manual_devices.py`, `test_manual_preview.py`, `tests/controller/test_camera_configuration.py`, `test_camera_evidence.py` |
| Windows I/O and supervisor integration | `tests/platform/test_byte_stream.py`, `tests/supervisor/test_worker_outbound_contracts.py`, existing supervisor recovery/shutdown tests |

Real camera wait/GIL behavior, native conversion precision, electrical pulse behavior,
firmware compatibility, simultaneous encoding throughput and crash durability still
require the hardware procedures and evidence in the rig worklist. Controlled component
tests cannot establish those properties.

Missing trigger lines/pins, incompatible firmware, unresolved required image or timing
settings, missing joint-wait/GIL support and unsupported formats must block the affected
operation explicitly. Do not fill them with guessed defaults merely to obtain Ready.
Managed experiment readiness also depends on the separately implemented participant
backends and the full workload verification in the rig worklist.
