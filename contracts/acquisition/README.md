# Acquisition contracts

The [acquisition architecture](../../docs/architecture/acquisition.md) and
[system contracts](../../docs/architecture/system-contracts.md) remain authoritative. These are declared
implementation contracts under E15, derived from A01–A11; no backend, camera driver,
encoder integration or file writer is implemented.

| Artifact | Defined scope |
| --- | --- |
| [Camera adapter](camera_adapter.pyi) | Typed in-worker SDK boundary and buffer lifetime |
| [Camera settings](camera-settings.md) / [wire types](../cephvr/acquisition/v1/camera.proto) | Common feature/capability schemas, readback validation and initial Basler mappings |
| [Empty video](empty-video.md) | Explicit content/presence/closure and allowed completion predicate |
| [Camera clock](camera-clock.md) / [recording identity](recording-identity.md) | Typed optional provenance and matching embedded MP4/frame-log identity |
| [Capture wait](capture-wait.md) | Joint frame/command/deadline wait and nonblocking retrieval |
| [Diagnostics](diagnostics.md) | Stable code catalogue, repeated-warning fields and bounded delivery |
| [Worker control](worker-control.md) | Resolution, result queries, report delivery and reconciliation |
| [MCU protocol](microcontroller.md) | Bounded serial grammar, errors, reported applied frequency and controller evidence |
| [Pixel processing](pixel-processing.md) / [SDK mappings](sdk-mappings.md) | Shared native preparation, explicit formats/transport/errors and Basler conversion |
| [Configuration bindings](configuration-bindings.md) / [runtime fields](../cephvr/acquisition/v1/runtime.proto) | Complete acquisition setting/policy routing and validation |
| [Encoding options](encoding-options.md) | Supported arguments/filters, precision validation and keyframe scheduling |
| [Windows resources](windows-resources.md) | Launch registration, partial-child containment, I/O cancellation and storage sync |
| [Preview handoff](preview-control.md) | Viewer-independent manual/session preview capture and private viewer attachment/release |
| [Configuration control](configuration-control.md) | Camera configuration, readback confirmation and preview/PFS commands |
| [Setup/preparation](setup-preparation.md) | Role-specific settings, attachment evidence and trial preparation |
| [Frame buffers](frame-buffers.md) / [layout](frame_buffers.toml) | Seqlock shared slots, wakeup event, in-process recording queue, reuse and cleanup |
| [Worker service](../cephvr/acquisition/v1/services.proto) | Internal lifecycle/resolution commands, unary reports and queries |
| [Worker messages](../cephvr/acquisition/v1/messages.proto) | Identity-bound control/evidence envelopes and Setup/trial payloads |
| [Recording lifecycle](recording-lifecycle.md) | Pre-T launch/cancel cleanup, producer cutoff, end marker and online closure |
| [Frame-log schema](frame_log_schema.toml) | `_frames.jsonl` header, frame and completion lines |

