# Backend and control contracts

[architecture.md](../architecture.md) indexes the authoritative records, including
[system contracts](../docs/architecture/system-contracts.md) and [acquisition](../docs/architecture/acquisition.md).
These files translate accepted rules into wire types; they do not add another decision register.

| File | Contents |
| --- | --- |
| [types.proto](cephvr/control/v1/types.proto) | Identities, configuration, lifecycle enums, reports and current-state views |
| [services.proto](cephvr/control/v1/services.proto) | Controller, supervisor and backend RPCs |
| [SpikeGLX control](spikeglx-control.md), [client stub](spikeglx_client.pyi), [spikeglx.proto](cephvr/synchronization/v1/spikeglx.proto), [mapping reference](spikeglx_mapping_reference.json) | E12 controller-owned SDK client (sole client): Setup readback/pulse inventory, writing gate, progress and bounded stop |
| [Operator incidents](operator-incidents.md) | Runtime Continue/Abort decisions, continuation scopes and blocking-failure classification |
| [Controller health](controller-health.md) | Independent supervisor/coordinator monitors, bounded recovery and shared cleanup entry |
| [Host clock](host-clock.md), [helper interface](host_clock.pyi) | Shared integer timestamp API, process compatibility, scheduler and storage bindings |
| [Acquisition contracts](acquisition/README.md) | Acquisition configuration, SDK/worker/resource/encoding contracts and frame-log schema |
| [Policy files](policy/) | Versioned fixed-policy constants per backend (`<backend>_policy.toml`), paired with the operator TOMLs by `policy_version` (E14) |
| [Visual Stimulus contract index](visual_stimulus/README.md) | Declared stimulus, feedback, display and recording contracts, with concrete gaps |
| [Tracking contract index](tracking/README.md) | Initial water/fin pipelines, pose/flow/estimator declarations, preparation, worker leases and compact records |
| [Visual Stimulus continuity contract](visual_stimulus/state-continuity.md) | V07 instance identity, retained state and renderer-local epoch transitions |
| [Data-preparation handoff](data-preparation.md) | Early protected descriptors, input attachment confirmation and acyclic acquisition/tracking/Visual Stimulus Setup |
| [Lifecycle tables](../docs/experiment-control-transitions.md) | State changes, guards and timing; backend evidence requires its concrete bindings |

This is a contract draft. All Protobuf files under `cephvr/` compile together; no runtime server,
client, devices, generated bindings or rig tests are included. Python bindings
are generated during implementation, not checked in as handwritten code. Numeric
tags beyond the explicitly accepted E05/E08 enums are initial schema assignments;
after publication, never renumber or reuse them.

## Scope and unfinished interfaces

Shared control, acquisition, Visual Stimulus, synchronization and tracking declarations have their
owning indexes above. Initial tracking geometry/estimators, dependent settings/channels
and pipeline connections are bound in its catalogue. The [data-preparation handoff](data-preparation.md)
binds the cross-backend Setup metadata path. ARCH-001 and runtime implementation remain
open; current work is contract/architecture review, not coding. No empty extension or generic string grants
permission to send arbitrary scientific data over control RPCs.

Schema-backed JSON fields carry only the exact owning versioned document model, with
strict validation and bounds; they are not open dictionaries or executable extensions.
E04's [central metadata writer](central-metadata.md) accepts exact validated disk
records locally inside the controller. Its bounded background queue reports completion
through the controller event path, not a writing RPC. Snapshot retains local persistence
state and the controller-local output reservation (`Snapshot.reservation`); neither
has an RPC. Retained evidence never retries an uncertain write or extends deadlines.

## Shared implementation helpers

E08 requires common Python helpers used in-process by controller, supervisor, backends
and internal workers. They contain no SDK, renderer, device initialization or GUI code;
there is no helper server, Manager process or cross-process shared command store.

