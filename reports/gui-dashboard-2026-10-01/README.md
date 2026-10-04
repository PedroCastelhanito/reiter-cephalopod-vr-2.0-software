# Dashboard frontend evidence — 2026-10-01

On 2026-10-04 the owner requested removal of all generated screenshots/images.
Review images and temporary synthetic image assets were deleted. Assessments,
harnesses and source hashes remain; image references below are historical only.

## Balanced projector columns — 2026-10-02

Inspected Projectors (review image removed): Size removed, Display
content-sized, Projector/Resolution share remaining width. Unassigned fits fully.
[Harness](balanced-columns-native-review.py), [closure](balanced-columns-native-window.txt),
[hashes](balanced-columns-source-sha256.txt). Uncommitted snapshot. 58 GUI/client
checks and static checks pass; boundaries 473 modules, zero violations, existing
non-GUI warnings. Windows numbering and actual hardware operation remain unverified.


## Test/Stop and compact cards — 2026-10-02

Inspected compact Microcontroller (review image removed) and
Stop state (review image removed). Stop-state capture uses a labelled temporary
COM fixture only inside the harness; ordinary discovery remains COM-only.
[Harness](test-toggle-native-review.py), [closure](test-toggle-native-window.txt),
[hashes](test-toggle-source-sha256.txt). Uncommitted snapshot. 58 GUI/client checks,
Ruff/format, Windows-target mypy (20 files), boundaries (473 modules, zero violations)
pass. Existing non-GUI size warnings remain. No physical test start/stop occurred.


## Per-pin test rows — 2026-10-02

Inspected Microcontroller (review image removed): Inputs before Outputs,
name/pin/Test rows, no camera header/rate or configurable level/edge. All page/subtab
and narrow captures retained. [Harness](pin-tests-native-review.py),
[closure](pin-tests-native-window.txt), [hashes](pin-tests-source-sha256.txt).
Uncommitted snapshot. 57 GUI/client checks, Ruff/format, Windows-target mypy
(20 files) and boundaries (473 modules, zero violations) pass. Existing non-GUI
cohesion warnings remain. Buttons log unsent intent; no physical pulse/input test
or Windows/rig acceptance is claimed.


## Fixed I/O and projector table — 2026-10-02

Inspected Microcontroller (review image removed) and
Projectors (review image removed); other pages/subtabs and narrow Cameras captured.
Fixed Outputs/Inputs, COM-only discovery, compact assignment table and desktop diagram.
This Mac has no COM ports or Windows display indices; unknown values are explicit.
[Harness](fixed-io-native-review.py), [closure](fixed-io-native-window.txt),
[source hashes](fixed-io-source-sha256.txt). Uncommitted snapshot.
56 GUI/client checks, Ruff/format, Windows-target mypy (20 files) and boundaries
(473 modules, zero violations) pass. Windows API calls are mocked locally; actual
Windows Settings equivalence, physical size accuracy and hardware behavior remain
unverified. Native reinspection corrected cell clipping and bottom corner overlap.


## Device configuration draft — 2026-10-02

Inspected native Cameras (review image removed),
Microcontroller (review image removed) and
Projectors (review image removed); all page/subtab views and
narrow Cameras (review image removed) captured. An example I/O row appears only
in this inspection; live drafts start empty. Qt port/display discovery is local and
read-only. PFS values are offline hints, not applied camera settings.
[Harness](device-config-native-review.py), [closure](device-config-native-window.txt),
[source hashes](device-config-source-sha256.txt). Uncommitted source snapshot; final
numeric frequency validation was tightened after captures without changing layout.
54 GUI/client tests, Ruff/format and Windows-target mypy (19 files) pass; boundaries
472 modules, zero violations, existing non-GUI cohesion warnings. No physical
trigger test, live viewer, SDK import, firmware or Windows/rig acceptance claimed.


## Camera and device polish — 2026-10-02

Inspected Cameras (review image removed), Arduino (review image removed)
and narrow Cameras (review image removed). Tabs fill their column and align
with the HUD border. Refresh occupies the table-header corner. Rounded header
sections plus transparent native header backgrounds remove protruding fills.
Selected-camera caption/footer removed; Test enabled is a review-only proposal.
[Harness](camera-polish-native-review.py), [closure](camera-polish-native-window.txt),
[source hashes](camera-polish-source-sha256.txt). Source is an uncommitted snapshot.
50 GUI/client tests and Ruff/format, Windows-target mypy (15 files), boundaries
(468 modules, zero violations) pass. Existing non-GUI size warnings remain.
Actual camera tests and Windows/rig verification remain unimplemented/unverified.


## Left-column device tabs — 2026-10-02

Inspected Cameras (review image removed) and narrow Cameras (review image removed).
Device tabs occupy the left column above cards while the right HUD remains aligned
across pages. All four icon labels fit. [Harness](left-tabs-native-review.py),
[closure](left-tabs-native-window.txt), [source hashes](left-tabs-source-sha256.txt).
49 GUI/client checks, Ruff/format, Windows-target mypy (15 files) and boundaries
(468 modules, zero violations) pass. Existing non-GUI cohesion warnings remain.
Native Windows/rig acceptance is unverified; owner visual review is pending.
The prior compact header trial below was rejected and superseded by this layout.


## Compact header trial — 2026-10-02

