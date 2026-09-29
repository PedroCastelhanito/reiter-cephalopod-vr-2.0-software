# VR bounded video preparation

Governing rule: [V11](../../docs/architecture/vr.md#v11). Playback semantics belong
to [animation and playback](animation-and-playback.md), catch-up to
[timing misses](timing-misses.md), and instance lifetime to
[state continuity](state-continuity.md). This is a declared contract, not a runtime.

## Ownership and memory

Decoder work runs outside the rendering thread. It fills bounded queues of decoded
frames carrying media/instance identity, playback generation, source-frame identity,
validated presentation interval and pixel representation. The renderer selects and
owns presentation state; the decoder never changes epoch progression or live pose.
[Decoder ownership](decoder-ownership.md) binds PyAV/FFmpeg background threads in
the rendering-worker process and [local API declarations](decoder_types.pyi); each
context has one serialized owner. Numeric budgets and runtime remain unfinished.

Bound decoded storage in bytes as well as frame slots. Count frame stride and plane
sizes, not just width times height. Budget the aggregate of active and prepared
video queues so adding streams cannot create an unbounded total cache. Account
separately for in-use renderer frames, GPU textures and codec working allocations;
a decoded-queue cap is not proof of a total process/GPU memory cap.

Apply producer backpressure outside the rendering thread when decoded capacity is
full. The consumer must release a frame before its storage is recycled. Retire
obsolete generations on reset/loop/reconfiguration without allowing old decode
completions to replace current content. Same asset does not imply shared playback
position across independent instances. Share immutable resources where compatible.

No full-clip decode requirement or persistent disk-frame cache is introduced. A short
clip fitting the chosen buffer does not create a second authoring mode. Numeric
capacity fields and prepared-session scheduling follow [worker-control.md](worker-control.md) and [runtime providers](runtime-bindings.md); keep
unselected values unset and distinguish resource admission checks from measured
throughput on the rig.

## Preparation and transitions

During Setup, validate the full prepared media plan, source timestamp mappings,
asset compatibility and resource requirements. Streaming sources follow
[asset lifetime](asset-lifetime.md): protected before read/hash and retained across
prepared consumers, without per-trial rehashing or a full-video preload requirement.
Prepare required initial decoded content before the applicable Ready gate. Upcoming
content, loop starts and returns
must use bounded decode-ahead preparation rather than blocking disk/decode work
inside an epoch transition. Preparing the session does not require retaining every
decoded frame for every trial simultaneously.

Pause-on-absence freezes presentation time under V07. Retaining or preparing frames
within the resource budget must not advance it. At a loop/reset, match pending work
to the intended playback generation and source position. Preserve V10 timestamp-based
catch-up; decoding reference frames does not require presenting obsolete frames.

A decoder waiting because its queue is full or no playback work is scheduled is not
stalled. Health/progress checks must distinguish such waits from failure to complete
required work. Invalid media blocks readiness; confirmed failures follow E06.
[V10](timing-misses.md) supplies the logged last-valid-frame hold while a target
frame is temporarily late; readiness must prepare the instance's initial content.

## Remaining work and verification

Source profiles and local decoder ownership/lease interfaces are declared in
[media profiles](media-profiles.md) and [decoder ownership](decoder-ownership.md).
Numeric budgets/defaults, full prefetch/timestamp-index binding, starvation evidence,
worker lifecycle integration and runtime implementation remain local work. Runtime
checks must cover bounded aggregate storage,
full-buffer waits, independent video instances, stale generations, loops and return
preparation. No runtime or rig checks have been performed; initial prebuffering does
not prove uninterrupted decoding for the whole trial.