Schema names, numeric widths and Protobuf tags are initial assignments, not a
published compatibility release. The artifact table identifies declared contracts;
the [worklist](#remaining-decisions-and-implementation-work) separates actual contract
gaps, missing hardware input, later runtime work and explicit deferrals. A Protocol
stub or compiled schema is not an implemented backend.

## Outputs and interpretation

[E04](../../docs/architecture/supervisor.md#e04) owns naming and supervisor-owned
namespace reservation. [A07/A09](../../docs/architecture/acquisition.md) own frame
identity, membership, accounting and crash behavior; the
[frame-log schema](frame_log_schema.toml) owns physical fields. For an enabled,
recorded behavioral camera, one trial writes `SP001_143025_behavioral_cam.mp4` and
`SP001_143025_behavioral_cam_frames.jsonl`.
Tracking-camera files use the `tracking` role. Saving disabled creates none of them.

Host receipt and device timestamps have separate origins. The nth non-dropped
frame line maps to video frame n, but only verified closure establishes recording
success. [Recording lifecycle](recording-lifecycle.md) binds producer cutoffs to the
completion line. [A08](../../docs/architecture/acquisition.md#a08) owns constant nominal-rate
video timing; it is not duplicated here.

## Encoder dependency baseline and verification

A08 targets a documented, tested FFmpeg version. No version number is selected yet.
Record candidate versions during implementation; rig execution checks establish the
tested baseline. Deliberate upgrades require renewed compatibility checks.
FFmpeg/ffprobe discovery stays on PATH; the baseline does not introduce automatic
installation, a bundled executable or session-log dependency lists. When recording is
enabled, a version mismatch is a Setup warning (tested versus installed) recorded in
the session log, with no prompt. Missing tools, known incompatibilities and invalid
encoding arguments still block Setup. An unset baseline is not a tested version.

Continue other acquisition contract work now. Under E15, encoder input-format and
throughput feasibility are explicitly deferred to
[rig verification](../../reports/rig-verification.md), including generated-frame
checks. This does not prove a working encoding mechanism or waive existing timing
requirements; the item needs evidence before the encoding path can be called verified.

## FFmpeg input connection

[A08](../../docs/architecture/acquisition.md#a08) owns the recording thread's raw-frame
stdin writes (`-f rawvideo -pix_fmt -s -framerate`, injected by acquisition at the
nominal rate), independent frame-log/control work and consumption of the in-process
queue. [Recording lifecycle](recording-lifecycle.md) owns startup ordering. Input
format/throughput remains on the [rig verification list](../../reports/rig-verification.md).

## Recording filter validation

[Encoding options](encoding-options.md) owns supported arguments, filter parsing,
precision checks and keyframe scheduling. [Pixel processing](pixel-processing.md)
owns consumer representations. Their declarations do not prove encoder feasibility.

## Shared acquisition and consumer branches

[Pixel processing](pixel-processing.md) owns common native interpretation/conversion,
private consumer representations and source precision. [Frame buffers](frame-buffers.md)
owns independent delivery branches. Shared code does not imply shared mutable images,
a central conversion stage or another camera owner.

## Camera input format coverage

[A01](../../docs/architecture/acquisition.md#a01) selects broad native-format scope.
[Pixel processing](pixel-processing.md) defines required conversion semantics; the
explicit supported-format/provider registry is in [SDK mappings](sdk-mappings.md). SDK enumeration
alone is not a complete pipeline mapping.

## Transport configuration and diagnostic summary

[SDK mappings](sdk-mappings.md#transport-and-metadata-bindings) owns the supported
transport nodes, application ordering and counter extraction.
[Transport summary binding](sdk-mappings.md#transport-summary-binding) defines the
compact diagnostic encoding and its reuse in status. A10 owns file-only transport
policy and A07 owns diagnostic scope; actual interface support remains a rig check.

## Camera adapter obligations

Use the [adapter interface](camera_adapter.pyi) for SDK buffer lifetime and data types,
[camera settings](camera-settings.md) for feature mapping/application, and
[configuration control](configuration-control.md) for PFS, editing and readback adoption.
[A01/A02/A09/A10](../../docs/architecture/acquisition.md) own device identity, worker
loop, source membership and capture lifetime. There is one SDK owner per device.

The serialized grab loop uses the [joint frame/control/deadline wait](capture-wait.md)
then nonblocking retrieval, stamping host receipt immediately after each result.
Check commands and local boundaries between frames even with continuous delivery.
Finish protected SDK copies before releasing the result; consumers never receive a
released SDK view. Native chunk metadata is separate from the image payload.
An empty retrieval alone is not a frame-health failure. Native wait/cancellation
bindings are declared; SDK implementation and rig verification remain outstanding.

## Preview activation, failure and cleanup

[Preview control](preview-control.md) defines viewer-independent capture, attachment,
stop and cleanup. [A10](../../docs/architecture/acquisition.md#a10) owns Configuration-
only display, temporary camera participation, control-loss grace and pulse behavior.
Each explicit manual preview has a latest-frame slot; closing its viewer does not
restart or stop capture. Sessions optionally publish in-trial frames to one slot per
camera at most `session_preview_max_hz` (0 = off); it gates nothing (A03).
[Configuration control](configuration-control.md) owns operator commands.

## Control, lifecycle and reporting

[A02](../../docs/architecture/acquisition.md#a02) owns process layout and endpoints;
[E08](../../docs/architecture/system-contracts.md#e08) owns launch registration,
containment, authority and common helpers. [Worker control](worker-control.md) owns
private commands, reports and reconciliation. Use those contracts directly; this
README keeps acquisition-specific evidence and data-path details below.

### Setup and per-trial preparation payloads

[Setup/preparation](setup-preparation.md) defines complete role-specific payloads,
controller-confirmed revision checks, readback-before-allocation ordering and fresh
per-trial preparation. [Frame buffers](frame-buffers.md) defines attachment evidence,
slot ownership and reset. Workers receive settings/resources directly; they never
fetch a configuration reference or reload TOMLs. Runtime integration remains open.

`WorkerCommand` and `WorkerLifecycleEvidence` bind exact process generations,
work, camera and operation. Require every applicable context; reject an absent
oneof, unknown role, unauthorized source, retired session or mismatched trial.
Shutdown can have no allocated work but must still target the exact worker.
Shared E05/E06/E08 deadlines, admission/result distinctions and idempotency apply.
Do not introduce worker-specific copies of heartbeat or lifecycle timeouts.

| Evidence | Capture thread | Recording thread (saving only) |
| --- | --- | --- |
| Ready | Session: confirmed device/settings and attachments. Trial: fresh checks, purge and external arming with pulses off. | Session: settings/tools and private storage confirmed. Trial: prior closure, recording queue/buffers/encoding plan prepared; FFmpeg launches at ScheduleTrial acceptance under A08, fed no frames before T. |
| Started | Required usable-frame evidence at trial onset | Processing real in-trial frame input or its accounting; not an encoding or durability claim |
| Stopped | Capture stopped and trial input sealed | Not required: buffered in-trial frames may still drain |
| Finished | All capture/accounting obligations and the end marker completed | Complete accounting, successful encoder finalization/exit and completion line and required frame-log/video sync (no MP4 inspection, A07) |
| Cleanup | Confirm release of registered resources | Confirm closure/release or explicitly report failure/uncertainty |

One camera worker reports one combined evidence stream for both threads.

For recording `Started`, use `ActivityEvidence.kind = "recording_input_processing"`
and the host-monotonic instant when the worker first processes an admitted trial
frame or its accounting record. Merely receiving a control command, opening files,
launching FFmpeg or emitting a heartbeat is insufficient. Processing dropped-frame
accounting counts; this must not require an encoded/retained frame and invalidate
A07's all-dropped-trial handling. The Started report retains E05's T + 250 ms deadline;
FFmpeg progress and online finalization/sync/closure remain independently required;
normal file-content validation is external post hoc work under E05/A07.

The capture thread's in-process end marker follows all accounting, bounded retrieval
and purge; it contains final in-trial and excluded-frame evidence. It is separate from
Stopped/Finished and never proves file closure. Closure reports must match the
registered obligation set; an empty output/resource list is not automatic success.
Use existing shared heartbeat/error types: heartbeats to the coordinator, errors directly to supervisor;
report real work progress independently of responsive control threads. FFmpeg has
no CephVR heartbeat; its camera worker's recording thread owns monitoring and diagnostics.

The dedicated [worker service](../cephvr/acquisition/v1/services.proto) binds lifecycle
commands to the existing worker contexts and shared `CommandAdmission`. Acceptance
is asynchronous ownership, not Ready/Stopped/Finished. Cleanup requests cannot reset
Interrupted or release resources without evidence. Supervisor authority is independently
validated for interruption, recovery cleanup and shutdown under existing rules.
[Worker control](worker-control.md) defines unary state/result queries and report
bindings: worker lifecycle reports go to the coordinator; the supervisor queries
retained worker evidence after coordinator loss under E08. Setup/preparation payloads are defined. Native resources, launch registration
and cleanup follow [Windows resources](windows-resources.md); runtime integration
remains unimplemented. Do not infer that context registration launches a process.

## Private image working storage

[A03](../../docs/architecture/acquisition.md#a03) owns preallocation, consumer-local
copies and lifetime rules. [Frame buffers](frame-buffers.md) defines seqlock copy/recheck
and the recording queue; [pixel processing](pixel-processing.md) defines converted storage.
Size local buffers for all simultaneously live images, including the recording queue.
Optional viewer storage never gates capture. SDK/codec allocations remain
outside CephVR's preallocation guarantee.

## Frame transfer and accounting

[Frame buffers](frame-buffers.md) and [frame_buffers.toml](frame_buffers.toml) own
the concrete attachment, seqlock slot layout, in-process recording queue, reset and
retirement contract. No pixels, per-frame polling or duplicate readiness queue enters
control gRPC, and no frame accounting crosses a process boundary.

The recording thread receives frame records and final drop decisions from the capture
thread in the same worker, appending only the complete acquisition-ordered prefix on the
sync cycle or closure. The end marker follows all trial accounting and bounded
retrieval/purge, counting in-trial images (including invalid/dropped) separately from
excluded receipts. Prompt stop reports remain separate. Reconcile unique IDs before
Finished; native counter gaps never create invented received-frame lines.

Queue and pending-record limits remain in acquisition_config.toml. Pending-record
exhaustion is a logging failure; image drops remain A04's separate policy.
[Windows resources](windows-resources.md) specifies I/O cancellation and wrapper
lifetime; implementation and rig validation remain outstanding.

## Frame log and validation boundaries

The [frame-log schema](frame_log_schema.toml) owns line types, fields and text bounds;
[A07](../../docs/architecture/acquisition.md#a07) owns append, sync, closure and crash
behavior. [Recording lifecycle](recording-lifecycle.md) binds the producer end, final
received count and online accounting-completion evidence to the completion line, and
distinguishes runtime closure from external post hoc file validation. There is no
recovery tool: after a crash the fragmented MP4 plays to its last complete fragment and
the frame log is valid to its last complete line; a missing completion line means
incomplete. Checking them is external post hoc work.

## Microcontroller wire contract

[Microcontroller protocol](microcontroller.md) is the concrete wire/error/readback
specification derived from A11. It includes complete CONFIGURE updates, requested
versus applied timing, CAPS freshness and controller confirmation. Board-specific
firmware/resolution, serial scheduling/reconnect code and rig verification remain
unfinished. Manual firmware installation and deferred flashing retain A11's scope.

## Remaining decisions and implementation work

This is the single acquisition completion worklist. The audited rig-independent
acquisition declaration gaps are now bound by the contracts below. Their syntax and
cross-contract consistency have been checked; this is not a runnable or rig-validated
backend. Runtime implementation, actual hardware inputs and explicit rig verification
remain outstanding. Newly discovered concrete conflicts still follow GOV-001.
Resolve any newly discovered contract gap under GOV-001, asking only for a concrete
behavior/guarantee tradeoff. The [rig handoff](../../reports/rig-handoff-2026-09-29/README.md)
supplies inventory and bounded probes; remaining workload/behavior checks stay in the
[rig worklist](../../reports/rig-verification.md). Unknown hardware values are not guessed.

| Work | Status / required next step | Authority |
| --- | --- | --- |
| Shared host clock | Declared in [host-clock.md](../host-clock.md): perf_counter_ns helper, launch/Setup compatibility and fixed frame-log header host-clock label. Camera-native clock provenance is separate. Runtime remains absent. | E05/E08, A05/A07 |
| Preview scope | Declared: manual Configuration preview (including headless) and optional rate-capped session preview slot that gates nothing. Runtime remains absent. | A03/A10 |
| Recording completion/empty video | Declared in empty-video.md, OutputResult and recording lifecycle: final accounting, content/presence/closure and narrow never-created artifact predicate. File validation remains external post hoc. Runtime/rig verification remains outstanding. | A07/E04/E05/E11 |
| SDK/wire completeness | Camera-clock descriptor/transfer/storage declared in camera-clock.md; retained PFS LoadFromString adapter binding declared in camera-settings.md. SDK/runtime/rig verification remains outstanding. | A07/A09/A10 |
| Camera wait and diagnostics | Declared in capture-wait.md and diagnostics.md: event-driven waits, stable codes, aggregation fields and report/reconciliation bindings. Runtime/SDK/rig checks remain outstanding. | A02/A07 |
| Pixel alignment | Declared in [pixel processing](pixel-processing.md#prepared-alignment-and-preview-scaling) and SDK mappings: unchanged native layout, explicit prepared MSB/range, alignment-aware preview and exact-match conversion bypass. Runtime remains absent. | A01/A08/A10 |
| Controller-loss fallback | Declared in the shared [controller-health contract](../controller-health.md); acquisition coordinator and supervisor monitor independently and converge on existing cleanup. Runtime remains absent. | E06/E08/E11 |
| Recording pair identity | Declared in recording-identity.md: matching existing IDs in MP4 tags and frame-log header identity, and argument ownership. Missing identity cannot establish a verified pair. Runtime/rig verification remains outstanding. | A07/A08 |
| MCU schedule boundary | Declared in microcontroller.md and PulseCommandEvidence: B_on=T, B_off=T+duration, independent camera cutoff, bounded serial dispatch/ACK and existing lifecycle deadlines. Physical pulse/exposure matching remains rig/synchronization work. | A11/E05/E11 |
| Camera settings, configuration/PFS/preview control, worker preparation/reporting, buffer slots/attachment, MCU grammar/readback, frame-log line fields | Declared in the artifact table; do not ask these choices again. Runtime remains absent. | A01–A11, E07/E08 |
| Encoder launch and interruption cutoffs | Declared in recording lifecycle and matching wire/schema fields. | A08, E11 |
| Acquisition file-policy binding | Declared in configuration-bindings.md and runtime.proto; controller resolves, workers receive typed values. | E07/E14, A02 |
| Native formats/provider, transport, SDK errors/counters | Declared in sdk-mappings.md; exact connected-device availability/clock/counter semantics remain hardware evidence, not guessed defaults. | A01/A09/A10 |
| Launch/Windows cleanup mechanisms | Declared in windows-resources.md and PlanLaunch/ConfirmLaunch/GetLaunchState, with the existing attachment ledger. | E06/E08, A02/A03/A07 |
| Encoding validation and keyframe scheduling | Declared in encoding-options.md; input-format/throughput feasibility retains its separate rig deferral. | A08 |
| Rig board, trigger pins/lines and device/interface identities | Camera serials/roles and 30/60 Hz owner rates are supplied; Arduino Uno/COM8 is inventory only. Trigger pins/lines, firmware, electrical behavior and final image/transport settings remain unresolved; do not infer them from snapshots. | A01/A10/A11 |
| Python services/helpers, device adapters, firmware, native Windows wrappers, writer code | Later implementation of the contracts; unimplemented is not an unanswered architecture choice or an approved feature deferral. | SYS-003, E15 |
| Encoder raw-input format and throughput | Bounded generated-frame probes are recorded in the handoff; production native conversion, simultaneous full workload and failure behavior remain unverified. | A08/E15, rig verification list |
| Timing/performance, startup-buffer behavior, hardware/electrical checks, crash/durability tests | Rig validation after the main architecture is established; retain evidence and failure limits. | E15 |
| Projector-locked camera pulses and assisted firmware flashing | Explicitly deferred features; no current implementation authority. | A10/A11 |
| Tracking estimator/reset response, VR presentation/lineage and synchronization pulse inventory | Their owning backend stages. Acquisition supplies its accepted interfaces; do not invent their behavior here. | A04–A06, tracking/VR/synchronization records |

Basler conversion and explicit supported FFmpeg argument validation are accepted
under A01/A08. They are no longer unresolved choices.
Static checks never establish hardware, runtime, durability or performance correctness.

## Static verification

From the project root, with the development `grpcio-tools` package available:

```sh
python -m grpc_tools.protoc -Icontracts --include_imports --descriptor_set_out=/tmp/cephvr-contracts.pb contracts/cephvr/control/v1/types.proto contracts/cephvr/control/v1/services.proto contracts/cephvr/acquisition/v1/camera.proto contracts/cephvr/acquisition/v1/microcontroller.proto contracts/cephvr/acquisition/v1/messages.proto contracts/cephvr/acquisition/v1/services.proto contracts/cephvr/acquisition/v1/runtime.proto
```

The current messages compile together. The adapter stub parses as Python and TOML
files parse. These checks do not exercise a frame-log writer, crash behavior or encoding.

## Scheduled serial boundaries (A11)

[MCU scheduled boundaries](microcontroller.md#scheduled-serial-boundaries-a11) owns
serial admission/drain, keepalive reservations and unpreemptible Abort handling.
