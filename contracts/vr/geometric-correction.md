# Imported geometric output correction

Authority: [V15](../../docs/architecture/vr.md#v15). This binds a static correction
representation after off-axis surface rendering; it does not select an automatic
calibrator, a physical optical simulation or measured rig values. The one renderer,
four direct surface views and fixed calibrated physical observer remain unchanged.

## Mapping ownership and representation

Each prepared surface-to-output mapping identifies its source surface, destination
physical output/viewport and an imported versioned calibration mesh. Store it with
rig/output configuration, separately from trial stimulus programs and V23's measured
photometric tables. A mesh maps source surface-image coordinates to destination pixels;
it does not alter arena geometry, virtual pose, stimulus phase or physical rig corners.

Use a regular rectangular topology of control points triangulated with one documented
cell diagonal. Each vertex carries normalized source image UV and normalized output-
viewport XY. Prepare the triangle/index arrays once. Source/destination origins are
bottom-left, x right and y up; file importer orientation changes must be explicit.
A concrete file schema must retain row/column counts, row-major vertices, mapping
identities, output pixel dimensions, viewport, format version and calibration identity.
No shader code, arbitrary executable mapping function or dynamic mesh editor is part
of the imported profile. The [generated profile schema](geometric-profile.schema.json) and [runtime binding](runtime-bindings.md) define its typed representation.

GPU rasterization interpolates source UV within those destination triangles and samples
composed linear float surface images. This is a calibrated approximation whose
resolution/accuracy must be checked; it does not promise exact nonlinear optics from
an arbitrary coarse grid. Mirror/back-projection mappings must be explicitly declared
in profile interpretation and validated as consistently oriented, not inferred from
face names or repaired by a guessed flip. An explicit identity profile is permitted
when intended; missing calibration never silently becomes identity.

## Masks, weights and assembling outputs

Optional static masks and overlap weights are scalar calibration fields in output-
viewport coordinates. Each is finite and within [0,1], with its exact sampling/grid
interpretation in the prepared profile. An absent optional mask or weight means one;
this mathematical identity supplies no rig calibration measurement. Inputs use V04's
protected source/preparation rules; do not gamma-decode weights as image colors.

Clear each physical output's linear composition target to black. For each validated
mapping, add its sampled linear RGB multiplied by its mask and overlap weight.
Declared overlaps therefore sum weighted contributions, independently of draw order.
Do not automatically renormalize weights, estimate seams, change stimulus contrast or
apply source-over a second time to these already composited opaque surface images.
Unmapped or fully masked pixels stay black. An intentional masked area is distinct
from a missing required surface/mapping. Validate declared intended coverage and
reject unexplained gaps or duplicate/conflicting mappings during Setup.

V21 still records/clips finite output-range excursions at the established boundary;
invalid/nonfinite calibration fails preparation rather than being repaired by clipping.
Weights do not prove equal projector brightness or physically uniform overlaps.
The [color pipeline](color-pipeline.md#per-output-stage-order) places the reserved
photodiode patch after this spatial mapping/masking stage, then applies the selected
photometric correction and output quantization once. Required patch placement cannot
be hidden by scene masks. E13 captures the resulting final physical-output images.

## Preparation, failures and provenance

Setup verifies exact source/output/viewport identities and dimensions, finite vertices,
positive grid extents, valid UV/range declarations and bounded resource requirements.
Reject zero-area triangles, folded cells, unintended self-overlap or inconsistent
orientation. Adjacent shared vertices must agree. Check required coverage and mask/
weight dimensions with the same mapping. The [canonical artifact model](artifact_models.py) checks local topology; [runtime-bindings.md](runtime-bindings.md) defines the additional coverage/intersection pass. That pass remains runtime implementation work.

Protect/read the profile and dependencies, validate, upload and bind its immutable
prepared resources before Ready. Keep the mapping, masks and weights fixed for the
prepared session, including across epochs/trials. A change invalidates readiness and
requires fresh Setup; no trial-time file watching, calibration recomputation or profile
swap. Renderer owns GPU resources; cleanup follows E08. Missing/unsupported or
incompatible required calibration blocks preparation with exact mapping identity.
Photometric Uncalibrated mode does not waive this geometric mapping requirement.

Retain profile version/content identity, source/output associations, sampling rules,
mesh topology, mask/weight references and explicit orientation in V13 provenance.
Keep the immutable calibration definition, or verified immutable references sufficient
for replay, under its existing recipe/manifest mechanism; do not invent a second log
or silently depend on the current mutable calibration file. External-source retention
still follows V13. Record the selected profile even when its mapping is identity.

Rig measurements must establish whether a mesh and fixed observer adequately correct
the real tank/projector optical path. Mesh resolution, calibration inputs, edge/overlap
quality and actual GPU cost stay unverified. No runtime ray tracing, automated camera
calibration or guaranteed refraction correction is implied by accepting this profile.
