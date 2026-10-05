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

- [ ] `spikeglx-controller-integration` [spikeglx] [controller] [gui] Verify the new controller-owned SDK connection diagnostic from the managed GUI once launcher job inspection is stable; direct rig readback and authenticated RPC/GUI intent checks pass. Then implement E12 Setup, writing, monitoring and stop safeguards before paired sessions; pulse proof remains open. Owner: current Codex chat. — [Control contract](contracts/spikeglx-control.md), [Evidence](reports/spikeglx-evidence-2026-10-05/README.md)
- [ ] `visual-renderer-startup-deadline` [visual_stimulus] [supervisor] Verify post-Setup renderer lifecycle/catalogue reports and resolve any remaining shutdown cleanup conflict without relaxing deadlines. Missing idle lifecycle and premature catalogue revision were fixed; a bounded live launch kept the Dashboard and all roles alive beyond 25 seconds. An earlier intermittent native process-inspection access error remains unisolated. GUI closure intentionally leaves the application running under E08; explicit GUI relaunch for that generation is not yet implemented. Owner: current Codex chat. — [Observed runtime evidence](reports/runtime.md#dashboard-frontend-implementation), [Dated stderr](reports/gui-startup-evidence-2026-10-05/README.md), [E08](docs/architecture/system-contracts.md#e08)
- [ ] `mcu-managed-connection-and-io` [gui] [controller] [acquisition] Verify managed diagnostic RPCs and bounded output/input behavior with receiver observation. Managed Save pins now includes D10/D11 and camera Test routes the saved role signals; focused tests pass, but the live managed UI route and receiver observation remain unverified. Earlier local real-device diagnostic reported 120 D2 rising edges with source unobserved. Confirm destination channels and voltage compatibility before D9/D10/D11 output tests; correlate D2 counts with observed projector flips. Owner: current Codex chat. — [A11](docs/architecture/acquisition.md#a11), [G01](docs/architecture/gui.md#g01), [MCU contract](contracts/acquisition/microcontroller.md), [Evidence](reports/acquisition.md)
- [ ] `gui-implementation` [gui] [visual_stimulus] [tracking] [spikeglx] Complete managed GUI configuration submissions, backend controls, runtime viewers/calibration and trial scheduling. The runtime Dashboard now exposes explicit Take control; camera enable/settings and MCU pins/tests use controller requests. Subject/recording forms, Protocol editor, projector configuration/calibration, SpikeGLX pairing/mapping and Tracking remain review-only or placeholders; do not present them as accepted runtime settings. The 720px Devices clipping test fails and only the operator display was visible in the prior rig review. Linked movement and 2D Tracking choices remain open. Owner: current Codex chat. — [Scope](architecture.md#arch-001), [GUI rules](docs/architecture/gui.md#g01), [Frontend evidence](reports/runtime.md#dashboard-frontend-implementation), [Rig checklist](reports/rig-verification.md)
- [ ] `camera-preview-gui-binding` [gui] [controller] [acquisition] Verify real camera capture, frame display and cleanup on the rig, and finish role editing/connection checks. Live read-only state confirms both cameras are detected and the GUI holds control, but behavioral enablement fails because `trigger_source` is unset. A new build now explains that missing field; restart and save a valid external-trigger PFS source, then verify enablement and live preview. The archived PFS has FrameStart TriggerMode Off. D10/D11 receiver/electrical checks remain open. Owner: current Codex chat. — [Preview contract](contracts/acquisition/preview-control.md), [GUI rule](docs/architecture/gui.md#g01), [Evidence](reports/runtime.md#dashboard-frontend-implementation)
- [ ] `projector-calibration-launch` [gui] [visual_stimulus] Implement manually opened/closed, untimed V01 diagnostic presentation on all four assigned outputs and verify on the rig. The GLB/profile exporter applies per-face scale, pixel offset and inversion, and the GUI Launch/Close state interface exists; the button stays disabled without a managed controller connection and only changes label after confirmed state. Managed GUI transport, controller/coordinator/worker commands, cleanup/evidence and optical rig verification remain. — [G01 output ownership](docs/architecture/gui.md#g01), [V01 renderer owner](docs/architecture/visual_stimulus.md#v01), [GUI implementation evidence](reports/runtime.md#dashboard-frontend-implementation)

## Next

- [ ] `devices-narrow-overflow` [gui] Resolve the observed 720px Devices horizontal overflow without hiding controls; `test_devices_draft_reflows_without_horizontal_clipping[720]` fails on this Windows rig (Camera 28–48px, Projectors 164px in a direct probe). — [Frontend evidence](reports/runtime.md#dashboard-frontend-implementation), [G02](docs/architecture/gui.md#g02)
- [ ] `visual-stimulus-pacing-config` [gui] [visual_stimulus] Adopt the accepted config-file-only pacing settings in managed Visual Stimulus configuration and verify typed defaults; current `test_default_and_file_policy_values_are_typed` rejects checked-in `presentation.pacing_refresh_hz`. Preserve explicit pacing-output identity and V20 ownership. — [Observed failure](reports/runtime.md#dashboard-frontend-implementation), [G01](docs/architecture/gui.md#g01), [V20](docs/architecture/visual_stimulus.md#v20)

- [ ] `trial-epoch-shuffle` [gui] Add a whole-trial epoch reorder action outside Batch generate, preserving group identity and undo history; settle how nested repeat/condition groups participate before implementation. — [G01](docs/architecture/gui.md#g01)
- [ ] `owned-camera-edits` [controller] [acquisition] Recheck and implement applying camera/pulse edits to owned editing/preview cameras under the existing contract. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `camera-readback-adoption` [controller] [acquisition] Review Setup and manual-camera readback paths; share compatible resolution/adoption logic while preserving their distinct checks. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `worker-launch-retirement` [supervisor] Recheck worker launch retention and release completed launches without losing required identity or replay evidence. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `shutdown-health-checks` [supervisor] Resolve gaps in controller-loss monitoring and timeout fencing during accepted shutdown, preserving original deadlines. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `pruned-launch-replay` [supervisor] Resolve PlanLaunch replay behavior after a released registry entry is pruned; retain the agreed replay guarantees. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `late-finished-recovery` [controller] [supervisor] Recheck startup inspection of logs containing late-Finished recovery events; preserve conservative handling of genuinely unconfirmed evidence. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `controller-audit-observations` [controller] Review ingress duplicate handling, pre-activation prompt cancellation, warning lock scope and unread fields before changing them; terminal retention is repaired and capacity bypass was not established. — [Observations](reports/runtime.md#unresolved-findings-and-limitations)

## Blocked

- [ ] `rig-acceptance` [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] Complete remaining managed application/device/full-workload acceptance after GUI implementation, required scientific/wiring inputs and owner-deferred encoder compatibility; bounded native repairs pass. — [Rig worklist](reports/rig-verification.md)

## Deferred

- [ ] `encoder-toolchain-owner-review` [acquisition] [visual_stimulus] Owner-deferred audit item 5: select/validate compatible encoder tools and existing settings before full-load acceptance; no encoder repair was authorized in this phase. — [Evidence and limits](reports/rig-audit-2026-10-01/README.md)

Owner-deferred scientific settings and firmware remain in their owning architecture/worklist records.
