# Linked Grating preview investigation

Date: 2026-10-28 (client Asia/Tokyo). Base revision:
`e4dd8f2694aa075380fe6711a884fe5894763c6f`; shared working tree already dirty.
No runtime source changes in this investigation. Added eight regression cases in
`tests/gui/test_stimulus_authoring.py` under the existing owner, following ARCH-002.

Inputs read in place, not modified:

- `C:/Users/ReiterU_PC/Desktop/Alsu/protocols/gratings_protocol.json`, SHA256
  `DED683D9A07CC298C027E06DCA009835BD7FD8417479DDC1D255E7A1C54A129D`.
- `C:/Users/ReiterU_PC/Desktop/Pedro/configs/projectors_config.json`, SHA256
  `0E6EBEDA03C61A398E25B33D016A65EC9A63287706FAB3704D2A1E3EDB1B8ED4`.

Probe: retained `.tmp-linked-grating-probe.py` imports the actual PreviewPlan and
PreviewCanvas. Run with repository Python and `QT_QPA_PLATFORM=offscreen` from the
repository root (its PNG output names are relative to that directory).
The final run uses the supplied protocol and geometry, assuming the calibration's
saved reference resolutions: Bottom720x1280, others1280x720. Current assigned display
resolutions are not independently established. Its unused initial example program
is superseded by the explicit input file load. Earlier probe attempts rejected
non-hold preset follower motion before applying the actual GUI link semantics.

Final probe samples (local angles, before output correction):

| Face | Rotation at0 | Phase at0 | Phase at25ms |
| --- | ---: | ---: | ---: |
| Front | 45 | 16.334167 | 16.234167 |
| Left | 135 | 14.637110 | 14.537110 |
| Right | -45 | -14.637110 | -14.737110 |
| Bottom | -225 (=135) | 0 | 0 |

All frequencies0.2cycles/mm. Bottom translation at25ms is
(-0.353553,+0.353553)mm; followers use phase transport rather than independent
translation. This is the first sampled rig direction135 degrees. No same-local-
direction failure is reproduced. Retained PNGs at0/25ms are from the final supplied
inputs;1s PNGs are historical example-geometry samples and are not rig evidence.

