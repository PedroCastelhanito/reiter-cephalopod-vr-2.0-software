# Experiment-control lifecycle tables

Derived from [E03](architecture/gui.md#e03), [E04](architecture/supervisor.md#e04),
[E05](architecture/experiment.md#e05), [E06](architecture/system-contracts.md#e06),
[E07](architecture/experiment.md#e07), [E08](architecture/system-contracts.md#e08),
E10 and E11. The architecture records govern disagreements; these tables add no
lifecycle states. During execution, E06 incident scopes override the data-only
failure transitions below when isolation is confirmed: prompt and continue on the
original timeline without claiming the missing evidence succeeded. Healthy
control/stimulus, metadata and registration gates remain; control/stimulus/ownership
failures still interrupt automatically, and initial Setup/first-trial gates are not
waivable ([operator incidents](../contracts/operator-incidents.md)).

## Common guards

- One controller event loop owns transitions. Each accepted command is tracked
  through completion by its original command ID; there is no separate operation ID.
- Validate authority, current generation, work identity and command deduplication
  before applying a change. A timely event uses receiver ingress time, not its
  later queue-processing time.
- Coordination-blocking failure and Abort override Stop after trial; continuable
  failures use E06 incident decisions. Operator disconnection never pauses
  execution.
- The supervisor sends `ReportInterruption` directly to the controller,
  independently of interrupting backends, with registered process authority, exact
  work context and a stable interruption ID; no operator lease is needed. It uses
  the failure transitions below, original deadlines and separate closure proof.
- Direct heartbeats run controller and top-level coordinators to supervisor,
  supervisor to controller, and workers to their coordinator. Coordinators watch
  controller/supervisor OS process handles instead. Heartbeat receipt never
  overrides an interruption or substitutes for lifecycle evidence.
- Configuration validation follows E07: pure module validity never proves
  hardware readiness.
- GUI state arrives as complete current views; reconnect does not replay
  transitions or execute commands.
- Configuration values lock when Start is accepted; Setup also rejects edits while
  preparing, prompting or cancelling. Ready is evidence for one configuration and
  attempt; a relevant edit invalidates it and retires the attempt's IDs.
- An Interrupted session never accepts commands that resume or advance execution.

## Session lifecycle

| From | Trigger and guard | Result / effects |
| --- | --- | --- |
| Configuration | Accepted Setup; ownership and configuration prerequisites satisfied | SettingUp; allocate fresh session/trial IDs, capture clock anchor, fan out preparation |
| SettingUp | Low/unknown space or path-conflict prompt | Stay SettingUp; wait for explicit choice; pause only automated Setup timing |
| SettingUp | All required Ready, validation, assets, reservation and output checks pass | Ready; wait for Start; no trial files |
| SettingUp | Cancel Setup or failed preparation; cleanup confirmed | Configuration; delete the directories/marker this Setup created and release its reservation (E04); retire attempt IDs; no activated or Interrupted session |
| SettingUp | Cleanup cannot be confirmed within its bounds | Configuration with cleanup blocked; warn why Setup/Start cannot proceed; retain recovery evidence |
| Ready | Cancel Setup, or a successfully validated and committed effective configuration edit | Invalidate readiness; run Cancel Setup cleanup (unarm, delete Setup-created directories/marker, release reservation) under its deadlines; Configuration after confirmed cleanup, or with cleanup blocked on exhaustion; retire attempt IDs |
| Ready | Accepted Start with prepared state still valid | Starting; lock configuration; sync session config; register and acknowledge recovery context |
| Starting, unactivated | Config sync and registration succeed | Activate session, then write/sync `session_started`; no trial release before that sync |
| Starting, unactivated | Stop/Abort, or required failure | Cancel activation; clean prepared resources; Configuration after confirmed cleanup or exhaustion, with unresolved cleanup blocked |
| Starting, activated | `session_started` sync succeeds; for a paired session, SpikeGLX startRun and the E12 writing gate pass | Running; first trial may prepare once all gates pass |
| Starting, activated | Paired session: startRun or the E12 writing gate fails | Finalizing with Interrupted outcome; stopRun if started; no trial is created |
| Starting, activated | Required failure, including session-start log failure | Finalizing with Interrupted outcome; close real resources; do not fabricate a trial |
| Running | A trial ends, more remain, no stop/blocking failure | Stay Running during closure, gap and next readiness; VR Idle |
| Running | Isolated data/function failure or bounded uncertainty | Remain Running on original schedule; retain incident and show Continue/Abort. Discharge only registered affected data-path gates as unavailable; healthy/control/stimulus gates remain required |
| Running | Continue for the current incident revision | Keep running; log exact accepted scope without restoring failed outputs or changing protocol |
| Running | Stop after trial during an active trial | Stay Running with pending stop until the trial's normal end |
| Running | Timely Cancel Stop after trial, no overriding failure/Abort | Clear pending stop through the inclusive normal end boundary |
| Running | Last trial ends, pending stop reaches boundary, or Stop between trials | Finalizing; no later trial; completed or stopped session outcome as applicable |
| Running | Operator Abort or coordination-blocking failure | Finalizing; interrupt only a trial that actually began; preserve previous completed files |
| Finalizing | Paired session: local Stopped deadline plus stop margin reached, or no trial involved | Controller calls SpikeGLX stopRun (E12); after controller loss nothing stops it and the emergency report says so. Fresh expected-run identity required; later isRunning=false confirms stop; unconfirmed stop remains a blocker |
| Finalizing | Required output/metadata cleanup confirmed | Ended with outcome and closure states; VR remains Idle |
| Finalizing | Finalization/recovery limits expire with unresolved resources | Ended, Interrupted, cleanup blocked; warn why New session is unavailable; no automatic kill/restart outside full Shutdown |
| Ended / blocked Configuration | Matching late evidence resolves every cleanup obligation | Clear cleanup block and update available commands; retain outcome/errors; no automatic New session/Setup |
| Any phase | Confirmed controller or supervisor loss | Fence work; survivor cancels/interrupts, stops the paired SpikeGLX run if it is the controller, writes emergency evidence and automatically shuts down. Launcher enforces the final deadline; no replacement or session resume |
| Ended | Explicit NewSession and confirmed resource cleanup | Configuration with current reusable values; no auto Setup/Start or process restart |

- Preactivation cleanup failure never becomes a fictitious Interrupted recording.
- Session outcome and output/metadata result are separate. Late verified closure or
  sync evidence may improve Unconfirmed results; it cannot resume the session or
  erase the original failure.
- Rejected edits preserve current configuration/readiness; accepted effective
  changes require fresh Setup. There is no automatic configuration rollback.

## Trial lifecycle

| From | Trigger and guard | Result / effects |
| --- | --- | --- |
| Pending | Session active and controller begins this fixed-order trial's preparation | Preparing; obtain fresh Ready for this trial |
| Preparing | All required trial Ready reports valid | Ready; still wait for prior closure/metadata and gap gates |
| Ready | All start gates pass | Starting; choose T with configured lead, distribute start and end, collect schedule acknowledgements |
| Starting | Target acknowledgements and release meet both cutoffs | Remain armed for T; schedule acknowledgement alone never authorizes activity |
| Starting | Successfully released interval begins at T | Running; actual backend activity is separately confirmed by Started evidence within its deadline |
| Starting / Running | At least one valid Started report | Append one `trial_started`; preserve actual partial outputs if another participant fails; no fabricated successful starts |
| Running | Normal end T + duration | Finalizing; stop trial activity locally, return VR to Idle, close outputs while draining only in-interval data |
| Starting / Running | Abort or required failure after any activity began | Finalizing with Interrupted outcome; request immediate producer stopping under E11; preserve each confirmed cutoff and real partial outputs |
| Pending / Preparing / Starting | Session ends before this trial actually begins | Never write trial frames or a fake started/Interrupted trial; retire scheduled execution; acquisition terminates its pre-launched FFmpeg and deletes only the output it created (A08) |
| Finalizing | Valid start/stop evidence, required output obligations satisfied under E05 (including the explicit A07/V12 empty-video predicates), and completion metadata synced | Ended; Completed unless already Interrupted |
| Finalizing | Closure/recovery limit expires | Ended, Interrupted; retain unresolved closure evidence and block session reuse until cleanup verified |
| Ended | Late matching closure evidence | Reconcile Unconfirmed output result only; never restart this occurrence |

- Setup requires a planned trial duration of at least 60 seconds (E05); an early
  interruption may leave a shorter partial recording.
- Start/stop reports must describe activity within each producer's E11 interval;
  reporting allowances never move its boundaries. Interruption issuance and the
  per-producer recording cutoffs are separate.
- FFmpeg launches at ScheduleTrial acceptance under
  [A08](architecture/acquisition.md#a08) and receives no frames before T; Ready
  confirms recording-thread preparation, not a running encoder.

### Completion evidence

- The controller or supervisor tracks cleanup completion using reports or verified
  retained evidence for exact process/work/operation identities. Warnings name each
  blocking resource and reason and update as obligations are resolved. Warning
  acknowledgement, a heartbeat or process exit cannot substitute for missing
  closure evidence.
- Returning to Configuration after cleanup timeout does not unlock edits while
  E07's cleanup guard remains unsatisfied. Resident VR remains running in Idle.
- Backends deliver typed Stopped and Finished payloads to the controller, and
  Cleanup independently to both authorities, through `ReportLifecycle`.
- Directory reservation and release are controller-local (E04): verified
  reservation gates Setup Ready; verified cleanup gates release. Context
  registration and command acceptance substitute for neither completion.
- Normal progression uses controller-validated evidence only, subject to the E06
  data-path exceptions above.
- The controller handles its metadata-writer and reservation results locally and,
  before clean release, validates its sealed metadata writer alongside backend
  Cleanup. Lost reports never authorize another writer, normal polling or an
  uncertain append retry.

## Timing and ordering

Values are the accepted defaults, loaded only from owning TOMLs; do not copy them
into code as constants. Comparisons use inclusive receiver-ingress cutoffs and
exact-context validation.

| Milestone | Default boundary | Required behavior on missing evidence |
| --- | --- | --- |
| Choose start target | T = scheduling time + 500 ms | All trial gates must already pass |
| All schedule acknowledgements and release dispatch | T − 100 ms | Interrupt; attempt cancellation before T |
| Backend release validation and all controller release acknowledgements | T − 50 ms | Interrupt; retain any real partial outputs |
| Trial boundary | T | No preroll or shifting T to report arrival |
| Actual start, first required activity, Started receipt | T + 250 ms | Interrupt; never allow activity outside the interval |
| Normal stop | T + protocol duration | Local stop already scheduled; no end-message dependency |
| Stopped receipt, normal end | Normal end + 250 ms | Interrupt while cleanup continues |
| Stopped receipt, early interruption | Issuance of interruption + 250 ms | Flag stop Unconfirmed; continue bounded cleanup |
| Finished/closure initial + shared recovery | 30 s + 10 s from normal end/interruption issuance | No next trial; report unresolved results |
| Setup initial + shared recovery | 60 s + 10 s | Required failure blocks execution |
| Cancel Setup cleanup + shared recovery | 10 s + 10 s | Block fresh Setup/Start until cleanup verified |
| Trial Ready initial + shared recovery | 10 s + 10 s | Interrupt the active session |
| Registration (Setup, Start, session updates) + shared recovery | 5 s + 10 s | No execution without matching registration |
| Heartbeat interval, silence | 5 s / 15 s, no recovery window | Silence or confirmed failure interrupts; no automatic process restart |
| Metadata sync | 5 s total from submission | Block/interrupt; never retry an uncertain append |

Initial collective waits share one deadline. At expiry, freeze the missing set
and query each once (GetState/GetRetainedResult) in parallel under the one shared
recovery budget. Independent obligations do not reset each other's clocks.

## Full application shutdown

- Shutdown is an operation spanning existing phases, not an ordinary GUI close.
- Confirmed controller/supervisor loss automatically invokes it under E08; that
  safety path needs no operator lease/confirmation or successful
  controller-to-supervisor handoff. The survivor notifies the persistent launcher
  and uses the same bounded cleanup; loss of both authorities still leaves
  launcher containment active.
- On acceptance, the controller immediately sends the authorized shutdown intent
  to the supervisor, which retains it and oversees completion. The controller
  coordinates cleanup while responsive; the supervisor continues after controller
  failure with the same deadlines and closure rules. A failed handoff is reported,
  not treated as supervisor acceptance.
- Progress uses supervisor-owned operation status and the controller's
  authoritative current-state views.
- Stop admitting ordinary work, interrupt activated work or cancel unactivated
  preparation, and follow bounded finalization. Then shut down tracked backend
  services, their registered workers/helper descendants (including
  backend-launched processes, not only direct children), controller and GUI; the
  supervisor exits last.
- Allow 5 seconds for graceful process exit, then 2 seconds after OS termination
  before force-killing that exact generation if needed. Never kill unrelated
  Python processes.
- Process absence does not prove file closure. Preserve known Closed/Failed
  results; missing evidence stays Unconfirmed.
- Application shutdown is complete only when all managed processes are absent; the
  launcher then closes its application job and exits. If graceful shutdown stalls,
  it terminates remaining members at the startup-only
  `application_shutdown_backstop_s` deadline in windows-launch.md.
- Keep unfinished markers and remote stop uncertainty for startup recovery.
- The owner tests rig behavior after the main architecture is established (E15).
