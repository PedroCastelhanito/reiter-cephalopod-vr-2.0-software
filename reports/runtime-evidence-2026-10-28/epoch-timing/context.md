# Epoch-owned stimulus timing — 2026-10-28

Source revision: e4dd8f2694aa075380fe6711a884fe5894763c6f plus the current working
tree, including pre-existing concurrent changes. Owner requested removal of duplicate
pattern count/duration, and explicitly selected a new deterministic pattern on each
repetition. Authority: [G01](../../../docs/architecture/gui.md#g01),
[V04](../../../docs/architecture/visual_stimulus.md#v04), ARCH-002 and E15.

## Validation

All commands use `.venv/Scripts/python.exe`; GUI uses `QT_QPA_PLATFORM=offscreen`.

- `-m pytest tests/gui/test_stimulus_authoring.py tests/gui/test_dashboard.py -q
  -k '(sparse_layer or sparse_epoch or sparse_repeated or trial_preview_generates_sparse
  or looming or fade or parameter_forms_round_trip or subgroup or batch or
  reference_fades or reference_advanced or reference_updates) and not camera and
  not callbacks and not reference_type' --basetemp=.tmp-epoch-timing-final`:
  54 passed, one fixture error because demo assets require an external output root.
- `-m pytest tests/gui/test_dashboard.py -q -k
  'subgroup_rules_persist_and_random_projectors' --basetemp=<external>/epoch-timing-gui`:
  the remaining case passes. Total 55 attributable GUI passes.
- `-m pytest tests/visual_stimulus/test_resources.py tests/visual_stimulus/test_compilation.py
  -q -m 'not windows and not rig' --basetemp=<external>/epoch-timing-backend`:
  162 passed. Includes nested repeats, seed wraparound, held-pattern request timing,
  distinct/reproducible generated cells, malformed hidden count rejection and legacy
  timed playback. Earlier in-repository basetemp triggered three demo fixture errors;
  external-root runs pass all three.
- `-m pytest tests/visual_stimulus/test_lifecycle.py -q -k sparse
  -m 'not windows and not rig' --basetemp=.tmp-epoch-timing-lifecycle`:
  4 passed, 74 deselected.
- `-m ruff check src/cephvr/gui src/cephvr/visual_stimulus tests/gui tests/visual_stimulus`:
  passes. Same paths with `-m ruff format --check`: 418 files pass.
- `-m mypy --platform win32 src/cephvr/gui src/cephvr/visual_stimulus`:
  396 source files pass.
- `contracts/visual_stimulus/generate_schemas.py --check`: 14 schemas, zero drift.
- `tools/check_backend_boundaries.py`: 791 modules, zero violations; cohesive existing
  schema/parameter-form size advisories reviewed in the runtime report.
- `git diff --check`: passes; links to new evidence and decision anchors checked.

External root: C:/Users/ReiterU_PC/.codex/visualizations/2026/10/28/
01a17ff3-fd67-7e30-89d0-9b4ae49a6e0e.

## Corrections and limits

Initial checks exposed old test expectations of changing noise within one epoch and
independent looming growth duration; updated to the requested behavior. New fixture
corrections: parse helper byte limit, E05 minimum trial duration and avoiding a second
call to a control-reparenting function. An editing script initially used the Windows
default text encoding; corrected affected files to their original Unicode and UTF-8
before validation. One script context mismatch made no edit.

A broader GUI keyword selection included unrelated camera/Tracking cases, showed two
failure markers and stopped progressing; interrupted only that test process. Isolated
`test_reference_type_change_clears_asset_and_switches_stimulus_mode[picker]` fails at
an unavailable `Looming` menu choice (current value remains Texture drift). HEAD's
FILE_TYPES also lacks Looming, establishing the pre-existing selector mismatch by
source comparison, not a full baseline execution. The paste marker was not separately
rerun. Keep this under the existing GUI-suite reconciliation task.

A broader full-lifecycle selection also stopped progressing and was interrupted with
no summary; it is not counted as a pass. Only the attributable tests above are claimed.
No device actions, managed-app restart, native pixels, optical timing or combined-load
acceptance. Old native timed-sequence evidence does not validate the newly repeated
one-pattern epochs. Follow the existing rig checklist.

## Asset-gate follow-up — 2026-10-28

Owner screenshot: Sparse noise selection blocks with Choose an asset for each
stimulus. Regression `test_sparse_noise_epoch_commits_without_an_asset` covers new
and formerly Image layers on two projectors, then checks Image still requires a
file. Both cases reproduce the ValueError before the one-line branch correction.
G01/V04 already require asset-free sparse noise; no design change.

Commands (`.venv/Scripts/python.exe`, QT_QPA_PLATFORM=offscreen):
- `-m pytest tests/gui/test_stimulus_authoring.py -q -k sparse_noise_epoch_commits
  --basetemp=.tmp-sparse-asset-red`: two expected failures before repair.
- `-m pytest tests/gui/test_stimulus_authoring.py -q
  --basetemp=<external>/sparse-asset-tests`: 34 passed after repair.
- Ruff check and format --check on src/cephvr/gui/epoch_composer.py and
  tests/gui/test_stimulus_authoring.py: pass.
- `-m mypy --platform win32 src/cephvr/gui/epoch_composer.py`: pass.
- `tools/check_backend_boundaries.py`: 791 modules, zero violations; size advisories
  concern other unchanged modules. `git diff --check`: pass.

Same source revision plus current uncommitted tree. No live app restart or device
execution; saved/in-memory user drafts were not modified by this repair.
