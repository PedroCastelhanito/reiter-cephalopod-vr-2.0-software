# Acquisition status

Oct26 camera preview preparation is independent under A10rev73: each existing
reader owns private copy, SDK conversion, channel order and viewport resampling;
native window operations remain shared. One in-flight operation per viewer and
final identity/lifetime/view checks reject stale work.181 local preview/platform
and two native tests pass, including deliberately blocked first-camera preparation
while a second viewer becomes ready. Earlier G01rev337 themed/icon-free captions
and byte-identical8-bit optimization remain. Actual final live FPS and full-load
acceptance remain unverified.
[Assessment](runtime.md#native-camera-captions-and-preview-pacing--2026-10-26) ·
[Current evidence](runtime-evidence-2026-10-26/independent-preview-preparation/context.md).


Oct26 `failed-setup-retired-report` is resolved under
[E06/E08](../docs/architecture/system-contracts.md#e06). Exact cancelled Setup Ready
retains factual attachment ownership for Cleanup without advancing readiness.
Identical replay after cleanup cannot reattach released resources; changed identity,
revision, attachments or original-deadline mismatch still reject. Owning143 tests
and full backend2676 pass. Native GPU88/1 rejection with the saved Behavioral camera
settles cleanly; after exact limit restoration, a distinct fresh Setup reaches Ready
and CancelSetup confirms cleanup. No trial or codec/trigger changes occur in that
probe. One conservative admitted-Setup fencing notice remains in stderr; its exact
child-to-session mapping was not captured, and it is not suppressed. The prior failed
probe is recovered through the normal file-preserving action. Subsequent Visual
Stimulus-only retirement repairs and successful native lifecycle verification are
recorded in that backend's report.
[Current evidence](runtime-evidence-2026-10-26/lifecycle-followup/).

Oct26 `repo-cleanup-and-code-review`: Astra/Luna source review found no additional
safe runtime dead-code removal or ownership simplification. Two unchanged recording
fixtures now live in the owning test support module instead of being imported from
another test module ([ARCH-002](../architecture.md#arch-002)); scenarios are retained.
The final local non-rig suite passes819 acquisition cases. Two additional synthetic
native preview checks pass across acquisition/platform; this does not close device
or full-workload acceptance. [Review evidence](runtime-evidence-2026-10-26/repo-review/).

## MCU release during shutdown — 2026-10-26

The post-session MCU-release warning is fixed under [A11](../docs/architecture/acquisition.md#a11)
and [E08](../docs/architecture/system-contracts.md#e08). Session cleanup already
acknowledged Close and cleared the logical claim; process teardown redundantly
sent another Close after controller exit. ControllerMicrocontrollerClient.close
now returns when no claim remains. Failed/uncertain Close still retains the exact
claim and original deadlines; controller exit is never treated as release proof.
ARCH-002: two-line guard in the existing client, no new state/dependency/order rule.
156 acquisition teardown/coordinator/cleanup checks pass, including absent and
acknowledged claims and retained failure evidence. Ruff/format, Win32 mypy and
boundaries760/zero pass.

Fresh native dummy session ran45seconds with Behavioral30Hz and Tracking60Hz
trigger streams. Stop returned Configuration with cleanup_confirmed/no errors;
normal ShutdownApplication succeeded, all managed processes exited, and final
stderr contains no MCU warning. Both config files restored byte-for-byte. This
bounded reproduction verifies the warning fix, not full-duration/optical timing
or recording-decode acceptance. Earlier process-inspection/bool_dealloc findings
remain separate. [Evidence](runtime-evidence-2026-10-26/mcu-release-fix/context.md).

Oct26 `camera-preview-hover-caption`: revised under [G01](../docs/architecture/gui.md#g01)
revision332 after owner screenshots showed image shrinkage and unused frame space.
Camera windows stay borderless; a28px drag/close strip is painted onto the private
preview output only. Hover changes no window/client geometry or viewport transform.
Native move/close is dispatched from the strip; image wheel/pan/reset remains below.
Initial chrome removal is followed by client sizing/placement before reveal; GUI
camera slots reserve no caption space. No recording/source pixels change.
ARCH-002: replace the existing caption helper behavior and reuse viewport rendering;
no new dependencies, callback subclassing or process ownership.
171 platform/acquisition tests pass, including actual native HighGUI client/outer
bounds invariant across hover, overlay-X closure without stopping producers, and
wheel/pan/reset.16 GUI frame/placement checks pass. Ruff/format, Win32 mypy three
owners and boundaries760/zero pass. Current running trial not restarted; live-session
pointer dragging, alternate DPI and full-load acceptance remain pending.
[Checks and limitations](runtime-evidence-2026-10-26/overlay-caption/context.md).


Oct26 `preview-run-encoder-closure-warning`: fixed missing recording-helper resource
proof under [A08](../docs/architecture/acquisition.md#a08) and
[E08](../docs/architecture/system-contracts.md#e08). Worker recycling retains the
exact encoder launch ID only after terminal session and confirmed encoder cleanup;
output durability remains independent. Existing supervisor proof checks remain
unchanged.817 acquisition tests and201 focused acquisition/rendering/recovery tests
pass, including unconfirmed-output versus released-process regression cases.
Native81.87s behavior recording stops with confirmed cleanup; warning does not
recur after GUI reconnect. Full ffprobe decode2456/2456 frames matches frame-log
completion with no failed/missed buffers. Final44.47s rerun also confirms cleanup/no retained errors and fully decodes
1334/1334 frames matching its frame log. User-approved authenticated takeover
resolved UI-input timeouts; normal shutdown succeeds, zero runtime processes
remain and original settings are restored byte-for-byte. Previous warning
evidence remains historical.
[Evidence, checks and limits](runtime-evidence-2026-10-26/recorder-fps-fix/context.md).

Oct23 `no-recording-dummy-session`: implements the owner-requested
[E04](../docs/architecture/supervisor.md#e04) all-recording-Off exception.
[Current validation and limits](runtime.md#no-recording-dummy-session--2026-10-23).


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

Oct21 `preview-20hz`: [A03](../docs/architecture/acquisition.md#a03) revision35
and [A10](../docs/architecture/acquisition.md#a10) revision72 implement G01's display
cadence and raise the session publication default to20 Hz. Pending newest frames
wait through the existing native event loop; close/placement handling stays active.
Publication advances fixed cadence slots so a30 Hz source can supply20 Hz rather
than falling to15. Explicit lower caps/zero remain supported; the owner's saved10
was updated to20. Capture/recording/Tracking delivery stays independent.
The combined373 local checks pass (shared invariants, manual preview, worker
foundations and stimulus rendering); static checks pass. Native live cadence was
not measured. ARCH-002 retains focused owners and one shared pacer, no dependency.

Oct21 current rig validation: two-camera normal60s → no-camera-demand/video-Off
Abort5s → normal60s passes; all camera videos fully decode with exact logged counts.
MCU PING recurs during full-texture Setup (114.451ms/99.979ms), followed by
unconfirmed cancellation cleanup. This is new native failure evidence; earlier
bounded passes do not close it. No firmware/deadline/retry change. See the
[current combined assessment](runtime.md#current-rig-validation--2026-10-21).


Oct21 `preview-frame-details`: [A10rev71](../docs/architecture/acquisition.md#a10)
implements advisory source/preview FPS for open native camera viewers. Existing frame
IDs and acquisition timestamps measure source rate despite viewer skipping; only new
imshow images count as preview updates. One queued callback and one in-flight exact-
reader report bound delivery through existing visibility state. Hide/retirement clears
GUI evidence; cancellation keeps optional telemetry out of close waiting. No capture-
worker traffic, scheduling, policy defaults or recording changes. ARCH-002 keeps
measurement in a small shared helper and native-view ownership in PreviewWindows.
Focused tests cover counter reset/stall, bounded delivery, retired readers and reordered
visibility; LOG records validation. Native camera rates remain unverified after restart
under E15.

Oct21 `setup-watchdog-cleanup`: a real missing Eye camera exposed a worker failure
that left Setup waiting for successful readback adoption. The coordinator now joins
exact terminal resolution results under their original deadline before failing,
retaining sibling readbacks before scope retirement. No retry, timeout or stale
evidence rule changes. Missing-camera failure/cleanup, Ready cancellation, recorded
10s Abort, fresh Setup/Start and60s two-camera normal closure pass on the rig;
camera videos fully decode with matching counts. Original settings/history restore
exactly. The disconnected Eye and intermittent MCU PING cause remain open; no
continuous-capture implementation or firmware change is included. See the
[current combined assessment](runtime.md) and
[evidence](runtime-evidence-2026-10-21/setup-recovery/output-verification.json).

## Continuous camera acquisition design — 2026-10-21

Owner explicitly selected design recording before implementation. Accepted
[A10rev70](../docs/architecture/acquisition.md#a10)/[A11rev52](../docs/architecture/acquisition.md#a11),
with A02/A07/A09 and E05/E11/E12 amendments, supersede trial-only capture.
No runtime, firmware, operator settings or executable policy was changed.
Existing policy22 and lifecycle/wire/schema contracts still encode trial-only
capture and per-trial camera ON/OFF; they require coordinated formalization with
the implementation, not an isolated policy toggle. Repository source inspection
identified coordinator trial preparation/pulses, worker capture/drain/recording
completion and controller evidence gates as affected. Existing independent protocol6
output masks provide the simpler mechanism; no new process or firmware scheduling
protocol is selected. Actual warm-up/continuity and cleanup remain unverified.

The former first-trigger/first-saved-source assumption is superseded for continuous
capture. Pulse/counter correspondence must remain explicit across trial boundaries
and across the later start of SpikeGLX saving; receipt-gated files may omit some
gate-selected boundary exposures. No new physical anchor or timing accuracy is
claimed. Historical SP0003-123824 measurements retain their original scope. Next
work is indexed as `continuous-camera-acquisition`; rig checks are consolidated
under [camera anchoring](rig-verification.md#camera-no-wiring-anchoring).

Oct21 `pilot-spikeglx-alignment-inspection`: SP0003-123824 camera trains match
26979/89933 retained frames plus1/2 logged post-cutoff exclusions; native counters
are contiguous and pulse/native-clock fit RMS is14.85/10.56 us. This supports
camera-to-OneBox correspondence, not calibrated exposure latency or neural-clock
alignment. Shared probe/OneBox sync is absent. See the
[current inspection and evidence](runtime.md#pilot-spikeglx-alignment-inspection--2026-10-21)
and [rig follow-up](rig-verification.md#pilot-synchronization-verification).

Oct20 `setup-watchdog-cleanup` reconnect: manual configuration used the same ownership
error for actual ownership and a same-revision settings mismatch. A01 demand filtering
leaves effective Use flags different from preserved operator selections after cleanup.
A01rev21 permits restoration of only enabled-field differences after local session
cleanup with no owned camera; stale/other same-revision changes and active ownership
remain rejected. Existing owner handles comparison; no parallel configuration state.
Five cases cover clean/pending/owned/device-change/no-session; initial enum fixture typo
and protobuf empty-parent presence issue were corrected. Final80 affected tests pass,
Ruff/format and Win32 mypy pass; native reconnect remains unverified.

Oct20 `setup-watchdog-cleanup` investigation: owner screenshot shows serial watchdog
PING acknowledgement timeout, acquisition readback arriving after Setup/revision
change, and rejected session cleanup. The retained
[emergency report](emergency-495128258860500-e8eeda53-8313-4b04-8346-5d372b0c1296.json)
confirms behavioral-worker INVALID_EVIDENCE escalated as COORDINATOR_HEALTH_LOST;
it also retains spikeglx_stop_unconfirmed=true. A03rev34 now admits device-only cleanup
before worker Setup dispatch, requiring exact session/role, camera release, no expected
attachments/retained producer allocations and no trial/output claims. No fabricated
Ready or release evidence. Post-dispatch partial-allocation recovery remains unchanged
and unresolved. ARCH-002 keeps this bounded predicate in the focused evidence owner;
no new state, helper or dependencies. Existing cleanup tests add13 acceptance/rejection
cases;149 cleanup/coordinator tests pass outside sandbox (sandbox stalled after the
13 synchronous cases and was interrupted). Initial fixture omitted native ledger
capacity arguments, then corrected. Ruff, format, Win32 mypy and boundary740/zero pass.
The dialog was closed, so detailed chronology is unavailable. Stale-readback guarding
combines cancellation/deadline/revision; the initiating serial cause remains unproven.
No hardware commands, recovery acknowledgement or runtime restart performed.

Oct20 `sdk-transport-warning-applicability` / `camera-session-demand`: implemented
owner-requested [A01rev20](../docs/architecture/acquisition.md#a01),
[A07rev65](../docs/architecture/acquisition.md#a07) and
[E05rev96](../docs/architecture/experiment.md#e05). Basler snapshots mark only
interface-inapplicable counters unsupported; both boundary reads must agree before
suppressing a warning. Null evidence is unchanged. Applicable missing/invalid/reset
counters and failed entire SDK reads still emit field-named warnings. The
[SDK binding](../contracts/acquisition/sdk-mappings.md#transport-summary-binding)
retains the exact USB/GigE mapping and adapter contract.

Controller Setup derives camera demand on a copy: saved video or enabled Tracking
processing keeps a selected camera active. Unsaved/no-consumer cameras reserve no
workers, pulses or files; manual preview does not create demand. Configuration
readback preserves saved Use/device choices while the prepared session records the
effective roles. Active processing cameras retain mandatory metadata with video
Off. Acquisition is omitted if neither cameras nor Trial state are required;
Trial-state-only sessions use the existing pulse scheduler, exact ON/OFF evidence
and original deadlines, without fabricated camera callbacks, producer ends or files.

ARCH-002 review keeps applicability in the existing adapter/counter record and
session selection in the focused controller configuration helper. A small
`trial_no_cameras.py` separates pulse-only evidence from camera aggregation; no new
process, dependency or wire field. Basler's667-line adapter remains its cohesive SDK
interface; trial_lifecycle.py's506 lines retain exact camera evidence joins while
the new responsibility is separate. Owning behavior test modules were extended.

Final acquisition/controller suite:1499 passed,4 skipped,8 deselected; scoped
Ruff/format23 files, Windows-target mypy304 source files, boundary740 modules/zero
violations, contract-stub syntax, governing anchors and whitespace pass. Tests cover
USB/GigE applicability, SDK failures/reset, camera-demand/save/backend matrices,
output/pulse sets, saved selections, no-camera Setup/Ready and pulse-only normal/
Abort lifecycle admission with failed OFF rejection. Sandbox async runs stalled and
were interrupted; one sandbox temp fixture failed, then permitted fixture-only
runs passed. Initial new-test phase enum typo was corrected. No device operations,
firmware upload, managed restart or physical acceptance by this chat.
[Validation/raw logs/source hashes](runtime-evidence-2026-10-20/sdk-transport-counters/verification.json).

The preceding investigation inspected pilot `0001-090932`: all three cameras had
null buffer-underrun/resend fields and zero failed-buffer/missed-frame/resync deltas,
consistent with exact-serial historical USB inventory. Pasted warning UUIDs were not
matched and live SDK reads were not established; this is not recording-integrity
validation. [Preserved raw records/provenance](runtime-evidence-2026-10-20/sdk-transport-counters/assessment.json).
Native acceptance remains in the [single rig checklist](rig-verification.md).

Oct20 `trial-state-runtime-output`: owner observes a near-zero trial channel with
small spikes in SpikeGLX and selects HIGH for the entire trial, LOW on stop/abort.
Source confirmed the old D12 assignment supported diagnostics only. Under
[A11rev51](../docs/architecture/acquisition.md#a11), protocol6 now carries the
independent held-level output in the existing controller serial owner and acquisition
trial-boundary masks. Setup configures/readbacks it, each trial checks the locked
pin, and valid release schedules ON at T and OFF at end; Abort cancels unsent ON
and includes the level in original-deadline cleanup. Free-running cameras can still
use the marker within an enabled acquisition session; camera-free Trial state
support is now covered by the demand change above. Preview masks omit it. Startup, watchdog, stop/claim release and upload
verification require explicit LOW evidence; controller Started/Stopped checks the
selected HIGH/LOW result. No physical timestamp is inferred from an ACK.

Host/wire/lifecycle tests and actual-sketch native adapter cover held HIGH, normal
stop, interruption failure fanout, stale-start rejection, preview separation,
watchdog LOW, unchanged-camera continuity, pin conflicts and bounded full replies.
The AVR build passes (14080 flash bytes,1285 global SRAM bytes). Final exact commands,
results, source hashes and failed attempts are in
[verification](runtime-evidence-2026-10-20/trial-state-runtime-output/verification.json).
The existing preview-transfer test doubles lacked the production deadline keyword;
corrected those fixtures while retaining their release assertions. No production
tracking behavior changed. ARCH-002 review retains cohesive single-serial ownership
in owner.py/device.py and cleanup.py's existing stop-proof join; the added mask/state
uses their current interfaces, with no new module, dependency or process. Size
advisories remain, with zero dependency-boundary violations.

Owner-authorized managed deployment on2026-10-20 now passes: fresh exclusive runtime,
data-preserving startup recovery, verified application upload on COM8 and fresh
CAPS6 / `cephvr2_uno_6` with stopped outputs. The prior controller endpoint was
stale and its exit receipt absent; recovery explicitly retains that uncertainty,
without deleting prior scientific files or fabricating exit proof. SpikeGLX was
confirmed acquiring/not saving before testing.

Two bounded native sessions physically verify D12 on SpikeGLX OneBox0/channel0:
normal HIGH lasts60.00231s (median4.88176V), then LOW; early Abort ends HIGH after
3.37917s, then LOW.2,514,552 unique samples at30303Hz cover82.9803s with no missing
sample intervals or HIGH dropouts. Settled100ms-to1s stop windows measure
0.00198–0.00702V. Initial unconfigured/reset intervals and edge transients are
retained (up to1.96V outside HIGH), not labelled steady LOW. Both sessions confirm
cleanup; original runtime configuration and saved bytes are restored. Tests used
existing Behavior saving/stimulus settings with SpikeGLX pairing temporarily off;
SDK streaming supplied independent electrical evidence without changing remote saving.
[Physical assessment](runtime-evidence-2026-10-20/trial-state-runtime-output/signal-assessment.json),
[upload/commands/limits](runtime-evidence-2026-10-20/trial-state-runtime-output/verification.json).
Preview, configured intertrial gaps, watchdog and full-load/timing acceptance remain
in [rig verification](rig-verification.md#managed-device-gui). The earlier tiny spikes'
physical cause was not independently reproduced.

Oct19 `gui-full-rig-test`:600s paired Gaussian run under A07/A08/A09 saves
17986 Behavior,35973 Tracking and35973 Eye frames. All camera accounting is complete,
including post-cutoff disposition; zero received-frame drops/invalids and contiguous
native counters. Every video index/source ID/time association matches; all three
videos fully decode. Behavior is1760×1716 yuvj444p, Eye1920×1200 and Tracking1588×1344
yuvj420p, full-range BT709 tags. Durations599.533333/599.55/599.55s follow actual
frame count divided by nominal30/60Hz under A08; no padding is required. Tags/decode
do not prove lossless pixels or calibrated color. Exact planned file set and resource
fingerprints pass. Original runtime/saved bytes restored and all cameras closed.

Early/middle/late Eye/Tracking videos are nearly black, consistent with prior paired
recordings. Supported image-only diagnostics then acquired five native Mono8 Tracking
and five BayerRG8 Eye frames using unchanged saved device settings and trigger pins.
Tracking mean is approximately0.000011 and Eye0.00256 on0–255 scale, with at least
99.9986%/99.9481% zeros. Thus missing scene content already exists before conversion
and NVENC; physical cause remains unknown. Exposure/lighting were not changed.
Operator scene/illumination/lens verification remains required; this workload cannot
establish representative detailed-image encoding capacity. Diagnostic retry/closure
and temporary camera-role/pulse assignment restoration are confirmed.
[Output assessment](runtime-evidence-2026-10-19/gui-full-rig/native-assessment.json),
[exact associations](runtime-evidence-2026-10-19/gui-full-rig/association-assessment.json),
[raw input statistics](runtime-evidence-2026-10-19/gui-full-rig/native-image-assessment.json),
[verification and limits](runtime-evidence-2026-10-19/gui-full-rig/verification.json),
[remaining acceptance](rig-verification.md).

Oct19 `camera-finalization-stimulus-timing-check`: reproduced early-Abort failure
with native all-three-camera recording, including a fresh current-source run.
Diagnostics prove device generation stopped, OFF applied,150ms margin confirmed and
SDK queue drained; SDK shutdown crossed the250ms activity deadline by2.7/16.5ms.
The worker incorrectly capped accounting at that activity deadline. Under
[A10rev69](../docs/architecture/acquisition.md#a10), A07/A08/A09 and E05/E06,
Stop/Interrupt now acknowledges proven activity stop promptly, then retains the same
capture continuation and original Finished deadline for SDK drain/accounting.
The no-writer work scope stays live until Finished, including Cleanup handoff;
post-ack drain errors still propagate. No timeout, margin, config, output format,
dependency or process added. ARCH-002 retains focused capture/finalizer/executor
ownership; existing capture/execution size advisories reflect cohesive ownership.

Fresh corrected runtime: two early Abort/reuse cycles and a60s normal trial save
all3 camera videos plus stimulus. All27 planned output results are Closed; all9
camera completions have complete in-trial/post-cutoff accounting and APPLIED ON/OFF.
No received-camera drops, invalid rows or native-counter gaps; exact source/video
mappings, identities and counts pass. All12 MP4s fully decode. Abort-to-session-end
is0.363739s/0.360223s, with cleanup and NewSession confirmed after each run. Normal
completion also confirms cleanup; later normal execution passes both retired trial
end times. Owner-authorized Abort of Desktop DUMMY_2-163814 also succeeds. Original
saved configuration bytes and authoritative runtime configuration are restored;
final runtime is Configuration/cleanup confirmed.1002 owner/controller/renderer tests
(3 deselected), scoped Ruff/format4, Win32 mypy41, boundaries736/zero and scoped
whitespace pass. Dated raw copies, hashes, commands and limitations:
[verification](runtime-evidence-2026-10-19/camera-timing-verification/verification.json),
[native artifacts](runtime-evidence-2026-10-19/camera-timing-verification/fixed-run/native-assessment.json).
Historical failures retain their original uncertainty. Full-load Tracking/SpikeGLX,
instrumented timing, forced cleanup/finalization races and idle300s/fault matrices
remain in the [single rig checklist](rig-verification.md).


Oct19 `pre-experiment-output-audit`: read-only inspection of four retained Desktop
open-loop sessions (DUMMY_2-152638/155008/160507/160948), governed by
[E04](../docs/architecture/supervisor.md#e04),
[A07](../docs/architecture/acquisition.md#a07) and A09. All planned files exist;
all JSON/JSONL parse with complete final lines. Camera IDs, contiguous source and
encoded mappings/counts agree; no logged dropped/invalid images or native-counter
gaps. All four Behavior MP4s fully decode, match mapping counts and retain exact
session/trial/role/device tags. Eye/Tracking video was explicitly Off; their required
source logs exist, but images cannot be recovered from those logs. Tracking processing
and SpikeGLX were not participants in these open-loop sessions.

Closure remains a pre-experiment blocker: 152638 retains four Unconfirmed acquisition
outputs and Behavior post-cutoff accounting=false; startup recovery did not certify
scientific closure. 155008 has Failed Eye-log closure and Eye post-cutoff=false.
160507/160948 report all outputs Closed with post-cutoff proofs true; their short
Abort runs do not resolve the separately reported unavailable 161258 recurrence.
Abort-to-session-end is40.008s,0.345s,0.331s,0.332s respectively. Keep the existing
`interrupted-finished-abort-proof` task open. No original recording was modified.
[File hashes, commands, frame counts and assessment](runtime-evidence-2026-10-19/output-audit/assessment.json).
No new hardware, durability, optical/electrical or full-experiment acceptance.


Oct19 DUMMY_2-161258 recurrence: supplied Interrupted Finished keys/paths match;
video=Unconfirmed, frame log=Closed. Read-only completion inspection found1934
Behavior admitted/recorded frames but post-cutoff accounting=false; Eye/Tracking
post-cutoff proofs=true. A02rev34 retains exact Unconfirmed results without normal
Finished or successful cleanup discharge.4 baseline cases reproduce rejection;258
coordinator/trial/recording/controller tests pass. Updated tests explicitly retain
the cleanup closure guard. Ruff/format2, Win32 mypy1, boundaries734/zero pass.
ARCH-002 keeps the existing validator and owning test module, no new dependency.
Native drain cause remains unresolved. Session directory became unavailable during
subsequent evidence capture; no deletion or modification was performed by this task.
No live restart/recovery/native pass claimed. Existing native Abort task stays open.

Oct19 `abort-late-report`: DUMMY_2-152638/152649 Abort15:28:10.424358 to
session-end15:28:50.432230 retained the screenshot rejection in the supervisor
emergency record, attributed to acquisition_behavioral_worker. The session log
has command/lifecycle events, not the rejected operation RPC. Its command ID/kind
and exact lateness cause cannot be recovered from these records. Behavior post-cutoff
accounting is incomplete; Eye/Tracking accounting complete; central acquisition
outputs remain UNCONFIRMED. Historical recordings/metadata must retain those states.

Fixed the reproducible rejection/escalation mechanism under [A02](../docs/architecture/acquisition.md#a02)
rev33 and [E06](../docs/architecture/system-contracts.md#e06): exact late complete
StopTrial/InterruptSession/Cleanup/Shutdown/RecordPulseEvidence status for the matching
interrupted session is retained without camera readback or parent-success relay.
Source generation, child ID, work, revision and command-kind matching remain mandatory.
Active sessions, progress-only reports, readback and stale contexts remain rejected.
Retained ingress time still makes wait_child_operation raise its original timeout;
status alone cannot close files/release resources. Rejection messages now identify
worker generation, command name/ID, completeness and ingress timestamp. No new
policy duration, process, retry or dependency. ARCH-002 extends the existing small
operation-evidence owner; unchanged large-module advisories do not require extraction.

Five valid late reports fail the old handler with the screenshot error;346 current
coordinator/worker/trial/recording/controller tests pass. Ruff/format2, Win32 mypy1,
boundaries730/zero pass. Initial verification found all11 original files unchanged.
Diagnostic restart then used Start recovery: only SESSION_LOG.jsonl changed among
those files (administrative recovery event); other10 retain size/mtime and config
SHA256 matches. Setup with restored configuration failed before Start: cannot import
ReviewLayout from visual_stimulus.config.models.artifact_models during concurrent
composite-preview work. GUI remains in Configuration; no native Abort occurred.
The346 focused tests passed again. This establishes the
local rejection bug, not unique original command attribution or a native closure pass.
Fresh native Abort and underlying late-drain cause remain in interrupted-finished-abort-proof
and the [rig checklist](rig-verification.md). [Read-only evidence and verification](runtime-evidence-2026-10-19/abort-late-report/assessment.json).

Oct19 `interrupted-finished-abort-proof`: repaired a reproducible terminal-drain
failure under [A10](../docs/architecture/acquisition.md#a10) rev68,
[A07/A08/A09](../docs/architecture/acquisition.md#a07) and
[E06](../docs/architecture/system-contracts.md#e06). A fresh control wake or pending
Cleanup during drain previously called SDK StopGrabbing with unfinished accounting.
The video result became UNCONFIRMED, the exact Interrupted Finished guard rejected
it, and aggregate cleanup could wait to its deadline. The isolated committed stop
method fails all three new-wake regressions (stage, StopTrial, InterruptSession);
the repaired path yields and resumes successfully. This establishes the local bug,
not the exact unretained command sequence of historical DUMMY_2-150713.

Trial drain now keeps the stopped generation, admission cutoff, first stop observation,
fixed margin end and original deadline across control handoffs. It services control
without SDK queue flush or premature end-marker sealing, then resumes with retained
purge counts/native counters. Cleanup waits for this continuation; Stopped is emitted
once, independently of final file closure. A deadline/failure still produces truthful
incomplete evidence, never an upgraded success. Preview cleanup retains its existing
nonresumable contract. The recording writer still drains admitted frames, completes
encoding, syncs/closes video/frame log and returns exact output evidence; no new
output format, timeout, policy choice or weakened coordinator guard.

ARCH-002 extracts native purge and capture-drain continuation from the oversized
adapter/capture modules into focused helpers with explicit resource/callback/clock
inputs. The667-line adapter remains SDK device/configuration ownership; the601-line
capture owner retains buffer/window/resource ownership. Single-owner trial state
retains the first stop timestamp and publication flag, reset with each trial.
No whole-runtime reference, process, dependency or per-frame logging added.
Owning behavior modules were extended, including real serialized Stop/Interrupt plus
Cleanup arriving during drain, single stop evidence, exact cutoff/deadline retention,
cumulative partial purge and expired-deadline failure. Existing saved-file sync/
closure, failed/pending file writes, duplicate outputs and cleanup guards remain tested.

Validation:748 acquisition/controller lifecycle tests pass/2 deselected; final26
handoff/purge/preview cases pass. Scoped Ruff/format10, Win32 mypy55 and boundaries730/
zero pass; focused decision/link checks and whitespace pass. Earlier refactor run
found5 fake-SDK/clock-binding failures (264 passed); corrected before final runs.
Initial269- and689-case runs passed before final extraction/additional coverage.
[Source-hashed verification and before-fix reproduction](runtime-evidence-2026-10-19/abort-finalization/fix-verification.json).
Fresh native camera stop/encoder/cleanup/NewSession timing remains in the
[single rig checklist](rig-verification.md). Reopen the managed application to load
this repair; no live restart, hardware command or fresh rig pass was performed.

Historical DUMMY_2-150713 Abort15:07:57.204988 to session end15:08:37.231697 took
40.026709s. Saved camera completions have complete in-trial counts/APPLIED ON/OFF
but incomplete post-cutoff accounting; camera closure remains UNCONFIRMED while
stimulus outputs are CLOSED. Behavior/stimulus MP4s fully decode; Tracking/Eye
videos were not planned. Decodability does not certify accounting/durable cleanup.
Those scientific files, reservation and metadata were not changed/recovered/deleted.
[Original read-only evidence](runtime-evidence-2026-10-19/abort-finalization/assessment.json).

Oct19 `action-progress-logging`: manual camera Connect/Disconnect reports action
detail through the existing lifecycle channel under [G02](../docs/architecture/gui.md#g02),
[A10](../docs/architecture/acquisition.md#a10) and the
[preview contract](../contracts/acquisition/preview-control.md). Settings, buffers,
arming/free-running start, external ON, first-frame waiting, external OFF and release
steps reflect actual execution. One background sender and one replaceable pending
action bound best-effort telemetry without blocking device/safety work. Controller
checks the live child/source/work/deadline and rejects result-bearing or stale action
reports; progress cannot satisfy readback, first-frame or release requirements.
380 acquisition/controller tests pass (1 skip/1 deselected), including nonblocking
coalescence, exact progress scope and no premature Live/success evidence. Scoped
static checks pass; native device timing/cleanup acceptance is untested. The
[runtime assessment](runtime.md) owns complete GUI/static results and limits;
[rig verification](rig-verification.md) owns the live checklist.

Oct19 `abort-pulse-retention`: DUMMY-142302 Abort at14:23:50 retains APPLIED
ON/OFF but incomplete post-cutoff camera accounting; administrative camera closure
remains UNCONFIRMED while stimulus outputs are CLOSED. Source review exposes
repeated Stop/Interrupt safety OFF overwriting the trial terminal outcome and
forwarding a conflicting replacement. Keep the first retained trial OFF immutable
while later safety OFF still reaches hardware and updates live MCU observation.
Failed first outcomes are not upgraded. Existing worker conflict and exact-output
guards remain intact under [A08/A09](../docs/architecture/acquisition.md#a08) and
[E06/E08](../docs/architecture/system-contracts.md#e06).

The prior wake repair covered due stages but missed safety-command entry: StopTrial
and InterruptSession could drain before consuming the already-observed external
wake. Moved consumption before both paths; subsequent wakes and queued commands
still interrupt. Both safety-entry regressions fail before the change and pass
afterward. Repeated OFF tests cover successful and rejected first outcomes.245
owner/lifecycle/pulse/recording-cleanup/admission tests, Ruff/format4, Win32 mypy2,
boundaries724/zero and whitespace pass. ARCH-002 uses the existing two focused
owners, no dependency/state additions; size warnings are outside changed source.
Native wake sequence was not captured, so these reproduced defects do not prove
unique incident causation. No scientific files modified or unknown outputs certified.
[Source/run evidence](runtime-evidence-2026-10-19/abort-pulse-retention/verification.json);
restart and bounded Abort/cleanup acceptance remain in [rig verification](rig-verification.md).

Oct19 `stop-now-wake-drain` / `interrupted-finished-abort-proof`: repaired a
reproduced owner-loop defect under [A08/A09](../docs/architecture/acquisition.md#a08)
and [E06/E08](../docs/architecture/system-contracts.md#e06). An external wake was
consumed only after due-stage processing. A terminal drain inside that stage saw
its own already-serviced wake as pending and aborted, leaving post-cutoff accounting
incomplete. Consume the observed generation before the stage; later wakes and queued
commands still interrupt. Original deadlines, SDK ownership and closure guards remain.
ARCH-002 review: existing owner and evidence modules suffice, no new state/dependency;
boundary size warnings are in unchanged modules, with no new oversized source file.

The saved DUMMY-140646/140658 completion lines have exactly the incomplete post-cutoff
symptom, but the original rejected RPC and wake sequence were not retained. Thus the
wake defect is proven locally, not yet proven the unique cause of that native incident.
Incomplete evidence maps successful encoder exit to UNCONFIRMED, which the interrupted
Finished guard rejects. The guard now returns expected paths plus rejected output keys,
paths, presence, numeric closure and failure text in the existing error response; it
still retains none of an invalid batch. No validation was relaxed.

Regression: old-wake handoff failed before the fix; new-wake case passed. Enhanced
regression exercises real WorkerCaptureResources.stop with a nonzero drain margin:
serviced wake completes accounting; a new wake still interrupts.228 owner, admission,
trial-lifecycle and recording tests pass; scoped Ruff/format, Win32 mypy2, boundary
checker724/zero and whitespace pass. Sandbox asyncio socketpair hung; rerun with
loopback permission passed. Read-only native GUI inspection now works and shows an
already Interrupted session with Abort now awaiting completion and calibration output
windows. No input/restart, configuration change or new rig run was performed; current
processes have not been verified to load this fix. Native Abort/cleanup/NewSession
acceptance remains in the [single rig checklist](rig-verification.md).
[Saved trial assessment](runtime-evidence-2026-10-19/stop-now-investigation/assessment.json)
and [source/test evidence](runtime-evidence-2026-10-19/stop-now-investigation/fix-validation.json).

Oct19 `preview-zoom-pan`: owner-requested left-button drag pans zoomed manual/session
viewer images under [A10](../docs/architecture/acquisition.md#a10) rev67. The existing
viewport clamps enlarged axes at image edges and centers smaller axes; drag at fit
does nothing. Release or motion without the left button ends the gesture, as do
wheel zoom, reset and resize. Cached pixels repaint without another source frame;
camera/recording/tracking coordinates and source pixels remain intact. ARCH-002
extends the existing small viewport and native callback, with no new module,
dependency or duplicated transform state. Existing owning preview suite144 passed
with six pypylon SWIG deprecation warnings, including native down/move/up after
zoom with a stationary generated-image producer, cached-image repaint, double-click
reset and exact cleanup. Unit cases cover square/portrait/landscape bounds, immediate
edge reversal, centered padding, gesture cancellation and source immutability.
Scoped Ruff/format, Win32 mypy2, boundaries724/zero and whitespace pass. No running
application restart or real-camera drag acceptance; full restart loads the feature.
Physical follow-up remains in the [single rig checklist](rig-verification.md#managed-device-gui).

Oct19 `preview-click-and-first-show`: acquisition Win32 viewers now share one
HighGUI/native window thread, with independent frame-event waits. New windows stay
hidden until initial geometry and owner binding are complete, then reveal without
activation under [A10](../docs/architecture/acquisition.md#a10) rev66 /
[G01](../docs/architecture/gui.md#g01) rev239.169 acquisition/Windows tests pass,
including three native generated-image windows with bounded repeated activation/
click checks and hidden initial-size/position assertions.79 GUI preview/Review tests
and scoped static checks pass. Suspected shared-lock/focus deadlock is source-inferred;
no stalled live-process stack collected. No real camera or scientific configuration
changed, no runtime restart or performance claim. [Current assessment](runtime.md)
and [dated evidence](runtime-evidence-2026-10-19/preview-click-first-show/verification.json)
retain implementation, failures and limits. Physical acceptance remains in the
[single rig checklist](rig-verification.md#managed-device-gui).

Oct19 `mcu-upload-recovery`: owner's screenshot reports Arduino upload/verification
exit1 with STK500 sync errors during flash readback. Independent AVRDUDE8 read-only
COM8 backup succeeds: ATmega328P signature1E950F,32768 flash bytes retained. All13874
application-image bytes match the protocol5 AVR build exactly. Live read-only CAPS
reports protocol5 / `cephvr2_uno_5`; STATUS reports all three camera outputs disabled
and stopped, unconfigured with watchdog unarmed. The owner's upload installed the
new image despite the failed verification operation. Do not relabel that operation
successful: original complete tool output/timing is unavailable, and the sync-error
cause remains unestablished. Installed AVR core1.8.8 selects AVRDUDE8.0-arduino.1;
successful independent readback does not implicate this version or prove the GUI
upload path reliable. No new flash, CONFIGURE/ON, diagnostics, application restart or
electrical test in this investigation. No production-code change or automatic retry.
[Dated backup, method, hashes and board replies](runtime-evidence-2026-10-19/mcu-upload-recovery/board-check.json)
retain source revision and limits under [A11](../docs/architecture/acquisition.md#a11)
and E15. Remaining acceptance stays in the [single rig checklist](rig-verification.md#managed-device-gui).

Oct19 `mcu-failed-connect-upload`: owner requests the ability to upload protocol5.
Source-confirmed failed acquisition CONNECT retained its exact device claim after
protocol mismatch, blocking explicit Upload even without an open camera. The
acquisition client now sends exact CLOSE on failed startup under the original
deadline. Only confirmed CLOSE clears the claim; failed cleanup still blocks Upload.
This implements existing [A11](../docs/architecture/acquisition.md#a11) ownership /
release rules without changing policy, active-camera gates or firmware. ARCH-002
keeps cleanup in the existing focused client and extends its owning behavior tests;
no dependencies or new modules. Tests cover mismatch, exact claim/deadline, failed
cleanup fencing, explicit upload admission after release and fresh reconnect.
Focused selection31 passed; MCU owner/manual-device/manual-preview/authenticated
controller RPC regression270 passed,1 skipped,1 deselected. Ruff/format, scoped
Win32 mypy and boundaries723/zero violations pass; existing size warnings concern
other modules and require no extraction for this focused client change. Initial
sandbox pytest emitted setup errors/stalled and was interrupted; permitted loopback
reruns pass. No actual flash, COM access, application restart or electrical test.
Restart the whole application to replace the already-retained in-memory claim and
load the repair, then use explicit Configuration Upload with the protocol5 sketch.
This enables the owner's upload workflow; it does not assert board installation or
close remaining [rig checks](rig-verification.md#managed-device-gui).

Oct19 `camera-connect-continuity`: owner authorizes source implementation under
[A10](../docs/architecture/acquisition.md#a10) rev65 /
[A11](../docs/architecture/acquisition.md#a11) rev50 and explicitly prohibits flashing.
Connect no longer pauses/stops/resumes existing captures or replaces their runs,
rings or viewers. It configures the complete active mask and starts only the new
output after its camera is Ready. Uno protocol5 preserves unchanged outputs' phase,
HIGH/LOW and running state, releases changed old pins before reassignments, and
leaves new outputs stopped until ON. Settings edits retain their existing dependent
capture pause/confirmation/restart path. Exact CAPS compatibility rejects old
firmware; a newly started host therefore requires a later authorized upload before
MCU use. Operator values are preserved; policy4 binds the changed semantics.

Host readback checks the expected running mask instead of requiring every output
stopped. Regressions cover second/third-camera additions, new-camera failures,
unexpected stopped/started readback and protocol4 rejection. The native C++ adapter
executes the actual sketch and checks phase/level retention during both pulse halves,
third-output addition, invalid pin/reply-size rejection, selective settings restart,
pin-swap LOW ordering and watchdog no-resurrection. It models neither ISR latency
nor electrical timing. New test-module responsibility is the native compiler fixture;
existing Python owning modules are extended. ARCH-002 removes the Connect-only
lifecycle binding; the serial owner remains cohesive at584 lines and runtime wiring
only shrinks. Existing edit/transport owners remain separate; no dependency added.

Validation: acquisition/controller1302 passed,4 skipped,7 deselected; final Connect
selection5 passed; explicit compiler-equipped actual-sketch test1 passed. AVR compile
passes (13874-byte program,1199-byte globals); no upload/COM operation. Scoped Ruff /
format26 files, Win32 mypy21 sources, policy loader tests and boundaries724/zero
violations pass. Initial sandbox asyncio stalls are traced to socketpair creation;
permitted loopback reruns pass. Fixed new tracking-field substring fixture and old
protocol4 completion expectation; those initial failures are not runtime defects.
Native continuous captures and electrical continuity/jitter remain unverified in the
[single rig checklist](rig-verification.md#managed-device-gui).
[Dated evidence](runtime-evidence-2026-10-19/camera-connect-continuity/verification.json).

Earlier Oct19 follow-up removed shared MCU pause/configure for internally clocked
camera Connect; its external-mask restart behavior is superseded by the change above.
GUI reconnect layout remains stable without reporting stale frames as live. Focused
checks pass; native transition smoothness remains unverified. [Assessment](runtime.md).

Oct19 preview repairs pass bounded native concurrent Connect, workspace close/reopen,
independent Show/Hide and Disconnect. Session viewers use existing A03 slots under A10;
exact cleanup/NewSession retire their status. Final 120-second three-camera trial,
subsequent Setup/CancelSetup and Shutdown pass. That earlier trial had videos off. Subsequent240-second video-on verification retains
Behavior7193, Tracking14387 and Eye14396 received frames exactly once, with zero native
counter gaps or dropped source frames. DPI repair and bounded validation are in the
linked runtime assessment; native X/individual drag and failure-injected reuse remain open. Native long-filename writer tests pass;
full long-root trial remains pending. See [assessment and evidence](runtime.md).

Current Oct17 [A08](../docs/architecture/acquisition.md#a08) sync repair passes
its primary no-omission/no-duplication criterion at unchanged saved camera quality:
120 s concurrent Behavior 3598/3598, Tracking 7188/7188 and stimulus 7200/7200.
All camera counters and mapping identities are unique, with zero native gaps,
invalid images or capacity omissions in this fixture. Cleanup/NewSession and
normal Shutdown confirm exact output/process closure. An explicit temporary
16-slot stimulus configuration is part of this result; saved three-slot defaults
are restored and are not certified by it.

Periodic video flushes now have one independent exact-file owner, retaining at
most one pending helper. The original cadence and final sync remain. Finalization
joins pending work then performs a distinct post-encoder-exit flush under the
original bound. Pending timeout retains the handle; a completed failure can close
resources without claiming successful durability. Frame-log sync stays unchanged.
Redundant per-frame path reopen stops after exact handle adoption; initial and
final identity checks still reject a replaced/deleted output. Existing accepted
[Windows ownership](../contracts/acquisition/windows-resources.md#ownership-ledger-and-storage-synchronization)
already requires independent single-pending flushes; no policy/default changed.

Experimental pixel-exact runs before the final hot-path guard still omit Behavior
frames (1710/1798 and instrumented 1512/1798), while their normal cleanup confirms.
The profiled flush totals 18.507 s concurrently; it cannot be added to consumer
work. Final source's pixel-exact real-time capacity remains unvalidated. Prior
synthetic prepared-RGB fidelity is not raw Bayer fidelity or a live pixel hash.
The owner prioritizes full frame retention; saved CQ23 is used without arbitrary
quality reduction. Source gaps and retained counts remain separate.

Final backend 2209 passed/5 privilege skips, explicit rig NVOF passed; acquisition
629 passed, owning cleanup 60 passed. Ruff/format, Win32 mypy and boundaries pass.
All three fresh PFS/readbacks and ten settings files match originals, cameras are
closed and the temporary profile hook is removed. Native Abort exact-Finished,
failed-Setup retired reports and older Shutdown findings remain open; normal
closure does not close those separate triggers. [Current methods/results](runtime-evidence-2026-10-17/file-sync-fix/README.md),
[restoration](runtime-evidence-2026-10-17/file-sync-fix/final-restoration.json).

Oct19 `preview-snap-workspace` extends the display-only path under
[G01](../docs/architecture/gui.md#g01) rev231 / [A10](../docs/architecture/acquisition.md#a10)
rev62. Explicit existing-only Snap overrides manual geometry once, then restores
automatic placement. Coalescing retains unconsumed snap intent. A workspace/main
host switch validates the new top-level handle in the already verified live GUI
process; a different PID/lifetime is never adopted. Hidden hosts defer drawing and
retain readers; restore resets the placement baseline without clearing a prior
manual opt-out. No new attachment, capture or image transport. Portable tests cover
snap, coalescing and host changes including while minimized; native Windows remains
pending. [GUI assessment/evidence](runtime.md) records actual local Review scope.

Oct19 `adaptive-preview-grid` refines the [G01](../docs/architecture/gui.md#g01)
revision228 display path under unchanged A10 capture ownership. The
[preview contract](../contracts/acquisition/preview-control.md#backend-owned-camera-windows)
adds existing-only layout hints. The coordinator retains its exact-run reader;
the display thread coalesces copied hints and updates only untouched native
geometry with the same GUI owner identity. Manual move/resize opts out until
reopen; native X is checked before layout/drawing and a completed reader is never
reopened by an automatic hint. Viewport resize preserves zoom and source pixels.
ARCH-002 keeps geometry tracking in a small shared helper and native measurement
in the platform owner. Owning portable tests exercise automatic resize, manual
move/resize preservation, coalescing, no recreation and release gating. Local
Review native evidence and Windows acceptance limits are in [the GUI assessment](runtime.md).

Oct17 `preview-window-follow` updates the earlier `gui-preview-slot` display path
under [G01](../docs/architecture/gui.md#g01) revision223 and
[A10](../docs/architecture/acquisition.md#a10). The optional
[placement owner identity](../contracts/acquisition/preview-control.md#backend-owned-camera-windows)
links the existing HighGUI window to the exact live GUI process/window. It follows
GUI movement, stays above its owner without global topmost status, and retains its
window/reader while minimized. Latest converted private pixels redraw on restore;
minimization never masquerades as native X closure or changes capture/pulses.
Owner loss fails the display only; cleanup detaches and confirms handle release.
No new device/process ownership or image transport is introduced. Legacy unowned
placement retains its prior behavior.

ARCH-002 keeps the native primitive separate from the display-thread lifecycle.
Manual-preview and portable platform checks130pass/2Windows deselected cover
owner identity, move/minimize/restore, retained frame delivery, X/no recreation,
release errors and placement admission. Scoped Ruff/format, Win32 mypy and
boundaries720/zero violations pass. The local Mac Review native result establishes
only Review behavior; Windows-native owner and actual HighGUI/DPI acceptance are
pending under E15. See [current GUI assessment and raw evidence](runtime.md).

Oct16 `camera-timestamp-yellow-preview`: repaired A09/A10 timestamp capability
detection in the existing small metadata owner. Exact documented USB models now
use the fixed 1 ns clock when frequency nodes are absent; readable frequency
nodes still win and unknown models remain unavailable. The
[SDK binding](../contracts/acquisition/sdk-mappings.md#transport-and-metadata-bindings)
owns the model mapping. No new dependency, process or policy setting; ARCH-002's
existing focused owner and adapter behavior test module suffice.

An authenticated controller snapshot confirmed Behavioral serial40065509 released
in Configuration before a bounded exclusive SDK diagnostic. Its acA4112-30uc has
neither frequency node; repaired metadata preparation returns ChunkTimestamp,
1 ns/tick and no warning. Four exposure samples preserve matching chunk/grab
timestamps. This is device-local time, not host/pulse synchronization acceptance.

The yellow image is reproduced in native BayerRG8 capture. All seven sampled
frames match direct Basler BGR conversion byte-for-byte. At25ms,99.885% of red
pixels saturate;5ms eliminates saturation but the scene remains nearly uniform
brown/yellow. Thus no preview conversion defect is observed; optical scene/focus
and suitable scientific exposure/white balance require owner confirmation.
No permanent exposure or white-balance change is adopted. Initial PFS reload
changed only LineSelector context; explicitly restoring its original Line1 yields
byte-exact original PFS, and the camera is closed. Test image mode is Off.
[Native evidence, captures and restoration](runtime-evidence-2026-10-16/camera-preview-diagnosis/sweep.json)
and [initial comparison](runtime-evidence-2026-10-16/camera-preview-diagnosis/probe.json)
retain the actual methods and limits. The SDK probes use temporary software
triggers; they do not validate external triggering or full application restart.

Owning adapter/diagnostic/preview tests pass165 with one native deselection;
scoped Ruff/format, Win32 mypy and boundaries715/zero violations pass.
Existing size advisories concern unchanged owners, not the small metadata edit.
Sandbox SDK enumeration found no device, and async loopback tests stalled;
permitted native/loopback runs completed. Full application restart is required
to load the fix into the already running workers; historical warnings are retained.

Comprehensive Oct15 recheck completes bounded native workloads. Fresh native camera readback differs
from saved configuration: Behavioral4096×3000/3ms versus saved1760×1716/25ms;
Tracking ROI1588×1344 matches; Eye1920×1200 matches but native100Hz/limiter-off
differs from saved60Hz/free-running. Full native PFS and exact saved-file backups
are retained before mutation. Engineering tests explicitly use the saved profile
and restore all three fresh native PFS baselines byte-exact with every original
feature readback matching and camera closed; no new scientific settings are adopted.
COM8 currently exposes an incompatible `three_camera_ttl` command dialect, so
external-trigger preview cannot be accepted. No firmware is flashed. Explicit
unaligned free-running tests disable every MCU output and prove no synchronization.
The controller's retained-port/free-running pulse-report mismatch is repaired with
real owning regressions; native Setup reaches acquisition Ready, then a renderer
resource rejection and long-path cancellation/recovery issue initially block trials.
After focused repairs, native saved-profile/free-running trials complete Gaussian,
reduced-texture arena and video Save On→Off→On cases with real cameras and four
projector outputs. Save-Off produces no videos but retains detailed frame/scientific
logs. All18 videos across seven normal/interrupted trials fully decode/count;
the final isolated two-camera/four-projector workload and exact original PFS/settings
restoration are assessed in [runtime](runtime.md). Camera final CFR outputs have
3/1801 Behavioral and12/3600 Tracking repeats, with zero failed/missed buffers;
this is explicit resampling, not loss-free source capture or synchronization.
An immediate post-Abort60-second trial runs51.8548seconds beyond the retired
boundary without stale-worker/cleanup errors. Both interrupted runs still require
about40.12seconds for metadata settlement; no normal Finished outcome is invented.
Independent synchronous SDK/FFmpeg capacity tests now complete two60-second
CQ23/CQ18 camera+offscreen-shader runs and a separate20-second native4096×3000
Behavioral/grating variant. All nine videos fully decode and counts equal submitted
frames. CQ23 receives1807 Behavioral/3601 Tracking frames; CQ18 receives1806/3600;
both have zero failed grabs/observed BlockID gaps. Cameras start before the common
barrier, so these are receipt spans, not exact trial CFR counts. Native4096 receives
594 frames at29.69 receipt fps with one BlockID gap: this is observed loss, not a
loss-free full-resolution guarantee. The sampled Tracking image is exactly black;
Behavioral imagery is dim. CQ23/CQ18 Behavioral sizes141.58/338.54MB are engineering
measurements, not representative-scene quality selection. SDK pipelines bypass
production queues/CFR and Tracking processing. Camera closure is confirmed;
Per-case PFS serialization initially differs only in selector context; final
pre-audit PFS restoration is byte-exact for all three cameras, with original feature
readbacks verified. [Counts/full decodes/settings](runtime-evidence-2026-10-15/comprehensive-audit/direct-assessment.json),
[final restoration](runtime-evidence-2026-10-15/comprehensive-audit/final-restoration.json).

Oct21 `repo-unused-code-oct21` removes five unused recording compatibility
modules that re-exported shared FFmpeg helpers. Existing filter tests import the
shared owners directly, with unchanged test bodies and production behavior.
[Cross-owner assessment](runtime.md#maintainability-review) records focused checks
and the interrupted broader run; no acquisition policy or rig guarantee changed.

Oct16 maintainability implementation shares controller-owned MCU validation with
acquisition defaults and uses one exact worker session predicate. Existing operator
values, original deadlines and ownership remain; focused configuration35 and worker90
checks pass. [Current cross-owner assessment](runtime.md#maintainability-review)
retains final integration evidence and remaining native limits.

Oct16 `camera-failed-output-presence` is repaired under E04/A07/A08:
`session_outputs.failed_outputs` now reports actual path presence independently of
owned-identity proof. An existing unmatched/unproved video is present with closure
unconfirmed; an absent path is absent. Exact owned failed-encoder outputs retain
failed closure. No deletion, replacement, ownership promotion or frame behavior changed.
Five real-path cases cover absent, unproved, replaced and exact-owned outcomes.
The [original probe](runtime-evidence-2026-10-16/backend-output-alignment-review/validation.json)
and [repair checks](runtime-evidence-2026-10-16/output-provenance-fixes/validation.json)
retain red/green evidence. Combined acquisition/stimulus/selected central-output tests
pass997 (five platform skips, three exclusions); native execution is separate.

The source/video/timestamp joins retain explicit losses. A09's initial anchor remains
an assumption and native counter gaps/reset ambiguity remain visible. On Oct16 the
owner confirmed hardware pulse wiring is verified and all planned cameras will be
externally triggered; free-running alignment is outside this task. This confirmation
does not rewrite historical free-running evidence below. Camera cadence and encoding
settings were not changed by these two output fixes.

Oct16 sequential camera recording is implemented under
[A08 revision51](../docs/architecture/acquisition.md#a08), with A07rev64/A09rev16
mapping/anchor clarifications and acquisition policy22. All three roles encode each
usable retained image once in source order, retaining receipt/native timestamps and
explicit invalid/capacity-loss rows. Schema5 removes nominal slots, enforces exact
one-to-one source mappings and retains a zero duplicate count. Playback remains at
the existing nominal rate; its duration need not equal the trial. Camera settings,
trigger rates, encoding arguments and E13 stimulus recording are unchanged. Historical
Oct15 schema4/CQ18 results below describe the former camera resampling path, not
native acceptance of this change.

ARCH-002 removes camera slot-selection/tail-padding code and redundant slot/duplicate
state. The recording session remains a cohesive schedule/pump/closure owner (638
lines, reduced from691), with conversion, append-only evidence and finalization in
existing focused modules. No dependency, process or extra recording mode is added.
Owning regressions cover all roles/timing modes, same-interval images, gaps, source
identity/timestamps, invalid/capacity losses, metadata-only output, normal/Abort
closure retries and input/mapping/maintenance failures without false success.
Final acquisition/planning/encoding-probe/stimulus-recording selection passes607
(five platform skips/two marker deselections). Ruff/format209, Win32 mypy185 and
boundaries698/zero violations pass; policy/schema/register and unchanged-rate/stimulus
checks pass. A broader run has1211 passes and three failures in concurrently edited
controller-configuration tests; those cases now pass a focused five-case recheck
after the concurrent implementation advanced. No full integration rerun is claimed.
Earlier fixture mistakes and corrected attempts are retained in the [validation context](runtime-evidence-2026-10-16/camera-sequential-recording/validation.json).
Native count/decode, unchanged-rate combined throughput and timestamp correspondence
remain in the [rig checklist](rig-verification.md); local checks do not establish
NVENC throughput, optical timing or zero physical loss.

Oct16 follow-up review reproduces inherited first-image accepted-input accounting loss
when its required mapping append fails. The local repair counts a completed pipe write
before that append, while retaining failure and incomplete source metadata. Maintenance
and sync remain after successful mapping. Input-write failure stays NO_FRAMES; mapping
and later maintenance faults retain FRAMES_SUBMITTED with unconfirmed video/failed log.
The owning fault test fails before repair and passes afterward; acquisition536 passes,
five platform skips/two exclusions, Ruff/format3, Win32 mypy2 and boundaries699/zero
violations pass. No native encoder or rig acceptance is inferred.
[Repair evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
The [reproduction and validation](runtime-evidence-2026-10-16/camera-sequential-recording-review/validation.json)
retain a real-queue/pump/JSONL/finalizer check combining capacity loss, invalid input,
equal receipt timestamps, a long gap and interrupted closure (four source rows,
two images, exact mappings, zero padding). The focused integration rerun passes607
with five skips/two deselections; scoped Ruff/format passes33 files. The fault probe
uses an accepting fake encoder and injected mapping failure, not native media proof.

Oct16 development-machine reliability repair under
[E04](../docs/architecture/supervisor.md#e04),
[E05](../docs/architecture/experiment.md#e05),
[E06/E08](../docs/architecture/system-contracts.md#e06) and
[A10](../docs/architecture/acquisition.md#a10): interrupted backend cleanup now
precedes interrupted trial/session metadata sealing. Already validated exact cleanup
reports supply current-trial output results without inventing normal Finished or
an actual stop timestamp. Missing evidence remains unconfirmed; one frozen-set
session-state recovery query retains the original deadline. Normal completion
keeps metadata-before-cleanup ordering, including an Abort joining during metadata
sealing. Cleanup admission additionally rejects output paths differing from the
registered plans. Earlier trial files are not retroactively rewritten.

The Basler adapter's unknown-discard reuse guard previously survived successful
native device Close and incorrectly blocked a fresh open. Local regressions reproduce
this across both timing modes. Confirmed Close now retires only that device-scoped
guard; same-device reuse and failed Close remain blocked, and retained unknown counts
stay unknown. Six repeated close/reopen cycles per test variant pass. This identifies
the cross-close software defect, not the original native drain-interruption cause.
Existing retired-boundary checks now exercise a fresh session/trial on the same
pulse owner after the old boundary, with no stale actuation or evidence mutation.

ARCH-002 review reuses the existing lifecycle, metadata, report-admission and SDK
owners and behavior test modules; no dependencies, processes, policy values or
runtime states are added. The existing 567-line interruption workflow remains
cohesive around one finalization task; the 685-line Basler facade retains device/SDK
ownership. No separable responsibility is extended. Native Abort latency/metadata,
rapid reuse and repeated real-camera preview acceptance remain open in the
[rig checklist](rig-verification.md). Local validation and source provenance are in
[Oct16 evidence](runtime-evidence-2026-10-16/dev-reliability/context.json).

Final local selection passes **1,531 tests**, with five skips and three native/rig
deselections; it includes authenticated loopback checks. Scoped Ruff/format passes
346 files, Win32 mypy passes 293 sources and boundaries inspect 698 modules with zero
violations. The first expanded run retained 11 denied loopback binds and two missing
imagecodecs failures; permitted final execution after installing the already pinned
imagecodecs version passes. Stale ignored bindings were regenerated from existing
contracts. A final review caught and fixed an overlap race introduced by the initial
ordering change; its red/green case is included in the final result. These are local
behavior/static results, not native timing or SDK acceptance.

Owner-selected Oct15 recording tuning now uses CQ23/p4 H.264 NVENC VBR with
zero target bitrate, zero lookahead and both AQ modes explicitly disabled for
all three cameras. Behavioral retains full-range BT.709 YUV444; Tracking and Eye
use explicit grayscale conversion with neutral-chroma YUV420 and unchanged
dimensions. Both repository defaults and saved camera argument overrides match;
other saved configuration, camera features/PFS, rates and recording depths are
unchanged. This is operator tuning within [A08](../docs/architecture/acquisition.md#a08)
and [E14](../docs/architecture/system-contracts.md#e14), not a policy revision or
quality/throughput pass. Owner will update PFS files before representative-scene
evaluation under the [existing rig plan](rig-verification.md#encoding-test-plan).
Full-width 4112-pixel Behavioral H.264 incompatibility remains; these settings
do not select an ROI or automatically switch codecs. [Exact argument changes](runtime-evidence-2026-10-15/camera-recording-cq23/settings.json).
Configuration loaders, strict saved Protobuf parsing and saved/default equality
checks pass; focused existing configuration/capability/filter coverage passes
23 cases (24 deselected). The broader three-module invocation was interrupted
without a completed result. No device or encoder execution was performed for
this tuning. [Validation and limits](runtime-evidence-2026-10-15/camera-recording-cq23/validation.json).

Current Oct15 open-loop verification uses all three supplied Pedro camera presets,
the latest GUI projector calibration and a strict no-Tracking runtime. The configured
Tracking camera still records. Eye uses acknowledged free-running60Hz, verified from
actual trigger-off/limiter-on readback. Camera imaging values remain unchanged;
Behavior/Tracking images are nearly black and Eye is dim, limiting scientific image
quality and realistic scene-load acceptance. CQ18 camera encoding is lossy; source
continuity, CFR substitutions and codec-input fidelity are separate measurements.

The current-calibration normal120s trial completes with confirmed cleanup/reuse and
four strict count/full-decode passes (3600 Behavior frames,7200 each other stream).
The requested 900-second trial also completes exactly, with confirmed cleanup,
successful NewSession and four strict external counts/full software decodes. Behavior
has 27,000 frames; Tracking camera, Eye and stimulus each have 54,000. Collection and
runtime errors are empty. All camera source/native counters are continuous, invalid
records are zero, pre/post-cutoff accounting is complete, and available SDK failed,
missed and resynchronization counters are zero. Camera CFR duplicates are respectively
55 (0.204%), 241 (0.446%) and 193 (0.357%); received but unselected same-slot frames are
34, 200 and 187. Nominal video counts do not imply every source frame was retained.
Active-only CPU averages 17.02% (maximum 36.62%); GPU memory stays at 1460 MiB for
rendering and 1030 MiB for encoding. Astra accepts endurance and closure as low-loss
engineering evidence, with dim/black scene limitations. Native camera timestamps lack
tick-frequency conversion; uniform physical exposure timing is not established.
[Final collection](runtime-evidence-2026-10-15/open-loop-soak/resume-1/combined900-final-r1/collection.json),
[source accounting](runtime-evidence-2026-10-15/open-loop-soak/resume-1/combined900-final-r1/assessment.json).
A bounded camera-lossless check also passes on the RTX 2080 Ti. Three six-frame,
full-ROI fixtures decode byte-for-byte to identical prepared 8-bit full-range YUV444
planes using H.264 NVENC `-rc constqp -qp 0 -tune lossless`, retaining the conversion
filters and removing CQ controls. This proves codec-input fidelity; Bayer demosaicing
and RGB/YUV conversion are not raw-sensor lossless. A separate 60-second native run
with only camera encoding changed completes and cleans up normally; all four strict
counts/full decodes pass (1800 Behavior, 3600 each remaining stream). Camera source/
native counters stay continuous and available SDK loss counters are zero. CFR repeats
are 14/18/4 (0.778%/0.500%/0.111%); same-slot omissions are 11/14/1. Stimulus has zero
capacity drops, three same-slot omissions and two repeats. CPU averages 19.64%
(maximum 30.07%); encoding GPU averages 42.34%, encoder engine 44.47%, memory 1030 MiB.
Measured camera storage is 191.29 GiB/hour plus 4.23 GiB/hour stimulus, extrapolated
from this short dim-scene run. This is not a controlled comparison with the 900-second
CQ18 run, a realistic-scene guarantee, or 15-minute lossless endurance acceptance.
Stimulus review remains lossy under [E13](../docs/architecture/visual_stimulus.md#e13).
[Codec fidelity](runtime-evidence-2026-10-15/open-loop-soak/resume-1/lossless-feasibility.json),
[native collection](runtime-evidence-2026-10-15/open-loop-soak/resume-1/lossless60-r1/collection.json),
[recording/storage accounting](runtime-evidence-2026-10-15/open-loop-soak/resume-1/final-accounting.json).

Reviewed repairs under [E06](../docs/architecture/system-contracts.md#e06),
[A10](../docs/architecture/acquisition.md#a10) and
[A11](../docs/architecture/acquisition.md#a11) retain strict ownership and deadlines:

- Allow acknowledged Eye free-running configuration; deliver MCU pulse evidence only
  to selected external cameras. Keep worker validation and first-frame deadlines.
- Route exact session-scoped interrupted Finished output evidence into the existing
  session ledger without fabricating normal trial completion. Missing/stale sessions
  and mismatched output batches reject before retention.
- Match retained backend parent identity for late pulse evidence. Seal admission
  immediately, then service exact terminal OFF evidence through the serialized owner
  loop before bounded SDK drain. Overlapping safety commands preserve the first output
  owner and earliest deadline; cleanup waits for a pending writer finish.
- Cancel retired scheduled ON/OFF/end tasks and fence current session/trial authority
  before actuation, after awaited results and before fallback Stop.
- Perform MCU OFF preflight before publishing a new trial. Revalidate prior authority
  and retain worker preparation children before yielding; serialize preparation without
  holding the telemetry lock across serial I/O. Heartbeat validation stays strict.

Final acquisition owner validation passes523 cases (two deselected), including actual
serialized-owner stop ordering, pending-writer bounds, retired-boundary races and real
READY heartbeats during blocked preflight. Scoped Ruff/format/Win32 mypy and695-module
boundary checks pass. Astra reviews the frozen increments. ARCH-002 cohesion review
retains capture_runtime623 and execution514 lines as focused SDK-resource and operation
dispatch/completion owners; no new policy or dependency. Source patches, hashes and
commands are retained in [resume-1 evidence](runtime-evidence-2026-10-15/open-loop-soak/resume-1/).

Abort120-r3 and Abort180 confirm actual camera pre/post-cutoff accounting, external
ON/OFF APPLIED, session cleanup and NewSession. All four r3 videos pass strict count/
decode. Interrupted finalization still takes about40s and emits lifecycle_recovery;
earlier trial-log closure can remain unknown even though later session cleanup confirms
actual outputs. Immediate capture cutoff is distinct from command return latency.
Follow `interrupt-trial-log-closure` without retroactively relabelling trial records.

Rapid post-Abort reuse remains unaccepted: rapid120-boundary-r1 accepts Setup/StartSession
but fails PrepareTrial before scheduledT with stale-work heartbeat rejection and ensuing
cleanup errors. The generic publication race is repaired and locally covered, but no
native rapid-reuse interval crossed the retired deadline. Astra selected a fresh900s
generation using the already verified normal120s gate, preserving that separate open
finding in `rapid-abort-setup-heartbeat`.

Earlier failed attempts remain evidence, not upgraded passes: the first900s failed
around71.4s with truncated Behavior/Eye tails; the owner stopped the next at883.852s
with unknown closure. CR-only FFmpeg statistics framing and a fatal-error route that
masked the original exception were repaired (947 relevant tests and Astra30 focused
checks), but the original masked cause is not conclusively recoverable. Resumed Abort
r1 exposed wrong pulse-parent identity; r2 correctly reported unconfirmed SDK drain.
All partial recordings and emergency reports are retained. Process-exit receipts alone
never establish file closure.

Fresh saved configuration/TOML, GUI calibration/cache and all three full camera PFS
baselines are retained in resume-1. Test warps use unique copies of the newer GUI
mapping (Bottom685x940; derived spin pivot23,0), because the old experiment profile
references older geometry. Do not restore historical pre-pause snapshots over these
later settings. Final owned runtime exit and empty native process inventory are verified.
Fresh saved experiment, GUI settings and Visual Stimulus TOML restore byte-exact under
compare-before-write guards. All three validated camera PFS loads and closes succeed;
their exact-text guard correctly fails because standalone LineSelector cursor records
differ (baseline Line1, restored Behavior Line2 and Tracking/Eye Line3). Astra's ordered
full diff confirms every selector-qualified feature value matches. Functional camera
settings are restored; byte-identical PFS serialization is not claimed or retried.
Separate reusable CQ18 endurance and camera-lossless 60-second packages retain actual
adopted settings and tested TOML overrides under Desktop/Pedro/media/protocols. Those
overrides are not left active. After all recording work ended, only 51 verified synthetic
MP4s (13.504 GiB) were deleted; real/failed recordings and raw evidence remain.
[Restoration and package index](runtime-evidence-2026-10-15/open-loop-soak/resume-1/final-cleanup.json),
[cleanup manifest](runtime-evidence-2026-10-15/projector-free-rig/synthetic-media-cleanup.json).
[All raw attempts and fixes](runtime-evidence-2026-10-15/open-loop-soak/).

Oct15 direct zero-byte raw-input probes using the production-shaped camera options
and FFmpeg9.0.2 on RTX2080Ti exit0 for both enabled camera formats and finalize small
MP4s (1614/1606 bytes), with writable-handle synchronization and close. Identity tags
are omitted for this standalone probe. This establishes muxer capability only, not
playable video or runtime A07 NO_FRAMES accounting/ownership acceptance. The initial
probe failed while synchronizing a read-only Windows handle; artifact/log retained,
then corrected to a writable handle and fresh paths. No failure exit was ignored.
The [Visual Stimulus report](visual_stimulus.md) owns the completed synthetic31-case
encoder matrix and its full-path limits.
[Raw empty-input results](runtime-evidence-2026-10-15/projector-free-rig/empty-video.json).

Oct15 actual projector-free rig checks: COM8 reports protocol4/cephvr2_uno_4;
saved Behavior D11/30Hz and Tracking D10/60Hz settings are retained. Eye remains disabled
with saved D9/60Hz configuration; it is not enabled for this test. Four native managed
preview cycles per enabled camera complete with confirmed device release and unchanged
adopted configuration. One extra Behavior preview/Stop succeeds, but the following Start
fails with `prior capture has unknown SDK-buffer discard accounting`. This is an observed
reuse blocker, not evidence that the accounting guard itself is defective; its source
cause is unverified. Follow `camera-preview-sdk-discard-reuse` without bypassing safety.

Exact idle controller departure stops owned supervisor/acquisition processes and yields
an all-owned-absent receipt. Acquisition reports MCU claim release unconfirmed after
controller departure. Active-capture loss, electrical LOW, watchdog under load and
combined recording acceptance remain open. Initial full PFS snapshots, including selector
cursors, restore exactly and cameras close; saved configuration bytes remain unchanged.
[Dated commands, raw results and limits](runtime-evidence-2026-10-15/projector-free-rig/context.json). This does not remeasure adopted queue20/SDK15/drain150 under full recording load.

Oct14 working-tree verification corrects the owning configuration test to the
owner-selected 150 ms drain and retains its missing-field assertion. The controller
integration fixture's status gate now honors its original RPC deadline, resolving
the reproduced unbounded test wait without changing runtime deadlines or assertions.
Owning configuration tests pass 72 cases; final local backend selection passes
1,670 cases with four skips and 26 native/rig deselections. These results do not
remeasure queue20/SDK15/drain150 or close hardware acceptance under
[E15](../docs/architecture/system-contracts.md#e15).
[Raw verification](runtime-evidence-2026-10-14/working-tree-validation/summary.json).

Oct14 rig audit verifies a sixty-second combined Behavior/Tracking/Eye trial: confirmed cleanup, restored settings, four independently counted/full-decoded videos and zero camera queue overflows. The measured queue17 covered burst demand with20% margin at30/60/60Hz. Owner now selects queue20, SDK15 per camera and150ms drain allowance; TOML/live configuration/history loading are verified, but these new values have not been remeasured. Sustained headroom remains unproven. Camera nominal-slot omissions remain separately accounted. Dedicated Save On to Save Off completes in one generation with two decoded camera videos and no stimulus artifact. Four preview start/stop cycles per camera (12 total) complete with unchanged settings and all devices released. E05/E06/E08/A10 repairs cover completed-session health, stale serial failure, aggregate CancelSetup, exact cleanup receipt retention and interrupted-trial pulse evidence. The last two require renewed native session checks: projectors are now owner-deferred and E10 correctly rejects disabling required Visual Stimulus. Physical electrical/photodiode, paired mappings and Tracking processing remain deferred. [Configuration assessment](runtime-evidence-2026-10-14/rig-timing-audit/configuration-assessment.json), [Current findings](runtime-evidence-2026-10-14/rig-timing-audit/lifecycle-findings.json).

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

Continuous pin tests now follow [A11 revision45](../docs/architecture/acquisition.md#a11): explicit Stop replaces elapsed expiry, while matched diagnostic polls renew a two-second firmware lease. Updated Uno firmware compiles; host/offscreen verification and limitations are in the [runtime assessment](runtime.md). Manual upload and physical sustained-output/lease-expiry acceptance remain in the [rig checklist](rig-verification.md).

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

Oct14 `encoding-quality-defaults`: owner selects CQ16 as the standard, p4, unchanged
source dimensions, Behavior color 4:4:4 and Tracking mono; Eye and Stimulus mono
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

Oct14 `always-save-scientific-evidence`: Required camera JSONL is now planned for every enabled experiment role. Metadata-only Setup skips FFmpeg/NVENC and conversion; capture admits bounded records without copying pixels or allocating video pools. The existing owner thread preserves interval, counters, invalid-image evidence, pulse/transport diagnostics and closure. Frame-log schema4 explicitly declares disabled video, without drops or fabricated mappings.
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

Device workflow refinement under [G01](../docs/architecture/gui.md#g01) and
[E07](../docs/architecture/experiment.md#e07) separates camera participation from
logical MCU wiring. Identity tests and selected-camera preparation can proceed while
unrelated drafts are incomplete; exact scoped validation preserves Use/recording
choices, ownership and strict Setup. The [runtime assessment](runtime.md) owns
review and local evidence; electrical/native acceptance remains in the
[rig checklist](rig-verification.md).

Oct13 development-machine repairs under [A02](../docs/architecture/acquisition.md#a02),
[A11](../docs/architecture/acquisition.md#a11) and
[E08](../docs/architecture/system-contracts.md#e08): completed camera-worker results
now release unused result-reservation bytes through explicit terminal completion.
Every preview's ResolveCameraConfiguration formerly retained16MiB even for a tiny
result; production limits reproduce rejection at the fourth request. Pending results
still reserve the full allowance; exact bytes, replay retention, deadlines, safety
quota and record count remain unchanged. Four completed readbacks now pass while
three unresolved large results still exhaust the normal allowance. MCU pending/
unavailable remains a separate unproven observation; no ownership fence is relaxed.

Orderly host teardown tolerates MCU Close UNAVAILABLE only after exact registered
controller PID/creation-time absence is confirmed. The claim remains unconfirmed
and is reported; live/unknown controller state and other RPC failures propagate.
Existing resource/channel cleanup still runs. Owning tests include actual client
claim preservation. [Cross-owner validation and review](runtime.md#unresolved-findings-and-limitations)
record1316 local passes/five platform skips/four deselections and final transport9,
plus static checks. [Raw provenance](runtime-evidence-2026-10-13/dev-machine-repairs/context.json)
retains commands and scope. No hardware/operator/firmware settings change; repeated
native preview and orderly teardown acceptance are [rig-deferred](rig-verification.md).

Oct13 owner-selected125ms drain margins remain applied to all camera roles
under [A10](../docs/architecture/acquisition.md#a10); Eye is disabled/unmeasured.
Two consecutive final normal60s Behavior30Hz/Tracking60Hz plus stimulus recordings
close with1797/3596 valid received frames each, complete post-cutoff accounting/two
excluded frames per camera and SDK failed/missed counters0. All four camera videos
externally count1800/3600 and fully decode. Camera queues drop9/28 in the first run,
6/19 in the repeat; identified video duplicates remain, so no zero-loss claim.
Live PID/UUID/NVENC evidence proves camera encoding RTX2080Ti/GPU1 and renderer
RTX5060Ti/GPU0. Renderer reaches60.0333/60.0167 real groups/s.

[A07](../docs/architecture/acquisition.md#a07) revision61 orders final warning
acknowledgement before Finished. Exact terminal MCU retries compare the MCU outcome
after scope/connection checks, independent of fresh forwarding command ID. Worker
health retains canceled scheduled trial scope until proven session cleanup. Shared
absolute-clock waits correct early async ON/OFF/end dispatch while preserving E05/
E08/E11 boundaries and strict evidence validation. Both final NewSession/restore
operations succeed in the same generation, no shutdown. Original settings and released
cameras are verified. No camera/PFS/encoder/firmware tuning;125ms is an adopted
engineering allowance, not a guaranteed worst-case bound.

1123 affected-owner regressions pass/3 skip/6 deselect; native pipe14 pass; Ruff,
Win32 mypy427 files and boundaries667/zero violations pass. Source/context records
retain initial fixture/sandbox failures, exact failed-generation administrative recovery
and all removed experiments. Remaining review/camera recording drops and broader
Eye/Tracking/paired/optical acceptance stay explicit.
[Dated raw evidence, verification and limits](runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)


Oct13 owner chooses measuring drain timing before approving A10 file allowances.
Managed sessionless previews retain original camera/trigger settings and recording
is disabled. Three completed two-second terminal-OFF/AcquisitionStop observations
per camera across two generations: Behavior25ms exposure/30Hz first receipt within
67.4401ms of ON dispatch and latest late receipt36.0479ms after OFF acknowledgement;
Tracking5ms/60Hz first receipt within23.426ms, no post-OFF receipt observed. First
receipt latency includes serial/phase/exposure/SDK, so it conservatively bounds an
empirical combined component; adding one period gives100.7734/40.0927ms. Proposed
125ms/50ms were initial proposals, superseded by the owner's125ms-for-all selection
above; observations are not guaranteed worst-case bounds. Initial
diagnostic sealed-ring failure is corrected to direct SDK tail retrieval/release;
raw tail observations are separate from production accounting. Repeated MCU
preview-start pending/unavailable and later command-record byte budget exhaustion
curtail planned sampling; retain the cause/reuse investigation in TODO/runtime
report. Normal GUI restored with exact original configuration and released devices.
[Raw measurements, proposal, limits and provenance](runtime-evidence-2026-10-13/combined-camera-stimulus/drain-assessment.json).

Oct13 owner-authorized GPU placement verification confirms the current physical
RTX2080Ti UUID GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc resolves to CUDA/NVENC
ordinal1 under [SYS-002](../architecture.md#sys-002)/A08. Fresh native NVENC capability
resolution and the existing camera command builders inject -gpu1 for Behavior,
Tracking and Eye using their current saved argument lists and actual configured
dimensions. Each bounded generated-frame encode has a matching live NVIDIA
encoder-session PID on that physical GPU, closes normally and externally probes
four frames. No camera is opened or saved encoding/ROI/rate/PFS setting changed.
This verifies encoder placement and command execution; camera conversion, actual
footage, simultaneous load and sustained throughput remain pending.
[Exact argv, live session samples and media evidence](runtime-evidence-2026-10-13/gpu-placement/context.json).

Oct13 fresh bounded capture is explicitly authorized for the workflow audit.
Behavior40065509 and Tracking40747103 real identity, usable capture/visible preview,
Stop and release pass on the current tree; the earlier no-usable-frame failure is
historical and does not reproduce. Eye remains disabled/untested. Optional native
timestamp availability warnings persist (A09). Combined recording Setup fails before
activation because the active cameras' file-only post-cutoff drain margins are unset
(A10); no camera video is produced. Establish exposure + rig delivery/SDK bound +
one applied frame period before setting those allowances and repeating recording.
Do not substitute guessed values. Failed-Setup renderer cleanup also fails, while
eventual exact full application absence is confirmed. See the current
[workflow failure/remedy inventory](runtime.md) and
[raw camera/Setup evidence](rig-evidence-2026-10-13/workflow-tests/).
Final orderly shutdown confirms exact application absence but acquisition's MCU
Close RPC after controller exit emits an uncaught UNAVAILABLE traceback. Retain
this teardown defect separately from the successful device preview releases;
review shutdown ordering and expected authority-loss handling under E08.

Oct13 Eye MCU integration is now owner-authorized and implemented under
[A01 revision18/A11 revision44](../docs/architecture/acquisition.md): protocol4
supplies an independent Eye output through Setup, preview, trial boundaries,
rate evidence and all-output stop/recovery. Explicit external FrameStart source,
unique pin/rate and device assignment remain required; defaults stay unset/disabled.
Firmware compiles and local controller/acquisition regressions pass834, with three
privilege skips/two native marker deselections. This supersedes the unconditional
Eye-integration admission block, not the owner's physical capture/electrical deferrals.
Installed protocol3 evidence below is historical and does not validate protocol4;
upload remains manual. [Current implementation/evidence](runtime.md),
[rig acceptance](rig-verification.md).

Oct13 native rig checks: controller-owned COM8 Connect confirms protocol 3 /
`cephvr2_uno_2` and stopped Behavior/Tracking outputs. An actual GUI Behavior Connect
attempt receives no usable frame by its original deadline and raises
WORKER_OWNER_FAILURE; exact application shutdown/guard release is verified.
The cause is unresolved; earlier preview passes remain historical evidence.
The owner defers further camera capture, all Eye checks and other electrical measurements.
Oct13 Trial state pin-12 output testing is now explicitly requested through the GUI
Test button. Earlier agent-triggered firmware tests have matched start/stopped evidence;
the owner clarifies manual triggering, and Runtime is reopened with pin 12 ready.
No SpikeGLX reception pass is inferred. This does not close electrical/timing or camera
acceptance; see the [current MCU assessment](runtime.md).
Windows backend/native regression passes 1,520 with five privilege skips across owners;
the native protected-source and ring/process checks are separate from real camera
acceptance. The later matched FFmpeg/ffprobe 9.0.2 upgrade resolves the original 4.3.2
MP4 incompatibility; current camera lists and reference-adapted proposals pass
build/device validation and short synthetic normal-closure checks on RTX 2080 Ti.
Saved settings remain unchanged; camera quality/conversion/throughput are unverified. [Current assessment](runtime.md),
[dated evidence](rig-evidence-2026-10-13/) and [remaining checks](rig-verification.md).

The Oct12 model-hierarchy audit deeply traced capture/source identity, cutoff,
shared-ring synchronization and terminal recording/flush/close paths, and sampled
manual devices, sessions and pixel adapters. No additional actionable acquisition
defect was established. The [current cross-owner assessment](runtime.md#current-scope-and-review)
records source provenance, review coverage and portable checks; native camera,
encoder and full-workload acceptance remain in the [rig checklist](rig-verification.md).

Oct11–12 behavior-preserving cleanup under [ARCH-002](../architecture.md#arch-002)
removes unused acquisition diagnostic state left over from MCU ownership, unused
capture/Basler/recording accessors and thread-identity bookkeeping. A11 diagnostics
remain controller-owned. Worker Schedule/Release now call the existing trial owner
directly; its implementation bodies are AST-identical after removing forwarding
layers. First-record accounting still invokes its callback once with the observed
clock value, without a redundant retained copy. Remove unused completion-result
locals, callback references and a queue forwarding lambda. One obsolete test-fixture
assignment is removed; all assertions and scenarios remain.

The earlier branch/return cleanup and worker stop-delegate removal preserve
A02/E08 authority, original deadlines, locking, capture clock checks and copied
cleanup evidence. SDK, recording, dispatch and lifecycle owners retain their focused
responsibilities and shrink; no new dependency, state owner or contract. Final Oct12
acquisition/Visual Stimulus/controller camera-and-MCU selection passes **795 tests,
five skips and three Windows/rig deselections**, including authenticated communication.
Ruff/format passes 874 files, Win32 mypy passes 311 affected backend sources, and
boundaries check 640 modules with zero violations. An initial invalid test filename
ran no tests; the corrected selection above passed. The owner requested removal of
both cleanup passes' raw logs and hash manifests on Oct12; these are historical
result summaries, separate from native camera/Windows/rig acceptance.

Oct9 optional-I/O work is stopped at the owner's request while leaving the rig.
Existing signal roles retain independent Use/pin controls under
[A11 revision 43](../docs/architecture/acquisition.md#a11); the disconnected projector
flip defaults Off with its D2 setting retained. An explicit saved On setting is not
overwritten: native Apply has not been verified. Missing sketch paths now produce
an actionable error containing the submitted path instead of incorrectly reporting
a link. Both repaired sketches already pass production snapshot/Arduino compilation;
the earlier CephVR2 GUI upload and protocol-3 connection test pass. CephVR1's missing
CAPS remains a compatibility limitation. No firmware code or new upload changes here.
[Latest scope/check evidence](review-evidence-2026-10-09/mcu-configurable-context.json)
records 300 focused passes/one privilege skip, static passes and a full-suite timeout
that passes focused rerun. The owner confirms projectors are disconnected; native
settings save and another experiment remain unverified.

Oct9 Eye camera/connect recovery (working tree based on `94285ac`) follows
[A01/A02](../docs/architecture/acquisition.md#a01),
[A07](../docs/architecture/acquisition.md#a07),
[A10/A11](../docs/architecture/acquisition.md#a10) and
[G01](../docs/architecture/gui.md#g01). The third role supports common configuration,
worker identity, status, preview plumbing and video/frame-log output pairs; Tracking
analysis still uses only its original camera. Eye capture rejects before worker/COM
access until external wiring, source/rate and trigger integration are specified.
The discovered third serial is 40278236. The prior missing-pacer validation rejection
is repaired for the owner's all-projector VSync mode; native assignment remains
unverified while projectors are disconnected and Eye triggering is unspecified.

Failed/canceled manual Connect and PFS readback now retire their exact adoption
barrier without clearing native ownership. Disconnect can finish an editing camera
that has no preview run, and identity results explain retained prior cleanup.
Manual completion acknowledgement uses the exact retained device result rather than
requiring a live experiment; altered source/work/result and late evidence reject.
The GUI has a separate selected-camera identity check and does not map Eye/unassigned
MCU rows onto Tracking's pin. Acquisition fixed policy is version 20.

Native GUI checks verify Behavior 40065509 and Tracking 40747103 identities.
A normally closed runtime followed by a bounded real SerialOwner probe finds
legacy `dual_camera_projector_sync` firmware on COM8 rejecting CAPS. The host now
reports that incompatibility immediately. The owner's subsequent Upload request
resolves the GUI's failure-only recovery block under G01/A11. Native `.ino` Browse,
GUI compile/verified upload to COM8 and Test connection succeed: `cephvr2_uno_2`,
protocol 3, both camera outputs stopped, no pending tool cleanup. The controller's
Upload admission also fences Eye device/preview/cleanup ownership. No new trial ran.
[Firmware source/native/check evidence](review-evidence-2026-10-09/firmware-picker-context.json)
retains the method and limits. Local tests cover all three role paths and
exact canceled/terminal evidence; native Eye capture and experiment/output acceptance
remain pending in the [rig checklist](rig-verification.md).
[Current commands, raw evidence and source provenance](review-evidence-2026-10-09/eye-camera-context.json)
retain final results and intermediate failures. Under ARCH-002 the existing manual
device command owner remains cohesive (SDK edit sequencing); results/status/preview
already have separate owners. GUI camera/MCU size advisories concern cohesive widget
construction and presentation; this change reuses focused managed bindings.
Earlier whole-repository non-rig execution passes 1,856 tests with five privilege
skips and one rig deselection after the subsequent shared runtime namespace repair;
all static and declaration checks pass. Earlier contract/schema evidence remains
scoped to its retained source/check provenance.

Final GUI relaunch during the runtime namespace repair retained a separate legacy-sketch compilation
failure: command `09e718b2-9c6b-4a19-b133-38f3a17f1cbe` reports missing
`projector_clock.h` in the staged `cephvr1_mcu.ino`. The owner reproduces that
failure after both independent sketches were placed together under `firmware/uno`
and the header stayed above them. A11's bounded complete-folder snapshot is correct;
repair the source layout, with no backend or new dependency/state change under
ARCH-002. Each sketch now has its own matching directory, and the legacy header is
copied beside CephVR1 with the original retained. All three source hashes match
their pre-repair bytes. Production snapshot/HEX validators plus installed Arduino
CLI compile both immutable snapshots for Uno successfully: CephVR1 uses 16,366
flash bytes/603 RAM bytes, CephVR2 11,078/1,112. Existing MCU owner checks pass 68
with one symlink-privilege skip. CephVR1 still lacks CAPS; compilation does not make
it compatible with the protocol-3 host. No new serial command or upload runs.
[Pinned sources, exact commands and compile outcomes](review-evidence-2026-10-09/firmware-layout-compile.json)
and [retained earlier failure](review-evidence-2026-10-09/runtime-root-final-reopened-status.json)
distinguish current compilation from installation/experiment acceptance.
Native Browse lists both repaired directories and accepts the current CephVR2
selection at `firmware/uno/cephvr2_mcu/cephvr2_mcu.ino`, with Upload enabled.
The former flat path remains only in retained failed activity. The fresh GUI is
idle; no firmware button is pressed by this task.
[Layout/check/picker reconciliation](review-evidence-2026-10-09/firmware-layout-context.json)
confirms all 1,039 prior runtime/test/config/contract inputs are unchanged, so their
earlier full/static results remain applicable; no new full-suite run is claimed.

The earlier Windows checkout `94285ac` passes the complete non-rig suite after regenerating
stale local bindings, including available native camera-wait/resource checks.
[Current cross-owner results and limits](runtime.md) retain commands and source hashes;
this does not repeat native trial recording or close encoder/camera throughput acceptance.

Latest retained native dummy evidence is run43 (Oct8), reviewed on 2026-10-09:
the 60 s unpaired trial/session completes with cleanup, metadata sync and seven
closed outputs. Behavior records 1,797 frames (29.95 fps) and Tracking camera 3,596
(59.93 fps); external counts and full CPU decode pass. This supersedes the run42
20/40 fps observation after preserving the saved-disabled limiter in external-trigger
mode under [A10](../docs/architecture/acquisition.md#a10). SDK missed/failed frames
are zero in the summary; unavailable native timestamps/counters remain unavailable.
This does not prove electrical trigger correlation, scientific timing or full-load
acceptance. Tracking velocities remain disabled independently from its camera video.
[Run43 raw summary](rig-wiring-evidence-2026-10-08/dummy-experiment/unpaired-run-43-output-verification.json)
has no exact tested source revision; no native run or decode was repeated in this audit.

Post-cutoff accounting used temporary 1,000 ms allowances, not measured guarantees.
The Oct9 authorized repair removes those temporary defaults; all 36 combined
configuration checks pass. Camera-worker retirement now explicitly confirms retained
successful Cleanup plus exact lifecycle/resource/output evidence under
[E08 revision 169](../docs/architecture/system-contracts.md#e08), with independent
supervisor native absence checks. Exact proof is acknowledged before Shutdown to
avoid an expected-exit/health race, then reconciled after native exit using the same
immutable confirmation. Independent operation/lifecycle delivery is joined
within the original deadline; guarded retained-query recovery preserves accepted state.
Workless Configuration and session callers are covered, including discharged failed
outputs. The final owning suite passes 338 with five skips and two marker exclusions.
Portable worker tests and execution extraction are complete locally (see below).
Sol and Astra also accept the shared worker-launch handshake: backend wrappers retain
their descriptors and retirement rules while one native helper owns the protected
bootstrap/confirmation sequence. Exact process identity, handle transfer and original
deadlines remain intact; 57 focused tests pass with one platform skip and three marker
exclusions. [Source review and limits](review-evidence-2026-10-09/nongui-sol-launch.txt).
[Implementation evidence and native limits](review-evidence-2026-10-09/implementation-context.json).

Repairs under A02/A07/A08/E08 cover exact preparation/readback, absolute output paths,
Schedule/Release joining, preparation-parent lifecycle, normal end/MCU OFF, SDK stop
before bounded drain, bare cleanup commands and retained failure delivery. Completed
cleanup publishes durable owner ENDED; coordinator accepts only exact quiet terminal
liveness. Shutdown uses delivered closure without changing its identity and avoids
cancelling gRPC termination before server.stop. Run43 remains healthy idle and closes
normally with exact all-owned absence in retained evidence. Committed defaults are
restored; current local regression results are recorded in the implementation evidence. [Integration assessment](runtime.md#current-scope-and-review),
[raw evidence](rig-wiring-evidence-2026-10-08/dummy-experiment/).

Oct9 non-GUI implementation: Luna adds portable worker deadline, safety priority,
coordinator-loss, preview, cleanup/report and camera-readback coverage; preparation,
wait verification and health projection move to focused owners under
[ARCH-002](../architecture.md#arch-002). Execution falls from 620 to 482 lines.
Sol independently passes 55 cases with five platform skips and accepts the preserved
ownership/deadlines; Astra concurs. Original-source statement coverage rises from
28.30% to 53.15% across 1,159 statements; branch-inclusive coverage is a separate
24.53% to 47.83% measure. [Methods and limitations](review-evidence-2026-10-09/nongui-luna-worker.txt),
[Sol review](review-evidence-2026-10-09/nongui-sol-worker.txt).

Owned camera/pulse editing and failed-operation recovery now follow
[A10 revision 57](../docs/architecture/acquisition.md#a10) and
[A11 revision 41](../docs/architecture/acquisition.md#a11). Exact late evidence,
pending cleanup identities and confirmed claim/resource release remain distinct from
configuration adoption and readiness. The [cross-owner assessment](runtime.md#unresolved-findings-and-limitations)
records current implementation, review findings and validation limits.

Owner-selected video timing rules are now recorded in
[A07 revision 59 / A08 revision 50](../docs/architecture/acquisition.md#a08).
First usable receipt-time image per slot wins; later same-slot sources retain explicit
video omissions. Leading slots use explicitly labelled first-image backfill, and later
gaps repeat the last selected image. Entirely empty recordings retain existing handling.
The bounded writer retains one prepared image and emits explicit encoded-slot rows;
source rows, same-slot omissions and duplicate counts remain distinct. Tail work keeps
the encoder-progress watchdog active even after its source queue empties; retries retain
the original stall/finish bounds. Header and grid use the same canonical FFmpeg rate.
Frame-log schema 3 and fixed policy 19 bind these changes. Sol accepts the corrected
implementation after 71 focused cross-owner checks and 21 header/closure checks.
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
[Implementation handoff](review-evidence-2026-10-09/nongui-luna-padding.txt),
[Sol review](review-evidence-2026-10-09/nongui-sol-padding.txt).
No rig timing or encoder throughput pass is claimed.

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
config/policy 19 retains camera pins/rates and distributes the resolved serial timing
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

Historical recording attempts 22–28 repaired retained trial failure admission,
camera clock validation, gray raw input naming, cleanup result format, pre-Ready
encoder obligations, Schedule/Release ordering, GPU fence arguments, compositor
resource order and trial-parent forwarding. Their interrupted reservations and exact
exit evidence remain in the [dated bundle](rig-wiring-evidence-2026-10-08/dummy-experiment/).
Run43 completion/decode results above supersede the early incomplete-run assessment.
Oct9 restores source defaults; measured timing and full-workload acceptance remain open.
ARCH-002 keeps focused owners and existing behavior test modules.

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
Oct9 repairs feedback in both snapshot and ordinary camera-save paths: select/focus
the blocking Tracking row/input while retaining the Behavior draft and atomic whole-
configuration validation. The focused three-case offscreen selection passes using a
real validator error; actual native chooser/DPI behavior remains in the rig checklist.

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

Oct23 `hierarchical-code-review`: Luna reviewed current dummy-session admission,
output reservations/function scopes and recording lifecycle under A02/A07/E04;
no additional actionable defect was established. Existing failed-Setup/reuse
acceptance remains open. Tests were inspected, not rerun; source review is not
rig evidence. [Cross-owner validation and limits](runtime.md#maintainability-review).

Oct19 `code-sweep-oct19` applies [ARCH-002](../architecture.md#arch-002) under
the owner's behavior-preservation constraint. Removed six unused stored values:
recording release deadline/input-format copies, capture session-preview copy,
duplicate first-frame callback reference, never-used first-frame flag and tracking
transfer flag. Release deadline checks, resolved encoder input and actual readiness/
attachment evidence retain their existing owners under A02/A07/A08/E06. The
write-only session UUID is retained because its conversion also validates input.
`capture_handoff` now calls the identical existing idle acknowledgement operation;
the same condition lock and before/after-clear command/external-wake checks remain.
Ten cases extend the owning worker-foundations module to exercise both entry points
with no work, queued work and arrivals during clear. No package or policy added;
cohesive capture/recording/lifecycle owners retain their existing size exceptions.
The worker module passes 84 tests; the final integrated backend rerun passes 2,215
tests (six skips, 14 deselections), including all acquisition cases. Static checks
and packaging also pass; the current [check context](runtime-evidence-2026-10-19/code-sweep/context.json)
retains actual commands and initial fixture/sandbox failures.
[Sweep evidence](runtime-evidence-2026-10-19/code-sweep/baseline.json) records the
dirty-tree baseline. No native/rig acceptance is inferred.

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

## Camera trigger-anchor capability assessment

Oct14 source/documentation review identifies the cameras actually used in Oct13 rig
readbacks: Behavioral acA4112-30uc serial40065509; Tracking a2A2464-77umPRO
serial40747103. The Behavior PFS filename names a different model and is not identity
evidence. Both models document ExposureActive. Behavior exposes a resettable acquired-
image Counter1/CounterValue chunk, not an established count of all incoming triggers.
Basler's Counter related-chunk table uses inconsistent names for this model; the
Data Chunks model listing and general CounterValue description identify acquired-image
counting. Tracking has two configurable counters and selectable CounterValue chunks;
counting rising edges on its trigger input is a candidate requiring installed-node
and per-image latch verification. Current CephVR adapter does not read CounterValue.

The retained baseline has Behavior trigger Line4, output Line2=UserOutput1;
Tracking trigger Line2, Line3=input/source Off. CounterValue chunks are disabled
on both; Tracking counters are Off. These are historical Oct14 readbacks, not
current node queries. The former first-trigger/first-video-source assumption is
superseded by the [continuous-capture design](#continuous-camera-acquisition-design--2026-10-21)
under [A09](../docs/architecture/acquisition.md#a09). Existing hardware capability
evidence does not establish an absolute trigger/frame anchor or exposure latency.
See the [current rig checks](rig-verification.md#camera-no-wiring-anchoring).
Eye was disabled; its PFS filename is not confirmed model evidence for this check.

[Source hashes, documentation links and limitations](runtime-evidence-2026-10-14/camera-anchor-capabilities/context.json).
Official [counter](https://docs.baslerweb.com/counter),
[data chunks](https://docs.baslerweb.com/data-chunks) and
[line source](https://docs.baslerweb.com/line-source) documentation establish model
capability only. No installed capability query, acquisition, electrical test or
runtime change; reset/latch/drop and signal timing validation remains within the
existing paired/rig integration work.
