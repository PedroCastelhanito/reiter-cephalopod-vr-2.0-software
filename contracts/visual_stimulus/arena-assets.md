# Visual Stimulus prepared arena asset contract

Governing rule: [V18](../../docs/architecture/visual_stimulus.md#v18). Appearance follows
[V17](arena-appearance.md), movement [V16](arena-movement.md), asset preparation
[E07](../../docs/architecture/experiment.md#e07), and retention [V13](replay.md).
This is a declared interface boundary; no importer/runtime is implemented.

## Authoring and protocol ownership

The operator generates the visual arena before session preparation using external
tools. The stimulus program references the resulting asset and gives each live
arena instance a stable identity. Selecting assets and configuring protocol
boundaries does not introduce a built-in mesh generator or 3D modeling editor.

The trial protocol is the single editable source of each arena instance's movement
mode, allowed-region geometry and optional wall margin. Bind protocol movement
settings to the program's stable arena instance ID, not its filename: multiple
instances may share one visual asset while using different movement settings.
Validate missing/unknown instance references and conflicting assignments during
Setup. Do not maintain another editable boundary definition in the visual asset
or silently accept its embedded collision/navigation metadata as authoritative.

Resolve protocol boundary coordinates and visual asset transforms into the same
explicit arena frame and units. Do not derive physical scale from the tank dimensions
or stretch boundaries to fit an asset bounding box. Both asset transform and movement
settings are inspectable in configuration; their correspondence is the protocol
author's responsibility, with numerical validity checked by preparation.

## Preparation and retained evidence

Resolve the selected asset and dependencies from the configured asset root. Validate
the supported geometry/material profile and prepare immutable render resources
before required Ready. Invalid or missing required geometry/materials block Setup;
there is no generated fallback arena. V04's [static GLB profile](media-profiles.md#static-arena-profile)
binds the supported import scope and protected dependencies. Typed importer output,
color/alpha interpretation and numeric resource budgets remain local work.

Keep compatible GPU resources resident across trial boundaries where possible,
while initializing live pose/state under V07. Session execution does not regenerate
meshes or reload unchanged assets at each frame/epoch. Editing an external source
file cannot silently change prepared session geometry; imports and transitive
resources use V04's [protected-source lifetime](asset-lifetime.md). Retain prepared
geometry and textures without reopening an unprotected source at trial boundaries.

Retain resolved protocol movement settings and asset-transform association with the
immutable trial program/plan evidence. Record visual asset/dependency fingerprints
under V13, retaining external originals rather than automatically copying them into
the session. Different protocol boundaries do not require duplicate visual assets.
Replay uses the recorded effective pose and prepared associations.

Later implementation checks must cover shared assets with distinct instances,
missing/conflicting protocol bindings, unit/transform mismatches, invalid imports,
resource reuse and immutable replay associations. None of these checks establishes
runtime readiness or rig accuracy; behavioral verification remains pending.
