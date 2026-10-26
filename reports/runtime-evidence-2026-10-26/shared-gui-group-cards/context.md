# Shared GUI group cards — 2026-10-26

Base f82be21f28d3c1141adeabe2558c29808062727a, concurrent dirty workspace preserved.
G02 revision152; presentation-only configuration changes, no device/runtime commands.

Final owning validation uses repository Python3.11 and this pytest selection:

```text
python -m pytest tests/gui/test_dashboard.py -q -k 'configuration_groups_share_cards or editing_card_keeps or recording_checks_stay_next or four_digit_subject_and_species_setup or directory_paths_clipboard_and_editing_locks or tracking_methods_preserve_fields or tracking_draft_roundtrip or tracking_preview_stages_retain or mcu_inputs_define_remove or mcu_inputs_persist or review_inline_output_templates or spikeglx_sources_preserve or calibration_and_screen_dimensions or screen_dimension_cards or projector_reference_measurements or legacy_numeric_projector_json or projector_brightness_layout or reference_motion_source or unified_subgroup or presentation_rows_keep or variation_cards_focus' --basetemp=C:/Users/ReiterU_PC/.codex/visualizations/2026/10/26/01a17586-62df-7660-b6ca-af466c7051c3/.pytest_shared_gui_cards_verified --timeout=60 --tb=short --junitxml=reports/runtime-evidence-2026-10-26/shared-gui-group-cards/tests.xml
57 passed, 880 deselected in116.03s
```

Executed through pytest.main with an uncaught-Qt-exception diagnostic hook that
prints exceptions and forces a nonzero result if any occur. Final count: zero
uncaught Qt errors. [JUnit result](tests.xml) preserves individual cases. A preceding
direct invocation reached100% but exited1 without a summary; it is not counted as
a pass. Static checking also caught and corrected an inherited QWidget.actions
name collision in the extracted toolbar before the final run.

Checks cover all configuration tabs at1175/720px in Standard, Retro and Amber:
actual viewport containment, wrapped headings, editing focus and painted fills;
popup ownership; saving controls/refresh identity; subject validation and path
clipboard/locks; MCU input/output drafts and SpikeGLX mapping; projector geometry,
calibration, brightness, synchronization snapshots; Protocol sources/fades/layers,
subgroup atomic changes and variation removal; Tracking method/draft retention.
Initial recording-grid assertions were updated to check the two semantic groups.
Visual inspection found a525px Tracking toolbar minimum exceeding the418px narrow
viewport; responsive controls now wrap without replacing their callback owners.

Ruff check/format passes19 source files and test_dashboard.py. Win32 mypy passes
all19 source files. Boundary checker:760 modules, zero violations with existing
size advisories. ARCH-002 review extracts the separable toolbar from Tracking's
larger owner; other touched large files receive only focused presentation assembly.
No dependency or new persistent model state. Whitespace checks pass separately.

Expanded preview checks in the concurrent worktree are not green: an initial
keyword run had50 passes/two preview failures; the focused preview follow-up had
11 passes/five failures. Missing Combined frame key and compact plot heights95–99px
against a100px assertion remain attributed only to the current worktree, with root
cause unresolved under preview-interaction-transitions. No preview code/assertions
were changed here, and no whole-GUI-suite pass is claimed.

[render.py](render.py) captures actual Qt widgets with the bundled font, Amber and
isolated settings. No Setup/Start, live device inventory or runtime commands.
Child-only layout captures disable CRT overlays to avoid clipped glow artifacts;
full-window Protocol and narrow Tracking captures retain normal CRT styling.

| Area reviewed | Captures |
| --- | --- |
| Dashboard Configure | [Session and saving groups](session.png) |
| Protocol | [Type, assets and Epoch settings](protocol.png) |
| Cameras | [Existing shared groups](cameras.png) |
| Microcontroller | [Connection, inputs and outputs](microcontroller.png) |
| SpikeGLX | [Connection and channel mapping](spikeglx.png) |
| Projectors | [Geometry](geometry.png), [Calibration](calibration.png), [Synchronization](synchronization.png) |
| Tracking | [Preprocessing](preprocessing.png), [Calibration](tracking-calibration.png), [Pose](pose.png), [Motion](motion.png), [720px viewport](tracking-narrow.png) |

All13 views inspected. Inventory tables, logs/HUD, timelines and preview plots keep
their existing section containers; their content is distinct from configuration
groups. Native app/DPI/full-workload acceptance was not performed. Running app
untouched; current backend/preview work and its existing TODO remain independent.
