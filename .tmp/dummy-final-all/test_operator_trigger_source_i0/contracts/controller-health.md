# Controller-health and authority-loss binding

Governing rules: [E06/E08](../docs/architecture/system-contracts.md) and
[E05/E11](../docs/architecture/experiment.md). This declares shared helper behavior
and existing RPC use; runtime monitoring remains unimplemented.

## Monitors

| Watcher | Watches | Evidence | Action on loss |
| --- | --- | --- | --- |
| Supervisor | Controller | OS process handle exit (immediate); heartbeat silence | Interrupt participants directly, then E08 full shutdown |
| Controller | Supervisor | OS process handle exit (immediate); heartbeat silence | Interrupt and coordinate survivors, then E08 full shutdown |
| Each active top-level coordinator | Controller and supervisor | SYNCHRONIZE OS process handles only | Local safety handler (table below) |
| Coordinator | Its workers | Private `ReportWorkerHeartbeat` + progress | Report the worker's silence/stall as its own `ErrorReport` |
| Supervisor | Coordinators | Coordinator heartbeat (with aggregated `workers`); OS handles for every descendant | E06 incident classification |

Share helper code, not mutable monitor state or a watchdog process. A coordinator
opens its handles at registration from the registered PID + creation time and
verifies both before accepting operational work; it has no controller heartbeat,
silence timer or snapshot query. Tracking's single process has no workers.

Health values come from the sole `[health]` definition in supervisor_config.toml,
read by every process at startup; a change takes effect after application restart.
Fixed health policy strings live in supervisor_policy.toml.

## Silence

Use `host_time_ns()` and authenticated registered identities/context. Valid receipt
ingress sets the next silence deadline to ingress plus `silence_timeout_s` (15 s at
the 5 s interval). Sender timestamps, GUI connectivity and another participant's
heartbeat cannot refresh it. Reject stale generations and invalid work context; an
older heartbeat cannot roll back a validated lifecycle transition.

Silence past the deadline is loss. There is no reconnect, fresh-snapshot check or
recovery window: controller/supervisor loss ends in full shutdown either way, and the
15 s timeout already absorbs brief stalls. Control responsiveness never replaces
backend progress checks. Once any interruption is committed, late heartbeats can
reconcile evidence only; they cannot remove that fence.

## One cleanup path

The supervisor uses its existing direct participant/worker interruption path and
sends its independent `InterruptionReport` to the controller. A coordinator that
observes controller or supervisor process exit invokes its local safety handler
immediately and fans out to its owned workers using existing lifecycle/safety
commands, without waiting for agreement or a new command. It reports the local cause
with a stable `ErrorReport` ID when a supervisor is reachable; it never impersonates
the supervisor in `InterruptionReport`.

| Local work at failure | Required action |
| --- | --- |
| Configuration / Setup / Ready / Starting before activation | Fence the affected preparation/start attempt; cancel pending execution and release prepared resources through existing cleanup. Stop manual preview if owned; Visual Stimulus retains/returns to valid Idle where possible. Do not invent a trial or an Interrupted session. |
| Activated session, including between trials | Permanently fence the session and prevent further trials. Stop active producers promptly, return Visual Stimulus to Idle, drain only admitted eligible recording work, then finalize/sync/close and release resources under existing limits. Preserve completed trials; do not fabricate an empty one. |
| Already stopping/finalizing or cleanup blocked | Join the existing cleanup operation and reconcile retained evidence. Preserve its original deadlines, producer cutoffs, output results and unresolved obligations. Never reopen outputs or reset the cleanup budget. |

Deduplicate identical commands by their command IDs. Independent detectors converge
on the same registered controller generation and affected Setup attempt/session/trial:
atomically fence future execution and enter the owning lifecycle cleanup once. Keep
each distinct cause for diagnostics without duplicate physical stop/close operations.
A repeated trigger never extends a deadline; use the earliest applicable absolute
deadline. Late original evidence may resolve blockers under E06, never erase Interrupted.

Controller or supervisor loss triggers E08's automatic full shutdown: after bounded
cleanup the survivor shuts down descendants and exits, without waiting for an operator.
It notifies the persistent launcher, which also observes authority process exits and
owns the final `application_shutdown_backstop_s` deadline (windows-launch.md). No
replacement authority, New session, Setup or Start is allowed. Preserve unfinished
markers/emergency evidence; outcome reconciliation and reservation completion belong
to the next application startup under E04. After controller loss no CephVR process
can stop a paired SpikeGLX run; the emergency report names it for manual stopping (E12).

Producer-local admission cutoff remains authoritative under E11. Detection, command
issuance and receipt are not substitute camera/render cutoffs; recording drain uses
actual retained producer evidence. Missing evidence stays unconfirmed. Keep health
and safety delivery separate from blocking SDK/encoding/file operations. Graceful
cleanup cannot guarantee completion if the owning process/data path is stuck; E06
retains unresolved ownership/output results through forced application exit and
next-startup recovery. No automatic restart or session resumption is introduced.
