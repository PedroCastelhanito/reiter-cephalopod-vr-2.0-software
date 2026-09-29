# Acquisition diagnostics and repeated warnings

Governing decisions: [A04/A07/A09/A10](../../docs/architecture/acquisition.md),
[E04](../../docs/architecture/supervisor.md#e04) and
[E06/E08](../../docs/architecture/system-contracts.md). These are declaration bindings;
no diagnostics producer, aggregation runtime or logging implementation is supplied.

## Stable catalogue

The following case-sensitive CephVR codes are constants, not SDK message matching.
SDK native error codes and concise details remain supporting evidence. This catalogue
covers image/native-metadata/recording diagnostics; configuration adjustments and
explicit Setup prompts retain their existing typed contracts. Do not infer
lost CephVR source IDs from native counter gaps or transport statistics.

| Code | Meaning and detailed recording |
| --- | --- |
| INVALID_IMAGE | Received SDK-failed/corrupt image; reference that received frame, retain native cause, and record its dropped frame line. |
| NATIVE_COUNTER_GAP | Comparable native counters show a forward gap; reference the new received frame and include previous/current counter values and only a defensible missing native count. |
| NATIVE_COUNTER_DISCONTINUITY | Unexplained reset/backward/jump; reference the new frame, preserve previous/current values and rebaseline under A09. No guessed missing count. |
| NATIVE_TIMESTAMP_UNAVAILABLE | Optional camera timestamp absent or its units unknown; record the transition into unavailability, with a frame reference only when observed on a received frame. |
| NATIVE_COUNTER_UNAVAILABLE | Optional native counter absent/unusable; same transition rule and no invented value. |
| TRANSPORT_SUMMARY | A07's one capture-run counter summary, using the exact existing SDK summary binding; unavailable fields remain explicit. Informational, not itself a warning occurrence. |
| TRANSPORT_COUNTERS_UNAVAILABLE | Operational warning when an optional summary counter cannot be interpreted/read; the detailed evidence is the existing TRANSPORT_SUMMARY, not another duplicate completion-line diagnostic. |
| NO_VIDEO_FRAMES | A07's operational warning for the allowed all-recording-frames-dropped outcome. Retain existing frame/timing evidence; no duplicate per-frame drop diagnostics or claimed playable video. |

Known documented counter wrap follows the adapter's declared semantics; it is not
an unexplained discontinuity. Optional timestamp/counter warnings count transitions
into unavailability (one at preparation if already unavailable), not one occurrence
for every subsequent missing value. A return to usable metadata permits a later
new unavailability occurrence. Invalid images and genuine new counter gaps count
individually. Counts are condition occurrences, never a universal lost-frame total.

The existing SDK exception catalogue in [SDK mappings](sdk-mappings.md) retains fatal
DEVICE_UNAVAILABLE, SDK_ACCESS/STATE/TIMEOUT/FAILURE, INVALID_LAYOUT and resource/setting
categories in their operation context. Unknown failures are not reclassified as
nonfatal diagnostics. Required device/storage/accounting/logging failure reports go
directly to supervisor immediately under E06, independent of warning publication.

Adapter NativeMetadataSupport returns typed NativeMetadataWarning values for optional
metadata absence, transferred as CameraResolvedState.metadata_diagnostics. The legacy
display strings derive from those same values and are never parsed or counted again.
The worker owns occurrence identity/counting; configuration adoption and warning
forwarding cannot manufacture a second occurrence from one adapter observation.

## Bounded aggregation

Use the existing camera worker and control reporting path. Each producer
retains one warning aggregate per (exact producer generation, camera role, work scope,
code). Work scope is the exact trial or Setup/session context; Configuration work uses
configuration revision and preview_run_id when applicable. Native SDK detail does not
create another key. Only the responsible camera worker counts its events; its recording
thread owns NO_VIDEO_FRAMES. Coordinator/controller forward absolute counts, never sum copied
reports. A stable warning_id is allocated on the first occurrence and reused.

The typed acquisition_occurrence on Warning carries source, scope, code, cumulative
count, first/last host observation and latest native code/detail. Count is positive,
first <= last, and neither regresses for the same warning ID. Use bounded native code
(64 UTF-8 bytes) and latest detail/message (1,024 bytes), truncating descriptive text at
a character boundary with the existing marker. Preserve detailed evidence in the
completion line's grouped diagnostics and frame lines' `invalid_code`, not in this
status. Do not truncate stable CephVR codes. No list of every occurrence or unbounded
SDK-code buckets in memory.

Each complete report holds at most the eight catalogue entries for a single exact
producer/camera/scope, and only warning-applicable entries can actually appear.
Retain current scope plus the latest completed trial's aggregates per producer/camera
for status; replace the latter at next completion even if empty. Fresh Setup clears
old status. Preserve original context on historical entries; do not imply a prior
warning is current-trial evidence. Existing command-result/incident retention remains
separate. Counter/revision overflow is an explicit reporting failure, not wraparound.

First occurrence makes a report eligible immediately on the existing control/report
executor. Later repeats only dirty the retained aggregate: send the newest complete
view on the existing heartbeat cadence, and at operation/trial completion. No extra
poll timer, per-frame RPC, modal acknowledgement or capture-thread logging call.
Only one immutable outgoing report and one coalesced latest pending view per scope;
never mutate an in-flight request. A new code during an in-flight send becomes the
next prompt update. "Prompt" means dispatch without waiting for the periodic cadence,
not a guaranteed UI latency. A count update never refreshes data-progress deadlines.

## Wire delivery and reconciliation

The camera worker sends WorkerWarningReport to the coordinator's ReportWorkerWarnings.
It contains exact WorkerContext, per-scope monotonically increasing warning_revision
and a complete repeated Warning view. Coordinator verifies registration, camera and
scope, preserves producer fields, and forwards AcquisitionWarningReport through
controller ReportAcquisitionWarnings on the existing endpoints. The coordinator
adds its own BackendContext, not a new scientific/event transport. Snapshot warnings
reuse those same Warning objects. Backend GetState and worker GetState retain the
matching views for reconciliation, including empty views when a scope has no warnings.

ReportReceipt means accepted state, not a new occurrence or file durability. Duplicate
revision/payload is idempotent; stale revisions cannot regress counts, changed payload
under the same revision is rejected. Do not add counts on retries. Reports from a
retired generation or mismatched scope cannot update current state. Use existing
bounded control-report transport and failure rules; a pending latest-value update may
replace an unsent intermediate warning view but never drop a required frame-log diagnostic or
fatal error. Reconciliation queries existing state rather than replaying a warning
history. Scope completion flushes the final aggregate through normal completion
reporting, without a new deadline or file-validation gate.

Aggregation adds no new event types or periodic warning entries to E04 central logs;
existing Setup-override/error logging retains its owning rules. Warning occurrences and
count changes use the status path; scientific per-frame details stay in the frame log.
Saving disabled still permits operational warnings, but creates no camera scientific
history or diagnostic files. A known required persistence failure remains fatal;
aggregation never conceals it.

## Frame-log mapping

When saving, the recording thread keeps one grouped entry per code for the completion
line's `diagnostics` ([frame_log_schema.toml](frame_log_schema.toml)): count, first/last
host observation, first referenced frame and details from the first occurrence. The code
must fit 64 bytes unchanged. Details start with `sdk_code=...; ` when available,
followed by concise SDK/context text within 1,024 bytes, truncated at a character
boundary with ` [truncated]`. No SDK code uses the stable-code field. Per-frame
invalid-image causes also appear as the frame line's `invalid_code`; ordinary recording
drops are represented only by `dropped = true`. TRANSPORT_SUMMARY values go to the
completion line's `transport_summary` object. No sidecar file, writer process or
output-file validation is introduced.