Validation:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv/Scripts/python.exe -m pytest tests/gui/test_stimulus_authoring.py -q -k 'linked_grating_preview or trial_preview' -m 'not windows and not rig' --basetemp=.tmp-linked-grating-pytest
.venv/Scripts/python.exe -m pytest tests/visual_stimulus/test_rendering.py -q -k 'linked_gratings or shared_grating' -m 'not windows and not rig'
.venv/Scripts/python.exe -m ruff check tests/gui/test_stimulus_authoring.py
.venv/Scripts/python.exe -m ruff format --check tests/gui/test_stimulus_authoring.py
.venv/Scripts/python.exe tools/check_backend_boundaries.py
```

Outcomes:10 authoring/preview passes;14 rendering passes; Ruff and formatting pass;
792 modules/zero boundary violations with pre-existing size advisories. Initial
selected preview run had9 passes and one TEMP fixture permission error; the explicit
writable basetemp rerun passes. Initial new-test formatting was corrected.

Native read-only CIM lists launcher processes from9:35 and10:41. Computer Use window
inventory returned Explorer, VS Code, TeraCopy and Codex, with no CephVR dashboard
or Trial preview. A subsequent inventory found the dashboard; activation exposed
a Save Protocol dialog over a different Image protocol. No editing, saving or
preview action followed. Running code location is not proven
by launcher command lines. Initial sandbox CIM access failed and psutil was absent;
no dependency was installed. Source review, offscreen calculations and raster
collection are not live GUI, device, physical direction or optical acceptance.

## Native opening on owner request

The owner explicitly requested that the agent open the preview. Initial window
inventory showed calibration outputs without a dashboard. Separate read-only
`open_saved_preview.py` launches (Hidden, then Normal, then with a startup traceback)
created processes but no targetable preview window; stderr remained empty and the
traceback timer was canceled after show. Only exact helper-command processes were
terminated. The cause of non-targetability was not established. Ruff skips this
evidence path under repository exclusions; no runtime source was edited.

The dashboard subsequently became targetable. Through Computer Use:

1. Dismissed the completed resource-budget Setup error summary with Continue.
2. Used Protocol Save As to preserve the current9000-epoch Image protocol as
   `before-native-preview.protocol.json` in this evidence directory (38608bytes).
3. Loaded the owner's `gratings_protocol.json` through Protocol Load.
4. Clicked Preview, then Play. Native Trial preview shows1/100, Epoch1, with
   Front/Left/Right/Bottom patterns and visibly different per-surface orientations.

The native dialog is left open and playing; Gratings is now the selected editor
protocol. Original external protocols/calibration are unchanged. No Setup, Start,
device control or configuration Apply was invoked. Screenshot observations alone
do not establish actual motion direction. Owner confirmation was requested; the
original defect remains unproven and no runtime repair is claimed.

## Subsequent observed defect and repair

The statement above describes the initial investigation. At51seconds native
playback visibly enlarged Bottom's bars while follower widths remained stable.
The source's translated preview quad grows to cover its displacement but its
pattern is still sampled in512columns, causing aliasing. Eight new50-second raster
invariance cases failed before the repair. Canvas drawing now converts translation
to centered phase before covering/sampling. It copies preview values and leaves
retained state unchanged. The exact formula is phase minus frequency times the
position projected on the bar normal, reduced modulo one cycle.

All-four-face checks then exposed a separate numerical defect: subtracting the
translated scalar origin to compute unit-point gradients made follower frequency
and angle depend on translation roundoff, enough to change rounded raster coverage.
The existing field helper now computes the spatial gradient without translation
and applies translation to phase only. This is algebraically the same V02 field.

Final tests cover eight45-degree directions, source/follower normals and phase,
quarter-cycle pixel changes, all four faces after200 periods/50seconds and backward
seek. Sine raster comparison permits one8-bit level of quantization. Existing
rendering edge-phase cases extend to50seconds and assert exact gradient invariance.
The longer test initially tried a2.5-second transition after sampling50seconds;
four fixture failures were corrected by using a boundary after the sample. Initial
all-face checks also caught loop-variable lint, corrected by explicit parameters.

Final commands:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv/Scripts/python.exe -m pytest tests/gui/test_stimulus_authoring.py tests/visual_stimulus/test_rendering.py tests/visual_stimulus/test_compilation.py -q -k 'linked_grating_preview or trial_preview or linked_gratings or shared_grating or linked_translation or linked_rotation or linked_spin' -m 'not windows and not rig' --basetemp=.tmp-linked-grating-final-3 --tb=short
.venv/Scripts/python.exe -m ruff check src/cephvr/gui/trial_preview_canvas.py src/cephvr/visual_stimulus/config/grating_field.py tests/gui/test_stimulus_authoring.py tests/visual_stimulus/test_rendering.py
.venv/Scripts/python.exe -m ruff format --check src/cephvr/gui/trial_preview_canvas.py src/cephvr/visual_stimulus/config/grating_field.py tests/gui/test_stimulus_authoring.py tests/visual_stimulus/test_rendering.py
.venv/Scripts/python.exe -m mypy --platform win32 src/cephvr/gui/trial_preview_canvas.py src/cephvr/visual_stimulus/config/grating_field.py
```

Results:32 passed/267 deselected; Ruff, format, two-source Win32 mypy pass. Boundary
check after the source repair reports792modules/zero violations, existing size
advisories; neither modified runtime owner exceeds500lines. Whitespace passes.
No architecture rule was changed; this implements existing V02/G01. No dependency,
schema, device-control, deadline or ownership changes.

Owner confirmed the old running preview still looks wrong. A fresh independent
helper was launched with an unparented window after repair (launcher PID14468);
Computer Use's next call was stopped by physical Escape, so no further UI input
or inspection was attempted. The helper may remain running. Dashboard was not
restarted; corrected native playback and physical/optical motion remain unverified.

