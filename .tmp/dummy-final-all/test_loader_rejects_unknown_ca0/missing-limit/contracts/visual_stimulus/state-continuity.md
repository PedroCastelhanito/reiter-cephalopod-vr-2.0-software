# Visual Stimulus state continuity contract

Governing rule: [V07](../../docs/architecture/visual_stimulus.md#v07). Runtime ownership follows
[V01](../../docs/architecture/visual_stimulus.md#v01), authoring [V02/V03](../../docs/architecture/visual_stimulus.md#v02),
and parameter animation [V05](../../docs/architecture/visual_stimulus.md#v05). This is a declared
implementation contract; no renderer or program compiler is implemented here.

## Identity, resources and state

A reusable scene definition is a template; an instance is the stimulus whose live
state can continue. Give every authored instance a stable program-local ID; an
epoch referencing that instance retains the ID. Reusing an asset or matching
parameter values does not establish identity. Distinct instances can share immutable
GPU assets while keeping independent motion/playback/pose state. The editor manages
IDs: reusing an instance preserves it; creating a separate stimulus gives a new ID.
Do not require operators to type IDs or infer continuity by asset-filename matching.

Each type supplies a small concrete state object and transition handler, not a
second scheduler. Keep three concerns separate:

| Data | Lifetime / use |
| --- | --- |
| Asset/render resources | Prepared textures, meshes, programs and decoder resources; reused when compatible, owned/released by the rendering/resource subsystem. |
| Authored settings | Validated epoch parameter blocks, initial-state values and explicit reset/state assignments. |
| Live state | Current motion anchors, texture phase/offset/angle, video playback clock or arena observer pose; retained in the renderer. |

Compatibility requires the same instance ID, state type and a compatible resource/
coordinate interpretation. Speed, contrast or visibility changes alone do not turn
one texture into a new instance. Changing a resource/type or coordinate definition
may invalidate some retained state; a type-specific compatibility rule must declare
this during Setup. Do not silently reinterpret incompatible state. Initialize the
new state from its declared initial values and expose that restart in the resolved
program/GUI. Detailed compatibility matrices follow the stimulus schemas.

Retaining state never means copying a GPU texture, frame buffer, decoded frame or
whole scene graph. Initial-state defaults apply when an instance initializes or
resets; materializing defaults in each epoch must not turn them into implicit resets.
An explicitly authored state assignment overrides the relevant retained field.
Live-state identity is scoped to one trial execution; matching a program-local ID
in another trial never carries state across that boundary.

## Preparation and runtime transition

During Setup, the program compiler resolves the active instance list and parameter
blocks for each epoch and creates a compact ordered list of boundary operations.
An operation names an existing instance, continuation/pause/resume/reset/initialization
action and changed settings. Numerical state for a continuation is obtained at runtime;
Setup does not precompute feedback-dependent arena poses or video outcomes.
Use the resolved epoch order/durations, not template order or assumed mean durations.

The rendering worker holds a direct instance lookup plus a cursor through prepared
boundaries. At a boundary, under the renderer's single state owner:

1. Advance/evaluate each affected instance's old motion to the logical boundary.
2. Retain its state in place, or apply an explicit reset/initialization.
3. Apply the next epoch's prepared settings and any explicit state assignments.
4. Establish new motion anchors at the boundary and switch the prepared active list.

These are local operations, not per-frame coordinator RPCs. Keep parameter changes
atomic with respect to one frame's state evaluation; all projector views of that
frame use the same evaluated stimulus state. Required decoder/asset preparation
must occur before the relevant readiness gate, not as blocking disk work here.

The runtime scheduler only selects due operations and dispatches them to types.
Type handlers own motion/playback/pose semantics. Avoid per-frame scans through the
whole timeline, backwards searches for matching stimuli, JSON parsing, deep copies,
shader recompilation or resource recreation for unchanged content. Storage scales
with prepared instances/resources and transitions, not elapsed frame history.

If rendering observes several elapsed boundaries, process logical transitions in
order to preserve the state path; do not fabricate frames for elapsed epochs. The
response to missed software submissions follows
[V10 and its timing contract](timing-misses.md); physical presentation evidence
remains separate.
For E13-enabled output, export evaluated state/frame lineage through the eventual
recording path; no recording loop mutates renderer state.

## Texture motion: drift, hold, resume

Treat static and drifting textures as the same type. Separate the pattern/asset
from phase/translation/rotation and their rate functions. For constant phase rate:

`phase(t) = phase_anchor + rate * (t - anchor_time)`

At boundary `b`, first evaluate `phase_b` with the old rate. Retain `phase_b` as
the new anchor, set `anchor_time = b`, and apply the new rate. With no feedback
contribution, rate zero holds that phase; combined motion follows
[V27](motion-composition.md). The same operation applies to translation offset and rotation angle.
Periodic texture coordinates may be reduced modulo their period without changing
the image; nonperiodic coordinates must not be wrapped implicitly.

For example, initial phase 0.1 cycles and rate 0.2 cycles/s give phase 0.7 after
3 seconds. A 2-second static epoch holds phase 0.7. Another 3 seconds at 0.2 cycles/s
ends at 1.3 cycles, equivalent to 0.3 for a periodic grating. No epoch resets to 0.1
unless explicitly requested. This example describes scheduled state, not measured
physical presentation timestamps.

Do not only replace `rate` in `initial_phase + rate * trial_elapsed`, which changes
past accumulated motion. For nonconstant rates, the type evaluates the defined
rate integral over each segment and anchors at changes; direct position/phase
keyframes are explicit state trajectories with their own contract. Prefer analytic
evaluation where defined so missed render iterations do not accumulate integration
error. Feedback bindings and invalid-input holds follow
[V24–V26](../../docs/architecture/visual_stimulus.md#v24) and the [feedback contract](feedback.md),
including application-time attribution and freshness/reset behavior.

## Absence and return within a trial

At the logical boundary where an instance leaves the active scene, evaluate its
state to that boundary and retain it in the renderer's direct instance lookup.
Remove it from the active update/draw set. Retain motion anchors, playback position,
pose and any instance-local elapsed time; do not advance them or apply feedback
while absent. Do not accumulate absent-period feedback for later replay. An instance
that remains in the active scene but is visually covered is not absent.

On a compatible return, reuse the retained state and re-anchor motion/playback at
the return boundary so the absent interval contributes no elapsed motion or playback.
Apply the returning epoch's prepared settings and explicit reset/state assignments
through the existing transition handler. If the instance has never appeared in this
trial, initialize it; if incompatible, use the existing compatibility/restart rule.
An explicit static epoch holds a present texture only when both programmed and
feedback contributions are stopped under [V27](motion-composition.md).

For example, phase 0.1 with drift 0.2 cycles/s for 3 seconds reaches 0.7. Omission
for 2 seconds leaves it at 0.7; returning for another 3 seconds at the same rate
reaches 1.3 cycles. No update loop is needed for the omitted interval. An explicit
trajectory assignment on return can still override the retained phase. Animation
functions use the returning epoch's local time under the
[animation/playback contract](animation-and-playback.md); absence never causes
an implicit catch-up of motion, media playback or closed-loop state.

Media resources may retain prepared data, but absence cannot consume presentation
time or require background playback. Decoder buffering and resume preparation remain
part of the media interface work; retaining state is not proof of timely video resume.

## Trial and Idle boundaries

Prepare each trial's initial live-state values from its own program. Initialize an
instance at its first scheduled activation in that trial, with timing relative to
the valid trial start. Time before that activation, in Ready or in Idle does not
advance its live state. The same program-local instance ID in a later
trial denotes a fresh trial state. Do not inherit phase, playback position, observer
pose or accumulated motion from the prior trial, even after normal completion.

E05 governs entering the independent Idle presentation at trial end/interruption.
Stop trial-state updates at the applicable boundary and preserve any final evidence
needed by E13 outputs; never reuse that terminal state as the next trial's initial
state. Resident renderer/GPU assets can remain loaded and shared when compatible.
Resetting live state is distinct from reloading resources or restarting the renderer.
All readiness, failure and cleanup obligations retain their existing owners.

## Remaining contract work

Detailed stimulus compatibility matrices, animation-function vocabulary, media decoder
interfaces and concrete feedback wire/record bindings remain to be specified. These do not
reopen the selected pause-on-absence or initialize-each-trial behavior.

Future implementation checks must cover drift/hold/resume, explicit reset/assignment,
distinct instances sharing an asset, compatibility changes, random epoch durations,
repetitions, absence/return without catch-up, no absent-period feedback replay,
fresh trial initialization independent of Idle duration, resource reuse, multiple
elapsed boundaries and consistent state across projector views.
These checks and runtime/rig measurements have not been performed. No performance
or physical onset guarantee follows from this contract alone.
