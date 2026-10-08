# Tracking feedback generations and queue credits

Authority: [A06](../../docs/architecture/tracking.md#a06), R1A, with
[V25/V26](../../docs/architecture/visual_stimulus.md#v25), T08/T19 and E08. This is an internal
contract for the existing ordered result/credit pipes, not another queue, service,
worker or runtime implementation. [data.proto](../cephvr/visual_stimulus/v1/data.proto) owns the types.

## Identities and ordering

| Identity | Scope and meaning |
| --- | --- |
| attachment_generation + stream_id | Prepared transport and registered source. Changed attachment requires the existing preparation/handshake, not silent counter reuse. |
| reset_generation | Carried by every FeedbackResult and credit: canonical decimal positive uint64, strictly increasing for each locally committed reset in the same attachment/stream, including new trials. Never reset/wrap it within that attachment. |
| processing generation | Internal only: the reset_generation of the latest processing reset, naming the current flow baseline/filter. Not on the wire; delivery-only resets retain it. |
| entry_sequence | Positive uint64 on every FeedbackEntry; strictly increases for the same attachment/stream. Identifies transport admission/credit, not a source frame, result counter or file record. |
| result_sequence | Existing FeedbackResult scientific ordering; not a credit token. |

The source assigns each identity once. Source/entry/reset counters are not inferred from
arrival time. Their limits are checked; exhaustion fails explicitly rather than reusing
an identity. No per-frame identifier is added to controller RPCs or central metadata.
FeedbackResult.work must be the exact released active trial; a session-only or another
trial's result cannot establish a current baseline. Each trial starts a new generation;
the attachment-scoped ordinal continues across trials, so gaps between trial files occur.

## Generation changes

On each accepted A06 reset, tracking gates old result publication, retires old pending
results and allocates the next reset_generation. There is no separate reset entry: the
next published result carries the new value. Result overflow alone preserves the flow
baseline, temporal hints, filter, input queue and eligible pose/geometry history. Trial
start, camera gaps or input-age/overflow also start a new processing generation with a
fresh flow baseline/filter; a joined processing cause wins over delivery-only overflow.
Tracking sends a result, invalid or baseline-only when necessary, for every evaluated
frame, so a new generation becomes visible to Visual Stimulus without an acknowledgement round trip.

Visual Stimulus first checks registered attachment/source/stream and the current trial. A result with
a greater reset_generation than Visual Stimulus's current one is the reset: discard/account for
unapplied older-generation entries, including already captured batch entries, preserve
movement already applied, and apply only results marked usable (baseline-only after a
processing reset; usable at once after delivery-only overflow). Visual Stimulus need not
have seen every intermediate generation. A lower generation is retired and cannot regress
state. Ordinary results retain the existing trial/age/validity checks.

V26 staleness is a local Visual Stimulus disposition. It neither advances generations nor calls
tracking control. A fresh valid result can resume Visual Stimulus in the same generation, using only
its explicit source interval; retained filter state does not authorize catch-up motion.

## Calculation continuity and publication boundary

The existing movement owner serializes the generation change with result construction/
record admission/publication. A delivery-only reset does not invoke method reset() or
invalidate in-flight native work: it remains tied to its original processing generation.
New input pairs retain contiguous source lineage in that generation. Native owners never
relabel a lease or retained image to match a transport reset. A newly constructed result
carries the current reset_generation; an already constructed/recorded older-generation
result is discarded/accounted, never retagged or replayed. A dropped result does not
undo the filter update that was validly computed from its source pair.
Saving retains those calculations and discard evidence. Visual Stimulus applies only the explicit
interval of a surviving valid result, never a summed interval across missing deliveries.

Pose observations keep their original identity and processing-generation provenance.
Same-trial/source/preparation pose/geometry remains eligible across processing resets
subject to T09 source-order, invalidity and host-monotonic age checks. Such reuse does not
permit a flow pair/filter continuation across a source gap. Trial/source/preparation
changes clear pose history and retire incompatible in-flight work; native ownership
and cutoff rules remain unchanged. No unbounded pose or reset-history buffer is added.

## Credits and storage lifetime

FeedbackCredit names attachment_generation, stream_id, reset_generation and the exact
entry_sequence. Every admitted result consumes one slot. Capture into the finite render
batch or discard releases a credit once; processing that same batch later cannot
release it twice. The receiver cannot grant capacity for an entry it never
received. Unsent entries retired locally are reconciled in the sender's own ledger.

For the current generation, accept a credit only for its matching outstanding entry;
an identical duplicate never increments capacity. Unknown/future entries or conflicting
identities are protocol failures. A credit for a retired generation is obsolete cleanup
information and never replenishes the current generation. On reset retire the old logical
ledger and initialize the new generation within the existing A06 capacity; do not add old
credits to it. Sender, pipe and receiver still share one pending-capacity budget; the
finite captured render batch has the separately declared same-count bound.

Logical retirement is not native memory release. Include retired in-flight pipe writes,
borrowed views and captured batches in prepared byte/resource bounds until completion.
New-generation admission cannot overwrite them, grow a rescue queue or exceed physical
prepared storage. An in-flight write remains immutable. An unknown native completion or
exhausted required resource uses existing progress/failure rules. Generation changes never create an allocation loop.

## Scientific history and cutoff

When saving, admit a reset line with its reset_generation and causes for every locally
committed reset before any result carrying that generation. Lines keep ordinal order even
when overflow drops every result of an intermediate generation. Failure to admit required
evidence follows E06. Do not imply Visual Stimulus received/applied a dropped result; Visual Stimulus's existing
evidence owns its actual observations. Saving Off promises no full scientific
history, while administrative reset/failure handling remains active.

At trial cutoff, gate result application/publication under E11/V25. Late native/pipe
completion cannot authorize feedback outside the trial. Preserve actual admitted result
and discard evidence, return/reconcile owned credits once, and retain unreleased buffers
until completion. The next trial starts with a new reset_generation and reset line, while
attachment-scoped counters continue. File completion, native release and participant
Stopped/Finished remain distinct under their existing contracts.
