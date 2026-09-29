# VR declaration and simplification validation — 2026-09-24

Scope: [VR contracts](../contracts/vr/README.md) and
[shared native transport](../contracts/native-transport.md). This report records checks;
[V03](../docs/architecture/vr.md#v03), [V05](../docs/architecture/vr.md#v05),
[V24](../docs/architecture/vr.md#v24), [V28](../docs/architecture/vr.md#v28) and
[E08](../docs/architecture/system-contracts.md#e08) own the accepted rules.

The ten [pure regression tests](../contracts/vr/tests/test_simplification.py) pass:
version/complete-setting rejection, parameter/coefficient and coordinate-dependent units,
feedback gain/rate compatibility, consistent opaque output IDs, bounded strict JSON,
single-plan structure, exact evidence byte preservation and envelope checksums/bounds.
The [drift/hold source](../contracts/vr/examples/drift-hold.json) validates as format 2.
The [generator](../contracts/vr/generate_schemas.py) reproduces all 13 published schemas
without drift. Python implementations and interface declarations parse successfully.

The complete 15-file Protobuf set compiles. The obsolete parallel schedule messages
and field were deliberately removed; the former control field's number/name are reserved.
All unrelated existing wire field names/numbers/types, enum values and reservations
remain intact. Program/PreparedTrial format 1 is intentionally rejected; rebuild clients
against the new declarations and use format 2. WatchState remains the only streaming RPC.
All 61 root-register revisions match their owners; changed-document relative links resolve.

The implemented Python changes are pure schemas/parsing/unit checks and evidence
payload/framing helpers. Compiler/native-transport/renderer/recorder/recovery interfaces
remain declarations. No Windows cleanup, GPU rendering, video encoding, recovery/export
runtime or rig behavior was tested. The existing encoder input-format, timestamp precision
and final-frame-duration feasibility deferrals remain. No runtime output-file validator,
new overload policy, original-pixel equality claim or measured speedup is introduced.
