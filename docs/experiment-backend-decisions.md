# Experiment-control design guide

[architecture.md](../architecture.md) indexes the authoritative records. Read the
[experiment backend](architecture/experiment.md),
[system contracts](architecture/system-contracts.md) and
[GUI rules](architecture/gui.md). This guide provides navigation, not alternate
policies.

| Area | Decisions / contracts |
| --- | --- |
| Ordered protocols, GUI and headless control | E01–E03 |
| Recording identity, filenames and durable metadata | E04 |
| Lifecycle and trial timing | E05, E11; [transition tables](experiment-control-transitions.md) |
| Interruption, recovery and shutdown | E06 |
| Configuration, validation and history | E07, E14 |
| Processes, RPCs and ownership | E08; [shared contracts](../contracts/README.md) |
| SpikeGLX scope and modes | E09–E13, SYS-004 |
| Contract status and later rig verification | E15 |

- See the architecture's **Current position** for scope and decisions, the
  [runtime report](../reports/runtime.md) for dated implementation/local validation
  evidence, and [rig verification](../reports/rig-verification.md) for pending acceptance.
  Wire compilation alone does not establish runtime or rig behavior.
- Backend payloads, device checks, scientific formats and final process boundaries
  belong to their backend designs; do not infer them from empty message
  definitions.
- Rig testing after the main architecture is established, with no simulated
  experiment runner as the first milestone, follows E15.
