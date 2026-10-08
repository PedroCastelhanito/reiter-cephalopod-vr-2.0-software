# Visual Stimulus custom lossy FFmpeg output arguments

Governing rules: [E13](../../docs/architecture/visual_stimulus.md#e13), [V12](recorded-outputs.md)
and [V28](../../docs/architecture/visual_stimulus.md#v28). Reuse the existing FFmpeg argument-list mechanism and
compatible implementation helpers. This declares Visual Stimulus's constraints; no encoder
runtime, capability probe or rig-throughput result is delivered.

## One complete list for the composite

The E13 tiled review composite has one complete `ffmpeg_args` token list at
`recording.ffmpeg_args` in the adopted Visual Stimulus recording settings (one encoder, one NVENC
session). The owning default-file section is in visual_stimulus_config.toml; explicit saved/operator
values follow E07 precedence, and the effective list locks at Start. No per-output or
per-surface encoder list, list merging, named encoder profile or separate codec/quality
knobs. A missing list fails Setup when saving is enabled. Save Off creates no encoder
obligation; a retained list remains reusable.

Use the [existing option inventory/parser](../acquisition/encoding-options.md#parsing-and-ownership)
for aliases, scalar duplicates, token/value parsing, supported encoder options,
capability checking and backend-owned option rejection. Keep one implementation of
those mechanisms rather than copying an option parser into Visual Stimulus. Installed FFmpeg
support does not make an unknown option valid. The current supported codec inventory
is the existing NVENC set, subject to device/build/MP4 compatibility; this choice
does not implicitly add libx264 or a CPU fallback. Adding a supported encoder later
requires explicit registry/validation support, not merely putting its name in a list.
Codec and quality are explicit; physical GPU placement follows
[SYS-002](../../architecture.md#sys-002). Reuse acquisition's backend-owned `-gpu`
resolution for the RTX 2080 Ti. Composite rendering/PBO readback stays on the RTX
5060 Ti; feed the resulting host buffer through the existing raw-stdin path to
the encoder. Do not assume cross-adapter GPU buffer sharing or ordinal equality.

Execute an argv list without a shell. Report validation errors with token position
and canonical option. Validate during Setup using advertised
capabilities and prepared input/output descriptions; no trial-output file, test
encode or completed-file scan is created by that validation. Encoder initialization
can still fail at runtime; there is no automatic switch to another encoder or format.
Resolve tools through the existing PATH discovery/compatibility helper and retain
selected build/effective arguments in existing Visual Stimulus setup provenance.
Shared device checks include the final composite dimensions: camera-size probe
success does not validate the composite. Reject an incompatible layout/codec pair;
any revised tile layout or codec must be explicitly prepared under E13, never an
automatic resize or adapter fallback.

## Visual Stimulus constraints on the shared validator

| Area | Visual Stimulus-specific rule |
| --- | --- |
| Fidelity | Require an explicitly lossy mode compatible with E13's high-quality review intent. Reject lossless tuning/mode combinations; codec-specific quality validation must not confuse a value meaning automatic quality with lossless. An occasionally exactly reproduced frame is not evidence that settings were lossless. |
| Input | The [tiled composite](recorded-outputs.md#tiled-composite) of final renderer-produced output images, including correction and patch, at the prepared composite dimensions and code representation. Retain both the native capture layout and the FFmpeg raw-input pixel format derived from that explicit ABI in `ReviewEncoding`; Setup verifies that the installed build advertises it. `rgba8_bottom_up` maps to `rgba`; packed little-endian RGB10 with R/G/B in the low 30 bits and two zero X bits maps to `x2bgr10le`. Recording flips bottom-up rows before rawvideo input. The FFmpeg format definition is documented in the [upstream pixel-format patch](https://ffmpeg.org/pipermail/ffmpeg-devel/2021-September/285611.html). Actual input fidelity and throughput remain rig checks. No camera-native/Bayer preparation or inherited acquisition alignment. |
| Filters | Permit the shared validated format/conversion chain, with scale restricted to unchanged dimensions. Reject crop/pad/flip, resizing, overlays and temporal filters: these would break the recorded tile layout. Shared filter grammar/alias validation still applies. |
| Pixel format | Require explicit terminal format and matching +pix_fmt, with explicit channel/range/matrix conversion. Explicit depth reduction is permitted for this lossy review copy, including RGB10 to 8-bit storage. Validate the requested conversion and encoder support during Setup; retain source/target depth, pixel format, chroma, range/matrix and effective arguments. Reject silent negotiation, undeclared intermediate reduction and reduction followed by widening presented as preserved precision. Chroma conversion remains explicit. |
| Color tags | Must describe the actual supplied code/conversion interpretation. Measured projector device codes are not automatically standard sRGB/BT.709 light values. Retain custom interpretation in replay provenance; do not invent standard transfer/primaries tags just to make a player accept a file. |
| Timing | Constant rate under [review timing](#review-timing); Visual Stimulus sets the input rate. Reject user tokens that change the frame rate, duplicate/drop frames or retime samples. Encoder input format/throughput retains its accepted rig deferral, without inheriting acquisition rules. |
| Metadata | Reuse duplicate-key/reserved-identity protection. Visual Stimulus owns session/trial identity and the tile layout; camera-role tags and camera frame-log correspondence are not Visual Stimulus identities. User title/comment/description remain separate. |
| Container/paths | One `_stimulus.mp4` per trial, reserved through E04. Visual Stimulus builds its raw stdin input, rate, path, overwrite protection, muxer flags and diagnostic pipes; user tokens cannot add another file or override them. Use fragmented MP4, retained after closure; never select hybrid conversion or ordinary MP4 implicitly. The fragment lifecycle below applies. |

Lossy review settings cannot weaken mandatory lossless render-state/presentation
records or change their save switch. Readback/encoding capacity loss retains V12's
drop-incoming policy with complete evidence; it does not authorize loss of metadata,
retiming the experiment, lower-resolution stimulus rendering or a new frame-rate cap.
Review conversion runs only after the stable composite image has been captured;
it never changes the live renderer, calibration/photodiode values or lossless replay
inputs. Validate the actual initialized conversion/encoder representation against the
prepared description and retain available runtime evidence; unknown or mismatched
negotiation is not permission to downgrade. Reuse the common validator with Visual Stimulus's
explicit review-depth allowance; acquisition separately requires an explicit per-camera
recording_bit_depth before reducing a deeper source under A08.
The [Visual Stimulus completion predicate](video-completion.md) binds confirmed empty/absent video
results; it does not waive encoder errors or required state/presentation records.

## Review timing

The review video is constant-rate at the pacing output's nominal refresh rate (the
photodiode output in `photodiode_only_vsync` mode), retained as PreparedTrial
ReviewEncoding.timing. Video frame n (zero-based) is the n-th admitted render group;
its evidence Capture carries `video_frame_index` n. Real timing (state-evaluation
host time, per-output swap observations) lives only in the
[evidence file](evidence-format.md). Each omission shortens playback by one frame
period; no duplicated, padded or replacement frames and no per-frame timestamps are
passed to FFmpeg. Review timing never establishes optical onset or display duration.

## Fragmented MP4 lifecycle

Keep the review video in one fragmented MP4 file through normal closure. The owning
argument builder selects the muxer/fragment controls; user output tokens cannot
override them. Use keyframe-aligned fragmentation with a finite prepared GOP bound
from the validated encoder settings. Include packet/fragment buffering in resource
validation; fragmented output is not a guarantee of fixed total process memory or
independently decodable fragments. Codec reordering and actual keyframe behavior
remain part of the selected encoder's compatibility/rig checks.

FFmpeg's `frag_keyframe` mechanism is the intended fragment boundary control. The
complete backend-owned command must still bind initialization metadata and CTS/DTS
handling with the raw constant-rate input; do not publish an untested flag
combination as a complete ready encoder plan. Require advertised support during
Setup and record the actual effective command at launch. Unsupported required mode
fails explicitly rather than falling back to ordinary/hybrid MP4.

Do not enable `hybrid_fragmented`, `faststart`, a whole-file index relocation pass,
or an automatic remux after the trial. End-of-trial work still drains admitted input,
flushes encoder/muxer buffers, writes required final metadata, checks exit, syncs and
closes under the shared deadlines. Fragment flush is not OS durable sync, Closed,
successful sample persistence or complete cleanup. No review-file content validation
runs here. Some players/tools have narrower fragmented-MP4 support; compatibility
is a rig/post hoc check, not grounds for a silent runtime conversion.

An interrupted file may contain readable fragments, but V28 still leaves unknown
closure Unconfirmed and supplies no review-video repair/remux path. The
[empty-output predicate](video-completion.md) still requires truthful artifact
presence, accounting and successful cleanup; fragmentation does not waive empty-input
errors or promise a playable empty file.

Reference: [FFmpeg fragmentation and muxer options](https://ffmpeg.org/ffmpeg-formats.html#Fragmentation).

## Ownership, failure and finalization

Use one FFmpeg child (one NVENC session) per trial for the composite, owned by the
rendering worker and fed by its V12 recording thread. Reuse E08's Windows registration,
containment and compatible pipe/sync/cleanup helpers. Launch it at ScheduleTrial
acceptance, off the render thread, with the final paths; no frames before T.
Cancellation before T terminates it and deletes only the file it created. A blocked
stdin write cannot block required evidence lines or control/health. Compositing and
PBO readback into bounded `capture_slots` belong to the GL thread; codec/disk work
never runs on it.

Use the existing progress-monitoring and bounded diagnostic-drain mechanisms with
Visual Stimulus-owned resource accounting. Create trial outputs only within E11, finalize
admitted data, verify online finalization/exit, synchronize and close before confirmed
completion. Do not reread MP4 indexes, decode outputs or reconcile file contents in
normal runtime. That work is external post hoc under E05. Known encode/write/sync
failure follows E06 even when frame-capacity drops are permitted.

V28 remains authoritative after a crash: unknown review-video closure stays
Unconfirmed; no dedicated repair/remux is introduced by using the same FFmpeg
mechanism. Acquisition's camera frame-log/crash behavior is not imported. Lossless
offline reconstruction uses program/assets/actual state independently of these lossy
files. Encoder input format and throughput remain deferred to the rig.

Mechanism reference: [FFmpeg options](https://ffmpeg.org/ffmpeg.html).
