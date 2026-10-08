# Replaceable tracking methods

Authority: [T27](../../docs/architecture/tracking.md#t27), with T02/T07/T08/T09/E07.
All method choices in the tracking documents describe the currently selected baseline.
They are open to replacement; accepted interface/ownership rules still govern experiments.
This contract adds pure registration/validation and typed interfaces, not runtime workers.

## Small explicit registry

[stage_registry.py](stage_registry.py) maps (stage_id, implementation_id) to an immutable
StageSpec: implementation version, concrete strict settings model/schema identity,
input/output contract identities and optional compact evidence model. Runtime factories
use the same key/version in a worker-only registration table; ordinary explicit imports
suffice. Pure validators never import GPU SDKs, load models or start workers. No filesystem
plugin scan, arbitrary import strings in experiment files or automatic provider substitution.

A named pipeline owns dependencies and scheduling. Its replaceable roles are image
preparation, pose, geometry/region construction, image flow, locomotion estimation and
filtering/mapping. It only instantiates required roles. A replacement must satisfy the
role's input/output units, coordinates, timing/lineage, validity, reset and lease contract;
matching Python shape alone is insufficient. Optional feature extraction stays inside the
relevant registered method until a concrete shared boundary is justified. No speculative
extra process or generic queue is introduced per stage.

Configuration carries exactly one StageConfiguration per selected stage in
TrackingSettings.stages. settings_json is decoded with the registered concrete schema;
unknown implementation/schema, duplicate stage, absent required stage or incompatible
ports fail Setup. Resolve settings/defaults under E07, then retain StageBinding with actual
implementation version, exact resolved settings and schema/port/evidence identities.
The existing provider-specific prototype wire fields are reserved and removed; no parallel
settings copies or edit priorities remain. The initial TOML tables map into these entries:

| Operator inputs | Stage / implementation | Settings schema |
| --- | --- | --- |
| pose.automatic_method=keypoint_model, pose.model | pose / keypoint_model | tracking.model-settings.v1 |
| pose.automatic_method=threshold_contour, pose.contour + pose.threshold | pose / threshold_contour | tracking.contour-settings.v2 |
| flow (provider currently fixed by T07) | image_flow / nvidia_optical_flow | tracking.flow-settings.v1 |
| geometry | geometry / three_point_ellipse (implementation 2) | tracking.ellipse-settings.v2 |
| estimator (water_flow) | estimator / water_flow_proxy | tracking.water-flow-settings.v1 |
| estimator (fin_flow) | estimator / fin_flow_proxy | tracking.fin-flow-settings.v1 |

The geometry row binds T25–T31's reference ellipse, tapered sampling outline and complete
uniform-distance band; [geometry.md](geometry.md) owns construction and settings details.
Its v2 schema rejects incomplete v1 settings; only E07 fills tracking_config defaults.
Schema validity does not establish an implemented geometry worker or a complete estimator.

Threshold level/polarity are fields of ContourSettings, not common pose requirements.
Manual mode retains common manual landmarks and does not instantiate an automatic pose
method. Inactive saved selections remain reusable settings, not active stage entries.
Contour landmark extraction is bound in [contour-landmarks.md](contour-landmarks.md).
The [pipeline catalogue](pipeline-catalogue.md) binds complete estimator settings and
connections; this registry cannot turn a declaration into an implemented or prepared backend. Missing runtime factory,
region binding or estimator blocks Ready, even when settings validate.

## Execution and scientific boundaries

Setup compares validator/factory versions, checks contracts/capabilities/resources and
builds direct stage object references once. The processing path does not discover modules,
parse JSON or choose a provider per frame. T09's asynchronous pose and ordered movement
stay with the pipeline host. The host owns camera attachment, source/reset generations,
record admission and feedback publication; methods do not become session authorities.

Reuse the prepare/compute/reset/close ownership rules in [runtime_types.pyi](runtime_types.pyi).
Settings are concrete model types supplied by registration, not ONNX/contour unions in the
shared method protocol. Image flow exposes a declared vector-grid lease with explicit
storage, scaling, units and completion; NVIDIA SHORT2/cost conventions remain that adapter's
mapping. Other implementations can expose another supported storage format without
rewriting controller/recorder or pretending it is an NVIDIA buffer. New data semantics
require an explicit compatible adapter or versioned contract, never a silent conversion.

The same extension rule applies to later geometry/estimator/filter methods: concrete typed
inputs/outputs per registered port, with native leases and stage-local reset state. Exact
scientific estimator ports are bound in [pipeline-catalogue.md](pipeline-catalogue.md).
Adding a future pose representation beyond the current three landmarks requires a new
versioned pose contract and compatible consumers, not reshaping it into misleading tips.

PreparedMethods.stages is retained in the existing tracking scientific header. StageEvidence
uses the exact registered compact evidence schema referenced by that prepared binding.
The recorder and external reader validate it through the same pure registration; opaque
unknown JSON is never considered valid. Byte budgets, backward references and no-dense-data
scope still apply. A reader lacking the matching historical validator reports an
unsupported schema; it never substitutes today's method schema for an older experiment. Saving Off retains existing administrative metadata
only; no new promise of detailed scientific provenance is added.

## Adding an approach

Provide its pure concrete settings/evidence schema, compatible stage contract identities,
method class and explicit registrations. Exercise validation, reset/lease/failure behavior
and scientific/rig checks appropriate to the change. Update the versioned supported-method
catalogue/policy and select it before fresh Setup. There is no architectural reapproval
solely because the algorithm differs; changes to shared guarantees/meaning remain explicit.
No existing scientific record is rewritten and no mid-session hot swap is authorized.
NVIDIA is the only flow provider included now. The initial ellipse/ONNX/threshold choices
are replaceable implementations, not proof that they will be the final best methods.
