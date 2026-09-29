# Shared pose and model deployment binding

Authority: [T10/T11](../../docs/architecture/tracking.md#t10) and
[T16/T17](../../docs/architecture/tracking.md#t16). Scheduling and invalid-pose
selection remain [execution.md](execution.md). These declarations are not a pose runtime.

## Experimental geometry

[T10](../../docs/architecture/tracking.md#t10) records the owner's head-fixed animal
scope. Automatic pose must permit observed mantle movement; do not freeze the mantle
triplet or force a rigid transform because the head is restrained. Manual mode retains
T05's explicitly fixed geometry and does not promise to measure those changes. A fixed
search rectangle under T16 limits where detection searches, not the mantle's measured
orientation within it. T20 supplies four labelled directional setup references.
Do not silently add a fixed pivot, maximum bend
or animal-speed interpretation. T12/T04 own the accepted initial locomotion inference
bound in the [pipeline catalogue](pipeline-catalogue.md).

## Four-point subject reference

[T20](../../docs/architecture/tracking.md#t20) maps `pose.subject_reference` to
TrackingSettings.subject_reference: positive image_width_px/image_height_px and named
anterior/posterior/medial_left/medial_right points with finite x_px/y_px coordinates.
Dimensions must match the selected prepared acquisition image. All points must be present
and within its pixel-centre bounds; zero is a valid coordinate. Reject coincident
anterior/posterior or coincident left/right references. Do not demand guessed symmetry
or an exact anatomical endpoint that the directional labels do not specify.

The accepted label meanings are anterior toward the head, posterior toward the mantle
tip, medial_left toward the animal's left side and medial_right toward its right side.
These are animal-relative labels, not increasing/decreasing screen x. Preserve operator
labels through camera/display transforms; do not swap them merely to match screen order.

The operator authors these points, manual landmarks, search rectangle and geometry
adjustments in Configuration through A10's manual camera preview and overlays. Convert
display zoom/crop back to acquired-image coordinates before committing through E07's
normal revision-checked configuration editing. Headless clients supply the same typed
values; this does not require a GUI or introduce another camera owner.

Setup validates saved annotations against the confirmed camera source/layout and
prepares immutable values; it does not open an annotation step, accept edits or wait
for a user to click points. Missing/incompatible values fail preparation with their
field names. Return to Configuration to correct them; Ready edits follow E07's
invalidation/cleanup rules before fresh Setup, and active-session edits remain blocked.

Changes to selected camera, ROI (including origin), binning, dimensions or orientation
invalidate the previous source/layout validation even when dimensions happen to match.
Review/revalidate the affected annotations against the new image; do not silently
rescale, relabel or reuse them as verified. Existing configuration/source identities
bind this validation; no new calibration log or per-frame copy of fixed annotations.
Retain the resolved values with existing active-backend setup metadata.

The posterior-to-anterior vector defines the initial headward longitudinal reference;
anterior-to-posterior is tipward. The medial_left-to-medial_right vector points toward
the animal's right side. No separately editable
copy of the derived angle is needed. These are image-space reference directions and
spans; they do not supply physical length calibration or a measured head-fixed pivot.
Do not require perpendicular axes or silently move the clicked points into an ideal shape.

Keep this four-point reference distinct from T10's live three-landmark observation.
In particular, medial points are not assumed to equal left/right base, and the anterior
point is not automatically a head centre or rotation pivot. These are directional
annotations, not confirmed widest-edge or base endpoints. [Contour-to-triplet extraction](contour-landmarks.md) uses them to resolve axis/side
signs; manual mode uses separately supplied live-landmark coordinates. Supplying
references alone does not establish runtime readiness or detection accuracy. Automatic detection
may observe new mantle coordinates; T05 manual geometry remains explicitly fixed.

Do not derive or enlarge T16's search rectangle implicitly from the subject points.
A reference point may lie outside the pose search crop while still lying in the acquired
image; the eventual extraction method must validate its actual required visibility.
T20 adds no dynamic crop, new model output, template matching or locomotion estimator.

## Common landmark coordinates

[PoseLandmarks](../cephvr/tracking/v1/pose.proto) keeps its three required named fields.
[T21](../../docs/architecture/tracking.md#t21) binds their exact meanings:

| Payload field | Anatomical/UI/model-annotation label |
| --- | --- |
| `tip` | Posterior mantle tip |
| `left_base` | Left anterior mantle tip |
| `right_base` | Right anterior mantle tip |

Use that same order for the ONNX triplet, manual settings, selected candidates and saved
observations. Existing field names are stable aliases, not a different anatomical model.
Image rotation does not reorder animal-left/right by screen x. T20 reference annotations
remain separate; anatomical location alone does not prescribe a contour extraction rule.

Pixel centres use the selected acquired image, before tracking crops/resizes: (0,0) at
top-left, x right, y down. This is the acquisition ROI image, not implicitly the full
sensor. Source identity and prepared acquisition ROI/layout belong to the existing
selected-source contract; model crops do not redefine that identity.

All coordinates must be present, finite and within [0,width-1] and [0,height-1]. Zero
is a valid coordinate. Invert the declared crop/resize/letterbox transform before
publishing pose. Do not clamp off-image detections into valid geometry. Reject coincident
base points, tip equal to base midpoint, and collinear triplets. Automatic geometric
limits are typed in [method-bindings.md](method-bindings.md); estimator-specific gates
remain with T12/T04. Invalid observations retain T09's
invalid disposition rather than a manufactured triplet.

`pose.manual` maps to TrackingSettings.manual_pose: `image_width_px`, `image_height_px`
and `landmarks` with named `x_px`/`y_px` entries. Dimensions must match Setup's selected
source. Manual coordinates are authored in Configuration against the selected camera's
preview geometry and checked against the actual prepared source during Setup; changing
camera ROI, binning or orientation requires revalidation and fresh Setup.
Automatic observations reuse PoseLandmarks alongside T09 source/timing/generation evidence.
Optional method confidence and contours are diagnostics, not extra required landmarks or
fabricated confidence=1 for manual input. Landmark coordinates require explicit input.

Under [T22](../../docs/architecture/tracking.md#t22), automatic geometry derives position,
orientation and both dimensions from the same T09-selected valid observation. The anterior
midpoint is the arithmetic mean of left_base/right_base. The longitudinal span is its
Euclidean distance from tip; anterior-tip separation is the left_base/right_base distance.
These reuse the method-quality distances. Keep these measured spans distinct from
T23's derived ellipse diameters; never overwrite them with extrapolated shape dimensions,
fixed session dimensions or coordinates from an older pose.
T22 introduces no filter or inference of a fixed head pivot; T09 still invalidates dependent
movement when geometry is missing, invalid or stale. Manual geometry stays session-fixed.

## Reference ellipse and region-distance units

[T23](../../docs/architecture/tracking.md#t23) selects a 2D reference ellipse constructed
from the three anatomical landmarks. The same pure function serves manual and automatic
pose. It requires neither a hand-drawn polygon nor live full-contour segmentation. This
shape guides sampling geometry; it does not replace anatomical observations or establish
an exact body boundary, physical calibration or 3D ellipsoid.

[T25](../../docs/architecture/tracking.md#t25) adopts the initial proportional construction:
M=(left_base+right_base)/2, d=|M-tip|, headward axis (M-tip)/d, w=|right_base-left_base|.
Longitudinal diameter is d/f, lateral diameter w, and centre tip+(M-tip)/(2*f).
The posterior tip is at the posterior longitudinal endpoint; the anterior landmarks do
not generally lie on the curve. f=geometry.front_fraction defaults to 0.60, with explicit
saved values preserved; require finite 0<f<=1 and bounded finite output geometry.
Reject degenerate/oversized geometry; never clamp dimensions into an apparently valid body.
Adjust against the Configuration preview overlay before Setup; Setup only validates
the frozen value. No fixed pivot follows.
[T28/T29 sampling geometry](geometry.md) derives a tapered-superellipse outline and
uniform-distance band from this reference; it does not change the ellipse formula.
[T27](stages.md) makes this a replaceable initial geometry method.

[T24](../../docs/architecture/tracking.md#t24) binds relative distances to the measured
d and w above, not the extrapolated ellipse diameters: longitudinal_fraction*d and
lateral_fraction*w. For example, a lateral fraction of 0.10 denotes 10% of anterior-tip
separation; this is an illustration, not a default. Recompute pixel distances with each
T09-selected eligible geometry; retain the configured fractions unchanged. Manual mode
uses its fixed triplet. T30 scales both T29 uniform-distance offsets by anterior-tip
separation; do not apply separate x/y scaling to that distance metric. T30 also records
body-following width (anterior-posterior) and height (left-right), rotated into the image.
The sampling construction and its remaining fields are owned by [geometry.md](geometry.md).
T26 below binds acquired-image clipping independently of those choices.
Body-axis-to-VR mapping and locomotion interpretation stay with the estimator discussion.

## Analysis-region coverage

T26 clips each requested analysis mask against the full acquired image and logs its
coverage; there is no separate visibility threshold. GeometryEvidence records
requested_pixels, visible_pixels and clipped_fraction per region; requested support must
be nonempty. T44's single per-section gate divides accepted flow area by the intended,
pre-clip area, so clipped pixels count as missing. Compute coverage
on the intended image-pixel mask before flow-grid subsampling or numerical-quality gates.
Use one declared pixel-centre inclusion rule consistently for requested/intersection masks.
Do not pool regions, fill missing pixels or shift/shrink the intended region to manufacture
coverage. Bound mask construction and off-image support accounting during preparation.

Empty visible support or a failed support gate invalidates the dependent result; VR
follows existing hold behavior. Clipping alone does not interrupt the session, and
clipping can bias sampling. Record coverage whenever a region is evaluated, through
the geometry stage's typed compact evidence. No region evaluation means an absent geometry
evidence payload, not invented zero/full coverage. Native method errors retain E06.
The pose-search rectangle and clipped silhouette candidate rules remain separate.

## Search rectangle and candidate selection

`pose.search_region` maps to TrackingSettings.pose_search_region. Supply all four integer
pixel fields x_px/y_px/width_px/height_px in the acquired-image reference frame. The crop
covers columns [x,x+width) and rows [y,y+height). Width/height must be positive and the
right/bottom edges no greater than the prepared image dimensions; use checked arithmetic.
Missing, fractional, negative or out-of-bounds fields fail validation. Do not clip them
silently. Full-image search is the explicit rectangle (0,0,image_width,image_height).
The adopted rectangle is locked to Setup's selected source/layout. Changing acquisition
ROI/binning/orientation or search settings requires fresh Setup and validation.

Crop on private/read-only leased input according to T01/T08/T09. The model's additional
resize/letterbox transform is composed with this crop and inverted once for output.
Validate candidate landmarks within the searched pixel-centre bounds before ranking;
never clamp out-of-search detections. No qualifying candidate is an invalid observation,
not permission to move or enlarge the search region. Manual mode can retain inactive
search settings but neither requires nor executes the automatic search.

Each method returns quality-qualified candidates with the common named landmark triplet
and a finite scalar ranking score whose documented ordering is higher-is-better. Reject
non-finite or geometrically invalid candidates before selection; method-specific minimum
quality checks must not be bypassed merely because a candidate has the highest score.
Do not assume a threshold-method geometric score is interchangeable with a model score.
Method formulas and threshold fields are bound in [method-bindings.md](method-bindings.md).

Choose the maximum score. Break exact-score ties by lexicographically ascending acquired-
image coordinates in the fixed sequence (tip.x,tip.y,left_base.x,left_base.y,right_base.x,
right_base.y), rather than provider enumeration or remembered identity. Identical triplets
with identical scores are equivalent selections. Do not introduce a near-tie epsilon or
reject ambiguity instead of applying the accepted highest-score policy.

The compact observation records qualified candidate count, selected score (absent with
no selected candidate) and whether an exact top-score tie required the geometric rule.
Its selected triplet, method and prepared settings identify that rule's inputs; dense
candidate images/contours remain excluded by T15. Automatic candidates are selected
without reference to previous pose identity. T09 independently selects which completed
observation may feed movement; it does not change within-image candidate selection.
A change in the winning candidate is not evidence that the same animal was followed.

## Fixed threshold segmentation

[T18](../../docs/architecture/tracking.md#t18) maps `pose.threshold.level` and
`pose.threshold.polarity` to the selected ContourSettings.threshold_level/foreground_polarity. Require both only
for automatic threshold_contour. Polarity is exactly `dark` or `bright`; no unspecified
fallback. Manual/keypoint modes may retain inactive settings without executing them.

Prepare grayscale through T01/A01 conversion with declared channel order, coefficients
and effective native intensity range. The level is a finite scalar in that same range;
for an unsigned B-bit code representation, 0 <= level <= 2**B-1. Allow zero and fractional
levels where the prepared grayscale representation supports them. No per-image min/max
normalization, auto-exposure-like threshold adjustment or preview 8-bit scaling is implied.
A change in effective depth or grayscale conversion invalidates preparation.

Within the fixed search rectangle, dark foreground means intensity <= level; bright
foreground means intensity > level. Produce a Boolean mask; storing the comparison
result as bytes does not reduce the source image's effective precision. The source
comparison remains in its declared representation. Reject invalid prepared ranges or
non-finite input as method input errors, rather than clamping or silently repairing them.

The mask feeds contour extraction, candidate geometry/quality gates and T17 selection.
Do not add adaptive/local thresholding, background images or stateful learning. Contour
extraction/scoring follow [method-bindings.md](method-bindings.md); tip/base construction
is bound in [contour-landmarks.md](contour-landmarks.md). A mask alone cannot establish a valid pose or Ready.

## Prepared ONNX session

[method-bindings.md](method-bindings.md#onnx-adapter-one-exported-tensor-contract) owns
the sole supported export/asset layout, preprocessing, provider preparation and native
resource rules. Reuse the loaded session across trials under T08/T09. Central E04 metadata
keeps permitted filenames/resolved settings; detailed asset/provider evidence belongs in
tracking's prepared evidence and saved scientific header. Training/export remain external;
no model loading/export or scientific file validation runs between trials.

## Detailed bindings and remaining geometry

[Method bindings](method-bindings.md) and [pure method schemas](method_models.py) define
model assets/tensors, preprocessing/output mapping, provider placement, contour selection
and quality settings. [Record schemas](records.md) bind observations and pose-use evidence.
Shared analysis geometry and [contour-to-triplet construction](contour-landmarks.md)
are declared. T20 labels resolve directions without supplying the detected coordinates;
runtime methods and their estimator integration remain to be built against the
[complete pipeline declarations](pipeline-catalogue.md).
Hardware capability, accuracy and workload tuning remain rig verification.
