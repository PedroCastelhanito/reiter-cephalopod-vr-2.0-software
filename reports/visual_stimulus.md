# Visual Stimulus status

Updated: 2026-10-01. The complete Visual Stimulus implementation is selected under
[ARCH-001](../architecture.md#arch-001). This report describes the uncommitted working
tree, preserving the existing controller, supervisor and acquisition work.
[V01–V28/E13](../docs/architecture/visual_stimulus.md) and [E05–E08/E14–E15](../docs/architecture/system-contracts.md)
remain authoritative; implementation does not mean experiment or rig acceptance.

## Implemented scope

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

The current checks exercise application behavior and authenticated transport on this
host. They do not establish native runtime or rig equivalence. Keep pending native/rendering/encoding, optical,
calibration, failure/durability and simultaneous-load checks in
[rig verification](rig-verification.md). No historical declaration pass closes them.
