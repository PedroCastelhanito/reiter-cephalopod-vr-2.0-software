# Visual Stimulus replay from trial records

Governing rule: [V13](../../docs/architecture/visual_stimulus.md#v13). E13 owns lossy review
recordings and the save switch; V12 owns required detailed evidence. This declares
the analysis software's offline reconstruction contract. The experiment backend owns
only the recipes and evidence described below; it has no offline player/export CLI.
The request/report/export schemas are shared interface declarations, not an
implemented analysis tool or a demonstrated pixel-reproducibility guarantee.

## Trial recipe and evidence ownership

Each trial must identify an immutable authored-program snapshot and retain its
resolved occurrence plan, durations, parameter definitions, starting state and seeds
in the Visual Stimulus-owned `_stimulus_LOG.json` for every started trial, even with Save Visual Stimulus data
Off. This file is the complete PreparedTrial recipe; there is no separate recipe output.
Central E07/E04 metadata keeps its verified reference, seed and compact occurrence
summary, never a second full plan. Do not require the original editable program file
or regenerate a random plan from a seed instead of retaining the resolved plan.
[Prepared artifact schemas](stimulus-schema.md) and [file ownership](runtime-bindings.md) bind this representation.

The stimulus log retains the prepared replay manifest in either save mode. With Save
Visual Stimulus data On, the renderer's recording thread additionally writes lossless scientific
state/presentation evidence (`_stimulus_frames.jsonl`), separately from the lossy
review-video pixels. The manifest identifies by content fingerprint every external
image/video/mesh/texture and projection/calibration resource consumed by the plan,
including transitive dependencies. Retain exact effective renderer settings, output
mapping/dimensions, shader/renderer identity and replay-relevant decode/color-transform
and graphics-environment provenance. Do not collect unrelated environment inventories.

The manifest is the narrowly scoped exception to E04's minimal asset/provenance
policy, not a second session log. Reference external originals; CephVR does not copy
media/arena/calibration files into the session or create a managed asset archive.
The operator must preserve the original content. Retained authored-program snapshots
and effective numeric settings remain session/trial records, not external-asset copies.

Store each external dependency's logical reference and SHA-256 content digest in the
Visual Stimulus manifest, including dependencies embedded/referenced by arena assets as applicable.
Embedded bytes are identified through their containing asset plus a stable subresource
reference. Resolve external references through the configured asset root; replay can
use a relocated root or explicit mapping to the same content. Do not require original
absolute machine paths or search unrelated directories silently. Verify each resolved
asset's digest before using it for replay; missing/mismatched content blocks
reconstruction with an asset-specific diagnostic, without falling back to the lossy
review video.

Cache each asset's SHA-256 digest in a local digest cache keyed by path, size and
modification time; re-hash only when one of these changes. [Read protection](asset-lifetime.md)
is still acquired before any read or hash. The cache is a speed-up, not provenance:
the manifest always records the digest.

A digest identifies bytes; it does not preserve them. Asset hashing is setup/replay
work, not per-render-frame pixel hashing, and is distinct from E07's representative
media-decode checks. V04's [asset lifetime](asset-lifetime.md) binds protection before reading/hashing and
retention for prepared consumers. Analysis software must independently establish
source stability for its replay readers. A manifest alone is not source protection
or completed replay preparation.

## Log the inputs actually rendered

For each evaluated render-state ID, retain the effective inputs necessary to render
that state without rerunning live tracking or re-integrating feedback. These include
active instances, phases/offsets/poses, evaluated parameter/function values or a
losslessly specified equivalent, applicable render time and resolved scene settings.
Preserve numerical values at the precision actually consumed by rendering, with
explicit units/types, rather than rounded display strings. Shared immutable settings
and state referenced by several outputs need not be copied into every frame record.

For each output frame, retain its render-state reference, output/frame ID, software
timing observations and attempted/confirmed/failed/unknown submission evidence. Keep
capture/recording disposition separately. For video textures retain the actual asset,
source-frame identity/PTS and loop/playback generation sampled, target media position,
and whether that image was a transient hold, an ordinary clip-end hold or current
content. Record V10 omitted epochs and V12 recording omissions with their distinct
meanings. Do not infer actual media selection solely from intended playback time.

Temporary decoder starvation holds the same instance's valid image while its target
clock advances. Log affected frames and a compact interval account: instance, held
source identity, first/last observed starvation times, target times and recovery or
termination reason. End an interval at recovery, deactivation/reset, trial end or
failure, without inventing an unseen recovery. Planned blank/static epochs are not
starvation. Other scene animations continue; holding a video image does not freeze
the whole scene. Compact administrative counts remain distinct from detailed E13 data.

If replay-required evidence cannot be retained or written while saving is enabled,
use the existing required-logging failure path. A lossy review video is not a fallback
for missing scientific state. When saving is Off, retain only the already-agreed
administrative/setup data and do not claim actual-output replay is available.

## Offline reconstruction in analysis software

The following reader/render/export responsibilities belong to analysis software.
Validate complete recipe/evidence coverage and content identities before claiming
faithful reconstruction. Load the recorded program/resources and apply the recorded
render inputs and actual source-frame selections, rather than rerunning live input,
randomization or current-time functions. Analysis software must use a rendering
implementation compatible with the recorded renderer and numerical/color pipeline;
its entry point must not operate the controller, tracking, devices or live rig.
Process offline at whatever speed is required and support lossless export of the
reconstructed final-output frames with recorded timeline/lineage retained.

Reproduce the recorded software submission sequence separately for each output.
Repeat a held source image where the evidence says it was used; do not repair missed
epochs or replace starvation with ideal playback. Reconstruct a frame omitted only
from the review-video recording if its render state and submission evidence survived.
A frame rendered but not confirmed submitted must not be presented as known displayed.
Unknown or incomplete intervals remain explicitly unknown; fail an exact replay
request for those intervals rather than silently synthesize missing evidence.

Replay reads the complete evidence lines that exist; an incomplete final line is
discarded (V28). There is no separate recovery step. If the closing Completion line
is missing, label the output "partial, up to render group N"; never present it as
complete-trial replay or synthesize missing state. Full-trial replay requires a
complete file. Validate the recipe, dependencies and frame evidence before export,
retain original trial/output/frame identities and report each output's
reconstructable coverage and unknown intervals. Complete lines are not necessarily a
continuous sequence of confirmed presentations; missing submission outcomes stay
unknown even when the render state survived. Do not silently downgrade a full-trial
request to partial replay.

This reconstructs software output evidence, not projector photons. Recorded software
submission times are not measured scanout or light-onset times. Physical display
reconstruction requires the separately deferred hardware/pulse evidence.

## Verification scope and remaining work

Lossless export preserves the pixels produced by the offline render. It does not
by itself prove equality to the original GPU output. Original media bytes, decoder
behavior, shader compilation, GPU/driver and pixel/color pipeline can affect pixels.
See the [GLSL specification, sections 4.8–4.9](https://registry.khronos.org/OpenGL/specs/gl/GLSLangSpec.4.60.html)
for permitted numerical variance. Record compatible provenance and report mismatches;
never promise bit-identical reproduction on arbitrary hardware from a seed alone.

Verify the program/plan snapshot, external asset digests, recorded state coverage and
replay-relevant software/graphics provenance. Reject unsupported schema/renderer
compatibility or incomplete required state rather than silently substituting current
defaults. Report environment differences explicitly; never convert provenance matches
into a claim of pixel equality. [Evidence/export binding](evidence-format.md) requires explicit supported compatibility and reports differences.

Do not capture original-output pixel fingerprints, either every frame or sampled
reference frames, for production replay verification. No hashing-only GPU readback,
GPU digest pass or comparison to original pixels is required. This leaves the existing
review-video capture path and required render-state logging intact. Replay/export
reports must distinguish input/state validation from original-pixel verification;
label the latter unverified. Lossless export describes encoding of the reconstructed
frames only, and cannot upgrade that verification claim.

[Typed evidence/storage/export interfaces](evidence-format.md) and [resource/native adapters](runtime-bindings.md)
bind these declarations. Analysis software implementation and validation remain
outside this repository: stream semantic validation, protected readers, compatible
rendering and lossless export. Experiment-side checks cover recipe/evidence retention;
they do not validate an analysis replay implementation. Analysis acceptance must cover
relocated/missing assets, held frames, feedback poses, dropped review samples and
partial coverage without production original-pixel fingerprints.
