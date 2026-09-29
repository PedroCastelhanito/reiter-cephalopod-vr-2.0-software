# Initial water-flow proxy

Authority: [T42–T45](../../docs/architecture/tracking.md#t42), under T27/T32–T41.
This is the core mathematical contract, not a runtime implementation or validated
measurement of intent, velocity, force or torque. Core method behavior is accepted;
complete typed evidence/settings and ports are bound in the [pipeline catalogue](pipeline-catalogue.md).

## Samples, weights and frame

Consume [estimator input](estimator-input.md) without mutating it. For every available
provider sample i retain its native acquired-image position, displacement, footprint
and screening disposition. Use the provider adapter's explicitly prepared grid mapping;
do not guess a grid origin, overlap support twice or use a cropped-image pixel scale.
The sampling footprint is the adapter-declared nonoverlapping represented area, not an
optical-flow algorithm's possibly overlapping search window. A mapping unable to define
represented areas fails preparation; actual device/grid mapping still requires binding
and verification in its adapter.

Let a_i be the acquired-image area of that footprint inside the visible raster band.
Under the existing pixel-centre mask, intersect footprints with the unit-area squares
of included pixels. Edge fractions contribute fractional area; count shared boundaries
once. Samples with positive intersection remain available to the estimator. After T41
screening, only accepted samples with a_i>0 contribute to the sums below. Finite zero
flow is an observation, not missing data. Do not weight by speed or confidence after
screening, and do not replace a rejected sample with zero or interpolated flow.

For a common valid source pair use dt=(t1-t0) in seconds from its declared source
interval, not nominal FPS or result-arrival spacing. Convert native displacement to
acquired-image pixels through the provider mapping, then divide by dt exactly once.
Express sample positions p_i and velocities u_i in the anatomical orthonormal basis:
x points anterior, y points animal-left. Use the same eligible pose for this estimate,
retaining its lineage/age. Derive lateral sign from anatomical labels, including camera
mirroring; do not treat the two possibly nonperpendicular annotation vectors as an
oblique coordinate basis. A change of basis adds no body-motion subtraction or pose
velocity. Positions and displacements use the same acquired-image scale.

## Core response and units

For accepted samples define W=sum(a_i), the position centroid c=sum(a_i*p_i)/W, mean
water velocity u_bar=sum(a_i*u_i)/W, centred water moment
m=sum(a_i*((p_i.x-c.x)*u_i.y-(p_i.y-c.y)*u_i.x))/W and centred second moment
J=sum(a_i*|p_i-c|^2)/W. Positive support, positive finite J and the final quality gates
are required; failure produces an invalid result without usable drive values, never
a zero turn. The unsmoothed response is (T45 filters this triplet before publication):

```text
forward_drive  = -u_bar.x
sideways_drive = -u_bar.y
turn_drive     = -sum(a_i*((p_i.x-c.x)*u_i.y - (p_i.y-c.y)*u_i.x)) / sum(a_i*|p_i-c|^2)
               = -m/J
```

Forward/sideways units are px/s (acquired-image pixels/s). Turning units are 1/s
(radians per second); turn_drive equals the negative least-squares rigid-rotation rate
of accepted water velocities about c. All three declare quantity=interval_average_rate
and coordinate_frame=anatomical_body under the [output contract](locomotion-output.md).
The negative signs are the adopted opposite-water-motion inference, not a force-balance
theorem. Positive turning means inferred turning toward animal-left, opposite positive
(anterior-toward-animal-left) water rotation in this basis. Existing VR gains own
conversion to virtual speed: linear gain is virtual mm per input px and turn gain is
virtual deg per radian, each integrated once over the source interval in VR.

Because sum(a_i*(p_i-c))=0, adding any spatially uniform velocity leaves m and
turn_drive unchanged. Subtracting u_bar only within the moment sum is an algebraically equivalent
numerical implementation; it is not ambient-current correction to translation and
never changes measured buffers. Translating all position coordinates also leaves m, J
and turn_drive unchanged. Rejection/clipping can change c and the moment of a nonuniform field;
this invariance is not protection against changing spatial coverage or bad vectors.

## Section integration and evidence

T32 sections remain available for runtime analysis and support accounting. Split each
sample's represented band area into a_ik by intersection with section-labelled pixel
squares, preserving sum_k(a_ik)=a_i. A sample crossing a section boundary remains one
measured vector, with fractional area contributions rather than duplicated independent
measurements. The global response uses each vector once with a_i, not equal weighting
of section means. Compute turning around the global accepted centroid, not a separate
centroid per section; otherwise section moments would not sum to the global moment.

Retain compact accepted area/counts, centroid, water mean, m and J alongside
screening/support dispositions and derived controls in the selected method's existing
scientific evidence; the raw turn equals -m/J evaluated from the recorded float64 values.
T44 binds support below; [FlowProxyEvidence](pipeline-catalogue.md#evidence) binds compact fields. Dense vectors, masks and sample-wise scores remain transient under
T15. Provider-grid density changes neither authorize additional independent measurements
nor establish output equivalence across different optical-flow grid configurations.

## Required section support

All configured T32 sections are required for this initial method. Let V_k be the
section's intended (pre-clip) raster area and A_k=sum(accepted a_ik) its area represented
by T41-accepted samples. Require V_k>0 and A_k/V_k >= minimum_accepted_area_fraction for
every k; equality passes. This single gate covers off-image clipping (T26) and missing or
rejected flow; there is no separate visibility threshold. Use the same explicit fraction
in (0,1] for every section. Clipped pixels, unavailable provider cells, unevaluable local
tests and rejected vectors contribute no accepted area, while V_k remains unchanged.
Empty support or a failing section invalidates all three outputs. Do not substitute the
visible area, an overall-band percentage, available-grid area or accepted-area sum as
the denominator. Shared cell/section intersections are area contributions, not
independent repeated samples.

[SectionFlowSupportSettings](method_models.py) (schema_version=1) binds the fraction;
its operator source is estimator.support.minimum_accepted_area_fraction. It is resolved
at Setup and locked for the session; the tracking_config default is 0.25, a starting
value to tune on the rig, and saved values win. This is an embeddable subset of the
complete estimator settings, not another registered stage. Record V_k, the visible
(post-clip) area, A_k and the configured threshold with compact per-section dispositions.
A scientifically inadequate but numerically passing sample is still possible; this
criterion is not a claim of validated tracer coverage or swimming-intent accuracy.

## Exponential smoothing and source-interval meaning

[ExponentialSmoothingSettings](method_models.py) (schema_version=1) binds positive finite
time_constant_s, operator source estimator.smoothing.time_constant_s. One explicit
value tau in seconds applies independently to all three channels, resolved at Setup and
locked for the session; the tracking_config default is 0.08 s and saved values win. The
filter follows support checks and the raw core response; it is not a provider-vector
filter or another gain layer.

For a contiguous valid interval of length dt, treat its raw drive x as constant over
that source interval. For each channel let y0 be the previous valid interval's filter
end state. Bind the first-order response dy/dt=(x-y)/tau as:

```text
alpha = -expm1(-dt/tau)
y_end = y0 + alpha*(x-y0)
y_average = x + (y0-x)*(tau/dt)*alpha
```

Publish y_average over this interval and retain y_end for the next one. This preserves
T37's interval_average_rate meaning: VR integrates the filtered average once over dt,
not an endpoint mislabelled as an interval average or the entire history window again.
Use numerically stable exponential/series evaluations for very small dt/tau. Arrival
time, pose-completion spacing and renderer FPS do not enter the filter coefficient.
This piecewise-constant drive is a declared approximation to the observed interval;
it does not reconstruct unobserved subframe motion. Output units remain unchanged.

On first valid use after clearing, seed y0=x; both y_end and y_average equal x. This
avoids inventing a zero baseline or a mandatory startup ramp. Invalid input or failed
support clears all three states and publishes no usable drive, not a decaying tail.
Source discontinuity and trial/preparation/processing-generation boundaries also clear the
states; source baselines and reset generations remain owned by A06/lifecycle. Only
adjacent usable source intervals in the same lineage reuse state. Do not manufacture a
flow pair across a gap, preserve stale filter history across invalid observations, or
fill unobserved source time. Duplicate computation never advances state twice. Delivery-
only overflow does not undo a valid filter update or clear state: subsequent contiguous
source pairs continue it even when earlier results were discarded before reaching VR.
Save their calculations/discard evidence under A06; VR never integrates missing delivery
intervals. Actual processing reset or invalid input still clears all filter channels.

Record the raw triplet, filtered average, filter end state and seeded/continued/cleared
disposition in existing compact method evidence when saving, with existing source/result
lineage and prepared tau. The first valid pair after source baseline restoration can
seed immediately; no extra warm-up period or new reset generation is required solely
for smoothing. Closed-loop VR retains its existing invalid/hold and epoch rules.

## Implementation boundary

[Local screening](flow-quality.md) binds W1A/W2A. The [pipeline catalogue](pipeline-catalogue.md)
composes settings/evidence and direct worker connections for both initial pipelines.
Runtime methods remain unimplemented. Numeric rig tuning and scientific/throughput
verification remain outstanding under E15; schema validation cannot establish Ready.
