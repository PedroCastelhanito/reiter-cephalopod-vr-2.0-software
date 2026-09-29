# VR scene composition

Authority: [V02](../../docs/architecture/vr.md#v02), [V04](../../docs/architecture/vr.md#v04)
and [V07](state-continuity.md). This binds the accepted scene scope and preparation
semantics; it is not a complete program schema or renderer implementation.

## Authored scene and draw sequence

A scene owns an opaque background color, an optional arena-instance reference, and
an ordered list of 2D stimulus-instance references. A 2D entry is an image, video or
static/drifting texture under V04. The list is bottom-to-top; later entries composite
over earlier entries using the existing linear premultiplied-alpha source-over rule.
Order is explicit program data, not asset loading order, dictionary iteration, or
an implicit z coordinate. Do not maintain a second independent layer-order field.

Render each surface from the same evaluated group state in this order:

1. Clear its scene target to the declared opaque background and initialize depth.
2. Render the optional arena using its one effective virtual observer pose, prepared
   asset transforms and V17/V04 unlit material/depth rules. Multiple nodes/meshes in
   that asset belong to this arena; they do not create independent arena viewpoints.
3. Draw applicable 2D entries in list order using each instance's declared V14 space,
   surface coverage, parameters and opacity. Disable arena-depth testing/writing for
   these overlays so they cannot disappear behind arena geometry or occlude its
   depth state. Their relative occlusion comes from list order and alpha.

A scene may contain no arena, no 2D layers, or neither; an explicit background-only
scene is valid. Do not guess its color. There is no second active arena viewpoint,
interleaved arena/2D stack or general world-space placement mode for 2D layers in
this profile. Images/objects that must participate in arena depth are prepared in
its external GLB asset under the existing supported static material profile. This
rule does not add imported animation, arbitrary video materials or 3D transparency.

## Preparation, continuity and ownership

The shared lightweight program validator resolves references, allowed instance types,
scene layer order and parameter/writer compatibility before execution. Reject unknown
references, more than one arena slot and duplicate use of an instance in the same
scene. One instance may cover multiple declared surfaces without duplicating its
state; use distinct instance IDs for independently positioned copies of an asset.
Instances may be reused by other scenes under V07. Multiple arena instances can exist
in a program and occur in different epochs, with at most one active in a scene.

Compile each scene's existing arena lookup and draw list into the immutable prepared
plan. At transitions select prepared entries; do not rebuild resources, sort layers,
parse JSON or ask the coordinator for a per-frame composition decision. Per-output
mapping follows [geometric correction](geometric-correction.md) after composition;
photodiode placement and color correction keep their existing stage order.

Changing layer order or covering a layer is not an implicit reset. A present covered
or zero-opacity instance remains active; only absence from the active scene pauses
its state under V07. Explicit assignments/resets and incompatible-resource transitions
retain their existing rules. Alpha still follows V21 clipping and invalid-state policy.

Retain scene background, arena/instance identities, layer order and surface selection
in the immutable recipe/resolved plan. Per-frame evidence references that plan plus
actual instance state; it need not repeat the full layer list. Replay must use those
values rather than current editor defaults. Under Save Off, preserve administrative
summaries without adding detailed recording. Physical timing and rendering performance
still require rig verification; full authoring/compiled/wire models remain local work.