Inspected Dashboard (review image removed),
Devices (review image removed), and narrow device selector (review image removed).
One header row removes the empty band while retaining card/HUD alignment. The narrow
selector preserves the active subtab. This visual trial awaits owner review.
[Harness](compact-header-native-review.py), [closure](compact-header-native-window.txt),
[source hashes](compact-header-source-sha256.txt).

49 GUI/client tests pass, including resizing/tab synchronization and stable card
positions. Ruff check/format, Windows-target mypy (15 files) and boundaries
(468 modules, zero violations) pass; existing non-GUI cohesion warnings remain.
Initial mypy local-variable type collisions were corrected. Native Windows remains
unverified; no backend behavior changed.


## Stable card alignment and table spacing — 2026-10-02

Inspected native Dashboard (review image removed),
Cameras (review image removed) and narrow Cameras (review image removed).
Shared tools-row height aligns first cards/HUDs across pages; selected rows are
visibly dimmer than headers, and Role text has shared horizontal padding.
[Harness](aligned-cards-native-review.py), [closure](aligned-cards-native-window.txt),
[source hashes](aligned-cards-source-sha256.txt).

Offscreen GUI/client pytest: 48 passed, including equal card/HUD top coordinates on
all seven page/subtab surfaces. Ruff check/format, Windows-target mypy (15 files),
and boundaries (468 modules, zero violations) pass; existing non-GUI cohesion
warnings remain. Native Windows rendering remains unverified.


## PFS camera workflow and shared HUD/log — 2026-10-02

Inspected native macOS Cameras (review image removed),
narrow Cameras (review image removed), and
Visual Stimulus layout (review image removed). All device subtabs,
Dashboard, Tracking and inactive preview rows were also captured.
Camera config now sits below inventory and exposes role, trigger source/rate and
PFS Browse only. Shared StatusColumn preserves fitted HUD/expanding log placement.
[Harness](camera-pfs-native-review.py), [closure](camera-pfs-native-window.txt),
[source hashes](camera-pfs-source-sha256.txt).

Offscreen GUI/client pytest: 48 passed (44 GUI + 4 client); Ruff check/format and
Windows-target mypy (15 source files) pass. Boundaries: 468 modules, zero violations,
existing non-GUI cohesion warnings. New checks cover all seven page/subtab status
columns and PFS selection, cancellation, camera identity and editing locks.
PFS selection performs no SDK import/readback; Windows and rig work remain pending.


## Camera inventory and active previews — 2026-10-02

Inspected native macOS Cameras (review image removed),
inactive preview rows (review image removed), and
narrow Cameras (review image removed). The two-card layout retains local
per-camera drafts and experiment enablement. Backend activity is a review-menu
fixture until Protocol integration. Camera operations/PFS remain local intent only.
[Reference provenance](camera-inventory-reference.txt), [source hashes](camera-inventory-source-sha256.txt),
[harness](camera-inventory-native-review.py), [confirmed closure](camera-inventory-native-window.txt).

Validation: offscreen pytest tests/gui tests/client/test_state_views.py: 46 passed
(42 GUI + 4 client); Ruff check/format passed; Windows-target mypy passed 15 source
files; boundaries passed 468 modules, zero violations and existing non-GUI cohesion
warnings. Initial Ruff import ordering and mypy loop-variable typing issues were
corrected before these passes. Tests cover draft retention, role uniqueness, inactive
preview rejection and authority/phase locks. Actual discovery, SDK capabilities,
connection, PFS, external image windows, Protocol integration and Windows/rig
acceptance remain unfinished.


## Simplified session and console cards — 2026-10-02

Removed Clear controls/action rows from Dashboard and Devices, renamed the card
Session config, and removed the subject subsection heading while retaining spacing.
Inspected the native macOS Dashboard (review image removed); the
[harness](clean-cards-native-review.py) also captured all Devices tabs and narrow
layout. [Closure record](clean-cards-native-window.txt), [source hashes](clean-cards-source-sha256.txt).
Offscreen GUI/client pytest: 44 passed. Ruff check/format, Windows-target mypy
(14 source files), boundaries (467 modules, zero violations) passed; existing
non-GUI cohesion warnings remain. Windows/rig acceptance remains pending.


## Card spacing and subject grouping — 2026-10-02

Native macOS inspection of Dashboard (review image removed) and
narrow Devices (review image removed) confirms increased title spacing,
inset Clear controls and separated session/subject fields without clipping.
All four Devices subtabs were also captured. [Harness](card-spacing-native-review.py),
[closure](card-spacing-native-window.txt), [source hashes](card-spacing-source-sha256.txt).
Validation: offscreen pytest for tests/gui and tests/client/test_state_views.py:
44 passed; GUI/test Ruff check and format passed; Windows-target mypy passed
14 source files; boundaries passed 467 modules with zero violations and existing
non-GUI cohesion warnings. Native Windows and rig acceptance remain pending.


## Corrected title gap — 2026-10-02

Owner reported visible rectangular masks in the earlier trial. The shared painter
now fills the card once and clips only the border underneath the transparent title.
The G02 style trial remains under review. Local macOS native inspection found no
rectangular patch or title clipping on Dashboard, Cameras or narrow Devices.

- [Source hashes](border-gap-source-sha256.txt), [capture harness](border-gap-native-review.py),
  [closure record](border-gap-native-window.txt).
