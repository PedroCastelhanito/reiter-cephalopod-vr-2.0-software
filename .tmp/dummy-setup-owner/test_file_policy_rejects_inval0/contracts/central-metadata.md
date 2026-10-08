# Controller-owned central metadata

Authority: [E04](../docs/architecture/supervisor.md#e04), with
[E05/E08](../architecture.md#e05). The private controller writer implements this contract.

## Submission and completion

One serialized background writer inside controller owns SESSION_CONFIG.json, SCHEMA.json,
central per-trial LOG.json and SESSION_LOG.jsonl. The trial LOG is created at trial start
and replaced atomically (`replace_json`) at trial end with the outcome and output index;
SCHEMA.json is generated at Start from the writers' schema definitions. Backend scientific files, stimulus_LOG and
configuration-history saves retain their existing owners/contracts. Validate exact
session/trial/preparation, schema, reserved destination, byte size and operation identity
before bounded local admission. No arbitrary paths, output scans or scientific payloads.
The [typed local interface](metadata-writer.pyi) replaces the removed persistence RPCs.

Read [metadata] only from experiment_config.toml: max_pending_operations and
max_pending_bytes bound accepted-unsynced work including active I/O; the byte limit
must accommodate at least four maximum control messages. completion_timeout_s
covers admission, waiting, write/append, flush and OS sync from original submission.
Convert to positive exact integer ns and bind ControlPolicies.metadata_timeout_ns.
Queue limits stay controller-local, checked against fixed experiment policy; no duplicate
supervisor queue. Queue-full rejects immediately with persistence failure; never block
control/health or evict accepted records. Other controller I/O cannot borrow/extend these
budgets. Immutable payload bytes remain bounded until completion; no per-event file reread.

Admission is not persistence. Writer publishes exact-operation MetadataResult through
the existing bounded controller event path after sync or a known failure. `submit`
binds exact WorkContext/OperationContext to the session and returns a noncancellable
retained Future; the controller awaits it without blocking its state loop and records
the completion under its original deadline. A synced write after the deadline retains
`deadline_met=false`. Failure
to deliver mandatory evidence follows E06, not an extra unbounded callback queue. Snapshot
and next-trial gates use these results. Retain only active/required reconciliation state
under existing bounds, not an ever-growing operation history. On uncertain write/timeout,
never retry an append or start another writer. Verified late completion can resolve
uncertainty but cannot reset a deadline or undo interruption. File failures follow E06's
incident classifier; loss of required bounded central bookkeeping is blocking.
The private writer accepts each new controller-owned metadata operation once; the
controller retains its Future for uncertain completion and calls `retire(command_id)`
only after consuming exact terminal evidence. A retired ID is never resubmitted to
the writer; external command retries remain in the controller command ledger. `seal`
admits no further writes and returns only after its dedicated sentinel drains the
queue and closes owned handles within the caller's remaining finalization budget;
its Boolean result is not a fabricated CleanupReport or MetadataResult.

## Closure, reservations and authority loss

Controller seals writer admissions only after required final session events are admitted,
drains/syncs/closes files under original finalization deadlines, and records one local
writer-cleanup result for its own reservation release. Its work/operation must match
the controller's session; resource central_metadata_writer is released only when
no call/handle can still write. MetadataResult entries summarize each required file's final
persistence under that finalization operation, not every historical append. A required
unknown/failed result cannot become SYNCED because the process exited or Abort was chosen.
Unstarted files retain their truthful states; no fabricated closure. For cancelled/
failed unactivated Setup, controller records that no central writes were admitted and
no file handles remain for that attempt; there is no session-log sync obligation and
no metadata file is created merely to produce cleanup evidence. The session writer's
seal applies to that exact attempt/session, not later authorized Setup work.

The controller's local reservation release requires this writer result plus verified
backend Cleanup and the original reservation; only clean completed obligations permit a
complete marker. No extra per-write metadata RPC or polling gate. Missing writer closure
preserves a blocker and unfinished marker. Failure never justifies another writer
taking over its files or extending shutdown deadlines.

A Setup that failed or was cancelled before activation keeps every written file: after
writer seal, `close_unactivated` writes the marker complete with `outcome` `not_activated`
(no session log is expected) and releases the lock; the caller then clears the pointer.
Startup treats a pointer with such a marker as finished and clears it without a report.

On controller loss, supervisor uses its independent emergency report and bounded E08
shutdown. Preserve unknown central metadata state and unfinished marker; do not append
or repair normal files in the lost controller's place. Startup reconciliation requires
controller-held exclusive reservation, supervisor-confirmed old-process absence and the
existing recovery authorization; the new controller performs any permitted repair and
marker/lock updates through this same serialized writer. The single owner-private
unfinished pointer identifies the exact old session; an immutable prior-launcher
receipt proves outer-job emptiness for those old generations. `open_existing` never
creates a path, `adopt_recovery_log` requires exact previously validated file
identity/size, and a new `RECOVERY-UUID.json` report can preserve corrupt evidence.
`finish_recovery` compares the original bounded marker fingerprint before marking
complete. Missing proof or changed evidence retains the pointer and blocker.
Supervisor owns emergency reports.
