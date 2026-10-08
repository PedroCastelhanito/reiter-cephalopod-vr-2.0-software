# Visual Stimulus arena appearance contract

Governing rule: [V17](../../docs/architecture/visual_stimulus.md#v17). Renderer ownership follows
[V01/V04](../../docs/architecture/visual_stimulus.md#v04), projection [V15](projection.md), and
actual-state replay [V13](replay.md). This is a declared contract; no runtime or
physical luminance validation is implemented.

## Prepared appearance

Use authored base colors/textures, with any selected vertex-color or material
multipliers explicitly represented in the prepared material. Baked shading is part
of the asset pixels; no runtime light source re-illuminates those pixels. Scene
lights, normal-based diffuse/specular terms, dynamic shadows and reflections do not
participate in the selected shading model. Do not import the legacy renderer's
lighting defaults merely because the geometry or textures are compatible.

Unlit does not mean a screen-space image: arena geometry still participates in
perspective, clipping and depth occlusion. All four views use the same geometry,
material interpretation and evaluated scene state. A face's orientation relative
to a hypothetical light cannot introduce brightness differences across views.

Declare the supported material interpretation during asset preparation, including
base-color channels, alpha handling, texture coordinates, color-space conversion
and any explicit multiplier. Reject required unsupported appearance features during
Setup instead of silently approximating them. Detailed importer/material schema
bindings follow [V18's prepared-asset workflow](arena-assets.md) and the common color
pipeline; this declaration
does not claim support for every field of an arbitrary asset format. Assets requiring
lit appearance must be prepared for the selected unlit representation, for example
by baking the intended appearance into their textures.

## Calibration and evidence

Keep material evaluation distinct from display calibration. Apply the configured
output corrections after scene composition as specified by V15; do not bypass gamma/
color handling merely because no scene lights are present. Finite range excursions
follow [V21](output-range.md); no automatic contrast rescaling is permitted. The [common color pipeline](color-pipeline.md) binds linear RGB, float32 precision,
premultiplied alpha and final correction; imported material descriptors and GPU
implementation remain local work. Explicit
calibrated/uncalibrated mode follows [V23](photometric-calibration.md); measurements
and optical accuracy remain deferred to rig verification.

V13's immutable asset fingerprints and prepared-program provenance identify baked
textures and material interpretation. Actual render-state evidence carries effective
material parameters when they vary. Replay uses that same interpretation; no lights
or current application defaults may be substituted for missing recorded settings.

Later implementation checks must cover known base colors/textures, baked shading,
view-consistent material evaluation, perspective/depth occlusion, unsupported
material rejection, calibrated output conversion and replay. Those checks and rig
measurements have not been performed. Rendering-stack selection alone cannot prove
physical luminance, contrast or pixel equality.
