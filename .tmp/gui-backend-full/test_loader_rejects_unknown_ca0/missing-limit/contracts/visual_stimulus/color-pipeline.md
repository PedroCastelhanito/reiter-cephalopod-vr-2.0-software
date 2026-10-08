# Visual Stimulus linear color and output pipeline

Governing rules: [V04](../../docs/architecture/visual_stimulus.md#v04), [V21](output-range.md)
and [V23](photometric-calibration.md). This declares a single pipeline for stimuli,
arenas, Idle and markers. Implementation and validation limits for shaders, GPU
resources and presentation are recorded in the [Visual Stimulus report](../../reports/visual_stimulus.md).

## Source interpretation and working values

Use linear Rec.709/sRGB primaries with D65 white and dimensionless relative RGB
intensity as the working space, identified as `linear_rec709_d65_relative`. These
values are software targets, not calibrated cd/m2 or a guarantee of cross-projector
color matching. Authored numeric stimulus colors/intensities use this space; GUI
color-picker sRGB values must be converted explicitly and shown with their units.
Source image/video encodings are independent of authored numeric parameters.

Resolve source transfer function, primaries, matrix/range (for YCbCr), alpha and
orientation at Setup. Initial direct interpretations are linear Rec.709, sRGB and
BT.709 transfer with the same primaries. Use the inverse declared transfer, not one
guessed gamma for all media. For example, sRGB E becomes E/12.92 for E <= 0.04045,
otherwise ((E+0.055)/1.055)^2.4. BT.709 uses E/4.5 below 0.081, otherwise
((E+0.099)/1.099)^(1/0.45). Do not label BT.709-coded values linear by dividing by 255.

Resolve YCbCr range expansion, matrix and chroma location before inverse transfer;
retain the effective conversion. Unsupported primaries/ICC/HDR or ambiguous metadata
require a supported explicit interpretation or external preparation, not ignored
tags or silent sRGB substitution. The loader must distinguish absent metadata from
contradictory metadata and record explicit resolutions in prepared/replay provenance.
glTF base-color texture RGB uses its standard sRGB interpretation; vertex colors and
base-color multipliers use their specified linear values. No inherited legacy gamma.

Preserve supported 8/16-bit samples through decode and conversion. Normalize against
the declared component range, never the frame's observed min/max. Use float32 or
better for color conversion and float32 RGBA working textures/attachments (RGBA32F)
for composition. No intermediate 8-bit conversion or RGBA16F substitution. Final
output quantization is a separate explicit boundary, not an input-precision claim.
Check GPU attachment/blending/filtering capabilities and aggregate memory at Setup;
failure blocks preparation rather than silently choosing a lower precision.

## Alpha, filtering and composition

Alpha is linear coverage, never gamma-encoded. Resolve straight versus associated
source alpha explicitly. For associated source samples, undo association in their
declared encoding before inverse transfer; zero-alpha pixels have zero premultiplied
color. Reject ambiguous association instead of guessing it. Once in the working
space, store premultiplied color c = alpha * RGB. Apply RGB multipliers and opacity
consistently; opacity scales both c and alpha.

Decode transfer and form premultiplied values before interpolation and mipmap
construction. Do not bilinearly filter encoded straight-alpha samples and then
pretend that the result equals linear premultiplied filtering. Static resources can
be prepared once; video conversion remains bounded and tied to source identity.

Use source-over in the [accepted scene order](scene-composition.md): opaque background,
optional single arena, then bottom-to-top 2D layers. Arena depth does not apply to
2D overlays. For each overlay:
c_out = c_src + (1-alpha_src)*c_dst;
alpha_out = alpha_src + (1-alpha_src)*alpha_dst.
Equivalent GL blend factors are ONE and ONE_MINUS_SRC_ALPHA. Standard depth behavior
and V04's supported arena material profile remain; this does not add general 3D
BLEND-material sorting. Compose onto the program's opaque background so final RGB
requires no arbitrary unpremultiply against an unknown desktop background.

Validate nonfinite values as errors. Finite excursions retain V21: clamp coverage
at the `alpha` boundary before premultiplication and record affected output frames;
keep finite RGB intermediates unclamped through composition until the declared
output boundary. Avoid implicit clamps in attachment formats or hidden color-space
conversion. Predictable excursions warn during Setup; they do not rewrite programs.

## Per-output stage order

1. Evaluate shared stimulus state and compose surface views in linear float32 RGB.
2. Apply the [imported static geometric meshes](geometric-correction.md), optional
   masks and overlap weights in linear space to assemble the physical output image.
   This follows V15's off-axis views; it does not replace the physical geometry.
3. Overlay the reserved photodiode patch in final output coordinates using its
   explicit linear RGB high/low levels and opaque coverage. It follows scene/spatial
   masking so a scene cannot obscure it. Outside trials use V19's uniform Idle.
4. Clamp finite composed RGB to [0,1] at `linear_output`, retaining V21 evidence.
   Do not normalize the frame, invent headroom or alter the authored contrast.
5. In Calibrated mode, apply each output's measured inverse-response table once.
   In Uncalibrated mode, apply standard sRGB encoding to the same linear values:
   12.92*L for L <= 0.0031308, otherwise 1.055*L^(1/2.4)-0.055. This is an explicit
   signal encoding, not measured photometric correction or a physical linearity claim.
6. Check finite device values and clamp to [0,1] at `device_code`; then quantize to
   the explicitly resolved per-output 8/10-bit representation. Record that representation and
   reproduce this same boundary offline. No automatic additional gamma, tone mapping
   or precision downgrade. [Output precision](output-precision.md) binds explicit 8/10-bit
   selection, framebuffer checks and nearest-code quantization.

For a calibrated output, table results are already final normalized device codes:
do not apply the sRGB encoding from the uncalibrated branch afterward. Disable
unintended GL_FRAMEBUFFER_SRGB conversion on the final code-writing pass; working
attachments also remain linear. Renderer-owned correction must not be duplicated in
another CephVR stage or an unaccounted OS gamma ramp. Prepare/query applicable state
and retain known external signal settings; software cannot prove the projector or
compositor did not change the signal. Such behavior is checked on the rig.

The final review-recording source remains the same renderer-produced output image
under E13, including patch and correction, before external display processing.
Codec color conversion for that image is a separate recording binding; do not label
measured projector device codes as standard sRGB simply because the uncalibrated
branch uses sRGB. Replay uses the retained interpretation, effective tables and
output representation, not current machine defaults.

## Evidence and limits

Keep distinct V21 flags for `alpha`, `linear_output` and `device_code`. Attribute
source/material excursions to outputs that actually use them; required flags may
arrive asynchronously but retain frame identity. Rounding within range is not a
clipping event. Profile validation rejects malformed table data; clamping a corrupt
profile is not recovery. Existing loss/failure and Save Off summary rules remain.

A half-opaque linear white layer over black yields 0.5 linear RGB before correction.
The uncalibrated sRGB signal is approximately 0.73536; calibrated codes depend on the
measured table. Neither number alone proves physical luminance. The pipeline version,
source interpretations and output bindings belong in existing V13 provenance.
Physical transfer, GPU numerical behavior, four-output throughput and full replay
remain unverified; no original-output pixel fingerprints are introduced.

References: [sRGB conversion](https://www.w3.org/TR/css-color-4/#color-conversion-code),
[OpenGL formats/blending](https://registry.khronos.org/OpenGL/specs/gl/glspec46.core.pdf).
