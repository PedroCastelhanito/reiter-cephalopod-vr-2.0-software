# Visual Stimulus status

Oct9 authorized baseline repair restores the 500 ms preparation lead and unsets the
diagnostic pacing-output identity; camera drain margins are also unset. All 36 owning
configuration cases pass. Visual Stimulus contract discovery passes 42 tests and all
11 generated schemas match. [Current integration evidence](review-evidence-2026-10-09/implementation-context.json)
records full local validation; native presentation/encoding throughput, scientific
timing and owner-deferred encoder acceptance remain in the [rig checklist](rig-verification.md).

Measured-reference implementation (2026-10-08, `physical-reference-calibration`)
follows [G01](../docs/architecture/gui.md#g01),
[V01/V15](../docs/architecture/visual_stimulus.md#v15) and
[V24](../docs/architecture/visual_stimulus.md#v24). Untimed calibration draws orange
horizontal and green vertical native-pixel bars after geometric/color correction.
Their measured mm spans derive X/Y scale and full image dimensions; the GUI derives
ideal read-only throw distance from width × effective throw ratio. Physical screen
dimensions and subject-to-screen distances remain independent. Portable full JSON 4
and numeric 3 retain measurements/native dimensions; legacy files load with unset
measurements. Output-mode mismatch invalidates scale without changing provenance.
Export/submission applies physical screen/full-image ratios with existing offsets/
inversions, creating new content-addressed 2×2 GUI affine assets. Original assets and
imported nonlinear/masked/weighted calibration are preserved; automatic replacement
of those imported corrections rejects explicitly. Planning preview shares the mapping.

ARCH-002 extracts focused bar/measurement/profile helpers; the 806-line projector
panel remains orchestration with existing draft ownership, while new numeric/file
responsibilities live outside it. No new dependency, process or persistent GPU resource.
Affected tests pass 658 plus the post-review checks described in the
[Tracking assessment](tracking.md); two concurrent temporary-pacing assertions remain
excluded and raw failures retained. Lint/format, Win32 mypy, schema drift and boundary
checks pass. [Offscreen card preview](tracking-evidence-2026-10-08/physical-reference-gui.png)
is visually inspected; [methods/source context](tracking-evidence-2026-10-08/physical-reference-context.json)
records limits. Local affine scale/ideal throw estimates require optical rig acceptance,
including current zoom/keystone/fold and depth/distortion. No projector or hardware
session is launched by this task. [Remaining acceptance](rig-verification.md).

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
See the local [E13](../docs/architecture/visual_stimulus.md#e13) padding implementation below and the
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

Owner-selected video timing rules now follow
[E13 revision 20](../docs/architecture/visual_stimulus.md#e13),
[V12 revision 11](../docs/architecture/visual_stimulus.md#v12) and
[V28 revision 5](../docs/architecture/visual_stimulus.md#v28): first usable image per
evaluation-time slot, explicit leading first-image backfill, later repeated-image
padding and separate real-source/encoded-frame evidence. The recording thread retains
one normalized image, preserves admitted source order, installs cutoff before draining,
and services evidence/sync during streamed padding. Resource preflight includes the
retained image, transient readback copy and row scratch. Evidence Header/registry 3
and fixed policy 8 bind the mapping; PreparedTrial/recipe remains format 2.
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
