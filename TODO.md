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


- [ ] `gui-backend-dummy-experiment` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Owner/chat: current Codex chat. Native runs 40–41 complete the 60 s unpaired trial/session and confirm cleanup; verify final shutdown fixes, externally decode/count the latest outputs and reconcile reduced camera/render rates. Restore temporary 1,000 ms drains, 2,000 ms preparation lead, pacing/GPU preferences and original draft/history; complete current regressions/reports. — [Current assessment](reports/runtime.md#current-scope-and-review)

- [ ] `runtime-replacement-and-auto-control` [launcher] [gui] [shared] Owner/chat: runtime-preview Codex chat. MSIX AppData virtualization is proven to hide replacement/credential records from ordinary CMD. Await owner choice to amend E08 to a shared private profile root with recovery preservation/restart, or keep AppData with ordinary-CMD-only launch; then implement and verify cross-context visibility. — [Current assessment](reports/runtime.md#current-scope-and-review)

## Next

- [ ] `video-cadence-padding` [acquisition] [visual_stimulus] Formalize slot assignment and leading-gap handling, then encoded-frame/source/duplicate schema and bounded writer changes for owner-selected padding; require an authorized coding increment and focused mapping/cutoff/closure coverage before implementation acceptance. — [A08](docs/architecture/acquisition.md#a08), [E13](docs/architecture/visual_stimulus.md#e13)

- [ ] `camera-configuration-validation-feedback` [gui] [controller] [acquisition] Explain cross-camera configuration blockers on the affected row and verify enabling/importing an initially incomplete Tracking configuration. Owner console reports Behavior PFS save rejected for enabled Tracking's missing external input; source review confirms whole-configuration submission, not a Behavior Line2 failure. — [Current assessment](reports/acquisition.md#current-windows-wiring-checks)

- [ ] `mcu-managed-connection-and-io` [gui] [controller] [acquisition] Complete electrical D2 source/receiver/LOW correlation, original-boundary and watchdog latency under load, actual chooser/button interaction and recoverable interrupted-upload/uncertain-cleanup injection. Oct8 controller-owned tests with acquisition disabled, generated D9/D10/D11 counts, native `.ino` compile/HEX verified upload, compiler-error preservation, active-D9 control release, isolated watchdog-stopped readback and exact shutdown/COM release pass after three focused repairs. Generated counts and stopped firmware state do not prove voltage or timing. Runtime is stopped. — [Current rig evidence](reports/rig-wiring-evidence-2026-10-08/README.md)

- [ ] `protocol-advanced-alignment` [gui] Reproduce and resolve the full-suite-only 12 px advanced-card displacement in `test_reference_advanced_controls_align_to_layer_and_retain_first`; an independent rerun passes, and the affected layout sources are unchanged by projector JSON work. — [Current assessment](reports/runtime.md#current-scope-and-review)

- [ ] `camera-preview-gui-binding` [gui] [controller] [acquisition] Verify actual selector/button interaction and alternate-monitor/DPI/left-fallback behavior. Oct8 real Behavior and repaired Tracking Connect/Show/Disconnect each pass twice with sustained visible capture and exact release; Behavior frames align at (1449,0) and moved-GUI (1473,24). Tracking's exact two-ring Ready/release validation is repaired. Runtime is stopped; ordered Tracking diagnostics remain in the rig checklist. — [Current rig evidence](reports/rig-wiring-evidence-2026-10-08/README.md#tracking-connect-and-release-correction)

- [ ] `visual-renderer-startup-deadline` [visual_stimulus] [supervisor] Verify post-Setup renderer lifecycle/catalogue and remaining fault cleanup. Current seven-role startup/long idle and normal authenticated shutdown pass; these do not prove initialized projection or post-Setup behavior. Older intermittent native errors remain historical unresolved findings. — [Current assessment](reports/runtime.md#current-scope-and-review)

- [ ] `spikeglx-controller-integration` [spikeglx] [controller] [gui] Restore reachability and verify paired Setup/writing/monitor/stop and pulse inventory. Current saved-host readback passes; SDK diagnostic times out then logs TCP failure and an unretrieved late future exception. No remote mutation ran. — [Current assessment](reports/runtime.md#current-scope-and-review), [Rig checks](reports/rig-verification.md)
- [ ] `projector-calibration-launch` [gui] [visual_stimulus] Verify first-use untimed Launch/Close on all assigned outputs, physical corrections, restore/Idle and fault cleanup on the rig. Managed transport/rendering/ownership and local checks are accepted; optical/native acceptance remains open. — [V01](docs/architecture/visual_stimulus.md#v01), [Rig checks](reports/rig-verification.md)

- [ ] `legacy-camera-trigger-rate` [acquisition] [gui] Verify Behavior camera trigger acceptance with frame-rate limiter disabled and measured pulse/readiness correlation. Legacy logs confirm 17.44–17.75 fps with consecutive hardware IDs; limiter timing is a hypothesis, not proven causality. Forced limiter enable on startup/reload is fixed in the installed Basler dependency with 19 focused tests passing; selected PFS now stores enable=0. Restart legacy GUI before the bounded comparison; preserve scientific exposure settings. — [Evidence](reports/acquisition.md)
- [ ] `devices-narrow-overflow` [gui] Complete native narrow-window/DPI inspection after the eight layout repairs; final repository validation includes 338 passing GUI cases and native wide-window camera controls render correctly. Drag did not resize the native window, so no narrow/DPI pass is claimed. Earlier native batch teardown access violation remains unverified by offscreen runs. — [Current assessment](reports/runtime.md#current-scope-and-review), [G02](docs/architecture/gui.md#g02)

- [ ] `trial-epoch-shuffle` [gui] Add a whole-trial epoch reorder action outside Batch generate, preserving group identity and undo history; settle how nested repeat/condition groups participate before implementation. — [G01](docs/architecture/gui.md#g01)
- [ ] `owned-camera-edits` [controller] [acquisition] Recheck and implement applying camera/pulse edits to owned editing/preview cameras under the existing contract. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `camera-readback-adoption` [controller] [acquisition] Review Setup and manual-camera readback paths; share compatible resolution/adoption logic while preserving their distinct checks. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `worker-launch-retirement` [supervisor] Recheck worker launch retention and release completed launches without losing required identity or replay evidence. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `shutdown-health-checks` [supervisor] Resolve gaps in controller-loss monitoring and timeout fencing during accepted shutdown, preserving original deadlines. Rejected or timed-out participant Shutdown requests now surface as supervisor warnings (2026-10-08); the controller-loss and fencing gaps remain. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `pruned-launch-replay` [supervisor] Resolve PlanLaunch replay behavior after a released registry entry is pruned; retain the agreed replay guarantees. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `late-finished-recovery` [controller] [supervisor] Recheck startup inspection of logs containing late-Finished recovery events; preserve conservative handling of genuinely unconfirmed evidence. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `controller-audit-observations` [controller] Review ingress duplicate handling, pre-activation prompt cancellation, warning lock scope and unread fields before changing them; terminal retention is repaired and capacity bypass was not established. — [Observations](reports/runtime.md#unresolved-findings-and-limitations)

- [ ] `acquisition-worker-portable-tests` [acquisition] Add portable tests with a fake camera adapter for `acquisition/worker/{execution,owner,cleanup_lifecycle,preview_lifecycle,health,report_dispatch,camera_resolution}.py` (about 1,300 statements, 0-8% covered), prioritising deadlines, cleanup and report delivery. Entry points and Windows launchers stay under rig acceptance. — [Coverage measurement](reports/review-evidence-2026-10-08/coverage.md)

## Blocked

- [ ] `runtime-gui-rig-wiring-acceptance` [gui] [launcher] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Available bounded Oct8 checks include native/controller/preview repairs, MCU compile/upload, both camera captures, reachable SpikeGLX and active saved projector assignments. Final suite passes 1566 including 338 GUI cases after layout/label/close repairs; shutdown history passes native restart. Full acceptance still needs native narrow/DPI, resolved pacing/pairing, experiment/scientific output and optical/electrical/full-load evidence. Follow the owning tasks above; bounded passes do not establish full rig acceptance. — [Current assessment](reports/runtime.md#current-scope-and-review), [Rig checklist](reports/rig-verification.md)

- [ ] `rig-acceptance` [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] Complete remaining Windows managed application/device/full-workload acceptance after locally accepted GUI wiring, required scientific/wiring inputs and owner-deferred encoder compatibility; development checks do not establish rig acceptance. — [Rig worklist](reports/rig-verification.md)

## For review

Behavior-preserving refactors the owner deferred on 2026-10-08. Each touches Windows-only or safety-critical code that local tests cannot validate (E15); none is a defect today.

- [ ] `worker-launch-handshake-sharing` [acquisition] [visual_stimulus] [shared] Merge the ~150-line PlanLaunch/ConfirmLaunch/bootstrap/GetLaunchState handshake that `acquisition/worker_launcher.py` and `visual_stimulus/worker_launcher.py` each hand-write into one shared helper with a single failure-path handle rule. Decide first whether rig validation is available. — [Review finding F-045](reports/review-evidence-2026-10-08/review-findings.md)
- [ ] `acquisition-execution-split` [acquisition] Split `acquisition/worker/execution.py` (complexity 33, 111 statements in one function, over the 500-line advisory) along its stages without changing deadlines or ownership. — [Review finding F-043](reports/review-evidence-2026-10-08/review-findings.md)
- [ ] `deadline-helper-sweep` [shared] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] Replace about 105 inline `max(0, (deadline - clock()) / 1e9)` conversions with `remaining_seconds` (about 38 sites already use it); consider consolidating it with `Deadline.remaining_ns`. Large diff; schedule when few files are changing. — [Review finding F-053](reports/review-evidence-2026-10-08/review-findings.md)

## Deferred

- [ ] `encoder-toolchain-owner-review` [acquisition] [visual_stimulus] Owner-deferred audit item 5: select/validate compatible encoder tools and existing settings before full-load acceptance; no encoder repair was authorized in this phase. — [Evidence and limits](reports/rig-audit-2026-10-01/README.md)

Owner-deferred scientific settings and firmware remain in their owning architecture/worklist records.
