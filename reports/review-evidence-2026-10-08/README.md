# Backend review and fixes, 2026-10-08

Source revision: HEAD `e4c653c` plus uncommitted GUI, upload and runtime work from other sessions, so results are not an immutable revision. Scope: `controller`, `supervisor`, `acquisition`, `visual_stimulus`, `tracking`, `launcher`, `client`, `platform`, `shared` and their tests. Windows-native, hardware and rig behavior were not exercised (E15).

## Method and limits

- A multi-agent review was stopped after repeated usage-limit failures. Its completed Sonnet reviews (launcher, client, supervisor, shared, cross-backend) date from baseline `5c24d99`, before 347 files changed. Controller, tracking, acquisition, visual_stimulus and platform had no model review; their rows come from ruff (extended rules), an AST scan for silent exception handlers, a name-reference scan for dead code, a name-in-tests scan and greps.
- [review-findings.md](review-findings.md) / [review-findings.json](review-findings.json) are the original 55-row table. Several rows were later judged not real after reading the code (silent-handler rows F-006 to F-009 and F-023, F-020, F-024, F-032, F-044, F-040 to F-042, F-050, F-051); F-055 was retracted. The table is kept as raw evidence, not as the list of defects.
- The heuristics have known false positives: the silent-handler scan flags handlers that record state; the untested-module scan only looks for names in test files.

## Applied (verified)

| Finding | Change | Test |
|---|---|---|
| F-001 | A replayed ShutdownApplication no longer resets the recorded operation outcome | `tests/supervisor/test_shutdown.py` replay assertions (fail without the change) |
| F-002 | gRPC failures reach the tracking-release retry loop as `OSError` | `tests/supervisor/test_recovery.py` (4 tests) |
| F-014 | `source_registered` tolerates one unreadable launch job | `tests/supervisor/test_health.py` |
| F-005 | Acquisition and Visual Stimulus worker cleanup run concurrently | `tests/supervisor/test_shutdown.py` (fails on the old order) |
| F-015 | Rejected participant Shutdown requests surface as warnings | `tests/supervisor/test_shutdown.py` |
| F-016 | Helper errors raise a keyed supervisor warning, cleared on release | `tests/supervisor/test_recovery.py` |
| F-038 | Flaky test given a realistic recovery limit | 10 repeated runs pass |
| F-003, F-018, F-013, F-028 | Launcher parser handles `RecursionError`; reader treats read errors as channel loss; bootstrap failure is reported; preflight extracted to `launcher/preflight.py` and `shared/managed_modules.py`; reader moved to `launcher/notification_reader.py` | `tests/launcher/` (deep nesting, preflight) |
| F-019, F-037 | Client timeouts and a missing `[rpc]` table give messages; credential-removal failure warns; Ctrl+C acts only in SettingUp, Starting, Running (E02) | `tests/client/test_cli_behavior.py` |
| F-052 | One shared parsed-policy digest for all three backends; E14 revision 207 | `tests/shared/test_config.py` |
| F-046 | Acquisition worker bootstrap rejects non-loopback endpoints | `tests/acquisition/test_worker_bootstrap.py` |
| F-047 | Visual Stimulus Setup rejects a wrong `contract_version` | `tests/visual_stimulus/test_coordinator.py` |
| F-021, F-030, F-031, F-036, F-049, F-022, F-035, F-006 | Small clean-ups and intent comments (see the diff) | `tests/shared/test_invariants.py` for F-021 |
| F-054 | Protected file source moved to `platform/windows/protected_source.py` (Tracking also imported it from Visual Stimulus) | existing tests, mypy win32 |
| F-033, F-034 | Ten unreferenced definitions deleted after a repository-wide grep | full suite |
| F-004 | Ruff now selects ASYNC, RUF006, RUF100 (tests ignore ASYNC; GUI ignores RUF100) | `ruff check src tests` |
| F-011, coverage | `coverage` added to the dev extras and run (see [coverage.md](coverage.md)); ownership-state-machine tests for `SupervisedEncoderLauncher` (fakes only) | `tests/shared/test_supervised_encoder.py` (7 tests) |

Not done: F-043, F-045, F-053 (now under TODO "For review"); the measured coverage gaps are in [coverage.md](coverage.md) and tracked as `acquisition-worker-portable-tests`; F-046 was not applied to Tracking's own peer check; the client needs-input exit-code-3 and release-failure paths still need a live controller to test.

## Checks at the end of the run

| Command | Result |
|---|---|
| `ruff check src/cephvr tests` | passed |
| `ruff format --check src/cephvr tests` | 806 files formatted |
| `mypy --platform win32 src/cephvr/<backend>` for the nine backends | no issues (83, 20, 189, 124, 65, 8, 4, 29, 37 files) |
| `pytest tests/{controller,supervisor,acquisition,visual_stimulus,tracking,launcher,client,platform,shared} -m "not windows and not rig"` | 1090 passed, 6 skipped, 5 deselected |
| `tools/check_backend_boundaries.py` | 606 modules, 0 violations; advisories include `supervisor/shutdown.py` 519 lines and `controller/service.py` 590 lines (cohesive, see ARCH-002 review) |

Local passes do not close E15 rig checks.
