# Asset selection without copying — 2026-10-29

Source: current uncommitted working tree; concurrent changes preserved. Governing
decision G01rev390/E07. No asset folder modification or saved-protocol rewrite.

Commands use `.venv/Scripts/python.exe`:

- `-m pytest tests/gui/test_stimulus_authoring.py tests/gui/test_dashboard.py -q -k "asset_selection_references or variation_folder_references or unified_subgroup_asset_edit_is_projector_local_and_atomic or texture_recipe_file_selection_preserves_original_json or demo_assets_can_be_selected_and_review_path_restores" -m "not windows and not rig"`: five passed, 1119 deselected.
- `-m pytest tests/gui/test_stimulus_authoring.py -q -m "not windows and not rig"`: 64 passed, two failed. Failures: test_sparse_repeated_epoch_preview_uses_distinct_reproducible_patterns[101] and [4000]; untouched motion_epochs returns 101/4000 while assertions expect 100. No isolated baseline comparison; gui-suite-reconciliation retains follow-up.
- `-m ruff check src/cephvr/gui/stimulus_files.py src/cephvr/gui/variation_assets.py tests/gui/test_stimulus_authoring.py`: pass.
- `-m ruff format --check` on the same paths: pass after formatting the changed test function signature.
- `-m mypy --platform win32 src/cephvr/gui/stimulus_files.py src/cephvr/gui/variation_assets.py`: success, two source files.
- `tools/check_backend_boundaries.py`: 802 modules, zero violations; existing size warnings, no edited helper exceeds 500 lines.
- `git diff --check`: pass, existing line-ending warnings.

Tests cover rejection of outside selections without creating files, shared-root
relative paths, old import-path compatibility, cache invalidation and folder
candidate selection. Offscreen Qt only; native GUI was not restarted.

## Selected but missing root follow-up

2026-10-29 local Test-Path for
`C:/Data/projects/reiter-cephalopod-vr/cephvr-assets/media` returned false; existing
root children: Alsu, config-files, Olivier, Pedro. Screenshot shows that obsolete
media root. choose_media used the same warning for empty and invalid directories.
Changed only that warning to identify the selected invalid path, preserving the
guard and direct-root selection policy.

- `-m pytest tests/gui/test_dashboard.py -q -k stimulus_parameter_edit_invalid_guard_and_media_root -m "not windows and not rig"`: one passed, 1057 deselected.
- Ruff check and format --check for stimulus_parameters.py and test_dashboard.py: pass.
- Win32 mypy for stimulus_parameters.py: success, one source file.
- Backend boundaries: 802 modules, zero violations. Existing stimulus_parameters.py size warning reviewed: picker owns this guard; no separable new responsibility added.
- No live GUI restart or saved-path rewrite.
