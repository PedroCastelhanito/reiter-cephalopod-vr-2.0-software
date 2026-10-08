# Contour landmark extraction

Authority: [T06](../../docs/architecture/tracking.md#t06), L1A/L2B, with T17/T20/T21.
Initial threshold_contour implementation 2 uses ContourSettings v2. This is a concrete
method declaration; no runtime or validated anatomical detector is supplied here.

## Component moments and orientation

Start from each eligible component of the selected threshold mask under
[method-bindings.md](method-bindings.md). Work in acquired-image coordinates and retain
native-source precision during thresholding. Use every foreground pixel of this component,
not all components together, the convex hull, contour-vertex density or an ellipse fit.
Holes/background pixels contribute no mass. OpenCV moments on the binary component with
binaryImage=True supply m00, m10, m01 and central moments; use float64 arithmetic.

The centroid is c=(m10/m00,m01/m00). The population covariance is
C=[[mu20,mu11],[mu11,mu02]]/m00. Crop-local computation is allowed; translate c and contour
coordinates back to source space. Covariance is translation invariant and remains in
source-pixel squared units. Compute eigenvalues lmax>=lmin and the major eigenvector
with NumPy's symmetric eigensolver. Require finite moments, positive mass, nonnegative
eigenvalues and lmax+lmin>0; invalid numerical input cannot become a pose observation.

Require (lmax-lmin)/(lmax+lmin) >= minimum_axis_anisotropy. This explicit finite setting
is in (0,1], with no default. Equality passes; a round/indistinguishable axis is invalid.
It measures orientation identifiability, not anatomical correctness or a probability.
Do not fix orientation to the previous frame, infer it from contour enumeration order,
or insert an unselected temporal filter to make a failed component valid.

Let h be the nonzero T20 anterior-minus-posterior reference direction. Sign the major
unit eigenvector e so dot(e,h)>0. A zero projection cannot resolve anterior/posterior
and invalidates that component. Choose the perpendicular unit vector l whose dot product
with T20 medial_left-minus-medial_right is positive. A zero lateral projection is also
invalid; never derive animal-left from screen x. Only the reference directions are used:
the clicked coordinates are neither live endpoints nor a pivot. This sign rule assumes
the setup reference still resolves the current animal orientation; head fixation is not
proof of that assumption. It does not claim continuous identification through a 180° turn.

## Automatic directional extremes

Use the observed vertices of the existing external CHAIN_APPROX_SIMPLE boundary in
source coordinates. For each boundary point p, define x=dot(p-c,e), y=dot(p-c,l).
The initial deterministic heuristic is:

| Landmark candidate | Eligible boundary points | Selection order |
| --- | --- | --- |
| posterior tip | All component boundary points | Smallest x; then smallest abs(y). |
| left anterior tip | x>0 and y>0 | Largest x; then largest y. |
| right anterior tip | x>0 and y<0 | Largest x; then smallest y. |

If either anterior-side subset is empty, the component is invalid. Final exact ties use
ascending acquired-image (y,x) solely for deterministic selection among equal extrema;
this tie-break does not assign anatomical side. Each output is an actual retained contour
vertex. No midpoint substitution, synthetic ellipse endpoint, extrapolated apex, widest-
section landmark, user search region, curvature detector or subpixel peak fit is added.

Reject nonfinite/out-of-image points, repeated coordinates or triplets failing the common
LandmarkQuality axis-length/base-width/triangle-area limits. Require the derived
posterior-to-anterior-midpoint direction to agree with e and the right-to-left base span
to agree with l. T17 ranks only components with passing triplets, using foreground area
and its existing candidate tie rules. No surviving candidate is an invalid observation;
a native error remains a method failure under E06, not ordinary no-detection.

The final shared geometry is constructed from this triplet under T22/T25, not the mask's
moment ellipse or its search axis. Preserve T09 source identity, completion, validity and
selection age. Mask centroid/covariance are internal extraction inputs; never substitute
those for the common three-landmark pose payload. Dense masks/contours remain transient.

This is a heuristic for the T21 anatomical targets. An arm, fin protrusion or noisy edge
can be an extreme and still pass geometric checks; that does not establish anatomical
accuracy. Validate against labelled rig images. No automated quality gate claimed here
can certify that an observed extreme is the true mantle tip.

## Settings and interfaces

ContourSettings v2 adds required minimum_axis_anisotropy to the existing threshold,
area and LandmarkQuality settings. Its operator source is pose.contour. Old v1 settings
are rejected, not filled with a guessed quality value. The declared registry identity
is pose/threshold_contour implementation 2, settings tracking.contour-settings.v2.
The image and candidate-pose port identities stay unchanged.

ContourCandidate in runtime_types.pyi supplies source-space boundary vertices, pixel
area, clipping flag, centroid and covariance to the prepared ContourGeometry helper.
The pose worker computes these from the same component. Preparation adopts source
layout, subject references and v2 settings once. This helper adds no stage/process,
provider selection or alternative registration. Complete runtime factories and numerical
image tests remain implementation work; schema validity alone cannot establish Ready.
