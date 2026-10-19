# Final repository quality checks — 2026-10-19

Source: HEAD `5945f1708240929406f40c4def98dbcf50ff7947` plus the shared dirty
working tree after the GUI and Tracking corrections. Python is the repository's
`.venv/Scripts/python.exe` (3.11). No source files were edited for these checks.
No devices, application runtime or GUI/backend behavioral suites were run again.

Every command below uses that interpreter. Logs share this directory and retain
complete output, including failed build attempts. All final checks exited zero.

| Command | Result | Log |
| --- | --- | --- |
| `python -m ruff check src tests tools scripts` | Pass | `final-quality-ruff-check.log` |
| `python -m ruff format --check src tests tools scripts` | 967 files formatted | `final-quality-ruff-format.log` |
| `python -m mypy --platform win32 src/cephvr` | 842 source files pass | `final-quality-mypy.log` |
| `python tools/generate_contracts.py --output .tmp/final-quality-contracts` | 19 Protobuf sources compile | `final-quality-contracts.log` |
| `python -m unittest discover -s contracts/tracking -p 'test_*.py'` | 48 tests pass | `final-quality-contracts-tracking.log` |
| `python contracts/tracking/schema_check.py` | 19 schemas match | `final-quality-tracking-schema.log` |
| `python -m unittest discover -s contracts/visual_stimulus/tests -p 'test_*.py'` | 42 tests pass | `final-quality-contracts-visual-stimulus.log` |
| `python contracts/visual_stimulus/generate_schemas.py --check` | 11 schemas checked, zero regeneration | `final-quality-visual-stimulus-schema.log` |
| `python -m build --no-isolation --outdir .tmp/final-quality-packages` | sdist and Windows CPython 3.11 wheel built | `final-quality-build-permitted.log` |
| `git diff --check` | Pass; existing CRLF notices only | `final-quality-diff-check.log` |

Contract commands and the non-isolated build match the existing
`tools/test_on_rig.ps1` workflow; no rig script or hardware tests were executed.
The already-passing 737-module boundary check was not repeated.

The first `python -m build` attempt failed while creating its isolated environment
with Windows sandbox temporary-directory access denied (`final-quality-build.log`).
An initial non-isolated attempt hit the same temporary-file restriction
(`final-quality-build-no-isolation.log`). The permission-enabled retry above passed
without installing packages, changing dependency versions or requiring network.

Outputs: `.tmp/final-quality-packages/cephvr-2.0.0.dev0.tar.gz` and
`.tmp/final-quality-packages/cephvr-2.0.0.dev0-cp311-cp311-win_amd64.whl`.
SHA256 hashes are retained in `final-quality-package-hashes.json`.
Compilation, schemas, static analysis and packaging do not establish hardware,
scientific timing or full-workload acceptance under E15.
