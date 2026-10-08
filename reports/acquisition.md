# Acquisition status

Oct8 native dummy execution (`gui-backend-dummy-experiment`) exercises both managed
camera connection/preview/disconnect paths and real unpaired Setup/Start. Runs40–42
complete the 60 s trial/session with confirmed cleanup and closed camera recordings;
Tracking velocities stay disabled independently from its camera video. Run42 counts
1,198 Behavior and 2,397 Tracking frames; complete external CPU decode passes both,
and frame-log video indices/counts match. SDK-reported missed/failed buffers and
resynchronizations are zero; optional timestamp conversion and some transport counters
remain unavailable. Exact cutoff and post-cutoff accounting complete under the owner's
temporary 1,000 ms allowances, which are budgets rather than measured rig guarantees.

Recorded delivery is about 20/40 fps against configured 30/60. MCU-only diagnostic
counts are 61/120 rising edges in 2 s, supporting the requested generator cadence
without establishing electrical receiver correlation. Both PFS baselines disable the
internal camera limiter; backend settings had enabled it when applying the saved
free-running rate even in externally triggered mode. Preserve that PFS choice under
[A10](../docs/architecture/acquisition.md#a10); 38 owning adapter cases pass, with
run43 native verification in progress. Do not infer a dropped trigger from transport
frame counters, which count accepted camera frames. Gap padding remains pending below.

Repairs under A02/A07/A08/E08 cover exact preparation/readback, absolute output paths,
Schedule/Release joining, preparation-parent lifecycle, normal end/MCU OFF, SDK stop
before bounded drain, bare cleanup commands and retained failure delivery. Completed
cleanup publishes durable owner ENDED; coordinator accepts only exact quiet terminal
liveness. Shutdown uses delivered closure without changing its identity and avoids
cancelling gRPC termination before server.stop. Run42 remains healthy idle and closes
normally with exact all-owned absence. Current restoration/full regressions remain
pending. [Integration assessment](runtime.md#current-scope-and-review),
[raw evidence](rig-wiring-evidence-2026-10-08/dummy-experiment/).

Owner-selected video timing revision (2026-10-08):
[A07 revision 58 / A08 revision 49](../docs/architecture/acquisition.md#a08)
require padding recording gaps and explicit encoded-frame/source/duplicate mapping
for post hoc exclusion. Current frame-log schema 2 and recording pump remain
unpadded. Slot assignment, leading-gap treatment, schema formalization and writer
implementation are pending; no new runtime or rig pass is claimed.

Microcontroller ownership update (2026-10-08) follows
[A10 revision 55](../docs/architecture/acquisition.md#a10) and
[A11 revision 40](../docs/architecture/acquisition.md#a11): serial, watchdog/keepalive,
diagnostics and firmware source/image/tool/handoff now belong to the controller.
Acquisition calls its authenticated typed camera-trigger API with the original absolute
deadline, exact claim and existing boundary/stop evidence. It never opens COM or
runs firmware tools. Acquisition cleanup confirms only the camera claim release after
OFF; controller separately owns physical COM/native closure. Last external manual
Disconnect releases the claim after camera cutoff; remaining external previews retain
it. Unconfirmed release keeps evidence and cleanup pending. Sessionless pulse edits
with no external previews also release their verified-stopped claim.

Microcontroller config/policy 1 is the sole generic serial/I/O/defaults owner; acquisition
config/policy 18 retains camera pins/rates and distributes the resolved serial timing
compatibility fields. New replay/identity/cleanup, idle-policy and preview-release cases
extend the existing owning test modules; the existing core owner/protocol and firmware
cases moved intact to controller. Portable acquisition/controller/supervisor/shared/client
passes 812 with five platform skips and three marker exclusions. Current integration,
static results and limits are in the [runtime assessment](runtime.md#current-scope-and-review).
Actual Windows camera-trigger timing, watchdog behavior and GUI/native `.ino`/`.hex`
Upload remain in the [single rig checklist](rig-verification.md#managed-mcu-and-camera-gui-verification).
No runtime restart or physical command was performed for this migration.

Current development integration: [A03](../docs/architecture/acquisition.md#a03) and
[A10](../docs/architecture/acquisition.md#a10) authorize the acquisition-owned ordered
Tracking ring in exact Configuration diagnostic preview scope. Sol accepted the
allocation, actual manual capture publication, source/transfer identity and confirmed
release repairs. The affected acquisition worker/manual-preview, controller diagnostic
and full Tracking selection passed 99 tests with one deselected, independently repeated
by Sol. Actual capture_once coverage verifies native pixels, frame IDs and discontinuity
publication without a recording window; retired resources remain held until every display
and Tracking consumer confirms release. [Tracking evidence](tracking.md) records scope and raw
results. Final managed GUI/development integration is accepted; native/rig acceptance
and the current camera/MCU findings below remain. See the
[managed wiring assessment](runtime.md#current-scope-and-review).

Current GUI camera integration (2026-10-08) follows
[A10](../docs/architecture/acquisition.md#a10). Camera Connect uses existing Start then
Show operations for the exact confirmed run; Disconnect uses existing stop/release.
Controller firmware compilation extends the previously implemented verified-image
upload with the same sole serial owner. Keepalive suspension while firmware work is
busy retains ordinary health failure handling. Existing manual installation evidence does
not establish native GUI compile/upload acceptance.

ARCH-002 cohesion review keeps coordinator runtime/assembly as composition and cleanup
as the single camera proof join. Controller firmware image validation, tool ownership
and serial handoff are focused modules; camera/Microcontroller panels retain only presentation/intents,
with managed dispatch separate. The shared native launcher adds a focused registered-plan
callback and stop-method binding, retaining existing encoder defaults and deadlines.

Current native recording follow-up: runs 22-28 expose and repair retained trial failure
admission, camera clock text validation, gray raw input naming, cleanup result format,
pre-Ready encoder obligations, asynchronous Schedule/Release sequencing, 64-bit GPU
fence arguments, compositor resource order and trial-parent lifecycle forwarding.
Each interrupted Desktop reservation and exact process exit remains retained in the
[dated dummy evidence](rig-wiring-evidence-2026-10-08/dummy-experiment/). No completed
60 s run, video decode/count verification or clean full-workload acceptance is yet
claimed. Current retry remains in progress; temporary camera drain/pacing/GPU inputs
must be restored. ARCH-002 reuses the existing focused owners and test modules.

## Current Windows wiring checks

Latest actual rig execution (2026-10-08, `7ba43b1` plus focused repairs): both camera
identity checks and two Behavior Connect/Show/Disconnect cycles pass through the
GUI's managed dispatch, with over five seconds of visible capture each and confirmed
camera/window/trigger-claim release. Native image frames begin at (1449,0), then
(1473,24) after moving the actual GUI, exactly beside its visible right/top edge.
Captured images show camera content. Existing isolated mouse/viewport tests remain
separate from actual mixed-DPI, selector and button-interaction acceptance.
Tracking Connect/Show/Disconnect now passes twice with the owner-approved
BehaviorSquid PFS, six seconds of real capture each and confirmed camera/both-ring
release. The earlier `COORDINATOR_HEALTH_LOST` report mislabeled rejected lifecycle
evidence: readiness and cleanup each assumed one producer ring, while Tracking
prepares two. Validate the exact complete set and retain the rejection reason in
the existing bounded health report; health/deadline policy is unchanged. The focused
helper validates every release before committing any ledger release (A03/A10/E08).
ARCH-002 extraction reduces the lifecycle validator and introduces no dependency or
whole-runtime reference; the existing worker executor remains lifecycle composition.
The final acquisition/affected-controller suite passes 363 with one platform skip;
Ruff/format, six-source Win32 mypy and 618-module boundaries pass. Original settings
are restored and exact normal shutdown/guard/COM release is confirmed. No scientific
recording or ordered Tracking diagnostic ran.
[Diagnosis, reproducers and final evidence](rig-wiring-evidence-2026-10-08/README.md#tracking-connect-and-release-correction).

Controller-owned MCU tests with acquisition disabled, actual `.ino` compile/HEX
upload, compile-failure preservation, active-D9 control release and isolated firmware
watchdog state pass after repairing invalid inactive-diagnostic cleanup and native
pipe construction. Those checks do not measure electrical delivery or camera rate.
Later `.ino` upload reproduces a supervisor executable-query failure and missing
native job termination permission. The focused platform repair passes two final
compile/verified uploads and serial-preserving compiler rejection, after three
exit-check-only passes; exact shutdown and staging cleanup are confirmed.
[Current native-job evidence](rig-wiring-evidence-2026-10-08/README.md#ino-upload-native-job-correction).
[Current methods, settings, images and raw failures](rig-wiring-evidence-2026-10-08/README.md)
retain provenance; remaining physical/full-load checks stay in the
[single rig checklist](rig-verification.md#managed-mcu-and-camera-gui-verification).
The earlier full Windows suite has 1463 passes/eight existing GUI failures/five
privilege skips; it predates the selection and Tracking repairs above. Runtime and capture are stopped.

Later owner console evidence (2026-10-08): enabling Tracking then importing a PFS
on the Behavior row yields `tracking.device.settings.trigger_source` validation
failure. Source review confirms the Behavior edit copies the whole configuration
and changes only its selected camera; enabled external Tracking still requires its
own explicit input. The prior saved snapshot has Tracking disabled, external timing,
and no PFS/input. A PFS hint of Line2 on Behavior does not configure Tracking or prove
application. Duplicate role assignment is independently refused. This is a reported
configuration/workflow failure, not new hardware evidence; no device action ran.
Improve cross-camera validation feedback under the existing GUI task.

Owner-requested camera selection repair (2026-10-08, G01): inventory restoration
now reloads the selected role/PFS/timing/rate even without a configuration revision
change. Clicking Use also selects that camera's row. Per-camera drafts remain
independent, and loading/selection sends no settings command. Both inventory rows
and checkbox directions reproduce before repair; final owning Windows Qt/offscreen
camera/PFS tests pass 27 with 295 deselected. Ruff/format, Win32 mypy and boundaries
pass. This later fixture-based GUI increment does not repeat physical capture or
the earlier full suite. [Dated results/source scope](rig-wiring-evidence-2026-10-08/README.md#later-camera-selection-correction).

Earlier owner evidence reports the image did not open snapped outside the GUI's top-right edge.
Read-only native geometry of the reopened GUI finds a 1,456-pixel outer width on
a 1,920-pixel work area; the old 640-pixel image rule produces x=0 over the GUI.
The GUI now fits the square into available right-hand space before left fallback,
without a tool-window gap. Under [G01 revision 123](../docs/architecture/gui.md#g01),
GUI and acquisition use visible physical frames; the native test reproduces a
seven-pixel invisible-border offset before repair and exact placement afterward.
Windows documents this distinction in [GetWindowRect](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect).
Six GUI and one native regression fail before the repair; ten selected GUI checks
and 549 acquisition/controller/client checks pass afterward (two privilege skips).
The final focused native/reader selection passes four after removal of a redundant
initial move. Ruff/format, Windows mypy (311 sources) and boundaries (604 modules,
zero violations) pass. [Current inputs, raw methods and limits](rig-wiring-evidence-2026-10-07/preview-snap-context.json)
retain the owner's observation and passive bounds. ARCH-002 extends focused geometry
and display owners without new processes, RPCs or dependencies; policy 15's existing
presentation rule is retained. The reopened runtime is preserved and needs a full
restart to load both sides of this repair. Actual camera positioning/visibility,
mixed-DPI and ordered Tracking diagnostic acceptance remain open; the later Oct8
physical preview cycles above supersede the preview health failure.

The owner-requested preview presentation follows [A10 revision 54](../docs/architecture/acquisition.md#a10)
and [G01 revision 122](../docs/architecture/gui.md#g01), with acquisition policy 15.
GUI Show carries a bounded physical-desktop placement hint; acquisition displays
a fixed square with aspect-preserving padding, pointer wheel zoom and double-click
fit reset. Interaction redraws the private cached image while capture stays idle
or continues independently. Focused viewport, placement-admission and native
Win32 checks pass; affected acquisition/controller/client integration passes
**549 with two symlink-privilege skips**, and eight selected offscreen GUI checks
pass. Native windows confirm 256×256 image areas at requested coordinates,
real wheel/reset redraw without new publications, and independent X/producer
lifetimes. Ruff/format (448 files), Windows mypy (395 sources) and boundaries
(604 backend modules, zero violations) pass. ARCH-002 keeps geometry and pixel
transforms in focused owners; manual capture (548 lines), camera admission (505)
and GUI composition retain their existing orchestration duties. No new SDK owner,
process or dependency is introduced. [Dated methods and input hashes](rig-wiring-evidence-2026-10-07/preview-presentation-context.json)
record scope. The running owner runtime was preserved and needs a full restart
to load this increment. Actual GUI-edge placement across monitor/DPI arrangements
and physical camera interaction remain in the [rig checklist](rig-verification.md).

Earlier [authorized installation and retest](rig-wiring-evidence-2026-10-07/mcu-installation-and-preview.md)
closes the observed host/board version mismatch: current flash is backed up, exact
protocol-3 firmware upload verifies, and actual CAPS reports `cephvr2_uno_2`.
Direct bounded D9/D10/D11 count/reset/Stop/OFF checks pass; managed D9/D10/D11
Test/Status/Stop and D9 automatic two-second timeout pass. Both Basler connection
checks pass. Real Behavior Start/Show/Hide/
native close/reopen/Stop passes with acquisition-owned window and capture unchanged
by hiding. Tracking exposed a readback-adoption revision defect, repaired within
the existing camera-resolution owner; 54 focused and 535 integration cases pass
(two integration privilege skips), with static checks passing. Tracking then gets
past preparation but Start is rejected and the existing coordinator-health shutdown
recurs. Exact fault cleanup is confirmed. The later Oct8 two-ring evidence repair
supersedes this Start/display failure; ordered consumer diagnostics, sustained/full-load
health and physical electrical/receiver acceptance remain open.

Earlier owner test reports no D10 pulses and repeated incomplete-result failures,
while D9 and D2 complete. Source/regressions establish missing camera CONFIGURE
before DIAG_START; manual Test now configures the selected camera output first,
and failure prevents start. Controller preserves the backend reason and follows
protocol 3 for Connect completion. Seven targeted cases and **526 acquisition/
controller/client cases pass**, with two symlink-privilege skips; static checks
pass. The live read attempt lacked an operator credential, so no current device
state or exact firmware rejection was collected. The runtime was not restarted
and firmware was not uploaded; bounded board count tests remain pending.
[Console, reproduction and correction to prior protocol-version coverage](rig-wiring-evidence-2026-10-07/mcu-camera-diagnostic-repair.md).

Owner-selected counted diagnostics implement [A11 revision 37](../docs/architecture/acquisition.md#a11)
with MCU protocol 3 / `cephvr2_uno_2`. The counted increment was validated at policy
13; camera-viewer work advanced the binding to 14 and presentation advances it to 15 while
preserving protocol 3, and all 45 owning MCU/configuration cases pass again. The existing counter
counts observed D2 input edges or generated output LOW-to-HIGH writes, including the
first HIGH; D9's held-HIGH test counts one. Camera counts come from timer transitions,
not rate-times-duration estimates. Counts reset per test, saturate at uint32 maximum
and remain available after Stop; ordinary session/STATUS pulse counters remain absent.
GUI distinguishes generated from observed edges. The Uno build passes (11,078 flash
bytes / 1,112 SRAM bytes), owning MCU/configuration tests pass 45, affected-owner
integration passes 508 with two privilege skips, and six GUI diagnostic cases pass.
Ruff/format (331 files), source mypy (305) and boundaries (598 modules, zero violations)
pass. [Counted diagnostic evidence and exact image](rig-wiring-evidence-2026-10-07/mcu-counted-diagnostics.md)
are ready for matching manual installation and on-board verification; no upload has
run in that prepared increment; the later authorized installation above supersedes
its installation status. New host restarts require protocol 3 firmware; protocol 2
is rejected at connection. This is implementation
and build evidence, not measured electrical delivery or an on-board count pass.

The owner confirms the repaired Preview works, then selects acquisition-owned OpenCV
windows matching CephVR1.0 under [A10 revision 53](../docs/architecture/acquisition.md#a10)
and [G01 revision 121](../docs/architecture/gui.md#g01). This is user-reported viewing
without generation/settings/timing provenance. The earlier identity/policy and
pending-operation repairs and their raw failures remain in the [dated evidence](rig-wiring-evidence-2026-10-07/README.md).

GUI Preview now sends Show/Hide for the exact active manual capture run. Acquisition
owns each window, private converter and newest-frame reader on its Win32 thread;
Show requires the first converted image to reach a visible window. Native X/Hide
releases only the reader/window, leaving capture and pulses running. Stop, pulse
reconfiguration and owner cleanup join local reader release before buffer closure.
A native-ledger obligation remains unresolved on failed release; cleanup still
attempts SDK/pulse stop. Monotone authenticated visibility/failure observations
cannot complete a command, resurrect retired runs or override a reopened window.
External client transfers and ordered Tracking consumers keep their separate exact
release rules. The Qt camera reader and unused GUI transfer path are removed.
Acquisition policy 14 retains concurrent MCU protocol 3 and selects OpenCV display;
matching `opencv-python==4.13.0.92` replaces the headless dependency in acquisition
and Tracking. The installed build reports WIN32UI and `pip check` passes.

Windows isolated affected-owner/client tests pass **526**, with two symlink-privilege
skips; selected GUI/bridge checks pass **17**. Final first-image/close-reopen refinements
pass **64** focused owner checks. These include two real OpenCV windows displaying
latest shared-ring images, native X closing one while the other window and both
producers stay active, RGB-to-BGR private-copy handling, display/release failures,
exact visibility/terminal identity and cleanup attempts despite viewer failure.
Ruff/format pass 444 files; Windows mypy passes 391 sources; boundaries cover 602
modules with zero violations; package build passes. ARCH-002 extracts viewer commands
from manual capture and pure device-view merging from projections. Remaining larger
manual capture (541 lines), camera admission (501), runtime and GUI files keep their
cohesive lifecycle/composition duties; new owners receive focused records/operations.
[Current OpenCV evidence](rig-wiring-evidence-2026-10-07/opencv-context.json) records
methods, hashes and limits. The window path supports 8-bit output and rejects other
depths explicitly; no physical display-precision pass is claimed.

The original OpenCV implementation increment left the owner runtime untouched.
The later authorized firmware/restart and actual Behavior check above supersede
that limitation. Tracking release, sustained delivery and heartbeat acceptance
remain in the [single rig checklist](rig-verification.md).

The owner resumed rig checks on 2026-10-07 at `08d146d`; the
[dated scripts and results](rig-wiring-evidence-2026-10-07/README.md) retain exact
generation/command identities. Both connection-only camera checks pass. Behavior
40065509 D10/Line4 completes two managed Start/Stop cycles with running and released
camera/preview projections. This closes the previously observed command-completion
failure for those cycles, but desktop viewer/frame inspection remains unverified.

COM8 CAPS confirms protocol 2 / `cephvr2_uno_1`. Managed Status and Stop fail with
`required MCU result evidence incomplete`; their native cause is unresolved.
Later [owner-supplied controller diagnostic console](rig-wiring-evidence-2026-10-07/owner-mcu-console.md)
reports completed Start/Stop pairs for D2 input (120 rising edges), D9 active-high
output and D10 requested 30 Hz output. D9/D10 zero edge counts were expected by the
then-installed protocol 2 diagnostic contract, not failed pulse
tests. This establishes reported diagnostic completion; physical source/rate/level
and camera reception are unmeasured. Ordinary Status/Stop failures above are separate
operations and remain unresolved. The supplied paste lacks revision/generation/duration.
The owner clarified that these checks are intended to test physical signals and has
SpikeGLX open for receiver observation. The GUI's output edge-count display was
misleading: the initial display correction reported firmware HIGH/LOW for Trial state
and running/stopped pulse output for camera diagnostics. It is superseded by the
owner-selected generated-transition counting implementation above. Six existing GUI
diagnostic/control cases passed; waveform measurements remain pending
the owner's channel observations. The live runtime is preserved; this source change
appears on the next GUI restart. See [focused evidence](rig-wiring-evidence-2026-10-07/mcu-output-feedback.md).
Tracking 40747103 successfully imports the owner-selected BehaviorSquid PFS and
finishes editing: Line2, Mono8, 1588x1344, 5,000 us. Managed Start is rejected and
leaves a prepared/open camera projection. Camera workers report
`COORDINATOR_HEALTH_LOST`, including Behavior after successful Stop; the supervisor
shuts down the application. No claim is made about the precise heartbeat cause.
Attempted configuration restoration is rejected while ownership remains;
the exact launcher receipt subsequently proves all owned processes absent.

After process absence, an isolated two-second D11/Line2 check receives **81 valid
Tracking frames** with matched ON/OFF acknowledgements. The initial readback finds
FrameStart Off after managed cleanup; a first assertion stops without pulses.
The successful repeat restores the selected PFS's explicit On mode; afterward the
pre-probe Off mode is restored and camera/serial owners close. This proves bounded
receiver delivery, not sustained 60 Hz, optical/electrical waveform timing or
managed Tracking diagnostics. D9/D2 physical correlation, simultaneous capture,
full recording/throughput and existing A08/A10/A11/E15 deferrals remain in the
[single rig checklist](rig-verification.md).

## Preview recheck stopped by owner, 2026-10-06

Rig work was paused on 2026-10-06; the owner subsequently authorized development-machine diagnosis and resumed rig checks above on 2026-10-07. Behavior serial 40065509 received 41 SDK frames during
the two-second direct COM8 D10 → Line4 check at a requested 30 Hz. MCU ON/OFF
acknowledgements passed; the camera and serial owner closed. This verifies the
receiver path, not sustained 30 fps, waveform timing, Tracking or GUI acceptance.
The existing CephVR2.0 image was uploaded with verification after the owner
confirmed CephVR1.0 firmware was installed. CAPS now reports protocol 2,
`cephvr2_uno_1`; the prior flash is preserved alongside upload evidence.

Managed preview remains unfinished: acquisition retained ready/started lifecycle
evidence and received frames, but the final operator Start command failed with
`OPERATION_FAILED: exact completion missing`. An earlier Start succeeded, followed
by Stop failing on incomplete camera result evidence. No final managed Stop or
GUI viewer acceptance is claimed. Development-machine regression now reproduces a
concrete completion blocker: the status reporter explicitly includes an empty
preview run ID for idle/closed cameras, while controller projection validation
required every present ID to be a UUID. Thus untouched Tracking rejects Behavior
Start, and released runs reject Stop. The controller now accepts empty inactive
IDs and still requires valid IDs for prepared/running previews and all nonempty
IDs. Real reporter-to-controller tests failed with `invalid UUID` before the fix
and now complete both Start and Stop. This establishes the local defect, not that
it was the only cause of the saved rig timeout. Repeat viewer and closure checks
in the [managed rig checklist](rig-verification.md#managed-device-gui).

Development-machine validation after this correction: acquisition/controller
pytest (`-m "not windows and not rig"`): 417 passed, five skipped, one deselected;
Ruff check and format check pass for both owners/tests; Windows-target mypy passes
256 source files; boundaries check 555 modules with zero violations. Existing size
advisories affect unchanged source owners. ARCH-002 review keeps the correction
in the focused projection validator and extends the existing evidence tests; no
new dependency, protocol, timeout or ownership policy. Existing late-result and
missing-evidence tests remain passing. No Windows/device acceptance was rerun.

Repairs apply existing [A03/A10/A11](../docs/architecture/acquisition.md),
[E06](../docs/architecture/system-contracts.md#e06) and
[E07](../docs/architecture/experiment.md#e07): preview payloads declare their
existing non-saving capture scope; closed status carries an explicit empty preview
run ID; initial controller projection revision matches loaded configuration;
worker warning IDs use canonical UUIDs. Strict evidence validators and deadlines
remain intact. ARCH-002 review reused focused owners and existing tests, with one
composition initialization in controller runtime and no new dependencies.

Focused preview/status/controller checks passed 32 tests before the final warning
ledger regression revision. Earlier protected pytest temp ACL failures were
environmental. Scoped preview Ruff and two-source Windows mypy passed earlier;
the final warning-ledger test revision, full affected suite, expanded static checks
and boundaries were not rerun before the owner's stop. Temporary tracing was
removed. Authenticated shutdown completed sufficiently for no CephVR2 processes
and a free application guard; full graceful cleanup acceptance remains open.
See [dated evidence and firmware backup](device-connection-evidence-2026-10-06/README.md).

2026-10-06 legacy CephVR1.0 FPS investigation (source review and saved-run analysis,
not a 2.0 capture test): Behavior serial 40065509 acquisition CSVs from
`SP0002-141843` measure 17.4408 and 17.7476 fps using camera timestamps, with
matching host receipt rates and zero source-sequence/hardware-frame-ID gaps.
The second CSV contains 17,961 rows over 1,011.966 seconds; 12,397 intervals are
near 66.7 ms and 5,563 near 33.3 ms. This indicates missing acquisitions at trigger
opportunities rather than lost already-numbered frames. Legacy HUD uses preview
publication sequence/timestamps, so it is not independently authoritative, but
these camera-origin timestamps corroborate the reported low rate.
Saved integrity reports 12,406 duplicate and five padded video frames at 30 fps.
Idle read-only SDK inspection finds 25 ms exposure, 17.184 ms sensor readout,
frame-rate limiting enabled at 30.0003 and ResultingFrameRate 29.9994; throughput
limit 360 MB/s versus reported demand about 90.6 MB/s. TriggerMode was Off at this
idle inspection, so its readback does not prove exact triggered-run readiness.
The frame limiter operating at the trigger rate is the leading hypothesis;
electrical pulse arrival/readiness and a bounded limiter-disabled comparison
remain unmeasured. Basler documents ignored triggers before readiness and automatic
overlap for this model; summing exposure plus readout is not a supported diagnosis.
No camera settings, pulse outputs or source code changed. See
[dated analysis](device-connection-evidence-2026-10-06/legacy-camera-fps-assessment.json)
and [Basler trigger documentation](https://docs.baslerweb.com/triggered-image-acquisition).

Owner then requested stopping forced AcquisitionFrameRateEnable on legacy connect
and file load. The installed editable `basler-vision-software` dependency passed
readback `self.fps` into `BaslerCamera.start`, which invokes set_frame_rate and
unconditionally enables the limiter. Stream startup now passes only an explicitly
supplied config FPS; CephVR1.0's camera service supplies none, preserving the loaded
camera/PFS enablement through start and file-load restart. Explicit FPS overrides
retain their existing behavior. Existing dependency controller regressions cover
both loaded enable states, repeated refresh/restart and an explicit override;
controller/settings tests: 10 passed. Legacy connection/trigger tests: nine passed.
No dependency upgrade, GUI override, PFS edit or hardware setting change. Existing
changes in the dependency's Basler adapter/settings tests were preserved.
Restart CephVR1.0 to import the correction; files explicitly storing enable=1 will
still apply that value. A bounded real-trigger acceptance comparison remains open.

Status: host implementation, source review and lightweight local verification are
recorded below (2026-10-01). Bounded native checks pass; device and full-workload acceptance remain
pending on the rig. This is not experiment-readiness approval.

On 2026-10-06, real COM8 SerialOwner CAPS/STATUS and both Basler SDK
open/identity/readback/close checks passed; see [dated connection evidence](device-connection-evidence-2026-10-06/README.md).
The controller-backed MCU Connect also passed. A live defect in A11 keepalive
scheduling treated connection-only firmware state (configuration invalid, zero
watchdog, both outputs explicitly stopped) as an expired configured watchdog and
shut down the application. The scheduler now waits in that proven unarmed state;
running or missing output evidence still follows the existing failure path.
This uses the existing observation and deadlines, without new state or policy.
The camera diagnostic shutdown was isolated to missing protected child credentials
and an empty work context in acquisition's PlanLaunch. The launcher now supplies
the same credential to supervisor admission, coordinator peer registration and
worker bootstrap, and omits absent session work. PlanLaunch transport rejection
becomes an ordinary command-owner failure. Live authenticated COM8 and both camera
connection commands now pass; both cameras report closed and the original draft
was restored. Participation toggles also pass with missing trigger settings under
[G01/E07](../docs/architecture/experiment.md#e07); Setup still validates readiness.
The owner's Behavior-camera PFS failure was reproduced on real hardware:
`BslEffectiveExposureTime` is absent, and float Gain has no constant increment.
The focused GenApi helper now treats only the SDK's explicit missing-node result
as absent, and calls float GetInc only when HasInc permits it. Required writes and
other lookup/range failures remain strict. Controller completion retains the
original acquisition failure message instead of replacing it with an evidence
summary. These apply existing A10/E07 behavior; no policy/dependency changed.
After preserving the operator draft and restarting the idle runtime, authenticated
PFS import/adoption/Finish editing passed for serial 40065509, with Line4 external
triggering, applied revision 3, device closed and no cleanup pending. Raw SDK and
managed evidence are in the dated connection directory. Acquisition/controller
tests: 408 passed, 2 skipped; scoped lint/format/mypy and boundaries pass.
ARCH-002 review reused the cohesive feature/readback owners and existing tests.

The subsequent pending-operation rejection was a manual lease-loss cleanup
barrier: acquisition's snapshot omitted untouched Tracking while retaining closed
Behavior. A fresh coordinator now explicitly records both roles closed/not
previewing/no cleanup pending, before any access; begin access still marks the
affected role pending until release/readback. No unknown evidence is coerced into
closure. Real PFS/Finish editing and both camera checks succeed across two control
leases; both cleanup operations succeed and both cameras finish closed. The
existing worker ingress also uses the normal result reservation for connection,
export and Finish editing results; settings/import readback retain the large
reservation. Repeated small edits previously consumed that large budget. Fixed
ceilings, safety reserve, result-size checks and deadlines are unchanged. Rejections
now retain the worker admission reason. Focused regressions: 30 passed. Cohesion
review retains the existing status and ingress owners; no policy or dependency.
One bounded live attempt failed independently with SUPERVISOR_HEARTBEAT_FAILED;
the later combined live check passes. That startup failure remains unisolated in
the native runtime task. Operator draft restored; current GUI/runtime is running.
The initial direct connection readback was FrameStart Off on both cameras;
tracking's initial source was Software. No frames, pulse-output test, receiver
observation or waveform proof was performed; full capture/preview acceptance is open.

The subsequent manual-preview failure was reproduced after releasing managed
ownership: stock pypylon 26.3.1 rejects the Win32 HANDLE passed to WaitObject.
Under [A02/SYS-003](../docs/architecture/acquisition.md#a02), a small typed SWIG
bridge now invokes the SDK duplicating constructor through the normal pylon type
table, without manufacturing SDK pointers or changing capture ownership/waits.
Full real-camera settings resolution succeeds and closes the device. Native
duplicate lifetime and blocked-wait Python-thread wake checks pass (one native
test); preview failure/missing-evidence checks pass and failed resolution retains
cleanup pending until actual release. The original error reaches the controller.
Affected portable acquisition/controller suite: 410 passed, 2 skipped, 1 native
test deselected; later focused ownership checks: 29 passed. Windows wheel contains
the generated proxy and AMD64 bridge. SDK/compiler/SWIG requirements and missing
build failure are documented. Both managed connections pass after draft restoration
and finish closed, with no cleanup pending. Behavior-only D10/Line4 preview is now
authorized by the owner; frame-delivery verification stopped at the owner's request
to close CephVR2.0 and use CephVR1.0.
Its first attempt reached MCU setup but failed on a serial write timeout. The
transport ignored the channel's remaining acknowledgement budget and fixed every
write to 10 ms. Writes now use the original remaining budget at dispatch; reads
keep short native polls without repeatedly reconfiguring COM. Expired writes are
not dispatched; the channel still rejects late completion under A11's unchanged
deadline. Owning serial/protocol tests: 19 passed. The final native recheck reaches
SDK resolution, MCU configuration and confirmed readback, then fails preview
preparation: the function catalogue omits the camera capture scope. No capture
start or usable frame was verified. The serial repair updates only native COM
write timeouts, avoiding PySerial's full port reconfiguration. All CephVR2.0
processes have exited and the application guard is free; testing remains unfinished.

The 2026-10-06 G01/A10 increment wires managed GUI role/configuration controls,
connection-only camera checks and MCU pending/final-status handling. The additive
camera diagnostic uses the existing authenticated controller → acquisition → camera
worker command path and original deadline; it never starts capture or pulses.
Identity mismatch or failed release cannot succeed; cleanup remains unconfirmed
until release evidence. Local behavioral checks cover these paths with hardware
boundaries replaced. Manual commands now carry complete accepted settings/revision;
stale/conflicting-owned changes are rejected before installation. First PFS import
opens the assigned camera, retains actual SDK readback, and GUI completion releases
its editing connection. Lazy serial connection closes the old COM owner before
opening a changed selection. These fix concrete source gaps found in the final
GUI-to-owner trace. Windows SDK/firmware/receiver acceptance remains pending in the
[managed device rig procedure](rig-verification.md#managed-device-gui).
Verification: 390 portable acquisition/controller tests passed, five skipped;
GUI and authenticated RPC evidence is recorded in [runtime](runtime.md#dashboard-frontend-implementation).
Regenerated contracts, scoped Ruff/mypy and backend boundaries pass. Hardware
boundaries were replaced in the new unit tests; these are not physical acceptance.

[ARCH-001](../architecture.md#arch-001) selects this stage;
[ARCH-002](../architecture.md#arch-002) governs module boundaries. The
[acquisition decisions](../docs/architecture/acquisition.md) and their
[contracts](../contracts/acquisition/README.md) own behavior. The previous
[controller/supervisor review](runtime.md) remains separate.

GUI-requested per-pin diagnostics are recorded under
[A11](../docs/architecture/acquisition.md#a11). Fixed trial-state polarity and
projector-flip rising-edge input are accepted. Protocol-v2 host parsing, a bounded
diagnostic serial-owner API and matching [Uno firmware source](../firmware/uno/README.md)
now exist. Controller/acquisition diagnostic RPCs, typed Trial state and
Projector flip pin settings, and GUI status projection are implemented. Focused
tests pass, but the complete managed GUI path and physical pin behavior remain
unverified. See the [frontend report](runtime.md#dashboard-frontend-implementation).

On 2026-10-05 the owner authorized MCU protocol/firmware work for the COM8 Arduino
Uno before camera pin testing. Initial read-only COM enumeration identified that
board; an isolated CephVR2 `CAPS`/`STATUS` probe missed its deadline, while a
legacy read-only PING yielded `OK READY dual_camera_projector_sync`, matching
the CephVR1.0 sketch. Its diagnostic process exited, releasing the port.
The owner then authorized a manual upload. The exact old flash readback and
verified new image are in [dated rig evidence](mcu-evidence-2026-10-05/README.md).
The new firmware returned matched protocol-v2 CAPS/STATUS through the real
SerialOwner on COM8 with both camera outputs stopped and no malformed replies.
No pin was driven by a test; managed GUI and physical I/O diagnostics remain open
in TODO. The new command path uses the controller's Configuration phase and
operator authority, an exact configuration revision, and the existing acquisition
serial owner. The backend reports exact device status through the controller. The
COM8 and the owner-assigned D9 Trial state, D2 Projector flip, D10 behavioral
camera and D11 tracking camera pins are saved as defaults. Destination channels
and electrical compatibility remain unverified.

The firmware source compiles with Arduino AVR core 1.8.8 for Uno (10,920 flash
bytes, 1,112 global SRAM bytes). It advertises D2–D13 and interrupt-capable
input pins D2/D3, uses Timer1 for bounded camera output diagnostics, counts flip
edges through external interrupts, and forces tested outputs LOW at the two-second
limit. Generated protocol sources were refreshed from the owning proto. Focused
MCU/configuration tests pass 28/28; Windows-target mypy passes 9 source files,
Ruff and boundary checks pass with zero boundary violations. The owner module's
585 lines were reviewed: command scheduling, wire calls and evidence projection
remain together around its single serial state; further GUI/controller code should
not be added there. Compilation, fake-port tests and the successful COM8 handshake
do not prove physical voltage, edge capture or managed host command routing. No
output command or pin test has been performed. The Windows serial adapter now uses
fixed 10 ms native polls and bounded chunk reads: changing two pySerial timeout
properties on this rig consumed roughly 63 ms per request, leaving too little
of A11's 100 ms acknowledgement budget. The corrected owner completed the
read-only handshake; original deadlines still govern success.

The focused acquisition/controller/client MCU suites pass (52 cases), and the
six focused offscreen MCU GUI tests pass. A combined GUI suite still crashes in
Qt fixture teardown on this Windows rig; it does not establish a managed launch
pass. The controller/acquisition command path and saved-pin update were not
exercised through a full live GUI session. Trial state output level, Projector
flip edge capture, camera outputs, and preview are unverified.

After the owner supplied the four pin numbers, the default loader bound and
validated the distinct `D9`/`D2`/`D10`/`D11` tokens. A direct live COM8 input
diagnostic on D2 returned active then inactive after the two-second firmware
limit, with zero rising edges. This verifies the bounded input command, not a
projector flip event or the physical voltage. The owner confirmed the projector
was off, so zero edges were expected in that window. The Trial state and camera
outputs were not driven; downstream voltage tolerance remains to be confirmed.

A later 2026-10-05 local review worker test on the same COM8 firmware confirmed
CAPS/STATUS with outputs stopped, followed by D2 diagnostic active at zero edges
and inactive after the firmware limit with 120 rising edges. The source of those
transitions was not independently observed. GUI pin requests now reach the A11
serial owner; output channels D9/D10/D11 still have no physical test evidence.

## Ownership and review

Final Windows repair snapshot (2026-10-01, baseline HEAD
`826984255e0a8469afccbda2dcaf8c642b528b33` plus uncommitted repairs): acquisition
171 passed. All owning ring cases pass with a documented MSVC intrinsic helper
under SYS-003, including native cross-process atomic visibility. Prepared Python
launches preserve exact executing identity; Windows recording paths are tested
with actual absolute temporary paths. The platform wheel includes both native DLLs.
Read-only Basler enumeration sees expected serials/models; no capture/settings changed.
The initial FFmpeg/ffprobe 4.3.2 three-frame 128x128 encode on RTX 2080 Ti failed
at preset configuration. Encoder item 5 is explicitly owner-deferred and unchanged.
[Dated evidence](rig-audit-2026-10-01/README.md) retains initial/final outcomes;
camera, input-format and full-load acceptance remain in the
[single rig worklist](rig-verification.md).

Review covered coordinator/camera/recording/serial ownership, focused peer interfaces,
authenticated bounded admission and original deadlines. Integration closed private
handoffs for applied MCU rates, exact tracking-consumer cleanup and future output
function scopes. [Worker control](../contracts/acquisition/worker-control.md),
[Setup preparation](../contracts/acquisition/setup-preparation.md) and shared E06/E08
contracts own those bindings; public output formats were not changed by that review.

Admission review checked that ordinary and safety reservations charge retained
commands/evidence in one budget, including terminal results and session cleanup proof.
Lifecycle review checked controller-owned completion barriers and exact producer,
consumer and output closure; source review does not establish delivery or durability.

The simplification pass removes the camera wait gate's never-initialized alternate
control-wait branch and separates trial-report delivery/retention from lifecycle
aggregation. Idle control still waits on the native event; active capture retains
joint SDK waits, control priority and deadline rounding under
[A02/A10](../docs/architecture/acquisition.md#a02). No package, schema, public RPC,
configuration or policy change is needed. Existing shared FFmpeg/bootstrap extraction
and Visual Stimulus naming changes were preserved.

Three concrete runtime defects were corrected alongside the refactor: pulse outcome
validation and shared bootstrap wait validation called `HasField` on protobuf scalars
without presence; Finished delivery compared session work directly with trial work.
Validation now uses the existing UNSPECIFIED/positive-value rules and matches the
current trial, its containing session and exact report work. These are behavior fixes
under [A11](../docs/architecture/acquisition.md#a11) and
[E05/E08](../docs/architecture/system-contracts.md#e08), not equivalence claims.

### Cohesion review

The camera adapter remains the single SDK-facing owner and delegates settings,
features, ROI, transport, metadata, grabs and joint waits. Its size reflects the
required adapter interface rather than combined backend or transport ownership.
The capture-resource owner keeps attachment, reset, seal and release together because
they operate on the same native lifetime; layouts, ring operations and accounting
live in separate modules. The worker executor and RPC service are dispatch and
admission boundaries, with trial stopping, recording completion, preview, health
and reporting extracted into independently constructible components.

The recording session retains one sequencing owner for input, frame-log ordering,
watchdog and durable completion. Frame preparation, process launch, input pumping,
negotiation, synchronization and completion predicates are separate modules. These
are cohesive size exceptions reviewed by responsibility; a line-count threshold
alone neither requires extraction nor exempts later unrelated additions.

The MCU owner sequences one physical serial connection; protocol parsing, byte I/O,
scheduling and async handoff are separate. Trial lifecycle aggregation keeps the
Started/Stopped/Finished evidence join; validation predicates and controller delivery
are separate. `trial_lifecycle.py` is now 494 lines, down from 574.
`trial_delivery.py` receives the session slot, workers, controller port, command ledger
and clock; attempt counts and pending/accepted reports remain on the authoritative
trial record. Output evidence is retained before delivery, with the same three-attempt
limit and original deadline. Acquisition `runtime.py` contains dependency assembly and
thin public delegates; shutdown and authority-loss workflows are extracted. Typed
coordinator records live under `coordinator/state/`; `state.py` is their public export.
These are deliberate cohesive exceptions to size warnings, not permission to add
unrelated responsibilities.

The remaining size warnings concern those unchanged SDK, serial, recording,
capture-resource, dispatch and assembly owners; their existing responsibility-based
exceptions remain bounded as described above. Tests extend the existing behavior
modules, with no new test module. The trial-lifecycle module retains its common exact
worker/session fixtures for aggregation and delivery tests. Portable camera tests
replace only native event allocation; the five Win32 ring cases retain their skips.

The 2026-10-01 cross-backend ARCH-002 audit rechecked the acquisition package layout,
camera/worker/coordinator/recording ownership and the reported size-warning owners.
It found no additional safe shared extraction: camera waits and serial ownership keep
their A02/A10/A11 semantics, while the already-shared pixel and FFmpeg mechanisms
remain in `shared/`. No acquisition code or public interface changed in this audit.

## Dependencies and prerequisites

The `acquisition` extra pins pypylon 26.3.1, NumPy 2.4.4 and pySerial 3.5 from the
rig inventory. These are implementation pins, not a validated deployment lock.
Hardware imports remain lazy. FFmpeg and ffprobe remain externally installed and
resolved through PATH; no tested production FFmpeg baseline is asserted.

Basler API assumptions must be checked against the pinned binding. Missing joint
camera/control wait or GIL support blocks capture preparation under
[capture-wait.md](../contracts/acquisition/capture-wait.md). No polling substitute
or automatic dependency upgrade is permitted. The
[upstream releases](https://github.com/basler/pypylon/releases) document API changes;
they do not establish this rig's compatibility.

Source inspection used the public Windows wheel
`pypylon-26.3.1-cp39-abi3-win_amd64.whl` without installing or executing it. Its
Python wrapper exposes `WaitObjects.WaitForAny`, `WaitObject` handle construction
and `PylonImage.AttachMemoryView`. The matching
[26.03.1 build source](https://github.com/basler/pypylon/blob/26.03.1/setup.py)
enables SWIG thread support. The
[converter typemap](https://github.com/basler/pypylon/blob/26.03.1/src/pylon/pylon.i)
allocates the SDK conversion result internally; the C++ destination overload is
not a Python caller-supplied destination interface. These findings correct draft
binding assumptions; Windows wait results, cancellation and actual conversion
remain unexecuted rig checks.

The joint wait uses the pinned binding's no-index `WaitForAny(timeout)` call and
the existing control-event predicate. This avoids an undocumented Python-to-SWIG
output-pointer conversion while retaining command priority under the
[capture-wait contract](../contracts/acquisition/capture-wait.md).

Basler's [acquisition-stop documentation](https://docs.baslerweb.com/acquisition-start-stop-and-abort)
distinguishes ending acquisition from finishing image readout. Its
[stream-grabber guide](https://docs.baslerweb.com/pylonapi/c/programmingguide)
distinguishes queued buffers from retrieved results. The accepted cutoff/drain
contract therefore requires the prepared delivery bound and terminal stop evidence;
an empty result queue alone cannot establish complete post-cutoff accounting.

The narrow native NVENC capability binding is checked against
[nv-codec-headers n12.2.72.0](https://github.com/FFmpeg/nv-codec-headers/blob/n12.2.72.0/include/ffnvcodec/nvEncodeAPI.h).
Header layout inspection does not prove installed-driver compatibility. Actual
codec, format and dimension support must come from the adopted encoding device,
alongside the installed FFmpeg build's advertised capabilities.

The 2026-09-30 source audit corrected the following implementation findings:

| Finding | Change and governing rule |
| --- | --- |
| Shipped acquisition configuration had unsupported empty `basler` and `recording.tools` sections, causing strict loading to reject it | Removed those obsolete sections. TOML comparison confirms every setting and policy version is unchanged; static comparison now matches the owning allowlist. Existing loader regressions remain prepared for the rig. [E07/E14](../docs/architecture/system-contracts.md#e14) |
| Native NVENC maximum dimensions were collected but never consumed by encoding validation | Require positive device limits for the exact codec/pixel format and check the resolved post-filter width and height before preparation succeeds. Explicit scaling is evaluated; no automatic resize or fallback. [A08](../docs/architecture/acquisition.md#a08) |
| Full FFmpeg help could add another encoder's private option values/ranges, including forced-IDR support | Parse selected-encoder help separately; take only the supported common fields from the `AVCodecContext` section. This follows FFmpeg's [generic/private AVOption distinction](https://ffmpeg.org/ffmpeg.html#AVOptions). [A08](../docs/architecture/acquisition.md#a08) |
| Invalid lookahead text escaped as raw `ValueError`; very large bitrate text could become infinity | Validate individual options before device comparisons, reject nonfinite rates and translate oversized integer conversion failures into `EncodingOptionsError`. Source-layout errors use the same public validation boundary. [A08](../docs/architecture/acquisition.md#a08) |
| GPU discovery lacked a platform guard and malformed UUID/missing driver exports escaped its declared error boundary | Normalize these to `WindowsLaunchError`, retaining exact UUID selection and required RTX 2080 Ti placement. Python documents [Windows DLL loading and missing-symbol failures](https://docs.python.org/3.11/library/ctypes.html#loading-shared-libraries); no driver fallback was added. [SYS-002](../architecture.md#sys-002) |

The same review shortened argument validation into named stages, consolidated
camera/admission predicates, removed four unreferenced protocols and a resource-key
helper, and merged the request accessor into worker ports. No dependency was added.
Static results are retained in [runtime.md](runtime.md#verification-evidence);
these corrections do not establish native or hardware behavior.

Native pipe review uses Microsoft's
[ConnectNamedPipe requirements](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-connectnamedpipe):
an overlapped pipe requires a valid `OVERLAPPED` structure. Cancellation and cleanup
must retain that structure, its event and buffers until completion is observed.

pySerial cancellation is a request to interrupt I/O, not proof that firmware applied
a command or that transmitted bytes stopped. Matched replies, observed completion
and original deadlines remain necessary; see the
[pySerial cancellation API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.cancel_write).

FFmpeg's [stream discovery API](https://www.ffmpeg.org/doxygen/7.1/group__lavf__decoding.html)
reads input packets to establish stream information. The live negotiation review
therefore checks for a potential circular wait if the writer stops feeding after its
first frame while waiting for output initialization. Negotiation must remain bounded
by existing startup/recording deadlines; successful nonempty closure requires matching
input/output facts. This is a source-based review constraint, not a measured startup
latency or a validated installed FFmpeg behavior.

Unknown trigger pins/lines, firmware capabilities, final camera settings and deferred
rig timing stay unset. Firmware implementation/flashing remains outside the authorized scope;
[ARCH-001](../architecture.md#arch-001) owns other backend implementation stages.

## Verification record

The earlier rows below were recorded on 2026-09-30 against an uncommitted working
tree without an exact source revision or full transcript; report consolidation did
not rerun them. The new simplification rows use HEAD
`7ae3767cea92bf7af94153d417e40df997e1fd05` plus pre-existing and new uncommitted changes.
[Raw simplification evidence](acquisition-evidence-2026-09-30/simplification.txt)
records commands, baseline failures, outcomes and source/test SHA256 hashes; HEAD
alone does not identify that snapshot.

| Local check | Result |
| --- | --- |
| Ruff lint / format | Passed; 412 Python files formatted |
| Strict Windows-target mypy | Passed; 370 runtime/test files in the selected scope |
| Compilation | Passed for source, tests, tools and contracts |
| Dependency boundaries | Passed; 268 backend modules, zero violations; cohesive size exceptions reviewed |
| Protobuf / contract syntax | 18 sources generated; 17 TOMLs parsed; all 12 frame-log field groups matched |
| Hardware-free imports | Six provider/entry modules imported without NumPy, pypylon or pySerial |
| Build / package contents | Wheel and sdist built; all 375 packaged Python/stub files match source bytes |
| Earlier behavioral / native / hardware execution | Not executed in that historical static-only review |
| Simplification baseline: `pytest tests/acquisition -q -m 'not windows and not rig'` | 121 passed, 17 failed, five Win32 ring skips. Fifteen failures came from stale fixtures or uncontrolled Windows event allocation; two exposed the invalid protobuf-presence checks. |
| Fixture/presence corrections, then delivery regressions | 149 passed/five skipped, then 165 passed/five skipped; the final aggregation regression brings acquisition coverage to 166 passing cases. No scenario or platform marker was removed. |
| Final integration: acquisition/controller/supervisor/shared/launcher/client, excluding listener tests | 540 passed, five Win32 ring skips. Two authenticated controller RPC tests passed separately with loopback permission: 542 passing cases combined. |
| Current scoped Ruff lint/format and Windows-target mypy | Passed: 204 source/test files formatted; 181 acquisition/shared-bootstrap sources typed, then 204 files including all acquisition tests. Two test-only typing corrections passed the affected 30 cases; refreshed hashes are retained. |
| Current boundary checker and source comparison | 406 backend modules, zero violations. Moved delivery body matches the original AST after normalizing the two intentional scope checks, method name and type assertion; lock, retry, retention and await order remain unchanged. Source/test manifest stayed unchanged through checks. |

Fixture repairs restored the intended scenarios: exact worker UUIDs and startup health
values, serial-owner factory injection, complete fake-clock/ACK budgets, correct method
binding, replay before transport closure, and a started preview with an exact child
operation and explicit viewer-release synchronization. The preview failure found in
the controller pass is resolved. New cases cover missing/nonpositive bootstrap waits,
unspecified pulse outcomes, idle/joint waits, rejected/failed delivery, exhausted retries,
stale work, retained output evidence, finalization and duplicate Finished aggregation.
These local checks do not establish SDK/GIL behavior, ring atomics, device timing or
rig equivalence.

Mypy covered runtime sources, all acquisition tests and the touched integration
fixtures/regressions. An exploratory whole-test-tree check also exposed historical
typing errors in unchanged controller/shared/platform tests; this record does not
claim that the entire historical test tree passes strict mypy. The rig runner's
mandatory mypy step targets runtime sources.

Transfer artifacts recorded at that time: `dist/cephvr-acquisition-20260930.zip`
and its `.sha256`; contents included source, tests, wheel/sdist and static logs in
`verification/`. Their availability/currentness has not been revalidated here.

The supervising review accepted the host implementation for rig verification after
correcting partial-launch ownership, evidence admission before mutation, original
deadline retention, concurrent safety fan-out, encoder negotiation/closure and
manual-preview retirement. Components use explicit state records, ports and callbacks;
feature modules do not hold the coordinator runtime.

## Remaining work and references

Continue native/device/full-workload verification under current E15; the scoped local
passes above do not close rig acceptance. Native
wait/GIL support, conversion precision, firmware/electrical behavior, full-load encoding
and crash durability remain in the [single rig worklist](rig-verification.md).

Background references from the retired design review:
[Stytra](https://pmc.ncbi.nlm.nih.gov/articles/PMC6472806/),
[Basler feature persistence](https://docs.baslerweb.com/knowledge/saving-camera-features-or-user-sets-as-a-file-on-hard-disk),
[pylon persistence API](https://docs.baslerweb.com/pylonapi/cpp/class_pylon_1_1_c_feature_persistence),
[Braid saved-video processing](https://strawlab.github.io/strand-braid/processing-saved-videos.html),
[Unity interpolation](https://docs.unity3d.com/Manual/rigidbody-interpolation.html),
[NVIDIA FFmpeg guide](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/ffmpeg-with-nvidia-gpu/index.html)
and [MP4 muxer source](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/movenc.c).
These references do not govern CephVR behavior or establish rig compatibility.
