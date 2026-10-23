# Motion source and advanced fades — 2026-10-23

Source: dirty working tree based on `59a973ac3ffc6fb331bbee1d93c6b283d6b90474`;
concurrent unrelated changes retained. Decision: [G01](../../../docs/architecture/gui.md#g01).

## Methods and outcomes

- Repository Python 3.11, `QT_QPA_PLATFORM=offscreen`.
- `python -m pytest tests/gui/test_dashboard.py -q -k 'reference or fade or category or motion'`:
  initial run 4 failed/65 passed; first failure showed detached labels during layout,
  with three later variation-notice failures. Showing cells after grid parenting
  fixes the lifetime regression. Final selection: **69 passed,788 deselected**.
- After the final narrow reflow, selection
  `-k 'reference_motion_source or reference_advanced_controls_align or reference_updates_do_not_show_detached_windows or compact_reference_rows'`:
  **6 passed,851 deselected**. Each run used a unique explicit repository-local
  `--basetemp` under the dated evidence directory.
- Ruff check/format: `motion_source.py`, `reference_fields.py`,
  `projector_reference.py`, `stimulus_parameters.py`, `advanced_appearance.py`,
  and `tests/gui/test_dashboard.py` pass. Initial formatting differences corrected.
- `python -m mypy --platform win32` for the five changed source modules: pass.
- `python tools/check_backend_boundaries.py`:757 modules, zero violations;
  existing cohesion advisories reviewed, focused selector extracted, no new dependency.
- `git diff --check`: pass.

## Visual inspection

Constructed the real `EpochComposer` with two built-in Texture settings (Bottom
source, Front target), packaged font and Amber stylesheet; no file/device access.
Captured `QWidget.grab()` after event processing at1450px wide and720px narrow,
with Advanced settings expanded. Inspected source selector visibility, hidden numeric
fields and fades. A first standalone capture omitted application font/theme setup;
the images here replace that unusable capture. A Dashboard-hosted capture attempt
had no selected source row; corrected to the standalone real composer fixture.

- [Linked, wide](linked-wide.png)
- [Linked, narrow](linked-narrow.png)
- [Self, narrow](self-narrow.png)

These are offscreen authoring fixtures, not native window/DPI or renderer evidence.
No running app restart, saved experiment change, Setup/trial or rig acceptance.