| Helper | Responsibility |
| --- | --- |
| Identity/context validation | Validate registered issuer/target generations, work/operation context, authority and required message presence. Accept the owner's policy/context as input; matching IDs alone never grant authority. |
| Host clock | Use [host_time_ns()](host-clock.md) for all host-time observations; validate the process clock descriptor before operational use. No per-process epoch or cross-process clock service. |
| Health monitoring | Use the [controller-health binding](controller-health.md) for independent process-local silence/recovery tracking and idempotent cleanup dispatch. Monitoring never depends on the data loop or creates a watchdog process. |
| Deadline accounting | Carry original absolute host-monotonic deadlines, ingress timestamps and the earliest applicable cutoff through queueing and nested work. A retry cannot renew a budget; preserve the command's accepted retry policy. |
| Command/results | Keep canonical request/admission/progress/evidence records in the owning process; deduplicate retries, reject changed requests under one ID, retain exact results and reconcile late cleanup without reviving execution. |

Use these helpers directly from small role-specific handlers. Controller progression,
supervisor interruption and backend/device work remain with their owners. Sharing code
does not merge state/authority or serialize independent safety-report deliveries.
The receiver invariants below and owning decisions define behavior; do not reproduce
separate copies per backend. These are implementation contracts, not runtime code.

## Resource registration and cleanup

Before backend Setup, controller registers the exact attempt/session and participant
generations and explicit frozen paired-SpikeGLX fact through preliminary
`RegisterContext`, without claiming final Ready. Absence of that fact is unknown;
it cannot be inferred from the failure cause when the independent emergency report
records an unconfirmed external stop.
During partial Setup, a backend sends `HeartbeatReport` with
`cleanup_resources_revision=0` and an empty complete catalogue. Before creating
each session resource, it sends the next revision with all prior obligations
unchanged plus the planned owner/resource/optional-path obligation and waits for
the supervisor's accepted `ReportHeartbeat` receipt. A heartbeat without the
revision carries no catalogue knowledge; revision replay requires identical full
content. Once revision zero is acknowledged, each subsequent heartbeat repeats the
latest full catalogue and revision so the exact forwarded status remains inspectable.
No obligation may disappear or change at a later revision. Each catalogue
is bounded by the control message limit and the receiver's resource count/byte cap.

Ready and final `RegisteredContext` carry the complete last acknowledged catalogue;
final registration seals it against later additions. A heartbeat with absent
catalogue fields remains unknown to a status reader and cannot establish cleanup.
`CleanupReport.cleanup_resources_revision` matches that catalogue; exact owner/path
release evidence and a fenced cleanup command with stopped trial activity are
required. An empty release list clears only an explicitly known-zero catalogue.
Before dispatching each controller cleanup, CancelSetup or Abort command that can
produce Cleanup, the controller appends its exact target generation/work/child command
ID to `RegisteredContext.cleanup_commands` and awaits an accepted RegisterContext
receipt. Same-work updates preserve prior fences and finalized topology. Supervisor
matches Cleanup's operation to that registered fence or to its own exact issued
recovery cleanup command; an arbitrary report operation ID cannot prove a fence.
Output closure is checked independently. The existing ReportLifecycle route also
carries `LifecycleReport.operation` for exact child-command completion; supervisor
still accepts only top-level backend Cleanup on that route.

## Control lease binding

Every WatchRequest has a fresh watch_id bound to that authenticated client's exact
subscription. It starts as observer; only a claim against its installed current view
can grant control. AcquireControl fails if another lease exists; explicit TakeOverControl
atomically revokes the old generation and grants a new one. Neither claim resumes work,
answers prompts or changes session configuration. Lease-recovery tokens/reservations do not exist.

Serialize claim/release/stream-close with command admission in the existing controller
state loop. Observed loss of the owning subscription immediately frees control and
invalidates its generation; an old or non-owning stream closure cannot revoke a new lease.
Reconnection with the same client ID still needs a new watch_id and explicit claim. No
silent network-loss detection guarantee is implied: this acts on stream/transport failure
observed by the existing connection handling. All not-yet-admitted commands revalidate
authority; accepted commands keep their identity and run independently of that lease.
Idempotent queries/retries cannot revive old authority or turn a new command into a retry.

