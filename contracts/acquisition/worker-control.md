# Acquisition worker control contract

Governing decisions: [A02/A03/A10](../../docs/architecture/acquisition.md),
[E05](../../docs/architecture/experiment.md#e05),
[E06/E08](../../docs/architecture/system-contracts.md).
[Messages](../cephvr/acquisition/v1/messages.proto) and
[services](../cephvr/acquisition/v1/services.proto) define the wire types.
These contracts define server behavior, not verified deadline guarantees. See the
[implementation review](../../reports/acquisition.md) for
implementation and validation status.

## Endpoints and direction

| Sender → receiver | Calls and purpose |
| --- | --- |
| Coordinator → exact registered worker | ResolveCameraConfiguration; EditCamera; PreparePreview/StartPreview/StopPreview; SetupSession; PrepareTrial; ScheduleTrial; ReleaseTrial; StopTrial; CancelSetup; Cleanup; Shutdown |
| Coordinator → camera worker | RecordPulseEvidence: grouped ON/OFF observations for bounded drain and the completion line's `pulses` (A07/A11) |
| Supervisor → exact registered worker | InterruptSession; authorized recovery Cleanup; Shutdown, under shared safety authority |
| Coordinator/supervisor → worker | GetState and GetRetainedResult for initial synchronization or reconciliation |
| Worker → coordinator | ReportWorkerOperation for command progress/completion; ReportWorkerLifecycle for Ready/Started/Stopped/Finished/Cleanup; ReportWorkerWarnings for bounded diagnostic aggregates |
| Worker → coordinator | ReportWorkerHeartbeat; aggregated into the coordinator's supervisor heartbeat (E08). |
| Worker → supervisor | Existing ReportError only (E08/O2). Supervisor → worker GetState/GetRetainedResult reconciles lifecycle evidence after coordinator loss. |
| Coordinator → controller/supervisor | Existing logical-backend lifecycle reports, aggregated from required worker and coordinator evidence |

The coordinator hosts its private report service alongside BackendService on its
existing endpoint. Each worker has one registered private endpoint; no extra process,
listener, streaming RPC or scientific-data channel is introduced. Workers remain
owned subprocesses, not additional logical backends. Health/report direction and
safety authority reuse E08; acquisition does not allocate another heartbeat policy.

All calls are unary. Report receipts acknowledge validation/receipt, not readiness,
file closure, durability or authority to advance execution. Required delivery and
recovery use existing budgets; do not add a retry loop that resets them. Worker
lifecycle goes only to the coordinator; if the coordinator is lost, the supervisor
queries the worker's retained evidence directly under E08.

[Empty-video results](empty-video.md) binds recording content/presence/closure evidence
and its narrow completion exception; forward exact values through lifecycle reports.
[Diagnostics](diagnostics.md) binds warning codes, bounded aggregation, complete-view
reports and controller forwarding. [Capture wait](capture-wait.md) binds the existing
control-to-camera-owner command wakeup without adding a camera access thread.

## Identity, admission and results

Require exact worker and owner process generations, camera role, applicable
session/trial context and command ID. Registration establishes authority; matching
text fields alone do not authenticate a caller. Ordinary work comes from the owner;
supervisor safety commands remain independently reachable. Workers never command or
report to each other; capture-to-recording handoff is in-process. Session-independent
shutdown and Configuration device operations may omit work, never process identity.
Read-only queries may address retained ended work; they never reactivate it.

The registered process roles are `acquisition_behavioral_worker` and
`acquisition_tracking_worker`, mapped explicitly to their respective CameraRole
values. Require agreement with WorkerContext.camera. The supervisor uses the
registered launch's child/owner identities and confirmed endpoint, with the
applicable registered work belonging to that launch session, for direct worker
access; it never discovers a worker by process name or substitutes a peer.

A child command has one ID and an optional parent command reference. Acceptance
means ownership of a canonical request, not completed device work. Return the same
admission/result for a retry of that request; reject changed payload under the same
ID. Lifecycle evidence references its originating child command. The coordinator
maps that command to the parent when aggregating reports; it does not substitute
worker evidence for its own required serial/output/resource obligations.

WorkerOperationReport contains shared OperationState and a generation-local uint64
state revision. Increment on visible state changes; compare report revisions only
within the same worker generation and command when merging that command's updates.
A late result for another command remains relevant to cleanup even if newer work
has produced a higher revision. Never regress a completed operation to pending or
replace confirmed evidence with an older query response. Reject conflicting terminal
results rather than treating them as a successful retry.

A failed command reports its failure through OperationState; confirmed operational
errors also use the existing direct supervisor error path without waiting for the
owner. Responsive RPC handlers are not proof of capture, encoding or cleanup progress.
Serialized device/lifecycle owners execute work outside handlers under A02/E08.

## Camera resolution before final Setup

ResolveCameraConfiguration is camera-only. The coordinator pushes the full requested
CameraDeviceConfiguration, file-resolved transport overrides and configuration
revision. It is an internal step of the current authorized device/Setup operation,
not a separate operator command or a new deadline. Capture and pulses stay stopped;
no trial files or final rings are created during resolution.

Successful completion carries CameraResolvedState for that exact request revision.
It includes actual settings, stable device identity, refreshed capabilities, layout,
transport readback and native-metadata availability. Use the
[camera settings contract](camera-settings.md) for validation and PFS precedence.
The coordinator forwards matched results through controller-owned adoption; neither
worker nor coordinator changes authoritative configuration independently.

Resolve all enabled paths and dependent MCU-rate/settings checks before final
controller confirmation. Only then allocate resources against the confirmed
revision and send WorkerSetupSession. Its [Setup/preparation contract](setup-preparation.md)
carries complete role settings and resource descriptors, not merely a revision or
an instruction to fetch configuration. Native resource integration remains open.

Failed or cancelled resolution has no successful resolved_camera payload. Preserve
its descriptive failure/readback diagnostics and clean up under E06; never silently
adopt partially applied values as Ready. Stale completion cannot revive cancelled
Setup, mutate newer configuration or allocate more buffers. Resolution success alone
is neither Setup Ready nor permission to acquire images.

## Lifecycle and reconciliation

The [worker evidence table](README.md#setup-and-per-trial-preparation-payloads) defines each
worker's obligations. Every report contains one evidence kind, exact work/command
context and worker state revision. Stopped seals activity; Finished proves that worker's completion obligations;
Cleanup proves actual registered releases/results. They are not interchangeable.
An empty output/resource list cannot discharge obligations that were registered.

GetState returns a coherent view for the requested worker/work, its state revision,
confirmed configuration revision, active/retained command summaries and latest
lifecycle evidence per kind. It does not poll the SDK, fetch pixels, include per-frame
history or return a PFS blob. A later snapshot cannot invalidate already confirmed
closure for older work retained under its own command.

GetRetainedResult returns the exact command's admission, latest operation result
(including camera resolution when applicable) and retained lifecycle evidence.
Retain the latest cumulative evidence of each kind per command/work. Identical
reports are idempotent; later evidence may resolve Unconfirmed to Closed/Failed and
confirm additional releases under E06. Preserve earlier confirmed results, original
errors and the Interrupted outcome; reject regressions/conflicting confirmed results.
A failed command may still gain late cleanup evidence without becoming successful.
`found=false` means no retained proof; it never permits re-execution of an uncertain
command or clearing cleanup blockers.

Push reports for normal operation. Queries reconcile after lost replies/reports or
communication recovery; no periodic completion polling, device reopening, closure
rerun or automatic session resumption. Retain canonical requests/results for active
work and 300 seconds after confirmed finalization/cleanup under E08. Retention is
in memory; it is neither the session log nor a recovery journal after process crash.
The Interrupted fence and exact registered-context checks still prohibit execution.

## Remaining integration

See the [single acquisition worklist](README.md#remaining-decisions-and-implementation-work)
for contract gaps, hardware inputs, later implementation and explicit rig deferrals.
The declarations above are not runtime or rig validation.
