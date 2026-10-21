# Visual Stimulus status

Oct21 current rig validation: video On60s → Off Abort5s → On60s retains required
stimulus scientific evidence in all modes, with no encoder in Off; all six combined
videos decode/count exactly, zero requested/actual image mismatches and zero capture
drops in the bounded dummy. Maximum state intervals are36.8833/33.3202/26.6106ms.
The unchanged full20min protocol did not start: long-path output reservation then
MCU PING/cleanup failures block acceptance. No full-texture or optical pass claimed.
See the [combined assessment](runtime.md#current-rig-validation--2026-10-21).


Oct21 `preview-frame-details`: [V01rev30](../docs/architecture/visual_stimulus.md#v01)
adds source/preview FPS to existing exact-session preview state. Completed render
batches and preview swaps feed the shared meter; optional roughly-one-second reports use
the existing bounded worker bridge. They do not block rendering or change scientific
timing/health authority. ARCH-002 cohesion review retains small native-owner and worker
lifecycle hooks in those existing large owners; measurement is separated in
shared/preview_rates.py. Focused rendering/lifecycle, projection and authenticated
transport checks pass (commands/results in LOG). Native appearance and rates need
application/backend restart and remain E15 acceptance work; no running experiment was
restarted for this change.

Oct21 `stimulus-preview-initial-placement`: [V01rev29](../docs/architecture/visual_stimulus.md#v01)
fixes a source-confirmed show-order defect: WindowsPreviewOwner construction can
show its child before placement, and the old GLFW show preceded native frame
correction. Size and visible-frame position now precede owner binding and Show;
Win32 no longer first applies GLFW client-origin coordinates. Manual-move opt-out,
explicit Snap and reopen reset remain covered. ARCH-002 reorders existing operations
in the focused preview owner without new dependencies or lifecycle state.
103 local rendering tests pass (one Windows-marked case excluded), including initial
placement order, manual movement, Snap, reopen, native-close and failed-release
ownership. Ruff lint/format2, Win32 mypy1 and boundaries742/zero pass. A bounded native
GLFW NO_API probe created a hidden300x300 window, positioned its visible frame at
(410,220), showed/polled it and read exactly(410,220), then destroyed it. This proves
first-show frame positioning on this desktop, not renderer/OpenGL, alternate-DPI or
live experiment acceptance. Existing [rig checks](rig-verification.md) remain open.
Application not restarted; no experiment operation sent.


Oct21 `setup-watchdog-cleanup`: [V01rev28](../docs/architecture/visual_stimulus.md#v01)
binds cleanup before Visual Stimulus Setup dispatch. The renderer verifies native
release before confirming an empty session catalogue; the coordinator registers
that catalogue with the supervisor, and the controller retains the dispatch fact.
Dispatched resources/outputs and every registered participant still require exact
cleanup. Native missing-camera failure/reuse, Ready cancellation, recorded10s Abort
and fresh60s normal playback pass; both stimulus videos fully decode with matching
600/3,600-frame counts. Final native GUI inspection confirms terminal log rows
and fresh-Setup gating. The original intermittent PING cause and full
texture-workload/optical acceptance remain open. See the
[combined assessment](runtime.md) and
[evidence](runtime-evidence-2026-10-21/setup-recovery/output-verification.json).

Oct21 `pilot-spikeglx-alignment-inspection`: full SP0003-123824 logs have contiguous
Right-only markers and current images; analog photodiode candidate transition
counts match both trials after short-window averaging. Digital threshold chatter,
analog clipping, candidate-fit outliers and unobserved same-level boundaries
require explicit optical QC; other projectors have no measured optical anchor.
Evaluation gaps reach355.121/94.983 ms despite zero video drops. See the
[current inspection and evidence](runtime.md#pilot-spikeglx-alignment-inspection--2026-10-21)
and [rig follow-up](rig-verification.md#pilot-synchronization-verification).

## Primate/cuttlebase texture mismatch — 2026-10-21

Oct21 `setup-texture-progress`: [V04rev20](../docs/architecture/visual_stimulus.md#v04)
and [E08rev178](../docs/architecture/system-contracts.md#e08) retain initial decode,
upload and GPU-fence completion before Ready, now with visible stages and counts.
CPU Setup validates all authored images (compatible repeated images reuse validation);
graphics Setup fills the bounded initial cache, including every first-use anchor.
Counts distinguish per-trial validation from initial GPU residency; they are not a
percentage of the whole protocol. Later images continue bounded prefetch during playback.
The worker sends at most one optional progress report in flight through existing
operation RPCs; repeated counts are throttled to one second, stage/completion changes
emit promptly. Controller generation/session/command/deadline checks publish the
existing participant progress field consumed by the GUI action log. Delivery failure
cannot fail Setup, and progress grants no Ready/completion or health evidence.
ARCH-002 review keeps formatting/throttling and controller admission in focused
helpers; existing resource/session orchestrators only call them. Resource prepare's
509-line warning reflects its cohesive file-to-manifest pipeline; no new dependency,
runtime state machine, configuration key or schema was added.

Validation: combined renderer/controller suite 1,195 passed, 4 skipped, 8 deselected;
10 offscreen GUI action-log checks pass. A final preservation of first-service
cancellation/deadline ordering passes 159 renderer/lifecycle checks. Ruff lint/format
323 files, Win32 mypy277 sources, boundaries742/zero and whitespace checks pass.
An earlier combined run hit the existing 20 ms reservation-thread scheduling test
(1,193 passed); it passed alone and on the final combined rerun. An initial callback
type-inference error was corrected before the passing static run.
[Raw test results](visual-stimulus-evidence-2026-10-21/texture-mismatch/setup-progress-tests.txt)
and [source/command context](visual-stimulus-evidence-2026-10-21/texture-mismatch/setup-progress-context.json)
retain scope. No app restart or native visible-progress/full-protocol run was made;
those remain in the [rig checklist](rig-verification.md).

Owner session `SP0003-145623` (20261020_ephys-pilot) confirms actual renderer
selection divergence, not merely preview labels. Read-only full JSONL inspection
of both trials found 16,381/18,016 and 16,410/18,001 texture render groups with
mixed image families across outputs. At least one mixed group occurs in 923/1,000
Primate and 933/1,000 Cuttlebase texture presentations; 887 and 878 respectively
are mixed in every observed group. Grey intervals are excluded. All prepared
texture epochs and all recorded requested selections agree across the four image
families. Desktop/saved programs differ only by presence of GUI sequence metadata
keys (batch/repetition/subgroup fields); no differing shared values were found.

Example: first trial at 18.6006314 s, occurrence62, requests image193 on all four
screens; Left retains image139 while Front/Right/Bottom select193. Records explicitly
label the stale selection `residency_hold`. Under [V04](../docs/architecture/visual_stimulus.md#v04),
`ImageResidency.select` selects independently per instance and holds its previous
texture when the requested resource is not resident, without delaying the clock.
This explains mixed screen content. The protocol alternates300 ms texture/300 ms
grey. Dedicated measurements below identify the upload throttle; recorded selections
alone do not isolate loading-stage costs. The recorded renderer source fingerprint
is retained in [asset verification](visual-stimulus-evidence-2026-10-21/texture-mismatch/asset-verification.json),
but no exact Git revision is recorded; the inspection tree is dirty. All664 tested
source images match the saved recipe hashes and sizes.

[Reproducible inspection and hashes](visual-stimulus-evidence-2026-10-21/texture-mismatch/summary.json)
and its adjacent `inspect_session.py` retain counts, affected zero-based epoch IDs,
examples and provenance. Method: repository Python3.11, full parse of both renderer
JSONLs and prepared recipes, consistency assertions, no runtime/device commands.
Renderer evidence is not optical measurement; historical MP4s were not decoded.
Planned epoch labels alone do not establish delivered stimulus identity for this session.

The confirmed upload bottleneck was one 1 MiB chunk per render update: the four
images expand to 41,297,200 bytes and required 45 upload turns, or 750 ms at 60 Hz
before decode, against a new set every 600 ms. Representative native decoding
cost about 113 ms per set; GPU transfer calls themselves took only milliseconds.
[Original uploads](visual-stimulus-evidence-2026-10-21/texture-mismatch/baseline-upload.json),
[corrected uploads](visual-stimulus-evidence-2026-10-21/texture-mismatch/final-upload.json)
and [one-chunk paced baseline](visual-stimulus-evidence-2026-10-21/texture-mismatch/baseline-cache.json)
retain measurements: the baseline has 1,025/1,480 mixed groups in the first 60 s of
each saved trial. Exact GPU pixel readback passes before and after the change.

[V04 revision 19](../docs/architecture/visual_stimulus.md#v04) / E14 policy 19 now
bound a turn to four 1 MiB chunks, reducing this set to 12 turns. Upload completion
skips trailing unused contexts; fences cover only contexts with actual allocations,
including partial uploads and retirement. Float32 RGBA, the single decoder, next-use
prefetch, first/held anchors, resource budgets, clocks and late-image evidence remain
unchanged. ARCH-002 retains the existing focused GPU owner and explicit texture-list
interface, with no new dependency or process.

A remaining pause was isolated to a 104.10 ms generation-2 garbage collection in
the loader thread, which blocks other Python execution under the GIL. The
[GC trace](visual-stimulus-evidence-2026-10-21/texture-mismatch/final-cache-gc.json)
retains attribution. A small stdlib PreparedHeap owner now collects Setup garbage
within the original deadline, freezes the existing prepared graph after graphics
preparation, and unfreezes on cleanup (including failed/cancelled Setup). New objects
remain collectible, prior GC enablement is preserved, and foreign frozen ownership
is rejected. The existing preparation orchestrator delegates this separate concern;
its large-file cohesion exception is unchanged. Tests cover deadline/foreign-owner/
reuse and real isolated-interpreter collection of new cycles and release of old cycles.

[Final native result](visual-stimulus-evidence-2026-10-21/texture-mismatch/final-prepared-heap.json):
200 presentations, 3,600 texture render groups, zero holds/mixes and every tested
onset current, including the second-trial transition. Each saved trial ran 60 s
at requested 60 Hz with four hidden RTX 5060 Ti contexts and protected real PNGs.
The 1 GiB budget reserved 551,476,536 bytes for scene/review obligations; peak total
reservation was 1,069,647,336 bytes. Cache-service p99 was 1.91/1.82 ms, maxima
8.66/8.72 ms. No GC callback exceeded the probe's 5 ms reporting threshold.
This is not full-rig acceptance: no projector swaps, cameras, compositing or review
recording were performed, and other processes were not controlled. Intermediate
holds and long calls remain in dated evidence. Restart/fresh Setup and the complete
20-minute combined workload remain in the [rig checklist](rig-verification.md).

Final checks: 336 tests pass, 1 skipped, 1 rig/platform case deselected, plus 82
contract subtests. Ruff lint/format 177 files, Win32 mypy 161 sources, boundary check
746 modules/zero violations and whitespace/local-link checks pass. Existing large
backend owners are unchanged except focused preparation delegation; no new oversized
module is introduced. [Commands, source hashes and limits](visual-stimulus-evidence-2026-10-21/texture-mismatch/fix-context.json)
retain provenance, regression failures and intermediate attempts. The application
was not restarted and no protocol/image/calibration values were changed.

For this workload, bounded ahead-of-time preparation is preferable to retaining
all used float32 RGBA images (9.19+9.23 GiB across both trials) under the1 GiB
configured asset budget. [PsychoPy timing guidance](https://psychopy.org/general/timing/reducingFrameDrops.html)
recommends preparation before onset and expensive updates during intervals;
[StaticPeriod](https://psychopy.org/api/core.html#psychopy.core.StaticPeriod) explicitly
accounts for loading time and reports overruns. [Psychtoolbox PreloadTextures](https://psychtoolbox.org/docs/Screen-PreloadTextures)
uploads textures before a trial and reports residency success subject to VRAM.
These approaches do not themselves guarantee optical synchronization of independent
projectors. V04's existing per-instance late-image evidence/fallback remains unchanged;
an atomic fallback or fail-on-miss experiment policy would require a separate choice.


Oct21 `quiet-recording-metrics`: owner requested no terminal recording_metrics JSON.
Removed the recording-thread summary emission and its dedicated renderer logger
setup. Internal capture metrics, V12/E13 evidence, output closure and error handling
remain unchanged. ARCH-002 removes now-unused logger plumbing without dependencies
or new policy. Existing recording tests retain cleanup/evidence assertions and check
that cancellation emits no metrics summary.73 recording tests pass with native file
access; scoped Ruff lint/format16, Win32 mypy15 and boundaries741/zero pass.
Initial local run exposed an accidentally removed live metrics alias (restored) and
sandbox extended-path publication failures; final checks pass. Runtime not restarted.

Oct20 playback follow-up: owner retained log since497633616783900 confirms Setup
8d62c7cb-805e-4ec2-a02d-276960852ba8 Ready and StartSession
63918951-4b22-407f-98e4-baf6adf44f6f activated, followed by cannot-add-resources-after-Ready,
Stopped-conditions-missing and unregistered-cleanup errors. Source identifies lazy
ImageResidency.service registering each GPU obligation on first allocation, including
future images first loaded during playback. V04rev18/E08 now predeclare all planned
GPU identities at attach during Setup (one batch through the existing preparation
callback). Lazy allocation/eviction and1GiB budget remain unchanged; GL owner retains
release proof for never-allocated entries and does not claim fenced/live allocations
released prematurely. CPU preparation does not own these GPU release facts.

202 rendering/lifecycle/resource tests pass,1 native deselected: a sealed registration
callback rejects any playback addition while the bounded-cache test loads future
images; both single/batch registration paths covered. Cleanup test verifies never-
allocated releases while failed fences retain allocated obligations. Initial lifecycle
assertion expected old individual announcements, updated to verify the batch instead.
Ruff/format, Win32 mypy2 pass; boundary checker740/zero. ARCH-002 reuses existing
residency/attachment/preparation callback without new state machine/dependency;
session.py remains the existing cohesive resource-lifetime owner above500 lines.
Memory admission and Setup/Start now have owner-provided native evidence, but full
playback, Stopped evidence and cleanup after reload remain unverified.

Oct20 `setup-watchdog-cleanup`, output-specific GPU allocation: owner screenshot
confirms minimum image residency budget rejection. Source review found each source
uploaded to all four contexts regardless of consuming surfaces. V04rev17 now scopes
ImageSchedule's immutable source records to the union of consuming outputs across
trials/epochs, accounts only those copies, and ImageGpu preserves output-indexed
bindings with empty unconsumed slots. Release skips empty slots, retaining existing
fence and failed-resource retry semantics. No format/precision, timing, cache-budget
or physical-screen behavior change. ARCH-002 uses existing schedule/upload owners;
no dependencies or new configuration. No modified module crosses500 lines.

[Calculation](runtime-evidence-2026-10-20/gpu-memory/calculation.json) and its
[reproduction script](runtime-evidence-2026-10-20/gpu-memory/calculate.py) use the saved
Pedro20min protocol and retained calibrated display snapshot. CPU preparation of1920
source assets completed in63.55s without native GPU operations. Fixed scene/preview/
calibration reservations426,138,936 bytes; two review capture allocations125,337,600;
minimum images165,188,800 (82,594,400 anchors +41,297,200 held +41,297,200 next).
Total minimum716,665,336 bytes =683.465MiB, versus1,212,231,736 =1156.074MiB before
output scoping; existing1GiB limit therefore admits the calculated working set.
Image texture copies fall75% for single-screen crops. Prefetch can grow toward the
budget; this is minimum accounted memory, not measured peak VRAM or driver overhead.
Review calculation includes both trials at1280x720, RGBA8,15 slots. Native Setup must
confirm effective display/calibration unchanged and actual rendering/cleanup.

201 rendering/resource/lifecycle tests pass,1 native test deselected; union sharing,
physical/angular surfaces, sparse indices and release covered. Ruff/check/format,
Win32 mypy4 and boundaries740/zero pass. First calculation reached completion but
failed formatting unused-source output metadata; rerun corrected evidence and uses
recording layout rather than preview layout for recording buffers. Source tests and
calculation do not establish a physical rig pass. Numerical capacity errors now
include fixed/image/total/limit bytes for future diagnostics.

Oct20 latest log check: [emergency496983556709800](emergency-496983556709800-d4fe31b4-f81c-47f5-8500-2fe8b9c0eca5.json)
(controller c401b963-bd3d-4422-a5bd-39047d86a851,14:35:46 JST) contains three
ReportWorkerLifecycle INCOMPLETE_CLEANUP errors and unconfirmed SpikeGLX stop.
No original Setup error or RPC timeout is present. Launcher recovery record for that
generation reports all_owned_processes_absent=true at14:36:37 JST; process absence
is not proof of resource/output cleanup. Config/runtime source edits predate launch,
but this report does not show the effective Setup policy. No newer emergency report
found in reports. Requested first GUI Setup-failed line to determine trigger; no
new code change or native success claim from this evidence.

Oct20 next attempt [emergency evidence](emergency-496811385853700-5cdaf1f0-6254-45e6-bcc7-ef40924a9cac.json)
records ReportWorkerOperation with its original peer deadline already expired.
This report does not reveal the retained executor failure; it establishes that
post-execution delivery triggered renderer loss. Runtime now skips an already-expired
result send after retaining the exact executor outcome, leaving the existing E06
query path available. It neither renews execution deadlines nor claims cleanup; actual
in-budget receipt loss still follows the existing failure path. Owner explicitly
approved Setup180s (E06rev78), replacing60s in experiment_config.toml; trial timing and
cleanup/recovery budgets unchanged.35 configuration/transport tests pass, including
expired delivery and existing receipt-loss behavior; Ruff/format, Win32 mypy1 and
boundaries740/zero pass. ARCH-002 keeps the existing ledger/query owner without new
state/dependencies; runtime module remains below the cohesion warning threshold.
Full texture Setup and native cleanup remain unverified after reload.

Oct20 next renderer attempt: [emergency report](emergency-496554628674800-c3caaf3a-1259-4e3f-b68d-907a27778209.json)
identifies ReportWorkerHeartbeat:389,959 bytes,6.934ms remaining deadline and11.613ms
elapsed. This establishes exhausted remaining Setup time at resource registration;
it does not measure the preceding preparation stages or prove memory exhaustion.
The prior asset release error is absent, but supervisor cleanup is still unconfirmed.
E08 permits multiple append-only obligations per revision: NativePreparation now
predeclares authored asset intents per trial, waits for one batch receipt, then uses
the unchanged protected-source opening/validation path. Transitive discovered assets
still register before creation. Lifecycle's single and batch paths share exact identity,
Ready sealing and original deadline checks. No timeout or memory-policy change.
ARCH-002 adds the callback through existing preparation ports; session/lifecycle remain
cohesive existing owners despite size warnings.172 resource/lifecycle/coordinator/
communication tests pass, including1,920-resource single-receipt/repeated-key identity
checks and native preparer batch wiring. Ruff/format, Win32 mypy4 and boundaries740/zero
pass after fixing callback typing/formatting. Full-workload Setup duration and native
cleanup still require rig evidence; this removes repeated catalogue transfer work,
not every possible preparation bottleneck.

Oct20 renderer-exit follow-up: [raw emergency report](emergency-496221647855400-f4487176-3678-4f2e-aa70-e21f515d48c0.json)
for controller faed0faf-a80c-42b7-9e73-6996bcd06d7e records RPC DEADLINE_EXCEEDED
and unconfirmed asset image_222_bottom. It does not identify the RPC or prove a
native crash, GPU exhaustion, or the reason for the timeout. Source review finds
NativePreparation recorded resource intent only after announcement returned; the
worker records it before awaiting receipt. A lost receipt therefore left an obligation
without local never-created release evidence. Resource owner now retains intent before
announcement; creation still waits for accepted registration, and failed live-source
closure remains unconfirmed (E08/V01). ReportBridge failures now identify RPC,
elapsed/budget milliseconds and message bytes while retaining the original exception
and deadline. ARCH-002 keeps ownership in existing modules; session.py's existing
cohesive resource lifetime owner remains above the size warning threshold, with only
statement ordering changed. Resource/lifecycle106 tests and coordinator/transport74
tests pass. Initial3 fixture errors were corrected by generating demo assets outside
the repository; Ruff/format and Win32 mypy pass. The originating timeout remains
unresolved; full Setup and failure cleanup require rig verification after reload.

Oct20 owner Setup log advances through camera preparation, then fails on the
supervisor's cleanup catalogue capacity. The shared 256-history-entry bound and
registration reply reservation are corrected in the existing supervisor owners;
see [runtime evidence](runtime.md) and E08 rev177. No asset obligations are omitted,
and the byte budget remains enforced. Local 2,049-resource registration/cleanup
passes; full texture-session Setup on the rig remains unverified.

Oct20 `setup-watchdog-cleanup`: profiling the actual two-trial texture protocol found
condition substitution repeatedly rebuilding unchanged frozen settings. Existing
expansion now reuses unchanged frozen models/tuples; changed paths still undergo strict
validation, preserving condition ordering and source immutability under V08/ARCH-002.
No cache, new dependency or process. Local four-batch controller validation improved
1.940s to1.415s; maximum observer-thread pause58.84ms to41.63ms. This demonstrates
avoidable load, not the cause or resolution of the serial timeout.80 affected compiler,
configuration and acquisition recovery cases pass; static checks pass. Native Setup
pending. [Probe evidence](runtime-evidence-2026-10-20/setup-watchdog/validation-load.json).

Oct20 `visual-stimulus-gpu-budget`: owner requested raising the GPU resource ceiling
after Setup reported551476536/536870912 bytes at scene-surfaces. Changed only
resources.max_asset_gpu_bytes in visual_stimulus_config.toml to1073741824 (1GiB),
an operator capacity under [E14](../docs/architecture/system-contracts.md#e14).
TOML parsing and the owning load_file_policies loader confirm the new value and
valid policy binding. Fresh Setup adopts it; no active allocation or prepared session
was modified. Capacity/performance and successful Setup remain unverified.
The supplied INCOMPLETE_CLEANUP, COMMAND_ADMISSION and IDENTITY warnings are retained
failure evidence, not resolved by a larger budget. Matching emergency report:
[emergency evidence](emergency-489843786873500-fd741bf6-3bde-4e72-940a-8a32f9e8e3be.json).
Recovery/cleanup must finish before retrying; no recovery action was executed here.

Oct20 `protocol-final-gap`: owner's Setup screenshot exposed an artifact defect:
generated protocols set final gap_after_seconds to the nonempty string "0".
G01's GUI apply_schedule rejects any final gap, including zero; structural file
validation did not cover this submission rule. Corrected only the final field to
empty in the dummy, Gaussian and Primate/Cuttlebase Desktop/Pedro files and the
two repository protocol copies; natural-texture reproduction now clears it too.
Original failure reproduced and actual ProtocolPage.apply_schedule passes with
real draft/program/Protobuf models for all three schedules (1,3,4 trials).
Lightweight UI-value stand-ins were used; this is local submission validation,
not live GUI load or rig Setup. Existing loaded drafts must be reloaded.
[Verification](runtime-evidence-2026-10-20/protocol-final-gap/verification.json).
This correction supersedes earlier artifact hashes and structural-only validation;
stimulus timing, motion, assets and calibration are unchanged.

Oct20 `bottom-preview-orientation`: owner confirms the dummy trial moves correctly
on the physical rig with the existing calibration (Bottom Y inversion off).
The preview's Bottom raster placement added a reflection along surface X.
[G01](../docs/architecture/gui.md#g01) rev257 removes that extra reflection by
undoing only the portrait quarter-turn, preserving calibrated output flips.
Only PreviewRig's corner order changes; renderer, projector profiles and protocol
motion are unchanged. ARCH-002 review finds the existing small placement method
cohesive; no new helper/state/dependency is needed. Existing oversized-module
boundary advisories are unrelated and no source module was enlarged.

Extended the existing owning pixel-placement test to both axes: before the fix,
only the two Bottom-X cases fail; after it,25 preview/motion tests pass. Ruff check/
format, Windows-target mypy and backend boundaries740/zero pass. Initial wider
pytest attempt had3 temp-directory fixture errors; rerun with a dedicated workspace
basetemp passes. The running GUI has not been restarted; native preview confirmation
after restart remains pending. Owner's physical confirmation is not an instrumented
optical measurement and does not close pitch/mask/tearing checks.
[Evidence](runtime-evidence-2026-10-20/bottom-preview-orientation/preview-fix-validation.json).

Owner-requested [dummy direction trial](../protocols/dummy_bottom_direction_95s.json)
is also saved as Desktop/Pedro/dummy_bottom_direction_95s.json under
[G01](../docs/architecture/gui.md#g01) and [V02](../docs/architecture/visual_stimulus.md#v02).
It uses scale15 Gaussian textures with Bottom-linked followers:5s initial static,
then each signed Bottom X/Y translation at30mm/s and signed rotation at10deg/s
for10s, each followed by5s static (13 epochs,95s). Epoch names state source signs,
not unverified physical directions. GUI validation, parsing, expansion, asset existence,
rate checks and byte-identical Desktop copy pass. Calibration files and other
protocols were not changed by the preview fix. Owner confirms rig motion; compare the
restarted preview under the same current calibration. [Validation/timeline](runtime-evidence-2026-10-20/bottom-preview-orientation/dummy-protocol-validation.json).
Existing [rig direction acceptance](rig-verification.md) and separate speed finding remain open.

Oct20 `natural-texture-screen-crops`: completed owner-requested separate session
under [G01](../docs/architecture/gui.md#g01) and [V02/V03](../docs/architecture/visual_stimulus.md#v02).
Desktop/Pedro/media/{primate,cuttlebase} each contains960 PNGs: all240 originals
cropped to Front760x690, Left1030x680, Right1025x695 and Bottom685x940.
Saved Pedro calibration matches runtime_gui; crop boxes form a centered contiguous
Left/Front/Right cross with Bottom centered below Front. Exact native grayscale
samples are retained without resampling; projector offsets stay in calibration.
The source/output hashes, boxes and reproducible ordering are in each manifest.

Desktop/Pedro/primate_cuttlebase_40min.json is a separate Open-loop session:
20min Primate then20min Cuttlebase, each2000 pairs of300ms image/300ms grey.
All four image assets in a pair come from one original. Each collection uses160
images eight times and80 images nine times, globally shuffled with saved seeds.
Untagged PNG samples explicitly use sRGB; grey is127/255 sRGB, encoded as the
corresponding linear background. Physical image extents follow measured pitches;
Bottom uses the calibrated90-degree surface-to-portrait coordinate mapping.

Each collection is split into two10min trials with zero authored gaps: the original
20min source/epoch/boundary serialization alone exceeded the existing8MiB prepared
artifact cap. Each final block's corresponding partial size is4.64MB; full resource
manifests and native Setup remain untested. No resource limit/runtime change was made.
Gaussian protocol bytes remain unchanged. All1920 saved crops pass source-pixel equality;
GUI validation, canonical parsing, full expansion (8000 epochs/2400s), per-image
frequencies and same-source four-screen grouping pass. Eight representative crops
also pass the actual backend image decoder. Initial preparation used two20min trials;
size inspection identified the limit and the final file uses four10min blocks.
No GUI load, full resource preparation or physical presentation pass is claimed;
existing [rig acceptance](rig-verification.md) remains separate.
[Verification](runtime-evidence-2026-10-20/natural-texture-screen-crops/verification.json),
[reproduction script](runtime-evidence-2026-10-20/natural-texture-screen-crops/prepare.py),
[initial inventory](runtime-evidence-2026-10-20/natural-texture-screen-crops/inventory.json).

Oct20 `gaussian-three-trial-protocol`: created the requested [loadable protocol](../protocols/gaussian_scale15_bottom_linked_3_trials.json) under
[G01](../docs/architecture/gui.md#g01) and [V02/V07](../docs/architecture/visual_stimulus.md#v02).
All four scale-15 Gaussian textures link motion to Bottom; baseline is900s,
then100 repetitions each of10s movement followed by20s static for translation
(30mm/s along Bottom X, both signs) and rotation (10deg/s, both signs).
Independent saved direction draws use seeds20261021/20261022; counts are54/46
and59/41, without enforced balance. Same instance/asset identities and reset=false
retain state at static boundaries. Total6900s, zero authored inter-trial gaps.
GUI file validation, canonical parsing and expansion verify1/200/200 epochs and
requested timing/motion; the external scale-15 recipe exists. No runtime code or
dependencies changed. Native load/Setup and physical motion remain untested;
existing [rig checks](rig-verification.md) and speed finding remain open.
[Validation evidence](runtime-evidence-2026-10-20/gaussian-three-trial-protocol/verification.json).

Oct19 `gui-full-rig-test`:600s Gaussian derivative uses20 repetitions of the
existing20s static/10s drift group, retaining accepted calibrated geometry/settings.
Four-output rendering and review encoding produce36001 groups/144004 submissions;
capture/capacity drops, omissions, duplicates and unresolved groups are zero. Full
1280×720 h264 yuvj444p review decode/count passes (600.016667s =36001/60).
Software evaluation-gap median16.659ms, p9919.732ms, max51.765ms; two gaps exceed25ms,
none100ms. Both worst gaps are mainly before first swap; no optical cause or perfect
frame-timing claim follows. All29 resource fingerprints and exact source recipe JSON
match. Current telemetry supports bounded rendering/encoding measurements, with the
first40s missing and scientific Tracking disabled. Original configuration restored.
No renderer/pacing change was justified. Physical speed/tearing/alignment acceptance
and representative full scientific load remain open.
[Assessment](runtime-evidence-2026-10-19/gui-full-rig/native-assessment.json),
[resource/association audit](runtime-evidence-2026-10-19/gui-full-rig/association-assessment.json),
[verification](runtime-evidence-2026-10-19/gui-full-rig/verification.json),
[outstanding rig work](rig-verification.md).

Oct19 `camera-finalization-stimulus-timing-check`: current native software cadence
checked with all3 camera videos and four projector outputs, under
[E13](../docs/architecture/visual_stimulus.md#e13), V10/V12/V28 and E15. Corrected
camera-runtime runs retain671/675/3602 render groups. Median/99th-percentile cadence
and individual worst gaps are in the [native assessment](runtime-evidence-2026-10-19/camera-timing-verification/fixed-run/native-assessment.json).
Max gaps are54.5658/25.8199/48.3826ms; p99 is19.2888/19.0619/18.915ms, with no gap
over100ms. The historical649.2921ms stall did not recur. Historical decomposition
places645.567ms before the first swap, within one static epoch; swap itself peaks
0.8991ms for that group. Its unique cause remains unknown; this is not evidence
that the old stall never recurs. No speculative renderer/pacing change was made.

First Abort run records one startup review-video capacity drop (15/15 slot peak):
670 encoded images for671 render states. All states remain saved. Next Abort and
normal60s encode675/3602 groups with zero capacity drops. All3 stimulus MP4s fully
decode and match submitted encoder counts. Capture loss, renderer cadence and
physical presentation are distinct; occasional25-55ms software gaps mean perfect
frame timing is not established. No instrumented optical/electrical measurements,
Tracking/SpikeGLX workload or full-duration scientific endurance was performed.
Owner confirms photometric calibration works; the old recipe label alone is not a
current calibration defect. Current configuration restored exactly.
[Checks and retained raw evidence](runtime-evidence-2026-10-19/camera-timing-verification/verification.json).


Oct19 `texture-rig-geometry-motion`: [V02](../docs/architecture/visual_stimulus.md#v02)
rev14 and the linked-motion contract now use the reference screen's geometric
center and signed perpendicular distances to target planes for angular flow.
Removed observer dependence from both rates and retained-pivot validation; physical
map translation determines the required texture-space pivot. Reused the existing
compiler/runtime helper and state ownership without new settings/dependencies
(ARCH-002). Drift remains physical mm/s with per-output calibration. Existing
programs with an explicitly subject-centered, off-screen-center spin pivot must
correct that center/reset before Setup; no silent migration. Added coverage for
observer invariance, moved rig planes/center, mapped pivots and runtime integration.
All436 non-Windows/non-rig Visual Stimulus tests pass (2 deselected); Ruff check/
format2, Windows-target mypy1 and boundaries735/zero pass. Existing oversized-owner
advisories are unchanged; this focused helper remains below the review threshold.
Initial sandboxed full-suite run stalled after33 tests and was interrupted; the
permitted rerun completed. Live runtime was not restarted and physical acceptance
remains pending. This angular-motion correction does not establish the cause of
the separately reported linear Front/Bottom speed discrepancy below.


Oct19 open `stimulus-physical-speed-mismatch`: owner observes Front downward motion
faster than Bottom backward motion on physical screens. Earlier synthetic checks
cannot close this finding. Read-only inspection of DUMMY_2_161013's actual logged
phase/period/clip uniforms over1.0005195s infers50 mm/s on both surfaces under its
saved calibration: Front0.122222 mm/pixel (409.091 pixels/s), Bottom0.1375 mm/pixel
(363.636 pixels/s). [Evidence](runtime-evidence-2026-10-19/stimulus-drift-speed/saved-motion.json)
identifies source and recipe hash. This older saved trial is not confirmed as the
current live configuration. Owner confirms current reference measurements are
Front Y22 mm/180 pixels and Bottom Y44 mm/320 pixels. Final recorded-pixel template
matching at three20.5-22.7s intervals gives Front50.0-50.2 and Bottom49.4-49.6 mm/s
within integer-pixel uncertainty (up to2 native pixels), using logged host intervals
and a zero-drop/duplicate/omission encoder outcome. Correlations exceed0.99;
[recorded-pixel evidence](runtime-evidence-2026-10-19/stimulus-drift-speed/recorded-pixel-motion.json).
This checks the recorded GPU result beyond the previous uniform arithmetic, not
optical motion. Need a same-measured-distance travel comparison on the physical
screens and current session binding. No cause established, corrective multiplier
applied or live output changed. V15 is not proof of optical speed.


Oct19 `pre-experiment-output-audit`: four retained Desktop dummy sessions contain
required recipe/state files and their planned review MP4s under
[E13](../docs/architecture/visual_stimulus.md#e13), V12/V13/V28. Recipe byte lengths/
SHA-256 match the evidence references; all29 resource fingerprints per recipe match
currently available external originals. Every review video fully decodes and its
frame count equals retained render groups (4830/2462/2059/1884). Recorded completion
has zero capture drops/unresolved attempts; group IDs are contiguous and all logged
presentation calls returned. These are software submission/recording facts, not
physical presentation or exact-pixel proof.

A timing concern requires bounded investigation before timing-sensitive experiments:
DUMMY_2-160507 has a649.2921ms maximum state-evaluation gap, four gaps over100ms,
and2059 rendered groups across35.621s. 155008 peaks129.844ms; latest160948 peaks
33.049ms. Zero capture drops does not mean uninterrupted rendering. Cause/physical
impact are unverified; continue existing rig timing acceptance rather than infer
encoder loss. All four historical recipes explicitly use photometric_mode=uncalibrated.
The owner confirms photometric calibration is working; that historical label alone
is not a current calibration defect or outstanding acceptance blocker. Preserve
external originals: fingerprints verify availability today, not archival retention.
[Read-only audit and exact evidence](runtime-evidence-2026-10-19/output-audit/assessment.json).
No projector commands, optical measurements, replay/export or full-duration run.



Oct19 `stimulus-calibrated-drift-speed`: [V15](../docs/architecture/visual_stimulus.md#v15)
rev22 makes the existing per-projector physical drift mapping explicit. Independent
and V02-linked texture rates stay in physical coordinates; measured X/Y pitch,
usable geometry and output mapping convert to pixels exactly once. No second
speed multiplier or runtime state was added (ARCH-002). The GUI speed tooltip
explains measured calibration and fresh Setup. Regression coverage follows linked
or independent diagonal drift through unequal anisotropic pitches, cropped/offset
affine maps and portrait Bottom rotation, checking 50 mm displacement in one second
while pixel displacements differ. Nine focused GUI/calibration tests and all20
compilation tests pass. Ruff check/format2, Win32 mypy1 and boundaries734/zero pass;
existing size advisories concern unchanged owners, with no responsibility added to
them. Initial new fixtures omitted required screen dimensions; corrected before
passing. These are mathematical mapping tests, not optical or live presentation
measurements; rig accuracy remains pending in [rig verification](rig-verification.md).

Oct19 `preview-image-flips`: E13rev30 applies horizontal mirrors to Left/Right
and a vertical mirror to Bottom in native preview composition only; Front,
projection and recording remain unchanged. Uses existing compositor uniforms and
layout kind/surface labels, no new schema/dependency/state owner (ARCH-002).
Standalone Windows GL test checks asymmetric quadrant pixels on all four preview
tiles and unchanged recording pixels/readback; passes.89 renderer unit tests pass;
Ruff/format2, Win32 mypy1 and boundaries734/zero pass. Existing cohesive-size
advisories unchanged. No live GUI restart or optical acceptance performed.

Oct19 `stimulus-composite-preview`: implements the owner's revised choice under
[E13](../docs/architecture/visual_stimulus.md#e13),
[V01](../docs/architecture/visual_stimulus.md#v01),
[V12](../docs/architecture/visual_stimulus.md#v12) and
[G01](../docs/architecture/gui.md#g01). Dashboard Visual stimulus uses a renderer-owned
native window after Setup: calibrated crops in Left–Front–Right / Bottom arrangement.
Recording uses uncropped full outputs in equal 2x2 cells, Bottom rotated 90 degrees
clockwise. Layout3 has no labels/header strips; matching post-rotation dimensions
fill adjoining cells exactly. Preview also omits labels and label-strip spacing. Separate targets share one compositor
implementation; projector pixels and video admission/accounting remain unchanged.
The recipe embeds both layouts, source/destination rectangles/rotation and protected
geometric/photometric values for later conversion. Policy pair18 and schema updated. Layout2 metadata remains readable.

Label-free follow-up:435 Visual Stimulus tests (2 deselected), one standalone GL
pixel test, scoped Ruff/format7, Win32 mypy160 and boundaries734/zero pass. The
rectangular fixture uses a portrait Bottom raster that matches the other landscape
rasters after rotation and asserts complete cell coverage. Native pixels allocate
no label textures. [Follow-up evidence](runtime-evidence-2026-10-19/stimulus-composite-preview/label-free-verification.json).
ARCH-002 keeps the geometry change in the existing pure helper; no new dependency.

Earlier integration baseline:571 scoped backend/client tests,82 preview GUI tests and2 explicit native pixel/cleanup
checks pass;12 policy checks pass after the final digest update. Ruff/format, Win32
mypy452 and boundaries734/zero pass. The GL check verifies preview-only cropping,
full recorded borders, Bottom rotation and captured row orientation. Metadata round-trip
checks need no source calibration files. Broader camera-test failures, sandbox retry
limits and exact commands/hashes are in the
[verification evidence](runtime-evidence-2026-10-19/stimulus-composite-preview/verification.json).
This is not a clean full-suite or full-workload rig pass.

ARCH-002: pure layout/metadata rules, native viewer ownership, controller authority
and GUI intents have focused owners with no runtime back-references or dependencies.
Existing large native/scene/worker/preparation modules retain only their established
GL/lifecycle orchestration; recording/native only uses the revised geometry provider.
No app restart, original-recording edit, physical projection or optical pass was made.
[Fresh-session preview/recording acceptance](rig-verification.md) remains pending;
the offline conversion script remains deferred.

Oct19 `texture-retain-static`: DUMMY-141422 recipe exactly matches the saved GUI
program and confirms separate static `stimulus_2/3/4/5` and drifting `Instance_1/2/3/4`
identities. At30s the compiled plan pauses drift and resumes the static instances
at their unchanged phase. Under [V07](../docs/architecture/visual_stimulus.md#v07),
Retain state applies per compatible instance; matching texture files alone do not
connect their state. Corrected only static instance IDs, their identical asset aliases
and scene references to reuse the drifting instances. Rates, timing, layer order,
texture recipes and all other settings remain unchanged. ARCH-002 favors this
protocol correction; no runtime changes or dependencies are needed.

Program parsing and exact semantic-diff assertions pass. Existing compiler and
runtime state/link handlers verify all199 internal boundaries across200 epochs:
all four states continue, every static interval holds its incoming phase, and every
drifting interval moves from that phase. GUI was closed; saved draft updated for
next launch with a byte-exact backup and an importable protocol. No native/optical
pass is claimed. [Evidence and corrected protocol](runtime-evidence-2026-10-19/texture-retain-static/)
and [physical acceptance](rig-verification.md).

Oct19 `bottom-direction-tearing`: owner confirms Bottom portrait top faces the head;
projector is below Right in the same physical orientation. Under
[G01 revision242](../docs/architecture/gui.md#g01)/[V15 revision21](../docs/architecture/visual_stimulus.md#v15),
GUI-generated Bottom mappings now rotate surface UVs before saved output flips.
Measured raw Y supplies physical depth and raw X the cross-span; current retained
values give129.25mm depth/91.333mm cross-span instead of the exchanged extents.
Preview places the corrected raster through the folded orientation. Trial/calibration
surface targets swap raster dimensions; live translations retain UV orientation and
pixel pitch. Raw reference bars/crops/offsets/masks/pulses and imported warps keep their
coordinate ownership. Linked source/follower motion is unchanged. No settings file
was edited; application restart and fresh Setup regenerate GUI profiles.

All432 local Visual Stimulus tests pass (1 deselected);99 affected GUI cases pass.
Scoped Ruff/format, Win32 mypy8 and boundaries724/zero pass. Focused direction tests check
four motion directions at the saved anisotropic pitch; native optical acceptance is
still pending. ARCH-002 reuses existing affine generation, resource builder and preview
helpers without dependencies or new state; scene_resources remains a cohesive GL
allocation owner. Detailed commands, source hashes and test receipts are in
[verification evidence](runtime-evidence-2026-10-19/bottom-direction-tearing/).

Original DUMMY-140646 evidence retains1932 groups with requested interval0 on
Front/Left/Bottom and1 on Right. Immediate swaps can tear under
[V20](../docs/architecture/visual_stimulus.md#v20); the existing all-output VSync option
is the comparison to run after cleanup/restart. Saved pulse-only mode is unchanged.
[Outstanding physical direction/pitch/tearing checks](rig-verification.md) remain open.

Oct19 `setup-scale15-recipe`: the newly pasted Setup failure identifies scale-15
`asset_6`; current saved GUI draft has eight scale-15 PNG references without a color
override, in addition to previously selected recipe assets. Applied the prior owner
recipe choice to these eight paths/profiles only; kept a byte-exact backup and
exported the corrected protocol for loading into the open GUI. Recipe, Asset and
all trial Program parsers pass; exact semantic diff confirms no other setting change.
This corrects the present draft and does not extend the earlier successful Setup
evidence to this larger protocol. Subsequently loaded corrected-protocol.json through
the native GUI Protocol Load dialog at owner request; Dashboard runtime log confirms
the path, and timeline shows 200 epochs/50 minutes. GUI remains Configuration;
Setup/Start were not clicked and controller history was not submitted. Under
[V13](../docs/architecture/visual_stimulus.md#v13), color validation still rejects
undeclared PNG encodings. Recipes can regenerate pixels differently from previews.
[Backup, corrected protocol and validation](runtime-evidence-2026-10-19/setup-scale15-recipe/verification.json).

Oct19 `preview-linked-fullscreen`: owner approved full-screen physical image-tile
textures in runtime and preview (V14 revision5); G01 revision240 binds preview links
through the runtime resolver with boundary/pivot validation. Whole-tile symmetric
extension covers calibrated surfaces under rotation/translation without stretching
periods or shifting phase; saved dimensions/configuration are not rewritten. GUI
brush Y anchoring now matches bottom-origin phase. Preview backward seeks replay
linked bindings; missing geometry rejects before playback.20 focused preview/coverage
cases and108 rendering/compilation cases pass. Saved actual protocol coverage passes
all four screens at six seeks with a white diagnostic tile; configuration byte equality
verified. Initial evidence script used strict Python validation on JSON lists; rerun
through model_validate_json succeeds. Ruff/format, Win32 mypy6 and boundaries724/zero
pass. ARCH-002 reuses the focused layer projection and canonical link helpers; no
new dependency or ownership. Existing scene orchestration remains cohesive.
Native inspection unavailable (Computer Use: foreground window did not report a
process id); GUI/runtime restart and physical output verification remain pending.
No live process restart, scientific config edits or staged promotion performed by
this change; concurrent work preserved. Evidence:
`runtime-evidence-2026-10-19/linked-fullscreen/verification.json`.


Oct19 shared GUI promotion implements per-output Frame/Pulse maps under
[V20](../docs/architecture/visual_stimulus.md#v20)/[V22](../docs/architecture/visual_stimulus.md#v22).
Every configured active output is bounds-checked and rendered with the group's
marker sequence; each submission keeps its own output/index/state/outcome evidence.
Explicit maps select every enabled pulse output for mixed VSync; blank/disabled
pulses request none. Legacy single-output profiles preserve their pacing behavior.
Portable rebinding and diagnostic updates retain all pulse screens; default files,
MCU ownership and physical input scope are unchanged. The complete local Visual
Stimulus suite passes427 tests (1 deselected); schema and contract checks pass.
[Evidence and scope](runtime-evidence-2026-10-19/shared-controls/context.json) remain
separate from [native/optical acceptance](rig-verification.md).

Oct19 Ponytail/Vulture maintenance removes two write-only cached display-limit
attributes. Preparation still uses request limits and its bounded budget; strict
asset-root resolution and protected resource retention remain unchanged under
[V15](../docs/architecture/visual_stimulus.md#v15)/[E14](../docs/architecture/system-contracts.md#e14).
Owning local tests pass; [caller review and validation scope](runtime.md#maintainability-review)
do not establish native/rig acceptance or performance.

Oct19 owner-selected GaussianNoise recipe replacement is complete:8 PNG asset
references now use the matching `.texture.json` and `cephvr1_texture_json_v1` profile.
Program/recipe parsing and exact candidate-diff assertions pass. Native Setup command
`be321de5-cf00-4a23-9276-fc1c4211ff0c` succeeds; session
`0813eb4e-fbbf-48e9-8642-ee975a7287fe` reaches Ready. Prior failed reservation required
administrative recovery preserving scientific files/unknown evidence. No trial was
started. Both saved configurations verify8 recipe references; corrected protocol was
also loaded into the open GUI, left on Ready. Other settings/staged scope are unchanged.
This supersedes the pending color-choice note below; recipe pixels need not match the
old PNG preview. [Raw evidence](runtime-evidence-2026-10-19/recipe-setup/verification.json).

Oct19 reported Setup failure is reproduced by an untagged PNG without color_override;
V13 rejects guessed color interpretation. Error now identifies asset/path and required
override. Saved GaussianNoise source has a sibling authoritative texture recipe naming
the PNG as preview; selecting the recipe is an alternative if intended, not a silent
pixel-equivalence substitution. Saved settings unchanged pending owner color intent.
Owning decoder regression passes. [Assessment](runtime.md).

Oct19 repair supplies missing GUI photodiode white/black RGB defaults, preserving
explicit values. Native texture-only 120-second preview trial completes with cleanup;
full saved-draft GUI Setup and optical timing remain unaccepted. Stimulus evidence
and recipe writers use extended paths; native >260-character filename tests pass,
but full long-root trial remains open. Subsequent240-second three-camera video-on
verification records14231 stimulus states/admissions, zero capture drops/same-slot
omissions/unresolved attempts at saved quality and15 slots. Tracking processing is
omitted; this does not certify optical timing or full-workload capacity. Saved defaults restore
exactly. See [assessment and evidence](runtime.md).

Oct17 owner selects `resources.capture_slots = 15` in the operator defaults for
a later rig test under V12/E14. Other settings and policy versions are unchanged.
This selection supersedes the restored three-slot baseline described in historical
evidence below; it does not change those results or certify zero-loss capacity.
Apply through fresh Setup; no rig run or running-session change was performed.

Current Oct17 concurrent acceptance run retains all 7200 real stimulus groups
exactly once over 120 s, alongside Behavior 3598/3598 and Tracking 7188/7188.
Rendering/projection and three encoders run concurrently; no capacity omissions,
duplicates or padding occur in this fixture. Its explicit temporary 16 capture
slots/half-resolution recording pass unchanged budgets. Saved three slots are
restored; their earlier startup limitation remains distinct and is not closed.
The saved lossy p4/CQ18 review recipe is unchanged under E13/V12/V28; GPU placement
remains SYS-002. Scientific JSONL is independent of optional review video.

The acquisition recording sync owner now independently services one flush per
exact file, with mandatory distinct final sync and strict timeout/closure proof.
Normal completed session, Cleanup/NewSession and Shutdown pass. All camera/settings
baselines restore exactly. Older acquisition Abort Finished, failed-Setup late
report and final Shutdown resource-registration triggers remain open. No optical,
external-trigger or Tracking-processing equivalence follows from software counts.
[Current assessment](runtime-evidence-2026-10-17/file-sync-fix/README.md),
[single outstanding checklist](rig-verification.md).

Historical Oct15 comprehensive recheck confirms fresh managed Idle initialization on
all four60Hz outputs with8-bit channels and swap interval1. This is software
submission evidence, not optical timing. The saved program's declared arena texture
requires715,827,840 GPU-budget bytes versus536,870,912 configured; Setup correctly
rejects it. Texture-only engineering variants remove unused declared arena
scene/instance/asset/boundary references; arena/combined variants require an explicit
smaller fixture rather than a silent budget increase. Failed-Setup long-path
cleanup/recovery is repaired in generated cancellation paths and lock-only startup
settlement with native before/after regressions; the original marker was immutably
backed up and explicitly removed only as this audit's unstarted artifact cleanup.
This is not general recovery acceptance. Fresh native60-second managed Gaussian
and mixed Gaussian/arena trials now complete on all four physical projector outputs
with both recording cameras; the arena uses an explicit512-pixel texture derivative,
retaining the original asset and budget. Save On→Off→On produces3→0→3 videos;
detailed frame/scientific logs remain enabled. Interrupted trials retain Interrupted
outcomes and complete output cleanup, with approximately40.12seconds metadata delay.
This establishes software submission/lifecycle evidence, not optical timing or
physical calibration accuracy. Post-session diagnostic reopening remains fenced.
Fresh native photodiode/blackout placement now pass invalid-bounds rejection then
valid live updates, move/remove and Close Idle/resourcesclosed with unchanged
asset/profile hashes. Safe worker prevalidation and typed owner/coordinator
propagation preserve proven Active state; generic/mismatched failures remain fatal.
Automated owner361 and managed-interpreter132 cases pass separately. The live
authenticated diagnostic run supplies native projector evidence; neither source
establishes GUI button-click or optical acceptance.
The final isolated60-second managed mixed-scene run completes with3600 decoded
review frames:3592 real/eight repeats, four capacity drops and two same-slot
omissions.3598 render groups have no unresolved submission attempts. The
[cross-owner benchmark](runtime.md) retains active-only CPU/GPU/RSS statistics,
per-stream saved codecs, three strict decode/count matches and exact restoration.
The later final Shutdown emits `cleanup returned an unregistered resource` despite
command success and exact process absence. This separate resource-report finding
remains open; it is not normal-shutdown acceptance. [Evidence](emergency-80538644376400-cf134742-126d-4fc6-aa22-c7ed8d33f493.json).
Independent capacity checks render four native-sized offscreen outputs through the
production layer shader and CPU-resize a review mosaic into a third NVENC stream;
they bypass calibrated projection/native presentation and the production recording
queue. Gaussian runs submit/decode3600 frames each at about60Hz; the separate20s
grating/native4096 case submits/decodes1199. All nine combined camera/stimulus
outputs fully decode. CQ23 GPU samples show5060Ti3–4%/339MiB and2080Ti encoder
45–52%/684MiB. CPU samples overlap another automated suite and do not establish
isolated workload cost/headroom; no CQ18 resource comparison is claimed.
Live-calibration explicit Update rejection is repaired without clearing the active
diagnostic block; owning cases cover three views and rejected/unknown outcomes.
[Fresh audit evidence](runtime-evidence-2026-10-15/comprehensive-audit/).

Oct16 `stimulus-sequential-recording` implements owner-approved
[E13 revision26](../docs/architecture/visual_stimulus.md#e13), with V12rev14,
V28rev7 and E14rev212/policy16. Retained usable composites now enter the MP4 once in
source-group order, including equal-time and repeated-content groups. Contiguous
zero-based indices are published only after a complete raw input frame is accepted.
Capacity drops and failed/cancelled readbacks consume no index; pending earlier
readbacks block later input ordering within the same fixed capture-slot bound.
There is no nominal-slot omission or leading/interior/trailing padding. Legacy
omission/duplicate counters stay zero, and closure requires full sequential count
reconciliation. A failed input or mapping publication cannot be retried as another
frame or promoted to successful closure.

Header6 and the MP4 writer schema3 distinguish the new correspondence; recipe schema2
is retained with `ffmpeg_rawvideo_sequential_v1`. The same `_stimulus_frames.jsonl`
provides `input_submitted.video_frame_index` → group → `state.evaluation_host_ns`
and exact per-output submission times, without a second timestamp file. Historical
Header3–5 remain readable under their original semantics. MP4 nominal playback rate
is unchanged but its duration is no longer scientific elapsed time. Video-off
scientific outputs, fragmented-MP4 closure, original deadlines and exact cutoff stay
in place. Crashed tail pixels/mappings remain unknown; no recovery/replay runtime is
added.

ARCH-002 removes the cadence/padding state and retained previous image, simplifying
the focused capture owner. No new
process, dependency or whole-runtime reference. The existing native recording and
resource session size advisories remain cohesive lifecycle/resource owner exceptions;
timing logic stays in the focused capture helper. The conservative memory ceiling
is unchanged. At that sequential-recording increment, geometry/input-argument helpers
matched HEAD by AST and compositor/readback source matched byte-for-byte; operator
TOML values matched except the required policy version. The subsequent capture
optimization below changes readback implementation while retaining tile sampling. The retained Oct15 profile still computes1280×1000 with factor2 and
unchanged tile rectangles when the encoder maximum needs no extra reduction; this
is not a live-rig configuration observation. Projector pacing and output rendering
were not edited.

Local validation:458 tests and79 contract subtests pass (one native/rig exclusion),
including authenticated transports, normal/interrupted on-disk mappings, same-time
real repeats, reverse readback completion, cancelled first capture, capacity gaps,
partial input/mapping failures, empty/off recording and original cleanup deadlines.
Ruff/format174, Win32 mypy158,11 generated schema checks and710 backend modules with
zero boundary violations pass. Initial Header version fixture/schema sequencing,
optional diagnostic typing and one formatting error were corrected. The first broad
run's11 localhost bind denials passed with socket permission. A preservation probe's
initial tuple serialization assumption was corrected; its actual equality/geometry
checks pass. [Raw results, exact commands, sample test outputs and source hashes](runtime-evidence-2026-10-16/stimulus-sequential-recording/validation.json)
retain the dirty-checkout/source scope. Native encoder input/count/fragment recovery
and full-load throughput remain in the [single rig checklist](rig-verification.md);
local fake-input tests do not prove NVENC output or device equivalence.
Local documentation checks resolve changed references/decision anchors but find two
pre-existing missing historical PNG targets (Oct15 bottom-grid/fix-verification/after/
bottom-offscreen.png and Oct14 tank-screen-plot/tank-screens.png). Their links already
exist in HEAD; restoration/location verification is queued separately.

Oct16 `stimulus-capture-optimization` now implements the owner-authorized PBO reuse
and GPU row orientation under [V12 revision15](../docs/architecture/visual_stimulus.md#v12).
The existing admission bound controls lazy pool growth; idle PBO storage is reused
without per-frame allocation/deletion. Each transfer has a fresh identity/fence.
Only signaled, successfully copied/unmapped buffers return to the pool; cancelled or
failed storage is discarded. Host bytearrays remain independent of later PBO writes.
Covered cleanup retries retain exact failed ownership and skip confirmed deletions, including
idle-buffer and partial-target allocation failures. Cleanup explicitly activates the
first output context before scene release, even when producer fences are already
retired. A local failure probe exposed this pre-existing context-selection gap; failed
activation retains scene/window ownership for retry. GL calls stay on their owner.

The compositor's shaders, quad, tile-render loop, dimensions and FFmpeg argv builder
are unchanged against the pre-increment snapshot; operator configuration is byte
identical. Rather than change bilinear tile sampling, a same-size nearest GPU blit
reverses the completed framebuffer into a second identical-format target. It preserves
black margins, restores scissor, rebinds the composite FBO and leaves no PBO bound. New capture strings
`rgba8_top_down` and `r10g10b10a2_le_top_down` make the actual row order explicit in
recipes/evidence. Historical bottom-up representations remain interpretable; live GL
capture accepts only top-down plans. The 8-bit recording path passes its owned buffer
through without a row copy; packed 10-bit retains X-bit normalization. This additional
GPU copy is a deliberate tradeoff to preserve sampled pixel codes; performance is
unmeasured. [OpenGL framebuffer blit semantics](https://wikis.khronos.org/opengl/GlBlitFramebuffer)
and [PBO synchronization](https://wikis.khronos.org/opengl/Pixel_Buffer_Object) support
the transfer design, not a hardware throughput claim.

ARCH-002 keeps ownership in the existing focused capture helper and moves recording
memory calculations to the existing resource-budget module. GPU preflight now counts
both targets (two RGBA8 or RGBA32F images) plus the bounded four-byte PBO pool; CPU
headroom/settings stay unchanged. No new process/dependency, independently editable
capacity or off-thread GL work. The existing large preparation/recording owner size
advisories remain reviewed cohesive exceptions; separable accounting was extracted.
E13 layout, resolution, image processing, nominal playback and projector pacing are
unchanged; sequential timestamp mapping and closure rules remain in place.

Final local owner/contract suite:430 tests and82 subtests pass, one native/rig exclusion,
including authenticated transports. The host GL model checks byte-equivalent transfer
against the prior CPU path for 8/10-bit, odd/even/single rows, bounded repeated reuse,
independent host buffers, reverse completion, unsignaled cancellation, stale handles,
blit/fence/map corruption, and failed-deletion/partial-allocation retries. It does not
execute native GL or prove actual GPU pixel equivalence. Ruff/format174, Win32 mypy158,
11 schemas and710 module boundary checks pass; three import-order issues were fixed
before final checks. The context probe initially lacked a GLFW teardown stub, which
was corrected without changing its ordering assertion; final normal/failing activation
cases pass. [Exact source snapshots/hashes and raw validation](runtime-evidence-2026-10-16/stimulus-capture-optimization/validation.json)
retain this dirty checkout's scope. The owner will perform native pixel, memory and
combined-load performance checks later under the [rig checklist](rig-verification.md).
GPU grayscale conversion, off-thread readback and layout/crop changes remain outside
this implementation; `stimulus-review-encoding-cost` retains the native follow-up.

Oct16 `stimulus-capture-cleanup-faults` repairs both locally reproduced cleanup
findings under [V12](../docs/architecture/visual_stimulus.md#v12) and
[E06](../docs/architecture/system-contracts.md#e06), without changing those decisions:

- Capture cancellation now attempts independent reservation/GL releases even when
  required evidence cannot be queued, then propagates the first error. Confirmed
  reservation cancellation is retained across GL retries, so failure counts are not
  repeated; a failed or incomplete GL deletion retains its exact pending handle.
  A stopped recorder still produces Failed output results after resource cleanup.
- Readback retirement/pooling now follows all fallible GL work, including the final
  buffer unbind. Restoration failures mark the handle failed and retain it for
  cancellation, even when the fence was already deleted. Failed storage is discarded,
  never recycled; later capture allocates fresh storage.

Ten new owning regressions fail before repair and pass after it. They cover full and
sealed evidence queues, multiple pending captures, false/raising GL cancellation
followed by retry, unchanged failure counters and deadlines, failed output results,
and ready/unsignaled unbind failures with deletion retries. Final owner/contract suite:
440 tests and82 subtests pass with one native/rig exclusion and localhost permission.
Ruff/format174 files, Win32 mypy158 sources and boundaries712 modules/zero violations
pass; two initial formatting findings were corrected. ARCH-002 keeps the existing
focused owners and owning test modules; unchanged large backend owners retain their
cohesion advisories. No new state machine, dependency or queue is added.

Static preservation checks confirm unchanged capture submission, GPU orientation,
shader bytes, composite geometry, encoding arguments and operator settings. Existing
host tests retain asymmetric 8/10-bit and odd/even/single-row image coverage. These
results do not establish native GL pixel equivalence, driver fault frequency or
throughput; those remain in the [rig checklist](rig-verification.md). The
[original review reproductions](runtime-evidence-2026-10-16/stimulus-capture-review/validation.json)
remain historical evidence of the defects; current red/green results, commands and
source fingerprints are in [fix validation](runtime-evidence-2026-10-16/stimulus-capture-cleanup-fixes/validation.json).

Oct16 E08/V12/ARCH-002 maintenance shares only unary peer mechanics, with Visual
Stimulus-owned stub selection retained. Recording metric comments clarify complete
input spans, zero-progress gaps and independent maxima without changing diagnostics
or scientific outputs. Authenticated peer26 and recording52 focused cases pass;
[current evidence](runtime.md#maintainability-review) retains final integration scope.
Native full-load acceptance remains open.

Oct16 `stimulus-replay-provenance` is repaired under
[V13 revision12](../docs/architecture/visual_stimulus.md#v13). The existing recipe
manifest now includes the installed renderer-source SHA-256, individual scene/arena/
warp/output shader hashes, Python/OS and relevant package/linked-decoder versions,
in-package color/importer identities, and actual per-output GL vendor/renderer/driver
observations. Missing required graphics facts reject Setup. Source/shader/environment
changes are distinguishable in saved canonical bytes; retain the matching software
release externally. The [earlier probe](runtime-evidence-2026-10-16/backend-output-alignment-review/validation.json)
reproduced the generic-label defect before this repair.

ARCH-002 extracts provenance from the resource preparer into a focused helper and
consolidates unchanged GLSL source ownership. Source collection runs once per Setup;
no per-frame hashing/readback or new dependency/process is introduced. The existing
CPU preparation worker now hands artifacts to the graphics owner and resumes after
context provenance enrichment, before recipe preparation, canonical hashing and
publication. Two bounded Futures preserve graphics-thread ownership, original Setup
deadlines and cleanup joins. Graphics failures retain the original lifecycle failure
path. Final serialized size remains bounded. Native/session/lifecycle size advisories
are reviewed as cohesive context/resource/lifecycle owners; new provenance mechanics
live in the helper and existing preparation job, without runtime back-references.

Owner-approved external preservation uses one backed-up, versioned asset library;
per-run manifests retain paths, sizes and hashes without copying an asset subset.
Preserve each image, mesh/material dependency and calibration version once, and keep
referenced versions. [Operator example](../docs/examples/session-logging.md#shared-asset-library).
Tracking remains deferred; reconstruction targets software-generated output.
Offline compatibility validation/replay/export and native GPU verification remain
separate from experiment-side retention; no pixel/light-onset equivalence is claimed.

Acquisition/stimulus and selected central-output tests pass997, with five platform
skips/three exclusions, including authenticated localhost transports. Five focused
final-publication cases additionally verify the on-disk recipe against the prepared
handle, graphics failure, cancellation, deadline and final-byte-limit rejection.
Source relocation/edit, shader mutation, driver changes/missing facts and shared
asset version reuse are covered. Exact GLSL preservation is checked against HEAD.
Ruff/format176, Win32 mypy159 and boundary checks pass. The initial run required
localhost access and correction of one new test fixture's snapshot budget; two initial
type annotations were corrected. [Commands, source fingerprints and raw results](runtime-evidence-2026-10-16/output-provenance-fixes/validation.json)
retain scope/limits. Native checks stay in the [single rig checklist](rig-verification.md#always-saved-scientific-evidence).

Oct15 live-pulse follow-up completes the owner-requested photodiode preview: the
existing GL-owner service loop repeatedly submits the current placement while Active.
Trial and diagnostic drawing share one pure V22 pattern helper, with separate
submission indices. Diagnostic Open starts at zero; successful all-output swaps
advance the index; live Frame/Pulse/target edits preserve it. Unknown and Close
stop repetition. Failed presentation marks Unknown and uses existing renderer
failure handling; no trial clock, marker log, recording or new resource owner is added.

Current pulse checks: affected backend/controller193 pass; the focused combined
GUI/rendering selection85 passes, including live edits to all Pulse fields, geometry
changes during a dark landmark, cycle wrap/reopen reset, failed swaps without index
advancement, Unknown cessation and Close/Idle. Ruff/format9, Win32 mypy50 and
boundaries699/zero violations pass. Two initial test-fixture errors (strict JSON
parsing and field-key names) were corrected before the final runs. RTX5060Ti
offscreen production drawing matches every pixel in66 frames across a live move/resize.
[Pulse evidence](runtime-evidence-2026-10-15/output-placement/pulse-native.json) and
[check context](runtime-evidence-2026-10-15/output-placement/pulse-validation.json)
retain method/source scope. No running GUI/projector or optical timing acceptance
was performed. Existing renderer-native and calibration-worker size advisories
remain cohesive owner exceptions: repetition stays with diagnostic lifecycle state;
the shared pattern is extracted rather than duplicating trial logic (ARCH-002).

Oct15 screenshot follow-up fixes `live-output-placement` launch incorrectly
requiring a pre-existing Frame/Pulse. Empty/incomplete initial definitions now
open black without inventing a rectangle or changing the draft. A complete
in-bounds live definition draws the pulse; later incomplete updates still retain
the confirmed image. The initial-only empty allowance stays with the existing
preparation validator; live-update validation remains strict. Existing GUI bundle,
initial draft and renderer-owner tests now cover empty-start-to-first-pulse and
unchanged cleanup. Follow-up GUI14/backend135, scoped Ruff/format7, Win32 mypy5,
schemas11 and boundaries698/zero violations pass. RTX5060Ti offscreen pixels are
exactly black initially, then show only the first valid white pulse. An initial
parameterized-test signature collection error was corrected before final execution.
[Follow-up native evidence](runtime-evidence-2026-10-15/output-placement/empty-start-native.json)
and [GUI transcript](runtime-evidence-2026-10-15/output-placement/empty-start-gui-tests-final.txt)
retain the scope; no running application/projector was operated.

`live-output-placement` is implemented under
[G01 revision208](../docs/architecture/gui.md#g01),
[V01 revision25](../docs/architecture/visual_stimulus.md#v01) and
[V22 revision7](../docs/architecture/visual_stimulus.md#v22). Synchronization adds
Launch photodiode placement (repeating bright/dark configured pulse on black) and Launch
blackout placement (black zones on neutral gray). Relevant pixel fields/target or
zone add/remove controls update the actual diagnostic via the existing debounced,
sequenced command path. Complete snapshots validate before replacing placement;
invalid/incomplete edits preserve the prior image. Unknown remains closable with
tuning disabled. Close restores Idle through existing exact resource ownership.
No trial clock or recording runs in these previews; V22 owns the diagnostic pulse sequence.

ARCH-002 keeps pixel drawing, strict placement records and GUI gating/conversion in
three focused helpers; existing lifecycle/GL/output owners remain authoritative.
One shared pattern allowlist covers all four views. Protobuf adds one placement JSON
field to the three existing update envelopes; regeneration preserves previous tags.
Only the display/profile-bearing derived schemas change. No dependency, process,
operator default or policy value is added. Cohesion advisories for the existing
Projectors composition, controller calibration dispatch and renderer owners remain
reviewed exceptions; no feature helper retains a whole runtime reference.

Final affected GUI52 and backend/controller362 pass (one Windows/rig case deselected),
including authenticated forwarding, stale/lease/sequence rejection, worker actual
presentation/Unknown, atomic invalid-rectangle rejection, resource closure and the
two new bundle/GUI paths. Contract42/79 subtests, schemas11, scoped Ruff/format342,
Win32 mypy336 and boundaries698/zero violations pass. Initial restricted communication
stalls, one legacy Close fixture, mixed-pacing fixture setup and screen-resource
ownership assertions were resolved or replaced by permitted final checks. Broad
repository-local temp runs reached GUI90/backend353 passes but failed the existing
external-demo-assets guard; final normal-temp executions pass without weakening it.
The offscreen Qt inspection required explicit test-only Segoe UI registration.

RTX5060Ti offscreen native pixels match complete expected images before/after pulse
movement and zone removal. This does not establish projector submission, physical
placement or optical timing acceptance. Restart the application to load all updated
clients/backends and use the new Synchronization actions. Existing local drafts hold
the edits for normal Apply; previews do not publish an experiment configuration.
[Native pixels, controls and final check transcripts](runtime-evidence-2026-10-15/output-placement/)
retain evidence; physical/fault checks stay in the
[single rig checklist](rig-verification.md).

Oct15 `bottom-calibration-grid-distortion` software fix completed under
[G01](../docs/architecture/gui.md#g01)/[V15](../docs/architecture/visual_stimulus.md#v15),
with no architecture/policy change. The existing diagnostic GLB builder now passes
native per-face raster sizes to its guide helper. Grey strokes cover at least two
source pixels on each axis; fixed10mm/world-phase line centers and measured
geometry/corrections remain unchanged. No new dependency, state owner or render
path was added under ARCH-002. Exports without a known raster retain their physical
stroke defaults. Source review found no separable responsibility requiring extraction.

An isolated RTX5060Ti render of production arena/warp shaders reproduces the latest
saved bundle's122px middle gap against ordinary41px gaps. The fixed generator
restores17 visible columns with40–41px gaps. Earlier inputs produced a163px gap;
their dated evidence remains separate. This corrects the initial CPU-only assessment:
uniform mesh centers do not establish visible raster coverage. All four generated
meshes retain exact10mm spacing on both axes. Existing owning GUI coverage is
extended for portrait/landscape/low-resolution strokes, mirrored world phase,
fractional sample coverage and bundle raster propagation. Focused GUI17 and
rendering74 pass; scoped Ruff/format4, Win32 mypy3 and boundaries695/zero violations
pass, with existing unrelated cohesion advisories. Broad restricted GUI selections
were interrupted after stalling; initial default/temp-root failures are not test passes.
The native probe initially supplied a full GUI configuration to the numeric-only
parser; corrected fixture construction uses the retained dimensions directly.

Physical cell-size equivalence remains open. Saved Bottom bars are44/24mm for
180/320px in portrait720×1280 mode:0.244444/0.075mm-per-pixel, yielding nominal
10mm cells of40.91×133.33px. Other screens use40/22mm for320/180px:
0.125/0.122222mm-per-pixel and80×81.82px cells. No extra Bottom grid spacing
factor exists. The owner is unsure whether Bottom measurements belong to the
current orientation; retain them pending remeasurement of the current orange X
and green Y bars. This establishes the different software scale assumptions,
not an optical diagnosis. Saved measurements and the running application were
not modified. Restart the GUI and relaunch projection calibration to regenerate
the fixed grid. Border cropping still creates partial edge cells by design.
[Native before/after, source hashes and input snapshots](runtime-evidence-2026-10-15/bottom-grid/fix-verification/summary.json),
[scale audit](runtime-evidence-2026-10-15/bottom-grid/fix-verification/scale-audit.json)
and [fixed render](runtime-evidence-2026-10-15/bottom-grid/fix-verification/after/bottom-offscreen.png)
retain the evidence. No projector presentation or optical acceptance is claimed.

Current Oct15 open-loop engineering gates pass linked Gaussian translation/spin,
visible rotating circular floor and combined60s reuse, with all four videos externally
counted/full-decoded and normal cleanup. Actual common-group state and four submitted
outputs support software motion linking; projection areas remain uncalibrated. The
original arena has only a textured circular floor, despite its directory name. A unique
unlit derivative preserves geometry/BIN/source; its explicit height0 test placement
corrects a failed black-frame trial at height53 without altering observer calibration.
Full resource preparation exposed invalid colon-containing generated arena IDs; bounded
deterministic valid IDs now agree across dependency manifests and GPU lookup, preserving
strict schemas. Embedded/external owning regressions and329 Visual Stimulus cases pass.

Controlled startup tuning changes capture slots3→15:25 capacity drops in the first0.739s
become zero in repeated60s and120s runs. Keep same-slot omissions/CFR duplicates distinct.
The source2048 texture requires a temporary GPU asset limit512MiB→1GiB; combined prepared
GPU usage is784,080,416bytes and CPU346,219,117bytes. Camera/codec settings and review
scale2 remain fixed. Both TOML overrides have exact originals retained for restoration.
The first900s interruption and reviewed shared-reader/fatal-error repairs are assessed
in [Acquisition](acquisition.md);120s passed afterward. The owner stopped the900s retry
at883.852s; outcome is Interrupted with recording cleanup unconfirmed. The owner has
resumed tests; those partial recordings remain retained. Original Visual Stimulus
TOML and last configuration were restored exactly
after all owned processes exited. Resumed trials use unique copies of the newer GUI
calibration (Bottom685x940; derived linked-spin pivot23,0). Current normal120s recording
passes four full decodes/counts, with7201 stimulus states/7168 real selected frames,
zero capacity drops,33 same-slot omissions and32 CFR duplicates. Fresh combined900-final-r1
now completes exactly 900 seconds with confirmed cleanup and four full video decodes.
Its 53,988 contiguous render groups retain four returned output submissions each;
there are no unresolved submissions/captures. Stimulus records 54,000 CFR frames:
53,389 real frames, 598 same-slot omissions, one capacity drop and 611 duplicates
(1.131%). The capacity drop is group 17 at T+0.2947451 seconds, with none thereafter.
Peak capture occupancy reaches 15/15 and maximum slot hold is 261.51 ms; burst headroom
and zero-loss capture are not established.
Oct16 read-only reanalysis bounds the historical ready-to-dequeue maximum at241.9643ms,
readback readiness at61.2051ms, normalization at10.0268ms and individual pipe calls
at9.3096ms. These maxima need not belong to one capture; pipe-call duration excludes
waiting between zero-progress calls. The old aggregates cannot attribute group17's
startup drop to GL, encoder or OS scheduling, and cannot recover percentiles.
Current local diagnostics retain one group/slot/timestamp example per fixed stage and
a full-frame input span with attempt/zero-progress counts, plus one unfinished span.
No rendering, pixels, capture selection, output count, deadline or GL ownership changes.
Owning tests pin old counts/timings, exact examples and snapshot isolation; new native
correlation remains in the [single rig plan](rig-verification.md#encoding-test-plan).
Final integrated backend/authenticated1860 passes/five skips/five exclusions, Ruff,
format679, Win32 mypy583 and boundaries702/zero violations pass. Validation is local;
no native throughput, total-memory or zero-loss acceptance is inferred.

The archived profile/scale resolves to1280x1000 RGBA (5,120,000bytes/frame), independently
matching276,480,000,000 submitted bytes/54,000 input frames. Accounted capture memory:

| Slots | CPU reservation | GPU reservation |
| --- | --- | --- |
| Restored default3 | 31.74MiB | 34.18MiB |
| Tested override15 | 90.33MiB | 92.77MiB |

Both CPU reservations fit256MiB `recording_bytes_total`; GPU reservations join the shared
asset budget. The evidence queue has a separate16MiB bound. These are current allocation
formulas, not measured full-process/driver/FFmpeg/OS memory. Keep restored default3;
15 fits these bounds but still filled and dropped in the900-second run, so no new default,
queue increase or headroom claim is justified here. Existing15-slot test settings remain
archived for controlled native comparison. [Reproducible analysis and limits](runtime-evidence-2026-10-16/remaining-dev-work/stimulus_capture_analysis.json).
 Active GPU means by translation/spin/arena
are 10.99/11.28/10.21% rendering and 42.36/42.76/42.56% encoding; memory stays constant.
Six nonaliasing snapshots at 15/17, 315/322 and 615/622 seconds show changing content
in all four tiles. Astra accepts software-linked motion/endurance, with physical
alignment still uncalibrated and stimulus review still lossy under E13.
[Final recording accounting](runtime-evidence-2026-10-15/open-loop-soak/resume-1/combined900-final-r1/completion-summary.json),
[active resource measurements](runtime-evidence-2026-10-15/open-loop-soak/resume-1/combined900-final-r1/monitor-analysis.json).
The separate 60-second camera-lossless workload also completes/counts/decodes, with
zero stimulus capacity drops, three same-slot omissions and two CFR repeats. Stimulus
review encoding is unchanged. Fresh resume-1 GUI/configuration/TOML baselines are now
restored, with the tested overrides retained only in the separate reusable packages.
All runtime processes are absent and camera handles are closed; Acquisition records
the camera PFS selector-cursor restoration limitation. Cleanup removes only 51 passed
regenerable synthetic MP4s (13.504 GiB), retaining their commands/counts/decode results,
all real/failed recordings and unique evidence.
[Cleanup manifest](runtime-evidence-2026-10-15/projector-free-rig/synthetic-media-cleanup.json).
Oct16 `arena-effective-pose-evidence` repairs that structured evidence gap under
[V13/V16](../docs/architecture/visual_stimulus.md#v16). The scene renderer retains one
pose for the active arena using the same frozen state as its existing model matrix:
explicit world frame, millimetre position and a unit xyzw quaternion matching the
existing yaw/pitch/roll composition. The authored asset transform remains separately
represented by the prepared asset and exact model-matrix words. Drawing/constraint
behavior and physical observer calibration are unchanged; no new movement semantics
or scientific acceptance is inferred. Existing arena helpers share finite pose-value
validation under ARCH-002, with no new dependency/state owner. Rendering/evidence/
feedback97 and Visual Stimulus347 pass (one native/rig deselected); scoped Ruff/format3,
Win32 mypy2 and boundaries698/zero violations pass. An initial test fixture omitted
the required arena kind and was corrected. Native pose/frame/matrix inspection remains
in the [rig checklist](rig-verification.md).
[Local source/check evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
[Raw attempts, fixes and native evidence](runtime-evidence-2026-10-15/open-loop-soak/)

Oct15 encoder matrix completes31/31 cases:10s all-source warm-up plus three
repetitions of five source combinations at CQ16/CQ23, each requesting60s of frames;
all external counts and full decodes pass. Enabled camera dimensions/rates are
Behavior1760x3000RGB24/30Hz and Tracking 1588x1344gray/60Hz; synthetic Stimulus is
1280x1000RGBA/60Hz. Actual FFmpeg GPU UUID is RTX2080Ti; matched FFmpeg/ffprobe9.0.2
is selected process-locally, leaving default PATH4.3.2 unchanged. A separately opened
application renderer appears on RTX5060Ti during r1-cameras-cq23 and thereafter;
later cases are not an otherwise idle-machine benchmark. Raw commands, versions,
formats, sizes and per-case timing are retained. Synthetic generation/conversion/NVENC
does not prove live capture, cross-GPU readback/stdin, sustained synchronized full-path
headroom, real-frame losses or animal-image quality. Eye remains disabled. CQ decisions
and saved argument lists are unchanged. Direct zero-byte raw-input probes for both
camera formats exit0 and finalize/synchronize small MP4s; these are not playable-video
or runtime NO_FRAMES ownership/accounting acceptance. Initial read-only-handle fsync
probe failure is retained; the corrected probe uses fresh paths.
[Results and actual workload](runtime-evidence-2026-10-15/projector-free-rig/context.json).

Oct15 projector-free verification finds stale derived prepared-trial JSON Schema
still embedding superseded seam_check and reference-bar guide Width/Height fields. Regenerating from
the retained canonical models under G01/V15 changes only that schema; all11 generated
schemas match afterward and42 contract cases pass. No policy or calibration behavior
changes. Native/source packages build; source archive contains both calibration GLBs.
[Dated commands, raw results and limits](runtime-evidence-2026-10-15/projector-free-rig/context.json). Projector rendering, readback, optical alignment and real-frame recording/drop
acceptance remain deferred while outputs are powered off; synthetic encoding is separate.

Oct15 Git-sync integration retains the owner-approved local pixel-size/offset calibration
under [G01](../docs/architecture/gui.md#g01)/[V15](../docs/architecture/visual_stimulus.md#v15),
while preserving independent required scientific evidence, optional reduced review video,
arena-file regions and recording metrics under E13/V12/V16/V28. E14 policy version15
binds the combined declarations; Protobuf projection remains field11 and review scaling
uses field12. Existing periodic sync is preserved when the video worker is absent.
Final owning suite327 passed/one deselected; full backend1,737 and offscreen GUI509 pass.
Static/document checks and initial failed attempts are assessed in the
[Runtime report](runtime.md) with [dated source provenance](runtime-evidence-2026-10-15/git-sync/context.json).
These local checks do not close [rig verification](rig-verification.md).


Oct14 `projection-calibration-window-controls` completes the owner's refinement under
[G01 revision204](../docs/architecture/gui.md#g01) and
[V15 revision20](../docs/architecture/visual_stimulus.md#v15). Screen names are smaller,
centered and use contiguous glyph cells. The table has no arrow buttons and adds
separate whole-pixel Offset X/Y columns (positive right/up, blank zero). Interactive
sizes cap at native resolution; offsets cap at remaining image margins and reclamp
when a size grows. Numeric8/full11/review6 persist pixel offsets while older removed
offsets remain discarded. Preview and published affine assets share translated bounds.
Diagnostic assets/views cover the full measured native raster, so expansion reveals
additional fixed-pitch, world-phase grid lines. Diagnostic plane isolation prevents
expanded grids occluding other faces; trial drawing disables that filter.

ARCH-002 reuses the pure extent owner, existing affine mapping, Qt entries, GLB
builder and arena shader/drawer; no dependency, wire field, process, deadline,
policy setting or whole-runtime reference is added. Projectors remains a cohesive
composition owner and delegates bounds/files/geometry. Owning GUI26 and persistence11
checks pass; renderer73 pass. Ruff/format157, Win32 mypy155 and boundaries686/zero
violations pass, with existing size advisories. The730px offscreen table was inspected;
no native restart/projector/optical/full-workload acceptance is claimed. Reopen the
application to load the code and launch projection calibration to regenerate its grid.
[Commands, XML, preview and provenance](runtime-evidence-2026-10-14/window-controls/context.json).
Broader GUI/calibration attempts stalled and were interrupted; no full-suite pass.
Stale version/extent assertions, numeric8 file routing and static findings were repaired.
A failed Windows encoding write emptied the GUI architecture page; its complete
pre-existing content was restored byte-exact from the Codex pre-edit snapshot before
these focused amendments. Remaining physical checks stay in
[rig verification](rig-verification.md).

Oct14 combined sixty-second three-camera trial completes with nine closed outputs, restored settings and four counted/full-decoded videos. Stimulus slots21 saturate with3078 capacity drops/3098 CFR duplicates; finite buffer growth is rejected and original visual TOML restored byte-exact. V12 throughput remains open. Source review identifies per-capture PBO allocation/deletion, fresh CPU readback followed by another ownership copy, row normalization, copied overlapped pipe backing and5ms recorder polling as optimization candidates. Stage timings are needed before attributing the bottleneck; preserve image quality/accounting/GPU ownership. [Performance review](runtime-evidence-2026-10-14/rig-timing-audit/recording-performance-review.json). Retain3 slots with256MiB recording CPU/512MiB asset GPU budgets for the tested2560x2000 composite/assets: CPU accounting133120000bytes requires159744000with20%; GPU same-assets estimate335054176bytes requires402065012with20%. These are allocation accounting estimates, not new native measurements or whole-process/GPU memory guarantees. Twenty-one slots saturated, so no finite slot recommendation establishes steady throughput. Nested video-sync cadence is corrected: measured successful intervals stay below1.2s (maximum1040.5247ms), errors0. Native Save On to Save Off completes/cleans/restores with two decoded camera videos and no stimulus output. E05/E06/E08 cleanup repairs preserve strict output absence, exact resource receipts and confirmed delivery. Fault6 records accepted cleanup from both backends, but warning authority loss prevents overall cancellation; its scope repair is locally verified under E03 revision35. With projectors off, fault9 exposes lost prior calibration release receipts; catalogue retirement/reopen handling is repaired and full Visual suite311 passes, native retest deferred. No renderer-exit cause is inferred from generic CHILD_EXITED. [Current evidence](runtime-evidence-2026-10-14/rig-timing-audit/lifecycle-findings.json).

ARCH-002 adds only a focused pure extent owner; reuse Qt and existing projection,
texture-coordinate and resource builders. No dependencies, wire/policy fields,
process/state machine, deadlines or ownership changes. Existing Projectors and
scene-resource size advisories are cohesive composition/allocation owners; physical
extent arithmetic stays in the helper. Current checks: owning GUI48 pass/445
excluded; rendering/config82 pass including real builder allocation with fake GL
contexts. Cross-projector proof uses different native resolutions and anisotropic
pitches: equal usable mm dimensions give equal physical corners/off-axis matrices,
and 20×10 mm texture spans retain physical size. Migration, arrow-click, integer
rejection, preview/export, fixed-pitch live sequence and imported asset preservation
checks pass. Ruff, format160, Win32 mypy158 and boundaries690/zero violations pass.
Projection numeric settings are unchanged: resulting extents are bounded by native
raster and measured pitch; current tests remain within near1/far250 and existing
tolerances. Hardware geometry changes still require V15's owner-approved limits review.

Initial unconfigured Qt runs fail without diagnostics; explicit offscreen mode fixes
local execution. A broader calibration selection stalls in restricted integration,
is interrupted, and is replaced by the focused owner checks. During implementation,
UTF-8 handling, an overly broad numeric restore conversion, obsolete version/offset
fixtures, strict JSON tuple validation and fake-resource cleanup field were corrected.
No native renderer restart, projector alignment, optical/scientific or full-workload
acceptance is claimed. Reopen the application to load changes; retain outstanding
[rig verification](rig-verification.md).
[Commands/scope](runtime-evidence-2026-10-14/integer-views/context.json) and XML evidence.
Previous pixel-crop evidence remains [here](runtime-evidence-2026-10-14/valid-area/context.json).

Oct14 `reference-calibration-output-frame` completed under
[G01 revision200](../docs/architecture/gui.md#g01) and
[V01 revision21](../docs/architecture/visual_stimulus.md#v01). Reference calibration
now shows a white native output-boundary frame and unchanged colored raw-pixel bars.
The initial frame needs only output resolution; it supports aiming/focus/rough
positioning and cannot claim a measured physical screen boundary. Align the raw
projection, measure bars, close it, then launch the measured physical frame/grid
for existing Scale/Offset refinement. No screen dimensions/measurements/corrections
or clipping values are changed by this step.

ARCH-002 reuses one focused four-rectangle helper in the native drawer and GLB
exporter; no dependencies, protocol fields, resources, policy or state additions.
Frame draws before colored bars, so intersections preserve exact configured bar
pixel spans; scissor restoration, native copy, protected lengths/digests, authority
and cleanup remain. Source GLB now contains four frame edges plus two bars per output.
Final rendering/resource71 and owning GUI15 pass/467 deselections. Ruff/format6,
Win32 mypy3 and boundaries689/zero violations pass with unchanged size advisories.
Initial70-pass/one-failure result exposes obsolete8-vertex asset assertion; update
it to24vertices and the bar slices, preserving length/cleanup assertions. Final71 pass.
No runtime/device/native/optical acceptance. A normal application restart loads the
renderer change, and reference launch regenerates its source. Physical alignment
remains in the [rig checklist](rig-verification.md).
[Commands, limits and test XML](runtime-evidence-2026-10-14/reference-frame/context.json).

Oct14 `updated-tank-screen-plot`: [3D/top/side plot](runtime-evidence-2026-10-14/tank-screen-plot/tank-screens.png)
uses current production corner construction, owner-confirmed126×94mm Bottom image
axes,5mm front/lower gaps and retained120×166×110mm tank / subject(60,93,53).
Retained51mm side distances give4mm lateral clearance;52mm would give5mm for the
centered94mm Bottom cross-span. Keep measured distances pending reconciliation;
the plot labels this source-input discrepancy without claiming optical verification.
[Inputs/corners](runtime-evidence-2026-10-14/tank-screen-plot/geometry.json) and
[generator](runtime-evidence-2026-10-14/tank-screen-plot/plot.py) retain provenance.
PNG inspected; front/lower gaps and Bottom axes asserted. No runtime/settings/device change.

Oct14 `clean-calibration-grid-bottom-fit` software correction completed under
[G01 revision199](../docs/architecture/gui.md#g01),
[V15 revision17](../docs/architecture/visual_stimulus.md#v15) and E14 revision210.
The grid remains solid neutral lines, a white border and one screen name. Owner
confirms 5 mm frame gaps at both front and lower junctions: Side/Bottom front edges
start behind Front; Front/side lower edges start above Bottom. Preserve perpendicular
subject distances and physical heights. Bottom image X/width126mm follows +rig Y;
Y/height94mm follows -rig X, preserving the 94×126mm tank footprint with corrected
image axes. The earlier on-disk Bottom width94/height126 caused image X to target
94mm instead of126mm. This resolves the source axis mismatch; actual optical
coverage is still pending, not inferred from arithmetic.

Numeric5/full8/review3 swap legacy Bottom width/height only, preserving raw native
bar measurements, extra scales/offsets/inversions and imported runtime profiles.
GUI fixed policy/config version6 declares the 5mm gap. All consumers reuse the shared
corner helper; ARCH-002 needs no dependency/state/process/module extraction. Final
owning GUI38 passes/444 deselections, plus2 focused passes after exact126/94 neutral
mapping and legacy-review migration assertions. Ruff/format7, Win32 mypy6 and
boundaries689/zero violations pass, with existing unrelated size advisories; TOML
syntax/version/binding and documentation references/whitespace pass. Initial legacy
affine/mirror-fixture failures and one static version comparison are corrected;
source geometry changes require the mirror tests' new clearances, retaining all
complete/partial/impossible-path scenarios.

Retain V15 clipping/tolerances after reviewing the orthonormal axes and 5mm gap;
no numeric change is needed for the supplied physical planes. Extra saved X/Y
multipliers remain operator adjustments. Reopen the GUI to migrate drafts and launch
projection calibration to regenerate the clean grid. No stored measurement edit,
runtime restart, device/output command or native/optical/full-workload acceptance.
Existing [rig checks](rig-verification.md) retain physical coverage verification.
[Correction evidence and commands](runtime-evidence-2026-10-14/frame-gaps/context.json).
The [earlier artifact assessment](runtime-evidence-2026-10-14/clean-grid/context.json)
records the old axis assumption and remains historical evidence, superseded by the
owner's126mm image-width/94mm image-height clarification.

Oct14 `calibration-close-button-and-distance-format` completed under
[G01 revision197](../docs/architecture/gui.md#g01). GUI derived distances display one
decimal millimetre; raw reference measurements/mm-per-pixel mapping retain precision.
The confirmed active step's own launch button becomes Close, with the other step
disabled and both disabled while pending. Existing diagnostic Close transport and
output-confirmation semantics remain unchanged. Owning GUI selection13 passes,
scoped static/boundary checks pass; no native output/restart or optical acceptance.
See the [runtime assessment](runtime.md) and
[local evidence](runtime-evidence-2026-10-14/calibration-controls/context.json).

Oct14 `bottom-attached-screen-elevation` completed under
[G01 revision196](../docs/architecture/gui.md#g01) and
[V15 revision16](../docs/architecture/visual_stimulus.md#v15). Replace tank-height
centering of Front/Left/Right with lower edges at subject Z minus Bottom-screen
distance. Preserve physical screen heights; shared corner construction now passes
Bottom distance through diagram, trial preview, saved calibration/GLB export and
prepared geometry. Missing/nonpositive/nonfinite Bottom distance invalidates all
planes rather than retaining detached wall geometry. Saved drafts gain no fields.

ARCH-002 reuses the focused geometry helper and existing owning behavior tests,
without new state, dependencies, runtime references or extraction needs. Final local
GUI selection25 passes/455 deselections; scoped Ruff/format5, Win32 mypy4 and
boundaries689/zero violations pass. Existing oversized-module advisories are unchanged;
all four edited source modules remain cohesive focused responsibilities. Initial
8-pass/2-failure run exposed test-fixture migration needs (full versus numeric
snapshot, missing Bottom distance); repair fixtures, intermediate20 and final25 pass.
Initial format finding corrected. Retain current V15 clipping/tolerances: no new
measured dimensions/scene depth justify a numeric adjustment, and planar attachment
does not change orthogonality. No runtime restart/device/native/optical acceptance;
reopen the GUI to load this fix. Existing [rig checks](rig-verification.md) remain.
[Local command/results and test XML](runtime-evidence-2026-10-14/screen-elevation/context.json).

Historical measured-base fit evidence used extra Scale multipliers; that rule is
superseded by G01's pixel valid-area crop. The original
[measured-base evidence](runtime-evidence-2026-10-14/measured-base-scale/context.json)
retains its dated measurements, tests and limits.

Oct14 `projector-cursor-stability` completed under
[G01 revision194](../docs/architecture/gui.md#g01), retaining V01/V04 native output ownership.
GLFW defaults to centering the cursor on each fullscreen creation; the shared native
window configuration now sets CENTER_CURSOR false after every hint reset. ARCH-002
uses the existing focused owner without cursor restoration, extra state or dependencies.
Owning rendering/calibration tests71 pass; scoped Ruff/format2, Win32 mypy1 and
boundaries689/zero violations pass. Native main-display checks verify launch at
(497,768), Close at (497,784), and recreated reference outputs at (497,425), each
exactly matching the clicked main-display location. Authenticated states confirm
Active/presented, Idle/resources_closed, then Active/presented. Leave reference bars
open for measurement; this verifies cursor placement, not optical/full-workload acceptance.
The accidental Escape interrupted the first native attempt; resume on owner request,
discover the closed Dashboard and reopen it in the running generation. The sandbox
status probe stalls; permitted loopback read succeeds. One initial cursor evidence
filename was overwritten by status evidence; record it separately on the next read.
[Commands, status and native evidence](runtime-evidence-2026-10-14/projector-cursor/context.json).

Oct14 `live-reference-measurements-and-tab` completed under
[G01 revision193](../docs/architecture/gui.md#g01). Measured X/Y mm fields now stay
editable with GUI editing authority during confirmed Active reference bars; retain
native pixel/mode provenance, rig/assignment/correction locks and protected inputs.
Edits update retained drafts/derived estimates without renderer updates or rewriting
active assets. Pending/unknown/closing and observer states remain locked; a pending
non-Active state now also locks the card. Frame/grid retains its original live
Scale/Offset controls. Shared DataTable's grid navigation trapped Tab on embedded
editors; disable that behavior to use Qt's normal widget traversal. Tab/Shift+Tab
moves between nested editors/combos/checkboxes and skips disabled fields; inventory
arrow selection remains native. Console, log-details and example text views release
Tab for navigation. Incomplete imported display profiles no longer raise a pre-existing
KeyError when adding file-owned projection limits; retain partial drafts while Setup
still validates complete geometry.

ARCH-002 reuses existing measurement drafts/refresh, shared Qt controls and owning
behavior tests; no global event filter, dependency, process or extra state. Existing
large Projectors code remains focused widget/view-lock composition; no separable new
responsibility is added. Focused7 tests pass; final calibration/keyboard/table/measurement
selection34 pass/441 deselections, after initial33-pass/incomplete-import failure.
Scoped Ruff/format5, Win32 mypy4, boundaries689/zero violations, documentation references
and whitespace pass. Final fixture run emits Windows COM0x8001010d diagnostic but
continues/exit0 with34 passes; cause unverified. Correct initial Ruff line/zip findings.

Reopen the already-closed GUI in the existing runtime using --reopen-gui. Native
Active reference presentation and screenshots verify FrontX→FrontY→LeftX and reverse
Tab movement with measurement fields focused; scientific values are unchanged.
This native Active-case check precedes the final pending-only guard refinement;
pending/observer behavior is verified by the local regressions. GUI remains open
with reference bars Active. A transient DWM ghost is observed without inferring backend
failure; read-only controller status confirms current presentation. Existing optical/
full-workload limits remain in the [rig checklist](rig-verification.md).
[Evidence and native focus captures](runtime-evidence-2026-10-14/live-reference-tab/context.json).

Oct14 `reference-bars-visible-output` repaired and verified under
[V01](../docs/architecture/visual_stimulus.md#v01)/[V15](../docs/architecture/visual_stimulus.md#v15).
Reference bars were drawn into the device framebuffer without copying to the native
screen; the branch continued before the copy used by frame/grid. Actual Front output
was black. Copy that framebuffer to the current screen before returning; native-pixel
lengths, correction independence, existing swaps, ownership and cleanup remain.
ARCH-002 reuses the established framebuffer copy, with no dependency, process, state,
module proliferation or architecture-policy change. Extend the owning behavior test
to require each output copy after bar drawing; both bars cases fail before the fix,
and both grid cases pass. After repair, rendering16 and calibration rendering/lifecycle/
authenticated transport22 cases pass (37 deselections); scoped Ruff/format2, Win32
mypy1, boundaries689/zero violations and whitespace pass. Default sandbox temp fixtures
initially cause six errors/ten passes; workspace basetemp and permitted integration pass.

Native GUI testing through Computer Use confirms four visible orange/green bar outputs,
normal Close with authenticated Idle/resource-closure evidence, and successful reopen
with Active/presented evidence. Graceful ShutdownApplication succeeds after the prior
GUI has closed and resources are confirmed closed; restart through the managed launcher
loads the repair and restores the draft/control. Final controller80dfe14b-7d23-45b0-a46f-eaf77c024b62
is left running with reference calibration open for measurements. An input-observation
race/stale-window binding and one geometry-unavailable click require refresh/reselection;
no unknown UI input is retried blindly. Initial exact-color screenshot analysis rejects
lossy JPEG values; corrected approximate-color analysis confirms both colors, without
claiming exact framebuffer pixels or optical accuracy. Optical/full-workload checks
remain in the [rig checklist](rig-verification.md). The repository asset directory
still contains only the two requested GLBs. [Evidence, native captures and commands](runtime-evidence-2026-10-14/reference-bars/context.json).

Oct14 `projection-config-only` completed locally under
[G01](../docs/architecture/gui.md#g01), [V15](../docs/architecture/visual_stimulus.md#v15)
and [E14](../docs/architecture/system-contracts.md#e14). Remove the four rig projection
editors and frontend draft persistence. `[projection]` in the owning Visual Stimulus
TOML supplies near 1 mm, far 250 mm, positional 0.000166 mm and orthogonality 0.000001.
Both calibration and experiment submission read that file; controller validation/startup
and worker Setup overlay its resolved snapshot before geometry validation. Missing or
invalid file values reject preparation. Imported numeric calibration/review drafts stay
loadable but cannot override these values; physical corners and other fields remain.
Regenerate the authoritative Protobuf bindings for the focused ProjectionLimits payload;
no policy value or policy_version changes. ARCH-002 removes the duplicate diagnostic
heuristic and reuses existing file/profile assembly, adding one focused pure validator,
no dependency/process/state. Existing large Projectors and worker lifecycle modules retain
composition and lifecycle ownership; no new independent responsibility is placed there.

GUI geometry/import/restoration/diagnostic 18 cases, configuration 9 cases, contracts 42
cases plus 79 subtests, worker lifecycle 34 cases and a controller startup overlay case pass.
Scoped Ruff/format and Win32 mypy 10 sources pass; boundaries 688 modules/zero violations
retain existing cohesion advisories; whitespace passes. Default sandbox temp fixtures fail;
repository-local basetemp works. Authenticated lifecycle tests stall under sandbox and are
interrupted; permitted loopback run passes. Initial fixtures lacked required projection
values and are updated, retaining rejection checks. Three transient admission failures
during concurrent two-step migration are corrected by the matching source/runtime
fixtures; the final55-case calibration selection passes and includes those scenarios. No running GUI restart, device command or
physical/optical acceptance performed. Existing rig checklist retains those boundaries.

Oct14 `projector-sync-modes` completed locally under
[G01 revision190](../docs/architecture/gui.md#g01),
[V20 revision9](../docs/architecture/visual_stimulus.md#v20) and E14 revision208.
Synchronization follows Screen calibration and Rig geometry. Remove its MCU summary,
editor and obsolete projector contextual-wiring path; Projector flip input/offsets
are now owner-deferred under A11 revision46. Offer Free run (no VSync), VSync on pulse
display, and VSync on all displays; migrate both old labels on portable/review draft
load. Existing file-owned pacing identity remains independent of pulse placement.
Free run requests zero swap interval on every output, including retained marker/pacer
outputs; it preserves V10 scheduling, V22 pulse controls and nominal recording-rate
validation. Canonical model, published schemas, codec and fixed policy agree;
Visual Stimulus policy/config/loader version12 and verified policy digest match.

ARCH-002 review removes redundant wiring and keeps mode mapping in ProjectorTiming,
presentation requests in DisplayProfile and existing GL owner binding. No new process,
dependency or runtime back-reference. Projectors remains composition of focused
helpers; native/configuration owners retain existing cohesive responsibilities.
Local GUI16, configuration/rendering61, lifecycle34 and contract42 cases pass
(79 contract subtests); scoped Ruff/format12 files, Win32 mypy10 sources,
boundaries687/zero violations and whitespace pass. Initial policy-version/digest and
new-test API mistakes were corrected; sandbox temp failures avoided with workspace
temp paths, stalled lifecycle transport run interrupted and permitted rerun passes.
No running GUI restart, physical output/device action or optical acceptance.
[Evidence and commands](runtime-evidence-2026-10-14/projector-sync/context.json).
Remaining V20 optical/driver/full-load checks stay in the [rig checklist](rig-verification.md).

Oct14 `two-step-calibration-assets` completed locally under
[G01](../docs/architecture/gui.md#g01), [V01](../docs/architecture/visual_stimulus.md#v01)
and [E07](../docs/architecture/experiment.md#e07). Exactly two files remain
in `assets/calibration/` (the extra README is removed): `reference_bars.glb` contains only two native-pixel bars per
output; `frame_grid.glb` contains the physical frame/grid for measured scale/offset
adjustment. Each launch refreshes only its selected file. Remove the five generated
repository JSONs and old shared grid filename. Generated profiles/mappings and exact
working copies live outside the repository in separate per-step user runtime roots.
GUI intent captures source/profile digests; controller rechecks the source, matching
profile view and staged copy before passing the runtime root to protected renderer
preparation. The reference file's pixel metadata must match the protected outputs;
reject wrong lengths/grid files, stale copies and wrong step references. Preserve
revision/authority/deadline/bounds, correction-independent bars, V15 frame/grid mapping,
exact source ownership and cleanup. No hardware command or live restart occurred.

ARCH-002 reuses the mesh packer, existing profiles and protected-source pipeline.
Extend the focused shared path helper; extract the controller's separable bounded
file reader into `device/calibration_inputs.py` before adding stage validation.
No dependency/process/runtime back-reference. Remaining controller calibration and
projector widget size advisories are cohesive command/state ownership and composition,
without new unrelated responsibilities. Extend owning test modules rather than adding
per-fix modules. Media outside calibration stays external; demo generator remains
external-only. Source distribution includes the two patterns; repository-less wheel
execution still rejects unavailable diagnostic sources.

Validation: focused `.venv/Scripts/python.exe -m pytest` controller admission, GUI and
calibration-rendering selection with `-m "not windows and not rig"`:55 pass/450
deselections. Covers independent exports, unchanged grid after reference export,
source/runtime byte identity, stale-copy rejection, exact reference quad pixel spans,
wrong-length/grid rejection and source cleanup. Scoped Ruff/format10 files, Win32
mypy7 sources, boundaries689/zero violations, actual two-file backend GLB parsing,
reference metadata/geometry consistency, source-manifest contents, local links/anchors
and whitespace pass. `python -m build --no-isolation` builds sdist/wheel. A transient
script insertion lookup fails before adding the new test; corrected and verified.
No application restart/native-output/optical/full-workload acceptance claimed; restart
before using the new path. [Current evidence](runtime-evidence-2026-10-14/calibration-assets/two-step-context.json),
[55-case results](runtime-evidence-2026-10-14/calibration-assets/two-step-tests.xml).

Oct14 `renderer-opengl-adapter-selection` repaired under
[SYS-002 revision3](../architecture.md#sys-002) and
[E08 revision171](../docs/architecture/system-contracts.md#e08): use separate Windows
executable identities with identical verified prepared Python bytes. Before creation,
apply/read back power-saving preference for cephvr-python.exe (GUI/CPU) and high
performance for cephvr-renderer.exe. Preserve unrelated per-application options;
global/other-application preferences are untouched. Verify the role image against
prepared provenance at resolution/bootstrap; stale/tampered images fail explicitly.
Actual renderer NVIDIA model/UUID checks remain authoritative. CUDA/OF and RTX2080Ti
encoding owners remain unchanged. ARCH-002 reuses prepared interpreter/launch/containment
mechanisms with one focused preference helper, no extra process/dependency/fallback.

Fresh hidden probes prove AMD GUI/CPU and RTX5060Ti renderer selection. After normal
GUI save/closure and approved full E08 replacement, controller
5a66b261-7079-49d6-bf9b-8bfcad0bb9ad reports four outputs resources-ready/applied
revision1/returned Idle submissions without initialization issues. Live renderer
PID23168 uses NVIDIA UUID GPU-77642118-1623-48dd-3686-1014aa86b818; native GUI
PID13128 restores its draft, holds control and shows no failure dialog. Leave runtime
session75315 open. The remedy now correctly distinguishes full renderer restart from
GUI-only reopen. Earlier AMD context failure remains in raw evidence; the exact
historical driver-selection cause is unproven, while fresh placement/Idle is verified.

Final485 affected renderer/supervisor/platform-adapter/launcher cases pass/one
deselection; native prepared-role-image tamper/refresh case passes. Focused89 cases
also pass. Scoped Ruff/format8 files, Win32 mypy5 sources, boundaries687/zero
violations and whitespace pass. Initial sandbox asyncio loopback stalls are interrupted;
permitted replacement passes without weakened assertions. These rig checks cover
fresh contexts/Idle only, not OF/recording/scientific/optical/full-load acceptance.
[Methods, hashes and live/test evidence](runtime-evidence-2026-10-14/gui-refresh/gpu-selection-context.json)
and the [rig checklist](rig-verification.md) retain scope and remaining checks.
## Arena-file movement regions

[V16](../docs/architecture/visual_stimulus.md#v16) revision5 and the
[schema binding](../contracts/visual_stimulus/stimulus-schema.md) now allow explicitly selected
arena-file regions. The protected GLB provider retains the declared legacy geometry; the
compiler converts each unique asset/transform once, checks cancellation/deadline budgets,
transforms it into the existing convex sliding input and rejects inconsistent instance
geometry/invalid starts/empty insets, and retains the resolved polygon and resource fingerprint.
Prepared artifacts reject unresolved source selectors. Existing explicit regions remain
independent of metadata. Rectangular/convex imports are implemented; circular/cross/T/torus
imports and wrapping are outside this owner-selected increment. GUI evidence lives in the
[Runtime report](runtime.md#protocol-group-headings-and-arena-advanced-settings).

ARCH-002 review uses focused geometry-declaration and region-resolution helpers, existing
Pydantic models/GLB preparation ownership and owning tests; no dependencies or runtime
back-references. Source/prepared boundary schemas regenerated. Local Visual Stimulus suite
passes318/one deselected with loopback permission; the initial sandbox run passed309 and
failed nine socket binds, and a15-case authenticated rerun passes before the full pass.
Final protected-source-adapter→GLB metadata→compiled artifact/closure regression passes;
native protection is mocked, not established. Ruff/format, Win32 mypy313 sources, boundary
check694/zero violations and schema/document checks pass. Initial type/fixture issues were
corrected. Native arena limits/sliding/four-view agreement remain in the single
[rig checklist](rig-verification.md), with existing physical/hardware deferrals preserved.


Oct14 encoding rig test plan: [commands, matrix and collection](rig-verification.md#encoding-test-plan)
cover CQ16/CQ23 isolated/concurrent synthetic probes and separate live-app runs.
`tools/encoding_probe.py` collects external decode/frame counts, sizes, source/drop/
padding counters and renderer timing JSON. Review repaired launch/probe/decode failure
retention, bounded version queries, malformed-log isolation and empty/missing diagnostic
reporting; decoder error output suppresses successful throughput even with exit0.
The plan uses one executable warm-up/three-repeat matrix and documents independent
synthetic completion versus sustained live contention. Fifteen offline tool tests plus lint/format/
Win32 mypy pass; no FFmpeg/NVENC, PowerShell or hardware execution on this machine.
Eye inputs/readiness remain required; missing timing/completion evidence is not a pass.

Oct14 `stimulus-local-recording-improvements` completed locally under
[V12](../docs/architecture/visual_stimulus.md#v12) revision12 and
[E13](../docs/architecture/visual_stimulus.md#e13) revision24. Fresh native readback
bytearrays transfer exclusive ownership to the recording worker; borrowed inputs
still copy. Rejecting stale completion/cancellation now preserves a live reservation
instead of removing it before validation. The GL owner, bounded admission, evidence
priority, frame identity/order, padding and original I/O/closure deadlines remain.

File-owned `recording_runtime.review_scale_factor=2` multiplies the encoder-fit tile
divisor before GPU readback: the prior 2560x2000 example becomes1280x1000 (5.12MB
instead of20.48MB RGBA/frame). Exact scaled rectangles/dimensions remain in the
prepared recipe; empty or incompatible layouts fail Setup. Full-resolution rendering
and reconstruction inputs are unchanged; V13 offline implementation stays deferred.
Policy version13/fingerprint and additive file-policy Protobuf binding are synchronized.
Older absent scale fields mean1; deployed files must be reloaded through fresh Setup.

`recording.metrics` stores fixed count/total/max nanosecond aggregates for ready and
pending readback polls, admission-to-ready, ready-to-dequeue, row normalization,
pipe-write calls and admitted-slot lifetime; it retains timestamps only for admitted
captures. Peak/current slot occupancy, queued captures, zero-progress writes, bytes
submitted and cancellations accompany the aggregates. `recording_metrics` emits one
JSON summary through a dedicated INFO session logger on thread exit (including
failure/cancel), with event=recording_metrics and the evidence path. Worker startup
installs one stderr handler without changing root logging; rig tools must capture
renderer stderr. Oct14 review fixed the previously unconfigured INFO logger, which
normal root WARNING settings silently suppressed, and removed the non-JSON prefix.
Invalid encoder write counts now fail before updating submitted-byte diagnostics. A live diagnostic reader can call `metrics.snapshot()`.
Ready-poll time includes native mapping/copy/unmapping/cleanup, not isolated GPU time;
pipe-call time excludes asynchronous OS wait (use zero-progress counts and slot hold).
These are diagnostics, not scientific timestamps, encode acknowledgements or durability.

Validation: `python -m pytest tests/visual_stimulus -q -m "not windows and not rig"`
passes313/one deselected after review with loopback permission. Initial sandbox run passed300 but
blocked nine socket binds; those15 owning transport tests then passed with permission.
Final Ruff/format and Win32 mypy (151 sources) pass; boundaries689/zero violations.
Protobuf generation succeeds for19 sources. Existing owning tests cover exclusive vs
borrowed buffers, partial/blocked writes, delayed/out-of-order captures, cancellation,
stale reservations, bounded counters/timing, diagnostic exit logging and scaled tile
layout without display changes. Review adds root-WARNING/idempotent-handler JSON
emission and invalid-write-count regressions. No other actionable ownership/scaling
defect found in this source review; native stderr collection and encoding remain
rig checks. ARCH-002: diagnostics are a focused module; existing
oversized native owner only binds the scale/clock to existing lifecycle operations,
with no added process/dependency or whole-runtime reference. No native GPU/FFmpeg
encode or measured frame-drop reduction was claimed by that increment. PBO pooling
and GPU row orientation are subsequently implemented above; off-thread readback and
RGB/mono capture-layout changes remain deferred. Current mono encoding still takes
RGBA input at the reduced review dimensions; [native measurements](rig-verification.md)
remain pending.

Oct14 `encoding-quality-defaults`: owner selects CQ16 as the standard, p4, unchanged
camera dimensions (review composite now reduced as above), Behavior color 4:4:4 and Tracking mono; Eye and Stimulus mono
use explicit CQ23 test overrides pending owner evaluation. Mono chains explicitly
convert to gray then NVENC-compatible 8-bit YUV 4:2:0 with neutral chroma; future
color Stimulus uses 4:4:4. Camera source-depth protections remain; saved settings
retain E07 precedence. No automatic bit-depth reduction or camera/PFS edits.
[A08](../docs/architecture/acquisition.md#a08) and
[E13](../docs/architecture/visual_stimulus.md#e13) govern these lists.
Local validation: 34 configuration/filter-expression tests pass; all four token/filter
chains preserve dimensions, TOML/policy bindings load, Ruff/format and Win32 mypy
for the policy-binding module pass. Boundary check: 688 modules, zero violations;
existing size warnings concern unchanged owners, with no new responsibility added.
Installed GPU/FFmpeg conversion, visual
quality, size and combined throughput remain [rig checks](rig-verification.md).

Oct14 `always-save-scientific-evidence`: Required stimulus recipe and JSONL are now planned and recorded with review video off. The existing bounded writer persists actual state, submissions, diagnostics, feedback and completion without a capture worker, GPU readback or FFmpeg child. Evidence schema5 declares video_enabled; disabled captures are empty and encoder outcomes absent. The saved legacy switch retains its value and controls video only; the GUI explains always-saved scientific evidence.
Policy/config bindings updated together (acquisition21, Visual Stimulus14). Wiring,
trigger timing, assumed first-trigger anchor and trial boundaries are unchanged.
[Local evidence](runtime-evidence-2026-10-14/always-save-scientific-evidence/context.json):
affected acquisition/Visual Stimulus/controller suites pass1200 tests
(five skips, three deselections); offscreen recording-control check passes (478
unrelated GUI cases deselected). Ruff/format and Win32 mypy338 source files pass;
contract generation, TOML/schema consistency and whitespace checks pass. Boundary
review:690 modules, zero violations. Native acceptance remains in the
[rig checklist](rig-verification.md#always-saved-scientific-evidence).
ARCH-002: keep existing lifecycle owners and bounded queues; camera metadata terminal
assembly is a separate focused module. The larger camera session and stimulus native
owner remain cohesive schedule/ownership adapters, without whole-runtime back-references
or extra processes. Tests cover video-off sources/invalid images/bounds/cutoffs,
pre-onset cancellation and write failure, plus stimulus scientific records and feedback
interval closure without native capture/encoder ports. Existing video-on tests pass.

Oct14 projector power-on recovery under
[V19](../docs/architecture/visual_stimulus.md#v19) and
[E08](../docs/architecture/system-contracts.md#e08): all four saved DLP identities
enumerate at60Hz. The approved fresh runtime reports four resources-ready outputs,
applied configuration revision1 and returned Idle submissions with no initialization
issues. Saved GUI settings restore as a local draft; no Setup/Start or scientific
settings change. This closes the unavailable-display startup blocker only;
optical/calibration/full-workload acceptance remains in the
[rig checklist](rig-verification.md).
[Authenticated status and method](runtime-evidence-2026-10-14/gui-refresh/projectors-on-context.json).

Oct14 repository media cleanup keeps the demo manifest/texture descriptors in source
control and generates their nine sample PNGs locally through
`tools/generate_demo_assets.py`. Existing texture decoding tests now use temporary
samples; three owning decode cases and three GUI authoring/repetition cases pass.
[Cleanup inventory and validation](runtime-evidence-2026-10-14/repo-cleanup/context.json)
index the local-only screenshots/run datasets and generated binaries. V02/V04/V12
runtime ownership, actual saved media/evidence and scientific acceptance limits are
unchanged. The native sources/builders remain tracked; no active runtime is altered.

Device workflow refinement under [G01](../docs/architecture/gui.md#g01) keeps
projector assignment/participation separate from MCU input wiring. Projectors opens
a contextual editor for the canonical MCU draft, shows calibration prerequisites,
and keeps VSync editable independently of the photodiode pulse. Existing runtime
validation and ownership remain unchanged. The [runtime assessment](runtime.md)
owns local GUI evidence; native synchronization/optical acceptance remains in the
[rig checklist](rig-verification.md).

Oct13 texture implementation under [V02](../docs/architecture/visual_stimulus.md#v02)
and [V04](../docs/architecture/visual_stimulus.md#v04): the previous importer required a
tagged `.texture.json` plus preview PNG. CephVR1 instead treats JSON as a procedural
recipe. The new image-producing recipe profile retains/hashes the original JSON and
protected image dependencies, prepares deterministic RGB8 pixels under existing
source/workspace/CPU/GPU/deadline limits, and uses configured geometry for polar
patterns. Preview PNGs are not authoritative. Plain JSON and legacy parameter aliases
are accepted by content; GUI and headless programs use the same prepared resource
path. Explicit tile dimensions update authored periods; missing dimensions preserve
the existing authored size. Source-derived fixtures substitute for the owner's files,
which are unavailable here. Source-derived pixel/provider checks pass; no actual-user-file or native acceptance
claim is made.

Independent image-tile appearances now support direct reference motion links.
Bottom-centered unfolding preserves linear speed across perpendicular screens and
opposite local axes. Angular flow follows V02's subject-distance convention. Each
follower retains its own asset, periods, phase and reset choice. Standard state fields
bind at epoch boundaries using retained orientations; no frame-time coordination or
second phase state is added. Custom/Tracking motion, chains/cycles, competing motion
writers, combined drift plus spin, nonuniform/reflected stimulus maps and skew-plane
spin are explicitly rejected. Output calibration reflections are separate. Spin
requires a known subject-centered reference pivot; Setup reports the necessary
coordinates and runtime rechecks the retained center. GUI linking disables follower
movement controls, including controls reparented into the reference table.

Astra review found a coordinate discrepancy: stimulus-schema declared a bottom-left
physical origin, while rendering/layer_projection.py's physical_corners emits
`2*local/extent`, making zero the screen center. Oct14 owner decision
([V14 revision 4](../docs/architecture/visual_stimulus.md#v14)): the surface-local
origin is the surface center, so the contract now matches the renderer and spin guard
and no placement changes. Surface maps authored against a different origin must be
regenerated (the owner is redoing calibration and surface mapping). A rendering
regression pins the convention. Normal drift is independent of the pivot limitation.
[Rig acceptance](rig-verification.md) remains deferred.

Final local texture validation:277 Visual Stimulus tests pass (one rig/platform
case deselected),42 contract tests/79 subtests pass,11 schemas are current, and14
focused GUI cases pass. The earlier broad GUI run had450 passes/seven failures while
another chat changed epoch editing; the final14-case run includes every previously
failing case, after the layout, demo recipe expectations and concurrent epoch changes.
This is not a fresh full-GUI-suite pass. Demo JSONs now explicitly declare their
existing PNG as an image input; three exact pixel comparisons preserve their original
checker/noise/sine appearance. Procedural recipes require no preview PNG.

Scoped Ruff/format checks pass23 feature files; Windows-target mypy passes19 sources,
boundaries pass676 modules/zero violations, and dependency consistency passes. Initial
sandbox transport retries failed on prohibited loopback binding; the permitted rerun
passes without weakening assertions. Packaging reaches the existing AMD64-Windows
native-DLL guard on this macOS host; no package/native acceptance is claimed. Luna
writing, Sol6.1 integration and Astra main review are complete. Dated commands,
source provenance and limitations are in the [texture evidence](runtime-evidence-2026-10-13/texture-recipes-motion/context.json).

Oct13 local recovery repair under [V01](../docs/architecture/visual_stimulus.md#v01)
and [E06/E08](../docs/architecture/system-contracts.md#e08): worker-local failure
recovery previously bypassed command registration and forwarded its cleanup under a
UUID the coordinator never issued. It now registers a command-local retained
admission/outcome before dispatch, keeps cleanup on the worker query route, preserves
exact context/deadline/replay and prunes local routing with the ledger. Coordinator
unknown-ID validation and supervisor-issued cleanup proof remain strict. Teardown
attempts owner/report/listener/channel closure with the original deadline even after
report-drain failure, then propagates the first failure.

The threaded RenderOwner/ReportBridge regression covers cleanup emitted while local
shutdown executes, prior finalized session scope, replay and pruning. Failure injection
verifies listener/channel attempts after drain rejection. Final authenticated transport
passes9; the [cross-owner validation](runtime.md#unresolved-findings-and-limitations)
records1316 passes/five platform skips/four deselections plus static checks and Luna/
Sol6.1/Astra review. [Raw provenance](runtime-evidence-2026-10-13/dev-machine-repairs/context.json)
retains the final-helper rerun boundary. This repairs a concrete local recovery defect,
not a reproduction of the complete historical failed-Setup/prior-calibration workflow.
Native failed-Setup/reuse and Save On-to-Off remain [rig-deferred](rig-verification.md).

Oct13 owner-authorized combined rendering/reset repair verifies two consecutive
normal60s Behavior/Tracking recordings at3602/3601 actual render groups
(60.0333/60.0167 groups/s), improving the combined baseline39.47/s. Renderer GPU0
and both camera/review NVENC GPU1 are confirmed by exact live PIDs/UUIDs in four
samples per trial. All six videos externally count/fully decode; both sessions close,
reset and restore original settings in the same live generation.

Under [V12](../docs/architecture/visual_stimulus.md#v12)/
[E13](../docs/architecture/visual_stimulus.md#e13), native row conversion, completed
PBO mapping/private copy, actual-context no-op checks, normalization outside admission
lock and private native pipe copying remove recording contention. Original ownership,
slot bounds, precision and encoder settings remain. Preparation release receipts are
retained for cleanup retry until all source/consumer ownership closes, then retired at
new preparation; this fixes the reproduced On-to-On unknown-resource shutdown.
That historical CPU budget included padding, readback/pipe copies and half-frame
scratch; the current sequential path retains the conservative ceiling without padding.
ARCH-002 keeps the existing cohesive native/preparation owners with small helpers,
no new dependency/process or whole-runtime reference.1123 regressions pass/3 skip/
6 deselect, native pipe14 pass, Ruff/static mypy427/boundaries667 pass.

Nominal60fps is not uniform frame timing or optical proof: repeat p9927.56ms,
max37.88ms. Review fidelity remains limited:1176 real samples/2367 capacity drops/
58 same-slot omissions and2424 explicit duplicates in3600 encoded frames. Dedicated
Save On-to-Off native verification, Eye/locomotion Tracking and paired/optical
acceptance remain open. Original GUI/settings are restored. Historical stimulus-only
measurements below remain distinct from this combined result.
[Dated raw evidence, verification and limits](runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)

Oct13 `stimulus-throughput-repair` implements the measured review-capture fix under
[V12](../docs/architecture/visual_stimulus.md#v12)/
[V20](../docs/architecture/visual_stimulus.md#v20)/
[E13](../docs/architecture/visual_stimulus.md#e13). Matched native60s trials on four
RGB8/all-output-VSync outputs show Save On30.13 real groups/s versus Save Off60.03/s.
Save Off's trial completes but session cleanup fails on an unregistered resource
after the preceding Save On session; this pre-change transition defect stays open.
Mean float-composite glReadPixels12.98ms and capture polling6.54ms dominate the
recording cost. Use an RGBA8 compositor for the already selected8-bit review path,
retaining float32 for packed10-bit, and fill a fresh host bytearray directly instead
of allocating a NumPy result then copying to bytes. The recording owner still copies
that buffer into its own bounded slot; deadlines, source/output rendering precision,
all-output VSync, trial timing and admitted-sample accounting are unchanged.

The first framebuffer-only run completes at50.42 real groups/s. The final instrumented
recorded run completes3600 real groups/60s (60.0/s),3422 real captures,178 padding
duplicates,166 same-slot omissions and12 capacity drops; all stimulus outputs close,
metadata syncs, reservation unlocks and external decode/recipe verification pass.
Mean readback submission falls to0.736ms and capture polling to3.40ms. These are
inclusive diagnostic timings, not optical measurements. A native768-pixel comparison
of the same compositor shader observes at most one8-bit code difference from the
former float-to-byte rounding; review video is not bit-exact, while physical
rendering and V13 input precision are unchanged. Final uninstrumented confirmation
also completes3600 real groups/60s (60.0/s):3423 real captures,177 duplicates,
169 same-slot omissions and eight capacity drops. All outputs close, metadata syncs
and original configuration restores; external count/full decode/recipe verification
passes for both final runs. The normal
uninstrumented GUI/runtime is left open in Configuration. Sustained simultaneous
camera/Tracking work and optical timing remain unverified.

ARCH-002 review keeps the implementation in the focused existing capture owner,
with no dependency/process or policy change. Native/scene modules receive only
transfer-type annotations; their existing cohesive size advisories remain reviewed.
Extend the owning rendering behavior module for8/10-bit retention, representation
locking, zero-wait fence polling and exact caller-owned host writes. Owning suite
passes244; Ruff check/format152 files, Win32 mypy136 sources and boundaries667/
zero violations pass. Retain failed diagnostic bootstrap/interrupted attempts,
concurrent GPU-placement context and complete native runs separately in the
[throughput methods/results](runtime-evidence-2026-10-13/throughput/context.json).

Oct13 owner-authorized GPU placement repair is now natively verified under
[SYS-002](../architecture.md#sys-002)/V19. Through NVIDIA Control Panel, add the
exact managed .venv/Scripts/cephvr-python.exe program and set OpenGL rendering GPU
explicitly to RTX5060Ti, then Apply. The previous generic Windows GpuPreference=2
entry and inherited NVIDIA global choice were insufficient proof of the actual
context. Leave CUDA GPUs at All and other driver/encoding settings unchanged.
The managed-image native renderer now verifies all four contexts against
GPU-77642118-1623-48dd-3686-1014aa86b818 (CUDA ordinal0), initializes actual assigned
RGB8 output modes/Idle and releases every native obligation. The owner's exact
Miniforge-base start_runtime_gui.py launch subsequently confirms all four outputs
ready without display issues in generationc3532451-334e-4874-beaa-3e181be7bc2d.
Leave that runtime/GUI open; no existing session is interrupted by this task.
These checks establish placement/startup, not optical correctness or sustained
presentation/encoding throughput. A separate concurrent throughput task remains open.
[Methods/raw GPU evidence](runtime-evidence-2026-10-13/gpu-placement/context.json).

Oct13 renewed owner screenshot/live read-only snapshot confirms a current AMD
adapter rejection, not only an old popup: controller generation10dc50d5-98da-463f-9bb9-02516f041026,
InitializeDisplay commande9933d53-eec0-4ec9-afa2-e04f8a1e3532 reports AMD Radeon
instead of RTX5060Ti, with all listed display resources released. The screenshot
shows the VS Code start_runtime_gui.py route and a visible Behavior preview;
read-only process paths confirm managed cephvr-python.exe children. Its exact
HKCU UserGpuPreferences entry already contains GpuPreference=2. That registry value
does not establish the requested actual context, and repeating the generic remedy
is not a verified repair. That earlier read-only investigation prompted the explicit
program-setting change and successful native checks above, which now close adapter
selection. Its prior matched RTX startup runs remain historical evidence.
[Controller assessment](runtime.md).

Oct13 fresh workflow audit: normal calibration assets fail pacing validation; a
separate profile using current accepted all-output VSync passes native grid Open,
two adjustments and confirmed Idle/closure. Regenerate the ordinary diagnostic
bundle before retesting its GUI path (V01/V19/V20). Independent open-loop60s
stimulus recording completes and externally decodes:3600 encoded frames/60s,
1820 real render groups (30.33/s),1805 captured groups,1795 duplicates and15 drops.
Median group interval32.18ms; median summed four-output swap durations2.42ms.
This run does not support the older sequential-swap bottleneck hypothesis as its
dominant explanation; capture/draw/context/transfer costs still need stage timing
and a matched Save-Off comparison. Padded60fps video is not60Hz optical evidence.
Combined camera recording cannot start with unset drain policy, and its failed-Setup
cleanup crashes the renderer on an unknown cleanup command link. Preserve that
separate E06/E08 failure for repair; normal stimulus-only closure and final exact
application shutdown pass. [Failure/remedy inventory](runtime.md),
[raw and external verification](rig-evidence-2026-10-13/workflow-tests/).

Oct13 Windows rig: V19 startup confirms four 60 Hz RGB8 outputs with requested
interval-1 swaps. A V01 native grid diagnostic using retained dummy geometry and a
separate all-output-VSync profile passes Open, live adjustments at sequences 1/2,
and Close with confirmed Idle/resource closure; accepted configuration is unchanged.
No optical accuracy, physical timing, mixed-DPI, reference-bar measurement or sustained
presentation-rate claim follows. The earlier native chooser crash is repaired under
G01; native GUI now completes with two separate hover-test failures, while the earlier
offscreen stage retains three projector-layout failures. The cross-owner assessment
below records exact stages and remaining limits.
The initial FFmpeg/ffprobe 4.3.2 incompatibility is resolved by the later matched 9.0.2
upgrade and synthetic composite closure check on RTX 2080 Ti (see runtime.md).
Recording/full-load acceptance remains open. [Current cross-owner assessment](runtime.md),
[raw evidence](rig-evidence-2026-10-13/) and [remaining rig checks](rig-verification.md).

Oct12 subgroup variations implement [V03 revision12](../docs/architecture/visual_stimulus.md#v03)
and [V08 revision5](../docs/architecture/visual_stimulus.md#v08): compact seeded rules
replace eager new repetition tables. Setup resolves by immediate-group repetition
index after condition substitution and validates concrete settings; it checks the
configured expanded-plan limit before sampling. Legacy tables remain supported.
No renderer RNG or device ownership changes. GUI authoring is compact at 10,000 and
1,000,000 repetitions; concrete Setup plans still scale with expanded epochs and
remain bounded (currently 100,000). The [current GUI/compiler assessment](runtime.md#current-scope-and-review)
records source/schema changes, 233 passing Visual Stimulus tests/one deselection,
layout evidence and native/rig limits.

The Oct12 model-hierarchy audit deeply traced live-calibration identities, sequence,
deadline, validation versus uncertain GPU failure, presentation/closure and blackout
ordering, with sampled compiler/media/recording/feedback paths. RT-001 identifies a
controller admission omission during application shutdown; the
[current cross-owner assessment](runtime.md#current-scope-and-review) owns its disposition
and verification. No renderer change or measured performance improvement is justified
by this pass. Native optical/GPU/full-load acceptance remains in the
[rig checklist](rig-verification.md).

Oct12 live frame/grid adjustment follows [V01 revision 18](../docs/architecture/visual_stimulus.md#v01)
and [G01 revision 148](../docs/architecture/gui.md#g01). A leased UpdateDisplayCalibration
carries bounded affine rectangles for the exact active diagnostic/revision and an
increasing sequence. Validate the whole request before writing existing GL-owner
warp buffers; render and present all outputs without asset replacement/window reopening.
The protected base profile/arena and inversion remain fixed. Evidence confirms the
sequence only after all outputs present; pre-write rejection retains the healthy
prior projection/sequence and reports failed update, while GPU/presentation uncertainty
remains Unknown with exact closure available. Fenced sessions never resume through
an adjustment. GUI partial/invalid edits send nothing; coalesce behind one update.

ARCH-002 keeps admission/validation/presentation in focused helpers and existing
renderer resource ownership. Buffer references alias existing tracked resources;
there is no additional GPU allocation or dependency. Affected backend suites
pass 659 tests/one deselection before the final mesh-precision guard, including authenticated controller-port/coordinator/
renderer transport with hardware injected. The final guard run passes 658 and
times out in one CLI-help case; the unchanged case passes an isolated rerun. Sixty GUI cases and seven final correction
cases pass (overlapping); source/static/contract checks and wide/narrow active-control
inspection pass. [Current dated evidence](runtime-evidence-2026-10-12/live-grid-context.json)
retains scope, failures and staged source context, without claiming full exact-final
coverage of concurrent Protocol/photodiode edits. Older workflow evidence below
remains distinct. Native GPU/Windows/DPI, optical correctness/latency and repeated
live-edit/closure acceptance remain in the [rig checklist](rig-verification.md).

Oct12 [V15](../docs/architecture/visual_stimulus.md#v15),
[V19](../docs/architecture/visual_stimulus.md#v19) and
[V22](../docs/architecture/visual_stimulus.md#v22) implement owner-requested
CephVR1.0-style output masks and photodiode placement. Optional output rectangles
clear mapped scene pixels to linear black before existing color correction; an
optional black marker area contains a separately positioned rectangular Pulse drawn above the
zones. Static zones persist in Idle and frame/grid diagnostics, including GUI bundle
export; raw measurement bars remain unobscured. The marker Frame/Pulse remains
trial-only, with the existing alternation and landmarks. Legacy patch rectangles
remain valid; positive integer rectangles must fit, with no clipping or resizing.
Planning preview illustrates placement with a white pulse. G01 revision150/V22
revision5 use a Frame/Pulse table with independent width/height and relative Pulse
origins. Full Projectors files are version 7; version-6 Size migrates into equal
dimensions and older standalone rectangles remain valid. Numeric calibration remains
version 4. Fifty affected cases, nine final presentation/file/render/parity cases
and 42 contract cases/79 subtests pass;
[current table evidence](runtime-evidence-2026-10-12/pulse-definition-table/context.json)
records the source stages, both-width captures and passing Ruff/format (289 files),
Win32 mypy (271 sources), 11 schemas/zero drift and boundaries (649 modules/zero violations).
Existing shared DataTable and rectangle/file owners replace the form/single Size
controls without new dependencies, rendering resources or runtime state.

ARCH-002 isolates zone editing and scissor-preserving clearing, keeps rendering and
calibration ownership intact, and moves photodiode draft/import operations out of
the large Projectors panel. Remove duplicate output lookup and fixed-page-height
plumbing. Native/scene size advisories retain cohesive rendering/resource ownership;
no shader, dependency, process or persistent GPU resource is added. The earlier local
GUI/Visual Stimulus/contract integration stage passes 665 tests, one Windows/rig deselection
and 79 contract subtests. Its 21-case final affected selection covers the initial
layout/export changes; these cover file migration, submission mapping, output bounds,
marker-over-zone order, grid/raw-bars behavior, scissor restoration, preview pixels,
growing tables and 1280/720 Runtime/Review parity. Ruff/format (289 files), Win32 mypy
(271 sources), schemas (11, zero drift), boundaries (649 modules, zero violations)
and whitespace pass. [Current source-stage context and raw evidence](runtime-evidence-2026-10-12/output-overlays/context.json)
retain corrected fixtures, observed layout defects and loopback-permission retry.
Both-width offscreen captures are inspected. Native Windows/WGL/DPI, optical black
levels/placement/timing, recorded GPU pixels and throughput remain unverified in this
increment; the existing [rig checklist](rig-verification.md) owns those checks.

Oct12 cleanup removes three constructor fields with no readers: the decoder's unused
ID counter, the scene renderer's unused clipping set, and the native port's unused
Idle color cache. Active state and evidence remain with their existing V01/V11/V19/V21
owners. Under ARCH-002 these cohesive modules shrink without new dependencies or
responsibilities. Final cross-owner selection passes 795 tests; affected Win32 mypy,
repository lint/format and boundaries pass. Raw cleanup logs and hash manifests were
removed at the owner's request on Oct12; these results remain historical summaries.
This establishes no new optical, native GPU,
throughput or rig acceptance.

Oct11 startup repair follows existing [V19](../docs/architecture/visual_stimulus.md#v19)
and E06/E08. Missing or ambiguous saved monitor identities produce a typed
configuration rejection only after exact sessionless resource release and confirmed
display evidence delivery within the original deadline. Controller/GUI operation
status exposes the corrective issue; Configuration remains available and a fresh
Setup can reuse the worker. Every identity is resolved before any window opens.
GPU/context errors, cancellation, expired deadlines, uncertain cleanup and failed
evidence delivery retain the existing failure path. The
[startup contract](../contracts/visual_stimulus/startup.md) records the evidence order.

ARCH-002 extracts coordinator display-report handling and the existing sessionless
cleanup helper. Native renderer and lifecycle files remain cohesive ownership
orchestrators; no new dependency, process or policy choice is introduced. Owning
renderer/lifecycle/coordinator/authenticated-controller cases cover missing/ambiguous
identities, complete versus stale/unreleased proof, cleanup/GPU/deadline/cancellation
failure and fresh Setup. The full portable suite passes 1,861 tests with six skips
and eight Windows/rig deselections; [current results](runtime.md) retain source and
validation scope. Native disconnected/reconnected startup acceptance remains in the
[rig checklist](rig-verification.md); this is not optical/throughput evidence.

Oct9 [V20/V15](../docs/architecture/visual_stimulus.md#v20) permits all-projector VSync
without a designated pacer. [E13](../docs/architecture/visual_stimulus.md#e13) derives
recording cadence from the common exact nominal enabled-output rate and records
null pacing identity; differing rates reject. Mixed mode still requires its selected
pacer. Policy/config version 9 and the prepared schema bind this behavior. Oct11
local regression/contracts/declarations cover it. The Oct9 Windows full-suite timeout
and passing focused rerun remain [historical evidence](review-evidence-2026-10-09/mcu-configurable-context.json);
its native cause is not proven fixed by the Mac pass. Native MCU Apply and a new
rendering/recording run remain pending.

Earlier Windows checkout `94285ac` passes the complete non-rig suite, all 42 stimulus
contract cases and 11 schema matches after regenerating stale local bindings.
[Current cross-owner results and limits](runtime.md) retain exact evidence; presentation,
encoding throughput and optical acceptance remain separate rig checks.

Oct9 authorized baseline repair restores the 500 ms preparation lead and unsets the
diagnostic pacing-output identity; camera drain margins are also unset. All 36 owning
configuration cases pass. Visual Stimulus contract discovery passes 42 tests and all
11 generated schemas match. [Current integration evidence](review-evidence-2026-10-09/implementation-context.json)
records full local validation; native presentation/encoding throughput, scientific
timing and owner-deferred encoder acceptance remain in the [rig checklist](rig-verification.md).

Measured-reference baseline (Oct12, `two-stage-projector-calibration`)
follows [G01 revision 146](../docs/architecture/gui.md#g01),
[V01 revision 17](../docs/architecture/visual_stimulus.md#v01),
[V15](../docs/architecture/visual_stimulus.md#v15) and
[V24](../docs/architecture/visual_stimulus.md#v24). The owner explicitly selects
config-controlled actual projected lengths. Per-screen `reference_x_px` /
`reference_y_px` resolve into output `reference_bars`, shared by native calibration,
measurement conversion and planning preview. Positive whole-pixel lengths must fit
the output; faces sharing an output must agree. Unset values retain the original
rounded quarter-output spans. Measure reference bars selects the protected `reference_bars` view: bars only on
black in exact native pixels, independent of prior measurements or corrections.
Adjust frame and grid selects `frame_grid`: complete mode-matched measurements
produce physical screen/image ratios combined with manual scale/offset/inversion.
Neither action requires throw ratio or projector distance. Both retain the same
V01 protected-input, GL ownership, Active/Closed evidence and deadline/cleanup paths;
Close must confirm release before switching views. The frame/grid uses V15 and does
not draw measurement bars; normal trial rendering ignores diagnostic selection.

Runtime and Review share the Pixel-to-mm calibration card with three equally
stretched columns and no explanatory text or pixel columns: Screen, paired Measured X / Y (mm), and read-only X / Y (mm/px).
Measured pairs derive scale independently of throw ratio; ideal read-only projector
distance additionally uses a positive config-only effective throw ratio. Physical screen
and subject distances remain independent. Full Projectors JSON version 7 / numeric
version 4 preserve lengths and measurements. Legacy full versions 3/4/5/6 and numeric
versions 1/2/3 migrate without changing prior spans or unmeasured historical distance.
Invalid lengths reject before draft mutation. Output-mode mismatch invalidates scale
without replacing measurement provenance. Export/submission preserves original
assets and creates content-addressed GUI affine corrections; imported nonlinear,
masked or weighted corrections still reject automatic replacement.

ARCH-002 retains focused measurement/file/profile helpers and existing native
render ownership, adding no dependency, process or persistent GPU resource. The
existing projector panel remains orchestration; boundary cohesion advisories retain
their established owners. Final affected GUI/config/render/preview selection passes
74 tests; separate contract discovery passes 42 tests with 79 subtests. Ruff/format,
Win32 mypy (265 sources), 11-schema drift and boundaries (642 modules/zero violations)
pass. Wide/narrow two-action card captures are visually inspected offscreen.
[Current workflow methods, hashes, failures and raw results](runtime-evidence-2026-10-12/calibration-workflow-context.json)
preserve local scope; [earlier measured-bar evidence](runtime-evidence-2026-10-12/projected-bars-context.json)
remains historical. No native Windows/GPU, optical, full GUI regression or rig
acceptance is claimed. Current zoom/keystone/fold, bar spans and physical mapping
remain in the [rig checklist](rig-verification.md).

Oct8 unpaired dummy execution uses all four saved active projector identities,
isolated **uncalibrated** geometry/color profiles and a 60-second procedural grating.
Temporary Front 60 Hz pacing satisfies [V20](../docs/architecture/visual_stimulus.md#v20).
Real startup observes required Idle submissions/framebuffer sizes/RGB precision
after strict SYS-002 RTX 5060 Ti verification. This is native initialization evidence,
not optical accuracy, timing or full-load acceptance. Runs40–42 complete real Setup,
Start, the immutable 60 s trial, output closure and session cleanup. Later run43
[output evidence](rig-wiring-evidence-2026-10-08/dummy-experiment/unpaired-run-43-output-verification.json)
records 1,182 admitted/submitted frames, four capacity drops, zero unresolved attempts
and confirmed EOF/drain/zero encoder exit. External count/full CPU decode and recipe
digest checks pass. Its 2560×2000 H.264 MP4 is 19.7 s at nominal 60 fps for a 60 s
trial; median render interval is 49.29 ms. This supersedes run42's 1,419-frame/23.65 s
measurement for the latest retained workload, without establishing a regression or
cause across differently loaded runs. Throughput and unpadded elapsed-time compression
remain separate issues; padding cannot restore missing physical presentations.
See current [E13](../docs/architecture/visual_stimulus.md#e13) sequential recording above and the
[rig checklist](rig-verification.md); this is not a scientific timing pass.

Recording uses one bounded full-frame pending encoder write instead of polling every
256 KiB, preserving native ownership/partial-progress/deadline rules. Bottom-up rows
are normalized exactly once even when the first write is pending. At cutoff, finish
already-admitted GPU transfers before sealing evidence; unresolved original-deadline
transfers still fail. Calibration CPU closure receipts survive retries and are revoked
on reopening a logical source. These fixes use existing owners under ARCH-002, V01/V12
and E08; owning recording cases pass 28. Oct9 restores defaults and records current
regressions above; all native attempts retain their dated raw evidence.

Under V01/V04/E08, disable GLFW's automatic fullscreen iconification so the four
windows survive focus changes. Load each current GLFW context with ModernGL's
loader-only initialization; GLFW retains sole WGL lifetime ownership. Detected
glcontext wrappers otherwise destroy an already GLFW-owned context at release,
observed as invalid WGL handles during cleanup. Move video selector/reset binding
from CPU preparation to the existing graphics handoff. Register the exact empty
revision-zero session cleanup catalogue before recipe/renderer resources, under the
existing catalogue lock. Retain private operation results locally and route only
Setup completion to the controller; display readiness still requires actual Idle
evidence. Native tests exposed these failures; no identity, precision, resource
proof or deadline check is bypassed.

Shared probe parsing now accepts FFmpeg's four-column pixel-format table; the
existing RGBA8 and packed RGB10 capture ABIs have explicit layout/matrix validation.
Capability evidence names conform to the existing prepared-record identifier schema.
System PATH FFmpeg 4.3.2 lacks the saved p4 preset; an isolated process PATH uses the
already installed static FFmpeg 7.1, preserving encoding arguments and global PATH.
The cached FFmpeg 8.0.1 package could not execute with available DLL paths and is
not adopted. Current ffprobe remains the installed 4.3.2 executable; actual output
inspection is recorded for run43 above. [Current integration assessment](runtime.md#current-scope-and-review),
[raw attempts and focused checks](rig-wiring-evidence-2026-10-08/dummy-experiment/).
The complete Visual Stimulus suite passed 170 before the latest context/format
repairs; latest focused context/registry checks pass 44, CPU handoff one, probe 28,
and strict review format eight. A later complete validation will supersede these.
Current source checks pass lint/format and 149-source Win32 mypy. Existing rendering
and session files remain cohesive owners; the small native attachment helper lives
in native_display under ARCH-002.

Library ownership references: [GLFW fullscreen hints](https://www.glfw.org/docs/latest/window_guide.html),
[ModernGL context creation](https://moderngl.readthedocs.io/en/latest/topics/context.html),
[ModernGL loader lifetime](https://github.com/moderngl/moderngl/blob/5.12.0/_moderngl.py).

Historical Oct9 timing validation used nominal-slot selection/padding, now superseded
by the Oct16 sequential implementation above under [E13](../docs/architecture/visual_stimulus.md#e13).
Its retained checks below establish only the source and policy tested at that date.
Pre-T cancellation, immutable cleanup cutoff, omission accounting and proved camera
tail boundaries are corrected. Successful encoder input is retained before maintenance;
a missing required mapping poisons normal retry. Sol accepts the corrections after 53
focused checks and the reproduced cancellation/omission paths. Astra independently
accepts these corrections and the exact camera terminal proof, with no remaining
padding finding. [Astra evidence](review-evidence-2026-10-09/nongui-astra-review.txt).
Repository-wide lint/format, Windows-target mypy, boundary and contract/schema checks
pass; the final portable suite passes and Sol/Astra accept the integrated source.
[Exact full-suite result and provenance](review-evidence-2026-10-09/nongui-context.json)
retain counts, source hashes and limits. Local checks
do not establish native encoder behavior or throughput.
[Current handoff](review-evidence-2026-10-09/nongui-luna-padding.txt),
[Sol review](review-evidence-2026-10-09/nongui-sol-padding.txt).
Original deadlines and rig deferrals remain.
The stimulus and acquisition wrappers now share the protected native launch handshake;
backend registration/retirement and exact native ownership remain with their owners.
[Shared launch review](review-evidence-2026-10-09/nongui-sol-launch.txt) passes locally;
Windows equivalence remains a rig check.

Oct9 local analysis of run43 finds 1,186 real groups in 60 s (19.77 groups/s), with
99.66% capture admission and all admitted inputs submitted at closure. Four capacity
drops do not explain the render-rate gap; this does not rule out recording-related
CPU/GPU contention. [Retained arithmetic and limits](review-evidence-2026-10-09/nongui-throughput-assessment.json)
require controlled per-stage rig measurements. Padding preserves review duration;
physical presentations and encoder/toolchain acceptance remain separate.

Oct11 source trace strengthens the multi-output pacing hypothesis. Decoding the
retained run43 Setup, pre-final and final snapshots gives the same controller/session,
`all_outputs_vsync`, four 60 Hz 8-bit outputs, and four retained requested swap intervals
of 1. The earlier Front-pacer description must not be read as interval 0 on the other
outputs: all-output mode requests VSync on each regardless of the selected pacer.
The current native presenter swaps all windows sequentially on one GL thread. The
49.29 ms median is near three refresh periods; accumulated swap waits are a leading
hypothesis, not measured causality. Retained display intervals are startup evidence,
not per-trial swap durations. [GLFW semantics](https://www.glfw.org/docs/latest/window_guide.html#buffer_swap)
allow driver overrides, so requested settings alone cannot establish actual waits.

Recording remains a second candidate: shared-context ordering, RGBA32F composition,
per-frame PBO allocation, readback and the completed CPU copy run on the GL thread.
Each 2560×2000 capture carries 20.48 MB; 60 fresh captures/s means 1.2288 GB/s of
payload before extra copies/encoding. This is arithmetic, not a measured bandwidth
limit. Recording normalization also holds the lock shared with capture admission.
The packed-10-bit Python mask loop is irrelevant to this 8-bit run. The trial loop
has no intentional 50 ms pacing delay, and later nominal-slot padding cannot cause
the historical run. Preserve accepted pacing; inspect raw submission entry/return
records first, then measure draw/capture/readback and recording on/off on the rig.
[Snapshot hashes, extracted settings and limits](runtime-evidence-2026-10-11/throughput-source-trace.json)
retain this investigation without claiming a backend fix or native benchmark.

Projector configuration JSON (2026-10-08) under [G01](../docs/architecture/gui.md#g01)
now combines all Projectors GUI experiment settings with reusable runtime profile
references. Physical inventory/mappings remain current; participation and pulse target
restore by logical face. Submission preserves geometry/color references and shared-output
coverage while rebinding current native properties. Numeric-only and legacy runtime
files remain supported through one Load JSON / Save as row. Full backend preparation
validation remains authoritative; no physical output is driven by loading a file.
ARCH-002 review extracts portable profile/native rebinding and file settings into focused
helpers; the Projectors panel remains the shared UI composition/selection owner. No new
dependency, backend process or policy choice is added. Validation results follow in the
[current runtime assessment](runtime.md#current-scope-and-review); Windows/optical
acceptance stays on the existing rig checklist.

Calibration authoring update (2026-10-08) under
[G01](../docs/architecture/gui.md#g01)/[V01](../docs/architecture/visual_stimulus.md#v01):
Launch always exports the grid using saved rig planes and display corrections.
CephVR1.0 `914ecbc` supplies world-phase colored solid/dashed grid, full-face center
cross, physical face dimensions and 50 mm ruler strategy. Guide geometry is built
once in a focused helper; narrow faces omit a ruler that would not fit, and labels
stay inside the face with dark backgrounds. Local tests verify world phase through
reversed U axes, midpoint spans, physical reference length and backend GLB parsing;
the sample asset is 316,004 bytes. Two focused cases pass after final guide formatting.
[Current local suite](runtime.md#current-scope-and-review) passes; actual corrected
output and optical measurements remain in the existing rig checklist. No projector
was driven in this local increment.

Latest Windows execution (2026-10-08, `7ba43b1` plus controller/native repairs):
managed coordinator/renderer startup, bounded idle and exact application cleanup pass.
Final full suite passes 1463 with eight existing GUI clipping failures/five privilege
skips; Visual Stimulus contracts/schema drift pass. The authenticated calibration
Shutdown test now waits for the asynchronous coordinator settlement inside its
existing bound; no runtime policy changed. Inventory finds only the operator display,
with no active projector outputs or saved profile/assignments. Actual corrected
Launch/Close and optical timing remain untested. [Dated methods/results](rig-wiring-evidence-2026-10-08/README.md)
retain scope; the [single rig checklist](rig-verification.md) owns remaining acceptance.

Earlier Windows check (2026-10-07, `08d146d`): managed coordinator/renderer startup
and long idle process liveness pass; normal authenticated application shutdown
confirms exact process absence. Inventory finds four projector outputs at 60 Hz.
The saved experiment profile, output-to-surface assignments and asset root remain
unset, and no exported diagnostic profile/arena was supplied. Untimed Launch/Close,
first-use restoration, physical corrections and optical timing therefore remain
pending. Native automated tests run in the full suite; GUI failures and native
teardown crash prevent blanket rig acceptance. See the
[current runtime assessment](runtime.md#current-scope-and-review) and
[dated raw evidence](rig-wiring-evidence-2026-10-07/README.md). E15 and the existing
encoder/scientific deferrals are unchanged.

Updated: 2026-10-08. The complete Visual Stimulus implementation is selected under
[ARCH-001](../architecture.md#arch-001). This report describes the uncommitted working
tree, preserving the existing controller, supervisor and acquisition work.
[V01–V28/E13](../docs/architecture/visual_stimulus.md) and [E05–E08/E14–E15](../docs/architecture/system-contracts.md)
remain authoritative; implementation does not mean experiment or rig acceptance.

Current managed-wiring increment: V20 file-only pacing propagation includes canonical
startup profile adoption, nominal-60 handling of 60000/1001 timebases, and resolution
of file-only output identity before pulse-disabled profile validation. Sol reproduced
three initial defects; the worker repairs passed re-review with 43 focused tests.
Installed validation and startup resolve pacing before strict profile validation.
Sol then reproduced lost policy-aware dispatch in the actual controller wrapper:
Setup rereads TOML instead of using its held policy. The focused wrapper repair and policy-drift regression now pass through actual
application assembly. Independent permitted-loopback controller/lifecycle tests pass
34 cases (1.16 s). Sol accepted the wrapper with no actionable findings and 43
controller/Visual Stimulus configuration checks passing separately. Earlier raw-provider passes did not
establish exact policy retention. Managed projector configuration and
renderer-owned V01 calibration/cleanup are active. Additive contracts are generated.
Sol accepted the repaired native leaf and final controller/coordinator/worker wiring.
Calibration uses the V15 correction/material pipeline, exact output contexts and
retryable partial resource closure. Focused helpers preserve one display and source
owner. The pre-Setup catalogue retains exact resources locally until Setup accepts
session context; no fake session evidence is published. Actual authenticated tests
cover first-use/repeated calibration, uncertain-close recovery, active Shutdown,
owner loss, late preparation cleanup and Close while preparation remains blocked.
The latter waits for exact worker Close application before releasing preparation and
asserts no late presentation. Cancellation before dispatch clears only the local
reservation; uncertain dispatched ownership remains retained. Setup rechecks all
diagnostic ownership after asynchronous validation. Sol and Astra have no remaining
source findings; final combined checks pass and evidence is tracked in the
[current wiring assessment](runtime.md#current-scope-and-review).
Hardware GL and optical presentation remain rig checks.

[V04](../docs/architecture/visual_stimulus.md#v04) image fitting is implemented in
the source model, renderer shader and planning preview: centered Contain, Cover
and Stretch within authored bounds, before geometry/calibration. Source/prepared
schemas carry the fit choice; omitted legacy values retain Stretch. The shader
uses the existing mode/period inputs and source texture dimensions; no render
process, frame transport or scheduling change. Local rendering/compilation/contract
checks report 68 passes and 79 passing subtests, with schema consistency and scoped
static checks passing. GPU shader compilation and physical Windows output remain
unverified. GUI details are in the [current runtime report](runtime.md#dashboard-frontend-implementation).

The 2026-10-05 managed rig launcher reached the renderer after correcting consumed
bootstrap-handle closure and confirming the coordinator's existing supervisor launch
record before planning its worker. The renderer then missed an original
`ReportWorkerHeartbeat` peer deadline and triggered safety shutdown; its cleanup
reported an unknown command and an async admission conflict. The deadline was not
relaxed. The exact delay between worker heartbeat construction, coordinator receipt
and supervisor forwarding remains open in `visual-renderer-startup-deadline` (TODO).
The emergency error is retained under `reports/emergency-*.json`; no projection or
camera command was issued. The Visual Stimulus/supervisor behavioral run passed 242
cases with one previously known pacing-key loader failure. See the
[runtime report](runtime.md#dashboard-frontend-implementation) for startup details.

Historical recording attempts 22–28 repaired retained trial failure admission,
camera clock validation, gray raw input naming, cleanup result format, pre-Ready
encoder obligations, Schedule/Release ordering, GPU fence arguments, compositor
resource order and trial-parent forwarding. Their interrupted reservations and exact
exit evidence remain in the [dated bundle](rig-wiring-evidence-2026-10-08/dummy-experiment/).
Run43 completion/decode results above supersede the early incomplete-run assessment.
Oct9 restores source defaults; measured timing and full-workload acceptance remain open.
ARCH-002 keeps focused owners and existing behavior test modules.

## Calibration arena asset

[V18 revision 4](../docs/architecture/visual_stimulus.md#v18) permits a dedicated
offline exporter for a static calibration GLB. It reads the G01 version 2 saved
rig JSON and reuses the GUI's four screen-corner calculation. The resulting unlit
mesh has a 10 mm grid, a center cross and a Front/Left/Right/Bottom name on each
screen, plus a thin tank outline. The owner's 2026-10-04 Desktop JSON defines a
120 × 166 × 110 mm tank and four screen planes; the generated local asset is under
ignored `cephvr-data/calibration`. The earlier timed trial program was removed when
the owner selected manual open/close. The
Visual Stimulus GLB reader parsed the 55,688-byte asset (806 triangles). This is
source/format evidence, not a managed launch or optical check. The saved JSON has
unset near/far/tolerance and correction values. The GUI's Launch action prepares
calibration files automatically, computing bounded diagnostic projection limits and explicit uncalibrated
geometric meshes from the current four face assignments and native monitor identities;
it exports the V15 display profile with the GLB into Protocol Assets.
The managed GUI now sends typed untimed Launch/Close requests with captured revision
and asset fingerprints before Setup. Active requires renderer presentation evidence;
Close requires Idle and confirmed release, restoring the prior display or known
uninitialized state. Its local review entry point has no controller transport.
Optical/native verification remains in `projector-calibration-launch` in TODO.

Oct14 projector-calibration rework (owner-approved; local validation only) follows
[G01 revision 183](../docs/architecture/gui.md#g01) and
[V01 revision 19](../docs/architecture/visual_stimulus.md#v01). A source review found
affine-only scale/offset correction, a 25 % centre-bar measurement, widget-only state,
Qt-logical vs GLFW-physical output binding, an unrecoverable late-completing Open and
silent live-update failures. The owner chose independent edge margins. Implemented:
(1) the valid area is the output minus four independent pixel margins per face
(blank = automatic, centered from a complete measurement, else the projector border;
undershoot rejects with its remedy), with calibration file version 5/full 8 and
conversion of older scale/offset files; (2) the reference view adds an output frame,
100 px ticks and a screen-aspect guide outline beside the bars, and any face may be
dark (Use ticks) so one projector is positioned at a time, using the existing output
subsets; (3) a `seam_check` view draws bold eye-level, corner, meridian and floor
lines through the same live mesh; (4) displays bind by native interface, with the
Windows adapter name matching Qt screens; (5) a late-completing Open is closed without
touching the renderer and a repeated Close repeats confirmed evidence; (6) live
edits show working/applied/rejected status and invalid fields are outlined; diagnostic
files are written atomically; the measurement table no longer pins bar lengths before a
measurement or blanks the distance on partial input; (7) the renderer-side calibration owner builds
its evidence through one `_build_evidence`/`_mark` pair instead of ten hand-built updates.
Local evidence (macOS offscreen): 2089 passed/6 skipped across tests, Ruff/format, Win32
mypy (782 sources), 11 schemas without drift, boundaries (687 modules, no violations;
`worker/display_calibration.py` 590 lines and `gui/projectors.py` 904 lines keep their
single owners, with launch helpers extracted to `gui/projector_launch.py`) and whitespace
pass. Rendered reference view and calibration card were inspected as offscreen images.
Not done and still open: native Windows/GPU/optical alignment; the 59.94 Hz refresh rate
GLFW reports as an integer; the `projector-calibration-retention` cause (not
reproduced; a launch/adjust/close regression and old-file loading are tested); and
old content-addressed `reference_*.json` assets remain intact. The unused standalone
pruning command and its dedicated test were removed in the Oct21 repository cleanup;
this does not change calibration publication, imported-profile protection or the
unresolved retention investigation;
Keystone is now corrected (below); lens distortion and depth remain uncorrected.

Oct14 keystone warp (owner-approved; local validation only): each face's valid area is
now a convex quadrilateral. Signed Keystone H / V pixel fields narrow the top or bottom
edge and shorten the right or left edge of the margin rectangle, and the screen maps onto
the quadrilateral by the projective transform of its four corners, tessellated into a
17×17 grid shared by the GUI profile builder, the submit path and the renderer's live
update (`projective_mesh`; the same four-corner wire message, now any convex
quadrilateral). Piecewise-affine error against the exact map is 0.13/0.29/0.69/2.1 px for
5/10/20/40 % top-edge narrowing on a 2560 px output (measured locally). Calibration file
version 6/full 9 adds `keystone_h/keystone_v`; older files load with none. Tests (macOS
offscreen): 2099 passed/6 skipped, Ruff/format, Win32 mypy783, schemas, boundaries688. They
cover mesh corners/straightness/perspective spacing, convexity rejection, the renderer's
17×17 live write (no allocation, inversion/area rejections), sign conventions, profile
validity, version 5 loading, signed entries, live keystone payload and preview. Not
established: that real keystone is removed on the rig, or that the sign convention suits
the Bottom mirror fold (check optically; the convention is output-space top/right).
The four exported geometric profiles now carry per-face scale, pixel offsets and
axis inversion when entered; unset fields produce identity mappings. A focused test
checks adjustment, mirroring and rejection of corrections beyond the output.

## Arena movement gains

[V24 revision 7](../docs/architecture/visual_stimulus.md#v24) now supports independent
longitudinal/lateral gains, explicitly selected by the owner to match CephVR1.0.
The canonical planar mapping adds optional `sideways_gain`; omission/null retains
legacy shared-gain behavior. Both gains use existing unit/function validation and
application-time evaluation before the unchanged midpoint-heading transform and
boundary slide. Zero disables an axis; yaw retains its existing independent mapping.
Program/prepared-trial schemas and the pure reference were updated. No input stream,
tracking estimator, resource ownership or timing semantics changed.

Local GUI/feedback/compiler/contract validation passes 194 tests and 79 subtests;
two additional focused authoring/reference tests pass. Ten runtime mapping cases
exercise unequal/zero/reversed/fallback gains at two headings; contracts check units
and source round trips. Static/schema/boundary checks and native GUI evidence are
in [frontend evidence](runtime.md#dashboard-frontend-implementation). Native Windows,
managed binding and physical closed-loop acceptance remain pending under
[the rig worklist](rig-verification.md). These are local implementation results.

## Authoring labels

[V03 revision 9](../docs/architecture/visual_stimulus.md#v03) adds optional epoch
batch labels for [G01 targeting](../docs/architecture/gui.md#g01). The bounded field
is retained in source/prepared-source JSON; compiler expansion settings and durations
are unchanged. Program and prepared-trial schemas were regenerated from the canonical
model; all 11 schema drift checks pass. Current GUI/compiler/contract results and
native authoring evidence are recorded in [runtime frontend evidence](runtime.md#dashboard-frontend-implementation).
A broader configuration test reproduces the existing loader rejection of
`presentation.pacing_refresh_hz`, whose managed adoption remains listed in TODO.
No renderer, pacing implementation or physical acceptance changed in this increment.

The 2026-10-05 GUI advanced update follows [G01 revision 93](../docs/architecture/gui.md#g01)
and V07: new authoring instances default to reset false, while imported resets and
assignments remain explicit. Advanced settings now use one card; the opacity editor
is removed, and fixed-duration fades encode ordinary V05 opacity keyframes without
a new renderer mechanism. Imported custom curves remain preserved. + Control is
a separate dialog launched below Advanced settings (action hidden during its draft), restricted to closed-loop Texture/Looming
with the three Tracking channels; imported mappings and arena axis controls remain. Body-relative input mapping to 2D screens awaits the local-axis versus
rig/heading choice; no conversion is silently introduced. Explicit ranges still
await the clamp-versus-extrapolation answer, with no change to V24 gain/offset behavior. [V02 revision 12](../docs/architecture/visual_stimulus.md#v02)
records the confirmed clockwise Bottom direction (Right front→back, Left back→front)
and subject-to-screen lever arms. Linked movement still awaits source/target feedback
ownership; no motion-link schema,
compiler or rendering behavior is claimed. GUI document guards now reuse the existing
16 MiB engineering default; Setup limits and policy values are unchanged. Large
200-epoch multi-layer round-trips and cached trial switching are locally verified.
A separate planning preview now reuses canonical expansion/V07 state for enabled
screens from either side in a rotatable 3D rig view using Devices geometry, with cached per-face
compositions, on-demand assets and bounded approximate arena rendering. Unset
tank/plane geometry prompts configuration rather than guessing dimensions. It applies
the GUI screen scale/offset/inversion calibration using the same mapping as export,
with assigned-resolution pixel normalization. Blank corrections share export defaults;
invalid corrections report errors. It applies no live Tracking, arbitrary runtime
warp/photometric profiles or physical output; actual video codec
playback remains unverified locally. Variation captions match stimulus columns and
ordered values materialize independent epochs, including video end modes and arena
gains, without runtime schema changes. Authoring Random samples a bounded numeric
range at a positive precision step, using batch Repetitions for the count; mixed
fixed lists repeat in order with a fresh draw per resulting epoch. Cached choices
remain stable until range/precision/count changes.
Concrete epoch values are saved; no runtime random rule or Setup-seed change.
Final commit cleanup retains the owning GUI tests, removes temporary review harnesses
and duplicate results, and verifies 183 GUI/client-state/compiler checks. The existing
pacing-default loader rejection remains open; no Windows/physical-output acceptance
is claimed. Current GUI/compiler checks and limits
are in [frontend evidence](runtime.md#dashboard-frontend-implementation).

## Output participation

[V15 revision 10](../docs/architecture/visual_stimulus.md#v15) and
[G01 revision 65](../docs/architecture/gui.md#g01) align the GUI draft
corner conversion with front-attached side/Bottom screens. The operator plot adds
drag rotation and ideal centered-projector footprints from distance/throw and
assigned display aspect, including the Bottom 45° mirror fold beneath Right.
One Projection button/legend entry groups the optics, with distinct violet footprints.
The Bottom diagram uses a schematic pyramid from mirror center to footprint.
Valid central Bottom paths remain visible when outer-ray clearance is incomplete. Backend corner validation, off-axis math and output
corrections are unchanged. Local tests and native plot evidence are recorded in
[frontend evidence](runtime.md#dashboard-frontend-implementation); managed binding
and physical optical acceptance remain pending.

[V15 revision 6](../docs/architecture/visual_stimulus.md#v15) separates output
participation from the full fixed calibration. Optional `enabled` defaults true;
active-output/mapping properties drive preparation, native windows, renderer checks,
recording tiles/budgets and output evidence. Full profiles retain geometry/mappings.
Photodiode visibility/placement and pacing are independent under V20/V22.
Explicit `pacing_output_id` selects an enabled timing output; old pulse-enabled
profiles without it retain their photodiode target. `photodiode_enabled=false`
retains inactive/missing placement without target/bounds checks, suppresses the
patch and emits null marker fields. Enabled pulse placement remains validated.
Native swap order/intervals and review encoding use pacing, not pulse placement.
All 15 nonempty four-output subsets preserve projection matrices in local tests.
Those tests exposed a pre-existing frustum-distance sign opposite to the documented
`-dot(pa-pe, normal)` and model validator. Corrected the sign and removed an invalid
observer override from the earlier renderer test. Physical calibration and optical
accuracy remain unverified; see [rig checks](rig-verification.md).

Validation on 2026-10-03: combined GUI/client/Visual Stimulus suite passes 186 tests
(one optional dependency skip, one Windows deselection), authenticated transport
included with loopback permission. Contracts pass 40 tests and 79 subtests; 11 schemas
match, Ruff/format and Windows-target mypy (141 GUI/backend files) pass. Boundary
checker reports zero violations across 475 modules, with retained cohesion warnings.
[Native UI evidence](gui-dashboard-2026-10-01/README.md) is distinct from rig evidence.
GUI participation, timing and geometry drafts are not yet connected to managed
configuration transport. The rig editor produces canonical four-surface geometry
from entered centered screen/tank dimensions and subject offsets; tests validate
corner winding and projection matrices. Per-face projector distance/throw ratio,
scale/offset/reversal and imported calibration/mask paths remain local drafts;
applying authored corrections to adopted profiles is still integration work.

ARCH-002 review reuses immutable display records and filtered properties, without
new coordination/dependencies. Existing large native/engine/recording owners receive
only focused iteration changes; geometry and process/resource ownership stay intact.

## Implemented scope

Final Windows repair snapshot (2026-10-01, baseline HEAD
`826984255e0a8469afccbda2dcaf8c642b528b33` plus uncommitted repairs): 123 tests,
40 contract tests and 11 schemas pass. Concrete PyAV video stream/frame and TIFF
page/dtype/enum handling clears installed-extra Windows-target mypy; repository
check passes 525 source files. Bounded generated TIFF uint8/uint16 decoding preserves
exact pixel values and rejects float input; most other resource tests use fake
prepared decoders, so these results are not broad codec fidelity coverage. No physical projection,
calibration or full composite/encoder workload was performed. The installed PATH
FFmpeg4.3.2 failed bounded explicit-2080 Ti encoding; production encoding remains
unvalidated. [Dated evidence](rig-audit-2026-10-01/README.md) and the
[single rig worklist](rig-verification.md) retain current limitations.

[V01](../docs/architecture/visual_stimulus.md#v01) owns the Visual Stimulus name.
The runtime, tests, contracts, configuration and documentation use `visual_stimulus`;
console commands are `cephvr-visual-stimulus` and `cephvr-visual-stimulus-worker`.
Install the `visual_stimulus` dependency extra. Rebuild all clients against the renamed
Protobuf packages/services and update saved configuration to `visual_stimulus` and
`save_visual_stimulus_data` (`saveVisualStimulusData` in JSON). Field tags, decision IDs,
port 50054, output filenames and program/prepared format 2 are preserved. This changes
interface names, including recorded compatibility identifiers; it does not migrate
previous saved configurations or assert compatibility with older analysis consumers.

The runtime under `src/cephvr/visual_stimulus` includes canonical lightweight models/configuration,
strict program compilation, exact resolved timing and immutable transitions, protected
asset preparation and budgets, coordinator/worker services, lifecycle/resource tracking,
ModernGL/GLFW scene rendering, bounded video decoding and feedback consumption,
recording with analysis-ready recipe/evidence outputs. Offline replay/export is owned
by analysis software under V13 and is not implemented in this experiment package.
Controller-facing validation and writer schemas
remain graphics-free. Pydantic is a base dependency; native graphics/media libraries
are lazy imports supplied by the `visual_stimulus` extra. Entry points are `cephvr-visual-stimulus` and
`cephvr-visual-stimulus-worker`. The analysis request/report/export schemas remain shared contracts;
there is no experiment replay CLI, offscreen export adapter or recorded-state player.

Setup retains one canonical PreparedTrial and PreparedHandle per trial; controller
summaries derive from it. The coordinator publishes `_stimulus_LOG.json` at/after
confirmed release onset, including Save Off. The persistent renderer owns GL and live
state; the coordinator never relays pixels or per-frame commands. Recording uses bounded
capture ownership, required JSONL evidence and one fragmented-MP4 FFmpeg path. Recipe,
evidence and review video closure remain independent. Empty/all-dropped paths have
explicit predicates and do not insert frames or infer successful closure.

The rendering core supports four off-axis views, unlit GLB arenas, images/video,
procedural and image textures, ordered overlays, geometric mapping, photometric curves
and photodiode output. Linear-premultiplied composition preserves finite RGB excursions
until the named output clipping boundary. Bounded asynchronous GPU diagnostics retain
per-group/output coverage and compact Save Off counters; missing observations cannot
be interpreted as no clipping. Compatible instance state continues across epochs,
absent instances pause, and incompatible video asset changes select separately prepared
textures/decoder cursors. Arena reservation includes generated vertex attributes and
both material texture variants with all allocated mip levels. Feedback preserves ordered finite batches, generation/freshness
checks, holds, additive motion and constraint evidence. Tracking production/readiness is
not implemented or fabricated.

The retained recipe contains the authored snapshot, resolved timing/settings/seeds,
asset/dependency fingerprints, display/calibration references, renderer compatibility,
provenance and shader uniform layouts. Save On evidence retains exact consumed shader
words, effective poses, actual video selections/holds, output submission observations,
clipping coverage, recording omissions and completion state. Output-contract tests
check serialization and coverage without rendering/exporting offline. Save Off retains
the recipe but cannot guarantee actual-output reconstruction. Matching external assets
must be preserved separately. Analysis implementation and original-pixel equality
remain unverified.

## Local verification

The simplification audit on 2026-09-30 used the dirty working tree at HEAD
`7ae3767cea92bf7af94153d417e40df997e1fd05`; HEAD alone does not identify the tested
snapshot. Existing backend work and concurrent tracking changes were preserved.
[Raw evidence and source/test hashes](visual-stimulus-evidence-2026-09-30/simplification.txt)
record commands, baseline, increment checks and static results; the
[final integration output](visual-stimulus-evidence-2026-09-30/integration.txt) records
execution. These are E15 lightweight checks, not native, optical or performance acceptance.

- Baseline: **101 passed, 1 Windows-only test deselected**. The sandbox initially
  denied five authenticated loopback socket binds; those tests passed with local
  network permission, without changing their assertions.
- Recording increment: **112 passed, 1 deselected**. Final combined run: **663 passed,
  5 native-platform skips, 1 Windows-only test deselected**, including **121 stimulus
  passes** and acquisition/controller/supervisor/shared/launcher/client integration.
- Ruff lint/format: **134 files** clean. Windows-target mypy: **119 source files**
  clean. Boundary checker: **421 modules**, zero violations; its count includes
  concurrent work outside this backend. Cohesion exceptions are assessed below.
- Twenty added cases extend the existing recording/resources behavior modules:
  partial child launch and exact cleanup, retained deadlines/releases, pending
  capture/session ownership, loop/hold reset, stale decode/delivery, request
  coalescing, idempotent leases and mixed-size memory admission. Existing scenarios
  and E15 markers remain intact.

The earlier rename verification below is historical evidence, not a rerun during this
audit. It preserved all **639** scenarios collected before/after the rename; a
concurrent supervisor case was present in its execution run. The historical acquisition
failures have since been resolved and verified in the [acquisition report](acquisition.md)
and are included in the current integration run.

| Check | Result and scope |
| --- | --- |
| `python -m pytest -q tests` after the rename | **616 passed, 7 skipped, 17 failed**. The exact failing test names match the existing acquisition baseline. |
| Visual Stimulus tests in that run | **101 passed, 1 Windows-only skip**. |
| Controller/supervisor tests in that run | **294 passed**, including concurrent supervisor work. |
| `python -m pytest -q contracts/visual_stimulus/tests` and configuration checks | **43 passed, 79 subtests passed** (40 contract cases plus 3 configuration cases). |
| Tracking contract unittest discovery | **48 passed**. |
| `python contracts/visual_stimulus/generate_schemas.py --check` | **11 schemas**, no drift. |
| `python tools/generate_contracts.py` | **19 Protobuf sources** compiled; field tags and enum numbers compared against the pre-rename snapshot and retained. |
| Ruff check and format check over `src tests tools` | Passed; **553 files** formatted. |
| `python -m mypy --platform win32 src` | Passed across **460 source files**. |
| `python tools/check_backend_boundaries.py` | **390 backend modules**, zero dependency violations; reviewed size warnings below. |
| `python -m compileall -q src tests`, `git diff --check` | Passed. |
| TOML parsing, root register and Markdown path checks | Backend config/policy versions match; **112** decision revisions match; all renamed documentation paths resolve. |
| Packaging | Wheel and source distribution built. Extracted-wheel imports/descriptors/writer schemas pass without graphics/media initialization; only renamed backend packages, commands and dependency extra are shipped. |

Authenticated loopback checks exercise real controller, acquisition coordinator,
supervisor outbound/registry and Visual Stimulus service/runtime components. Coverage includes
configuration/display-status separation, resolved artifact handoff, lifecycle ordering,
retained duplicate/conflicting commands, stale generations, original deadlines,
worker errors, interruption and cleanup. The supervisor test uses the actual persistent
pre-session renderer launch shape and reconciles exact retained executor completion;
admission is not treated as cleanup success.

## ARCH-002 implementation review

Oct19 `code-sweep-oct19` removes the unused engine-access wrapper and unused scalar
sRGB decoder. Texture patterns reuse the identical existing `_mix`, `_smoothstep` and `_num`
functions from the geometry module they already import. This adds no dependency or
owner, and preserves V04 pixel formulas and resource lifetimes. The owning resources,
rendering and lifecycle selection passes 184 tests, including existing reference
raster hashes; native rendering/rig acceptance remains separate.
[Raw checks](runtime-evidence-2026-10-19/code-sweep/visual-after.txt);
the final numeric-helper consolidation also passes all 16 texture/recipe cases.
[AST equivalence](runtime-evidence-2026-10-19/code-sweep/equivalence.txt) confirms
the three retained function bodies match their removed duplicates.

Owner-approved Oct19 correction: polar geometry now clamps finite RGB channels
to 0–1 before multiplying by 255, matching ordinary patterns under
[V04](../docs/architecture/visual_stimulus.md#v04), revision 16. The parser continues
to accept finite out-of-range channels. The original parsed 8x8 polar recipe with
`color_a=[1e308,0,0]` raised `OverflowError`; it now generates successfully. The owning
reference-pixel test additionally compares positive/negative extreme channels and
an in-range midpoint against clamped inputs for both colors of ordinary and polar
gratings. Its original reference hash still passes. Rendering and resource tests:
133 passed. Scoped Ruff/format, Win32 mypy, boundaries and whitespace pass; this
does not establish native rendering or rig equivalence.
[Original probe](runtime-evidence-2026-10-19/code-sweep/probes.txt),
[regression failure](runtime-evidence-2026-10-19/code-sweep/approved-clamping-red.txt),
[passing tests](runtime-evidence-2026-10-19/code-sweep/approved-visual-green.txt),
[commands and provenance](runtime-evidence-2026-10-19/code-sweep/approved-context.json).

The Oct13 texture increment separates recipe parsing, formula rasterization, geometry,
protected dependencies and preparation admission. Linked-motion validation, compiler
pivot preflight and renderer binding are focused helpers over existing state fields.
No whole-runtime references, alternate renderer or per-frame recipe generation are
introduced. The 635-line pattern module remains one cohesive legacy formula catalogue;
its size warning was reviewed rather than split into generic dispatch scaffolding.
Tests extend existing compilation, rendering, resources and dashboard behavior owners.
Pillow is pinned for the legacy blur/image conversion semantics; GUI recipe inspection
keeps numerical/image dependencies lazy.

The 2026-10-07 V01 review keeps GL-thread output/Idle restoration in the native port
and engine, and one protected-source promotion/release registry in NativePreparation.
Calibration drawing and asset preparation now have focused helpers. Sol accepts these
cohesive state owners; their size warnings do not justify duplicating closure state.
The dedicated calibration behavior module uses distinct fake-GL context, protected-file,
restoration and partial-release fixtures. Hardware GL remains unexecuted locally.

Each increment used focused state and operations. Shared command admission and compatible
FFmpeg argument/capability/I/O mechanisms are reused; acquisition policy remains separate
from Visual Stimulus's lossy, fixed-composite, fragmented-MP4 requirements. Resource preparation,
trial admission/execution, feedback, scene allocation, arena drawing, GPU diagnostics,
capture and encoder ownership have separate cohesive modules. The V13 ownership
revision removed replay resource readers, offscreen GL, export orchestration and live
renderer branches for recorded-state playback. Small test-only evidence readers check
experiment output coverage; they are not shipped as an analysis product. No feature
module retains a reference to an entire backend runtime.

The simplification audit removed three write-only recording fields and an unused
encoding property, inlined a one-call output wrapper, and consolidated resource-release
classification while retaining each resource's own closure predicate (V12/E13, E06/E08).
The recording facade fell from 781 to 751 lines; native child/file ownership remains in
`EncoderTrialOwner`, not in a second bookkeeping owner. The canonical typed evidence
and output-result paths still retain failures and exact process/file identity.

Timestamp selection and its generation identity now live in the focused
`resources/video_selection.py` module (V09/V10). The decoder scheduler shares one
content-match operation at decode completion and delivery, and reuses its fixed worker
assignment for scheduling/closure (V11). Its file fell from 598 to 512 lines without
changing locks, decoder-thread ownership, clock progression or coalescing semantics.
The pure cursor algorithm itself is unchanged. A redundant texture-upload cast was
also removed; no graphics behavior changed.

The audit reproduced and corrected a pre-existing V11 admission error: multiplying the
latest frame size by the instance count admitted 40 bytes of mixed-size frames against
a 32-byte limit, and could reject valid mixtures in the opposite order. Admission now
sums the prepared frame sizes using one size calculation and checks both decoded and
working-memory limits before registering the instance. This intentionally corrects
admission behavior to the existing limits; it is not a new policy or a throughput claim.
No package was added: the existing standard-library, media and native dependencies
cover these mechanisms. No RPC/schema/configuration or architecture decision changed.

The 2026-10-01 cross-backend ARCH-002 sweep removed the write-only
`NativeRecording.video_sync_factory` attribute: the constructor still passes the
factory directly to `EncoderTrialOwner`, its sole runtime owner. The recording path,
process/resource identities and closure evidence are unchanged (V12/E13, E06/E08).
Visual Stimulus and Tracking `authenticate()` bodies use the same lookup and identity
check shape and both delegate credential proof to shared `require_authenticated_peer`.
A wider RPC boundary helper would blur their distinct command/worker admission and
deadline policies. No other
extraction or naming change was justified. Exact source provenance and local checks
are recorded in the [2026-10-01 evidence](visual-stimulus-evidence-2026-10-01/simplification.txt).

The boundary check's size warnings are reviewed cohesion exceptions: the canonical
program model owns the discriminated schema; recording/native owns the recording facade
with capture, encoder, outcomes and session work extracted; rendering/scene owns live
draw orchestration with allocations/shaders/arena draw/capture extracted;
rendering/native owns context/output lifetime and submission; rendering/engine owns
trial state and schedule orchestration; resources/video owns bounded playback scheduling
and lease delivery with selection/decoder/index/session bindings extracted; worker/lifecycle owns command routing and
progress with preparation, trial, timing and cleanup operations extracted. Existing
non-Visual Stimulus size warnings remain recorded in their owning reports. No complexity reduction
or source-level check is presented as a measured throughput improvement.

## Windows handoff and remaining acceptance

Run the [stimulus handoff procedure](rig-verification.md#stimulus-implementation-handoff--execution-procedure)
with explicit rig inputs and `tools/test_on_rig.ps1 -Install`. The runner installs Visual Stimulus
dependencies, performs automated checks and preserves logs. Windows-native launch,
process authority/worker loss, named pipes, protected files, partial allocation/cancel,
GPU identity/framebuffer precision, shader execution, display/projection/color/photodiode,
pacing, decoder/media fidelity, encoding throughput/storage/crash/empty-input behavior,
analysis-input evidence fidelity and combined workload remain pending rig procedures.
Offline export acceptance belongs to the analysis software and needs its own implementation. No GPU or Windows
native behavior has been exercised on this machine. Firmware, GUI authoring, tracking
implementation and calibration measurement remain outside this stage.

## Verification evidence — 2026-09-24

The following records the original declaration snapshot; no exact source revision
or full command transcript was recorded, and these checks were not rerun during
report consolidation. Counts and implementation limits describe that snapshot.

The ten [pure regression tests](../contracts/visual_stimulus/tests/test_simplification.py) passed:
version/complete-setting rejection, parameter/coefficient and coordinate-dependent units,
feedback gain/rate compatibility, consistent opaque output IDs, bounded strict JSON,
single-plan structure, exact evidence byte preservation and envelope checksums/bounds.
The [drift/hold source](../contracts/visual_stimulus/examples/drift-hold.json) validated as format 2.
The [generator](../contracts/visual_stimulus/generate_schemas.py) reproduced all 13 published schemas
without drift. Python implementations and interface declarations parsed successfully.

The complete 15-file Protobuf set compiled. The obsolete parallel schedule messages
and field were deliberately removed; the former control field's number/name are reserved.
All unrelated existing wire field names/numbers/types, enum values and reservations
remain intact. Program/PreparedTrial format 1 is intentionally rejected; rebuild clients
against the new declarations and use format 2. WatchState remains the only streaming RPC.
All 61 root-register revisions matched their owners; changed-document relative links resolved.

At that snapshot, the implemented Python changes were pure schemas/parsing/unit checks and evidence
payload/framing helpers. Compiler/native-transport/renderer/recorder/recovery interfaces
remained declarations. No Windows cleanup, GPU rendering, video encoding, recovery/export
runtime or rig behavior was tested. The existing encoder input-format, timestamp precision
and final-frame-duration feasibility deferrals remain. No runtime output-file validator,
new overload policy, original-pixel equality claim or measured speedup is introduced.

## Validation limits

Oct13 `long-protocol-resource-scaling` implements owner-authorized bounded residency
and advance loading for ordinary still images and image-producing CephVR1 recipes
under [V04 revision14](../docs/architecture/visual_stimulus.md#v04), while retaining
[E07](../docs/architecture/experiment.md#e07) whole-session validation and protected
sources. One CPU loader produces a bounded handoff; the GL owner uploads in bounded
chunks, polls completion without waiting, and evicts only unpinned completed resources.
Compatible image content/interpretation shares residency across trials. Setup retains
source descriptors and schedule metadata, validates every image sequentially, and
pins each instance's first-use image. Indexed next-use lookahead avoids scanning the
remaining protocol at every epoch; a 100,000-epoch regression covers this boundary.

If an image misses its scheduled onset, the previous texture remains selected while
current motion and original clocks continue. Save On evidence version4 records requested
and actual asset IDs/zero-based indices, readiness holds and repeated image identity;
version3 input remains accepted. Repetition means the preceding selection/render attempt,
not identical moving pixels or optical proof. Submission outcomes remain separate.
Save Off retains E13's absence of per-frame output and emits a bounded miss summary.
Reload/decode errors remain failures; readiness misses alone use the accepted hold.

ARCH-002 separates source interpretation, scheduling, CPU handoff, GL uploads and
residency from existing lifecycle owners, without new dependencies or processes.
The existing large preparation/session, renderer and recorder modules remain cohesive
orchestrators; new responsibilities are focused modules with explicit interfaces and
no runtime back-references. Worker joins protect source lifetime, and unresolved GPU
completion/release retains resources, reservations and cleanup obligations for retry.

This bounds decoded-image residency, not all protocol memory. Protected handles,
descriptors, schedule metadata, per-trial scene targets and eager video/arena/calibration
resources still consume existing budgets. The union of first-use anchors plus held/next
working sets must fit; Setup rejects insufficient capacity. Chunking does not bound a
native driver's allocation latency. Real storage/decode contention, native fence behavior,
peak RAM/VRAM, onset timing and simultaneous recording require the owner-deferred
[rig checks](rig-verification.md). Final local validation passes 296 owner tests (one platform/rig case deselected),
42 contract tests/79 subtests, 11 schemas, scoped Ruff/format (166 files), Win32 mypy
(150 sources) and boundaries (686 modules, zero violations). Luna writing, Sol6.1
integration and Astra main review are complete. Intermediate fixture/reservation
expectation failures and loopback restrictions remain identified separately.
Validation and review provenance are retained
in [image residency evidence](runtime-evidence-2026-10-13/image-residency/context.json).

The current checks exercise application behavior and authenticated transport on this
host. They do not establish native runtime or rig equivalence. Keep pending native/rendering/encoding, optical,
calibration, failure/durability and simultaneous-load checks in
[rig verification](rig-verification.md). No historical declaration pass closes them.

The 2026-10-03 GUI refinement moves pacing identity and the 60 Hz target to the Visual
Stimulus TOML under [V20](../docs/architecture/visual_stimulus.md#v20). TOML syntax is
checked; managed adoption/native refresh validation remains pending. No physical
refresh or render-rate guarantee is established by this configuration declaration.

The GUI geometry builder now positions parallel screen planes by explicit positive
perpendicular subject-to-screen distances under [V15](../docs/architecture/visual_stimulus.md#v15),
independently of tank walls. The GUI now derives the right-screen distance from
the left using equal tank-wall offsets, as explicitly confirmed by the owner;
o independent right distance remains in GUI calibration JSON v2. It shares corner generation with the schematic; backend
corner schema/rendering is unchanged. Physical placement and managed profile adoption
remain unverified. Local geometry tests cover independent planes and invalid distances.
## Startup GPU placement and closure

Oct13 actual launches record AMD Radeon OpenGL contexts rejected against the
required RTX 5060 Ti under [SYS-002](../architecture.md#sys-002). Evidence includes
[09:35 emergency](emergency-328494867654500-500f6310-e26f-453c-be55-81996dc33dd2.json)
and [screenshot-associated emergency](emergency-328763941422600-cc8b402d-c96c-42d3-82f2-d2c3ee11b8f0.json).
A task-owned identical executable with no Windows GPU preference reproduces AMD
on all four configured projectors. The existing configured managed executable
(`GpuPreference=2`) uses the RTX 5060 Ti in direct probes and two fresh managed
launches. Relocating GLFW's bootstrap does not correct the default selection; that
probe workaround is not adopted. The original failing launch route remains unknown.
No production Windows preference or driver was changed.

Under [V19 revision 6](../docs/architecture/visual_stimulus.md#v19), the startup
closure defect is repaired: narrowly classify a healthy wrong-adapter context as
unavailable output placement, reuse exact sessionless cleanup/rejection delivery,
and expose the managed executable's Windows Graphics remedy. No wrong-GPU rendering,
Idle/Ready claim, fallback or retry is allowed. CUDA driver/API failures, actual GPU
operation failures, cancellation, lateness and uncertain cleanup retain E06/E08
escalation. ARCH-002 adds only focused error classification/remedy to existing
owners; no new process, dependency or lifecycle state. The existing native renderer
cohesion advisory remains; window/context ownership stays together.

Final affected checks: 249 Visual Stimulus/platform tests pass (including authenticated
controller wrong-adapter rejection and fault/deadline/cleanup gates), Ruff/format
154 files, Win32 mypy 137 sources and boundaries 665 modules/zero violations pass.
Three actual isolated AMD contexts are rejected with exact native window/context/GLFW
release. Final managed GUI launch confirms all four outputs initialized, revision 1,
Configuration phase and no warnings/errors; it remains open for the owner. This
launch passed the existing exact RTX 5060 Ti verification. No camera, recording,
optical, electrical or full-load acceptance is implied. Raw methods/results and
source hashes: [GPU evidence](runtime-evidence-2026-10-13/gpu-selection/context.json).
