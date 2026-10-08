# Sampling geometry

Authority: [T28–T32](../../docs/architecture/tracking.md#t28), with T22–T27.
This is a construction contract; runtime implementation and rig validation remain
future work.
[pose.md](pose.md) owns the reference ellipse, landmark units and per-region coverage.

## Outline construction

T30 names the anterior–posterior dimension width and the left–right dimension height.
These are independent shape measurements, not band thickness or raster bounding-box
size. Both axes rotate with the body under T22/T25. Do not freeze rotation or replace
Euclidean landmark spans with camera x/y projections. For image displacement p-centre
and headward unit vector e=(ex,ey), local x=dot(p-centre,e), local y=dot(p-centre,(-ey,ex)).
The inverse maps the body outline back into the acquired image; no camera-image rotation
or resampling is required. The symmetric lateral shape does not assign animal-left
labels from the sign of this perpendicular; anatomical labels retain the pose contract.

Use the reference centre and headward unit vector from T25. Let a=d/(2*f) and b=w/2
be its longitudinal and lateral radii. Coordinates x/y below are in that orthonormal
body frame; x is positive headward. With squareness n>0 and -1<taper<1:

- u=x/a; reject |u|>1.
- width_scale=1-taper*u, strictly positive on the outline's longitudinal domain.
- A pixel centre is inside the closed body mask when
  |u|**n + |y/(b*width_scale)|**n <= 1.

Positive taper widens the posterior side, matching the reference implementation.
Taper zero with n=2 gives the reference ellipse. The parametric boundary for overlays is
x=a*sign(cos(theta))*|cos(theta)|**(2/n),
y=b*(1-taper*x/a)*sign(sin(theta))*|sin(theta)|**(2/n).
There is no optimization or fit through the three points and no added live segmentation.
Taper/squareness default to current CephVR's 0.4 and 3.5 in tracking_config; saved values win.

Use vectorized NumPy evaluation of the body predicate at acquired-image pixel centres
(integer x/y under the pose convention), retaining fractional pose/shape values until
this evaluation. This avoids a fixed 48-vertex rounded polygon defining scientific support.
Overlay contour tessellation is display-only; it must not supply a competing analysis mask.
Reject invalid, nonfinite or resource-unbounded geometry rather than clamping it into validity.

## Uniform-distance band

Rasterize the complete body into a bounded working rectangle that contains its full
extent plus the requested outer distance and a pixel halo. Body pixels are zeros and
outside pixels nonzero in the OpenCV distance-transform input. Use distanceTransform
with DIST_L2, DIST_MASK_PRECISE, and float32 output (the no-label overload).
Compare that output to the original float64 radius values; do not first round fractional
radius limits to float32 and accidentally change the half-open inclusion test.
This is Euclidean distance to the nearest body pixel centre; uniformity is at acquired-image
pixel resolution, not an exact continuous distance to the mathematical boundary.
Do not call it physical clearance from the animal without separate anatomical/calibration evidence.
A subpixel body that contains no rasterized body pixels has invalid support.

T30 resolves inner_clearance_fraction and outer_extent_fraction by multiplying each
by w, the left/right anterior-tip separation from the same eligible pose. These are
finite operator settings, with 0<=inner_clearance_fraction<outer_extent_fraction,
defaulting to 0.1 and 0.75 in tracking_config (starting values to tune on the rig). Retain the fractions under E07 and recompute scalar
pixel distances with eligible geometry updates. Require finite 0<=r_inner<r_outer. Sampling support consists of outside-body pixel centres
with r_inner<=distance<r_outer. One scalar distance is used in both axes; no anisotropic
body normalization or axis inflation. The scalar reference remains the transverse
landmark span even when the owner calls that outline dimension height.

Construct the intended full support and then intersect with the acquired image for T26
coverage. Never crop the body before the distance transform: an off-image part can be the
nearest boundary, and dropping it would alter the band as well as its coverage denominator.
Account for the whole bounded working rectangle in existing memory limits before allocating.
T31 selects the full 360-degree band with region_id=full_band. No angular sectors are
removed by this geometry stage. Its coverage is computed before flow-grid/estimator
quality gates; downstream estimator-specific support checks remain separate.

## Fin-flow reuse

[T04](../../docs/architecture/tracking.md#t04) selects this same ellipse-derived
ROI/band machinery for fin_flow, with explicit prepared settings targeting fin tissue
instead of water. Geometry is a sampling region, not automatic tissue classification;
it does not guarantee that every included pixel is fin. Reuse source coordinates,
pose lineage, coverage and buffer ownership; do not copy water-region values implicitly.
The selected pipeline's configuration owns its resolved geometry settings under T27.

The downstream fin estimator applies the angular selection defined in
[fin-flow.md](fin-flow.md), retaining the full-outline equal-arc section labels within
that selection. Shared geometry still returns the full band. T04 explicitly accepts
reuse of the numerical proxy for fin controls; its evidence remains fin/tissue motion.

## Ownership and reuse

The same geometry method serves manual and automatic poses. Automatic construction
runs on the existing pose worker, publishing an immutable exact pose/geometry pair;
manual construction runs at Setup. Reuse only that exact observation's geometry with
unchanged settings/source layout. Retain bounded pairs across movement/delivery resets;
trial/source/preparation changes retire incompatible references. Execution.md owns
history leases and resource bounds; no approximate pose thresholds or extra worker.
A cache does not authorize reusing a previous valid pose after an invalid/stale observation.
Keep all dense geometry transient under T15. Prepared stage identities/settings and T26
compact coverage evidence use the existing T27/recording boundaries.

The accepted method uses NumPy/OpenCV inside the existing tracking process. No separate
geometry service, Shapely dependency, iterative contour solver or additional GPU method
is required. Runtime scheduling and feedback remain pipeline-owned.

## Concrete settings and estimator ownership

EllipseSettings v2 in [method_models.py](method_models.py) is the pure strict settings
model for three_point_ellipse implementation 2, schema tracking.ellipse-settings.v2.
The implementation retains T25's reference ellipse and constructs T28–T31 sampling
geometry; the name does not imply a plain elliptical analysis mask. Required fields:

| Field | Meaning and bounds |
| --- | --- |
| schema_version | Exact integer 2. |
| front_fraction | Finite 0<f<=1; E07 resolves the adopted 0.60 default. |
| taper | Finite -1<value<1; config default 0.4. |
| squareness | Finite value>0; config default 3.5. |
| inner_clearance_fraction | Finite value>=0, times anterior-tip separation; default 0.1. |
| outer_extent_fraction | Finite value>inner_clearance_fraction, same reference; default 0.75. |

There is no visibility threshold: T26 clipping is logged per section and gated once by
T44's support fraction. Unknown fields, missing values, nonfinite values, inverted/equal band limits and earlier
schema versions are rejected. No camera-axis, sector or distance-reference selector is
added to operator settings: these are fixed selected-method policies. The registered
version/schema and exact resolved settings remain in PreparedMethods.stages. Source-dependent
finite extents, raster support and resource budgets still require preparation/use validation;
pure settings parsing does not establish those checks or runtime availability.

T31 assigns subsequent sectioning to the downstream estimator during tracking. Keep the
full mask and compatible transient flow data available until that estimator finishes its
work under the existing lease/ownership rules; geometry performs no early aggregation.
[T32 sectioning](sectioning.md) binds the initial equal-arc partition of the shaped
outline. The estimator owns that operation, statistics/fit, quality gates and compact
records. Measurement settings and scientific units are bound under T12/T04. No extra offline-analysis
path or dense-flow persistence is selected; T15 remains in force.
Reference construction, raster bands, section/wedge calculations, runtime caching,
evidence/lease adapters and the full Ready path remain unimplemented. The declarations
establish no rig performance or anatomical accuracy.
