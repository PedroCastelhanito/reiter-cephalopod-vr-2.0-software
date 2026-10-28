# Preview prefix validation — 2026-10-28

Source: working tree based on e4dd8f2694aa075380fe6711a884fe5894763c6f,
including concurrent pre-existing edits. Task: `preview-first-100-epochs`.
Local Windows Python3.11 environment; Qt offscreen. This is implementation evidence,
not native device, optical or full-workload acceptance.

Commands (Python means `.venv/Scripts/python.exe`):

- `python -m pytest tests/visual_stimulus/test_compilation.py tests/gui/test_stimulus_authoring.py tests/gui/test_preview_timeline.py -q -m 'not windows and not rig' --basetemp=.tmp-preview-prefix`
  with `QT_QPA_PLATFORM=offscreen`:190 passed,3 failed in18.58s.
  All compiler/authoring cases passed. Extended the owning sparse preview regression
  to3,100,101,4000 repeats, checking prefix settings, distinct/reproducible patterns,
  duration and unchanged source. Compiler regression checks shuffled prefix equality,
  equal substitution work for120 versus8000 occurrences, invalid bounds and continued
  rejection by full expansion.
- The three failures are `test_arena_map_and_body_frame_dial_follow_planned_continuity`,
  `test_projector_card_instruments_wrap_to_the_column_width` and
  `test_feedback_arena_pose_waits_until_reset` in `tests/gui/test_preview_timeline.py`.
  Each raises IndexError on an empty maps/map_samples list. Repeated those tests with
  an in-process replacement of `preview_motion_data.expand_program_prefix` by
  `lambda program, seed_decimal, max_expanded_epochs: expand_program(program,
  seed_decimal=seed_decimal, max_expanded_epochs=2000)`, then `pytest.main` with the
  three test names selected and `--basetemp=.tmp-preview-prefix-baseline`:
  same3 failures,115 deselected. This isolates the new prefix behavior; it is not
  a clean HEAD checkout comparison. Existing GUI-suite reconciliation stays open.
- `python -m pytest tests/gui/test_dashboard.py -q -k 'preview_uses_retained_motion_and_backward_scrubbing or preview_rejects_setup_resolved_durations_without_mutating_program' --basetemp=.tmp-preview-prefix-retention`:
  2 passed,1041 deselected.
- `python -m ruff check` and `python -m ruff format --check` on
  `src/cephvr/visual_stimulus/compiler/expansion.py`,
  `src/cephvr/gui/trial_preview_plan.py`, `src/cephvr/gui/preview_motion_data.py`,
  `tests/gui/test_stimulus_authoring.py`, `tests/visual_stimulus/test_compilation.py`:
  pass (five files). Initial format normalized the added compiler test.
- `python -m mypy --platform win32` on the three source files above:
  success, no issues.
- `python tools/check_backend_boundaries.py`:791 modules,0 violations.
  No affected source module exceeds500 lines; existing other-module cohesion
  advisories are unchanged by this increment.
- `git diff --check`:pass before final report reconciliation; repeated afterward.

The running app was not restarted. Full backend execution, Setup resource acceptance
and native/optical/full-load behavior were not exercised by this change.
