# VR motion composition

Governing rule: [V27](../../docs/architecture/vr.md#v27). Lifetime follows
[V07](state-continuity.md), programmed integration [V05](animation-and-playback.md),
feedback [V24–V26](feedback.md), and arena constraints [V16](arena-movement.md).
The declaration types in [motion_types.pyi](motion_types.pyi) describe local renderer
data, not a new runtime subsystem, process, public RPC or implemented renderer.

## Prepared targets and writer checks

A target is an existing `(instance_id, state_field)` with concrete units, coordinate
frame and a type-owned integration operation. Compile direct references to the
instance's state and prepared programmed-rate/feedback evaluators. Do not search
scene definitions or expression graphs at each update. A covered but active instance
continues normally; an absent one pauses under V07.

For each resolved epoch, group declared writers by actual target/storage overlap,
not only by their authored names. A full position and its x component overlap.
Validate the following table in the shared Setup validator:

| Writers to the same target | Result |
| --- | --- |
| Programmed rate only | Integrate into retained state. |
| Feedback movement only | Add each eligible increment into retained state. |
| Programmed rate plus feedback movement | Accepted additive composition. |
| One absolute trajectory or one direct feedback assignment | Accepted as the sole continuous writer. |
| Absolute writer plus any other continuous writer, or two absolute writers | Reject Setup with both source paths and target identity. |
| Explicit boundary initialization/reset plus subsequent incremental motion | Accepted: apply boundary assignment once, then evolve from it. |

Treat a feedback-controlled motion rate as a writer to the integrated position/phase,
not just to an unrelated parameter called speed. Multiple declarations that alias the
same feedback binding are invalid duplicates; additive composition does not authorize
counting one measured movement twice. Distinct configured source channels still follow
V24's mapping model. Unit/frame incompatibility is a Setup error, not an automatic
conversion inferred from similar names. Non-motion parameters such as contrast do not
acquire additive semantics from this rule; their direct writer remains explicit.

## One state, two increment sources

For an unconstrained scalar target, the descriptive update is:

`q_next = q_previous + integral(programmed_rate, active_segments) + sum(eligible_feedback_increments)`

The feedback increment formula and valid source interval are defined once in the
[feedback contract](feedback.md). Programmed integration uses logical elapsed active
time, while feedback uses each result's measured valid interval and current-epoch
coefficients. Do not integrate a held feedback rate over renderer elapsed time.

Keep one reached value and its programmed-motion anchor/cursor. After applying an
increment, re-anchor subsequent programmed evaluation at that reached value and the
current logical time. A later evaluation must not overwrite it with a trajectory
recomputed from the trial's original state. This does not restart an epoch function:
the local function time continues from that epoch's start under V05.

Changing a gain/rate affects future increments only. There is no second accumulated
feedback pose to subtract when feedback is disabled. Evidence may separate requested
contributions, but those diagnostics are not competing live state stores.

## Update order and constrained targets

Use the existing single renderer update:

1. Capture the finite pending feedback batch and one logical update time.
2. Advance programmed motion and due transitions to that time in chronological
   segments. At each boundary apply the prepared reset/assignment once, retain or
   pause instances under V07, and activate the next prepared parameter block.
3. Apply eligible current-epoch feedback in A06 order using V24/V26. When several
   channels form one movement result, resolve them together into that target's
   declared coordinate frame before passing the increment to its type handler. A
   heading-relative planar binding adds its yaw and midpoint-heading world x/y
   increments together from the state reached after step 2 and earlier results, then
   applies V16 sliding ([feedback contract](feedback.md)).
4. Snapshot the final effective state once for all four views and E13/V13 evidence.

For positions, transform vectors into the declared common frame before addition.
For angular scalar fields, add angular increments in their declared units; wrapping
is only the type's existing equivalence rule. For a 3D orientation, the type handler
composes rotations with a declared frame/convention; never add quaternion or matrix
components as if they were scalar phase. The concrete planar pose vocabulary is bound in stimulus-schema.md and cannot be guessed from tracking channel names.

Apply arena constraints to the actual ordered motion path through the existing V16
handler. Do not collapse a programmed move into a wall and a later feedback move
away into a net displacement before collision handling. They are sequential at
application under V24, and blocked displacement must be discarded at each step.
An unconstrained scalar can use the additive equation directly; it is not a license
to ignore noncommuting rotations, intervening resets or constrained paths.

## Holds, static epochs and evidence

Invalid or stale feedback contributes no new increment; programmed motion continues
on the same state. A fully static target has zero programmed motion and zero feedback
motion, including its integration offset/rate bias. Merely setting gain to zero does
not cancel a separately nonzero bias. Absence pauses both paths; a new trial initializes
one fresh state. Explicit boundary reset remains visibly authored.

Example in cycles, with zero feedback bias: phase 0.1 plus 0.2 cycles of programmed
drift and 0.3 cycles of valid feedback reaches 0.6. One further second of 0.2 cycles/s
drift during a feedback hold reaches 0.8. A following fully static epoch stays at 0.8.
This is a contract illustration, not a runtime test or a physical timing claim.

Record effective state consumed by rendering, contribution/binding identity and
feedback result dispositions under V13. For constrained movement preserve requested
and applied motion under V16. Replay consumes retained effective state rather than
summing idealized motion again. No recording process owns or mutates live state.

## Validation boundary

Later runtime checks must cover additive phase retention across gain/rate changes,
invalid/stale holds with ongoing programmed drift, full static holds, bias handling,
absolute-writer rejection, resets, absence/return and ordered boundary constraints.
Only declaration syntax and document consistency are checked here. Schemas and transport/record layouts are declared in the [VR contract index](README.md); renderer implementation remains code work; physical behavior remains rig-deferred.
