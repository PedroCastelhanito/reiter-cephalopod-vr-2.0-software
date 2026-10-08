# Stimulus vocabulary and compiler binding

Authority: [V02–V08](../../docs/architecture/visual_stimulus.md#v02), [V14](../../docs/architecture/visual_stimulus.md#v14),
[V16](arena-movement.md), [V24–V27](motion-composition.md). The canonical source is
[program_model.py](program_model.py), with generated [program.schema.json](program.schema.json).
The complete prepared artifact is [PreparedTrial](prepared-trial.schema.json) in
[artifact_models.py](artifact_models.py). These are declarations and partial pure
validators; the compiler/runtime semantic passes below must still be implemented.
Do not claim structural parsing alone is full program validation or Ready.

## Required family settings and coordinates

All required fields in each selected settings variant follow V02. Empty feedback
and assignments explicitly mean none; `hold` explicitly means no programmed writer.
A plain image may specify `fit: contain|cover|stretch` under V04. Omitted legacy
values preserve Stretch; new GUI Images write Contain explicitly. Fit acts within
the authored width/height rectangle before projection, with transparent margins
for Contain and a centered source crop for Cover. Looming remains an image with
size animation and keeps its existing default Stretch behavior.
A numeric condition reference is legal at a Number position only. AssetChoice also
permits a typed asset_id column. Other structural enums, spaces, counts and scene
membership are literal. Resolve all reachable row combinations at Setup; reject
numeric/asset/unit mismatches at both cell and receiving setting paths. No overrides,
implicit products, callbacks or condition lookup during execution.

| Family | Complete appearance/resource block | Live state |
| --- | --- | --- |
| Image | asset, sampling, 2D space/extent/opacity | centre and rotation |
| Video | image fields plus initial playback and explicit end behavior | centre, rotation, playback |
| Texture | pattern, extent/opacity, mean/modulation RGB, contrast, spatial frequency or tile periods | centre, rotation, x/y phase |
| Arena | GLB, asset-to-world transform, world frame, planar initial pose, fixed height/pitch/roll | planar x/y and yaw |

A 2D physical surface uses bottom-left origin, right/up local axes measured in mm
from calibrated corner vectors. Each selected surface has one nonsingular 2x3 affine
map from those coordinates into the explicitly declared common stimulus plane.
The map may intentionally align/mirror adjacent faces; no face-name guess changes signs.
The instance centre, extent and image x/y are in that plane; positive rotation is
counterclockwise viewed along its positive normal. Image/video UV x increases right
and y up after prepared source-orientation correction; clamp at the image edge,
with a hard rectangular extent and transparent exterior.

Visual-angle space uses the fixed physical observer and a unit xyzw quaternion from
local angular frame to rig frame. Local +X is right, +Y up, +Z forward. For each surface
point, rotate its normalized observer ray into that frame; x = atan2(ray.x,ray.z),
y = atan2(ray.y,hypot(ray.x,ray.z)), in degrees. This is an explicit longitude/latitude
mapping, not a guessed planar mm-to-degree conversion. The declared active footprint
must avoid its pole and wrap discontinuities; reject an unsupported crossing during
Setup. Author another explicit frame to move the seam. Validate every listed surface
and every reachable footprint/function envelope before Ready.

Width/height use mm or deg and must stay positive; opacity/contrast are dimensionless
[0,1]. Rotations use deg; texture phases use cycle and spatial frequencies cycle/mm
or cycle/deg (nonnegative); tile periods use mm/deg (positive). Pure validation checks
always-attained values (constants, knots, ramp initials, condition cells) against the
catalogue's `PARAMETER_RANGES`; resolved-duration extrema remain a compiler pass. Sine grating is cos(2*pi*(frequency*x + phase_x)),
square grating is +1 when that cosine is >=0, -1 otherwise. Checkerboard multiplies
corresponding x/y square signals. Procedural RGB is mean + contrast*modulation*signal;
finite over/under-range values follow V21 clipping, not automatic normalization.
Image tiles repeat local x/period_x + phase_x and y/period_y + phase_y; their RGB is
mean + contrast*modulation*(2*sample-1), alpha from the source times opacity. Pattern rotation
uses the same 2D transform. Mean/modulation RGB are linear coefficients, not gamma codes.
No stochastic texture plugin or hidden phase reset is introduced.

## Functions, clocks and checks

The four supported function variants are constant, ramp `initial+slope*u`, sine
`mean+amplitude*sin(2*pi*(frequency_hz*u+phase_cycles))`, and linear/step keyframes.
Their output unit comes from the receiving parameter and selected coordinate space.
Functions and assignments do not repeat unit fields. Ramp slope has that unit/s; sine frequency
has Hz and phase has cycle. Keyframes start at zero and increase strictly in exact
integer nanoseconds. Step interpolation is left-held and right-continuous at knots.
V05: evaluate only up to the epoch boundary; after the last knot hold its value.
Never stretch a curve to fit a sampled duration. Retain each cut-short curve's path,
last-knot time and actual duration in CompiledEpoch.truncated_curves for the timeline.
Compute exact piecewise integrals for supported rates (analytic ramp/sine and
piecewise linear/constant), splitting at knots and epoch boundaries; no frame-delta
Euler integration for unconstrained motion. Sine frequency is nonnegative; zero is
valid. Check function extrema on each resolved duration, not only knot endpoints.

The [fixed parameter catalogue](parameter_catalogue.py) owns supported units, rate units
and feedback source/target pairs. The editor shows the receiving unit; the compiler
resolves it once. No generic unit-expression parser, dimensional algebra or implicit
conversion is required. Numeric condition columns and input channels still declare
units. Every coefficient reference must match its destination, including ramp slope,
sine frequency and phase. Feedback gain columns use the finite `feedback_gain`
descriptor (input unit, output unit, value/slope coefficient); literal gains derive this
from the binding. Asset-ID condition columns have no unit. Unsupported pairs fail validation.
Static program inspection checks all reachable values; duration-dependent ranges use
resolved occurrences. Parser limits precede recursive validation; canonical JSON input
is used for files and control payloads, with duplicate keys and nonfinite tokens rejected.

A rate is an incremental writer and a trajectory an absolute writer; `hold` is none.
For direct feedback to appearance (opacity/contrast/extent/frequency), require the
corresponding authored function to be constant and mark it as the initial/held value;
it is not another concurrent animation. Direct feedback to state requires its motion
variant to be hold. Reject an animated function plus direct feedback, competing direct
bindings, absolute trajectories plus increments and unit/frame alias conflicts under
V27. Movement integration targets state only. `heading_relative_planar_integration`
is one incremental writer of both arena x and y; frame rules are in [feedback.md](feedback.md). Assignments apply once at boundaries,
with units matching the selected target; playback assignment is an exact decimal Time seek with
prepared media support, not reverse playback or a new time-varying playback-rate mode.

## Arena scope and boundaries

V16: world axes are +X right, +Y forward, +Z up. Continuous programmed/feedback motion
supports x/y in mm and yaw in deg, counter-clockwise about world +Z: +yaw turns the
observer's forward toward its left. At yaw psi (radians) the observer's forward unit
vector is f=(-sin psi, cos psi) and its left unit vector l=(-cos psi, -sin psi).
Tracking anatomical_body channels are animal-left-positive for sideways and turn (T36). Height/pitch/roll are explicit fixed
settings for each epoch and apply at its boundary; they have no feedback/rate writer.
Initial x/y/yaw applies only on first activation/reset/incompatibility. Compose orientation
as Rz(yaw)*Rx(pitch)*Ry(roll), acting on the base +Y-forward camera frame. Scalar yaw
increments compose about the same world axis; never add quaternion components.
All four projected views use the same resulting virtual pose and fixed physical geometry.

[TrialArenaBoundaries](arena-boundaries.schema.json) is a separate protocol binding:
exactly one entry for every used arena instance, with matching world frame, explicit
unrestricted movement or a strictly convex CCW XY polygon plus nonnegative wall margin.
Rectangles are four-vertex polygons, with no second equivalent box representation.
GLB metadata cannot set boundaries. Convert polygon edges once into outward unit
halfplanes, inset offsets by margin, intersect and reject an empty allowed region.
Keep the supplied vertices/margin in the prepared recipe. Reject initial/reset/boundary
assignments outside the inset region; no snapping. Height/pitch/roll do not change XY
boundary membership. A boundary definition is fixed for that trial's instance.

Sweep each ordered requested XY displacement to first wall contact; project the residual
onto the feasible tangent cone of all simultaneous contacts using the minimum Euclidean
change, without renormalizing speed. In 2D compare unconstrained residual, each feasible
wall tangent and zero, using stable edge-index tie order. Continue for remaining motion,
with at most edge_count+1 contacts; numerical failure interrupts, fully blocked is valid.
Use configured positive geometry tolerances and reject inconsistent residuals, rather
than creating a free-running iterative solver. A curved programmed path is segmented at
its analytic wall intersections and function extrema; the implementation must provide
bounded conservative root isolation within preparation limits. Unsupported/unbounded
path combinations fail Setup, never silently use a chord that bypasses boundaries.
Replay uses recorded effective poses, not a new collision simulation.

## Compatibility, expansion and prepared artifacts

Stable instance ID/family is mandatory. Compatible state requires unchanged coordinate
interpretation and resource identity: image/video asset, texture pattern variant/tile
asset, or arena asset/asset-to-world/world frame. Rate/contrast/extent, feedback gains,
video hold/loop and fixed arena height/pitch/roll changes do not reset retained x/y/yaw
or phase/playback. Spatial-frequency/tile-period changes retain phase in cycles, with
the resulting appearance change explicit. Incompatible changes restart from the new
initializer and are flagged in the prepared timeline. No hidden state conversion.

Count group repetition/row products with checked integers before allocating; reject
above max_expanded_epochs. Bind parser depth to 64 for this recursive authoring grammar,
while callers may impose a smaller limit. Ordering stream `cephvr.order.v1`, independent
of the duration stream: for each group occurrence, seed a separate CPython `random.Random`
with `int.from_bytes(sha256(b"cephvr.order.v1:" + seed + b":" + path).digest(), "big")`,
where `seed` is the UTF-8 canonical decimal trial seed (no leading zeros, except `0`) and
`path` is the UTF-8 group occurrence path: one `group_id[repetition_index]:unit_id` segment
per enclosing group visit, then this group's ID, joined by `/`. Paths use IDs, not positions:
adding/reordering other groups leaves a group's order unchanged for the same seed;
renaming a group or unit changes it. Expand nested groups
depth-first in authored order. Its repetitions consume that one stream in order; for each
`shuffle_each_repetition` repetition apply explicit Fisher–Yates to the authored unit IDs
(child-block or row IDs): for i from n-1 down to 1, j = randrange(i+1), swap i and j.
Do not call `random.shuffle`. `as_listed` consumes nothing. Retain exact Python/random
implementation compatibility and actual order; replay never resamples.
The duration stream and Stafford sampler remain exclusively defined in durations.md.
No fallback sampler is authorized. Validate exact total, bounds and E05 minimum.

PreparedTrial includes the complete source snapshot, resolved settings for each occurrence,
lineage/truncation, transitions, display/boundaries/resources, uniform layouts and compatibility
identities. Tables may share immutable storage in memory; serialized values are self-contained.
Use compact UTF-8 JSON with sorted keys and no NaN; SHA-256 covers exact retained bytes.
Integers stay integers, no float timestamps. The transport carries this canonical artifact,
with no parallel PreparedSchedule payload. Derive local indexes/timeline summaries from
that artifact once; never transmit or reconcile a second schedule. The compiler returns
PreparedTrial alone, including its manifest. Retain its exact bytes once per started
trial in the OutputPlan-reserved `_stimulus_LOG.json`, independently of the save switch.
Preparation remains in bounded memory at Setup; publication follows the trial boundary
in runtime-bindings.md. Central control/logs carry its verified identity and compact
summary; the complete artifact stays inside Visual Stimulus under E08's message bound.

Compiler pass order: parse/reference checks → bounded expansion/condition substitution →
ordering/duration resolution → units/ranges/writers/compatibility → protected resources and
media/index preparation → display/geometry/GPU capability/reservation → complete plan and
transition construction → final size/reference checks → adopted prepared identity. Cancellation
and deadlines use E07/E08 throughout. Mutable state is allocated separately at release.
The compiler interface is [preparation_types.pyi](preparation_types.pyi); GPU/decoder/file
providers remain runtime work, and no declaration implies their behavior is verified.

Prepared-artifact validation additionally requires: unique resolved scene/resource/layout
identities; exact source occurrence lineage and scene settings; condition-free settings;
full active-instance coverage; valid boundary before/after indices and transition actions;
all resource dependencies and uniform layouts; matching display/output sets; and exactly one
tiled-composite review encoding covering every output when saving On (none when Off). Match shared TrialPlan
duration and PreparedHandle content hash/generations. Check limits before materialization.
These cross-document checks are the compiler/Ready adoption boundary, not implied by the
structural Pydantic schema's partial validators. No arbitrary JSON payload is executable.
