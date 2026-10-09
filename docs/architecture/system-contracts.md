# System contracts

[Overview and decision register](../../architecture.md)

Cross-component rules for failure handling, process/control transport, end-to-end
timing evidence, configuration-file conventions and verification. Controller-owned
[lifecycle and preparation](experiment.md) and the
[storage/metadata ownership rules](supervisor.md#e04) are recorded with their owners.

See the root register for backend-specific decisions; wire/schema detail remains in
[contracts](../../contracts/README.md).

## Decisions

<a id="a05"></a>
### A05 — Acquisition-to-Visual Stimulus delay measurement

**Status:** Accepted · **Revision:** 6

- Measure delay from acquisition through tracking to Visual Stimulus output, not only tracking
  wait time. Carry source-frame identity and acquisition timestamps through tracking
  results and the Visual Stimulus outputs that use them.
- The camera worker assigns the source host-monotonic nanosecond timestamp
  immediately on receipt, before application copying or processing; later software
  handling counts as measured delay. This is host receipt time, not exposure time,
  and excludes camera/transport/SDK buffering before receipt. Keep camera-provided
  timestamps separately when available; hardware pulses remain the scientific
  alignment authority (SYS-004).
- A strict decrease of required host receipt timestamps within one camera's ordered
  stream (not across interleaved cameras) is an acquisition timing fault: interrupt
  the session through the existing failure path, stop forwarding affected frames,
  close outputs gracefully where possible and mark the session/trial Interrupted.
  Keep diagnostic evidence; never repair timestamps, reorder frames or silently drop
  and continue. Rounded-video-PTS collision handling is separate; optional
  camera-native counter/timestamp behavior is not a host clock regression.
- Link each applied tracking result, with its source-frame identity and acquisition
  timestamp, to the first Visual Stimulus output incorporating it. Several results may link to
  one output; this does not mean each intermediate state was displayed.
- Keep detailed timing/lineage records in backend output files under the existing
  save settings, never as per-frame histories in session configuration or the
  session-wide log.
- The 250 ms pre-processing frame-age guard is a separate rule. [V26](visual_stimulus.md#v26) owns
  the configurable Visual Stimulus application-age guard and local hold/resumption, which is not
  a physical display-latency guarantee.

**Contract work:** the [feedback contract](../../contracts/visual_stimulus/feedback.md) defines
application observation times and their distinction from output submission/optical
evidence. [Result-to-render layouts](../../contracts/visual_stimulus/evidence-format.md) and
[delivery bindings](../../contracts/visual_stimulus/runtime-bindings.md) are declared; their
runtime providers, V26's numeric limit and rig evidence remain outstanding.

<a id="e06"></a>
### E06 — Stop, interruption, timeout, and recovery

**Status:** Accepted · **Revision:** 77

**Operator commands**

- **Stop after trial** lets the active trial finish, starts no other trial, completes
  finalization and ends the session. It may be withdrawn under E05 (a distinct
  command and audit event); withdrawal cannot override Abort, required failure or
  finalization committed for another reason.
- **Abort now** immediately requests every active producer to stop, starts no other
  trial, closes partial files through normal finalization, marks the trial/session
  and retained partial outputs **Interrupted** and ends the session. Producer cutoffs
  follow [E11](experiment.md#e11); request issuance is not proof of simultaneous stop.
- In Starting, before activation, either command cancels the pending start (no
  activation, no first trial), cleans up prepared resources under the existing
  cancellation rules and returns to Configuration after confirmed cleanup or after
  exhausted cleanup bounds with cleanup explicitly blocked under E05. Metadata
  already written is kept; no trial or Interrupted session is created. After
  activation, normal Stop/Abort rules apply even before the first trial.
- Between trials, either command ends the session without an empty trial or
  relabeling a completed trial. Abort overrides a pending Stop after trial.
- **Shutdown application** is a separate full-system command. In an active session it
  first runs Abort now's interruption and graceful finalization, then terminates
  every tracked CephVR process: all backends including Visual Stimulus, the GUI, the controller,
  and the supervisor last. In Configuration, SettingUp or Ready it cancels or unarms
  prepared work and closes resources without an Interrupted session. Interrupting a
  session alone leaves CephVR running with Visual Stimulus in Idle, except controller/supervisor
  loss, which enters full shutdown under E08.

**Failure classification**

- Before the first trial, every configured backend/device/output must pass its
  existing preparation/start gates. During an experiment, failures are classified by
  whether coordinated execution can continue; a required-output failure alone does
  not force interruption. The
  [operator incident contract](../../contracts/operator-incidents.md) owns
  classification, scope and interfaces; backend references to E06 interruption use
  this policy.
- An isolatable failure or bounded uncertainty gets one updating incident window
  with consequences and **Continue session / Abort session**. While it is pending,
  the current trial and later valid protocol progression keep their original clocks:
  no pause, timeout-default abort or GUI-dependent backend wait. Continue accepts
  only that incident/scope, not future failures or fabricated data. Abort enters the
  existing interruption path and never rewrites prior trial intervals.
- Classify with the exact prepared function/resource loss closure and authenticated
  generation/work-bound fault, fencing/lease and continuing-path observations from
  the [incident contract](../../contracts/operator-incidents.md). Prepared functions
  declare exact backend-scoped E11 lifecycle sources, with E12's controller-owned
  remote recording capability retaining its session-level scope; lost functions close
  only their declared activity/cutoff gates, and worker ownership is checked against the
  supervisor's registered launch ancestry. A code, source
  role, heartbeat or missing proof alone never grants Continue; missing proof is
  bounded by the original E06 recovery deadline, then blocks continuation.
- Stop automatically only when coordinated execution cannot continue: controller or
  supervisor loss (E08), required stimulus presentation unavailable, invalid
  execution identity/clock/schedule, unsafe or unconfirmed ownership that cannot be
  isolated, or loss of bounded authoritative control/incident bookkeeping. Notify
  the operator immediately with the reason and no nonfunctional Continue button.
  Missing device/output evidence alone does not prove such a failure; use the known
  dependency graph and bounded recovery. A new blocking condition overrides pending
  Continue decisions and keeps original stop deadlines.
- An isolated failed acquisition, recording, tracking or ephys function may stay
  unavailable while healthy functions run, using only existing declared behavior
  (for example V25 feedback hold). Fence the affected path, preserve failed/missing
  outputs and log the exact loss scope; never claim normal data completeness or
  change the frozen protocol. Never restart devices/workers, retry uncertain writes,
  invent samples or resume an interrupted trial. Unknown isolation is blocking.
- Permitted drops, timing misses, clipping and invalid-feedback holds stay nonfatal
  under their owning decisions; ordinary per-frame occurrences open no window. A
  distinct condition threatening continuation opens or escalates one incident;
  repeated identical reports update its counts.
- On interruption, end any active trial, gracefully finalize its real partial
  outputs, keep earlier completed trials, record the reason separately from closure
  errors and start no later trial. Never fabricate a trial or output that did not
  start.

**Cleanup and recovery**

- Outside full application shutdown, a required participant stuck after
  finalization and recovery limits is reported as unresolved ownership and left
  running (no automatic kill or restart); new sessions are blocked while resources
  are unsafe.
- A cleanup block on New session, Setup or Start shows an actionable warning naming
  the responsible component/resource or file, what remains unconfirmed, the reason
  and the recovery action. Headless clients see the same blockers; dismissing the
  warning never clears them.
- The coordinating controller or supervisor tracks required cleanup obligations and
  consumes matching completion evidence, including late reports and retained
  results. Each blocker clears automatically only when its obligation is verified;
  the overall block clears only when all are resolved. Never infer file closure from
  a heartbeat, elapsed time or process exit alone. Keep the original Interrupted
  outcome and error history; the operator still requests New session or fresh Setup
  explicitly.
- Cleanup evidence covers stopped work, output/metadata results and release of
  trial/session resources, not exit of normal resident processes or the Visual Stimulus runtime.
  Resource release is distinct from successful recording; cleanup never relabels a
  failed output Closed. A reserved output that never started retains NotStarted with
  confirmed absence only after exact writer/command ownership proves it was never
  created and all possible writers are fenced or released; this discharges cleanup,
  not normal Finished or recording-success requirements. E12 delegates SpikeGLX file
  finalization to the external recorder: require confirmed stopping (isRunning false),
  but do not block reuse
  solely on absent CephVR-verified native-file closure/durability. The
  [SpikeGLX control contract](../../contracts/spikeglx-control.md) owns that
  exception; confirmed errors and unresolved stopping remain failures.
- After failed Setup, or an ended/interrupted session with unresolved resources,
  GUI/headless clients show a recovery view from the supervisor's recovery state:
  each affected backend/process, resource, output path, closure state and last
  error. Its only action, **Retry graceful cleanup**, re-enters the same idempotent
  cleanup/finalization path without reopening recording or changing the trial
  interval. Only the current control-lease holder, verified by the controller, may
  request it; there is no supervisor-local fallback. A process that stays stuck is
  resolved by **Shutdown application**; there is no per-process Terminate action.
- There is no **Restart backend** action. Reusing a failed backend requires a full
  application restart after the existing bounded cleanup/shutdown, then fresh Setup.
  This never resumes the old session or forces interruption of an otherwise
  continuable incident. Reconciled old outputs keep their actual status.
- An accepted Shutdown application command authorizes terminating all tracked
  CephVR process generations after their graceful deadlines; E08's
  controller/supervisor-loss policy grants the same authority automatically, without
  an operator lease or confirmation. Forced exit preserves files, confirmed
  Closed/Failed results and unstarted outputs; missing evidence stays Unconfirmed
  and termination never implies successful finalization. Recovery actions target an
  exact process generation; stale requests are rejected.

**Timeouts and late evidence**

- Confirmed errors and process exits are classified/reported immediately. Ready,
  Finished or registration evidence missing at its initial deadline gets one state
  query (GetState/GetRetainedResult) of the frozen missing set within the one
  shared recovery budget; gRPC reconnects the channel itself. Heartbeat silence is
  loss under E08 with no recovery window. Never reopen devices, restart processes,
  add another attempt or resume an Interrupted session.
- Recovering Finished requires retained proof that the same trial's enabled files
  closed; a connection or Ready report is insufficient, and closure is not rerun.
- Verified late closure evidence for the exact backend/process, trial and output may
  change Unconfirmed to Closed or Failed. Keep the original timeout/error and append
  a recovery result; never rewrite earlier session-log events. The interrupted
  trial/session outcome is unchanged and execution never resumes.
- A Setup timeout before activation leaves the attempt unstarted. During an
  experiment, exhausted Ready, Finished or registration recovery, or health silence,
  enters the incident classifier (isolate where possible, otherwise interrupt).
  Previously confirmed files are unchanged.

| Setting | Default | Owner |
| --- | ---: | --- |
| Setup initial | 60 s | `experiment_config.toml` |
| Cancel Setup cleanup | 10 s | `experiment_config.toml` |
| Per-trial Ready initial | 10 s | `experiment_config.toml` |
| Finished and file closure initial | 30 s | `experiment_config.toml` |
| Supervisor registration (session-level, not per trial) | 5 s | `experiment_config.toml` |
| Shared recovery (one state query after any initial deadline above) | 10 s | `experiment_config.toml` |
| Heartbeat interval / silence (no recovery window) | 5 s / 15 s | `supervisor_config.toml` |
| Metadata completion | 5 s | `experiment_config.toml` |
| Configuration-history save, including queueing | 5 s | `experiment_config.toml` |
| Setup free-space query | 5 s | `experiment_config.toml` |
| Emergency report | 5 s | `supervisor_config.toml` |
| Graceful process exit after Shutdown / OS-terminate exit | 5 s / 2 s | `supervisor_config.toml` |
| Launcher application-shutdown backstop (startup-only; Setup checks it covers the derived sum) | 90 s | `supervisor_config.toml` |

**Backend follow-up:** acquisition progress policies are selected in
[A07/A08/A10](acquisition.md). Other backends define progress evidence in their own
design; runtime monitoring remains unimplemented.

<a id="e08"></a>
### E08 — Processes and control transport

**Status:** Accepted · **Revision:** 169

**Processes and startup**

- Supervisor, controller and GUI are separate Python processes. The launcher starts
  the supervisor and stays alive as containment owner, owning only containment/exit
  deadlines, never session control or replacement authority. Once its service is
  ready, the supervisor launches controller, GUI and top-level backends
  concurrently. Backends own workers, workers own helpers; the supervisor watches
  all descendants. Visual Stimulus registration and containment use the canonical
  backend identifier owned by [V01](visual_stimulus.md#v01).
- One shared launch helper registers planned ownership before creation, then
  confirms exact process generation/identity, endpoint and stop information before
  operational work, covering partial launches and owner failure. Unconfirmed
  children are never Ready or untracked workers. A launch not registered within the
  health silence timeout (15 s) from PlanLaunch is a required launch failure. Health
  values are startup-only settings every process reads at startup.
- A launcher-held application Job Object with kill-on-close contains supervisor,
  controller, GUI and all backend descendants (acquisition, Visual Stimulus, tracking); the
  launcher keeps the sole non-inherited handle outside it. Per-launch jobs stay
  nested with kill-on-close disabled, preserving graceful cleanup after authority
  loss. Verify membership before work; no breakout. At the startup-only
  `application_shutdown_backstop_s` deadline (Setup blocks if it is below the derived
  sum) the launcher terminates remaining members, confirms their absence and closes
  its handle; launcher failure also triggers kill-on-close. The
  [Windows launch contract](../../contracts/windows-launch.md) binds creation-time
  containment, job mechanics, partial-child identification and typed registration.
- A11's controller-owned Arduino CLI uses sequential one-shot native Configuration
  helpers for compilation and upload under the same original operation/deadline,
  planned with an exact parent operation and no session/trial work. Reuse registered
  suspended creation and containment before resume; no Ready/heartbeat is required.
  Normal exit remains retained until controller confirms native process/job/pipe
  and private source/build/image cleanup before starting the next phase. Only this helper role
  accepts the native-helper cleanup flag; supervisor independently requires its exact
  job empty before release. Partial launches remain blockers until reconciled. Cancellation/deadline
  terminates the exact job, including compiler/uploader descendants, without extending the
  original operation budget.
- Acquisition retires a camera worker through explicit exact-owner launch confirmation
  carrying its verified retained successful Cleanup operation and matching resource/output
  evidence before requesting worker shutdown. Supervisor acknowledgement fences only
  that exact worker/work/operation's expected exit; release still requires independently
  verified native process/job absence. The original retirement deadline is unchanged;
  released resources do not turn failed recordings into successful outputs. Queries, exit and liveness alone
  never establish closure; persistent renderer session cleanup does not retire its process.
- Acquisition, Visual Stimulus and tracking reuse the small
  [native transport helpers](../../contracts/native-transport.md) for bounded
  message-mode pipes, mapping attachment, cancellation and resource ownership.
  Queue/drop/credit and storage-sync policies stay with each backend; no service or
  common worker framework is added. Native runtime implementation is pending.
- Machine-wide OS guards allow one application/supervisor/controller/GUI/backend
  role, independent of ports or checkout. Launch admission is serialized, including
  Starting. An interactive duplicate launch waits for the existing owner's
  published endpoint, then asks Y/N before replacing that runtime. Retry an absent
  endpoint within the requester's startup health-silence budget; invalid/unsafe
  records fail immediately. A persistently absent endpoint reports its exact
  runtime path and requires the owning terminal/controller to stop that runtime.
  N/EOF/noninteractive launch leaves it running. Y signals
  only the retained owner-private, generation-specific launcher event. That launcher
  terminates its own application job, verifies empty membership and publishes its
  exact exit receipt before releasing the guard. The requester requires that receipt
  and reacquires the guard before starting; missing endpoint/proof, timeout or a
  competing launcher never permits guessed PID termination or overlapping runtimes.
  This explicit force replacement may lose unfinished output and does not prove
  graceful file closure. Duplicate role requests remain no-ops.
  A missing GUI may be launched explicitly;
  headless clients may coexist. Released guards never prove descendant cleanup after
  a crash.
- The GUI opens in startup/synchronizing state and observes registered health.
  Backends start dormant without opening disabled devices. Always-active Visual Stimulus
  initializes configured Idle from validated saved display settings under
  [V19](visual_stimulus.md#v19); missing/invalid settings leave its outputs uninitialized with an
  actionable issue. Headless startup is the same and still needs explicit Setup and
  Start.
- The [data-preparation handoff](../../contracts/data-preparation.md) binds early
  acquisition/tracking descriptors and confirmations through existing control
  endpoints, transferring metadata before final Ready; it is neither scientific data
  nor execution authority. Preparation handoffs retire with their Setup attempt;
  the same protected endpoint forwards validated tracking Cleanup evidence from
  controller or supervisor to acquisition for exact consumer release. Release
  evidence remains admissible during cleanup without renewing its original budget.
- One controller event loop owns lifecycle state. Device/file work returns results
  asynchronously and cannot mutate lifecycle or block the loop. Ingress timestamps
  are kept for deadline decisions (E05).
- Controller events are bounded to **1,024** and **64 MiB** serialized payload
  (configurable). When full, ordinary work is rejected but interruption stays
  available; losing essential evidence blocks unstarted execution or interrupts an
  active session. No scientific streams enter this queue; it is not a total-memory
  limit.

**Control transport and state**

- Windows runtime credentials and recovery records use the version-specific
  `%LOCALAPPDATA%/CephVR2/runtime` namespace, with existing owner-only protection.
  CephVR2.0 never hardens the legacy `%LOCALAPPDATA%/CephVR/runtime` tree;
  independent versions must not change each other's runtime-file access.
- Rig services use gRPC/Protobuf on local loopback only. The only off-host
  connection is E12's controller-owned SpikeGLX client: an outbound SDK client to
  SpikeGLX's command server over the dedicated link, with no CephVR listener there
  ([SpikeGLX control contract](../../contracts/spikeglx-control.md)). General remote
  operator control is deferred; local headless clients may run through SSH.
  Pixels/scientific streams use backend data paths, not control RPCs.
- Fixed configurable top-level ports, owned separately: controller **50051**,
  supervisor **50052**, acquisition **50053**, Visual Stimulus **50054**, tracking **50055**
  (single process per T08). Conflicts are reported at startup/Setup with no
  automatic replacement port. Private worker ports are OS-assigned and registered
  with exact process generations. Port edits require restart.
- The controller owns operator configuration/control/lifecycle, authoritative views,
  and E04's central metadata writer and output reservation (local, no RPC). The
  supervisor owns launch/registration, health/interruption, the emergency report and
  recovery state. Backends share one lifecycle service with typed backend-specific
  settings. Normal commands come from the controller; the supervisor has direct
  safety/recovery authority.
- [Control contracts](../../contracts/README.md) and
  [service definitions](../../contracts/cephvr/control/v1/services.proto) own the
  complete RPC/field/enum inventories, Snapshot contents, message sizing and prompt
  binding. NewSession requires Ended and confirmed cleanup; SaveConfigurationHistory
  saves controller state, not a GUI replacement. Prompts survive GUI disconnect and
  reconnect never supplies Continue.
- Ready/Started/Stopped/Finished reports go only to the controller. Each top-level
  backend sends Cleanup independently to controller and supervisor (for recovery
  state and shutdown) through one typed ReportLifecycle endpoint per recipient;
  Cleanup carries E06's cleanup evidence and an empty report cannot clear
  obligations. Internal workers report lifecycle only to their coordinator; if it is
  lost, the supervisor reconciles worker evidence through the workers' GetState
  (acquisition also GetRetainedResult). Recipients validate/deduplicate; normal
  progression never waits on the supervisor copy. Heartbeats, errors and
  interruption use separate endpoints.
- E06's prepared function closure and separate exact native cleanup obligations
  are registered after preliminary exact session/participant/paired-run RegisterContext and
  during partial Setup by full, append-only, revisioned heartbeat
  catalogues. Revision zero explicitly declares empty; absent revision is unknown.
  Each planned obligation needs the supervisor's accepted receipt before resource
  creation. Ready and final RegisterContext carry the identical last catalogue and
  seal it against later additions;
  Cleanup matches its revision and exact releases, plus fenced/stopped work; the
  controller registers exact append-only cleanup command target/work/ID before
  dispatch, or the supervisor matches its own issued recovery command. Empty
  Cleanup clears only a known-zero catalogue with stopped admissions. Source-owned typed fault and continuing
  function facts travel in existing Error/Heartbeat/status routes with exact work
  and process generations; forwarding or admission alone does not prove isolation.
- The controller's metadata writer and output reservation are local (E04); their
  results appear in Snapshot, and the controller sends the supervisor no Cleanup or
  reservation report. Queries never retry writes, reset deadlines, clear Interrupted
  or authorize a replacement writer.
- ReportSupervisorStatus pushes a complete supervisor-owned view on change and
  reconnect; it replaces that projection atomically, never controller lifecycle/
  readiness or retained evidence
  ([status binding](../../contracts/README.md#supervisor-status-views)).
- WatchState is the only streaming RPC; other calls are unary. It publishes complete,
  coalesced current views, never patches or event replay, without blocking control;
  configuration values arrive in each stream's first item and on each revision
  change. Reconnect warnings use the Snapshot's bounded retained incidents; there is
  no history RPC. See
  [current-state views](../../contracts/README.md#current-state-views-and-reconnect-warnings).
- One maximum gRPC message size, `[rpc] max_message_bytes` (default **16 MiB**),
  applies everywhere; large prepared artifacts stay with their backend and control
  messages carry references ([message size](../../contracts/README.md#message-size)).
- Control transport is versioned as `cephvr.control.v1`; Setup checks required
  compatibility, permitting compatible independently versioned components. Enum
  values are prefixed, required UNSPECIFIED=0 is reserved/rejected, and published
  values are never renumbered/reused.

**Identity, commands and evidence**

- One shared `host_time_ns()` helper, backed directly by Python
  `time.perf_counter_ns()`, serves host timestamps, trial scheduling, deadlines and
  latency. Keep its system-wide origin: no process-relative offset, clock server or
  mixing with wall/device/GPU clocks. Compatible clock bindings are validated before
  operational use and Setup; a mismatch blocks preparation under E06. The
  [host-clock contract](../../contracts/host-clock.md) owns API, compatibility and
  storage bindings. Nanosecond representation does not establish timing accuracy.
- Identity/context validation, absolute-deadline accounting and command/result
  retention are common Python helpers imported by controller, supervisor, backends
  and workers. Each process owns its state; handlers keep device-specific work and
  authority rules. No helper service or new framework; boundaries are in the
  [control contract](../../contracts/README.md#shared-implementation-helpers).
- Contexts are the contracts' typed operator/session/trial/backend/operation
  contexts. Command/client/control/controller/supervisor/backend generations are
  canonical lowercase hyphenated UUIDv4. Process/client IDs are allocated at startup
  before publishing; reconnect keeps a live process ID, restart gets a fresh
  generation.
- Controller state revision is a uint64 increasing within its generation and
  restarting on replacement; never compare across generations. It orders state
  views, not replayable events.
- A state-changing command uses one issuer-allocated command ID for admission,
  operation and completion. The same ID/request executes once and returns the
  retained result; a changed payload under that ID is rejected. Child commands have
  their own IDs and optional parent reference, not a second execution ID. A command
  targeting allocated work carries its expected work identity, matched exactly;
  Abort now and ShutdownApplication match the session only, so a trial transition
  never blocks them.
- Accepted/Rejected returns promptly; Accepted is ownership, not completion.
  Rejections carry code/message; completion is asynchronous state. Read-only queries
  return typed data directly. Secrets use protected gRPC metadata, never
  payload/config/log fields.
- Canonical request/admission/result records are retained for active Setup/session
  work and **300 s** after confirmed finalization/cleanup; active work is never
  evicted. A rejected or failed command starts retention for its own record only and
  never finalizes the shared work scope. The cache is in-memory, generation-scoped,
  excluded from logs/reports and cannot resume a session. Accepted completions stay
  in current views while their records remain.
- The controller registers exact process/work/operation context with the supervisor,
  and gets its acknowledgement, before Setup Ready, again at Start (recovery
  context) and on session-level changes (E06 incident scopes); there is no per-trial
  registration. Acknowledgement is not readiness/start evidence. Every backend
  locally validates registered controller/work/command/state and permanently rejects
  further execution of an Interrupted session.

**Health, recovery and shutdown**

- Backends detect operational/device errors and report directly to the supervisor.
  Structured error/recovery reports carry stable identities, work context, monotonic
  occurrence/progress/deadline times, cause and evidence/result; retries keep IDs.
  E04 logs concise errors and one final recovery result, not intermediate reports.
- For E06 coordination-blocking failures, the supervisor interrupts participants
  directly and independently notifies the controller with stable interruption ID,
  original issuance time and cause. For continuable incidents it forwards retained
  errors/status without Interrupt; the controller publishes the operator prompt and
  continuation scope. Delivery to the controller never gates stopping or resets
  deadlines. Before activation, unstarted cleanup applies; interruption evidence
  alone proves neither stopped work nor closure.
- Only the supervisor monitors the controller: exit of its OS process handle acts at
  once; heartbeat silence past the timeout is loss, with no reconnect or
  fresh-snapshot step. The controller monitors the supervisor's heartbeat to catch a
  hung supervisor. Each active top-level coordinator holds SYNCHRONIZE handles to
  the registered controller and supervisor (verified PID + creation time) and starts
  local interruption/cleanup when either exits, without waiting for delivery;
  otherwise it acts on supervisor InterruptSession. Concurrent triggers join the same
  cleanup, keep original deadlines/evidence and never reopen or resume work. On
  confirmed supervisor failure the controller interrupts and coordinates survivors.
  The [controller-health contract](../../contracts/controller-health.md)
  binds monitors and actions.
- Controller or supervisor loss automatically enters full application shutdown with
  no operator action or reopened session work. The survivor fences execution,
  interrupts/finalizes under E06/E11, stops E12's paired SpikeGLX run if the
  controller survives (otherwise the emergency report says it may still be
  recording), writes E04's emergency report, then shuts down surviving processes
  under the existing exit deadlines. The launcher is the final bounded containment
  backstop, including when both authorities fail. Nothing replaces the lost
  authority, resumes the session or fabricates its terminal events. The unfinished
  reservation marker stays for next-startup recovery; OS lock release on exit is not
  verified finalization. Report the failure and shutdown while a UI remains, with no
  modal delaying exit; next startup keeps the warning, reconciles outcomes and
  requires a fresh session.
- The launcher writes an owner-private generation-bound application-exit receipt only
  after its outer Job membership is verified empty, before releasing the application
  guard. A new supervisor exposes that exact prior-generation receipt on the existing
  recovery query; missing/invalid proof blocks E04 startup repair. A free reservation
  lock or current guard alone never proves old process absence.
- Unary heartbeats are pushed controller → supervisor, supervisor → controller, and
  each top-level coordinator → supervisor. Workers send heartbeats/progress to their
  coordinator, which aggregates them (HeartbeatReport.workers) and reports a
  worker's silence or stall as its own error; the supervisor holds OS handles for
  every descendant and sees any exit directly. Workers still send errors directly to
  the supervisor, but only the controller or a top-level coordinator may report
  controller or supervisor loss. Validate context and measure silence at recipient ingress:
  **5 s** interval, **15 s** silence, no recovery window.
  Registered controller/coordinator Configuration heartbeats without work remain
  valid process health while session scope changes; they cannot carry session
  cleanup catalogues or continuing-function evidence. Work-scoped reports retain
  exact registered context validation.
  During the exact camera PrepareTrial child's original deadline, the acquisition
  coordinator accepts idle session-only worker health until its first trial-scoped
  heartbeat. It carries no trial progress, error, cleanup or continuing-function
  evidence; after that handoff, old session health is rejected.
- Required active work reports meaningful progress; idle workers have no progress
  obligation. FFmpeg has no gRPC/heartbeat: its feeding worker monitors
  output/progress/errors and the supervisor tracks identity/exit. A healthy control
  thread does not prove data progress.
- E03 governs GUI reconnect, explicit control acquisition and warning
  acknowledgement. There is no automatic GUI relaunch: after a crash the operator
  reopens the GUI from the normal launcher under the single-GUI guard while the
  experiment continues.
- GUI closure leaves CephVR running. ShutdownApplication immediately hands
  authorized shutdown intent to the supervisor, binding command/generations/work,
  before any cleanup, then interrupts active work at once without awaiting the
  reply. The controller coordinates while alive; the supervisor continues if it
  fails, keeping deadlines. The command succeeds only with an accepted handoff and
  confirmed cleanup; a failed handoff is reported, not assumed received. After
  accepted intent, controller silence or exit is not controller loss: the supervisor
  interrupts a still-active session's participants before Shutdown, with no
  emergency report.
- After bounded finalization, release the reservation only when eligible
  (authority-loss markers remain for startup recovery), then shut down backends
  concurrently, then controller/GUI, supervisor last; the launcher exits after
  application-job cleanup. Each child gets **5 s** graceful exit, then exact-process
  OS termination and **2 s** before force-kill. Shutdown completes only when every
  owned descendant is absent and the supervisor exits. Never kill unrelated Python
  processes by name.
- Exit is tracked separately from closure; E06 owns forced-exit output status, the
  guarded Retry graceful cleanup action, exact-generation checks, stuck-process
  shutdown and full-restart backend reuse.
- E04's controller-owned metadata writer and supervisor-owned independent emergency
  path keep their bounds; no file I/O blocks health/interruption control.
  Controller loss never transfers its normal-file writer to the supervisor.

**Contract work:** process-launch registration and partial-launch identification
remain in the
[managed-process launch contract](../../contracts/README.md#managed-process-launch-contract).
Tracking's
[independent preparation/method/record declarations](../../contracts/tracking/README.md)
are bound; estimator-dependent payloads remain with T12/T04. Platform implementation
and rig validation remain later work under E15.

- Visual Stimulus's [worker/control binding](../../contracts/visual_stimulus/worker-control.md) adds typed
  startup-display status and private worker lifecycle reports to existing
  processes. Snapshot display state stays separate from Ready, with no extra
  streaming RPC or per-frame control traffic.
- Visual Stimulus [private data bindings](../../contracts/visual_stimulus/runtime-bindings.md) declare direct
  bounded data attachments and tracking-owned result generations, using existing
  process registration/deadlines. Visual Stimulus freshness handling is local; no reset service
  or scientific per-frame RPC/controller relay is added.

<a id="e14"></a>
### E14 — Backend configuration files

**Status:** Accepted · **Revision:** 207

- **Operator files contain only settings.** Human-readable `<backend>_config.toml`
  files under [config/backends/](../../config/backends/README.md) hold only values an
  operator may change to another accepted value: numbers, ports, timeouts,
  capacities, enable/save switches, device/wiring values, selectable modes and
  per-camera arguments. Fixed architecture policy (single-valued rules, selected
  libraries and algorithms, supported-option lists) lives in operator-read-only
  [`contracts/policy/<backend>_policy.toml`](../../contracts/policy/). Each pair
  carries the same `policy_version`; the loader rejects a mismatch, and
  implementation constants are checked against the policy file by one shared rule:
  the SHA-256 of the canonical parsed policy, excluding `policy_version`, so a value
  change fails startup but a comment or whitespace edit does not. Changing a policy
  value needs its governing decision plus a `policy_version` bump. Every new key is
  classified by this rule; unsupported values are invalid.
- One file owns each shared setting. The controller resolves/distributes session
  settings under E07; processes may read their own startup settings locally.
- Defaults fill missing values; explicit saved/operator values and seeds are kept.
  Reload at Setup, lock at Start, restart processes for startup-only changes.
  Control timing/timeout settings are file-only; GUI/headless edits cannot override
  them. A10's transport overrides likewise come from their owning TOML; selection of
  GUI-exposed transport controls remains deferred.
- Resource/queue limits and operational timeouts have configurable engineering
  defaults. Preparation validates the actual workload, transport headroom and
  aggregate allocation before Ready; limits are ceilings, not allocations or
  measured capacity. Never silently resize limits, alter stimulus/method settings or
  promise performance. Scientific thresholds, calibration, device/model selection
  and explicitly rig-deferred timing remain unset. File presence does not enable a
  backend. Owning TOMLs hold the numbers; contracts bind their validation.
- Reusable history lives in `config/last_configuration.json` (E07); session JSON
  logs hold only active participants' resolved setup (E04). TOMLs are not session
  logs.
- Files and governing decisions (no key inventories; adding or moving a key does
  not revise E14):

| Operator file / policy file | Governing decisions |
| --- | --- |
| `experiment_config.toml` / `experiment_policy.toml` | SYS-002/E01/E03/E05–E08/E11 |
| `supervisor_config.toml` / `supervisor_policy.toml` | E03–E06/E08 |
| `acquisition_config.toml` / `acquisition_policy.toml` | A01–A10; A11 camera-trigger consumers |
| `microcontroller_config.toml` / `microcontroller_policy.toml` | A11/E08; controller device owner |
| `gui_config.toml` / `gui_policy.toml` | E03/A10 |
| `visual_stimulus_config.toml` / `visual_stimulus_policy.toml` | V01–V28/E13/A06 |
| `tracking_config.toml` / `tracking_policy.toml` | E10/A04–A06/T01–T12/T14–T45 |
| `synchronization_config.toml` / `synchronization_policy.toml` | SYS-004/E09/E10/E12 |

- Changing repository defaults requires updating the governing rule and checking
  TOML syntax/consistency. Customizing an already configurable value is not a new
  architecture decision. Static checks do not prove runtime/rig behavior.
- Visual Stimulus capacity/progress fields and public-port ownership are bound in the
  [worker/control contract](../../contracts/visual_stimulus/worker-control.md#resource-policy-binding),
  with engineering defaults supplied and required scientific/rig inputs unset; none
  is a measured performance guarantee.

<a id="e15"></a>
### E15 — Contract artifacts and verification

**Status:** Accepted · **Revision:** 9

- Write the shared Protobuf definitions and lifecycle transition tables from
  accepted decisions, linked to this record and updated together: wire contracts
  under `contracts/cephvr/control/v1/`, derived lifecycle tables in
  `docs/experiment-control-transitions.md`. Backend-specific payload details wait
  for their backend design stages; mark gaps explicitly.
- Accepted acquisition interfaces are formalized under
  [`contracts/acquisition/`](../../contracts/acquisition/README.md) (camera-adapter
  interface, worker message definitions, frame-log schemas), with Protobuf messages
  under `contracts/cephvr/acquisition/v1/` reusing shared control semantics. Mark
  unresolved fields, bindings and encoding integration explicitly; partial contracts
  neither authorize new behavior nor claim a runnable backend.
- Lightweight implementation and authenticated backend-communication tests run
  locally with narrow hardware-boundary test adapters. Native Windows, device,
  rendering, timing and full-workload acceptance run on the rig; no simulated
  scientific backend product or readiness substitute is introduced. Track inventory, bounded capability probes
  and full-workload/backend verification separately in the
  [rig verification list](../../reports/rig-verification.md). Retain each result's
  device, build, settings and workload scope; successful generated-frame checks do
  not close untested source conversion, throughput, timing or failure checks.
- Contract compilation and static consistency checks do not establish runtime,
  hardware, timing, storage durability or recovery correctness. Runtime implementation and local-test results are recorded separately from
  pending rig acceptance in the owning implementation reports.
