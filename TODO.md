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

- [ ] `gui-implementation` [gui] [visual_stimulus] [tracking] [spikeglx] Complete trial scheduling and managed adoption. Rig review discovers real Basler cameras, four secondary displays and named COM ports. G01 revision 73 uses GUI-owned projector display indices in matching table/layout positions and a label-free rig plot; verify physical surfaces against Windows Settings layout. Epoch asset paths are editable; Batch edit has epoch-wide duration and independent projector values. Transient Protocol reference-label and projector-selector windows are fixed across startup and value updates, verified by a native relaunch. Managed device commands, projector output and full rig acceptance remain pending. Preserve reviewed Protocol/Bottom layout, G01/V15/V24/V03/V02/E10/T14 behavior, saved Tracking defaults, and the pacing TOML and remote channel mapping follow-ups. Owner: current GUI chat (Codex). — [Scope](architecture.md#arch-001), [Navigation](docs/architecture/gui.md#g01), [Frontend evidence](reports/runtime.md#dashboard-frontend-implementation)
- [ ] `projector-calibration-launch` [gui] [visual_stimulus] Implement manually opened/closed, untimed V01 diagnostic presentation on all four assigned outputs and verify on the rig. The GLB/profile exporter applies per-face scale, pixel offset and inversion, and the GUI Launch/Close state interface exists; the button stays disabled without a managed controller connection and only changes label after confirmed state. Managed GUI transport, controller/coordinator/worker commands, cleanup/evidence and optical rig verification remain. — [G01 output ownership](docs/architecture/gui.md#g01), [V01 renderer owner](docs/architecture/visual_stimulus.md#v01), [GUI implementation evidence](reports/runtime.md#dashboard-frontend-implementation)

## Next

- [ ] `trial-epoch-shuffle` [gui] Add a whole-trial epoch reorder action outside Batch generate, preserving group identity and undo history; settle how nested repeat/condition groups participate before implementation. — [G01](docs/architecture/gui.md#g01)
- [ ] `owned-camera-edits` [controller] [acquisition] Recheck and implement applying camera/pulse edits to owned editing/preview cameras under the existing contract. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `camera-readback-adoption` [controller] [acquisition] Review Setup and manual-camera readback paths; share compatible resolution/adoption logic while preserving their distinct checks. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `worker-launch-retirement` [supervisor] Recheck worker launch retention and release completed launches without losing required identity or replay evidence. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `shutdown-health-checks` [supervisor] Resolve gaps in controller-loss monitoring and timeout fencing during accepted shutdown, preserving original deadlines. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `pruned-launch-replay` [supervisor] Resolve PlanLaunch replay behavior after a released registry entry is pruned; retain the agreed replay guarantees. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `late-finished-recovery` [controller] [supervisor] Recheck startup inspection of logs containing late-Finished recovery events; preserve conservative handling of genuinely unconfirmed evidence. — [Finding](reports/runtime.md#unresolved-findings-and-limitations)
- [ ] `controller-audit-observations` [controller] Review ingress duplicate handling, pre-activation prompt cancellation, warning lock scope and unread fields before changing them; terminal retention is repaired and capacity bypass was not established. — [Observations](reports/runtime.md#unresolved-findings-and-limitations)

## Blocked

- [ ] `camera-preview-gui-binding` [gui] [acquisition] Choose managed A10 viewer attachment or explicitly authorize a separate local rig diagnostic camera owner, then wire live camera Preview and verify start, frame display and cleanup on the rig. Blocked by the ownership choice: the review GUI has no managed viewer and A10 assigns SDK capture to acquisition workers. Owner: current GUI chat (Codex). — [Preview contract](contracts/acquisition/preview-control.md), [GUI rule](docs/architecture/gui.md#g01)

- [ ] `rig-acceptance` [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] Complete remaining managed application/device/full-workload acceptance after GUI implementation, required scientific/wiring inputs and owner-deferred encoder compatibility; bounded native repairs pass. — [Rig worklist](reports/rig-verification.md)

## Deferred

- [ ] `encoder-toolchain-owner-review` [acquisition] [visual_stimulus] Owner-deferred audit item 5: select/validate compatible encoder tools and existing settings before full-load acceptance; no encoder repair was authorized in this phase. — [Evidence and limits](reports/rig-audit-2026-10-01/README.md)

Owner-deferred scientific settings and firmware remain in their owning architecture/worklist records.
