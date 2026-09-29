# Runtime tests

Tests mirror the owning package under `src/cephvr/`. The current suite covers shared
invariants, controller lifecycle and filesystem ownership, supervisor registration,
and real loopback controller/client calls. Native Windows and rig behavior require
their own execution evidence; mocks do not establish those guarantees.

The [development guide](../docs/development.md#checks) gives the commands and
registered markers. Existing contract checks stay with their source artifacts in
`contracts/`. [E15](../docs/architecture/system-contracts.md#e15) owns the distinction
between local checks and behavioral verification on the rig.
