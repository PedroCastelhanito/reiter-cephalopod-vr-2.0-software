# Rig verification — outstanding checks

Latest execution: [2026-10-01 Windows audit](rig-audit-2026-10-01/README.md),
baseline HEAD `826984255e0a8469afccbda2dcaf8c642b528b33` plus uncommitted repairs.
Final all-marker suite under the actual High-integrity token, using a dedicated
workspace basetemp: 759 passed, zero skipped or failed. This ran the four previously
privilege-skipped symlink cases; the two POSIX mode tests were explicitly removed,
and native broad-DACL rejection remains covered. The earlier Medium-token
default-temp snapshot (755 passed, 6 skipped) is historical. Native ring binding,
executing-interpreter identity and reservation/recovery repairs pass focused
regressions. These are bounded evidence, not full-workload acceptance. Encoder
compatibility item 5 remains owner-deferred and unchanged. The bounded GUI/SpikeGLX
diagnostic below is later evidence; full session integration remains open. Deferred scientific inputs remain unset. No camera
settings, projection, wiring or firmware changed.

Latest development handoff:
[hardware evidence and implementation constraints](rig-handoff-2026-09-29/README.md).
Camera roles/rates are now owner-confirmed (behavioral 40065509 at 30 Hz; tracking
40747103 at 60 Hz). Final ROI/depth and surface mapping remain deferred; the
SpikeGLX command-server address was saved after the 2026-10-05 SDK readback.
The 2080 Ti format checks and current camera rate limits in
that handoff do not close the full-workload checks below.

