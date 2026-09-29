# VR output precision and quantization

Governing rule: [V20](../../docs/architecture/vr.md#v20). Working color is fixed by
[V04](color-pipeline.md), measured tables by [V23](photometric-calibration.md).
This binds the final software output representation, not measured display precision.

## Requested versus observed representation

Each adopted physical output configuration supplies `rgb_bits_per_channel`, exactly
8 or 10. All three channels on that output use the same value; outputs may differ.
No default, automatic best-format selection or silent downgrade is selected. Output
IDs remain independent of surface IDs and window enumeration order. Preserve saved
explicit values; changing one requires fresh preparation and compatible calibration.

Before creating its window, request the matching GLFW RGB component depths. Once the
correct OpenGL context/default framebuffer is current, query its actual red, green
and blue attachment sizes and component type. Require the requested unsigned
normalized representation and exact component depths, not merely a successful window
creation or GLFW hint. Check actual framebuffer pixel dimensions against the adopted
output dimensions as well; logical window size/DPI scaling is not that evidence.
Unsupported/unqueryable/mismatched results block startup Idle or Setup, with partial
resource cleanup under E08/V19. Never publish Ready after silently obtaining RGB8
for an RGB10 request. Alpha-channel storage does not establish RGB precision.

Retain output identity, requested bits, observed channel sizes/component type and
framebuffer dimensions in prepared output evidence; match V23 profile RGB bits to
those exact values. Its refresh/device/operating-condition checks remain required.
Revalidate resources replaced by a fresh Setup; known context/device loss invalidates
the affected prepared output and follows required-backend failure handling.
[Canonical display configuration and typed control evidence](worker-control.md) bind these fields; only the validated canonical schema may cross the JSON transport boundary.

## Final code boundary

After linear composition and the selected V23 output branch, clamp finite normalized
device codes to [0,1] with V21 evidence. For b in {8,10}, use M = 2^b-1 and
q = floor(clamp(code,0,1)*M + 0.5). Carry the final integer code q, or the exact
declared q/M representation, to the final output path. A later attachment write
must not introduce a different code quantizer. Use an appropriately matched owned
final-image attachment for recording/presentation rather than downconverting every
output through a shared 8-bit intermediate.

Disable renderer-side GL_DITHER and unintended GL_FRAMEBUFFER_SRGB conversion on
final code writes; there is no selected spatial/temporal dithering mode. This does
not control hidden driver/projector processing. Earlier texture sampling, scene
composition and measured-table interpolation retain float32; choosing RGB8 does
not replace the accepted float32 working pipeline or normalize source images.

The scientific replay record retains the output representation, pipeline version
and actual effective render state. Offline reconstruction applies the same output
quantization. Lossy video conversion may use its explicitly selected recording
representation under E13; it cannot alter live framebuffer selection. Save Off does
not bypass presentation/calibration validation or change precision.

Requested/queried RGB10 proves a software framebuffer format only. Retain available
signal configuration separately; do not claim a 10-bit cable/projector path, physical
luminance steps or absence of external processing from the GL query. Those checks
remain deferred to the rig. Validating 16-bit input and float32 composition does not
increase a physical output's independently selected precision.

Binding reference: [GLFW window/framebuffer hints](https://www.glfw.org/docs/latest/window.html).
Implementation must verify actual attachment queries, format mismatch cleanup,
code preservation through presentation/capture and both precisions on the target
platform. No display runtime or rig result is delivered by this contract.
