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
A plain image offers `fit: resize|source|fold` under V04/V14. Resize fills the valid
screen rectangle with the complete image; Source selects original pixels using
independent per-axis centered crop/padding. For source size S and target T, the
retained extent is min(S,T), source start floor((S-min(S,T))/2), and destination
start floor((T-min(S,T))/2). Padding is transparent to the underlying scene; odd
surplus goes right/bottom in top-left image coordinates. These fits override the
authored position, extent and motion with the selected screen's fixed rectangle;
opacity remains effective. Resolve native valid-area dimensions and source-axis
orientation from the prepared rectangular affine calibration; reject sheared/nonlinear profiles during
Setup. Preserve downstream calibration/masks/blackouts/color and marker processing.
Evidence records actual mapped clip vertices and per-mapping image target pixels.
New GUI Images write Resize. Existing `contain|cover|stretch` values retain their
authored bounds and movement; omitted legacy values remain Stretch. Looming retains
its existing size animation and default Stretch behavior. Source sampling uses
original texels; the subsequent calibration/display path is not a claim of optical
pixel equality. No source asset is rewritten, downsampled or memory-cropped.
Fold uses one unfolded source, anchored at its top-left, with Bottom in output
orientation below a top-aligned Left/Front/Right row, centered over Front. Net
extents use calibrated surface millimetres, including disabled/unselected screens.
One source pixel represents the Front output's X/Y mm-per-pixel, derived from its
physical surface and rectangular calibration derivatives (not resolution alone).
Each target's calibration maps its fixed valid rectangle into that shared field;
no per-screen fit or recenter occurs. Out-of-image samples are transparent; unused
source pixels are cropped. Front must have exactly one prepared mapping (its output
must remain enabled, but need not show the image). Missing Front, nonrectangular
mapping, or incompatible orientation fails preparation. Bottom uses quarter-turned
axes; other faces and the Front reference use landscape axes. Physical preservation
is within calibration, resampling and optical limits, not a claim of exact statistics.
`image_fold_map_<mapping_id>` records three float32 vec2 values: source top-left-pixel
coordinates at local quad UV=(0,0), and the increments for local U and V. The shader
samples original image coordinates with the selected image sampling filter.

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

A 2D physical surface uses its centre as local origin, with right/up axes in mm
defined by the calibrated corner vectors (the corners themselves stay in rig
coordinates); `±extent/2` are its edges. Each selected surface has one nonsingular 2x3 affine
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

