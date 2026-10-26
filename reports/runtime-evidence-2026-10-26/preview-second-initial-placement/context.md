# Second preview initial placement — 2026-10-26

Source base: `e6210a3d545c490e10dffa4f7b5bbd0f9a474fa9`; dirty shared workspace, not a clean revision. Source hashes at verification:

- `src/cephvr/gui/preview_placement.py` SHA256 `813672fb2cddc6e9e01eccad53a629c6c1363e97065d7aebe551daed057c4554`
- `tests/gui/test_dashboard.py` SHA256 `23bbb4b5f147870695d5a7d637c765d2f768b5738664926e29b29c4316fccc17`

Under [G01](../../../docs/architecture/gui.md#g01), initial native placement must use the target preview slot. A newly parented frame remained explicitly hidden until Qt delivered its show event, so synchronous prospective layout measured stale geometry. Explicitly showing the frame after adding it to the grid includes it in the pre-open measurement. Native window operations remain on their existing shared owner; image preparation remains independent.

ARCH-002: one call in the existing layout owner, no dependency, state, timer, event pumping or new module. Extend the existing Dashboard behavior tests.

## Reproduction and checks

The corrected three-theme harness was replayed against pre-fix source, then source restored in a finally block: all three cases failed initial-versus-pending geometry equality. Standard initial `(164,424,344)` versus settled `(274,571,197)`; Amber and Retro initial `(160,415,353)` versus `(271,565,203)`. An earlier harness left the empty-workspace hint visible; hiding that hint matches the actual Dashboard with available cameras.

Final coverage tests both camera opening orders in Standard, Amber and Retro, asserts prospective measurement restores the original source set, and compares initial, pending and settled geometry.

Command: `.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -k "second_preview_initial or preview_workspace_pending_visible_update or preview_grid_retains_pending or preview_slot_adapts_open_source_grid or preview_placement" --tb=short --timeout=30`

Result: 21 passed, 951 deselected (final repeat 1.75s). Ruff check and format check pass for both changed files; Win32 mypy passes for preview_placement.py. Backend boundaries: 760 modules, zero violations, existing unrelated size advisories.

These are local offscreen Qt checks. No running application restart, native first-reveal observation, mixed-DPI or live FPS acceptance is claimed. See the [outstanding rig check](../../rig-verification.md#camera-native-caption).
