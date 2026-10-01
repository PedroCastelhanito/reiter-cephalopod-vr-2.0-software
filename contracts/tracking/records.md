# Scientific record schema

Authority: [T09/T15/T17/T19](../../docs/architecture/tracking.md#t09).
[record_models.py](record_models.py) is canonical; tracking-record.schema.json is generated
from it. Each TrackingRecord is one `<prefix>_tracking.jsonl` line under the
[recording contract](recording.md). [record_codec.py](record_codec.py) provides pure line
encode/decode helpers; it performs no file I/O, scan, sync or runtime work. All readers
additionally enforce the cross-record rules below; structural JSON validation alone
cannot prove coverage or closure. Bounds are checked before allocation/base64 decode.

## One header and bounded backwards references

The first line is exactly one Header. Its identity binds session/trial, tracking
process, writer/configuration/preparation generation and acquisition allocation. Header
contains canonical PreparedMethods JSON and resolved TrackingSettings in standard Protobuf
JSON (standard lowerCamelCase field names, uint64/int64 decimal strings, unknown fields
rejected); no native handles, attachment nonces or ephemeral paths. Validate embedded JSON
with its owning schema/Protobuf and the same bounded strict JSON parser. Hash the exact
UTF-8 PreparedMethods text and compare prepared_methods_sha256. Preserve immutable bytes.
Central E04 logs keep allowed filenames/resolved setup, without asset hash/package dumps.

Frame IDs are A09's uint64 per-camera/per-trial IDs, which also supply source order;
there is no second frame counter. In FeedbackResult's existing string fields encode
them as canonical unsigned decimal (no sign/leading zeros, except "0"). Resolve camera
and trial from the prepared source/work context, never treat these as global UUIDs. Preserve host receipt and resolve exact
camera/layout against Header's prepared allocation; do not create guessed device timestamps.
Retired/cutoff-excluded pose completions may be recorded with their true disposition but
cannot enter current history. Result references to poses are validated against published
observations of the same trial/source/preparation, source order <= newest movement
frame, completion <= selection time and exact source receipt/age arithmetic under T09.
PoseObservation.reset_generation is the reset_generation of the latest processing reset
when it was computed; it need not equal a later result's generation. Completion means
the immutable pose/geometry pair is ready, including geometry work; dense geometry is
not saved. Retain invalid observations; do not repair a missing/newer-invalid pose by
using old-valid, mutate retained pose records or accept another source.

The record stream is append-only. The Header precedes all lines. Each Reset line names
the new reset_generation, its causes and observation time, and precedes every result
carrying that generation; the file-scoped trial supplies the exact WorkContext. The
first Reset has cause trial_start. A reset whose only cause is result_overflow is
delivery-only; any other cause also starts a processing generation. Reset generations
strictly increase within the file; gaps between trial files are allowed because the
counter is attachment/stream-scoped (the [delivery contract](feedback-delivery.md)).
When saving, every locally committed reset has its line, including one whose results
were all dropped before Visual Stimulus delivery. A result's reset_generation equals the latest
preceding Reset line. Result IDs are unique; result_sequence is monotonic under the
adopted feedback boundary. Late old-generation evidence can be retained
only as excluded/discard accounting, never as newly usable movement. Same-binding pose
completions are the explicit exception: processing-reset provenance alone does not retire
an observation under T09. Actual record count
bounds references and lookup storage; use bounded online windows plus counters, not a
whole-trial in-memory history. The external reader may use bounded disk-backed indexes.

## Reuse FeedbackResult without a second scientific schema

A result embeds the exact serialized cephvr.visual_stimulus.v1.FeedbackResult as canonical base64.
The existing [data.proto](../cephvr/visual_stimulus/v1/data.proto) remains its sole wire definition. The tracking
boundary validates typed messages before encoding, checks finite values and all required
fields, then serializes once; the same result bytes can feed Visual Stimulus. Saving does not depend on
whether Visual Stimulus consumes the result. There are no dense arrays or arbitrary estimator dictionaries.

The external reader decodes within the record byte limit and parses against the exact
supported descriptor. Reject unknown fields/enum values, mismatched identity, duplicate
channel IDs or nonfinite values. Match all channel IDs, quantity types, units and coordinate
frames to PreparedMethods and the accepted [pipeline catalogue](pipeline-catalogue.md). Valid movement
requires a positive valid source interval with newest frame/time agreement and ordered
contributing source identities; invalid/baseline-only results carry no usable movement
values. A valid pose alone cannot imply a valid locomotion estimate. Required timing fields must not be
fabricated to satisfy a schema. Movement produced_host_ns >= newest source receipt and
pose selection time. Missing/invalid/stale pose cannot accompany valid dependent movement.

PoseUse manual disposition names the prepared fixed geometry and has no automatic age.
Automatic selected observations retain check/source/age/limit; a missing one has absent
identity/age, not zeros. Candidate quality ranking remains T17: records carry count,
selected score, tie flag and triplet, rather than every rejected contour or image.
MovementResult.stage_evidence contains only payloads validated against the concrete
evidence schemas declared in PreparedMethods.stages under [T27](stages.md). Initial
geometry evidence records T26 coverage per required region. Method IDs in pose records
resolve to the prepared pose implementation. Estimator-specific quality definitions
are bound by the [pipeline catalogue](pipeline-catalogue.md#evidence) under T12/T04;
unknown schemas cannot bypass validation through a map.

Discard batches name source frames or result IDs with reason and observed time. Split
large batches into bounded records; no truncation, unbounded ID arrays or fabricated
identities for frames never delivered. Acquisition owns native camera gaps/counters;
tracking records its known rejected inputs and reset cause. A06 result overflow records
which pending results were retired; it never removes their already-admitted scientific
records. Publication to Visual Stimulus and recording admission must be ordered so that recording
failure cannot silently claim complete tracking history.

## Cutoff and completion

Header's trial interval is [T,normal_end). Input membership uses A09 host receipt. Movement
intervals must lie entirely within the actual trial interval; late processing completion
may be recorded but cannot authorize feedback outside the current trial. At cutoff, gate
publication, clear waiting pose work, complete/reconcile in-flight jobs, drain required
record admission and append exactly one Completion. It counts all earlier pose/result/reset/
discard records (including excluded completions); verify counters incrementally without
rereading disk. Completed outcome requires scheduled end; Interrupted uses the confirmed
cutoff. No further scientific records follow Completion. Final sync/close evidence is
reported through E06, not asserted by the completion record itself.

The schema/codec checks here are local declaration tests only. Native recording, semantic
stream validation, file reading, device inference and crash durability remain unimplemented.

## Initial proxy cross-validation

For estimator evidence, use the registered schema and then
[validate_proxy_evidence](pipeline_catalogue.py) against the exact prepared pipeline.
Apply the [catalogue evidence rules](pipeline-catalogue.md#evidence) and compare every
valid filtered_average channel to the paired FeedbackResult, including quantity, units,
source interval and validity. A baseline has no fabricated flow estimate. Check filter
seed/continuation/clear behavior across contiguous results/Reset lines using the
[proxy equations](water-flow-proxy.md); a continued state cannot cross invalid input,
a source gap, trial, preparation or processing reset. A delivery-only Reset may retain
a continued filter across computed contiguous pairs, including saved results
subsequently discarded from feedback; use the Reset causes rather than treating every
generation change as a filter clear. Retain failure evidence; a reader rejects
unsupported historical schemas.
