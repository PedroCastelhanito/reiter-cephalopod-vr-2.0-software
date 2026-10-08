# Equal-arc sectioning

Authority: [T32](../../docs/architecture/tracking.md#t32), under T26/T27/T31.
The downstream estimator owns this helper; it does not become another stage worker,
modify full-band geometry construction or select a locomotion fit. This contract and its
pure settings model are declarations; runtime construction and rig validation remain
future work.

## Coordinate and assignment rule

Use the full tapered-superellipse outline from [geometry.md](geometry.md), before image
clipping. Let its complete perimeter be L. Arc coordinate s=0 starts at the posterior
outline endpoint (T25's posterior landmark). Increase s along the animal-left side toward
the anterior endpoint, then return along the animal-right side. T21's labelled landmarks
identify sides; screen left/right never does. The labels must define a valid lateral side
under existing pose quality checks; do not infer a side from camera mirroring.

For explicit count N, section k covers normalized arc [k/N,(k+1)/N), k=0..N-1.
The closing endpoint wraps to zero. N=1 is valid and leaves one complete-band section;
tracking_config defaults to 12 (current CephVR's sector count). Recompute equal-length boundaries for changed shape
parameters/dimensions, while maintaining this anatomical origin and direction. Rigid
pose changes transform the outline and its sections together. IDs are normalized
geometric positions, not material tissue trajectories across time.

For each pixel centre in the intended full band, find its nearest location on this
outline in acquired-image Euclidean distance, compute its normalized arc coordinate
q=(s/L) modulo 1, and assign floor(N*q). If there are exactly tied nearest locations,
choose the lowest normalized q. A shared boundary belongs to the section starting there.
Each intended band pixel belongs to exactly one section; sections neither overlap nor
leave gaps. Contour-to-pixel nearest association is not an angular wedge from the centre.
Equal inner-outline lengths need not yield equal band areas or equal flow sample counts.

For fin_flow, intersect these labels with the downstream angular selection in
[fin-flow.md](fin-flow.md). Preserve section IDs and full-outline boundaries; do not
renumber or redistribute arc lengths after cropping. Required fin sections are those
with nonzero intended selected support before image clipping. Water-flow continues to
require every full-band section. The fin binding owns selected-area coverage denominators.

## Numerical construction and resources

Approximate the analytic outline with a closed, adaptively refined ordered polyline;
compute cumulative segment lengths and interpolate the N equal-arc breakpoints. Project
band pixel centres onto polyline segments (including segment interiors), not merely the
nearest sampled vertex. Retain the corresponding interpolated arc coordinate. The implementation's fixed accuracy policy is versioned under
[tracking_policy.toml](../policy/tracking_policy.toml), sectioning.numerics_revision=1:
quarter-point chord deviation <= outline_error_px and relative refined-versus-coarse
segment-length difference <= perimeter_relative_error. These are numerical approximation
limits, not operator/biological tuning values or a claim of exact continuous arc length.

Start from the four exact quadrant endpoints in the anatomical frame. For each segment,
evaluate its quarter/mid/three-quarter points; compare their distances to the chord and
the four-piece versus single-chord length. Bisect failing parameter intervals until all
checks pass. Do not round trigonometric endpoint residuals through fractional powers:
evaluate exact cardinal endpoints explicitly. Exhausted workspace or representable
float64 refinement fails explicitly. These are convergence checks at refined probes,
not a mathematical certificate of the maximum continuous-curve error for every shape.
Future numerical verification must compare circular and tapered outlines to independent
perimeter calculations. The declared numerical values are 0.01 source pixel and 0.0001
relative length (0.01%), owned by the policy file; their runtime implementation and
verification remain future work.

Nearest-segment projection runs in the anatomical orthonormal frame. It preserves
acquired-image Euclidean distances while avoiding image-translation/reflection roundoff
changing labels. No body-motion subtraction or anisotropic normalization is introduced.
The returned overlay/breakpoint coordinates remain in the source-image frame. Project
against segment interiors in bounded pixel-by-segment tiles; resolve exact squared-
distance ties by minimum wrapped arc coordinate, including the closing endpoint.

Use bounded batches for projection within existing memory/work limits; do not allocate
an unbounded pixels-by-segments matrix. Excessive N, inability to meet accuracy/resources,
zero perimeter or empty required support cannot produce a valid estimate. Do not silently
change the requested count, downgrade accuracy or omit sections. Runtime operational
errors retain E06; invalid observations/support retain existing T09/T26 semantics.
Reuse a partition only when the selected pose/shape, section count, source geometry and
preparation/trial/source binding match. A delivery/processing reset alone does not
change retained eligible geometry. No smoothing or last-valid fallback is introduced.

Partition the intended full support before image clipping. Compute requested/visible
pixel counts per section through the shared coverage helper, retained as intended/visible
areas in FlowProxyEvidence with section_index=0..N-1. T26 clipping is logged per section;
T44's single gate divides accepted area by the intended area of each required section. The geometry stage retains its full_band GeometryEvidence separately; do not
duplicate per-section coverage records in both stages. Additional
flow-grid coverage or estimator-quality checks cannot replace that geometric evidence.
No duplicate geometry authority is introduced: the estimator calls the shared coverage
helper for its derived regions. Keep dense labels and intermediate projections transient.

## Settings and estimator integration

[ArcSectionSettings](method_models.py) / [arc-section-settings.schema.json](arc-section-settings.schema.json)
contains schema_version=1 and count (exact positive uint32; no Boolean or float).
The operator source is estimator.sections.count (config default 12). E07 resolves this subset and locks it
for the session. The selected estimator's concrete settings model embeds it and
retains the resolved values/version through T27's existing prepared-stage binding.

Do not register a fictitious estimator or add a second StageConfiguration solely for
this helper. The complete [pipeline catalogue](pipeline-catalogue.md) composes this
subset with response, quality gates and compact evidence. Parsing cannot establish Ready.
The equal-arc method remains replaceable under T27.

## Flow samples and measured motion

[T33/T34 estimator input](estimator-input.md) preserves provider-grid samples and separate
pose evidence. Section association does not authorize averaging, spatial subsampling,
upsampling or body-motion subtraction. The geometry-pixel partition above is distinct
from the provider's flow grid: retain the provider's actual sample positions/footprints
and provenance rather than fabricating one independent vector per mask pixel.
