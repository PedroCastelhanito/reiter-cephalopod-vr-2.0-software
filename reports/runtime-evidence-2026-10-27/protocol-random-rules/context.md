# Protocol random rules — 2026-10-27

Source: c7881b1f87a5d294383d310ebcb92630cd825099 plus pre-existing and concurrent working-tree changes.
Scope: local implementation/offscreen Qt and compiler checks; no running-app restart or rig acceptance.

Commands use `.venv/Scripts/python.exe`; GUI runs set `QT_QPA_PLATFORM=offscreen`.

- `-m pytest tests/gui/test_dashboard.py -q -m "not windows and not rig" -k "variation or subgroup or random_batch" --basetemp=<writable external visualization root>/protocol-rule-tests-3 --timeout=45`: 26 passed, 993 deselected.
- After extending the existing compact test with a five-repetition save/reload/expansion assertion: `-m pytest tests/gui/test_dashboard.py -q -k large_random_group --basetemp=<writable external visualization root>/protocol-rule-final --timeout=45`: 1 passed, 1018 deselected.
- `-m pytest tests/visual_stimulus/test_compilation.py -q -m "not windows and not rig" -k "repetition or compact_random or rig_random" --basetemp=<writable external visualization root>/protocol-repetition-tests --timeout=45`: 3 passed, 20 deselected.
- `-m ruff check` and `-m ruff format --check` on batch_variation.py, batch_create.py, subgroup_editor.py and tests/gui/test_dashboard.py: pass (four files formatted).
- `-m mypy --platform win32 src/cephvr/gui/batch_variation.py src/cephvr/gui/batch_create.py src/cephvr/gui/subgroup_editor.py`: pass, three source files.
- `tools/check_backend_boundaries.py`: 772 modules, zero violations; existing size advisories, including the variation widget.
- `git diff --check`: pass, with CRLF normalization warnings for pre-existing/concurrent files.

The compact test verifies a single source epoch for 5, 10000 and 1000000 repetitions; seeds remain unchanged, representative resolution stays constant work, and five saved/reloaded occurrences match rule resolution. Existing tests cover independent/shared projectors, invalid drafts, undo, saved list reconstruction and narrow layouts. Focus assertions now activate their test window and wait for the existing deferred remove timer; editing targets the visible random range field.

Earlier attempts: the default sandbox temp directory could not allocate pytest paths; a repository-local retry passed 20 cases but demo-assets correctly rejected generation within the repository. External writable basetemp resolved both. Initial assertions still expected new explicit-list rules; they now restore legacy drafts to preserve that coverage. Focus tests initially failed before activation/deferred-timer dispatch. An initial format check detected CRLF from text writing; LF normalization/formatting corrected it. Windows wildcard-path searches failed and were retried against directories. No production ownership, compiler sampling, dependencies or hardware behavior changed.
