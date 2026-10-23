# Category template and inactive media-link checks — 2026-10-23

Source: current uncommitted workspace on Oct23; includes concurrent changes, so
no isolated committed revision is claimed. Method: repository Python3.11, pure
backend checks and Qt offscreen GUI fixtures. No running app or saved experiment
settings changed; no native, hardware, physical motion or full-load acceptance.

- `.venv/Scripts/python.exe -m pytest tests/visual_stimulus/test_compilation.py tests/visual_stimulus/test_configuration.py -q -m "not windows and not rig" --basetemp=.pytest-category-backend`:
  37 passed,3 subtests passed. Covers source link retention, ignored invalid reference
  and compiler removal before executable link validation/binding.
- `.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -k 'protocol_category or category_first_visit or presentation_rows' --basetemp=.pytest-category-final`:
  5 passed,850 deselected. Covers category restoration, portable snapshots, first
  compatible classification undo, legacy moving-content retention, invalid template
  category rejection, seed/gap retention and hidden-link retention during fade edits.
- Changed-owner Ruff check and format check pass. Win32 mypy passes7 source files.
  Backend boundaries:756 modules,zero violations; existing cohesive size advisories.
- Broader GUI selection, `-k 'protocol or category_first_visit or presentation_rows or category_preview' -m 'not windows and not rig' --basetemp=.pytest-category-protocol`:
  28 passed,827 deselected in53.99s. Final focused5-check rerun also includes the
  additional seed/gap and inactive-link fade-edit assertions. Whitespace check passes.

Initial attempts: backend tests passed36 cases but one fixture could not create
the sandbox default temp directory; explicit workspace basetemp rerun passed all37.
Initial GUI checks exposed a first-classification history reset and comparisons of
flat source against editor-only grouping. The first was corrected by using only
previously stored target templates; comparisons now use exported source. Final
focused rerun above passes. Test changes extend the existing owning modules.
