# Estimator input: flow and pose

Authority: [T33/T34](../../docs/architecture/tracking.md#t33), with T09/T15/T27/T30–T32.
This contract constrains the concrete estimator port in [runtime_types.pyi](runtime_types.pyi).
The [catalogue](pipeline-catalogue.md) registers declarations, not a running flow reducer.

## Water-flow evidence source

[T39](../../docs/architecture/tracking.md#t39) targets visible particles/tracers transported
by the water for the current water_flow pipeline. The dense field is image displacement
of that tracer pattern, not individual particle tracks or a direct body-motion measurement.
NVIDIA remains the only optical-flow provider. Preserve its actual selected/verified grid;
"dense" introduces no forced grid setting, interpolated evidence or additional PIV backend.

The selected estimator infers relative forward/sideways/turning drive under T35–T38.
A water-motion field alone does not establish physical force/torque or separate propulsion
from ambient circulation. Body/fin pixels, reflections and other non-tracer texture are
potentially different signals even when they fall inside the geometric band. Their quality
handling remains explicit method work; do not silently classify all band pixels as water.
There is no newly adopted segmenter, background subtractor, force model, pivot or trained
intent decoder. T34 measured-input ownership and T15 compact-only persistence still apply.
T04 also supports fin_flow: the same provider measures fin/tissue image motion. Its
[fin binding](fin-flow.md) selects an angular part of the shared band and explicitly
reuses the numerical flow proxy for provisional relative controls. This shares arithmetic,
not a claim that tissue motion and water motion establish the same biological inference.

## Selected inference and quality boundary

[T40](../../docs/architecture/tracking.md#t40) selects a transport/turning proxy;
[T42/T43 mathematics](water-flow-proxy.md) bind its weighting, reference, response law
and units; T44/T45 bind support and smoothing in the same contract. Complete typed
settings/evidence and ports are bound in [pipeline-catalogue.md](pipeline-catalogue.md).

[T41](../../docs/architecture/tracking.md#t41) screening consumes the full input below
inside the movement worker. Native invalid/nonfinite samples are ineligible; provider
cost is additional evidence only when supplied and explicitly configured. The local
normalized-median test compares eligible neighboring measured vectors with their local
variation. Its normalization belongs to outlier scoring, not T38's output units/gain path.
It neither smooths nor overwrites accepted vectors. Rejected samples remain identifiable
in the transient view and contribute no invented replacement measurement.

[Local screening](flow-quality.md) binds neighborhood boundaries, minimum neighbors,
residual/noise-floor units, thresholds and tracking_config defaults. T44 support gates
belong to the proxy contract. An unevaluable local test is never treated as a successful
one. Preserve separate geometric coverage (T26), native availability and
screening support. Use compact counts/dispositions through the method's existing quality
records; no dense rejection-mask recording or new worker is introduced. Insufficient
reliable support follows existing invalid-result/VR-hold behavior, not an unscreened
fallback. Spatial coherence alone cannot identify body texture or prove swimming intent.

## Samples, sections and units

Pass the existing FlowLease/read-only provider buffer plus the geometry/section view to
the selected estimator. All available provider samples associated with the analysis
band remain accessible until that estimator finishes. Preserve each native grid index,
acquired-image position/footprint, forward displacement, source pair and optional quality
metadata. Section membership follows [sectioning.md](sectioning.md); it is an annotation
on evidence, not authority to discard the evidence or average a section in advance.

The adapter's prepared grid-to-acquired-image mapping owns sample positions, partial edge
footprints and source-coordinate conventions. Keep that mapping explicit at the concrete
port; grid stride alone is not permission to guess a grid origin or a different frame
anchor. The NVIDIA mapping in [method-bindings.md](method-bindings.md) already fixes
forward earlier-to-later displacement, source resolution, grid layout and native scaling.
The [proxy sampling contract](water-flow-proxy.md) binds flow-cell/band area association;
it does not reduce the provider grid or invent additional measurements.

Do not expand grid vectors into supposedly independent per-camera-pixel measurements.
No mandatory interpolation, arbitrary decimation, amplitude cutoff, top-k selection,
section summary, fitted value or speed threshold precedes estimator access. Preserve
provider invalid/nonfinite/cost evidence rather than manufacturing zero-valued vectors.
An estimator can explicitly reject/weight unusable samples under its chosen quality
rules; sample availability does not declare every vector scientifically reliable.
The [completed host-buffer contract](method-bindings.md#completed-host-buffer-contract)
binds byte order, pitches, optional native availability and cost views; absent native
validity is an explicit complete-grid declaration, not a missing-evidence repair.

Measured values are input-pixel displacements with the existing source frame timestamps,
not physical velocities. Native scaling/declared coordinate conversions preserve meaning.
A future conversion to rate must retain its interval/time basis and units explicitly.
T26 geometric support coverage remains separate from provider availability or fit quality.

## Separate pose, no implicit compensation

Supply the selected T09 observation/landmarks or prepared manual geometry, plus its
existing PoseUse lineage/validity/age evidence. Do not mislabel an asynchronous eligible
pose as measured at either flow frame. T09's invalid/stale/no-fallback behavior remains.
No single pose observation establishes translation velocity, rotation rate or a tissue
motion field. A method needing additional historical poses must declare that dependency
and validate their lineage rather than infer or reuse untracked state.

Body-following sampling geometry does not rotate/warp the source images or subtract
animal motion from the vectors. Expressing a measured vector in body coordinates is a
change of basis, distinct from subtracting a body/background-motion estimate. Preserve
camera-measured samples unchanged. No translation/rotation/deformation/background
compensator runs implicitly before this boundary.

Future T12/T04 methods may explicitly derive projections or compensated quantities from
these inputs under their own versioned settings and provenance. Such derived views do
not overwrite the measured buffers; this contract selects no compensation/fit algorithm.

## Ownership and remaining implementation

Reuse [runtime_types.pyi](runtime_types.pyi)'s FlowLease and [execution.md](execution.md)'s
movement worker ownership. Wait for native completion before consuming a buffer, and
retain its lease until all estimator CPU/GPU consumers finish. Read-only native views,
indexed views and bounded chunks are suitable; do not require a Python object per sample,
additional CPU copy, new per-frame RPC or separate worker. T08's initial CPU estimator
uses the adapter's single native-grid host readback; this is distinct from copying that
host view again for each consumer. Account for retained views and
pending computation in existing resource/progress limits. Never silently subsample to
meet an exceeded budget or publish an estimate as complete after partial processing.

T15 is unchanged: full samples, costs and section maps are transient, not dense recorded
outputs. Compact scientific fields, complete settings and port integration are bound in the
[pipeline catalogue](pipeline-catalogue.md). Core response mathematics belongs to the proxy contract;
runtime and rig validation are not implied by this handoff contract.

The selected output target is [T35/T36 relative planar control](locomotion-output.md).
Those control signals are derived quantities; preserving camera-measured input does not
make an image-flow component a validated sideways/forward/turning drive by itself.