Status: rig access established on 2026-09-29. Start with the later
[rig handoff](rig-handoff-2026-09-29/README.md) and
[evidence review](rig-handoff-2026-09-29/review.md); the
[initial audit and repair follow-up](rig-audit-2026-09-29/README.md) retain earlier snapshots.
Owner camera assignments/rates and repaired RTX 2080 Ti availability are established.
Small concurrent encodes and selected three-frame full-resolution encodes passed;
known codec/size failures are recorded. Four outputs are detected on the RTX 5060 Ti
at 60 Hz; physical surface mapping and optical/presentation verification remain open. The
full-workload, optical, electrical and CephVR2.0 lifecycle checks below remain open;
controller/supervisor and acquisition implementation reports record source review,
and Visual Stimulus implementation is in progress. None of these observations establishes full
rig acceptance. See [runtime](runtime.md), [acquisition](acquisition.md),
[Visual Stimulus](visual_stimulus.md) and [tracking](tracking.md) for their current status.
Continue rig-independent decisions under [GOV-001](../architecture.md#gov-001).

This is a verification worklist, not another decision log. Governing rules are
[A08](../docs/architecture/acquisition.md#a08) and
[E15](../docs/architecture/system-contracts.md#e15). These checks are explicitly
tracked separately from installation discovery and dependency smoke checks.

2026-10-05 SpikeGLX preflight: after the ephys machine came online, the rig's
`169.254.91.196` interface discovered `169.254.240.108`. Port 4142 accepted a
TCP connection, and the official SDK connected and read SpikeGLX
`v20251218 api v4.1.3`, `isRunning=false`, `isSaving=false` and data directory
`C:/SGL_DATA`. `getRunName` returned "Run parameters never validated." No
mutation or recording was attempted. The observed address and port are now in
the operator synchronization config; the local GUI draft is independent. The checked-in mapping reference is for
`v20260901`, so E12 Setup and start/stop acceptance remain open. See the
[dated connection evidence](spikeglx-evidence-2026-10-05/README.md).

Later 2026-10-05 SDK preflight read validated settings, an idle run,
Immediate gate/trigger modes and one OneBox stream with 14 saved channels.
After the operator enabled recording at run start, an SDK smoke test started
`CephVR_Test_20261005_163039`, observed saving and increasing samples, and
called stopRun with exact run/data-directory identity. stopRun returned
success, but isRunning stayed true through about two seconds of immediate
checks; a fresh connection then confirmed running/saving false. The precise
stop-confirmation latency, full installed-version mapping, saved-channel
roles and E12 controller lifecycle remain open. See the dated evidence.

Later the controller-owned, read-only SDK diagnostic returned the same server
version, idle/not-saving state, run name and data directory from the saved endpoint.
The managed GUI Test connection action now forwards an authenticated controller
RPC. Its GUI intent and controller RPC authorization tests pass. A later managed
launch displayed a connected Dashboard after concurrent renderer startup fixes,
then exited before the button could be clicked. The agent's UI tool could read
but could not click that window. A retry ended with `JOB_INSPECTION_FAILED`;
the intermittent native process-inspection error remains open. The exact GUI
button response remains unverified. No E12 Setup or recording command was issued.

<a id="managed-device-gui"></a>
### Managed MCU and camera GUI verification

Implementation update: 2026-10-06; physical acceptance remains open under A10/A11/E15.
Use `.venv\Scripts\python.exe tools/generate_contracts.py`, then
`.venv\Scripts\python.exe scripts/start_runtime_gui.py` on the rig. Do not launch a
second application generation while the previous launcher/backends remain active.

1. Take control. In Devices/Microcontroller, scan and select the actual COM port,
   set enabled I/O pins, complete edits with Enter, and wait for controller confirmation.
   Test connection must report the actual firmware/protocol with outputs stopped.
2. Test one enabled output at a time, observing its configured SpikeGLX receiver
   under the existing wiring/voltage checks. Verify Test→Stop→Test, explicit Stop,
   firmware's bounded termination and truthful final edge counts. Projector flip
   observes input edges; it must not drive that pin. A software response is not
   physical waveform proof.
3. In Cameras, refresh, assign Behavior/Tracking roles, select each PFS and confirm
   the detected trigger source. Set requested external rates; configure matching
   MCU pins. Wait for accepted settings, then enable Use. Missing source/rate/pin
   errors must remain explicit; no free-running fallback is permitted.
4. Test enabled: verify separate connection/identity results, no capture or trigger
   pulses, preserved selection, and reported failure for an unavailable camera.
5. Start capture on each camera; confirm usable frames and MCU pulse state. Open
   Preview from Cameras and the Dashboard selector. Close/reopen the viewer while
   capture continues, then Stop capture and verify camera/buffer/pulse release.
   Repeat with both enabled. Settings remain locked while a camera is owned.
6. Exercise loss of control/controller connection during tests/capture, failed PFS,
   missing trigger input and device unplug. Verify stale actions are not replayed,
   incomplete cleanup stays visible, and no false successful result appears.

Retain source revision, logs and receiver evidence with the dated rig results.
Existing operating-point/throughput deferrals below remain separate.

| Check | Evidence required |
| --- | --- |
| Final camera operating points | Under A10, choose the owner-deferred ROI/source/recording precision, then re-read payload, chunks, transport limits and applicable resulting-rate nodes. Resolve behavioral 30 Hz's saved 368,640,000 B/s payload demand versus 360,000,000 B/s limit explicitly; no guessed higher limit or lower cadence. Verify simultaneous externally triggered 30/60 Hz capture with native counters and saved pulse evidence. Different USB host controllers and tracking's 71.803 Hz estimate do not prove sustained rates. |
| Production encoder/tool combination | Under A08/E13/SYS-003, resolve a deliberate compatible FFmpeg/ffprobe pair on the fresh environment PATH. The tested FFmpeg 7.1 / ffprobe 4.3.2 combination is not that deployment baseline. Verify final camera post-filter and Visual Stimulus composite dimensions/depth on the RTX 2080 Ti; retain the handoff's H.264 width/10-bit and AV1 failures. Run both cameras plus composite with rendering/tracking, measuring drops, transfer cost, queue occupancy and finalization. Three static frames and small concurrent sessions do not close this check. |
| Pulse inventory and wiring | Under E12/SYS-004, fill `[pulse_inventory]` from the actual OneBox wiring and verify each camera trigger and the photodiode appears on its mapped saved channel/bit, including edge polarity and a reassigned-role Setup. The Setup check proves configuration only. |
| Visual Stimulus multi-output lifecycle/pacing | Under V15/V20/E05, measure both configured presentation modes with all outputs and full tracking/recording load. Verify per-output Started evidence within the existing 250 ms allowance, Idle transitions and late/in-flight submission handling; software swaps are not optical proof. |
| Visual Stimulus startup Idle | Under V19/E08, check valid saved settings, first-run/missing outputs or profiles, partial window/context failure and cleanup, stale configuration results, Setup reuse/replacement and GUI/headless issue visibility. No guessed black/default calibration or false session Ready. |
| Visual Stimulus geometry, photometry and photodiode | Verify surface/observer geometry, output mapping, calibrated/uncalibrated profiles, marker placement/levels and optical sequence/timing under V15/V22/V23. Include same-level marker boundaries with no edge. |
| Visual Stimulus media decode and profiles | Under V04/V11, verify PNG/TIFF source-depth preservation, JPEG/H.264 interpretation, FFV1 and static GLB supported/rejected profiles, exact media endpoints/VFR selection and independent instances. Exercise aggregate decoder/codec thread and memory limits, callbacks/logging, stale generation rejection, leases, cancellation/hung native work and all four outputs with tracking/recording. No measured throughput or decoder fault isolation is claimed. |
| Visual Stimulus protected assets | Under V04/V13, verify protected streaming sources on the actual storage/decoder combination, independent instance cursors, dependency coverage, external write/replacement attempts and release after cancellation/owner loss. Prepared-memory reuse and relocated replay must use the identified content; no periodic trial-time hashing or archive is introduced. |
| Visual Stimulus linear color and measured tables | Under V04/V21/V23, verify source transfer/range/channels and 8/16-bit preservation, float32 composition/premultiplied alpha/filtering, named clipping flags, curve interpolation and one-time correction. Measure each output's response and actual code precision; check manual/driver/projector conditions, no double gamma, Idle/marker consistency and distinct marker light levels. Independent channel tables alone do not prove cross-projector color matching or spatial uniformity. |
| Visual Stimulus output precision and custom encoding | Under V20/E13, verify requested versus actual RGB8/RGB10 buffers, final code preservation, calibration matching and the real driver/cable/projector path. Exercise the single composite lossy argument validation, actual encoder compatibility at the composite resolution, explicit review conversion and encoder load/failure while preserving live rendering and required state evidence. Under SYS-002, confirm the now-operational RTX 2080 Ti sustains three concurrent NVENC sessions (two cameras plus one Visual Stimulus composite) at planned rates while the RTX 5060 Ti renders/tracks and AMD integrated graphics serves the operator display/GUI. Verify actual adapter identities, explicit FFmpeg device selection and host-transfer costs; the earlier RTX 5060 Ti encoder probes do not validate this placement. Normal runtime still performs no file-content validation. |
| SpikeGLX session control | Under E12 and the [control contract](../contracts/spikeglx-control.md): installed SDK/SpikeGLX versions; command server bound to the dedicated link and firewall admitting only the rig; readback, gate/trigger-mode rejection and run-name collision behavior; startRun-to-saving latency and per-stream sample-count progress (including one stalled stream) to set the writing/no-progress bounds; stopRun completion; timed-out mutation reconciliation; Abort/link-loss behavior including transient recovery, per-stream deadline expiry, late replies and counter reset detection; command-server port (default 4142); stop margin against the final photodiode edge; controller-loss emergency warning naming the run for manual stopping. Acknowledgements are not pulse timing. |

| Visual Stimulus scene composition and geometric correction | Under V02/V15, exercise one arena plus ordered alpha overlays, overlay independence from arena depth, covered-instance continuity and invalid composition rejection. Verify imported mesh coverage/orientation/fold rejection, masks and weighted overlaps, immutable session mappings, photodiode stage order and final-output recording/replay. Establish calibration accuracy through the actual optical path and resource cost on all outputs; no automatic calibration or optical-model guarantee is selected. |
| Visual Stimulus review video and fragmented MP4 | Under E13, verify the constant-rate raw stdin input at the pacing output's nominal refresh sustains the composite resolution, video frame n maps to the n-th admitted render group in the evidence, tile placement/scale matches the recorded layout and admission drops shorten playback without duplicated frames. Exercise fragmented output, keyframe/fragment resource bounds, reader compatibility and drain/sync/close without ordinary-MP4 conversion or file-validation passes. |
| Empty Visual Stimulus review video and explicit depth conversion | Under V12/E13, exercise an all-dropped composite with complete required records, warnings, truthful artifact presence and successful cleanup. Reject empty-input encoder errors, missing-created artifacts and unknown results as normal completion. Verify explicit RGB10-to-8-bit review conversion and rejection of silent negotiation while live output/replay retain their selected precision. Normal runtime does not inspect completed-file contents. |
| Visual Stimulus capture and durability | Verify per-group composite admission, compositing/PBO readback cost on the render thread, recording-thread and FFmpeg throughput within the renderer's process/GIL, ScheduleTrial FFmpeg launch with no frames before T and pre-T cancellation cleanup, required state/metadata retention and failures under V12/V13/V28; test periodic sync, sync failure, an incomplete final JSON line and replay labelled "partial, up to render group N". Preserve Unconfirmed crashed-video outcomes. |
| Acquisition electrical/serial behavior | COM8 Uno protocol-v2 CAPS/STATUS passed after the manual upload. Owner assigned D9 Trial state, D2 Projector flip input, D10 behavioral trigger and D11 tracking trigger; the initial D2 test counted zero edges while the projector was off, and a later local GUI-worker test counted 120 rising edges without independent source observation. Confirm actual destinations, 5 V compatibility and shared signal ground before output tests. Run bounded GUI Test/Stop with physical level/edge observation and repeat D2 with independently observed projector flips. Then verify camera trigger levels/edges, OFF/watchdog behavior, serial latency and DTR/RTS reconnect/reset under A10/A11; do not infer pulse-to-frame edge mapping from host receipts. |
| Acquisition platform bindings | Verify frame-log flush/OS sync on the selected filesystem and SDK/native conversion under A07/A10, and the A03 seqlock slots plus Win32 named event adapter across spawned and independently launched consumers, including torn/lapped-read skips under load and a killed producer. |
| Visual Stimulus feedback freshness | Tune and validate the 350 ms engineering default maximum under [V26](../docs/architecture/visual_stimulus.md#v26) with the full rig workload. Measure host-receipt-to-application age separately from optical latency; verify local stale-result rejection, fresh-result resumption within the same generation, producer-marker generation exclusion and logged hold/resumption. No passing evidence is supplied. |
| FFmpeg raw input path | Verify raw stdin input (`-f rawvideo`, resolved pixel format/size, nominal `-framerate`) for the selected native pixel/conversion paths sustains the planned rates. Confirm video frame count equals non-dropped frame lines, no duplicated/padded frames and a final frame of one nominal period. Record exact tested versions, arguments and camera formats. |
| Consumer precision and encoder compatibility | Verify native unpacking/alignment and source-depth RGB/grayscale preparation under the [pixel contract](../contracts/acquisition/pixel-processing.md), including high-bit-depth sources. Confirm the actual selected codec/output bit depth and color representation; no silent lower-depth conversion or widened 8-bit data labelled original-depth. Preview alone uses the approved display scaling. Keep lossy compression quality separate from representation bit depth. Verify the explicit per-camera output pixel format under A08, including detection of encoder format substitution. Check requested versus actual range/matrix conversion and output tags using known pixel values; tags alone do not prove the conversion. Verify that lower-depth output settings reject higher-depth sources until explicitly compatible arguments are provided. |
| Basler conversion mappings | Exercise the declared [SDK registry](../contracts/acquisition/sdk-mappings.md): native packing/stride, Bayer patterns and edges, private buffer lifetime, effective depth and preview scaling. Record actual device/SDK support; unsupported mappings must fail explicitly. |
| Windows ownership and cleanup | Exercise the shared [acquisition/Visual Stimulus launch contract](../contracts/windows-launch.md) and acquisition [I/O/sync contracts](../contracts/acquisition/windows-resources.md), including owner death at every launch stage, partial handle transfer, blocked pipe/stdin cancellation, process identity reuse, encoder sharing and failed storage sync. Require truthful cleanup blockers. |
| GUI authoring and planning preview | Install `.[dev,gui]` and launch `python scripts/start_gui.py`; follow [frontend review commands](../docs/development.md#dashboard-frontend-review). Check Windows DPI/narrow-window layouts, discovered cameras/COM ports, enabled projector combinations, calibration JSON load/save and pixel offsets/inversions. Build and reload a 200-epoch trial with independent per-projector layers and random/ordered batch values; switch trials and rotate/scrub the two-sided rig preview using local assets. Record latency and errors. This is frontend acceptance, not physical output or live Tracking validation. The existing pacing-default loader failure remains tracked in TODO. |
| GUI Windows display inventory | Compare Projectors table/diagram indices against Windows Settings → Identify on the actual multi-GPU rig, including reconnect, clone mode and changed topology. Verify pixel resolution, retained assignments and explicit query failures. macOS inspection and mocked native API calls do not establish equivalence. See [G01](../docs/architecture/gui.md#g01). |
| Windows venv interpreter process tree | Prepared-image native regression now verifies one live job member, exact launched/executing PID and OS image, fresh venv imports and inherited bootstrap. Verify real managed registration and shutdown after GUI implementation; focused evidence does not establish full application behavior. |
| Runtime finalization boundary | Under A07/E05, verify bounded online accounting, encoder finalization, sync and close without a separate file-validation pass. Measure drain/closure delay before the next trial. Output-content inspection belongs to external post hoc or development verification, never an automatic runtime validator. |
| Empty camera video | Verify the all-dropped case with actual input/muxer behavior: complete frame log with its completion line, truthful artifact presence/closure and grouped warning. Reject encoder failure disguised as empty success, missing-created artifacts and unknown closure; retain Interrupted/health outcomes. |
| MCU host boundary binding | Verify grouped ON/OFF dispatch at host T/end, reserved-channel drain, command/reply timestamps, Abort during an outstanding request and late OFF evidence. Validate report deadlines independently from physical pulse/exposure delay; no early compensation or shifted recording interval. |
| Encoder pre-T launch and cancel cleanup | Under A08, with both cameras enabled, verify FFmpeg launch/registration at ScheduleTrial acceptance completes before T, no frames reach it before T, and first real input, recording-queue occupancy/drops and Started deadlines at T. Measure T-to-first-encoded-input latency (including any encoder initialization FFmpeg defers until its first frame) and confirm zero start-up drops without `recording_startup_allowance_ms`. Exercise pre-T launch/initialization failure (interrupts before release), and schedule cancellation, interruption and release failure before T: the child is terminated, only its own created MP4 is deleted and an unexpected file is kept and reported. Ready alone is not encoder initialization evidence. |
| Producer-local interruption | Delay stop delivery across cameras. Verify each camera worker's recording thread uses its capture cutoff, preserves prior admitted frame records, never substitutes request time, and keeps a missing cutoff unconfirmed. |
| Camera clock provenance | Verify selected source/unit readback, descriptor transfer and frame-log header clock fields against actual models/configurations; include unknown units, missing samples, reset/wrap and source changes. No host-clock calibration or inferred device semantics. |
| Recording identity survival | Verify acquisition-owned tags match frame-log header/session identities through hybrid MP4 writing, normal finalization and interrupted (crash-truncated) writing. Missing/damaged/cross-paired tags must remain unverified; checks here are development work, never a runtime validation pass. |

Exercise both representative generated input and camera recordings on the rig after
the main architecture is established. Keep sample outputs and comparison results as
evidence. An unsuccessful check requires a revised implementation proposal or an
explicit decision change; do not silently loosen timing requirements. Missing/crashed
outputs must remain uncertain rather than being counted as a passing result.

Other runtime, performance and durability verification remains required by E15;
this list records the specific items deferred here, not a completed test plan.

Visual Stimulus declaration closure: the constant-rate review timing (frame n = n-th admitted render
group) is bound in [encoding options](../contracts/visual_stimulus/encoding-options.md#review-timing).
The existing encoder input-format/throughput deferral is unchanged; no successful test
is implied. Full declaration status is in the
[Visual Stimulus contract index](../contracts/visual_stimulus/README.md).

Application shutdown verification under E08: nested job membership for every backend
and partial helper launch; sole non-inherited outer handle; controller, supervisor,
both-authority and launcher failure; graceful cleanup followed by bounded escalation;
no unrelated process termination; unresolved output/SpikeGLX evidence retained at
next startup. Verify actual process absence and machine-guard release separately
from file closure. These checks remain pending rig execution; implementation status belongs in the backend reports.

E06 operator-incident verification remains pending: confirm popup/reconnect/headless
behavior without shifting stimulus clocks; isolate camera/recording/tracking/ephys
failures while retaining truthful missing-data outcomes; abort and new blocking faults
override pending/stale Continue; repeated faults coalesce without losing scope; initial
readiness and healthy-function gates remain enforced; decision persistence and emergency
failure paths work within existing bounds. No runtime UI or fault-isolation behavior is
claimed by the declarations.

## Acquisition terminal accounting and serial stop budgets

- Verify A07/A10/A11 bounded post-cutoff retrieval, countable SDK purge/stop discards,
  optional native counter availability and complete terminal pulse evidence before sync.
- Resolve per-camera exposure/transport/SDK/frame-period drain allowances and verify
  actual stop/report delivery, including Abort behind an outstanding serial request.
  The 100 ms ACK / 50 ms completion reserve within 250 ms is an engineering allocation,
  not measured feasibility. No trial extension, output-file scan or runtime validation
  worker is authorized. See [MCU contract](../contracts/acquisition/microcontroller.md).

## Tracking delivery resets and exact pose geometry

- Verify [A06/T08/T09/T45](../docs/architecture/tracking.md): delivery overflow preserves
  continuous flow/filter state, actual camera gaps rebuild it, retained poses still pass
  age/order checks, and discarded movement is never replayed.
- Verify bounded pose/geometry history and native leases under reset/cutoff/concurrent
  consumers. Measure exact geometry construction's effect on pose cadence and movement
  throughput; no tolerance approximation or performance guarantee is accepted.

- Compare camera receipt → feedback publication and receipt → actual display,
  including upper-tail latency, queue/reset/drop/pose age, valid-result rate,
  CPU/GPU/transfer time and memory under four-view Visual Stimulus plus recording. Compare both
  tracking options on matched recorded inputs and live trials, retaining source
  identity and parameter differences; isolated flow speed does not prove experiment
  performance or scientific accuracy.

## Execution and results

Use a complete current source checkout (`src`, `tests`, `tools`, `contracts`, `config`
and packaging files). A wheel alone omits tests/settings; a remote clone may omit
uncommitted implementation. Preserve rig settings and recordings. Do not copy the
Mac `.venv`, caches or build environment. Use fresh Windows Python 3.11 under
[SYS-003](../architecture.md#sys-003), and close other test runs in the same checkout.

```powershell
.\tools\test_on_rig.ps1 -Install
# Later runs reuse the environment:
.\tools\test_on_rig.ps1
```

The runner installs `.[dev,acquisition]` (including pypylon 26.3.1, NumPy 2.4.4 and
pySerial 3.5). FFmpeg/ffprobe must be deliberately installed on PATH; no production
pair is validated by installation/import. If local script policy blocks execution:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\test_on_rig.ps1 -Install
```

This changes no persistent execution policy. Hardware-marked tests require `-Rig`;
the runner rejects an empty hardware selection. Missing tests and skips are not passes.

| Check | Evidence produced |
| --- | --- |
| Python/package prerequisites | Python 3.11 and generated control bindings import successfully |
| Syntax, Ruff, Windows-target mypy | Handwritten code parses and meets configured static checks |
| Module boundaries | Feature modules avoid runtime/entry imports and private runtime access; size warnings require review |
| Existing contract checks | Pure tracking and Visual Stimulus declarations remain consistent; these are separate from runtime behavior |
| Shared/controller/supervisor unit tests | Identity, bounds, deadlines, leases, evidence, reservations, and isolated failure-path logic |
| Loopback gRPC integration | Actual local controller/client transport, authentication and state-stream behavior |
| Native Windows tests | Creation-time nested jobs, retained exact process identity, kill-on-close, bootstrap pipes, ACLs, durable publication and role guards |
| Package build | Source archive builds a wheel with generated bindings using the installed compiler |

Native tests launch only their own temporary Python children. They do not start
the managed CephVR application, open cameras/projectors, or command SpikeGLX. A
Windows symlink-specific check may skip when the account lacks symlink creation
privileges; inspect the reported reason rather than treating the skip as a pass.

Success means every runner step exits zero and pytest reports no failures or errors.
Any skipped test remains unverified. Collect the actual result before accepting
platform behavior. The PowerShell runner and native assertions have not been executed
on the macOS development host.

The runner also checks acquisition dependencies/tests. Its current script determines
executed scope; newly implemented Visual Stimulus behavior needs explicit coverage and prerequisites
before any acceptance claim. E15 still permits lightweight local implementation and
authenticated communication tests; this guide does not move all tests to the rig.

The runner prints its result directory, by default:

```text
%LOCALAPPDATA%\CephVR2\TestRuns\<timestamp>\
  prerequisites.log
  syntax.log
  ruff.log
  format.log
  module-boundaries.log
  mypy-win32.log
  contracts-tracking.log
  contracts-visual_stimulus.log
  pytest.log
  pytest.xml
  package.log
  packages/
  summary.json
```

The first installation also writes `install.log`. Preserve the entire directory for
review; `summary.json` shows step exit codes and `pytest.xml` records individual
tests and skips. A custom destination can be supplied with `-OutputDirectory`.

Retain `interpreter-process-tree.log` and optional `rig-collection.log` as well.
Record the tested source revision (and uncommitted patch when applicable), platform,
device/build/settings/workload scope, commands, date, outcomes and skips with new
evidence. Update the owning backend report and close only checks supported by results.

Historical transfer identifiers, not claims of current bundle availability:
`dist/cephvr-controller-supervisor-20260929.zip` plus `.sha256` (source without
Git/bindings/caches/environments) and `dist/cephvr-acquisition-20260930.zip` plus
`.sha256` (source, packages and static logs). Regenerate or verify before relying on
an old bundle for the current tree.

## Runtime recovery and regression coverage

- Startup repair requires the prior launcher's durable receipt proving all owned
  processes absent. A missing receipt preserves the blocker; a free lock or missing
  process name does not replace that proof.
- Combined configuration/log inspection is bounded to the configured metadata byte
  capacity (currently 64 MiB). Oversized, corrupt, or incomplete administrative logs
  are preserved and described in a separate recovery report. This path does not
  certify scientific outputs or reconstruct their closure.
- Recovery appends label timestamps as observations by the new application, with
  actual historical end times unconfirmed. Unknown remote SpikeGLX stopping remains
  visible with the saved endpoint/run when available.
- An uncertain recovery append is not retried in the same application. Failed
  durable pointer publication blocks reservation release and another Setup.

| Guarantee | Prepared coverage |
| --- | --- |
| Setup cancellation and Start interruption | `tests/controller/test_safety_regressions.py`, `test_setup.py` |
| Exact/stale/conflicting reports, deadline edges, late Finished | `tests/controller/test_lifecycle_reports.py`, `test_runtime_retention.py` |
| Uncertain metadata completion and reservation ownership | `tests/controller/test_metadata.py`, `test_storage.py`, `test_startup_recovery.py` |
| Control lease loss and takeover | `tests/controller/test_control_leases.py`, `tests/client/test_controller_rpc.py` |
| Partial launches and exact process identity | `tests/supervisor/test_registry.py` |
| Cleanup proof and retained shutdown deadline/escalation | `tests/supervisor/test_registration.py`, `test_recovery.py`, `test_shutdown.py`, `tests/controller/test_shutdown_handoff.py` |
| Replay ownership and bounded report ordering | `tests/controller/test_command_admission.py` |
| Module launch enters the existing CLI | `tests/controller/test_entrypoint.py` |

## Acquisition acceptance coverage

| Area | Evidence to retain || --- | --- |
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
implemented automated test or has passed. The table below identifies prepared tests and the remaining hardware-only checks.

The original 2026-09-30 handoff recorded these sources as unexecuted. The table identifies where
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

## Stimulus implementation handoff — execution procedure

This procedure remains pending Windows execution. Run the automated checks first:

```powershell
.\tools\test_on_rig.ps1 -Install
.\.venv\Scripts\python.exe -m pytest tests/visual_stimulus -q
```

The runner installs the lazy `visual_stimulus` extra (ModernGL/GLFW/PyOpenGL, PyAV,
imagecodecs/tifffile and NumPy), checks imports, and includes the Visual Stimulus tests in the
normal suite. It does not start a projector or prove encoding feasibility. Save
the runner's logs, JUnit, package versions, GPU identifiers and exact Git revision.
The Windows-only protected-source test checks independent read cursors, denied
write/replacement while readers are owned, and mutation after confirmed closure.
Its local non-Windows skip is not a passing Windows result. Run it explicitly with
`.\.venv\Scripts\python.exe -m pytest tests/visual_stimulus/test_windows_resources.py -q`;
the remaining projector, encoder and named-pipe procedures below require their
stated native prerequisites and are not implied by the automated suite.

Before a managed run, supply the accepted display profile with actual device IDs,
four surface geometries, geometric correction files, selected photometric mode and
measured profiles where applicable, Idle color and photodiode patch. Supply the
asset root, authored format-2 program and retained seeds, experiment output root,
and explicit lossy FFmpeg arguments for Save On. Resolve the FFmpeg/ffprobe pair and
RTX 2080 Ti encoder capability checks. Leave unavailable scientific/device inputs
unset; their preparation failures are expected evidence, not reasons to guess values.
The rig must expose the SYS-002 GPU assignments. Closed-loop runs additionally
require the implemented tracking producer and its actual readiness/credit handshake.

Start the application in one terminal, then use the exact controller generation
printed by the launcher in another. The supplied configuration must enable `visual_stimulus`;
camera/firmware inputs are additionally required when acquisition is enabled.

```powershell
$repo = (Get-Location).Path
.\.venv\Scripts\cephvr.exe --software-root $repo --supervisor-config "$repo\config\backends\supervisor_config.toml" --python "$repo\.venv\Scripts\python.exe"
# In a second terminal:
$generation = Read-Host 'Exact running controller generation'
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation --json status
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation configuration --file .\rig-stimulus-configuration.json
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation setup
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation start
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation --json status
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation shutdown
```

Use a short authored program containing image, video, texture and arena epochs,
overlays and instance absence/re-entry. Reuse a video instance across two different
assets/dimensions, then return to the first asset, checking recorded frame selection
and reset generations. Include half-alpha white over black (linear value 0.5),
opaque and masked GLB textures sharing an image, and an intentionally out-of-range
texture. Check per-output clipping coverage and compact Save Off counters, including
delayed diagnostics at Stop. Run it once with Save Off and once with Save
On. Match immutable resolved plans, epoch totals and seeds to the retained recipe;
verify no trial file or frame before released onset. Observe startup/inter-trial/stop
Idle separately from session Ready. Confirm four-view orientation, depth, alpha,
code depth, calibration, photodiode sequence and optical timing with rig instruments.
Inspect evidence/video correspondence, fixed tile dimensions, encoder placement,
storage synchronization and separate output closure results. Retain observations
even when an operation fails; software swap return is not photon timing.

For each failure procedure use a separate short session and record the affected
generation, operation ID, original deadline, retained GetState/cleanup evidence and
remaining OS resources: cancel Setup during protected reads/decode; cancel after
Schedule before onset; interrupt during presentation and during blocked encoder
input; remove storage access; terminate the exact renderer or owning authority.
Require immediate local fencing, bounded shared cleanup and truthful unresolved
resources/output closure. Do not treat a process exit or empty output file as
successful finalization. Exercise empty/all-dropped recordings through the recording
capacity and closure tests, then verify the native encoder's empty-input result on
the rig without inserting dummy frames.

For the analysis handoff, preserve `_stimulus_LOG.json`, `_stimulus_frames.jsonl`
(when Save On), and the matching external assets. Inspect the recipe's complete
resolved plan, fingerprints, calibration/output settings, compatibility/provenance
and uniform layouts. Match frame records to effective state, actual source-frame
selections, output submissions, clipping coverage and recording omissions. Verify
that an interrupted final JSONL line is distinguishable from complete records and
that absent Completion remains visibly incomplete. Save Off retains the recipe only
and cannot guarantee actual-output reconstruction.

Offline replay/export testing belongs to the analysis software once its implementation
is available; this experiment package has no replay command. That acceptance must
exercise missing assets/evidence, partial coverage and exported PNG/index/report
contents against the published contracts, retaining unverified original-pixel equality.
Combined acquisition/stimulus throughput and eventual closed-loop operation remain
separate full-load acceptance procedures.

## Tracking native/runtime handoff (2026-09-30)

Tracking code and lightweight local tests are present; scientific/full-workload
acceptance remains pending. Follow the executable build/smoke-test commands and explicit
procedures in [Tracking status](tracking.md#windows-execution-handoff). The API 2.0 shim
was not compiled on the development machine at that handoff. The 2026-10-01 rig
audit built it and passed the bounded native smoke; preserve the distinction
between automated Windows checks and full camera/model/closed-loop experiment evidence.

- [ ] Projector participation (V15): compare enabled surfaces against all-output
  calibration for each required subset; confirm disabled outputs own no rendering
  windows and surviving viewports/meshes/masks/weights remain unchanged. Retain valid
  pacing selection; test pulse-off with inactive/missing stored target, pulse-on on
  a different enabled display, and verify patch placement/observed edges independently. Verify corrected frustum orientation against measured
  rig corners; local matrix tests do not establish optical accuracy.
