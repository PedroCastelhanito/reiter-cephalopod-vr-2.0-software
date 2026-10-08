# Visual Stimulus timing misses and video catch-up

Governing policy: [V10](../../docs/architecture/visual_stimulus.md#v10). Timing comes from
[V06](../../docs/architecture/visual_stimulus.md#v06), animation/media clocks from the
[animation/playback contract](animation-and-playback.md), and state transitions from
the [continuity contract](state-continuity.md). This contract declares behavior;
[renderer/evidence interfaces](runtime-bindings.md) are declared; runtime implementation and verification remain outstanding.

## Clock-preserving execution

Use the prepared epoch boundaries against the controller's scheduled trial clock.
Rendering delays never move those boundaries or pause the trial clock. At a render
update, process elapsed logical boundaries in order using the existing continuity
handlers, then evaluate the currently active epoch at its elapsed local time. Do not
render old epochs in a catch-up burst, repeat them later, or extend the trial.

State still follows the intended logical path through a missed epoch. For example,
a drift epoch missed by rendering can advance a retained phase before the following
hold epoch. That is computed state, not evidence that the drift was displayed.
Apply the ordinary absence/reset rules even across multiple elapsed boundaries.
At trial end, account for any remaining elapsed epochs before completing the
renderer-owned stop evidence; do not submit their frames after the trial boundary.

## Video frame selection after a delay

Video playback position advances according to scheduled active playback time and
its declared rates, independently of how many frames were submitted. V07 excludes
absent time and V09 supplies hold/loop behavior. On recovery from a brief delay,
select the source frame whose validated presentation interval contains the current
target media position. Use source presentation timestamps and the endpoint mapping;
do not calculate frame selection solely as elapsed time times nominal frame rate.

Frames whose intended presentation intervals have already elapsed are not replayed.
Decoding may still traverse reference frames needed to produce the selected frame;
not presenting a source frame does not imply the codec can skip decoding it. The
renderer never blocks to replay an obsolete queue or slows playback to show every
source frame. Loop generation plus source-frame identity disambiguates repeated
uses of the same asset frame. In hold mode, select the final valid image normally.

Retain evidence of source frames not submitted during active playback, distinct
from deliberate absence, holds and resets. Repeated use of a source frame at a
higher display rate is not a source-frame skip. Timestamp/rate conversion can also
omit source frames without a rendering stall; do not label every unsubmitted frame
a decoder error or falsely attribute every omission to a measured late render.
Detailed records identify the target media time and actual selected source frame.

If the target video frame is temporarily unavailable, reuse the same compatible
instance's last valid source image while advancing the target playback clock. Other
scene/parameter updates continue. Record target media time, held source identity,
starvation reason and observed interval boundaries; on recovery select the frame
for the current target, not the overdue queue. Initial/reset content must have been
prepared before the applicable readiness gate; missing that prerequisite is a
preparation/invariant failure, not permission to use an unrelated image. Never
silently substitute a future frame. Detailed evidence follows the
[replay contract](replay.md); administrative summaries retain compact hold counts.
Confirmed decoder failure and absence of required progress retain E06/E08 handling;
an empty queue does not prove normal end of clip.

## Entire epochs with no output submission

Track software submission evidence for each resolved epoch occurrence and required
output. Record an epoch/output pair with zero submissions when its complete scheduled
interval has elapsed and the renderer has complete accounting evidence. Include
misses at trial start, several epochs crossed in one delayed update, and the final
epoch at trial end. Successful submission accounting must distinguish an attempted
call from an output operation reported as failed; concrete API observation points
remain part of the presentation-evidence contract.

A missing epoch on one output is not repaired by another output having submissions.
Record the affected output identities and preserve the original schedule. Such timing
misses, even a whole omitted epoch, do not themselves interrupt a trial/session or
skip subsequent trials, except E05's start limit: every required output must return
its first trial presentation call by `T + 250 ms`, or the session is interrupted. They do not change the controller's lifecycle outcome into
Interrupted, and normal completion must not be described as timing-perfect.

An epoch cut short by an independent Abort/failure is not a fully elapsed missed
epoch. Missing accounting after a crash/disconnection is unknown, not proof of zero
submissions. Software frame submission is not proof of physical scanout or emitted
light; physical onset, inter-projector timing and pulse evidence remain separate.
No new strict timing limit or automatic abort threshold is selected here.

## Evidence and failure boundaries

Keep per-frame/source-frame lineage and per-epoch/output omission details in the
E13-controlled Visual Stimulus outputs. When Save Visual Stimulus data is Off, do not write these detailed
histories through a different log. Expose compact timing-warning counts in current
status and existing administrative trial metadata regardless of that switch; retain
full omission identities/times only in the detailed outputs when enabled. Accumulate
status counters rather than emitting a control RPC or session-log line for each miss.
Do not invent frame or physical-onset records for content that was never submitted.

The exception is for timing misses, not failed components. Confirmed renderer,
GPU/output, decoder, enabled recording or required logging failures still follow
E06. [V12 recording-buffer omissions](recorded-outputs.md) are a separate nonfatal
policy, not rendering misses or permission to lose required evidence. E08 health/progress obligations remain active; a live heartbeat cannot establish
render/decoder progress. Keeping a schedule after a miss does not authorize recovery
from a failed process or resumption of an interrupted session.

## Remaining work and checks

Bounded video preparation follows [V11](media-preparation.md). Concrete
submission/timestamp observations, frame lineage schemas, buffer-limit bindings,
starvation logging interfaces, decoder progress detection, refresh/pacing
integration and recording interfaces remain local contract work. Rig measurements
remain deferred under E15. Future runtime checks must cover multiple elapsed epochs,
per-output zero submissions, video timestamp catch-up and loop generations, Save Visual Stimulus
data Off, incomplete/crash evidence and failure-policy separation. No such behavioral
checks or physical timing verification have been performed.
