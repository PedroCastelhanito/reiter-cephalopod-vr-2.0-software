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

- [ ] `runtime-replacement-and-auto-control` [launcher] [gui] [shared] Owner/chat: runtime-preview Codex chat. MSIX AppData virtualization is proven to hide replacement/credential records from ordinary CMD. Await owner choice to amend E08 to a shared private profile root with recovery preservation/restart, or keep AppData with ordinary-CMD-only launch; then implement and verify cross-context visibility. — [Current assessment](reports/runtime.md#current-scope-and-review)

- [ ] `mcu-managed-connection-and-io` [gui] [controller] [acquisition] Owner/chat: signal-check Codex chat; runtime-preview chat completed authorized backup/manual upload/restart. Protocol-3 CAPS, direct D9/D10/D11 generated counts/reset/Stop/OFF, managed D9/D10/D11 Test/Status/Stop and D9 automatic timeout pass. Prior owner-requested shutdown confirmed exact absence/free guard; owner has since reopened runtime. Verify physical D2/receiver/LOW correlation and reconnect/watchdog wiring; generated counts do not prove electrical delivery. — [Installation and retest evidence](reports/rig-wiring-evidence-2026-10-07/mcu-installation-and-preview.md)

## Next

- [ ] `camera-preview-gui-binding` [gui] [controller] [acquisition] Fully restart for repaired visible-frame snap/fitting and verify actual camera opening outside GUI top-right, moved-GUI reopen and mixed-DPI/fallback behavior. Ten GUI, four final native/reader and 549 integration checks pass (two privilege skips); current owner runtime preserved. Existing Tracking health/sustained capture acceptance remains open. — [Current bounds and validation](reports/rig-wiring-evidence-2026-10-07/preview-snap-context.json)
- [ ] `camera-worker-coordinator-health` [acquisition] [supervisor] Resolve recurring COORDINATOR_HEALTH_LOST shutdown after Tracking preparation on protocol-3/repaired-preview runtime; retain original health/deadline rules and repeat Start/Stop/import/release. Latest fault cleanup has exact all-owned-process absence. — [Current rig evidence](reports/acquisition.md#current-windows-wiring-checks)

- [ ] `visual-renderer-startup-deadline` [visual_stimulus] [supervisor] Verify post-Setup renderer lifecycle/catalogue and remaining fault cleanup. Current seven-role startup/long idle and normal authenticated shutdown pass; these do not prove initialized projection or post-Setup behavior. Older intermittent native errors remain historical unresolved findings. — [Current assessment](reports/runtime.md#current-scope-and-review)

- [ ] `spikeglx-controller-integration` [spikeglx] [controller] [gui] Restore reachability and verify paired Setup/writing/monitor/stop and pulse inventory. Current saved-host readback passes; SDK diagnostic times out then logs TCP failure and an unretrieved late future exception. No remote mutation ran. — [Current assessment](reports/runtime.md#current-scope-and-review), [Rig checks](reports/rig-verification.md)
- [ ] `projector-calibration-launch` [gui] [visual_stimulus] Verify first-use untimed Launch/Close on all assigned outputs, physical corrections, restore/Idle and fault cleanup on the rig. Managed transport/rendering/ownership and local checks are accepted; optical/native acceptance remains open. — [V01](docs/architecture/visual_stimulus.md#v01), [Rig checks](reports/rig-verification.md)

- [ ] `legacy-camera-trigger-rate` [acquisition] [gui] Verify Behavior camera trigger acceptance with frame-rate limiter disabled and measured pulse/readiness correlation. Legacy logs confirm 17.44–17.75 fps with consecutive hardware IDs; limiter timing is a hypothesis, not proven causality. Forced limiter enable on startup/reload is fixed in the installed Basler dependency with 19 focused tests passing; selected PFS now stores enable=0. Restart legacy GUI before the bounded comparison; preserve scientific exposure settings. — [Evidence](reports/acquisition.md)
- [ ] `devices-narrow-overflow` [gui] Repair Windows layout/clipping failures and rerun owning GUI tests plus actual DPI/window inspection. Current offscreen suite has eight layout failures, including Devices overflow at 720/1175px, and one Qt/native path comparison fixture failure; native batch teardown also access-violates. — [Current assessment](reports/runtime.md#current-scope-and-review), [G02](docs/architecture/gui.md#g02)

- [ ] `trial-epoch-shuffle` [gui] Add a whole-trial epoch reorder action outside Batch generate, preserving group identity and undo history; settle how nested repeat/condition groups participate before implementation. — [G01](docs/architecture/gui.md#g01)
- [ ] `owned-camera-edits` [controller] [acquisition] Recheck and implement applying camera/pulse edits to owned editing/preview cameras under the existing contract. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `camera-readback-adoption` [controller] [acquisition] Review Setup and manual-camera readback paths; share compatible resolution/adoption logic while preserving their distinct checks. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `worker-launch-retirement` [supervisor] Recheck worker launch retention and release completed launches without losing required identity or replay evidence. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `shutdown-health-checks` [supervisor] Resolve gaps in controller-loss monitoring and timeout fencing during accepted shutdown, preserving original deadlines. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `pruned-launch-replay` [supervisor] Resolve PlanLaunch replay behavior after a released registry entry is pruned; retain the agreed replay guarantees. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `late-finished-recovery` [controller] [supervisor] Recheck startup inspection of logs containing late-Finished recovery events; preserve conservative handling of genuinely unconfirmed evidence. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `controller-audit-observations` [controller] Review ingress duplicate handling, pre-activation prompt cancellation, warning lock scope and unread fields before changing them; terminal retention is repaired and capacity bypass was not established. — [Observations](reports/runtime.md#unresolved-findings-and-limitations)

## Blocked

- [ ] `runtime-gui-rig-wiring-acceptance` [gui] [launcher] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Finish outstanding wiring acceptance after observed GUI/native-crash, MCU evidence and camera heartbeat repairs, remote reachability and missing projector inputs. Current execution/evidence/cleanup is recorded; blocked dependent tests are not passes. — [Current results](reports/rig-wiring-evidence-2026-10-07/README.md)

- [ ] `rig-acceptance` [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] Complete remaining Windows managed application/device/full-workload acceptance after locally accepted GUI wiring, required scientific/wiring inputs and owner-deferred encoder compatibility; development checks do not establish rig acceptance. — [Rig worklist](reports/rig-verification.md)

## Deferred

- [ ] `encoder-toolchain-owner-review` [acquisition] [visual_stimulus] Owner-deferred audit item 5: select/validate compatible encoder tools and existing settings before full-load acceptance; no encoder repair was authorized in this phase. — [Evidence and limits](reports/rig-audit-2026-10-01/README.md)

Owner-deferred scientific settings and firmware remain in their owning architecture/worklist records.
