# Backend discussion checklist

[architecture.md](../architecture.md) indexes the authoritative system contracts and
backend records in `docs/architecture/`. This is a discussion checklist, not a
second decision record.

- Discussion order, batching and rig deferrals follow
  [GOV-001](../architecture.md#gov-001); selected process boundaries, the initial
  implementation stage and remaining choices belong to
  [ARCH-001](../architecture.md#arch-001).
- Use [SYS-003](../architecture.md#sys-003) as the language baseline for each
  backend; feasibility and any justified exception are discussed within that
  backend's scope.

## Cover these topics for each backend

| Topic | Questions to answer |
| --- | --- |
| Ownership | Which state is authoritative here? What belongs to another backend? |
| Functionality | Which first-version workflows are required? Which are deferred? |
| Execution | Which language, process/thread structure, and CPU/GPU assignment? |
| Contracts | Which commands/events/data, identifiers, units, schemas, and transport? |
| Timing and buffering | Which clocks, latency targets, queue limits, loss rules, and overload behavior? |
| Configuration | Which defaults, validation, calibrations/assets, and rules for applying changes? |
| Recording and recovery | Who writes each output? Which provenance, finalization, and restart rules? |
| Acceptance | Which rig checks establish correct behavior after the main architecture is established, under E15? |

## Topics specific to each responsibility

- **Experiment:** protocol progression, trial identity, recording boundaries,
  lifecycle, GUI disconnects, participant failures, remote SpikeGLX coordination.
- **Acquisition:** cameras/formats/rates/ROIs, independent tracking and recording
  consumers, image conversions, source changes, frame and hardware provenance.
- **Synchronization:** E09/E12 own remote session control, native recorder
  responsibility, host configuration and interfaces; SYS-004 keeps hardware pulses
  authoritative, with scientific alignment/file validation external post hoc.
  Camera-trigger ownership follows A10. Hardware inventory/channel/edge routing and
  measurements remain rig work; do not reopen those accepted ownership/scope
  choices. See the [SpikeGLX control contract](../contracts/spikeglx-control.md).
- **Stimulus / Visual Stimulus:** stimulus types/combinations, projector layout, presentation
  clock, onset evidence, response gains, applied-state recording, stale tracking.
- **Tracking:** pose/body methods, flow estimators, locomotion model, coordinates,
  calibration, pose/flow scheduling, frame skipping, quality, and source age.

After each choice or batch, update the owning architecture record and root
register, including its status and concise current rules. Unanswered options are
not accepted choices.
