# Visual Stimulus photodiode marker contract

Governing rule: [V22](../../docs/architecture/visual_stimulus.md#v22). Presentation follows
[V20](presentation.md), recording/replay [V13](replay.md), and physical alignment
[SYS-004](../../architecture.md#sys-004). The frame-alternation/periodic-landmark
strategy and the six-frame marker every 60 submitted frames are accepted.
Physical optical timing validation remains a rig obligation.

The operator may disable the pulse independently of pacing. Disabled pulses keep
stored placement but do not require that target to be enabled or available, do not
draw a patch and retain null marker fields in submission evidence. Explicit pacing
still requires an active output. Enabled pulses validate target and rectangle at Setup.

## Sequence definition

Pattern version 1 uses two symbolic levels, H (bright) and L (dark). Let `i` be
its zero-based, trial-relative photodiode-output submission index and `p = i % 60`.
For `p < 3`, emit H; for `3 <= p < 6`, emit L; otherwise emit H on even `p`
and L on odd `p`. The six marker frames are included in the 60-frame period,
not appended to 60 alternating frames. This is a frame-count pattern, not a timer.

| Submission indices | Intended levels |
| --- | --- |
| 0–5 | H H H L L L |
| 6–11 | H L H L H L |
| 58–65 | H L H H H L L L |
| 66–71 | H L H L H L |

Reset `i` to zero for the first submission of each trial. Increment once per
submission attempt on this output; do not increment for discarded, unsubmitted
candidate images, other outputs' swaps or elapsed refresh intervals. Associate
landmark cycle `i // 60` and position `p` with the existing frame evidence.
A failed/unknown attempt does not prove that the corresponding level appeared.
Stop at the actual trial cutoff even if the final landmark is incomplete.

## Ownership and frame association

Use one configured output-space patch on the designated photodiode projector. Patch
geometry, bright/dark levels and the versioned pattern definition resolve during
Setup; validate that the patch is visible within that output and has distinct finite
levels. Do not inherit a particular face, channel or patch rectangle
from the old implementation. Mapping to the real detector remains a rig input.

The rendering worker composites the marker into the same final image presented and
captured for that output. It cannot be obscured by scene layers or independently
updated by another timing loop. Its calibrated/uncalibrated output interpretation
follows V23 and finite clipping V21. The [color pipeline](color-pipeline.md) places
its opaque linear-RGB patch after scene/spatial composition and before the shared
per-output correction. Preparation checks distinct resulting code triplets. Trial stimuli do not directly write the reserved patch.

Use a trial-relative sequence index tied to photodiode-output submission attempts,
not `elapsed_time * nominal_refresh_rate`, video-source frame count or a recording
worker's admitted-video count. Associate the intended patch state, landmark identity/
position, sequence version, render-group ID and output ID before the corresponding
swap. Record attempted, failed and unknown submission outcomes honestly under V20;
no software counter is a physical displayed-frame counter. Candidate images never
submitted do not constitute optical events.

An unchanged held video image still receives the marker for the current submitted
output frame. Epoch changes do not reset the sequence or inject unlogged markers.
Do not synthesize catch-up marker flashes after a rendering delay or extend a trial
to finish a landmark. Detailed per-frame evidence follows E13; disabling saving does
not disable the selected display marker, but prevents a guarantee of full trace-to-log
reconstruction. Outside trials V19's uniform Idle background applies without a
flashing trial marker.

## Optical interpretation

Retain both the recorded intended sequence and measured analog trace; a thresholded
edge is a measurement with its own detector/analysis assumptions. Repeated marker
cycles cannot uniquely identify an arbitrary recording fragment. Use trial anchors,
neighboring sequence context and measured timing to align, and label ambiguous or
missing intervals instead of forcing a match. A held displayed frame can resemble
an intentionally prolonged marker level. Never treat every three-frame high run
as definitive proof of a landmark or of a fixed number of lost frames.

Each six-frame landmark has four internal same-level boundaries with no luminance
transition (two within H H H and two within L L L).
Any timing assigned there from refresh assumptions or another signal is inferred or
separately measured, not a photodiode edge. Rising and falling transitions may also
have different response delays; quantify them on the rig. One patch cannot prove
simultaneous illumination of the whole projector image or of other projectors.

Patch placement/levels, thresholds, detector response and display timing remain
deferred for rig measurement. Trace-matching interfaces, sequence/log schemas and
resource interfaces remain local work; the reference vectors above establish only
the intended logical pattern, not measured optical behavior.