## Owner reports continuing preview and rig mismatch

The next owner screenshot (`owner-preview-mismatch.png`) shows a2s tank preview;
owner also explicitly reports that the physical rig looks the same. This is owner
observation, not an agent-measured optical acceptance result. The earlier sampling
repair addressed a separate observed defect and does not establish resolution of
the reported coherence problem.

`check_final_field.py` draws actual PreviewCanvas frames through PreviewRig's final
face mapping, then compares sampled display levels against the current unfolded
physical field. Uses supplied files/reference resolutions, a20mm sine period for
sampling diagnostics, no input-file edits. With calibrated extents, mean/max encoded
level errors are Front0.0115/0.0598, Left0.0129/0.0768, Right0.0158/0.0892,
Bottom0.0116/0.0637 (nearest-pixel/raster approximation included). Earlier comparison
against nominal physical rather than measured extents gave larger errors up to
Bottom0.0601/0.3115. This is diagnostic agreement with the existing rule, not a
pass for optical calibration or the owner's intended definition of coherence.
Output `final-*.png` files are diagnostic face rasters, not rig captures.

V02 explicitly unfolds each wall independently about its Bottom intersection and
permits wall/wall corner seams. For the owner's Bottom-left example, Left moves up
while Front moves left: their straight grating phase derivatives along a shared
vertical corner are respectively nonzero and zero. A continuously joined phase
cannot have both. A globally seamless interpretation therefore conflicts with
unchanged constant orientation/spacing and that cardinal mapping. Asked the owner
whether continuous joins with bending/spacing variation are required, or the
straight constant-spacing/Bottom-motion rule governs. No proposed new field or
unanswered choice is implemented or recorded as Accepted. Runtime source unchanged
in this investigation increment. Computer Use was not resumed.

## Final straight-bar revision and validation

The owner first accepted continuous wall joins with bending/spacing variation.
A temporary shared cubic phase correction was implemented, preflighted and tested:
415 owner cases/5 subtests and6 native GL waveform cases passed. The owner then
explicitly revised that choice: straight bars, phase matching at corners, without
requiring complete geometric connection. That instruction supersedes the bending
implementation. Removed its helper module, shader/evidence uniforms, curved image
sampling and upright-wall restriction; no runtime curvature code remains.
`continuous-preview.png` is superseded offscreen evidence, not the final behavior.

Current V02rev21/G01rev383 define Bottom-level corner points as the spatial anchors
in the existing affine unfold, with one temporal phase/motion clock and straight
uniform-spacing bars per surface. They do not require matching stripes at every
height of a vertical wall edge. Eight orientations and Bottom/Front references now
check the three incident phases at the two Bottom/front/side corner points at0,
0.7s and50s, including actual scaled shader inputs. Long-raster invariance and
backward seek remain covered. PreviewRig now uses measured usable corners rather
than stretching calibrated pixels onto nominal frame dimensions. A dedicated
measured-pitch case and existing margin/flip cases pass.

Fixed declaration `programs.linked_grating_field` is
`bottom_corner_anchored_affine_phase_v1`. This work revised the policy to24; a
concurrent owner-authorized PNG change subsequently advanced the shared tree to25.
Retained that change. Current two TOMLs and loader version25/digest
`d2420960f28a8935db32cd7ca8650dadb20431681d1737f24e99bde9ac391fa8` agree, confirmed by
the owning loader and final tests. Full restart/fresh Setup is required.

Final broad command (QT_QPA_PLATFORM=offscreen):

```powershell
.venv/Scripts/python.exe -m pytest tests/visual_stimulus/test_configuration.py tests/visual_stimulus/test_compilation.py tests/visual_stimulus/test_resources.py tests/visual_stimulus/test_rendering.py tests/gui/test_stimulus_authoring.py -q -m 'not windows and not rig' --basetemp=C:/Users/ReiterU_PC/.codex/visualizations/2026/10/28/01a18022-52f8-7702-ace7-a1a3875bcdd7/straight-grating-consistent-final --tb=short
```

