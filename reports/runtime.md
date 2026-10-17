# Controller and supervisor status

Oct17 `merge-main-oct17` integrates local GUI595ab681 with recording/evidence
origin/main1314a743. Only LOG and this report conflicted; both records and
committed product sources/tests are preserved. Fresh acquisition selection passes
622/5 skipped/2 deselected; focused Dashboard preview/log/Retro/startup selection
passes55/549 deselected. Ruff/format386, Win32 mypy361 and boundaries719/zero
violations pass after regenerating stale ignored bindings from19 Protobuf sources.
Inherited cohesion advisories remain. Full offscreen Dashboard rerun stops after
107 passes at `test_camera_trigger_form_reflows_and_destroys_owned_editors`:
at298px the form is unstacked while the fixture expects stacked. Concurrent
`preview-card-visibility` edits appeared during validation, so these GUI results
are working-tree evidence rather than an isolated committed-tree certification.
An earlier combined run was interrupted after GUI failures and aborted in Qt
fixture construction; no full GUI or native/rig pass is claimed. Existing
`devices-narrow-overflow` tracks the reflow finding; cause remains unverified.

Oct17 `log-error-color` implements [G02](../docs/architecture/gui.md#g02) revision76:
error log blocks and Retro prompts use the existing coral-red error palette token.
Command completion supplies explicit severity (failed/rejected/unconfirmed versus
completed/operator-input/cancelled); unstructured local messages use recognizable
error words, excluding negated wording. Explicit successful recovery stays normal
even when its message mentions an earlier failure. A syntax highlighter preserves
source text, entry-bound details and normal-row formatting after errors; appearance
switching refreshes colors. No runtime/error classification authority changes.

ARCH-002 review extracts Console/FittedConsole/LogConsole and bounded details from
the500-line component module into focused `consoles.py`, retaining component imports
as compatibility exports. `log_colors.py` owns classification/highlighting and is
shared with the Retro prompt painter; no new package, whole-runtime reference or
duplicate log history. Main only supplies existing outcome flags; its prior size
advisory remains an orchestration-cohesion review rather than another responsibility.
The owning Dashboard module retains its scenarios and adds10parameter cases:
log/appearance/HUD selection38pass, with604collected total versus594before this
increment. Coverage includes source-status severity, negative wording, no color
bleed, style changes, exact text/details, bounded history and scroll following.
Scoped Ruff/format, Win32 mypy5, boundaries718/zero violations and whitespace pass.
[Inspected sample render](runtime-evidence-2026-10-17/review-synthetic-preview/log-error-colors.png)
and [method/scope](runtime-evidence-2026-10-17/review-synthetic-preview/log-error-colors.json)
retain fixture provenance. Fresh native Retro Review reopened maximized with
synthetic previews; no real device errors or Windows/rig acceptance are claimed.

Oct17 `preview-card-fit` implements [G01](../docs/architecture/gui.md#g01)
revision220: the shared placement helper selects the largest permitted initial
square fitting the visible Preview card/desktop intersection and centers the full
native frame within it. Title/border reservation and Cocoa minimum frame width are
included; insufficient visible room reports an error rather than overlapping
controls. Reopening samples the current card. Windows keeps its existing physical
DPI/client-to-screen path; local synthetic Cocoa Review corrects HighGUI's
work-height origin after its first move selects the screen. This follows
[OpenCV's owning Cocoa implementation](https://github.com/opencv/opencv/blob/4.13.0/modules/highgui/src/window_cocoa.mm).
ARCH-002 review extends the existing focused helpers without new dependencies,
protocol fields, image readers or continuous window repositioning.

Placement/closure selection19pass covers centered fit, clipping, insufficient room,
native minimum width, scales1/1.5/2, Cocoa coordinate conversion and Connect/Hide
lifecycle. Native isolated Retro Qt/OpenCV probes measure actual own-process Cocoa
frames against maximized Dashboard and restored Cameras cards: both contained,
center errors(-1,-2)px within conservative chrome reservation. The first native
probe exposed8px horizontal error from minimum width; the final probe includes it.
[Initial evidence](runtime-evidence-2026-10-17/review-synthetic-preview/card-fit-native-initial.json),
[final results](runtime-evidence-2026-10-17/review-synthetic-preview/card-fit-native.json)
and [method/source](runtime-evidence-2026-10-17/review-synthetic-preview/card-fit-native.py)
retain scope. Scoped Ruff/format, Win32 mypy2, boundaries716/zero violations and
whitespace pass; existing unrelated size advisories remain. A fresh maximized
Retro Review with synthetic previews was opened. No real camera, mixed-monitor
Cocoa placement or new-location Windows-native acceptance is claimed.

Oct17 `retro-entry-maximized-start` implements the owner's Retro entry prompts in
[G02](../docs/architecture/gui.md#g02) revision75. Shared Console painting adds `>`
to each nonempty HUD/log block in a reserved margin; separators and wrapped
continuations stay unmarked. Appearance switching restores the plain margin and
preserves text/entry metadata. Captures of the Dashboard HUD/log were inspected
([HUD](runtime-evidence-2026-10-17/review-synthetic-preview/retro-entry-hud.png),
[log](runtime-evidence-2026-10-17/review-synthetic-preview/retro-entry-log.png));
these are local offscreen Qt renders of sample data, not runtime/rig telemetry.

The owner clarified that the nonmaximized startup concerns local Review. An initial
native probe already reported maximized with frame equal to available desktop, so
the reported failure was not reproduced. The shared startup helper now reapplies
maximization once after the first native/layout event pass under
[G01](../docs/architecture/gui.md#g01) revision219, without forcing later Restore.
The saved-draft Retro Review was reopened with synthetic previews; its native frame
and available desktop both equal(82,33,1388,923), maximized true
([method/source](runtime-evidence-2026-10-17/review-synthetic-preview/retro-startup-native.py),
[result](runtime-evidence-2026-10-17/review-synthetic-preview/retro-startup-native.json)).
The menu bar/Dock remain outside the usable desktop. This establishes the current
local launch state, not the cause of the earlier report or Windows acceptance.

Appearance/HUD/startup/placement selection17pass, including style restoration,
unchanged log text and deferred maximize followed by manual Restore. Scoped
Ruff/format, Win32 mypy6, boundaries716/zero violations and whitespace pass.
ARCH-002 review reuses focused console painting and layout helpers without new
dependencies; the oversized main entry point only replaces its duplicate launch
calls with the shared helper. Existing unrelated cohesion advisories remain.

Oct17 `preview-below-status` implements the owner's placement correction in
[G01](../docs/architecture/gui.md#g01) revision218: Preview sits below HUD and log
inside their original status column on Dashboard, Cameras and Tracking. Removing
the extra shell column restores the original control/status widths and top/right
alignment. Log and Preview share available height; the square image fits below
the card heading. A single slot moves between owning status columns on navigation;
other tabs retain their original layout. Existing helpers own the change under
ARCH-002, with no new dependency or runtime state.

The owning preview/HUD/device-tab selection passes46cases, including original HUD
alignment, fitted telemetry, log growth, below-log placement/containment and source
closure. Scoped Ruff/format, Win32 mypy2, boundaries716/zero violations and whitespace
pass. The offscreen Cameras render was inspected and Dashboard geometry checked;
[captures/method](runtime-evidence-2026-10-17/review-synthetic-preview/below-status-layout.json)
retain local scope. A fresh maximized Review with fake previews was opened for the
owner. Native Windows placement at the new vertical location remains unverified;
the Oct16 coordinates below are historical and do not establish this layout's native
acceptance. No real device or runtime was restarted.

Oct17 `review-blank-preview` updates the initial `review-synthetic-preview` under
[G01](../docs/architecture/gui.md#g01) revision221. Default isolated `--review`
now opens blank black OpenCV windows on camera Connect or an active source's Show,
including noncamera selector sources. The title retains its local Review label;
there are no image annotations, grid or animation. Existing placement, Hide,
Disconnect, inactive-source and exit cleanup remain. X clears visibility without
disconnecting the camera fixture. `--fake-previews` remains compatible; real-device
inspection retains its separate opt-in boundary and managed acquisition is unchanged.

ARCH-002 review removes drawing/frame-update work from the existing focused helper;
the timer only pumps native events and detects closure. No dependency, process,
camera reader or runtime reference. Owning placement/lifecycle selection19pass,
including black pixels before/after polling, camera and Visual stimulus Show/Hide,
external closure, Disconnect and cleanup. Scoped Ruff/format, Win32 mypy2,
boundaries718/zero violations and whitespace pass. The actual Review entry point
with `--review` alone opens a native visible180x180 black image, then closes it;
the updated GUI remains open for the owner
([method/source](runtime-evidence-2026-10-17/review-synthetic-preview/blank-default-native.py),
[result](runtime-evidence-2026-10-17/review-synthetic-preview/blank-default-native.json)).
Earlier native smoke of the animated version is historical
([method/result](runtime-evidence-2026-10-17/review-synthetic-preview/native-smoke.json),
[source](runtime-evidence-2026-10-17/review-synthetic-preview/native-smoke.py)).
Windows-native, real-camera and rig acceptance remain separate under E15.

Current Oct17 recording sync repair completes a 120 s concurrent workload at
unchanged saved quality, with Behavior 3598/3598, Tracking 7188/7188 and stimulus
7200/7200 retained exactly once, zero native counter gaps/capacity omissions.
The explicit fixture uses temporary 16 stimulus slots; restored saved three-slot
startup behavior is not certified. Normal output closure, Cleanup/NewSession and
Shutdown/process absence confirm; original sync cadence and lifecycle bounds stay.

Full backend validation is 2209 passed/5 privilege skips; explicit NVOF rig case
passes. Ruff/format, Win32 mypy 815 files and 717 backend modules/zero boundary
violations pass. GUI source is unchanged; prior GUI evidence is historical, not a
new native GUI run. All three camera baselines and ten operator files restore.
Earlier Abort Finished, failed-Setup late report and historical Shutdown findings
remain open. Pixel-exact performance on final source remains unvalidated; failed
pre-hotpath-guard experiments cannot establish current success or failure.
[Current evidence and provenance](runtime-evidence-2026-10-17/file-sync-fix/README.md).

Oct16 `device-action-cancel` implements owner-selected safe cancellation under
[G01](../docs/architecture/gui.md#g01) and [A11](../docs/architecture/acquisition.md#a11).
Camera Connect/Test selected, MCU connection/pin tests and SpikeGLX Test connection
show Cancel while pending and disabled Cancelling after a click. The GUI skips
remaining steps, waits for the existing bounded call, and closes only newly created
resources using confirmed controller identity. Accepted settings and pre-existing
connections remain. MCU cleanup adds an exact-connection Disconnect command using
the existing outputs-off/close owner; admission and execution retain authority,
Configuration/camera-claim gates and bounded deadlines. Unconfirmed cleanup or
changed controller/acquisition identity is an error, never reported as cancellation
success. Firmware Upload and safety Stop/Disconnect retain their completion behavior.
Restart the full runtime to load both client and controller contract changes.

ARCH-002 review: isolated button/token and compensation logic in two focused GUI
modules; existing panels/coordinators only wire lifecycle callbacks, with no new
process, package, whole-runtime back-reference or duplicate authoritative device state.
Existing size advisories for panels/main remain cohesive presentation/orchestration
owners. Extended the owning GUI and MCU behavior suites. Final offscreen selection
(`pytest tests/gui/test_dashboard.py tests/controller/test_microcontroller_owner.py
 tests/controller/test_microcontroller_protocol.py -q -k
 '(camera or mcu or microcontroller or spikeglx or cancellation or manual_disconnect)
 and not picker and not chooser'`) passes272, skips1, deselects443. A subsequent
pin-button click assertion passes separately (1/582 deselected). Covers queued and
in-flight cancellation, skipped Show/Connect, retained accepted settings, exact new
preview/serial cleanup, preserved pre-existing connection, generation change,
cleanup failure, repeat-click fencing and button restoration. Initial checks exposed
and fixed the MCU completion label overwrite and managed-camera Cancel authority gate;
two older request-dictionary assertions now include the per-request cancellation token.
Ruff/format212, Win32 mypy210, boundaries715/zero violations and whitespace pass;
19 Protobuf sources regenerated. Tests used approved loopback access and Qt offscreen.
No live-device cancellation, firmware action or native/rig acceptance was performed;
[E15 rig verification](rig-verification.md) remains separate.

Oct16 `gui-preview-slot` implements [G01](../docs/architecture/gui.md#g01): runtime
and Review open maximized, with a reserved Preview area on Dashboard,
Devices/Cameras and Tracking. Owner native feedback exposed the initial full-height
card and preserved Z-order as unsuitable. The fitted card now reserves only the
initial image/native chrome plus heading/padding; physical ClientToScreen mapping
targets its inset child region. Native owner-checked placement uses topmost without
activation, keeping detached windows visible above GUI interaction. Other tabs
reclaim the area; reopening samples current layout. No embedding, image reader,
new protocol/process or backend state is introduced. Focused existing placement
and Windows-native modules own the change under ARCH-002.

Oct16 validation before the below-status correction:14 GUI layout/placement cases and three HighGUI thread/failure
cases pass. The native HighGUI case passes outside the sandbox after sandbox
shared-memory denial; it verifies frame size/position, topmost, nonactivation,
wheel/reset and independent closure/producer continuity. An isolated real Qt/OpenCV
probe verifies exact inset/frame match after GUI activation: maximized image640,
frame642x672 at(1250,150), restored image373/frame375x405 at(805,158), both96dpi.
The fitted native GUI capture was inspected. Scoped Ruff/format, Win32 mypy3 and
boundaries715/zero violations pass; existing unrelated cohesion advisories remain.
[Native probe and results](runtime-evidence-2026-10-16/preview-slot/native-slot-results.json)
and [validation history](runtime-evidence-2026-10-16/preview-slot/validation.txt)
retain bounded scope. No real camera, mixed-monitor DPI or full-workload acceptance
is claimed. Restart the application to load both GUI and acquisition-owned native
placement changes; no running application/device was restarted by this work.

Current integration (2026-10-16, `merge-dev-gui`): fetched origin/main eac2e0e
is merged with local rig fixes a0dc31a and the appearance checkpoint3743a81.
[G01](../docs/architecture/gui.md#g01)/[G02](../docs/architecture/gui.md#g02)
share the dev font, CRT controls, dynamic card/focus treatment, HUDs, tab appearance
and camera Test selected/Connect row with runtime. MCU wiring is hidden in both
camera layouts; existing camera pin/MCU configuration remains available. Review-only
inline inputs/outputs and multi-screen pulse simulation retain their runtime contract
boundary. Appearance preferences retain the shared key and legacy Review fallback.
This supersedes the narrower appearance-only implementation reported earlier in LOG.
Controller conflict resolution preserves the rig-proven explicit rejected-Update
versus uncertain-transport handling, merged with the dev typed callback contract.
Generated bindings were regenerated from all19 authoritative Protobuf sources.
Local/backend validation:129 conflict-owner cases pass; broader rig-independent
selection2119pass/four skips/31deselected, with three external-asset fixture errors
caused by workspace basetemp. Those three pass on rerun with normal external temp.
The sandbox asyncio socketpair stall was diagnosed before the approved loopback run.
Package sdist/wheel build succeeds outside the sandbox after a temp-access failure.
Ruff/format924, Win32 mypy811 and boundaries713/zero pass. GUI16 focused integration
cases pass. Broader offscreen GUI run passes536 with29 picker/chooser exclusions;
two stale HUD expectations fail, then both pass after alignment with G02's compact
HUD while preserving authority checks. No complete native-GUI pass is claimed.
[Merge context, package logs and runtime camera raster](runtime-evidence-2026-10-16/dev-merge/context.json)
retain the source revisions, checks and limitations.
The protocol timeline remains a cohesive drawing/interaction owner; palette changes
introduce no new runtime ownership or dependency. Both branches' dated rig and dev
evidence below is retained with its original scope; local checks do not refresh rig
acceptance. No device/firmware actions or saved configuration changes were performed.

Historical comprehensive Oct15 audit final source checks pass (E06/E07/E08/ARCH-002):
1920 backend cases pass/five skip/one rig deselected, including eligible native
Windows and HighGUI tests. Ruff, format915, Win32 mypy795 and boundaries699/zero
violations pass. Five skips retain privilege/platform limitations in the JUnit log.
The separately selected rig-only synthetic CUDA/NVOF lease test also passes; it
does not enable live Tracking processing or feedback.
GUI519 pass offscreen across512+7 selections. Native execution finishes510pass/two
fail with seven picker roundtrips excluded. A focused follow-up replaces an
unsupported320px test cap with equal-height/control-containment checks; the full
native trial-row interaction then passes. Inline timeline MouseMove delivery
remains unresolved despite an active/unobscured target; synthetic picker selection
is ignored by the Windows helper. Computer-use state capture separately hangs
twice, so complete manual/native feature acceptance and an all-tests-pass claim
are unavailable. The native failures do not establish clipping or operator picker
failure; bounded diagnostics and exact process absence are retained.

Focused controller repairs distinguish explicitly rejected live-calibration Updates
from unknown transport outcomes, and require acquisition pulse readback only for
enabled external-trigger cameras. Owning coverage pins retained Active fencing,
valid retry after rejection, and real free-running/external readback adoption.
Camera configuration59 cases pass. The later empty-edit failure is traced to a
Windows asyncio timeout occurring3.4854ms before its original deadline. The
acquisition wait now retries only within that unchanged deadline; deterministic
regressions and the combined acquisition/controller/shared1148pass/four privilege
skips verify the correction. Affected managed-interpreter cases70pass/one skip.

Fresh COM8 boot text is `OK READY three_camera_ttl`; read-only request-ID CAPS
returns `ERR Unexpected command arguments`. Managed Connect reaches its original
deadline failure; firmware is unchanged. Earlier40-second preview attempts stop
before the configured70-second deadline and establish only incomplete admission
within the harness bound. Exact managed exit receipts/inventories separate attempts.

The corrected retained-COM8/free-running Setup reaches acquisition Ready but the
saved arena asset exceeds the declared GPU budget. Cancellation then leaves an
exact quarantine containing its marker/lock; its275-character marker path fails
ordinary Windows filesystem access, blocking startup recovery. Native before/after
tests verify existing extended-path transport repairs both cancellation and
lock-only settlement while marker/user-file guards remain strict. Exact own
unstarted artifact remediation retains marker/lock bytes and hashes; no durable
pointer is edited and no general recovery acceptance is claimed.
Subsequent native recovery and seven managed trials complete: four normal60-second
Save-On trials (Gaussian and reduced-texture arena), one normal60-second Save-Off,
and two interrupted trials. All18 retained videos fully decode/count successfully;
Off retains frame/scientific logs but no videos. The immediate post-Abort trial
crosses the retired boundary8.1452seconds after its new start and completes normally.
Abort still takes approximately40.12seconds to settle interrupted metadata; this
responsiveness finding remains open. Independent camera/shader/NVENC runs and nine
full-video decode/count passes are recorded in the owning backend reports; they
do not prove managed lifecycle or calibrated projector rendering. Native cancellation
and startup lock-only settlement now use the existing extended-path transport;
marker-bearing/user-file guards remain strict. The unused shared Deadline wrapper
is removed after a source/contract consumer search, retaining active helper coverage.
An unsupported whole-suite managed-executable
invocation separately fails an entrypoint child missing its DLL bootstrap; this is
retained separately from normal-suite results. [Fresh evidence and settings backups](runtime-evidence-2026-10-15/comprehensive-audit/)
retain these limits; previous successful endurance evidence remains historical.

Fresh native photodiode and blackout diagnostics now pass Open, invalid bounds
rejection, subsequent valid updates, move/remove and Close with Idle/resources
closed; saved asset/profile hashes remain unchanged. The repair validates before
GL dispatch and propagates only typed, exactly proven retained-Active rejection
without renderer shutdown. Generic/mismatched failures remain fatal.361 owning
and132 managed-interpreter cases cover the full mailbox/report path. Opening
calibration after a completed session remains rejected by
retained interrupted/setup fences; safe context retirement is a separate follow-up.

| Feature group | Fresh evidence | Remaining limit |
| --- | --- | --- |
| Dashboard, file/load/save, protocol/variation validation, status and operator controls |519 offscreen pass; native510pass plus focused repaired row pass; [per-feature owning inventory](runtime-evidence-2026-10-15/comprehensive-audit/gui/coverage-inventory.json) |One native hover-input failure and seven synthetic picker roundtrips remain; manual end-to-end GUI coverage incomplete |
| Setup/Start/normal completion/NewSession |Real authenticated controller, two cameras and four projectors; Gaussian and reduced-texture arena |Unaligned free-running fixture; no MCU synchronization or Tracking processing |
| Video Save On→Off→On |3→0→3 videos; frame/scientific logs retained throughout |No scientific scene-quality acceptance |
| Abort/reuse |Two Interrupted trials with confirmed cleanup; immediate new trial crosses retired boundary and completes |40.12second interrupted-metadata settlement remains |
| Camera/controller connections |Fresh enumeration, native Setup/readbacks, full-bound COM8 failure |Legacy MCU command dialect prevents external-trigger acceptance; no firmware flash |
| Calibration diagnostics |Two native views pass Open/invalid→valid/move/remove/Close with unchanged asset hashes |Post-session reopening still fenced; physical calibration unmeasured |
| Rendering/encoding capacity |CQ23/CQ18 camera+offscreen-shader workloads, native4096 variant, full counts/decodes |Tracking imagery sampled black, native4096 one BlockID gap; initial CPU sample confounded |

The final isolated production workload runs exactly60seconds with Behavioral
1760×1716/30Hz and Tracking 1588×1344/60Hz, camera CQ23, stimulus CQ18/YUV444,
four60Hz projector outputs and the explicit512-pixel arena derivative. No other
test runs during this interval. Current machine is Ryzen9 9950X16cores/32threads,
66,094,223,360bytes usable RAM,2TB CT2000P3PSSD8, RTX5060Ti16,311MiB and
RTX2080Ti11,264MiB (driver617.14). [Hardware and monitor evidence](runtime-evidence-2026-10-15/comprehensive-audit/).

| Active-trial measurement | Median |95th percentile |Maximum |
| --- | ---: | ---: | ---: |
| System CPU |11.28% |16.19% |20.32% |
| RTX5060Ti GPU utilization |11% |12% |12% |
| RTX2080Ti encoder utilization |44% |46% |47% |
| Monitored process working sets |2.137GiB |2.179GiB |2.189GiB |

Device-wide GPU memory is716/713MiB respectively;5060Ti encoder utilization is0%.
Working sets include monitoring processes/shared pages and are not system used RAM;
process IO counters include pipes, not physical disk bandwidth. GPU UUIDs and
59 active one-second GPU/CPU-delta samples are retained; no per-process GPU
attribution or sustained headroom guarantee is inferred. Camera videos contain
1801=1798real+3duplicate and3600=3588real+12duplicate frames; stimulus contains
3600=3592real+8duplicate frames with four capacity drops/two same-slot omissions.
Camera failed/missed buffers are0 and counter gaps absent. Stimulus has3598 render
groups, median16.659ms/p99 17.920ms/max33.381ms intervals, with no unresolved
submission attempts. All three full decodes match declared counts, completing
27 video validations across18 managed/nine direct outputs. This is a bounded
low-loss engineering result, not optical synchronization or representative-scene
quality acceptance. [Active resources](runtime-evidence-2026-10-15/comprehensive-audit/managed-isolated-mixed60-r1/resource-assessment.json),
[source/CFR accounting](runtime-evidence-2026-10-15/comprehensive-audit/managed-accounting-summary.json).
All three original pre-audit PFS files restore byte-exact, every original feature
readback matches and all cameras close. All10 saved JSON/TOML files also match
their original bytes; exact application exit receipts confirm process absence.
[Restoration](runtime-evidence-2026-10-15/comprehensive-audit/final-restoration.json).
Final Shutdown returns a successful command and exact process-absence receipt but
also emits `cleanup returned an unregistered resource` from Visual Stimulus after
the completed trial/NewSession/original-configuration restoration sequence. The
trial, decode/count and physical restoration evidence remain valid; shutdown
resource-report acceptance is unresolved. [Emergency evidence](emergency-80538644376400-cf134742-126d-4fc6-aa22-c7ed8d33f493.json)
is retained for a focused follow-up rather than interpreted as clean shutdown.

Oct16 output-content audit under [SYS-004](../architecture.md#sys-004),
[E04](../docs/architecture/supervisor.md#e04),
[A07/A09](../docs/architecture/acquisition.md#a07),
[T19](../docs/architecture/tracking.md#t19) and
[V13/V28](../docs/architecture/visual_stimulus.md#v13): current files retain the
software-side joins below. Both confirmed findings are repaired locally: missing
stimulus replay provenance ([Visual Stimulus assessment](visual_stimulus.md)) and false
absence in camera failed-output summaries ([Acquisition assessment](acquisition.md)).
The repair selection passes997 tests (five platform skips, three exclusions), plus
five final-publication cases; [repair evidence](runtime-evidence-2026-10-16/output-provenance-fixes/validation.json)
retains commands and limits. No additional central-metadata/Tracking output defect
was established in this scoped review.

| Outputs | Retained alignment/reconstruction input |
| --- | --- |
| SESSION_CONFIG, SCHEMA, SESSION_LOG and trial LOG | Session/trial identities, effective configuration, wall/host anchor, planned occurrences, versioned output index and closure; paired SpikeGLX readback/inventory. |
| Camera frame JSONL plus optional MP4 | Exact sequential video-to-source join, receipt/native clocks and counters, explicit invalid/capacity loss and terminal cutoff/accounting. Nominal playback time is not acquisition time. |
| Optional Tracking JSONL | Selected camera role/settings, source IDs and receipt intervals, result/pose/reset/discard evidence; joins to stimulus by stream/result identity. |
| Stimulus recipe and always-saved frame JSONL | Resolved plan/assets/display settings, consumed uniform words, actual media/image choices, effective arena pose, per-output submission/marker times and review-video source mappings. |
| Original SpikeGLX files | External authority for recorded pulse sample times; transfer full native files/metadata and retain segment/stream identity. CephVR control timestamps do not substitute for pulses. |

Owner clarification (Oct16): hardware pulse wiring is verified, all planned camera
recordings will use external triggers, Tracking backend work is deferred, and the
current reconstruction target is software-generated output. This is owner-supplied
hardware evidence; the local audit did not measure wiring or query live mappings.
Checked-in pulse_inventory remains unassigned. Retaining the actual saved-channel
mapping and source-counter semantics still matters for interpreting losses and A09's
assumed initial correspondence. Physical projector light onset is outside this task's
acceptance target. Preserve external assets once in a versioned library, the matching
renderer/environment and native SpikeGLX files; per-run manifests reference matching
content under V13 without copying it. Offline analysis/replay implementation remains
deferred; no new clock fit, asset archive, runtime policy or hardware action is introduced.

The earlier audit selection passed337 across acquisition, controller metadata/planning/
output admission/SpikeGLX control, Tracking recording and stimulus resource/render/
evidence owners. Two standalone probes reproduced the pre-repair findings; first probe invocation
needed the repository on PYTHONPATH. [Commands, source hashes and limitations](runtime-evidence-2026-10-16/backend-output-alignment-review/validation.json)
are retained with raw output. No actual session compilation, native GPU replay or
physical timing validation ran; remaining execution stays in the
[single rig checklist](rig-verification.md).


Oct16 `review-terminal-refinements` applies owner-selected suggestions 2/3/4/5/9,
then 6/7/8 as the Review candidate under [G01 revision210](../docs/architecture/gui.md#g01).
Existing inverse selection/hover and cursor work is retained. Disabled bracket labels
use lowercase; the selected sidebar carries a prompt. One cached, mouse-transparent
window film uses 13/255 scanline alpha and a faint vignette, toggled with heading/lamp
glow in Style. Per-console scanlines were removed so CRT Off removes the film.
IBM Plex Mono Regular (168 KiB) ships with IBM's unmodified OFL license and source/hash
record; Qt registers the bundled font once. No package dependency was added.
The candidate uses a single-line wordmark with a lower rule and double frames on every Retro card
(owner-requested all-card trial), contiguous block-character position meter and shape-coded status lamps.
Position/status/phase retain existing view authority; phase remains in the HUD.
Standard/runtime retain their theme and gates; Tracking controls retain their presentation.
Protocol now shares the Retro treatment described below.

ARCH-002 review moved separable status-lamp drawing into the existing retro instrument
module before extending it; shared components remain below the size advisory threshold.
Offscreen wide/narrow renders were inspected, including empty-log cursor and CRT Off.
Extended owning style-switch coverage passes at1440/720 pixels, preserving drafts,
log bytes, view identity, gates and Standard runtime; checks include actual font family,
mouse transparency, cached-film reuse and toggle behavior. GUI
Ruff/format166, Win32 mypy5, boundaries706/zero violations and whitespace pass.
[Raw checks and rendered fixtures](runtime-evidence-2026-10-16/review-terminal/).
Focused affected GUI checks pass11 (534 deselected). Local non-isolated build produces
a wheel and source archive; all font/license/source bytes match in both packages.
Initial isolated build could not resolve PyPI; installed build dependencies succeeded. An overly broad GUI run
was intentionally interrupted after34 cases and Qt aborted on interruption; no complete
suite pass is claimed. Initial test-import placement/lint issues were corrected before
the passing style checks. Native Windows/DPI, CRT comfort/repaint cost and rig acceptance
remain unmeasured; this work stages appearance only.
Owner-requested all-card frame trial removes the primary-only marker and uses the
same double outline for each Retro card under [G02 revision48](../docs/architecture/gui.md#g02).
Fresh style-switch2, scoped lint/format/mypy, boundaries and whitespace pass;
[comparison renders and commands](runtime-evidence-2026-10-16/review-terminal/all-card-frames/)
retain the prior primary-only fixture alongside this candidate. Standard is unchanged.
The owner subsequently removed the extra review/phase/clock banner under G02rev49;
its label, timer, style rule and obsolete test assertions are removed. Existing
appearance-switch2 passes at both widths; scoped Ruff/format/mypy, boundaries and
whitespace pass. [Fresh render and validation](runtime-evidence-2026-10-16/review-terminal/no-banner/)
show the resulting layout; wide offscreen render inspected. No native/DPI claim.
Owner-requested [Running presentation](runtime-evidence-2026-10-16/review-terminal/running/)
uses existing Review widgets/state: trial2/6, current-trial elapsed48s, ready lamps,
open/reserved/synced sample outputs and coherent example log entries. Setup/Start
and session editing are locked, Stop enabled. Wide/narrow renders inspected and
fixture assertions pass. An isolated interactive window was launched without startup
error; native visibility was not independently inspected. No production source/default
or saved Review draft is changed; content is static sample data, no commands or devices.
Subsequent owner-requested HUD simplification under G02rev50 removes Outputs,
Reservation and Metadata display rows while retaining the underlying state records.
The Retro trial-position glyph strip repeats across the full available width,
preserving current-position/count semantics. [Fresh running preview/checks](runtime-evidence-2026-10-16/review-terminal/hud-simplified/)
pass11 existing appearance/phase/layout cases, scoped lint/format/mypy, boundaries
and whitespace; wide/narrow renders inspected. The owner subsequently selected
Trial time and Total time elapsed/duration pairs under G02rev51, replacing the
previous Elapsed row. Review shows48/150 seconds and198/900 seconds. The managed
projection derives trial duration from scheduled end minus start; the focused
regression distinguishes actual elapsed48s from planned150s and preserves unknown
values. Current Snapshot/SessionState lacks session start/total-duration fields, so
managed total values remain unknown; live-total projection is a follow-up, not a
session-clock estimate or schema amendment. [Timing fixture/checks](runtime-evidence-2026-10-16/review-terminal/time-pairs/)
pass4 existing style/HUD/projection cases plus scoped lint/format/mypy3, boundaries
and whitespace; wide/narrow renders inspected. Native/DPI and rig acceptance remain separate.
The owner consolidated Phase/Outcome into Status, then removed Control under G02rev53:
show reported outcome when available, otherwise current phase, and separate Status
from Trial/timing with a blank line. Command authority/gates remain unchanged. [Updated layout evidence](runtime-evidence-2026-10-16/review-terminal/status-group/)
passes11 existing style/layout/phase cases plus scoped lint/format/mypy, boundaries
and whitespace; wide running render inspected. Live-total timing remains pending.
[Control-removal validation and fresh preview](runtime-evidence-2026-10-16/review-terminal/no-control/)
passes11 appearance/layout/phase cases and scoped lint/format/mypy, boundaries and
whitespace; wide render inspected. No native/DPI/rig claim.

Owner-requested Devices/Protocol/Previews styling and refinements follow
[G01rev212](../docs/architecture/gui.md#g01) and
[G02rev73](../docs/architecture/gui.md#g02). All four device subtabs share the Retro
font, double frames, square controls and bracketed buttons; selected table rows use
dark blue-teal/light text to keep enable boxes visible, while navigation/menu inverse
selection remains. Diagrams retain geometry/semantic roles and use the active palette.
Previews uses a compact shared Card and separate cached, mouse-transparent CRT film;
the style toggle controls both windows. Drafts, preview pending/visibility, device
ownership and command gates remain intact. Runtime retains Standard; shared
table/header sizing repairs apply across pages.
All tab HUDs now use the Dashboard's shared structured-row renderer in StatusColumn:
uppercase labels, aligned value columns across groups, Retro colon separators,
blank section gaps and the same fitted console. Dashboard, device readbacks, MCU
fault/diagnostic updates and Tracking ordinary/diagnostic readouts share this path;
freeform notes retain their text. Appearance changes re-render stored presentation
rows, while Dashboard also refreshes its separately owned trial-position strip.
Tracking's HUD/log column alone follows Retro; its controls remain unchanged.
[Shared HUD evidence](runtime-evidence-2026-10-16/review-terminal/shared-hud/) retains
wide/narrow captures across Retro/Standard/Retro, raw tests and source hashes;
Dashboard/Camera/MCU/Tracking wide cards inspected.42 owning HUD/device/appearance
cases and one additional managed Tracking diagnostic case pass. GUI/test Ruff,
scoped format13, Win32 mypy12, boundaries712/zero violations and whitespace pass.
Initial checks exposed omitted trial-strip refresh and an obsolete equal-width
measurement assertion; repaired. Tracking timing assertions now check retained rows.
The484-line component module remains cohesive shared widget presentation; no new
framework, dependency or backend policy. No native/DPI/CRT-cost/rig acceptance claim.

Protocol now joins the shared Review Retro surface: double card frames, uppercase/glowing
card titles, bundled font, bracketed text buttons, native block caret/focus corners and
inverse menu/trial/timeline selection. Timeline paint uses the active palette and square
Retro frames; unselected epochs retain their deterministic stimulus-content colors.
A shared divider role replaces local QSS. New screen rows register their advanced-card
titles/glow through the existing screens-changed notification; no generic widget observer.
Symbol-only controls retain bare glyphs to fit fixed affordances. Narrow group controls
omit the redundant Selected group caption and balance fields so Group name/Repetitions
remain readable. Qt models, selection/hits, source/history, validation and Running locks
retain their owners; rendered scientific stimulus content is unchanged.

[Protocol evidence](runtime-evidence-2026-10-16/review-terminal/protocol/) retains wide/narrow
fixtures, initial failures, final tests and source hashes. Final15 tests pass, plus both
appearance cases pass again after the shared-HUD integration settled. Checks cover
1440/720 style switches, screen rows added after Retro selection, caption/glow/focus,
unpersisted draft/history/gates, selected-block pixels, layouts, actions/undo and clipboard
paths; renders at1440/1175/720 include populated rows and advanced settings, with wide,
narrow and advanced views inspected. Ruff/format7, Win32 mypy6, boundaries712/zero
violations and whitespace pass. Initial icon-role changes were reverted to preserve
Standard behavior; the shared Button skips decorative brackets on symbolic glyphs.
A pre-existing platform-dependent321px card height failed a320px test cap even with
the original inline divider restored; the owning assertion now checks compact bottom
padding against actual group controls rather than a font-dependent total height.
Fixture draft setup now explicitly applies the local edit before testing style changes,
matching existing subgroup auto-commit semantics. A temporary concurrent shared-HUD
change omitted Dashboard rendering and hid its trial-position instrument; the settled
appearance path renders both status rows and Dashboard instruments once.

ARCH-002 cohesion review retains the existing timeline paint/interaction owner: palette
lookup and selection paint use its current geometry/state without another coordination
layer. Shared tests remain in their owning behavior module. No full GUI-suite, native/DPI,
CRT repaint-cost, hardware or rig acceptance is claimed.

Owner reported a crash on Add variation rule. The13:37 native report shows SIGABRT
through PyQt QTableWidget eventFilter amid nested QWidget visibility/synthetic enter-leave
dispatch; its original Python exception and exact loaded source revision are unavailable.
VariationTable changed remove-button visibility inside Enter dispatch, while the table-mode
row also showed the same button in its own Enter handler. Under G02rev73/ARCH-002,
the table now owns these affordances alone and coalesces hover updates through one
parented single-shot Qt slot after dispatch, resolving the pointer against current rows.
Pending updates tolerate removal/replacement; standalone rows retain their hover owner.
No rule values, generation/seed behavior, source ownership or history policy changed.

[Variation crash evidence](runtime-evidence-2026-10-16/review-terminal/variation-crash/)
retains native stack extraction/provenance, red callback-timing assertions, native probes
and final25 passing variation/subgroup/history/style cases. Both Standard/Retro regressions
failed before repair and pass afterward; hover show/hide and queued removal/reopen are
covered. Ruff/format3, Win32 mypy2, boundaries712/zero violations and whitespace pass.
Native Cocoa runs complete21 repaired add/remove cycles across1440/1175/720:9 Standard,
9 Retro and3 using the owner's saved Review draft read-only. No callback errors occurred.
The exact original abort was not reproduced even with legacy callbacks restored in an
isolated saved-draft probe, so the repair removes the implicated reentrant path rather
than proving its original Python exception. Keep `variation-open-crash` pending owner-session
confirmation and collect stderr if it recurs. The first sandboxed Cocoa attempt could
not access screens; approved isolated native runs succeeded. No native Windows,
alternate-DPI, hardware or rig acceptance is claimed.

Camera HUD now shows inventory found/enabled counts, a single shared dashed separator
in Retro, then selected role, connection status, Trigger source, controller-configured
external Trigger rate and backend acquisition rate. Trigger source shows Internal clock
or External controller above Trigger rate, from controller configuration in managed
mode and the local draft in Review. Its confirmed serial-keyed projection clears on
disconnect and is reused when installing editable drafts. Five owning appearance/pin/
inventory cases pass, with both inventory cases rerun after final source/disconnect
assertions; Ruff/format3, Win32 mypy2, boundaries712/zero violations and whitespace pass. Confirmed trigger configuration is keyed by serial
and cleared on controller disconnect; unsaved edits/free-running camera pulse drafts
are not shown as confirmed external rates. CameraDeviceView currently exposes no
measured receive rate; Acquisition rate stays unknown and `camera-acquisition-rate-readback`
tracks that integration. No configured/synthetic frequency substitutes for observation.
[Camera HUD evidence](runtime-evidence-2026-10-16/review-terminal/camera-hud/) retains
wide/narrow sample captures and source hashes; wide image inspected. Five selected
appearance/preset/inventory cases pass, with both inventory cases rerun after final
count/status assertions and separator cleanup. Scoped Ruff/format3, Win32 mypy2,
boundaries712/zero violations and whitespace pass. The shortened camera page remains
its existing cohesive assembly; no new helper/dependency or backend schema change.
No native/DPI/hardware/rate-measurement acceptance claimed.
The sidebar brand omits its Experiment Control subtitle in both appearances. Retro
uses a single-line CEPHVR wordmark with restrained tracking, a thin lower rule and
version only in the footer, replacing the awkward text-drawn box. [Sidebar renders](runtime-evidence-2026-10-16/review-terminal/sidebar-wordmark/)
fit at1440/720px; wide crop inspected. Two appearance cases, Ruff/format3, Win32 mypy2,
boundaries712/zero violations and whitespace pass. First standalone capture exited138
during Qt teardown after saving images; explicit effect removal/deferred-widget cleanup
lets the same fixture exit0. No production teardown regression or native/DPI acceptance
claim is inferred from the standalone fixture.
The Photodiode card uses shared content-sized caption geometry; its obsolete wrapping/
full-width override is removed so the frame gap is100px rather than nearly card-wide.
Main page headings share the existing card-title CRT glow and its toggle. [Heading/frame evidence](runtime-evidence-2026-10-16/review-terminal/heading-frame/)
checks1440/1175/720 caption widths and all four page headings;1175 card and Devices
heading inspected. Six existing appearance/layout/configuration cases pass, including
matching glow parameters and CRT-off/Standard removal; Ruff/format3, Win32 mypy2,
boundaries712/zero violations and whitespace pass. Existing cohesion warnings unchanged;
no native/DPI/repaint-cost acceptance claimed.
Card captions now use Displays layout without its Display IDs suffix, Setup geometry
instead of Tank & screens, and Runtime log across shared page assemblies. Retro
retains its existing uppercase transform. Three existing card/appearance checks pass;
the dashboard-only card assertion now excludes the separately owned Preview sources
dialog introduced earlier. Initial run exposed that assertion drift. Scoped Ruff/format,
Win32 mypy2, boundaries712/zero violations and whitespace pass; native/DPI unverified.
SpikeGLX Input channels now content-sizes Use instead of fixing it at42px.
[Header geometry and renders](runtime-evidence-2026-10-16/review-terminal/input-use-header/)
show one-line Use at1440/1175/720 in both appearances (Standard53px, Retro50px);
Retro1175 capture inspected. Five owning inventory/layout cases pass, scoped
Ruff/format/Win32 mypy1, boundaries712/zero violations and whitespace pass.
Native/DPI acceptance remains separate.
Icon-only controls use a dark hover/pressed fill and accent outline, preserving refresh
symbol contrast. [Actual-control state captures](runtime-evidence-2026-10-16/review-terminal/refresh-hover/)
verify normal/hover/pressed/disabled rendering and measure the hover/pressed background;
hover/pressed images inspected. Two appearance cases, scoped Ruff/format/Win32 mypy,
boundaries712/zero violations and whitespace pass. Native/DPI inspection remains separate.

Projector measurement Screen/scale columns size to contents, allocating the remainder
to measured X/Y; the header fits one line at1440/1175/720px. Offset X/Y share one cell
like Width/Height. Scale labels display one decimal in their existing mm/px unit;
raw measurements, derived distance and saved precision remain intact. [Calibration evidence](runtime-evidence-2026-10-16/review-terminal/calibration-table/)
retains geometry, captures and source hashes;1175px cards inspected. Seven calibration
checks pass, including rounded-display/full-precision derivation and paired offset
ownership; Ruff/format3, Win32 mypy2, boundaries712/zero violations and whitespace
pass. Existing cohesion warnings unchanged; native/DPI acceptance remains separate.

Shared PathEdit fields now accept both Ctrl and Command-style select-all/copy/cut/paste
through native line-edit operations, preserving full underlying paths. Focused read-only
paths display native text selection rather than elided painting. This covers output and
Assets directories, stimulus filepaths and other shared path fields; mutation still
respects read-only/disabled gates and existing stimulus validation/commit ownership.
The local baseline reproduced Meta+V inserting a literal v while Control+V pasted.
Seven owning clipboard/asset/style cases pass, plus both stimulus cases rerun after
extending coverage to an absolute pasted path; relative paths, Unicode/long directories,
selection/cut, saved-asset commit, invalid-file rejection and Running locks are checked.
Ruff/format2, Win32 mypy1, boundaries712/zero violations and whitespace pass. One
integer-versus-Key mapping annotation/import-order finding was repaired. Native platform
clipboard integration remains unverified beyond host offscreen Qt; no rig claim.

Styled inputs use one native Qt block caret at insertion position, with typed text
immediately to its left. The theme's existing Fusion base supplies a wider cursor metric
only to Retro QLineEdit fields; remove decorative block painting and separate field
blink subscriptions. Qt owns cursor placement, scrolling, selection and blinking;
Standard restores the base thin caret. [Native-caret evidence](runtime-evidence-2026-10-16/review-terminal/native-block-caret/)
checks typing, Home/End insertion, selection replacement, long-value scrolling and
Standard/Retro switches (cursor rectangle width16 versus10 including Qt insets).
End/Home/replacement/long-value captures inspected. Five owning appearance/pin/editing
cases pass; Ruff/format2, Win32 mypy2, boundaries712/zero violations and whitespace
pass. No native/DPI/complex-script acceptance claimed.

Camera source/rate/pin boxes now bottom-align when a label wraps: source review and
capture reproduced an8px rate/pin offset at1175px, then actual y/height equality passes
at720/1175/1440. VSync mode is an independent full-column field aligned to card edges.
Shared Qt headers measure wrapped text at actual section widths and refit after
resize/font changes, retaining empty-header visibility and owner extra-height settings.
A resize lambda initially segfaulted in a repeated-window sequence; a receiver-owned
Qt slot removes that reproduced failure in the five-case sequence and final21 checks.
This is not evidence about the historical native GUI fault's cause.

Review Add output now inserts an empty inline type/pin row with no menu/pin dialog.
Selecting an existing supported signal binds its original pin owner; changing type
transfers that pin without changing camera participation. Clearing a selected pin
retains the row until explicit removal. Unassigned/empty drafts survive both marked
Review files and full Review draft restoration; invalid identities/capacity are rejected.
Test/admission locks remain, and runtime output authoring is unchanged pending review.
ARCH-002 keeps draft presentation/validation in a focused Review output helper and
header painting in one small shared module. Cameras/MCU/Projectors remain cohesive
page assemblies with only focused layout/class-selection anchors; size advisories do
not justify duplicating those responsibilities. Dynamic fields use live focus wrappers.

[Current commands, hashes, raw checks and captured controls](runtime-evidence-2026-10-16/review-terminal/device-polish/validation.json)
record21 focused passes, GUI Ruff/format171, Win32 mypy12, boundaries712/zero violations
and whitespace pass. Device/projector/table controls were captured at1440/1175/720;
Protocol/Tracking pages also rendered at1440/720. Representative full-page and direct
control views inspected; direct captures disable CRT/glow for clear boundaries.
Initial spacer, forward-reference/typing/test-import attempts were corrected; raw
resize callback failure is retained. [Prior style/selector evidence](runtime-evidence-2026-10-16/review-terminal/devices-previews/validation.json)
retains the repaired compact-selector height checks and dynamic focus coverage.
No full GUI/native Windows/DPI/hardware/rig pass or measured CRT comfort/cost is claimed.


Oct16 `review-device-layout-multipulse` / `review-mcu-input-editor` implement the
owner's staged review candidate under [G01](../docs/architecture/gui.md#g01).
Camera MCU wiring is now hidden and Test selected/Connect paired in both modes;
Review-only MCU Inputs and
Outputs follow the connection card. Inputs now uses the shared Outputs-style table
with Add input, editable names/pins, enable checkboxes and remove buttons. Empty
Inputs shows only Add input, with table/header hidden. Unfinished definitions survive
review draft/file save and restore; legacy input-free files restore empty. Review
files retain an explicit extension rejected by managed runtime. Phase/observer and
active device-operation gates disable edits; input Test remains disabled under
[A11](../docs/architecture/acquisition.md#a11)'s physical/serial/firmware deferral.

Review Synchronization retains per-face Frame/Pulse drafts; blank faces add no pulse,
partial edits preserve other complete patches, and mixed VSync selects every enabled
pulse face. A modeless four-screen local fixture repeats V22's sequence without
resetting on edits. Planning overlays and review persistence retain multiple patches;
legacy single-pulse files remain loadable. Runtime multi-pulse/input support,
physical rendering, pacing/evidence and rig testing await owner review and promotion.

ARCH-002 review keeps the new behavior in focused review layout, timing, file and
input owners, reusing existing table/pin/card components, rectangle parsing and marker
pattern; no dependency added. Shared large Cameras/Projectors/MCU modules retain only
cohesive assembly selection; their existing size advisories do not place new feature
logic there. Baseline review/runtime parity stays tested with staging disabled.
Current input/MCU/persistence/parity selection passes28; scoped Ruff/format7, Win32
mypy6, boundaries710/zero violations and whitespace pass. Empty/populated renders
were inspected; owning layout cases cover720/1280. Initial test-caption/import issues
were corrected. [Current input commands, hashes and renders](runtime-evidence-2026-10-16/review-mcu-inputs/validation.json).
The initial broader GUI run had520 passes and the separately tracked Protocol
card-height failure (321px versus<320); it predates this input refinement. Earlier
pulse/layout checks and their limits remain in the
[staging evidence](runtime-evidence-2026-10-16/review-device-layout/validation.json).
No physical input, Windows, optical or actual VSync acceptance is claimed.

Oct16 baseline `gui-review-runtime-parity`: [G01](../docs/architecture/gui.md#g01)
and [G02](../docs/architecture/gui.md#g02) already share page construction.
Extended the owning real-composition regression to compare visible control positions,
sizes and accessible identities across every page/device/projector/Tracking subtab
at 1280/720 pixels, plus Dashboard/Protocol/Tracking authoring and Stop gates across
all eight phases with and without control. Match camera selection explicitly; compare
semantic controls independently of Qt child creation order. Hardware actions retain
their connection/ownership prerequisites; no production change was required.
The focused offscreen parity/style selection passes six cases; GUI Ruff/format
checks pass161 files, boundaries check698 modules/zero violations and whitespace
checks pass. Existing cohesion advisories remain; no runtime dependencies/state or
source owners changed under ARCH-002. Validation uses HEAD0361484d plus the concurrent
dirty tree on macOS; native Windows/DPI, device execution and rig acceptance remain
separate. Initial expanded-test failures concerned child order, unmatched camera
selection and hardware-specific gates; corrected test setup/scope before the final run.

Oct15 photodiode placement now repeats V22 pulses while accepting live Frame/Pulse
edits. The preview uses a separate submission index and retains the existing
controller fences; see the [current checks and limits](visual_stimulus.md).

Oct15 `live-output-placement` extends the existing authenticated display-calibration
update envelope with a bounded strict output-space placement snapshot under
[G01](../docs/architecture/gui.md#g01)/[V01](../docs/architecture/visual_stimulus.md#v01).
Controller lease, diagnostic/generation/revision, original deadline and increasing
sequence fences are retained; no new controller state owner or command lifecycle
is introduced. The renderer validates complete placement against prepared outputs
and confirms after presentation. Current affected backend/controller362 and GUI52
checks pass, including authenticated placement forwarding/rejection; physical
acceptance remains separate. [Owning assessment/evidence](visual_stimulus.md).

Owner-requested no-Tracking launch is implemented under
[E08 revision173](../docs/architecture/system-contracts.md#e08). Normal launcher and
GUI wrapper accept `--no-tracking`; exactly that role is omitted for the application
lifetime. Ports, credentials, jobs, process descriptors and preview-consumer rings
follow one protected declaration. Contradictory/missing required identities reject;
Tracking-dependent Setup/diagnostics remain unavailable until a full restart.
Configured Tracking-camera preview/recording remains acquisition-owned. Default full
launch is unchanged. ARCH-002 review reuses focused launch/bootstrap helpers without
new dependencies or general optional-backend machinery. Sol6.1 reports1163 affected
owner tests passing (three skips/two native deselections), scoped Ruff/format/mypy and
boundary checks passing. Astra's final review finds nothing actionable. Native process inventories now confirm Tracking absent across controlled launches.
Short recorded trials and120s post-repair reuse pass. The owner stopped the900s retry;
AbortNow at883.852s left it Interrupted, with recording cleanup unconfirmed. The exact
generation's exit receipt confirms all owned processes absent; this does not confirm
recording closure. After the owner resumed testing, a fresh strict no-Tracking run
completes exactly 900 seconds with confirmed cleanup/reuse and all four video counts/
full decodes passing. Reviewed acquisition start/stop repairs pass 523 owner tests.
This is low-loss engineering acceptance: source accounting and remaining CFR repeats
are recorded in Acquisition; zero-loss and physical calibration are not established.
During the pause, original TOML/last configuration were restored and a separate runtime
blocked camera restoration. On resume the rig was idle; fresh configuration, GUI
calibration and camera baselines govern completed restoration: three saved files are
byte-exact, camera feature settings match with only PFS selector-cursor serialization
differences, all camera handles close and the final runtime inventory is empty.
Separate camera-lossless 60-second recording/count/decode and prepared-YUV fidelity
checks pass; source/CFR and fidelity limits remain explicit in Acquisition. Interrupted trial-log
latency and native rapid-Abort reuse remain open as recorded in [Acquisition](acquisition.md).
[Acquisition](acquisition.md) and [Visual Stimulus](visual_stimulus.md) own current
source fixes, failed-attempt assessment, measurements and limitations.
[Commands, attempts and source fingerprints](runtime-evidence-2026-10-15/open-loop-soak/no-tracking-implementation.json).

Oct15 synthetic encoder matrix31/31 cases passes external counts/full decodes,
with actual RTX2080Ti evidence; direct empty raw-input finalization also succeeds.
The [Visual Stimulus report](visual_stimulus.md) owns the workload and performance
limits; [Acquisition](acquisition.md) owns the empty-output capability assessment.

Oct15 projector-free rig verification under [E15](../docs/architecture/system-contracts.md#e15):
native Windows/rig selection25 passed/one symlink-privilege skip; actual Windows picker
selection22 passed with ordinary pytest plugins. Native layout/hover selection5 passed,
one failed because the trial card is326px against a less-than320px assertion; this is
not a confirmed clipping diagnosis. Broad native GUI execution was interrupted after
approximately two minutes without recorded progress; no full-suite pass is claimed.
Prepared native interpreter,90 contract cases,19 Tracking schemas and11 Visual Stimulus
schemas pass. Regenerated the sole stale prepared-trial JSON schema from its canonical
model, removing superseded calibration fields under G01/V15. Native wheel/source build
passes; native binaries and source GLBs are present, without standalone-install proof.

Real COM8 Connect reads protocol4/cephvr2_uno_4 without flashing. Four preview cycles
per enabled Behavior/Tracking camera pass start/stop/release; first-cycle viewers report
visible. An extra Behavior cycle completes, then its next Start is blocked by unknown
SDK-buffer discard accounting. Cause remains unverified; preserve the safety guard.
An exact owned idle-controller fault produces automatic containment and an all-owned-
processes-absent exit receipt; MCU claim release remains truthfully unconfirmed. Active
capture-loss injection did not run: rounded-time identity was safely refused first,
and retry capture was blocked by the reuse finding. Both baseline full camera PFS
snapshots and saved configuration bytes were verified restored after this generation.
SpikeGLX read-only SDK check times out at its saved endpoint; remote state is unknown.
[Dated commands, raw results and limits](runtime-evidence-2026-10-15/projector-free-rig/context.json). Owner defers live-camera Tracking diagnostics and requests leaving the separately opened GUI running; no takeover or shutdown was performed against it.

Git-sync integration (2026-10-15) preserves local pixel-size/offset calibration
under [G01](../docs/architecture/gui.md#g01)/[V15](../docs/architecture/visual_stimulus.md#v15)
and independent incoming camera, arena, appearance and scientific-evidence changes.
Owner explicitly approved this conflict resolution. Direct role-pin editing shares the
existing MCU draft and locks; identity-fenced contextual editing remains. Native display
adapter identity survives scaled desktop rectangles. Invalid existing drafts stay quiet
when mode changes are rejected; an otherwise valid creation with missing subject height
still reports the incoming action-time warning. ARCH-002 review keeps these operations
in their existing focused owners without added state, dependencies or processes.

Final local validation: 1,737 non-GUI tests pass (four skips, 26 native/rig deselections),
509 offscreen GUI tests pass, and the final Visual Stimulus rerun passes327/one deselected.
Ruff and format911 files, Win32 mypy791 sources, boundaries695 modules/zero violations,
114 architecture register entries, 1,575 Markdown targets/anchors, edited JSON/TOML and
whitespace checks pass. Existing cohesive-owner size advisories remain. Superseded
margin/keystone/seam tests follow the retained affine-calibration tests; the older plot-toggle
scenario is covered by the retained interactive-legend regression. Initial failed/partial
runs remain failures, not passes. No native Windows, hardware, optical or workload
acceptance is claimed. [Commands, parent revisions and source fingerprints](runtime-evidence-2026-10-15/git-sync/context.json).

Oct14 full working-tree review under [ARCH-002](../architecture.md#arch-002)
and [E15](../docs/architecture/system-contracts.md#e15) closes local validation:
1,670 backend tests pass (four skips, 26 native/rig deselections), 494 offscreen GUI
tests pass with pytest faulthandler disabled, and 90 contract tests pass. Ruff/format
(902 files), Windows-target mypy (782 files), dependencies, boundaries (686 modules,
zero violations), 114 architecture register entries and declaration/schema checks
pass. Existing cohesion advisories and native exception-hook acceptance remain open.
Review fixes planning preview ignoring G01's restored pixel offsets; preview/export
bounds now agree and reject unresolved/out-of-bounds offsets. A regression fails
before the fix and passes afterward. Corrected accidental projector fields in a
Tracking test fixture, the stale 125 ms acquisition expectation, and a removed
demo-manifest report link. The configuration-confirmation test bridge now respects
the original RPC deadline instead of waiting indefinitely; production timing and
assertions are unchanged. No additional actionable source finding was confirmed
within the reviewed changes. Existing TODO findings/deferrals remain unresolved.

The final Windows wheel and source distribution build successfully; all 57 isolated
Protobuf outputs match source bindings. The source distribution includes both
calibration GLBs and excludes removed modules/demo assets. The wheel contains native
binaries but no repository calibration assets; standalone installation/runtime
acceptance is not established by this build. Initial sandbox suites stalled on
asyncio entry and default-temp packaging failed; permitted loopback tests and an
external writable build temp completed. No device command, flash, projector launch,
application restart or scientific acceptance occurred. Disposable build/cache files
are removed; existing uncommitted changes and dated evidence remain.
[Commands, failures, final results and provenance](runtime-evidence-2026-10-14/working-tree-validation/summary.json).

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

Oct14 repository cleanup under [ARCH-002](../architecture.md#arch-002) removes
766 lines from the retired BatchEdit/EpochTargets, ScreenScope and
StimulusSelectionMenu branches, unused ProjectorLayers state wrapper and shuffle
helper. Source/import searches find no current callers; the unified G01 editor and
shared/tested authoring helpers remain. No dependency, state, contract or behavior
was added. Removed disposable pytest fixtures, bytecode/tool caches and build
outputs; root pytest scratch directories are now ignored. Existing changes,
calibration assets, native/generated sources, environment, recordings, recovery
outputs, toolchain and dated evidence are retained. Owning editor tests pass
12 cases; Ruff, scoped format/Win32 mypy and boundaries pass (686 modules, zero
violations; existing cohesion advisories remain). Broader GUI/client attempts were
interrupted after no progress; fixture-location attempts failed before the final
external-scratch run. No full-suite or rig pass is claimed.
[Commands, counts and provenance](runtime-evidence-2026-10-14/repo-cleanup.txt).

Oct14 rig audit measured queue17 with20% burst margin. Owner subsequently selects queue20, SDK15 per camera and150ms drain allowance; apply through idle Controller UpdateConfiguration/SaveConfigurationHistory and owning TOML. Current/live/saved values match, other current fields are preserved and the open application remains running. New values are not native retested. Original visual TOML remains unchanged. Combined three-camera and dedicated Save Off trials complete/clean/restore and independently decode. Four preview cycles per camera pass; normal ShutdownApplication succeeds with exact all-owned absence. Current regression selections1540 backend passes/five skips and494 GUI passes; Ruff, format906, Win32 mypy786 and boundaries690/zero violations pass. An earlier authenticated timeout passes isolated and final selection; cause unproven. Native layout9/hover2 pass, but full native GUI exception-hook stall/manual DPI acceptance remain open. E05/E06/E08 fixes cover aggregate cleanup, stopped-trial pulse proof and bounded warning scope (E03 revision35); native full cancellation/Abort/idle-reuse checks await projectors. Tracking processing, photodiode and physical paired mappings remain owner-deferred. [Assessment](runtime-evidence-2026-10-14/rig-timing-audit/configuration-assessment.json).

ARCH-002 review removes duplicate selection, reusing the existing focused pulse
owner and camera-role registry; no new state, dependency, process or whole-runtime
reference. The preview orchestration owner is now656 lines and already delegates
start, pulse lifecycle, evidence and transfers. Existing behavior modules cover
all three roles' real resolver/confirmation, start/existing selection across
free/external timing and stopped/running states, plus test-only registry discovery.
Final follow-up local tests: 174 passed, one Windows test deselected across camera
configuration, handoffs, manual preview and manual devices. Scoped Ruff lint and
format (three files), Win32 mypy (two changed sources), boundaries (690 modules,
zero violations with existing size advisories) and whitespace pass.
[Dated evidence](runtime-evidence-2026-10-14/eye-readback/context.json) retains
before/final XML and failed intermediate test attempts. The
[registry follow-up evidence](runtime-evidence-2026-10-14/registry-preview/context.json)
retains an initial existing integration timeout (173 pass/one failure); isolated
recheck and final selection pass without assertion changes, cause unverified.
Additional physical roles still require schema/device/firmware support.
Runtime not restarted;
no camera/MCU command or optical/electrical acceptance performed. Full application
restart is required to load backend changes; [rig checks](rig-verification.md)
remain pending.

Oct14 `mcu-test-console-polling` completed under
[A11](../docs/architecture/acquisition.md#a11) and
[G01](../docs/architecture/gui.md#g01). Owner reports repeated HIGH/count/warning
and command-completion messages after Test. Source review identifies diagnostic
status polling, not repeated START: the existing 500ms polls renew A11's firmware
lease. Retain those polls and live HUD counts; console reports active signal changes
and stop results, while successful routine STATUS completions are quiet in both
device and dashboard consoles. Start/Stop/connection/upload results and failures
remain visible. No serial protocol, lease, timing or output behavior changes.

ARCH-002 uses the existing focused MCU owner for pending command kind and existing
panel/result routing; no dependency/process/helper or whole-runtime reference.
Existing main/panel size warnings reflect composition and presentation ownership;
this patch adds no separable responsibility. Extend the owning dashboard behavior
test: seven polls remain quiet, one START, camera counts refresh, Stop and failed
STATUS remain visible. Offscreen pytest selection
`managed_mcu_pending_completion_and_final_status or successful_tracking_frame_poll`
passes 2 cases/488 deselections. Broader `mcu or microcontroller or
successful_tracking_frame_poll` collection fails twice because concurrently edited
`src/cephvr/gui/projector_calibration.py` is zero bytes and cannot export
`CalibrationTable`; no broader pass claimed or unrelated edit repaired.
Ruff/format (four files), Win32 mypy (three source files), boundaries (690 modules,
zero violations with existing cohesion warnings) and whitespace pass. Initial
import-order/format findings corrected. Reopen the GUI to load this change; no
native GUI restart, hardware command or physical acceptance performed. Existing
[rig checks](rig-verification.md) remain pending.

Oct14 `projection-integer-physical-views` completed under
[G01 revision203](../docs/architecture/gui.md#g01),
[V14](../docs/architecture/visual_stimulus.md#v14) and
[V15 revision19](../docs/architecture/visual_stimulus.md#v15).
Width/Height are integer pixel entries with visible arrows and Up/Down one-pixel
steps. Remove Offset. Numeric7/full10/review5 migrate older offsets/fractional valid
sizes while retaining reference measurements, native modes, inversions and distances.
The centered usable view dimensions equal valid pixels times independent measured
X/Y mm/pixel. Preserve the frame-placed physical plane center, observer and axes;
measured physical dimensions retain the 5 mm gap placement reference. Preview,
calibration export and prepared affine mappings share the focused extent helper.
Prepared GUI affine surface textures use valid pixel resolution, keeping V14
physical texture sizes/frequencies and shared phase independent of projector resolution.
Live diagnostics retain the protected scene and fixed pitch while changing crop bounds;
fresh preparation publishes usable physical views. Imported warps/targets retain
original geometry/resolution. Raw reference frames/bars bypass stale measurements/crops.

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

Oct14 `updated-tank-screen-plot` completed [gui] [visual_stimulus]: production
corner geometry plotted with updated5mm gaps and Bottom126×94 image axes.
Retained side distances imply4mm lateral clearance; measurement reconciliation
remains open. No settings/runtime/device change. See the
[plot assessment](visual_stimulus.md) and
[3D/top/side figure](runtime-evidence-2026-10-14/tank-screen-plot/tank-screens.png).

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
[G01 revision197](../docs/architecture/gui.md#g01). Derived projector distances now
show exactly one decimal millimetre, eliminating float-tail display artifacts;
reference inputs, mm/px and measured base mapping precision remain unchanged.
Confirmed reference bars display Close on their own button and disable projection
launch; confirmed frame/grid displays Close on projection launch and disables
reference launch. The corresponding action emits the existing close request;
wrong-step direct calls and pending/unavailable states emit nothing. Unknown active
view retains the existing projection Close fallback. Labels remain confirmation-driven.

ARCH-002 retains focused measurement formatting and calibration action owners,
without new state/dependency/process. Owning GUI selection13 passes/467 deselections,
including precision/roundtrip, both Close routes, pending guards, live editing and
measured affine mappings. Initial selection5 passes/one stale old-button assertion;
update the owning expectation and correct formatting. Ruff/format3, Win32 mypy2,
boundaries689/zero violations and whitespace pass. No native GUI restart/output
command or optical acceptance in this increment; reopen the GUI to load changes.
[Evidence](runtime-evidence-2026-10-14/calibration-controls/context.json).

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
[G01 revision194](../docs/architecture/gui.md#g01). Shared native projector window
configuration disables GLFW fullscreen cursor centering on every creation/recreation;
controller ownership and lifecycle guarantees remain unchanged. Rendering/calibration
tests71 pass; scoped static checks and boundaries pass. Native GUI launch, Close and
reopen preserve the exact clicked main-display coordinates, with authenticated
Active/presented → Idle/resources_closed → Active/presented status. Reference bars
remain open. The owner authorizes resuming the accidentally interrupted Computer Use
check; reopen the closed GUI in the current controller generation. See the owning
[Visual Stimulus assessment](visual_stimulus.md) and
[raw evidence](runtime-evidence-2026-10-14/projector-cursor/context.json) for commands,
attempts and limits. No optical/full-workload acceptance is claimed.

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

Oct14 `projector-flip-deferred` completed locally under
[A11 revision46](../docs/architecture/acquisition.md#a11),
[G01 revision191](../docs/architecture/gui.md#g01) and E14 revision209.
Owner explicitly defers Projector flip input, its diagnostics and camera-trigger
offsets. Remove Inputs/Add input and new SpikeGLX flip source; retained hidden
legacy draft fields migrate enablement to false, preserve the pin and cannot emit
an activation/test command. Configuration and connection edits reject enabled
legacy input fields; serial-owner/diagnostic parser reject the kind before work.
Firmware removes input interrupt setup/cleanup and rejects the kind. V20's three
modes remain independent. Remove default D2 assignment; Microcontroller policy,
config and loader version3/digest agree and count only generated output transitions.
No firmware upload, device command or running-runtime restart occurred.

ARCH-002 reuses existing signal, validation, serial and firmware owners; delete
unsupported signal actions/interrupt work rather than adding alternate behavior.
Compatibility fields remain inert; existing panel/serial/device composition remains
cohesive with no dependency/process/runtime reference. Backend owner/protocol/config
122 pass/one existing skip; focused GUI11 pass; Ruff/format15 files, Win32 mypy11
sources and boundaries688/zero violations pass. Uno compile uses13590 flash/1199 RAM
bytes. Initial partial edit stopped before owner write due to an unmatched source
anchor; reread and completed it. Correct policy digest using Decimal parsing, stale
input-test expectations and a mypy variable-name collision. Sandbox backend and
broader GUI runs were interrupted on transport/modal stalls. Permitted broader GUI
also stalled; no broader pass claimed. Broader controller device admission14 pass/
three calibration-open/close failures in concurrently changing calibration workflow;
these are outside the MCU request path and remain with current calibration work.
[Commands/results](runtime-evidence-2026-10-14/projector-flip/context.json).
Output electrical acceptance stays in the [rig checklist](rig-verification.md);
Projector flip is explicitly deferred rather than a pending implementation test.

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

Oct14 `gui-description-cleanup` completed locally under
[G01 revision189](../docs/architecture/gui.md#g01). Audit all GUI label constructors:
remove explanatory body text in protocol insertion/condition/expanded-example forms,
custom motion/looming editors, retained-review/Stop dialogs and empty Tracking
annotation. Useful instructions move to existing control tooltips. Keep functional
captions, units, generated counts, live frame identity, status/errors and operator
choices. The custom forms retain their controls/data paths; annotation captions show
only after a real reference/frozen source is installed. Earlier camera/projector
card removal is retained; concurrent synchronization cleanup already removed its
wiring summary, so preserve that independent change.

ARCH-002 deletes redundant widgets/update calls through existing focused owners;
no shared blanket QLabel hiding, dependency, process or runtime state. Existing
oversized parameter composition retains only one fewer orchestration call. Extend
no tests for reversible text removal; adapt the existing scope-tooltip assertion.
Owning regressions initially pass61/408 deselected with one asset fixture error:
the concurrently updated generator requires samples outside the checkout. Retry
only that case with ordinary external pytest temp: one pass/469 deselected. No
production behavior is weakened. Scoped Ruff/format11 files, Win32 mypy10 sources,
boundaries687/zero violations and whitespace pass. Initial source-edit attempt
finds the synchronization label already removed by concurrent work and stops before
code writes; re-read and continue with remaining owners. No GUI restart, device
command or native/rig acceptance. [Local evidence](runtime-evidence-2026-10-14/gui-descriptions/context.json).


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

Oct14 `calibration-card-descriptions` completed locally under
[G01 revision188](../docs/architecture/gui.md#g01): remove description/prerequisite
labels from Pixel-to-mm and Screen calibration cards. ARCH-002 removes the now-unused
CalibrationPrerequisites class and refresh wiring; retain the shared no-projector
availability message and existing launch validation. No new state/dependency.
Standalone QApplication/ProjectorsPanel probe confirms descriptions absent and
reference launch button retained at index1. Scoped Ruff/format2 files, Win32 mypy2
sources, boundaries687/zero violations and whitespace pass. Initial import/format
findings corrected using repository Ruff configuration. No new test for this
reversible presentation removal; no running GUI restart/device/native acceptance.
Preserve concurrent calibration-asset and other GUI work.


Oct14 `device-card-and-signal-removal` completed locally under
[G01 revision187](../docs/architecture/gui.md#g01). Rename camera inventory to
Available cameras and remove the explanation below its buttons and unused summary
formatter; contextual wiring tooltips remain. Every MCU input/output supports Remove;
clear the pin, disable fixed Trial-state/Projector-flip signals, hide unassigned rows
and empty headers using DataTable's existing fit_rows. Add input/output offers missing
supported signals and asks for the explicit pin; fixed I/O readdition enables it.
Camera removal preserves Cameras' Use/role/source/rate and inventory. Enabled external
trigger cameras still require a valid pin under A10 (validation_pulse.py); removal
leaves an incomplete draft until reassigned rather than switching the timing source.
Snapshot format remains unchanged: empty pins represent absent assignments.

ARCH-002 review keeps presence/editing in the focused MicrocontrollerSignals helper,
removes obsolete camera explanation state, and reuses tables/configuration/authority
locks without dependencies, backend state or runtime references. Existing oversized
panel remains composition; separable signal behavior stays in its helper. Seven
owning GUI cases pass/461 deselected, covering remove/readd, all-empty headers,
snapshot restoration, unchanged camera choices and active-test editing locks.
Scoped Ruff/format5 files, Win32 mypy4 sources, boundaries687/zero violations and
whitespace pass. Existing no-faulthandler/loopback test allowance retained. No physical
device action or running GUI restart; native layout/device acceptance remains E15.
[Commands and local evidence](runtime-evidence-2026-10-14/signal-removal/context.json).


Oct14 GPU-selection launch repair under [SYS-002](../architecture.md#sys-002) and
[E08](../docs/architecture/system-contracts.md#e08) uses separate verified renderer
and GUI/CPU executable identities with per-image preferences applied/read back before
creation. Preserve native plans, PID/creation-time checks, Job Objects and deadlines;
actual GPU checks remain authoritative. AMD GUI/RTX5060Ti renderer hidden probes and
four-output native Idle startup pass; saved GUI draft restores/control is held.
The [Visual Stimulus assessment](visual_stimulus.md) records the485-case integration,
native provenance check, historical failure and acceptance limits. Encoding/OF bindings
remain unchanged; no global or other-application GPU preference is modified.

Oct14 `mcu-continuous-pin-test` is implemented locally under [G01 revision186](../docs/architecture/gui.md#g01) and [A11 revision45](../docs/architecture/acquisition.md#a11). Test requests duration_ms=0 and runs until explicit Stop. Matched DIAG_STATUS every500ms renews a two-second firmware communication lease without restarting pulses/resetting counts; expiry leaves outputs LOW/input detached and cannot revive on a late poll. Existing camera watchdog and authority/phase/shutdown cleanup remain. Firmware cephvr2_uno_4 accepts continuous and legacy2000ms requests; old firmware rejects without bounded fallback. No upload, serial/device command or runtime restart occurred.

ARCH-002 review reuses existing serial owner, firmware state and GUI timer, without dependencies/processes/runtime references. Existing owner/panel size advisories remain cohesive serial ownership/widget orchestration; no separable responsibility added. Controller/protocol105 passes/one skip; four existing GUI cases pass/464 deselected, including five-second active observation,500ms polling and manual Stop dispatch. Scoped Ruff/format6 files, Win32 mypy4 sources, boundaries687/zero violations and whitespace pass. Uno compile uses14038 flash/1219 RAM bytes. Sandbox asyncio tests stall and are interrupted; permitted focused tests pass. Broader GUI selection stalls after one dot and is interrupted; no broader pass claimed. Sandbox Arduino lacks core/index; permitted installed-core compile passes without upload. Physical sustained pulses/lease expiry remain in the [rig checklist](rig-verification.md). [Local evidence](runtime-evidence-2026-10-14/mcu-continuous/context.json).


Oct14 `projector-calibration-card-order` completed under
[G01 revision185](../docs/architecture/gui.md#g01): Pixel-to-mm calibration now
appears above the projection correction card in Devices/Projectors' Screen
calibration tab, matching the owner's workflow. ARCH-002 review uses only the
existing composition layout order; no extra module, dependency or state is needed
in the oversized Projectors composition owner. A local QApplication/ProjectorsPanel
probe confirms measurement/correction layout indices0/1. Scoped Ruff/format and
Win32 mypy for projectors.py pass; boundaries687/zero violations (existing cohesion
advisories) and whitespace pass. No managed GUI restart or physical calibration
acceptance ran; no new test is added for this reversible layout-only change.

Oct14 `projector-legend-visibility` completed locally under
[G01 revision184](../docs/architecture/gui.md#g01): Devices/Projectors removes the
four plot toggle buttons and their unused styling. Clicking Tank, Screens,
Projection or Subject in the legend toggles the corresponding view group.
Hidden entries remain dimmed and clickable, including without rig geometry;
wrapped hit regions retain their positions when groups are hidden. Projection
continues grouping projectors, rays, footprints and mirror. Visibility survives
refresh/phase changes without editing calibration or participation; legend clicks
do not start rotation. Plot dragging and double-click reset remain available.

ARCH-002 review removes redundant controls and keeps interaction/hit regions in
the existing focused TankDiagram owner, with no dependency or runtime reference.
The existing oversized Projectors composition module shrinks; its remaining
assignment/calibration orchestration stays with existing focused helpers.
Five owning GUI/geometry/rotation cases pass; scoped Ruff/format (four files),
Win32 mypy (three sources), boundaries687/zero violations and whitespace pass.
Initial wrapped-legend test fails because the parent layout overrides resize;
fix the test width constraint, then verify wrapped toggling/refresh/rotation.
GUI tests use the documented `-p no:faulthandler` limitation. No managed GUI
restart, device command or native visual acceptance is claimed.
[Commands and local evidence](runtime-evidence-2026-10-14/projector-legend/context.json).

Oct14 `projector-offline-drafts` under
[G01 revision183](../docs/architecture/gui.md#g01) and
[E07 revision62](../docs/architecture/experiment.md#e07): disconnected saved display
identities no longer reject GUI snapshot saving/restoration. Retain assignments,
participation, calibration and enabled authoring faces independently of live inventory.
Existing controller pure validation accepts structurally valid saved output properties
without device discovery; unknown physical properties are not invented. Empty inventory
shows the availability explanation in the diagram, device HUD and log, including the
turn-on/refresh prerequisite for projector tests/Setup. Managed Setup refreshes inventory
on click and logs the reason without collecting/submitting configuration or dispatching
Setup when none are found. Ordinary authority/phase gates and backend physical validation
remain intact; the Setup button is clickable with control in Configuration.

ARCH-002 review removes the erroneous live-inventory snapshot check and reuses existing
draft ownership, display discovery, command routing and focused prerequisite text owner.
The oversized main/projector modules add only orchestration/presentation wiring; no new
dependency, process, duplicate state or whole-runtime reference. Owning GUI regressions
pass23 cases; surrounding projector/calibration/Setup/full-GUI checks pass86 with the
existing narrow projector15px overflow failure. Loading unchanged HEAD projector/layout
modules in an isolated test process reproduces that same failure. Scoped Ruff/format6
files, Win32 mypy5 sources, boundaries687/zero violations and whitespace pass. Initial
sandbox asyncio setup stalls in socketpair accept and is interrupted; permitted tests
run normally. Initial test-only numeric normalization/button lookup/pacing-fixture
expectations are corrected before final23 passes, without changing production behavior
to satisfy them. Existing no-faulthandler/native-picker limitation remains.

The prior GUI was already closed; same-generation `--reopen-gui` opens current GUI
PID31324, responsive on Windows. Controller/session/backends remain intact. Projectors
are still on; physical power-off/save/Setup/reconnect acceptance remains in the
[rig checklist](rig-verification.md).
[Commands, provenance and results](runtime-evidence-2026-10-14/gui-refresh/projector-offline-context.json).

## Protocol group headings and arena Advanced settings

`protocol-group-and-arena-settings` is implemented under [G01](../docs/architecture/gui.md#g01)
revision191 and [V16](../docs/architecture/visual_stimulus.md#v16) revision5. Selected group
labels the timeline parameter row; group names sit above blocks, with repetitions/duration
inside. The longer footer label preserves a readable repetitions field at narrow widths.
Advanced settings put trial-owned wall limits first, followed by aligned Initial position
XYZ and Orientation yaw/pitch/roll sections with plain numeric inputs and no selectors.
All arena inputs share the same equal column stops: Movement limits aligns with Position,
wall clearance with Orientation; descriptive text spans both columns.
Imported condition values remain read-only references rather than being flattened. New arenas start at X/Y=0, with Z copied
from the configured subject height and zero orientation (forward, level horizon). Missing
subject height blocks new-arena creation. The mode switch validates this prerequisite
before changing active mode, preserving previous controls/selection and presenting an
action-time warning. This repairs the reproduced empty 3D row with erased error after
a failed height check. Later rig edits preserve existing authored poses.
These fields reuse the existing planar pose plus fixed height/pitch/roll model. Arena limits default to declared arena-file geometry and
30 mm clearance, preserve explicit saved regions/unrestricted mode, and participate in
snapshot restoration and Undo/Redo. Invalid clearance blocks navigation/save. The editor
shows declared asset bounds as a preview; protected preparation owns effective geometry.
See the [Visual Stimulus implementation assessment](visual_stimulus.md#arena-file-movement-regions)
and [native/rig worklist](rig-verification.md).

ARCH-002: initial-pose form assembly, trial boundary controls and bounded metadata access
are focused helpers; no new dependencies or process ownership. Existing cohesive source
warnings remain for canonical Protocol selection/history, timeline paint/input, parameter
binding and protected resource session ownership; geometry parsing/resolution lives outside
them. Extend owning dashboard/compiler/resource test modules rather than per-fix files.
Current mode-failure/default/gain checks: five owning cases pass. A pre-fix offscreen probe
reproduced 3D arena selected, no arena controls and an empty error string. The regression
verifies previous-mode/program preservation, a visible warning, successful retry with
configured height, asset chooser availability and returning to per-projector editing.
Scoped Ruff/format two files, Win32 mypy one source and boundaries696/zero violations pass.
The earlier aligned layout capture remains at
[aligned capture/context](runtime-evidence-2026-10-15/protocol-arena-settings/aligned-advanced-context.json).
Earlier group/region and aligned-pose evidence remains in the dated evidence directory and LOG.
No full GUI/native Windows/rig or production-shutdown acceptance is claimed.



## Post-hoc alignment readiness after always-saved evidence

Oct14 source/schema audit under [SYS-004](../architecture.md#sys-004),
[A09](../docs/architecture/acquisition.md#a09), [E12](../docs/architecture/synchronization.md#e12)
and [V22/V28](../docs/architecture/visual_stimulus.md#v22), accepting first matched
camera trigger = source of first recorded video frame. No post-change rig dataset
was validated; this is implementation evidence, not recorded-pulse proof.

Camera schema4 retains source IDs/host receipt/native counters and timestamps,
clock/counter descriptors, invalid/drop dispositions, explicit video-source mappings,
cutoff/pulse/transport/completion evidence independently of video. Stimulus format5
retains actual group state, per-output submissions/marker index+level, diagnostics,
feedback and completion with recipe identities/provenance. Paired SESSION_CONFIG
retains SpikeGLX run/directory, streams/rates/saved-channel indices and pulse mappings.

Eye inventory support is implemented under E12 revision21: additive enum7 and
`eye_tracking_camera` TOML/GUI mapping, including saved draft restoration and
SESSION_CONFIG serialization through the existing preparation. Paired Setup requires
Eye only when acquisition and Eye are enabled and externally triggered; missing,
non-OneBox or unsaved required mappings fail before run-name mutation. "Eye tracking"
is classified separately from Tracking in the GUI. No assigned channels, wiring,
trigger cadence, native counter semantics or acquisition settings changed.
ARCH-002 review: extend existing focused inventory/validation/panel modules and owning
behavior tests; no dependencies, new state or extra coordination. No fixed policy
values changed; the config addition is a commented operator mapping example only.
Local checks: controller/client suite490 passes with14 loopback setup errors from
sandbox socket restrictions; the authorized authenticated RPC rerun passes all15.
Final SpikeGLX tests35 pass (including nested Eye TOML editing), focused GUI tests13
pass/466 deselected. Protobuf generation19 sources, Ruff check/format15 files,
Win32 mypy13 source files and boundary check690 modules/zero violations pass.
Existing size warnings are outside the touched modules; no cohesion exception added.
An initial new-test helper import error was corrected before these passing runs.
Rig verification remains open in the [paired checklist](rig-verification.md).

Remaining concrete gaps:
- Checked-in synchronization pulse_inventory has no assigned channels. Supply actual
  stream/acquisition-channel/digital-bit mappings for the camera triggers, enabled
  photodiode and trial-state/projector-flip signals in use; do not copy legacy columns.
- No explicit shared-sync association binds OneBox to each probe. Retain original
  native bin/meta files, segment identities and actual common-waveform channel/bit
  semantics on both ends. Existing custom mappings/native metadata may carry pieces;
  CephVR does not require or verify the cross-stream relationship. Generic digital-bit
  validation covers DW, not SY words, so a SY-bit mapping is not currently representable
  through that validated path. Need actual rig sync inventory before selecting fields.
- Native camera descriptors allow unknown reset/wrap semantics and generic "frames"
  counter semantics; the first anchor does not prove recovery after missed triggers,
  dropped SDK frames or reset. Review retained timestamps/counter gaps; unresolved
  correspondence stays unresolved. No stronger anchor is requested.
- Photodiode markers are recorded, but periodic60-submission landmarks are not absolute
  IDs and held levels supply no internal edges. The measured output is the selected
  photodiode display; other displays have host submission evidence, not independently
  measured optical onset. These are timing/recovery limits, not missing source rows.

Trial-to-pulse-train selection and raw-file completeness remain compiler prerequisites;
no per-trial OneBox edge index is needed in the acquisition output when uniquely
recoverable from recorded gates/trains. Alignment tables, clock fits and quality labels
belong to the owner's future compiler. Tracking result files remain controlled by
save_tracking_data; enable it if complete locomotion histories are required.


Oct14 owner-requested repository cleanup under [ARCH-002](../architecture.md#arch-002)
removes423 files/254291141 bytes from the current tracked tree:136 images,260
captured-run dataset files,13 obsolete source/document-editing probes and14 other
build/run artifacts, including locally generated native DLLs. Original local files
and assessed evidence are preserved. Image/video ignore rules apply throughout the
repository; historical commits stay unchanged, as explicitly selected by the owner.
The [cleanup inventory](runtime-evidence-2026-10-14/repo-cleanup/context.json)
records original paths, sizes, SHA-256 hashes and local-only storage. Screenshots,
recording datasets, archived packages and old one-shot edits listed there require
local access; summaries, contracts, logs and substantive verification records stay
tracked. Existing screenshot/archive hyperlinks now identify local-only evidence.

The nine demo PNGs are generated on demand from a small standard-library tool and
source descriptors. The GUI/Visual Stimulus tests use one shared temporary fixture,
so a fresh checkout needs no checked-in images. No backend runtime code/state,
scientific policy, native C++ source or dependency is removed. The two native DLLs
remain on the rig; fresh checkout builds use the existing documented flags.
Six affected GUI/resource tests pass; full source/test/tool/script Ruff, Win32 mypy
for the two new helper/fixture files, and boundaries687/zero violations pass.
The no-isolation wheel/sdist build passes and archive inspection confirms neither
contains images/videos; the sdist includes the generator and four JSON descriptors.
Initial sandbox build fails on temporary-directory permission before the permitted
replacement succeeds. This is packaging/fixture validation, not rig acceptance.
Concurrent GUI-refresh work and its projector-availability finding are preserved.

Oct15 Review-only style experiment (`gui-retro-console-style`) under
[G02 revision47](../docs/architecture/gui.md#g02): Style → Standard / Retro console
switches the Review Dashboard and window chrome live, with a local appearance
preference. Green-black surfaces, blue borders/actions, muted red-orange card titles,
cyan page headings/field labels, restrained amber branding, pale green readouts/logs, cyan navigation/focus,
warm stop accents, unnumbered uppercase card headers, aligned HUD columns, square
controls/frames, bracketed status lamps and static faint terminal lines with edge
graduations use the shared theme. Periodic longer ticks extend to card edges;
Dashed section rules remain only inside the HUD; cyan corners mark focused inputs.
A segmented strip shows exact trial position when a count exists (up to24 visual
segments), without claiming completed trials. Lamp colors reflect the current view, with a
subtle halo; exact statuses remain in captions/tooltips. No embedded plots are added. Runtime retains
Standard without a style selector. Existing widgets, drafts (including invalid
unfinished values), actual log/status text, authority gates and experiment snapshots
are preserved. ARCH-002 review parameterizes the existing stylesheet and adds a
focused Review menu/preferences component, with no new dependency or runtime owner.
Existing source-size advisories are outside these small cohesive changes.
Seven focused appearance/theme/Standard-parity cases and eight log/HUD/navigation/
draft-retention cases pass offscreen; GUI Ruff/format163 files, Win32 mypy161 sources
and boundaries695 modules/zero violations pass. Wide1440 and narrow720 captures
are visually inspected; returning to Standard produces identical captured pixels.
[Dated method/results](runtime-evidence-2026-10-15/retro-console/context.json) retain
source hashes and the capture method; PNGs are local-only ignored evidence.
No native Windows or rig run. The owner explicitly limits the experiment to Review.
The current terminal-marking refinement (`gui-retro-terminal-markings`) passes ten
owning appearance/theme/HUD/Standard-parity cases (477 deselected), scoped
Ruff/format5 files, Win32 mypy4 sources and boundaries696/zero violations. Existing
appearance coverage verifies field/combo focus, mouse-transparent brackets,
continued typing, unchanged drafts/logs/gates, live statuses and hidden/zero/mid/last/
large-count trial positions. Standard restores and Runtime stays unchanged.
Wide/narrow, focused-input and active-trial captures are visually inspected;
Standard round-trip pixels match. ARCH-002 review extracts existing terminal
painting into a focused retro instrument module with the new static decorations,
editor-owned overlays and scalar-fed position widget; no new dependency, timer,
experiment state or test module. Shared components stay below500 lines; remaining
source cohesion advisories are pre-existing unrelated areas.
Fresh native Review launched through scripts/start_gui.py (session10674), retaining
earlier windows. Native accessibility verification remains unavailable for this
Python app; no native Windows/rig acceptance.
The main-card divider removal (`gui-retro-hud-only-divider`) deletes the unused
section-anchor plumbing. Scoped Ruff/format and Win32 mypy2 sources pass, with
boundaries696/zero violations; the wide render confirms no card divider and the
HUD rule retained. Standard round-trip pixels still match. No new tests for this
cosmetic removal. Fresh Review launched (session71475).
[Current capture evidence](runtime-evidence-2026-10-15/retro-console/hud-only-divider/context.json);
[earlier source/method/results](runtime-evidence-2026-10-15/retro-console/terminal-markings/context.json);
[earlier instrument detail evidence](runtime-evidence-2026-10-15/retro-console/instrument-details/context.json)
and [palette evidence](runtime-evidence-2026-10-15/retro-console/card-title-accent/context.json)
are historical.

Oct15 current Runtime/Review parity (`runtime-review-gui-current-parity`) under
[G01](../docs/architecture/gui.md#g01) and [ARCH-002](../architecture.md#arch-002):
both entry points resolve to this checkout and inherit the same DashboardWindow;
no separate layout or stale source copy was found. Extend the existing owning
parity regression through all five stimulus families with Advanced settings open,
comparing visible labels, editors, buttons and their positions/sizes, including
arena initial pose and movement limits. Preserve mode-specific menus, authority,
device discovery and separate local draft files. No production layout changes or
dependencies were needed; existing source-size advisories do not require extending
those modules. Validation on macOS with QT_QPA_PLATFORM=offscreen and
`-p no:faulthandler`: four wide/narrow, authority variants pass; twenty focused
camera pin/contextual wiring, group editor, arena limits, advanced-family and
runtime draft close/reopen cases pass. GUI Ruff/format and Win32 mypy (160 sources)
pass; boundaries check694 modules/zero violations. Tested the dirty working tree
based on `0d70295898bcb9f058ef4bf26df4680df62d595d`, retaining concurrent changes.
These are source/composition checks, not native Windows or rig acceptance. Existing
open processes were not refreshed; reopening each GUI loads the current source.

Oct14 rig GUI refresh (`runtime-gui-source-refresh`) under
[G01](../docs/architecture/gui.md#g01),
[E08](../docs/architecture/system-contracts.md#e08) and
[E15](../docs/architecture/system-contracts.md#e15): Review and Runtime already
inherit the same DashboardWindow; the rig editable install resolves this checkout.
Regenerated 19 Protobuf sources with no tracked binding changes and installed the
missing declared Pillow12.2.0 dependency. All20 declared runtime dependencies
match current requirements. Existing owning GUI checks pass14 cases, including
wide/narrow Review/Runtime parity, contextual wiring, managed editing and full-draft
close/reopen; launcher tests pass46. Boundaries687/zero violations. Initial sandbox
test attempt passes7 with7 temporary-directory fixture errors; the repository-local
temporary-directory rerun passes all14. The initial sandbox package install lacked
DNS; the permitted install succeeds. Tests use `-p no:faulthandler` for the GUI
under the previously recorded native exception-hook limitation; no full/native suite
or scientific acceptance is claimed.

Reopened the GUI through the existing launcher, then performed the owner's explicitly
approved full replacement through E08's exact owner event/exit-confirmation path.
The new controller16297497-8a48-4a38-866a-f21c52339bf2 and supervisor
575eb577-487e-4737-b768-3afa49d6c574 run current source with newly launched
acquisition, Visual Stimulus, Tracking and GUI. Authenticated status confirms
Configuration/revision1; Windows inspection confirms a responsive Dashboard.
Native UI inspection confirms the updated shared cards and compact retained review.
The initial unavailable-projector blocker is resolved after owner power-on:
all four saved DLP identities enumerate at60Hz. A further approved E08 replacement
starts controller87ca3771-29f3-41db-bfdc-31ec13491f0f; native GUI confirms saved
settings restored as a local draft, Control held and enabled Setup without startup
dialogs. Four renderer outputs report resources ready, applied revision1 and returned
Idle submissions without initialization issues. Leave runtime session73592 open;
no settings were reset and no experiment was started. This confirms restoration
and native initialization, not measured calibration or optical/full-workload acceptance.
[Power-on recovery evidence](runtime-evidence-2026-10-14/gui-refresh/projectors-on-context.json).
[Evidence/provenance](runtime-evidence-2026-10-14/gui-refresh/context.json)
retains test results and pre/post-replacement status; remaining acceptance stays in
the [rig checklist](rig-verification.md).

Oct13 sidebar cleanup under [G01 revision181](../docs/architecture/gui.md#g01)
removes the full-GUI Load/Save buttons. Snapshot/history ownership and per-page
file controls remain; restore errors no longer recommend the removed button.
ARCH-002 review keeps the change in window composition and its existing history
message. Offscreen visibility probe passes after selecting Protocol; initial probe
incorrectly checked a control on a hidden page. Scoped Ruff/format, Win32 mypy2
sources, boundaries683/zero violations and whitespace pass. Existing native preview
processes have not been restarted; no device or rig actions.

Oct15 `camera-inline-mcu-pin` implements the owner's inline pin field beside
Cameras' trigger frequency under [G01](../docs/architecture/gui.md#g01).
The Microcontroller role row remains the single draft owner: user edits, table
clearing, role/selection changes and MCU file restoration synchronize the displayed
pin. Unassigned cameras have no editable pin; capture, authority, phase and pending
MCU operation locks retain their existing scope. Pin edits retain Use and timing
choices and enter the existing MCU submission/save path. ARCH-002 review removes
the obsolete camera wiring dialog and its camera-specific stale-save branch;
existing camera/MCU presentation modules only add a field and refresh notifications,
with Devices owning synchronization. No new dependency, policy, schema or runtime
state owner; these cohesive presentation modules retain their existing size warnings.
Offscreen layout inspected at 1100×760: pin field sits beside rate without overflow.
Validation: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
 tests/gui/test_dashboard.py -q -p no:faulthandler -k "camera_pin or contextual_wiring
 or cancelled_projector_wiring or microcontroller or camera"` passes81/402 deselected.
Scoped Ruff check/format and Win32 mypy3 sources pass; boundary check690 modules/zero
violations and edited Markdown links/whitespace pass. Optional aggregate GUI run was
interrupted after focused completion and emitted a failure marker before exit134;
no aggregate pass or diagnosis is claimed. A sandbox restriction prevented process
listing for an earlier stop attempt; the owned tool session was interrupted directly.
Native Windows/device acceptance remains in the [rig checklist](rig-verification.md).

Device workflow refinement (`device-wiring-drafts`) under
[G01](../docs/architecture/gui.md#g01) and
[E07](../docs/architecture/experiment.md#e07) separates wiring from camera/display
participation. MCU owns logical Behavior/Tracking/Eye pin drafts independently of
inventory; the inline Cameras pin field and contextual Projector editor update that
same owner. MCU v3 files
and review v2 drafts preserve role wiring without changing Use, with explicit legacy
migration. Unfinished GUI settings survive polling; selected identity tests omit
PFS/import/capture, MCU connection checks submit only their port, and manual camera
preparation preserves participation and recording choices. Focused exact-diff
connection/selected-camera validators retain unrelated state, active conflict checks,
authority/revision/ownership guards and full Setup validation. Selected-camera
validation uses an action-only copy; actual stored Use/recording flags never change.
ARCH-002 keeps these validators, contextual editor and projector prerequisite hints
in focused helpers with existing owner interfaces and no new dependencies. Existing
large main/bridge, MCU panel and projector panel remain their respective composition,
command-routing and presentation owners; new validation/editor/hint logic is separate.
Aggregate review also corrected the compact group footer label so repetition fields
remain readable at narrow widths, without weakening the existing width assertion.
Root controller regression passes251 cases; acquisition manual-device/preview
regression passes101 with one platform/rig deselection. Scoped controller Ruff/format
and Win32 mypy5 sources pass. Final GUI aggregate passes463 with one obsolete
caption assertion; correcting that assertion gives four related layout passes,
covering the remaining case without further production changes. All464 GUI cases
are accounted for across those runs; an all-green aggregate rerun is not claimed.
GUI Ruff/format157 files and Win32 mypy156 sources pass; boundaries686/zero violations,
document links and whitespace pass. Luna implementation, Sol6.1 integration and
Astra main/final review find no remaining blocker. Initial migration/type failures,
stale assertions and their corrections remain with the [raw evidence and provenance](runtime-evidence-2026-10-13/device-wiring-drafts/context.json).
Offscreen production-widget layouts were inspected and the native Cocoa sample GUI
launched with isolated temporary settings (session71109, visible confirmation).
Native device/electrical/full-load checks remain in the [rig checklist](rig-verification.md).

Oct13 readable GUI messages (`gui-readable-runtime-messages`) under
[G02](../docs/architecture/gui.md#g02) and [E03](../docs/architecture/gui.md#e03):
automatic reconnect/launch review now excludes exact current completed/valid
nonfatal configuration notices and explicitly completed recoveries with completion
evidence and no failure. Errors, runtime incidents, pending choices, failed or
unknown terminal operations, unresolved recoveries and all other warnings still
require review. Ordinary pending commands, routine success history and truncation
alone do not trigger it; empty reconnects no longer force a review. Warning has no
severity field, so classification uses exact source evidence rather than keywords.
Full history remains available through Review controller history, with no added
control gate. An already-open important review remains fenced to its connection
until acknowledged, including when a later same-connection snapshot is empty.
Luna implementation, Sol integration and Astra final source review pass. Final18
focused review/history/control tests pass; scoped lint/format, Win32 types and
boundaries676/zero violations pass. The broader GUI run records461 passes and one
concurrent demo-texture failure: its already-loaded test tried decoding JSON as an
image while the texture chat changed the fixture/manifest. That case passes its
current-source rerun; no fresh complete-suite pass is claimed.
[Filter evidence](runtime-evidence-2026-10-13/readable-gui-messages/important-only/context.json)
retains both runs and their scope. The local sample preview confirms routine
history starts without an automatic dialog, with explicit buttons for history/important examples.

The themed, icon-free reconnect review groups retained errors, recoveries, incidents, pending
choices, warnings and operations needing attention. Routine successful operations
appear as a count; the 540×400 dialog uses bold accented category headings and a
vertically scrollable summary with only Copy details
and Continue. Copied plain-text details preserve exact command identities,
diagnostics and bounded-history omissions. Copy details
copies every currently retained error and operation, including entries beyond the
former routine-history display limit, from the latest snapshot.
Only Continue acknowledges the exact connection; copy and dismissal
do not acknowledge or send a controller command. Activity entries use readable action
names and concise outcomes, with exact diagnostics available through View details
and Copy details in the entry context menu. Admission remains explicitly pending
completion; acknowledgement identity, control authority and log retention/scroll
ownership stay unchanged. ARCH-002 review keeps formatting in the existing focused
snapshot/console owners without new dependencies or runtime back-references.
The larger main/bridge modules only route existing signals and outcomes; no new
state ownership is added. Tracked calibration, inventory, Tracking and control-release
operations no longer fall through to a contradictory generic success message;
successful Tracking frame polls stay quiet while completion handlers still run.
Duplicate MCU failure rows are removed. Luna implementation, Sol integration and
Astra source/screenshot review found no remaining blocker. Four themed offscreen
screenshots verify grouping, literal text and readable detail panes. A direct Qt
popup-interaction test crashed; the replacement render exercises the actual detail
constructor with popup selection substituted, so native mouse/keyboard input is
not claimed verified. The original log/grouping repair's offscreen GUI regression
passes452 tests; Ruff check
and format pass155 files, Win32-target mypy passes153 sources, and the boundary
check reports667 modules/zero violations with existing cohesion advisories.
Local links and whitespace pass. [Commands, provenance and screenshots](runtime-evidence-2026-10-13/readable-gui-messages/context.json)
retain the development-machine evidence. Native Windows/DPI appearance remains
part of the existing [rig checklist](rig-verification.md).
Final compact-dialog checks pass12 focused prompt, clipboard, markup-escaping,
vertical-overflow and acknowledgement cases; scoped lint/format, Win32 types and
the current boundary check676/zero violations pass. Sol/Astra review normal and
long-report screenshots, confirming the two-action footer remains reachable.
Snapshot-derived text is escaped before trusted heading styling; full copied
diagnostics remain literal. The refreshed macOS sample preview reports both dashboard and compact
dialog visible, with isolated settings and synthetic events.
[Compact-dialog evidence](runtime-evidence-2026-10-13/readable-gui-messages/dialog-compact/context.json)
records commands and scope; this is local presentation evidence, not rig acceptance.

Oct13 Git synchronization packaging: raw evidence videos remain at their original
local paths and are excluded from Git. The
[local video manifest](runtime-evidence-2026-10-13/local-video-manifest.json)
records71 files/10081381328 bytes with complete SHA-256 hashes. Remote checkouts
contain the manifest and associated reports/logs/metadata, but require a separate
copy of these video bytes for playback or independent decode. Original media and
the oversized unpushed commit are retained locally; no validation result changes.

Oct13 MCU pin diagnostic submission repair (`mcu-pin-test-submission`) under
[G01 revision174](../docs/architecture/gui.md#g01) and
[A11](../docs/architecture/acquisition.md#a11): authenticated read-only status of
controller04afb7ac-8774-4a0b-8380-41f21c6fca3f/revision1 confirms Eye requested60Hz
but no saved pin, disabled camera/free-running timing and no MCU observation.
The displayed pin9 is a local GUI draft. Loaded MCU drafts suppress immediate
pin saves; the former Test guard rejected the difference, followed by a misleading
"Requested ... through controller" message despite no test dispatch.
Explicit Test now submits only the selected diagnostic pin/rate and COM port,
checks exact controller acceptance, then targets that confirmed revision. Changed
bases, rejection or unconfirmed settings prevent the diagnostic; a later revision
change is rejected by the existing controller guard. Preserve other camera settings
and local drafts. Dispatch feedback comes from the managed binding.
ARCH-002 review uses a focused submission helper, existing configuration lock,
revision-adoption operation and owning behavior tests; no dependency, process,
firmware or whole-runtime reference is added. Existing large transport/panel owners
only route the focused operation and retain their responsibilities.
Final offscreen GUI30 cases and controller76 cases pass/one platform skip; Ruff
check/format155 files, Win32 mypy153 sources and boundaries668/zero violations
pass, with existing cohesion advisories. Sandboxed Qt/status attempts stalled and
were interrupted; permitted replacements pass. Initial import/type errors were
corrected. The running GUI is not restarted; native pin9/60Hz test, installed
protocol compatibility and physical reception remain unverified. No hardware or
firmware command was sent. [Commands/provenance/limits](runtime-evidence-2026-10-13/mcu-submission-context.json),
[GUI regression](runtime-evidence-2026-10-13/mcu-submission-verified.xml),
[controller regression](runtime-evidence-2026-10-13/mcu-submission-controller.xml),
[live read-only evidence](runtime-evidence-2026-10-13/mcu-submission-live.json).

Oct13 projector calibration retention investigation (`projector-calibration-retention`):
Oct14 owner screenshot still shows blank corrections/measurements. Read-only inspection
now finds `config/runtime_gui.json` last written Oct14 09:17:14 JST, with all16
scale/offset fields null, all four measured X/Y pairs null and tank geometry null;
stable role assignments and reference pixel dimensions remain present. SHA256
503c4d57079e51d2fb81cc405f996e80b394c0536caa22b6180cf145e277d7b4.
The saved file therefore explains the currently restored blanks, but not where earlier
entered values were lost. Review draft also has empty calibration; modes have separate
files. Owner says they will check again; no runtime/UI/configuration mutation or
additional tests performed. Actual prior entry/closure path remains unverified.

owner reports values missing after GUI closure. Under [G01](../docs/architecture/gui.md#g01),
current managed normal close saves the full GUI snapshot before controller-history
RPC; the snapshot includes all four screens' calibration fields. Read-only inspection
of `config/runtime_gui.json` found every scale/offset field null (file last written
Oct13 16:27:54 according to host filesystem metadata). The existing connected and
disconnected close/reopen regression passes2 cases; a separate offscreen GuiHistory
save/restore with explicit nonzero scale/offset values passes all16 fields. These
checks establish current source behavior, not the owner's previous running process
or closure path. Live diagnostic updates do not themselves persist GUI history;
normal close is the automatic save point. Actual closure method, restore warnings,
and prior values remain unknown; no production defect/root cause is established.
Process creation-time inspection via CIM was denied. No runtime/device/configuration
mutation occurred. Commands: `.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py
-q -k runtime_gui_close_reopen_preserves_full_draft --basetemp
.local-projector-retention-investigation` with offscreen Qt, plus isolated sample
windows using GuiHistory and a local JSON file. The generated roundtrip history is
[retained as evidence](runtime-evidence-2026-10-13/projector-retention-history.json)
after SHA-256-verified copying before temporary-fixture cleanup. No rig acceptance
is claimed.

Oct13 runtime Protocol group-control repair (`runtime-protocol-group-controls`):
source review confirms both frontends share `ProtocolEditor`, but controller and
saved schedules with direct root epochs hide the subgroup form and disable group
creation. Under [G01](../docs/architecture/gui.md#g01) revision173, these schedules
now receive one listed, once-only presentation group through the existing helper.
Untouched submission and schedule/single-program export preserve the original
source; actual program edits serialize the grouped form, and Undo back to the
initial program restores source export. Already grouped and mixed/nested programs
are retained. Standalone canonical imports keep their existing inspection path.
ARCH-002 review reuses the focused trial record, shared grouping helper, existing
page/snapshot operations and owning dashboard tests; no dependency, runtime owner
back-reference, device action or scientific default changes are needed. The focused
GUI regression suite passes50 cases, including managed source preservation,
saved-schedule restoration, subgroup edits/Undo and group/subgroup creation/reload.
Ruff check/format pass154 GUI/test files; Win32 mypy passes152 GUI sources;
boundaries check667 modules with zero violations and existing unrelated cohesive
size advisories. Whitespace passes. Initial pytest temporary-directory creation
fails for one fixture; rerun with repository-local basetemp passes. These are
offscreen checks; native Protocol control behavior remains visually unaccepted.
The runtime has since been restarted for the combined recording work below.
[Dated results and commands](runtime-evidence-2026-10-13/protocol-group-controls-context.json),
[test evidence](runtime-evidence-2026-10-13/protocol-group-controls.xml).

Oct13 combined recording/reset repair under [SYS-002](../architecture.md#sys-002),
[A07](../docs/architecture/acquisition.md#a07), [V12](../docs/architecture/visual_stimulus.md#v12)
and [E05](../docs/architecture/experiment.md#e05)/[E08](../docs/architecture/system-contracts.md#e08)/
[E11](../docs/architecture/experiment.md#e11) is verified in two
consecutive normal60s sessions in generation449c9382-c65d-4ed8-ae4e-393490ce9085.
Actual3602/3601 render groups give60.0333/60.0167 groups/s while Behavior30Hz and
Tracking60Hz record. Four samples per trial identify renderer23560 on RTX5060Ti/GPU0
and both camera plus review NVENC encoders on RTX2080Ti/GPU1. All six saved videos
externally count and fully CPU-decode; trial/output/metadata closure and reservation
release pass. Both NewSession/configuration restores succeed without shutdown.
The normal GUI is Configuration/no prompts, original full settings equal and cameras
released. All camera drain allowances remain the owner-selected125ms; Eye is disabled.

Reset repair acknowledges final coalesced warnings before Finished under A07
revision61, preserves exact pulse outcome retry identity, and retains canceled trial
health scope until cleanup. Shared absolute-clock waits correct early Windows async
wakes: a rejected lifecycle trace proves internal Stop3.38ms before normal end,
which the MCU channel correctly rejected. Preparation cleanup receipts now retire
only when all local source/consumer ownership has closed before a new preparation;
old resource-generation keys cannot enter the new cleanup catalogue. Strict evidence
checks and original deadlines remain intact.

The rendering repair moves native pixel work outside admission locking, uses bounded
native row conversion/completed PBO mapping and actual-context no-op checks, and
copies encoder input privately with a GIL-releasing native copy. No new dependency,
process, policy option or scientific/PFS/encoder tuning. CPU budget now covers retained
padding, readback/pipe copies and half-frame row scratch.1123 regressions pass,
3 skip/6 deselect; native Windows pipe14 pass. Ruff check/format, Win32 mypy427
sources, boundaries667/zero violations and whitespace pass. Existing large owners
remain cohesive: small context callbacks and preparation receipt/budget helpers do
not add whole-runtime references or a separable feature responsibility.

This verifies nominal60fps host cadence, not uniform16.67ms/optical timing. Repeat
median16.79ms, p9927.56ms/max37.88ms; camera queues drop6/19 frames and review captures
1176 real samples with2367 capacity drops,58 same-slot omissions and2424 identified
duplicates in3600 encoded frames. Full accounting remains explicit; recording is
not zero-loss. Eye/locomotion Tracking/paired/optical/electrical acceptance and the
dedicated Save On-to-Off verification remain open. Earlier failed attempts/recovery,
removed experiments and baseline39.47fps are retained in dated evidence.
[Dated raw evidence, verification and limits](runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)

Oct13 owner-authorized throughput implementation removes the measured float-to-byte
review readback stall and one intermediate host copy under V12/V20/E13. Recorded
four-output RGB8/all-VSync stimulus improves from30.13 real groups/s to60.0/s in
the final instrumented60s trial, with3600 real render groups and3600 encoded frames.
The review video still includes178 duplicates/12 capture drops/166 same-slot omissions;
full external decode, recipe digest, output closure, metadata sync and configuration
restoration pass. Native pixel comparison sees at most one8-bit rounding-code
difference in review pixels; physical rendering precision is unchanged. Final
uninstrumented confirmation also completes3600 groups/60s (60.0/s),3423 real captures,
177 duplicates,169 same-slot omissions and eight capacity drops, with normal
session/output cleanup, external decode/recipe verification and restored original
settings. The normal GUI/runtime is
left open in Configuration. The Save-Off comparison presents60.03groups/s
but reveals an existing Save-On→Save-Off cleanup failure (`cleanup returned an
unregistered resource`); exact full shutdown eventually passes. Keep that failure
separate from the throughput repair and the earlier failed-Setup cleanup link.
See [current implementation/limits](visual_stimulus.md) and
[raw timings/video verification](runtime-evidence-2026-10-13/throughput/).

Oct13 owner-authorized computer-level GPU placement is configured and verified.
NVIDIA Control Panel now explicitly binds the exact managed cephvr-python.exe
OpenGL program setting to RTX5060Ti; the fresh native four-output renderer verifies
its physical UUID/CUDA0 and exact release. Production camera encoder builders plus
actual generated-frame NVENC sessions verify RTX2080Ti/ordinal1 for all three
camera configurations. Fresh original Miniforge-base GUI launch confirms all four
Idle outputs without display issues; runtime remains open. No scientific/encoder
settings, firmware, camera or SpikeGLX commands are changed. This closes the current
adapter-selection task under SYS-002/V19/A08, without closing the separate native
camera or sustained throughput/optical tasks. No production source change is needed.
[Current setting, identities and execution evidence](runtime-evidence-2026-10-13/gpu-placement/context.json).

Oct13 fresh owner-requested workflow audit (`rig-workflow-failure-inventory`):
the current dirty working tree is tested through authenticated managed commands,
with real Behavior/Tracking cameras and four projectors. No production fixes,
firmware upload, scientific settings or wiring changes are made. The original
configuration is restored and final launcher evidence confirms all owned processes
absent. [Raw methods, snapshots and results](rig-evidence-2026-10-13/workflow-tests/).

| Workflow | Observed result | Remedy / next verification |
| --- | --- | --- |
| Camera connection and previews | Behavior40065509 and Tracking40747103 identity, capture/Show, visible preview and Stop pass; both devices closed, no cleanup pending. Earlier no-frame failure does not reproduce. Eye is disabled and untested. | Keep current settings; later exercise GUI selection, repeated reuse and native placement/DPI. Both previews report optional native timestamp unavailable; inspect SDK timestamp-frequency/chunk support before relying on device-clock diagnostics (A09), without inventing a clock conversion. |
| Normal projector calibration | Normal `calibration/diagnostic_display_profile.json` is rejected: mixed pacing requires an explicit pacing output. A separate diagnostic file made from the accepted current all-output-VSync profile passes Open, two grid updates, Close, Idle and resource closure. | Regenerate the normal diagnostic bundle from current accepted pacing/geometry and retest the ordinary GUI path. Do not change accepted V19/V20 pacing or treat dummy geometry as measured calibration. |
| Combined protocol and camera encoding | Setup fails before activation: `camera role 1 needs confirmed exposure/rate and drain policy`. Camera exposure/rate readback succeeds in preview; both file-only drain margins are unset. No camera video is recorded in this audit. | Establish the rig delivery/SDK bound and set each `cameras.<role>.post_cutoff_drain_margin_ms` under A10; it must cover exposure + delivery bound + one applied frame period. Behavior's exposure/frame-only floor is about58.34ms; Tracking's about21.67ms, before delivery allowance. Then repeat Setup and all-video closure. Do not guess the missing allowance or bypass validation. |
| Failed-Setup cleanup | CancelSetup cannot confirm cleanup; renderer exits after `ReportWorkerLifecycle: VISUAL_STIMULUS_EVIDENCE: cleanup command unknown` at coordinator `runtime.py:199`. Supervisor shuts down the application. Exact outer-Job absence is subsequently confirmed. | Trace the emitted cleanup operation against retained child-command links across Setup cancellation, prior closed calibration and supervisor cleanup. Repair the identity/lifetime mismatch with focused failed-Setup coverage under E06/E08; preserve original deadlines and truthful closure. Specific causality beyond the rejected link is unproven. |
| Stimulus presentation and encoding | Original audit renders30.33groups/s. The later measured capture repair reaches60.0 real groups/s in both final instrumented and normal60s recorded tests, with all outputs closed and settings restored. Normal run retains177 review duplicates/eight capture drops/169 same-slot omissions. | Main readback stall is repaired; retain explicit omissions and verify simultaneous camera/Tracking workload and optical timing. See the current [stimulus assessment](visual_stimulus.md) and [throughput evidence](runtime-evidence-2026-10-13/throughput/). |

The failed unstarted Setup leaves no `SESSION_CONFIG.json`; restart requires the
normal administrative recovery prompt. Exact test-session recovery succeeds,
preserving a recovery report and files. It emits an unknown-SpikeGLX-stop warning
despite this explicitly unpaired test; review recovery's unavailable-session-config
classification alongside cleanup. No remote SpikeGLX mutation occurred. A first
10s diagnostic is rejected by E05's60s minimum (probe error, corrected before the
recorded trial); one early restart declines while the old guard is held.

Normal final Shutdown succeeds and exact process absence is confirmed, but
acquisition's `_close` finalizer emits an uncaught `UNAVAILABLE` traceback when
its MCU Close RPC reaches the already departed controller. Review shutdown
ordering/expected authority-loss handling in `acquisition/main.py:277` and
`microcontroller_client.py:220`, preserving actual release evidence; normal exit
and a traceback-free teardown remain distinct checks. The saved reusable history
semantically equals the pre-test configuration; byte identity is not claimed.

Focused component tests pass213; owning GUI/offscreen calibration, preview and
protocol checks pass62/380 deselected. These and managed software observations
do not establish optical accuracy/photon timing, electrical pulse reception,
Eye, closed-loop Tracking, paired SpikeGLX or simultaneous full-load acceptance
(E15). [External video/cadence verification](rig-evidence-2026-10-13/workflow-tests/output-verification.json)
and [rig follow-up procedure](rig-verification.md) retain the boundaries.

Oct13 calibration export rejects the current version4 calibration snapshot after
successfully loading the owner's version3 portable projector file. The exporter
still gated versions2/3 although G01's loader already migrates calibration values
to4 (portable projector wrapper7). Extend the focused geometry exporter gate to
2/3/4 with exact integer versions; unsupported versions remain rejected. No schema,
geometry policy, calibration values or architecture decision changes are required.
ARCH-002 reuses the existing geometry helper and owning tests; no extraction or
dependency is needed, and existing cohesive source-size advisories are unchanged.

Eight geometry/profile/migration cases pass across versions2/3/4, including backend
GLB parsing and diagnostic bundle output. The owner's actual Desktop rig_cal.json
also loads in isolated Qt, yields calibration4/wrapper7 and exports a reference-bar
bundle parsed by the backend with four physical screen planes. Monitor bindings
in that check are synthetic; no native display, optical or live calibration pass
is claimed. The original file hash is preserved; initial evidence-helper failure
only omitted creation of its required existing Assets output directory and was
corrected. Ruff check/format2 files, Win32 mypy exporter, boundaries667/zero violations
and whitespace pass. No runtime restart or hardware/display command occurs.
[Owner-file method and provenance](runtime-evidence-2026-10-13/calibration-version-owner-file.json),
[regression cases](runtime-evidence-2026-10-13/calibration-version-tests.xml).

Oct13 owner reports prepare_camera rejection of canonical rising_edge as an
unadvertised TriggerActivation choice. The saved Eye PFS explicitly selects
FrameStart Off/Software, while the saved settings can retain the external edge
default. Canonical RisingEdge/rising_edge mapping already exists; fix applicability
in the GUI request owners under [G01 revision172](../docs/architecture/gui.md#g01)/A10.
Internal clock now clears TriggerActivation together with TriggerSource in both
camera-setting requests and loaded-proposal collection. External timing preserves
explicit edges, including FallingEdge; the adapter continues to reject unsupported
explicit feature requests. This avoids applying an inactive external control without
renaming saved canonical values, editing PFS/config files or weakening SDK checks.
ARCH-002 uses the two existing focused collectors, with no extraction or dependency
needed for this small refinement. Existing cohesive size advisories are unchanged.

Thirteen isolated GUI cases pass, including mocked reproduction of the exact
reported rejection, Test/Connect continuation, failure cleanup, loaded proposal and
explicit external-edge preservation. Forty adapter contract cases pass. Ruff
check/format153 files, Win32 mypy152 sources and boundaries667/zero violations pass.
No camera is opened, runtime restarted, MCU command sent or fresh SDK capability
read performed. Local reproduction and PFS source inspection explain the request
defect; physical post-fix acceptance remains pending.
[Source/provenance and checks](runtime-evidence-2026-10-13/internal-trigger-context.json).

Oct13 selected-camera Test/Connect now submits the current local camera parameters
automatically under [G01 revision171](../docs/architecture/gui.md#g01)/E03/E07/A10;
Setup is not needed. Capture the explicit camera identity, role, timing, PFS path,
rate and pin against the synchronized base; reject changed generation/configuration
before mutation. Reuse role assignment, camera-setting validation and SDK PFS
import/Finish editing, then issue the requested Test or Connect only after success.
Reassignment forces import of an explicitly selected PFS rather than trusting the
former device's baseline. External camera timing includes the selected COM port;
internal timing does not publish a unrelated local COM-port edit. Disconnect remains
an immediate cleanup command. Loaded PFS edits remain local until the requested action.

The chain uses the existing configuration dispatch lock, acknowledges confirmed
camera revisions including SDK/preview readback, and preserves unrelated dirty
page drafts and newer status views. A new focused submission helper owns the
separable preparation sequence under ARCH-002; transport/panel assembly stays with
existing owners, with no runtime back-reference, new process or dependency.
Existing cohesive size advisories for main/bridge/panels are retained and reviewed.
The affected Windows/offscreen suite passes87/347 deselected in29.17s; final focused
ordering/rejection/import-cleanup/draft preservation checks pass12/422 deselected
in1.53s. Ruff check/format153 files, Win32 mypy152 sources, boundaries667 modules/
zero violations and whitespace pass. Fake controller/SDK outcomes establish local
ordering, not physical camera acceptance. No live Test/Connect, restart, MCU pulse,
firmware or SpikeGLX command is performed.
[Current methods/provenance](runtime-evidence-2026-10-13/camera-action-context.json),
[focused cases](runtime-evidence-2026-10-13/camera-action-focused.xml),
[affected regression](runtime-evidence-2026-10-13/camera-action-broad.xml).

Oct13 live Eye selection investigation identifies a restored-draft defect under
[G01 revision169](../docs/architecture/gui.md#g01)/E03/E07. The running current-source
GUI accepts an immediate role command but retains the saved Unassigned draft;
that hides Eye from supported MCU outputs and the controller revision change
invalidates the draft. Keep role, participation and pin edits in a loaded draft
local until normal submission, updating camera rows and MCU choices together.
Retain immediate confirmed commands for configurations without loaded drafts and
the existing explicit SDK PFS import owner. Track local edits without projecting
controller state as edits; select Tracking by its exact role, excluding Eye tracking.
ARCH-002 reuses existing panel/snapshot/configuration owners and signals, with no
new process or dependency; existing cohesive panel size advisories remain reviewed.

The owning regression reproduces restored Unassigned selection, Eye assignment,
Add output pin entry, participation, poll preservation, file availability and zero
device commands. Final focused selection passes5/416 deselected; a broader permitted
Windows/offscreen run passes94 with one previously recorded projector horizontal
overflow failure (15px at1175px window width),326 deselected. The sandbox broad
attempt stalls at asyncio initialization and is interrupted before the permitted
rerun; initial temp-directory failure is resolved with workspace basetemp. Ruff
check/format, Win32 mypy151 sources and boundaries666/zero violations pass.
These isolated results do not establish live restart, native visual or electrical
acceptance. No runtime closed/restarted, firmware uploaded or device command sent.
[Read-only live state](runtime-evidence-2026-10-13/eye-selection-read.json),
[focused regression](runtime-evidence-2026-10-13/eye-selection-final.xml),
[broader regression](runtime-evidence-2026-10-13/eye-selection-broad.xml).

Oct13 owner screenshot corrects the earlier Explorer-picker completion claim:
revision168's nonmodal opener silently fell back to Qt widgets because the Windows
[file helper explicitly refuses nonmodal operation](https://github.com/qt/qtbase/blob/v6.11.2/src/plugins/platforms/windows/qwindowsdialoghelpers.cpp#L1378-L1391).
The prior21-case results establish widget cancellation only. Under
[G01 revision170](../docs/architecture/gui.md#g01)/E03, the focused shared opener now
queues native modal execution on a dialog-owned timer. Immediate rejection stops
startup; native execution stops Qt's helper timer. This is the minimal native
mechanism supported by existing PyQt6, replacing the earlier no-nested-chooser rule.
Filters, owner/path validation, stale-result fences and deferred deletion remain.
Windows shell proof verifies actual DirectUIHWND/NamespaceTreeControl controls for
Open, Save and folder modes with the real theme. Native GUI timers fire during
execution. Final regression passes23/400 deselected in16.43s, including40 rapid
pre/post-launch cancellations,12 immediate authority-loss cases and two started
authority-loss cases; started checks assert native WA_DontShowOnScreen to detect
fallback. Qt can emit rejection twice when closing the shell; callbacks remain safe.
Native pytest with the default faulthandler exits with0xC0000409; the same native
case with `-p no:faulthandler` and standalone themed repeated cancellation passes.
Cause remains unverified; record the exception-hook comparison without claiming a
default-native-suite pass. Local picker Ruff/format and Win32 mypy pass; broader
checks initially pass but final broad formatting/mypy find concurrent in-progress
camera/controller-bridge edits outside this change. Boundaries666/zero violations
retain existing cohesion advisories. No managed restart or hardware operation.
[Shell proof](runtime-evidence-2026-10-13/native-chooser/explorer-native-proof.log),
[final regression](runtime-evidence-2026-10-13/native-chooser/explorer-final-native.xml)
and [provenance](runtime-evidence-2026-10-13/native-chooser/explorer-corrected-context.json)
retain current validation scope; older widget evidence remains historical.

Oct13 per-tab configuration files are verified under
[G01](../docs/architecture/gui.md#g01)/E03/E07 without production changes.
The actual Save/Load buttons and nonmodal Qt widget dialogs round-trip Protocol,
Cameras, Microcontroller, Projectors, SpikeGLX, Tracking and full GUI JSON into fresh
matching-inventory windows. Three synthetic camera identities include Eye; MCU/full
files retain Eye pin8 and enabled Projector flip pin2. Loading emits no camera,
MCU/connection/firmware requests. Dashboard metadata uses the sidebar full-GUI file.
Extend the owning file behavior tests and Camera chooser authority-loss cases under
ARCH-002, without another test module or dependency. Nineteen button/chooser cases
pass; the broader Windows/offscreen file regression passes54/362 deselected in29.14s,
including malformed-file atomic rejection, failed-save destination preservation,
runtime/review retention and device/authority locks. Ruff check/format, boundaries666
modules/zero violations and whitespace pass; existing cohesion advisories unchanged.
These are isolated GUI/file checks, not native desktop visual or device acceptance.
[Methods and exact evidence](runtime-evidence-2026-10-13/tab-config-context.json).

Oct13 owner-authorized Eye trigger output is implemented under
[G01 revision167](../docs/architecture/gui.md#g01),
[A01 revision18](../docs/architecture/acquisition.md#a01) and
[A11 revision44](../docs/architecture/acquisition.md#a11). The GUI exposes an
assigned Eye camera trigger, retains numeric pins through MCU/full snapshots and
forwards its own diagnostic identity. Projector flip remains the supported passive
input through Add input; removal/Add/file restoration and authority locks are checked.
Managed Add collects an unset camera pin in a nonblocking dialog and atomically
submits pin plus participation, avoiding enablement rejection before a hidden pin
can be edited. Role/inventory or authority loss closes the dialog; existing revision,
dispatch lock and confirmed-state gates remain authoritative. Source/rate stay in
Cameras; no physical Eye assignment, pin or rate is inferred.

Protocol4 adds Eye configuration/state, grouped boundary masks/reservations,
diagnostics, SDK readback rate selection and all-output cleanup proof. Missing Eye
state never means stopped; protocol3 is rejected before testing and requires the
owner's manual upgrade. E14 Microcontroller policy/config are version2 with updated
digest; generated bindings come from the three owning proto sources. ARCH-002
reuses serial, operation and snapshot owners without another process, dependency
or independent pulse owner. Reviewed existing MCU/preview/cleanup coordinator size
advisories remain cohesive; only focused masks/projection/admission are extended.
Firmware uses the existing timer scheduler for three independent pins, validates
pairwise conflicts before mutation, bounds complete replies through Print counting
and leaves unassigned boot pins as inputs without pull-ups.

Local controller/acquisition suite passes834 (three privilege skips/two native
marker deselections); final readiness-focused rerun passes97. GUI/configuration
verification passes38 cases (369 deselected), including pin-first Add, rejected
oversized input and role/authority cancellation; final artifact provenance is in the
[evidence context](runtime-evidence-2026-10-13/eye-trigger-context.json).
Initial failures identify obsolete two-output fixtures, expected protocol versions,
the already owner-reassigned Trial pin, and an Add fixture with Trial state missing;
update fixtures without weakening required-state assertions. Ruff and Win32 mypy440
sources pass; boundary audit checks666 modules/zero violations. Firmware compiles
for Uno at13,922 flash bytes/1,214 global SRAM bytes (834 bytes remaining for locals).
No serial port, camera, pin test or upload runs. Manual installation, native GUI
inspection, electrical/timing/three-camera workload acceptance remain in the
[single rig checklist](rig-verification.md).

Oct13 FFmpeg compatibility repair completes the explicit owner-authorized tool
upgrade under [A08](../docs/architecture/acquisition.md#a08)/
[E13](../docs/architecture/visual_stimulus.md#e13)/[SYS-002](../architecture.md#sys-002).
A checksum-verified Gyan release supplies matched FFmpeg/ffprobe 9.0.2; the active
PATH directory keeps its historical `ffmpeg-4.3.2-2021` name, but its two executables
are now 9.0.2. Preserve original files in `C:/Dev/software/ffmpeg-backup-20261013`
and the complete new package in `C:/Dev/software/ffmpeg-9.0.2-essentials_build`.
No process/system PATH, runtime source, camera arguments or scientific settings
changed. Runtime continues its existing PATH resolution and needs fresh Setup.

Real build/native-device validation resolves the RTX 2080 Ti UUID
`GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc`, currently ordinal1. All required camera
hybrid-MP4 and stimulus fragmented-MP4 flags exist. Current saved lists and two
reference-derived camera proposals pass existing production validators. Five
sequential eight-frame synthetic cases use production command builders, close
successfully and ffprobe verifies frame counts/dimensions, H.264 profiles, full
range/chroma layouts and camera identity tags. This establishes only the tested
build/input/options/normal-closure cases, not camera conversion, sustained
throughput, crash-prefix behavior, quality or simultaneous workload acceptance.
Native capability query advertises H.264 8-bit 4:2:0/4:4:4 and HEVC 10-bit options;
AV1 is not advertised on this physical encoder. Eye format/rate remain unverified.

The supplied PylonRecorder guide's ant-rig CQ/preset/AQ size ratios do not establish
CephVR results. Saved p4/CQ18/yuv444p/lookahead0 lists remain unchanged.
The latest requested starting recommendation uses p3/CQ18/lookahead0/surfaces0:
color Behavior and saved BayerRG8 Eye use full-range yuv444p/high444p; Mono8
Tracking uses full-range yuv420p/main. All three proposed lists pass existing
validation against recorded9.0.2/RTX2080Ti facts after installed hash verification.
The newly saved Eye ROI1920x1200/rate100Hz is disabled and not physically checked.
[Proposed lists and validation scope](runtime-evidence-2026-10-13/ffmpeg/recommendations.json)
are not applied defaults or actual-footage quality/concurrent throughput acceptance.
Earlier p3/CQ33/lookahead4/surfaces16/rate caps remain compatible comparison options. Container,
GPU ordinal, B-frame prohibition, keyframe cadence and input geometry/rate remain
backend-owned; the reference Matroska/live/GOP options are not accepted GUI tokens.
[Actual methods, install/rollback provenance and probe limitations](runtime-evidence-2026-10-13/ffmpeg/context.json),
[build/device/options audit](runtime-evidence-2026-10-13/ffmpeg/audit.json),
[synthetic executions](runtime-evidence-2026-10-13/ffmpeg/smoke.json),
[post-install PATH/native checks](runtime-evidence-2026-10-13/ffmpeg/installed.json).

Oct13 disabled runtime controls are traced to an authoritative protocol projection
failure: the planner retains a previous group navigation scope when installing an
ungrouped controller trial, raising `Only groups contain epochs`. That leaves
`configuration_wired` false, correctly locking configuration files under G01/E03.
Reset scope and selected paths when replacing the schedule, preserving imported
programs unchanged. Separately, the MCU-specific Configuration gate enabled the
COM children but left their parent disabled by the general gate; apply the same
MCU gate to that parent, retaining authority and active-diagnostic locks.
ARCH-002 review uses existing owners and two small state resets, with no dependency
or new coordination. The cohesive MCU panel retains its existing size advisory.

Read-only native snapshot projection at generation
`f17215ba-41c0-42e1-baeb-4c30d5ccf2b8`, revision4 reproduces the error, disabled
ports/files and enabled Test connection. After repair, the same snapshot installs
without error and enables COM selector/refresh, MCU files and full GUI files.
Five focused offscreen Windows cases pass (397 deselected, 3.60s); Ruff/check format
three files, Win32 mypy151 GUI sources, boundaries666/zero violations and whitespace
pass. The first regression attempt fails only because the sample fixture starts
ungrouped; explicitly establish the prior grouped selection before testing reload.
No pin tests, flashing or camera/SpikeGLX commands run. The live old-code GUI is
then closed through owner-requested normal ShutdownApplication after accepted
history save; exact generation-bound receipt confirms all owned processes absent.
The existing local GUI file is preserved; this controller shutdown does not claim
to save unsent edits in the old GUI. Reopening loads the repaired source.
[Projection evidence](runtime-evidence-2026-10-13/disabled-controls.json),
[shutdown evidence](runtime-evidence-2026-10-13/disabled-controls-shutdown.json).

Oct13 numeric MCU pin display under [G01 revision 166](../docs/architecture/gui.md#g01)
uses number-only editors for fixed I/O and camera pins, including restored D-prefixed
assignments. Keep existing snapshot/firmware tokens canonical at capture/submission;
numeric edits compare correctly with confirmed controller pins before Test. A11's
runtime serial configuration and bounded diagnostics require no firmware flashing
for reassignment. ARCH-002 extracts one focused editor/token helper, reusing Qt and
existing snapshot/request owners without new dependencies or firmware changes.
Final native GUI selection passes 29 (373 deselected, 20.09 s), covering migration,
numeric/legacy request tokens, confirmed test gates and full-file/runtime/review
round trips. Initial expectations for prefixed widget text and saved-token formatting
were corrected; saved files retain their existing wire representation. Ruff
check/format (153 files), Win32 mypy (151 sources), boundaries (666 modules/zero
violations; existing cohesion advisories), edited TOML loader and whitespace pass.
[Validation evidence](runtime-evidence-2026-10-13/pin-numbers-context.json).

The owner selects Trial state output on pin 12, with manual SpikeGLX observation.
Update its owning TOML default and confirm/save D12 through the controller's existing
configuration/history operations. Two native two-second output tests on COM8 use
installed protocol 3 / cephvr2_uno_2 with camera outputs stopped; no pin-9 test runs.
The first starts successfully but its probe incorrectly supplies a signal to STATUS;
the controller rejects that follow-up, then normal shutdown succeeds. Retain it as
probe misuse, not a production MCU defect. The corrected repeat has matched active
and stopped D12 diagnostic snapshots, one generated rising transition, confirmed
normal shutdown and generation-bound all-owned-absence receipt. Saved D12 history
reloads without warning. Read-only SpikeGLX status reports acquiring; no remote
mutation, firmware upload, camera capture or experiment/recording command runs.
The owner then clarifies that testing must be triggered manually with the GUI Test
button; the agent had over-interpreted the earlier observation request and sent the
two tests automatically. Stop automation; neither a receiver pass nor a wiring defect
is inferred. Reopen Runtime for the owner: read-only readiness confirms Configuration,
COM8/D12 enabled, GUI-held control and no active diagnostic. Leave that runtime open
for manual Test connection / Trial state Test. The owning regression now clicks the
actual numeric-pin-12 Test button against an isolated controller: one native case
passes (401 deselected, 2.98 s), preserving stale-pin rejection. Electrical voltage,
timing and receiver acceptance remain in the existing rig checklist; other hardware
deferrals remain. The earlier two test runtimes are closed; this final GUI is
intentionally running for the owner's manual interaction.
[Native methods and outcomes](runtime-evidence-2026-10-13/pin-test/context.json).

Oct13 exact controller-exit verification under [E08](../docs/architecture/system-contracts.md#e08)
passes on the running Windows runtime. Preflight confirms Configuration, four startup
Idle outputs and no Acquisition/Tracking work. The actual controller is still alive
after GUI closure; GUI closure intentionally retains the runtime under E03/E08.
Terminate only controller PID 27476 with its retained creation-time/image identity:
supervisor 23512, acquisition 20976, Visual Stimulus 26684, tracking 23848 and renderer
24404 all exit. At 3.453 s the generation-bound launcher receipt confirms the outer
application Job empty; a fresh process inventory finds no managed executable and
the application guard is available. This closes the running projector-process
ownership check without a production code/architecture change. The independent
controller-loss emergency report is preserved; process absence does not prove
recording finalization or paired SpikeGLX stopping. Activated/full-load fault acceptance
and existing hardware deferrals remain open. Launcher/supervisor/native isolated tests
pass 95 with one Windows symlink-privilege skip (7.63 s). No camera capture, new
recording, scientific-setting change or automatic relaunch is performed.
[Exact identities, method and retained evidence](runtime-evidence-2026-10-13/controller-exit/context.json)
include the authenticated preflight, native exit observations and test results.

Oct13 GPU startup closure repair follows [V19 revision 6](../docs/architecture/visual_stimulus.md#v19):
a healthy wrong-adapter context is rejected through exact sessionless display cleanup,
with configuration/GUI retained; actual GPU faults and unsafe cleanup still escalate.
Authenticated controller cases and native AMD context release pass. The final managed
GUI launch uses the required RTX 5060 Ti, initializes all four outputs and has no
warnings/errors. The original failing launch route remains unresolved; see the
[owning GPU assessment](visual_stimulus.md#startup-gpu-placement-and-closure).

Oct13 runtime GUI retention under [G01 revision 165](../docs/architecture/gui.md#g01)
and [E07 revision 60](../docs/architecture/experiment.md#e07) saves the complete editable
GUI snapshot atomically to `config/runtime_gui.json` and verifies it by reading back
before closure. Restore once after initial inventory/base installation, retaining
local drafts and marking them dirty for normal E07 acceptance. Preserve delayed
SpikeGLX mapping replies as provenance without replacing restored channel edits;
explicit controller reload resets that draft protection. Startup-only host values
remain read-only. Runtime and Review have separate local files.

Local save failures keep the GUI open unless Close without saving is explicitly
selected. Controller disconnection or accepted-history save rejection cannot discard
the verified local snapshot. Remove close-time configuration submission and obsolete
discard handling; controller history remains controller-owned. Fix Qt's reentrant
close suppression by accepting the outer close event after synchronous local-save
completion. Unreadable/incompatible, not-yet-restored and active-session previous
files remain preserved. Restoring never changes controller state or launches devices.
Retention covers normal closure; forced process termination cannot promise a save.
The original reported warning detail remains unknown; initial read-only checks found
valid current controller/review history and QSettings NoError.

ARCH-002 uses one focused GuiHistory owner with the existing GuiSnapshot validators
and QSaveFile, without a new schema/dependency or whole-runtime reference. Main retains
its existing Qt wiring/snapshot/authority coordination (size advisory); storage is
separate and obsolete close submission/discard responsibilities are removed.
Extend the owning dashboard behavior module rather than create per-fix tests.

Final native Windows selection: 27 passed (374 deselected, 18.27 s), including actual
close/reopen full-snapshot equality, disconnected saving, rejected controller history,
failed disk writes, preserved unreadable files, repeated snapshot polling and late
inventory replies. Isolated fixtures use no devices/controller process. Broader
offscreen selection: 106 passed/two existing 15-pixel projector overflow failures
(293 deselected, 51.18 s); those remain in the existing narrow-overflow task. Sandbox
attempts stall while Windows asyncio creates its loopback socketpair; a retained
30-second trace identifies socket.accept/_fallback_socketpair. Stop only the exact
owned test processes and rerun unchanged assertions with permitted loopback access.
No full-suite or device/experiment/forced-exit acceptance is claimed.
Ruff check/format (152 files), Win32 mypy (150 GUI sources), boundaries (665 modules,
zero violations; existing cohesion advisories) and whitespace pass.
[Native results](runtime-evidence-2026-10-13/settings-retention-native.xml),
[broader results](runtime-evidence-2026-10-13/settings-retention-offscreen.xml) and
[methods/source hashes](runtime-evidence-2026-10-13/settings-retention-context.json)
retain the exact validation scope.

Oct13 native picker repair under [G01 revision 164](../docs/architecture/gui.md#g01)
and E03 resolves the immediate-open/reject/parent-cleanup crash without changing the
test fixture or cancellation timing. Five native authority-loss cases and a standalone
window reproduce `0xC0000005`; unwrapped QFileDialog reproduces it too. Qt 6.11.2's
[Windows helper source](https://github.com/qt/qtbase/blob/v6.11.2/src/plugins/platforms/windows/qwindowsdialoghelpers.cpp#L188-L284)
shows deferred modal startup while hide clears the native dialog without stopping its
timer. This mechanism matches the reproduced sequence; no native instruction-pointer
dump is available. Delaying cleanup still emits access-violation notices, so no sleep
or production event-loop pumping is introduced.
ARCH-002 adds one focused factory selecting Qt's documented widget picker before
configuration/showing, reused by configuration, projector, folder/PFS, prepared-file
and stimulus-media owners. Existing filters, path/schema checks, stale-result guards
and deleteLater ownership remain intact; no global dialog setting or dependency change.
The original standalone sequence passes 50 rapid cycles without notices; ten real
Windows Load/Save authority-loss cases pass. The broad native GUI stage now finishes
normally with 401 passes/two hover-control lookup failures (186.89 s), before the final
media-picker adoption/test refinement. Final affected native selection passes 20
(382 deselected), covering those refinements, all picker owners and Runtime/Review
parity. The two hover cases repeat in fresh isolation with zero QFileDialog
constructions; they are separate native-test findings, not evidence of a picker crash
or a proven production hover defect. Existing offscreen projector-overflow findings
remain open; no exact-final-tree full-GUI or hardware acceptance is claimed.
Ruff/format (151 files), Win32 mypy (149 GUI sources), boundaries (664 modules/zero
violations; existing cohesion advisories) pass.
[Raw methods, source fingerprints and outcomes](runtime-evidence-2026-10-13/native-chooser/context.json)
retain baseline failures, comparisons and staged validation.

Oct13 Runtime/Review layout parity under [G01 revision 163](../docs/architecture/gui.md#g01)
removes Runtime-only Dashboard control-button/hint rows, their signal and unused
forwarder. Both modes retain one shared page construction and identical card geometry;
Runtime authority stays in the existing Control menu and truthful HUD, with unchanged
command/edit gates. ARCH-002 removes redundant presentation rather than adding another
layout or state owner. Strengthen the existing parity test to compare every card
without exceptions across Dashboard, Protocol, Devices/Projectors and Tracking subtabs,
at 1280/720 widths with Runtime/Review authority states and matched drafts. Menu
Take/Release and denied/confirmed takeover still dispatch their exact intents.
Eight focused layout/HUD/control cases pass; Ruff/format (150 files), Win32 mypy
(148 GUI sources), boundaries (663 modules/zero violations; existing cohesion
advisories) and whitespace pass. An initial sandbox run cannot create temp fixtures;
the permitted identical selection passes. No new dependency or device operation.
[Dated methods and final source hashes](runtime-evidence-2026-10-13/runtime-review-parity-context.json)
retain scope; subsequent picker repair is recorded above. Projector overflow,
encoding and hardware findings remain separate.

Oct13 rig verification uses clean source `f4e6bc89a612e5f33fe5b5256281bd1650257e32`.
Regenerating 19 authoritative Protobuf inputs resolves stale local bindings.
Windows static/contracts/schema/package steps pass; isolated backend/native tests
pass 1,520 with five skips. Combined/native GUI runs terminate with access violation
`0xC0000005`; the isolated native trace identifies fixture teardown after configuration
chooser tests. These are pre-repair failures; the focused native repair above resolves
that reproduction, while broader GUI acceptance remains incomplete.
Offscreen GUI regression completes with 396 passes and three failures: projector
configuration scrolling has a 15-pixel horizontal range at 1175-pixel window width.
All five backend skips require unavailable Windows symlink privileges; they remain
unverified. Existing ARCH-002 cohesion advisories remain, with zero boundary violations.
Four projectors at 60 Hz and both NVIDIA adapters are visible; read-only SpikeGLX
connection succeeds. Native V19 startup confirms all four RGB8 outputs with requested
interval-1 swaps. V01 grid Open, live updates at sequences 1/2, and Close confirm
presentation, Idle and resource closure using retained dummy geometry plus a separate
all-output-VSync diagnostic profile; the accepted configuration remains unchanged.
This is native lifecycle evidence, not optical geometry or latency acceptance.
The actual GUI Behavior Connect command produces no usable frame by its deadline,
then WORKER_OWNER_FAILURE triggers shutdown. The exact exit receipt confirms all
owned processes absent and the application guard free. COM8 Connect independently
reports protocol 3 / `cephvr2_uno_2`, both camera outputs stopped. A diagnostic STATUS
request without an active diagnostic is correctly rejected; it is probe misuse.
The initial PATH FFmpeg/ffprobe 4.3.2 audit lacks required `hybrid_fragmented`
capability; the later matched 9.0.2 repair above resolves that tool incompatibility.
Recording/full-load acceptance remains unverified. Eye, further camera capture, pulse
mapping and electrical measurements are owner-deferred today.
The missing-identity update probe does not exercise V19 startup initialization;
its two result waits time out, while both configuration updates succeed. An independent
snapshot proves exact restoration. Final normal shutdown confirms exact all-owned
absence, free application guard, exclusive COM8 open/close, and saved history matching
the original adopted configuration. A native desktop resize drag has no effect,
so narrow/DPI acceptance remains unverified. See
[current raw evidence](rig-evidence-2026-10-13/) and the
[remaining rig checklist](rig-verification.md); no full-workload acceptance is claimed.

Oct12 [G01 revision 151](../docs/architecture/gui.md#g01) adds Up/Down stepping to
shared Runtime/Review calibration inputs: scale 0.01 with two decimal places,
offset 0.1 px with one. The existing text draft/serialization and live user-edit
path remain authoritative; imported precision and partial typed input are preserved.
ARCH-002 review keeps this small input behavior in the focused calibration widget,
without new dependencies or state ownership. Five offscreen stepping/live/file/draft
cases pass, with scoped Ruff/format, GUI Win32 mypy (141 sources), boundaries
(650 modules/zero violations; existing cohesion advisories) and whitespace checks.
[Dated commands and source hashes](runtime-evidence-2026-10-12/calibration-steps/context.json)
record the local scope; no new native/optical/rig acceptance is claimed.

Oct12 [G01 revision 150](../docs/architecture/gui.md#g01) presents photodiode
placement as Frame/Pulse rows with Origin X, Origin Y, Width and Height. Frame
origins remain bottom-left output pixels; Pulse origins are relative to Frame, with
independent dimensions and strict containment. Both GUI modes use the shared table,
existing authority/pulse gates and planning preview. Full Projectors JSON version 7
migrates version-6 squares into equal Pulse dimensions and preserves older standalone
rectangles; numeric calibration remains version 4. Blackout zones retain the shared
empty-header rule. [Visual Stimulus](visual_stimulus.md) owns rectangular-pulse
validation and final composition. Fifty affected cases and 42 contract tests with
79 subtests pass; nine final presentation/file/render/parity checks also pass.
Ruff/format (289 files), Win32 mypy (271 sources), 11 schemas/zero drift, boundaries
(649 modules/zero violations) and whitespace pass. Both-width captures are inspected;
[current evidence](runtime-evidence-2026-10-12/pulse-definition-table/context.json).
Earlier [665-case integration evidence](runtime-evidence-2026-10-12/output-overlays/context.json)
and [empty-header evidence](runtime-evidence-2026-10-12/blackout-header/context.json)
retain their source stages and native limits. Existing open Review imports require
reopening to load this update; unsaved edits are left intact.

Oct12 [G01 revision 148](../docs/architecture/gui.md#g01) /
[V01 revision 18](../docs/architecture/visual_stimulus.md#v01) implement live Scale
X/Y and Offset X/Y in the active frame/grid diagnostic. Debounced edits coalesce
behind one in-flight, sequence-bound leased update; only actual all-output presentation
confirms it. Invalid/partial typing retains the last valid projection. Rejecting a
stale or malformed update before GL writes keeps the diagnostic healthy and reports
failed adjustment; GPU/presentation uncertainty retains Unknown and exact Close.
Other projector settings remain locked, and control loss/disconnect/change of
identity discards queued intents. Protected assets, windows, configuration revision
and original cleanup owners/deadlines stay intact; these are Configuration diagnostics.

ARCH-002 extracts focused GUI coalescing, controller admission, coordinator validation
and worker presentation helpers; the existing GL owner updates retained warp buffers.
Controller/Visual Stimulus suites pass 659 tests/one deselection before the final
mesh-precision guard, including the
real authenticated coordinator/renderer update services with display hardware injected.
The final guard run passes 658 cases and hits one CLI-help timeout; that unchanged
CLI case passes a targeted rerun. Sixty affected GUI cases pass, including
Runtime/Review parity; seven focused final
GUI/render cases overlap. Ruff/format (423 files), Win32 mypy (376 sources), boundaries
(649 modules/zero violations), 11-schema drift, 57 generated binding matches and
whitespace pass. [Dated methods, stages, hashes and limits](runtime-evidence-2026-10-12/live-grid-context.json)
retain staged validation and repaired attempts, rather than a full exact-final-tree
claim while other chats update Protocol/photodiode code. Active-grid controls are visually
inspected offscreen at wide/narrow widths. Concurrent Blackout zones parity and
calibration-profile comparison failures are retained as intermediate results; final
shared GUI checks pass after that task's corrections. No full GUI regression or
native Windows/DPI/GPU/optical/rig acceptance is claimed.

Oct12 [G01 revision 146](../docs/architecture/gui.md#g01) implements the owner's
separate Launch reference calibration and Launch projection calibration actions. Bars ignore prior
measurements/manual corrections; grid requires mode-matched pairs and maps mm/px
directly onto physical rig screens with manual scale/offset/inversion. Throw ratio
is config-only and produces the distance estimate; neither launch nor measured
mapping requires it. Existing protected managed launch/Close, authority and pending
locks remain. [Visual Stimulus](visual_stimulus.md) owns current workflow evidence:
74 affected tests and 42 contract cases/79 subtests pass, with local static checks
and wide/narrow card inspection. Native Windows/DPI/optical acceptance remains open.

Oct12 [G01 revision 145](../docs/architecture/gui.md#g01) names the shared card
Pixel-to-mm calibration and lets all three columns stretch equally through the
existing DataTable default. Remove the SpikeGLX connection explanatory paragraph,
retaining the config-path tooltip and read-only host controls. ARCH-002 removes the
local header override/widget rather than introducing another layout owner.
Projector distance is not an input to diagnostic launch; complete measured pairs
update ideal distance from native width × X mm/px × positive throw ratio. The later revision 146 removes the historical measured-mapping dependency on
throw ratio; revision 145 itself changes only presentation.
[Current layout evidence](runtime-evidence-2026-10-12/reference-layout-context.json)
records local checks; native Windows/DPI and physical acceptance remain pending.

Oct12 Projectors refinement under [G01 revision 144](../docs/architecture/gui.md#g01)
and [V01 revision 16](../docs/architecture/visual_stimulus.md#v01) removes explanatory
text and pixel columns, pairs measured X/Y millimetres under one header and shows
mm/px estimates independently of throw ratio. Config-only pixel lengths control
actual native bars, conversion and planning preview. Full/numeric file versions
5/4 retain them with legacy migration and atomic invalid-length rejection.
[Visual Stimulus](visual_stimulus.md) owns implementation and evidence: 71 affected
checks, 42 contract cases/79 subtests and local static checks pass. Wide/narrow
shared Runtime/Review card inspection passes offscreen; native/optical acceptance
remains in the existing rig worklist.

Oct12 [G01 revision 139](../docs/architecture/gui.md#g01) removes Gap/Seed controls and
the Selected trial section in both GUI modes. Per-trial Seed is config-only through
the existing Protocol JSON `stimulus_seed_decimal` field. Load/save preserves edited
seeds, including zero, and existing gap values; managed submission retains E01/E07
validation and timing. ARCH-002 deletes the widget/synchronization plumbing instead
of introducing another seed setting or state owner. Ten focused file-round-trip,
schedule, draft-retention, layout and parity checks pass. GUI Ruff, scoped format,
Win32 mypy (138 sources), boundaries (642 modules/zero violations), references and
whitespace pass. [Current hashes, commands and raw results](runtime-evidence-2026-10-12/config-seed-context.json)
record local scope and a formatting-only test-line correction. Native Windows/DPI,
live restart and full GUI/rig acceptance remain untested in this increment.

Oct12 Devices refinement under [G01/G02](../docs/architecture/gui.md#g01) puts a
Configuration file card first beneath each device tab row, including camera-only
files. The shared file rows use Load… / Save as… captions, equal-sized buttons and the
same field gap across all four Devices tabs under G01 revision 142/G02 revision 36;
Tracking captions match while retaining its Pipeline layout. Six focused layout/
file/parity checks and static checks pass; [current file-action evidence](runtime-evidence-2026-10-12/file-actions-context.json)
retains local methods, hashes and limits.
G01 revision 143/G02 revision 37 unify inventory Refresh through one accessible
icon/header helper, Use-first columns and single-row selection. MCU discovery uses
that icon beside COM selection, with Test connection separate. Empty MCU Inputs/
Outputs and SpikeGLX channel headers share visibility/height fitting; empty discovery
inventories retain Refresh. Protocol variation rows refit the shared control height
after ancestor styles settle, correcting an observed 38/36 px mismatch. Seventy-seven
affected checks pass, including discovery/identity/authority, file/layout and GUI
parity; GUI static checks and boundaries pass. [Current audit evidence](runtime-evidence-2026-10-12/shared-controls-context.json)
preserves initial failures, corrected measurements and final hashes/raw results.
Wide populated Projectors and narrow device views are inspected locally; existing
scrolling remains necessary. Native Windows/DPI/live restart/device/full GUI and rig
acceptance remain untested in this increment.
Cameras replaces the visible batch identity action with Test selected beside
Connect. MCU omits Apply pin settings and adds supported-signal dropdowns with
Add/remove: Projector flip input, Trial state and assigned Behavior/Tracking outputs.
Removal disables the owning signal while retaining its pin; camera participation
continues to belong to Cameras. MCU v2 files retain output enablement, load v1 files
without changing camera participation, and reject inconsistent full-GUI enable flags
before mutation. Load restores local drafts without device commands. SpikeGLX shows
only Use, Signal and Channel index while preserving stream/index/bit metadata under
the [snapshot contract](../contracts/gui-configuration-files.md).

ARCH-002 reuses camera serialization for camera-only/full files and keeps supported
MCU row editing in a focused GUI helper. Remove obsolete batch-button state and
embedded file-toolbar/Apply wiring; no backend protocol, firmware or dependency changes.
The large camera/MCU panels retain orchestration with small helper bindings, rather
than accumulating snapshot or signal-table implementation. Existing owner tests
cover saves, v1 compatibility, invalid-file atomicity, disabled-camera identity,
diagnostic/authority locks, narrow controls and Runtime/Review parity. All **390 GUI
tests pass in 353.58 s**, including the concurrent Protocol refinement; exact source
hashes still match. Ruff/format (140 files), Win32 mypy (138 sources), boundaries
(642 modules/zero violations) and whitespace pass. Wide/narrow offscreen captures
are inspected. The first suite rejects an inconsistent older fixture; correcting
both camera enable inventories preserves its scenario and the validation guarantee.
[Methods, hashes, captures and raw results](runtime-evidence-2026-10-12/devices-gui/context.json)
retain failed attempts and the hash-confirmed redundant rerun cancellation, including
the Qt abort during that deliberate interrupt; it is excluded from passing evidence.
Desktop Review launch required screen access; its subsequent UI inspection timed
out, so no native visual/Windows/DPI/device acceptance is claimed. Existing
[rig checks](rig-verification.md) remain open.

Oct12 Protocol presentation under [G01 revision 140](../docs/architecture/gui.md#g01)
defaults to Batch generate and uses natural-width Shuffle/Preview buttons at the
right, with the existing narrow-width reflow. Source selection still opens Batch
edit and tab switches preserve drafts. Projectors' configuration button reads Load….
Trials arrows and timeline Delete/Duplicate buttons remain absent; mouse selection,
guarded keyboard edits, history and authority are preserved. ARCH-002 removes
redundant grid rebuilding and uses existing components without new state/dependencies.
Twelve focused layout/default-tab/file/keyboard/shuffle/draft/parity checks pass.
GUI Ruff, scoped format, Win32 mypy (138 sources), boundaries (642 modules/zero
violations), references and whitespace pass; wide/narrow offscreen captures are
inspected. [Current methods, hashes and raw results](runtime-evidence-2026-10-12/compact-default-context.json)
retain local limits. Native Windows/DPI, live restart and full GUI/rig acceptance
remain outside this increment.

Oct12 Runtime/Review parity review under [G01/G02](../docs/architecture/gui.md#g01)
finds no unintended page-layout differences. Both entry points reuse DashboardWindow
and the application theme. Strengthen the existing owning parity test to construct
runtime with `sample=False`, restore matching validated settings and populated camera/
projector fixtures, and exercise actual runtime authority presentation at 1280/720 px.
All pages and nested tabs match in control inventory and card geometry; only runtime
lease controls and their Dashboard left-column displacement are excluded explicitly.
Review inspection/runtime authority menus retain their G01/E03 purpose. No production
code or dependencies change; ARCH-002 retains the existing behavior test module.
Five focused parity/editor cases pass; GUI Ruff/format (138 files), Windows-target
mypy (136 sources), boundaries (640 modules/zero violations) and whitespace pass.
[Methods, tested hashes, setup failures and results](runtime-evidence-2026-10-12/gui-parity-context.json)
record local offscreen Configuration scope. No native Windows/DPI/pixel or rig
acceptance is claimed; existing [rig checks](rig-verification.md) remain open.

Oct11 repository cleanup under [ARCH-002](../architecture.md#arch-002) removes
unreferenced shared context protocols/validators, the unused payload-transfer and
admission-inspection methods, and an unused startup-recovery test helper. Equivalent
device-admission branches and the supervisor cleanup predicate are simplified;
E08 identity, retention, ownership and deadline checks on active paths are unchanged.
Remove 51 stale GUI naming suppressions and their obsolete Ruff exception; all 25
edited GUI modules have identical before/after ASTs. Across the cleanup, 37 Python
files lose 119 net lines. Existing uncommitted repairs are preserved.

Owner tests pass 1,032 cases; integration passes 424 in the sandbox, with 27 localhost
bind failures/errors resolved by a permitted communication-module rerun (43 passes).
Together these cover 1,483 distinct passing cases, six skips and eight Windows/rig
deselections. GUI behavioral tests were not rerun for comment-only edits. Repository
Ruff/format passes 874 files, Win32 mypy passes 735 sources, and boundaries report
640 modules with zero violations. Existing cohesion advisories remain; this cleanup
adds no dependencies or responsibilities. Remove 74 untracked generated cache
directories (51,093,992 bytes), preserving environment, bindings, saved settings and
dated evidence. The owner subsequently requested removal of this cleanup's raw logs
and hash manifest on Oct12; the counts above remain historical summaries, including
the initial sandbox limitation. These checks do not close E15 rig work.

Oct11 sequential local repairs (working tree based on `f96286e`): the V19
missing/ambiguous saved-output startup failure now retains Configuration with an
actionable issue only after exact sessionless cleanup and confirmed evidence delivery
within the original deadline. GPU errors, cancellation, deadlines and uncertain
cleanup remain failures. All output identities are resolved before exposing windows.
[V19 implementation and limits](visual_stimulus.md) and the
[startup contract](../contracts/visual_stimulus/startup.md) own the details.
ARCH-002 reuses the resource ledger and extracts sessionless cleanup/display report
handling into focused owners; no new dependency or runtime state owner is introduced.

Portable/offscreen full regression passes **1,861 tests, six skips, eight Windows/rig
deselections** in 307.43 s, including authenticated controller/worker communication.
This covers the startup repair and prior optional-I/O/all-VSync implementation,
before the subsequent GUI shuffle changes. It does not establish a cause or Windows
resolution for Oct9's exact-completion timeout. Contracts pass 48 Tracking/42 Visual
cases; generated schemas (19/11) and 57 protobuf bindings match. Static analysis,
declarations and dependency checks pass. [Raw full-suite evidence](runtime-evidence-2026-10-11/startup-full.txt)
and [tested input hashes](runtime-evidence-2026-10-11/startup-inputs.json) retain local
scope; native MCU Apply and all-output VSync remain pending.

GUI **Shuffle trial** follows the owner-approved [G01 revision 135](../docs/architecture/gui.md#g01):
it permutes top-level blocks as a normal source edit, retaining each group's nested
objects, repetitions and condition references. Current nested/multiple selection
moves with its blocks; undo/redo restores selection and source order, and saved files
retain the permutation. Existing edit authority and pending-validation gates apply;
Setup seeds and V08 runtime shuffle remain unchanged. ARCH-002 keeps the pure reorder
in the existing node-editing helper and selection snapshots in the history owner;
the editor remains GUI orchestration without new dependencies or runtime references.
The GUI owner suite passes 381 cases; the subsequent two-row narrow-action layout
passes five focused shuffle/layout cases. Final lint/format, Win32 mypy (735 sources)
and boundaries (640 modules, zero violations) pass. Wide/narrow offscreen screenshots
are visually checked, and all four timeline actions meet their minimum label widths.
The initial screenshot helper exits 138 during teardown; explicit deferred widget
destruction in the final helper exits normally. This does not establish native Windows
teardown or DPI acceptance. [Methods, source hashes, raw results and limits](runtime-evidence-2026-10-11/context.json)
keep each validation stage separate.

Oct11 GUI error/recovery review under [G01/E03](../docs/architecture/gui.md#g01)
and E07 fixes two configuration-recovery paths. An earlier accepted submission no
longer clears the explanation for newer unsent edits. Configuration installation
uses the existing scoped projection guard, restoring edit tracking even on rejection;
explicit failed Reload returns an actionable error instead of escaping the GUI slot.
Subsequent valid reload clears stale/error state. ARCH-002 removes the entry point's
private-state repair and keeps errors with the focused configuration owner; no new
state, dependency or architecture rule. Three regressions fail before the repair and
pass afterward. The broader managed/recovery selection passes 82 cases; GUI static
checks and boundaries pass. Command failure, stale queue, reconnect review,
close/save and device pending-state review finds no further actionable defect.
[Source hashes, methods and raw outcomes](runtime-evidence-2026-10-11/gui-recovery-context.json)
retain local scope; native managed-GUI acceptance remains in the rig checklist.

Current [managed bindings](../src/cephvr/gui/main.py) connect configuration/Protocol,
camera controls/previews, MCU, Tracking diagnostics, projector calibration and
SpikeGLX operations. Older incremental statements below are historical. The explicit
remaining capture implementation gate is
[Eye external triggering](../src/cephvr/acquisition/config/validation_pulse.py).
Controlled stimulus throughput diagnosis, paired SpikeGLX, scientific Tracking/feedback,
calibration, native GUI/DPI, electrical timing and fault cleanup retain their existing
[rig checks](rig-verification.md). No new native runtime/device execution is claimed.

Oct9 Eye role/connect recovery (working tree based on `94285ac`) extends common
three-camera configuration/process/output evidence under
[A01/A02/A07](../docs/architecture/acquisition.md#a01),
[A10/A11](../docs/architecture/acquisition.md#a10) and
[G01](../docs/architecture/gui.md#g01). It repairs canceled readback barriers,
failed-start Disconnect, exact manual terminal acknowledgements, prior-cleanup
diagnostics and GUI pin aliasing. No new state owner, dependency or firmware policy
is introduced; the existing ledger retains exact terminal evidence. Controller runtime
only routes that evidence to its focused readback owner under ARCH-002.
[Acquisition assessment](acquisition.md) records role/capture limits.

Live GUI identity tests pass for both existing cameras. COM8's native responses identify
legacy firmware that does not implement CAPS, explaining the original timeout.
The owner's subsequent `.ino` Upload request exercises the native chooser and exposes
a GUI recovery defect: a displayed MCU failure disabled Upload despite A11 allowing
the idle repair handoff. G01 revision 134 removes that failure-only gate; diagnostics,
all three camera ownership views and exact native cleanup still block Upload. Controller
admission now includes Eye ownership, matching the GUI. ARCH-002 keeps the existing
focused bindings/admission owner and introduces no dependency or state owner.
Native Browse accepts `firmware/uno/cephvr2_mcu/cephvr2_mcu.ino`; explicit GUI Upload
compiles and verifies it on COM8, reconnecting as `cephvr2_uno_2`, protocol 3, with both
camera outputs stopped and cleanup complete. A subsequent Test connection succeeds.
That repair left the GUI open. The owner's subsequent all-output VSync choice now
passes pure validation without a pacer, but disconnected outputs prevent live checks.
Eye additionally needs external wiring/source/rate
and corresponding integration. Run43 remains historical output evidence; no new
recording or SpikeGLX pairing is claimed.
[Firmware repair method, source and raw outcomes](review-evidence-2026-10-09/firmware-picker-context.json)
retain chooser/button observations, native status and current checks.
[Current check/source/native evidence](review-evidence-2026-10-09/eye-camera-context.json)
preserves final verification and failed attempts separately from the prior checkout
audit. See the [rig checklist](rig-verification.md) for remaining acceptance.
Earlier non-rig Windows/offscreen execution passes 1,856 tests with five symlink
privilege skips and one rig deselection. Ruff/format (849 files), Win32 mypy
(734 sources), boundaries (640 modules/zero violations), dependencies,
contracts/schemas and declarations pass. The firmware evidence records the tested
1,039-input snapshot and a subsequent test-only import-separator formatting correction;
the forty focused firmware cases pass again on that final text. Subsequent E08
revision 170 moves all local runtime records to the owner-private
`%USERPROFILE%/.cephvr2/runtime` namespace. The current full suite and static checks
cover the final runtime source, with 295 focused integration cases passing and one
privilege skip. [Runtime namespace evidence](review-evidence-2026-10-09/runtime-root-context.json)
records preservation, live Y/N replacement, physical path visibility and limits.

Updated: 2026-10-11. Implementation/source review is recorded for the controller,
supervisor, launcher, headless client and shared/native helpers. Local results below
have their original scope; Windows and full-workload acceptance remain pending.
[ARCH-001/002](../architecture.md#arch-001) owns scope and structure;
[E04](../docs/architecture/supervisor.md#e04) and
[E05/E07](../docs/architecture/experiment.md) and
[E06/E08](../docs/architecture/system-contracts.md#e08) own behavior.

Current Windows checkout verification (2026-10-09, `94285ac`): regenerate stale
ignored local bindings from all 19 authoritative protos, resolving seven collection
errors and 17 typing errors without changing runtime source. The full offscreen
`not rig` suite, including isolated Windows resources/children and authenticated
loopback, passes **1,820 tests / five symlink-privilege skips / one rig deselection**.
Ruff/format (849 files), Win32 mypy (734 sources), boundaries (640 modules, zero
violations), dependency consistency, Tracking/Visual Stimulus contracts (48/42),
schema drift (19/11), fresh binding comparison (57 files), TOMLs (18), decision
register (114 revisions) and current changed-document links pass. Correct stale
V08/V17/V18 root index revisions to their owning records without changing decisions.
Size advisories retain their existing ownership/cohesion assessments; this verification
adds no runtime behavior or dependency. [Exact Windows commands, input hashes and outcomes](review-evidence-2026-10-09/windows-checkout-context.json)
retain failed attempts and exclusions. These checks do not rerun the dummy protocol
or establish camera/encoder throughput, optical/electrical or scientific acceptance;
those remain in the [rig checklist](rig-verification.md).

Completed initial repair scope (2026-10-09, working tree based on `0aebf47`): the owner
authorized fixes and cleanup after the Luna/Sol/Astra audit. Sol and Astra accept the final source with no remaining actionable finding in this
bounded review. The confirmed retirement,
recovery, replay, shutdown, SDK and GUI-feedback defects are repaired below; accepted
defaults are restored to a 500 ms preparation lead with unmeasured camera drain margins
and pacing-output identity unset. All 36 owning configuration cases now pass.
[Original audit and rejected candidates](review-evidence-2026-10-09/context.json)
remain historical evidence. [Implementation methods and validation](review-evidence-2026-10-09/implementation-context.json)
identify the final source snapshot, model handoffs and local/native boundary.

Latest retained native evidence is **run43**, not run42: its unpaired 60 s trial and
session complete, seven artifacts close, metadata syncs and the reservation unlocks.
Both camera videos and stimulus video pass external count/full CPU decode in the
[Oct8 output summary](rig-wiring-evidence-2026-10-08/dummy-experiment/unpaired-run-43-output-verification.json).
Behavior delivers 1,797 frames (29.95 fps) and Tracking camera 3,596 (59.93 fps),
superseding the earlier 20/40 fps observation after the external-trigger limiter fix.
Stimulus delivers 1,182 frames (19.7 fps), with four capacity drops; its nominal-60-fps
MP4 is 19.7 s for a 60 s trial. Render intervals have a 49.29 ms median. Throughput
remains open; the Oct9 non-GUI implementation adds explicit nominal-slot padding,
which cannot repair missed presentations and has not been rerun on the rig.
[Shutdown](rig-wiring-evidence-2026-10-08/dummy-experiment/final43-shutdown.json)
records exact process absence, released guard and saved history. Later raw records
report [GPU preference restoration](rig-wiring-evidence-2026-10-08/dummy-experiment/final-gpu-restoration.json)
and [original configuration restoration](rig-wiring-evidence-2026-10-08/dummy-experiment/final-history-restoration.json).
These are historical observations with no exact source revision in the inspected
summaries, not new native checks or current-default/full-load acceptance. Velocities
and SpikeGLX pairing were disabled. Remaining acceptance lives in the
[rig checklist](rig-verification.md).

## Current scope and review

<a id="maintainability-review"></a>
Oct16 owner-authorized maintainability implementation follows the Astra architectural
review under ARCH-002/E08/E14. All seven reviewed source changes are implemented;
final integrated validation is recorded in the
[implementation evidence](runtime-evidence-2026-10-16/code-maintainability-review/implementation/context.json).
The [original source review/probes](runtime-evidence-2026-10-16/code-maintainability-review/context.json)
retain their pre-fix fingerprints and reproduction outputs; their reproduction script
is historical and is not expected to run unchanged against removed private APIs.

| Reviewed concern | Current implementation and local evidence |
| --- | --- |
| Required SpikeGLX roles diverged | Fixed: GUI imports the canonical synchronization-owned projection. The original enabled external-trigger Eye mismatch was GUI `[]`, backend `[7]`. The red regression and25 all-camera enable/trigger cases now pass under E12/A01/A11. Physical mappings remain explicit and rig acceptance stays open. |
| MCU numeric acceptance diverged | Fixed: one pure controller-owned `resolve_serial_policies` validates both serial file policies and acquisition defaults under A11/E14. Preserve their common accepted positive uint32 integer baud/ms settings, exact finite seconds/ns, keepalive ordering and exact uint32-ms watchdog.35 configuration cases include17 parity cases. No operator value or fixed policy changed. Ack covers send through complete matching reply, capped by the original operation deadline; no timeout retransmission added. |
| Unary peer mechanics duplicated | Fixed: shared `UnaryPeer` owns bounded channels, principal/deadline metadata, receipt/type checks and close. Tracking and Visual Stimulus retain their own stub selection maps; diagnostics retain backend/method context and no retry is added.26 real authenticated owner transport/runtime cases pass. |
| GUI feature dispatch mixed with connection ownership | Fixed: focused `ManagedActions` receives explicit callbacks and has named device, inventory, display, Tracking, configuration and prompt methods. Bridge drops from777 to451 lines and retains the same thread/queue/safety/configuration-lock/fencing/cancellation methods. AST comparison finds all17 methods outside `_dispatch` unchanged. No whole-runtime feature reference or generic action/plugin framework added. |
| Unused GUI editing remnants | Removed only the121-line `EpochSelection` class, `editable_parameters` and class-only imports. `SelectionComposer` stays live in subgroup editing; eight focused fresh-process GUI cases pass. Other static candidates are not automatically removed. |
| Worker session matching duplicated | Fixed: service/state import one predicate from the existing worker scope helper.90 worker foundation/admission cases include27 session/trial/empty/mismatched-controller/session identity checks. Authorization is not broadened. |
| Recording metric API semantics unclear | Fixed: write/snapshot docstrings specify first-attempt through full-frame consumption, zero-progress gaps, one serialized unfinished input, copied independent stage-max examples and pipe acceptance versus encoding/durability. Existing52 recording cases pass without behavioral/output changes. |

Configured lint/format passes931 files, Win32 mypy809 source files and boundaries710
modules/zero violations. New shared transport and feature-action modules have focused
ownership; existing size advisories remain cohesion-review prompts, not failures.
Final backend integration passes1918 cases, with five platform skips and five
exclusions. The broad offscreen GUI snapshot passes544 cases with one existing
Protocol row-height failure (321px versus <320). A separate process loading the
pre-maintenance GUI adapters reproduces the identical failure; no geometry or test
assertion was changed. All46 bridge cases in that collection passed, and eight
focused fresh-process editing cases pass after the unused-class removal. The broad
GUI collection had545 cases; three concurrent GUI additions arrived afterward and
are outside that broad-run count. Source/wheel builds and wheel inspection pass,
including packaged new helpers and a dev-only Vulture requirement. Vulture2.16 is
installed in the repository environment and its command is available. Exact commands
and limits belong to the implementation context; local checks do not close E15
native/rig/full-workload acceptance.

Vulture2.16 is now a development-only dependency, with generated bindings excluded
and handwritten source/tests/tools/scripts/contract Python included. The documented
commands are advisory: default confidence100 finds five unused test-double arguments
and no production candidate at that threshold; confidence60 finds311 suggestions,
including286 in source. The two deliberately removed GUI symbols disappear from
that scan. Many remaining suggestions are implicit Qt/gRPC/Pydantic/native fields;
a lower-confidence hit is unverified until caller/contract review. No blanket
whitelist, hard CI gate or automatic deletion was added. The temporary install's
first automatic approval review timed out before execution; one approved retry
installed the declared version for evaluation. See the
[upstream false-positive/confidence guidance](https://github.com/jendrikseipp/vulture#handling-false-positives)
and [development commands](../docs/development.md#checks). No new runtime package
is justified; native process identity/Jobs, raw-stdin FFmpeg and distinct scientific
writers retain their owning guarantees.

Contract-exported Tracking protocols/validators remain intentional; Windows
`ensure_owner_only` also has documented historical manual recovery use. Neither
is classified as dead merely from the runtime caller scan. Broader lower-confidence
triage remains a follow-up, with source evidence retained rather than blind removal.

Oct15 projector-off TODO audit at `b68c4ee` runs1,737 projector-independent backend
cases (four skips,26 native/rig deselections) and38 targeted offscreen GUI cases
(470 deselected). Ruff/format911 files, Win32 mypy791 sources, dependencies and
boundaries695 modules/zero violations pass;44 existing cohesion advisories remain.
The existing subgroup regression confirms mixed-identity rule edits are rejected
without discarding the dirty draft, closing the stale `mixed-subgroup-random-rule-edit`
entry. Duplicate task IDs/status sections are consolidated, later evidence is kept,
and obsolete margin/keystone/seam acceptance instructions are replaced by current
G01/V15 pixel-size/offset checks. All projector-dependent and pre-existing hardware
acceptance deferrals remain. No implementation or device settings changed.
[Commands, probes, source fingerprints and limitations](runtime-evidence-2026-10-15/todo-projectors-off/context.json).


Current model-hierarchy audit (`hierarchy-audit-20261012`) starts from
`f96286e86dc9af334da78ab55a8c14ec111c6184` plus existing uncommitted source,
contracts and reports. Concurrent unified subgroup work is preserved and has its
own assessment below. Two fresh-context `gpt-6-luna` high auditors performed one
bounded responsibility pass; `gpt-6.1-sol` high independently reviewed evidence and
routine dispositions, and `gpt-6-astra` low reviewed the proposed change.

| Responsibility | Source-review coverage in this audit |
| --- | --- |
| Controller/shared | Deep calibration/shutdown admission, shared identity/command retention, Start activation/evidence waits; sampled metadata/reservation and snapshot projections. |
| Acquisition | Deep source identity, cutoff/capture, ring synchronization and recording terminal/flush/close; sampled manual devices, sessions and pixel adapters. |
| Supervisor/launcher/platform | Deep launcher replacement identity and atomics; sampled registration/recovery/exit, Windows jobs, pipes, guards and security. |
| Tracking | Deep ring sequence/private lease, record codec, bounded writer and completion; sampled coordinator, trials, methods and feedback. |
| Visual Stimulus | Deep live-calibration identity/sequence/deadline, validation versus uncertain GPU failure, all-output presentation/closure and blackout ordering; sampled compiler, media, recording and feedback. |
| GUI | Deep bounded/atomic JSON and full configuration imports, camera/protocol restoration and source transforms; sampled dashboard, device/projector codecs and widgets. Concurrent subgroup changes were read only. |
| SpikeGLX/MCU/tooling | Deep serialized SpikeGLX SDK/lifecycle paths; sampled MCU timers/parser, policy/configuration, packaging and schema-generation tools. |

This is not an exhaustive branch review. Detailed scientific algorithms, full
compiler/media/encoder behavior and every widget remain sampled or unreviewed.
Native Windows, CUDA/Pylon/OpenGL, DPI, electrical/optical behavior and full-load
performance require the existing [rig checklist](rig-verification.md).

The sole material candidate is **RT-001** (controller correctness/reliability):
`device/display_adjustments.py` omitted the shutdown flag from its locked admission
predicate. `lifecycle/commands.py` sets that flag before asynchronous shutdown
cleanup; ordinary lease authorization and retained active-grid evidence still allow
a fresh update. Luna reproduced Accepted plus one backend dispatch with shutdown
already requested; Sol independently verified reachability and Astra approved the
smallest guard and existing-module regression. The implementation adds the shutdown
flag to the existing locked rejection predicate; an otherwise-valid fresh update
now rejects without dispatch or pending state. The regression preserves successful
updates and resets shutdown before the independent lease-loss assertion. Confidence
is high; this is a defect in the pre-audit dirty tree, not an audit-introduced
regression. Sol accepts the final patch after one test-isolation revision; Luna's
final quality pass found no further justified edits. Astra independently inspected
the final source, test, surrounding admission/shutdown behavior and assessment, then
granted final acceptance: **RT-001 approved and implemented**. This is the complete
candidate list; no rejected/deferred candidate was manufactured.
[V01](../docs/architecture/visual_stimulus.md#v01),
[E06/E08](../docs/architecture/system-contracts.md#e08) already require closure and
fencing; no architecture revision or broader authorization abstraction is needed.
No other material candidate or measured optimization was established; no speculative
refactor/performance improvement is claimed. Oversized-file warnings remain review
prompts, not a reason to split cohesive owners or weaken their guarantees.

Verification uses the repository Python 3.11 environment and preserves E15:
baseline portable non-GUI pytest passes **1,492 / six skips / eight deselections**
after permitting authenticated loopback sockets. The sandbox-only attempt had 28
socket-bind failures/errors, not evidence of a product defect. After the final
patch and Luna quality pass, `pytest tests/controller tests/visual_stimulus -q
-m "not windows and not rig" -p no:cacheprovider` passes **659 / one deselection**
in 10.56 s. The focused admission case also passes; overlapping runs are not added.
Final Ruff check/format `src tests tools scripts` passes (865 files), Win32 mypy
`src/cephvr` passes (748 sources), boundaries pass (653 modules, zero violations)
and whitespace passes. No new responsibility or dependency is added to the focused
adjustment helper; its surrounding calibration owner and existing size advisories
retain their established ownership. Full offscreen GUI verification passes **393**
in 246.07 s with `QT_QPA_PLATFORM=offscreen`; all 146 GUI source/test Python files
remained unchanged during that run. This is portable widget evidence, not native
Windows/DPI/optical acceptance.

Contract unittest discovery passes Tracking 48 and Visual Stimulus 42; schema checks
match 19/11 models. Isolated generation matches all 57 binding files from 19 Protobuf
sources. No contract/config/package input changed during this audit, so those checks
remain applicable; no package build is required by the one-line runtime fix.
Final source/test/contract/config/tool input provenance is 1,025 sorted paths with
SHA-256 `4ef69d74b7bd741e6991dc0b6722b3b4840424676af2137beeb093189057ea8b`
(hash concatenated relative-path, NUL, bytes, NUL for `.py/.pyi/.proto/.toml/.json/
.ps1/.c/.h/.cpp/.glsl`, excluding bytecode, plus root `pyproject.toml`). The only
non-GUI runtime/test changes since the initial inventory are RT-001's helper and
owning test. Raw task evidence is disposable at the owner's request; retain this
assessment and results, preserving all pre-existing and concurrent evidence.
The requested model hierarchy ran without substitution; token/cost metrics were
unavailable. The bounded audit's independent work is complete, with no user decision
required. Existing rig-dependent and explicitly deferred work remains open. Exact
task-owned test directories and generated temporary bindings are removed; existing
caches, raw evidence and user work are preserved. The temporary inventory is removed
last after the lightweight status/reference check; no task background process remains.

Oct13 right-edge refinement (`timeline-edge-alignment`) follows
[G01 revision179](../docs/architecture/gui.md#g01): group blocks omit epoch counts,
retaining repetitions and duration; overall trial totals retain epoch counts.
Both timeline rows remove the extra16px right gutter so trailing add buttons align
with editing-content edges. Seven focused timeline tests, scoped Ruff/format,
Win32 mypy and boundaries682/zero violations pass. Offscreen/native geometry checks
confirm matching sequence/composer widths and flush right add buttons; full dashboard
render reviewed. [Evidence and preview](runtime-evidence-2026-10-13/timeline-edge-alignment/context.json).
Updated Cocoa sample GUI remains open; prior preview preserved. No device/controller
mutation or Windows/rig acceptance.

Oct13 compact timeline refinement (`trial-timeline-polish`) under
[G01 revision178](../docs/architecture/gui.md#g01): left-aligned totals, dark unselected
group blocks, accent selection, separate count/duration lines, subtle footer divider
and Selected group label. Content-based height replaces the320px floor; current sample
is281px on Cocoa. Seven focused timeline tests pass; final scoped lint/format, Win32
mypy and boundary checks pass. ProgramTimeline's502-line cohesion review retains its
existing painting/hit/scroll owner and focused external details/cache helpers.
[Evidence and interactive preview](runtime-evidence-2026-10-13/trial-timeline-polish/context.json)
record native/offscreen visual review. Sandbox launch lacked a screen; authorized native
launch reports PREVIEW_READY and remains open with isolated settings/sample data for
owner inspection. No controller/device connection or Windows/rig acceptance.

Oct13 trial timeline layout (`trial-timeline-layout`) follows
[G01 revision177](../docs/architecture/gui.md#g01): totals above the blocks, compact
selected-group controls below, aligned to the last group's visible right edge during
resize and horizontal scroll. Hide the secondary repetition/count/duration line when
it cannot fit a group block; retain the name and complete hover details. ARCH-002
keeps control layout and painting in their existing focused owners, with one viewport
notification and no dependencies. Seven focused timeline/history/scrolling tests pass;
three offscreen geometry checks and reviewed renders cover one/eight groups at1200px
and eight groups at720px. Scoped lint/format, Win32 mypy, boundaries676/zero violations
and whitespace pass. [Evidence and preview script](runtime-evidence-2026-10-13/trial-timeline-layout/context.json).
Native Windows/DPI and rig acceptance remain unverified.

Oct13 epoch title labels (`epoch-title-labels`) follow
[G01 revision176](../docs/architecture/gui.md#g01): named subgroup headers display
only their name; unnamed headers display Epoch N using existing sequence numbering.
ARCH-002 review keeps this presentation-only change in TimelineViews without new
state or dependencies. A direct model/view probe verifies unnamed numbering,
name-only headers and shared run boundaries. Scoped Ruff/format and Win32 mypy,
boundaries676/zero violations and whitespace pass; no native or rig check is claimed.

Oct13 epoch automatic updates (`epoch-auto-update`) implement
[G01 revision175](../docs/architecture/gui.md#g01): completed text edits and control
changes commit through the existing whole-trial subgroup transaction, without
Apply/Discard footer buttons. Navigation/save flush valid pending changes; invalid
input remains a draft and Undo can discard it. Passive validation never opens a
modal or continuously retries invalid variation inputs. Rebase the reference and
canonical declarations without rebuilding focused controls. Preserve source identities,
projector-local changes, variation seeds, and existing Undo/Redo history. ARCH-002
review retains the focused subgroup owner and existing Qt timers, with no new
dependencies or whole-runtime references. Final focused checks pass12 cases, including motion/fade edits, invalid drafts,
focus, atomic projector-local updates, history, variation persistence and file reload.
The broader run passed451 with six failures: four obsolete explicit-Apply/draft-asset
expectations are updated and pass; the concurrent advanced-control layout now passes.
The remaining texture-import test attempts QImage decoding of JSON before using the
editor. This prevents a clean whole-GUI claim and belongs to the active texture work.
Scoped Ruff/format, Win32-target mypy (two owners), boundaries (676 modules, zero
violations),526 local links/anchors and whitespace pass. Existing boundary size
advisories concern unchanged owners; the affected focused files remain below500 lines.
[Commands, source hashes, logs and offscreen render](runtime-evidence-2026-10-13/epoch-auto-update/context.json)
retain evidence. Native Windows/DPI remains unverified.

An investigation while testing invalid random edits also observed a pre-existing
mixed-subgroup limitation: changing random rules while multiple batch identities
are selected can leave stored rules unchanged and clear the local draft. The same
`apply` path excludes metadata updates for mixed identities. This is separate from
the automatic-update wiring. Oct14 (`mixed-subgroup-random-rule-edit`): `SubgroupEditor.apply`
now rejects a rule change across more than one batch identity with a notice and keeps
the draft dirty; other mixed-selection edits are unchanged. Bulk random-rule editing
remains unsupported. Offscreen regression in the owning subgroup test only; no native
or rig validation.

Oct13 subgroup editing follows [G01 revision175](../docs/architecture/gui.md#g01),
[V03 revision12](../docs/architecture/visual_stimulus.md#v03) and
[V08 revision5](../docs/architecture/visual_stimulus.md#v08). Clicking any member selects
its complete subgroup; parameter edits affect all members/repetitions. One composer
retains variation controls through automatic updates, selection, Undo and file reload. The trailing
subgroup + copies one template without inheriting rules. Order is removed; imported ordering
is preserved. Layer selectors show only indices at 64 px; timeline durations use
hh:mm:ss with fractional precision retained.

Current layout polish matches + heights to trial rows and timeline blocks, uses a
shared-column variation table, and separates correction/measurement calibration
cards with their launch actions above each table. Remove the separate SpikeGLX
inventory-save button; GUI file saving remains local and does not implicitly publish
controller inventory changes. ARCH-002 keeps row validation in BatchVariationRow,
with a focused VariationTable presentation helper and no new dependency. Existing
large GUI owner modules retain their responsibilities; no runtime ownership changes.
[Layout polish evidence](runtime-evidence-2026-10-13/layout-polish/context.json)
records 45 passing focused GUI checks, Ruff/format150 files, Win32 mypy148 sources,
and662 modules with zero boundary violations. Inspect1280/720 protocol captures and
1280 calibration cards; local rendering does not establish native Windows/DPI acceptance.

The selected group's name/repetitions sit below the blocks inside Trial timeline;
Sequence editor begins with subgroup blocks. Reparent the existing GroupEditor and
retain its binding/history, including resizing for imported condition controls.
Removal controls in the protocol use the same `button("×", "compact")` role as the
MCU outputs table, replacing custom 22 px padding overrides. Natural control sizing,
consistent insets, a taller subgroup header and reserved text space avoid clipping
or collision. Trial/group/subgroup and variation-row removal is hover-only; selection
alone shows no cross. The variation row reserves hidden-button space to avoid jumps.
[Card balance evidence](runtime-evidence-2026-10-13/card-balance/context.json) records
53 passing focused GUI checks (including trial/group interactions, layout and MCU
controls), Ruff/format 149 files, Win32 mypy 147 GUI sources, 661 modules with zero
boundary violations and inspected 1280/720 captures. Initial tests relying on selected
crosses or a hidden ungrouped fixture were migrated to explicit hover/group setup.
ARCH-002 keeps
canonical edits unchanged and reuses existing styling instead of adding a new button
style. Native Windows/DPI appearance remains unverified.

Trials and Trial timeline now share a 320 px minimum height and matched caption/header
heights, aligning their painted top borders despite the Preview button. Trials keeps
QListWidget selection and indices, adding a trailing + inside its scrollable viewport
and one reusable × control for the hovered row. No sentinel trial or per-trial
widget allocation is introduced. Existing deletion confirmation now targets the
clicked trial identity, retaining the selected trial when another row is removed.
Saved files, final-trial replacement and authority checks remain unchanged; invalid
pending edits block deletion of another trial. The focused TrialList module owns
presentation only (ARCH-002). [Trial-list evidence](runtime-evidence-2026-10-13/trial-list/context.json)
records 12 passing focused tests and a final interaction rerun, Ruff/format 149 files,
Win32 mypy 147 GUI sources and 661 modules with zero boundary violations. Inspected
1280/720 captures show three trial rows,
trailing addition and aligned borders. Native Windows/DPI checks remain outstanding.

Variation rules now have an always-visible Add variation rule button without an
Enable checkbox. The presence of rows determines active authoring rules; Apply and
reload preserve them, and removing the last rule clears compact execution rules on
Apply. Legacy inactive drafts do not silently become active on load. No schema or
runtime sampler change is needed. ARCH-002 removes redundant widget activation state
and uses shared table columns with horizontally scrollable narrow layouts. The
Layer control retains a Fixed size policy and 64 px width: an Ignored policy previously
allowed the grid to allocate less than its actual width, overlapping Parameter.
The owning layout regression checks adjacent geometry, equal heights, All layers,
Values/Sweep/Random and 1280/720 widths; persistence checks cover last-rule removal
and Undo. [Variation layout evidence](runtime-evidence-2026-10-13/variation-layout/context.json)
records 40 passing focused GUI tests, Ruff/format (148 files), Win32 mypy (146 sources),
660 modules with zero dependency-boundary violations and inspected 1280/720 offscreen
captures. These checks cover this increment; the preceding full GUI run is historical. An initial
layout test inspected a hidden legacy editor; opening its group exposed and verified
the actual column-overlap fix. Native Windows/DPI acceptance remains unverified.

Inline group/subgroup actions replace the + Group, − Group and + Epoch toolbar
buttons. A trailing + appends and selects; a top-right × appears only on hover
and targets that block, independently of prior selection. Subgroup deletion removes
all members; final-block removal remains disabled. Existing draft-validation,
authority, minimum-duration validation and Undo transactions remain authoritative.
ARCH-002 uses a focused presentation helper with explicit path signals and a small
reused button pool sized to visible blocks. No widgets are allocated per repetition.
The obsolete responsive header-action stacking is removed now that only Preview
remains. Offscreen 1280/720 captures show readable crosses and trailing additions with
no horizontal page overflow; no native interaction or rig validation is implied.
[Oct13 evidence](runtime-evidence-2026-10-13/inline-actions/context.json) records
31 focused passing cases and the final full GUI suite with 398 passes. Ruff and
format (148 files), Win32 mypy (146 GUI sources), dependency boundaries (660 modules,
zero violations), local links and whitespace checks pass. Initial checks
caught a QWidget.actions name collision, clipped cross padding and a deletion test
fixture violating the retained minimum trial duration; all were corrected without
weakening runtime validation. Earlier compact-rule evidence below remains historical
for the execution path, which this UI increment does not change.

Random rules now store compact executable seeded declarations; the earlier 2000
random-occurrence authoring limit is removed. GUI work samples only representative
source settings. Changing repetitions retains rules/seeds and the existing sampled
prefix. Random access uses the immediate-group repetition index and source-member
stride/offset, independently of shuffle; target streams default to independent
projector values, with explicit sharing. Independent draws may coincide. Setup
checks its configured expanded-plan bound (currently 100,000 epochs) before resolving
rules to validated concrete settings; rendering does not sample. Legacy concrete
tables remain readable. Explicit source-list generation and expanded/animated
previews retain their separate 2000-item limits.

ARCH-002 extracts existing pure numeric setting patches and precision-grid sampling
into Visual Stimulus configuration helpers, reused by GUI and compiler. The compact
rule model and random-access resolver have focused ownership; no new dependency,
process or renderer changes. Canonical schema validation remains a cohesive owner
with an existing size advisory. Source/prepared schemas match their models. Structural
checks at 10,000 and 1,000,000 repetitions confirm unchanged rules, one source block,
one representative resolution per edit and essentially constant serialized size.
This does not establish full-workload latency or memory guarantees: Setup's concrete
plan still scales with expanded epochs; image streaming remains separate pending work.

External authoring samples can be regenerated with the
[demo asset generator](../tools/generate_demo_assets.py); the local review assets root remains.
Inspected 1280/720 offscreen captures show image/gray ×10,000, clock labels, no Order,
narrow readable indices and no horizontal page overflow. A first capture exposed a
minimum-width reset hiding the variation index; moving the fixed-width assignment
after common control setup corrected it. Existing review instances require reopening;
this increment did not restart the user's application.

Current evidence is in the [manifest](runtime-evidence-2026-10-12/compact-rules/context.json).
Visual Stimulus passes 233/one deselection with loopback access; compilation passes 11.
The full GUI stage passes 396 with one obsolete index-label expectation failing;
the final 12 focused cases pass after migrating that assertion
and the final layer-width correction. Earlier focused failures identified strict
settings conversion and random-only source-count preservation; both were corrected.
Tests cover golden deterministic samples, source round-trip, group-count bounds before
sampling, independent/shared values, retained rules, and compact million-repeat edits.
Ruff/format (171 files), Win32 mypy (168 sources), all 11 generated schemas
and dependency boundaries (659 modules, zero violations) pass. Stages overlap and are not summed as a single exact-final-tree run.
Native Windows/DPI/rig acceptance remains in the [rig checklist](rig-verification.md).

Reusable configuration files (2026-10-08, `gui-configuration-snapshots`):
[G01](../docs/architecture/gui.md#g01) revision 132 and the
[snapshot contract](../contracts/gui-configuration-files.md) govern complete Protocol,
Microcontroller, portable Projector, SpikeGLX and Tracking files plus full GUI files
from sidebar controls. All loads prevalidate local drafts; atomic saves preserve
existing files. Full files retain metadata, recording choices, camera serials/roles
and explicit display assignments; incompatible inventories reject before restore.
Loaded camera/MCU values survive polling and join ordinary E07 proposals; changed
PFS paths require A10 SDK import. Inactive Tracking remains a local pending draft
until enabled. SpikeGLX rows persist through GUI Save/Load without a separate
pulse-mapping save button or automatic controller inventory writes; saved host/pairing
references cannot override startup TOML or current file digest. Firmware, camera
capture and projector output never start on load. Local validation completes:
initial full GUI run passes 368; final full run passes 367 with two outdated
SimpleNamespace projection-interface mocks failing. Correct both fixtures without
weakening their assertions; post-review owner checks pass 49 and three direct
projection/fixture cases pass. Ruff lint/format pass 138 GUI/test files, Win32 mypy
passes 136 GUI sources, boundaries inspect 632 modules with zero violations, and
732 local links/anchors plus ten register checks and whitespace pass. Retain
[raw JUnit, source hashes and method limits](gui-configuration-evidence-2026-10-08/context.json),
plus inspected offscreen sidebar (local-only `gui-configuration-evidence-2026-10-08/sidebar.png`),
MCU (local-only `gui-configuration-evidence-2026-10-08/microcontroller.png`) and
SpikeGLX (local-only `gui-configuration-evidence-2026-10-08/spikeglx.png`) images. No running
managed runtime is restarted or native chooser/hardware pass claimed;
[rig checks](rig-verification.md) retain native chooser/DPI and hardware acceptance.
ARCH-002 review keeps file IO and snapshot codecs in focused modules, with existing
page/device owners retaining widget/operation state. Existing large cameras/MCU,
Tracking and main files receive only draft guards/callbacks; no new runtime reference,
process or dependency is added. Projector orchestration remains unchanged.

Current calibration/output-unit work (2026-10-08, `physical-reference-calibration`):
the [Tracking](tracking.md) and [Visual Stimulus](visual_stimulus.md) assessments own
G01/T20/T38/V15 implementation and evidence. Per-screen raw-pixel bars replace editable
throw distance with measured X/Y scale and a derived estimate; Tracking requires camera
scale and publishes mm/s/deg/s proxies. Explicit old input/gain editing and versioned
files prevent silent reinterpretation. Affected checks pass 658 (one skip; two concurrent
temporary-pacing checks excluded plus one rig deselection), with post-review owning
checks passing. The offscreen card (local-only `tracking-evidence-2026-10-08/physical-reference-gui.png`)
is visually checked. No managed runtime restart or physical calibration is claimed;
native/DPI/optical/scientific/full-load acceptance remains in the rig checklist.

Unpaired dummy execution follow-up (2026-10-08, `gui-backend-dummy-experiment`):
the owner explicitly disables SpikeGLX pairing and approves temporary 1,000 ms
post-cutoff drain allowances for both cameras. Front 60 Hz pacing and the managed
wrapper's high-performance Windows graphics preference are temporary diagnostic
inputs; strict RTX 5060 Ti identity/framebuffer checks remain enabled. Real Setup
attempts now run, preserving each failed Desktop reservation and exact generation
exit evidence before controller recovery. This early-attempt account is historical;
run43 completion and its remaining cadence limits are summarized above.

Native attempts expose and repair E08 Configuration-heartbeat handoff, E04 missing
path-free Setup output identities, exact terminal Setup failure admission, empty
arena-boundary submission, GLFW fullscreen focus loss, private renderer-completion
routing, revision-zero cleanup catalogue initialization, CPU-to-GL video binding,
normal renderer-owned FFmpeg helper exit retention and duplicate WGL destruction.
The [Visual Stimulus assessment](visual_stimulus.md) records graphics/probe details;
the [Acquisition assessment](acquisition.md) records camera and shared encoding scope.
ARCH-002 reuses focused planners/ports/ledgers and existing behavior test modules;
no process, dependency, deadline or resource-proof exception is introduced.
Run43 supersedes these early attempts; remaining throughput and native acceptance are
in the rig checklist. [Raw attempts](rig-wiring-evidence-2026-10-08/dummy-experiment/).

GUI/backend dummy-experiment work (2026-10-08): the owner authorizes wiring/fixes
and a Desktop-output dummy run, explicitly retaining both camera videos and stimulus
video while disabling velocities. Eight reproducible Windows Qt layout failures
are repaired under [G02](../docs/architecture/gui.md#g02): shrinkable field/status
labels, tab elision, responsive protocol management, and targeted title wrapping
prevent minimum-width feedback without changing device ownership. The final owning
GUI suite passes **334 tests**. The first all-owner suite passes 1560, skips five,
deselects one rig case and exposes two GUI regressions; both are repaired and the
final complete GUI rerun covers them. No test assertion was weakened.

Later native inspection identifies two additional wiring/closure defects. Backend
camera-role adoption leaves Dashboard recording names at “Unassigned video”; the
recording owner now updates names/accessibility during view refresh without toggling
choices or marking drafts dirty. Both inventory-row regressions fail before and pass
after; native reopening confirms Behavior/Tracking names. Normal GUI close with an
incomplete protocol incorrectly reports history-save failure before sending a save.
It now saves the accepted controller configuration, with explicit discard/cancel
choice for unsent drafts, under E07. Four regression cases fail before repair; ten
focused close/recording cases pass afterward. Native discard/save closure exits the
GUI, preserves original configuration/history and leaves the session in Configuration.
The repaired GUI is reopened afterward. ARCH-002 keeps both changes in their small
existing recording/close owners with no new callbacks or state. Final all-owner
validation, including all 338 GUI cases, passes **1566 tests, five skips and one
rig deselection in 171.33 seconds**. Ruff lint/format, Win32 mypy and boundaries
pass again. [Final JUnit](rig-wiring-evidence-2026-10-08/dummy-experiment/final-all.xml),
[source/method context](rig-wiring-evidence-2026-10-08/dummy-experiment/context.json).

[E07](../docs/architecture/experiment.md#e07)'s application-shutdown history save
now shares the existing atomic writer and serialization lock. The history deadline
covers queueing; shutdown interruption/handoff retain their original deadlines and
run independently of that writer. Owning tests cover gated shutdown persistence,
queue timeout and failed-write preservation. ARCH-002 keeps these responsibilities
in the existing focused configuration/command owners, with one injected callback;
no runtime back-reference, dependency or policy choice is added. Ruff lint/format
pass 260 files; Win32 mypy passes 229 sources; boundaries inspect 620 modules with
zero violations. Existing cohesive source-size advisories remain review prompts.

Real GUI dispatch confirms both camera connection checks, bounded capture/disconnect
and Arduino connection. SpikeGLX diagnostics reach the remote server but find an
already-running acquisition; the empty pulse inventory also prevents pairing.
An invalid standalone MCU Status probe is correctly rejected because no pin
diagnostic is active; it is test-method error, not a backend defect. Native screen
inspection confirms assigned camera controls. Saved native projector identities
and rig geometry produce explicit **uncalibrated diagnostic** profiles and a
60-second procedural-grating protocol; this does not certify optical accuracy.
Before loading repairs, explicit history saving, normal shutdown, matching exit
receipt and application-guard release pass for generation
`93cbe363-06ee-419c-b55f-8e14fcf600ce`. The repaired runtime then persists a temporary
accepted experiment-name marker through **ShutdownApplication without a separate
save command**, confirms exact exit, and reloads it in a new generation. Restore
and save of the original configuration pass. Pure dummy-proposal validation passes
experiment/acquisition/inactive Tracking but rejects Visual Stimulus because V20's
explicit pacing-output identity is unset. Automatic approval review separately
rejects the proposed configuration/real Setup action for unavailable display
coordination and unresolved pairing against an active remote acquisition; **no
dummy configuration submission, Setup, Start or recording occurred**. Owner choices
for pairing and pacing are pending. Native wide-window camera controls render
correctly; the attempted drag did not resize the window, so narrow native/DPI
acceptance remains open. [Dated raw checks](rig-wiring-evidence-2026-10-08/dummy-experiment/).

Latest `.ino` upload shutdown (2026-10-08, E08/A11): owner emergency identifies
JOB_INSPECTION_FAILED; a controlled GUI-command-path upload reproduces executable
query WinError 5 for a compiler job member, followed by TerminateJobObject WinError 5.
The focused native inspection now waits at most one millisecond for the exact
process exit signal after failed identity queries, within the existing three passes;
unverified live processes still raise. Reopened launch-owner job handles now request
the required termination right, retaining exact contained ownership. Native regression
reproduces the missing-right failure before repair and passes afterward. Three
upload cycles pass after the exit check, then two final compile/verified-upload cycles
and deliberate compiler rejection pass with both repairs; rejection preserves serial
identity and confirmed cleanup. Affected platform/supervisor/firmware-owner/shared
tests pass 199 with one skip; static checks and 619-module boundaries pass. ARCH-002
keeps the small native-handle changes in the existing API owner with no dependency,
policy or firmware-source changes. Current settings were not edited. Exact exit,
guard/COM/helper release and removal of one archived failed-attempt staging directory
are confirmed; runtime remains stopped. Full-load and interrupted-flash acceptance
stay in the rig checklist. [Dated method/results](rig-wiring-evidence-2026-10-08/README.md#ino-upload-native-job-correction).

Output-format comparison (2026-10-08, `output-format-comparison`): inspected the
sibling CephVR1.0 writers/schema-v5 registry and saved October 6 session
`C:/Data/projects/reiter-cephalopod-vr/cephvr-data/20261006_ephys-pilot/SP0002-151412/protocol-data`,
then compared current CephVR2.0 output planning and all three scientific writers.
The existing date/experiment/subject-session layout and `protocol-data` /
`spikeglx-data` split are shared. [E04](../docs/architecture/supervisor.md#e04)
removes trial-number filename suffixes, adds UUID identities, replaces session-summary
JSON with lifecycle JSONL, and uses `SCHEMA.json` instead of `SESSION_SCHEMA.json`.
[A07/A08](../docs/architecture/acquisition.md#a07) replace acquisition/video CSV pairs
with one camera JSONL stream containing received frames, drop/video correspondence,
clock descriptors and terminal accounting. The Oct9 implementation adds identified
nominal-slot padding under A07/A08 and E13/V12; the owning
[acquisition](acquisition.md) and [stimulus](visual_stimulus.md) reports retain current
validation and native limits. The historical 1.0 example reports five padded Behavior
frames and nineteen duplicated VR frames.

[T15/T19](../docs/architecture/tracking.md#t15) replace `_tracking_state.csv` with
typed pose/result/reset/discard/completion records. The owner's subsequent decoded
storage choice replaces base64 feedback/escaped stage payloads with schema-2 JSON
objects; [implementation evidence](tracking.md) records local checks and limits.
[T35/T38](../docs/architecture/tracking.md#t35) use relative drive
in px/s and 1/s, not the legacy mm/s/deg/s velocity columns.
[E13/V13](../docs/architecture/visual_stimulus.md#e13) replace separate VR/stimulus
CSV state files with the always-retained prepared `_stimulus_LOG.json` plus Save On
render evidence/review video. The review video samples final corrected output tiles;
the legacy recorder captures its dashboard composite. Current SubjectMetadata moves
animal details into session configuration, uses `size_mm`, adds condition, and has
no legacy `weight_g` field. These are format/semantic changes, not a migration or a
claim that old readers can consume the new files.

Evidence scope: 16 `SESSION_SCHEMA.json` files and no 2.0-style session/schema/
scientific JSONL files were found by filename inventory in the inspected data root.
The 2.0 side is source/schema inspection at HEAD `7ba43b1` with concurrent local edits,
not an inspected production scientific session or new runtime/rig pass. The sibling
main ref reads `1082d917`; its dirty status could not be checked through `git -C`
under current permissions, so that ref alone does not identify the reviewed source
snapshot. No recording, device, runtime or scientific-data mutation ran.

Projector assignment retention (2026-10-08, G01 revision 130): explicit choices sync
immediately to local frontend preferences by stable display identity, including
Unassigned/missing displays, independently of a complete calibration or GUI closure.
A new Configuration/Ready GUI restores these as drafts and marks differences dirty;
active-session synchronization and explicit reload retain the controller base. Saved
mapping identity never changes controller state or triggers output. Profile install
now synchronizes the visible assignment dropdowns silently. Invalid/duplicate saved
preferences remain preserved and reported; failed writes retain the current draft.
The initial four restart/managed cases fail before repair. Final owning projector,
calibration and managed-configuration selection passes 53 with one existing horizontal
scroll/layout failure, already present in the earlier full suite. New retention cases
cover restart without closing/Setup, reordered/missing/returning inventory, explicit
Unassigned, invalid preferences, failed save, active-session isolation and explicit
reload. Ruff/format, four-source Win32 mypy and 619-module boundaries pass.
ARCH-002 puts bounded preferences/validation and silent control synchronization in
a focused helper; the existing Projectors panel retains UI/native inventory ownership.
No dependency/process or controller-history writer is added. These are isolated Qt
settings/display fixtures; actual multi-monitor restart/unplug acceptance remains in
the rig checklist. No hardware command or managed runtime restart ran.
[Raw validation and source context](rig-wiring-evidence-2026-10-08/projector-assignments-context.json).

Camera Disconnect presentation (2026-10-08, G01/G02): the button now uses the shared
red danger style for a connected camera and returns to primary styling when closed
or selecting an unconnected camera. Three existing camera-control Qt cases pass;
offscreen theme checks confirm the actual red/primary palette and both transitions.
Ruff/format, one-source Win32 mypy and boundaries pass. ARCH-002 keeps this small
presentation update in the existing cohesive camera refresh owner, without new
state or dependencies; no hardware command or managed restart ran.

SpikeGLX table presentation (2026-10-08, G01): the Stream column is hidden from
the mapping table while retained stream identity continues to roundtrip internally.
Five existing owning Qt panel cases pass; an offscreen rendered table confirms
zero Stream width and aligned visible columns after adding a custom row. Ruff,
format, single-source Win32 mypy and 618-module boundaries pass. ARCH-002 uses
the existing table's column visibility without new state, dependency or schema.
This presentation check sends no runtime/remote command.

Later G01 camera-selection increment (2026-10-08): selected config reloads after
managed inventory assignment changes, and Use-checkbox clicks select their row.
Camera/PFS Qt tests pass 27; selection is silent and preserves per-camera drafts.
Static/boundary checks pass. Earlier full-suite/physical results below predate
this increment. [Current evidence](rig-wiring-evidence-2026-10-08/README.md#later-camera-selection-correction).

Latest Windows/device execution (2026-10-08): reviewed committed `e4c653c..7ba43b1`
and repaired three observed integration defects under A11/E08/ARCH-002: invalid
diagnostic-stop after firmware reconnect, an extra native pipe-creation argument,
and invalid diagnostic-stop during control-release cleanup. Existing OFF proof,
deadlines, ownership and failed-close fencing remain intact; an unacknowledged
diagnostic Start remains uncertain until confirmed Stop/cleanup (owning regression
coverage, without physical missing-ACK injection). Real controller-owned
MCU diagnostics with acquisition disabled, supervised HEX upload and `.ino`
compile/upload, deliberate compiler rejection without serial handoff, active-D9
control release and final exact shutdown/COM cleanup pass. Behavior capture/display
and moved-GUI native placement pass twice. The later Tracking repair validates both
exact producer rings at Ready and release; the previous generic health shutdown was
a rejected-report path, not an established heartbeat timeout. Two physical Tracking
Connect/Show/Disconnect cycles now pass with restored settings and exact normal
shutdown. Failure reporting retains a bounded specific reason without relaxing
fencing/deadlines. Acquisition/affected-controller checks pass 363 with one skip;
affected static/boundary checks pass.
[Current Tracking evidence](rig-wiring-evidence-2026-10-08/README.md#tracking-connect-and-release-correction).
SpikeGLX still times out with a late unretrieved future failure. Eight existing GUI
clipping failures remain.

Earlier full Windows/offscreen suite (before camera-selection/Tracking repairs): **1463 passed, 8 failed, 5 privilege skips, 1 rig
deselection**. Separate native GPU smoke passes one; affected Ruff/format, Win32
mypy and boundaries pass. Baseline contracts/schema checks and native package build
pass. Test fixture path/privilege and asynchronous settlement/clock repairs are
distinct from the three product repairs. [Current dated methods, exact source
provenance, raw outcomes and cleanup](rig-wiring-evidence-2026-10-08/README.md)
retain every failure and scope. Runtime is stopped; saved settings are retained.
Remaining acceptance belongs to the [single rig checklist](rig-verification.md).
The original development-only migration assessment below predates this execution.

Controller Microcontroller ownership (2026-10-08) implements
[A10 revision 55](../docs/architecture/acquisition.md#a10),
[A11 revision 40](../docs/architecture/acquisition.md#a11),
[E08 revision 166](../docs/architecture/system-contracts.md#e08) and
[G01 revision 129](../docs/architecture/gui.md#g01). The controller owns the single
serial thread, boundary/keepalive arbitration, Configuration pin tests and supervised
`.ino` compilation / `.hex` upload. These operations work with acquisition disabled
and no acquisition service. Acquisition is an authenticated camera-trigger client;
its original deadlines, stop issuance and timing evidence survive the RPC hop.
CONNECT creates an exact claim; stale-claim calls cannot alter a later connection.
The final external manual preview releases its claim after OFF and camera cutoff;
remaining external previews retain ownership. Independent Snapshot Microcontroller
state prevents old camera reports from overwriting device/diagnostic state.

Control-loss cleanup waits for the camera claim's original release allowance while
fencing new execution and admitting OFF/release. Normal shutdown includes physical
COM/native cleanup in its retained cleanup/recovery deadline, clamped by the
application backstop. Failed closure remains visible and fenced. Serial timing reload
requires a released port; a connected owner cannot silently change watchdog policy.
The local review GUI now opens no COM handle, including real-inventory mode; device
tests use the managed GUI. Microcontroller config/policy pair 1 owns generic defaults
and fixed policy, with a canonical digest; acquisition pair 18 retains camera defaults
and distributed compatibility fields. The existing pyserial 3.5 dependency now belongs
to the base install, independent of acquisition extras.

Final portable command covering acquisition/controller/supervisor/shared/client passes
**812 tests / 5 platform skips / 3 marker exclusions** (12.21 s). Fifteen real authenticated
loopback controller tests pass (1.14 s), including forged/stale peer rejection, exact
metadata deadlines/replay, disabled-acquisition pin tests and `.ino`/`.hex` Upload,
independent state, normal shutdown and control-loss claim ordering. Eleven offscreen
GUI Microcontroller/firmware cases pass (6.94 s), including read-only review behavior,
cleanup/failure gating and clearing retired diagnostic/connection state. These
checks exercise mocked device/tool boundaries, not native board flashing or physical
camera timing. Ruff check/format pass 491 files; Windows-target mypy passes 427
sources. Boundaries inspect 616 modules with zero violations; existing size advisories
retain their cohesion review. All 19 protobuf bindings regenerate. Five edited TOMLs
parse; canonical acquisition 18/Microcontroller 1 load. Twelve documents / 490 local
links and anchors pass, and whitespace is clean.

ARCH-002 review keeps runtime/assembly/service as composition/transport and the
rehomed serial owner as the existing single-connection state machine; its protocol,
channel, pulse scheduling and serial adapter remain separate. Device, firmware source,
image/tool/handoff, authenticated admission, lifecycle, health and bootstrap are focused
modules with records/callbacks rather than whole-runtime references. Acquisition's
old keepalive/firmware handling and the review GUI serial worker are removed.
Manual Preview retains the single stop/cutoff/transfer/remaining-output coordination
chain with focused helpers; its new claim-release operation lives in the existing pulse
observation helper. Retained OFF proof allows an uncertain closing bridge to finish
cleanup without attempting fresh commands on it. Cancellation uses the caller's
original deadline rather than an invented transport allowance.

The earlier selected-sketch increment passed 26 firmware/source cases, four offscreen
GUI cases and 771 portable backend/shared cases before this ownership migration;
those are historical development results at acquisition policy 17. Current raw board
installation evidence keeps its original ownership/source scope. All results refer to
the shared uncommitted tree at HEAD `e4c653c`, not an immutable rig revision. The
AMD64-Windows native packaging guard blocks `python -m build --no-isolation` here on
macOS; no packaging pass is claimed. No actual Arduino CLI compilation, flash,
hardware command or GUI/runtime restart ran. Full restart with the new config/policy
files is required before rig testing. Installed CLI, Uno AVR core and sketch libraries
remain prerequisites; native/device/timing acceptance stays in the
[single rig checklist](rig-verification.md#managed-mcu-and-camera-gui-verification).

Projector identifier wording (2026-10-08), [G01 revision 127](../docs/architecture/gui.md#g01):
shared review/runtime mapping table and related labels use Display ID. The existing
inventory/layout check passes; numbering and physical mapping behavior are unchanged.


Projector JSON update (2026-10-08), [G01 revision 126](../docs/architecture/gui.md#g01):
one Load JSON / Save as row restores all Projectors experiment settings and reusable
geometry/color profile references, preserving current physical assignments. Version 3
restores pulse/participation by logical face; numeric versions 1/2 and legacy runtime
profiles remain supported. Offscreen 1280×900 inspection confirms the compact shared
page without the redundant import button; its temporary image/settings were removed.
No hardware command or managed-runtime restart ran.

The full portable GUI run records **313 passed / 2 failed in 251.47 s**: one new
roundtrip test had an incomplete inventory fixture (corrected; the focused seven-case
file/native-profile check passes); the untouched Protocol advanced-alignment check
showed a 12 px displacement but passes on independent rerun. It remains an explicitly
tracked intermittent follow-up, so this increment claims no blanket GUI-suite pass.
The added native-rebinding test validates the submitted profile through the backend's
JSON model, with measured-reference/shared-output preservation and current monitor
properties. Ruff lint/format pass six affected files, Windows-target mypy passes five
sources, and boundaries inspect 608 modules with zero violations. Final projector/tank/
calibration selection passes **40 in 30.60 s**; three final install/roundtrip cases pass
in 4.38 s after retaining the authoritative-state profile reset (empty/new state cannot
reuse prior runtime references). Physical projector,
Windows/DPI and optical acceptance remain pending under E15.


Review/runtime layout parity follows [G01 revision 125](../docs/architecture/gui.md#g01)
and [G02 revision 34](../docs/architecture/gui.md#g02): both actual window compositions
retain shared DashboardWindow pages. Camera Connect starts capture and opens the
confirmed run's backend-owned preview; Disconnect stops both. PFS/source/rate restore
per camera, with filename-only PFS display. Device hover colors remain stable; Tracking
places Load/Save beside Pipeline and diagnostics/annotation in a separate action row.
Controller authorizes and owns explicit Configuration-only firmware Upload,
serial handoff, the supervised native helper and fresh stopped-output verification
under [A11](../docs/architecture/acquisition.md#a11)/[E08](../docs/architecture/system-contracts.md#e08).
Details and rig limits are in [acquisition](acquisition.md); always-grid calibration
asset changes are in [Visual Stimulus](visual_stimulus.md).

Matched-state checks compare controls and card/header geometry at 1280/720 across
navigation and all subtabs; offscreen render inspection confirms Cameras,
Microcontroller and Tracking layouts at both widths. The older Tracking-crop draft
migration fix preserves the annotation dictionary; the owner's saved file previously
restored twice with unchanged hash, while invalid files remain preserved/reported.
The final portable GUI command passes **309 tests in 226.30 s**. Acquisition/controller/
supervisor/shared suites pass **748 in 12.01 s**, with five Win32-atomic ring skips
and three marker exclusions; this shared-tree run includes concurrent runtime work.
Ruff lint/format pass 525 files, Windows-target mypy passes 454 sources, and boundary
checks cover 607 modules with zero violations. All 19
Protobuf sources were regenerated from owning schemas. Native Upload, camera output,
Windows/DPI clipping and optical calibration remain rig acceptance. The updated
isolated review GUI is open after approved desktop launch; native visual inspection
is not claimed and no hardware/controller command ran.

The owner has reopened the runtime and reports incorrect preview placement. Native
read-only bounds reproduce insufficient space for the default square and x=0
fallback over the GUI. Placement now fits available right-hand space and aligns
visible physical frames under G01 revision 123. Ten selected GUI checks, four final
native/reader checks and 549 affected-owner/client checks pass (two privilege skips);
static checks pass. Current runtime ownership is preserved; full restart and actual
camera viewing remain outstanding. [Current camera placement assessment](acquisition.md#current-windows-wiring-checks).

Owner-requested stop: controller `73987d0f-0d80-4f63-a646-3dba430048bb`
normally shuts down successfully. Exact launcher exit receipt confirms all owned
processes absent; independent native inventory finds zero managed Python processes
and the application guard is free. Runtime was left stopped for that request, with no repeated
firmware installation or restart. [Shutdown evidence](rig-wiring-evidence-2026-10-07/mcu-installation-and-preview.md).

The earlier owner recurrence was traced to MSIX AppData virtualization, not a missing
publication delay. The owner's ordinary CMD reports File Not Found, while native
agent CMD on the same volume sees the logical path. GetFinalPathNameByHandle
resolves that file into Codex's package `LocalCache/Local`; all inspected user SIDs,
integrity and UAC flags agree. [Decisive file identity/token evidence](rig-wiring-evidence-2026-10-07/replacement-msix-visibility.json)
and [read-only idle controller state](rig-wiring-evidence-2026-10-07/replacement-msix-before-state.json)
are retained. Microsoft's [MSIX virtualization rules](https://learn.microsoft.com/en-us/windows/msix/desktop/flexible-virtualization)
explain this merged view. The owner now authorizes moving the namespace. E08 revision
170 selects `%USERPROFILE%/.cephvr2/runtime`, outside AppData, using the existing
private ACL and credential/recovery helpers. Missing or relative USERPROFILE fails
without an AppData fallback. ARCH-002 review retains the single root selector and
existing exact replacement event/exit-receipt mechanism; no new service or state
owner is needed. Normal shutdown precedes guard-exclusive preservation of all 136
recovery records, with identical source/destination hashes and originals retained.
Old endpoint/generation credentials are not imported; startup provisions fresh ones.

Oct9 recurrence: the owner again reports the ordinary-terminal endpoint timeout.
The current Codex child shell sees the descriptor for controller
`ebb927d3-ad19-4f61-b52b-a906cdb44a57`; the owner's exact base-Python launch command
shows Y/N here, and answering N preserves that generation. Launcher/shared
credential/recovery baseline tests pass 66 with one privilege skip. The initial
baseline command named a nonexistent test file and collected nothing; retain it
separately. [Baseline method and provenance](review-evidence-2026-10-09/runtime-replacement-baseline-context.json)
remain historical diagnostic evidence. After the authorized move, the owner's exact
base-Python command reaches Y/N in native exec PTY: N preserves the exact controller
generation; Y starts a new generation only after the former launcher's matching
all-owned-processes-absent receipt. A Codex child shell and a Windows Shell-launched
helper independently resolve the endpoint to the same physical profile path and
exercise the real N branch with injected interactive input. Both report no package
identity (API result 15700); artifact tags are launch-context labels, not evidence
of a packaged process. The owner's own terminal has not been manually retested.
Final GUI relaunch succeeds in the same idle controller generation; retained V20
pacing warning still blocks new experiment Setup. An early final-start attempt
entered the duplicate prompt before launcher exit; retire only its verified task
helper and retry after exact release. Preserve failed-attempt logs alongside
[current commands, source hashes and native outcomes](review-evidence-2026-10-09/runtime-root-context.json).

The preceding duplicate launch failed before Y/N because its replacement descriptor was
absent. Current read-only inspection finds the earlier controller
`73987d0f-0d80-4f63-a646-3dba430048bb` endpoint intact in the normal Windows
profile, and the owner's exact base-Python command now displays Y/N; two native
checks answer N and preserve it. The original failure's runtime path/timing are
unknown, so startup timing versus a different profile directory is not proven.
Source exposes guard-before-publication timing; [E08 revision 163](../docs/architecture/system-contracts.md#e08)
now bounds missing directory/descriptor retries by the existing startup
health-silence budget. Unsafe/invalid records still fail immediately, and the
exact event remains retained before asking. Persistent absence reports the exact
path; ordinary native launch failures print a concise error instead of a traceback.
Five owning regressions fail before the change; 37 launcher cases pass after,
219 shutdown/supervisor/shared/client integration cases pass (one privilege skip),
and three real delayed-publication/private-event checks pass, including a missing
initial runtime directory. Ruff/format (eight files), Windows mypy (six launcher
sources) and boundaries (604 modules, zero violations) pass. ARCH-002 keeps the
retry in the focused replacement owner and startup-budget injection/error rendering
in launcher composition; no policy, dependency or process owner is added.
[Dated replacement evidence](rig-wiring-evidence-2026-10-07/replacement-context.json).
No live Y/termination/restart or device operation occurs in this repair.

Earlier [manual installation and camera retest](rig-wiring-evidence-2026-10-07/mcu-installation-and-preview.md)
verifies protocol-3 Uno upload/CAPS, generated D9/D10/D11 counts, managed D9/D10/D11
Test/Status/Stop and D9 automatic timeout. Real Behavior HighGUI Start/Show/Hide/native close/reopen/Stop
passes with acquisition-owned native window. Tracking's readback revision handoff
is repaired (54 focused, 535 integration passes/two privilege skips; static checks
pass), but its subsequent Start fails amid recurring coordinator-health shutdown.
Exact launcher absence is confirmed before restoring a fresh GUI runtime.
Firmware installation is complete. The later Oct8 exact two-ring repair supersedes
this Start failure; sustained/full-workload acceptance remains open.

Earlier owner D10 test fails without pulses. The camera diagnostic now applies its
selected output configuration before starting; controller completion forwards
the backend rejection message and accepts the matching protocol-3 version.
Seven targeted regressions and **526 acquisition/controller/client tests pass**
(two privilege skips); static checks pass. This corrects a protocol-version gap
missed by the previous counted suite. Runtime restart/manual installation and
actual generated counts were pending at that repair's handoff; the authorized
installation above supplies later board evidence.
[Current MCU diagnostic assessment](rig-wiring-evidence-2026-10-07/mcu-camera-diagnostic-repair.md).

Latest MCU diagnostic implementation follows the owner's choice to count generated
transitions on the board under [A11 revision 37](../docs/architecture/acquisition.md#a11).
Protocol 3 host/firmware are prepared; counted changes were validated at policy 13.
Concurrent camera-viewer policy 14 retains MCU protocol 3; 45 owning cases pass again.
GUI reports firmware-generated
counts separately from observed input edges. The Uno image builds; 508 affected-owner
integration cases and six focused GUI cases pass (two integration privilege skips).
Source mypy, Ruff/format and boundaries pass. Matching manual installation and on-board
counts were pending at that increment; the later installation above supersedes that status.
Restarting the new host requires protocol 3 firmware.
[Image and validation](rig-wiring-evidence-2026-10-07/mcu-counted-diagnostics.md).

Camera display now follows the owner's [A10/G01 OpenCV ownership choice](acquisition.md#current-windows-wiring-checks).
Current presentation adds bounded initial GUI-edge positioning, square
aspect-preserving padding, pointer wheel zoom and double-click fit reset under
acquisition policy 15. Native isolated windows verify placement, square image
areas and cached-frame wheel/reset redraw; 549 affected-owner/client and eight
selected GUI tests pass (two integration privilege skips). Geometry/pixel helpers
remain focused, and static/boundary checks pass. The current owner runtime remains
on its earlier loaded source; full restart and physical GUI/DPI acceptance are
still required. [Current presentation evidence](rig-wiring-evidence-2026-10-07/preview-presentation-context.json).
GUI sends exact-run Show/Hide; acquisition owns windows/private readers, confirms
first-image display and native release, and reports visibility independently of
capture. X/Hide leaves capture running. Failed release retains its ledger blocker
while SDK/pulse cleanup is attempted; delayed observations cannot complete commands
or undo newer visibility. The former Qt reader and GUI frame-transfer path are removed.
526 affected-owner/client tests pass (two privilege skips), 17 GUI/bridge tests pass,
and final first-image/reopen refinements pass 64 focused checks. Two real Win32
OpenCV windows/latest-frame/X closure pass with isolated rings; package/dependency
and static checks pass. These are native display/implementation evidence, not physical
camera, heartbeat or full-load acceptance. That implementation increment preserved
the active runtime; later authorized installation and Behavior viewing/release are
recorded above. Original full-suite failures remain open.

Current Windows rig execution (2026-10-07, `08d146d` plus the generated-SWIG mypy
exclusion): [raw evidence, commands and limits](rig-wiring-evidence-2026-10-07/README.md).
The full offscreen Windows suite reports **1,252 passed, nine GUI failures, four
symlink-privilege skips, one rig deselection**. A separate native Qt run crashes
with access violation during GUI fixture teardown. Eight failures concern
layout/clipping; one compares normalized Qt paths to native path spelling.
These are current Windows findings; the earlier development pass below remains
historical evidence. Ruff/format, source mypy, boundaries, contracts/schema checks
and AMD64 package build pass. Generated Protobuf bindings were stale on arrival
and regenerated; source mypy now excludes only the generated Basler SWIG wrapper
under ARCH-002, preserving checks of handwritten adapters.

Managed startup registers all seven roles and stays alive for over an hour while
desktop inspection awaits approval. Automatic GUI control and explicit headless
takeover pass. Injected exact GUI loss followed by `--reopen-gui` creates one fresh
GUI in the unchanged controller/application generation. Interactive replacement
N preserves the exact endpoint; Y obtains the old process-absence receipt before
the successor generation. Authenticated normal shutdown succeeds; exact exit
receipts, no remaining managed processes and a free application guard are verified.
Mouse-driven close, reconnect warning acknowledgement and viewers remain unverified:
the computer-use app approval timed out. No full experiment ran.

Camera activity reveals a current E08 blocker: after two successful Behavior
Start/Stop cycles and a Tracking PFS import, camera workers report
`COORDINATOR_HEALTH_LOST`, causing application shutdown. See the
[acquisition assessment](acquisition.md#current-windows-wiring-checks).
The owner's later [controller-route MCU console](rig-wiring-evidence-2026-10-07/owner-mcu-console.md)
reports completed D2/D9/D10 diagnostic Start/Stop pairs, including 120 D2 rising
edges. Output zero counts are expected; ordinary MCU Status/Stop and physical
waveform/receiver checks remain separate unresolved acceptance work.
The owner's follow-up requests physical signal tests using the open SpikeGLX display.
Initial MCU output feedback correction under G01/A11: Trial state showed firmware-reported
HIGH/LOW and camera tests show running/stopped pulse output; only input diagnostics
show rising-edge counts. Six existing GUI diagnostic/control cases pass, GUI mypy
checks 124 sources, Ruff/format pass, and 598 backend modules have zero boundary
violations. ARCH-002 review keeps this presentation change in the focused existing
panel without dependencies or ownership changes; existing size advisories are
unchanged by it. Physical channel observations are pending, not new rig passes.
It is superseded by counted diagnostics above; its results retain their original
scope. The running GUI remains active with its previously loaded code. [Focused evidence](rig-wiring-evidence-2026-10-07/mcu-output-feedback.md).
The E12 read-only SDK connection times out, then logs a TCP connection failure
and an unretrieved late future exception. Saved endpoint/inventory readback succeeds;
remote recording, wiring proof and paired Setup remain pending. No mapping update
or remote mutation was issued. Existing scientific/encoder deferrals remain.

The owner-requested runtime wiring is implemented in the existing managed application.
Review and runtime share the current Dashboard, Protocol, Devices and Tracking layout.
Luna audited and implemented the work; Sol 6.1 prepared the plan and reviewed the code;
Astra reviewed the design and final source. All reproduced development findings are
repaired. Sol and Astra accept the final development implementation; Windows/rig
acceptance remains separate under [E15](../docs/architecture/system-contracts.md#e15).

| Area | Implemented and reviewed behavior |
| --- | --- |
| Configuration and commands | Full E07 proposals against the accepted revision, optional subject metadata, ordered trials/seeds/gaps, recording and projector/Tracking settings; exact captured Setup identity; stale drafts remain visible without rebase/replay |
| Authority and close | Retained warnings before control acquisition, exact prompt/command identity, safety actions during preparation, explicit discard/cancel, and history-save completion before GUI closure |
| Tracking | Selected-stage diagnostics including image-only/partial pipelines, real ordered preview frames, bounded exact-scope live image/overlays/timings, explicit acquired-frame annotation, and confirmed Close before editing |
| Projectors | Typed pacing and held policy propagation; first-use untimed V01 calibration through the V15 correction pipeline; exact output/context ownership, prior-display restoration, and bounded active/in-flight/lost-owner cleanup |
| SpikeGLX | Saved host endpoint readback, serialized SDK/inventory/monitor/stop ownership, exact trial stop timing, digest-guarded pulse mapping updates and bounded off-loop persistence with truthful late outcomes |
| GUI relaunch | Explicit same-generation reopen after exact prior release, authenticated fresh launch, retained uncertain/partially created successor identity, terminal RELEASED reconciliation and a responsive launcher backstop |
| Ownership gates | Configuration and Setup recheck unresolved diagnostic, cleanup and inventory ownership at admission and atomic commit, preserving valid Ready-edit cleanup |

Final review exercised actual controller, coordinator, worker, GUI and supervisor
assemblies with only necessary OS/native boundaries adapted. This found gaps that
isolated helpers missed; the final regressions preserve those paths. In particular,
RPC admission is distinguished from worker Close application, cancelled pre-dispatch
validation is distinguished from uncertain dispatched work, and late file completion
is reported truthfully without freeing an in-flight writer early. Scientific values,
encoder feasibility and firmware deferrals remain unchanged.

ARCH-002 review accepts the retained controller admission/cleanup ledgers, interruption
transaction, GUI connection/dispatch owners, GL-thread display restoration and protected
source registry. Separable calibration rendering/preparation, GUI close/display/diagnostic
transport/codecs, timed SpikeGLX stopping and pure inventory validation have focused
helpers. Sol found no whole-runtime back-references in the additions. The boundary
checker reports 597 modules and zero violations; larger cohesive owners retain their
single state ledger instead of duplicating it across modules.

Themed captures made through actual `ManagedGui.install_snapshot` with inert RPC and
device discovery were inspected at 720px and wide sizes. Inputs are readable with
vertical scrolling, authority text agrees with the snapshot, and menu contrast is
corrected. The [final captures and fixture](runtime-wiring-evidence-2026-10-06/gui-captures-final-2026-10-07/)
are local visual evidence; Windows DPI, monitor identity and optical output remain rig
checks. See the [Tracking](tracking.md), [acquisition](acquisition.md) and
[Visual Stimulus](visual_stimulus.md) reports for their retained scope/evidence.

| Development check | Result |
| --- | --- |
| Combined offscreen suite, Windows/rig markers excluded | 1,240 passed, six native-platform skips, five deselected (128.20 s); frozen-source hashes unchanged |
| Ruff / formatting | Pass; 793 files formatted |
| Windows-target mypy | Pass; 683 source files |
| Backend boundaries | 597 modules, zero violations; cohesion reviewed above |
| Pure contracts | Tracking: 48 passed; Visual Stimulus: 42 passed and 79 subtests |
| Schema consistency | 19 Tracking and 11 Visual Stimulus JSON schemas match; isolated Protobuf regeneration matches all 57 bindings from 19 sources |
| Dependencies | No broken requirements; declared TIFF dependency installed to execute its decoder check |
| Native package build | Blocked by the existing AMD64 Windows DLL guard on macOS; Windows packaging remains required |

Exact commands, failures, repair checkpoints and scope are retained in
[command/provenance metadata](runtime-wiring-evidence-2026-10-06/baseline-context.json)
and [LOG](../LOG.md). The [source manifest](runtime-wiring-evidence-2026-10-06/final-source-sha256.json)
records 954 implementation/input hashes, including generated bindings. The baseline
commit alone does not reproduce the pre-existing dirty working tree; transfer the
complete current source when preparing the rig. PowerShell/native execution was not
performed on this host. The [single rig checklist](rig-verification.md) is the remaining
execution guide; local passes do not establish experiment acceptance.

2026-10-06 startup workflow: interactive duplicate launches now ask Y/N. A confirmed
replacement signals the retained owner-private launcher event; the existing owner
terminates its contained application job and verifies absence before publishing its
exact exit receipt. The requester requires that receipt and the application guard
before starting. Older launchers without an endpoint require one manual shutdown;
missing proof, timeout and competing launches never permit overlapping generations.
The managed GUI automatically claims an unheld lease once after synchronization and
reconnect warning acknowledgement, using ordinary AcquireControl. Other holders
require confirmed takeover; manual Release stays released within that connection.
[E08](../docs/architecture/system-contracts.md#e08) revision 162 and
[E03](../docs/architecture/gui.md#e03) revision 29 own these operator-requested changes.
ARCH-002 reused native owner-only events, bounded private record I/O and exit receipts
in one focused launcher module, with no service, dependency or runtime back-reference.
GUI/launcher/configuration checks: 246 passed, one deselected in offscreen Qt mode;
final controller/launcher checks: 238 passed. Scoped Ruff lint/format and Windows-target
mypy (seven source files) pass; boundaries: 555 modules, zero violations, unchanged
cohesion advisories. An initial GUI run aborted at Qt initialization before rerunning
successfully offscreen. Native event coverage was added to the existing Windows owner
module but not executed on macOS. Actual Windows replacement/control acceptance stays
in the [rig checklist](rig-verification.md#managed-device-gui); no runtime or hardware
was started for this increment.

Development-machine follow-up, 2026-10-06: repaired controller rejection of explicit
empty preview run IDs for inactive cameras. The real acquisition status reporter
and controller reproduce Start/Stop rejection before the fix and success after it;
active previews still require UUIDs. This applies existing A10/E07 release evidence,
without extending deadlines or accepting unknown closure. Acquisition/controller:
417 passed, five skipped, one deselected; Ruff lint/format pass; Windows-target mypy
256 sources pass; boundaries 555 modules, zero violations. Existing size advisories
are unchanged; the focused projection owner needs no extraction under ARCH-002.
Rig viewer/Stop acceptance remains open; see the [current acquisition assessment](acquisition.md#preview-recheck-stopped-by-owner-2026-10-06).

Latest handoff, 2026-10-06: owner stopped the Behavior D10 → Line4 preview recheck.
The direct receiver check yielded 41 frames in two seconds after verified upload
of existing CephVR2 firmware; prior legacy flash is backed up. Managed ready/started
evidence reaches acquisition, but operator completion still fails with
`exact completion missing`; GUI viewer and managed Stop remain unaccepted.
Capture-scope declaration, explicit closed preview identity, initial projection
revision and canonical warning UUID repairs are retained under E06/E07/A10.
See [current acquisition assessment](acquisition.md#preview-recheck-stopped-by-owner-2026-10-06).
The authenticated shutdown of generation `2dd0392f-54f9-4c83-a733-3ea0549872ef`
was followed by empty CephVR2 process inventory and successful application-guard
acquire/release. Temporary tracing is removed; no replacement runtime was launched.
These findings supersede older statements below about missing capture catalogue
scope and a retained running runtime. One intervening launch failed independently
with `VISUAL_STIMULUS_EVIDENCE` / invalid UUID; that defect remains uninvestigated.

Requested development cleanup removed 42 preflighted directories, 6,640 files and
201,368,736 bytes, including 81 tracked test artifacts and disposable SDK prototypes,
build outputs and caches. Focused fixture ignore rules were added. Experiment data,
configuration/PFS, production native bridge, dated evidence and firmware backup
were preserved. Later checks recreated small temporary/cache directories; no
further optional cleanup was performed after the stop. The
[cleanup manifest](device-connection-evidence-2026-10-06/development-cleanup-manifest.json)
records the completed removal.

The 2026-10-06 manual-preview resolution failure was isolated to pypylon's
unsupported Python-integer Win32 HANDLE constructor. The bounded typed native
bridge and verification are recorded in [acquisition](acquisition.md) under
A02/SYS-003. Preview failures now retain original worker evidence and possible
ownership until release. Real settings resolution/native blocking wake and both
managed connections pass. External preview testing stopped at the owner's request
to use CephVR1.0; preparation still fails because its camera capture scope is
missing from the function catalogue. Acquisition heartbeat rejection was isolated
to reporting before endpoint registration; registration now precedes health
reporting, with one subsequent native startup reaching preview preparation.
Broader startup acceptance remains open.

CephVR2.0 is closed on 2026-10-06: process inventory contains no 2.0 roles and
the application guard can be acquired and released. CephVR1.0 startup was then
reproduced with a bounded Python traceback: GUI construction retries opening
`%LOCALAPPDATA%/CephVR/runtime/controller/controller.log` and receives WinError 5.
Its legacy controller directory and log have empty inherited DACLs; the shared
runtime root has a protected owner-only ACE without child inheritance. This is
a runtime-path/security collision between versions, not camera connection proof.
Resolved in the owner-authorized follow-up: E08 revision 161 assigns CephVR2.0
`%LOCALAPPDATA%/CephVR2/runtime`. The one-time migration moved only canonical
generation directories and the protected recovery folder after preflight checks;
all moved entries retain their exact ACLs and file SHA256 hashes. Legacy runtime
now grants inherited FullControl only to the current owner. The native repair
changes DACL alone; PowerShell Set-Acl first requested unavailable
SeSecurityPrivilege after migration, without completing the access repair.
Windows PowerShell 5 also failed to load its security module before any mutation;
the available PowerShell 7 completed the migration. No credentials were printed.
The normal CephVR1.0 launcher now opens the fully rendered Experiment OS Dashboard
and its controller. No CephVR2.0 runtime was started. Scoped invariant tests:
10 passed, including native credential isolation and writable legacy log coverage;
Ruff lint/format, Windows-target mypy and boundaries (556 modules, zero violations)
pass. Existing cohesion warnings concern unchanged modules; the focused credential
helper adds no dependency or new coordination under ARCH-002.

Final Windows repair and one-time elevated follow-up (2026-10-01, baseline HEAD
`826984255e0a8469afccbda2dcaf8c642b528b33` plus uncommitted repairs): controller
202 passed; supervisor 106; shared 52; platform 46; launcher 10 and client 6 passed.
Whole suite: 759 passed with zero failures/skips, all Windows and bounded rig markers,
using dedicated elevated scratch. The owner removed exactly two POSIX-only tests;
native unsafe-DACL rejection remains. Standard-token default-temp full suite passed
755 with four symlink privilege skips; actual one-time elevation executed those four.
Elevation exposed missing startup dependencies in prepared Python; finite matching-base
VCRUNTIME140.dll/optional zlib.dll preparation now verifies source/copy hashes before
planning. Exact executing PID/image, venv imports and bootstrap proof passes elevated
and Medium-token default-temp checks. No persistent OS privilege/policy change.
[Dated evidence](rig-audit-2026-10-01/README.md) preserves failed attempts, latest JUnit,
commands, startup provenance and scoped cleanup; full experiment acceptance remains open.
Setup Ready/failure and successful Start use the existing terminal completion
owner, preserving failure codes, publication order and active-session retention.
The native intrinsic helper repairs cross-process ring atomics. Verified prepared
Python images preserve the fresh virtual environment: a live native regression
confirms launched/code PID and OS image, one job member and inherited bootstrap.
E04 reservation guards preserve exclusive ownership while Windows closes the byte
lock for quarantine, including failure; default-path recovery persistence passes.
Fixtures now respect Windows sharing/permissions and await actual async outcomes.

An earlier proposed launcher invocation was rejected by automatic approval review
for potential managed service/hardware effects and was not executed at that time.
The later 2026-10-05 owner-authorized managed launch and its Visual Stimulus failure
are recorded in the frontend section. Focused checks do not establish full E04/E08
application/device/workload acceptance. Capacity bypass was not
established; authorization checks the same capacity under the lifecycle lock.
ARCH-002 review keeps the 502-line reservation owner cohesive around namespace
ownership; native tests remain one platform-fixture module rather than per-fix files.

- Controller lifecycle, configuration validation, live control leases, RPC admission,
  output planning, serialized central metadata, preparation handoffs, incident handling,
  camera/preview forwarding, and headless control.
- Supervisor launch registration, health/evidence forwarding, cleanup obligations,
  independent emergency reporting, and bounded shutdown.
- Shared identity, command retention, ingress bounds, policy loading, credentials,
  resource/incident proof helpers; Windows jobs, process handles, guards, bootstrap
  pipes, private ACLs and publication helpers; persistent external launcher.
- One Python project with backend-owned packages, generated Protobuf bindings and
  type stubs, configured development tools, reproducible generation in package builds,
  and tests organized by code owner.

Components use focused typed records, peer operations and shared authoritative state.
Controller control/lifecycle/device/incident/metadata/transport owners and supervisor
registration/health/recovery/shutdown owners are assembled by their coordinators.
RPC adapters retain authentication and admission. Source review covered cleanup
fences, partial Setup, cancellation, original deadlines, command retention, durable
metadata and process ownership; static comparisons do not prove execution.

The module entry point calls the controller CLI. Mutable incident retention belongs
to `controller/incident/registry.py`; shared proof validation stays in `shared/`.
The acquisition-specific audit corrections are recorded in [acquisition.md](acquisition.md).

Supervisor simplification under ARCH-002 removes unreachable registry rejections,
shares worker channel revalidation/cache management and session/trial containment,
and separates native process exit evidence from shutdown outcome ownership. Camera
and persistent Visual Stimulus launch scopes remain distinct. Independent delivery still uses
bounded asyncio tasks; no additional package, public interface or policy change was
needed. E04/E06/E08 emergency reporting, original deadlines and cleanup/exit evidence
remain with their existing owners. Existing recovery/retention findings below remain
outside this refactor.

A second behavior-preserving pass gives the acquisition (`acquisition_worker.py`) and
Visual Stimulus worker controllers one interface (`WorkerControl`), so shutdown loops
over them instead of duplicating each step; acquisition's separate cleanup module was
merged into its controller. `shutdown_owned` is split into named steps with one bounded
polling helper and one outer-deadline expression. `GrpcOutbound` extends the worker
transport instead of re-declaring its methods, with one call helper and the port now
declaring channel retirement and close. Work scope, live launch phases and backend
role sets each have one definition, and the health monitor tick and tracking-release
forwarding are separate methods. Error codes/messages, lock scopes, deadlines and side-
effect order are unchanged; two observable differences are accepted: process-exit polling
sleeps are capped at the remaining deadline, and a registration with several faults can
report a different first error (single-fault errors are unchanged). Windows-only
`startup.py`/`main.py` and the registry `confirm()` state machine were intentionally left
alone.

Controller simplification under ARCH-002 shares bounded backend interruption delivery,
moves recovery-log draining and writer sealing into the existing metadata owner,
and consolidates camera-operation retirement in its retention owner. E04/E05/E06/E07/E08
lock scopes, original deadlines, terminal evidence, durable-write order and cleanup
outcomes remain unchanged. No dependency, schema, public RPC or policy change was
needed. Setup and manual camera readback keep distinct admission/adoption transactions:
their validator and ownership requirements differ, so merging them is not a safe
mechanical simplification.

A second controller pass removes unread wiring (constructor parameters, attributes and
three mirrored configuration fields), the static file-policy fallback and the
five-layer `recovery_log_done` hook, and gives repeated patterns one owner: bounded
warning retention (`ControlState.add_warning`), rejected receipts/admissions
(`controller/receipts.py`), affected-resource and reservation-unconfirmed predicates on
`Attempt`, and the backend-name set. Backend command wrappers, AbortNow/Shutdown
admission, reservation finish, trial-log documents, admission failure handling,
report-retention conflicts and the shared backend cleanup dispatch (Setup cancel and
finalize) each have one implementation. `ControllerRuntime` now keeps wiring and thin
delegators: startup-recovery installation moved to `OperatorPrompts`, authority status
capture to `AuthorityStatus`, the manual-cleanup warning to its cleanup owner, and the
AbortNow/Shutdown precondition to the one predicate in `SessionCommands`. Settings and
output resolution moved from `setup_execution.py` to `setup_resolution.py`, and
oversized Setup, interruption, completion and configuration functions were split into
named steps. Lock scopes, deadlines, durable-write order, identity checks and message
text are unchanged; one accepted observable difference is that warnings recorded at
sites that previously did not trim are now bounded in memory (published snapshots
already applied the same cap). The controller backend port keeps
`apply_camera_settings`/`apply_pulse_configuration` for the open owned-camera-edit task.
`startup/application.py` (Windows-only, untested here), `transport/ingress.py` (no direct
test), the authority-loss/evidence/recovery-inspection state machines and the Optional
fail-closed dependencies were intentionally left alone.

## Unresolved findings and limitations

Oct16 local Abort/preview reliability work is complete; native acceptance stays open.
Interrupted cleanup is requested before trial/session metadata sealing, and exact
admitted cleanup can supply current-trial closure without normal Finished or invented
stop times. Registered output paths, frozen-set recovery bounds and overlapping
Abort/finalization are covered. The preview guard is retired only by successful
native device Close; failed Close and retained-device uncertainty stay fenced.
[Acquisition assessment](acquisition.md) owns details and
[Oct16 validation](runtime-evidence-2026-10-16/dev-reliability/context.json) retains
source/test scope. Historical forty-second Abort and preview-blocker evidence below
is not relabelled as a native repair pass. Existing E04 metadata-completeness and
unrelated race/audit tasks remain open.

Oct15 `gui-empty-variation-group` [gui]: owner reports GUI exit after adding a
group with an untouched empty variation row; an error was shown, text unavailable.
Under [G01/G02](../docs/architecture/gui.md#g01), invalid input must preserve the
draft and block mutation with an action-time warning. New owning dashboard cases
exercise native Windows button clicks/focus changes for blank and sample programs,
warning dismissal, row removal and successful subsequent group creation. Both pass;
related persisted-rule/random-group cases also pass (four total). No production
defect or fix is established. Initial suspicion of an exception in dirty checking
was not reproduced. Read-only Windows Application events show only an older
09:45 cephvr-python AppHangTransient, not a matching crash. Runtime traceback/error
text remains needed; local widget tests do not establish live controller equivalence.

Oct15 local probes confirm two existing TODO defects despite the passing suites:

- `calibration-live-update-rejection` is repaired Oct16 under V01/E06/G01.
  Explicit renderer rejection clears the exact pending Update/expected receipt and
  leaves the confirmed active projection and Setup block intact. A subsequent
  valid Update is admitted; uncertain transport outcomes remain fenced. Real
  ProjectionStore coverage exercises rejection/retry for all three live views.
  Device-admission25/controller522 and authenticated calibration3 pass; scoped
  Ruff/format, Win32 mypy and boundaries698/zero violations pass. Existing owners
  and test module are retained under ARCH-002, with no policy/dependency change.
  [Current local evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
- `controller-config-inactive-backend-defaults` is repaired Oct16 under E07.
  Missing/malformed inactive acquisition defaults produce a startup configuration
  warning without filling invented values or replacing saved settings; active
  acquisition still fails strictly. Setup reloads control limits/policies without
  rereading saved history or backend defaults; its active file-policy loader remains
  strict. Configuration/Setup38 and controller528 pass, including actual admission
  with malformed inactive files and unchanged current configuration. Scoped
  Ruff/format4, Win32 mypy3 and boundaries698/zero violations pass. Initial optional
  return annotations were corrected after mypy; no policy/default file changed.
  [Current local evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).

The original probes used local fixture adapters/config copies; current repair status
is stated above. Remaining audit/race/logging concerns keep their unverified status.
[Reproduction outputs and exact scope](runtime-evidence-2026-10-15/todo-projectors-off/context.json).


Current dev-machine triage (2026-10-13, source `4a62844`, macOS/Python3.11.15):
latest combined evidence verifies nominal60fps and repeated reset; the old39.47fps/
warning-shutdown statements in TODO and the outstanding rig checklist are corrected.
Historical workflow observations below retain their original scope.

| Standing issue | Work possible on the development machine | Remaining acceptance |
| --- | --- | --- |
| Failed-Setup renderer cleanup rejects an unknown command | Local worker recovery formerly submitted an unregistered worker-issued shutdown and forwarded its cleanup as coordinator-issued evidence. The repair retains this local command/result on the worker query route; the coordinator still rejects unknown IDs (E06/E08). Local regressions pass; see validation below. | Repeat the native failed-Setup/prior-calibration workflow; the full historical failure is not reproduced here. |
| Acquisition finalizer calls a departed controller | Teardown tolerates MCU Close UNAVAILABLE only after exact PID/creation-time exit confirmation, retaining the unconfirmed claim and reporting it (A11/E08). Live/unknown process and other RPC failures propagate. Local regressions pass; see validation below. | Native orderly shutdown and exact release. |
| Repeated manual preview hits MCU pending/unavailable and retention capacity | Reproduced fourth-readback capacity failure: each completed result retained a16MiB reservation. Explicit terminal completion now charges actual result bytes while preserving in-flight capacity, exact replay and300s retention (E08/A02). MCU pending is separately unproven; lease-turnover cleanup fences remain. Local regressions pass; see validation below. | Repeated real preview reuse in one generation with lease/claim state captured. |
| Review/camera recording loss | Profile bounded drain/padding/copy behavior, test backpressure and prepare measured changes (V12/V28/A07). The recording owner still waits up to5ms between unresolved writes. This is a cost, not proven NVENC saturation. | Combined Windows/GPU/camera throughput, zero-loss and optical timing. |
| Calibration loss and stale ordinary diagnostic bundle | Trace actual save/restore paths and validate regenerated all-VSync assets (G01/V01). Current normal-close tests pass; reported loss has no established root cause. | Actual closure-path reproduction and physical calibration. |
| Windows projector overflow, hover lookup and native picker exception-hook failures | Improve portable layout/lifetime coverage and inspect source (G01/G02). Local layout passes do not resolve Windows failures. | Windows native/DPI/pytest compatibility. |
| Long image protocols | Complete image readiness/lookahead/miss contracts; accepted bounded residency remains unimplemented (V04/V11). Critical miss behavior still requires an owner choice. | Native memory/performance and full-load acceptance after implementation. |

Local generated bindings were stale: controller and ManagedGui imports failed on
`MICROCONTROLLER_SIGNAL_KIND_EYE_TRACKING`, already present in authoritative contracts.
`python tools/generate_contracts.py` regenerates19 ignored Protobuf sources and clears
that blocker without editing contracts or handwritten runtime code. Focused tests then
pass222 (two deselected); nine offscreen GUI checks pass, including normal calibration
close/reopen and projector layout. Authenticated communication/startup recovery/shutdown
checks pass29 after granting loopback access; the sandbox attempt had five bind failures
and24 passes. Boundaries inspect667 modules with zero violations and existing cohesion
advisories. Exact commands and limits are recorded in LOG under
`runtime-dev-machine-triage`; this is sampled review, not a full runtime audit or rig pass.
That initial triage performed no runtime repair or operator/device mutation; the later
owner-authorized repairs above are separately validated below.

Oct13 local repair validation (source4a62844 plus retained patch): Luna implements,
Sol6.1 independently analyzes/integrates, and Astra approves the final source with no
actionable blockers. The affected acquisition/controller/supervisor/shared/Visual
Stimulus suite passes1316, skips five Win32-atomic ring cases and deselects four
Windows/rig cases. The final renderer teardown-helper extraction overlaps this run;
a final authenticated transport rerun passes9. Ruff check/format573 files, Win32
mypy486 sources, boundary check667 modules/zero violations and whitespace pass.
Sandbox transport attempts fail at loopback binding; unchanged permitted runs pass.
[Commands, source hashes and evidence](runtime-evidence-2026-10-13/dev-machine-repairs/context.json)
retain that scope. These are local implementation checks, not Windows/rig acceptance.

ARCH-002 review retains existing ownership and dependencies. Terminal reservation
compaction is explicit and atomic under the existing ledger lock; ordinary admission/
executor completion retains its original reservation. Native process identity uses
the existing exact PID/creation-time helper. Renderer local recovery uses its own
command-local ledger scope, retained admission/outcome and pruned routing marker;
worker/owner identity, original deadline and same-ID replay are checked before dispatch.
Its cleanup is queryable locally and never treated as a coordinator-issued command
or supervisor cleanup receipt. Endpoint teardown attempts continue after report-drain
failure while propagating the original failure. The new acquisition test_main module
owns host-entrypoint finalization, distinct from existing worker/bootstrap/coordinator
behavior tests; all other regressions extend their owning modules. Existing oversized
module advisories remain cohesive; no source split, dependency or policy change is needed.

The missing-SESSION_CONFIG recovery warning remains conservative: the durable
reservation identifies the session but cannot prove that it was unpaired. Removing
that warning would invent evidence. Likewise, MCU pending/unavailable is not proven
to share the readback-capacity cause; the historical probe repeatedly released its
control lease, which can legitimately fence new work while cleanup completes.
Capture exact lease/claim state during the deferred rig repeat. The local renderer
regression exercises RenderOwner/ReportBridge recovery delivery and finalized prior
scope; it does not reproduce the entire historical failed-Setup/calibration workflow.
Native acceptance procedures remain solely in [the rig checklist](rig-verification.md).

Oct12 `long-protocol-resource-scaling`: the authorized GUI portion now uses compact
source groups, scoped editing and viewport-only block painting under
[G01 revision 153](../docs/architecture/gui.md#g01). It no longer expands repetitions
for timeline loading/selection. Source JSON parsing, canonical validation and source
metadata traversal remain synchronous; this change does not establish latency bounds
for huge numbers of independently authored epochs. Explicit expanded/animated previews
and batch generation retain their 2000-occurrence engineering limits. The initial
CephVR1.0 concern was assessed by source review, not reproduced or benchmarked.
Image residency/readiness/miss behavior remains the separate
[Visual Stimulus follow-up](visual_stimulus.md#validation-limits).

The Oct8 missing application-shutdown history save is repaired and locally/native
verified in the current scope above under [E07](../docs/architecture/experiment.md#e07).
An abrupt crash or termination that cannot execute the controller's save path can
still lose accepted edits since the last successful save. Earlier Tracking-probe
restoration meant its captured startup snapshot, not recovery of the owner's
pre-crash in-memory edits; cleanup did not delete the history file. Do not reinterpret
that historical restoration as crash resilience or recovery of those lost edits.

Oct9 repairs follow [E06/E08 revision 169](../docs/architecture/system-contracts.md#e08),
[E04](../docs/architecture/supervisor.md#e04),
[E07](../docs/architecture/experiment.md#e07) and
[E12](../docs/architecture/synchronization.md#e12):

- Camera-worker retirement sends typed retained Cleanup operation/lifecycle evidence
  through the existing authenticated ConfirmLaunch route before Shutdown, then replays
  the identical request after exit. Acknowledgement fences only that exact expected
  exit; live ownership remains retained. The coordinator checks its
  exact resource/output obligations; supervisor independently checks child/work/owner
  identity and exact process/job absence. Both independently delivered Cleanup records
  must arrive within the original deadline, including guarded retained-query recovery.
  Workless Configuration retirement is supported; discharged failed outputs remain failed.
  Queries, exit and quiet liveness do not become closure evidence; persistent renderer
  session cleanup remains distinct.
- Released launch records stay pinned for active work and through the configured
  replay window after both release and work finalization. Capacity refuses new admission
  instead of evicting unexpired canonical replay evidence. Finalized-work bookkeeping
  is bounded by retained records; obsolete release-order state is removed.
- Startup inspection distinguishes exact late-Finished/incident reconciliation from
  terminal startup recovery. Malformed/unknown records remain unconfirmed; terminal
  recovery must still follow session end and remain last. Pre-activation Shutdown
  settles attempt-owned Setup prompt futures through the existing cancellation owner.
- Accepted shutdown watches controller loss during the existing bounded cleanup waits
  and invokes the same one-shot interruption under unchanged deadlines. An event-gated
  regression requires interruption while the first wait is still held; disabling the
  observer makes it fail. Pending-fault escalation remains covered.
- Timeout/caller cancellation attaches an observer to the shielded SDK future without
  releasing in-flight native ownership. Late results/failures are consumed and logged;
  subsequent calls remain busy until native completion.
- Snapshot and ordinary camera-save errors select the blocking camera row and field.
  Tests use the actual backend validation error, preserve the Behavior draft and whole
  proposal validation, and accept corrected Tracking settings. Native UI acceptance
  remains separate.

Sol found no compatible remaining readback duplication: Setup and manual paths already
share `resolved_configuration()` while owning different admission/adoption transactions.
Close that conditional task without another abstraction. Remove only the write-only
`completed_camera_operation` mirror; retain authoritative bounded status evidence and
accepted operator compatibility settings. Duplicate-command ingress and warning-race
claims remain rejected by the audit. Owned-camera edits now use exact readback and
commit-before-confirm semantics under [A10 revision 57](../docs/architecture/acquisition.md#a10)
and [A11 revision 41](../docs/architecture/acquisition.md#a11). Confirmation transport
admission is separate from execution/adoption; post-commit device failure does not
roll back accepted settings. Exact pending MCU proposals require the live edit,
claim, generation and original deadline; scope on other request kinds rejects.

Recovery retains exact late worker terminal evidence without adopting settings or
resuming previews. Fresh callers query retained results and can retry only an already
pending exact MCU CLOSE after camera cleanup. Stable previews remain editable;
unknown SDK/preview/resource/claim ownership remains fenced. Explicit exact-run Stop
works across controller/backend revision lag. Confirmed OFF/claim-release proof
survives live-observation clearing and expires before new connection/output work.
Cleanup failure keeps actual ownership and truthful closed-camera status; expired
Ready/Started records never create readiness. [Sol source and real-chain evidence](review-evidence-2026-10-09/nongui-sol-owned-camera.txt)
and [Luna recovery scope](review-evidence-2026-10-09/nongui-luna-camera-recovery.txt)
record the corrections and limits. Proven never-dispatched or explicitly rejected edits create no missing-status obligation; unknown admission retains its fence. Removal targets only that attempt; existing bounded-history pruning is unchanged. Sol and Astra accept the final integrated implementation.

Repository hygiene: remove the 10,353-file, 224,923,430-byte tracked `.tmp` tree and
ignore that root. Preserve three unique historical QA/collection artifacts in their
own dated bundles; existing JUnit copies match exactly. Git history, the environment,
actual runtime recovery/history and dated rig evidence remain intact. The
[cleanup inventory](review-evidence-2026-10-09/cleanup.json) records preservation hashes
and removal of 75 project cache directories (932 files / 52,844,967 bytes) after
validation in the preceding cohort. Final non-GUI cleanup removes another 42 cache
directories (321 files / 28,233,854 bytes); nine redundant handoff snapshots (181,320
bytes) were consolidated only after exact prefix checks. No active credential leak
was established.

ARCH-002 review extracts pure launch-request and cleanup-proof validation, leaving
registry native/state ownership and acquisition worker lifecycle orchestration in their
existing modules. The Oct9 non-GUI follow-up extracts worker preparation/waits/health,
shared native launch sequencing, manual-device recovery and exact retained-status
querying. Preview transfer release stays with its focused owner. Existing records keep
state/resource ownership; helpers receive explicit operations and focused records.
No process, dependency, whole-runtime reference or duplicate resource catalogue is
introduced. Remaining manual edit/preview orchestration (559/656 lines), recording
session closure (599 lines) and stimulus recording (833 lines) retain their cohesive
workflow/thread ownership; the size advisories do not justify duplicating that state.

Portable worker coverage/execution extraction and shared launch are accepted by
Sol/Astra. The deadline sweep closes the original 148-site inventory (135 first-batch,
10 controller and three launcher sites); the final controller increment also converts
one expression introduced during concurrent owned-edit work. Exact clocks, original
bounds and existing transport validation remain unchanged. The final scan finds zero
remaining inventoried patterns. Padding uses first usable image per nominal slot,
labelled first-image leading backfill and explicit omission/duplicate mappings;
[acquisition](acquisition.md) and [stimulus](visual_stimulus.md) own the details.
GUI source/tests are unchanged throughout this cohort.

Current non-GUI validation: repository-wide lint/format pass (849 files), Windows-target
mypy passes 734 sources, and boundaries inspect 639 modules with zero violations.
Contract discovery passes 48 Tracking and 42 stimulus cases; canonical schemas match
19/11 and all 57 generated bindings match. Final portable/offscreen authenticated-loopback
validation: **1795 passed, 6 skipped, 8 deselected in 309.49s (0:05:09)**. Sol and Astra
accept the final integrated source. [Current provenance](review-evidence-2026-10-09/nongui-context.json)
records the dirty baseline, exact changes, commands and model handoffs. One dirty
worker-test before-state could not be recovered: retain its declared hash and separately
label its HEAD-to-final supplement; every final tested input is hashed.

The preceding initial-repair portable/offscreen suite passes **1,698 tests, six skips and eight marker
exclusions** in 322.25 s before the final retirement-order correction. After that
correction, the complete supervisor/acquisition rerun passes **472 tests, five skips
and two exclusions** in 4.02 s; other source is unchanged. Final Ruff and formatting
(839 files), Win32-target mypy (726 sources) and boundaries (633 modules, zero
violations; 41 cohesion advisories) pass. Tracking/Visual Stimulus contract discovery
passes 48/42 and generated schemas match 19/11. Do not sum overlapping selections.
[Implementation evidence and model dispositions](review-evidence-2026-10-09/implementation-context.json)
retain commands, source patch/hashes, failures and limitations. Current full-suite
alignment passes; the historical advanced-card issue is not reproduced.
Windows native camera reuse, process/job proof, fault-injected shutdown, SDK pairing,
DPI and scientific/full-load acceptance remain unverified by these local checks.

Recovery and native acceptance cases have one home in the
[rig worklist](rig-verification.md#runtime-recovery-and-regression-coverage).
Missing required participants fail explicitly; this report does not establish an
operational experiment or authorize firmware, GUI or tracking implementation.

### Controller/supervisor audit (2026-10-14)

Scope: whole `src/cephvr/supervisor` and `src/cephvr/controller` trees with their tests, read by six
module-group auditors; every candidate was then re-read and, where an observed defect, reproduced by
probe or a failing regression test before any edit (source `0d70295` plus concurrent GUI/SpikeGLX
work in the tree). Source and local-test evidence only; no Windows-native or rig run (E15).

Fixed, each with a test that fails without the change:

| Finding | Repair | Decisions |
| --- | --- | --- |
| Cancel or failure before the preliminary supervisor registration (low-space/collision Cancel, space-query or reservation failure) left cleanup blocked and the reservation held | `dispatch_backend_cleanup` returns confirmed when no registered context exists and authority is intact: backends receive Setup work only after that registration | E04, E05, E06 |
| Accepted commands admitted with no live attempt (display calibration, tracking diagnostic, SpikeGLX inventory) were never finalized, so after 1,024 every non-safety command was refused | Such a command's own scope is finalized when it completes | E08 |
| An action raising a message over 4 KiB hung the RPC and wedged its record | Rejection messages bounded to 2 KiB; the caller's future is always resolved | E08 |
| A failed or timed-out calibration Close kept an IDLE pending with no timer, so the exact Close could never be retried | The unconfirmed Close expires on its recovery bound; the blocked flag stays until evidence arrives | E06, V01 |
| A failed manual-camera release RPC never freed `camera_operation`, wedging cleanup retries | The slot is retired; a late exact report is still adopted | E06, E08, A10 |
| Eye-tracking camera kept dormant values and the PFS payload in SESSION_CONFIG | Eye role handled with the other cameras | E04 |
| `incident_scope` log events made startup recovery reject the session log | Added to the inspector and to the E04 catalog (revision 89) | E04, E06 |
| A late ConfirmLaunch with a fresh command ID revived a RELEASED launch to CLEANUP_REQUIRED, after which registry refresh failed and health began shutdown | Release is final once the exact identities match | E08 |
| A firmware-rejected DIAG_START left the diagnostic "uncertain" and Release unable to confirm | Only an unanswered start stays uncertain | A11 |
| Pre-dispatch deadline failures were recorded as `SERIAL_FAILURE` | Labelled by exception type | A11 |
| `setup_override` events were never written | Appended after `session_started` | E04 |
| Stale protocol-3 text in the microcontroller contract | Corrected to 4 | A11 |
| An isolated required-backend exit was later overridden by heartbeat silence and entered full shutdown (owner chose to exempt it, 2026-10-15) | Backends in `isolated_backend_exits` skip silence checks; E08 revision 171 | E06, E08 |
| A failed manual Connect left an owner that could never reconnect (owner chose discard) | `LazySerialOwner` discards the failed owner and port; A11 revision 45 | A11 |
| An unanswered DIAG_START wedged Release (owner chose firmware-bound cleanup) | Cleanup attempts Stop, then the verified OFF decides; a failed Stop of a known-active diagnostic still fences | A11 |
| The host keepalive task ended if its failure handler raised, so later connections had no watchdog feed | Keepalive survives the handler error and skips only the failed connection; the failed close now warns | A11, E06 |

Also removed as dead write-only state: `Attempt.cleanup_commands`, two tracking-diagnostic fields and three unused
serial-owner members. Rejected: hard-coded 5 s delivery cap (matches E04's fixed 5 s), stop-after-trial gap wait (a
configured minimum, no decision requires early exit), and findings that did not survive tracing.

Oct16 local repairs complete E04/E03 accepted Stop/withdrawal/Abort events, automatic-stop and
terminal-unanswered dispositions, and short error messages. Required event tasks are registered
before writer seal and joined under the original finalization budget; safety dispatch remains
independent. SESSION_CONFIG records only supervisor/active-backend accepted software versions
(unknown is null). Every reserved trial output is indexed with exact owner/path, writer
format/schema, presence/closure and owner-observed counts; missing counts remain unknown.
Snapshot publishes oldest retained error/recovery/incident time and bounded-retention omissions,
including source and combined-list trims. Untimed warnings do not invent a history timestamp.
Existing owners/helpers are reused under ARCH-002; no new processes, inventories or timing policy.
Local backend/authenticated suites1785 pass/five platform skips/five exclusions; Ruff/format224,
Win32 mypy540 and boundaries699/zero violations pass. Initial fixture/import errors were corrected;
the sandbox-only socket failures remain in raw evidence, followed by authorized loopback passes.
[Evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json). Native E15 acceptance stays open.

Oct16 `controller-cleanup-and-race-hardening` completed locally under E04/E03/E06/E08:

| Audit concern | Current disposition/evidence |
| --- | --- |
| Late backend Cleanup hid failed central metadata | Reproduced; separate attempt-owned metadata-clean result gates late completion. Resource closure alone cannot certify persistence. |
| Timed-out Setup reservation thread outlived discarded attempt | Reproduced; exact acquisition task is shielded/retained, cancellation keeps the attempt blocked, and late settlement serializes cleanup. Original wait deadlines stay unchanged. |
| Missing recording root counted as cleaned | Reproduced; absent session/experiment is accepted only with its recording root present and safe. |
| SpikeGLX log failure changed a confirmed remote Stop to Unknown | Reproduced; remote STOPPED remains, metadata failure warns/blocks clean finalization independently. |
| Tracking begin held lifecycle lock during policy I/O | Reproduced; load outside lock, then recheck lease/revision/phase/device ownership before admission. |
| Display/camera admission gaps across validation | Reproduced; recheck pending display/calibration ownership and current camera selection/lifecycle before dispatch. |
| Configuration commit rejected any status publication | Reproduced; guard exact configuration revision/phase/authority and pending edit, without treating unrelated publications as conflicts. |
| Retry identity depended on current scope | Reproduced; retained canonical command uses its original scope after NewSession/retirement; changed payload still rejects. |
| Sessionless warning projections / supervisor error and recovery history grew without bound | Not reproduced in source review: ProjectionStore and supervisor enforce entry/byte bounds and E06 failure. Existing scope reset clears warning projections; no speculative history/eviction policy added. |
| RegisterContext could fail after admission on ordinary validation | Not reproduced in source review: final catalogue verification precedes admission under the same lock, with no await before sealing. No transaction rewrite justified. |
| GUI relaunch advanced its command before native creation | Fixed in extracted focused launch owner; creation failure retains old command, notification failure retains the actually launched child for cleanup. |
| Supervisor preview receipt stored no evidence | Reproduced in source; bounded exact failure/release evidence now retained and exposed by existing recovery query. No producer closure or viewer start is inferred. |

Owning tests pin the fixes; local backend/authenticated1804 pass/five platform skips/five
exclusions, Ruff/format170, Win32 mypy132 and boundaries701/zero violations pass.
GuiRelaunch and preview-evidence retention are separable owners extracted under ARCH-002;
no whole-runtime back-reference, new process or timing allowance. Existing cohesive-size
advisories remain. Initial patch/fixture/type errors were corrected and retained with the
[raw evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
Native ownership/process/serial/SDK behavior remains E15 rig work.

Oct16 `mcu-owner-residual-hardening` completed locally under A11/E12. Acquisition
Schedule rejection cancels unsent ON but retains OFF; confirmed immediate safety OFF
now retires only fully covered OFF reservations when no pending ON remains. Partial,
rejected and unknown OFF stay fenced. Startup probe propagates hard transport failures
instead of repeatedly writing a broken link inside its deadline. Firmware ERR retains
parsed context/request identity and symbolic codes. Full MCU observations expose
connection-cumulative malformed/unmatched diagnostics without health credit. SpikeGLX
monitor preserves actual observation failure reasons; only actual deadline violations
become DEADLINE, and missing unexplained observation is explicit unknown evidence.
Owner/protocol/monitor158 checks and backend/authenticated1813 pass/five platform skips/
five exclusions; Win32 mypy293, boundaries701/zero violations and scoped lint/format
pass. No firmware/electrical/mapping changes or rig acceptance.
[Evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).

Oct16 `controller-supervisor-residual-simplification` completed under ARCH-002.
Pending display/calibration commands are named immutable records; one dispatch helper
preserves transport-entry ordering, shielded calls and original deadlines. Shared
acquisition-entry lookup preserves duplicates/order/dormant or malformed payloads for
owning validation. Pacing resolution and incident byte accounting share focused helpers;
ByteSize avoids temporary serialization for capacity checks. Explicit release and watch
loss share one observer registry, removing duplicate registrations. All central warning
entry points now enforce one retention bound and omission flag. Removed unused Deadline
wrapper; existing absolute-deadline helpers remain. The camera role map and runtime
safety-kind set were already centralized; source review found no unused supervisor/
lifecycle flags to delete. Exact terminal late-evidence flags remain intentional records.

New owning coverage exercises real cleanup-fence registration/echo rejection, late
metadata cleanup, inclusive T−100/T−50 ms cutoffs, active-I/O writer entry/byte capacity
and late sync, the Tracking begin rejection matrix, exact ExecuteRecoveryAction replay/
cleanup proof and the production credential authentication factory. Existing tests pin
refactored behavior. Backend/authenticated1852 pass/five platform skips/five exclusions;
Ruff/format222, Win32 mypy111 and boundaries702/zero violations pass. State remains a
cohesive collection of focused records; display calibration retains exact diagnostic/
control-loss ownership after removing duplicated dispatch, with no new runtime back-reference.
Corrected initial extraction syntax, redundant cast, old test introspection and missing
paired-Setup fixture fields. [Raw checks and limits](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
Native E15 checks remain open. Inactive acquisition defaults and live calibration
rejection were repaired/tested Oct16 above.

### GUI preview design review

Source review on 2026-10-01 of the sibling CephVR1.0 checkout at HEAD
`38f728291ed551a332392dc2c7b6897e8428b060` found plausible preview costs, not
a measured cause of the owner's historical slowdown. Inspected preview files
had no local changes; the historical running revision is unknown. The old
`protocol/src/protocol/gui/stream_workers.py` emits a Qt signal per snapshot;
GUI-side draw throttling does not coalesce those notifications. In
`gui/experiment_window.py`, `_render_gl_frame` ignores `resolution_percent`,
expands monochrome frames to RGBA, and passes full dimensions to the GL widget.
The widget reuses textures and retains only the latest pending frame, so this is
not evidence of an entirely unbounded image renderer. Tracking metadata matching
and separate overlay consumers add possible latency/work. The existing external
`protocol/highgui_preview.py` also copies frames, fits them to a canvas and pumps
HighGUI events; external windows are not free of display work.

CephVR2.0 acquisition already applies its producer-side session sampling in
`src/cephvr/acquisition/worker/capture.py`; [A03](../docs/architecture/acquisition.md#a03),
[A10](../docs/architecture/acquisition.md#a10) and
[T08](../docs/architecture/tracking.md#t08) require preview work to remain outside
critical capture/tracking ownership. No new viewer performance was measured.
The owner accepted backend-managed external viewers and a modeless visibility selector
under [G01 revision 41](../docs/architecture/gui.md#g01). Runtime integration still needs
bounded latest-frame delivery, independent viewer/capture lifetimes and an OpenCV
dependency review: the current tracking extra is headless. Preview-off versus enabled
full-workload comparison remains part of [rig acceptance](rig-verification.md).
Window placement alone does not establish isolation or throughput.

The earlier three HTML sketches remain historical alternatives. The selected frontend
uses one Previews button and a reusable selector, with reported visibility, pending/
failure status and unavailable reasons. Footer actions and redundant labels are removed. Review fixtures explicitly emulate
visibility without creating windows or device commands. Native runtime admission,
completion correlation and external-window feedback are still integration work.

Additional CephVR1.0 source review at the same unchanged HEAD found useful candidates
in `protocol/src/protocol/gui/experiment_window.py`: geometry retention across trials
(`dashboard_preview_window_geometry`, line 22847), console scroll preservation
(`_set_console_text_preserve_scroll`, line 27834), a native output folder picker
(`select_output_directory`, line 28655), compact paths with full-path tooltips
(`_CameraConfigPathLineEdit`, line 4199), and field-specific help (`add_field`,
around line 4316). Viewer geometry restoration for backend-owned image windows remains integration work. Source review establishes
these mechanisms, not their rig behavior. Folder selection, compact paths, scroll retention and selector geometry memory are
now accepted and implemented in the frontend. Contextual help remains a suggestion;
external backend viewer geometry integration remains pending. Shared round indicators, bounded logs and modeless tool
windows already reuse useful reference patterns with smaller focused components.

### Dashboard frontend implementation

Tracking frontend review, 2026-10-06 ([G01](../docs/architecture/gui.md#g01)
revision 118, [G02](../docs/architecture/gui.md#g02) revision 33): role-derived
Preprocessing/Calibration/Pose/Motion retains source-pixel crop-before-downscale,
editable point tables and independent image-plane distance calibration. Subject
reference now places Set points and Clear at the left, without a point-count label;
Clear preserves manual pose and distance calibration. Numeric rectangle bounds
remain editable; Draw region actions are removed. Preprocessing has only Enable
crop and downscale; output-size and uncalibrated-scale captions are removed.
Valid calibrated scale is still displayed. Manual pose now uses natural method-form
sizing and measured table rows, with Set landmarks aligned left.

Enable switches now cover pose, sampling region, optical
flow, flow quality and locomotion. They dim dependent controls without losing values,
close annotation editing when toggled and persist in a separate diagnostic map.
Draft v4 migrates v1/v2 enabled and v3 by removing the obsolete preprocessing
diagnostic flag, preserving crop/downscale and other switches. Invalid flags fail
before mutation. These flags never enter experiment configuration: T02 still requires every
stage of the selected experiment pipeline. Live diagnostic execution and timing,
managed submission, acquired-image transforms and overlays remain pending. Optional
crop/downscale and chosen pose/analysis methods retain their semantics. Image-plane
scale does not establish physical swimming velocity or change T35/T38 output units.

One shared DataTable now applies Cameras styling to camera/projector inventories,
Tracking points, MCU I/O, SpikeGLX channels, screen calibration and dimensions.
Persistent editor sizing includes Qt's item insets; visual inspection caught and
corrected double padding and unpolished row sizing. Shared row-height checks now
assert full editor containment. Coral remains on page/navigation accents; blue
headers and existing editing/authority behavior are retained. ARCH-002 uses focused
stage and table helpers without new dependencies or runtime back-references.

Validation: current Tracking/review-draft checks pass 13 tests (221 deselected,
9.63s), including v1/v2/v3 migration, retained settings and Manual form containment
at 1280/720px. The new uncalibrated-label assertion initially ran after calibration
had already updated it; its ordering was corrected. Ruff lint/format (seven files),
Windows-target mypy (five source files), boundaries (563 modules, zero violations)
and whitespace pass; existing unrelated size advisories remain. Inspected
Preprocessing, Calibration and Pose at both widths plus native Manual pose. The
updated review GUI remains open (PID 36708); temporary helpers/captures removed.
Native UI automation inventory timed out, so validation used the app's own capture.
Previous shared-table GUI evidence: full suite 233 passed/one skip before final
sizing, then 39 affected passes. Previous backend evidence remains 36 local Tracking
plus six authenticated loopback passes, one Windows test excluded. No backend
processing changed; these local checks do not establish Windows/hardware acceptance.



The 2026-10-06 [live connection checks](device-connection-evidence-2026-10-06/README.md)
confirm controller-backed COM8 Connect and both assigned Basler connection tests,
including camera closure and successful original-draft restoration. Earlier
timeouts were isolated to acquisition worker PlanLaunch credential/empty-work
errors, now repaired in the existing launch/transport owners. Stale generated
bindings were regenerated from authoritative schemas; the unarmed watchdog fix
is recorded in [acquisition status](acquisition.md).

G01 revision 108/E07 revision 58 allow flags-only camera participation edits
without capture-ready settings. A real controller accepted both Use flags with
missing trigger sources, stayed alive for 25 seconds, and restored the draft.
Setup and settings edits keep full validation. Absolute native-picker directories
address the relative file:. warning. Native job inspection retries errors within
its existing three-pass bound; persistent unknown membership retains guards and
containment deadlines during shutdown. Original WinError 5's underlying OS cause
is not established; it recurred during the later authenticated shutdown for
acquisition PID 18904. The launcher released its guard without the posted traceback.
After the owner reported duplicate startup, native window inventory showed no GUI
but a live controller. The retained test generation was shut down through the
existing authenticated command; port 50051 is absent and the application guard
can be acquired. No replacement runtime is left running. Failure
diagnostics now retain role/PID/native cause and acquisition shutdown reason.
Portable controller/supervisor/platform/launcher: 356 passed, 2 skipped;
supervisor rerun: 106 passed; GUI selection: 4 passed; two real Windows containment
checks passed. Scoped lint/format, Windows-target mypy and boundaries pass.
ARCH-002 review retains cohesive native jobs/shutdown owners and introduces no
dependency or policy. Capture, preview, electrical pulses and full rig acceptance
remain in the existing checklist; no history save or pulse output occurred.

The later Behavior-camera PFS error was reproduced and repaired in the focused
GenApi helper: absent optional effective-exposure nodes and float Gain without
an increment are valid device capabilities. Controller camera completion now
retains the original failure text. Preserved the operator's current draft before
an authenticated idle-runtime restart, restored it, and verified PFS import,
readback adoption and Finish editing through the controller. The camera reports
closed/no cleanup pending at adopted revision 3; control was released and the
managed GUI remains running. Acquisition/controller checks: 406 passed, 2 skipped.
The preceding discovery-only inventory messages were not proof of camera opening.
The later command rejection was a lease-loss cleanup barrier: untouched Tracking
was absent from acquisition status, despite a fresh coordinator owning no camera.
Both roles now start with explicit closed/no-preview/no-cleanup facts; access still
requires exact subsequent evidence. Controller cleanup remains strict. The final
live PFS import/Finish editing, both camera tests, release/reclaim and both camera
retests pass; both cleanup operations succeed. Worker small edits retain normal
result reservations, avoiding unnecessary exhaustion of full-readback budgets;
readback operations and all ceilings remain unchanged. Acquisition/controller:
408 passed, 2 skipped; scoped static checks pass. A preceding attempt exited on
SUPERVISOR_HEARTBEAT_FAILED, retained as an unresolved native startup finding.

The 2026-10-06 runtime synchronization check confirms the managed launcher imports
`cephvr.gui.main`, whose ManagedDashboardWindow inherits the same DashboardWindow
and screen components used by review. Current Protocol/Devices layouts therefore
already apply to runtime; no duplicate frontend or build step was needed. A local
probe instantiated the actual ManagedGui/ManagedDashboardWindow with discovery and
transport substituted, installed authoritative-shaped protobuf snapshots, and checked
camera/rate and MCU/pin field completion reaches the existing bridge requests.
Snapshot installation emits no update requests; control loss disables editing.
Removed buttons/Stream controls are absent or hidden in the managed window, and the
unwired calibration presenter remains disabled. This verifies client wiring, not
authenticated transport, Windows startup or physical device execution.

Current GUI checks: **202 passed, 11 deselected (118.39s)** for the GUI/launcher
selection command (the selector included all portable GUI tests and excluded the
launcher cases). Ruff lint/format (97 files), Windows-target GUI mypy (96 source
files), boundaries (551 modules, zero violations) and whitespace pass. Updated the
runtime guide's obsolete Save-button instructions and calibration preparation wording.
No new source change or architecture amendment was required; G01/G02 already govern
the shared frontend. The existing main/camera/Protocol cohesion advisories were not
extended. The temporary managed probe and QSettings were removed. Windows runtime
startup and pending Protocol/projector/SpikeGLX configuration and calibration-output
bindings remain in the existing worklist.

The 2026-10-06 SpikeGLX refinement under [G01 revision 106](../docs/architecture/gui.md#g01)
removes the Stream header/selector from Input channels, leaving Use, Signal, Index,
Channel and the custom-input remove action. Existing stream identities remain in
retained mapping metadata so review-draft load/save does not discard them. Source
refresh cannot reveal the hidden stream controls. No managed acquisition behavior
changed. Existing SpikeGLX, draft-restoration and device-reflow checks: **6 passed,
197 deselected (3.97s)**. Scoped Ruff lint/format, Windows-target mypy (1 source file),
boundaries (551 modules, zero violations) and whitespace pass. Native inspection
checked the compact mapping rows, including a custom input; inspection closed and
the isolated GUI reopened on SpikeGLX. Temporary inspection artifacts were removed.

The 2026-10-06 Devices refinement under [G01 revision 103](../docs/architecture/gui.md#g01)
removes Save camera settings and Save pins. Managed clients submit completed fields,
camera trigger/PFS selections, COM selections and fixed I/O enable changes through
their existing controller requests; loading snapshots and refreshing ports stay
silent. Unfinished/invalid camera hints remain drafts, and pin tests require the
controller-confirmed configuration. Managed enable/pin edits lock during diagnostics.
Isolated review still sends no hardware commands. Under G01 revision 104, the separate
Prepare calibration files button/signal are removed; Launch prepares the diagnostic
GLB/display profiles and requests output only on success. Managed calibration
presentation remains unfinished. The focused calibration run passes **5 checks**
(198 deselected, 3.80s), including automatic preparation, preparation-failure gating
and confirmed Launch/Close state. Scoped Ruff lint/format (3 files), Windows-target
mypy (2 source files), boundaries (551 modules, zero violations) and whitespace pass.
Native Projectors inspection checked the simplified Screen calibration card and closed
before reopening the isolated review GUI.

Local affected GUI checks: **19 passed, 184 deselected (12.78s)**, then **2 passed,
201 deselected (3.65s)** after extending scan/snapshot silence coverage. Scoped Ruff
lint/format (4 files), Windows-target mypy (3 source files), boundaries (551 modules,
zero violations) and whitespace pass. Native Cameras/Microcontroller inspection at
1280px and narrow Microcontroller inspection at 720px were closed after review.
ARCH-002 review retains the cohesive camera panel's widget/draft/intent owner
(602 lines); transport and device execution remain in separate existing modules.
No new dependency or backend policy. Native Windows and physical controller/device
acceptance remain in the rig checklist; local review is not evidence of that pass.

G01's family-specific editor now gives Images Fit (Contain/Cover/Stretch), Move
speed and Direction, with initial position and whole-image rotation in Advanced
settings. Fit has a Batch edit dropdown and is excluded from numeric variation.
New Images use Contain; omitted legacy values preserve Stretch under
[V04](../docs/architecture/visual_stimulus.md#v04). Video hides Retain state/Linked
to; 3D arena hides Retain state in generation and editing. Both preserve loaded
reset values during other edits; Looming hides Linked to.
Image motion uses the existing 2D state, with no texture phase conversion. Fades
and existing closed-loop availability remain in their owning forms.

The 2026-10-06 arena visibility refinement under G01 revision 113 reuses the
shared stimulus editor without changing runtime reset policy. Focused family,
arena-variation and full-selection checks: **8 passed, 217 deselected** (8.60s).
Scoped Ruff lint/format (two files), Windows-target mypy (one source), boundaries
(559 modules, zero violations) and whitespace pass. These are local Qt checks;
no native Windows or physical projection acceptance is claimed.

Local checks for this increment: GUI suite **195 passed, 1 deselected**;
the final family/legacy/Batch-fit subset **5 passed, 192 deselected** after adding
the last compatibility scenario. Rendering, compilation and contract checks:
**68 passed, 79 subtests passed**. Scoped Ruff lint/format (16 files), Windows-target
mypy (14 affected files; an earlier broader pass covered 124 source files), schema
generation/check (11 schemas; Program/PreparedTrial regenerated), boundaries
(550 modules, zero violations), and whitespace pass. Native Qt inspection checked
mixed Image/Texture/Video/Looming rows and advanced cards at wide and settled 720px
layouts; inspection windows were closed and captures removed. The comparison review
window subsequently exited normally; the standard isolated GUI was reopened for review.
The 504-line StimulusParameters remains the binding/atomic-commit owner; image
fields and fitting math are separate focused modules. The existing canonical model
and renderer composition remain cohesive. GPU shader compilation and physical
Windows projection are not established by these portable checks; the existing rig
worklist remains authoritative.

[G01 revision 111](../docs/architecture/gui.md#g01) gives a single Timeline
selection the shared full Batch generate form: duration, stimulus mode, batch
label and each projector/layer's stimulus parameters. Duplicate/Delete sit before
Preview in the timeline header; at narrow widths their row sits below the title
without clipping. Selection/authority guards and shortcut behavior are preserved. Target epochs retains
parameter-at-a-time batch controls with All epochs, Epoch label and Epoch index
filters. Parameter choices derive from the same generation-column definition,
plus Duration/Asset; Opacity is absent. Rotation is Texture-only, Image exposes
Fit/Speed/Direction, Looming exposes size/growth, Video exposes Start/At end, and
arena exposes longitudinal/lateral/angular gains. Video end behavior uses a
dropdown; arena patches reuse the existing gain/channel helper used by variation. Labels refresh from the current trial; a one-based index selects a source
epoch, including nested groups without expanding repeated occurrences. Invalid or
out-of-range indices or missing label matches stay quiet during editing; Apply
opens a warning and rejects mutation, including direct apply calls. Validation
actions remain enabled so operators can obtain the failure reason.
Changing filters with unapplied edits restores the accepted filter. Epochs,
Filter and any label/index choice share one row; Parameter and the duration or
per-projector values share the row below. Fixed matching durations retain their
clock value; mixed/variable durations show hh:mm:ss, without staging a patch.
Targeting and epoch identity fields share equal grid columns, matching control
heights and explicit 12px gutters. Timeline selection keeps its larger section gap.
Discard/Apply sit opposite the Batch generate/edit tabs at the card's top right
across selection modes; Apply has primary emphasis. The shared
pair dispatches to the full selected-source form or the target patch, without a
second pair in the form. The redundant All parameters inspector shortcut and
Projector header in parameter editing are removed. Shared FormNotice removes inline error/status labels: action failures open one
window-modal warning per form; passive checks remain quiet, and status events
reach the Dashboard activity log. Editing-authority loss dismisses owned warnings. Empty narrow projector rows omit unused asset/numeric placeholders.
Batch generate aligns field heights and uses consistent horizontal/vertical gaps. Multiple
Timeline selections retain
batch patches for mixed settings, with structural actions disabled. Returning to
Timeline selection restores the previous targets. Pending form edits block a scope
switch until applied or discarded. Apply preserves source epoch identity, isolates
shared projector layers and copies changed scenes without altering sibling epochs.

Keyboard-only undo/redo, Ctrl+D duplication and Backspace deletion remain guarded;
text editing and multiple-selection protection are covered. The timeline has no
internal scroller, fits the largest enabled-screen layer stack across the trial,
and caches sizing by immutable program/screen identity. Trials matches its height;
the Protocol configuration section remains scrollable.

Final fresh GUI suite: **216 passed, 1 deselected** (125.59s). Focused targeting,
notice lifecycle, selection, generation, media and variation checks: **21 passed,
196 deselected** (21.86s). Tests verify quiet invalid filters until Apply, rejected
mutation, warning-window content/reuse, dismissal on editing-authority loss, and
status delivery to the activity log. Scoped Ruff lint/format (18 files), GUI
Windows-target mypy (100 sources), boundaries (556 modules, zero violations), and
whitespace pass.
The 2026-10-06 spacing refinement under [G02 revision 25](../docs/architecture/gui.md#g02)
uses one 8 px token for the dependent sections below SpikeGLX control, photodiode
pulse, Tracking crop and Variation rules. Margins belong to dependent sections;
hidden variation content leaves no spacer. Table/recording checkboxes keep their
row alignment. Four rendered sections reviewed and inspection window closed.
Focused owning GUI checks: **8 passed, 225 deselected** (6.12s), including narrow
variation layout. Scoped Ruff lint/format (five files), Windows-target mypy (five
sources), boundaries (561 modules, zero violations) and whitespace pass. No new
dependency or runtime behavior; native Windows/rig acceptance remains pending.

Under [G02 revision 24](../docs/architecture/gui.md#g02), protocol forms share the
notification helper: passive validation stages diagnostics privately, explicit
failed actions warn, and transient status goes to the log. Generation's live
preview no longer disables Add merely for invalid draft values; Add validates and
warns without mutation. Under G01 revision 114, shared parameter commits and
layer/type/scope navigation stage diagnostics privately. Parameter errors surface
once through the owning Add epochs/Apply edit action, including the projector
and specific invalid value; rejected navigation retains the pending draft.
Preparing a variation stays quiet. File-picker/load failures still warn at their
explicit file action. No new dependency or runtime policy. Local GUI suite:
**226 passed, 1 deselected** (144.70s); final submission/target/navigation subset
**5 passed, 222 deselected** (8.37s) after quieting the remaining batch navigation
guards. Scoped Ruff lint/format (six files), Windows-target mypy (five sources),
boundaries (559 modules, zero violations) and whitespace pass. Tests preserve
invalid drafts, verify a single warning on submission and corrected resubmission.
No native inspection window or hardware process was spawned for this increment. Authored timeline/preview counts remain visible data.
Native review confirmed an unmatched label is quiet, Apply opens the themed warning,
and status reaches the log. Inspection window closed normally. The first review
handoff subsequently exited; the updated isolated Protocol GUI was reopened.
Temporary helpers, QSettings, captures and results were removed after assessment.
ARCH-002 extracts notification/dialog lifecycle and the focused log event into
notices, removing InlineMessage and repeated inline-label behavior across protocol
forms. Existing form/document/history and controller ownership remain unchanged;
no dependency or backend policy changes. StimulusParameters remains the cohesive
binding/atomic-commit owner, with notification behavior delegated. Concurrent
launcher/controller/Tracking work and rig evidence were preserved. These checks
do not establish managed runtime or physical rig acceptance.

2026-10-06 portable update review of `c0120e9`: inspected the managed/review launcher
split, controller bridge, camera viewer, MCU wiring, draft persistence and renderer
startup amendments under G01/A03/E08. Refreshed the ignored generated bindings from
the 19 authoritative Protobuf sources; stale local bindings caused the initial
missing-field test/type errors. No hand-written implementation was changed.
The initially failing SpikeGLX review-action expectation was reconciled with the
intentionally disabled sample-mode connection button during the following authorized
layout increment; managed connection-query wiring is unchanged.
The existing Windows 720px horizontal-overflow finding below remains open; the
corresponding portable test passes on this macOS checkout.

The eight affected acquisition/controller/shared/Visual Stimulus test modules
report **82 passed**. Authenticated client RPC tests report **6 passed** after a
permitted loopback rerun (the sandbox attempt had five socket-binding errors).
GUI Ruff lint/format (96 files), Windows-target mypy (93 source files), and backend
boundaries (547 modules, zero violations) pass. Cohesion warnings remain review
prompts, not acceptance failures. These checks do not establish Windows runtime,
physical camera/MCU/SpikeGLX behavior or full rig acceptance.

Native simulated review inspected Dashboard, Protocol and all four Devices subtabs
at the wide layout and Cameras at 720px. The inspection window was closed, temporary
captures removed, and the standard isolated review GUI reopened for layout work.
The current commit also tracks 81 `.local-*` test-output files, including generated
locks, fixture images and review drafts; they are housekeeping leftovers, separate
from the dated rig evidence that must be preserved.

The SpikeGLX managed Devices panel now sends a read-only authenticated controller
connection query. It reports the saved endpoint, SpikeGLX version, running/saving
state, run name and data directory via the official SDK. The local SDK readback and
focused GUI/RPC checks pass. A later managed launch displayed a connected
Dashboard after concurrent renderer startup fixes, but it exited before the
button could be clicked. The agent's UI tool could read but could not click the
window. A retry ended with `JOB_INSPECTION_FAILED`; the exact SpikeGLX button
response remains unverified.
The separate E12 session lifecycle port is still unavailable, so pairing is not
claimed ready. See [E12](../docs/architecture/synchronization.md#e12) and the
[rig worklist](rig-verification.md).

2026-10-05 Windows rig review, current `main` checkout: PyQt6 constructed the review
Dashboard at 1280×800 with real discovery. Both expected Basler serials appeared in
Cameras; `Test enabled` opened, identified and closed 40065509 (`acA4112-30uc`) and
40747103 (`a2A2464-77umPRO`) without capture or settings writes. Dashboard,
Protocol, Cameras, Microcontroller, Projectors, SpikeGLX and the Tracking placeholder
were visually inspected from transient Qt grabs; cards, controls and text fit at that
size, with lower editor content available through the page scrollers. The GUI
discovered two COM ports without opening either. The current Qt session reported
one 1920×1080 Dell operator display
and no secondary projectors, so physical output assignment cannot be checked from
this session. The reviewed PNGs were deleted after inspection.

The focused Windows `test_devices_draft_reflows_without_horizontal_clipping[720]`
fails: the Devices scroller has horizontal overflow (48px in the test, and a direct
probe found 28px Cameras / 164px Projectors). This is an observed narrow-layout
defect, tracked in TODO. The first broad GUI run also emitted Qt access violations
and temporary-directory errors; the offscreen rerun encountered many setup/errors
and could not finish because pytest was denied access to its generated basetemp.
Focused camera/controller and authenticated-client runs also encountered
temporary-directory permission failures; no backend suite pass is claimed.
These runs provide no passing GUI-suite claim. Scoped Ruff/format pass (87 files),
Windows-target mypy passes (86 GUI files), and the boundary checker reports 539
modules with zero violations and existing cohesion advisories. The real-camera
review console now identifies discovery accurately instead of claiming sample input.
Two focused camera-review behavior tests pass after that change.

Managed camera wiring under [G01](../docs/architecture/gui.md#g01),
[E03](../docs/architecture/gui.md#e03),
[A03/A10](../docs/architecture/acquisition.md#a03) and the
[preview contract](../contracts/acquisition/preview-control.md) now has a separate
`cephvr.gui.main` entry point, exact GUI credential, observer WatchState stream,
explicit control claim/release, current-revision camera Start/Stop/Attach RPCs,
attachment query and release reports. The GUI preview reader waits on the A03 event,
copies the newest slot, converts it off the Qt event thread and coalesces delivery to
one pending image. The managed window leaves unrelated configuration editors disabled
until their controller submissions are implemented. Existing saved acquisition settings
must enable the backend and assign a camera before Start capture is available; the
current default leaves acquisition disabled; COM8 and D10/D11 outputs are now
assigned, while camera trigger input and other camera settings remain incomplete.
The GUI still lacks a separate editing-only Connect operation,
camera/PFS config submission and broader backend controls. No actual camera frame or
full managed launch has been verified in this increment.

Managed normal window closure now requests the controller's existing E07
`SaveConfigurationHistory` RPC before exiting. An observer acquires control only
when the lease is free; another holder causes an explicit save failure. The UI
offers Retry or Close without saving on failure/disconnection. Controller restart
already loads `config/last_configuration.json`, preserves accepted disabled-backend
settings and fills missing defaults. A focused GUI close-flow test and authenticated
loopback save-to-disk test pass. This applies to the controller-accepted reusable
configuration; review-only local drafts are not controller settings. The full
managed close/restart sequence remains unverified on the rig. The renderer startup
heartbeat defect below is corrected, but the bounded startup probe did not exercise
a controller configuration save or explicit E08 application shutdown.

The `scripts/start_gui.py` design-review window now atomically saves its local
editable drafts to ignored `config/review_draft.json` on close and restores them
after camera/display inventory on its next launch. It retains subject, device,
recording, projector and canonical trial-program drafts without claiming backend
application. A damaged prior file is preserved and warned; close-time save errors
offer Retry or Close without saving. The focused managed/review GUI and
authenticated controller persistence run passed 10 cases, with one additional
malformed-draft read check; Ruff, Windows-target
mypy on five affected sources, backend boundaries (546 modules, zero violations)
and diff whitespace checks passed. The controller's E07 history remains the
only accepted reusable experiment configuration.

2026-10-05 local rig-review MCU correction under [G01](../docs/architecture/gui.md#g01)
and [A11](../docs/architecture/acquisition.md#a11): the COM Test connection and
per-pin Test/Stop controls now use an exclusive acquisition serial owner on a Qt
worker thread. Numeric GUI pins map to Uno D pins; camera rows use their retained
requested rate. Firmware bounds each diagnostic to two seconds, and the GUI shows
matched active/inactive edge counts or command failures. Close requests an explicit
stop before port release. Isolated sample fixtures retain command-free behavior.
The focused MCU/review GUI and acquisition serial subset passed 56 cases after
a fixture-state correction;
the initial sandbox pytest run could not access its Windows temp directory. A live
COM8 test through the new worker confirmed firmware `cephvr2_uno_1`, protocol 2,
stopped outputs, then D2 active with zero edges and inactive with 120 rising edges
after 2.2 seconds. This confirms the input diagnostic path and observed D2
transitions, not the projector as their source. D9/D10/D11 outputs and receiving
channels remain untested. The managed GUI still uses its controller-owned route.

The standard entry points are now separate under [G01](../docs/architecture/gui.md#g01)
revision 96: `scripts/start_gui.py` always opens fixture cameras, four simulated
projector displays and one simulated Arduino entry, without OS camera/display/COM
inventory. `scripts/start_runtime_gui.py` enters through the Windows application
launcher and its managed GUI. The managed Devices page inventories real Basler
cameras, secondary OS displays and COM ports at startup even before a control lease;
these display/port scans are read-only. Focused GUI tests passed 41 cases, including
fixture isolation and managed pre-control inventory. Script-command smoke checks
confirmed the selected modules and required launcher arguments without starting
the runtime. A later bounded managed launch is described below. Physical display/MCU
checks remain separate.

2026-10-05 VS Code runtime launch follow-up: added explicit review and managed
Run and Debug profiles using the repository `.venv`. A real managed launch initially
failed because the user-profile CephVR runtime directory had an inherited Windows
DACL; the exact directory was repaired with the repository owner-only helper and
verified. The first renderer heartbeat lacked an E08 lifecycle phase, and after
that was repaired the idle coordinator aggregate declared a cleanup catalogue
revision before session registration. The worker now provides an initial
configuration phase and a setting-up phase with its resource catalogue; the
coordinator forwards the phase and omits the idle revision. A bounded managed
launch kept every role and the real Dashboard window open beyond 25 seconds, with
repeated accepted renderer heartbeats. The VS Code profiles use the repository
`.venv` without debugger attachment to child processes, preserving startup
deadlines. An offscreen managed GUI construction check inventoried two cameras and
two COM ports. The speculative heartbeat timestamp adjustment and diagnostic
instrumentation were reverted. No Setup, preview capture, pin output or projector
presentation occurred. GUI closure intentionally leaves the application running
under E08; the diagnostic launcher remained active and was later found to hold the
single-instance mutex. Its exact process identity and ancestry were verified
before it was stopped; the mutex was then confirmed available. Explicit E08
application shutdown and same-generation GUI relaunch remain unverified or
unimplemented, respectively. Earlier intermittent native process-inspection access error
and later lifecycle phases remain unverified. [Dated startup evidence](gui-startup-evidence-2026-10-05/README.md)
contains raw traces and limits.

2026-10-05 managed control audit under [G01](../docs/architecture/gui.md#g01),
[E03](../docs/architecture/gui.md#e03), [E07](../docs/architecture/experiment.md#e07),
[A10](../docs/architecture/acquisition.md#a10) and
[A11](../docs/architecture/acquisition.md#a11): the Dashboard now exposes Take
control, including explicit takeover confirmation when another operator holds it.
The Cameras Use checkbox submits an E07 update by assigned serial and waits for the
authoritative snapshot; rejection restores the previous state and is logged.
Camera config now submits its PFS path, FrameStart line source, timing selection and
requested pulse rate through the same revision-checked route. Managed Microcontroller
configuration submission includes both camera outputs as well as Trial state and Projector flip;
camera Test/Stop uses the saved behavioral/tracking signal identity. A pure validation
probe against the current rig defaults found that enabling the behavior camera is
rejected until `device.settings.trigger_source` is set; with an explicit `Line1`
source the acquisition validator returned valid. This probe is schema validation,
not proof that Line1 is wired or present on the physical camera. No camera or MCU
command was sent in this increment.

A later read-only query of the owner's live controller generation at 17:10 JST
confirmed Configuration phase, a GUI-held lease, both Basler serials discoverable,
acquisition disabled, and the enabled behavioral camera lacking `trigger_source`.
The owner's observed `REJECTED: configuration validation failed` is consistent
with the acquisition validator's `TRIGGER_SOURCE_REQUIRED` issue. The controller
now includes the first field issue in edit rejection text, and the GUI explains
the missing FrameStart line before sending the enable request. Focused GUI
enable tests passed 3; controller configuration transactions passed 17 with
1 skip outside the sandbox after Windows temp access denied the sandboxed run.
Ruff, Windows-target mypy, backend boundaries and diff whitespace passed. These
changes require a new application generation; the owner's running GUI and
controller were left untouched. The archived 2026-09-29 behavior PFS records
FrameStart `TriggerMode Off` with `TriggerSource Line1`; its Line1 entry alone
does not establish a currently active external-trigger configuration or wiring.

At this historical audit checkpoint, Dashboard subject/recording forms, Protocol,
projectors, SpikeGLX mapping and Tracking still lacked complete managed routes. The
[current wiring assessment](#current-scope-and-review) supersedes that implementation
status; the rig evidence below retains its original scope. Existing managed
Start/Stop/Attach preview, MCU diagnostics and SpikeGLX connection tests require
separate rig execution; the audit did not prove them from a live click. Focused
managed camera/control/MCU Qt tests passed 10 cases; related controller configuration
transaction tests passed 26 with one skip. The broad GUI suite reached
two failures before a Qt access violation stopped collection; the first expects an
older SpikeGLX review log message, and the second compares Qt forward-slash paths
with Windows backslash paths. Neither assertion covers this increment. This is
not a suite pass. Ruff lint, Windows-target mypy on 93 GUI source
files, backend boundaries and diff whitespace checks are recorded in LOG. The
585-line camera panel and 564-line managed entry prompted ARCH-002 cohesion review:
the panel still owns one camera UI state, while the entry coordinates distinct
transport/views; further backend binding should be extracted before extending them.

2026-10-05 Windows in-memory native preview check: the first 2×2 A03 ring attach
failed because CPython's shared-memory attach requested more mapping rights than the
owner-only DACL granted. Giving the same owner all non-execute mapping rights fixed
that attach without widening principal access. The next run exposed that the rig's
pypylon marks inactive converter controls read-only and copies a memoryview source.
Setting only the active truncate-mode shift and accepting that private SDK copy made
the ring-to-8-bit-GUI-reader check pass, including reader closure. This is an actual
Windows ring/converter test, not a Basler capture, frame-rate or optical pass.
The older CephVR1.0 `FrameStreamWorker` emits one Qt signal per frame; the new reader
retains only one replaceable pending image to avoid a render backlog. Rig throughput
for that improvement has not been measured. The focused authenticated-client,
credential, native-mapping, manual-preview and GUI checks pass (11 selected); 30
controller-camera/ring checks pass separately. Ruff, Windows-target mypy and backend
boundaries pass with existing cohesion advisories. Owner-assigned trigger wiring or
an explicit temporary unaligned free-running test is needed before live capture.

2026-10-05 managed launcher check: an inherited user-profile runtime DACL rejected
GUI credential provisioning, so the launch was repeated with an isolated owner-only
runtime under the workspace; that temporary credential directory was removed after
the launcher exited. Startup then exposed stale bootstrap-handle closure in the
acquisition, Visual Stimulus, renderer and Tracking entries, and a missing Tracking
policy descriptor. Correcting those and confirming each backend's existing supervisor
launch record let startup reach the renderer. The renderer subsequently reported
`VISUAL_STIMULUS_WORKER_FAILURE: original Visual Stimulus peer deadline expired`;
the supervisor performed safety shutdown and an emergency report records the error.
Its cleanup also logged `VISUAL_STIMULUS_EVIDENCE: cleanup command unknown` and an
async admission conflict during shutdown. One further launch with method-specific
deadline text identified `ReportWorkerHeartbeat` as the expiring peer call; whether
it is delayed before submission or in the coordinator still needs isolation. The
5-second registration policy was not changed. No camera command or
Setup was issued. The real user-profile ACL was not altered. Emergency outputs from
these launches remain under `reports/emergency-*.json` as E04 runtime artifacts.
Two current managed GUI tests pass, including native latest-of-two-frame ring read;
authenticated client/shared credentials pass 12. Visual Stimulus and supervisor
behavioral tests pass 242 with the previously tracked
`presentation.pacing_refresh_hz` loader failure. Scoped Ruff, Windows-target mypy
(102 source files), boundary checks (542 modules, zero violations) and diff whitespace
pass. These tests do not close full launcher or physical camera acceptance.

2026-10-05 planner/layer/performance update at base commit
`3af4289814927c1c3fdc4251731ef894a49a1489` plus working tree follows
[G01 revision 93](../docs/architecture/gui.md#g01) and
[V07](../docs/architecture/visual_stimulus.md#v07). New GUI-created stimuli use
reset false for every family; imported explicit resets/assignments remain intact.
A shared-style Advanced settings card sits below each projector row, aligned to
Layer. Retain state comes first, then Linked to and Fade in/Fade out, then controls.
The linking/fade row reflows at narrow widths. The opacity editor is removed;
new stimuli use their constant base opacity and optional V05 linear keyframe fades.
Standard fades use exact seconds and reject negative/nonfinite/sub-nanosecond or
combined lengths exceeding the fixed epoch. Explicit duration edits retain their
lengths and move fade-out to the new end. Imported custom opacity curves remain
unchanged, with simple fade fields disabled rather than flattening saved functions.

+ Control sits below the Advanced settings/entries and opens a separate draft dialog
without changing row height. Its action hides while configuring and restores on commit
or cancellation; entries appear only after Add control. It appears only for Texture/Looming under Closed-loop, with
canonical Tracking longitudinal, lateral and angular inputs. The current V24
catalogue has no body-to-2D conversion, so committing those mappings is disabled
pending the owner's coordinate choice. Imported mappings and existing arena axis
controls remain intact. Open-loop closes the draft; Cancel/invalid drafts preserve
state. Add layer creates an empty local slot; choosing its family creates the
canonical instance, then prepared-file/motion/fade settings persist independently
across layer and projector switches. Empty slots are not serialized as stimuli.
Variation rules use a Card with body Enable and separate Projectors/Layer selectors,
including All projectors and All layers. Local ordinals resolve independently per
projector; canonical identities reject stale layers and shared targets are deduplicated.
Remove controls share the Projectors/Layer/Parameter row and height. Combine is removed from Batch generate;
equal-length rules pair by value position in entered order, without random assignment.
Method and all value controls occupy the second row; Random shows Minimum, Maximum and Precision there. Precision is a positive step (1, 0.1, 0.01, etc.).
A focused Decimal-grid sampler draws uniformly with replacement from grid multiples
inside bounds, without allocating the full grid; numeric/input-size guards and the
existing 2000 expanded-epoch bound apply to Random batches. Batch Repetitions
supplies the count: 100 creates 100 random epochs, without a second repetition
multiplier. Mixed Values/Sweep lists retain their ordered repeated sequence, with
one draw per resulting epoch; nonrandom-only batches retain existing repeat groups
and the 512-variant bound. Per-row caches include the resulting count and stay stable through preview
and insertion; changed range/precision/count resamples. Final concrete epochs
survive JSON round-trips, leaving Setup/V08 randomization unchanged. Multiple rules
still pair by position with matching counts, and one all-projector/layer rule shares
its drawn list across selected targets. Categorical video end behavior stays Values-only.
ARCH-002 reuses canonical materialization and shared row sizing, with no dependencies.
The shared stimulus-column catalogue supplies matching captions/units, including
Rotation, with Width/Height/Opacity removed. Looming size/growth and Video start/end
values materialize directly into independent canonical epochs; categorical video
end modes are preserved. Existing imported conditions and the
separate group authoring dialog retain their semantics. ARCH-002 extracted the focused
Batch variation row rather than extending the reference composer.
ARCH-002 uses focused local layer-slot and bounded timeline-view owners, without
threads or new dependencies. Unchanged metadata no longer validates the whole
program; selection reuses expanded paths/content keys (four immutable views maximum).
The timeline remains painted rather than allocating widgets or decoding each asset.
A real 200-epoch, four-projector, two-layer program exceeded the GUI's previous 1 MiB
read guard. GUI read/save validation now shares the backend's existing 16 MiB
engineering default; managed Setup limits stay authoritative. Configuration/policy
values and runtime capacity guarantees have not changed.

Heavy local offscreen benchmark: 200 epochs, eight layers per epoch, 3,202,179-byte
pretty JSON; parsing 463.26 ms, initial UI binding 333.45 ms, warm switching between
two distinct trials median 12.63 ms. These are development-machine observations,
not rig acceptance or rendering/asset-decoding throughput. A first-source fade test
confirms independently generated later epochs are unchanged; a repeated source still
applies to all its occurrences, so a first-occurrence-only fade needs a separate intro.

Explicit input/output ranges remain pending the owner's clamp-versus-extrapolation
answer. V24 currently applies gain/offset without input clipping; this update does
not silently turn authoring ranges into runtime bounds. The editor currently shows
gain/offset, not range controls.

Linked to is visible as a disabled selector in the card; movement linking is not
implemented yet. The owner confirmed clockwise Bottom drives
Right front→back and Left back→front when both sides are linked. [V02 revision 12](../docs/architecture/visual_stimulus.md#v02)
records that accepted convention and the distance-based lever arms. Pure analytic
examples with unequal distances verify opposite side directions and different
linear speeds; runtime behavior has not been exercised. The remaining pending
question is whether links follow total source motion while replacing target motion
or follow programmed motion with additive target feedback. These affect experiment
behavior and cannot be silently selected under GOV-001. CephVR1.0 reference
`optic_flow_motion.py:415–510` preserves target appearance and maps subject-frame
motion by face, but its yaw lever arm uses half the source dimensions. The new link
must use accepted rig geometry/subject distances rather than copy that approximation.
V24 does not currently declare inter-stimulus motion sources; resolve semantics
before changing program schemas/preparation/rendering. Old planner fade-in and video
loop overrides were reviewed as separate candidates; no extra overrides were added.

Trial timeline Preview opens a separate read-only snapshot window for enabled
screens on one rotatable tank view, with Play/Pause, seeking, epoch navigation and speed.
CephVR1.0 reference `protocol/gui/trial_preview_dialog.py:_TankView` paints
stimuli onto calibrated planes and culls outward-facing content. The new view reuses
TankDiagram placement/rotation, paints enabled faces from both sides without
back-face culling, using cached reduced-resolution
compositions and keeps inactive planes as outlines. Screen labels remain above the
completed scene. Default/reset azimuth is now 25° instead of 155°: Left appears
left of Right, while fixed rig planes, mappings and calibration stay attached to
the same identities. Shared TankDiagram screen painting sorts ascending view depth
so nearer screens cover farther ones consistently; the previous reverse order could
leave a face label on another face’s visible content. Native inspection confirms
separate Left/Right textures on their planes. The planning-description banner, enabled-projector text and subject
marker are removed; the observer remains in projection geometry. Rotation reuses frames; playback/seek/media changes invalidate them.
It reuses canonical
expansion and V07 state helpers, with example seed 0 and fixed-duration validation.
Images use a bounded cache; only active videos own Qt decoders. Paused windows stop
the playback timer; close/edit-authority loss cleans up resources. Current geometry
projects supported image/texture layers; unset tank/plane geometry shows a Devices
configuration prompt. No fallback tank dimensions are invented. Arena rendering is approximate, capped at 4000 triangles
and two cached scenes; unsupported/missing content reports errors per screen.
Screen scale, pixel offsets and inversions now use the shared calibration export
mapping after complete per-face composition. Pixel offsets use the assigned display
resolution, not the <=512px planning frame. Invalid/out-of-range corrections or
unresolved nonzero pixel offsets display an error; blank fields reuse export's
identity defaults. Geometry and corrections are frozen at opening, independent of
output enablement. Reopen after changing calibration. Arbitrary imported runtime
warp meshes, masks/weights and photometric corrections are not applied by this
planning view; ideal projector optics remain schematic. No live Tracking or physical
output is applied. Actual video
codec playback has not been exercised locally; Qt multimedia availability alone
is not decoding evidence. Procedural textures are not rendered in this planner.

ARCH-002 review keeps preview expansion/state, geometry snapshots, asset ownership,
canvas drawing and bounded arena rendering in focused modules. ProtocolEditor's
628-line cohesion advisory remains: its six added lines only flush/emit the request;
window/resource ownership is separate. No whole-runtime references or dependencies
were introduced. Prior 200-epoch measurements above remain historical observations;
this increment did not rerun that benchmark.

Commit cleanup (2026-10-05): removed 173 temporary native/visual/benchmark scripts,
duplicate JUnit exports and routine check outputs from the dated GUI evidence folder.
Recorded outcomes, source hashes and unique performance/native evidence remain;
removed links are labelled as removed artifacts. Functional test assets stay local.
All 170 owning GUI tests remain; the obsolete single-rule compatibility wrapper was
removed and its sweep test now exercises canonical ValueRule generation. Shared row
sizing runs once. Native narrow inspection exposed a linking/fade container that
kept its wide-row height after reflow; reserving the new minimum height keeps controls
visible while preserving Layer alignment. The owning alignment test now checks fade
control containment. Focused docstrings explain blank-layer preservation, immutable
cache identity and retained-state seeking. Batch IDs reuse one edit-local identifier
set instead of rescanning the growing document; 1000 allocations match uncached
numbering, including reserved-ID collisions. No dependencies or experiment policy changed.

Final validation: **183 GUI/client-state/compiler checks pass in 69.28s**
(`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui
tests/client/test_state_views.py tests/visual_stimulus/test_compilation.py -q
-m "not windows and not rig"`). Four focused random/batch checks pass in 3.63s; 23 advanced/control/fade/reference
checks pass in 14.94s, and the extended narrow containment test passes in 2.10s.
Ruff checks the GUI/tests/launcher and two affected Visual Stimulus sources;
format check passes 90 files and Windows-target mypy passes 88 sources.
Backend boundaries check 539 modules with zero violations; unchanged 505-line
Cameras/628-line ProtocolEditor cohesion advisories remain, with new responsibilities
kept in focused modules. The earlier broader configuration run had **187 passes and
one existing failure**, `test_default_and_file_policy_values_are_typed`: the loader
rejects checked-in `presentation.pacing_refresh_hz`. Its assertions remain unchanged;
managed pacing adoption is indexed separately in TODO. Local passes do not establish
Windows, optical calibration, video-codec or full rig acceptance.

Native wide/narrow controls inspected after cleanup; inspection exited successfully.
173 temporary repository review artifacts and 75 local review scripts/settings/flags/
captures are removed; GUI reopened for owner review.
The launch guide now distinguishes real-device discovery from optional simulated
fixtures and describes the current Protocol/Projectors layouts. Rig-specific
frontend checks live in [the rig checklist](rig-verification.md).

Prior behavior validation: **170 GUI checks pass in 91.46s**. Four focused random/paired/sweep
checks also pass in 19.40s. New coverage includes finite bounds, negative ranges,
precision grid membership, repetition-driven 100/10/999-epoch generation, ordered
mixed fixed/random rules, invalid/empty grids, cached
preview/commit values, resampling after settings change, saved JSON values and wide/narrow layout.
Existing preview/calibration tests remain in the full GUI pass. Tests compare the shared
export mapping and actual scaled/offset/inverted pixels, assigned-resolution
normalization, missing-resolution errors and invalid bounds. Prior combined
client/compiler results are historical; not rerun for this GUI-only increment.
Coverage includes menu ordering/moves, matching and ordered variation values, arena
gain variants, retained preview motion/backward seeking, image cache, window cleanup,
bounded arena drawing and rejection of unresolved timing. Windows-target mypy
passes 86 GUI files. Ruff/format and boundaries are recorded with current source
hashes in [random-variation evidence](gui-dashboard-2026-10-01/random-variation-2026-10-05.txt).
Native wide/narrow editor and four-screen planning preview were inspected; inspection
closed cleanly and temporary screenshots deleted. Reopened review uses prepared test
assets and simulated projector discovery. The existing pacing-key loader failure,
managed viewers/calibration adoption, pending scientific choices above and rig
acceptance remain open. Earlier dated evidence retains prior scope/counts.

Live camera Preview remains pending under [A10](../docs/architecture/acquisition.md#a10)
and [G01](../docs/architecture/gui.md#g01). The review GUI's Connect flag and
Preview visibility signal do not open a capture stream or image window. The
acquisition backend has manual preview commands, but this frontend has no managed
controller connection or registered viewer. An independent GUI SDK reader would
change A10's camera ownership; the owner choice for the rig test is pending.

2026-10-04 rig device review: [G01 revision 66](../docs/architecture/gui.md#g01)
changes normal `scripts/start_gui.py` and `cephvr.gui.review --review` startup to
discover attached Basler cameras, secondary Qt/Windows displays and COM ports.
Camera refresh retains drafts by serial; Test enabled uses the A10 adapter for a
bounded open/identity/close check. COM labels include the available description
while selection retains the system port path. Explicit `--simulated-devices` keeps
isolated frontend fixtures available. This remains a local review GUI; Connect,
preview, projector output, controller commands and Setup are not managed device
operations. Direct rig inventory on 2026-10-04 found behavioral serial 40065509
(acA4112-30uc), tracking serial 40747103 (a2A2464-77umPRO), COM8 Arduino Uno
and COM9 USB-Serial Controller. Both cameras opened, returned identity and closed
through `BaslerCameraAdapter`. Qt reported only the primary DELL S2721HS display;
no secondary projector output was available for an output test. This is device
discovery/control-open evidence, not acquisition, projection or lifecycle acceptance.
The rig GUI construction smoke check showed those two physical camera rows, zero
projector rows and named COM8/COM9 entries. Focused GUI checks passed (3); Ruff,
format, Windows-target mypy, boundaries and `git diff --check` passed.

Later on 2026-10-04, four secondary Qt projector screens appeared. The owner's
Windows Settings screenshot showed that DisplayConfig path positions **5, 2, 3, 4**
in Qt order did not match Settings IDs; the primary `DISPLAY9` was path 1 but
Settings label 5. QueryDisplayConfig returns path priority order, not a documented
Settings number. Under [G01 revision 70](../docs/architecture/gui.md#g01), the
GUI now assigns its own consecutive numbers to secondary screens sorted by desktop
position. The table, scaled layout, timing labels and projector labels use the same
CephVR numbers. The operator compares layout positions with Windows Settings to
associate each number; no manual ID entry or Windows-number inference remains.
Assignments and Use state stay keyed by display identity through refresh, so local
renumbering does not silently transfer a projector face. Four focused GUI checks
pass for local labels, primary exclusion, sorted ordering and retained assignment.
An additional projector-focused run passed seven tests; three unrelated file-fixture
cases could not set up because the host denied pytest's temp directory. Ruff,
format, Windows-target mypy (67 GUI source files), boundaries (520 modules, zero
violations) and whitespace pass. A native read-only GUI construction on the rig
resolved four secondary screens in spatial order: CephVR 1 at (-3840, 0), 2 at
(-2560, 0), 3 at (-2280, 720), and 4 at (-1280, 0). Actual physical surface
correspondence and projector output remain rig checks. The prior broad GUI attempt
also encountered a native Qt access violation; it is not a passing suite.

2026-10-04 projector plot: [G01 revision 65](../docs/architecture/gui.md#g01)
and [V15 revision 10](../docs/architecture/visual_stimulus.md#v15) retain shared
front-attached screen geometry, independent calibration and view-only rotation.
The Bottom diagram now draws four schematic pyramid edges from the mirror center
to the footprint, with one incoming line from the projector beneath Right. The
physical 45° reflection/clearance helper remains unchanged: incomplete outer-ray
coverage retains the valid center and dashed ideal footprint with a hover warning;
impossible central paths still omit Bottom optics. This schematic does not establish
physical mirror coverage or calibrated ray paths. Backend rendering and JSON fields
are unchanged.

Five compact buttons toggle Tank, Screens, Projection, Subject and Labels; Labels
fills the remaining second-row width. The wrapping legend remains visible, following
visible elements. Projection still groups projectors, rays, footprints and mirror;
violet footprints remain distinct. ARCH-002 review simplified the existing painter
and removed the separate legend state/button without new dependencies or modules.
Existing coordinator/backend cohesion advisories remain unchanged.

Validation: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui
 tests/client/test_state_views.py tests/visual_stimulus/test_compilation.py
 contracts/visual_stimulus/tests -q -m "not windows and not rig"` passes **193 tests
and 79 subtests in 63.76s**, including 138 GUI tests. Existing optical-path,
incomplete-coverage and phase-safe view tests remain; the visibility test now
requires exactly five controls. Ruff check/format (68 files), Windows-target mypy
(67 GUI files), boundaries (520 modules, zero violations), changed local link
targets and whitespace pass. Existing cohesion advisories were reviewed: this change
reduces the focused painter and does not extend the 622-line Protocol coordinator.
Native normal/600 mm/narrow views were inspected using explicit local samples;
rotation, disabled Right and grouped visibility were also exercised by the harness. The Bottom pyramid and five controls
fit both widths. Inspection exited 0 and closed its window. Method:
`.venv/bin/python reports/gui-dashboard-2026-10-01/tank-pyramid-native-review.py --capture`
uses Qt grabs, temporary QSettings and four simulated 1920×1080 displays; no device
commands or rig measurements. Base source `5c24d99aacf41f75fd07249faa1bfb52cf1dea78`
plus working tree; harness (temporary artifact removed)
and [source hashes](gui-dashboard-2026-10-01/tank-pyramid-source-sha256.txt) remain.
At the owner's request, all 383 generated GUI review images (including this inspection)
and three temporary synthetic assets were deleted on 2026-10-04. Their historical
assessments remain, with removed-image links converted to text. No screenshot is
retained. Managed adoption, the existing pacing-loader follow-up and Windows/optical
rig acceptance remain pending. The GUI reopened on Devices / Projectors / Rig geometry at Bottom distance 600 mm
and reported Visible: True; it remains open for owner review.

The native Protocol planner follows [G01 revision 61](../docs/architecture/gui.md#g01)
and [V02/V03/V07/V08](../docs/architecture/visual_stimulus.md#v02). Source validity
remains separate from compilation/Ready. Asset folders and recording participation
remain in-memory drafts; Save as writes one canonical trial. Session scheduling,
persistence and managed configuration/Setup adoption remain unfinished.

Recordings omits the metadata/scientific-data explanatory sentence (G01); offscreen
construction confirms the text is absent. Recording choices and backend evidence policies
retain their existing ownership. Scoped lint/format/type checks pass.

Protocol type/Load/Save as sits beside Assets. Recordings now sits on Dashboard below
Session config, in two columns with adjacent checkbox/label pairs. Camera and Visual Stimulus video switches are independent of
required lifecycle metadata and acquisition/rendering. Tracking follows closed-loop
or Tracking velocities, with no Protocol tracking-status indicator; saved video choices
survive camera disablement. Device control remains in Devices. The review fixture
explicitly starts velocity saving Off without changing T14's saved/file default On.

The planner places a 208-pixel Trials list beside the fixed-height Trial timeline, with
full-width Sequence editor inside the open group. Add/Delete sit at the foot of
the trial list. The current subgroup workflow and validation are described above
under G01 revision157. Existing reference composition supports prepared assets,
projector-local layers, exact duration, family parameters and bounded variation.
Source blocks keep horizontal navigation and visible-range painting; group repetition
counts do not allocate repeated occurrences. Explicit previews remain bounded.
Structural actions duplicate, remove and move selected subgroup sources; Undo/Redo
retains bounded per-trial history. Imported nested/condition source programs remain
preserved. Shared epoch boundaries, physical geometry and runtime ownership are
unchanged; no new serialized hierarchy or dependency is introduced.

CephVR1.0 source at `38f728291ed551a332392dc2c7b6897e8428b060`,
`protocol/src/protocol/gui/trial_planner_window_v3.py` (1490–1540, 1645–1718,
3266–3578, 4288–4530), informed direct actions, reference-plus-variation creation and
explicit-target/value batch editing. Its `.texture.json` import resolves an existing
exported PNG and declared tile dimensions; plain image pixels do not imply physical
scale. Old random-generation modes were not adopted. Source review is UI reference,
not performance or rig evidence.

Earlier official UI research (documentation review, not hands-on benchmarking) used
[PsychoPy Flow](https://devdocs.psychopy.org/builder/flow.html),
[Labvanced frames](https://www.labvanced.com/content/learn/en/guide/task-editor/frames),
[Gorilla Task Builder 2](https://support.gorilla.sc/support/tools/task-builder-2/how-to),
[OpenSesame loops](https://osdoc.cogsci.nl/4.0/manual/structure/loop/),
[BonVision series](https://bonvision.github.io/pages/04-Series-of-stimuli/) and
[sequences](https://bonvision.github.io/pages/05-Adding-sequence/). The owner subsequently
refined the native workflow into a visualization-only timeline and batch-first editor.

Previous 2026-10-03 verification (before the fixed-height/list change), working tree based on
`5c24d99aacf41f75fd07249faa1bfb52cf1dea78` plus uncommitted work:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui tests/client/test_state_views.py tests/visual_stimulus/test_compilation.py -q -m "not windows and not rig"`
passes **121 checks in 48.17s**. Coverage includes batch combinations/repetitions,
count previews, exact nanosecond durations, JSON reload, media/dimension replacement,
projector/layer isolation, atomic invalid/missing-target rejection, mixed/pending fields,
range/toggle selection across groups and nested-insertion undo. Existing cancellation,
custom-function fidelity, nested condition editing, saved-file preservation, responsive
layout, runtime edit gates and Close checks remain covered. Ruff/format and
Windows-target mypy (55 GUI files) pass. Boundary checks report 508 modules and zero
violations. ARCH-002 review separated batch mutations, composition, generation and
patch forms; extracted popup ownership and shared texture-dimension replacement.
The 627-line ProtocolEditor remains the cohesive document/history/selection coordinator
with explicit component signals, not a backend/runtime reference. Remaining size
advisories concern existing non-GUI modules; no dependencies were introduced.

2026-10-04 validation: the same GUI/client-state/compiler command passes **122 checks
in 46.83s**. Ruff/format (56 files), Windows-target mypy (55 GUI files), boundary
checks (508 modules, zero violations; existing size advisories) and whitespace pass.
Focused coverage checks review inventory/refresh/participation, list selection/draft
preservation, centered summary and stable card bounds with internal scrolling.

2026-10-04 epoch-controls review under [G01](../docs/architecture/gui.md#g01)
and [V03 revision 9](../docs/architecture/visual_stimulus.md#v03): the earlier captured
layout placed Stimulus mode on its own row and included Order; G01 revision 68 now
places mode with clock duration, repetitions, label and insertion. Reserved
heading space keeps row pitch equal with or without repeated headings. Arena mode
omits the type column and exposes independent Longitudinal/Lateral/Angular toggles
and gains using [V24 revision 7](../docs/architecture/visual_stimulus.md#v24). A zero
gain disables an axis; imported custom mappings and programmed motion remain intact. Tracking declarations are added only when needed; conflicts reject the edit. The type dropdown
changes the selected layer independently, clears its asset and blocks generation
until a compatible file is selected. A visible Layer dropdown selects the current
projector layer and its asset/parameters. The menu retains layer management.
Advanced controls are one indented, vertically separated section under the selected
projector/layer: Opacity, Retain state, and Feedback. Input declarations are inline
in Feedback; binding IDs are internal and operation follows the signal kind.
Mappings expose compatible Input signal/Parameter choices and coefficients; generic
sources require explicit metadata, not assumed runtime discovery. Loaded coefficient
functions remain read-only and preserved. Arena basic/advanced edits synchronize
without overwriting one another; invalid coefficients reject atomically. Retain state
inverts reset while preserving explicit assignments. Loaded placement and dimensions
remain unchanged. Inactive
projector content is retained. Per-projector and rig-wide arena drafts survive mode
switches; only the selected mode's referenced definitions are generated. Source files
show basenames while preserving full logical paths for loading/copy/hover. Shared
combo helpers draw a consistent chevron. Looming is the displayed family name.

Optional labels persist on every generated source epoch and remain available for
Batch edit targeting after JSON reload, including nested groups. Insertion supports append/start/before/after/replace/
every-N-blocks and After label. Label choices come from the current trial. A fresh
batch is inserted after each original matching source epoch inside its existing
group scope; new matching labels are not targeted recursively. Instance/asset/group
identities are remapped, newly generated content is bounded to 2000 occurrences and failures
leave the trial unchanged. Interval insertion consumes
one generated block per interval, appends remaining blocks, and counts top-level
repeat groups as blocks; it never flattens their scheduling semantics. New source
paths are selected after the atomic commit, and undo restores the previous trial.
The final button explicitly says Replace trial in replacement mode.

ARCH-002 review keeps reference transformations and batch insertion in focused pure
helpers; no dependencies were added. ProtocolEditor remains at 622 lines and remains
the cohesive document/history/selection coordinator. Focused feedback-entry, signal-declaration and mapping-owner modules replace the tabbed schema editor and reuse canonical units and Tracking declarations. ArenaMovement owns only its basic axis controls; the mapping owner patches explicit changes, with no duplicate program state or new dependencies. The 714-line canonical source model remains the cohesive schema authority.
Other size advisories are existing backend modules. Previous captures are historical.

Native per-projector controls (review image removed),
label insertion (review image removed),
selected layer (review image removed),
opacity (review image removed),
arena mode (review image removed) and
narrow layout (review image removed) were inspected
using the capture script (temporary artifact removed)
with `--capture`, temporary QSettings and generated PNG/placeholder GLB references.
Command: `.venv/bin/python reports/gui-dashboard-2026-10-01/protocol-layer-label-native-review.py --capture`.
These are authoring fixtures; no GLB decoding, rendering or device connections occur.
Source is base `5c24d99aacf41f75fd07249faa1bfb52cf1dea78` plus current uncommitted edits.
CephVR1.0 reference: original planner arena movement-axis/gain controls,
V3 BlockEditorDialog batch-label/insertion controls,
PlannerBatchEditDialog label targets, and `_insert_rows_every_n` in the original
planner; previously recorded reference revision `38f728291ed551a332392dc2c7b6897e8428b060`.

Current advanced-settings evidence (2026-10-04, G01 revision 64):
wide (review image removed) and
narrow (review image removed) native layouts were
inspected using the review script (temporary artifact removed)
with `--capture`; both inspections closed normally. The script uses temporary
assets/settings, four review projectors and an explicitly declared sample brightness
signal. No device connections or live feedback transport are exercised. Base revision
is `5c24d99aacf41f75fd07249faa1bfb52cf1dea78` plus uncommitted work, identified by
[source hashes](gui-dashboard-2026-10-01/protocol-feedback-source-sha256.txt).
Final `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui
tests/client/test_state_views.py tests/visual_stimulus/test_compilation.py -q
-m "not windows and not rig"` passes **151 tests in 60.32s** (138 GUI tests).
Final review GUI reports Visible: True on Protocol with Front advanced settings open.
Five focused checks cover mode width, retained explicit assignments, inline input
creation, automatic operations/IDs, invalid coefficient rollback, removal/JSON
round-trip and bidirectional arena control synchronization. Existing per-projector
isolation and custom-mapping tests remain in the owning GUI suite.
Ruff/format (68 files), Windows-target mypy (67 GUI files), boundaries (520 modules,
zero violations with existing cohesion advisories), local links and whitespace pass.
Managed signal discovery/adoption and Windows/rig validation remain pending.

Previous Protocol verification on 2026-10-04: `QT_QPA_PLATFORM=offscreen .venv/bin/python
-m pytest tests/gui tests/client/test_state_views.py tests/visual_stimulus/test_compilation.py
-q -m "not windows and not rig"` passes **146 tests in 58.25s** (133 GUI tests).
Four focused checks passed before the full run. After the native narrow capture
exposed horizontal clipping, the batch header gained a three-column fallback;
three affected checks pass, including a zero-horizontal-overflow assertion. Normal
widths retain the requested single parameter row. Native normal/narrow, selected-layer,
label-insertion and opacity views were recaptured and inspected. The capture process
closed normally. [Source hashes](gui-dashboard-2026-10-01/protocol-layer-label-source-sha256.txt)
identify the reviewed controls; no hardware/backend commands ran. Ruff/format (65 files),
Windows-target mypy (64 GUI files; also the six edited modules separately), boundaries
(517 modules, zero violations), local evidence targets and whitespace pass. A transient
full-GUI mypy run saw three errors during concurrent tank-diagram edits; a later run
passed without this task changing that file. Initial obsolete Width-editor tests were
updated to retain invalid-value, animation and reset coverage through Opacity.

Earlier arena-gain validation on 2026-10-04: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
 tests/gui tests/visual_stimulus/test_feedback.py tests/visual_stimulus/test_compilation.py
 contracts/visual_stimulus/tests -q -m "not windows and not rig"` passes **194 tests
and 79 subtests in 38.83s**. Two subsequently added focused tests pass for imported
custom/legacy mappings, channel conflicts and the pure independent-gain reference.
Fourteen initial focused checks also pass. Ruff/format (67 files), Windows-target
mypy (65 source files), 11 generated schema comparisons, boundaries (515 modules,
zero violations) and whitespace pass. The remaining cohesion advisories are existing
backend modules and the reviewed coordinator/canonical model. No dependencies added.
Coverage includes independent/disabled/reversed gains, legacy shared-gain fallback,
unit checking, save/reload, equal row pitch, control ordering and tab spacing.
The inspection window exited; the final local review is reopened for owner review.

Broader configuration testing reproduces the pre-existing `presentation.pacing_refresh_hz`
loader rejection in `test_default_and_file_policy_values_are_typed`: the earlier
GUI-selected config value exists, but managed loader adoption is still the existing
`gui-implementation` TODO follow-up. Neither the TOML nor loader changed in this
increment. Managed integration and Windows/rig acceptance remain pending.

2026-10-04 overview/inspector validation: the combined GUI/client-state/compiler
command above passes **123 checks in 47.24s**. Eight focused timeline/layer/batch
checks also pass. Coverage verifies same-setting colors across renamed/differently
sized epochs, changed-setting separation, current projector details, range selection,
unchanged source documents, fixed card height and retained pending-edit guards.
Ruff/format (58 files), Windows-target mypy (57 GUI files), boundaries (510 modules,
zero violations; the existing coordinator and backend size advisories) and whitespace
pass. Local native review does not establish managed or Windows/rig acceptance.

2026-10-04 overview/inspector increment under G01 revision 53: replaced repeated
per-projector full-trial lanes with one selectable overview plus focused projector
rows, and labeled the existing generation/patch modes Batch create / Batch edit.
ARCH-002 review keeps color keys and descriptions in a focused read-only helper,
reusing canonical layer order and parameter readers. No new grammar, dependencies
or backend behavior. Pending batch changes still reject retargeting and restore the
accepted detail selection; expanded occurrences keep their condition-specific display.
Native overview and details (review image removed),
narrow layout (review image removed) and
Batch create (review image removed) were inspected
using the review script (temporary artifact removed)
with `--capture`, isolated temporary QSettings and the existing built-in sample.
Base revision remains `5c24d99aacf41f75fd07249faa1bfb52cf1dea78` plus uncommitted work.
Inspection exited; the reviewed Protocol layout is reopened for owner review.

2026-10-04 Recordings relocation under G01 revision 52: extracted the existing
recording controls into a focused RecordingsCard owned by the shell and placed below
Dashboard Session config. Protocol reads that single draft for Tracking activation;
camera enablement, retained choices and phase/control locks are unchanged. Two-column
checkbox/label pairs fit the narrower Dashboard column. The obsolete Protocol card
placement/reflow was removed. No backend changes or dependencies were introduced.
Validation: the GUI run passed 109 checks with one obsolete expected-card-list failure;
after updating that assertion, all five affected checks pass in a focused rerun.
Ruff/format (57 files), Windows-target mypy (56 GUI files), boundaries (509 modules,
zero violations; same reviewed size advisories) and whitespace pass.
Native Dashboard (review image removed),
narrow Dashboard (review image removed) and
Protocol (review image removed) captures were
inspected with the review script (temporary artifact removed),
using `--capture`, repository Python and temporary QSettings on the same source base
plus current edits. Inspection exited and Dashboard was reopened for review. Managed
integration and Windows/rig acceptance remain pending.

2026-10-04 layout increment: the review launcher supplies four simulated 1920 × 1080
displays (2–5), assigned Front/Left/Right/Bottom. Devices table, display diagram,
participation and planner lanes share these records; Refresh preserves draft choices.
Native discovery remains the default when no review inventory is supplied. Sample
labels appear in the title/tooltips/log; there are no hardware commands or saved
assignment changes. ARCH-002 review reuses QListWidget, existing selection styling
and a scroll area; a small immutable display record shares rendering between actual
inventory and fixtures. No dependencies or backend semantics changed.

Native Protocol (review image removed),
narrow Protocol (review image removed) and
Devices (review image removed) captures were inspected
using the capture/reopen script (temporary artifact removed)
with `--capture`, repository Python and isolated temporary QSettings. The script
uses the built-in three-epoch/60-second sample and exits after inspection; omit the
flag to leave Protocol open. Source is the same base revision plus current uncommitted
work. Four lanes fit the normal viewport; fixed-height scrolling and trial navigation
are checked locally. The narrow capture also reveals existing recording-label clipping
at 720-pixel window width; the subsequent move to Dashboard with two columns resolves
this observed clipping, verified at 720 and 1175 pixels.

Native batch edit (review image removed),
reference composition (review image removed),
creation options (review image removed) and
narrow layout (review image removed) were captured and
inspected with the review script (temporary artifact removed).
Fixtures use temporary prepared assets and explicitly labeled sample Left/Right
assignments, without saving device configuration or sending hardware commands.
Inspection exited and the final sample GUI reopened (Visible: True). Earlier
group editor (review image removed) and
expanded sequence (review image removed)
captures are historical evidence for retained features. Native macOS review does not
establish Windows, full workload or managed acceptance; those remain in the
[rig worklist](rig-verification.md).

The convenience launcher `scripts/start_gui.py` selects the repository `.venv`,
starts the existing review entry from the repository root and forwards its exit code.
It defaults to labeled review mode; `--read-only` opens the disconnected frontend.
It does not start managed backends or hardware. On 2026-10-02, help, Ruff/format,
Windows-target mypy and both command modes/exit forwarding were checked; a native
launch from `/private/tmp` succeeded.

The PyQt6 Dashboard follows [G01 revision 41](../docs/architecture/gui.md#g01) and
[G02 revision 23](../docs/architecture/gui.md#g02). Compact read-only round Runtime
status indicators form a horizontal row inside System controls in the owner-reviewed layout;
System controls and subject/session fields occupy the left column.
The accepted shared Card style places titles in a gap in the top-left border,
using existing palette/radius tokens. Shared headers add 14 pixels of vertical
separation; console Clear buttons and their action rows are removed. Session config
places Subject ID and Experiment above Output directory, then uses spacing alone
to separate species, sex, age, size and condition; there is no subsection heading.
A small Qt paint override preserves QLabel titles/accessibility and existing layout
ownership. The visible rectangular title mask reported by the owner is corrected:
the rounded fill stays continuous and only the outline is clipped beneath the
transparent caption. The owner approved the Dashboard presentation on 2026-10-02. Dashboard, Devices and narrow
native captures were inspected on 2026-10-03; 76 GUI/client checks and static checks
pass for the current frontend.
Runtime HUD fits its rendered text height; Activity log fills the remaining right
column. Shared FittedConsole measures Qt text blocks and recalculates on text/width
changes, while existing log/card stretch owns extra window height.
Setup spans the full row above equal-width Start/Stop buttons. Subject age is labeled
Age (dph), and experiment phase appears only in the HUD. The HUD also retains distinct
recording/metadata evidence. Camera experiment enablement belongs to Devices; other participation/use/save editing
now belongs to the local Protocol draft. Managed adoption remains pending. Prior banner/footer,
trial/progress removals remain in effect; preview selection now lives in a secondary window. Header connection/local-control
badges and their now-unused shared pill component/styles are removed; command gates
are preserved.

Setup requests preparation in Configuration and New session in Ended, returning to
Configuration after controller-owned cleanup before fresh Setup/Start. Stop requests
Cancel Setup during SettingUp/Ready. During a session it opens a window-modal chooser
with Stop now (E06 Abort now), Stop after trial and Cancel. Dismissal/Cancel sends no
intent; Cancel is the default. The chooser updates current phase/control availability,
closes when no stop action remains available and selection rechecks authority. It
opens asynchronously without blocking backend progress. The redundant Session menu
is removed. E05/E06's underlying commands and cleanup/finalization remain distinct.

ARCH-002 review reused the action/phase table and added a small focused dialog module
using shared component/theme helpers, with no new dependency or runtime back-reference.
The previous standalone status card and phase pill were removed under ARCH-002; the
combined readiness grouping is owner-reviewed. A focused PreviewDialog uses
shared styling and immutable visibility records, with no image processing or new
dependency. The selector is opened at the right of the compact page header. Shared layout helpers
position its native frame with a 12-pixel right-hand gap and equal top edges, clamping
to the main screen when necessary on first opening. Geometry is then retained across
reopen and frontend restarts via Qt save/restoreGeometry and local CephVR/Frontend
QSettings. Current rows determine width/height after restoration, replacing the
previous oversized remembered dimensions. The current selector follows CephVR1.0’s Source/Live table structure (reference
experiment_window.py around line 7948) as a lighter Source/Show grid: dark bordered
panel, aligned right-side checkboxes, blue column labels and shared focus/hover rules.
Accessible checkbox names retain each source label. Normal rows omit redundant state; pending
and unavailable reasons remain visible. Review labeling is in the title. No Hide all
or Close buttons, duplicate title or instruction/footer text remains. Invalid saved
data falls back to first-open snapping. This stores GUI
geometry only; no permanent docking or continuous movement coupling is added. Reference source is `position_aux_tool_window`
(line 6635) and `_move_tool_window_frame_to` (line 27984) in CephVR1.0. The selector
persists while hidden, scrolls a changing viewer inventory,
rechecks current availability/control and holds reported checkbox state while awaiting
an update. Local review visibility fixtures remain independent of session phase. Devices now has a presentation draft; Visual Stimulus and Tracking remain placeholders. `cephvr.gui.review --review` identifies local fixtures
in the window title; phase/observer inspection lives in View. Buttons/dialog selections
report intent without commands or fabricated execution; drafts are neither saved nor
submitted. Default presentation is disconnected/read-only. No `cephvr.gui.main` managed
entry was added; controller transport/leases, viewers, incidents/reconnect and managed
registration remain unfinished under E02/E03/E08.

The shared DirectoryField opens a nonblocking existing-folder picker, rechecks editing
availability on selection and preserves cancellation. PathEdit elides only painting
while unfocused: full draft text, copying and tooltip remain intact. LogConsole uses
word-wrapped bounded lines without forced token splitting, keeps the current retained entry during append/eviction and
follows only from the bottom. These helpers add no dependency or runtime ownership.

The preview header count is removed and its button toggles the selector. Sources are
Behavior cam, Tracking cam, additional configured camera roles, Tracking and Visual
stimulus. An explicit active flag gates both controls and request dispatch; inactive
names are dimmed and explain the restriction in a tooltip. Review camera enablement
updates these rows, and Protocol Tracking participation drives its preview gate; View fixtures remain available.
Tracking camera enablement remains independent of tracking-pipeline participation.

Devices orders Cameras, Microcontroller, Projectors, SpikeGLX. Cameras stacks its compact
inventory and Camera config at the left. Role, Internal clock / External controller trigger source, requested
Microcontroller pulse frequency and PFS path/Browse are the only camera configuration
controls. Detailed parameters are edited in PylonViewer; GUI parameter editing and
PFS export are removed for now. The shared asynchronous PathField serves both output
folders and PFS files. Cancellation preserves drafts, and switching cameras rejects
the open picker; late callbacks also check dialog identity and editing availability.
PFS selection now reads bounded FrameStart trigger hints without applying a preset. Missing, ambiguous or unsupported hints leave the dropdown unset. SDK import/readback integration under
A10 remains necessary before any future applied-settings claim.

Device subtabs fill the left column width and align with the HUD’s painted top border, with configuration cards
below. A single existing QTabBar moves between the retained panel layouts; the
shell no longer needs a device dropdown or resize handler. The title/Previews row
keeps one measured height. Tests verify that the right HUD stays aligned across
all seven surfaces, navigation survives resizing, and cards sit below the tabs.
Native wide/narrow captures confirm all four labels fit. ARCH-002 review removed
the rejected header trial's extra controls without adding dependencies or state.
Removed the selected-camera caption from Camera config and the draft footer.
Refresh is an accessible icon in a reserved table-header section. Shared header
corner radii and a transparent native header background fix protruding corner fills;
no similar defect was found in the inspected cards/fields/HUD/log views. Connect
switches to Disconnect and back for the selected review connection.
The proposed Test enabled action logs one explicitly untested request per enabled
camera, preserving selection and connection state; no hardware result is fabricated.
Tests cover disabled-camera exclusion, empty selection of enabled devices, phase
gates, real tab clicks, full-width tabs and their border alignment. Managed connection-only batch checks are now implemented through the controller and
camera worker; their physical rig acceptance remains pending.
The camera inventory is titled Available devices. A shared dim selection palette
separates selected rows from headers and applies to navigation/subtabs/text selection.
Shared 12-pixel horizontal cell/header padding is included in content-sized columns,
keeping Role text away from the table boundary.

Shared StatusColumn now supplies a fitted HUD and expanding log on Dashboard, every
device subtab and Visual Stimulus/Tracking placeholders, using the existing responsive
stacking rule. Camera HUD now uses the counts/selected-role/status/controller-trigger/
measured-acquisition layout described in the current appearance assessment above;
backend acquisition-rate readback remains outstanding.
Per-camera drafts, unique roles and active-source preview restrictions remain.
ARCH-002 review removed the obsolete parameter/Apply/export UI and reused existing
Qt layouts, fitted consoles and picker logic without dependencies or runtime references.

Connection/visibility remain labelled local review fixtures; Refresh/connect controls
send no SDK command. Actual Protocol participation, PFS application, controller-owned
configuration/validation, image windows, managed integration and Windows/rig acceptance
remain pending. The reference inventory/connect patterns come from CephVR1.0's
experiment_window.py lines 8065–8230 and 8440–8505; the initial broader parameter
form is superseded by the owner's PylonViewer workflow.
Microcontroller lists only discovered COM-number names through QtSerialPort; no
ports are opened, and this Mac correctly yields an empty COM list. One controller
selection owns camera triggers; Cameras has no port setting. Inputs now precedes
Outputs. Each signal has an enable checkbox/name/pin/Test row. Camera enablement
shares Cameras' participation state through stable-ID signals and immutable records;
disabled rows stay visible for re-enabling. Pins persist, disabled controls dim,
disabled signals do not cause pin conflicts, and disabling ends local tests. Fixed
I/O enablement is local draft configuration, not applied hardware state. No new
dependency or backend ownership was added under ARCH-002; no camera heading, frequency column
or level/edge selectors remain. Trial state is fixed active-high; Projector flip
is fixed rising-edge. Tests validate target identity, pin conflicts and gates and
use retained camera rates. Output tests are intended for SpikeGLX observation;
input testing observes edges. Test now toggles to a compact red Stop button with
unchanged geometry. Explicit local review state locks wiring/port edits, clears on
port or authority/phase loss, and cancels affected camera tests on draft changes.
Small Inputs/Outputs cards use shared compact density and a four-column row helper:
centered enable checkboxes, wrapped signal names, equal-width pin and action controls.
Name, pin and action columns now share width equally, widening pin/Test controls.
Both cards share column proportions and spacing; other cards keep their spacing.
The 2026-10-06 managed-camera binding adds controller-confirmed role assignment,
connection-only Test enabled, capture-versus-editing state, pending-command locks,
and external viewer attachment/close refresh. G01/A10 distinguish open/identify/close
from Start capture's frame/trigger evidence. Controller disconnect discards queued
operator intents. ARCH-002 moved camera projection/intents and request construction
out of the GUI entry point; MCU projection lives with its focused binding, and
serial-keyed discovery records moved out of the Cameras widget. The remaining
Cameras widget remains cohesive presentation/signal wiring; the Basler adapter's
small ownership property remains with its sole SDK owner. No new
dependency or direct GUI hardware ownership was added. Camera/pulse edits while
owned were blocked in this historical Oct6 scope; the current Oct9 owned-edit
implementation and review are described above. The final source trace found that accepted drafts previously never reached manual
acquisition commands and GUI PFS selection only changed provenance. Commands now
carry the accepted acquisition draft/revision, with ownership/staleness gates;
selected PFS files use actual SDK import/readback and explicit editing completion.
COM changes close the previous serial owner before connecting the new port. These
fixes are portable-test verified; native launcher/hardware acceptance remains in the
[rig guide](rig-verification.md#managed-device-gui).

Validation (2026-10-06): full portable GUI suite 206 passed/1 deselected;
subsequent focused managed/PFS/inventory checks 25 passed and MCU gates 5 passed.
Complete portable acquisition/controller suites: 390 passed/5 skipped; authenticated
controller RPC suite: 6 passed. Ruff lint/format (360 files), Windows-target mypy
(355 sources), regenerated Protobuf, boundary checks (555 modules, zero violations)
and whitespace pass. A temporary actual ManagedGui snapshot/layout probe passed
with discovery/transport replaced; both device pages were visually inspected, then
closed and temporary images removed. The native design-review window was reopened
on Cameras. No native managed launch, camera SDK frame, MCU waveform or rig pass is
claimed. Acquisition runtime remains composition/delegation; its new draft-adoption
logic lives in a focused owner instead of extending the runtime body.

The managed GUI now submits COM8 connection, saved Trial state/Projector flip
pins, and bounded Test/Stop requests through the controller to acquisition's
serial owner. Firmware protocol v2 implements the two diagnostics and their
device status is projected back to the panel. The owner-assigned D10/D11 camera
trigger pins and saved rates are projected to their matching camera rows. MCU
commands were extracted from the managed GUI entry into a focused binding under
ARCH-002. The 2026-10-06 increment adds pending/failure locks, confirmation-based
final-status queries and current camera-pin projection. GUI/portable owner checks
are recorded in LOG; the full managed Windows path and physical pins remain unverified.
The earlier Qt teardown failure is historical; the subsequent full offscreen GUI
suite passed. ARCH-002
review reuses one small row helper and removes the obsolete aggregate test path.
Projectors replaces its HUD with Displays layout, a tank/screen schematic and the
activity log. Screen calibration/Synchronization/Rig geometry sections beneath inventory
keep cards fitted to their content. Independent pulse visibility/placement and
config-file pacing retain separate targets; off-pulse fields dim and preserve values.
Tank dimensions, left/front/bottom subject offsets, clip/tolerance fields and
per-face screen dimensions/distances/throw/scale/pixel offsets/reversal
remain local drafts. Geometry conversion creates four inward-facing parallel screens at explicit
subject distances, with side/Bottom front edges starting at the Front screen plane.
The rotatable diagram updates on edits; its legend identifies the drawn elements
without in-plot labels. CephVR IDs remain in the display table and layout.
CephVR1.0's Launch calibration ran a world-phase multicolor calibration grid through
its VR runtime, with a Disconnect action. The owner selected V01's managed Visual
Stimulus renderer for CephVR2.0. The saved rig JSON now feeds an offline GLB exporter;
the resulting asset is under ignored `cephvr-data/calibration`. The owner rejected
the timed 60-second trial program; calibration is to remain visible until manually
closed through a distinct V01 diagnostic state.
Screen calibration Launch prepares files automatically: it reads the current four
enabled face assignments and native monitor identities, computes bounded diagnostic
projection limits from the rig dimensions and writes a V15 display profile plus four
diagnostic geometric profiles into Protocol Assets. This is a local export, with no
output command. The review GUI still has no managed projector command, so Launch/Close
and physical presentation remain open under `projector-calibration-launch`.
The Screen calibration card now has a Launch/Close control interface for all four
outputs. It stays disabled without a managed controller connection and changes its
label only after confirmed output state; the local review frontend cannot project.
The diagnostic profile exporter now applies each face's scale, pixel offset and
inverse-axis drafts to its geometric mesh, so software centering values are prepared
per projector. Adjustments require a new preparation and later managed presentation;
they are not live projector output in the review GUI.
CephVR1.0 reference inspected: experiment_window.py 8990–9068 and 10274–10309.
No old measured rig values are adopted. Optical calibration/config transport remain
pending; parallel-plane placement follows the GUI geometry draft, not rig measurements.

The shared left configuration scroll area contains overflow while the right column
stays fixed; whole-page scroll wrappers are removed. Calibration uses a per-face
inverse/scale/offset grid based on CephVR1.0 lines 11535–11591. Physical sizes and
projector distances/throw belong to Rig geometry; removed footer text stays absent.
Pulse-off disables all synchronization fields, retaining their independent values.
VSync mode replaces Presentation; pacing selection is absent from the GUI. The
Visual Stimulus TOML declares a 60 Hz target and installation-owned pacing identity;
managed adoption/validation remains pending, so this is not a runtime rate guarantee.
Shared scrollbar tracks have zero width/height, retaining scrolling without any
width changes across tabs. Wheel delivery is regression-tested.
Screen dimensions presents all four faces with width/height/projector distance
and throw ratio. Left/Front/Bottom subject-to-screen distances sit in Rig geometry below the
Subject → Left wall / Front wall / Bottom fields. The right-screen distance is
now derived using equal side-screen offsets: width + left-screen distance − 2 ×
subject-to-left-wall distance. Diagram and geometry conversion recompute together;
invalid inputs clear the derived plane. JSON v2 omits the dependent value. Compatible
v1 imports retain their independent values; conflicting explicit right distances
reject the complete import without mutations. Regression tests cover an off-center
subject, subject edits, stale-value clearing, JSON omission and legacy migration. The diagram footer is removed. Regression coverage
confirms calibration JSON excludes display/projector inventory and preserves
existing assignment/participation state on load. Row-name header is blank and
column headings wrap within their fields. One Load JSON / Save as row replaces the per-screen file picker. The complete
versioned calibration document covers rig, limits and all four screen dimensions,
distances and corrections; bounded validation precedes any field changes, invalid
loads preserve state, QSaveFile commits atomically, and authority loss cancels pickers.
Files preserve null draft fields without claiming backend readiness. The owning
[format contract](../contracts/gui-calibration.md) distinguishes these GUI snapshots
from mesh/display profiles. An application wheel filter prevents focused/unfocused
combo/spin/slider mutation while routing gestures to containing scroll areas.
The filter is removed at application shutdown. After one native inspection exited
with status 138 following confirmed window closure, a native launch/close check
passed with exit 0; focused/unfocused wheel regression checks also pass. The geometry builder and diagram use one corner
helper, separating physical screens from tank walls; invalid distances are not guessed.
SpikeGLX has retained local stream/index/channel mappings for cameras, fixed I/O,
conditionally visible photodiode and added named inputs. Camera streams are restricted
to OneBox. Mapping Use checkboxes retain disabled values; custom signals have remove
buttons, while device-derived signals retain their source identities. Local mapping
opt-out cannot waive E12's required camera/pulse validation at managed preparation. Remote saved-channel discovery, duplicate/type validation, configuration
adoption and physical pulse acceptance remain pending under E12; no applied mapping
or remote connection is claimed.

2026-10-03 validation: 74 GUI/client tests cover fixed right-column positions under
left scroll, phase gates, calibration retention and mapping source toggles. Ruff,
format and Windows-target mypy (26 GUI modules) pass; boundary checker finds zero
violations across 479 modules, with pre-existing non-GUI cohesion warnings unchanged.
Native captures in `gui-dashboard-2026-10-01/derived-right-*` use explicitly labelled
projector fixtures and actual primary-only inventory. A layout attribute collision
in the new mapping editor initially hung resize checks; native stack sampling located
it, and distinct layout names plus the full narrow/wide suite verify the correction.
ARCH-002 review keeps calibration and input mapping in focused modules and standard
Qt scroll containers, without new dependencies or backend ownership changes.

Projectors uses a compact index/assignment/resolution/Use table and scaled desktop
Displays layout diagram. Per-display Use retains assignments/geometry, persists
through refresh and dims disabled diagram rectangles. GUI drafts remain local;
managed config binding is unfinished. Shared equal-row-height helper matches
Microcontroller pin/Test and path/Browse controls. Both exclude the current primary screen;
remaining screens receive local CephVR IDs from 1 in desktop-position order.
Primary-only setups show a clear empty state. Local tests cover primary removal,
ordering, retained assignment and empty refresh; physical layout comparison remains
rig work. Size and verbose properties are removed. Projector choices are
Unassigned/Front/Left/Right/Bottom. Display is content-sized and the remaining two
columns share spare width evenly; native inspection confirms Unassigned fits.
Selection/drafts survive refresh by identity. ARCH-002 review removed physical-size
collection and obsolete editable-combo caret handling; no new helper or dependency.
The former Windows path-index helper and manual-ID dialog were removed under ARCH-002;
neither yielded a reliable automatic Windows Settings number. The
[QueryDisplayConfig API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-querydisplayconfig)
documents path priority order, which differed on this rig. Actual surface matching
remains a [rig check](rig-verification.md). No dependency was added.
Native inspection corrected projector-name clipping and selected-row bottom overlap.
Camera Preview shares Dashboard source/visibility state, without an actual image window.
Full validation, persistence/apply and backend checks remain under A10/A11/V15/E12.

On macOS/Python 3.11, 54 widget-behavior checks plus four existing client state-view
checks passed. Ruff/format, Windows-target mypy (20 GUI files) and the 473-module boundary
check pass; existing non-GUI size warnings remain. Regressions cover preparation
cancellation, contextual New session, distinct stop selections, Cancel/Escape/window
close, repeated-click dialog identity and current phase/control gates. Updated layout
assertions check full-width Setup above equal Start/Stop, one horizontal readiness row
in System controls, four remaining cards, Age (dph) and no status pills; HUD/log sizing
and draft/readiness behavior are preserved. Configuration/Running/narrow renders and the Stop chooser
were inspected in earlier increments; the current native Dashboard at 1175×883,
460×350 preview selector and narrow Dashboard were inspected. New checks cover
modeless reuse, close/reopen persistence, checkbox visibility, pending requests, failures,
external-closure reports, inventory removal and authority loss. Header placement and
snapping tests cover right-side space, a negative-origin screen and screen-edge
clamping; native checks confirmed equal frame tops and a 12-pixel gap at 900-pixel
main-window width, plus the clamped case at 1175 pixels in the prior increment.
Current native capture confirms Browse placement and compact Windows-style path
rendering. New checks cover selection/cancellation/late-selection locking, unchanged
full path text, log retention/follow behavior and geometry across widget recreation
using a temporary preferences file. External image windows still do not exist in the
frontend; their backend geometry integration is not claimed.
Current Devices checks cover icons/tab order, per-camera draft retention and role
uniqueness, active-source preview restrictions, review-only actions and
disconnected/observer/running gates. New tests cover PFS selection/cancellation,
late-result camera identity, and fitted HUD/expanding log behavior on all seven
page/subtab surfaces. All four native subtabs were
inspected at 1175×883, plus a settled 720×800 layout without horizontal scrolling.
The inspection windows were closed with harness confirmation/exit 0, then the final
frontend reopened for owner review. [Dated evidence](gui-dashboard-2026-10-01/README.md)
preserves separate source hashes, checks, scripts and captures for each increment.
These are local presentation checks; owner review, Windows packaging and full
application/device/workload acceptance remain pending. The earlier Mac packaging
attempt failed at the existing AMD64 Windows DLL guard;
[rig acceptance](rig-verification.md) remains the Windows verification boundary.

### Backend review fixes (2026-10-08)

Source review plus ruff/AST scans produced candidate findings; those confirmed in the code are fixed and tested, with evidence in [review-evidence-2026-10-08](review-evidence-2026-10-08/README.md). Fixed: supervisor shutdown replay, tracking-release gRPC retry, tolerant `source_registered`, concurrent worker cleanup, warnings for rejected participant Shutdown and persistent helper errors, launcher parser/reader resilience, client timeout messages and E02 Ctrl+C scope, shared policy digest ([E14](../docs/architecture/system-contracts.md#e14) revision 207), loopback/`contract_version` checks. Still open: `shutdown-health-checks` (controller-loss and fencing gaps), the TODO "For review" refactors, and coverage measurement. Local results do not close E15 rig checks.

## Cohesion and test organization

Reviewed size exceptions under ARCH-002: controller `assembly.py` (519 lines,
flat component wiring; `runtime.py` is now 422 lines),
supervisor `shutdown.py` (505 lines, retained intent/deadlines and ordered cleanup,
delivery and operation outcomes), shared `incidents.py` (topology/proof
checks) and native `jobs.py`/`security.py` (Windows ABI and exact handle ownership).
These boundaries do not permit unrelated additions; extract a separable responsibility
before extending them. Acquisition exceptions belong in its report.

Supervisor native exit ordering and final absence inspection now live in the focused
`process_exit.py`; it receives the registry, native interface and shutdown state,
and returns evidence without changing coordinator outcomes. The small
`worker_context.py` owns the work-scope comparison shared by registration, discovery and
transport. No
whole-runtime dependency or duplicate authoritative state was added. Registry,
worker-transport and shutdown regressions extend their existing behavior modules;
no additional test module was needed.

Controller `lifecycle/interruption.py` is now 444 lines (previously 525); finalization
outcomes and cleanup remain there, while the 360-line `metadata/coordination.py` owns
writer closure. Removing the lifecycle owner's direct metadata-state dependency
keeps one authoritative state owner. Camera retirement shares the existing device
state and adds no wrapper module. Regressions extend the existing metadata, safety,
camera-evidence and lifecycle behavior modules; admission tests use the real
retention component instead of a stale method-only stub.

Tests are grouped by behavior. The 2026-09-30 consolidation reduced 105 test modules
to 67 (acquisition 40→22, controller 37→23, supervisor 10→7, shared 7→7,
platform 7→5, launcher 2→1, client 2→2). All 24 fix-named modules were absorbed or
renamed by responsibility; test-to-test imports were removed. Controller's now
533-line lifecycle-command module retains its common interruption/finalization
fixture, including the regression that failed trial metadata cannot skip sealing;
acquisition's 591-line worker-foundations module was not extended.

The 2026-10-01 cross-backend ARCH-002 sweep rechecked controller and supervisor
package boundaries alongside acquisition, Visual Stimulus and Tracking. It found no
additional safe controller/supervisor extraction; retained size exceptions and
unresolved observations remain as recorded above.

## Verification evidence

Earlier rows retain historical results and were not rerun during report consolidation;
their uncommitted snapshots had no recorded source revision. The supervisor
simplification rows describe newly executed checks, based on HEAD
`7ae3767cea92bf7af94153d417e40df997e1fd05` plus pre-existing and new working-tree changes.
[Raw evidence](runtime-evidence-2026-09-30/supervisor-simplification.txt) retains commands,
results, scope and SHA256 hashes of supervisor source/tests; HEAD alone does not
identify that snapshot. Concurrent Visual Stimulus backend renaming was preserved;
the evidence includes revalidation and a refreshed source/test manifest after that
rename. Counts describe each run's snapshot. The second supervisor pass has its own
[raw evidence](runtime-evidence-2026-09-30/supervisor-simplification-pass2.txt)
(same HEAD, later working tree, new source/test hashes).

The controller simplification uses the same HEAD plus the dirty working tree.
[Controller raw evidence](runtime-evidence-2026-09-30/controller-simplification.txt)
records increment results, final commands, an unchanged source/test SHA256 manifest,
and the separate acquisition-preview fixture failure encountered by broader checks.
That fixture failure was subsequently corrected and verified in the
[acquisition simplification pass](acquisition.md#verification-record).

| Date / scope | Command or method | Recorded result and limits |
| --- | --- | --- |
| 2026-09-30, portable run before backend audit | `python -m pytest tests -q`, asyncio auto | Controller/supervisor/shared/platform/launcher/client passed except seven acquisition-loader-blocked tests; native Windows skipped. The later loader correction was not a rerun pass. |
| Same portable snapshot | `ruff check src tests tools`; `ruff format --check src tests tools`; `mypy --platform win32`; `python tools/check_backend_boundaries.py` | Passed; 323 source files typed; zero boundary violations. |
| 2026-09-30, backend source audit | Ruff lint/format, Windows-target mypy, boundary checker, Python compilation and TOML parsing | Passed: 439 formatted files; 325 source/regression modules typed; 269 backend modules, zero violations; 15 TOMLs parsed. |
| Same audit | `pip check`; wheel/sdist build with `--no-isolation`; pytest collection | Passed dependency consistency/build; 483 cases collected including 22 encoding/GPU regressions. No test bodies run. Driver/SDK compatibility untested. |
| 2026-09-30, test consolidation | Collection and AST comparison against pre-consolidation snapshot | All 483 collected cases, names, markers and fixture dependencies retained; 451 test functions, 678 top-level definitions and 3,218 module-binding comparisons preserved subject to reviewed helper merges/renames. Native/ring platform skips unchanged. |
| Same consolidation | Ruff, compile, Windows-target mypy, boundary checker | Passed: 74 test/support modules compiled; 323 runtime and 346 combined runtime/acquisition-test modules typed; 269 backend modules, zero violations. No test bodies run. |
| 2026-09-30, supervisor simplification increments | `.venv/bin/python -m pytest tests/supervisor -q -m 'not windows and not rig'` | Passed: registry increment 64, worker increment 96, shutdown increment 106 cases (audit baseline 55). Covers rejection/replay, work scope, stale/capacity-bound channels, independent delivery, native-boundary ordering/deadlines and distinct cleanup/exit outcomes. |
| Same refactor, integration | `pytest tests/supervisor tests/launcher tests/shared tests/client tests/controller/test_shutdown_handoff.py -q -m 'not windows and not rig'` | Initially 177 passed and two client RPC fixtures were blocked by sandbox loopback binding; network-permitted retry passed both. After concurrent renaming, reran the 177 non-listener cases and the two authenticated RPC cases separately: all passed. Combined coverage 179 passing cases; no native Windows/rig run. |
| Same refactor, static/source review | Scoped Ruff lint/format and `mypy --platform win32 src/cephvr/supervisor`; `python tools/check_backend_boundaries.py`; AST comparison of extracted native exit body | Passed: 30 source/test files formatted, 21 supervisor modules typed, 390 backend modules with zero boundary violations. Native exit control flow matches the pre-refactor working copy after dependency/backend-role renaming, excluding result packaging. Shutdown's remaining size warning is assessed above. |
| 2026-09-30, supervisor simplification second pass | `pytest tests/supervisor tests/visual_stimulus/test_transport.py -q -m 'not windows and not rig'` after each of four increments; scoped Ruff lint/format, `mypy --platform win32 src/cephvr/supervisor`, boundary checker, `git diff --check` | 110 passed throughout (106 supervisor plus 4 transport); 20 supervisor modules typed; 450 backend modules, zero violations; supervisor source 5,208 to 5,013 lines. Only `shutdown.py` (505) still exceeds the size warning. No test assertion changed; edits limited to renamed methods/modules and fake-port no-ops. |
| Same pass, integration | `pytest tests/supervisor tests/launcher tests/shared tests/client tests/controller/test_shutdown_handoff.py tests/tracking/test_runtime.py tests/visual_stimulus/test_transport.py -q -m 'not windows and not rig'` | 188 passed (three repeats). One earlier run had a tracking heartbeat-catalogue test fail while another session was editing the Tracking runtime; it reproduced against the pre-refactor supervisor and passes with the current tree (see raw evidence). No native Windows/rig run; E15 checks remain open. |
| 2026-10-14/15, controller/supervisor audit fixes | `pytest tests/supervisor tests/controller tests/shared tests/client tests/launcher tests/platform -q -m "not windows and not rig"` after each increment and at the end; `ruff check`/`ruff format --check` on supervisor, controller and their tests; `mypy --platform win32 src/cephvr/supervisor src/cephvr/controller`; `tools/check_backend_boundaries.py`; `git diff --check` | Final (after the owner-approved follow-ups) 840 passed, 1 skipped, 4 deselected; 129 source files typed; 690 backend modules, zero violations; ruff and whitespace clean. New regression tests were each confirmed to fail without their fix (admission, setup cancel, registry, calibration Close, camera release, startup recovery). Two existing tests were corrected: a lifecycle fixture now models an activated session's registered context, and a client RPC test no longer asserts the failed cancel that pinned the Setup-cancel defect. Local only; no Windows-native/rig run. |
| 2026-10-01, controller simplification second pass | `pytest tests/controller tests/client tests/shared tests/launcher tests/supervisor tests/visual_stimulus/test_controller_communication.py -q -m 'not windows and not rig'` after each of seven increments; scoped Ruff lint/format, `mypy --platform win32 src/cephvr/controller`, boundary checker, `git diff --check`; whole repository `pytest tests -q -m 'not windows and not rig'` at the end | 379 passed throughout (200 controller cases collected before and after); whole repository 736 passed, 6 skipped, 2 deselected; 74 controller modules typed; 453 backend modules, zero violations. Controller source 16,494 to 16,297 lines (72 to 74 modules: `receipts.py`, `setup_resolution.py`), tests 7,069 to 6,991. No assertion changed; edits limited to removed dead fixtures/kwargs and shared fixture imports. `assembly.py` (519) remains the only controller size advisory. No native Windows/rig run; E15 checks remain open. [Raw evidence](runtime-evidence-2026-10-01/controller-simplification-pass2.txt). |
| 2026-09-30, controller simplification increments | `.venv/bin/python -m pytest tests/controller -q -m 'not windows and not rig'` | Baseline 187 passed; lifecycle/metadata regressions 195 passed; camera retirement regressions 199 passed. Final integration adds one finalization regression, bringing controller coverage to 200 cases. |
| Same controller refactor, integration | `pytest tests/controller tests/supervisor tests/shared tests/launcher tests/client -q -m 'not windows and not rig' --ignore=tests/client/test_controller_rpc.py`; separate network-permitted RPC run | 374 passed, plus two authenticated controller RPC tests passed: 376 total. Original deadlines, independent interruption delivery, metadata closure ordering/failure and camera result retention are covered. Native Windows/rig acceptance remains pending. |
| Same refactor, broader acquisition checks | Added `test_manual_devices.py`, `test_manual_preview.py`, `test_cleanup_aggregation.py` to the non-listener integration run | 386 passed, one existing acquisition-preview test failed and reproduced in isolation. Its fixture leaves `WorkerPreview.started=False`, so the pause path skips it. Both that test and its acquisition implementation are unchanged from HEAD; no acquisition fix is included here. |
| Same controller refactor, static/source review | Scoped Ruff lint/format, `mypy --platform win32 src/cephvr/controller`, boundary checker, AST comparison against pre-refactor working copy | Passed: 97 source/test files formatted, 72 controller source modules typed, 390 backend modules with zero violations. Extracted metadata closure, interruption delivery and camera-retirement bodies preserve statement order after dependency/deadline-name normalization. This source evidence does not establish rig equivalence. |

The consolidation's initial test-only mypy invocation omitted source discovery;
rerunning with `src/cephvr tests/acquisition` resolved it without suppression.
Earlier modular review compared moved storage classes by AST and lifecycle branch,
lock and await ordering against a working-tree snapshot; review corrected stale
limits injection, shadowed activity handling, warning retention and shutdown text.
This establishes reviewed source preservation, not behavioral equivalence on the rig.

The 2026-09-23 declaration audit compiled control/acquisition Protobuf with isolated
`grpcio-tools 1.84.0` / `protobuf 7.36.2` under `/tmp`; TOML, register revisions and
local links passed. Commands and source revision were not retained. Clock and
controller-loss declaration findings are owned by [host clock](../contracts/host-clock.md)
and [controller health](../contracts/controller-health.md). That historical schema
check is neither current runtime validation nor a second unresolved audit worklist.

Follow [E15](../docs/architecture/system-contracts.md#e15) for lightweight local
implementation/communication tests and native/device/full-workload rig checks.
Execution instructions and retained-result requirements are in
[rig verification](rig-verification.md#execution-and-results).

## Post hoc alignment compatibility review

2026-10-14 source review (`posthoc-alignment-review`): supplied Desktop guide
`raw_trial_preprocessing_and_spikeglx_alignment.md` and sibling CephVR1 checkout
at `914ecbc` (matching the guide), particularly session_compiler/core/alignment.py,
datasets.py and compiler/record schema paths; compared with current dirty CephVR2
contracts and acquisition/tracking/Visual Stimulus writer source. No session was
compiled and no hardware or scientific timing acceptance was performed.

Under [SYS-004](../architecture.md#sys-004),
[E04](../docs/architecture/supervisor.md#e04),
[A07/A09](../docs/architecture/acquisition.md#a07),
[T19](../docs/architecture/tracking.md#t19) and
[V22/V28/E13](../docs/architecture/visual_stimulus.md#v22), current files carry
session/trial identities, camera-native provenance, source/video-slot joins,
tracking source lineage and per-output stimulus submission/marker evidence.
These support external alignment when the required streams were saved and hardware
correspondence is established; they do not supply measured OneBox times themselves.
CephVR1's CSV reader and ten-frame optical-tag assumptions cannot consume CephVR2's
JSONL records and six-frame marker every 60 submissions unchanged. A09 frame_id
counts received images, not hardware triggers; never use its gaps as pulse gaps.
Camera native counter meaning must be read from its descriptor. Review-video padding
must join to its original source, never become additional scientific observations.

Unresolved alignment limits: first-source/first-pulse assumptions can hide integral
frame offsets; periodic optical landmarks cannot identify arbitrary missing cycles;
one photodiode cannot prove other outputs' illumination times; saving Off removes
required detailed histories. Probe-to-OneBox shared-sync mapping remains external,
separate from discovering probe files or controlling SpikeGLX. The checked-in pulse
inventory is unset and paired scientific acceptance remains open in the existing
[rig checklist](rig-verification.md); this review does not infer live rig wiring.
Legacy thresholding uses global extrema and 100-sample closing: noise sensitivity
and pulse merging are risks, not observed corruption in a tested session.

Recommendations, not accepted changes: use version-specific readers feeding one
shared inspection/compiler alignment core; retain native edge sample indices,
recording/segment identities and explicit per-row timing/anchor quality; derive
analysis tables/events externally from canonical records instead of adding competing
runtime CSV logs. Reuse existing central schema/output index and resolved pulse
inventory; enrich missing sync-route/probe-segment provenance only where needed.
Consider separating compact scientific stimulus evidence from optional review-video
encoding to reduce load while retaining timing history; this requires an E13 policy
choice. Additional physical absolute anchors or per-output optical measurement
require their own accepted scope and rig validation, not merely new JSON fields.
Legacy code already uses memmap, block/halo edge extraction and virtual views;
profile disk/concurrency and avoid duplicate notebook processing before adding
parallelism or changing storage format. Offline analysis implementation stays deferred.

Owner clarification: assess missing raw evidence only; the owner will build the
CephVR2 compiler separately. Additional source findings: A07 ties camera frame logs
(including optional native counter/timestamp evidence) to save_video, whereas T14
allows Tracking saving independently. Tracking records retain host/source lineage,
but do not replace the full acquisition native-clock history when camera saving is
Off. E13 similarly couples detailed presentation evidence to review-video saving.
These are accepted configuration limitations, not a claim of corrupted files.
The earlier missing-Eye finding is resolved by E12 revision21's first-class Eye
inventory and active external-trigger Setup requirement; see the current alignment
readiness section above. Actual channel assignments and pulse proof remain rig-pending. Raw files also do not establish
an absolute first camera-trigger anchor, an absolute optical cycle identity, measured
exposure latency, or other-projector optical onsets. Their necessity depends on the
required timing claim; metadata alone cannot create missing physical observations.


Oct16 `preview-consumer-authenticated-handoff` completes the owner-approved
[E08](../docs/architecture/system-contracts.md#e08)/[A10](../docs/architecture/acquisition.md#a10)
amendment. A production-port in-process probe reproduced controller relays failing
consumer-only supervisor authentication. Supervisor now authenticates either the exact
current controller or the registered consumer before retaining unchanged terminal
FAILED/RELEASED proofs. Existing generation/token/loopback/duplicate-metadata and exact
report checks remain; ATTACHED rejects at supervisor. Controller forwards ATTACHED only
to acquisition and terminal proofs to both owners. Independent reporting, original
handoff timeout and cleanup obligations remain. This is not evidence of the historical
native preview fault's cause. Real loopback transport coverage exercises both accepted
routes, idempotence and invalid credentials/subjects/payloads; focused routing coverage
checks acquisition-only attachment even when supervisor is unavailable. No aggregate
closure is inferred; rig acceptance remains open.

Final Oct16 integrated development validation: backend/authenticated1860 passed,
five platform skips and five exclusions; Ruff passes,679 files formatted, Win32
mypy583 source files and boundaries702/zero violations. The supervisor service remains
focused on transport authentication/delegation; preview retention has its own bounded
owner. Existing cohesive-size advisories were reviewed without another abstraction or
dependency. Documentation checks find zero new broken local targets/anchors; three
pre-existing unavailable image references remain. Commands/raw outputs and source
snapshot are in the [evidence context](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
Local completion does not close Windows, hardware or full-workload E15 acceptance.
