# Bottom output and Monitor duration validation

Date: 2026-10-29 (Asia/Tokyo). Base revision:
`1f10e5f70487c3e3bed074593168d1d2aa4ad9d7`, with the pre-existing dirty image-bundle
implementation retained. This is validation of the current working tree, not a
pristine revision or physical experiment. Governing rule:
[G01](../../../docs/architecture/gui.md#g01).

Changed production helpers: `gui/calibration_profile.py`,
`gui/preview_motion_data.py`, `gui/trial_preview_rig.py`,
`visual_stimulus/rendering/preview_rig.py`. Existing owning test modules extended;
no new test module. No application restart, projector window or device session.

- [Focused GUI](gui-focused.txt): 73 passed. Long trial has 125 occurrences;
  Monitor includes all, editor animated preview retains 100; two-trial total and gap
  remain complete. Bottom pitch, flip composition, cropping, export and preview cases.
- [Native preview](native-preview.txt): five passed, including four offscreen OpenGL
  quadrant/crop/source-preservation checks; no physical projector acceptance.
- [Complete timeline module](timeline-suite.txt): 116 passed, three existing arena
  instrument failures with empty map lists.
- [Original-helper comparison](original-helper-comparison.txt): those three failures
  and the calibration physical-versus-usable-plane assertion reproduce after loading
  HEAD versions of `preview_motion_data` and `calibration_profile` into their already
  imported modules in memory, then running pytest. Other working-tree code remains
  current; no stash, reset or baseline checkout. This attributes the failures away
  from the changed helpers without claiming an entirely clean baseline.
- [Ruff](ruff.txt), [format](format.txt), [Win32 mypy](mypy.txt): pass.
- [Boundaries](boundaries.txt): 802 modules, zero violations. Size warnings are
  unchanged owners; all four edited production helpers remain below 500 lines.

Initial attempts exposed invalid Group fixture enums/missing conditions, old Bottom
winding/signed-pitch expectations and import ordering. These were corrected before
the retained passing runs. Existing full-suite failures were not weakened or fixed
as part of this task. Native optical direction, saved-calibration agreement and
full-limit GUI responsiveness remain unverified. Runtime reports and the single rig
checklist retain these limits.
