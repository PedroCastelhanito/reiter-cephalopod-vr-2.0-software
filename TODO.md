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


- [ ] `scientific-evidence-rig` [acquisition] [visual_stimulus] [controller] [gui] Verify always-saved scientific evidence with video On→Off→On, native resource absence, exact counters/state/cutoffs, cancellation and storage failure. Local implementation/tests complete; preserve wiring/cadence and existing Eye/physical/paired deferrals. — [Rig checks](reports/rig-verification.md#always-saved-scientific-evidence)

- [ ] `camera-no-wiring-anchor` [acquisition] [spikeglx] Rig-check the accepted first-trigger/first-video-source assumption using saved source/video mappings, native timing and leading-loss diagnostics; label it assumed and report mismatches. Keep wiring/cadence unchanged; stronger anchoring deferred unless needed. — [Rig checks](reports/rig-verification.md#camera-no-wiring-anchoring), [Assessment](reports/acquisition.md#camera-trigger-anchor-capability-assessment)


- [ ] `projector-calibration-retention` [gui] Diagnose owner-reported calibration loss after closure using the actual closure path and saved/restored values; normal-close regressions, a launch/adjust/close state-cycle test and old-file (version 4/7) loading pass, so the production cause is still unverified. — [Investigation](reports/runtime.md), [Rework](reports/visual_stimulus.md#calibration-arena-asset)
- [ ] `gui-backend-dummy-experiment` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Complete remaining Eye/locomotion Tracking/paired/optical/electrical scientific acceptance within owner-approved scope and existing deferrals. Combined Behavior/Tracking recording now verifies nominal60fps/GPU placement and repeated reset; uniform frame time and zero-loss recording are not established. — [Current assessment](reports/runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)
- [ ] `combined-recording-loss` [acquisition] [visual_stimulus] Investigate observed recording loss while preserving nominal60fps presentation: camera queue drops6/19 and review2367 capacity drops/2424 padding duplicates in final60s repeat. Maintain exact accounting, ownership and bounds. Owner calls the stimulus-video loss unacceptable (Oct14). Local owned-buffer handoff, bounded metrics and half-size review composite now implemented/tested; rig drop reduction remains unverified. Measure remaining capture_slots=3 pressure, conversion and encoder contention under combined load. — [Current evidence](reports/runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)

- [ ] `stimulus-encode-benchmark` [visual_stimulus] Rig: benchmark the prepared reduced RGBA composite (1280x1000 for the previous2560x2000 layout) at60fps alone and with camera encoders; retain actual recipe/arguments plus renderer stderr JSON recording_metrics exit summaries (verify collection before benchmark) for readback poll, queue, normalization, pipe-call time, slot lifetime/occupancy and zero-progress writes. Completion: bottleneck evidence and real-frame drops/padding recorded; local correctness passes do not prove throughput. — [Current implementation](reports/visual_stimulus.md), [Rig checklist](reports/rig-verification.md) — [Reviewed test plan/helper (15 offline tests; native execution pending)](reports/rig-verification.md#encoding-test-plan)
- [ ] `stimulus-capture-slots-trial` [visual_stimulus] After rig timing measurements, evaluate capture slot count using actual reduced frame bytes and full scratch/retained-frame accounting within recording_bytes_total. Only increase for measured burst stalls; sustained slow encoding needs another remedy. Keep bounded memory and exact admission/drop accounting. — [Current implementation](reports/visual_stimulus.md), [V12](docs/architecture/visual_stimulus.md#v12)
- [ ] `stimulus-review-encoding-cost` [visual_stimulus] [acquisition] Rig encoding tests for all four sources: Behavior CQ16/color 4:4:4, Tracking CQ16/mono, Eye and Stimulus CQ23/mono test overrides versus standard CQ16; all p4, original camera dimensions and half-size stimulus review composite. Verify effective saved arguments, decoded dimensions/depth/color or neutral chroma, visual detail, file size/bitrate, throughput and real-frame drops/padding separately and under combined load. Future color Stimulus must retain 4:4:4. Completion: dated build/GPU/settings/workload evidence in owning reports and owner evaluation retaining or reverting CQ23; preserve Eye readiness/rig deferrals and do not silently overwrite saved lists. — [Acquisition](reports/acquisition.md), [Visual Stimulus](reports/visual_stimulus.md), [Rig checklist](reports/rig-verification.md), [E13](docs/architecture/visual_stimulus.md#e13) — [Reviewed test plan/helper (15 offline tests; native execution pending)](reports/rig-verification.md#encoding-test-plan)
- [ ] `stimulus-readback-off-gl-thread` [visual_stimulus] Deferred until rig measurements justify further optimization: evaluate remaining PBO map/copy off the GL thread, bounded PBO reuse, CPU row-flip elimination and RGB/mono capture layouts. Redundant handoff copy is already removed locally. Preserve ownership, ordered identity, deadlines/cleanup and prepared pixel ABI; V12 amendment before changing GL ownership. — [Current implementation](reports/visual_stimulus.md), [V12](docs/architecture/visual_stimulus.md#v12)

- [ ] `stimulus-save-switch-cleanup` [visual_stimulus] Verify the dedicated native Save On→Save Off transition after preparation receipt-scope repair. Repeated Save On→On cleanup/reset now passes; preserve exact ownership/catalogue/deadlines and do not infer Save-Off hardware acceptance from that result. — [Current assessment](reports/visual_stimulus.md), [Historical failure](reports/runtime-evidence-2026-10-13/throughput/baseline-off.json)

- [ ] `native-picker-pytest-exception-hook` [gui] Diagnose native picker exit0xC0000409 with pytest's default faulthandler; the same23-case regression without that plugin and standalone native shell/cancellation proofs pass. Cause unverified; establish ordinary native suite compatibility. — [Runtime assessment](reports/runtime.md)

- [ ] `native-protocol-hover-tests` [gui] Diagnose two real-Windows Protocol hover-control lookup tests failing with StopIteration; isolated repeats construct zero file dialogs. Establish whether native input/geometry or fixture timing causes the failures before claiming production behavior or native GUI acceptance. — [Current assessment](reports/runtime.md), [Native evidence](reports/runtime-evidence-2026-10-13/native-chooser/context.json)

- [ ] `mcu-managed-connection-and-io` [gui] [controller] [acquisition] Verify the fresh-GUI Eye pin9/60Hz diagnostic after the local submission repair, including installed protocol compatibility; complete original-boundary/watchdog latency under load and recoverable interrupted-upload/uncertain-cleanup injection. Oct13 COM8 Connect confirms protocol 3 / cephvr2_uno_2 with stopped camera outputs and final exclusive COM release; earlier verified GUI uploads remain historical passes. Electrical D2/source/receiver/LOW measurements are owner-deferred today. — [MCU submission repair](reports/runtime.md), [Current assessment](reports/acquisition.md), [Rig checks](reports/rig-verification.md)

- [ ] `visual-renderer-startup-deadline` [visual_stimulus] [supervisor] Verify remaining renderer fault/deadline/catalogue cleanup cases on the rig. Retained run43 now exercises post-Setup recording, normal cleanup and shutdown; older intermittent native faults remain historical unresolved findings, not evidence that post-Setup has never run. — [Current assessment](reports/runtime.md#current-scope-and-review)

- [ ] `spikeglx-controller-integration` [spikeglx] [controller] [gui] Verify installed-version mapping and paired Setup/writing/monitor/stop after actual Behavioral/Tracking/Eye pulse channel/bit inventory is checked on the rig and supplied; Eye software support is locally complete. Oct13 read-only reachability is restored at the saved endpoint, reporting idle SpikeGLX v20251218 api v4.1.3. Owner defers pulse mapping today; no remote mutation or paired acceptance ran. — [Current assessment](reports/runtime.md), [Rig checks](reports/rig-verification.md) Camera-anchor follow-up follows the owner's no-wiring constraint; see `camera-no-wiring-anchor`. — [Capability assessment](reports/acquisition.md#camera-trigger-anchor-capability-assessment)
- [ ] `projector-calibration-launch` [gui] [visual_stimulus] Rig-test the reworked workflow: per-projector reference view (frame, ticks, guide), edge margins and keystone with live updates, seam check, native binding at Windows scaling above 100 %, a late-completing Open, then physical/optical/fault acceptance. The earlier mixed-pacing failure was an older bundle; Launch rewrites it and the current builder passes the pacing overlay locally. Dummy geometry is not measured calibration. — [Current assessment](reports/visual_stimulus.md), [V01](docs/architecture/visual_stimulus.md#v01)

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
