# Architecture simplification review

Date: 2026-09-22. Documentation/contract review only; no runtime or rig validation.
The old camera implementation was not used as a design constraint.

| Reviewed area | Authoritative record |
| --- | --- |
| Applied MCU frequency readback | [A11](../docs/architecture/acquisition.md#a11), [MCU contract](../contracts/acquisition/microcontroller.md) |
| Viewer-independent capture and latest-frame preview | [A03/A10](../docs/architecture/acquisition.md), [preview contract](../contracts/acquisition/preview-control.md) |
| Common configuration adoption and command helpers | [Configuration control](../contracts/acquisition/configuration-control.md), [E08](../docs/architecture/system-contracts.md#e08) |
| FFmpeg launch ordering | [A08](../docs/architecture/acquisition.md#a08), [recording lifecycle](../contracts/acquisition/recording-lifecycle.md) |
| Producer-local interruption cutoffs | [E11](../docs/architecture/experiment.md#e11), [recording lifecycle](../contracts/acquisition/recording-lifecycle.md) |
| Remaining work versus deferral | [Single acquisition worklist](../contracts/acquisition/README.md#remaining-decisions-and-implementation-work), [rig list](rig-verification.md) |

Documentation cleanup removes stale unresolved inventories and revision histories,
links repeated policy to its owner, and aligns the logging example with E04/E05.
Configuration policy declarations now live in `contracts/policy/` (E14). The worklist keeps
open contract tasks distinct from unimplemented code and explicitly deferred checks;
no unfinished contract or hardware mapping is declared complete by this cleanup.
