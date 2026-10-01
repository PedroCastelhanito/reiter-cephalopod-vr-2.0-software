# Visual Stimulus resource, transport and presentation bindings

Authority: [V01/V04/V11/V12](../../docs/architecture/visual_stimulus.md#v01),
[V15](geometric-correction.md), [V20](presentation.md), [V24–V28](feedback.md), E08.
These are implementation contracts, not delivered Windows/GPU providers. Feedback
attachments/messages are in [data.proto](../cephvr/visual_stimulus/v1/data.proto), resource/prepared
artifacts in [artifact_models.py](artifact_models.py), and local provider boundaries in
[resource_types.pyi](resource_types.pyi). E14 supplies configurable engineering limits; device/workload feasibility remains checked at preparation.

## Assets and provider mappings

ResourceManifest covers content fingerprints, embedded subresource identities,
dependencies, effective interpretation, CPU/GPU reservation sizes and relevant provider
compatibility. Reject cycles/missing dependencies. Keep the manifest inside the retained
PreparedTrial recipe, not a second editable asset database. Protected source ownership
and cleanup remain exclusively defined in asset-lifetime.md.

Use imagecodecs PNG/JPEG decoders and tifffile with imagecodecs for TIFF, wrapped by
one profile-checking adapter. Inspect headers/tags and exact dtype/channel/alpha before
admission; library format support never expands media-profiles.md. Preserve uint16
without an intermediate Pillow/RGB8 path. Palette expansion is explicit. Decode from
protected bytes/file adapters; do not allow pathname-only dependency reopens. Parse
GLB container/JSON/accessors with a focused importer into immutable vertex/index/material
arrays; reuse the same image adapter for embedded/external textures. This avoids importing
a general scene engine that rewrites materials or launches another renderer. Check all
lengths/offsets/strides/indices before allocation, glTF little-endian accessors and sparse
accessors by bounded materialization, and reject unsupported required features.

Keep initial media source interpretation explicit: source metadata or a complete
ColorOverride with reason. Only supported Rec.709/sRGB primaries and listed transfer/
matrix/range/chroma conventions are admitted. Unsupported ICC/HDR/transform content
requires explicit externally corrected content or a valid intentional source override,
never guessed transfer. GLB base-color semantics remain fixed by glTF. Interpretation
retains original component layout/depth, row origin, alpha, orientation and sample aspect;
resource provenance retains the provider/build and chosen conversion. Normalize decoded
planes to linear premultiplied RGBA32F through color-pipeline.md. Gray replicates RGB;
none alpha means 1; preserve actual alpha, discard documented padding only. FFV1 plane
order/endianness follows media-profiles.md; H.264 uses its explicit YCbCr interpretation.

PyAV contexts remain on bounded renderer-owned CPU decoder threads. Each independent
playback needs its own context/cursor; never share a mutable demux cursor across instances.
At Setup, a protected-source index pass obtains every supported frame's presentation
interval, decode/seek anchor and endpoint; retain rational time base and source-frame IDs.
Use packet/index metadata when it proves the mapping; otherwise a bounded sequential
decode pass may establish it without retaining all decoded frames. No full clip pixel
cache. Enforce Setup deadline/aggregate index memory. Missing duration may be derived
from the next presentation timestamp; the final interval needs explicit reliable stream/
frame endpoint evidence. Reject unresolved final endpoint, overlaps, gaps without defined
frame coverage or nonmonotonic presentation order after reorder resolution. Do not use
nominal FPS/audio/container duration as proof. This is input preparation, not runtime
output-file validation. Advance/loop/resume uses prepared seek anchors off the GL thread,
with V10's explicit hold only for temporary frame lateness, never a decoder failure.

Windows source adapters use CreateFileW read access with FILE_SHARE_READ only, retaining
file identity and exclusion for every handle before reading/hashing. Independent cursors
open a separately protected handle and verify identity while the first remains protected.
Use a Python binary read/seek adapter over that native owner for PyAV/tifffile. No copied
handle integer is a portable reference. Provider combinations unable to maintain these
semantics fail Setup. Release decoder/importer consumers before closing protected sources.

## Geometry and per-output presentation

[GeometricProfile](geometric-profile.schema.json) binds the regular grid, bottom-left
source UV/destination XY, explicit mirror orientation, BL-to-TR cell diagonal, bilinear
mask/weight grids and intended coverage polygon. Shared vertices are single array entries.
The model checks local triangle orientation/area; Setup additionally checks nonadjacent
triangle intersections (shared edges/vertices excluded), a simple boundary, exact declared
mapping/output/viewport identity and union coverage against the intended polygon within
its supplied tolerance. Use robust orientation/intersection predicates with a bounded
spatial index; exceeding preparation memory/deadline fails Setup. Deliberate overlaps
between mappings require the same nonempty overlap_group. Do not allow self-overlap
within one mapping or infer weights. Each source face's required full UV domain must be
covered by its declared mappings; masked output portions remain intentional black.
Calibration tolerances are explicit input values, not invented physical measurements.

One GL-owner thread creates all GLFW contexts/windows and shared immutable resources.
Keep context-local VAOs/FBOs per context. At each group snapshot state once, render all
surface/composed final output textures, then present in authored output order, with
the designated photodiode output last. In mixed pacing only it requests interval 1;
others request 0. In all-VSync each requests 1. Log each call separately; sequential
swap calls do not promise synchronized scanout. Shared-context resources use a producer
fence plus flush and consumer GPU-side wait; never read incomplete shared textures.
No per-group coordinator barrier, automatic pacing change or CPU glFinish is introduced.
Startup validates actual framebuffer component bits and per-context swap configuration.
The Windows provider resolves `device_identity` against the monitor interface path
returned by `EnumDisplayDevicesW(EDD_GET_DEVICE_INTERFACE_NAME)`, mapped to GLFW
through its native adapter/monitor names. Friendly labels are not physical identities.
GLFW mode selection uses the nearest integer nominal refresh and checks the active
mode against that request. The configured rational refresh remains the review input
timebase; neither the integer mode observation nor a swap return measures optical
refresh. RGB10 requests use the matching RGB10A2 framebuffer hint and still require
observed ten-bit RGB channels before Idle or Ready.

## Capture and required-evidence paths

Recording stays inside the rendering worker (V12): the GL thread, one recording thread
and one FFmpeg child. There is no interprocess pixel/evidence pipe, shared pixel
pool, bridge thread or second process. Save Off allocates none of this.

Reserve one capture slot and the group's evidence-line space before compositing. If
no capture slot is free, record V12 `capacity_drop` for that group and skip
compositing/readback. After a group's swap calls are issued, the GL owner samples each
final output texture into its [tile](recorded-outputs.md#tiled-composite) of one
composite target (shared-context fence rules above apply); presented images are
unchanged. Composite codes are opaque device codes. Pixel layout is row-major,
bottom-up, width*4 stride, either RGBA8 (R,G,B,A bytes) or R10G10B10A2 little-endian
(R low 10, G next 10, B next 10, A high 2). Alpha is ignored for review; integer code
values and conversion are explicit. The recording thread handles orientation/channel/
depth conversion in the validated encoding path; do not infer representation from
allocation width alone.

Use glReadPixels into the slot's preallocated PBO from the composite target with an
associated GL fence; poll glClientWaitSync with timeout zero on later iterations. Map
only when signaled, hand the mapped slot to the recording thread and return it to the
GL owner's free list after its stdin write completes. Only the GL thread makes GL calls;
GL_WAIT_FAILED is failure. A signaled fence avoids an explicit completion wait; it is
not a guarantee of zero driver overhead. At cutoff, no new captures; drain admitted
eligible captures under existing deadlines. Keep context/GPU release on the owner
thread; unknown slot release remains a cleanup blocker under E06/E08.

RenderGroup carries one state plus known output/capture observations; GroupUpdate
carries late outcomes under [evidence-format.md](evidence-format.md). Reserve bounded
space before output work, seal after the synchronous group pass and batch currently
available facts. The GL thread hands immutable group data to the recording thread,
which serializes and appends the lines; the GL thread never builds JSON/Pydantic
models or waits for readback, encoding or sync. Every open group, pending line and
late-outcome reservation counts against `evidence_pending_bytes`. Evidence lines are
serviced ahead of blocking FFmpeg writes. At cutoff the renderer seals admission, then
the recording thread drains admitted captures and pending lines, writes Completion,
syncs and closes within existing deadlines before exact closure reports.

## Feedback/reset boundary

Tracking's bounded ordered result queue remains A06-owned. Its same-host named-pipe
messages use the same native bounded-message/generation/peer checks with FeedbackResult payloads; the
registered session preparation binds the endpoint, stream catalogue and queue capacity. FeedbackResult identifies
tracking process/stream/reset generation, trial, result sequence, source-frame lineage,
host receipt, interval and typed declared channel values. No channel units/frame are
inferred from its name; match the adopted Program.input_channels declaration. Movement
requires positive valid source interval; absolute/baseline/invalid dispositions remain
distinct. Capture the finite pending batch at update start. The data connection uses FeedbackCredit for the single A06 pending-capacity budget
across sender, in-flight pipe and receiver; capture into the finite render batch returns
a credit once for the exact FeedbackEntry.entry_sequence. That batch is separately bounded by the same maximum result count.
Old-generation credit cannot replenish a new generation. Generation fences discard
in-flight old entries without counting them as applied. No unbounded second result
queue is introduced; capacity/overflow/reset accounting stays with A06.

Tracking alone initiates A06 producer resets. V26 rejects stale results locally,
without a control RPC or acknowledgement handshake. The
[reset-generation and credit binding](../tracking/feedback-delivery.md) owns numbered
result generations and exact entry acknowledgments. A result with a newer
reset_generation is the reset, whether or not Visual Stimulus saw every intermediate generation; Visual Stimulus
still checks the current trial/source first. The [tracking catalogue](../tracking/pipeline-catalogue.md) binds the
initial estimators; native implementation remains future work.

<a id="output-reservation-and-replay-artifacts"></a>
## Output reservation and analysis replay inputs

Use existing E04 OutputPlans/reservations and the controller's authoritative prefix,
never writer-open time. Under protocol-data, use:

| Suffix | Contents | Written |
| --- | --- | --- |
| `_stimulus_LOG.json` | Complete immutable PreparedTrial: authored snapshot, resolved settings/order/durations/seed, lineage, display and resource/replay manifest. Written once at/after T atomically (temp, fsync, rename); after a crash it is either complete or absent | Every started trial, including Save Visual Stimulus data Off |
| `_stimulus_frames.jsonl` | Detailed state/presentation evidence lines (V28) | Save Visual Stimulus data On |
| `_stimulus.mp4` | One tiled review video | Save Visual Stimulus data On |

No separate recipe file or duplicate full plan in central logs. Retain tile→output
identity in PreparedTrial.ReviewEncoding when saving. No trial UUID/number appended to
filenames; internal Visual Stimulus service/schema names are unchanged. SESSION_CONFIG/trial LOG
retain the prepared identity, compact planned summary and verified log reference.

The Visual Stimulus coordinator owns the stimulus log in both save modes, using bounded background
file work inside its existing process, never the renderer/control loop or an extra
process. Prepare immutable serialized bytes and their
sha256/size at Setup within max_prepared_plan_bytes; create/write/sync the reserved
file only at/after T for a released trial. Its digest is PreparedHandle.plan_sha256.
Report closure through existing E06 output accounting. A write/sync failure is required
logging failure even with Save Off. No trial file is created during Setup, and no
serialization, rereading or post hoc validation is added to the trial transition.

When saving, the evidence Header.recipe references this same `_stimulus_LOG.json`; keep
dependent evidence in its bounded pending buffer until log publication succeeds,
without blocking rendering. The existing finalization deadline and buffer limits apply;
exhaustion/failure interrupts, never an unbounded queue or a timing extension. Publication
must precede writing the dependent Header; a reference never proves successful closure.
Save Off still closes the required stimulus log, but has no detailed evidence/video
outputs and no guarantee of actual-output replay.

The stimulus log and, when enabled, evidence file and video have separate exact
OutputPlan/closure obligations. Unexpected existing paths fail; no runtime overwrite
prompt or post hoc file validator is introduced. Encoder input format/throughput
retain the explicit rig deferral.

References for the selected mechanisms: [imagecodecs](https://github.com/cgohlke/imagecodecs), and the existing linked PyAV,
OpenGL and Windows source contracts. Library availability is not throughput evidence.