- Dashboard (review image removed), Cameras (review image removed),
  narrow Devices (review image removed); all four device tabs were captured.
- Validation: offscreen pytest `tests/gui tests/client/test_state_views.py -q`:
  44 passed; Ruff check/format for GUI/tests passed; Windows-target mypy passed
  14 GUI source files; boundaries passed 467 modules, zero violations, existing
  non-GUI cohesion warnings. Windows/rig rendering remains unverified.


## Card-title style trial — 2026-10-02

The G02 revision 4 visual trial places shared card titles in the top-left border.
It remains under owner review. [Hashes](legend-cards-source-sha256.txt) identify sources.

- [44 passing tests](legend-cards-pytest.txt), [JUnit](legend-cards-pytest.xml),
  [Ruff](legend-cards-ruff.txt), [format](legend-cards-format.txt),
  [mypy](legend-cards-mypy.txt), [boundaries](legend-cards-boundaries.txt).
- Inspected Dashboard (review image removed),
  Devices (review image removed), narrow Devices (review image removed).
  [Harness](legend-cards-native-review.py), [confirmed closure](legend-cards-native-window.txt).
  Local presentation evidence only; earlier sections retain previous layouts.

## Earlier Devices draft and preview toggle

G01 revision 13 removes the count, toggles the selector and adds four Devices icon
subtabs. [Source hashes](devices-draft-source-sha256.txt) identify the local draft.

- [44 passing tests](devices-draft-pytest.txt), [JUnit](devices-draft-pytest.xml),
  [Ruff](devices-draft-ruff.txt), [format](devices-draft-format.txt),
  [mypy](devices-draft-mypy.txt), [boundaries](devices-draft-boundaries.txt).
- Native captures inspected: Cameras (review image removed),
  Arduino (review image removed), SpikeGLX (review image removed),
  Projectors (review image removed), narrow (review image removed).
  [Harness](devices-draft-native-review.py) asserts zero horizontal scroll after
  layout settles; [closure evidence](devices-draft-native-window.txt).
- Device actions report local review intent only. No backend connection, inventory,
  hardware check or saved configuration is claimed by this frontend draft.

## Earlier content-height HUD

G02 revision 3 fits HUD text and gives remaining height to the log.
Native capture (review image removed) was inspected; the
[harness](fitted-hud-native-review.py) and [closure evidence](fitted-hud-native-window.txt)
record local scope. [Hashes](fitted-hud-source-sha256.txt) identify current sources.

- [41 passing tests](fitted-hud-pytest.txt), [JUnit](fitted-hud-pytest.xml),
  [Ruff](fitted-hud-ruff.txt), [format](fitted-hud-format.txt),
  [mypy](fitted-hud-mypy.txt), [boundaries](fitted-hud-boundaries.txt).
- Existing layout tests now verify content-height changes and allocation of all
  extra window height to the log. Native/rig acceptance remains separate.

## Earlier Source/Show selector styling

G01 revision 12 adopts the reference source-table structure with refined shared
styling. Native selector capture (review image removed) was inspected.
The [harness](styled-selector-native-review.py) and [closure evidence](styled-selector-native-window.txt)
record local scope. [Hashes](styled-selector-source-sha256.txt) identify current sources.

- [41 passing tests](styled-selector-pytest.txt), [JUnit](styled-selector-pytest.xml),
  [Ruff](styled-selector-ruff.txt), [format](styled-selector-format.txt),
  [mypy](styled-selector-mypy.txt), [boundaries](styled-selector-boundaries.txt).
- Reference: CephVR1.0 `experiment_window.py` Source/Live table and tool-window
  construction around lines 7948–8051. No reference runtime or rig equivalence claimed.

## Earlier compact preview selector

G01 revision 11 removes footer buttons, instructions and redundant labels. Current
rows determine dimensions after saved-position restoration. Review labeling remains
in the native title; pending/error/unavailable status remains visible.

- [Source hashes](compact-selector-source-sha256.txt),
  [41 passing tests](compact-selector-pytest.txt), [JUnit](compact-selector-pytest.xml),
  [Ruff](compact-selector-ruff.txt), [format](compact-selector-format.txt),
  [mypy](compact-selector-mypy.txt), [boundaries](compact-selector-boundaries.txt).
- [Native harness](compact-selector-native-review.py),
  inspected selector (review image removed),
  [closure evidence](compact-selector-native-window.txt). Earlier captures below are historical.
- Initial type checking caught a QWidget.scroll name collision; renamed the member
  before final verification. Runtime viewer integration and Windows acceptance remain pending.

## Earlier folder, path, log and geometry conveniences

G01 revision 10 adds the accepted conveniences. [Source hashes](quality-source-sha256.txt)
identify the current frontend. Geometry memory applies to the modeless selector;
backend image viewers are not implemented by this increment.

- [41 passing GUI/client tests](quality-pytest.txt), [JUnit](quality-pytest.xml),
  [Ruff](quality-ruff.txt), [format](quality-format.txt), [mypy](quality-mypy.txt),
  [boundary check](quality-boundaries.txt). Existing backend size warnings remain.
- [Native inspection harness](quality-native-review.py),
  Dashboard capture (review image removed), selector (review image removed),
  [confirmed visibility/closure](quality-native-window.txt). Inspected native output
  path elision, Browse placement and populated log at 1175×883. The harness uses a
  temporary preferences file; the normal local entry uses CephVR/Frontend QSettings.
