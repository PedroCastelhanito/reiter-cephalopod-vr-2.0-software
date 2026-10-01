# Runtime incidents and operator decisions

Authority: [E06/E08](../docs/architecture/system-contracts.md#e06),
[E03](../docs/architecture/gui.md#e03), [E04](../docs/architecture/supervisor.md#e04),
[E05/E10](../docs/architecture/experiment.md). Wire evidence and the shared pure
classifier do not imply that backend producers or controller incident UI exist.

## Classification and ownership

During active experiment execution, replace unconditional interruption solely because
an enabled device/output failed with this shared E06 classifier. This refines backend
contracts that say “interrupt under E06”; it does not delay immediate local fault
containment, authorize unsafe buffer access or change pre-first-trial readiness.
Before the first trial, normal Setup/start/writing gates must still pass. Direct
operator Abort and explicit application shutdown remain unconditional commands.

| Condition | Required response |
| --- | --- |
| Recoverable uncertainty with a valid current schedule, including SpikeGLX link loss inside J1's existing deadline | Incident prompt; keep running and perform only existing bounded recovery |
| Failed camera/recorder/tracking/output or expired data-progress limit, with proven isolated ownership and a functioning stimulus/control path | Prompt; fence that failed path, explicitly retain its data/function loss, continue healthy paths |
| Tracking unavailable with V25's declared feedback hold | Prompt for the loss condition; hold affected feedback while stimulus clock continues; do not substitute an estimator or invent motion |
| Controller/supervisor lost | E08 automatic shutdown; show an informative incident, no Continue |
| Required renderer/projector cannot present, or valid protocol scheduling/identity/host clock cannot be maintained | Automatic interruption; no Continue |
| Failed path cannot be isolated, ownership is unsafe/unknown after its existing recovery bound, or bounded control/incident accounting cannot be maintained | Automatic interruption; no Continue |
| Normal permitted frame drops, transient invalid flow/pose or timing misses under existing nonfatal policies | Existing grouped warnings; not a new confirmation per sample |

Controller owns the operator decision and current incident view. Supervisor and backend
safety paths use the same classifier/rules and existing retained work/resource evidence;
the GUI cannot label an error continuable. Supervisors forward continuable reports using
existing error/status delivery, and issue InterruptionReport only for actual interruption.
A failure code alone does not prove isolation: validate the affected prepared dependency
closure, source generations, resource leases and safe behavior of every continuing path.
If those facts cannot be established within existing recovery limits, interrupt.

Each backend's exact Ready includes `PreparedFunctionScope` declarations for its owned
session resources/functions, transitive affected closure (including self), essential
stimulus/control paths, any V25 feedback hold dependency and functions permitted to
remain uncertain only inside the original recovery bound. Controller validates and
registers the aggregate with supervisor; an absent/inconsistent declaration grants no
Continue.
`lifecycle_sources` identifies the backend-scoped E11 activity/cutoff gates lost with
each function: acquisition `behavioral`/`tracking`, tracking `tracking`, Visual Stimulus `renderer`.
Output-only functions use an empty list. Source claims are unique per backend; the Visual Stimulus
renderer is always essential. Each acquisition camera source binds one exact
supervisor-registered worker reporter through `ProcessHealthStatus.launch_owner`
ancestry, never an inferred worker name. A retained loss closes the named source's
activity gate and later cutoff requirement without claiming its output complete.
`ErrorReport.isolation` supplies source-attested affected/fenced prepared keys,
lease disposition, exact held keys and host observation time. It cannot attest another
owner's healthy path. Each owner's `HeartbeatReport.continuing_functions` provides
current typed function/schedule/clock/control observations, forwarded intact in
`ProcessHealthStatus.last_heartbeat`. Receivers check registered generations, work,
prepared ownership, closure and observations after the fault; health text, process
liveness, failure code or a controller-created scope alone is insufficient. These
are bounded control observations, not per-frame data. Unknown evidence remains pending
only through the original E06 recovery deadline and then blocks continuation.
The source keeps `incident_episode_id` stable across related error IDs; if absent,
one error ID is one episode. Blocked incidents retain acknowledgement separately
from resolution or Continue.

Ready also declares `cleanup_resources` as exact native owner/resource/optional-path
release obligations; controller registers the identical aggregate with supervisor.
During partial Setup, each backend first sends revision 0 with an explicitly empty
catalogue, then sends a complete append-only catalogue at each next revision and
waits for supervisor's accepted heartbeat receipt before creating newly planned
resources. Absent revision is unknown. Ready/final registration must match the last
acknowledged catalogue and seal it against later additions. Cleanup names that
revision and exact released obligations;
even a known-zero catalogue clears only with fenced cleanup and stopped work. The
controller registers exact cleanup target/work/child command IDs append-only through
RegisterContext before dispatch; supervisor also accepts its own issued recovery
cleanup command. A report operation ID alone is not a fence.
These obligations are distinct from prepared logical functions and reserved output
closures. A recipient matches each Cleanup resource against that catalogue and the
owning backend's rules. An empty declaration alone does not prove that a required
backend has no native resource obligations.

“Continue” never makes a failed function healthy. Freeze its admissions, preserve pending
eligible data where possible and stop/close its owned work under existing deadlines.
Do not reuse a hung worker's leased buffers or reopen failed files. An allocation may
remain quarantined only if it cannot block/corrupt healthy paths and its retained memory
fits existing limits. New corruption, unbounded pressure or shared GPU failure escalates.
A dead process is not automatically a session failure if its entire function is isolated;
a live heartbeat is not proof that a required renderer can still present.

Camera/recording loss must remain visible as missing video/frames; lost tracking remains
visible as feedback hold; lost SpikeGLX confirmation is not proof it stopped or kept
recording. Do not change camera source, tracking method, arena/program, gains, trial
order/durations or the configured participant set. Preserve the original configuration
and separately record actual unavailable functions for this session. No automatic
restart/re-enable of a failed device, worker or writer; a new Setup is required.

## Running while a decision is pending

Use one runtime incident per session/source-generation/failure/resource episode, with
stable ID, increasing incident revision, original error IDs and first/last observation.
Coalesce repeat reports/counts; reopen a prompt only for a materially new consequence,
resource, severity or episode. Recovered transient conditions update/resolve the same
incident; they do not erase the fault history. Unknown status is distinct from success.

No pause, clock shift, extra intertrial wait or implicit abort on operator silence.
The original current-trial cutoff remains authoritative. Healthy protocol progression
may continue while the decision is pending or Continue was selected. Record the exact
incident-scoped exceptions to data-path readiness/health/output completion: a known
unavailable function is never represented as Ready/Started/Finished-success. Instead,
controller uses its retained failure and isolation evidence to discharge only the
corresponding activity/completion gate as unavailable. Register the same incident/scope
with supervisor using existing RegisterContext and send ApplyIncidentScope to affected
healthy coordinators (registered command/session/incident revision, idempotent). They
retain unavailable dependency/output scope, fence admissions and use only already
specified hold/omission behavior; push exact terminal `OperationState` in
`LifecycleReport.operation` to controller, or answer one bounded
`GetRetainedResult` reconciliation for the same child command/source/work.
Use the original registration/recovery bound; admission alone does not prove isolation.
A missing scope acknowledgement that prevents coherent control is blocking under E06.
Local fault containment never waits for these messages. Subsequent TrialPlan carries
the same retained incident revisions; register/acknowledge them before the next trial. Healthy functions, stimulus schedule, safe resource cleanup, central
metadata and identity/reservation gates remain mandatory. Do not skip a protocol trial.

A failed output keeps FAILED/UNCONFIRMED or confirmed NOT_CREATED as appropriate; it
cannot become CLOSED because the operator continued. Missing scientific data does not
by itself relabel a running/completed trial Interrupted. Trial/session records identify
the active incident IDs and affected outputs; elapsed stimulus execution and data
completeness are separate. Unresolved unsafe ownership still blocks further execution.
At normal session end, close pending prompts as unanswered/session-ended, never as
implicit Continue, and finalize healthy work plus known failed obligations.

## GUI, headless use and command binding

Use one updating incident window listing active issues, their occurrence time, affected
function/trial/files, known or unknown data loss, current behavior and available actions.
Continuable incidents offer Continue session / Abort session; blocking incidents explain
automatic stopping and offer acknowledgement only. Never block rendering, acquisition,
SDK/health threads or scheduled trial boundaries on the window. Dismissing/minimizing is
not an answer. New blocking evidence supersedes a stale Continue immediately.

Expose the same retained incident list in Snapshot/WatchState and headless clients.
A lost/reconnecting GUI restores current incidents, not a replay of popup events. Use
one existing GUI process; if unavailable use the supervisor's existing local warning
window when possible, or retain an actionable headless prompt. A graphical display
cannot be promised when the host/UI has failed; next-startup reports retain blocking
failures. Local window decisions while controller lives require the normal control
lease (Take control if needed); no second lifecycle authority is introduced.

RuntimeIncident and Prompt.runtime_incident refer to the same ID/revision. Reuse
RespondToPrompt: legacy setup/setup_operation fields bind the current session and
incident operation for runtime prompts, and expected_incident_revision is required.
Choices are exactly continue_session, abort_session or acknowledge as advertised.
Validate current session/controller/lease/incident revision and allowed choice. Continue
acknowledges only the displayed incident scope. Abort delegates to existing AbortNow
semantics. Reject a stale Continue; the ordinary AbortNow command remains available
regardless of which window/revision is displayed. Repeated identical command IDs remain
idempotent. No timer or GUI response resumes an already Interrupted session.

## Retention, logging and bounds

Use existing bounded control/status storage and coalescing; one window, no per-frame
RPCs or new service. Retain active incident/scopes through session finalization and
existing command retention. A capacity limit that prevents required incident accounting
is a coordination-blocking fault, not permission to drop an unseen decision.

E04 SESSION_LOG records the initial error and material scope/escalation using existing
error events, plus incident_decision for each accepted choice with incident ID/revision,
choice, source client, affected scope and host-monotonic time. Record automatic-stop
reason and unanswered terminal disposition separately from operator consent. The central
trial log references incidents already active at its start; later changes use the session
log's trial attribution. No rewrite of authored config, scientific files or past events.
Normal lifecycle outcomes stay independent of the preserved failed-output evidence.

Failure of scientific recording alone is promptable when isolated. Failure of central
metadata/incident persistence retains its existing E04 bounded emergency path; if the
required decision/execution bookkeeping cannot be retained, automatically interrupt.
A prompt cannot waive identity, reservation or control-accounting integrity. Emergency
logging never delays stopping and never fabricates successful persistence.

SPIKEGLX: during execution, J1's in-bound connection uncertainty opens/updates the
incident; its deadline expiry or confirmed stopped/changed run escalates its consequences
and reopens the choice for that scope. This does not automatically abort while local
execution remains valid. No new start/adoption of a remote run is authorized. At session
end H1's expected-run-only stop remains bounded and a different run is never stopped.