A one-shot state-changing CLI opens/synchronizes WatchState, acquires unowned control,
submits the command, waits under E02 unless no-wait/needs-input applies, then explicitly
releases and closes. No-wait releases after admission; accepted work continues. Explicit
operator takeover is required to replace another holder. Read-only CLI needs no lease.
Reopened GUIs and reconnects always remain observers until Take control; existing
warning acknowledgement and incident handling remain separate from that claim.

## Message size

Every gRPC client and server uses one maximum message size, `[rpc] max_message_bytes`
in experiment_config.toml (default 16 MiB), read at process startup. The controller
event queue and the central-metadata writer each budget at least four maximum
messages (defaults 64 MiB). Prepared artifacts stay with their producing backend;
control messages carry digest/size references (for Visual Stimulus, PreparedHandle plus a compact
planned-occurrence summary). Setup rejects a configuration or Ready report exceeding
the limit, naming the largest items. Before committing UpdateConfiguration, size its
resulting complete Snapshot with envelope/status headroom and reject an
untransportable candidate, keeping current settings/revision, so no edit can make
reconnect impossible.

## Operator prompts

Typed RespondToPrompt binds the operator, the exact pending prompt and the
Setup/generation. It resolves once and rejects stale, replaced or resolved prompts,
except a valid same-command retry. Prompts survive GUI disconnect; reconnect never
supplies Continue. Runtime incident prompts follow the
[incident contract](operator-incidents.md).

## Receiver invariants

- Reject missing required context, `UNSPECIFIED` lifecycle values, mismatched
  generations, stale configuration revisions and unauthorized commands. Protobuf
  parsing alone does not enforce these rules. Optional presence is not a bypass.
- Preserve the accepted fixed enum numbers. Report identifiers and diagnostics are
  not authorization tokens. Credentials travel only in protected gRPC metadata.
- A command ID identifies exactly one canonical request per process generation.
  The same command ID tracks acceptance, progress and completion; no separate
  operation ID is allocated. Child commands may have their own IDs and parent
  references. Identical retries return retained results; changed payloads reject.
  Querying retained results never authorizes replay of uncertain work.
- Ordinary operator commands require the current control lease. Control claims
  cannot require an already-held lease. Supervisor safety commands use registered
  process authority and remain independent of GUI availability.
- Immediately after accepting `ShutdownApplication`, send the authorized intent
  through supervisor `RequestApplicationShutdown`. Bind the original operator
  command, exact process generations, controller operation and applicable work;
  allow application shutdown without a session. Supervisor admission retains intent
  idempotently; it does not prove cleanup or exit. Retain progress in recovery state
  and status reports. If the controller fails after handoff, the supervisor finishes
  the existing bounded shutdown sequence without resetting deadlines. Expose failed
  handoff rather than inferring that the supervisor received it. Confirmed authority
  loss independently invokes E08 automatic shutdown from the survivor's safety path,
  without a fabricated OperatorContext or waiting for this RPC; notify the launcher.
