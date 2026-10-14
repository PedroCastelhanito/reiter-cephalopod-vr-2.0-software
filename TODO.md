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

- [ ] `screen-frame-lateral-distance` [gui] [visual_stimulus] Reconcile retained51mm side distances (4mm lateral Bottom clearance) with owner-described5mm frame gaps;52mm fits centered94mm cross-span but requires measurement confirmation. Source-input discrepancy, optics unverified. — [Plot/assessment](reports/visual_stimulus.md)

- [ ] `mixed-subgroup-random-rule-edit` [gui] Reject or correctly apply random-rule edits across multiple batch identities; source inspection and local invalid-input probe show stored rules remain unchanged while the draft is cleared. — [Assessment](reports/runtime.md)

- [ ] `physical-surface-coordinate-origin` [visual_stimulus] Reconcile observed contract/renderer mismatch: stimulus-schema declares bottom-left local origin but physical_corners emits centered clip coordinates. Choose/migrate the intended contract before changing existing stimulus placement; linked-spin validation follows actual rendering without changing it. — [Assessment](reports/visual_stimulus.md)

- [ ] `projector-calibration-retention` [gui] Diagnose owner-reported calibration loss after closure using the actual closure path and saved/restored values; current normal-close regressions and all16 nonzero field roundtrips pass, so production cause is unverified. — [Investigation](reports/runtime.md)
- [ ] `gui-backend-dummy-experiment` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Complete remaining Eye/locomotion Tracking/paired/optical/electrical scientific acceptance within owner-approved scope and existing deferrals. Combined Behavior/Tracking recording now verifies nominal60fps/GPU placement and repeated reset; uniform frame time and zero-loss recording are not established. — [Current assessment](reports/runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)
- [ ] `combined-recording-loss` [acquisition] [visual_stimulus] Resolve sustained review throughput when projector tests resume: Oct14 camera queues17 have zero overflows but nominal-slot omissions remain; review21 saturates3078capacity drops/3098CFRduplicates. Original precision/quality/rates preserved and visual defaults restored. - [Assessment](reports/visual_stimulus.md)

- [ ] `native-picker-pytest-exception-hook` [gui] Diagnose native picker exit0xC0000409 with pytest's default faulthandler; the same23-case regression without that plugin and standalone native shell/cancellation proofs pass. Cause unverified; establish ordinary native suite compatibility. — [Runtime assessment](reports/runtime.md)

- [ ] `mcu-managed-connection-and-io` [gui] [controller] [acquisition] Installed COM8 protocol4/cephvr2_uno_4 readback and all3 configured triggers verified in combined run and12 preview cycles; no flashing. Complete electrical edge/LOW, watchdog-load/lease-expiry and interrupted-upload acceptance with instruments; preserve deferred physical mappings. Historical ON rejection cause remains unproven. - [Findings](reports/runtime-evidence-2026-10-14/rig-timing-audit/lifecycle-findings.json)