Result423 passed/47 deselected/5 subtests. A preceding broad attempt coincided with
the concurrent policy/hash update:409 passed,14 failed and2 modal teardown errors
reported fixed-policy-content mismatch. Current loader verifies the complete25
content; the stable rerun passes. No assertions were relaxed.

Additional checks (overlapping scopes):67 focused Grating/preview cases including
native GL waveform cases pass;30 selected authoring/Dashboard preview cases pass.
Evidence/lifecycle checks required native hard-link/loopback permissions:93 pass,
one Windows case excluded. The sandbox first denied os.link at evidence test13;
an earlier combined run also stalled without a summary and was interrupted. Native
permission rerun passes without assertion changes. The first broad fixture run
used repository basetemp and three demo-asset setup cases rejected the destination;
using the authorized writable visualization root outside the repo resolves this.

Scoped Ruff/format and six-source Win32 mypy pass. Boundary and whitespace checks
pass. No dependency, process ownership, deadline, generated contract or external
protocol/image edit belongs to this change. ARCH-002 kept existing focused owners;
uniform metadata scans reuse the existing traversal. Current `straight-preview.png`
was rendered from actual TrialPreview/PreviewRig with the saved inputs, packaged
font and --snapshot under offscreen Qt. It is not native optical/rig acceptance.
No Computer Use or managed-device action was resumed after Escape.

## Side orientation clarification

### Drift-link behavior previews - review pending

Owner requests Grating linking like Texture drift, with previews before implementation.
drift_link_preview.py calls production config.texture_links.linked_rates directly,
with saved geometry and unit reference translation along each Bottom grating normal.
ImageTile models adapt to that existing API only (unit periods,zero angular rate/
target rotation). Candidate bar normal follows mapped velocity; frequency compensates
mapped speed magnitude, retaining source physical period and shared temporal phase.
Existing Texture drift keeps its own appearance/phase; the proposed reuse is its
physical motion transport for Grating normals. No custom Right-only flip added.

Rendered all eight orientations in cardinal/diagonal pages, actual tank preview plus
aspect-preserved flat views/local arrows. Full fields remain; no perspective origin.
20mm/s,5mm reference period. Physical feature tracking for25ms and Bottom180 giving
Left-up/Right-down assert successfully. Exact vectors/normals saved in
 drift-link-preview-directions.json. Initial check advanced retained state before
rendering at0; corrected evidence helper to evaluate each requested timestamp from
fresh state, leaving runtime integration untouched. PNGs inspected; both GIFs decode
25 frames/1040x1010/40ms (quarter speed), changed midpoint assertion passes.
No production/policy/contract, saved input or device edits. No unrelated runtime
suite repeated. Optical correctness is not established; owner visual review precedes
implementation. A documentation patch missed a concurrently mojibaked task separator;
retried by stable task ID without altering other agents' entries.

### Right-only video investigation — no new runtime change

Owner supplied Downloads/IMG_1435.MOV and reports Bottom/Left/Front coherent but
Right not. Retained raw copy rig-video-IMG_1435.MOV, frame decodes rig-video-1s.png
and rig-video-6s.png, ffprobe metadata and inspect_rig_video.py/rig-video-phase.json.
H264720x1280,273 frames, duration9.133333s, nominal30fps. Decoded frames visibly show
full fields; no projection origin issue identified. Saved Pedro config has all
flips false. Cached last_configuration profile also has orientation-preserving
Front/Left/Right meshes, but it may be a different run and is not attribution of
the MOV's active configuration.

Geometry explicitly defines Left horizontal+rigY, Right horizontal−rigY. Policy33
shares one identical local gradient; a Right-only horizontal stimulus-coordinate
reflection is the focused diagnostic proposal to reconcile physical side direction,
keeping vertical gradient, temporal clock, period and full coverage. Not yet an
accepted/validated new mapping. An asymmetric arrow/text check distinguishes a
global optical calibration reflection from a Grating-only link convention. A speed
sign change alone cannot fix tilt. Cardinal0/90 and diagonal45 checks, then all eight,
are required before claiming optical resolution.

