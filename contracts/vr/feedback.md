# VR feedback contract

Governing rules: [V24–V26](../../docs/architecture/vr.md#v24). Result transport,
ordering and reset generations remain owned by [A06](../../docs/architecture/tracking.md#a06).
This contract declares accepted behavior; it does not implement or validate a runtime.

## Preparation and ownership

Store bindings in the versioned stimulus program, resolve them into epoch parameter
blocks and expose the same typed model to GUI/headless validation. Each binding names
one declared input channel and one compatible target parameter on a stable instance,
its operation, gain and offset. Functions follow V05 and use the current render
update's logical time under V24. Do not reinterpret a position, displacement and velocity as
interchangeable values. Units, coordinate frames and operation compatibility must be
explicit, with finite values and supported source/target declarations checked at Setup.
Validate competing writers using [V27's motion contract](motion-composition.md);
do not let iteration order resolve conflicting assignments to the same state field.

A channel whose frame_id is `anatomical_body` (tracking's T36 body frame) binds only
through `heading_relative_planar_integration` or by `movement_integration` to an arena's
yaw; binding it directly to world x/y, a layer target or direct_value fails Setup. The
planar operation, allowed only in an arena block, names one ordered pair
(`forward_channel`, `sideways_channel`) of distinct anatomical_body interval_average_rate
channels with the same unit and one linear gain in mm per input unit (e.g. mm per px),
with no offset. The order declares the axes; VR does not infer them from channel names.
Turning uses '1/s' (radians per second) onto yaw with a deg-per-radian gain.

Compile bindings into direct references to renderer-owned state and prepared parameter
blocks. Apply A06's finite ordered batch locally, with its generation checks. Do not
introduce coordinator updates per result, a second process, a node-graph interpreter,
implicit smoothing, prediction or a newest-result mailbox. Apply movement constraints
through the existing arena handler; all views use the same resulting state.

A direct-value mapping evaluates `gain * input + offset` in declared target units.
Movement integration consumes explicitly identified displacement or rate/interval
information; it must not repeatedly apply a displacement at render frequency, integrate
a remembered velocity across missing input, or guess a sample period from output FPS.
For a displacement `dx`, integrate `gain * dx + offset * dt`; for an interval-average
rate `r`, integrate `(gain * r + offset) * dt`. Here `dt` is the result's declared valid
source interval in seconds, never time since the last rendered frame. The integration
offset is a rate bias in target-units/second; a direct-value offset instead has target
units. In the absence of usable input, neither the feedback rate nor its offset is
integrated. Independently programmed motion follows its own animation clock.

For each eligible result covering source interval [t0,t1), dt=t1-t0, the arena's yaw
increment is dpsi=(g_turn*turn + offset_turn)*dt from its ordinary yaw binding (zero
without one). The planar increment uses the midpoint heading psi_m=psi_before+dpsi/2,
where psi_before is the retained yaw just before this result, and f/l from
[stimulus-schema.md](stimulus-schema.md): dxy = g_lin*dt*(forward*f(psi_m) +
sideways*l(psi_m)). Apply both increments together, then V16's boundary slide to dxy.
Tracking results are interval averages (T37), so the midpoint heading approximates the
heading over the interval; the existing CephVR integrator used the start-of-step heading.
[planar_feedback.py](planar_feedback.py) is the pure reference for these signs.

## Application-time attribution

At the start of a render update, capture A06's finite pending batch and select one
logical trial time `t`. Advance scheduled state/epoch transitions to `t` first. For
eligible results, use that current epoch's active bindings and evaluate their gain/
offset functions at `t - epoch_start`. Use the same prepared coefficients for the
batch, applying its eligible entries in order. Keep actual monotonic age checks
separate from this shared animation time. All views then use the resulting state.

A delayed result crossing an ordinary epoch boundary is not itself a reason to drop
it, use the earlier gain, reopen the old epoch or retroactively alter recorded frames.
For example, gain 1 in the preceding epoch and gain 0/offset 0 now produces no new
feedback movement now. Retain already-applied movement under V07.

Source/reset identity and trial/instance eligibility still apply. No source interval
from another trial or an instance's absent period may be applied on return; do not
split a displacement over an unobserved gap by an assumed uniform motion. Compatible
continuously active epochs do not constitute such a gap. A direct absolute value is
a new assignment, subject to current target validation, not an inferred displacement.

## Application-age check and local hold

`feedback.max_result_age_ms` is the single VR-owned positive finite maximum, resolved
at Setup into VRFilePolicies.max_result_age_ns and locked at Start. Its vr_config
default is **350 ms** (current CephVR's value), an engineering starting value to tune
on the rig; missing/invalid values block closed-loop readiness. Open-loop observation does not require or invoke
this control guard. Do not copy the tracking pre-processing 250 ms default into it.

Immediately before applying each otherwise eligible valid result, read the renderer's
host-monotonic clock and subtract the preserved A05 source-frame host-receipt time:
`age_ns = application_check_ns - source_host_receipt_ns`. Accept equality with the
maximum; excess age triggers V26. For interval-valued movement, the source identity is
the result's newest contributing frame; the full interval must separately be valid.
Never replace source receipt by result-production/arrival time or device-clock time.
Missing required timestamps or negative ages are invalid timing evidence under E06,
not a zero-age repair or an ordinary nonfatal stale event.

For each stale result, record its identity, source time, check time, measured age,
maximum and stale disposition. Preserve movement already applied and hold new feedback
movement under V25. Continue considering the finite batch in order: the next eligible
fresh valid result may resume feedback in the same reset generation, even in that
batch. Apply only its declared valid source interval; do not accumulate or replay the
intervals of rejected results, integrate a remembered velocity, or undo tracking's filter.
A direct-value result assigns its own new measurement. No fade or smoothing is added.

Staleness does not invalidate the generation, clear otherwise eligible batch entries,
or request a processing reset. Tracking retains sole ownership of camera-gap, input-age/
overflow and result-overflow resets under A06. Every result carries its reset_generation;
after exact trial/source checks, a result with a newer generation is the reset: discard
older-generation pending entries. Tracking marks validity: after a processing reset the
first new-generation result is baseline-only; after delivery-only overflow new-generation
results may be usable at once.
Tracking sends a result, invalid when necessary, for every evaluated frame, so V25's
hold applies until a usable one arrives. A baseline-only result supplies no movement.
There is no VR reset service, retry state or recovery acknowledgement. Required health/
progress/evidence failures retain E06/E08; a local hold is not permission to conceal them.

The application-age observation is a software consumption timestamp, not output swap
or illumination time. Retain actual first output incorporation separately under A05/
V13, including per-output failed/unknown presentation; passing this guard does not
prove a physical end-to-end latency bound.

E10 permits feedback to drive stimuli only in closed-loop mode. Instance activity,
trial initialization and continuity follow [V07](state-continuity.md); absent-instance
feedback is not saved for later catch-up. Parameter/state assignments must remain
explicit so feedback cannot silently overwrite independent programmed animation.

## Invalid input, reset and recovery

At a reset or invalid report, preserve already-applied state and stop applying unusable
feedback. Only a producer generation change discards old-generation pending results
under A06, including any dequeued but unapplied entries. An invalid result alone does
not retire otherwise eligible later results. Preserve the invalid interval and source/reset identity as evidence.
Before a first usable result, start from the declared initial state and advance only
any independent programmed motion; do not invent a feedback baseline or displacement.

Holding a feedback-controlled rate means stopping its feedback-driven movement, not
continuing the last velocity indefinitely. Preserve already-applied feedback movement
in the shared state; programmed motion may still advance that same pose/phase under
[V27](motion-composition.md). The trial/epoch clock, videos and photodiode keep their existing
behavior. An explicit scheduled reset or assignment still follows V07; this is not a
freeze of the whole scene or an extension of the trial.

A render update with no new result does not manufacture another movement sample or
by itself declare the tracker invalid. It also does not prove the last result is fresh.
V26 checks newly considered valid results at application; it does not create a
separate no-result/invalid-input timer. E08 health/progress failure detection and the
tracking pre-processing age guard remain independently applicable.

Resume only with a usable result in the current generation. A baseline-only result
cannot supply an invented displacement. Movement increments must describe a valid
interval, never bridge a discarded/invalid gap. A directly measured absolute value can
assign its declared target on recovery; that is a new measurement, not replay of lost
movement. Do not add an unselected smoothing transition to conceal a discontinuity.

Temporary invalid data does not change the active backend set, enter a fallback
animation or restart the scene. Confirmed required process/device/progress failures
and inability to retain required evidence still follow E06/E08.

## Evidence and implementation

Under E13/V13 retain binding identity, input/result/reset lineage, effective applied
values/state, current epoch/evaluation time, application age/check time and threshold,
hold onset/resumption, observed reset generations and invalid/discard dispositions. Tie actually
applied results to output evidence under A05; never claim that a discarded result was
displayed. A hold is a logged state interval, not a fabricated result every frame.
Saving Off retains existing administrative status/incident obligations but does not
promise detailed feedback history or actual-output replay.

Additive motion and rejection of conflicting absolute writers follow
[V27](motion-composition.md); no selectable writer-priority policy is introduced.
[Typed messages/providers](runtime-bindings.md), [function/writer compatibility](stimulus-schema.md) and [evidence schemas](evidence-format.md) now bind these interfaces; their runtime execution remains code work. Tracking estimator and
reset-algorithm design remains with that backend's later discussion. Physical latency
and full-workload performance remain rig-deferred; no such measurements are claimed.
