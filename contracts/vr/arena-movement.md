# VR arena movement contract

Governing rule: [V16](../../docs/architecture/vr.md#v16). The renderer owns instance
state under [V07](state-continuity.md); the fixed physical observer and calibrated
views follow [V15](projection.md). This contract declares preparation, ownership
and sliding response; no runtime is implemented.

## Authored and prepared data

The trial protocol explicitly selects simple boundaries or unrestricted movement
for each arena instance. A constrained instance receives a protocol-owned simple
allowed-region definition in its declared arena coordinate frame and units.
The visual asset is loaded under [V18](arena-assets.md); its metadata cannot supply
or override the protocol's movement settings. An explicitly supplied nonnegative
wall margin reduces the allowed region by the declared distance from its walls;
omitting an optional margin means no additional inset. This is mathematical
geometry, not a physical rig dimension or a collision mesh inferred from artwork.

Keep the visible arena and movement-region definitions independently identifiable.
A mesh bounding box is not an implicit allowed region: it can include inaccessible
space or decorative geometry. Expose the chosen region alongside the arena in the
editor so the author can inspect alignment before preparation.

Setup validates finite coordinates, supported region representation, positive
extents, well-formed topology, matching coordinate transforms and a nonempty
allowed region after margins. Reject a declared starting/reset position outside
its allowed region; do not silently snap it inside. Retention/compatibility at
program transitions follows V07, with concrete boundary-change compatibility to
be bound in the stimulus schema. Unrestricted mode has no hidden walls, wrapping
or repositioning inferred from the visual mesh.

Prepare immutable region data once and associate it with the arena instance.
[Planar polygon schema and solver binding](stimulus-schema.md) define the vocabulary and protocol serialization; implementing the region helpers does not authorize general rigid-body physics.

## Motion and ownership

Keep requested motion separate from effective constrained motion. The rendering
worker computes one effective virtual pose and all surface views consume it.
Neither the coordinator nor the recording thread applies a second boundary
correction. Boundaries apply to virtual arena coordinates and never relocate V15's
fixed physical viewing position.

The movement contract must handle the traversed path, not only whether the final
point lies inside: one large update must not cross a forbidden gap and reappear
inside another allowed portion. Sweep the requested path to first contact, then
remove the remaining displacement component directed into the wall and continue
with the allowed tangential component. For a planar wall with unit outward normal
`n` and remaining displacement `u`, the single-contact rule is
`u_slide = u - max(0, dot(u,n)) * n`. Do not renormalize this result to the original
movement magnitude or change heading. Subsequent movement away from the wall is
unrestricted by that contact.

Handle subsequent contacts along the remaining path. At simultaneous contacts,
constrain against the active walls together so a corner cannot push the pose through
another wall; stop translation when no permitted component remains. Stable contact
ordering, tolerances, supported region geometry and bounded solver execution require
concrete bindings. A failed numerical solve follows E06 rather than silently passing
through walls. A valid fully blocked move is ordinary contact, not a failed solve.

Discard blocked displacement for that update. It does not become momentum, stored
velocity, or a later catch-up movement. A new input may request movement into the
wall again and is constrained again. Rotation still follows its authored/input
source; contact does not automatically turn the virtual observer. Direct pose
assignments/reset transitions must follow their explicit validation contract rather
than being mistaken for displacement or silently projected to a nearby region.

Normal boundary contact does not interrupt a trial or change its scheduled duration.
Invalid/nonfinite runtime state remains a failure under E06, not a collision event.
V10's missed-render policy cannot bypass constraints on the logical motion path.

## Evidence and outstanding work

Retain the resolved boundary definition or a verified immutable reference with the
protocol snapshot/resolved plan. Under V13, record the actual effective pose used by rendering and
whether movement was constrained, with requested/applied displacement available
in the arena state evidence. Reconstruction uses recorded effective state, not a
new collision simulation. Detailed records remain governed by E13's save switch.

[Stimulus/region declarations](stimulus-schema.md), [effective evidence](evidence-format.md) and [runtime bindings](runtime-bindings.md) bind these interfaces; runtime integration remains code work. Later implementation checks must cover invalid/empty regions,
outside initial positions, margins, oblique sliding, corner blocking, departure
from contact, unchanged heading, discarded blocked motion, large updates through
forbidden space, explicit unrestricted mode, shared views and replay. No behavioral
checks or rig verification have been performed.
