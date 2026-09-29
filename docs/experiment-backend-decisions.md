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

- The shared wire files compile, but no runtime or rig verification is complete.
  See the architecture's **Current position** and the
  [audit assessment](../reports/audit-assessment.md) for current decisions and
  contract gaps.
- Backend payloads, device checks, scientific formats and final process boundaries
  belong to their backend designs; do not infer them from empty message
  definitions.
- Rig testing after the main architecture is established, with no simulated
  experiment runner as the first milestone, follows E15.
