# Acquisition configuration, preview and PFS control

Derived from [E07](../../docs/architecture/experiment.md#e07),
[E03](../../docs/architecture/gui.md#e03),
[E08/E14](../../docs/architecture/system-contracts.md), and
[A10/A11](../../docs/architecture/acquisition.md).
[Control services](../cephvr/control/v1/services.proto) bind controller/operator
commands and acquisition confirmation; [worker services](../cephvr/acquisition/v1/services.proto)
bind serialized camera editing. These declarations are not runtime implementations.

## Configuration ownership

AcquisitionSettings now carries named behavioral/tracking CameraSessionSettings,
the common ring capacity and requested camera pulse settings. Camera values include
enablement, video saving, device settings/PFS baseline, per-camera FFmpeg arguments
and SDK pool size. Use typed presence: disabled=false and explicitly provided values
must survive default filling; a present empty argument list is not a missing default.
Pin tokens/port are explicit; requested Hz is finite, positive and on the accepted
0.1-Hz grid. Firmware-applied timing remains separate evidence, never silently replacing
the request. Inactive camera values may remain stored for later sessions or preview.

Clients edit through full UpdateConfiguration with the current revision/control
ownership. Pure validation uses the shared lightweight configuration module, without
SDK/device initialization. Device-resolvable feature omissions can remain pending;
active-role assignment, required wiring and invalid numeric/structural settings
cannot be invented. E07 governs validation (reject-and-preserve, no Unvalidated state or rollback), deadlines,
history writes and invalidation of Ready. The GUI does not own another configuration.

Backend-owned PFS snapshots may round-trip unchanged in edits and be restored through
normal reusable history. Replacement camera persistence text must come from validated
SDK import/readback, not an arbitrary client blob used to bypass connected Import.
Transport overrides and timeout settings remain file-only; they are not new operator
fields. [MCU timing](microcontroller.md) defines applied readback separately;
[configuration bindings](configuration-bindings.md) defines the accompanying file
policies and distribution. These declarations do not implement a runnable session.

## Readback and controller confirmation

The coordinator collects a complete expected camera batch for its outstanding Setup
or device command and sends AcquisitionResolutionReport. During Setup this is every
enabled camera; an explicit camera operation reports its target role. An internal
ApplyCameraSettings command batches the changed, currently owned editing/preview
cameras from one validated UpdateConfiguration under one request revision. Ordinary
offline edits do not open devices implicitly; only validated committed values are applied.
Affected previews pause through validation/application and resume only after matching
confirmation. The batch prevents adoption for one camera from making a concurrent
result for the same edit's other camera stale. Include exact
backend generation, work, operation and request revision. Reject duplicates, missing
roles, mismatched device identity or conflicting repeated results. Retain the report
for normal GetRetainedResult reconciliation; receipt alone is not confirmation.

The controller verifies that the operation remains live and its request revision is
current. Overlay only permitted actual device fields/PFS snapshot from matched readback;
never let a device report change mode, enablement, recording flags, trial order,
FFmpeg arguments, file-only controls or another camera's settings. Validate the resulting
configuration and dependent consumers. Commit related camera readbacks atomically;
advance the configuration revision when values change, otherwise keep it. Publish
requested-versus-actual warnings, resolved values and validation state under E07.

Controller then sends ConfirmConfiguration with the original resolution operation,
request revision, final revision and full confirmed acquisition settings. Acquisition
checks the exact retained report and live operation. Only this confirmation permits
its dependent allocation, preview restart or PFS export; every other existing readiness,
MCU, control and lifecycle gate still applies. During Setup, dependent MCU checks must
also succeed before final resource preparation. This message is not Ready or Start.

Duplicate identical reports/confirmations return retained results. Conflicting content
under the same command is rejected. Cancellation, timeout, control loss or a newer edit
cannot be undone by late confirmation. If hardware changed before a stale/failed result
is discovered, expose the observed device state and leave capture/pulses stopped;
do not overwrite newer configuration, claim hardware rollback or continue preparation.
Queries recover evidence without replaying uncertain SDK or file writes or extending
existing deadlines. Public snapshots separate applied device evidence from current
controller configuration, so a pending edit is not shown as already applied.

Use one internal resolution/adoption helper for Setup, editable camera/pulse updates,
Preview and PFS import/export. Parameterize the expected roles, revision and operation;
do not implement separate confirmation caches or validation paths for each workflow.
Keep their existing operation-specific checks and completion evidence. This is code
reuse, not removal of controller confirmation or another handshake.

## Operator commands

ExecuteCameraCommand has one typed kind, camera role, expected configuration revision
and ordinary OperatorCommand. The controller validates lifecycle, control ownership,
cleanup blockers and request shape, then issues a child AcquisitionCameraCommand to
the registered coordinator. GUI/headless clients never issue worker SDK commands.
Attach Preview Viewer requires only its run/viewer context; do not apply camera
settings, refresh SDK capabilities or perform MCU configuration for attachment.
Paths are rig-host paths; Import/Export require one. Other kinds reject a path.
Stop Preview and Attach Preview Viewer require the current preview_run_id; other
operator kinds omit it. Only Attach requires preview_consumer, an exact registered
viewer identity. Start Preview does not select or wait for a viewer.
The coordinator creates a fresh acquisition-run UUID on each actual preview start
or reconfiguration restart and reports it to the controller. Same-command retries
retain that result rather than creating another run. Delayed stops cannot target a
replacement run merely because it uses the same camera role.

| Kind | Completion requirement |
| --- | --- |
| Start Preview | Assigned camera/settings and required pulse outputs validated; readback adopted; needed resources prepared; actual preview running. Session enable/save flags remain unchanged. |
| Attach Preview Viewer | Existing live slot bound to the registered viewer; transfer published and viewer attachment confirmed. No camera restart or capture gate. |
| Stop Preview | Exact preview capture/pulses stopped; SDK connection and preview resources released or explicitly reported unconfirmed. |
| Import PFS | Assigned connected SDK camera successfully loaded/validated the file; common settings and SDK snapshot read back and adopted. |
| Export PFS | Pending current edits applied/read back, snapshot refreshed/adopted, then SDK export to the selected new file completed and closed. |
| Finish Editing | Explicit editing ownership released; close a connection held only for editing. An independently active preview retains its normal connection lifecycle. |

Ordinary device commands are Configuration-only; settings remain locked after Start.
Attach Preview Viewer is also accepted during a session for an enabled session preview
slot, named by the session preview_run_id the coordinator reports at Setup; it never
touches the camera, pulses or trial lifecycle.
Setup's internal preview/editing stop and release sequence is cleanup, not a newly
permitted operator edit during Setup. It must finish within the existing Setup budget.
A completed command is reported through operation state and current device views;
Accepted only means ownership. SDK work never blocks the controller's event loop.

## Camera worker editing

EditCamera is a private child command executed by the existing serialized SDK owner:
Apply Settings, Import PFS, Export PFS or Finish Editing. Before an operation that
changes device settings, coordinator pauses affected preview capture and pulses and
quiesces image access. Preserve other independent previews under A10; shared MCU
changes follow A11's full active-preview mask, not planned session enablement.

Apply/Import return CameraResolvedState through WorkerOperationReport. Import adopts
the file's common camera settings, rather than immediately restoring the old typed
values over them. Later explicit edits take precedence. Cross-model imports rely on
SDK validation and readback; no automatic feature skipping or same-model-only gate.

Export is a two-step child workflow: successful Apply/readback/controller confirmation,
then a separate export child ID using those confirmed values. Do not reapply stale
settings, export cached snapshots offline, or skip the first step when pending edits
exist. Serialize intervening device changes; if the confirmed state no longer matches,
fail the export rather than save different values. Import/Export may open only the
assigned camera on demand without preview, images or pulses. Retain editing connection
ownership across related calls; explicit Finish/Setup/control-loss cleanup ends it.

Export targets a new external file. Existing destinations or write/close failures
produce actionable errors; never automatically overwrite an imported source or label
a partial file a successful export. A lost export reply uses retained command evidence,
not another export attempt. A file failure does not falsely reverse already adopted
camera values. Repeated same-command calls do not re-import or re-export.

Changes after import need not be saved to PFS to run. Keep the nonblocking reminder
under A10; no autosave, original-file reload or extra Setup confirmation gate. Session
logs retain the preset filename and active common settings; omit snapshot contents,
file hashes and new PFS copies. Operational results may identify the requested path
for troubleshooting; persistent preset references use only the filename.

## Current device state and recovery

Acquisition sends a full AcquisitionDeviceStatusReport with generation-local revision,
observation time and exact work/operation. Controller validates order/context before
updating Snapshot.acquisition_devices; normal GetSnapshot never polls a camera. Views
contain open/preview/cleanup evidence, preview run ID, applied revision/settings,
capabilities, identity and last failure. Missing evidence is unknown, not false.
No raw handles, images, PFS contents or per-frame history enters this status view.

Operation result and device state are distinct. A late result for an older command
can confirm cleanup without replacing a newer current view or changing Interrupted.
A successful import need not close editing ownership; a successful command receipt
cannot prove release. Existing resource/lifecycle evidence remains authoritative.
GUI/headless warning and error handling use the common state/event paths.

E03 releases the lease on its WatchState subscription loss. Begin preview/pulse stop
and editing-connection release promptly, with no grace timer. Reconcile already accepted
SDK work under existing deadlines before closing its resources; never free in-use handles.
Reconnection/control reacquisition cannot cancel cleanup or automatically reopen/resume.
An atomic authorized takeover without an unowned interval can retain existing resources;
only the new lease may issue further edits. Experiments remain independent of GUI loss.

[Preview handoff](preview-control.md) binds private start/stop and viewer attachment;
[MCU protocol](microcontroller.md) binds requested/applied pulse evidence. See the
[single worklist](README.md#remaining-decisions-and-implementation-work) for remaining
contracts and separate implementation/verification work.
