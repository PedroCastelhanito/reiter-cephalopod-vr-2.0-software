# Detailed evidence format and offline interfaces

Authority: [V12](../../docs/architecture/visual_stimulus.md#v12), [V13](replay.md) and
[V28](../../docs/architecture/visual_stimulus.md#v28). The canonical line definitions are
[evidence_model.py](evidence_model.py); [evidence-record.schema.json](evidence-record.schema.json)
is generated from them. The experiment backend writes the recipe and evidence.
[Offline interfaces](evidence_types.pyi) declare the analysis software's reader/export
boundary; no replay renderer or export CLI belongs to the experiment backend.

## JSON Lines file

With Save Visual Stimulus data On the renderer's recording thread writes `<prefix>_stimulus_frames.jsonl`:
UTF-8 JSON Lines, one EvidenceRecord per line, each ending in `\n`. Use compact JSON
with Unicode retained, no NaN/Infinity, no duplicate object keys and no arbitrary
object deserialization. There are no envelopes, length prefixes, checksums, sequence
numbers or custom framing; line order is file order. The GL thread builds no JSON.

Append only; never rewrite an earlier line. OS-sync every `record_sync_interval_s`
and at close; rendering never waits for disk sync. A reader discards an incomplete
final line and uses the complete lines that exist. Periodic sync does not guarantee
that pending lines survive a crash. Parse each line within a bounded size; JSON
nesting is limited to 32 levels for this nonrecursive grammar.

The first line is the Header. It binds the precise trial/prepared/resource/renderer
and writer identities, common trial T, required output set and the recipe content
reference to `_stimulus_LOG.json` (including its manifest and uniform layouts). The
referenced log must be published before the Header is written. Paths are relative to
the session's `protocol-data/` directory (no `protocol-data/` prefix) and cannot escape
it after normalization/symlink resolution.
Artifact names still use E04's reservation mechanism.

## Definitions and effective inputs

Build one RenderGroup line per render group in the renderer's bounded storage and
seal it after that group's submission pass and capture admission has been decided
(or the pass has terminated early). It contains one complete State, all per-output
submission observations and the capture disposition already known. Do not emit
separate attempt and return lines per output, and do not wait for readback,
encoding, storage or a later render group to fill it.

Use group IDs starting at zero and increasing without reuse, nondecreasing state
times and the exact prepared occurrence/scene/active-instance set. State is a complete
effective snapshot, not a delta requiring unrecorded renderer history. Its
`evaluation_host_ns` is the E08 host time selected for that group's state; all output
views and the group's composite share it.
Layout bindings cover all mutable shader inputs, including effective projections,
transforms, phase, appearance and per-output correction inputs. Immutable inputs
remain in the verified recipe/resources. Emit each required binding exactly once;
reject unknown, duplicate or missing bindings. Uniform words preserve the precise
IEEE/integer representation actually uploaded, using GLSL column-major order for
matrices. Word count is shape product (one for scalar) times two only for float64.
Reject nonfinite floating bit patterns. Host computations may use greater precision;
record the actual consumed representation. This does not add GPU pixel hashing.

MediaSelection identifies the actual decoded frame, including stream/index/PTS/time
base, loop/playback generation and hold disposition. Rational source/target times
avoid silently rounding arbitrary source timestamps to integer nanoseconds. Source
frames and resource IDs must resolve to the retained manifest. Effective poses use
explicit frame IDs, millimetres and unit xyzw quaternions; these are evidence of the
rendered pose, not an extension of authored arena movement scope.

The marker value is per submission attempt and follows V22; it is not a shared
scene uniform that accidentally changes every output. Replay combines recorded
state with the exact attempt's marker value using the same output pipeline.

## Late outcomes and closing line

RenderGroup is the only state-bearing line for that group. Nested submissions/captures
inherit its group_id. Append a GroupUpdate line for late readback/FFmpeg-input
observations or resolution of a recorded pending submission; it references the group
ID and carries no state replacement. Batch facts already available together, but never
wait for another outcome to fill a batch. Later groups may precede earlier groups'
updates; each update references an earlier RenderGroup line.

The final Completion line records complete accounting. A stopped-but-live renderer
writes it during normal bounded cleanup. A crash can lose unsealed groups, unsynced
lines and the closing line. Missing group or output outcomes remain unknown,
including whether a call occurred or light changed; absence never means
cutoff-excluded or not presented. Do not fabricate entry/return times, markers,
attempt indices or counts for lost observations.

Setup must ensure that one complete group (state plus the maximum prepared
output/capture observations) and the bounded late-update reservations fit
`evidence_pending_bytes`, which counts lines built but not yet written. No unbounded
collection, extra worker or per-group RPC. Exhaustion is a required-logging failure
under V12/E06. Implementation checks are recorded in the [Visual Stimulus report](../../reports/visual_stimulus.md).
Earlier drafts carry no migration promise; future incompatible deployed changes
require format versioning.

## Cross-line validation

The structural model is necessary but insufficient. The writer's coverage checks and
the offline reader use the same semantic rules:

- Require the Header first and at most one Completion, last. Reject a second header,
  lines after Completion or references to groups not yet written.
- Exactly one RenderGroup establishes each group in increasing group order. A nested
  submission identifies output_id and its actual attempt_index. A known returned/failed/
  unknown observation may establish the attempt and outcome together; returned requires
  entry and return times, failed requires a failure code, and unknown has no return time.
  An `attempt` observation declares a still-pending call; a later GroupUpdate resolves it
  once without changing identity, entry time, marker or swap interval. No repeated final
  outcome or state replacement. At most one actual attempt per output/group. Actual
  per-output attempt indices start at zero and increase. Swap times are software
  evidence only; never infer an unobserved call from the required output set.
- `cutoff_excluded` marks an output view of a group evaluated before the E11 cutoff that
  was abandoned unsubmitted, with no attempt index, entry/return time, marker or failure.
  No projector shows a trial image after the cutoff.
- Capture dispositions are independent of submission and refer to the group's one
  tiled review composite (tiles map to outputs through the recipe's ReviewEncoding
  layout). Admission, capacity drop (no free `capture_slots`) or cutoff exclusion is
  decided once per `group_id`; readback and FFmpeg-input outcomes follow admission in
  order. An admitted group carries `video_frame_index` n: the review video's frame n
  is the n-th admitted group, so indices start at zero and increase by one. A stdin
  write is not proof of encoded pixels.
- Feedback and interval lines retain the current application/disposition identities.
  Applied FeedbackEvidence references an existing RenderGroup and is written after it
  even though the application occurred before rendering. Each line keeps its result's
  A06 reset_generation; a newer generation is the reset, and discarded older pending
  results are `old_generation` lines. There is no separate reset line.
  Interval end references its existing begin and closes once at a nondecreasing time;
  a crash may leave an interval open. An `applied` feedback line names its group and
  binding, keeps every source frame ID and has `application_check_ns >= source_receipt_ns`.
  Increment array lengths/units match the prepared target declaration.
- A `Clipping` line follows each completed render group/output after the renderer's
  bounded GPU diagnostic readback resolves. It names that exact `group_id`, output,
  epoch occurrence and observation time, with an ordered set of clipped stages
  (`alpha`, `linear_output`, `device_code`); an empty set records complete coverage
  with no clipping. Capture-slot drops do not omit clipping records.
- EncoderOutcome is one final account for the composite FFmpeg process after all
  capture dispositions, including late GroupUpdates. Verify counts against earlier
  lines; absent observations remain unknown. File sync/close is reported through E06;
  a line cannot prove the later close of its own file.
- Completion counts reconcile all prior groups, attempts and dispositions (each group
  contributes exactly one state), declared cutoff and exact output set. Normal
  completion requires scheduled end; interruption records the confirmed cutoff. It
  may disclose unknown submissions; that does not make them replayable or prove
  presentation. No state evaluated outside [T, cutoff) is trial content.

Metadata for every eligible group/output is retained under V12 even when its video
sample drops. When required evidence cannot be retained, interrupt under E06; no lossy
metadata mode or unbounded rescue queue. Sync cadence/progress fields stay owned by
[worker-control.md](worker-control.md#resource-policy-binding).

## Analysis-software replay and export boundary

[ReplayRequest](replay-request.schema.json) and [ReplayReport](replay-report.schema.json)
are canonical model types. Replay reads the complete lines that exist and never
modifies source files or promotes closure. Without a valid Completion line the report
is `partial` with `last_group_id` N ("partial, up to render group N"); `full` mode
requires the complete file. Coverage ranges are half-open, sorted and disjoint within
each category; coverage may be sparse. Every Clipping line must reference an existing
group and required output and match that group's epoch and evaluation timestamp. A
full replay requires one Clipping line for every requested group/output; empty stages
still count as complete diagnostic coverage. Partial replay reports diagnostic and
missing-diagnostic ranges per output and exports only groups with complete diagnostic
coverage for that output. Post hoc file validation remains external to runtime under
E05.

Full export requires complete supported recipe/manifest/state and known returned
submissions throughout the requested coverage; reject unknown/failed/missing required
coverage rather than silently exporting a partial trial. Partial mode exports only
reconstructable groups and labels missing/unknown portions. Missing or mismatched
external content blocks affected reconstruction in either mode.
Model/renderer/compiler/shader/decode/color compatibility identifiers must match an
explicit supported implementation; a version string is not a guessed compatibility
rule. Report graphics-environment differences without claiming original-pixel equality.

The analysis renderer implements the recorded rendering pipeline and consumes its
recorded effective inputs, without live devices, tracking, random resampling or
motion reintegration. It is not part of the experiment backend.
The first lossless export binding is one PNG per confirmed output/group plus a JSON
index retaining exact trial/group/attempt timestamps and native code depth. Use PNG
RGB8 for native 8-bit codes and RGB16 for native 10-bit codes; in the latter store each
0..1023 integer unchanged in a 16-bit channel and declare `code_bits=10` in the index.
Do not scale values or introduce a video timestamp grid. Index each image by relative
path, output, group, attempt, state time, submission entry/return, dimensions and code
bits, plus the ReplayReport, using [ExportIndex](export-index.schema.json). Write only
into a new reserved export directory. This is lossless storage of reconstructed
numeric output codes, not a claim about image-viewer brightness, original GPU pixels
or emitted light.

Replay reports always keep original_pixel_equality and optical_presentation
`unverified`. Original images are not captured/hashed for comparison. Experiment
writer validation is tracked in the [Visual Stimulus report](../../reports/visual_stimulus.md); analysis reader
and offline rendering validation belong to the analysis software. Schema generation
and declaration checks alone do not validate either implementation.
