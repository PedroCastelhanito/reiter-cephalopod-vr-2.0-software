# Relative planar locomotion output

Authority: [T35–T38](../../docs/architecture/tracking.md#t35), under T04/T12/T27.
This contract binds calibrated channel meanings without claiming estimator accuracy.
The owner explicitly includes sideways movement in the initial scope.

## Channel identity and meaning

| Channel | Positive direction | Negative direction |
| --- | --- | --- |
| forward_drive | Anterior/headward drive | Posterior/mantle-tipward drive |
| sideways_drive | Animal-left lateral drive | Animal-right lateral drive |
| turn_drive | Turning toward animal-left | Turning toward animal-right |

Coordinates are anatomical body coordinates. Preserve the T20/T21 side labels through
camera orientation/mirroring and T30 body rotation; image-positive x/y does not define
control polarity. Camera-measured flow, a mantle pose change, relative locomotor drive
and virtual-observer movement remain distinct quantities. In particular neither a
lateral optical-flow component nor unequal side activity automatically establishes a
valid sideways or turning estimate; the selected method must define those inferences.

These are relative control signals, not measured swimming speeds in mm/s or physical
animal turning rates. T38 selects direct method units without a normalization layer, reference
range or physical conversion. T37 fixes quantity=interval_average_rate; the concrete
water-flow units are bound in [water-flow-proxy.md](water-flow-proxy.md); fin-flow explicitly reuses those units under [T04](fin-flow.md). No vertical/pitch/roll channels are selected. A missing/unidentifiable
component cannot be represented as an apparently valid zero.

## Temporal quantity and direct scale

All three drive channels declare quantity=interval_average_rate and coordinate_frame=
anatomical_body. Their declared method units describe rate-like relative controls;
channel names alone never imply physical velocity. Each valid result identifies its
valid source interval [t0,t1), dt=(t1-t0) in seconds, with t1>t0 and the existing lineage.
Use the Visual Stimulus feedback contract's existing interval-average-rate integration without a
second formula or integrator in tracking. Gains have virtual-speed units per declared
drive unit; the integration offset has virtual-speed units. Visual Stimulus retains ownership of
epoch attribution, overlap/reset gates and application of the source interval.

The estimator must state how its measured input produces an interval-representative
rate. If its measurement starts as displacement, conversion to rate uses the declared
source interval exactly once, not a nominal camera/render FPS. A history window used
for a fit is not permission to repeatedly integrate that entire window. Do not append
unobserved time to late results, fill source gaps or coast using remembered drive.

T38 supplies method output directly to the gain: no reference-amplitude division,
recent-activity normalization or mandatory [-1,1] scaling is inserted at this boundary.
Native encoding conversion and operations intrinsic to the declared estimator remain
allowed and explicit; this rule does not change T33/T34 measured-input ownership.
T45 binds water-flow exponential smoothing and its filtered interval average in
[water-flow-proxy.md](water-flow-proxy.md). No deadband, saturation, inertia or numeric
gain default is selected here.

## Visual Stimulus mapping and recording ownership

Reuse [Visual Stimulus feedback](../visual_stimulus/feedback.md) and its existing stimulus-program bindings for
gain, offset, target compatibility and source-interval integration. Units are spelled
as Visual Stimulus input units: forward/sideways mm/s bind together through heading_relative_planar_integration
to arena x/y (virtual mm per input mm); turn deg/s binds by movement_integration to arena yaw
(virtual deg per input deg). T20 camera endpoints/known mm are mandatory for enabled
Tracking. T38 divides pixel-space filtered translation by acquired-image pixels_per_mm
and converts angular radians/s by 180/pi exactly once before feedback publication.
Retain original estimator evidence. Old input declarations and gains require explicit
operator edits; no gain migration or historical-file relabeling occurs. Do not add a second
tracking-owned copy of those Visual Stimulus gains. Mapping relative drive into virtual metres or
radians does not make the input a physically calibrated animal velocity. Gain values
remain explicit program settings with existing epoch/program ownership; this decision
adds no numeric defaults or live configuration exception.

The estimator's channels use the existing PreparedMethods.channels declarations and
tracking-result transport. Validate the three required channel identities,
quantity=interval_average_rate, coordinate_frame=anatomical_body and each selected
method's explicit unit/gain compatibility before Ready. Retain separate source evidence, derived controls and Visual Stimulus-applied changes
through existing compact records and source/result links; introduce no duplicate log
or dense-data output. T09/A06/V25 retain invalid/reset/hold behavior, without remembered
velocity, invented zero motion or integration across missing source intervals.

## Complete initial binding

Both options use the response units, quality method and filtering bound in the
[pipeline catalogue](pipeline-catalogue.md), with distinct evidence and independently
resolved settings. It registers the actual initial channel declarations, settings,
evidence and connections. Fin selection/support remain owned by [fin-flow.md](fin-flow.md).
Runtime construction is still required before Ready. Numeric gains/tuning and scientific
verification remain outstanding; no further fin-wave choice is required. T27 permits
later alternatives without treating the initial proxy as proof of scientific accuracy.
