# Acquisition Setup and per-trial payloads

Derived from [A02/A03/A07–A10](../../docs/architecture/acquisition.md),
[E05/E07](../../docs/architecture/experiment.md) and
[E06/E08](../../docs/architecture/system-contracts.md).
Definitions: [messages.proto](../cephvr/acquisition/v1/messages.proto),
[camera settings](camera-settings.md), [frame buffers](frame-buffers.md).
These declare payloads and validation. Runtime implementation and verification
status belong in the [implementation review](../../reports/acquisition-implementation-review.md).

## Final Setup payload

Each enabled camera has one camera worker (A02). Its CameraWorkerSetupPayload carries:

| Part | Complete role-specific inputs |
| --- | --- |
| Capture | Confirmed device/settings/PFS baseline, file-resolved transport, actual native layout, metadata availability and clock descriptor; SDK buffer count, frame-silence budget and resolved `session_preview_max_hz`. |
| Outputs | Tracking-ring attachment only when a tracking consumer needs this camera; one session PREVIEW slot only when `session_preview_max_hz > 0`. |
| Failure scope | `owned_functions` reuses `PreparedFunctionScope`: this camera's capture, optional recording and exact reserved session output keys. Logical owner is the acquisition coordinator; authorized reporter is this registered worker. Closures are unique, self-inclusive and transitive. Recording includes every affected future output key; capture includes recording and those outputs. These are the same declarations emitted in backend Ready. |
| Recording | Present only when saving: resolved FFmpeg/ffprobe executables, that camera's argument list and recording depth, frame-log/video sync, fragment and stall intervals, recording-queue and pending-record capacities, bounded diagnostic-tail sizes and session-config reference. External-trigger saving also requires `pulse_configuration`, the controller-confirmed existing `MicrocontrollerObservation`; use this role's applied rate, never the requested rate or camera free-running control. |

Use positive integer capacities and nanosecond intervals; preserve scalar presence
(including explicit false for native availability). Reject missing required fields,
unknown enum/policy values, conflicting roles, duplicate attachments and mismatched
scope/revision/layout/process generations. Protocol-fixed policies are enforced by
implementation and the existing owning TOML; do not add unsupported policy switches
to these payloads. File-only values must originate from the controller's resolved
configuration, not worker reloads or operator overrides.

A camera payload carries only its own device and output consumers. Reject manual-
preview-scoped PREVIEW attachments in WorkerSetupSession and WorkerPrepareTrial.
All attached resources bind the confirmed revision in WorkerSetupSession.
Camera settings must match successful earlier readback/adoption; this step must not
silently reapply or adopt new values. SDK support alone does not validate consumer
conversion compatibility. Validate the selected consumer representation and source
precision under [pixel processing](pixel-processing.md). Fail required missing/
mismatched readback, layout or conversion compatibility.

Recording settings retain the independent per-camera FFmpeg argument list; defaults
and validation rules remain A08. Require an explicit output pixel format and validate
source precision, filter conversions and codec/output compatibility under the pixel
contract; incomplete arguments fail with the camera role, setting and reason.
Resolve tools during Setup. Accepted arguments do not prove NVENC/runtime
compatibility; encoder input-format/throughput feasibility remains deferred to the
rig. The fixed frame-log schema comes from
[frame_log_schema.toml](frame_log_schema.toml); device/trial/session identities come
from these typed settings/contexts. The fixed host-clock label comes from the
validated shared [clock helper](../host-clock.md). Native camera-clock provenance uses
the typed [camera-clock binding](camera-clock.md). Unknown optional provenance is
explicit, not a Ready failure; malformed descriptors are rejected. Recording identity
is derived from existing contexts under [pair identity](recording-identity.md).
The session-config reference points to the reserved session metadata, not a copy.

## Resource preparation order

1. Stop/release Configuration preview/editing under A10. Resolve enabled cameras
   concurrently, preserving serialized SDK ownership and the existing Setup deadline.
2. Controller adopts actual settings; revalidate dependent MCU cadence and consumers.
   Required failures cancel preparation rather than substituting a device or settings.
3. Once the final revision/layout is confirmed, create only the needed tracking rings
   and session preview slots, each with its event and ownership record. Send full
   worker Setup payloads without trial files or capture.
4. Workers validate and attach resources, allocate the in-process recording queue and
   private copies/conversion storage, and perform their device/input checks. Return
   exact AttachedResource evidence with Ready only after obligations pass. The
   coordinator waits for every required worker and required tracking consumer, plus
   its own device/control obligations, before backend Ready. A session preview viewer
   is never a Ready requirement.

No partial result, accepted command, live endpoint, successful memory open or another
worker's acknowledgement substitutes for Ready. Failed/cancelled Setup cleans every
partially opened device, allocation and transfer using E06. Late success cannot revive
cancelled preparation. Stage changes and concurrent paths never restart the budget.
[Configuration control](configuration-control.md) defines the public camera readback/
confirmation binding; intermediate readback is not Ready. [MCU protocol](microcontroller.md)
binds applied pulse evidence; [configuration bindings](configuration-bindings.md)
owns complete file-policy routing. Implementation status is tracked in the review.

## Per-trial preparation

The enclosing WorkerCommand supplies exact trial context. Camera preparation lists
its expected session allocation IDs and, when saving, the symbolic MP4 and frame-log
output plans. These must match retained Setup for the required configuration
revision; never accept a replacement allocation without new Setup.

Before dispatch, coordinator verifies prior closure/drain and safe ring reset to the
new trial ID, with admission sealed. The camera worker performs fresh capture-critical
readback, purges stale SDK frames and arms external capture with pulses off. When
saving, it verifies prior file/encoder closure, resets trial-only counters and the
recording queue and prepares fresh recording resources under A08; FFmpeg launches at
ScheduleTrial acceptance. Resource IDs remain stable; new trial identity prevents late
frames from being accepted as the new trial.

Fresh Ready includes the worker's exact attachment evidence for this trial and
confirmed configuration revision. It still requires all device, processing and prior
closure checks; retained handles alone are insufficient. Tracking attachment uses
the resource contract without giving acquisition ownership of its process or choosing
its still-pending public service design. Preview viewer attachment is never a session
Ready requirement.

Output plans identify role, extension and trial but have no final time-derived path.
WorkerSchedule supplies the final prefix/paths and T/end; WorkerRelease authorizes
that schedule under E05. [Recording lifecycle](recording-lifecycle.md) defines the
pre-T launch, cancel cleanup and camera cutoff evidence. No guessed timestamps, dummy
frames, trial writes or changed session settings in PrepareTrial.

See the [single acquisition worklist](README.md#remaining-decisions-and-implementation-work)
for contract gaps, hardware inputs, later implementation and explicit rig deferrals.
The declarations above are not runtime or rig validation.
