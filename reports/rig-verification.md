# Rig verification — outstanding checks

Oct26 bounded lifecycle checks complete: deliberate GPU-budget rejection with the
saved Behavioral camera confirms cleanup and fresh Setup/Cancel; two60-second Visual
Stimulus-only trials, NewSession, post-session calibration Open/Close and normal
Ended-session Shutdown pass. Exact process-absence/rendererexit0 and settings
restoration proofs are retained in [lifecycle evidence](runtime-evidence-2026-10-26/lifecycle-followup/).
This does not close the remaining fault, physical or full-workload checks below.

<a id="dummy-session-no-output"></a>
- [ ] `dummy-session-no-output` [controller] [acquisition] [visual_stimulus] After
  a safe normal restart, disable every active saving selection and check Setup,
  Start, normal completion, Abort and a fresh session: no experiment/session folder,
  lock/marker, metadata, frame logs or videos appear. Verify normal projection,
  Tracking/camera activity where required, truthful cleanup and dummy status.
  Enable one recording and confirm normal outputs return. Runtime safety diagnostics
  remain independent. [Local evidence](runtime.md#no-recording-dummy-session--2026-10-23).
  Oct23 native Setup failed with INVALID_CATALOGUE on an empty revision1 update;
  the focused local fix passes102 coordinator/supervisor tests. Preserve the retained
  failed-session evidence; verify normal cleanup/recovery and corrected Setup after
  loading the fix. No native recovery or successful retry is claimed.

<a id="protocol-category-previews"></a>
- [ ] `protocol-category-previews` [gui] [visual_stimulus] On the rig, verify media
  overlays/layer selection/fades, texture drift/fades and shared-observer arena previews
  with cameras visible. Check Combined's single GPU screen-plane rig view, left-drag
  rotation, elevation limits, double-click home and repeated Per-projector switches,
  enlarged Combined allocation when cameras are hidden, shared colored vectors and
  projector-row parameter table, camera-column restoration, and all four image/plot
  pairs including static Bottom at short/tall window sizes and scaled DPI,
  correct calibrated content/orientation/aspect, physical direction versus planned
  instruments, mixed layers and unavailable tracking. Compare signed rotation on all
  four physical screens, protocol rig preview and Monitor after the Oct23 preview-only
  reflection corrections; the owner confirms existing physical rotation is coherent.
  Check native owner-follow,
  DPI/monitor changes, manual drag/Snap, X-close without polling reopen, clean session
  release and failure recovery. Compare cropped content and folded Bottom orientation
  with the protocol rig view. Measure Combined versus four Per-projector viewers'
  preview cadence and GPU cost under full recording/projection load; local checks do
  not prove native resource behavior, optical timing or throughput.
  [Implementation/evidence](runtime.md#protocol-category-and-preview-design--2026-10-23).

- [ ] `gui-startup-splash` [gui] [launcher] At the next safe normal launch and GUI
  reopen, verify the saved Standard/Retro/Amber splash appears without transient Qt
  windows or a white main window, then hands off to the populated maximized GUI.
  Oct23: transparent native first-paint tests pass for all three themes; the
  foreground native Dashboard probe has zero white frames in1627 captured frames
  and clean Qt teardown. Managed same-generation GUI reopens connect successfully.
  Oct23 later full-role native startup and GUI-only save/close/reopen pass: all
  non-GUI native process identities and controller generation stay unchanged;
  launcher event remains reachable and GUI reconnects in Configuration. Saved
  projectors are undetected, so display readiness is not established. Still check
  alternate monitor/DPI, CRT disabled and controller-unavailable diagnostics.
  No Setup/trial/device actions were performed.
  [Implementation/evidence](runtime.md#startup-splash-preview).

Oct22 current result: the image-read ctypes lifetime defect and helper retirement
proof mismatch are fixed. Final uninstrumented unchanged2×600s playback/recording
completes with confirmed cleanup, all14 outputs closed and six videos fully decoded.
All4000 image/blank occurrences agree; no image mismatch, residency hold or failed
submission. Worst state interval improves105.882→31.9408ms; worst output interval
107.899→38.6401ms and software onset47.1322→21.8091ms. Neither helper warning recurs.
This is software timing/content validation, not strict60Hz or optical/electrical
certification. Exact original configuration/history is restored; app is idle.
483 Visual Stimulus and168 supervisor tests pass; prior899 GUI-node coverage remains.
One pre-Start MCU PING timeout followed by a successful fresh retry and separate idle
shutdown findings remain explicit follow-ups. [Evidence and limits](runtime.md#rig-checks-oct22).

Oct21 current execution: bounded two-camera/stimulus On60s→Off Abort5s→On60s,
Ready cancellation and fresh Setup/cancel after326.259s idle pass;16 outputs close,
six videos decode/count exactly. Off has no camera demand and retains stimulus
scientific files, without camera/encoder processes. Full20min acceptance is blocked:
initial long-path Setup failed WinError206; approved reservation fixes now pass
managed session247/child261 and session280/child294 Ready/cancel with exact
restoration after the approved durable-publication correction. Full recording at
these paths remains unverified.
Shorter-path full-texture Setup reproduces MCU PING114.451ms
against99.979ms and unconfirmed cleanup. Subsequent automatic managed shutdown
and preserving startup recovery confirm old process absence and exact original
configuration/history restoration; failed-session unknown closure remains retained.
Do not repeat full workload or close its
checkbox from dummy evidence. [Current assessment and raw evidence](runtime.md#current-rig-validation--2026-10-21).
Physical pulse/optical, active-camera video-Off, fault/storage matrix and GUI appearance
remain open. Continuous capture is design-only and was not certified.


<a id="pilot-synchronization-verification"></a>
- [ ] Before a future timing-sensitive paired experiment, configure and verify a
  shared periodic SpikeGLX sync wave in both OneBox SY and probe SY, with matched
  edges throughout a saved test and documented rate calibration. SP0003-123824
  has no SY transitions and cannot supply this verification. Check analog
  photodiode gain/range, thresholds, short-pulse rejection, polarity delays and
  optical coverage of each required projector; retain camera trigger/exposure
  semantics. No settings were changed by the read-only inspection. Detailed
  findings and data limits: [pilot assessment](runtime.md#pilot-spikeglx-alignment-inspection--2026-10-21).

- [ ] After restarting with V04rev20/policy19, verify Setup displays per-trial
  decoding/validation and initial GPU-upload counts on one updated console row
  while waiting, and reaches Ready
  only after initial textures finish uploading. Then run the complete unchanged
  primate_cuttlebase_20min protocol with normal camera/review recording. Require
  requested=actual for all four images on every texture render group, including
  each first group after onset and the second-trial transition; inspect submission
  cadence and use optical timing evidence for physical synchronization. Hidden
  four-context loader probes do not close this full-workload check. Keep the
  historical SP0003-145623 mismatches distinct from new results. — [Assessment](visual_stimulus.md#primatecuttlebase-texture-mismatch--2026-10-21)


- [ ] After restart, interrupt a protocol and verify automatic Configuration after
  confirmed cleanup, retained settings and Interrupted output records, then fresh
  Setup/Start with new identities. Unconfirmed cleanup must remain blocked; late
  confirmation should permit automatic reset, while application Shutdown must not.
  Oct21 native10s Abort returns automatically to Configuration in357ms with exact
  Interrupted finalization/settings retained; fresh Setup/Start and recorded60s
  normal stop pass, all outputs close and six videos decode/count correctly.
  Native GUI confirms terminal rows, editable Configuration/Setup and disabled
  Start. Late-confirmation and shutdown/fault branches remain pending. — [Runtime](runtime.md)

- [ ] After GUI restart, toggle Stimulus timeline in Previews with native viewers
  open. Verify automatic followers resize/reposition into the expanded grid and
  restore with the plot, retaining Show/capture state and existing manual opt-out.
  Verify unchanged visible stimulus previews keep a stable frame/window size across
  repeated placement polls with timeline shown and hidden (Oct21 pending-header fix).
  Offscreen reflow, frame identity, preference and plot checks pass22 cases; native
  viewer follow was not exercised. — [Runtime assessment](runtime.md)

- [ ] `dashboard-embedded-previews`: with G01rev294/G02rev112, press Start and check the
  Dashboard switches to Monitor (System controls at row height, HUD, Log, Timeline
  card, stream footprints) and back to Configure after Stop/Ended; switch manually
  both ways mid-session. Check each Video-row checkbox opens/closes its viewer and
  that showing/hiding a stream reflows the remaining frames with each native viewer
  re-placed on its new footprint (untouched windows follow; manually moved ones keep
  their opt-out). Native viewers must follow the main window (move/minimize/restore),
  hide on leaving the Dashboard tab or Monitor, and reappear with capture intact.
  Advanced-row checkboxes hide/show projector sections. Offscreen layout checks only;
  native follow and reflow not exercised. — [Runtime](runtime.md)

- [ ] With G01rev268, open Previews before Setup and during a recorded trial, wide (side-by-side) and narrow (stacked), and check native viewers sit on their frames.
  Confirm in-frame reasons, the VIEW strip (the HUD no longer shows a REC lamp), the dimmed remaining plan, 60 s left-pinned window, cursor and
  hover values; headings stay fixed while viewers open/close. Offscreen renders and
  focused tests only. — [Runtime assessment](runtime.md)

- [ ] Reopen the GUI with G01rev261/G02rev89, finish a session through Stop and verify
  all configuration draft editors unlock only after confirmed cleanup.
  Edit the next subject, use Setup's New session action and verify the draft survives
  into Configuration/fresh Setup while completed-session metadata remains unchanged.
  Offscreen gates/retention pass18 focused cases. Launcher relaunch requires closing
  the existing GUI first; desktop inspection approval timed out, so native acceptance
  remains pending. — [Runtime assessment](runtime.md)
  Also verify failed/cancelled Setup restores editing after returning to Configuration,
  repeated stimulus Show/Hide clears pending immediately on completion/failure,
  and preview HUD/time formatting/centered speed units match the Dashboard.
  Check total planned progress across a gap and interrupted session; it excludes
  preparation/finalization overhead. Latest offscreen checks do not close native acceptance.

- [ ] Verify A01/A07 camera demand and transport warnings on the native rig after
  loading the updated source and the separately managed compatible MCU firmware:
  repeated USB trial stops should omit unsupported-counter warnings; applicable
  SDK read failures must still warn. Save Cam Off with no backend consumer must
  leave that camera's pulses off and create no camera files; active Tracking with
  camera video Off must retain pulses and metadata. Check saved Use choices after
  NewSession, and all-camera-Off Trial state HIGH/normal-stop/Abort LOW. Local
  fixture tests pass; no physical run from the stop-warning chat.
  — [Acquisition assessment](acquisition.md),
  [validation evidence](runtime-evidence-2026-10-20/sdk-transport-counters/verification.json)

- [ ] Complete remaining saving-only E12 fault/scientific acceptance. Oct20 native
  normal60s, Abort12s and Setup cancellation pass: acquisition stays running, saving
  toggles only at Start/end/Abort, Setup does not rename, counts do not reset, and
  actual session-named native files exist. All18 local outputs close/8 videos decode.
  Verify electrical/optical pulse alignment and transfer/inspect native contents;
  exercise name/enable/disable timeouts, externally changed acquisition/recording,
  link loss, per-stream stalls, controller loss and long workload acceptance.
  Historical acquisition-start/stop passes do not substitute for these checks.
  — [Current runtime](runtime.md), [Oct20 evidence](runtime-evidence-2026-10-20/spikeglx-continuous-acquisition/verification.json)


- [ ] Finish actual GUI control/menu/dialog and native DPI/layout acceptance once
  desktop capture works. Oct19 state capture failed twice after prescribed recovery;
  no native inputs were issued.48 offscreen states/7932 repeated control rows and751
  owning GUI tests pass, distinct from physical control coverage. Safe inventory-order,
  preview geometry and sessionless diagnostic fixes pass native diagnostic reuse and
 805 backend tests.600s Gaussian run/output audit is complete; do not repeat solely
  to fill the initial40s telemetry gap. Retain other physical/control checks below.
  — [Current verification](runtime-evidence-2026-10-19/gui-full-rig/verification.json)

- [ ] Establish usable Eye/Tracking scene content with the operator before detailed-image
  throughput/scientific acceptance. Early/mid/late videos and ten direct native frames
  are nearly black before conversion/NVENC. Exact saved exposure/gain/trigger settings
  were preserved; physical cause is unproven. Verify scene, illumination and optics,
  then repeat a representative workload only when appropriate; do not silently change
  scientific settings.600s all-three-camera/4-projector paired output closure passed;
  simultaneous scientific Tracking and physical alignment remain separate.
  — [Acquisition](acquisition.md), [raw statistics](runtime-evidence-2026-10-19/gui-full-rig/native-image-assessment.json)

- [ ] Complete remaining E12 pulse/native-content and fault acceptance after the
  Oct19 bounded paired pass:60s normal plus12s Abort, exact session-folder native
  filenames, saving/increasing counts, remote stop, cleanup and reuse now pass.
  All18 local outputs close and8 videos decode; three-camera/4-projector workload,
  Tracking processing disabled. Verify physical pulses/photodiode sample alignment,
  transfer/inspect original native files under E09, then remaining stalled-stream,
  link-loss/recovery, counter-reset, controller-loss, collision and endurance cases.
  Owner changed the initially-OFF manual recording override; Setup now rejects it.
  Retain full existing session-control matrix below; do not upgrade control
  timestamps or saved-channel validation into electrical/optical timing evidence.
  — [Runtime](runtime.md), [dated verification](runtime-evidence-2026-10-19/spikeglx-pairing/verification.json)


- [ ] After restart and fresh Setup, verify Dashboard Visual stimulus Show/Hide,
  native X/reopen, manual placement/Snap, GUI minimize/reconnect and cleanup across
  multiple trials. Preview must crop calibrated areas into Left–Front–Right with
  Bottom beneath Front; recording must keep full outputs in 2x2 with Bottom rotated
  90 degrees clockwise and no clipping/stretching. Verify both views have no labels
  or header strips, and matching post-rotation recordings meet with no gutters.
  Check both Save On/Off, stored
  calibration/layout metadata, required evidence and concurrent full-workload pacing/
  throughput. Optional viewer failure must not stop trials; failed cleanup remains
  owned. No projector/camera or managed runtime execution was done for this increment.
  — [Visual Stimulus](visual_stimulus.md), [local evidence](runtime-evidence-2026-10-19/stimulus-composite-preview/verification.json)

- [ ] After restart, verify G02 action-only logs through existing camera/MCU,
  Setup/stimulus/tracking, SpikeGLX, recording, stop/Abort, recovery and shutdown
  checks as those operations are authorized. Success advances directly to the next
  action; failures and uncertainty retain details. Verify first-frame Live and
  confirmed-cleanup Idle, quiet polls and prompt safety OFF during a stalled
  progress connection. Do not lift existing scientific/device deferrals for logging.
  — [Runtime](runtime.md), [Local verification](runtime-evidence-2026-10-19/action-progress-logging/verification.json)

- [ ] Restart the managed application and verify Devices/Projectors brightness:
  enter an appropriate LED current, click Adjust, compare all USB interface readbacks
  and physical outputs; verify SDK contention/missing interface and clamped-current
  reporting. Confirm no console appears, exact registered helper cleanup precedes
  Setup reuse, and a subsequent session's SESSION_CONFIG/SCHEMA preserve the observed
  per-interface results, timestamps and uncertainty. A fresh runtime with no Adjust
  must record unknown, without applying a saved draft. Local SDK responses are
  fixtures; benign native process tests do not establish hardware current.
  — [Contract](../contracts/projector-brightness.md), [Runtime](runtime.md)

- [ ] Reopen CephVR and exercise the E04 startup
  prompt on the retained unfinished session: Start recovery preserves scientific
  files and reports unknown closure; Cancel and delete files removes only the
  explicitly displayed local session. Close must preserve the blocker. The real
  session has not been recovered/deleted by source tests. With no prior launcher
  receipt, verify explicit locked actions work without reboot and retain unconfirmed
  process absence; a live lock must block. Verify post-choice Setup
  admission, remote-stop warning retention where applicable and failure/timeout
  behavior; use owned disposable sessions for destructive/fault cases. — [Runtime](runtime.md)

- [ ] Complete remaining repeated Stop/Interrupt, forced Cleanup/control arrival
  during drain and Abort-during-finalization acceptance under A10rev69, preserving
  first cutoff/OFF and original deadlines. Bounded native two-Abort/reuse and60s
  normal all-three-camera recording now pass: complete post-cutoff accounting,
  Closed outputs, cleanup/NewSession and0.36s Abort-to-end. Following normal trial
  exceeds retired end times; no forced race or idle300s/full-workload pass claimed.
  Preserve historical failed outputs without closure upgrades.
  [Current verification](runtime-evidence-2026-10-19/camera-timing-verification/verification.json).

- [ ] Load the corrected retained-state protocol and perform fresh Setup; confirm
  texture positions hold at drift-to-static boundaries and resume smoothly on all
  four outputs over repeated cycles. Local200-epoch state evaluation passes.
  [Correction/evidence](runtime-evidence-2026-10-19/texture-retain-static/verification.json).

- [ ] After completed cleanup and application restart/fresh Setup, verify corrected
  Bottom portrait mapping: head-to-tail, reverse and both lateral directions, retained
  10mm grid/pixel pitch, crop offsets, masks and pulse location. Confirm side/front
  linked movement and physical preview agreement. Oct20 owner confirms dummy-trial
  physical motion with Bottom Y inversion off; confirm the corrected preview after
  GUI restart. Pitch, offsets, masks and tearing remain unverified. Compare pulse-only and all-output
  VSync for Left/Front tearing and record actual cadence/optical behavior; do not infer
  simultaneous scanout from requested intervals. — [Assessment](visual_stimulus.md)

- [ ] Verify the promoted shared Inputs/Outputs and per-screen Synchronization
  editors at native narrow/tall/DPI sizes, including save/reopen and observer/session
  gates. Under [V20/V22](../docs/architecture/visual_stimulus.md#v20), exercise multiple
  active pulse outputs, blank/disabled screens, live placement edits without sequence
  reset, requested/actual swaps, saved per-output marker evidence and optical traces.
  Local [shared-control checks](runtime-evidence-2026-10-19/shared-controls/context.json)
  do not establish native timing or close the A11 physical-input deferral.

Oct19 repairs pass native Configuration concurrent Connect, workspace close/reopen,
independent Show/Hide and Disconnect. Runtime all 3 viewers, workspace close/reopen
and independent Behavior Hide/Show pass in a 120-second trial with confirmed cleanup.
NewSession, subsequent Setup/CancelSetup, Shutdown/process absence and 11-file restoration
pass. Subsequent240-second all-video trial completes with cleanup confirmed at saved
quality/15 slots. Fixed DPI false manual-placement detection: workspace movement100%
and alignment125% pass during recording;150% visually aligns at the terminal boundary.
Eye Snap125% passes in an intermediate run. Native X/individual drag remain blocked by
computer-use targeting, and actual multi-camera minimize/restore, sustained150% and
reverse-DPI runtime acceptance remain open. Tracking processing, multi-trial transitions,
failure injection, full long-root and optical/full-workload acceptance remain open. See [assessment and evidence](runtime.md).

Current Oct17 sync repair passes bounded frame-retention acceptance at unchanged
saved camera CQ23/stimulus CQ18: 120 s Behavior 3598/3598, Tracking 7188/7188,
stimulus 7200/7200, no native counter gaps, capacity omissions, duplicate mappings
or padding. Exact normal closure, Cleanup/NewSession and Shutdown/process absence
confirm. Temporary 16 stimulus slots are part of the fixture; saved three-slot
startup behavior is not certified. Full final-source pixel-exact capacity remains
unvalidated; pre-hotpath-guard lossless failures are separate historical evidence.

All three fresh camera PFS/readbacks and ten settings files restore exactly. Full
backend 2209/5privilege skips and explicit NVOF rig pass; GUI was not rerun because
unchanged. Native Abort exact Finished, failed-Setup retired reports, old Shutdown
resource registration and optical/external-trigger/Tracking-processing acceptance
remain outstanding. MCU outputs stay disabled, firmware unchanged. [Current results
and limitations](runtime-evidence-2026-10-17/file-sync-fix/README.md).

Historical comprehensive Oct15 audit supersedes the availability limits of earlier
runs below: owner confirmed an empty rig with cameras and projection available;
reward/actuator/stimulation remain disabled and firmware unchanged. Current COM8
firmware is incompatible with request-ID CAPS, so new trials explicitly acknowledge
unaligned free-running cameras with MCU outputs disabled. Seven managed trials cover
Gaussian/reduced-texture arena, Save On→Off→On, Abort and immediate reuse across
the retired boundary; all18 retained videos fully decode/count. This closes that
bounded reuse regression, not external-trigger/optical acceptance. Abort metadata
settlement still takes40.12seconds. Two fresh native placement views now pass
invalid→valid updates and Close with resourcesclosed. Native GUI selection fixtures
remain blocked;510 native cases pass and the trial-row follow-up passes after
replacing an unsupported height cap with containment checks. One native hover-input
assertion remains unresolved. Tracking processing and physical
calibration remain unverified. [Current runtime scope](runtime.md),
[camera/accounting assessment](acquisition.md), [rendering limits](visual_stimulus.md),
[dated raw evidence](runtime-evidence-2026-10-15/comprehensive-audit/).

Earlier Oct15 endurance evidence (historical, not a new run in this audit):
Sol6.1 completes combined900-final-r1: exact 900 seconds, confirmed cleanup/reuse and
all four strict video counts/full decodes. Astra accepts this low-loss engineering gate;
camera CFR repeats are 0.20–0.45%, stimulus 1.13% with one startup capacity drop.
Earlier failed/owner-interrupted runs retain unknown closure. Bounded prepared-YUV
codec fidelity and a separate 60-second camera-lossless native recording/count/decode
pass; this is neither raw-sensor fidelity nor 15-minute lossless acceptance. Fresh
saved files restore byte-exact; camera feature values match with PFS selector-cursor
serialization differences. That run did not establish immediate post-Abort boundary
crossing; the latest comprehensive paired run above does. Interrupted trial-log
finalization latency remains open.

Earlier Oct15 scope authorized open-loop

Oct16 local reliability fixes do not close the following native checks. Use the
normal managed application with fresh Setup and retain exact source/settings,
commands, reports and output metadata; preserve original stop/recovery bounds.
[Software changes and local evidence](acquisition.md).

- [x] `interrupt-trial-log-closure`: Abort an active all-camera/stimulus recording;
  verify prompt cutoff separately from command-return latency, exact cleanup and
  synchronized Interrupted trial/session logs with truthful output statuses.
  Confirm no unnecessary Finished recovery wait when cleanup is already verified;
  missing/failed evidence must remain visible. Verify NewSession after safe cleanup.
  Oct19 A10rev69 native two-Abort/reuse cycles pass at0.36s with exact Closed
  statuses and complete camera accounting; see current verification above.
- [ ] `rapid-abort-setup-heartbeat`: immediately perform NewSession, fresh Setup and
  Start in the same application generation; record beyond the retired trial's
  original end. Retain heartbeats/pulse identities and confirm no old worker,
  deadline or pulse task mutates the new trial; include Abort during finalization.
- [ ] `camera-preview-sdk-discard-reuse`: repeat more than five Behavior/Tracking
  preview Start/Stop cycles in one generation, confirming actual device/ring release
  after each Stop and a successful following Start. Capture any incomplete drain
  evidence; failed/unconfirmed Close and pulse-pause paths retaining the device
  must keep their safety guard. Do not force reopen or clear unknown accounting.
  Include independent consumer and exact current-controller terminal-proof delivery
  under E08/A10, lost acknowledgement/reconciliation and stale-generation rejection.
  Oct16 authenticated local handoff tests pass; native handle release remains open.

Current Oct15 scope: owner now confirms projectors/cameras on and requests open-loop
Gaussian linked-screen motion, simple3D arena and all configured camera/stimulus
recordings, CPU/GPU monitoring and a15-minute trial after shorter checks succeed.
Use Desktop/Pedro files; projection areas remain uncalibrated, so engineering results
do not establish physical alignment. Tracking processing is excluded; the configured
Tracking camera remains eligible for recording. Sol6.1 executes tests and Astra reviews
results. Earlier powered-off and leave-GUI-open limits below describe prior runs,
not this newly authorized scope. Completed `combined-recording-loss` is recorded in LOG;
remaining optical/scientific acceptance and interrupted-finalization checks stay open.

Oct15 synthetic encoder portion of the listed matrix completes31/31 cases with
external counts/full decodes; direct zero-input finalization also succeeds. Full-path
capture/drop, scientific quality and projector readback acceptance remain open.
Live-camera Tracking diagnostics are owner-deferred Oct15: leave the separately opened GUI running and finish current checks only.
[Workload/results](visual_stimulus.md), [empty-output scope](acquisition.md),
[raw evidence](runtime-evidence-2026-10-15/projector-free-rig/context.json).

Oct15 owner explicitly authorizes available native/device checks on this rig with
projectors off. Completed portions:25 native/rig tests with one privilege skip,22 native
picker tests, five native layout cases,90 contract cases, schema consistency and native
package build. One layout assertion fails (326px versus less than320px); broad native GUI
run was interrupted and is not a pass. COM8 protocol4 Connect and four preview cycles
per enabled Behavior/Tracking camera pass. A later Behavior restart is blocked by unknown
SDK-buffer discard accounting. Exact idle-controller containment/all-owned-absent receipt
passes; active capture-loss remains unexecuted and MCU release remains unconfirmed.
Saved configuration and baseline full camera PFS restore exactly after that generation.
SpikeGLX read-only check times out. [Dated commands, raw results and limits](runtime-evidence-2026-10-15/projector-free-rig/context.json). These partial results do not close remaining
full-session, scientific, electrical, alternate-DPI or projector-dependent acceptance.

Oct15 owner confirms projectors are powered off: defer all powered-projector,
combined-session, optical, presentation-timing and projector fault/throughput tests.
Offline/local checks may continue and never close rig acceptance. Oct14 combined
three-camera and SaveOff recordings counted/full-decoded with queue17 measured;
owner-selected queue20/SDK15/drain150 remain saved but not remeasured. Required
scientific-evidence/video On→Off→On reuse after the later integration, full
CancelSetup/Abort/idle300s reuse and lifecycle receipt margins remain open.
[Current TODO audit](runtime-evidence-2026-10-15/todo-projectors-off/context.json),
[configuration assessment](runtime-evidence-2026-10-14/rig-timing-audit/configuration-assessment.json).

Owner defers Projector flip input/diagnostics and camera-trigger phase offsets on
Oct14 under A11 revision46. Do not run former passive input checks; retained D2
results below are historical evidence. Current firmware/host support output tests
only. No upload or physical input acceptance is required for this deferred feature.

V20 revision9 adds Free run (no VSync) alongside selected-output/all-output VSync.
Verify all three modes' requested/effective driver swap behavior and optical timing
on the rig, including retained pulse/pacer targets in Free run and no MCU input.
Local tests do not establish flicker suppression or simultaneous scanout.

- [ ] Extend SYS-002's verified AMD GUI/RTX5060Ti renderer startup to repeated
  launcher generations and the existing simultaneous OF/camera/stimulus recording
  workload, retaining actual adapter UUID evidence. Oct14 distinct verified images,
  two hidden-context pairs and four-output Idle pass; throughput/optical/scientific
  acceptance remains separate. [Current assessment](visual_stimulus.md).

- [ ] Verify G01 offline projector drafts on the rig: with outputs off, save/close/
  reopen retains assignments and calibration; clicking Setup logs no-projector reason
  without a configuration/Setup request. Power on and refresh, then continue existing
  projector preparation checks. Local23-case behavior/parity coverage passes;
  physical disconnected acceptance is not claimed. [Current assessment](runtime.md).

Oct13 final combined repair verifies two consecutive normal60s Behavior/Tracking
recordings at60.0333/60.0167 actual render groups/s. Renderer RTX5060Ti/GPU0 and
camera/review NVENC RTX2080Ti/GPU1 are proven with exact live PID/UUID samples;
all six videos externally count and fully decode. Trial/output/metadata closure,
two NewSession/config restores, original settings and released cameras pass in one
generation, without shutdown. Owner-selected125ms drain margins remain all roles.
This closes the reproduced warning/boundary/On-to-On receipt-reuse failures within
this scope. Nominal cadence is not uniform16.67ms or optical proof (repeat p9927.56ms,
max37.88ms). Repeat camera queues drop6/19 and review has2367 capacity drops/
2424 identified duplicates: zero-loss recording remains open. Eye/locomotion
Tracking/paired/optical/electrical acceptance and dedicated Save On-to-Off native
verification remain outstanding.
[Dated raw evidence, verification and limits](runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)

Oct13 later throughput repair achieves60.0 real render groups/s in a recorded
four-output60s stimulus-only test, after a30.13/s instrumented baseline. Float-to-byte
readback submission falls from12.98ms to0.736ms; final outputs/video/evidence/metadata
close and external decode passes. Review padding/omissions remain explicit and the
same-shader byte comparison differs by at most one8-bit code. Final uninstrumented
confirmation also completes3600groups/60s (60.0/s),3423 real captures/177 duplicates,
eight capture drops and169 same-slot omissions, with normal cleanup/restored settings;
optical and simultaneous camera/Tracking workload acceptance
remain open. Save On→Save Off exposes a pre-change cleanup/catalogue failure despite
the complete60s Save-Off presentation; retain that separate reuse check. See the
[current stimulus assessment](visual_stimulus.md) and
[throughput evidence](runtime-evidence-2026-10-13/throughput/).

Historical Oct13 workflow audit (before the combined repair above) supersedes the earlier basic camera
preview failure within its bounded scope: both enabled cameras connect, show usable
preview and stop/release. Eye remains disabled. Normal calibration bundle pacing
validation fails, while a separate current-profile grid lifecycle passes. Combined
recording is blocked by unset camera drain margins; failed-Setup cleanup additionally
exits the renderer on an unknown cleanup command. A separate unpaired stimulus-only
60s trial completes, video fully decodes and outputs close, with30.33 real render
groups/s and 60fps video padding. Exact final application absence and configuration
restoration pass. See the [current failure/remedy inventory](runtime.md) and
[new raw evidence](rig-evidence-2026-10-13/workflow-tests/); previous results below
retain their historical scopes.

- [ ] Complete frame/grid live-adjustment and measured optical calibration acceptance.
  Oct14 native reference-bar GUI Open/four visible outputs/Close/reopen passes after
  framebuffer-copy repair; this does not establish measured optics or frame/grid
  update acceptance. — [Current evidence](runtime-evidence-2026-10-14/reference-bars/context.json)
- [ ] Extend A10 drain/full-load verification to Eye when enabled and remaining
  scientific workloads. Owner125ms values/Behavior and Tracking bounded observations
  plus combined online closure now pass; worst-case/full scientific bound unproven.
- [ ] Repeat failed Setup after prior closed calibration, cancellation and supervisor
  cleanup using the local recovery/report-routing repair. Confirm no unknown-command
  renderer failure, exact resource evidence and permitted subsequent reuse under
  E06/E08. Local threaded regressions are not the historical native workflow.
  Missing SESSION_CONFIG cannot prove unpaired status; preserve the conservative
  unknown-SpikeGLX recovery warning unless exact durable evidence becomes available.
- [ ] Repeat orderly acquisition shutdown after exact controller departure: verify
  no unhandled UNAVAILABLE traceback, truthful unconfirmed release reporting and
  exact all-owned absence. Other RPC errors/live or uninspectable controller cases
  must remain failures; local injected tests now pass.
Oct14 four preview start/stop cycles per camera (12 total) complete in one generation, settings unchanged and all devices released. Electrical/GUI acceptance remains separate. [Evidence](runtime-evidence-2026-10-14/rig-timing-audit/final-preview/measurement-cycles.json).

- [ ] Reduce combined review/camera recording loss while preserving the verified
  nominal60fps presentation, exact omission accounting, original timing and precision.
  Profile capture/transfer/encoding under simultaneous load; final repeated sessions
  already close and reset successfully. Verify uniform/optical timing separately.
Oct14 dedicated Save On to Save Off native60s trial completes in the same generation, confirms cleanup and restores settings. Both camera videos independently count/full-decode; no stimulus output is created. This closes the normal switch check; failed-Setup and Abort cleanup remain separate open checks. [Evidence](runtime-evidence-2026-10-14/rig-timing-audit/save-off/verification.json).
  already close and reset successfully. Repeat with the locally implemented owned-buffer
  handoff and review_scale_factor=2 (2560x2000 becomes1280x1000); retain actual prepared
  recipe/arguments and capture renderer stderr JSON recording_metrics exit summaries
  (verify one summary per recording thread), comparing real-frame drops,
  padding, capture/queue/normalization/pipe timing and slot occupancy. Camera resolution
  and live rendering remain unchanged. Evaluate PBO pooling, threaded readback and
  row-flip/layout changes only after these measurements. Verify uniform/optical timing separately.
- [ ] Repair/retest the observed pre-change Save On→Save Off session-cleanup failure
  (`cleanup returned an unregistered resource`) under exact catalogue ownership;
  the60s presentation completed but its session could not finish cleanly.

Oct13 Eye output source and host are implemented/locally verified for protocol4.
Owner explicitly keeps upload manual: install the updated Uno sketch (or retained
application HEX), then verify CAPS protocol4/cephvr2_uno_3 and all three outputs
stopped before any test. Assign the actual Eye camera, external FrameStart line,
unique output pin and rate explicitly; GUI Add output collects an unset pin.
Verify Eye Test/Stop and watchdog LOW electrically,
three independent camera rates under load, preview/stop/reuse, Eye video/frame-log
identity and exact all-three cleanup. Existing capture/electrical deferrals remain;
compile/local fixtures do not close them. [Current evidence](runtime.md).

Oct13 Trial state pin-12 tests have bounded firmware start/stop evidence through COM8.
The owner clarifies manual GUI triggering; Runtime is reopened ready for that Test
click, with no receiver pass or wiring failure inferred. Other
camera/Eye/electrical deferrals and full-load acceptance remain unchanged. The
[current MCU assessment](runtime.md) retains methods, failed probe usage and limits.

Oct13 Configuration-only abrupt controller-exit check passes: all six retained owned
processes, including the renderer, are absent and the launcher confirms its outer
Job empty within 3.453 s; the application guard is available. This does not close
activated/recording/paired/full-load authority-loss acceptance. See the
[current ownership assessment and exact evidence](runtime.md).

Oct13 current rig verification: static/contracts/schema/package checks pass after
regenerating stale local bindings; isolated backend/native suite passes 1,520 with
five skips. Earlier combined/isolated native GUI runs crash with `0xC0000005` during
chooser-test fixture teardown. The later G01 Qt-widget picker repair passes the original
50-cycle reproducer and 20 final affected native cases; fixture teardown is unchanged.
The broad native GUI stage finishes 401 passed/two hover-test failures, before the last
media-picker refinement. Those failures repeat in isolation without constructing any
file dialogs. Full GUI acceptance remains open; see the [current assessment](runtime.md).
Read-only inventory sees four 60 Hz projectors, both NVIDIA GPUs and idle SpikeGLX
at its saved endpoint. Native V19 startup Idle and V01 grid Open/live sequences 1/2/
Close pass with all-output VSync and confirmed resource closure. The actual Behavior
GUI Connect attempt fails with no usable frame by its deadline; exact shutdown is
confirmed. Offscreen GUI completes with 396 passes/three projector horizontal-range
failures; a desktop drag does not resize the window, so native narrow acceptance is
still open. COM8 Connect confirms protocol 3 and stopped camera outputs. The installed
Initial FFmpeg/ffprobe 4.3.2 lacks `hybrid_fragmented`; the later matched 9.0.2
upgrade resolves tool compatibility and passes short sequential synthetic encodes.
Actual-footage quality/conversion, interrupted files and simultaneous sustained
workload acceptance remain open; see the current FFmpeg assessment in runtime.md.
The owner defers Eye, further camera capture, pulse mappings and electrical measurements
today. A missing-identity configuration-update probe is inconclusive: V19 startup
initialization is not rerun by that command. Exact configuration restoration is
independently confirmed; physical disconnected/reconnected startup remains pending.
Final normal shutdown confirms exact all-owned absence, free guard, exclusive COM8
release and saved history equal to the original adopted configuration. Retain
[raw current evidence](rig-evidence-2026-10-13/); these results do not close optical,
electrical, paired-session or full-load acceptance.

Oct9 camera-role check: real GUI identity tests for 40065509/40747103 pass; third
Basler serial 40278236 is discovered. Eye preview/video admission is pending external
wiring and source/rate under [A11](../docs/architecture/acquisition.md#a11).
Protocol4 now provides the owner-requested independent third output; do not use
an internal clock or assume the update is installed. The owner selects
all-projector VSync without a pacer; local V20/E13 validation now supports it.
Reconnect required outputs and verify native MCU Apply before another dummy run.
Oct11 repairs the V19 startup classification locally; native acceptance remains
pending. Launch with a saved output disconnected (and inject an ambiguous identity):
Configuration must remain available with the output issue and exact release evidence,
without session Ready. Reconnect/correct the assignment, then verify fresh Setup and
Idle on all outputs. GPU/context failures and uncertain cleanup must still fail
through the existing safety path. Verify GUI and headless issue visibility. No native
Apply/experiment is verified by the local repair. [Latest evidence](review-evidence-2026-10-09/mcu-configurable-context.json).
The owner's earlier
firmware request passes native `.ino` selection, GUI compile/verified upload and
connection retest on COM8: protocol 3, `cephvr2_uno_2`, both camera outputs stopped.
This resolves the observed legacy-firmware incompatibility; electrical/timing and
interrupted-upload acceptance remain pending.
Then verify accepted Eye assignment, exact identity, triggered preview/stop/reuse,
recorded Eye video/frame-log pair and all-three cleanup/output closure, preserving
Behavior/Tracking settings and disabled velocity recording.
[Current diagnosis and local/native limits](acquisition.md),
[raw camera checks](review-evidence-2026-10-09/eye-camera-context.json),
[firmware repair checks](review-evidence-2026-10-09/firmware-picker-context.json).

Latest retained dummy-experiment evidence is run43 (Oct8), reconciled on Oct9:
unpaired 60 s trial/session, seven closed outputs, synced metadata, unlocked reservation,
external counts/full CPU decode and normal exact shutdown pass in the retained records.
Camera rates recover to 29.95/59.93 fps after the external-trigger limiter correction;
stimulus recording remains 19.7 fps with four capacity drops and a compressed 19.7 s
MP4. Recheck presentation/recording throughput and later padding under the intended
configuration and full workload; the completed unpaired trial does not establish either.
Pending rig test — stimulus ~20 fps diagnosis (owner requested Oct11):

- [ ] Extract each output's swap entry/return durations from the retained run43
  evidence log, if available. Compare summed swap time per group against the
  49.29 ms median group interval. Four requested interval-1 outputs make accumulated
  sequential VSync waits a hypothesis; requested intervals alone do not prove it.
- [ ] Run the same stimulus with recording enabled and disabled, preserving all four
  outputs, accepted all-output VSync, resolution, precision, GPU placement and other
  workload settings. Record actual GPU identity and requested swap intervals.
- [ ] Measure state/draw, context switching, each swap, composite/capture enqueue and
  completed GPU readback/CPU copy separately. Retain per-stage timing distributions,
  real render groups/s, capture admissions/drops and encoder submission counts.
- [ ] Recheck sequential decoded-frame count and exact source timestamp mappings
  separately from actual rendering rate; nominal playback duration need not match
  the trial. Compare historical padded recordings using their original schema. Save command, source revision, configuration
  and raw evidence; use results to identify the bottleneck before choosing a fix.

[Snapshot/source findings](runtime-evidence-2026-10-11/throughput-source-trace.json)
and [run43 arithmetic](review-evidence-2026-10-09/nongui-throughput-assessment.json)
do not establish causality or authorize changing pacing or the deferred encoder/toolchain.
Measured drain bounds, SpikeGLX pairing, Tracking velocities, optical/electrical
correlation, native narrow/DPI and scientific/full-load acceptance remain open.
Oct9 restores accepted source defaults; all 36 owning configuration checks pass.
[Current local implementation validation](review-evidence-2026-10-09/implementation-context.json)
does not establish native acceptance or measured drain/throughput guarantees. [Current assessment](runtime.md#current-scope-and-review),
[dated raw checks](rig-wiring-evidence-2026-10-08/dummy-experiment/).

Latest execution: [2026-10-08 changes and Windows/device checks](rig-wiring-evidence-2026-10-08/README.md),
baseline `7ba43b1` plus focused controller/native, camera-selection and Tracking
preview-evidence repairs. Controller-owned
MCU diagnostics with acquisition disabled, verified HEX upload and selected `.ino`
compile/upload, compile-error preservation, active-D9 control release, real Behavior
Connect/display/Disconnect and moved-GUI placement pass. D9/D10/D11 final counts
are 1/13/25; isolated watchdog readback shows both outputs stopped after 3.43 seconds
without keepalive. Counts and stopped state do not establish electrical timing/LOW
or receiver correlation. D2 reports zero edges without an established projector source.
Final runtime shutdown confirms exact all-owned absence, free application guard and
closed COM; capture is stopped. Raw evidence and emergency/recovery records are retained.

Later owner `.ino` crash reproduces JOB_INSPECTION_FAILED during compiler job
inspection. Exact exit-signal checking and required launch-owner termination rights
are repaired. Two final compile/verified-upload cycles and serial-preserving compiler
rejection pass; affected tests pass 199 with one skip. Exact final exit, guard/COM/
tool release and archived failed-attempt staging cleanup are confirmed.
[Latest method/source scope](rig-wiring-evidence-2026-10-08/README.md#ino-upload-native-job-correction).
This does not close interrupted-flash, full-load or electrical acceptance below.

Earlier full Windows/offscreen suite: 1463 pass, eight existing GUI clipping failures,
five privilege skips, one rig deselection; separate GPU smoke passes. Later Tracking
Ready/release repair passes two physical Connect/Show/Disconnect cycles with
BehaviorSquid and six seconds of capture each. Acquisition/affected-controller checks
pass 363 with one skip; original settings and exact normal shutdown are confirmed.
Ordered Tracking diagnostics and scientific acceptance remain open. SpikeGLX remains
unreachable. Only the
operator display is active; saved projector profile/assignments remain unset.
The remaining electrical, native UI/DPI, projector, scientific and deferred encoder/
full-workload checks below remain open. Earlier evidence below retains its dated scope.

Preview edge placement repair follows [G01 revision 123](../docs/architecture/gui.md#g01):
fit the square into available right-hand space and align visible physical frames.
[Current bounds and isolated validation](rig-wiring-evidence-2026-10-07/preview-snap-context.json)
retain six GUI/one native pre-repair failures, ten GUI/549 integration passes (two
privilege skips) and four final native/reader passes. Fully restart both GUI and
acquisition, then verify actual camera opening outside the GUI's top-right edge,
reopening after moving the GUI, and alternate-monitor/DPI/fallback behavior.
Actual Behavior opening and moved-GUI reopening now pass in the Oct8 evidence;
Tracking Start/Show/Stop also passes twice; mixed-DPI/fallback and actual
selector/button interaction remain unverified.

Current MCU implementation: [counted diagnostics](rig-wiring-evidence-2026-10-07/mcu-counted-diagnostics.md)
uses protocol 3 / `cephvr2_uno_2` under A11 revision 37. Build and local host/GUI
checks pass. The [owner-authorized manual installation](rig-wiring-evidence-2026-10-07/mcu-installation-and-preview.md)
now passes exact shutdown/flash backup/upload verification/CAPS, D9's one rise,
increasing D10/D11 counts, retained Stop counts and matched OFF/stopped firmware state.
Managed D9/D10/D11 Test/Status/Stop and D9 automatic timeout pass. Verify physical LOW/receiver
correlation; generated counts do not prove SpikeGLX reception or electrical timing.

The earlier D10 owner test reports no pulses. The
[configure-before-start and error-report repair](rig-wiring-evidence-2026-10-07/mcu-camera-diagnostic-repair.md)
passes seven targeted and 526 affected-owner cases (two privilege skips), including
protocol-3 controller completion. The subsequent installed-board managed D10/D11
Test/Status/Stop passes; physical pulse/receiver observation remains open.

Current camera display: [A10/G01 backend-owned OpenCV evidence](acquisition.md#current-windows-wiring-checks)
passes 526 affected-owner/client checks (two privilege skips), 17 GUI/bridge checks
and 64 final focused owner checks, including two real Win32 windows with native X
closure and independent active producers. Actual Behavior Start/Show/X/Hide/reopen/
Stop now passes after matching firmware installation/restart, with acquisition PID
owning the native window. Tracking preparation and two real Start/Show/Stop cycles
now pass after correcting exact two-ring readiness and release proof. Verify ordered
Tracking diagnostics and remaining GUI clicks/selector visibility; the bounded
preview checks do not close scientific or full-workload acceptance.

Earlier execution: [2026-10-07 GUI wiring rig checks](rig-wiring-evidence-2026-10-07/README.md),
HEAD `08d146d0d97847cb3f395144886fc175dc627487` plus generated-SWIG mypy exclusion.
Windows offscreen suite: 1,252 passed, nine GUI failures, four symlink-privilege
skips, one rig deselection; native Qt teardown also crashes in a separate run.
Static/contracts/schema/build checks and the separate GPU rig smoke pass.
Managed startup, automatic control, exact GUI-loss/reopen, interactive N/Y
replacement and authenticated normal shutdown pass their bounded procedures.
Both camera identities and two Behavior Start/Stop cycles pass; subsequent
camera-worker heartbeat faults cause shutdown. Tracking PFS import and isolated
D11/Line2 receiver delivery pass, while managed Tracking capture/diagnostics remain
blocked. Agent-run ordinary MCU Status/Stop result evidence fails, and SpikeGLX is unreachable.
Later [owner-supplied controller diagnostics](rig-wiring-evidence-2026-10-07/owner-mcu-console.md)
report completed D2/D9/D10 Start/Stop pairs and 120 D2 rising edges. Output diagnostics
reported zero edges under the then-installed protocol 2; D9 levels, D10 rate/reception and D2 source correlation
remain unmeasured. Ordinary Status/Stop still needs a repeat with exact provenance.
Desktop app approval timed out; actual viewer/close/reconnect acknowledgement is
unverified. Missing projector profile/arena/assignments and existing scientific,
electrical, encoder and full-workload checks remain open. No experiment or remote
recording ran. Final exact receipts and application-guard release confirm cleanup.

Historical execution: [2026-10-01 Windows audit](rig-audit-2026-10-01/README.md),
baseline HEAD `826984255e0a8469afccbda2dcaf8c642b528b33` plus uncommitted repairs.
Final all-marker suite under the actual High-integrity token, using a dedicated
workspace basetemp: 759 passed, zero skipped or failed. This ran the four previously
privilege-skipped symlink cases; the two POSIX mode tests were explicitly removed,
and native broad-DACL rejection remains covered. The earlier Medium-token
default-temp snapshot (755 passed, 6 skipped) is historical. Native ring binding,
executing-interpreter identity and reservation/recovery repairs pass focused
regressions. These are bounded evidence, not full-workload acceptance. Encoder
compatibility item 5 remains owner-deferred and unchanged. The bounded GUI/SpikeGLX
diagnostic below is later evidence; full session integration remains open. Deferred scientific inputs remain unset. No camera
settings, projection, wiring or firmware changed.

Current development handoff: [2026-10-07 managed runtime wiring](runtime.md#current-scope-and-review).
Use the complete current source and the [Windows execution procedure](#execution-and-results);
this development increment performed no rig/device operations. Retained
[hardware evidence and implementation constraints](rig-handoff-2026-09-29/README.md)
still govern the physical checks.
Camera roles/rates are now owner-confirmed (behavioral 40065509 at 30 Hz; tracking
40747103 at 60 Hz). Final ROI/depth and surface mapping remain deferred; the
SpikeGLX command-server address was saved after the 2026-10-05 SDK readback.
The 2080 Ti format checks and current camera rate limits in
that handoff do not close the full-workload checks below.

Status: rig access established on 2026-09-29. Start with the later
[rig handoff](rig-handoff-2026-09-29/README.md) and
[evidence review](rig-handoff-2026-09-29/review.md); the
[initial audit and repair follow-up](rig-audit-2026-09-29/README.md) retain earlier snapshots.
Owner camera assignments/rates and repaired RTX 2080 Ti availability are established.
Small concurrent encodes and selected three-frame full-resolution encodes passed;
known codec/size failures are recorded. Four outputs are detected on the RTX 5060 Ti
at 60 Hz; physical surface mapping and optical/presentation verification remain open. The
full-workload, optical, electrical and CephVR2.0 lifecycle checks below remain open;
controller/supervisor and acquisition implementation reports record source review,
and Visual Stimulus implementation is in progress. None of these observations establishes full
rig acceptance. See [runtime](runtime.md), [acquisition](acquisition.md),
[Visual Stimulus](visual_stimulus.md) and [tracking](tracking.md) for their current status.
Continue rig-independent decisions under [GOV-001](../architecture.md#gov-001).

This is a verification worklist, not another decision log. Governing rules are
[A08](../docs/architecture/acquisition.md#a08) and
[E15](../docs/architecture/system-contracts.md#e15). These checks are explicitly
tracked separately from installation discovery and dependency smoke checks.

2026-10-05 SpikeGLX preflight: after the ephys machine came online, the rig's
`169.254.91.196` interface discovered `169.254.240.108`. Port 4142 accepted a
TCP connection, and the official SDK connected and read SpikeGLX
`v20251218 api v4.1.3`, `isRunning=false`, `isSaving=false` and data directory
`C:/SGL_DATA`. `getRunName` returned "Run parameters never validated." No
mutation or recording was attempted. The observed address and port are now in
the operator synchronization config; the local GUI draft is independent. The checked-in mapping reference is for
`v20260901`, so E12 Setup and start/stop acceptance remain open. See the
[dated connection evidence](spikeglx-evidence-2026-10-05/README.md).

Later 2026-10-05 SDK preflight read validated settings, an idle run,
Immediate gate/trigger modes and one OneBox stream with 14 saved channels.
After the operator enabled recording at run start, an SDK smoke test started
`CephVR_Test_20261005_163039`, observed saving and increasing samples, and
called stopRun with exact run/data-directory identity. stopRun returned
success, but isRunning stayed true through about two seconds of immediate
checks; a fresh connection then confirmed running/saving false. The precise
stop-confirmation latency, full installed-version mapping, saved-channel
roles and E12 controller lifecycle remain open. See the dated evidence.

Later the controller-owned, read-only SDK diagnostic returned the same server
version, idle/not-saving state, run name and data directory from the saved endpoint.
The managed GUI Test connection action now forwards an authenticated controller
RPC. Its GUI intent and controller RPC authorization tests pass. A later managed
launch displayed a connected Dashboard after concurrent renderer startup fixes,
then exited before the button could be clicked. The agent's UI tool could read
but could not click that window. A retry ended with `JOB_INSPECTION_FAILED`;
the intermittent native process-inspection error remains open. The exact GUI
button response remains unverified. No E12 Setup or recording command was issued.

<a id="managed-device-gui"></a>
### Managed MCU and camera GUI verification

- [ ] `trial-state-runtime-output`: remaining acceptance is preview LOW, configured
  intertrial gaps/consecutive trials, bounded watchdog loss and full-load edge timing.
  Oct20 owner-authorized managed upload verifies COM8 protocol6/stopped outputs;
  native normal60s and early-Abort sessions confirm physical HIGH/LOW on SpikeGLX
  OneBox0/channel0 (median HIGH4.882V; settled LOW below0.008V), no missing samples
  or HIGH dropouts. Initial/unconfigured/reset and edge transients remain in raw
  evidence; this does not certify electrical behavior across board reset.
  Original configuration/saved bytes restored and both native cleanup joins pass.
  [Assessment](acquisition.md),
  [raw/commands/limits](runtime-evidence-2026-10-20/trial-state-runtime-output/verification.json).

- [ ] `camera-connect-selected-all`: after GUI reopen, verify Connect selected /
  Disconnect selected and enabled-only Connect all / Disconnect all with actual
  cameras. Confirm partial connection joins retain prior captures, selected-row
  changes never retarget the pending call, disabled cameras remain untouched and
  controller readback drives labels. Exercise cancellation/failure and remaining
  disconnect attempts with truthful cleanup; local offscreen queue/layout cases
  pass but do not establish camera/MCU workload acceptance. [Assessment](runtime.md).

- [ ] `preview-click-and-first-show`: after a full application restart, verify the
  current A10/G01 viewer code with all three real cameras. Repeatedly click/focus
  each image and title bar, drag/resize the window, wheel zoom and drag the zoomed
  image to each edge, reset, X/Show and minimize/restore;
  confirm first visibility already has the measured footprint geometry, continued
  capture/run identities and truthful independent close state. Repeat on alternate
  DPI/monitors with manual placement opt-out and Snap. Oct19 three isolated native
  generated-image windows pass hidden creation, activation/click responsiveness,
  zoom/pan/reset/X/mapping-release checks; this does not close physical interaction or
  camera workload acceptance. [Evidence/limits](runtime.md).

- [ ] `camera-connect-continuity`: owner-authorized managed upload installed matching
  protocol6 `cephvr2_uno_6` onOct20. Camera continuity acceptance remains outstanding;
  the trial-state physical checks do not close the checks below.
  Measure existing pulse edges during repeated second/third-camera Connect, including
  joins during HIGH/LOW and invalid new pin/rate rejection. Verify no missing/extra
  edges or phase reset, quantify jitter, and retain unchanged capture run/ring/viewer
  identities plus camera frame/counter continuity. Exercise failed new-camera
  preparation and normal existing-output OFF/watchdog/fault handling. No board action
  or electrical continuity acceptance was performed by the source implementation.
  [Current local evidence/limits](acquisition.md).
- With the installed firmware, verify continuous tests stay active beyond
  two seconds, explicit Stop leaves outputs LOW/retains counts, and loss of matched
  diagnostic status renewal stops within the two-second lease without restart.
  Retest control/phase/closure cleanup. [Local evidence and limits](runtime.md) do not
  establish electrical/camera acceptance.


- [ ] Under [G01](../docs/architecture/gui.md#g01), exercise each tab's native
  configuration chooser and sidebar full-GUI controls at narrow/window DPI settings;
  verify experimenter files restore explicit identities/paths, changed PFS paths
  require SDK import, pulse mapping publication stays explicit, and authority/device
  activity cancels or blocks loading. Local round-trip tests and offscreen images
  do not establish native chooser, optical or hardware acceptance. See the
  [snapshot contract](../contracts/gui-configuration-files.md).
- [ ] After a Connect that fails (unplugged or wrong-firmware board, timeout),
  retry Connect without releasing control: the second attempt must open a fresh
  COM handle with no "access denied", and a failed start of a pin diagnostic must
  end by Release with outputs verified LOW. Local fakes prove the discard and
  cleanup order ([A11](../docs/architecture/acquisition.md#a11), revision 45); they
  do not prove Windows handle release.

Implementation update: 2026-10-08; physical acceptance remains open under A10/A11/E15.
Use `.venv\Scripts\python.exe tools/generate_contracts.py`, then
`.venv\Scripts\python.exe scripts/start_runtime_gui.py` on the rig. Do not launch a
second application generation while the previous launcher/backends remain active.
For replacement testing, start an idle runtime from the updated launcher, run the
same script in another interactive terminal, and verify N leaves the first runtime
unchanged. Repeat with Y: the first launcher must verify an empty application job
and publish its exact exit receipt before the second generation starts. Do this
outside an experiment; force replacement is not graceful recording closure.
Older launchers without the replacement endpoint require one manual shutdown.

For explicit firmware Upload, select the primary Arduino `.ino` (or compiled Uno
application `.hex`) and verify the board/port before pressing Upload. Keep the selected
sketch in its own directory with its companion headers. The repaired paths are
`firmware/uno/cephvr2_mcu/cephvr2_mcu.ino` for this protocol-3 host and
`firmware/uno/cephvr1_mcu/cephvr1_mcu.ino` for the incompatible legacy program.
Both pinned snapshots compile on Oct9; this does not authorize treating the legacy
program as host-compatible. Verify the installed
CLI/Uno AVR core and required libraries. Confirm source/companion changes are detected,
compiler errors leave serial untouched, the application image excludes bootloader data,
and exact compiler/job/source/build cleanup precedes upload. During Configuration
with camera/device ownership and diagnostics released, confirm controller authorization
and sole serial ownership, serial release, contained CLI upload
with verification, exact helper/pipe/private-source/build/image cleanup and fresh protocol-3
CAPS/STATUS with all outputs off. Confirm tests/capture block Upload, malformed or
changed images leave serial untouched, and failed/disconnected uploads never resume
outputs. Only perform interruption/failure injection with an approved recoverable
image and wiring; verify unresolved native cleanup blocks Setup and device access.
Existing successful manual installations do not establish GUI upload acceptance.
Oct8 managed RPC execution now passes native compilation/verified upload, fresh
outputs-off readback and compiler rejection with unchanged serial connection;
actual chooser/button interaction, interrupted upload and unresolved-helper cleanup
injection remain open. Active-D9 control release and stopped-diagnostic cleanup pass.
After a full restart with acquisition policy 18 and Microcontroller policy 1, test
Microcontroller Connect/Test/Stop and Upload with acquisition disabled, then camera
external-trigger Setup/preview/Start/Stop through the authenticated controller claim.
Verify original boundary/stop timing and watchdog behavior under load, stale-claim
rejection, and physical COM/native cleanup on normal shutdown and authority loss.

1. Confirm the synchronized GUI automatically acquires unheld control. With a
   headless holder, it must remain observing until explicit confirmed takeover.
   Manual Release must stay released; reconnect must acknowledge important retained issues before
   making a fresh unheld claim. Repeat a quiet reopen with routine validation notices
   and confirmed completed recovery: no automatic review; full manual history/copy
   remains available. Failed/uncertain outcomes, pending decisions and unknown warnings
   must still require review under E03. In Devices/Microcontroller, scan and select the actual COM port,
   set enabled I/O pins, complete edits with Enter, and wait for controller confirmation.
   Test connection must report the actual firmware/protocol with outputs stopped.
   Verify the G01 contextual Camera/Projector wiring editors at native narrow/DPI
   sizes. Configure logical camera pins before discovery, then assign devices without
   changing Use; remove/reload wiring and confirm participation is preserved. Repeat
   identity/MCU diagnostics with another camera incomplete, checking exact requested
   inputs, stale-base/control-loss rejection and no implicit pulse/capture start.
   Incomplete participating settings must still block capture/Setup as applicable.
2. Test one enabled output at a time, observing its configured SpikeGLX receiver
   under the existing wiring/voltage checks. Verify Test→Stop→Test, explicit Stop,
   firmware's bounded termination and truthful final state. Trial state D9 should
   hold HIGH for up to two seconds and return LOW; Behavior D10 at requested 30 Hz
   should produce a 50%-duty pulse train with approximately 33.3 ms between rising
   edges, then return LOW. Record receiving channel and measured timing/level.
   Protocol 3 output tests count generated rising transitions (D9: one); camera
   counts must increase while active and remain stable after Stop/timeout. Repeat
   Test and confirm the counter resets rather than accumulating across tests.
   The counter does not independently measure the receiving signal. Projector flip
   input tests remain owner-deferred; a software response is not physical waveform proof.
3. In Cameras, refresh, assign Behavior/Tracking roles, select each PFS and confirm
   the detected trigger source. Set requested external rates; configure matching
   MCU pins. Wait for accepted settings, then enable Use. Missing source/rate/pin
   errors must remain explicit; no free-running fallback is permitted.
4. Test enabled: verify separate connection/identity results, no capture or trigger
   pulses, preserved selection, and reported failure for an unavailable camera.
5. Click Connect on each camera; confirm capture and its OpenCV window open together,
   with usable frames and MCU pulse state. The Dashboard selector uses the same
   acquisition-owned native windows. Close with X/Hide and verify backend visibility updates
   the selector while capture continues. Reopen, then Disconnect and verify
   window/reader and camera/buffer/pulse release.
   After full restart for policy 15, verify initial GUI-right-edge placement, left
   fallback and work-area clamping on actual monitor/DPI arrangements. Confirm
   square image area, undistorted landscape/portrait padding, pointer wheel zoom
   and double-click fit reset, including while no new frames arrive. Move the GUI
   and reopen to verify fresh initial placement. Isolated native geometry/mouse
   checks pass; these physical GUI/camera checks remain outstanding.
   Oct8 real Behavior Connect/display/Disconnect and moved-GUI placement pass twice;
   real Tracking Connect/Show/Disconnect also passes twice after exact ring-proof
   repair. Retain alternate-DPI/fallback, actual selector/click and mouse acceptance.
   First repeat Behavior-only with Tracking idle to verify acceptance of its empty
   preview identity; confirm Start completes, visible frames, Stop completes and
   camera/buffer/pulse release, then repeat the cycle. Repeat with both enabled.
   Settings remain locked while a camera is owned.
6. Exercise loss of control/controller connection during tests/capture, failed PFS,
   missing trigger input and device unplug. Verify stale actions are not replayed,
   incomplete cleanup stays visible, and no false successful result appears.

Retain source revision, logs and receiver evidence with the dated rig results.
Existing operating-point/throughput deferrals below remain separate.

| Check | Evidence required |
| --- | --- |
| Final camera operating points | Under A10, choose the owner-deferred ROI/source/recording precision, then re-read payload, chunks, transport limits and applicable resulting-rate nodes. Resolve behavioral 30 Hz's saved 368,640,000 B/s payload demand versus 360,000,000 B/s limit explicitly; no guessed higher limit or lower cadence. Verify simultaneous externally triggered 30/60 Hz capture with native counters and saved pulse evidence. Different USB host controllers and tracking's 71.803 Hz estimate do not prove sustained rates. |
| Production encoder/tool combination | Under A08/E13/SYS-003, the Oct13 matched 9.0.2 PATH pair passes build/device and five short sequential synthetic cases. The tested FFmpeg 7.1 / ffprobe 4.3.2 combination is not that deployment baseline. Verify final camera post-filter and Visual Stimulus composite dimensions/depth on the RTX 2080 Ti; retain the handoff's H.264 width/10-bit and AV1 failures. Run both cameras plus composite with rendering/tracking, measuring drops, transfer cost, queue occupancy and finalization. Three static frames and small concurrent sessions do not close this check. |
| Pulse inventory and wiring | Under E12/SYS-004, fill `[pulse_inventory]` from the actual OneBox wiring and verify Behavioral, Tracking and Eye triggers plus the photodiode appear on their mapped saved channel/bit, including edge polarity and a reassigned-role Setup. Eye uses `eye_tracking_camera`; keep its actual stream/channel/bit unset until checked on the rig. Verify paired Setup rejects an enabled externally triggered Eye with missing/unsaved mapping and retains the verified mapping in SESSION_CONFIG; disabled/free-running Eye does not require it. Keep wiring and trigger timing unchanged. The Setup check proves configuration only. |
| Visual Stimulus multi-output lifecycle/pacing | Under V15/V20/E05, measure both configured presentation modes with all outputs and full tracking/recording load. Verify per-output Started evidence within the existing 250 ms allowance, Idle transitions and late/in-flight submission handling; software swaps are not optical proof. |
| Visual Stimulus startup Idle | Under V19/E08, check valid saved settings, first-run/missing outputs or profiles, partial window/context failure and cleanup, stale configuration results, Setup reuse/replacement and GUI/headless issue visibility. No guessed black/default calibration or false session Ready. |
| Visual Stimulus geometry, photometry and photodiode | Verify surface/observer geometry, output mapping, calibrated/uncalibrated profiles, marker black-area/inner-square placement and levels, per-output blackout zones and optical sequence/timing under V15/V19/V22/V23. Check corner bounds, marker priority over overlapping zones, masked final recordings, static zones through Idle and frame/grid diagnostics, and unobscured raw reference bars. Include same-level marker boundaries with no edge. |
| Visual Stimulus media decode and profiles | Under V04/V11, verify PNG/TIFF source-depth preservation, JPEG/H.264 interpretation, FFV1 and static GLB supported/rejected profiles, exact media endpoints/VFR selection and independent instances. Exercise aggregate decoder/codec thread and memory limits, callbacks/logging, stale generation rejection, leases, cancellation/hung native work and all four outputs with tracking/recording. No measured throughput or decoder fault isolation is claimed. |
| Visual Stimulus protected assets | Under V04/V13, verify protected streaming sources on the actual storage/decoder combination, independent instance cursors, dependency coverage, external write/replacement attempts and release after cancellation/owner loss. Prepared-memory reuse and relocated replay must use the identified content; no periodic trial-time hashing or archive is introduced. |
| Visual Stimulus linear color and measured tables | Under V04/V21/V23, verify source transfer/range/channels and 8/16-bit preservation, float32 composition/premultiplied alpha/filtering, named clipping flags, curve interpolation and one-time correction. Measure each output's response and actual code precision; check manual/driver/projector conditions, no double gamma, Idle/marker consistency and distinct marker light levels. Independent channel tables alone do not prove cross-projector color matching or spatial uniformity. |
| Visual Stimulus output precision and custom encoding | Under V20/E13, verify requested versus actual RGB8/RGB10 buffers, final code preservation, calibration matching and the real driver/cable/projector path. Exercise the single composite lossy argument validation, actual encoder compatibility at the composite resolution, explicit review conversion and encoder load/failure while preserving live rendering and required state evidence. Under SYS-002, confirm the now-operational RTX 2080 Ti sustains three concurrent NVENC sessions (two cameras plus one Visual Stimulus composite) at planned rates while the RTX 5060 Ti renders/tracks and AMD integrated graphics serves the operator display/GUI. Verify actual adapter identities, explicit FFmpeg device selection and host-transfer costs; the earlier RTX 5060 Ti encoder probes do not validate this placement. Normal runtime still performs no file-content validation. |
| SpikeGLX session control | Under E12 and the [control contract](../contracts/spikeglx-control.md): installed SDK/SpikeGLX versions; command server bound to the dedicated link and firewall admitting only the rig; readback, gate/trigger-mode rejection and run-name collision behavior; saving-enable-to-saving latency and per-stream sample-count progress (including one stalled stream) to set the writing/no-progress bounds; saving-OFF confirmation with acquisition continuing; timed-out mutation reconciliation; Abort/link-loss behavior including transient recovery, per-stream deadline expiry, late replies and counter reset detection; command-server port (default 4142); stop margin against the final photodiode edge, including normal/Abort/Cancel across trials with acquisition preserved, interrupted uncertain starts and immediate stop between trials; repeated fault/recovery episodes; controller-loss emergency warning naming the run for manually disabling saving. Acknowledgements are not pulse timing. |

| Arena-file movement limits | Under V16/G01, load a legacy rectangular GLB and a declared convex GLB; verify transformed world bounds, 30 mm/default and edited clearance, starting pose, sliding at walls/corners and four-view agreement. Reject missing/unsupported/invalid geometry, empty inset and outside starts; retain resolved regions/fingerprints and source specifications through Setup/reset/restart. Preserve loaded explicit regions and unrestricted mode. Inspect nonempty effective_poses for the active arena: declared frame, mm position and unit quaternion must agree with the frozen rendered transform before its authored asset mapping; retain exact model matrices and constrained-motion evidence. Oct16 local structured-evidence checks do not close this native/scientific acceptance. Local offscreen/compiler/resource tests do not establish native file protection or rig equivalence. |
| Visual Stimulus scene composition and geometric correction | Under V02/V15, exercise one arena plus ordered alpha overlays, overlay independence from arena depth, covered-instance continuity and invalid composition rejection. Verify imported mesh coverage/orientation/fold rejection, masks and weighted overlaps, immutable session mappings, photodiode stage order and final-output recording/replay. Establish calibration accuracy through the actual optical path and resource cost on all outputs; no automatic calibration or optical-model guarantee is selected. |
| Visual Stimulus review video and fragmented MP4 | Under E13/Header6, verify sequential raw stdin at the unchanged nominal playback rate sustains the unchanged composite resolution. Decoded frame n must map once to its exact source group/evaluation time and per-output submissions, with zero same-slot omissions or synthetic duplicates; tile placement/scale must match the recipe. Exercise same-time groups, capacity drops, out-of-order/cancelled readbacks, normal/Abort/empty input, and missing-tail mappings after a crash. Verify successful closure reconciles admissions/input counts and cleanup retries retain the exact first cutoff and original write deadline. Exercise fragmented output, keyframe/fragment resource bounds, reader compatibility and drain/sync/close without ordinary-MP4 conversion or file-validation passes. |
| Empty Visual Stimulus review video and explicit depth conversion | Under V12/E13, exercise an all-dropped composite with complete required records, warnings, truthful artifact presence and successful cleanup. Reject empty-input encoder errors, missing-created artifacts and unknown results as normal completion. Verify explicit RGB10-to-8-bit review conversion and rejection of silent negotiation while live output/replay retain their selected precision. Normal runtime does not inspect completed-file contents. |
| Visual Stimulus capture and durability | Verify per-group composite admission, compositing/PBO readback cost on the render thread, recording-thread and FFmpeg throughput within the renderer's process/GIL, ScheduleTrial FFmpeg launch with no frames before T and pre-T cancellation cleanup, required state/metadata retention and failures under V12/V13/V28; test periodic sync, sync failure, an incomplete final JSON line and replay labelled "partial, up to render group N". Preserve Unconfirmed crashed-video outcomes. |
| Acquisition electrical/serial behavior | COM8 Uno protocol-v2 CAPS/STATUS passed after the manual upload. Owner assigned D9 Trial state, D2 Projector flip input, D10 behavioral trigger and D11 tracking trigger; the initial D2 test counted zero edges while the projector was off, and a later local GUI-worker test counted 120 rising edges without independent source observation. Confirm actual destinations, 5 V compatibility and shared signal ground before output tests. Run current output GUI Test/Stop with physical level/edge observation; former D2 input tests remain owner-deferred. Then verify camera trigger levels/edges, OFF/watchdog behavior, serial latency and DTR/RTS reconnect/reset under A10/A11; do not infer pulse-to-frame edge mapping from host receipts. |
| Owned camera/pulse edits | Under A10/E07, apply a two-camera batch and pulse-only/configuration-only edits while the backend owns editing/preview devices. Verify actual readback, old external-output OFF before timing changes, exact preview restart and partial SDK/confirmation failure with capture/pulses stopped. Lose confirmation replies and verify committed configuration stays distinct from device outcome; exercise bounded next-edit base synchronization only after prior work quiesces, plus control loss, late results and exact cleanup. Suppress failed-restart status delivery before first-frame proof; recover the exact cleanup run without claiming it is running. Inject primary/Tracking transfer-release failure and lost MCU CLOSE replies; retain ownership fences until exact release or same-claim cleanup succeeds. Local fake-device tests do not close this check. |
| Acquisition platform bindings | Verify frame-log flush/OS sync on the selected filesystem and SDK/native conversion under A07/A10, and the A03 seqlock slots plus Win32 named event adapter across spawned and independently launched consumers, including torn/lapped-read skips under load and a killed producer. |
| Visual Stimulus feedback freshness | Tune and validate the 350 ms engineering default maximum under [V26](../docs/architecture/visual_stimulus.md#v26) with the full rig workload. Measure host-receipt-to-application age separately from optical latency; verify local stale-result rejection, fresh-result resumption within the same generation, producer-marker generation exclusion and logged hold/resumption. No passing evidence is supplied. |
| Reusable stimulus readback and GPU row orientation | Verify new `*_top_down` recipe/evidence declarations and byte-identical pre-encoding RGBA8/packed10 input against the previous CPU flip, including asymmetric tiles, black margins, photodiode patches and odd/even heights. Confirm lazy PBO allocation plateaus at the existing capture-slot bound, ready buffers reuse safely, Abort/fault cleanup releases idle/pending storage and both FBO targets even when evidence publication fails, unbind/deletion failures retain exact retry ownership, and repeated Setup/Start does not grow GPU memory. End on a different projector context and verify cleanup activates the composite owner before deleting its FBOs; activation failure must retain resources for retry. Compare capture/readback/normalization/pipe timing, drops and combined-load throughput at unchanged dimensions, quality and projector rates; the new nearest GPU flip adds a copy and no speedup is presumed. |
| FFmpeg raw input path | Verify raw stdin input (`-f rawvideo`, resolved pixel format/size, nominal `-framerate`) for the selected native pixel/conversion paths sustains the planned rates. For A07/A08 schema5 cameras, confirm decoded count equals sequential encoded mappings and retained usable source count, including closely spaced receipts, invalid images/capacity losses, long gaps, Abort and empty input. Require zero padding and unchanged source/native timestamps; playback duration is count/nominal rate and need not match the trial. Record representative combined-load throughput at unchanged camera rates. E13/Header6 stimulus also uses sequential retained composites without padding or rate-based omission; verify its group/timestamp mappings and unchanged composite geometry/pacing under combined load. Record exact tested versions, arguments and camera formats. |
| Consumer precision and encoder compatibility | Verify native unpacking/alignment and source-depth RGB/grayscale preparation under the [pixel contract](../contracts/acquisition/pixel-processing.md), including high-bit-depth sources. Confirm the actual selected codec/output bit depth and color representation; no silent lower-depth conversion or widened 8-bit data labelled original-depth. Preview alone uses the approved display scaling. Keep lossy compression quality separate from representation bit depth. Verify the explicit per-camera output pixel format under A08, including detection of encoder format substitution. Check requested versus actual range/matrix conversion and output tags using known pixel values; tags alone do not prove the conversion. Verify that lower-depth output settings reject higher-depth sources until explicitly compatible arguments are provided. |
| Basler conversion mappings | Exercise the declared [SDK registry](../contracts/acquisition/sdk-mappings.md): native packing/stride, Bayer patterns and edges, private buffer lifetime, effective depth and preview scaling. Record actual device/SDK support; unsupported mappings must fail explicitly. |
| Windows ownership and cleanup | Exercise the shared [acquisition/Visual Stimulus launch contract](../contracts/windows-launch.md) and acquisition [I/O/sync contracts](../contracts/acquisition/windows-resources.md), including owner death at every launch stage, partial handle transfer, blocked pipe/stdin cancellation, process identity reuse, encoder sharing and failed storage sync. Require truthful cleanup blockers. |
| GUI authoring and planning preview | Install `.[dev,gui]` and launch `python scripts/start_gui.py`; follow [frontend review commands](../docs/development.md#dashboard-frontend-review). Check Windows DPI/narrow-window layouts, discovered cameras/COM ports, enabled projector combinations, calibration JSON load/save and pixel offsets/inversions. Build and reload a 200-epoch trial with independent per-projector layers and random/ordered batch values; use Shuffle trial on nested repeat/condition groups, verify intact blocks and selection through undo/redo/save/load, and check readable timeline actions at narrow DPI; switch trials and rotate/scrub the two-sided rig preview using local assets. Record latency and errors. This is frontend acceptance, not physical output or live Tracking validation. Typed pacing configuration and exact held-policy checks now pass locally; physical output acceptance remains open. |
| Managed GUI configuration and authority | After local wiring acceptance, use the installed managed entry point and current review layout at wide/narrow Windows DPI. Submit subject metadata, ordered trials/seeds/gaps, recording selections, Tracking settings and projector mappings; compare accepted revision/history/session metadata. Exercise first-run display-profile import separately from calibration-value JSON. Invalid or stale visible drafts must block Setup with a useful explanation. Exercise pending Setup cancellation, Abort, lease loss/takeover, pending prompt updates, disconnect/reopen with retained warnings and GUI close/relaunch with `python scripts/start_runtime_gui.py --reopen-gui` for the same application generation. Exercise delayed/lost relaunch replies and shutdown during the request; containment deadlines must remain unchanged. Cancel a proposed discard or dismiss a save-error dialog and confirm unsent edits remain. No stale intent replay or silent draft replacement. |
| Tracking configuration diagnostics | Under T08/A03/A10, attach to the selected owned camera preview with exact source identity, including when experiment Tracking is disabled. Start with an empty stage mask, then flow-only without pose annotations, and verify unavailable dependent stages. Verify crop/downscale annotations stay in acquired coordinates and enabled stages produce live overlays/timings. Confirm ordered Tracking consumption, bounded viewer latency, explicit viewer detach/reopen versus actual processing closure, and cleanup after source/authority loss and before Setup. Use **Use this frame for annotation** to freeze an exact acquired image; confirm source changes reset annotations and stale frames are rejected. Pending or failed Close must keep settings locked and must not enable another Begin. Changed diagnostic settings require confirmed Close and fresh Begin. Verify no scientific files or Visual Stimulus feedback arise from diagnostics. Under T20/T38, confirm missing/invalid camera calibration blocks experiment/runnable locomotion, early diagnostics still run, acquired-image scale survives crop/downscale, and known motion produces correctly converted mm/s/deg/s feedback/file values with retained pixel-space evidence. Verify explicit old gain/unit rejection; scale is not animal swimming-speed validation. Scientific accuracy/full-load acceptance remains separate. |
| Untimed projector calibration | Dedicated physical/fault acceptance remains pending. Under current G01/V01/V15/V22, use Launch reference calibration, Launch projection calibration, Launch photodiode placement and Launch blackout placement with all four assigned/enabled outputs, separate protected per-view sources and per-step runtime copies. Check repeating V22 bright/dark pulse placement on black and black zones on neutral gray, live target/Frame/Pulse/zone add/remove, partial/out-of-bounds edits retaining prior output, selected Close and Unknown tuning locks; check pulse continuation after live edits, sequence restart on reopen, and cessation on Unknown/Close. Diagnostic submissions do not establish optical timing. Verify native output-boundary frame/raw pixel bars; measure both bar lengths per screen in the current native mode. Frame/grid uses the measured per-axis mm/px: compare physical spacing with a ruler, whole-pixel Width/Height capped at native dimensions, blank measured sizes, center-relative Offset X/Y limits/reclamping and retained fixed pitch during live crop/translation. Verify load/save/actual close/reopen persistence, invalid/partial edits retaining the last applied output, exact sequence/revision/lease fences, late Open, rejection, loss and shutdown cleanup. Repeat after Windows scaling above100% using native identities. Preserve imported nonlinear/masked/weighted corrections. No margin/keystone/seam controls belong to this retained workflow; local/offscreen passes do not establish measured alignment or actual output closure. — [G01](../docs/architecture/gui.md#g01), [V15](../docs/architecture/visual_stimulus.md#v15) |
| GUI Windows display inventory | Compare Projectors table/diagram indices against Windows Settings → Identify on the actual multi-GPU rig, including reconnect, clone mode and changed topology. Verify pixel resolution, retained assignments and explicit query failures. Oct8 isolated Qt retention checks cover immediate saving, restart, reordered/missing/returning identities and local-draft/controller isolation; repeat actual GUI restart and physical unplug/reconnect with stable native identity. macOS inspection and mocked native API calls do not establish equivalence. See [G01](../docs/architecture/gui.md#g01). |
| Windows venv interpreter process tree | Prepared-image native regression now verifies one live job member, exact launched/executing PID and OS image, fresh venv imports and inherited bootstrap. Verify real managed registration and shutdown after GUI implementation; focused evidence does not establish full application behavior. |
| Runtime finalization boundary | Under A07/E05, verify bounded online accounting, encoder finalization, sync and close without a separate file-validation pass. Measure drain/closure delay before the next trial. Output-content inspection belongs to external post hoc or development verification, never an automatic runtime validator. |
| Empty camera video | Verify the all-dropped case with actual input/muxer behavior: complete frame log with its completion line, truthful artifact presence/closure and grouped warning. Reject encoder failure disguised as empty success, missing-created artifacts and unknown closure; retain Interrupted/health outcomes. |
| MCU host boundary binding | Verify grouped ON/OFF dispatch at host T/end, reserved-channel drain, command/reply timestamps, Abort during an outstanding request and late OFF evidence. Validate report deadlines independently from physical pulse/exposure delay; no early compensation or shifted recording interval. |
| Encoder pre-T launch and cancel cleanup | Under A08, with both cameras enabled, verify FFmpeg launch/registration at ScheduleTrial acceptance completes before T, no frames reach it before T, and first real input, recording-queue occupancy/drops and Started deadlines at T. Measure T-to-first-encoded-input latency (including any encoder initialization FFmpeg defers until its first frame) and confirm zero start-up drops without `recording_startup_allowance_ms`. Exercise pre-T launch/initialization failure (interrupts before release), and schedule cancellation, interruption and release failure before T: the child is terminated, only its own created MP4 is deleted and an unexpected file is kept and reported. Ready alone is not encoder initialization evidence. |
| Producer-local interruption | Delay stop delivery across cameras. Verify each camera worker's recording thread uses its capture cutoff, preserves prior admitted frame records, never substitutes request time, and keeps a missing cutoff unconfirmed. |
| Camera clock provenance | Verify selected source/unit readback, descriptor transfer and frame-log header clock fields against actual models/configurations; include unknown units, missing samples, reset/wrap and source changes. No host-clock calibration or inferred device semantics. |
| Recording identity survival | Verify acquisition-owned tags match frame-log header/session identities through hybrid MP4 writing, normal finalization and interrupted (crash-truncated) writing. Missing/damaged/cross-paired tags must remain unverified; checks here are development work, never a runtime validation pass. |

Exercise both representative generated input and camera recordings on the rig after
the main architecture is established. Keep sample outputs and comparison results as
evidence. An unsuccessful check requires a revised implementation proposal or an
explicit decision change; do not silently loosen timing requirements. Missing/crashed
outputs must remain uncertain rather than being counted as a passing result.

Other runtime, performance and durability verification remains required by E15;
this list records the specific items deferred here, not a completed test plan.

Visual Stimulus declaration closure: sequential retained frames with exact external
source timestamps and nominal MP4 playback timing are bound in
[encoding options](../contracts/visual_stimulus/encoding-options.md#review-timing).
The existing encoder input-format/throughput deferral is unchanged; no successful test
is implied. Full declaration status is in the
[Visual Stimulus contract index](../contracts/visual_stimulus/README.md).

Application shutdown verification under E08: nested job membership for every backend
and partial helper launch; sole non-inherited outer handle; controller, supervisor,
both-authority and launcher failure; graceful cleanup followed by bounded escalation;
no unrelated process termination; unresolved output/SpikeGLX evidence retained at
next startup. Verify actual process absence and machine-guard release separately
from file closure. Verify repeated manual-camera and session retirement using the
new exact typed Cleanup confirmation, including independently delayed lifecycle and
operation reports, failed-but-discharged outputs and unconfirmed resource rejection.
Inject controller loss while the first accepted-shutdown cleanup wait is pending;
interruption must begin promptly without extending the retained cleanup/outer bounds.
These checks remain pending rig execution; implementation status belongs in the backend reports.

E06 operator-incident verification remains pending: confirm popup/reconnect/headless
behavior without shifting stimulus clocks; isolate camera/recording/tracking/ephys
failures while retaining truthful missing-data outcomes; abort and new blocking faults
override pending/stale Continue; repeated faults coalesce without losing scope; initial
readiness and healthy-function gates remain enforced; decision persistence and emergency
failure paths work within existing bounds. No runtime UI or fault-isolation behavior is
claimed by the declarations.

## Acquisition terminal accounting and serial stop budgets

- Verify A07/A10/A11 bounded post-cutoff retrieval, countable SDK purge/stop discards,
  optional native counter availability and complete terminal pulse evidence before sync.
- Resolve per-camera exposure/transport/SDK/frame-period drain allowances and verify
  actual stop/report delivery, including Abort behind an outstanding serial request.
  The 100 ms ACK / 50 ms completion reserve within 250 ms is an engineering allocation,
  not measured feasibility. No trial extension, output-file scan or runtime validation
  worker is authorized. See [MCU contract](../contracts/acquisition/microcontroller.md).

## Tracking delivery resets and exact pose geometry

- Verify [A06/T08/T09/T45](../docs/architecture/tracking.md): delivery overflow preserves
  continuous flow/filter state, actual camera gaps rebuild it, retained poses still pass
  age/order checks, and discarded movement is never replayed.
- Verify bounded pose/geometry history and native leases under reset/cutoff/concurrent
  consumers. Measure exact geometry construction's effect on pose cadence and movement
  throughput; no tolerance approximation or performance guarantee is accepted.

- Compare camera receipt → feedback publication and receipt → actual display,
  including upper-tail latency, queue/reset/drop/pose age, valid-result rate,
  CPU/GPU/transfer time and memory under four-view Visual Stimulus plus recording. Compare both
  tracking options on matched recorded inputs and live trials, retaining source
  identity and parameter differences; isolated flow speed does not prove experiment
  performance or scientific accuracy.

## Execution and results

Use a complete current source checkout (`src`, `tests`, `tools`, `contracts`, `config`
and packaging files). A wheel alone omits tests/settings; a remote clone may omit
uncommitted implementation. Preserve rig settings and recordings. Do not copy the
Mac `.venv`, caches or build environment. Use fresh Windows Python 3.11 under
[SYS-003](../architecture.md#sys-003), and close other test runs in the same checkout.

```powershell
.\tools\test_on_rig.ps1 -Install
# Later runs reuse the environment:
.\tools\test_on_rig.ps1
```

The runner installs `.[dev,gui,acquisition,visual_stimulus,tracking]` (including the
managed Qt GUI and the declared backend dependencies). FFmpeg/ffprobe must be deliberately installed on PATH; no production
pair is validated by installation/import. If local script policy blocks execution:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\test_on_rig.ps1 -Install
```

This changes no persistent execution policy. Hardware-marked tests require `-Rig`;
the runner rejects an empty hardware selection. Missing tests and skips are not passes.

| Check | Evidence produced |
| --- | --- |
| Python/package prerequisites | Python 3.11, generated bindings, QtCore/QtWidgets and backend dependencies import successfully |
| Syntax, Ruff, Windows-target mypy | Handwritten code parses and meets configured static checks |
| Module boundaries | Feature modules avoid runtime/entry imports and private runtime access; size warnings require review |
| Existing contract checks | Pure tracking and Visual Stimulus declarations remain consistent; these are separate from runtime behavior |
| Shared/controller/supervisor unit tests | Identity, bounds, deadlines, leases, evidence, reservations, and isolated failure-path logic |
| Loopback gRPC integration | Actual local controller/client transport, authentication and state-stream behavior |
| Native Windows tests | Creation-time nested jobs, retained exact process identity, kill-on-close, bootstrap pipes, ACLs, durable publication and role guards |
| Package build | Source archive builds a wheel with generated bindings using the installed compiler |

Native tests launch only their own temporary Python children. They do not start
the managed CephVR application, open cameras/projectors, or command SpikeGLX. A
Windows symlink-specific check may skip when the account lacks symlink creation
privileges; inspect the reported reason rather than treating the skip as a pass.

Success means every runner step exits zero and pytest reports no failures or errors.
Any skipped test remains unverified. Collect the actual result before accepting
platform behavior. The PowerShell runner and native assertions have not been executed
on the macOS development host.

The runner also checks acquisition dependencies/tests. Its current script determines
executed scope; newly implemented Visual Stimulus behavior needs explicit coverage and prerequisites
before any acceptance claim. E15 still permits lightweight local implementation and
authenticated communication tests; this guide does not move all tests to the rig.

The runner prints its result directory, by default:

```text
%LOCALAPPDATA%\CephVR2\TestRuns\<timestamp>\
  prerequisites.log
  syntax.log
  ruff.log
  format.log
  module-boundaries.log
  mypy-win32.log
  contracts-tracking.log
  contracts-visual_stimulus.log
  pytest.log
  pytest.xml
  package.log
  packages/
  summary.json
```

The first installation also writes `install.log`. Preserve the entire directory for
review; `summary.json` shows step exit codes and `pytest.xml` records individual
tests and skips. A custom destination can be supplied with `-OutputDirectory`.

Retain `interpreter-process-tree.log` and optional `rig-collection.log` as well.
Record the tested source revision (and uncommitted patch when applicable), platform,
device/build/settings/workload scope, commands, date, outcomes and skips with new
evidence. Update the owning backend report and close only checks supported by results.

Historical transfer identifiers, not claims of current bundle availability:
`dist/cephvr-controller-supervisor-20260929.zip` plus `.sha256` (source without
Git/bindings/caches/environments) and `dist/cephvr-acquisition-20260930.zip` plus
`.sha256` (source, packages and static logs). Regenerate or verify before relying on
an old bundle for the current tree.

## Runtime recovery and regression coverage

- Startup repair requires the prior launcher's durable receipt proving all owned
  processes absent. A missing receipt preserves the blocker; a free lock or missing
  process name does not replace that proof.
- Combined configuration/log inspection is bounded to the configured metadata byte
  capacity (currently 64 MiB). Oversized, corrupt, or incomplete administrative logs
  are preserved and described in a separate recovery report. This path does not
  certify scientific outputs or reconstruct their closure.
- Recovery appends label timestamps as observations by the new application, with
  actual historical end times unconfirmed. Unknown remote SpikeGLX stopping remains
  visible with the saved endpoint/run when available.
- An uncertain recovery append is not retried in the same application. Failed
  durable pointer publication blocks reservation release and another Setup.
- On the rig, inspect a preserved administrative log after late-Finished reconciliation
  and a later process loss. Exact reconciliation must remain nonterminal; malformed
  records and missing process-absence proof must retain blockers. Local parser tests
  cover both outcomes without certifying scientific output closure.

| Guarantee | Prepared coverage |
| --- | --- |
| Setup cancellation and Start interruption | `tests/controller/test_safety_regressions.py`, `test_setup.py` |
| Exact/stale/conflicting reports, deadline edges, late Finished | `tests/controller/test_lifecycle_reports.py`, `test_runtime_retention.py` |
| Uncertain metadata completion and reservation ownership | `tests/controller/test_metadata.py`, `test_storage.py`, `test_startup_recovery.py` |
| Control lease loss and takeover | `tests/controller/test_control_leases.py`, `tests/client/test_controller_rpc.py` |
| Partial launches and exact process identity | `tests/supervisor/test_registry.py` |
| Cleanup proof and retained shutdown deadline/escalation | `tests/supervisor/test_registration.py`, `test_recovery.py`, `test_shutdown.py`, `tests/controller/test_shutdown_handoff.py` |
| Replay ownership and bounded report ordering | `tests/controller/test_command_admission.py` |
| Module launch enters the existing CLI | `tests/controller/test_entrypoint.py` |

## Acquisition acceptance coverage

| Area | Evidence to retain || --- | --- |
| Configuration | Presence versus explicit zero/false, defaults and saved precedence, exact serial assignments, missing or unsupported SDK features |
| Capture | Joint wait wakeups and cancellation, command priority, early/normal cutoff membership, invalid frames and counter discontinuities |
| Buffers | Native layout round trips, overwrite/copy/recheck, exact run binding, retirement and partial allocation cleanup |
| Accounting | Queue drops, accounting exhaustion, empty and all-dropped trials, known versus unknown post-cutoff exclusions |
| Recording | Pre-start cancellation, pipe backpressure/stalls, negotiated format rejection, retained I/O cancellation, exact synchronization and output closure |
| MCU | Bounded malformed replies, stale request IDs, matched capabilities, requested/applied rates, watchdog/reconnect and scheduled stop budgets |
| Lifecycle | Setup cancellation, partial launches, stale/conflicting reports, original deadline boundaries, retained late closure and next-trial barriers |
| Recovery | Controller/worker loss, declared resource catalogues, consumer release proof, cleanup uncertainty and shutdown escalation |
| Manual control | Preview first usable frame, pulse acknowledgement, viewer-independent capture, settings/PFS confirmation and control-loss cleanup |

These rows are acceptance targets, not a claim that every scenario already has an
implemented automated test or has passed. The table below identifies prepared tests and the remaining hardware-only checks.

The original 2026-09-30 handoff recorded these sources as unexecuted. The table identifies where
to inspect coverage; it does not replace review of the complete rig results.

| Area | Prepared sources |
| --- | --- |
| Configuration and adoption | `tests/acquisition/test_configuration.py`, `test_session_preparation.py` |
| Exact SDK selection and required features | `tests/acquisition/test_camera_adapter_contracts.py` |
| Capture, cutoffs, queue bounds and trial reset | `tests/acquisition/test_worker_foundations.py`, `test_pulse_evidence.py` |
| Ring overwrite, copy/recheck and retirement | `tests/acquisition/test_worker_ring_regressions.py` |
| Encoder negotiation, cancellation and closure | `tests/acquisition/test_recording_negotiation.py`, `test_recording_cleanup.py`, `test_recording_paths.py`, `test_recording_capabilities.py` |
| Retained recording faults and output scope | `tests/acquisition/test_recording_cleanup.py`, `test_worker_admission.py` |
| Serial protocol, cancellation, scheduled budgets and observation provenance | `tests/controller/test_microcontroller_protocol.py`, `test_microcontroller_owner.py`; acquisition `test_pulse_evidence.py` |
| Admission, partial launch and health | `tests/acquisition/test_transport_admission.py`, `test_coordinator.py` |
| Stop/Interrupt independence and session handoff | `tests/acquisition/test_trial_lifecycle.py`, `test_session_preparation.py` |
| Cleanup closure | `tests/acquisition/test_cleanup_aggregation.py`, `tests/shared/test_cleanup_outputs.py` |
| Manual status and controller cleanup | `tests/acquisition/test_manual_devices.py`, `test_manual_preview.py`, `tests/controller/test_camera_configuration.py`, `test_camera_evidence.py` |
| Windows I/O and supervisor integration | `tests/platform/test_byte_stream.py`, `tests/supervisor/test_worker_outbound_contracts.py`, existing supervisor recovery/shutdown tests |

Real camera wait/GIL behavior, native conversion precision, electrical pulse behavior,
firmware compatibility, simultaneous encoding throughput and crash durability still
require the hardware procedures and evidence in the rig worklist. Controlled component
tests cannot establish those properties.

Missing trigger lines/pins, incompatible firmware, unresolved required image or timing
settings, missing joint-wait/GIL support and unsupported formats must block the affected
operation explicitly. Do not fill them with guessed defaults merely to obtain Ready.
Managed experiment readiness also depends on the separately implemented participant
backends and the full workload verification in the rig worklist.

## Stimulus implementation handoff — execution procedure

- [ ] Oct13 bounded image residency (owner-deferred to rig): run a protocol whose
  decoded images exceed the cache, with different per-screen images and repeated
  trials. Measure peak RAM/VRAM, storage/decode load, upload latency and frame timing
  under simultaneous recording. Force late loads: preserve the prior texture with
  current motion and unchanged clocks; reconcile requested/actual indices and repeat
  flags with submission evidence under Save On, and bounded summaries under Save Off.
  Verify first-use readiness, shared compatible sources, native fences, failed Setup,
  cancellation, release retry and protected source closure after the loader joins.
  Local fake-GL tests establish ownership logic only. See [V04](../docs/architecture/visual_stimulus.md#v04)
  and the [current assessment](visual_stimulus.md#validation-limits).

- [ ] Oct13 texture recipes/reference motion (owner-deferred to rig): load actual
  CephVR1 JSON-only and exported designs, including the owner's previously rejected
  files; compare prepared appearance/scale/blur/polar geometry on the physical
  screens. Use different textures and periods on reference/followers; verify linear
  movement through Front/Bottom and both side axes, V02 clockwise/reversed flow
  with unequal subject distances, stopped/relinked/reset phase and disabled outputs.
  Verify off-center rotation pivot diagnostics, actual prepared memory/deadline
  behavior and native file protection/cleanup. Local synthetic-source and offscreen
  tests do not establish optical signs, source-library equivalence on owner files,
  native protection or frame timing. See the [current report](visual_stimulus.md).

This procedure remains pending Windows execution. Run the automated checks first:

```powershell
.\tools\test_on_rig.ps1 -Install
.\.venv\Scripts\python.exe -m pytest tests/visual_stimulus -q
```

The runner installs the lazy `visual_stimulus` extra (ModernGL/GLFW/PyOpenGL, PyAV,
imagecodecs/tifffile and NumPy), checks imports, and includes the Visual Stimulus tests in the
normal suite. It does not start a projector or prove encoding feasibility. Save
the runner's logs, JUnit, package versions, GPU identifiers and exact Git revision.
The Windows-only protected-source test checks independent read cursors, denied
write/replacement while readers are owned, and mutation after confirmed closure.
Its local non-Windows skip is not a passing Windows result. Run it explicitly with
`.\.venv\Scripts\python.exe -m pytest tests/visual_stimulus/test_windows_resources.py -q`;
the remaining projector, encoder and named-pipe procedures below require their
stated native prerequisites and are not implied by the automated suite.

Before a managed run, supply the accepted display profile with actual device IDs,
four surface geometries, geometric correction files, selected photometric mode and
measured profiles where applicable, Idle color and photodiode patch. Supply the
asset root, authored format-2 program and retained seeds, experiment output root,
and explicit lossy FFmpeg arguments for Save On. Resolve the FFmpeg/ffprobe pair and
RTX 2080 Ti encoder capability checks. Leave unavailable scientific/device inputs
unset; their preparation failures are expected evidence, not reasons to guess values.
The rig must expose the SYS-002 GPU assignments. Closed-loop runs additionally
require the implemented tracking producer and its actual readiness/credit handshake.

Start the application in one terminal, then use the exact controller generation
printed by the launcher in another. The supplied configuration must enable `visual_stimulus`;
camera/firmware inputs are additionally required when acquisition is enabled.

```powershell
$repo = (Get-Location).Path
.\.venv\Scripts\cephvr.exe --software-root $repo --supervisor-config "$repo\config\backends\supervisor_config.toml" --python "$repo\.venv\Scripts\python.exe"
# In a second terminal:
$generation = Read-Host 'Exact running controller generation'
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation --json status
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation configuration --file .\rig-stimulus-configuration.json
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation setup
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation start
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation --json status
.\.venv\Scripts\cephvr-control.exe --controller-generation $generation shutdown
```

Use a short authored program containing image, video, texture and arena epochs,
overlays and instance absence/re-entry. Reuse a video instance across two different
assets/dimensions, then return to the first asset, checking recorded frame selection
and reset generations. Include half-alpha white over black (linear value 0.5),
opaque and masked GLB textures sharing an image, and an intentionally out-of-range
texture. Check per-output clipping coverage and compact Save Off counters, including
delayed diagnostics at Stop. Run it once with Save Off and once with Save
On. Match immutable resolved plans, epoch totals and seeds to the retained recipe;
verify no trial file or frame before released onset. Observe startup/inter-trial/stop
Idle separately from session Ready. Confirm four-view orientation, depth, alpha,
code depth, calibration, photodiode sequence and optical timing with rig instruments.
Inspect evidence/video correspondence, fixed tile dimensions, encoder placement,
storage synchronization and separate output closure results. Retain observations
even when an operation fails; software swap return is not photon timing.

For each failure procedure use a separate short session and record the affected
generation, operation ID, original deadline, retained GetState/cleanup evidence and
remaining OS resources: cancel Setup during protected reads/decode; cancel after
Schedule before onset; interrupt during presentation and during blocked encoder
input; remove storage access; terminate the exact renderer or owning authority.
Require immediate local fencing, bounded shared cleanup and truthful unresolved
resources/output closure. Do not treat a process exit or empty output file as
successful finalization. Exercise empty/all-dropped recordings through the recording
capacity and closure tests, then verify the native encoder's empty-input result on
the rig without inserting dummy frames.

For the analysis handoff, preserve `_stimulus_LOG.json`, `_stimulus_frames.jsonl`
(when Save On), and the matching external assets. Inspect the recipe's complete
resolved plan, fingerprints, calibration/output settings, compatibility/provenance
and uniform layouts. Match frame records to effective state, actual source-frame
selections, output submissions, clipping coverage and recording omissions. Verify
that an interrupted final JSONL line is distinguishable from complete records and
that absent Completion remains visibly incomplete. Save Off retains the recipe only
and cannot guarantee actual-output reconstruction.

Offline replay/export testing belongs to the analysis software once its implementation
is available; this experiment package has no replay command. That acceptance must
exercise missing assets/evidence, partial coverage and exported PNG/index/report
contents against the published contracts, retaining unverified original-pixel equality.
Combined acquisition/stimulus throughput and eventual closed-loop operation remain
separate full-load acceptance procedures.

## Tracking native/runtime handoff (2026-09-30)

Tracking code and lightweight local tests are present; scientific/full-workload
acceptance remains pending. Follow the executable build/smoke-test commands and explicit
procedures in [Tracking status](tracking.md#windows-execution-handoff). The API 2.0 shim
was not compiled on the development machine at that handoff. The 2026-10-01 rig
audit built it and passed the bounded native smoke; preserve the distinction
between automated Windows checks and full camera/model/closed-loop experiment evidence.

- [ ] Projector participation (V15): compare enabled surfaces against all-output
  calibration for each required subset; confirm disabled outputs own no rendering
  windows and surviving viewports/meshes/masks/weights remain unchanged. Retain valid
  pacing selection; test pulse-off with inactive/missing stored target, pulse-on on
  a different enabled display, and verify patch placement/observed edges independently. Verify corrected frustum orientation against measured
  rig corners; local matrix tests do not establish optical accuracy.

## Camera no-wiring anchoring

Oct16 owner confirmation: hardware pulse wiring is verified and all planned camera
recordings will be externally triggered. This is owner-supplied wiring evidence;
the remaining checks below concern retained channel identity, source correspondence
and loss accounting. Historical free-running runs retain their original scope.

The Oct21 [A09/A10 design](../docs/architecture/acquisition.md#a09) supersedes the
first-trigger/first-video-source assumption for continuous acquisition. Runtime
implementation is pending. Retain existing wiring/rates; no ExposureActive wiring
or coded trigger phase is selected. Historical trial-only tests do not validate
the new capture lifetime or boundary correspondence.

- [ ] After implementation, verify usable frames before Setup Ready and uninterrupted
  camera pulse phase/capture across Ready and repeated trials/gaps, with no non-trial
  video frames. Verify Trial state LOW outside trials, normal trial-only closure,
  and actual device/pulse stopping on Cancel Setup, session end, Abort and faults.

- [ ] Verify saved camera-trigger and Trial-state routes and select rising edges in
  the measured HIGH interval (start inclusive/end exclusive);
  retain original OneBox files/meta and camera/native timestamp/counter descriptors.
  SpikeGLX saving begins after Setup capture: its first pulse is not the acquisition
  origin. Verify boundary matching with native generation/counter/timestamp context.
- [ ] Resolve encoded frame zero to its actual source using video_frame mappings;
  inspect leading invalid images and recording losses (plus padding for historical
  schema4 files). Do not pair it automatically with the first in-gate pulse.
  Include exposures before the rising gate and in-gate exposures received after
  recording cutoff; report unmatched pulses/frames and ambiguous correspondence.
- [ ] Inspect timing/count consistency at beginning/middle/end under normal repeated
  trials and combined load; map sequential video indices through source identity and
  distinguish source loss from encoding loss. Historical duplicates retain their labels. Native counter gaps are interpreted
  only under their retained semantics. Good fit does not independently prove offset.
- [ ] Retain mismatches, missing frame/pulse evidence, interrupted trials and
  unknown intervals for owner review. Validate a stronger anchor if required;
  do not add wiring, reset counters or change cadence as part of this check.

Method and provenance are specified in the
[camera-clock contract](../contracts/acquisition/camera-clock.md#no-wiring-anchor-scope).


## Always-saved scientific evidence

Local implementation under [A07](../docs/architecture/acquisition.md#a07) and
[E13/V12/V28](../docs/architecture/visual_stimulus.md#e13) has passing host tests;
these checks remain native acceptance, without wiring or trigger-cadence changes.

- [ ] Verify V13 provenance in a native saved recipe: nonempty renderer-source/shader
  hashes and actual per-output GPU/driver strings, with recipe bytes/digest matching
  the prepared handle. Repeat after a controlled software release change; retain
  referenced external asset/calibration versions. Oct16 local serialization/context
  fixtures pass; native driver observations and performance remain unmeasured.
- [ ] Run video On → Off → On across repeated sessions/trials using unchanged saved
  device/trigger settings. For every active camera, retain `_cam_frames.jsonl` in
  both modes; for Visual Stimulus retain `_stimulus_LOG.json` and `_stimulus_frames.jsonl`.
  Disabled cameras and sessionless preview must not acquire recording obligations.
- [ ] With video off, verify no corresponding FFmpeg/NVENC probe/child, camera video
  pixel pool/copy or stimulus review readback/capture allocation. Check required
  metadata identities, native counters/timestamps, invalid images, contiguous source
  IDs, pulse/transport summaries, actual stimulus states/submissions/image selections,
  clipping/feedback intervals and completion against the retained trial cutoff.
- [ ] Confirm camera header schema5 `video.enabled=false`, null video mappings and
  `video_disabled` source dispositions without recording-drop claims; stimulus
  header format6 `video_enabled=false`, empty captures and no encoder-outcome lines.
  Camera video-on retains one mapping per real image; stimulus video retains its
  sequential source/timestamp mappings. Both retain their configured encoding;
  legacy recordings retain their original omission/duplicate interpretation.
- [ ] Exercise normal completion, Abort, pre-T cancellation, required-evidence queue
  exhaustion and storage/sync failure; retain truthful closure/incomplete evidence,
  original deadlines and exact cleanup. Inspect GUI restoration of existing false
  save switches: they disable video while scientific evidence remains required.
- [ ] Retain source revision/settings and native observations. Keep Eye capture,
  physical timing and paired SpikeGLX acceptance within their existing deferrals;
  these checks do not establish an independent first-trigger anchor.

<a id="encoding-test-plan"></a>
## Encoding comparison: CQ16/CQ23, isolated and combined

Prepared Oct14 for the owned-buffer/half-size review changes under
[A08](../docs/architecture/acquisition.md#a08),
[V12](../docs/architecture/visual_stimulus.md#v12) and
[E13](../docs/architecture/visual_stimulus.md#e13). The synthetic encoder portion now has Oct15 dated evidence above; full-path recording/drop and quality acceptance below remain a plan.
Use `tools/encoding_probe.py` for synthetic encoder isolation and read-only collection.
It does not acquire cameras, pulse the MCU, change application configuration or start
an experiment. Full-path capture/drop testing below uses the normal managed app.
Do not rerun the dated Oct13 scripts unchanged: they contain historical bindings,
protocol assumptions and settings restoration logic specific to those sessions.

### Freeze the workload and tools

Use the Windows repository Python3.11 environment, installed FFmpeg/ffprobe pair and
confirmed RTX2080Ti encoding adapter. Preserve original camera/PFS/configuration
settings and the original adopted GUI configuration. Complete normal device/display
readiness first; Eye tests remain pending until its real serial, source format,
trigger line/pin/rate and drain allowance are confirmed. Do not assign these from
another camera or enable Eye merely to fill the matrix. Locomotion Tracking, SpikeGLX
and optical/electrical acceptance stay outside this encoder comparison.

Run in PowerShell from the repository root, while no experiment is active:

```powershell
$Py = (Resolve-Path '.venv\Scripts\python.exe').Path
$Run = Join-Path $env:LOCALAPPDATA ('CephVR2\EncodingTests\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $Run | Out-Null
& $Py tools/generate_contracts.py
if ($LASTEXITCODE -ne 0) { throw 'Contract generation failed' }
git rev-parse HEAD | Set-Content "$Run\revision.txt"
git status --short | Set-Content "$Run\working-tree.txt"
git diff HEAD --binary | Set-Content -Encoding utf8 "$Run\source.patch"
Copy-Item tools\encoding_probe.py "$Run\encoding_probe.py"
ffmpeg -version | Set-Content "$Run\ffmpeg-version.txt"
ffprobe -version | Set-Content "$Run\ffprobe-version.txt"
nvidia-smi --query-gpu=index,uuid,name,driver_version --format=csv | Tee-Object "$Run\gpu-inventory.csv"
$Gpu = [int](Read-Host 'Confirmed RTX 2080 Ti ordinal from inventory')
Copy-Item config\backends\acquisition_config.toml "$Run\acquisition-original.toml"
Copy-Item config\backends\visual_stimulus_config.toml "$Run\stimulus-original.toml"
```

The patch includes staged and unstaged tracked edits; it omits untracked files.
Preserve any additional untracked code used by the run with the evidence. The copied
helper is provenance only; execute it from the repository so it finds the TOMLs.
Confirm the selected FFmpeg/CUDA adapter is the2080Ti from its diagnostics and
observed GPU activity; do not rely on matching numeric indices alone.

Also record the storage volume/free space, power mode, source revision/dirty patch,
real camera dimensions/rates/depth, exposure/gain, stimulus program/seed/duration and
prepared recipe. The half-size setting is file-owned `review_scale_factor=2`; verify
actual prepared dimensions, usually1280x1000 for the previously2560x2000 composite.
Keep p4, unchanged camera resolution, no B-frames, identical fragment cadence,
capture slots and memory bounds throughout. Color Behavior uses4:4:4; Tracking/Eye
mono and current mono stimulus use the explicit grayscale/neutral-chroma chain.

### A. Synthetic FFmpeg throughput (no live app or cameras)

Create a profile manifest from confirmed Setup inputs. For each camera use its
prepared width/height, nominal rate and FFmpeg input format; for Stimulus use the
**reduced composite** dimensions and `rgba`. This helper intentionally supports only
confirmed8-bit `rgb24`, `gray` and `rgba`. Do not downgrade a higher-depth source to
make the probe run; that row needs a separately verified matching input/codec path.

This command prompts for the values rather than guessing camera dimensions/rates:

```powershell
$Sources = @('behavioral', 'tracking', 'stimulus')
# Add 'eye_tracking' only after its configuration is confirmed.
$Profiles = @{}
foreach ($Source in $Sources) {
    $Profiles[$Source] = @{
        width = [int](Read-Host "$Source prepared input width")
        height = [int](Read-Host "$Source prepared input height")
        fps = [double](Read-Host "$Source nominal fps")
        input_pixel_format = Read-Host "$Source prepared format (rgb24, gray or rgba)"
    }
}
$Profiles | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 "$Run\profiles.json"
```

The tool copies each source's current TOML output arguments and overrides only CQ
in memory. It records the full command, profile, tools, elapsed time, FFmpeg progress,
stderr, file size, external decoded count and full software-decode result. It runs
without `-re`: requested frames divided by elapsed wall time estimates available
throughput, including synthetic generation and startup. Decode checks run only after
all concurrent encoders finish. Each output directory must be new. Validation errors
(including decoder error output despite exit0) suppress the throughput result.
Collector errors produce a saved summary and nonzero exit; successful collection
is still not acceptance—inspect final accounting and match timing records to trials.

Run a separate10s all-source warm-up, then three60s measurements of each source,
all confirmed cameras, and all confirmed sources. Eye is included only if it was
explicitly added to `$Sources` after readiness. Repeat2 reverses CQ order. Every
row gets a unique directory; stop on failure and inspect its retained summary.

```powershell
$CameraSources = @($Sources | Where-Object { $_ -ne 'stimulus' }) -join ','
$AllSources = $Sources -join ','
& $Py tools/encoding_probe.py bench --profiles "$Run\profiles.json" --sources $AllSources --cq 16 --gpu $Gpu --seconds 10 --output "$Run\warmup"
if ($LASTEXITCODE -ne 0) { throw 'Warm-up failed; inspect evidence' }
$Cases = [ordered]@{}
foreach ($Source in $Sources) { $Cases[$Source] = $Source }
$Cases['cameras'] = $CameraSources
$Cases['all'] = $AllSources
foreach ($Repeat in 1..3) {
    $Qualities = if ($Repeat -eq 2) { @(23, 16) } else { @(16, 23) }
    foreach ($Case in $Cases.GetEnumerator()) {
        foreach ($Cq in $Qualities) {
            $Output = Join-Path $Run ("r{0}-{1}-cq{2}" -f $Repeat, $Case.Key, $Cq)
            & $Py tools/encoding_probe.py bench --profiles "$Run\profiles.json" --sources $Case.Value --cq $Cq --gpu $Gpu --seconds 60 --timeout 300 --output $Output
            if ($LASTEXITCODE -ne 0) { throw "Probe failed: $Output; inspect evidence" }
        }
    }
}
```

Combined commands launch the selected FFmpeg processes concurrently, but finish
independently: the faster stream's tail does not remain under full contention.
Compare per-source start/elapsed times and use the full-app timed trial for sustained
combined load. These streams are not synchronized capture or cross-GPU stdin traffic.
The300s timeout bounds each encoder/probe/decode/version subprocess, not the whole
matrix. A timeout or launch/validation failure is not a throughput pass. Synthetic moving
patterns are deliberately reproducible but neither camera noise nor scientific
stimulus content. They cannot establish image quality, native capture drops, pipe
throughput or zero-loss recording. A slow synthetic run takes longer; it does not
simulate real capture drops. File counts must equal the requested counts.

### B. Full application capture/drop comparisons

Launch the managed app through its normal entry point if it is not already running:

```powershell
& $Py -m cephvr.launcher.main --software-root (Get-Location).Path
```

Use the existing GUI Configuration → Setup → Start → normal completion → New Session
workflow, one reproducible60s open-loop trial per row. Keep projectors rendering the
same program at60Hz even when stimulus video is Off. Selecting the Tracking **camera**
does not enable the locomotion Tracking backend. Saving Off still follows the current
implemented scientific-evidence policy; inspect effective settings rather than assuming
that a TOML edit overrides an explicitly saved value. Set each selected source's
complete FFmpeg list in the adopted test configuration to VBR/CQ16 or VBR/CQ23,
then perform fresh Setup. Preserve every other token. If the GUI workflow cannot
update an explicitly saved list, stop and use the existing authenticated configuration
API with a reviewed candidate; do not delete saved configuration or reuse a dated script.
There is no supported one-command CLI for this live run matrix in this helper.

| Row | Enabled cameras | Stimulus video | CQ comparisons |
| --- | --- | --- | --- |
| Behavior only | Behavior | Off |16,23 |
| Tracking camera only | Tracking | Off |16,23 |
| Eye only | Eye, when ready | Off |16,23 |
| Stimulus only | None | On |16,23 |
| Cameras together | All confirmed cameras | Off | all16, all23 |
| Full combined | All confirmed cameras | On | all16, all23 |
| Intended mixed setup | All confirmed cameras | On | Behavior/Tracking16; Eye/Stimulus23 |

Do one10s warm-up, then three60s measured repetitions per available row/CQ variant.
Use stable camera framing/lighting and repeatable motion where practical; preserve
stimulus seed. Separate scene variation from codec differences when judging quality.
Capture actual FFmpeg command lines and adapter identity **during** each trial:

```powershell
# Use a distinct label for every row/CQ/repeat, e.g. full-cq16-r1.
$Label = 'full-cq16-r1'
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'ffmpeg.exe' } |
    Select-Object ProcessId, CreationDate, CommandLine |
    ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 "$Run\$Label-processes.json"
# In a second terminal, first set $Run and $Label to the same values above.
# Start before the trial; stop with Ctrl+C after completion.
nvidia-smi --query-gpu=timestamp,index,uuid,utilization.gpu,utilization.encoder,memory.used --format=csv -l 1 |
    Tee-Object "$Run\$Label-gpu.csv"
```

Before measured runs, verify renderer stderr collection emits one pure JSON
`event=recording_metrics` summary per recording thread. Capture **renderer** stderr;
redirecting the launcher alone does not establish child-handle inheritance. If no
summary is collected, label timing unavailable and fix capture before timing comparisons;
never infer zero latency from an empty log. Timing emission is local-test verified,
but native stderr routing remains a rig check. App runs provide readback/queue/pipe
metrics; the synthetic subprocesses do not.

### C. Collect and interpret every completed run

Close the trial normally before full decode/probe. Point at that run's actual session
recording directory, and at the UTF-8 renderer stderr file collected for that run:

```powershell
$SessionDirectory = Read-Host 'Actual completed session recording directory'
$RendererLog = Read-Host 'Renderer stderr UTF-8 log path for this run'
& $Py tools/encoding_probe.py collect --directory $SessionDirectory --diagnostics $RendererLog --output "$Run\$Label-summary.json"
```

The collector is read-only and recursively finds MP4s and frame logs, including logs
with no video. Missing completion, malformed/truncated logs, decode failures and
missing diagnostics must remain unknown/failure, never zero drops. Match diagnostic
`evidence_path` to the correct session/trial; an stderr file can contain several trials.
A collector exit alone is not a pass: inspect its `errors`, each decode/probe status,
`completion_present` and final accounting. JSON is the retained machine-readable result.

For each source/row/CQ/repeat, record these columns in the owning report:

- Actual command, source representation/rate, encoded dimensions/format/depth, CQ/p4,
  physical GPU UUID, workload, duration, file size bytes and file bitrate
  (8 × size_bytes / duration_seconds, in bits/s; includes container overhead).
- Camera source counts: `received_frames`, invalid images and source dispositions
  (`capacity_drop`, `invalid_image`, `video_disabled` separately); retain raw dropped
  flags and completion transport counters. Schema5 camera images are sequential with
  zero duplicates; count historical schema4 same-slot omissions/padding separately. Missed camera transport frames require
  native counters; nominal rate minus received count is not an independent loss proof.
- Stimulus: authoritative final `encoder_outcome` capacity-drop, selected-real,
  input-submitted/encoded and unresolved counts; Header6 legacy same-slot-omission
  and synthetic-duplicate counters must be zero.
  Initial capture dispositions are diagnostics only: do not add late update lines to
  admission counts and double-count the same group. Separate render cadence misses
  from recording admission drops; historical padded frames retain their labels.
- FFprobe decoded frame count versus final input-submitted/encoded mapping count;
  complete software decode; normal completion and closure evidence. A playable padded
  video alone is not zero-loss capture. Missing/contradictory evidence invalidates the row.
- Timing aggregate count/total/max for ready/pending readback polls, capture readiness,
  queue wait, normalization, pipe-call duration, full-frame input and slot lifetime;
  average=total/count when count>0. Retain bounded worst-stage group/slot/start/end
  examples and any unfinished input span. For startup, correlate these with T, the
  dropped source group and encoder first-input/progress. Frame-input span includes
  time between zero-progress calls; its attempt counts distinguish repeated pipe
  unavailability from a long gap with few calls, without alone proving an OS cause.
  Also retain peak/current slots, zero-progress writes and submitted bytes. Readback
  polls include mapping/copy/cleanup; individual pipe-call time excludes async OS wait.
  No percentiles can be recovered from these aggregates; zero-progress calls are not drops.
  Compare the accounted capture CPU/GPU reservations and separate evidence queue with
  measured full-process/driver/encoder peaks before retaining a different slot default.
  The restored3-slot default and archived15-slot override remain distinct test settings.

Target zero recording capacity drops/unresolved captures, truthful duplicate accounting,
normal closure and preserved nominal presentation. Throughput below nominal is a clear
failure; throughput above nominal does not itself establish adequate full-workload
headroom. Oct15 current-calibration 900-second recording has one startup capacity drop
at 0.2947451 seconds, peak slots 15/15 and maximum slot hold 261.51 ms, with none
unresolved and no later capacity drop. The separate lossless-camera 60-second run has
zero stimulus capacity drops. These results do not close zero-drop/burst-headroom
acceptance; any future claim requires measured evidence, not a speculative queue increase.
Compare all three repetitions and visual crops at identical display scale,
including motion/edges/low contrast. CQ16/CQ23 file size and acceptability are measured,
not assumed. Owner evaluates whether to retain the temporary Eye/Stimulus CQ23 values;
CQ16 remains the standard. Keep existing buffer sizes and remaining optimizations
unchanged until these measurements identify the bottleneck. Restore the original
adopted configuration/default files after testing through the normal configuration
workflow, preserving the resulting evidence and explicit owner decisions.
