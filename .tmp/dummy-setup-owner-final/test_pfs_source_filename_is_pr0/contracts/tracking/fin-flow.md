# Initial fin-flow binding

Authority: [T04](../../docs/architecture/tracking.md#t04), F1A/F2A. This contract binds
sampling and explicit reuse of the numerical proxy, not a running or validated estimator.

## Shared geometry and angular selection

The common stage constructs the full [ellipse-derived band](geometry.md) from the same
eligible pose. The downstream fin estimator intersects it with one body-following angular
wedge; water_flow still uses its full band. Use fin-specific resolved geometry values to
place the band over visible fin tissue. Do not infer fin membership from being inside a
geometric mask or run an added edge/wave/tissue classifier.

FinRegionSettings (schema tracking.fin-region-settings.v1) has exact schema_version=1,
offset_degrees in [-180,180) and span_degrees in (0,360], both finite and required with
no defaults (rig/subject inputs). Embed this subset in the selected fin estimator settings; operator input is
estimator.fin_region. It is not a new worker or independent StageConfiguration. An active
water estimator rejects fin-region fields; inactive saved configurations remain separate.

Use the T25 reference ellipse centre and the pose's anatomical orthonormal basis. For
pixel-centre displacement from that centre, let x point anterior and y animal-left.
Let theta=degrees(atan2(y,x)), and delta=((theta-offset_degrees+180) modulo 360)-180.
For span<360, select -span/2 <= delta < span/2. Span=360 selects the complete band.
The zero-radius centre is not a band sample. Positive offset follows animal-left,
independent of camera mirroring. Do not silently clamp invalid values. Numerical mask
construction is vectorized on CPU and participates in the existing geometry cache.

Retain the full-outline [equal-arc section labels](sectioning.md), posterior origin,
anatomical direction and section count. Intersect each section with the wedge; do not
repartition a shortened outline, renumber sections or treat angular width as arc length.
Compute intended selected support before image clipping. The required section set is
exactly those sections with nonzero intended selected raster area. Empty total selection
is invalid. A section entirely outside the wedge is excluded, not a failed observation.
A selected section entirely outside the acquired image is required and fails support.
Recompute this set for changed eligible shape/selection; report its section IDs and areas.

For each required section apply the shared single gate: accepted represented flow area /
selected intended (pre-clip) area >= minimum_accepted_area_fraction. Clipping is logged
per section (T26) but has no separate threshold; clipped pixels count as missing. Every
required section must pass; one failed section invalidates all three controls. No empty
denominator or absence of required sections can pass.
Flow-cell intersection and split area accounting use exactly the proxy contract with
band replaced by selected band. No vector duplication, early averaging or interpolation.

## Shared numerical response, distinct evidence

Use the same numerical implementation as [water-flow-proxy.md](water-flow-proxy.md):
source-dt conversion, anatomical coordinates, native validity/cost handling, normalized
local-median screening, represented-area weighting, negative mean translation, negative
centred angular turning rate with its second-moment validity gate, all-required-section
support, exponential interval-average smoothing and reset behavior. Do not copy the formulas into a second method body or policy table.
Compute the global centroid over accepted selected support, not independently per wedge
section. Screening neighborhoods must respect the selected fin support under the shared
quality binding; never borrow surrounding-water samples solely to pass support.

Units (px/s, px/s, 1/s), quantities and Visual Stimulus gain compatibility are identical to the shared proxy. Fin and
water configurations resolve their own region, section, quality, support, smoothing and
Visual Stimulus gain values; sharing code/fixed policy does not copy numerical tuning. Configuration
changes require fresh Setup; no simultaneous pipelines or automatic method switching.

Retain pipeline_id=fin_flow, the prepared fin selection and exact shared implementation
identity/version with the existing scientific header and compact method evidence. Label
sample means/moments as fin image motion, not measured water motion. Required section
IDs, selected areas, rejection dispositions, raw controls and filter evidence use the
same compact schema structure with explicit evidence-source identity. Dense images,
flow, masks and histories remain transient. This creates no second log or wave record.

The adopted signs and proxy are an explicit experimental control mapping, not a claim
that fin texture displacement measures swimming speed, thrust or intent. Opposing or
oscillating fin motion can cancel; scientific adequacy is tested later. No rectification,
phase/frequency estimator, body-motion subtraction or hidden sign adaptation is introduced.
T27 permits replacement after testing without changing lifecycle/ownership contracts.

## Shared bindings and implementation

The [pipeline catalogue](pipeline-catalogue.md) embeds FinRegionSettings in the complete
FinFlowSettings and binds shared screening, compact evidence and worker connections.
Only declarations are registered; runtime and scientific/whole-rig verification remain
outstanding under E15. Fin-region angles remain explicit operator inputs; other numeric
settings take the tracking_config defaults unless saved values exist.
