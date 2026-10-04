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

- [ ] `gui-implementation` [gui] [visual_stimulus] [tracking] [spikeglx] Review completed Bottom schematic pyramid from mirror and five plot toggles; all generated review images removed at owner request; review completed unified advanced section with retain-state and simplified feedback/input entries; mode and duration widths match; preserve completed batch header/layer selectors and label insertion; review completed grouped Projection legend/visibility and retained Bottom center paths; review completed batch spacing and independent arena movement controls; complete trial scheduling and managed adoption. No Tracking status or HUD/log on Protocol. G01 revision 65/V15 revision 10/V24 revision 7/V03 revision 9/V02 revision 11/E10 revision 22/T14 revision 3 derive Tracking and keep device controls in Devices. Review fixture velocity saving is explicitly Off; preserve T14 saved/file defaults during managed binding; complete session-setting persistence and managed adoption. 138 GUI checks pass in the 193-test GUI/client-state/compiler/contracts run plus 79 subtests; previous projector contract coverage remains recorded; previous responsive-layout/insertion checks remain recorded; prior 194-test feedback/contract coverage plus custom/legacy-mapping and pure-reference checks remains recorded; prior client-state/compiler coverage includes overview selection/color grouping, batch generation, patch isolation and nested insertion undo; nested group edits, saved conditions, per-screen isolation and cancellation/history are covered. Pacing TOML adoption/validation remains pending with managed GUI binding; the default-config test reproduces the existing unrecognized presentation.pacing_refresh_hz key (see frontend evidence). Remote saved-channel discovery/mapping validation and adoption remain pending. Managed GUI-to-profile binding and physical subset acceptance remain pending. Per-pin diagnostics still need bounded firmware/transport contracts and integration. Verify Windows Settings display numbering on the rig before acceptance. Owner: current GUI chat (Codex). Dashboard styling is approved; Cameras is a local review draft and contextual help remains unaccepted. Controller/managed integration, runtime viewers and Windows work remain pending. — [Scope](architecture.md#arch-001), [Navigation](docs/architecture/gui.md#g01), [Formatting](docs/architecture/gui.md#g02), [Frontend evidence](reports/runtime.md#dashboard-frontend-implementation)

## Next

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