- [ ] `visual-renderer-startup-deadline` [visual_stimulus] [supervisor] Verify remaining renderer fault/deadline/catalogue cleanup cases on the rig. Retained run43 now exercises post-Setup recording, normal cleanup and shutdown; older intermittent native faults remain historical unresolved findings, not evidence that post-Setup has never run. — [Current assessment](reports/runtime.md#current-scope-and-review)

- [ ] `spikeglx-controller-integration` [spikeglx] [controller] [gui] Verify installed-version mapping and paired Setup/writing/monitor/stop after actual pulse inventory is supplied. Oct13 read-only reachability is restored at the saved endpoint, reporting idle SpikeGLX v20251218 api v4.1.3. Owner defers pulse mapping today; no remote mutation or paired acceptance ran. — [Current assessment](reports/runtime.md), [Rig checks](reports/rig-verification.md)
- [ ] `projector-calibration-launch` [gui] [visual_stimulus] Complete remaining frame/grid live-adjustment/physical/optical/fault acceptance with separate repository bars/frame-grid sources and per-step runtime copies. Oct14 repaired reference bars are visibly verified on all four outputs with GUI Close/reopen and authenticated state; digital visibility is not measured optics. Local source/copy/pixel-length/digest/cleanup regressions and GLB parsing pass; historical all-output-VSync Open/two adjustments/Close remains separate evidence, and dummy geometry is not measured calibration. — [Current assessment](reports/visual_stimulus.md), [V01](docs/architecture/visual_stimulus.md#v01)

- [ ] `devices-narrow-overflow` [gui] Camera action-row minimum width, wrapped projector timing caption and deferred table cell geometry fixed; nine focused native layout cases pass Oct14. Complete physical alternate-DPI/narrow inspection and MCU dropdown/add/remove checks; the app capture approval timed out, so no new visual inspection is claimed. — [Current assessment](reports/runtime.md), [G02](docs/architecture/gui.md#g02)

## Blocked

- [ ] `mcu-optional-io-and-all-vsync` [gui] [controller] [acquisition] [visual_stimulus] Complete disconnected/reconnected V19 startup, native MCU Apply and combined acceptance. Oct13 owner125ms margins/real Behavior+Tracking+stimulus Setup/recording/closure and actual GPU0-render/GPU1-encoding pass; two final combined sessions reach60.0333/60.0167 real groups/s and reset/restore passes. Recording drops and uniform/optical timing remain unverified acceptance items. Eye/electrical/full scientific acceptance remains deferred. — [Current evidence](reports/runtime.md), [Rig checks](reports/rig-verification.md)

- [ ] `eye-camera-and-connect-recovery` [gui] [controller] [supervisor] [acquisition] [shared] [visual_stimulus] Triggered Eye60Hz video/drain and four preview cycles now verified Oct14; complete full-session interrupted reuse after source repairs when projectors return, plus separate physical/GUI acceptance. Firmware upload manual; Tracking processing/photodiode/paired mappings deferred. - [Assessment](reports/acquisition.md)

- [ ] `runtime-gui-rig-wiring-acceptance` [gui] [launcher] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Complete combined/paired/Tracking scientific workload and native narrow/DPI/optical/electrical/full-load checks. Oct13 final two-camera+stimulus sessions pass nominal60fps, Setup/recording/closure and repeated reset with125ms margins; recording drops and timing jitter remain. Failed-Setup/Save-switch cleanup, Protocol hover failures and projector overflow remain open; Eye, locomotion Tracking, paired and full scientific acceptance remain rig-dependent. — [Current assessment](reports/runtime.md), [Rig checklist](reports/rig-verification.md)

- [ ] `rig-acceptance` [gui] [launcher] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] [shared] Complete remaining managed device/fault/full-workload acceptance. Oct13 static/contracts/schema/package, 1520 backend/native cases (five privilege skips), four-output Idle/grid live-update/closure and final exact shutdown/COM release pass. The native chooser crash is repaired; Protocol hover-test failures and projector overflow remain unresolved; matched 9.0.2 tool compatibility/synthetic closure pass; camera/Eye/pulse/electrical checks are owner-deferred today. — [Current assessment](reports/runtime.md), [Rig worklist](reports/rig-verification.md)

## Deferred

- [ ] `rig-timing-buffer-audit` [controller] [supervisor] [acquisition] [visual_stimulus] [spikeglx] [shared] [gui] Owner-deferred after projectors powered off Oct14: resume required full-session Abort/idle300s reuse, lifecycle receipt margins and sustained stimulus throughput. Owner queue20/SDK15/drain150 saved; prior queue17 measured with20% burst margin, full combined/SaveOff/preview checks pass; preserve Tracking/photodiode/paired mapping deferrals. - [Assessment](reports/runtime-evidence-2026-10-14/rig-timing-audit/configuration-assessment.json)
- [ ] `renderer-failed-setup-cleanup-link` [visual_stimulus] [controller] [supervisor] [acquisition] Projector-dependent native retest deferred by owner: verify complete failed Setup cancellation and fresh reuse after strict cleanup, bounded warning scope and release-receipt repairs. Fault6 backend proofs accepted but aggregate failed; latest local311 Visual/1229 other backend tests pass, native complete cancellation unproven. - [Findings](reports/runtime-evidence-2026-10-14/rig-timing-audit/lifecycle-findings.json)

- [ ] `projector-flip-input` [gui] [controller] [acquisition] Owner-deferred Oct14: no Projector flip input, diagnostics or camera-trigger phase-offset implementation until explicitly requested. — [A11](docs/architecture/acquisition.md#a11)

- [ ] `acquisition-shutdown-controller-rpc` [acquisition] [controller] Rig-deferred by owner: verify orderly teardown after exact controller departure without traceback and with truthful release evidence. Local handling/tests pass; live/unknown-controller failures still propagate. — [Current assessment](reports/acquisition.md), [Rig checks](reports/rig-verification.md)

- [ ] `legacy-camera-trigger-rate` [acquisition] [gui] Owner-deferred camera capture today (Oct13); later verify Behavior camera trigger acceptance with frame-rate limiter disabled and measured pulse/readiness correlation. Legacy logs confirm 17.44–17.75 fps with consecutive hardware IDs; limiter timing is a hypothesis, not proven causality. Forced limiter enable on startup/reload is fixed in the installed Basler dependency with 19 focused tests passing; selected PFS now stores enable=0. Restart legacy GUI before the bounded comparison; preserve scientific exposure settings. — [Evidence](reports/acquisition.md)

- [ ] `camera-preview-gui-binding` [gui] [controller] [acquisition] Complete GUI selector/button, alternate-monitor/DPI/fallback and repeated release/reuse acceptance when requested. Fresh Oct13 bounded audit passes real Behavior/Tracking identity, usable visible previews, Stop and exact release; earlier no-frame failure does not reproduce. Eye disabled/untested; broader physical checks remain deferred. — [Current assessment](reports/acquisition.md), [Rig checks](reports/rig-verification.md)

Owner-deferred scientific settings and firmware remain in their owning architecture/worklist records.
