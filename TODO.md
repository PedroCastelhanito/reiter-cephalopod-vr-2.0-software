# Tasks

Open work, grouped by status. The entry format and agent maintenance rules live in
[AGENTS.md](AGENTS.md#task-and-change-tracking). Completed work moves to [LOG.md](LOG.md).
Architecture owns decisions; backend reports own detailed findings and evidence.
Listing a task does not authorize a new implementation stage or lift a deferral.

Format: `- [ ] task-id [backend] [other-backend] Brief action and completion condition. — Context link`
Use a descriptive, stable ID in backticks. Add an owner/chat reference for work in
progress and a concrete reason for blocked/deferred work. Keep one entry per task.

Entries link to current source/implementation assessments and their validation limits.
Recheck source findings before implementation; local completion does not close rig checks.

## In progress











## Next

- [ ] `mixed-subgroup-random-rule-edit` [gui] Reject or correctly apply random-rule edits across multiple batch identities; source inspection and local invalid-input probe show stored rules remain unchanged while the draft is cleared. — [Assessment](reports/runtime.md)

- [ ] `physical-surface-coordinate-origin` [visual_stimulus] Reconcile observed contract/renderer mismatch: stimulus-schema declares bottom-left local origin but physical_corners emits centered clip coordinates. Choose/migrate the intended contract before changing existing stimulus placement; linked-spin validation follows actual rendering without changing it. — [Assessment](reports/visual_stimulus.md)


- [ ] `projector-calibration-retention` [gui] Diagnose owner-reported calibration loss after closure using the actual closure path and saved/restored values; current normal-close regressions and all16 nonzero field roundtrips pass, so production cause is unverified. — [Investigation](reports/runtime.md)
- [ ] `gui-backend-dummy-experiment` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Complete remaining Eye/locomotion Tracking/paired/optical/electrical scientific acceptance within owner-approved scope and existing deferrals. Combined Behavior/Tracking recording now verifies nominal60fps/GPU placement and repeated reset; uniform frame time and zero-loss recording are not established. — [Current assessment](reports/runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)
- [ ] `combined-recording-loss` [acquisition] [visual_stimulus] Investigate observed recording loss while preserving nominal60fps presentation: camera queue drops6/19 and review2367 capacity drops/2424 padding duplicates in final60s repeat. Maintain exact accounting, ownership and bounds. — [Current evidence](reports/runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)

- [ ] `stimulus-save-switch-cleanup` [visual_stimulus] Verify the dedicated native Save On→Save Off transition after preparation receipt-scope repair. Repeated Save On→On cleanup/reset now passes; preserve exact ownership/catalogue/deadlines and do not infer Save-Off hardware acceptance from that result. — [Current assessment](reports/visual_stimulus.md), [Historical failure](reports/runtime-evidence-2026-10-13/throughput/baseline-off.json)

- [ ] `native-picker-pytest-exception-hook` [gui] Diagnose native picker exit0xC0000409 with pytest's default faulthandler; the same23-case regression without that plugin and standalone native shell/cancellation proofs pass. Cause unverified; establish ordinary native suite compatibility. — [Runtime assessment](reports/runtime.md)

- [ ] `native-protocol-hover-tests` [gui] Diagnose two real-Windows Protocol hover-control lookup tests failing with StopIteration; isolated repeats construct zero file dialogs. Establish whether native input/geometry or fixture timing causes the failures before claiming production behavior or native GUI acceptance. — [Current assessment](reports/runtime.md), [Native evidence](reports/runtime-evidence-2026-10-13/native-chooser/context.json)


- [ ] `mcu-managed-connection-and-io` [gui] [controller] [acquisition] Verify the fresh-GUI Eye pin9/60Hz diagnostic after the local submission repair, including installed protocol compatibility; complete original-boundary/watchdog latency under load and recoverable interrupted-upload/uncertain-cleanup injection. Oct13 COM8 Connect confirms protocol 3 / cephvr2_uno_2 with stopped camera outputs and final exclusive COM release; earlier verified GUI uploads remain historical passes. Electrical D2/source/receiver/LOW measurements are owner-deferred today. — [MCU submission repair](reports/runtime.md), [Current assessment](reports/acquisition.md), [Rig checks](reports/rig-verification.md)

- [ ] `visual-renderer-startup-deadline` [visual_stimulus] [supervisor] Verify remaining renderer fault/deadline/catalogue cleanup cases on the rig. Retained run43 now exercises post-Setup recording, normal cleanup and shutdown; older intermittent native faults remain historical unresolved findings, not evidence that post-Setup has never run. — [Current assessment](reports/runtime.md#current-scope-and-review)

- [ ] `spikeglx-controller-integration` [spikeglx] [controller] [gui] Verify installed-version mapping and paired Setup/writing/monitor/stop after actual pulse inventory is supplied. Oct13 read-only reachability is restored at the saved endpoint, reporting idle SpikeGLX v20251218 api v4.1.3. Owner defers pulse mapping today; no remote mutation or paired acceptance ran. — [Current assessment](reports/runtime.md), [Rig checks](reports/rig-verification.md)
- [ ] `projector-calibration-launch` [gui] [visual_stimulus] Regenerate ordinary diagnostic bundle: fresh normal Open fails mixed-pacing validation; separate accepted all-output-VSync profile passes Open/two adjustments/Close. Then complete GUI/reference-bar/physical/optical/fault acceptance; dummy geometry is not measured calibration. — [Current assessment](reports/visual_stimulus.md), [V01](docs/architecture/visual_stimulus.md#v01)

- [ ] `devices-narrow-overflow` [gui] Fix/retest Oct13 Windows projector configuration horizontal overflow (15-pixel range in three offscreen cases at width 1175), then complete native narrow/DPI and MCU dropdown/add/remove inspection. Current offscreen suite: 396 passes/three failures; native wide cards inspected, resize drag ineffective. — [Current assessment](reports/runtime.md), [G02](docs/architecture/gui.md#g02)

## Blocked


- [ ] `mcu-optional-io-and-all-vsync` [gui] [controller] [acquisition] [visual_stimulus] Complete disconnected/reconnected V19 startup, native MCU Apply and combined acceptance. Oct13 owner125ms margins/real Behavior+Tracking+stimulus Setup/recording/closure and actual GPU0-render/GPU1-encoding pass; two final combined sessions reach60.0333/60.0167 real groups/s and reset/restore passes. Recording drops and uniform/optical timing remain unverified acceptance items. Eye/electrical/full scientific acceptance remains deferred. — [Current evidence](reports/runtime.md), [Rig checks](reports/rig-verification.md)

- [ ] `eye-camera-and-connect-recovery` [gui] [controller] [supervisor] [acquisition] [shared] [visual_stimulus] GUI/backend chat: protocol4 independent Eye MCU output and Add pin workflow are locally implemented/compiled under owner authorization. Complete manual firmware upgrade, explicit physical Eye pin/FrameStart source/rate and triggered capture/video/cleanup acceptance; physical capture/electrical checks remain owner-deferred. Existing canceled Connect recovery and native identity checks remain valid within their scope. Earlier protocol3 installation and four-output VSync checks are historical evidence, not protocol4 or three-camera acceptance. — [Acquisition assessment](reports/acquisition.md), [Rig checks](reports/rig-verification.md)

- [ ] `runtime-gui-rig-wiring-acceptance` [gui] [launcher] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Complete combined/paired/Tracking scientific workload and native narrow/DPI/optical/electrical/full-load checks. Oct13 final two-camera+stimulus sessions pass nominal60fps, Setup/recording/closure and repeated reset with125ms margins; recording drops and timing jitter remain. Failed-Setup/Save-switch cleanup, Protocol hover failures and projector overflow remain open; Eye, locomotion Tracking, paired and full scientific acceptance remain rig-dependent. — [Current assessment](reports/runtime.md), [Rig checklist](reports/rig-verification.md)

- [ ] `rig-acceptance` [gui] [launcher] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] [shared] Complete remaining managed device/fault/full-workload acceptance. Oct13 static/contracts/schema/package, 1520 backend/native cases (five privilege skips), four-output Idle/grid live-update/closure and final exact shutdown/COM release pass. The native chooser crash is repaired; Protocol hover-test failures and projector overflow remain unresolved; matched 9.0.2 tool compatibility/synthetic closure pass; camera/Eye/pulse/electrical checks are owner-deferred today. — [Current assessment](reports/runtime.md), [Rig worklist](reports/rig-verification.md)

## Deferred

- [ ] `renderer-failed-setup-cleanup-link` [visual_stimulus] [controller] [supervisor] Rig-deferred by owner: repeat failed Setup after prior closed calibration, exact cleanup/recovery and permitted reuse. Local worker-recovery command/report routing and endpoint teardown are repaired/tested; complete historical workflow remains unverified. Missing-config SpikeGLX warning remains conservative without durable unpaired proof. — [Current assessment](reports/visual_stimulus.md), [Rig checks](reports/rig-verification.md)

- [ ] `acquisition-shutdown-controller-rpc` [acquisition] [controller] Rig-deferred by owner: verify orderly teardown after exact controller departure without traceback and with truthful release evidence. Local handling/tests pass; live/unknown-controller failures still propagate. — [Current assessment](reports/acquisition.md), [Rig checks](reports/rig-verification.md)

- [ ] `manual-camera-repeat-admission` [controller] [acquisition] [gui] [shared] Rig-deferred by owner: repeat real preview starts/stops in one generation after terminal-result reservation compaction; capture lease/claim state for separately unproven MCU pending/unavailable. Local fourth-readback capacity defect is fixed under unchanged budgets and replay retention. — [Current assessment](reports/acquisition.md), [Rig checks](reports/rig-verification.md)

- [ ] `legacy-camera-trigger-rate` [acquisition] [gui] Owner-deferred camera capture today (Oct13); later verify Behavior camera trigger acceptance with frame-rate limiter disabled and measured pulse/readiness correlation. Legacy logs confirm 17.44–17.75 fps with consecutive hardware IDs; limiter timing is a hypothesis, not proven causality. Forced limiter enable on startup/reload is fixed in the installed Basler dependency with 19 focused tests passing; selected PFS now stores enable=0. Restart legacy GUI before the bounded comparison; preserve scientific exposure settings. — [Evidence](reports/acquisition.md)

- [ ] `camera-preview-gui-binding` [gui] [controller] [acquisition] Complete GUI selector/button, alternate-monitor/DPI/fallback and repeated release/reuse acceptance when requested. Fresh Oct13 bounded audit passes real Behavior/Tracking identity, usable visible previews, Stop and exact release; earlier no-frame failure does not reproduce. Eye disabled/untested; broader physical checks remain deferred. — [Current assessment](reports/acquisition.md), [Rig checks](reports/rig-verification.md)

Owner-deferred scientific settings and firmware remain in their owning architecture/worklist records.
