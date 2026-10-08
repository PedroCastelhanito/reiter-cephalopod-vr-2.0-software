# Visual Stimulus animation clocks and video completion

Governing policies: [V05](../../docs/architecture/visual_stimulus.md#v05) and
[V09](../../docs/architecture/visual_stimulus.md#v09). Instance lifetime and motion anchoring
belong to the [continuity contract](state-continuity.md); resolved epoch boundaries
belong to the [duration contract](durations.md). These are declared implementation
contracts, not an implemented or validated renderer.

## Parameter animation clock

For a resolved epoch occurrence starting at trial-relative time `s`, evaluate its
parameter functions and keyframes at `u = t - s`, where `t` is trial-relative logical
time. Subtract integer nanosecond timestamps before converting the local difference
to the numeric seconds used by a function. Each occurrence, including a repeated
or shuffled copy of the same epoch, starts with `u = 0`. There is no authored
instance-active or trial-global clock selector in the accepted model.

The prepared occurrence stores its start and duration together with its validated
parameter definitions. The renderer uses those values directly; coordinator updates,
frame counts and observed frame intervals do not drive the function clock. When a
render iteration reaches an epoch late, evaluate at that epoch's elapsed logical
time rather than starting its function at zero on the first rendered frame.
This does not claim a physical display onset. Miss handling follows
[V10 and its timing contract](timing-misses.md).

At an epoch boundary, first complete the prior segment's state evaluation using
its old function and local time, then apply the next epoch's values at zero. A rate
function changes how retained state evolves; it does not replace accumulated phase,
position or playback state with a calculation from trial start. For a motion rate
`r(u)`, the state increment over a segment is its integral over that segment's local
time interval. Prefer analytic integrals for supported functions. An explicitly
authored position/phase curve instead assigns that state field, as permitted by V07;
[V27](motion-composition.md) rejects another concurrent writer to that absolute target.
Programmed rate increments may combine with feedback increments under V27.

For example, a speed ramp `r(u) = 0.5*u` cycles/s over 2 seconds adds 1 cycle.
Repeating that epoch restarts its speed ramp at zero but begins from the retained
phase. With no feedback contribution, a static epoch sets speed to zero and preserves
that phase; V27 defines the combined case. Returning after
an absent epoch uses the returning epoch's local clock while preserving V07 state;
no motion or playback is integrated over the absent interval.

Random epoch durations do not implicitly stretch timestamps or rescale functions.
Evaluate definitions against each resolved occurrence duration. [The stimulus vocabulary](stimulus-schema.md) binds supported functions, interpolation, V05 truncation/hold and parameter domains; unsupported definitions must not be silently
substituted. Video frame timestamps and retained playback position are media state,
not epoch-relative animation keyframe timestamps.

## Video end behavior

Each video instance has a typed `end_behavior` of `hold_final_frame` or `loop`.
The editor's creation default is `hold_final_frame`; explicit program values are
preserved. Under [complete epoch settings](program-authoring.md), the stored block
must contain the choice: runtime loading does not repair an omitted field. Retain
the value in the prepared program so GUI,
headless execution and recorded setup agree. Changing this setting does not itself
restart playback or alter an epoch's duration.

The media adapter must provide a validated finite positive playable duration `D`,
an ordered video-frame timestamp mapping and a valid final image. This refers to
the effective video timeline, not an assumed frame count divided by nominal frame
rate or a longer container/audio duration. Supported formats and the adapter's exact
endpoint-discovery interface remain media-contract work. Invalid or unresolvable
media blocks readiness; do not guess an endpoint or substitute an empty image.

At ordinary clip completion:

- `hold_final_frame` retains the valid final image through the rest of the active
  presentation. The playback position is held at the endpoint; time spent holding
  does not accumulate an overshoot that later advances playback.
- `loop` continues at the clip beginning, preserving elapsed remainder across a
  wrap. For constant forward playback from the beginning, target media time is
  elapsed playback time modulo `D`. A logical advance across multiple wraps uses
  the same remainder rule; overdue frame selection follows the
  [timing-miss contract](timing-misses.md). A normal wrap resets only clip playback
  position, not the whole stimulus instance, its other parameters or the epoch clock.

V07 governs pause-on-absence, continuity across compatible adjacent epochs, explicit
playback resets and fresh trial initialization. The epoch scheduler continues to
own scene transitions; a clip ending, holding or looping never ends, extends or
inserts an epoch. This policy alone does not add reverse playback, audio, arbitrary
seek controls or new playback-rate ranges.

Keep decoder work and loop/resume preparation off the render thread under V04.
The renderer's video instance owns presentation state; the decoder provides prepared
frames and explicit completion/error status. Do not treat an empty decoder queue,
timeout, corrupt/truncated stream or decode failure as normal clip completion.
Confirmed decode failures follow E06. Overdue-frame catch-up follows V10; bounded
decode-ahead preparation follows the [V11 media contract](media-preparation.md).
Temporary target-frame unavailability uses V10's logged last-valid-image hold,
distinct from normal clip-end hold. [Resource limits](worker-control.md) and [provider interfaces](resource_types.pyi) bind loop/resume preparation, with numeric inputs still required; hold/loop cannot conceal failure.

## Verification boundary

Future implementation checks must cover repeated/shuffled epoch clocks, rate
integration with retained phase, explicit state curves, absence/return, fresh trials,
hold and multiple loop wraps, persistence of explicit end behavior, and distinguishing
normal completion from starvation/failure. No behavioral checks or rig measurements
have been performed. Physical timing and seamless loop performance require evidence.
