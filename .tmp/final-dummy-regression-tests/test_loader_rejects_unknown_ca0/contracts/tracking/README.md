# Tracking contracts and current scope

Authority: [tracking decisions](../../docs/architecture/tracking.md). T02–T11 bind
pipeline organization, families, camera scope and pose/image-flow method scope.
The independent method, lifecycle and compact-record contracts are declared below.
Canonical lightweight models, configuration and validators now live in
`src/cephvr/tracking`; contract modules re-export them. They do not implement native
tracking or prove rig behavior.
T08's [optimized frame path](execution.md#optimized-frame-path) is accepted: CPU
preparation/estimation in one ordered movement worker, independent pose, reusable
private leases and one native-grid host readback. The typed private-frame retention
and completed host-flow views are bound in runtime_types.pyi; runtime providers and
local tests are implemented under `src/cephvr/tracking` and `tests/tracking`.
See the [tracking report](../../reports/tracking.md) for current evidence and pending
native/rig acceptance. The [flow operation contract](method-bindings.md#baseline-and-pair-operation-contract)
and [host-buffer contract](method-bindings.md#completed-host-buffer-contract) now specify
first-frame establishment, completion/lease ordering, source/mapping identity, byte order
and optional native availability explicitly. These are declarations, not executable methods.

| Contract | Owner |
| --- | --- |
| Replaceable methods and concrete settings registration | [stages.md](stages.md), [stage_registry.py](stage_registry.py) |
| Complete initial pipelines, connections and evidence checks | [pipeline-catalogue.md](pipeline-catalogue.md), [pipeline_catalogue.py](pipeline_catalogue.py) |
| Shared local flow consistency | [flow-quality.md](flow-quality.md) |
| Pose/reference coordinates and candidate selection | [pose.md](pose.md), [contour-landmarks.md](contour-landmarks.md) |
| Sampling outline and uniform-distance band | [geometry.md](geometry.md) |
| Downstream equal-arc outline sectioning | [sectioning.md](sectioning.md) |
| Measured flow and separate pose at estimator input | [estimator-input.md](estimator-input.md) |
| Relative planar control output meanings | [locomotion-output.md](locomotion-output.md) |
| Shared initial response mathematics and units (water-flow owner) | [water-flow-proxy.md](water-flow-proxy.md) |
| Fin angular selection and explicit proxy reuse | [fin-flow.md](fin-flow.md) |
| ONNX, threshold/contour and NVIDIA SDK mappings | [method-bindings.md](method-bindings.md), [method_models.py](method_models.py) |
| Result reset generations and exact queue credits | [feedback-delivery.md](feedback-delivery.md) |
| Worker scheduling, private buffers and pose eligibility | [execution.md](execution.md), [runtime_types.pyi](runtime_types.pyi) |
| Cross-backend Setup descriptors and attachment confirmation | [data-preparation.md](../data-preparation.md) |
| Setup attachments, first activity and teardown | [lifecycle.md](lifecycle.md), [preparation RPCs](../cephvr/tracking/v1/services.proto) |
| JSON Lines file, writer admission, synchronization and cutoff | [recording.md](recording.md) |
| Compact record line types | [records.md](records.md), [record_models.py](record_models.py), [record_codec.py](record_codec.py) |

Generated JSON schemas come from the two pure model modules; run `schema_check.py`
to check freshness and `test_contracts.py` / `test_pipeline_contracts.py` for local boundary checks. Neither opens
experimental files or invokes a backend/SDK. Shared strict JSON helpers are reused
from contracts/visual_stimulus without adding another service or framework.

## Selection and configuration binding

E07/E14 own configuration resolution, strict validation, Setup and Start locking.
Use the existing [TrackingSettings](../cephvr/control/v1/types.proto) in BackendSettings;
no second tracking configuration envelope or independent device owner is introduced.

| Operator value | Typed control field | Validation |
| --- | --- | --- |
| `recording.save_tracking_data` | `TrackingSettings.save_tracking_data` | Boolean, default true; preserve explicit false. Independent of activation/camera/Visual Stimulus saving; no outputs from disabled tracking. |
| `pipeline.name` | `TrackingSettings.pipeline_id` | `water_flow` or `fin_flow` from the versioned pipeline catalogue; default `water_flow`. No fallback pipeline. |
| `input.camera_role` | `TrackingSettings.input_camera_role` | `behavioral` or `tracking`, mapped to the existing CameraRole enum. Exactly one selected role; unspecified/unknown values fail. |
| `pose.threshold.level` / `polarity` | `stages[pose].settings_json` (ContourSettings) | Required for automatic threshold_contour; finite level in prepared grayscale range; dark/bright enum under T18. |
| `recording.*` resource/timing fields | `TrackingFilePolicies.recording` | T19 file-only positive bounds; required when saving; see recording contract. |
| `pose.subject_reference` | `TrackingSettings.subject_reference` | T20 headward/tipward and animal-left/right setup references with matching source dimensions; live landmarks use the selected manual/automatic pose binding. |
| `pose.search_region` | `TrackingSettings.pose_search_region` | Automatic mode requires integer x/y/width/height; validate against the prepared acquisition image under T16. No crop defaults. |
| `pose.manual` | `TrackingSettings.manual_pose` | Required in manual mode; named landmarks and positive image dimensions validated under the pose contract. No fabricated defaults. |
| `pose.model` | `stages[pose].settings_json` (ModelSettings) | Strict ModelSettings, including explicit model asset, score/geometry gates and device; required only for selected model pose. |
| `pose.contour` | `stages[pose].settings_json` (ContourSettings) | Strict ContourSettings; selected contour pose also includes its threshold fields. |
| `flow` tuning | `stages[image_flow].settings_json` (FlowSettings) | Strict FlowSettings only if the accepted pipeline needs flow; defaults device 0, grid 4 px, preset slow, hints/cost off, verified at Setup. Fixed adapter/input mapping are injected from policy, not operator selectors. |
| `frames.max_frame_age_ms` / `results.capacity_results` | `TrackingFilePolicies.maximum_input_frame_age_ns` / `result_capacity` | File-resolved A04 input-age and A06 queue budgets; exact positive int64 ns / positive uint32; no duplicate defaults. |
| `geometry` | `stages[geometry].settings_json` (EllipseSettings v2) | Reference fraction, taper, squareness and inner/outer distance fractions; strict bounds in the [geometry contract](geometry.md). Defaults 0.60, 0.4, 3.5, 0.1 and 0.75. All are session-locked. |
| `estimator` | `stages[estimator].settings_json` | Complete WaterFlowSettings or FinFlowSettings; sectioning, quality, support, smoothing and fin-only wedge under the [catalogue](pipeline-catalogue.md). Config defaults except fin_region angles, which are explicit. |
| `limits` | `SetupSessionRequest.tracking_policies.limits_json` | Strict FileLimits; configuration-file-only document/asset/native/message budgets and progress deadlines, required for enabled tracking. |
| `pose.mode` | `TrackingSettings.pose_mode` | `manual` or `automatic`, mapped to TrackingPoseMode; default `automatic`. Unspecified/unknown values fail. |
| `rpc.port` | Tracking startup endpoint | Loopback port 1..65535, default 50055; startup-only. No session override. |
| `pose.max_age_ms` | `TrackingSettings.pose_max_age_ms` | Positive finite automatic-pose age bound, default 500; convert once to exact positive int64 nanoseconds. |
| `pose.history_capacity` | `TrackingSettings.pose_history_capacity` | Required positive uint32 automatic-pose history count, included in Setup memory accounting. |
| `pose.automatic_method` | `stages[pose].implementation_id` | `keypoint_model` or `threshold_contour`, resolved through the installed stage registry; default `threshold_contour`, which still needs rig threshold/contour values. No implicit fallback. |

Saved/explicit session selections take precedence over defaults under E07. Pipeline,
pose mode/method/age/history, flow, geometry and estimator tuning have tracking_config
defaults. Camera role, threshold level/polarity, contour limits, model manifest/scores,
search rectangle, subject reference, manual landmarks and fin_region angles remain unset. Disabled tracking retains ordinary settings without opening
sources or loading methods; it adds no input or output obligations under E10.
The [operator file](../../config/backends/tracking_config.toml) and
[fixed policy file](../policy/tracking_policy.toml) must have matching policy_version.
Unsupported policy values and unknown fields are errors, not ignored extensions.

T27 keeps the method implementations replaceable through [typed stage registration](stages.md).
The [pipeline catalogue](pipeline-catalogue.md) owns each supported ID's required stages,
complete estimator settings and output-channel declarations. Validate against that same definition
in GUI/headless configuration and backend preparation; do not maintain a separate GUI
stage graph. Do not introduce arbitrary dictionaries, executable expressions or dynamic
module paths to bypass the typed schemas. The accepted family IDs are
`water_flow` and `fin_flow`; neither denotes an exact estimator implementation.
Supporting both is not authority to run both concurrently. T06/T07 bind pose and
image-flow method scope; T10/T11 bind landmarks and the model runtime. Complete estimator bindings and contour extraction are declared; rig tuning and runtime
construction remain outstanding. T08/T09 bind execution
and scheduling.

The pose mode is explicit and session-locked. Validate manual geometry against the
selected source and pipeline requirements; do not treat missing or zero-valued sentinels
as permission to substitute automatic pose. Validate automatic method/assets before
Ready, without falling back to manual geometry or a different method. Retain mode and
its resolved inputs in the existing E04/E07 setup record. The [landmark payload](../cephvr/tracking/v1/pose.proto) and independent method payloads
are declared. Geometry/estimator contracts are declared; their runtime providers must be built before Ready.
T09 invalidates pose-dependent movement for missing/invalid/stale geometry; actual
quality settings must be supplied and validated against the source. No mode change or fabricated movement follows.

Automatic pose instantiates only its explicitly selected method. Keep trained-model
and threshold/contour settings typed and distinct; both must meet the pipeline's
required landmark/geometry contract. A retained inactive automatic-method choice may
remain in saved manual-mode settings, but it does not load a model or execute detection.
Bind method assets/settings to [method-bindings.md](method-bindings.md). Runtime geometry
construction and estimator quality evaluation must be implemented before preparation.

NVIDIA Optical Flow is fixed by [tracking policy](../policy/tracking_policy.toml) under
T07; do not duplicate it as a single-option GUI/TOML selector or operator control field.
Instantiate it only when the selected pipeline requires image flow. The native adapter
must inspect actual hardware/driver/provider capability and selected input representation
at Setup, preserve source lineage and T01 preprocessing provenance, and fail preparation
when requirements are unmet. Capability checks and runtime integration are unimplemented.
Keep only the NVIDIA implementation behind the [small flow-method interface](execution.md#flow-method-extension-boundary). DIS/PIV are not supported-method entries today. Add a method only for a documented concrete
need under T07, with its contract/policy version updated and explicit validated selection
if more than one becomes supported. Do not substitute methods during a session.

Setup validates that the selected acquisition role is enabled and supplies a compatible
native representation under T01. Bind its exact camera/device and source-generation
identity through acquisition's existing preparation/attachment contracts. Retain the
resolved selection and relevant identity in E04/E07's existing active-backend setup
metadata. Do not copy camera settings into tracking, select the first discovered camera,
or silently switch input when the selected source fails. Required failures follow E06.

A03/A04 own frame transport and backlog handling; A06 and V25/V26 own the already
accepted result/reset and Visual Stimulus hold behavior. Selecting one camera changes none of those
policies. [Execution binding](execution.md) names the tracking process as the attachment
and result owner. Use [lifecycle.md](lifecycle.md) for typed preparation and the existing A06 channel.
T35/T36 channel names/meanings are bound in [locomotion-output.md](locomotion-output.md);
T37/T38 bind interval-average speed control without a normalization layer. Water-flow
units/support/smoothing are shared explicitly by fin_flow under T04; complete typed
estimator declarations are bound in the catalogue.

## Recording binding

[T14/T15](../../docs/architecture/tracking.md#t14) own the independent save switch and
compact scientific content. Resolve the switch once through E07; require explicit
presence in prepared settings for enabled tracking. An inactive backend may retain its
saved switch without creating files or dependencies. Saving Off changes persistence,
not computation, result publication or administrative failure reporting.

Use supervisor-owned E04 output reservations and common E11 trial admission/finalization.
Keep scientific records in backend outputs, not SESSION_LOG or per-trial configuration.
Record actual observations/results, including invalid/baseline/reset/discard evidence;
Visual Stimulus-owned applied-result/render links remain with Visual Stimulus. Missing/dropped input cannot be
represented as a fabricated observation. T09 pose selection links must identify the
observation used or its missing/invalid/stale disposition.

[Recording contract](recording.md) binds the T19 JSON Lines file, bounded writer,
periodic sync and crash state. The independent typed payloads are bound in [records.md](records.md);
estimator-dependent fields follow T12/T04. No dense-flow switch or payload is declared.

## Current water-flow evidence

[T39](../../docs/architecture/tracking.md#t39) selects visible tracer-water motion as the
current signal for swimming-intent inference. The [input contract](estimator-input.md)
binds its distinction from body texture motion and its unchanged native-grid/recording
scope. [T40/T41](../../docs/architecture/tracking.md#t40) select the initial proxy
family and local screening; [T42/T43 response mathematics](water-flow-proxy.md) bind
weighting, turning reference and units. T44/T45 bind support in every section and
exponential smoothing. T12 method choices and local declarations are accepted; runtime
construction and scientific validation remain distinct. [T04](../../docs/architecture/tracking.md#t04)
adds fin/tissue optical flow through the same execution path. [Fin-flow](fin-flow.md)
binds angular support, retained equal-arc sections and explicit numerical proxy reuse.
Complete shared estimator settings/evidence and registration are bound in the catalogue.

## Completion and remaining work

The initial water-flow and fin-flow architecture, method settings, compact evidence,
worker interfaces and complete pipeline composition are declared. The catalogue links
their owners without introducing another decision list. No critical owner choice is
left in the four requested groups: fin sampling, contour landmarks, water completion
and pipeline registration. Alternative methods remain possible through T27.

Runtime implementation is authorized under [ARCH-001](../../architecture.md#arch-001).
The [Tracking report](../../reports/tracking.md) records progress and validation limits. The following scenarios
must be traced through the owning contracts before overall architecture review is closed:

| Scenario | Owning contract and expected evidence |
| --- | --- |
| Setup/manual or automatic pose; saving On or Off; open or closed loop | [Lifecycle](lifecycle.md): active resources and Ready obligations match the selected mode. |
| First frame, subsequent pair and source reset | [Flow operations](method-bindings.md#baseline-and-pair-operation-contract): baseline creates no displacement; only completed matching leases reach the estimator. |
| Missing/newer-invalid/stale pose or insufficient support | [Execution](execution.md), [proxy](water-flow-proxy.md): no older-valid fallback, usable control or retained filter tail. |
| Input gap/overload or feedback-age reset | [A04](../../docs/architecture/acquisition.md#a04), [A06](../../docs/architecture/tracking.md#a06), [Visual Stimulus feedback](../visual_stimulus/feedback.md): one reset owner, result reset_generation, exclusions and fresh baseline. |
| Evidence admission failure, normal cutoff or Abort | [Recording](recording.md), [lifecycle](lifecycle.md): required evidence precedes dependent publication, producer cutoff is distinct from file closure, no between-trial file scan. |
| Native timeout or incomplete cleanup | [Execution](execution.md), [E06](../../docs/architecture/system-contracts.md#e06): no reuse of live buffers or false cleanup success. |

The [integration review](../../reports/tracking.md) records
an earlier pass; its reset-marker findings are superseded by A06's result generations.
This is a document-review checklist, not a runtime test suite or a claim that the
scenarios have been exercised on hardware.

Runtime workers, geometry/estimator computations, SDK adapters, lifecycle integration,
and recording remain unimplemented. Lightweight configuration loading/validation
and schema discovery are implemented; see the report for checks and limits. In particular the adapter must
establish the actual native grid mapping/capabilities and enforce the declared resource
and lease contracts before Ready. Pure declaration checks do not execute these methods.
Rig/subject inputs still require operator entry, and timing, image/landmark accuracy,
scientific response and integrated performance retain E15 rig verification.
Existing CephVR code remains reference material; no simulated-backend milestone is added.