Approximate fixed hand-picked quad rectification/FFT carrier extraction is only
supporting exploratory evidence. Phase slope estimates are not reliable timing
measurements: camera movement and partial Right crop give Right residual RMS2.47
cycles, substantially larger than other regions. No speed/180-degree-reversal claim
is based on those values. Retain result with this limitation. ffmpeg/cv2 decoded
only; source video and saved config unchanged. One rg invocation incorrectly used a
PowerShell ErrorAction flag; subsequent direct JSON/profile reads succeeded. No
runtime/config/device actions or unrelated test reruns.

### Approved full-screen local wave — current implementation

Owner explicitly accepted flat-four-projectors-candidate.gif and authorized
implementation for all linked screens and random0..315/45-degree orientations,
with no origin or uncovered stimulus areas. V02rev26/G01rev388 and policy33 now
govern one infinite local physical affine wave. Current canonical policy digest
a17197e4233dc98190f31abb1c799dfe7ca163f449d331839c9fa7b66c87a8dd.
Reference physical gradient and centre phase are copied through inverse target
stimulus maps. All followers share local angle/period/signed drift; corners need
not stitch in world space. No perspective divide, horizon or geometry dependence
remains. Removed the perspective cache, UV coefficients and extra shader/evidence
uniforms; existing full coverage, calibrated corrections and masks are retained.
ARCH-002 keeps the smaller pure helper; RenderEngine only loses geometry arguments
at existing assembly calls. No new dependency/process/state owner.

QT_QPA_PLATFORM=offscreen, five-module owner pytest as previous broad runs, external
basetemp flat-local-final:492 passed,70 deselected,5 subtests in19.89s. A100-epoch
seeded uniform_grid_v1 rule with retained rig-angle convention samples all eight
angles and proves every linked snapshot has common local angle/phase and -0.1cycle
drift per25ms (20mm/s at5mm). All64 angle/reference/positive-map combinations prove
physical local field equality and production coverage enclosure of all screen
corners. Long drift/backward seek, eye invariance and unlink phase remain covered.
24 native OpenGL waveform/full-alpha cases pass. Initial diagonal fixtures showed
up to about2e-5 amplitude discrepancy from vertex raster snapping; fixture vertices
were aligned to pixel grid rather than loosening3e-6 waveform assertions.16 evidence
contract cases pass with native hard-link permission. Scoped Ruff/13-file format,
ten-source Win32 mypy,796-module boundaries/zero violations and whitespace pass.
Formatting-context and import patch mismatches were reread/reconciled.

flat_linked_preview.py --runtime generates flat-four-projectors-implemented.png/.gif
from actual PreviewPlan fields. PNG inspected; its panel area exactly byte-matches
the approved candidate. GIF decoded25 frames/1040x870/40ms, quarter speed. Runtime
rendering assertions verify spatial variation, changed midpoint and exact0.25s
repeat. Saved protocol/calibration and devices unchanged. No native session restart,
physical Grating presentation or optical policy33 acceptance claimed. Prior policy32
rig rejection below remains unresolved until the new implementation is tested there.

### Rig feedback rejects the subject-perspective implementation

Owner reports Bottom/Right share one coherent direction, Front/Left another; parts
of screens are uncovered and origin is visible. Explicitly rejects partial coverage
and wants simple straight bars moving the same direction in per-projector views.
No new agent native/optical measurement or attribution to calibration flips.
Current perspective field mathematically has a horizon; it does not satisfy this
revised full-coverage requirement. All prior test passes remain scoped checks of
the old model, not evidence that the rig meets the revised target.

flat_linked_preview.py creates a read-only full-screen local-coordinate candidate
using the saved geometry extents and source state after an in-memory45-degree/
20mm/s override. Each face uses the same signed local gradient,5mm period and shared
clock, with no perspective divide, origin or horizon. This is a visual proposal;
projector output corrections/subject-view parity are not claimed by the drawing.
PNG inspected; GIF25 frames/1040x870/40ms playback, quarter speed. Nonconstant spatial
signals, changed midpoint and exact0.25s repeat assertions pass. Saved inputs,
production source/policy and devices unchanged. Await owner visual clarification
before another runtime mapping. No unrelated runtime suite repeated.

