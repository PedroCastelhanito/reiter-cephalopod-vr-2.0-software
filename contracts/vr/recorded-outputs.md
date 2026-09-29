# VR recorded output images

Governing rules: [E13](../../docs/architecture/vr.md#e13) and
[V12](../../docs/architecture/vr.md#v12). Recording namespace and administrative
metadata ownership follow E04; trial intervals follow E11. This declares capture,
recording-thread and overload contracts, not a working implementation. E13 uses custom lossy
FFmpeg arguments through the [shared-mechanism binding](encoding-options.md).

## Capture source

With Save VR data On, plan one tiled review video per trial. An output is a
projector/display presentation target, not an operator preview window. Each tile is
that output's final renderer-produced image after any renderer-applied warp, mask,
blend or color correction. This rule does not itself select which corrections or
projection geometry the backend supports.

Reuse the images already produced for the outputs; do not render a second observer
view. After a group's final output images exist, the renderer samples them into one
composite target under the tile layout below, then captures a stable copy of that
composite before its storage is overwritten, retaining render-group identity through
transfers and encoding; the recipe's layout maps each tile back to its output. Buffer lifetime and
transfer mechanisms follow [runtime bindings](runtime-bindings.md) and the ownership rules below;
the source choice does not promise zero-copy transfer or cost-free recording.

Reserve output files under the existing E04 mechanism. Keep the existing single
Save VR data switch; no independent switch per projector is introduced. Operator
preview/recording layout must not alter the stimulus. Record the composite with
high-quality lossy compression through one complete custom FFmpeg token list under
[encoding options](encoding-options.md), including explicit codec/quality/pixel
conversion within the required constraints. Keep fragmented MP4 at closure under
that binding. The video is constant-rate; frame n is the n-th admitted render group
([review timing](encoding-options.md#review-timing)). The video serves
posthoc visualization, not exact pixel recovery. [V13 replay](replay.md) uses retained
program/assets and actual frame state for high-fidelity reconstruction and lossless
offline export; it does not decode the lossy review video to recover original pixels.

## Tiled composite

Tiles follow DisplayProfile output order, left to right then top to bottom, in a grid
of `ceil(sqrt(n))` columns for n outputs. A tile is its output's configured
dimensions times one session-fixed scale `1/k`, with k the smallest positive integer
for which the composite fits the encoder's advertised maximum resolution (Setup
fails if none does); tile dimensions round down to whole pixels. Column width and
row height are the largest tile in that column/row; a tile sits at its cell's
top-left, and unused area plus any encoder-alignment padding is fixed black code 0.
Sampling uses the policy's fixed resampling filter; k = 1 copies codes unchanged.
The composite depth is the largest output code depth; a lower-depth tile is widened
by `round(c·(2^d−1)/(2^s−1))`. This is review-only conversion: rendering, presented
images and V13 inputs are unchanged.

The prepared ReviewEncoding retains the layout: composite dimensions, k, and each
output ID with its tile rectangle and source depth. Evidence references it through
the recipe; review pixels are never the per-output record.

## Recording thread and bounded admission

With saving On, the rendering worker runs one recording thread and one FFmpeg/NVENC
child per trial (an owned child under E08; argument/launch/cleanup helpers are shared
with acquisition). There is no separate recording process, shared-memory pixel
transport or evidence bridge. The coordinator prepares the renderer and aggregates
lifecycle evidence; it never relays pixels or performs scientific file writes.

The GL thread tiles each render group's final output images into one composite and
reads it back by PBO into one of the bounded in-process `capture_slots`. The recording
thread takes completed readbacks, writes raw composite frames to FFmpeg's stdin and
writes the [evidence file](evidence-format.md). The GL thread never waits on recording.
Launch FFmpeg at ScheduleTrial acceptance, off the render thread, with the final
paths; feed no frames before T. Launch failure before T is a required failure before
release. Cancellation before T terminates it and deletes only the file it created.

Prepare the recording thread and reservations before required readiness under
E04/E05/E08; create/write trial outputs only under E11. When saving is Off no
recording thread, capture or encoding runs and no capture slots are allocated.

Make one admission decision per render group. If no capture slot is free, drop that
group's video sample before compositing/readback, record its identity, timing and
`capacity_drop` disposition in the evidence and continue rendering. Never evict an
admitted sample, slow presentation, spill to an unbounded queue or replay the omitted
sample. `recording_bytes_total` bounds slots plus encoder-input buffering. Temporary
exhaustion alone is not encoder failure. A blocked FFmpeg write must not stop the
recording thread servicing required evidence lines, nor the worker's control/health path.

Evidence lines are bounded by `evidence_pending_bytes`, separately from capture slots,
so a full video path cannot silently drop metadata. If required evidence cannot be
retained, report a required-logging failure under E06 without waiting indefinitely or
allocating a rescue buffer. Evidence distinguishes not admitted, admitted/pending and
FFmpeg-input outcomes, retaining render-group IDs and original timing. Do not infer
encoding success from a stdin write, encoder liveness or successful presentation.
Unconfirmed outcomes after a crash stay unknown; surviving samples are never renumbered.
V10 render/epoch misses and media source frame skips are not recording-capacity drops.

At trial cutoff, stop admitting out-of-interval samples and drain admitted work under
E11. Apply the [review-video completion predicate](video-completion.md), including
confirmed empty/absent results with warnings and complete required records. Report
closure/evidence before aggregate Finished; finalization never adds a replacement for
a dropped sample. E05's external post hoc file-validation boundary applies: no file
reread/decode validator runs in the runtime. Confirmed encoder, storage or required
logging failures retain E06 handling. E08 health/progress checks must not mistake a
live heartbeat for encoder/file progress. Recording-loss counts belong in compact
status summaries; detailed histories remain under E13, with no per-frame RPC.

The recording thread shares the renderer's process and GIL; full-workload throughput
remains an E15 rig check.

## Evidence and limits

Retain [V13 replay state and provenance](replay.md) even when review-video samples
are dropped. Associate recorded frames with render/state identity and tile layout, epoch occurrence,
video source-frame lineage where applicable, and software timing observations.
Separate rendered, submitted, captured and encoded outcomes. An encoded image does
not establish that the output swap succeeded or that the projector emitted it.
Do not fabricate frames for V10 missed epochs or interpret recording gaps as proof
of missing physical presentation. Conversely, render submission does not prove the
frame reached the recording file.

Final renderer images precede any external desktop-compositor, driver, display-link
or projector processing not performed by CephVR. They cannot measure light onset,
brightness or physical alignment. Rig/pulse evidence remains separate.

When Save VR data is Off, skip the recording-only capture/encoding path and detailed
outputs under E13; preserve rendering and the agreed administrative summaries.

## Remaining work and verification

[Runtime bindings](runtime-bindings.md) and [evidence format](evidence-format.md) declare
capture slots, file names and typed lines; encoder input format/throughput retain the
accepted rig deferral. The [completion predicate and result fields](video-completion.md)
are bound; implement their aggregation and cleanup under these rules. V28 owns
append-only evidence durability and crash behavior. Acquisition-specific policies are
not imported automatically. Resource demand depends on the configured number,
dimensions and rates of outputs, the composite scale and encoding settings; compare
full-rig workloads before making performance claims. Future runtime checks must cover
per-group admission, tile mapping, drop-incoming without render waits, complete
metadata during capture overflow, metadata failure interruption, encoder failure,
drain/closure and Save VR data Off. No behavioral/rig verification is implemented here.
