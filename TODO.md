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

- [ ] `runtime-replacement-and-auto-control` [launcher] [gui] [shared] Owner/chat: runtime-preview Codex chat. MSIX AppData virtualization is proven to hide replacement/credential records from ordinary CMD. Await owner choice to amend E08 to a shared private profile root with recovery preservation/restart, or keep AppData with ordinary-CMD-only launch; then implement and verify cross-context visibility. — [Current assessment](reports/runtime.md#current-scope-and-review)

## Next

- [ ] `mcu-managed-connection-and-io` [gui] [controller] [acquisition] Complete electrical D2 source/receiver/LOW correlation, original-boundary and watchdog latency under load, actual chooser/button interaction and recoverable interrupted-upload/uncertain-cleanup injection. Oct8 controller-owned tests with acquisition disabled, generated D9/D10/D11 counts, native `.ino` compile/HEX verified upload, compiler-error preservation, active-D9 control release, isolated watchdog-stopped readback and exact shutdown/COM release pass after three focused repairs. Generated counts and stopped firmware state do not prove voltage or timing. Runtime is stopped. — [Current rig evidence](reports/rig-wiring-evidence-2026-10-08/README.md)

- [ ] `camera-preview-gui-binding` [gui] [controller] [acquisition] Verify actual selector/button interaction and alternate-monitor/DPI/left-fallback behavior. Oct8 real Behavior and repaired Tracking Connect/Show/Disconnect each pass twice with sustained visible capture and exact release; Behavior frames align at (1449,0) and moved-GUI (1473,24). Tracking's exact two-ring Ready/release validation is repaired. Runtime is stopped; ordered Tracking diagnostics remain in the rig checklist. — [Current rig evidence](reports/rig-wiring-evidence-2026-10-08/README.md#tracking-connect-and-release-correction)

- [ ] `visual-renderer-startup-deadline` [visual_stimulus] [supervisor] Verify remaining renderer fault/deadline/catalogue cleanup cases on the rig. Retained run43 now exercises post-Setup recording, normal cleanup and shutdown; older intermittent native faults remain historical unresolved findings, not evidence that post-Setup has never run. — [Current assessment](reports/runtime.md#current-scope-and-review)

- [ ] `spikeglx-controller-integration` [spikeglx] [controller] [gui] Restore remote reachability and verify paired Setup/writing/monitor/stop and pulse inventory. Oct9 repairs and tests late SDK outcome observation while preserving native busy ownership; no remote mutation or paired acceptance ran. — [Findings](reports/runtime.md#unresolved-findings-and-limitations), [Rig checks](reports/rig-verification.md)
- [ ] `projector-calibration-launch` [gui] [visual_stimulus] Verify first-use untimed Launch/Close on all assigned outputs, physical corrections, restore/Idle and fault cleanup on the rig. Managed transport/rendering/ownership and local checks are accepted; optical/native acceptance remains open. — [V01](docs/architecture/visual_stimulus.md#v01), [Rig checks](reports/rig-verification.md)

- [ ] `legacy-camera-trigger-rate` [acquisition] [gui] Verify Behavior camera trigger acceptance with frame-rate limiter disabled and measured pulse/readiness correlation. Legacy logs confirm 17.44–17.75 fps with consecutive hardware IDs; limiter timing is a hypothesis, not proven causality. Forced limiter enable on startup/reload is fixed in the installed Basler dependency with 19 focused tests passing; selected PFS now stores enable=0. Restart legacy GUI before the bounded comparison; preserve scientific exposure settings. — [Evidence](reports/acquisition.md)
- [ ] `devices-narrow-overflow` [gui] Complete native narrow-window/DPI inspection after the eight layout repairs; final repository validation includes 338 passing GUI cases and native wide-window camera controls render correctly. Drag did not resize the native window, so no narrow/DPI pass is claimed. Earlier native batch teardown access violation remains unverified by offscreen runs. — [Current assessment](reports/runtime.md#current-scope-and-review), [G02](docs/architecture/gui.md#g02)

- [ ] `trial-epoch-shuffle` [gui] Add a whole-trial epoch reorder action outside Batch generate, preserving group identity and undo history; settle how nested repeat/condition groups participate before implementation. — [G01](docs/architecture/gui.md#g01)

## Blocked

- [ ] `gui-backend-dummy-experiment` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Diagnose stimulus throughput with controlled per-stage measurements on the Windows rig. Local run43 analysis and cadence-padding implementation are complete; the retained 60 s unpaired run reports cameras 29.95/59.93 fps and stimulus 19.7 fps. Further measurement is blocked on the intended native workload/rig; padding does not establish physical presentation rate, full-load or paired/scientific acceptance. — [Current assessment](reports/runtime.md#current-scope-and-review)

- [ ] `runtime-gui-rig-wiring-acceptance` [gui] [launcher] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Retained Oct8 run43 completes the unpaired 60 s experiment/output decode/cleanup/shutdown after MCU/camera/projector repairs. Oct9 restores defaults and completes current local regression checks. Acceptance remains blocked on stimulus throughput, paired/Tracking scientific workload and native narrow/DPI/optical/electrical/full-load checks. — [Current assessment](reports/runtime.md#current-scope-and-review), [Rig checklist](reports/rig-verification.md)

- [ ] `rig-acceptance` [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] Complete remaining Windows managed application/device/full-workload acceptance, including Oct9 exact camera retirement/reuse, fault-injected shutdown and recovery-log checks. Required scientific/wiring inputs and owner-deferred encoder compatibility remain pending; local checks do not establish rig acceptance. — [Rig worklist](reports/rig-verification.md)

## Deferred

- [ ] `encoder-toolchain-owner-review` [acquisition] [visual_stimulus] Owner-deferred audit item 5: select/validate compatible encoder tools and existing settings before full-load acceptance; no encoder repair was authorized in this phase. — [Evidence and limits](reports/rig-audit-2026-10-01/README.md)

Owner-deferred scientific settings and firmware remain in their owning architecture/worklist records.
