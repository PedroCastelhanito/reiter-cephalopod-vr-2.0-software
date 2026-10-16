# Visual Stimulus recorded output images

Governing rules: [E13](../../docs/architecture/visual_stimulus.md#e13) and
[V12](../../docs/architecture/visual_stimulus.md#v12). Recording namespace and administrative
metadata ownership follow E04; trial intervals follow E11. This declares capture,
recording-thread and overload contracts, not a working implementation. E13 uses custom lossy
FFmpeg arguments through the [shared-mechanism binding](encoding-options.md).

## Capture source

With Save Visual Stimulus data On, plan one tiled review video per trial. An output is a
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
Save Visual Stimulus data switch; no independent switch per projector is introduced. Operator
preview/recording layout must not alter the stimulus. Record the composite with
operator-tuned lossy compression through one complete custom FFmpeg token list under
[encoding options](encoding-options.md), including explicit codec/quality/pixel
conversion within the required constraints. Keep fragmented MP4 at closure under
that binding. The video stores retained composites sequentially; frame n maps
to the n-th completely submitted source composite, with exact source timestamps
([review timing](encoding-options.md#review-timing)). The video serves
posthoc visualization, not exact pixel recovery. [V13 replay](replay.md) uses retained
program/assets and actual frame state for high-fidelity reconstruction and lossless
offline export; it does not decode the lossy review video to recover original pixels.

## Tiled composite

Tiles follow DisplayProfile output order, left to right then top to bottom, in a grid
of `ceil(sqrt(n))` columns for n outputs. A tile is its output's configured
dimensions times one session-fixed scale `1/k`. First find the smallest positive
integer divisor fitting the encoder maximum, then multiply by file-owned
`recording_runtime.review_scale_factor` (absent means 1 for older configuration).
Setup rejects empty tiles or encoder-incompatible final dimensions; tile dimensions
round down to whole pixels. The shipped factor 2 halves each tile dimension before
readback, leaving presented images and reconstruction inputs unchanged. Column width and
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

The rendering worker always runs one evidence recording thread. With video saving On it also runs one FFmpeg/NVENC
child per trial (an owned child under E08; argument/launch/cleanup helpers are shared
with acquisition). There is no separate recording process, shared-memory pixel
transport or evidence bridge. The coordinator prepares the renderer and aggregates
lifecycle evidence; it never relays pixels or performs scientific file writes.

The GL thread tiles each render group's final output images into one composite and
orients its completed pixels on the GPU and reads them back through reusable PBOs
within the bounded in-process `capture_slots`. Before pixel
admission, no nominal-rate selection is applied. Every render group is eligible,
including repeated pixels or equal evaluation timestamps. The recording thread takes
completed readbacks in source-group order, writes each retained composite once and
writes the [evidence file](evidence-format.md). The GL thread never waits on recording.
Launch FFmpeg at ScheduleTrial acceptance, off the render thread, with the final
paths; feed no frames before T. Launch failure before T is a required failure before
release. Cancellation before T terminates it and deletes only the file it created.

Prepare the recording thread and reservations before required readiness under
E04/E05/E08; create/write trial outputs only under E11. With video off the same
thread persists scientific evidence, without capture, encoding or capture-slot allocation.

Make one admission decision per render group. If no capture slot is free, record a
`capacity_drop` and drop that group's video sample before
compositing/readback and continue rendering. Never evict an admitted sample, slow
presentation, spill to an unbounded queue or replay an omitted source.
`recording_bytes_total` conservatively bounds capture slots, encoder-input buffering
and transient PBO readback ownership copies. No previous image is retained for padding.
The existing CPU ceiling retains conservative scratch/headroom; new top-down buffers
need no CPU row-swap scratch. GPU accounting includes the composite and same-format
flip target plus the admission-bounded PBO pool. Temporary exhaustion alone is
not encoder failure. A blocked FFmpeg write must not stop the
recording thread servicing required evidence lines, nor the worker's control/health path.

Recording diagnostics retain fixed stage aggregates, at most one worst-duration
example per stage, and one unfinished frame-input span. Examples carry exact source
group/video-index identity where applicable and host start/end times. `pipe_write`
measures individual calls; `frame_input` spans all attempts for one complete raw frame,
including time between zero-progress calls, with attempt/zero-progress counts. Capture
readiness, ready-to-dequeue queue wait and reservation-to-release lifetime retain their
own examples. Snapshots copy these bounded records; no per-frame diagnostic history,
percentile estimate or new deadline/control input is introduced. These times prove
neither encoding/persistence nor physical presentation.

Evidence lines are bounded by `evidence_pending_bytes`, separately from capture slots,
so a full video path cannot silently drop metadata. If required evidence cannot be
retained, report a required-logging failure under E06 without waiting indefinitely or
allocating a rescue buffer. Evidence distinguishes not admitted, admitted/pending and
FFmpeg-input outcomes, retaining render-group IDs and original timing. Do not infer
encoding success from a stdin write, encoder liveness or successful presentation.
Unconfirmed outcomes after a crash stay unknown; surviving samples are never renumbered.
V10 render/epoch misses and media source frame skips are not recording-capacity drops.

At trial cutoff, stop admitting out-of-interval samples, reconcile the exact producer
watermark and drain admitted work under E11 without leading, interior or trailing
padding. Assign consecutive zero-based video indices as complete input frames are
submitted; capture failures/cancellations/drops consume no index. Pending readbacks
cannot allow later groups to overtake earlier ones. No usable image keeps
the existing empty/absent outcome. Apply the [review-video completion predicate](video-completion.md),
including confirmed empty/absent results with warnings and complete required records.
Report closure/evidence before aggregate Finished. E05's external post hoc file-validation boundary applies: no file
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
Do not fabricate source groups for V10 missed epochs or interpret recording gaps as proof
of missing physical presentation. Conversely, render submission does not prove the
frame reached the recording file.

Final renderer images precede any external desktop-compositor, driver, display-link
or projector processing not performed by CephVR. They cannot measure light onset,
brightness or physical alignment. Rig/pulse evidence remains separate.

When Save Visual Stimulus data is Off, skip only the capture/encoding path; retain
required scientific evidence and recipe outputs under E13.

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
drain/closure and Save Visual Stimulus data Off. No behavioral/rig verification is implemented here.
