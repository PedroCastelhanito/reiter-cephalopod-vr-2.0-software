# Tasks

Open work, grouped by status. The entry format and agent maintenance rules live in
[AGENTS.md](AGENTS.md#task-and-change-tracking). Completed work moves to [LOG.md](LOG.md).
Architecture owns decisions; backend reports own detailed findings and evidence.
Listing a task does not authorize a new implementation stage or lift a deferral.

Format: `- [ ] task-id [backend] [other-backend] Brief action and completion condition. — Context link`
Use a descriptive, stable ID in backticks. Add an owner/chat reference for work in
progress and a concrete reason for blocked/deferred work. Keep one entry per task.

The initial entries below come from the current runtime report. That report labels
the findings as retained source review; recheck the current code before changing it.
This is an initial backlog, not a claim that every existing report has been audited.

## In progress


- [ ] `mcu-managed-connection-and-io` [gui] [controller] [acquisition] Complete remaining managed I/O acceptance and receiver correlation. On 2026-10-06 owner-authorized verified upload restored CephVR2 protocol 2 firmware on COM8; prior legacy flash is backed up. Behavior D10 → Line4 receiver frames and ON/OFF acknowledgements pass. D9/D11/D2, waveform timing and full managed preview remain unverified. Owner: this Codex chat, paused by user. — [A11](docs/architecture/acquisition.md#a11), [Evidence](reports/acquisition.md#preview-recheck-stopped-by-owner-2026-10-06)
- [ ] `camera-preview-gui-binding` [gui] [controller] [acquisition] Dev-machine completion fix verified: controller now accepts explicit empty inactive preview IDs; real reporter-to-controller Start/Stop regressions pass. Affected suites: 417 passed, five skipped, one deselected; lint/format/mypy/boundaries pass. Rig work remains paused: repeat Behavior Preview/Stop/release and viewer verification, then Tracking. Direct D10 → Line4 receiver check previously yielded 41 frames in two seconds; latest saved rig Start failed exact completion missing. Local fix is not full rig acceptance or proof of the sole timeout cause. Owner: current Codex chat. — [Current assessment](reports/acquisition.md#preview-recheck-stopped-by-owner-2026-10-06), [Rig checklist](reports/rig-verification.md#managed-device-gui)

## Next

- [ ] `visual-renderer-startup-deadline` [visual_stimulus] [supervisor] Verify post-Setup renderer lifecycle/catalogue reports and resolve any remaining shutdown cleanup conflict without relaxing deadlines. Missing idle lifecycle and premature catalogue revision were fixed; a bounded live launch kept the Dashboard and all roles alive beyond 25 seconds. Native inspection now retries within its existing bound and retains unknown membership safely during shutdown. Managed camera checks pass after repairing worker admission; WinError 5 recurred during authenticated shutdown; its OS cause and full graceful cleanup acceptance remain open. The prior retained test runtime was stopped and its guard verified free; the latest preview test runtime was also stopped on 2026-10-06, with no CephVR2 processes and a free application guard. An intervening launch failed with VISUAL_STIMULUS_EVIDENCE / invalid UUID; this remains uninvestigated. A later launch also failed on SUPERVISOR_HEARTBEAT_FAILED, before the subsequent successful PFS/lease check; the rejection cause remains unisolated. GUI closure intentionally leaves the application running under E08; same-generation relaunch is implemented and locally accepted; Windows verification remains. Owner: current Codex chat. — [Observed runtime evidence](reports/runtime.md#dashboard-frontend-implementation), [Dated stderr](reports/gui-startup-evidence-2026-10-05/README.md), [E08](docs/architecture/system-contracts.md#e08)

- [ ] `spikeglx-controller-integration` [spikeglx] [controller] [gui] Verify managed connection, inventory pulse proof, paired Setup/writing/monitoring and stop edge cases on the rig. E12 implementation and development review/checks are accepted; paired/native evidence remains open. — [Current implementation](reports/runtime.md#current-scope-and-review), [Rig checks](reports/rig-verification.md)
- [ ] `projector-calibration-launch` [gui] [visual_stimulus] Verify first-use untimed Launch/Close on all assigned outputs, physical corrections, restore/Idle and fault cleanup on the rig. Managed transport/rendering/ownership and local checks are accepted; optical/native acceptance remains open. — [V01](docs/architecture/visual_stimulus.md#v01), [Rig checks](reports/rig-verification.md)

- [ ] `runtime-replacement-and-auto-control` [launcher] [gui] Verify Windows terminal N/Y replacement, exact process absence before new launch, automatic unheld GUI control, explicit takeover and reconnect acknowledgement. Local implementation/checks pass; native acceptance pending. Older launchers need one manual shutdown. — [Implementation evidence](reports/runtime.md#current-scope-and-review), [Rig checks](reports/rig-verification.md#managed-device-gui)

- [ ] `legacy-camera-trigger-rate` [acquisition] [gui] Verify Behavior camera trigger acceptance with frame-rate limiter disabled and measured pulse/readiness correlation. Legacy logs confirm 17.44–17.75 fps with consecutive hardware IDs; limiter timing is a hypothesis, not proven causality. Forced limiter enable on startup/reload is fixed in the installed Basler dependency with 19 focused tests passing; selected PFS now stores enable=0. Restart legacy GUI before the bounded comparison; preserve scientific exposure settings. — [Evidence](reports/acquisition.md)
- [ ] `devices-narrow-overflow` [gui] Verify the 720px Devices layout on Windows DPI after local responsive-control repairs and accepted managed captures. The earlier rig probe found Camera 28–48px and Projectors 164px overflow; local passes do not close that Windows observation. — [Frontend evidence](reports/runtime.md#dashboard-frontend-implementation), [G02](docs/architecture/gui.md#g02)

- [ ] `trial-epoch-shuffle` [gui] Add a whole-trial epoch reorder action outside Batch generate, preserving group identity and undo history; settle how nested repeat/condition groups participate before implementation. — [G01](docs/architecture/gui.md#g01)
- [ ] `owned-camera-edits` [controller] [acquisition] Recheck and implement applying camera/pulse edits to owned editing/preview cameras under the existing contract. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `camera-readback-adoption` [controller] [acquisition] Review Setup and manual-camera readback paths; share compatible resolution/adoption logic while preserving their distinct checks. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `worker-launch-retirement` [supervisor] Recheck worker launch retention and release completed launches without losing required identity or replay evidence. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `shutdown-health-checks` [supervisor] Resolve gaps in controller-loss monitoring and timeout fencing during accepted shutdown, preserving original deadlines. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `pruned-launch-replay` [supervisor] Resolve PlanLaunch replay behavior after a released registry entry is pruned; retain the agreed replay guarantees. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `late-finished-recovery` [controller] [supervisor] Recheck startup inspection of logs containing late-Finished recovery events; preserve conservative handling of genuinely unconfirmed evidence. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `controller-audit-observations` [controller] Review ingress duplicate handling, pre-activation prompt cancellation, warning lock scope and unread fields before changing them; terminal retention is repaired and capacity bypass was not established. — [Observations](reports/runtime.md#unresolved-findings-and-limitations)

## Blocked

- [ ] `rig-acceptance` [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] Complete remaining Windows managed application/device/full-workload acceptance after locally accepted GUI wiring, required scientific/wiring inputs and owner-deferred encoder compatibility; development checks do not establish rig acceptance. — [Rig worklist](reports/rig-verification.md)

## Deferred

- [ ] `encoder-toolchain-owner-review` [acquisition] [visual_stimulus] Owner-deferred audit item 5: select/validate compatible encoder tools and existing settings before full-load acceptance; no encoder repair was authorized in this phase. — [Evidence and limits](reports/rig-audit-2026-10-01/README.md)

Owner-deferred scientific settings and firmware remain in their owning architecture/worklist records.
