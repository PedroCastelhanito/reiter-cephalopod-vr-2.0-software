# Acquisition host implementation review

Status: host implementation and supervising source review completed. Final static
verification is recorded below; behavioral and hardware acceptance remain pending
on the rig. This is not experiment-readiness approval.

[ARCH-001](../architecture.md#arch-001) selects this stage;
[ARCH-002](../architecture.md#arch-002) governs module boundaries. The
[acquisition decisions](../docs/architecture/acquisition.md) and their
[contracts](../contracts/acquisition/README.md) own behavior. The previous
[controller/supervisor review](runtime-implementation-review.md) remains separate.

## Ownership and review

The supervising model establishes interfaces and reviews the implementation.
Luna agents write configuration/serial, camera/buffers/pixels and recording/native
I/O components in separate ownership areas. Dependent coordinator and camera-worker
integration follows foundation review. Existing uncommitted controller/supervisor
work is preserved.

Each coordinator has one authoritative state owner. Feature components receive
specific records, limits, peer ports and callbacks. The camera lifecycle owner
alone accesses camera control; its recording thread owns encoding and frame-log
I/O. The coordinator's serial thread owns the MCU connection. Shared images retain
native pixels; each consumer owns its conversion state and working storage.

Existing Protobuf messages and the camera adapter contract remain the interface
definitions. Integration exposed one omitted private Setup input: the applied MCU
rate required by A08. `CameraWorkerSetupPayload.pulse_configuration` adds the existing
`MicrocontrollerObservation` type without changing existing tags, RPC methods or
experimental output formats. The coordinator forwards controller-confirmed evidence;
workers reject missing/invalid evidence for external-trigger saving. A second missing
internal handoff is formalized under A03/E08: optional `tracking_cleanup` on the existing
`TrackingInputConfirmation` forwards an already validated tracking Cleanup report, so
acquisition can discharge its exact registered consumer transfer. Existing attachment
confirmation keeps its original behavior; release evidence never renews cleanup deadlines.
The private worker Setup also carries its existing `PreparedFunctionScope` declarations
as `owned_functions`. This closes the E06 handoff for future reserved output keys:
workers fence the exact session recording closure, not only the current trial's files.
The coordinator and worker use the same declarations; public RPCs and output formats
remain unchanged.
Authentication, replay retention and bounded admission belong to
transport adapters. Original operation deadlines must survive asynchronous handoff
and retries. No feature component may access a whole runtime back-reference.

Acquisition control assembly uses explicit immutable memory limits: at most 1,024
retained commands, a byte ceiling of the larger of 64 MiB or four shared maximum
messages, and a 64 KiB ordinary-result reservation. Camera resolution/PFS operations
reserve the shared maximum message size before admission. These implementation
ceilings bound retention and reject overload; they are not rig timing guarantees or
new operator policy choices. The same records and byte accounting must cover
retained evidence rather than maintaining an uncharged second history.
Sixteen records and 2 MiB within that budget are reserved for safety admission;
ordinary work cannot consume them. The review expanded the initial reserve to
cover Stop, terminal pulse evidence, Stopped/Finished, Cleanup and Shutdown in one
bounded recovery sequence. This is an implementation memory budget, not a timing
or hardware-performance claim.

The controller owns the cross-backend trial-completion barrier under E05/E08.
Its next authenticated `PrepareTrial` follows required Finished evidence and durable
trial metadata. Acquisition must match that command to its retained session/trial
sequence and its own prior producer closure before resetting shared rings. It must
not create a second tracking-evidence owner or infer completion from a sealed ring.

The cleanup review follows [E06](../docs/architecture/system-contracts.md#e06)'s
distinction between resource release and successful recording. Reserved future
outputs retain their actual never-started status only with exact ownership and
absence proof. Cleanup acceptance must not weaken normal Finished predicates or
convert failed output data into success.

### Cohesion review

The camera adapter remains the single SDK-facing owner and delegates settings,
features, ROI, transport, metadata, grabs and joint waits. Its size reflects the
required adapter interface rather than combined backend or transport ownership.
The capture-resource owner keeps attachment, reset, seal and release together because
they operate on the same native lifetime; layouts, ring operations and accounting
live in separate modules. The worker executor and RPC service are dispatch and
admission boundaries, with trial stopping, recording completion, preview, health
and reporting extracted into independently constructible components.

The recording session retains one sequencing owner for input, frame-log ordering,
watchdog and durable completion. Frame preparation, process launch, input pumping,
negotiation, synchronization and completion predicates are separate modules. These
are cohesive size exceptions reviewed by responsibility; a line-count threshold
alone neither requires extraction nor exempts later unrelated additions.

The MCU owner sequences one physical serial connection; protocol parsing, byte I/O,
scheduling and async handoff are separate. Trial lifecycle aggregation keeps the
Started/Stopped/Finished evidence join with its retained delivery state; validation
predicates are separate. Acquisition `runtime.py` contains dependency assembly and
thin public delegates; shutdown and authority-loss workflows are extracted. Typed
coordinator records live under `coordinator/state/`; `state.py` is their public export.
These are deliberate cohesive exceptions to size warnings, not permission to add
unrelated responsibilities.

## Dependencies and prerequisites

The `acquisition` extra pins pypylon 26.3.1, NumPy 2.4.4 and pySerial 3.5 from the
rig inventory. These are implementation pins, not a validated deployment lock.
Hardware imports remain lazy. FFmpeg and ffprobe remain externally installed and
resolved through PATH; no tested production FFmpeg baseline is asserted.

Basler API assumptions must be checked against the pinned binding. Missing joint
camera/control wait or GIL support blocks capture preparation under
[capture-wait.md](../contracts/acquisition/capture-wait.md). No polling substitute
or automatic dependency upgrade is permitted. The
[upstream releases](https://github.com/basler/pypylon/releases) document API changes;
they do not establish this rig's compatibility.

Source inspection used the public Windows wheel
`pypylon-26.3.1-cp39-abi3-win_amd64.whl` without installing or executing it. Its
Python wrapper exposes `WaitObjects.WaitForAny`, `WaitObject` handle construction
and `PylonImage.AttachMemoryView`. The matching
[26.03.1 build source](https://github.com/basler/pypylon/blob/26.03.1/setup.py)
enables SWIG thread support. The
[converter typemap](https://github.com/basler/pypylon/blob/26.03.1/src/pylon/pylon.i)
allocates the SDK conversion result internally; the C++ destination overload is
not a Python caller-supplied destination interface. These findings correct draft
binding assumptions; Windows wait results, cancellation and actual conversion
remain unexecuted rig checks.

The joint wait uses the pinned binding's no-index `WaitForAny(timeout)` call and
the existing control-event predicate. This avoids an undocumented Python-to-SWIG
output-pointer conversion while retaining command priority under the
[capture-wait contract](../contracts/acquisition/capture-wait.md).

Basler's [acquisition-stop documentation](https://docs.baslerweb.com/acquisition-start-stop-and-abort)
distinguishes ending acquisition from finishing image readout. Its
[stream-grabber guide](https://docs.baslerweb.com/pylonapi/c/programmingguide)
distinguishes queued buffers from retrieved results. The accepted cutoff/drain
contract therefore requires the prepared delivery bound and terminal stop evidence;
an empty result queue alone cannot establish complete post-cutoff accounting.

The narrow native NVENC capability binding is checked against
[nv-codec-headers n12.2.72.0](https://github.com/FFmpeg/nv-codec-headers/blob/n12.2.72.0/include/ffnvcodec/nvEncodeAPI.h).
Header layout inspection does not prove installed-driver compatibility. Actual
codec, format and dimension support must come from the adopted encoding device,
alongside the installed FFmpeg build's advertised capabilities.

The 2026-09-30 [backend code audit](runtime-implementation-review.md#backend-code-audit--2026-09-30)
corrected malformed-UUID, unsupported-platform and missing-CUDA-API errors in
`platform/windows/nvidia_device.py`. They now use its `WindowsLaunchError` preparation
boundary. `cuInit` remains in the worker that owns FFmpeg after registration
acknowledgement ([Windows launch](../contracts/windows-launch.md)); exact device
selection still follows [SYS-002](../architecture.md#sys-002). The same audit corrected
post-filter NVENC dimension checks, selected-encoder help isolation and numeric
validation, removed obsolete empty configuration sections and consolidated duplicate
helpers. Its static checks and prepared regressions are recorded in that audit;
Windows and rig execution remain pending.

Native pipe review uses Microsoft's
[ConnectNamedPipe requirements](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-connectnamedpipe):
an overlapped pipe requires a valid `OVERLAPPED` structure. Cancellation and cleanup
must retain that structure, its event and buffers until completion is observed.

pySerial cancellation is a request to interrupt I/O, not proof that firmware applied
a command or that transmitted bytes stopped. Matched replies, observed completion
and original deadlines remain necessary; see the
[pySerial cancellation API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.cancel_write).

FFmpeg's [stream discovery API](https://www.ffmpeg.org/doxygen/7.1/group__lavf__decoding.html)
reads input packets to establish stream information. The live negotiation review
therefore checks for a potential circular wait if the writer stops feeding after its
first frame while waiting for output initialization. Negotiation must remain bounded
by existing startup/recording deadlines; successful nonempty closure requires matching
input/output facts. This is a source-based review constraint, not a measured startup
latency or a validated installed FFmpeg behavior.

Unknown trigger pins/lines, firmware capabilities, final camera settings and deferred
rig timing stay unset. Firmware implementation/flashing and other backend runtimes
are outside this stage.

## Verification record

Final local verification (2026-09-30):

- Ruff lint and formatting checks across `src`, `tests` and `tools`.
- Strict Windows-target mypy across runtime sources and the acquisition/touched
  integration tests. The unrelated historical test suite is not claimed fully typed.
- Python compilation, Protobuf generation, dependency-boundary inspection and
  hardware-free entry/provider imports.
- AST-only frame-log field/order comparison against all 12 schema groups and
  parsing of all 17 configuration, contract and project TOML files.
- Wheel/source-distribution build and content inspection, including acquisition
  entry points, exact dependency pins, native helpers and generated bindings.
- Working-tree whitespace and preservation checks against the pre-acquisition
  source snapshot. Existing controller/supervisor work was retained.

These are source/package checks, not execution of the prepared behavioral tests.
The exact final results and transfer artifact are recorded in the rig handoff.
No acquisition behavioral, native Windows or hardware tests have been executed in
this local task. Prepared tests are for the owner's Windows rig under
[E15](../docs/architecture/system-contracts.md#e15); the
[acquisition rig handoff](acquisition-rig-test-handoff.md) records execution instructions.

Review must cover optional-setting presence, exact device assignment, SDK capability
failures, capture cancellation and cutoff membership, native counter discontinuity,
ring overwrite/recheck, resource retirement, queue drops and bounded accounting.
Recording review covers cancellation before T, backpressure/stalls, empty and
all-dropped trials, uncertain synchronization and exact output closure. MCU review
covers bounded parsing, stale IDs, watchdog/reconnect and scheduled stop budgets.
Integration review covers partial launches, stale evidence, authority/worker loss,
cleanup proof and shutdown escalation.

The supervising review accepted the host implementation for rig verification after
correcting partial-launch ownership, evidence admission before mutation, original
deadline retention, concurrent safety fan-out, encoder negotiation/closure and
manual-preview retirement. Components use explicit state records, ports and callbacks;
feature modules do not hold the coordinator runtime.

Cleanup/Shutdown commands retain their own command-local E08 scope while their
canonical requests preserve the exact original target/work. Ordinary commands
cannot reopen finalized work. CleanupReport storage remains charged for each
terminal command's retention window. One separately reserved current-session
cleanup proof survives receipt expiry until the session handoff; expired replay
copies are removed, and an unpublished Setup releases its unused reservation.
`GetRetainedResult` returns its admission and
operation; the existing `GetState` / `ParticipantState.cleanup` field returns the
exact latest retained cleanup proof. No new query schema was introduced.

Local cleanup proof and delivery receipts are separate facts. Configuration becomes
available after exact local cleanup; old session workers must still be retired with
cleanup/process/job proof before sessionless operations. A lost controller or
supervisor receipt cannot erase local evidence or extend the original deadline.
Manual viewer-release receipts have their own reserved transfer lifetime, finalized
at release rather than at the earlier Attach command.

The remaining acceptance work is execution on the Windows rig: run the prepared
component/integration suite, then perform the hardware procedures in
[rig-verification.md](rig-verification.md). Missing device, firmware, wait/GIL,
format or timing prerequisites block the affected operation explicitly. No firmware,
GUI, tracking or VR runtime was implemented in this stage.