### Option A selected and implemented — current result

Owner chose the forward subject-eye sheet. V02rev25/G01rev387 and policy32 now
govern gaze rig−Y/down30° at the fixed calibrated observer; the old orthographic
external-camera and folded fields below are superseded. Current canonical policy
digest6b2cd28096cbbe8887b3f1886815d6ea9b9b52244eaddac94974a399359e89c1.
The analytic local reference-centre Jacobian calibrates wave coefficients to
authored physical period, Orientation and Speed there, with perspective variation
elsewhere. Both reference and followers resolve homogeneous physical rows and a
shared temporal offset. Shader/preview convert rows through the same actual quad
UV mapping. Horizon depth<=1e-6mm has transparent coverage. Exact float32 flag,
numerator/denominator and phase are included in evidence uniform layouts.
Unlink retains the local tangent/centre phase rather than promising whole-screen
continuity with a restored independent affine pattern. No head/gaze tracking.

ARCH-002: pure projection/UV maths in existing focused config helper, existing
snapshot/shader/uniform/preview paths, no new dependency/process. The eleven scoped
files pass Ruff/format; eight-source Win32 mypy and796-module boundaries pass.
Five-module QT_QPA_PLATFORM=offscreen pytest, authorized external basetemp
subject-a-verified:492 passed,52 deselected,5 subtests in27.15s. All eight angles,
four references, non-identity scale/shear/offset maps, full incident edges, eye/cache
changes, translated features,50-second periodicity, backwards seek and mask covered.
Six native GL cases pass (three sharpness values, independent/projective variants).
Resource/evidence initial run168 pass/one sandbox os.link WinError5; focused evidence
rerun outside sandbox16 pass, no relaxed assertions. Native GL/evidence use isolated
contexts and temporary files, not a physical projector presentation.

Initial59 affine-test failures were model-assumption mismatches. After updating
checks for homogeneous phase/features,180-degree periodic raster check exposed
real cancellation from subtracting a large temporal offset in spatial derivatives;
fixed by computing the spatial ratio directly. Corrected edge-on fixture to the
new gaze frame. Final checks pass. Initial combined delete/add patch was rejected
before changes; split operations succeeded. One formatted-context patch mismatch
and contract replacement prefix mismatch were corrected after rereading.

subject_projection_options.py --runtime reads the same saved inputs and evaluates
actual PreviewPlan homogeneous field snapshots. subject-forward-implemented.png
and .gif show the selected45-degree example and motion,25 frames/1040x930/40ms frame
duration at quarter speed. PNG inspected; GIF decoded. Coverage overview brown is
diagnostic only; actual outside coverage is scene background. No saved input/device
edits or new managed native Grating Setup/optical acceptance. Previous evidence
below is historical where inconsistent.

### Subject-centred alternatives — awaiting owner choice

Owner revised the target to subject perspective, then requested previews of both
forward flat image and full surrounding panorama. No production/contract/policy
change. subject_projection_options.py raycasts the four measured usable rectangles
from the saved subject position; upper view is150-degree horizontal pinhole field
looking forwards/down30°, lower view is360-degree azimuth/elevation overview.
Forward-sheet coordinates use a gaze-plane perspective divide; beyond-forward
projection is brown. Panorama uses atan2 azimuth/elevation; rear seam and nadir pole
are retained visibly, not hidden or treated as resolved. Both match local Bottom
centre45-degree normal,5mm period and20mm/s via the local coordinate Jacobian only;
whole-screen physical period is not preserved or claimed. These are conceptual
alternatives, not the current production rendering or an accepted subject model.

