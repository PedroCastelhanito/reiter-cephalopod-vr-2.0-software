# Visual Stimulus output-range contract

Governing rule: [V21](../../docs/architecture/visual_stimulus.md#v21). Rendering follows V04/V17,
output correction V15, recording [V12](recorded-outputs.md), and replay
[V13](replay.md). Implementation status and test limits are recorded in
[the Visual Stimulus report](../../reports/visual_stimulus.md).

## Finite clipping semantics

At each declared output-range boundary, clamp finite values componentwise to the
supported lower/upper limits. Do not change the authored parameter values, rescale
the frame, change mean brightness to make room, or alter the trial schedule. Merely
being outside the range is nonfatal; Setup warns about predictable excursions rather
than rejecting an otherwise valid program. Report those warnings through existing
configuration/status channels without requiring another approval prompt.
Pure validation coalesces predictable authored RGB/contrast excursions into a
`PREDICTABLE_CLIPPING` issue per trial while keeping `ValidationResult.valid=true`.
The controller retains the accepted validation revision and projects these valid
results' issues as nonfatal warnings after configuration adoption and Setup reload.
They predict possible source excursions, not measured per-output clipping.

The color pipeline must declare its working spaces, numeric ranges and stage order.
Keep floating-point intermediate values until the relevant defined range boundary;
do not allow an undocumented integer attachment or codec conversion to hide earlier
clipping. Guard bounded-domain color operations and final output encoding explicitly,
including excursions introduced by calibrated output correction. Record the affected
stage so source/compositing clipping is not confused with final-output clipping.
The [color pipeline](color-pipeline.md) binds float32 linear composition and the
`alpha`, `linear_output` and `device_code` boundaries, each clamped to [0,1] with
separate evidence. These bounds are not a physical projector luminance claim.

NaN/infinity, malformed input, unsupported calibration/assets and confirmed GPU or
logging failures retain E06/E07 handling. Clipping cannot turn those failures into
valid pixels. Legitimate finite values are distinct from an undefined calculation;
normal rounding to a representable value within range is not range clipping.

## Evidence without blocking the render loop

For each rendered output image, retain whether clipping occurred and at which
instrumented range stage, linked to trial/epoch, output and render-group identity.
Use bounded GPU-side flags/reductions with asynchronous small-metadata readback when
GPU calculations determine the result; CPU-only range predictions are not proof of
actual per-frame clipping. Do not read back entire images solely for this diagnostic
or introduce original-pixel hashes prohibited by V13. Detailed instrumentation and
queue bindings must preserve the flag even if the corresponding review-video sample
is dropped. Delayed diagnostic results retain their original frame association.

Keep compact affected-frame counters/status warnings and administrative trial summaries
regardless of Save Visual Stimulus data. Detailed per-frame records follow E13 and are not written
elsewhere when saving is Off. Coalesce warnings rather than issuing a control RPC or
session-log line for every affected frame. Required diagnostic loss follows the
existing required-evidence failure path; do not report missing results as no clipping.
Drain admitted required evidence before aggregate Finished under E11/V12.

The worker drains one completed diagnostic result per render group and output,
including results with no clipped stages. Per-output group indices must remain
contiguous; unknown, duplicate or missing results cannot become a successful
Finished report. `TrialTimingSummary` carries `alpha_clipped_groups` (tag 12),
`linear_output_clipped_groups` (13) and `device_code_clipped_groups` (14), including
Save Off. These fields fill the administrative clipping handoff without changing
existing wire tags or claiming optical measurements. The original finalization
deadline bounds pending GPU diagnostics and subsequent recording closure together.

The final-output review image includes the clipped result. Replay uses original
program/material/calibration inputs and the same recorded pipeline interpretation,
with clipping evidence linked to reconstructed frames. Neither records nor replay
claim that the actual projector emitted the requested physical luminance.

Implementation checks must cover exact limits,
finite excursions, nonfinite failures, correction-induced clipping, no rescaling,
Save Off summaries, recording drops and late/missing diagnostic results. Those
checks require separately identified local and Windows/GPU results; the contract
does not establish rig validation.
