# Repository cleanup and review — 2026-10-26

Source baseline: `f82be21f28d3c1141adeabe2558c29808062727a`, with the owner's existing
uncommitted GUI/preview/recording changes. Owner confirmed Claude tests complete and
authorized reviewing/fixing their findings, final validation, cleanup, commit and sync.
GPT-6 Astra adjudicates changes; GPT-6 Luna readers/implementers cover GUI and the
non-GUI owners. Root integrates evidence and validation. No new dependency or
scientific backend scope is selected. Decisions: ARCH-002, G01/G02, E08/E15.

## Current findings

- Advanced-off lost the stimulus close request while an earlier command was pending.
  Reuse the existing viewer-close queue; preserve source/capture ownership.
- Dashboard test teardown did not deliver DeferredDelete. The isolated ownership
  probe reports `deleted_after_processEvents False` and
  `deleted_after_sendPostedEvents True`.
- Correct teardown exposed unowned local-review simulation callbacks. The isolated
  Setup-click test passed its body then exited with native status `-1073740791`
  (`0xC0000409`). Parented single-shot timers preserve cumulative delays and the
  simulation token while canceling callbacks on destruction; the exact test then
  passes with native exit0. This does not identify the cause of the older
  CalibrationCards construction access violation.
- Narrow Protocol layouts clipped the timeline heading, Preview action and group
  fields. G01 revision334 clarifies stacking the same existing cards. Current
  full/narrow captures cover Standard, Retro and Amber, with a populated variation
  rule; direct child captures expose controls below the viewport.
- Arena pose headings now wrap so their minimum widths do not shift the shared
  second-column alignment at narrow widths. The same-widget geometry probe
  confirms the cause (`arena-column-probe.log`); exact alignment assertions remain.
  The timeline culling test now fixes its intended400px width, verifies actual
  width and visible intersections; parent layout resizing previously invalidated
  its assumed paint bound. Production timeline culling is unchanged.
- Shared test fixtures no longer import other test modules. Eleven moved
  definitions/classes preserve their AST behavior; existing owner support modules
  are reused, except acquisition's new shared recording-fixture module for two
  existing behavior modules. No test scenarios are removed.
- Broad source/caller review found no safe additional runtime deletion in the
  non-GUI owners. Vulture's remaining high-confidence findings are unused callback
  or test-stub parameters, not evidence that their interfaces are removable.

## Validation provenance

Use `.venv/Scripts/python.exe` (Python3.11). Commands run from repository root.
Local communication tests require the authorized loopback/filesystem access;
GUI tests use the offscreen platform. Final local validation is complete.

- `-m pytest tests -q -m "not windows and not rig" --ignore=tests/gui --timeout=60`:
  the initial restricted attempt stalled and was interrupted. The authorized-access
  baseline passed2640, skipped5, deselected48, with three asset-fixture errors caused
  by an in-repository basetemp. The generator deliberately requires an external
  directory. An external-temp resource rerun passed56, and the settled full backend
  run with an external basetemp passed2643, skipped5, deselected48, plus3subtests
  in28.46seconds (`backend-final.log/xml`).
- `-m pytest tests/gui -q -n 4 -m "not windows and not rig"`: diagnostic run with
  the corrected teardown but before all fixes completed reports1044passes/38failures
  in318.22seconds (`gui-review.log/xml`). Eighteen assertion failures reproduce
  Claude's findings; four import errors arose while helpers were being moved during
  this diagnostic run; sixteen workers crashed on local-review action teardown.
  This is not a final validation pass. An earlier serial baseline was interrupted
  after identifying retained-window accumulation; its partial output is retained.
- The first settled full GUI run reports1069passes/two layout assertion failures
  in268.74seconds (`gui-final.log/xml`), with no worker crashes. Both reproduce
  serially (`gui-last-two.log`). Collection comparison finds zero removed dashboard
  nodes and five added regressions:953 original to958 current, plus113 other GUI
  nodes (`collection-reconciliation.log`). Crash totals in the earlier diagnostic
  are not unique collection counts.
- Final full GUI rerun after both reviewed corrections passes all1071 tests in
  267.47seconds, exit0, no worker crashes (`gui-validated.log/xml`). The exact
  final two cases also pass (`gui-last-two-fixed.log/xml`).
- `-m pytest tests/platform/test_window_coordinates.py tests/acquisition/test_manual_preview.py
  -q -m "windows and not rig"`: two synthetic native preview checks pass,
  169deselected, six existing SWIG deprecation warnings (`native-preview.log/xml`).
  No camera/MCU/experiment actions or rig-throughput acceptance.
- `-m ruff check src tests tools scripts`: passes. `-m ruff format --check src
  tests tools scripts`:999files pass. `-m mypy --platform win32 src/cephvr`:871sources
  pass. `tools/check_backend_boundaries.py`:760modules, zero violations; advisory
  sizes reviewed for cohesive ownership, not treated as mandatory splitting.
- `tools/generate_contracts.py --output .test-tmp-review-contracts`:19schemas
  compile; regenerated `*_pb2*` files hash-identically to installed bindings.
- `render.py` captures real widgets with isolated settings and no backend commands.
  `render.log` records dimensions and styles. Offscreen renders do not establish
  alternate-DPI or physical display acceptance.

## Cleanup and synchronization

Initial cleanup removed147 repository-contained, untracked, non-reparse disposable
directories:5763files/137337999bytes. It preserved source/tests, environment,
generated runtime bindings, settings, emergency reports and retained evidence.
Root `.test-tmp*` directories are now ignored. Captured `reports/**/output/` datasets
remain local and ignored, like existing recording directories; this preserves about
1.18GB of outputs including an848MB frame log without adding it to Git. Summaries,
methods and provenance remain eligible for version control. No retention-policy
cleanup or recording deletion was performed.

Final cleanup removed74 repository cache/test directories and four probe INIs:
6346files/149895033bytes (`cleanup-final.json`). Ten named external test directories
were also removed:6320files/111029425bytes (`cleanup-external.json`). Absolute paths
and absence of reparse points were checked; no tracked content was removed.

Remote fetch showed HEAD and origin/main equal before changes. Local validation
and cleanup are complete; commit/sync follows and its result is recorded in LOG. Existing E15 rig deferrals
and unrelated TODO acceptance items remain open.