Offscreen execution produced subject-forward-concept.png/.gif and
subject-panorama-concept.png/.gif. Both PNGs visually inspected. All four surface
visibility, local gradient and changed midpoint-frame assertions pass; GIF decoding
confirms25 frames at40ms/frame, representing0..240ms logical time at10ms/frame
(quarter speed). Input calibration SHA256 remains
0e6ebeda03c61a398e25b33d016a65ec9a63287706fab3704d2a1e3edb1b8ed4.
No runtime tests repeated for evidence-only rendering. No device, saved protocol,
calibration or production mapping edits. Native/optical acceptance remains open.

### Owner-approved projected sheet — current result

The owner explicitly chose alignment from the tank-preview camera, described one
translated textured sheet projected across the sides, requested preview first,
then accepted projected-sheet-135.png. The approved image uses orthographic
azimuth−35°/elevation25°. The shared resolver now directly projects calibrated
rig points onto that sheet, inverts the independent reference projection, and
evaluates its affine wave everywhere. This supersedes folds/reflections and the
earlier Left-up/Right-down convention. Preview opens/resets at this reference view;
dragging it does not change stimuli. V02rev24/G01rev386, policy29, canonical digest
be7a2485faa44183ed4b1742c738e6c1636b3f94fe40af54166123be77c764cd.

ARCH-002 replaces the previous larger geometry routine with SurfaceProjection and
reuses the inverse affine field resolver. No new dependency/state/uniform/process.
The same five-module pytest command with external basetemp projected-sheet-final
passes456/47 deselected/5 subtests in21.77s. Covers all eight45-degree orientations,
all four reference faces, common projected gradient/spacing and sheet velocity,
whole shared edges, long raster invariance/backward seek, absent unused faces,
edge-on reference rejection and geometry cache identity. Separate Dashboard
planning-preview home-view case passes1/1045 deselected. Five-file scoped Ruff,
seven-file format, four-source Win32 mypy,793-module boundaries/zero violations,
owning policy loader and whitespace pass. Rendering-test Ruff retains unrelated
concurrent upload B007 at3049. The report-update Unicode-heading mismatch made no
write; retried successfully with ASCII-prefix lookup and restored canonical heading.

projected-sheet-motion.gif is25 actual TrialPreview frames, logical timestamps
0..240ms at10ms intervals; playback40ms/frame (quarter speed), looped. Decode checks
25 frames/924x569/40ms duration; first and midpoint rasters differ. Static approved
frame and GIF are offscreen evidence, not optical/native acceptance. Saved inputs
and devices unchanged. Previous evidence below is superseded where inconsistent.

### Two-side reflection also rejected

Owner rejects corrected-sides-135-rotated.png and draws steep Right strokes. The
previous implementation interpreted drawings as tilt sign alone. Approximate
Right screen basis read from that artifact: local right projects(-213,-120) pixels
over128.125mm; up projects(0,-228) over84.944mm. Two hand-read stroke displacements
(29,-171),(64,-198) inverse-map to bar-normal angles14.0/23.8 degrees modulo180,
not45. This is an approximate interpretation, not a new calibration or accepted
mapping. Asked whether desired parallel alignment is from subject position or tank
camera angle. No further production edit, new test/native run or saved input/device
change. All prior local passes remain implementation checks, not visual acceptance.

### Both marked side tilts implemented

The subsequent owner screenshot marks Right's reversed diagonal tilt too. The
same reflection now applies to both side hinge coordinates; Front/Bottom retain
their definitions, vertical cardinal flow and Front/side/Bottom phase anchors
remain fixed. ARCH-002: extend the existing pure resolver, no new state/dependency.
V02rev23/G01rev385, policy28, canonical digest
a10d70fcefb26b907f01aee852e5ac6fb5498a42660f0faaad211155d78b0c0f.

Same five-module pytest command as below, authorized external basetemp
both-sides-final:457 passed,47 deselected,5 subtests in21.35s. Extended reference
parameterization to Right and missing-corner checks to both sides. Two-source
Win32 mypy, four-file format, scoped source/GUI Ruff and792-module boundary checks
pass. Full rendering-test Ruff retains unrelated concurrent B007 at3047. Whitespace
and owning policy loader pass. No new native/optical acceptance.