- Picker tests exercise selection, cancellation and editing changes without invoking
  native OS dialogs. Geometry tests recreate the window using a temporary INI file;
  these checks do not establish Windows or backend image-window behavior.

## Earlier header placement and selector snapping

G01 revision 9 moves preview access to the Dashboard's top-right header and uses
CephVR1.0's top-aligned right-column placement with a shared 12-pixel gap, constrained
to the main screen. [Source hashes](snap-source-sha256.txt) identify this increment.

- [37 passing GUI/client tests](snap-pytest.txt), [JUnit](snap-pytest.xml),
  [Ruff](snap-ruff.txt), [format](snap-format.txt), [mypy](snap-mypy.txt),
  [boundary check](snap-boundaries.txt): all passed. Existing backend size warnings remain.
- [Native harness](snap-native-review.py) verified frame alignment in the clamped case
  and exact 12-pixel separation with space available; [geometry/closure evidence](snap-native-window.txt).
  Inspected 1175-pixel Dashboard (review image removed) and
  900-pixel Dashboard (review image removed); selector capture (review image removed).
- The first type check flagged Qt's optional `window()` result; added its guard before
  final checks. This is local macOS presentation evidence, not Windows/rig acceptance.

## Earlier modeless preview selector

G01 revision 8 accepts the secondary preview selector. Earlier layouts below are
historical. [Current hashes](previews-source-sha256.txt) identify the uncommitted
frontend and behavior tests; no backend viewer or transport implementation is claimed.

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui tests/client/test_state_views.py -q --junit-xml=reports/gui-dashboard-2026-10-01/previews-pytest.xml`:
  [34 passes](previews-pytest.txt), [JUnit](previews-pytest.xml).
- GUI Ruff check, Ruff format check, Windows-target mypy and boundary checker:
  [lint](previews-ruff.txt), [format](previews-format.txt),
  [types](previews-mypy.txt), [464 modules / zero violations](previews-boundaries.txt).
- [Native harness](previews-native-review.py):
  Dashboard (review image removed), selector (review image removed),
  [visibility and confirmed closure](previews-native-window.txt). Inspected the
  1175×883 Dashboard and 460×350 selector, then closed and reopened for owner review.
- [Offscreen script](previews-visual-qa.py) generated
  Configuration (review image removed),
  Running (review image removed) and narrow (review image removed);
  the narrow capture was inspected alongside native captures.
- CephVR1.0 source review at `38f728291ed551a332392dc2c7b6897e8428b060`, with unchanged
  `protocol/src/protocol/gui/experiment_window.py`, found folder selection, compact-path
  tooltips, log scroll preservation, contextual help and viewer geometry retention.
  Current recommendations and source locations are in the
  [owning assessment](../runtime.md#gui-preview-design-review).

## Earlier badge removal and sketch review

G01 revision 7 removes header connection/local-control badges and unused pill helpers.
Earlier evidence below retains historical layouts; current sources are identified by
[badge-removal hashes](badges-source-sha256.txt). No backend behavior changed.

- GUI/client tests: [31 passes](badges-pytest.txt), [JUnit](badges-pytest.xml).
- Static checks: [Ruff](badges-ruff.txt), [format](badges-format.txt),
  [Windows-target mypy](badges-mypy.txt), [boundaries](badges-boundaries.txt).
- Native capture: Dashboard (review image removed),
  [capture harness](badges-native-review.py), [closure evidence](badges-native-window.txt).
  Inspected at 1175×883, closed with exit 0, then reopened for owner review.
- Offscreen captures generated by [this script](badges-visual-qa.py):
  Configuration (review image removed),
  Running (review image removed), narrow (review image removed).
- Interactive sketches live in the task visualization directory as
  `dashboard-preview-sketches.html`. All three wide captures were visually inspected;
  [browser QA script](badges-sketch-qa.cjs) records its absolute artifact location and
  [transcribed successful output](badges-sketch-qa.txt) records geometry/interaction scope.
  Sketches are proposals and local interactions only, with no device/viewer integration.


Scope: [G02](../../docs/architecture/gui.md#g02) local frontend presentation under
[E15](../../docs/architecture/system-contracts.md#e15), not experiment or rig acceptance.
Current implementation assessment lives in the
[runtime report](../runtime.md#dashboard-frontend-implementation).

## Initial implementation evidence

This section records the earlier implementation and its historical window handoff.
The simplification below supersedes its layout, feature inventory and running PID.
Baseline HEAD: `5c24d99aacf41f75fd07249faa1bfb52cf1dea78`, plus uncommitted GUI changes.
[Source hashes](source-sha256.txt) identify the checked GUI/test/tool/packaging files.
[Environment](environment.txt): macOS ARM64, Python 3.11, PyQt6 6.11.0/Qt 6.11.2.

| Method | Outcome | Evidence |
| --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui tests/client/test_state_views.py -q --junit-xml=reports/gui-dashboard-2026-10-01/pytest.xml` | 21 passed: 17 widget checks, 4 existing state-view checks | [stdout](pytest.txt), [JUnit](pytest.xml) |
| Ruff check on `src/cephvr/gui tests/gui tools/check_backend_boundaries.py` | Passed | [stdout](ruff.txt) |
| Ruff format check on the same paths | 12 files formatted | [stdout](format.txt) |
| `.venv/bin/python -m mypy --platform win32 src/cephvr/gui` | Passed, 10 source files; static only | [stdout](mypy.txt) |
| `.venv/bin/python tools/check_backend_boundaries.py` | 463 modules, zero violations; existing non-GUI size warnings | [stdout](boundaries.txt) |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python /private/tmp/cephvr-dashboard-visual-qa.py` | Rendered and visually inspected Configuration/Running at 1440×940 and narrow at 720×800 | [Exact script](visual_qa.py), Configuration (review image removed), Running (review image removed), Narrow (review image removed) |
| `.venv/bin/python /private/tmp/cephvr-dashboard-open-review.py` with desktop access | Native Qt window verified visible, captured/inspected at 1175×883 and left running; compact three-column layout | [Exact script](open_review.py), [Window result](native-window.txt), Native Qt capture (review image removed) |

Checks cover phase/observer edit locks, offline command refusal, local intent without
session advancement, trial value/reordering/removal preservation, Use/Save behavior,
completed-session display, navigation/reflow ownership and visible wide-layout logs.
Review subject/program/status values are explicitly sample data. Widgets only retain
local drafts; there are no device/network/filesystem-output operations.

The first dependency installation failed on sandbox DNS, then the repository-local
approved install succeeded. Initial static diagnostics were repaired. Offscreen Qt
uses a platform font fallback where Segoe UI is absent; the font alias warning is not
a timing/performance measurement. Initial macOS native launch failed with
`Cannot create window: no screens available`; the approved launch of
`.venv/bin/python -m cephvr.gui.review --review` ran initially (PID 31267), then a
delayed inspection interruption retired it. The local review harness reopened the
same frontend; its native capture exposed the need for compact three-column sizing.
Only that verified review PID was retired for the corrected layout. The final window
is visible and running at PID 31977. Computer-use app inspection timed out; no desktop
capture is claimed. The first three screenshots are offscreen QWidget renders;
`dashboard-native.png` is a Qt-owned capture of the actual Cocoa window. Owner review
and Windows/native managed integration remain pending.

`.venv/bin/python -m build --no-isolation` failed at the existing `setup.py` guard:
`RuntimeError: native CephVR DLLs can only be packaged for AMD64 Windows`.
This error excerpt is transcribed from the tool output; the full build traceback was
not saved. No platform check or native DLL was changed to bypass it. Windows package
validation and full application/device/workload acceptance remain open in the
[rig worklist](../rig-verification.md).

## Dashboard simplification

This section records the preceding six-card layout and historical window handoff;
the height/layout revision below supersedes its contents and running-window status.

Owner-directed [G01 revision 2](../../docs/architecture/gui.md#g01) removes the
design-review banner, frontend footer, trial editor, separate progress card and
external-preview controls. Six remaining cards use two responsive columns; narrow
windows stack them. Fixture phase/observer inspection moved to the native View menu.
No Protocol tab or backend integration was added. The baseline HEAD/environment above
still applies; [current source hashes](simplified-source-sha256.txt) distinguish this
increment from the initial files.

| Method | Outcome | Evidence |
| --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui tests/client/test_state_views.py -q --junit-xml=reports/gui-dashboard-2026-10-01/simplified-pytest.xml` | 21 passed: 17 widget checks, 4 existing state-view checks | [stdout](simplified-pytest.txt), [JUnit](simplified-pytest.xml) |
| `.venv/bin/python -m ruff check src/cephvr/gui tests/gui` | Passed | [stdout](simplified-ruff.txt) |
| `.venv/bin/python -m ruff format --check src/cephvr/gui tests/gui` | 10 files formatted | [stdout](simplified-format.txt) |
| `.venv/bin/python -m mypy --platform win32 src/cephvr/gui` | Passed, 9 source files; static only | [stdout](simplified-mypy.txt) |
| `.venv/bin/python tools/check_backend_boundaries.py` | 462 modules, zero violations; existing non-GUI size warnings | [stdout](simplified-boundaries.txt) |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python /private/tmp/cephvr-dashboard-visual-qa.py` | Rendered/inspected Configuration and Running at 1440×940, narrow at 720×800 | [Exact script](simplified-visual-qa.py), Configuration (review image removed), Running (review image removed), Narrow (review image removed) |
| `.venv/bin/python /private/tmp/cephvr-dashboard-open-review.py` with desktop access | Native window visible and inspected at 1175×883; left open at PID 32876 | [Exact script](simplified-open-review.py), [Window result](simplified-native-window.txt), Native Qt capture (review image removed) |

The existing behavior checks were updated for two-column reflow and menu fixture
inspection. The obsolete trial-edit test was replaced with exact six-card contents
and absence of the removed banner/footer. The native capture is the actual Cocoa
window grabbed by Qt (2350×1766 device pixels); the other three captures are offscreen
widget renders. These checks establish local presentation behavior only; pending
Windows packaging, managed integration and rig acceptance above remain unchanged.

## Runtime status placement and shared height rule

This section records the preceding layout; the compact-controls revision below
supersedes its status placement and final review-window state.

Owner-directed [G01 revision 3](../../docs/architecture/gui.md#g01) removes participation/
use/save editing from Dashboard, moves compact Runtime status below the subject card
and places Runtime HUD/Activity log in the right column. Recording and metadata
evidence remain separate HUD values. [G02 revision 2](../../docs/architecture/gui.md#g02)
requires HUD/console cards to fill available column/window height using shared
expanding size policies/layout stretch, with readable minima and narrow-window scroll.
Protocol implementation remains deferred. The baseline HEAD/environment above still
applies; [source hashes](height-source-sha256.txt) identify this increment.

| Method | Outcome | Evidence |
| --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui tests/client/test_state_views.py -q --junit-xml=reports/gui-dashboard-2026-10-01/height-pytest.xml` | 21 passed: 17 widget checks, 4 existing state-view checks | [stdout](height-pytest.txt), [JUnit](height-pytest.xml) |
| `.venv/bin/python -m ruff check src/cephvr/gui tests/gui` | Passed | [stdout](height-ruff.txt) |
| `.venv/bin/python -m ruff format --check src/cephvr/gui tests/gui` | 10 files formatted | [stdout](height-format.txt) |
| `.venv/bin/python -m mypy --platform win32 src/cephvr/gui` | Passed, 9 source files; static only | [stdout](height-mypy.txt) |
| `.venv/bin/python tools/check_backend_boundaries.py` | 462 modules, zero violations; existing non-GUI size warnings | [stdout](height-boundaries.txt) |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python reports/gui-dashboard-2026-10-01/height-visual-qa.py` | Inspected Configuration/Running at 1440×940 and narrow at 720×800 | [Exact script](height-visual-qa.py), Configuration (review image removed), Running (review image removed), Narrow (review image removed) |
| `.venv/bin/python reports/gui-dashboard-2026-10-01/height-native-review.py` with desktop access | Actual native window inspected at 1175×883, then closed; process exited successfully | [Exact script](height-native-review.py), [Window/closure result](height-native-window.txt), Native Qt capture (review image removed) |

The obsolete participation/save test was replaced by a layout/resize check: HUD/log
cards share the full right-column height, text areas grow at 883/1100 px and runtime
status is below subject fields in the left column. Exact card contents now number
five. Native capture is Qt-owned (2350×1766 device pixels), not a desktop screenshot.
PID 33257's harness reports `Closed after inspection: True` and exit code 0. The prior
review session was already exited when checked; no review window was left open.
These remain local presentation checks, not managed integration or rig acceptance.

## Compact Runtime status and System controls

This section records the preceding menu-based controls; the contextual-controls
increment below supersedes their button dispatch and secondary menu.

[G01 revision 4](../../docs/architecture/gui.md#g01) puts Runtime status above System
controls and subject/session fields. Independent read-only round indicators replace
status pills; tooltips/accessibility text retain detailed evidence. Main buttons are
Setup, Start and Stop. Stop requests the existing Stop-after-trial action; Cancel
Setup, Abort now and New session remain in the Session menu with unchanged gates.
G02's full-height HUD/log layout remains intact. Baseline HEAD/environment above still
applies; [source hashes](compact-source-sha256.txt) identify the current files.

| Method | Outcome | Evidence |
| --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui tests/client/test_state_views.py -q --junit-xml=reports/gui-dashboard-2026-10-01/compact-pytest.xml` | 23 passed: 19 widget checks, 4 existing state-view checks | [stdout](compact-pytest.txt), [JUnit](compact-pytest.xml) |
| `.venv/bin/python -m ruff check src/cephvr/gui tests/gui` | Passed | [stdout](compact-ruff.txt) |
| `.venv/bin/python -m ruff format --check src/cephvr/gui tests/gui` | 10 files formatted | [stdout](compact-format.txt) |
| `.venv/bin/python -m mypy --platform win32 src/cephvr/gui` | Passed, 9 source files; static only | [stdout](compact-mypy.txt) |
| `.venv/bin/python tools/check_backend_boundaries.py` | 462 modules, zero violations; existing non-GUI size warnings | [stdout](compact-boundaries.txt) |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python reports/gui-dashboard-2026-10-01/compact-visual-qa.py` | Inspected Configuration/Running at 1440×940 and narrow at 720×800 | [Exact script](compact-visual-qa.py), Configuration (review image removed), Running (review image removed), Narrow (review image removed) |
| `.venv/bin/python reports/gui-dashboard-2026-10-01/compact-native-review.py` with desktop access | Native window inspected at 1175×883 and then closed (exit 0); frontend reopened afterward for owner review | [Exact script](compact-native-review.py), [Inspection/closure result](compact-native-window.txt), Native Qt capture (review image removed) |

Regressions verify immutable independent readiness lamps, the three main labels,
separate Stop/Abort intents and phase/observer locking for menu actions. The initial
test run had one stale New session button lookup after its move to the menu (22 passed,
1 failed); that assertion was updated. Initial mypy runs exposed mixed Qt action/button
inference, repaired with separate locals and explicit unions without behavior changes:
[first diagnostics](compact-mypy-initial.txt), [intermediate diagnostics](compact-mypy-intermediate.txt).
Native/offscreen captures precede only those final type annotations; visual behavior
is unchanged. The earlier review PID 33489 was identified and retired before refresh;
inspection PID 33786 confirmed closure. The reviewed frontend was reopened using
`.venv/bin/python -m cephvr.gui.review --review` and left running for the owner. No
device/backend operation or managed/Windows/rig acceptance is implied.

## Contextual Setup and Stop controls

This section retains the preceding five-card layout. The sizing/grouping increment
below supersedes its separate status card, age label and controls badge.

[G01 revision 5](../../docs/architecture/gui.md#g01) maps Setup to preparation in
Configuration or New session in Ended. Stop requests Cancel Setup in SettingUp/Ready,
otherwise opening a session chooser with Stop now, Stop after trial and Cancel.
Stop now retains E06's immediate-interruption meaning. Cancel/Escape/window dismissal
sends no intent. Current phase/control changes update the chooser and close it when
no action remains available; selection rechecks authority. Contextual controls replace
the redundant Session menu. Baseline/environment above still applies;
[current source hashes](contextual-source-sha256.txt) identify this increment.

| Method | Outcome | Evidence |
| --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui tests/client/test_state_views.py -q --junit-xml=reports/gui-dashboard-2026-10-01/contextual-pytest.xml` | 31 passed: 27 widget checks, 4 existing state-view checks | [stdout](contextual-pytest.txt), [JUnit](contextual-pytest.xml) |
| `.venv/bin/python -m ruff check src/cephvr/gui tests/gui` | Passed | [stdout](contextual-ruff.txt) |
| `.venv/bin/python -m ruff format --check src/cephvr/gui tests/gui` | 11 files formatted | [stdout](contextual-format.txt) |
| `.venv/bin/python -m mypy --platform win32 src/cephvr/gui` | Passed, 10 source files; static only | [stdout](contextual-mypy.txt) |
| `.venv/bin/python tools/check_backend_boundaries.py` | 463 modules, zero violations; existing non-GUI size warnings | [stdout](contextual-boundaries.txt) |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python reports/gui-dashboard-2026-10-01/contextual-visual-qa.py` | Inspected Configuration/Running at 1440×940, narrow at 720×800 and dialog at 440×158 | [Exact script](contextual-visual-qa.py), Configuration (review image removed), Running (review image removed), Narrow (review image removed), Dialog (review image removed) |
| `.venv/bin/python reports/gui-dashboard-2026-10-01/contextual-native-review.py` with desktop access | Native Dashboard (1175×883) and chooser (440×158) inspected, then closed with exit 0 | [Exact script](contextual-native-review.py), [Inspection/closure result](contextual-native-window.txt), Dashboard (review image removed), Dialog (review image removed) |

The existing owning test module covers direct preparation cancellation, Setup/New
session dispatch, both session stop choices, Cancel/Escape/window close, one dialog
across repeated clicks, stale after-trial choice disabling and closure on control loss.
Intent selection does not advance fixture state. Removed a duplicate HUD visibility
assertion left by the earlier output-panel merge. All checks passed on the initial
scoped run and the final evidence run. The previous review process was already absent;
inspection PID 34320 confirmed closure. The reviewed frontend was reopened with
`.venv/bin/python -m cephvr.gui.review --review` for the owner. Native captures are
Qt-owned window grabs, not desktop captures; Windows/managed/rig acceptance stays open.

## Setup sizing, Age (dph) and combined readiness candidate

[G01 revision 6](../../docs/architecture/gui.md#g01) records full-width Setup above
equal Start/Stop buttons, Age (dph) and experiment phase in the HUD only. The owner's
question about grouping readiness is presented as a review candidate: independent
read-only indicators share one horizontal row inside System controls. Its separate
status card and phase badge are removed, leaving four cards. Preview controls remain
a recommendation; no viewer UI/integration was added. Baseline/environment above still
applies; [current source hashes](controls-source-sha256.txt) identify this increment.

| Method | Outcome | Evidence |
| --- | --- | --- |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui tests/client/test_state_views.py -q --junit-xml=reports/gui-dashboard-2026-10-01/controls-pytest.xml` | 31 passed: 27 widget checks, 4 existing state-view checks | [stdout](controls-pytest.txt), [JUnit](controls-pytest.xml) |
| `.venv/bin/python -m ruff check src/cephvr/gui tests/gui` | Passed | [stdout](controls-ruff.txt) |
| `.venv/bin/python -m ruff format --check src/cephvr/gui tests/gui` | 11 files formatted | [stdout](controls-format.txt) |
| `.venv/bin/python -m mypy --platform win32 src/cephvr/gui` | Passed, 10 source files; static only | [stdout](controls-mypy.txt) |
| `.venv/bin/python tools/check_backend_boundaries.py` | 463 modules, zero violations; existing non-GUI size warnings | [stdout](controls-boundaries.txt) |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python reports/gui-dashboard-2026-10-01/controls-visual-qa.py` | Inspected Configuration/Running at 1440×940 and narrow at 720×800 | [Exact script](controls-visual-qa.py), Configuration (review image removed), Running (review image removed), Narrow (review image removed) |
| `.venv/bin/python reports/gui-dashboard-2026-10-01/controls-native-review.py` with desktop access | Native Dashboard inspected at 1175×883, then closed with exit 0 | [Exact script](controls-native-review.py), [Inspection/closure result](controls-native-window.txt), Dashboard (review image removed) |

Updated existing assertions verify Setup spanning both Start/Stop columns, equal lower
button widths, horizontal indicator placement within System controls, four card titles,
Age caption/placeholder and absence of the controls phase pill. All existing contextual
dispatch/dialog/state-lock checks still pass. The native capture is a Qt-owned window
grab; the prior review process was absent and the inspected GUI was closed before the
frontend was reopened for the owner. Combined readiness grouping remains under review;
Windows, managed integration, backend viewers and rig acceptance remain pending.


### 2026-10-02 — Per-signal enable checkboxes

Uncommitted source snapshot: [hashes](enabled-io-source-sha256.txt).
[Native harness](enabled-io-native-review.py) captures
enabled rows (review image removed), disabled rows (review image removed)
and narrow layout (review image removed). All three inspected with no clipped controls;
[window record](enabled-io-native-window.txt) confirms inspection closure.

`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui tests/client/test_state_views.py -q`
passes 59 checks. Ruff check/format for GUI source/tests and Windows-target mypy for
GUI source pass. `tools/check_backend_boundaries.py` checks 473 modules with zero
violations and pre-existing non-GUI cohesion warnings. Tests cover retained pins,
disabled test/conflict exclusion, stopping on disable, two-way camera participation
and phase gates. This is local presentation/configuration draft evidence; no COM
port was opened, no signal applied and no physical test claimed.


### 2026-10-02 — Balanced Microcontroller columns

Uncommitted [source hashes](even-io-source-sha256.txt), [native harness](even-io-native-review.py),
wide layout (review image removed), disabled rows (review image removed),
narrow layout (review image removed), and [inspection closure](even-io-native-window.txt).
Wide/narrow captures inspected: both cards align checkbox/name/pin/action columns,
with equal-width pin/actions and no clipping. Same-valued spacing literals were
replaced by theme tokens after capture/testing; no rendering value changed.

Existing GUI/client pytest command passed 59 tests. Ruff check/format, GUI
Windows-target mypy (20 files), backend boundaries (473 modules, zero violations,
pre-existing non-GUI size warnings) and whitespace checks passed. This layout-only
change does not add hardware integration or Windows/rig evidence.


### 2026-10-03 — Secondary displays and wider pin controls

Uncommitted [source hashes](secondary-displays-source-sha256.txt),
[native harness](secondary-displays-native-review.py),
Microcontroller (review image removed),
Projectors empty state (review image removed),
narrow layout (review image removed) and
[inspection closure](secondary-displays-native-window.txt).
All three captures inspected with no clipped controls. The local primary-only
screen inventory correctly produces zero projector candidates. Mocked inventory
checks preserve Windows index 4 after excluding primary index 2.

GUI/client pytest passes 60 checks. Ruff/format, GUI Windows-target mypy (20 files),
boundaries (473 modules, zero violations; existing non-GUI size warnings) and
whitespace checks pass. Initial log-message assertion/import sorting repaired.
Existing numbering matches the approach documented by
[Microsoft PowerToys](https://microsoft.github.io/PowerToys/modules/powerdisplay/design/#monitor-number-windows-display-settings);
actual Windows Settings/rig comparison remains outstanding.


### 2026-10-03 — Projector participation and equal heights

Uncommitted [hashes](participation-source-sha256.txt),
[native harness](participation-native-review.py),
Microcontroller (review image removed),
explicit projector fixtures (review image removed),
narrow layout (review image removed) and
[inspection closure](participation-native-window.txt). Inspected equal pin/Test heights
and retained/dimmed disabled projector rectangle. Mock display fixtures exist only in
the inspection harness; final GUI returns to real discovery.

Combined `tests/gui tests/client/test_state_views.py tests/visual_stimulus` with
`QT_QPA_PLATFORM=offscreen` and `-m "not windows and not rig"`: 183 passed, one skipped,
one deselected. Socket permission was required for authenticated transports.
`contracts/visual_stimulus/tests`: 40 passed, 79 subtests. Schema drift check: 11 match.
Ruff/format for affected source/tests, Windows-target mypy (139 files), boundaries
(473 modules, zero violations; existing size warnings), whitespace and links pass.
Subset tests cover all 15 nonempty combinations with fixed projection matrices and
reject disabled designated timing output. GUI managed binding and physical rig
verification remain pending; no applied-hardware or optical accuracy claim.


### 2026-10-03 — Independent photodiode/pacing and rig geometry

Uncommitted [source hashes](rig-geometry-source-sha256.txt), [native harness](rig-geometry-native-review.py),
Timing (review image removed), Rig geometry (review image removed),
Screen calibration (review image removed), and [closure](rig-geometry-native-window.txt).
Explicit review screen/geometry fixtures were used only in this harness; real inventory
and blank measurements are restored for the final owner window. Inspected field/card
spacing, diagrams and tab layout. Initial stacked-card blank space corrected before
second captures. Final placeholder shortened and Subject annotation moved below its
point after capture; no state behavior changed.

Combined GUI/client/Visual Stimulus/contracts pytest with offscreen Qt and
`-m "not windows and not rig"`: 226 passed, one skipped, one deselected, 79 subtests.
Loopback permission used for authenticated transport. Ruff/format, Windows-target
mypy (141 source files), 11 schema drift checks, boundaries (475 modules, no violations;
existing backend cohesion warnings), whitespace and local links pass. Tests cover
independent pulse-off/pacing, disabled or missing stored marker target, null marker
evidence, valid physical geometry and retained per-face drafts. GUI profile adoption,
physical optics and Windows acceptance remain pending; no rig pass claimed.
