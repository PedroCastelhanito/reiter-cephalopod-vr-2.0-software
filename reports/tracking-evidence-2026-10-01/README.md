# Tracking simplification evidence — 2026-10-01

Scope: ARCH-002, T08/T09 ownership/reset behavior and T19 record-before-feedback.
Source base: `7ae3767cea92bf7af94153d417e40df997e1fd05`, with substantial pre-existing
uncommitted work. That commit alone does not identify the tested tree. Before editing,
the tracking source/tests/native subtree was copied to a temporary snapshot.

- [Source diff](source.diff): audit changes only, compared with that snapshot;
  includes the extracted formatter and additions to existing behavior tests.
- [SHA-256 manifest](source-sha256.txt): before/after source, test and native files,
  excluding bytecode. An absent file is represented by the empty-file hash.
- [Static/contract checks](checks.txt): captured command outputs and exit codes.
- [Test results](tests.txt): commands and results transcribed from tool output,
  including the failed sandbox attempt and each independent increment.

Assessment: the 14 added local cases and existing suite support preservation of
ownership, ordering, generation and record-format behavior. No new package, policy,
scientific algorithm or native implementation was introduced. Windows-target mypy
is static only; no native Windows, GPU, camera, scientific accuracy or throughput
acceptance ran here. Full-suite totals include other existing backend changes.
See the [current report](../tracking.md) and [rig worklist](../rig-verification.md).
