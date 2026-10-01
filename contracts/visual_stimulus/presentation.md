# Visual Stimulus presentation pacing contract

Governing rule: [V20](../../docs/architecture/visual_stimulus.md#v20). State/projection follows
[V15](projection.md), software timing [V10](timing-misses.md), and recording/replay
[V12/V13](replay.md). This declaration is not a verified multi-projector runtime.

## Configuration and capabilities

Each physical output explicitly selects 8 or 10 RGB bits per channel and must pass
[framebuffer precision validation](output-precision.md) against actual resources and
its adopted calibration profile. This does not change the float32 working pipeline
or establish physical projector precision.

Use two session modes with explicit requested swap intervals:

| Mode | Photodiode output | Other outputs |
| --- | --- | --- |
| `photodiode_only_vsync` (default for new profiles) | 1 | 0 |
| `all_outputs_vsync` (selectable for rig testing) | 1 | 1 |

Resolve the designated photodiode output through a stable output identity, not a
hard-coded tank face, monitor enumeration index or window creation order. The mixed
mode requires exactly one designated active output. Output identity names a physical
presentation target; surface-to-output mappings remain separate under V15.

Apply the requested interval with the corresponding OpenGL context current under
[GLFW's swap-interval interface](https://www.glfw.org/docs/latest/window_guide.html#buffer_swap).
Outputs assigned different intervals require independently controllable presentation
contexts; a single atlas window spanning all projectors cannot provide those controls.
They may share prepared GPU assets while retaining context-local resources where
required by OpenGL. Do not create additional rendering-worker processes.

New display profiles default to `photodiode_only_vsync`, as current CephVR runs on
the rig ([DisplayProfile](display_profile.py)); preserve explicit saved selections.
Resolve the mode, output mapping and intervals at Setup and lock them at Start;
changing mode requires fresh Setup. Initial [startup Idle](startup.md) uses the same
capability checks against its adopted saved display settings, without claiming
session Ready. Do not infer an automatic mode switch from a timing miss, invent a performance threshold,
or weaken V10 by pausing/extending the trial to wait for missed refreshes.

Reject invalid mappings or an unsupported required control mechanism before Ready.
Driver/compositor overrides can prevent the requested behavior even when the API
accepts it. Log requests and available capability/driver evidence separately from
observed behavior; do not report effective VSync or zero-latency immediate output
merely because a swap call returned without a reported API error.

## Frame execution and observations

Take one pending result batch, process due logical transitions and evaluate one
state at a recorded host-monotonic time. Render all four views from that state before
the group's presentation calls; never apply newly arrived input between views.
A render-group identity ties those images together without claiming simultaneous
physical display. Repeated video holds remain the same selected source image while
other scene state and the render-group identity advance normally.

In the mixed mode the photodiode output supplies the intended refresh pacing; the
other outputs request immediate swaps for their image from the same group. Avoid
an independent sleep/rate limiter on each immediate output or a separate update
loop that creates newer state for those views. Concrete swap order, cross-context
fences/resource ownership and frame-admission bindings remain local implementation
work, and must be retained with presentation provenance. In all-output VSync mode,
sequential swaps may introduce additional waits; performance must be measured, not
assumed to equal a single-output refresh rate.

Record per-output swap-call entry/return host times, requested interval, render-group
identity and reported error/unknown disposition. A returned call is software evidence,
not optical onset or proof that the same frame appeared on every output. Keep state
sampling, GPU completion (where measured), swap calls, video admission and photodiode
trace evidence distinct. [Review playback](encoding-options.md#review-timing) is
constant-rate at the pacing output's nominal refresh; per-output swap times remain
independent evidence. V13 replay reproduces recorded states/output sequences;
it cannot reconstruct tearing/scanout from a swap timestamp alone.

A photodiode observes only its calibrated patch on its projector. Do not assign its
edge time to other outputs or to every pixel of that output. The
[photodiode contract](photodiode.md) binds V22's selected marker strategy and remaining
sequence/measurement work; no legacy marker defaults or physical wiring are adopted
by selecting this presentation mode. SYS-004
retains hardware-recorded scientific alignment authority without a live SpikeGLX
connection. Confirmed required-output failure follows E06; V10 owns timing misses.

## Outstanding work and evidence

Typed output/window schemas, swap ordering, GPU-resource lifetime, bounded recording
and presentation metadata transport remain local contract work. Optical calibration,
photodiode assignment and full-load measurements stay deferred until rig access.
Check both modes with all four projectors, compare per-output timings, detect driver
settings that override requests and verify that rendering/recording share one state
without serial-wait assumptions. No implementation or rig behavior is verified here.
