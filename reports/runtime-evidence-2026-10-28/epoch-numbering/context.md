# Epoch numbering — 2026-10-28

Source: working tree based on e4dd8f2694aa075380fe6711a884fe5894763c6f, with
concurrent unrelated edits preserved. Owner requested current-position card labels
and saved identifiers that follow edits. Governing decision: [G01](../../../docs/architecture/gui.md#g01), revision378.

Method: source review, Qt offscreen tests, static checks. No controller/device
operations or app restart. ARCH-002: shared numbering lives in program_editing;
timeline views cache the numbers. Existing oversized protocol_editor and
protocol_timeline remain cohesive transaction and painter owners; additions are
only integration, with no new dependency or whole-runtime reference.

## Validation

Using `.venv/Scripts/python.exe`, `QT_QPA_PLATFORM=offscreen`:

```
python -m pytest tests/gui/test_dashboard.py -q -k "protocol_epoch_structure or epoch_numbers_follow or epoch_renumbering or file_first_epoch_insertion or group_actions or grouped_editor_pair or grouped_batch_insertion or flat_group_initial or unified_subgroup or label_insertion or batch_insertion_positions or inline_timeline_actions or timeline_epoch_shortcuts or 200_epoch_timeline or nested_group_edit or epoch_card_uses or subgroup_rules_persist or batch_create_variations or grouped_timeline_large or protocol_timeline_edits or trial_overview_selects or timeline_overview_colors" --basetemp=C:/Users/ReiterU_PC/.codex/visualizations/2026/10/28/01a1800c-ae8a-7081-a6bb-0d7515947d36/epoch-tests
```

Result:39 passed,1007 deselected in21.98s. Includes card paint capture for stale
Epoch_2, trial-wide order across groups, movement/content preservation, deletion,
insert/duplicate operations, variations, save/reload, Undo/Redo, large repeats,
legacy nested imports and imported group-identity collisions.

Final refinement reserves only actual group IDs rather than every declaration ID.
After it, reran `-k "protocol_epoch_structure or epoch_card_uses or
epoch_numbers_follow or epoch_renumbering" --basetemp=.tmp-epoch-numbering-verified`:
4 passed,1042 deselected in1.90s.

Ruff check and format --check passed for program_editing.py, protocol_editor.py,
protocol_timeline.py, timeline_views.py and tests/gui/test_dashboard.py.
Win32 mypy passed for those four source files. Backend-boundary checker:
792 modules, zero violations, existing size advisories reviewed as above.
`git diff --check` passed.

Initial integration run:28 pass/4 fail from assertions requiring unchanged IDs;
updated those expectations while retaining content/history comparisons, then
32 pass. Additional selection:8 pass/1 fixture error because demo assets reject
repository-local generation. External sandbox TEMP attempt:29 pass/10 fixture
directory-creation errors. Moving basetemp to the writable external visualization
root produced the39-case pass above. These attempts are not application failures.

Limits: selected local GUI behavior only; no whole-suite, native appearance,
physical display or rig acceptance. Loading alone preserves imported identifiers;
structural edits apply the owner's renumbering revision. Source order is listed
depth-first order, not a prediction of randomized runtime occurrences.
