# Sidebar selection and preview CRT exclusion — 2026-10-23

Source: current uncommitted Oct23 workspace, including concurrent work; no isolated
committed revision is claimed. Python3.11 and Qt source widgets; no renderer/device
action, Setup, trial execution or running-application restart.

## Verification

- `.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -k 'side_rail or phosphor or crt_overlay or trial_preview or planning_arena' -m 'not windows and not rig' --basetemp=.pytest-navigation-preview-final --tb=short`:
  **33 passed,824 deselected in19.27s**.
- Tests extend the existing navigation/film/trial-preview owners. They cover
  active-only selection, inactive tab changes/return, actual selected delegate text
  (no Microcontroller elision), balanced marker gaps, preview white pixels unaffected
  through resize/move and CRT toggles, and equal trial-view crops with CRT on/off.
- Changed-file Ruff check/format and Win32 mypy6 sources pass. Backend boundaries:
  757 modules,zero violations; existing size advisories reviewed (theme adds only
  a size value, no separable responsibility). Whitespace check passes.
- Final window-scope guard restricts exclusions to the film's own top-level window;
  the popup/trial-preview selection passes again (2 passed,855 deselected), with
  changed-owner Ruff/format/Win32 mypy passing after that guard.

## Captures and limits

- `before-rail.png`: source-widget baseline reproduces selected Microcontroller elision.
  Actual paint-option probe:105px label,104px available after suffix/gap reservation.
- `selected-microcontroller.png`: selected full label and suffix at262px sidebar.
- `inactive-subtabs.png`: Protocol active, both expanded child groups unselected.
- `trial-preview.png`: offscreen planning-fixture dialog; clean rig rectangle with
  CRT retained around controls. This fixture has unavailable calibrated layer content,
  so it is not evidence of correct projected stimulus pixels. Dedicated white-region
  assertions verify film exclusion independently of stimulus preparation.
- `fixture.png` and `render.ini`: local capture inputs/preferences only. Neither is
  the owner's saved experiment configuration. No physical/DPI/native-viewer/full-load
  acceptance is claimed.

Initial checks caught a missing QColor import, then native sibling mapping offset
in `mapTo(overlay)`: host-ancestor coordinates fix the exclusion. A child-only grab
used a different background/composition from its parent; the meaningful comparison
now captures the same trial-view rectangle with film on/off. Final selection passes.
The first capture script opened a planning-error modal and was interrupted; a direct
fixture capture completed. An initial sizing probe created and closed an isolated
native source window; the running application/settings were not controlled.