Epoch authoring metadata includes optional `batch_label` (empty by default) and
`batch_id` (null by default). Under [V03](../../docs/architecture/visual_stimulus.md#v03),
the latter distinguishes GUI generation actions within a parent group even when
labels match. Neither field changes compilation order, timing or rendering. Preserve
both in source/prepared-source JSON; individual epoch edits retain batch membership.

## Direct Media layers

`TextureSettings.uniform=true` declares independent stationary zero-contrast color,
with linear `mean_linear_rgb`, an asset-free procedural pattern and opacity/fades.
The renderer extends its physical rectangle over the selected surface.

Direct `grating=true` uses `sine_grating` with positive constant `frequency=1/period_mm`
and `feature_sharpness` in [0,1]. Center the signal at the rectangle center:
`a=0.5+0.5*cos(2*pi*(frequency*x_centered+phase_x))`; blend `a` with a centered
smoothstep of half-width `(1-sharpness)/2`, weighted by sharpness (sharpness 1 uses
an exact step). Convert `2*blend-1` using the existing linear mean/modulation/contrast.
Sharpness 0 is sinusoidal and 1 square. This centered convention applies only to
marked direct Grating; legacy unmarked procedural patterns keep their definition.
The epoch's absolute rotation assignment is the single bar-normal orientation;
Cartesian speed follows that normal. Existing marked image-tile Grating remains
asset-backed and uses its declared source interpretation.

`ImageSettings.sparse_noise` contains `asset_ids`, exact positive `pattern_duration`,
optional validated `appearance` for direct authoring, and `background_linear_rgb`.
Its initial asset equals the first sequence member; all members are declared PNGs,
nearest sampled with physical stretch on one surface. Select
`min(floor(max(0, epoch_local_ns)/duration_ns), count-1)` at each evaluation; keep
actual requested/selected image evidence through normal residency holds. The authored
epoch is not split, so other layers' animation/video/motion clocks stay unchanged.
The sequence starts again at each epoch occurrence; excess patterns are truncated,
and exhaustion holds the last. Background composites inactive alpha before layer
opacity; residual complete-grid margins retain the underlying scene.

## Reference-shared grating pattern and phase

A marked direct Grating may link only to another independent marked direct Grating
on a different physical surface in the same frame. Its reference owns appearance,
period, orientation, motion and phase; follower settings remain dormant independent
values until unlinking. Chaining, cycles, feedback and competing follower motion fail.

Use calibrated surface right/up/inward-normal bases. Unfold each surface around
its plane intersection with Bottom by the shortest rotation of its inward normal
to Bottom's, using Bottom's calibrated center/right/up as the common origin/basis.
Evaluate the reference's mapped, rotated, translated centered grating coordinate at
each follower point. Derive follower frequency, local orientation and phase from that
affine coordinate; copy the reference waveform/color coefficients and use the same
logical time. Reject opposite normals and singular/reflected stimulus mappings;
output warp/flips remain independent. Bottom-edge phases agree for coincident physical
edges. Constant spacing is preserved; arbitrary patterns can have wall/wall corner
seams around the closed tank. No global 3D-field or projector frame-lock is implied.

Resolve exact derived phase into existing follower state at epoch boundaries before
unlink/reset handling (V07). Unlinked Gratings remain independent. These rules do not
change the motion-only Texture drift links below.

## Reference-linked texture motion

`TextureSettings.linked_to` is an optional active reference instance ID in the same
resolved epoch. The reference is independent and both endpoints are physical,
single-surface image tiles. Each follower retains its own image, tile periods,
appearance, initial/retained phase and reset choice. Its authored phase and layer
motion are holds; the reference supplies constant phase drift, constant mapped
X/Y layer translation, or constant rotation. Phase drift and layer translation
cannot compete. G01 rig-fixed translation uses the latter with phase motion held.
Chains, cycles, self/same-screen links, animated tile periods, simultaneous drift and
spin, motion/period assignments and motion/period feedback on either endpoint are
invalid. Constant values may be condition-selected; validate each expanded occurrence.
Appearance feedback follows the existing writer rules. Missing/disabled output
presentation never renormalizes geometry or moves a reference to another screen.

Construct calibrated unit surface right/up/inward-normal bases. Let `F_i` be the
shortest rotation from surface normal `n_i` to Bottom's inward normal. For linear
motion convert source phase cycles/s to local texture mm/s using its own periods and
retained orientation, invert its physical map, then transport `F_target^-1 F_source v`.
For mapped X/Y layer translation, use its rates directly before the map inverse;
do not rotate them by layer orientation.
Convert into the target's map, retained orientation and periods to obtain its phase
rates. Antiparallel-to-Bottom normals and nonuniform/sheared/reflected stimulus maps
are unsupported; output warp/reflection is separate and remains supported.

For source angular rate `a` in rad/s, let `c` be the reference screen center
(midpoint of its calibrated bottom-left and top-right corners) and let
`d = dot(c - target.bottom_left_mm, n_target)` be the signed perpendicular
rig distance to the target plane. Subject/observer position is not an input. Then
add physical velocity `a*d*(n_source cross n_target)`; target spin is
`a*(n_source dot n_target)`. Rotation linking requires parallel/perpendicular planes,
with accepted near-zero/unit dot products clamped to exactly zero/signed one.
This preserves V02's Bottom/side convention. It is a coordinated-flow definition,
not a rigid-body rotation or seamless texture wrap.

The source pivot for spin must equal its calibrated screen center: local `(0, 0)`
transformed into its stimulus plane (the physical map’s translation components).
Carry known center positions through compiled transition actions; uncertain prior
position writers require an explicit reset before spin linking. Fail Setup with the
required coordinates if unknown/mismatched. Recheck actual retained centers during
boundary binding. The surface-local origin is the surface centre (V14), matching the renderer, so this
feature does not change projection or move authored textures.

Bind followers after all epoch state transitions, using actual retained rotations.
The existing state fields integrate the derived constant rates analytically; no new
per-frame synchronization, phase owner or frame-delta integration is introduced.
Drift→hold, source changes and unlinking preserve target state unless V07 requires
an explicit reset or incompatible-resource restart. GUI **Linked to** selects the
reference and disables target movement controls; **Independent** releases the link
with zero drift, ready for explicit editing. Advanced initial-center controls allow
the required spin pivot to be authored.

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
unrestricted movement, a strictly convex CCW XY polygon plus nonnegative wall margin,
or `arena_file` plus finite nonnegative `margin_mm` (GUI default 30 mm).
Rectangles are four-vertex polygons, with no second equivalent box representation.
Arena-file mode reads `extras.cephvr.metadata.geometry` from the protected GLB:
`shape: rectangular` with `width` and `depth` (legacy `height` when depth is absent),
or `shape: convex_polygon` with 3–1024 strictly convex CCW `vertices_mm`. Dimensions
are millimetres; omitted shape means rectangular, but dimensions have no fallback.
Unsupported shapes/missing geometry reject Setup. Apply the declared planar affine
asset-to-world transform, reverse reflected winding, and require the same resolved
region for every use of the trial instance. Prepared artifacts contain the resolved
polygon, never `arena_file`; asset fingerprints retain source provenance. Preserve
explicit protocol regions without consulting metadata. Convert polygon edges once into outward unit
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

Subgroup authoring metadata: optional `subgroup_draft` defaults to null. The GUI stores
one record on the first member of a batch: `enabled` and up to 64 `rules`. A rule
retains projector scope, local layer ordinal (-1 for all), parameter, method (0 Values,
1 Sweep, 2 Random), entered values/range/precision, explicit `shared` choice, and
seed and sample key (legacy cached values remain readable). The canonical model bounds these text/list fields. This
metadata is not evaluated by the compiler; canonical settings and repetition rules remain authoritative.

Optional epoch `repetition_settings` defaults to an empty tuple/list. A nonempty table
contains one complete Settings list per immediate enclosing group repetition (at most
2000 rows). Every row must match the epoch scene's active instances and pass the same
asset, function, feedback and condition-reference validation as ordinary settings. A
root epoch cannot carry a nonempty table. V08 expansion indexes this table by the
immediate group's zero-based repetition index before substituting conditions; it
does not select by shuffled visit position or use random draws at runtime.

`VariationDraft.rig_coordinates` and `RepetitionRule.rig_coordinates` default to
false for saved-source compatibility. Both carry `rig_angle_version` (1 or 2,
default 1). New GUI rules write true and version 2: Direction is
Right0/Front90/Left180/Back−90 in the rectangular rig's unfolded plane, and Speed
uses the existing declared distance/time unit. Rig edits write mapped X/Y rates
and hold texture phase rates. Legacy rules retain their local phase conversion.
Version 1 retains Back0/Right90/Front180/Left270, including the Back default when
adding speed to a stationary source. Version 2 displays angles in (−180, 180];
wrapped inputs are equivalent. An instance's Speed and Direction repetition rules
must agree on the flag and, for rig coordinates, angle version.

Optional epoch `repetition_rules` defaults to an empty list and cannot coexist with a
legacy table. Each `uniform_grid_v1` rule identifies an active instance and numeric
parameter, inclusive minimum/maximum/precision grid, 32-digit hexadecimal seed,
stream, nonnegative offset and positive stride. For repetition r, index = r × stride
+ offset. SHA-256 of UTF-8 `cephvr.uniform-grid.v1:{seed}:{stream}:{index}` seeds
Python Random (digest interpreted as a big-endian integer); randrange selects one
uniform grid index. Independent targets use distinct streams; shared targets reuse
one stream. Expansion resolves after condition substitution and validates concrete
settings before compilation. The rule declaration is constant-size with respect to
repetitions; Setup's configured expanded-plan limit still applies before sampling.

Asset repetition rules use `kind: uniform_asset_v1`, `parameter: Asset`, an active
`instance_id`, and an ordered `asset_ids` list of 1–2000 distinct declared compatible
media IDs. Every candidate is checked, including candidates not selected for the
representative occurrence. Image/video/image-tile texture settings are supported;
procedural patterns and arenas reject Asset rules. Other layer settings are retained.
The seed, stream, offset and stride have the same meanings as numeric rules. Hash
UTF-8 `cephvr.uniform-asset.v1:{seed}:{stream}:{index}` with SHA-256; seed Python
Random from the big-endian digest and select `asset_ids[randrange(len(asset_ids))]`.
Sampling is uniform with replacement and independent of numeric/order/duration
streams. Source count is unchanged; concrete asset IDs appear in prepared occurrences.

Non-executable variation drafts retain `folder` and `asset_ids` for GUI restoration,
with `method: 2` for both random modes. New fields default to empty for legacy drafts.
The folder is an authoring hint, never scanned during Setup or rendering. G01 saves
compatible files directly in the selected folder in deterministic filename order,
imports external sources through the normal Assets-root mechanism, and retains the
snapshot when reopening. Asset declarations use the normal portable paths and media
validation. Editing another rule or the repetition count preserves the existing seed
and prefix. Missing `kind` on legacy numeric rules retains `uniform_grid_v1` semantics.

### Grating stimulus

A `texture` setting with `grating: true` is G01's Grating stimulus; omission/false
preserves ordinary Texture interpretation. It requires an independent physical
`image_tile`, `cephvr_grating_json_v1` asset references, hold phase/rotation functions
and constant Cartesian motion. Only Asset, Orientation and nonnegative Speed are
editable. Orientation uses current rig directions; zero speed retains the angle.
The absolute `rotation` assignment stores the local normal to the bars and applies
at every V07 boundary. Drift remains parallel to that normal in the selected sense;
reject misaligned/custom/linked or feedback-driven Grating declarations.

The numeric `Orientation` repetition parameter is available only for Grating. It
updates both drift and the rotation assignment; it does not create source epochs
or resample another rule. `uniform_asset_v1` Grating rules additionally contain
`grating_periods_mm`: one positive finite physical period per ordered candidate ID.
Resolution updates image-tile X/Y periods together with the chosen asset. Other
families omit that tuple. Authoring drafts retain the same tuple for reloading.
Missing fields on older drafts/rules retain their prior semantics. The new asset
profile's decoding contract is in [asset lifetime](asset-lifetime.md#grating-recipe-interpretation).
