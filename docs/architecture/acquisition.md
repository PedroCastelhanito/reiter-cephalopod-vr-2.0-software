# Acquisition backend

[Overview and decision register](../../architecture.md) · [System contracts](system-contracts.md)

Rules for the acquisition coordinator and its camera, recording and helper processes.
[End-to-end delay](system-contracts.md#a05) and
[tracking-result delivery](tracking.md#a06) have their own authoritative records.

Related: [trial timing](experiment.md#e05), [failure handling](system-contracts.md#e06),
[process ownership](system-contracts.md#e08), and
[acquisition contracts](../../contracts/acquisition/README.md).

Configuration: [acquisition_config.toml](../../config/backends/acquisition_config.toml).

## Implementation scope

The [acquisition contract index and worklist](../../contracts/acquisition/README.md)
is the single worklist for declared contracts, hardware inputs and explicit rig
deferrals. Host code acceptance and static results belong in the
[implementation review](../../reports/acquisition.md).
Manual preview is Configuration-only; session preview is rate-capped (A03).
Hardware inputs and explicitly deferred rig checks remain pending; accepted design
is not runtime or rig validation (E15).

## Decisions

<a id="a01"></a>
### A01 — Camera acquisition and recording ownership

**Status:** Accepted · **Revision:** 16

- The acquisition backend owns camera capture, video encoding and camera video files,
  including trial-bound recording and verified file closure under E05/E11. The
  experiment controller keeps session/trial timing authority; camera output closure
  and failures follow the shared lifecycle and supervisor rules.
- Capture and recording run as separate threads in one camera worker process per
  camera; FFmpeg encodes in its own subprocess. A02 defines the process layout, A03
  frame transfer.
- Camera SDK access sits in a small adapter module inside the camera worker, starting
  with Basler: device opening/closing, settings, capture, native metadata extraction
  and PFS operations. It returns results/errors through this boundary; no extra
  process or general plugin framework. Future SDKs implement the same interface.
  Common worker code owns trial timing, frame delivery/buffers and health/error
  reporting.
- Initial format support covers a broad range of monochrome, color, Bayer and packed
  high-bit-depth images, not only current rig formats. Supported formats need
  explicit native layouts, consumer mappings and validated source precision; SDK
  exposure or enumeration alone proves nothing. Setup rejects unmapped formats or
  incompatible active consumers with the format/path and reason. Detailed mappings
  remain implementation work, not a claim of completed support.
- SDK-native pixels stay in A03's shared buffers. After copying/releasing their input,
  recording, preview and tracking use one common Python module for native-layout
  interpretation, conversion and reusable pixel-processing methods. Each consumer owns
  its working images/converter state; no shared mutable results or central conversion
  stage. Consumer representations and explicit recording conversion follow A08, A10
  and tracking T01.
- Image-only SDK conversion may run in that module; camera opening/control stays
  exclusively in the capture adapter. Use the Basler SDK converter through it for
  supported native recording and preview conversions and reuse that binding for
  identical tracking preparation. No second unpacking/demosaicing provider or silent
  fallback. The pinned Python binding's SDK-owned conversion result is checked,
  copied into consumer-owned preallocated storage and released under the
  [SDK mapping](../../contracts/acquisition/sdk-mappings.md); A03's SDK-internal
  allocation exception remains unchanged.
- Prepared original-depth images use MSB alignment in wider containers, retaining
  declared source depth; unchanged native pixels keep their own alignment. Preview
  scales the interpreted source range. Skip conversion only when the complete
  representation already matches. Preparation resolves mappings; no inference from
  image values. See the
  [pixel-processing contract](../../contracts/acquisition/pixel-processing.md).
- Bind each enabled camera role to an explicitly configured stable device ID (e.g.
  serial number). Setup verifies that exact device; an unavailable device or missing
  assignment blocks Ready with an actionable error. Never substitute by discovery
  order. With both roles enabled, require distinct physical devices and reject
  duplicate assignments before capture; initially no camera stream is shared across
  behavioral/tracking roles.
- Assignments are configurable under E07 before the session and locked during it;
  changing a prepared assignment invalidates Ready and requires fresh Setup. Supplied
  owner assignments live in the acquisition configuration; discovery/readback alone
  never selects roles, image settings or rates.

**Contracts:** [camera settings](../../contracts/acquisition/camera-settings.md),
[frame buffers](../../contracts/acquisition/frame-buffers.md) and
[frame-log schema](../../contracts/acquisition/frame_log_schema.toml) are declared.
Remaining format mappings and integration are classified in the contract worklist.

<a id="a02"></a>
### A02 — Acquisition service and camera workers

**Status:** Accepted · **Revision:** 30

- One acquisition coordinator serves both camera roles through one external control
  endpoint; it aggregates readiness/closure and never relays pixels.
- The initial runtime targets Windows. Isolate OS-specific memory, process
  containment and storage integration; other OS support is future work.
- Each enabled camera has one Python camera worker: a capture thread and, when saving
  video, a recording thread feeding its FFmpeg subprocess; tracking runs in another
  process. A native SDK crash thus also ends that camera's recording; E06 treats a
  camera's capture and recording as one data path.
- Session-disabled roles open no devices except for explicitly requested
  Configuration preview (A10). Session worker failures enter E06 incident
  classification; isolate failed data functions where safe, otherwise interrupt.
- Acquisition owns worker launches; camera workers own per-trial FFmpeg launches. Use
  E08's shared registration helper, supervisor oversight and Windows Job Objects for
  every descendant; ownership stays with the backend, not a launcher service.
- Launch each Python worker as a fresh interpreter (`python -m` entry point) through
  E08's native contained launcher; no multiprocessing bootstrap, private Popen adapter
  or inherited Python objects. Rings and wake events use A03's named resources.
  Register the worker endpoint before importing/initializing SDKs.
- Each Python worker has a private OS-assigned loopback gRPC endpoint, registered with
  its owner and supervisor before work. Both reach it independently under shared
  authority/context/idempotency checks. The
  [worker-control binding](../../contracts/acquisition/worker-control.md) maps its
  registered process role to the exact camera; never infer a replacement's endpoint.
- Camera worker endpoints expose a small dedicated worker service for preparation,
  scheduling/release, stop/interruption and cleanup/shutdown, reusing shared
  identities, command admission and lifecycle semantics. Only the coordinator exposes
  the public BackendService; supervisor interruption remains direct.
- Prepare enabled cameras concurrently in their own workers, preserving each camera
  path's dependencies and A03's readback-before-allocation order. Overall Ready
  requires every required participant. Concurrency adds no timeout/retry allowance;
  shared devices keep one serialized owner; E06 governs failure/cancellation cleanup.
- The coordinator pushes each worker's complete resolved Setup settings and required
  resource descriptors, tied to the controller-approved configuration revision,
  together with that worker's exact E06 function declarations from the session plan.
  The coordinator is the logical function owner; the registered camera worker is its
  authorized reporter. Capture/recording dependency closures include all affected
  reserved session output keys, including future trials. Workers validate and retain
  these declarations before Ready; no inferred output keys, configuration-reference
  fetch, independent TOML reload or settings from unrelated worker roles.
- Per-trial preparation sends only that worker's new trial plan and the required
  confirmed configuration revision. Session settings are reused, but device/resource
  readiness and prior closure are rechecked before fresh Ready. Missing or mismatched
  retained setup fails preparation under existing failure rules; never silently
  fetch, substitute settings or reuse an earlier trial's Ready.
- Camera workers own their ordered grab loop: wait jointly for a camera result, a
  control-command signal or the nearest lifecycle/health deadline, then retrieve
  available results without blocking; recheck commands/boundaries between frames. No
  fixed 1 ms polling cap or SDK-owned callback/grab loop. One camera owner stamps
  receipt before copying; recording (own thread) and tracking (own process) never run
  in the capture thread. The
  [capture-wait binding](../../contracts/acquisition/capture-wait.md) owns wakeup,
  deadline and compatibility mechanics, including control priority after the joint
  wait; timeout alone is not frame-health failure.
  The typed Windows HANDLE bridge is a bounded SYS-003 SDK exception for the
  measured pypylon constructor limitation; it duplicates the existing event and
  adds no owner, queue or capture loop. Missing/incompatible builds fail preparation.
- Workers send heartbeats to their coordinator (aggregated into its supervisor
  heartbeat) and errors directly to the supervisor, under E08. Control/health threads
  stay separate from blocking data work; one data/lifecycle owner applies commands.
  Responsive RPCs do not prove capture/encoding progress.
- Camera workers persist through a session, idle between trials; reuse requires prior
  closure, reset trial state and fresh Ready. No automatic worker restart or session
  resumption; E06 governs cleanup. Crash output follows A07 (no recovery tool).

**Contract status:** worker RPCs and launch interfaces are declared; runtime providers
and verification remain in the
[worklist](../../contracts/acquisition/README.md#remaining-decisions-and-implementation-work).

<a id="a03"></a>
### A03 — Frame transfer between processes

**Status:** Accepted · **Revision:** 32

- Pixels reach other processes (tracking, preview viewers) through coordinator-owned
  host shared memory, never control gRPC. Inside a camera worker, capture hands frames
  to recording through an in-process bounded queue; recording uses no shared memory.
- Use Python `SharedMemory`; Windows releases mappings after the last handle closes,
  not through `unlink()`. Keep ownership records until all users release or exit.
- Allocate during Setup only after camera settings are applied/read back, actual
  layout is confirmed and the controller has adopted the resolved configuration;
  then prepare dependent consumers. Never allocate against requested-but-unconfirmed
  dimensions/formats. Reuse only after previous-trial closure and occupancy/context
  reset; release on session cleanup or failed/cancelled Setup. Each allocation gets a
  fresh unique name; descriptors bind allocation, role, layout and
  session/configuration.
- T08 Configuration diagnostics may additionally allocate an ordered TRACKING ring
  in exact manual-preview scope after confirmed camera layout, separate from the
  latest-frame GUI ring. Acquisition retains allocation and transfer ownership,
  exact registered Tracking consumer identity and release obligations. This is not
  a session/trial binding; both scopes preserve native pixels and A04 reset rules.
- The tracking ring and the in-process recording queue each default to **10 frames**
  (`[buffers] tracking_ring_frames`, `recording_queue_frames`), configurable before
  Setup. Create only what is needed; never grow at runtime. When the optional
  `recording_startup_allowance_ms` is set, the recording queue holds at least
  `ceil(frame_rate_hz × recording_startup_allowance_ms / 1000)` frames (applied MCU
  rate or free-running rate). The allowance stays unset; Setup reports memory.
  Capacity excludes SDK pools, working copies and library/OS buffers.
- Shared rings use seqlock slots: the writer increments a slot's generation before and
  after copying pixels and publishes the newest index, never locking or waiting. A
  reader copies the slot into private memory, then rechecks the generation; a changed
  or odd generation (torn or lapped read) discards the copy and counts a skipped
  frame.
- One auto-reset Win32 named event per ring wakes readers (ctypes, public kernel32
  API); every wait has a deadline and rechecks shared state. A notification means
  "inspect shared state", not one frame. Stop/reset also wake waiters.
- The capture thread never waits on a consumer. A lapped shared-ring reader skips
  (counted) and follows A04's tracking reset rule; a full recording queue drops its
  oldest waiting frame (A04). No per-frame lock, retry or copy timeout. Writer failure
  retires the ring and its event; fresh Setup requires released/exited users and new
  resources, never repair/reuse of a failed ring.
- Every consumer, spawned by acquisition or independently launched, opens the ring's
  memory and event by the unique per-allocation names in its prepared descriptor, for
  its exact registered process generation. Names alone do not authorize attachment;
  validate/confirm attachment before Ready and close partial attachments on failure.
  Controller or supervisor forwards its validated tracking Cleanup report through
  the existing protected handoff; acquisition matches the registered consumer, work
  and input resource before accepting release. Cancellation alone is not release.
- Preserve SDK-native pixel packing, row padding and bit depth. One immutable prepared
  descriptor defines dimensions, format, stride and payload size; verify every result
  before copying. Layout changes require re-preparation. Readers copy into private
  working memory before processing/encoding, own explicit conversion/repacking and
  never modify shared pixels.
- Consumers allocate/reuse CephVR-owned, known-size, process-local image working
  buffers, separate from shared rings, after layout/conversion confirmation: required
  recording/tracking copies before capture; optional viewer copies before its first
  read, without gating capture. Reuse only after all users release the image. Size for
  required concurrent images without adding a frame queue. SDK/codec internal
  allocations are outside this guarantee; required allocation failure blocks
  preparation.
- One seqlock latest-frame slot serves each camera preview: manual Configuration
  preview (A10) and, when enabled, session preview. Session preview is capped by
  `[preview] session_preview_max_hz` (default **10**, configurable; 0 disables it):
  the capture thread copies the newest valid in-trial frame at most at that rate.
  Viewer attachment never restarts capture or pulses; preview never gates recording,
  tracking, Ready or trial start and creates no recordings. Allocate after confirmed
  layout; release when the preview run or session ends, not when a viewer closes. Stop
  and release manual preview before Setup.
- The coordinator owns cleanup but is outside the frame path. Memory accounting
  includes every enabled ring, SDK pool and working copy; shared memory is not a claim
  of GPU residency, zero-copy operation or lossless acquisition.

**Contract status:** [frame-buffer contracts](../../contracts/acquisition/frame-buffers.md)
define slots, protected tracking attachment confirmation and quiescent tracking-ring
cleanup. The [Setup handoff](../../contracts/data-preparation.md) binds descriptor and
consumer evidence before Ready. Native cancellation and later implementation/rig work
remain in the contract worklist.

<a id="a04"></a>
### A04 — Frame delivery and consumer overload

**Status:** Accepted · **Revision:** 20

- Recording drops, preview skips and tracking backlog discards are independent
  consumer actions; none discards another consumer's frames. Confirmed required
  failures keep E06's incident classification and local containment.
- A full recording queue drops its oldest waiting frames to admit newer ones; the
  trial and session continue. Never remove already encoded frames or the frame being
  written. Dropped frames keep their frame-log lines with `dropped = true`; drops never
  permit metadata loss.
- Keep retained frames ordered and record gaps explicitly in acquisition output
  metadata (frame identities/timestamps, drop counts); never retime source-frame
  metadata to hide gaps. Loss alone does not mark the trial Interrupted; successful
  file closure does not imply a gap-free video.
- Account for retained and dropped recording frames under [A07](#a07) (frame-log
  schema, intended frame/video mapping, online closure). Acquisition or queue
  admission alone never proves saving.
- An SDK-reported incomplete/corrupt image has its payload discarded; record/report
  the recoverable acquisition error and continue. Never send invalid pixels to
  recording, tracking or preview; never interrupt solely for that frame-quality error
  or treat it as a required-device failure signal. With recording enabled, details go
  to acquisition-owned diagnostic/output records; received invalid images keep source
  IDs and dropped frame-log lines (A07/A09).
- Persistent loss of usable frames remains subject to A10's deadlines; confirmed
  device/process, storage and required-logging failures follow E06.
- Group repeated tolerated data-quality warnings by camera and cause within each
  trial: show the first and update its occurrence count, without separate
  operator-warning entries or per-frame session-log events. Detailed evidence stays in
  enabled acquisition outputs (A07); disabled recording keeps operational warnings
  without per-frame files. Grouping must not suppress a different cause, hide a
  confirmed required failure or delay health deadlines and session interruption.
- Preview always selects the newest available frame and skips obsolete waiting
  frames.
- Tracking consumes frames in order. Its delay is the next frame's age immediately
  before processing: current host-monotonic time minus the frame's host-monotonic
  acquisition timestamp, against a configurable limit defaulting to 250 milliseconds.
  Preserve the acquisition timestamp across transfers; never substitute queue arrival
  time, frame count or an unaligned camera-device clock. This is a pre-processing age
  threshold, not an end-to-end tracking/display latency guarantee.
- When age exceeds the limit, or on tracking-ring overflow even below that limit, discard
  the waiting tracking backlog, reset tracking state and restart from the newest
  available frame. A lapped tracking read (A03) is a skipped delivery requiring this
  reset before further processing; preserve the discontinuity until safely applied.
  Never silently skip a missing pending frame and continue with the previous state.
  This is an in-session state reset, not a process, camera or trial restart or
  resumption of an Interrupted session. Recording continues independently.
- After a received invalid image or evidenced missing-frame gap in the camera
  supplying tracking, reset tracking state before the next valid frame and establish
  a fresh baseline; never estimate movement across the gap (A06 result-generation
  reset and validity rules). Preserve the gap's position in input order so buffered
  frames cannot hide it. Only tracking input counts: recording-only drops or another
  camera's gaps do not reset tracking. Exact algorithm reset state is a
  tracking-backend decision.
- Record tracking discontinuities/resets in tracking output metadata; detailed frame
  histories belong in the owning backend outputs, not the session log.

**Other-backend work:** [A06](tracking.md#a06) owns result validity and the remaining
tracking-reset/Visual Stimulus response contracts; these do not reopen acquisition drop policies.

<a id="a07"></a>
### A07 — Recording frame log and crash behavior

**Status:** Accepted · **Revision:** 58

**Files**

- Each saved camera/trial has two files sharing its prefix: `<prefix>_<role>_cam.mp4`
  and `<prefix>_<role>_cam_frames.jsonl` (`behavioral_cam`, `tracking_cam`).
  `save_video` enables both; disabled saving creates neither, no recording
  thread/queue and no detailed camera history. Tracking outputs and operational
  warnings/health are independent. No HDF5, CSV or separate meta file.
- MP4 tags and the frame-log header embed session/trial/camera-role/device identities
  as acquisition-owned metadata that operator arguments cannot override. Filenames
  alone cannot establish a pair; the
  [pair-identity contract](../../contracts/acquisition/recording-identity.md) defines
  keys.
- The [frame-log schema](../../contracts/acquisition/frame_log_schema.toml) owns line
  types and fields. The recording thread owns both files.

**Frame log (`_frames.jsonl`)**

- UTF-8 JSON Lines, append-only from creation (at/after T) to closure: one `header`
  line, one `frame` line per received in-trial image, one `completion` line. A missing
  `completion` line means incomplete.
- `header`: identity, host and camera clock/counter descriptors (resolved once during
  preparation under the [camera-clock contract](../../contracts/acquisition/camera-clock.md)),
  trial start and the nominal video rate.
- `frame`: source ID, host receipt ns, `dropped`, `video_frame` (MP4 index, null when
  dropped), optional native counter and native timestamp (null when unavailable) and
  `invalid_code` for invalid images. Include invalid images and recording drops; never
  fabricate lines for unreceived images or infer drop/saving from missing lines.
- Convert native timestamps to nearest integer ns with documented units and
  integer/rational arithmetic, preserving device origin; no host substitution or
  raw-tick duplicate. Missing units/optional metadata warn and leave the field null,
  without dropping valid pixels or blocking Ready. Timestamps are exact JSON integers.
- Retain an explicit mapping for every encoded video frame to its real source or
  identified padding under A08. Mark duplicated frames so post hoc analysis can
  discard them without inferring duplication from image equality. Padding never
  creates a received-source record, native timestamp or acquisition count. An
  input submission alone does not prove encoding; persisted correspondence checks
  remain external post hoc work. The existing frame-log schema/writer still need
  this mapping amendment before the revised timing behavior is implemented.
- Append complete frame lines, in contiguous source order, once final drop decisions
  are known. Every **1 s** (`sync_interval_s`, configurable) and at closure, write
  ready lines and request one OS sync; completion requires sync success. Not a
  maximum-loss window.
- `completion` (once, at closure): outcome (`completed`/`interrupted`), producer
  cutoff, final received count and accounting completion, recorded video frame count,
  A11 ON/OFF dispatch/acknowledgement evidence (SYS-004), post-cutoff excluded-frame
  count/last native counter (A09), one SDK transport-counter summary and grouped
  diagnostics. Unknown values are `null`, never guessed. No timing history or setup
  copy.
- Diagnostics use stable CephVR codes with native SDK cause/details, grouped by code
  with count and first/last observation. Code at most **64 bytes** (must fit); details
  at most **1,024 bytes** (truncate at a character boundary with ` [truncated]`).
  Per-frame invalid-image causes live on frame lines, so they survive a crash. Surface
  an operational warning's first occurrence promptly and update it thereafter;
  confirmed device/storage/logging errors are reported immediately and classified
  under E06. The [diagnostic contract](../../contracts/acquisition/diagnostics.md)
  owns catalogue and delivery; no per-frame alert or logging service. Backend status
  exposes each camera's latest transport summary after trial closure, without further
  SDK polling.

**In-process accounting**

- The capture thread passes each received frame's record to the recording thread with
  its pixels in the A03 recording queue. A frame dropped from the queue releases its
  pixels but keeps its record (`dropped = true`). Records awaiting append are bounded
  at **10,000 per camera** (`pending_records_capacity`, configurable); exhaustion is a
  logging failure: fence the recording path and report to E06, never silently drop
  records, block capture or claim complete accounting.
- Once all trial accounting, bounded post-cutoff retrieval and final purge are sealed,
  the capture thread hands the recording thread one terminal end marker carrying the
  E11 cutoff, in-trial received count, actual stop observation and excluded-frame
  accounting; unknown values stay absent with explicit incomplete accounting. Camera
  Stopped stays prompt and independent of this drain. The recording thread reconciles
  unique complete IDs, cutoff and applicable ON/OFF outcomes before successful
  closure. Stop/finalization deadlines are unchanged; the
  [recording lifecycle](../../contracts/acquisition/recording-lifecycle.md) binds
  failures.
- At finalization, including Interrupted trials, drain admitted frames, reconcile the
  final count/cutoff, complete encoding, write the completion line, sync and close
  both files before Finished. No completed-file integrity scan, MP4 inspection or
  decoding pass gates trials/sessions; Closed is closure evidence, not a
  file-integrity certificate.
- If valid images were acquired but every recording frame dropped, close the frame
  log, warn "no video frames" and continue if online finalization succeeded. Never
  fabricate a playable video, delete uncertain output or change Interrupted. Report
  video content, artifact presence and closure separately under the
  [empty-video contract](../../contracts/acquisition/empty-video.md).

**Crash behavior**

- There is no recovery tool. After a crash the fragmented MP4 (A08) plays up to its
  last complete fragment and the frame log is valid up to its last complete line, with
  no `completion` line; `video_frame` maps frame lines to video frames. Checking
  correspondence, integrity and timing is external post hoc work, outside CephVR
  runtime. Startup never decodes or repairs recording files.

**Contract status:** remaining contracts and validation are in the single acquisition
[worklist](../../contracts/acquisition/README.md#remaining-decisions-and-implementation-work).

<a id="a08"></a>
### A08 — Video encoding and container

**Status:** Accepted · **Revision:** 49

**Encoder lifecycle and input**

- FFmpeg/NVENC is fed by each camera worker's recording thread. Before fresh Ready,
  prepare the recording thread, queue and validated encoder settings without launching
  FFmpeg; Ready means recording-thread preparation, not a running encoder.
- At ScheduleTrial acceptance (about T − E05 start lead), launch a fresh supervised
  FFmpeg subprocess with the final scheduled paths so start-up precedes T; feed it no
  frames before T. Its empty/unwritten output file is allowed; frame-log creation
  stays at/after T. Launch/initialization failure before T is a required failure
  before release (E06 classification, never a late start); first-input failure
  follows E06. Bounded buffers, drop policy and E05 evidence deadlines are unchanged.
- If the schedule is cancelled, the session interrupted or release fails before T,
  terminate that FFmpeg and delete only the output file it created at its recorded
  path; keep and report an unexpected file under E06.
- Recording `Started` requires processing real in-trial frame input or its accounting
  within E05's **250 ms** report deadline. It proves neither encoding nor persistence;
  encoder progress and verified closure are separate obligations.
- The recording thread writes raw frames in the resolved input layout to FFmpeg's
  stdin; FFmpeg performs NVENC encoding and MP4 writing. Acquisition injects the input
  arguments (`-f rawvideo -pix_fmt <fmt> -s <W>x<H> -framerate <nominal rate>`). No
  PyAV, intermediate file, TCP endpoint, custom muxer or extra compression stage.
- The recording thread owns pipe writes, taking frames from the A03 in-process queue
  and appending frame-log lines; health/control work runs independently and control
  handlers never touch the pipe. Write each frame promptly, without intentional
  batching; backpressure fills the queue and follows A04's drop rule. Pipe writes
  prove neither encoding nor disk persistence. Stalled I/O keeps existing deadlines.

**Arguments and pixel formats**

- Each camera owns a complete independent `ffmpeg_args` list, the only home of its
  encoding defaults in acquisition config, for encoding, explicit encoder-format
  conversion/filtering and compatible container options. No shared-list merging or
  separate quality/compression controls. Codec, pixel format, range/matrix, supported
  lossless modes, quality/rate control and lookahead are tunable values, not
  architecture decisions. Acquisition owns validated input arguments and output
  paths; no user input-path list or output destination override.
- B-frames are forbidden: acquisition injects fixed `-bf 0` so stored order equals
  presentation order and a crash leaves a clean prefix. Operator arguments cannot
  provide this option or the injected raw-input arguments, even with equal values.
  Log effective active settings and lock at Start; validate changes against these
  contracts. Encoder buffers are additional to ring capacity.
- Recording uses the shared pixel methods to prepare RGB for color/Bayer sources or
  grayscale for monochrome, retaining source effective bit depth; native unpacking and
  Bayer reconstruction happen in the recording consumer, not before shared buffers.
  Submit a resolved FFmpeg-compatible RGB/grayscale input layout, never Bayer or
  uninterpreted packed camera pixels or preview images; avoid unnecessary
  channel/depth conversions. Wider storage containers do not claim extra sensor
  precision.
- Bayer recording is reconstructed color, not an uninterpreted mosaic. Common native
  preparation follows the selected source representation without another operator
  conversion switch (details in the pixel-processing contract). Extra FFmpeg
  conversion does not permit reinterpreting packed native bytes or using the
  display-scaled image.
- Each camera may set `recording_bit_depth` to 8 or 10. Absence preserves source depth
  and blocks Setup if the configured recording path cannot preserve it, with an
  actionable warning naming the camera, source/target depths, codec/format and
  incompatibility. Acknowledging the warning cannot make Setup succeed; compatible
  explicit settings and fresh Setup are required. Reducing a deeper source requires
  an explicit value. Fixed full-source-range quantization happens only in the recording
  consumer, retaining native acquisition/tracking precision. Log source and recording
  depths and the conversion mapping; reduced precision cannot be recovered from the
  video. No automatic downgrade or codec/encoder fallback.
- Select the saved pixel format explicitly in each camera's FFmpeg arguments;
  compatible YUV or RGB/grayscale storage is allowed. Validate the full
  prepared-input/codec/output path, including post-filter dimensions, output depth
  and chroma layout, against the resolved recording depth and actual build/device
  capabilities on SYS-002's encoding adapter; an FFmpeg encoder listing alone is
  insufficient. Unsupported combinations fail Setup. The terminal pixel format must
  match the recording depth and intermediate precision may not drop below it. Conversion and declared output
  metadata must agree on range and color matrix. Source-depth representation does not
  promise lossless compression; metadata labels alone establish neither conversion
  correctness nor camera color calibration.
- Reject arguments conflicting with paths, trial bounds, timestamp/frame
  correspondence or container/crash-prefix rules, naming the argument and rule; never
  silently rewrite. Reject duplicate single-value options, including
  aliases/overlapping selectors; explicitly mapped repeatable options stay allowed.
  An explicit option/alias/value/filter validation table rejects unrecognized
  arguments before Ready. Extend support deliberately, preserving ordinary independent
  camera argument lists and tunable encoding controls. See the
  [encoding contract](../../contracts/acquisition/encoding-options.md).
- Optional video filters form one linear chain per camera from `format`, `scale`,
  `crop`, `pad`, `hflip`, `vflip`, with order/parameters validated to preserve frame
  count and presentation times. No branching graphs. Transform parameters stay fixed
  for the session: constants and validated image-size expressions resolving to fixed
  values, no frame/time-dependent expressions or live updates. Unsupported
  filters/combinations block Setup with an explanation. Filters affect recorded video
  only, not acquisition or tracking input; the default chain belongs in camera
  arguments, not architecture policy.

**Tools and verification**

- Resolve `ffmpeg`/`ffprobe` on PATH at Setup and retain the resolved executables.
  Check availability/advertised capabilities and arguments without a test encode or
  dummy file; no auto-install/custom tool path. Actual initialization, throughput and
  storage remain runtime/rig checks.
- Target a documented, tested FFmpeg version, selected during implementation and
  called validated only after execution checks; upgrades are deliberate and the exact
  baseline remains unset. With recording enabled, a different installed version gives
  a Setup warning (tested versus installed) in the session log, with no prompt, so
  unattended Setup is not stalled. Missing tools, known incompatibilities and invalid
  arguments still block Setup.
- Bounded encoder probes establish only the tested device/build/representation cases.
  Production source conversion, concurrent throughput and failure behavior still
  require E15 [rig verification](../../reports/rig-verification.md); a passing smoke
  test neither selects defaults nor validates the recording backend.

**Container and closure**

- One continuously encoded hybrid-fragmented MP4 per camera/trial, converted to
  ordinary MP4 on graceful close. No clip stitching or encoder reuse across trials;
  faststart's extra pass is disabled. Fragment/keyframe target **1 s**, configurable
  and dependent on available frames; independent of frame-log/video sync and not a
  loss bound.
- Before Finished, drain only in-trial frames and confirm online accounting, encoder
  finalization/exit, successful sync and closure under A07. File
  reread/index/sample validation is external post hoc work, not a runtime gate.
  Disabled saving creates no encoder. Crash output follows A07.
- While work is pending, **10 s** (configurable) without advancing FFmpeg progress
  fails the recording path under E06. Unchanged reports/heartbeats do not reset it;
  idle with no input work has no progress obligation. Earlier start/closure deadlines
  still apply.
- Encoder diagnostics drain continuously into a bounded in-memory tail: **100 lines**,
  **64 KiB**, including incomplete lines. On failure it feeds the existing incident
  report; no full FFmpeg log or interruption delay. The tail is not crash-durable.

**Video timing**

- Video is constant-rate at the nominal rate recorded in the frame-log header: the
  applied MCU rate for externally triggered cameras, or the resolved `frame_rate_hz`
  for free-running ones. The coordinator supplies its controller-confirmed typed MCU
  observation in the private worker Setup payload for external-trigger saving;
  missing or invalid applied-rate evidence blocks recording preparation.
  Maintain the nominal video cadence through recording drops by padding missing
  video slots with explicitly identified duplicated images. Padding must preserve
  video duration rather than compressing gaps. A07 records encoded indices,
  duplicate disposition and real-source references so post hoc analysis can
  identify drops and discard duplicates. Never relabel padding as real acquisition.
  The video timeline is not a scientific clock; host receipt/native timestamps and
  SYS-004 pulse alignment retain their meaning.
- Real images retain source order; padding stays within the actual E11 interval.
  Empty recordings follow A07's empty-video handling. The slot assignment and
  leading-gap treatment require contract formalization; no unanswered choice or
  current unpadded writer establishes those rules. Backwards host times interrupt
  under A05. Encoder/storage failure handling and original deadlines are unchanged.
- Sync flushed video storage every **1 s** (configurable) and at final closure,
  without stopping encoding. This cannot persist encoder-buffered frames or guarantee
  a loss window. Video sync is separate from the frame log; storage failure enters
  E06.

**Contract status:** [recording lifecycle](../../contracts/acquisition/recording-lifecycle.md)
defines launch/output gating and producer cutoffs.
[Encoding options](../../contracts/acquisition/encoding-options.md) and
[Windows resources](../../contracts/acquisition/windows-resources.md) define
validation, scheduling and storage mechanisms. The encoder input/throughput rig
deferral (E15) remains.

<a id="a09"></a>
### A09 — Source-frame identity

**Status:** Accepted · **Revision:** 12

- A camera frame belongs to a trial only if its host-monotonic receipt timestamp
  (A05) satisfies `trial_start <= receipt < trial_stop`, using the normal scheduled
  stop or camera-owned interruption cutoff under E11. Earlier or later receipts are
  excluded from trial source IDs, acquired-frame totals and trial recording/tracking
  input, even if exposure fell inside the interval. Never relabel a late frame as a
  recording drop or shift its receipt timestamp. Camera native timing/hardware pulses
  are post hoc alignment evidence, not the online membership clock.
- Number received source frames **0, 1, 2, ...**, restarting at zero per camera at
  every trial, independently of recording success. Received invalid images take IDs
  in the same sequence with their receipt timestamp; their frame-log lines are dropped
  (A07) and their pixels never reach consumers. Identities persist through recording,
  tracking and Visual Stimulus lineage; recording drops and tracking-state resets never renumber
  frames.
- Trial numbers remain **1-based** under E04; camera-native hardware counters are
  separate and unchanged. A frame reference must include its camera and trial
  identity (directly or through unambiguous enclosing context); a bare counter is not
  globally unique.
- With a reliable camera hardware frame counter, retain native counters alongside
  CephVR identity and detect unexpected gaps between valid received frames, after
  accounting for documented wrap/reset behavior. Record the gap, warn and continue
  with valid images; a gap alone neither interrupts the session nor renumbers frames.
  Record only what the counter evidence establishes; never fabricate frame lines or
  timestamps for unreceived frames. Counter availability is device-dependent and does
  not replace valid-frame health checks.
- For an unexplained native counter discontinuity, including an unexplained backwards
  jump, preserve observed values, warn and continue with valid images. When saving,
  record it in camera diagnostics; start later gap comparison from the new observed
  value. Never infer a missing-frame count for the ambiguous interval, synthesize
  frame lines or change CephVR source IDs. Confirmed device failures enter E06
  incident classification.
- Session preview shows in-trial frames with their trial source IDs. Manual preview
  (A10) uses a separate non-trial scope: temporary frame IDs per camera acquisition
  run, with camera/run context distinguishing them from trial-local recording IDs.
  The scope does not restart for each Idle period; a new acquisition run gets a new
  scope so stale references cannot identify its frames.
- Non-trial frames and IDs serve only the transient live preview/tracking pipeline:
  no video frames, frame-log lines or per-frame session-log entries. E11 still
  excludes pre-roll/post-roll; only buffered in-trial data may finish writing after
  the trial boundary.

**Contract status:** native counter fields and validity flags are declared in the
[adapter](../../contracts/acquisition/camera_adapter.pyi),
[SDK mappings](../../contracts/acquisition/sdk-mappings.md) and frame-log schema.
Actual model clock/counter availability remains hardware evidence; receipt
stamping/filtering and the mappings still need runtime implementation.

<a id="a10"></a>
### A10 — Camera capture lifetime and Basler settings

**Status:** Accepted · **Revision:** 55

**Capture lifetime**

- Read SDK images in order (Basler OneByOne) from a configurable
  **10-buffer SDK pool** per camera, separate from consumer rings, validated at Setup
  and fixed for the session. Upstream buffering is not a latency/loss guarantee.
- Capture only during trials; no intertrial capture, including for preview.
  Preparation may keep cameras open/configured and arm external triggering with pulses
  off. After prior drain/closure, purge stale SDK frames before arming; never reopen
  devices routinely or discard admitted trial data. Free-running capture starts at T.
  E05 evidence deadlines and E11 bounds apply.
- At cutoff, seal trial admission but keep bounded excluded-frame retrieval until
  external OFF has a terminal outcome plus the prepared drain margin (exposure,
  transfer and one frame period). Count final purge discards when observable; unknown
  counts stay unknown. Free-running cameras stop generation promptly and drain only
  buffered results. This cannot extend trial data or the E05 Stopped deadline; SDK
  cleanup/accounting uses the remaining original finalization budget. See the
  [recording lifecycle](../../contracts/acquisition/recording-lifecycle.md).
- During Setup, request supported native timestamp/frame-counter metadata when
  needed, before final readback/layout and buffer preparation; retain usable metadata
  without redundant enabling. Report unsupported/unavailable fields and continue
  under A07, without changing trigger behavior or host-monotonic boundaries. Confirm
  effective metadata settings before Ready and fix them for the session.
- Before every trial, read back pixel format, dimensions, trigger mode, exposure and
  gain against confirmed session settings, with connection/arming checks. A mismatch
  or unreadable required value fails preparation under E06; never silently adopt
  changes or reapply settings to repair a locked session.
- Require a usable first frame by **T + 250 ms**. During capture, **1 s** without
  usable frames (per-camera configurable) reports failure to the supervisor. Measure
  at host receipt before queues; invalid images do not reset the timer. Intentional
  gaps need suitable configured timeouts. Not applied after stop; recording drops are
  not missing camera frames.

**Connection diagnostic**

- Manual camera commands carry the controller-accepted complete acquisition
  draft and revision. Install newer drafts only with exact controller/backend/parent
  identity and no conflicting device/diagnostic ownership; this is not SDK readback.
  Unchanged drafts may advance an unrelated revision. Microcontroller commands use
  controller-owned settings and the accepted revision under A11; its serial owner
  closes the old port before opening a newly selected one, under the original deadline.
- An explicit controller-authorized Configuration check opens the assigned serial,
  verifies its identity, and closes only a device opened by that check. The camera
  worker remains the sole SDK owner; no PFS/settings, capture, pulses or recording
  are started. Existing preview is not interrupted. Retain cleanup as unconfirmed
  on failure until normal device-release evidence resolves it. This check is not
  frame-delivery, trigger or Setup-readiness evidence.

**Preview**

- Manual Preview is explicit Configuration work; stop capture/pulses and confirm it
  before Setup. An optional low-rate session preview (A03, `session_preview_max_hz`,
  default 10, configurable, 0 = off) shows in-trial frames only and never changes
  capture or pulses.
- Controller-authorized T08 diagnostics may consume the selected manual preview
  through A03's distinct ordered ring without another camera/SDK owner. Exact
  diagnostic/preview identities and confirmed attachment/release bind the consumer;
  stop diagnostics and confirm release before Setup or source replacement.
- Display newly arriving frames without a software FPS cap, always the newest
  available, skipping superseded images if rendering falls behind. No display backlog
  or busy polling. Camera rate is unchanged and not every acquired frame is guaranteed
  to reach the screen.
- Basler preview uses its SDK image converter through the common conversion module,
  with a converter owned by the preview consumer. The
  [SDK mapping contract](../../contracts/acquisition/sdk-mappings.md) defines binding
  and format/edge handling; full-range scaling follows the pixel contract. Actual
  device conversion and preview behavior require rig verification.
- Preview converts color/Bayer to ordinary RGB and keeps monochrome grayscale, on
  private copies in the preview consumer; native pixels and recording/tracking
  conversion are unaffected. Output bit depth is configurable, default
  **8 bits per channel**; validate the conversion and viewer path and report
  unsupported depth rather than substituting another. Scale the native format's full
  valid range to the configured range consistently across frames; no per-frame
  automatic contrast.
  Storage width and physical display precision are separate from this setting.
- Preview capture can run headlessly. The acquisition coordinator owns OpenCV
  windows and private latest-frame readers; GUI/headless Show/Hide commands bind the
  exact active manual run. Each Win32 window pumps HighGUI on its owning thread,
  outside the coordinator event loop. Native X closure hides only that window.
  Publish monotone visibility/failure observations for the exact run; stale callbacks
  cannot change a replacement run or complete a camera command. Viewer availability
  gates neither Ready nor capture start. Retain each local reader in the native
  ownership ledger and confirm window/mapping closure before buffer release. Failed
  viewer release remains a cleanup blocker while capture/pulse cleanup is attempted.
  Explicit external latest-frame transfers remain available to authenticated clients,
  with one display consumer per slot. Closing a viewer is distinct from Stop Preview
  and from loss of the controlling client.
- The OpenCV image area is a fixed square with aspect-preserving fit and black
  padding. Mouse wheel zooms the private image about the pointer, bounded from
  fitted size to 16×; double-click restores fit. Repaint cached pixels without a
  new frame. Show may supply bounded initial physical-desktop placement/size from
  the GUI; subsequent movement is operator-owned. Display transforms never edit
  source coordinates, camera settings or recording/tracking pixels.
- Preview may explicitly open a session-disabled camera without changing session
  enablement or recording flags. Validate its device/settings and required trigger
  configuration; scope temporary devices, buffers and pulses to the preview request.
- Preview uses experimental camera timing: external-trigger preview drives the same
  pulse rate and never silently switches to free-running.
- Stop Preview stops capture and its pulses, closes that camera connection and
  releases its preview buffers after safe detachment; later Preview or Setup
  reopens/verifies the camera.
- On controlling-client disconnection or explicit release without an atomic handover,
  promptly stop preview/pulses and begin normal safe release (E03: no grace period).
  A new control claim cannot cancel cleanup or restart preview automatically; explicit
  restart waits for confirmed release. Active experiments are not stopped.
- Editable preview changes, including pulses and buffer layout, follow
  stop/apply/restart; restart only on success, otherwise capture/pulses stay stopped.
  Session locking and control ownership remain E07's.
- A camera-local preview failure reports the error and stops/releases only that
  preview; independent previews may continue, and shared-component failures stop every
  affected preview. Failed cleanup stays blocked under E06; experimental sessions use
  E06 incident classification, and preview-local cleanup stays separate.

**Microcontroller pulses**

- Controller owns one configured microcontroller connection with independently
  configurable behavioral/tracking pins/rates. Validate distinct active pins;
  disabled/free-running roles need no pulses. Port, wiring and rig values stay
  explicit. Acquisition requests camera triggers through A11’s typed controller API
  and records returned timing evidence; it never opens the COM port.
- Firmware hardware timers generate pulses from the board's local clock,
  independently of serial parsing; Python sends configuration/ON/OFF, not a command
  per pulse. Validate board/pin support; no main-loop timer polling substitute.
- Fixed active-HIGH pulses, idle LOW, **50% duty cycle**; frequency determines width,
  with no width/polarity setting. Immediate OFF can shorten the final HIGH (A11).
  Verify electrical levels and camera edge/wiring on the rig.
- Keepalive defaults to **1 s** and firmware watchdog to **3 s**, configurable and
  separate from process heartbeats. The watchdog stops pulses locally; keepalive
  never resumes them. A11's serial reservations must fit this budget; normal Stop
  still uses its boundary.
- **Deferred:** projector-synchronized pulses. If implemented, loss warns and falls
  back to the local clock; detection/re-lock need future design. No projector
  settings or requirement exist.
- During Setup, check external-trigger cadence against applicable SDK limits and
  enabled transport limits for the final resolved layout/settings and applied MCU
  rate. A known insufficient payload budget fails preparation even when the trigger
  maximum is unavailable. Otherwise an unknown maximum warns and allows Setup with
  no confirmation gate. Never silently change ROI, precision, exposure, transport or
  cadence to pass; passing these checks is not measured capture throughput.

**Camera settings**

- Select camera ROI from the experiment's required field of view, then explicitly
  tune transport to the requested cadence and verify it on the rig. Retain the
  current behavioral ROI as the initial candidate if it covers that field; do not
  crop solely to fit an encoder. If full sensor width is required, explicitly select
  compatible HEVC recording arguments under A08 and verify throughput. This does
  not authorize automatic ROI, codec, depth or cadence changes.
- Manual exposure/gain with automatic controls disabled. Device configuration operations cover
  exposure, gain, free-running rate, ROI, pixel format and applicable triggers, using
  `exposure_us`, `frame_rate_hz`, pixel ROI and explicit SDK gain units (dB or
  labelled native/raw). Uncommon features stay available through PFS.
  The initial GUI exposes the narrower PylonViewer/PFS workflow in
  [G01](gui.md#g01); this does not remove backend/headless parameter operations.
- External triggering is the per-camera default; free-running is configurable before
  session locking only with that camera's explicit `unaligned_free_running = true`,
  recorded in `SESSION_CONFIG.json`; otherwise Setup rejects it. Such a camera has no
  SpikeGLX pulse alignment under SYS-004/E12. External defaults: FrameStart,
  RisingEdge, Timed exposure. Preserve explicit saved/PFS/operator values and validate
  the combination; input lines stay explicit. Timed duration is distinct from manual
  exposure control; external pulses, not a free-running frame-rate field, set
  external-trigger cadence.
- Transport tuning uses explicit per-camera configuration, SDK defaults otherwise.
  Validate/apply supported overrides and retain resolved active settings under E07;
  invalid requested overrides fail preparation. No automatic tuning, OS/driver
  reconfiguration or coupling to FFmpeg arguments; lock at Start. Overrides are
  file-based, resolved from the owning TOML before preparation; saved/session edits
  cannot override them. GUI exposure of transport controls is undecided and removes
  no existing camera controls.
- Use exact supported SDK parameter names, native types/units and connected-device
  validation. Initial transport scope covers Basler USB3 and GigE in the same adapter;
  applicability follows the actual interface. Include explicit device-link bandwidth
  mode/limit mappings under the [SDK registry](../../contracts/acquisition/sdk-mappings.md#transport-and-metadata-bindings).
  No generic node-write escape hatch or claim that untested combinations are verified.
- The SDK supplies controls, ranges, increments and choices, refreshed after relevant
  edits. Fill missing feature values from the selected camera during Setup/permitted
  device operations, preserving explicit values/policies; missing wiring/device IDs
  cannot be inferred. Offline validation may leave device features pending; Setup
  resolves them or blocks Ready on unsupported/unreadable required settings.
- Setup, preview, camera/pulse edits and PFS operations share one internal
  resolution/readback/adoption workflow with operation-specific checks; no separate
  confirmation/validation machinery.
  [Configuration control](../../contracts/acquisition/configuration-control.md) owns
  its detailed contract.
- Read back applied values before locking. Camera adjustments warn with requested
  versus actual values, compared at documented precision, without separate
  confirmation. Update controller config, GUI/headless state, history and
  active-camera session logs; revalidate consumers/layout/encoding. Locked values
  cannot change. Microcontroller rate adjustment/readback follows A11.
- Partial/failed camera application leaves capture/pulses off and preparation failed;
  report actual readback as diagnostics where available (unknown is not success). No
  automatic hardware rollback. Require successful reconfiguration before Preview and
  fresh successful Setup before Ready; rejecting a configuration edit cannot restore
  hardware settings already applied by an explicit device command.

**PFS presets**

- An SDK-generated PFS snapshot is retained alongside standard typed camera settings
  for advanced Basler-persistable features, refreshed after successful device
  edits/import and readback and included in reusable configuration/history (E07).
  Standard explicit edits stay authoritative. Setup uses retained current settings,
  never automatically rereading the imported file. PFS is not all device state.
- PFS import/export is optional and presets stay external: session configuration
  records only filenames, with no PFS copy or snapshot contents in session/trial
  outputs; standard camera settings remain logged. A source filename alone does not
  show that later edits match the file.
- Import loads the file for further GUI/headless editing: apply/validate, then read
  back. Cross-model imports rely on SDK validation and actual readback, with no
  same-model gate. Adopt successful imported settings/snapshot into controller state;
  later edits take precedence. Device assignment and CephVR-only settings stay
  separate.
- Save as PFS first validates/applies pending camera edits, adopts actual readback and
  refreshes the snapshot, then writes the applied/read-back values to a new selected
  external file, never automatically overwriting the source. Failed
  validation/application/readback prevents export; never silently save older values.
- Changes after import may run unsaved: warn to save a new external PFS, with no
  confirmation gate or Setup/Start block solely for unsaved changes. Normal
  validation/readiness applies; never reload the old preset or export automatically.
  Saving a preset is an explicit operator action.
- Import and export need the assigned camera connected/open through the SDK; preview
  need not run. No offline pending import or cached-snapshot export. Camera
  unavailability fails the operation with an actionable explanation; offline
  configuration editing/history restoration remains available under E07.
- For a PFS request the camera worker opens only the assigned device if needed,
  without starting acquisition/pulses, and keeps that connection across related
  import/edit/export operations until the GUI/headless client explicitly signals
  editing completion (no inactivity timer); then it closes and releases it, retaining
  resolved settings/snapshot. An already owned connection is reused without a second
  SDK owner; preview keeps its own lifecycle. Confirm release through normal cleanup
  reporting; a close failure is not success.
- Setup automatically finishes outstanding camera editing and waits for confirmed
  connection release before resource preparation, within the existing Setup deadline
  and with no operator step. Current settings are preserved and no preset is saved
  automatically. Failed cleanup blocks preparation under E06.
- Controlling-client disconnection or release starts bounded editing-connection
  cleanup immediately, with no grace period or automatic reopen. Finish/reconcile an
  already accepted device operation before releasing its resources; connection loss
  cannot undo an operation or free an in-use SDK handle. Reconnection/new control does
  not cancel cleanup. Active experiments continue headlessly under E03.
- Acquisition serializes PFS/device access under control ownership while
  configuration is editable; these operations may configure a camera but never
  acquire images or bypass Setup. Report SDK/validation/write failures. CephVR roles,
  recording flags and FFmpeg settings stay in CephVR config, not PFS.

**Contract status:** the acquisition worklist separates contract completion, required
hardware information and later implementation; no new deferral is implied.

<a id="a11"></a>
### A11 — Microcontroller command protocol

**Status:** Accepted · **Revision:** 40

**Board and firmware**

- Target the rig's COM8 Arduino Uno first, with a board-independent host serial
  protocol; add board implementations when needed, with no initial multi-board
  firmware framework. Firmware-reported pins and actual timer behavior require
  validation on this board.
- Firmware may be installed manually or through explicit GUI Upload in Configuration.
  Controller authorizes the operation; a focused controller Microcontroller module is the sole COM-port owner
  and performs the handoff. Camera/device ownership, capture, diagnostics, another
  operation or unresolved native cleanup block Upload. Select a compiled application
  `.hex` or an Arduino `.ino` sketch. Controller digest-pins the image or complete
  supported sketch source snapshot, compiles sketches with installed Arduino CLI for
  Uno in private storage, confirms compiler cleanup and validates the application HEX
  before serial release. Compile failure/cancellation leaves serial untouched. The same
  installed CLI uploads with verification under the original operation deadline.
  No automatic flashing, tool/core/library installation or board selection is added.
- Controller closes serial, supervises the bounded Configuration helper under E08,
  confirms each phase's exact job/process/pipes and private source/build/image cleanup,
  then opens a fresh
  protocol/capability connection and verifies outputs off. It never resumes capture
  or pulses. Failed/uncertain upload reports failure; unresolved helper cleanup blocks
  Setup and manual device access until exact cleanup succeeds. Setup still rejects
  incompatible firmware. Native flashing and electrical acceptance remain E15 rig work.
- Serial protocol version is integer **3**, separate from firmware release, and must
  match exactly at Setup; future wire changes increment published versions. Firmware,
  not host monitoring alone, implements A10's watchdog.

**Connection**

- Microcontroller connection, command arbitration, keepalive, diagnostics and firmware
  helpers belong to the controller regardless of acquisition participation. Serial I/O
  stays on its dedicated owner thread and tool work stays outside the lifecycle loop.
  Acquisition is an authenticated trigger client: typed configure/reserve/ON/OFF/status
  and release calls retain exact generation/claim, original deadlines and returned MCU
  timing evidence. The final external manual preview releases its claim after confirmed
  OFF and camera cutoff; remaining external previews retain it. Acquisition owns its logical device claim, never the physical COM handle.
  Failed or uncertain release remains a cleanup blocker; no automatic pulse resumption.
  The standalone review GUI opens no serial handle; physical tests use the managed
  controller API. Serial timing reloads only with no owned port.
- Pin tests and Upload require idle Configuration and no camera-trigger claim/device
  activity. Control loss releases Configuration diagnostics; active experiment work
  follows E06. Controller shutdown includes serial and native helper cleanup within
  the original shutdown/authority-loss allowance and application backstop. Pending
  release fences new execution while admitting camera safety cleanup. Firmware watchdog
  remains independent.

- One serial owner opens only the configured port. Boot/reset leaves outputs off and
  volatile configuration invalid. Reopen requires outputs-off verification, fresh
  capabilities and full configuration; no automatic pulse/session resumption.
- Never deliberately request an extra board reset on connection or assume opening
  preserves state; unavoidable port-open resets go through startup verification.
  Exact DTR/RTS behavior depends on the rig board/driver and is unverified.
- After opening/reopening, send bounded read-only startup probes until firmware
  responds within the existing Setup/reconnect deadline; no fixed boot sleep or fresh
  timeout budget. Confirmed incompatibility fails immediately. Keep
  single-request/ID matching and output-off/readiness checks before configuration or
  use.

**Wire format**

- Newline-terminated ASCII `CONFIGURE`, `ON`, `OFF`, `STATUS`, `PING`, `CAPS` and
  bounded `DIAG_START`, `DIAG_STATUS`, `DIAG_STOP` with
  OK/ERR. Space-separated named fields hold tokens/numbers; no quoting/escaping/debug
  prints. Per-output keys use lowercase `behavioral_` / `tracking_`, not numeric maps.
- Every complete line, including newline, is at most **512 bytes**; no additional
  text field limits. Bounded reception precedes parsing. Reject malformed,
  unknown-field or oversized commands whole, discarding bad input through newline;
  never truncate into an executable command. Validate complete updates before
  changing outputs.
- Every request carries `id=<fresh-connection-id>-<counter>`; combined IDs are never
  reused. Replies echo the full ID; ignore mismatched replies with a diagnostic,
  keeping the original deadline; they are not fresh health evidence. ERR uses
  symbolic uppercase underscore codes plus structured context, explained by host
  clients.
- Defaults: **115200 baud**, **100 ms acknowledgement timeout**, configurable before
  Setup. One outstanding request at a time, PING included. Earlier operation/trial
  deadlines win. OK follows application (including any authorized restart) and
  resulting state, not early acceptance. MCU state proves neither frame receipt nor
  physical pulses.
- Timeout reports unconfirmed completion with no automatic retransmission, except
  bounded read-only startup probes, each with a fresh ID; CONFIGURE/ON/OFF are never
  retried. Cleanup may send a new OFF with a new ID; a late reply cannot restore
  timely success.

**Boundaries and stopping**

- Normal ON dispatch boundary B binds to host T and OFF to T + duration; reserve the
  serial channel before each and dispatch at the boundary after valid release. This
  schedules host dispatch, not firmware application or a physical edge; camera
  admission/cutoff stays independent under E11. Keep dispatch/acknowledgement
  observations separate and persist them in each recorded camera's A07 frame-log
  completion line (`pulses`).
  [MCU timing](../../contracts/acquisition/microcontroller.md#host-boundary-and-evidence-binding)
  defines wire evidence and start/stop deadline limits. No early compensation or new
  firmware clock/scheduling protocol.
- Reserve the serial owner for known ON/OFF boundaries B: admit a routine request only
  if `now + ack_timeout < B`, rechecked at dispatch. Drain before B; defer routine
  traffic until the boundary command completes. Service keepalives early as needed;
  Setup/preparation must validate compatibility with the watchdog budget. Never extend
  deadlines, overlap requests or disable the watchdog to resolve a conflict.
- Validate the entire Abort stop path at preparation: one outstanding request, OFF,
  camera stopping/drain and report delivery must fit the original shared allowance.
  After two 100 ms command budgets, the default remaining **50 ms** is reserved for
  camera completion/reporting; an allocation, not a sleep or measured guarantee.
  Reject incompatible settings rather than extend the shared deadline. Rig timing
  evidence is pending; detailed checks/bindings belong to the MCU contract.
- Unscheduled Abort cannot preempt a transmitted request. Stop cancels unsent
  execution commands and precedes queued routine work: stop local admission promptly,
  send OFF at the next serial slot and keep the original stop deadline. Missing stop
  evidence is Unconfirmed under E06, never a late successful stop.
- OFF/watchdog/interruption cancels scheduling and drives owned pins LOW immediately,
  including any active pulse; stale timer callbacks cannot restart it. Acknowledge
  after application. Host dispatch-to-hardware latency is not zero.

**Outputs and rates**

- Grouped ON/OFF drives enabled externally triggered roles at trial boundaries;
  individual preview control remains, and preview asserts no trial marker. The first
  pulse starts on ON application without a full-period delay. Repeated ON retains
  phase; OFF is repeat-safe. Physical simultaneous edges are not guaranteed.
- CONFIGURE replaces both roles together. Active outputs derive from session roles
  during experiments, or from explicitly requested previews in Configuration; preview
  never changes session enablement. Inactive outputs send only `<role>_enabled=0`,
  clearing their firmware assignment and leaving old pins LOW. Host reusable values
  remain.
- Requested rates use decimal Hz on a **0.1 Hz grid**. Firmware computes the nearest
  feasible timing for the full pin/output configuration and fixed duty cycle;
  achievable rates need not lie on the grid. Host code does not duplicate timer
  calculations.
- One CONFIGURE operation validates the full request, resolves nearest feasible
  timing, applies it and returns actual settings; no proposal/check phase or separate
  approval of frequency adjustments. If no full configuration is feasible, reject
  without changing outputs; application failures retain the stop/off rule below.
- CephVR keeps requested and applied nominal Hz separately, with enough precision for
  stable readback and adjustment warnings and without rounding applied rates to the
  grid. Firmware reports applied Hz, pin, enabled/running and watchdog state and keeps
  only current applied state (no proposals or proposal IDs); timer internals stay in
  firmware. When rates differ, warn with role, requested/applied rates and reason,
  publish actual values to GUI/headless state and log active-camera setup. Never
  require re-entry of an off-grid applied rate or overwrite the requested rate with
  it.
- Resolve adjustments before session locking. Preparation checks the retained applied
  settings; a mismatch in a locked session fails preparation/interrupts under E06,
  never silently reconfiguring or adopting a new rate. Nominal rate is not measured
  oscillator accuracy; preserve timing precision without inventing a rounding
  tolerance.
- An authorized valid update during preview stops pulses, applies the full update and
  restarts only previously running, still-enabled outputs; old pins are released LOW.
  Validation rejection leaves outputs unchanged; application failure after stop
  leaves them off. Fault/Stop takes precedence over restoration. Boot configuration
  starts off.

**Operator I/O diagnostics**

- Trial state is an active-high output; Projector flip is a rising-edge input.
  Their pin assignments belong to Microcontroller. Per-output test intent targets
  one assigned pin for external observation in SpikeGLX; camera tests use the rate
  already configured in Cameras. Input diagnostics observe edges rather than drive
  the input. Controller owns one diagnostic on its serial connection in
  Configuration with control authority; it rejects session/preview activity and
  conflicting or unsupported pins. Firmware ends every diagnostic within two
  seconds and leaves tested outputs LOW; explicit Stop, control loss, transport
  failure and shutdown request earlier stop. Return matched state and rising-edge
  counts: observed edges for Projector flip, generated LOW-to-HIGH transitions at
  the output write for camera/Trial state tests, including the first HIGH. Trial
  state holds HIGH and therefore counts one rise; camera tests count actual timer
  transitions, not requested Hz multiplied by duration. Reset on each new test,
  saturate at uint32 maximum, and retain the stopped count until the next test.
  Counter updates and readback are atomic against timer/input interrupts. Ordinary
  STATUS/session outputs have no pulse counters. Generated counts do not prove
  electrical delivery, camera reception or SpikeGLX capture; label the GUI evidence
  accordingly and leave outputs LOW at stop.
  Installing/flashing follows the explicit workflow above.

**Status and capabilities**

- The watchdog-stop indication stays set until a successful complete CONFIGURE;
  reads, OFF and failed updates do not clear it. Reboot clears volatile state but
  requires setup.
- PING returns running states and watchdog flag. STATUS returns validity, applied
  per-output settings/state and watchdog timeout. Unconfigured values are not valid
  settings. No generated-pulse counters; native camera counters remain in A07/A09.
- Firmware owns supported pins and timer limits; no host board profiles. CAPS is
  read-only and returns one complete bounded reply, never split/truncated. Refresh on
  connection/reconnection and Setup; cache between trials. Reset/connection
  replacement invalidates it; a failed required refresh cannot pass on stale data.
- Pin IDs are firmware-defined text (`D5`, `PA8`, `5`), preserved exactly, including
  numeric-looking IDs; never autoassigned or mapped numerically. Firmware validates
  full combinations before application; advertised ranges alone are not sufficient.

**Contract status:** the
[MCU wire/error/readback and boundary scheduling](../../contracts/acquisition/microcontroller.md)
contract is implemented by the controller-owned device component and acquisition
camera-trigger client. Pin/timing/native and physical behavior require rig verification;
implementation evidence belongs in the owning reports.