- `ReportSupervisorStatus` replaces only the complete supervisor-owned projection under
  the [status binding](#supervisor-status-views). Dedicated safety/result reports and
  controller-owned lifecycle/incident evidence remain separate.
- `Setup` targets the current configuration. Once work has IDs, commands/reports
  carry that exact work context. Full application shutdown also works with no
  allocated session. Backend shutdown without a session still targets the exact
  process generation. Role-specific requirements are checked by the receiver.
- `ScheduleTrial` admits a target only; `ReleaseTrial` must validate the same
  retained schedule before authorizing execution. Actual Started evidence is
  distinct from both acknowledgements. Stop, Finished and metadata-sync evidence
  remain separate.
- Stopped evidence retains E11 producer cutoffs separately from activity-stop time.
  `ProducerRecordingEnd.source_id` is scoped to its backend: acquisition uses
  `behavioral` and/or `tracking` for each enabled camera, tracking uses `tracking`
  for its local producer, and Visual Stimulus uses `renderer` for its shared composite-group
  stream. Saving Off does not erase an enabled producer's cutoff. Each entry names
  the exact registered producer generation; duplicate/missing expected entries
  are unconfirmed. Camera `StartedReport` first-callback evidence similarly carries
  the exact enabled `CameraRole` and registered worker identity; the Visual Stimulus and tracking
  evidence arms do not substitute for a camera callback.
  `TrialState.interruption_issued_monotonic_ns` anchors interruption deadlines;
  `actual_end_monotonic_ns` is only the E11 aggregate summary. See acquisition
  [recording lifecycle](acquisition/recording-lifecycle.md) for camera cutoff evidence.
- A successfully released trial enters Running at T, not at report receipt.
  Reporting deadlines and evidence-based `trial_started` logging still apply.
- `ReportLifecycle` uses a typed `oneof` for Ready, Started, Stopped, Finished,
  Cleanup or child-operation completion; reject missing payloads and kinds not
  allowed for the recipient. The
  controller accepts all kinds; supervisor accepts top-level backend Cleanup only.
  Keep urgent interruption, errors and health on their dedicated endpoints.
- Send identical Cleanup evidence independently to controller and supervisor.
  Track delivery separately, validate/deduplicate at both, and never block one
  delivery behind the other's receipt. Stopped/Finished go to the controller only.
- Controller evidence gates normal progression; there is no supervisor acknowledgement
  gate. Supervisor health, controller-local metadata synchronization, session-level
  context registration and other existing gates still apply. The supervisor uses its
  own verified backend Cleanup evidence for recovery state and shutdown; the
  controller sends it no Cleanup.
- The output reservation is controller-local (E04): reserve the namespace during
  Setup; filenames based on actual T are resolved later. Conflict authorization is
  for exact displayed files, and release requires verified backend Cleanup, the
  sealed writer and marker handling. It cannot silently overwrite or force ownership.
  `RegisterContext` does not reserve or release.
- After bounded cleanup exhaustion, activated work is Ended/Interrupted; an
  unactivated attempt is Configuration with cleanup blocked. A Cleanup payload in
  `ReportLifecycle` lets
  the coordinating controller or supervisor verify later resource release and
  closure. Match the registered obligation set and source/work/operation identity,
  not merely a success flag or empty resource list. Update explicit cleanup blockers
  in snapshots/recovery state and clear them only on verified evidence. Do not
  clear errors, start a new session, or reinterpret failed outputs as successful.
- Receiver ingress timestamps decide deadline compliance, before application
  queueing and after context validation. Sender timestamps cannot rescue late
  delivery. Integer nanoseconds represent resolved timing, not new duration limits.
- Reject configuration edits when required pure validation cannot complete successfully;
  warn and preserve current settings/revision. Include disabled-backend settings for
  future editing; session metadata still filters disabled backends and asset directories.
- Late validation can affect only its matching unexpired proposal and current authority/
  configuration/lifecycle. It cannot auto-apply a rejected edit or restore old settings.
- Required health includes worker progress, not just a responsive RPC thread.
  Dormant/disabled workers have no progress obligation.
- `ReportInterruption` is a dedicated supervisor-to-controller safety notification,
  independent of operator control and direct backend interruption. Validate exact
  generations/work and deduplicate by interruption ID. Its original issuance time
  cannot be replaced by receipt time to extend a deadline. It is not stopped/closure
  evidence, does not resume retired work, and preserves unstarted cleanup before
  activation. The controller applies its existing lifecycle and logging rules.
- `ReportHeartbeat` is unary. Controller and top-level coordinators report to the
  supervisor; supervisor reports to controller. Workers use their coordinator's
  private `ReportWorkerHeartbeat`, aggregated into the coordinator's heartbeat.
  Coordinators watch controller/supervisor OS process handles instead of heartbeats
  ([controller-health](controller-health.md)). Delivery to one recipient cannot block
  another. Validate expected source generation/context and use receiver ingress for
  silence detection. Keep the 5 s / 15 s health policy (no recovery window) and
  exclude raw heartbeats from session logs.
  GUI connections, heartbeat receipts and process liveness are not readiness or
  completion evidence. Normal health delivery does not use periodic queries.

## Current-state views and reconnect warnings

`WatchState` is the only streaming RPC. Its first item is a consistent current
`Snapshot`, including configuration values. Subsequent items replace the entire
compact state whenever it changes; the client does not apply patches or replay
events. Reconnect with a new subscription. `GetSnapshot` provides a complete
one-shot query and is not polled during normal operation.

`state_revision` increases within one controller generation. Skipped revisions
are valid; ignore older views. Atomically capture initial state and arrange change
delivery in the controller's state loop so a subscription cannot miss the current
view. Slow clients may receive coalesced views; they must not block experiment
execution. State revisions do not replace command/configuration admission checks.
Keep accepted-command completion results in `operations` for their command-record
retention period; coalescing views cannot hide completion from a waiting client.

`configuration` contains revision/lock/validation state. `configuration_values`
is required in every GetSnapshot response, in the first WatchState item of each
stream, and whenever the configuration revision changes on that stream (E08).
Capture both atomically with the rest of the view; coalescing never drops a
revision-changing item's values. Clients reuse values only from the same stream
and revision. Missing or mismatched configuration invalidates the view; remain
read-only and obtain a fresh subscription. A new stream invalidates pending
UI updates from the old stream. Include current configuration with its validation
status; rejected proposals are not current values. Presence does not establish Setup. Loaded assets,
scientific streams and large generated sequences remain outside snapshots.

A Snapshot contains identities/revisions, configuration validation/lock, cleanup
blockers, session/trial phases/outcomes/timing, participant health/devices,
preparation/output/persistence results, the output reservation, control holder and
available commands, active/retained commands, stop/finalization/shutdown state,
errors/recovery and unanswered prompts, each with evidence times. GetSnapshot copies
controller-known state without polling backends. Disabled participants stay compact;
raw RPC/heartbeats and credentials are excluded.

Reconnect warnings use the Snapshot's retained `errors`, `recoveries` and
`runtime_incidents`, bounded by `[control].max_retained_incidents`, with
`retained_since_monotonic_ns` / `retained_truncated` coverage. There is no separate
history RPC. A controller restart starts fresh; show unavailable coverage honestly.
Scientific data and routine heartbeats are excluded.

## Supervisor status views

ReportSupervisorStatus remains a unary supervisor-to-controller call. Each view contains
all retained supervisor-owned process-health, error, warning, recovery and operation
entries for its registered application/session context. Empty lists explicitly replace
empty sections; there are no removal keys or delta messages. Build one consistent snapshot
outside blocking device/file work, stamp its revision/capture time once, and replace the
controller's supervisor projection atomically only after validation. Each entry still
retains its own source/work identity, including retained older completed work.

Use strictly increasing status_revision within the registered supervisor generation;
newer complete views may skip revisions. An identical repeated revision is idempotent;
same revision with different content is a protocol error, older revisions are ignored.
Validate controller/supervisor generations and context before replacement. On reconnect,
push the newest full view; a gap never requires GetRecoveryState or event replay. That
query remains available for explicit recovery evidence/reservations, not normal polling
or reconstruction of this projection. A fresh process generation never inherits old
revision authority and does not bypass E08's authority-loss shutdown rules.

Coalesce unsent updates to one newest pending view; allow at most one immutable send
in flight. Bound both bytes and retained entries within existing control/message limits,
including envelope overhead. Validate prepared limits before Ready; never truncate an
active error or required operation to fit a message, split a view into partial updates,
or grow an overflow queue. Capacity/delivery failures follow existing E06/E08 limits.
A change triggers delivery; no new periodic status timer or per-frame history. Repeated
unchanged status does not require another revision; normal health observations retain
their established cadence.

Projection replacement cannot overwrite controller-owned session/trial phases, Ready,
output closure, metadata, operator consent or incident history. Absence from a status
view is not proof of resource release, resolution of an incident or command completion.
Completed operations stay queryable under existing retention bounds; urgent errors,
interruption, reservation and lifecycle results keep their dedicated paths. Their delivery
never waits behind a full-view send, and coalescing cannot erase durable event obligations.

## Configuration validation

Each backend supplies a lightweight Python configuration module, shared with the
controller, containing types and pure validators. It must not initialize devices
or import heavy runtime code. Edit validation runs locally outside the controller
state loop under the existing shared deadline. Pure edit validation has no backend RPC. Results identify their component, module version and configuration
revision. A missing/incompatible/timed-out validator rejects the proposal with a warning;
backend process downtime alone is not unavailability of a pure validator. The warning
names the component, field when known, stable failure code and reason, says “Changes were
not applied; current settings are unchanged,” and gives an actionable retry/correction.
GUI/headless clients receive the same result. No confirmation override or automatic retry.

Run validation against immutable candidate values; commit only after success and rechecking
expected revision, current lease and lifecycle lock. Expiry rejects once; late completion
cannot commit. Report candidate issues through the initiating command result/warning,
not as invalidation of the unchanged current configuration. An unchanged valid Ready
state survives rejected edits; successful effective edits retain normal cleanup rules.
History stores only current reusable values, without a rollback section or rejected draft.
Startup/default completeness and Setup compatibility/device/asset checks still apply;
the absence of an Unvalidated-edit state is not a claim that every loaded setting is ready.

Backend Setup still verifies module compatibility, devices, capabilities and assets
and resolves generated values. Module/backend mismatch blocks Ready with an error;
locally valid settings never prove hardware readiness. Typed backend-specific
configuration fields and the Python modules themselves remain unimplemented.

## Managed-process launch contract

E08/A02 assign internal worker launching to the owning backend and FFmpeg launching
to the worker that feeds it (acquisition camera worker, Visual Stimulus rendering worker). A shared helper
registers launch intent before creation and confirms exact identity/generation, owner
and stop/control information before operational work. The supervisor tracks every managed descendant for failure
handling and full shutdown, including when its owner dies during startup.

Each Python acquisition worker sends heartbeats to its coordinator
(`ReportWorkerHeartbeat`) and errors directly to the supervisor using existing report types, plus private loopback gRPC worker
control reachable by its owner and the supervisor. The controller still addresses
one acquisition service. Native FFmpeg helpers are monitored by the worker that feeds
them and tracked for process exit; they do not implement CephVR gRPC/heartbeats.

Private Python-worker endpoints bind OS-assigned loopback ports; confirmed launch
registration provides the bound address and exact process generation to owner and
supervisor. Top-level service ports remain fixed/configured. Worker control/health
threads are separate from blocking data work, with synchronized command handoff
and actual progress evidence independent of heartbeat delivery.

Private acquisition worker services and preparation payloads are declared in the
[worker contract](acquisition/worker-control.md). The shared
[Windows launch contract](windows-launch.md) binds application-wide launcher containment, nested backend jobs and
partial-child identification to PlanLaunch/ConfirmLaunch/GetLaunchState. Backend
resource cleanup uses [shared native mechanisms](native-transport.md), with backend policies
in their owning contracts, including acquisition's
[Windows resources](acquisition/windows-resources.md). Existing RegisterContext registers experiment
context at Setup, Start and session-level updates (not per trial), separately from process launch. No runtime helper is implemented.

## Verification status

The owner selected the rig for full runtime verification under E15; see the
[runtime test handoff](../reports/rig-verification.md). The declarations and
pure checks in this directory remain distinct from runtime tests in `tests/`.
Contract compilation and descriptor inspection only check wire
syntax, type references, RPC inventory, enums and streaming shape. They do not
establish timing, file durability, hardware synchronization or recovery behavior.

Compile from this directory with an available Protobuf compiler, for example:

```sh
python -m grpc_tools.protoc -I . --descriptor_set_out=/tmp/cephvr-control.pb \
  --include_imports cephvr/control/v1/types.proto cephvr/control/v1/services.proto
```

The compiler version and generated-package build are now configured in
[pyproject.toml](../pyproject.toml); see the [development guide](../docs/development.md).
