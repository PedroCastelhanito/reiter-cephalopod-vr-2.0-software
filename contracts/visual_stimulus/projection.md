# Visual Stimulus calibrated surface projection contract

Governing rule: [V15](../../docs/architecture/visual_stimulus.md#v15). Coordinate semantics follow
[V14](../../docs/architecture/visual_stimulus.md#v14), state ownership
[V07](../../docs/architecture/visual_stimulus.md#v07), and final-output capture
[E13](../../docs/architecture/visual_stimulus.md#e13). This is a declared contract, not a renderer
implementation or evidence of optical/timing accuracy.

Output participation never modifies the four-surface geometry, fixed observer,
viewport, correction mesh, mask or overlap weights. Render only mappings targeting
enabled outputs; omit disabled outputs without redistributing their coverage.

## Geometry and projection mathematics

Use the generalized perspective construction documented by
[PsychoPy](https://psychopy.org/api/tools/viewtools.html#psychopy.tools.viewtools.generalizedPerspectiveProjection),
based on Kooima's method. Implement the mathematical helper in CephVR's lightweight
geometry layer; using this reference does not embed PsychoPy's runtime. Any copied
implementation must retain its applicable license/attribution.

Give each surface a stable ID and ordered bottom-left, bottom-right, top-right and
top-left corners in one physical rig coordinate frame, viewed from the observer
side. Bottom-face orientation is explicit in its corner order, not inferred from
its name or a hard-coded wall rotation. Use millimetres consistently for rig
geometry, physical observer position and clipping distances; conversions from
other units occur at input boundaries. PsychoPy's documented API uses metres;
reference comparisons must convert all length inputs consistently.

For a validated rectangular surface, let `pa`, `pb`, `pc` be bottom-left,
bottom-right and top-left, and `pe` the physical observer position. Define:

```text
visual_stimulus = normalize(pb - pa)
vu = normalize(pc - pa)
vn = cross(visual_stimulus, vu)             # toward the observer
va = pa - pe; vb = pb - pe; vc = pc - pe
d = -dot(va, vn)
l = dot(visual_stimulus, va) * near / d
r = dot(visual_stimulus, vb) * near / d
b = dot(vu, va) * near / d
t = dot(vu, vc) * near / d
```

Construct the standard OpenGL asymmetric perspective matrix from `l,r,b,t,near,far`.
The view matrix has rows `visual_stimulus,vu,vn` with translation `-dot(axis,pe)`; its forward
view direction is negative Z. Use column-vector mathematical transforms
`clip = P * V * M * point`. Distinguish mathematical convention from NumPy storage:
serialize explicitly in the column-major layout expected by the shader. Calculate
geometry in float64; perform the explicit GPU representation conversion at upload.

Validate finite inputs, consistent units/corner winding, nonzero extents,
orthogonal in-plane axes, coplanarity and the fourth-corner rectangular closure
within declared geometry tolerances. Require `d > 0`, `0 < near < far`, `l < r`
and `b < t`; reject degenerate/behind-surface observer geometry. Do not silently
repair a skew quadrilateral, guess observer height or copy old rig dimensions.
Measurement tolerances and clip values require concrete configuration bindings.
Projector keystone/warp belongs to the output mapping, not skewed physical corners.

## Render execution and output mapping

At each render update, select one trial time, apply pending transitions/results and
freeze the effective state used by all four surface passes. Share prepared meshes,
textures, programs and instance state; do not create four independent simulations
or processes. Physical observer inputs must also be consistent across the passes.
Resolve and validate the fixed physical observer position during Setup, then
precompute the surface view/projection matrices. Keep that physical position and
calibration unchanged throughout the prepared session; a different physical
position requires fresh Setup. Do not use tracking results to move this reference.
Virtual movement can change the world transform without rebuilding these matrices.
Virtual-arena pose changes the shared world-to-rig transform, and must not be
silently substituted for the physical observer used to calibrate the views.

For 2D content, use the declared physical-surface or visual-angle interpretation
under V14. Views of one continuous pattern share its coordinate definition and
phase. Drawing to multiple faces alone does not define how an authored physical
pattern wraps around a corner; its mapping must be explicit in the stimulus schema.

Compose each surface using the [single-arena and ordered-overlay contract](scene-composition.md).
Map those images to configured output viewports using the
[imported static mesh/mask/weight binding](geometric-correction.md).
Validate surface coverage, unique identities, output dimensions and declared
mapping coverage before Ready. Do not assume one surface per physical device or
require an extra output for an uncovered tank face. Final physical-output images
remain the capture source under E13, including when one output contains several
surface regions. Required output failures retain E06; mapping flexibility does not
permit silently omitting a required surface.

Projection math assumes straight viewing rays. Required optical corrections for
the real tank must be represented by calibration; these equations alone do not
establish accuracy through its optical path. Shared frame state also does not
establish synchronized projector scanout. Retain V10/V13's distinct per-output
submission and recording evidence.

## Remaining work and verification

Virtual-arena constraints follow [V16 and its contract](arena-movement.md).
Geometric correction scope and composition semantics are bound by the contracts
above. Complete typed calibration/output schemas, GPU/resource lifecycle and
presentation interfaces remain local contract work. Rig
corner/observer measurements, optical calibration, edge alignment and full-load
presentation timing retain their hardware-input/verification deferrals.

Later implementation checks must cover off-center observers, all four face
orientations, corner-to-viewport projection, consistent edge rays, invalid geometry,
unit conversion and matrix-upload conventions. No behavioral checks, renderer
implementation or rig measurements have been performed by this declaration.