Actual renderer captures corrected-sides-45.png and
corrected-sides-135-rotated.png; the latter fixes source135 and azimuth-35 for a view
closer to the owner's screenshot, not an exact recovered camera pose. Evidence
helper --azimuth only changes camera pose. Saved inputs and devices unchanged.

### Marked Left tilt implemented

Owner supplied red stripe directions on Left, retaining the shown Front/Right.
The production shared resolver now reflects Left physical coordinates along the
Left/Bottom hinge about the calibrated Front intersection before unfolding. The
shared inverse reference map supports Left as source too. Vertical gradient and
temporal phase retain the requested cardinal flow; the corner anchor is fixed,
but Left's complete Bottom edge no longer matches pointwise. Missing/degenerate
Front corner fails explicitly. V02rev22/G01rev384 and fixed policy27 record this;
canonical digest05e25916716fe504b081670055522168dda1124a1e41fb71b4e2a78eb23b3a0d.
ARCH-002 review retained the focused pure resolver with no new dependencies/state.

QT_QPA_PLATFORM=offscreen: pytest tests/gui/test_stimulus_authoring.py
tests/visual_stimulus/test_rendering.py tests/visual_stimulus/test_configuration.py
tests/visual_stimulus/test_compilation.py tests/visual_stimulus/test_resources.py
-q -m 'not windows and not rig' --basetemp=(authorized visualization root)/left-marked-final
--tb=short:447 passed,47 deselected,5 subtests in20.93s. Initial raw-file policy
digest caused loader failures; interrupted, replaced with canonical policy_digest,
then reran. No assertions relaxed. Win32 mypy two source files, scoped source/GUI
Ruff, four-file format,792-module boundaries and whitespace pass. Rendering-test
Ruff B007 at3047 belongs to concurrent upload changes, not this mapping increment.

Re-rendered actual TrialPreview at45 with saved inputs and no diagnostic angle
override: corrected-left-orientation-45.png. Saved external files/devices unchanged.
Static image only; owner visual and native/optical acceptance remain pending.

The owner also rejects orientation-45.png: both side patterns are described as
orthogonal to Bottom. Rendered candidate-side-orientation-45.png with the existing
diagnostic side-angle negation; it swaps the steep side tilt between Left and
Right in this camera view rather than demonstrating the requested alignment.
Restored orientation-45.png to the unmodified production mapping immediately.
No production change or new motion/phase validation. A marked intended stripe
direction on each wall is needed to disambiguate physical surface orientation
from parallel appearance in this perspective projection.

Owner accepts Front relative to Bottom in straight-preview.png but explicitly
rejects Left/Right stripe tilts. Added --side-orientation-candidate to the read-only
evidence renderer: it negates only those two snapshot rotation angles before
painting. It does not change production source, phase, geometry, policy, saved
inputs or device state. candidate-side-orientation.png is a static orientation-only
prototype; its motion and corner phase are not validated. Asked whether those
tilts match the desired appearance before amending the shared orientation/motion
mapping. Earlier Bottom-left → Left-up/Right-down remains a required constraint.
The existing test passes are not acceptance evidence for this remaining mismatch.

Owner then described one full image wrapping around the tank. Inspected the existing
image Fold layout (a Left/Front/Right row with Bottom below Front). Its wall motion
differs from the prior Bottom-centered flow. Asked which governs; owner explicitly
selected preserving Left-up/Right-down. No full-image wrap algorithm was accepted
or implemented. A vertical grating moved vertically has zero visible normal flow,
so the specified cardinal motion requires horizontal side bars and vertical Front
bars. Generated left-motion-example.png through actual PreviewPlan/PreviewRig,
using --left-motion-example: in-memory only, clears the random rule and sets the
independent Bottom Orientation180/Speed20. Saved inputs remain unchanged. This
static diagnostic illustrates the preserved motion rule; it does not establish
optical direction or acceptance of the original diagonal appearance.
