# Visual Stimulus backend

[Overview and decision register](../../architecture.md) ·
[System contracts](system-contracts.md)

Accepted runtime topology/rendering stack, stimulus scope/program model/storage,
recording policy and interface references. Declaration closure is recorded in the
[contract index](../../contracts/visual_stimulus/README.md); implementation and validation status
belong in the [Visual Stimulus report](../../reports/visual_stimulus.md).

Related: [modes and participants](experiment.md#e10),
[configuration/stimulus preparation](experiment.md#e07),
[delay measurement](system-contracts.md#a05) and
[tracking results](tracking.md#a06).

**Status:** V01–V28 and E13 are accepted; declarations are indexed in the
[contract index and worklist](../../contracts/visual_stimulus/README.md). Decision acceptance is
not a running backend or rig validation. Hardware inputs and rig verification retain
their existing deferrals; tracking design remains last.

Configuration: [visual_stimulus_config.toml](../../config/backends/visual_stimulus_config.toml).

## Decisions

<a id="v01"></a>
### V01 — Visual Stimulus coordinator and rendering worker

**Status:** Accepted · **Revision:** 15

- The backend is named **Visual Stimulus**, with `visual_stimulus` as its canonical
  configuration, registration, package and protocol identifier. Use
  `cephvr-visual-stimulus` and `cephvr-visual-stimulus-worker` entry points. Keep the
  CephVR project name, decision IDs, public port, output suffixes and program/prepared
  format versions unchanged. All components use the renamed contracts together;
  saved configurations require the new field names, and unsupported names are rejected.
- Use one Visual Stimulus coordinator and one separate Python rendering worker. The coordinator
  owns the backend's public control endpoint, preparation coordination and aggregate
  lifecycle evidence; the renderer owns display/GPU resources and live stimulus state.
  Controller configuration and trial authority remain under E05/E07/E08.
- One rendering worker serves the configured outputs and keeps running across trials
  to provide E05's configurable Idle presentation. Programs follow V02/V03, rendering
  stack V04, surface views V15; V12 owns the renderer's recording thread and FFmpeg
  subprocess when saving is enabled.
- Controller-authorized calibration presentation uses that same rendering worker,
  prepared static arena and V15 display pipeline during Configuration. It is a
  diagnostic state outside trial programs and recording, with no duration or trial
  clock. One presentation remains visible until the operator closes it; Close
  submits Idle and confirms cleanup. Setup requires it closed. Control-authority
  loss, renderer failure or application shutdown ends the diagnostic through E06/E08
  cleanup, retaining truthful output evidence rather than assuming a blank screen.
  Commands bind the diagnostic identity, accepted configuration revision, exact
  coordinator/renderer generations and original deadline. Protected profile/arena
  content is fingerprinted; asset-root-relative references carry bounded size and
  digest. Active requires actual presentation, and Closed requires confirmed Idle
  and resource closure; uncertain cleanup blocks Setup. Calibration-only orange
  horizontal and green vertical reference bars span rounded native pixel boundaries
  at 3/8 and 5/8 of each output dimension. Draw them after geometric/color output
  correction so their measured lengths refer to raw device pixels; no trial timing,
  recording or extra persistent GPU resource is added.
- Prepare the renderer's required plan/resources before Ready. After valid schedule
  and release, execute prepared stimulus timing locally against the trial clock; the
  coordinator sends no per-frame commands and relays no rendered pixels. Setup hands
  the coordinator the bounded immutable prepared bytes for its required recipe;
  publication confirmation binds the exact handle and does not release a trial or
  extend an existing deadline.
- Reuse E08's registered child ownership, Windows process-tree containment, direct
  worker health/error reporting and independently reachable safety control. The
  coordinator aggregates evidence only after the renderer's required obligations
  pass. Failure follows E06; process separation does not authorize trial continuation
  or automatic renderer restart.
- Separation does not establish higher frame rate, bounded jitter or GPU resource
  isolation; interprocess overhead and the full shared-GPU workload need E15 rig
  evidence.
- **Contracts:** [worker/control binding](../../contracts/visual_stimulus/worker-control.md)
  (private commands, prepared identities, direct cutoff/reporting, lifecycle
  aggregation); [runtime interfaces](../../contracts/visual_stimulus/runtime-bindings.md)
  (handlers, program payloads, data-path attachments). Implementation and verification
  scope is recorded in the [Visual Stimulus report](../../reports/visual_stimulus.md).

<a id="v02"></a>
### V02 — Structured trial stimulus programs

**Status:** Accepted · **Revision:** 12

- Author each trial as reusable scenes arranged in timed epochs, with groups for
  repetitions and condition-table parameter sweeps. A scene combines simultaneous
  stimuli; an epoch selects a scene, duration and parameter settings/changes.
  Families follow V04, animation V05, duration V06 and group ordering V08; the
  stimulus/function vocabulary is bound in the canonical schemas (V03).
- Each scene has an opaque background, at most one active 3D arena, then an ordered
  stack of 2D images/videos/textures. Arena geometry has normal depth occlusion; 2D
  overlays follow authored order and source-over opacity, independent of arena
  depth. Objects needing arena occlusion belong in its externally authored asset.
- The GUI presents ordered program nodes through timeline-only trial programming,
  scene/parameter controls and condition editors (add, reorder, duplicate, group).
  Stimulus appearances are prepared externally as texture/image/video/arena assets;
  the planner selects files and edits protocol structure and epoch parameters such
  as speed/direction, without texture-design controls. Legacy texture export imports
  normalize the exported image and tile dimensions into the existing model.
  Timeline edits modify the canonical nodes; expanded timing remains derived rather
  than a second editable schedule. GUI and headless authoring share
  one model and validation.
- CephVR owns the stimulus model and explicit parameter definitions.
  [PsychoPy](https://psychopy.org/api/visual/index.html) (scientific stimulus
  conventions) and
  [BonVision](https://bonvision.github.io/pages/02-Display-Environment-basics/)
  (content separate from display geometry) are design references, not runtime
  frameworks or feature-parity requirements. Define units, coordinate frames and
  conversions explicitly; angular frequency, physical texture period and
  texture-coordinate motion are not interchangeable aliases.
- Accepted linked-motion geometry convention: when both side stimuli follow Bottom,
  clockwise Bottom rotation about the subject drives Right front→back and Left
  back→front; reversing rotation reverses both. Linear speeds use the respective
  perpendicular subject-to-screen distances (angular rate in rad/s × distance),
  not half the source texture/screen width. Common longitudinal translation has
  the same physical front/back direction on both sides despite opposite local
  screen axes. Target appearances remain independent. Source/target feedback
  writer ownership is still Open; this convention alone does not define a complete
  link schema/preparation/runtime contract or imply implementation.
- Prepare the resolved program under E07 and execute it locally under V01. Closed-loop
  input may change declared stimulus parameters; adaptive trial progression remains
  deferred under E01. V24 owns feedback bindings/application-time attribution, V25
  invalid-input behavior and V26 the application-age guard.
- Every epoch supplies a complete typed settings block for each active instance;
  reject missing settings instead of inheriting base or preceding-epoch values. This
  never resets retained phase/pose/playback under V07.
- Condition rows supply named typed values through explicit references in those
  settings, with qualified group/column identity and Setup substitution. Rows never
  implicitly override parameters; V08 owns their order/repetition.
- **Contracts:** [scene composition](../../contracts/visual_stimulus/scene-composition.md);
  [authoring contract](../../contracts/visual_stimulus/program-authoring.md);
  [canonical family/settings schema](../../contracts/visual_stimulus/program.schema.json)
  (declaration boundary);
  [semantic/compiler obligations](../../contracts/visual_stimulus/stimulus-schema.md) (separate
  from structural parsing; no settings inheritance).

<a id="v03"></a>
### V03 — Versioned JSON stimulus-program files

**Status:** Accepted · **Revision:** 9

- Store reusable authored programs as versioned JSON documents (scenes, epoch/group
  structure, conditions, parameter settings). Keep media external, resolved through
  E07's asset root. visual_stimulus_config.toml (settings) and visual_stimulus_policy.toml (fixed policy, E14)
  are not a second program format. Optional epoch `batch_label` is bounded authoring
  metadata (empty when omitted), retained in source/prepared-source JSON for GUI
  targeting; it never controls ordering, timing, state continuity or rendering.
- One canonical Pydantic model in the Visual Stimulus lightweight configuration module generates
  JSON Schema, with shared structural and semantic validation for GUI and headless
  use. Apply E07's edit/Setup/locking rules; JSON is not executable Python or a code
  hook. Source and prepared formats are version 2; reject old inputs explicitly.
  Shared schema primitives give output IDs one meaning across display, calibration
  and evidence.
- At Setup, resolve V08 ordering and V06 durations into the prepared epoch plan using
  E07's retained seeds. The authored program is the editable source; the expanded
  plan is generated execution/evidence data, never separately maintained. Execution
  uses prepared data/resources, never reparses JSON per frame and runs no
  authoring-model validation in the rendering loop; later file edits cannot alter it.
  Immutable prepared data and mutable per-instance live state are owned separately
  under V07.
- One PreparedTrial artifact, including its manifest, is the compiler result and
  control payload; runtime indexes and timeline views derive from it. No parallel
  schedule grammar or duplicate manifest return. V02's complete settings and named
  conditions stay required; compiler execution remains implementation work.
- Retain the complete immutable prepared program/plan, including resolved seeds and
  group lineage, in the Visual Stimulus-owned `_stimulus_LOG.json` at trial start. E07 central
  metadata keeps a verified reference and compact summary; no separate recipe file or
  seed-only regeneration substitute. Actual presentation evidence follows E13.
- **Contracts:** [program validation](../../contracts/visual_stimulus/program-validation.md)
  (strict parsing, schema generation, compatibility, preparation;
  [schema primitives/parsing](../../contracts/visual_stimulus/program-validation.md));
  [canonical source/prepared schemas](../../contracts/visual_stimulus/stimulus-schema.md)
  (vocabulary, serialization, compiler obligations);
  [PreparedTrial artifact](../../contracts/visual_stimulus/prepared-plan.md).

<a id="v04"></a>
### V04 — Rendering stack and required stimulus scope

**Status:** Accepted · **Revision:** 11

- A focused Python renderer uses ModernGL (GPU rendering) and GLFW (windows/contexts)
  inside V01's rendering worker. Reuse graphics/decoding libraries for mechanisms;
  CephVR owns scientific stimulus behavior and lifecycle integration. No embedded
  second experiment framework.
- Required families: images/videos, static/drifting textures and true 3D arenas with
  virtual-observer movement and perspective, via image/video textures, procedural or
  image-based patterns and textured arena geometry in one rendering system with
  common trial timing, projection configuration and presentation evidence.
- Media profiles: PNG/TIFF images with defined 8/16-bit profiles, photographic JPEG,
  MP4/H.264, Matroska/FFV1 and static GLB 2.0 arenas under V17's unlit model.
  Validate actual content/features, preserve supported source precision and reject
  unsupported profiles explicitly; no silent conversion or discarded required
  appearance.
- One linear RGB working space, 32-bit floating-point composition and premultiplied
  alpha. Interpret source encodings explicitly, compose before output correction and
  quantize only at the declared presentation boundary. V23 supplies measured
  per-output correction; neither input precision nor float buffers establish
  projector precision or physically linear light in Uncalibrated mode.
- Display geometry/calibration stays separate from V02's authored content. V15 owns
  off-axis surface projection, V14 coordinate spaces, V20 pacing and V21 output
  range. Projector assignments and measured calibration values remain rig inputs.
- Images fit centrally within their authored 2D bounds before V15 projection:
  Contain preserves proportions with transparent margins, Cover preserves
  proportions with a centered crop, and Stretch fills the bounds. New GUI Images
  choose Contain; legacy omitted `fit` means Stretch. Texture tiling, Video playback
  and default Looming size animation keep their existing semantics.
- The existing Visual Stimulus implementation (GLB arenas, shader textures, observer/projection
  transforms) is a capability reference only; its code, defaults, timing/fallback
  policies and resource handling are not automatically accepted.
- Protect external sources: small assets live in immutable prepared memory/GPU
  resources; streamed sources keep protected read handles, covering transitive
  dependencies. Acquire protection before hashing/reading; fail Setup if it cannot be
  established. Applies with saving On or Off, lasts the prepared-resource lifetime and
  releases through existing cleanup. No asset-archive copy or periodic rehash during
  trials. V13 owns replay fingerprints and external preservation.
- Prepare execution data/resources under V01/V03; keep media decoding off the
  rendering thread. Video completion follows V09, timing misses V10, decode-ahead
  V11. GPU/resource ownership and presentation evidence must be explicit. Runtime
  performance and timing need full-workload rig evidence under SYS-002/E15.
- **Contracts:** [media profiles](../../contracts/visual_stimulus/media-profiles.md);
  [color pipeline](../../contracts/visual_stimulus/color-pipeline.md);
  [asset lifetime contract](../../contracts/visual_stimulus/asset-lifetime.md);
  [provider/native mappings](../../contracts/visual_stimulus/runtime-bindings.md) (decoder,
  importer, resource interfaces; code remains work).

<a id="v05"></a>
### V05 — Declarative parameter animation

**Status:** Accepted · **Revision:** 6

- Support constant values, built-in time functions (including ramps and periodic
  functions) and optional timestamped keyframe curves. The GUI edits the same typed
  definitions stored in V03 programs; no arbitrary user Python callbacks.
- Resolve and validate definitions before execution; the renderer evaluates them
  locally under V01. Functions and keyframes use time since the current resolved
  epoch occurrence began, restarting at zero for each occurrence, including repeats.
  This clock does not reset retained state or video playback under V07; explicit
  state trajectories still assign their declared fields.
- The [fixed parameter catalogue](../../contracts/visual_stimulus/parameter_catalogue.py) derives
  function/assignment units from the named parameter and chosen coordinate space.
  Condition columns/input channels keep explicit units; validate coefficients against
  their destinations. No repeated function-unit fields or generic unit algebra.
  Feedback mapping and coefficient evaluation follow V24.
- Keyframe curves stop at the epoch boundary; longer epochs hold the final keyframe
  value. Expose truncation in the prepared timeline.
- **Contracts:** [animation/playback contract](../../contracts/visual_stimulus/animation-and-playback.md);
  [typed function binding](../../contracts/visual_stimulus/stimulus-schema.md) (interpolation,
  units, integration).

<a id="v06"></a>
### V06 — Epoch durations and trial duration

**Status:** Accepted · **Revision:** 5

- Two modes: explicit epoch durations, with trial duration the sum of all expanded
  occurrences; or target-total, generating random epoch durations within a
  configured range that exactly match the requested total. Neither keeps a separately
  editable resolved trial duration.
- In target-total mode, fixed epochs keep their durations and consume part of the
  total; random-duration epochs share the remainder. Include baseline/pause epochs
  under E11. Epoch counts come from the program/groups; never add/remove epochs,
  trim, pad or alter repetitions to satisfy an infeasible total.
- Validate finite positive durations and ordered positive bounds, then check the
  remaining target against the summed lower/upper bounds. Reject infeasible requests
  with the allowed total range; with no random epochs, the fixed sum must match the
  target. Apply E05's minimum trial duration. Expose constrained cases with no
  duration variability rather than promising randomness.
- Visual Stimulus resolves durations at Setup using E07's seed rules and returns the complete
  epoch plan and total in typed plan evidence. The controller distributes the total
  and keeps E05 authority over common trial boundaries; every backend checks
  scheduled boundaries against its retained plan. E07's planned-epoch evidence
  includes each resolved duration; execution and reconnect never redraw them.
- The GUI shows the derived sum (explicit mode) or target, bounds, epoch count and
  feasibility (target-total mode), and the resolved schedule after Setup. Authored
  constraints and resolved values follow V03's source/plan distinction.
- Sample uniformly over feasible continuous duration combinations with the
  contract's fixed-sum method, then quantize to stored time units preserving bounds
  and total. Uniformity applies to complete combinations before quantization, not to
  independent epoch durations or resulting integer vectors.
- Each expanded random-duration occurrence, including repetitions of one epoch, gets
  its own component in the jointly sampled vector. Never reuse a template duration
  across repetitions or force distinct draws. Ordering follows V08; E07's
  retained-seed behavior across sessions is unchanged.
- The exact sum holds for the prepared software schedule at its defined clock
  representation, not for physical presentation of arbitrary durations. V10/V20 bind
  execution to that schedule; pacing never quantizes authored durations to display
  frames. Physical timing evidence retains E15's rig deferral.
- **Contracts:** [duration contract](../../contracts/visual_stimulus/durations.md) (sampler,
  representation, reproducibility, validation).

<a id="v07"></a>
### V07 — Stimulus state continuity and trial initialization

**Status:** Accepted · **Revision:** 5

- Retain live state automatically for the same compatible instance across adjacent
  epochs unless the program explicitly resets or sets it. Instance identity is
  distinct from shared asset identity. New/incompatible instances initialize from
  their declared starting state; the GUI shows that restart.
- Static and drifting presentations of a texture are one stimulus type with
  different motion parameters. Drifting-to-static keeps the phase, texture offset and
  orientation reached at the boundary and zeroes the relevant motion rates. Under
  V27, a fully static target also stops feedback increments and their rate bias.
  Resumed motion starts from retained state; zero programmed drift alone does not
  disable feedback.
- The rendering worker owns compact per-instance live state and reusable resources;
  the coordinator owns no live mutable state. Setup prepares compatibility checks and
  transition operations; the runtime scheduler applies them locally without
  searching previous epochs, copying images/state through the coordinator or
  recreating unchanged resources at boundaries.
- Runtime continuation reads retained state in place; prepared operations cannot
  substitute precomputed feedback-dependent state or turn parameter defaults into
  resets.
- Retained state follows actual resolved epoch order, including repetitions; V06
  duration sampling does not itself reset state.
- An instance omitted from the active scene within a trial pauses with its state
  retained; a compatible return resumes from it, subject to explicit
  resets/assignments. Absence accumulates no motion, playback or feedback; visual
  occlusion alone is not absence.
- Each trial initializes instances from its declared starting state, never from the
  previous trial's live state. E05's Idle presentation is independent and cannot
  advance trial state. Reuse compatible prepared resources without renderer restart
  or asset reload. Failure/recovery follow E06; retained resources do not authorize
  session resumption.
- **Contracts:** [continuity contract](../../contracts/visual_stimulus/state-continuity.md);
  [prepared-plan binding](../../contracts/visual_stimulus/prepared-plan.md) (transition
  descriptors, boundary compilation);
  [compatibility matrix and complete prepared artifact](../../contracts/visual_stimulus/stimulus-schema.md).

<a id="v08"></a>
### V08 — Group ordering and repetition

**Status:** Accepted · **Revision:** 3

- Each group uses authored order (default) or a fresh shuffle without replacement per
  repetition. Every selected condition row or child block appears exactly once per
  repetition; repetitions are a configured positive integer count. Equal adjacent
  conditions across repetition boundaries are valid.
- Shuffle at the group's chosen unit: condition rows instantiating its whole body, or
  complete immediate child blocks (authored child blocks when there is no condition
  table). Preserve each block's internal sequence, such as drift then hold; nested
  groups order themselves. No implicit trial-wide shuffle; E01's fixed session trial
  order is unchanged.
- Expand ordering at Setup with E07's retained seed and a versioned ordering stream
  separate from V06's duration sampler. A fresh shuffle may coincidentally repeat an
  earlier order. The prepared epoch plan retains the resolved occurrence order;
  rendering and reconnect never reshuffle it.
- V06 per-occurrence durations are generated after order expansion; timeline
  boundaries derive from their integer sums. V07 continuity follows actual neighbors
  in that order; a block/repetition boundary is not by itself a reset.
- V02's program view edits group bodies, conditions, repetition counts and ordering;
  its derived timeline shows group/repetition boundaries. Before Setup, random
  order/durations are unresolved; any illustration is labeled as an example, not the
  prepared plan.
- **Contracts:** [compiler binding](../../contracts/visual_stimulus/stimulus-schema.md) (bounded
  expansion, explicit condition substitution, independent versioned ordering RNG).

<a id="v09"></a>
### V09 — Video clip completion

**Status:** Accepted · **Revision:** 4

- Each video instance declares hold-final-frame or loop. The editor initializes new
  settings to hold; V02 requires the stored epoch block to state the choice, and
  runtime loading never uses the creation default to repair missing settings.
  Preserve explicit settings. Hold retains the final valid image; loop wraps to the
  beginning. Neither changes epoch duration or scene progression; V07 owns continuity
  and initialization.
- The renderer's video instance owns playback using prepared media data; decoding and
  loop preparation stay off the rendering thread (V04).
- Normal clip completion is distinct from missing/late data and decoder failure.
  Invalid media blocks readiness; confirmed decoding failures follow E06 and are
  never disguised as a final-frame hold. V10 governs overdue frames, V11
  preparation. Decoder/media interfaces are bound in runtime-bindings (V11); no
  seamless-loop guarantee.
- **Contracts:** [animation/playback contract](../../contracts/visual_stimulus/animation-and-playback.md)
  (endpoint, clock mechanics);
  [V02's authoring contract](../../contracts/visual_stimulus/program-authoring.md) (full source
  blocks).

<a id="v10"></a>
### V10 — Clock-preserving playback and nonfatal timing misses

**Status:** Accepted · **Revision:** 4

- Prepared epoch/trial boundaries stay authoritative through rendering delays. Video
  catches up to the source frame for its current scheduled media time, skipping
  overdue presentations with evidence rather than slowing. V07 pause/continuity and
  V09 clip-end behavior still apply.
- If the current video frame is temporarily unavailable, keep that instance's last
  valid image while its clock continues; log the held source frame, target media time
  and starvation interval, then catch up on recovery. Other scene state continues.
  Required initial content is prepared before Ready; never substitute another
  instance's image or treat starvation as clip completion.
- Record late/missed rendering, including complete epochs with no frame submission
  to a required output, and continue on the original schedule. Never extend, replay
  or insert epochs, or interrupt solely for timing misses. Preserve logical state
  transitions through elapsed epochs without claiming those states were displayed.
- Exception: E05's start-liveness limit applies; a required output with no returned
  trial presentation call by `T + 250 ms` interrupts.
- Detailed frame/epoch evidence follows E13; current status and administrative trial
  metadata keep compact timing-warning counts even with saving Off. Submission
  evidence is not proof of physical presentation.
- Confirmed renderer, output/GPU, decoder, enabled-recording and required-logging
  failures keep E06 classification and E08 health/progress handling: unavailable
  required presentation stops automatically; isolated scientific-recording loss opens
  the operator incident window. No timing-miss count disables those obligations or
  permits automatic recovery/session resumption.
- **Contracts:** [timing-miss contract](../../contracts/visual_stimulus/timing-misses.md)
  (accounting).

<a id="v11"></a>
### V11 — Bounded video decode-ahead preparation

**Status:** Accepted · **Revision:** 5

- PyAV/FFmpeg CPU decoding runs on a bounded set of background threads inside the
  rendering-worker process. Each container/decoder context has one serialized owner;
  instances keep independent playback positions. Bound codec-internal threads,
  application threads and frame memory. No separate decoding process or hardware
  decoding; native decoder failure can affect the renderer and follows E06/E08.
- Decode ahead off the render thread into memory-limited frame buffers; prepare
  required initial content before the applicable Ready gate. Validate assets and the
  prepared plan at Setup. No whole-video decoding or disk frame-cache conversion.
- The media subsystem owns bounded decoded storage and preparation; the renderer owns
  playback state and selection (V07/V09/V10). Bound aggregate prepared buffers,
  preserve frame ownership and prepare transitions without blocking decoding in the
  render loop.
- Temporary starvation follows V10. Engineering starting limits come from E14;
  runtime integration remains implementation work. Readiness is not proof of
  sustained throughput; full-workload verification remains under E15.
- **Contracts:** [decoder contract](../../contracts/visual_stimulus/decoder-ownership.md)
  (ownership, cancellation);
  [media preparation contract](../../contracts/visual_stimulus/media-preparation.md);
  [resource/provider contracts](../../contracts/visual_stimulus/runtime-bindings.md) (protected
  cursors, timestamp indexing, bounded preparation).

<a id="v12"></a>
### V12 — Visual Stimulus recording thread and overload

**Status:** Accepted · **Revision:** 10

- With E13 saving enabled, the rendering worker runs one recording thread and one
  FFmpeg/NVENC subprocess for the tiled review video; that thread also writes the
  detailed evidence file (V28). No separate recording process, pixel-slot transport
  or evidence bridge. The coordinator owns preparation/lifecycle aggregation.
- The GL thread tiles each render group's final output images into one composite and
  reads it back through bounded pixel buffers (`capture_slots`); the recording thread
  writes completed readbacks as raw frames to FFmpeg's stdin. The GL thread never
  waits on recording: one admission decision per render group; with no free slot,
  drop that group's video sample and record its identity, timing and drop
  disposition. Never evict an admitted sample, slow presentation or grow memory
  without bound. Submission evidence stays per output.
- Launch FFmpeg at ScheduleTrial acceptance, off the render thread, with final paths;
  feed no frames before T (as A08). Launch failure before T is a required failure
  before release; cancellation before T terminates it and deletes only its own file.
- Write one evidence line per render group (complete shared state, per-output
  submission observations, known capture dispositions) and separate update lines for
  late outcomes. Rendering never waits for encoding or disk sync. Evidence is bounded
  by `evidence_pending_bytes`; exhaustion is a required-logging failure.
- Video admission loss is nonfatal; frame/state evidence is not optional.
  Encoder/storage errors or progress failure follow E06/E08. Rendering misses (V10),
  recording omissions and physical presentation evidence stay distinct.
- An all-dropped review video may complete with a warning and no artifact only when
  final accounting, required evidence and successful cleanup are confirmed. Never
  fabricate real render/capture evidence; E13's identified duplicate padding is
  derived recording content, not a newly rendered or presented image.
- Prepare the recording thread before required Ready; finalize video and evidence
  before aggregate Finished, draining admitted in-interval samples and E13's
  identified in-interval padding (E11). With
  saving Off, no recording thread, capture or encoding runs. The thread shares the
  renderer's process and GIL; full-workload throughput is an E15 rig check.
- **Contracts:** [completion contract](../../contracts/visual_stimulus/video-completion.md);
  [recorded-output contract](../../contracts/visual_stimulus/recorded-outputs.md) (capture,
  admission, tile layout).

<a id="v13"></a>
### V13 — Trial replay from program and actual render evidence

**Status:** Accepted · **Revision:** 10

- Analysis software owns offline reconstruction and lossless export. The experiment
  backend records immutable program/resolved-plan information, matching asset
  fingerprints and actual render/presentation evidence needed by that software; it
  does not provide a replay runtime or export entry point. Review videos (E13) are
  lossy conveniences, not replay inputs.
- Retain the effective frame state consumed by rendering: closed-loop pose, actual
  video source frames/holds, per-output submission and composite recording outcomes.
  Reproduce the recorded sequence, not an ideal rerun of the plan. Required evidence
  follows V12; recording-video drops cannot drop replay state.
- Retain the complete prepared snapshot and replay manifest in `_stimulus_LOG.json`
  even with saving Off; logging failure enters E06 incident classification.
  Replay-relevant content fingerprints/provenance are a scoped exception to E04's
  filename-only asset logging. Reference external originals by fingerprint; never
  bundle/copy assets or create a managed archive. The operator preserves matching
  assets; replay rejects missing/mismatched content. V04's source protection covers
  preparation/execution; a Setup digest alone neither establishes immutability nor
  preserves originals after release.
- Validate recorded program, assets, replay-relevant provenance and effective state
  without original-output pixel fingerprints (sampled included). No per-frame pixel
  hashing or verification-only GPU readback. Reconstructed output is validated at
  input/state level only.
- Replay reads the complete evidence lines that exist (V28). Without the trial's
  closing record, label output "partial, up to render group N"; never present it as
  complete-trial replay or synthesize missing state. Full-trial replay requires a
  complete evidence file.
- Cache each asset's SHA-256 digest keyed by path, size and modification time in a
  local digest cache; re-hash only when one changes. Read protection (V04) is still
  acquired before any read or hash. The cache is a speed-up, not provenance: the
  manifest always records the digest.
- With E13 saving Off, setup logs alone do not guarantee actual-output replay.
  Lossless export does not prove original pixel/optical equality or physical
  presentation; replay compatibility still needs implementation checks.
- **Contracts:** [replay contract](../../contracts/visual_stimulus/replay.md) (snapshots,
  fingerprints/provenance, evidence ownership);
  [typed evidence and offline interfaces](../../contracts/visual_stimulus/evidence-format.md)
  (consumed state, resource compatibility, coverage, lossless PNG/index export).

<a id="v14"></a>
### V14 — Explicit stimulus coordinate spaces

**Status:** Accepted · **Revision:** 3

- 2D stimuli support physical-surface and observer-centered visual-angle
  coordinates. Each stimulus explicitly selects its space; the GUI shows matching
  units and the versioned program retains the selection. No implicit default or
  automatic reinterpretation.
- Physical-surface positions/sizes use millimetres and spatial frequency cycles/mm in
  an identified surface frame; visual-angle positions/sizes use degrees and
  cycles/degree relative to an identified observer frame. True 3D arenas keep
  explicit world coordinates and units.
- The renderer maps these through shared display/observer geometry and calibration,
  preserving meaning through V15's projection pipeline. Missing/incompatible mappings
  and unsupported singular crossings fail Setup. Never use a constant
  degrees-to-pixels scale across a wide field or treat angular as physical frequency.
- Measured calibration values and physical accuracy keep the hardware-input and
  rig-verification deferrals.
- **Contracts:** [stimulus-schema.md](../../contracts/visual_stimulus/stimulus-schema.md) (axes,
  angular parameterization, conversions, typed units, surface maps, angular-frame
  interpretation).

<a id="v15"></a>
### V15 — Four calibrated off-axis surface views

**Status:** Accepted · **Revision:** 11

- V01's single rendering worker renders four calibrated views for the rectangular
  rig's front, left, right and bottom screens by direct per-surface rendering with the
  generalized off-axis perspective method documented by PsychoPy (Kooima), on V04's
  ModernGL/GLFW stack; no cubemap intermediate.
- One shared scene/stimulus state per render update serves every face, with a common
  physical observer position and face-specific geometry. Shared patterns use common
  coordinates and phase; never restart them per view. The fixed calibrated physical
  observer position is resolved at Setup and kept for the session; tracking and
  virtual-arena movement cannot change it, and changing it requires fresh Setup.
  Virtual observer movement remains independently supported.
- Surface definitions are separate from output/viewport assignments; four surfaces
  need not mean four projectors. Apply calibrated output corrections after surface
  rendering; record final outputs under E13. Imported static calibration meshes map
  surfaces to outputs, with optional static masks and overlap weights, validated once
  and fixed for the session. No automatic calibration solver or runtime optical model.
- Per-output participation is independent of fixed rig geometry/calibration. Retain
  all four surfaces and stored mappings; prepare, render, present and record only
  enabled outputs and their mappings, in retained authored order. Never stretch,
  recenter, reassign coverage or renormalize calibration when outputs are disabled.
  Participation is fixed for prepared execution; changes require fresh preparation.
  At least one output and the selected pacing output must be enabled. V22
  independently gates the pulse target; reject invalid selections rather than
  moving either target silently.
- Physical screen planes need not coincide with tank walls. The GUI parallel-plane
  editor uses an explicit perpendicular distance from the fixed subject for each
  independent screen. Left/right screens have equal tank-wall offsets in that
  editor, so right distance is derived from tank width, subject position and left
  distance under G01. Side and Bottom front edges start at the Front screen plane;
  G01 owns the shared draft corner construction and ideal centered-projector diagram.
  The diagram does not change output corrections or introduce a runtime optical model.
  Corner-based backend geometry remains authoritative. Tank dimensions,
  subject position and derived ideal projector throw distance remain distinct.
  G01's measured raw-pixel bars derive X/Y scale and generate static affine mapping
  assets for GUI-owned profiles using physical screen/full-image ratios and existing
  offsets/inversions. Preserve imported warps, masks, weights and overlap ownership;
  this does not solve nonlinear optics or change runtime projection ownership.
- The display model covers physical corners/observer, explicit tolerances/clipping,
  output identities and viewport/profile references. Invalid/incomplete geometry or
  output mappings block preparation (E07). Geometric-profile content validation and
  runtime projection integration remain code work; measured values stay unset.
- Calibration data, measurements and verification wait for rig access; this design
  establishes neither simultaneous physical presentation nor measured optical
  accuracy.
- **Contracts:** [geometric correction](../../contracts/visual_stimulus/geometric-correction.md);
  [projection contract](../../contracts/visual_stimulus/projection.md) (geometry, matrix
  conventions, shared-state execution, Setup checks);
  [canonical display model/schema](../../contracts/visual_stimulus/worker-control.md);
  [geometric payload/schema](../../contracts/visual_stimulus/geometric-profile.schema.json);
  [validation binding](../../contracts/visual_stimulus/runtime-bindings.md).

<a id="v16"></a>
### V16 — Explicit simple arena movement boundaries

**Status:** Accepted · **Revision:** 4

- The trial protocol, not the arena asset, authors explicit simple allowed regions
  for virtual-observer movement, with optional nonnegative wall margins, or
  explicitly selects unrestricted movement. Embedded asset metadata never sets or
  overrides boundaries. No collision inference from visible triangles and no general
  physics engine.
- The rendering worker owns the constraint calculation and effective virtual pose,
  shared by all four views. Boundary contact is normal behavior, not a device
  failure. Slide at contact: remove movement into the wall, keep allowed tangential
  movement; no heading change, bounce, inertia or accumulated blocked displacement.
- Validate boundary geometry, units, margins and declared initial poses under E07;
  reject invalid or empty regions rather than resizing them or moving the start pose.
  Retained/reset instance state follows V07.
- Support planar x/y motion and yaw, with explicit fixed height, pitch and roll per
  epoch. The arena stays true 3D; continuous vertical/pitch/roll control is outside
  this first scope. Physical observer calibration stays fixed under V15.
- V13 retains the effective constrained pose and resolved boundary definition for
  replay; runtime implementation remains required.
- **Contracts:** [arena movement contract](../../contracts/visual_stimulus/arena-movement.md)
  (preparation, state, replay evidence);
  [typed planar boundary/solver declarations](../../contracts/visual_stimulus/stimulus-schema.md).

<a id="v17"></a>
### V17 — Unlit arena appearance

**Status:** Accepted · **Revision:** 4

- Render 3D arenas with unlit authored colors/textures, including baked shading. No
  runtime scene lighting, dynamic shadows, reflections or physically based shading.
  V04's true 3D geometry, perspective and depth occlusion remain required.
- The rendering worker applies one prepared material interpretation across V15's
  four views. Authored appearance stays separate from display calibration; V15 output
  color/brightness corrections still apply.
- V18 owns external arena preparation/import; material/color and asset bindings live
  in the arena-appearance, color-pipeline and media-profile contracts. Unlit
  rendering does not establish calibrated luminance or identical pixels across
  graphics environments.
- **Contracts:** [arena appearance contract](../../contracts/visual_stimulus/arena-appearance.md)
  (material preparation, feature validation, replay provenance).

<a id="v18"></a>
### V18 — Externally prepared arena assets

**Status:** Accepted · **Revision:** 2

- Arenas are generated beforehand in an external authoring workflow and loaded as
  prepared assets. CephVR loads, validates and renders them; no general parametric
  generation or modeling editor. A dedicated offline calibration exporter may use
  G01's saved tank and four screen dimensions to author a static GLB containing
  a physical screen grid, center cross and face name. It creates an asset for V01's
  manually controlled diagnostic presentation through V15, not a timed trial,
  alternate display owner or calibration solver.
- Resolve assets through E07's asset root and prepare geometry/material resources
  before Ready. Assets supply visual geometry and V17-compatible appearance; only
  V16's protocol settings define movement boundaries and margins.
- Reuse compatible prepared resources across trials; V13's external-original
  retention and fingerprints apply. Importer implementation remains code work.
- **Contracts:** [arena asset contract](../../contracts/visual_stimulus/arena-assets.md)
  (identity, protocol association, preparation);
  [media profiles](../../contracts/visual_stimulus/media-profiles.md) and
  [typed resource/provider bindings](../../contracts/visual_stimulus/runtime-bindings.md)
  (importer boundary).

<a id="v19"></a>
### V19 — Uniform Idle background

**Status:** Accepted · **Revision:** 4

- E05's Idle presentation uses a configurable uniform background color/brightness,
  black included, before the first trial, between trials, during finalization and
  after session termination. No numeric default is selected. Startup initialization
  carries the controller-selected asset root so protected display dependencies can
  be checked before Setup; missing required dependencies fail initialization.
- The resident rendering worker owns Idle output independently of trial instances,
  clearing full assigned outputs through the common output pipeline; calibration may
  use different device values for the same background. Never hold the preceding
  trial image or advance its state in Idle.
- Idle has no image/video/arena program or stimulus timeline. Its configuration is
  resolved under E07 and locked at Start; edits cannot mutate an active session.
  Trial recording boundaries stay under E11/E13. Color/precision follow the
  color-pipeline and output-precision contracts; Idle/trial boundaries follow the
  [continuity contract](../../contracts/visual_stimulus/state-continuity.md#trial-and-idle-boundaries).
- At startup, validate saved display/Idle settings through the existing controller
  configuration and renderer validation paths. Present Idle only when all required
  output settings, capabilities and correction resources are valid; otherwise leave
  outputs uninitialized and expose an actionable issue to GUI/headless clients
  without blocking configuration editing. Never guess output assignments, brightness
  or calibration mode.
- Startup display initialization is not Setup or Ready: no trial program, recording
  or stimulus seeds; fresh Setup stays mandatory. The canonical display model is
  independent of trial programs and separates startup Idle checks from full Setup
  requirements. E06 governs confirmed process/device failures and unsafe cleanup; no
  automatic restart.
- **Contracts:** [startup contract](../../contracts/visual_stimulus/startup.md) (ownership,
  evidence, cleanup, retry);
  [typed display/worker binding](../../contracts/visual_stimulus/worker-control.md) (startup
  requests/results, applied-output views).

<a id="v20"></a>
### V20 — Configurable projector presentation pacing

**Status:** Accepted · **Revision:** 7

- Default: VSync on the explicitly designated pacing projector, immediate
  presentation on the other outputs (current CephVR rig behavior). All-output VSync
  stays selectable for rig testing. Select the mode at Setup, preserve saved
  selections and lock at Start (E07); changing it needs fresh Setup, never automatic
  switching on a late frame.
- The rendering worker owns output contexts, swap settings and presentation. Both
  modes keep V15's single evaluated state for all four views and V10's schedule and
  timing-miss policy.
- Select 8 or 10 bits per RGB channel explicitly per physical output, with equal
  channel depths within an output. Validate the actual framebuffer against the
  request and adopted calibration profile before startup Idle/Ready; no automatic
  precision selection or downgrade. Float32 working color, review-video
  representation and physical signal precision stay distinct.
- Mixed mode requires an unambiguous configured pacing output and independent
  presentation control for outputs with different intervals; reject incompatible
  configurations rather than changing modes or guessing the pacing face.
- The pacing target is 60 Hz, configured with the pacing output identity only in
  the Visual Stimulus config file, not a GUI field. Adopt and validate it before
  startup Idle/Setup; no timing guarantee follows from the requested value alone.
- Pacing selection is independent of V22 pulse visibility/placement. Existing profiles
  without an explicit pacing ID retain their enabled photodiode target as a legacy
  fallback; pulse-disabled profiles require explicit pacing.
- VSync requests and sequential swaps do not establish simultaneous scanout or
  effective driver behavior. Immediate outputs may tear; one photodiode measures only
  its own output. Throughput, swap behavior and optical timing retain E15's rig
  deferral. V22 owns the photodiode marker strategy.
- **Contracts:** [presentation contract](../../contracts/visual_stimulus/presentation.md) (swap
  intervals, output identity, pacing, evidence);
  [output precision](../../contracts/visual_stimulus/output-precision.md) (quantization,
  evidence); [presentation/native binding](../../contracts/visual_stimulus/runtime-bindings.md)
  (GL-owner contexts, resource fences, stable output order).

<a id="v21"></a>
### V21 — Output-range clipping with evidence

**Status:** Accepted · **Revision:** 2

- Clamp finite color/brightness values outside the declared software output range,
  record the clipping and continue the original schedule. Never reject a valid
  program solely for a predictable finite excursion or auto-rescale its
  image/contrast; expose predictable clipping as a Setup warning.
- The renderer owns clipping and its evidence, with named alpha, linear-output and
  device-code boundaries in V04's color pipeline. Detailed per-output/frame records
  follow E13; compact warning/count summaries remain with saving Off. Recording
  overload cannot discard required clipping metadata.
- Scope: finite output-range excursions only. Invalid parameters, nonfinite numerical
  state, unsupported calibration/asset formats and GPU/component or required-logging
  failures keep E06/E07 handling. Clipping diagnostics describe the software
  pipeline, not measured projector light.
- **Contracts:** [output-range contract](../../contracts/visual_stimulus/output-range.md).

<a id="v22"></a>
### V22 — Photodiode frame alternation with landmarks

**Status:** Accepted · **Revision:** 3

- Pulse enablement and target/rectangle are operator settings independent of V20
  pacing. When disabled, retain placement but require neither target participation
  nor availability; draw no patch and emit no marker-state/submission evidence.
  When enabled, require an active target with a valid in-bounds patch at Setup.
- The enabled designated photodiode output shows a bright/dark frame-alternating patch with
  periodic distinctive markers. Detailed E13/V13 evidence associates intended states
  and marker positions with trial-relative output-frame identities.
- Each 60-submission cycle starts with six marker frames (three bright, then three
  dark), then alternates bright/dark for the other 54 frames. Restart at trial index
  zero, not at epoch changes; physical placement/levels remain unset.
- The renderer owns the patch and sequence, synchronized with that output's submitted
  image under V20 and independent of epoch changes and video frame holds.
- Match measured traces to the recorded intended sequence and available trial/timing
  evidence. A periodic landmark is not an absolute frame ID; missing cycles, repeated
  images and ambiguous matches stay explicit. Held marker states give no optical
  transition at their internal frame boundaries. Optical validation and signal
  thresholds wait for rig verification.
- **Contracts:** [photodiode contract](../../contracts/visual_stimulus/photodiode.md)
  (counter/recording ownership, interpretation).

<a id="v23"></a>
### V23 — Explicit photometric calibration mode

**Status:** Accepted · **Revision:** 3

- Brightness/gamma correction has calibrated and explicitly uncalibrated modes.
  Validate the explicit selection for V19 startup Idle and again at Setup; lock it at
  Start (E07). No implicit mode or automatic fallback. V15's projection geometry
  stays required.
- Calibrated mode requires valid, compatible measured profiles for all required
  outputs; missing, malformed or incompatible ones block Setup, never replaced by
  identity correction or a switch to uncalibrated mode.
- Uncalibrated mode omits measured photometric correction and is visibly labeled in
  configuration, current status and session/replay provenance. It does not bypass
  standard media/color interpretation, geometric calibration or V21 clipping, and
  cannot claim calibrated luminance/contrast.
- Use three measured 1D inverse-response lookup tables per output, one per RGB
  channel, validated at Setup and applied once after linear composition, including
  Idle and the photodiode patch. No assumed gamma equation, 3D color correction or
  silently generated identity profile.
- Runtime GPU integration remains local work; measurements and physical validation
  are rig-deferred. Per-channel correction does not establish matched chromaticity,
  spatial uniformity or optical accuracy across outputs.
- **Contracts:** [photometric contract](../../contracts/visual_stimulus/photometric-calibration.md)
  (versioned profile model/schema, interpolation, output compatibility, provenance).

<a id="v24"></a>
### V24 — Explicit feedback parameter mappings

**Status:** Accepted · **Revision:** 8

- A feedback binding is an input channel, target stimulus parameter, gain, offset
  and a declared direct-value, movement-integration or heading-relative planar
  operation: typed, unit-checked and prepared, never a matrix/processing graph or
  arbitrary callback. Source/target/gain units resolve through V05's finite
  catalogue at preparation; unsupported pairs fail validation. Gains may vary by
  trial/epoch through V03/V05; no numeric gain is selected.
- The renderer applies bindings to existing instance state using A06's ordered batch,
  with additive motion/conflicting-writer validation under V27, then shares one
  evaluated state across V15's views. Feedback stays out of the coordinator's
  per-frame path. No implicit filtering, prediction or smoothing.
- Respect E10's session mode, V07's initialization/pause-on-absence and V16's arena
  constraints. Units and source/target coordinate transformations are defined before
  execution; unsupported or ambiguous bindings block Setup (E07).
- T36 anatomical_body channels bind only by `heading_relative_planar_integration`
  (one ordered forward/sideways pair of equal unit, interval_average_rate, onto one
  arena's world x/y with independent longitudinal/lateral gains and no offset) or
  by movement integration to that arena's yaw (deg/s, deg per deg); direct world x/y binding fails Setup.
  `gain` scales longitudinal movement; optional `sideways_gain` scales lateral
  movement and falls back to `gain` for existing programs. A zero gain disables
  that axis; yaw retains its independent gain. Each result's yaw and midpoint-heading
  planar increments apply together, then V16.
- Process due epoch transitions first; eligible results use the current epoch's
  bindings and gains at the render update's logical time, whatever their source
  epoch. Never backdate state changes or discard results merely for crossing an epoch
  boundary. Trial, absence, reset-generation and V26 freshness exclusions apply.
- **Contracts:** [feedback contract](../../contracts/visual_stimulus/feedback.md) (preparation,
  application, evidence); [typed targets/units](../../contracts/visual_stimulus/stimulus-schema.md)
  and [result/reset messages](../../contracts/visual_stimulus/runtime-bindings.md) (independent
  of the later tracking estimator design).

<a id="v25"></a>
### V25 — Hold feedback-driven state during invalid input

**Status:** Accepted · **Revision:** 4

- During temporary invalid feedback or a reported tracking reset, stop adding
  feedback movement and retain the last direct feedback assignment. Keep applied
  movement; never extrapolate the last velocity. Programmed motion may still advance
  the same state (V27). Before usable feedback, only declared programmed motion
  evolves from the trial's initial state.
- Epoch timing, programmed animation, video playback and presentation continue.
  Resume on new usable results from A06's current reset generation; never
  reconstruct discarded movement or integrate across an invalid interval.
- The renderer owns hold/resume and records the gap and effective state under
  E13/V13.
- No invalid-feedback timeout or fallback animation. Required participant, device,
  progress and logging failures use E06/E08. V26 owns rejection and hold/resumption
  for valid-but-old results; it is not an invalid-input timeout.
- **Contracts:** [feedback contract](../../contracts/visual_stimulus/feedback.md) (evidence;
  invalid input vs no new input vs backend failure).

<a id="v26"></a>
### V26 — Feedback freshness guard with local hold

**Status:** Accepted · **Revision:** 8

- Before applying valid closed-loop feedback, measure its age from A05's source
  camera-frame host-receipt timestamp to the renderer's current host-monotonic time;
  reject it above the configured positive maximum. Never substitute device
  timestamps or result-arrival time. This guards software application, not physical
  display latency, and is separate from the 250 ms pre-processing guard.
- Log each stale result and hold its feedback contribution under V25. Continue the
  finite batch in order; resume on the next eligible fresh valid result, including
  one in the same delivery generation. Integrate only that result's explicit valid
  source interval; never catch up discarded movement. Keep applied state and
  independently programmed motion on the original schedule.
- Visual Stimulus never requests tracking resets or invalidates a generation solely for staleness.
  Tracking owns A06 producer resets and their generations; normal generation/trial
  gates apply. Required failures follow E06/E08.
- Resolve `[feedback] max_result_age_ms` (default **350 ms**, current CephVR's value;
  configurable, positive) at Setup into VisualStimulusFilePolicies.max_result_age_ns, locked for
  the session under E07/E14. Open-loop observation does not invoke this guard. The
  default is an engineering starting value; tuning and full-workload validation are
  rig-deferred.
- **Contracts:** [feedback contract](../../contracts/visual_stimulus/feedback.md) (age comparison,
  hold/resumption, evidence).

<a id="v27"></a>
### V27 — Additive motion on retained stimulus state

**Status:** Accepted · **Revision:** 2

- Programmed and eligible feedback motion add increments to the same retained
  phase/position/orientation state, owned by the renderer under V07. Changing
  gains/rates or losing feedback cannot subtract applied movement. No separate
  open-loop and feedback poses, combination graph or per-parameter mode selector.
- V25/V26 suppress new unusable feedback while programmed motion continues, including
  on the same target. A fully static target needs both contributions stopped,
  including any feedback rate bias; it keeps its reached state.
- Setup rejects competing continuous absolute assignments, or an absolute
  trajectory/direct feedback assignment combined with another writer of the same
  target. Explicit boundary reset/initialization stays permitted (V07) and precedes
  the next epoch's incremental motion. Compatible increments share units/frame; V24's
  heading-relative planar binding converts body-frame drive to world x/y first.
- Keep one compact state per target, reusing existing type handlers and V16 boundary
  handling. Never ignore the traversed path or add rotation matrices/quaternions
  componentwise.
- **Contracts:** [motion composition contract](../../contracts/visual_stimulus/motion-composition.md)
  (preparation, update order, constraints, state anchors, evidence).

<a id="v28"></a>
### V28 — Visual Stimulus evidence file and crash behavior

**Status:** Accepted · **Revision:** 4

- With E13 saving On, the recording thread writes `<prefix>_stimulus_frames.jsonl`:
  UTF-8 JSON Lines, one line per render group plus separate update lines for late
  outcomes (referencing the group ID), append-only, OS-synced every **1 s**
  (`record_sync_interval_s`) and at closure. Never rewrite earlier lines or make
  rendering wait for disk sync. A final closing line records complete accounting.
  Missing required evidence or failed writes/sync follows V12/E06.
- After a crash the file is valid up to its last complete line; readers discard an
  incomplete final line. No checksums, custom framing or recovery contract. Periodic
  sync does not guarantee pending lines survive.
- Replay of a file without its closing line is partial (V13) and cannot establish a
  completed trial, file closure or physical presentation.
- Crashed review videos without confirmed closure stay Unconfirmed; the fragmented
  MP4 plays up to its last complete fragment. No repair/remux tool. E13 live review
  recording stays enabled when selected.
- **Contracts:** [evidence format](../../contracts/visual_stimulus/evidence-format.md) (line
  schemas).

<a id="e13"></a>
### E13 — Save Visual Stimulus data

**Status:** Accepted · **Revision:** 19

- One **Save Visual Stimulus data** switch controls rendered Visual Stimulus video, associated frame logs and
  detailed Visual Stimulus state and presentation outputs. It defaults to On for a new
  configuration, preserves explicit saved On or Off values and locks at Start. Visual Stimulus
  output files follow E11's trial-only boundaries.
- Save one tiled review video per trial: every configured output's final renderer
  image, after configured renderer-applied corrections, in the fixed
  [tile layout](../../contracts/visual_stimulus/recorded-outputs.md#tiled-composite) retained in
  the recipe. Reuse those images; never rerender a recording viewpoint.
- One NVENC session in an FFmpeg subprocess encodes the composite from raw frames fed
  by V12's recording thread (never the render thread), as high-quality lossy video
  for posthoc visualization only, not a replay input. V13 owns exact per-output
  reconstruction and lossless export; V12 owns recording execution and overload.
- Use the existing validated FFmpeg output-token mechanism with one complete custom
  lossy argument list, not a named encoder-preset abstraction. Visual Stimulus owns inputs, paths,
  timing and MP4 lifecycle, reusing compatible parser/launch/cleanup mechanisms.
  Transfer/timing implementation remains unfinished; review recordings do not prove
  pixel identity or physical display.
- Explicitly configured review-video depth reduction is allowed with validated
  conversion and retained source/target representation evidence; silent negotiation
  is forbidden. Rendering and V13 reconstruction keep their original precision.
- The review video is constant-rate at the designated pacing output's nominal
  refresh rate in both presentation modes. Pad missing recording slots with
  explicitly identified duplicated composite images to preserve cadence/duration.
  V28 evidence must map every encoded frame to its real render group or padding,
  identifying duplicates for post hoc exclusion. Padding never fabricates state,
  render groups or presentation observations. Real timing (state-evaluation host
  time, per-output swap observations) stays in the evidence file; review timing
  never establishes optical onset. Slot assignment and leading-gap treatment still
  require contract formalization; current schemas/writers retain unpadded behavior
  until amended and implemented. Original resource bounds/deadlines stay in force.
- Review videos are fragmented MP4, kept in that format after normal closure; no
  conversion to ordinary MP4 or faststart pass at trial end. Normal encoder drain,
  finalization, sync and close stay required; V28's Unconfirmed crashed-video outcome
  and no-repair policy apply.
- When Off, detailed evidence and review video are not written. The complete
  `_stimulus_LOG.json` stays required (V03/V13); it preserves planned content, not
  actual closed-loop presentation history. Rendering/projection, camera recording
  and tracking are unchanged. Encoder input format/throughput retain the accepted rig
  deferral.
- **Contracts:** [Visual Stimulus encoding binding](../../contracts/visual_stimulus/encoding-options.md);
  [output reservation and naming](../../contracts/visual_stimulus/runtime-bindings.md)
  (`_stimulus_LOG.json`, `_stimulus_frames.jsonl` and `_stimulus.mp4` under E04).
