# Tracking backend

[Overview and decision register](../../architecture.md) ·
[System contracts](system-contracts.md)

Records input, pipeline/camera scope, pose and image-flow methods (T01–T11), result
delivery (A06) and compact recording scope (T14/T15). Complete initial estimator and
pipeline declarations are bound. Tracking implementation is the selected stage under
[ARCH-001](../../architecture.md#arch-001); progress and validation limits belong in
the [Tracking report](../../reports/tracking.md).

**Method scope:** under [T27](#t27), accepted methods are replaceable starting
implementations for experimentation: precise contracts for the selected method, not
permanent scientific conclusions. Shared lifecycle, source lineage, resource ownership
and recording guarantees apply across implementations. No record claims accuracy,
throughput or rig validation; [T12](#t12) states runtime and verification scope.

## Governing decisions

- [E10 — Modes and participants](experiment.md#e10): tracking enablement and
  dependencies.
- [A03 — Frame transport](acquisition.md#a03) and
  [A04 — Delivery/overload](acquisition.md#a04): input buffers, ordering, reset and loss
  rules.
- [A05 — Acquisition-to-Visual Stimulus delay](system-contracts.md#a05): timing evidence and
  boundaries.
- [A06 — Results to Visual Stimulus](#a06): result delivery and consumer behavior.

**Status:** water-flow and fin-flow pipelines, contour landmarks, estimator
settings/evidence, worker ports and pipeline registration are declared in the
[contract index](../../contracts/tracking/README.md). The owner has authorized runtime implementation under
[ARCH-001](../../architecture.md#arch-001). Visual Stimulus freshness/hold is
[V26](visual_stimulus.md#v26).

Configuration: [tracking_config.toml](../../config/backends/tracking_config.toml); fixed
policy: [tracking_policy.toml](../../contracts/policy/tracking_policy.toml).
Selection/validation binding: [tracking contracts](../../contracts/tracking/README.md).

## Decisions

<a id="t01"></a>
### T01 — Tracking image representation

**Status:** Accepted · **Revision:** 4

- Receive native camera pixels through A03's tracking ring; apply A01's common
  conversion and pixel-processing methods to private copies, preserving source effective
  bit depth.
- The selected method declares RGB or grayscale input; color-to-grayscale conversion is
  method-dependent. No preview display scaling or silent precision reduction to fit a
  method. Validate compatibility before Ready.
- Optional configured crop then isotropic downscale operates only on private
  representations. Retain acquired dimensions and the actual invertible pixel-centre
  transform; source annotations and published pose, geometry, flow positions/vectors
  and locomotion units remain in acquired-image coordinates. Normalize processed
  results before geometry/estimation, preserve source precision and reset temporal
  baselines after source/transform changes. Fixed resampling belongs in the method
  contract, not an operator algorithm menu.
- Representation preparation is separate from algorithm-specific normalization/features;
  A01 owns the shared native conversion provider/binding. The
  [method contract](../../contracts/tracking/method-bindings.md) binds ONNX
  normalization and NVIDIA OF's required 8-bit feature input; native/shared/recorded
  pixels keep source precision.

**Contracts:** [pixel-processing](../../contracts/acquisition/pixel-processing.md).

<a id="t02"></a>
### T02 — Named tracking pipelines with shared stages

**Status:** Accepted · **Revision:** 4

- Select one supported named pipeline per session. Each declares required stages, typed
  settings, supported method selections and output channels; reuse common stage
  implementations and execute only required stages.
- Pipeline structure belongs to the versioned implementation catalogue. Operators select
  a pipeline and compatible registered implementations/settings at its stage boundaries
  under T27; no arbitrary stage-graph editor or incompatible combinations. Unknown
  pipelines, methods or missing required settings fail validation before Ready under
  E07, which also locks the selection.
- T04 owns supported families, T05/T06 pose modes/methods, T07 image flow and T08/T09
  process layout and stage scheduling.

**Contracts:** [pipeline catalogue](../../contracts/tracking/pipeline-catalogue.md)
(concrete stages and connections).

<a id="t03"></a>
### T03 — One selected tracking camera per session

**Status:** Accepted · **Revision:** 1

- An enabled tracking backend consumes exactly one explicitly selected acquisition-owned
  camera per session for its pipeline. No concurrent camera pipelines or multi-camera
  fusion; other cameras may acquire/record independently.
- Select by stable camera role, resolved to the exact prepared device/source identity
  during Setup; never by discovery order, via a second SDK owner or by implicit source
  switching. Missing/disabled/incompatible input blocks Ready under E07/E10; changing it
  requires fresh Setup.
- Reuse A03/T01 input ownership/conversion and A04/A06 ordering/reset rules. Hardware
  identity and calibration are explicit installation/session inputs, not guessed
  defaults. T08/T09 own attachment/lifecycle bindings.

<a id="t04"></a>
### T04 — Water-flow and fin-flow pipeline options

**Status:** Accepted · **Revision:** 6

- Exactly two initial options, both using T07 NVIDIA Optical Flow: `water_flow` (visible
  water-tracer motion) and `fin_flow` (visible fin/tissue motion). Select one before
  Setup, locked under T02; no simultaneous execution. New configurations default to
  `water_flow`, as current CephVR does; saved choices win.
- Share frame preparation, source lineage, optical-flow execution, compatible pose and
  geometry stages, result delivery and recording. The option supplies its sampling
  region and replaceable estimator through T27; no duplicate workers, fin-edge profiles,
  wave propagation, correlation, phase estimation or wave analysis.
- Fin-flow reuses the ellipse-derived ROI/band and sectioning machinery, configured to
  sample visible fin motion rather than water, with region settings separate from
  water-flow's; no fin-edge/wave detector. Its estimator selects an angular wedge from
  the band, keeping T32's equal-arc section labels inside that support; water-flow
  support is unchanged.
- Fin-flow reuses T12's numerical proxy (signs, units, screening, support checks,
  smoothing) as one shared implementation behind the existing estimator boundary, with
  independent resolved fin settings and evidence identity. It is an experimental
  relative fin-motion control, not validated swimming intent; opposing motions can
  cancel.
- Prioritize the common frame pipeline and initial integrated testing; methods remain
  replaceable after testing CephVR2.0 against 1.0.

**Contracts:** [fin-flow binding](../../contracts/tracking/fin-flow.md) (crop).

<a id="t05"></a>
### T05 — Explicit manual or automatic pose mode

**Status:** Accepted · **Revision:** 3

- Before Setup, select fixed manual landmarks/analysis geometry or image-based automatic
  pose estimation; both are in scope and each pipeline validates its required geometry.
  New configurations default to manual; explicit saved selections are retained.
- Manual landmarks stay fixed for the session; deriving prepared geometry runs no
  automatic estimator. Automatic mode uses the selected method, with no silent fallback,
  mode switching or fabricated manual geometry on failure.
- Missing or incompatible manual geometry or automatic method/assets block Ready under
  E07; mode/settings are locked and need fresh Setup to change.
- T06 owns automatic method selection; T09 owns invalid/stale pose use. Adds no
  prediction/hold policy (A04/A06, V25/V26 apply) or live manual correction path.

<a id="t06"></a>
### T06 — Selectable keypoint-model or threshold/contour pose

**Status:** Accepted · **Revision:** 5

- Automatic pose supports trained keypoint-model and threshold/contour methods. Select
  exactly one before Setup, with separate method-specific settings/validation feeding
  the pipeline's common pose/geometry requirements. T05 owns manual mode.
- Never run both, vote/blend outputs or switch methods automatically. Missing
  model/settings, unsupported input or incompatible required landmarks block Ready under
  E07. New configurations default to threshold/contour, as current CephVR does; it still
  requires the rig-specific T18 threshold/polarity and contour limits.
- T10/T11 own common landmarks and model deployment runtime; threshold/contour
  scoring/quality settings follow the
  [method contract](../../contracts/tracking/method-bindings.md).
- The initial contour implementation takes a search axis from foreground-mask principal
  moments, signed by T20's references, then observed directional contour extremes as the
  three T21 landmark candidates. No extra setup search regions, ellipse-derived points
  or curvature detector. Invalid/ambiguous axes or degenerate triplets yield invalid
  pose under T09.

**Contracts:** [contour binding](../../contracts/tracking/contour-landmarks.md) (exact
selection/ties and quality; anatomical accuracy untested).

<a id="t07"></a>
### T07 — NVIDIA Optical Flow with need-driven extensions

**Status:** Accepted · **Revision:** 7

- NVIDIA Optical Flow is the initial image-flow method when the pipeline requires flow:
  fixed policy under E14, not a single-option operator setting. Implement only the
  NVIDIA backend, as the owner requested; no DIS, PIV or other provider
  implementations/dependencies.
- Reuse two GPU input buffers; upload only each new admitted GRAYSCALE8 image. The
  initial adapter returns the native SHORT2 grid to bounded host storage once per pair,
  plus optional cost when enabled. Decode/reduce on CPU without GPU float expansion or
  early sample aggregation; keep explicit completion and lease ownership.
- Add a flow method only for a documented compatibility, accuracy or performance need,
  binding its typed settings, input/output semantics and validation before cataloguing
  it. A small prepare/compute/reset/close interface lets a provider be added without
  rewriting the pipeline; no prebuilt plugin framework or unspecified alternatives. T27
  extends this to other tracking methods.
- Setup checks actual device/driver/provider capability, supported input and required
  resources; unsupported or unavailable NVIDIA flow blocks Ready, with no silent method
  or hardware switch. Required runtime failures retain E06.
- T01 owns native precision and declared method-specific preprocessing; T12/T04 own the
  downstream estimator.

**Contracts:**
[CUDA method binding](../../contracts/tracking/method-bindings.md#nvidia-of-cuda-adapter)
(internal: capability checks, byte conversion, flow units, baseline/pair operations,
completed-buffer identity/layout/availability).

<a id="t08"></a>
### T08 — One tracking process with internal workers

**Status:** Accepted · **Revision:** 9

- One Python tracking backend process owns control, preparation, source attachments,
  estimator state and result publication, with internal worker threads; no separate
  coordinator or per-stage processes. Model/native resources have explicit thread
  ownership, independent of controller/health handling.
- The first implementation runs preparation, geometry construction/caching, locomotion
  estimation and filtering on CPU with shared conversion code, NumPy and OpenCV. One
  movement worker runs preparation, ordered flow-pair evaluation, estimation, sectioning
  and flow-dependent work; T09's pose worker builds exact automatic geometry and
  publishes an immutable pose/geometry pair; manual geometry is prepared at Setup. No
  extra preparation-stage queue or automatic CPU/GPU placement switch.
- Use bounded private-buffer leases, reusable representations and native-grid host
  readback; cache geometry for unchanged eligible pose/settings. Optional preview and
  recording never retain control-critical images or block movement on UI/disk work.
  Later GPU estimation or extra stage concurrency needs a demonstrated need and an
  explicit binding update.
- Reuse E08 launch registration, loopback lifecycle control, health monitoring, Windows
  containment and shared native helpers. Attach to A03's selected-camera input and
  publish A06's direct result stream; scientific data does not cross the controller.
  Closed-loop Setup carries the exact registered renderer identity through the
  controller-owned preparation handoff; missing or ambiguous identity fails Setup.
- Configuration diagnostics reuse this process with a separate diagnostic identity,
  exact accepted acquisition preview/consumer binding and independently selected
  stage mask. Begin freezes a bounded typed diagnostic draft against the accepted
  configuration revision; it does not require experiment Tracking participation or
  change E07 configuration/history. The controller supplies the accepted asset root
  and file policies. Settings or mask changes require confirmed Close and a fresh Begin.
  No experiment
  recording, trial context or Visual Stimulus feedback is produced. Use acquisition
  ordered input and a bounded latest-only direct viewer path; the controller carries
  coalesced status/timing only. Authority/source loss closes diagnostic ownership
  under original deadlines; Setup requires confirmed closure. Viewer detachment
  alone does not claim processing stopped. T02 experiment stages remain mandatory.
- Resolve diagnostic stage availability before validating or preparing runnable
  stage inputs, reusing the owning typed components without whole-experiment
  validation. Missing/disabled prerequisites make dependent outputs unavailable;
  malformed consumed annotations, source-dimension mismatch or invalid selected
  method settings reject explicitly. Independent flow requires no pose; an empty
  mask provides image/preprocessing-only annotation with no native algorithm/GPU
  preparation. Never invent missing scientific inputs. Common source/crop/downscale
  bounds remain mandatory; T20 requires valid camera scale for runnable locomotion.
  Other diagnostic stages can run without scale.
- Control/health responsiveness is distinct from computation progress. Blocking native
  calls run outside control handling; cancellation requests do not prove completion or
  release. Retain resources until consumers finish, report blocked cleanup under E06,
  and never treat daemon-thread exit as finalization evidence.
- First required activity is completed frame evaluation, including baseline/invalid
  evaluation; it need not wait for scientifically valid movement. No source interval or
  stale completion crosses trials. Stop separates admission cutoff, confirmed
  computation stop and output closure; retired work never becomes a newly published
  result.

**Contracts:**
[execution binding](../../contracts/tracking/execution.md#optimized-frame-path)
(lifetime, cache, dispatch, publication);
[execution](../../contracts/tracking/execution.md) and
[lifecycle](../../contracts/tracking/lifecycle.md) (stage/resource handoff, typed setup
attachments);
[stop contract](../../contracts/tracking/lifecycle.md#producer-cutoff-late-work-and-finalization).

<a id="t09"></a>
### T09 — Independent automatic pose and ordered movement

**Status:** Accepted · **Revision:** 4

- Automatic pose runs independently of ordered movement: use the latest completed
  eligible pose, never wait for matching-frame inference. A bounded latest pending image
  feeds pose; skipping superseded pose images discards no movement frame pairs and
  leaves A04/A06 ordering/reset policies unchanged.
- The pose worker completes candidate selection and exact geometry together, publishing
  one immutable pair into bounded history. Reuse geometry only for that exact
  observation/settings/layout; no tolerance approximation or extra worker.
- At movement evaluation, select the newest completed pair from the same
  trial/source/preparation whose source frame is no later than the movement frame, and
  check its source host-receipt age against an explicit session-locked maximum. Retain
  its identity, source frame, age/check time and disposition with the result.
- Pose history survives delivery and movement-processing resets and clears on
  trial/source/preparation change. A reset never relaxes age, invalidity or source-order
  checks.
- Missing, invalid or over-age pose invalidates dependent movement. Never search past a
  newer invalid pose for an older valid one, use future-frame pose, predict geometry or
  silently switch method. Recovery cannot bridge an invalid/discarded movement interval;
  A06 and V25/V26 own baseline and Visual Stimulus hold.
- Manual mode uses T05's fixed prepared geometry with no pose worker or pose-age
  requirement. Automatic mode needs valid age/history bounds at Setup; E14 configurable
  defaults are history capacity 8 and maximum pose age 500 ms (current CephVR's 30-frame
  limit), to be tuned on the rig.

**Contracts:** [execution binding](../../contracts/tracking/execution.md) (bounded
handoff and comparison mechanics; no measured latency asserted).

<a id="t10"></a>
### T10 — Shared three-landmark pose

**Status:** Accepted · **Revision:** 4

- The intended animal is a head-fixed cuttlefish or squid with a moving mantle. Head
  fixation implies no fixed mantle orientation, rigid mantle shape, fixed mantle
  landmark coordinates, rig coordinates or motion limits. T20 supplies the setup
  directional reference; T06 binds contour-to-landmark extraction.
- Manual, keypoint-model and threshold/contour pose supply the same named tip, left-base
  and right-base payload fields; [T21](#t21) owns their anatomical meanings, [T22](#t22)
  live geometry updates. One shared geometry function derives orientation and analysis
  regions; no method-specific geometry conventions, and optional contours are not a
  required common payload.
- Coordinates use the selected acquisition image's reference frame, with declared
  transforms back from method crops/resizes. Invalid/missing or degenerate required
  landmarks invalidate pose under T09; never fabricate coordinates or swap labels.
- Extra contours/keypoints may remain method-specific diagnostics. Region construction
  and body-axis interpretation are declared in their contracts; numeric quality tuning
  remains. Three landmarks alone do not validate locomotion accuracy.

**Contracts:** [pose contract](../../contracts/tracking/pose.md) (basic field/coordinate
bindings).

<a id="t11"></a>
### T11 — ONNX pose models with ONNX Runtime CUDA

**Status:** Accepted · **Revision:** 4

- The initial keypoint implementation deploys pre-exported ONNX models through ONNX
  Runtime's NVIDIA CUDA provider; no direct PyTorch/Ultralytics or TensorRT
  implementation. The shared pose boundary must not require ONNX-specific tensors,
  sessions or settings.
- Export/train outside CephVR. Setup validates the model, declared preprocessing/output
  mapping, actual provider/device compatibility and required resources before Ready. The
  prepared session and buffers persist across trials under T08/T09; no per-trial model
  loading, exporting or provider selection in the movement path.
- The pose worker prepares inputs on CPU in reused tensors, uploads only admitted pose
  jobs, reuses the prepared CUDA session and bound buffers, and returns the bounded
  candidate tensor for CPU selection. No extra GPU preprocessing framework.
- Missing/incompatible assets or unavailable CUDA block preparation; never silently fall
  back to CPU-only inference. Required runtime failures follow E06. Detailed
  asset/runtime/provider identity goes in tracking's prepared evidence and saved
  scientific header; E04 central metadata keeps its filename-only asset rule and
  resolved setup settings.
- This selects deployment, not architecture/weights, training workflow or accuracy.

**Contracts:** [pose contract](../../contracts/tracking/pose.md) (adapter/schema work).

<a id="t12"></a>
### T12 — Water-flow locomotion estimator

**Status:** Accepted · **Revision:** 8

- T39–T45 select the initial tracer-water proxy: local consistency screening, linear
  area-weighted translation, a centred flow moment, required support in every section
  and exponential command smoothing. Neither the old sector fit nor its momentum-flux
  implementation is adopted.
- Initial estimator declarations and catalogue integration are bound, with T04 fin-flow
  reuse and T06 contour extraction. Runtime construction remains local implementation
  work; numeric rig tuning and scientific/runtime verification retain E15.

**Contracts:** [water-flow proxy](../../contracts/tracking/water-flow-proxy.md)
(response, units, support, filtering);
[local screening](../../contracts/tracking/flow-quality.md) (W1A/W2A);
[catalogue](../../contracts/tracking/pipeline-catalogue.md) (complete settings, compact
evidence, worker connections).

<a id="t13"></a>
### T13 — Fin-wave estimator

**Status:** Superseded · **Revision:** 5

Fin-undulation method choices were withdrawn at the owner's request; [T04](#t04) owns
the two optical-flow options and this ID imposes no implementation requirement.

<a id="t14"></a>
### T14 — Independent tracking-data saving

**Status:** Accepted · **Revision:** 3

- A session-level Save tracking data switch (GUI label owned by [G01](gui.md#g01)), independent of
  camera recording and Save Visual Stimulus data. Enabling it requires Tracking under
  E10; disabling it still permits required closed-loop feedback. New-configuration default On; preserve an explicit saved
  Off under E07. Disabled tracking creates no tracking outputs.
- With saving Off, enabled tracking keeps observation/feedback and administrative
  error/lifecycle obligations, without detailed scientific history. E07 Setup/Start
  locking applies; no mid-session toggle.
- With saving On, the tracking scientific output is required under E10; recording
  failures follow E06. Use E04 reservations/paths and E11 trial boundaries.

<a id="t15"></a>
### T15 — Compact tracking scientific records

**Status:** Accepted · **Revision:** 4

- With T14 saving On, retain compact pose observations, movement results and their
  quality evidence, source-frame/timing links, invalidity, reset and tracking-owned
  discard accounting: all generated observations/results, not only valid or Visual Stimulus-applied
  ones. Visual Stimulus keeps its own application/presentation evidence under V13/A05.
- Dense flow fields, intermediate image masks and diagnostic image histories are
  excluded; the owner confirmed no dense-flow saving for now. No dense-flow writer,
  payload or save switch unless the owner later requests that scope.
- T19 owns durable recording and its contract the layout and writer boundary;
  estimator-specific fields follow T12/T04. Compact records do not promise exact
  reconstruction of unsaved intermediate computations.
- Store FeedbackResult as a decoded standard Protobuf JSON object using its owning
  descriptor: lowerCamelCase names, int64/uint64 decimal strings, enum names and
  preserved optional-field presence. Reject unknown/nonfinite values and
  noncanonical representations. Registered stage evidence is a nested JSON object,
  not base64 or escaped JSON text; no second scientific schema or dense payload.

<a id="t16"></a>
### T16 — Fixed automatic-pose search rectangle

**Status:** Accepted · **Revision:** 2

- Automatic pose uses one configured rectangular search area, fixed for the session and
  authored in Configuration against the selected camera's manual preview; it may cover
  the entire image. Setup validates it against the prepared source without interactive
  editing. E07 locking; no following crop, adaptive expansion or automatic whole-image
  retry.
- Both automatic methods use this convention, converting crop/resize coordinates back to
  T10's acquired-image coordinates. It does not change acquisition ownership/ROI, frame
  delivery or flow-analysis regions. Manual pose runs no automatic search.
- Missing/out-of-range geometry blocks preparation; no qualifying detection follows
  T09's invalid-pose response.

**Contracts:** [pose contract](../../contracts/tracking/pose.md) (rectangle fields,
source-layout validation); numerical coordinates remain unset.

<a id="t17"></a>
### T17 — Highest-scoring eligible pose candidate

**Status:** Accepted · **Revision:** 2

- After the method's candidate-quality checks within T16's search area, choose the
  highest-scoring eligible candidate per observation. Multiple qualifying candidates do
  not invalidate it; with none, report invalid pose under T09 without relaxing checks.
- Each method declares a finite, higher-is-better score and quality checks; compare only
  candidates from one method/observation. No cross-method blending, previous-target
  preference, identity tracker or extra hysteresis.
- Record candidate count, selected score and deterministic tie-breaking evidence in T15
  observations. Scores are method-specific, not calibrated probabilities or proof of
  identity continuity.

**Contracts:** [method contract](../../contracts/tracking/method-bindings.md) (model row
scores, contour foreground-area ranking).

<a id="t18"></a>
### T18 — Fixed brightness threshold for contour pose

**Status:** Accepted · **Revision:** 4

- Threshold/contour pose separates foreground with one configured brightness threshold
  and foreground polarity, fixed for the session and applied within T16's rectangle to
  T01's declared grayscale representation at source precision. No adaptive threshold,
  background-reference subtraction or automatic adjustment.
- Threshold and polarity are explicit method settings, not guessed defaults, validated
  before Ready and locked under E07. Missing/incompatible settings block preparation; no
  eligible pose follows T09. Keypoint-model/manual modes never execute or implicitly
  fall back to it. T06 binds contour-to-landmark interpretation.

**Contracts:** [pose contract](../../contracts/tracking/pose.md) (intensity/field
bindings); [method contract](../../contracts/tracking/method-bindings.md) (component
extraction, quality fields, scoring).

<a id="t19"></a>
### T19 — Tracking record file

**Status:** Accepted · **Revision:** 5

- With T14 saving On, append T15 records to `<prefix>_tracking.jsonl`: UTF-8 JSON Lines,
  one line per pose observation, movement result or reset, append-only, OS-synced every
  `sync_interval_s` and at closure. A bounded tracking-owned writer thread runs outside
  movement computation; feedback delivery never waits for disk. No checksums, envelopes
  or dependency on Visual Stimulus's former framing code.
- Header schema version 3 identifies decoded feedback/stage objects with T38's
  calibrated output units and pipeline version 2. Retain pixel-space stage evidence. Keep
  admitted payloads immutable and charge expanded serialization workspace to the
  existing recording byte limit. The file contains objects even when the internal
  immutable representation is text. Retain exact prepared-method/settings header
  text and its digest. Reject unsupported historical schemas; never rewrite old data.
- Admission, write/sync/progress or closure failure of required records follows E06/E10.
  A06's lossy Visual Stimulus delivery queue is separate and never authorizes dropping scientific
  records. Finalization drains admitted work, syncs and closes before reporting output
  closure; cleanup stays under shared deadlines.
- After a crash the file is valid up to its last complete line; readers discard an
  incomplete final line. Readable lines prove neither closure nor complete trial
  coverage. No recovery tool and no live or between-trial reread.
- Recording limits and sync/progress intervals are file-only E14 settings delivered
  through TrackingFilePolicies, never editable TrackingSettings or trial overrides.

**Contracts:** [recording contract](../../contracts/tracking/recording.md) (line
schemas).

<a id="t20"></a>
### T20 — Four labelled subject-reference points in Configuration

**Status:** Accepted · **Revision:** 8

- The operator supplies anterior, posterior, medial-left and medial-right subject
  coordinates in Configuration on the selected camera's manual preview; Setup validates
  them against the prepared source and accepts no interactive edits. Labels are
  anatomical: anterior toward the head, posterior toward the mantle tip,
  medial-left/right toward the animal's own sides. No guessed coordinates, screen-left
  sorting or extra baseline angle.
- Manual landmarks, these points, the T16 rectangle and T25 geometry adjustments use the
  same Configuration preview/overlay workflow, converting display to acquired-image
  coordinates. Camera/layout changes require revalidation, not silent reuse. Headless
  clients supply the same typed values before Setup, without GUI interaction.
- Enabled experiment Tracking and locomotion diagnostics require two distinct
  camera-image distance endpoints, positive known millimetres and exact source
  dimensions. Validate the derived acquired-image px/mm against the endpoints and
  prepared source, independently of crop/downscale. T38 uses it for linear outputs;
  it does not establish physical swimming velocity. Earlier diagnostic stages may
  run without scale. Source changes require revalidation, never guessed scale.
- The points set the initial anatomical direction and lateral reference for pose
  interpretation, locked under E07 and retained with tracking setup metadata. They are a
  setup reference, not a claim that the moving mantle stays there, a continuous
  head/pivot measurement, or an exact head centre, pivot, widest-body cross-section or
  mantle-base endpoint.
- T06's contour binding and manual landmarks map separately to T10's triplet; never
  equate side references with base landmarks, replace live model output or impose a
  rigid shape.

**Contracts:** [pose contract](../../contracts/tracking/pose.md) (four-point payload);
T16 bounds and the [pipeline catalogue](../../contracts/tracking/pipeline-catalogue.md)
bind separate consumers without changing these labels.

<a id="t21"></a>
### T21 — Anatomical mantle-tip landmarks

**Status:** Accepted · **Revision:** 2

- The live triplet is the posterior mantle tip and left and right anterior mantle tips,
  left/right being the animal's own sides. Preserve labels through camera/display
  transforms and across manual/model/contour methods.
- Payload keys tip, left_base and right_base map in that order via the
  [pose contract](../../contracts/tracking/pose.md); UI/model annotation uses the
  anatomical names. No widest-section substitution, screen-side sorting or
  ellipse-derived virtual landmarks.
- T20's setup points are directional references, not these live coordinates. T06's
  contour heuristic picks posterior and anterior-side boundary extremes as candidates
  without redefining the labels; a geometrically valid extreme can still be anatomically
  wrong.

<a id="t22"></a>
### T22 — Pose-derived position, orientation and dimensions

**Status:** Accepted · **Revision:** 2

- In automatic mode, update position, orientation, posterior-to-anterior-midpoint span
  and anterior-tip separation together from each eligible valid T21 triplet (one
  observation under T09); never mix observations or hold dimensions fixed while updating
  the rest.
- T09 handles missing/invalid/stale pose; no last-valid fallback, invented geometry or
  implicit smoothing. T05 manual mode stays fixed.
- These are image-space landmark measurements, not body reconstruction, physical length
  calibration or head-fixation pivot identification; T23–T45/T04 analysis bindings do
  not alter them.

<a id="t23"></a>
### T23 — Three-landmark reference ellipse

**Status:** Accepted · **Revision:** 2

- Construct a 2D ellipse in the acquired-image plane from T21's three mantle tips,
  similar to the existing three-point geometry; no 3D ellipsoid/depth estimate.
- The same geometry function serves manual and automatic modes. The ellipse is derived
  from measured landmarks without replacing them by virtual endpoints; no hand-drawn
  outline or live full-outline segmentation.
- T25 binds the initial proportional construction and default; three points alone
  neither define a general ellipse nor prove anatomical fit. Replacement geometry keeps
  explicit landmark/region contracts.

<a id="t24"></a>
### T24 — Analysis-region distances relative to landmark dimensions

**Status:** Accepted · **Revision:** 5

- Directional longitudinal distances are fractions of T22's current
  posterior-to-anterior-midpoint span; directional lateral distances are fractions of
  current anterior-tip separation, from the same observation as the reference ellipse
  (manual mode: prepared fixed dimensions).
- T29's uniform-distance band needs one scalar pixel distance in all directions, not
  separate longitudinal/lateral offsets or distance after anisotropic body
  normalization; T30 selects anterior-tip separation as that reference.
- Fractions resolve through the common geometry function and are session-locked under
  E07; T22 updates only their pixel extent. They are neither millimetres nor velocity
  calibration. T26 owns clipping; numeric margins need operator input; T31 selects
  full-band geometry, whose estimator-specific use is separate.

<a id="t25"></a>
### T25 — Adjustable initial ellipse proportion

**Status:** Accepted · **Revision:** 2

- The initial ellipse follows the existing proportional construction: headward axis from
  posterior tip to anterior-tip midpoint, longitudinal diameter span/front_fraction,
  lateral diameter equal to anterior-tip separation. The posterior landmark lies at the
  posterior longitudinal endpoint.
- front_fraction is an operator setting, initial default 0.60; explicit saved values
  win. Validate 0 < front_fraction <= 1 and finite bounded resulting geometry during
  preparation/use; no artificial minimum-size clamps manufacture valid geometry.
- Adjust it on the Configuration preview overlay before Setup; Setup only validates it
  and E07 locks the prepared/session settings.
- It controls a reference shape, not a measured body length or exact fit through all
  three points.

<a id="t26"></a>
### T26 — Clipped regions with logged coverage

**Status:** Accepted · **Revision:** 2

- Intersect requested sampling regions with the acquired image; log requested/visible
  coverage and clipped fraction per section with the affected result. No separate
  visibility threshold: T44's per-section gate divides accepted flow area by intended,
  pre-clip section area, so clipped pixels count as missing.
- Never infer movement from absent pixels or renormalize missing coverage. Clipping
  alone does not interrupt the session. T16 search-area validation and contour candidate
  completeness are separate.

<a id="t27"></a>
### T27 — Replaceable tracking-stage implementations

**Status:** Accepted · **Revision:** 3

- Tracking methods, algorithms and implementation bindings are initial working choices,
  open to replacement as the owner tests alternatives. Stable stage boundaries: image
  preparation, pose, geometry/regions, image flow, locomotion and filtering/mapping.
  Pipelines select compatible stages; T08/T09 keep execution ownership.
- A small explicit registry holds implementation IDs, versions, typed setting schemas,
  input/output contracts and optional compact evidence schemas. New implementations
  register against these without controller, lifecycle or recorder changes.
  Provider-native details stay in adapters; no method must accept ONNX settings or
  NVIDIA buffers.
- Select installed compatible implementations before Setup; validate, resolve stage
  objects once and record exact identities/settings. E07 locking: no live replacement,
  automatic fallback or mixed-method trial history. Requires no extra backend process,
  arbitrary executable configuration or general plugin-discovery/graph framework.
- An experimental implementation preserving stage and shared contracts needs typed
  registration, compatibility checks and a versioned catalogue/policy update, not a new
  architectural decision solely because the algorithm differs. Changes to scientific
  meaning, source/time/units, shared guarantees or supported stage contracts must be
  explicit and versioned; never relabel incompatible outputs as compatible.
- Initial implementations keep their method-specific decisions/settings; no hypothetical
  alternatives now, and T07's NVIDIA-only scope stands. The
  [catalogue](../../contracts/tracking/pipeline-catalogue.md) binds both initial T12/T04
  estimators; declaration registration does not make a missing runtime implementation
  Ready.

**Contracts:** [stage contract](../../contracts/tracking/stages.md) (concrete boundary,
extension workflow).

<a id="t28"></a>
### T28 — Tapered-superellipse sampling outline

**Status:** Accepted · **Revision:** 3

- Derive the initial sampling outline from T25's reference geometry with
  operator-adjustable taper and squareness: an approximate body shape, not a measured
  anatomical contour. T23's ellipse and the landmarks keep their meaning.
- Same construction in manual and automatic modes under T22. Resolve shape settings
  before Setup/Start locking and retain them with the registered geometry
  implementation. Defaults are current CephVR's taper 0.4 and squareness 3.5; saved
  values win. No live silhouette segmentation or iterative shape fitting.
- Implement as a small NumPy/OpenCV geometry module. T29 owns the surrounding band;
  T31/T32 and T04 own its water/fin analysis regions.

**Contracts:** [geometry contract](../../contracts/tracking/geometry.md) (shape
formulas, rasterization, validation).

<a id="t29"></a>
### T29 — Uniform-distance sampling band

**Status:** Accepted · **Revision:** 4

- Build the band by Euclidean distance from T28's outline in acquired-image coordinates,
  with explicit inner clearance and outer extent and uniform offsets at image-pixel
  resolution; no enlarged ellipse axes or anisotropically normalized distances.
- Use the geometry contract's OpenCV precise distance transform of the rasterized body
  mask: distance from the approximate shape, not anatomical clearance or millimetres.
  T24 keeps relative sizing; T30 owns the scalar size reference.
- Offsets default to 0.1 (inner) and 0.75 (outer) of anterior-tip separation, starting
  values to tune on the rig.
- Build intended support before clipping; T26 owns per-region coverage. Reuse geometry
  only for the same eligible pose/settings/source geometry, without implicit smoothing
  or last-valid fallback. Masks/distances stay transient (T15). T31 selects full-band
  output; T12/T04 bind estimator use via the pipeline catalogue.

<a id="t30"></a>
### T30 — Band scale and ROI dimension meanings

**Status:** Accepted · **Revision:** 2

- Scale both band offsets by the left/right anterior mantle-tip separation of the same
  eligible triplet, not the longitudinal span, geometric mean or extrapolated ellipse
  diameter. Fractions stay session-locked; T22 updates their pixel distances.
- The owner names the anterior–posterior-controlled outline dimension width and the
  left–right-controlled dimension height, distinct from band thickness and the raster
  crop's bounding box.
- Both axes rotate with landmark-derived body orientation (T22/T25), not fixed camera
  axes. Keep full Euclidean landmark spans and transform the body-frame outline into
  acquired-image coordinates; manual mode keeps its fixed prepared pose. The geometry
  contract owns the settings and coordinate binding.

<a id="t31"></a>
### T31 — Full-band sampling geometry

**Status:** Accepted · **Revision:** 5

- The geometry stage supplies the complete 360-degree T29 band: no configured angular
  sectors, fixed left/right halves, preselected regions or single aggregate. T26 still
  clips intended support and logs coverage.
- Sectioning belongs to the downstream estimator, which owns T32 sectioning (initial
  equal-arc partition), measurements, quality gates and compact outputs; measurement/fit
  choices stay with T12/T04.
- Transient band/flow data remains available to the runtime estimator; no
  offline-analysis or dense-recording requirement. T04's fin estimator may select its
  angular wedge downstream; water-flow keeps full-band support.

<a id="t32"></a>
### T32 — Equal-arc outline sections

**Status:** Accepted · **Revision:** 6

- The initial sectioning divides T28's tapered-superellipse outline into equal
  arc-length sections, not equal polar angles or the undeformed ellipse. Section count
  is a positive operator setting, default 12 (current CephVR's sector count), locked for
  the session.
- Each full-band pixel takes the nearest outline location's section. Partition intended
  support before clipping; preserve T26 coverage for required sections. Equal outline
  lengths do not imply equal band area or sample counts.
- Recompute boundaries from the same eligible shape when dimensions change; sections
  move with body geometry and are geometric coordinates, not tissue identities. No
  separate worker or early statistic. T04 fin-flow intersects its angular selection with
  these labels without repartitioning the cropped outline.
- Flow summarization, fitting, quality and movement mapping stay T12/T04 choices. Dense
  section maps stay transient (T15).

**Contracts:** [sectioning contract](../../contracts/tracking/sectioning.md) (anatomical
origin/order, deterministic boundaries/ties, numerical construction, settings, versioned
convergence checks, bounded segment projection); fixed accuracy limits belong to the
sectioning policy, not rig tuning.

<a id="t33"></a>
### T33 — Full flow samples available to the estimator

**Status:** Accepted · **Revision:** 3

- Give the estimator all available provider-grid flow samples in the analysis band, with
  acquired-image positions and T32 section association; no representative vectors,
  averages, early fit or spatial subsample beforehand.
- Preserve provider resolution, sample identity, source frame pair, units, native
  validity and optional quality evidence. Per-camera-pixel flow,
  interpolation/upsampling and out-of-band samples are not required as scientific input.
  Quality rejection and weighting are explicit T12/T04 method choices, not hidden
  preprocessing.
- NVIDIA samples use the native block estimate, positioned at the centre of its
  represented acquired-image footprint, including clipped edge blocks. This is the
  declared coordinate convention for turning, not an arithmetic mean of pixel flow
  or a claim that NVIDIA exposes an independent sample at that point.
- Use existing native buffer leases and the bounded path; no per-sample RPC, extra
  process, mandatory CPU copy or duplicate full-field representation.

**Contracts:** [estimator input](../../contracts/tracking/estimator-input.md) (transient
handoff).

<a id="t34"></a>
### T34 — Measured flow with separate pose evidence

**Status:** Accepted · **Revision:** 2

- Preserve camera-measured forward optical-flow displacement at the estimator boundary;
  supply the T09 pose/manual geometry separately with source/age/validity evidence.
  Preprocessing subtracts no body translation/rotation, mantle deformation or background
  motion.
- Rotating ROI/sections (T30) changes sampling geometry, not measured flow.
  Re-expressing vectors in another basis stays distinguishable from subtracting motion;
  no hidden stabilization, frame warping or compensation.
- A future estimator may explicitly define projections or compensation with compatible
  inputs and retained method settings/identity; none is selected now. Never infer pose
  history/velocity from one observation or mutate measured samples. T12/T04 keep
  measurement, fit and calibration choices.

<a id="t35"></a>
### T35 — Relative locomotion-control outputs

**Status:** Accepted · **Revision:** 4

- Publish camera-scale-calibrated locomotion-control proxies in mm/s for forward
  and sideways and deg/s for turning, mapped to virtual movement by explicit gains.
  They remain image-plane flow-derived controls, not measured animal swimming
  velocities. Never infer calibration from camera flow or body dimensions.
- Keep measured evidence, estimator control signals and Visual Stimulus-applied movement
  distinguishable in compact records and declarations. Method identities, units/scaling
  and source timing stay explicit (T27/A05); no undocumented arbitrary units or
  camera-FPS-dependent behavior.
- Reuse existing Visual Stimulus feedback binding/gain ownership; no tracking-owned Visual Stimulus gain layer.
  T37/T38 bind speed control and direct method units.

**Contracts:** [output contract](../../contracts/tracking/locomotion-output.md) (channel
meanings; links each method's unit/mathematics bindings and remaining work).

<a id="t36"></a>
### T36 — Full planar locomotion control

**Status:** Accepted · **Revision:** 3

- The initial target is forward/backward, left/right sideways and turning (yaw) drive.
  Sideways is an independent planar translation, never dropped or derived from yaw. No
  vertical translation, pitch or roll control.
- Control meanings use the animal's anatomical body frame, independent of camera
  orientation/mirroring. The output contract binds names and sign conventions; Visual Stimulus's
  motion/feedback contracts own conversion to virtual-observer movement.
- Each estimator declares support and evidence for all three components before meeting
  the full-planar target; this does not establish identifiability. Never publish an
  unsupported component as a valid-looking zero or fabricate a calibration.
- T12/T04 govern measurement and quality rules. This neither runs both pipeline families
  concurrently nor establishes a missing runtime/Ready path.

<a id="t37"></a>
### T37 — Drive controls virtual speed over source intervals

**Status:** Accepted · **Revision:** 1

- Forward, sideways and turn drive set virtual linear/angular speed through existing Visual Stimulus
  feedback gains. Channels are interval_average_rate, integrated only over explicit
  valid source intervals under V24–V26; render FPS or result spacing never sets movement
  amount.
- Reuse the existing integration rule and timing/reset/epoch attribution. No virtual
  acceleration/inertia, repeated movement from an unchanged sample, gap bridging with
  remembered drive, or overlapping history counted as new time. Missing/invalid input
  holds feedback-driven state; programmed motion keeps its own rules.
- This is temporal meaning for relative control, not physical velocity. The output
  contract binds quantity/units and gain compatibility; the estimator must derive values
  consistent with that interval and their declared units.

<a id="t38"></a>
### T38 — Calibrated estimator outputs through existing Visual Stimulus gains

**Status:** Accepted · **Revision:** 5

- Consumer identifiers use the canonical Visual Stimulus name owned by [V01](visual_stimulus.md#v01).
- Pipeline version 2 converts the filtered pixel-space forward/sideways controls
  once by dividing by T20's acquired-image px/mm, and converts filtered angular
  radians/s to degrees/s. Publish mm/s and deg/s through the existing Visual Stimulus
  feedback binding. Preserve raw/filter intermediates in px/s and rad/s for evidence;
  no activity rescaling, fixed [-1,1] range or adaptive gain normalization.
- Retain exact method/version, units and configuration with compact evidence; gains keep
  their stimulus-program/epoch owner. New methods or subjects may need new explicit
  gains. Require matching program input units/quantity/body frame before preparation;
  old px/s or 1/s bindings must be edited explicitly with their gains. Never rewrite
  old recordings or silently reinterpret their units.
- Estimator-defining operations (native flow scaling, coordinate transforms,
  displacement-to-rate conversion) are explicit method mathematics, not hidden
  normalization. T12/T04 bind initial units and T45 the filter; this adds no clamp,
  deadband, fit or numeric gain.

<a id="t39"></a>
### T39 — Dense tracer-water flow for swimming intent

**Status:** Accepted · **Revision:** 3

- The water_flow target measures visible water-borne particles/tracers in the
  surrounding band, using their dense image-motion field to infer swimming intent as
  T35–T38 relative planar control. Fin/mantle texture motion does not substitute for
  tracer evidence; T04's fin/tissue option keeps its own explicit interpretation.
- Keep T07's NVIDIA-only provider and T33's full provider-grid samples; no invented
  per-camera-pixel vectors, forced 1-pixel grid, particle trajectories or second
  PIV/flow backend.
- Tracer flow does not directly measure animal velocity, thrust, torque or intent.
  Animal/background contamination, ambient currents, flow quality and out-of-plane
  limits need explicit estimator checks/interpretation, unresolved by this choice or a
  geometric body exclusion alone.
- T34 keeps flow and pose separate; T40/T41 select the inference family and screening;
  T12 tracks remaining mathematics/contracts. No old rigid fit, momentum formula or
  pose-to-yaw rule is adopted by reference.

<a id="t40"></a>
### T40 — Flow-transport and turning proxy

**Status:** Accepted · **Revision:** 2

- The initial water-flow estimator combines tracer-flow direction, strength and position
  into T35–T38 relative forward, sideways and turning drive via a flow-transport/turning
  proxy, without a whole-field rigid translation/rotation model or learned decoder.
- This selects the inference family, not force/torque reconstruction or proven intent
  measurement. T42/T43 bind weighting, turning reference/calculation and units; T12
  tracks remaining contracts. Neither the old implementation nor a specific momentum law
  is adopted.
- Reuses T33/T34 measured input, T32 sections and T41 screening; existing
  invalid/reset/Visual Stimulus-hold behavior applies. Scientific support for all three outputs needs
  validation, never an assumed valid zero for a missing component.

<a id="t41"></a>
### T41 — Local flow-consistency screening

**Status:** Accepted · **Revision:** 3

- The initial estimator combines native validity with a normalized local-median
  consistency check, using provider cost only when available/configured. Compare each
  sample with nearby eligible flow and local variation, not a global rigid fit or an
  amplitude-only rule that rejects strong jets for being fast.
- Screening runs inside the estimator after T33's handoff. Measured buffers are
  preserved; suspect samples are excluded from derived estimates, never replaced by
  interpolated or fitted values. Dense screening data stays transient (T15); compact
  quality/support evidence goes in the method's records.
- W1A uses a fixed square on the native grid, excluding the tested cell and ineligible
  or outside-ROI neighbors. Insufficient neighbor support makes a sample unevaluable;
  section coverage gates decide estimate validity. One pass on original eligibility, no
  rejection cascades.
- W2A uses component-wise median residuals normalized by neighboring variation plus a
  positive displacement noise floor, combined by Euclidean magnitude. Radius, neighbor
  support, noise floor and threshold default to 1 cell, 4 neighbors, 0.1 px and 2.0
  (standard normalized-median-test values), tuned on the rig; no unscreened fallback or
  replacement vectors.
- The input contract owns the integration boundary. This is a quality method, not a new
  PIV backend, process or scientific body/water segmenter.

**Contracts:** [screening contract](../../contracts/tracking/flow-quality.md) (exact
arithmetic, boundary behavior).

<a id="t42"></a>
### T42 — Linear area-weighted water-flow response

**Status:** Accepted · **Revision:** 1

- Average T41-accepted water velocities by represented acquired-image area and infer
  forward/sideways drive opposite to that mean in anatomical body coordinates. Doubling
  velocity doubles its contribution; no speed-squared weighting, outgoing-flow gate or
  equal-section reweighting.
- Convert forward displacement to rate once over the valid source interval (T37).
  Intrinsic area averaging is not T38 output normalization.
- Opposing flow can cancel and ambient circulation can bias the proxy; a valid
  arithmetic result does not prove propulsion/intent. T39/T41 limits and existing
  invalid-result behavior apply.

**Contracts:** [proxy contract](../../contracts/tracking/water-flow-proxy.md)
(calculation, area accounting, section integration, acquired-image-pixel units).

<a id="t43"></a>
### T43 — Turning rate centred on accepted support

**Status:** Accepted · **Revision:** 4

- The estimator's internal turning rate is in rad/s (1/s), converted to deg/s
  at T38's output boundary: the signed area-weighted
  moment of accepted water velocities about their area-weighted sample-position
  centroid, divided by the area-weighted second moment of those positions about the same
  centroid. This equals the least-squares rigid-rotation rate about the centroid.
  Turning drive is opposite to that water rotation, with T36's animal-left-positive
  convention.
- Use T42's accepted samples and area weights. The centroid is recomputed per estimate
  as a mathematical reference, not the outline centre, a head-fixation annotation or a
  physical pivot. Uniform velocity or translated positions leave the rate unchanged,
  even for asymmetric support; the field need not be rigid.
- A second moment that is not positive and finite invalidates the estimate under
  existing invalid-result behavior, never a zero. The rate is image-plane water
  rotation, not the animal's angular velocity or torque; support changes can change it.
  T41/T44 own quality/support gates; never substitute a remembered centroid or
  fabricated zero for failed support.

**Contracts:** proxy contract (formula, units, compact evidence).

<a id="t44"></a>
### T44 — Reliable flow coverage in every section

**Status:** Accepted · **Revision:** 2

- In every T32 section, accepted flow area after T41 screening divided by the section's
  intended (pre-clip) area must be at least `minimum_accepted_area_fraction` (default
  **0.25**, a starting value to tune on the rig; equality passes). This one gate covers
  off-image clipping (T26) and missing/rejected flow; a well-observed section cannot
  compensate for another.
- Missing, unusable, rejected or clipped flow adds no accepted area and never shrinks
  the denominator. A failed section invalidates the whole estimate; V25 holds
  feedback-driven state. No remembered drive, invented zero or partial-section fallback.
  The proxy contract binds the calculation.
- Retain compact per-section support, clipping and failure evidence; dense data stays
  transient (T15).

<a id="t45"></a>
### T45 — Source-time exponential command smoothing

**Status:** Accepted · **Revision:** 3

- Smooth the three valid relative-drive channels with a causal first-order exponential
  filter, one configurable positive time constant in seconds, default 0.08 s (about
  current CephVR's 2 Hz base low-pass), session-locked, inside the existing movement
  worker. T38 gains/units and T37 source-interval integration are unchanged.
- The proxy contract binds time-based updates and the interval-average filtered output.
  Source elapsed time sets the response, not render FPS, processing time or a fixed
  per-frame coefficient. Keep unsmoothed evidence separate from delivered drive.
- Clear filter history after invalid input, a source gap, trial/preparation boundaries
  or a processing reset; A06 delivery-only overflow preserves valid filter state. After
  clearing, seed the next usable interval from its current raw estimate; no zero-origin
  ramp, integration across missing time, stale output or remembered filtered movement.
  A06 keeps reset ownership.

<a id="t46"></a>
### T46 — Fin-edge profiles and NVIDIA fin flow

**Status:** Superseded · **Revision:** 3

Withdrawn with the other fin-undulation choices; [T04](#t04) owns the optical-flow
options and this ID imposes no implementation requirement.

<a id="t47"></a>
### T47 — Local cross-correlation of fin-motion histories

**Status:** Superseded · **Revision:** 2

Withdrawn with the other fin-undulation choices; [T04](#t04) owns the optical-flow
options and this ID imposes no implementation requirement.

<a id="t48"></a>
### T48 — One fin-motion method per session

**Status:** Superseded · **Revision:** 2

Withdrawn with the other fin-undulation choices; [T04](#t04) owns the optical-flow
options and this ID imposes no implementation requirement.

<a id="t49"></a>
### T49 — Signed lateral fin-flow feature

**Status:** Superseded · **Revision:** 2

Withdrawn with the other fin-undulation choices; [T04](#t04) owns the optical-flow
options and this ID imposes no implementation requirement.

<a id="t50"></a>
### T50 — Geometry-derived fin-analysis regions

**Status:** Superseded · **Revision:** 2

Withdrawn with the other fin-undulation choices; [T04](#t04) owns the optical-flow
options and this ID imposes no implementation requirement.

<a id="t51"></a>
### T51 — Retained local fin-wave estimates

**Status:** Superseded · **Revision:** 2

Withdrawn with the other fin-undulation choices; [T04](#t04) owns the optical-flow
options and this ID imposes no implementation requirement.

<a id="a06"></a>
### A06 — Tracking-result delivery to Visual Stimulus

**Status:** Accepted · **Revision:** 14

- A bounded tracking-result queue, capacity configurable with default 10 results,
  independent of camera-frame ring capacities, delivers retained results to Visual Stimulus in order.
  Ordered delivery needs no rendered frame per result and specifies no smoothing,
  prediction or catch-up movement.
- **Delivery overflow:** drop old pending results and advance only the delivery
  generation. With continuous camera processing, preserve valid flow baseline, filter
  and eligible pose/geometry history; never replay discarded movement. This explicit
  exception to lossless ordered delivery is not a newest-state mailbox during normal
  operation. Overflow alone does not interrupt the session; required failures retain
  E06. [V26](visual_stimulus.md#v26) rejects stale feedback locally in Visual Stimulus without requesting a
  tracking reset.
- **Processing reset** (camera gaps or input-age/overflow): clear pending results,
  advance processing and delivery generations and restart flow from the newest available
  frame with fresh baseline/filter, keeping only eligible pose history from the same
  trial/source/preparation. Combined causes use this stronger reset; delivery overflow
  alone cannot force it. Report valid movement only after a fresh baseline; never
  compute a delta across a discarded frame gap.
- Every result carries its `reset_generation`, monotonic per attachment/stream, and
  states whether it is valid; results are identified by delivery generation. A newer
  generation is the reset (no separate marker): after exact trial/source checks Visual Stimulus
  discards older pending results. Reject late previous-generation results, including
  dequeued but unapplied ones; applied Visual Stimulus movement stays applied.
- After a processing reset the first new-generation result is baseline-only (invalid
  movement); after delivery-only overflow the preserved baseline makes new-generation
  results usable at once. Tracking sends a result, marked invalid when necessary, for
  every evaluated frame, so V25's hold applies. Visual Stimulus must distinguish reset/invalid
  reports from usable updates; [V25](visual_stimulus.md#v25) owns behavior without valid feedback.
- Account for discarded results by result/source-frame identity, timestamps and reason
  in the owning backend outputs under existing save settings; saving records every reset
  with its cause. Discarded, unapplied results get no fictitious Visual Stimulus-output timing link.
- At each render update start, take the already-pending batch, apply it in order, then
  render once; later results wait for the next update.
- Preserve result identity and source-frame/timestamp lineage under A05.

**Contracts:** [delivery contract](../../contracts/tracking/feedback-delivery.md)
(generations, credits); [feedback contract](../../contracts/visual_stimulus/feedback.md) (result
generation semantics, Visual Stimulus generation gate, local freshness hold);
[concrete result/reset interfaces](../../contracts/visual_stimulus/runtime-bindings.md) (shared
boundary; runtime providers remain implementation work). Water-flow reset state is bound
under T45 and reused by fin-flow under T04. A05 defines required result-to-output links;
[Visual Stimulus evidence layouts](../../contracts/visual_stimulus/evidence-format.md) bind its output-side
records.
