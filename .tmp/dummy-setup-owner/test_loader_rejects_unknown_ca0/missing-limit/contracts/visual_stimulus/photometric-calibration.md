# Visual Stimulus photometric calibration contract

Governing rule: [V23](../../docs/architecture/visual_stimulus.md#v23). Projection geometry remains
under [V15](projection.md), finite clipping under [V21](output-range.md), and asset/
provenance retention under [V13](replay.md). The [canonical profile model](photometric_profile.py) and its
[generated JSON Schema](photometric-profile.schema.json) declare and validate profile
data. Runtime file loading and GPU application live under `src/cephvr/visual_stimulus`; the
[Visual Stimulus report](../../reports/visual_stimulus.md) records implementation checks. Physical verification
remains pending on the rig.

## Explicit mode and readiness

Resolve one explicit session mode, calibrated or uncalibrated, alongside the output
configuration during Setup. Preserve an explicit saved selection and lock the mode
at Start. Before first Setup, [startup Idle](startup.md) uses these same mode/profile
checks against the adopted saved display settings; recheck them during Setup.
Do not infer uncalibrated mode from missing files, use a guessed gamma
value, or change modes after a profile/runtime failure.

Calibrated mode requires a compatible measured profile for each required physical
output. Validate the profile's identity, format/version, numeric correction data,
output binding and recorded operating conditions against the prepared configuration.
Malformed/missing data or a known mismatch blocks readiness. Profile calibration
dates/provenance are retained; do not invent an automatic expiry duration. File
validity and configuration correspondence cannot prove current physical accuracy.

Uncalibrated mode bypasses measured photometric compensation explicitly. Standard
asset transfer functions, alpha/compositing interpretation and geometric projection
still apply. Do not relabel this mode as linearized physical light or match brightness
across projectors by assuming identical device-code values produce identical light.
A missing/invalid profile requested in calibrated mode never silently selects this
mode. The operator changes the selection through ordinary configuration and fresh
Setup; an active session cannot downgrade itself.

## Application and provenance

The renderer owns prepared correction resources per output and applies the declared
color/output pipeline consistently to stimuli, Idle and the photodiode patch.
Apply the [color pipeline](color-pipeline.md): compose in linear RGB, then apply
three per-channel inverse-response tables once to produce final device codes.
Use this same path for stimuli, Idle and photodiode levels; no additional gamma
encoding follows a calibrated table. External display processing must correspond
to the profile's declared operating conditions and remains an optical verification
obligation. This is not support for arbitrary calibration formats.

## Profile and interpolation binding

Use the canonical Pydantic profile model and regenerate its schema when structure
changes. The schema alone cannot enforce equal lengths, monotonic curves, distinct
condition names or output compatibility: call the pure semantic validator as well.
Unknown fields/versions, duplicate keys, nonfinite values and implicit type coercion
are rejected. Profile identity is descriptive; V13 SHA-256 identifies actual bytes.

Each curve contains N >= 2 equally spaced input samples x_i = i/(N-1), all three
curves sharing N. Samples are normalized device codes in [0,1], finite and
nondecreasing, with final > initial. Plateaus are permitted for quantized response;
a constant channel is not a usable RGB calibration. The curve is an inverse mapping
from requested normalized channel intensity to device code, not measured luminance
as a function of code. Black-to-white normalization describes each channel's measured
usable range; it does not equalize maximum light or chromaticity across projectors.
Endpoints need not be device codes 0 and 1. No runtime fit, sorting, extrapolation or
repair of measurements. External calibration may use an appropriate measurement/fit
method to produce the stored tables; the runtime consumes the resolved tables only.

For clamped linear x, let u=x*(N-1), j=min(floor(u),N-2), w=u-j;
return (1-w)*curve[j] + w*curve[j+1]. At x=1 this returns the last sample exactly in
the declared arithmetic. Use float32 table values and explicit two-sample interpolation
(e.g. texelFetch on a three-row R32F texture) rather than relying on unspecified
texture-filter precision. Validate the uploaded float32 representation remains finite,
monotonic and nonconstant. Table shape/capacity must fit the prepared GPU budget;
there is no guessed fixed table length or calibration-value default.

Bind a profile to stable output/device identity, exact dimensions, refresh rational,
uniform RGB8 or RGB10 under [output precision](output-precision.md), full-range
RGB signal and named operating-condition values. Compare
these with the adopted output configuration before Ready/startup Idle; rational
refresh comparisons use value equality, not rounded Hz strings. Required condition
names are those declared in the photometric profile's own `conditions` list, which
must be non-empty with unique names, so an empty list cannot bypass relevant settings. Mark manual conditions as operator declarations,
not verified readback. Missing required information, mismatches, unsupported signal
paths or unresolved bit-depth selection block calibrated preparation. No automatic
profile fallback, expiration date, 3D color matrix/LUT or spatial correction is added.

Measurement provenance identifies UTC time, method, instrument and measurement
reference. These are supplied measured facts, not generated defaults; parsing them
does not prove the experiment's current optical response. Protected profile bytes
and prepared tables follow V04 asset lifetime. Hold their immutable generation until
resource release, including across trials. Replay uses the matching retained profile
identity/content and interpretation, never the newest file with a matching name.

During preparation, evaluate the configured photodiode high/low RGB levels through
the selected output mapping and quantization; require distinct final code triplets.
Distinct codes do not prove an adequate measured optical signal. If a measured table
or output quantization collapses the two levels, reject the configuration instead of
inventing new levels or changing the six-frame marker sequence. Levels stay rig inputs.

## Retained provenance and verification

Expose the chosen mode in GUI/headless configuration and current state. Retain mode,
output/profile associations and correction-relevant settings in active Visual Stimulus setup
provenance, with V13 content fingerprints/replay-specific records under its save
scope. Uncalibrated labeling persists in retained metadata; choosing that mode does
not cause repeated per-frame warning messages. Calibrated profiles remain external
assets under V13, without automatic copying into the session.

Changing profiles or operating conditions requires fresh validated preparation.
Known invalid runtime correction data/failures use E06; ordinary finite output-range
excursions retain V21's clip-and-log behavior. Measurements, projector settings and
optical validation remain rig-deferred. Later implementation checks cover mode
selection, profile mismatch, missing files, no silent downgrade, per-output mapping,
recording/replay provenance and unchanged geometry in uncalibrated mode. No such
behavioral or rig checks have been performed.
