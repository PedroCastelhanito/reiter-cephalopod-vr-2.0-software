# Controller and supervisor status

## Runtime GUI history inventory repair — 2026-10-22

`runtime-gui-camera-inventory-repair`: saved `config/runtime_gui.json` retained Eye
camera40278236 after the owner's earlier Behavior40065509/Tracking40747103 selection.
Full GUI validation reproduces the inventory mismatch; G01 correctly preserves the
unrestored file and blocks overwriting it. Removed only the Eye camera draft and its
recording flag after a byte-identical backup. Other settings, including role-based MCU
wiring, remain unchanged. No source, contract, policy or dependency change (ARCH-002).

[Evidence](runtime-evidence-2026-10-22/runtime-gui-history-repair/validation.json)
records hashes, source revision and method; the adjacent original JSON preserves the
previous file. Repository Python3.11 offscreen checks pass full GUI validation,
GuiHistory restoration, exact two-field-change assertions and evidence-only atomic
save/readback against explicit two-camera inventory records. First script reached all
passing assertions but exited1 during implicit Qt teardown without diagnostics;
repeat with explicit deferred widget deletion exits0. Native GUI was left unchanged;
its restore latch requires reopening. Close without saving discards current-window
edits and retains the repaired on-disk draft. Native reopen/save remains unverified;
no hardware actions or runtime/rig acceptance claimed.

## Sidebar subtab selection — 2026-10-22

G02rev128 replaces child-link selection boxes with a2px left accent bar, brighter
text/icons and an unfilled background. Hover also stays unboxed. Existing sidebar
selectors and icon owner reused (ARCH-002); no state/dependency changes. All3 focused
style/navigation tests, Ruff/format2 files, Win32 mypy2 sources and boundary751/zero
checks pass. [Actual Amber sidebar](runtime-evidence-2026-10-22/subtab-selection/amber_phosphor.png)
and Retro render inspected; all three palettes rendered offscreen from a1920x1000
sample window. Native GUI was not restarted; existing native follow-up remains.

## Navigation selection feedback — 2026-10-22

G02rev127: Amber selected main navigation paints `< Icon Title >`, preserving the
canonical button text. Checked-state repaint occurs before clicked/page-layout work;
checked-hover text remains coral instead of inheriting the later hover color.
ARCH-002 reuses existing button/appearance/theme owners with no new state or
dependency. Four focused GUI tests and Ruff/format4 files, Win32 mypy3 sources and
boundary751/zero checks pass. Existing style expectation updated for corrected
bracket direction; new behavior coverage checks paint during the checked signal.
[Actual offscreen sidebar](runtime-evidence-2026-10-22/navigation-feedback/sidebar.png)
was inspected; copying the QIcon before clearing the style option preserves its
painting lifetime. No native restart or end-to-end latency measurement performed.

## Pedro config inventory

2026-10-22: Desktop/Pedro/configs included Eye camera40278236, absent from the screenshot inventory. Owner selected Behavior40065509 and Tracking40747103 only. Removed Eye from the camera file and migrated MCU v2 to v3 using saved roles, preserving D11/D10/D12 and other settings under [G01](../docs/architecture/gui.md#g01) and the [snapshot contract](../contracts/gui-configuration-files.md). Originals retained in Desktop/Pedro/configs/backup-before-two-camera-20261022-165004.

Inline repository Python3.11 checks passed actual camera/MCU validators against focused two-camera inventory records; referenced PFS/firmware files exist. Copied files match validated evidence by SHA256. Evidence: runtime-evidence-2026-10-22/pedro-config-inventory. Source: dirty working tree based on814e555edcb50a60774ac8101c68bfde0c3b7f28. No GUI reload, SDK import, hardware commands or rig acceptance.

## Sidebar navigation hierarchy — 2026-10-22

G02rev126 retains smaller,16px-indented Dashboard/Devices child links with12px
text and16px icons, adding6px vertical margin between child rows and16px between
sidebar entries; the rail reserves40px per child. Amber main navigation is left-aligned to make the
parent-child relationship explicit. Existing rail state/selection is unchanged;
ARCH-002 review retains focused layout/theme ownership without new dependencies.
Five focused GUI checks pass, including three-style indentation/font/last-row fit;
Ruff/format3 files, Win32 mypy2 sources, boundaries751/zero violations pass.
[Dashboard](runtime-evidence-2026-10-22/sidebar-hierarchy/dashboard.png) and
[Devices](runtime-evidence-2026-10-22/sidebar-hierarchy/devices.png) are inspected
offscreen1920x1000 sample-window sidebar captures from the current working tree.
Latest spacing check:5 focused tests pass; actual Amber sidebar renders in
[runtime-evidence-2026-10-22/sidebar-spacing](runtime-evidence-2026-10-22/sidebar-spacing/dashboard.png)
were inspected. Offscreen900x620 resize retained620px window height. Existing
rail-height assertion was updated for the larger spacing. Native GUI was not restarted; existing [rig checks](rig-verification.md)
retain native acceptance.

<a id="startup-splash-preview"></a>
## GUI startup splash — 2026-10-22

`gui-startup-splash` is implemented under [G02rev123](../docs/architecture/gui.md#g02).
The approved text-only CephVR2.0 / Initializing design replaces the earlier animal
proposal. Native Qt drawing uses the bundled IBM Plex Mono font and existing palette
values; no generated bitmap or new dependency is required. [Standard](runtime-evidence-2026-10-22/startup-preview/implemented-standard.png),
[Retro console](runtime-evidence-2026-10-22/startup-preview/implemented-retro_console.png)
and [Amber phosphor](runtime-evidence-2026-10-22/startup-preview/implemented-amber_phosphor.png)
are actual offscreen Qt renders, visually inspected. Shared saved-style resolution
retains legacy fallback, unknown-to-Standard behavior and CRT-effects preference.

An application Show-event observer reproduced three transient top-level QWidgets
from BatchCreate.arrange_fields during construction: field visibility preceded Qt
parenting. Parenting those controls at creation removes these observed windows;
regression coverage checks that only the splash is shown before the ready dashboard.
The managed launch definition now selects a lightweight bootstrap that paints the
splash before importing the frontend, preserving protected bootstrap arguments and
runtime ownership. The main window is polished, laid out and rendered while hidden,
then maximized and revealed. Clicks cannot dismiss the splash; bootstrap failures
close it. Local Review also uses the splash. Controller connection/diagnostic handling
is unchanged; this visual readiness gate does not wait for all devices or extend
startup deadlines. G02rev125 makes the indeterminate segment bounce side to side
using elapsed time. Construction ChildAdded events trigger rate-limited splash-only
painting while timers are blocked; no queued frontend/controller callbacks are
processed. The animation/filter stop on close. Long non-Qt work (such as imports)
can still pause painting until control returns; no extra UI thread/process is added.
Eight focused splash tests pass, including construction-time motion without queued
callback dispatch and segment positions at both ends/return travel. Ruff/format2
files, Win32 mypy1 source and boundary751/zero violations pass. An initial offscreen
attempt using QSplashScreen.setPixmap during construction caused an access violation:
that API pumps events implicitly. The final implementation sets the base pixmap only
before construction, then draws updated frames through its own paintEvent using
QWidget.repaint; the corrected full focused run passes. No native restart performed.

ARCH-002 review: presentation and bootstrap have separate focused modules, with no
runtime back-reference. The shared font loader moved from appearance to theme; all
callers updated. The existing large main coordinator only gains startup wiring;
theme remains the cohesive token/font owner. The boundary checker classifies the new
bootstrap as assembly and an entry module, preserving feature import restrictions.
No native GUI restart or hardware operation was performed. Native white-frame/flicker,
monitor placement and fresh-launch/reopen acceptance remain in the single
[rig checklist](rig-verification.md).

Validation: repository Python3.11, offscreen GUI tests select `startup_splash or
startup_bootstrap or retro_family_switch or appearance or phosphor or subgroup`:
**28 passed**; launcher preflight/supervisor bootstrap-port selection: **25 passed**.
[GUI JUnit](runtime-evidence-2026-10-22/startup-preview/gui-tests.xml) and
[launch JUnit](runtime-evidence-2026-10-22/startup-preview/launch-tests.xml) retain final
results. Ruff check/format13 files, Windows-target mypy10 source files, boundary751
modules/zero violations pass. Initial broad GUI run had25 passes, a test asset fixture
rejecting repository-local output and an unreliable fixed100ms timer assertion;
external writable fixture output and signal-based waiting resolve both in the final
run. Initial font-loader caller omission and boundary classification were corrected
before final checks. Two broader supervisor selections stalled (17 and25 completed
dots respectively) and were interrupted, with no full-suite pass or cause established;
selected static bootstrap/preflight behavior passes independently. The missing local
`modules` binding in the intermediate relaunch edit was caught by lint/mypy and fixed
to use the shared REQUIRED_MODULES definition. [Provenance](runtime-evidence-2026-10-22/startup-preview/implementation-context.json).

<a id="rig-checks-oct22"></a>
## Current rig verification — 2026-10-22

Sol 6.1 manages tests; Astra reviews results under
[GOV-001](../architecture.md#gov-001)/[E15](../docs/architecture/system-contracts.md#e15).
[Raw commands, provenance, logs and JUnit](runtime-evidence-2026-10-22/rig-checks/README.md)
retain initial failures, instrumented runs and validation limits.

**Current rig result:** final uninstrumented corrected-source session
f8ee72c7 in generation e985c1a2 completes the unchanged two-trial20min protocol
(two natural600s trials), with confirmed cleanup and exact original runtime/history
restoration. All14 outputs close and six videos fully decode/count-match. Each trial
has17,985 Behavioral/35,972 Tracking frames; stimulus has36,000/36,001 frames.
All4000 image/blank occurrences and143,544 image bindings agree with prepared
assets/indices, with zero residency holds, mismatches or failed submissions. Every
admitted stimulus capture maps to exactly one transfer/input/encoded/decoded frame.
Camera source counters are contiguous with zero drops/invalid/native gaps; post-cutoff
exclusions remain separately accounted. Final Configuration has no errors, warnings,
prompts, session context or acquisition generation; healthy GUI remains running.
[Full decode/evidence audit](runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/final-full-fresh/output-verification.json),
[camera accounting](runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/final-full-fresh/camera-accounting.json),
[restoration/source proof](runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/final-full-fresh/restoration-verification.json).

**Timing correction:** bounded diagnostic instrumentation identifies gen2 GC pauses
of76–142ms overlapping GL/recording work. Fixed-image60s and offline evidence/engine
controls do not retain a growing graph;60s of original changing images retains313
ctypes structure types/4069 fields. Protected image identity checking declared a new
13-DWORD ABI structure and POINTER on every read, permanently retained by ctypes'
pointer-type cache. Moving the unchanged structure to module scope removes this
accumulation while preserving native identity, failure and handle semantics. An old-source
regression observes256 distinct pointer types; corrected identity/error tests and32
native independent reads pass. No GC policy, deadline, dependency or file-proof change.
Temporary hooks are removed and final source hashes match pre-validation capture.
[Diagnostic context, commands and provenance](runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/README.md).

**Helper proof correction:** reconciliation now consumes a copied, already accepted
exact-worker session cleanup proof only for a covered helper work context and its
explicitly released, failure-free `ffmpeg:command` resource. Native job-empty/exact-process
release remains mandatory; output results are never promoted. This resolves the live
trial-proof/session-proof mismatch after worker retirement. Eight proof/identity/live-job
cases and168 supervisor tests pass. The diagnostic full run,60s controls and final
uninstrumented full run have no helper retirement warnings. Registry/reconciler size
advisories remain cohesive ownership exceptions; no generic coordination state is added.

**Evidence reservation correction:** four small Clipping records per group each
reserved256KiB although observed lines are147–155bytes. A fixed-schema2048byte
reservation is conservatively sufficient for maximum escaped128-character output
IDs, all three stages and bounded scalar fields. Only that reservation changes;
the global16MiB limit, complex RenderGroup256KiB reserve, offGL serialization and
strict actual-size/overflow guards remain. A blocked-consumer32-group/128-clipping
regression reproduces the old exact overflow and preserves every record on the
correction; three maximum-schema variants pass. Astra approves source/gates.
The historical queue stall itself is not identified, and a dead consumer is not
established: the failed trial's recorder later drained successfully. No speculative
buffer, deadline, scheduling or fail-fast change is made. Original
[failed-run emergency](emergency-655095435292400-2427d2e6-3141-4519-b27b-a6b26d6ba3bf.json),
partial recordings and unknown prior closure remain retained, distinct from the
successful fresh-generation validation.

**Timing limits and final state:** final state interval maximum is31.9408ms in
trial1/26.8303ms in trial2 (p99 21.9190/22.5099ms), with zero state gaps over35ms.
Worst output submission-entry interval is38.6401ms (one Front interval over35ms);
none exceed50ms. Maximum first-group software onset delay is21.8091ms. Earlier
baseline maxima105.882ms state/107.899ms output/47.1322ms onset remain retained as
historical comparison. [Full distributions](runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/final-full-fresh/cadence-distribution.json)
establish improvement against the retained GC stalls, not uninterrupted60Hz,
acceptable optical timing, electrical trigger/exposure or scientific Tracking.
Configured ACK200ms/Started250ms/Stopped450ms remain enforced bounds, not measured
ingress margins. Exact current user configuration/history SHA256
7c12d49cc9fc46e4f8b14d547882514c49fb50b7c78ba39b27cf2f34c2d8b93c is restored;
read-only final inventory confirms idle Configuration and no active encoder/test job.

**Separate MCU admission finding:** the first final-validation Setup fails before
Start on PING at200.495ms against199.987ms remaining budget; native serial timeout,
query and read calls show delayed wall time with near-zero thread CPU. Normal Cancel
confirms cleanup and restores baseline. A same-generation retry is rejected by the
retained owner failure without device execution. One reviewed fresh restart/retry
then passes the full protocol above. This does not explain the intermittent serial
latency; `mcu-setup-ping-latency` remains open without deadline relaxation or blind
retries. [Failed admission and snapshots](runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/final-full/).

**Renderer repair:** image cleanup previously treated its first unsignaled GPU
completion fence as terminal uncertainty. The correction propagates the existing
absolute cleanup deadline through focused ports and polls pending fences on their
GL owner, preserving reservations/errors at expiry. No new deadline, state,
dependency or health waiver. Five completion/error/deadline cases and actual
GL_WAIT_FAILED coverage pass within 478 owner cases; Astra finds no further issue.
Engine/native size advisories remain cohesive ownership exceptions; the polling
stays in the existing image owner. Historical rejection's exact predicate remains
unknown: its generic message cannot identify identity/revision/release/output term,
and a pre-fix clean replay also passed. Temporary controller instrumentation is
removed; accepted command/cleanup enforcement and metadata are used without raw
payload or receipt-margin claims. Original [failed-session emergency](emergency-649269129986100-560b85e4-87df-4bdf-9d90-e4d49d32de79.json)
and unknown closure stay retained. [Current raw evidence](runtime-evidence-2026-10-22/rig-checks/cleanup-fix/).

**Separate shutdown finding:** normal idle shutdown of restored generation fc3524d2
emits a work=null CONTROLLER_PROCESS_LOST acquisition incident and reports MCU Close
unconfirmed after controller exit. [Retained emergency](emergency-652423689954500-384b547c-da84-4d02-a3a2-5a2785cc551f.json)
records SpikeGLX stop_unconfirmed=false. Exact old PIDs are absent and subsequent
fresh Setup/Cancel succeeds; Astra finds no new blocker for corrected retest, but
ordered-shutdown acceptance remains open in `idle-shutdown-ordering`. Later idle
shutdowns also reproduce JOB_INSPECTION_FAILED/WinError5 and repeated cleanup
unregistered-resource reports; [latest retained emergency](emergency-671222891311500-184b469b-d95c-4e3f-a128-b5d8e1fd7145.json).
Exact old process absence is verified before reload; none of these old closures is
upgraded by the successful fresh run.

**GUI repairs and native check:** Monitor→Amber exposed a deleted QLabel caption;
style selection now refreshes its cache from live children while preserving original
text. A separate multi-layer projector-card key overwrite destroyed earlier layer
parents; one face card now owns all layer instruments, preserving dial/map order.
Both use focused existing owners under ARCH-002. Native disposable reproduction
passes with proper Qt teardown; the original exception and an intermediate fixture
teardown failure remain labeled. Root then confirms actual managed menu Amber→Retro,
Configure→Monitor, aligned System/HUD/Log and readable timeline/Protocol/Devices at
1920×1032, restoring original Retro. These are direct tool observations, not saved
screenshots; the separate 1440×940 disposable image is retained locally. Generic
PREVIEW/NO SIGNAL with Video off is G01's intended empty state. Viewer reflow/follow,
all dialogs, alternate DPI and physical/optical checks remain open.

**Automated checks:** latest affected Visual Stimulus483 cases and168 supervisor cases pass;
scoped Ruff/format35, Win32mypy25 and boundaries749/zero pass. Prior final recording77
pass after fixture metadata tidy, Win32mypy163, scoped Ruff/format15, boundaries749/
zero and whitespace pass. No unrelated GUI rerun. The earlier full backend run records 2,633 passed, six prerequisite skips,
one deselected and one unchanged 20 ms thread-entry timing failure under concurrent
GUI load; its focused serial replay passes, giving 2,634 unique passing backend cases.
Five skips need symlink privilege/Developer Mode and one needs actual-sketch C++.
Existing Windows/native-marker and generated-image NVOF results remain distinct from
scientific Tracking, which stays deferred. Final lint/format scopes, Win32 mypy857,
boundaries749/zero, contracts/schemas and wheel/sdist checks pass; existing manifest
warning is retained. Launcher whitespace and stale generated prepared-trial schema
are repaired from authoritative source.

Full GUI899 run completes in923.07s:894 pass/5 fail. Final seven serial replays pass
12.79s with process exit0; [coverage accounting](runtime-evidence-2026-10-22/rig-checks/cleanup-fix/gui-coverage.json)
verifies899 unique nodes with passing evidence, without a single-clean-parallel-run
claim. Exact failed-node traces remain, including intermediate failed-replay Qt GC
access violations; final repaired replay exits cleanly. Window activation is explicitly
asserted before each single shortcut delivery, preserving every semantic assertion;
native focus retention across rebuild remains unverified. Three card-width fixtures
and earlier HUD/event fixtures are reconciled with accepted designs under
[G02 revision114](../docs/architecture/gui.md#g02), without production geometry/motion
changes. A linked Speed notice timing failure passes serially (all three parameters).
The exception harness fails uncaught Qt slots at owning teardown. Previous partial
runs/sandbox restrictions stay historical raw evidence, not passes. Native viewer/DPI,
optical, electrical and scientific acceptance are not closed by these local outcomes.

Oct21 `uppercase-disabled-buttons`: [G02](../docs/architecture/gui.md#g02) keeps
Retro action labels uppercase regardless of enabled state. Shared Button renderer
only; ARCH-002 removes the case branch without new dependencies. Offscreen enabled/
disabled assertions, Ruff check/format and boundaries748/zero pass (existing size
advisories). No native GUI restart.

Oct21 `dashboard-backend-status`: restored read-only Cameras, Visual stimulus and
Tracking radio indicators inside Dashboard System controls, below its title and above
actions, per [G01](../docs/architecture/gui.md#g01). Corrected insertion before the
header, which placed the row outside the painted border. Cameras follows enabled
camera drafts; Tracking follows the existing save-velocities/closed-loop predicate.
Settings signals and view installation refresh visibility; Preview has no radios.
Existing StatusIndicator and DashboardView projection are reused under ARCH-002
without dependencies or command changes. Focused system controls/participation
tests:18 passed; Ruff, Win32 mypy and boundaries748/zero pass (existing
unrelated size advisories). No native GUI restart or rig validation.

Oct21 `preview-visual-simplification`: [G01](../docs/architecture/gui.md#g01)/
[G02](../docs/architecture/gui.md#g02) align preview titles with the coral GUI hue,
show four log rows at HUD height, center controls in their body and remove the
timeline's outer card. ARCH-002 reuses existing widgets with no new dependency;
the small row host supplies vertical alignment. Final23 control/log/layout tests,
earlier4 appearance-switch cases and78 timeline tests pass. GUI Win32 mypy192,
Ruff lint and boundaries748/zero pass; existing boundary size advisories remain.
Changed-source formatting passes; final dashboard-test formatting encounters a
concurrent unrelated backend-indicator assertion at line4222. Offscreen Retro
render inspected; no native GUI restart or rig acceptance.

Oct21 `gui-hide-draft-restored-log`: suppressed the successful local-draft
restoration console message; [G01](../docs/architecture/gui.md#g01) restoration
and failure warnings are preserved. Ruff check/format and scoped whitespace pass;
boundaries748/zero with existing size advisories. Message-only deletion; no runtime
tests or native GUI restart.

Oct21 `stimulus-rig-direction-authoring`: physical-screen editor, batch/condition
and new variation controls use Right0°/Front90°/Left180°/Back−90°; matching polar
labels/readouts preserve arrow alignment. Saved angle declarations are versioned
to preserve physical movement. Existing local sources remain
unchanged until edited. Validation and native limits are in
[Visual Stimulus](visual_stimulus.md);260 focused checks pass. No GUI restart.

Oct21 repository cleanup under [GOV-001](../architecture.md#gov-001) and
[ARCH-002](../architecture.md#arch-002): removed 16,905 disposable cache/test
fixture files (183,092,944 bytes); follow-up removed remaining root pytest scratch; retained all rig evidence,
recordings, environment and concurrent work. Current unused-code scan candidates
are required callback/test-double parameters or generated imports; no source
removal justified. Ruff passes; boundaries748/zero (existing size advisories).
No behavior changes or runtime/rig validation. Full diff whitespace still flags
existing launcher line52. Method and limits: LOG `repo-cleanup-oct21-refresh`.


Oct21 `preview-top-row` / `preview-system-controls`: [G01](../docs/architecture/gui.md#g01)
and [G02](../docs/architecture/gui.md#g02) now place System controls, HUD and Console
left-to-right in one compact aligned preview row. Both Dashboard and Preview use
one Setup/Start primary button beside Stop; status radios are Dashboard-only. Session Ready
and existing authority/cleanup gates control Start; no automatic Start is issued.
Advanced previews and stream Show use standard checkboxes; the former sits in the
timeline. The log retains original timestamps; its current four-row height is
specified by the preview simplification above.
ARCH-002 reuses the shared control component and existing command admission; no
new dependencies or runtime ownership/state.30 preview/layout/control checks,
27 lifecycle/stop/gating checks and the standalone checkbox/glow test pass. Four
appearance-switch cases also passed; two combined cross-module runs stalled at the
standalone checkbox test and were interrupted. Isolated execution passes; cause is
unverified, so no complete combined-suite pass is claimed. Ruff check/format6,
GUI Win32 mypy192 and boundaries748/zero pass (unrelated size advisories).
Scoped whitespace passes. Final1440px Retro render inspected;720px geometry also
checked. No running GUI restart or live Setup/rig acceptance.

Oct21 `setup-log-checklist`: [G02](../docs/architecture/gui.md#g02) revision104
retains observed Setup stages with in-place count updates and terminal evidence.
Enabled cameras use revision-matched accepted configuration; MCU connection readback
gets a named checklist item rather than bare Ready. Backend readiness finishes its
observed preparation rows, while missing completion on Setup exit stays Unconfirmed.
Reconnect does not replay successes. ARCH-002 keeps stage retention in a focused GUI
helper, with no new dependencies or changes to runtime ownership/activation.
19 focused checklist/log tests pass after final wording/dedup changes. The broader
log selection passed59; its sole temp-directory fixture error passed separately
with a unique workspace basetemp (60 total). Ruff lint/format, GUI Win32 mypy189,
boundaries744/zero and scoped whitespace pass; size advisories concern other modules.
A synthetic offscreen Retro checklist render was inspected. WatchState coalescing
can omit intermediate stages; this GUI change retains observed steps and does not
invent device substeps or prove physical activation. No live Setup/restart performed.

Oct21 `preview-subject-coordinates`: [G01](../docs/architecture/gui.md#g01)rev282 /
[G02](../docs/architecture/gui.md#g02)rev103 align polar plots to subject directions
with Right0/Front90/Left180/Back−90 labels (current G01/G02 convention). V02 calibrated unfolding and retained
rotation align physical-screen drift; standard face rotations cover other previews.
78 preview/compilation checks, changed-file Ruff, Win32 mypy189 and boundaries743
(zero violations; existing unrelated size advisories) pass. Raw motion and rendering
are unchanged. Stationary values remain local orientation. Offscreen font glyphs were unavailable, so label readability needs native checking;
native acceptance remains in the existing [rig checklist](rig-verification.md).

Oct21 `runtime-log-terminal-format`: [G02](../docs/architecture/gui.md#g02)
revision102 requires a category for every operator-log entry. The retained summary
acknowledgement explicitly uses CONTROLLER; shared formatting supplies GUI when
no subject exists and preserves bracketed categories. Initial/replaced console
text follows the same formatter. ARCH-002 review keeps this in the existing
focused formatter/console; main.py changes only its acknowledgement text despite
its existing size advisory. No dependencies, backend state or audit format changes.
Validation covers append, details, progress replacement/results and initial rows;
85 selected checks pass; one native-mouse delivery failure in the protocol trial-row
test matches the existing GUI test limitation. Ruff lint/format, GUI Win32 mypy188,
boundaries743/zero and scoped whitespace checks pass. Native appearance remains
pending after restart; commands and initial corrections are recorded in LOG.

Oct21 `timeline-axis-clock`: [G01](../docs/architecture/gui.md#g01) uses mm:ss
for timeline ticks until the visible right edge reaches one hour, then hh:mm:ss
for the whole axis. Label spacing measures the same chosen format. All32 standalone
preview timeline checks pass, including hour-boundary cases; changed-file Ruff,
GUI Win32 mypy187, boundaries742/zero and whitespace checks pass. ARCH-002 review
reuses the existing duration formatter in the focused painter; no dependency or
state added. Boundary size advisories concern other files. Running GUI not restarted.

Oct21 `preview-20hz`: [G01](../docs/architecture/gui.md#g01) revision273 and
GUI policy7 bind camera/stimulus display pacing to 20 Hz or the slower source.
The shared optional pacer skips missed cadence slots without catch-up bursts.
373 relevant local tests pass; changed-file Ruff, Win32 mypy349 and boundaries742
(zero violations) pass. TOMLs parse. Native live cadence remains unverified; the
running app was not restarted. The saved configuration's camera preview cap was
explicitly updated from10 to20 alongside the default, so restoration uses20.

Dashboard Saving options layout follows [G01](../docs/architecture/gui.md#g01):
Data precedes Videos with a dedicated category gap and separated option columns.
Oct21 saving-options-labels renames the title and prefixes every entry with Save,
including accessibility and refreshed camera labels.13 focused dashboard cases pass;
two initial temporary-directory fixture errors passed with workspace basetemp.
Changed-file Ruff/format, recording-module Win32 mypy and boundaries744/zero pass.
No native restart performed.
ARCH-002 review retains the focused recording component and existing widget/state
ownership without new dependencies. On 2026-10-21, 10 selected dashboard tests pass,
including repeated synchronization, narrow/wide checkbox alignment and card titles.
Changed-file Ruff lint/format, GUI Win32 mypy (188 files) and backend boundaries
(743 modules, zero violations) pass; size advisories concern other modules.
The 620px Retro offscreen render was visually inspected with the bundled font.
Scoped whitespace passes; repository-wide checking reports unrelated existing
whitespace in scripts/start_runtime_gui.py. No running GUI restart or rig acceptance.

## Current rig validation — 2026-10-21

Under [E15](../docs/architecture/system-contracts.md#e15), Sol6.1 managed tests
and Astra assessed decisions. Source/dirty-tree provenance, commands and raw results
are retained in [verification](runtime-evidence-2026-10-21/rig-validation/verification.json).
The owner-approved long-path correction applies Windows extended paths only at
reservation filesystem I/O and durable-publication parent resolution, retaining
logical identities, strict same-parent/canonical checks, collision authorization,
write-through flags and lock/cleanup ordering under
[E04](../docs/architecture/supervisor.md#e04). Astra found no actionable issue.
Final controller/native platform checks pass769 with five skips, including session
paths247 and280, retained-file cancellation refusal, recovery/reopen, collision
identity, and durable create/replace/cross-parent guards. Ruff, format147, Win32
mypy116 and boundaries742/zero pass. Earlier failure-first results remain historical.

Managed session247/child261 passes Ready4.5355s/Cancel132.33ms. After a normal
shutdown and verified old-process absence, session280/child294 passes
Ready5.0185s/Cancel122.50ms on controller16d96273-2eaa-4767-a153-efc12ddf481d.
Both verify exact marker identities, removed session namespaces, Configuration
cleanup confirmed, and byte-exact original runtime/history restoration. No Start
or full texture workload was run. The initial short-geometry attempt and subsequent
pre-fix longer-session failure remain labeled separately in
[verification](runtime-evidence-2026-10-21/long-path-fix/verification.json), alongside
commands and source hashes. [Longer-path managed result](runtime-evidence-2026-10-21/long-path-fix/managed-output-280.txt).
The focused reservation/Setup task is complete; full recording acceptance remains
separate. No MCU, retry or deadline behavior was changed.

Two-camera/stimulus dummy acceptance passes: Ready cancellation, two 60-second
normal trials around a video-Off 5-second Abort (166 ms), exact fresh identities,
16 Closed/present outputs and six complete independent decodes matching logged
counts. Fresh Setup/cancel after 326.259 seconds from confirmed cleanup passes
in the same controller generation. Runtime/history restored exactly before the
full-workload attempt. Off demand filtering creates no camera obligations; the
required stimulus scientific files remain, with no camera worker or encoder.
This does not establish active-camera video-Off evidence or physical pulse levels.

The unchanged two-trial 20-minute texture protocol never reached Start:
- Initial long output-root Setup failed with WinError206 creating protocol-data,
  before recording; cleanup confirmed. The approved correction and bounded native/
  managed verification above resolve this reservation failure; full recording is untested.
- A shorter-root Setup reproduces MCU PING failure: 114.451 ms against 99.979 ms,
  write 65.560 ms, read 48.864 ms, 125 late bytes, zero partial/unmatched/malformed.
  Only 0.027 ms is outside measured calls; call spans include scheduling/GIL time
  and do not prove firmware latency. Late bytes were discarded before parsing.
  CancelSetup fails after 9.841 seconds with unconfirmed cleanup; the retained
  session and BACKEND_HEARTBEAT_LOST emergency require managed recovery.


The subsequent PING/cleanup investigation matches historical serial/channel/health
and renderer-runtime source hashes to current code. The existing focused Windows
timeout update therefore predates the failure. Retained publication timestamps place
PING failure at Setup+3317.104ms, CancelSetup progress at+3334.631ms, Visual Stimulus
**coordinator** heartbeat loss at+12479.652ms and cleanup-unconfirmed at+13168.442ms.
This does not prove renderer death or cleanup-deadline expiry before escalation.
The worker interruption warning discarded its detailed admission reason. The prior
direct CLI recovery query was rejected by the controller-only role guard, so a
complete supervisor cleanup-obligation dump is unavailable; this is an evidence
collection limitation, not a reason to bypass authentication.

New tests prove late matched and malformed serial lines are both discarded before
parsing, so zero unmatched/malformed counters do not identify the125 late bytes.
A controlled post-authentication admission race reproduces INVALID_REQUEST when
the deadline expires before ledger admission, while preserving cancellation of the
uncommitted owner ticket. It proves a possible mechanism, not the historical cause.
Focused MCU/worker suites pass188 with one skip. An isolated full/dummy controller
probe finds full snapshot max1.03ms, serialization max2.42ms and one-watcher publish
max0.345ms; full program validation max57.01ms versus dummy2.38ms. Observer gaps
peak31–35ms with no gap over100ms; observer gaps include OS scheduling,
timer and GIL effects that this probe does not separate. This did not reproduce the timeout or establish GIL/driver/firmware
causality. Historical watcher count is unknown; the harness tests zero/one.
[Investigation evidence](runtime-evidence-2026-10-21/ping-investigation/verification.json)
retains provenance, timeline, tests and offline measurements. The owner subsequently
approved bounded diagnostic logging and one controlled full-Setup/cancel retest.
Serial failures now include four per-exchange wall/thread-CPU subcall aggregates;
worker interruption warnings retain bounded rejection text and exact identity/deadline.
Diagnostics preserve original native calls, deadlines, retries and cleanup rules.
Astra reviewed the source;237 focused tests pass with one skip, supervisor owner
suite160 passes, Ruff/format8, Win32 mypy43 and boundaries743/zero pass.
The owner-approved single diagnostic Setup reproduced the watchdog PING timeout
before any read: timeout configuration36.824ms plus PySerial write81.300ms
(118.124ms total), each reporting0.000ms thread CPU. These spans include native
calls and thread resumption; they do not distinguish driver/USB delay from
scheduling or GIL waits. Reply parsing is not the proximal cause of this attempt.
Setup failed after3642.7658ms; CancelSetup succeeded in75.5936ms with cleanup
confirmed. No Start/trial occurred. Historical cleanup failure did not recur and
remains unresolved; no timeout, retry or cleanup-policy fix is justified yet.

After explicit owner approval, normal configuration commands applied/saved20Hz
acquisition session previews with C:/Users/ReiterU_PC/Desktop/tmp output. Exact
post-save live settings were restored after the test, and saved history remained
byte-identical (SHA256533ff90ab34552a703df576a3fc9f600b3bf366adaffe0b92a1040f47897e6f3).
A concurrent managed app replacement was detected before the attempt; diagnostic
source hashes and process-start timestamps were verified for the new generation.
Its stderr destination was unavailable; snapshot failure diagnostics were retained.
See [controlled retest evidence](runtime-evidence-2026-10-21/ping-investigation/controlled-setup-1/verification.json).
The owner subsequently approved one additional Setup/cancel with CPU.Verbose
native scheduling tracing and a trace-only UAC helper. Ordinary WPR initially failed
with0xc5585011 before any Setup RPC; current settings were restored, and the owner
approved transient elevation without security-policy changes. The elevated helper
successfully captured the one additional attempt (Setup4ef7107d, controller950972cb,
sessioncfe49316). Application replacement interrupted backend preparation and revoked
the client credential; normal CancelSetup completion could not be verified. This
attempt is not evidence of a new PING failure or successful normal cancellation.
No Start or repeat occurred. WPR saved the owned ETL and confirmed not recording;
stop/flush took28.781s. Offline tracerpt decoding completed with zero reported
events/buffers lost. CSwitch v5 prefix decoding was checked against Microsoft
TraceEvent, but the serial native thread could not be identified. Exploratory
latency numbers are excluded. Astra identified lifetime/ready-pairing limits in the
initial exploratory pass; a compact lifetime-filtered summary corrected these, but
no serial identity or driver, scheduling or GIL attribution is supported.

The replacement controllerab7df142 reports Configuration/cleanup_confirmed and
successful StartupRecovery for the interrupted session, with unfinished local files
deleted. Its live settings and saved history already exactly match the approved
20Hz/Desktop baseline533ff90; no restoration write was needed. A retained
startup-recovery warning reports unknown-endpoint/run SpikeGLX stop unconfirmed.
This is unresolved recovery evidence, not proof of an active remote recording or
scientific file closure (the test fixture disabled synchronization). A separate
prior-generation JOB_INSPECTION_FAILED emergency is also retained without causal
attribution. A later read-only snapshot found a separate operator generationa688e215
in Ready/session66a4aafb; it was left untouched, so the earlier recovered idle state
is historical evidence rather than the current application state. See [native trace evidence](runtime-evidence-2026-10-21/ping-investigation/native-trace-uac-1/verification.json).

The owner approved changing the engineering defaults to200ms MCU acknowledgement
and450ms shared stop reporting (A11 revision53/E05 revision99). The50ms completion
reserve is unchanged; the declared arithmetic is2*200+50=450ms. Operator TOMLs own
these values; fixed policies and their versions are unchanged. Earlier operation
boundaries still win and recording intervals do not grow. Existing serial timing
reload requires releasing the owned connection; the current rig session was not
modified or restarted. Focused loader/protocol/owner checks:211 passed, one skipped;
Ruff/format and scoped whitespace pass, backend boundaries743/zero violations
(existing size warnings). Astra review passed. Start evidence still has its250ms
limit; the increased acknowledgement budget leaves less headroom there. No live
verification or resolution of the underlying delay/cleanup issue is claimed.

Initial broad backend checks: 2,600 pass, six skip, one deselected, three failures;
all three reproduce alone. Astra traced the MCU upload/shutdown failures to the
shared test double omitting explicit Trial-state stopped evidence. The existing GUI
post-submit stale-ack test typed letters into a four-digit subject validator, so
no edit occurred. Test-only corrections supply the missing stopped field and a valid
changed ID, asserting edit_serial advances before acknowledgement. All four corrected
cases and all33 client tests pass; no production behavior changed. Complete backend
rerun passes2603 with six skips/one rig deselected. Full GUI parallel has832 passes
and two variation-hover failures; the original hover pair passes alone. An attempted
offscreen cursor-input correction was fully reverted after it failed to preserve
the expected visibility transition. Final full serial run passes834 in414.82s,
including both unchanged hover cases. Final parallel repeat passes833 and fails
`test_trial_row_actions_scroll_target_and_align_cards[standard]`: its native mouse
move is not delivered within1000ms; the earlier hover pair passes in this run.
Parallel cursor delivery therefore remains an unresolved test-environment concern,
not a proven GUI runtime defect. No further repeats or weakened tests; historical
failed/interrupted runs remain retained. Final tested-file hashes are unchanged
through the serial run.
[Automated results](runtime-evidence-2026-10-21/rig-validation/automated-summary.json)
retain exact test names/skips. Focused native ownership 17 pass/one skip, native
preview/storage nine pass, coordinate/launch 28 pass, NVOF one pass and MCU 145
pass/one skip overlap the broad suite and are not additive totals. Ruff, format
977 files, Win32 mypy 850, boundaries 742/zero and contract/schema checks pass.
Skips include missing symlink privilege and a native C++ compiler fixture.

Computer Use window inventory worked, but Dashboard capture approval timed out;
no native GUI visual acceptance is claimed. Continuous capture remains design-only;
physical optical/electrical, Eye, Tracking processing and paired SpikeGLX acceptance
remain in the [rig checklist](rig-verification.md). Managed automatic shutdown
confirmed all old owned processes absent. Supported preserving startup recovery
retained the failed session and its unknown-closure recovery record. New controller
`efe06d83-4485-4e5d-91dc-00306026a16e` is in Configuration with cleanup confirmed,
no session and no prompts; original runtime configuration and saved history restored
exactly ([restoration](runtime-evidence-2026-10-21/rig-validation/startup-recover-restore.txt)).
The definitive failed command snapshot is
[retained separately](runtime-evidence-2026-10-21/rig-validation/ping-failure-command-snapshot.json);
the generic snapshot filename was reused for later pre-recovery reads.


Oct21 `preview-all-projector-plots` / `preview-resolved-linked-motion`:
[G01rev280](../docs/architecture/gui.md#g01) keeps every projector/layer visible in
centered Advanced previews cards with a default2:1 stream/plot split matching the
owner screenshot, and plain colored headings in Left/Front/Right/Bottom
row order. `preview-heading-order-spacing` uses16px section/card gaps, removes the
reference suffix and repeated instrument titles, retaining accessible dial names.
69 focused GUI checks plus lint/format, GUI mypy and boundaries pass; updated
offscreen render inspected. `polar-label-clearance` reserves measured label widths
outside the full angular-ring stroke with a6px logical gap. Texture and tracking
labels inspected at128/204/300px widths;45 preview checks and static checks pass. `preview-fit-all-plots`
fits the cards and their instruments into adaptive rows/columns, scaling the complete
painted instruments uniformly to the available panel dimensions without scrolling. Shared multi-surface
sources receive separate plots. Followers now use the renderer's calibrated
[V02](../docs/architecture/visual_stimulus.md#v02) boundary binding with
[V07](../docs/architecture/visual_stimulus.md#v07) retained state, yielding their own
local vector, angular speed and scales. Loaded geometry is retained until edited;
geometry changes rebuild the plan. Missing geometry or invalid links report a
per-source unavailable state without hiding valid plots. Values remain planned,
not measured output. ARCH-002: reuse existing state/link helpers, no new dependencies
or runtime ownership. 71 checks pass:39 standalone preview tests,11 dashboard preview
integration tests and21 stimulus-compilation tests. Renderer comparisons include
unequal tile periods/screen distances, drift, both spin signs, stop/relink, orientation
continuity/reset and geometry invalidation. Changed-file Ruff lint/format, GUI Win32
mypy188 and backend boundaries pass (0 violations; existing size warnings outside
changed modules). Layout follow-up:45 standalone preview tests and24 dashboard
preview tests pass, including four-projector and paired-dial fits at1440x960,1000x700
and600x480 with divider changes. Offscreen render inspected; native appearance
remains under the existing preview acceptance.

Oct21 `preview-frame-details`: [G01rev271](../docs/architecture/gui.md#g01)/[G02rev101](
../docs/architecture/gui.md#g02) place titles/Show eight logical pixels above each
native frame and two measured FPS rows directly below. Adaptive columns reserve footer
height. Current exact-view rates propagate through controller projections;
hidden/unknown or three-second-stale data becomes a dash. Camera source FPS is received-
frame metadata rate, stimulus source FPS completed render batches; preview FPS counts
new viewer submissions/swaps, not optical refresh.
[E08rev180](../docs/architecture/system-contracts.md#e08) owns common semantics.
ARCH-002 uses one small shared rate meter and existing status channels; managed-camera
size warning was reviewed, with only projection fields added to its cohesive adapter. No
new dependency or whole-runtime reference. Focused verification and limitations are
recorded in LOG under this task; native appearance and live rates after restart remain
pending under the existing preview workspace acceptance item.

Oct21 `console-category-alignment`: [G02rev98](../docs/architecture/gui.md#g02)
widens the log category column to the longest category seen in each console.
The previous nine-character width put CONTROLLER's message one character to the
right of CONFIG. Existing rows now gain padding when the column grows, retaining
their QTextBlock identities, timestamps, details and result suffixes. In-place
progress uses the same width; clearing resets it. ARCH-002 reuses the focused
log formatter and console, with no dependencies or backend changes.
24 focused offscreen checks pass in both themes, including category expansion,
retained progress/results, diagnostics, selection and scroll anchoring. Changed-file
Ruff lint/format, Win32 GUI mypy187 and boundaries742/zero pass. Native restart and
appearance remain pending under the existing runtime-log-terminal-format rig check.

Oct21 `gui-startup-stray-windows`: the owner screenshot's small window was
`StimulusTimeline.notice`. Constructor refresh made this parentless QLabel visible
before its first instrument rebuild, so Qt created a top-level window. Creating
it with `instrument_host` as parent keeps all visibility under the existing
preview hierarchy ([G01](../docs/architecture/gui.md#g01)); no new window/state
or dependency. ARCH-002 review keeps the one-line ownership correction in the
focused timeline module. Regression failed before the correction on an unexpected
visible top-level QLabel and passes after it, including Advanced on/off visibility.
All20 timeline and14 related Dashboard/history tests pass offscreen; separate
construction/show checks for Review and Managed windows expose only their main
window. Ruff lint/format, Win32 mypy, boundaries (742 modules, zero violations)
and scoped whitespace checks pass. Existing size warnings concern other modules.
Native Windows startup after restart remains unverified under E15.

Oct21 `preview-hud-prompts`: the Retro preview HUD now prefixes its second-column
TRIAL and TOTAL TIME labels with `>`, matching the first-column painted gutter
(including TRIAL TIME) under G01/G02. Shared grid alignment and Standard style remain
intact. Six focused HUD tests and a Retro/Standard formatting assertion pass; Ruff,
Win32 mypy and boundaries742/zero pass. Native application not restarted.

Oct21 `preview-plot-label`: [G02rev99](../docs/architecture/gui.md#g02) moves
source controls such as Bottom · reference from the timeline header to their own
motion section directly above the plots. The timeline header retains only its epoch
readout. Source controls remain available when their plots are unchecked, and follow
Advanced visibility. ARCH-002 reuses the existing legend/dials in one layout container;
no new module or dependency. All37 selected timeline/preview layout checks pass,
including stacked/side-by-side ownership, toggling and unchanged epoch visibility.
Ruff lint/format, Win32 mypy1 and boundaries742/zero pass; existing unrelated size
warnings remain. Native application not restarted; physical appearance unverified.

Oct21 `preview-full-width-timeline` / `stationary-polar-direction`:
[G01rev270/G02rev100](../docs/architecture/gui.md#g01) keep the timeline always visible
across the full width immediately below the HUD. The separate Advanced settings
container fills the HUD row's height. Advanced controls only the motion section beside
streams and the timeline's optional size lanes. Existing 75/25 draggable splitter,
source controls beside plots, target identities and adaptive grid remain intact.
At zero speed, polar readouts show current planned layer rotation/arena yaw normalized
to0–360 degrees, as confirmed by the owner, while retaining no translation arrow.
Moving samples keep their velocity-based readout; feedback/unknown samples retain
explicit messages. PlannedStates supplies epoch continuity and resets, so seeking
backward does not retain a stale heading.

ARCH-002: reused the motion-section widget in the existing workspace layout and the
existing planned-state evaluator; one optional sample field carries stationary
orientation. No new module/dependency or backend state. All41 focused offscreen
Dashboard/timeline cases pass, including both themes, full-width row, equal header
height, splitter/visibility/restore, orientation continuity/reset and backward seeks.
Initial continuity test used a reset-enabled fixture; corrected it to cover both
modes. Ruff lint/format6, Win32 mypy4, boundaries742/zero and scoped whitespace pass.
Existing unrelated size warnings remain; application not restarted or native viewers
visually inspected. Existing [rig checklist](rig-verification.md) stays pending.
Earlier broad preview-selected test stall remains uncharacterized; this increment
claims only the focused completed checks.

Oct21 `recordings-card-categories`: [G01rev266](../docs/architecture/gui.md#g01)
groups the Recordings card into Cameras and Recorded data (Visual stimulus video,
Tracking velocities and Save spikeglx). The existing checkboxes, persistence and
phase/authority gates retain their owners. ARCH-002 review keeps this layout in
its focused recordings module with existing label/grid helpers and no dependency.
Final scoped whitespace check passes; whole-tree whitespace flags a concurrent
unrelated blank line at tests/controller/test_setup.py:679.
Five focused offscreen layout/participation/persistence cases, Ruff lint/format,
Win32 mypy and boundaries (742 modules, zero violations) pass. Repeated layout
rebuilds retain one instance of each heading/control. The rendered card was visually
inspected; [render and provenance](runtime-evidence-2026-10-21/recordings-categories/context.json)
record the local-only scope. Native GUI appearance after restart remains unverified.

Oct21 `runtime-log-terminal-format`: startup draft restoration and controller
connection messages now supply Configuration/Controller subjects to the existing
[G02](../docs/architecture/gui.md#g02) formatter, yielding `[CONFIG]` and
`[CONTROLLER]`. No new state, dependencies or formatting layer. ARCH-002 cohesion
review keeps the two literal changes at their owning lifecycle call sites in the
existing oversized `gui/main.py`; no responsibility is added. Validation: three
focused offscreen log/history cases, source/formatter assertions, Ruff lint/format,
Win32 mypy for main.py, boundaries (742 modules, zero violations) and diff whitespace
pass. Initial pytest selection matched no cases; a corrected run hit sandbox temp
creation errors, then passed with a fresh workspace basetemp. Native GUI restart
and visual confirmation remain pending.

Oct21 `setup-texture-progress`: [E08rev178](../docs/architecture/system-contracts.md#e08)
adds bounded nonterminal Setup progress admission into participant snapshots.
Exact backend generation, session, Setup command and original deadline are required;
cancelled/interrupted/completed/Ready work rejects late feedback. Progress never
satisfies readiness or completion and leaves deadlines unchanged. Visual Stimulus
now supplies decoding and initial-upload counts to the existing GUI action log.
Focused ownership, stale-report, snapshot and delivery checks pass; native verification
remains pending. See [Visual Stimulus](visual_stimulus.md#primatecuttlebase-texture-mismatch--2026-10-21).

Oct21 `continuous-camera-acquisition` design only: [E05rev98/E11rev18](../docs/architecture/experiment.md#e05)
and [E12rev26](../docs/architecture/synchronization.md#e12) bind continuous Setup-to-session
camera capture to trial-only admission/Trial-state gating, with distinct normal
trial-stop versus session/fault device-stop evidence. Runtime gates and contracts
remain pending implementation; no runtime or setting changes. See the
[acquisition assessment](acquisition.md#continuous-camera-acquisition-design--2026-10-21).

Oct21 `setup-watchdog-cleanup` / `interruption-configuration-reset`: fixed two
reproduced failure paths under [E05](../docs/architecture/experiment.md#e05),
[E08](../docs/architecture/system-contracts.md#e08) and
[V01rev28](../docs/architecture/visual_stimulus.md#v01). A failed camera resolution
no longer waits for successful adoption that cannot arrive; all sibling terminal
readbacks settle within the original deadline before retiring Setup. Visual Stimulus
now confirms native release and registers an empty session catalogue when cancellation
precedes its Setup. The controller retains that dispatch fact to distinguish absent
prepared outputs from missing output evidence. All registered participants still
require exact fenced cleanup; supervisor checks and stale-context guards are unchanged.

Final native sequence on controller `b548684d-25ca-4dc3-b8c3-31643a09b3af` passes:
missing Eye camera fails Setup in2.710s with confirmed cleanup; three subsequent
Setups take4.401–4.657s; Ready cancellation takes133ms. A recorded10s trial Abort
completes in357ms, automatically returns to Configuration, retains exact Interrupted
finalization and settings, and permits fresh Setup/Start with new identities. The
fresh60s trial completes after Stop-after-trial, then New session and restoration
pass. All14 output records are Closed/present; independent complete decoding of
six videos matches their logged frame counts. Runtime configuration and saved
history restore exactly, including Eye and recording selections.
[Sequence](runtime-evidence-2026-10-21/setup-recovery/verification-output-r6.txt),
[output verification](runtime-evidence-2026-10-21/setup-recovery/output-verification.json),
[source provenance](runtime-evidence-2026-10-21/setup-recovery/source-provenance.json).

Final owner tests:2,012 pass,4 skip,10 deselected; Ruff lint/format533, Win32 mypy463
and boundaries742/zero pass. ARCH-002 reuses existing owners without dependencies;
the687-line renderer lifecycle remains cohesive around GL-owner lifecycle and cleanup
proof, and existing large state/report owners retain their documented responsibilities.
Earlier fixture, native and sandbox failures remain retained; the interim controller-only
cleanup filter was removed after supervisor reuse correctly remained blocked. Failed
test reservations were preserved through explicit recovery. No firmware or remote
SpikeGLX action occurred. The MCU PING delay did not recur; its original intermittent
cause and full texture-workload acceptance remain open. Eye40278236 is disconnected;
native recordings used40065509 and40747103. Computer Use initially timed out;
the final retry restored the minimized Dashboard and verified Configuration,
editable session fields/Setup, disabled Start, Interrupted finalization and Done
normal-finalization rows. GUI control was returned through its Control menu.
[Native accessibility evidence](runtime-evidence-2026-10-21/setup-recovery/native-dashboard.txt)
closes `interruption-configuration-reset`; late-confirmation/shutdown/fault variants
remain in the [single rig checklist](rig-verification.md). Retained supervisor
FFmpeg-exit warnings remain in the handoff snapshot; the subsequent exact Closed
records and independent decodes establish this bounded run's final output results.

## Pilot SpikeGLX alignment inspection — 2026-10-21

Owner-requested read-only inspection of `SP0003-123824` at
`D:\cephvr-data\protocol-data\20261020_ephys-pilot\SP0003-123824`.
The earlier C: copy contains protocol files but an empty SpikeGLX folder.
[SYS-004](../architecture.md#sys-004), [E09/E12](../docs/architecture/synchronization.md)
and [V22](../docs/architecture/visual_stimulus.md#v22) govern interpretation;
this inspection does not implement or approve an analysis backend.

**Observed critical limitation:** both original metadata files have
`syncSourceIdx=0` (None). Every OneBox SY bit-6 sample has no transitions;
all117,109,938 probe SY words equal64. Thus there is no recorded shared sync
wave for OneBox-to-probe edge mapping. The metadata rates are30303 Hz and
30000.303361344537 Hz. Nominal firstSample/rate coordinates agree within1.1 us,
but that arithmetic does not measure physical start offset or clock drift.
File durations differ by154.697 ms; differing closure tails do not measure drift
and must not be used to stretch one recording onto the other. Current pilot
neural alignment cannot be certified as pulse-synchronized. Recommend external
event tables on the OneBox timeline, retaining probe timestamps separately until
an independently justified mapping exists. TPrime requires shared recorded edges.

**Protocol and available anchors:** trial1 is900 s static Gaussian texture;
trial2 is100 repetitions of10 s Translation plus20 s Static (3000 s).
OneBox XD word12 bits0/2 give trial-state and behavioral-camera edges, consistent
with saved XA0/XA2 roles. Trial-state highs are approximately1.705970–901.681913 s
and902.643237–3902.601327 s in the OneBox file. Camera trains contain26980/89935
rising edges versus26979/89933 recorded frames; the1/2 extras match explicit
post-cutoff exclusions. All source counters advance by1. Per-trial affine
camera-native-to-pulse consistency fits have RMS14.85/10.56 us; these are fit
residuals, not absolute trigger-to-exposure accuracy. First trial2 camera edge
precedes the gate edge by one OneBox sample: avoid strict gate clipping that
silently discards it. Use pulse trains, counters and saved source/video mappings.
Saved camera exposure is25 ms; preserve trigger time and exposure integration
semantics separately.

**Photodiode:** only `calibration_right` has a patch. XA1 contains recoverable
bright/dark structure, substantial high-frequency excursions and positive-rail
clipping; XD bit1 yields2,723,102 rising edges and is unsuitable as a direct frame
counter. Exploratory30-sample bin means (~0.99 ms), thresholded at1/1.5/2 V,
all yield50378/167986 transitions, exactly the logged marker-transition counts
including initial/final changes to Idle. At2.5 V extra short transitions appear.
Ordered candidate matches agree in polarity, but render-evaluation affine-fit
residuals include outliers to approximately55 ms: matching/count agreement is
not calibrated optical latency or proof of a unique match in every local interval.
Decode the actual HHHLLL/alternating sequence with explicit ambiguity and local
timing checks. Its same-level internal boundaries are unobserved; other screens
have no direct optical measurement. Renderer logs contain53978/179985 groups
with complete contiguous markers, all returned submissions and all current image
selections. Maximum evaluation gaps are355.121/94.983 ms despite zero reported
video drops; nominal video rate cannot supply scientific timestamps.

Evidence and reproducible inspection scripts:
[provenance](runtime-evidence-2026-10-21/pilot-alignment/context.json),
[pulse scan](runtime-evidence-2026-10-21/pilot-alignment/pulse_inspection.json),
[full probe scan](runtime-evidence-2026-10-21/pilot-alignment/probe_sync_full.json),
[full logs](runtime-evidence-2026-10-21/pilot-alignment/log_inspection.json),
[camera matching](runtime-evidence-2026-10-21/pilot-alignment/camera_matching.json),
[photodiode checks](runtime-evidence-2026-10-21/pilot-alignment/photodiode_threshold_checks.json),
[waveform windows](runtime-evidence-2026-10-21/pilot-alignment/photodiode_windows.png).
Binary byte counts agree with metadata; full binary hashes and video decoding
were not performed. Acquisition source revision is unknown; dev version labels
are not a source revision. Hardware recommendations remain outstanding in the
[single rig checklist](rig-verification.md#pilot-synchronization-verification).

Oct21 `preview-advanced-motion-dials`: implements [G01](../docs/architecture/gui.md#g01)
rev264/[G02](../docs/architecture/gui.md#g02) rev92. The preview card now shows an
epoch-only timeline (current epoch filled to its elapsed fraction, cursor, 5 s ticks,
hover values, click-to-inspect) and an `Epoch n / N` readout above the strip; the speed trace and
standalone polar plot are retired. A VIEW-strip Advanced previews checkbox (default
off, `windows/preview-advanced-visible`) shows per-source dials: texture dials (arrow
length = speed against labelled rings, outer ring = signed angular speed, 0°/+X down);
tracking-form forward/animal-left dials for authored trajectories and arenas; an arena
world map; texture+tracking pairs for feedback-driven textures; and a size lane when
width/height vary. Planned pose continuity replays V07 `compile_boundaries` through
renderer `InstanceState`, so continue/reset/restart match playback; an instance's pose
is unknown (Waiting for tracking) during and after a feedback epoch until a fresh
initialize/reset. Arena body frame follows V24 (`feedback/mapping.py`), sideways
animal-left-positive (T36). ARCH-002: instrument painting is `preview_motion_dial.py`,
pose replay `preview_motion_state.py`, sample selection `preview_motion_samples.py`;
`preview_timeline.py` keeps layout/clock (372 lines). Limitation: live Tracking drive
values and renderer-reported arena pose do not reach the GUI, so live-only dials always
show Waiting for tracking; no feed or command was added. Validation: see LOG entry of
the same date. Offscreen renders only; GUI not restarted and native appearance unverified.
Owner layout follow-up (G01rev265/G02rev94): the timeline card is always shown directly
under the HUD at content height and streams take the rest (Stimulus timeline checkbox,
its preference and the splitter are retired); the cursor has no separate time label;
the preview HUD aligns label/value columns (`hud_grid`); the recording lamp is hidden
when idle and shows only REC, closing or output faults.

Oct21 `preview-compact-readouts` refines [G02](../docs/architecture/gui.md#g02)
revision95: only `Epoch n / N` appears above the strip (unknown index is `—`),
with no epoch title or duration readout beneath. Motion dials place numeric values
and units on one row, showing zero speed instead of Still and signed angular speed
(positive CCW); tracking components are forward then animal-left. Unknown live
observations retain their existing explicit message. ARCH-002 review reuses the
focused timeline/formatter/painter owners without dependencies or state changes.
`.venv/Scripts/python.exe -m pytest tests/gui/test_preview_timeline.py -q`:19 pass,
including label placement, readout and existing motion/clock/painter checks. GUI
Ruff lint/format191, Win32 mypy187, boundary check742/zero and whitespace pass;
existing size advisories concern unchanged cohesive owners. Offscreen only; no
application restart or native appearance check. Existing preview verification task
retains that follow-up.

Oct21 `interruption-configuration-reset`: owner explicitly requested automatic
Configuration after an interrupted protocol. [E05](../docs/architecture/experiment.md#e05)
rev97, [E06](../docs/architecture/system-contracts.md#e06) rev79 and
[G01](../docs/architecture/gui.md#g01) rev262 now record that behavior. Finalization
settles command results before retiring the interrupted session; late verified
cleanup uses the same reset. Shutdown/authority loss and unresolved cleanup prevent
automatic reuse. Completed/Stopped sessions retain explicit New session. Durable
interrupted results, reusable configuration and control error history are preserved;
fresh Setup/Start allocate new identities. E06's prior page/register revisions were
77/78; both advance to79 with this amendment.

ARCH-002: extracted existing NewSession state retirement into one focused
`lifecycle/session_reset.py` owner shared by explicit reset and cleanup, removing
duplicated state dependencies from SessionCommands. No new dependency, runtime
back-reference or backend command. The oversized interruption module adds only
the terminal reset call; assembly only wires the shared owner. Boundary size
advisories otherwise remain pre-existing. Tests extend the owning lifecycle module.

Validation: `python -m pytest tests/controller -q -m 'not windows and not rig'
--basetemp=reports/tmp-interruption-controller` passes731, skips4, deselects6;
covers exact cleanup-before-metadata ordering, interrupted output retention,
settings retention, current/unrelated preview identity, stale old reports, late
cleanup, incomplete metadata, shutdown/authority gates and explicit completed reset.
Ruff check/format controller+tests144, Win32 mypy controller114, boundaries741/zero
and whitespace checks pass. Two initial sandbox test attempts stalled in asyncio's
loopback socketpair fixture (stack captured by faulthandler), before test bodies;
interrupted those test processes and reran with loopback access. First executable
focused run exposed one old Ended assertion; updated it to the new Configuration
contract while retaining durable Interrupted checks. No rig commands or application
restart; actual interruption/reuse confirmation remains in the
[rig checklist](rig-verification.md).

Oct21 `preview-resize-feedback` (base c740c5c2): owner reports periodic frame/window
resizing during a dummy trial. Reproduced offscreen: pending placement updates add
the "Waiting for viewer…" header row, shrinking the target by 13 logical pixels;
completion removes it, feeding changed geometry back into the 200 ms placement
poll. The existing G01/G02 presentation owner now shows waiting text only while
the viewer is not visible. Pending command gates and actual failure messages remain.
ARCH-002 review: one conditional change in the existing cohesive workspace module;
no dependencies, transport or experiment behavior changes, and regression coverage
extends the owning dashboard test module. No architecture rule was changed.

Corrected active-source regression fails before the fix with timeline both hidden
and shown, then passes repeated pending/completed geometry cycles after it. Initial
test fixture omitted active/reason fields and failed a control assertion; corrected
before using it as defect evidence. Validation: offscreen `pytest
tests/gui/test_dashboard.py -q -k 'preview_workspace or managed_preview_relayout or
managed_stimulus_preview or preview_grid' --basetemp=reports/tmp-preview-resize`
passes8; GUI/tests Ruff lint/format187, Win32 GUI mypy184, backend boundaries740
(zero violations; existing unrelated size advisories) and `git diff --check` pass.
Running trial was not interrupted or restarted; full GUI suite and native fix
acceptance remain unperformed. See the [rig checklist](rig-verification.md).

Oct21 `preview-workspace-polish`: owner-selected Previews refinements under
[G01rev263](../docs/architecture/gui.md#g01)/[G02rev90](../docs/architecture/gui.md#g02).
Stream reasons now sit centered inside their frames, so headings no longer change
height while viewers open; a one-word hint beside Show appears only for observers or
over an open viewer. The HUD row adds a recording lamp derived solely from the
existing controller output-closure status and one VIEW toggle strip. The timeline uses
a 60 s window pinned at trial start until centered, a dimmed dashed remaining plan, a
current-time cursor and outlined current epoch, hover readouts, 10% headroom,
`Speed (unit)` axes, unitless legend entries and non-overlapping clock ticks; the
not-measured caveat moved to tooltips. Previews headings use accent rather than coral.
ARCH-002: changes stay in the existing preview presentation owners (no new modules,
dependencies, telemetry or commands); preview_motion_plot.py is 469 lines.
Validation (offscreen, `QT_QPA_PLATFORM=offscreen`): 131 preview-focused tests pass,
including 9 legacy timeline cases that failed before this increment; full `tests/gui`
798 pass, 2 fail outside this change (preview HUD lacks a concurrent uncommitted
OUTPUT Dashboard row; ManagedConfiguration.stale). GUI/tests Ruff lint/format, Win32
mypy (184 files), boundaries (zero violations) and diff whitespace pass. An earlier
full-suite attempt without the offscreen platform opened real windows on the rig
desktop and stalled; it was stopped (along with a concurrent agent's test run) and is
not evidence. Native viewer checks remain in the [rig checklist](rig-verification.md).

Oct21 `gui-test-batching`: `tests/gui/conftest.py` now selects offscreen Qt unless
`QT_QPA_PLATFORM` is set, owns the shared themed `app` fixture and gives GUI tests a
120 s pytest-timeout (2.4.0); pytest-xdist (3.8.0) enables workers. On the working tree
with concurrent edits: serial was stopped by the timeout at an order-dependent modal
Trial preview error in `test_trial_preview_is_read_only_has_enabled_screens_and_cleans_up`
(passes alone); `-n 8` 800 pass/2 fail in 85 s; `-n auto` (32 workers) 799/3 in 42 s,
against 385 s for the earlier serial run. Remaining failures are listed under
`gui-dashboard-test-restoration`; timings are local wall-clock, not rig workload data.
Follow-up: the serial modal did not reproduce. Replaying the 458 preceding tests and
a full serial run with message boxes intercepted both pass the target; the first hang
coincided with a concurrent GUI refactor, so its cause is unproven. An autouse
`unexpected_modals` guard now records unpatched static message boxes, returns
NoButton and fails the test at teardown. Serial 818 pass/1 fail (482 s) and `-n 8`
819/1 (80 s); the failure is ManagedConfiguration.stale, outside this work.

Oct20 `experiment-gui-recovery-hud`: G01rev261/G02rev89 unlock all configuration
draft editors after confirmed Ended cleanup, retaining current authority/version
gates and New session before submission. Failed/cancelled Setup returning to
Configuration keeps normal editing; unconfirmed cleanup never becomes permission
to reuse devices. Preview pending was listening only to command_finished, while
SetStimulusPreview uses operation_finished. Both now clear pending and immediately
reproject the retained snapshot, including failure/rejection. Visibility still
comes from renderer evidence. A compact preview HUD reuses Dashboard values;
total time now derives bounded planned schedule progress from accepted programs,
current trial timing and gaps. It excludes preparation/finalization overhead,
leaves unresolved timing unknown and freezes interrupted gap progress. Preview
readouts/ticks use hh:mm:ss and speed-unit labels are rotated/centered.
The preview grid now propagates changing frame minimum heights to its splitter.
ARCH-002: existing presentation/transport owners and canonical expansion reused,
no dependencies or backend lifecycle changes; main.py's added signal wiring stays
with GUI composition rather than creating another state owner.

Initial focused checks exposed insufficient preview height after adding the HUD
and a legacy future-trace assertion already indexed in TODO. Compact HUD/minimum
propagation repairs the geometry; timeline coverage now checks successive history
instants instead of nonexistent future traces. 73 focused offscreen cases pass;
an additional total-time check covers unknown/frozen interrupted gaps. Full GUI
mypy (184 files), Ruff check/format (187 files) and boundary checks (740 modules,
zero violations) pass. Final focused selection again passes73 cases; subsequent
narrow-clock spacing checks pass21 cases. Full GUI suite remains unrun.
[Preview evidence](runtime-evidence-2026-10-20/gui-recovery-hud/context.json)
is synthetic/offscreen, not native viewer or experiment acceptance.

Error-prevention assessment: reviewed retained Oct20 emergency reports through
498120295051300. Catalogue capacity, late GPU registration and missing registration
intent already have source repairs described above/below and in the
[Visual Stimulus report](visual_stimulus.md). They require a freshly loaded runtime
and bounded playback/cancellation/reuse acceptance, not a claim of eliminated
recurrence. Latest MCU PING latency and exact failed cleanup remain unresolved.
Use existing write/read timing to distinguish host scheduling from serial/USB/MCU
latency under preparation load; preserve deadlines/watchdog instead of masking a
miss with retries or longer safety limits. Use the new exact cleanup rejection
diagnostics to fix the owning identity/resource path, then repeat failed Setup,
cancel, fresh Setup and preview hide/show under load. No new device commands,
firmware changes or automatic runtime restart were performed in this increment.
The outstanding execution procedure remains in the [rig checklist](rig-verification.md).

Oct20 owner log since498119757265100: Setup7319b6b3 failed during resolving settings
and recording outputs after PING timeout139.316ms/99.978ms,2 reads,151 bytes with53
late and98 partial, longest read47.048ms; no malformed/unmatched replies. Attempt
retirement and cleanup failure follow. This establishes incomplete timely acknowledgement,
not whether delay is MCU/USB/driver or host scheduling. A11 deadline/retry/watchdog
rules unchanged. Serial diagnostics now separate write and total read durations.
Supervisor cleanup rejection preserves exact catalogue validation reason or output
mismatch/closure detail (including paired/finalized/absence flags), instead of hiding
all failures behind a generic message. Validation behavior is unchanged; resource
release diagnostics identify the failed key, revision/fence/identity mismatches retain
expected/reported facts. Existing focused owners reused under ARCH-002.
166 supervisor/shared-resource tests and145 serial tests pass,1 skipped; Ruff/format,
Win32 mypy3 and boundaries740/zero pass. No device command, firmware or timing-policy
change. Root serial delay and actual cleanup rejection remain unconfirmed until next
instrumented run; prior successful Ready/Start does not close these intermittent issues.

Oct20 `setup-watchdog-cleanup`, catalogue follow-up: owner log confirms manual
Behavior camera Live/disconnect and Setup reaching remaining backends; Visual
Stimulus then fails INVALID_CATALOGUE. Supervisor incorrectly reused its 256-entry
history bound for resource obligations. E08 rev177 separates that count from the
existing quarter-message byte budget (4 MiB at default transport settings).
Every obligation and exact cleanup check remains; diagnostic errors include counts
and bytes. A 2,049-resource regression exposed an additional fixed 64 KiB registration
reply reservation; admission now reserves the exact reply before ownership mutation.
ARCH-002 keeps both corrections in existing owners, without dependencies or new
configuration. The changed modules remain below the cohesion warning threshold;
unrelated existing size warnings remain. Supervisor/shared-resource suite:166 passed.
Ruff passes; formatting corrected after initial check; Win32 mypy25 files passes;
boundary checker740 modules/zero violations. Final registration, replay, cleanup and
over-budget rejection are covered locally. Whole-session rig success and previous
serial timing/partial cleanup questions remain open; restart must reload supervisor.

Oct20 `setup-watchdog-cleanup` follow-up: authenticated read-only snapshot from
controller e69fb44b-e37b-4710-91cf-3b1ebe0eb4af shows Setup
a80a66dd-a2ff-4517-934d-038c351ab076 failed at Preparing cameras, revision2, with
MICROCONTROLLER PING timeout, stale-readback and attempt-retired warnings. Current
phase has returned to Configuration and ReleaseManualCameraState succeeded. Cleanup
repair therefore does not establish serial recovery. Recovery also retains an
unconfirmed SpikeGLX-stop warning. No client control claim or device commands issued.
Source review found PySerial read_until performs byte-at-a-time native reads. Adapter
now reads at most the buffered byte count (bounded by requested size), or waits for
one byte when empty. SerialChannel retains line framing, request IDs, cancellation
and the100ms deadline under A11. ARCH-002 reuses the focused transport owner; no new
state/dependency/policy.215 serial/protocol/readback tests pass,1 skipped; Ruff/format2,
Win32 mypy1 and boundaries740/zero pass. Local two-trial Visual Stimulus validation
took0.448s with a47.8ms maximum observer-thread pause; this suggests load sensitivity
but does not prove the missed PING's cause. Subsequent controller435acc9b-e1fa-425f-
8ca4-d9c9dd78cb23 still reports PING timeout and failed Setup2547c399-d55e-4523-8fc8-
4d57a43ca406; buffered reads did not resolve the observed failure. Retained
[snapshot](runtime-evidence-2026-10-20/setup-watchdog/snapshot.json) confirms Configuration
and successful manual-state release. Readback now retains the original closure reason
on cancellation (E06), separating revision/deadline rejection. Serial ChannelTimeout
adds per-exchange elapsed/budget/read/byte/late-byte/partial/unmatched/malformed metrics;
no raw serial payload or extra runtime file, timeout relaxation or acceptance changes.
ARCH-002 keeps transient counters in the existing exchange and messages at their owner.
216 serial/protocol/readback tests pass,1 skipped; Ruff/format4, Win32 mypy2 and
boundaries740/zero pass. Initial serial cause remains unresolved; diagnostic runtime
restart and one Setup reproduction are pending. No firmware or device commands issued.

Oct20 `projector-missing-profile`: changing Protocol Assets to Pedro/media left
the saved display's four reference profiles in the previous media root. Restored
the exact referenced Front/Left/Right/Bottom files from C:/Data/projects/
reiter-cephalopod-vr/cephvr-assets/media into Desktop/Pedro/media/calibration;
GeometricProfile parsing, filename SHA256 and destination-byte checks pass for all4.
No calibration values changed. Unreadable source profiles now raise actionable
ValueError through the existing configuration-warning path (G01/E07), preserving
validation rather than regenerating unknown mappings. ARCH-002 keeps error handling
in the focused measured-profile owner. Existing affine-profile coverage checks missing
sources without recreation:6 cases pass. First attempt failed on Windows path length
inside the verbose evidence directory; shorter reports/tmp-profile basetemp passes.
Ruff/format2, Win32 mypy1 and boundaries740/zero pass, existing size advisories remain.
No Setup or native GUI restart performed; file restoration is immediately available.

Oct20 `trial-delete-final-gap`: removing the final scheduled trial retained its
predecessor's gap, causing Setup rejection even for a zero-second string. G01rev260
clears only the newly final gap on confirmed deletion; Cancel and intervening gaps
remain unchanged. ARCH-002 keeps the two-line repair in the existing deletion owner;
the ProtocolEditor size advisory does not justify extracting this state mutation.
Extended owning deletion coverage for zero and positive gaps plus apply_schedule:
both fail before repair; final four deletion/row-action cases pass. An intermediate
run exposed a missing test session-mode prerequisite, corrected without relaxing
validation. Ruff/format2, Win32 mypy1 and boundaries740/zero pass. Validated and saved
Desktop/Pedro/primate_cuttlebase_20min.json from parts1 of the original:600s each,
1200s total, two trials, zero inter-trial duration and no final gap. Portable parser
and GUI apply_schedule pass; no Setup or native restart performed. Original retained.

Oct20 `preview-timeline-toggle`: [G01rev259](../docs/architecture/gui.md#g01)
adds an always-available Stimulus timeline checkbox above the preview grid. Defaults
on; existing local GUI preferences retain its choice. QSplitter hides the entire
timeline card and reallocates its space to PreviewSlot's existing adaptive grid;
source frame identities and Show requests remain unchanged. ARCH-002 keeps this
in the cohesive PreviewDialog owner (under250 lines), with no dependency, backend
command or additional layout state. Six workspace/visibility/preference cases and
16 standalone timeline checks pass. A broader selector also hits the unchanged
Dashboard timeline test's future-segment expectation at elapsed0 (IndexError);
this is consistent with the outstanding centered-history test reconciliation,
not a complete GUI-suite pass. Initial preference fixture failed because its
temporary parent directory was absent; creating that directory fixed the fixture.
Ruff/check and format2, Win32 mypy1 and boundaries740/zero pass, with unrelated size
advisories. GUI not restarted; native viewer follow remains in
[rig verification](rig-verification.md). [Validation record](runtime-evidence-2026-10-20/preview-timeline-toggle/verification.json).

Oct20 `trial-delete-visible`: owner could not see/click the trial-row deletion action.
[G01](../docs/architecture/gui.md#g01) rev258 keeps the existing viewport-local ×
visible on the selected row when no row is hovered; hovering another row still
retargets it. Existing confirmation, saved-file preservation, pending edits and
configuration/authority locks are unchanged. The owner's follow-up screenshot exposed
a second cause missed by visibility-only checks: long names make visualItemRect wider
than the viewport, placing the visible widget wholly off-screen. The action now clamps
its right edge to the viewport. ARCH-002 retains the cohesive TrialList owner with no
new dependency/state/module; existing source-size advisories are unrelated.
The owning test now uses long names in both themes and asserts viewport containment,
nonempty visible region and clickable confirmation. Both variants failed before the
geometry fix; final focused deletion/layout/lock tests pass5 cases (774 deselected).
Ruff check/format, Win32 mypy1 and boundaries740/zero pass. No live trial was deleted
and no native acceptance is claimed; restart the GUI to load the change.
Earlier checks: [evidence](runtime-evidence-2026-10-20/trial-delete-visible/verification.json).

Oct20 `post-stop-session-editing`: [G01rev256](../docs/architecture/gui.md#g01)
unlocks Session config drafts in Ended after authoritative cleanup confirmation,
synchronized configuration and operator control. Existing E05 NewSession preserves
the draft into Configuration; subsequent Setup applies it. Completed metadata and
general device/protocol editing gates are unchanged.18 focused offscreen Dashboard
cases pass, including cleanup/authority loss and subject draft retention. Ruff/check
and format5, Win32 mypy4 and boundaries740/zero pass. ARCH-002 keeps the predicate
in the existing presentation record; oversized main.py changes only its existing
NewSession feedback string, adding no responsibility or dependency. GUI relaunch
was requested but the launcher declined because the exact old GUI was not released;
desktop inspection then timed out waiting for app approval. Current window has not
loaded the fix. Native reopen/post-stop acceptance remains in
[rig verification](rig-verification.md); no experiment was run for this change.

Oct20 `species-session-prefix`: [E04rev93](../docs/architecture/supervisor.md#e04)
and [E12rev25](../docs/architecture/synchronization.md#e12) derive the session folder
label from species initials plus subject: Sepia pharaonis/0001 -> `SP0001-HHMMSS`.
Existing exact-basename preparation/Start readback supplies the same SpikeGLX prefix.
Raw subject/species, trial-file names and historical folders remain unchanged;
absent/incomplete species retains the old label, existing matching prefixes are not
duplicated, and safe-component validation precedes prefixing. Existing metadata
path helper owns the derivation; no new schema/state/dependency or oversized module.
104 owning storage/Setup/SpikeGLX cases pass, Ruff/format and Win32 mypy pass,
boundary740/zero. Confirmed ended/clean runtime reloads through normal Shutdown and
exact launcher-exit receipt. Fresh Configuration retains operator settings and saved
bytes exactly; subject label resolves toSP0001, remote acquisition remains running
with saving OFF. No new paired recording or historical rename during this check.
[Commands, hashes and reload evidence](runtime-evidence-2026-10-20/species-session-prefix/verification.json).

Oct20 `camera-session-demand`: [A01rev20](../docs/architecture/acquisition.md#a01)
filters unused cameras from the prepared session while preserving operator selections
on readback. [E05rev96](../docs/architecture/experiment.md#e05) retains independent
Trial state participation with exact pulse-only lifecycle evidence.1499 acquisition/
controller tests pass (4 skipped,8 deselected), Win32 mypy304 and boundaries740/zero
pass. No managed restart or hardware operation by this change; native acceptance
remains in [rig verification](rig-verification.md). Detailed source review, failure
attempts and commands live in [Acquisition](acquisition.md) and its
[dated evidence](runtime-evidence-2026-10-20/sdk-transport-counters/verification.json).

Oct20 `trial-state-runtime-output`: [A11rev51](../docs/architecture/acquisition.md#a11)
adds the selected held-HIGH trial marker to the existing MCU serial owner, typed
boundary evidence and controller Started/Stopped checks. Setup retains requested
pin/enablement, previews omit the marker, and stop/abort/watchdog/claim release
include LOW proof. [Acquisition assessment and verification](acquisition.md)
own the complete evidence. Owner-authorized Oct20 managed upload now verifies
COM8 protocol6 after data-preserving recovery. Independent SpikeGLX samples verify
continuous HIGH for60.00231s and LOW after normal end and early Abort; original
configuration/saved bytes restored. Broader rig acceptance remains open.

Oct20 `subject-id-species-controls`: G01rev255/G02rev88 restrict new GUI Subject ID
entry/Setup to exactly4 ASCII digits, retaining leading zeros as text. Species is a
native noneditable dropdown of Sepia Pharaonis, Sepia Latimanus and Sepioteuthis
lessoniana. Unset optional species remains absent. Loaded legacy IDs/species are
retained without truncation or historical-output changes; an unlisted species is
visible as a disabled legacy item and requires replacement before Setup. Updated
managed metadata, full-GUI and review-draft codecs keep the existing text schema.
Condition recent suggestions remain; species free-text suggestions are removed.
24 owning offscreen tests pass/738 deselected, Ruff/format5, Win32 mypy4 and
boundaries739/zero pass. Existing size warnings remain; affected modules are focused
and below500 lines, with no new module/dependency/runtime reference. Subject card
renders in both themes; dropdown and Retro layout visually verified.
A test-edit encoding failure temporarily truncated the owning test module. Recovery
from tracked base plus recorded test edits matched the exact prior tested SHA256
before UTF-8 new edits; concurrent preview/pairing changes are preserved. No managed
GUI restart or device action; reopen GUI to see controls.
[Current verification and render evidence](runtime-evidence-2026-10-20/subject-id-species/verification.json).


Oct20 `recordings-save-spikeglx`: [G01rev253](../docs/architecture/gui.md#g01)
moves the existing E12 pairing checkbox into Dashboard Recordings as **Save spikeglx**.
One widget/state preserves current confirmed configuration, revision-checked On/Off
updates, pending/phase/control locks and existing saved On/Off choices. Devices
retains connection and channel mapping. No new backend flag, command, dependency
or native action; checkbox changes configuration only, and E12 still controls saving
at protocol Start/end/Abort. GUI reload is required for the open application.
9 focused offscreen GUI cases pass/744 deselected, including both saved values and
On/Off confirmation/queue rejection/authority locks. Ruff/format4, Win32 mypy3 and
boundaries739/zero pass. Existing size warnings remain; Window's cohesive assembly
only passes the existing checkbox, with no new runtime back-reference. Initial
broader native GUI selection stalled and was interrupted; targeted offscreen retry
passes. No live GUI restart/device operation or scientific acceptance claimed.
[Verification and both-theme renders](runtime-evidence-2026-10-20/recordings-save-spikeglx/verification.json).


Oct20 `spikeglx-continuous-acquisition`: owner-approved [E12rev24/E09rev5](../docs/architecture/synchronization.md)
replaces acquisition start/stop with saving-only control (policy6). Setup requires an
already-running, non-saving acquisition and performs no mutation. Start verifies the
captured identity/settings, assigns the exact session-folder basename and enables
saving, then retains the existing per-stream writing gate. End/Abort disables only
saving against the original Stopped deadline/margin and fresh expected identity;
no startRun/stopRun calls remain. A changed/already-saving recording is not adopted.
Saving intent survives unknown enable outcomes; a naming timeout alone cannot
justify disabling someone else's saving. Unchanged shared SDK ownership retains
in-flight calls and absolute bounds. SESSION_CONFIG's `spikeglx_control_scope` marks
saving-only semantics; historical acquisition-control evidence stays historical.
Recovery warnings direct the operator to inspect/disable saving without acquisition
stop. No new dependency/process/optional lifecycle mode introduced (ARCH-002).

Native tests pass on the same operator-started acquisition:60s normal completion
`SAVEVERIFY-085520`,12s Abort `SAVEVERIFY-085641`, and Setup cancellation. Saving is
OFF and acquisition running before/after each operation. Setup retains the previous
name; Start changes it. OneBox sample counts advance continuously from4,267,515 to
7,545,750 across operations, with no observed reset. Remote directory listing proves
native `.bin`/`.meta` pairs with exact session basenames and native_g1_t0/_g2_t0
suffixes. Both local trials have all9 outputs Closed;6 camera accounting logs are
complete with zero dropped/invalid frames;8 videos fully decode and match frame
counts/identities. Software renderer max gaps57.94/22.74ms; no gap>100ms or capture
drop in these runs. Control timestamps/counters do not establish pulse alignment.

155 focused controller/recovery/authenticated RPC tests pass,4 deselected; Ruff and
format17 files pass, Win32 mypy16 pass, boundaries739/zero. Existing size warnings
remain; interruption's583-line cohesive failure/cleanup module changes only its
docstring, other affected lifecycle/SDK responsibilities remain focused. No unrelated
refactor or dependency added. Test harness corrected a post-Start monitor-snapshot
race and resumed the successfully running normal protocol; no runtime failure was
hidden. Initial restart hit the existing-runtime guard, then normal interactive
launch succeeded without terminating unrelated processes.

Original runtime configuration and saved file bytes restored exactly; CephVR is
Configuration/cleanup-confirmed, SpikeGLX remains acquiring with saving OFF as
requested. Ephys contents were not transferred/validated; pulse alignment, native
fault/recovery and endurance acceptance remain in the [single rig worklist](rig-verification.md).
[Dated raw session copies, commands, hashes and native checks](runtime-evidence-2026-10-20/spikeglx-continuous-acquisition/verification.json).


Oct19 `gui-full-rig-test`: authenticated controller execution completed one600s
Gaussian trial with all3 camera recordings, four projector outputs, stimulus review
and paired SpikeGLX; scientific Tracking remained disabled. All9 planned outputs
Closed and the exact13-file local data set, resource fingerprints, source/video
associations and four full decodes pass. Native ephys filenames were checked through
the SDK; original ephys contents and electrical/optical alignment remain unverified.
Original runtime configuration and saved file bytes were restored; final state is
Configuration with all3 cameras closed, previews stopped and no cleanup pending.

Measured264 valid samples cover trial seconds40.07–598.92; a startup GPU-counter
instance error left the initial interval unmeasured. Sampled mean/p95/max host CPU
is19.05/23.64/31.18%; NVIDIA UUID-mapped5060Ti GPU10.88/11/11%,2080Ti GPU31.09/32/32%
and NVENC58.84/59/60%; AMD operator adapter busiest engine5.59/6.67/10.03%.
2080Ti Windows3D engine82.03% mean is a separate engine measurement; VideoEncode
59.62% agrees with NVENC. Max temperatures52/47°C and mean power36/65W are for
5060Ti/2080Ti respectively. Process CPU is normalized to32 logical CPUs; host
aggregate does not rule out one saturated core. These are sampled utilization,
not quantitative headroom or full scientific-workload acceptance. Near-black
Eye/Tracking source content limits encoder-load representativeness.

Native desktop state capture failed twice (507.8s and186.4s after reset), returning
no screenshot or input. Actual per-control/DPI acceptance remains open. Separately,
48 offscreen layout states and7932 repeated control rows were inventoried; all751
GUI tests pass. Two source defects were corrected: camera inventory now creates
recording controls before participation callbacks, and preview geometry retains
the top-right corner. Stale G02 assertions and incomplete fixtures were corrected.
Owning controller/Tracking/acquisition-transport selection:805 passed,4 skipped,
7 deselected. GUI and affected backend Ruff/format/Win32 mypy pass; boundaries737,
zero violations (existing size advisories). The diagnostic repair and native reuse
are detailed in [Tracking](tracking.md); no critical architectural choice was needed.
The subsequent owner-requested Sol review also exposed a pre-resource diagnostic
failure-bookkeeping gap; Astra confirmed the narrow repair and116 Tracking tests pass.
Its [supplemental verification](runtime-evidence-2026-10-19/gui-full-rig/preallocation-verification.json)
identifies the later source separately from the completed native workload.
Oct20 `brightness-supervised-helper`: the owner approved repairing the direct native
launch found by the follow-up Sol/Astra review and adding experiment evidence.
[E08rev176](../docs/architecture/system-contracts.md#e08),
[G01rev251](../docs/architecture/gui.md#g01) and [E04rev92](../docs/architecture/supervisor.md#e04)
now govern the implemented dedicated brightness role, registered suspended creation,
original deadline, exact native cleanup and truthful manual/authority cleanup gates.
The helper preserves hidden-console behavior, existing SDK commands and explicit
clamping; no physical current or calibration was changed. A small shared release
function preserves firmware behavior without another service or dependency (ARCH-002).
Latest admitted evidence is frozen in SESSION_CONFIG with a matching SCHEMA descriptor;
unknown, failed, partial and clamped outcomes cannot masquerade as a current requested
value. Rejected commands retain prior evidence; pre-entry cancellation clears stale
readbacks. Human GUI progress omits the structured machine-result line.

Three final production-adapter probes pass with actual Windows children/jobs/pipes,
no console, exact exit/empty-job checks and bounded success/cancellation/timeout.
Supervisor receipts and SDK results in those probes are simulated. Five actual
Start/writer fixtures pass, with20 retained metadata files independently hash-checked
and parsed; no session/device execution is implied. Initial sandbox pipe denials,
probe DLL lookup and path/expectation failures remain explicitly contextualized in
the [native/output verification](runtime-evidence-2026-10-20/brightness-helper/native-validation-context.md).
Physical SDK/USB/readback and live adjustment acceptance remain in the single rig
checklist. Astra accepts the final focused ownership/metadata changes. Final owning
selection255 passed/1 skipped; strengthened authority regression4 passed. Ruff,
format184 files, Win32 mypy142 source files, boundaries739/zero, PowerShell syntax,
19 Protobuf compilations and whitespace pass. Two broader runs each passed893 but
hit separate unrelated short-timing/concurrently edited fixtures; both pass in
isolation, and no clean broad-suite pass is claimed. Four stale supervisor fixture
calls were corrected to forward the existing original deadline; baseline-source
comparison confirms the mismatch predates this work. Exact commands, source hashes,
failures and validation limits are in [brightness verification](runtime-evidence-2026-10-20/brightness-helper/verification.json).
[Evidence/commands/limits](runtime-evidence-2026-10-19/gui-full-rig/verification.json),
[telemetry](runtime-evidence-2026-10-19/gui-full-rig/telemetry-summary.json),
[GUI context](runtime-evidence-2026-10-19/gui-full-rig/gui-offscreen-context.md),
[remaining rig checks](rig-verification.md).

Oct19 `spikeglx-session-name-pairing`: [E12rev23](../docs/architecture/synchronization.md#e12)
now uses the exact reserved session-folder basename for the native run base. Native
paired60s normal completion and12s Abort/reuse pass with all3 camera videos and4
projectors, Tracking processing disabled. Both starts confirm saving and increasing
OneBox0 counts before the trial; confirmation follows session_started by1.28s.
Both remote stops, cleanup and NewSession succeed. Final read-only SDK check confirms
idle; original DUMMY_2 runtime configuration and matching prior saved bytes restored.
Actual remote SDK directory listing confirms `.bin`/`.meta` pairs named
`PAIRVERIFY-170744_g0_t0.obx0.obx` and `PAIRVERIFY-170856_g0_t0.obx0.obx`.
Native suffixes remain SpikeGLX-owned; files stay on the ephys computer under E09.

Native checks found and fixed premature prepared-function registration before local
catalogues existed and a missing Setup check for manual recording initially OFF.
The latter caused running=true/saving=false throughout5s and15s failed gates; the
owner corrected SpikeGLX settings, and the original5s writing bound now passes.
Unknown override values reject Setup; acquisition settings remain operator-owned.
The initial complete SDK read exceeded1s; native-call budget is5s, with unchanged
finalization bounds and explicit timeout diagnostics retaining native ownership.
The source mapping pins installed v20251218/API4.1.3 at official commit
83ae3e9e1f8cfe16f52905609f5bd420c651dae1 (14 source files/hash provenance), without
weakening version rejection. Owner-supplied OneBox0 analog Trial0/photo1/Behavior2/
Tracking3/Eye4 maps validate as saved channels; physical reception remains unmeasured.

All18 local outputs Closed;6 camera accounting logs complete with zero dropped or
invalid frames;8 videos fully decode with matching frame counts and identities.
Renderer maximum gaps are62.57ms/21.52ms with no gap over100ms, no capture drop,
omission or duplicate in either run; these are software observations, not photodiode
measurements. Focused controller100 and authenticated RPC3 tests pass; Ruff/format6,
Win32 mypy14 and boundaries737/zero pass. Existing unrelated size warnings remain;
affected focused modules stay below500 lines, no dependency or runtime back-reference
added (ARCH-002). Initial failed attempts/harness corrections are retained as failures.
[Dated commands, native raw copies, hashes and verification](runtime-evidence-2026-10-19/spikeglx-pairing/verification.json).
Remaining pulse alignment/native content transfer and fault/endurance acceptance stay
in the [single rig worklist](rig-verification.md); this bounded pass does not close them.


Oct19 `camera-finalization-stimulus-timing-check`: native investigation reproduced
Abort cleanup failure and isolated camera SDK accounting using the250ms activity
budget instead of the original Finished budget. A10rev69 correction passes1002
focused acquisition/controller/renderer tests and native two-Abort/reuse plus60s
normal recording with all3 camera videos. All outputs Closed, complete camera
accounting,12 successful full video decodes and0.36s Abort-to-session-end replace
the reproduced40s failures for this tested scope. Owner-authorized Desktop dummy
Abort, NewSession and orderly shutdown also succeed. Final runtime is Configuration
with cleanup confirmed; runtime configuration and saved file bytes restored exactly.
Photometric calibration is owner-confirmed working. See
[Acquisition](acquisition.md) and [Visual Stimulus](visual_stimulus.md) for exact
cadence, startup review omission and remaining E15 limits.
[Dated source hashes, raw evidence and verification](runtime-evidence-2026-10-19/camera-timing-verification/verification.json).


Oct19 `dashboard-preview-workspace` / `dashboard-preview-controls` /
`dashboard-preview-motion-plots`, updated Oct20 by `preview-centered-speed`:
[G01](../docs/architecture/gui.md#g01) rev254 and [G02](../docs/architecture/gui.md#g02)
rev87 provide a 1440×960 default external workspace with Show beside each stream's
frame heading, status below and no separate selector card. Dashboard camera slots
require both experiment participation and video recording selected; Eye/Tracking
camera recording Off cannot open a viewer. Recording changes send no device commands;
already-open viewers retain a Hide control until closed. Devices diagnostics keep
their independent eligibility. The grid chooses up to three columns for the largest
fitted squares; native ownership and reported visibility remain authoritative.
(Historical: the speed timeline and polar plot below were replaced on Oct21 by the
epoch timeline and Advanced previews dials described at the top of this report.)
A vertical splitter separates streams from a wide planned-speed timeline and a
compact polar local-direction plot, surrounded by a signed angular-speed CW/CCW ring.
The motion card now expands vertically rather than inheriting Card's Maximum policy:
the initial split is about58% streams/42% plots and remains user-adjustable. Stream
headings/frame tops align on resize; compact headers can be wider than their native
square to keep names/Show legible. The legend sits above the speed graph, and a larger
polar dial has aligned source/direction/rotation columns with compact-width labels.
Standard, Retro and800×800 five-stream fixtures were visually inspected. The first
layout check caught stale header alignment after resize; recomputing common heading
height against the updated grid fixes it without new scheduling or state ownership.
The speed plot and epoch strip share a30s sliding range centered on current time,
including startup. History stops at the exact evaluated velocity at the center;
future speed is blank, contiguous epoch steps connect, and the vertical time bar is
removed. Absolute nonnegative5s ticks and epoch blocks use the same range. A200ms
Qt timer advances planned time between reports only in Running/Stopping, clamps to
the trial end and stops advancing on disconnection/non-running reports. Hidden plots
skip refresh work. Click inspection is clamped to trial bounds until the next refresh.
The polar display places 0° down, 90° right, 180° up and 270° left. The
`preview-polar-zero-down` follow-up passed six focused motion tests, offscreen pixel
checks of all four arrows, Ruff/format, Win32 mypy and boundaries737/zero; existing
unrelated cohesion warnings remain. [Zero-down render](runtime-evidence-2026-10-19/dashboard-preview/polar-zero-down.png)
supersedes the polar axis convention in earlier workspace screenshots. No live GUI restart.
Epoch labels occupy a separate strip; rounded five/ten-multiple ticks and zero padding
keep stationary intervals visible. Colored projector legend toggles replace the dropdown:
sources overlay the same speed/polar plots, with matching direction/rotation colors.
Fully linked projectors expose only their reference; independent projectors remain
alongside it. Source grouping spans projector/layer occurrences across epochs rather
than instance IDs; static unlinked baselines no longer expose otherwise linked followers.
The baseline cause is reproduced in a fixture, not verified against the screenshot's
unprovided program. Independently moving epochs still expose their projector, with gaps
while linked. Mixed units have separately labeled axes; unsupported sources report limits
without hiding valid traces. The shared planned instant synchronizes both plots.
Rotation remains visible without translation; absent
translation has no direction arrow. Canonical bounded expansion/function evaluation
supplies values; unresolved timing/order, feedback and unsupported motion remain
explicitly unavailable. No new RPC, dependency, device operation or recording.
ARCH-002 separates footprint/header painting into `preview_frame.py` before extending
placement; plot painting lives in `preview_motion_plot.py`, with canonical program
evaluation/source grouping extracted to `preview_motion_data.py` before extending the
timeline controls. No new dependency or whole-runtime reference;
unchanged oversized modules retain their existing cohesion warnings.63 focused offscreen GUI
tests pass, including both themes, 800×800 containment, initial placement hints,
stable frames, inline controls, recording changes, Eye and Tracking exclusion,
pending/observer gates, close/reopen, page retargeting, reference filtering, polar
direction, signed rotation, stationary translation, shared click cursor, tick ranges,
all-linked baselines, independent overlays, mixed units, toggles and isolated unsupported
sources, expanding plot space and aligned stream tops. Ruff/format6, Win32 mypy5,
boundaries739/zero and scoped whitespace pass. Follow-up
layout tests exposed five-stream small-window overflow from the polar minimum size;
corrected and rechecked. The earlier broad preview run was interrupted; no full GUI-suite pass.
Offscreen screenshots are fixtures, with no connected devices; actual Windows
viewer/DPI/full-workload acceptance remains in the [rig checklist](rig-verification.md).
No running application was restarted by this chat.
[Centered-speed evidence and render](runtime-evidence-2026-10-20/preview-centered-speed/verification.json):
16 standalone offscreen timeline tests pass (initial fractional-endpoint precision
failure fixed), Ruff/format4 and Win32 mypy3 pass, boundaries739/zero and whitespace
pass. An actual Qt event-loop probe delivered6 callbacks in1250ms at approximately
200ms intervals; this is local scheduling evidence, not a loaded-rig guarantee.
The final offscreen render confirms centered history and no time bar. ARCH-002
review retains the focused data/painter/timeline split and changes only Window's
existing playback call. No affected source exceeds500lines; unrelated cohesion
advisories remain. The standalone test module owns clock/painter behavior with a
small QApplication fixture instead of the large Dashboard/device fixture. Existing
`tests/gui/test_dashboard.py` was already zero bytes during this work and remains
untouched; restoring its concurrent changes and reconciling old trailing-window
assertions is still required before claiming a full GUI-suite pass.
[Current layout verification](runtime-evidence-2026-10-20/preview-layout-polish/verification.json);
[overlay verification](runtime-evidence-2026-10-20/preview-source-overlay/verification.json);
[earlier motion-plot verification](runtime-evidence-2026-10-19/dashboard-preview/motion-verification.json);
[inline-control verification](runtime-evidence-2026-10-19/dashboard-preview/inline-verification.json);
[initial workspace evidence](runtime-evidence-2026-10-19/dashboard-preview/verification.json).

Oct19 `pre-experiment-output-audit`: inspected the four retained sessions in
Desktop/20261019_gui_backend_dummy without changing their files. All seven planned
outputs per session exist; central configuration/schema/trial/session logs parse,
and output keys match reservations. All trials are Interrupted, not completed
50-minute experiment acceptance. Two newest sessions have all Closed outputs;
earlier Unconfirmed/Failed camera closures and an observed649ms stimulus-state gap
remain distinct blockers in [Acquisition](acquisition.md) and
[Visual Stimulus](visual_stimulus.md). Existing task deferrals remain in force.
[Audit method, hashes, full video decodes and limitations](runtime-evidence-2026-10-19/output-audit/assessment.json).
Current source revision is recorded with a dirty/concurrent-checkout caveat; the
recorded runtime build revision is unknown. No automatic repair, recovery, deletion,
configuration change or experiment/device execution was performed.


Oct19 `recovery-result-feedback`: under [G02](../docs/architecture/gui.md#g02)
rev82, explicit startup recovery/deletion emits one final action-log message after
the exact command completes successfully: "Unfinished session files deleted." or
"Recovery completed; existing files preserved." Admission or a running action is
not completion. Failed, unconfirmed and needs-input outcomes retain existing detail;
ordinary prompt successes remain quiet. The bridge reuses its existing action
signal after awaiting the authoritative result, avoiding retained-snapshot/reconnect
success replay. ARCH-002 keeps this in the focused managed-action callback path;
no new state, resource, RPC or dependency. Existing bridge orchestration remains
cohesive.23 focused GUI/action-log cases and1 authenticated loopback prompt case
pass, including both recovery choices, delayed completion, failure/uncertainty and
ordinary prompt suppression. Ruff/format4, Win32 mypy2, boundaries734/zero and
whitespace pass. Reopen the GUI to load this change; no live recovery/deletion or
desktop acceptance was performed. Session files were untouched.

Oct19 `preview-window-restore`: Dashboard Previews now clears only the minimized
window-state flag before raising/activating its existing workspace. Qt reports a
minimized window as visible, so the old visibility-only path never restored it.
G01 ownership/optional viewer behavior is unchanged; native owner handle, maximized
state and stream selections remain intact without issuing visibility commands.
Two pre-fix minimized cases fail;7 focused offscreen tests pass, covering Configuration
and Running, normal/maximized restore, geometry persistence and native-owner close.
Ruff/format2, Win32 mypy1 and boundaries734/zero pass. ARCH-002 keeps the fix in
the cohesive existing dialog; no new dependency/state or staged-feature promotion.
Initial geometry test hit sandbox temp permissions; rerun passed with writable temp.
No live experiment restart or Windows taskbar/physical viewer acceptance performed.

Oct19 `stimulus-composite-preview`: Dashboard Visual stimulus is now a managed row
with exact session/configuration/backend status, lease-authorized Show/Hide and
retained executor completion. Native close changes visibility without changing trial
state; older status updates cannot overwrite newer observations. G01/V01 own this
optional renderer window; E13 owns cropped display preview versus uncropped rotated
recording. The label-free layout3 follow-up stitches matching post-rotation rasters
edge-to-edge;435 Visual Stimulus tests and one standalone GL test pass.571 scoped backend/client and82 preview GUI tests pass; full-suite camera
failures remain outside this increment. See the
[current Visual Stimulus assessment](visual_stimulus.md) and
[commands/limits](runtime-evidence-2026-10-19/stimulus-composite-preview/verification.json).
No running app was restarted here; fresh native/full-workload checks remain in the
[rig checklist](rig-verification.md). Controller service/assembly and GUI main retain
wiring only; preview state/control lives in focused helpers (ARCH-002).

Oct19 Abort late-report rejection: exact interrupted-session terminal status now
retains under E06 without satisfying original deadline or output-closure gates.
346 focused acquisition/controller tests pass; DUMMY_2-152638 recordings/config
unchanged. Exact original RPC/lateness cause unavailable; native acceptance pending.
See [acquisition assessment](acquisition.md).

Oct19 `mcu-test-button-layout`: MCU input/output Test columns now size to content
rather than100px, allowing Retro bracketed Test/Stop/Cancel labels and table cell
padding. G01 test gates/dispatch and G02 shared styling unchanged. Five focused
offscreen tests pass, including both styles, action-label sizing, row containment
and existing fixed-signal/pending-cancel behavior. Scoped Ruff/format, Win32 mypy1
and boundaries730/zero pass. ARCH-002 retains the small existing table owner; no
new state/module/dependency, oversized-module advisories outside changed source.
No hardware action, saved configuration change, restart or native visual pass.

Oct19 `projector-brightness-layout`: Adjust aligns with the input bottom instead
of the combined label/field center; hide native spin-button chrome, retaining typed
and keyboard-step input. G01 brightness command/authority/value semantics remain
unchanged; G02 shared styling applies. Five focused offscreen tests pass (Standard/
Retro at320/580px plus authority/pending behavior), scoped Ruff/format, Win32 mypy1
and boundaries729/zero pass. ARCH-002 changes only the small existing brightness
card; existing size advisories elsewhere need no extraction for this edit. No
hardware command, configuration mutation, app restart or native visual pass.

Oct19 `interrupted-finished-abort-proof`: A10rev68 now yields/resumes terminal
camera drain across control/Cleanup arrivals instead of flushing unfinished SDK
buffers and producing rejected Interrupted output evidence.748 acquisition/controller
lifecycle tests and final26 interleaving/purge/preview cases pass; original cutoffs,
deadlines, sync/closure and exact-output guards remain intact. Reopen the managed
application to load the repair. Fresh native Abort/file-close/reuse timing is pending;
historical saved files remain unchanged. [Acquisition assessment/evidence](acquisition.md).

Oct19 `action-progress-logging`: [G02](../docs/architecture/gui.md#g02) rev81
replaces routine admission/success-result rows with dispatched actions, changed
controller progress and observed ongoing states across camera/MCU, Setup,
stimulus/tracking preparation, SpikeGLX, trial recording, stop/Abort, recovery and
shutdown. Failures/rejections/cancellations/unknown outcomes retain their details;
E04 audit and retained operation history are preserved. Polls and unchanged
snapshots stay quiet. Camera Live requires frame evidence; session Idle requires
confirmed cleanup. Intermediate telemetry/snapshots may coalesce; no fabricated
asset/model stages or progress timers are introduced.

ARCH-002: the new focused GUI projection receives snapshots and a log callback,
not a runtime reference. Existing operation records/transports are reused, with
no dependency or policy/configuration additions. Camera telemetry has one
background sender and one replaceable pending action so controller stalls cannot
delay hardware OFF; exact terminal device/release evidence remains mandatory.
Existing oversized entry-point/assembly, device dispatch and preview-lifecycle
owners receive only hooks or callback calls; their state/cleanup ownership remains
cohesive. Other boundary size advisories are outside this change.

Validation:380 affected acquisition/controller tests pass (1 skip/1 deselected),
62 focused managed GUI/device/logging tests pass (645 deselected), Ruff check and
format22, Win32 mypy18 and boundaries728/zero pass. The broader GUI run was
interrupted after unrelated preview geometry failures/stall; an isolated `-x`
rerun gives7 passes/1 failure in
`test_multiple_review_previews_have_independent_source_frames[standard-0]`
(native preview frame outside its slot). No clean baseline attribution or full
GUI-suite pass is claimed. No application restart or hardware/device acceptance;
see [rig verification](rig-verification.md) and
[verification record](runtime-evidence-2026-10-19/action-progress-logging/verification.json).

Oct19 `projector-brightness-adjust`: [G01](../docs/architecture/gui.md#g01)
rev243 adds Devices/Projectors RGB LED current (101–2500 mA) and Adjust for all
USB-detected TI projectors, independently of display assignment/Use. Managed GUI
submits authenticated, retained controller commands; Configuration, control lease,
revision and manual-operation gates prevent session changes or overlapping SDK work.
Review logs intent only. No automatic application or draft/calibration persistence.
The helper follows the owner's `Desktop/set-projector-brightness` SDK reference,
using installed TI DLP EVM GUI 3.2.0.6 DLLs through 32-bit PowerShell. Equal RGB
currents, LED enable, interface identities/readback and explicit 1023 clamping are
retained in the device log. No-interface, partial, mismatch, SDK/release and timeout
failures remain failures; no rollback/retry. See the [contract](../contracts/projector-brightness.md).

ARCH-002 review: focused GUI card, controller operation and Windows SDK helper;
no added Python dependency, SDK redistribution or whole-runtime back-reference.
Existing assembly/service/runtime and GUI main/projectors size advisories were
reviewed: those edits only assemble, gate or dispatch the new focused responsibility.
Reuse the existing manual-operation slot/retention; the projector discriminator
allows authority-loss cleanup to await helper exit without requiring camera evidence.
The necessary child process bridges the installed 32-bit SDK; timeout kills/reaps it.

Validation:74 client/manual-device/SDK-boundary tests and18 focused Qt-offscreen
projector/layout tests pass. Coverage includes authentication/control, range/revision/
phase rejection, identical-ID replay, pending-operation exclusion, partial failure,
readback, subprocess timeout/reaping, authority-loss waiting and review/GUI gates.
Scoped Ruff check/format16, Win32 mypy12, PowerShell parser, backend boundaries727/
zero violations, wheel build (helper included) and whitespace pass. Generated19
Protobuf sources through the repository generator. Initial sandbox temp failures
and asyncio stalls required permitted loopback/build runs; broader GUI selection
stalled at native-dialog scope and was stopped. One test initially tried to create
an operator command without control; fixture corrected. An initial import-order/
encoding issue and a GUI local-variable type conflict were corrected. Concurrent
logging edits made an import unused and rewrote CRLF files; scoped checks were
rerun after preserving their behavior and substantive SDK readback logging.
No actual SDK execution, hardware brightness mutation, live restart or optical pass.
[Verification summary](runtime-evidence-2026-10-19/projector-brightness/verification.json).
Outstanding native checks remain in the [single rig checklist](rig-verification.md).

Oct19 `gui-dialog-style`: under [G02](../docs/architecture/gui.md#g02) rev80,
the dashboard owner applies the complete selected stylesheet before its chrome,
so warning/confirmation dialogs and owned tool windows inherit both colors and
fonts. Existing windows update on style selection; newly created dialogs inherit
immediately. ARCH-002 uses existing Qt inheritance and theme definitions, with no
window registry, event filter, dependency or backend/configuration changes.
G01 native file pickers and OS title bars retain platform appearance; image/stimulus
pixels are unchanged.43 focused appearance/style/theme, retained-review, prompt and
file-picker tests pass with Qt offscreen, including live standard/retro round trips
and dialogs created after selection. Scoped Ruff/format, Win32 mypy1 and boundaries
725/zero pass; size warnings remain outside the changed source. Initial sandbox
suite stalled and was interrupted; permitted loopback rerun passed. Running GUI
not restarted and desktop visual acceptance not performed.

Oct19 `startup-recovery-actions`: the owner revised the reboot requirement under
[E04](../docs/architecture/supervisor.md#e04) rev91. Startup retains **Start recovery**
and **Cancel and delete files**, with Close submitting neither. When the exact prior
launcher receipt is missing, both explicit choices can proceed under the held
exclusive session lock without rebooting Windows. The prompt discloses unconfirmed
prior process absence; recovery reports retain
`old_process_absence: unconfirmed_exclusive_session_lock`, alongside unconfirmed
scientific closure. Existing valid launcher receipts remain exit proof; present
invalid/mismatched receipts still block. A missing receipt never authorizes automatic
namespace settlement, pointer clearing or normal-file repair without the choice.

Removed the boot-GUID API, boot-witness storage helper and their tests. The previously
recorded private witness is inert historical evidence; no live recovery state was
changed by this revision. ARCH-002 reuses exact prompt/control/work admission,
namespace ownership and scoped deletion; no new state, dependency or process.
Tree preflight, marker identity/fingerprint, link/reparse rejection, bounds,
quarantine and ownership retention during timed-out deletion remain intact.
Deletion permanently removes only the explicitly displayed local session, including
local imported SpikeGLX files. Live locks, wrong identities and partial/uncertain
completion keep the blocker. Remote files remain outside scope.

Final recovery/Setup/shared/client run:76 passed,1 skipped, including native
junction/quarantine and both missing-receipt choices without reboot. Live-lock
rejection preserves files/pointer; recovery reports do not claim exit proof.
Scoped Ruff/format and Win32 mypy pass; boundaries728/zero and whitespace pass.
Existing cohesive size advisories reviewed; this revision reduces recovery/store
code. [Current verification](runtime-evidence-2026-10-19/startup-recovery-block/no-reboot-verification.json).
Earlier test/reboot-witness results are historical in the same evidence directory.
No GUI reopening, live recovery/deletion or subsequent Setup pass; reopen the
application to load this revision. The retained DUMMY-142302 scientific files and
reservation/pointer were not changed. Live prompt/reuse acceptance remains in the
[single rig checklist](rig-verification.md). [Original incident evidence](runtime-evidence-2026-10-19/startup-recovery-block/assessment.json).

Oct19 Bottom direction correction aligns GUI-generated calibration and rig preview
with the owner-confirmed folded portrait orientation under G01rev242/V15rev21.
Saved measurements/flips/crops and scientific motion remain retained; fresh GUI
restart/Setup is needed. See [Visual Stimulus assessment](visual_stimulus.md) for
validation and the outstanding physical/VSync comparison.

Oct19 Stop now investigation: acquisition owner wake-consumption defect repaired;
invalid interrupted output batches now carry their rejected claims in the existing
error response.228 focused tests pass, exact native incident attribution and live
cleanup acceptance remain pending. Controller closure guards and user configuration
are unchanged. See [acquisition assessment](acquisition.md).

Oct19 `camera-connect-selected-all`: under [G01](../docs/architecture/gui.md#g01)
rev241, removed Test selected from the shared camera inventory. The two actions are
Connect selected / Disconnect selected and Connect all / Disconnect all. Bulk
Connect uses enabled camera identities, skips already-open cameras and serializes
the existing prepare/SDK/Start/Show path, using each confirmed configuration revision
and current preview placement. No new backend RPC, capture owner, timeout or policy.
The selected label reflects that selected camera's confirmed open/cleanup state;
the bulk label reflects the enabled set (or pending cleanup), without optimistic
connection status. Disabled connected cameras remain outside the bulk selection.

Batch state freezes key/serial/role, locks camera settings, stops on changed selection,
authority/connection loss or failed/cancelled Connect, and preserves prior successes.
The initiating bulk button owns the existing Cancel token. Disconnect all attempts
remaining releases after one camera fails; logs retain each outcome, with no false
aggregate success. Review emits the same enabled-only preview intents locally.
ARCH-002 keeps UI construction/control gating in the existing646-line CamerasPanel
and sequential intents in the focused ManagedCameras binding; the size warnings were
reviewed as cohesive presentation/projection/command ownership, without additional
resources or a second transport layer to extract. Removed the selected identity-test
UI branch; existing headless identity checks and behavioral coverage remain.

Validation: initial focused49 pass; camera/layout selection134 pass, including720/
1280px shared layouts; final17 bulk/Review cases pass after frozen-identity guards.
Cases cover partial connection, disabled cameras, completion labels, failure/cancel,
queue refusal, authority loss, changed role, selection changes during an active call,
fresh per-camera revisions and disconnect failure continuation. Ruff/format3,
Win32 mypy2, boundaries724/zero and whitespace pass. Initial lint saw an unrelated
in-progress test's missing json import; its owning concurrent edit supplied it and
final lint passes. An initial multi-hunk test patch did not match and made no change;
the focused retry succeeded. No live GUI restart, camera command or native bulk
acceptance. Reopen the GUI to load this UI/binding change; remaining physical checks
stay in the [single rig checklist](rig-verification.md#managed-device-gui).

Oct19 `synchronization-validator`: fixed the screenshot's
`synchronization: VALIDATOR_UNAVAILABLE` rejection. Startup discovery expected
`cephvr.synchronization.configuration`, which was missing. The new pure provider
validates the existing empty SynchronizationSettings envelope and rejects duplicate
backend entries or foreign settings. Under [E07](../docs/architecture/experiment.md#e07)
and [E12](../docs/architecture/synchronization.md#e12), pairing uses the backend
enabled flag; absent or explicitly empty typed settings are valid. Host endpoint,
inventory, SDK, saved-channel and native preparation checks remain with Setup.
This is configuration validity, not paired readiness or recorded-pulse evidence.

ARCH-002 review uses the existing provider discovery, with no new dependency,
state, policy, process or whole-runtime reference. The focused 39-line owner module
avoids expanding startup orchestration; existing size advisories are unrelated.
Regression cases extend the existing SpikeGLX and configuration transaction modules,
covering discovery without host files, enabled pairing, subsequent paired edits,
wrong settings, duplicates and candidate immutability. Using the repository Python:
`-m pytest tests/controller -q -m "not windows and not rig"` passes646,
4 skipped/5 deselected; focused three-module run passes104/1 skipped. Both use
explicit writable `--basetemp` paths outside the software root. Initial sandbox
attempts failed temp creation or hung in asyncio's local socket-pair initialization;
those processes were interrupted, and the permitted unsandboxed reruns pass.
Ruff check/format for affected files, `-m mypy --platform win32
src/cephvr/synchronization` (12 sources), backend boundaries (724/zero) and
`git diff --check` pass. Full application restart and GUI retry remain unverified;
no live connection, recording command or physical channel assignment was performed.

Oct19 `epoch-display-index`: timeline epoch cards and detail headings now derive
numbers from current sequence positions instead of persistent epoch IDs. Removing
first/middle/last epochs closes numbering gaps; restoring prior program state restores
numbers. Internal IDs and batch names remain unchanged. Twelve focused timeline
cases pass, including nested repeated groups. Scoped Ruff/format, Win32 mypy2 and
boundaries724/zero pass. G01 presentation repair; ARCH-002 reuses existing paint/index
state with no helper/dependency or configuration mutation. Native GUI not restarted;
change takes effect on next GUI reopen. Final shared-test format check sees concurrent
camera-bulk edits; this change was formatted before those edits, production files clean.


Oct19 `preview-zoom-pan`: native camera viewers support left-button image dragging
after wheel zoom, clamped to image edges. Release ends pan; wheel/reset/resize cancel
the gesture, and double-click restores fit. A10rev67 keeps it in the existing private
viewport and shared HighGUI callback, independent of window dragging and scientific
pixels.144 owning preview tests pass, including native drag and cached-image repaint
without new source frames; static checks pass. Full application restart is needed;
real-camera interaction remains unverified. [Current evidence/limits](acquisition.md).

Oct19 `preview-linked-fullscreen`: owner approved full-screen physical image-tile
textures in runtime and preview (V14 revision5); G01 revision240 binds preview links
through the runtime resolver with boundary/pivot validation. Whole-tile symmetric
extension covers calibrated surfaces under rotation/translation without stretching
periods or shifting phase; saved dimensions/configuration are not rewritten. GUI
brush Y anchoring now matches bottom-origin phase. Preview backward seeks replay
linked bindings; missing geometry rejects before playback.20 focused preview/coverage
cases and108 rendering/compilation cases pass. Saved actual protocol coverage passes
all four screens at six seeks with a white diagnostic tile; configuration byte equality
verified. Initial evidence script used strict Python validation on JSON lists; rerun
through model_validate_json succeeds. Ruff/format, Win32 mypy6 and boundaries724/zero
pass. ARCH-002 reuses the focused layer projection and canonical link helpers; no
new dependency or ownership. Existing scene orchestration remains cohesive.
Native inspection unavailable (Computer Use: foreground window did not report a
process id); GUI/runtime restart and physical output verification remain pending.
No live process restart, scientific config edits or staged promotion performed by
this change; concurrent work preserved. Evidence:
`runtime-evidence-2026-10-19/linked-fullscreen/verification.json`.


Oct19 `preview-click-and-first-show`: owner reports real-camera preview windows
becoming unresponsive on click and visibly moving/resizing after opening. Source
review identifies a plausible focus deadlock: per-viewer HighGUI threads share
OpenCV's window locks while Win32 activation synchronously crosses window threads.
No stack of the stalled live process was collected, so that attribution remains a
source inference. Acquisition viewers now marshal their native/window steps onto
one process-local HighGUI owner; independent ring-event waits remain off that thread,
with one pending step per reader and no queued frame history. Cleanup, viewport
mouse callbacks, owner retargeting and placement run on the same UI thread.

Under [A10](../docs/architecture/acquisition.md#a10) rev66 /
[G01](../docs/architecture/gui.md#g01) rev239, a thread-local exact-title/class creation
hook suppresses HighGUI's eager ShowWindow until initial sizing, physical placement,
blank caption and GUI-owner binding complete. Reveal does not activate the viewer.
Review uses the same native staging helper on its existing GUI thread. Later layout,
manual placement opt-out, Snap, minimize and exact X/cleanup ownership remain intact.
ARCH-002 separates the small process-local UI dispatcher and focused native creation
mechanism from the existing viewer; no new process, dependency, policy option or
whole-runtime reference. Existing owning behavior modules are extended.

Native generated-image testing checks three actual Win32 windows: each remains
hidden until its256x256 image area and requested400/700/1000,100 frame origin are set;
five rounds of activation/click/WM_NULL messages per window respond within1000ms.
Shared HWND owner identity, latest-frame read, wheel zoom, double-click reset, X,
other-viewer survival and exact mapping closure pass. All169 relevant acquisition /
Windows tests and79 offscreen GUI preview/Review tests pass; scoped Ruff/format,
Win32 mypy6 sources, boundaries and whitespace pass. Existing size warnings concern
other cohesive modules. The first native run exposed an obsolete per-thread-name
test assertion, corrected to shared-owner/per-image assertions before reruns.
No live camera operation, running-app restart or physical click/drag/DPI150/performance
acceptance. Full application restart is required to replace acquisition's loaded
viewer code; real-camera follow-up remains in the [single rig checklist](rig-verification.md#managed-device-gui).
[Dated commands/hashes/scope](runtime-evidence-2026-10-19/preview-click-first-show/verification.json).

Oct19 `mcu-output-card-spacing`: owner promoted every staged Microcontroller and
Projector Synchronization control under [G01](../docs/architecture/gui.md#g01).
Runtime and Review now construct the same Inputs, inline Outputs and per-screen
Frame/Pulse editors. I/O cards precede the expanding spacer. Shared portable/full
files retain unfinished definitions, legacy Review extensions and per-screen pulses;
physical bindings remain separate, and rebinding preserves configured pulse levels.
Input authoring retains existing authority/phase/operation gates; physical input
capture and diagnostics remain deferred under A11. Runtime placement retains the
authenticated diagnostic path; Review uses its local fixture.
[V20/V22](../docs/architecture/visual_stimulus.md#v20) now support explicit per-output
pulse maps, requested VSync, bounds/availability checks and per-output submission
evidence, preserving legacy single-output profiles. See [local evidence](runtime-evidence-2026-10-19/shared-controls/context.json)
and the [single native/optical worklist](rig-verification.md). Source/layout and local
checks do not establish electrical, native driver or optical acceptance.
Current GUI collection has669 passing cases across continuation batches; final
Visual Stimulus427/1 deselected, contracts42/82 subtests, Win32 mypy335, scoped
format/lint, schema11/no drift, local document/register, TOML semantic equality
and whitespace checks pass. Historical failures and the explicitly combined
coverage receipt remain beside the source hashes. ARCH-002 review of existing
large Microcontroller/Projectors panels and renderer engine/scene keeps orchestration
with their owners; new input/pulse/file responsibilities use focused helpers and
obsolete pin-menu/dialog code is removed. Boundaries724/zero; no dependency added.

Oct19 `camera-device-revision-ack`: screenshot shows Connect rejected locally with
"Camera configuration changed; reload before retrying." Source confirms successful
camera enable/role/settings and MCU pin/output edits lacked the existing accepted
device-revision callback used by pairing and prepared actions. With a restored or
unsent draft, their streamed new revision therefore marked the GUI stale and blocked
subsequent camera submission. Extend the existing success-only acknowledgement to
those five owning actions under [G01](../docs/architecture/gui.md#g01)/E07. Preserve
generation/base-revision matching, unrelated conflict/rejection fences and unsent
page contents. No automatic reload/rebase or backend configuration rule changes.
ARCH-002 keeps the change in the focused dispatcher and extends the owning Dashboard
test module, with no dependency or new abstraction. Ten regressions cover each action,
stream-before-ack ordering, Connect options, unsent subject preservation and rejected
updates; focused11 and related54 tests pass. Ruff/format, scoped Win32 mypy,
boundaries723/zero violations and whitespace pass. Existing backend size warnings
are unrelated to the GUI dispatcher change. No native GUI restart, camera operation,
file/configuration write or rig acceptance in this increment. Current stale window
can use Control / Reload controller configuration after preserving unsent edits;
source prevention loads on GUI reopen. Concurrent staged-control work is preserved.

Oct19 `mcu-upload-recovery`: owner's GUI upload reports verification failure, but
independent COM8 flash readback matches all13874 application bytes of the new build.
Live CAPS confirms protocol5 / `cephvr2_uno_5`; all camera outputs are stopped and
disabled. No repeat flash needed to install this image. Original GUI operation stays
failed; its sync-error cause is unestablished, with future reproduction tracked.
[Native evidence and limits](acquisition.md). No production code or runtime restart.

Oct19 `mcu-failed-connect-upload`: failed acquisition MCU startup now releases its
exact claim through confirmed CLOSE, making explicit Upload available after a
protocol mismatch. Active-camera and uncertain-cleanup guards stay in force under
[A11](../docs/architecture/acquisition.md#a11).270 relevant regression tests pass;
source repair needs a whole-application restart to replace the existing stale claim.
No board flashed or live process changed. [Evidence/limits](acquisition.md).

Oct19 `preview-screen-coverage`: PreviewRig now maps the calibrated valid-area
rectangle, rather than the full projector raster, onto the physical screen polygon.
This removes duplicate black projector margins; polygon clipping prevents unused
raster pixels spilling outside the screen. Existing flips, content composition and
final overlays are retained. G01 behavior repair; ARCH-002 uses existing correction
state in the focused painter without new dependencies.15 focused preview/geometry
tests pass, including all four faces, portrait Bottom, offset crop, both-axis flips
and outside-screen clipping. Scoped Ruff/format, Win32 mypy and boundaries724/zero
pass. Saved configuration remains byte-identical; no config writes or staged promotion.
Native restart/inspection was unavailable: Computer Use activation and fresh-inventory
state recovery both failed with "foreground window did not report a process id".
Running GUI left untouched; source fix loads on next GUI reopen. No native or optical
pass claimed. Evidence: `runtime-evidence-2026-10-19/preview-coverage/`.

Oct19 `preview-bottom-plane`: Trial Preview retains the physical screen corners
used by the rig geometry plot independently of calibrated image extents. Portrait
Bottom calibration previously replaced the floor dimensions, making its long edge
appear across the tank. G01 physical placement now remains front-to-back; existing
image calibration/state are unchanged. Seven focused preview/geometry tests pass,
including portrait calibration versus exact rig corners. Scoped Ruff/format, Win32
mypy and boundaries (724 modules, zero violations) pass. ARCH-002 keeps the two
coordinate meanings in the focused snapshot; no new dependency or runtime ownership.
GUI saved configuration compares equal before/after close; backup is in
`reports/runtime-evidence-2026-10-19/bottom-preview/`. GUI reopen command succeeded;
post-reload native inspection blocked by repeated Computer Use activation error
"foreground window did not report a process id". No optical acceptance claimed.
Staged features stay separate.

Oct19 `recipe-trial-preview`: corrected PreviewMedia interpreting texture recipe JSON
as an encoded image. Dispatch by declared profile now reuses the renderer recipe
parser/generator, bounded to1024 squared pixels and the existing JSON byte limit,
with owned QImage storage and linear-to-sRGB display conversion. Thumbnail paths
are not substituted. Linear/sRGB procedural recipes supported; image dependencies,
geometry-dependent calibration recipes and BT709 override preview remain outside
this increment. Six focused preview cases pass, all9 current saved recipe assets
generate successfully. Ruff/format, scoped win32 mypy and boundaries pass.
Native GUI reopened with saved configuration; Static and Drifting screens now show
textures, next epoch and Play/Pause work. Left paused at29.41s. No projector output
or optical equivalence claimed; staged features remain separate. G01 revision237.
ARCH-002 retains this bounded asset-load responsibility in the existing media owner.
Source review also found PreviewPlan lacks linked-motion resolution: followers keep
independent hold state in planning preview. This is an open fidelity defect, not
closed by recipe rendering; tracked in TODO. Actual runtime linked motion is separate.
Backups/evidence: `reports/runtime-evidence-2026-10-19/recipe-preview/`.

Oct19 `camera-connect-continuity` updates the MCU host and firmware source to
protocol5 under A10/A11, with policy4. CONFIGURE readback preserves the expected
running mask, while acquisition Connect no longer pauses unrelated captures.
Older firmware is rejected at CAPS; no board was flashed and no live application
was restarted by this task. Local owner, native-sketch and AVR build evidence and
remaining rig limits are in [Acquisition](acquisition.md); deployment is explicitly
deferred by the owner. Existing settings-edit stopping remains unchanged.

Oct19 `gui-restart-paste-native`: GUI reopened through the existing launcher's
`--reopen-gui` path with latest shared fixes. Original GUI was blocked by the pending
Front asset; selecting the same recipe through its picker allowed that current draft
to commit and save. Both original disk snapshot and saved current draft are retained.
The saved draft includes the pending replacement's new Front instance/recipe tile
size104mm; the older disk snapshot had20mm. Unsaved pre-picker pose/size is unavailable,
so exact preservation is measured against the successfully saved current draft.
Native Ctrl+C/Ctrl+V in Static Front followed by Drifting selection passes; copying
that path into Drifting Left then selecting Static passes with no warning. Ellipsis
opens Advanced settings directly. A final save equals the pre-test saved draft
exactly, and reopening restores it. Controller generation, configuration revision
and values remain equal; all4 pre-existing calibration window identities remain.
GUI left open on Protocol, in Configuration. No Setup/Start or rendering/recording
acceptance claimed; pending-family/invalid-path cases retain prior local test evidence.
Staged features remain separate. [Verification/backups](runtime-evidence-2026-10-19/gui-restart-paste/verification.json).

Oct19 `pasted-asset-pending`: reproduced the screenshot's missing-asset error with
Ctrl+V after a stimulus-family change. Successful pasted-path commits now clear the
owning instance's pending-asset flag in the shared composer, like picker selection.
Invalid/empty drafts remain blocked; the warning no longer incorrectly refers only
to adding epochs. Existing G01 pasted-path and atomic-edit behavior is unchanged.
Regression failed with the exact original error before the fix;7 focused offscreen
GUI tests pass afterward, including invalid-path recovery and picker parity.
Ruff/format, scoped win32 mypy and boundaries pass (0 violations; existing cohesion
warnings). ARCH-002 review keeps this in the existing commit owner, without new
state/dependencies. Staged features and live draft untouched. No live restart or
hardware test; the current process can use its file picker until restarted.

Oct19 `protocol-layer-menu`: shared Runtime/Review Layer dropdown now contains
layer choices and Add/Remove/Move up/down actions, including on empty/single-layer
rows. Ellipsis directly toggles Advanced settings; its state follows the card.
Texture initial position/orientation controls are removed while saved pose values
remain unchanged. Arena, Video and Looming pose controls remain available.
Owner-requested behavior recorded in [G01](../docs/architecture/gui.md#g01) revision236.
18 focused offscreen GUI tests pass (layer selection/actions, ordering/local values,
advanced cards and hidden-state preservation); Ruff/format and scoped win32 mypy
pass; boundaries report0 violations. ARCH-002 review keeps the dropdown in its
focused row owner and removes dead texture-caption handling; the540-line parameter
binder receives only a narrowed existing condition, with no added responsibility.
Staged features remain separate. No live GUI restart or hardware acceptance was run.

Oct19 `linked-texture-variation-diagnostic`: reproduced the reported failure from
the captured recipe-setup configuration: Direction variation still targeted linked
followers. Shared Runtime/Review validation now names the conflicting variation and
reference screen to target; no rule is silently removed or retargeted. Also repaired
subgroup merge retaining sampled follower motion when its template was stationary:
linking now replaces phase/motion atomically, preserving unrelated fields under
[G01](../docs/architecture/gui.md#g01) and
[V02](../docs/architecture/visual_stimulus.md#v02). No architecture or staged-scope change.
27 focused offscreen GUI tests pass;3 regression cases pass again after the final
merge guard refinement. Ruff, scoped Windows mypy and boundaries pass (0 violations,
existing unrelated size warnings). ARCH-002 review retained existing focused owners
and added no dependencies. Initial test runs hit sandbox temp creation (8 fixture
errors) and demo assets requiring an external directory (2 fixture errors); the
external writable basetemp resolved both. No native Setup/rendering rerun or live
GUI restart; saved draft untouched. New code loads on the next GUI restart.

Oct19 owner-selected GaussianNoise recipe replacement is complete:8 PNG asset
references now use the matching `.texture.json` and `cephvr1_texture_json_v1` profile.
Program/recipe parsing and exact candidate-diff assertions pass. Native Setup command
`be321de5-cf00-4a23-9276-fc1c4211ff0c` succeeds; session
`0813eb4e-fbbf-48e9-8642-ee975a7287fe` reaches Ready. Prior failed reservation required
administrative recovery preserving scientific files/unknown evidence. No trial was
started. Both saved configurations verify8 recipe references; corrected protocol was
also loaded into the open GUI, left on Ready. Other settings/staged scope are unchanged.
This supersedes the pending color-choice note below; recipe pixels need not match the
old PNG preview. [Raw evidence](runtime-evidence-2026-10-19/recipe-setup/verification.json).

Oct19 `preview-connect-setup-diagnostics`: internal-clock camera Connect no longer
pauses/reconfigures already-running external-camera previews. Its external-mask
stop/cleanup/restart path is superseded by the source-only continuity change above;
the earlier native evidence did not test continuous pulses. GUI pending
reconnects retain grid footprints without claiming live/visible state, and surviving
footprint widgets are reused on reflow. This reduces collapse/rebuild churn; continuous
native-window display during an external MCU change is not claimed or rig-verified.
Configuration rejection now includes unavailable provider code/component/reason.
The missing `cephvr.synchronization.configuration` provider originally rejected
pairing at the validator gate; `synchronization-validator` above fixes that software
prerequisite. The saved host pulse inventory was empty and runtime GUI indices were
blank at that inspection. Paired native acceptance and exact saved-channel mapping
remain separate E12 work.
Inventory reads recheck Configuration/Ready at dispatch and translate the exact server
phase-race rejection to a deferred-refresh explanation, preserving unrelated RPC errors.
The PNG color diagnostic now names asset/path and override fields. Saved GaussianNoise
PNG references have no override; the sibling `.texture.json` identifies the PNG as its
preview. Selecting the recipe is supported for the intended recipe stimulus; this may
regenerate noise and was not silently substituted. Owner color-intent question remains
pending. No saved settings or staged features were changed.

Validation:293 passed,1 skipped,567 deselected across affected acquisition/controller/
media suites and focused GUI preview/inventory checks; Win32 mypy8 sources clean,
boundaries724/zero violations. ARCH-002 changes stay in focused existing owners, with
no new dependencies or oversized-source extensions. Native smoothness remains to be
checked. [Dated assessment](runtime-evidence-2026-10-19/preview-connect-setup/assessment.json).

Oct19 `preview-windows-native-follow`: video-on testing reproduced a DPI defect:
automatic native scaling was mistaken for an operator move, permanently disabling
bracket layout. Repeated DPI-polling candidates failed on the rig and were discarded.
The final implementation observes Win32 move/resize completion on the preview's owning
thread. Runtime and Review share the geometry guard; Cocoa retains geometry inference.
This implements [G01](../docs/architecture/gui.md#g01); staged MCU I/O and multi-screen
pulse editing remain separate. ARCH-002 keeps the native event adapter focused with no
new dependency, process or policy. Manual movement still opts out until Snap/reopen.

Final 240-second three-camera/all-video session
`15f0a602-4a53-497a-9373-c6f0c68bffb3` completed with trial cleanup confirmed.
Workspace dragging at100% and all-three bracket alignment at125% pass during recording;
150% alignment was visually observed, but its later authenticated snapshot was already
terminal, so it is not a separate sustained runtime acceptance. Eye Snap at125% passed
in an intermediate trial. Native X and individual-child drag remain unverified: the
computer-use tool rejects cross-process input to blank-caption camera windows and does
not expose them as targetable windows. Requested manual assistance was not received.
Minimize/restore/notification dispatch pass in an isolated native HWND test, not actual
multi-camera operator acceptance. Returning to100% is confirmed in Windows Settings;
terminal UI warnings obscured preview alignment on that return, so no reverse-transition
alignment pass is claimed. All11 saved files restore byte-identically after process exit.

Source revision/hashes, trial metadata, full-decode verification, output hashes and
failed attempts are retained in
[dated evidence](runtime-evidence-2026-10-19/preview-video-native/assessment.json).
All4 videos fully decode without error and match closed receipt counts (Behavior7193,
Tracking14387, Eye14396, stimulus14231). All three camera completions retain every
received frame without duplication; stimulus
reports14231 states/admissions with zero capture drops or same-slot omissions. Tracking
processing is omitted; actual3-camera capture,4-projector rendering and4 encoders run at
saved quality/15 stimulus slots. This is bounded fixture evidence, not optical timing or
full workload certification. Normal Shutdown succeeds and all runtime processes exit;
stderr truthfully reports unconfirmed MCU claim release after controller departure,
covered by the existing `acquisition-shutdown-controller-rpc` limitation. Some SDK
transport counters are unavailable; unknown counters are not reported as zero.

Validation on final implementation: owner/acquisition148 passed (2 deselected), focused
Review5 passed, native owner/notification1 passed (18 deselected), Win32 mypy39 sources,
Ruff/format10 files pass; boundaries724 modules/zero violations. Earlier broad GUI plus
owner run had778 passes and5 fixture failures; Review mocks were corrected and those5
passed. That broad run predates the final event adapter and is not a fresh full-suite
pass. Sandbox loopback run was interrupted and replaced by permitted execution. Existing
unrelated cohesion warnings were reviewed; no affected source exceeds500 lines.

Oct19 `preview-rig-repair-oct19`: repaired preview failures under
[A10/A11](../docs/architecture/acquisition.md#a10), [G01](../docs/architecture/gui.md#g01)
and E06/E08. Staged MCU editing and multi-screen pulse controls remain separate.
Source: `5945f170` plus working changes. [Dated assessment](runtime-evidence-2026-10-19/preview-rig-repair/assessment.json)
indexes raw snapshots, logs, trial metadata, hashes and failed attempts.

- Concurrent external-camera Connect stops existing pulses before MCU reconfiguration,
  then restores viewer placement/visibility after usable frames. Final native
  Configuration checks preserve Behavior/Tracking and exact run IDs across workspace
  close/reopen and independent Hide/Show. Use off/on changes the local participation
  draft while connected capture remains; both Disconnects succeed before Setup.
  Cleanup pending now has a distinct HUD state.
- Workspace Close hides without destroying its owner HWND. Native CRT input
  transparency restores navigation after HighGUI creation. HighGUI destroys its child
  before owner release; only already-destroyed-child detachment errors are tolerated.
  Geometry-only updates no longer falsely demand visible state; resumed placement
  clears its update-only hint.
- Running Show/Hide uses existing session preview slots with exact identity/revision,
  enabled-camera and nonzero-preview-rate checks. Readers follow actual trial IDs;
  no capture/pulse owner is added. Command evidence remains until session cleanup.
  Cleanup closes readers before mappings and retires matching local status;
  proof-gated NewSession clears matching controller camera projections.
- Final 120-second session `dd609408-c775-4ed7-b5c9-aa52bb931173` completes with cleanup
  confirmed. Real clicks open all 3 viewers, close/reopen the workspace preserving Show,
  and hide/restore Behavior independently. Snapshots 17-19 retain the same capture/session
  identities. NewSession reports all cameras closed; fresh Setup/CancelSetup pass.
  Normal Shutdown/process absence and byte-identical restoration of 11 settings pass.
- Photodiode conversion supplies missing white/black RGB defaults and preserves explicit
  values. Local tests pass; the native trial used an accepted texture-only candidate,
  so full saved-draft GUI Setup is not claimed. Native extended paths repair camera
  frame-log and stimulus evidence/recipe creation. Actual >260-character filename
  cases pass; full long-root trial repetition remains outstanding.

Validation: GUI 636 passed; controller/camera/acquisition 150 passed, then 42 passed
with exact-session retirement regressions; preview/device/window/recording owner
selection 253 passed,2 deselected before that final addition. Win32 mypy 633 sources
passes; final GUI owner-lifetime/color/input checks 3 passed; boundaries 724 modules, zero violations. Ruff/format checks pass. ARCH-002
keeps session viewers in a focused allocation adapter; existing runtime composition
and cleanup proof-join size warnings remain cohesive. No new dependency or policy.

Earlier repair attempts are not passes: first runtime cleanup failed with WinError1400
and prematurely finalized commands; intermediate workspace tests destroyed the owner
HWND; the next completed trial exposed stale status on reuse. Evidence is retained.
Initial async-window timing hypotheses were superseded by owner destruction and CRT
input interception. An accidental visible GUI pytest run was interrupted and replaced
by the passing offscreen run. Corrected harness/mock mistakes are not product findings.

Limits: optional videos off, Tracking processing omitted. Native X/move/Snap/minimize/
DPI, multi-trial reader transitions, failure injection, tracking/stimulus viewer transport,
full long-root trial and optical/throughput acceptance remain in [rig checks](rig-verification.md).
Dark Eye/Tracking images prove viewer operation only. Post-trial reuse uses authenticated
Setup/CancelSetup; GUI reload/reconnect was not completed. Original audit history is
retained in [its click matrix](runtime-evidence-2026-10-19/preview-rig-clicks/click-matrix.json).

Oct19 `runtime-review-parity-oct19`: current checkout at `5945f17` imports the
shared GUI directly from `src`. Owner confirms G01's staged device controls stay
separate. Regenerated 19 contract sources after finding stale ignored control
bindings missing `update_existing_only` and `snap_to_grid`; the former caused a
reproduced runtime preview relayout AttributeError. Generated bindings now match
fresh output byte-for-byte. No generated source was hand-edited.

The existing cold-start parity test also reproduced different header and Session
config heights between Review and runtime. Register the bundled font before
constructing/sizing controls, and measure the header after applying appearance,
including style changes. This implements existing [G01/G02](../docs/architecture/gui.md)
parity rules. ARCH-002 review keeps font ownership in appearance and construction
in the shared shell; no dependency, state or page duplication is added.

Windows Python 3.11.15, Qt offscreen: existing page/authority/appearance/staged-device
and managed-preview selection **11 passed**; preview slot/log/snap/card selection
**25 passed**. GUI Ruff/format (180 files), Win32 mypy (178 sources) and backend
boundaries (723 modules, zero violations) pass. Existing backend cohesion warnings
remain outside these small GUI owners. Initial pytest temp-directory creation was
restricted; reran using repository-local basetemp. Initial parity/preview failures
above were resolved; a transient mypy loop-variable type error was corrected.
Process inventory was denied by the sandbox, so no running application was restarted
or certified. These are local composition checks, not live device, native placement
or full-suite acceptance; [rig checks](rig-verification.md) remain open.

Oct19 `dashboard-log-expand` ([G01](../docs/architecture/gui.md#g01) rev232):
Dashboard log now fills its available column height with external previews open.
Four-line compaction applies only to the status column hosting an in-page preview
grid (Cameras/Tracking); collapse-follow-latest and subsequent manual scrolling
remain unchanged. ARCH-002 uses the existing host identity, with no added state or
dependencies. Both-style preview/page-transition tests7pass and Dashboard height
tests2pass. Scoped Ruff/format, Win32 mypy and boundaries721/zero violations pass.
Offscreen test windows close automatically; only the final updated Review is left
open. This display-only change has no new Windows/rig acceptance evidence.

Oct19 `preview-snap-workspace` implements [G01](../docs/architecture/gui.md#g01)
rev231 and [A10](../docs/architecture/acquisition.md#a10) rev62. Centered Snap
buttons restore only their named existing preview and resume automatic placement.
Dashboard Previews now opens/raises a resizable external workspace containing the
source controls and native-window grid; Cameras retains its in-page grid. The owner
selected OpenCV over the grid, streams now and plots later. Closing/hiding the
workspace hides viewers while retaining logical Show/capture; reopening restores
them. Same-GUI-process native host changes preserve exact process identity, manual
opt-outs and reader ownership. Restoring refreshes only the automatic geometry
baseline so OS repositioning is not mistaken for a manual move.

ARCH-002 reuses the existing workspace, placement and display-thread owners; the
snap flag is display-only, coalesced without dropping an unconsumed explicit snap.
No new image transport, package or capture state. [Native method](runtime-evidence-2026-10-19/preview-snap/native-workspace.py)
and [result](runtime-evidence-2026-10-19/preview-snap/native-workspace.json) pass
snap/reset/no-reopen, three-source containment, move/hide/restore and return to
Cameras in actual local macOS Review. Every native test closes all its windows;
retained initial failures show the restore baseline issue and its correction.
Portable selections pass26 owner/display/workspace cases and18 snap/grid/placement
cases. A broader preview selection56pass/9fail used old in-page/toggle assumptions
and pre-caption mocks; after updates the affected cases pass as8cases plus the final
first-placement/tab case. Settling source-control height before measurement fixes
initial grid drift. Win32 mypy11sources (final2rechecked), scoped Ruff/format16files
and whitespace pass; boundaries721/zero violations.
Windows native/DPI and real streams remain pending in the existing native-follow
task. Concurrent device navigation, empty-frame styling and blank-caption changes
are preserved; local evidence is for the uncommitted combined working tree.

Oct19 `preview-four-line-log`: [G01](../docs/architecture/gui.md#g01) rev229/
[G02](../docs/architecture/gui.md#g02) rev78 remove the trial-position strip.
Open previews fix logs to four rendered lines and scroll to latest on collapse;
subsequent manual reading remains stable. Last close restores expansion. Initial
placement measures the same geometry without changing reading position. ARCH-002
reuses focused owners and removes the unused strip widget without dependencies.
Both-style four-line/rollback checks3pass; broader affected selection13pass and
four obsolete-strip assertion failures, corrected appearance cases4pass on rerun.
Ruff/format6files, Win32 mypy5sources and boundaries721/zero violations pass.
Offscreen tests close their windows; final local Review alone is opened for review.
Windows-native acceptance remains pending; concurrent navigation edits preserved.

Oct17 `merge-main-oct17` integrates local GUI595ab681 with recording/evidence
origin/main1314a743. Only LOG and this report conflicted; both records and
committed product sources/tests are preserved. Fresh acquisition selection passes
622/5 skipped/2 deselected; focused Dashboard preview/log/Retro/startup selection
passes55/549 deselected. Ruff/format386, Win32 mypy361 and boundaries719/zero
violations pass after regenerating stale ignored bindings from19 Protobuf sources.
Inherited cohesion advisories remain. Full offscreen Dashboard rerun stops after
107 passes at `test_camera_trigger_form_reflows_and_destroys_owned_editors`:
at298px the form is unstacked while the fixture expects stacked. Concurrent
`preview-card-visibility` edits appeared during validation, so these GUI results
are working-tree evidence rather than an isolated committed-tree certification.
An earlier combined run was interrupted after GUI failures and aborted in Qt
fixture construction; no full GUI or native/rig pass is claimed. Existing
`devices-narrow-overflow` tracks the reflow finding; cause remains unverified.

Oct19 `adaptive-preview-grid` implements [G01](../docs/architecture/gui.md#g01)
revision228. Both Dashboard and Cameras retain external resizable OpenCV windows.
Only open eligible sources occupy slots: one centered, two side by side, then
additional two-column rows. Untouched windows follow grid changes; any operator
move or resize preserves that geometry until close/reopen. Cameras still excludes
disabled cameras and non-camera streams. Height can constrain one and two previews
to the same square size even though their horizontal layout changes.

ARCH-002 uses a small shared geometry guard, platform-owned owner-relative frame
measurement and existing placement/command owners; no package, image transport or
whole-runtime references. Runtime serializes changed hints through existing command
authority and coalesces them on the display thread. Existing-only hints cannot
reopen an X-closed viewer. All affected source modules remain cohesive; boundary
size advisories are inherited and unchanged by this increment.

[Native method](runtime-evidence-2026-10-19/adaptive-previews/native.py) and
[result](runtime-evidence-2026-10-19/adaptive-previews/native.json) verify maximized
local Retro Review, one/two/three layouts, containment, centering, reflow on close,
manual move/resize preservation and reset on reopen. The first observation retained
in the same directory showed an obsolete Cocoa minimum-width allowance for the now
resizable windows; the corrected run centers the actual small frames. Its initial
strict one-greater-than-two assertion was too strong for a height-limited area and
was replaced by centering and one-versus-three resizing checks. Qt-only screenshot
inspection verifies the underlying shell; native frames are measured separately.
Final focused selection:37pass and one obsolete minimum-width assertion; its
replacement resizable-frame centering/narrow-fit case passes in isolation. Scoped
Ruff/format16files, Win32 mypy11sources and boundaries720/zero violations pass.
Portable owning tests cover one through six slots, update coalescing/copying,
authority/visibility gates, manual opt-out, no recreation, and cleanup. Windows
native/DPI and real camera acceptance remain pending in `preview-windows-native-follow`.

Oct17 `log-scroll-camera-preview-scope` refines
[G01](../docs/architecture/gui.md#g01) revision227 and
[G02](../docs/architecture/gui.md#g02) revision77. LogConsole already retained
native scrolling, but global zero-width scrollbar styling hid its control. A
log-specific named vertical bar now has a10px track/visible handle and AsNeeded
policy; short logs hide it. Shared Console/HUD behavior remains unchanged. Both
appearances retain reading anchors and follow-at-bottom semantics.

Cameras filters placement footprints and Preview/log visibility to enabled camera
keys from current drafts/readback, excluding disabled cameras even if connected
and excluding Tracking/Visual stimulus streams. Dashboard retains all source types. A10 diagnostic Connect remains independent
of experiment enablement: a source with no eligible slot uses the existing
monitor-constrained fallback instead of blocking capture admission.
The previous open-viewer membership freeze prevented changing page/eligibility;
removing that redundant restriction refreshes footprints for membership changes,
with the subsequent adaptive-grid rule above now also refreshing on Show/Hide.
ARCH-002 extends the existing focused console/theme/shell/placement owners with no
new module, dependency, transport or capture state.

Actual native Retro Cameras Review shows only the two enabled camera frames;
both native200×226px windows fit their200×230px targets without overlap. The
100-line log exposes a10px scrollbar with range89 and navigates from end to start.
Both previews minimize/restore together and independent close preserves the other
position. [Source/method](runtime-evidence-2026-10-17/review-synthetic-preview/camera-slots-log-native.py)
and [result/scope](runtime-evidence-2026-10-17/review-synthetic-preview/camera-slots-log-native.json)
record local macOS Review evidence; no real devices or Windows-native acceptance.
Four added page-scope/overflow cases span both styles and include pointer scrollbar
navigation, overflow hiding, preserved reading anchor, enable/disable while open,
stream-only/no-enabled-camera Cameras hiding/log expansion, disabled-camera
placement fallback and return to full Dashboard sources.
The focused preview/log/HUD selection passes34cases/581deselected.
The existing multi-preview cases now require two camera windows on Cameras and
three camera/stream windows on Dashboard. A generic camera test fixture was updated
to an actual enabled identity for the new filtering. Scoped Ruff/format5files,
Win32 mypy4sources, boundaries720/zero violations and whitespace pass. Existing
unrelated cohesion and narrow-layout limitations remain; the fresh Review is open.

Oct17 `log-error-color` implements [G02](../docs/architecture/gui.md#g02) revision76:
error log blocks and Retro prompts use the existing coral-red error palette token.
Command completion supplies explicit severity (failed/rejected/unconfirmed versus
completed/operator-input/cancelled); unstructured local messages use recognizable
error words, excluding negated wording. Explicit successful recovery stays normal
even when its message mentions an earlier failure. A syntax highlighter preserves
source text, entry-bound details and normal-row formatting after errors; appearance
switching refreshes colors. No runtime/error classification authority changes.

ARCH-002 review extracts Console/FittedConsole/LogConsole and bounded details from
the500-line component module into focused `consoles.py`, retaining component imports
as compatibility exports. `log_colors.py` owns classification/highlighting and is
shared with the Retro prompt painter; no new package, whole-runtime reference or
duplicate log history. Main only supplies existing outcome flags; its prior size
advisory remains an orchestration-cohesion review rather than another responsibility.
The owning Dashboard module retains its scenarios and adds10parameter cases:
log/appearance/HUD selection38pass, with604collected total versus594before this
increment. Coverage includes source-status severity, negative wording, no color
bleed, style changes, exact text/details, bounded history and scroll following.
Scoped Ruff/format, Win32 mypy5, boundaries718/zero violations and whitespace pass.
[Method/scope](runtime-evidence-2026-10-17/review-synthetic-preview/log-error-colors.json)
retains fixture provenance; the historical sample image is no longer present.
Fresh native Retro Review reopened maximized with
synthetic previews; no real device errors or Windows/rig acceptance are claimed.

Oct17 `preview-card-fit` implements [G01](../docs/architecture/gui.md#g01)
revision220: the shared placement helper selects the largest permitted initial
square fitting the visible Preview card/desktop intersection and centers the full
native frame within it. Title/border reservation and Cocoa minimum frame width are
included; insufficient visible room reports an error rather than overlapping
controls. Reopening samples the current card. Windows keeps its existing physical
DPI/client-to-screen path; local synthetic Cocoa Review corrects HighGUI's
work-height origin after its first move selects the screen. This follows
[OpenCV's owning Cocoa implementation](https://github.com/opencv/opencv/blob/4.13.0/modules/highgui/src/window_cocoa.mm).
ARCH-002 review extends the existing focused helpers without new dependencies,
protocol fields, image readers or continuous window repositioning.

Placement/closure selection19pass covers centered fit, clipping, insufficient room,
native minimum width, scales1/1.5/2, Cocoa coordinate conversion and Connect/Hide
lifecycle. Native isolated Retro Qt/OpenCV probes measure actual own-process Cocoa
frames against maximized Dashboard and restored Cameras cards: both contained,
center errors(-1,-2)px within conservative chrome reservation. The first native
probe exposed8px horizontal error from minimum width; the final probe includes it.
[Initial evidence](runtime-evidence-2026-10-17/review-synthetic-preview/card-fit-native-initial.json),
[final results](runtime-evidence-2026-10-17/review-synthetic-preview/card-fit-native.json)
and [method/source](runtime-evidence-2026-10-17/review-synthetic-preview/card-fit-native.py)
retain scope. Scoped Ruff/format, Win32 mypy2, boundaries716/zero violations and
whitespace pass; existing unrelated size advisories remain. A fresh maximized
Retro Review with synthetic previews was opened. No real camera, mixed-monitor
Cocoa placement or new-location Windows-native acceptance is claimed.

Oct17 `retro-entry-maximized-start` implements the owner's Retro entry prompts in
[G02](../docs/architecture/gui.md#g02) revision75. Shared Console painting adds `>`
to each nonempty HUD/log block in a reserved margin; separators and wrapped
continuations stay unmarked. Appearance switching restores the plain margin and
preserves text/entry metadata. The historical report records inspection of Dashboard
HUD/log captures (`retro-entry-hud.png` and `retro-entry-log.png`); both artifacts
are unavailable in this checkout as verified Oct21. That historical assessment
cannot be independently rechecked from these captures. They were local offscreen
Qt renders of sample data, not runtime/rig telemetry.

The owner clarified that the nonmaximized startup concerns local Review. An initial
native probe already reported maximized with frame equal to available desktop, so
the reported failure was not reproduced. The shared startup helper now reapplies
maximization once after the first native/layout event pass under
[G01](../docs/architecture/gui.md#g01) revision219, without forcing later Restore.
The saved-draft Retro Review was reopened with synthetic previews; its native frame
and available desktop both equal(82,33,1388,923), maximized true
([method/source](runtime-evidence-2026-10-17/review-synthetic-preview/retro-startup-native.py),
[result](runtime-evidence-2026-10-17/review-synthetic-preview/retro-startup-native.json)).
The menu bar/Dock remain outside the usable desktop. This establishes the current
local launch state, not the cause of the earlier report or Windows acceptance.

Appearance/HUD/startup/placement selection17pass, including style restoration,
unchanged log text and deferred maximize followed by manual Restore. Scoped
Ruff/format, Win32 mypy6, boundaries716/zero violations and whitespace pass.
ARCH-002 review reuses focused console painting and layout helpers without new
dependencies; the oversized main entry point only replaces its duplicate launch
calls with the shared helper. Existing unrelated cohesion advisories remain.

Oct17 `preview-window-follow` refines `preview-card-visibility` under
[G01](../docs/architecture/gui.md#g01) revision224. The ordinary card is replaced
by a centered `[ PREVIEW ]` caption and tall bracketed native-window footprint.
`preview-multiple-frames` adds a two-column grid of named source frames on Dashboard
and Cameras. Review and managed camera Connect/Show pass the exact source key to
placement; independent windows no longer receive the same coordinates. Keep positions stable for ordinary Show/Hide; page or enabled-camera membership
changes refresh the relevant source footprint set. Native chrome and headers fit each tile;
compact log minimum64px during Preview is also used by speculative placement and
restored on failure/last close. The fitted frame uses explicit geometry to avoid
fixed-child minimum-size feedback in the grid.
HUD/log retain their original column/alignment. Preview appears only while at
least one viewer is logically open; the log shares its height then and reclaims
it after the last close. First-open measurement temporarily expands the layout,
propagates ancestor geometry and restores visibility even on failure. Observer X
closure updates presentation without admitting commands.

Review uses focused Cocoa/Win32 native owner helpers; Windows runtime camera
HighGUI uses the same Win32 helper on its existing display thread. Separate native
windows stay above the GUI, follow its translation and minimize/restore together,
without global topmost status. Minimization retains Show/window/reader state;
latest private pixels redraw on restore, including without a new frame. The
optional display owner identity crosses the existing placement contract; Windows
checks top-level HWND/PID/process creation time and retains a query/synchronize
handle, rejects stale owners and reports cleanup failure. Capture/pulse ownership
and deadlines remain A10's. Runtime Tracking/stimulus viewer integration remains
unfinished under its existing scope; this does not certify those implementations.

ARCH-002 review chooses native owner links over embedding or another process;
no dependency, image transport or capture state is added. Placement, display
lifecycle and native mechanisms remain separate focused modules. The new platform
test module owns native display mechanisms/fixtures rather than a per-fix suite.
Boundaries720/zero violations; inherited size advisories concern other modules.
Regenerated19 protobuf sources. Acquisition manual-preview plus portable platform
checks130pass/2 Windows deselected; focused GUI placement/blank lifecycle/HUD
checks27pass/579deselected. Scoped Ruff/format13files and Win32 mypy8sources pass.
These are local checks, not Windows or rig acceptance. The separate full-GUI
merge/narrow-overflow limitation above remains open.

Actual native Retro Review verifies a200×206px native frame inside the200×210px
footprint, native parent identity, hidden preview while GUI is minimized with
Show retained, and visible preview above the restored GUI; explicit Hide closes
both window/link. Retina measurement initially exposed insufficient minimum
footprint sizing and was corrected. A subsequent native test exposed Qt/native
minimize-state disagreement; passing Review's Qt minimized state fixes it
([initial failed observation](runtime-evidence-2026-10-17/review-synthetic-preview/preview-follow-native-before-visibility-check.json),
[final result](runtime-evidence-2026-10-17/review-synthetic-preview/preview-follow-native.json),
[method/source](runtime-evidence-2026-10-17/review-synthetic-preview/preview-follow-native.py)).
The [Retro frame render](runtime-evidence-2026-10-17/review-synthetic-preview/preview-frame-retro.png)
was inspected; QWidget rendering excludes the separate native OpenCV pixels.
Additional actual Retro Review tests open Behavior cam, Tracking cam and Visual
stimulus together on both Dashboard and Cameras: all three native200×156px frames
fit independent200×160px targets, do not overlap, minimize/restore together and
retain their positions when one closes. Initial native test caught second-row
clipping; reducing the log minimum and settling tile geometry before measurement
fixes it. Preserved
[initial failure](runtime-evidence-2026-10-17/review-synthetic-preview/multiple-previews-native-before-fit.json),
[Dashboard result](runtime-evidence-2026-10-17/review-synthetic-preview/multiple-previews-native.json),
[Cameras result](runtime-evidence-2026-10-17/review-synthetic-preview/multiple-previews-native-cameras.json)
and [source/method](runtime-evidence-2026-10-17/review-synthetic-preview/multiple-previews-native.py).
The [Cameras frame render](runtime-evidence-2026-10-17/review-synthetic-preview/multiple-preview-frames-cameras-retro.png)
was inspected. Four added cases span both pages/styles and independent Show/Hide/X,
nonoverlap, stable coordinates and log restoration; the combined selection passes
25cases/585deselected, including existing camera admission/cancellation checks.
Scoped Ruff/format9files, Win32 mypy8sources and boundaries720/zero violations pass.
ARCH-002 retains grid/placement logic in its small owner; the oversized main module
only wires source-key callbacks, with no new responsibility or dependency.
Concurrent Retro styling edits are preserved; these tests describe the working tree.
Updated maximized Review remains open with multiple blank windows. The prior
[log growth native result](runtime-evidence-2026-10-17/review-synthetic-preview/card-visibility-native.json)
records439→144→439px before the bracket refinement. Windows native owner test is
included but unrun on macOS; actual Windows HighGUI/DPI/device acceptance remains
pending. No camera or rig pass is claimed.

Oct17 `review-blank-preview` updates the initial `review-synthetic-preview` under
[G01](../docs/architecture/gui.md#g01) revision221. Default isolated `--review`
now opens blank black OpenCV windows on camera Connect or an active source's Show,
including noncamera selector sources. The title retains its local Review label;
there are no image annotations, grid or animation. Existing placement, Hide,
Disconnect, inactive-source and exit cleanup remain. X clears visibility without
disconnecting the camera fixture. `--fake-previews` remains compatible; real-device
inspection retains its separate opt-in boundary and managed acquisition is unchanged.

ARCH-002 review removes drawing/frame-update work from the existing focused helper;
the timer only pumps native events and detects closure. No dependency, process,
camera reader or runtime reference. Owning placement/lifecycle selection19pass,
including black pixels before/after polling, camera and Visual stimulus Show/Hide,
external closure, Disconnect and cleanup. Scoped Ruff/format, Win32 mypy2,
boundaries718/zero violations and whitespace pass. The actual Review entry point
with `--review` alone opens a native visible180x180 black image, then closes it;
the updated GUI remains open for the owner
([method/source](runtime-evidence-2026-10-17/review-synthetic-preview/blank-default-native.py),
[result](runtime-evidence-2026-10-17/review-synthetic-preview/blank-default-native.json)).
Earlier native smoke of the animated version is historical
([method/result](runtime-evidence-2026-10-17/review-synthetic-preview/native-smoke.json),
[source](runtime-evidence-2026-10-17/review-synthetic-preview/native-smoke.py)).
Windows-native, real-camera and rig acceptance remain separate under E15.

Current Oct17 recording sync repair completes a 120 s concurrent workload at
unchanged saved quality, with Behavior 3598/3598, Tracking 7188/7188 and stimulus
7200/7200 retained exactly once, zero native counter gaps/capacity omissions.
The explicit fixture uses temporary 16 stimulus slots; restored saved three-slot
startup behavior is not certified. Normal output closure, Cleanup/NewSession and
Shutdown/process absence confirm; original sync cadence and lifecycle bounds stay.

Full backend validation is 2209 passed/5 privilege skips; explicit NVOF rig case
passes. Ruff/format, Win32 mypy 815 files and 717 backend modules/zero boundary
violations pass. GUI source is unchanged; prior GUI evidence is historical, not a
new native GUI run. All three camera baselines and ten operator files restore.
Earlier Abort Finished, failed-Setup late report and historical Shutdown findings
remain open. Pixel-exact performance on final source remains unvalidated; failed
pre-hotpath-guard experiments cannot establish current success or failure.
[Current evidence and provenance](runtime-evidence-2026-10-17/file-sync-fix/README.md).

Oct16 `device-action-cancel` implements owner-selected safe cancellation under
[G01](../docs/architecture/gui.md#g01) and [A11](../docs/architecture/acquisition.md#a11).
Camera Connect/Test selected, MCU connection/pin tests and SpikeGLX Test connection
show Cancel while pending and disabled Cancelling after a click. The GUI skips
remaining steps, waits for the existing bounded call, and closes only newly created
resources using confirmed controller identity. Accepted settings and pre-existing
connections remain. MCU cleanup adds an exact-connection Disconnect command using
the existing outputs-off/close owner; admission and execution retain authority,
Configuration/camera-claim gates and bounded deadlines. Unconfirmed cleanup or
changed controller/acquisition identity is an error, never reported as cancellation
success. Firmware Upload and safety Stop/Disconnect retain their completion behavior.
Restart the full runtime to load both client and controller contract changes.

ARCH-002 review: isolated button/token and compensation logic in two focused GUI
modules; existing panels/coordinators only wire lifecycle callbacks, with no new
process, package, whole-runtime back-reference or duplicate authoritative device state.
Existing size advisories for panels/main remain cohesive presentation/orchestration
owners. Extended the owning GUI and MCU behavior suites. Final offscreen selection
(`pytest tests/gui/test_dashboard.py tests/controller/test_microcontroller_owner.py
 tests/controller/test_microcontroller_protocol.py -q -k
 '(camera or mcu or microcontroller or spikeglx or cancellation or manual_disconnect)
 and not picker and not chooser'`) passes272, skips1, deselects443. A subsequent
pin-button click assertion passes separately (1/582 deselected). Covers queued and
in-flight cancellation, skipped Show/Connect, retained accepted settings, exact new
preview/serial cleanup, preserved pre-existing connection, generation change,
cleanup failure, repeat-click fencing and button restoration. Initial checks exposed
and fixed the MCU completion label overwrite and managed-camera Cancel authority gate;
two older request-dictionary assertions now include the per-request cancellation token.
Ruff/format212, Win32 mypy210, boundaries715/zero violations and whitespace pass;
19 Protobuf sources regenerated. Tests used approved loopback access and Qt offscreen.
No live-device cancellation, firmware action or native/rig acceptance was performed;
[E15 rig verification](rig-verification.md) remains separate.

Oct16 `gui-preview-slot` implements [G01](../docs/architecture/gui.md#g01): runtime
and Review open maximized, with a reserved Preview area on Dashboard,
Devices/Cameras and Tracking. Owner native feedback exposed the initial full-height
card and preserved Z-order as unsuitable. The fitted card now reserves only the
initial image/native chrome plus heading/padding; physical ClientToScreen mapping
targets its inset child region. Native owner-checked placement uses topmost without
activation, keeping detached windows visible above GUI interaction. Other tabs
reclaim the area; reopening samples current layout. No embedding, image reader,
new protocol/process or backend state is introduced. Focused existing placement
and Windows-native modules own the change under ARCH-002.

Oct16 validation before the below-status correction:14 GUI layout/placement cases and three HighGUI thread/failure
cases pass. The native HighGUI case passes outside the sandbox after sandbox
shared-memory denial; it verifies frame size/position, topmost, nonactivation,
wheel/reset and independent closure/producer continuity. An isolated real Qt/OpenCV
probe verifies exact inset/frame match after GUI activation: maximized image640,
frame642x672 at(1250,150), restored image373/frame375x405 at(805,158), both96dpi.
The fitted native GUI capture was inspected. Scoped Ruff/format, Win32 mypy3 and
boundaries715/zero violations pass; existing unrelated cohesion advisories remain.
[Native probe and results](runtime-evidence-2026-10-16/preview-slot/native-slot-results.json)
and [validation history](runtime-evidence-2026-10-16/preview-slot/validation.txt)
retain bounded scope. No real camera, mixed-monitor DPI or full-workload acceptance
is claimed. Restart the application to load both GUI and acquisition-owned native
placement changes; no running application/device was restarted by this work.

Current integration (2026-10-16, `merge-dev-gui`): fetched origin/main eac2e0e
is merged with local rig fixes a0dc31a and the appearance checkpoint3743a81.
[G01](../docs/architecture/gui.md#g01)/[G02](../docs/architecture/gui.md#g02)
share the dev font, CRT controls, dynamic card/focus treatment, HUDs, tab appearance
and camera Test selected/Connect row with runtime. MCU wiring is hidden in both
camera layouts; existing camera pin/MCU configuration remains available. Review-only
inline inputs/outputs and multi-screen pulse simulation retain their runtime contract
boundary. Appearance preferences retain the shared key and legacy Review fallback.
This supersedes the narrower appearance-only implementation reported earlier in LOG.
Controller conflict resolution preserves the rig-proven explicit rejected-Update
versus uncertain-transport handling, merged with the dev typed callback contract.
Generated bindings were regenerated from all19 authoritative Protobuf sources.
Local/backend validation:129 conflict-owner cases pass; broader rig-independent
selection2119pass/four skips/31deselected, with three external-asset fixture errors
caused by workspace basetemp. Those three pass on rerun with normal external temp.
The sandbox asyncio socketpair stall was diagnosed before the approved loopback run.
Package sdist/wheel build succeeds outside the sandbox after a temp-access failure.
Ruff/format924, Win32 mypy811 and boundaries713/zero pass. GUI16 focused integration
cases pass. Broader offscreen GUI run passes536 with29 picker/chooser exclusions;
two stale HUD expectations fail, then both pass after alignment with G02's compact
HUD while preserving authority checks. No complete native-GUI pass is claimed.
[Merge context, package logs and runtime camera raster](runtime-evidence-2026-10-16/dev-merge/context.json)
retain the source revisions, checks and limitations.
The protocol timeline remains a cohesive drawing/interaction owner; palette changes
introduce no new runtime ownership or dependency. Both branches' dated rig and dev
evidence below is retained with its original scope; local checks do not refresh rig
acceptance. No device/firmware actions or saved configuration changes were performed.

Historical comprehensive Oct15 audit final source checks pass (E06/E07/E08/ARCH-002):
1920 backend cases pass/five skip/one rig deselected, including eligible native
Windows and HighGUI tests. Ruff, format915, Win32 mypy795 and boundaries699/zero
violations pass. Five skips retain privilege/platform limitations in the JUnit log.
The separately selected rig-only synthetic CUDA/NVOF lease test also passes; it
does not enable live Tracking processing or feedback.
GUI519 pass offscreen across512+7 selections. Native execution finishes510pass/two
fail with seven picker roundtrips excluded. A focused follow-up replaces an
unsupported320px test cap with equal-height/control-containment checks; the full
native trial-row interaction then passes. Inline timeline MouseMove delivery
remains unresolved despite an active/unobscured target; synthetic picker selection
is ignored by the Windows helper. Computer-use state capture separately hangs
twice, so complete manual/native feature acceptance and an all-tests-pass claim
are unavailable. The native failures do not establish clipping or operator picker
failure; bounded diagnostics and exact process absence are retained.

Focused controller repairs distinguish explicitly rejected live-calibration Updates
from unknown transport outcomes, and require acquisition pulse readback only for
enabled external-trigger cameras. Owning coverage pins retained Active fencing,
valid retry after rejection, and real free-running/external readback adoption.
Camera configuration59 cases pass. The later empty-edit failure is traced to a
Windows asyncio timeout occurring3.4854ms before its original deadline. The
acquisition wait now retries only within that unchanged deadline; deterministic
regressions and the combined acquisition/controller/shared1148pass/four privilege
skips verify the correction. Affected managed-interpreter cases70pass/one skip.

Fresh COM8 boot text is `OK READY three_camera_ttl`; read-only request-ID CAPS
returns `ERR Unexpected command arguments`. Managed Connect reaches its original
deadline failure; firmware is unchanged. Earlier40-second preview attempts stop
before the configured70-second deadline and establish only incomplete admission
within the harness bound. Exact managed exit receipts/inventories separate attempts.

The corrected retained-COM8/free-running Setup reaches acquisition Ready but the
saved arena asset exceeds the declared GPU budget. Cancellation then leaves an
exact quarantine containing its marker/lock; its275-character marker path fails
ordinary Windows filesystem access, blocking startup recovery. Native before/after
tests verify existing extended-path transport repairs both cancellation and
lock-only settlement while marker/user-file guards remain strict. Exact own
unstarted artifact remediation retains marker/lock bytes and hashes; no durable
pointer is edited and no general recovery acceptance is claimed.
Subsequent native recovery and seven managed trials complete: four normal60-second
Save-On trials (Gaussian and reduced-texture arena), one normal60-second Save-Off,
and two interrupted trials. All18 retained videos fully decode/count successfully;
Off retains frame/scientific logs but no videos. The immediate post-Abort trial
crosses the retired boundary8.1452seconds after its new start and completes normally.
Abort still takes approximately40.12seconds to settle interrupted metadata; this
responsiveness finding remains open. Independent camera/shader/NVENC runs and nine
full-video decode/count passes are recorded in the owning backend reports; they
do not prove managed lifecycle or calibrated projector rendering. Native cancellation
and startup lock-only settlement now use the existing extended-path transport;
marker-bearing/user-file guards remain strict. The unused shared Deadline wrapper
is removed after a source/contract consumer search, retaining active helper coverage.
An unsupported whole-suite managed-executable
invocation separately fails an entrypoint child missing its DLL bootstrap; this is
retained separately from normal-suite results. [Fresh evidence and settings backups](runtime-evidence-2026-10-15/comprehensive-audit/)
retain these limits; previous successful endurance evidence remains historical.

Fresh native photodiode and blackout diagnostics now pass Open, invalid bounds
rejection, subsequent valid updates, move/remove and Close with Idle/resources
closed; saved asset/profile hashes remain unchanged. The repair validates before
GL dispatch and propagates only typed, exactly proven retained-Active rejection
without renderer shutdown. Generic/mismatched failures remain fatal.361 owning
and132 managed-interpreter cases cover the full mailbox/report path. Opening
calibration after a completed session remains rejected by
retained interrupted/setup fences; safe context retirement is a separate follow-up.

| Feature group | Fresh evidence | Remaining limit |
| --- | --- | --- |
| Dashboard, file/load/save, protocol/variation validation, status and operator controls |519 offscreen pass; native510pass plus focused repaired row pass; [per-feature owning inventory](runtime-evidence-2026-10-15/comprehensive-audit/gui/coverage-inventory.json) |One native hover-input failure and seven synthetic picker roundtrips remain; manual end-to-end GUI coverage incomplete |
| Setup/Start/normal completion/NewSession |Real authenticated controller, two cameras and four projectors; Gaussian and reduced-texture arena |Unaligned free-running fixture; no MCU synchronization or Tracking processing |
| Video Save On→Off→On |3→0→3 videos; frame/scientific logs retained throughout |No scientific scene-quality acceptance |
| Abort/reuse |Two Interrupted trials with confirmed cleanup; immediate new trial crosses retired boundary and completes |40.12second interrupted-metadata settlement remains |
| Camera/controller connections |Fresh enumeration, native Setup/readbacks, full-bound COM8 failure |Legacy MCU command dialect prevents external-trigger acceptance; no firmware flash |
| Calibration diagnostics |Two native views pass Open/invalid→valid/move/remove/Close with unchanged asset hashes |Post-session reopening still fenced; physical calibration unmeasured |
| Rendering/encoding capacity |CQ23/CQ18 camera+offscreen-shader workloads, native4096 variant, full counts/decodes |Tracking imagery sampled black, native4096 one BlockID gap; initial CPU sample confounded |

The final isolated production workload runs exactly60seconds with Behavioral
1760×1716/30Hz and Tracking 1588×1344/60Hz, camera CQ23, stimulus CQ18/YUV444,
four60Hz projector outputs and the explicit512-pixel arena derivative. No other
test runs during this interval. Current machine is Ryzen9 9950X16cores/32threads,
66,094,223,360bytes usable RAM,2TB CT2000P3PSSD8, RTX5060Ti16,311MiB and
RTX2080Ti11,264MiB (driver617.14). [Hardware and monitor evidence](runtime-evidence-2026-10-15/comprehensive-audit/).

| Active-trial measurement | Median |95th percentile |Maximum |
| --- | ---: | ---: | ---: |
| System CPU |11.28% |16.19% |20.32% |
| RTX5060Ti GPU utilization |11% |12% |12% |
| RTX2080Ti encoder utilization |44% |46% |47% |
| Monitored process working sets |2.137GiB |2.179GiB |2.189GiB |

Device-wide GPU memory is716/713MiB respectively;5060Ti encoder utilization is0%.
Working sets include monitoring processes/shared pages and are not system used RAM;
process IO counters include pipes, not physical disk bandwidth. GPU UUIDs and
59 active one-second GPU/CPU-delta samples are retained; no per-process GPU
attribution or sustained headroom guarantee is inferred. Camera videos contain
1801=1798real+3duplicate and3600=3588real+12duplicate frames; stimulus contains
3600=3592real+8duplicate frames with four capacity drops/two same-slot omissions.
Camera failed/missed buffers are0 and counter gaps absent. Stimulus has3598 render
groups, median16.659ms/p99 17.920ms/max33.381ms intervals, with no unresolved
submission attempts. All three full decodes match declared counts, completing
27 video validations across18 managed/nine direct outputs. This is a bounded
low-loss engineering result, not optical synchronization or representative-scene
quality acceptance. [Active resources](runtime-evidence-2026-10-15/comprehensive-audit/managed-isolated-mixed60-r1/resource-assessment.json),
[source/CFR accounting](runtime-evidence-2026-10-15/comprehensive-audit/managed-accounting-summary.json).
All three original pre-audit PFS files restore byte-exact, every original feature
readback matches and all cameras close. All10 saved JSON/TOML files also match
their original bytes; exact application exit receipts confirm process absence.
[Restoration](runtime-evidence-2026-10-15/comprehensive-audit/final-restoration.json).
Final Shutdown returns a successful command and exact process-absence receipt but
also emits `cleanup returned an unregistered resource` from Visual Stimulus after
the completed trial/NewSession/original-configuration restoration sequence. The
trial, decode/count and physical restoration evidence remain valid; shutdown
resource-report acceptance is unresolved. [Emergency evidence](emergency-80538644376400-cf134742-126d-4fc6-aa22-c7ed8d33f493.json)
is retained for a focused follow-up rather than interpreted as clean shutdown.

Oct16 output-content audit under [SYS-004](../architecture.md#sys-004),
[E04](../docs/architecture/supervisor.md#e04),
[A07/A09](../docs/architecture/acquisition.md#a07),
[T19](../docs/architecture/tracking.md#t19) and
[V13/V28](../docs/architecture/visual_stimulus.md#v13): current files retain the
software-side joins below. Both confirmed findings are repaired locally: missing
stimulus replay provenance ([Visual Stimulus assessment](visual_stimulus.md)) and false
absence in camera failed-output summaries ([Acquisition assessment](acquisition.md)).
The repair selection passes997 tests (five platform skips, three exclusions), plus
five final-publication cases; [repair evidence](runtime-evidence-2026-10-16/output-provenance-fixes/validation.json)
retains commands and limits. No additional central-metadata/Tracking output defect
was established in this scoped review.

| Outputs | Retained alignment/reconstruction input |
| --- | --- |
| SESSION_CONFIG, SCHEMA, SESSION_LOG and trial LOG | Session/trial identities, effective configuration, wall/host anchor, planned occurrences, versioned output index and closure; paired SpikeGLX readback/inventory. |
| Camera frame JSONL plus optional MP4 | Exact sequential video-to-source join, receipt/native clocks and counters, explicit invalid/capacity loss and terminal cutoff/accounting. Nominal playback time is not acquisition time. |
| Optional Tracking JSONL | Selected camera role/settings, source IDs and receipt intervals, result/pose/reset/discard evidence; joins to stimulus by stream/result identity. |
| Stimulus recipe and always-saved frame JSONL | Resolved plan/assets/display settings, consumed uniform words, actual media/image choices, effective arena pose, per-output submission/marker times and review-video source mappings. |
| Original SpikeGLX files | External authority for recorded pulse sample times; transfer full native files/metadata and retain segment/stream identity. CephVR control timestamps do not substitute for pulses. |

Owner clarification (Oct16): hardware pulse wiring is verified, all planned camera
recordings will use external triggers, Tracking backend work is deferred, and the
current reconstruction target is software-generated output. This is owner-supplied
hardware evidence; the local audit did not measure wiring or query live mappings.
Checked-in pulse_inventory remains unassigned. Retaining the actual saved-channel
mapping and source-counter semantics still matters for interpreting losses and A09's
assumed initial correspondence. Physical projector light onset is outside this task's
acceptance target. Preserve external assets once in a versioned library, the matching
renderer/environment and native SpikeGLX files; per-run manifests reference matching
content under V13 without copying it. Offline analysis/replay implementation remains
deferred; no new clock fit, asset archive, runtime policy or hardware action is introduced.

The earlier audit selection passed337 across acquisition, controller metadata/planning/
output admission/SpikeGLX control, Tracking recording and stimulus resource/render/
evidence owners. Two standalone probes reproduced the pre-repair findings; first probe invocation
needed the repository on PYTHONPATH. [Commands, source hashes and limitations](runtime-evidence-2026-10-16/backend-output-alignment-review/validation.json)
are retained with raw output. No actual session compilation, native GPU replay or
physical timing validation ran; remaining execution stays in the
[single rig checklist](rig-verification.md).


Oct16 `review-terminal-refinements` applies owner-selected suggestions 2/3/4/5/9,
then 6/7/8 as the Review candidate under [G01 revision210](../docs/architecture/gui.md#g01).
Existing inverse selection/hover and cursor work is retained. Disabled bracket labels
use lowercase; the selected sidebar carries a prompt. One cached, mouse-transparent
window film uses 13/255 scanline alpha and a faint vignette, toggled with heading/lamp
glow in Style. Per-console scanlines were removed so CRT Off removes the film.
IBM Plex Mono Regular (168 KiB) ships with IBM's unmodified OFL license and source/hash
record; Qt registers the bundled font once. No package dependency was added.
The candidate uses a single-line wordmark with a lower rule and double frames on every Retro card
(owner-requested all-card trial), contiguous block-character position meter and shape-coded status lamps.
Position/status/phase retain existing view authority; phase remains in the HUD.
Standard/runtime retain their theme and gates; Tracking controls retain their presentation.
Protocol now shares the Retro treatment described below.

ARCH-002 review moved separable status-lamp drawing into the existing retro instrument
module before extending it; shared components remain below the size advisory threshold.
Offscreen wide/narrow renders were inspected, including empty-log cursor and CRT Off.
Extended owning style-switch coverage passes at1440/720 pixels, preserving drafts,
log bytes, view identity, gates and Standard runtime; checks include actual font family,
mouse transparency, cached-film reuse and toggle behavior. GUI
Ruff/format166, Win32 mypy5, boundaries706/zero violations and whitespace pass.
[Raw checks and rendered fixtures](runtime-evidence-2026-10-16/review-terminal/).
Focused affected GUI checks pass11 (534 deselected). Local non-isolated build produces
a wheel and source archive; all font/license/source bytes match in both packages.
Initial isolated build could not resolve PyPI; installed build dependencies succeeded. An overly broad GUI run
was intentionally interrupted after34 cases and Qt aborted on interruption; no complete
suite pass is claimed. Initial test-import placement/lint issues were corrected before
the passing style checks. Native Windows/DPI, CRT comfort/repaint cost and rig acceptance
remain unmeasured; this work stages appearance only.
Owner-requested all-card frame trial removes the primary-only marker and uses the
same double outline for each Retro card under [G02 revision48](../docs/architecture/gui.md#g02).
Fresh style-switch2, scoped lint/format/mypy, boundaries and whitespace pass;
[comparison renders and commands](runtime-evidence-2026-10-16/review-terminal/all-card-frames/)
retain the prior primary-only fixture alongside this candidate. Standard is unchanged.
The owner subsequently removed the extra review/phase/clock banner under G02rev49;
its label, timer, style rule and obsolete test assertions are removed. Existing
appearance-switch2 passes at both widths; scoped Ruff/format/mypy, boundaries and
whitespace pass. [Fresh render and validation](runtime-evidence-2026-10-16/review-terminal/no-banner/)
show the resulting layout; wide offscreen render inspected. No native/DPI claim.
Owner-requested [Running presentation](runtime-evidence-2026-10-16/review-terminal/running/)
uses existing Review widgets/state: trial2/6, current-trial elapsed48s, ready lamps,
open/reserved/synced sample outputs and coherent example log entries. Setup/Start
and session editing are locked, Stop enabled. Wide/narrow renders inspected and
fixture assertions pass. An isolated interactive window was launched without startup
error; native visibility was not independently inspected. No production source/default
or saved Review draft is changed; content is static sample data, no commands or devices.
Subsequent owner-requested HUD simplification under G02rev50 removes Outputs,
Reservation and Metadata display rows while retaining the underlying state records.
The Retro trial-position glyph strip repeats across the full available width,
preserving current-position/count semantics. [Fresh running preview/checks](runtime-evidence-2026-10-16/review-terminal/hud-simplified/)
pass11 existing appearance/phase/layout cases, scoped lint/format/mypy, boundaries
and whitespace; wide/narrow renders inspected. The owner subsequently selected
Trial time and Total time elapsed/duration pairs under G02rev51, replacing the
previous Elapsed row. Review shows48/150 seconds and198/900 seconds. The managed
projection derives trial duration from scheduled end minus start; the focused
regression distinguishes actual elapsed48s from planned150s and preserves unknown
values. Current Snapshot/SessionState lacks session start/total-duration fields, so
managed total values remain unknown; live-total projection is a follow-up, not a
session-clock estimate or schema amendment. [Timing fixture/checks](runtime-evidence-2026-10-16/review-terminal/time-pairs/)
pass4 existing style/HUD/projection cases plus scoped lint/format/mypy3, boundaries
and whitespace; wide/narrow renders inspected. Native/DPI and rig acceptance remain separate.
The owner consolidated Phase/Outcome into Status, then removed Control under G02rev53:
show reported outcome when available, otherwise current phase, and separate Status
from Trial/timing with a blank line. Command authority/gates remain unchanged. [Updated layout evidence](runtime-evidence-2026-10-16/review-terminal/status-group/)
passes11 existing style/layout/phase cases plus scoped lint/format/mypy, boundaries
and whitespace; wide running render inspected. Live-total timing remains pending.
[Control-removal validation and fresh preview](runtime-evidence-2026-10-16/review-terminal/no-control/)
passes11 appearance/layout/phase cases and scoped lint/format/mypy, boundaries and
whitespace; wide render inspected. No native/DPI/rig claim.

Owner-requested Devices/Protocol/Previews styling and refinements follow
[G01rev212](../docs/architecture/gui.md#g01) and
[G02rev73](../docs/architecture/gui.md#g02). All four device subtabs share the Retro
font, double frames, square controls and bracketed buttons; selected table rows use
dark blue-teal/light text to keep enable boxes visible, while navigation/menu inverse
selection remains. Diagrams retain geometry/semantic roles and use the active palette.
Previews uses a compact shared Card and separate cached, mouse-transparent CRT film;
the style toggle controls both windows. Drafts, preview pending/visibility, device
ownership and command gates remain intact. Runtime retains Standard; shared
table/header sizing repairs apply across pages.
All tab HUDs now use the Dashboard's shared structured-row renderer in StatusColumn:
uppercase labels, aligned value columns across groups, Retro colon separators,
blank section gaps and the same fitted console. Dashboard, device readbacks, MCU
fault/diagnostic updates and Tracking ordinary/diagnostic readouts share this path;
freeform notes retain their text. Appearance changes re-render stored presentation
rows, while Dashboard also refreshes its separately owned trial-position strip.
Tracking's HUD/log column alone follows Retro; its controls remain unchanged.
[Shared HUD evidence](runtime-evidence-2026-10-16/review-terminal/shared-hud/) retains
wide/narrow captures across Retro/Standard/Retro, raw tests and source hashes;
Dashboard/Camera/MCU/Tracking wide cards inspected.42 owning HUD/device/appearance
cases and one additional managed Tracking diagnostic case pass. GUI/test Ruff,
scoped format13, Win32 mypy12, boundaries712/zero violations and whitespace pass.
Initial checks exposed omitted trial-strip refresh and an obsolete equal-width
measurement assertion; repaired. Tracking timing assertions now check retained rows.
The484-line component module remains cohesive shared widget presentation; no new
framework, dependency or backend policy. No native/DPI/CRT-cost/rig acceptance claim.

Protocol now joins the shared Review Retro surface: double card frames, uppercase/glowing
card titles, bundled font, bracketed text buttons, native block caret/focus corners and
inverse menu/trial/timeline selection. Timeline paint uses the active palette and square
Retro frames; unselected epochs retain their deterministic stimulus-content colors.
A shared divider role replaces local QSS. New screen rows register their advanced-card
titles/glow through the existing screens-changed notification; no generic widget observer.
Symbol-only controls retain bare glyphs to fit fixed affordances. Narrow group controls
omit the redundant Selected group caption and balance fields so Group name/Repetitions
remain readable. Qt models, selection/hits, source/history, validation and Running locks
retain their owners; rendered scientific stimulus content is unchanged.

[Protocol evidence](runtime-evidence-2026-10-16/review-terminal/protocol/) retains wide/narrow
fixtures, initial failures, final tests and source hashes. Final15 tests pass, plus both
appearance cases pass again after the shared-HUD integration settled. Checks cover
1440/720 style switches, screen rows added after Retro selection, caption/glow/focus,
unpersisted draft/history/gates, selected-block pixels, layouts, actions/undo and clipboard
paths; renders at1440/1175/720 include populated rows and advanced settings, with wide,
narrow and advanced views inspected. Ruff/format7, Win32 mypy6, boundaries712/zero
violations and whitespace pass. Initial icon-role changes were reverted to preserve
Standard behavior; the shared Button skips decorative brackets on symbolic glyphs.
A pre-existing platform-dependent321px card height failed a320px test cap even with
the original inline divider restored; the owning assertion now checks compact bottom
padding against actual group controls rather than a font-dependent total height.
Fixture draft setup now explicitly applies the local edit before testing style changes,
matching existing subgroup auto-commit semantics. A temporary concurrent shared-HUD
change omitted Dashboard rendering and hid its trial-position instrument; the settled
appearance path renders both status rows and Dashboard instruments once.

ARCH-002 cohesion review retains the existing timeline paint/interaction owner: palette
lookup and selection paint use its current geometry/state without another coordination
layer. Shared tests remain in their owning behavior module. No full GUI-suite, native/DPI,
CRT repaint-cost, hardware or rig acceptance is claimed.

Owner reported a crash on Add variation rule. The13:37 native report shows SIGABRT
through PyQt QTableWidget eventFilter amid nested QWidget visibility/synthetic enter-leave
dispatch; its original Python exception and exact loaded source revision are unavailable.
VariationTable changed remove-button visibility inside Enter dispatch, while the table-mode
row also showed the same button in its own Enter handler. Under G02rev73/ARCH-002,
the table now owns these affordances alone and coalesces hover updates through one
parented single-shot Qt slot after dispatch, resolving the pointer against current rows.
Pending updates tolerate removal/replacement; standalone rows retain their hover owner.
No rule values, generation/seed behavior, source ownership or history policy changed.

[Variation crash evidence](runtime-evidence-2026-10-16/review-terminal/variation-crash/)
retains native stack extraction/provenance, red callback-timing assertions, native probes
and final25 passing variation/subgroup/history/style cases. Both Standard/Retro regressions
failed before repair and pass afterward; hover show/hide and queued removal/reopen are
covered. Ruff/format3, Win32 mypy2, boundaries712/zero violations and whitespace pass.
Native Cocoa runs complete21 repaired add/remove cycles across1440/1175/720:9 Standard,
9 Retro and3 using the owner's saved Review draft read-only. No callback errors occurred.
The exact original abort was not reproduced even with legacy callbacks restored in an
isolated saved-draft probe, so the repair removes the implicated reentrant path rather
than proving its original Python exception. Keep `variation-open-crash` pending owner-session
confirmation and collect stderr if it recurs. The first sandboxed Cocoa attempt could
not access screens; approved isolated native runs succeeded. No native Windows,
alternate-DPI, hardware or rig acceptance is claimed.

Camera HUD now shows inventory found/enabled counts, a single shared dashed separator
in Retro, then selected role, connection status, Trigger source, controller-configured
external Trigger rate and backend acquisition rate. Trigger source shows Internal clock
or External controller above Trigger rate, from controller configuration in managed
mode and the local draft in Review. Its confirmed serial-keyed projection clears on
disconnect and is reused when installing editable drafts. Five owning appearance/pin/
inventory cases pass, with both inventory cases rerun after final source/disconnect
assertions; Ruff/format3, Win32 mypy2, boundaries712/zero violations and whitespace pass. Confirmed trigger configuration is keyed by serial
and cleared on controller disconnect; unsaved edits/free-running camera pulse drafts
are not shown as confirmed external rates. CameraDeviceView currently exposes no
measured receive rate; Acquisition rate stays unknown and `camera-acquisition-rate-readback`
tracks that integration. No configured/synthetic frequency substitutes for observation.
[Camera HUD evidence](runtime-evidence-2026-10-16/review-terminal/camera-hud/) retains
wide/narrow sample captures and source hashes; wide image inspected. Five selected
appearance/preset/inventory cases pass, with both inventory cases rerun after final
count/status assertions and separator cleanup. Scoped Ruff/format3, Win32 mypy2,
boundaries712/zero violations and whitespace pass. The shortened camera page remains
its existing cohesive assembly; no new helper/dependency or backend schema change.
No native/DPI/hardware/rate-measurement acceptance claimed.
The sidebar brand omits its Experiment Control subtitle in both appearances. Retro
uses a single-line CEPHVR wordmark with restrained tracking, a thin lower rule and
version only in the footer, replacing the awkward text-drawn box. [Sidebar renders](runtime-evidence-2026-10-16/review-terminal/sidebar-wordmark/)
fit at1440/720px; wide crop inspected. Two appearance cases, Ruff/format3, Win32 mypy2,
boundaries712/zero violations and whitespace pass. First standalone capture exited138
during Qt teardown after saving images; explicit effect removal/deferred-widget cleanup
lets the same fixture exit0. No production teardown regression or native/DPI acceptance
claim is inferred from the standalone fixture.
The Photodiode card uses shared content-sized caption geometry; its obsolete wrapping/
full-width override is removed so the frame gap is100px rather than nearly card-wide.
Main page headings share the existing card-title CRT glow and its toggle. [Heading/frame evidence](runtime-evidence-2026-10-16/review-terminal/heading-frame/)
checks1440/1175/720 caption widths and all four page headings;1175 card and Devices
heading inspected. Six existing appearance/layout/configuration cases pass, including
matching glow parameters and CRT-off/Standard removal; Ruff/format3, Win32 mypy2,
boundaries712/zero violations and whitespace pass. Existing cohesion warnings unchanged;
no native/DPI/repaint-cost acceptance claimed.
Card captions now use Displays layout without its Display IDs suffix, Setup geometry
instead of Tank & screens, and Runtime log across shared page assemblies. Retro
retains its existing uppercase transform. Three existing card/appearance checks pass;
the dashboard-only card assertion now excludes the separately owned Preview sources
dialog introduced earlier. Initial run exposed that assertion drift. Scoped Ruff/format,
Win32 mypy2, boundaries712/zero violations and whitespace pass; native/DPI unverified.
SpikeGLX Input channels now content-sizes Use instead of fixing it at42px.
[Header geometry and renders](runtime-evidence-2026-10-16/review-terminal/input-use-header/)
show one-line Use at1440/1175/720 in both appearances (Standard53px, Retro50px);
Retro1175 capture inspected. Five owning inventory/layout cases pass, scoped
Ruff/format/Win32 mypy1, boundaries712/zero violations and whitespace pass.
Native/DPI acceptance remains separate.
Icon-only controls use a dark hover/pressed fill and accent outline, preserving refresh
symbol contrast. [Actual-control state captures](runtime-evidence-2026-10-16/review-terminal/refresh-hover/)
verify normal/hover/pressed/disabled rendering and measure the hover/pressed background;
hover/pressed images inspected. Two appearance cases, scoped Ruff/format/Win32 mypy,
boundaries712/zero violations and whitespace pass. Native/DPI inspection remains separate.

Projector measurement Screen/scale columns size to contents, allocating the remainder
to measured X/Y; the header fits one line at1440/1175/720px. Offset X/Y share one cell
like Width/Height. Scale labels display one decimal in their existing mm/px unit;
raw measurements, derived distance and saved precision remain intact. [Calibration evidence](runtime-evidence-2026-10-16/review-terminal/calibration-table/)
retains geometry, captures and source hashes;1175px cards inspected. Seven calibration
checks pass, including rounded-display/full-precision derivation and paired offset
ownership; Ruff/format3, Win32 mypy2, boundaries712/zero violations and whitespace
pass. Existing cohesion warnings unchanged; native/DPI acceptance remains separate.

Shared PathEdit fields now accept both Ctrl and Command-style select-all/copy/cut/paste
through native line-edit operations, preserving full underlying paths. Focused read-only
paths display native text selection rather than elided painting. This covers output and
Assets directories, stimulus filepaths and other shared path fields; mutation still
respects read-only/disabled gates and existing stimulus validation/commit ownership.
The local baseline reproduced Meta+V inserting a literal v while Control+V pasted.
Seven owning clipboard/asset/style cases pass, plus both stimulus cases rerun after
extending coverage to an absolute pasted path; relative paths, Unicode/long directories,
selection/cut, saved-asset commit, invalid-file rejection and Running locks are checked.
Ruff/format2, Win32 mypy1, boundaries712/zero violations and whitespace pass. One
integer-versus-Key mapping annotation/import-order finding was repaired. Native platform
clipboard integration remains unverified beyond host offscreen Qt; no rig claim.

Styled inputs use one native Qt block caret at insertion position, with typed text
immediately to its left. The theme's existing Fusion base supplies a wider cursor metric
only to Retro QLineEdit fields; remove decorative block painting and separate field
blink subscriptions. Qt owns cursor placement, scrolling, selection and blinking;
Standard restores the base thin caret. [Native-caret evidence](runtime-evidence-2026-10-16/review-terminal/native-block-caret/)
checks typing, Home/End insertion, selection replacement, long-value scrolling and
Standard/Retro switches (cursor rectangle width16 versus10 including Qt insets).
End/Home/replacement/long-value captures inspected. Five owning appearance/pin/editing
cases pass; Ruff/format2, Win32 mypy2, boundaries712/zero violations and whitespace
pass. No native/DPI/complex-script acceptance claimed.

Camera source/rate/pin boxes now bottom-align when a label wraps: source review and
capture reproduced an8px rate/pin offset at1175px, then actual y/height equality passes
at720/1175/1440. VSync mode is an independent full-column field aligned to card edges.
Shared Qt headers measure wrapped text at actual section widths and refit after
resize/font changes, retaining empty-header visibility and owner extra-height settings.
A resize lambda initially segfaulted in a repeated-window sequence; a receiver-owned
Qt slot removes that reproduced failure in the five-case sequence and final21 checks.
This is not evidence about the historical native GUI fault's cause.

Review Add output now inserts an empty inline type/pin row with no menu/pin dialog.
Selecting an existing supported signal binds its original pin owner; changing type
transfers that pin without changing camera participation. Clearing a selected pin
retains the row until explicit removal. Unassigned/empty drafts survive both marked
Review files and full Review draft restoration; invalid identities/capacity are rejected.
Test/admission locks remain, and runtime output authoring is unchanged pending review.
ARCH-002 keeps draft presentation/validation in a focused Review output helper and
header painting in one small shared module. Cameras/MCU/Projectors remain cohesive
page assemblies with only focused layout/class-selection anchors; size advisories do
not justify duplicating those responsibilities. Dynamic fields use live focus wrappers.

[Current commands, hashes, raw checks and captured controls](runtime-evidence-2026-10-16/review-terminal/device-polish/validation.json)
record21 focused passes, GUI Ruff/format171, Win32 mypy12, boundaries712/zero violations
and whitespace pass. Device/projector/table controls were captured at1440/1175/720;
Protocol/Tracking pages also rendered at1440/720. Representative full-page and direct
control views inspected; direct captures disable CRT/glow for clear boundaries.
Initial spacer, forward-reference/typing/test-import attempts were corrected; raw
resize callback failure is retained. [Prior style/selector evidence](runtime-evidence-2026-10-16/review-terminal/devices-previews/validation.json)
retains the repaired compact-selector height checks and dynamic focus coverage.
No full GUI/native Windows/DPI/hardware/rig pass or measured CRT comfort/cost is claimed.


Oct16 `review-device-layout-multipulse` / `review-mcu-input-editor` implement the
owner's staged review candidate under [G01](../docs/architecture/gui.md#g01).
Camera MCU wiring is now hidden and Test selected/Connect paired in both modes;
Review-only MCU Inputs and
Outputs follow the connection card. Inputs now uses the shared Outputs-style table
with Add input, editable names/pins, enable checkboxes and remove buttons. Empty
Inputs shows only Add input, with table/header hidden. Unfinished definitions survive
review draft/file save and restore; legacy input-free files restore empty. Review
files retain an explicit extension rejected by managed runtime. Phase/observer and
active device-operation gates disable edits; input Test remains disabled under
[A11](../docs/architecture/acquisition.md#a11)'s physical/serial/firmware deferral.

Review Synchronization retains per-face Frame/Pulse drafts; blank faces add no pulse,
partial edits preserve other complete patches, and mixed VSync selects every enabled
pulse face. A modeless four-screen local fixture repeats V22's sequence without
resetting on edits. Planning overlays and review persistence retain multiple patches;
legacy single-pulse files remain loadable. Runtime multi-pulse/input support,
physical rendering, pacing/evidence and rig testing await owner review and promotion.

ARCH-002 review keeps the new behavior in focused review layout, timing, file and
input owners, reusing existing table/pin/card components, rectangle parsing and marker
pattern; no dependency added. Shared large Cameras/Projectors/MCU modules retain only
cohesive assembly selection; their existing size advisories do not place new feature
logic there. Baseline review/runtime parity stays tested with staging disabled.
Current input/MCU/persistence/parity selection passes28; scoped Ruff/format7, Win32
mypy6, boundaries710/zero violations and whitespace pass. Empty/populated renders
were inspected; owning layout cases cover720/1280. Initial test-caption/import issues
were corrected. [Current input commands, hashes and renders](runtime-evidence-2026-10-16/review-mcu-inputs/validation.json).
The initial broader GUI run had520 passes and the separately tracked Protocol
card-height failure (321px versus<320); it predates this input refinement. Earlier
pulse/layout checks and their limits remain in the
[staging evidence](runtime-evidence-2026-10-16/review-device-layout/validation.json).
No physical input, Windows, optical or actual VSync acceptance is claimed.

Oct16 baseline `gui-review-runtime-parity`: [G01](../docs/architecture/gui.md#g01)
and [G02](../docs/architecture/gui.md#g02) already share page construction.
Extended the owning real-composition regression to compare visible control positions,
sizes and accessible identities across every page/device/projector/Tracking subtab
at 1280/720 pixels, plus Dashboard/Protocol/Tracking authoring and Stop gates across
all eight phases with and without control. Match camera selection explicitly; compare
semantic controls independently of Qt child creation order. Hardware actions retain
their connection/ownership prerequisites; no production change was required.
The focused offscreen parity/style selection passes six cases; GUI Ruff/format
checks pass161 files, boundaries check698 modules/zero violations and whitespace
checks pass. Existing cohesion advisories remain; no runtime dependencies/state or
source owners changed under ARCH-002. Validation uses HEAD0361484d plus the concurrent
dirty tree on macOS; native Windows/DPI, device execution and rig acceptance remain
separate. Initial expanded-test failures concerned child order, unmatched camera
selection and hardware-specific gates; corrected test setup/scope before the final run.

Oct15 photodiode placement now repeats V22 pulses while accepting live Frame/Pulse
edits. The preview uses a separate submission index and retains the existing
controller fences; see the [current checks and limits](visual_stimulus.md).

Oct15 `live-output-placement` extends the existing authenticated display-calibration
update envelope with a bounded strict output-space placement snapshot under
[G01](../docs/architecture/gui.md#g01)/[V01](../docs/architecture/visual_stimulus.md#v01).
Controller lease, diagnostic/generation/revision, original deadline and increasing
sequence fences are retained; no new controller state owner or command lifecycle
is introduced. The renderer validates complete placement against prepared outputs
and confirms after presentation. Current affected backend/controller362 and GUI52
checks pass, including authenticated placement forwarding/rejection; physical
acceptance remains separate. [Owning assessment/evidence](visual_stimulus.md).

Owner-requested no-Tracking launch is implemented under
[E08 revision173](../docs/architecture/system-contracts.md#e08). Normal launcher and
GUI wrapper accept `--no-tracking`; exactly that role is omitted for the application
lifetime. Ports, credentials, jobs, process descriptors and preview-consumer rings
follow one protected declaration. Contradictory/missing required identities reject;
Tracking-dependent Setup/diagnostics remain unavailable until a full restart.
Configured Tracking-camera preview/recording remains acquisition-owned. Default full
launch is unchanged. ARCH-002 review reuses focused launch/bootstrap helpers without
new dependencies or general optional-backend machinery. Sol6.1 reports1163 affected
owner tests passing (three skips/two native deselections), scoped Ruff/format/mypy and
boundary checks passing. Astra's final review finds nothing actionable. Native process inventories now confirm Tracking absent across controlled launches.
Short recorded trials and120s post-repair reuse pass. The owner stopped the900s retry;
AbortNow at883.852s left it Interrupted, with recording cleanup unconfirmed. The exact
generation's exit receipt confirms all owned processes absent; this does not confirm
recording closure. After the owner resumed testing, a fresh strict no-Tracking run
completes exactly 900 seconds with confirmed cleanup/reuse and all four video counts/
full decodes passing. Reviewed acquisition start/stop repairs pass 523 owner tests.
This is low-loss engineering acceptance: source accounting and remaining CFR repeats
are recorded in Acquisition; zero-loss and physical calibration are not established.
During the pause, original TOML/last configuration were restored and a separate runtime
blocked camera restoration. On resume the rig was idle; fresh configuration, GUI
calibration and camera baselines govern completed restoration: three saved files are
byte-exact, camera feature settings match with only PFS selector-cursor serialization
differences, all camera handles close and the final runtime inventory is empty.
Separate camera-lossless 60-second recording/count/decode and prepared-YUV fidelity
checks pass; source/CFR and fidelity limits remain explicit in Acquisition. Interrupted trial-log
latency and native rapid-Abort reuse remain open as recorded in [Acquisition](acquisition.md).
[Acquisition](acquisition.md) and [Visual Stimulus](visual_stimulus.md) own current
source fixes, failed-attempt assessment, measurements and limitations.
[Commands, attempts and source fingerprints](runtime-evidence-2026-10-15/open-loop-soak/no-tracking-implementation.json).

Oct15 synthetic encoder matrix31/31 cases passes external counts/full decodes,
with actual RTX2080Ti evidence; direct empty raw-input finalization also succeeds.
The [Visual Stimulus report](visual_stimulus.md) owns the workload and performance
limits; [Acquisition](acquisition.md) owns the empty-output capability assessment.

Oct15 projector-free rig verification under [E15](../docs/architecture/system-contracts.md#e15):
native Windows/rig selection25 passed/one symlink-privilege skip; actual Windows picker
selection22 passed with ordinary pytest plugins. Native layout/hover selection5 passed,
one failed because the trial card is326px against a less-than320px assertion; this is
not a confirmed clipping diagnosis. Broad native GUI execution was interrupted after
approximately two minutes without recorded progress; no full-suite pass is claimed.
Prepared native interpreter,90 contract cases,19 Tracking schemas and11 Visual Stimulus
schemas pass. Regenerated the sole stale prepared-trial JSON schema from its canonical
model, removing superseded calibration fields under G01/V15. Native wheel/source build
passes; native binaries and source GLBs are present, without standalone-install proof.

Real COM8 Connect reads protocol4/cephvr2_uno_4 without flashing. Four preview cycles
per enabled Behavior/Tracking camera pass start/stop/release; first-cycle viewers report
visible. An extra Behavior cycle completes, then its next Start is blocked by unknown
SDK-buffer discard accounting. Cause remains unverified; preserve the safety guard.
An exact owned idle-controller fault produces automatic containment and an all-owned-
processes-absent exit receipt; MCU claim release remains truthfully unconfirmed. Active
capture-loss injection did not run: rounded-time identity was safely refused first,
and retry capture was blocked by the reuse finding. Both baseline full camera PFS
snapshots and saved configuration bytes were verified restored after this generation.
SpikeGLX read-only SDK check times out at its saved endpoint; remote state is unknown.
[Dated commands, raw results and limits](runtime-evidence-2026-10-15/projector-free-rig/context.json). Owner defers live-camera Tracking diagnostics and requests leaving the separately opened GUI running; no takeover or shutdown was performed against it.

Git-sync integration (2026-10-15) preserves local pixel-size/offset calibration
under [G01](../docs/architecture/gui.md#g01)/[V15](../docs/architecture/visual_stimulus.md#v15)
and independent incoming camera, arena, appearance and scientific-evidence changes.
Owner explicitly approved this conflict resolution. Direct role-pin editing shares the
existing MCU draft and locks; identity-fenced contextual editing remains. Native display
adapter identity survives scaled desktop rectangles. Invalid existing drafts stay quiet
when mode changes are rejected; an otherwise valid creation with missing subject height
still reports the incoming action-time warning. ARCH-002 review keeps these operations
in their existing focused owners without added state, dependencies or processes.

Final local validation: 1,737 non-GUI tests pass (four skips, 26 native/rig deselections),
509 offscreen GUI tests pass, and the final Visual Stimulus rerun passes327/one deselected.
Ruff and format911 files, Win32 mypy791 sources, boundaries695 modules/zero violations,
114 architecture register entries, 1,575 Markdown targets/anchors, edited JSON/TOML and
whitespace checks pass. Existing cohesive-owner size advisories remain. Superseded
margin/keystone/seam tests follow the retained affine-calibration tests; the older plot-toggle
scenario is covered by the retained interactive-legend regression. Initial failed/partial
runs remain failures, not passes. No native Windows, hardware, optical or workload
acceptance is claimed. [Commands, parent revisions and source fingerprints](runtime-evidence-2026-10-15/git-sync/context.json).

Oct14 full working-tree review under [ARCH-002](../architecture.md#arch-002)
and [E15](../docs/architecture/system-contracts.md#e15) closes local validation:
1,670 backend tests pass (four skips, 26 native/rig deselections), 494 offscreen GUI
tests pass with pytest faulthandler disabled, and 90 contract tests pass. Ruff/format
(902 files), Windows-target mypy (782 files), dependencies, boundaries (686 modules,
zero violations), 114 architecture register entries and declaration/schema checks
pass. Existing cohesion advisories and native exception-hook acceptance remain open.
Review fixes planning preview ignoring G01's restored pixel offsets; preview/export
bounds now agree and reject unresolved/out-of-bounds offsets. A regression fails
before the fix and passes afterward. Corrected accidental projector fields in a
Tracking test fixture, the stale 125 ms acquisition expectation, and a removed
demo-manifest report link. The configuration-confirmation test bridge now respects
the original RPC deadline instead of waiting indefinitely; production timing and
assertions are unchanged. No additional actionable source finding was confirmed
within the reviewed changes. Existing TODO findings/deferrals remain unresolved.

The final Windows wheel and source distribution build successfully; all 57 isolated
Protobuf outputs match source bindings. The source distribution includes both
calibration GLBs and excludes removed modules/demo assets. The wheel contains native
binaries but no repository calibration assets; standalone installation/runtime
acceptance is not established by this build. Initial sandbox suites stalled on
asyncio entry and default-temp packaging failed; permitted loopback tests and an
external writable build temp completed. No device command, flash, projector launch,
application restart or scientific acceptance occurred. Disposable build/cache files
are removed; existing uncommitted changes and dated evidence remain.
[Commands, failures, final results and provenance](runtime-evidence-2026-10-14/working-tree-validation/summary.json).

Oct14 `projection-calibration-window-controls` completes the owner's refinement under
[G01 revision204](../docs/architecture/gui.md#g01) and
[V15 revision20](../docs/architecture/visual_stimulus.md#v15). Screen names are smaller,
centered and use contiguous glyph cells. The table has no arrow buttons and adds
separate whole-pixel Offset X/Y columns (positive right/up, blank zero). Interactive
sizes cap at native resolution; offsets cap at remaining image margins and reclamp
when a size grows. Numeric8/full11/review6 persist pixel offsets while older removed
offsets remain discarded. Preview and published affine assets share translated bounds.
Diagnostic assets/views cover the full measured native raster, so expansion reveals
additional fixed-pitch, world-phase grid lines. Diagnostic plane isolation prevents
expanded grids occluding other faces; trial drawing disables that filter.

ARCH-002 reuses the pure extent owner, existing affine mapping, Qt entries, GLB
builder and arena shader/drawer; no dependency, wire field, process, deadline,
policy setting or whole-runtime reference is added. Projectors remains a cohesive
composition owner and delegates bounds/files/geometry. Owning GUI26 and persistence11
checks pass; renderer73 pass. Ruff/format157, Win32 mypy155 and boundaries686/zero
violations pass, with existing size advisories. The730px offscreen table was inspected;
no native restart/projector/optical/full-workload acceptance is claimed. Reopen the
application to load the code and launch projection calibration to regenerate its grid.
[Commands, XML, preview and provenance](runtime-evidence-2026-10-14/window-controls/context.json).
Broader GUI/calibration attempts stalled and were interrupted; no full-suite pass.
Stale version/extent assertions, numeric8 file routing and static findings were repaired.
A failed Windows encoding write emptied the GUI architecture page; its complete
pre-existing content was restored byte-exact from the Codex pre-edit snapshot before
these focused amendments. Remaining physical checks stay in
[rig verification](rig-verification.md).

Oct14 repository cleanup under [ARCH-002](../architecture.md#arch-002) removes
766 lines from the retired BatchEdit/EpochTargets, ScreenScope and
StimulusSelectionMenu branches, unused ProjectorLayers state wrapper and shuffle
helper. Source/import searches find no current callers; the unified G01 editor and
shared/tested authoring helpers remain. No dependency, state, contract or behavior
was added. Removed disposable pytest fixtures, bytecode/tool caches and build
outputs; root pytest scratch directories are now ignored. Existing changes,
calibration assets, native/generated sources, environment, recordings, recovery
outputs, toolchain and dated evidence are retained. Owning editor tests pass
12 cases; Ruff, scoped format/Win32 mypy and boundaries pass (686 modules, zero
violations; existing cohesion advisories remain). Broader GUI/client attempts were
interrupted after no progress; fixture-location attempts failed before the final
external-scratch run. No full-suite or rig pass is claimed.
[Commands, counts and provenance](runtime-evidence-2026-10-14/repo-cleanup.txt).

Oct14 rig audit measured queue17 with20% burst margin. Owner subsequently selects queue20, SDK15 per camera and150ms drain allowance; apply through idle Controller UpdateConfiguration/SaveConfigurationHistory and owning TOML. Current/live/saved values match, other current fields are preserved and the open application remains running. New values are not native retested. Original visual TOML remains unchanged. Combined three-camera and dedicated Save Off trials complete/clean/restore and independently decode. Four preview cycles per camera pass; normal ShutdownApplication succeeds with exact all-owned absence. Current regression selections1540 backend passes/five skips and494 GUI passes; Ruff, format906, Win32 mypy786 and boundaries690/zero violations pass. An earlier authenticated timeout passes isolated and final selection; cause unproven. Native layout9/hover2 pass, but full native GUI exception-hook stall/manual DPI acceptance remain open. E05/E06/E08 fixes cover aggregate cleanup, stopped-trial pulse proof and bounded warning scope (E03 revision35); native full cancellation/Abort/idle-reuse checks await projectors. Tracking processing, photodiode and physical paired mappings remain owner-deferred. [Assessment](runtime-evidence-2026-10-14/rig-timing-audit/configuration-assessment.json).

ARCH-002 review removes duplicate selection, reusing the existing focused pulse
owner and camera-role registry; no new state, dependency, process or whole-runtime
reference. The preview orchestration owner is now656 lines and already delegates
start, pulse lifecycle, evidence and transfers. Existing behavior modules cover
all three roles' real resolver/confirmation, start/existing selection across
free/external timing and stopped/running states, plus test-only registry discovery.
Final follow-up local tests: 174 passed, one Windows test deselected across camera
configuration, handoffs, manual preview and manual devices. Scoped Ruff lint and
format (three files), Win32 mypy (two changed sources), boundaries (690 modules,
zero violations with existing size advisories) and whitespace pass.
[Dated evidence](runtime-evidence-2026-10-14/eye-readback/context.json) retains
before/final XML and failed intermediate test attempts. The
[registry follow-up evidence](runtime-evidence-2026-10-14/registry-preview/context.json)
retains an initial existing integration timeout (173 pass/one failure); isolated
recheck and final selection pass without assertion changes, cause unverified.
Additional physical roles still require schema/device/firmware support.
Runtime not restarted;
no camera/MCU command or optical/electrical acceptance performed. Full application
restart is required to load backend changes; [rig checks](rig-verification.md)
remain pending.

Oct14 `mcu-test-console-polling` completed under
[A11](../docs/architecture/acquisition.md#a11) and
[G01](../docs/architecture/gui.md#g01). Owner reports repeated HIGH/count/warning
and command-completion messages after Test. Source review identifies diagnostic
status polling, not repeated START: the existing 500ms polls renew A11's firmware
lease. Retain those polls and live HUD counts; console reports active signal changes
and stop results, while successful routine STATUS completions are quiet in both
device and dashboard consoles. Start/Stop/connection/upload results and failures
remain visible. No serial protocol, lease, timing or output behavior changes.

ARCH-002 uses the existing focused MCU owner for pending command kind and existing
panel/result routing; no dependency/process/helper or whole-runtime reference.
Existing main/panel size warnings reflect composition and presentation ownership;
this patch adds no separable responsibility. Extend the owning dashboard behavior
test: seven polls remain quiet, one START, camera counts refresh, Stop and failed
STATUS remain visible. Offscreen pytest selection
`managed_mcu_pending_completion_and_final_status or successful_tracking_frame_poll`
passes 2 cases/488 deselections. Broader `mcu or microcontroller or
successful_tracking_frame_poll` collection fails twice because concurrently edited
`src/cephvr/gui/projector_calibration.py` is zero bytes and cannot export
`CalibrationTable`; no broader pass claimed or unrelated edit repaired.
Ruff/format (four files), Win32 mypy (three source files), boundaries (690 modules,
zero violations with existing cohesion warnings) and whitespace pass. Initial
import-order/format findings corrected. Reopen the GUI to load this change; no
native GUI restart, hardware command or physical acceptance performed. Existing
[rig checks](rig-verification.md) remain pending.

Oct14 `projection-integer-physical-views` completed under
[G01 revision203](../docs/architecture/gui.md#g01),
[V14](../docs/architecture/visual_stimulus.md#v14) and
[V15 revision19](../docs/architecture/visual_stimulus.md#v15).
Width/Height are integer pixel entries with visible arrows and Up/Down one-pixel
steps. Remove Offset. Numeric7/full10/review5 migrate older offsets/fractional valid
sizes while retaining reference measurements, native modes, inversions and distances.
The centered usable view dimensions equal valid pixels times independent measured
X/Y mm/pixel. Preserve the frame-placed physical plane center, observer and axes;
measured physical dimensions retain the 5 mm gap placement reference. Preview,
calibration export and prepared affine mappings share the focused extent helper.
Prepared GUI affine surface textures use valid pixel resolution, keeping V14
physical texture sizes/frequencies and shared phase independent of projector resolution.
Live diagnostics retain the protected scene and fixed pitch while changing crop bounds;
fresh preparation publishes usable physical views. Imported warps/targets retain
original geometry/resolution. Raw reference frames/bars bypass stale measurements/crops.

ARCH-002 adds only a focused pure extent owner; reuse Qt and existing projection,
texture-coordinate and resource builders. No dependencies, wire/policy fields,
process/state machine, deadlines or ownership changes. Existing Projectors and
scene-resource size advisories are cohesive composition/allocation owners; physical
extent arithmetic stays in the helper. Current checks: owning GUI48 pass/445
excluded; rendering/config82 pass including real builder allocation with fake GL
contexts. Cross-projector proof uses different native resolutions and anisotropic
pitches: equal usable mm dimensions give equal physical corners/off-axis matrices,
and 20×10 mm texture spans retain physical size. Migration, arrow-click, integer
rejection, preview/export, fixed-pitch live sequence and imported asset preservation
checks pass. Ruff, format160, Win32 mypy158 and boundaries690/zero violations pass.
Projection numeric settings are unchanged: resulting extents are bounded by native
raster and measured pitch; current tests remain within near1/far250 and existing
tolerances. Hardware geometry changes still require V15's owner-approved limits review.

Initial unconfigured Qt runs fail without diagnostics; explicit offscreen mode fixes
local execution. A broader calibration selection stalls in restricted integration,
is interrupted, and is replaced by the focused owner checks. During implementation,
UTF-8 handling, an overly broad numeric restore conversion, obsolete version/offset
fixtures, strict JSON tuple validation and fake-resource cleanup field were corrected.
No native renderer restart, projector alignment, optical/scientific or full-workload
acceptance is claimed. Reopen the application to load changes; retain outstanding
[rig verification](rig-verification.md).
[Commands/scope](runtime-evidence-2026-10-14/integer-views/context.json) and XML evidence.
Previous pixel-crop evidence remains [here](runtime-evidence-2026-10-14/valid-area/context.json).

Oct14 `reference-calibration-output-frame` completed under
[G01 revision200](../docs/architecture/gui.md#g01) and
[V01 revision21](../docs/architecture/visual_stimulus.md#v01). Reference calibration
now shows a white native output-boundary frame and unchanged colored raw-pixel bars.
The initial frame needs only output resolution; it supports aiming/focus/rough
positioning and cannot claim a measured physical screen boundary. Align the raw
projection, measure bars, close it, then launch the measured physical frame/grid
for existing Scale/Offset refinement. No screen dimensions/measurements/corrections
or clipping values are changed by this step.

ARCH-002 reuses one focused four-rectangle helper in the native drawer and GLB
exporter; no dependencies, protocol fields, resources, policy or state additions.
Frame draws before colored bars, so intersections preserve exact configured bar
pixel spans; scissor restoration, native copy, protected lengths/digests, authority
and cleanup remain. Source GLB now contains four frame edges plus two bars per output.
Final rendering/resource71 and owning GUI15 pass/467 deselections. Ruff/format6,
Win32 mypy3 and boundaries689/zero violations pass with unchanged size advisories.
Initial70-pass/one-failure result exposes obsolete8-vertex asset assertion; update
it to24vertices and the bar slices, preserving length/cleanup assertions. Final71 pass.
No runtime/device/native/optical acceptance. A normal application restart loads the
renderer change, and reference launch regenerates its source. Physical alignment
remains in the [rig checklist](rig-verification.md).
[Commands, limits and test XML](runtime-evidence-2026-10-14/reference-frame/context.json).

Oct14 `updated-tank-screen-plot` completed [gui] [visual_stimulus]: production
corner geometry plotted with updated5mm gaps and Bottom126×94 image axes.
Retained side distances imply4mm lateral clearance; measurement reconciliation
remains open. No settings/runtime/device change. See the
[plot assessment](visual_stimulus.md) and
[3D/top/side figure](runtime-evidence-2026-10-14/tank-screen-plot/tank-screens.png).

Oct14 `clean-calibration-grid-bottom-fit` software correction completed under
[G01 revision199](../docs/architecture/gui.md#g01),
[V15 revision17](../docs/architecture/visual_stimulus.md#v15) and E14 revision210.
The grid remains solid neutral lines, a white border and one screen name. Owner
confirms 5 mm frame gaps at both front and lower junctions: Side/Bottom front edges
start behind Front; Front/side lower edges start above Bottom. Preserve perpendicular
subject distances and physical heights. Bottom image X/width126mm follows +rig Y;
Y/height94mm follows -rig X, preserving the 94×126mm tank footprint with corrected
image axes. The earlier on-disk Bottom width94/height126 caused image X to target
94mm instead of126mm. This resolves the source axis mismatch; actual optical
coverage is still pending, not inferred from arithmetic.

Numeric5/full8/review3 swap legacy Bottom width/height only, preserving raw native
bar measurements, extra scales/offsets/inversions and imported runtime profiles.
GUI fixed policy/config version6 declares the 5mm gap. All consumers reuse the shared
corner helper; ARCH-002 needs no dependency/state/process/module extraction. Final
owning GUI38 passes/444 deselections, plus2 focused passes after exact126/94 neutral
mapping and legacy-review migration assertions. Ruff/format7, Win32 mypy6 and
boundaries689/zero violations pass, with existing unrelated size advisories; TOML
syntax/version/binding and documentation references/whitespace pass. Initial legacy
affine/mirror-fixture failures and one static version comparison are corrected;
source geometry changes require the mirror tests' new clearances, retaining all
complete/partial/impossible-path scenarios.

Retain V15 clipping/tolerances after reviewing the orthonormal axes and 5mm gap;
no numeric change is needed for the supplied physical planes. Extra saved X/Y
multipliers remain operator adjustments. Reopen the GUI to migrate drafts and launch
projection calibration to regenerate the clean grid. No stored measurement edit,
runtime restart, device/output command or native/optical/full-workload acceptance.
Existing [rig checks](rig-verification.md) retain physical coverage verification.
[Correction evidence and commands](runtime-evidence-2026-10-14/frame-gaps/context.json).
The [earlier artifact assessment](runtime-evidence-2026-10-14/clean-grid/context.json)
records the old axis assumption and remains historical evidence, superseded by the
owner's126mm image-width/94mm image-height clarification.

Oct14 `calibration-close-button-and-distance-format` completed under
[G01 revision197](../docs/architecture/gui.md#g01). Derived projector distances now
show exactly one decimal millimetre, eliminating float-tail display artifacts;
reference inputs, mm/px and measured base mapping precision remain unchanged.
Confirmed reference bars display Close on their own button and disable projection
launch; confirmed frame/grid displays Close on projection launch and disables
reference launch. The corresponding action emits the existing close request;
wrong-step direct calls and pending/unavailable states emit nothing. Unknown active
view retains the existing projection Close fallback. Labels remain confirmation-driven.

ARCH-002 retains focused measurement formatting and calibration action owners,
without new state/dependency/process. Owning GUI selection13 passes/467 deselections,
including precision/roundtrip, both Close routes, pending guards, live editing and
measured affine mappings. Initial selection5 passes/one stale old-button assertion;
update the owning expectation and correct formatting. Ruff/format3, Win32 mypy2,
boundaries689/zero violations and whitespace pass. No native GUI restart/output
command or optical acceptance in this increment; reopen the GUI to load changes.
[Evidence](runtime-evidence-2026-10-14/calibration-controls/context.json).

Oct14 `bottom-attached-screen-elevation` completed under
[G01 revision196](../docs/architecture/gui.md#g01) and
[V15 revision16](../docs/architecture/visual_stimulus.md#v15). Replace tank-height
centering of Front/Left/Right with lower edges at subject Z minus Bottom-screen
distance. Preserve physical screen heights; shared corner construction now passes
Bottom distance through diagram, trial preview, saved calibration/GLB export and
prepared geometry. Missing/nonpositive/nonfinite Bottom distance invalidates all
planes rather than retaining detached wall geometry. Saved drafts gain no fields.

ARCH-002 reuses the focused geometry helper and existing owning behavior tests,
without new state, dependencies, runtime references or extraction needs. Final local
GUI selection25 passes/455 deselections; scoped Ruff/format5, Win32 mypy4 and
boundaries689/zero violations pass. Existing oversized-module advisories are unchanged;
all four edited source modules remain cohesive focused responsibilities. Initial
8-pass/2-failure run exposed test-fixture migration needs (full versus numeric
snapshot, missing Bottom distance); repair fixtures, intermediate20 and final25 pass.
Initial format finding corrected. Retain current V15 clipping/tolerances: no new
measured dimensions/scene depth justify a numeric adjustment, and planar attachment
does not change orthogonality. No runtime restart/device/native/optical acceptance;
reopen the GUI to load this fix. Existing [rig checks](rig-verification.md) remain.
[Local command/results and test XML](runtime-evidence-2026-10-14/screen-elevation/context.json).

Historical measured-base fit evidence used extra Scale multipliers; that rule is
superseded by G01's pixel valid-area crop. The original
[measured-base evidence](runtime-evidence-2026-10-14/measured-base-scale/context.json)
retains its dated measurements, tests and limits.

Oct14 `projector-cursor-stability` completed under
[G01 revision194](../docs/architecture/gui.md#g01). Shared native projector window
configuration disables GLFW fullscreen cursor centering on every creation/recreation;
controller ownership and lifecycle guarantees remain unchanged. Rendering/calibration
tests71 pass; scoped static checks and boundaries pass. Native GUI launch, Close and
reopen preserve the exact clicked main-display coordinates, with authenticated
Active/presented → Idle/resources_closed → Active/presented status. Reference bars
remain open. The owner authorizes resuming the accidentally interrupted Computer Use
check; reopen the closed GUI in the current controller generation. See the owning
[Visual Stimulus assessment](visual_stimulus.md) and
[raw evidence](runtime-evidence-2026-10-14/projector-cursor/context.json) for commands,
attempts and limits. No optical/full-workload acceptance is claimed.

Oct14 `live-reference-measurements-and-tab` completed under
[G01 revision193](../docs/architecture/gui.md#g01). Measured X/Y mm fields now stay
editable with GUI editing authority during confirmed Active reference bars; retain
native pixel/mode provenance, rig/assignment/correction locks and protected inputs.
Edits update retained drafts/derived estimates without renderer updates or rewriting
active assets. Pending/unknown/closing and observer states remain locked; a pending
non-Active state now also locks the card. Frame/grid retains its original live
Scale/Offset controls. Shared DataTable's grid navigation trapped Tab on embedded
editors; disable that behavior to use Qt's normal widget traversal. Tab/Shift+Tab
moves between nested editors/combos/checkboxes and skips disabled fields; inventory
arrow selection remains native. Console, log-details and example text views release
Tab for navigation. Incomplete imported display profiles no longer raise a pre-existing
KeyError when adding file-owned projection limits; retain partial drafts while Setup
still validates complete geometry.

ARCH-002 reuses existing measurement drafts/refresh, shared Qt controls and owning
behavior tests; no global event filter, dependency, process or extra state. Existing
large Projectors code remains focused widget/view-lock composition; no separable new
responsibility is added. Focused7 tests pass; final calibration/keyboard/table/measurement
selection34 pass/441 deselections, after initial33-pass/incomplete-import failure.
Scoped Ruff/format5, Win32 mypy4, boundaries689/zero violations, documentation references
and whitespace pass. Final fixture run emits Windows COM0x8001010d diagnostic but
continues/exit0 with34 passes; cause unverified. Correct initial Ruff line/zip findings.

Reopen the already-closed GUI in the existing runtime using --reopen-gui. Native
Active reference presentation and screenshots verify FrontX→FrontY→LeftX and reverse
Tab movement with measurement fields focused; scientific values are unchanged.
This native Active-case check precedes the final pending-only guard refinement;
pending/observer behavior is verified by the local regressions. GUI remains open
with reference bars Active. A transient DWM ghost is observed without inferring backend
failure; read-only controller status confirms current presentation. Existing optical/
full-workload limits remain in the [rig checklist](rig-verification.md).
[Evidence and native focus captures](runtime-evidence-2026-10-14/live-reference-tab/context.json).

Oct14 `reference-bars-visible-output` repaired and verified under
[V01](../docs/architecture/visual_stimulus.md#v01)/[V15](../docs/architecture/visual_stimulus.md#v15).
Reference bars were drawn into the device framebuffer without copying to the native
screen; the branch continued before the copy used by frame/grid. Actual Front output
was black. Copy that framebuffer to the current screen before returning; native-pixel
lengths, correction independence, existing swaps, ownership and cleanup remain.
ARCH-002 reuses the established framebuffer copy, with no dependency, process, state,
module proliferation or architecture-policy change. Extend the owning behavior test
to require each output copy after bar drawing; both bars cases fail before the fix,
and both grid cases pass. After repair, rendering16 and calibration rendering/lifecycle/
authenticated transport22 cases pass (37 deselections); scoped Ruff/format2, Win32
mypy1, boundaries689/zero violations and whitespace pass. Default sandbox temp fixtures
initially cause six errors/ten passes; workspace basetemp and permitted integration pass.

Native GUI testing through Computer Use confirms four visible orange/green bar outputs,
normal Close with authenticated Idle/resource-closure evidence, and successful reopen
with Active/presented evidence. Graceful ShutdownApplication succeeds after the prior
GUI has closed and resources are confirmed closed; restart through the managed launcher
loads the repair and restores the draft/control. Final controller80dfe14b-7d23-45b0-a46f-eaf77c024b62
is left running with reference calibration open for measurements. An input-observation
race/stale-window binding and one geometry-unavailable click require refresh/reselection;
no unknown UI input is retried blindly. Initial exact-color screenshot analysis rejects
lossy JPEG values; corrected approximate-color analysis confirms both colors, without
claiming exact framebuffer pixels or optical accuracy. Optical/full-workload checks
remain in the [rig checklist](rig-verification.md). The repository asset directory
still contains only the two requested GLBs. [Evidence, native captures and commands](runtime-evidence-2026-10-14/reference-bars/context.json).

Oct14 `projector-flip-deferred` completed locally under
[A11 revision46](../docs/architecture/acquisition.md#a11),
[G01 revision191](../docs/architecture/gui.md#g01) and E14 revision209.
Owner explicitly defers Projector flip input, its diagnostics and camera-trigger
offsets. Remove Inputs/Add input and new SpikeGLX flip source; retained hidden
legacy draft fields migrate enablement to false, preserve the pin and cannot emit
an activation/test command. Configuration and connection edits reject enabled
legacy input fields; serial-owner/diagnostic parser reject the kind before work.
Firmware removes input interrupt setup/cleanup and rejects the kind. V20's three
modes remain independent. Remove default D2 assignment; Microcontroller policy,
config and loader version3/digest agree and count only generated output transitions.
No firmware upload, device command or running-runtime restart occurred.

ARCH-002 reuses existing signal, validation, serial and firmware owners; delete
unsupported signal actions/interrupt work rather than adding alternate behavior.
Compatibility fields remain inert; existing panel/serial/device composition remains
cohesive with no dependency/process/runtime reference. Backend owner/protocol/config
122 pass/one existing skip; focused GUI11 pass; Ruff/format15 files, Win32 mypy11
sources and boundaries688/zero violations pass. Uno compile uses13590 flash/1199 RAM
bytes. Initial partial edit stopped before owner write due to an unmatched source
anchor; reread and completed it. Correct policy digest using Decimal parsing, stale
input-test expectations and a mypy variable-name collision. Sandbox backend and
broader GUI runs were interrupted on transport/modal stalls. Permitted broader GUI
also stalled; no broader pass claimed. Broader controller device admission14 pass/
three calibration-open/close failures in concurrently changing calibration workflow;
these are outside the MCU request path and remain with current calibration work.
[Commands/results](runtime-evidence-2026-10-14/projector-flip/context.json).
Output electrical acceptance stays in the [rig checklist](rig-verification.md);
Projector flip is explicitly deferred rather than a pending implementation test.

Oct14 `projection-config-only` completed locally under
[G01](../docs/architecture/gui.md#g01), [V15](../docs/architecture/visual_stimulus.md#v15)
and [E14](../docs/architecture/system-contracts.md#e14). Remove the four rig projection
editors and frontend draft persistence. `[projection]` in the owning Visual Stimulus
TOML supplies near 1 mm, far 250 mm, positional 0.000166 mm and orthogonality 0.000001.
Both calibration and experiment submission read that file; controller validation/startup
and worker Setup overlay its resolved snapshot before geometry validation. Missing or
invalid file values reject preparation. Imported numeric calibration/review drafts stay
loadable but cannot override these values; physical corners and other fields remain.
Regenerate the authoritative Protobuf bindings for the focused ProjectionLimits payload;
no policy value or policy_version changes. ARCH-002 removes the duplicate diagnostic
heuristic and reuses existing file/profile assembly, adding one focused pure validator,
no dependency/process/state. Existing large Projectors and worker lifecycle modules retain
composition and lifecycle ownership; no new independent responsibility is placed there.

GUI geometry/import/restoration/diagnostic 18 cases, configuration 9 cases, contracts 42
cases plus 79 subtests, worker lifecycle 34 cases and a controller startup overlay case pass.
Scoped Ruff/format and Win32 mypy 10 sources pass; boundaries 688 modules/zero violations
retain existing cohesion advisories; whitespace passes. Default sandbox temp fixtures fail;
repository-local basetemp works. Authenticated lifecycle tests stall under sandbox and are
interrupted; permitted loopback run passes. Initial fixtures lacked required projection
values and are updated, retaining rejection checks. Three transient admission failures
during concurrent two-step migration are corrected by the matching source/runtime
fixtures; the final55-case calibration selection passes and includes those scenarios. No running GUI restart, device command or
physical/optical acceptance performed. Existing rig checklist retains those boundaries.

Oct14 `projector-sync-modes` completed locally under
[G01 revision190](../docs/architecture/gui.md#g01),
[V20 revision9](../docs/architecture/visual_stimulus.md#v20) and E14 revision208.
Projection synchronization follows Rig geometry and Projection calibration (G01rev297). Remove its MCU summary,
editor and obsolete projector contextual-wiring path; Projector flip input/offsets
are now owner-deferred under A11 revision46. Offer Free run (no VSync), VSync on pulse
display, and VSync on all displays; migrate both old labels on portable/review draft
load. Existing file-owned pacing identity remains independent of pulse placement.
Free run requests zero swap interval on every output, including retained marker/pacer
outputs; it preserves V10 scheduling, V22 pulse controls and nominal recording-rate
validation. Canonical model, published schemas, codec and fixed policy agree;
Visual Stimulus policy/config/loader version12 and verified policy digest match.

ARCH-002 review removes redundant wiring and keeps mode mapping in ProjectorTiming,
presentation requests in DisplayProfile and existing GL owner binding. No new process,
dependency or runtime back-reference. Projectors remains composition of focused
helpers; native/configuration owners retain existing cohesive responsibilities.
Local GUI16, configuration/rendering61, lifecycle34 and contract42 cases pass
(79 contract subtests); scoped Ruff/format12 files, Win32 mypy10 sources,
boundaries687/zero violations and whitespace pass. Initial policy-version/digest and
new-test API mistakes were corrected; sandbox temp failures avoided with workspace
temp paths, stalled lifecycle transport run interrupted and permitted rerun passes.
No running GUI restart, physical output/device action or optical acceptance.
[Evidence and commands](runtime-evidence-2026-10-14/projector-sync/context.json).
Remaining V20 optical/driver/full-load checks stay in the [rig checklist](rig-verification.md).

Oct14 `gui-description-cleanup` completed locally under
[G01 revision189](../docs/architecture/gui.md#g01). Audit all GUI label constructors:
remove explanatory body text in protocol insertion/condition/expanded-example forms,
custom motion/looming editors, retained-review/Stop dialogs and empty Tracking
annotation. Useful instructions move to existing control tooltips. Keep functional
captions, units, generated counts, live frame identity, status/errors and operator
choices. The custom forms retain their controls/data paths; annotation captions show
only after a real reference/frozen source is installed. Earlier camera/projector
card removal is retained; concurrent synchronization cleanup already removed its
wiring summary, so preserve that independent change.

ARCH-002 deletes redundant widgets/update calls through existing focused owners;
no shared blanket QLabel hiding, dependency, process or runtime state. Existing
oversized parameter composition retains only one fewer orchestration call. Extend
no tests for reversible text removal; adapt the existing scope-tooltip assertion.
Owning regressions initially pass61/408 deselected with one asset fixture error:
the concurrently updated generator requires samples outside the checkout. Retry
only that case with ordinary external pytest temp: one pass/469 deselected. No
production behavior is weakened. Scoped Ruff/format11 files, Win32 mypy10 sources,
boundaries687/zero violations and whitespace pass. Initial source-edit attempt
finds the synchronization label already removed by concurrent work and stops before
code writes; re-read and continue with remaining owners. No GUI restart, device
command or native/rig acceptance. [Local evidence](runtime-evidence-2026-10-14/gui-descriptions/context.json).


Oct14 `two-step-calibration-assets` completed locally under
[G01](../docs/architecture/gui.md#g01), [V01](../docs/architecture/visual_stimulus.md#v01)
and [E07](../docs/architecture/experiment.md#e07). Exactly two files remain
in `assets/calibration/` (the extra README is removed): `reference_bars.glb` contains only two native-pixel bars per
output; `frame_grid.glb` contains the physical frame/grid for measured scale/offset
adjustment. Each launch refreshes only its selected file. Remove the five generated
repository JSONs and old shared grid filename. Generated profiles/mappings and exact
working copies live outside the repository in separate per-step user runtime roots.
GUI intent captures source/profile digests; controller rechecks the source, matching
profile view and staged copy before passing the runtime root to protected renderer
preparation. The reference file's pixel metadata must match the protected outputs;
reject wrong lengths/grid files, stale copies and wrong step references. Preserve
revision/authority/deadline/bounds, correction-independent bars, V15 frame/grid mapping,
exact source ownership and cleanup. No hardware command or live restart occurred.

ARCH-002 reuses the mesh packer, existing profiles and protected-source pipeline.
Extend the focused shared path helper; extract the controller's separable bounded
file reader into `device/calibration_inputs.py` before adding stage validation.
No dependency/process/runtime back-reference. Remaining controller calibration and
projector widget size advisories are cohesive command/state ownership and composition,
without new unrelated responsibilities. Extend owning test modules rather than adding
per-fix modules. Media outside calibration stays external; demo generator remains
external-only. Source distribution includes the two patterns; repository-less wheel
execution still rejects unavailable diagnostic sources.

Validation: focused `.venv/Scripts/python.exe -m pytest` controller admission, GUI and
calibration-rendering selection with `-m "not windows and not rig"`:55 pass/450
deselections. Covers independent exports, unchanged grid after reference export,
source/runtime byte identity, stale-copy rejection, exact reference quad pixel spans,
wrong-length/grid rejection and source cleanup. Scoped Ruff/format10 files, Win32
mypy7 sources, boundaries689/zero violations, actual two-file backend GLB parsing,
reference metadata/geometry consistency, source-manifest contents, local links/anchors
and whitespace pass. `python -m build --no-isolation` builds sdist/wheel. A transient
script insertion lookup fails before adding the new test; corrected and verified.
No application restart/native-output/optical/full-workload acceptance claimed; restart
before using the new path. [Current evidence](runtime-evidence-2026-10-14/calibration-assets/two-step-context.json),
[55-case results](runtime-evidence-2026-10-14/calibration-assets/two-step-tests.xml).

Oct14 `calibration-card-descriptions` completed locally under
[G01 revision188](../docs/architecture/gui.md#g01): remove description/prerequisite
labels from Pixel-to-mm and Screen calibration cards. ARCH-002 removes the now-unused
CalibrationPrerequisites class and refresh wiring; retain the shared no-projector
availability message and existing launch validation. No new state/dependency.
Standalone QApplication/ProjectorsPanel probe confirms descriptions absent and
reference launch button retained at index1. Scoped Ruff/format2 files, Win32 mypy2
sources, boundaries687/zero violations and whitespace pass. Initial import/format
findings corrected using repository Ruff configuration. No new test for this
reversible presentation removal; no running GUI restart/device/native acceptance.
Preserve concurrent calibration-asset and other GUI work.


Oct14 `device-card-and-signal-removal` completed locally under
[G01 revision187](../docs/architecture/gui.md#g01). Rename camera inventory to
Available cameras and remove the explanation below its buttons and unused summary
formatter; contextual wiring tooltips remain. Every MCU input/output supports Remove;
clear the pin, disable fixed Trial-state/Projector-flip signals, hide unassigned rows
and empty headers using DataTable's existing fit_rows. Add input/output offers missing
supported signals and asks for the explicit pin; fixed I/O readdition enables it.
Camera removal preserves Cameras' Use/role/source/rate and inventory. Enabled external
trigger cameras still require a valid pin under A10 (validation_pulse.py); removal
leaves an incomplete draft until reassigned rather than switching the timing source.
Snapshot format remains unchanged: empty pins represent absent assignments.

ARCH-002 review keeps presence/editing in the focused MicrocontrollerSignals helper,
removes obsolete camera explanation state, and reuses tables/configuration/authority
locks without dependencies, backend state or runtime references. Existing oversized
panel remains composition; separable signal behavior stays in its helper. Seven
owning GUI cases pass/461 deselected, covering remove/readd, all-empty headers,
snapshot restoration, unchanged camera choices and active-test editing locks.
Scoped Ruff/format5 files, Win32 mypy4 sources, boundaries687/zero violations and
whitespace pass. Existing no-faulthandler/loopback test allowance retained. No physical
device action or running GUI restart; native layout/device acceptance remains E15.
[Commands and local evidence](runtime-evidence-2026-10-14/signal-removal/context.json).


Oct14 GPU-selection launch repair under [SYS-002](../architecture.md#sys-002) and
[E08](../docs/architecture/system-contracts.md#e08) uses separate verified renderer
and GUI/CPU executable identities with per-image preferences applied/read back before
creation. Preserve native plans, PID/creation-time checks, Job Objects and deadlines;
actual GPU checks remain authoritative. AMD GUI/RTX5060Ti renderer hidden probes and
four-output native Idle startup pass; saved GUI draft restores/control is held.
The [Visual Stimulus assessment](visual_stimulus.md) records the485-case integration,
native provenance check, historical failure and acceptance limits. Encoding/OF bindings
remain unchanged; no global or other-application GPU preference is modified.

Oct14 `mcu-continuous-pin-test` is implemented locally under [G01 revision186](../docs/architecture/gui.md#g01) and [A11 revision45](../docs/architecture/acquisition.md#a11). Test requests duration_ms=0 and runs until explicit Stop. Matched DIAG_STATUS every500ms renews a two-second firmware communication lease without restarting pulses/resetting counts; expiry leaves outputs LOW/input detached and cannot revive on a late poll. Existing camera watchdog and authority/phase/shutdown cleanup remain. Firmware cephvr2_uno_4 accepts continuous and legacy2000ms requests; old firmware rejects without bounded fallback. No upload, serial/device command or runtime restart occurred.

ARCH-002 review reuses existing serial owner, firmware state and GUI timer, without dependencies/processes/runtime references. Existing owner/panel size advisories remain cohesive serial ownership/widget orchestration; no separable responsibility added. Controller/protocol105 passes/one skip; four existing GUI cases pass/464 deselected, including five-second active observation,500ms polling and manual Stop dispatch. Scoped Ruff/format6 files, Win32 mypy4 sources, boundaries687/zero violations and whitespace pass. Uno compile uses14038 flash/1219 RAM bytes. Sandbox asyncio tests stall and are interrupted; permitted focused tests pass. Broader GUI selection stalls after one dot and is interrupted; no broader pass claimed. Sandbox Arduino lacks core/index; permitted installed-core compile passes without upload. Physical sustained pulses/lease expiry remain in the [rig checklist](rig-verification.md). [Local evidence](runtime-evidence-2026-10-14/mcu-continuous/context.json).


Oct14 `projector-calibration-card-order` completed under
[G01 revision185](../docs/architecture/gui.md#g01): Pixel-to-mm calibration now
appears above the projection correction card in Devices/Projectors' Screen
calibration tab, matching the owner's workflow. ARCH-002 review uses only the
existing composition layout order; no extra module, dependency or state is needed
in the oversized Projectors composition owner. A local QApplication/ProjectorsPanel
probe confirms measurement/correction layout indices0/1. Scoped Ruff/format and
Win32 mypy for projectors.py pass; boundaries687/zero violations (existing cohesion
advisories) and whitespace pass. No managed GUI restart or physical calibration
acceptance ran; no new test is added for this reversible layout-only change.

Oct14 `projector-legend-visibility` completed locally under
[G01 revision184](../docs/architecture/gui.md#g01): Devices/Projectors removes the
four plot toggle buttons and their unused styling. Clicking Tank, Screens,
Projection or Subject in the legend toggles the corresponding view group.
Hidden entries remain dimmed and clickable, including without rig geometry;
wrapped hit regions retain their positions when groups are hidden. Projection
continues grouping projectors, rays, footprints and mirror. Visibility survives
refresh/phase changes without editing calibration or participation; legend clicks
do not start rotation. Plot dragging and double-click reset remain available.

ARCH-002 review removes redundant controls and keeps interaction/hit regions in
the existing focused TankDiagram owner, with no dependency or runtime reference.
The existing oversized Projectors composition module shrinks; its remaining
assignment/calibration orchestration stays with existing focused helpers.
Five owning GUI/geometry/rotation cases pass; scoped Ruff/format (four files),
Win32 mypy (three sources), boundaries687/zero violations and whitespace pass.
Initial wrapped-legend test fails because the parent layout overrides resize;
fix the test width constraint, then verify wrapped toggling/refresh/rotation.
GUI tests use the documented `-p no:faulthandler` limitation. No managed GUI
restart, device command or native visual acceptance is claimed.
[Commands and local evidence](runtime-evidence-2026-10-14/projector-legend/context.json).

Oct14 `projector-offline-drafts` under
[G01 revision183](../docs/architecture/gui.md#g01) and
[E07 revision62](../docs/architecture/experiment.md#e07): disconnected saved display
identities no longer reject GUI snapshot saving/restoration. Retain assignments,
participation, calibration and enabled authoring faces independently of live inventory.
Existing controller pure validation accepts structurally valid saved output properties
without device discovery; unknown physical properties are not invented. Empty inventory
shows the availability explanation in the diagram, device HUD and log, including the
turn-on/refresh prerequisite for projector tests/Setup. Managed Setup refreshes inventory
on click and logs the reason without collecting/submitting configuration or dispatching
Setup when none are found. Ordinary authority/phase gates and backend physical validation
remain intact; the Setup button is clickable with control in Configuration.

ARCH-002 review removes the erroneous live-inventory snapshot check and reuses existing
draft ownership, display discovery, command routing and focused prerequisite text owner.
The oversized main/projector modules add only orchestration/presentation wiring; no new
dependency, process, duplicate state or whole-runtime reference. Owning GUI regressions
pass23 cases; surrounding projector/calibration/Setup/full-GUI checks pass86 with the
existing narrow projector15px overflow failure. Loading unchanged HEAD projector/layout
modules in an isolated test process reproduces that same failure. Scoped Ruff/format6
files, Win32 mypy5 sources, boundaries687/zero violations and whitespace pass. Initial
sandbox asyncio setup stalls in socketpair accept and is interrupted; permitted tests
run normally. Initial test-only numeric normalization/button lookup/pacing-fixture
expectations are corrected before final23 passes, without changing production behavior
to satisfy them. Existing no-faulthandler/native-picker limitation remains.

The prior GUI was already closed; same-generation `--reopen-gui` opens current GUI
PID31324, responsive on Windows. Controller/session/backends remain intact. Projectors
are still on; physical power-off/save/Setup/reconnect acceptance remains in the
[rig checklist](rig-verification.md).
[Commands, provenance and results](runtime-evidence-2026-10-14/gui-refresh/projector-offline-context.json).

## Protocol group headings and arena Advanced settings

`protocol-group-and-arena-settings` is implemented under [G01](../docs/architecture/gui.md#g01)
revision191 and [V16](../docs/architecture/visual_stimulus.md#v16) revision5. Selected group
labels the timeline parameter row; group names sit above blocks, with repetitions/duration
inside. The longer footer label preserves a readable repetitions field at narrow widths.
Advanced settings put trial-owned wall limits first, followed by aligned Initial position
XYZ and Orientation yaw/pitch/roll sections with plain numeric inputs and no selectors.
All arena inputs share the same equal column stops: Movement limits aligns with Position,
wall clearance with Orientation; descriptive text spans both columns.
Imported condition values remain read-only references rather than being flattened. New arenas start at X/Y=0, with Z copied
from the configured subject height and zero orientation (forward, level horizon). Missing
subject height blocks new-arena creation. The mode switch validates this prerequisite
before changing active mode, preserving previous controls/selection and presenting an
action-time warning. This repairs the reproduced empty 3D row with erased error after
a failed height check. Later rig edits preserve existing authored poses.
These fields reuse the existing planar pose plus fixed height/pitch/roll model. Arena limits default to declared arena-file geometry and
30 mm clearance, preserve explicit saved regions/unrestricted mode, and participate in
snapshot restoration and Undo/Redo. Invalid clearance blocks navigation/save. The editor
shows declared asset bounds as a preview; protected preparation owns effective geometry.
See the [Visual Stimulus implementation assessment](visual_stimulus.md#arena-file-movement-regions)
and [native/rig worklist](rig-verification.md).

ARCH-002: initial-pose form assembly, trial boundary controls and bounded metadata access
are focused helpers; no new dependencies or process ownership. Existing cohesive source
warnings remain for canonical Protocol selection/history, timeline paint/input, parameter
binding and protected resource session ownership; geometry parsing/resolution lives outside
them. Extend owning dashboard/compiler/resource test modules rather than per-fix files.
Current mode-failure/default/gain checks: five owning cases pass. A pre-fix offscreen probe
reproduced 3D arena selected, no arena controls and an empty error string. The regression
verifies previous-mode/program preservation, a visible warning, successful retry with
configured height, asset chooser availability and returning to per-projector editing.
Scoped Ruff/format two files, Win32 mypy one source and boundaries696/zero violations pass.
The earlier aligned layout capture remains at
[aligned capture/context](runtime-evidence-2026-10-15/protocol-arena-settings/aligned-advanced-context.json).
Earlier group/region and aligned-pose evidence remains in the dated evidence directory and LOG.
No full GUI/native Windows/rig or production-shutdown acceptance is claimed.



## Post-hoc alignment readiness after always-saved evidence

Oct14 source/schema audit under [SYS-004](../architecture.md#sys-004),
[A09](../docs/architecture/acquisition.md#a09), [E12](../docs/architecture/synchronization.md#e12)
and [V22/V28](../docs/architecture/visual_stimulus.md#v22), accepting first matched
camera trigger = source of first recorded video frame. No post-change rig dataset
was validated; this is implementation evidence, not recorded-pulse proof.

Camera schema4 retains source IDs/host receipt/native counters and timestamps,
clock/counter descriptors, invalid/drop dispositions, explicit video-source mappings,
cutoff/pulse/transport/completion evidence independently of video. Stimulus format5
retains actual group state, per-output submissions/marker index+level, diagnostics,
feedback and completion with recipe identities/provenance. Paired SESSION_CONFIG
retains SpikeGLX run/directory, streams/rates/saved-channel indices and pulse mappings.

Eye inventory support is implemented under E12 revision21: additive enum7 and
`eye_tracking_camera` TOML/GUI mapping, including saved draft restoration and
SESSION_CONFIG serialization through the existing preparation. Paired Setup requires
Eye only when acquisition and Eye are enabled and externally triggered; missing,
non-OneBox or unsaved required mappings fail before run-name mutation. "Eye tracking"
is classified separately from Tracking in the GUI. No assigned channels, wiring,
trigger cadence, native counter semantics or acquisition settings changed.
ARCH-002 review: extend existing focused inventory/validation/panel modules and owning
behavior tests; no dependencies, new state or extra coordination. No fixed policy
values changed; the config addition is a commented operator mapping example only.
Local checks: controller/client suite490 passes with14 loopback setup errors from
sandbox socket restrictions; the authorized authenticated RPC rerun passes all15.
Final SpikeGLX tests35 pass (including nested Eye TOML editing), focused GUI tests13
pass/466 deselected. Protobuf generation19 sources, Ruff check/format15 files,
Win32 mypy13 source files and boundary check690 modules/zero violations pass.
Existing size warnings are outside the touched modules; no cohesion exception added.
An initial new-test helper import error was corrected before these passing runs.
Rig verification remains open in the [paired checklist](rig-verification.md).

Remaining concrete gaps:
- Checked-in synchronization pulse_inventory has no assigned channels. Supply actual
  stream/acquisition-channel/digital-bit mappings for the camera triggers, enabled
  photodiode and trial-state/projector-flip signals in use; do not copy legacy columns.
- No explicit shared-sync association binds OneBox to each probe. Retain original
  native bin/meta files, segment identities and actual common-waveform channel/bit
  semantics on both ends. Existing custom mappings/native metadata may carry pieces;
  CephVR does not require or verify the cross-stream relationship. Generic digital-bit
  validation covers DW, not SY words, so a SY-bit mapping is not currently representable
  through that validated path. Need actual rig sync inventory before selecting fields.
- Native camera descriptors allow unknown reset/wrap semantics and generic "frames"
  counter semantics; the first anchor does not prove recovery after missed triggers,
  dropped SDK frames or reset. Review retained timestamps/counter gaps; unresolved
  correspondence stays unresolved. No stronger anchor is requested.
- Photodiode markers are recorded, but periodic60-submission landmarks are not absolute
  IDs and held levels supply no internal edges. The measured output is the selected
  photodiode display; other displays have host submission evidence, not independently
  measured optical onset. These are timing/recovery limits, not missing source rows.

Trial-to-pulse-train selection and raw-file completeness remain compiler prerequisites;
no per-trial OneBox edge index is needed in the acquisition output when uniquely
recoverable from recorded gates/trains. Alignment tables, clock fits and quality labels
belong to the owner's future compiler. Tracking result files remain controlled by
save_tracking_data; enable it if complete locomotion histories are required.


Oct14 owner-requested repository cleanup under [ARCH-002](../architecture.md#arch-002)
removes423 files/254291141 bytes from the current tracked tree:136 images,260
captured-run dataset files,13 obsolete source/document-editing probes and14 other
build/run artifacts, including locally generated native DLLs. Original local files
and assessed evidence are preserved. Image/video ignore rules apply throughout the
repository; historical commits stay unchanged, as explicitly selected by the owner.
The [cleanup inventory](runtime-evidence-2026-10-14/repo-cleanup/context.json)
records original paths, sizes, SHA-256 hashes and local-only storage. Screenshots,
recording datasets, archived packages and old one-shot edits listed there require
local access; summaries, contracts, logs and substantive verification records stay
tracked. Existing screenshot/archive hyperlinks now identify local-only evidence.

The nine demo PNGs are generated on demand from a small standard-library tool and
source descriptors. The GUI/Visual Stimulus tests use one shared temporary fixture,
so a fresh checkout needs no checked-in images. No backend runtime code/state,
scientific policy, native C++ source or dependency is removed. The two native DLLs
remain on the rig; fresh checkout builds use the existing documented flags.
Six affected GUI/resource tests pass; full source/test/tool/script Ruff, Win32 mypy
for the two new helper/fixture files, and boundaries687/zero violations pass.
The no-isolation wheel/sdist build passes and archive inspection confirms neither
contains images/videos; the sdist includes the generator and four JSON descriptors.
Initial sandbox build fails on temporary-directory permission before the permitted
replacement succeeds. This is packaging/fixture validation, not rig acceptance.
Concurrent GUI-refresh work and its projector-availability finding are preserved.

Oct15 Review-only style experiment (`gui-retro-console-style`) under
[G02 revision47](../docs/architecture/gui.md#g02): Style → Standard / Retro console
switches the Review Dashboard and window chrome live, with a local appearance
preference. Green-black surfaces, blue borders/actions, muted red-orange card titles,
cyan page headings/field labels, restrained amber branding, pale green readouts/logs, cyan navigation/focus,
warm stop accents, unnumbered uppercase card headers, aligned HUD columns, square
controls/frames, bracketed status lamps and static faint terminal lines with edge
graduations use the shared theme. Periodic longer ticks extend to card edges;
Dashed section rules remain only inside the HUD; cyan corners mark focused inputs.
A segmented strip shows exact trial position when a count exists (up to24 visual
segments), without claiming completed trials. Lamp colors reflect the current view, with a
subtle halo; exact statuses remain in captions/tooltips. No embedded plots are added. Runtime retains
Standard without a style selector. Existing widgets, drafts (including invalid
unfinished values), actual log/status text, authority gates and experiment snapshots
are preserved. ARCH-002 review parameterizes the existing stylesheet and adds a
focused Review menu/preferences component, with no new dependency or runtime owner.
Existing source-size advisories are outside these small cohesive changes.
Seven focused appearance/theme/Standard-parity cases and eight log/HUD/navigation/
draft-retention cases pass offscreen; GUI Ruff/format163 files, Win32 mypy161 sources
and boundaries695 modules/zero violations pass. Wide1440 and narrow720 captures
are visually inspected; returning to Standard produces identical captured pixels.
[Dated method/results](runtime-evidence-2026-10-15/retro-console/context.json) retain
source hashes and the capture method; PNGs are local-only ignored evidence.
No native Windows or rig run. The owner explicitly limits the experiment to Review.
The current terminal-marking refinement (`gui-retro-terminal-markings`) passes ten
owning appearance/theme/HUD/Standard-parity cases (477 deselected), scoped
Ruff/format5 files, Win32 mypy4 sources and boundaries696/zero violations. Existing
appearance coverage verifies field/combo focus, mouse-transparent brackets,
continued typing, unchanged drafts/logs/gates, live statuses and hidden/zero/mid/last/
large-count trial positions. Standard restores and Runtime stays unchanged.
Wide/narrow, focused-input and active-trial captures are visually inspected;
Standard round-trip pixels match. ARCH-002 review extracts existing terminal
painting into a focused retro instrument module with the new static decorations,
editor-owned overlays and scalar-fed position widget; no new dependency, timer,
experiment state or test module. Shared components stay below500 lines; remaining
source cohesion advisories are pre-existing unrelated areas.
Fresh native Review launched through scripts/start_gui.py (session10674), retaining
earlier windows. Native accessibility verification remains unavailable for this
Python app; no native Windows/rig acceptance.
The main-card divider removal (`gui-retro-hud-only-divider`) deletes the unused
section-anchor plumbing. Scoped Ruff/format and Win32 mypy2 sources pass, with
boundaries696/zero violations; the wide render confirms no card divider and the
HUD rule retained. Standard round-trip pixels still match. No new tests for this
cosmetic removal. Fresh Review launched (session71475).
[Current capture evidence](runtime-evidence-2026-10-15/retro-console/hud-only-divider/context.json);
[earlier source/method/results](runtime-evidence-2026-10-15/retro-console/terminal-markings/context.json);
[earlier instrument detail evidence](runtime-evidence-2026-10-15/retro-console/instrument-details/context.json)
and [palette evidence](runtime-evidence-2026-10-15/retro-console/card-title-accent/context.json)
are historical.

Oct15 current Runtime/Review parity (`runtime-review-gui-current-parity`) under
[G01](../docs/architecture/gui.md#g01) and [ARCH-002](../architecture.md#arch-002):
both entry points resolve to this checkout and inherit the same DashboardWindow;
no separate layout or stale source copy was found. Extend the existing owning
parity regression through all five stimulus families with Advanced settings open,
comparing visible labels, editors, buttons and their positions/sizes, including
arena initial pose and movement limits. Preserve mode-specific menus, authority,
device discovery and separate local draft files. No production layout changes or
dependencies were needed; existing source-size advisories do not require extending
those modules. Validation on macOS with QT_QPA_PLATFORM=offscreen and
`-p no:faulthandler`: four wide/narrow, authority variants pass; twenty focused
camera pin/contextual wiring, group editor, arena limits, advanced-family and
runtime draft close/reopen cases pass. GUI Ruff/format and Win32 mypy (160 sources)
pass; boundaries check694 modules/zero violations. Tested the dirty working tree
based on `0d70295898bcb9f058ef4bf26df4680df62d595d`, retaining concurrent changes.
These are source/composition checks, not native Windows or rig acceptance. Existing
open processes were not refreshed; reopening each GUI loads the current source.

Oct14 rig GUI refresh (`runtime-gui-source-refresh`) under
[G01](../docs/architecture/gui.md#g01),
[E08](../docs/architecture/system-contracts.md#e08) and
[E15](../docs/architecture/system-contracts.md#e15): Review and Runtime already
inherit the same DashboardWindow; the rig editable install resolves this checkout.
Regenerated 19 Protobuf sources with no tracked binding changes and installed the
missing declared Pillow12.2.0 dependency. All20 declared runtime dependencies
match current requirements. Existing owning GUI checks pass14 cases, including
wide/narrow Review/Runtime parity, contextual wiring, managed editing and full-draft
close/reopen; launcher tests pass46. Boundaries687/zero violations. Initial sandbox
test attempt passes7 with7 temporary-directory fixture errors; the repository-local
temporary-directory rerun passes all14. The initial sandbox package install lacked
DNS; the permitted install succeeds. Tests use `-p no:faulthandler` for the GUI
under the previously recorded native exception-hook limitation; no full/native suite
or scientific acceptance is claimed.

Reopened the GUI through the existing launcher, then performed the owner's explicitly
approved full replacement through E08's exact owner event/exit-confirmation path.
The new controller16297497-8a48-4a38-866a-f21c52339bf2 and supervisor
575eb577-487e-4737-b768-3afa49d6c574 run current source with newly launched
acquisition, Visual Stimulus, Tracking and GUI. Authenticated status confirms
Configuration/revision1; Windows inspection confirms a responsive Dashboard.
Native UI inspection confirms the updated shared cards and compact retained review.
The initial unavailable-projector blocker is resolved after owner power-on:
all four saved DLP identities enumerate at60Hz. A further approved E08 replacement
starts controller87ca3771-29f3-41db-bfdc-31ec13491f0f; native GUI confirms saved
settings restored as a local draft, Control held and enabled Setup without startup
dialogs. Four renderer outputs report resources ready, applied revision1 and returned
Idle submissions without initialization issues. Leave runtime session73592 open;
no settings were reset and no experiment was started. This confirms restoration
and native initialization, not measured calibration or optical/full-workload acceptance.
[Power-on recovery evidence](runtime-evidence-2026-10-14/gui-refresh/projectors-on-context.json).
[Evidence/provenance](runtime-evidence-2026-10-14/gui-refresh/context.json)
retains test results and pre/post-replacement status; remaining acceptance stays in
the [rig checklist](rig-verification.md).

Oct13 sidebar cleanup under [G01 revision181](../docs/architecture/gui.md#g01)
removes the full-GUI Load/Save buttons. Snapshot/history ownership and per-page
file controls remain; restore errors no longer recommend the removed button.
ARCH-002 review keeps the change in window composition and its existing history
message. Offscreen visibility probe passes after selecting Protocol; initial probe
incorrectly checked a control on a hidden page. Scoped Ruff/format, Win32 mypy2
sources, boundaries683/zero violations and whitespace pass. Existing native preview
processes have not been restarted; no device or rig actions.

Oct15 `camera-inline-mcu-pin` implements the owner's inline pin field beside
Cameras' trigger frequency under [G01](../docs/architecture/gui.md#g01).
The Microcontroller role row remains the single draft owner: user edits, table
clearing, role/selection changes and MCU file restoration synchronize the displayed
pin. Unassigned cameras have no editable pin; capture, authority, phase and pending
MCU operation locks retain their existing scope. Pin edits retain Use and timing
choices and enter the existing MCU submission/save path. ARCH-002 review removes
the obsolete camera wiring dialog and its camera-specific stale-save branch;
existing camera/MCU presentation modules only add a field and refresh notifications,
with Devices owning synchronization. No new dependency, policy, schema or runtime
state owner; these cohesive presentation modules retain their existing size warnings.
Offscreen layout inspected at 1100×760: pin field sits beside rate without overflow.
Validation: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
 tests/gui/test_dashboard.py -q -p no:faulthandler -k "camera_pin or contextual_wiring
 or cancelled_projector_wiring or microcontroller or camera"` passes81/402 deselected.
Scoped Ruff check/format and Win32 mypy3 sources pass; boundary check690 modules/zero
violations and edited Markdown links/whitespace pass. Optional aggregate GUI run was
interrupted after focused completion and emitted a failure marker before exit134;
no aggregate pass or diagnosis is claimed. A sandbox restriction prevented process
listing for an earlier stop attempt; the owned tool session was interrupted directly.
Native Windows/device acceptance remains in the [rig checklist](rig-verification.md).

Device workflow refinement (`device-wiring-drafts`) under
[G01](../docs/architecture/gui.md#g01) and
[E07](../docs/architecture/experiment.md#e07) separates wiring from camera/display
participation. MCU owns logical Behavior/Tracking/Eye pin drafts independently of
inventory; the inline Cameras pin field and contextual Projector editor update that
same owner. MCU v3 files
and review v2 drafts preserve role wiring without changing Use, with explicit legacy
migration. Unfinished GUI settings survive polling; selected identity tests omit
PFS/import/capture, MCU connection checks submit only their port, and manual camera
preparation preserves participation and recording choices. Focused exact-diff
connection/selected-camera validators retain unrelated state, active conflict checks,
authority/revision/ownership guards and full Setup validation. Selected-camera
validation uses an action-only copy; actual stored Use/recording flags never change.
ARCH-002 keeps these validators, contextual editor and projector prerequisite hints
in focused helpers with existing owner interfaces and no new dependencies. Existing
large main/bridge, MCU panel and projector panel remain their respective composition,
command-routing and presentation owners; new validation/editor/hint logic is separate.
Aggregate review also corrected the compact group footer label so repetition fields
remain readable at narrow widths, without weakening the existing width assertion.
Root controller regression passes251 cases; acquisition manual-device/preview
regression passes101 with one platform/rig deselection. Scoped controller Ruff/format
and Win32 mypy5 sources pass. Final GUI aggregate passes463 with one obsolete
caption assertion; correcting that assertion gives four related layout passes,
covering the remaining case without further production changes. All464 GUI cases
are accounted for across those runs; an all-green aggregate rerun is not claimed.
GUI Ruff/format157 files and Win32 mypy156 sources pass; boundaries686/zero violations,
document links and whitespace pass. Luna implementation, Sol6.1 integration and
Astra main/final review find no remaining blocker. Initial migration/type failures,
stale assertions and their corrections remain with the [raw evidence and provenance](runtime-evidence-2026-10-13/device-wiring-drafts/context.json).
Offscreen production-widget layouts were inspected and the native Cocoa sample GUI
launched with isolated temporary settings (session71109, visible confirmation).
Native device/electrical/full-load checks remain in the [rig checklist](rig-verification.md).

Oct13 readable GUI messages (`gui-readable-runtime-messages`) under
[G02](../docs/architecture/gui.md#g02) and [E03](../docs/architecture/gui.md#e03):
automatic reconnect/launch review now excludes exact current completed/valid
nonfatal configuration notices and explicitly completed recoveries with completion
evidence and no failure. Errors, runtime incidents, pending choices, failed or
unknown terminal operations, unresolved recoveries and all other warnings still
require review. Ordinary pending commands, routine success history and truncation
alone do not trigger it; empty reconnects no longer force a review. Warning has no
severity field, so classification uses exact source evidence rather than keywords.
Full history remains available through Review controller history, with no added
control gate. An already-open important review remains fenced to its connection
until acknowledged, including when a later same-connection snapshot is empty.
Luna implementation, Sol integration and Astra final source review pass. Final18
focused review/history/control tests pass; scoped lint/format, Win32 types and
boundaries676/zero violations pass. The broader GUI run records461 passes and one
concurrent demo-texture failure: its already-loaded test tried decoding JSON as an
image while the texture chat changed the fixture/manifest. That case passes its
current-source rerun; no fresh complete-suite pass is claimed.
[Filter evidence](runtime-evidence-2026-10-13/readable-gui-messages/important-only/context.json)
retains both runs and their scope. The local sample preview confirms routine
history starts without an automatic dialog, with explicit buttons for history/important examples.

The themed, icon-free reconnect review groups retained errors, recoveries, incidents, pending
choices, warnings and operations needing attention. Routine successful operations
appear as a count; the 540×400 dialog uses bold accented category headings and a
vertically scrollable summary with only Copy details
and Continue. Copied plain-text details preserve exact command identities,
diagnostics and bounded-history omissions. Copy details
copies every currently retained error and operation, including entries beyond the
former routine-history display limit, from the latest snapshot.
Only Continue acknowledges the exact connection; copy and dismissal
do not acknowledge or send a controller command. Activity entries use readable action
names and concise outcomes, with exact diagnostics available through View details
and Copy details in the entry context menu. Admission remains explicitly pending
completion; acknowledgement identity, control authority and log retention/scroll
ownership stay unchanged. ARCH-002 review keeps formatting in the existing focused
snapshot/console owners without new dependencies or runtime back-references.
The larger main/bridge modules only route existing signals and outcomes; no new
state ownership is added. Tracked calibration, inventory, Tracking and control-release
operations no longer fall through to a contradictory generic success message;
successful Tracking frame polls stay quiet while completion handlers still run.
Duplicate MCU failure rows are removed. Luna implementation, Sol integration and
Astra source/screenshot review found no remaining blocker. Four themed offscreen
screenshots verify grouping, literal text and readable detail panes. A direct Qt
popup-interaction test crashed; the replacement render exercises the actual detail
constructor with popup selection substituted, so native mouse/keyboard input is
not claimed verified. The original log/grouping repair's offscreen GUI regression
passes452 tests; Ruff check
and format pass155 files, Win32-target mypy passes153 sources, and the boundary
check reports667 modules/zero violations with existing cohesion advisories.
Local links and whitespace pass. [Commands, provenance and screenshots](runtime-evidence-2026-10-13/readable-gui-messages/context.json)
retain the development-machine evidence. Native Windows/DPI appearance remains
part of the existing [rig checklist](rig-verification.md).
Final compact-dialog checks pass12 focused prompt, clipboard, markup-escaping,
vertical-overflow and acknowledgement cases; scoped lint/format, Win32 types and
the current boundary check676/zero violations pass. Sol/Astra review normal and
long-report screenshots, confirming the two-action footer remains reachable.
Snapshot-derived text is escaped before trusted heading styling; full copied
diagnostics remain literal. The refreshed macOS sample preview reports both dashboard and compact
dialog visible, with isolated settings and synthetic events.
[Compact-dialog evidence](runtime-evidence-2026-10-13/readable-gui-messages/dialog-compact/context.json)
records commands and scope; this is local presentation evidence, not rig acceptance.

Oct13 Git synchronization packaging: raw evidence videos remain at their original
local paths and are excluded from Git. The
[local video manifest](runtime-evidence-2026-10-13/local-video-manifest.json)
records71 files/10081381328 bytes with complete SHA-256 hashes. Remote checkouts
contain the manifest and associated reports/logs/metadata, but require a separate
copy of these video bytes for playback or independent decode. Original media and
the oversized unpushed commit are retained locally; no validation result changes.

Oct13 MCU pin diagnostic submission repair (`mcu-pin-test-submission`) under
[G01 revision174](../docs/architecture/gui.md#g01) and
[A11](../docs/architecture/acquisition.md#a11): authenticated read-only status of
controller04afb7ac-8774-4a0b-8380-41f21c6fca3f/revision1 confirms Eye requested60Hz
but no saved pin, disabled camera/free-running timing and no MCU observation.
The displayed pin9 is a local GUI draft. Loaded MCU drafts suppress immediate
pin saves; the former Test guard rejected the difference, followed by a misleading
"Requested ... through controller" message despite no test dispatch.
Explicit Test now submits only the selected diagnostic pin/rate and COM port,
checks exact controller acceptance, then targets that confirmed revision. Changed
bases, rejection or unconfirmed settings prevent the diagnostic; a later revision
change is rejected by the existing controller guard. Preserve other camera settings
and local drafts. Dispatch feedback comes from the managed binding.
ARCH-002 review uses a focused submission helper, existing configuration lock,
revision-adoption operation and owning behavior tests; no dependency, process,
firmware or whole-runtime reference is added. Existing large transport/panel owners
only route the focused operation and retain their responsibilities.
Final offscreen GUI30 cases and controller76 cases pass/one platform skip; Ruff
check/format155 files, Win32 mypy153 sources and boundaries668/zero violations
pass, with existing cohesion advisories. Sandboxed Qt/status attempts stalled and
were interrupted; permitted replacements pass. Initial import/type errors were
corrected. The running GUI is not restarted; native pin9/60Hz test, installed
protocol compatibility and physical reception remain unverified. No hardware or
firmware command was sent. [Commands/provenance/limits](runtime-evidence-2026-10-13/mcu-submission-context.json),
[GUI regression](runtime-evidence-2026-10-13/mcu-submission-verified.xml),
[controller regression](runtime-evidence-2026-10-13/mcu-submission-controller.xml),
[live read-only evidence](runtime-evidence-2026-10-13/mcu-submission-live.json).

Oct13 projector calibration retention investigation (`projector-calibration-retention`):
Oct14 owner screenshot still shows blank corrections/measurements. Read-only inspection
now finds `config/runtime_gui.json` last written Oct14 09:17:14 JST, with all16
scale/offset fields null, all four measured X/Y pairs null and tank geometry null;
stable role assignments and reference pixel dimensions remain present. SHA256
503c4d57079e51d2fb81cc405f996e80b394c0536caa22b6180cf145e277d7b4.
The saved file therefore explains the currently restored blanks, but not where earlier
entered values were lost. Review draft also has empty calibration; modes have separate
files. Owner says they will check again; no runtime/UI/configuration mutation or
additional tests performed. Actual prior entry/closure path remains unverified.

owner reports values missing after GUI closure. Under [G01](../docs/architecture/gui.md#g01),
current managed normal close saves the full GUI snapshot before controller-history
RPC; the snapshot includes all four screens' calibration fields. Read-only inspection
of `config/runtime_gui.json` found every scale/offset field null (file last written
Oct13 16:27:54 according to host filesystem metadata). The existing connected and
disconnected close/reopen regression passes2 cases; a separate offscreen GuiHistory
save/restore with explicit nonzero scale/offset values passes all16 fields. These
checks establish current source behavior, not the owner's previous running process
or closure path. Live diagnostic updates do not themselves persist GUI history;
normal close is the automatic save point. Actual closure method, restore warnings,
and prior values remain unknown; no production defect/root cause is established.
Process creation-time inspection via CIM was denied. No runtime/device/configuration
mutation occurred. Commands: `.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py
-q -k runtime_gui_close_reopen_preserves_full_draft --basetemp
.local-projector-retention-investigation` with offscreen Qt, plus isolated sample
windows using GuiHistory and a local JSON file. The generated roundtrip history is
[retained as evidence](runtime-evidence-2026-10-13/projector-retention-history.json)
after SHA-256-verified copying before temporary-fixture cleanup. No rig acceptance
is claimed.

Oct13 runtime Protocol group-control repair (`runtime-protocol-group-controls`):
source review confirms both frontends share `ProtocolEditor`, but controller and
saved schedules with direct root epochs hide the subgroup form and disable group
creation. Under [G01](../docs/architecture/gui.md#g01) revision173, these schedules
now receive one listed, once-only presentation group through the existing helper.
Untouched submission and schedule/single-program export preserve the original
source; actual program edits serialize the grouped form, and Undo back to the
initial program restores source export. Already grouped and mixed/nested programs
are retained. Standalone canonical imports keep their existing inspection path.
ARCH-002 review reuses the focused trial record, shared grouping helper, existing
page/snapshot operations and owning dashboard tests; no dependency, runtime owner
back-reference, device action or scientific default changes are needed. The focused
GUI regression suite passes50 cases, including managed source preservation,
saved-schedule restoration, subgroup edits/Undo and group/subgroup creation/reload.
Ruff check/format pass154 GUI/test files; Win32 mypy passes152 GUI sources;
boundaries check667 modules with zero violations and existing unrelated cohesive
size advisories. Whitespace passes. Initial pytest temporary-directory creation
fails for one fixture; rerun with repository-local basetemp passes. These are
offscreen checks; native Protocol control behavior remains visually unaccepted.
The runtime has since been restarted for the combined recording work below.
[Dated results and commands](runtime-evidence-2026-10-13/protocol-group-controls-context.json),
[test evidence](runtime-evidence-2026-10-13/protocol-group-controls.xml).

Oct13 combined recording/reset repair under [SYS-002](../architecture.md#sys-002),
[A07](../docs/architecture/acquisition.md#a07), [V12](../docs/architecture/visual_stimulus.md#v12)
and [E05](../docs/architecture/experiment.md#e05)/[E08](../docs/architecture/system-contracts.md#e08)/
[E11](../docs/architecture/experiment.md#e11) is verified in two
consecutive normal60s sessions in generation449c9382-c65d-4ed8-ae4e-393490ce9085.
Actual3602/3601 render groups give60.0333/60.0167 groups/s while Behavior30Hz and
Tracking60Hz record. Four samples per trial identify renderer23560 on RTX5060Ti/GPU0
and both camera plus review NVENC encoders on RTX2080Ti/GPU1. All six saved videos
externally count and fully CPU-decode; trial/output/metadata closure and reservation
release pass. Both NewSession/configuration restores succeed without shutdown.
The normal GUI is Configuration/no prompts, original full settings equal and cameras
released. All camera drain allowances remain the owner-selected125ms; Eye is disabled.

Reset repair acknowledges final coalesced warnings before Finished under A07
revision61, preserves exact pulse outcome retry identity, and retains canceled trial
health scope until cleanup. Shared absolute-clock waits correct early Windows async
wakes: a rejected lifecycle trace proves internal Stop3.38ms before normal end,
which the MCU channel correctly rejected. Preparation cleanup receipts now retire
only when all local source/consumer ownership has closed before a new preparation;
old resource-generation keys cannot enter the new cleanup catalogue. Strict evidence
checks and original deadlines remain intact.

The rendering repair moves native pixel work outside admission locking, uses bounded
native row conversion/completed PBO mapping and actual-context no-op checks, and
copies encoder input privately with a GIL-releasing native copy. No new dependency,
process, policy option or scientific/PFS/encoder tuning. CPU budget now covers retained
padding, readback/pipe copies and half-frame row scratch.1123 regressions pass,
3 skip/6 deselect; native Windows pipe14 pass. Ruff check/format, Win32 mypy427
sources, boundaries667/zero violations and whitespace pass. Existing large owners
remain cohesive: small context callbacks and preparation receipt/budget helpers do
not add whole-runtime references or a separable feature responsibility.

This verifies nominal60fps host cadence, not uniform16.67ms/optical timing. Repeat
median16.79ms, p9927.56ms/max37.88ms; camera queues drop6/19 frames and review captures
1176 real samples with2367 capacity drops,58 same-slot omissions and2424 identified
duplicates in3600 encoded frames. Full accounting remains explicit; recording is
not zero-loss. Eye/locomotion Tracking/paired/optical/electrical acceptance and the
dedicated Save On-to-Off verification remain open. Earlier failed attempts/recovery,
removed experiments and baseline39.47fps are retained in dated evidence.
[Dated raw evidence, verification and limits](runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)

Oct13 owner-authorized throughput implementation removes the measured float-to-byte
review readback stall and one intermediate host copy under V12/V20/E13. Recorded
four-output RGB8/all-VSync stimulus improves from30.13 real groups/s to60.0/s in
the final instrumented60s trial, with3600 real render groups and3600 encoded frames.
The review video still includes178 duplicates/12 capture drops/166 same-slot omissions;
full external decode, recipe digest, output closure, metadata sync and configuration
restoration pass. Native pixel comparison sees at most one8-bit rounding-code
difference in review pixels; physical rendering precision is unchanged. Final
uninstrumented confirmation also completes3600 groups/60s (60.0/s),3423 real captures,
177 duplicates,169 same-slot omissions and eight capacity drops, with normal
session/output cleanup, external decode/recipe verification and restored original
settings. The normal GUI/runtime is
left open in Configuration. The Save-Off comparison presents60.03groups/s
but reveals an existing Save-On→Save-Off cleanup failure (`cleanup returned an
unregistered resource`); exact full shutdown eventually passes. Keep that failure
separate from the throughput repair and the earlier failed-Setup cleanup link.
See [current implementation/limits](visual_stimulus.md) and
[raw timings/video verification](runtime-evidence-2026-10-13/throughput/).

Oct13 owner-authorized computer-level GPU placement is configured and verified.
NVIDIA Control Panel now explicitly binds the exact managed cephvr-python.exe
OpenGL program setting to RTX5060Ti; the fresh native four-output renderer verifies
its physical UUID/CUDA0 and exact release. Production camera encoder builders plus
actual generated-frame NVENC sessions verify RTX2080Ti/ordinal1 for all three
camera configurations. Fresh original Miniforge-base GUI launch confirms all four
Idle outputs without display issues; runtime remains open. No scientific/encoder
settings, firmware, camera or SpikeGLX commands are changed. This closes the current
adapter-selection task under SYS-002/V19/A08, without closing the separate native
camera or sustained throughput/optical tasks. No production source change is needed.
[Current setting, identities and execution evidence](runtime-evidence-2026-10-13/gpu-placement/context.json).

Oct13 fresh owner-requested workflow audit (`rig-workflow-failure-inventory`):
the current dirty working tree is tested through authenticated managed commands,
with real Behavior/Tracking cameras and four projectors. No production fixes,
firmware upload, scientific settings or wiring changes are made. The original
configuration is restored and final launcher evidence confirms all owned processes
absent. [Raw methods, snapshots and results](rig-evidence-2026-10-13/workflow-tests/).

| Workflow | Observed result | Remedy / next verification |
| --- | --- | --- |
| Camera connection and previews | Behavior40065509 and Tracking40747103 identity, capture/Show, visible preview and Stop pass; both devices closed, no cleanup pending. Earlier no-frame failure does not reproduce. Eye is disabled and untested. | Keep current settings; later exercise GUI selection, repeated reuse and native placement/DPI. Both previews report optional native timestamp unavailable; inspect SDK timestamp-frequency/chunk support before relying on device-clock diagnostics (A09), without inventing a clock conversion. |
| Normal projector calibration | Normal `calibration/diagnostic_display_profile.json` is rejected: mixed pacing requires an explicit pacing output. A separate diagnostic file made from the accepted current all-output-VSync profile passes Open, two grid updates, Close, Idle and resource closure. | Regenerate the normal diagnostic bundle from current accepted pacing/geometry and retest the ordinary GUI path. Do not change accepted V19/V20 pacing or treat dummy geometry as measured calibration. |
| Combined protocol and camera encoding | Setup fails before activation: `camera role 1 needs confirmed exposure/rate and drain policy`. Camera exposure/rate readback succeeds in preview; both file-only drain margins are unset. No camera video is recorded in this audit. | Establish the rig delivery/SDK bound and set each `cameras.<role>.post_cutoff_drain_margin_ms` under A10; it must cover exposure + delivery bound + one applied frame period. Behavior's exposure/frame-only floor is about58.34ms; Tracking's about21.67ms, before delivery allowance. Then repeat Setup and all-video closure. Do not guess the missing allowance or bypass validation. |
| Failed-Setup cleanup | CancelSetup cannot confirm cleanup; renderer exits after `ReportWorkerLifecycle: VISUAL_STIMULUS_EVIDENCE: cleanup command unknown` at coordinator `runtime.py:199`. Supervisor shuts down the application. Exact outer-Job absence is subsequently confirmed. | Trace the emitted cleanup operation against retained child-command links across Setup cancellation, prior closed calibration and supervisor cleanup. Repair the identity/lifetime mismatch with focused failed-Setup coverage under E06/E08; preserve original deadlines and truthful closure. Specific causality beyond the rejected link is unproven. |
| Stimulus presentation and encoding | Original audit renders30.33groups/s. The later measured capture repair reaches60.0 real groups/s in both final instrumented and normal60s recorded tests, with all outputs closed and settings restored. Normal run retains177 review duplicates/eight capture drops/169 same-slot omissions. | Main readback stall is repaired; retain explicit omissions and verify simultaneous camera/Tracking workload and optical timing. See the current [stimulus assessment](visual_stimulus.md) and [throughput evidence](runtime-evidence-2026-10-13/throughput/). |

The failed unstarted Setup leaves no `SESSION_CONFIG.json`; restart requires the
normal administrative recovery prompt. Exact test-session recovery succeeds,
preserving a recovery report and files. It emits an unknown-SpikeGLX-stop warning
despite this explicitly unpaired test; review recovery's unavailable-session-config
classification alongside cleanup. No remote SpikeGLX mutation occurred. A first
10s diagnostic is rejected by E05's60s minimum (probe error, corrected before the
recorded trial); one early restart declines while the old guard is held.

Normal final Shutdown succeeds and exact process absence is confirmed, but
acquisition's `_close` finalizer emits an uncaught `UNAVAILABLE` traceback when
its MCU Close RPC reaches the already departed controller. Review shutdown
ordering/expected authority-loss handling in `acquisition/main.py:277` and
`microcontroller_client.py:220`, preserving actual release evidence; normal exit
and a traceback-free teardown remain distinct checks. The saved reusable history
semantically equals the pre-test configuration; byte identity is not claimed.

Focused component tests pass213; owning GUI/offscreen calibration, preview and
protocol checks pass62/380 deselected. These and managed software observations
do not establish optical accuracy/photon timing, electrical pulse reception,
Eye, closed-loop Tracking, paired SpikeGLX or simultaneous full-load acceptance
(E15). [External video/cadence verification](rig-evidence-2026-10-13/workflow-tests/output-verification.json)
and [rig follow-up procedure](rig-verification.md) retain the boundaries.

Oct13 calibration export rejects the current version4 calibration snapshot after
successfully loading the owner's version3 portable projector file. The exporter
still gated versions2/3 although G01's loader already migrates calibration values
to4 (portable projector wrapper7). Extend the focused geometry exporter gate to
2/3/4 with exact integer versions; unsupported versions remain rejected. No schema,
geometry policy, calibration values or architecture decision changes are required.
ARCH-002 reuses the existing geometry helper and owning tests; no extraction or
dependency is needed, and existing cohesive source-size advisories are unchanged.

Eight geometry/profile/migration cases pass across versions2/3/4, including backend
GLB parsing and diagnostic bundle output. The owner's actual Desktop rig_cal.json
also loads in isolated Qt, yields calibration4/wrapper7 and exports a reference-bar
bundle parsed by the backend with four physical screen planes. Monitor bindings
in that check are synthetic; no native display, optical or live calibration pass
is claimed. The original file hash is preserved; initial evidence-helper failure
only omitted creation of its required existing Assets output directory and was
corrected. Ruff check/format2 files, Win32 mypy exporter, boundaries667/zero violations
and whitespace pass. No runtime restart or hardware/display command occurs.
[Owner-file method and provenance](runtime-evidence-2026-10-13/calibration-version-owner-file.json),
[regression cases](runtime-evidence-2026-10-13/calibration-version-tests.xml).

Oct13 owner reports prepare_camera rejection of canonical rising_edge as an
unadvertised TriggerActivation choice. The saved Eye PFS explicitly selects
FrameStart Off/Software, while the saved settings can retain the external edge
default. Canonical RisingEdge/rising_edge mapping already exists; fix applicability
in the GUI request owners under [G01 revision172](../docs/architecture/gui.md#g01)/A10.
Internal clock now clears TriggerActivation together with TriggerSource in both
camera-setting requests and loaded-proposal collection. External timing preserves
explicit edges, including FallingEdge; the adapter continues to reject unsupported
explicit feature requests. This avoids applying an inactive external control without
renaming saved canonical values, editing PFS/config files or weakening SDK checks.
ARCH-002 uses the two existing focused collectors, with no extraction or dependency
needed for this small refinement. Existing cohesive size advisories are unchanged.

Thirteen isolated GUI cases pass, including mocked reproduction of the exact
reported rejection, Test/Connect continuation, failure cleanup, loaded proposal and
explicit external-edge preservation. Forty adapter contract cases pass. Ruff
check/format153 files, Win32 mypy152 sources and boundaries667/zero violations pass.
No camera is opened, runtime restarted, MCU command sent or fresh SDK capability
read performed. Local reproduction and PFS source inspection explain the request
defect; physical post-fix acceptance remains pending.
[Source/provenance and checks](runtime-evidence-2026-10-13/internal-trigger-context.json).

Oct13 selected-camera Test/Connect now submits the current local camera parameters
automatically under [G01 revision171](../docs/architecture/gui.md#g01)/E03/E07/A10;
Setup is not needed. Capture the explicit camera identity, role, timing, PFS path,
rate and pin against the synchronized base; reject changed generation/configuration
before mutation. Reuse role assignment, camera-setting validation and SDK PFS
import/Finish editing, then issue the requested Test or Connect only after success.
Reassignment forces import of an explicitly selected PFS rather than trusting the
former device's baseline. External camera timing includes the selected COM port;
internal timing does not publish a unrelated local COM-port edit. Disconnect remains
an immediate cleanup command. Loaded PFS edits remain local until the requested action.

The chain uses the existing configuration dispatch lock, acknowledges confirmed
camera revisions including SDK/preview readback, and preserves unrelated dirty
page drafts and newer status views. A new focused submission helper owns the
separable preparation sequence under ARCH-002; transport/panel assembly stays with
existing owners, with no runtime back-reference, new process or dependency.
Existing cohesive size advisories for main/bridge/panels are retained and reviewed.
The affected Windows/offscreen suite passes87/347 deselected in29.17s; final focused
ordering/rejection/import-cleanup/draft preservation checks pass12/422 deselected
in1.53s. Ruff check/format153 files, Win32 mypy152 sources, boundaries667 modules/
zero violations and whitespace pass. Fake controller/SDK outcomes establish local
ordering, not physical camera acceptance. No live Test/Connect, restart, MCU pulse,
firmware or SpikeGLX command is performed.
[Current methods/provenance](runtime-evidence-2026-10-13/camera-action-context.json),
[focused cases](runtime-evidence-2026-10-13/camera-action-focused.xml),
[affected regression](runtime-evidence-2026-10-13/camera-action-broad.xml).

Oct13 live Eye selection investigation identifies a restored-draft defect under
[G01 revision169](../docs/architecture/gui.md#g01)/E03/E07. The running current-source
GUI accepts an immediate role command but retains the saved Unassigned draft;
that hides Eye from supported MCU outputs and the controller revision change
invalidates the draft. Keep role, participation and pin edits in a loaded draft
local until normal submission, updating camera rows and MCU choices together.
Retain immediate confirmed commands for configurations without loaded drafts and
the existing explicit SDK PFS import owner. Track local edits without projecting
controller state as edits; select Tracking by its exact role, excluding Eye tracking.
ARCH-002 reuses existing panel/snapshot/configuration owners and signals, with no
new process or dependency; existing cohesive panel size advisories remain reviewed.

The owning regression reproduces restored Unassigned selection, Eye assignment,
Add output pin entry, participation, poll preservation, file availability and zero
device commands. Final focused selection passes5/416 deselected; a broader permitted
Windows/offscreen run passes94 with one previously recorded projector horizontal
overflow failure (15px at1175px window width),326 deselected. The sandbox broad
attempt stalls at asyncio initialization and is interrupted before the permitted
rerun; initial temp-directory failure is resolved with workspace basetemp. Ruff
check/format, Win32 mypy151 sources and boundaries666/zero violations pass.
These isolated results do not establish live restart, native visual or electrical
acceptance. No runtime closed/restarted, firmware uploaded or device command sent.
[Read-only live state](runtime-evidence-2026-10-13/eye-selection-read.json),
[focused regression](runtime-evidence-2026-10-13/eye-selection-final.xml),
[broader regression](runtime-evidence-2026-10-13/eye-selection-broad.xml).

Oct13 owner screenshot corrects the earlier Explorer-picker completion claim:
revision168's nonmodal opener silently fell back to Qt widgets because the Windows
[file helper explicitly refuses nonmodal operation](https://github.com/qt/qtbase/blob/v6.11.2/src/plugins/platforms/windows/qwindowsdialoghelpers.cpp#L1378-L1391).
The prior21-case results establish widget cancellation only. Under
[G01 revision170](../docs/architecture/gui.md#g01)/E03, the focused shared opener now
queues native modal execution on a dialog-owned timer. Immediate rejection stops
startup; native execution stops Qt's helper timer. This is the minimal native
mechanism supported by existing PyQt6, replacing the earlier no-nested-chooser rule.
Filters, owner/path validation, stale-result fences and deferred deletion remain.
Windows shell proof verifies actual DirectUIHWND/NamespaceTreeControl controls for
Open, Save and folder modes with the real theme. Native GUI timers fire during
execution. Final regression passes23/400 deselected in16.43s, including40 rapid
pre/post-launch cancellations,12 immediate authority-loss cases and two started
authority-loss cases; started checks assert native WA_DontShowOnScreen to detect
fallback. Qt can emit rejection twice when closing the shell; callbacks remain safe.
Native pytest with the default faulthandler exits with0xC0000409; the same native
case with `-p no:faulthandler` and standalone themed repeated cancellation passes.
Cause remains unverified; record the exception-hook comparison without claiming a
default-native-suite pass. Local picker Ruff/format and Win32 mypy pass; broader
checks initially pass but final broad formatting/mypy find concurrent in-progress
camera/controller-bridge edits outside this change. Boundaries666/zero violations
retain existing cohesion advisories. No managed restart or hardware operation.
[Shell proof](runtime-evidence-2026-10-13/native-chooser/explorer-native-proof.log),
[final regression](runtime-evidence-2026-10-13/native-chooser/explorer-final-native.xml)
and [provenance](runtime-evidence-2026-10-13/native-chooser/explorer-corrected-context.json)
retain current validation scope; older widget evidence remains historical.

Oct13 per-tab configuration files are verified under
[G01](../docs/architecture/gui.md#g01)/E03/E07 without production changes.
The actual Save/Load buttons and nonmodal Qt widget dialogs round-trip Protocol,
Cameras, Microcontroller, Projectors, SpikeGLX, Tracking and full GUI JSON into fresh
matching-inventory windows. Three synthetic camera identities include Eye; MCU/full
files retain Eye pin8 and enabled Projector flip pin2. Loading emits no camera,
MCU/connection/firmware requests. Dashboard metadata uses the sidebar full-GUI file.
Extend the owning file behavior tests and Camera chooser authority-loss cases under
ARCH-002, without another test module or dependency. Nineteen button/chooser cases
pass; the broader Windows/offscreen file regression passes54/362 deselected in29.14s,
including malformed-file atomic rejection, failed-save destination preservation,
runtime/review retention and device/authority locks. Ruff check/format, boundaries666
modules/zero violations and whitespace pass; existing cohesion advisories unchanged.
These are isolated GUI/file checks, not native desktop visual or device acceptance.
[Methods and exact evidence](runtime-evidence-2026-10-13/tab-config-context.json).

Oct13 owner-authorized Eye trigger output is implemented under
[G01 revision167](../docs/architecture/gui.md#g01),
[A01 revision18](../docs/architecture/acquisition.md#a01) and
[A11 revision44](../docs/architecture/acquisition.md#a11). The GUI exposes an
assigned Eye camera trigger, retains numeric pins through MCU/full snapshots and
forwards its own diagnostic identity. Projector flip remains the supported passive
input through Add input; removal/Add/file restoration and authority locks are checked.
Managed Add collects an unset camera pin in a nonblocking dialog and atomically
submits pin plus participation, avoiding enablement rejection before a hidden pin
can be edited. Role/inventory or authority loss closes the dialog; existing revision,
dispatch lock and confirmed-state gates remain authoritative. Source/rate stay in
Cameras; no physical Eye assignment, pin or rate is inferred.

Protocol4 adds Eye configuration/state, grouped boundary masks/reservations,
diagnostics, SDK readback rate selection and all-output cleanup proof. Missing Eye
state never means stopped; protocol3 is rejected before testing and requires the
owner's manual upgrade. E14 Microcontroller policy/config are version2 with updated
digest; generated bindings come from the three owning proto sources. ARCH-002
reuses serial, operation and snapshot owners without another process, dependency
or independent pulse owner. Reviewed existing MCU/preview/cleanup coordinator size
advisories remain cohesive; only focused masks/projection/admission are extended.
Firmware uses the existing timer scheduler for three independent pins, validates
pairwise conflicts before mutation, bounds complete replies through Print counting
and leaves unassigned boot pins as inputs without pull-ups.

Local controller/acquisition suite passes834 (three privilege skips/two native
marker deselections); final readiness-focused rerun passes97. GUI/configuration
verification passes38 cases (369 deselected), including pin-first Add, rejected
oversized input and role/authority cancellation; final artifact provenance is in the
[evidence context](runtime-evidence-2026-10-13/eye-trigger-context.json).
Initial failures identify obsolete two-output fixtures, expected protocol versions,
the already owner-reassigned Trial pin, and an Add fixture with Trial state missing;
update fixtures without weakening required-state assertions. Ruff and Win32 mypy440
sources pass; boundary audit checks666 modules/zero violations. Firmware compiles
for Uno at13,922 flash bytes/1,214 global SRAM bytes (834 bytes remaining for locals).
No serial port, camera, pin test or upload runs. Manual installation, native GUI
inspection, electrical/timing/three-camera workload acceptance remain in the
[single rig checklist](rig-verification.md).

Oct13 FFmpeg compatibility repair completes the explicit owner-authorized tool
upgrade under [A08](../docs/architecture/acquisition.md#a08)/
[E13](../docs/architecture/visual_stimulus.md#e13)/[SYS-002](../architecture.md#sys-002).
A checksum-verified Gyan release supplies matched FFmpeg/ffprobe 9.0.2; the active
PATH directory keeps its historical `ffmpeg-4.3.2-2021` name, but its two executables
are now 9.0.2. Preserve original files in `C:/Dev/software/ffmpeg-backup-20261013`
and the complete new package in `C:/Dev/software/ffmpeg-9.0.2-essentials_build`.
No process/system PATH, runtime source, camera arguments or scientific settings
changed. Runtime continues its existing PATH resolution and needs fresh Setup.

Real build/native-device validation resolves the RTX 2080 Ti UUID
`GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc`, currently ordinal1. All required camera
hybrid-MP4 and stimulus fragmented-MP4 flags exist. Current saved lists and two
reference-derived camera proposals pass existing production validators. Five
sequential eight-frame synthetic cases use production command builders, close
successfully and ffprobe verifies frame counts/dimensions, H.264 profiles, full
range/chroma layouts and camera identity tags. This establishes only the tested
build/input/options/normal-closure cases, not camera conversion, sustained
throughput, crash-prefix behavior, quality or simultaneous workload acceptance.
Native capability query advertises H.264 8-bit 4:2:0/4:4:4 and HEVC 10-bit options;
AV1 is not advertised on this physical encoder. Eye format/rate remain unverified.

The supplied PylonRecorder guide's ant-rig CQ/preset/AQ size ratios do not establish
CephVR results. Saved p4/CQ18/yuv444p/lookahead0 lists remain unchanged.
The latest requested starting recommendation uses p3/CQ18/lookahead0/surfaces0:
color Behavior and saved BayerRG8 Eye use full-range yuv444p/high444p; Mono8
Tracking uses full-range yuv420p/main. All three proposed lists pass existing
validation against recorded9.0.2/RTX2080Ti facts after installed hash verification.
The newly saved Eye ROI1920x1200/rate100Hz is disabled and not physically checked.
[Proposed lists and validation scope](runtime-evidence-2026-10-13/ffmpeg/recommendations.json)
are not applied defaults or actual-footage quality/concurrent throughput acceptance.
Earlier p3/CQ33/lookahead4/surfaces16/rate caps remain compatible comparison options. Container,
GPU ordinal, B-frame prohibition, keyframe cadence and input geometry/rate remain
backend-owned; the reference Matroska/live/GOP options are not accepted GUI tokens.
[Actual methods, install/rollback provenance and probe limitations](runtime-evidence-2026-10-13/ffmpeg/context.json),
[build/device/options audit](runtime-evidence-2026-10-13/ffmpeg/audit.json),
[synthetic executions](runtime-evidence-2026-10-13/ffmpeg/smoke.json),
[post-install PATH/native checks](runtime-evidence-2026-10-13/ffmpeg/installed.json).

Oct13 disabled runtime controls are traced to an authoritative protocol projection
failure: the planner retains a previous group navigation scope when installing an
ungrouped controller trial, raising `Only groups contain epochs`. That leaves
`configuration_wired` false, correctly locking configuration files under G01/E03.
Reset scope and selected paths when replacing the schedule, preserving imported
programs unchanged. Separately, the MCU-specific Configuration gate enabled the
COM children but left their parent disabled by the general gate; apply the same
MCU gate to that parent, retaining authority and active-diagnostic locks.
ARCH-002 review uses existing owners and two small state resets, with no dependency
or new coordination. The cohesive MCU panel retains its existing size advisory.

Read-only native snapshot projection at generation
`f17215ba-41c0-42e1-baeb-4c30d5ccf2b8`, revision4 reproduces the error, disabled
ports/files and enabled Test connection. After repair, the same snapshot installs
without error and enables COM selector/refresh, MCU files and full GUI files.
Five focused offscreen Windows cases pass (397 deselected, 3.60s); Ruff/check format
three files, Win32 mypy151 GUI sources, boundaries666/zero violations and whitespace
pass. The first regression attempt fails only because the sample fixture starts
ungrouped; explicitly establish the prior grouped selection before testing reload.
No pin tests, flashing or camera/SpikeGLX commands run. The live old-code GUI is
then closed through owner-requested normal ShutdownApplication after accepted
history save; exact generation-bound receipt confirms all owned processes absent.
The existing local GUI file is preserved; this controller shutdown does not claim
to save unsent edits in the old GUI. Reopening loads the repaired source.
[Projection evidence](runtime-evidence-2026-10-13/disabled-controls.json),
[shutdown evidence](runtime-evidence-2026-10-13/disabled-controls-shutdown.json).

Oct13 numeric MCU pin display under [G01 revision 166](../docs/architecture/gui.md#g01)
uses number-only editors for fixed I/O and camera pins, including restored D-prefixed
assignments. Keep existing snapshot/firmware tokens canonical at capture/submission;
numeric edits compare correctly with confirmed controller pins before Test. A11's
runtime serial configuration and bounded diagnostics require no firmware flashing
for reassignment. ARCH-002 extracts one focused editor/token helper, reusing Qt and
existing snapshot/request owners without new dependencies or firmware changes.
Final native GUI selection passes 29 (373 deselected, 20.09 s), covering migration,
numeric/legacy request tokens, confirmed test gates and full-file/runtime/review
round trips. Initial expectations for prefixed widget text and saved-token formatting
were corrected; saved files retain their existing wire representation. Ruff
check/format (153 files), Win32 mypy (151 sources), boundaries (666 modules/zero
violations; existing cohesion advisories), edited TOML loader and whitespace pass.
[Validation evidence](runtime-evidence-2026-10-13/pin-numbers-context.json).

The owner selects Trial state output on pin 12, with manual SpikeGLX observation.
Update its owning TOML default and confirm/save D12 through the controller's existing
configuration/history operations. Two native two-second output tests on COM8 use
installed protocol 3 / cephvr2_uno_2 with camera outputs stopped; no pin-9 test runs.
The first starts successfully but its probe incorrectly supplies a signal to STATUS;
the controller rejects that follow-up, then normal shutdown succeeds. Retain it as
probe misuse, not a production MCU defect. The corrected repeat has matched active
and stopped D12 diagnostic snapshots, one generated rising transition, confirmed
normal shutdown and generation-bound all-owned-absence receipt. Saved D12 history
reloads without warning. Read-only SpikeGLX status reports acquiring; no remote
mutation, firmware upload, camera capture or experiment/recording command runs.
The owner then clarifies that testing must be triggered manually with the GUI Test
button; the agent had over-interpreted the earlier observation request and sent the
two tests automatically. Stop automation; neither a receiver pass nor a wiring defect
is inferred. Reopen Runtime for the owner: read-only readiness confirms Configuration,
COM8/D12 enabled, GUI-held control and no active diagnostic. Leave that runtime open
for manual Test connection / Trial state Test. The owning regression now clicks the
actual numeric-pin-12 Test button against an isolated controller: one native case
passes (401 deselected, 2.98 s), preserving stale-pin rejection. Electrical voltage,
timing and receiver acceptance remain in the existing rig checklist; other hardware
deferrals remain. The earlier two test runtimes are closed; this final GUI is
intentionally running for the owner's manual interaction.
[Native methods and outcomes](runtime-evidence-2026-10-13/pin-test/context.json).

Oct13 exact controller-exit verification under [E08](../docs/architecture/system-contracts.md#e08)
passes on the running Windows runtime. Preflight confirms Configuration, four startup
Idle outputs and no Acquisition/Tracking work. The actual controller is still alive
after GUI closure; GUI closure intentionally retains the runtime under E03/E08.
Terminate only controller PID 27476 with its retained creation-time/image identity:
supervisor 23512, acquisition 20976, Visual Stimulus 26684, tracking 23848 and renderer
24404 all exit. At 3.453 s the generation-bound launcher receipt confirms the outer
application Job empty; a fresh process inventory finds no managed executable and
the application guard is available. This closes the running projector-process
ownership check without a production code/architecture change. The independent
controller-loss emergency report is preserved; process absence does not prove
recording finalization or paired SpikeGLX stopping. Activated/full-load fault acceptance
and existing hardware deferrals remain open. Launcher/supervisor/native isolated tests
pass 95 with one Windows symlink-privilege skip (7.63 s). No camera capture, new
recording, scientific-setting change or automatic relaunch is performed.
[Exact identities, method and retained evidence](runtime-evidence-2026-10-13/controller-exit/context.json)
include the authenticated preflight, native exit observations and test results.

Oct13 GPU startup closure repair follows [V19 revision 6](../docs/architecture/visual_stimulus.md#v19):
a healthy wrong-adapter context is rejected through exact sessionless display cleanup,
with configuration/GUI retained; actual GPU faults and unsafe cleanup still escalate.
Authenticated controller cases and native AMD context release pass. The final managed
GUI launch uses the required RTX 5060 Ti, initializes all four outputs and has no
warnings/errors. The original failing launch route remains unresolved; see the
[owning GPU assessment](visual_stimulus.md#startup-gpu-placement-and-closure).

Oct13 runtime GUI retention under [G01 revision 165](../docs/architecture/gui.md#g01)
and [E07 revision 60](../docs/architecture/experiment.md#e07) saves the complete editable
GUI snapshot atomically to `config/runtime_gui.json` and verifies it by reading back
before closure. Restore once after initial inventory/base installation, retaining
local drafts and marking them dirty for normal E07 acceptance. Preserve delayed
SpikeGLX mapping replies as provenance without replacing restored channel edits;
explicit controller reload resets that draft protection. Startup-only host values
remain read-only. Runtime and Review have separate local files.

Local save failures keep the GUI open unless Close without saving is explicitly
selected. Controller disconnection or accepted-history save rejection cannot discard
the verified local snapshot. Remove close-time configuration submission and obsolete
discard handling; controller history remains controller-owned. Fix Qt's reentrant
close suppression by accepting the outer close event after synchronous local-save
completion. Unreadable/incompatible, not-yet-restored and active-session previous
files remain preserved. Restoring never changes controller state or launches devices.
Retention covers normal closure; forced process termination cannot promise a save.
The original reported warning detail remains unknown; initial read-only checks found
valid current controller/review history and QSettings NoError.

ARCH-002 uses one focused GuiHistory owner with the existing GuiSnapshot validators
and QSaveFile, without a new schema/dependency or whole-runtime reference. Main retains
its existing Qt wiring/snapshot/authority coordination (size advisory); storage is
separate and obsolete close submission/discard responsibilities are removed.
Extend the owning dashboard behavior module rather than create per-fix tests.

Final native Windows selection: 27 passed (374 deselected, 18.27 s), including actual
close/reopen full-snapshot equality, disconnected saving, rejected controller history,
failed disk writes, preserved unreadable files, repeated snapshot polling and late
inventory replies. Isolated fixtures use no devices/controller process. Broader
offscreen selection: 106 passed/two existing 15-pixel projector overflow failures
(293 deselected, 51.18 s); those remain in the existing narrow-overflow task. Sandbox
attempts stall while Windows asyncio creates its loopback socketpair; a retained
30-second trace identifies socket.accept/_fallback_socketpair. Stop only the exact
owned test processes and rerun unchanged assertions with permitted loopback access.
No full-suite or device/experiment/forced-exit acceptance is claimed.
Ruff check/format (152 files), Win32 mypy (150 GUI sources), boundaries (665 modules,
zero violations; existing cohesion advisories) and whitespace pass.
[Native results](runtime-evidence-2026-10-13/settings-retention-native.xml),
[broader results](runtime-evidence-2026-10-13/settings-retention-offscreen.xml) and
[methods/source hashes](runtime-evidence-2026-10-13/settings-retention-context.json)
retain the exact validation scope.

Oct13 native picker repair under [G01 revision 164](../docs/architecture/gui.md#g01)
and E03 resolves the immediate-open/reject/parent-cleanup crash without changing the
test fixture or cancellation timing. Five native authority-loss cases and a standalone
window reproduce `0xC0000005`; unwrapped QFileDialog reproduces it too. Qt 6.11.2's
[Windows helper source](https://github.com/qt/qtbase/blob/v6.11.2/src/plugins/platforms/windows/qwindowsdialoghelpers.cpp#L188-L284)
shows deferred modal startup while hide clears the native dialog without stopping its
timer. This mechanism matches the reproduced sequence; no native instruction-pointer
dump is available. Delaying cleanup still emits access-violation notices, so no sleep
or production event-loop pumping is introduced.
ARCH-002 adds one focused factory selecting Qt's documented widget picker before
configuration/showing, reused by configuration, projector, folder/PFS, prepared-file
and stimulus-media owners. Existing filters, path/schema checks, stale-result guards
and deleteLater ownership remain intact; no global dialog setting or dependency change.
The original standalone sequence passes 50 rapid cycles without notices; ten real
Windows Load/Save authority-loss cases pass. The broad native GUI stage now finishes
normally with 401 passes/two hover-control lookup failures (186.89 s), before the final
media-picker adoption/test refinement. Final affected native selection passes 20
(382 deselected), covering those refinements, all picker owners and Runtime/Review
parity. The two hover cases repeat in fresh isolation with zero QFileDialog
constructions; they are separate native-test findings, not evidence of a picker crash
or a proven production hover defect. Existing offscreen projector-overflow findings
remain open; no exact-final-tree full-GUI or hardware acceptance is claimed.
Ruff/format (151 files), Win32 mypy (149 GUI sources), boundaries (664 modules/zero
violations; existing cohesion advisories) pass.
[Raw methods, source fingerprints and outcomes](runtime-evidence-2026-10-13/native-chooser/context.json)
retain baseline failures, comparisons and staged validation.

Oct13 Runtime/Review layout parity under [G01 revision 163](../docs/architecture/gui.md#g01)
removes Runtime-only Dashboard control-button/hint rows, their signal and unused
forwarder. Both modes retain one shared page construction and identical card geometry;
Runtime authority stays in the existing Control menu and truthful HUD, with unchanged
command/edit gates. ARCH-002 removes redundant presentation rather than adding another
layout or state owner. Strengthen the existing parity test to compare every card
without exceptions across Dashboard, Protocol, Devices/Projectors and Tracking subtabs,
at 1280/720 widths with Runtime/Review authority states and matched drafts. Menu
Take/Release and denied/confirmed takeover still dispatch their exact intents.
Eight focused layout/HUD/control cases pass; Ruff/format (150 files), Win32 mypy
(148 GUI sources), boundaries (663 modules/zero violations; existing cohesion
advisories) and whitespace pass. An initial sandbox run cannot create temp fixtures;
the permitted identical selection passes. No new dependency or device operation.
[Dated methods and final source hashes](runtime-evidence-2026-10-13/runtime-review-parity-context.json)
retain scope; subsequent picker repair is recorded above. Projector overflow,
encoding and hardware findings remain separate.

Oct13 rig verification uses clean source `f4e6bc89a612e5f33fe5b5256281bd1650257e32`.
Regenerating 19 authoritative Protobuf inputs resolves stale local bindings.
Windows static/contracts/schema/package steps pass; isolated backend/native tests
pass 1,520 with five skips. Combined/native GUI runs terminate with access violation
`0xC0000005`; the isolated native trace identifies fixture teardown after configuration
chooser tests. These are pre-repair failures; the focused native repair above resolves
that reproduction, while broader GUI acceptance remains incomplete.
Offscreen GUI regression completes with 396 passes and three failures: projector
configuration scrolling has a 15-pixel horizontal range at 1175-pixel window width.
All five backend skips require unavailable Windows symlink privileges; they remain
unverified. Existing ARCH-002 cohesion advisories remain, with zero boundary violations.
Four projectors at 60 Hz and both NVIDIA adapters are visible; read-only SpikeGLX
connection succeeds. Native V19 startup confirms all four RGB8 outputs with requested
interval-1 swaps. V01 grid Open, live updates at sequences 1/2, and Close confirm
presentation, Idle and resource closure using retained dummy geometry plus a separate
all-output-VSync diagnostic profile; the accepted configuration remains unchanged.
This is native lifecycle evidence, not optical geometry or latency acceptance.
The actual GUI Behavior Connect command produces no usable frame by its deadline,
then WORKER_OWNER_FAILURE triggers shutdown. The exact exit receipt confirms all
owned processes absent and the application guard free. COM8 Connect independently
reports protocol 3 / `cephvr2_uno_2`, both camera outputs stopped. A diagnostic STATUS
request without an active diagnostic is correctly rejected; it is probe misuse.
The initial PATH FFmpeg/ffprobe 4.3.2 audit lacks required `hybrid_fragmented`
capability; the later matched 9.0.2 repair above resolves that tool incompatibility.
Recording/full-load acceptance remains unverified. Eye, further camera capture, pulse
mapping and electrical measurements are owner-deferred today.
The missing-identity update probe does not exercise V19 startup initialization;
its two result waits time out, while both configuration updates succeed. An independent
snapshot proves exact restoration. Final normal shutdown confirms exact all-owned
absence, free application guard, exclusive COM8 open/close, and saved history matching
the original adopted configuration. A native desktop resize drag has no effect,
so narrow/DPI acceptance remains unverified. See
[current raw evidence](rig-evidence-2026-10-13/) and the
[remaining rig checklist](rig-verification.md); no full-workload acceptance is claimed.

Oct12 [G01 revision 151](../docs/architecture/gui.md#g01) adds Up/Down stepping to
shared Runtime/Review calibration inputs: scale 0.01 with two decimal places,
offset 0.1 px with one. The existing text draft/serialization and live user-edit
path remain authoritative; imported precision and partial typed input are preserved.
ARCH-002 review keeps this small input behavior in the focused calibration widget,
without new dependencies or state ownership. Five offscreen stepping/live/file/draft
cases pass, with scoped Ruff/format, GUI Win32 mypy (141 sources), boundaries
(650 modules/zero violations; existing cohesion advisories) and whitespace checks.
[Dated commands and source hashes](runtime-evidence-2026-10-12/calibration-steps/context.json)
record the local scope; no new native/optical/rig acceptance is claimed.

Oct12 [G01 revision 150](../docs/architecture/gui.md#g01) presents photodiode
placement as Frame/Pulse rows with Origin X, Origin Y, Width and Height. Frame
origins remain bottom-left output pixels; Pulse origins are relative to Frame, with
independent dimensions and strict containment. Both GUI modes use the shared table,
existing authority/pulse gates and planning preview. Full Projectors JSON version 7
migrates version-6 squares into equal Pulse dimensions and preserves older standalone
rectangles; numeric calibration remains version 4. Blackout zones retain the shared
empty-header rule. [Visual Stimulus](visual_stimulus.md) owns rectangular-pulse
validation and final composition. Fifty affected cases and 42 contract tests with
79 subtests pass; nine final presentation/file/render/parity checks also pass.
Ruff/format (289 files), Win32 mypy (271 sources), 11 schemas/zero drift, boundaries
(649 modules/zero violations) and whitespace pass. Both-width captures are inspected;
[current evidence](runtime-evidence-2026-10-12/pulse-definition-table/context.json).
Earlier [665-case integration evidence](runtime-evidence-2026-10-12/output-overlays/context.json)
and [empty-header evidence](runtime-evidence-2026-10-12/blackout-header/context.json)
retain their source stages and native limits. Existing open Review imports require
reopening to load this update; unsaved edits are left intact.

Oct12 [G01 revision 148](../docs/architecture/gui.md#g01) /
[V01 revision 18](../docs/architecture/visual_stimulus.md#v01) implement live Scale
X/Y and Offset X/Y in the active frame/grid diagnostic. Debounced edits coalesce
behind one in-flight, sequence-bound leased update; only actual all-output presentation
confirms it. Invalid/partial typing retains the last valid projection. Rejecting a
stale or malformed update before GL writes keeps the diagnostic healthy and reports
failed adjustment; GPU/presentation uncertainty retains Unknown and exact Close.
Other projector settings remain locked, and control loss/disconnect/change of
identity discards queued intents. Protected assets, windows, configuration revision
and original cleanup owners/deadlines stay intact; these are Configuration diagnostics.

ARCH-002 extracts focused GUI coalescing, controller admission, coordinator validation
and worker presentation helpers; the existing GL owner updates retained warp buffers.
Controller/Visual Stimulus suites pass 659 tests/one deselection before the final
mesh-precision guard, including the
real authenticated coordinator/renderer update services with display hardware injected.
The final guard run passes 658 cases and hits one CLI-help timeout; that unchanged
CLI case passes a targeted rerun. Sixty affected GUI cases pass, including
Runtime/Review parity; seven focused final
GUI/render cases overlap. Ruff/format (423 files), Win32 mypy (376 sources), boundaries
(649 modules/zero violations), 11-schema drift, 57 generated binding matches and
whitespace pass. [Dated methods, stages, hashes and limits](runtime-evidence-2026-10-12/live-grid-context.json)
retain staged validation and repaired attempts, rather than a full exact-final-tree
claim while other chats update Protocol/photodiode code. Active-grid controls are visually
inspected offscreen at wide/narrow widths. Concurrent Blackout zones parity and
calibration-profile comparison failures are retained as intermediate results; final
shared GUI checks pass after that task's corrections. No full GUI regression or
native Windows/DPI/GPU/optical/rig acceptance is claimed.

Oct12 [G01 revision 146](../docs/architecture/gui.md#g01) implements the owner's
separate Launch reference calibration and Launch projection calibration actions. Bars ignore prior
measurements/manual corrections; grid requires mode-matched pairs and maps mm/px
directly onto physical rig screens with manual scale/offset/inversion. Throw ratio
is config-only and produces the distance estimate; neither launch nor measured
mapping requires it. Existing protected managed launch/Close, authority and pending
locks remain. [Visual Stimulus](visual_stimulus.md) owns current workflow evidence:
74 affected tests and 42 contract cases/79 subtests pass, with local static checks
and wide/narrow card inspection. Native Windows/DPI/optical acceptance remains open.

Oct12 [G01 revision 145](../docs/architecture/gui.md#g01) names the shared card
Pixel-to-mm calibration and lets all three columns stretch equally through the
existing DataTable default. Remove the SpikeGLX connection explanatory paragraph,
retaining the config-path tooltip and read-only host controls. ARCH-002 removes the
local header override/widget rather than introducing another layout owner.
Projector distance is not an input to diagnostic launch; complete measured pairs
update ideal distance from native width × X mm/px × positive throw ratio. The later revision 146 removes the historical measured-mapping dependency on
throw ratio; revision 145 itself changes only presentation.
[Current layout evidence](runtime-evidence-2026-10-12/reference-layout-context.json)
records local checks; native Windows/DPI and physical acceptance remain pending.

Oct12 Projectors refinement under [G01 revision 144](../docs/architecture/gui.md#g01)
and [V01 revision 16](../docs/architecture/visual_stimulus.md#v01) removes explanatory
text and pixel columns, pairs measured X/Y millimetres under one header and shows
mm/px estimates independently of throw ratio. Config-only pixel lengths control
actual native bars, conversion and planning preview. Full/numeric file versions
5/4 retain them with legacy migration and atomic invalid-length rejection.
[Visual Stimulus](visual_stimulus.md) owns implementation and evidence: 71 affected
checks, 42 contract cases/79 subtests and local static checks pass. Wide/narrow
shared Runtime/Review card inspection passes offscreen; native/optical acceptance
remains in the existing rig worklist.

Oct12 [G01 revision 139](../docs/architecture/gui.md#g01) removes Gap/Seed controls and
the Selected trial section in both GUI modes. Per-trial Seed is config-only through
the existing Protocol JSON `stimulus_seed_decimal` field. Load/save preserves edited
seeds, including zero, and existing gap values; managed submission retains E01/E07
validation and timing. ARCH-002 deletes the widget/synchronization plumbing instead
of introducing another seed setting or state owner. Ten focused file-round-trip,
schedule, draft-retention, layout and parity checks pass. GUI Ruff, scoped format,
Win32 mypy (138 sources), boundaries (642 modules/zero violations), references and
whitespace pass. [Current hashes, commands and raw results](runtime-evidence-2026-10-12/config-seed-context.json)
record local scope and a formatting-only test-line correction. Native Windows/DPI,
live restart and full GUI/rig acceptance remain untested in this increment.

Oct12 Devices refinement under [G01/G02](../docs/architecture/gui.md#g01) puts a
Configuration file card first beneath each device tab row, including camera-only
files. The shared file rows use Load… / Save as… captions, equal-sized buttons and the
same field gap across all four Devices tabs under G01 revision 142/G02 revision 36;
Tracking captions match while retaining its Pipeline layout. Six focused layout/
file/parity checks and static checks pass; [current file-action evidence](runtime-evidence-2026-10-12/file-actions-context.json)
retains local methods, hashes and limits.
G01 revision 143/G02 revision 37 unify inventory Refresh through one accessible
icon/header helper, Use-first columns and single-row selection. MCU discovery uses
that icon beside COM selection, with Test connection separate. Empty MCU Inputs/
Outputs and SpikeGLX channel headers share visibility/height fitting; empty discovery
inventories retain Refresh. Protocol variation rows refit the shared control height
after ancestor styles settle, correcting an observed 38/36 px mismatch. Seventy-seven
affected checks pass, including discovery/identity/authority, file/layout and GUI
parity; GUI static checks and boundaries pass. [Current audit evidence](runtime-evidence-2026-10-12/shared-controls-context.json)
preserves initial failures, corrected measurements and final hashes/raw results.
Wide populated Projectors and narrow device views are inspected locally; existing
scrolling remains necessary. Native Windows/DPI/live restart/device/full GUI and rig
acceptance remain untested in this increment.
Cameras replaces the visible batch identity action with Test selected beside
Connect. MCU omits Apply pin settings and adds supported-signal dropdowns with
Add/remove: Projector flip input, Trial state and assigned Behavior/Tracking outputs.
Removal disables the owning signal while retaining its pin; camera participation
continues to belong to Cameras. MCU v2 files retain output enablement, load v1 files
without changing camera participation, and reject inconsistent full-GUI enable flags
before mutation. Load restores local drafts without device commands. SpikeGLX shows
only Use, Signal and Channel index while preserving stream/index/bit metadata under
the [snapshot contract](../contracts/gui-configuration-files.md).

ARCH-002 reuses camera serialization for camera-only/full files and keeps supported
MCU row editing in a focused GUI helper. Remove obsolete batch-button state and
embedded file-toolbar/Apply wiring; no backend protocol, firmware or dependency changes.
The large camera/MCU panels retain orchestration with small helper bindings, rather
than accumulating snapshot or signal-table implementation. Existing owner tests
cover saves, v1 compatibility, invalid-file atomicity, disabled-camera identity,
diagnostic/authority locks, narrow controls and Runtime/Review parity. All **390 GUI
tests pass in 353.58 s**, including the concurrent Protocol refinement; exact source
hashes still match. Ruff/format (140 files), Win32 mypy (138 sources), boundaries
(642 modules/zero violations) and whitespace pass. Wide/narrow offscreen captures
are inspected. The first suite rejects an inconsistent older fixture; correcting
both camera enable inventories preserves its scenario and the validation guarantee.
[Methods, hashes, captures and raw results](runtime-evidence-2026-10-12/devices-gui/context.json)
retain failed attempts and the hash-confirmed redundant rerun cancellation, including
the Qt abort during that deliberate interrupt; it is excluded from passing evidence.
Desktop Review launch required screen access; its subsequent UI inspection timed
out, so no native visual/Windows/DPI/device acceptance is claimed. Existing
[rig checks](rig-verification.md) remain open.

Oct12 Protocol presentation under [G01 revision 140](../docs/architecture/gui.md#g01)
defaults to Batch generate and uses natural-width Shuffle/Preview buttons at the
right, with the existing narrow-width reflow. Source selection still opens Batch
edit and tab switches preserve drafts. Projectors' configuration button reads Load….
Trials arrows and timeline Delete/Duplicate buttons remain absent; mouse selection,
guarded keyboard edits, history and authority are preserved. ARCH-002 removes
redundant grid rebuilding and uses existing components without new state/dependencies.
Twelve focused layout/default-tab/file/keyboard/shuffle/draft/parity checks pass.
GUI Ruff, scoped format, Win32 mypy (138 sources), boundaries (642 modules/zero
violations), references and whitespace pass; wide/narrow offscreen captures are
inspected. [Current methods, hashes and raw results](runtime-evidence-2026-10-12/compact-default-context.json)
retain local limits. Native Windows/DPI, live restart and full GUI/rig acceptance
remain outside this increment.

Oct12 Runtime/Review parity review under [G01/G02](../docs/architecture/gui.md#g01)
finds no unintended page-layout differences. Both entry points reuse DashboardWindow
and the application theme. Strengthen the existing owning parity test to construct
runtime with `sample=False`, restore matching validated settings and populated camera/
projector fixtures, and exercise actual runtime authority presentation at 1280/720 px.
All pages and nested tabs match in control inventory and card geometry; only runtime
lease controls and their Dashboard left-column displacement are excluded explicitly.
Review inspection/runtime authority menus retain their G01/E03 purpose. No production
code or dependencies change; ARCH-002 retains the existing behavior test module.
Five focused parity/editor cases pass; GUI Ruff/format (138 files), Windows-target
mypy (136 sources), boundaries (640 modules/zero violations) and whitespace pass.
[Methods, tested hashes, setup failures and results](runtime-evidence-2026-10-12/gui-parity-context.json)
record local offscreen Configuration scope. No native Windows/DPI/pixel or rig
acceptance is claimed; existing [rig checks](rig-verification.md) remain open.

Oct11 repository cleanup under [ARCH-002](../architecture.md#arch-002) removes
unreferenced shared context protocols/validators, the unused payload-transfer and
admission-inspection methods, and an unused startup-recovery test helper. Equivalent
device-admission branches and the supervisor cleanup predicate are simplified;
E08 identity, retention, ownership and deadline checks on active paths are unchanged.
Remove 51 stale GUI naming suppressions and their obsolete Ruff exception; all 25
edited GUI modules have identical before/after ASTs. Across the cleanup, 37 Python
files lose 119 net lines. Existing uncommitted repairs are preserved.

Owner tests pass 1,032 cases; integration passes 424 in the sandbox, with 27 localhost
bind failures/errors resolved by a permitted communication-module rerun (43 passes).
Together these cover 1,483 distinct passing cases, six skips and eight Windows/rig
deselections. GUI behavioral tests were not rerun for comment-only edits. Repository
Ruff/format passes 874 files, Win32 mypy passes 735 sources, and boundaries report
640 modules with zero violations. Existing cohesion advisories remain; this cleanup
adds no dependencies or responsibilities. Remove 74 untracked generated cache
directories (51,093,992 bytes), preserving environment, bindings, saved settings and
dated evidence. The owner subsequently requested removal of this cleanup's raw logs
and hash manifest on Oct12; the counts above remain historical summaries, including
the initial sandbox limitation. These checks do not close E15 rig work.

Oct11 sequential local repairs (working tree based on `f96286e`): the V19
missing/ambiguous saved-output startup failure now retains Configuration with an
actionable issue only after exact sessionless cleanup and confirmed evidence delivery
within the original deadline. GPU errors, cancellation, deadlines and uncertain
cleanup remain failures. All output identities are resolved before exposing windows.
[V19 implementation and limits](visual_stimulus.md) and the
[startup contract](../contracts/visual_stimulus/startup.md) own the details.
ARCH-002 reuses the resource ledger and extracts sessionless cleanup/display report
handling into focused owners; no new dependency or runtime state owner is introduced.

Portable/offscreen full regression passes **1,861 tests, six skips, eight Windows/rig
deselections** in 307.43 s, including authenticated controller/worker communication.
This covers the startup repair and prior optional-I/O/all-VSync implementation,
before the subsequent GUI shuffle changes. It does not establish a cause or Windows
resolution for Oct9's exact-completion timeout. Contracts pass 48 Tracking/42 Visual
cases; generated schemas (19/11) and 57 protobuf bindings match. Static analysis,
declarations and dependency checks pass. [Raw full-suite evidence](runtime-evidence-2026-10-11/startup-full.txt)
and [tested input hashes](runtime-evidence-2026-10-11/startup-inputs.json) retain local
scope; native MCU Apply and all-output VSync remain pending.

GUI **Shuffle trial** follows the owner-approved [G01 revision 135](../docs/architecture/gui.md#g01):
it permutes top-level blocks as a normal source edit, retaining each group's nested
objects, repetitions and condition references. Current nested/multiple selection
moves with its blocks; undo/redo restores selection and source order, and saved files
retain the permutation. Existing edit authority and pending-validation gates apply;
Setup seeds and V08 runtime shuffle remain unchanged. ARCH-002 keeps the pure reorder
in the existing node-editing helper and selection snapshots in the history owner;
the editor remains GUI orchestration without new dependencies or runtime references.
The GUI owner suite passes 381 cases; the subsequent two-row narrow-action layout
passes five focused shuffle/layout cases. Final lint/format, Win32 mypy (735 sources)
and boundaries (640 modules, zero violations) pass. Wide/narrow offscreen screenshots
are visually checked, and all four timeline actions meet their minimum label widths.
The initial screenshot helper exits 138 during teardown; explicit deferred widget
destruction in the final helper exits normally. This does not establish native Windows
teardown or DPI acceptance. [Methods, source hashes, raw results and limits](runtime-evidence-2026-10-11/context.json)
keep each validation stage separate.

Oct11 GUI error/recovery review under [G01/E03](../docs/architecture/gui.md#g01)
and E07 fixes two configuration-recovery paths. An earlier accepted submission no
longer clears the explanation for newer unsent edits. Configuration installation
uses the existing scoped projection guard, restoring edit tracking even on rejection;
explicit failed Reload returns an actionable error instead of escaping the GUI slot.
Subsequent valid reload clears stale/error state. ARCH-002 removes the entry point's
private-state repair and keeps errors with the focused configuration owner; no new
state, dependency or architecture rule. Three regressions fail before the repair and
pass afterward. The broader managed/recovery selection passes 82 cases; GUI static
checks and boundaries pass. Command failure, stale queue, reconnect review,
close/save and device pending-state review finds no further actionable defect.
[Source hashes, methods and raw outcomes](runtime-evidence-2026-10-11/gui-recovery-context.json)
retain local scope; native managed-GUI acceptance remains in the rig checklist.

Current [managed bindings](../src/cephvr/gui/main.py) connect configuration/Protocol,
camera controls/previews, MCU, Tracking diagnostics, projector calibration and
SpikeGLX operations. Older incremental statements below are historical. The explicit
remaining capture implementation gate is
[Eye external triggering](../src/cephvr/acquisition/config/validation_pulse.py).
Controlled stimulus throughput diagnosis, paired SpikeGLX, scientific Tracking/feedback,
calibration, native GUI/DPI, electrical timing and fault cleanup retain their existing
[rig checks](rig-verification.md). No new native runtime/device execution is claimed.

Oct9 Eye role/connect recovery (working tree based on `94285ac`) extends common
three-camera configuration/process/output evidence under
[A01/A02/A07](../docs/architecture/acquisition.md#a01),
[A10/A11](../docs/architecture/acquisition.md#a10) and
[G01](../docs/architecture/gui.md#g01). It repairs canceled readback barriers,
failed-start Disconnect, exact manual terminal acknowledgements, prior-cleanup
diagnostics and GUI pin aliasing. No new state owner, dependency or firmware policy
is introduced; the existing ledger retains exact terminal evidence. Controller runtime
only routes that evidence to its focused readback owner under ARCH-002.
[Acquisition assessment](acquisition.md) records role/capture limits.

Live GUI identity tests pass for both existing cameras. COM8's native responses identify
legacy firmware that does not implement CAPS, explaining the original timeout.
The owner's subsequent `.ino` Upload request exercises the native chooser and exposes
a GUI recovery defect: a displayed MCU failure disabled Upload despite A11 allowing
the idle repair handoff. G01 revision 134 removes that failure-only gate; diagnostics,
all three camera ownership views and exact native cleanup still block Upload. Controller
admission now includes Eye ownership, matching the GUI. ARCH-002 keeps the existing
focused bindings/admission owner and introduces no dependency or state owner.
Native Browse accepts `firmware/uno/cephvr2_mcu/cephvr2_mcu.ino`; explicit GUI Upload
compiles and verifies it on COM8, reconnecting as `cephvr2_uno_2`, protocol 3, with both
camera outputs stopped and cleanup complete. A subsequent Test connection succeeds.
That repair left the GUI open. The owner's subsequent all-output VSync choice now
passes pure validation without a pacer, but disconnected outputs prevent live checks.
Eye additionally needs external wiring/source/rate
and corresponding integration. Run43 remains historical output evidence; no new
recording or SpikeGLX pairing is claimed.
[Firmware repair method, source and raw outcomes](review-evidence-2026-10-09/firmware-picker-context.json)
retain chooser/button observations, native status and current checks.
[Current check/source/native evidence](review-evidence-2026-10-09/eye-camera-context.json)
preserves final verification and failed attempts separately from the prior checkout
audit. See the [rig checklist](rig-verification.md) for remaining acceptance.
Earlier non-rig Windows/offscreen execution passes 1,856 tests with five symlink
privilege skips and one rig deselection. Ruff/format (849 files), Win32 mypy
(734 sources), boundaries (640 modules/zero violations), dependencies,
contracts/schemas and declarations pass. The firmware evidence records the tested
1,039-input snapshot and a subsequent test-only import-separator formatting correction;
the forty focused firmware cases pass again on that final text. Subsequent E08
revision 170 moves all local runtime records to the owner-private
`%USERPROFILE%/.cephvr2/runtime` namespace. The current full suite and static checks
cover the final runtime source, with 295 focused integration cases passing and one
privilege skip. [Runtime namespace evidence](review-evidence-2026-10-09/runtime-root-context.json)
records preservation, live Y/N replacement, physical path visibility and limits.

Updated: 2026-10-11. Implementation/source review is recorded for the controller,
supervisor, launcher, headless client and shared/native helpers. Local results below
have their original scope; Windows and full-workload acceptance remain pending.
[ARCH-001/002](../architecture.md#arch-001) owns scope and structure;
[E04](../docs/architecture/supervisor.md#e04) and
[E05/E07](../docs/architecture/experiment.md) and
[E06/E08](../docs/architecture/system-contracts.md#e08) own behavior.

Current Windows checkout verification (2026-10-09, `94285ac`): regenerate stale
ignored local bindings from all 19 authoritative protos, resolving seven collection
errors and 17 typing errors without changing runtime source. The full offscreen
`not rig` suite, including isolated Windows resources/children and authenticated
loopback, passes **1,820 tests / five symlink-privilege skips / one rig deselection**.
Ruff/format (849 files), Win32 mypy (734 sources), boundaries (640 modules, zero
violations), dependency consistency, Tracking/Visual Stimulus contracts (48/42),
schema drift (19/11), fresh binding comparison (57 files), TOMLs (18), decision
register (114 revisions) and current changed-document links pass. Correct stale
V08/V17/V18 root index revisions to their owning records without changing decisions.
Size advisories retain their existing ownership/cohesion assessments; this verification
adds no runtime behavior or dependency. [Exact Windows commands, input hashes and outcomes](review-evidence-2026-10-09/windows-checkout-context.json)
retain failed attempts and exclusions. These checks do not rerun the dummy protocol
or establish camera/encoder throughput, optical/electrical or scientific acceptance;
those remain in the [rig checklist](rig-verification.md).

Completed initial repair scope (2026-10-09, working tree based on `0aebf47`): the owner
authorized fixes and cleanup after the Luna/Sol/Astra audit. Sol and Astra accept the final source with no remaining actionable finding in this
bounded review. The confirmed retirement,
recovery, replay, shutdown, SDK and GUI-feedback defects are repaired below; accepted
defaults are restored to a 500 ms preparation lead with unmeasured camera drain margins
and pacing-output identity unset. All 36 owning configuration cases now pass.
[Original audit and rejected candidates](review-evidence-2026-10-09/context.json)
remain historical evidence. [Implementation methods and validation](review-evidence-2026-10-09/implementation-context.json)
identify the final source snapshot, model handoffs and local/native boundary.

Latest retained native evidence is **run43**, not run42: its unpaired 60 s trial and
session complete, seven artifacts close, metadata syncs and the reservation unlocks.
Both camera videos and stimulus video pass external count/full CPU decode in the
[Oct8 output summary](rig-wiring-evidence-2026-10-08/dummy-experiment/unpaired-run-43-output-verification.json).
Behavior delivers 1,797 frames (29.95 fps) and Tracking camera 3,596 (59.93 fps),
superseding the earlier 20/40 fps observation after the external-trigger limiter fix.
Stimulus delivers 1,182 frames (19.7 fps), with four capacity drops; its nominal-60-fps
MP4 is 19.7 s for a 60 s trial. Render intervals have a 49.29 ms median. Throughput
remains open; the Oct9 non-GUI implementation adds explicit nominal-slot padding,
which cannot repair missed presentations and has not been rerun on the rig.
[Shutdown](rig-wiring-evidence-2026-10-08/dummy-experiment/final43-shutdown.json)
records exact process absence, released guard and saved history. Later raw records
report [GPU preference restoration](rig-wiring-evidence-2026-10-08/dummy-experiment/final-gpu-restoration.json)
and [original configuration restoration](rig-wiring-evidence-2026-10-08/dummy-experiment/final-history-restoration.json).
These are historical observations with no exact source revision in the inspected
summaries, not new native checks or current-default/full-load acceptance. Velocities
and SpikeGLX pairing were disabled. Remaining acceptance lives in the
[rig checklist](rig-verification.md).

## Current scope and review

<a id="maintainability-review"></a>


Oct21 `repo-unused-code-oct21` follows [ARCH-002](../architecture.md#arch-002):
removed the unintegrated GUI calibration-asset pruning CLI and its dedicated test,
five acquisition recording modules that only re-exported shared FFmpeg helpers,
and the unused preview `trace_value` helper. The filter tests now import the owning
shared modules directly; all six test-function bodies/signatures/decorators are
unchanged. Caller/import and documentation searches found no remaining consumers.
Calibration publication and existing profile assets remain intact under
[G01](../docs/architecture/gui.md#g01). Build, contract generation, launch and rig
validation tools retain active uses. Dynamic entry points, framework callbacks,
serialized fields and native resource owners were retained where static unused-code
signals alone were insufficient. No cleanup infrastructure was added.

Validation: 29 focused acquisition-filter/GUI-timeline tests pass; acquisition/GUI
Ruff lint and format checks pass (401 files), Win32 source mypy passes (373 files),
and backend boundaries pass (740 modules, zero violations). Broader acquisition
and selected dashboard runs stalled without further output and were interrupted;
no full-suite pass is claimed. An extra mypy invocation including the existing
untyped filter-test module reported 12 test-typing errors outside the source-only
scope; test function ASTs were unchanged, and the proper source check passed.
Reference and whitespace checks pass. No native or rig acceptance was performed.

Oct21 `reports-retention-policy` is documented intent only under
[GOV-001 revision29](../architecture.md#gov-001). The owner requested removal of
both scheduling and the dormant implementation. The Codex automation was deleted;
the standalone cleanup tool, protection registry, dedicated tests and empty deletion
log have now been removed. There is no automatic cleanup or maintained retention
implementation. No development evidence or experiment output was deleted by this
retention work. Historical implementation checks remain in LOG, not as current
validation of a removed tool.

Development reports and independent emergency files are not copied to experiment
output. E04's central session log/config/schema and trial/backend outputs remain
separate; failed or cancelled Setup creates no session log. Experiment output is
not a backup of development evidence. Remaining retention intent belongs solely to
GOV-001; future cleanup needs an explicit request.

Oct20 `repo-cleanup-oct20`, reviewed against dirty base `b3984bc2`, removes
17 lines of unused GUI presentation code: `DashboardView.metadata_status`, its
managed/review producers, and the write-only `DashboardWindow.page_layout` alias.
Repository caller searches found no consumers; the QWidget still owns its layout.
This follows [ARCH-002](../architecture.md#arch-002) without changing
[G01](../docs/architecture/gui.md#g01), wire metadata, cleanup gates or retained
failure details. Existing uncommitted work remains in place.

Removed 1,407 disposable files (46,907,949 bytes) from 25 inspected directories:
build/dist, tool caches, three preview pytest directories and 17 `reports/tmp-*`
fixture directories. These contained no tracked files; resolved deletion targets
were checked within this checkout. Runtime emergency reports, dated evidence,
recordings, configuration, native bindings and the environment remain.
`reports/tmp-*/` is now ignored; TODO's excess blank lines are collapsed.

Validation: `python -m pytest tests/gui/test_dashboard.py -q -m "not windows and
not rig" -k "managed_status or managed_total_time or retained or review_phase or
dashboard_control_status or post_stop_session or dashboard_has_only or hud_fits
or all_pages_share" --basetemp=.tmp/cleanup-oct20-focused` with Qt offscreen:
33 passed, 748 deselected. The isolated full-GUI draft-loading case also passes.
GUI/tests Ruff lint and format (187 files), Win32 GUI mypy (184 source files),
backend boundaries (740 modules, zero violations) and `git diff --check` pass.
Existing size advisories concern unchanged owners; these deletions need no split.
Vulture's six high-confidence callback/test-argument findings remain intentionally.
The initial broad GUI attempt emitted fixture errors and was interrupted; a second
attempt with a workspace basetemp stopped producing progress and was interrupted.
The latest fixture's isolated case passes, so the broad-run cause is unresolved.
Full GUI completion stays open under `gui-dashboard-test-restoration`; no hardware,
native acceptance, packaging rebuild or exhaustive dead-code proof is claimed.

Oct19 `vulture-low-confidence-triage` uses the declared Vulture2.16 and individual
caller/contract review under [ARCH-002](../architecture.md#arch-002). Successive
advisory scans decrease from 302 to 287, then **283 findings** (259 in source).
The first increment removes write-only tracking/display state and six unused native
constants ([baseline and checks](runtime-evidence-2026-10-19/ponytail-vulture/context.json)).

The helper follow-up removes four caller-free methods and their exclusive state:
the source-depth pixel convenience wrapper and its eager output bytearray, plus
unwired MCU output, SpikeGLX inventory-submit and Tracking Load wrappers. Net37
lines are removed across four source modules. Active pixel consumers supply their
own storage; conversion, strict validation, native source retention and cleanup
bodies remain AST-identical under [A01](../docs/architecture/acquisition.md#a01)/
[T01](../docs/architecture/tracking.md#t01). Existing ConfigurationFiles button
bindings, local pulse drafts and managed MCU routes retain
[G01](../docs/architecture/gui.md#g01) behavior.

`ResourceLedger.unresolved()` remains because the
[native transport interface](../contracts/native_transport.pyi) declares it.
Six high-confidence callback/test parameters, generated SWIG, schema/Protobuf
members, framework callbacks and native owner references remain. No whitelist,
CI gate, policy or dependency change. Existing size advisories do not justify
splitting owners for these deletions.

Current owner selection passes **424 tests** (one skip, three deselections);
focused offscreen Tracking/MCU/SpikeGLX GUI selection passes **103 tests**
(541 deselections). Ruff lint, four-file format, Win32 mypy (826 sources) and
boundaries (724 modules, zero violations) pass. Earlier 2,233-pass backend evidence
belongs to the first increment. No full GUI rerun, native/rig/SDK or performance
acceptance is claimed. Remaining advisory findings stay in TODO for individual
review. [Helper caller traces, source comparison, patch and commands](runtime-evidence-2026-10-19/ponytail-vulture/helper-followup/context.json).

Oct19 `ponytail-repo-simplification` uses repository-wide static/AST scans and
targeted caller review under [ARCH-002](../architecture.md#arch-002). Shared command
finalization and FFmpeg scale/crop/pad updates now use `dataclasses.replace` instead
of copying unchanged fields. Four caller-free helpers/properties are removed:
`retry_storage_cleanup`, `ensure_owner_only`, `has_pending_io`, and
`inherited_handle`, including the ACL mutator's exclusive native binding/constant.
Production code shrinks by 87 lines across six modules.
All retained security functions/classes are AST-identical; active private creation,
verification, cleanup and pending-I/O ownership remain intact under
[E08](../docs/architecture/system-contracts.md#e08). No dependency, setting, policy
or architecture rule changes. Callback/contract/native-owner references remain;
size warnings alone do not justify another abstraction or file split.

Affected local suites pass **206 tests**, with one skip and 23 deselections.
Three geometry cases verify 10-bit/chroma/color metadata and immutable source
preservation. Repository-wide Ruff lint, Win32 mypy (826 sources), boundaries
(724 modules, zero violations), and scoped formatting (seven files) pass.
Broad formatting finds only an existing CRLF-only mismatch in concurrent
`gui/main.py`; it is preserved. Vulture was unavailable for that increment;
the follow-up above resolves installation. Broad offscreen integration passes
2,867 tests, with four skips, 32 deselections and six demo-fixture errors caused by
the chosen in-repository temp directory. All six pass when rerun in a fresh external
temp directory, for **2,873 passing local cases** across the two runs. No assertion
or product behavior was changed to bypass the fixture rule. No native/rig or
exhaustive manual source-audit claim is made. Baseline, patch,
commands, failed attempts and current checks are retained in the
[review evidence](runtime-evidence-2026-10-19/ponytail-review/context.json).

Oct19 `code-sweep-oct19` follows [ARCH-002](../architecture.md#arch-002) and the
owner's restriction to behavior-preserving edits. Repository-wide static scanning
and caller review remove unused batch-binding and parent-navigation
helpers; live subgroup binding, asset editing and breadcrumb navigation retain
their existing owners under [G01](../docs/architecture/gui.md#g01).
The whole obsolete `ProjectorEditRow` module is also removed: its sole caller was
an old test. That test retains the unique Fit-edit/legacy-default/invalid-value
schema assertions through the live patch operation; existing ImageParameters
coverage still verifies Cover selection and saved state. The post-removal focused
GUI selection passes all three cases. Acquisition and Visual Stimulus cleanup
details belong to their owning reports.
Native buffer-retention references, Qt/gRPC callbacks, model validators and
contract-exported interfaces are retained; an unused-name report alone is not
deletion evidence. Source-only import tracing also retains explicit compatibility
exports, generated-schema adapters and manual/managed module entry points. The
refreshed Vulture advisory falls from 314 hits (290 source) to 299 (275 source);
five 100%-confidence hits remain unused test-double arguments. Lower-confidence
hits remain advisory, without a whitelist or CI gate. The sweep starts from an extensively modified working tree;
[baseline fingerprints](runtime-evidence-2026-10-19/code-sweep/baseline.json)
and [reproduction method](runtime-evidence-2026-10-19/code-sweep/probes.py) preserve
provenance. Initial Ruff, Win32 mypy (826 sources), dependencies and 57 generated
bindings pass. The final backend rerun passes 2,215 tests (six skips, 14 deselections)
with loopback access, resolving all 33 initial sandbox bind failures/errors. The
obsolete `NominalVideoGrid` module and its five self-tests are retired: no source/
contract/entry-point caller remains, and A08/E13 use sequential recording. Current
sequential frame/mapping tests remain. Final Ruff/format (947 files), Win32 mypy
(824 sources), boundaries (722 modules, zero violations), whitespace and source/
wheel builds pass. Wheel inspection confirms removed modules are absent and live
owners match source. Existing cohesion advisories remain with their owning reviews;
no new runtime dependency, architecture rule or hardware setting is introduced.
[Exact commands, provenance and limits](runtime-evidence-2026-10-19/code-sweep/context.json).

The pre-existing CameraTriggerForm test failure reproduces independently: with local
font metrics the three controls fit the requested 298-pixel panel, so expecting a
stacked form is incorrect. The fixture now derives narrow/wide widths from actual
control hints and retains every geometry, value and destruction assertion; all three
narrow/wide/narrow cycles pass. No product layout changed.
[Original failure](runtime-evidence-2026-10-19/code-sweep/gui-reflow.txt),
[geometry probe](runtime-evidence-2026-10-19/code-sweep/reflow-probe.txt),
[corrected check](runtime-evidence-2026-10-19/code-sweep/gui-reflow-after.txt).
The broad offscreen GUI run passes 630 cases and reports only that original fixture
failure. Its collection predates the correction and final unused editor removal;
all three affected final-tree cases pass separately. This is not a fresh full
final-tree GUI or native/rig pass. [Broad result](runtime-evidence-2026-10-19/code-sweep/gui-after.txt),
[final affected cases](runtime-evidence-2026-10-19/code-sweep/gui-removal-final.txt).

Owner-approved Oct19 correction: `subject_history.find_subject_sessions` now selects
by date, then time including seconds, with experiment name only breaking timestamp
ties ([G02](../docs/architecture/gui.md#g02), revision 79). The original probe selected
Zulu 09:00 over Alpha 18:00; it now reports Alpha 18:00. Four ordering cases cover
same-day cross-experiment ordering, date precedence, seconds and deterministic ties.
Before the fix, two cases failed; all six subject-history/reuse cases now pass,
including the existing read-only scan and Setup confirmation checks. Output
reservation, scan limits and stored data remain unchanged.
[Original probe](runtime-evidence-2026-10-19/code-sweep/probes.txt),
[regression failures](runtime-evidence-2026-10-19/code-sweep/approved-ordering-red.txt),
[passing checks](runtime-evidence-2026-10-19/code-sweep/approved-gui-green.txt).
Both approved fixes pass scoped Ruff/format (354 files), Win32 mypy (336 sources),
boundaries (722 modules, zero violations) and whitespace checks. Existing cohesion
advisories remain unchanged. No full GUI rerun, native Windows or rig acceptance
is claimed. [Follow-up provenance and commands](runtime-evidence-2026-10-19/code-sweep/approved-context.json).

Oct16 owner-authorized maintainability implementation follows the Astra architectural
review under ARCH-002/E08/E14. All seven reviewed source changes are implemented;
final integrated validation is recorded in the
[implementation evidence](runtime-evidence-2026-10-16/code-maintainability-review/implementation/context.json).
The [original source review/probes](runtime-evidence-2026-10-16/code-maintainability-review/context.json)
retain their pre-fix fingerprints and reproduction outputs; their reproduction script
is historical and is not expected to run unchanged against removed private APIs.

| Reviewed concern | Current implementation and local evidence |
| --- | --- |
| Required SpikeGLX roles diverged | Fixed: GUI imports the canonical synchronization-owned projection. The original enabled external-trigger Eye mismatch was GUI `[]`, backend `[7]`. The red regression and25 all-camera enable/trigger cases now pass under E12/A01/A11. Physical mappings remain explicit and rig acceptance stays open. |
| MCU numeric acceptance diverged | Fixed: one pure controller-owned `resolve_serial_policies` validates both serial file policies and acquisition defaults under A11/E14. Preserve their common accepted positive uint32 integer baud/ms settings, exact finite seconds/ns, keepalive ordering and exact uint32-ms watchdog.35 configuration cases include17 parity cases. No operator value or fixed policy changed. Ack covers send through complete matching reply, capped by the original operation deadline; no timeout retransmission added. |
| Unary peer mechanics duplicated | Fixed: shared `UnaryPeer` owns bounded channels, principal/deadline metadata, receipt/type checks and close. Tracking and Visual Stimulus retain their own stub selection maps; diagnostics retain backend/method context and no retry is added.26 real authenticated owner transport/runtime cases pass. |
| GUI feature dispatch mixed with connection ownership | Fixed: focused `ManagedActions` receives explicit callbacks and has named device, inventory, display, Tracking, configuration and prompt methods. Bridge drops from777 to451 lines and retains the same thread/queue/safety/configuration-lock/fencing/cancellation methods. AST comparison finds all17 methods outside `_dispatch` unchanged. No whole-runtime feature reference or generic action/plugin framework added. |
| Unused GUI editing remnants | Removed only the121-line `EpochSelection` class, `editable_parameters` and class-only imports. `SelectionComposer` stays live in subgroup editing; eight focused fresh-process GUI cases pass. Other static candidates are not automatically removed. |
| Worker session matching duplicated | Fixed: service/state import one predicate from the existing worker scope helper.90 worker foundation/admission cases include27 session/trial/empty/mismatched-controller/session identity checks. Authorization is not broadened. |
| Recording metric API semantics unclear | Fixed: write/snapshot docstrings specify first-attempt through full-frame consumption, zero-progress gaps, one serialized unfinished input, copied independent stage-max examples and pipe acceptance versus encoding/durability. Existing52 recording cases pass without behavioral/output changes. |

Configured lint/format passes931 files, Win32 mypy809 source files and boundaries710
modules/zero violations. New shared transport and feature-action modules have focused
ownership; existing size advisories remain cohesion-review prompts, not failures.
Final backend integration passes1918 cases, with five platform skips and five
exclusions. The broad offscreen GUI snapshot passes544 cases with one existing
Protocol row-height failure (321px versus <320). A separate process loading the
pre-maintenance GUI adapters reproduces the identical failure; no geometry or test
assertion was changed. All46 bridge cases in that collection passed, and eight
focused fresh-process editing cases pass after the unused-class removal. The broad
GUI collection had545 cases; three concurrent GUI additions arrived afterward and
are outside that broad-run count. Source/wheel builds and wheel inspection pass,
including packaged new helpers and a dev-only Vulture requirement. Vulture2.16 is
installed in the repository environment and its command is available. Exact commands
and limits belong to the implementation context; local checks do not close E15
native/rig/full-workload acceptance.

Vulture2.16 is now a development-only dependency, with generated bindings excluded
and handwritten source/tests/tools/scripts/contract Python included. The documented
commands are advisory: default confidence100 finds five unused test-double arguments
and no production candidate at that threshold; confidence60 finds311 suggestions,
including286 in source. The two deliberately removed GUI symbols disappear from
that scan. Many remaining suggestions are implicit Qt/gRPC/Pydantic/native fields;
a lower-confidence hit is unverified until caller/contract review. No blanket
whitelist, hard CI gate or automatic deletion was added. The temporary install's
first automatic approval review timed out before execution; one approved retry
installed the declared version for evaluation. See the
[upstream false-positive/confidence guidance](https://github.com/jendrikseipp/vulture#handling-false-positives)
and [development commands](../docs/development.md#checks). No new runtime package
is justified; native process identity/Jobs, raw-stdin FFmpeg and distinct scientific
writers retain their owning guarantees.

Contract-exported Tracking protocols/validators remain intentional; Windows
`ensure_owner_only` also has documented historical manual recovery use. Neither
is classified as dead merely from the runtime caller scan. Broader lower-confidence
triage remains a follow-up, with source evidence retained rather than blind removal.

Oct15 projector-off TODO audit at `b68c4ee` runs1,737 projector-independent backend
cases (four skips,26 native/rig deselections) and38 targeted offscreen GUI cases
(470 deselected). Ruff/format911 files, Win32 mypy791 sources, dependencies and
boundaries695 modules/zero violations pass;44 existing cohesion advisories remain.
The existing subgroup regression confirms mixed-identity rule edits are rejected
without discarding the dirty draft, closing the stale `mixed-subgroup-random-rule-edit`
entry. Duplicate task IDs/status sections are consolidated, later evidence is kept,
and obsolete margin/keystone/seam acceptance instructions are replaced by current
G01/V15 pixel-size/offset checks. All projector-dependent and pre-existing hardware
acceptance deferrals remain. No implementation or device settings changed.
[Commands, probes, source fingerprints and limitations](runtime-evidence-2026-10-15/todo-projectors-off/context.json).


Current model-hierarchy audit (`hierarchy-audit-20261012`) starts from
`f96286e86dc9af334da78ab55a8c14ec111c6184` plus existing uncommitted source,
contracts and reports. Concurrent unified subgroup work is preserved and has its
own assessment below. Two fresh-context `gpt-6-luna` high auditors performed one
bounded responsibility pass; `gpt-6.1-sol` high independently reviewed evidence and
routine dispositions, and `gpt-6-astra` low reviewed the proposed change.

| Responsibility | Source-review coverage in this audit |
| --- | --- |
| Controller/shared | Deep calibration/shutdown admission, shared identity/command retention, Start activation/evidence waits; sampled metadata/reservation and snapshot projections. |
| Acquisition | Deep source identity, cutoff/capture, ring synchronization and recording terminal/flush/close; sampled manual devices, sessions and pixel adapters. |
| Supervisor/launcher/platform | Deep launcher replacement identity and atomics; sampled registration/recovery/exit, Windows jobs, pipes, guards and security. |
| Tracking | Deep ring sequence/private lease, record codec, bounded writer and completion; sampled coordinator, trials, methods and feedback. |
| Visual Stimulus | Deep live-calibration identity/sequence/deadline, validation versus uncertain GPU failure, all-output presentation/closure and blackout ordering; sampled compiler, media, recording and feedback. |
| GUI | Deep bounded/atomic JSON and full configuration imports, camera/protocol restoration and source transforms; sampled dashboard, device/projector codecs and widgets. Concurrent subgroup changes were read only. |
| SpikeGLX/MCU/tooling | Deep serialized SpikeGLX SDK/lifecycle paths; sampled MCU timers/parser, policy/configuration, packaging and schema-generation tools. |

This is not an exhaustive branch review. Detailed scientific algorithms, full
compiler/media/encoder behavior and every widget remain sampled or unreviewed.
Native Windows, CUDA/Pylon/OpenGL, DPI, electrical/optical behavior and full-load
performance require the existing [rig checklist](rig-verification.md).

The sole material candidate is **RT-001** (controller correctness/reliability):
`device/display_adjustments.py` omitted the shutdown flag from its locked admission
predicate. `lifecycle/commands.py` sets that flag before asynchronous shutdown
cleanup; ordinary lease authorization and retained active-grid evidence still allow
a fresh update. Luna reproduced Accepted plus one backend dispatch with shutdown
already requested; Sol independently verified reachability and Astra approved the
smallest guard and existing-module regression. The implementation adds the shutdown
flag to the existing locked rejection predicate; an otherwise-valid fresh update
now rejects without dispatch or pending state. The regression preserves successful
updates and resets shutdown before the independent lease-loss assertion. Confidence
is high; this is a defect in the pre-audit dirty tree, not an audit-introduced
regression. Sol accepts the final patch after one test-isolation revision; Luna's
final quality pass found no further justified edits. Astra independently inspected
the final source, test, surrounding admission/shutdown behavior and assessment, then
granted final acceptance: **RT-001 approved and implemented**. This is the complete
candidate list; no rejected/deferred candidate was manufactured.
[V01](../docs/architecture/visual_stimulus.md#v01),
[E06/E08](../docs/architecture/system-contracts.md#e08) already require closure and
fencing; no architecture revision or broader authorization abstraction is needed.
No other material candidate or measured optimization was established; no speculative
refactor/performance improvement is claimed. Oversized-file warnings remain review
prompts, not a reason to split cohesive owners or weaken their guarantees.

Verification uses the repository Python 3.11 environment and preserves E15:
baseline portable non-GUI pytest passes **1,492 / six skips / eight deselections**
after permitting authenticated loopback sockets. The sandbox-only attempt had 28
socket-bind failures/errors, not evidence of a product defect. After the final
patch and Luna quality pass, `pytest tests/controller tests/visual_stimulus -q
-m "not windows and not rig" -p no:cacheprovider` passes **659 / one deselection**
in 10.56 s. The focused admission case also passes; overlapping runs are not added.
Final Ruff check/format `src tests tools scripts` passes (865 files), Win32 mypy
`src/cephvr` passes (748 sources), boundaries pass (653 modules, zero violations)
and whitespace passes. No new responsibility or dependency is added to the focused
adjustment helper; its surrounding calibration owner and existing size advisories
retain their established ownership. Full offscreen GUI verification passes **393**
in 246.07 s with `QT_QPA_PLATFORM=offscreen`; all 146 GUI source/test Python files
remained unchanged during that run. This is portable widget evidence, not native
Windows/DPI/optical acceptance.

Contract unittest discovery passes Tracking 48 and Visual Stimulus 42; schema checks
match 19/11 models. Isolated generation matches all 57 binding files from 19 Protobuf
sources. No contract/config/package input changed during this audit, so those checks
remain applicable; no package build is required by the one-line runtime fix.
Final source/test/contract/config/tool input provenance is 1,025 sorted paths with
SHA-256 `4ef69d74b7bd741e6991dc0b6722b3b4840424676af2137beeb093189057ea8b`
(hash concatenated relative-path, NUL, bytes, NUL for `.py/.pyi/.proto/.toml/.json/
.ps1/.c/.h/.cpp/.glsl`, excluding bytecode, plus root `pyproject.toml`). The only
non-GUI runtime/test changes since the initial inventory are RT-001's helper and
owning test. Raw task evidence is disposable at the owner's request; retain this
assessment and results, preserving all pre-existing and concurrent evidence.
The requested model hierarchy ran without substitution; token/cost metrics were
unavailable. The bounded audit's independent work is complete, with no user decision
required. Existing rig-dependent and explicitly deferred work remains open. Exact
task-owned test directories and generated temporary bindings are removed; existing
caches, raw evidence and user work are preserved. The temporary inventory is removed
last after the lightweight status/reference check; no task background process remains.

Oct13 right-edge refinement (`timeline-edge-alignment`) follows
[G01 revision179](../docs/architecture/gui.md#g01): group blocks omit epoch counts,
retaining repetitions and duration; overall trial totals retain epoch counts.
Both timeline rows remove the extra16px right gutter so trailing add buttons align
with editing-content edges. Seven focused timeline tests, scoped Ruff/format,
Win32 mypy and boundaries682/zero violations pass. Offscreen/native geometry checks
confirm matching sequence/composer widths and flush right add buttons; full dashboard
render reviewed. [Evidence and preview](runtime-evidence-2026-10-13/timeline-edge-alignment/context.json).
Updated Cocoa sample GUI remains open; prior preview preserved. No device/controller
mutation or Windows/rig acceptance.

Oct13 compact timeline refinement (`trial-timeline-polish`) under
[G01 revision178](../docs/architecture/gui.md#g01): left-aligned totals, dark unselected
group blocks, accent selection, separate count/duration lines, subtle footer divider
and Selected group label. Content-based height replaces the320px floor; current sample
is281px on Cocoa. Seven focused timeline tests pass; final scoped lint/format, Win32
mypy and boundary checks pass. ProgramTimeline's502-line cohesion review retains its
existing painting/hit/scroll owner and focused external details/cache helpers.
[Evidence and interactive preview](runtime-evidence-2026-10-13/trial-timeline-polish/context.json)
record native/offscreen visual review. Sandbox launch lacked a screen; authorized native
launch reports PREVIEW_READY and remains open with isolated settings/sample data for
owner inspection. No controller/device connection or Windows/rig acceptance.

Oct13 trial timeline layout (`trial-timeline-layout`) follows
[G01 revision177](../docs/architecture/gui.md#g01): totals above the blocks, compact
selected-group controls below, aligned to the last group's visible right edge during
resize and horizontal scroll. Hide the secondary repetition/count/duration line when
it cannot fit a group block; retain the name and complete hover details. ARCH-002
keeps control layout and painting in their existing focused owners, with one viewport
notification and no dependencies. Seven focused timeline/history/scrolling tests pass;
three offscreen geometry checks and reviewed renders cover one/eight groups at1200px
and eight groups at720px. Scoped lint/format, Win32 mypy, boundaries676/zero violations
and whitespace pass. [Evidence and preview script](runtime-evidence-2026-10-13/trial-timeline-layout/context.json).
Native Windows/DPI and rig acceptance remain unverified.

Oct13 epoch title labels (`epoch-title-labels`) follow
[G01 revision176](../docs/architecture/gui.md#g01): named subgroup headers display
only their name; unnamed headers display Epoch N using existing sequence numbering.
ARCH-002 review keeps this presentation-only change in TimelineViews without new
state or dependencies. A direct model/view probe verifies unnamed numbering,
name-only headers and shared run boundaries. Scoped Ruff/format and Win32 mypy,
boundaries676/zero violations and whitespace pass; no native or rig check is claimed.

Oct13 epoch automatic updates (`epoch-auto-update`) implement
[G01 revision175](../docs/architecture/gui.md#g01): completed text edits and control
changes commit through the existing whole-trial subgroup transaction, without
Apply/Discard footer buttons. Navigation/save flush valid pending changes; invalid
input remains a draft and Undo can discard it. Passive validation never opens a
modal or continuously retries invalid variation inputs. Rebase the reference and
canonical declarations without rebuilding focused controls. Preserve source identities,
projector-local changes, variation seeds, and existing Undo/Redo history. ARCH-002
review retains the focused subgroup owner and existing Qt timers, with no new
dependencies or whole-runtime references. Final focused checks pass12 cases, including motion/fade edits, invalid drafts,
focus, atomic projector-local updates, history, variation persistence and file reload.
The broader run passed451 with six failures: four obsolete explicit-Apply/draft-asset
expectations are updated and pass; the concurrent advanced-control layout now passes.
The remaining texture-import test attempts QImage decoding of JSON before using the
editor. This prevents a clean whole-GUI claim and belongs to the active texture work.
Scoped Ruff/format, Win32-target mypy (two owners), boundaries (676 modules, zero
violations),526 local links/anchors and whitespace pass. Existing boundary size
advisories concern unchanged owners; the affected focused files remain below500 lines.
[Commands, source hashes, logs and offscreen render](runtime-evidence-2026-10-13/epoch-auto-update/context.json)
retain evidence. Native Windows/DPI remains unverified.

An investigation while testing invalid random edits also observed a pre-existing
mixed-subgroup limitation: changing random rules while multiple batch identities
are selected can leave stored rules unchanged and clear the local draft. The same
`apply` path excludes metadata updates for mixed identities. This is separate from
the automatic-update wiring. Oct14 (`mixed-subgroup-random-rule-edit`): `SubgroupEditor.apply`
now rejects a rule change across more than one batch identity with a notice and keeps
the draft dirty; other mixed-selection edits are unchanged. Bulk random-rule editing
remains unsupported. Offscreen regression in the owning subgroup test only; no native
or rig validation.

Oct13 subgroup editing follows [G01 revision175](../docs/architecture/gui.md#g01),
[V03 revision12](../docs/architecture/visual_stimulus.md#v03) and
[V08 revision5](../docs/architecture/visual_stimulus.md#v08). Clicking any member selects
its complete subgroup; parameter edits affect all members/repetitions. One composer
retains variation controls through automatic updates, selection, Undo and file reload. The trailing
subgroup + copies one template without inheriting rules. Order is removed; imported ordering
is preserved. Layer selectors show only indices at 64 px; timeline durations use
hh:mm:ss with fractional precision retained.

Current layout polish matches + heights to trial rows and timeline blocks, uses a
shared-column variation table, and separates correction/measurement calibration
cards with their launch actions above each table. Remove the separate SpikeGLX
inventory-save button; GUI file saving remains local and does not implicitly publish
controller inventory changes. ARCH-002 keeps row validation in BatchVariationRow,
with a focused VariationTable presentation helper and no new dependency. Existing
large GUI owner modules retain their responsibilities; no runtime ownership changes.
[Layout polish evidence](runtime-evidence-2026-10-13/layout-polish/context.json)
records 45 passing focused GUI checks, Ruff/format150 files, Win32 mypy148 sources,
and662 modules with zero boundary violations. Inspect1280/720 protocol captures and
1280 calibration cards; local rendering does not establish native Windows/DPI acceptance.

The selected group's name/repetitions sit below the blocks inside Trial timeline;
Sequence editor begins with subgroup blocks. Reparent the existing GroupEditor and
retain its binding/history, including resizing for imported condition controls.
Removal controls in the protocol use the same `button("×", "compact")` role as the
MCU outputs table, replacing custom 22 px padding overrides. Natural control sizing,
consistent insets, a taller subgroup header and reserved text space avoid clipping
or collision. Trial/group/subgroup and variation-row removal is hover-only; selection
alone shows no cross. The variation row reserves hidden-button space to avoid jumps.
[Card balance evidence](runtime-evidence-2026-10-13/card-balance/context.json) records
53 passing focused GUI checks (including trial/group interactions, layout and MCU
controls), Ruff/format 149 files, Win32 mypy 147 GUI sources, 661 modules with zero
boundary violations and inspected 1280/720 captures. Initial tests relying on selected
crosses or a hidden ungrouped fixture were migrated to explicit hover/group setup.
ARCH-002 keeps
canonical edits unchanged and reuses existing styling instead of adding a new button
style. Native Windows/DPI appearance remains unverified.

Trials and Trial timeline now share a 320 px minimum height and matched caption/header
heights, aligning their painted top borders despite the Preview button. Trials keeps
QListWidget selection and indices, adding a trailing + inside its scrollable viewport
and one reusable × control for the hovered row. No sentinel trial or per-trial
widget allocation is introduced. Existing deletion confirmation now targets the
clicked trial identity, retaining the selected trial when another row is removed.
Saved files, final-trial replacement and authority checks remain unchanged; invalid
pending edits block deletion of another trial. The focused TrialList module owns
presentation only (ARCH-002). [Trial-list evidence](runtime-evidence-2026-10-13/trial-list/context.json)
records 12 passing focused tests and a final interaction rerun, Ruff/format 149 files,
Win32 mypy 147 GUI sources and 661 modules with zero boundary violations. Inspected
1280/720 captures show three trial rows,
trailing addition and aligned borders. Native Windows/DPI checks remain outstanding.

Variation rules now have an always-visible Add variation rule button without an
Enable checkbox. The presence of rows determines active authoring rules; Apply and
reload preserve them, and removing the last rule clears compact execution rules on
Apply. Legacy inactive drafts do not silently become active on load. No schema or
runtime sampler change is needed. ARCH-002 removes redundant widget activation state
and uses shared table columns with horizontally scrollable narrow layouts. The
Layer control retains a Fixed size policy and 64 px width: an Ignored policy previously
allowed the grid to allocate less than its actual width, overlapping Parameter.
The owning layout regression checks adjacent geometry, equal heights, All layers,
Values/Sweep/Random and 1280/720 widths; persistence checks cover last-rule removal
and Undo. [Variation layout evidence](runtime-evidence-2026-10-13/variation-layout/context.json)
records 40 passing focused GUI tests, Ruff/format (148 files), Win32 mypy (146 sources),
660 modules with zero dependency-boundary violations and inspected 1280/720 offscreen
captures. These checks cover this increment; the preceding full GUI run is historical. An initial
layout test inspected a hidden legacy editor; opening its group exposed and verified
the actual column-overlap fix. Native Windows/DPI acceptance remains unverified.

Inline group/subgroup actions replace the + Group, − Group and + Epoch toolbar
buttons. A trailing + appends and selects; a top-right × appears only on hover
and targets that block, independently of prior selection. Subgroup deletion removes
all members; final-block removal remains disabled. Existing draft-validation,
authority, minimum-duration validation and Undo transactions remain authoritative.
ARCH-002 uses a focused presentation helper with explicit path signals and a small
reused button pool sized to visible blocks. No widgets are allocated per repetition.
The obsolete responsive header-action stacking is removed now that only Preview
remains. Offscreen 1280/720 captures show readable crosses and trailing additions with
no horizontal page overflow; no native interaction or rig validation is implied.
[Oct13 evidence](runtime-evidence-2026-10-13/inline-actions/context.json) records
31 focused passing cases and the final full GUI suite with 398 passes. Ruff and
format (148 files), Win32 mypy (146 GUI sources), dependency boundaries (660 modules,
zero violations), local links and whitespace checks pass. Initial checks
caught a QWidget.actions name collision, clipped cross padding and a deletion test
fixture violating the retained minimum trial duration; all were corrected without
weakening runtime validation. Earlier compact-rule evidence below remains historical
for the execution path, which this UI increment does not change.

Random rules now store compact executable seeded declarations; the earlier 2000
random-occurrence authoring limit is removed. GUI work samples only representative
source settings. Changing repetitions retains rules/seeds and the existing sampled
prefix. Random access uses the immediate-group repetition index and source-member
stride/offset, independently of shuffle; target streams default to independent
projector values, with explicit sharing. Independent draws may coincide. Setup
checks its configured expanded-plan bound (currently 100,000 epochs) before resolving
rules to validated concrete settings; rendering does not sample. Legacy concrete
tables remain readable. Explicit source-list generation and expanded/animated
previews retain their separate 2000-item limits.

ARCH-002 extracts existing pure numeric setting patches and precision-grid sampling
into Visual Stimulus configuration helpers, reused by GUI and compiler. The compact
rule model and random-access resolver have focused ownership; no new dependency,
process or renderer changes. Canonical schema validation remains a cohesive owner
with an existing size advisory. Source/prepared schemas match their models. Structural
checks at 10,000 and 1,000,000 repetitions confirm unchanged rules, one source block,
one representative resolution per edit and essentially constant serialized size.
This does not establish full-workload latency or memory guarantees: Setup's concrete
plan still scales with expanded epochs; image streaming remains separate pending work.

External authoring samples can be regenerated with the
[demo asset generator](../tools/generate_demo_assets.py); the local review assets root remains.
Inspected 1280/720 offscreen captures show image/gray ×10,000, clock labels, no Order,
narrow readable indices and no horizontal page overflow. A first capture exposed a
minimum-width reset hiding the variation index; moving the fixed-width assignment
after common control setup corrected it. Existing review instances require reopening;
this increment did not restart the user's application.

Current evidence is in the [manifest](runtime-evidence-2026-10-12/compact-rules/context.json).
Visual Stimulus passes 233/one deselection with loopback access; compilation passes 11.
The full GUI stage passes 396 with one obsolete index-label expectation failing;
the final 12 focused cases pass after migrating that assertion
and the final layer-width correction. Earlier focused failures identified strict
settings conversion and random-only source-count preservation; both were corrected.
Tests cover golden deterministic samples, source round-trip, group-count bounds before
sampling, independent/shared values, retained rules, and compact million-repeat edits.
Ruff/format (171 files), Win32 mypy (168 sources), all 11 generated schemas
and dependency boundaries (659 modules, zero violations) pass. Stages overlap and are not summed as a single exact-final-tree run.
Native Windows/DPI/rig acceptance remains in the [rig checklist](rig-verification.md).

Reusable configuration files (2026-10-08, `gui-configuration-snapshots`):
[G01](../docs/architecture/gui.md#g01) revision 132 and the
[snapshot contract](../contracts/gui-configuration-files.md) govern complete Protocol,
Microcontroller, portable Projector, SpikeGLX and Tracking files plus full GUI files
from sidebar controls. All loads prevalidate local drafts; atomic saves preserve
existing files. Full files retain metadata, recording choices, camera serials/roles
and explicit display assignments; incompatible inventories reject before restore.
Loaded camera/MCU values survive polling and join ordinary E07 proposals; changed
PFS paths require A10 SDK import. Inactive Tracking remains a local pending draft
until enabled. SpikeGLX rows persist through GUI Save/Load without a separate
pulse-mapping save button or automatic controller inventory writes; saved host/pairing
references cannot override startup TOML or current file digest. Firmware, camera
capture and projector output never start on load. Local validation completes:
initial full GUI run passes 368; final full run passes 367 with two outdated
SimpleNamespace projection-interface mocks failing. Correct both fixtures without
weakening their assertions; post-review owner checks pass 49 and three direct
projection/fixture cases pass. Ruff lint/format pass 138 GUI/test files, Win32 mypy
passes 136 GUI sources, boundaries inspect 632 modules with zero violations, and
732 local links/anchors plus ten register checks and whitespace pass. Retain
[raw JUnit, source hashes and method limits](gui-configuration-evidence-2026-10-08/context.json),
plus inspected offscreen sidebar (local-only `gui-configuration-evidence-2026-10-08/sidebar.png`),
MCU (local-only `gui-configuration-evidence-2026-10-08/microcontroller.png`) and
SpikeGLX (local-only `gui-configuration-evidence-2026-10-08/spikeglx.png`) images. No running
managed runtime is restarted or native chooser/hardware pass claimed;
[rig checks](rig-verification.md) retain native chooser/DPI and hardware acceptance.
ARCH-002 review keeps file IO and snapshot codecs in focused modules, with existing
page/device owners retaining widget/operation state. Existing large cameras/MCU,
Tracking and main files receive only draft guards/callbacks; no new runtime reference,
process or dependency is added. Projector orchestration remains unchanged.

Current calibration/output-unit work (2026-10-08, `physical-reference-calibration`):
the [Tracking](tracking.md) and [Visual Stimulus](visual_stimulus.md) assessments own
G01/T20/T38/V15 implementation and evidence. Per-screen raw-pixel bars replace editable
throw distance with measured X/Y scale and a derived estimate; Tracking requires camera
scale and publishes mm/s/deg/s proxies. Explicit old input/gain editing and versioned
files prevent silent reinterpretation. Affected checks pass 658 (one skip; two concurrent
temporary-pacing checks excluded plus one rig deselection), with post-review owning
checks passing. The offscreen card (local-only `tracking-evidence-2026-10-08/physical-reference-gui.png`)
is visually checked. No managed runtime restart or physical calibration is claimed;
native/DPI/optical/scientific/full-load acceptance remains in the rig checklist.

Unpaired dummy execution follow-up (2026-10-08, `gui-backend-dummy-experiment`):
the owner explicitly disables SpikeGLX pairing and approves temporary 1,000 ms
post-cutoff drain allowances for both cameras. Front 60 Hz pacing and the managed
wrapper's high-performance Windows graphics preference are temporary diagnostic
inputs; strict RTX 5060 Ti identity/framebuffer checks remain enabled. Real Setup
attempts now run, preserving each failed Desktop reservation and exact generation
exit evidence before controller recovery. This early-attempt account is historical;
run43 completion and its remaining cadence limits are summarized above.

Native attempts expose and repair E08 Configuration-heartbeat handoff, E04 missing
path-free Setup output identities, exact terminal Setup failure admission, empty
arena-boundary submission, GLFW fullscreen focus loss, private renderer-completion
routing, revision-zero cleanup catalogue initialization, CPU-to-GL video binding,
normal renderer-owned FFmpeg helper exit retention and duplicate WGL destruction.
The [Visual Stimulus assessment](visual_stimulus.md) records graphics/probe details;
the [Acquisition assessment](acquisition.md) records camera and shared encoding scope.
ARCH-002 reuses focused planners/ports/ledgers and existing behavior test modules;
no process, dependency, deadline or resource-proof exception is introduced.
Run43 supersedes these early attempts; remaining throughput and native acceptance are
in the rig checklist. [Raw attempts](rig-wiring-evidence-2026-10-08/dummy-experiment/).

GUI/backend dummy-experiment work (2026-10-08): the owner authorizes wiring/fixes
and a Desktop-output dummy run, explicitly retaining both camera videos and stimulus
video while disabling velocities. Eight reproducible Windows Qt layout failures
are repaired under [G02](../docs/architecture/gui.md#g02): shrinkable field/status
labels, tab elision, responsive protocol management, and targeted title wrapping
prevent minimum-width feedback without changing device ownership. The final owning
GUI suite passes **334 tests**. The first all-owner suite passes 1560, skips five,
deselects one rig case and exposes two GUI regressions; both are repaired and the
final complete GUI rerun covers them. No test assertion was weakened.

Later native inspection identifies two additional wiring/closure defects. Backend
camera-role adoption leaves Dashboard recording names at “Unassigned video”; the
recording owner now updates names/accessibility during view refresh without toggling
choices or marking drafts dirty. Both inventory-row regressions fail before and pass
after; native reopening confirms Behavior/Tracking names. Normal GUI close with an
incomplete protocol incorrectly reports history-save failure before sending a save.
It now saves the accepted controller configuration, with explicit discard/cancel
choice for unsent drafts, under E07. Four regression cases fail before repair; ten
focused close/recording cases pass afterward. Native discard/save closure exits the
GUI, preserves original configuration/history and leaves the session in Configuration.
The repaired GUI is reopened afterward. ARCH-002 keeps both changes in their small
existing recording/close owners with no new callbacks or state. Final all-owner
validation, including all 338 GUI cases, passes **1566 tests, five skips and one
rig deselection in 171.33 seconds**. Ruff lint/format, Win32 mypy and boundaries
pass again. [Final JUnit](rig-wiring-evidence-2026-10-08/dummy-experiment/final-all.xml),
[source/method context](rig-wiring-evidence-2026-10-08/dummy-experiment/context.json).

[E07](../docs/architecture/experiment.md#e07)'s application-shutdown history save
now shares the existing atomic writer and serialization lock. The history deadline
covers queueing; shutdown interruption/handoff retain their original deadlines and
run independently of that writer. Owning tests cover gated shutdown persistence,
queue timeout and failed-write preservation. ARCH-002 keeps these responsibilities
in the existing focused configuration/command owners, with one injected callback;
no runtime back-reference, dependency or policy choice is added. Ruff lint/format
pass 260 files; Win32 mypy passes 229 sources; boundaries inspect 620 modules with
zero violations. Existing cohesive source-size advisories remain review prompts.

Real GUI dispatch confirms both camera connection checks, bounded capture/disconnect
and Arduino connection. SpikeGLX diagnostics reach the remote server but find an
already-running acquisition; the empty pulse inventory also prevents pairing.
An invalid standalone MCU Status probe is correctly rejected because no pin
diagnostic is active; it is test-method error, not a backend defect. Native screen
inspection confirms assigned camera controls. Saved native projector identities
and rig geometry produce explicit **uncalibrated diagnostic** profiles and a
60-second procedural-grating protocol; this does not certify optical accuracy.
Before loading repairs, explicit history saving, normal shutdown, matching exit
receipt and application-guard release pass for generation
`93cbe363-06ee-419c-b55f-8e14fcf600ce`. The repaired runtime then persists a temporary
accepted experiment-name marker through **ShutdownApplication without a separate
save command**, confirms exact exit, and reloads it in a new generation. Restore
and save of the original configuration pass. Pure dummy-proposal validation passes
experiment/acquisition/inactive Tracking but rejects Visual Stimulus because V20's
explicit pacing-output identity is unset. Automatic approval review separately
rejects the proposed configuration/real Setup action for unavailable display
coordination and unresolved pairing against an active remote acquisition; **no
dummy configuration submission, Setup, Start or recording occurred**. Owner choices
for pairing and pacing are pending. Native wide-window camera controls render
correctly; the attempted drag did not resize the window, so narrow native/DPI
acceptance remains open. [Dated raw checks](rig-wiring-evidence-2026-10-08/dummy-experiment/).

Latest `.ino` upload shutdown (2026-10-08, E08/A11): owner emergency identifies
JOB_INSPECTION_FAILED; a controlled GUI-command-path upload reproduces executable
query WinError 5 for a compiler job member, followed by TerminateJobObject WinError 5.
The focused native inspection now waits at most one millisecond for the exact
process exit signal after failed identity queries, within the existing three passes;
unverified live processes still raise. Reopened launch-owner job handles now request
the required termination right, retaining exact contained ownership. Native regression
reproduces the missing-right failure before repair and passes afterward. Three
upload cycles pass after the exit check, then two final compile/verified-upload cycles
and deliberate compiler rejection pass with both repairs; rejection preserves serial
identity and confirmed cleanup. Affected platform/supervisor/firmware-owner/shared
tests pass 199 with one skip; static checks and 619-module boundaries pass. ARCH-002
keeps the small native-handle changes in the existing API owner with no dependency,
policy or firmware-source changes. Current settings were not edited. Exact exit,
guard/COM/helper release and removal of one archived failed-attempt staging directory
are confirmed; runtime remains stopped. Full-load and interrupted-flash acceptance
stay in the rig checklist. [Dated method/results](rig-wiring-evidence-2026-10-08/README.md#ino-upload-native-job-correction).

Output-format comparison (2026-10-08, `output-format-comparison`): inspected the
sibling CephVR1.0 writers/schema-v5 registry and saved October 6 session
`C:/Data/projects/reiter-cephalopod-vr/cephvr-data/20261006_ephys-pilot/SP0002-151412/protocol-data`,
then compared current CephVR2.0 output planning and all three scientific writers.
The existing date/experiment/subject-session layout and `protocol-data` /
`spikeglx-data` split are shared. [E04](../docs/architecture/supervisor.md#e04)
removes trial-number filename suffixes, adds UUID identities, replaces session-summary
JSON with lifecycle JSONL, and uses `SCHEMA.json` instead of `SESSION_SCHEMA.json`.
[A07/A08](../docs/architecture/acquisition.md#a07) replace acquisition/video CSV pairs
with one camera JSONL stream containing received frames, drop/video correspondence,
clock descriptors and terminal accounting. The Oct9 implementation adds identified
nominal-slot padding under A07/A08 and E13/V12; the owning
[acquisition](acquisition.md) and [stimulus](visual_stimulus.md) reports retain current
validation and native limits. The historical 1.0 example reports five padded Behavior
frames and nineteen duplicated VR frames.

[T15/T19](../docs/architecture/tracking.md#t15) replace `_tracking_state.csv` with
typed pose/result/reset/discard/completion records. The owner's subsequent decoded
storage choice replaces base64 feedback/escaped stage payloads with schema-2 JSON
objects; [implementation evidence](tracking.md) records local checks and limits.
[T35/T38](../docs/architecture/tracking.md#t35) use relative drive
in px/s and 1/s, not the legacy mm/s/deg/s velocity columns.
[E13/V13](../docs/architecture/visual_stimulus.md#e13) replace separate VR/stimulus
CSV state files with the always-retained prepared `_stimulus_LOG.json` plus Save On
render evidence/review video. The review video samples final corrected output tiles;
the legacy recorder captures its dashboard composite. Current SubjectMetadata moves
animal details into session configuration, uses `size_mm`, adds condition, and has
no legacy `weight_g` field. These are format/semantic changes, not a migration or a
claim that old readers can consume the new files.

Evidence scope: 16 `SESSION_SCHEMA.json` files and no 2.0-style session/schema/
scientific JSONL files were found by filename inventory in the inspected data root.
The 2.0 side is source/schema inspection at HEAD `7ba43b1` with concurrent local edits,
not an inspected production scientific session or new runtime/rig pass. The sibling
main ref reads `1082d917`; its dirty status could not be checked through `git -C`
under current permissions, so that ref alone does not identify the reviewed source
snapshot. No recording, device, runtime or scientific-data mutation ran.

Projector assignment retention (2026-10-08, G01 revision 130): explicit choices sync
immediately to local frontend preferences by stable display identity, including
Unassigned/missing displays, independently of a complete calibration or GUI closure.
A new Configuration/Ready GUI restores these as drafts and marks differences dirty;
active-session synchronization and explicit reload retain the controller base. Saved
mapping identity never changes controller state or triggers output. Profile install
now synchronizes the visible assignment dropdowns silently. Invalid/duplicate saved
preferences remain preserved and reported; failed writes retain the current draft.
The initial four restart/managed cases fail before repair. Final owning projector,
calibration and managed-configuration selection passes 53 with one existing horizontal
scroll/layout failure, already present in the earlier full suite. New retention cases
cover restart without closing/Setup, reordered/missing/returning inventory, explicit
Unassigned, invalid preferences, failed save, active-session isolation and explicit
reload. Ruff/format, four-source Win32 mypy and 619-module boundaries pass.
ARCH-002 puts bounded preferences/validation and silent control synchronization in
a focused helper; the existing Projectors panel retains UI/native inventory ownership.
No dependency/process or controller-history writer is added. These are isolated Qt
settings/display fixtures; actual multi-monitor restart/unplug acceptance remains in
the rig checklist. No hardware command or managed runtime restart ran.
[Raw validation and source context](rig-wiring-evidence-2026-10-08/projector-assignments-context.json).

Camera Disconnect presentation (2026-10-08, G01/G02): the button now uses the shared
red danger style for a connected camera and returns to primary styling when closed
or selecting an unconnected camera. Three existing camera-control Qt cases pass;
offscreen theme checks confirm the actual red/primary palette and both transitions.
Ruff/format, one-source Win32 mypy and boundaries pass. ARCH-002 keeps this small
presentation update in the existing cohesive camera refresh owner, without new
state or dependencies; no hardware command or managed restart ran.

SpikeGLX table presentation (2026-10-08, G01): the Stream column is hidden from
the mapping table while retained stream identity continues to roundtrip internally.
Five existing owning Qt panel cases pass; an offscreen rendered table confirms
zero Stream width and aligned visible columns after adding a custom row. Ruff,
format, single-source Win32 mypy and 618-module boundaries pass. ARCH-002 uses
the existing table's column visibility without new state, dependency or schema.
This presentation check sends no runtime/remote command.

Later G01 camera-selection increment (2026-10-08): selected config reloads after
managed inventory assignment changes, and Use-checkbox clicks select their row.
Camera/PFS Qt tests pass 27; selection is silent and preserves per-camera drafts.
Static/boundary checks pass. Earlier full-suite/physical results below predate
this increment. [Current evidence](rig-wiring-evidence-2026-10-08/README.md#later-camera-selection-correction).

Latest Windows/device execution (2026-10-08): reviewed committed `e4c653c..7ba43b1`
and repaired three observed integration defects under A11/E08/ARCH-002: invalid
diagnostic-stop after firmware reconnect, an extra native pipe-creation argument,
and invalid diagnostic-stop during control-release cleanup. Existing OFF proof,
deadlines, ownership and failed-close fencing remain intact; an unacknowledged
diagnostic Start remains uncertain until confirmed Stop/cleanup (owning regression
coverage, without physical missing-ACK injection). Real controller-owned
MCU diagnostics with acquisition disabled, supervised HEX upload and `.ino`
compile/upload, deliberate compiler rejection without serial handoff, active-D9
control release and final exact shutdown/COM cleanup pass. Behavior capture/display
and moved-GUI native placement pass twice. The later Tracking repair validates both
exact producer rings at Ready and release; the previous generic health shutdown was
a rejected-report path, not an established heartbeat timeout. Two physical Tracking
Connect/Show/Disconnect cycles now pass with restored settings and exact normal
shutdown. Failure reporting retains a bounded specific reason without relaxing
fencing/deadlines. Acquisition/affected-controller checks pass 363 with one skip;
affected static/boundary checks pass.
[Current Tracking evidence](rig-wiring-evidence-2026-10-08/README.md#tracking-connect-and-release-correction).
SpikeGLX still times out with a late unretrieved future failure. Eight existing GUI
clipping failures remain.

Earlier full Windows/offscreen suite (before camera-selection/Tracking repairs): **1463 passed, 8 failed, 5 privilege skips, 1 rig
deselection**. Separate native GPU smoke passes one; affected Ruff/format, Win32
mypy and boundaries pass. Baseline contracts/schema checks and native package build
pass. Test fixture path/privilege and asynchronous settlement/clock repairs are
distinct from the three product repairs. [Current dated methods, exact source
provenance, raw outcomes and cleanup](rig-wiring-evidence-2026-10-08/README.md)
retain every failure and scope. Runtime is stopped; saved settings are retained.
Remaining acceptance belongs to the [single rig checklist](rig-verification.md).
The original development-only migration assessment below predates this execution.

Controller Microcontroller ownership (2026-10-08) implements
[A10 revision 55](../docs/architecture/acquisition.md#a10),
[A11 revision 40](../docs/architecture/acquisition.md#a11),
[E08 revision 166](../docs/architecture/system-contracts.md#e08) and
[G01 revision 129](../docs/architecture/gui.md#g01). The controller owns the single
serial thread, boundary/keepalive arbitration, Configuration pin tests and supervised
`.ino` compilation / `.hex` upload. These operations work with acquisition disabled
and no acquisition service. Acquisition is an authenticated camera-trigger client;
its original deadlines, stop issuance and timing evidence survive the RPC hop.
CONNECT creates an exact claim; stale-claim calls cannot alter a later connection.
The final external manual preview releases its claim after OFF and camera cutoff;
remaining external previews retain ownership. Independent Snapshot Microcontroller
state prevents old camera reports from overwriting device/diagnostic state.

Control-loss cleanup waits for the camera claim's original release allowance while
fencing new execution and admitting OFF/release. Normal shutdown includes physical
COM/native cleanup in its retained cleanup/recovery deadline, clamped by the
application backstop. Failed closure remains visible and fenced. Serial timing reload
requires a released port; a connected owner cannot silently change watchdog policy.
The local review GUI now opens no COM handle, including real-inventory mode; device
tests use the managed GUI. Microcontroller config/policy pair 1 owns generic defaults
and fixed policy, with a canonical digest; acquisition pair 18 retains camera defaults
and distributed compatibility fields. The existing pyserial 3.5 dependency now belongs
to the base install, independent of acquisition extras.

Final portable command covering acquisition/controller/supervisor/shared/client passes
**812 tests / 5 platform skips / 3 marker exclusions** (12.21 s). Fifteen real authenticated
loopback controller tests pass (1.14 s), including forged/stale peer rejection, exact
metadata deadlines/replay, disabled-acquisition pin tests and `.ino`/`.hex` Upload,
independent state, normal shutdown and control-loss claim ordering. Eleven offscreen
GUI Microcontroller/firmware cases pass (6.94 s), including read-only review behavior,
cleanup/failure gating and clearing retired diagnostic/connection state. These
checks exercise mocked device/tool boundaries, not native board flashing or physical
camera timing. Ruff check/format pass 491 files; Windows-target mypy passes 427
sources. Boundaries inspect 616 modules with zero violations; existing size advisories
retain their cohesion review. All 19 protobuf bindings regenerate. Five edited TOMLs
parse; canonical acquisition 18/Microcontroller 1 load. Twelve documents / 490 local
links and anchors pass, and whitespace is clean.

ARCH-002 review keeps runtime/assembly/service as composition/transport and the
rehomed serial owner as the existing single-connection state machine; its protocol,
channel, pulse scheduling and serial adapter remain separate. Device, firmware source,
image/tool/handoff, authenticated admission, lifecycle, health and bootstrap are focused
modules with records/callbacks rather than whole-runtime references. Acquisition's
old keepalive/firmware handling and the review GUI serial worker are removed.
Manual Preview retains the single stop/cutoff/transfer/remaining-output coordination
chain with focused helpers; its new claim-release operation lives in the existing pulse
observation helper. Retained OFF proof allows an uncertain closing bridge to finish
cleanup without attempting fresh commands on it. Cancellation uses the caller's
original deadline rather than an invented transport allowance.

The earlier selected-sketch increment passed 26 firmware/source cases, four offscreen
GUI cases and 771 portable backend/shared cases before this ownership migration;
those are historical development results at acquisition policy 17. Current raw board
installation evidence keeps its original ownership/source scope. All results refer to
the shared uncommitted tree at HEAD `e4c653c`, not an immutable rig revision. The
AMD64-Windows native packaging guard blocks `python -m build --no-isolation` here on
macOS; no packaging pass is claimed. No actual Arduino CLI compilation, flash,
hardware command or GUI/runtime restart ran. Full restart with the new config/policy
files is required before rig testing. Installed CLI, Uno AVR core and sketch libraries
remain prerequisites; native/device/timing acceptance stays in the
[single rig checklist](rig-verification.md#managed-mcu-and-camera-gui-verification).

Projector identifier wording (2026-10-08), [G01 revision 127](../docs/architecture/gui.md#g01):
shared review/runtime mapping table and related labels use Display ID. The existing
inventory/layout check passes; numbering and physical mapping behavior are unchanged.


Projector JSON update (2026-10-08), [G01 revision 126](../docs/architecture/gui.md#g01):
one Load JSON / Save as row restores all Projectors experiment settings and reusable
geometry/color profile references, preserving current physical assignments. Version 3
restores pulse/participation by logical face; numeric versions 1/2 and legacy runtime
profiles remain supported. Offscreen 1280×900 inspection confirms the compact shared
page without the redundant import button; its temporary image/settings were removed.
No hardware command or managed-runtime restart ran.

The full portable GUI run records **313 passed / 2 failed in 251.47 s**: one new
roundtrip test had an incomplete inventory fixture (corrected; the focused seven-case
file/native-profile check passes); the untouched Protocol advanced-alignment check
showed a 12 px displacement but passes on independent rerun. It remains an explicitly
tracked intermittent follow-up, so this increment claims no blanket GUI-suite pass.
The added native-rebinding test validates the submitted profile through the backend's
JSON model, with measured-reference/shared-output preservation and current monitor
properties. Ruff lint/format pass six affected files, Windows-target mypy passes five
sources, and boundaries inspect 608 modules with zero violations. Final projector/tank/
calibration selection passes **40 in 30.60 s**; three final install/roundtrip cases pass
in 4.38 s after retaining the authoritative-state profile reset (empty/new state cannot
reuse prior runtime references). Physical projector,
Windows/DPI and optical acceptance remain pending under E15.


Review/runtime layout parity follows [G01 revision 125](../docs/architecture/gui.md#g01)
and [G02 revision 34](../docs/architecture/gui.md#g02): both actual window compositions
retain shared DashboardWindow pages. Camera Connect starts capture and opens the
confirmed run's backend-owned preview; Disconnect stops both. PFS/source/rate restore
per camera, with filename-only PFS display. Device hover colors remain stable; Tracking
places Load/Save beside Pipeline and diagnostics/annotation in a separate action row.
Controller authorizes and owns explicit Configuration-only firmware Upload,
serial handoff, the supervised native helper and fresh stopped-output verification
under [A11](../docs/architecture/acquisition.md#a11)/[E08](../docs/architecture/system-contracts.md#e08).
Details and rig limits are in [acquisition](acquisition.md); always-grid calibration
asset changes are in [Visual Stimulus](visual_stimulus.md).

Matched-state checks compare controls and card/header geometry at 1280/720 across
navigation and all subtabs; offscreen render inspection confirms Cameras,
Microcontroller and Tracking layouts at both widths. The older Tracking-crop draft
migration fix preserves the annotation dictionary; the owner's saved file previously
restored twice with unchanged hash, while invalid files remain preserved/reported.
The final portable GUI command passes **309 tests in 226.30 s**. Acquisition/controller/
supervisor/shared suites pass **748 in 12.01 s**, with five Win32-atomic ring skips
and three marker exclusions; this shared-tree run includes concurrent runtime work.
Ruff lint/format pass 525 files, Windows-target mypy passes 454 sources, and boundary
checks cover 607 modules with zero violations. All 19
Protobuf sources were regenerated from owning schemas. Native Upload, camera output,
Windows/DPI clipping and optical calibration remain rig acceptance. The updated
isolated review GUI is open after approved desktop launch; native visual inspection
is not claimed and no hardware/controller command ran.

The owner has reopened the runtime and reports incorrect preview placement. Native
read-only bounds reproduce insufficient space for the default square and x=0
fallback over the GUI. Placement now fits available right-hand space and aligns
visible physical frames under G01 revision 123. Ten selected GUI checks, four final
native/reader checks and 549 affected-owner/client checks pass (two privilege skips);
static checks pass. Current runtime ownership is preserved; full restart and actual
camera viewing remain outstanding. [Current camera placement assessment](acquisition.md#current-windows-wiring-checks).

Owner-requested stop: controller `73987d0f-0d80-4f63-a646-3dba430048bb`
normally shuts down successfully. Exact launcher exit receipt confirms all owned
processes absent; independent native inventory finds zero managed Python processes
and the application guard is free. Runtime was left stopped for that request, with no repeated
firmware installation or restart. [Shutdown evidence](rig-wiring-evidence-2026-10-07/mcu-installation-and-preview.md).

The earlier owner recurrence was traced to MSIX AppData virtualization, not a missing
publication delay. The owner's ordinary CMD reports File Not Found, while native
agent CMD on the same volume sees the logical path. GetFinalPathNameByHandle
resolves that file into Codex's package `LocalCache/Local`; all inspected user SIDs,
integrity and UAC flags agree. [Decisive file identity/token evidence](rig-wiring-evidence-2026-10-07/replacement-msix-visibility.json)
and [read-only idle controller state](rig-wiring-evidence-2026-10-07/replacement-msix-before-state.json)
are retained. Microsoft's [MSIX virtualization rules](https://learn.microsoft.com/en-us/windows/msix/desktop/flexible-virtualization)
explain this merged view. The owner now authorizes moving the namespace. E08 revision
170 selects `%USERPROFILE%/.cephvr2/runtime`, outside AppData, using the existing
private ACL and credential/recovery helpers. Missing or relative USERPROFILE fails
without an AppData fallback. ARCH-002 review retains the single root selector and
existing exact replacement event/exit-receipt mechanism; no new service or state
owner is needed. Normal shutdown precedes guard-exclusive preservation of all 136
recovery records, with identical source/destination hashes and originals retained.
Old endpoint/generation credentials are not imported; startup provisions fresh ones.

Oct9 recurrence: the owner again reports the ordinary-terminal endpoint timeout.
The current Codex child shell sees the descriptor for controller
`ebb927d3-ad19-4f61-b52b-a906cdb44a57`; the owner's exact base-Python launch command
shows Y/N here, and answering N preserves that generation. Launcher/shared
credential/recovery baseline tests pass 66 with one privilege skip. The initial
baseline command named a nonexistent test file and collected nothing; retain it
separately. [Baseline method and provenance](review-evidence-2026-10-09/runtime-replacement-baseline-context.json)
remain historical diagnostic evidence. After the authorized move, the owner's exact
base-Python command reaches Y/N in native exec PTY: N preserves the exact controller
generation; Y starts a new generation only after the former launcher's matching
all-owned-processes-absent receipt. A Codex child shell and a Windows Shell-launched
helper independently resolve the endpoint to the same physical profile path and
exercise the real N branch with injected interactive input. Both report no package
identity (API result 15700); artifact tags are launch-context labels, not evidence
of a packaged process. The owner's own terminal has not been manually retested.
Final GUI relaunch succeeds in the same idle controller generation; retained V20
pacing warning still blocks new experiment Setup. An early final-start attempt
entered the duplicate prompt before launcher exit; retire only its verified task
helper and retry after exact release. Preserve failed-attempt logs alongside
[current commands, source hashes and native outcomes](review-evidence-2026-10-09/runtime-root-context.json).

The preceding duplicate launch failed before Y/N because its replacement descriptor was
absent. Current read-only inspection finds the earlier controller
`73987d0f-0d80-4f63-a646-3dba430048bb` endpoint intact in the normal Windows
profile, and the owner's exact base-Python command now displays Y/N; two native
checks answer N and preserve it. The original failure's runtime path/timing are
unknown, so startup timing versus a different profile directory is not proven.
Source exposes guard-before-publication timing; [E08 revision 163](../docs/architecture/system-contracts.md#e08)
now bounds missing directory/descriptor retries by the existing startup
health-silence budget. Unsafe/invalid records still fail immediately, and the
exact event remains retained before asking. Persistent absence reports the exact
path; ordinary native launch failures print a concise error instead of a traceback.
Five owning regressions fail before the change; 37 launcher cases pass after,
219 shutdown/supervisor/shared/client integration cases pass (one privilege skip),
and three real delayed-publication/private-event checks pass, including a missing
initial runtime directory. Ruff/format (eight files), Windows mypy (six launcher
sources) and boundaries (604 modules, zero violations) pass. ARCH-002 keeps the
retry in the focused replacement owner and startup-budget injection/error rendering
in launcher composition; no policy, dependency or process owner is added.
[Dated replacement evidence](rig-wiring-evidence-2026-10-07/replacement-context.json).
No live Y/termination/restart or device operation occurs in this repair.

Earlier [manual installation and camera retest](rig-wiring-evidence-2026-10-07/mcu-installation-and-preview.md)
verifies protocol-3 Uno upload/CAPS, generated D9/D10/D11 counts, managed D9/D10/D11
Test/Status/Stop and D9 automatic timeout. Real Behavior HighGUI Start/Show/Hide/native close/reopen/Stop
passes with acquisition-owned native window. Tracking's readback revision handoff
is repaired (54 focused, 535 integration passes/two privilege skips; static checks
pass), but its subsequent Start fails amid recurring coordinator-health shutdown.
Exact launcher absence is confirmed before restoring a fresh GUI runtime.
Firmware installation is complete. The later Oct8 exact two-ring repair supersedes
this Start failure; sustained/full-workload acceptance remains open.

Earlier owner D10 test fails without pulses. The camera diagnostic now applies its
selected output configuration before starting; controller completion forwards
the backend rejection message and accepts the matching protocol-3 version.
Seven targeted regressions and **526 acquisition/controller/client tests pass**
(two privilege skips); static checks pass. This corrects a protocol-version gap
missed by the previous counted suite. Runtime restart/manual installation and
actual generated counts were pending at that repair's handoff; the authorized
installation above supplies later board evidence.
[Current MCU diagnostic assessment](rig-wiring-evidence-2026-10-07/mcu-camera-diagnostic-repair.md).

Latest MCU diagnostic implementation follows the owner's choice to count generated
transitions on the board under [A11 revision 37](../docs/architecture/acquisition.md#a11).
Protocol 3 host/firmware are prepared; counted changes were validated at policy 13.
Concurrent camera-viewer policy 14 retains MCU protocol 3; 45 owning cases pass again.
GUI reports firmware-generated
counts separately from observed input edges. The Uno image builds; 508 affected-owner
integration cases and six focused GUI cases pass (two integration privilege skips).
Source mypy, Ruff/format and boundaries pass. Matching manual installation and on-board
counts were pending at that increment; the later installation above supersedes that status.
Restarting the new host requires protocol 3 firmware.
[Image and validation](rig-wiring-evidence-2026-10-07/mcu-counted-diagnostics.md).

Camera display now follows the owner's [A10/G01 OpenCV ownership choice](acquisition.md#current-windows-wiring-checks).
Current presentation adds bounded initial GUI-edge positioning, square
aspect-preserving padding, pointer wheel zoom and double-click fit reset under
acquisition policy 15. Native isolated windows verify placement, square image
areas and cached-frame wheel/reset redraw; 549 affected-owner/client and eight
selected GUI tests pass (two integration privilege skips). Geometry/pixel helpers
remain focused, and static/boundary checks pass. The current owner runtime remains
on its earlier loaded source; full restart and physical GUI/DPI acceptance are
still required. [Current presentation evidence](rig-wiring-evidence-2026-10-07/preview-presentation-context.json).
GUI sends exact-run Show/Hide; acquisition owns windows/private readers, confirms
first-image display and native release, and reports visibility independently of
capture. X/Hide leaves capture running. Failed release retains its ledger blocker
while SDK/pulse cleanup is attempted; delayed observations cannot complete commands
or undo newer visibility. The former Qt reader and GUI frame-transfer path are removed.
526 affected-owner/client tests pass (two privilege skips), 17 GUI/bridge tests pass,
and final first-image/reopen refinements pass 64 focused checks. Two real Win32
OpenCV windows/latest-frame/X closure pass with isolated rings; package/dependency
and static checks pass. These are native display/implementation evidence, not physical
camera, heartbeat or full-load acceptance. That implementation increment preserved
the active runtime; later authorized installation and Behavior viewing/release are
recorded above. Original full-suite failures remain open.

Current Windows rig execution (2026-10-07, `08d146d` plus the generated-SWIG mypy
exclusion): [raw evidence, commands and limits](rig-wiring-evidence-2026-10-07/README.md).
The full offscreen Windows suite reports **1,252 passed, nine GUI failures, four
symlink-privilege skips, one rig deselection**. A separate native Qt run crashes
with access violation during GUI fixture teardown. Eight failures concern
layout/clipping; one compares normalized Qt paths to native path spelling.
These are current Windows findings; the earlier development pass below remains
historical evidence. Ruff/format, source mypy, boundaries, contracts/schema checks
and AMD64 package build pass. Generated Protobuf bindings were stale on arrival
and regenerated; source mypy now excludes only the generated Basler SWIG wrapper
under ARCH-002, preserving checks of handwritten adapters.

Managed startup registers all seven roles and stays alive for over an hour while
desktop inspection awaits approval. Automatic GUI control and explicit headless
takeover pass. Injected exact GUI loss followed by `--reopen-gui` creates one fresh
GUI in the unchanged controller/application generation. Interactive replacement
N preserves the exact endpoint; Y obtains the old process-absence receipt before
the successor generation. Authenticated normal shutdown succeeds; exact exit
receipts, no remaining managed processes and a free application guard are verified.
Mouse-driven close, reconnect warning acknowledgement and viewers remain unverified:
the computer-use app approval timed out. No full experiment ran.

Camera activity reveals a current E08 blocker: after two successful Behavior
Start/Stop cycles and a Tracking PFS import, camera workers report
`COORDINATOR_HEALTH_LOST`, causing application shutdown. See the
[acquisition assessment](acquisition.md#current-windows-wiring-checks).
The owner's later [controller-route MCU console](rig-wiring-evidence-2026-10-07/owner-mcu-console.md)
reports completed D2/D9/D10 diagnostic Start/Stop pairs, including 120 D2 rising
edges. Output zero counts are expected; ordinary MCU Status/Stop and physical
waveform/receiver checks remain separate unresolved acceptance work.
The owner's follow-up requests physical signal tests using the open SpikeGLX display.
Initial MCU output feedback correction under G01/A11: Trial state showed firmware-reported
HIGH/LOW and camera tests show running/stopped pulse output; only input diagnostics
show rising-edge counts. Six existing GUI diagnostic/control cases pass, GUI mypy
checks 124 sources, Ruff/format pass, and 598 backend modules have zero boundary
violations. ARCH-002 review keeps this presentation change in the focused existing
panel without dependencies or ownership changes; existing size advisories are
unchanged by it. Physical channel observations are pending, not new rig passes.
It is superseded by counted diagnostics above; its results retain their original
scope. The running GUI remains active with its previously loaded code. [Focused evidence](rig-wiring-evidence-2026-10-07/mcu-output-feedback.md).
The E12 read-only SDK connection times out, then logs a TCP connection failure
and an unretrieved late future exception. Saved endpoint/inventory readback succeeds;
remote recording, wiring proof and paired Setup remain pending. No mapping update
or remote mutation was issued. Existing scientific/encoder deferrals remain.

The owner-requested runtime wiring is implemented in the existing managed application.
Review and runtime share the current Dashboard, Protocol, Devices and Tracking layout.
Luna audited and implemented the work; Sol 6.1 prepared the plan and reviewed the code;
Astra reviewed the design and final source. All reproduced development findings are
repaired. Sol and Astra accept the final development implementation; Windows/rig
acceptance remains separate under [E15](../docs/architecture/system-contracts.md#e15).

| Area | Implemented and reviewed behavior |
| --- | --- |
| Configuration and commands | Full E07 proposals against the accepted revision, optional subject metadata, ordered trials/seeds/gaps, recording and projector/Tracking settings; exact captured Setup identity; stale drafts remain visible without rebase/replay |
| Authority and close | Retained warnings before control acquisition, exact prompt/command identity, safety actions during preparation, explicit discard/cancel, and history-save completion before GUI closure |
| Tracking | Selected-stage diagnostics including image-only/partial pipelines, real ordered preview frames, bounded exact-scope live image/overlays/timings, explicit acquired-frame annotation, and confirmed Close before editing |
| Projectors | Typed pacing and held policy propagation; first-use untimed V01 calibration through the V15 correction pipeline; exact output/context ownership, prior-display restoration, and bounded active/in-flight/lost-owner cleanup |
| SpikeGLX | Saved host endpoint readback, serialized SDK/inventory/monitor/stop ownership, exact trial stop timing, digest-guarded pulse mapping updates and bounded off-loop persistence with truthful late outcomes |
| GUI relaunch | Explicit same-generation reopen after exact prior release, authenticated fresh launch, retained uncertain/partially created successor identity, terminal RELEASED reconciliation and a responsive launcher backstop |
| Ownership gates | Configuration and Setup recheck unresolved diagnostic, cleanup and inventory ownership at admission and atomic commit, preserving valid Ready-edit cleanup |

Final review exercised actual controller, coordinator, worker, GUI and supervisor
assemblies with only necessary OS/native boundaries adapted. This found gaps that
isolated helpers missed; the final regressions preserve those paths. In particular,
RPC admission is distinguished from worker Close application, cancelled pre-dispatch
validation is distinguished from uncertain dispatched work, and late file completion
is reported truthfully without freeing an in-flight writer early. Scientific values,
encoder feasibility and firmware deferrals remain unchanged.

ARCH-002 review accepts the retained controller admission/cleanup ledgers, interruption
transaction, GUI connection/dispatch owners, GL-thread display restoration and protected
source registry. Separable calibration rendering/preparation, GUI close/display/diagnostic
transport/codecs, timed SpikeGLX stopping and pure inventory validation have focused
helpers. Sol found no whole-runtime back-references in the additions. The boundary
checker reports 597 modules and zero violations; larger cohesive owners retain their
single state ledger instead of duplicating it across modules.

Themed captures made through actual `ManagedGui.install_snapshot` with inert RPC and
device discovery were inspected at 720px and wide sizes. Inputs are readable with
vertical scrolling, authority text agrees with the snapshot, and menu contrast is
corrected. The [final captures and fixture](runtime-wiring-evidence-2026-10-06/gui-captures-final-2026-10-07/)
are local visual evidence; Windows DPI, monitor identity and optical output remain rig
checks. See the [Tracking](tracking.md), [acquisition](acquisition.md) and
[Visual Stimulus](visual_stimulus.md) reports for their retained scope/evidence.

| Development check | Result |
| --- | --- |
| Combined offscreen suite, Windows/rig markers excluded | 1,240 passed, six native-platform skips, five deselected (128.20 s); frozen-source hashes unchanged |
| Ruff / formatting | Pass; 793 files formatted |
| Windows-target mypy | Pass; 683 source files |
| Backend boundaries | 597 modules, zero violations; cohesion reviewed above |
| Pure contracts | Tracking: 48 passed; Visual Stimulus: 42 passed and 79 subtests |
| Schema consistency | 19 Tracking and 11 Visual Stimulus JSON schemas match; isolated Protobuf regeneration matches all 57 bindings from 19 sources |
| Dependencies | No broken requirements; declared TIFF dependency installed to execute its decoder check |
| Native package build | Blocked by the existing AMD64 Windows DLL guard on macOS; Windows packaging remains required |

Exact commands, failures, repair checkpoints and scope are retained in
[command/provenance metadata](runtime-wiring-evidence-2026-10-06/baseline-context.json)
and [LOG](../LOG.md). The [source manifest](runtime-wiring-evidence-2026-10-06/final-source-sha256.json)
records 954 implementation/input hashes, including generated bindings. The baseline
commit alone does not reproduce the pre-existing dirty working tree; transfer the
complete current source when preparing the rig. PowerShell/native execution was not
performed on this host. The [single rig checklist](rig-verification.md) is the remaining
execution guide; local passes do not establish experiment acceptance.

2026-10-06 startup workflow: interactive duplicate launches now ask Y/N. A confirmed
replacement signals the retained owner-private launcher event; the existing owner
terminates its contained application job and verifies absence before publishing its
exact exit receipt. The requester requires that receipt and the application guard
before starting. Older launchers without an endpoint require one manual shutdown;
missing proof, timeout and competing launches never permit overlapping generations.
The managed GUI automatically claims an unheld lease once after synchronization and
reconnect warning acknowledgement, using ordinary AcquireControl. Other holders
require confirmed takeover; manual Release stays released within that connection.
[E08](../docs/architecture/system-contracts.md#e08) revision 162 and
[E03](../docs/architecture/gui.md#e03) revision 29 own these operator-requested changes.
ARCH-002 reused native owner-only events, bounded private record I/O and exit receipts
in one focused launcher module, with no service, dependency or runtime back-reference.
GUI/launcher/configuration checks: 246 passed, one deselected in offscreen Qt mode;
final controller/launcher checks: 238 passed. Scoped Ruff lint/format and Windows-target
mypy (seven source files) pass; boundaries: 555 modules, zero violations, unchanged
cohesion advisories. An initial GUI run aborted at Qt initialization before rerunning
successfully offscreen. Native event coverage was added to the existing Windows owner
module but not executed on macOS. Actual Windows replacement/control acceptance stays
in the [rig checklist](rig-verification.md#managed-device-gui); no runtime or hardware
was started for this increment.

Development-machine follow-up, 2026-10-06: repaired controller rejection of explicit
empty preview run IDs for inactive cameras. The real acquisition status reporter
and controller reproduce Start/Stop rejection before the fix and success after it;
active previews still require UUIDs. This applies existing A10/E07 release evidence,
without extending deadlines or accepting unknown closure. Acquisition/controller:
417 passed, five skipped, one deselected; Ruff lint/format pass; Windows-target mypy
256 sources pass; boundaries 555 modules, zero violations. Existing size advisories
are unchanged; the focused projection owner needs no extraction under ARCH-002.
Rig viewer/Stop acceptance remains open; see the [current acquisition assessment](acquisition.md#preview-recheck-stopped-by-owner-2026-10-06).

Latest handoff, 2026-10-06: owner stopped the Behavior D10 → Line4 preview recheck.
The direct receiver check yielded 41 frames in two seconds after verified upload
of existing CephVR2 firmware; prior legacy flash is backed up. Managed ready/started
evidence reaches acquisition, but operator completion still fails with
`exact completion missing`; GUI viewer and managed Stop remain unaccepted.
Capture-scope declaration, explicit closed preview identity, initial projection
revision and canonical warning UUID repairs are retained under E06/E07/A10.
See [current acquisition assessment](acquisition.md#preview-recheck-stopped-by-owner-2026-10-06).
The authenticated shutdown of generation `2dd0392f-54f9-4c83-a733-3ea0549872ef`
was followed by empty CephVR2 process inventory and successful application-guard
acquire/release. Temporary tracing is removed; no replacement runtime was launched.
These findings supersede older statements below about missing capture catalogue
scope and a retained running runtime. One intervening launch failed independently
with `VISUAL_STIMULUS_EVIDENCE` / invalid UUID; that defect remains uninvestigated.

Requested development cleanup removed 42 preflighted directories, 6,640 files and
201,368,736 bytes, including 81 tracked test artifacts and disposable SDK prototypes,
build outputs and caches. Focused fixture ignore rules were added. Experiment data,
configuration/PFS, production native bridge, dated evidence and firmware backup
were preserved. Later checks recreated small temporary/cache directories; no
further optional cleanup was performed after the stop. The
[cleanup manifest](device-connection-evidence-2026-10-06/development-cleanup-manifest.json)
records the completed removal.

The 2026-10-06 manual-preview resolution failure was isolated to pypylon's
unsupported Python-integer Win32 HANDLE constructor. The bounded typed native
bridge and verification are recorded in [acquisition](acquisition.md) under
A02/SYS-003. Preview failures now retain original worker evidence and possible
ownership until release. Real settings resolution/native blocking wake and both
managed connections pass. External preview testing stopped at the owner's request
to use CephVR1.0; preparation still fails because its camera capture scope is
missing from the function catalogue. Acquisition heartbeat rejection was isolated
to reporting before endpoint registration; registration now precedes health
reporting, with one subsequent native startup reaching preview preparation.
Broader startup acceptance remains open.

CephVR2.0 is closed on 2026-10-06: process inventory contains no 2.0 roles and
the application guard can be acquired and released. CephVR1.0 startup was then
reproduced with a bounded Python traceback: GUI construction retries opening
`%LOCALAPPDATA%/CephVR/runtime/controller/controller.log` and receives WinError 5.
Its legacy controller directory and log have empty inherited DACLs; the shared
runtime root has a protected owner-only ACE without child inheritance. This is
a runtime-path/security collision between versions, not camera connection proof.
Resolved in the owner-authorized follow-up: E08 revision 161 assigns CephVR2.0
`%LOCALAPPDATA%/CephVR2/runtime`. The one-time migration moved only canonical
generation directories and the protected recovery folder after preflight checks;
all moved entries retain their exact ACLs and file SHA256 hashes. Legacy runtime
now grants inherited FullControl only to the current owner. The native repair
changes DACL alone; PowerShell Set-Acl first requested unavailable
SeSecurityPrivilege after migration, without completing the access repair.
Windows PowerShell 5 also failed to load its security module before any mutation;
the available PowerShell 7 completed the migration. No credentials were printed.
The normal CephVR1.0 launcher now opens the fully rendered Experiment OS Dashboard
and its controller. No CephVR2.0 runtime was started. Scoped invariant tests:
10 passed, including native credential isolation and writable legacy log coverage;
Ruff lint/format, Windows-target mypy and boundaries (556 modules, zero violations)
pass. Existing cohesion warnings concern unchanged modules; the focused credential
helper adds no dependency or new coordination under ARCH-002.

Final Windows repair and one-time elevated follow-up (2026-10-01, baseline HEAD
`826984255e0a8469afccbda2dcaf8c642b528b33` plus uncommitted repairs): controller
202 passed; supervisor 106; shared 52; platform 46; launcher 10 and client 6 passed.
Whole suite: 759 passed with zero failures/skips, all Windows and bounded rig markers,
using dedicated elevated scratch. The owner removed exactly two POSIX-only tests;
native unsafe-DACL rejection remains. Standard-token default-temp full suite passed
755 with four symlink privilege skips; actual one-time elevation executed those four.
Elevation exposed missing startup dependencies in prepared Python; finite matching-base
VCRUNTIME140.dll/optional zlib.dll preparation now verifies source/copy hashes before
planning. Exact executing PID/image, venv imports and bootstrap proof passes elevated
and Medium-token default-temp checks. No persistent OS privilege/policy change.
[Dated evidence](rig-audit-2026-10-01/README.md) preserves failed attempts, latest JUnit,
commands, startup provenance and scoped cleanup; full experiment acceptance remains open.
Setup Ready/failure and successful Start use the existing terminal completion
owner, preserving failure codes, publication order and active-session retention.
The native intrinsic helper repairs cross-process ring atomics. Verified prepared
Python images preserve the fresh virtual environment: a live native regression
confirms launched/code PID and OS image, one job member and inherited bootstrap.
E04 reservation guards preserve exclusive ownership while Windows closes the byte
lock for quarantine, including failure; default-path recovery persistence passes.
Fixtures now respect Windows sharing/permissions and await actual async outcomes.

An earlier proposed launcher invocation was rejected by automatic approval review
for potential managed service/hardware effects and was not executed at that time.
The later 2026-10-05 owner-authorized managed launch and its Visual Stimulus failure
are recorded in the frontend section. Focused checks do not establish full E04/E08
application/device/workload acceptance. Capacity bypass was not
established; authorization checks the same capacity under the lifecycle lock.
ARCH-002 review keeps the 502-line reservation owner cohesive around namespace
ownership; native tests remain one platform-fixture module rather than per-fix files.

- Controller lifecycle, configuration validation, live control leases, RPC admission,
  output planning, serialized central metadata, preparation handoffs, incident handling,
  camera/preview forwarding, and headless control.
- Supervisor launch registration, health/evidence forwarding, cleanup obligations,
  independent emergency reporting, and bounded shutdown.
- Shared identity, command retention, ingress bounds, policy loading, credentials,
  resource/incident proof helpers; Windows jobs, process handles, guards, bootstrap
  pipes, private ACLs and publication helpers; persistent external launcher.
- One Python project with backend-owned packages, generated Protobuf bindings and
  type stubs, configured development tools, reproducible generation in package builds,
  and tests organized by code owner.

Components use focused typed records, peer operations and shared authoritative state.
Controller control/lifecycle/device/incident/metadata/transport owners and supervisor
registration/health/recovery/shutdown owners are assembled by their coordinators.
RPC adapters retain authentication and admission. Source review covered cleanup
fences, partial Setup, cancellation, original deadlines, command retention, durable
metadata and process ownership; static comparisons do not prove execution.

The module entry point calls the controller CLI. Mutable incident retention belongs
to `controller/incident/registry.py`; shared proof validation stays in `shared/`.
The acquisition-specific audit corrections are recorded in [acquisition.md](acquisition.md).

Supervisor simplification under ARCH-002 removes unreachable registry rejections,
shares worker channel revalidation/cache management and session/trial containment,
and separates native process exit evidence from shutdown outcome ownership. Camera
and persistent Visual Stimulus launch scopes remain distinct. Independent delivery still uses
bounded asyncio tasks; no additional package, public interface or policy change was
needed. E04/E06/E08 emergency reporting, original deadlines and cleanup/exit evidence
remain with their existing owners. Existing recovery/retention findings below remain
outside this refactor.

A second behavior-preserving pass gives the acquisition (`acquisition_worker.py`) and
Visual Stimulus worker controllers one interface (`WorkerControl`), so shutdown loops
over them instead of duplicating each step; acquisition's separate cleanup module was
merged into its controller. `shutdown_owned` is split into named steps with one bounded
polling helper and one outer-deadline expression. `GrpcOutbound` extends the worker
transport instead of re-declaring its methods, with one call helper and the port now
declaring channel retirement and close. Work scope, live launch phases and backend
role sets each have one definition, and the health monitor tick and tracking-release
forwarding are separate methods. Error codes/messages, lock scopes, deadlines and side-
effect order are unchanged; two observable differences are accepted: process-exit polling
sleeps are capped at the remaining deadline, and a registration with several faults can
report a different first error (single-fault errors are unchanged). Windows-only
`startup.py`/`main.py` and the registry `confirm()` state machine were intentionally left
alone.

Controller simplification under ARCH-002 shares bounded backend interruption delivery,
moves recovery-log draining and writer sealing into the existing metadata owner,
and consolidates camera-operation retirement in its retention owner. E04/E05/E06/E07/E08
lock scopes, original deadlines, terminal evidence, durable-write order and cleanup
outcomes remain unchanged. No dependency, schema, public RPC or policy change was
needed. Setup and manual camera readback keep distinct admission/adoption transactions:
their validator and ownership requirements differ, so merging them is not a safe
mechanical simplification.

A second controller pass removes unread wiring (constructor parameters, attributes and
three mirrored configuration fields), the static file-policy fallback and the
five-layer `recovery_log_done` hook, and gives repeated patterns one owner: bounded
warning retention (`ControlState.add_warning`), rejected receipts/admissions
(`controller/receipts.py`), affected-resource and reservation-unconfirmed predicates on
`Attempt`, and the backend-name set. Backend command wrappers, AbortNow/Shutdown
admission, reservation finish, trial-log documents, admission failure handling,
report-retention conflicts and the shared backend cleanup dispatch (Setup cancel and
finalize) each have one implementation. `ControllerRuntime` now keeps wiring and thin
delegators: startup-recovery installation moved to `OperatorPrompts`, authority status
capture to `AuthorityStatus`, the manual-cleanup warning to its cleanup owner, and the
AbortNow/Shutdown precondition to the one predicate in `SessionCommands`. Settings and
output resolution moved from `setup_execution.py` to `setup_resolution.py`, and
oversized Setup, interruption, completion and configuration functions were split into
named steps. Lock scopes, deadlines, durable-write order, identity checks and message
text are unchanged; one accepted observable difference is that warnings recorded at
sites that previously did not trim are now bounded in memory (published snapshots
already applied the same cap). The controller backend port keeps
`apply_camera_settings`/`apply_pulse_configuration` for the open owned-camera-edit task.
`startup/application.py` (Windows-only, untested here), `transport/ingress.py` (no direct
test), the authority-loss/evidence/recovery-inspection state machines and the Optional
fail-closed dependencies were intentionally left alone.

## Unresolved findings and limitations

Oct16 local Abort/preview reliability work is complete; native acceptance stays open.
Interrupted cleanup is requested before trial/session metadata sealing, and exact
admitted cleanup can supply current-trial closure without normal Finished or invented
stop times. Registered output paths, frozen-set recovery bounds and overlapping
Abort/finalization are covered. The preview guard is retired only by successful
native device Close; failed Close and retained-device uncertainty stay fenced.
[Acquisition assessment](acquisition.md) owns details and
[Oct16 validation](runtime-evidence-2026-10-16/dev-reliability/context.json) retains
source/test scope. Historical forty-second Abort and preview-blocker evidence below
is not relabelled as a native repair pass. Existing E04 metadata-completeness and
unrelated race/audit tasks remain open.

Oct15 `gui-empty-variation-group` [gui]: owner reports GUI exit after adding a
group with an untouched empty variation row; an error was shown, text unavailable.
Under [G01/G02](../docs/architecture/gui.md#g01), invalid input must preserve the
draft and block mutation with an action-time warning. New owning dashboard cases
exercise native Windows button clicks/focus changes for blank and sample programs,
warning dismissal, row removal and successful subsequent group creation. Both pass;
related persisted-rule/random-group cases also pass (four total). No production
defect or fix is established. Initial suspicion of an exception in dirty checking
was not reproduced. Read-only Windows Application events show only an older
09:45 cephvr-python AppHangTransient, not a matching crash. Runtime traceback/error
text remains needed; local widget tests do not establish live controller equivalence.

Oct15 local probes confirm two existing TODO defects despite the passing suites:

- `calibration-live-update-rejection` is repaired Oct16 under V01/E06/G01.
  Explicit renderer rejection clears the exact pending Update/expected receipt and
  leaves the confirmed active projection and Setup block intact. A subsequent
  valid Update is admitted; uncertain transport outcomes remain fenced. Real
  ProjectionStore coverage exercises rejection/retry for all three live views.
  Device-admission25/controller522 and authenticated calibration3 pass; scoped
  Ruff/format, Win32 mypy and boundaries698/zero violations pass. Existing owners
  and test module are retained under ARCH-002, with no policy/dependency change.
  [Current local evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
- `controller-config-inactive-backend-defaults` is repaired Oct16 under E07.
  Missing/malformed inactive acquisition defaults produce a startup configuration
  warning without filling invented values or replacing saved settings; active
  acquisition still fails strictly. Setup reloads control limits/policies without
  rereading saved history or backend defaults; its active file-policy loader remains
  strict. Configuration/Setup38 and controller528 pass, including actual admission
  with malformed inactive files and unchanged current configuration. Scoped
  Ruff/format4, Win32 mypy3 and boundaries698/zero violations pass. Initial optional
  return annotations were corrected after mypy; no policy/default file changed.
  [Current local evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).

The original probes used local fixture adapters/config copies; current repair status
is stated above. Remaining audit/race/logging concerns keep their unverified status.
[Reproduction outputs and exact scope](runtime-evidence-2026-10-15/todo-projectors-off/context.json).


Current dev-machine triage (2026-10-13, source `4a62844`, macOS/Python3.11.15):
latest combined evidence verifies nominal60fps and repeated reset; the old39.47fps/
warning-shutdown statements in TODO and the outstanding rig checklist are corrected.
Historical workflow observations below retain their original scope.

| Standing issue | Work possible on the development machine | Remaining acceptance |
| --- | --- | --- |
| Failed-Setup renderer cleanup rejects an unknown command | Local worker recovery formerly submitted an unregistered worker-issued shutdown and forwarded its cleanup as coordinator-issued evidence. The repair retains this local command/result on the worker query route; the coordinator still rejects unknown IDs (E06/E08). Local regressions pass; see validation below. | Repeat the native failed-Setup/prior-calibration workflow; the full historical failure is not reproduced here. |
| Acquisition finalizer calls a departed controller | Teardown tolerates MCU Close UNAVAILABLE only after exact PID/creation-time exit confirmation, retaining the unconfirmed claim and reporting it (A11/E08). Live/unknown process and other RPC failures propagate. Local regressions pass; see validation below. | Native orderly shutdown and exact release. |
| Repeated manual preview hits MCU pending/unavailable and retention capacity | Reproduced fourth-readback capacity failure: each completed result retained a16MiB reservation. Explicit terminal completion now charges actual result bytes while preserving in-flight capacity, exact replay and300s retention (E08/A02). MCU pending is separately unproven; lease-turnover cleanup fences remain. Local regressions pass; see validation below. | Repeated real preview reuse in one generation with lease/claim state captured. |
| Review/camera recording loss | Profile bounded drain/padding/copy behavior, test backpressure and prepare measured changes (V12/V28/A07). The recording owner still waits up to5ms between unresolved writes. This is a cost, not proven NVENC saturation. | Combined Windows/GPU/camera throughput, zero-loss and optical timing. |
| Calibration loss and stale ordinary diagnostic bundle | Trace actual save/restore paths and validate regenerated all-VSync assets (G01/V01). Current normal-close tests pass; reported loss has no established root cause. | Actual closure-path reproduction and physical calibration. |
| Windows projector overflow, hover lookup and native picker exception-hook failures | Improve portable layout/lifetime coverage and inspect source (G01/G02). Local layout passes do not resolve Windows failures. | Windows native/DPI/pytest compatibility. |
| Long image protocols | Complete image readiness/lookahead/miss contracts; accepted bounded residency remains unimplemented (V04/V11). Critical miss behavior still requires an owner choice. | Native memory/performance and full-load acceptance after implementation. |

Local generated bindings were stale: controller and ManagedGui imports failed on
`MICROCONTROLLER_SIGNAL_KIND_EYE_TRACKING`, already present in authoritative contracts.
`python tools/generate_contracts.py` regenerates19 ignored Protobuf sources and clears
that blocker without editing contracts or handwritten runtime code. Focused tests then
pass222 (two deselected); nine offscreen GUI checks pass, including normal calibration
close/reopen and projector layout. Authenticated communication/startup recovery/shutdown
checks pass29 after granting loopback access; the sandbox attempt had five bind failures
and24 passes. Boundaries inspect667 modules with zero violations and existing cohesion
advisories. Exact commands and limits are recorded in LOG under
`runtime-dev-machine-triage`; this is sampled review, not a full runtime audit or rig pass.
That initial triage performed no runtime repair or operator/device mutation; the later
owner-authorized repairs above are separately validated below.

Oct13 local repair validation (source4a62844 plus retained patch): Luna implements,
Sol6.1 independently analyzes/integrates, and Astra approves the final source with no
actionable blockers. The affected acquisition/controller/supervisor/shared/Visual
Stimulus suite passes1316, skips five Win32-atomic ring cases and deselects four
Windows/rig cases. The final renderer teardown-helper extraction overlaps this run;
a final authenticated transport rerun passes9. Ruff check/format573 files, Win32
mypy486 sources, boundary check667 modules/zero violations and whitespace pass.
Sandbox transport attempts fail at loopback binding; unchanged permitted runs pass.
[Commands, source hashes and evidence](runtime-evidence-2026-10-13/dev-machine-repairs/context.json)
retain that scope. These are local implementation checks, not Windows/rig acceptance.

ARCH-002 review retains existing ownership and dependencies. Terminal reservation
compaction is explicit and atomic under the existing ledger lock; ordinary admission/
executor completion retains its original reservation. Native process identity uses
the existing exact PID/creation-time helper. Renderer local recovery uses its own
command-local ledger scope, retained admission/outcome and pruned routing marker;
worker/owner identity, original deadline and same-ID replay are checked before dispatch.
Its cleanup is queryable locally and never treated as a coordinator-issued command
or supervisor cleanup receipt. Endpoint teardown attempts continue after report-drain
failure while propagating the original failure. The new acquisition test_main module
owns host-entrypoint finalization, distinct from existing worker/bootstrap/coordinator
behavior tests; all other regressions extend their owning modules. Existing oversized
module advisories remain cohesive; no source split, dependency or policy change is needed.

The missing-SESSION_CONFIG recovery warning remains conservative: the durable
reservation identifies the session but cannot prove that it was unpaired. Removing
that warning would invent evidence. Likewise, MCU pending/unavailable is not proven
to share the readback-capacity cause; the historical probe repeatedly released its
control lease, which can legitimately fence new work while cleanup completes.
Capture exact lease/claim state during the deferred rig repeat. The local renderer
regression exercises RenderOwner/ReportBridge recovery delivery and finalized prior
scope; it does not reproduce the entire historical failed-Setup/calibration workflow.
Native acceptance procedures remain solely in [the rig checklist](rig-verification.md).

Oct12 `long-protocol-resource-scaling`: the authorized GUI portion now uses compact
source groups, scoped editing and viewport-only block painting under
[G01 revision 153](../docs/architecture/gui.md#g01). It no longer expands repetitions
for timeline loading/selection. Source JSON parsing, canonical validation and source
metadata traversal remain synchronous; this change does not establish latency bounds
for huge numbers of independently authored epochs. Explicit expanded/animated previews
and batch generation retain their 2000-occurrence engineering limits. The initial
CephVR1.0 concern was assessed by source review, not reproduced or benchmarked.
Image residency/readiness/miss behavior remains the separate
[Visual Stimulus follow-up](visual_stimulus.md#validation-limits).

The Oct8 missing application-shutdown history save is repaired and locally/native
verified in the current scope above under [E07](../docs/architecture/experiment.md#e07).
An abrupt crash or termination that cannot execute the controller's save path can
still lose accepted edits since the last successful save. Earlier Tracking-probe
restoration meant its captured startup snapshot, not recovery of the owner's
pre-crash in-memory edits; cleanup did not delete the history file. Do not reinterpret
that historical restoration as crash resilience or recovery of those lost edits.

Oct9 repairs follow [E06/E08 revision 169](../docs/architecture/system-contracts.md#e08),
[E04](../docs/architecture/supervisor.md#e04),
[E07](../docs/architecture/experiment.md#e07) and
[E12](../docs/architecture/synchronization.md#e12):

- Camera-worker retirement sends typed retained Cleanup operation/lifecycle evidence
  through the existing authenticated ConfirmLaunch route before Shutdown, then replays
  the identical request after exit. Acknowledgement fences only that exact expected
  exit; live ownership remains retained. The coordinator checks its
  exact resource/output obligations; supervisor independently checks child/work/owner
  identity and exact process/job absence. Both independently delivered Cleanup records
  must arrive within the original deadline, including guarded retained-query recovery.
  Workless Configuration retirement is supported; discharged failed outputs remain failed.
  Queries, exit and quiet liveness do not become closure evidence; persistent renderer
  session cleanup remains distinct.
- Released launch records stay pinned for active work and through the configured
  replay window after both release and work finalization. Capacity refuses new admission
  instead of evicting unexpired canonical replay evidence. Finalized-work bookkeeping
  is bounded by retained records; obsolete release-order state is removed.
- Startup inspection distinguishes exact late-Finished/incident reconciliation from
  terminal startup recovery. Malformed/unknown records remain unconfirmed; terminal
  recovery must still follow session end and remain last. Pre-activation Shutdown
  settles attempt-owned Setup prompt futures through the existing cancellation owner.
- Accepted shutdown watches controller loss during the existing bounded cleanup waits
  and invokes the same one-shot interruption under unchanged deadlines. An event-gated
  regression requires interruption while the first wait is still held; disabling the
  observer makes it fail. Pending-fault escalation remains covered.
- Timeout/caller cancellation attaches an observer to the shielded SDK future without
  releasing in-flight native ownership. Late results/failures are consumed and logged;
  subsequent calls remain busy until native completion.
- Snapshot and ordinary camera-save errors select the blocking camera row and field.
  Tests use the actual backend validation error, preserve the Behavior draft and whole
  proposal validation, and accept corrected Tracking settings. Native UI acceptance
  remains separate.

Sol found no compatible remaining readback duplication: Setup and manual paths already
share `resolved_configuration()` while owning different admission/adoption transactions.
Close that conditional task without another abstraction. Remove only the write-only
`completed_camera_operation` mirror; retain authoritative bounded status evidence and
accepted operator compatibility settings. Duplicate-command ingress and warning-race
claims remain rejected by the audit. Owned-camera edits now use exact readback and
commit-before-confirm semantics under [A10 revision 57](../docs/architecture/acquisition.md#a10)
and [A11 revision 41](../docs/architecture/acquisition.md#a11). Confirmation transport
admission is separate from execution/adoption; post-commit device failure does not
roll back accepted settings. Exact pending MCU proposals require the live edit,
claim, generation and original deadline; scope on other request kinds rejects.

Recovery retains exact late worker terminal evidence without adopting settings or
resuming previews. Fresh callers query retained results and can retry only an already
pending exact MCU CLOSE after camera cleanup. Stable previews remain editable;
unknown SDK/preview/resource/claim ownership remains fenced. Explicit exact-run Stop
works across controller/backend revision lag. Confirmed OFF/claim-release proof
survives live-observation clearing and expires before new connection/output work.
Cleanup failure keeps actual ownership and truthful closed-camera status; expired
Ready/Started records never create readiness. [Sol source and real-chain evidence](review-evidence-2026-10-09/nongui-sol-owned-camera.txt)
and [Luna recovery scope](review-evidence-2026-10-09/nongui-luna-camera-recovery.txt)
record the corrections and limits. Proven never-dispatched or explicitly rejected edits create no missing-status obligation; unknown admission retains its fence. Removal targets only that attempt; existing bounded-history pruning is unchanged. Sol and Astra accept the final integrated implementation.

Repository hygiene: remove the 10,353-file, 224,923,430-byte tracked `.tmp` tree and
ignore that root. Preserve three unique historical QA/collection artifacts in their
own dated bundles; existing JUnit copies match exactly. Git history, the environment,
actual runtime recovery/history and dated rig evidence remain intact. The
[cleanup inventory](review-evidence-2026-10-09/cleanup.json) records preservation hashes
and removal of 75 project cache directories (932 files / 52,844,967 bytes) after
validation in the preceding cohort. Final non-GUI cleanup removes another 42 cache
directories (321 files / 28,233,854 bytes); nine redundant handoff snapshots (181,320
bytes) were consolidated only after exact prefix checks. No active credential leak
was established.

ARCH-002 review extracts pure launch-request and cleanup-proof validation, leaving
registry native/state ownership and acquisition worker lifecycle orchestration in their
existing modules. The Oct9 non-GUI follow-up extracts worker preparation/waits/health,
shared native launch sequencing, manual-device recovery and exact retained-status
querying. Preview transfer release stays with its focused owner. Existing records keep
state/resource ownership; helpers receive explicit operations and focused records.
No process, dependency, whole-runtime reference or duplicate resource catalogue is
introduced. Remaining manual edit/preview orchestration (559/656 lines), recording
session closure (599 lines) and stimulus recording (833 lines) retain their cohesive
workflow/thread ownership; the size advisories do not justify duplicating that state.

Portable worker coverage/execution extraction and shared launch are accepted by
Sol/Astra. The deadline sweep closes the original 148-site inventory (135 first-batch,
10 controller and three launcher sites); the final controller increment also converts
one expression introduced during concurrent owned-edit work. Exact clocks, original
bounds and existing transport validation remain unchanged. The final scan finds zero
remaining inventoried patterns. Padding uses first usable image per nominal slot,
labelled first-image leading backfill and explicit omission/duplicate mappings;
[acquisition](acquisition.md) and [stimulus](visual_stimulus.md) own the details.
GUI source/tests are unchanged throughout this cohort.

Current non-GUI validation: repository-wide lint/format pass (849 files), Windows-target
mypy passes 734 sources, and boundaries inspect 639 modules with zero violations.
Contract discovery passes 48 Tracking and 42 stimulus cases; canonical schemas match
19/11 and all 57 generated bindings match. Final portable/offscreen authenticated-loopback
validation: **1795 passed, 6 skipped, 8 deselected in 309.49s (0:05:09)**. Sol and Astra
accept the final integrated source. [Current provenance](review-evidence-2026-10-09/nongui-context.json)
records the dirty baseline, exact changes, commands and model handoffs. One dirty
worker-test before-state could not be recovered: retain its declared hash and separately
label its HEAD-to-final supplement; every final tested input is hashed.

The preceding initial-repair portable/offscreen suite passes **1,698 tests, six skips and eight marker
exclusions** in 322.25 s before the final retirement-order correction. After that
correction, the complete supervisor/acquisition rerun passes **472 tests, five skips
and two exclusions** in 4.02 s; other source is unchanged. Final Ruff and formatting
(839 files), Win32-target mypy (726 sources) and boundaries (633 modules, zero
violations; 41 cohesion advisories) pass. Tracking/Visual Stimulus contract discovery
passes 48/42 and generated schemas match 19/11. Do not sum overlapping selections.
[Implementation evidence and model dispositions](review-evidence-2026-10-09/implementation-context.json)
retain commands, source patch/hashes, failures and limitations. Current full-suite
alignment passes; the historical advanced-card issue is not reproduced.
Windows native camera reuse, process/job proof, fault-injected shutdown, SDK pairing,
DPI and scientific/full-load acceptance remain unverified by these local checks.

Recovery and native acceptance cases have one home in the
[rig worklist](rig-verification.md#runtime-recovery-and-regression-coverage).
Missing required participants fail explicitly; this report does not establish an
operational experiment or authorize firmware, GUI or tracking implementation.

### Controller/supervisor audit (2026-10-14)

Scope: whole `src/cephvr/supervisor` and `src/cephvr/controller` trees with their tests, read by six
module-group auditors; every candidate was then re-read and, where an observed defect, reproduced by
probe or a failing regression test before any edit (source `0d70295` plus concurrent GUI/SpikeGLX
work in the tree). Source and local-test evidence only; no Windows-native or rig run (E15).

Fixed, each with a test that fails without the change:

| Finding | Repair | Decisions |
| --- | --- | --- |
| Cancel or failure before the preliminary supervisor registration (low-space/collision Cancel, space-query or reservation failure) left cleanup blocked and the reservation held | `dispatch_backend_cleanup` returns confirmed when no registered context exists and authority is intact: backends receive Setup work only after that registration | E04, E05, E06 |
| Accepted commands admitted with no live attempt (display calibration, tracking diagnostic, SpikeGLX inventory) were never finalized, so after 1,024 every non-safety command was refused | Such a command's own scope is finalized when it completes | E08 |
| An action raising a message over 4 KiB hung the RPC and wedged its record | Rejection messages bounded to 2 KiB; the caller's future is always resolved | E08 |
| A failed or timed-out calibration Close kept an IDLE pending with no timer, so the exact Close could never be retried | The unconfirmed Close expires on its recovery bound; the blocked flag stays until evidence arrives | E06, V01 |
| A failed manual-camera release RPC never freed `camera_operation`, wedging cleanup retries | The slot is retired; a late exact report is still adopted | E06, E08, A10 |
| Eye-tracking camera kept dormant values and the PFS payload in SESSION_CONFIG | Eye role handled with the other cameras | E04 |
| `incident_scope` log events made startup recovery reject the session log | Added to the inspector and to the E04 catalog (revision 89) | E04, E06 |
| A late ConfirmLaunch with a fresh command ID revived a RELEASED launch to CLEANUP_REQUIRED, after which registry refresh failed and health began shutdown | Release is final once the exact identities match | E08 |
| A firmware-rejected DIAG_START left the diagnostic "uncertain" and Release unable to confirm | Only an unanswered start stays uncertain | A11 |
| Pre-dispatch deadline failures were recorded as `SERIAL_FAILURE` | Labelled by exception type | A11 |
| `setup_override` events were never written | Appended after `session_started` | E04 |
| Stale protocol-3 text in the microcontroller contract | Corrected to 4 | A11 |
| An isolated required-backend exit was later overridden by heartbeat silence and entered full shutdown (owner chose to exempt it, 2026-10-15) | Backends in `isolated_backend_exits` skip silence checks; E08 revision 171 | E06, E08 |
| A failed manual Connect left an owner that could never reconnect (owner chose discard) | `LazySerialOwner` discards the failed owner and port; A11 revision 45 | A11 |
| An unanswered DIAG_START wedged Release (owner chose firmware-bound cleanup) | Cleanup attempts Stop, then the verified OFF decides; a failed Stop of a known-active diagnostic still fences | A11 |
| The host keepalive task ended if its failure handler raised, so later connections had no watchdog feed | Keepalive survives the handler error and skips only the failed connection; the failed close now warns | A11, E06 |

Also removed as dead write-only state: `Attempt.cleanup_commands`, two tracking-diagnostic fields and three unused
serial-owner members. Rejected: hard-coded 5 s delivery cap (matches E04's fixed 5 s), stop-after-trial gap wait (a
configured minimum, no decision requires early exit), and findings that did not survive tracing.

Oct16 local repairs complete E04/E03 accepted Stop/withdrawal/Abort events, automatic-stop and
terminal-unanswered dispositions, and short error messages. Required event tasks are registered
before writer seal and joined under the original finalization budget; safety dispatch remains
independent. SESSION_CONFIG records only supervisor/active-backend accepted software versions
(unknown is null). Every reserved trial output is indexed with exact owner/path, writer
format/schema, presence/closure and owner-observed counts; missing counts remain unknown.
Snapshot publishes oldest retained error/recovery/incident time and bounded-retention omissions,
including source and combined-list trims. Untimed warnings do not invent a history timestamp.
Existing owners/helpers are reused under ARCH-002; no new processes, inventories or timing policy.
Local backend/authenticated suites1785 pass/five platform skips/five exclusions; Ruff/format224,
Win32 mypy540 and boundaries699/zero violations pass. Initial fixture/import errors were corrected;
the sandbox-only socket failures remain in raw evidence, followed by authorized loopback passes.
[Evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json). Native E15 acceptance stays open.

Oct16 `controller-cleanup-and-race-hardening` completed locally under E04/E03/E06/E08:

| Audit concern | Current disposition/evidence |
| --- | --- |
| Late backend Cleanup hid failed central metadata | Reproduced; separate attempt-owned metadata-clean result gates late completion. Resource closure alone cannot certify persistence. |
| Timed-out Setup reservation thread outlived discarded attempt | Reproduced; exact acquisition task is shielded/retained, cancellation keeps the attempt blocked, and late settlement serializes cleanup. Original wait deadlines stay unchanged. |
| Missing recording root counted as cleaned | Reproduced; absent session/experiment is accepted only with its recording root present and safe. |
| SpikeGLX log failure changed a confirmed remote Stop to Unknown | Reproduced; remote STOPPED remains, metadata failure warns/blocks clean finalization independently. |
| Tracking begin held lifecycle lock during policy I/O | Reproduced; load outside lock, then recheck lease/revision/phase/device ownership before admission. |
| Display/camera admission gaps across validation | Reproduced; recheck pending display/calibration ownership and current camera selection/lifecycle before dispatch. |
| Configuration commit rejected any status publication | Reproduced; guard exact configuration revision/phase/authority and pending edit, without treating unrelated publications as conflicts. |
| Retry identity depended on current scope | Reproduced; retained canonical command uses its original scope after NewSession/retirement; changed payload still rejects. |
| Sessionless warning projections / supervisor error and recovery history grew without bound | Not reproduced in source review: ProjectionStore and supervisor enforce entry/byte bounds and E06 failure. Existing scope reset clears warning projections; no speculative history/eviction policy added. |
| RegisterContext could fail after admission on ordinary validation | Not reproduced in source review: final catalogue verification precedes admission under the same lock, with no await before sealing. No transaction rewrite justified. |
| GUI relaunch advanced its command before native creation | Fixed in extracted focused launch owner; creation failure retains old command, notification failure retains the actually launched child for cleanup. |
| Supervisor preview receipt stored no evidence | Reproduced in source; bounded exact failure/release evidence now retained and exposed by existing recovery query. No producer closure or viewer start is inferred. |

Owning tests pin the fixes; local backend/authenticated1804 pass/five platform skips/five
exclusions, Ruff/format170, Win32 mypy132 and boundaries701/zero violations pass.
GuiRelaunch and preview-evidence retention are separable owners extracted under ARCH-002;
no whole-runtime back-reference, new process or timing allowance. Existing cohesive-size
advisories remain. Initial patch/fixture/type errors were corrected and retained with the
[raw evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
Native ownership/process/serial/SDK behavior remains E15 rig work.

Oct16 `mcu-owner-residual-hardening` completed locally under A11/E12. Acquisition
Schedule rejection cancels unsent ON but retains OFF; confirmed immediate safety OFF
now retires only fully covered OFF reservations when no pending ON remains. Partial,
rejected and unknown OFF stay fenced. Startup probe propagates hard transport failures
instead of repeatedly writing a broken link inside its deadline. Firmware ERR retains
parsed context/request identity and symbolic codes. Full MCU observations expose
connection-cumulative malformed/unmatched diagnostics without health credit. SpikeGLX
monitor preserves actual observation failure reasons; only actual deadline violations
become DEADLINE, and missing unexplained observation is explicit unknown evidence.
Owner/protocol/monitor158 checks and backend/authenticated1813 pass/five platform skips/
five exclusions; Win32 mypy293, boundaries701/zero violations and scoped lint/format
pass. No firmware/electrical/mapping changes or rig acceptance.
[Evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).

Oct16 `controller-supervisor-residual-simplification` completed under ARCH-002.
Pending display/calibration commands are named immutable records; one dispatch helper
preserves transport-entry ordering, shielded calls and original deadlines. Shared
acquisition-entry lookup preserves duplicates/order/dormant or malformed payloads for
owning validation. Pacing resolution and incident byte accounting share focused helpers;
ByteSize avoids temporary serialization for capacity checks. Explicit release and watch
loss share one observer registry, removing duplicate registrations. All central warning
entry points now enforce one retention bound and omission flag. Removed unused Deadline
wrapper; existing absolute-deadline helpers remain. The camera role map and runtime
safety-kind set were already centralized; source review found no unused supervisor/
lifecycle flags to delete. Exact terminal late-evidence flags remain intentional records.

New owning coverage exercises real cleanup-fence registration/echo rejection, late
metadata cleanup, inclusive T−100/T−50 ms cutoffs, active-I/O writer entry/byte capacity
and late sync, the Tracking begin rejection matrix, exact ExecuteRecoveryAction replay/
cleanup proof and the production credential authentication factory. Existing tests pin
refactored behavior. Backend/authenticated1852 pass/five platform skips/five exclusions;
Ruff/format222, Win32 mypy111 and boundaries702/zero violations pass. State remains a
cohesive collection of focused records; display calibration retains exact diagnostic/
control-loss ownership after removing duplicated dispatch, with no new runtime back-reference.
Corrected initial extraction syntax, redundant cast, old test introspection and missing
paired-Setup fixture fields. [Raw checks and limits](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
Native E15 checks remain open. Inactive acquisition defaults and live calibration
rejection were repaired/tested Oct16 above.

### GUI preview design review

Source review on 2026-10-01 of the sibling CephVR1.0 checkout at HEAD
`38f728291ed551a332392dc2c7b6897e8428b060` found plausible preview costs, not
a measured cause of the owner's historical slowdown. Inspected preview files
had no local changes; the historical running revision is unknown. The old
`protocol/src/protocol/gui/stream_workers.py` emits a Qt signal per snapshot;
GUI-side draw throttling does not coalesce those notifications. In
`gui/experiment_window.py`, `_render_gl_frame` ignores `resolution_percent`,
expands monochrome frames to RGBA, and passes full dimensions to the GL widget.
The widget reuses textures and retains only the latest pending frame, so this is
not evidence of an entirely unbounded image renderer. Tracking metadata matching
and separate overlay consumers add possible latency/work. The existing external
`protocol/highgui_preview.py` also copies frames, fits them to a canvas and pumps
HighGUI events; external windows are not free of display work.

CephVR2.0 acquisition already applies its producer-side session sampling in
`src/cephvr/acquisition/worker/capture.py`; [A03](../docs/architecture/acquisition.md#a03),
[A10](../docs/architecture/acquisition.md#a10) and
[T08](../docs/architecture/tracking.md#t08) require preview work to remain outside
critical capture/tracking ownership. No new viewer performance was measured.
The owner accepted backend-managed external viewers and a modeless visibility selector
under [G01 revision 41](../docs/architecture/gui.md#g01). Runtime integration still needs
bounded latest-frame delivery, independent viewer/capture lifetimes and an OpenCV
dependency review: the current tracking extra is headless. Preview-off versus enabled
full-workload comparison remains part of [rig acceptance](rig-verification.md).
Window placement alone does not establish isolation or throughput.

The earlier three HTML sketches remain historical alternatives. The selected frontend
uses one Previews button and a reusable selector, with reported visibility, pending/
failure status and unavailable reasons. Footer actions and redundant labels are removed. Review fixtures explicitly emulate
visibility without creating windows or device commands. Native runtime admission,
completion correlation and external-window feedback are still integration work.

Additional CephVR1.0 source review at the same unchanged HEAD found useful candidates
in `protocol/src/protocol/gui/experiment_window.py`: geometry retention across trials
(`dashboard_preview_window_geometry`, line 22847), console scroll preservation
(`_set_console_text_preserve_scroll`, line 27834), a native output folder picker
(`select_output_directory`, line 28655), compact paths with full-path tooltips
(`_CameraConfigPathLineEdit`, line 4199), and field-specific help (`add_field`,
around line 4316). Viewer geometry restoration for backend-owned image windows remains integration work. Source review establishes
these mechanisms, not their rig behavior. Folder selection, compact paths, scroll retention and selector geometry memory are
now accepted and implemented in the frontend. Contextual help remains a suggestion;
external backend viewer geometry integration remains pending. Shared round indicators, bounded logs and modeless tool
windows already reuse useful reference patterns with smaller focused components.

### Dashboard frontend implementation

Finalization result/reset (`finalizing-log-after-reset`, Oct21): fixed under
[G02](../docs/architecture/gui.md#g02) revision97 and
[E08](../docs/architecture/system-contracts.md#e08) revision179. Reset copies one
latest terminal session/trial view into `Snapshot.last_finalization` under the
lifecycle lock, before retiring active identities. The GUI finishes only already
shown rows with matching controller/session/trial identities; clean finalization
shows `[Done]`, while trial interruption remains a distinct outcome. Reconnect
never replays old success. The view is overwritten on the next retirement and is
not a history log or a work scope. This closes the stale Finalizing files row
without using disappearance as output-integrity evidence.
Finalizing already locked editing; Setup/New session now also require editable,
cleanup-safe state. Snapshot cleanup blockers lock protocol/session editing even
in Configuration. Controller Setup refuses wrong phases or unresolved cleanup at
initial admission, before configuration loading, and retains its atomic commit
check. Gates reopen after confirmed cleanup; no artificial post-cleanup delay.
ARCH-002 reuses focused reset/snapshot/projection owners without dependencies or
lifecycle/deadline changes; existing size advisories remain cohesive.
Validation: generated19 Protobuf sources; controller suite733 passed,4 skipped,
6 deselected; focused GUI30 plus14 phase/control cases pass. Ruff lint/format336,
Win32 mypy302, boundaries742/zero and whitespace pass. Sandbox fixture/temp and
stalled event-loop attempts did not pass; normal Windows execution does. No native
restart or rig acceptance; existing interruption-configuration-reset tracks it.

Inline action progress/results, 2026-10-21 (`console-progress-in-place`,
[G02](../docs/architecture/gui.md#g02) revision 96): background SpikeGLX inventory
reads remain silent. Requested actions and snapshot operations use scoped retained
text blocks; observed results append `[Done]`, `[Failed]`, `[Cancelled]`,
`[Rejected]` or `[Unconfirmed]` without changing the original timestamp or adding
success rows. Counts and stage changes replace the same scoped row in place,
including texture decoding and initial uploads in Dashboard and Projectors.
Preserve the original timestamp, unrelated rows, selection, reading position across
wrapping and follow-at-bottom. Progress alone appends no Done; participant checks
explicitly confirm preparation. Missing work alone never proves success. Retained
failures keep context-menu diagnostics; eviction never redirects results to newer
rows, and failed requested actions retain fallback details when their row expires.
ARCH-002 review reuses ActionProgress and LogConsole, with no dependency or backend
state changes. main.py's existing size advisory remains GUI signal/view wiring;
row ownership stays in the console and evidence projection in ActionProgress.
Focused offscreen result:21 passed, including500 count updates, stage replacement,
interleaved rows and both themes. Changed-file Ruff lint/format and whole-GUI Win32
mypy187 passed before concurrent finalizing-log edits; the later static repeat
reported formatting and a duplicate key annotation in that ongoing action_progress
work. Boundary check742/zero passed. Native appearance remains unchecked;
see LOG.md for commands and attempt limits.

Runtime log/HUD format, 2026-10-21 ([G02](../docs/architecture/gui.md#g02) revision 91):
log rows render as `HH:MM:SS SUBJECT step` through `gui/log_format.py`; `LogConsole`
skips exact consecutive repeats (bound error entries are always kept). Controller Setup,
Start, interruption and cleanup step strings are shortened; the Dashboard HUD adds
an Output row showing the reserved session directory. Focused GUI log/HUD tests
(159) and the controller suite pass. Four timeline/variation hover cases fail
because native MouseMove is not delivered in this desktop session; they are unrelated
to these changes. The format has not yet been checked in the running GUI.

Tracking frontend review, 2026-10-06 ([G01](../docs/architecture/gui.md#g01)
revision 118, [G02](../docs/architecture/gui.md#g02) revision 33): role-derived
Preprocessing/Calibration/Pose/Motion retains source-pixel crop-before-downscale,
editable point tables and independent image-plane distance calibration. Subject
reference now places Set points and Clear at the left, without a point-count label;
Clear preserves manual pose and distance calibration. Numeric rectangle bounds
remain editable; Draw region actions are removed. Preprocessing has only Enable
crop and downscale; output-size and uncalibrated-scale captions are removed.
Valid calibrated scale is still displayed. Manual pose now uses natural method-form
sizing and measured table rows, with Set landmarks aligned left.

Enable switches now cover pose, sampling region, optical
flow, flow quality and locomotion. They dim dependent controls without losing values,
close annotation editing when toggled and persist in a separate diagnostic map.
Draft v4 migrates v1/v2 enabled and v3 by removing the obsolete preprocessing
diagnostic flag, preserving crop/downscale and other switches. Invalid flags fail
before mutation. These flags never enter experiment configuration: T02 still requires every
stage of the selected experiment pipeline. Live diagnostic execution and timing,
managed submission, acquired-image transforms and overlays remain pending. Optional
crop/downscale and chosen pose/analysis methods retain their semantics. Image-plane
scale does not establish physical swimming velocity or change T35/T38 output units.

One shared DataTable now applies Cameras styling to camera/projector inventories,
Tracking points, MCU I/O, SpikeGLX channels, screen calibration and dimensions.
Persistent editor sizing includes Qt's item insets; visual inspection caught and
corrected double padding and unpolished row sizing. Shared row-height checks now
assert full editor containment. Coral remains on page/navigation accents; blue
headers and existing editing/authority behavior are retained. ARCH-002 uses focused
stage and table helpers without new dependencies or runtime back-references.

Validation: current Tracking/review-draft checks pass 13 tests (221 deselected,
9.63s), including v1/v2/v3 migration, retained settings and Manual form containment
at 1280/720px. The new uncalibrated-label assertion initially ran after calibration
had already updated it; its ordering was corrected. Ruff lint/format (seven files),
Windows-target mypy (five source files), boundaries (563 modules, zero violations)
and whitespace pass; existing unrelated size advisories remain. Inspected
Preprocessing, Calibration and Pose at both widths plus native Manual pose. The
updated review GUI remains open (PID 36708); temporary helpers/captures removed.
Native UI automation inventory timed out, so validation used the app's own capture.
Previous shared-table GUI evidence: full suite 233 passed/one skip before final
sizing, then 39 affected passes. Previous backend evidence remains 36 local Tracking
plus six authenticated loopback passes, one Windows test excluded. No backend
processing changed; these local checks do not establish Windows/hardware acceptance.



The 2026-10-06 [live connection checks](device-connection-evidence-2026-10-06/README.md)
confirm controller-backed COM8 Connect and both assigned Basler connection tests,
including camera closure and successful original-draft restoration. Earlier
timeouts were isolated to acquisition worker PlanLaunch credential/empty-work
errors, now repaired in the existing launch/transport owners. Stale generated
bindings were regenerated from authoritative schemas; the unarmed watchdog fix
is recorded in [acquisition status](acquisition.md).

G01 revision 108/E07 revision 58 allow flags-only camera participation edits
without capture-ready settings. A real controller accepted both Use flags with
missing trigger sources, stayed alive for 25 seconds, and restored the draft.
Setup and settings edits keep full validation. Absolute native-picker directories
address the relative file:. warning. Native job inspection retries errors within
its existing three-pass bound; persistent unknown membership retains guards and
containment deadlines during shutdown. Original WinError 5's underlying OS cause
is not established; it recurred during the later authenticated shutdown for
acquisition PID 18904. The launcher released its guard without the posted traceback.
After the owner reported duplicate startup, native window inventory showed no GUI
but a live controller. The retained test generation was shut down through the
existing authenticated command; port 50051 is absent and the application guard
can be acquired. No replacement runtime is left running. Failure
diagnostics now retain role/PID/native cause and acquisition shutdown reason.
Portable controller/supervisor/platform/launcher: 356 passed, 2 skipped;
supervisor rerun: 106 passed; GUI selection: 4 passed; two real Windows containment
checks passed. Scoped lint/format, Windows-target mypy and boundaries pass.
ARCH-002 review retains cohesive native jobs/shutdown owners and introduces no
dependency or policy. Capture, preview, electrical pulses and full rig acceptance
remain in the existing checklist; no history save or pulse output occurred.

The later Behavior-camera PFS error was reproduced and repaired in the focused
GenApi helper: absent optional effective-exposure nodes and float Gain without
an increment are valid device capabilities. Controller camera completion now
retains the original failure text. Preserved the operator's current draft before
an authenticated idle-runtime restart, restored it, and verified PFS import,
readback adoption and Finish editing through the controller. The camera reports
closed/no cleanup pending at adopted revision 3; control was released and the
managed GUI remains running. Acquisition/controller checks: 406 passed, 2 skipped.
The preceding discovery-only inventory messages were not proof of camera opening.
The later command rejection was a lease-loss cleanup barrier: untouched Tracking
was absent from acquisition status, despite a fresh coordinator owning no camera.
Both roles now start with explicit closed/no-preview/no-cleanup facts; access still
requires exact subsequent evidence. Controller cleanup remains strict. The final
live PFS import/Finish editing, both camera tests, release/reclaim and both camera
retests pass; both cleanup operations succeed. Worker small edits retain normal
result reservations, avoiding unnecessary exhaustion of full-readback budgets;
readback operations and all ceilings remain unchanged. Acquisition/controller:
408 passed, 2 skipped; scoped static checks pass. A preceding attempt exited on
SUPERVISOR_HEARTBEAT_FAILED, retained as an unresolved native startup finding.

The 2026-10-06 runtime synchronization check confirms the managed launcher imports
`cephvr.gui.main`, whose ManagedDashboardWindow inherits the same DashboardWindow
and screen components used by review. Current Protocol/Devices layouts therefore
already apply to runtime; no duplicate frontend or build step was needed. A local
probe instantiated the actual ManagedGui/ManagedDashboardWindow with discovery and
transport substituted, installed authoritative-shaped protobuf snapshots, and checked
camera/rate and MCU/pin field completion reaches the existing bridge requests.
Snapshot installation emits no update requests; control loss disables editing.
Removed buttons/Stream controls are absent or hidden in the managed window, and the
unwired calibration presenter remains disabled. This verifies client wiring, not
authenticated transport, Windows startup or physical device execution.

Current GUI checks: **202 passed, 11 deselected (118.39s)** for the GUI/launcher
selection command (the selector included all portable GUI tests and excluded the
launcher cases). Ruff lint/format (97 files), Windows-target GUI mypy (96 source
files), boundaries (551 modules, zero violations) and whitespace pass. Updated the
runtime guide's obsolete Save-button instructions and calibration preparation wording.
No new source change or architecture amendment was required; G01/G02 already govern
the shared frontend. The existing main/camera/Protocol cohesion advisories were not
extended. The temporary managed probe and QSettings were removed. Windows runtime
startup and pending Protocol/projector/SpikeGLX configuration and calibration-output
bindings remain in the existing worklist.

The 2026-10-06 SpikeGLX refinement under [G01 revision 106](../docs/architecture/gui.md#g01)
removes the Stream header/selector from Input channels, leaving Use, Signal, Index,
Channel and the custom-input remove action. Existing stream identities remain in
retained mapping metadata so review-draft load/save does not discard them. Source
refresh cannot reveal the hidden stream controls. No managed acquisition behavior
changed. Existing SpikeGLX, draft-restoration and device-reflow checks: **6 passed,
197 deselected (3.97s)**. Scoped Ruff lint/format, Windows-target mypy (1 source file),
boundaries (551 modules, zero violations) and whitespace pass. Native inspection
checked the compact mapping rows, including a custom input; inspection closed and
the isolated GUI reopened on SpikeGLX. Temporary inspection artifacts were removed.

The 2026-10-06 Devices refinement under [G01 revision 103](../docs/architecture/gui.md#g01)
removes Save camera settings and Save pins. Managed clients submit completed fields,
camera trigger/PFS selections, COM selections and fixed I/O enable changes through
their existing controller requests; loading snapshots and refreshing ports stay
silent. Unfinished/invalid camera hints remain drafts, and pin tests require the
controller-confirmed configuration. Managed enable/pin edits lock during diagnostics.
Isolated review still sends no hardware commands. Under G01 revision 104, the separate
Prepare calibration files button/signal are removed; Launch prepares the diagnostic
GLB/display profiles and requests output only on success. Managed calibration
presentation remains unfinished. The focused calibration run passes **5 checks**
(198 deselected, 3.80s), including automatic preparation, preparation-failure gating
and confirmed Launch/Close state. Scoped Ruff lint/format (3 files), Windows-target
mypy (2 source files), boundaries (551 modules, zero violations) and whitespace pass.
Native Projectors inspection checked the simplified Screen calibration card and closed
before reopening the isolated review GUI.

Local affected GUI checks: **19 passed, 184 deselected (12.78s)**, then **2 passed,
201 deselected (3.65s)** after extending scan/snapshot silence coverage. Scoped Ruff
lint/format (4 files), Windows-target mypy (3 source files), boundaries (551 modules,
zero violations) and whitespace pass. Native Cameras/Microcontroller inspection at
1280px and narrow Microcontroller inspection at 720px were closed after review.
ARCH-002 review retains the cohesive camera panel's widget/draft/intent owner
(602 lines); transport and device execution remain in separate existing modules.
No new dependency or backend policy. Native Windows and physical controller/device
acceptance remain in the rig checklist; local review is not evidence of that pass.

G01's family-specific editor now gives Images Fit (Contain/Cover/Stretch), Move
speed and Direction, with initial position and whole-image rotation in Advanced
settings. Fit has a Batch edit dropdown and is excluded from numeric variation.
New Images use Contain; omitted legacy values preserve Stretch under
[V04](../docs/architecture/visual_stimulus.md#v04). Video hides Retain state/Linked
to; 3D arena hides Retain state in generation and editing. Both preserve loaded
reset values during other edits; Looming hides Linked to.
Image motion uses the existing 2D state, with no texture phase conversion. Fades
and existing closed-loop availability remain in their owning forms.

The 2026-10-06 arena visibility refinement under G01 revision 113 reuses the
shared stimulus editor without changing runtime reset policy. Focused family,
arena-variation and full-selection checks: **8 passed, 217 deselected** (8.60s).
Scoped Ruff lint/format (two files), Windows-target mypy (one source), boundaries
(559 modules, zero violations) and whitespace pass. These are local Qt checks;
no native Windows or physical projection acceptance is claimed.

Local checks for this increment: GUI suite **195 passed, 1 deselected**;
the final family/legacy/Batch-fit subset **5 passed, 192 deselected** after adding
the last compatibility scenario. Rendering, compilation and contract checks:
**68 passed, 79 subtests passed**. Scoped Ruff lint/format (16 files), Windows-target
mypy (14 affected files; an earlier broader pass covered 124 source files), schema
generation/check (11 schemas; Program/PreparedTrial regenerated), boundaries
(550 modules, zero violations), and whitespace pass. Native Qt inspection checked
mixed Image/Texture/Video/Looming rows and advanced cards at wide and settled 720px
layouts; inspection windows were closed and captures removed. The comparison review
window subsequently exited normally; the standard isolated GUI was reopened for review.
The 504-line StimulusParameters remains the binding/atomic-commit owner; image
fields and fitting math are separate focused modules. The existing canonical model
and renderer composition remain cohesive. GPU shader compilation and physical
Windows projection are not established by these portable checks; the existing rig
worklist remains authoritative.

[G01 revision 111](../docs/architecture/gui.md#g01) gives a single Timeline
selection the shared full Batch generate form: duration, stimulus mode, batch
label and each projector/layer's stimulus parameters. Duplicate/Delete sit before
Preview in the timeline header; at narrow widths their row sits below the title
without clipping. Selection/authority guards and shortcut behavior are preserved. Target epochs retains
parameter-at-a-time batch controls with All epochs, Epoch label and Epoch index
filters. Parameter choices derive from the same generation-column definition,
plus Duration/Asset; Opacity is absent. Rotation is Texture-only, Image exposes
Fit/Speed/Direction, Looming exposes size/growth, Video exposes Start/At end, and
arena exposes longitudinal/lateral/angular gains. Video end behavior uses a
dropdown; arena patches reuse the existing gain/channel helper used by variation. Labels refresh from the current trial; a one-based index selects a source
epoch, including nested groups without expanding repeated occurrences. Invalid or
out-of-range indices or missing label matches stay quiet during editing; Apply
opens a warning and rejects mutation, including direct apply calls. Validation
actions remain enabled so operators can obtain the failure reason.
Changing filters with unapplied edits restores the accepted filter. Epochs,
Filter and any label/index choice share one row; Parameter and the duration or
per-projector values share the row below. Fixed matching durations retain their
clock value; mixed/variable durations show hh:mm:ss, without staging a patch.
Targeting and epoch identity fields share equal grid columns, matching control
heights and explicit 12px gutters. Timeline selection keeps its larger section gap.
Discard/Apply sit opposite the Batch generate/edit tabs at the card's top right
across selection modes; Apply has primary emphasis. The shared
pair dispatches to the full selected-source form or the target patch, without a
second pair in the form. The redundant All parameters inspector shortcut and
Projector header in parameter editing are removed. Shared FormNotice removes inline error/status labels: action failures open one
window-modal warning per form; passive checks remain quiet, and status events
reach the Dashboard activity log. Editing-authority loss dismisses owned warnings. Empty narrow projector rows omit unused asset/numeric placeholders.
Batch generate aligns field heights and uses consistent horizontal/vertical gaps. Multiple
Timeline selections retain
batch patches for mixed settings, with structural actions disabled. Returning to
Timeline selection restores the previous targets. Pending form edits block a scope
switch until applied or discarded. Apply preserves source epoch identity, isolates
shared projector layers and copies changed scenes without altering sibling epochs.

Keyboard-only undo/redo, Ctrl+D duplication and Backspace deletion remain guarded;
text editing and multiple-selection protection are covered. The timeline has no
internal scroller, fits the largest enabled-screen layer stack across the trial,
and caches sizing by immutable program/screen identity. Trials matches its height;
the Protocol configuration section remains scrollable.

Final fresh GUI suite: **216 passed, 1 deselected** (125.59s). Focused targeting,
notice lifecycle, selection, generation, media and variation checks: **21 passed,
196 deselected** (21.86s). Tests verify quiet invalid filters until Apply, rejected
mutation, warning-window content/reuse, dismissal on editing-authority loss, and
status delivery to the activity log. Scoped Ruff lint/format (18 files), GUI
Windows-target mypy (100 sources), boundaries (556 modules, zero violations), and
whitespace pass.
The 2026-10-06 spacing refinement under [G02 revision 25](../docs/architecture/gui.md#g02)
uses one 8 px token for the dependent sections below SpikeGLX control, photodiode
pulse, Tracking crop and Variation rules. Margins belong to dependent sections;
hidden variation content leaves no spacer. Table/recording checkboxes keep their
row alignment. Four rendered sections reviewed and inspection window closed.
Focused owning GUI checks: **8 passed, 225 deselected** (6.12s), including narrow
variation layout. Scoped Ruff lint/format (five files), Windows-target mypy (five
sources), boundaries (561 modules, zero violations) and whitespace pass. No new
dependency or runtime behavior; native Windows/rig acceptance remains pending.

Under [G02 revision 24](../docs/architecture/gui.md#g02), protocol forms share the
notification helper: passive validation stages diagnostics privately, explicit
failed actions warn, and transient status goes to the log. Generation's live
preview no longer disables Add merely for invalid draft values; Add validates and
warns without mutation. Under G01 revision 114, shared parameter commits and
layer/type/scope navigation stage diagnostics privately. Parameter errors surface
once through the owning Add epochs/Apply edit action, including the projector
and specific invalid value; rejected navigation retains the pending draft.
Preparing a variation stays quiet. File-picker/load failures still warn at their
explicit file action. No new dependency or runtime policy. Local GUI suite:
**226 passed, 1 deselected** (144.70s); final submission/target/navigation subset
**5 passed, 222 deselected** (8.37s) after quieting the remaining batch navigation
guards. Scoped Ruff lint/format (six files), Windows-target mypy (five sources),
boundaries (559 modules, zero violations) and whitespace pass. Tests preserve
invalid drafts, verify a single warning on submission and corrected resubmission.
No native inspection window or hardware process was spawned for this increment. Authored timeline/preview counts remain visible data.
Native review confirmed an unmatched label is quiet, Apply opens the themed warning,
and status reaches the log. Inspection window closed normally. The first review
handoff subsequently exited; the updated isolated Protocol GUI was reopened.
Temporary helpers, QSettings, captures and results were removed after assessment.
ARCH-002 extracts notification/dialog lifecycle and the focused log event into
notices, removing InlineMessage and repeated inline-label behavior across protocol
forms. Existing form/document/history and controller ownership remain unchanged;
no dependency or backend policy changes. StimulusParameters remains the cohesive
binding/atomic-commit owner, with notification behavior delegated. Concurrent
launcher/controller/Tracking work and rig evidence were preserved. These checks
do not establish managed runtime or physical rig acceptance.

2026-10-06 portable update review of `c0120e9`: inspected the managed/review launcher
split, controller bridge, camera viewer, MCU wiring, draft persistence and renderer
startup amendments under G01/A03/E08. Refreshed the ignored generated bindings from
the 19 authoritative Protobuf sources; stale local bindings caused the initial
missing-field test/type errors. No hand-written implementation was changed.
The initially failing SpikeGLX review-action expectation was reconciled with the
intentionally disabled sample-mode connection button during the following authorized
layout increment; managed connection-query wiring is unchanged.
The existing Windows 720px horizontal-overflow finding below remains open; the
corresponding portable test passes on this macOS checkout.

The eight affected acquisition/controller/shared/Visual Stimulus test modules
report **82 passed**. Authenticated client RPC tests report **6 passed** after a
permitted loopback rerun (the sandbox attempt had five socket-binding errors).
GUI Ruff lint/format (96 files), Windows-target mypy (93 source files), and backend
boundaries (547 modules, zero violations) pass. Cohesion warnings remain review
prompts, not acceptance failures. These checks do not establish Windows runtime,
physical camera/MCU/SpikeGLX behavior or full rig acceptance.

Native simulated review inspected Dashboard, Protocol and all four Devices subtabs
at the wide layout and Cameras at 720px. The inspection window was closed, temporary
captures removed, and the standard isolated review GUI reopened for layout work.
The current commit also tracks 81 `.local-*` test-output files, including generated
locks, fixture images and review drafts; they are housekeeping leftovers, separate
from the dated rig evidence that must be preserved.

The SpikeGLX managed Devices panel now sends a read-only authenticated controller
connection query. It reports the saved endpoint, SpikeGLX version, running/saving
state, run name and data directory via the official SDK. The local SDK readback and
focused GUI/RPC checks pass. A later managed launch displayed a connected
Dashboard after concurrent renderer startup fixes, but it exited before the
button could be clicked. The agent's UI tool could read but could not click the
window. A retry ended with `JOB_INSPECTION_FAILED`; the exact SpikeGLX button
response remains unverified.
The separate E12 session lifecycle port is still unavailable, so pairing is not
claimed ready. See [E12](../docs/architecture/synchronization.md#e12) and the
[rig worklist](rig-verification.md).

2026-10-05 Windows rig review, current `main` checkout: PyQt6 constructed the review
Dashboard at 1280×800 with real discovery. Both expected Basler serials appeared in
Cameras; `Test enabled` opened, identified and closed 40065509 (`acA4112-30uc`) and
40747103 (`a2A2464-77umPRO`) without capture or settings writes. Dashboard,
Protocol, Cameras, Microcontroller, Projectors, SpikeGLX and the Tracking placeholder
were visually inspected from transient Qt grabs; cards, controls and text fit at that
size, with lower editor content available through the page scrollers. The GUI
discovered two COM ports without opening either. The current Qt session reported
one 1920×1080 Dell operator display
and no secondary projectors, so physical output assignment cannot be checked from
this session. The reviewed PNGs were deleted after inspection.

The focused Windows `test_devices_draft_reflows_without_horizontal_clipping[720]`
fails: the Devices scroller has horizontal overflow (48px in the test, and a direct
probe found 28px Cameras / 164px Projectors). This is an observed narrow-layout
defect, tracked in TODO. The first broad GUI run also emitted Qt access violations
and temporary-directory errors; the offscreen rerun encountered many setup/errors
and could not finish because pytest was denied access to its generated basetemp.
Focused camera/controller and authenticated-client runs also encountered
temporary-directory permission failures; no backend suite pass is claimed.
These runs provide no passing GUI-suite claim. Scoped Ruff/format pass (87 files),
Windows-target mypy passes (86 GUI files), and the boundary checker reports 539
modules with zero violations and existing cohesion advisories. The real-camera
review console now identifies discovery accurately instead of claiming sample input.
Two focused camera-review behavior tests pass after that change.

Managed camera wiring under [G01](../docs/architecture/gui.md#g01),
[E03](../docs/architecture/gui.md#e03),
[A03/A10](../docs/architecture/acquisition.md#a03) and the
[preview contract](../contracts/acquisition/preview-control.md) now has a separate
`cephvr.gui.main` entry point, exact GUI credential, observer WatchState stream,
explicit control claim/release, current-revision camera Start/Stop/Attach RPCs,
attachment query and release reports. The GUI preview reader waits on the A03 event,
copies the newest slot, converts it off the Qt event thread and coalesces delivery to
one pending image. The managed window leaves unrelated configuration editors disabled
until their controller submissions are implemented. Existing saved acquisition settings
must enable the backend and assign a camera before Start capture is available; the
current default leaves acquisition disabled; COM8 and D10/D11 outputs are now
assigned, while camera trigger input and other camera settings remain incomplete.
The GUI still lacks a separate editing-only Connect operation,
camera/PFS config submission and broader backend controls. No actual camera frame or
full managed launch has been verified in this increment.

Managed normal window closure now requests the controller's existing E07
`SaveConfigurationHistory` RPC before exiting. An observer acquires control only
when the lease is free; another holder causes an explicit save failure. The UI
offers Retry or Close without saving on failure/disconnection. Controller restart
already loads `config/last_configuration.json`, preserves accepted disabled-backend
settings and fills missing defaults. A focused GUI close-flow test and authenticated
loopback save-to-disk test pass. This applies to the controller-accepted reusable
configuration; review-only local drafts are not controller settings. The full
managed close/restart sequence remains unverified on the rig. The renderer startup
heartbeat defect below is corrected, but the bounded startup probe did not exercise
a controller configuration save or explicit E08 application shutdown.

The `scripts/start_gui.py` design-review window now atomically saves its local
editable drafts to ignored `config/review_draft.json` on close and restores them
after camera/display inventory on its next launch. It retains subject, device,
recording, projector and canonical trial-program drafts without claiming backend
application. A damaged prior file is preserved and warned; close-time save errors
offer Retry or Close without saving. The focused managed/review GUI and
authenticated controller persistence run passed 10 cases, with one additional
malformed-draft read check; Ruff, Windows-target
mypy on five affected sources, backend boundaries (546 modules, zero violations)
and diff whitespace checks passed. The controller's E07 history remains the
only accepted reusable experiment configuration.

2026-10-05 local rig-review MCU correction under [G01](../docs/architecture/gui.md#g01)
and [A11](../docs/architecture/acquisition.md#a11): the COM Test connection and
per-pin Test/Stop controls now use an exclusive acquisition serial owner on a Qt
worker thread. Numeric GUI pins map to Uno D pins; camera rows use their retained
requested rate. Firmware bounds each diagnostic to two seconds, and the GUI shows
matched active/inactive edge counts or command failures. Close requests an explicit
stop before port release. Isolated sample fixtures retain command-free behavior.
The focused MCU/review GUI and acquisition serial subset passed 56 cases after
a fixture-state correction;
the initial sandbox pytest run could not access its Windows temp directory. A live
COM8 test through the new worker confirmed firmware `cephvr2_uno_1`, protocol 2,
stopped outputs, then D2 active with zero edges and inactive with 120 rising edges
after 2.2 seconds. This confirms the input diagnostic path and observed D2
transitions, not the projector as their source. D9/D10/D11 outputs and receiving
channels remain untested. The managed GUI still uses its controller-owned route.

The standard entry points are now separate under [G01](../docs/architecture/gui.md#g01)
revision 96: `scripts/start_gui.py` always opens fixture cameras, four simulated
projector displays and one simulated Arduino entry, without OS camera/display/COM
inventory. `scripts/start_runtime_gui.py` enters through the Windows application
launcher and its managed GUI. The managed Devices page inventories real Basler
cameras, secondary OS displays and COM ports at startup even before a control lease;
these display/port scans are read-only. Focused GUI tests passed 41 cases, including
fixture isolation and managed pre-control inventory. Script-command smoke checks
confirmed the selected modules and required launcher arguments without starting
the runtime. A later bounded managed launch is described below. Physical display/MCU
checks remain separate.

2026-10-05 VS Code runtime launch follow-up: added explicit review and managed
Run and Debug profiles using the repository `.venv`. A real managed launch initially
failed because the user-profile CephVR runtime directory had an inherited Windows
DACL; the exact directory was repaired with the repository owner-only helper and
verified. The first renderer heartbeat lacked an E08 lifecycle phase, and after
that was repaired the idle coordinator aggregate declared a cleanup catalogue
revision before session registration. The worker now provides an initial
configuration phase and a setting-up phase with its resource catalogue; the
coordinator forwards the phase and omits the idle revision. A bounded managed
launch kept every role and the real Dashboard window open beyond 25 seconds, with
repeated accepted renderer heartbeats. The VS Code profiles use the repository
`.venv` without debugger attachment to child processes, preserving startup
deadlines. An offscreen managed GUI construction check inventoried two cameras and
two COM ports. The speculative heartbeat timestamp adjustment and diagnostic
instrumentation were reverted. No Setup, preview capture, pin output or projector
presentation occurred. GUI closure intentionally leaves the application running
under E08; the diagnostic launcher remained active and was later found to hold the
single-instance mutex. Its exact process identity and ancestry were verified
before it was stopped; the mutex was then confirmed available. Explicit E08
application shutdown and same-generation GUI relaunch remain unverified or
unimplemented, respectively. Earlier intermittent native process-inspection access error
and later lifecycle phases remain unverified. [Dated startup evidence](gui-startup-evidence-2026-10-05/README.md)
contains raw traces and limits.

2026-10-05 managed control audit under [G01](../docs/architecture/gui.md#g01),
[E03](../docs/architecture/gui.md#e03), [E07](../docs/architecture/experiment.md#e07),
[A10](../docs/architecture/acquisition.md#a10) and
[A11](../docs/architecture/acquisition.md#a11): the Dashboard now exposes Take
control, including explicit takeover confirmation when another operator holds it.
The Cameras Use checkbox submits an E07 update by assigned serial and waits for the
authoritative snapshot; rejection restores the previous state and is logged.
Camera config now submits its PFS path, FrameStart line source, timing selection and
requested pulse rate through the same revision-checked route. Managed Microcontroller
configuration submission includes both camera outputs as well as Trial state and Projector flip;
camera Test/Stop uses the saved behavioral/tracking signal identity. A pure validation
probe against the current rig defaults found that enabling the behavior camera is
rejected until `device.settings.trigger_source` is set; with an explicit `Line1`
source the acquisition validator returned valid. This probe is schema validation,
not proof that Line1 is wired or present on the physical camera. No camera or MCU
command was sent in this increment.

A later read-only query of the owner's live controller generation at 17:10 JST
confirmed Configuration phase, a GUI-held lease, both Basler serials discoverable,
acquisition disabled, and the enabled behavioral camera lacking `trigger_source`.
The owner's observed `REJECTED: configuration validation failed` is consistent
with the acquisition validator's `TRIGGER_SOURCE_REQUIRED` issue. The controller
now includes the first field issue in edit rejection text, and the GUI explains
the missing FrameStart line before sending the enable request. Focused GUI
enable tests passed 3; controller configuration transactions passed 17 with
1 skip outside the sandbox after Windows temp access denied the sandboxed run.
Ruff, Windows-target mypy, backend boundaries and diff whitespace passed. These
changes require a new application generation; the owner's running GUI and
controller were left untouched. The archived 2026-09-29 behavior PFS records
FrameStart `TriggerMode Off` with `TriggerSource Line1`; its Line1 entry alone
does not establish a currently active external-trigger configuration or wiring.

At this historical audit checkpoint, Dashboard subject/recording forms, Protocol,
projectors, SpikeGLX mapping and Tracking still lacked complete managed routes. The
[current wiring assessment](#current-scope-and-review) supersedes that implementation
status; the rig evidence below retains its original scope. Existing managed
Start/Stop/Attach preview, MCU diagnostics and SpikeGLX connection tests require
separate rig execution; the audit did not prove them from a live click. Focused
managed camera/control/MCU Qt tests passed 10 cases; related controller configuration
transaction tests passed 26 with one skip. The broad GUI suite reached
two failures before a Qt access violation stopped collection; the first expects an
older SpikeGLX review log message, and the second compares Qt forward-slash paths
with Windows backslash paths. Neither assertion covers this increment. This is
not a suite pass. Ruff lint, Windows-target mypy on 93 GUI source
files, backend boundaries and diff whitespace checks are recorded in LOG. The
585-line camera panel and 564-line managed entry prompted ARCH-002 cohesion review:
the panel still owns one camera UI state, while the entry coordinates distinct
transport/views; further backend binding should be extracted before extending them.

2026-10-05 Windows in-memory native preview check: the first 2×2 A03 ring attach
failed because CPython's shared-memory attach requested more mapping rights than the
owner-only DACL granted. Giving the same owner all non-execute mapping rights fixed
that attach without widening principal access. The next run exposed that the rig's
pypylon marks inactive converter controls read-only and copies a memoryview source.
Setting only the active truncate-mode shift and accepting that private SDK copy made
the ring-to-8-bit-GUI-reader check pass, including reader closure. This is an actual
Windows ring/converter test, not a Basler capture, frame-rate or optical pass.
The older CephVR1.0 `FrameStreamWorker` emits one Qt signal per frame; the new reader
retains only one replaceable pending image to avoid a render backlog. Rig throughput
for that improvement has not been measured. The focused authenticated-client,
credential, native-mapping, manual-preview and GUI checks pass (11 selected); 30
controller-camera/ring checks pass separately. Ruff, Windows-target mypy and backend
boundaries pass with existing cohesion advisories. Owner-assigned trigger wiring or
an explicit temporary unaligned free-running test is needed before live capture.

2026-10-05 managed launcher check: an inherited user-profile runtime DACL rejected
GUI credential provisioning, so the launch was repeated with an isolated owner-only
runtime under the workspace; that temporary credential directory was removed after
the launcher exited. Startup then exposed stale bootstrap-handle closure in the
acquisition, Visual Stimulus, renderer and Tracking entries, and a missing Tracking
policy descriptor. Correcting those and confirming each backend's existing supervisor
launch record let startup reach the renderer. The renderer subsequently reported
`VISUAL_STIMULUS_WORKER_FAILURE: original Visual Stimulus peer deadline expired`;
the supervisor performed safety shutdown and an emergency report records the error.
Its cleanup also logged `VISUAL_STIMULUS_EVIDENCE: cleanup command unknown` and an
async admission conflict during shutdown. One further launch with method-specific
deadline text identified `ReportWorkerHeartbeat` as the expiring peer call; whether
it is delayed before submission or in the coordinator still needs isolation. The
5-second registration policy was not changed. No camera command or
Setup was issued. The real user-profile ACL was not altered. Emergency outputs from
these launches remain under `reports/emergency-*.json` as E04 runtime artifacts.
Two current managed GUI tests pass, including native latest-of-two-frame ring read;
authenticated client/shared credentials pass 12. Visual Stimulus and supervisor
behavioral tests pass 242 with the previously tracked
`presentation.pacing_refresh_hz` loader failure. Scoped Ruff, Windows-target mypy
(102 source files), boundary checks (542 modules, zero violations) and diff whitespace
pass. These tests do not close full launcher or physical camera acceptance.

2026-10-05 planner/layer/performance update at base commit
`3af4289814927c1c3fdc4251731ef894a49a1489` plus working tree follows
[G01 revision 93](../docs/architecture/gui.md#g01) and
[V07](../docs/architecture/visual_stimulus.md#v07). New GUI-created stimuli use
reset false for every family; imported explicit resets/assignments remain intact.
A shared-style Advanced settings card sits below each projector row, aligned to
Layer. Retain state comes first, then Linked to and Fade in/Fade out, then controls.
The linking/fade row reflows at narrow widths. The opacity editor is removed;
new stimuli use their constant base opacity and optional V05 linear keyframe fades.
Standard fades use exact seconds and reject negative/nonfinite/sub-nanosecond or
combined lengths exceeding the fixed epoch. Explicit duration edits retain their
lengths and move fade-out to the new end. Imported custom opacity curves remain
unchanged, with simple fade fields disabled rather than flattening saved functions.

+ Control sits below the Advanced settings/entries and opens a separate draft dialog
without changing row height. Its action hides while configuring and restores on commit
or cancellation; entries appear only after Add control. It appears only for Texture/Looming under Closed-loop, with
canonical Tracking longitudinal, lateral and angular inputs. The current V24
catalogue has no body-to-2D conversion, so committing those mappings is disabled
pending the owner's coordinate choice. Imported mappings and existing arena axis
controls remain intact. Open-loop closes the draft; Cancel/invalid drafts preserve
state. Add layer creates an empty local slot; choosing its family creates the
canonical instance, then prepared-file/motion/fade settings persist independently
across layer and projector switches. Empty slots are not serialized as stimuli.
Variation rules use a Card with body Enable and separate Projectors/Layer selectors,
including All projectors and All layers. Local ordinals resolve independently per
projector; canonical identities reject stale layers and shared targets are deduplicated.
Remove controls share the Projectors/Layer/Parameter row and height. Combine is removed from Batch generate;
equal-length rules pair by value position in entered order, without random assignment.
Method and all value controls occupy the second row; Random shows Minimum, Maximum and Precision there. Precision is a positive step (1, 0.1, 0.01, etc.).
A focused Decimal-grid sampler draws uniformly with replacement from grid multiples
inside bounds, without allocating the full grid; numeric/input-size guards and the
existing 2000 expanded-epoch bound apply to Random batches. Batch Repetitions
supplies the count: 100 creates 100 random epochs, without a second repetition
multiplier. Mixed Values/Sweep lists retain their ordered repeated sequence, with
one draw per resulting epoch; nonrandom-only batches retain existing repeat groups
and the 512-variant bound. Per-row caches include the resulting count and stay stable through preview
and insertion; changed range/precision/count resamples. Final concrete epochs
survive JSON round-trips, leaving Setup/V08 randomization unchanged. Multiple rules
still pair by position with matching counts, and one all-projector/layer rule shares
its drawn list across selected targets. Categorical video end behavior stays Values-only.
ARCH-002 reuses canonical materialization and shared row sizing, with no dependencies.
The shared stimulus-column catalogue supplies matching captions/units, including
Rotation, with Width/Height/Opacity removed. Looming size/growth and Video start/end
values materialize directly into independent canonical epochs; categorical video
end modes are preserved. Existing imported conditions and the
separate group authoring dialog retain their semantics. ARCH-002 extracted the focused
Batch variation row rather than extending the reference composer.
ARCH-002 uses focused local layer-slot and bounded timeline-view owners, without
threads or new dependencies. Unchanged metadata no longer validates the whole
program; selection reuses expanded paths/content keys (four immutable views maximum).
The timeline remains painted rather than allocating widgets or decoding each asset.
A real 200-epoch, four-projector, two-layer program exceeded the GUI's previous 1 MiB
read guard. GUI read/save validation now shares the backend's existing 16 MiB
engineering default; managed Setup limits stay authoritative. Configuration/policy
values and runtime capacity guarantees have not changed.

Heavy local offscreen benchmark: 200 epochs, eight layers per epoch, 3,202,179-byte
pretty JSON; parsing 463.26 ms, initial UI binding 333.45 ms, warm switching between
two distinct trials median 12.63 ms. These are development-machine observations,
not rig acceptance or rendering/asset-decoding throughput. A first-source fade test
confirms independently generated later epochs are unchanged; a repeated source still
applies to all its occurrences, so a first-occurrence-only fade needs a separate intro.

Explicit input/output ranges remain pending the owner's clamp-versus-extrapolation
answer. V24 currently applies gain/offset without input clipping; this update does
not silently turn authoring ranges into runtime bounds. The editor currently shows
gain/offset, not range controls.

Linked to is visible as a disabled selector in the card; movement linking is not
implemented yet. The owner confirmed clockwise Bottom drives
Right front→back and Left back→front when both sides are linked. [V02 revision 12](../docs/architecture/visual_stimulus.md#v02)
records that accepted convention and the distance-based lever arms. Pure analytic
examples with unequal distances verify opposite side directions and different
linear speeds; runtime behavior has not been exercised. The remaining pending
question is whether links follow total source motion while replacing target motion
or follow programmed motion with additive target feedback. These affect experiment
behavior and cannot be silently selected under GOV-001. CephVR1.0 reference
`optic_flow_motion.py:415–510` preserves target appearance and maps subject-frame
motion by face, but its yaw lever arm uses half the source dimensions. The new link
must use accepted rig geometry/subject distances rather than copy that approximation.
V24 does not currently declare inter-stimulus motion sources; resolve semantics
before changing program schemas/preparation/rendering. Old planner fade-in and video
loop overrides were reviewed as separate candidates; no extra overrides were added.

Trial timeline Preview opens a separate read-only snapshot window for enabled
screens on one rotatable tank view, with Play/Pause, seeking, epoch navigation and speed.
CephVR1.0 reference `protocol/gui/trial_preview_dialog.py:_TankView` paints
stimuli onto calibrated planes and culls outward-facing content. The new view reuses
TankDiagram placement/rotation, paints enabled faces from both sides without
back-face culling, using cached reduced-resolution
compositions and keeps inactive planes as outlines. Screen labels remain above the
completed scene. Default/reset azimuth is now 25° instead of 155°: Left appears
left of Right, while fixed rig planes, mappings and calibration stay attached to
the same identities. Shared TankDiagram screen painting sorts ascending view depth
so nearer screens cover farther ones consistently; the previous reverse order could
leave a face label on another face’s visible content. Native inspection confirms
separate Left/Right textures on their planes. The planning-description banner, enabled-projector text and subject
marker are removed; the observer remains in projection geometry. Rotation reuses frames; playback/seek/media changes invalidate them.
It reuses canonical
expansion and V07 state helpers, with example seed 0 and fixed-duration validation.
Images use a bounded cache; only active videos own Qt decoders. Paused windows stop
the playback timer; close/edit-authority loss cleans up resources. Current geometry
projects supported image/texture layers; unset tank/plane geometry shows a Devices
configuration prompt. No fallback tank dimensions are invented. Arena rendering is approximate, capped at 4000 triangles
and two cached scenes; unsupported/missing content reports errors per screen.
Screen scale, pixel offsets and inversions now use the shared calibration export
mapping after complete per-face composition. Pixel offsets use the assigned display
resolution, not the <=512px planning frame. Invalid/out-of-range corrections or
unresolved nonzero pixel offsets display an error; blank fields reuse export's
identity defaults. Geometry and corrections are frozen at opening, independent of
output enablement. Reopen after changing calibration. Arbitrary imported runtime
warp meshes, masks/weights and photometric corrections are not applied by this
planning view; ideal projector optics remain schematic. No live Tracking or physical
output is applied. Actual video
codec playback has not been exercised locally; Qt multimedia availability alone
is not decoding evidence. Procedural textures are not rendered in this planner.

ARCH-002 review keeps preview expansion/state, geometry snapshots, asset ownership,
canvas drawing and bounded arena rendering in focused modules. ProtocolEditor's
628-line cohesion advisory remains: its six added lines only flush/emit the request;
window/resource ownership is separate. No whole-runtime references or dependencies
were introduced. Prior 200-epoch measurements above remain historical observations;
this increment did not rerun that benchmark.

Commit cleanup (2026-10-05): removed 173 temporary native/visual/benchmark scripts,
duplicate JUnit exports and routine check outputs from the dated GUI evidence folder.
Recorded outcomes, source hashes and unique performance/native evidence remain;
removed links are labelled as removed artifacts. Functional test assets stay local.
All 170 owning GUI tests remain; the obsolete single-rule compatibility wrapper was
removed and its sweep test now exercises canonical ValueRule generation. Shared row
sizing runs once. Native narrow inspection exposed a linking/fade container that
kept its wide-row height after reflow; reserving the new minimum height keeps controls
visible while preserving Layer alignment. The owning alignment test now checks fade
control containment. Focused docstrings explain blank-layer preservation, immutable
cache identity and retained-state seeking. Batch IDs reuse one edit-local identifier
set instead of rescanning the growing document; 1000 allocations match uncached
numbering, including reserved-ID collisions. No dependencies or experiment policy changed.

Final validation: **183 GUI/client-state/compiler checks pass in 69.28s**
(`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui
tests/client/test_state_views.py tests/visual_stimulus/test_compilation.py -q
-m "not windows and not rig"`). Four focused random/batch checks pass in 3.63s; 23 advanced/control/fade/reference
checks pass in 14.94s, and the extended narrow containment test passes in 2.10s.
Ruff checks the GUI/tests/launcher and two affected Visual Stimulus sources;
format check passes 90 files and Windows-target mypy passes 88 sources.
Backend boundaries check 539 modules with zero violations; unchanged 505-line
Cameras/628-line ProtocolEditor cohesion advisories remain, with new responsibilities
kept in focused modules. The earlier broader configuration run had **187 passes and
one existing failure**, `test_default_and_file_policy_values_are_typed`: the loader
rejects checked-in `presentation.pacing_refresh_hz`. Its assertions remain unchanged;
managed pacing adoption is indexed separately in TODO. Local passes do not establish
Windows, optical calibration, video-codec or full rig acceptance.

Native wide/narrow controls inspected after cleanup; inspection exited successfully.
173 temporary repository review artifacts and 75 local review scripts/settings/flags/
captures are removed; GUI reopened for owner review.
The launch guide now distinguishes real-device discovery from optional simulated
fixtures and describes the current Protocol/Projectors layouts. Rig-specific
frontend checks live in [the rig checklist](rig-verification.md).

Prior behavior validation: **170 GUI checks pass in 91.46s**. Four focused random/paired/sweep
checks also pass in 19.40s. New coverage includes finite bounds, negative ranges,
precision grid membership, repetition-driven 100/10/999-epoch generation, ordered
mixed fixed/random rules, invalid/empty grids, cached
preview/commit values, resampling after settings change, saved JSON values and wide/narrow layout.
Existing preview/calibration tests remain in the full GUI pass. Tests compare the shared
export mapping and actual scaled/offset/inverted pixels, assigned-resolution
normalization, missing-resolution errors and invalid bounds. Prior combined
client/compiler results are historical; not rerun for this GUI-only increment.
Coverage includes menu ordering/moves, matching and ordered variation values, arena
gain variants, retained preview motion/backward seeking, image cache, window cleanup,
bounded arena drawing and rejection of unresolved timing. Windows-target mypy
passes 86 GUI files. Ruff/format and boundaries are recorded with current source
hashes in [random-variation evidence](gui-dashboard-2026-10-01/random-variation-2026-10-05.txt).
Native wide/narrow editor and four-screen planning preview were inspected; inspection
closed cleanly and temporary screenshots deleted. Reopened review uses prepared test
assets and simulated projector discovery. The existing pacing-key loader failure,
managed viewers/calibration adoption, pending scientific choices above and rig
acceptance remain open. Earlier dated evidence retains prior scope/counts.

Live camera Preview remains pending under [A10](../docs/architecture/acquisition.md#a10)
and [G01](../docs/architecture/gui.md#g01). The review GUI's Connect flag and
Preview visibility signal do not open a capture stream or image window. The
acquisition backend has manual preview commands, but this frontend has no managed
controller connection or registered viewer. An independent GUI SDK reader would
change A10's camera ownership; the owner choice for the rig test is pending.

2026-10-04 rig device review: [G01 revision 66](../docs/architecture/gui.md#g01)
changes normal `scripts/start_gui.py` and `cephvr.gui.review --review` startup to
discover attached Basler cameras, secondary Qt/Windows displays and COM ports.
Camera refresh retains drafts by serial; Test enabled uses the A10 adapter for a
bounded open/identity/close check. COM labels include the available description
while selection retains the system port path. Explicit `--simulated-devices` keeps
isolated frontend fixtures available. This remains a local review GUI; Connect,
preview, projector output, controller commands and Setup are not managed device
operations. Direct rig inventory on 2026-10-04 found behavioral serial 40065509
(acA4112-30uc), tracking serial 40747103 (a2A2464-77umPRO), COM8 Arduino Uno
and COM9 USB-Serial Controller. Both cameras opened, returned identity and closed
through `BaslerCameraAdapter`. Qt reported only the primary DELL S2721HS display;
no secondary projector output was available for an output test. This is device
discovery/control-open evidence, not acquisition, projection or lifecycle acceptance.
The rig GUI construction smoke check showed those two physical camera rows, zero
projector rows and named COM8/COM9 entries. Focused GUI checks passed (3); Ruff,
format, Windows-target mypy, boundaries and `git diff --check` passed.

Later on 2026-10-04, four secondary Qt projector screens appeared. The owner's
Windows Settings screenshot showed that DisplayConfig path positions **5, 2, 3, 4**
in Qt order did not match Settings IDs; the primary `DISPLAY9` was path 1 but
Settings label 5. QueryDisplayConfig returns path priority order, not a documented
Settings number. Under [G01 revision 70](../docs/architecture/gui.md#g01), the
GUI now assigns its own consecutive numbers to secondary screens sorted by desktop
position. The table, scaled layout, timing labels and projector labels use the same
CephVR numbers. The operator compares layout positions with Windows Settings to
associate each number; no manual ID entry or Windows-number inference remains.
Assignments and Use state stay keyed by display identity through refresh, so local
renumbering does not silently transfer a projector face. Four focused GUI checks
pass for local labels, primary exclusion, sorted ordering and retained assignment.
An additional projector-focused run passed seven tests; three unrelated file-fixture
cases could not set up because the host denied pytest's temp directory. Ruff,
format, Windows-target mypy (67 GUI source files), boundaries (520 modules, zero
violations) and whitespace pass. A native read-only GUI construction on the rig
resolved four secondary screens in spatial order: CephVR 1 at (-3840, 0), 2 at
(-2560, 0), 3 at (-2280, 720), and 4 at (-1280, 0). Actual physical surface
correspondence and projector output remain rig checks. The prior broad GUI attempt
also encountered a native Qt access violation; it is not a passing suite.

2026-10-04 projector plot: [G01 revision 65](../docs/architecture/gui.md#g01)
and [V15 revision 10](../docs/architecture/visual_stimulus.md#v15) retain shared
front-attached screen geometry, independent calibration and view-only rotation.
The Bottom diagram now draws four schematic pyramid edges from the mirror center
to the footprint, with one incoming line from the projector beneath Right. The
physical 45° reflection/clearance helper remains unchanged: incomplete outer-ray
coverage retains the valid center and dashed ideal footprint with a hover warning;
impossible central paths still omit Bottom optics. This schematic does not establish
physical mirror coverage or calibrated ray paths. Backend rendering and JSON fields
are unchanged.

Five compact buttons toggle Tank, Screens, Projection, Subject and Labels; Labels
fills the remaining second-row width. The wrapping legend remains visible, following
visible elements. Projection still groups projectors, rays, footprints and mirror;
violet footprints remain distinct. ARCH-002 review simplified the existing painter
and removed the separate legend state/button without new dependencies or modules.
Existing coordinator/backend cohesion advisories remain unchanged.

Validation: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui
 tests/client/test_state_views.py tests/visual_stimulus/test_compilation.py
 contracts/visual_stimulus/tests -q -m "not windows and not rig"` passes **193 tests
and 79 subtests in 63.76s**, including 138 GUI tests. Existing optical-path,
incomplete-coverage and phase-safe view tests remain; the visibility test now
requires exactly five controls. Ruff check/format (68 files), Windows-target mypy
(67 GUI files), boundaries (520 modules, zero violations), changed local link
targets and whitespace pass. Existing cohesion advisories were reviewed: this change
reduces the focused painter and does not extend the 622-line Protocol coordinator.
Native normal/600 mm/narrow views were inspected using explicit local samples;
rotation, disabled Right and grouped visibility were also exercised by the harness. The Bottom pyramid and five controls
fit both widths. Inspection exited 0 and closed its window. Method:
`.venv/bin/python reports/gui-dashboard-2026-10-01/tank-pyramid-native-review.py --capture`
uses Qt grabs, temporary QSettings and four simulated 1920×1080 displays; no device
commands or rig measurements. Base source `5c24d99aacf41f75fd07249faa1bfb52cf1dea78`
plus working tree; harness (temporary artifact removed)
and [source hashes](gui-dashboard-2026-10-01/tank-pyramid-source-sha256.txt) remain.
At the owner's request, all 383 generated GUI review images (including this inspection)
and three temporary synthetic assets were deleted on 2026-10-04. Their historical
assessments remain, with removed-image links converted to text. No screenshot is
retained. Managed adoption, the existing pacing-loader follow-up and Windows/optical
rig acceptance remain pending. The GUI reopened on Devices / Projectors / Rig geometry at Bottom distance 600 mm
and reported Visible: True; it remains open for owner review.

The native Protocol planner follows [G01 revision 61](../docs/architecture/gui.md#g01)
and [V02/V03/V07/V08](../docs/architecture/visual_stimulus.md#v02). Source validity
remains separate from compilation/Ready. Asset folders and recording participation
remain in-memory drafts; Save as writes one canonical trial. Session scheduling,
persistence and managed configuration/Setup adoption remain unfinished.

Recordings omits the metadata/scientific-data explanatory sentence (G01); offscreen
construction confirms the text is absent. Recording choices and backend evidence policies
retain their existing ownership. Scoped lint/format/type checks pass.

Protocol type/Load/Save as sits beside Assets. Recordings now sits on Dashboard below
Session config, in two columns with adjacent checkbox/label pairs. Camera and Visual Stimulus video switches are independent of
required lifecycle metadata and acquisition/rendering. Tracking follows closed-loop
or Tracking velocities, with no Protocol tracking-status indicator; saved video choices
survive camera disablement. Device control remains in Devices. The review fixture
explicitly starts velocity saving Off without changing T14's saved/file default On.

The planner places a 208-pixel Trials list beside the fixed-height Trial timeline, with
full-width Sequence editor inside the open group. Add/Delete sit at the foot of
the trial list. The current subgroup workflow and validation are described above
under G01 revision157. Existing reference composition supports prepared assets,
projector-local layers, exact duration, family parameters and bounded variation.
Source blocks keep horizontal navigation and visible-range painting; group repetition
counts do not allocate repeated occurrences. Explicit previews remain bounded.
Structural actions duplicate, remove and move selected subgroup sources; Undo/Redo
retains bounded per-trial history. Imported nested/condition source programs remain
preserved. Shared epoch boundaries, physical geometry and runtime ownership are
unchanged; no new serialized hierarchy or dependency is introduced.

CephVR1.0 source at `38f728291ed551a332392dc2c7b6897e8428b060`,
`protocol/src/protocol/gui/trial_planner_window_v3.py` (1490–1540, 1645–1718,
3266–3578, 4288–4530), informed direct actions, reference-plus-variation creation and
explicit-target/value batch editing. Its `.texture.json` import resolves an existing
exported PNG and declared tile dimensions; plain image pixels do not imply physical
scale. Old random-generation modes were not adopted. Source review is UI reference,
not performance or rig evidence.

Earlier official UI research (documentation review, not hands-on benchmarking) used
[PsychoPy Flow](https://devdocs.psychopy.org/builder/flow.html),
[Labvanced frames](https://www.labvanced.com/content/learn/en/guide/task-editor/frames),
[Gorilla Task Builder 2](https://support.gorilla.sc/support/tools/task-builder-2/how-to),
[OpenSesame loops](https://osdoc.cogsci.nl/4.0/manual/structure/loop/),
[BonVision series](https://bonvision.github.io/pages/04-Series-of-stimuli/) and
[sequences](https://bonvision.github.io/pages/05-Adding-sequence/). The owner subsequently
refined the native workflow into a visualization-only timeline and batch-first editor.

Previous 2026-10-03 verification (before the fixed-height/list change), working tree based on
`5c24d99aacf41f75fd07249faa1bfb52cf1dea78` plus uncommitted work:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui tests/client/test_state_views.py tests/visual_stimulus/test_compilation.py -q -m "not windows and not rig"`
passes **121 checks in 48.17s**. Coverage includes batch combinations/repetitions,
count previews, exact nanosecond durations, JSON reload, media/dimension replacement,
projector/layer isolation, atomic invalid/missing-target rejection, mixed/pending fields,
range/toggle selection across groups and nested-insertion undo. Existing cancellation,
custom-function fidelity, nested condition editing, saved-file preservation, responsive
layout, runtime edit gates and Close checks remain covered. Ruff/format and
Windows-target mypy (55 GUI files) pass. Boundary checks report 508 modules and zero
violations. ARCH-002 review separated batch mutations, composition, generation and
patch forms; extracted popup ownership and shared texture-dimension replacement.
The 627-line ProtocolEditor remains the cohesive document/history/selection coordinator
with explicit component signals, not a backend/runtime reference. Remaining size
advisories concern existing non-GUI modules; no dependencies were introduced.

2026-10-04 validation: the same GUI/client-state/compiler command passes **122 checks
in 46.83s**. Ruff/format (56 files), Windows-target mypy (55 GUI files), boundary
checks (508 modules, zero violations; existing size advisories) and whitespace pass.
Focused coverage checks review inventory/refresh/participation, list selection/draft
preservation, centered summary and stable card bounds with internal scrolling.

2026-10-04 epoch-controls review under [G01](../docs/architecture/gui.md#g01)
and [V03 revision 9](../docs/architecture/visual_stimulus.md#v03): the earlier captured
layout placed Stimulus mode on its own row and included Order; G01 revision 68 now
places mode with clock duration, repetitions, label and insertion. Reserved
heading space keeps row pitch equal with or without repeated headings. Arena mode
omits the type column and exposes independent Longitudinal/Lateral/Angular toggles
and gains using [V24 revision 7](../docs/architecture/visual_stimulus.md#v24). A zero
gain disables an axis; imported custom mappings and programmed motion remain intact. Tracking declarations are added only when needed; conflicts reject the edit. The type dropdown
changes the selected layer independently, clears its asset and blocks generation
until a compatible file is selected. A visible Layer dropdown selects the current
projector layer and its asset/parameters. The menu retains layer management.
Advanced controls are one indented, vertically separated section under the selected
projector/layer: Opacity, Retain state, and Feedback. Input declarations are inline
in Feedback; binding IDs are internal and operation follows the signal kind.
Mappings expose compatible Input signal/Parameter choices and coefficients; generic
sources require explicit metadata, not assumed runtime discovery. Loaded coefficient
functions remain read-only and preserved. Arena basic/advanced edits synchronize
without overwriting one another; invalid coefficients reject atomically. Retain state
inverts reset while preserving explicit assignments. Loaded placement and dimensions
remain unchanged. Inactive
projector content is retained. Per-projector and rig-wide arena drafts survive mode
switches; only the selected mode's referenced definitions are generated. Source files
show basenames while preserving full logical paths for loading/copy/hover. Shared
combo helpers draw a consistent chevron. Looming is the displayed family name.

Optional labels persist on every generated source epoch and remain available for
Batch edit targeting after JSON reload, including nested groups. Insertion supports append/start/before/after/replace/
every-N-blocks and After label. Label choices come from the current trial. A fresh
batch is inserted after each original matching source epoch inside its existing
group scope; new matching labels are not targeted recursively. Instance/asset/group
identities are remapped, newly generated content is bounded to 2000 occurrences and failures
leave the trial unchanged. Interval insertion consumes
one generated block per interval, appends remaining blocks, and counts top-level
repeat groups as blocks; it never flattens their scheduling semantics. New source
paths are selected after the atomic commit, and undo restores the previous trial.
The final button explicitly says Replace trial in replacement mode.

ARCH-002 review keeps reference transformations and batch insertion in focused pure
helpers; no dependencies were added. ProtocolEditor remains at 622 lines and remains
the cohesive document/history/selection coordinator. Focused feedback-entry, signal-declaration and mapping-owner modules replace the tabbed schema editor and reuse canonical units and Tracking declarations. ArenaMovement owns only its basic axis controls; the mapping owner patches explicit changes, with no duplicate program state or new dependencies. The 714-line canonical source model remains the cohesive schema authority.
Other size advisories are existing backend modules. Previous captures are historical.

Native per-projector controls (review image removed),
label insertion (review image removed),
selected layer (review image removed),
opacity (review image removed),
arena mode (review image removed) and
narrow layout (review image removed) were inspected
using the capture script (temporary artifact removed)
with `--capture`, temporary QSettings and generated PNG/placeholder GLB references.
Command: `.venv/bin/python reports/gui-dashboard-2026-10-01/protocol-layer-label-native-review.py --capture`.
These are authoring fixtures; no GLB decoding, rendering or device connections occur.
Source is base `5c24d99aacf41f75fd07249faa1bfb52cf1dea78` plus current uncommitted edits.
CephVR1.0 reference: original planner arena movement-axis/gain controls,
V3 BlockEditorDialog batch-label/insertion controls,
PlannerBatchEditDialog label targets, and `_insert_rows_every_n` in the original
planner; previously recorded reference revision `38f728291ed551a332392dc2c7b6897e8428b060`.

Current advanced-settings evidence (2026-10-04, G01 revision 64):
wide (review image removed) and
narrow (review image removed) native layouts were
inspected using the review script (temporary artifact removed)
with `--capture`; both inspections closed normally. The script uses temporary
assets/settings, four review projectors and an explicitly declared sample brightness
signal. No device connections or live feedback transport are exercised. Base revision
is `5c24d99aacf41f75fd07249faa1bfb52cf1dea78` plus uncommitted work, identified by
[source hashes](gui-dashboard-2026-10-01/protocol-feedback-source-sha256.txt).
Final `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui
tests/client/test_state_views.py tests/visual_stimulus/test_compilation.py -q
-m "not windows and not rig"` passes **151 tests in 60.32s** (138 GUI tests).
Final review GUI reports Visible: True on Protocol with Front advanced settings open.
Five focused checks cover mode width, retained explicit assignments, inline input
creation, automatic operations/IDs, invalid coefficient rollback, removal/JSON
round-trip and bidirectional arena control synchronization. Existing per-projector
isolation and custom-mapping tests remain in the owning GUI suite.
Ruff/format (68 files), Windows-target mypy (67 GUI files), boundaries (520 modules,
zero violations with existing cohesion advisories), local links and whitespace pass.
Managed signal discovery/adoption and Windows/rig validation remain pending.

Previous Protocol verification on 2026-10-04: `QT_QPA_PLATFORM=offscreen .venv/bin/python
-m pytest tests/gui tests/client/test_state_views.py tests/visual_stimulus/test_compilation.py
-q -m "not windows and not rig"` passes **146 tests in 58.25s** (133 GUI tests).
Four focused checks passed before the full run. After the native narrow capture
exposed horizontal clipping, the batch header gained a three-column fallback;
three affected checks pass, including a zero-horizontal-overflow assertion. Normal
widths retain the requested single parameter row. Native normal/narrow, selected-layer,
label-insertion and opacity views were recaptured and inspected. The capture process
closed normally. [Source hashes](gui-dashboard-2026-10-01/protocol-layer-label-source-sha256.txt)
identify the reviewed controls; no hardware/backend commands ran. Ruff/format (65 files),
Windows-target mypy (64 GUI files; also the six edited modules separately), boundaries
(517 modules, zero violations), local evidence targets and whitespace pass. A transient
full-GUI mypy run saw three errors during concurrent tank-diagram edits; a later run
passed without this task changing that file. Initial obsolete Width-editor tests were
updated to retain invalid-value, animation and reset coverage through Opacity.

Earlier arena-gain validation on 2026-10-04: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
 tests/gui tests/visual_stimulus/test_feedback.py tests/visual_stimulus/test_compilation.py
 contracts/visual_stimulus/tests -q -m "not windows and not rig"` passes **194 tests
and 79 subtests in 38.83s**. Two subsequently added focused tests pass for imported
custom/legacy mappings, channel conflicts and the pure independent-gain reference.
Fourteen initial focused checks also pass. Ruff/format (67 files), Windows-target
mypy (65 source files), 11 generated schema comparisons, boundaries (515 modules,
zero violations) and whitespace pass. The remaining cohesion advisories are existing
backend modules and the reviewed coordinator/canonical model. No dependencies added.
Coverage includes independent/disabled/reversed gains, legacy shared-gain fallback,
unit checking, save/reload, equal row pitch, control ordering and tab spacing.
The inspection window exited; the final local review is reopened for owner review.

Broader configuration testing reproduces the pre-existing `presentation.pacing_refresh_hz`
loader rejection in `test_default_and_file_policy_values_are_typed`: the earlier
GUI-selected config value exists, but managed loader adoption is still the existing
`gui-implementation` TODO follow-up. Neither the TOML nor loader changed in this
increment. Managed integration and Windows/rig acceptance remain pending.

2026-10-04 overview/inspector validation: the combined GUI/client-state/compiler
command above passes **123 checks in 47.24s**. Eight focused timeline/layer/batch
checks also pass. Coverage verifies same-setting colors across renamed/differently
sized epochs, changed-setting separation, current projector details, range selection,
unchanged source documents, fixed card height and retained pending-edit guards.
Ruff/format (58 files), Windows-target mypy (57 GUI files), boundaries (510 modules,
zero violations; the existing coordinator and backend size advisories) and whitespace
pass. Local native review does not establish managed or Windows/rig acceptance.

2026-10-04 overview/inspector increment under G01 revision 53: replaced repeated
per-projector full-trial lanes with one selectable overview plus focused projector
rows, and labeled the existing generation/patch modes Batch create / Batch edit.
ARCH-002 review keeps color keys and descriptions in a focused read-only helper,
reusing canonical layer order and parameter readers. No new grammar, dependencies
or backend behavior. Pending batch changes still reject retargeting and restore the
accepted detail selection; expanded occurrences keep their condition-specific display.
Native overview and details (review image removed),
narrow layout (review image removed) and
Batch create (review image removed) were inspected
using the review script (temporary artifact removed)
with `--capture`, isolated temporary QSettings and the existing built-in sample.
Base revision remains `5c24d99aacf41f75fd07249faa1bfb52cf1dea78` plus uncommitted work.
Inspection exited; the reviewed Protocol layout is reopened for owner review.

2026-10-04 Recordings relocation under G01 revision 52: extracted the existing
recording controls into a focused RecordingsCard owned by the shell and placed below
Dashboard Session config. Protocol reads that single draft for Tracking activation;
camera enablement, retained choices and phase/control locks are unchanged. Two-column
checkbox/label pairs fit the narrower Dashboard column. The obsolete Protocol card
placement/reflow was removed. No backend changes or dependencies were introduced.
Validation: the GUI run passed 109 checks with one obsolete expected-card-list failure;
after updating that assertion, all five affected checks pass in a focused rerun.
Ruff/format (57 files), Windows-target mypy (56 GUI files), boundaries (509 modules,
zero violations; same reviewed size advisories) and whitespace pass.
Native Dashboard (review image removed),
narrow Dashboard (review image removed) and
Protocol (review image removed) captures were
inspected with the review script (temporary artifact removed),
using `--capture`, repository Python and temporary QSettings on the same source base
plus current edits. Inspection exited and Dashboard was reopened for review. Managed
integration and Windows/rig acceptance remain pending.

2026-10-04 layout increment: the review launcher supplies four simulated 1920 × 1080
displays (2–5), assigned Front/Left/Right/Bottom. Devices table, display diagram,
participation and planner lanes share these records; Refresh preserves draft choices.
Native discovery remains the default when no review inventory is supplied. Sample
labels appear in the title/tooltips/log; there are no hardware commands or saved
assignment changes. ARCH-002 review reuses QListWidget, existing selection styling
and a scroll area; a small immutable display record shares rendering between actual
inventory and fixtures. No dependencies or backend semantics changed.

Native Protocol (review image removed),
narrow Protocol (review image removed) and
Devices (review image removed) captures were inspected
using the capture/reopen script (temporary artifact removed)
with `--capture`, repository Python and isolated temporary QSettings. The script
uses the built-in three-epoch/60-second sample and exits after inspection; omit the
flag to leave Protocol open. Source is the same base revision plus current uncommitted
work. Four lanes fit the normal viewport; fixed-height scrolling and trial navigation
are checked locally. The narrow capture also reveals existing recording-label clipping
at 720-pixel window width; the subsequent move to Dashboard with two columns resolves
this observed clipping, verified at 720 and 1175 pixels.

Native batch edit (review image removed),
reference composition (review image removed),
creation options (review image removed) and
narrow layout (review image removed) were captured and
inspected with the review script (temporary artifact removed).
Fixtures use temporary prepared assets and explicitly labeled sample Left/Right
assignments, without saving device configuration or sending hardware commands.
Inspection exited and the final sample GUI reopened (Visible: True). Earlier
group editor (review image removed) and
expanded sequence (review image removed)
captures are historical evidence for retained features. Native macOS review does not
establish Windows, full workload or managed acceptance; those remain in the
[rig worklist](rig-verification.md).

The convenience launcher `scripts/start_gui.py` selects the repository `.venv`,
starts the existing review entry from the repository root and forwards its exit code.
It defaults to labeled review mode; `--read-only` opens the disconnected frontend.
It does not start managed backends or hardware. On 2026-10-02, help, Ruff/format,
Windows-target mypy and both command modes/exit forwarding were checked; a native
launch from `/private/tmp` succeeded.

The PyQt6 Dashboard follows [G01 revision 41](../docs/architecture/gui.md#g01) and
[G02 revision 23](../docs/architecture/gui.md#g02). Compact read-only round Runtime
status indicators form a horizontal row inside System controls in the owner-reviewed layout;
System controls and subject/session fields occupy the left column.
The accepted shared Card style places titles in a gap in the top-left border,
using existing palette/radius tokens. Shared headers add 14 pixels of vertical
separation; console Clear buttons and their action rows are removed. Session config
places Subject ID and Experiment above Output directory, then uses spacing alone
to separate species, sex, age, size and condition; there is no subsection heading.
A small Qt paint override preserves QLabel titles/accessibility and existing layout
ownership. The visible rectangular title mask reported by the owner is corrected:
the rounded fill stays continuous and only the outline is clipped beneath the
transparent caption. The owner approved the Dashboard presentation on 2026-10-02. Dashboard, Devices and narrow
native captures were inspected on 2026-10-03; 76 GUI/client checks and static checks
pass for the current frontend.
Runtime HUD fits its rendered text height; Activity log fills the remaining right
column. Shared FittedConsole measures Qt text blocks and recalculates on text/width
changes, while existing log/card stretch owns extra window height.
Setup spans the full row above equal-width Start/Stop buttons. Subject age is labeled
Age (dph), and experiment phase appears only in the HUD. The HUD also retains distinct
recording/metadata evidence. Camera experiment enablement belongs to Devices; other participation/use/save editing
now belongs to the local Protocol draft. Managed adoption remains pending. Prior banner/footer,
trial/progress removals remain in effect; preview selection now lives in a secondary window. Header connection/local-control
badges and their now-unused shared pill component/styles are removed; command gates
are preserved.

Setup requests preparation in Configuration and New session in Ended, returning to
Configuration after controller-owned cleanup before fresh Setup/Start. Stop requests
Cancel Setup during SettingUp/Ready. During a session it opens a window-modal chooser
with Stop now (E06 Abort now), Stop after trial and Cancel. Dismissal/Cancel sends no
intent; Cancel is the default. The chooser updates current phase/control availability,
closes when no stop action remains available and selection rechecks authority. It
opens asynchronously without blocking backend progress. The redundant Session menu
is removed. E05/E06's underlying commands and cleanup/finalization remain distinct.

ARCH-002 review reused the action/phase table and added a small focused dialog module
using shared component/theme helpers, with no new dependency or runtime back-reference.
The previous standalone status card and phase pill were removed under ARCH-002; the
combined readiness grouping is owner-reviewed. A focused PreviewDialog uses
shared styling and immutable visibility records, with no image processing or new
dependency. The selector is opened at the right of the compact page header. Shared layout helpers
position its native frame with a 12-pixel right-hand gap and equal top edges, clamping
to the main screen when necessary on first opening. Geometry is then retained across
reopen and frontend restarts via Qt save/restoreGeometry and local CephVR/Frontend
QSettings. Current rows determine width/height after restoration, replacing the
previous oversized remembered dimensions. The current selector follows CephVR1.0’s Source/Live table structure (reference
experiment_window.py around line 7948) as a lighter Source/Show grid: dark bordered
panel, aligned right-side checkboxes, blue column labels and shared focus/hover rules.
Accessible checkbox names retain each source label. Normal rows omit redundant state; pending
and unavailable reasons remain visible. Review labeling is in the title. No Hide all
or Close buttons, duplicate title or instruction/footer text remains. Invalid saved
data falls back to first-open snapping. This stores GUI
geometry only; no permanent docking or continuous movement coupling is added. Reference source is `position_aux_tool_window`
(line 6635) and `_move_tool_window_frame_to` (line 27984) in CephVR1.0. The selector
persists while hidden, scrolls a changing viewer inventory,
rechecks current availability/control and holds reported checkbox state while awaiting
an update. Local review visibility fixtures remain independent of session phase. Devices now has a presentation draft; Visual Stimulus and Tracking remain placeholders. `cephvr.gui.review --review` identifies local fixtures
in the window title; phase/observer inspection lives in View. Buttons/dialog selections
report intent without commands or fabricated execution; drafts are neither saved nor
submitted. Default presentation is disconnected/read-only. No `cephvr.gui.main` managed
entry was added; controller transport/leases, viewers, incidents/reconnect and managed
registration remain unfinished under E02/E03/E08.

The shared DirectoryField opens a nonblocking existing-folder picker, rechecks editing
availability on selection and preserves cancellation. PathEdit elides only painting
while unfocused: full draft text, copying and tooltip remain intact. LogConsole uses
word-wrapped bounded lines without forced token splitting, keeps the current retained entry during append/eviction and
follows only from the bottom. These helpers add no dependency or runtime ownership.

The preview header count is removed and its button toggles the selector. Sources are
Behavior cam, Tracking cam, additional configured camera roles, Tracking and Visual
stimulus. An explicit active flag gates both controls and request dispatch; inactive
names are dimmed and explain the restriction in a tooltip. Review camera enablement
updates these rows, and Protocol Tracking participation drives its preview gate; View fixtures remain available.
Tracking camera enablement remains independent of tracking-pipeline participation.

Devices orders Cameras, Microcontroller, Projectors, SpikeGLX. Cameras stacks its compact
inventory and Camera config at the left. Role, Internal clock / External controller trigger source, requested
Microcontroller pulse frequency and PFS path/Browse are the only camera configuration
controls. Detailed parameters are edited in PylonViewer; GUI parameter editing and
PFS export are removed for now. The shared asynchronous PathField serves both output
folders and PFS files. Cancellation preserves drafts, and switching cameras rejects
the open picker; late callbacks also check dialog identity and editing availability.
PFS selection now reads bounded FrameStart trigger hints without applying a preset. Missing, ambiguous or unsupported hints leave the dropdown unset. SDK import/readback integration under
A10 remains necessary before any future applied-settings claim.

Device subtabs fill the left column width and align with the HUD’s painted top border, with configuration cards
below. A single existing QTabBar moves between the retained panel layouts; the
shell no longer needs a device dropdown or resize handler. The title/Previews row
keeps one measured height. Tests verify that the right HUD stays aligned across
all seven surfaces, navigation survives resizing, and cards sit below the tabs.
Native wide/narrow captures confirm all four labels fit. ARCH-002 review removed
the rejected header trial's extra controls without adding dependencies or state.
Removed the selected-camera caption from Camera config and the draft footer.
Refresh is an accessible icon in a reserved table-header section. Shared header
corner radii and a transparent native header background fix protruding corner fills;
no similar defect was found in the inspected cards/fields/HUD/log views. Connect
switches to Disconnect and back for the selected review connection.
The proposed Test enabled action logs one explicitly untested request per enabled
camera, preserving selection and connection state; no hardware result is fabricated.
Tests cover disabled-camera exclusion, empty selection of enabled devices, phase
gates, real tab clicks, full-width tabs and their border alignment. Managed connection-only batch checks are now implemented through the controller and
camera worker; their physical rig acceptance remains pending.
The camera inventory is titled Available devices. A shared dim selection palette
separates selected rows from headers and applies to navigation/subtabs/text selection.
Shared 12-pixel horizontal cell/header padding is included in content-sized columns,
keeping Role text away from the table boundary.

Shared StatusColumn now supplies a fitted HUD and expanding log on Dashboard, every
device subtab and Visual Stimulus/Tracking placeholders, using the existing responsive
stacking rule. Camera HUD now uses the counts/selected-role/status/controller-trigger/
measured-acquisition layout described in the current appearance assessment above;
backend acquisition-rate readback remains outstanding.
Per-camera drafts, unique roles and active-source preview restrictions remain.
ARCH-002 review removed the obsolete parameter/Apply/export UI and reused existing
Qt layouts, fitted consoles and picker logic without dependencies or runtime references.

Connection/visibility remain labelled local review fixtures; Refresh/connect controls
send no SDK command. Actual Protocol participation, PFS application, controller-owned
configuration/validation, image windows, managed integration and Windows/rig acceptance
remain pending. The reference inventory/connect patterns come from CephVR1.0's
experiment_window.py lines 8065–8230 and 8440–8505; the initial broader parameter
form is superseded by the owner's PylonViewer workflow.
Microcontroller lists only discovered COM-number names through QtSerialPort; no
ports are opened, and this Mac correctly yields an empty COM list. One controller
selection owns camera triggers; Cameras has no port setting. Inputs now precedes
Outputs. Each signal has an enable checkbox/name/pin/Test row. Camera enablement
shares Cameras' participation state through stable-ID signals and immutable records;
disabled rows stay visible for re-enabling. Pins persist, disabled controls dim,
disabled signals do not cause pin conflicts, and disabling ends local tests. Fixed
I/O enablement is local draft configuration, not applied hardware state. No new
dependency or backend ownership was added under ARCH-002; no camera heading, frequency column
or level/edge selectors remain. Trial state is fixed active-high; Projector flip
is fixed rising-edge. Tests validate target identity, pin conflicts and gates and
use retained camera rates. Output tests are intended for SpikeGLX observation;
input testing observes edges. Test now toggles to a compact red Stop button with
unchanged geometry. Explicit local review state locks wiring/port edits, clears on
port or authority/phase loss, and cancels affected camera tests on draft changes.
Small Inputs/Outputs cards use shared compact density and a four-column row helper:
centered enable checkboxes, wrapped signal names, equal-width pin and action controls.
Name, pin and action columns now share width equally, widening pin/Test controls.
Both cards share column proportions and spacing; other cards keep their spacing.
The 2026-10-06 managed-camera binding adds controller-confirmed role assignment,
connection-only Test enabled, capture-versus-editing state, pending-command locks,
and external viewer attachment/close refresh. G01/A10 distinguish open/identify/close
from Start capture's frame/trigger evidence. Controller disconnect discards queued
operator intents. ARCH-002 moved camera projection/intents and request construction
out of the GUI entry point; MCU projection lives with its focused binding, and
serial-keyed discovery records moved out of the Cameras widget. The remaining
Cameras widget remains cohesive presentation/signal wiring; the Basler adapter's
small ownership property remains with its sole SDK owner. No new
dependency or direct GUI hardware ownership was added. Camera/pulse edits while
owned were blocked in this historical Oct6 scope; the current Oct9 owned-edit
implementation and review are described above. The final source trace found that accepted drafts previously never reached manual
acquisition commands and GUI PFS selection only changed provenance. Commands now
carry the accepted acquisition draft/revision, with ownership/staleness gates;
selected PFS files use actual SDK import/readback and explicit editing completion.
COM changes close the previous serial owner before connecting the new port. These
fixes are portable-test verified; native launcher/hardware acceptance remains in the
[rig guide](rig-verification.md#managed-device-gui).

Validation (2026-10-06): full portable GUI suite 206 passed/1 deselected;
subsequent focused managed/PFS/inventory checks 25 passed and MCU gates 5 passed.
Complete portable acquisition/controller suites: 390 passed/5 skipped; authenticated
controller RPC suite: 6 passed. Ruff lint/format (360 files), Windows-target mypy
(355 sources), regenerated Protobuf, boundary checks (555 modules, zero violations)
and whitespace pass. A temporary actual ManagedGui snapshot/layout probe passed
with discovery/transport replaced; both device pages were visually inspected, then
closed and temporary images removed. The native design-review window was reopened
on Cameras. No native managed launch, camera SDK frame, MCU waveform or rig pass is
claimed. Acquisition runtime remains composition/delegation; its new draft-adoption
logic lives in a focused owner instead of extending the runtime body.

The managed GUI now submits COM8 connection, saved Trial state/Projector flip
pins, and bounded Test/Stop requests through the controller to acquisition's
serial owner. Firmware protocol v2 implements the two diagnostics and their
device status is projected back to the panel. The owner-assigned D10/D11 camera
trigger pins and saved rates are projected to their matching camera rows. MCU
commands were extracted from the managed GUI entry into a focused binding under
ARCH-002. The 2026-10-06 increment adds pending/failure locks, confirmation-based
final-status queries and current camera-pin projection. GUI/portable owner checks
are recorded in LOG; the full managed Windows path and physical pins remain unverified.
The earlier Qt teardown failure is historical; the subsequent full offscreen GUI
suite passed. ARCH-002
review reuses one small row helper and removes the obsolete aggregate test path.
Projectors replaces its HUD with Displays layout, a tank/screen schematic and the
activity log. Rig geometry/Projection calibration/Projection synchronization sections
beneath inventory keep cards fitted to their content. Oct22 G01rev297 applies these
labels/order to the local Projectors tabs, with the calibration card
heading renamed too. Three focused offscreen navigation/width/draft-retention tests,
Ruff/format, Win32 mypy2 sources and boundary749/zero pass. ARCH-002 reuses the
existing tab/page tuple and derived rail; the913-line Projectors owner changes only
labels/order, without responsibility expansion. Native appearance was not checked. Independent pulse visibility/placement and
config-file pacing retain separate targets; off-pulse fields dim and preserve values.
Tank dimensions, left/front/bottom subject offsets, clip/tolerance fields and
per-face screen dimensions/distances/throw/scale/pixel offsets/reversal
remain local drafts. Geometry conversion creates four inward-facing parallel screens at explicit
subject distances, with side/Bottom front edges starting at the Front screen plane.
The rotatable diagram updates on edits; its legend identifies the drawn elements
without in-plot labels. CephVR IDs remain in the display table and layout.
CephVR1.0's Launch calibration ran a world-phase multicolor calibration grid through
its VR runtime, with a Disconnect action. The owner selected V01's managed Visual
Stimulus renderer for CephVR2.0. The saved rig JSON now feeds an offline GLB exporter;
the resulting asset is under ignored `cephvr-data/calibration`. The owner rejected
the timed 60-second trial program; calibration is to remain visible until manually
closed through a distinct V01 diagnostic state.
Screen calibration Launch prepares files automatically: it reads the current four
enabled face assignments and native monitor identities, computes bounded diagnostic
projection limits from the rig dimensions and writes a V15 display profile plus four
diagnostic geometric profiles into Protocol Assets. This is a local export, with no
output command. The review GUI still has no managed projector command, so Launch/Close
and physical presentation remain open under `projector-calibration-launch`.
The Screen calibration card now has a Launch/Close control interface for all four
outputs. It stays disabled without a managed controller connection and changes its
label only after confirmed output state; the local review frontend cannot project.
The diagnostic profile exporter now applies each face's scale, pixel offset and
inverse-axis drafts to its geometric mesh, so software centering values are prepared
per projector. Adjustments require a new preparation and later managed presentation;
they are not live projector output in the review GUI.
CephVR1.0 reference inspected: experiment_window.py 8990–9068 and 10274–10309.
No old measured rig values are adopted. Optical calibration/config transport remain
pending; parallel-plane placement follows the GUI geometry draft, not rig measurements.

The shared left configuration scroll area contains overflow while the right column
stays fixed; whole-page scroll wrappers are removed. Calibration uses a per-face
inverse/scale/offset grid based on CephVR1.0 lines 11535–11591. Physical sizes and
projector distances/throw belong to Rig geometry; removed footer text stays absent.
Pulse-off disables all synchronization fields, retaining their independent values.
VSync mode replaces Presentation; pacing selection is absent from the GUI. The
Visual Stimulus TOML declares a 60 Hz target and installation-owned pacing identity;
managed adoption/validation remains pending, so this is not a runtime rate guarantee.
Shared scrollbar tracks have zero width/height, retaining scrolling without any
width changes across tabs. Wheel delivery is regression-tested.
Screen dimensions presents all four faces with width/height/projector distance
and throw ratio. Left/Front/Bottom subject-to-screen distances sit in Rig geometry below the
Subject → Left wall / Front wall / Bottom fields. The right-screen distance is
now derived using equal side-screen offsets: width + left-screen distance − 2 ×
subject-to-left-wall distance. Diagram and geometry conversion recompute together;
invalid inputs clear the derived plane. JSON v2 omits the dependent value. Compatible
v1 imports retain their independent values; conflicting explicit right distances
reject the complete import without mutations. Regression tests cover an off-center
subject, subject edits, stale-value clearing, JSON omission and legacy migration. The diagram footer is removed. Regression coverage
confirms calibration JSON excludes display/projector inventory and preserves
existing assignment/participation state on load. Row-name header is blank and
column headings wrap within their fields. One Load JSON / Save as row replaces the per-screen file picker. The complete
versioned calibration document covers rig, limits and all four screen dimensions,
distances and corrections; bounded validation precedes any field changes, invalid
loads preserve state, QSaveFile commits atomically, and authority loss cancels pickers.
Files preserve null draft fields without claiming backend readiness. The owning
[format contract](../contracts/gui-calibration.md) distinguishes these GUI snapshots
from mesh/display profiles. An application wheel filter prevents focused/unfocused
combo/spin/slider mutation while routing gestures to containing scroll areas.
The filter is removed at application shutdown. After one native inspection exited
with status 138 following confirmed window closure, a native launch/close check
passed with exit 0; focused/unfocused wheel regression checks also pass. The geometry builder and diagram use one corner
helper, separating physical screens from tank walls; invalid distances are not guessed.
SpikeGLX has retained local stream/index/channel mappings for cameras, fixed I/O,
conditionally visible photodiode and added named inputs. Camera streams are restricted
to OneBox. Mapping Use checkboxes retain disabled values; custom signals have remove
buttons, while device-derived signals retain their source identities. Local mapping
opt-out cannot waive E12's required camera/pulse validation at managed preparation. Remote saved-channel discovery, duplicate/type validation, configuration
adoption and physical pulse acceptance remain pending under E12; no applied mapping
or remote connection is claimed.

2026-10-03 validation: 74 GUI/client tests cover fixed right-column positions under
left scroll, phase gates, calibration retention and mapping source toggles. Ruff,
format and Windows-target mypy (26 GUI modules) pass; boundary checker finds zero
violations across 479 modules, with pre-existing non-GUI cohesion warnings unchanged.
Native captures in `gui-dashboard-2026-10-01/derived-right-*` use explicitly labelled
projector fixtures and actual primary-only inventory. A layout attribute collision
in the new mapping editor initially hung resize checks; native stack sampling located
it, and distinct layout names plus the full narrow/wide suite verify the correction.
ARCH-002 review keeps calibration and input mapping in focused modules and standard
Qt scroll containers, without new dependencies or backend ownership changes.

Projectors uses a compact index/assignment/resolution/Use table and scaled desktop
Displays layout diagram. Per-display Use retains assignments/geometry, persists
through refresh and dims disabled diagram rectangles. GUI drafts remain local;
managed config binding is unfinished. Shared equal-row-height helper matches
Microcontroller pin/Test and path/Browse controls. Both exclude the current primary screen;
remaining screens receive local CephVR IDs from 1 in desktop-position order.
Primary-only setups show a clear empty state. Local tests cover primary removal,
ordering, retained assignment and empty refresh; physical layout comparison remains
rig work. Size and verbose properties are removed. Projector choices are
Unassigned/Front/Left/Right/Bottom. Display is content-sized and the remaining two
columns share spare width evenly; native inspection confirms Unassigned fits.
Selection/drafts survive refresh by identity. ARCH-002 review removed physical-size
collection and obsolete editable-combo caret handling; no new helper or dependency.
The former Windows path-index helper and manual-ID dialog were removed under ARCH-002;
neither yielded a reliable automatic Windows Settings number. The
[QueryDisplayConfig API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-querydisplayconfig)
documents path priority order, which differed on this rig. Actual surface matching
remains a [rig check](rig-verification.md). No dependency was added.
Native inspection corrected projector-name clipping and selected-row bottom overlap.
Camera Preview shares Dashboard source/visibility state, without an actual image window.
Full validation, persistence/apply and backend checks remain under A10/A11/V15/E12.

On macOS/Python 3.11, 54 widget-behavior checks plus four existing client state-view
checks passed. Ruff/format, Windows-target mypy (20 GUI files) and the 473-module boundary
check pass; existing non-GUI size warnings remain. Regressions cover preparation
cancellation, contextual New session, distinct stop selections, Cancel/Escape/window
close, repeated-click dialog identity and current phase/control gates. Updated layout
assertions check full-width Setup above equal Start/Stop, one horizontal readiness row
in System controls, four remaining cards, Age (dph) and no status pills; HUD/log sizing
and draft/readiness behavior are preserved. Configuration/Running/narrow renders and the Stop chooser
were inspected in earlier increments; the current native Dashboard at 1175×883,
460×350 preview selector and narrow Dashboard were inspected. New checks cover
modeless reuse, close/reopen persistence, checkbox visibility, pending requests, failures,
external-closure reports, inventory removal and authority loss. Header placement and
snapping tests cover right-side space, a negative-origin screen and screen-edge
clamping; native checks confirmed equal frame tops and a 12-pixel gap at 900-pixel
main-window width, plus the clamped case at 1175 pixels in the prior increment.
Current native capture confirms Browse placement and compact Windows-style path
rendering. New checks cover selection/cancellation/late-selection locking, unchanged
full path text, log retention/follow behavior and geometry across widget recreation
using a temporary preferences file. External image windows still do not exist in the
frontend; their backend geometry integration is not claimed.
Current Devices checks cover icons/tab order, per-camera draft retention and role
uniqueness, active-source preview restrictions, review-only actions and
disconnected/observer/running gates. New tests cover PFS selection/cancellation,
late-result camera identity, and fitted HUD/expanding log behavior on all seven
page/subtab surfaces. All four native subtabs were
inspected at 1175×883, plus a settled 720×800 layout without horizontal scrolling.
The inspection windows were closed with harness confirmation/exit 0, then the final
frontend reopened for owner review. [Dated evidence](gui-dashboard-2026-10-01/README.md)
preserves separate source hashes, checks, scripts and captures for each increment.
These are local presentation checks; owner review, Windows packaging and full
application/device/workload acceptance remain pending. The earlier Mac packaging
attempt failed at the existing AMD64 Windows DLL guard;
[rig acceptance](rig-verification.md) remains the Windows verification boundary.

### Dashboard embedded previews (2026-10-21)

Owner request: replace the external Previews workspace with an in-Dashboard layout.
Under [G01](../docs/architecture/gui.md#g01)/[G02](../docs/architecture/gui.md#g02)
`Dashboard` now stacks the session form and a `PreviewWorkspace` widget; Start
(phases Starting–Finalizing) shows the workspace and moves the Dashboard's own
System controls card into its top row, and the form returns afterwards. The
HUD recording lamp (REC/closing/fault text), Previews button, workspace geometry preference, minimize/restore handling and
dialog-only CRT overlay were removed; previews are unavailable before Start.
Placement now always measures against the main window (the Cameras path). In `--review`, Setup/Start/Stop walk a simulated session (no command sent); Start loads the sample trial program when the draft is blank and shows the Advanced previews dials for that run without saving the preference. This is
source and offscreen-test evidence only; native Windows viewer follow remains pending
in [rig-verification](rig-verification.md).

### Amber phosphor style (2026-10-21)

Oct22 G02rev119: inner card/subsection and projector headings use `| NAME |`.
Existing display-only formatters are reused (ARCH-002); other styles and stored
titles remain unchanged. Two focused appearance/projector checks, Ruff/format,
Win32 mypy2 sources and749-module boundaries pass. Native appearance unverified.

Oct22 owner screenshot follow-up ([G02](../docs/architecture/gui.md#g02) rev115):
slightly brighter surfaces, amber labels/frames/tabs and values, with softer scanlines.
Projector titles previously used source trace colors; all now use coral on restyle
and rebuild. Focused offscreen appearance/preview selection passes6 tests, separate
preference selection8; touched-file Ruff/format, Win32 mypy3 sources and boundary
check749 modules/zero violations pass. Initial sandbox temp/font-order failures
clear with a writable basetemp and the complete focused selection. Existing theme
owner remains cohesive for this palette-only amendment under ARCH-002. Native
brightness/title appearance awaits owner review after GUI reload.

Owner request: a third Style option modelled on owner-supplied retro HUD references,
iterated through owner-reviewed offscreen previews. Under
[G02](../docs/architecture/gui.md#g02) rev111, `PHOSPHOR_COLORS` is a Retro-family
palette selected by a `retroPalette` widget property beside `retroConsole`, so
concurrent windows keep their own palette. Phosphor-only behaviour: recessed cards
with dim outlines and corner brackets, open HUD/log frames (`openFrame`), `< TITLE >`
captions and `| NAME |` subsections (display-only; stored text unchanged),
hidden page heading, centred bracketed navigation, filled orange/red buttons,
underlined fields, inset checkboxes, log column titles (`ColumnHeader`) and
display-only hanging log wraps (`log_wrap.py`; copy returns the stored row). CRT
scanline alpha is 60 for Phosphor and unchanged for Retro.

Evidence: focused appearance/log/CRT/button tests pass apart from the known
native-mouse flake, which passes alone. Win32 mypy (193 files), ruff and format pass.
Offscreen renders were inspected. The earlier full GUI run (before the last button,
wrap and scanline edits) was 891 passed, 1 failed:
`test_managed_total_time_tracks_trials_gaps_and_stops` expects a 2-line preview HUD
but gets 4 lines. That HUD is part of the concurrent uncommitted embedded-previews
change; this style work does not touch it, and it is not attributed here.
Limitations: native look was seen only in owner screenshots of earlier revisions.
Inset checkboxes rely on Qt `background-clip`; stripe visibility depends on the CRT
toggle; wrap is phosphor-only.

### Dashboard Monitor view (2026-10-22)

G02rev122 applies compact main-sidebar navigation to Devices too. Cameras,
Microcontroller, Projectors and SpikeGLX appear beneath Devices only on that page;
Projector subtabs stay below Displays. Removed the redundant rail host, mode flag,
resize handler and1000px fallback. Both page groups reuse one shell visibility rule
and their existing tab state (ARCH-002); sidebar width214px fits Microcontroller.
Seven focused navigation/layout/theme tests pass, plus four rerun after the width
adjustment; Ruff/format and Win32 mypy4 sources pass. Final offscreen Amber
[Projectors render](runtime-evidence-2026-10-22/devices-navigation-space/projectors.png)
inspected, including the full Microcontroller label. Native GUI was not restarted.


G01rev299/G02rev121 removes Dashboard's second navigation column: its existing
Configure/Monitor rail is a compact96px-high group beneath the main Dashboard button,
visible only on that page. Content recovers the rail width and gap; narrow windows
keep these links in the main sidebar. Turning Side navigation off restores top tabs.
Existing selection/session/theme owners are reused; Dashboard's redundant resize
handler is removed (ARCH-002). Five focused navigation/layout/theme tests, Ruff,
Win32 mypy2 sources and boundary checks pass. The offscreen
[Monitor render](runtime-evidence-2026-10-22/dashboard-navigation-space/monitor.png)
was inspected; native runtime was not restarted.


Approved navigation icons are applied under [G02](../docs/architecture/gui.md#g02)
rev120 to all thirteen page/view/device/projector destinations. Tracking reuses the
CephVR1 six-arrow design, synchronization uses nested pulse squares, and Projectors
retains its existing icon. Existing SVG rendering and appearance owners handle
selected/inactive colors and theme/view transitions without new dependencies
(ARCH-002). Main sidebar width is190px to fit icons and complete bracketed labels.
Six focused offscreen navigation/theme/layout tests, changed-file Ruff/format and
Win32 mypy pass. Final sample [Dashboard](runtime-evidence-2026-10-22/navigation-icons/dashboard.png)
and [Projectors](runtime-evidence-2026-10-22/navigation-icons/projectors.png) renders
are retained with [context](runtime-evidence-2026-10-22/navigation-icons/context.txt).
No managed GUI restart or native icon acceptance was performed.


Side navigation defaults on under G01rev298/G02rev118, retaining explicit saved
preferences in the existing key. The shared rail style now presents Dashboard
Configure/Monitor and Devices; Projectors subtabs remain below Displays. This earlier revision retained the1000px top-tab fallback; rev122 supersedes that
placement with compact main-sidebar links. Dashboard mirrors manual/session changes.
ARCH-002 reuses DeviceRail with optional icons and the existing tab state; no new
navigation state store/dependency. Nine focused offscreen navigation/layout checks
pass, plus Ruff/format, Win32 mypy4 sources and749-module boundaries. The prior HUD
alignment assertion expected a Dashboard top-tab offset; it now checks both rail
and top-tab modes. Inspected1920x1000 offscreen
[Dashboard](runtime-evidence-2026-10-22/default-side-navigation/dashboard.png) and
[Projectors](runtime-evidence-2026-10-22/default-side-navigation/projectors.png)
confirm placement. Native runtime was not restarted or validated.

Shared headings (G02rev117): all StatusColumn owners and Monitor use HUD and
LOG console, without camera/device/tracking prefixes; Retro retains uppercase
caption decoration. Removed the unused custom-title parameter under ARCH-002,
reusing existing owners without dependencies. Three offscreen shared-heading,
layout and palette-switch checks pass; Ruff/format, Win32 mypy5 sources and
749-module boundaries pass. Native appearance not checked.

Single-row projector follow-up (G01rev296): existing grid sizing now gives a single
projector row equal vertical margins, including its headings, and clears them for
multiple rows. Focused owner reuse under ARCH-002 adds no state/dependency. All85
preview-timeline tests pass, with wide/narrow reflow and Standard/Amber coverage;
Ruff/format, Win32 mypy and749-module boundaries pass. Geometry-only offscreen
render confirms equal119px margins for a242px row in480px height. Native acceptance
remains outstanding in the existing rig checklist.

Font/controls follow-up: shared font metrics and sidebar/card-title overrides are
one pixel larger in all styles. Existing Card and toggle ownership are reused under
ARCH-002; no dependency or state added, and the579-line theme only changes values.
Fourteen focused offscreen appearance/workspace tests pass, including all three
styles, viewer/advanced toggle behavior and section geometry; Ruff/format, Win32
mypy2 sources and749-module boundary check pass. A wider preview/layout selection
stalled after29 progress dots and was interrupted; no full-suite pass or cause is
claimed. Initial new Amber parameter exposed an old square-bracket-only test
expectation; it now checks Amber's accepted angle brackets. An inspected
[offscreen sample render](runtime-evidence-2026-10-22/gui-font-preview-controls/amber-monitor.png)
shows both selector rows below Timeline. Native runtime was not restarted; native
font sizing/viewer placement remains in the existing rig checklist.

Owner request under [G01](../docs/architecture/gui.md#g01) rev296 /
[G02](../docs/architecture/gui.md#g02) rev116: `Dashboard.view_tabs` (Configure |
Monitor) switches only on run-phase entry/exit and otherwise follows the operator;
`layout_switched` refreshes the preview slot. `PreviewWorkspace` puts the timeline
alone in a Timeline card, followed by a full-width Preview controls card with
master toggles in its header and Video/Advanced selector rows;
stream checkboxes moved from frame headers into the Video row. `PreviewSlot` frames
only shown or pending streams (the previous reserve-all-active rule is removed), so
hiding a stream reflows the grid and re-places native viewers. That reflow is
unverified on Windows and is in the rig checklist. `StimulusTimeline` hides projector
sections by name (`hidden_projectors`), and the Projectors card replaces the bare
details widget. HUD/Log titles are shared. Evidence: preview-selected suite 187
passed; new view-switch and projector-toggle tests pass; Win32 mypy and ruff pass;
offscreen Amber phosphor render inspected. The full suite was not run (owner
instruction). Size advisory: `theme.py` is 579 lines (three styles' palettes and
sheets). It is cohesive, but splitting the phosphor sheet would need the palette
registry moved first; that is noted as a follow-up.

### Backend review fixes (2026-10-08)

Source review plus ruff/AST scans produced candidate findings; those confirmed in the code are fixed and tested, with evidence in [review-evidence-2026-10-08](review-evidence-2026-10-08/README.md). Fixed: supervisor shutdown replay, tracking-release gRPC retry, tolerant `source_registered`, concurrent worker cleanup, warnings for rejected participant Shutdown and persistent helper errors, launcher parser/reader resilience, client timeout messages and E02 Ctrl+C scope, shared policy digest ([E14](../docs/architecture/system-contracts.md#e14) revision 207), loopback/`contract_version` checks. Still open: `shutdown-health-checks` (controller-loss and fencing gaps), the TODO "For review" refactors, and coverage measurement. Local results do not close E15 rig checks.

## Cohesion and test organization

Reviewed size exceptions under ARCH-002: controller `assembly.py` (519 lines,
flat component wiring; `runtime.py` is now 422 lines),
supervisor `shutdown.py` (505 lines, retained intent/deadlines and ordered cleanup,
delivery and operation outcomes), shared `incidents.py` (topology/proof
checks) and native `jobs.py`/`security.py` (Windows ABI and exact handle ownership).
These boundaries do not permit unrelated additions; extract a separable responsibility
before extending them. Acquisition exceptions belong in its report.

Supervisor native exit ordering and final absence inspection now live in the focused
`process_exit.py`; it receives the registry, native interface and shutdown state,
and returns evidence without changing coordinator outcomes. The small
`worker_context.py` owns the work-scope comparison shared by registration, discovery and
transport. No
whole-runtime dependency or duplicate authoritative state was added. Registry,
worker-transport and shutdown regressions extend their existing behavior modules;
no additional test module was needed.

Controller `lifecycle/interruption.py` is now 444 lines (previously 525); finalization
outcomes and cleanup remain there, while the 360-line `metadata/coordination.py` owns
writer closure. Removing the lifecycle owner's direct metadata-state dependency
keeps one authoritative state owner. Camera retirement shares the existing device
state and adds no wrapper module. Regressions extend the existing metadata, safety,
camera-evidence and lifecycle behavior modules; admission tests use the real
retention component instead of a stale method-only stub.

Tests are grouped by behavior. The 2026-09-30 consolidation reduced 105 test modules
to 67 (acquisition 40→22, controller 37→23, supervisor 10→7, shared 7→7,
platform 7→5, launcher 2→1, client 2→2). All 24 fix-named modules were absorbed or
renamed by responsibility; test-to-test imports were removed. Controller's now
533-line lifecycle-command module retains its common interruption/finalization
fixture, including the regression that failed trial metadata cannot skip sealing;
acquisition's 591-line worker-foundations module was not extended.

The 2026-10-01 cross-backend ARCH-002 sweep rechecked controller and supervisor
package boundaries alongside acquisition, Visual Stimulus and Tracking. It found no
additional safe controller/supervisor extraction; retained size exceptions and
unresolved observations remain as recorded above.

## Verification evidence

Earlier rows retain historical results and were not rerun during report consolidation;
their uncommitted snapshots had no recorded source revision. The supervisor
simplification rows describe newly executed checks, based on HEAD
`7ae3767cea92bf7af94153d417e40df997e1fd05` plus pre-existing and new working-tree changes.
[Raw evidence](runtime-evidence-2026-09-30/supervisor-simplification.txt) retains commands,
results, scope and SHA256 hashes of supervisor source/tests; HEAD alone does not
identify that snapshot. Concurrent Visual Stimulus backend renaming was preserved;
the evidence includes revalidation and a refreshed source/test manifest after that
rename. Counts describe each run's snapshot. The second supervisor pass has its own
[raw evidence](runtime-evidence-2026-09-30/supervisor-simplification-pass2.txt)
(same HEAD, later working tree, new source/test hashes).

The controller simplification uses the same HEAD plus the dirty working tree.
[Controller raw evidence](runtime-evidence-2026-09-30/controller-simplification.txt)
records increment results, final commands, an unchanged source/test SHA256 manifest,
and the separate acquisition-preview fixture failure encountered by broader checks.
That fixture failure was subsequently corrected and verified in the
[acquisition simplification pass](acquisition.md#verification-record).

| Date / scope | Command or method | Recorded result and limits |
| --- | --- | --- |
| 2026-09-30, portable run before backend audit | `python -m pytest tests -q`, asyncio auto | Controller/supervisor/shared/platform/launcher/client passed except seven acquisition-loader-blocked tests; native Windows skipped. The later loader correction was not a rerun pass. |
| Same portable snapshot | `ruff check src tests tools`; `ruff format --check src tests tools`; `mypy --platform win32`; `python tools/check_backend_boundaries.py` | Passed; 323 source files typed; zero boundary violations. |
| 2026-09-30, backend source audit | Ruff lint/format, Windows-target mypy, boundary checker, Python compilation and TOML parsing | Passed: 439 formatted files; 325 source/regression modules typed; 269 backend modules, zero violations; 15 TOMLs parsed. |
| Same audit | `pip check`; wheel/sdist build with `--no-isolation`; pytest collection | Passed dependency consistency/build; 483 cases collected including 22 encoding/GPU regressions. No test bodies run. Driver/SDK compatibility untested. |
| 2026-09-30, test consolidation | Collection and AST comparison against pre-consolidation snapshot | All 483 collected cases, names, markers and fixture dependencies retained; 451 test functions, 678 top-level definitions and 3,218 module-binding comparisons preserved subject to reviewed helper merges/renames. Native/ring platform skips unchanged. |
| Same consolidation | Ruff, compile, Windows-target mypy, boundary checker | Passed: 74 test/support modules compiled; 323 runtime and 346 combined runtime/acquisition-test modules typed; 269 backend modules, zero violations. No test bodies run. |
| 2026-09-30, supervisor simplification increments | `.venv/bin/python -m pytest tests/supervisor -q -m 'not windows and not rig'` | Passed: registry increment 64, worker increment 96, shutdown increment 106 cases (audit baseline 55). Covers rejection/replay, work scope, stale/capacity-bound channels, independent delivery, native-boundary ordering/deadlines and distinct cleanup/exit outcomes. |
| Same refactor, integration | `pytest tests/supervisor tests/launcher tests/shared tests/client tests/controller/test_shutdown_handoff.py -q -m 'not windows and not rig'` | Initially 177 passed and two client RPC fixtures were blocked by sandbox loopback binding; network-permitted retry passed both. After concurrent renaming, reran the 177 non-listener cases and the two authenticated RPC cases separately: all passed. Combined coverage 179 passing cases; no native Windows/rig run. |
| Same refactor, static/source review | Scoped Ruff lint/format and `mypy --platform win32 src/cephvr/supervisor`; `python tools/check_backend_boundaries.py`; AST comparison of extracted native exit body | Passed: 30 source/test files formatted, 21 supervisor modules typed, 390 backend modules with zero boundary violations. Native exit control flow matches the pre-refactor working copy after dependency/backend-role renaming, excluding result packaging. Shutdown's remaining size warning is assessed above. |
| 2026-09-30, supervisor simplification second pass | `pytest tests/supervisor tests/visual_stimulus/test_transport.py -q -m 'not windows and not rig'` after each of four increments; scoped Ruff lint/format, `mypy --platform win32 src/cephvr/supervisor`, boundary checker, `git diff --check` | 110 passed throughout (106 supervisor plus 4 transport); 20 supervisor modules typed; 450 backend modules, zero violations; supervisor source 5,208 to 5,013 lines. Only `shutdown.py` (505) still exceeds the size warning. No test assertion changed; edits limited to renamed methods/modules and fake-port no-ops. |
| Same pass, integration | `pytest tests/supervisor tests/launcher tests/shared tests/client tests/controller/test_shutdown_handoff.py tests/tracking/test_runtime.py tests/visual_stimulus/test_transport.py -q -m 'not windows and not rig'` | 188 passed (three repeats). One earlier run had a tracking heartbeat-catalogue test fail while another session was editing the Tracking runtime; it reproduced against the pre-refactor supervisor and passes with the current tree (see raw evidence). No native Windows/rig run; E15 checks remain open. |
| 2026-10-14/15, controller/supervisor audit fixes | `pytest tests/supervisor tests/controller tests/shared tests/client tests/launcher tests/platform -q -m "not windows and not rig"` after each increment and at the end; `ruff check`/`ruff format --check` on supervisor, controller and their tests; `mypy --platform win32 src/cephvr/supervisor src/cephvr/controller`; `tools/check_backend_boundaries.py`; `git diff --check` | Final (after the owner-approved follow-ups) 840 passed, 1 skipped, 4 deselected; 129 source files typed; 690 backend modules, zero violations; ruff and whitespace clean. New regression tests were each confirmed to fail without their fix (admission, setup cancel, registry, calibration Close, camera release, startup recovery). Two existing tests were corrected: a lifecycle fixture now models an activated session's registered context, and a client RPC test no longer asserts the failed cancel that pinned the Setup-cancel defect. Local only; no Windows-native/rig run. |
| 2026-10-01, controller simplification second pass | `pytest tests/controller tests/client tests/shared tests/launcher tests/supervisor tests/visual_stimulus/test_controller_communication.py -q -m 'not windows and not rig'` after each of seven increments; scoped Ruff lint/format, `mypy --platform win32 src/cephvr/controller`, boundary checker, `git diff --check`; whole repository `pytest tests -q -m 'not windows and not rig'` at the end | 379 passed throughout (200 controller cases collected before and after); whole repository 736 passed, 6 skipped, 2 deselected; 74 controller modules typed; 453 backend modules, zero violations. Controller source 16,494 to 16,297 lines (72 to 74 modules: `receipts.py`, `setup_resolution.py`), tests 7,069 to 6,991. No assertion changed; edits limited to removed dead fixtures/kwargs and shared fixture imports. `assembly.py` (519) remains the only controller size advisory. No native Windows/rig run; E15 checks remain open. [Raw evidence](runtime-evidence-2026-10-01/controller-simplification-pass2.txt). |
| 2026-09-30, controller simplification increments | `.venv/bin/python -m pytest tests/controller -q -m 'not windows and not rig'` | Baseline 187 passed; lifecycle/metadata regressions 195 passed; camera retirement regressions 199 passed. Final integration adds one finalization regression, bringing controller coverage to 200 cases. |
| Same controller refactor, integration | `pytest tests/controller tests/supervisor tests/shared tests/launcher tests/client -q -m 'not windows and not rig' --ignore=tests/client/test_controller_rpc.py`; separate network-permitted RPC run | 374 passed, plus two authenticated controller RPC tests passed: 376 total. Original deadlines, independent interruption delivery, metadata closure ordering/failure and camera result retention are covered. Native Windows/rig acceptance remains pending. |
| Same refactor, broader acquisition checks | Added `test_manual_devices.py`, `test_manual_preview.py`, `test_cleanup_aggregation.py` to the non-listener integration run | 386 passed, one existing acquisition-preview test failed and reproduced in isolation. Its fixture leaves `WorkerPreview.started=False`, so the pause path skips it. Both that test and its acquisition implementation are unchanged from HEAD; no acquisition fix is included here. |
| Same controller refactor, static/source review | Scoped Ruff lint/format, `mypy --platform win32 src/cephvr/controller`, boundary checker, AST comparison against pre-refactor working copy | Passed: 97 source/test files formatted, 72 controller source modules typed, 390 backend modules with zero violations. Extracted metadata closure, interruption delivery and camera-retirement bodies preserve statement order after dependency/deadline-name normalization. This source evidence does not establish rig equivalence. |

The consolidation's initial test-only mypy invocation omitted source discovery;
rerunning with `src/cephvr tests/acquisition` resolved it without suppression.
Earlier modular review compared moved storage classes by AST and lifecycle branch,
lock and await ordering against a working-tree snapshot; review corrected stale
limits injection, shadowed activity handling, warning retention and shutdown text.
This establishes reviewed source preservation, not behavioral equivalence on the rig.

The 2026-09-23 declaration audit compiled control/acquisition Protobuf with isolated
`grpcio-tools 1.84.0` / `protobuf 7.36.2` under `/tmp`; TOML, register revisions and
local links passed. Commands and source revision were not retained. Clock and
controller-loss declaration findings are owned by [host clock](../contracts/host-clock.md)
and [controller health](../contracts/controller-health.md). That historical schema
check is neither current runtime validation nor a second unresolved audit worklist.

Follow [E15](../docs/architecture/system-contracts.md#e15) for lightweight local
implementation/communication tests and native/device/full-workload rig checks.
Execution instructions and retained-result requirements are in
[rig verification](rig-verification.md#execution-and-results).

## Post hoc alignment compatibility review

2026-10-14 source review (`posthoc-alignment-review`): supplied Desktop guide
`raw_trial_preprocessing_and_spikeglx_alignment.md` and sibling CephVR1 checkout
at `914ecbc` (matching the guide), particularly session_compiler/core/alignment.py,
datasets.py and compiler/record schema paths; compared with current dirty CephVR2
contracts and acquisition/tracking/Visual Stimulus writer source. No session was
compiled and no hardware or scientific timing acceptance was performed.

Under [SYS-004](../architecture.md#sys-004),
[E04](../docs/architecture/supervisor.md#e04),
[A07/A09](../docs/architecture/acquisition.md#a07),
[T19](../docs/architecture/tracking.md#t19) and
[V22/V28/E13](../docs/architecture/visual_stimulus.md#v22), current files carry
session/trial identities, camera-native provenance, source/video-slot joins,
tracking source lineage and per-output stimulus submission/marker evidence.
These support external alignment when the required streams were saved and hardware
correspondence is established; they do not supply measured OneBox times themselves.
CephVR1's CSV reader and ten-frame optical-tag assumptions cannot consume CephVR2's
JSONL records and six-frame marker every 60 submissions unchanged. A09 frame_id
counts received images, not hardware triggers; never use its gaps as pulse gaps.
Camera native counter meaning must be read from its descriptor. Review-video padding
must join to its original source, never become additional scientific observations.

Unresolved alignment limits: first-source/first-pulse assumptions can hide integral
frame offsets; periodic optical landmarks cannot identify arbitrary missing cycles;
one photodiode cannot prove other outputs' illumination times; saving Off removes
required detailed histories. Probe-to-OneBox shared-sync mapping remains external,
separate from discovering probe files or controlling SpikeGLX. The checked-in pulse
inventory is unset and paired scientific acceptance remains open in the existing
[rig checklist](rig-verification.md); this review does not infer live rig wiring.
Legacy thresholding uses global extrema and 100-sample closing: noise sensitivity
and pulse merging are risks, not observed corruption in a tested session.

Recommendations, not accepted changes: use version-specific readers feeding one
shared inspection/compiler alignment core; retain native edge sample indices,
recording/segment identities and explicit per-row timing/anchor quality; derive
analysis tables/events externally from canonical records instead of adding competing
runtime CSV logs. Reuse existing central schema/output index and resolved pulse
inventory; enrich missing sync-route/probe-segment provenance only where needed.
Consider separating compact scientific stimulus evidence from optional review-video
encoding to reduce load while retaining timing history; this requires an E13 policy
choice. Additional physical absolute anchors or per-output optical measurement
require their own accepted scope and rig validation, not merely new JSON fields.
Legacy code already uses memmap, block/halo edge extraction and virtual views;
profile disk/concurrency and avoid duplicate notebook processing before adding
parallelism or changing storage format. Offline analysis implementation stays deferred.

Owner clarification: assess missing raw evidence only; the owner will build the
CephVR2 compiler separately. Additional source findings: A07 ties camera frame logs
(including optional native counter/timestamp evidence) to save_video, whereas T14
allows Tracking saving independently. Tracking records retain host/source lineage,
but do not replace the full acquisition native-clock history when camera saving is
Off. E13 similarly couples detailed presentation evidence to review-video saving.
These are accepted configuration limitations, not a claim of corrupted files.
The earlier missing-Eye finding is resolved by E12 revision21's first-class Eye
inventory and active external-trigger Setup requirement; see the current alignment
readiness section above. Actual channel assignments and pulse proof remain rig-pending. Raw files also do not establish
an absolute first camera-trigger anchor, an absolute optical cycle identity, measured
exposure latency, or other-projector optical onsets. Their necessity depends on the
required timing claim; metadata alone cannot create missing physical observations.


Oct16 `preview-consumer-authenticated-handoff` completes the owner-approved
[E08](../docs/architecture/system-contracts.md#e08)/[A10](../docs/architecture/acquisition.md#a10)
amendment. A production-port in-process probe reproduced controller relays failing
consumer-only supervisor authentication. Supervisor now authenticates either the exact
current controller or the registered consumer before retaining unchanged terminal
FAILED/RELEASED proofs. Existing generation/token/loopback/duplicate-metadata and exact
report checks remain; ATTACHED rejects at supervisor. Controller forwards ATTACHED only
to acquisition and terminal proofs to both owners. Independent reporting, original
handoff timeout and cleanup obligations remain. This is not evidence of the historical
native preview fault's cause. Real loopback transport coverage exercises both accepted
routes, idempotence and invalid credentials/subjects/payloads; focused routing coverage
checks acquisition-only attachment even when supervisor is unavailable. No aggregate
closure is inferred; rig acceptance remains open.

Final Oct16 integrated development validation: backend/authenticated1860 passed,
five platform skips and five exclusions; Ruff passes,679 files formatted, Win32
mypy583 source files and boundaries702/zero violations. The supervisor service remains
focused on transport authentication/delegation; preview retention has its own bounded
owner. Existing cohesive-size advisories were reviewed without another abstraction or
dependency. Documentation checks find zero new broken local targets/anchors; three
pre-existing unavailable image references remain. Commands/raw outputs and source
snapshot are in the [evidence context](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
Local completion does not close Windows, hardware or full-workload E15 acceptance.
