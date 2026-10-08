# Tracking preparation, lifecycle and resource binding

Authority: [T02–T09](../../docs/architecture/tracking.md#t02), E05/E06/E08/E10/E11,
A03/A04/A06 and [T19](../../docs/architecture/tracking.md#t19). Reuse the existing backend
lifecycle RPCs; the [tracking preparation service](../cephvr/tracking/v1/services.proto)
only binds late-resolved data attachments and reads retained preparation evidence.
It is hosted on the existing tracking process/port, not another service process.

## Setup dependency handshake

The shared [data-preparation handoff](../data-preparation.md) is the canonical
controller/acquisition/tracking/Visual Stimulus ordering. It binds protected early reports,
BindData, acquisition attachment confirmation and Visual Stimulus Setup's feedback attachment.
Reports and retained reads are available before final Ready; no readiness cycle or
polling loop substitutes for a missing handoff.

Tracking publishes its preparation generation when Setup is admitted. BindData validates
command authority, session/configuration/preparation generation, selected camera role,
buffer kind TRACKING, exact consumer process and allocation/layout/synchronization identity.
Same request/contents is idempotent; changed content under that identity fails. After
successful attachment it reports data_attached and the exact AttachedResource; command
admission alone is insufficient. Failed/partial attachment is unwound under E06.

Resolve typed method settings and the pipeline once. Prepare private/native buffers,
validate device capabilities, provider placement, byte/time limits and method assets.
Retain PreparedMethods with actual versions, resolved settings and binding identities.
For closed loop publish the protected feedback descriptor once its listener/resources
are prepared, before waiting for Visual Stimulus's peer handshake. Open loop allocates no unused Visual Stimulus
queue. Disabled tracking loads no methods and creates no data/output obligations.

Send Ready only after required input and feedback attachment checks, selected methods,
geometry/estimator/channel bindings and enabled-output reservations all pass. Partial
preparation reports never substitute for Ready. GetPreparation reads the same retained
state for bounded reconciliation; normal progression uses pushed reports. It creates no
resource and cannot revive a retired preparation. All reports/reads obey adopted message
and document bounds; exclude native names/nonces from public snapshots and logs.

Asset hashes and method identities belong to detailed tracking evidence when saving;
ReadyReport central asset_filenames follows E04 filename-only rules. Cancellation gates
publication, retires preparation, reconciles native work and confirms cleanup under E06.

## Trial lifecycle

PrepareTrial resets pose/history, movement/native temporal state and per-trial counters;
prepare no source interval spanning trials. Allocate finite reset/completion bookkeeping.
No recording file is opened before authoritative T. ScheduleTrial adopts exact T/end,
reserved prefix/paths and Visual Stimulus-owned duration; ReleaseTrial requires the existing deadlines.

At T, accept only frames whose host receipt is in the trial interval. The first admitted
frame establishes source baseline and the trial's first reset generation, carried by
every A06 result from then on. Start evidence is completion of the first frame evaluation
(including a legitimate baseline-only/invalid result), with actual host observation time
and source frame ID. Do not require a scientifically valid movement result to become
Started, and do not report Started from thread launch or the scheduled time alone.
The shared start-evidence deadline still detects lack of required activity.

Automatic pose history and pending work follow T09. Result-queue overflow is a delivery-
only reset: flush pending results and advance reset_generation, preserving contiguous
native flow, filter, input work and eligible pose/geometry history. A source-frame gap,
input-age/overflow uses the same owner but additionally resets flow/filter and pending
movement input, starts at the latest available frame and rebuilds the baseline.
Retain eligible same-trial/source/preparation pose pairs and pending pose work under T09;
clear them when those identities change, not merely on a feedback/processing reset. The [delivery contract](feedback-delivery.md) binds numbered reset
generations and queue credits; when saving, every committed reset has a Reset line even
when overflow drops all of its results. The water-flow filter additionally clears/seeds under
[T45](water-flow-proxy.md#exponential-smoothing-and-source-interval-meaning); fin-flow explicitly
reuses this same filter/reset behavior under [T04](fin-flow.md).
Discard incompatible movement completions by trial/preparation/processing generation and record their
actual exclusion when saving. No cancellation frees a buffer still used by a native call.

At normal cutoff/Abort follow the stop ordering below. E06 aggregate cleanup and
Interrupted outcomes apply without extending trial duration or auto-resuming.

### Producer cutoff, late work and finalization

Tracking owns its local admission/publication cutoff under E11. At normal end it is the
scheduled end; on interruption it is the observed local sealing time capped by that end.
It is neither the controller's request-issuance time nor the camera's separate producer
cutoff. Preserve the original interruption time for deadlines. Required camera membership
is checked on frame admission through A03/A09; tracking cannot extend it by processing
later or by substituting its own later cutoff.

| Order | Tracking obligation |
| --- | --- |
| Seal | Atomically gate new movement/pose work and result publication for this trial; retain the cutoff once. Retire waiting pose work. Native cancellation does not free a lease. |
| Reconcile | Finish or safely cancel in-progress copies/native work. Stop reading the acquisition ring; unread frames need no release under A03's seqlock. Do not run new estimates merely to empty the ring. |
| Account | Preserve already-admitted records. Record known excluded frames/results and late pose dispositions under the rules below. Do not fabricate identities for input never acquired by tracking. |
| Stopped | Report actual activity-stop time only when producer computation/copy activity is confirmed stopped, along with the separately retained admission cutoff. Merely closing the publication gate is not activity_stopped=true. Do not wait for writer sync/closure. |
| Finish outputs | After all producers reconcile required evidence, seal writer admission, drain, append incremental completion counts, sync/close and report exact OutputResult before Finished. No disk reread or post hoc file validation. |

A result becomes externally eligible only through the host's bounded commit step: check
trial/generation/cutoff, admit required compact evidence when saving, then expose it to
the feedback path. Serialize this short ownership transition with reset/cutoff gating;
no device call, disk sync or waiting for UI/pipe capacity occurs inside it. If a reset
or cutoff wins before commit, discard the computation and account its known source frame
IDs instead of manufacturing a usable result. If evidence was already admitted but
feedback is subsequently retired, retain that result record and append its actual discard
reason; never erase or relabel it as applied. Open loop uses the same evidence/generation
checks without a Visual Stimulus queue. Writer admission failure follows E06 and exposes no dependent
result. Independent automatic pose follows its existing record-before-history rule.

An in-flight pose completion after cutoff is recorded as cutoff_excluded when saving;
it cannot enter usable history. A late pose completion from another trial/source/
preparation is retired_generation; a feedback or movement reset alone does not retire
same-binding pose work. Neither excluded case can restore old geometry or filter state. A pose record already published before the gate
remains truthful history. Only known delivered/admitted identities enter discard records;
source frames never delivered to tracking retain acquisition-owned accounting.

A source ring can remain sealed with unread frames after tracking has stopped admission.
Its acquisition owner resets it under A03 once the producer is quiescent; recording is
unaffected because it never uses the ring. Tracking releases its own copies/views and reports its registered
resource obligation. Ring quiescence/release, scientific file closure and backend Finished
remain separate proof. No later trial can reuse the ring before its owning reset checks.

If native completion misses the Stopped deadline, report the failure/unconfirmed stop and
retain resources under E06; do not falsely report success or wait silently. The fixed
cutoff is not moved by late completion. Saving Off removes the writer/output steps only;
work reconciliation, native ownership and required lifecycle evidence still apply.

## Progress and bounds

Separate control heartbeat from completed source evaluation, pose-job completion,
movement completion, writer append and durable sync. The first two compute timeouts are
explicit file-only limits; a job outstanding beyond its configured budget is E06 failure.
Only real completion advances that stage's progress; heartbeat/admission does not. Idle
pose with no input is not independently stalled; required source silence is acquisition's
existing responsibility. Valid-looking numerical output is not proof of useful progress.
Budget jobs, history, private image copies, result pipe credits, records and native buffers
at Setup, including in-flight work. Refuse allocations exceeding max_native_bytes.

Methods/native storage are owned by their worker thread. A timed-out native job may keep
its leases while control reports failure; don't release or reuse them until confirmed
completion or process teardown under E06. Close order: gate publication, drain/cancel and
reconcile work, destroy method sessions/buffers, detach result/input transport, then retire
preparation resources. Windows Job/process cleanup helpers remain E08-owned. No daemon exit,
PID disappearance or pipe EOF alone proves required scientific file closure.
