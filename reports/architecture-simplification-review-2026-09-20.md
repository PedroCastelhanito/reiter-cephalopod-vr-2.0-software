# Architecture review — reference index

Review date: 2026-09-20; reconciled against current records on 2026-09-22.
Design review only, not runtime or rig evidence. Superseded option discussions and
revision-by-revision policies have been removed; current rules have one owning record.

| Original finding | Current authority / status |
| --- | --- |
| R1: trial filename uniqueness | [E04](../docs/architecture/supervisor.md#e04), [E05](../docs/architecture/experiment.md#e05); retain chosen naming/minimum-duration and collision handling. |
| R2: achievable pulse frequency | [A11](../docs/architecture/acquisition.md#a11); current adjustment/readback rule supersedes the review's earlier proposal. |
| R3: serial boundary scheduling | [A11](../docs/architecture/acquisition.md#a11), [MCU contract](../contracts/acquisition/microcontroller.md#scheduled-serial-boundaries-a11). |
| R4: duplicated policy records | [GOV-001](../architecture.md#gov-001), [E14](../docs/architecture/system-contracts.md#e14). |
| R5: complete snapshots | [E03](../docs/architecture/gui.md#e03), [E08](../docs/architecture/system-contracts.md#e08). |
| R6: bounded pending-row credits | [A07](../docs/architecture/acquisition.md#a07), accounting attachment (setup-preparation.md accounting section, removed 2026-09-27). |
| R7: exact final video duration | [A08](../docs/architecture/acquisition.md#a08); the proposed relaxation was not selected. Feasibility remains on the [rig list](rig-verification.md). |
| R8: recording/crash safeguards | [A07/A08](../docs/architecture/acquisition.md), HDF5 schema (hdf5_schema.toml, removed 2026-09-27). |

Remaining acquisition work is tracked only in its [contract worklist](../contracts/acquisition/README.md#remaining-decisions-and-implementation-work).
