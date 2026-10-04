# Experiment backend

[Overview and decision register](../../architecture.md) ·
[System contracts](system-contracts.md)

The controller owns protocol execution, session/trial lifecycle and timing,
configuration and preparation. Cross-component failure handling and transport remain
in system contracts.

Related: [GUI/control ownership](gui.md#e03), [lifecycle](#e05),
[configuration](#e07), and
[experiment design guide](../experiment-backend-decisions.md).

Configuration: [experiment_config.toml](../../config/backends/experiment_config.toml).

## Decisions

<a id="e01"></a>
### E01 — Protocol progression

**Status:** Accepted · **Revision:** 13

- A session executes a predefined ordered list of trials. Each trial is one
  experimental event with its own protocol and recording interval.
- Session trial order is never shuffled. Shuffle and repeat rules apply only to
  stimulus presentation inside the relevant trial.
- Adaptive progression is deferred.
- There is no intertrial gap by default. Each real gap is independently
  configurable and uses zero when omitted.

<a id="e02"></a>
### E02 — Experiment authority and GUI role

**Status:** Accepted · **Revision:** 11

- The experiment controller executes protocols headlessly and owns authoritative
  configuration, lifecycle, command state and E04's serialized central metadata
  writer. Accepted work continues independently of GUI availability.
- The GUI is a client: it submits configuration and commands and displays
  controller state; it does not execute the protocol.
- A Python client and command-line interface support headless configuration
  changes, Setup, Start, Stop and status inspection through the same controller
  API, validation, control-ownership and lifecycle rules as the GUI.
- Each state-changing one-shot CLI invocation opens WatchState, installs current
  state, acquires unowned control, executes, then releases control and closes its
  stream. It keeps the stream while waiting; an explicit takeover is required if
  another client holds control. Read-only commands need no lease. Loss of the
  stream does not cancel accepted work; the result remains queryable by command ID.
- CLI commands wait by default: Setup for Ready, Start for completed session
  activation, and Abort for finalization. `--no-wait` returns the command ID after
  acceptance for later status inspection.
- Ctrl+C while the CLI waits requests cancellation of the current work: Cancel
  Setup during SettingUp, or Abort now during Starting or an active session. The
  CLI follows the existing bounded cleanup/finalization path before exiting;
  backend process termination remains governed by E06. Normal control-ownership
  checks apply; report an unconfirmed/rejected cancellation honestly.
- CLI output is readable text by default. `--json` provides structured results,
  errors, command identifiers and pending-prompt information for scripts.
- If unattended CLI Setup needs a Continue/Cancel answer, return the pending
  prompt information and command ID with a needs-input result, leaving Setup
  pending with prepared resources held. Another client may obtain control and
  answer or cancel under the existing rules. Never automatically approve the
  prompt, cancel Setup or report completion.

<a id="e05"></a>
### E05 — Lifecycle and trial timing

**Status:** Accepted · **Revision:** 95

#### Lifecycle

- Session phases: **Configuration, SettingUp, Ready, Starting, Running,
  Finalizing, Ended**.
- Trial phases: **Pending, Preparing, Ready, Starting, Running, Finalizing, Ended**.
- Encode session phases as `UNSPECIFIED=0`, `CONFIGURATION=1`, `SETTING_UP=2`,
  `READY=3`, `STARTING=4`, `RUNNING=5`, `FINALIZING=6`, and `ENDED=7`, and trial
  phases as `UNSPECIFIED=0`, `PENDING=1`, `PREPARING=2`, `READY=3`, `STARTING=4`,
  `RUNNING=5`, `FINALIZING=6`, and `ENDED=7`, in separately prefixed Protobuf enums.
- Outcomes, output-closure results and metadata-persistence results are separate
  from lifecycle phase; trial/session outcome is also independent of closure and
  persistence states.
- Encode output closure as `UNSPECIFIED=0`, `NOT_STARTED=1`, `OPEN=2`, `CLOSING=3`,
  `CLOSED=4`, `FAILED=5`, and `UNCONFIRMED=6`. `FAILED` means a confirmed output
  error; `UNCONFIRMED` means final closure evidence is unavailable. `CLOSED`
  confirms the owning writer's online finalization/accounting, sync and closure
  obligations; it is not a certificate of persisted file integrity.
- File validation is external post hoc work outside CephVR runtime and its
  gates; there is no validation-pending state or background validation job.
- E12's external SpikeGLX recording is a scoped exception: native finalization is
  delegated to SpikeGLX, with separate stopped evidence under the
  [SpikeGLX control contract](../../contracts/spikeglx-control.md). Do not
  synthesize CLOSED or a blocking UNCONFIRMED native-file obligation solely because
  CephVR does not independently verify that writer's finalization/durability.
- Encode metadata persistence as `UNSPECIFIED=0`, `NOT_REQUIRED=1`, `NOT_STARTED=2`,
  `PENDING=3`, `SYNCED=4`, `FAILED=5`, and `UNCONFIRMED=6`. `FAILED` means a
  confirmed persistence error; `UNCONFIRMED` means completion cannot be proven.
- `CLOSED` and `FAILED` are terminal output-closure states. Output `UNCONFIRMED`
  may change to either on late evidence verified under E06, or to `NOT_STARTED`
  only for A07/V12's positively established never-created empty-video cases. Such
  reconciliation never reopens trial execution or changes Interrupted.
- `NOT_REQUIRED`, `SYNCED` and `FAILED` are terminal metadata-persistence states;
  metadata `UNCONFIRMED` may change to `SYNCED` or `FAILED` on verified late
  evidence under E04.
- **Setup** validates and prepares the full session, collects required backend
  Ready reports, then waits in Ready. It does not activate the session or create
  trial files. Allocate the Setup attempt's session/trial IDs before preparation
  fan-out so all backend results use the same identities.
- **Start** is separate. It revalidates the prepared state, freezes the effective
  configuration, saves and synchronizes `SESSION_CONFIG.json`, and registers
  recovery context. The controller then activates the session and writes and
  synchronizes `session_started` before allowing the first trial; failure of that
  write/sync interrupts the activated session without starting a trial.
  Activation itself does not start trial files.
- For paired recordings, E12's session-scoped SpikeGLX control starts the managed
  run after activation and `session_started` persistence, before first-trial
  release, under the [SpikeGLX control contract](../../contracts/spikeglx-control.md).
  Verified writing is required before the first trial is released; a failed
  initial writing gate prevents first release. During execution, E06 classifies
  later remote failures and uncertainty for operator decision or automatic
  stopping under its runtime incident policy.
- Remote ephys recording is not a camera/Visual Stimulus per-trial output and does not change
  the trial clock. Its completion result follows E12's delegated native
  finalization contract; transport/runtime integration remains local work.
- Remain in Ended with the session result visible until an explicit **New session**
  command, which after confirmed cleanup returns to Configuration with the current
  reusable settings and unlocks editing; unresolved cleanup blocks it. It requires
  fresh Setup and Start with new identities allocated during Setup, and never
  restarts processes or resumes the old session.
- **Cancel Setup** is available to the lease holder in SettingUp and Ready. It
  cancels and unarms all participants concurrently, invalidates readiness, deletes
  the directories/marker that Setup created, releases the output reservation (E04)
  and returns to Configuration after confirmed cleanup. Cancellation retires that
  attempt's session/trial IDs and is not an interruption. An effective
  configuration edit accepted in Ready runs this same cleanup automatically.
  There is no separate Cancel Start command; Stop/Abort during Starting follows E06.
- Cancel Setup uses one shared 10-second cleanup deadline and, for the frozen
  missing set, E06's shared 10-second recovery budget (one state query). If still
  unconfirmed, return to Configuration with cleanup explicitly blocked; further
  Setup/Start remains blocked until cleanup is verified. The phase alone is not
  evidence that resources were released.
- After finalization/recovery bounds expire, an activated session and its affected
  trial end in Ended with Interrupted outcome and unresolved cleanup recorded
  separately. An unactivated attempt returns to Configuration with cleanup blocked,
  without inventing a trial or Interrupted session. E06 governs the warning and
  subsequent confirmation; no automatic new session follows cleanup completion.
- Each participant sends **Ready** only after verifying its backend, devices and
  current trial resources. Obtain a fresh Ready before every trial, including the
  first; readiness is never reused.
- Ready, Started, Stopped and Finished reports identify the backend, its process
  generation, controller generation, session, applicable trial and answered
  operation. Ready includes the verified configuration revision, confirmation that
  required device/resource checks passed, and settings resolved during Setup when
  applicable.
- Each participant sends **Stopped** promptly when trial activity has ended,
  independently of output closure. Include actual activity-stop time, each producer
  recording cutoff under E11, and confirmation of the stop conditions: Visual Stimulus is Idle
  and recording no longer admits samples outside the trial interval. Draining
  already admitted samples may continue.
- Each participant sends **Finished** only after trial work has ended and every
  enabled output obligation is satisfied. Normally this requires successful
  closure; explicitly empty camera/Visual Stimulus review-video results may instead confirm an
  artifact was never created, with complete accounting and cleanup under the owning
  [A07 camera](../../contracts/acquisition/empty-video.md) or
  [V12 Visual Stimulus](../../contracts/visual_stimulus/video-completion.md) contract. These exceptions cannot
  hide failed/unknown output or waive required activity/health evidence. Finished
  lists each enabled output's reserved path, artifact presence, applicable content
  evidence and closure state. A lost report may be recovered without closing files
  twice.
- On failure, report the error and current state instead of successful Ready or
  Finished. Validate report context before using its evidence; repeated delivery
  of the same report has no additional effect. These reports add no verbose
  per-participant entries to the concise session log.
- The next trial requires prior completion, synchronized trial metadata, fresh
  readiness and valid execution gates; these operations may overlap. Supervisor
  registration is session-level, not per trial.
- E06 incident scopes take precedence over the per-participant activity/completion
  requirements only for proven isolated unavailable data functions: while a prompt
  is pending or continued, they may discharge only the affected data-path
  obligations as unavailable, as bound by the
  [incident contract](../../contracts/operator-incidents.md). Healthy
  stimulus/control participants still meet every original timing and ownership
  gate. Never fabricate successful Ready/Finished, relabel late activity as timely,
  treat missing data as success, or bypass stimulus, identity, metadata or safe
  resource ownership.
- Setup cannot become Ready until output-path collision handling and reservation
  have completed successfully. No session or trial may start from an unreserved
  output plan.
- Visual Stimulus stays running in the same configurable Idle presentation before the first
  trial, between trials, during finalization and after session termination. Idle
  has no relevant trial stimulus; all-black windows must be supported.

#### Trial start and end

- After all start gates pass, schedule a common target **T** in the main computer's
  host-monotonic clock through E08's shared `host_time_ns()` binding and encode it
  as integer nanoseconds. Every recipient uses that same unshifted clock domain.
- Deliver both T and the protocol-defined end boundary `T + duration` to each
  backend before trial start. After valid release, each backend schedules the
  normal stop locally; it does not wait for a new message at the end boundary.
  Abort may end the trial earlier.
- Use a 500 ms lead by default (`start_lead_time_ms`, file-only, fixed for the
  session). Collect target acknowledgements and dispatch release by `T - 100 ms`.
  Every required backend must receive and validate release, and the controller must
  receive valid release acknowledgements from every required backend, by
  `T - 50 ms` (the same cutoff setting). Target acknowledgement alone never
  authorizes execution.
- Missing schedule/release evidence triggers immediate session interruption and an
  attempt to cancel scheduled execution before T. If a participant nevertheless
  starts, retain its real partial outputs under the normal interruption policy.
- Allow one transport-failure retry per `ScheduleTrial` or `ReleaseTrial` request,
  using the same command ID and payload, within its original absolute deadline.
  Do not retry a confirmed rejection, move T, or extend a cutoff. Delivery still
  unconfirmed at its cutoff interrupts the session. The retry limit is owned by
  `experiment_config.toml` and does not apply to uncertain metadata writes.
- When every required backend validly accepts release, **T is the trial-start and
  recording boundary**; the normal end boundary is `T + duration`.
- After successful release, the trial enters Running at T; Started reports confirm
  actual activity separately and neither their arrival nor full participation
  delays this transition. Keep unconfirmed activity visible and write
  `trial_started` only on E04's actual evidence.
- Each backend sends an explicit Started report with its process/trial/operation
  context, actual start time and first required activity evidence: the first
  expected current-trial camera callback; for Visual Stimulus, one returned presentation call per
  required output (the swap call of the first render group evaluated at or after T
  has returned); or, for tracking, a completed first frame evaluation under
  [T08](tracking.md#t08). Actual software start, that evidence and controller
  receipt of the report must all occur by `T + 250 ms`.
- Visual Stimulus evidence is software-only: the rig cannot observe the photodiode; optical
  onset is recovered post hoc from SpikeGLX.
- A required backend that cannot meet this liveness limit must not start late;
  interrupt the session. T is never shifted to T+250 ms. Reports add no routine
  session-log entries; command acceptance alone is not evidence of execution.
- Planned trials last at least **60 seconds**; validate this during Setup. Visual Stimulus
  resolves the protocol duration from its epoch plan under [V06](visual_stimulus.md#v06); the
  controller retains the common trial boundaries. The
  [duration contract](../../contracts/visual_stimulus/durations.md) binds Visual Stimulus-owned resolved
  duration and schedule validation; there is no independently editable duration in
  operator configuration. Keep the HHMMSS filename scheme without a trial-number
  suffix (E04).
- Abort/failure may produce shorter partial recordings; reporting allowances never
  extend their actual trial interval.
- The locally scheduled stop takes effect at `T + duration`: every backend stops
  trial work and begins graceful output closure at that boundary. Slow reports or
  file closure cannot extend the recorded interval.
- For normal trial end, the controller must receive valid Stopped evidence from
  every required participant by `T + duration + 250 ms`. Missing evidence
  interrupts the session while graceful cleanup continues. This allowance never
  extends trial activity; Finished retains its separate closure deadline.
- For early interruption of an active trial, the same 250 ms Stopped allowance
  begins when the controller or supervisor issues the interruption, not when each
  backend receives it; delivery and reporting consume it. Missing evidence flags
  stopping as unconfirmed while graceful cleanup continues; this does not authorize
  forced termination outside the existing shutdown/recovery policy.
- Each configured intertrial gap is a minimum duration from the previous trial end.
  Closure, metadata sync, registration and preparation may overlap it, but all
  start gates must still pass. There is no first-trial or final-trial gap.
- A pending Stop after trial may be withdrawn by **Cancel Stop after trial** through
  the active trial's inclusive `T + duration` boundary. A timely withdrawal is
  classified before stop-driven finalization and changes no trial boundary.

#### Deadline accounting

- Applicable deadlines run independently on host-monotonic time; the earliest
  required failure controls. One state query may serve overlapping waits for the
  same component without resetting either deadline.
- Setup, per-trial Ready and Finished each use one shared initial deadline across
  all required participants. At expiry, freeze the missing set and query each once
  (GetState/GetRetainedResult) in parallel under the one shared recovery budget.
- Start clocks at controller-side phase/fan-out boundaries: SettingUp, Preparing,
  the normal trial end or original interruption issuance, recovery expiry, and the
  session-level supervisor-registration dispatch. Producer stop/closure reports
  never restart finalization deadlines. Transport and queue delay consume the
  allowance.
- The receiving authority stamps ingress in host-monotonic nanoseconds before
  application queueing. Evidence arriving at or before an inclusive cutoff counts
  only after exact process/session/trial/operation/generation validation. Sender
  timestamps are diagnostic.
- Waiting for an explicit low/unknown-space or output-conflict choice pauses only
  automated Setup timing. Health and already submitted persistence work remain
  timed.
- Timing and timeout values come only from their owning backend TOML before Setup;
  reject session-level and trial-level overrides.

The [lifecycle tables](../experiment-control-transitions.md) formalize the accepted
transitions and guards.

**Backend follow-up:** camera frame association is defined in [A09](acquisition.md#a09);
display evidence and remaining timing diagnostics belong to [Visual Stimulus](visual_stimulus.md) and
[A05](system-contracts.md#a05).

<a id="e07"></a>
### E07 — Configuration and protocol preparation

**Status:** Accepted · **Revision:** 57

#### Sources and loading

- Experimental settings and the protocol become immutable when Start is accepted
  and stay fixed for the session; changing them requires a new session.
- Initialize a new configuration from the last-used values when history exists,
  otherwise from defaults. Defaults fill missing settings without replacing saved
  values. Config-file-only control policies come from their owning TOML files
  under E14.
- The controller assembles the session configuration from backend TOML defaults
  and saved/operator values under the existing precedence rules and sends each
  backend its relevant settings. Backends validate them and return resolved values
  during Setup; the controller retains the resulting effective configuration for
  execution and logging. Backends do not independently merge session defaults.
- Reload backend TOMLs at each Setup, preserving explicit saved/operator values;
  file edits never modify the prepared or running session without a new Setup.
- Processes may read startup-only settings needed before controller coordination,
  such as service ports, from the same files; this is not a separate session
  configuration source. Changing them requires an application restart; Setup
  cannot apply them to running services.
- A missing, unreadable or invalid required-backend TOML blocks Setup. Report the
  affected file and field or parse location where available and require
  correction; do not substitute built-in defaults or offer Continue.
- For an inactive backend not required by the selected session, such a TOML
  produces a warning without blocking Setup; it must be corrected before that
  backend can be enabled and prepared. This never bypasses the configuration
  requirements of an active backend or required process.
- If history is unreadable or incompatible, preserve the problematic file for
  diagnosis, warn clearly that defaults were loaded and initialize from defaults.
  This fallback still requires valid backend default files for the required
  participants, explicit mode selection and normal Setup validation before
  execution.
- On startup without a GUI, the controller loads the same saved configuration with
  the same fallback rules. Loading configuration never automatically runs Setup or
  starts a session. After initial configuration adoption, V19's bounded startup
  display initialization may validate/apply only Visual Stimulus display/Idle settings; it does
  not grant session readiness. GUI and headless startup follow the same rule.

#### Configuration history

- The controller is the sole writer of configuration history,
  `config/last_configuration.json`. Normal GUI closure requests a save of the
  controller's current reusable configuration; application shutdown uses the same
  mechanism. Serialize writes outside the lifecycle state-processing loop using the
  existing atomic save procedure. GUIs read the file when initializing a new
  configuration but never overwrite it.
- Store one current reusable configuration, grouped by backend with shared
  experiment/protocol settings; there is no rollback section or retained rejected
  edit. Keep settings for disabled as well as enabled backends; session
  reproducibility logs include only active-backend settings under E04.
- Saving does not require successful Setup or a started session; missing rig
  values remain subject to normal preparation checks. Restoring history never
  replaces a running controller's state; reconnecting clients synchronize under E03.
- Configuration-history saving has a configurable 5-second deadline covering
  queueing and the save operation, owned by `experiment_config.toml` and separate
  from session metadata timing. On failure or timeout, preserve the previous saved
  configuration and warn that recent changes were not saved.
- Interactive GUI closure then offers Retry or Close without saving. Unattended
  headless shutdown reports the failure and finishes graceful shutdown without
  waiting for operator input.
- A history-save failure alone does not interrupt an ongoing experiment; full
  application shutdown still proceeds with experiment interruption and graceful
  cleanup while the save problem is handled.

#### Editing and edit validation

- Headless clients inspect and edit configuration through the same controller
  `GetSnapshot`, control-ownership and `UpdateConfiguration` contracts and rules
  as the GUI. Accepted edits become the current configuration and enter normal
  history saving; config-file-only policies stay in their TOMLs.
- `UpdateConfiguration` submits the full proposed configuration and the revision
  last received by the client. Require the current control holder; reject a stale
  revision or locked configuration without changing the stored values.
- Disable editing and reject `UpdateConfiguration` throughout SettingUp, including
  while awaiting a Continue/Cancel response and during Setup cancellation cleanup.
  To edit, Cancel Setup and wait for confirmed cleanup and return to
  Configuration. Returning to Configuration after cleanup exhaustion does not
  bypass this cleanup guard; clients cannot bypass it through direct RPCs.
- Validate every proposed edit before committing it. Pure module validation runs
  outside the controller state loop under one configurable 5-second total deadline,
  including queueing; it needs no validation RPC or live device. A stopped backend
  alone does not make its local pure validator unavailable.
- If a required pure validator is unavailable, incompatible or timed out, or
  rejects a value, reject the edit and preserve the current configuration,
  revision, saved history and existing Ready state. A confirmed rejection returns
  specific field paths, stable error codes and short explanations. The operator
  warning names the affected component/field when known, stable code and reason,
  and states explicitly that changes were not applied.
- GUI and headless clients receive the same failure. There is no Continue
  override, stored pending edit or automatic later apply.
- Successful validation commits atomically only after rechecking the current
  control lease, expected configuration revision and lifecycle lock; obsolete or
  late results cannot commit or overwrite newer state. A committed effective edit
  advances the revision. Before Start it invalidates Ready and runs E05's Cancel
  Setup cleanup back to Configuration, requiring a new Setup; there is no live
  reload.
- There is one current configuration, with no Unvalidated-edit state or automatic
  rollback; retry is an explicit new edit against current state.
- Each backend owns a lightweight Python configuration module containing its types
  and pure validation functions, used by both controller and backend; importing it
  must not initialize devices or load heavy runtime components. The controller
  validates shared fields/dependencies and remains the only commit authority.
- Edit validation checks structure and values without applying settings, opening
  devices, preparing assets or generating seeds; those remain in Setup.
- V19's separate startup display initialization checks/applies only its required
  output resources; it is not an edit-validation side effect and does not satisfy
  session device/asset obligations. A10's explicit preview and PFS import/export
  actions are separate acquisition-backend operations, not edit-validation side
  effects. They follow control ownership and configuration-lock rules;
  imported/edited values enter controller configuration before Setup.
- Reject unknown configuration fields with their location and an explanation.
  Invalid saved history uses the warning-and-default fallback above. This rule
  concerns configuration validation, not compatible additions to gRPC messages.

#### Setup validation and resolution

- A valid protocol/session requires valid configuration for every active backend
  and required process, including the controller and supervisor. Setup validates
  the entire planned session and every required asset. The controller validates
  shared plan rules and cross-backend dependencies; each backend validates its own
  settings, devices, capabilities and assets.
- Check configuration-module compatibility with each required backend during
  Setup; mismatches block Ready with an actionable error. Pure validation success
  never substitutes for backend device, capability and asset checks or resolution
  of generated values. Loading/Setup validation failures report/block preparation
  without automatically replacing existing settings.
- Each backend declares the dependencies of its selected configuration (defined
  in its backend design); during Setup the controller validates them against
  enabled participants and capabilities. Missing requirements block Ready with an
  actionable explanation; never silently enable a backend to satisfy one.
- Collect independent failures into one actionable report. Skip only checks whose
  prerequisites are invalid; any required failure blocks Ready and Start.
- Setup validates the configured control endpoints, reports duplicate assignments
  or occupied-port conflicts, and verifies that expected running services own
  their endpoints (a port bound by its expected service is not a conflict).
  Unresolved required-service conflicts block Ready.
- Show validation failures as a warning naming the failing backend/process, check,
  configuration field or file location and device/trial context, with a stable
  code and short explanation; headless clients receive the same structured
  information. The warning does not override failed validation.
- Use practical asset checks: decode static images; inspect video metadata and
  representative frames rather than scanning every frame.
- Configure a shared `assets.asset_root` directory, possibly outside the software
  folder or on another disk; there is no default. Asset/media references resolve
  relative to it (including subfolders), not to the launch directory or config
  file. The controller distributes the root with the relevant settings; consuming
  backends validate their required assets during Setup. The root follows ordinary
  configuration editing, history and session-locking rules. It does not change
  recording-output paths or E04's minimal central asset metadata; V13 owns the
  scoped Visual Stimulus replay manifest.
- Each active backend returns the filename of every validated asset for the
  minimal session metadata defined in E04.
- Setup resolves and retains every effective shared and trial-specific setting,
  including omitted intertrial gaps as zero (E01). Start and execution use exactly
  those resolved values.
- During Setup, resolve the main computer's local IANA timezone and include it in
  the prepared session configuration. A later host-timezone change does not alter
  that Setup/session's timezone.
- The Visual Stimulus backend generates missing stimulus seeds and planned stimulus
  sequences during Setup. Preserve explicit seeds and reuse resolved seeds across
  later sessions until changed. Invalid explicit seeds block Ready.
- Store each trial's resolved seed and compact planned epochs, including scene and
  ordered group/repetition/unit/visit lineage, in its central trial log at trial
  start. Reference the complete immutable `_stimulus_LOG.json` under
  [V13](visual_stimulus.md#v13), required independently of Save Visual Stimulus data; never rely on later
  editable files or seed regeneration. Actual presentation and behavior remain
  backend output data.
- Control timing and timeout values are editable only in their owning TOML files;
  reject session-level and trial-level overrides (E05).

**Backend follow-up:** each backend owns its remaining settings schema/ranges.
Stimulus shuffle/repeat and seed-stream contracts belong to [Visual Stimulus](visual_stimulus.md);
these are not unanswered controller ownership choices.

<a id="e10"></a>
### E10 — Modes and required participants

**Status:** Accepted · **Revision:** 22

- Support two session modes, open-loop Visual Stimulus and closed-loop Visual Stimulus; Visual Stimulus runs in both.
- Select one mode and one active-backend set for the whole session. Trial-specific
  gains may change, including gains that simulate open-loop behavior, without
  changing the session mode or participant set.
- Derive Tracking participation from the session mode and T14 saving: active for
  closed-loop or velocity recording, otherwise inactive. Open-loop saved tracking
  does not drive the stimulus; closed-loop requires feedback even with saving Off.
  Camera and Visual Stimulus video recording remain independent of this derivation.
- Every enabled backend, device, input dependency and scientific output is required
  at initial preparation/start; disabled roles add no obligations. During
  execution E06 permits explicit incident-scoped unavailable data functions while
  valid coordinated stimulus execution continues; record configured participation
  separately from actual function/data loss, never silently changing the mode.
- Cameras may all be disabled when no selected feature requires their input.
  Closed-loop tracking still requires a valid configured input.
- New-configuration defaults:

| Role or output | Default |
| --- | --- |
| Visual Stimulus runtime | On |
| Behavioral camera | On |
| Behavioral-camera video | On |
| Tracking backend | Derived from mode and T14 saving |
| Tracking camera | Off |
| Tracking-camera video, when camera enabled | On |
| Save Visual Stimulus data | On |
| SpikeGLX pairing (E12) | On; default editable in `synchronization_config.toml` |

- SpikeGLX pairing is a per-session configuration choice like the rows above; an
  explicit saved On/Off is restored and the file default applies only when none
  exists.
- Restore the saved session mode when present. There is no fallback session mode:
  without a saved or explicitly selected mode, the operator must choose open-loop
  or closed-loop before Setup. Preserve other explicit saved choices.
- Camera-video saving is configurable per camera before the session under E07 and
  stays locked for the session. Preserve an explicit saved Off value; enabling the
  tracking camera does not overwrite it, and its video-saving default does not
  enable the camera. `save_video = false` also disables that camera's frame log
  and diagnostics under A07; it does not disable acquisition needed by tracking or
  tracking's independently enabled outputs.

<a id="e11"></a>
### E11 — Trial recording interval

**Status:** Accepted · **Revision:** 17

- All local camera/Visual Stimulus/tracking trial outputs use the authoritative start T and
  normal end `T + duration`. E12's separate session-scoped SpikeGLX recording may
  span trials/intertrial periods; its remote boundary observations do not replace
  the producer cutoffs below.
- Data membership is start inclusive and end exclusive. Camera membership uses A09
  host receipt, with hardware exposure/trigger timing retained as alignment
  evidence.
- On Abort/failure, each producer promptly seals sample admission at its local
  host-monotonic cutoff, capped by the scheduled normal end. Preserve the original
  interruption-request time separately for deadlines and diagnostics; it is not a
  retroactive recording cutoff. Interrupted sources may have different end times.
- Consumers drain only samples admitted by their producer before its cutoff; camera
  video and frame log share the camera's cutoff, not the recording thread's later
  stop or closure. Do not trim already admitted data back to request issuance or
  fabricate a common physical stop. Missing producer evidence leaves its cutoff
  unconfirmed.
- Retain producer cutoffs in stopped evidence and owning backend output timing.
  The controller's interrupted-trial end summarizes the latest confirmed required
  producer cutoff only once all required cutoffs are known; otherwise it is
  unknown. This summary never replaces an individual source boundary or resets
  deadlines.
- There is no pre-roll or post-roll. Setup, Idle, intertrial gaps and file-closing
  time are outside trial files.
- Baseline and pause stimuli belong inside the trial stimulus protocol and
  therefore inside the trial duration.
- Graceful finalization may drain buffered in-interval data after the boundary but
  must never append later samples.
