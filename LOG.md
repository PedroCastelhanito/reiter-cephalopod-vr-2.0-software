# Development log

Dated entries, oldest first; append new entries at the bottom. Each entry states the
context or finding, what changed, and the verification with its limits; it names the
affected-backend tags and the TODO task ID when there is one. Detailed evidence lives
in the linked backend report, not here. Rules and tag vocabulary:
[AGENTS.md](AGENTS.md#task-and-change-tracking).

The log starts on 2026-09-30. On 2026-10-15 the entries written up to that point were
condensed once at the owner's request (outcomes, task IDs, decisions, evidence links
and verification results kept; narrative removed). Entries added by the GUI sessions
later that day are left as written. The earlier full text is in Git history (commit
`0d70295` and before); the one entry from after that commit was kept as written.
Do not condense entries again except on an owner request.

## 2026-09-30

### [repo] Establish task and change tracking

- Context: owner requested a shared task list and concise log for code work, report changes and findings.
- Changes: created root TODO/LOG, seeded TODO from unresolved runtime findings, linked the rig worklist; added agent maintenance rules, README navigation and the GOV-001 tracking convention.
- Verification: local links, task ID uniqueness, GOV-001 revision/register and whitespace checked. Documentation only; no runtime tests.

### [repo] Share agent guidance across ChatGPT/Codex and Claude

- `shared-model-guidance`: AGENTS.md made canonical for both model families; CLAUDE.md import added; Luna delegation preference scoped to ChatGPT/Codex, configured-model path for Claude. Architecture and TODO/LOG obligations preserved.
- Verification: links, import target, whitespace checked; import syntax confirmed against [Claude Code documentation](https://code.claude.com/docs/en/memory#import-additional-files). Documentation only; live Claude session loading not tested. Task complete.

### [repo] Align Codex guidance with OpenAI documentation

- `codex-documented-guidance`: AGENTS.md kept as plain Markdown; clarified scope/discovery; added repository map, scoped setup/validation commands and Code Review Rules per [OpenAI's guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md). Governance/tracking text preserved; CLAUDE.md still imports it.
- Verification: links/anchors, command paths, fences, whitespace checked; file is 18,233 bytes (below 32 KiB default). No runtime tests or fresh-session discovery test. Task complete.

### [supervisor] Second ARCH-002 simplification pass

- `supervisor-simplification-pass2`: four increments delegated to Sonnet coders, reviewed against a pre-refactor snapshot. Shared work-scope comparator and live-phase/role constants; registry/registration/health/recovery tidy-ups; one `WorkerControl` interface (`acquisition_shutdown.py` renamed `acquisition_worker.py`); `shutdown_owned` split (541 to 505 lines); `GrpcOutbound` extends worker transport (319 to 202). Source 5,208 to 5,013 lines, 21 to 20 modules (smaller than ~10% estimate). `startup.py`, `main.py`, `registry.confirm()` left alone.
- Verification: 110 supervisor/transport tests, Ruff, Windows-target mypy, boundary checker, whitespace passed per increment; 188-case integration passed. One tracking test failed once during unrelated Tracking edits, then passed. Evidence: [pass 2](reports/runtime-evidence-2026-09-30/supervisor-simplification-pass2.txt). Local only; no rig/Windows run. Two accepted observable differences in [the report](reports/runtime.md#current-scope-and-review). Nothing committed.

## 2026-10-01

### [tracking] Simplification baseline and ownership cleanup

- `tracking-simplification` under ARCH-002, T08/T09: no added dependency justified. Removed unused history/feedback fields and shared pose-thread geometry retirement; added borrowed-history and normal/failure thread-ownership regressions.
- Verification: baseline 28 passed (one rig case deselected); first increment 31 passed. Ruff/format, Windows-target mypy (59 files), boundaries (450 modules, zero violations) passed. Sandbox run hit six loopback-bind errors; authorized loopback run passed. E15 rig acceptance separate. Audit continues in [the tracking report](reports/tracking.md).

### [tracking] Complete movement simplification and regression audit

- `tracking-simplification`, T08/T09/T19, ARCH-002: shared discard/reset handling, value-only recording formatter, regression cases in existing modules. Native ownership, generations, deadlines, payloads and record-before-feedback ordering preserved; stale provider-status prose in the tracking contract index corrected. No package, algorithm, schema or policy change.
- Verification: 42 tracking tests passed (one rig case deselected); full local suite 736 passed, 6 skipped, 2 deselected; 48 tracking contract tests passed. Ruff/format, mypy (60 files), boundaries (451 modules, zero violations), whitespace passed. [Evidence](reports/tracking-evidence-2026-10-01/README.md). E15 native/scientific acceptance pending. Task complete; nothing committed.

### [controller] Second ARCH-002 simplification pass

- `controller-simplification-pass2`: four read-only audits fed a 13-item plan; seven increments by Sonnet coders, each reviewed against a snapshot (cleanup dispatch and AbortNow/Shutdown precondition re-traced). Removed unread wiring, static file-policy chain, `recovery_log_done` hook; deduplicated command wrappers, admission, reservation finish, trial-log, cleanup dispatch; `ControllerRuntime` 527 to 422 lines; extracted `setup_resolution.py` (`setup_execution.py` 423). Source 16,494 to 16,297 lines (~1%), tests 7,069 to 6,991. `assembly.py`, `startup/application.py`, `transport/ingress.py` and authority/evidence state machines left alone.
- Verification: 379 controller/consumer tests, Ruff, mypy, boundaries, whitespace per increment; whole suite 736 passed, 6 skipped, 2 deselected. [Evidence](reports/runtime-evidence-2026-10-01/controller-simplification-pass2.txt). Local only; no rig/Windows run. One accepted difference (bounded in-memory warnings) in [the report](reports/runtime.md#current-scope-and-review). Unverified observations in TODO `controller-audit-observations`. Nothing committed.

### [acquisition] [visual_stimulus] [tracking] [controller] [supervisor] Cross-backend ARCH-002 audit

- `backend-simplification-review`: reviewed layouts and cohesion across backends; no broad helper extraction or renaming met ARCH-002. Removed Visual Stimulus's write-only `NativeRecording.video_sync_factory` attribute (constructor input and `EncoderTrialOwner` transfer unchanged). Reports updated; [evidence](reports/visual-stimulus-evidence-2026-10-01/simplification.txt).
- Verification: Visual Stimulus 121 passed, 1 deselected (initial sandbox run had 5 loopback bind failures). Ruff, format (134 files), mypy (119 files), boundaries (453 modules, zero violations, 16 reviewed size warnings), `git diff --check` passed. Independent review pending; Windows-native/hardware/rig under E15.

### [visual_stimulus] Complete cross-backend ARCH-002 audit

- Sol and Astra independently reviewed final changes; no remaining actionable issues. Confirmed the attribute was unread; reviewers did not rerun pytest.
- Links/anchors and whitespace rechecked, passed. `backend-simplification-review` complete for this audit. Windows-native, GPU, hardware and full-workload checks deferred to rig verification under E15.

### [repo] Clarify repository convention reminders

- `agent-guidance-reminders`: owner-approved four reminders in AGENTS.md: project-layout link, checked-in format/lint/type/pytest settings, boundary-checker >500-line notices prompt cohesion review (no cap), concise comment/docstring guidance. CLAUDE.md unchanged (imports AGENTS.md).
- Astra and Sol approved with no actionable findings. Markdown links/anchors, whitespace and `git diff --check` passed. No runtime suite applicable. Task complete.

### [repo] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [shared] [launcher] Windows rig audit

- `windows-rig-audit`: baseline clean HEAD `826984255e0a8469afccbda2dcaf8c642b528b33`; fresh Python 3.11.15 environment; full suite and read-only device/GPU and bounded native/encoder/retention/identity probes in [dated evidence](reports/rig-audit-2026-10-01/README.md). No implementation/scientific settings changed.
- Results: full snapshot 727 passed, 18 failed, 6 skipped (751); focused native 8 passed, 1 privilege skip. Lint/format/boundaries, 48/40 contract tests, schemas, package build passed; installed-extra mypy failed (52 errors); Tracking schema default decoding failed. Open: ring binding, interpreter identity, reservation/recovery, bounded FFmpeg failures; terminal timestamp leak reproduced at component scope; capacity bypass claim corrected. Managed launcher invocation rejected by approval review (not executed). GUI/SpikeGLX and scientific/full-load acceptance open. Audit complete, repairs queued.

### [controller] [shared] [launcher] Authorized Windows repair preparation and terminal retention

- `windows-native-audit-repairs`: owner authorized audit items 1-4 and 6; encoder item 5 deferred. Luna routed Setup Ready/failure and successful Start through existing terminal completion via a focused dependency; failure code/progress and lock/publication order retained; regressions added; Sol reviewed. Native atomic shim next.
- Verification: 21 focused controller cases, Ruff/format, mypy (74 files), boundaries (453 modules, zero violations), whitespace passed. Real-interpreter proof preserves `.venv` prefix/imports, one OS/code PID and bootstrap transfer after explicit matching-base DLL-directory setup; the proof without it failed `_ctypes` loading (retained). Temporary-resource probes, not application or scientific acceptance.

### [shared] [acquisition] [repo] Native atomic binding and binary packaging

- `windows-native-audit-repairs`, ARCH-002/SYS-003: tiny documented MSVC intrinsic export (required Win32 atomic is not exported by kernel32 here); no Python fallback. Luna added x64 helper, strict binding, rig-install build path and cross-process shared-word coverage; packaging validates AMD64 PE images, emits Windows platform wheel, sdist keeps native source. Sol reviewed.
- Verification: MSVC/CMake build/install passed; native/ring checks 14 passed, 1 symlink privilege skip. Mypy, Ruff, format, boundaries, whitespace passed. Wheel: both native DLLs, `Root-Is-Purelib: false`, `cp311-cp311-win_amd64`. Raw evidence in dated audit directory (repair-prefixed). Does not establish full acquisition or scientific acceptance.

### [launcher] [supervisor] [controller] [acquisition] [visual_stimulus] [shared] Exact managed Python execution

- `windows-native-audit-repairs`, E08: Luna added provenance/freshness validation, a small versioned entry retaining matching-base DLL-directory handles, and consistent launch arguments/resolution at Windows boundaries; rig install prepares the artifact; missing/stale/mismatched files fail explicitly. Sol and Astra reviewed. No production diagnostic mode.
- Verification: prepare/verify and stale/mismatch regression passed; native suite 11 passed, 1 privilege skip, live child regression verifies OS/code/launched identity and bootstrap. Portable launch/registration/worker batch 153 passed, 1 rig case deselected; log/JUnit in dated bundle. Mypy/Ruff/boundaries/whitespace passed. Ran on Windows; no Linux, managed-application or scientific acceptance claimed.

### [controller] [shared] [supervisor] Windows reservation and recovery persistence

- `windows-native-audit-repairs`, E04 refinement (Windows directory-rename restriction), ARCH-002: Luna added canonical case-insensitive namespace guard in the existing reservation owner; POSIX semantics preserved; guard held through quarantine/cleanup and failure; failed quarantine preserves evidence and claims no cleanup. Native publication uses extended-length paths and short UUID temp names. E04/register and native contract amended together.
- Verification: corrected default-temp storage/recovery/native batch 42 passed, 2 symlink privilege skips, 1 open-live-log fixture deselected for item 6; initial run 27 passed with 3 failures (corrected). Alias exclusion, process-death release, marker ownership pass. Raw results with repair-d prefixes; scoped type/lint passed. Final full-suite/static checks pending portability increment.

### [repo] [controller] [supervisor] [acquisition] [tracking] [visual_stimulus] [shared] [launcher] Complete authorized Windows repairs

- `windows-native-audit-repairs` and `windows-validation-portability` complete for items 1-4 and 6; encoder item 5 remains owner-deferred. Luna wrote repairs; Sol/Astra reviewed under ARCH-002. Windows-aware fixtures, bounded outcome waits, UTF-8 schemas, tightened media typing and TIFF handling.
- Verification: whole suite with all Windows/rig markers 755 passed, 6 skipped, 761 collected. Ruff/format (627 files), installed-extra mypy (525 files), boundaries (453 modules, zero violations), 48/40 contract tests, 19/11 schemas, package build pass; wheel has both DLLs, cp311/win_amd64 non-pure tag. One fixed-sleep heartbeat failure fixed (raw retained). Scratch removed after containment checks; environment, prepared interpreter and DLLs kept. No commit. GUI/full application, devices, scientific/full-load acceptance open; no Linux runtime claimed.
- Provenance correction: original atomic compiler command/stdout/build-directory was not saved; reproduction recipe, DLL hashes, native tests, package evidence and source snapshot retained.

### [controller] [shared] [repo] One-time elevated symlink verification

- `windows-symlink-verification`: owner asked to remove exactly two POSIX mode tests (done; native ACL coverage remains) and run four skipped symlink scenarios elevated. Standard-token whole suite: 755 passed, 4 symlink skips (759 collected). First UAC dispatch (session 88294) was cancelled by user; approved retry (PID 23476) confirmed High-integrity token; four symlink nodes passed; elevated full suite 758 passed, 1 managed-Python child-proof failure.
- Diagnosis: child exit 0xC0000135 before Python startup; base Python needs `zlib.dll` and `VCRUNTIME140.dll`, loaded too early for `add_dll_directory`. Fix prepares only finite matching-base startup DLLs with provenance/pair hashes; no PATH fallback or OS change.
- Completion: task passes. Elevated focused proof 2 passed; full all-marker suite 759 passed, zero skips/failures; Medium-token default-temp proof 2 passed. Scoped Ruff/format/type/boundaries and package checks pass. No encoder or persistent OS change; scratch removed.

### [repo] Rig verification current-result pointer

- `reports/rig-verification.md` opening result now names the High-integrity dedicated-temp full run (759 passed, zero skipped/failed) as latest; 755/6 labelled historical. Runtime report and evidence already agreed.
- Cross-checked completion JSON, stdout/JUnit links, reports; `git diff --check` passed. No test execution or GUI/rig readiness claim added.

### [gui] Start GUI reference and workflow review

- `gui-implementation`: owner requested GUI stage using current GUI as reference. ARCH-001/register record the authorized stage; tab/layout recommendations unaccepted. Reviewed rules, reports, sibling GUI format guide, version selection and layout source; default compact and optional V4 layouts coexist, reference version needs clarification. Recommend navigation review, per-page keep/remove/add inventory, lifecycle permissions, wireframe before coding. No code or dependency change.
- Links/anchors and whitespace checked; no GUI execution or tests. Implementation and full application acceptance open.

### [gui] Explain existing layout variants

- `gui-implementation`: V4 emphasizes embedded previews, visible status/log panels and parameter editors embedded in maximized layouts or opened explicitly in smaller ones; keeps four-page navigation; source default remains `current`.
- Source/documentation inspection only; neither variant launched. Reference selection and proposed tab contents open.

### [gui] [acquisition] [visual_stimulus] [spikeglx] Review proposed Devices tab

- `gui-implementation`: owner proposed Devices replacing Cameras (camera, Arduino, SpikeGLX, projector). Reviewed A10/A11, V15/V19/V23, E12. Recommend one Devices page with device sections; stimulus programs and tracking algorithms keep their pages; connection evidence distinct from Setup readiness and physical verification.
- Limits: GUI does not take over SDK/serial/renderer/SpikeGLX ownership; diagnostics need mapping to supported backend commands (no generic connection test established). SpikeGLX integration and firmware keep stage/deferral. Navigation not yet accepted. Source/doc review only; no hardware action or code change.

### [gui] Accept navigation and review CephVR1.0 Dashboard

- `gui-implementation`: owner accepted Dashboard/Devices/Visual Stimulus/Tracking; recorded G01 and root register entry. Reviewed old Dashboard source and E05/E07/E10/Snapshot rules. Recommend subject/session details, ordered protocol summary, distinct participation/save choices, explicit lifecycle controls, selectable previews, concise readiness/output/incident status; hardware controls stay in Devices; preview/plot delivery needs backend support.
- Links/anchors and whitespace checked; source review only. Dashboard contents/layout remain proposals; SpikeGLX and rig deferrals intact.

### [gui] Create and verify Dashboard HTML mockup

- `gui-implementation`: HTML design preview matching the current GUI, files `cephvr-dashboard.html` and `cephvr-dashboard-preview.html` under `/Users/pedrocastelhanito/.codex/visualizations/2026/10/01/01a0f6a6-67df-7941-875b-a12acf196161/`; sample data illustrative, no device/network calls; only Dashboard interactive. Stale host-state echo found in QA corrected with revision checks. No runtime Python, contract, policy or dependency change.
- Verification: headless Chrome/Playwright layout checks at 1440/1024/736/390/320 px and state/edit-lock/control/protocol/preview interactions passed, zero page errors; Configuration and Running screenshots inspected. Sandbox initially blocked Chrome (escalated run succeeded). No native GUI, hardware or rig validation claimed. Layout/content acceptance open.

### [gui] [acquisition] [tracking] Review embedded versus external runtime previews

- `gui-implementation`: reviewed sibling preview source, A03/A10/T08, capture publisher, OpenCV dependency and Qt/OpenCV docs. Plausible costs recorded in the runtime report (per-snapshot Qt notifications, unused resolution scaling, monochrome conversion/full texture uploads, tracking overlay work); no blanket claim embedding caused the slowdown.
- Recommend starting with external backend-managed viewers with bounded latest-frame handoff; placement alone does not isolate CPU/GIL contention; headless OpenCV needs dependency review for HighGUI. Unaccepted; historical profiling unavailable; comparison stays under rig acceptance.
- Verification: 36 local links/anchors and `git diff --check` passed (link-checker false failure fixed). No GUI execution or timing measurement.

### [gui] Propose shared formatting rules from the current Dashboard

- `gui-implementation`: owner chose the current Dashboard as template (embedded stimulus plots excluded). Reviewed sibling stylesheet, ModernCard/field construction, ui_kit helpers, dialogs and GUI_format guide (V4 dimensions differ from compact helpers).
- Proposal: central tokens, small reusable widget/layout/formatting helpers; keep dark blue/black palette, card/button/field treatments, spacing, typography, pink monospace status panels; content-measured sizing, semantic states, responsive layouts. Rules remain in conversation pending review; no accepted architecture, GUI, backend or dependency change.
- Source/documentation review and `git diff --check` only.

### [gui] [repo] Implement and review the native Dashboard frontend

- `gui-implementation`: owner accepted formatting rules and authorized Dashboard implementation. Recorded G02/root register; added GUI extra and local `cephvr-dashboard` entry (managed `cephvr.gui.main` still absent); boundary checker extended; one GUI test module added. Local subject/session drafts, Use/Save, trial durations/repetitions/reorder, phase/observer presentation, progress/output evidence, pink panels, disabled external-viewer affordances; other pages are placeholders. Fixtures cannot launch backends or admit commands.
- Verification: offscreen GUI/client run 20 passed (16 GUI + 4 client); Ruff/format, GUI mypy, boundary check (463 modules, zero violations) pass; screenshots inspected (1440x940, 720x800, 1100 px). Evidence: `reports/gui-dashboard-2026-10-01/`. PyQt6 6.11.0 (Qt 6.11.2) installed after approved local install.
- Limits: native launch needed approved desktop run (PID 31267); native visual acceptance pending owner review. Package build fails on macOS at the existing AMD64 Windows DLL guard (preserved); Windows packaging, transport/leases, other pages, viewers, incidents/reconnect, rig acceptance open. No commit.

### [gui] Verify native display sizing and final review handoff

- `gui-implementation`: PID 31267 had been retired by an earlier delayed KeyboardInterrupt; reopened via owned Qt capture harness (1175x883 Cocoa window; harness PID 31838 retired, final window PID 31977). Compact shared column sizing now keeps status/logs beside controls; console height hints trimmed; local entry sizes/activates window.
- Verification: display dimensions added to the visible-status/log test; 21 passed (17 GUI/4 client), superseding 20. Static/boundary checks pass; captures regenerated, hashes/report/TODO/evidence updated; links, TOML, whitespace checked. Local UI checks only; owner visual review and Windows packaging pending.

### 2026-10-01 [gui] Simplify Dashboard for owner review

- `gui-implementation`: owner removed Design review banner, Trial plan, Session progress, External previews and footer text. G01 revision 2 recorded; Protocol navigation under consideration. Six cards in two responsive columns; unused trial-editor module, trial draft record and table-sizing helper removed (ARCH-002); phase/observer inspection moved to View menu.
- Verification: 21 GUI/client checks pass (17 + 4); Ruff/format, mypy (9 GUI files), boundaries (462 modules, zero violations) pass. Native captures 1344x883 and 1175x883 inspected; final window PID 32876 left open. Evidence/guide/report/TODO updated. Windows packaging, managed integration, rig acceptance pending.

### 2026-10-01 [gui] Align Dashboard columns and share expanding HUD rule

- `gui-implementation`: owner removed participation/use editing (future Protocol ownership), put Runtime status in the left column and wanted HUD/console filling height. G01 revision 3, G02 revision 2 recorded. Unused participation widget removed; shared Card growth, Console expansion and full-height columns implement the rule; Protocol page deferred.
- Verification: 21 GUI/client checks pass, including five-card contents and growth at 883/1100 px. Ruff/format, mypy (9 files), boundaries (462 modules, zero violations) pass. Native 1175x883 capture inspected; harness PID 33257 closed, exit 0; no window left open. Windows packaging, managed integration, rig acceptance pending.

### 2026-10-01 [gui] Reopen reviewed Dashboard for owner

- `gui-implementation`: reopened the unchanged, verified Dashboard with `.venv/bin/python -m cephvr.gui.review --review` and left it running; TODO/development workflow updated. No frontend code, backend operation or new test run.

### 2026-10-01 [gui] Simplify readiness and System controls

- `gui-implementation`: G01 revision 4. Independent read-only round readiness indicators (shared component, tooltip/accessible detail) sit above controls; main buttons Setup/Start/Stop (Stop emits Stop-after-trial; Cancel Setup, Abort now, New session in Session menu with identical gates). E06 Stop/Abort kept distinct; no new command states.
- Verification: 23 GUI/client checks pass (19 + 4); Ruff/format, mypy (9 files), boundaries (462 modules, zero violations), links, whitespace pass. One stale assertion and mixed action/button typing corrected. Native capture 1175x883 inspected; PIDs 33489 retired, 33786 closed; GUI reopened and left running for review. Windows managed/packaging/rig pending.

### 2026-10-01 [gui] Add contextual Setup and Stop chooser

- `gui-implementation`: G01 revision 5 within E05/E06: Setup requests preparation in Configuration or New session in Ended; no automatic Setup/Start after cleanup. Stop requests Cancel Setup in SettingUp/Ready; session Stop opens an asynchronous window-modal chooser (Stop now maps to Abort now; Stop after trial separate; Cancel/Escape/dismissal sends no intent; authority rechecked). Session menu removed; small GUI dialog extracted, no dependency or backend command.
- Verification: 31 GUI/client tests pass (27 + 4); Ruff/format, mypy (10 files), boundaries (463 modules, zero violations), links, whitespace pass. Native captures of Dashboard (1175x883) and chooser (440x158) inspected; PID 34320 closed; GUI reopened. Windows managed, packaging, rig pending.

### 2026-10-01 [gui] Match Setup layout and simplify status grouping

- `gui-implementation`: G01 revision 6. Setup spans both lower button columns; Age (dph) renamed; controls phase pill removed (phase only in HUD). Review candidate: one horizontal readiness row inside System controls, leaving four cards (obsolete builder removed). Recommended compact Show/Hide preview controls for external viewers; not accepted.
- Verification: 31 GUI/client checks pass (27 + 4); Ruff/format, mypy (10 files), boundaries (463 modules, zero violations), links, whitespace pass. Native Dashboard 1175x883 inspected (PID 35549 closed); GUI reopened. Combined grouping, preview design and Windows/managed/rig acceptance pending.

### 2026-10-01 [gui] Remove header badges and sketch Dashboard alternatives

- `gui-implementation`: G01 revision 7. Header badges and unused StatusPill/style removed (authority gates unchanged). Three interactive HTML sketches (preview row, preview card, preview card with HUD/log hierarchy) made in the task visualization directory; recommend separate visibility controls and backend-reported viewer state; native preview integration unfinished.
- Verification: 31 GUI/client checks, Ruff/format, mypy (10 files), boundaries (463 modules, zero violations) pass. Native capture 1175x883 inspected (PID 36217 closed), GUI reopened; sketches checked in Chrome at 320/390/736/1024/1100 px with no page errors. Local UI checks; no preview performance, Windows or rig acceptance claimed.

### 2026-10-01 [gui] Implement modeless preview selector and review reference ideas

- `gui-implementation`: G01 revision 8. Previews button, one reusable modeless selector with per-source checkboxes, Hide all, unavailable reasons, pending states; closing leaves visibility unchanged; local fixtures create no viewers or backend commands. Transport/admission/completion integration unfinished.
- Reference review (CephVR1.0 experiment_window.py at HEAD 38f728291ed551a332392dc2c7b6897e8428b060): output-folder selection, compact paths, console scroll preservation, contextual help, viewer geometry retention; recorded as proposals.
- Verification: 34 GUI/client checks pass (30 + 4); Ruff/format, mypy (11 files), boundaries (464 modules, zero violations) pass. Native Dashboard 1175x883 and selector 460x350 inspected; PID 36501 retired, 37062 closed; GUI reopened. Windows managed, packaging, viewers, full-workload pending.

### 2026-10-01 [gui] Move preview access and snap selector beside Dashboard

- `gui-implementation`: G01 revision 9. Previews button/count moved to the Dashboard header (hidden on other pages); shared layout helpers and a 12-pixel theme token snap the selector top-aligned beside the window within screen limits; Qt geometry reused, no docking framework.
- Verification: 37 GUI/client tests pass; Ruff/format, mypy (11 files), boundaries (464 modules, zero violations) pass; optional Qt window return guarded after mypy finding. Native frame checks at 1175 and 900 px confirmed alignment, clamping, 12-pixel gap. Links/whitespace pass; GUI reopened. Windows/rig pending.

### 2026-10-01 [gui] Add folder/path conveniences, log retention and geometry memory

- `gui-implementation`: G01 revision 10 (supersedes resnap-on-every-open). Asynchronous existing-folder picker (cancel/late-selection gates keep drafts); PathEdit elides only unfocused painting; LogConsole follows only from the bottom with the existing bounded buffer; selector geometry persisted via injected QSettings (CephVR/Frontend; tests use temporary INI). External viewer geometry remains integration work.
- Verification: 41 GUI/client checks pass (37 + 4); Ruff/format, mypy (12 files), boundaries (465 modules, zero violations) pass; nullable `appendPlainText` override fixed. Native Dashboard 1175x883 inspected (PID 37862 closed); links/whitespace pass; GUI reopened. Viewer integration, managed transport, Windows/rig pending.

### 2026-10-01 [gui] Compact the preview selector

- `gui-implementation`: G01 revision 11. Selector shows checkbox rows only (pending/error/unavailable reasons stay); Hide all, duplicate heading/instructions/footer removed; size fits content within screen limits, superseding remembered dimensions; window controls/Escape dismiss without visibility requests.
- Verification: 41 GUI/client tests, Ruff/format, mypy (12 files), boundaries (465 modules, zero violations) pass; `QWidget.scroll` name collision fixed; existing tests updated, no new module. Native selector inspected; links/whitespace pass; GUI reopened. Backend viewers and Windows/rig pending.

### 2026-10-01 [gui] Refine selector with reference source-table styling

- `gui-implementation`: G01 revision 12. Source/Show grid (left labels, right checkboxes, dark bordered panel, blue column labels, shared hover/focus); accessible names preserved; reference at experiment_window.py lines 7948-8051; QGridLayout, no table framework.
- Verification: 41 GUI/client tests pass; Ruff/format, mypy (12 files), boundaries (465 modules, zero violations) pass. Native selector inspected; evidence/report/TODO updated; links/whitespace pass; GUI reopened. Local presentation evidence; viewer and Windows/rig work pending.

### 2026-10-01 [gui] Fit HUD to text and expand the Activity log

- `gui-implementation`: G02 revision 3 supersedes equal expanding HUD/log cards. Small FittedConsole subclass measures rendered text blocks; HUD does not expand and all remaining vertical stretch goes to Activity log; wrapping and page scrolling unchanged.
- Verification: 41 GUI/client checks pass after updating the old equal-height expectation; layout test covers stable HUD height, all growth to the log, no overflow. Ruff/format, mypy (12 files), boundaries (465 modules, zero violations) pass. Native 1175x883 capture inspected; links/whitespace pass; GUI reopened. Windows/rig pending.

### 2026-10-01 [gui] Add Devices first draft and preview toggle

- `gui-implementation`: G01 revision 13. Header open count removed; selector toggled without changing viewer state. Devices subtabs Cameras, Arduino, SpikeGLX, Projectors with vector icons, local draft fields, connection/readback placeholders, per-tab logs; scan/test/identify append review-only intent and lock outside editable states. Ownership stays under A10/A11/V15/E12; one Devices module and a Qt SVG icon helper, no new dependency.
- Verification: 44 GUI/client checks pass (40 + 4); Ruff/format, mypy (14 files), boundaries (467 modules, zero violations) pass; `QWidget.actions` collision renamed. Four tabs inspected at 1175x883 and 720x800 (no horizontal scroll); PID 39340 retired; links/whitespace pass; GUI reopened on Devices > Cameras. Inventory/config load/save, hardware checks, transport, Windows/rig unfinished.

### 2026-10-02 [gui] Add a scripts-folder GUI launcher

- `gui-implementation`: `scripts/start_gui.py`, a small standard-library wrapper around the existing review entry; picks Windows or POSIX `.venv` Python, resolves project independent of cwd, defaults to review mode, supports `--read-only`, reports a missing environment, forwards exit status. Report/TODO updated.
- Verification: `--help`, Ruff check/format, mypy (one script) pass; mocked launch checks from /private/tmp cover both modes, cwd and exit-code propagation; boundaries 467 modules, zero violations. Native launch from /private/tmp succeeded and was left open. No GUI/backend behavior change.

### 2026-10-02 [gui] Trial border-inset card titles

- `gui-implementation`: G02 revision 4 (visual trial, not accepted). Shared Card paints the rounded surface and title gap with a small Qt painter; header actions stay right; no per-page change or dependency.
- Verification: 44 GUI/client tests, Ruff/format, mypy (14 files), boundaries (467 modules, zero violations) pass. Native Dashboard, Devices/Cameras, narrow Devices inspected; PID 73367 retired. Evidence in `reports/gui-dashboard-2026-10-01` (dated 2026-10-02); links/whitespace pass; reopened via `scripts/start_gui.py`. Windows/rig pending.

### 2026-10-02 [gui] Remove rectangular card-title masks

- `gui-implementation`: corrects the earlier painter (background patches) without accepting the style trial. Card paints rounded fill continuously and clips only the outline under the caption via Qt QRegion.
- Verification: 44 GUI/client tests, Ruff, mypy (14 files), boundaries (467 modules, zero violations) pass. Native Dashboard, Cameras, narrow Devices inspected; evidence/hashes/report/TODO updated. Windows/rig pending.
- Refs: G02

### 2026-10-02 [gui] Space cards and regroup session fields

- `gui-implementation`: G01 revision 14/G02 revision 5. Extra header spacing via existing card_top token; Clear actions moved into card body; Subject ID/Experiment share the top row, then Output directory, then spaced Subject information (species/sex/age/size/condition). Title style remains under review.
- Verification: 44 GUI/client tests, Ruff, mypy (14 files), boundaries (467 modules, zero violations) pass. Native Dashboard and narrow Devices inspected; PID 80915 closed. Windows/rig pending.

### 2026-10-02 [gui] Simplify session and console cards

- `gui-implementation`: G01 revision 15/G02 revision 6. Dashboard/Devices Clear controls and handlers removed; session card renamed and its subsection heading removed; tests updated.
- Verification: 44 GUI/client tests, Ruff, mypy (14 files), boundaries (467 modules, zero violations) pass. Native Dashboard inspected; Devices tabs and narrow layout captured; evidence/report/TODO updated. Windows/rig pending.

### 2026-10-02 [gui] Add camera inventory/config draft and active preview gates

- `gui-implementation`: G01 revision 16/G02 revision 7; camera enablement now belongs to Devices. Inactive preview sources dimmed/disabled, activity rechecked on request. Source order: Behavior cam, Tracking cam, extra roles, Tracking, Visual stimulus; Devices order Cameras/Arduino/Projectors/SpikeGLX. New `cameras.py` (inventory selection, role checks, per-camera drafts, connection/preview review interactions, exposure/gain/rate/pixel/ROI/trigger/PFS fields); View menu fixtures stand in for Protocol activity.
- Verification: 46 GUI/client checks pass (42 + 4); Ruff/format, mypy (15 files), boundaries (468 modules, zero violations) pass. Native Cameras, inactive selector and narrow layout inspected; PID 91729 retired.
- Limits: sample inventory and connection/visibility are fixtures; no hardware scan/SDK, PFS I/O, viewer or Protocol integration. SDK capability ranges/readback, managed runtime, Windows/rig pending; A10 backend manual-preview contract unchanged.

### 2026-10-02 [gui] [acquisition] Simplify camera configuration and restore shared status columns

- `gui-implementation`: G01 revision 17/G02 revision 8, A10 revision 50/root register. Shared StatusColumn gives HUD/log on every page/subtab. Camera config keeps role, exact trigger-source name, requested Arduino pulse rate and PFS Browse; detail editors, Apply/import/export removed. Shared PathField reuses the async picker with identity/authority checks.
- Verification: 48 GUI/client checks pass (44 + 4); Ruff/format, mypy (15 files), boundaries (468 modules, zero violations) pass. Native Cameras, narrow Cameras, Visual Stimulus inspected; PID 94237 closed.
- Limits: PFS Browse selects a draft path only, no import or applied-parameter report. Controller-owned preset validation/application, trigger configuration, viewers, Windows/rig pending; no acquisition runtime change.

### 2026-10-02 [gui] Align page cards and share selection/table spacing

- `gui-implementation`: G01 revision 18/G02 revision 9. Shell owns a measured-height tools row (device QTabBar left, Dashboard Previews right); device content in synchronized QStackedWidget; one selection palette token; shared 12-pixel table-cell/header padding; nested tab chrome replaced by standard Qt primitives.
- Verification: 48 GUI/client checks, Ruff/format, mypy (15 files), boundaries (468 modules, zero violations) pass; cross-page test verifies equal first-card/HUD top coordinates across seven surfaces. Native Dashboard/Cameras/narrow inspected; PID 94904 retired. Native Windows/rig pending.

### 2026-10-02 [gui] Trial compact single-row headers

- `gui-implementation`: G01 revision 19/G02 revision 10 (visual trial). Tools row merged into title header; Devices tabs beside the title, becoming a synchronized icon dropdown when narrow; common header height.
- Verification: 49 GUI/client checks pass (width synchronization, top-card/HUD alignment); Ruff, mypy (15 files), boundaries (468 modules, zero violations) pass; mypy name collisions corrected. Native Dashboard, Devices, narrow selector inspected; PID 95334 retired. Native Windows/rig pending.

### 2026-10-02 [gui] Place device navigation above the left cards

- `gui-implementation`: owner rejected tabs beside the title; G02 revision 11. One QTabBar in each device panel's left layout above the cards; shell dropdown, synchronization and resize handler removed; shared tab padding fits four icon labels.
- Verification: 49 GUI/client tests pass; Ruff, format, mypy (15 files), boundaries (468 modules, zero violations) pass. Native wide/narrow Cameras inspected; PID 95713 closed. Native Windows/rig pending.

### 2026-10-02 [gui] Polish device navigation and camera inventory actions

- `gui-implementation`: G01 revision 20/G02 revision 12. Full-width tabs aligned with HUD border; camera caption/footer removed; shared ActionHeader with icon Refresh; Connect toggles Disconnect; Test enabled logs only enabled-camera requests as not tested (batch presentation a trial). Transparent header background fixed rounded-section corners after second inspection.
- Verification: 50 GUI/client tests pass (tab clicks across widths, alignment, batch filtering/gates); Ruff/format, mypy (15 files), boundaries (468 modules, zero violations) pass. Native Cameras and Arduino inspected. Hardware checks and Windows/rig pending.

### 2026-10-02 [gui] Expand camera, Microcontroller and projector configuration drafts

- `gui-implementation`: G01 revision 21/G02 revision 13; read A10/A11/V15 and reference (experiment_window.py 10751-11010). Mirror-flip input/output meaning unanswered; no hardware semantics assumed. Test enabled/Connect/Preview order; wrapped log keeps position through eviction. PFS reader extracts bounded FrameStart hints without SDK import (unsupported values unknown). Microcontroller: QtSerialPort enumeration, enabled-camera role/rate pin drafts, conflict checks, add/remove I/O drafts. Projectors: Qt screens, per-output labels, reported properties. No device opened, no pulse sent.
- ARCH-002: generic DevicePanel extracted before Microcontroller, Projectors, preset-hint modules; existing dependencies only; firmware capabilities and display identity not inferred.
- Verification: 54 GUI/client checks pass (50 + 4); Ruff/format, mypy (19 files), boundaries (472 modules, zero violations) pass. Native Cameras, Microcontroller, Projectors inspected; PID 96750 closed. Triggering/frame verification, PFS SDK, viewers, persistence, Windows/rig pending.

### 2026-10-02 [gui] Simplify fixed controller I/O and projector inventory

- `gui-implementation`: owner specified Trial state/camera-trigger outputs, Projector flip input, COM-only discovery, one controller owned by Microcontroller, compact projector display-index/resolution/size/layout view. G01 revision 22/root register updated; electrical/timing firmware details remain open.
- Changes: fixed Outputs/Inputs replace generic signal rows; COM dropdown filters/deduplicates; Projectors uses a four-column table and scaled desktop diagram; read-only Windows QueryDisplayConfig helper maps display numbers (macOS/error paths unknown). No hardware/firmware writes. ARCH-002: no new dependencies.
- Verification: 56 GUI/client tests pass (52 GUI + 4 client); Ruff/format, Windows-target mypy (20 files), boundaries 473 modules, zero violations. Native Microcontroller/Projectors inspected; clipping/corner overlap corrected. Actual Windows Settings numbering and physical dimensions added to the rig checklist. Physical tests/viewers/config application remain unimplemented.

### 2026-10-02 [gui] [acquisition] Simplify Microcontroller rows and individual test intents

- `gui-implementation`: owner requested Inputs first, no camera subsection/Hz, fixed active-high Trial state and rising-edge Projector flip, per-pin tests for SpikeGLX observation. G01 revision 23/A11 revision 35/root register updated.
- Changes: shared local pin-row helper (label/pin/Test); removed edge/level selectors and aggregate trigger-test control. Tests target only the chosen output or input-edge observation; input never driven. Gates retained; unsent requests explicitly not tested. ARCH-002: no new module/dependency.
- Verification: 57 GUI/client tests pass (53 GUI + 4 client); Ruff/format, Windows-target mypy (20 files), boundaries (473 modules, zero violations) pass. Native Microcontroller inspected. Unimplemented: trial-state diagnostic and projector-edge observation commands, bounded test duration, hardware signaling, rig evidence. No pulse-sent claim.

### 2026-10-02 [gui] Toggle pin tests and compact small cards

- `gui-implementation`: owner requested Test changing to Stop and less empty cards. G01 revision 24/G02 revision 14/root register updated.
- Changes: local per-pin review state toggles Test/Stop (compact red Stop, fixed width). Port/scan/pin edits lock until stopped; phase/control/port loss clears review tests. Shared Card compact density for Inputs/Outputs only. ARCH-002: reuses row helper/theme, no new modules/dependencies.
- Verification: 58 GUI/client checks pass (54 GUI + 4 client); conflict test updated to stop before editing wiring. Ruff/format, Windows-target mypy (20 files), boundaries (473 modules, zero violations) pass. Native layout inspected with a labelled temporary COM fixture in the capture harness only. Hardware start/stop and acknowledgements unimplemented; review toggle is not pulse evidence.

### 2026-10-02 [gui] Balance projector columns and remove size

- `gui-implementation`: owner requested Microcontroller suggestions, balanced projector widths, Size removal. G01 revision 25/root register updated. Suggested per-pin status, observed input edge count/last edge, elapsed test time, Stop all: none implemented or accepted.
- Changes: Projectors has Display, Projector, Resolution columns (content-sized Display, equal stretch otherwise); fixed Unassigned/Front/Left/Right/Bottom choices; removed physical-size collection/tooltips and editable-combo caret code. No new dependencies/helpers.
- Verification: 58 GUI/client checks, Ruff, format, Windows-target mypy (20 files), boundaries (473 modules, zero violations) pass. Native Projectors inspected unclipped. Native Windows numbering and hardware diagnostics remain pending; rig checklist updated.

### 2026-10-02 [gui] Enable individual Microcontroller signals

- `gui-implementation`: owner requested enable checkboxes in Inputs/Outputs matching camera participation. G01 revision 26/root register updated.
- Changes: pin-row helper includes enable checkboxes; fixed I/O keeps local draft enablement; camera rows share Cameras participation via stable-ID signals. Disabled rows stay visible, retain pins, cannot test or cause pin conflicts, and stop their local test. Gates remain. ARCH-002: existing Qt controls, no dependencies.
- Verification: 59 GUI/client tests pass (incl. two-way camera sync, disabled conflict exclusion); Ruff/format, Windows-target mypy (20 GUI files), boundaries (473 modules, zero violations) pass. Native captures inspected. Hardware application, diagnostics/transport and Windows rig acceptance pending.

### 2026-10-02 [gui] Balance Microcontroller columns

- `gui-implementation`: owner requested using the enable element to distribute columns evenly. G02 revision 15/root register updated.
- Changes: compact centered checkbox column, wrapped signal name, equal-width expanding pin/Test columns across both cards. ARCH-002: extends row helper with Qt grid proportions/theme spacing; no new dependencies or behavior changes. Spacing literals replaced by theme tokens.
- Verification: 59 GUI/client checks, Ruff/format, Windows-target mypy (20 files), boundaries (473 modules, zero violations), whitespace pass. Native wide/narrow inspected. Hardware/managed integration and Windows rig acceptance pending.

### 2026-10-03 [gui] Exclude operator display and widen pin controls

- `gui-implementation`: owner requested excluding the main display, retaining Windows Settings IDs, wider pin/Test controls. G01 revision 27/G02 revision 16/register updated.
- Changes: primary screen excluded from projector inventory/diagram without renumbering; primary-only topology shows a no-secondary-displays empty state. QueryDisplayConfig mapping rechecked against PowerToys documentation. Name/pin/action columns share equal width. No dependencies or hardware operations.
- Verification: 60 GUI/client checks pass (primary exclusion, retained index 4, empty refresh); Ruff/format, Windows-target mypy (20 files), boundaries (473 modules, zero violations), whitespace, doc links pass. Native layouts inspected. Windows numbering still needs comparison with Settings on the rig; no Windows runtime or hardware pass claimed.

### 2026-10-03 [gui] [visual_stimulus] Projector participation and equal row heights

- `gui-implementation`: owner accepted independent projector enablement, Displays layout caption, equal row heights. G01 revision 28/G02 revision 17/V15 revision 6/root register updated.
- Changes: equal-row-height helper; projector Use drafts retain assignment/geometry. Display Output.enabled defaults true; active-output views drive calibration, native windows, renderer expectations, budgets, evidence. Disabled designated photodiode output and empty selections rejected. Schemas/contracts updated.
- Finding/fix: subset matrix test exposed a pre-existing reversed frustum-distance sign vs V15's formula; corrected (plus an old test's invalid observer workaround). Every nonempty four-output subset preserves projection matrices.
- Verification: 183 GUI/client/Visual Stimulus tests pass (1 optional-dependency skip, 1 Windows deselection); 40 contract tests plus 79 subtests; 11 schema checks; Ruff/format, Windows-target mypy (139 files), boundaries (473 modules, zero violations), whitespace, doc links pass. Repaired eight stale schema links to stimulus-schema.md. No native Windows/optics/hardware acceptance claimed; GUI edits remain local drafts until managed configuration binding.

### 2026-10-03 [gui] [visual_stimulus] Independent pulse/pacing and projector geometry

- `gui-implementation`: owner accepted a photodiode card independent of pacing, CephVR1.0 geometry/projection controls, diagrams replacing the Projectors HUD. G01 revision 29/G02 revision 18/V15 revision 7/V20 revision 6/V22 revision 3/E13 revision 18/register/contracts updated.
- Changes: Timing/Rig geometry/Screen calibration sections; geometry builder with centered inward-facing surfaces; schematic diagram. Backend: `pacing_output_id` controls VSync/swap order and recording rate independently of photodiode; legacy fallback when omitted; pulse-off draws no marker and records null marker evidence. Two generated schemas updated.
- Verification: 226 GUI/client/backend/contract tests and 79 subtests pass (1 skip, 1 deselection); Ruff/format, Windows-target mypy (141 files), 11 schema drift checks, boundaries (475 modules, zero violations), whitespace, doc links pass. Native layouts inspected with explicit fixtures.
- Limits: configuration transport/profile adoption pending; diagram assumes centered planar screens, not optical calibration. Native Windows numbering, physical patch/pacing and measured geometry stay in rig verification.

### 2026-10-03 [gui] [spikeglx] Configuration scrolling and pulse channel drafts

- `gui-implementation`: owner requested reordered projector sections, separated geometry/calibration, pulse editing gates, fixed right column, SpikeGLX channel mapping. G01 revision 30/G02 revision 19/E12 revision 18/register updated; E12 requires photodiode mapping only when enabled (consistent with V22).
- Changes: shared left-column scrolling; per-face inverse/scale/offset table; Synchronization locks dependent editors when pulse is off; focused SpikeGLX editor retains camera/fixed-I/O/pulse/custom mappings with stream/index/channel/bit fields, OneBox-only cameras. No managed backend commands added. ARCH-002: no new dependencies.
- Verification: 65 GUI/client tests pass; Ruff/format and Windows-target mypy (24 GUI files), boundaries (477 modules, zero violations) checked; four affected tests, doc links, whitespace pass. A grid-name collision stalling layout checks was fixed. Native captures reviewed with labelled fixtures. Managed configuration/channel discovery/validation, Windows numbering and rig pulse acceptance pending; no hardware configured.

### 2026-10-03 [gui] [visual_stimulus] Stable columns and screen dimensions table

- `gui-implementation`: owner requested config-only 60 Hz pacing, clearer VSync naming, stable widths, per-screen dimensions table. G01 revision 31/G02 revision 20/V20 revision 7/register updated.
- Changes: pacing selector removed; Visual Stimulus TOML declares `pacing_refresh_hz = 60.0`, installation output identity unset. Synchronization labels presentation as VSync mode; shared scroll gutter and tighter tab padding. Screen dimensions table (Front/Left/Right/Bottom: width, height, projector distance, throw ratio). ARCH-002: no new dependency.
- Verification: 66 GUI/client tests pass (a four-pixel tab overflow was fixed); Ruff/format, Windows-target mypy (24 GUI files), TOML parsing/60 Hz value, boundaries (477 modules, no violations), whitespace, doc links checked. Native captures inspected. Managed TOML adoption and native 60 Hz validation pending; no hardware timing guarantee.

### 2026-10-03 [gui] [visual_stimulus] [spikeglx] Independent screen placement and hidden scrollbars

- `gui-implementation`: owner requested hidden scrollbar tracks, removal of Bit and Screen headers, fitted headings, Profile screen explanation, subject-to-screen distances. G01 revision 32/G02 revision 21/V15 revision 8/register updated.
- Changes: zero-size scrollbar styling keeps wheel/keyboard scrolling; removed Bit editor (E12 digital-word metadata unchanged); Profile screen renamed Calibration file for. Explicit positive perpendicular distances place parallel screens independently of tank walls; diagram and payload share one corner helper; missing/invalid measurements do not default to walls. Projector distance separate. No dependencies.
- Verification: 68 GUI/client checks pass (scrolling, independent planes, invalid-distance rejection, backend compatibility); Ruff/format, Windows-target mypy (24 GUI files), boundaries (477 modules, zero violations), whitespace, doc links checked; four tests pass after heading fixes. Native captures reviewed. Managed adoption, angled-screen editor and physical optics validation outside this increment.

### 2026-10-03 [gui] [spikeglx] All-screen calibration files and deliberate input edits

- `gui-implementation`: owner requested one calibration file updating all values, Load JSON/Save as, no wheel-driven value changes, signal disable/removal. G01 revision 33/G02 revision 22/register updated; GUI calibration JSON contract records the local versioned format.
- Changes: shared file-action row; files hold rig geometry, projection limits and all screen values (null retains unfinished fields); full validation before application, QSaveFile atomic writes. Application-owned wheel filter blocks combo/spin/slider changes and forwards to scroll areas. SpikeGLX Use toggles retain mappings; custom inputs removable. E12 required-channel checks not waived.
- Verification: 73 GUI/client tests pass (JSON roundtrip, invalid no-mutation, wheel forwarding, input disable/removal); Ruff/format, Windows-target mypy (26 GUI modules), boundaries (479 modules, zero violations), whitespace, doc links checked. Native inspected. Native close exited 138; wheel filter now removed on aboutToQuit, later native launch/close exited 0. Managed adoption/SpikeGLX validation and hardware acceptance pending.

### 2026-10-03 [gui] Subject distance grouping and calibration scope

- `gui-implementation`: owner requested calibration JSON excluding display/projector lists, removed schematic footer, Subject distances in Rig geometry, clearer labels. G01 revision 34/register updated.
- Changes: subject-to-screen editors under Subject → Left wall / Front wall / Bottom (mm); Screen dimensions holds sizes, projector distance, throw only. JSON keeps existing field identities and excludes device inventory/assignments; test verifies assignments/participation survive save/load. Diagram footer removed. No geometry change or new dependencies.
- Verification: 73 GUI/client tests pass; Ruff/format, Windows-target mypy (26 GUI files), boundaries (479 modules, zero violations), whitespace, doc links checked; a loop-variable typing collision fixed. Native inspection confirms fit. Managed adoption and physical rig validation pending.

### 2026-10-03 [gui] [visual_stimulus] Right-screen derivation clarification

- `gui-implementation`: owner asked to remove the right-screen distance editor and how to remove SpikeGLX signals. Custom SpikeGLX rows have × removal; source-derived rows keep identity and Use toggles.
- Review: equal wall offsets imply right distance = tank width + left-screen distance − 2 × subject-to-left-wall distance; using tank width as screen separation implies right = tank width − left-screen distance; the two give different projections.
- Status: asked the owner which constraint applies under GOV-001. Equal offsets was an unaccepted assumption. No code changed, no tests rerun.

### 2026-10-03 [gui] [visual_stimulus] Derive right-screen distance from equal offsets

- `gui-implementation`: owner confirmed equal left/right offsets from tank walls. G01 revision 35/V15 revision 9/register updated.
- Changes: only Left/Front/Bottom distance editors remain; shared resolver derives right = width + left distance − 2 × subject-left-wall distance (invalid/missing cleared); diagram and projection builder use it. Calibration JSON v2 stores independent fields only; v1 right distances must match the formula or the file is rejected with values untouched. Backend corner schema unchanged. One focused resolver, no dependency.
- Verification: 74 GUI/client tests pass (off-center, stale clearing, legacy migration, asymmetric no-mutation); Ruff/format, Windows-target mypy (26 GUI files), boundaries (479 modules, zero violations), whitespace, doc links checked. Native inspected with fixtures. Managed profile adoption and physical optics acceptance pending.

### 2026-10-03 [gui] [visual_stimulus] Protocol navigation and asset-folder ownership

- `gui-implementation`: owner places Protocol below Dashboard (stimulus programming/participation/recordings), assigns asset folders to Visual Stimulus, removes Advanced subtitle. G01 revision 36/register updated.
- Changes: Protocol and asset pages reuse shared cards/helpers. Camera Use edits share Devices drafts; E10 locks required Visual Stimulus and closed-loop Tracking. Initial program editor uses canonical V03 JSON with bounded validation and atomic Save as. E07 runtime root semantics unchanged. Pending: graphical V02 authoring, session-setting persistence, managed adoption, hardware acceptance.
- Verification: 76 GUI/client tests pass; Ruff/format, Windows-target mypy (28 GUI modules), boundaries (481 modules, zero violations), whitespace pass. Earlier attempts used nonexistent client test paths (no tests executed); corrected to test_state_views.py. Native captures inspected. No backend execution claimed.

### 2026-10-03 [gui] [visual_stimulus] Consolidate Protocol and propose graphical planner

- `gui-implementation`: owner removed the Visual Stimulus navigation page, moved asset directories atop Protocol, renamed Session mode to Protocol type. G01 revision 37/register updated; redundant asset wrapper removed (ARCH-002).
- Review: inspected CephVR1.0 at 38f728291ed551a332392dc2c7b6897e8428b060 (trial-planner family, per-screen, sequence, variation). Proposed full-width sequence/inspector with derived timeline; automatic participant scenarios and HUD/log removal remain proposals. No E10/backend behavior amended.
- Verification: 76 GUI/client checks pass; Ruff/format, Windows-target mypy (28 GUI files), boundaries (481 modules, zero violations), whitespace pass. Interactive proposal passed isolated Chrome checks at 1024/736/320 px. Managed backend binding and graphical planner implementation pending.

### 2026-10-03 [gui] [tracking] [visual_stimulus] [spikeglx] Separate recording choices from device controls

- `gui-implementation`: owner clarified per-camera/stimulus video switches, Tracking derived from protocol and velocity recording, Devices-only SpikeGLX/Microcontroller configuration. G01 revision 38/E10 revision 21/T14 revision 2/register updated; T14 saved/file defaults preserved.
- Changes: Protocol Recordings replaces the manual Use/backend grid; video switches preserve selections on device disablement. Record velocities derives Tracking with Protocol type; SpikeGLX local control-enable checkbox. Managed propagation pending. No dependencies.
- Planner review: inspected CephVR1.0 classic/table and V3 source; the graphical proposal is separate from the native JSON editor and not implemented.
- Verification: 76 GUI/client checks; lint/format, Windows-target mypy (28 GUI modules), boundaries (481 modules, zero violations), whitespace pass. Native captures and isolated Chrome checks (1024/736/320px) done. No hardware validation.

### 2026-10-03 [gui] [visual_stimulus] Timeline-only planner research and status removal

- `gui-implementation`: owner removes Tracking status from Protocol and rejects the trial table view. G01 revision 39/V02 revision 10/register updated. Label/update code removed; derived Tracking participation and preview gating retained.
- Research: PsychoPy Builder, E-Prime Procedure, OpenSesame, BonVision docs; sources/recommendations in reports/runtime.md. Timeline-only sketch keeps trial/block navigation and bottom properties; timeline edits represent canonical nodes. Other proposals unaccepted.
- Verification: three focused checks pass (69 deselected); Ruff/format, Windows-target mypy (28 GUI files), boundaries (481 modules, zero violations), whitespace pass. Isolated Chrome sketch checks at 1024/736/320 px pass. No backend changes or rig acceptance claimed.

### 2026-10-03 [gui] [visual_stimulus] Implement clean Protocol cards and timeline

- `gui-implementation`: owner requested native card separation and visual simplification. G01 revision 40/G02 revision 23/register record Protocol's full-width authoring exception, no HUD/log or trial table.
- Changes: separate folder, recording, program/file, trial, timeline and selected-stimulus cards; trial selection and exact fixed-duration edits use canonical V03 models; per-trial JSON validation/atomic save; imported groups survive. Trial drafts are local. Pending: full scene/group/condition authoring, managed integration. No new dependencies.
- Verification: 78 GUI/client checks pass (four Protocol checks after final refinements); Ruff/format, Windows-target mypy (31 GUI files), boundaries (484 modules, zero violations), whitespace pass. Native review fixed narrow ruler crowding/min height. Evidence and limits in reports/runtime.md. No hardware or managed execution claimed.

### 2026-10-03 [gui] [visual_stimulus] [tracking] Simplify Protocol controls and expose stimulus parameters

- `gui-implementation`: owner requested Tracking velocities in the recording grid, Load instead of path field, no draft/Validate controls, enabled-screen timeline lanes, type-dependent stimulus editing. G01 revision 41/E10 revision 22/T14 revision 3/register updated; semantics unchanged.
- Changes: model-generated parameter widgets; templates for image/video/arena, grating/checkerboard/image-tile, keyframed looming. Edits validate before commit; invalid drafts editable with Reset. Asset browser enforces root-relative paths. No new grammar/dependencies (ARCH-002/V02–V05/V14/V24).
- Verification: 88 GUI/client checks pass; all eight presets round-trip; Ruff/format, Windows-target mypy (34 GUI files), boundaries (487 modules, zero violations), whitespace pass. Native review fixed gray backgrounds/nested controls. Evidence in reports/runtime.md.
- Limits: not complete legacy planner parity; nested group/condition editing, scene/sequence authoring, scheduling/persistence, managed adoption, rig checks pending. Media template filenames are placeholders; structural validity is not Setup readiness.
- Refs: V03

### 2026-10-03 [gui] [visual_stimulus] Prepared stimulus files and epoch motion

- `gui-implementation`: owner requests one Assets folder, prepared stimulus appearances, epoch parameter editing, accepting exported images and CephVR1 texture JSON. G01 revision 42/V02 revision 11/register updated.
- Changes: removed secondary folder controls and texture-design forms. Add stimulus selects prepared files; legacy texture imports use the exported PNG, normalize to canonical V03, reject incomplete/outside-root bundles without mutation. Replacing a file is epoch-local. Simple motion controls coexist with custom motion; epoch add/duplicate/reorder/remove validates first. No dependencies.
- Verification: 93 GUI/client tests pass (nine focused after final adjustments); Ruff/format, Windows-target mypy (37 GUI files), boundaries (490 modules, zero violations), whitespace pass. Native captures inspected; evidence in GUI evidence directory/reports/runtime.md.
- Limits: plain texture images retain declared scale (pixels do not imply physical size); no legacy procedural rendering. Nested group/condition authoring, scheduling, managed adoption, hardware/runtime acceptance pending.

### 2026-10-03 [gui] [visual_stimulus] Simplify Protocol layout and epoch editing

- `gui-implementation`: owner requests Assets above Visual stimulus program with Recordings beside both, simpler epoch editing per CephVR1 V3 inspector (38f728291ed551a332392dc2c7b6897e8428b060, 1490–1540, 1645–1718). G01 revision 43/register updated; V02 unchanged.
- Changes: Recordings spans two rows, stacks at narrow widths; timeline exposes Add epoch; Epoch editor groups selection/duration/stimulus, Remove direct, duplication/reordering under More; State/Feedback/Inputs under More parameters. Hidden controls keep values. No dependencies/backend change.
- Verification: 93 GUI/client tests pass; Ruff/format, Windows-target mypy (37 GUI files), boundaries (490 modules, zero violations), doc links, whitespace checked. A standalone offscreen probe exited signal 138; pytest/native runs completed normally. Native captures inspected. Managed integration, nested groups/conditions, scheduling, rig acceptance pending.

### 2026-10-03 [gui] Horizontal Protocol recordings

- `gui-implementation`: owner replaces the top-card arrangement. G01 revision 44/register: Protocol type left of Assets folder, one full-width horizontal Recordings row below; Load/Save as stay with Protocol type; narrow widths stack. No dependencies or behavior changes (ARCH-002).
- Verification: nine focused Protocol/prepared-file tests pass; Ruff/format, Windows-target mypy (37 files), boundaries (490 modules, zero violations), whitespace pass. Native overview inspected. Earlier 93-test suite remains historical; managed and rig limits unchanged.

### 2026-10-03 [gui] [visual_stimulus] Research a simpler stimulus-programming workflow

- `gui-implementation`: owner requested research/planning only. Reviewed PsychoPy Builder/Flow, Labvanced, Gorilla Task Builder 2, OpenSesame loop, BonVision guides; sources, proposed workflow, stages and acceptance scenarios in the runtime report; TODO awaits proposal review. G01/V02 unchanged.
- Proposal: one dominant timeline and contextual editor, prepared-content-first epoch creation, compact trial selection, Undo/Redo, explicit screen scopes, canonical repeat/variation groups with expanded-order inspection. No new runtime semantics/libraries/backend changes authorized.
- Evidence: conversation-only interactive alternatives passed isolated Chrome checks at 1024/736/320px; screenshots in the GUI evidence directory. Documentation review only, not benchmarking or usability proof. Native GUI unchanged; no runtime tests.

### 2026-10-03 [gui] [visual_stimulus] Implement all three Protocol authoring stages

- `gui-implementation`: owner requests all three proposed stages and selects timeline with side editor. G01 revision 45/register updated; V02/V03/V07/V08 unchanged.
- Changes: content-first atomic epoch insertion, compact trial selection, per-trial Undo/Redo; screen scopes and optional layers; nested group navigation/editing/duplication, paired/product variations, condition-list editing, expanded-order inspection. Fixed stationary image-tile negative-zero direction (speed-only variation keeps +X, regression test). ARCH-002 split into focused modules; no dependency changes.
- Verification: GUI/client-state/compiler suite passes 110 checks in 30.51s; Ruff/format, Windows-target mypy (46 GUI files), boundaries (499 modules, zero violations), whitespace, doc links pass. Native captures in the GUI evidence directory, limits in reports/runtime.md.
- Limits: local authoring only; managed binding, session scheduling/persistence, Windows/rig acceptance pending.

### 2026-10-03 [gui] [visual_stimulus] Projector-lane layers and planner controls

- `gui-implementation`: owner requests Expanded sequence Close, trial deletion, adjacent recording checks, projector-specific layered stimuli. G01 revision 46/register updated; V02/V03/V07 unchanged.
- Changes: each enabled projector lane shows its layer stack; selected projector filters the layer editor and targets overlays/edits/removal/ordering. Shared 2D content detaches only on local mutation. Rig-wide arenas need All projectors. Placement exposes opacity; looming supports size functions. Delete trial confirms and preserves files. ARCH-002: extracted dialog/view/mutation/menu modules; roughly 540-line editor remains a cohesive coordinator (noted in report). No dependencies.
- Verification: 114 GUI/client-state/compiler checks pass (six focused after final layout); Ruff/format, Windows-target mypy (48 GUI files), boundaries (501 modules, zero violations), whitespace, doc links pass. Native captures inspected with temporary assets and labeled sample assignments; no hardware commands. Managed execution, scheduling/persistence, rig acceptance pending.
- Refs: `reports/runtime.md`

### 2026-10-03 [gui] Remove history toolbar buttons and review Epoch clutter

- `gui-implementation`: owner requests Undo/Redo button removal and Epoch simplification advice. Toolbar widgets removed; history operations remain in Actions. G01 revision 47/register updated; no dependency or program-semantic change.
- Proposal (not implemented/accepted): timeline owns projector/layer selection, epoch metadata near it, side card with one file row plus family parameters and one More settings expansion.
- Validation: four focused checks pass; Ruff/format, Windows-target mypy (48 GUI files), boundaries (501 modules, zero violations), whitespace pass. Native captures inspected. No hardware or managed-runtime validation claimed.
- Refs: `reports/runtime.md`

### 2026-10-03 [gui] [visual_stimulus] Compact Stimulus inspector

- `gui-implementation`: owner accepts the Epoch simplification. G01 revision 48/register: epoch metadata above the timeline, one compact Stimulus inspector. V02/V03/V07 unchanged.
- Changes: timeline layer clicks replace dropdowns; per-projector + and layer context menus; one path/Replace row and essential controls before a single More settings; looming size/growth edits keep exact decimal timing, unsupported imported curves stay canonical in advanced settings. ARCH-002: extracted menus/looming controls; 566-line editor stays a cohesive coordinator. No dependencies.
- Validation: full suite passed 117 checks; three focused tests pass after a looming synchronization fix. Ruff/format and Windows-target mypy (50 GUI files) pass; boundaries 503 modules, zero violations. Doc targets and whitespace pass. Native captures inspected with labeled samples. Managed adoption, scheduling/persistence, Windows and hardware acceptance pending.

### 2026-10-03 [gui] Full-width timeline above Stimulus

- `gui-implementation`: owner requests a horizontal full-width timeline with the Stimulus card below. G01 revision 49/register; stimulus/timing semantics unchanged.
- Changes: stacked cards at all widths, combined footer, hidden root-only breadcrumb, shared drag/keyboard height grip (a splitter probe was blocked by minimum-sized cards, so the grip changes section height). ARCH-002: obsolete reflow removed; coordinator's cohesion exception remains in the runtime report. No dependencies/backend changes.
- Validation: 105 GUI tests pass in 38.35s; Ruff/format, Windows-target mypy (50 files), boundaries (503 modules, zero violations), doc targets, whitespace pass. Earlier 117-test evidence is historical. Native captures inspected with labeled samples. Managed integration and Windows/rig acceptance pending.

### 2026-10-03 [gui] [visual_stimulus] Review batch-first epoch workflow

- `gui-implementation`: owner wants full-trial visualization/epoch selection in the timeline, separate controls, primarily batch creation/editing. Inspected CephVR1.0 V3 reference generation/batch-edit source at HEAD 38f728291ed551a332392dc2c7b6897e8428b060 (3266–3578, 4288–4530).
- Proposal: visualization-only timeline above one Epoch editor with Create/Edit selected modes, projector/layer scope, generation summaries, explicit patch-only multi-epoch edits. Report records findings; TODO awaits review. G01 revision 49 and native implementation unchanged; no runtime policy or random generator added. Source inspection is not runtime verification; no runtime tests.

### 2026-10-03 [gui] [visual_stimulus] Batch-first Epoch editor

- `gui-implementation`: owner authorizes the visualization-only timeline and separate Create/Edit selected workflow. G01 revision 50/register; V02/V03/V07/V08 and Setup seed ownership preserved.
- Changes: projector lanes select epochs by click/range/toggle. Create composes a prepared-asset reference with layers, exact duration, paired/crossed variations, repetition/order, preview count; insertion atomic. Edit selected shows mixed values, applies only checked fields, rejects invalid targets without partial commits. ARCH-002: split batch/reference/generation/patch UI modules; 624-line coordinator exception recorded in report. No dependencies.
- Validation: GUI/client-state/compiler suite passes 121 checks in 48.17s; Ruff/format, Windows-target mypy (55 GUI files), boundaries (508 modules, zero violations), doc targets, whitespace pass. Fixed premature whole-trial minimum validation on a reference. Native captures inspected. No hardware commands. Scheduling/persistence, managed adoption, Windows/rig acceptance pending.
- Refs: `reports/runtime.md`

### 2026-10-04 [gui] Four review projectors and fixed trial overview

- `gui-implementation`: owner requests four simulated projectors for authoring, centered count/duration, no vertical expansion, slim CephVR1-style Trials column (V3 rail source 4690–4725). G01 revision 51/register updated.
- Changes: review launcher supplies Front/Left/Right/Bottom display records; Refresh keeps local assignments; labels identify samples; no saved configuration or hardware commands. Styled Trials list with compact Add/Delete; equal fixed heights; internal scrolling. 625-line editor stays cohesive. No dependencies.
- Validation: 8 focused checks, then full suite 122 checks in 46.83s; Ruff/format, Windows-target mypy (55 files), boundaries (508 modules, zero violations), whitespace pass. No Windows/hardware or managed acceptance claimed. Narrow review found existing recording-label clipping at 720 pixels; tracked as follow-up.
- Refs: `reports/runtime.md`

### 2026-10-04 [gui] Move Recordings to Dashboard

- `gui-implementation`: owner requests Recordings below Session config. G01 revision 52/register updated.
- Changes: extracted a focused RecordingsCard into Dashboard's configuration column; removed Protocol's recording row. Two-column checkbox/label pairs fix the narrow clipping. Shared draft state still derives Tracking; camera enablement, saved choices and edit gates intact. No backend/dependency changes.
- Validation: full GUI run passed 109 checks and failed one obsolete card-list assertion; after correction all five affected checks pass. Ruff/format (57 files), Windows-target mypy (56 files), boundaries (509 modules, zero violations), doc targets, whitespace pass. Prior 122-check evidence is historical. Native captures inspected. Windows/hardware and managed integration pending.

### 2026-10-04 [gui] Color-coded overview and current-epoch projector details

- `gui-implementation`: owner requests one overview bar split by epochs, color grouping for similar settings, current-epoch per-projector descriptions, Batch create/Batch edit tabs. G01 revision 53/register updated.
- Changes: duration-proportional overview keeps selection semantics; stable muted colors from ordered settings/assets/mappings/background (excluding names, durations, identifiers). Current occurrence shows enabled-projector rows with hover descriptions. Summaries/color keys in separate read-only modules; no new dependencies/semantics.
- Validation: eight focused checks; combined suite passes 123 checks in 47.24s. Ruff/format (58 files), Windows-target mypy (57 GUI files), boundaries (510 modules, zero violations), doc targets, whitespace pass. Editor remains 626 lines. Native captures inspected; provenance in reports/runtime.md. Managed integration, Windows and hardware acceptance pending.

### 2026-10-04 [gui] Wider trial layout and separate batch windows

- `gui-implementation`: owner requests wider Trials, overview aligned with projector labels, extra spacing, CephVR1.0-style batch windows (V3 BlockEditorDialog/PlannerBatchEditDialog reviewed). G01 revision 54/register updated.
- Changes: Trials 158 to 208 logical pixels; overview extends to section edges; Batch buttons open modal windows with internal scrolling; commits close, failed validation stays visible, Cancel discards patches; phase/control loss closes windows. Focused dialog shell reuses existing forms; coordinator 633 lines. No dependencies/backend change.
- Validation: three focused tests; full suite 124 checks in 50.11s. Ruff/format (59 files), Windows-target mypy (58 files), boundaries (511 modules, zero violations), doc targets, whitespace pass. Native captures inspected. Managed integration and Windows/hardware acceptance pending.
- Refs: `reports/runtime.md`

### 2026-10-04 [gui] Inline batch tabs in Epoch editor

- `gui-implementation`: owner clarifies Batch create/edit are tabs inside the card. G01 revision 55/register updated.
- Changes: batch forms embedded below a tab bar; switching preserves drafts; explicit Add/Apply and Discard unchanged. Modal wiring and unused dialog shell removed (ARCH-002). Coordinator 627 lines. No dependency/backend change.
- Validation: 112 GUI tests pass in 50.46s; Ruff/format (58 files), Windows-target mypy (57 files), boundaries (510 modules, zero violations), doc targets, whitespace pass. Earlier combined client/compiler results historical. Native layouts inspected. Managed integration and Windows/hardware acceptance pending.
- Refs: `reports/runtime.md`

### 2026-10-04 [gui] Per-projector Batch create parameters

- `gui-implementation`: owner requests stimulus-specific parameters per projector (CephVR1.0). G01 revision 56/register updated.
- Changes: each enabled projector has independent assets, layer selection and family controls (texture/image motion, looming, video playback via existing editors); advanced under More settings; rig-wide arena separate; sibling fields survive commits; file dialogs follow phase locks. Focused projector-row widget; ProtocolEditor unchanged at 627 lines. No dependency.
- Validation: three focused checks; final GUI suite 114 tests in 49.05s (supersedes earlier 114-test pass). Ruff/format (59 files), Windows-target mypy (58 files), boundaries (511 modules, zero violations), doc targets, whitespace pass. Native captures inspected. Managed integration and Windows/rig acceptance pending.
- Refs: `reports/runtime.md`

### 2026-10-04 [gui] Compact Batch create reference grid

- `gui-implementation`: owner rejects the repeated full-form layout, requests CephVR1.0 simplicity. G01 revision 57/register: compact reference rows, shared headings, one secondary-action menu per row.
- Changes: projector, layer, asset and family values share one row; headings repeat only when meaning/units change; repeated buttons and More checkboxes removed; blank projectors expose Choose; narrow windows stack. Reference-cell helper reuses actual family controls; superseded layout code removed. No dependency/backend change.
- Validation: four focused tests; full GUI suite 115 checks in 53.91s. Ruff/format (60 files), Windows-target mypy (59 files), boundaries (512 modules, zero violations), doc targets/anchor, whitespace pass. Native captures refined after first view. Managed and Windows/rig acceptance pending.
- Refs: `reports/runtime.md`

### 2026-10-04 [gui] [visual_stimulus] Epoch types, batch labels and insertion

- `gui-implementation`: owner requests working type dropdowns with asset reset, no Projector heading, per-projector/arena mode, saved batch labels, insertion choices, filename-only assets, Looming naming. Reviewed CephVR1.0 V3 and `_insert_rows_every_n`; G01 revision 58/V03 revision 9/register updated.
- Changes: header groups duration, mode, label; layer types switchable with fresh assets; optional bounded source-epoch label persists through JSON, targetable by Batch edit; six atomic insertion modes keep repeat groups as top-level blocks with undo. No dependencies or rendering changes; coordinator 621 lines.
- Validation: 12 focused checks; combined GUI/compiler/contract command 172 tests plus 79 subtests in 58.87s (123 GUI). Ruff/format (64 files), Windows-target mypy (62 files), 11 schema comparisons, boundaries (514 modules, zero violations), doc targets, whitespace pass. Pre-existing pacing-refresh loader rejection recorded under the managed-adoption follow-up. An ad hoc geometry probe exited 139; cause not established. Managed integration, pacing-loader follow-up and Windows/rig acceptance pending.
- Refs: `reports/runtime.md`

### 2026-10-04 [gui] [visual_stimulus] Batch spacing and independent arena axes

- `gui-implementation`: owner requests generation controls below epoch identity, consistent row spacing, arena axis/gain controls per CephVR1.0; after the V24 shared-gain conflict was explained, owner selected independent axes/gains. G01 revision 59/V24 revision 7/register/reports updated.
- Changes: Arena shows Longitudinal/Lateral/Angular toggles and signed gains; form preserves imported custom feedback/programmed motion and rejects incompatible Tracking channels. Planar `sideways_gain` optional (fallback to `gain`); both evaluated independently before heading transform/boundary slide; zero disables an axis. No dependency/timing changes.
- Validation: GUI/feedback/compiler/contracts command 194 tests plus 79 subtests in 38.83s; ten runtime cases (unequal/disabled/reversed/legacy gains at two headings). Ruff/format (67 files), Windows-target mypy (65 files), 11 schema checks, boundaries (515 modules, zero violations), doc targets, whitespace pass. Native captures inspected. Managed binding, pacing-loader adoption and Windows/physical closed-loop acceptance pending.
- Refs: `reports/runtime.md`

### 2026-10-04 [gui] [visual_stimulus] Rotate tank view and show projector footprints

- `gui-implementation`: owner requests drag rotation, distance/throw projections with projectors centered on screens, side/Bottom screens starting at Front. G01 revision 60/V15 revision 10/register/calibration format updated.
- Changes: side/Bottom front edges anchored to the Front plane; focused QPainter diagram (no dependencies); left drag rotates view only, double-click resets; ideal centered footprints from distance/throw and display aspect, inactive/invalid cones omitted. Backend rendering/warp and calibration JSON fields unchanged.
- Validation: final run 183 tests plus 79 subtests in 37.76s (128 GUI). Ruff/format (64 files), Windows-target mypy (63 files), boundaries (516 modules, zero violations), link targets, whitespace pass. A first command referenced a nonexistent client filename and ran no tests. Native captures inspected with sample geometry; evidence in reports/runtime.md. Managed adoption, pacing-loader follow-up and Windows/optical rig acceptance pending.

### 2026-10-04 [gui] [visual_stimulus] Bottom mirror path and plot visibility controls

- `gui-implementation`: owner corrects Bottom routing via a 45° mirror below the tank with its projector beneath Right, requests plot toggles/legend. G01 revision 61/register/calibration-distance docs updated. Total optical path is a working interpretation of Bottom distance; no measured mirror dimensions or runtime optical model added.
- Changes: Bottom's virtual cone folds through a computed 45° reflector, horizontal coordinates match Right; invalid paths omit the cone with hover explanation. Nine toggle buttons (tank/screens/projectors/mirror/footprints/rays/subject/labels/legend) do not mutate calibration. Pure optics extracted; no dependencies/backend rendering changes.
- Validation: four focused checks; GUI/client-state/compiler/contracts 186 tests plus 79 subtests in 65.06s (131 GUI). Ruff/format (65 files), Windows-target mypy (64 GUI files), boundaries (517 modules, zero violations), link targets, whitespace pass. Native captures with local samples; evidence in reports/runtime.md. Managed adoption, pacing-loader follow-up and Windows/optical rig acceptance pending.

### 2026-10-04 [gui] Batch header, visible layers and insertion by label

- `gui-implementation`; G01 revision 62/root register and runtime report updated. Batch fields share a row (wrapping when narrow); per-projector Layer dropdown selects prepared asset/family parameters; After label inserts batches after matching labeled epochs (atomic reject on missing label/invalid/oversized; undo restores). Placement editors removed (values kept), Opacity editable. ARCH-002: reused import/remapping/validation; ProtocolEditor stays 622 lines.
- Validation: GUI/client-state/compiler 146 passed (58.25s; 133 GUI); Ruff/format (65 files), Windows-target mypy (64 GUI files), boundaries (517 modules, 0 violations), docs, whitespace pass. One transient mypy run saw concurrent tank-diagram errors; next run passed.
- Native review done (clipped Layer label and narrow overflow fixed, recaptured); evidence in reports/runtime.md. Managed binding, pacing-loader adoption, Windows/rig acceptance pending.

### 2026-10-04 [gui] Projection grouping and incomplete Bottom cone visibility

- `gui-implementation`; G01 revision 63/root register, calibration/report clarifications updated. No hard-coded 700 threshold exists: the helper rejected the whole assembly on any invalid outer-ray intercept. It now separates impossible central geometry from incomplete edge coverage (incomplete footprint dashed with hover detail). All four optics share Projection visibility/legend; violet footprints distinct. ARCH-002: removed duplicated per-element gates.
- Validation: 5 focused tests; GUI/client-state/compiler/contracts 190 tests + 79 subtests (62.77s; 135 GUI); Ruff/format (65 files), mypy (64 GUI files), boundaries (517 modules, 0 violations), links, whitespace pass. A fixture using a below-tank screen was corrected.
- Native review done; evidence in reports/runtime.md. Managed adoption, pacing-loader follow-up, Windows/optical rig acceptance pending.

### 2026-10-04 [gui] Unified advanced settings and readable feedback mappings

- `gui-implementation`; G01 revision 64/root register, runtime report updated. Separate advanced tabs removed: Opacity, Retain state and Feedback share one indented section. Binding IDs generated, operation follows signal quantity, compatible Input signal/Parameter choices replace schema fields, custom inputs inline; imported functions preserved; arena axis gains sync both ways; invalid edits reject atomically. ARCH-002: split signal definitions, rows, patch ownership into focused modules; no new dependency/backend change; ProtocolEditor stays 622 lines.
- Validation: GUI/client-state/compiler 151 passed (60.32s; 138 GUI); Ruff/format (68 files), mypy (67 GUI files), boundaries (520 modules, 0 violations), links, whitespace pass; initial static errors corrected.
- Native review done; review signals are local declarations, not transport discovery. Managed integration, pacing-loader follow-up, Windows/rig acceptance pending.
- Refs: `reports/runtime.md`

### 2026-10-04 [gui] Bottom schematic pyramid and review-image cleanup

- `gui-implementation`; G01 revision 65/root register, runtime/Visual Stimulus reports updated. Legend toggle removed (five toggles; legend always visible); Bottom draws four schematic edges mirror-to-footprint plus projector-to-mirror line. Reflection/clearance calculation, dashed warning, calibration, backend rendering unchanged.
- Cleanup: removed all 383 generated GUI review images and three temporary synthetic assets (owner request); historical image links converted to text, assessments/harnesses/hashes retained.
- Validation: GUI/client-state/compiler/contracts 193 tests + 79 subtests (63.76s; 138 GUI); Ruff/format (68 files), mypy (67 GUI files), boundaries (520 modules, 0 violations), docs, whitespace pass. No backend/Windows/optical rig acceptance claimed. Managed integration and pacing-loader follow-up pending.

### 2026-10-04 [repo] Project dependency environment refresh

- `environment-dependencies`; Python 3.11 `.venv` checked against `pyproject.toml` and SYS-003. Installed editable `cephvr` with `[dev,gui,tracking,visual_stimulus,acquisition]`; PyQt6 6.11.0, PyQt6-Qt6 6.11.2, PyQt6-sip 13.12.0 added. No package declarations or tracked source changed. Sandboxed pip attempts failed on build-tracker files; the authorized escalated install completed.
- Validation: `pip check` no broken requirements; Python 3.11.15; PyQt6/QtWidgets, backend extras and `cephvr` import; version 2.0.0.dev0; `git diff --check` passes. Establishes import/dependency consistency only, not device, GPU or GUI operation. Base interpreter is `miniforge3/envs/CephVR`; no independent Python 3.11 found, so interpreter provenance stays a SYS-003 deployment consideration.

### 2026-10-04 [gui] [acquisition] Rig device discovery and COM labels

- `gui-implementation`; G01 revision 66/root register, runtime report, TODO updated (no managed Setup claim). Normal review startup removes camera fixtures and scans Basler SDK inventory, secondary Qt/Windows displays and COM ports; camera refresh keeps per-serial drafts, Test enabled does A10 open/identity/close; COM labels show descriptions plus port identity. `--simulated-devices` remains. ARCH-002: no new dependency/process.
- Rig evidence: pypylon found 40065509/acA4112-30uc and 40747103/a2A2464-77umPRO (opened, identified, closed). Qt found COM8/Arduino Uno, COM9/USB-Serial Controller, only the primary DELL S2721HS display and no projector output. No stream, projector light or managed lifecycle tested.
- Validation: 3 focused tests, Ruff, mypy, boundaries (520 modules, 0 violations) pass; broad offscreen GUI run inconclusive (temp permission errors, unrelated layout failures). Rig output and full GUI behavior pending.

### 2026-10-04 [gui] Rig projector display index mapping

- `gui-implementation`; G01 revision 67/root register, runtime report, TODO updated. Qt EDID names (`ITE6801 (1)`-`(4)`) did not match Windows DisplayConfig source names (`\\.\DISPLAY1`-`DISPLAY4`), causing unknown labels. Fix: map active Windows monitors to desktop rectangles; assign index only on unique Qt rectangle match, ambiguity stays unknown. Kept in `display_indices` module (ARCH-002).
- Rig evidence: all four secondary Qt screens matched; GUI showed indices 5, 2, 3, 4 in Qt screen order; five active Windows monitor rectangles returned. Physical surfaces and Settings Identify still need user observation.
- Validation: 4 focused tests, Ruff, mypy, boundaries (520 modules, 0 violations), whitespace pass. No projection/optical verification.

### 2026-10-04 [gui] [acquisition] Live camera preview path investigation

- `camera-preview-gui-binding`; reviewed A10, G01, preview/configuration-control contracts, GUI signal path and client/backend commands.
- Finding: review GUI Connect/Preview change only local flags; `PreviewDialog` is a selector with no viewer. Acquisition worker already implements manual preview start/stop/attachment, but the GUI has no managed controller connection or viewer. A direct GUI SDK reader would be a second camera owner, contrary to A10. Owner asked to choose between managed path and an explicit local diagnostic exception; no capture code or settings changed.
- Source/contract inspection only; the earlier open/identity/close check is not frame-capture evidence.

### 2026-10-04 [gui] Epoch Editor batch generation controls

- `gui-implementation`; reviewed G01, V08, CephVR1.0 V3 flow. G01 revision 68/root register, runtime report, form updated. Batch generate names the tab; stimulus mode joins duration/repetitions/label/insertion with proportional widths; duration accepts `hh:mm:ss` with optional nanosecond fractions; listed order preserved, repetitions capped at three digits; tab wheel gestures ignored; bounded min/max/step sweeps added to explicit lists. ARCH-002: existing composer/generator kept.
- Validation: 6 focused tests pass; Ruff/format, mypy, boundaries (520 modules, 0 violations) pass (one annotation fix). Broader batch run hit a native Qt access violation in the existing file-picker test, so not a passing suite. No managed Setup or rig validation.

### 2026-10-04 [gui] Startup transient reference-label windows

- `gui-implementation`; a Qt Show/Hide trace on Windows found unparented `QLabel` headings/placeholders in `ProjectorReference.arrange` (`show()` before grid add) creating brief windows; a G01 GUI construction defect, not backend/device.
- Fix: add each heading/control to its grid before `show()`; local to existing method (ARCH-002).
- Validation: focused regression and adjacent batch test pass; Ruff, format, mypy pass. A second visible launch traced only `DashboardWindow` over five seconds. No device command.

### 2026-10-04 [gui] Windows display ID correction

- `gui-implementation`; rig screenshot showed DisplayConfig path positions differ from Settings IDs (QueryDisplayConfig is priority order). G01 revision 69/root register, runtime report, TODO record the mismatch.
- Change: table/diagram show unknown until Match Windows IDs confirms Settings Identify labels by position; dialog rejects duplicates, saves labels for the whole screen topology, clears them on layout change. ARCH-002: dialog, persistence, topology and drawing extracted into focused modules.
- Validation: 3 focused tests; Ruff, format, mypy, boundaries (522 modules, 0 violations), whitespace pass. Broader GUI suite hit temp-path errors and a native Qt access violation, so not a pass. Exact Settings labels need operator comparison; no physical projection.

### 2026-10-04 [gui] Prevent transient windows on Epoch Editor updates

- Correction to the startup-window entry: with four projectors, a second trace found `SelectionBox` layer/stimulus dropdowns shown unparented in projector-row creation (`ProjectorReference.render_fields` called `setVisible(True)` before grid attach; same path on value changes). The no-projector relaunch had not exercised it.
- Fix: removed early visibility calls; `arrange` attaches then shows. Earlier label fix remains (ARCH-002).
- Validation: regression covers four rows, value edit/apply, type replacement, rebind, duration update with no detached Show event; compact reference test passes. Visible launch with four simulated projectors recorded only `DashboardWindow`. Ruff, format, mypy pass; no physical projector/managed backend action.

### 2026-10-04 [gui] Automatic display identification investigation

- `gui-implementation`; owner rejected the manual Windows-ID matching workflow. Read Microsoft QueryDisplayConfig/DisplayMonitor docs and Q&A.
- Finding: read-only enumeration gave primary `DISPLAY9` as path 1 and projectors paths 2-5, while Settings screenshot labels the primary 5 with other ordering. Neither path position nor GDI suffix is the Settings ID; no documented API gives the exact number. Reliable alternative is an application-owned ID matched to each physical target by an on-screen overlay.
- Asked owner to choose automatic physical identities vs approximate Settings digits. No new algorithm or hardware output applied; manual dialog remains in source, recorded as pending in TODO/runtime report.

### 2026-10-04 [gui] CephVR-owned projector display indices

- `gui-implementation`; owner chose GUI-owned indices. G01 revision 70/root register, runtime report/TODO replace the rejected manual rule. Secondary screens sort by desktop x/y and get local indices 1..N, used by table, layout, timing and status; assignments/Use stay keyed by display identity. Removed manual dialog, saved-number state and unused path-index helper/tests (ARCH-002).
- Validation: 4 targeted tests; wider projector run 7 pass with 3 unrelated temp-fixture setup errors (temp denied). Ruff/format, mypy (67 GUI files), boundaries (520 modules, 0 violations), whitespace pass. Native construction gave IDs 1-4 at (-3840, 0), (-2560, 0), (-2280, 720), (-1280, 0). No hardware command or optical check; no full-suite pass (earlier native Qt access violation).

### 2026-10-04 [gui] [visual_stimulus] Rig plot labels and calibration launch investigation

- `gui-implementation`, `projector-calibration-launch`; reviewed G01/V01/V15/V19 and CephVR1.0 calibration. G01 revision 71/root register, runtime report, plot code remove in-plot labels and Labels toggle (legend and four 2x2 toggles kept); removed per-face identifier state (ARCH-002).
- CephVR1.0 used a world-phase multicolor grid with Disconnect. CephVR2.0 GUI has no managed projector command and V19 Idle is uniform; asked owner for output ownership choice before adding a launch path.
- Validation: 2 focused tests; Ruff, format, mypy (67 GUI files), boundaries (520 modules, 0 violations), `git diff --check` pass. No projector image presented, no optical calibration verified.

### 2026-10-04 [gui] Epoch asset paths and parameter-specific batch editing

- `gui-implementation`; G01 revision 72/root register, runtime report, forms updated. Typed/pasted prepared paths validated within the Assets folder (full path shown when focused); texture picker "Loaded" line and four redundant headings removed; Batch edit selects a family-supported parameter with its value editor/asset picker, atomic Apply and pending-edit protection kept. ARCH-002: no new owner/dependency.
- Validation: 7 focused tests (path paste, missing-path rejection, family-dependent options, atomic edit); Ruff, format, mypy (67 GUI files), boundaries (520 modules, 0 violations), whitespace pass. Two sandboxed pytest attempts failed on temp permissions before rerun. No managed backend or rig acceptance.

### 2026-10-04 [gui] [visual_stimulus] Rig-specific calibration arena asset

- `projector-calibration-launch`; owner selected V01's managed renderer. Reviewed V15/V17/V18, GLB importer, G01 screen corners. V18 revision 3/root register and arena contract allow a dedicated offline calibration exporter: bounded unlit GLB from version 2 GUI calibration JSON (10 mm grids, center crosses, face names, tank outline). `C:\Users\ReiterU_PC\Desktop\rig_geometry.json` (120 x 166 x 110 mm tank) produced ignored `cephvr-data/calibration/rig_geometry_grid.glb` and a 60-second arena program.
- Validation: 1 focused test; GLB reader parses 55,688 bytes/806 triangles; program parser accepts the trial. Ruff, format, mypy (68 GUI files), boundaries (521 modules, 0 violations), whitespace pass. JSON has unset projection limits/corrections; no saved controller config; GUI lacks managed Launch/Stop; no projector output or optical calibration verified.

### 2026-10-04 [gui] Independent projector values in Batch edit

- `gui-implementation`; G01 revision 73/root register, runtime report updated. Batch edit shows layer/value choice per projector row plus one rig-wide arena row; a changed row patches only its projector; all row patches validate before one commit; target/parameter switching with a pending edit stays blocked; open asset pickers close on rebinding. Reused `apply_batch`; row widget extracted (ARCH-002).
- Validation: 4 focused tests (independent edits, epoch-level Duration, lock, one failing row leaves program unchanged; a fixture lacking Assets folder fixed). Ruff, format, mypy (69 GUI files), boundaries (522 modules, 0 violations), whitespace pass. No managed backend/rig acceptance.

### 2026-10-04 [gui] [visual_stimulus] Diagnostic calibration package preparation

- `projector-calibration-launch`; owner approved GUI face assignments as binding source, explicit diagnostic identity meshes and computed diagnostic projection limits. G01 revision 74/root register add Prepare calibration files: needs four unique enabled assignments, matches display rectangles to native monitor interfaces, writes GLB, arena program, V15 display profile and four full-viewport identity meshes under the Protocol Assets folder; limits derive from rig dimensions for this package only; no projector command.
- Validation: 3 focused tests (bundle export, unmatched-display refusal); owner JSON parses and generates the 55,688-byte GLB. Ruff, format, mypy (70 GUI files), boundaries (523 modules, 0 violations), `git diff --check` pass. No owner-specific display profile written (assignments unavailable); no projector output or optical alignment tested. Managed Launch/Stop open.

### 2026-10-04 [gui] [visual_stimulus] Manual calibration lifetime correction

- `projector-calibration-launch`; owner rejected the 60-second trial and requires manual open/close; V06 (finite durations) and V19 (uniform Idle) cannot express that. G01 revision 75, V01 revision 13, V18 revision 4 define a controller-authorized untimed diagnostic presentation on the resident V01 renderer, outside trial timing/recording, ending on Close or required cleanup.
- Prepare now exports only the GLB and diagnostic display/identity profiles; deleted the obsolete ignored 60-second program file. No projector command sent.
- Validation: 2 focused export tests; Ruff, format, mypy (70 GUI files), whitespace pass. Managed Launch/Close and rig output outstanding; architectural acceptance is not implementation or optical evidence.

### 2026-10-04 [gui] [visual_stimulus] All-output calibration control state and per-face centering mappings

- `projector-calibration-launch`; owner chose simultaneous calibration on all four projectors with Launch becoming Close. Reviewed G01/V01/E08: GUI is a local review frontend with no controller client. G01 revision 77/root register specify confirmed state. Launch/Close button and outward signals added (Launch prepares the bundle; disabled until a managed client reports availability; label changes only on confirmed state). Diagnostic meshes apply each face's scale, pixel offsets and inverse axes (default identity, overflow rejected).
- Validation: 2 focused tests; Ruff, format, mypy (70 GUI files) pass. No controller transport/diagnostic RPC added: no projector activation, Close or centering evidence. TODO open.

### 2026-10-05 [gui] Review current GUI after rig synchronization

- `gui-implementation`; HEAD 3af4289814927c1c3fdc4251731ef894a49a1489, tree clean; reviewed changes since ff694b1 and G01 revision 77. No code/test edits. Expected features present; native Dashboard/Protocol/Projectors views (simulated devices) showed no new visual issue. Actual rig output unavailable locally.
- Validation: full GUI suite 143 passed, 2 failed (70.48s); failures assert superseded mode-above-duration/equal-width, vs G01 shared row with proportional widths; recorded in existing task. Ruff/format (71 files), mypy (70 GUI files), boundaries (523 modules, 0 violations) pass. 505-line camera owner: separate discovery/check if substantially expanded. No Windows/hardware acceptance.
- Screenshots deleted; GUI reopened `--review --simulated-devices`; report, TODO and text evidence updated. Preview, calibration transport, managed adoption tasks open.

### 2026-10-05 [gui] [visual_stimulus] Advanced settings alignment and retained-state defaults

- `gui-implementation`; read G01/V07/V24, CephVR1.0 helpers. G01 revision 78/root register. New presets default reset false (imports unchanged); Retain, opacity, feedback ordering aligned to Layer at both widths; + Input signal defines a channel and starts a mapping, + Feedback uses an existing declaration; obsolete epoch-header assertions corrected.
- Linking: V1 coherent mapping approximates yaw lever arms with half source size; not adopted. Asked clockwise Left/Right convention and whether source motion replaces target motion or combines with feedback; no link selector/schema/runtime added. Owner reply: clockwise Bottom means Right front-to-back, Left back-to-front when linked; V02 revision 12/root register records only that convention. Feedback writer question remains open; no link runtime pass claimed.
- Validation: 160 GUI/client-state/compiler tests (59.46s; 147 GUI); Ruff/format 71 files, mypy 70 GUI files, boundaries 523 modules (0 violations), links/whitespace pass. No Windows/hardware/link-motion acceptance. Linked to behavior pending.

### 2026-10-05 [gui] [visual_stimulus] Unified input and parameter Control editor

- `gui-implementation`; G01 revision 79/root register. One + Control action replaces + Input/+ Feedback: pick or define an input inline, compatible parameter and gain/offset response, commit declaration and binding together; Cancel/invalid preserve the trial; removal labelled Remove control. ARCH-002: focused local draft, existing validation reused.
- Pending: explicit ranges await owner's clamp-vs-extrapolation choice (V24 unbounded gain/offset unchanged); linked movement awaits source/target feedback ownership answer. Neither marked implemented.
- Validation: 162 tests pass (59.57s; 149 GUI) with two new atomic Control scenarios; Ruff/format 72 files, mypy 71 GUI files, boundaries 524 modules (0 violations) pass. No Windows/hardware or range/link-motion acceptance. Native inspection done; reports/TODO keep open questions.

### 2026-10-05 [gui] [visual_stimulus] [tracking] Advanced card, closed-loop controls and fades

- `gui-implementation`; G01 revision 80/root register. One Advanced card beneath each projector row: Retain, disabled Linked to selector, responsive fade fields, controls. + Control offers three canonical Tracking channels only in Closed-loop; arena longitudinal/lateral share one planar binding, yaw independent. Fades use V05 opacity keyframes (zero duration disables, nanosecond timing, bounded by epoch); duration edits move fade-out. Imported custom functions unchanged. Opacity editing removed. V02 ownership and V24 2D conversion remain open. ARCH-002: focused fade/appearance helpers.
- Validation: 165 tests (57.28s; 152 GUI); Ruff/format 74 files, mypy 73 GUI files, boundaries 526 modules (0 violations), 245 links/anchors, whitespace pass; intermediate failures corrected. Native narrow clipping fixed by reflow. No managed input delivery, physical output, link runtime or Windows/rig acceptance.

### 2026-10-05 [gui] [visual_stimulus] [tracking] Layer drafts, separate Controls and 200-epoch responsiveness

- `gui-implementation`; G01 revision 81/root register. Advanced header opens a separate Control draft (closed-loop Texture/Looming only; unsupported 2D Save disabled); empty layer slots need no picker; settings survive switching. ARCH-002: focused layer and bounded immutable timeline-view helpers, skipped unchanged validation; no threads/dependencies. GUI read/save guards now reuse the 16MiB backend default after a 200-epoch/eight-layer file exceeded the 1MiB guard. 2D conversion, linking ownership, clipping questions unanswered.
- Validation: 170 GUI/client/compiler pass (68.02s); 4 configuration checks pass, known pacing-key loader failure excluded and open. Ruff/format 78 files, mypy 77 files, boundaries 528 modules (0 violations) pass. Benchmark 200 epochs/four projectors/two layers: 3.2MB JSON, parse 463ms, first UI 333ms, warm trial switch 12.63ms median; offscreen local only, not hardware/full-load acceptance.
- Variation-column clipping repaired; test textures under /private/tmp/cephvr-file-review-assets. Managed delivery, linked runtime, rig acceptance open.

### 2026-10-05 [gui] [visual_stimulus] Advanced action placement and scoped variation rules

- `gui-implementation`; G01 revision 82/root register. +Control sits inside Advanced below settings, hidden during its draft; entries added only on Add control. Variation rules card: header Enable, separate Projectors/Layer/Parameter/Method/Values, one or all projectors, common layer ordinal or all layers, aligned removal; Combine removed (equal-length lists pair by position); stale-layer identities rejected. ARCH-002: `BatchVariationRow` extracted from BatchCreate; shared grid for exact alignment.
- Validation: full suite 171 passed (67.60s); six focused checks (4.68s); Ruff/format 77 files, mypy 76 GUI files, boundaries 529 modules (0 violations) pass. No rig or managed Tracking delivery. Duplicate heading removed; earlier conversion/linking/range decisions pending.

### 2026-10-05 [gui] [visual_stimulus] [tracking] Layer menu, matching variations and planning preview

- `gui-implementation`; G01 revision 83/root register. Layer menu (Add/Remove/Move up/down/Advanced); stimulus-matching variation catalogue (Rotation, no Width/Height/Opacity); values pair in entered order; independent epochs materialized atomically. Timeline Preview (separate planning window): snapshots enabled screens, playback, seek, epoch navigation, speed, pure V07 boundary state. ARCH-002: focused preview modules, bounded caches, active-only decoders; close releases resources. Arena approximate; codec playback and optical equivalence unverified. Conversion/linking/range choices open.
- Validation: 178 GUI/client/compiler tests (67.97s); mypy 84 GUI files; other checks in dated timeline-preview evidence. Intermediate failures (outdated button expectations, fixtures, Qt deleted-object assertions, typing) corrected. Existing pacing loader issue and managed/rig acceptance pending.

### 2026-10-05 [gui] [visual_stimulus] Rig-space trial preview

- `gui-implementation`; source review of CephVR1.0 `_TankView`. G01 revision 84/root register: one rotatable tank view replaces flat screen cards; reuses TankDiagram via a screen-paint hook, composes enabled outputs onto planes, keeps inactive outlines and labels, caches reduced-resolution frames (invalidate on seek/playback/media). Unconfigured geometry prompts Devices configuration; no guessed dimensions.
- Validation: 166 GUI tests (68.32s); two focused (2.13s); Ruff/format 86 files, mypy 85 GUI sources, boundaries 538 modules (0 violations) pass. Native four-screen preview inspected with illustrative dimensions, not saved calibration. No live Tracking, physical outputs, optical equivalence or codec acceptance.

### 2026-10-05 [gui] [visual_stimulus] Two-sided planning screens

- `gui-implementation`; G01 revision 85/root register. Enabled screen textures/labels paint from either side (depth occlusion kept, disabled screens outlines); preview-only culling removed (ARCH-002).
- Validation: 2 focused tests (1.96s), geometry test checks white pixels from four hemispheres; Ruff/format 86 files, mypy 85 sources, boundaries 538 modules (0 violations) pass. Native view inspected. No physical projection or rig acceptance.

### 2026-10-05 [gui] [visual_stimulus] Calibration-aware planning preview

- `gui-implementation`; G01 revision 86/root register requires exporter corrections after surface composition. Existing mapping reused as public helper (ARCH-002); V15 runtime policy unchanged. Snapshot scale, offset, axis inversions; display resolutions normalize pixel offsets; invalid/out-of-bounds corrections and offsets without resolution report per-screen errors; correction applies to cached reduced-resolution frame.
- Validation: 168 GUI tests (68.17s); focused pair (1.33s) covers inversion, scale/offset, exporter correspondence, errors; Ruff/format 86 files, mypy 85 sources, boundaries 538 modules (0 violations) pass; float comparison fixed.
- Runtime warp/mask/photometric profiles, optical rig equivalence, codecs, live Tracking remain outside local planning evidence.

### 2026-10-05 [gui] [visual_stimulus] Clean preview presentation

- `gui-implementation`; G01 revision 87/root register; display-only. Planning text, enabled-projector text, legend and subject marker removed (subject stays in projection math); screen labels, calibration, playback remain. ARCH-002: removed unused description widget/legend drawing.
- Validation: 4 focused checks (1.30s); Ruff/format 86 files, mypy 85 sources, boundaries 538 modules (0 violations), whitespace pass. Native view inspected. No runtime/rig acceptance.

### 2026-10-05 [gui] [visual_stimulus] Preview left/right orientation and screen overlap

- `gui-implementation`; source confirms Left is low-X, Right high-X; old home angle 155 degrees put them on opposite sides; screen depth painting was reversed. G01 revision 88/root register. Home azimuth now 25 degrees; shared TankDiagram paints surfaces in ascending depth. Face assignments/calibration unchanged; no new dependency/schema.
- Validation: 6 focused checks (1.65s) with home-angle, label-order and plane-side assertions; Ruff/format 86, mypy 85, boundaries 538 modules (0 violations) pass. Native view inspected. No physical calibration/output or rig acceptance.

### 2026-10-05 [gui] [visual_stimulus] Random range variations

- `gui-implementation`; G01 revision 89/root register accepts authoring-time sampling; runtime/Setup seed ownership unchanged. Random method adds Minimum/Maximum/Precision/Epochs plus refresh icon; uniform sampling with replacement on grid multiples; numeric/input-size guards, 1-512 count, paired-length checks; cached per-row samples keep preview/commit stable; concrete values saved in JSON; categorical At end Values-only. ARCH-002: bounded Decimal sampler, no dependencies.
- Validation: 170 GUI tests (70.28s); 4 focused (3.09s); Ruff/format 87, mypy 86, boundaries 539 modules (0 violations) pass. Fixture helper names, a 2-pixel button height mismatch and nullable Qt style fixed. No runtime random distribution, scientific control or rig capacity acceptance changed.

### 2026-10-05 [gui] [visual_stimulus] Random count follows batch repetitions

- `gui-implementation`; G01 revision 90/root register. Separate Epochs control removed; random count derives from batch Repetitions (100 repetitions create 100 random epochs, no second multiplier). Mixed Values/Sweep lists repeat in entered order with random draws per epoch. Existing 2000 expanded-epoch cap for random; nonrandom 512-variant bound remains; cache keyed on count. ARCH-002: duplicated input removed.
- Validation: 170 GUI checks (91.46s); 4 focused (19.40s) for 100/10/999 counts, stable values, resampling, mixed lists. First concurrent full run 169 pass/1 fail (older fixture); final rerun passes. Ruff/format 87, mypy 86, boundaries 539 modules (0 violations), 244 links pass. No hardware/performance acceptance.

### 2026-10-05 [gui] [visual_stimulus] Two-row variation layout

- `gui-implementation`; G01 revision 91/root register. Row 1 Projectors/Layer/Parameter plus removal; row 2 Method with Values or Random range/precision. `BatchVariationRow` uses one shared grid; nested random layout and dynamic spans removed (ARCH-002); no generation/runtime change.
- Validation: 2 owning checks (1.55s); cross-row height assertion updated; mypy loop-variable collision fixed; Ruff/format 87, mypy 86, boundaries 539 modules (0 violations) pass. Full 170-test result is prior evidence; suite not rerun. No rig validation.

### 2026-10-05 [gui] [visual_stimulus] Remove random resample button

- `gui-implementation`; G01 revision 92/root register removes manual resampling; cached draws change only with range/precision/resulting count. Removed button, native icon dependency and resample method (ARCH-002); owning test changes precision to exercise automatic redraw.
- Validation: 4 focused checks (16.42s); Ruff/format 87, mypy 86, boundaries 539 modules (0 violations), whitespace pass. Prior full 170-test result historical. No hardware checks.

### 2026-10-05 [gui] [visual_stimulus] Final frontend commit cleanup and rig handoff

- `gui-implementation`; final trim before owner commit. Removed obsolete variation wrapper and redundant sizing; docstrings added; batch epoch allocation reuses collected IDs (1000 allocations match original numbering). Narrow clipping of advanced controls fixed via reserved minimum height (G01 revision 93/root register); full-width anchor attempt reverted.
- Cleanup: removed 173 repository temporary scripts/JUnit exports/duplicate outputs and 75 local temporary files; hashes, unique native/performance results, test textures, all 170 GUI tests retained; links and launch guide updated.
- Validation: GUI/client/compiler 183 passed (69.28s); focused 4, 23, 1 pass; Ruff/format 90 files, mypy 88 sources, boundaries 539 modules (0 violations), 433 links/anchors pass. Configuration run 187 passed/1 pre-existing failure (81.46s): `test_default_and_file_policy_values_are_typed` rejects `presentation.pacing_refresh_hz`; not weakened; excluded from combined pass. Changes uncommitted. Windows display, codecs, managed transport, Tracking/linked-control and physical output remain follow-ups.

### 2026-10-05 [gui] [controller] [acquisition] Windows GUI and camera entry review

- `gui-implementation`, `camera-preview-gui-binding`, `devices-narrow-overflow`; reviewed G01/A10/E03/E08/E15. Rig: Qt saw only the Dell 1920x1080 display, no projectors; both Basler serials enumerated and Test enabled opened/identified/closed them without capture or settings writes; stale sample-inventory message fixed.
- Findings: managed launcher requires missing `cephvr.gui.main`; review Connect/Preview are local state. Preview wiring tracked via A10 path. 720px Devices reflow check fails (48px overflow in test; Camera 28px, Projectors 164px). No projector, capture or frame display claimed.
- Validation: Ruff (87 files), mypy (86 modules), boundaries (539 modules, 0 violations) pass; broad GUI run hit Qt access violations/temp errors; narrow test 2 passed, 1 failed; camera/controller/client groups failed on temp permissions, no backend pass. Two COM ports enumerated unopened; Protocol/MCU/Projectors/SpikeGLX/Tracking views inspected at 1280x800. `.pytest-gui-current` resisted cleanup (Access denied), Git-ignored. TODO open.

### 2026-10-05 [gui] [controller] [acquisition] [shared] [repo] Managed camera control and native preview increment

- `gui-implementation`, `camera-preview-gui-binding`; owner authorized backend wiring incl. live preview. ARCH-002: reused WatchState client, controller camera RPCs, A03 ring; viewer coalesces one latest frame. Added supervisor GUI credential, observer-before-control session, managed GUI bootstrap/reconnect bridge, camera Start/Stop/Attach, viewer/consumer reports, ring reader, Qt image window. Non-camera editors stay disabled; Connect editing-only and camera/PFS updates open. Windows fixes: named-mapping attach rights, pypylon inactive controls/private copy.
- Validation: client/credential 12 passed; controller camera/ring 30; focused 11; native 2x2 A03 read/conversion/release passed after three diagnostic failures. Ruff, format, Windows mypy, boundaries, whitespace pass. No real camera frame, throughput, managed launch or projector output. Acquisition defaults leave backend disabled, external trigger COM/pin/input unset; asked owner for wiring or a temporary free-running preview test.

### 2026-10-05 [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [shared] Managed launch diagnosis

- `camera-preview-gui-binding`, `gui-implementation`, `visual-renderer-startup-deadline`; E03/E08/A10 launch check in an isolated owner-only runtime (user-profile runtime DACL rejected; untouched; isolated credentials/logs removed). Removed double-close of bootstrap handles in four entries, added Tracking policy descriptor, confirmed endpoints against launch records; ring viewer reports failed vs released exclusively. No timeout/policy change.
- Result: launcher reached the renderer but safety triggered `VISUAL_STIMULUS_WORKER_FAILURE: original Visual Stimulus peer deadline expired`; second launch identified `ReportWorkerHeartbeat` as the expiring call (pre-submission vs coordinator response unresolved). Deadline kept, method added to error. E04 emergency output retained; no camera command, frame, Setup or output.
- Validation: managed intent/ring viewer 2 passed; client/shared 12; Visual Stimulus/supervisor 242 passed, 1 existing pacing-key loader failure; Ruff, mypy (102 sources), boundaries (542 modules, 0 violations), whitespace pass. Full managed startup and rig acceptance pending.

### 2026-10-05 [gui] [acquisition] [controller] Arduino Uno diagnostic investigation

- `mcu-managed-connection-and-io`; owner put MCU connection/per-I/O tests first, authorized extending protocol and firmware, identified COM8 Uno. A11/G01/MCU wire contract define only two camera pulse outputs; GUI pin buttons are local intents. Acquisition stays sole serial owner (ARCH-002).
- Rig evidence: COM8 Arduino Uno (VID 9025, PID 67), COM9 Prolific. Bounded CephVR2 CAPS/STATUS probe on COM8 failed after deadline (close unconfirmed; process exit released handles). Legacy PING returned `OK READY dual_camera_projector_sync`, matching the CephVR1.0 sketch: legacy firmware, not a CephVR2 handshake or pin test. No output command, pin drive or flashing.

### 2026-10-05 [acquisition] [gui] [controller] Uno protocol and firmware increment

- `mcu-managed-connection-and-io`; owner lifted the firmware deferral for COM8; A11 keeps installation manual. ARCH-001 revision 19/A11 revision 36/MCU wire contract describe protocol v2 diagnostics. Added v2 diagnostic parsing, serial-owner/bridge operations, fresh CAPS input-pin capability, regenerated protobuf outputs, deadline cleanup that attempts OS close after an expired probe. Uno sketch in `firmware/uno`: Timer1 camera pulses, 2 s HIGH Trial state test, D2/D3 interrupt flip edge count, 2 s stop, watchdog LOW. Managed commands, typed GUI pin settings, installation open.
- Validation: acquisition MCU/config 28 passed (unsupported flip pins rejected); Arduino AVR 1.8.8 Uno compile passed (10,920 flash, 1,112 SRAM bytes); Ruff, mypy (9 files), boundaries (542 modules, 0 violations), `git diff --check` pass. 585-line serial owner stays cohesive. No COM8 v2 handshake, edge test, GUI command or preview.

### 2026-10-05 [acquisition] [gui] [controller] COM8 firmware upload and host handshake

- `mcu-managed-connection-and-io`; owner authorized upload/wiring. ARCH-001 revision 20 records one manual installation under A11; application-assisted flashing stays deferred. Arduino CLI identified COM8 as Uno; avrdude saved previous flash to dated evidence; protocol-v2 image uploaded with `--verify`, success. Direct CAPS returned protocol 2. Owner CAPS retries timed out: pySerial timeout updates cost about 63 ms per request; adapter now uses short native polls and bounded chunk reads. Real SerialOwner then returned matched CAPS and STATUS on COM8, camera outputs stopped, zero malformed/unmatched replies; handle closed.
- Validation: MCU serial tests 17 passed; Ruff and Windows mypy pass. Hashes, size, readback in `reports/mcu-evidence-2026-10-05`. No CONFIGURE, DIAG_START, ON, pin test, preview or managed GUI command. Front-door transport and typed pin adoption open.

### 2026-10-05 [gui] [controller] [acquisition] Managed MCU diagnostic wiring

- `mcu-managed-connection-and-io`; serial ownership stays in acquisition; reused controller authority, configuration revision and device-status path (ARCH-002). Added typed Trial state/Projector flip pin settings, Configuration-phase controller/acquisition diagnostic RPCs, status projection, managed GUI Save pins, Test connection, Test/Stop, results. Default COM8; physical pins unset; wiring table/rig checklist state the missing mapping and voltage checks before driving outputs.
- Validation: acquisition/controller/client MCU 52 passed; offscreen MCU GUI 5 passed; Ruff, format, Windows mypy (10 files), boundaries (543 modules, 0 violations), whitespace pass. Broader GUI run hit a Qt teardown access violation after two earlier failures; no broad GUI pass. COM8 handshake passed previously. No full managed GUI command, pin, camera pulse or preview.

### 2026-10-05 [acquisition] [gui] Owner-assigned pin defaults and bounded D2 input test

- `mcu-managed-connection-and-io`, `camera-preview-gui-binding`; owner supplied Trial state 9, Projector flip 2, behavioral camera 10, tracking camera 11. Bound D9/D2/D10/D11 in defaults/typed settings; panel projects saved trigger pins/rates; wiring guide/checklist updated; MCU handlers extracted from the GUI entry (ARCH-002). No trigger source or camera setting inferred from pins.
- Rig: COM8 CAPS/STATUS confirmed protocol 2, D2/D3 input capability, cameras stopped. D2 `DIAG_START` active with zero edges; after 2.1 s `DIAG_STATUS` inactive, zero edges; COM8 closed. Proves firmware command/timeout response only, not a flip edge or electrical level; receiver channels, ground, voltage uninspected. D9/D10/D11 not driven.
- Validation: acquisition/controller/client 52 passed; MCU GUI 6 passed; Ruff/format (102 formatted), mypy (4 sources), boundaries (544 modules, 0 violations), whitespace pass. No full managed GUI, Trial state output, camera pulse or preview.

### 2026-10-05 [gui] [controller] [acquisition] Save accepted configuration before managed GUI close

- `gui-implementation` under E07/G01; owner clarified the projector was off during the D2 check, so zero edges was expected, not a failure. Managed window defers close until an exact controller `SaveConfigurationHistory` result; claims the lease first if none held; if another operator holds it or save fails, offers Retry or Close without saving. Controller remains sole atomic writer/startup reader of `config/last_configuration.json`. Evidence/report/checklist record the projector-off condition.
- Validation: native GUI tests cover intercepted close and finishing after confirmed save; authenticated loopback test confirms controller writes subject/experiment and format version. Other checks in the current frontend report. Live managed close/restart pass pending (launcher hits the retained Visual Stimulus heartbeat failure). Review-only local drafts are outside controller history.

### 2026-10-05 [gui] [repo] Retain local design-review drafts separately

- `gui-implementation`; G01 revision 94 owns separate local persistence for review drafts (never in E07 controller history). One focused capture/restore module reuses canonical Program validation (ARCH-002).
- Normal review-window close atomically saves subject, camera/MCU assignments, recordings, trial programs, projector geometry/timing and SpikeGLX drafts to ignored `config/review_draft.json`; launch restores after inventory discovery. Save failure offers Retry/Close; malformed prior draft is preserved unless replaced. Not Setup-ready configuration.
- Validation: focused managed/review GUI and authenticated controller persistence 10 passed, plus one malformed-draft read check; Ruff (94 formatted), Windows mypy (5 files), boundaries (546 modules, zero violations), diff whitespace passed. Close/reopen with real devices remains to be observed on the rig.
- Refs: `scripts/start_gui.py`

### 2026-10-05 [spikeglx] Rig connection/control preflight

- `spikeglx-rig-connection-control`; owner requested live connection/control testing under E12.
- Findings: `ipconfig` showed two linked Ethernet adapters with link-local addresses; `arp -a` showed no ephys neighbor. Saved config and GUI draft have no ephys host. No SpikeGLX SDK in repository/CephVR Python environments; `cephvr.synchronization.client` absent. GUI Test connection is review-only. Owner asked for dedicated-link address and server status.
- Limits: local source/config inspection and network inventory only; no remote connection, SDK call, run-name change, startRun, stopRun or recording. Live control and E12 acceptance open.

### 2026-10-05 [gui] [acquisition] Wire local rig-review MCU diagnostics

- `mcu-managed-connection-and-io`; G01 revision 95 permits local review to use A11's exclusive serial owner for explicitly requested bounded tests.
- Connected COM Test connection and per-pin Test/Stop to a Qt worker (matched firmware results, numeric Uno pin normalization, requested camera rates, two-second status readback, close-time stop/port release). Sample fixtures stay command-free. Updated runtime/acquisition reports and rig checklist.
- Verification: focused MCU/review GUI and acquisition serial tests 56 passed; Ruff, Windows mypy, boundaries, whitespace passed. Live COM8 worker test: firmware `cephvr2_uno_1` protocol 2, outputs stopped, D2 input diagnostic active at zero then inactive with 120 rising edges. D9/D10/D11 not driven; D2 edge source and electrical compatibility not established. Initial sandbox pytest failed on temp-directory permissions.

### 2026-10-05 [spikeglx] Official SDK live readback

- `spikeglx-rig-connection-control`; owner authorized a connection attempt to the ephys computer.
- TCP to `169.254.240.108:4142` succeeded; official SDK checkout `9169309e3f3cd0bfaa7c8dacc5b16288948bbfa3` read SpikeGLX `v20251218 api v4.1.3`, `isRunning=false`, `isSaving=false`, `C:/SGL_DATA`; `getRunName` returned "Run parameters never validated." Corrected read-only rerun exited zero. Details: [dated evidence](reports/spikeglx-evidence-2026-10-05/README.md).
- Limits: mapping reference targets `v20260901`; no controller client exists. No remote mutation or recording. E12 Setup and bounded start/stop await validated acquisition settings and matching mapping review. Disposable SDK checkout removed; doc links and `git diff --check` passed.

### 2026-10-05 [gui] [launcher] Separate simulated review and managed runtime launchers

- `gui-implementation`, `mcu-managed-connection-and-io`; G01 revision 96: review for layout iteration, managed runtime for implementation tests.
- `scripts/start_gui.py` always launches isolated fixture devices (simulated cameras, four displays, Arduino entry, no COM enumeration); new `scripts/start_runtime_gui.py` invokes the Windows launcher with repository environment/config. Managed startup inventories real cameras, secondary displays and COM ports read-only before control.
- Validation: focused GUI inventory/review 41 passed; mocked script launches chose intended modules/arguments; Ruff, Windows mypy, boundaries, whitespace passed. Full managed launch and physical device checks not run; renderer startup deadline finding remains open.

### 2026-10-05 [spikeglx] Save observed command-server endpoint

- `spikeglx-rig-connection-control`; E12/E14 assign command-server address/port to operator settings.
- Saved observed `169.254.240.108:4142` in `config/backends/synchronization_config.toml`; reconciled rig checklist, dated evidence and task status. Dedicated-interface/firewall restriction still needs verification.
- Validation: TOML parsed; link-local IPv4, port 4142, policy version 5 match; `git diff --check` passed. No further SDK query, client, run-name mutation or recording. Link-local address may change; recheck reachability before Setup.

### 2026-10-05 [spikeglx] Prepare operator handoff for start/stop test

- `spikeglx-rig-connection-control`; asked what to set up after "Run parameters never validated."
- Manual review: `File > New Acquisition` opens configuration; `Verify | Save` validates/saves without starting. E12's writing gate needs Immediate gate/trigger modes with recording enabled; operator selects devices/streams, saved channels, data directory and unique test run name. Agent must still review installed `v20251218` mapping before start/stop; controller client absent.
- Limits: documentation and contract review only; no hardware query, config edit or recording.

### 2026-10-05 [gui] [launcher] [visual_stimulus] Investigate VS Code managed GUI startup

- `gui-implementation`, `visual-renderer-startup-deadline`; added `.vscode/launch.json` profiles for simulated review and managed runtime (repository `.venv`, integrated terminal).
- Rig finding: runtime startup rejected the inherited DACL on the user-profile CephVR runtime credential directory (`icacls`, `verify_owner_only`); `ensure_owner_only` repaired it. Next launch created all roles; the renderer worker exited first, then safety shutdown. Offscreen managed GUI constructor found two cameras and two COM ports. A heartbeat timestamp adjustment did not help and was reverted.
- Limits: traces retained in dated GUI startup evidence. No Setup, capture or output diagnostic. Runtime GUI still exits before implementation testing; renderer heartbeat deadline and shutdown cleanup issue remain open.

### 2026-10-05 [spikeglx] Live SDK start/stop smoke test

- `spikeglx-rig-connection-control`; owner requested a start/stop attempt. Preflight found `manOvInitOff=true`; owner unchecked **Disable recording at run start** and Verify | Save; readback confirmed `manOvInitOff=false`, idle.
- Official SDK at `169.254.240.108:4142`, source-reviewed mapping at tag `Release_v20251218-api4` (`c936965dfb679c3d4ceec19956e633748c3cfea5`): set/read back run `CephVR_Test_20261005_163039`, startRun once (360 ms), isSaving true, OneBox count 0→4079, stopRun once (SDK success). isRunning stayed true about two seconds, so the script exited 1 (stop unconfirmed); a fresh connection confirmed isRunning/isSaving false. Evidence: [dated evidence](reports/spikeglx-evidence-2026-10-05/README.md).
- Limits: stop delay not measured; no native-file content/closure, pulse roles, physical timing, interface/firewall restriction or controller lifecycle verified. Test name remains selected; files may exist under `C:/SGL_DATA`, not removed. SDK checkouts removed; links and `git diff --check` passed. Smoke test complete; full E12 integration deferred under ARCH-001.

### 2026-10-05 [gui] [launcher] [visual_stimulus] [supervisor] Restore managed startup in VS Code

- `visual-renderer-startup-deadline`, `gui-implementation`; ARCH-002 kept lifecycle evidence in the existing worker report bridge/coordinator aggregate.
- Traces: first renderer heartbeat failed E08 lifecycle validation; coordinator idle cleanup revision failed supervisor catalogue admission before Setup registration. Added an initial configuration phase, setting-up phase on worker resource and coordinator Setup reports, lifecycle forwarding, and dropped the idle cleanup revision; coordinator regression covers the startup heartbeat. VS Code F5 profiles disable child debugger attachment.
- Verification: bounded live managed launch kept all roles and the Dashboard beyond 25 seconds with repeated accepted renderer heartbeats; the lingering launcher was terminated after verification. No Setup, capture or output. Visual Stimulus tests 22 passed (sandbox run: 5 `tmp_path` errors, 17 passes); Ruff, Windows mypy (119 files), boundaries (547 modules, zero violations), launch JSON, whitespace passed. Open: intermittent native process-inspection error, post-Setup phases, normal GUI-close launcher exit. [Startup evidence](reports/gui-startup-evidence-2026-10-05/README.md).

### 2026-10-05 [gui] [launcher] [supervisor] Release diagnostic application guard

- Owner hit `application instance already running`. Elevated inventory found a launcher under the earlier Codex diagnostic shell with supervisor, controller and backend descendants; no GUI process. E08 says GUI closure leaves the application running, correcting the previous entry's "unresolved shutdown failure" characterization.
- Verified exact launcher PID/parent/command line, stopped only it, its Job descendants exited, then acquired and released `Global\\CephVR2-application` in a read-only probe; free for next launch. No hardware or controller command. Docs, runtime report and TODO now distinguish GUI closure from explicit shutdown; same-generation GUI relaunch still missing.

### 2026-10-05 [spikeglx] [controller] [gui] Wire managed connection diagnostic

- `spikeglx-controller-integration`; ARCH-001 revision 21/root register records bounded SpikeGLX client wiring. One read-only diagnostic owner over existing controller gRPC and GUI bridge; the E12 lifecycle port stays unavailable.
- Controller loads saved endpoint and the official SDK wrapper/DLL from an ignored local install, one outstanding diagnostic with five-second bound, authenticated read-only RPC. Devices/SpikeGLX Test connection shows version, run state, name and data directory. Added SDK install guidance. No Setup, startRun or stopRun path.
- Validation: rig readback through new controller code returned `SpikeGLX v20251218 api v4.1.3`, idle/not-saving, `CephVR_Test_20261005_163039`, `C:/SGL_DATA`. 19 Protobuf bindings generated; 3 GUI SpikeGLX and 6 authenticated client tests passed; Windows mypy (98 files), Ruff, boundaries (547 modules, zero violations), `git diff --check` passed (sandbox runs failed on access controls; elevated reruns passed). Managed launch exited before the button could be clicked; retry ended `JOB_INSPECTION_FAILED`/child-channel EOF. Button response, E12 lifecycle, pulse inventory and rig acceptance open; Qt transient exception means stable managed GUI operation not established.

### 2026-10-05 [gui] [controller] [acquisition] Audit managed controls and wire camera configuration

- `gui-implementation`, `camera-preview-gui-binding`, `mcu-managed-connection-and-io`; G01/E03/E07/A10/A11, reusing the existing WatchState/UpdateConfiguration path and MCU bridge.
- Found `configuration_wired=False` disabled camera participation and control lease only in the menu. Added Dashboard Take control, assigned-serial camera enable update, Camera config Save (PFS path/line trigger/timing/rate), and D10/D11 persistence/output tests. Behavior camera default lacks `trigger_source`, so enabling is rejected until a source is saved (`Line1` candidate validated, wiring not asserted). Dashboard subject/recording, Protocol, projector, SpikeGLX pairing/mapping, camera role editing/Test and Tracking remain unavailable in managed mode.
- Validation: 10 focused Qt tests; controller configuration 26 passed, 1 skipped; Ruff and Windows mypy (93 files), boundaries (547 modules, zero violations). Broad GUI suite did not pass: two pre-existing review assertions plus a Qt access violation. No live click, capture, Arduino output or PFS import.

### 2026-10-05 [gui] [controller] [acquisition] Explain live camera enable rejection

- `camera-preview-gui-binding`; `REJECTED: configuration validation failed` on Behavior cam enable after taking control (E03). Live read-only query: Configuration phase, GUI-held control, acquisition disabled, behavioral enabled without `trigger_source`; both Basler serials found. Older behavior PFS has FrameStart TriggerMode Off, so Line1 alone does not assert the external input.
- Controller edit rejection now names the first failed field/message; managed Cameras blocks an external-trigger enable without a saved FrameStart line source and explains the next action. No active configuration or output changed; restart needed to load changes.
- Checks: managed enable tests 3 passed; controller configuration 17 passed, 1 skipped (elevated rerun); Ruff, Windows mypy, boundaries (547 modules), `git diff --check` passed. Live enablement, capture, preview and trigger wiring unverified.

# 2026-10-06 [repo] Repository temporary-file cleanup

- `repo-temp-cleanup`; working tree had no changes. Removed 76 disposable directories: `.mypy_cache` (43 MB), `.pytest_cache`, `.ruff_cache`, every `__pycache__`, `build/` (5.0 MB), `dist/` (5.6 MB), `src/cephvr.egg-info/`.
- Preserved `.venv/` and ignored generated protobuf bindings; no `*.tmp`, `*~` or `.DS_Store` found. No tests run (cleanup only); `git diff --check` passed; only LOG/TODO modified.

### 2026-10-06 [gui] [acquisition] [controller] [shared] [visual_stimulus] [repo] Review updated code before layout work

- `gui-implementation`; reviewed `fe1825f..c0120e9` against G01/A03/E08; no hand-written source edits. Generated contracts were stale (14 failures/68 passes affected backends; GUI 5 failures, mypy 20 errors); regenerated all 19 Protobuf sources with the generator.
- Checks: GUI 189 passed, 1 failed (simulated SpikeGLX connection action vs disabled button), 1 deselected; 8 affected modules 82 passed; client RPC 6 passed (after loopback access); GUI Ruff (96 files), Windows mypy (93 files), boundaries (547 modules), whitespace passed. Local only; no rig acceptance.
- Layout inspected in native simulated review; documented Windows 720px overflow remains open. Follow-ups `gui-review-spikeglx-test`, `repo-tracked-test-artifacts` (HEAD tracks 81 `.local-*` outputs, retained).

### 2026-10-06 [gui] Simplify epoch controls and fit the trial timeline

- `gui-implementation`; G01 revision 97. Removed Batch edit count line and Actions menu; Duplicate/Remove buttons in timeline card; Undo/Redo keyboard-only (Ctrl+Z/Ctrl+Y, macOS equivalents); timeline height reserves largest enabled-projector layer stack, cached by program identity; page keeps its scroller. No backend changes.
- Verification: GUI suite 191 passed, 1 deselected; sizing-cache subset 5 passed; Ruff (94 files), Windows mypy (93 files), boundaries (550 modules), whitespace passed. Fixed an outdated selector-layout index and a one-pixel card size-hint change found in checks. Frontend checks only.
- `gui-review-spikeglx-test` completed (disabled connection button in isolated review is intended); managed button verification stays in its rig task.

### 2026-10-06 [gui] Add epoch duplicate/remove shortcuts

- `gui-implementation`; G01/register revision 98: Backspace removal and Ctrl+D duplication, reusing guarded timeline buttons and existing mutations/history (editor-scoped, non-repeating).
- Checks: keyboard-history scenario extended (1 passed, 191 deselected), including Backspace text editing in the uncommitted Batch edit field; Ruff (2 files), Windows mypy, boundaries (549 modules), whitespace passed. A missing import separator in a concurrent Image preview test was fixed. Runtime/hardware acceptance remains in the rig worklist.

### 2026-10-06 [gui] [visual_stimulus] Tailor epoch controls by stimulus family

- `gui-implementation`; G01/register revision 99, V04/register revision 11. Images expose Fit, Move speed, Direction (position/rotation in Advanced); Fit persists in image settings/source/prepared schemas (Contain for new GUI Images, Stretch for legacy), has a Batch edit dropdown, excluded from numeric variation; preview and renderer shader fit within authored bounds. Video hides generic retain/link widgets (explicit reset values preserved); Looming hides linking.
- Checks: GUI suite 195 passed, 1 deselected; family subset 5 passed; rendering/compilation/contract 68 passed, 79 subtests; Ruff (16 files), Windows mypy (14 files; broader 124), 11-schema consistency, boundaries (550 modules), whitespace passed; two schemas regenerated. Mypy name collisions repaired; a wrong module name ran no tests, corrected to `test_compilation.py`.
- Limits: GPU shader compilation, physical calibration and native Windows rendering remain rig acceptance. Native review at wide and 720px widths; the isolated GUI was reopened with `scripts/start_gui.py`.

### 2026-10-06 [gui] Edit selected epochs with the full shared form

- `gui-implementation`; G01/register revision 100. Single Timeline selection loads the full shared form (duration, mode, label, per-projector/layer parameters) via a focused EpochSelection form; Apply preserves source identity and other epochs; Delete/Duplicate beside the scope selector; All/label scopes keep batch patches; pending edits block scope changes.
- Validation: GUI suite 198 passed, 1 deselected; focused selection tests 4 passed; Ruff (6 files), Windows mypy (95 files), boundaries (550 modules), whitespace passed. Tests cover sibling/projector preservation, source IDs, history, pending-edit protection. No backend or rig acceptance claimed.

### 2026-10-06 [gui] Filter Target epochs by label or index

- `gui-implementation`; G01/register revision 101. All epochs mode renamed Target epochs with All epochs, Epoch label and Epoch index filters; filter/validation in focused EpochTargets; one-based indices traverse nested source epochs without expanding repetitions; invalid/zero/out-of-range indices warn and disable Apply (revalidated on apply); pending patches block filter changes.
- Validation: GUI suite 199 passed, 1 deselected; filter subset 5 passed; Ruff (3 files), Windows mypy (96 files), boundaries (551 modules), whitespace passed. Native inspection at wide and 720px. Managed runtime and rig checks remain in existing worklist.

### 2026-10-06 [gui] Remove device Save buttons

- `gui-implementation`; G01/register revision 103: completed rate/pin edits and camera trigger/PFS, COM and fixed-I/O changes submit through existing controller configuration requests; snapshots, camera selection and port scans stay silent; managed edits lock during diagnostics; review stays command-free. Prepare calibration files = diagnostic GLB/grid and display/geometric-profile export into Assets; Launch already prepares; renderer launch wiring unfinished.
- Validation: affected GUI subset 19 passed; commit/scan/snapshot subset 2 passed; Ruff (4 files), Windows mypy (3 files), boundaries (551 modules), whitespace passed (`QT_QPA_PLATFORM=offscreen`). Stale Save-message expectations updated. Local checks do not establish Windows/controller/hardware acceptance. Native review at 1280px and 720px.

### 2026-10-06 [gui] Refine Protocol editor rows, spacing and actions

- `gui-implementation`; G01/register revision 102 (with concurrent Devices revision 103). Epochs/Filter/label-or-index share a row; Parameter/value share the next; matching fixed durations keep exact clock values, mixed show hh:mm:ss; Timeline-selection actions beside identity fields (wrap at narrow widths); shared InlineMessage; Actions undo hint updated to Ctrl+Z.
- Verification: fresh GUI suite 202 passed, 1 deselected; selection/format/wrapping subset 7 passed; narrow subset 3 passed; Ruff (8 files), Windows mypy (96 files), boundaries (551 modules), whitespace passed. Narrow variation overflow and clipped narrow action buttons fixed. An earlier full run during concurrent MCU changes had three failures; final fresh suite passes. Managed runtime/rig acceptance remains pending.

### 2026-10-06 [gui] [visual_stimulus] Make calibration preparation part of Launch

- `gui-implementation`; G01/register revision 104. Removed Prepare calibration files; Screen calibration has only Launch/Close. Launch prepares the diagnostic arena/profiles first; failure emits no output request. No dependency or backend policy change.
- Checks: calibration suite 5 passed, 198 deselected; Ruff (3 files), Windows mypy (2 files), boundaries (551 modules), whitespace passed. Managed renderer launch wiring and physical projection acceptance remain pending.

### 2026-10-06 [gui] Align epoch fields and keep edit actions fixed

- `gui-implementation`; G01/register revision 105: equal field columns/heights (12px gutters) and a permanent Discard/Apply pair at the top right in every Batch edit mode, replacing the form's duplicate buttons. BatchEdit stays cohesive (506 lines).
- Verification: fresh GUI suite 202 passed, 1 deselected; focused subset 10 passed; Ruff (4 files), Windows mypy (96 files), boundaries (551 modules), whitespace passed. First full run had two failures from legacy tests editing hidden patch controls (now target source index 1). Native checks at 1280px/720px assert fixed action positions and aligned heights. Managed/rig acceptance pending.

### 2026-10-06 [gui] [spikeglx] Remove Stream mapping column

- `gui-implementation`; G01/register revision 106: Devices/SpikeGLX grid keeps Use, Signal, Index and Channel; stream metadata retained hidden in the existing review-draft serializer. Camera OneBox constraints and configuration gates remain; managed channel discovery/adoption pending.
- Verification: SpikeGLX/draft/reflow subset 6 passed; Ruff, Windows mypy (1 file), boundaries (551 modules), whitespace passed; no new tests for this layout change. No hardware/runtime pass claimed.

### 2026-10-06 [gui] [visual_stimulus] [spikeglx] Synchronize and verify current runtime GUI

- `gui-implementation`; ManagedDashboardWindow inherits the same DashboardWindow/screens as review, so layout changes already reach runtime; no source edit needed. An offscreen probe of the actual ManagedGui showed completed camera/rate and MCU/pin edits reach existing bridge actions, control loss disables editing, and removed Save/Prepare buttons and hidden Stream fields are reflected; the calibration presenter stays disabled.
- Checks: `tests/gui/test_dashboard.py tests/launcher/test_lifecycle.py ... -k "managed or ... gui"` 202 passed, 11 deselected (selector matched the whole GUI module; launcher cases deselected); Ruff (97 files), Windows mypy (96 files), boundaries (551 modules), whitespace passed. Corrected runtime guide's Save workflow.
- Limits: macOS host cannot run the Windows runtime; no authenticated command, rig startup, device execution or projection pass. Managed Protocol/projector/SpikeGLX adoption and calibration-output wiring remain in TODO.

### 2026-10-06 [gui] [controller] [acquisition] Wire managed MCU and camera controls

- `mcu-managed-connection-and-io`, `camera-preview-gui-binding`; G01 revision 107, A10 revision 51, root register updated. MCU pending/failure locks and confirmation-based final-status queries; camera role assignment, connection checks, capture/editing state and viewer refresh use controller-owned paths. Live-edit adoption stays in `owned-camera-edits`.
- Fixed two missing handoffs: accepted drafts now reach manual acquisition commands (stale/conflicting ownership rejected; prior COM owner closed first); PFS selection now imports through the assigned camera worker with SDK readback and no implicit enabling. Test enabled stays connection-only; added request/worker enum values and regenerated Protobuf; queued intents discarded on transport loss. ARCH-002 extractions, no new dependency.
- Validation: portable GUI 206 passed, 1 deselected; acquisition/controller 390 passed, 5 skipped; authenticated loopback RPC 6 passed; Ruff 360 files; Windows mypy 355 sources; boundaries 555 modules, zero violations; whitespace passed. Native startup, real PFS compatibility, frames, pulse waveforms and cleanup remain pending (macOS host cannot run managed GUI).
- Refs: A11, E03, E07

### 2026-10-06 [gui] [controller] [acquisition] Begin live device connection checks

- `mcu-managed-connection-and-io`, `camera-preview-gui-binding`; revision `7b250de613c9d3568932eb648974d9e4964c2c35`. Windows Python 3.11.15 enumerates Arduino Uno COM8 and Basler 40065509/acA4112-30uc and 40747103/a2A2464-77umPRO. SerialOwner CAPS/STATUS: protocol 2, `cephvr2_uno_1`, outputs stopped, zero malformed/unmatched replies, confirmed close. Both cameras open/read/close via pypylon; FrameStart Off on both (does not prove external trigger wiring). No output pulse requested.
- First managed launch failed on missing generated `CAMERA_COMMAND_KIND_TEST_CONNECTION`; regenerating via `tools/generate_contracts.py` is the build repair (no schema/behavior change). No Python process remained afterward. Managed checks and electrical confirmation pending.

### 2026-10-06 [gui] [controller] [acquisition] Check live connections and repair unarmed keepalive

- `mcu-managed-connection-and-io`, `camera-preview-gui-binding`, `visual-renderer-startup-deadline`; evidence in reports/device-connection-evidence-2026-10-06. COM8 CAPS/STATUS, both Basler open/readback/close and controller-backed MCU Connect pass; FrameStart Off (behavioral Line4, tracking Software); no frames, pulses, PFS import or receiver proof. Wiring/5 V/shared-ground confirmation requested, unanswered.
- Fix (A11/E08/ARCH-002): connection-only firmware has configuration_valid=false, watchdog_ms=0, stopped outputs; acquisition wrongly raised MICROCONTROLLER_KEEPALIVE_WINDOW_EXHAUSTED after one second. Health loop now waits only for that proven unarmed state; three regression cases added. Bindings regenerated from 19 schemas.
- Live limits: managed behavioral connection command exceeded the 12-second probe wait; later native launches hit JOB_INSPECTION_FAILED/QueryFullProcessImageNameW error 5 or CHILD_EXITED. Camera command/cleanup acceptance unconfirmed.
- Validation: coordinator 19 passed; elevated acquisition/controller 395 passed, 2 skipped, one long-temp-path copy failure (passes with shorter path, 1 passed); Ruff, Windows mypy pass; boundaries 555 modules. No CephVR processes/listeners on 50051-50055 remain. Electrical question and native blockers open.

### 2026-10-06 [gui] [controller] [acquisition] [launcher] [supervisor] [shared] Enable camera participation before configuration

- `camera-preview-gui-binding`, `visual-renderer-startup-deadline`. G01 revision 108, E07 revision 58: camera participation edits allowed in any current configuration, separate from capture/Setup readiness; GUI trigger-source guard removed; controller verifies only flags changed. PathField passes an absolute directory to the Windows file dialog.
- Native inspection retries transient failures within its three-pass bound and names the PID; supervisor retains the native cause; launcher treats unreadable membership as unknown during shutdown, reusing its guard-retention mechanism. A protobuf parent-presence mutation on clearing an absent enabled field fixed in the comparator.
- Controller camera suite 13/13, native fake-job suite 13/13. Full verification and runtime stability pending.

### 2026-10-06 [gui] [controller] [acquisition] [launcher] [supervisor] [shared] Verify camera enablement and repair worker admission

- `camera-preview-gui-binding`, `mcu-managed-connection-and-io`, `visual-renderer-startup-deadline`. Live flags-only enablement accepts both cameras, holds Configuration 25 seconds and restores selections. Isolated acquisition WORKER_HEARTBEAT_SILENCE: PlanLaunch failed before child creation (missing protected child token, empty work context). Launcher now generates the credential before admission, carries it through bootstrap/peer registration, omits absent work, and maps PlanLaunch gRPC rejection to a command-owner failure (E08/A02; no deadline or auth relaxed).
- Live: COM8 Connect and both Basler TEST_CONNECTION succeed, cameras closed, draft restored; no PFS import, capture, pulses. FrameStart Off; wiring and receiver/frame evidence pending. Original WinError 5 cause not proven.
- Verification: acquisition 194 passed; controller/supervisor/platform/launcher 356 passed, 2 skipped, 15 deselected; supervisor 106 passed; GUI 4 passed; Windows containment 2 passed; Ruff/mypy (188 sources), boundaries (555 modules) pass. Open: WinError 5 cause, full shutdown, PFS/capture/preview, electrical verification. Runtime left running for owner.

### 2026-10-06 [launcher] [supervisor] [gui] Release the retained test runtime

- `visual-renderer-startup-deadline`. Owner's launch failed because this chat left generation 50eb58af-d5ca-4317-b587-669ff3638d2c running (controller PID 7440 on 50051, no GUI). Authenticated ShutdownApplication via the headless client; no controller listener remains and the application guard acquires/closes. No process-name kill or policy change.
- Correction: shutdown stderr records PROCESS_INSPECTION_FAILED / QueryFullProcessImageNameW PID 18904 WinError 5; cause unresolved, and full graceful cleanup is not proven. Same-generation GUI relaunch pending under E08; no production code changed.

### 2026-10-06 [gui] [controller] [acquisition] Repair real PFS capability/readback failures

- `camera-preview-gui-binding`; save_camera_settings failure. SDK readback failed on Gain.GetInc (no constant increment) and absent optional BslEffectiveExposureTime (import had applied). Features helper now respects HasInc and treats only explicit SDK missing-node errors as absent; required writes and other errors stay strict; controller preserves acquisition's original failure message (A10/E07).
- Live: authenticated PFS import/readback adoption/Finish editing succeeded; serial 40065509 external-triggered on Line4 at revision 3, closed, no cleanup pending. No capture, pulses, history save.
- Checks: focused 34 passed; acquisition/controller 406 passed, 2 skipped; Ruff, Windows mypy (2 sources), boundaries (555 modules) pass. Tracking PFS, frames and electrical waveform/receiver acceptance open.

### 2026-10-06 [gui] [controller] [acquisition] [supervisor] Repair lease-loss camera cleanup barrier

- `camera-preview-gui-binding`, `visual-renderer-startup-deadline`. Repeated failed ReleaseManualCameraState: Tracking absent. Acquisition status now retains explicit closed/no-preview/no-cleanup facts for initially unowned roles; strict controller predicates unchanged (A10/E03/E08).
- Oversized result reservations for EditCamera: ingress now uses the normal reservation for connection/export/finish and large for import/apply/readback; byte ceilings, reserves, replay identity, deadlines unchanged. Worker rejection reason reaches the command owner. Exact native cause of the earlier generic rejection unavailable.
- Verification: focused 30 passed; acquisition/controller 408 passed, 2 skipped; lint/mypy pass; boundaries 555 modules. Live: lease/connection/PFS/cleanup sequence passes, cameras closed. One launch exited on SUPERVISOR_HEARTBEAT_FAILED (evidence retained, cause not claimed fixed). Startup rejection cause, trigger delivery, Tracking PFS, full workload open.

### 2026-10-06 [gui] [controller] [acquisition] [repo] Repair Windows camera wait binding and serial write budget

- `camera-preview-gui-binding`. Stock pypylon 26.3.1 rejects an integer Win32 HANDLE; a bounded typed SWIG bridge imports the SDK WaitObject and invokes the duplicating native constructor (SYS-003 SDK exception; A02 refined, root register updated). Pypylon 26.6 still omits WaitObjectEx, not installed. Preview preserves the original SDK failure and marks ownership pending before dispatch.
- Native serial ignored the channel budget (fixed 10 ms writes); writes now use the remaining acknowledgement budget, expired writes not dispatched.
- Checks: portable acquisition/controller 410 passed, 2 skipped, 1 native deselected (final affected 411 passed); native plus preview 6 passed; ownership 29; serial/protocol 19; lint/mypy/boundaries/builds pass. Live: both connections pass. Owner-authorized Behavior-only D10/Line4 preview avoided the timeout but lacked exact completion. Repeated startup heartbeat rejection unresolved; raw evidence in dated directory.

### 2026-10-06 [gui] [acquisition] [controller] [launcher] [shared] Stop CephVR2.0 and diagnose legacy GUI startup

- `camera-preview-gui-binding`, `visual-renderer-startup-deadline`, `legacy-runtime-path-isolation`. Acquisition startup rejection was WRONG_CONTEXT (registration now precedes the health task). A later launch reaches SDK resolution, MCU configuration and readback; preview preparation fails because its function catalogue omits the camera capture scope. No frame pass.
- Owner stopped 2.0 for 1.0: controller already unavailable; no 2.0 processes; application guard acquire/release succeeded; legacy preserved. Earlier TODO claims of a running runtime superseded.
- 1.0 GUI startup stalled on controller log PermissionError (WinError 5 on `%LOCALAPPDATA%/CephVR/runtime/controller/controller.log`); empty inherited DACLs below the protected root. No ACL or legacy source edits; follow-up `legacy-runtime-path-isolation` open.

### 2026-10-06 [shared] [launcher] [gui] Restore CephVR1.0 startup and isolate runtime storage

- `legacy-runtime-path-isolation` completed at owner's request. CephVR2.0 defaults to `%LOCALAPPDATA%/CephVR2/runtime`; E08 revision 161/root register amended; no dependency, migration service or legacy-source changes.
- Moved generation directories and recovery into the private root (ACLs and SHA256 preserved). PowerShell 5 could not load its security module; PowerShell 7 Set-Acl needed unavailable SeSecurityPrivilege (failed result retained); the typed native API repaired the DACL. Legacy launcher now shows a populated Experiment OS Dashboard; no 2.0 roles; no Setup/Start/capture.
- Checks: shared invariants 10 passed; Ruff, Windows mypy pass; boundaries 556 modules, zero violations.

### 2026-10-06 [acquisition] [gui] Diagnose legacy acquisition HUD at 16–18 fps

- `legacy-camera-trigger-rate`. HUD shows a preview sequence/timestamp metric. Historical legacy Behavior CSVs measure 17.4408/17.7476 fps; second run 17,961 rows/1,011.966 seconds, mostly 66.7 ms intervals; saved video has 12,406 duplicated and five padded frames. Historical measurements, not a new capture.
- Read-only SDK: 25 ms exposure, 17.184 ms readout, limiter enabled at 30.0003, free-run capacity 29.9994, 360 MB/s cap vs about 90.6 MB/s demand; TriggerMode Off after shutdown. Limiter/trigger timing near 30 fps is the leading hypothesis, not established. Triggered-run capacity unmeasured. No source/config/output changes.

### 2026-10-06 [acquisition] [gui] Preserve loaded legacy camera frame-rate control

- `legacy-camera-trigger-rate`. Legacy startup passed readback FPS into camera.start, forcing set_frame_rate and enabling the limiter; the call now uses only `config.get('fps')`. Camera/PFS state survives startup/reload; explicit overrides still work.
- Dependency controller/settings 10 passed; legacy GUI connection/trigger settings 9 passed (actual CephVR conda environment); external `git diff --check` passes. No live capture/pulse test, PFS change or GUI restart; legacy restart required. 30 Hz trigger acceptance open.

### 2026-10-06 [gui] [controller] [acquisition] [launcher] [supervisor] [repo] Recheck Behavior receiver, clean artifacts and stop at owner request

- `camera-preview-gui-binding`, `mcu-managed-connection-and-io`, `visual-renderer-startup-deadline`; `repo-tracked-test-artifacts` completed. Owner confirmed Behavior-only D10 → Line4; uploaded existing CephVR2 firmware (original ATmega328P flash saved; Arduino CLI verification exit 0; protocol 2 / `cephvr2_uno_1`). Direct check: 41 frames in two seconds at 30 Hz, ON/OFF applied, closure confirmed. Receiver path passes; sustained 30 fps, waveform and full-workload acceptance do not.
- Preview payload declares its non-saving capture scope; closed-camera reports carry empty preview run identity; strict validators and deadlines remain. Latest managed Start still fails OPERATION_FAILED (exact completion missing); earlier Stop lacked result evidence. A Visual Stimulus invalid UUID launch failure is separate and uninvestigated.
- Validation: preview/status/controller 32 passed; final warning-ledger revision and expanded suite/static checks not rerun; no end-to-end preview acceptance.
- Cleanup: 42 directories, 6,640 files, 201,368,736 bytes (incl. 81 tracked fixture artifacts); focused ignore rules added; manifest records removals; data, configs/PFS, dated evidence, firmware backup preserved.
- Owner stop: authenticated ShutdownApplication for generation 2dd0392f-54f9-4c83-a733-3ea0549872ef; CephVR2 process inventory empty, guard free. Graceful cleanup acceptance open; tasks user-paused.
- Refs: A03, A10, A11, E06, E07

### 2026-10-06 [acquisition] [controller] [gui] [supervisor] Review latest rig status

- Reviewed evidence at aff8e0c, acquisition/runtime assessments and TODO. Camera connection diagnostics and Behavior PFS adoption passed; direct D10 → Line4 gave 41 frames in two seconds. Latest managed Start reports exact completion missing; earlier Stop lacks result evidence. GUI viewer, sustained rates, Tracking capture and graceful cleanup unaccepted under E15.
- Historical preview log (411 passed, two skipped, one deselected) does not validate the final tree. No new tests, hardware actions or launch; TODO unchanged.

### 2026-10-06 [controller] [acquisition] Explain preview failure and firmware naming

- "Exact completion missing" is the controller camera-operation deadline path; frame arrival alone does not complete the command. Start needs a matching successful result plus running/run-identity/cleanup evidence; earlier Stop failed result validation. Upstream cause unisolated. Firmware sketch `cephvr2_mcu`, reported identity `cephvr2_uno_1`. Explanation only; no changes or tests.

### 2026-10-06 [gui] Place epoch actions in card and timeline headers

- `gui-implementation`; G01/register revision 109. Apply/Discard pair at top right of the tabs row; Duplicate/Delete before Preview in the timeline header (narrow widths: below the title); removed the redundant single-epoch inspector shortcut button/signal; Projector heading omitted in parameter editing. BatchEdit 506 to 462 lines.
- Validation: fresh GUI suite 206 passed, 1 deselected; focused 9 passed; narrow subset 3 passed; Ruff (4 files), Windows mypy (99 files), boundaries (555 modules), whitespace passed. Narrow overflow and shifting action positions repaired; one flaky narrow-generation assertion handled with four event-loop passes. No hardware or managed runtime acceptance.

### 2026-10-06 [controller] [acquisition] Repair inactive preview identity validation

- Task `camera-preview-gui-binding`: acquisition sends explicit empty run IDs for idle/closed cameras but controller validated all present IDs as UUIDs; real status-reporter/controller regressions reproduced EVIDENCE / invalid UUID on Start and Stop. Validator now permits inactive empty IDs, keeps UUID checks for nonempty IDs and prepared/running previews. Operation identities, deadlines and release predicates unchanged (A10/E07/E15); no new dependencies (ARCH-002).
- Tests: camera evidence 26 passed; affected acquisition/controller portable suites 417 passed, five skipped, one native deselected. Ruff check/format (305 files), Windows-target mypy 256 sources, boundaries 555 modules/zero violations pass. Reports, TODO, rig checklist updated. No device commands or native runtime. Exclusive causality of the saved rig timeout and end-to-end viewer/Stop closure still require rig verification.

### 2026-10-06 [gui] Align Batch edit parameter choices with generation

- Task `gui-implementation`: owner asked to remove Opacity and allow only parameters available during generation. G01/register revision 110. Batch edit reuses stimulus_columns for choices/layer compatibility (ARCH-002); Duration/Asset common, per-family Texture/Image/Looming/Video choices and arena Longitudinal/Lateral/Angular gains; Video At end is a dropdown. Arena patch helper moved to ArenaMovement, shared by variation and batch editing; serialization unchanged.
- Verification: GUI suite 211 passed, 1 deselected (154.24s); focused checks 10 passed, 202 deselected. Ruff lint/format (8 files), Windows-target GUI mypy (99 sources), boundaries (555 modules, zero violations), whitespace pass. Native review of five-family lists and Video dropdown done; temporary helpers removed. No hardware commands or rig acceptance.

### 2026-10-06 [launcher] [gui] [controller] Add confirmed runtime replacement and automatic unheld control

- Task `runtime-replacement-and-auto-control`: terminal Y/N replacement through the existing containment owner; Y terminates only the old launcher's application job after empty membership, exit receipt and guard reacquisition. N/EOF/noninteractive leave the old runtime; older versions without endpoint need one manual shutdown. No PID kill, handle duplication or remote SpikeGLX termination. E08 revision 162; supervisor policy/pair bumped to 8. GUI makes one AcquireControl attempt per synchronized connection if unheld; E03 revision 29, policy pair versions 8/5.
- Validation: launcher/configuration/GUI 246 passed, one deselected (offscreen; first run aborted in Qt init); controller/launcher 238 passed, launcher-only 20 passed. Ruff (11 files), Windows mypy seven files, boundaries 555 modules/zero violations, TOML pairs, whitespace pass. Native event/ACL tests added; actual replacement and managed GUI acceptance unexecuted on macOS. Remaining native verification moved to Next; rig checklist updated.

### 2026-10-06 [gui] [tracking] Review Tracking UI direction

- Compared legacy experiment_window Tracking form, V4 navigation and preview controller with current tracking architecture. Recommend keeping grouped settings, annotations and optional external overlays; dropping legacy algorithm/provider toggles, fin-undulation controls and video-debug source from initial scope. Proposed Source/Pipeline plus Subject/Analysis views. T03–T07/T20/T24–T45 govern options; T38 keeps stimulus gains in Visual Stimulus/Protocol.
- Design proposal only; no architecture acceptance, code changes, runtime tests or preview support claimed.

### 2026-10-06 [gui] Use action-time warning windows and log-only status

- Task `gui-implementation`: owner asked to remove the unmatched-epoch inline message, show errors only on required actions, and put status in the log. G01/register revision 111, G02/register revision 24. ARCH-002: focused FormNotice/window lifecycle and GUI status event. Inline labels removed; passive validation stages diagnostics; failed Apply/Add opens one reusable window-modal warning per form; routine statuses go to the Dashboard activity log; authority loss dismisses warnings.
- Validation: GUI suite 216 passed, 1 deselected (125.59s); focused subset 21 passed. Ruff (18 files), Windows GUI mypy (100 sources), boundaries (556 modules, zero violations), whitespace pass. Native review confirmed quiet label, themed Apply warning, status in log. No hardware or rig acceptance.

### 2026-10-06 [gui] [tracking] Implement Tracking frontend for review

- Task `gui-implementation`: implemented Subject/Analysis layout (G01/register revision 112): camera/pipeline card, conditional threshold/model/manual controls, collapsed pose quality/analysis advanced settings, separate water/fin drafts, HUD/log. Reference-image tool supports point placement and search-region drag; source/image changes invalidate annotations. Local draft JSON/review persistence separate from backend settings. ARCH-002: focused page/forms/annotation modules, no new dependencies.
- Owning GUI tests extended (draft isolation, atomic invalid-load rejection, annotation roundtrip, camera-change invalidation, coordinate mapping). GUI suite 220 passed, one skipped (142.24s); Ruff, five-source Windows mypy, boundaries (559 modules, zero violations), whitespace pass. Inspected 1280px/720px native renders; Tracking left open (PID 29753). No physical/runtime Tracking acceptance; managed submission/live previews/diagnostics pending.

### 2026-10-06 [gui] Hide Retain state for 3D arena stimuli

- Task `gui-implementation`: owner requested no Retain state in 3D stimuli. G01/register revision 113 refines editor visibility/writeback (generation, Timeline selection, inspection); loaded arena reset values preserved. ARCH-002: existing family guards reused, no new abstraction or runtime reset policy change.
- Extended family-hidden-state scenario; focused checks 8 passed, 217 deselected (8.60s). Ruff (two files), Windows mypy (one source), boundaries (559 modules, zero violations), whitespace pass. Local Qt checks only; no native Windows or rig acceptance.

### 2026-10-06 [gui] Defer epoch parameter warnings to Add and Apply

- Task `gui-implementation`: owner requested parameter warnings only on adding/editing epochs. G01/register revision 114. Parameter commits stage diagnostics privately; focus/layer/type changes, variation preparation and batch navigation stay quiet, keeping drafts; Add/Apply owns one warning. File-picker/load failures keep their own warning. ARCH-002: reuses FormNotice; no new dependency or policy.
- Owning GUI tests cover quiet paths, one warning on Add/Apply and corrected resubmission. GUI suite 226 passed, one deselected (144.70s); final subset five passed. Ruff six files, Windows mypy five sources, boundaries 559 modules/zero violations, whitespace pass. No native inspection, hardware or rig acceptance.

### 2026-10-06 [gui] [tracking] Restore missing Tracking pipeline sections

- Task `gui-implementation`: reviewed CephVR1.0 processing sections; replaced Subject/Analysis with Preprocessing/Calibration/Pose/Motion; camera selector removed (unique Tracking-role camera resolved from Devices). Added optional source-pixel crop, 10–100% downscale draft, two-point known-mm reference (px/mm, mm/px), synchronized numeric/drawn rectangles; optical flow in a visible card. G01/register revision 115. No runtime preprocessing, scale conversion or output-unit change; T01/T20 transforms and managed integration pending.
- ARCH-002: spatial controls and draft validation/migration extracted. Draft v1→v2 migration defaults to no preprocessing/calibration; source mismatch clears annotations. GUI suite 229 passed, one skipped (154.82s); initial focused nine passed. Ruff, Windows mypy six files, boundaries 561 modules/zero violations, whitespace pass. Native launch inspected (PID 31897). Local frontend checks only; no backend, native Windows or rig acceptance.

### 2026-10-06 [gui] Space section enable controls from dependent fields

- Task `gui-implementation`: owner requested more space under enable checkboxes. G02/register revision 25: one shared 8 px token as dependent-section top margin (SpikeGLX control, photodiode pulse, Tracking crop, Variation rules). ARCH-002: reuses theme/layout margins; no behavior change.
- Focused GUI checks eight passed, 225 deselected (6.12s). Ruff five files, Windows mypy five sources, boundaries 561 modules/zero violations, whitespace pass. Offscreen renders of four sections reviewed. No new tests (layout-only); no hardware commands or native Windows/rig acceptance.

### 2026-10-06 [gui] [tracking] Refine Tracking coordinates and defaults

- Task `gui-implementation`: removed preprocessing caption (crop-before-downscale kept); Subject reference precedes Pixel-to-mm calibration; Search region precedes Pose detection. One shared point-row helper exposes X/Y for anatomical, manual and distance points. Fresh UI/operator defaults now Manual pose; Water flow unchanged; saved automatic values preserved. G01/register revision 116 and T05/register revision 3. No fixed-policy value or version changed.
- Tests: GUI/config focused 19 passed; draft subset 12 passed (6.69s); Tracking suite 36 passed, one Windows deselected; six authenticated checks failed sandbox socket binding then passed with loopback permission (2.07s). Ruff seven files, Windows mypy five sources, boundaries 561 modules/zero violations, TOML, whitespace pass. Native Calibration inspected (PID 33261). Backend submission, preprocessing and rig acceptance pending.

### 2026-10-06 [gui] [tracking] Refine point-table presentation

- Task `gui-implementation`: one compact rounded point table (row separators, aligned 2:1:1 Point/X/Y, centered numeric cells, dash placeholders) reused by PointEditor for all anatomical/manual/distance rows. G02/register revision 26. ARCH-002: focused helper kept, theme roles centralized; no behavior/validation change.
- Tracking/draft subset 12 passed, 221 deselected (6.56s); Ruff, two-source Windows mypy, boundaries 561 modules/zero violations, whitespace pass. No new tests (styling only). Inspected at 1280/720px (PID 33561). No backend command or rig acceptance.

### 2026-10-06 [gui] [tracking] Try coral coordinate headers

- Task `gui-implementation`: owner-requested log-coral color on enabled Point/X/Y headers via one scoped theme selector; disabled labels stay muted. G02/register revision 27, pending owner visual review. ARCH-002: existing console token reused.
- Native Calibration inspected (PID 33894). Ruff, Windows theme mypy, boundaries (561 modules, zero violations), whitespace pass. No behavioral test rerun for the one-line change; no hardware or rig validation.

### 2026-10-06 [gui] [tracking] Move coral accents to navigation

- Task `gui-implementation`: owner rejected coral table headers; neutral headers restored; shared coral applied to page headings, selected sidebar text and active subtabs; blue action/focus and status colors kept. G02/register revision 28. ARCH-002: one shared palette token.
- Native Dashboard, Protocol, Devices, Tracking renders inspected (PID 34082). Ruff, Windows theme mypy, boundaries (561 modules, zero violations), whitespace pass. No behavioral suite rerun (palette only); no hardware or rig validation.

### 2026-10-06 [gui] [tracking] Strengthen coordinate-header hierarchy

- Task `gui-implementation`: owner liked coral navigation but found neutral headers too subdued; PointEditor headers now bright neutral bold, 28 px minimum height, 2 px divider; disabled headings muted. G02/register revision 29. ARCH-002: shared theme/component ownership kept.
- Native Calibration inspected (PID 34257). Ruff, two-source Windows mypy, boundaries (561 modules, zero violations), whitespace pass. No new tests or suite rerun (style only); no hardware or rig validation.

### 2026-10-06 [gui] [tracking] Try muted teal point headings

- Task `gui-implementation`: owner-approved trial color #86CFC7 for Point/X/Y headings; size, spacing and coral navigation kept. G02/register revision 30, pending visual review. ARCH-002: one palette token shared with the unchanged mirror color.
- Native Calibration inspected (PID 34511). Ruff, Windows theme mypy, boundaries (561 modules, zero violations), whitespace pass. No suite rerun (color only); no hardware or rig validation.

### 2026-10-06 [gui] [tracking] Use brighter blue point headings

- Task `gui-implementation`: rejected teal trial replaced by existing blue accent #8EC7FF for Point/X/Y headings; teal alias removed, mirror color retained. G02/register revision 31. ARCH-002: shared palette/component reused.
- Native Calibration inspected (PID 34631). Ruff, Windows theme mypy, boundaries (561 modules, zero violations), whitespace pass. No suite rerun (color only); no hardware or rig validation.

### 2026-10-06 [gui] [tracking] Reuse camera table presentation for coordinates

- Task `gui-implementation`: custom point grid replaced by QTableWidget using the Cameras header band, blue header text, rounded border and shared padding; stable 2:1:1 columns, validators, incomplete-edit behavior and drawing/draft sync retained; unused point-frame theme rules removed. G02/register revision 32. ARCH-002: native Qt reused, no new state.
- Tracking/review-draft checks 12 passed, 221 deselected (7.38s). Ruff, two-source Windows mypy, boundaries 561 modules/zero violations, whitespace pass. Inspected at 1280/720px and native Calibration (PID 34873). No backend command or hardware acceptance.

### 2026-10-06 [gui] [tracking] Share table forms and isolate diagnostic stage switches

- Task `gui-implementation`: Cameras table template applied via one helper to camera/projector inventories, projection calibration/dimensions, MCU I/O, SpikeGLX inputs and Tracking coordinates. Clear preserves manual/distance annotations. Added default-enabled pre-experiment switches (preprocessing, pose, sampling region, optical flow, flow quality, locomotion); disabled controls keep values; flags persist in draft v3, older drafts migrate enabled. G01/register revision 117, G02/register revision 33. T02 experiment requirements unchanged; live diagnostics/timing and managed submission pending.
- ARCH-002: focused table/stage helpers. Row-height regression extended; full GUI suite 233 passed/one skip (182.45s) before final sizing; final affected suite 39 passed/195 deselected (40.08s). Ruff 14 files, Windows mypy 12 sources, boundaries 563 modules/zero violations, whitespace pass. Offscreen review of four Tracking and four Devices pages and native Motion (PID 36119). No device commands or hardware acceptance; backend wiring and Windows/rig limits in reports/TODO.

### 2026-10-06 [gui] [tracking] Simplify Tracking controls and Manual pose layout

- Task `gui-implementation`: diagnostic switches renamed Enable; redundant preprocessing switch, Draw region actions, output-size calculation/caption removed; uncalibrated scale caption hidden. Draft v4 migrates v3 by dropping only the obsolete preprocessing flag. G01/register revision 118; experiment-required stages unchanged. ARCH-002: fixed-height pose stack replaced by naturally sized forms; no new dependency/helper.
- Tracking/review-draft suite 13 passed, 221 deselected (9.63s). Ruff seven files, Windows mypy five sources, boundaries 563 modules/zero violations, whitespace pass. Inspected at 1280/720px and native Manual pose (PID 36708). Managed Tracking and rig acceptance pending.

### 2026-10-06 [gui] [controller] [acquisition] [visual_stimulus] [tracking] [spikeglx] Start managed runtime GUI wiring

- Task `gui-implementation`: owner authorized layout parity, necessary backend wiring and dev checks before separate rig acceptance, with Luna audit/code, Sol 6.1 planning/review and Astra plan/final review. Two read-only Luna audits (GUI, backend interfaces) started; uncommitted work preserved, baseline diff kept outside the repository.
- Managed/review windows share DashboardWindow; managed snapshot sets configuration_wired=False. No runtime or rig readiness claimed; audit, plan and implementation in progress.

### 2026-10-06 [gui] [controller] [visual_stimulus] [tracking] [spikeglx] Complete wiring audits and baseline finding

- Task `gui-implementation`: both Luna audits completed, confirming layout parity and missing configuration, status, Tracking diagnostic and projector calibration paths. Sol 6.1 preparing wiring plan for Astra review.
- Reproduced Visual Stimulus typed-default failure (one failed/four passed, rejected presentation.pacing_refresh_hz). Wider offscreen baseline in progress; boundary check 563 modules, zero violations; whitespace passes. No implementation readiness claimed.

### 2026-10-06 [gui] [controller] [tracking] [visual_stimulus] [spikeglx] Review wiring plan and begin implementation

- Task `gui-implementation`: Sol completed the plan; Astra approved the first increment and identified existing SpikeGLX lifecycle hooks for reuse. Luna GUI/transport and Tracking agents began code under disjoint ownership; one Luna owns schema edits/generation. ARCH-001 revision 22 records the managed integration scope without lifting rig/scientific/encoder deferrals.
- Baseline combined GUI/Tracking/Visual Stimulus: 273 passed, one known pacing-loader failure, two deselected, six RPC fixture errors from sandbox-denied loopback; authorized loopback rerun passed all six Tracking RPC tests (2.07 s). No hardware or rig readiness claimed.

### 2026-10-06 [gui] [acquisition] [tracking] [spikeglx] Record Astra wiring decisions

- Task `gui-implementation`: Astra approved the Sol plan (existing lifecycle reuse, bounded diagnostic contracts); no owner choice needed. Recorded G01 managed schedule/subject semantics; T01/T20 private transform and image-scale lineage; T08 separate same-process diagnostics; A03/A10 acquisition-owned ordered diagnostic ring; E12 controller-serialized inventory-only host-file edits; root register revisions updated. Implementation requirements, not completed wiring or evidence.
- Three Luna code owners (central GUI/contracts, Tracking, Visual Stimulus/SpikeGLX); proto generation serialized. Scientific units, firmware, encoder feasibility and rig acceptance remain deferred.

### 2026-10-06 [visual_stimulus] [controller] [gui] Review first pacing implementation checkpoint

- Task `gui-implementation`: Luna completed file-only V20 pacing propagation (controller/coordinator/worker); owner reports 41 focused tests and scoped lint/format/Windows mypy/boundaries/whitespace passing. Sol review found a startup parsed/serialized-profile mismatch despite helper passes; repair and end-to-end regression required before acceptance.
- Baseline raw logs preserved with provenance and scope in reports/runtime-wiring-evidence-2026-10-06; no rig pass claimed.

### 2026-10-06 [tracking] [acquisition] [visual_stimulus] [gui] Refine implementation evidence and transform binding

- Task `gui-implementation`: backend reports now distinguish active managed implementation from pending diagnostic/rig acceptance. Recorded the Tracking private INTER_AREA crop/downscale binding, integer round-half-up dimensions, actual-axis pixel-centre inverse and acquired-unit normalization in the method contract. Typed submit codec omits diagnostic switches; validation/inverse install and tests in progress.
- Sol also reproduced rational-refresh rejection and pulse-off validation-before-file-identity adoption; Luna repairing all three pacing issues. No runtime/rig success claimed.

### 2026-10-06 [tracking] [gui] Review first Tracking wiring checkpoint

- Task `gui-implementation`: Luna completed typed submit/inverse codecs, tolerant default restoration, private crop/downscale, actual-axis normalization, source/dimension checks and minimum flow-grid validation. Diagnostic flags remain separate; live diagnostics unimplemented. Sol review started.
- Owner evidence: Tracking 47 passed, one Windows deselected, loopback permitted; Ruff/format, 64-source Windows mypy, boundaries (570 modules/zero violations), whitespace pass. Earlier sandbox socket failures are development attempts, not rig evidence. Final combined raw checks pending.

### 2026-10-06 [visual_stimulus] [controller] [gui] Repair pacing across controller validation

- Task `gui-implementation`: Sol accepted three worker repairs (43 focused passes) but found raw-profile validation before file identity adoption at controller startup/UpdateConfiguration/Setup. Luna added policy-aware installed validation (copied candidates, exact held Setup file policies), canonical startup resolution and a focused pacing module; post-Ready path unchanged.
- Luna reports 19 configuration-transaction and 38 setup/device/Visual Stimulus tests plus scoped lint/format/seven-source Windows mypy passing; one concurrent GUI test assertion excluded and corrected by its owner. Combined validation and review pending; rig acceptance separate.

### 2026-10-06 [tracking] [gui] Repair Sol Tracking review findings

- Task `gui-implementation`: Sol passed 35 configuration/method/processing tests and reproduced five defects: automatic search-region shape mismatch, lost original reference dimensions, transformed directional-reference bounds rejection, asset-relative path resolution, native-cost gate loss. Luna repairing with round-trip/boundary regressions; first-slice passes did not imply correctness.
- GUI transport has a real authenticated bridge-queue regression; verification continues. Concurrent projector module construction temporarily blocked the GUI fixture. No rig readiness claimed.

### 2026-10-06 [gui] [controller] Review transport and authority checkpoint

- Task `gui-implementation`: Sol reviewed Luna's transport/status/prompt code. Nine GUI, 53 controller and one authenticated bridge checks passed; E07 SettingUp rejection at admission/commit correct. Sol reproduced five issues: retained-summary visibility, acknowledgement crossing disconnect, observer prompt re-enablement, uncertain admitted-response identity, initial/reopened warning gating. Repair precedes full integration.
- Projector construction passes 23 focused GUI cases after stabilization. Exact V01 calibration transport/evidence requirements handed to the schema owner; no runtime calibration or rig acceptance.

### 2026-10-06 [tracking] [gui] Accept reviewed transform and codec repairs

- Task `gui-implementation`: Sol accepted all five Tracking repairs, no new findings. Root ran full Tracking suite with loopback: 55 passed, one Windows deselected (3.15 s); raw output in dated evidence. Live diagnostics, managed publication and rig acceptance pending.
- V01 additive calibration contracts frozen and generated (19 bindings); controller/renderer implementation continues; declaration presence is not a calibration pass. Setup file-policy wrapper propagation under review.

### 2026-10-06 [controller] [visual_stimulus] Verify actual Setup policy assembly

- Task `gui-implementation`: Sol withdrew the inactive-backend concern but found the actual enabled-backend wrapper loses policy-aware dispatch, so Setup rereads TOML and may validate against values differing from its held policy (reproduced with held pacing-output identity and changed on-disk value). Luna repair and actual-assembly regression requested. Corrects the prior exact-held-policy claim.
- V01/register revision 14 records Astra-reviewed diagnostic identity/revision/generation/deadline and protected asset provenance. No new owner decision or rig acceptance.

### 2026-10-06 [gui] [tracking] [visual_stimulus] Prepare managed integration rig acceptance

- Task `gui-implementation`: single rig checklist extended with managed configuration/authority, live Tracking diagnostics and untimed projector calibration acceptance, conditional on local implementation/reviews. Existing scientific/full-load deferrals retained; no rig checks executed.

### 2026-10-06 [tracking] [visual_stimulus] Check pure contract consistency

- Task `gui-implementation`: Visual Stimulus pure contracts 42 tests/79 subtests passed. Tracking unittest contracts 48 tests with one stale automatic-pose default expectation against accepted manual configuration; Luna assigned the test correction. Initial combined pytest had two Tracking collection errors (local-module imports); unittest working-directory invocation resolved it. Raw outputs in dated evidence. Declaration checks, not runtime or rig passes.

### 2026-10-06 [controller] [visual_stimulus] Validate held Setup policy repair

- Task `gui-implementation`: Luna preserved policy-aware dispatch through the enabled-backend/identity validator wrapper and added an actual-assembly policy-drift regression. Root ran controller configuration transactions and Visual Stimulus lifecycle with loopback: 34 passed (1.16 s), raw evidence retained. Sandbox socket errors were environmental; final Sol review pending; V01 continues.
- Twelve edited documents have no missing local link targets; whitespace passes.

### 2026-10-06 [gui] [controller] Verify authority repair checkpoint

- Task `gui-implementation`: independent offscreen metadata/status/prompt/retained-acknowledgement regressions 10 passed (237 deselected, 1.64 s). Boundary check 573 modules, zero violations; growing central GUI/configuration owners sent for cohesion review. Sol re-review and full managed publication pending; raw evidence retained.

### 2026-10-06 [gui] [controller] [visual_stimulus] Begin repair re-review

- Task `gui-implementation`: Luna declared the five authority repairs stable; Sol re-review covers them and the extracted held-policy validator gate. Luna's full GUI checkpoint: 245 passed, one deselected, one projector-message assertion failure (owner reconciling local-number wording). Central configuration and Tracking diagnostic implementation continue; schema generation complete for current interfaces.

### 2026-10-06 [gui] [controller] [visual_stimulus] Accept authority and policy repairs after Sol re-review

- Task `gui-implementation`: Sol found no actionable issues in the five GUI authority repairs or the held-policy validator wrapper; actual Qt manager/window/bridge signal checks confirm gating, no consent across disconnect, one claim per new acknowledgement. Reported: 16 GUI, 43 controller/Visual Stimulus and one authenticated pending-Setup/Cancel/prompt bridge pass. No full GUI, diagnostic or rig acceptance.
- Luna resumed V01/E12 work. The [official SDK wrapper](https://raw.githubusercontent.com/billkarsh/SpikeGLX-CPP-SDK/main/Windows/Python/sglx_pkg/sglx.py) read for E12 call signatures; installed Windows SDK/version compatibility remains a rig check.

### 2026-10-06 [tracking] Correct pure-contract default expectation

- Task `gui-implementation`: Luna updated the owning contract test to accepted Manual pose and its active stages. Reported 48/48 pure contract tests and 19 matching generated schemas. Wrong-working-directory invocations changed no source. Runtime settings, scientific deferrals and rig limits unchanged.

### 2026-10-06 [acquisition] [tracking] Check ordered diagnostic input plumbing

- Task `gui-implementation`: Luna added the bounded ordered Tracking ring, capture output on preview start/restart, retained transfer state and exact Tracking consumer acceptance. Existing acquisition suite 199 passed, five skipped, one deselected. Diagnostic lifecycle/authentication/closure scenarios and Sol review pending; regression evidence only, not managed diagnostics or rig acceptance.

### 2026-10-06 [tracking] [gui] Resolve direct diagnostic viewer authentication

- Task `gui-implementation`: Tracking launch credentials contain only controller/supervisor peers. Decision: reuse the shared E08 CredentialStore for exact GUI credentials under the controller generation, via bounded off-loop lookup; distinct read-only viewer scope and controller-only mutation gates kept; images stay out of controller snapshots; no new capability distribution. Luna implementing negative-authentication and stale-scope checks; no runtime pass claimed.

### 2026-10-06 [gui] [spikeglx] Review active integration details

- Task `gui-implementation`: independent projector local-number regression passes (one test, 247 deselected, 1.54 s), closing the wording failure. Raw result retained.
- Source review of Luna's in-progress E12 client flagged remaining-deadline/late-reply acceptance, prepared stream readback drift and digital-word bit validation for repair and coverage; implementation-review findings, not a reproduced rig defect. Requested extraction of native readback/settings responsibilities before adding monitoring.

### 2026-10-06 [tracking] [gui] Review diagnostic processing scope

- Task `gui-implementation`: first diagnostic core found to handle manual landmarks/geometry only; full accepted enabled-stage scope retained (automatic pose, image flow, quality, locomotion). Requested processing-owner reuse, off-control computation, source-coordinate invariants and a tested mapping from the five GUI stage switches. Permanently unavailable unimplemented stages do not meet acceptance. Luna continues.

### 2026-10-06 [spikeglx] Preserve prepared remote endpoint identity

- Task `gui-implementation`: source review found the active client rereads host settings before start/stop, so a TOML edit could redirect a prepared session. Requested frozen prepared endpoint/policy/budgets under E12/E14 with an endpoint-change regression; monitoring/cleanup must target the original expected run. In-progress finding until tested and reviewed.

### 2026-10-06 [gui] [controller] Implement captured-revision configuration workflow

- Task `gui-implementation`: Luna added the whole-proposal manager and ordered Protocol schedule with typed page patches, exact revision/completion gates before Setup/New session/history, preserved stale/newer drafts and explicit reload. Initial focused run passed eight cases; post-submit tests and static checks in progress before Sol review. Protocol parses restoration before widget mutation; shows empty managed first-run schedule. No full managed path or rig acceptance.

### 2026-10-07 [spikeglx] Verify pinned digital-word source binding

- Task `gui-implementation`: fetched the [official OneBox quickstart at the existing mapping commit](https://github.com/billkarsh/SpikeGLX/blob/0cffa0b748a01f92e4418ed15ebdbfff7e9342c5/Markdown/SpikeGLX_OneBox_Quickstart.md); confirms the 16-bit XD word after XA and before SY. URL/hash/size in dated evidence metadata. First permission review timed out; single retry succeeded. No SDK/device call. Luna to formalize verified digital mapping capabilities; actual wiring/pulse proof remains on the rig.

### 2026-10-07 [gui] [controller] Repair assembled configuration review findings

- Task `gui-implementation`: Sol reproduced eight defects: managed edit gates, unchanged-revision confirmation, phase-invalid New Session/close sequencing, omitted first-run backend participation, missing Tracking dirty hooks, incomplete Tracking installation, unknown subject sex preservation, editor mode propagation. Eight focused tests pass but do not cover these paths. Luna assigned repairs and actual managed-window regressions; no acceptance claimed.
- Root stopped the full GUI pytest (exit 143) after the SpikeGLX five-field row change broke draft saving and a close-error modal blocked it; isolated test confirmed the tuple-unpacking failure; Luna repaired optional-bit draft compatibility (two focused passes). Raw incomplete output retained; combined rerun needed.

### 2026-10-07 [tracking] [gui] [controller] Verify draft repair and diagnostic review

- Task `gui-implementation`: root passed both draft restore/close regressions (two passed, 254 deselected, 2.05 s) and all 48 Tracking pure-contract tests; raw results retained; no combined GUI or diagnostic acceptance.
- Source review of the diagnostic pipeline found stage dependency/execution mismatches, empty-read counter reset and exception/deadline cleanup concerns; controller review found pending-admission/Setup races, uncertain begin resource release and insufficient closure checks. Luna repairing with behavioral coverage. TODO condensed to current completion conditions.

### 2026-10-07 [spikeglx] [controller] Formalize existing E12 incident integration

- Task `gui-implementation`: E12 revision 20 formalizes the monitor's controller-owned prepared incident capability and recovery transition using the existing E06 registry; no fabricated process or warning-only substitute; exact scope, retained history and irreversible Abort/interruption required. Implementation and recovery checks in progress.
- Clarified E12 revision 19: the three alignment role classes need no invented mappings for inactive sources; optional trial-state/projector-flip/custom rows remain saved-channel metadata only.

### 2026-10-07 [gui] [visual_stimulus] Close pacing configuration development task

- Task `visual-stimulus-pacing-config`: typed file-owned pacing loader, startup/configuration resolution and exact held Setup policy propagation implemented and accepted in Sol re-review (earlier 34-test and 43-test checks); no new runtime test needed. Physical refresh/pulse/optical verification remains in the rig checklist.
- Boundary scan zero violations; source-size advisories for growing GUI/diagnostic owners returned to Luna. Fourteen edited documents have valid local targets/anchors. E06 revision 77 references E12's controller-owned session capability.

### 2026-10-07 [spikeglx] Verify digital bit limits from pinned manual

- Task `gui-implementation`: official manual at the mapping commit confirms NI 16-bit word packing and limits OneBox XD signals to the low 12 bits; the new mapping allowed bits 12–15, so Luna assigned correction and regression. Source URL/hash/size in dated evidence. Web cache fetch failed; permitted read-only curl succeeded. Source verification only, not pulse or rig acceptance.

### 2026-10-07 [tracking] [controller] Record intermediate combined test failure

- Task `gui-implementation`: Luna reports `.venv/bin/python -m pytest tests/tracking tests/controller -q -m 'not windows and not rig'`: 290 passed, one failed, one deselected. `test_shutdown_interrupts_at_once_and_completes_after_handoff_and_cleanup` saw FINALIZING rather than ENDED after its 50 ms sleep; isolated retry passed. Raw output not retained; cause unconfirmed. Combined run must be repeated after diagnostic cleanup repairs; the isolated retry is not a combined pass.

### 2026-10-07 [spikeglx] [tracking] [acquisition] Verify intermediate backend repairs

- Task `gui-implementation`: combined agent run 492 passed, five skipped, two deselected, one SpikeGLX monitor-test failure; its observation was 100 ns before the configured timeout, so the test was corrected to the exact threshold. Root passed 25 SDK/monitor/incident checks (0.18 s), raw retained. Inventory persistence and service/GUI integration pending.
- Luna reports 57 Tracking passes/one deselection with loopback (raw retained), nine manual-preview checks and one repaired shutdown timing check (test now awaits actual completion before releasing its gate). A sandbox attempt had six loopback binding errors. Diagnostic method-failure coverage, cohesion extraction, direct viewer and independent review open.

### 2026-10-07 [gui] [controller] Start configuration repair re-review

- Task `gui-implementation`: Luna reports all eight Sol findings repaired with actual managed-window regressions. Full offscreen GUI 260 passed, one deselected (117.01 s); focused eight passed; Ruff/format/mypy, 19-source generation, 581-module boundary check, whitespace pass. Sol re-review started; remaining GUI consumers/relaunch open.
- E12 monitor source review found missing writing-gate baseline retention, per-stream timestamps/history, same-observation recovery and failure-change coalescing; Luna assigned actual-loop coverage and repair. The earlier 25-test checkpoint covers only tested helper/incident behavior.

### 2026-10-07 [gui] [controller] Repair five residual configuration defects

- Task `gui-implementation`: Sol re-review passed ten focused GUI checks (251 deselected) but actual Qt manager/bridge probes reproduced five residuals: incomplete newer edits marked clean, first-run projector edits dropped, inactive Tracking kept enabled, incomplete drafts blocking New Session/close, direct Setup admitting a changed queued configuration revision. Luna assigned assembled-path regressions and repairs. The 260-test checkpoint did not establish these guarantees; configuration acceptance open.

### 2026-10-07 [tracking] [acquisition] [controller] [gui] Review full diagnostic slice

- Task `gui-implementation`: Luna reports 62 Tracking passes/one deselection (raw retained), nine manual-preview, one viewer check, scoped static passes. Sol's ten focused checks pass, but assembled probes reproduce six defects: asynchronous completion waiting, automatic-close release, foreign status evidence, acquisition release reservation, receipt/deadline enforcement, manual annotation lineage. Tracking report retains findings; repair and re-review required.
- Sol confirms first-use selected-stage diagnostics cannot bypass missing unrelated pose settings under the strict accepted-configuration path. Astra reviewing the smallest diagnostic-only contract refinement; nothing accepted yet.

### 2026-10-07 [tracking] [gui] [controller] Record Astra diagnostic refinement

- Task `gui-implementation`: Astra approved a separate bounded typed diagnostic draft, selected-stage resolution and an empty-mask image/preprocessing-only path. Accepted camera/configuration identity, controller-owned asset root/policy, exact cleanup and strict experiment submission unchanged; no dummy scientific settings or live mutation; settings changes need confirmed Close and fresh Begin. T08 revision 8, G01 revision 120, E07 revision 59, root register updated. Luna owns implementation plus six Sol repairs; design-only acceptance.
- Astra: explicit GUI relaunch within the current application generation implements E03/E08 (controller/session and containment preserved); whole-application replacement does not.

### 2026-10-07 [spikeglx] [controller] [gui] [repo] Check inventory RPC and rig dependencies

- Task `gui-implementation`: Luna's E12 checkpoint: 55 focused controller/incident/configuration/safety passes, two GUI inventory checks, eight authenticated controller RPC passes (covers unauthenticated access, lease-backed Get/Update, stale digest/revision rejection). An earlier concurrent GUI run hit a missing `asyncio` name; isolated retry passed, so that run is incomplete. Sol review has found concrete finalization/monitor/inventory defects; not E12 acceptance.
- Declared GUI extra added to the Windows test runner's installation list; root verified the edit and updated the rig handoff dependency description and stale pacing note. PowerShell/native runner not executed on macOS.

### 2026-10-07 [spikeglx] [controller] [gui] Review assembled E12 lifecycle and inventory

- Task `gui-implementation`: Sol reproduced eight defects: TOML section corruption, absent stop-margin scheduling, loss of confirmed stopped flags, reused resolved incident episodes, changed data directory at writing gate, inactive photodiode requirements, removable active mappings, custom-ID draft restore. Runtime report retains findings; Luna assigned repairs/regressions before V01 continues. Sol passed 13 controller, 38 shared/lifecycle, three authenticated RPC tests; GUI subset one pass/one failure then cleanup exit 138. No E12 or full GUI acceptance.
- Root: current GUI bootstrap/diagnostic state lacks an authoritative Tracking endpoint/process route; Luna owners coordinating the interface.

### 2026-10-07 [gui] [tracking] [spikeglx] [repo] Check first-use integration and source boundaries

- Task `gui-implementation`: first-run Projectors has no display-profile import action though required (calibration import is a different format); reachable bounded adoption flow assigned. Also found nonfinite SpikeGLX duration acceptance and early diagnostic resolver conflicts with selected-stage-only validation; Luna repairing. Calibration dispatch picks identities from the latest snapshot after queueing, allowing drift; assigned exact submission identity and protected asset binding with queued-path regressions (no runtime reproduction).
- Seven edited TOMLs parse; edited Markdown local targets exist; boundary scan 586 modules, zero violations; GUI main/bridge owners returned for extraction. In-flight Ruff found eight unused imports in Tracking resolver/session: incomplete checkpoint, not a final static pass.

### 2026-10-07 [spikeglx] [controller] [gui] Re-review E12 repair checkpoint

- Task `gui-implementation`: Luna reports all eight Sol findings plus finite-budget validation repaired. Controller/shared/configuration/safety 65 passed; GUI inventory/restore two passed; authenticated controller RPC eight passed; Ruff/format, Windows mypy, boundaries zero, whitespace clean. Sol re-review started before V01. Root raised uncertain release without Started, pending normal-stop task supersession and finalization-bound retention for review; no final acceptance.
- GUI Luna: profile import and captured calibration asset/revision support, eight focused passes; queued identity regressions, Tracking integration, extraction and same-generation relaunch open.

### 2026-10-07 [repo] [gui] Verify collection and queued calibration identity

- Development suite collects 1,165 of 1,170 tests with `not windows and not rig` (five deselected, 1.77 s); raw collection/provenance in dated wiring evidence. Collection only; implementation in progress.
- Luna reports queued calibration Open revision/asset hash and Close diagnostic identity checks plus accepted-configuration E12 role binding; six focused GUI tests and scoped Windows mypy pass. Full GUI review, live Tracking, relaunch and integrated execution pending.
- Refs: `gui-implementation`

### 2026-10-07 [spikeglx] [controller] [gui] Repair retained stop-scheduler defects

- Task `gui-implementation`: Sol's probes reproduce six residuals: uncertain released trial classified inactive; earlier interruption suppressed by pending normal stop; withdrawn timer reused for a later trial; mutation/late state after finalization deadline; insufficient three-call stop budget; inactive bit-mapped photodiode still requiring saved channel. Scheduler extraction and regressions assigned to Luna (ARCH-002/E12). Independent suites (61 controller/shared, two GUI) passed but missed these paths; no acceptance.
- ManagedDashboardWindow does not persist local raw drafts on closure, unlike the review window; truthful preserve/discard with close/reopen coverage assigned; backend accepted history stays authoritative.

### 2026-10-07 [gui] [repo] Refine closure and inspect viewer behavior

- Task `gui-implementation`: under GOV-001, explicit discard/cancel on managed close satisfies truthful unsent-draft handling without a separate persistence/rebase system; Cancel keeps edits; authoritative history distinct. Direct Tracking viewer inspection found automatic reopening after detachment, numeric stage labels and uncertain-close button gating; repairs assigned. Camera-viewer, MCU and diagnostic orchestration now use focused GUI helpers.
- Eighteen edited Markdown files have 351 valid local anchor links; `git diff --check` passes. Documentation checks only; runtime suites pending.

### 2026-10-07 [tracking] [controller] [acquisition] [gui] Validate partial diagnostics repair checkpoint

- Task `gui-implementation`: Luna reports six diagnostic lifecycle/identity/release findings repaired and Astra's selected-stage resolver implemented. Full Tracking 69 passed, one deselected (2.05 s); focused controller/acquisition/Tracking 63 passed (1.37 s); root verified raw logs. Covers empty-mask/no-native-init, flow-only, pose-only, transitive unavailable stages, partial quality inputs, inactive experiment Tracking, exact release. Ruff/format, Windows mypy, boundaries pass; lifecycle/processing owner cohesion is review work. Sol re-review and GUI binding required.

### 2026-10-07 [spikeglx] [tracking] [controller] [visual_stimulus] Review stable repairs and begin calibration runtime

- Task `gui-implementation`: Luna's second E12 checkpoint extracts the 173-line stop scheduler, binds exact trial timing, withdraws cancelled schedules, handles uncertain released activity, cancels at finalization bounds, grants the three-call budget. Controller/shared/setup/lifecycle 85 passed; GUI two; authenticated RPC eight; static checks pass. Sol independent review pending; earlier findings unaccepted until then.
- Tracking owner-loss cleanup corrected to the original recovery budget; five controller tests and static checks pass. Luna began V01 runtime implementation; GUI relaunch and Astra final checks open.

### 2026-10-07 [gui] [tracking] [controller] Connect direct diagnostic viewer

- Task `gui-implementation`: GUI Luna reports typed Begin/Close drafts bound to accepted camera preview/revision, registered Tracking route, authenticated bounded latest-frame polling and explicit viewer reopening; controls locked until confirmed closed evidence; active-phase close offers discard/cancel. 13 focused GUI tests and static checks pass; same-generation relaunch next. Sol backend review reproduced empty-mask rejection at the outer gateway and an extended preparation deadline; full managed diagnostic acceptance open.

### 2026-10-07 [tracking] [acquisition] [controller] [spikeglx] Review complete diagnostic data path

- Task `gui-implementation`: Sol confirms the six E12 scheduler repairs (one inter-trial Abort classification defect assigned). Diagnostic re-review found five defects: real capture_once leaves the manual Tracking ring empty; backend Begin rejects empty masks; native preparation extends Begin deadline; unavailable selected status disappears; pre-Begin lease loss can falsely close an attached transfer (source-traced; others reproduced). Real gateway/capture/transfer regressions assigned. Independent selections passed 63 E12, 52 diagnostic integration, nine runtime diagnostic, 12 acquisition worker checks, which do not cover the failing paths.
- Rig checklist updated (first-run profile adoption, draft discard/cancel, empty/partial diagnostics, viewer reopening, paired-stop edge cases). No rig operation ran.

### 2026-10-07 [tracking] [acquisition] [controller] Verify actual diagnostic-path repairs

- Task `gui-implementation`: Luna repaired the five findings and injected the focused diagnostic service owner. Acquisition worker/manual-preview, controller diagnostic and full Tracking: 99 passed, one deselected; root verified raw output. Tests exercise actual capture_once, backend Begin, NativeSession and acquisition transfer owner. Windows mypy, Ruff/format, 592-module boundaries (zero violations), whitespace pass. Sol re-review started; no final acceptance.
- Runtime report consolidated to acceptance map and unresolved findings.

### 2026-10-07 [tracking] [acquisition] [controller] Accept diagnostic backend repair slice

- Task `gui-implementation`: Sol found no remaining issues in the five repairs and independently passed the same 99 tests (one deselected, loopback permitted). Authenticated gateway probe ran empty-mask Begin through the actual pipeline (frame 17, 10,000 image bytes) and confirmed exact Close with the original deadline; only the Windows ring boundary adapted. Accepts the backend development slice, not full GUI or native/rig integration. V01, GUI relaunch, combined dev checks and Astra final verification open.

### 2026-10-07 [gui] [launcher] [supervisor] [visual_stimulus] Complete remaining first-use seams

- Task `gui-implementation`: GUI Luna implemented the explicit reopen signal and authenticated exact-release launch path with focused checks; normal-script flag forwarding, original relaunch deadline propagation and integration remain. Fresh bootstrap omits unused child and privileged controller/supervisor tokens. Retiring an empty GUI Job proves only process absence, not backend resource/output cleanup.
- V01 source review: first-use admission/preparation wrongly depends on an initialized display/profile; Luna adopting the protected diagnostic profile and typed file policies before Setup, preserving cleanup/restoration evidence. No decision or scientific default inferred.

### 2026-10-07 [gui] [visual_stimulus] [controller] [launcher] Review first-use cleanup and broad static checkpoint

- Task `gui-implementation`: V01 preparation timeout discarded its still-running future and failed preparation could discard uncertain source closure; retained late-result/resource cleanup assigned. Sessionless diagnostics keep their own cleanup evidence; no new catalogue protocol needed. Normal launcher script imported the package before selecting the repository environment; bootstrap-safe forwarding assigned.
- Broad Ruff of `src tests tools scripts` passes; Windows mypy eight errors in three actively edited calibration files; formatting flags five calibration files; boundaries 592 modules, zero violations. In-progress checks. Luna: Dashboard 274 passed, six failed, one deselected; repairs/rerun required. Development guidance updated for the wiring stage; first doc patch failed context matching without changes, corrected patch applied; final commands/status await reviewed completion.

### 2026-10-07 [gui] [controller] [supervisor] [launcher] [acquisition] [tracking] [visual_stimulus] Verify assembled backend checkpoint and inspect captures

- Task `gui-implementation`: acquisition, Tracking, supervisor, launcher, shared, client and platform selection with loopback 510 passed, six skipped, three deselected (4.84 s); preceding attempt stopped at collection on an edited calibration syntax error (both raw outputs retained). Tracking contracts 48 tests; Visual Stimulus contracts 42 tests/79 subtests; 19 Tracking and 11 Visual Stimulus schemas match canonical models. Full GUI/V01 integration and Astra final verification open.
- V01 controller Open reserves before async reads and rechecks authority/backend/configuration/deadline before dispatch; Luna reports 21 admission/lifecycle checks and static passes; native leaf 19 focused passes, cohesion extraction pending Sol review.
- Root rejected visual acceptance of five of ten initial managed-window captures (missing runtime theme, review-only Tracking text); themed wide/720px captures requested. No Windows visual acceptance.

### 2026-10-07 [visual_stimulus] [spikeglx] [gui] [repo] Review calibration leaf and native packaging boundary

- Task `gui-implementation`: Luna completed the V01 native leaf, extracting diagnostic request preparation into a focused resource module; 19 focused and static checks pass; Sol review started. Full Visual Stimulus: 146 passed, one skipped, one deselected, one failure in authenticated startup InitializeDisplay (pre-Setup resource announcement conflicts with the session-only coordinator catalogue); V19 integration repair assigned without weakening cleanup evidence.
- E12 inter-trial Abort predicate corrected to recognize confirmed trial log closure before retained Started/Release history; 46-test selection passes; Sol review pending.
- `python -m build --no-isolation` exits at dependency discovery: native DLLs package only on AMD64 Windows, so macOS cannot validate the package; DLLs/build guard intact. Raw output retained for the Windows rig handoff.

### 2026-10-07 [visual_stimulus] [gui] Return native rendering and narrow-layout findings for repair

- Task `gui-implementation`: Sol reproduced three V01 native-leaf defects despite 46 focused passes/one skip: direct framebuffer presentation bypasses V15 correction, drawer creation/release uses the wrong output context, successful generic release retains a calibration key that blocks another presentation. Repairs assigned to Luna. ARCH-002 accepts engine display/restoration ownership and the preparation extraction; native calibration resources need a focused owner.
- Root's themed 720px inspection found unreadable SpikeGLX stream/index/channel/bit controls and clipped headers; responsive sizing and managed-snapshot capture fixtures assigned. The fixture's contradictory Observer/control-held labels are not an observed runtime defect.

### 2026-10-07 [gui] [visual_stimulus] [spikeglx] Trace remaining first-use UI gates

- Task `gui-implementation`: calibration Launch still gated by initialized display resources in `ManagedGui._install_calibration_state`, blocking the pre-Setup path; managed first-use/click coverage and gating repair assigned, retaining unknown-cleanup blocking and exact identities.
- SpikeGLX pairing/endpoint widgets remain editable local review controls while runtime uses saved host-file settings (E12 keeps them file-owned). Luna adding typed read-only enabled/address/port projection to the inventory read; pulse mapping keeps its separate file update. Development guide updated, including the same-generation reopen command. Final Sol/Astra acceptance open.

### 2026-10-07 [gui] [launcher] [supervisor] [tracking] [visual_stimulus] Review assembled interaction failures

- Task `gui-implementation`: Sol confirms the five prior configuration repairs but managed snapshot probes reproduce diagnostic Close overwritten by the general page view (re-enabling Begin, erasing stage/timing status), lost GUI successor registration after an uncertain relaunch reply, and dialog dismissal treated as destructive close in `_save_failed`. Repairs/regressions and ARCH-002 extraction of submission, device binding and diagnostic transport/codec assigned to Luna. Independent 55 launcher/registry/registration and 19 GUI checks missed these.
- Root inspected eleven themed snapshot PNGs: narrow values readable with scrolling; HUD has a hardcoded Observer label despite held control; source correction and menu contrast repair assigned. Dashboard checkpoint 280 passed, one deselected (116.04 s), before the newest repairs.
- V01 native leaf uses a focused calibration renderer; root verified 44-pass log (0.42 s); Sol re-review pending. Luna reports startup Idle-to-Setup promotion and sessionless Open/Close/reopen/recovery pass; safety cleanup during in-flight preparation still in progress.

### 2026-10-07 [gui] [launcher] [visual_stimulus] Accept native leaf and preserve launcher backstop

- Task `gui-implementation`: Sol accepts all three V01 native-leaf repairs after 44 independent passes (0.40 s), including correction/material paths, GL context ownership and retained partial closure; accepts the 176-line calibration owner; nine calibration tests use distinct fixtures. Worker safety integration separate.
- Sol found synchronous GUI relaunch RPCs run inside the launcher backstop loop and can overrun an armed shutdown deadline; Luna moving one retained exact attempt off that loop, preserving reconciliation and shutdown gating. Authority text and menu contrast fixes pass two focused tests.
- Correction: the 280-pass checkpoint's raw summary is retained but its exact invocation was not preserved; a candidate command from an unrelated 2026-10-05 script is rejected and metadata marks the command unavailable.

### 2026-10-07 [gui] [tracking] [visual_stimulus] [spikeglx] [controller] Review stable safety integration

- Task `gui-implementation`: Luna's controller/E12/Visual Stimulus checkpoint passes 201 tests, one skipped, one deselected, static checks pass; exercises active Shutdown, late preparation cleanup, first-use/repeated calibration, uncertain closure. Sol review started. Completed-trial gap predicate checks retained log closure directly.
- ARCH-002: direct authenticated Tracking frame transport and diagnostic-only draft encoding extracted. Managed screenshots confirm authority HUD/menu contrast repair; combined execution pending. Runtime and Visual Stimulus assessments consolidated.

### 2026-10-07 [visual_stimulus] [controller] Identify safety integration gaps

- Task `gui-implementation`: Sol repeated the 201-pass checkpoint, then found two uncovered V01 paths: actual controller assembly lacks a display-calibration owner-loss observer; cleanup with no prepared result raises before retained protected-source release can retry. Current defects, not rig uncertainty. Luna repair and actual-owner regressions required before final acceptance.
- Refs: E12

### 2026-10-07 [gui] [tracking] [repo] Complete focused GUI extraction and rig-runner preparation

- Task `gui-implementation`: Luna's direct-frame transport and diagnostic-codec extraction passes seven owning GUI tests; scoped Ruff/format, Windows mypy, compilation and 595-module boundary checks pass. Rig runner now imports QtCore/QtWidgets in prerequisites, installs the GUI extra and checks scripts with Ruff/format. PowerShell execution/parsing unavailable on this macOS host; exact PyQt import smoke passes locally.
- Development instructions and the single rig checklist describe first-use untimed calibration, explicit GUI reopen, exact-frame annotation, delayed relaunch/shutdown and pending-close checks. No hardware command issued.

### 2026-10-07 [launcher] [visual_stimulus] [controller] Preserve recovery identity without extending operations

- Task `gui-implementation`: Sol reproduces ambiguous calibration Open discarding the exact recovery identity and repeated safety cleanup replacing its first deadline; Luna includes these in the pending safety repair. E12 gap classification and immutable host inventory readback have no remaining Sol findings.
- Sol's relaunch coordinator/RPC-adapter probes confirm two residuals: an expired launch deadline prevents later read-only reconciliation, and a definite failure before PlanLaunch leaves a never-submitted attempt permanently retained. Luna is separating those outcomes while keeping submitted launch identity/deadline frozen. No blind launch retry authorized.

### 2026-10-07 [launcher] [supervisor] Preserve partially launched GUI ownership

- Task `gui-implementation`: Sol's supervisor service/registry probe creates a live job member, fails exact confirmation and gets REJECTED/PROCESS_MISMATCH while the launch stays CLEANUP_REQUIRED; generic RPC rejection therefore cannot be classified as never submitted. Retention of exact submitted identity assigned to Luna; only a definite pre-Plan failure may clear the attempt without authoritative reconciliation.

### 2026-10-07 [gui] [tracking] [spikeglx] Review actual managed interaction paths

- Task `gui-implementation`: Sol accepts the Tracking frame-transport/diagnostic-codec extraction with six independent selected passes. ManagedGui probes confirm first-use calibration before display initialization, read-only host values, explicit discard/cancel, confirmed-history close and exact-frame diagnostic state.
- A delayed inventory response at an old revision escapes as uncaught ClientError; Luna owns the slot-boundary repair. GUI selection reports 13 passes and one stale lightweight fixture failure after close extraction; fixture being updated without behavior change.

### 2026-10-07 [gui] [launcher] [supervisor] Accept managed GUI and relaunch repairs

- Task `gui-implementation`: Sol accepts GUI extraction, stale inventory handling, close choices, diagnostic projection and relaunch repairs. Expanded selection passes 22 tests; focused relaunch selection passes nine (overlapping scopes, not additive). Supervisor service/registry/dispatcher probe verifies a rejected partial native launch retains CLEANUP_REQUIRED/live-member ownership and exact query-only recovery; Console distinguishes proven pre-dispatch failure from uncertainty.
- Luna's final focused selection passes 17 tests (303 deselected). Themed ManagedGui capture fixture updated for the extracted collaborator after an initial stale-method failure; regeneration succeeds; Dashboard/SpikeGLX/Tracking720 captures preserved with script/provenance. Calibration safety review, combined tests and Astra final checks remain open.

### 2026-10-07 [launcher] [supervisor] Complete terminal relaunch reconciliation

- Task `gui-implementation`: Sol's exact RELEASED-state probe finds reconciliation still returns unknown and retains the ended attempt forever. Luna is adding a distinct exact terminal disposition so only a later explicit operator request creates a fresh identity. Unknown and partially live attempts remain retained; no automatic launch/replay.

### 2026-10-07 [visual_stimulus] [controller] [spikeglx] [gui] Check assembled development state

- Task `gui-implementation`: terminal RELEASED repair accepted by Sol with ten focused launcher passes. Assembled offscreen/non-Windows/non-rig run started with authenticated loopback. Ruff passes, 793 files meet formatting, 597 backend modules have zero boundary violations. Windows-target mypy finds one missing explicit private-helper export after inventory extraction; owning public import assigned to Luna. 19 edited Markdown documents have 711 valid local links/anchors; seven edited TOMLs parse; dependency check clean.
- Sol finds controller owner-loss tests substitute immediate backend closure and miss actual pending preparation (coordinator Close has no projected output identity; worker Close rejects a pending job). Assigned retained exact Open identity, bounded preparation cleanup and a real coordinator/worker regression. Combined suite has one failure awaiting traceback; checkpoint, not final acceptance.

### 2026-10-07 [gui] [visual_stimulus] [repo] Resolve combined-check fixture failures

- Task `gui-implementation`: assembled run gives 1,225 passed, seven skipped, five deselected, two failures (131.46 s). Both are stale GUI fixtures after reviewed changes (managed pairing must be disabled/read-only; retained-warning adapter needs the extracted calibration eligibility callback). Luna repairs both; isolated regressions pass without weakening behavior.
- Installed declared `tifffile==2025.5.10` to remove the decoder-test skip. Windows process and Win32 ring skips remain platform limits. Pending-preparation and pre-dispatch cancellation repairs continue; combined run is a checkpoint to be repeated on stable source.

### 2026-10-07 [gui] [controller] [supervisor] [tracking] [spikeglx] [repo] Begin Astra final review of accepted slices

- Task `gui-implementation`: Astra begins final independent review of Sol-accepted GUI, relaunch, Tracking and E12 slices while Luna/Sol finish two calibration residuals. Final acceptance remains contingent on calibration review and stable combined checks.
- Root regenerated all 19 Protobuf sources into isolated temporary output and compared all 57 generated files to installed bindings: zero mismatches, no production generated-file edits.

### 2026-10-07 [gui] [tracking] Resolve Astra partial diagnostic finding

- Task `gui-implementation`: Astra reproduces a partial-quality codec defect via encode_diagnostic_draft and the real resolver: Water-to-Fin lacks the visible fin sampling wedge, edits to an existing Fin wedge retain prior values, Water can retain Fin fields. Full-stage encoding handles these; prior tests missed the partial path. Focused codec and owning regressions assigned to Luna; no new scientific choice. Root's second assembled run remains a checkpoint until this repair is reviewed.

### 2026-10-07 [gui] [tracking] [spikeglx] [controller] Close codec finding and repair persistence scheduling

- Task `gui-implementation`: Luna's partial Fin codec regression passes with all 20 owning Tracking configuration tests. Astra confirms Water-to-Fin45°/90°, changed Fin60°/120° and Fin-to-Water removal via the real resolver; Sol review follows. Astra's GUI selection passes 29 (260 deselected).
- Astra's inventory/control-owner probe stalls only filesystem I/O and proves the global lifecycle lock stays held, blocking independent safety/lease work. Luna is moving persistence outside the lock with one retained bounded operation, authority/configuration checks and Setup/conflicting-write exclusion; a timeout must not discard an outstanding disk write. Sol requires the blocked-preparation calibration test to await worker Close application, not RPC admission, before asserting zero late presentations.

### 2026-10-07 [controller] [gui] [tracking] [visual_stimulus] Enforce unresolved-ownership configuration gates

- Task `gui-implementation`: second full run gives 1,228 passed, six platform skips, five deselected, one failure in the known calibration admission-versus-worker-application race (132.95 s). GUI failures closed; TIFF regression now executes. Sol accepts the Fin codec repair (20 owning passes); Astra confirms resolver behavior.
- Astra reproduces E07 revision-changing edits accepted after exhausted unclean cancellation, during active Tracking diagnostics, and while manual cleanup is pending; these can strand diagnostic revision identity. Luna adds one shared ownership eligibility check to configuration admission and commit, with the inventory-persistence reservation; no-op semantics may not erase blockers. Applies the existing E07 cleanup rule, not a new policy.

### 2026-10-07 [controller] [spikeglx] [tracking] [visual_stimulus] Accept final ownership and persistence repairs

- Task `gui-implementation`: Sol and Astra accept bounded off-lock inventory persistence and shared configuration guards. Astra probe confirms safety-lock responsiveness, retained unconfirmed write ownership and truthful late commit; inventory/configuration suite passes 52. Authenticated pending-preparation calibration tests pass independently after matching generated worker Close identity; zero late presentation asserted.
- Setup's atomic commit needed the same ownership checks after asynchronous validation; Luna shares the guard. Sol passes 30 transaction tests (0.80 s); Astra repeats 30 (0.82 s) and its three-case owner probe passes. No source findings remain from either reviewer.
- Third combined run passes 1,237, six native-platform skips, five deselections (134.92 s); a final run on frozen source is underway. Final-source Ruff/format and Windows mypy pass (793 files/683 sources); boundary results retained with the 954-file source hash manifest.

### 2026-10-07 [gui] [controller] [supervisor] [launcher] [acquisition] [visual_stimulus] [tracking] [spikeglx] [shared] Complete runtime GUI wiring development acceptance

- Task `gui-implementation` completed: shared review layout, managed bindings, exact configuration/authority/close/relaunch behavior, real Tracking diagnostics/annotation, untimed calibration and E12 integration implemented. Luna → Sol6.1 → Astra sequence complete; all reproduced findings repaired and rechecked under E07/E08/E12/T08/V01/E03 and ARCH-002.
- Frozen final source: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests -q -ra -m 'not windows and not rig'` passes 1,240, six native-platform skips, five deselections (128.20 s); all 954 source/input hashes unchanged. Ruff passes; formatting 793 files; Windows-target mypy 683 files; boundaries 597 modules, zero violations. Pure Tracking contracts 48 tests; Visual Stimulus 42 plus 79 subtests. Protobuf/JSON schemas match. No test-module typing pass is claimed.
- Astra accepts development scope. Native package build blocked by the AMD64 Windows guard on macOS; PowerShell, Windows/native devices, optical timing and full-workload checks did not run. Scientific, encoder and firmware deferrals unchanged.
- Removed `gui-implementation` from TODO; `spikeglx-controller-integration` and `projector-calibration-launch` retain only rig acceptance; Windows startup/relaunch and narrow-layout follow-ups remain open; owner-paused camera/MCU checks remain paused. No rig/hardware operation started.

### 2026-10-07 [repo] [gui] Finalize wiring handoff records

- Reconciled completed development work and remaining rig-only tasks in existing reports, TODO and the single rig guide. Link/anchor check passes 19 edited Markdown documents and 714 local references; seven edited TOMLs parse; `git diff --check` passes. No implementation changes followed the frozen-source test run.

### 2026-10-07 [gui] [controller] [supervisor] [launcher] [acquisition] [visual_stimulus] [tracking] [spikeglx] [repo] Begin current Windows rig wiring acceptance

- Task `runtime-gui-rig-wiring-acceptance`: owner requests necessary rig checks and disposable-file cleanup. Checkout clean at `08d146d0d97847cb3f395144886fc175dc627487`; no running Python/CephVR/FFmpeg/SpikeGLX/Pylon owner. Scientific and encoder deferrals unchanged.
- Initial `tools/test_on_rig.ps1 -OutputDirectory reports/rig-wiring-evidence-2026-10-07/automated` (Windows/Python 3.11.15): syntax, Ruff/format, boundaries, pure contracts/schema drift and AMD64 build pass. Stale ignored Protobuf bindings cause 488 mypy diagnostics and collection errors (deployment-preparation failure, not behavioral); original logs retained. Ran `tools/generate_contracts.py` (19 sources) and started a full runner repeat. Managed Python verification passes.

### 2026-10-07 [gui] [controller] [supervisor] [acquisition] [tracking] [visual_stimulus] [spikeglx] [repo] Record current Windows and device blockers

- Task `runtime-gui-rig-wiring-acceptance`: regenerated native Qt run crashes in GUI fixture teardown (access violation `-1073741819`). Offscreen Windows run: 1,252 passed, nine GUI assertion failures (eight layout/clipping, one native-vs-normalized path string), four symlink-privilege skips, one rig deselection (138.86 s). Original runs retained; no assertions/deadlines weakened.
- ARCH-002: added only the generated SWIG wrapper filename to `pyproject.toml`'s generated-source mypy exclusion; Windows mypy passes 683 sources. GPU rig smoke passes one test (0.48 s); pure contracts and AMD64 build pass.
- Managed runtime starts all seven roles, acquires GUI control, stays alive over an hour. Computer-use capture times out on app approval; no GUI click/viewer acceptance claimed. Authenticated SDK connection times out with a native TCP connect failure and an unretrieved late future exception.
- Headless takeover succeeds. COM8 CAPS: protocol 2 / `cephvr2_uno_1`; MCU Status and Stop fail required-result evidence. Camera identity checks pass. Two Behavior D10/Line4 Start/Stop cycles complete, then camera-worker COORDINATOR_HEALTH_LOST faults trigger shutdown. BehaviorSquid: Tracking enable/PFS import/readback/Finish editing pass (Line2, Mono8, 1588x1344, 5,000 us), Start fails; Restore rejected while preview ownership remains; no blind replay. Launcher exit receipt proves all owned processes absent. Full receiver/viewer/Tracking diagnostic acceptance open.

### 2026-10-07 [gui] [launcher] [supervisor] [controller] [acquisition] [tracking] [visual_stimulus] [spikeglx] [repo] Finish bounded rig execution and cleanup

- Task `runtime-gui-rig-wiring-acceptance`: GUI-loss injection/reopen passes (29916 → 8632) in unchanged generation. Duplicate-launch N preserves endpoint; Y obtains exact all-owned-processes-absent receipt before a fresh generation. Final Shutdown succeeds; receipt, no managed processes and free guard confirm closure. Mouse-driven close/reconnect acknowledgement unverified (app approval timed out).
- Tracking receiver isolation first stops because managed cleanup left FrameStart Off. Restoring owner's PFS On mode gives 81 valid frames in two seconds on COM8 D11 → Line2, matched ON/OFF; owners close, pre-probe Off restored. Not sustained 60 Hz or managed diagnostics. No firmware, remote recording, pulse-map or operator-file change; 958 input hashes unchanged.
- Reports, rig checklist and TODO retain Windows failures and bounded passes; camera heartbeat defect tracked; incomplete wiring acceptance Blocked. Projector Launch/Close lacks accepted profile/arena/output inputs; remote SpikeGLX unreachable. Deferrals unchanged.
- Ruff/format (793), Windows mypy (683), dependency, TOML, whitespace pass; eight Markdown/290 links pass. Evidence in `reports/rig-wiring-evidence-2026-10-07/`. Cleanup removes 79 workspace directories / 980 files / 56,986,907 bytes (54.3 MiB) of disposables; no tracked/unique evidence deleted. Rig acceptance not complete.

### 2026-10-07 [gui] [controller] [acquisition] Record owner MCU diagnostic results

- Task `mcu-managed-connection-and-io`: preserved owner's controller-route GUI console paste (revision/generation/duration labelled missing). D2, D9, D10 diagnostic Start/Stop pairs report Completed; D2 stops with 120 rising edges. A11 specifies output edge counts are zero, so D9/D10 counts do not indicate failed output or measured frequency.
- Reported completion is distinct from earlier agent-run Status/Stop failures; physical D2 source, D9 level, D10 requested 30 Hz waveform/receiver and ordinary-command repeat remain open. No hardware action or new test. Validation: 295 links/anchors in eight Markdown files, 958 hashes unchanged, TOML parses, `git diff --check` passes.

### 2026-10-07 [gui] [controller] [acquisition] Correct misleading signal-test feedback

- Task `mcu-managed-connection-and-io`: owner clarifies the console was for physical signal testing with SpikeGLX observation; the paste is command/diagnostic evidence, not completion of that test. Mapped receiving channels and observed D9/D10/D2 results remain pending.
- Under G01/A11, output rows now show firmware-reported Trial state HIGH/LOW and camera pulse output running/stopped instead of input-only zero-edge wording; D2 rising-edge counts kept. ARCH-002: existing focused panel, no new dependency/state/timing.
- Six owning GUI tests pass (285 deselected, 4.59 s); Ruff/format pass; Windows GUI mypy 124 sources; boundaries 598 modules zero violations; 305 links/anchors in ten Markdown files; whitespace passes. No serial takeover, output command or restart; feedback applies at next GUI restart. No physical pass claimed.

### 2026-10-07 [gui] [controller] [acquisition] Repair Preview attachment and pending-operation rejection

- Task `camera-preview-gui-binding`: owner reports Test enabled → Start capture → Preview → Stop with repeated rejection (controller `205bc097-d44b-4d88-9325-19ad87630566`; snapshot shows a camera timeout without command kind, button not conclusively identified). Owner lease/runtime untouched.
- Under A03/A10/G01/E08: acquisition accepts the controller's authenticated gui/cli consumer and attachment-only omission of unchanged loaded policy; conflicting supplied policy/revision/identity/deadline stay strict. A new transfer to the same consumer waits for confirmed previous release. GUI Preview waits for confirmed consumer completion. Sessionless camera/MCU failures now use the device reporter; failed attachment releases its operation slot without claiming capture/pulses stopped. Six regressions fail before and pass after.
- Windows checks: acquisition/controller/client 495 passed, two symlink-privilege skips (6.67 s); camera/viewer GUI 13 passed (3.47 s); Ruff/format 440 files; mypy 387 sources; boundaries 598 modules zero violations. Native reader and isolated tests do not prove real camera viewing; restart and actual Start → Preview → Stop/release remain open with capture timeout/heartbeat and Tracking acceptance.
- Cleanup removes 64 directories / 766 files / 32,527,493 bytes (`preview-repair-cleanup.json`); 304 links pass; 12 input hashes unchanged.

### 2026-10-07 [gui] [controller] [acquisition] Prepare MCU-generated pulse counting

- Task `mcu-managed-connection-and-io`: owner selects MCU-generated transition counts over SpikeGLX received counts. A11 revision 37, MCU wire protocol 3, acquisition policy/config version 13. Ordinary session/STATUS counters remain absent; diagnostic counts identify observed input or generated output rises. Firmware counts per active diagnostic, resets per test, saturates at uint32 maximum, retains counts after Stop; host rejects old firmware and malformed/zero output counts.
- Uno compile passes: 11,078 flash / 1,112 SRAM bytes; protocol 3 image SHA-256 `0e4d05e6466328f26b33866793d895d65943ea4dfbd35165a2a090f2023bf630` retained. MCU/configuration checks 45 (1.07 s); acquisition/controller/client 508 with two symlink-privilege skips (8.05 s); six offscreen GUI cases (3.82 s); Ruff/format 331 files, mypy 305 sources, boundaries 598 modules zero violations.
- Reports/checklist distinguish prepared implementation from installation/board acceptance; host needs matching protocol 3 firmware after restart. No upload, serial takeover or physical pulse test ran; installation authorization requested. Cleanup removed 65 targets / 830 files / 32,352,178 bytes. Concurrent camera-viewer work advances policy/config to 14; 45 MCU cases pass again (1.35 s). Final handoff: 331 links/anchors in 11 Markdown files.

### 2026-10-07 [gui] [controller] [acquisition] Move camera display ownership to acquisition

- Task `camera-preview-gui-binding`: owner confirms repaired Preview works (user-reported, no retained generation/settings/timing provenance; heartbeat/full rig checks open) and requests backend-owned OpenCV windows as in CephVR1.0. Implementing Show/Hide commands, coordinator-owned private readers/windows, exact native-ledger release and monotone visibility observations; GUI sends intents and holds no reader. A10 revision 53, G01 revision 121; policy 14 binds the viewer.
- Replaced OpenCV headless 4.13.0.92 with the matching GUI package (original build reports GUI NONE). Initial checks expose fixtures expecting GUI attachment and one callback annotation; fixes and validation in progress. One unrelated GUI planner clipping test fails. No camera/serial operation, runtime restart or physical-camera OpenCV acceptance.
- Refs: E08, E14

### 2026-10-07 [gui] [controller] [acquisition] Repair camera MCU test configuration and failure evidence

- Task `mcu-managed-connection-and-io`: owner's console and no-D10-pulses observation preserved. Source reproduction finds camera Test omitted CONFIGURE required by firmware before DIAG_START (D9/D2 do not require it). Native read-only status attempt fails with missing operator credential; live firmware rejection not collected. No takeover, hardware command, restart or upload.
- Under A11/ARCH-002, the manual-pulse owner configures only the selected camera role through its serial owner and original deadline before starting; rejection prevents start. Controller retains backend failure text. Correction: the earlier counted-readiness suite missed controller Connect's hardcoded protocol-2 check, now the protocol-3 parser constant.
- Before: six failures/one pass; after: seven pass. Native acquisition/controller/client 526 with two symlink-privilege skips (7.28 s); Ruff/format, mypy 267 sources, boundaries 601 modules zero violations; 12 Markdown/347 links. Firmware unchanged and uninstalled; manual installation authorization pending. Cleanup 48 directories / 553 files / 10,545,258 bytes (`mcu-camera-cleanup.json`).

### 2026-10-07 [gui] [controller] [acquisition] [tracking] Validate backend-owned OpenCV preview

- Task `camera-preview-gui-binding`: completed A10/G01 Show/Hide. Acquisition owns private latest-frame readers and Win32 OpenCV windows; Show waits for a converted image to reach the window; X/Hide leaves capture/pulses active. Deadlines, run/consumer identity and cleanup evidence stay strict; native-ledger release failure blocks buffer closure while SDK/pulse cleanup still runs. GUI loses its Qt reader. ARCH-002 separates viewer commands from manual capture; manual capture (541 lines) and camera admission (501) remain cohesive.
- Isolated Windows validation: acquisition/controller/client 526 with two symlink-privilege skips (8.89 s); GUI/bridge 17 (4.60 s); first-image/reopen/cleanup 64 (0.82 s). Two HighGUI windows show synthetic ring pixels; native X closes one without stopping producers; failures retain truthful state. Unrelated planner clipping remains historical. No physical camera, serial takeover, upload or runtime interruption.
- Ruff/format 444 files; mypy 391 sources; boundaries 602 modules zero violations; build and pip check pass; OpenCV reports WIN32UI.
- Cleanup: 56 directories / 591 files / 73,826,542 bytes (`opencv-cleanup.json`); 448 links, 44 input hashes pass. OpenCV compatibility: 72 Tracking cases (2.30 s), one rig workload deselected; no Tracking algorithm change or GPU pass claimed. Post-Tracking cleanup 235 files / 2,674,004 bytes; aggregate 826 files / 76,500,546 bytes; 492 links pass. Actual camera OpenCV viewing and heartbeat/Tracking remain queued after MCU installation/full restart.

### 2026-10-07 [gui] [controller] [acquisition] Install matching MCU firmware and retest native preview

- Tasks `mcu-managed-connection-and-io`, `camera-preview-gui-binding`: owner authorizes runtime stop, flash backup, manual upload, restart, retest. Shutdown of controller `028d0e0b-7e6e-47e8-8814-07818b27489d` succeeds; receipt confirms processes absent. Backup SHA-256 `dcc0f4d1c7f50c45115bf45c591d6df8d4bc6d77f52ba9e0785736678716e19a` (flash only, not EEPROM/fuses). Arduino CLI verified upload of image `0e4d05e6…bf630` exits zero. CAPS reports protocol 3 / `cephvr2_uno_2`.
- D9 cycles count one each; D10 one to 18, D11 one to 35/36, with matched OFF and serial closure (generated-count observations, not electrical/receiver measurements). Generation `27c3499c-55b2-4784-a116-ec8b531f1939`: Connect, both Basler tests, Behavior Start/Show/Hide/reopen/native WM_CLOSE/reopen/Stop pass (window PID 9320 is acquisition). Idle MCU Status/Stop truthfully fail.
- Tracking Start exposes a revision-adoption defect (controller accepts changed SDK readback; worker keeps requested revision). Repair reuses the camera-resolution owner/comparator under A10/E07/ARCH-002, accepting only unchanged or next adopted revision with byte-identical SDK facts. 54 regressions; acquisition/controller/client 535 with two skips (8.68 s); mypy 185 sources; boundaries 602 modules.
- Post-repair `d0bcd52b-88db-4011-98d7-947d454fe86f`: Tracking passes preparation but Start rejected, then recurring COORDINATOR_HEALTH_LOST (existing blocker, no Tracking window pass). Test generation `3b888e38-9328-4863-9098-5f6f8b417891` passes D10/D11 Test/Status/Stop (11 and 21/22 rises) and D9 two-second timeout. Evidence `mcu-installation-and-preview.md`.
- Final: controller `73987d0f-0d80-4f63-a646-3dba430048bb` restored in Configuration, seven processes, no current errors; Visual Stimulus display-unavailable warning needs operator acknowledgement (not fabricated). Cleanup total 1,380 files / 25,650,891 bytes (`mcu-install-cleanup.json`). Firmware/Behavior scope complete; TODO retains Tracking health, GUI interaction, physical receiver and full-workload acceptance.
- Refs: `mcu-installed-context.json`

### 2026-10-07 [gui] [controller] [acquisition] [shared] Add square positioned OpenCV preview and wheel zoom

- Task `camera-preview-presentation`: owner requests CephVR1.0-style GUI-edge opening, square aspect-preserving padding, wheel zoom. A10 revision 54/G01 revision 122: GUI Show sends bounded physical desktop coordinates/size (right-edge with left fallback/work-area clamp, resampled on reopen); acquisition owns fixed square rendering, black padding, pointer-centered 1.2-per-notch zoom (fit–16×), double-click fit reset; cached images redraw without new publication. Policy/config advances to 15; 19 Protobuf sources regenerated.
- ARCH-002: viewport, placement, admission bounds and Win32 DPI geometry in focused modules; manual capture (548 lines) and camera admission (505) stay cohesive.
- Acquisition/controller/client 549 with two skips (7.00 s); eight offscreen GUI cases (0.84 s); native HighGUI check (0.63 s) covers 256×256 areas, coordinates, wheel/reset redraw, X-close. Ruff/format 448 files, mypy 395 sources, boundaries 604 modules zero violations. Sandboxed selection stalled after 17 cases and was ended by exact test-process identity. No runtime/camera/MCU operation or restart.
- Task presentation implemented and removed; `camera-preview-gui-binding` retains restart, physical edge/DPI/camera interaction and Tracking health acceptance. Active runtime needs full restart. Evidence: [presentation context](reports/rig-wiring-evidence-2026-10-07/preview-presentation-context.json). Cleanup 52 directories / 602 files / 30,942,993 bytes (`preview-presentation-cleanup.json`).

### 2026-10-07 [launcher] [gui] Repair duplicate-launch endpoint publication wait

- Task `runtime-replacement-and-auto-control`: owner reports WindowsLaunchError before the Y/N replacement prompt. Controller 73987d0f-0d80-4f63-a646-3dba430048bb endpoint was present; the owner's command displays Y/N before and after repair; N preserves the runtime. Owner-terminal cause unproven. Source shows guard-before-endpoint publication timing.
- Under E08 revision 163/ARCH-002, the replacement owner retries only a missing directory/descriptor within the startup health-silence budget; unsafe/invalid records fail immediately; persistent absence names the descriptor path and remedy; native launch errors print concisely. No new policy, dependency or process termination fallback.
- 37 launcher cases pass (3.02 s); shutdown/supervisor/shared/client 219 with one skip (2.84 s); three native delayed-publication cases (0.55 s); Ruff/format eight files, mypy six sources, boundaries 604 modules. No live Y, termination/restart or device operation. [Context](reports/rig-wiring-evidence-2026-10-07/replacement-context.json). Task returns to Next for owner-terminal diagnosis if recurring and GUI-close/reconnect/relaunch acceptance. Cleanup 47 targets / 271 files / 9,291,873 bytes; eight documents/375 links pass.

### 2026-10-07 [launcher] [gui] Investigate persistent owner-terminal endpoint invisibility

- Task `runtime-replacement-and-auto-control`: owner still reports missing endpoint at the ordinary launcher.json path. Correction: the wait repair addresses reproduced timing but does not resolve this failure. Fresh CMD run displays Y/N and N preserves it; token is expected user at medium integrity; sandbox AppContainer LOCALAPPDATA differs (cause not established by that alone). Recurrence retained in [recurrence observations](reports/rig-wiring-evidence-2026-10-07/replacement-recurrence.json); no guessed fix.
- Owner dir /a shows File Not Found at the ordinary path while native CMD sees the descriptor. GetFinalPathNameByHandle resolves it into OpenAI.Codex package LocalCache/Local; matching SIDs, medium integrity and disabled UAC virtualization rule out a different user. Established: MSIX AppData file redirection is the visibility defect (`replacement-msix-visibility.json`).
- E08 fixes the LocalAppData namespace; owner asked to choose a shared owner-only profile root outside AppData or ordinary-CMD launch; no namespace change or restart pending that choice. Read-only state: Configuration, cameras closed, no cleanup pending. 61 recovery record hashes captured, nothing migrated. Cleanup `replacement-msix-cleanup.json`.

### 2026-10-07 [launcher] [supervisor] [controller] [gui] [acquisition] Stop runtime at owner's request

- Owner says "yes, stop it". Prior increment already backed up/uploaded protocol 3 and passed D9/D10/D11 count checks; not repeated. Controller `73987d0f-0d80-4f63-a646-3dba430048bb` Shutdown command `3a756a6c-ff00-46ed-bb16-204fb7aa92fa` completes; launcher receipt confirms all owned processes absent, zero managed Python processes, guard acquirable. No forced termination, upload, output test or restart.
- Physical receiver/LOW/D2 correlation, Tracking health and the pending E08 runtime-root choice remain open.

### 2026-10-07 [gui] [acquisition] [controller] [shared] Repair preview fitting and visible-frame edge placement

- Task `camera-preview-gui-binding`: owner reports image did not open snapped outside GUI top-right. GUI outer bounds 0,0–1456,979 on a 1920×1032 work area produced old hint x=0, overlapping the GUI. Whether an image appeared is not supplied; bounds and regressions do not prove camera visibility.
- Under G01 revision 123/A10/ARCH-002: square sizing fits right-hand space before left fallback, preserves top alignment; GUI reads visible DWM bounds; acquisition positions only its own preview frame. Native test exposes invisible-border x=407 vs requested 400; repaired corner exact. Removed redundant move. Policy 15 binding remains valid.
- Before: six GUI failures/one pass, one native failure. After: ten GUI cases (2.06 s); native acquisition/controller/client 549 with two skips (8.25 s); native/reader four (0.65 s). Ruff, mypy 311 sources, boundaries 604 modules zero violations. Owning Protobuf field comment updated and 19 sources regenerated; wire unchanged. Full restarted-camera acceptance, DPI inspection, Tracking health and physical signals remain open; runtime untouched.
- Cleanup 28 files / 18,932,121 bytes; nine documents/418 links pass.

### 2026-10-08 [gui] Align review/runtime elements and repair saved draft migration

- Completed `gui-review-runtime-parity` under G01 revision 124/G02: both compositions reuse DashboardWindow; matched-state tests compare controls and card/header geometry at 1280/720 across pages, Devices subtabs, Protocol editor modes, Tracking and projector subtabs. Review now shares Start capture/Stop capture/Disconnect labels; authority and routing unchanged.
- Reproduced the preservation warning against the owner's saved review file: older Tracking crop migration replaced the annotation dictionary with a point list. The validator repair retains valid annotations and rejects invalid regions; the file loads twice with unchanged hash. Regenerated stale protobuf bindings (19 sources).
- Focused 9 pass; full portable GUI 303 passed (302.23 s); Ruff 126 files, mypy 124 sources, boundaries 603 modules zero violations. Local checks do not close Windows clipping/native teardown or rig tasks. Native visual inspection not claimed (CUA cannot bind the window). No device commands. Task removed from TODO.

### 2026-10-08 [gui] [controller] [acquisition] [supervisor] [shared] [visual_stimulus] Review Devices/Tracking and authorize explicit firmware upload

- Task `gui-devices-tracking-calibration-review`: owner selects Configuration-only Upload with controller authorization and acquisition's sole serial ownership. A11 revision 38 lifts only explicit compiled Uno upload (automatic flashing/tool installation deferred); E08 revision 164 records the one-shot supervised helper and cleanup receipt; G01/G02 record Connect/Disconnect capture-plus-preview, filename-only PFS, hover color, Tracking grouping and always-grid calibration. Acquisition pair advances to 16.
- ARCH-002: reuses native child/pipe ownership and controller/device admission; focused image validation/upload/handoff owners added. CephVR1.0 HEAD `914ecbc` supplies the grid strategy. No board command run locally.
- Full `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui -q -m "not windows and not rig" --tb=short --maxfail=4` passes 309 (226.30 s); `pytest tests/acquisition tests/controller tests/supervisor tests/shared -q -m "not windows and not rig" --tb=short -rs` passes 748 (12.01 s), five Win32-atomic skips, three marker exclusions (shared tree with concurrent work). Upload release-replay regression repaired; 31 added cases pass. Ruff/format 525 files; mypy 454; boundaries 607 modules zero violations; 19 Protobuf regenerate; policy pair 16 binds. Final 24 registry and 15 GUI cases pass. 12 documents/529 links pass.
- Offscreen inspection of Cameras, Microcontroller and Tracking at 1280/720. HEAD `e4c653c` with uncommitted work, so not an immutable rig revision. No native visual or hardware acceptance claimed; no upload, camera or projector command. Firmware GUI upload and Connect/output inspection added to rig follow-ups.

### 2026-10-08 [supervisor] [launcher] [client] [shared] [controller] [acquisition] [visual_stimulus] [tracking] [platform] [repo] Apply verified backend review fixes

- A read-only review (ruff, AST scans, five model reviews) produced 55 candidate findings; about a third were judged not real after reading code. Evidence and method limits: [review-evidence-2026-10-08](reports/review-evidence-2026-10-08/README.md).
- Changes (E02, E06, E08, E14, ARCH-002): supervisor replay keeps recorded shutdown outcome; gRPC tracking-release failures retry to original deadline; one unreadable launch job no longer fails other heartbeats; acquisition/Visual Stimulus worker cleanup concurrent; rejected Shutdown and helper errors surface as warnings; launcher parser survives deep-nesting/read errors; client reports timeouts and honours E02 Ctrl+C scope; shared policy digest (E14 revision 207); worker bootstrap loopback check; Setup checks `contract_version`; protected Windows file source moved to `platform/windows`; ten unreferenced definitions deleted; ruff gains ASYNC, RUF006, RUF100; new tests per change.
- Portable suite 1090 passed/6 skipped/5 deselected; ruff/format clean; mypy `--platform win32` clean for nine backends; boundaries 606 modules zero violations (`supervisor/shutdown.py` 519, `controller/service.py` 590 advisory). Tests for F-001, F-005, F-014 and client Ctrl+C fail on old code. Windows-native, GPU and rig behavior unvalidated (E15); shared tree not immutable.
- Tasks: added `coverage-gap-measurement`, "For review" `worker-launch-handshake-sharing`, `acquisition-execution-split`, `deadline-helper-sweep`; `shutdown-health-checks` keeps controller-loss and fencing gaps.

### 2026-10-08 [gui] [visual_stimulus] Merge projector configuration JSON

- Task `projector-configuration-json`: owner requests one JSON for all Projectors GUI settings except physical display mapping. G01 revision 126 and the GUI calibration contract: version 3 stores calibration, synchronization, logical-face participation and reusable runtime geometry/color references. Numeric versions and legacy profiles share Load JSON; separate import button removed. Machine assignments stay independent.
- ARCH-002: file-settings and profile/native rebinding extracted into helpers; no new dependency/process/policy. Load rejects invalid/duplicate/nonfinite documents before mutation; Save keeps atomic replacement. Initial tests exposed old import semantics, a shared-output rebinding regression and an incomplete fixture, corrected without weakening. Checks in progress; native/optical unchanged.
- Follow-up: `coverage` 7.16.2 added to dev extras and run ([coverage.md](reports/review-evidence-2026-10-08/coverage.md)); `coverage-gap-measurement` became `acquisition-worker-portable-tests` (worker runtime 0-8% portable coverage). A VS transport test is flaky (2 of 25 solo runs); not fixed.

### 2026-10-08 [gui] [visual_stimulus] Complete projector JSON implementation and review

- Completed `projector-configuration-json`: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui/test_dashboard.py -q -k 'calibration or projector or tank or portable_screen_profile' --tb=short --maxfail=2` passes 40 (30.60 s); authoritative install/roundtrip 3 (4.38 s); seven merged-file/native-profile cases pass. Native-profile fixture now uses the backend JSON model with all-output VSync; no assertion weakened.
- Full portable GUI run: 313 passed, two failures (251.47 s): new roundtrip fixture omitted display inventory (repaired), and unchanged Protocol advanced alignment showed a 12 px displacement (independent rerun passes). Intermittent finding retained as `protocol-advanced-alignment` in TODO/runtime report; no blanket pass claimed.
- Ruff/format six files, mypy five sources, boundaries 608 modules zero violations, four documents/195 links pass. Offscreen Projectors inspection at 1280×900 shows one Load/Save row. No hardware/controller action or restart. Rig/DPI/optical acceptance pending. JSON task removed after recording.

### 2026-10-08 [gui] Rename projector identifiers to Display ID

- Completed `projector-display-id-label` under G01 revision 127: projector table, diagram caption, inventory message and hidden status label now say Display ID; identifier generation/mapping unchanged. Label-only edit (ARCH-002).
- Existing inventory/layout check passes (1 case, 2.93 s); Ruff lint/format pass; boundaries zero violations; whitespace clean. No hardware/restart.

### 2026-10-08 [gui] [acquisition] Confirm firmware file format

- Read picker, validator, uploader and guide: Upload accepts a compiled Uno application `.hex`; `.ino` is its source. GUI compilation was outside the accepted A11 upload scope. No implementation change, upload or hardware check.

### 2026-10-08 [gui] [controller] [acquisition] [supervisor] Implement selected-sketch compile and flash

- Task `mcu-sketch-compile-upload`: owner authorizes compiling selected `.ino` files. A11 revision 39 lifts the limitation within the Configuration-only operation; controller authorization and acquisition COM ownership unchanged. G01 revision 128, E08 revision 165, ARCH-001 scope reference revision 23. Policy/config pair advances to 17; 19 protobuf sources regenerate.
- ARCH-002: sequential use of the contained Arduino CLI helper (validate generated HEX, confirm compiler cleanup before serial release); focused source module pins bounded content with private staging; both phases share the original deadline; cancellation preserved across compile-to-flash. Installed CLI/core/libraries required; automatic installation deferred.
- Source-bound digest bug (default floats vs loader Decimal) corrected via the canonical helper. 26 firmware/source cases and two GUI cases pass. `command -v arduino-cli` returns no tool, so compiler/board execution remains rig acceptance. No hardware command or restart.

### 2026-10-08 [gui] [controller] [acquisition] [supervisor] Complete selected-sketch compile/upload development

- Completed `mcu-sketch-compile-upload`: `tests/acquisition/test_microcontroller_owner.py` and `test_manual_devices.py` (`-k 'firmware or uno_sketch'`) pass 26 (0.63 s), proving sequential phases with distinct identities, same original deadline, compiler release before image staging, pinned image bytes surviving build removal; compiler failure/cancellation/corrupt image never launches upload. Four offscreen GUI cases pass (3.81 s), including `.ino` and `.hex` dispatch.
- Portable acquisition/controller/supervisor/shared suite passes 771 (13.18 s), five Win32-atomic skips, three marker exclusions. Ruff/format 344 files; mypy 400 sources; boundaries 609 modules zero violations; ten documents/470 links; policy/config 17 loads; 19 bindings regenerate.
- Shared uncommitted tree at HEAD `e4c653c` with concurrent work. No native Arduino CLI here; sketch compilation, board flash and GUI/native cleanup acceptance remain in the MCU rig task/checklist, with the policy-17 restart follow-up. No hardware, restart or screenshot.

### 2026-10-08 [controller] [acquisition] [supervisor] Review broader Microcontroller ownership

- Owner asks whether general-purpose Microcontroller ownership belongs upstream. A10/A11/E08 currently place serial owner, diagnostics and firmware helpers in acquisition; existing implementation complies.
- Recommendation (not an accepted amendment): a controller-owned Microcontroller component taking serial/request arbitration, keepalive/watchdog, diagnostics and compile/upload together, with acquisition as client for camera trigger configuration; retaining acquisition is smaller but keeps device availability coupling. Preserve one serial owner, deadlines/reservations, native cleanup, outputs-off; device work off the controller lifecycle event loop (E08). No code/policy change, hardware or test.

### 2026-10-08 [controller] [acquisition] [supervisor] [gui] Start controller Microcontroller ownership migration

- Task `controller-microcontroller-owner`: owner accepts and requests the recommended ownership change. Preserve the dedicated serial owner thread, reservations/deadlines, watchdog and native cleanup. Prefer a focused in-process controller owner and typed acquisition client over a new backend process or duplicate serial owner; implementation and contract amendments in progress. Existing runtime and concurrent work untouched.

### 2026-10-08 [controller] [acquisition] [supervisor] [gui] Wire controller-owned Microcontroller and camera claims

- `controller-microcontroller-owner`: serial/parser/pulse owner and firmware modules rehomed to controller; acquisition uses authenticated typed camera I/O via the controller endpoint with exact generation, deadline metadata and bounded ledger replay; CONNECT establishes an exact claim. Controller owns keepalive, pin diagnostics, supervised compiler/uploader identity, authority-loss and cleanup. A10 revision 55, A11 revision 40, E08 revision 166, G01 revision 129, ARCH-001 revision 24; E14 adds the Microcontroller config/policy pair (version 1); acquisition pair 18; pyserial moves to the base install.
- ARCH-002 removed acquisition keepalive/firmware orchestration; repaired a gap so the final external manual preview releases its camera claim after confirmed OFF and camera cutoff. Failed closes stay visible/fenced.
- Portable acquisition/controller/supervisor/shared 776 passed (5 Windows-only skips, 3 marker exclusions); 15 authenticated loopback controller cases; 11 offscreen GUI cases; mypy 428 sources. Sandbox denied socket binding initially; permitted rerun keeps authentication assertions.
- `python -m build --no-isolation --outdir /tmp/cephvr-mcu-owner-build` stops at the AMD64 Windows packaging guard (macOS cannot validate the package). No Arduino compile/flash, hardware, restart or screenshot. Consolidated checks and reconciliation in progress; native/rig acceptance stays in the MCU checklist.

### 2026-10-08 [visual_stimulus] Fix a race in the authenticated Setup transport test

- `tests/visual_stimulus/test_transport.py::test_authenticated_setup_compiles_and_hands_off_exact_prepared_trial` failed in 2 of 25 solo runs: the InitializeDisplay receipt returns at admission (E08, `shared/admission.py`) and the display resource is announced later on the GL owner. The test now polls for it; no product code changed. 120 of 120 solo runs pass. Evidence: [coverage.md](reports/review-evidence-2026-10-08/coverage.md).

### 2026-10-08 [controller] [acquisition] [supervisor] [gui] Complete controller Microcontroller ownership development

- Completed `controller-microcontroller-owner` within A10/A11/E08/G01/ARCH-001: all managed device/tool work belongs to controller; acquisition and GUI use explicit authenticated requests. Removed the standalone review serial worker and dead live-review wiring; GUI uses independent controller observations. Cleanup retains OFF proof across uncertain bridge closure; cancellation requires the caller's original deadline.
- `.venv/bin/python -m pytest tests/acquisition tests/controller tests/supervisor tests/shared tests/client -q -m 'not windows and not rig'`: 812 pass / 5 platform skips / 3 marker exclusions (12.21 s); GUI `microcontroller or firmware` selection 11 pass. Ruff 491 files, Win32 mypy 427 sources, boundaries 616 modules zero violations; 19 bindings regenerate; 490 links/anchors pass.
- Applies to uncommitted tree at HEAD `e4c653c`. Native package build blocked by AMD64-Windows guard on this Mac; Arduino CLI absent. Compiler/flash, trigger/watchdog latency, COM/native cleanup, Windows acceptance remain in rig checklist. No hardware command, GUI/runtime restart or commit ran. Completed task removed; full-restart/rig checks retained for acquisition policy 18 and Microcontroller policy 1.
- Refs: `tests/gui/test_dashboard.py`

### 2026-10-08 [gui] [launcher] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Begin committed-change Windows rig verification

- Task `runtime-gui-rig-wiring-acceptance`: owner requests change review and rig tests. Checkout clean at `7ba43b1`; review scope `e4c653c..7ba43b1`. Native inventory finds yesterday's controller/acquisition/Visual Stimulus/Tracking and camera-worker generation; GUI absent. Controller descriptor `bbb53abe-bec0-4e61-acf6-ea5667f2510b`. State to be inspected before normal replacement; no takeover/hardware command yet. Prior board image and scientific/encoder deferrals retained.

### 2026-10-08 [controller] [supervisor] [acquisition] [gui] [shared] [visual_stimulus] [spikeglx] Initial Windows results and MCU repairs

- `runtime-gui-rig-wiring-acceptance`: prior runtime had no active session; normal shutdown receipt proves all owned processes absent. COM8 flash readback retained (flash backup only). New generation `50676d58-a5de-4dd5-8033-fc1b8b944070`: MCU connects, D9/D10/D11 counts/Stop and D9 timeout succeed; first managed HEX upload fails (eight-versus-nine argument error before helper launch); configuration restored. Evidence: [Oct8 rig evidence](reports/rig-wiring-evidence-2026-10-08/).
- Baseline Windows/offscreen suite: 1456 pass, 12 fail, 4 skip, 1 rig deselected; static checks, contracts/schema drift and AMD64 build pass. Eight known GUI layout failures persist, plus Qt-path/sketch fixture, two async-settlement and one Visual Stimulus shutdown failure.
- ARCH-002/A11/E08 repairs: remove invalid diagnostic-stop after firmware reconnect (stub reproduces 2 fail/9 pass before; integration 90 pass, one symlink privilege failure); fix `CreateNamedPipeW` extra argument; canonicalize fixture paths, skip only privilege 1314, await shutdown settlement, inject clock. No policy/firmware change. Native reruns in progress.

### 2026-10-08 [controller] [supervisor] [acquisition] [gui] [tracking] [shared] Managed board upload and camera acceptance

- `mcu-managed-connection-and-io`: generation `8931f391-8b79-4b9d-af83-a0a6b656770b` passes managed HEX upload/verification and `.ino` compile/upload (acquisition disabled). Reconnects report protocol 3 / `cephvr2_uno_2`, outputs stopped; Stop counts D9=1, D10=13, D11=25 are firmware transitions, not voltage/timing. Native pipe transfer plus owner/transport selection passes 118 (one privilege skip); GPU smoke 1.
- Camera testing exposes the same invalid diagnostic-stop in cleanup, fencing control release; fixed to stop only an active diagnostic (107 pass, one skip). That earlier generation's control-release cleanup failed: not an outputs-release pass.
- After restart, Behavior Connect/Show/Disconnect and trigger-claim/COM release pass twice with camera content visible. Tracking imports BehaviorSquid and prepares, but Start is rejected and `COORDINATOR_HEALTH_LOST` recurs; automatic shutdown proves absence; health task open.
- Full suite: 1462 pass, same eight GUI layout failures, five skips, one rig deselected (157.66 s). Ruff 52 files, mypy 47, boundaries 617 modules zero violations. Compiler-failure/remote checks and docs in progress.

### 2026-10-08 [controller] [supervisor] [acquisition] [gui] [tracking] [visual_stimulus] [spikeglx] [shared] Finish bounded rig verification and cleanup

- `runtime-gui-rig-wiring-acceptance` / `mcu-managed-connection-and-io`: supervised compiler rejection preserves COM identity and cleans helper storage; active-D9 release succeeds. After exit, COM8 D2 shows zero edges (no projector source); D10/D11 watchdog-stopped after 3.431453 s, matched OFF and close succeed (firmware observations, not precise latency). SpikeGLX inventory reads; read-only diagnostic times out. Projector Launch/optical checks unavailable.
- Final cleanup review keeps uncertainty after unacknowledged diagnostic Start (108 pass, one skip; no missing-ACK injection). Full suite: **1463 pass, eight GUI layout failures, five symlink skips, one rig deselection, 167.66 s**; lint, typing, boundaries pass.
- Final Shutdown receipt proves absence; guard free, COM8 exclusive, no private firmware dirs. Tracking's transient failed restore kept as failure; fresh snapshot confirms disabled config. Removed 71 cache targets (911 files / 51,073,083 bytes). Open: Tracking health, GUI clipping, SpikeGLX, projector, electrical/full-load. [Oct8 evidence](reports/rig-wiring-evidence-2026-10-08/README.md).

### 2026-10-08 [gui] [controller] [acquisition] Diagnose cross-camera settings rejection

- Owner console shows Behavior settings rejected naming Tracking's missing trigger source. Read-only review: PFS hints are draft-only, selected-row save submits the whole configuration, enabled external Tracking needs its own input. Recommend configuring Tracking row with its BehaviorSquid PFS before enabling, or disabling Tracking meanwhile. Recorded `camera-configuration-validation-feedback` for row-specific feedback; no code change, restart, device command or rig pass.

### 2026-10-08 [gui] [acquisition] Restore the selected camera's configuration

- Completed `camera-selection-config-sync` under G01/ARCH-002: inventory restoration reloads selected role/PFS/timing/rate even if controller revision unchanged; Use also selects that camera's row. Silent loading sends no command; no dependency, policy or device change.
- Both inventory rows and both checkbox directions fail before repair; Qt camera/PFS selection passes **27 / 295 deselected in 7.30 s**. Ruff 3 files, mypy 2 sources, boundaries 617 modules zero violations. No camera/firmware/runtime command ran; earlier full-suite results predate this. [Source scope](reports/rig-wiring-evidence-2026-10-08/README.md#later-camera-selection-correction).
- Removed 63 cache targets (740 files / 21,490,160 bytes). Running GUI must reload code; cross-camera validation feedback and physical GUI acceptance remain open.

### 2026-10-08 [acquisition] [controller] [supervisor] [gui] [tracking] Repair Tracking Connect shutdown and verify exact release

- Completed `camera-worker-coordinator-health`: evidence shows rejected lifecycle evidence, not a heartbeat timeout. Tracking prepares display and ordered-Tracking producer rings, but Ready and cleanup validators each assumed one; repaired both attachment/release sets. Health path preserves specific rejection/transport/task reason. ARCH-002 extracts a focused evidence helper and validates all releases before ledger commit. No policy/firmware/scientific-default change.
- Final controller `f4128e9d-2218-41e5-b17d-143f91383072`: BehaviorSquid import/readback, two Tracking Connect/Show/Disconnect cycles (six seconds each), exact Stops, restoration, shutdown and release pass. No scientific session or ordered Tracking diagnostic ran; physical GUI clicks/DPI open.
- Ready regressions 2 fail/14 pass before; 48 ring-proof cases and three dispatcher cases added. Acquisition/camera/config suite **363 / one skip in 2.75 s**; Ruff 8 files, mypy 6, boundaries 618 modules zero violations. [Raw methods](reports/rig-wiring-evidence-2026-10-08/README.md#tracking-connect-and-release-correction). Cleanup removed 63 targets (1,706 files / 23,947,750 bytes); 441 links pass; runtime stopped.

### 2026-10-08 [gui] [controller] Explain configuration retention after the Tracking crash

- Owner reports previous GUI values missing. Read-only inspection: ignored `config/last_configuration.json` still dated Oct6 (Tracking disabled, no PFS/input). Normal GUI close calls SaveConfigurationHistory; ShutdownApplication has no history save despite E07's shutdown-save requirement; abrupt health shutdown bypasses it; no autosave-on-edit.
- Earlier restoration claim clarified: final Tracking test restored its fresh startup snapshot, not newer pre-crash edits. Recorded `configuration-history-retention`. No code, runtime or hardware change.

### 2026-10-08 [gui] [spikeglx] Remove Stream from the input mapping table

- Completed `spikeglx-stream-column` under G01: Stream column hidden using the table's existing visibility operation; no new dependency/state/contract. No restart or SpikeGLX command ran.
- `tests/gui/test_dashboard.py -k 'spikeglx and not bridge'` passes five / 317 deselected in 3.15 s; offscreen render confirms zero width. Ruff/format, mypy, boundaries (618 modules zero violations) pass. Cleanup removed 60 cache targets; documentation links pass.

### 2026-10-08 [gui] Match camera Disconnect to the shared red style

- Completed `camera-disconnect-color` under G01/G02: connected-camera Disconnect uses the existing danger role and repolishes on role change; Connect restores primary role. No new state/dependency/device behavior.
- Qt selection (`camera_batch_check or preview_participation_gates or managed_camera_disconnect`) passes three / 319 deselected in 2.40 s; offscreen palette checks confirm colors. Ruff/format, mypy, 618-module boundaries pass. No hardware command or restart.

### 2026-10-08 [gui] [controller] [supervisor] [shared] Investigate .ino upload shutdown

- Started `ino-upload-job-inspection` after owner crash: emergency `667347656846800` identifies JOB_INSPECTION_FAILED for controller `c54bc934-6250-478a-910e-9c88920a8274`; exit confirms all owned processes absent. Emergency lacks native error detail. Preserve raw evidence; investigate job membership/firmware helper lifecycle without weakening identity checks or deadlines. No new upload or restart yet.

### 2026-10-08 [gui] Retain last display assignments across frontend restarts

- Completed `projector-assignment-retention`: G01 revision 130/register and GUI calibration contract retain physical mappings separately from portable calibration JSON. Assignments sync via frontend QSettings by stable display identity (incl. Unassigned/absent); restore marks differences as dirty drafts; loading sends no command; invalid preferences preserved/reported. Focused helper, no new dependency; fixed visible-dropdown mismatch.
- Four restart/managed cases fail before repair; eleven new retention cases pass. Owning selection: **53 passed, one existing layout failure, 279 deselected, 25.45 s** (`test_configuration_scroll_keeps_projector_status_fixed`; `devices-narrow-overflow` retained). Ruff 5 files, mypy 4, boundaries 619 modules zero violations; 372 links pass. No multi-monitor restart or hardware ran; physical acceptance remains in rig checklist. [Raw results](reports/rig-wiring-evidence-2026-10-08/projector-assignments-context.json).

### 2026-10-08 [gui] [controller] [supervisor] [shared] Repair .ino upload native-job shutdown and cleanup

- Completed `ino-upload-job-inspection` under E08/A11: reproduced QueryFullProcessImageNameW WinError 5 for a compiler job member and TerminateJobObject WinError 5. Added bounded one-millisecond exact-handle exit check after failed image queries (live/unknown members still raise) and termination right on reopened launch-owner job handles. Regression fails before, passes after. No policy, firmware, dependency or ownership change.
- Controller `4226bad4-92db-4001-879c-1149c49dea8e`: real compile/verified uploads pass, deliberate compiler rejection preserves serial identity, shutdown and absence pass. Failed evidence preserved; no experiment edit or GUI interaction.
- Platform/supervisor/MCU-owner/shared suite **199 / one skip in 2.79 s**; Ruff 2 files, mypy 1, boundaries 619 modules zero violations. One old private staging directory archived and removed. [Raw results](reports/rig-wiring-evidence-2026-10-08/README.md#ino-upload-native-job-correction). Cleanup removed 64 targets (743 files / 22,890,181 bytes); 386 links pass; skip is symlink privilege. Interrupted-flash/full-load/electrical acceptance open.

### 2026-10-08 [controller] [acquisition] [visual_stimulus] [tracking] [spikeglx] Compare CephVR1.0 and current 2.0 outputs

- Completed `output-format-comparison`: compared sibling 1.0 writers and actual October 6 SP0002 JSON/CSV with current 2.0 writers/models. Folder layout retained; filenames, JSON/JSONL organization, tracking quantities, subject metadata, frame correspondence, review capture and completion evidence differ. Assessment in reports/runtime.md links E04/A07/A08/T15/T19/T35/T38/E13/V13; no architecture/implementation change.
- Found 16 legacy session schemas, no 2.0-style scientific artifacts in C:/Data. Conclusions are source/schema evidence, not a recording or rig pass. 2.0 HEAD 7ba43b1; sibling ref 1082d917, but `git -C` status inspection denied so dirty-snapshot provenance incomplete. Five links and `git diff --check` pass; no runtime test, recording or data mutation.

### 2026-10-08 [acquisition] [visual_stimulus] [tracking] Revise video timing and review decoded Tracking storage

- Owner revises video timing: pad recording gaps to preserve nominal FPS/duration and identify duplicates for post hoc exclusion. Recorded A07 revision 58 / A08 revision 49 / E13 revision 19 / V12 revision 10 plus root register. Frame/source/duplicate mapping must not fabricate evidence; bounds, deadlines, empty-video rules and rig deferrals stay. `video-cadence-padding` retains slot/leading-gap formalization and implementation; writers still unpadded.
- Recommend standard Protobuf JSON over base64 for Tracking results (T15/T19 unchanged, no measured size claim); recorded in reports/tracking.md. Revision checks, five links, frame-log TOML parse and `git diff --check` pass. No code, runtime or test execution.
- Refs: V03

### 2026-10-08 [controller] Copy current CephVR1.0 MCU source

- Completed `legacy-mcu-source-copy`: byte copies of sibling `reiter-cephalopod-vr-software/protocol/arduino/camera_vr_dual_projector_sync_ttl/camera_vr_dual_projector_sync_ttl.ino` to `firmware/cephvr1_mcu.ino` and [projector_clock.h](firmware/projector_clock.h). SHA256 equal: sketch 32363 bytes `8E7102B221E5CAB65336E2B8450CC726E4DC5CE7710E18D5CEA80B38FB65C41E`; header 3819 bytes `DCCFA8D4782B66793138D9DDCCE55A62759BE661C7E7F5F93C6C7D5467A6AB9C`. Local provenance only; no compile, upload or rig test. `git diff --check` passes.

### 2026-10-08 [tracking] Implement decoded scientific-record objects

- Completed `tracking-decoded-records`: T15/T19 revision 4/register and schema-2 header use descriptor-owned Protobuf JSON feedback and nested stage payload objects; exact int64/uint64 strings, enum names, optional-zero presence preserved; unknown/nonfinite/noncanonical input rejected; old recordings unchanged, unsupported schemas rejected. ARCH-002: focused adapter, old base64 wrapper removed, writer admission bound charges expanded workspace; Tracking JSON schema regenerated.
- Tracking/controller planning/metadata suite **113 passed / one rig deselection in 3.65 s**; recording selection 28; contract unittest 48; 19 schemas match. Ruff 74 files, mypy 66, boundaries 620 modules zero violations; 447 links pass. [Context](reports/tracking-evidence-2026-10-08/decoded-records-context.json).
- Initial failures (stale base64 assertions, mypy annotations) corrected; pytest contract collection unavailable, unittest used. No restart, hardware, throughput or crash-durability test ran. `video-cadence-padding` stays separate.

### 2026-10-08 [tracking] Review schema-2 information preservation

- Reviewed decoded-record change under T15/T19: no supported scientific fields removed; base64 packaging and escaped JSON become objects, original binary encoding/formatting not retained. proto3 defaults may be omitted (descriptor supplies meaning); optional zero explicit; unknown fields rejected; existing files untouched; schema-1 reading unsupported. No further actionable defect; no new test ran.

### 2026-10-08 [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Wire and verify GUI for dummy experiment

- Started `gui-backend-dummy-experiment` (both camera videos and stimulus video on, Tracking velocities off). Native camera and MCU paths pass GUI dispatch; SpikeGLX reachable but already running another acquisition; asked owner whether to disable pairing. Standalone MCU Status without diagnostic correctly rejected.
- Reproduced eight layout failures and repaired them under G02/ARCH-002. Full repository run 1560 pass, two GUI regressions (fixed), five skips, one rig deselection; owning suite 334 pass.
- Repaired E07 application-shutdown history saving (atomic writer, queue-inclusive deadline); Ruff 260 files, mypy 229, boundaries 620 modules zero violations.
- Prepared 60-second open-loop dummy grating and diagnostic calibration assets (uncalibrated; no optical acceptance). Normal shutdown confirmed. Experiment start and native shutdown-save reload pending; evidence in reports/rig-wiring-evidence-2026-10-08/dummy-experiment.

### 2026-10-08 [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx] Verify shutdown retention; retain dummy-run blockers

- Completed `configuration-history-retention`: generation bc379e5f-c2b0-45a2-8d0f-5430bc78b8fe saves a marker via ShutdownApplication without explicit save; c4bbb0f6-e0cc-4fbd-97dd-8ac20f804524 reloads it; original restored. History tests 47 pass, one skip. Abrupt crash before saving remains outside the guarantee.
- Dummy validation passes experiment/acquisition/Tracking and rejects Visual Stimulus for unset V20 pacing output; asked owner for pacing face and SpikeGLX pairing. Approval review rejected combined dummy submission/Setup; not bypassed. No submission, Setup, Start or recording.
- Native assigned-camera rows and wide-window tabs/HUD correct; narrow native/DPI verification not claimed. Reports and rig worklist updated.

### 2026-10-08 [gui] [controller] Correct native-discovered recording labels and partial-draft closure

- Under `gui-backend-dummy-experiment`: Dashboard labelled assigned camera recordings Unassigned; label refresh moved into recording owner's view refresh (eight focused cases and 334-case suite pass; native shows correct labels).
- Native GUI close with incomplete protocol falsely reported history-save failure; under E07 the close helper now saves the accepted controller configuration, dirty drafts require discard/cancel. Four cases fail before repair; ten focused pass; native close verified.
- Full permitted suite: **1566 passed, five skipped, one rig deselected in 171.33 s** (338 GUI). Ruff 260 files, mypy 229, boundaries 620 modules zero violations. Setup unexecuted pending pairing/pacing choices; optical/electrical/scientific/full-load and narrow/DPI acceptance open. TODO reconciled.

### 2026-10-08 [tracking] Clarify reference-distance conversion

- Reviewed T21/T35/T38/T42/T43 for owner question: known mm over image endpoint separation scales planar displacement/linear rates to mm and mm/s, subject to depth/geometry/distortion. `image_scale` is retained metadata; estimator outputs remain px/s and angular 1/s. Water-flow scaling does not establish animal swimming velocity. No decision or code change; no runtime or rig test.

### 2026-10-08 [visual_stimulus] Clarify physical texture drift

- Reviewed V14/V15 and schema for owner question: calibrated surface geometry permits mm/s texture translation; periodic phase rate is speed divided by physical period. Correct mapping/direction required; optical accuracy remains rig acceptance. No implementation, configuration or decision change; no runtime/rig test.

### 2026-10-08 [gui] [controller] [supervisor] [acquisition] [visual_stimulus] Diagnose unpaired dummy Setup

- `gui-backend-dummy-experiment` resumed with SpikeGLX pairing disabled by owner. Prepared Front 60 Hz pacing temporarily and an explicit empty arena-boundary document; GUI schedule submission now includes it.
- First Setup: acquisition rejected session scope while heartbeating Configuration. Repaired E08 process-only heartbeat admission for exact registered controller/coordinator identities; session-scoped checks retained. Failed dummy reservation recovered, files and remote acquisition preserved.
- Retry hit deadline: Setup output identities missing until Ready and terminal Setup failures rejected by incident-only gate. Reused identity planner for accepted save selections; exact Setup completions retained so waiting reports the actual failure. E04/E08 refined; no new state/process/deadline.
- Controller/acquisition/supervisor suite **773, three skips**; GUI/supervisor run 459; Ruff 289 files, mypy 249. Next startup fails closed: managed Python gets AMD OpenGL not RTX 5060 Ti (SYS-002); temporary GPU preference applied, strict verification kept. No trial Start or videos yet.

### 2026-10-08 [gui] [tracking] [visual_stimulus] Review proposed measured reference bars and output units

- Reviewed owner proposal against G01/V14/V15/T20/T35/T38/T42/T43: projected raw-pixel bars give local mm/px; throw distance needs effective throw ratio and ideal projection assumptions; subject-to-screen distance independent; nonuniform scale needs horizontal/vertical checks. Camera calibration independent of projector; valid image-scale can gate Tracking and scale linear drive; rad/s to deg/s is an angular conversion. Units/gain bindings must be amended together without relabeling old data.
- Feasibility review only; no code, settings, decision or runtime test.

### 2026-10-08 [gui] [controller] [supervisor] [acquisition] [visual_stimulus] Repair native preparation and recording preflight

- `gui-backend-dummy-experiment`, real unpaired Setup: owner approves temporary 1,000 ms post-cutoff drain allowances for both cameras (test budgets, originals preserved). No trial Start/video yet.
- Repairs: fullscreen focus loss (AUTO_ICONIFY false); private InitializeDisplay completion no longer in controller session evidence; revision-zero cleanup init; video-selector binding moved to GL handoff; FFmpeg EOF helpers retain cleanup obligations; ModernGL loader-only attachment fixes double WGL destruction. Visual Stimulus suite 170 pass; context/registry 44.
- FFmpeg four-column pixel-format rows were discarded by parser (fixed; 28 pass); system FFmpeg 4.3.2 lacks p4, so installed imageio FFmpeg 7.1 used in isolated PATH. RGBA8/packed RGB10 layout facts added (eight cases). Lint/format and 149-source mypy pass; no weakened proof. Native retry in progress.

### 2026-10-08 [gui] [tracking] [visual_stimulus] Implement measured reference calibration

- Owner authorizes `physical-reference-calibration`. Amended G01/V01/V15/V24, T19/T20/T35/T38/T43/register: native-pixel bars with measured X/Y mm give affine scale and ideal read-only throw distance; subject distances independent. Camera endpoint scale gates Tracking/locomotion diagnostics with mm/s and deg/s outputs, pipeline version 2, file header 3, Tracking policy 43. Pixel/radian evidence preserved; incompatible legacy bindings rejected.
- ARCH-002 focused helpers; exports create content-addressed affine assets; old inventories migrate with unset measurements, failing atomically on unknown keys.
- Tracking 79, rendering 19, Win32 mypy 322 sources pass; affected integration run in progress. Native/optical/scientific/full-load acceptance open; no runtime restart or hardware.

### 2026-10-08 [controller] [acquisition] [visual_stimulus] Reach real dummy Ready and repair Start schema

- `gui-backend-dummy-experiment` (no SpikeGLX/velocities): absent optional feedback attachment preserved for open-loop Setup (3 pass); native Visual Stimulus Ready succeeds.
- Acquisition now waits on retained camera Setup failures before Ready (8 pass); unchanged camera revision and stopped MCU cadence no longer wrongly rejected (camera/adoption 44; recording-pulse/Setup 13).
- Run 16 reaches aggregate Ready, but Start fails before a trial: writer provider omits stimulus_LOG recipe. Supplied PreparedTrial v2 schema (6 pass). No videos yet; output inspection in progress; ARCH-002 reuse, no new deadlines.

### 2026-10-08 [gui] [tracking] [visual_stimulus] Complete physical reference implementation and local validation

- Completed `physical-reference-calibration` under G01/V01/V15/V24/T08/T19/T20/T35/T38/T43: review fixes output-mode provenance reuse, bounds generated-asset comparison, restricts unit checks to active Visual Stimulus (E07). Old inventories strict and unmeasured; raw evidence preserved.
- Affected suite passes 658 with one skip and three deselections (190.04 s); two deselections are default/pacing checks affected by another chat's temporary value. Configuration/recording 57, GUI 4, Tracking contracts 48, schemas 19/11 pass. Ruff 348 files, mypy 322, boundaries 625 modules zero violations; 682 links pass.
- Evidence: reports/tracking-evidence-2026-10-08/physical-reference-context.json. No native projector/camera session, optical/DPI/scientific/full-load pass or gain conversion claimed. Rig acceptance and `video-cadence-padding` remain open.

### 2026-10-08 [controller] [acquisition] [visual_stimulus] Surface trial preparation failures and repair native receipts

- `gui-backend-dummy-experiment` runs 18–22 accept Start but never begin a trial. Camera warning source bound to its session/trial; original coordinator-loss cause retained; no writer cleanup without trial thread (19 pass). Idle heartbeat handoff bounded to exact PrepareTrial child/deadline (20 pass); E08 revision 168.
- Controller awaits exact camera PrepareTrial completions before Ready and retains terminal results (60 pass, one skip; only known temporary pacing fixture failure). MCU pulse-evidence child identity retained (12 pass).
- Run 22: protobuf text presence fixed (5 pass); shutdown receipts for calibration CPU release and worker query results fixed (21 pass). Shutdown honestly unconfirmed, process-absence/guard/history receipt passes. Restart and output verification in progress; full checks and restoration pending.

### 2026-10-08 [controller] [supervisor] [acquisition] [visual_stimulus] Repair recording scheduling and native capture integration

- `gui-backend-dummy-experiment` runs 24–28 reach scheduling but no completed dummy experiment claimed. Fixes: monochrome gray format (30 pass); FFmpeg obligation predeclared per trial (38 pass); Release gated on retained Schedule executor, camera Schedule children awaited, supervisor Cleanup reconciles pending executor (99 and 84 pass).
- Run 26 GL_TIMEOUT_IGNORED passed as explicit 18446744073709551615; run 27 compositor tuple order fixed (capture 21 pass); run 28 Schedule ID versus PrepareTrial parent fixed (20 pass).
- Broad suite 986 pass, three skips/three deselected, one temporary camera-drain default fixture failure (passes after restoration). Failed reservations preserved; full validation and output inspection pending.

### 2026-10-08 [gui] [controller] [acquisition] [visual_stimulus] [tracking] [spikeglx] Implement reusable configuration snapshots

- Started `gui-configuration-snapshots` (ARCH-002: one JSON/atomic-write/nonmodal-dialog helper, per-section codecs). Protocol toolbar saves full schedule, seeds, gaps, boundaries, mode, asset root; Microcontroller/SpikeGLX and sidebar controls added. Sections prevalidated before restore; loaded values remain drafts for E07 submission; firmware paths never upload.
- Eight existing cases and Win32 mypy pass; new snapshot checks pass 20 (repository-local basetemp used for MSIX temp failure). No native file chooser/hardware session claimed.

### 2026-10-08 [controller] [supervisor] [acquisition] [visual_stimulus] Repair native trial onset and normal end wiring

- `gui-backend-dummy-experiment` runs 29–30: absolute reserved Desktop prefix passed, camera lifecycle forwarded under preparation (controller/acquisition/transport 58 pass; camera/renderer 12 and two). Run 31 begins recording; four surface-local physical gratings authored (same 5/20/35 s schedule). Run 33 records all three videos for the full interval, exposing missing normal camera Stop and forgotten output paths; fixed with Release-owned end task and Stopped emitted after confirmed Stop/OFF (63 pass; no deadline extended).
- Run 34: Behavior 1,198 frames, Tracking 2,397, no transport misses; stimulus renders 3,590 groups but admits 118 captures; final GPU capture cancellation blocks closure. Fix: poll pending transfers, seal queue (27 pass). Run 35 and external decode in progress; rates are observed limitations, not full-load acceptance.
- Win32 mypy 602 sources; boundaries 632 modules zero violations. Temporary restoration and final checks pending.
- Refs: A07, A08, E04, E05, E08

### 2026-10-08 [gui] [controller] [acquisition] [visual_stimulus] [tracking] [spikeglx] Complete configuration file implementation and verification

- Completed `gui-configuration-snapshots` under G01 revision 132 and contracts/gui-configuration-files.md: same-rig identity validation, atomic JSON, complete protocol schedule, projector/Tracking migrations. Loaded camera/MCU values enter normal proposals; inactive Tracking stays pending; reload restores device roles/pins first.
- Full GUI runs pass 368 (186.15 s) then 367 with two stale mocks (fixed, assertions unchanged); 49 snapshot/managed cases pass. Evidence in reports/gui-configuration-evidence-2026-10-08.
- Ruff 138 files, mypy 136, boundaries 632 modules zero violations; 729 links pass. No runtime restart or hardware; native chooser/DPI/optical acceptance in rig checklist.

### 2026-10-08 [controller] [supervisor] [acquisition] [visual_stimulus] Complete native dummy sessions and repair terminal ownership

- `gui-backend-dummy-experiment` runs 35–37 complete the 60 s trial and seven outputs, but camera cleanup times out; repaired bare WorkerCommand cleanup envelopes (12 pass) and CPU release receipt retention (37 pass).
- ffprobe/decode pass run35 MP4s (Behavior 1,198, Tracking 2,398, stimulus 120 frames). Pending-write polling replaced (28 pass). Run40: 1,496 stimulus frames, zero drops; cameras about 20/40 fps vs 30/60 configured; unpadded timelines compress gaps (observed limitations, not acceptance).
- Run39 exceeded 500 ms Schedule allowance; temporary 2,000 ms lead set (backup kept). Runs40–41 complete; stale idle heartbeat fixed with durable ENDED (38 pass). Shutdown proof reuse fixed (13 pass). Run42 and final checks in progress.
- Refs: A02, A07, A08, E04, E05, E08, V01, V12, V20

### 2026-10-09 [repo] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [gui] [spikeglx] [launcher] [shared] Begin requested multi-model repository audit

- `repository-luna-sol-astra-audit`: clean checkout at `0aebf47`. Owner requests Luna source audits, Sol interpretation and Astra review. Three Luna reviewers cover runtime ownership, capture/rendering, GUI/Tracking/SpikeGLX; root checks hygiene and provenance. Audit only: no runtime/device actions or implementation changes; deferrals and E15 limits preserved.

### 2026-10-09 [repo] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [gui] [spikeglx] [launcher] [shared] Complete Luna–Sol–Astra audit and reconcile evidence

- Completed `repository-luna-sol-astra-audit` at `0aebf47`; [raw reports](reports/review-evidence-2026-10-09/context.json). No demonstrated P1. Only TODO/LOG, reports, rig checklist and evidence changed; no product change or commit.
- New P2: three diagnostic-default mismatches cause four configuration-test failures; 10,353 tracked `.tmp` files (224,923,430 bytes). Restoration kept in `gui-backend-dummy-experiment`; added `tracked-scratch-cleanup`.
- Revalidated P2 worker retirement, late-Finished parsing, 300 s PlanLaunch replay retention, shutdown loss-response; camera retirement can block reuse (native reproduction pending); pruned-ID replanning reproduced locally; P3 late SDK exception confirmed. Duplicate-ID and warning lost-update candidates rejected.
- Oct8 run43 evidence is newer than TODO/LOG: 60 s unpaired trial, seven outputs, cameras 29.95/59.93 fps, stimulus 19.7 fps with four drops; current TOMLs still hold diagnostic settings. No new rig run or padding claimed.
- Validation: Luna selections runtime 45, acquisition/Visual Stimulus 132, Tracking 80, SpikeGLX 25, GUI 19 (not full suite); configuration 32 pass/four fail; contracts 48/42, schemas 19/11; Ruff passes, mypy 724 sources, boundaries 631 modules zero violations/40 advisories. No full suite or E15 acceptance; fixes remain open.

### 2026-10-09 [repo] [controller] [supervisor] [acquisition] [visual_stimulus] [gui] [spikeglx] [shared] Begin authorized fixes and cleanup

- `audit-fixes-and-repository-cleanup`: owner requests fixes and dead-code/tmp/cache cleanup with the Luna/Sol/Astra hierarchy. Luna increments: launch retirement/replay, controller recovery/prompt/SDK, shutdown/GUI feedback; root restores defaults and inventories scratch. Prior audit report changes preserved; no hardware or remote action planned.

### 2026-10-09 [repo] [controller] [acquisition] [visual_stimulus] [gui] [tracking] Restore defaults and remove disposable scratch

- `audit-fixes-and-repository-cleanup` / `tracked-scratch-cleanup`: restored 500 ms preparation lead, unset camera drain margins and pacing-output identity; 36 configuration cases pass (was 32/four failures); TOMLs parse.
- Inventoried `.tmp` (10,353 files / 224,923,430 bytes); kept two unique GUI QA scripts and collection evidence; removed generated fixtures, copied FFmpeg tools and one-shot scripts; added `/.tmp/` ignore. [Cleanup provenance](reports/review-evidence-2026-10-09/cleanup.json). No history rewrite or runtime history deletion; cache cleanup after final validation.

### 2026-10-09 [controller] [spikeglx] [shared] Controller repair increment ready for Sol review

- `audit-fixes-and-repository-cleanup`: Luna implements late-Finished/incident versus terminal startup recovery classification, shared attempt-prompt cancellation for pre-activation Shutdown, late shielded SDK completion observation; removed write-only camera-completion reference.
- Controller/SDK/camera regressions pass 142; Ruff/format, Win32 mypy, boundaries zero violations. [Luna handoff](reports/review-evidence-2026-10-09/luna-controller-fixes.txt). Sol review in progress; not native or final acceptance.

### 2026-10-09 [supervisor] [acquisition] [controller] [gui] [spikeglx] Review integrated fixes and close the remaining retirement race

- `audit-fixes-and-repository-cleanup`: Luna completes typed camera cleanup confirmation/replay retention and shutdown-loss/GUI feedback. Sol repeats 142 controller and 90 registry/shutdown/health/coordinator checks; correction joins lifecycle/operation completion under the original deadline. Restored omitted firmware-role import; 132 supervisor and 336 acquisition checks pass.
- Astra reproduces a remaining P2: camera Shutdown/native exit can reach health tick before owner confirmation, causing CHILD_EXITED escalation. Returned for exact bounded owner-proof acknowledgement before exit; native process/job absence still required for RELEASED; no blanket suppression or deadline extension. Full portable checks in progress; native/rig separate.

### 2026-10-09 [repo] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [gui] [spikeglx] [shared] Complete authorized Luna–Sol–Astra fixes and cleanup

- Completed `audit-fixes-and-repository-cleanup`: Astra accepts final source, no remaining actionable finding. Camera-retirement race fixed by acknowledging one exact immutable owner Cleanup proof before Shutdown and replaying after exit; original deadline kept, hung retirement blocks reuse, unexpected exits still escalate. E08/register revision 169; 19 protobuf sources regenerated. [Evidence](reports/review-evidence-2026-10-09/implementation-context.json), [Astra disposition](reports/review-evidence-2026-10-09/astra-implementation-review.txt).
- Completed `late-finished-recovery`, `shutdown-health-checks`, `pruned-launch-replay`, `camera-configuration-validation-feedback`, `controller-audit-observations`; closed `camera-readback-adoption`; `worker-launch-retirement` native checks move to `rig-acceptance`; `protocol-advanced-alignment` retired as unreproduced.
- Validation: full portable/offscreen suite 1,698 pass, six skips, eight excluded (322.25 s); final supervisor/acquisition 472 pass; Ruff/format 839 files, Win32 mypy 726 sources, boundaries 633 modules zero violations; contracts 48/42, schemas 19/11. Scopes overlap. No native Windows, hardware, remote SpikeGLX or rig acceptance ran.
- Completed `tracked-scratch-cleanup`: 10,353 scratch files deleted, `/.tmp/` ignored, 75 cache directories removed ([cleanup.json](reports/review-evidence-2026-10-09/cleanup.json)). 651 links/anchors and `git diff --check` pass; changes uncommitted.
- Refs: `gui-backend-dummy-experiment`, `spikeglx-controller-integration`

### 2026-10-09 [repo] [acquisition] [controller] [gui] [visual_stimulus] [launcher] [shared] Triage remaining TODO work for the development machine

- Triage only: portable acquisition-worker tests, owned-camera edits, epoch shuffle and video padding are locally implementable; runtime path replacement needs the owner choice and Windows verification; stimulus throughput and native UI/device/paired/rig acceptance cannot close on this Mac. Three behavior-preserving refactors remain deferred. No task started, no TODO/architecture change, nothing run.

### 2026-10-09 [controller] [supervisor] [acquisition] [visual_stimulus] [shared] Start authorized non-GUI development work

- Owner requests all non-GUI development-machine work and lifts the Oct8 deferrals for `worker-launch-handshake-sharing`, `acquisition-execution-split`, `deadline-helper-sweep`; also starts `acquisition-worker-portable-tests`, `owned-camera-edits`, `video-cadence-padding` (Luna implements, Sol integrates, Astra reviews). Rig/encoder deferrals and GUI/runtime-storage work stay outside.
- Baseline: 40 passes/five skips, 960 statements/29% coverage over seven target modules. No device/native/remote action runs.

### 2026-10-09 [acquisition] [visual_stimulus] Accept recording slot and leading-gap rules

- `video-cadence-padding`: owner accepts first usable image per nominal slot (later same-slot sources logged, omitted from video) and backfilling leading slots from the first usable image with explicit padding labels. Recorded A07 rev 59, A08 rev 50, V12 rev 11, V28 rev 5, E13 rev 20 plus root register. Quantization bounded to less than one period; original deadlines unchanged.
- Accepted behavior and implementation scope only, not a completed writer/schema or rig-throughput claim; no new synthetic black-frame category or unbounded gap queue.

### 2026-10-09 [acquisition] [visual_stimulus] [shared] Complete portable worker coverage and execution extraction

- Completed `acquisition-worker-portable-tests` and `acquisition-execution-split`: `execution.py` 620 to 482 lines. Sol passes 55 cases with five skips, Win32 mypy 40 sources, boundaries 636 modules zero violations; Astra accepts. [Luna](reports/review-evidence-2026-10-09/nongui-luna-worker.txt), [Sol](reports/review-evidence-2026-10-09/nongui-sol-worker.txt), [Astra](reports/review-evidence-2026-10-09/nongui-astra-review.txt). Native SDK/Windows and full-load remain E15 rig checks.
- Coverage correction: statement coverage 328/1,159 (28.30%) to 616/1,159 (53.15%); statement+branch 24.53% to 47.83%. Post-extraction uses ten modules, not comparable.
- Run43 analysis: 1,186 real groups in 60 s, 1,182 capture admissions (99.66%); four drops cannot explain about 19.8 vs 60 groups/s; cause not isolated. [Assessment](reports/review-evidence-2026-10-09/nongui-throughput-assessment.json) supports a rig measurement only.

### 2026-10-09 [controller] [acquisition] [visual_stimulus] Review in-progress camera edits and padding

- `owned-camera-edits`: Sol finds five defects (hidden empty-batch rejection, post-confirmation failures mislabeled as rejected edits, missing concurrency fences, stale external pulse output on switch to free-running, missing controller routing of batch reports); returned for correction. [Review](reports/review-evidence-2026-10-09/nongui-sol-owned-camera.txt) is not acceptance.
- Per E07/A10, validated readback plus accepted ConfirmConfiguration defines adoption; later preview failure keeps committed configuration, no rollback or second commit protocol; root's delay-commit suggestion superseded.
- `video-cadence-padding`: encoded-count mismatch being corrected; shared-grid selection 14 cases, one fixture failure fixed to strictly-before-cutoff rule. All 138 GUI files unchanged.

### 2026-10-09 [controller] [acquisition] Clarify owned-edit commit and confirmation semantics

- `owned-camera-edits`: controller commits validated exact readback before ConfirmConfiguration; transport acceptance is not adoption proof. Confirmation/preview failure keeps committed configuration and reports failed/stopped device work, no rollback.
- A10 revision 56 and register updated: a fresh batch may carry the current accepted snapshot separately from proposed edits, syncing lagging bookkeeping only after prior exact work is quiesced. No second commit protocol; no role-only FinishEditing bypass. Final acceptance pending.

### 2026-10-09 [acquisition] [visual_stimulus] Close padding schema and fixed-policy bindings

- `video-cadence-padding`: writer emitted header version 2 vs declared 3; policies forbade duplication. Added one shared frame-log version constant; bound A07/A08/E13 in acquisition policy/config 19 and Visual Stimulus policy/config 8 (E14 digests updated). Evidence Header/registry advances to format 3; PreparedTrial/recipe stay format 2.
- Focused checks 80 pass; Visual contracts 42, 11 schemas match; Ruff and four-source Win32 mypy pass. Not final acceptance: Sol reproduces trailing inputs renewing the encoder-stall timer; Luna correcting. Native full-load pending; rig checklist predicates to update.

### 2026-10-09 [controller] [acquisition] [visual_stimulus] [shared] Resolve recording deadline review and continue backend integration

- `video-cadence-padding`: trailing writes count as active input; only encoder progress renews the stall timer. Luna: 362 acquisition passes (five skips, two exclusions), 71 cross-owner; 21 recording cleanup/path tests pass; canonical-rate mismatch fixed. Sol review pending.
- `owned-camera-edits`: second Sol review keeps four corrections (retained identity before late evidence, reciprocal Tracking fence, full prior Apply/preview terminal for every batch, exact failed-parent routing); 75-case snapshot 74 pass, not acceptance. `deadline-helper-sweep` proceeds.
- Tracking/stimulus contracts 48/42 pass; no native acceptance.

### 2026-10-09 [acquisition] [visual_stimulus] [shared] Review terminal padding boundaries

- `video-cadence-padding`: Sol accepts tail-progress/rate fix; contracts 48/42, schemas 19/11, 57 bindings byte-match, 841 links pass. Astra finds terminal defects: pre-T cancellation yields negative cutoff; repeated cancellation overwrites original cutoff; trailing duplicates written before validating Stopped timing/watermark; same-slot omissions give UNKNOWN/UNCONFIRMED. Returned to Luna; acceptance pending. [Findings](reports/review-evidence-2026-10-09/nongui-astra-review.txt), [probe](reports/review-evidence-2026-10-09/nongui-astra-padding-probe.py).
- `deadline-helper-sweep`: generic helper must keep arithmetic semantics; int64 validation stays in the transport wrapper.

### 2026-10-09 [controller] [acquisition] Review expired owned-edit recovery

- `owned-camera-edits`: Luna and Sol pass the 100-case corrected selection. Sol reproduces an expired-budget failure: undelivered Confirm leaves revisions 2/1, blocks terminal reports and retains a canceled resolution rejecting every fresh edit. [Probe](reports/review-evidence-2026-10-09/nongui-owned-expired-probe.py). Returned for bounded read-only late evidence and quiescence-based bookkeeping release; native/SDK ownership stays fenced until quiet. Acceptance pending.

### 2026-10-09 [shared] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] Review shared deadlines and terminal retry repairs

- `deadline-helper-sweep`: 135 expressions across 60 files; 56 files AST-identical, four separately reviewed; admission wrapper restored. 36 focused cases pass (one skip); Luna 997 plus 180 Visual Stimulus; six Tracking cases need loopback permission, unverified. 13 live camera/launcher sites remain; task open. Scopes overlap.
- `video-cadence-padding`: Astra's three terminal findings corrected; retry hazard fixed (retain written slot before maintenance; mapping-append failure poisons normal closure); first cancellation capped to scheduled end. 53 focused pass; 548 broader (five skips/three exclusions) before last change. Sol/Astra re-review pending.

### 2026-10-09 [acquisition] [visual_stimulus] [shared] Accept corrected padding and first deadline batch

- `video-cadence-padding`: Sol and Astra accept; Sol 53 focused pass; production errors stay failed/unconfirmed via fail_cleanup. [Disposition](reports/review-evidence-2026-10-09/nongui-astra-review.txt). Full integration pending; native encoder/full-load pending.
- Astra accepts the 135-site/60-file deadline batch. Camera late-child recovery, shared launch completion and the remaining 13 expressions still active; launch helper moved between Luna lanes. No GUI edits or device actions.

### 2026-10-09 [controller] [acquisition] Bind real owned-edit recovery and MCU authorization

- `owned-camera-edits`: Sol accepts empty-batch expiry fix (101 cases pass) but finds in the nonempty matrix: late terminal child evidence rejected, preview restart children with unrelated parent IDs, canceled resolution blocked after quiet. Preview start uncertainty must retain ownership and need exact Stop/Cleanup. [Matrix](reports/review-evidence-2026-10-09/nongui-sol-owned-camera.txt).
- MCU owner gate rejects proposed pulse settings before readback/commit. A11 revision 41 and register bind the pending A10 proposal to the exact edit operation, revision, bytes, authority, generation/claim and deadline; stale scope never falls back. No second commit protocol or firmware change. Luna implementing; validation pending.

### 2026-10-09 [acquisition] [visual_stimulus] [shared] Complete launch increment for review

- `worker-launch-handshake-sharing`: Luna completes the common native handshake sequence and both wrappers; exact PID/creation identity checked through Operational; WindowsJobs remains handle owner. [Scope/validation](reports/review-evidence-2026-10-09/nongui-luna-launch.txt): 57 focused passes, one skip/three exclusions, five-source Win32 mypy, Ruff/format, zero boundary violations. Sol review pending; no native Windows equivalence.
- Camera correction split into two Luna lanes (MCU pending-edit authorization path; late child/lifecycle/preview correlation/cleanup).

### 2026-10-09 [controller] [acquisition] Verify the complete MCU edit call chain

- `owned-camera-edits`: scoped MCU authorization passes 58 owner tests and Sol review, but the ManualDevices to typed client to lifecycle probe shows CONFIGURE with no active previews rejects an empty role selection although both outputs disabled is valid. [Probe](reports/review-evidence-2026-10-09/nongui-mcu-client-integration-probe.py). Return only CONFIGURE's empty-mask validation; ON/OFF keep nonempty masks. Add typed-client chain to owning tests.

### 2026-10-09 [repo] [controller] [acquisition] [visual_stimulus] [shared] Consolidate redundant review snapshots

- Eight intermediate raw handoff files proven byte-identical prefixes of the retained Astra/Sol handoffs; removed (176,555 bytes), links repaired. All findings retained. [Hashes/proof](reports/review-evidence-2026-10-09/cleanup.json). Cache cleanup waits for final checks.

### 2026-10-09 [controller] [acquisition] [visual_stimulus] [shared] Close launch review and finish deadline/MCU guards

- `worker-launch-handshake-sharing`: Sol and Astra accept; 57 tests pass (one skip, three exclusions); native Windows equivalence unverified.
- `deadline-helper-sweep`: Sol accepts final 11 controller substitutions (AST-identical, zero candidates left). Original inventory 148 sites: 135 + 10 controller + three launcher; one later-added expression in final migration.
- `owned-camera-edits`: stale edit-scope fields on ON reached serial; Luna adds a CONFIGURE-only scope guard before every branch (seven request kinds rejected). 59 owner cases pass within 163-case selection. Final Astra review and nonempty camera recovery pending.

### 2026-10-09 [controller] [acquisition] Review late SDK and preview cleanup recovery

- `owned-camera-edits`: Sol's matrix: fresh callers need exact read-only retained queries with their own budget; original SDK deadlines unchanged; prior-work admission runs for equal and lagging revisions. Keep preview ownership until actual viewer/ring release; lost/tardy Start and timed-out Stop need exact Cleanup/worker-retirement proofs. Luna implementing; no acceptance.
- Astra accepts final MCU guard and controller deadline remainder; 57 bindings and inputs match saved hashes; 138 GUI files unchanged.

### 2026-10-09 [controller] [acquisition] Exercise real recovery composition and claim-release failure

- `owned-camera-edits`: probe reproduces successful Stop leaving the cancelled edit blocked (MCU close clears observation). Retain confirmed OFF plus connection identity after successful close; Stop-to-fresh-resolution probe passes; real hardware untested.
- Real retained-query probe finds wrong protobuf field level and nonexistent lifecycle method hidden by mocks; recovery logic moves to a focused helper under ARCH-002.
- Failed/timed-out MCU close stays fenced; fresh bounded CLOSE retry after camera cleanup. A10 revision 57 and register updated; no new policy value or RPC. 18 TOMLs parse; seven decision revisions match.
- Refs: A11

### 2026-10-09 [repo] [controller] [acquisition] Validate repository checkpoint and finish exact cleanup reachability

- Checkpoint: 1,782 pass, six skips, eight exclusions (182.36 s); Ruff/format 848 files, Win32 mypy 733 sources, boundaries 638 modules zero violations; contracts 48/42, schemas 19/11. [Results](reports/review-evidence-2026-10-09/nongui-portable-checkpoint.result.json), [hashes](reports/review-evidence-2026-10-09/nongui-suite-source-hashes.json).
- `owned-camera-edits`: normal Stop falsely reported camera open when later MCU close failed; fixed by retaining device-cleanup fact separately. Failed-restart case lacked reachable exact Stop; pending run identity now recorded and only exact cleanup-pending Stop admitted. Finish exact retained Apply-status query via DeviceViews.
- Another 4,765-byte handoff prefix consolidated; nine redundant snapshots proven.

### 2026-10-09 [controller] [acquisition] Review final Stop admission and rejected edits

- `owned-camera-edits`: sweep 1,790 pass, six skips, eight exclusions, one fixture failure (fake selector lacks new keyword); [failed sweep](reports/review-evidence-2026-10-09/nongui-portable-before-rejected-edit-fix.result.json) preserved. Astra confirms rejected/never-dispatched edits can leave a nonexistent status obligation blocking a valid Stop; returned to Luna keeping unknown-admission obligations. Re-review pending.

### 2026-10-09 [repo] [shared] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] Complete local non-GUI implementation and review

- Completed `owned-camera-edits`, `video-cadence-padding`, `worker-launch-handshake-sharing`, `deadline-helper-sweep` (Astra final acceptance). Rejected/non-dispatched edits no longer need device status; unknown admission and prior unresolved work stay fenced.
- Final validation: **1795 passed, 6 skipped, 8 deselected in 309.49s**; Ruff/format 849 files, Win32 mypy 734 sources, boundaries 639 modules zero violations, contracts 48/42, schemas 19/11, 57 bindings, 18 TOMLs. Overlapping scopes. [Evidence](reports/review-evidence-2026-10-09/nongui-context.json). 138 GUI files unchanged; 876 links pass.
- One worker-test before-state unavailable; HEAD-to-final supplement kept. Stimulus-throughput task moved to Blocked (needs rig). Hygiene: 42 cache directories removed (321 files/28,233,854 bytes) ([cleanup](reports/review-evidence-2026-10-09/cleanup.json)). Evidence correction: first exact Stop succeeds, second rejects as expected. Native SDK/device/encoder/full-load, GUI, firmware open.

## 2026-10-09 — Updated Windows checkout verification

- `updated-tree-verification` [repo] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [gui] [shared]: clean checkout at `94285ac748419b74bec048394ad30807837ff4fe`. Initial collection fails in seven supervisor modules and Win32 mypy 17 errors from stale ignored Protobuf bindings; regenerated 19 protos with `tools/generate_contracts.py`, then mypy passes 734 sources. Ruff/format 849 files, boundaries 640 modules zero violations, 48/42 contracts and 19/11 schemas pass.
- Stale V08/V17/V18 root index revisions (2/2/4 vs owning 3/4/2) corrected in root index only.
- Completed: `pytest tests -q -m "not rig"` passes **1,820 / five skips / one rig deselection in 181.06 s** (skips: symlink privilege only). 57 bindings, 18 TOMLs, 114 revisions agree; 1,039 inputs unchanged; 882 links pass. [Context](reports/review-evidence-2026-10-09/windows-checkout-context.json). No physical/paired/optical/scientific/full-workload acceptance rerun.

## 2026-10-09 — Eye camera preparation and canceled Connect recovery

- `eye-camera-and-connect-recovery` [gui] [controller] [supervisor] [acquisition] [shared]: owner requests a third Eye camera, preview/video only, external trigger, not wired; serial, pin, frequency, drain allowance unset; no eye analysis or firmware install. Added Eye role (protobufs, policy-version 20, settings, workers, status, recording schema); external Eye capture rejects pending wiring before opening a worker. Fixed canceled Connect leaving a readback barrier, PFS readback cancellation, Disconnect Finish Editing.
- Native: serial 40278236 discovered; 40065509/40747103 verified via GUI Test enabled. Eye assignment rejected by missing V20 pacing output (not invented). MCU on COM8/115200 answers legacy `OK READY dual_camera_projector_sync` and `ERR Unknown command: CAPS`; explicit incompatible-firmware rejection added. Firmware HEX `0e4d05e6466328f26b33866793d895d65943ea4dfbd35165a2a090f2023bf630` compiled, no flash; installation authorization requested.
- Identity-command lifecycle acknowledgement routed to existing result-retention owner (seven scenarios pass).
- Final: **1,843 tests / five privilege skips / one rig deselection in 217.40 s** (earlier broad pass had one 2 s wait failure, passes in isolation); Ruff/format 849 files, mypy 734, boundaries 640. [Evidence](reports/review-evidence-2026-10-09/eye-camera-context.json). 922 links; task moved to Blocked; no physical acceptance.
- Refs: A10

## 2026-10-09 — Firmware picker and Upload recovery

- `firmware-picker-upload-recovery` [gui] [controller] [acquisition]: Browse works; Upload was blocked by a failure-only gate. Removed under G01 revision 134/A11; Eye included in controller admission; 40 focused cases pass (initial fixture failures retained).
- Owner-authorized native test: GUI Upload compiles/verifies `cephvr2_mcu.ino` on COM8; fresh connection reports `cephvr2_uno_2`, protocol 3, outputs stopped; Test connection succeeds. No recording, Eye trigger or SpikeGLX pairing.
- Full `not rig` regression **1,852 / five skips / one rig deselection in 213.86 s**; Ruff/format 849 files, mypy 734, boundaries 640. [Context](reports/review-evidence-2026-10-09/firmware-picker-context.json) closes the task; 927 links pass. Electrical/timing/interrupted-upload/experiment acceptance separate.
- Owner cannot see CephVR1.0 sketch: found `firmware/cephvr1_mcu.ino` and `projector_clock.h`; chooser left open; no upload.
- Refs: V20, `firmware/uno/cephvr2_mcu`, `cephvr1_mcu.ino`

## 2026-10-09 — Runtime replacement visibility recurrence

- `runtime-replacement-and-auto-control` [launcher] [gui] [shared]: missing `launcher.json` recurs; owner accepts E08 revision 170, owner-private `%USERPROFILE%/.cephvr2/runtime` ("move it"). Missing/relative USERPROFILE rejected; all 136 recovery records preserved byte-for-byte; fresh credentials, no old endpoints imported.
- Native PTY: N exits 0 keeping controller; Y starts a new controller only after the all-processes-absent receipt. Both helper contexts see the same endpoint (package API 15700, no package identity); owner's own terminal not manually retested.
- Final suite **1,856 / five skips / one rig deselection in 204.63 s**; focused 295; Ruff/format 849 files, mypy 734, boundaries 640; 1,039 inputs unchanged; 948 links. [Evidence](reports/review-evidence-2026-10-09/runtime-root-context.json), [baseline](reports/review-evidence-2026-10-09/runtime-replacement-baseline-context.json). Task completed.
- Follow-up: GUI retains legacy-sketch compile failure (`projector_clock.h` missing). V20 pacing/Eye wiring deferrals remain.
- Refs: `firmware/uno`, `tests/shared/test_auth.py`, `test_invariants.py`

## 2026-10-09 — Legacy sketch companion layout repair

- `legacy-firmware-companion-path` [gui] [controller] [acquisition]: both sketches placed in independent valid directories under `firmware/uno`, header copied beside the legacy source (hashes identical); backend include discovery unchanged per A11/E08/ARCH-002.
- Compile only, no serial: CephVR1 16,366 flash/603 RAM bytes, CephVR2 11,078/1,112; MCU owner suite 68 pass (one skip). Legacy CAPS incompatibility remains. Native Browse accepts `firmware/uno/cephvr2_mcu/cephvr2_mcu.ino`, Upload enabled; no Upload/Test pressed. Prior full/static checks carried forward, not rerun. [Evidence](reports/review-evidence-2026-10-09/firmware-layout-compile.json), [context](reports/review-evidence-2026-10-09/firmware-layout-context.json). Task completed.
- Refs: `projector_clock.h`

## 2026-10-09 — Optional MCU I/O and all-projector VSync

- `mcu-optional-io-and-all-vsync` [gui] [controller] [acquisition] [visual_stimulus]: owner disconnects projector flip and selects all-output VSync with no pacer. A11 revision 43, V20 revision 8, V15 revision 12, E13 revision 21 plus register; flip input defaults Off, pin kept. Visual fixed policy/config version 9; prepared-trial schema regenerated; mixed pacing still needs an enabled output. Custom-signal question unanswered.
- Focus passes 300 (one skip), 42 Visual contracts; failed JUnits preserved. Static checks: Ruff/format 849 files, mypy 734, boundaries 640. Full regression 1,858 passed, one exact-completion timeout (passes on rerun), five skips, one deselection in 183.35 s; not a full pass.
- Stopped/deferred at owner request: startup exits on saved DLP identity matching zero active monitors (projectors disconnected). No new upload, MCU Apply or dummy protocol. V19 failure-classification follow-up recorded.
- Refs: A10

## 2026-10-11 — GUI/runtime gap assessment

- `gui-runtime-gap-assessment` [gui] [controller] [acquisition] [visual_stimulus] [tracking] [spikeglx]: source at `f96286e` reviewed. Priorities: disconnected-projector startup classification and measured stimulus throughput; paired/scientific, electrical/optical, GUI/DPI, fault cleanup, latest regression/declaration acceptance stay open. No new backend defect established.
- Assessment only; nothing run; `git diff --check` passes. Task completed, temporary TODO entry removed.
- Refs: G01, V19

## 2026-10-11 — Sequential GUI/runtime repairs

- `mcu-optional-io-and-all-vsync` [gui] [controller] [visual_stimulus]: under V19/E06/E08 only exact missing/ambiguous startup monitor identities are recoverable after verified sessionless cleanup within the original deadline; identities preflighted before windows open. Owner selection 649 pass (one rig deselection); cancellation guard five; mypy 735 sources, boundaries 640 modules zero violations; contracts 48/42, 19/11 schemas, 57 bindings. Three listener binds needed loopback permission. Local only, not Windows/projector acceptance.
- Full suite 1,861 pass, six skips, eight deselections (307.43 s); evidence and 1,040 hashes in `reports/runtime-evidence-2026-10-11/`; 19 TOMLs, 107 revisions match. Historical Windows timeout cause and native Apply not closed; rig checklist gets disconnected/reconnected steps.
- `trial-epoch-shuffle` [gui]: owner selects shuffling top-level epochs/groups as intact blocks (G01 revision 135). Completed: GUI owner suite 381 pass (284.12 s); five shuffle/layout cases pass; Ruff/format 845 files, mypy 735, boundaries 640, 546 links. Context in `reports/runtime-evidence-2026-10-11/context.json`. Native teardown helper issue not resolved; no native pass claimed.

## 2026-10-11 — Stimulus throughput source investigation

- `stimulus-throughput-source-trace` completed [visual_stimulus]: run43 snapshots show all-output VSync, four interval-1 outputs, 60 Hz, 8-bit. Sequential context swaps are the leading hypothesis (49.29 ms group median) but causality not established locally; 20.48 MB/capture, render-thread copy/allocation and recording-lock are candidates; four drops, 50 ms loop delay, padding, 10-bit mask excluded as sufficient. Report/rig checklist updated; no runtime run or performance claim.
- `gui-backend-dummy-experiment` [visual_stimulus]: rig checklist expanded (per-output swap timing, recording on/off, per-stage timing, padding); no rig test executed.

## 2026-10-11 — GUI error and recovery review

- `gui-error-recovery-review` completed [gui]: three reproduced defects fixed (acceptance callback clearing newer-edit explanation, rejected install leaving edit tracking suppressed, rejected reload raising) by reusing the projection context manager under G01/E03/E07. Managed/recovery selection 82 pass (301 deselected); three regressions pass; Ruff/format 138 files, mypy 136, boundaries 640 modules zero violations. No further defect found. Native GUI/Windows acceptance pending.

## 2026-10-11 — Repository cleanup

- `repository-code-cleanup` completed [repo] [acquisition] [controller] [supervisor] [shared] [gui]: removed unused helpers and 51 obsolete N802 comments; 25 GUI ASTs identical, 37 files shrink by 119 net lines. Owner checks 1,032 pass; integration 424 pass with 27 sandbox loopback failures, permitted rerun 43 (1,483 distinct passes, six skips, eight deselections). Ruff/format 874 files, mypy 735, boundaries 640. 74 cache directories (51,093,992 bytes) removed. GUI checked by AST, no new GUI run; no native acceptance.

## 2026-10-12 — Second repository cleanup pass

- `repository-code-cleanup-pass2` completed [acquisition] [visual_stimulus]: removed dormant acquisition MCU diagnostic state, unused properties, redundant callback/field writes; eleven files shrink by 63 net lines. Selection 795 pass, five skips, three deselections (74.60 s); Ruff/format 874 files, mypy 311 sources, boundaries 640. No contract/policy change; no native acceptance. Evidence artifacts removed at owner request on 2026-10-12.
- Refs: A02, A11, E08, V01, V11, V19, V21

## 2026-10-12 — Runtime and Review GUI parity

- `runtime-review-gui-parity` completed [gui]: no unintended layout difference under G01/G02/E03; parity test extended at 1280/720 px across all pages/tabs (lease controls excepted). Focused selection five pass (17.53 s); Ruff/format 138 files, mypy 136, boundaries 640. Production sources unchanged. [Evidence](reports/runtime-evidence-2026-10-12/gui-parity-context.json). Offscreen only; no native Windows/DPI/hardware acceptance.

## 2026-10-12 — Protocol controls simplification

- `protocol-controls-simplification` completed [gui]: Trials arrows and timeline Delete/Duplicate buttons removed (G01 revision 137); shortcuts kept via a scope/authority guard. Seed/Gap relocation is a recommendation only, not accepted. Focused 11 pass (48.13 s); Running-phase case one pass; Ruff, mypy 138 sources, boundaries 642 modules zero violations. [Context](reports/runtime-evidence-2026-10-12/protocol-controls-context.json). No native/DPI/hardware pass.

## 2026-10-12 — Devices configuration and supported signals

- `devices-config-and-signal-editing` completed [gui]: Configuration file card (Load/Save) on every Devices tab; Test selected beside Connect replaces Test enabled; Apply pin settings removed; supported MCU signals chosen by dropdown with Add/remove; only SpikeGLX channel index visible. G01 revision 136 and G02 revision 35 record it, preserving concurrent G01 revision 137. MCU v2 files retain enable flags, v1 loads without changing participation, conflicting full-file flags rejected before mutation; Load sends no device/enable/firmware commands.
- ARCH-002: shared camera serialization/validation; MCU row editing isolated; no backend protocol/firmware/policy/dependency change. Full portable/offscreen GUI suite passes **390 in 353.58 s**; Ruff/format 140 files, Win32 mypy 138 sources, boundaries 642 modules/zero violations, whitespace pass. Initial run had one stale-fixture failure (389 passes), corrected. A redundant repeat was interrupted (Qt abort -6, retained, not counted). [Evidence](reports/runtime-evidence-2026-10-12/devices-gui/context.json). No native window/DPI/Windows acceptance claimed.

## 2026-10-12 — Selected trial settings layout

- `selected-trial-fields-layout` completed [gui]: owner accepts Seed/Gap below the Trials list; G01 revision 138 and root register. Selected trial section with full-width Random seed and Gap after trial (s); final-trial gap disabled but draft retained; matched Trials/timeline card heights. ARCH-002: redundant timeline-height cache removed.
- Nine focused checks pass (380 deselected, 22.01 s); Ruff, scoped format, Win32 GUI mypy 138 sources, boundaries 642 modules/zero violations, whitespace and doc references pass. [Evidence](reports/runtime-evidence-2026-10-12/selected-trial-context.json). No native Windows/DPI/live restart/hardware/full GUI or rig pass claimed.

## 2026-10-12 — Config-only trial Seed

- `protocol-config-only-seed` completed [gui]: owner removes Gap and makes Seed config-file only. G01 revision 139 supersedes the Selected trial section; the per-trial Protocol JSON stimulus_seed_decimal parameter is retained. Widgets/synchronization removed from ProtocolPage under ARCH-002; E01/E07 validation and schema/timing/policy unchanged; file contract documents config-only seed strings.
- Ten focused tests pass (379 deselected, 11.78 s); seeds zero/42 survive reload, selection and resave. GUI Ruff, format, Win32 mypy 138 sources, boundaries 642 modules/zero violations, references, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/config-seed-context.json). No native Windows/DPI/live restart/pixel/hardware/full GUI or rig pass claimed.

## 2026-10-12 — Compact Protocol actions and default tab

- `protocol-default-and-compact-actions` completed [gui]: G01 revision 140 and root register. Natural-width Shuffle/Preview buttons in a right-aligned action group; PlannerControls defaults to Batch generate (explicit source selection still opens Batch edit; tab switches keep drafts); calibration configuration caption changed to Load without changing import behavior. ARCH-002: redundant grid rebuilding removed.
- Twelve focused checks pass (377 deselected, 13.22 s); GUI Ruff, format, Win32 mypy 138 sources, boundaries 642 modules/zero violations, references, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/compact-default-context.json). No live restart/native Windows/DPI/hardware/full GUI or rig pass.

## 2026-10-12 — Empty MCU Inputs header

- `mcu-empty-input-header` completed [gui]: Inputs table header hidden when empty; G01 revision 141 and root register. Visibility set in the existing signal refresh path; shared DataTable fitting excludes a hidden header's height. ARCH-002: no new state or dependency.
- Eighteen focused cases pass (371 deselected, 16.78 s); Ruff/format, Win32 GUI mypy 138 sources, boundaries 642 modules/zero violations, references, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/mcu-empty-header-context.json). Local offscreen only; no native Windows/DPI/live restart/hardware/full GUI or rig pass.

## 2026-10-12 — Consistent file-action rows

- `consistent-file-actions` completed [gui]: Load… / Save as… captions restored; consistent file-action rows across all four Devices cards (zero inner margins, shared gap, equal button stretch/height, Load first); Tracking actions stay beside Pipeline. G01 revision 142, G02 revision 36, root register. ARCH-002: no new helper/state/dependency; no file/command semantics change.
- Six focused cases pass (383 deselected, 10.25 s); Ruff/format, Win32 GUI mypy 138 sources, boundaries 642 modules/zero violations, references, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/file-actions-context.json). Local offscreen only; no live restart/native Windows/DPI/hardware/full GUI or rig pass.

## 2026-10-12 — Shared device-control consistency audit

- `shared-device-controls-audit` completed [gui]: G01 revision 143, G02 revision 37, root register specify one accessible Refresh icon with inventory header placement, Use-first/single-row inventory selection, COM Refresh beside selector, and empty signal-header fitting via focused helpers in DataTable. Camera duplication and Projector/MCU outside scan rows removed; discovery commands, identities, mappings and locks kept. Protocol variation-row 38/36 px height drift fixed by reusing equal_row_height on show. No new dependency/state/backend mechanism.
- Final affected selection passes 77/312 deselected in 51.53 s (earlier initial 76 pass had the row-height defect; a constructor-parenting candidate failed and was reverted). Ruff/format 140 files, Win32 mypy 138 sources, boundaries 642 modules/zero violations, references, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/shared-controls-context.json). No full GUI/native Windows/DPI/live restart/device/rig pass.

## 2026-10-12 — Config-controlled projected reference bars

- `projected-bars-measurement-table` completed [gui] [visual_stimulus]: owner chooses config pixel lengths to control projection. G01 revision 144, V01 revision 16, root register. Config-only screens.<face>.reference_x_px/reference_y_px feed native bars, affine conversion and preview; scale independent of throw ratio; measured X/Y mm inputs merged under one header, read-only mm/px estimates kept. Full/numeric file versions 5/4 migrate legacy lengths; noninteger/oversized values rejected before mutation. Owning schemas regenerated.
- Final selection passes 71/360 deselected in 41.62 s; contract suite 42 tests/79 subtests. Ruff/format 283 files, Win32 mypy 265 sources, 11 schemas/zero drift, boundaries 642 modules/zero violations pass. Initial partial-output, render-fixture and static failures corrected; a nonexistent contract-check script ran nothing. [Evidence](reports/runtime-evidence-2026-10-12/projected-bars-context.json). No full GUI/native Windows/DPI/GPU/optical/rig pass; rig procedure updated.

## 2026-10-12 — Pixel-to-mm calibration card layout

- `reference-scale-card-layout` completed [gui]: G01 revision 145, root register: card named Pixel-to-mm calibration, three columns evenly stretched; SpikeGLX connection prose removed (read-only host controls and config-path tooltip kept). ARCH-002: header override and note widget removed. Source-verified: projector distance derives from projected width times positive throw ratio, never read by launch; measured affine application currently also requires throw.
- Eight focused cases pass (381 deselected, 16.10 s); GUI Ruff/format 140 files, Win32 mypy 138 sources, boundaries 642 modules/zero violations, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/reference-layout-context.json). Local only; no full GUI/native Windows/DPI/optical or rig acceptance.

## 2026-10-12 — Calibration workflow assessment

- [gui] [visual_stimulus] Source-only review of the owner-proposed geometry, reference measurements, throw-derived distance, grid and manual scale/offset workflow. Recommends using measured X/Y pixel scale directly with physical screen geometry for the initial grid mapping, keeping throw-derived distance as an estimate (feeding it back adds no independent measurement). Separate presentation steps and decoupling are recommendations, not accepted or implemented. No runtime/rig validation; no implementation authorized; rig deferrals remain.

## 2026-10-12 — Two-stage projector calibration workflow

- `two-stage-projector-calibration` completed [gui] [visual_stimulus]: separate Measure reference bars (exact native-pixel lengths on black) and Adjust frame and grid (needs complete mode-matched X/Y measurements; omits bars); direct mm/px mapping; throw ratio config-only for distance estimation, GUI editor hidden but screens.<face>.throw load/save kept. Neither launch nor mapping requires throw. Close confirms diagnostic release before switching. G01 revision 146, V01 revision 17, root register; two owning schemas regenerated.
- Final selection passes 74/359 deselected in 72.31 s; 42 contract tests/79 subtests; Ruff/format 283 files, Win32 mypy 265 sources, 11 schemas/zero drift, boundaries 642 modules/zero violations pass. One incorrect test comparison fixed. [Evidence](reports/runtime-evidence-2026-10-12/calibration-workflow-context.json). No full GUI/backend suite, native Windows/DPI/GPU/optical or rig acceptance; native/hardware follow-ups retained.

## 2026-10-12 — Long-protocol and image-loading assessment

- `long-protocol-resource-scaling` [gui] [visual_stimulus]: source review against G01, E07, V02/V03/V04/V07/V11/V13 finds cached but eagerly expanded GUI views capped at 2,000 occurrences, full-view painting, and per-trial retained static image preparation. Recommends incremental/visible-range editing, compatible resource reuse and bounded image lookahead, keeping whole-session asset validation and source protection. Image-miss/readiness behavior remains a design choice; no policy accepted, no runtime code changed. One TODO design follow-up retained. Doc links/anchors and git diff --check pass; no benchmarks, runtime suite or rig acceptance.

## 2026-10-12 — Photodiode frame and Blackout zones

- `photodiode-frame-and-blackout-zones` completed [gui] [visual_stimulus]: separate black-area X/Y/Width/Height and relative square X/Y/Size, plus per-screen Blackout zones Add/remove. G01 revision 147 (kept by concurrent 148), V15 revision 13, V19 revision 5, V22 revision 4, root register: bottom-left coordinates, strict bounds, marker priority, trial-only photodiode, persistent Idle/grid zones. Full Projectors JSON 6/numeric 4 migrates old rectangles. Zones propagate into diagnostic bundles; raw measurement bars unobscured. Two schemas regenerated; rig procedure extended.
- ARCH-002: focused zone/clear helpers; no shader/dependency/process/GPU resource. Broad local stage passes **665/one deselection/79 subtests in 377.33 s**; final affected 21/413 deselected in 18.66 s (staged, not an exact-final-tree full suite). Ruff/format 289 files, Win32 mypy 271 sources, 11 schemas/zero drift, boundaries 649 modules/zero violations pass. [Evidence](reports/runtime-evidence-2026-10-12/output-overlays/context.json). Empty-table height and clipped-control defects repaired. Native Windows/DPI/GPU, optical/electrical timing, black levels and rig throughput remain open.

## 2026-10-12 — Bounded still-image residency accepted

- `long-protocol-resource-scaling` [gui] [visual_stimulus]: owner accepts bounded image preloading. V04 revision 12 and root register formalize protected-source lifetime across decoded-pixel eviction; E07 full-session decode validation, initial preparation, deadlines, reuse and bounded resident accounting preserved. Image-miss response, readiness/lookahead remain Open; GUI visible-range loading remains a proposal. First-time validation still decodes all unique images; bounded retention only removes aggregate pixel growth. V04 anchors and whitespace pass. No runtime, timing, memory or rig validation.

## 2026-10-12 — Review GUI photodiode inspection launch

- [gui] Owner asks to inspect photodiode and Blackout zones: launched standard review entry point with isolated simulated fixtures, navigated to Devices → Projectors → Synchronization; no config or device changes. Qt reports visible=True, exposed=True, one screen; app left running. Verifies window exposure/navigation only, not Windows/DPI, projector output or optical acceptance. Sandbox process-list read denied; no source change or tests.

## 2026-10-12 — Grouped timeline and image worker design discussion

- `long-protocol-resource-scaling` [gui] [visual_stimulus]: reviewed G01/V02/V08 grouping and renderer video-thread ownership. Proposed (not accepted; would revise G01): group-level overview with on-demand detail, repetition/shuffle semantics unchanged. Compared sequential ring buffer with bounded reusable image cache plus small read/decode thread pool, keeping GL context ownership, active-consumer pinning, byte admission and deadlines. Pool size and image-miss behavior remain open; no new processes or runtime change. Scoped whitespace passes; no performance, runtime or rig validation.

## 2026-10-12 — Empty Blackout zones header

- `blackout-empty-header` completed [gui]: G01 revision 149, root register: empty Blackout zones header hidden via DataTable.fit_rows(hide_empty_header=True) in construction, Add, remove and file restoration (ARCH-002: no new state/dependency).
- Seven focused checks pass (388 deselected, 19.12 s); GUI Ruff, format, Win32 mypy 140 sources, boundaries 649 modules/zero violations, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/blackout-header/context.json). Running Review window needs reopening to load this. No new native/DPI or rig acceptance.

## 2026-10-12 — Image/grey repeat-group example

- `long-protocol-resource-scaling` [gui] [visual_stimulus]: explanation only. Source inspection confirms Repeat / vary… supports a consecutive two-epoch group with Repeat count and As listed order; 300 repetitions give 600 occurrences from two source epochs. A same-image example needs one reusable image asset and no grey image file. Proposed collapsed group overview differs from current expanded timeline; no acceptance inferred, no source/runtime changes or tests; TODO stays open.

## 2026-10-12 — Protocol hierarchy controls proposal

- `long-protocol-resource-scaling` [gui] [visual_stimulus]: owner asks for best GUI controls/layout, not implementation. Proposed persistent trial overview, breadcrumb-scoped group content and shared epoch inspector, with group-selected and current-scope batch generation shown in an interactive mockup. No runtime/config/schema or accepted-architecture change. Fragment read-back and JavaScript syntax (Node static check) pass; browser inspection blocked by file-URL policy, so no rendered/interaction verification. Report/log whitespace passes; TODO stays open.

## 2026-10-12 — Frame/Pulse definition table

- `photodiode-definition-table` completed [gui] [visual_stimulus]: Frame/Pulse rows with Origin X, Origin Y, Width, Height replace separate forms. G01 revision 150, V22 revision 5, root register: bottom-left Frame origins, Frame-relative Pulse origins, independent positive dimensions, strict containment. Full Projectors JSON 7 uses frame_rect/pulse_rect; v6 Size migrates to equal dimensions; v3/4/5 rectangles and numeric 4 preserved; invalid files rejected before mutation. No new GL resources/dependencies.
- Fifty affected cases pass (371 deselected, 180.83 s); final nine pass (412 deselected, 88.21 s) (overlap, not summed); contract suite 42 tests/79 subtests in 12.51 s. Ruff/format 289 files, Win32 mypy 271 sources, 11 schemas/zero drift, boundaries 649 modules/zero violations, whitespace pass. Link scan finds two missing live-grid-context.json references from the concurrent calibration chat (not fabricated). [Evidence](reports/runtime-evidence-2026-10-12/pulse-definition-table/context.json). No native Windows/DPI/GPU/optical timing or rig acceptance.

## 2026-10-12 — Grouped protocol editor implementation started

- `long-protocol-resource-scaling` [gui] [visual_stimulus]: owner accepts grouped overview/editor and authorizes GUI implementation reusing batch generation and epoch controls. ARCH-002 review selects compact source-node views, a focused hierarchy-control widget and pure scoped document operations on the canonical group model with existing validation/history; no schema/dependency change. Image streaming/miss contracts excluded. Initial GUI/test hashes captured; concurrent work preserved.

## 2026-10-12 — Live frame/grid scale and offset

- `live-calibration-adjustments` completed [gui] [controller] [visual_stimulus]: Scale X/Y and Offset X/Y edits update the active frame/grid without Close/relaunch. G01 revision 148, V01 revision 18: exact diagnostic/revision, leased, sequence-bound UpdateDisplayCalibration; GUI debounce 150 ms coalesces edits; invalid fields keep the last valid projection. GL owner validates rectangles, inversion, mesh tolerance and float32 nondegeneracy before writing retained VBOs. Pre-write rejection preserves prior sequence; GPU uncertainty stays Unknown with Close enabled. No experiment-time mapping/timing change.
- Protobufs regenerated (19 sources/57 binding files match). Controller/Visual Stimulus suites pass 659/one deselection; final guard run 658 with one CLI-help timeout, unchanged test then passes isolated 1/0.68 s (10 s threshold not widened; no exact-final-tree full pass claimed). Authenticated real coordinator/renderer services pass with hardware submission injected. 60 GUI cases pass (335 deselected, 64.76 s); contracts 42/79 subtests; Ruff/format 423 files, Win32 mypy 376 sources, 11 schemas/zero drift, boundaries 649 modules/zero violations pass. [Evidence](reports/runtime-evidence-2026-10-12/live-grid-context.json). No full-GUI exact-final-tree, native Windows/DPI/GPU/optical latency or rig acceptance.

## 2026-10-12 — Calibration adjustment increments

- `calibration-adjustment-steps` completed [gui]: G01 revision 151, root register, calibration contract: scale step 0.01 (two decimals), offset step 0.1 px (one decimal); imported precision and partial drafts kept; steps emit the existing live user-edit signal; invalid input/nonpositive steps leave drafts untouched. ARCH-002: helper stays in the calibration module.
- Five cases pass (401 deselected, 6.14 s); Ruff/format, GUI Win32 mypy 141 sources, boundaries 650 modules/zero violations, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/calibration-steps/context.json). No new native Windows/DPI/optical/rig acceptance.

## 2026-10-12 — Grouped Protocol implementation and local review

- `long-protocol-resource-scaling` [gui]: implementing the G01 revision 151 grouped overview/Sequence editor on canonical V02/V03/V08 groups; compact program/scope views replace repetition expansion, only viewport blocks paint; breadcrumbs, group fields, nested creation, grouping, scoped insertion; condition references follow group rename. ARCH-002: focused hierarchy widget, existing pure transforms, no schema/dependency/process/image-loading change.
- Tests extended (300 repeats, nesting, insertion modes, rename, save/reload, history, authority). Affected runs 46 (three old-overview failures), 12 (one hidden-resize scrolling defect repaired), 11, 57 (two old-layout/API assertions updated). Static collisions and a Python 3.11 quote corrected; capture teardown exit 139 fixed by processing deferred deletion. Not rig acceptance; final results pending.
- Revision correction: concurrent calibration stepping also recorded G01 revision 151; final grouped-editor amendment is revision 152 in G01/root register.

## 2026-10-12 — Grouped Protocol GUI completed

- `long-protocol-resource-scaling` GUI portion completed [gui]: G01 revision 152 (preserves calibration stepping 151). Full GUI stage 401 passes with five obsolete assertions; after updating them, final affected checks pass 62/344 deselected in 64.41 s (earlier 59 and 15 overlap). Group edits keep the clicked anchor; Undo discards invalid fields without document history.
- Ruff/format 143 files, Win32 mypy 141 sources, boundaries 650 modules/zero violations, links, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/grouped-timeline/context.json). No exact-final-tree full GUI pass; native Windows/DPI/full-workload pending. Only the bounded-image contract follow-up returns to Next; no image runtime implementation.

## 2026-10-12 — Cleanup artifact removal

- `cleanup-artifact-removal` [repo] [acquisition] [visual_stimulus] [shared]: owner-selected removal of 10 untracked cleanup evidence files (Oct11/Oct12) and 58 generated cache directories (45,470,681 bytes) from this chat's two cleanup passes only. Hash check confirms 3294 other source/contract/test/evidence files unchanged; AST/reference scans find no unreferenced private definitions, so no further code deletion. Report references updated; earlier LOG evidence links annotated as removed.
- Completed [repo]: deleted-artifact and Markdown-reference checks and `git diff --check` pass; regenerated Ruff/mypy caches removed again. No source change or runtime test claim.

## 2026-10-12 — Flat group/batch GUI refinement started

- `flat-group-batches` [gui] [visual_stimulus]: owner authorizes top-level groups only, epoch-only group contents, separate editable generated batches. ARCH-002 review reuses the source timeline, batch/epoch controls and canonical groups; adds only a persistent authoring batch identity so same-label generations do not merge. Imported scheduling semantics preserved; no image preparation or runtime scheduling change. Initial hashes captured.

## 2026-10-12 — Flat groups and persistent generated batches

- `flat-group-batches` [gui] [visual_stimulus]: G01 revision 153, V03 revision 10, root register: flat GUI groups with optional authoring batch identity. New/default trials grouped; root + Group; flat group offers + Epoch and Generate/Edit epochs; generation appends flat copies with distinct ID. Imported/headless nested programs intact; nested-group dialog removed; generated Program/PreparedTrial schemas updated. ARCH-002: pure batch construction/selection; no dependency/process change.
- Tests extended. Initial full stage 26 failed/381 passed (obsolete layout/nested expectations); corrections: layout 6, batch/file 12, targeting/parity 9 (overlap). Shortcut dispatch bypassing the target-filter guard fixed; two keyboard cases pass. Portable config/compiler/contracts pass 58 tests/79 subtests; 11 schemas/zero drift; 650 modules/zero boundary violations. 1280/720 captures inspected (placeholders, not image I/O evidence). Full GUI stage still running; no Windows/DPI/optical/image-streaming/rig acceptance.

## 2026-10-12 — Flat group/batch GUI completed

- `flat-group-batches` completed [gui] [visual_stimulus]: full GUI stage 407 passed/1 failed in 328.73 s (stale expectation that entering a group opens Generate rather than the accepted Edit default); affected stage 71 with same failure (336 deselected, 81.12 s). After the fix, five final focused cases pass (403 deselected, 7.78 s). Shortcut guard defect found in source review. No exact-final-tree full-suite pass claimed.
- Ruff/format 144 files, Win32 mypy 142 sources, boundaries 650 modules/zero violations, 58 config/compiler/contract cases with 79 subtests, 11 schemas/zero drift, 599 links/anchors, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/flat-groups/context.json). Image readiness/residency follow-up stays open.

## 2026-10-12 — Unified subgroup editor started

- `unified-subgroup-editor` [gui]: owner authorizes one batch-composer-based subgroup editor with no duplicated mode/target controls and template-based + Epoch with immediate selection. ARCH-002 selects a focused subgroup form and pure atomic source transforms reusing composition/variation and history; untouched imported differences preserved; no runtime hierarchy, schema or dependency change. Initial hashes captured.

## 2026-10-12 — Model hierarchy repository audit started

- `hierarchy-audit-20261012` [repo] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [gui] [spikeglx] [launcher] [shared]: owner authorizes evidence-driven audit, justified implementation, model review and exact task-owned cleanup. Baseline HEAD `f96286e86dc9af334da78ab55a8c14ec111c6184` with extensive pre-existing edits preserved. Sol high coordinates Luna high scans; Astra reviews dispositions and final acceptance.
- Baseline checks pass: Ruff/format (863 files), Win32 mypy (748 sources), boundaries (653 modules/zero violations), whitespace, 19 Protobuf sources/57 files no drift, contract unittests (48/42), schema checks (19/11). Non-GUI pytest 1,464 passes/six skips/eight deselections/28 loopback-bind failures under sandbox; permitted rerun passes 1,492/six skips/eight deselections in 18.58 s. GUI under concurrent editing; native/rig acceptance separate.

## 2026-10-12 — Unified subgroup editor completed

- `unified-subgroup-editor` completed [gui]: G01 revision 154, root register: unified composer with per-projector parameters, Copies, Name, variation rules, one Apply/Discard pair; Generate/Edit tabs, target filters, separate inspector and batch selector removed. + Epoch copies one template, applies valid pending edits and selects the new subgroup. Flat groups, atomic updates, batch identities, member differences, per-epoch fade timing kept; no schema/dependency/runtime change.
- Initial full GUI stage 96 failures/314 passes (test migration, fixture/clock corrections, offscreen retry); source review repaired movement/fade retiming. Final broad stage 392 passes in 282.60 s; layout 14, behavior 7 (393 collected); broad run predates last refinements, so no exact-final-tree full pass. Compiler/config 16, Ruff/format 146 files, Win32 mypy 144 sources, boundaries 653 modules/zero violations pass. [Evidence](reports/runtime-evidence-2026-10-12/unified-subgroups/context.json). No native Windows/DPI/image-streaming/rig acceptance.

## 2026-10-12 — Model hierarchy audit completed

- `hierarchy-audit-20261012` completed [repo] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [gui] [spikeglx] [launcher] [shared]: two `gpt-6-luna` high auditors, `gpt-6.1-sol` high validation of the sole candidate, `gpt-6-astra` low approval. RT-001 adds the missing shutdown-intent guard to the locked live-calibration admission predicate (one production line, six test lines); V01/E06/E08 already govern it; no architecture revision, dependency or performance claim.
- Controller/Visual Stimulus suites pass 659/one deselection in 10.56 s; focused 1/16 deselected; full offscreen GUI 393 in 246.07 s; earlier non-GUI baseline 1492/six skips/eight deselections (not summed). Ruff/format (865 files), Win32 mypy (748 sources), boundaries (653 modules/zero violations), whitespace pass. [Assessment](reports/runtime.md#current-scope-and-review) records digest, coverage, E15 limits.
- No user decision remains; native Windows/device/scientific/full-workload acceptance and deferrals stay open. Task-owned test directories and generated bindings removed; token/cost metrics unavailable.

## 2026-10-12 — Direct group editor started

- `direct-group-editor` [gui]: owner requests direct first-epoch editing, Add/Remove group beside Preview, and removal of Shuffle trial, subgroup Copies and repetition/count helper labels. ARCH-002: keep document/history and composer ownership, remove navigation widgets; group repetitions alone repeat sequences. Imported values preserved; deterministic test images/textures prepared for the local review draft.

## 2026-10-12 — Direct group editor completed

- `direct-group-editor` completed [gui]: G01 revision 155, root register: direct first-epoch selection, group actions beside Preview; Trial navigation, Shuffle trial, subgroup Copies and redundant labels removed. Unified composer reused; group repetitions repeat the full sequence; pending epoch templates preserved. No dependency/schema/runtime change.
- Six RGB test images and three texture design/PNG pairs created in `demo_assets`; only the ignored local review draft assets root points there. Native review GUI launched; desktop tool cannot attach, so no native interaction claimed.
- Full GUI stage 393 passes with two obsolete Copies-layout expectations, then only hidden-parent assertions failing (corrected); six layout/group cases pass; no exact-final-tree full pass. Ruff/format 146 files, Win32 mypy 144 sources, boundaries 653 modules/zero violations, links/whitespace pass. [Evidence](reports/runtime-evidence-2026-10-12/direct-groups/context.json). Native Windows/DPI/rig and image streaming separate.

## 2026-10-12 — Persistent subgroup variations started

- `subgroup-variation-persistence` [gui] [visual_stimulus]: owner requests whole-subgroup edits, retained variation controls and independent projector randomness unless shared explicitly. Source inspection finds single-epoch selection, cleared rule widgets and a shared sample list. ARCH-002: persistent rule metadata follows the owning document, not a widget cache. Open question: whether random draws also vary between group repetitions.

## 2026-10-12 — Persistent subgroup variations completed

- `subgroup-variation-persistence` completed [gui] [visual_stimulus]: owner confirms independent samples per repetition and projector. G01 revision 156, V03 revision 11, V08 revision 4, root register: complete-subgroup selection, retained rule controls, opt-in projector sharing. Editor metadata stored separately from per-repetition settings; compiler selects by the enclosing group's repetition index; samples regenerate on repetition change, kept on unrelated edits, reload, Undo. Settings validated against scene/assets/feedback; schemas regenerated. Random operations bounded to 2000 occurrences. No renderer RNG/dependency change.
- Full GUI 396 passes; 19 focused plus mixed-subgroup case pass; Visual Stimulus 232/one deselection (restricted run 224 passes/eight bind failures). Ruff/format 163 files, Win32 mypy 160 sources, boundaries 655 modules/zero violations, 11 schemas, 943 links/anchors pass; no exact-final-tree combined run. [Evidence](reports/runtime-evidence-2026-10-12/subgroup-rules/context.json). No full-workload or native Windows/projector/rig acceptance.

## 2026-10-12 — Compact long-protocol rules started

- `compact-long-protocol-rules` [gui] [visual_stimulus]: owner rejects the 2000-occurrence cap and requests Order removal, index-only narrow Layer and clock timeline durations. ARCH-002 selects persisted seeded rules evaluated on demand/at Setup instead of larger eager tables; shared pure numeric patches move to the backend configuration helper (no backend-to-GUI dependency, no renderer RNG). Imported concrete tables preserved.

## 2026-10-12 — Compact long-protocol rules completed

- `compact-long-protocol-rules` completed [gui] [visual_stimulus]: G01 revision 157, V03 revision 12, V08 revision 5, root register: compact seeded random-access rules replace eager sample tables; Setup resolves settings after its plan-size check. Independent projector streams and explicit sharing kept; legacy tables load unchanged. GUI random authoring has no 2000 cap; source-list/expanded-preview bounds and Setup's 100,000 default remain. Order removed; Layer index-only 64 px; durations hh:mm:ss.
- Visual Stimulus 233 passes/one deselection; compiler 11; full GUI 396 passes/one obsolete label assertion, then 12 affected cases pass. Million-repeat regression shows near-constant JSON size. Ruff/format 171 files, Win32 mypy 168 sources, boundaries 659 modules/zero violations, 11 schema checks pass. [Evidence](reports/runtime-evidence-2026-10-12/compact-rules/context.json). No full-workload performance or native Windows/rig claim; image readiness pending.

## 2026-10-13 — Inline timeline actions started

- `inline-timeline-actions` [gui]: block-local hover/selection deletion and trailing additions replace toolbar Group/Epoch actions. ARCH-002 reuses structural transactions/history and visible-block painting; a focused helper owns button presentation with path signals to the editor. No repetition expansion or dependencies.

## 2026-10-13 — Inline timeline actions completed

- `inline-timeline-actions` completed [gui]: G01 revision 158, root register: trailing + controls and hover/selection × replace + Group, − Group, + Epoch buttons. Add appends and selects; subgroup delete removes all source members, with draft validation, authority, minimum-duration checks and Undo; last group/subgroup not deletable. No per-repetition widgets or backend change.
- Full GUI suite 398 passes; focused 31. Ruff/format 148 files, Win32 mypy 146 GUI sources, boundaries 660 modules/zero violations, links, whitespace pass. QWidget.actions name collision, button padding and a test fixture corrected. [Evidence](reports/runtime-evidence-2026-10-13/inline-actions/context.json). Native Windows/DPI/rig separate.

## 2026-10-13 — Variation rule simplification started

- `variation-rule-layout` [gui]: only Add variation rule (no Enable) and a Layer layout fix. ARCH-002 removes duplicated activation state from widgets, separates target/value layout sizing, reuses canonical drafts and parameter controls; legacy inactive drafts not activated on load.

## 2026-10-13 — Variation rule simplification completed

- `variation-rule-layout` completed [gui]: G01 revision 159, root register: Enable removed; Add always visible, existing rows define active rules; removing the last rule clears compact variations, Undo restores. Layer overlap fixed (Fixed size policy, 64 px reserved; prior Ignored policy let Parameter overlap). No schema/sampler change. Regressions cover All layers, Values/Sweep/Random, 1280/720, removal, Undo; captures show no overlap.
- Final 40 focused GUI tests pass; Ruff/format 148 files, Win32 mypy 146 sources, boundaries 660 modules/zero violations, links/whitespace pass. [Evidence](reports/runtime-evidence-2026-10-13/variation-layout/context.json). No new full-suite or native Windows/DPI/rig claim.

## 2026-10-13 — Trial list controls started

- `trial-list-inline-controls` [gui]: trial deletion onto hovered/selected rows, addition below the last row, taller Trials, aligned card borders/titles. ARCH-002 keeps QListWidget selection/model and the existing confirmation, using a focused list subclass for viewport controls, no sentinel trial or per-row widgets.

## 2026-10-13 — Trial list controls completed

- `trial-list-inline-controls` completed [gui]: G01 revision 160, root register: Trials/timeline cards at least 320 px with matched captions and top borders; hover/selected × on rows; scrolling + follows the last trial. Confirmation, saved-file preservation and final-trial blank replacement kept; hover deletion targets the clicked identity; invalid drafts/disabled authority guarded. ARCH-002: focused TrialList subclass, no per-trial widgets.
- Focused 12 pass (final interaction 1 after Qt typing cleanup); no new full-suite claim. Ruff/format 149 files, Win32 mypy 147 GUI sources, boundaries 661 modules/zero violations pass; links/whitespace checked. [Evidence](reports/runtime-evidence-2026-10-13/trial-list/context.json). Native Windows/DPI unverified.

## 2026-10-13 — Protocol card balance started

- `protocol-card-balance` [gui]: group fields into the timeline card, more even filling, hover-only remove controls matching MCU outputs. ARCH-002 reuses the compact button role instead of custom miniature styles; group binding/history retained while reparenting.

## 2026-10-13 — Protocol card balance completed

- `protocol-card-balance` completed [gui]: G01 revision 161, root register: selected group fields above timeline blocks balance the cards and shorten Sequence editor; existing form reparented, edits/history/condition-expansion sizing retained.
- Trial/group/subgroup/variation removal hover-only, reusing the MCU compact × role (custom 22 px overrides removed); subgroup header height fits controls; trial removal is one reusable hover button. No new style/dependency/runtime change.
- Final 53 focused GUI tests pass; Ruff/format 149 files, Win32 mypy 147 GUI sources, boundaries 661 modules/zero violations, links/whitespace pass. [Evidence](reports/runtime-evidence-2026-10-13/card-balance/context.json). No new full-suite or native Windows/DPI/rig claim.

## 2026-10-13 — Configuration layout polish started

- `configuration-layout-polish` [gui]: layout refinements reuse row controls, calibration actions and GUI file saving. Save pulse mapping is a separate controller inventory-write action; removing its button adds no automatic writes and leaves controller inventory ownership unchanged. ARCH-002: focused variation table presentation helper.

## 2026-10-13 — Configuration layout polish completed

- `configuration-layout-polish` completed [gui]: G01 revision 162, root register: trailing + heights match trial rows/epoch blocks; variation rules use shared Projectors/Layer/Parameter/Method/Values columns with horizontal scrolling on narrow windows (focused table helper, ARCH-002). SpikeGLX Save pulse mapping removed; GUI file Save/Load kept, no automatic controller writes. Screen/Pixel-to-mm calibration flattened into sibling cards with Launch projection calibration / Launch reference calibration above tables; Close lifecycle and locks preserved.
- Final 45 focused GUI tests pass; Ruff/format 150 files, Win32 mypy 148 sources, boundaries 662 modules/zero violations pass. [Evidence](reports/runtime-evidence-2026-10-13/layout-polish/context.json). Native Windows/DPI/rig unverified.

## 2026-10-13 — Rig verification started

- `rig-verification-20261013` [repo] [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx]: owner requests deferred checks on the rig. Clean baseline HEAD f4e6bc89a612e5f33fe5b5256281bd1650257e32; Python 3.11.15, managed interpreter and Windows atomics present. Starting automated Windows acceptance; requesting projector/remote readiness and missing Eye/electrical inputs. No acceptance inferred from presence. An initial combined tracking patch failed before applying; corrected separately.

## 2026-10-13 — Rig automated and inventory findings

- `rig-verification-20261013` [repo] [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx]: sandbox runner finds stale generated bindings (42 mypy errors/three collection errors), no CIM inspection, blocked package temp access. All 19 Protobuf inputs regenerated; unsandboxed runner passes static/contracts/schema/package steps but combined pytest exits 0xC0000005. Isolated backend/native suite passes 1520/five skips in 20.32 s, including the rig NVIDIA smoke. Isolated native GUI repeats the access violation at test_dashboard.py:94 teardown; offscreen regression in progress. No combined/native-GUI pass.
- Preflight: four projectors 60 Hz, both NVIDIA GPUs, SpikeGLX v20251218 api v4.1.3 at the saved endpoint, idle/not saving. PATH ffmpeg/ffprobe 4.3.2; no encoder feasibility established. Owner confirms devices clear and excludes all Eye checks; actual pulse mappings and electrical instrumentation requested. Raw evidence: reports/rig-evidence-2026-10-13.

## 2026-10-13 — Available rig verification reconciled

- `rig-verification-20261013` [repo] [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking] [spikeglx]: offscreen GUI 396 passed/three 15 px projector-scroll failures in 146.59 s; two native 0xC0000005 chooser-teardown failures retained. Windows static/contracts/schema/package and 1520 backend/native tests pass (five symlink-privilege skips). No summed or native-GUI approval.
- Four projector outputs pass startup Idle/RGB8/interval 1, V01 grid Open, live sequences 1/2, Close/Idle/resource closure (retained dummy geometry, all-output-VSync profile); historical mixed-pacing asset correctly rejected. Narrow/DPI unverified. COM8 Connect reports protocol 3/cephvr2_uno_2, camera outputs stopped. No firmware, remote recording or electrical tests.
- GUI Behavior Connect yields no usable frame by deadline and WORKER_OWNER_FAILURE; exact first exit/guard release passes. Owner defers further capture, all Eye checks, pulse mapping and electrical measurements. Installed FFmpeg/ffprobe 4.3.2 lacks required hybrid_fragmented MP4 support; recording/throughput blocked. Missing-display injection via UpdateConfiguration inconclusive (both display-result waits time out); final shutdown confirms exact absence/free guard/COM8 release and history equal to original; task-created diagnostic profile removed.
- Reports/TODO reconciled; the dated verification tracking item is superseded by existing rig-acceptance and GUI/encoder/device follow-ups; acceptance incomplete. Raw evidence: reports/rig-evidence-2026-10-13. Final: 1,003 hashed inputs unchanged; 608 links/anchors resolve; whitespace passes. Open: native chooser, projector overflow, compatible encoding, physical/scientific/full-load acceptance.

## 2026-10-13 — Runtime/Review layout parity started

- `runtime-review-layout-parity` [gui]: owner wants Runtime elements/layout to match Review before rig findings are addressed. G01 already selects shared DashboardWindow composition; Runtime-only control button/hint rows and parity-test exceptions found. ARCH-002: remove those rows, the signal and the forwarding method; Take/Take over/Release menu actions and controller/HUD gates retained. No new state/dependency/device operation; rig evidence preserved.

## 2026-10-13 — Runtime/Review layout parity completed

- `runtime-review-layout-parity` completed [gui]: G01 revision 163, root register: identical page/card geometry; Runtime authority actions stay in the Control menu, status in the HUD. 36 production lines removed; shared pages, configuration ownership and gates unchanged.
- Parity cases compare all controls/card geometry without Runtime exceptions (Protocol and all Devices subtabs, 1280/720, both authority modes). Final eight cases pass (389 deselected); Ruff/format 150 files, Win32 mypy 148 GUI sources, boundaries 663 modules/zero violations, whitespace pass (sandbox stage four passes/four temp-fixture errors). No full-GUI/native/device acceptance; rig findings and deferrals open. Evidence: reports/runtime-evidence-2026-10-13/runtime-review-parity-context.json.

## 2026-10-13 — Native configuration chooser diagnosis started

- `native-configuration-chooser-teardown` [gui]: owner authorizes diagnosis/fix; reproduce the five authority-loss picker cases natively first. G01/E03 require nonmodal pickers, stale-result fencing and closure on authority loss; start from the ConfigurationFiles owner and existing tests, no new dependencies. Prior Runtime parity edits, rig evidence and emergency output preserved.

## 2026-10-13 — Native picker cause and repair

- `native-configuration-chooser-teardown` [gui]: five native cases reproduce 0xC0000005, also reproduced by a tiny standalone ConfigurationFiles/window process. Qt 6.11.2 source schedules native modal-open on a zero-delay timer that hide does not stop; no C++ instruction-pointer dump claimed. A delayed probe exits zero but emits 28 access-violation notices (rejected). Child-first forced destruction and Qt widget dialogs each pass 20 cycles with no notices.
- ARCH-002 selects one file-dialog factory using the existing DontUseNativeDialog option, reused by five asynchronous owners (configuration, projector files, paths/PFS, prepared assets, stimulus media); immediate rejection, filters, stale-result fencing, deleteLater kept; no global setting/dependency/sleeps. G01 revision 164, root register. Ten real-Windows Load/Save authority-loss cases pass; original sequence completes 50 cycles. Full native GUI regression running; final media-picker adoption needs final-tree coverage.

## 2026-10-13 — Native chooser crash repaired and verified

- `native-configuration-chooser-teardown` completed [gui]: one Qt-widget picker factory for all five owners under G01 revision 164/E03. Original sequence passes 50 cycles with no access-violation notices; ten Load/Save authority-loss cases pass and stale callbacks cannot mutate draft/file. No C++ dump or upstream Qt patch claimed.
- Broad real-Windows GUI stage 401 passed/two native Protocol hover-control lookup failures in 186.89 s (predates final media-picker refinement); final affected selection 20/382 deselected in 16.56 s. The two hover cases repeat in fresh processes with zero QFileDialog constructions; recorded as separate native-test findings, production behavior unconfirmed; native hover investigation queued. No full/final-tree/native-UI acceptance.
- Ruff/format 151 files, Win32 mypy 149 GUI sources, boundaries 664 modules/zero violations pass. Projector-overflow/encoder findings and hardware deferrals preserved. Evidence: reports/runtime-evidence-2026-10-13/native-chooser/context.json. No hardware or managed-runtime launch.

## 2026-10-13 - Settings warning investigation

- `runtime-settings-warning-diagnosis` [gui] [controller]: owner reports startup/closure warnings without exact text. Traced E07 history load/save, managed-close/bridge failures, review/preferences paths. Controller loader returns no history warning, offscreen review-draft restore succeeds, registry read reports NoError. No reproduction; cause pending warning detail/running revision. Existing edits and scientific settings preserved. apply_patch could not decode TODO encoding (no edits); byte-preserving inserts used.
- Doc checks pass: links/anchors resolve, whitespace clean. A CP1252 write into the new TODO line was normalized to UTF-8. No task-owned native test/probe left running.
- Correction for `native-configuration-chooser-teardown` [gui]: the UTF-8 repair doubled CRLF line endings and failed whitespace; byte-level LF normalization fixes it, concurrent settings-warning task/log preserved, final whitespace passes, recorded input hashes still match.

## 2026-10-13 - Startup GPU failure identified

- `renderer-startup-gpu-selection` [visual_stimulus] [launcher] [gui]: owner reports a GPU error then GUI closure. Two emergency reports (09:21/09:35) show AMD Radeon OpenGL contexts rejected by the exact RTX 5060 Ti check under SYS-002; renderer failure triggers managed runtime closure. UserGpuPreferences already has GpuPreference=2 for cephvr-python.exe; an earlier four-output startup passed, so selection varies between launches; underlying cause unresolved. Diagnosis queued; parallel settings-warning investigation and hardware deferrals preserved. No source/driver/preference/device change or relaunch; documentation whitespace passes.

## 2026-10-13 - Runtime GUI retention started

- `runtime-settings-warning-diagnosis` [gui] [controller]: owner requests retaining the closed GUI configuration and identical values on reopening. G01 revision165/E07 revision60: complete local GUI draft separate from accepted controller history; reuse GuiSnapshot validators and atomic QSaveFile, no new schema/dependency/controller draft owner. Remove obsolete close-time submission/discard code.
- Initial tests expose reentrant Qt close suppression and informational SpikeGLX host provenance; fix outer close-event acceptance. A Python default-encoding edit caused mojibake; restore exact UTF-8. No operator/scientific values or hardware changed.

## 2026-10-13 - GPU startup repair implemented

- `renderer-startup-gpu-selection` [visual_stimulus] [launcher] [gui]: ARCH-002 review selects the existing sessionless display rejection/cleanup/report path; no GPU fallback, process, dependency or retry state. An identical executable without a Windows graphics preference reproduces AMD contexts on all four projectors; the configured managed image and fresh managed launch use RTX 5060 Ti. Original reported launch route remains unknown.
- Type a live OpenGL adapter mismatch separately from CUDA failures and convert it to an unavailable-output rejection with an executable-specific remedy. V19 revision6 and startup contract clarify this case; genuine GPU faults and unsafe cleanup still escalate. 73 platform/rendering/lifecycle/authenticated controller cases pass. Native final verification in progress. No production Windows preference, driver or scientific setting changed.

## 2026-10-13 - Runtime GUI retention completed

- `runtime-settings-warning-diagnosis` completed [gui] [controller]: G01 revision165/E07 revision60 retain the complete editable runtime GUI snapshot in config/runtime_gui.json (existing validators, atomic QSaveFile, read-back equality before normal closure). Restore once after initial inventory/base installation; local edits go through normal controller validation and survive polling/delayed SpikeGLX replies. Disconnected closure or rejected controller history cannot discard the draft. Obsolete close-time code removed. Forced termination is outside the guarantee; original warning detail remains unobserved.
- Native Windows selection passes 27/374 deselected in 18.27s; offscreen selection 106 pass with two pre-existing 15px projector-overflow failures/293 deselected in 51.18s. Sandbox runs stall in asyncio fallback_socketpair accept; permitted reruns unchanged. Ruff check/format 152 files, Win32 mypy 150 sources, boundaries 665 modules/zero violations, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-13/settings-retention-context.json).
- Documentation check: 545 local links/anchors, zero errors; git diff --check passes. Three task-created .tmp-settings test directories removed. Concurrent GPU diagnosis remains open.

## 2026-10-13 - GPU startup closure repair verified

- `renderer-startup-gpu-selection` [visual_stimulus] [launcher] [gui]: V19 revision6 closure repair passes 249 Visual Stimulus/platform cases, Ruff/format 154 files, Win32 mypy 137 sources, boundaries 665/zero violations. Three isolated AMD contexts reject and release owned resources exactly. Fresh managed GUI launch: four RGB8/interval1 outputs initialized at revision1, Configuration, no warnings/errors, RTX 5060 Ti check passed; earlier baseline launch also succeeds. No registry/driver change, no camera/recording tests. Evidence: reports/runtime-evidence-2026-10-13/gpu-selection.
- Task stays in Next for the unknown original launch route; the no-preference diagnostic image reproduces AMD but does not prove why the original image failed. Diagnostic executable removed after probes; final runtime left available to owner.

## 2026-10-13 - Controller-exit ownership investigation started

- `controller-exit-descendant-cleanup` [controller] [supervisor] [launcher] [visual_stimulus]: owner requests calibration screens/owned children close when controller Python exits. E08 already requires automatic full shutdown, exact OS process monitoring and launcher kill-on-close containment. Live inspection finds controller 27476, supervisor 23512, renderer 24404 alive; snapshot reports Configuration, four Idle outputs, no Acquisition/Tracking work. Initial probe used a nonexistent display field (corrected to visual_stimulus_display); temporary CLI credentials removed. No process stopped.

## 2026-10-13 - Exact controller-exit cleanup verified

- `controller-exit-descendant-cleanup` completed [controller] [supervisor] [launcher] [visual_stimulus] [gui]: E08's existing monitoring and shutdown satisfy the request; the controller had stayed alive after GUI closure. After a Configuration preflight, terminating only controller 27476 makes all six owned identities exit, with outer-Job absence receipt at 3.453s. No managed executable remains; no relaunch, camera/recording changes. Absence is not recording finalization or paired SpikeGLX stop proof. No production source or architecture change.
- Launcher/supervisor/native tests pass 95/one Windows symlink-privilege skip in 7.63s. Runtime report and rig-verification updated; active/full-load/paired fault checks and deferrals retained. [Evidence](reports/runtime-evidence-2026-10-13/controller-exit/context.json). Docs check 432 links/anchors, zero errors; git diff --check passes.

## 2026-10-13 - Numeric MCU pin display started

- `numeric-mcu-pin-display` [gui] [controller]: owner requests pin-connection testing, asks whether reassignment needs flashing, and requests removing D next to pin numbers. Firmware protocol3 parses dynamic CONFIGURE/TEST_START pins; reassignment needs no flash. Physical target/receiving source unspecified; requested without starting camera or electrical work. G01 revision166 reuses canonical A11/E14 tokens at submission; ARCH-002 extracts a focused numeric display/token helper. Extend dashboard tests; preserve hardware deferrals.

## 2026-10-13 - Numeric pins completed and Trial state tested

- `numeric-mcu-pin-display` completed [gui] [controller]: G01 revision166 shows number-only pin editors and retains canonical firmware tokens in snapshots/requests; legacy D-prefixed files restore as numbers. Native GUI checks pass 29/373 deselected in 20.09s; Ruff check/format 153 files, Win32 mypy 151 sources, boundaries 666/zero violations, TOML loader, whitespace pass. [Evidence](reports/runtime-evidence-2026-10-13/pin-numbers-context.json).
- `trial-state-pin12-test` [controller] [gui] [acquisition] [spikeglx]: owner selects Trial state output only, corrects pin 9 to 12; default changed to D12, saved history reloads D12. COM8 verifies protocol3/cephvr2_uno_2. First 2s pin12 test is rejected (probe misused STATUS with a signal), preserved; corrected repeat shows one rising transition and exact absence receipt. No pin9 output, flash, capture or remote command. Owner reception observation pending. [Methods and results](reports/runtime-evidence-2026-10-13/pin-test/context.json).

## 2026-10-13 - Manual GUI pin testing clarified and prepared

- `trial-state-pin12-test` superseded by owner-controlled manual GUI testing [gui] [controller] [acquisition] [spikeglx]: owner wants to press Test themselves; agent-triggered pulses are not that interaction or receiver evidence. Automatic test commands stopped; pin12 stays confirmed. Runtime reopened, inspected read-only (GUI 24284, Configuration, COM8/D12 enabled, no diagnostic); left available.
- Owning test now clicks Test connection and the Trial state Test button (displayed 12/confirmed D12), stale-assignment rejection retained; passes 1/401 deselected in 2.98s, no electrical output. Manual voltage/timing/SpikeGLX acceptance stays in the rig worklist. Final: Ruff check/format 153 files, Win32 mypy 151 sources, 699 links/anchors, git diff --check pass; boundaries 666/zero violations. No lease claimed, no MCU commands.

## 2026-10-13 - Disabled runtime controls repaired and runtime closed

- `runtime-disabled-device-controls` completed [gui] [controller] [launcher]: live revision4 projection reproduced `Only groups contain epochs`, false configuration wiring, disabled COM/files and enabled Test connection. Reset protocol group scope/selection on authoritative schedule replacement; apply MCU authority/diagnostic gate to the COM-row parent. G01/E03 locks intact. Same snapshot now enables COM selector/refresh and MCU/full GUI files.
- Five focused offscreen Windows tests pass/397 deselected in 3.60s; Ruff 3 files, Win32 mypy 151 sources, boundaries 666/zero violations, whitespace pass. No pin tests, firmware, capture or SpikeGLX commands. Runtime closed via accepted-history save and ShutdownApplication; generation f17215ba-41c0-42e1-baeb-4c30d5ccf2b8 receipt confirms all owned processes absent. Unsent old-GUI edits not claimed saved. [Assessment/evidence](reports/runtime.md).

## 2026-10-13 - Add output limit explained

- [gui] Owner asks why another output cannot be added. Source review of MicrocontrollerSignals.supported/refresh/add: only Trial state and assigned Behavior/Tracking camera trigger outputs are supported, once each; all three were already present. Existing signal inventory, not a wiring defect or exhausted Arduino pins. No change, hardware command or test; extending needs the owner's intended signal/function.

## 2026-10-13 - Remaining failures reviewed

- [gui] [acquisition] [visual_stimulus] [supervisor]: owner asks for remaining failures. Read TODO/reports: FFmpeg 4.3.2 incompatibility, Behavior no-frame Connect deadline, historical 19.7fps stimulus result, native Protocol hover-test failures and offscreen projector overflow are pending/deferred, distinct from repaired items. Screenshot's interruption-report IDENTITY rejection during the earlier GPU failure has no independent post-repair closure claim. Eye output/protocol4 work in progress separately. Recommend compatible encoder toolchain next. No hardware operation or source change.

## 2026-10-13 - FFmpeg compatibility repair started

- `encoder-toolchain-owner-review` [acquisition] [visual_stimulus] [shared]: owner authorizes FFmpeg repair and supplies an H.264 NVENC/Matroska reference. Read A08/E13/E14, camera settings, validators. Runtime resolves PATH tools; 4.3.2 lacks hybrid_fragmented. Preserve accepted MP4 lifecycle and ownership. Saved Behavior BayerRG8/1760x3000/~30Hz; Tracking Mono8/1588x1344/60Hz; Eye unset/disabled; all lists p4/CQ18/yuv444p/lookahead0. No silent CQ33/chroma reduction or reference size/rate. No camera opened.

## 2026-10-13 - FFmpeg compatibility repair completed

- `encoder-toolchain-owner-review` completed [acquisition] [visual_stimulus] [shared]: install checksum-verified Gyan 9.0.2 FFmpeg/ffprobe pair into the existing PATH bin (4.3.2 directory name retained); old executables and hashes preserved in C:/Dev/software/ffmpeg-backup-20261013. No PATH, runtime code, saved encoding or scientific change; no camera opened. Lookup/hash/version checks and MP4 flags pass. RTX 2080 Ti resolves to ordinal 1; H264 8-bit 444/420 and HEVC 10-bit available, AV1 absent.
- Existing validators accept saved camera lists and the p3/CQ33/lookahead4/surfaces16/capped VBR proposals. Five synthetic eight-frame encodes verify count/dimensions, H264 profile, full-range chroma and identity tags; synthetic only. Does not establish camera conversion, footage quality, sustained throughput, crash recovery or simultaneous GPU placement. Reference HTML used as tuning reference only (reports/runtime-evidence-2026-10-13/ffmpeg/context.json). Reports/rig tasks drop only the tool-incompatibility blocker.
- Verification: git diff --check passes, FFmpeg evidence links resolve; broad 589-link check sees the concurrent Eye context file not yet present (left alone). Active hashes match tested binaries; backups retain 4.3.2 bytes.

## 2026-10-13 - Independent Eye MCU output implemented

- `eye-mcu-trigger-output` completed [gui] [controller] [acquisition]: owner selects an independent third Arduino output, upload manual. G01 revision167/A01 revision18/A11 revision44 replace the deferral with external source/pin/rate requirements and protocol4; E14 Microcontroller pair to policy 2; three proto sources regenerated via the 19-source generator. ARCH-002: reuse existing owners, one timer scheduler, no new process/dependency.
- GUI Eye Add/remove, numeric pins, persistence and Test forwarding wired; unset camera pin collected via nonblocking dialog and submitted atomically under the configuration dispatch lock; no pin/rate/device defaults inferred. Setup/preview/readback, grouped boundaries, reservation, terminal evidence and all-output stop include Eye; old protocol3 rejects before diagnostics. Firmware validates all three pins before mutation. Uno compile 13,922 flash bytes/1,214 SRAM bytes.
- Controller/acquisition regressions pass 834 (3 privilege skips/2 native deselections); readiness subset 97; Eye GUI selection 38/369 deselected in 18.12s. Ruff 494 files, Win32 mypy 440 sources, boundaries 666/zero violations, 839 links/anchors pass. Firmware not uploaded; no COM, pin, camera or SpikeGLX command; no native GUI acceptance. Manual upload and electrical/timing/three-camera checks stay in rig checklist. [Assessment](reports/runtime.md).

## 2026-10-13 - Tab configuration file verification completed

- `tab-configuration-files-verification` completed [gui]: G01/E03/E07 source review finds all six tab formats and full-GUI composition already implemented. Extended owning file tests with actual button/dialog Save/Load into fresh matching-inventory windows and Camera chooser authority-loss coverage (three synthetic cameras incl. Eye; MCU/full files retain Eye pin8 and Projector flip pin2). Loading emits no device/firmware requests; no production change.
- Initial selection passes 19/397 deselected in 13.02s; broader selection 54/362 deselected in 29.14s. Ruff on test module, boundaries 666/zero violations, whitespace pass. Real desktop chooser inspection and hardware remain separate. [Assessment](reports/runtime.md).

## 2026-10-13 - Normal Windows GUI file browsers restored

- `native-explorer-file-browsers` completed [gui]: owner requests normal Explorer windows. G01 revision168: shared native nonmodal opener replaces Qt widget workaround; pickers keep validation, authority cancellation, stale-result fences. ARCH-002: no dependency; extend owning tests.
- Native tests pass 21/399 deselected in 22.18s incl. 40 rapid Open/Save cancellation cycles and 12 authority-loss cases. COM 0x8001010d notices in raw log; process exits 0; visual/DPI acceptance not claimed. Ruff 153 files, Win32 mypy 151 sources, boundaries 666/zero violations pass. No managed restart/device operation. (Superseded by the correction entry below.)

## 2026-10-13 - Restored Eye camera/output selection repaired

- `eye-output-selection-runtime` completed [gui]: read-only snapshot plus native GUI inspection confirms a saved third-camera Unassigned draft; an owner role command completes while projection retains Unassigned, hiding Eye output. G01 revision169: loaded role/participation/pin edits stay local until submission; inventory/output choices update together. Select Tracking by exact role. Un-restored confirmed paths and SDK PFS import preserved.
- Restored-draft regression: focused 5 pass/416 deselected; broader 94 pass/one known projector horizontal overflow failure/326 deselected. Ruff 6 files, Win32 mypy 151 sources, boundaries 666/zero violations, git diff --check pass. No restart, firmware, camera/pin/SpikeGLX commands or live post-restart acceptance. [Evidence](reports/runtime.md).

## 2026-10-13 - Correction: actual native Explorer pickers verified

- `native-explorer-file-browsers` completed [gui]: owner screenshot disproves the earlier claim; Qt's Windows helper refuses nonmodal operation, so revision168 used widget fallback and the earlier 21 passes are widget evidence. Report corrected; G01 revision170 uses a dialog-owned zero-delay timer for native modal exec, preserving owner/path validation and authority cancellation. No new dependency.
- Native shell Open/Save/folder controls verified; 23 regressions pass/400 deselected in 16.43s incl. 40 rapid cycles and authority cancellation. Default pytest faulthandler cases fast-fail 0xC0000409 while plugin-disabled and standalone probes pass; this unverified exception-hook finding stays open in TODO, ordinary native suite acceptance not claimed. Focused Ruff/mypy pass; broad checks hit concurrent camera/controller-bridge edits. Boundaries 666/zero violations. No visual/DPI acceptance.

## 2026-10-13 - Camera Test/Connect submits current parameters

- `camera-action-submit` completed [gui]: owner replaces Setup-dependent draft submission with submission on selected-camera Test/Connect. G01 revision171: capture assignment/timing/PFS/rate/pin against exact generation/base, serialize assignment/settings/SDK import and Finish editing, then continue the action only after success. Changed assignment forces PFS reimport; Disconnect unchanged.
- Confirmed camera revisions adopted without discarding other drafts. ARCH-002 extracts the sequence into camera_action_submission; no dependency/process. Regression 87 pass/347 deselected in 29.17s; focused 12 pass/422 deselected in 1.53s. Ruff 153 files, Win32 mypy 152 sources, boundaries 667/zero violations pass. Fake controller/SDK evidence only; no live Test/Connect, restart, MCU or SpikeGLX. [Assessment](reports/runtime.md).

## 2026-10-13 - Per-camera encoder recommendations validated

- [acquisition] [visual_stimulus] [shared]: owner asks for best args with rationale, not application. Saved settings (not fresh readback): Behavior BayerRG8/1760x3000/~30Hz, Tracking Mono8/1588x1344/60Hz, Eye BayerRG8/1920x1200/100Hz disabled. Recommend CQ18, p3, lookahead0, surfaces0; full-range 444/high444p for Bayer cameras, 420/main for Mono8 Tracking; no maxrate/bufsize. All three lists pass the production validator against recorded 9.0.2/RTX 2080 Ti capabilities. No capture, encode, restart or settings write.
- Proposals preserved in reports/runtime-evidence-2026-10-13/ffmpeg/recommendations.json; not accepted defaults; CQ18 not claimed lossless. Quality, size, latency and throughput remain empirical; native Eye checks deferred.

## 2026-10-13 - Internal camera clock omits inactive trigger edge

- `camera-internal-trigger-activation` completed [gui]: owner reports prepare_camera rejection of rising_edge. Saved Eye PFS has FrameStart Off/Software. G01 revision172: camera-settings and loaded-proposal collectors clear external TriggerActivation with TriggerSource when Internal clock is selected; explicit External edge choices and strict adapter rejection preserved; no rename, PFS/default/history edit.
- Regression incl. the exact rejection, Test/Connect ordering and falling-edge preservation: 13 GUI cases pass/425 deselected in 2.71s; adapter contracts 40 pass in 0.15s. Ruff 153 files, Win32 mypy 152 sources, boundaries 667/zero violations pass. No camera opened, no SDK capability read; physical post-fix acceptance pending. [Assessment](reports/runtime.md).

## 2026-10-13 - Current calibration snapshot exports successfully

- `calibration-export-version-four` completed [gui]: owner reports version 2/3 rejection loading Desktop rig_cal.json. Reproduced version 3 migration to calibration4/wrapper7; geometry export now accepts current 4 with exact integer validation, unsupported-version and geometry checks kept. Implements G01/V15 ownership; no schema/architecture change.
- Version 2/3/4 regressions 8 pass/434 deselected in 2.82s. Actual owner-file load exports a bundle; GLB parser confirms four screen planes/one node (synthetic identities, evidence only). Input hash unchanged. Ruff 2 files, Win32 mypy exporter, boundaries 667/zero violations pass. No restart, device/display command or optical/native calibration acceptance. [Assessment](reports/runtime.md).

## 2026-10-13 - Requested rig workflow failure inventory

- `rig-workflow-failure-inventory` completed [gui] [controller] [supervisor] [acquisition] [visual_stimulus]: owner authorizes fresh camera/calibration/stimulus/protocol tests, fixes deferred. Behavior 40065509/Tracking 40747103 identity, previews and Stop/release pass; earlier no-frame failure does not reproduce. Normal calibration profile fails mixed-pacing validation; all-output-VSync profile passes.
- Combined Setup fails before activation (camera drain margins unset). CancelSetup cannot confirm cleanup; renderer exits on `cleanup command unknown`, causing full shutdown with exact Job absence. Administrative recovery preserves the session report; missing SESSION_CONFIG gives an unknown-SpikeGLX-stop warning. Unpaired open-loop 60s stimulus trial completes: 3600 frames decode; 1820 real render groups/30.33fps, 1805 captures, 1795 duplicates, 15 capacity drops; median group 32.18ms vs swaps 2.42ms does not support the sequential-swap hypothesis.
- Component checks 213 pass; GUI/offscreen 62 pass/380 deselected. 10s protocol rejected by E05 minimum 60s. Final Shutdown succeeds, but acquisition finalizer's MCU Close emits an UNAVAILABLE traceback (separate task). No production fixes, firmware, or paired/Tracking/full-load acceptance. Evidence: reports/rig-evidence-2026-10-13/workflow-tests/.

## 2026-10-13 - Current renderer AMD mismatch confirmed

- `renderer-startup-gpu-selection` [visual_stimulus] [launcher]: screenshot shows retained-events popup. Read-only GetSnapshot confirms generation 10dc50d5-98da-463f-9bb9-02516f041026 and InitializeDisplay e9933d53-eec0-4ec9-afa2-e04f8a1e3532 failed AMD-context resolution; resources released. Managed cephvr-python.exe children in the VS Code start_runtime_gui.py route; its Windows preference already has GpuPreference=2, not adapter proof. No repaired outcome claimed; earlier RTX passes historical. No GUI input, setting change, restart or source edit.

## 2026-10-13 - GPU rendering/encoding placement configured and verified

- `renderer-startup-gpu-selection` completed [visual_stimulus] [launcher] [acquisition]: owner authorizes computer use. NVIDIA Control Panel entry for .venv/Scripts/cephvr-python.exe now selects RTX 5060 Ti for OpenGL (Apply/readback confirmed); CUDA GPUs remain All. Implements SYS-002/V19/A08; no code/dependency/architecture change.
- CUDA enumeration: ordinal0 RTX 5060 Ti, ordinal1 RTX 2080 Ti. ModernGLPort initializes all four contexts on RTX 5060 Ti; NVENC and camera argv verify RTX 2080 Ti/-gpu1 for Behavior 1760x3000, Tracking 1588x1344, Eye 1920x1200 (generated inputs, four-frame probes; no cameras opened, no quality/throughput inference).
- Owner's start_runtime_gui.py route then initializes four Idle outputs without issues in generation c3532451-334e-4874-beaa-3e181be7bc2d; left open. Evidence in gpu-placement/context.json; no pytest/static suite as production code unchanged.

## 2026-10-13 - Stimulus throughput measurement and capture repair

- `stimulus-throughput-repair` in progress [visual_stimulus]: owner authorizes coding/rig work. ARCH-002: two focused changes in the capture owner; no pacing, timing, slot or ownership change under V12/V20/E13. Save On trial: 1808 groups/60s (30.13/s); glReadPixels 12.98ms, polling 6.54ms, draw 4.79ms point to the float32 review readback. Save Off: 3602 groups (60.03/s), but cleanup fails with an unregistered resource after prior Save On (pre-change defect, separate).
- Use RGBA8 for 8-bit review (float32 kept for packed 10-bit); fill a bytearray via ctypes. Tests 29, then owning suite 244 pass; Ruff 152 files, Win32 mypy 136 sources, boundaries 667/zero violations. First optimized recording: 50.42 groups/s, 2988 captures/612 duplicates/nine drops; 3600 frames decode; stage costs unmeasured. Native 768-pixel comparison: max one 8-bit code difference (not bit-exact). Final recorded measurement in progress.
- Diagnostic corrections: injector ctypes import order; an early accidental shutdown run retained as Interrupted, not performance proof. Raw runs in runtime-evidence-2026-10-13/throughput/.

## 2026-10-13 - Stimulus throughput repair verified and completed

- `stimulus-throughput-repair` completed [visual_stimulus]: final instrumented and normal 60s recorded trials each render 3600 groups (60.0/s) vs baseline 1808/30.13/s (audit 1820/30.33/s). Readback 12.98 to 0.736ms; polling 6.54 to 3.40ms. Normal run: 3423 captures/177 padding duplicates/eight capacity drops/169 same-slot omissions, not hidden by 60fps video. Outputs close, metadata syncs, FFprobe 3600 frames/60s, full decode and recipe digest pass.
- 768-pixel comparison keeps max one 8-bit rounding difference (review-only; not bit-exact). Physical precision, 10-bit path, VSync, frame identity, owner copy/bounds and deadlines preserved. Owning suite 244 pass; Ruff 152 files, Win32 mypy 136 sources, boundaries 667/zero violations. No architecture/dependency change.
- Final generation 8f0e0aaa-99cb-4d54-b64a-824db35744a1 is Configuration, original settings, history equal. Save On to Save Off cleanup remains a separate pre-change task; combined camera/Tracking/paired/optical acceptance and review omissions open. Evidence: throughput/context.json.
- Refs: E13, V12, V20

## 2026-10-13 - Combined real recording preparation

- `camera-recording-drain-allowances` in progress [acquisition] [visual_stimulus]: owner authorizes simultaneous real-camera recording/stimulus (60fps/GPU0, NVENC/GPU1). Generation 8f0e0aaa/revision3 Configuration baseline preserved; Behavior 40065509 at 30Hz/25ms, Tracking 40747103 at 60Hz/5ms, Eye disabled. File policy loader confirms both drain allowances absent; A10 requires exposure + transfer/SDK + one period; prior Setup fails on these. Critical values asked, not guessed.
- ARCH-002: reuse 60s diagnostic ops and GPU sampling; guarded script checks margins before mutation. Syntax check passes; no Setup/Start or device command. Owner response pending; no combined 60fps/encoding result claimed.

## 2026-10-13 - Real-camera drain timing measured; allowances proposed

- `camera-recording-drain-allowances` [acquisition] [visual_stimulus] [controller] [launcher]: owner selects measurement/proposal before applying. Diagnostic-only wrappers under ARCH-002/A10/E08 (no production change). Three 2s post-OFF/AcquisitionStop observations per camera across two generations: exposures 25/5ms, MCU 30/60Hz; max ON-to-first-SDK 67.4401/23.426ms; plus one period 100.7734/40.0927ms supports proposed 125ms Behavior/50ms Tracking. Four Behavior tail frames, latest 36.0479ms after OFF ACK; Tracking none. Limited-load; no guaranteed maximum. File values unset; approval pending.
- Initial wrapper hit RingError (corrected to direct SDK retrieval). Repeated previews return MCU pending/unavailable then command-record byte exhaustion; 12-cycle plan curtailed, separate reuse task added, cause unverified. Orphan-only cleanup approved after exact receipts. Final generation 7ed9d374-aa03-492f-b9d8-80d51e3b788c Configuration, config equals baseline, cameras released. Reports/TODO reconciled; combined test awaits approval.

## 2026-10-13 - All camera allowances applied and combined recording tested

- `camera-recording-drain-allowances` completed [acquisition] [visual_stimulus] [controller] [gui] [launcher]: owner selects 125ms for all cameras (supersedes 125/50). Only operator TOML fields set under A10/E14; loader resolves 125000000ns each; Eye and scientific/PFS/encoder values untouched. Configuration tests 17 pass; Ruff, boundaries 667/zero violations, TOML/loader, whitespace pass.
- Real 60s combined recording completes with closure and unlock. GPU/PID samples: renderer 26516 on RTX 5060 Ti/GPU0; camera NVENC 29320/28416 plus stimulus 300 on RTX 2080 Ti/GPU1. Behavior/Tracking 1797/3596 valid frames, queue drops 7/16, SDK failed/missed 0; FFprobe/decode pass: camera 1800/3600 frames (10/20 duplicates), stimulus 3600 (1287 duplicates, 2313 captures/37 capacity drops/18 same-slot omissions). Actual 2368 groups/60s (39.47/s) FAILS requested 60fps.
- Stage-timer repeat: 2295 groups (38.25/s); 9% GPU0/60% GPU1 samples are not a root cause. No tuning. Both sessions shut down during NewSession/restore on warning producer/scope/revision mismatch (separate reuse remedy and cadence work open). Final generation 6b8d9b8e-bb7d-42de-84ee-423bc81e1b3e Configuration, settings equal. Evidence: combined-camera-stimulus/context.json; no Eye/locomotion/SpikeGLX/optical/electrical acceptance.

## 2026-10-13 - Combined performance/reset repair authorized; first increment

- `gui-backend-dummy-experiment`/`combined-session-reset-warning` in progress [visual_stimulus] [acquisition] [controller]: owner requests both repairs and real 60fps while recording. ARCH-002: reuse capture owner and NumPy. Replace Python row-swap/X-bit loops with in-place NumPy half-frame swap and vector mask (bytes, identity, owner copy, deadlines and precision preserved under V12/E13; temp memory bounded by half a frame). Recording tests 36 pass. GIL contention remains a hypothesis; reset diagnosis underway, no validation weakened.

## 2026-10-13 - Runtime Protocol group/subgroup controls repaired

- `runtime-protocol-group-controls` completed [gui]: flat controller/saved schedules bypassed grouped controls. G01 revision173 presents them through one listed group; untouched submission/export keeps source, edits keep groups, Undo restores. Grouped/mixed/nested and canonical imports unchanged. ARCH-002: reuse trial record/group helper and dashboard test.
- Offscreen selection passes 50; Ruff 154 files, Win32 mypy 152 sources, boundaries 667/zero violations, whitespace pass. Default temp dir failed one fixture (repo-local basetemp fixed). Evidence: reports/runtime-evidence-2026-10-13/protocol-group-controls*. Native acceptance and hover failures separate; running GUI needs reopening.

## 2026-10-13 - Reset delivery ordering repaired; combined rendering improved

- `combined-session-reset-warning` [acquisition] [controller]: post-stop TRANSPORT_COUNTERS_UNAVAILABLE view revision5 arrives after NewSession/restore empties scope/revision3. Strict validation kept; flush coalesced warnings before Finished and serialize Warning/Finished delivery on the bounded dispatcher with original timeout. A07 revision61 and diagnostics contract clarify. Tests pass; three real NewSession/restore generations stay alive, settings/release verify.
- `gui-backend-dummy-experiment` [visual_stimulus]: native row swap improves ~39.47 to 54fps. 1ms switch-quantum, NumPy staging and PyOpenGL accelerator (52.57fps) experiments do not reach 60 and are removed; wheel uninstalled, pyproject restored. JSON serialization 0.010 to 0.006ms, no rewrite.
- Next changes: map signalled PBO, copy into owned bytearray, unmap at once; skip redundant GLFW rebind on native-pointer equality. Combined run 3385 groups/60s (56.42fps), closure/reset succeed, below 60. Owner tests 247 pass/one excluded; acquisition/render/controller suite 683 pass. Final validation/repeat in progress; no 60fps claim.

## 2026-10-13 - Combined cadence reaches nominal60; early boundary wake diagnosed

- `gui-backend-dummy-experiment` [visual_stimulus] [acquisition] [shared]: recorder normalization moved outside admission lock; native pipe copies writable frames with ctypes.memmove (GIL released, private buffer kept). Lock regression 38 and pipe 12 pass. Combined trial 3599 groups/60s (59.9833/s), closure/NewSession/restore ok, GPU0 renderer/GPU1 three NVENC. Review: 1031 admissions/2554 capacity drops/14 same-slot omissions; cadence is not review zero-loss. Repeated session still fails.
- `combined-session-reset-warning` [acquisition] [controller] [shared]: terminal MCU evidence retries compare the MCU payload after exact validation; canceled pre-capture schedule retains trial-scoped health until cleanup proven (E08). Authenticated owning suite 16 pass; recording 38 pass; unprivileged run blocked at hard-link/loopback.
- First-activity probe within 100ms (57.75fps before pipe change). NVIDIA Threaded optimization Off experiment causes start failures; restored Use global (Auto). A premature diagnostic mutation fixed by waiting for display initialization.
- Rejected trace: scheduled OFF issued Stop 3.38ms before end; asyncio wake is no absolute-boundary guarantee on Windows. Early ON explains intermittent start interruption. ARCH-002: shared deadline owner with async absolute-clock recheck for acquisition ON/OFF/end and controller waits (E05/E11); boundaries/allowances unchanged. Early-wake plus 78 owning tests pass; final repeat and static validation underway.

## 2026-10-13 - Final combined rendering and repeated reset verified

- `combined-session-reset-warning` completed; combined part of `gui-backend-dummy-experiment` completed [acquisition] [visual_stimulus] [controller] [supervisor] [gui] [shared]: two consecutive 60s sessions in 449c9382-c65d-4ed8-ae4e-393490ce9085 render 3602/3601 groups (60.0333/60.0167/s), Behavior 30Hz/Tracking 60Hz. PID/GPU UUID/NVENC samples: renderer 23560/GPU0 RTX 5060 Ti; cameras and review GPU1 RTX 2080 Ti. Six videos 1800/3600/3600 frames decode; closure, NewSession/restore and settings pass. Nominal host cadence, not uniform frame time: median 16.79ms/p99 27.56ms/max 37.88ms.
- Old unknown-resource cleanup reproduced with Save On to On; ARCH-002 scopes receipt history at new preparation after ownership closes. 59 resource/lifecycle tests pass; budget covers row scratch and pipe copy. Two final On to On sessions prove repair; dedicated Save On to Off native verification remains Next.
- Regression 1123 pass (3 skips/6 deselections); pipe transfer 14 pass; Ruff 364/138 files, Win32 mypy 427 sources, boundaries 667/zero violations. Evidence in combined-camera-stimulus; patch includes earlier shared edits.
- Limits: cameras 1797/3596 valid frames, SDK failed/missed 0; queue drops 9/28 then 6/19; review 1176 samples/2367 capacity drops/58 same-slot omissions/2424 duplicates; no zero-loss claim. Eye/locomotion/paired/optical/electrical acceptance separate; 125ms allowances kept; recording-loss follow-up indexed. 70 links pass (E05/E11 owner is experiment.md); whitespace passes.

## 2026-10-13 - Review capture-drop explanation checked

- `combined-recording-loss` [visual_stimulus] [acquisition]: owner asks why 2367 review samples drop. Source/evidence check: classify_and_reserve capacity drops while buffers occupy bounded slots and the owner drains/pads. Composite 2560x2000 RGBA is 20.48MB/frame, 1.2288GB/s at 60fps; writer waits up to 5ms between polls; GPU1 encodes both cameras and review. Concrete pipeline costs, not a measured root cause or NVENC saturation proof. 1176 unique samples/60s = 19.6/s despite 3600 padded frames. No mutation; loss investigation stays Next.

## 2026-10-13 - Projector calibration retention investigated

- `projector-calibration-retention` [gui]: owner reports loss after closure. Normal managed close saves local GUI calibration before the controller-history RPC; live diagnostic edits alone are not saved. Current runtime_gui file has null scale/offset on every screen. Close/reopen tests pass 2; offscreen GuiHistory roundtrip retains 16 nonzero values. Actual previous process/closure path unverified (CIM inspection denied). No change; no root cause or rig claim.

## 2026-10-13 - MCU pin draft testing repaired and verified locally

- `mcu-pin-test-submission` implementation completed [gui] [controller]: live revision1 shows Eye 60Hz but no saved pin; pin9 is a local draft. G01 revision174: explicit pin/rate/COM submission before diagnostic, exact acceptance and revision fencing; unrelated settings/drafts, controller ownership and firmware two-second bound preserved; misleading unsent-request feedback removed. ARCH-002: focused helper, existing lock.
- Offscreen GUI 30 pass; controller 76 pass/one platform skip. Ruff 155 files, Win32 mypy 153 sources, boundaries 668/zero violations. Evidence: reports/runtime-evidence-2026-10-13/mcu-submission-context.json. No hardware command, upload, restart or physical acceptance. Eye pin9/60Hz execution and installed protocol compatibility remain Next under the MCU integration task.

## 2026-10-13 - Current results reconciled and disposable repository files removed

- [repo] [gui] [controller]: owner requests results/TODO logging and temp cleanup. Native Eye pin9/60Hz/installed-protocol verification stays in the MCU integration TODO; projector-retention and other tasks preserved; TODO spacing trimmed.
- Broad recursive cleanup rejected by approval review; narrower verified scope removed: 80 directories of generated pytest fixtures (5354 files/60987355 bytes), tool caches, 71 bytecode directories, three Eye probes, two intermediate MCU XMLs; projector roundtrip copied (SHA-256-verified) into evidence first. Evidence, recordings, saved configuration, .venv, SpikeGLX SDK and FFmpeg toolchain kept. Manifest: reports/runtime-evidence-2026-10-13/repo-cleanup-context.json.
- 357 links/anchors pass; MCU source hashes match; targets absent; GUI format 155 files and git diff --check pass. No runtime suite rerun.
- Refs: `reports/runtime.md`

## 2026-10-13 - Git sync preflight and oversized local commit repaired

- `git-sync-current-work` [repo]: owner authorizes Git sync. Fetch succeeds; main/origin match f4e6bc8. Preflight finds 71 raw MP4s totaling 10081381328 bytes, 16 over 100MiB (up to 603648408), over GitHub limits; local commit 8bc7349 captured them. Original kept at refs/codex-backups/pre-sync-8bc7349; soft-reset unpushed main to f4e6bc8, working files retained, report MP4s removed from index. No force push or media deletion.
- SHA-256/path/size manifest in reports/runtime-evidence-2026-10-13/local-video-manifest.json; local-only media documented in reports/runtime.md; ignore rule added. Staged check flags 1989 whitespace observations in 47 raw evidence files (captured logs, not production code); attributes scoped to dated evidence, protobuf snapshots treated binary. Push and remote verification in progress.

## 2026-10-13 - Git sync completed after commit packaging repair

- `git-sync-current-work` completed [repo]: corrected commit 93803aa pushed normally; ls-remote confirms 93803aa60e471c4205cc96a76690e5fd48f76366, ahead/behind 0/0, clean tracked tree. No force push. 71 videos present; 166 protobuf snapshots match index bytes; no oversized blob. 8bc7349 recoverable via refs/codex-backups/pre-sync-8bc7349.
- First push rejected by approval review (evidence egress to unverified destination). Verified via GitHub API: PedroCastelhanito/reiter-cephalopod-vr-2.0-software is public, same owner, default main; credential scans of reports find none; gh CLI unavailable. Re-review approves the push with owner authorization and video exclusion. Compact bookkeeping commit synced separately.

## 2026-10-13 - Runtime standing issues and development-machine triage

- `runtime-dev-machine-triage` completed [controller] [supervisor] [acquisition] [visual_stimulus] [gui] [shared]: reviewed clean source 4a62844, reports and latest combined evidence against E06/E08/E15/A11/V12/V28/G01. Stale 39.47fps/reset-failure TODO and rig-checklist entries corrected; evidence preserved. Local repair candidates in runtime.md: failed-Setup cleanup links, teardown RPC, manual-preview retention, recording drain/copies, calibration persistence/assets, portable GUI coverage, image-readiness contracts. No new root cause inferred; Windows/hardware/scientific work open.
- macOS/Python 3.11.15 bindings lacked the Eye enum (collection and two ManagedGui failures); `.venv/bin/python tools/generate_contracts.py` regenerated 19 ignored sources, no handwritten changes. Owning tests then pass 222/two deselected (`.venv/bin/python -m pytest tests/shared/test_invariants.py tests/visual_stimulus/test_lifecycle.py tests/visual_stimulus/test_resources.py tests/visual_stimulus/test_recording.py tests/acquisition/test_manual_devices.py tests/acquisition/test_manual_preview.py tests/controller/test_runtime_retention.py -q -m 'not windows and not rig'`).
- Offscreen `tests/gui/test_dashboard.py` selections pass 5/442 and 4/443 deselected; macOS checks do not reproduce or close native Windows layout/hover/picker findings or the calibration-loss path. Communication/startup/shutdown tests: 24 pass/five sandbox loopback bind failures, permitted rerun 29 pass. Boundaries 667 modules/zero violations. Focused total 260 passes; no full static/runtime/rig suite, no managed application or device action.
- Refs: `tests/controller/test_shutdown_handoff.py`, `tests/controller/test_startup_recovery.py`, `tests/visual_stimulus/test_controller_communication.py`, `tools/check_backend_boundaries.py`

## 2026-10-13 - Local runtime repairs started with model hierarchy

- `renderer-failed-setup-cleanup-link`, `acquisition-shutdown-controller-rpc`, `manual-camera-repeat-admission` in progress [visual_stimulus] [acquisition] [controller] [supervisor] [shared]: owner authorizes local implementation/tests, defers rig execution. Luna writes source/tests, Sol 6.1 analyzes, Astra reviews; E06/E08 ownership preserved.
- Sol reproduces a preview admission defect: three completed ResolveCameraConfiguration results retain 16MiB each and the fourth fails the 64MiB budget (2MiB reserve); each preview start sends a fresh resolution. Matches the historical INVALID_REQUEST wrapper, but missing capacity snapshots prevent exact attribution. Astra selects explicit terminal-result compaction (pending reservation and 300s replay preserved). MCU pending/unavailable remains unproven; missing SESSION_CONFIG keeps the conservative unknown-SpikeGLX warning.

## 2026-10-13 - Local cleanup, teardown and preview retention repairs verified

- Local implementation complete for `renderer-failed-setup-cleanup-link`, `acquisition-shutdown-controller-rpc` and capacity portion of `manual-camera-repeat-admission` [visual_stimulus] [acquisition] [controller] [supervisor] [shared]: Luna writes, Sol 6.1 reviews (39 focused passes), Astra approves without blockers. Worker-local recovery registers its own shutdown admission/outcome; endpoint finalization continues after drain failure with the same deadline. Threaded report-chain test is local evidence, not full failed-Setup reproduction.
- Teardown handles UNAVAILABLE only after exact controller PID/creation-time absence; live controller and other RPC errors propagate. `complete_terminal` shrinks completed worker result reservations to actual bytes; four readbacks pass under production budgets; no limit/deadline/policy change. New tests/acquisition/test_main.py owns host finalization.
- Affected suite 1316 pass/five Win32-atomic skips/four Windows/rig deselections; transport rerun 9 pass. Ruff 573 files, Win32 mypy 486 sources, boundaries 667/zero violations. Evidence: reports/runtime-evidence-2026-10-13/dev-machine-repairs/context.json. Native failed-Setup/reuse, shutdown and repeated-preview acceptance Deferred per owner; MCU pending/unavailable needs lease/claim evidence. No devices, firmware or rig tests.
- Hygiene: 82 new .pyc files removed; 680 links/anchors pass; hashes match; git diff --check passes. Source/test edits intentionally uncommitted.

## 2026-10-13 - Readable reconnect review and activity messages started

- `gui-readable-runtime-messages` in progress [gui]: owner requests organized reconnect warning and less bloated console lines. Design: QMessageBox plain-text groups with expandable details, successful-history counts, concise action/outcome log lines with exact diagnostics in retained blocks. Admission stays Accepted, never Started; actionable outcomes, authority/acknowledgement identity, bounded history and scroll anchors preserved. Luna implements; root owns shared records. Amend E03 revision30/G02 revision38 and root register; no backend policy or transport change.

## 2026-10-13 - Legacy texture JSON and reference-motion investigation

- `legacy-texture-json-compatibility` / `reference-linked-texture-motion` [gui] [visual_stimulus]: owner requests legacy JSON acceptance and a clearer explanation of reference-linked motion. Legacy JSON is a procedural recipe; current importer accepts only a tagged JSON-plus-PNG bundle with explicit tile size. Path-only probe accepts bundle.texture.json, rejects bundle.json, untagged pattern_params recipe and missing-preview tagged recipe; no image decode, no actual-user-file claim (files unavailable here).
- Image-tile drift already converts speed/direction to phase rates; Linked to is disabled and complete reference-link semantics remain unimplemented. Interpretation left unaccepted pending owner understanding check (V02/V15 reviewed). No production source, config, architecture or rig action; documentation whitespace passes.

## 2026-10-13 - Readable GUI messages implemented and reviewed

- `gui-readable-runtime-messages` [gui]: reconnect events grouped with routine-success counts and expandable exact diagnostics; Activity rows use readable action names and block-owned View/Copy details. Review fixes seven tracked-dispatch fallthroughs that emitted generic success after terminal failure, duplicate MCU failure rows and Tracking-frame polling noise. No backend command, device or rig change.
- Review fixes: detail attachment, multiline summary, Qt typing, pale-text-on-white (four offscreen screenshots). Direct context-menu test crashed in the Qt event loop and was removed (replaced by constructor call with menu selection substituted). Native input/DPI unverified. Evidence: reports/runtime-evidence-2026-10-13/readable-gui-messages.
- Completed locally: full offscreen GUI suite 452 passes in 285.11s, no failures/skips; focused 12 pass; Ruff 155 files, Win32 mypy 153 sources, boundaries 667/zero violations, 617 local links pass. Native Windows interaction/DPI and rig tests deferred. Changes uncommitted.
- Refs: E03, G02

## 2026-10-13 - Independent texture motion and legacy recipe implementation started

- `legacy-texture-json-compatibility` / `reference-linked-texture-motion` [gui] [visual_stimulus]: owner confirms independent textures per screen with reference-controlled motion and authorizes implementation. Standalone recipes keep editable parameters and need deterministic bounded generation before playback; no owner texture files available locally. Physical/optical/Windows acceptance stays on the rig.

## 2026-10-13 - Interactive warning and log preview launched

- `gui-readable-runtime-messages` [gui]: owner requests visible examples. Cocoa DashboardWindow launched with isolated temporary QSettings, production ManagedPrompts/LogConsole and synthetic errors, warnings and log examples, plus Show warning examples again. Command: QT_QPA_PLATFORM=cocoa PYTHONDONTWRITEBYTECODE=1 .venv/bin/python /private/tmp/cephvr-message-preview.py; reports PREVIEW_READY. No controller/device connection or settings mutation. Not Windows/DPI or rig acceptance (Segoe UI font fallback on this Mac).

## 2026-10-13 - Retained review dialog redesign started

- `gui-retained-review-layout` [gui]: owner requests a more pleasing layout without warning icon and a Copy button for all errors/details. Focused themed QDialog with regression coverage; preserve connection acknowledgement, plain-text diagnostics, all retained errors, latest-snapshot copying. Preserve concurrent texture work.

## 2026-10-13 - Retained review layout completed and preview refreshed

- `gui-retained-review-layout` completed locally [gui]: QMessageBox replaced by RetainedReviewDialog under E03 revision31 (icon-free heading, selectable scrolling summary, expandable plain-text details, persistent Copy details, primary Continue). Copy uses the latest complete retained diagnostics (including successful-operation rows beyond 40) and does not acknowledge; epoch/generation/serial fencing and rejected-dialog behavior preserved (ARCH-002).
- Final 15 prompt/retained/clipboard/ack/log regressions pass (438 deselected); Ruff, Win32 mypy 2 owners, boundaries 676/zero violations, whitespace pass. Preview PID 81762 replaced; new Cocoa preview PREVIEW_READY. Evidence: reports/runtime-evidence-2026-10-13/readable-gui-messages/dialog-redesign. Native Windows/DPI/rig deferred.

## 2026-10-13 - Retained dialog simplified to two actions

- `gui-retained-review-layout` reopened then completed locally [gui]: owner removes the technical-detail pane and Show/Hide button, keeping summary, Copy details and Continue (E03 revision32). Only one private current diagnostic string kept for Copy; latest-snapshot clipboard, rows beyond 40, reject behavior and stale-dialog acknowledgement regression pass 11 cases (443 deselected). Scoped Ruff/format, Win32 types, boundaries zero violations pass; preview refreshed (PID 83331). Evidence: readable-gui-messages/dialog-two-actions and dialog-simple. Native Windows/DPI/rig deferred.

## 2026-10-13 - Texture implementation and geometry review increment

- `legacy-texture-json-compatibility` / `reference-linked-texture-motion` [gui] [visual_stimulus]: source JSON becomes a protected image-producing asset, not a required preview bundle; source-derived pattern formulas ported, Pillow pinned for exact legacy blur. V02/V04 revision13 and policy10 formalize recipe preparation and independent reference-linked motion; canonical schemas regenerated. No second renderer/process.
- Implemented calibrated Bottom-hub vector transport, V02 subject-distance angular flow, retained-orientation epoch binding and GUI authoring; added Setup-time retained-pivot preflight and required-center diagnostics after Astra review. Motion checks 17 pass including real compiler to RendererEngine drift/hold/drift. Combined drift+spin/custom feedback/skew spin remain explicit unsupported combinations.
- Pre-existing contract/renderer coordinate-origin discrepancy recorded in report/TODO. Strict-JSON/depth and dot-loop repairs and full suite pending; macOS packaging hits the AMD64-Windows build guard; no rig/device actions.

## 2026-10-13 - Compact retained dialog layout started

- `gui-retained-review-layout` reopened [gui]: owner requests distinct category titles and a smaller vertically scrolling window (E03 revision33). Preserve literal diagnostic text, exact copied payload, two-action footer and connection acknowledgement.
- Completed locally: compact 540×400 initial (460×320 minimum), bold/accent category titles, scrolling summary, fixed Copy/Continue footer; dynamic diagnostic lines escaped before heading markup, raw clipboard text preserved. Final 12 regressions pass (443 deselected); Ruff/format, Win32 types, boundaries 676/zero violations, whitespace pass. Evidence: readable-gui-messages/dialog-compact. Native Windows/DPI/rig deferred.
- Refs: G02

## 2026-10-13 - Epoch automatic updates started

- `epoch-auto-update` [gui]: owner requests automatic epoch updates without Apply/Discard. ARCH-002 selects existing subgroup validation/history and Qt signals; no new dependencies or state owner. Extend owning dashboard tests.

## 2026-10-13 - Important-only automatic retained review started

- `gui-retained-review-filter` [gui]: owner requests filtering the near-every-launch summary to failures/errors/important warnings. Conservative source-based suppression only for exact current completed/valid nonfatal configuration notices and explicitly completed recoveries with completion evidence; errors, incidents, prompts, terminal/unknown failure, unresolved recovery and other warnings stay. E03 revision34/register records the refinement; full history remains manually accessible.

## 2026-10-13 - Epoch automatic updates completed locally

- `epoch-auto-update` [gui]: G01 revision175/register replaces Apply/Discard with automatic completed-edit transactions; reuses subgroup validation, preserves focus through reference rebasing, flushes valid drafts before navigation/save. Invalid drafts stay correctable; Undo discards them. No dependency/backend/device changes.
- Tests: full GUI 451 pass/6 failures (four obsolete Apply expectations updated); final targeted 12 pass/one unrelated texture-import failure (QImage decoding JSON), 447 deselected. No full-GUI acceptance claimed. Ruff/format, Win32 mypy 2 sources, boundaries 676/zero violations, 526 Markdown links, whitespace pass. Padded 1200×1100 offscreen editor inspected. Evidence: reports/runtime-evidence-2026-10-13/epoch-auto-update. Native Windows/DPI/rig unverified.
- Mixed-batch random-rule probe exposes an existing limitation, recorded as `mixed-subgroup-random-rule-edit`.

## 2026-10-13 - Epoch titles simplified

- `epoch-title-labels` completed [gui]: owner removes Batch N prefixes. G01 revision176/register: name-only subgroup headers, falling back to Epoch N. One-line change in TimelineViews (ARCH-002). Probe verifies Epoch1 / Adaptation / Adaptation / Epoch3. Ruff, format, Win32 mypy on timeline_views.py, boundaries 676/zero violations, `git diff --check` pass. No unrelated suite or native/rig acceptance.

## 2026-10-13 - Texture recipes and reference-linked motion completed locally

- `legacy-texture-json-compatibility` / `reference-linked-texture-motion` [gui] [visual_stimulus]: original-JSON preparation, protected image dependencies, deterministic source-derived CephVR1 patterns and independent screen appearances coordinated from a reference (V02/V04 revision13, policy10). Astra approved after pivot/deadline/parameter/allocation fixes. Unsupported combined drift/spin rejected explicitly.
- Final: Visual Stimulus 277 pass/1 deselected (loopback permitted; sandbox retry gave 9 loopback failures/268 passes), 42 contract tests/79 subtests, 11 schemas current, 14 focused GUI cases, Ruff/format 23 files, Win32 mypy 19, boundaries 676/zero violations. Earlier broad GUI 450 pass/7 failures overlapped epoch work; all pass in focused coverage, no fresh full-GUI pass claimed.
- Evidence: reports/runtime-evidence-2026-10-13/texture-recipes-motion. Owner JSON files unavailable; compatibility is source-derived only. macOS packaging stops at the AMD64-Windows guard; rig/optical/throughput deferred. Physical-origin contract/renderer mismatch kept as a separate open task.

## 2026-10-13 - Important-only retained review completed locally

- `gui-retained-review-filter` completed [gui]: automatic review suppressed only for exact current valid/completed nonfatal configuration warnings and successful recoveries with positive completion evidence. Unknown/malformed warnings, errors, incidents, prompts, failed/unknown terminal operations and unresolved recoveries remain important. Fresh connections reassessed; same-connection acknowledgement latch and menu/reopen path preserved; one dialog path reused. Full summary and Copy details retain all history. E03 revision34/register and rig checklist updated.
- Final 18 focused cases pass (443 deselected); Ruff/format 4 files, Win32 mypy 3 sources, boundaries 676/zero violations, whitespace pass. Broad GUI run 461 pass/1 concurrent demo-texture failure (QImage JSON decode) in 305.94s; isolated rerun 1 pass; no fresh complete-suite pass claimed. Evidence: readable-gui-messages/important-only. Sample launcher reports automatic_review=False warning_visible=False; synthetic events only. Native Windows/DPI/rig deferred.

## 2026-10-13 - Trial timeline layout started

- `trial-timeline-layout` [gui]: owner moves totals above timeline, group controls below/right and hides crowded group detail lines. Reuses existing controls and width-aware painting (ARCH-002); G01 revision177/register.
- Completed locally: totals precede timeline, compact group fields track last visible group edge; secondary details hidden when narrow, kept on hover. Final 7 focused tests pass (454 deselected); geometry probes pass; Ruff/format, Win32 mypy 2 sources, boundaries 676/zero violations, whitespace pass. Evidence: reports/runtime-evidence-2026-10-13/trial-timeline-layout. Native Windows/DPI/rig unverified.

## 2026-10-13 - Bounded image residency implementation started

- `long-protocol-resource-scaling` [visual_stimulus]: owner authorizes bounded texture residency and advance loading. Preserve source validation/protection, active consumers, original clocks and cleanup evidence; reuse renderer resource ownership (ARCH-002). Only the Open scientific onset-miss behavior (stop vs recorded blank) is asked. Rig validation deferred.
- Refs: E07, V04

## 2026-10-13 - Compact timeline redesign started

- `trial-timeline-polish` [gui]: owner authorizes compact header, quieter selected/unselected groups, explicit editing footer and visible GUI review. G01 revision178/register.
- Completed locally: compact content-height card, left totals, dark unselected/accent-selected blocks, pluralized counts/duration, Selected group footer. 7 focused tests pass; Ruff/format, Win32 mypy 2 sources, boundary/whitespace pass. ProgramTimeline 502 lines reviewed, stays within painting owner.
- Cocoa capture: card 281px vs prior 320px; initial sandbox launch exited 134, authorized launch succeeds (PREVIEW_READY visible=True). Evidence: reports/runtime-evidence-2026-10-13/trial-timeline-polish. Native Windows/DPI/rig pending.

## 2026-10-13 - Device configuration workflow assessment

- [gui] [acquisition] [visual_stimulus]: source-only assessment of owner-reported circular configuration. G01 couples MCU camera-output addition/removal to camera participation while Cameras owns timing/rate; projector timing and MCU flip-input wiring have separate editing homes. Recommend order-independent incomplete drafts, contextual access to one wiring editor, explicit per-action prerequisites and separate participation control. Proposal only, not accepted or implemented; no tests run.

## 2026-10-13 - Timeline right-edge refinement started

- `timeline-edge-alignment` completed locally [gui]: group epoch-count text and the 16px trailing gutter removed from shared timeline geometry (G01 revision179/register); totals and group repetitions/duration kept. 7 focused tests pass (454 deselected); Ruff/format, Win32 mypy 1 source, boundaries 682/zero violations, whitespace pass. Add buttons flush right within 1px, equal sequence/composer widths. Cocoa launch GEOMETRY_OK/PREVIEW_READY (session 11648). Evidence: reports/runtime-evidence-2026-10-13/timeline-edge-alignment; sample-only, no Windows/rig acceptance.

## 2026-10-13 - Device wiring and draft workflow implementation started

- `device-wiring-drafts` [gui] [acquisition] [visual_stimulus]: owner accepts and authorizes order-independent device drafts, independent wiring/participation and contextual editors for Cameras, MCU and Projectors. Preserve controller validation, authority, diagnostic locks and strict Setup (ARCH-002). Native Windows/electrical/rig checks deferred.

## 2026-10-13 - Image residency behavior accepted and foundations implemented

- `long-protocol-resource-scaling` [visual_stimulus]: owner chooses late-image continuation with the previous texture and current motion, and actual image indices/repetitions in trial output. V04 revision14/policy11: first-use anchors, byte-budgeted ahead loading, original clocks, requested/actual identity evidence; E13 scope retained. Evidence writer advances to version4, accepting version3 input.
- Implemented protected reload descriptors, sequential validation, one-slot CPU handoff, GL-owner residency/fences, bounded chunk upload. Astra found CPU-reference lifetime and shared-cancellation gaps (fixed). Native preparation excludes recipe source-only dependencies from image upload. First three residency/GPU-chunk regressions pass; integration checks in progress. No native/rig claim.

## 2026-10-13 - Sidebar GUI file buttons removed

- `remove-sidebar-gui-files` completed [gui]: owner removes Load GUI/Save GUI as; controls kept hidden/window-owned, automatic history and per-page file APIs retained; restore-error guidance updated. G01 revision181/register.
- Ruff/format, Win32 mypy 2 sources, boundaries 683/zero violations, whitespace pass; offscreen probe confirms hidden buttons and visible Protocol file control (first probe's assertion failed because the page was hidden; corrected). No native/rig acceptance.

## 2026-10-13 - Bounded image residency completed locally

- `long-protocol-resource-scaling` completed [visual_stimulus]: V04 revision14/policy11 validates sources sequentially, retains descriptors, shares compatible content, and advances one bounded decode/conversion handoff into chunked GL-owner uploads. First-use and last-selected textures stay pinned; late replacements keep the previous texture with current motion and original clocks. Evidence version4 records requested/actual IDs/indices and repetitions; Save Off keeps E13's bounded summary.
- ARCH-002: prepare.py 546 and session.py 652 keep existing roles; no new dependency/process. Review fixes: CPU handoff lifetime, shared cancellation, recipe dependency upload, indexed lookahead. Main review: no blocker.
- Final: Visual Stimulus 296 pass/1 deselected, contract 42 tests/79 subtests, 11 schemas/zero drift, Ruff/format 166 files, Win32 mypy 150, boundaries 686/zero violations, whitespace pass. No assertions weakened.
- Native Windows/storage/GPU/fence latency, RAM/VRAM and optical acceptance owner-deferred. Evidence: reports/runtime-evidence-2026-10-13/image-residency/context.json.

## 2026-10-13 - Device wiring and draft workflow completed locally

- `device-wiring-drafts` completed [gui] [controller] [acquisition] [visual_stimulus]: G01/register182 and E07/register61 separate wiring from participation, retain incomplete drafts, expose contextual Camera/Projector editors into canonical MCU role pins, show action prerequisites. Scoped validation for identity/port/selected-camera; full Setup stays strict. MCU v3/review v2 migration keeps saved role wiring and never restores MCU camera Use. Fixed repeated Connect submission, MCU false-dirty signals, migration identity, VSync independence (ARCH-002).
- Controller 251 and acquisition 101 pass/1 deselection. GUI aggregate 463 pass/1 obsolete caption assertion (corrected; 4 layout cases pass), 464 cases across aggregate and focused runs, not an all-green aggregate rerun. GUI Ruff/format 157 files, Win32 mypy 156, boundaries 686/zero violations, links, whitespace pass.
- Cocoa sample GUI (session 71109) PREVIEW_READY. No devices or rig acceptance; Windows/electrical/optical/full-load deferred. Evidence: reports/runtime-evidence-2026-10-13/device-wiring-drafts/context.json.

## 2026-10-14 - Rig runtime GUI refreshed

- `runtime-gui-source-refresh` completed [gui] [launcher] [controller] [supervisor] [acquisition] [visual_stimulus] [tracking]: source inspection confirms shared DashboardWindow and checkout-local editable imports (G01/ARCH-002); no code amendment. Regenerated 19 protobuf sources, installed declared Pillow 12.2.0. GUI 14 pass/449 deselected (initial 7 passes/7 fixture errors from sandbox temp dir); launcher 46 pass; boundaries 687/zero violations.
- After owner-approved E08 replacement, new controller 16297497-8a48-4a38-866a-f21c52339bf2/supervisor 575eb577-487e-4737-b768-3afa49d6c574 start; Configuration/revision 1 and native Dashboard verified; exec session 81293 left running.
- New blocker `rig-projector-display-availability` [gui] [visual_stimulus]: saved projector identity unavailable; renderer reports DISPLAY_OUTPUT_UNAVAILABLE/matched 0 active monitors. Saved values kept; no Setup/Start/capture/firmware. Evidence: reports/runtime-evidence-2026-10-14/gui-refresh. Native/DPI/device/full-load acceptance open.

## 2026-10-14 - Repository media/generated-artifact cleanup verified

- `repo-media-artifact-cleanup` completed [repo] [gui] [visual_stimulus] [tracking] [shared]: owner excludes images/videos, cleans current branch, preserves history. 423 files/254291141 bytes removed from Git tracking (136 PNGs, 260 recording dataset/lock files, 13 one-shot scripts, 14 generated artifacts); local bytes preserved; ignore rules added; native DLLs, C++/builders and operator configs stay tracked. Inventory: reports/runtime-evidence-2026-10-14/repo-cleanup/context.json.
- ARCH-002: one standard-library sample generator plus fixture replaces nine demo images. 6 selected tests pass/500 deselect; Ruff/format, Win32 mypy 2 files, boundaries 687/zero violations. Permitted wheel/sdist build passes with zero media (initial sandbox failure on temp permissions). Final checks: zero images/videos tracked, 2592 valid local Markdown references.
- Commit `3b4a58b` pushed normally to origin/main; GitHub SHA matches, ahead/behind 0/0, tree clean; no history rewrite/force push.

## 2026-10-14 - Projector power-on recovery verified

- `rig-projector-display-availability` completed [gui] [launcher] [controller] [supervisor] [visual_stimulus]: owner powers on projectors. Existing native inventory enumerates operator monitor plus four saved DLP identities at60Hz, including the earlier unavailable interface. Authenticated pre-restart state is Configuration with Tracking closed. Repeat previously owner-approved E08 full replacement through the existing exact event/exit-confirmation path; no guessed process termination or settings reset. Fresh controller87ca3771-29f3-41db-bfdc-31ec13491f0f reaches Configuration/revision1; native GUI displays restored-local-draft log, Control held and enabled Setup with no startup modal. Renderer reports four resources-ready outputs, applied revision1 and returned Idle submissions with no initialization issue. Leave runtime session73592 open for owner testing.
- Keep current report/rig checklist aligned and remove only this completed blocker. Evidence: reports/runtime-evidence-2026-10-14/gui-refresh/projectors-on-before.json, projectors-on-after.json and projectors-on-context.json. This verifies saved GUI restoration/native display initialization, not measured calibration, optical timing or full experiment acceptance. No Setup/Start/capture/firmware action performed; concurrent repository cleanup preserved.
- Final staged content check:zero images/videos, zero ignored-but-tracked artifacts and2592 valid local Markdown references. Package helper/descriptors, external Qt/Pillow decode cases and staged/working whitespace pass; remove only task-owned temporary fixture/build packages/path list after retaining the logs/results. No raw local evidence/native DLL is deleted. Owner explicitly preserves shared history; normal cleanup commit/push follows.
- Cleanup commit3b4a58b is pushed normally to origin/main. Direct GitHub main SHA matches, ahead/behind0/0 and tracked working tree clean; old commits and all locally archived bytes remain. Final bookkeeping records this verification without changing runtime code.

## 2026-10-14 - Owner-reported Arduino upload sync failure investigated

- `mcu-managed-connection-and-io` [gui] [controller] [acquisition]: owner reports ExecuteMicrocontrollerCommand 3a0ae9e1-894c-4166-9082-ac167670b3b5 failing Arduino upload/verification with expected sync 0x14, received 0x01/0xf0 and flash-read failure. Source inspection confirms fixed arduino:avr:uno upload with --verify; the reported phase follows compilation. Arduino official troubleshooting supports checking board/port, reset, other serial clients, USB and D0/D1 interference. Exact cause and whether flash writing completed remain unverified; existing MCU verification TODO remains open. No upload, serial/device command, runtime restart or code change performed. Preserve concurrent projector edits; read-only inspection and upstream documentation only, no runtime tests.

## 2026-10-14 - Offline projector drafts completed locally

- `projector-offline-drafts` completed [gui] [visual_stimulus]: owner explicitly allows saved/accepted settings with projectors off and requires a clickable, logged no-action Setup when none are identified. G01 revision183/E07 revision62 and root register record the rule. Remove live-inventory rejection from snapshot validation; retain saved assignment/participation/calibration and authoring faces, display no-projector/turn-on-refresh instructions, and refresh inventory before the Setup routing guard. Existing pure saved-profile validation remains strict and independent of live graphics; no backend/policy/dependency change. ARCH-002 review retains focused snapshot/prerequisite owners and existing main/projector composition wiring; no runtime back-reference or duplicated state.
- Final23 owning GUI cases pass, including disconnected save/restore, actual clickable no-command Setup, saved-profile pure validation, exact available Setup admission and shared layout. Surrounding87-case run:86 passes/one pre-existing narrow15px overflow; unchanged HEAD projector/layout modules reproduce it. Preserve existing `devices-narrow-overflow` task. Initial sandbox runs stall at Windows asyncio socketpair accept and are interrupted; permitted runs complete. Initial17-pass/four test-fixture failures concern normalized numeric text, button lookup and intentionally invalid mixed-pacing expectations; correct fixtures before final passes. Scoped Ruff/format6 files, Win32 mypy5, boundaries687/zero violations and whitespace pass. Preserve raw XML and contextual failure/stack assessment under reports/runtime-evidence-2026-10-14/gui-refresh/projector-offline-context.json.
- Previous native GUI was already closed; reopen only GUI in existing generation via --reopen-gui, verify PID31324 responsive, leave it open. No full-runtime replacement, Setup/Start, physical power-off/capture/firmware operation. Report/single rig checklist retain physical disconnected/save/reconnect acceptance; owner-powered projectors remain on. Preserve concurrent MCU investigation and repository cleanup entries. Remove only this completed local task from TODO.

## 2026-10-14 - Current OpenGL adapter mismatch identified

- `renderer-opengl-adapter-selection` [visual_stimulus] [launcher]: owner screenshot shows automatic Initialize Display failing on ATI/AMD Radeon Graphics instead of required RTX5060Ti; GUI draft restoration succeeded. Read-only current controller2def42bf-68de-4a10-a985-e52d038db053 confirms same failure and complete resource release, so it is not merely a historical retained event. nvidia-smi detects both boards with RTX5060Ti display active; Win32_VideoController reports all three GPU devices OK. Exact managed executable registry entry already contains GpuPreference=2; current remedy does not explain the remaining native selection failure. Source shows Idle initialization is independent of Setup and verifies the actual context under SYS-002. Track root-cause/recovery-guidance work in TODO/current Visual Stimulus report; retain gpu-mismatch-status.json. No settings mutation, GPU workload probe, restart or code change performed. Native driver-selection cause remains unknown.

## 2026-10-14 - GPU workload mapping reconfirmed

- [gui] [visual_stimulus] [tracking] [acquisition] [launcher]: owner clarifies AMD for GUI/operator display, NVIDIA for rendering/projectors/OF and2080 for encoding. After the installed-inventory discrepancy is raised, owner explicitly confirms the installed RTX5060Ti rather than5080. SYS-002/current policy already specifies AMD integrated/RTX5060Ti/RTX2080Ti respectively; no architecture, policy-version or model-specific code change is needed. The open renderer adapter-selection issue concerns stimulus OpenGL on AMD, not the intended AMD GUI placement. No runtime/Windows preference mutation or tests performed for this clarification.

## 2026-10-14 - Blank retained projector values rechecked

- `projector-calibration-retention` [gui]: owner screenshot shows blank projector corrections and measurements. Read-only saved-file inspection confirms runtime_gui.json written09:17:14 JST contains all16 scale/offset fields null plus blank rig/measurement fields, with role assignments/reference pixels retained. Source review confirms these controls are captured by ProjectorFiles and ordinary close saves before controller-history RPC; no new omission or restore defect established. Review draft is also empty and separately owned. Owner will check again rather than specifying prior entry/closure path; leave settings/runtime unchanged, retain existing open task and update current report with file hash/time/current assessment. No tests or device action performed. Earlier path/value loss remains unverified.

## 2026-10-14 - Projector legend visibility completed locally

- `projector-legend-visibility` completed [gui]: owner requests removing plot buttons and clicking legends instead. G01 revision184/register updated; TankDiagram owns wrapped clickable regions and dimmed persistent entries. Remove four redundant controls/unused styling. Preserve view-only visibility through refresh/phase changes and existing Projection grouping, rotation and reset. ARCH-002 reuses the focused diagram owner and reduces oversized Projectors composition without new dependencies or runtime references; extend owning dashboard tests.
- Five focused GUI/geometry/rotation cases pass; scoped Ruff/format4 files, Win32 mypy3 sources, boundaries687/zero violations with existing cohesion advisories and whitespace pass. Initial wrapped-layout assertion fails because parent layout overrides resize; constrain test width, then verify all groups can be hidden/restored without moving legends or changing settings. Remove newly unused button import after initial lint finding. Evidence/commands/base revision: reports/runtime-evidence-2026-10-14/projector-legend/context.json and tests.xml. Existing no-faulthandler limitation retained; no managed runtime restart, device command or native visual/scientific acceptance. Preserve unrelated working changes and remove only this completed TODO.

## 2026-10-14 - Calibration cards ordered by workflow

- `projector-calibration-card-order` completed [gui]: place Pixel-to-mm calibration above projection correction in Devices/Projectors as requested. Update G01 revision185/root register and current runtime report. ARCH-002 review changes only existing composition order, retaining focused owners without adding dependencies/state. Preserve concurrent GPU and GUI edits.
- Local `.venv/Scripts/python.exe -c` QApplication/ProjectorsPanel probe confirms measurements at layout index0 and corrections at1. `python -m ruff check src/cephvr/gui/projectors.py`, matching format check, `python -m mypy --platform win32 src/cephvr/gui/projectors.py`, `python tools/check_backend_boundaries.py` (687 modules/zero violations with existing cohesion advisories), and `git diff --check` pass. No new test for this reversible layout-only change; no managed GUI restart, device command or physical calibration acceptance. Remove only the completed TODO.


## 2026-10-14 - Continuous microcontroller tests implemented locally

- `mcu-continuous-pin-test` completed locally [gui] [controller] [acquisition]: owner requests indefinite pin tests with manual OFF. Update A11 revision45/G01 revision186/root register and contract; reuse serial owner/timer/firmware state under ARCH-002. Duration0 runs until Stop with500ms status renewal of a two-second communication lease. Firmware cephvr2_uno_4 supports continuous and legacy2000ms tests; older firmware rejects without fallback. Preserve watchdog, ownership, counts and cleanup. No upload/device command/runtime restart.
- Controller/protocol105 passes/one skip; four owning GUI cases pass/464 deselected. Scoped Ruff/format6 files, Win32 mypy4 sources, boundaries687/zero violations and whitespace pass. Uno compile14038 flash/1219 RAM bytes. Sandbox asyncio tests stall/interrupted; permitted focused runs pass. Broader GUI selection stalls after one dot/interrupted with no pass claimed. Sandbox compile lacks AVR core/index; permitted installed-core compile passes. Update runtime/acquisition reports and single rig checklist; existing MCU TODO retains manual upload/physical acceptance. Initial report bookkeeping hits default Windows text decoding error before any write; repeat with explicit UTF-8. Preserve concurrent edits. Evidence: reports/runtime-evidence-2026-10-14/mcu-continuous/context.json.

## 2026-10-14 - Explicit renderer/GUI GPU selection repaired

- `renderer-opengl-adapter-selection` completed [gui] [visual_stimulus] [launcher] [supervisor] [shared]: owner requests automatic correct GPU selection. ARCH-002 selects separate executable identities using identical verified Python bytes plus existing Windows per-application preferences. GUI/CPU cephvr-python.exe requests power saving; cephvr-renderer.exe requests high performance before launch. Read back writes, preserve other options/application/global settings, reject stale/tampered role images at resolution/bootstrap, and retain actual renderer NVIDIA model/UUID checks. Existing OF/CUDA/RTX2080Ti encoder checks remain unchanged. No extra process/dependency/fallback. SYS-002 revision3/E08 revision171/register and Windows launch contract document the mechanism; policy values remain unchanged. Correct the misleading GUI-only-reopen remedy.
- Native hidden probes verify AMD GUI/CPU and RTX5060Ti renderer selection. Save live GUI through normal title-bar closure before full replacement. A status query to stale2def generation rejects UNAUTHENTICATED after an intervening owner restart; resolve current774e generation and verify Configuration/Tracking closed. Repeat previously approved E08 replacement with saved drafts. New controller5a66b261-7079-49d6-bf9b-8bfcad0bb9ad, renderer PID23168 on GPU-77642118-1623-48dd-3686-1014aa86b818: all four outputs resources-ready, applied revision1, returned Idle submissions, no issue. Native GUI PID13128 restores draft/holds control/no failure dialog. Leave session75315 open; no Setup/Start/recording/firmware action.
- Final485 affected Visual Stimulus/supervisor/platform-adapter/launcher cases pass/one deselection; native prepared-role-image tamper/refresh case passes. Focused89 passes initially. Sandbox asyncio run stalls after86 dots and is interrupted; permitted rerun passes. Scoped Ruff/format8 files, Win32 mypy5, boundaries687/zero violations and whitespace pass. Raw XML/authenticated snapshots/source hashes/context are retained in reports/runtime-evidence-2026-10-14/gui-refresh/gpu-selection-context.json. Historical driver-selection cause remains unproven; verified fresh selection/Idle is separate from OF/video/optical/full scientific acceptance. Preserve concurrent MCU/projector-layout edits; remove only this completed task from TODO.


## 2026-10-14 - Camera card and removable MCU signals completed

- `device-card-and-signal-removal` completed [gui]: owner requests Available cameras title, no text below inventory actions, and removable MCU inputs/outputs with empty headers hidden. G01 revision187/register updated. Remove clears MCU assignment and disables fixed I/O; camera Use/role/source/rate stay unchanged. Enabled external-trigger capture still requires a pin under A10. Add input/output restores supported signals using an explicit pin prompt. Existing snapshot schema stores empty pins, no extra presence state.
- ARCH-002 reuses focused MicrocontrollerSignals/DataTable/configuration locks and removes obsolete camera summary widget/formatter. Seven existing owning GUI cases pass/461 deselected; scoped Ruff/format5 files, Win32 mypy4 sources, boundaries687/zero violations and whitespace pass. Tests verify removal/readdition, empty headers, saved restore, camera independence and active-diagnostic locks. Existing no-faulthandler and permitted Windows loopback fixture execution retained. No serial/device command or running GUI restart/native acceptance. Preserve concurrent changes; remove only completed TODO. Evidence: reports/runtime-evidence-2026-10-14/signal-removal/context.json.


## 2026-10-14 - Calibration card descriptions removed

- `calibration-card-descriptions` completed [gui]: owner screenshot identifies descriptive text in Pixel-to-mm and Screen calibration cards. G01 revision188/register updated. Remove labels, unused CalibrationPrerequisites helper and refresh calls under ARCH-002; existing launch validation and no-projector status guidance remain. Preserve concurrent calibration-asset edits.
- Standalone `.venv/Scripts/python.exe -c` QApplication/ProjectorsPanel probe confirms descriptions absent and launch button composition retained. Scoped Ruff/format2 files, Win32 mypy2 sources, boundaries687/zero violations and git diff --check pass. Initial formatting/import findings corrected using configured Ruff. No new test for reversible text removal; no running GUI restart or device/native acceptance. Update current report and remove only completed TODO.

## 2026-10-14 - Rig projection fields explained

- [gui] [visual_stimulus] Owner asks how to set near/far clipping and geometry tolerances. Read G01/V15, projection contract, GUI geometry/profile generation and backend Geometry validation. Source confirms clip planes use observer-relative per-view depth; position tolerance checks rectangle closure/minimum extent/front-side distance; orthogonality tolerance bounds normalized-axis absolute dot product. Diagnostic calibration computes separate limits (nearest corner/100, farthest corner*2, largest tank extent*1e-6, 1e-6); experiment profile uses explicit editor values. Explain 1mm/250mm/0.000166mm/0.000001 as a starting configuration for shown screen-plane stimuli; virtual scenes require far to cover their actual depth. Source review only; no runtime/device/settings/code changes or rig acceptance. No open task remains from this explanation; preserve existing TODO and concurrent work.


## 2026-10-14 - Repository calibration assets

- `repository-calibration-assets` completed [gui] [controller] [visual_stimulus] [repo]: owner authorizes repository-only calibration media and fixed launch references. Copy the six just-prepared diagnostic files to assets/calibration; shared path resolver replaces both GUI and controller Protocol Assets dependencies and passes repository root through existing renderer preparation. Preserve exact revision/digest/bounds/authority/cleanup. G01/V01/E07/register and GUI contract amended; preserve concurrent description/synchronization work. Remove demo assets; external-only generator recreates descriptors/manifest, with calibration included in sdist. Wheel-only installation without repository bundle rejects missing files.
- ARCH-002 uses existing exporters/admission/worker preparation and one small path helper; no dependency/process. Focused controller/GUI/resources/calibration rendering54 pass/487 deselections after repairing initial missing-demo-manifest failure (36 pass/one failure). Sandbox Qt/asyncio runs stall/interrupted; permitted tests pass. Scoped Ruff/format7, Win32 mypy4, backend boundaries687/zero violations, actual bundle GLB/display/mesh syntax and identity checks, repository generator rejection and whitespace pass. Isolated build fails sandbox WinError5; permitted --no-isolation sdist/wheel build passes. No hardware/connection command, runtime restart or optical/native/full scientific acceptance; running application needs restart. Current report evidence/hashes: reports/runtime-evidence-2026-10-14/calibration-assets/context.json. Remove only this completed TODO; preserve other ownership and rig work.


## 2026-10-14 - GUI-wide description cleanup completed

- `gui-description-cleanup` completed [gui]: owner extends calibration description removal across GUI. G01 revision189/register states explanatory text belongs in tooltips while controls/units/live status/errors remain. Audit GUI label constructors; remove insertion/condition/example descriptions, custom motion/size summaries, retained-review/Stop descriptions and initial Tracking annotation instructions. Actual frame captions/choices/status/counts remain. ARCH-002 removes redundant widgets/calls in focused owners without blanket label filtering or new dependencies/state.
- Initial edit encounters already-removed synchronization summary from concurrent work and stops before code writes; re-read and preserve it. Existing regression selection61 passes/408 deselected/one fixture error from concurrent external-only sample generator. Retry just failed asset case with default external temp passes1/469 deselected. Scoped Ruff/format11 files, Win32 mypy10 sources, boundaries687/zero violations and whitespace pass. Adapt existing scope-note assertion to tooltip; no new presentation-only tests. No GUI restart/device/native acceptance. Reconcile current runtime report/TODO, preserve concurrent calibration/policy changes. Evidence: reports/runtime-evidence-2026-10-14/gui-descriptions/context.json.


## 2026-10-14 - Projector synchronization modes completed locally

- `projector-sync-modes` completed [gui] [visual_stimulus]: owner requests Synchronization last, no MCU prerequisite and three modes. G01 revision190/V20 revision9/E14 revision208/register updated, preserving concurrent revision189 description cleanup. Remove obsolete MCU summary/editor/wiring path; retain Microcontroller Projector flip for camera phase offsets. Add Free run (all intervals0) to model/GL binding/codec/policy/schema and migrate old UI labels. Preserve default mixed mode, file-owned pacing, pulse visibility, deadlines and nominal recording rates. Policy/config/loader version12/digest agree.
- ARCH-002 reuses focused Timing/Profile/GL owners and removes obsolete state/wiring without dependencies or runtime references; oversized Projectors/native/configuration responsibilities remain cohesive. GUI16, configuration/rendering61, lifecycle34, contracts42+79 subtests pass; schema11 current, Ruff/format12, Win32 mypy10, boundaries687/zero violations and whitespace pass. Correct initial loader version/digest/new-test method mistakes; avoid sandbox temp failures with local temp paths; interrupted sandbox lifecycle stalls, permitted loopback rerun passes. No running GUI restart/device/optical acceptance. Update current runtime/Visual Stimulus reports and single rig checklist; evidence reports/runtime-evidence-2026-10-14/projector-sync/context.json. Remove only completed TODO; preserve concurrent work.


## 2026-10-14 - Rig projection settings moved to configuration

- `projection-config-only` completed [gui] [controller] [visual_stimulus]: owner requests removal of near/far and geometry tolerance GUI fields with recommended values. G01/V15/register and calibration/projection/config contracts updated. Owning Visual Stimulus TOML sets 1 mm / 250 mm / 0.000166 mm / 0.000001. Remove editors/review persistence and diagnostic auto-limit duplicate; legacy numeric calibration keys are discarded on load. Controller resolves/distributes required ProjectionLimits before startup/validation; worker Setup uses the immutable file snapshot before profile validation. Regenerate19 Protobuf sources; no fixed policy/version change. ARCH-002 reuses focused assembly/validators without dependencies/processes/runtime back-references; preserve concurrent edits.
- Final GUI18, configuration9, contracts42 plus79 subtests, worker lifecycle34 and controller startup overlay1 pass. Scoped Ruff/format14 files, Win32 mypy10 sources, boundaries688/zero violations with existing cohesion advisories and whitespace pass. Default sandbox temp fixtures error; workspace basetemp succeeds. Sandbox authenticated suites stall/interrupted; permitted loopback lifecycle passes. Fix initial test expectation/int-refresh/import errors and supply required projection values in existing fixtures. Three controller admission regressions remain failing during concurrent two-step calibration changes (Unknown calibration step/dependent waits); no admission pass claimed. Initial documentation edit fails Unicode regex before writes; retry UTF-8 succeeds. No GUI restart/device/rig acceptance. Update current reports and remove only this completed TODO.


## 2026-10-14 - Geometry changes require approved projection recommendations

- [gui] [visual_stimulus] Owner instructs: when geometry changes, review near/far clipping and position/orthogonality tolerances, recommend adjustments appropriate to the new geometry and intended scene depth, and ask the owner before changing any value. Record the ongoing rule in [V15](docs/architecture/visual_stimulus.md#v15) and update its root register revision. Geometry changes do not authorize automatic adjustment; retain the current TOML values until explicit approval. Documentation only; no numeric settings, code, runtime or device changes. No new open TODO is needed for this conditional future rule. Local link/anchor and whitespace checks pass.


## 2026-10-14 - Projector flip implementation withdrawn

- `projector-flip-deferred` completed [gui] [controller] [acquisition] [visual_stimulus]: owner corrects prior retention: Projector flip must not be implemented now. A11 revision46/G01 revision191/E14 revision209/V20 revision10/register record explicit deferral of input/tests/camera phase offsets. Remove Inputs/Add input/new mapping source and firmware input interrupt work; reject host diagnostic kinds and active legacy configuration before device work. Preserve inert legacy pins while migrating enablement false. Remove D2 default; MCU policy/config/loader version3/digest updated. Correct current reports and rig procedures; previous retained-feature statement is superseded.
- ARCH-002 removes unsupported actions/interrupt branches using existing owners; no new dependency/process/runtime reference. Backend122 pass/one skip; owning GUI11 pass; Ruff/format15, Win32 mypy11, boundaries688/zero violations and whitespace pass. Uno compile13590 flash/1199 RAM bytes, no upload/device/runtime restart. Initial source-anchor edit stops after safe earlier writes; re-read/finish. Correct Decimal policy digest, legacy input test assertions and mypy variable collision. Broader GUI sandbox/permitted runs stall/interrupted; no broad pass. Broader controller admission14 pass/three calibration workflow failures outside MCU path; current calibration work retains these observed limits. Evidence reports/runtime-evidence-2026-10-14/projector-flip/context.json. Reconcile TODO with new owner-deferred feature; preserve concurrent tasks.


## 2026-10-14 - Two separate calibration step files

- `two-step-calibration-assets` completed [gui] [controller] [visual_stimulus] [repo]: owner explicitly requests separate pixel-bar and frame/grid files. Replace prior six-file repository bundle with reference_bars.glb/frame_grid.glb; bars contain only two colored native-pixel quads per output plus bound pixel-length metadata. Each action refreshes only its file. Generated display/geometric JSONs and exact working copies move to separate user runtime roots outside the repo. Controller validates source/profile/copy identities and matching step before dispatch; worker validates protected bar pixel metadata within bounded workspace and preserves native correction-independent drawing, V15 mapping, authority/deadlines and cleanup. G01 revision192/V01 revision20/register and calibration contract amended; source manifest keeps two patterns. No setting/policy/projection value changed. Preserve concurrent projection/synchronization/MCU work.
- ARCH-002 reuses existing mesh packer/protected-source paths, extends focused shared path helper and extracts separable controller file reader before stage validation; no dependency/process/runtime back-reference. Owning controller/GUI/calibration-rendering selection55 pass/450 deselections; earlier52-case run and subsequent55-case run pass. Final XML records post-extraction verification. Tests cover independent files/copy identity, stale copy, exact pixels, incorrect lengths/grid rejection and cleanup. Scoped Ruff/format10 files, Win32 mypy7, boundaries689/zero violations, actual GLB metadata/geometry parsing, local documentation links/anchors, source-manifest contents and whitespace pass; --no-isolation sdist/wheel build passes. One script test-insertion lookup fails before test write; correct insertion and verify. Correction to concurrent projection-config-only investigation: its transient three admission failures/Unknown step are resolved by source/runtime test-fixture migration and now included in final passes; preserve raw historical log. No hardware command, connection check, runtime restart or optical/native-output/full scientific acceptance. Evidence: reports/runtime-evidence-2026-10-14/calibration-assets/two-step-context.json and two-step-tests.xml. Restart the app to load the changed paths; remove only this completed TODO and retain rig acceptance.


## 2026-10-14 - Calibration directory contains only two files

- `calibration-directory-only-two-files` completed [gui] [visual_stimulus]: owner requests removal of all extra files alongside the two new calibration patterns. Remove assets/calibration/README.md; earlier generated JSONs/old grid are already removed. Exact directory inventory now consists only of reference_bars.glb and frame_grid.glb, with both SHA-256 hashes unchanged from two-step-context.json. No incoming README links found; whitespace passes. Documentation/file removal only, no runtime test or hardware command. Update current reports and remove only this completed TODO.


## 2026-10-14 - Reference bars visibly presented

- `reference-bars-visible-output` completed [visual_stimulus] [gui]: owner reports absent bars and requests testing/fix. Reproduce black native Front output and two failing bars pipeline regressions (two grid cases pass). V01/V15 defect: bars branch continues after drawing device_fbo without the native-screen copy. Add existing copy operation before continuation; preserve native pixel lengths/correction independence, swaps, deadlines/ownership and cleanup. ARCH-002 needs no new state/dependency/module/process; extend owning behavior tests to verify copy after drawing on every output. Directory still contains only reference_bars.glb/frame_grid.glb.
- Rendering16 pass using workspace basetemp; default sandbox temp run initially has10 passes/six fixture errors. Final rendering/lifecycle/authenticated transport calibration selection22 pass/37 deselections. Scoped Ruff/format2, Win32 mypy1, boundaries689/zero violations and whitespace pass. Initial format findings corrected. Native Computer Use captures verify all four orange/green bar outputs after managed restart; normal GUI Close gives authenticated Idle/resources_closed, reopening gives Active/presented. Old GUI closes during inspection; verify Configuration/closed resources then authenticated graceful ShutdownApplication succeeds, normal hidden managed launcher restores saved draft/control. New controller80dfe14b-7d23-45b0-a46f-eaf77c024b62 left running with reference calibration open for owner measurements. No Setup/recording/camera/firmware action. Native screenshot encoding is lossy JPEG; initial strict color threshold rejects it, corrected approximate analysis verifies colors without claiming exact pixels/optics. UI input race/stale selection/geometry lookup require refresh; use fresh visible coordinates for Close. Preserve these attempts and screenshots with evidence in reports/runtime-evidence-2026-10-14/reference-bars/context.json. Update backend reports and single rig checklist; measured optics/full scientific acceptance remains pending. Remove only this completed TODO.


## 2026-10-14 - Live reference measurement editing and GUI Tab navigation

- `live-reference-measurements-and-tab` completed [gui] [visual_stimulus]: owner wants to enter measured bar distances while projecting and use Tab throughout GUI. G01 revision193/register and calibration contract record editable measured X/Y mm during confirmed Active bars, with retained pixel/mode provenance and other projector locks. Updates remain local draft/derived estimates; no protected rewrite/RPC. Pending/unknown/observer states lock fields, including non-Active Preparing/Closing. Shared DataTable disables cell Tab navigation (standalone probe reproduces five trapped Tabs); Qt now traverses nested widgets normally. Console/details/example views release Tab. Extend owning tests for real key input, forward/reverse focus, disabled skipping, persistence and phase/authority locks. ARCH-002 reuses existing Qt/measurement mechanisms; no event-filter framework/dependency/process/state. Large panel remains view-lock/widget composition.
- Focused7 pass/468 deselections; broader33 pass/one pre-existing incomplete-import KeyError exposes missing geometry at file-limit overlay. Repair using partial geometry/default file limits without inventing surfaces or relaxing Setup. Final selection34 pass/441 deselections; repeat after pending-lock refinement also34 pass/441 deselections. Last run emits COM0x8001010d at Qt fixture construction but continues/exit0 with all cases passing; cause unverified. Correct initial Ruff format/zip findings. Scoped Ruff/format5, Win32 mypy4, boundaries689/zero violations and whitespace/doc references pass. GUI already closed; --reopen-gui in existing controller0768dae0-1b01-4381-9454-156598268931 loads editing/Tab changes. Native Active bars + caret/border screenshots verify FrontX→FrontY→LeftX, ShiftTab→FrontY; no measurement values fabricated/changed. Native test occurs before final pending-only guard, whose transitions remain locally verified. DWM NotResponding ghost in initial inventory gives no hardware/fault conclusion. Accessibility returns empty/stale text, so focus assessed from screenshots. Leave GUI/reference bars open; no backend restart/Setup/recording/MCU/camera mutation. Only two repo calibration GLBs remain. Current evidence: reports/runtime-evidence-2026-10-14/live-reference-tab/context.json. Update reports; remove only completed TODO and preserve rig work.

## 2026-10-14 - Projector updates preserve operator cursor

- `projector-cursor-stability` completed [visual_stimulus] [gui]: owner reports mouse jumping to projectors on updates. GLFW fullscreen creation centers by default; shared native configure_window now disables CENTER_CURSOR after every hint reset. G01 revision194/root register amended; V01/V04 fullscreen ownership and existing RGB/refresh/auto-iconify hints retained. ARCH-002 uses one existing focused operation, no restoration state/dependency/process. Extend owning rendering tests for repeated 8/10-bit creation. Preserve concurrent work.
- Rendering/calibration71 pass; scoped Ruff/format2, Win32 mypy1, boundaries689/zero violations pass. Native normal GUI launch at desktop(497,768), Close(497,784), reopen(497,425) retain exact clicked main-display positions; authenticated states Active/presented, Idle/resources_closed, Active/presented. Current controller6357d396-4246-4bd5-b532-d850712bc8b5, rendererf657c4a2-a212-4bde-9b7a-4d9326c8cfd1; leave bars active for measurement. Earlier graceful runtime shutdown/restart loads fix. Accidental Escape interrupts first UI attempt; stop then resume on explicit owner instruction, discover absent Dashboard and reopen existing generation. Sandbox status stalls; permitted read succeeds and stalled probe interrupted. Correct initial evidence filename overwrite and failed documentation heading patch. Evidence reports/runtime-evidence-2026-10-14/projector-cursor/context.json. No optical/full-workload acceptance; update current reports and remove completed TODO.

## 2026-10-14 - Measured base scaling with extra adjustment

- `measured-base-projection-scale` completed [gui] [visual_stimulus]: owner requests automatic scaling from measured bar distances with Scale as extra adjustment. Inspect shared face_mapping, grid exporter, live update, preview and measured submission: behavior already implements physical screen/image ratios times independent Scale X/Y. Retain the simpler existing operation; no duplicate implementation/state/dependency or automatic resetting of saved corrections. Clarify intent and G01 revision195/register/calibration contract: neutral1, extra1.05 adds5%, no throw/distance requirement, raw bars unchanged during measurement.
- Extend owning affine behavior test for six neutral/extra X/Y and absent/present throw combinations, checking all four physical footprints, grid/submission identity, preview agreement, source preservation/content-addressed idempotence and stale-mode/imported-warp rejection. Initial6 pass; final measurement/affine/live selection11 pass/469 deselections. Scoped Ruff/format2, Win32 mypy1, boundaries689/zero violations with existing cohesion advisories pass; repair initial formatting findings. No functional runtime change/restart/device action/scientific-value changes or native/optical acceptance. Update current reports and evidence reports/runtime-evidence-2026-10-14/measured-base-scale/context.json; remove completed TODO and preserve unrelated work.


## 2026-10-14 - Screen lower edges attached to Bottom

- `bottom-attached-screen-elevation` completed [gui] [visual_stimulus]: owner requests Front/side elevations depend on subject-to-Bottom-screen distance. G01 revision196/V15 revision16/register and calibration contract record lower edges at subject Z minus Bottom distance; physical heights extend upward unchanged. Shared helper replaces tank-height centering and propagates required Bottom distance through diagram, planning preview, prepared geometry and calibration GLB conversion. Invalid Bottom drafts invalidate all planes. Preserve existing dirty work, saved measurements/corrections and source assets.
- ARCH-002 reuses focused owners and existing tests without extra state/dependency/module. Final offscreen GUI25 pass/455 deselections (intermediate20 pass); scoped Ruff/format5, Win32 mypy4, boundaries689/zero violations, documentation reference/anchor and whitespace checks pass. Initial8-pass/2-failure run identifies full-version7 versus numeric-version4 test misuse and missing Bottom distance in old fixture; both corrected. Initial formatting finding corrected. Missing optional conftest/activation-script reads have no implementation consequence; use existing venv Python3.11. Review V15 file settings; retain values since measured geometry/scene depth are not supplied and orthogonality is preserved. No native restart/output/device/optical/full-workload acceptance. Evidence reports/runtime-evidence-2026-10-14/screen-elevation/context.json and tests.xml. Reopen GUI to load fix; preserve outstanding rig work.

## 2026-10-14 - Calibration Close follows the active step

- `calibration-close-button-and-distance-format` completed [gui] [visual_stimulus]: owner requests one-decimal derived distances and Close on the reference button while bars run. Format newly derived projector distance as fixed one-decimal mm; retain reference/mm-per-pixel/mapping precision. Confirmed reference Active gives its button Close and disables projection launch; grid Active gives projection Close and disables reference launch. Route both through existing close signal, guard direct wrong-step/pending/unavailable calls, restore labels only from confirmed state. Unknown active view retains existing projection Close fallback. G01 revision197/register and calibration contract amended; preserve concurrent screen-elevation work.
- ARCH-002 reuses focused formatting/action owners; no extra state/dependency/process or transport change. Initial6-case selection5 pass/one obsolete active-reference-disabled assertion fails; update expectation. Final owning selection13 pass/467 deselections covering decimal artifact, saved roundtrip, both routes/pending guards, measured affine/live/edit locks. Ruff/format3, Win32 mypy2, boundaries689/zero violations with existing cohesion advisories and whitespace pass; fix initial test formatting finding. Current reports and evidence reports/runtime-evidence-2026-10-14/calibration-controls/context.json updated; completed TODO removed. No native GUI restart/output command or optical/full-workload acceptance; reopen GUI to load changes.


## 2026-10-14 - Clean calibration grid and Bottom-height assessment

- `clean-calibration-grid-bottom-fit` [gui] [visual_stimulus]: grid cleanup complete, physical Bottom diagnosis pending owner remeasurement. G01 revision198/V18 revision3/register/calibration contract record neutral solid thin grid, white border and one screen name. Remove rainbow/dashes/cross/dimensions/ruler/tank outline and obsolete glyphs under ARCH-002; retain world phase/physical geometry/measured corrections and protected inputs. GUI relaunch then normal projection action regenerates frame_grid; no source asset rewritten from potentially stale geometry.
- Owning GUI16 pass/464 deselections; scoped Ruff/format3, Win32 mypy2, boundaries689/zero violations, documentation link/anchor and whitespace checks pass. Format one test file. Read-only last generated Bottom profile shows94×126mm,720×1280px and normalized Y span0.919459;37mm/320px bars imply148mm raw height,126/148×1.08 predicts136.08mm. That exceeds126mm configured screen but falls short of166mm tank depth; this is an artifact-based explanation, not proven optical cause. Pure V15 transform maps all four faces' corners to full normalized XY within existing clip limits. Computer Use window inventory finds no CephVR windows; sandbox QSettings/native LOCALAPPDATA are redirected/empty, explicit user runtime file read succeeds. Missing guessed helper paths/glob syntax corrected by focused existing owners. No GUI/device/output action or native acceptance. Owner answers “let me measure again”; no measurement/scale/default changes. Current reports/evidence reports/runtime-evidence-2026-10-14/clean-grid/context.json and tests.xml updated; move this partial task to Next pending remeasurement, preserve other work.


## 2026-10-14 - Frame gaps and Bottom image-axis correction

- `clean-calibration-grid-bottom-fit` software correction completed [gui] [visual_stimulus]: owner clarifies5mm frame separation, Bottom image width126mm/height94mm, and explicitly confirms both front/lower gaps. G01 revision199/V15 revision17/E14 revision210/register/calibration contract amended. Shared corners offset front edges5mm behind Front and wall lower edges5mm above Bottom; rotate Bottom image X toward tank back and Y across tank width while retaining inward normal. Numeric5/full8/review3 swap legacy Bottom dimension fields only; raw bar/native/mapping adjustments and measured plane distances remain. Fixed GUI policy/config version6 declare5mm gap. ARCH-002 reuses focused owners without dependency/module/state/process additions.
- Final GUI38 pass/444 deselections; after adding exact126/94 measured-affine and legacy-review assertions, focused2 pass/480 deselections. Ruff/format7, Win32 mypy6, boundaries689/zero violations, TOML syntax/version6/gap binding, changed links/anchors/registers and whitespace pass. Initial21-pass/7-failure then27-pass/1-failure runs expose old affine version and mirror origin/clearance fixtures; update to new orientation while preserving complete/partial/impossible scenarios. Static object-version comparison repaired; intermediate31 pass. No new physical measurements fabricated or defaults changed. Earlier136.08mm height interpretation is superseded: old image width94 targeted wrong axis; neutral corrected mapping fits126×94, extra scales remain. Clip/tolerance review retains current settings; no rig/device/output/restart/native acceptance. Evidence reports/runtime-evidence-2026-10-14/frame-gaps/context.json and tests.xml. Remove completed task; existing projector-calibration-launch/rig checklist retain physical coverage verification.


## 2026-10-14 - Updated tank and screen plot

- `updated-tank-screen-plot` completed [gui] [visual_stimulus]: user requests plot after geometry correction. Create3200×2100px PNG with3D/top/side views from current screen_corners/resolved_screens under G01/V15, retained120×166×110mm tank/subject60,93,53 and updated Bottom126×94 image axes. Front/lower5mm gap and axis assertions pass; image inspected and side dimension label adjusted to avoid overlap. Retained51mm side distance gives4mm lateral clearance, explicitly labeled;52mm would give5mm with centered94mm cross-span, pending measured confirmation. Preserve settings. Inputs/corners/generator/PNG saved together in reports/runtime-evidence-2026-10-14/tank-screen-plot; no optical/native/runtime/device acceptance.
- Matplotlib unavailable; use installed Pillow for static technical figure. Optional PDF export fails on missing JPEG encoder; remove incomplete optional PDF, regenerate PNG/JSON successfully. Initial report write raises Windows Invalid argument before log/TODO edits; re-read, apply focused patches and finish tracking. Whitespace passes, no unrelated runtime suite. Current reports updated; complete plot task and retain lateral-distance reconciliation.


## 2026-10-14 - Reference calibration includes raw output frames

- `reference-calibration-output-frame` completed [gui] [visual_stimulus]: owner requests frame alignment before measuring bars, then Scale/Offset refinement. Clarify initial output frame needs resolution only and cannot establish physical screen dimensions without measurements; correct earlier broad alignment wording. G01 revision200/V01 revision21/register/calibration contract record raw white2pixel boundary plus unchanged bars, then existing measured physical frame/grid. Shared bounded rectangle helper reused by GLB exporter/native framebuffer; draw colored bars after frame to preserve exact pixel spans. ARCH-002 adds no resource/process/state/dependency or transport/policy setting. Source directory still contains only two GLBs; next normal launch regenerates reference source, no active input rewrite.
- Rendering/resource71 pass; owning GUI15 pass/467 deselections. Ruff/format6, Win32 mypy3, boundaries689/zero violations, changed doc links/anchors/registers and whitespace pass. Initial70-pass/one-failure run identifies old8-vertex asset expectation; update to24vertices/bar slices and preserve length/cleanup coverage. Static format updates4 files. No native restart/output/device/optical acceptance; normal application restart loads renderer source. Current reports/evidence reports/runtime-evidence-2026-10-14/reference-frame/context.json and XMLs updated; completed TODO removed. Physical alignment/coverage remains under existing rig checks.

## 2026-10-14 - SpikeGLX connection check

- `spikeglx-connection-test` completed [controller] [spikeglx]: owner requests connection test. Existing controller-owned read-only E12 diagnostic succeeds at11:31JST on169.254.240.108:4142; SpikeGLXv20251218/api4.1.3, idle running=false/saving=false, retained name test, directory C:/SGL_DATA. Exact controller generation/source revision/method/result retained in reports/runtime-evidence-2026-10-14/spikeglx-connection/result.json with script; current runtime report updated. No lease/configuration/recording/start/stop mutation; temporary CLI credential removed.
- Initial sandbox TCP attempt returns10013 access denied, not remote failure; permitted authenticated RPC succeeds. Navigation reads include missing guessed paths, corrected by file discovery. No code change or runtime test suite required; whitespace check follows. Connection/status passes do not establish pulse wiring, recording, synchronization or paired lifecycle acceptance; preserve rig checklist and concurrent work.

## 2026-10-14 - GUI SpikeGLX Test connection routing

- `spikeglx-gui-connection-test` completed [gui] [controller] [spikeglx]: owner requests GUI test and supplies REVIEW/no hardware command screenshot. Source confirms editing-control branch swallows diagnostic intent. Under G01/E12 route enabled Test connection first through existing signal/controller RPC; disconnected/sample remain disabled and endpoint read-only. ARCH-002 adds no state/dependency/process and retains existing HUD/result handler. No architecture amendment needed for restoring accepted behavior; native open GUI must be reopened to load fix.
- Owning GUI SpikeGLX13 pass/472 deselected with permitted local sockets; focused holder/observer2 pass/483 deselected. Initial holder assertion wrongly required endpoint widget disabled; correct to read-only invariant. Initial broad sandbox run errors/fails and stalls without summary; interrupt and rerun with explicit basetemp/permitted transport successfully. Ruff/format2, Win32 mypy1 and boundaries689/zero violations pass with existing cohesion advisories; whitespace check follows. Current report updated; preserve concurrent work. No native GUI restart/click or recording/pulse/paired acceptance claimed.

## 2026-10-14 - GUI per-session SpikeGLX pairing

- `spikeglx-gui-pairing-control` completed [gui] [controller] [spikeglx]: owner cannot enable pairing; screenshot establishes successful native GUI diagnostic, idle running/saving=false. Replace read-only pairing presentation with controller-confirmed per-session synchronization flag updates in Configuration with control. Reuse existing configuration lock/UpdateConfiguration/revision/lease checks; block pending repeats and restore confirmed state on rejection/disconnection. No SDK/start/stop/host-file mutation. G01 revision202/root register amended; E12 session participation unchanged. Native GUI must reopen to load fix.
- ARCH-002 reuses focused display/device owners; generalize existing camera acceptance signal/operation to device acceptance to preserve other local drafts after confirmed pairing revisions. Owning tests cover flag-only proposal, rejection/stale revision/wrong phase, queue rejection, pending/authority gates and accepted revision. Final related GUI30 pass/460 deselected, intermediate17 pass/472 deselected. Initial restricted focused run stalls after two passes, interrupted; permitted socket/native inventory runs pass. Ruff/format8, Win32 mypy7, boundaries689/zero violations with existing cohesion advisories pass. Repair one failed patch context before applying; avoid guessed missing navigation paths after discovery. Current report and reports/runtime-evidence-2026-10-14/spikeglx-connection/pairing-validation.json retain results; whitespace/reference check follows. No native restart/click, paired session recording or pulse acceptance claimed; preserve concurrent work.

## 2026-10-14 - SpikeGLX table remove-button formatting

- `spikeglx-table-remove-format` completed [gui] [spikeglx]: owner reports wrongly formatted table crosses. Padded compact buttons exceed40pixel column after shared insets. Reuse icon role/fixed26x26/centered cell alignment and50pixel column including shared12pixel padding; preserve custom deletion and observer/configuration authority. G02 revision39/root register amended. ARCH-002 reuses focused owners without new state/helper/dependency. No new runtime suite for a reversible appearance change.
- Ruff/format1, Win32 mypy1, boundaries689/zero violations with existing cohesion advisories pass. Isolated themed1220x720 panel visually inspected: both crosses visible/centered/contained; exact26x26 and deletion/observer probes pass. Initial offscreen automatic font discovery renders boxes both restricted/permitted; explicit installed Segoe UI application-font load fixes it. Failed multi-file patch contexts corrected before applying. Preserve render/script/context at reports/runtime-evidence-2026-10-14/spikeglx-table-buttons; update current report and finish task. Native open GUI not restarted; reopen to load. Whitespace/register checks follow; preserve concurrent work.


## 2026-10-14 - Pixel valid-area Width and Height replace Scale

- `projection-valid-area-dimensions` completed [gui] [visual_stimulus]: owner explicitly selects pixel dimensions and crop preserving measured mm/px. Replace Scale controls with Width/Height plus centered pixel Offset. Fixed-pitch affine mapping/edge UV clipping preserve physical coordinates; size changes crop, Offset translates without resize. Optional normalized geometric-profile valid_area is shared by preview, grid outline/live updates, prepared scene rendering and Idle union; independent V22 marker/raw bars retain their ordering. Numeric6/full9/review4 migrate old Scale bounds, preserve Bottom axes/native measurements and reject insufficient non-neutral migrations before widget restoration. G01 amendment201 retained concurrent202 pairing work; V01 revision22/V15 revision18/V19 revision7/register/contracts/schema updated. No wire fields/policy/timing/numeric projection settings changed.
- ARCH-002 reuses focused owners with pure affine clipping/output-mask helpers; no dependency/process/whole-runtime reference. Existing oversized Projectors/native/scene owners remain cohesive with new separable logic in helpers. Final GUI34 pass/456 deselections; rendering/config81 pass; calibration control12 pass/41 deselections with permitted loopback. Additional exact legacy crop/raw-bar/missing-mode atomic rejection1 and final float32-collapse-guard16 proofs pass. Ruff, Win32 mypy162, format167 before final formatted increments, boundaries689/zero violations and11-schema consistency pass; regenerate only geometric-profile schema. Initial stale Scale/vertex/asset/legacy fixtures, strict tuple, variable collision, missing helper/insertion lookups, import lint and UV floating endpoints corrected; evidence retains attempts. Sandbox controller/lifecycle run stalls, interrupted; permitted rerun succeeds, no assertions weakened. No native runtime restart/device/optical/scientific acceptance; restart app to use changes. Current reports consolidated obsolete Scale assessment into historical evidence link; reports/runtime-evidence-2026-10-14/valid-area/context.json/XMLs record scope. Remove only completed TODO, preserve concurrent SpikeGLX and rig tasks.

## 2026-10-14 - Quiet MCU diagnostic polling

- `mcu-test-console-polling` completed [gui]: owner reports repeated Test messages. Source identifies normal500ms STATUS/lease renewal under A11, not repeated START. Keep live HUD/counts and firmware lease; console emits start/stop lifecycle evidence and suppresses successful routine STATUS completions in device/dashboard logs. Preserve failure, connection, upload and explicit-command messages. No hardware/firmware/protocol/timing mutation; reopen GUI to load fix.
- ARCH-002 reuses focused ManagedMcu pending command kind and existing panel/result routing; no dependency/process/runtime reference or separable new responsibility. Extend owning dashboard test for seven quiet polls, exactly one START, camera count updates, stop and failure visibility. Focused offscreen pytest2 pass/488 deselected. Broader MCU selection collection fails twice after concurrent projector_calibration.py becomes zero bytes, missing CalibrationTable; preserve unrelated work and claim no broader pass. Ruff/format4, Win32 mypy3 and boundaries690/zero violations with existing cohesion advisories pass; initial import-order/format findings repaired. Missing guessed tests/gui/conftest.py corrected through existing fixture discovery. Current runtime report updated; whitespace check completes handoff. No native/device/physical acceptance; rig deferrals retained.

## 2026-10-14 - Eye preview readback trigger mismatch

- `eye-preview-readback-mismatch` completed [acquisition] [controller]: owner requests diagnosis/fix for screenshot failure. Source isolates missing Eye role in ManualPreview._external_roles; acquisition omits pulse evidence/activation while controller expects external-trigger readback. Real resolver regression reproduces exact outstanding-batch error for Eye, with Behavioral/Tracking passing. Add missing role under A10/E07; preserve identity/revision/deadline checks and existing pulse ownership. ARCH-002 one-line selection correction within existing orchestration; no new state/dependency/process or separable responsibility. Existing behavior modules cover three-role confirmation and Eye start/existing selection, stopped/running and free/external cases.
- Final focused integration165 pass/one Windows deselection; Ruff lint/format3, Win32 mypy1, boundaries690/zero violations with existing cohesion advisories, whitespace pass. Initial TODO patch fails due pre-existing invalid UTF-8; preserve bytes for tracking. Sandbox temp creation fails then asyncio run stalls/interrupted; permitted local tests succeed. Initial test ControlState method mistake and intermediate missing Any import corrected; before.xml retains exact-error reproduction and after.xml retains161-pass/4 test-only failures. Reports/runtime and acquisition updated with context.json/before/final XML provenance; source baseffa3edef plus dirty concurrent work. No live command identity captured, runtime restart/device/SDK/serial/optical acceptance; full app restart required, rig work remains pending. Preserve unrelated edits and tasks.

## 2026-10-14 - Registry-based preview trigger selection

- `registry-preview-trigger-selection` completed [acquisition]: owner requests flexible inclusion of new cameras after Eye omission. Under A10/E07, reuse CAMERA_NAME_BY_ROLE and the existing pulse-owner selector, with optional pending-start role; remove duplicate ManualPreview selection loop. Registered starting/running external-trigger cameras participate automatically. Unknown/new physical roles still require schema/device/firmware support; no arbitrary camera-count contract or hardware change. ARCH-002 removes duplication and reduces preview orchestration to656 lines, retaining focused peers, ownership, original deadlines and readback checks.
- Expand existing preview behavior test across every registered role and verify test-only registry extension using an existing schema-field alias. Final local acquisition/controller integration174 pass/one Windows deselection; Ruff lint/format3, Win32 mypy2, boundaries690/zero violations with existing reviewed size advisories, evidence JSON/decision-target and whitespace checks pass. Initial run173 pass/one existing two-second integration timeout; isolated two-case recheck and final full selection pass unchanged, cause unverified. Retain all XML/context under reports/runtime-evidence-2026-10-14/registry-preview and update existing reports in place. Guessed camera-control document absent; no governing-source change required. Preserve concurrent tasks/edits. No runtime restart/device/SDK/serial/optical acceptance; full app restart needed, rig work remains pending.


## 2026-10-14 - Integer usable pixels and coherent physical views

- `projection-integer-physical-views` completed [gui] [visual_stimulus]: owner requests integer Width/Height, visible one-pixel arrows, Offset removal and usable-pixel/mm-per-pixel authority for textures/views. Use Qt integer validator and existing user-edit path; remove Offset controls, numeric7/full10/review5 migrate obsolete offsets and fractional crops without changing raw measurements. Focused extent helper supplies centered usable physical corners and fixed-pitch affine mappings to preview/calibration/preparation. Prepared GUI affine surface targets use valid pixel resolution; existing V14 physical texture coordinates retain sizes/frequencies/shared phase across different resolutions/pitches. Live diagnostics retain protected-scene cropping at fixed pitch until fresh preparation. G01 revision203/V15 revision19/root register/contracts/current reports updated; projection numeric settings, imported warp ownership and runtime wire/policy/lifecycle retained.
- ARCH-002 reuses focused owners/Qt/coordinate and allocation machinery, no dependencies or runtime back-references. Final GUI48 pass/445 excluded, rendering/config82 pass including allocation/imported-target proof and cross-projector anisotropic pitch/off-axis/20×10 mm texture behavior. Ruff, format160, Win32 mypy158, boundaries690/zero violations (existing cohesion advisories), diff whitespace pass. Initial Qt default failures, stalled broader restricted calibration selection interrupted, UTF-8 source write failure/recovery, overbroad numeric restore conversion and obsolete/strict-tuple/cleanup fixtures corrected and verified. Evidence reports/runtime-evidence-2026-10-14/integer-views retains XML/context. No native runtime restart/hardware/optical/scientific acceptance; reopen app to load. Preserve concurrent work and outstanding lateral-distance/rig tasks; remove completed TODO only.


## 2026-10-14 - Integer usable pixels and coherent physical views

- `projection-integer-physical-views` completed [gui] [visual_stimulus]: owner requests integer Width/Height, visible one-pixel arrows, Offset removal and usable-pixel/mm-per-pixel authority for textures/views. Use Qt integer validator/existing user-edit path; numeric7/full10/review5 migrate obsolete offsets/fractional crops without changing raw measurements. Focused extent helper supplies centered usable physical corners and fixed-pitch mappings to preview/calibration/preparation. Prepared GUI affine targets use valid pixel resolution; V14 physical texture sizes/frequencies/shared phase retain meaning across different resolutions/pitches. Live diagnostics retain protected-scene cropping at fixed pitch until fresh preparation. G01 revision203/V15 revision19/register/contracts/current reports updated; projection numeric settings, imported ownership and runtime wire/policy/lifecycle retained.
- ARCH-002 reuses Qt/focused owners/coordinate/allocation machinery, no dependencies or runtime back-references. GUI48 pass/445 excluded, rendering/config82 pass including allocation/imported-target and cross-projector anisotropic pitch/off-axis/20 by 10 mm texture proofs. Ruff, format160, Win32 mypy158, boundaries690/zero violations (existing cohesion advisories), diff whitespace pass. Initial Qt failures, stalled broader restricted calibration selection interrupted, UTF-8 write failure/recovery, overbroad numeric restore conversion and obsolete/strict-tuple/cleanup fixtures corrected and verified. Evidence reports/runtime-evidence-2026-10-14/integer-views retains XML/context. No native restart/hardware/optical/scientific acceptance; reopen app to load. Preserve concurrent work and outstanding lateral-distance/rig tasks; remove completed TODO only.


## 2026-10-14 - Integer usable pixels and coherent physical views

- `projection-integer-physical-views` completed [gui] [visual_stimulus]: owner requests integer Width/Height, visible one-pixel arrows, Offset removal and usable-pixel/mm-per-pixel authority for textures/views. Qt integer validator/existing edit path; numeric7/full10/review5 migrate offsets/fractional crops without changing raw measurements. Focused extent helper supplies centered usable physical corners and fixed-pitch mappings to preview/calibration/preparation. Prepared GUI affine targets use valid pixel resolution; V14 physical texture sizes/frequencies/shared phase retain meaning across different resolutions/pitches. Live diagnostics retain protected-scene cropping at fixed pitch until fresh preparation. G01 revision203/V15 revision19/register/contracts/current reports updated; projection numeric settings, imported ownership and runtime wire/policy/lifecycle retained.
- ARCH-002 reuses Qt/focused owners/coordinate/allocation machinery, no dependencies/runtime back-references. GUI48 pass/445 excluded, rendering/config82 pass including allocation/imported-target and cross-projector anisotropic pitch/off-axis/20 by 10 mm texture proofs. Ruff, format160, Win32 mypy158, boundaries690/zero violations (existing cohesion advisories), diff whitespace pass. Initial Qt failures, stalled broader restricted selection interrupted, UTF-8 write failure/recovery, numeric restore conversion and obsolete/strict-tuple/cleanup fixtures corrected/verified. Preserve existing Markdown encodings during record updates. Evidence reports/runtime-evidence-2026-10-14/integer-views retains XML/context. No native restart/hardware/optical/scientific acceptance; reopen app to load. Preserve concurrent work and outstanding lateral-distance/rig tasks; remove completed TODO only.

- Correction [gui] [visual_stimulus]: the preceding three same-title records describe one completed increment; retries after encoding errors accidentally appended duplicates. Their validation totals refer to the same final runs, not additional executions.


## 2026-10-14 - Rig timing and buffer audit started

- `rig-timing-buffer-audit` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [spikeglx] [shared]: owner authorizes rig/TODO checks, protocol/backends and measured config adjustment with 20% safety margin; Tracking deferred. Waited for active screen-height chat to finish. Preserve dirty source snapshot and existing work; Luna performs read-only config/checklist audit, parent serializes hardware measurement. No test or hardware pass yet. Evidence reports/runtime-evidence-2026-10-14/rig-timing-audit.


## 2026-10-14 - Rig recording baseline and regression findings

- `rig-timing-buffer-audit` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [spikeglx] [shared]: native/backend run1548pass/6failure/5skip/3error. Correct parent temp-path mistake through resource recheck43pass. Two camera deadline cases pass isolated; renderer Ready fails repeatedly with missing projection fixture under investigation. Delegate corrects stale MCU Eye OFF and renderer resolver fixtures; no production deadlines relaxed. Restricted attempts stall/stop; permitted loopback/native tests progress. Ruff/format906 and Win32 mypy701 pass; boundaries690/zero violations with existing cohesion advisories. Default isolated GUI stalls/stops without result; verbose documented no-faulthandler recheck ongoing.
- Fresh normal-venv launcher activates4 confirmed Idle outputs; earlier wrong package entry and copied-interpreter DLL failures retained. Real unpaired60s Behavior/Tracking-role-camera plus stimulus passes Setup/Start, completed trial/session, seven outputs Closed, NewSession and exact config restoration. Three external counts/full CPU decodes pass. Rendering59.95groups/s; cameras6/26drops, review2342capacity drops remain real defects/acceptance gaps. Setup4.422s, cutoff-to-session-ended321.207ms; no highwater measurement yet or config change. Eye/Tracking backend disabled. SpikeGLX read-only inventory reports existing active test run; no remote action. Raw provenance/source patch/current context retained in reports/runtime-evidence-2026-10-14/rig-timing-audit.


## 2026-10-14 - Rig buffer candidate and native blockers

- `rig-timing-buffer-audit` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [spikeglx] [shared]: full non-Tracking backend/native recheck1557pass/5skip; fixture-only corrections preserve production/identities/deadlines. GUIoffscreen483pass/11fail; four stale fixtures pass focused4. Seven layout assertions retained under focused correction. NativeProtocolhover2 still fail StopIteration with default exceptionhook; activation diagnostic pending. Windows appcapture approval timesout, no visualinspection claimed; documentation read attempts/stalled restrictedprocesses retained.
- Aggregate occupancy run completes/restores but review3312drops versus uninstrumented2342 (method/run variability confounded). Peakqueue10/review3 motivates provisional12/4; retest completes/restores and3 videoscount/decode, but queue1overflow/review2944drops remain. Restore12/4 candidate filebytes. Camera dropped rows include nominal-slot omissions; classify separately in camera-loss-classification.json, correcting earlier queue-only wording. Maxconsumer277.8992ms at30Hz/224.8805ms at60Hz support17frame sharedburst candidate; capacity-bound peaks are censored. File sync/encoderprogress probe added for next generation only.
- CurrentMCUConnect confirmsCOM8 protocol4/cephvr2_uno_4/all3 stopped; obsolete STATUS diagnostic probe fails(no diagnostic active), correctedCONNECT-only/readbackfield probe succeeds. User now authorizes Eye/paired checks, retainsmanualfirmware and defersunsetphotodiode. FirstEye preview after completedrecording exposes acquisitionINVALID_CATALOGUE/heartbeatshutdown and admittedcommandcleanup timeout; exactall-ownedabsence receipt retained. Sourcecompleted-sessioncatalogue retirement hypothesis under focusedregression, exactrejectedkeynotretained. Existing pairedrun test disposable perowner, but pulseinventoryempty/physicalmapping requested. No Eye/paired/optical pass. Evidence reports/runtime-evidence-2026-10-14/rig-timing-audit/fault-context.json and measurement-assessment.json.


## 2026-10-14 - Rig lifecycle faults and measured buffer retest

- `rig-timing-buffer-audit` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [spikeglx] [shared]: completed-session heartbeat fix1562pass/five skips; later race guard6focused. Native layout9/hover2 pass; full native suite stalls after12, exact owned test processes stopped, cause unproven. Offscreen493pass/one stale hidden-variation fixture corrected2focused.
- Temporary17/21 budget rejections expose pre-trial camera CancelSetup and Visual cleanup output-validation defects; exact exit/startup recovery retained. Resource-accounted CPU/GPU budgets with20% margin permit retest completed/restored, three external counts/decodes pass,59.817groups/s and2666reviewcapacity drops remain. Candidate not accepted. Initial suspected stream swap corrected by saved config/process ownership/decoded evidence; no identity defect established.
- Two preview cycles each Eye/Behavior/Tracking-role complete/settings unchanged; later serial watchdog fault recovered with Connect. Three-camera Setup/Start admits then missing lifecycle evidence interrupts and closure unconfirmed; supervisor exact all-owned absence proven. Original settings restoration pending next recovery. User defers physical SpikeGLX mappings; paired/photodiode acceptance and Tracking processing remain deferred. lifecycle-findings.json retains current failures; source fixes/local validation ongoing.


## 2026-10-14 - Native hover evidence and outstanding rig reconciliation

- `native-protocol-hover-tests` [gui]: completed under current scope; actual Windows MouseMove arrives after one processEvents call (12-18ms observed). Scoped event-filter/EventLoop wait preserves actual native input and assertions; two native/default-faulthandler and two offscreen cases pass. No file dialog or production hover change. Remove completed TODO; full native suite exceptionhook stall remains separate.
- `rig-timing-buffer-audit` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [spikeglx] [shared]: reconcile existing MCU/Eye/narrow-layout/failed-Setup tasks with actual Oct14 evidence and lifted capture scope, retaining photodiode/paired mapping and Tracking deferrals. Controlled failed-Setup retest proves output proof repair alone insufficient; native worker cleanup INCOMPLETE_CLEANUP rejection then renderer exit remains. Exact owned absence retained; source terminal-report acknowledgement repair under investigation. No source/hardware pass inferred from local tests.


## 2026-10-14 - Shared failed-Setup proof and fresh three-camera run

- `rig-timing-buffer-audit` [controller] [supervisor] [acquisition] [visual_stimulus] [shared]: preliminary-output registration proposal failed real RegisterContext and was reverted; final reserved registration restored. Controller validates all frozen requested IDs and explicit absence before reservation. Shared Supervisor rule retains only distinct path-free/never-created absence facts in an unpaired unsealed context, after exact native catalogue/fence proof; final outputs/resources remain exact. E08 revision172/register clarify this scope. Local78 affected cases pass; worker Cleanup now confirms accepted delivery within original deadline. Controlled budget recheck no longer reports INCOMPLETE_CLEANUP but CPU preparation failure still becomes a fatal renderer Error; command/process classification repair locally under validation. No native failed-Setup cleanup pass yet.
- Fresh normal three-camera60s trial succeeds Setup/Start, completed session and confirmed cleanup; original settings/Eye enablement restore. Worker frame probes disabled; passive controller event probe preserves full ON/OFF rejection codes and role/watchdog state. All three ON roles applied, keepalives continue; four external videos are under verification. Earlier21ms firmware ON rejection after previews remains separate, not a startup-timeout measurement.


## 2026-10-14 - Three-camera confirmation and reuse faults

- `rig-timing-buffer-audit` [controller] [supervisor] [acquisition] [visual_stimulus] [shared]: final three-camera60s completes/cleans/restores; four external counts/full decodes pass. Queue17 has zero overflows and covers measured burst sizing with20% margin. Camera nominal-slot omissions remain. Visual21 saturates3078capacity drops/3098CFRduplicates, so restore original visual TOML bytes; no sustained throughput acceptance. Corrected sync cadence measured maximum1040.5247ms/errors0.
- Dedicated Save On to Save Off same-generation60s trial completes/cleans/restores; two camera videos count/decode and no stimulus output. Stale canceled keepalive fenced; owning79pass/one skip. Later idle retirement loses exact cleanup evidence after bounded payload expiry: pin current exact successful Cleanup child/lifecycle proof until retirement, full coordinator47pass; native reuse pending. Abort has not dispatched because Setup failed first.
- `renderer-failed-setup-cleanup-link` [visual_stimulus] [controller] [supervisor]: fault4 expected budget Setup rejection still becomes Supervisor shutdown; CancelSetup unconfirmed, candidate restore blocked. Exact generation4a1fc86b-c89f-4cb9-b12b-b760654436a0 all-owned absence receipt retained. Coordinator generic failed-operation promotion is next source investigation. Final backend1534pass/five skips/one authenticated configuration timeout; unchanged isolated2pass, cause unproven.


## 2026-10-14 - Exact cleanup tracing and final GUI verification

- `stimulus-save-switch-cleanup` [visual_stimulus]: completed dedicated native Save On to Save Off trial in same generation, confirmed cleanup/settings restore, two camera full decodes/counts, no stimulus artifact. Remove completed TODO; interruption/fault recovery remains separate.
- `rig-timing-buffer-audit` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [shared]: GUI final offscreen494pass. Ruffpasses; Win32mypy786filespasses; boundaries690zero. Format catches one test indentation, corrected. Real Abort at5.3356403s interrupts but cleanup unconfirmed; three partial videos count/decode, exact owned absence. No original configuration restoration claim after failure.
- `renderer-failed-setup-cleanup-link` [controller] [supervisor] [acquisition] [visual_stimulus]: fix duplicate Setup fatal promotion76tests; fix acquisition CancelSetup missing existing aggregate cleanup71tests. Fault6 bounded macrotrace records both backend admissions/cleanupreports accepted with resources released/outputabsence. A warning scope/revision rejection still loses authority, so aggregate fails despite closure facts. Native end-to-end acceptance remains open.


## 2026-10-14 - Rig audit available-scope completion

- `manual-camera-repeat-admission` [controller] [acquisition] [gui] [shared]: four real preview start/stop cycles each Eye/Behavior/Tracking in one generation (12 total), all completed, configuration unchanged and final devices closed/no preview/no pending cleanup. Remove completed TODO. Physical edge/LOW and GUI selector/DPI acceptance remain separate.
- `rig-timing-buffer-audit` [controller] [supervisor] [acquisition] [visual_stimulus] [shared] [spikeglx] [gui]: accept and persist only camera queue10->17 via typed UpdateConfiguration plus owning TOML; baseline comparison proves other original fields unchanged. Reject Visual21 growth, restore exact original TOML. Normal ShutdownApplication succeeded; exact generation b51cab36-51b9-4a41-bcc1-458fed93fb28 all-owned absence receipt retained.
- Native fault6 both backend cleanup proofs accepted but warning authority loss prevents aggregate pass. Generalize existing one-previous-warning-scope slot with exact session/config revision; E03 revision35/register updated, producer/camera/occurrence validation retained. Interrupted worker accepts only exact retained stopped-trial pulse evidence after readiness is fenced; source152focused pass, native Abort retest pending. Fault9 starts with absent projector and separately rejects budget; prior calibration receipts regress in cleanup, repaired with explicit catalogue retirement and same-key reopen invalidation. FullVisual311pass; no native post-fix projector pass.
- Owner confirms projectors off and defers projector tests. Camera-only trial was rejected before Setup by accepted E10 required Visual participant; original configuration restored. Defer remaining full-session cancellation/Abort/idle300s reuse, timing receipts and visual throughput. Photodiode, physical SpikeGLX mappings/paired acceptance, Tracking processing and manual firmware deferrals remain.
- Exact quarantined fault6 marker/lock preserved/restored within verified workspace paths; recreate only removed empty protocol/spikeglx directories for normal explicit StartupRecovery. Recovery completes administrative marker/report without certifying unknown files/remote stopping. No manual pointer clearing or forced process termination occurred.
- Final source selections: nonVisual1229pass/5skip, Visual311pass, GUI494pass; earlier backend authenticated timeout rechecks2pass and final selection passes, cause unproven. Ruff/format906/mypyWin32786/boundaries690zero pass. Full native GUI exception-hook stall remains unresolved.


## 2026-10-14 - Final configuration and evidence checks

- `rig-timing-buffer-audit` [repo] [controller] [supervisor] [acquisition] [visual_stimulus] [shared] [gui]: parse16 operator/policy TOMLs, parse30 schema JSON objects (formal meta-schema validator unavailable), validate10 new report links, confirm visual config byte-exact original and buffer17 in owning TOML. Generate19 proto sources into isolated owned temporary directory;57 pb2 outputs compare with zero source drift. Generated source untouched. Final-provenance records changed tracked-file hashes and their dirty/untracked/earlier-generation limits.
- Full Visual selection initially310pass/one old automatic-retirement fixture expectation failed; update only that owning fixture to call explicit catalogue retirement, delegated full311pass. Failed log/XML preserved under closing-visual-before-fixture-retirement; final delegated outcome/provenance recorded. Other final backend1229pass/5skip and GUI494pass remain current. Source/resource retirement reviewed under ARCH-002: existing preparation/catalogue owners, no new dependency/process, same-key reopening invalidates receipts; lifecycle609 lines remains cohesive orchestration delegating resource/recording/display/trial owners.


## 2026-10-14 - Owner parameter selections and stimulus budget review

- `rig-timing-buffer-audit` [controller] [acquisition] [visual_stimulus]: owner requests queue20, SDK15 per camera and150ms post-cutoff drain. Initial closed-app update refuses held application guard before any settings mutation; read-only snapshot shows existing application idle Configuration. Authenticated UpdateConfiguration and SaveConfigurationHistory both succeed; owning TOML/default/file-policy loading and saved/current equality verified, all other current fields preserved. No Setup/recording/projector test or restart/shutdown dispatched; application remains open. New20/15/150 values are not native remeasured. A03 revision33/register remove obsolete duplicated numeric defaults, leaving operator TOML authoritative; fixed policy values/version unchanged.
- Recommend retaining10000 metadata-only pending records: normal peak14 does not bound fault backlog. Retain Visual3 slots/256MiB recording CPU/512MiB asset GPU budget; same tested composite CPU accounting133120000bytes,20%159744000; same-assets inferred GPU335054176bytes,20%402065012. Allocation accounting is not a new measurement or whole-process/GPU budget. Slots21 saturated and finite growth cannot establish sustained throughput. Recommendations preserved in owner-parameter-review/recommendations.json; reports/current assessment updated without rewriting measured raw evidence.

## 2026-10-14 - Repository cleanup started

- `repo-unused-cleanup` [repo] [gui]: owner requests unnecessary-file/code cleanup. Reviewed dirty status, GOV-001/ARCH-002, system contracts, G01 and current queue/runtime evidence. Import and symbol searches confirm four retired GUI modules (old BatchEdit and sole EpochTargets dependency, ScreenScope, StimulusSelectionMenu), unused ProjectorLayers state wrapper and top-level shuffle helper have no current callers. Preserve shared/tested authoring helpers, Tracking declarations, generated/native files, application data, recovery outputs and dated evidence. Remove confirmed dead branch with no new dependency or behavior; add root pytest-scratch ignore. Validation and artifact removal in progress.

## 2026-10-14 - Repository cleanup completed

- `repo-unused-cleanup` [repo] [gui]: removed four unused GUI modules plus ProjectorLayers/shuffle helper and obsolete imports (766 lines), preserving current unified G01 editor/shared tested functions and all pre-existing work. Added root pytest-scratch ignore. Containment/reparse-checked PowerShell deletion removed5941 disposable files (114504512bytes,109.2MiB) from old/current pytest fixtures, source bytecode, tool caches and dist; retained environment/native/generated sources, calibration assets, runtime data/recovery/evidence and FFmpeg toolchain.
- Validation: Ruff src/tests/tools passes; GUI format155files/Win32mypy153files pass; boundaries686modules/zero violations, existing cohesive size advisories retained; whitespace passes. Owning editor12tests pass offscreen/no-faulthandler in permitted external scratch. Broad GUI/client and broad editor attempts interrupted after no progress; initial owning fixture retries failed from in-repo asset-generator guard and unwritable default temp, resolved by external writable root without source/assertion changes. No full-suite or rig pass. Current runtime report and dated repo-cleanup.txt record commands/provenance/limits; remove completed queue entry.


## 2026-10-14 - Stimulus recording performance investigation

- combined-recording-loss [visual_stimulus] [shared]: current source review finds repeated full-frame ownership/pipe copies, per-capture PBO allocation/deletion, CPU row normalization and5ms recording-loop polling. Tested2560x2000 RGBA8 at60Hz is20.48MB/frame and1.2288GB/s raw input. Slots21 saturation remains measured; no stage-specific bottleneck or speedup is inferred from source. Prioritize bounded buffer reuse/owned handoff, completion scheduling and isolated conversion/encoder profiling, preserving resolution/precision/rate/accounting/SYS-002. NVIDIA primary documentation supports minimizing unnecessary system/video-memory transfers; direct GPU path remains separate cross-adapter design. No code/hardware changes or new acceptance claimed. Owning report links recording-performance-review.json.


## 2026-10-14 - Projection calibration window controls

- `projection-calibration-window-controls` [gui] [visual_stimulus]: owner requests smaller/cleaner labels, expanding grids, capped sizes, removal of table arrows and capped window offsets. G01 revision204/V15 revision20 and calibration contract now retain integer center-relative X/Y offsets in numeric8/full11/review6. Shared extent/mapping bounds preserve measured pitch; full-native diagnostic grid/views reveal additional lines during expansion and isolate face planes against occlusion. Trial shader disables diagnostic filtering. No dependency/process/protocol/deadline/policy-setting change; existing Projectors composition delegates focused arithmetic/file owners under ARCH-002.
- Local GUI26/persistence11 and renderer73 pass. Ruff/format157/Win32mypy155/boundaries686zero/whitespace pass; existing cohesion advisories remain. Offscreen table730px inspected after loading Segoe UI into otherwise empty offscreen font inventory. Broader GUI/calibration attempts stall and are interrupted; no full-suite/native/optical acceptance. Stale fixture version/extent expectations, numeric8 import routing and type/format findings corrected. Failed Windows encoding write restored GUI architecture byte-exact from pre-edit Codex snapshot1a575e4261ff5c9e23b6577468edd5250842f3af before amendments, preserving existing dirty work. Evidence in reports/runtime-evidence-2026-10-14/window-controls; application not restarted/projectors not commanded. Restart/relaunch needed to load/regenerate; existing rig deferrals remain.

## 2026-10-14 - Full working-tree verification started

- `working-tree-validation` [repo] [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [launcher] [shared]: owner asks to check all changes/tests and update TODO/LOG after repository cleanup. Inventory includes substantial earlier uncommitted backend/GUI/contracts/config/firmware/evidence changes; preserve them. Review current diff plus untracked source/assets, run rig-independent checks with external writable pytest fixtures, distinguish source/static results from pending hardware acceptance. Git cleanliness requires retaining these uncommitted changes unless separately committed; no deletion of evidence or reset is implied.

## 2026-10-14 - Full working-tree review and tests completed

- `working-tree-validation` [repo] [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [launcher] [shared]: reviewed current backend/GUI/firmware/contracts/config/package changes plus untracked source/calibration assets and test changes (29 modules,45 added test functions/eight removed-or-renamed functions checked against replaced behavior). Confirmed G01 planning-preview pixel offsets were omitted; failing owning regression proves mismatch. Fix via existing pure mapping owner; add bounded/unresolved-offset cases in existing dashboard module. Remove accidental projector-value migration from Tracking fixture, update stale125ms fixture to accepted150ms/missing-field check, replace stale demo-manifest link. Initial integration timeout traced to fake status gate ignoring RPC deadline; bound fixture by original remaining deadline, with no production deadline/assertion changes. ARCH-002 adds no dependency/state/process/runtime back-reference.
- Final permitted local backend1670pass/four skip/26native-or-rig deselections, offscreen GUI494pass (no faulthandler), contract90pass; owning configuration72pass/preview3pass. Full lint/format902/Win32mypy782/pip-check/boundaries686zero pass; existing cohesion warnings retained. Parse16TOMLs/30schemaJSONs, check114register status/revision entries, generate19proto/57outputs with zero drift; source distribution and AMD64 Windows wheel build. Initial sandbox asyncio stalls/temp build denial, initial stale-fixture failures and red regression retained beside final evidence. Installed standalone runtime/native/scientific acceptance not inferred; no hardware commands or restart.
- Reconcile current runtime/acquisition reports and TODO with results; preserve known mixed-subgroup/origin/physical/throughput findings and owner rig deferrals. Evidence/provenance in reports/runtime-evidence-2026-10-14/working-tree-validation. Remove disposable build/tool/bytecode artifacts while preserving environment, binaries, calibration assets, operator/runtime/recovery files and all earlier uncommitted work. Git working tree intentionally remains uncommitted; no reset/delete-evidence/commit performed.

## 2026-10-14 - Reviewed changes committed

- `working-tree-validation` [repo] [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [launcher] [shared]: owner explicitly authorized committing the completed work. Confirmed no source/contract/config drift from the validated snapshot, staged reviewed changes plus tests, docs, calibration sources and retained raw evidence, and created the commit. Post-commit Git status was clean. This supersedes the earlier handback's uncommitted status; 2,254 passing checks, four skips and outstanding native/rig deferrals retain their recorded scope. Include this outcome in the same commit; no push or hardware action.
- `rig-projector-display-availability` completed [gui] [launcher] [controller] [supervisor] [visual_stimulus]: owner powers on projectors; native inventory enumerates operator monitor plus four saved DLP identities at 60Hz. Repeated owner-approved E08 full replacement via the exact event/exit-confirmation path; fresh controller 87ca3771-29f3-41db-bfdc-31ec13491f0f reaches Configuration/revision 1, no startup modal; renderer reports four resources-ready outputs, applied revision 1, Idle. Session 73592 left open.
- Evidence: reports/runtime-evidence-2026-10-14/gui-refresh/projectors-on-before.json, projectors-on-after.json, projectors-on-context.json. Verifies saved GUI restoration/display initialization only, not calibration, optical timing or experiment acceptance. No Setup/Start/capture/firmware.

## 2026-10-14 - Projector calibration source review

- Read-only source review of projector calibration (measurement/geometry/profile, live update, controller admission, renderer, panel); one `face_mapping` probe confirms undershoot rejection and manual scale compounding on measured scale. No runtime/optical/rig run; no code changed.
- New findings [gui] [visual_stimulus] [controller]: `projector-calibration-dpi-binding` (Qt-logical vs GLFW-physical), `projector-calibration-late-open-recovery` (UNKNOWN after late-completing timed-out Open; source trace only), `projector-calibration-live-feedback` (silent live-update failures). Approach limits (affine-only, 25 % centre bars, widget-only state) recorded for owner decision in reports/visual_stimulus.md. Mixed-pacing failure in `projector-calibration-launch` predates the builder; regenerate the bundle.

## 2026-10-14 - Dev-machine triage of Oct13 rig findings; two local repairs

- `dev-machine-rig-triage` completed [gui] [controller] [repo]: baseline at `ffa3ede` (Python 3.11.15, PyQt6 6.11.0 offscreen): tests/gui 464 pass/0 failures; other owners 1608 pass, 6 skips, 3 failures. `devices-narrow-overflow` does not reproduce here (needs native Windows measurement).
- `mixed-subgroup-random-rule-edit` completed [gui]: reproduced; `SubgroupEditor.apply` now rejects a rule change across more than one batch identity ("Select one subgroup to change its variation rules"), draft stays dirty (G01/V03/V08, GOV-001). Subgroup test extended (6 pass; fails without fix); Ruff/format, Win32 mypy 156, boundaries 686/zero violations pass.
- [controller] stale fixture repaired: three tests/client/test_controller_rpc.py cases failed (`_install_microcontroller` lacked `eye_tracking` stopped); 15 pass. Not rig evidence.
- Not locally closable: `physical-surface-coordinate-origin` (owner contract choice), `combined-recording-loss`, `stimulus-save-switch-cleanup`, Protocol hover/pytest-hook, native picker items (Windows/GPU/camera), `projector-calibration-retention`. No device/rig/runtime/firmware action.

## 2026-10-14 - Projector calibration reworked to independent edge margins

- `projector-calibration-dpi-binding`, `projector-calibration-late-open-recovery` and `projector-calibration-live-feedback` completed [gui] [visual_stimulus] [controller]: owner approves the workflow. G01 revision183/V01 revision19: each face's valid area is output minus four pixel margins (blank = automatic from measurement, else projector border), replacing scale/offset; calibration file version5/full8 converts older files; reference view adds output frame, ticks, screen-aspect guide; seam_check view and per-projector launch added.
- Repairs: native interface binding with adapter-name match; late Open released without touching renderer; live edits report working/applied/rejected; atomic diagnostic writes; negative scissor fix. ARCH-002: no new dependency; launch helpers in `gui/projector_launch.py`.
- Evidence (macOS offscreen, no native/optical run): tests 2089 passed/6 skipped/8 deselected, Ruff/format, Win32 mypy 782, 11 schemas, boundaries 687/zero violations. Not done: 59.94 Hz GLFW rounding, pruning old reference_*.json, `projector-calibration-retention` cause (not reproduced), perspective/keystone.

## 2026-10-14 - Calibration asset pruning tool

- [gui]: owner asks to clean the Protocol Assets folder; it is on the Windows rig, unreachable here. Added `cephvr.gui.calibration_assets`: lists, and with `--apply` deletes, superseded `calibration/reference_<face>_<sha256>.json`, keeping files named in saved GUI JSON (config/runtime_gui.json, review_draft.json) and the newest three per face; other files never touched. One test covers retention, dry run, non-hash names, missing folder; Ruff, Win32 mypy, format pass. Not run on the rig; owner runs dry run first. A profile not named in saved files is protected only by the newest-three rule.

## 2026-10-14 - Surface-local origin decided: centre (V14 revision 4)

- `physical-surface-coordinate-origin` completed [visual_stimulus]: owner keeps the renderer and changes the contract. V14 revision 4 and root register: a 2D physical surface's local origin is its centre (right/up, edges ±extent/2); stimulus-schema.md and reports/visual_stimulus.md updated. No code change; maps authored bottom-left must be regenerated in the owner's redo.
- One regression in tests/visual_stimulus/test_rendering.py pins the convention. 72 rendering/compilation cases and 26 contract/link/spin selections pass; Ruff/format, whitespace pass. No rig or optical validation.

## 2026-10-14 - Post hoc alignment compatibility review

- `posthoc-alignment-review` completed [acquisition] [tracking] [visual_stimulus] [spikeglx]: reviewed CephVR1 guide/source at `914ecbc`, CephVR2 output contracts/writers, reports and SpikeGLX sync-edge docs. Assessment in reports/runtime.md: version/marker incompatibility, pulse-anchor ambiguity, padded-video source joins, per-output optical limits, separate probe clock mapping. Performance proposals unbenchmarked.
- Recommendations (shared alignment core, versioned adapters, timing quality, metadata reuse, evidence/review-video separation, stronger anchors) are proposals, not accepted E13/V22 amendments. No code, tests or rig action; offline implementation deferred. Documentation anchor/whitespace checks pass.

## 2026-10-14 - CephVR1 review-video comparison for recording loss

- `combined-recording-loss` [visual_stimulus] [acquisition]: read-only comparison with CephVR1 (`914ecbc`) against V12/E13, `recording/capture*.py`, `rendering/capture.py`, `config/backends/visual_stimulus_config.toml` and Oct13 combined evidence (`context.json`, `profile-cpu.json`, `profile-gpu-utilization.csv`).
- Findings (no profiling/rig run): stimulus-only 60 s keeps 3423 captures/8 drops; combined keeps 1176/2367, so loss is load-dependent. Composite 2560x2000 RGBA (20.5 MB/frame) to yuv444p h264_nvenc vs CephVR1 1920x1080 bgr24 to yuv420p constqp. `capture_slots=3` vs `recording_bytes_total` (256 MiB, about 12 frames); two GL-thread copies per frame; CephVR1 used worker PBO readback (0.999 written/rendered). Profile sample: FFmpeg 1.25 cores, GPU1 encoder 60%, CPU mostly idle. Cause unproven. Recorded as hypotheses in TODO; nothing changed.
- Refs: V13, `_recording.py`, `reconstruct_vr_video.py`

## 2026-10-14 - Raw alignment evidence scope clarified

- `posthoc-alignment-review` follow-up [acquisition] [tracking] [visual_stimulus] [spikeglx]: owner will implement the compiler separately; scope narrowed to acquisition-time evidence gaps: A07 camera-log/video coupling vs independent T14 saving, E13 evidence/video coupling, optional camera native metadata, no dedicated/required Eye pulse role. Limitations in runtime report; no policy change or implementation. Paired/optical TODOs stay open. Source review and whitespace check only.

## 2026-10-14 - Keystone warp for projector calibration

- `projector-keystone-warp` completed [gui] [visual_stimulus] [controller]: owner approves. G01 revision184/V01 revision20: signed Keystone H / V pixel fields per face narrow the margin rectangle; screen maps onto the convex quadrilateral by projective transform, tessellated into a 17×17 grid shared by profile export, submit path and live update (`projective_mesh`, `LIVE_ADJUSTABLE_VIEWS`, same four-corner message, validation relaxed to convex quadrilateral). Calibration file version6/full9; older files load without keystone. A 2×2 triangle pair rejected (cannot represent projective map).
- ARCH-002: no new dependency/process. Local (macOS offscreen): tests 2099 passed/6 skipped, Ruff/format, Win32 mypy 783, schemas without drift, boundaries 688/zero violations. Piecewise-affine error 0.13/0.29/0.69/2.1 px for 5/10/20/40 % narrowing at 2560 px. Not verified: real keystone removal and sign convention on rig/Bottom fold; lens distortion, depth, skew/roll not modeled.

## 2026-10-14 - Recording-loss comparison results and solution tasks

- `combined-recording-loss` [visual_stimulus] [acquisition]: owner asks to record the CephVR1 comparison and set fixes as TODO. Results (source/evidence reading, no profiling/rig): stimulus-only 60 s 3423 captures/8 drops; combined 1176/2367 (Oct13 `context.json`), load-dependent. Current 2560x2000 RGBA (20.5 MB/frame), yuv444p; CephVR1 1920x1080 bgr24 yuv420p constqp (6.2 MB/frame), six PBO slots plus eight-frame queue, 0.999 written/rendered. `capture_slots=3` vs 256 MiB (about 12 frames); two GL-thread copies. Profile: FFmpeg 1.25 cores, GPU1 encoder 60%, CPU idle; cause unproven. V13 deferred.
- Added TODO proposals: `stimulus-encode-benchmark` (measure first), `stimulus-capture-slots-trial`, `stimulus-review-encoding-cost` (needs owner fidelity approval), `stimulus-readback-off-gl-thread`. No decision, config, source or deferral changed.

## 2026-10-14 - Encoder fidelity clarification

- [acquisition] [visual_stimulus]: owner withdraws strict losslessness, accepts lossy compression with minimal loss, keeps source-resolution preference. CephVR1 (`914ecbc`) defaults: h264_nvenc, p4, constqp QP18, bgr24 in, yuv420p out (overridable; not evidence of an actual session command). CephVR2 camera defaults VBR/CQ18/yuv444p; QP and CQ differ. CQ16 suggested as trial candidate only, not accepted or measured. Benchmark TODOs pending; no config, architecture, runtime change or rig validation.

## 2026-10-14 - Always-save scientific evidence accepted; trigger-anchor explanation

- `always-save-scientific-evidence` [acquisition] [visual_stimulus] [controller] [gui]: owner accepts always saving camera metadata and stimulus scientific data/metadata. A07 revision62/E13 revision22 and root register; optional video and trial-only scope retained. Design acceptance only; dependent contract/schema/policy/GUI/runtime work pending in TODO.
- [acquisition] [spikeglx]: reviewed native_metadata adapter (ChunkFramecounter/GetBlockID; no trigger-input chunk) and Basler Data Chunks/Line Source docs. Recommend checking per-model trigger-input-counter capability plus a known counter origin with pulses inhibited; exposure-active/coded timing remain conditional alternatives. Device support, latching and electrical timing unverified. No device/runtime commands; decision/link/whitespace checks pass.

## 2026-10-14 - Per-source recording quality settings

- `encoding-quality-defaults` completed [acquisition] [visual_stimulus]: owner selects standard CQ16/p4, Behavior color 4:4:4, Tracking mono, Eye/Stimulus mono with temporary CQ23 test overrides. Dimensions and camera precision kept; saved configs and device/PFS settings untouched. Existing scale/format grammar used (gray then neutral-chroma yuv420p); no new abstraction (ARCH-002). Stimulus argument list added. E13 revision23; policy version12 and loader fingerprint synchronized.
- Validation: tests/acquisition/test_configuration.py, tests/acquisition/test_recording_filter_expressions.py, tests/visual_stimulus/test_configuration.py: 34 passed. Four lists parse via production filter validation; TOML versions match. Ruff/format, Win32 mypy, boundaries 688/zero violations pass. No local ffmpeg; no encode, quality, size or throughput result claimed. Owner evaluates CQ23 later; review-encoding task updated (dimensions preserved, supersedes downscale suggestion).

## 2026-10-14 - Rig camera trigger-anchor capabilities checked

- [acquisition] [spikeglx]: Oct13 readback serials match acA4112-30uc Behavior and a2A2464-77umPRO Tracking (Behavior PFS model name rejected as identity). Basler docs: ExposureActive on both, acquired-image CounterValue for Behavior, configurable counters for Tracking. No dedicated Behavior incoming-trigger counter can be claimed (document naming inconsistency). Baseline has both CounterValue chunks disabled; adapter does not read it. Eye disabled/unconfirmed.
- Candidate ExposureActive-plus-known-counter-origin and simpler Tracking input-edge counter recorded in reports/acquisition.md; paired integration TODO extended. Evidence: reports/runtime-evidence-2026-10-14/camera-anchor-capabilities/context.json. Documentation/JSON/whitespace checks pass; no hardware, settings or runtime action.

## 2026-10-14 - Encoding tests queued

- `stimulus-review-encoding-cost` [acquisition] [visual_stimulus]: owner requests logging and TODO encoding tests. Existing task expanded: all four sources, CQ16/CQ23 where applicable, effective settings and decoded representation, visual detail, size/bitrate, throughput and drops/padding separately and under combined load; dated evidence and owner evaluation required. Rig benchmark and Eye deferrals remain. Documentation-only; link and whitespace checks pass; no encoding tests executed.

## 2026-10-14 - Development-machine drop-reduction review

- `combined-recording-loss` [visual_stimulus] [acquisition]: source review confirms duplicate readback handoff copy, per-frame PBO allocation/deletion and recording-thread row flip. Proposes first explicit owned-buffer transfer plus bounded stage/queue timing and ownership/backpressure tests; PBO reuse and CPU row-flip removal are later candidates needing GL/ABI checks; shared-context readback contingent on rig evidence. Mono output still gets four-byte RGBA capture. No performance gain established. Assessment in visual_stimulus report; tasks stay open; documentation references and whitespace checked.

## 2026-10-14 - Camera anchor selection narrowed to unchanged wiring

- [acquisition] [spikeglx]: owner first selects ExposureActive, then rejects wiring changes. Superseded by existing-wiring-only A09 revision14/A10 revision60 and root register; ExposureActive contract/checklist drafts removed. A07/E13 always-save decisions unchanged.
- `camera-no-wiring-anchor` added to TODO with one rig checklist: confirm native timestamp/counter capability and evaluate input-edge counter or distinctive trigger-interval matching; both candidates, altered cadence/pre-roll/firmware/reset not accepted. Acquired-image counters alone cannot give a unique pulse offset after unknown leading loss. No live test, wiring, config or runtime change; link/anchor/revision/whitespace checks pass.

## 2026-10-14 - Simple assumed camera anchor selected

- `camera-no-wiring-anchor` [acquisition] [spikeglx]: owner chooses first trigger during recording = first video frame for now, revisited only if issues appear. A09 revision15/register and camera-clock contract record it as an explicit assumption; frame zero joined to its actual source, padding/dropped sources not rewritten; metadata-only analogue uses first received source. Stronger anchor strategies deferred.
- Acquisition assessment, TODO and rig checklist updated to baseline consistency checks. No camera, firmware, runtime or compiler change; no independent physical anchor claimed. Link/anchor/revision/whitespace checks pass.

## 2026-10-14 - Local recording improvements and half-size review capture

- `stimulus-local-recording-improvements` completed [visual_stimulus]: owner authorizes priorities 1-3 and half width/height review video. Explicit bytearray ownership transfer across native readback/session/worker (borrowed buffers keep defensive copy); bounded stage timing/slot diagnostics in a focused metrics module, JSON aggregate on recording-thread exit; stale-reservation validation fixed.
- E13 revision24/V12 revision12: file-owned review_scale_factor 2 divides tile size before readback (2560x2000 becomes 1280x1000, 5.12 MB vs 20.48 MB RGBA). Additive Protobuf field, 19 sources regenerated, policy13/fingerprint synchronized; CQ settings unchanged.
- Tests: `.venv/bin/python -m pytest tests/visual_stimulus -q -m "not windows and not rig"` 310 passed/1 deselected (initial sandbox 300 passed/9 socket-bind failures; loopback subset 15 passed). Ruff/format 167 files, Win32 mypy 151, boundaries 689/zero violations. No GPU encode, benchmark or rig drop reduction measured.
- TODOs and rig checklist updated; PBO pooling, row-flip, shared-context readback await rig measurements.

## 2026-10-14 - Always-saved scientific evidence implementation started

- `always-save-scientific-evidence` [acquisition] [visual_stimulus] [controller] [gui]: owner authorizes implementation under A07/E13. Preserve wiring, trigger cadence, trial boundaries and assumed camera anchor. ARCH-002 selects existing bounded recording owners with optional video resources; no compiler or extra capture process.

## 2026-10-14 - Recording improvement review and diagnostic repairs

- `stimulus-recording-review` completed [visual_stimulus]: reviewed owned-buffer handoff, reservation checks, metrics and half-size flow (V12/E13/ARCH-002). Fixed: INFO summary silently suppressed by renderer logging (one dedicated stderr INFO handler at worker startup, pure JSON event); invalid encoder write counts could inflate submitted-byte metrics (validate first). No other ownership/scaling defects.
- Regressions added. `.venv/bin/python -m pytest tests/visual_stimulus -q -m "not windows and not rig"`: 313 passed/1 deselected (loopback permitted); Ruff/format 167 files, Win32 mypy 151, boundaries 689/zero violations. No native stderr/FFmpeg/GPU/throughput validation; rig checklist verifies renderer stderr summaries.

## 2026-10-14 - Always-saved scientific evidence implemented

- `always-save-scientific-evidence` completed [acquisition] [visual_stimulus] [controller] [gui]: A07/E13 camera metadata and stimulus recipe/evidence saved independent of video; output reservations, fault scopes, lifecycle validation include metadata-only trials. Camera video off skips discovery/conversion/pixel pools; stimulus video off skips capture/readback/encoder. Wiring, cadence, E11 cutoffs and first-trigger anchor preserved.
- Frame-log schema4 (video.enabled, video_disabled rows); stimulus format5 (video_enabled). Policy bindings acquisition21/Visual Stimulus14, schema/Protobuf regenerated; GUI explains required recording; feedback hold closure fixed.
- `.venv/bin/python -m pytest tests/acquisition tests/visual_stimulus tests/controller -q -m "not windows and not rig"`: 1200 passed, 5 skipped, 3 deselected (loopback). GUI recording-control test (`-p no:faulthandler`) 1 passed/478 deselected. Ruff/format, Win32 mypy 338, boundaries 690/zero violations. No native Windows/GPU/timing/rig acceptance.
- `scientific-evidence-rig` tracks native On/Off/On checks; Eye/timing/SpikeGLX deferred. Evidence: `reports/runtime-evidence-2026-10-14/always-save-scientific-evidence/`.

## 2026-10-14 - Rig encoding comparison plan and collection tool

- `encoding-rig-test-plan` completed [acquisition] [visual_stimulus]: reports/rig-verification.md extended with provenance, synthetic FFmpeg per-source/concurrent commands, warm-up and three 60 s repeats, live capture matrix, monitoring and restore steps. Eye conditional on confirmed readiness. lavfi encoder isolation distinguished from raw-stdin/capture/real-drop acceptance; no live-run CLI invented.
- Added tools/encoding_probe.py: bench (CQ-only in-memory override, concurrent bounded synthetic 8-bit encoders, frame-count and decode checks outside timing) and collect (videos, frame logs, renderer JSON; flags malformed logs). No runtime/device/config mutation. ARCH-002: standard library only; new tests/shared/test_encoding_probe.py justified by tooling fixtures.
- Local: 5 offline tests pass; Ruff/format, Win32 mypy, CLI help, boundaries 690/zero violations pass. FFmpeg/NVENC and PowerShell not executed; rig tasks stay open.

## 2026-10-14 - Post-hoc alignment output audit

- [acquisition] [visual_stimulus] [tracking] [spikeglx] [controller]: audit of output gaps under the first-trigger/first-recorded-source assumption against the legacy preprocessing guide (reference only). Camera/stimulus evidence retention present; checked-in pulse assignments empty. Missing Eye PulseRole/key/required-channel admission confirmed; added `eye-spikeglx-pulse-inventory`. SpikeGLX/rig tasks retain channel/shared-sync inventory work.
- Runtime report records absent OneBox-probe waveform association, SY-bit inventory limitation, unknown camera counter/reset semantics, trial matching prerequisites, optical limits, optional Tracking history. No new wiring or cadence justified. Source/schema inspection only; no tests, runtime change or independent anchor claimed.

## 2026-10-14 - Encoding rig plan/helper review

- `encoding-rig-plan-review` completed [acquisition] [visual_stimulus]: reviewed against A08/V12/E13/E15. Fixed lost benchmark summaries on launch/probe failures, unbounded version queries, false throughput on decoder error output despite exit 0, collector aborts on malformed records. Collection reports nonzero status for invalid/empty input or missing diagnostics; failed validation suppresses throughput claims.
- Repeated commands simplified into one warm-up/three-repeat PowerShell matrix with CQ order reversal; clarified synthetic vs full-app contention, GPU adapter verification, provenance, bitrate units. ARCH-002: standard-library tool/tests only.
- `.venv/bin/python -m pytest tests/shared/test_encoding_probe.py -q`: 15 passed; Ruff/format, Win32 mypy, boundaries 690/zero violations. No Windows PowerShell, FFmpeg/NVENC or hardware run; stderr routing, tool compatibility and throughput pending.

## 2026-10-14 - Eye SpikeGLX inventory and Setup support

- `eye-spikeglx-pulse-inventory` completed [acquisition] [spikeglx] [controller] [gui]: E12 revision21 adds first-class Eye role (enum7; existing values preserved), `eye_tracking_camera` parsing/atomic editing, GUI classification/restoration and enabled externally triggered Eye Setup requirement. Missing/wrong-family/unsaved mappings fail before run-name mutation; disabled/free-running Eye or disabled acquisition requires none. Existing preparation serialization retains Eye in SESSION_CONFIG. Defaults remain empty; no wiring, trigger timing or acquisition settings changed.
- ARCH-002 review extends focused existing modules and owning tests without new dependencies/state/coordination. Regenerated19 Protobuf sources with `tools/generate_contracts.py`. No fixed policy values changed. Root register, E12 contract, runtime report and single rig checklist updated; existing paired integration TODO retains actual Behavioral/Tracking/Eye channel/bit assignment and recorded-pulse proof. Rig execution remains pending.
- Validation: `.venv/bin/python -m pytest tests/controller tests/client -q -m "not windows and not rig"`:490 passed,14 sandbox loopback setup errors; authorized rerun of `tests/client/test_controller_rpc.py` passes15. Final `tests/controller/test_spikeglx.py`:35 passed; offscreen GUI `-p no:faulthandler -k "spikeglx or inventory_required_roles"`:13 passed/466 deselected. Initial test helper import error repaired. Scoped Ruff check/format and Win32 mypy pass; boundaries690 modules/zero violations (existing size warnings outside touched modules). TOML empty-inventory check, Markdown reference checks and git diff whitespace check pass. Local validation does not establish physical pulse capture or hardware compatibility.

## 2026-10-15 - Controller/supervisor audit and verified repairs

- `controller-supervisor-audit` [controller] [supervisor] [shared]: owner-requested whole-backend audit. Six read-only module audits produced about 85 candidates; the strongest were reproduced by probe or a failing test before any edit. Twelve repairs (E04 revision 89 adds the `incident_scope` event the controller already wrote): Setup cancel/failure before supervisor registration no longer blocks cleanup or holds the reservation; accepted commands with no live attempt are finalized (the ledger was exhausted at 1,024); long failure messages no longer hang an RPC; a failed calibration Close or camera release no longer wedges its retry; eye-camera dormant values/PFS payload excluded from SESSION_CONFIG; recovery inspects logs containing `incident_scope`; a late ConfirmLaunch no longer revives a released launch; a firmware-rejected DIAG_START is not an uncertain start; deadline failures labelled by type; `setup_override` appended after `session_started`; MCU contract text corrected to protocol 4. Dead write-only state removed.
- Verification: each new regression fails on the pre-fix source and passes after. Two existing tests corrected (a lifecycle fixture now models an activated session's registered context; a client RPC test no longer expects the failed cancel that pinned the defect). Local only; no Windows-native or rig run. Findings and open items: [audit](reports/runtime.md#controllersupervisor-audit-2026-10-14). Follow-up tasks: `e04-session-log-completeness`, `controller-cleanup-and-race-hardening`, `controller-config-inactive-backend-defaults`, `calibration-live-update-rejection`, `controller-supervisor-residual-simplification`.

## 2026-10-15 - Audit owner decisions applied

- `controller-supervisor-audit` follow-up [supervisor] [controller] [acquisition]: owner accepts both proposed options. E08 revision 171: a required backend whose exit was already classified continuable no longer triggers `BACKEND_HEARTBEAT_LOST`. A11 revision 45: a failed manual Connect discards its owner and port so a retry opens a fresh one; an unanswered DIAG_START is cleaned by a Stop attempt plus the verified OFF (a failed Stop of a known-active diagnostic still fences); the keepalive task survives a failure handler that raises, skipping only that failed connection, and the failed close now warns. The test asserting the old wedge was rewritten to the decided behavior.
- Verification: new tests fail on the pre-change source (isolated exit, Connect retry, unanswered start; the keepalive test failed with the handler error before the fix). Scoped pytest 840 passed, 1 skipped, 4 deselected (supervisor, controller, shared, client, launcher, platform); Ruff check and format, Win32 mypy (129 files), boundaries 690 modules with zero violations, whitespace clean. COM-handle release after a failed Connect is added to the rig checklist; local fakes do not establish it. Remaining microcontroller items: `mcu-owner-residual-hardening`.

## 2026-10-15 - Cameras inline MCU pin

- `camera-inline-mcu-pin` completed [gui]: owner requests removal of MCU wiring button and an editable pin beside Cameras trigger frequency. G01 revision186 records the inline field and bidirectional synchronization with the existing role-owned MCU draft. Selection/role changes, table clears and MCU file restore update the display; preserve camera participation/timing and authority/capture/diagnostic locks. ARCH-002 review removes the obsolete camera dialog and camera-specific save branch, with no added dependency or state owner. Existing camera/MCU presentation size warnings remain cohesive; Devices owns synchronization.
- Validation: offscreen owning dashboard regression (`-p no:faulthandler -k "camera_pin or contextual_wiring or cancelled_projector_wiring or microcontroller or camera"`) passes81/402 deselected; initial focused run11 passes. Ruff check/format and Win32 mypy3 sources pass; boundaries690/zero violations, edited Markdown links and whitespace pass. Offscreen layout at1100×760 inspected. Initial formatting repaired. Optional aggregate GUI run interrupted after focused completion emitted a failure marker and exit134; no aggregate pass or diagnosis claimed. Process listing for an earlier stop attempt was sandbox-denied; direct owned-session interrupt succeeded. No native Windows/hardware run. Concurrent protocol/controller work preserved.

## 2026-10-15 - Current Runtime and Review GUI parity

- `runtime-review-gui-current-parity` completed [gui]: verified both entry points import current checkout sources and reuse DashboardWindow under G01. No layout divergence found. Extend the existing owning parity test to compare visible field/label/button positions and sizes for Texture, Image, Video, Looming and Arena with Advanced settings open, including current initial pose/movement limits. ARCH-002 review retains shared construction without production edits, new dependencies or separate test modules. Concurrent Protocol, camera and backend changes remain intact; report updated in place.
- Validation: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui/test_dashboard.py -q -p no:faulthandler -k 'review_and_runtime_share_page_elements_and_card_layouts'` passes4/480 deselected (final button-inclusive comparison; earlier baseline and expanded runs also pass4). Same command selecting `camera_pin or direct_group_editor or protocol_arena_limits or family_advanced_controls or contextual_wiring or runtime_gui_close_reopen` passes20/464 deselected. GUI Ruff/format, Win32 mypy160 sources and boundaries694/zero violations pass; existing source cohesion advisories remain outside this test-only change. Source imports resolve to this checkout. macOS offscreen checks only; no native Windows/rig acceptance or running-process refresh. Reopening each GUI loads current code.


## 2026-10-15 - Protocol group headings and arena Advanced settings

- `protocol-group-and-arena-settings` completed [gui] [visual_stimulus]: rename the timeline footer to Selected group; move names above group blocks and preserve readable repetitions at narrow widths. Expose initial pose in Advanced settings, including arena height/pitch/roll, with minimum height preventing nested-control clipping. Owner selects CephVR1.0-style declared arena-file geometry, limited to rectangular/convex import first; G01 revision187 and V16 revision5 record the final behavior. Legacy source inspection confirms extras.cephvr.metadata.geometry, shape-derived limits and20 mm legacy session default; new GUI clearance defaults to the owner's30 mm.
- Add trial-owned arena-file region drafts with margin validation, Undo/Redo and Protocol snapshot restore; preserve saved explicit regions/unrestricted mode. Protected GLB preparation retains geometry; compilation transforms unique asset/geometry recipes once, checks cancellation/deadline budgets, rejects unsupported/missing/inconsistent geometry, zero/negative-area insets and outside initial poses, and retains resolved polygons/fingerprints. No mesh-bound inference, wrapping or additional shape solver. Regenerate the two owning boundary/artifact JSON schemas and update contracts plus both owning reports and the single rig checklist. ARCH-002: focused initial-pose/arena form and geometry-declaration/resolution helpers, existing state/resource owners and owning test modules; no new dependencies. Existing cohesive size advisories reviewed in the reports.
- Validation: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui/test_dashboard.py -q -p no:faulthandler -k 'protocol or group or arena or advanced or schedule'`:62 passed/422 deselected; after final pose-height/snapshot changes, the family/arena subset passes7/477 deselected. Final `.venv/bin/python -m pytest tests/visual_stimulus -q -m 'not windows and not rig'` with loopback access:318 passed/one deselected. Final compiler/resource subset64 passes, including protected-source-adapter→metadata→compiled artifact/closure and repeated-epoch conversion. Initial sandbox Visual Stimulus run309 passes/nine socket-bind failures; authenticated rerun15 passes. Initial fixture/type/height expectations and repetition compression repaired. Scope Ruff/format18 files, Win32 mypy313 GUI/Visual Stimulus sources, boundaries694 modules/zero violations, both schemas,857 Markdown targets/anchors and whitespace pass. A first link check mistakenly read fenced PowerShell as Markdown; the corrected prose-only check passes.
- Dated offscreen capture/source context retained in reports/runtime-evidence-2026-10-15/protocol-arena-settings/. Initial ad hoc captures wrote PNGs then exited139 during interpreter teardown; final explicit deferred widget cleanup/capture exits0 and is visually inspected. No production shutdown, Windows-native file protection, physical sliding/four-view or rig acceptance claimed; the rig checklist retains these. Concurrent camera, Runtime/Review parity, styling and controller/supervisor work is preserved.

## 2026-10-15 - Review Retro console style

- `gui-retro-console-style` completed [gui]: owner limits the experiment to Review. Add Style → Standard / Retro console in its window bar, retain the local preference, and style Dashboard/chrome with charcoal, amber and cyan, monospace fields, square instrument frames and subtle static terminal lines. Runtime keeps Standard and has no style menu. G02 revision39 and its root register record the scope. ARCH-002 review reuses the shared stylesheet/palette and existing widgets, adding one focused menu/preferences module; no dependencies or experiment state changes. Concurrent work preserved.
- Validation: offscreen appearance/theme/Standard Runtime–Review parity selection7 passed/479 deselected; log/HUD/navigation/Review-save selection8 passed/478 deselected. GUI Ruff/format163 files, Win32 mypy161 sources and boundaries695 modules/zero violations pass. Existing source cohesion advisories are outside the edited modules. Wide1440×940 and narrow720×940 renders inspected; Standard→Retro→Standard returns identical captured pixels. Switching retains unfinished edits, logs, widget identity and command gates; preference restores on reopening and does not affect Runtime. Dated commands/source hashes and repeatable capture method are in `reports/runtime-evidence-2026-10-15/retro-console/`; images are local-only. No Windows-native or rig checks, running-GUI restart or actual draft writes. Minor unused import/formatting corrected before passing checks.


## 2026-10-15 - Open updated Protocol GUI

- [gui] Owner requests the updated GUI for inspection. Launch current checkout Review with simulated devices and the standard draft restore/startup path, selecting Protocol before showing the window. Initial sandbox launch exits134 because Cocoa cannot access screens; desktop-enabled launch remains running (exec session35630) with no startup error beyond the existing font warning. Native accessibility lookup cannot bind the virtual-environment Python application, so visible-page verification is unavailable through CUA; no native/rig acceptance claimed. No source or saved-draft mutation.

## 2026-10-15 - Open Review with Retro console

- [gui] Owner requests the Review GUI reopened with Retro console selected. Saved only `review/appearance=retro_console` through QSettings and launched the normal Review entry point with simulated devices and ordinary draft restore on the desktop (PID55072, exec session80316). Process remains running; independent settings read confirms the selected preference. Runtime was not restarted or restyled.
- The ad hoc status timer was scheduled before QApplication existed and emitted a timer warning, so it supplied no visible-window confirmation. Startup otherwise reports only the existing font fallback warning. CUA cannot bind this virtual-environment Python executable (`Invalid app`), preventing native screenshot/accessibility verification. No source changes, experiment commands or rig acceptance.

## 2026-10-15 - Warmer Review console palette

- `gui-retro-warmer-palette` completed [gui]: deepen Retro console to warm charcoal/copper surfaces, orange headings/borders and burnt-orange actions; use cream inputs and amber selections/logs while retaining muted cyan readouts. Review-only under G02 revision40; Standard/Runtime unchanged. ARCH-002 review reuses palette tokens and removes remaining fixed cool-color overrides; no new logic or tests needed for this cosmetic refinement.
- Validation: existing offscreen appearance/theme selection3 passed/483 deselected; scoped Ruff/format, Win32 mypy and boundaries695/zero violations pass. Wide warm capture visually inspected; narrow capture generated and Standard round-trip pixels remain identical. Evidence in `reports/runtime-evidence-2026-10-15/retro-console/warm-context.json`. Started a fresh desktop Review through the standard launcher (exec session32517) with the existing Retro preference; prior windows were not force-closed. Native accessibility remains unavailable, no rig acceptance.

## 2026-10-15 - Balanced Review console palette

- `gui-retro-balanced-palette` completed [gui]: follow the owner's new reference with green-black surfaces, blue framing/actions, cyan headings, pale green terminals/checked controls and restrained amber branding/warm stop accents. G02 revision41 and root register updated. ARCH-002 review retains the existing palette/stylesheet, widget/state ownership and Review-only scope; no new dependencies or behavior tests.
- Existing offscreen appearance/theme checks3 passed/484 deselected; scoped Ruff/format, Win32 mypy and boundaries695/zero violations pass. Wide render visually inspected, narrow render generated, Standard round-trip pixels identical. Capture helper accepts a separate output directory to preserve earlier evidence. Current source hash/method/results in `reports/runtime-evidence-2026-10-15/retro-console/balanced/context.json`. Fresh desktop Review launched with retained Retro preference (exec session14201); previous windows not force-closed. Native accessibility remains unavailable; no native Windows/rig acceptance.

## 2026-10-15 - Phosphor-orange Review titles

- `gui-retro-orange-titles` completed [gui]: apply warm phosphor orange (#f0aa63) to page/panel titles and branding, with softer amber (#c9a578) field captions. Preserve balanced blue framing/actions, cyan navigation/focus and green terminal text. Review-only under G02 revision42; root register/report updated. ARCH-002: existing theme tokens/selectors only, no new logic/dependencies/tests.
- Existing offscreen appearance/theme checks3 passed/484 deselected; scoped Ruff/format, Win32 mypy and boundaries695/zero violations pass. Wide capture inspected and Standard round-trip pixels match; dated evidence in `reports/runtime-evidence-2026-10-15/retro-console/orange-titles/context.json`. Fresh native Review launched via standard script (exec session12164); earlier windows not force-closed. Native accessibility unavailable; no Windows/rig acceptance. Concurrent Protocol work preserved.


## 2026-10-15 - Aligned arena XYZ and orientation

- `protocol-arena-pose-layout` completed [gui]: G01 revision188 puts wall limits first, then aligned XYZ (mm) and yaw/pitch/roll (degrees) columns. X/Y default to0, Z copies configured subject height and angles default to0 (forward +Y, level horizon). Rig height is passed as a focused value to both new-family and new-file authoring; missing/nonfinite height blocks creation. Existing poses are preserved on later rig edits. The schema stays planar XY/yaw plus fixed height/pitch/roll; no runtime motion/schema change. ARCH-002 review extends the focused initial-pose helper and existing authoring interfaces with no dependencies or duplicated pose state; loaded condition references remain supported by existing ValueEditors.
- Validation: final `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui/test_dashboard.py -q -p no:faulthandler -k 'arena or advanced or review_and_runtime_share_page_elements_and_card_layouts'`:25 passed/462 deselected. Earlier broad Protocol selection57 passes/five fixture failures; corrected three missing explicit subject heights and two old yaw-control lookups. Final ten owning default/edit/layout cases pass. New regression checks X/Y/Z and all angles, subject-height changes preserving authored values, both creation paths, missing-height rejection and 720/1280 row alignment. Initial new test's absent selected asset was corrected before its apply assertion. Scoped Ruff/format7 files, Win32 mypy6 sources, boundaries695 modules/zero violations,524 Markdown targets/anchors and whitespace pass. No native Windows/rig acceptance.
- Visually inspected successful offscreen capture/cleanup; dated image/source context at reports/runtime-evidence-2026-10-15/protocol-arena-settings/xyz-orientation-context.json. Updated the current Runtime report and root register, preserving concurrent styling/backend edits. Fresh desktop Review launched through its standard restore path with Protocol selected and arena Advanced settings opened when present (exec session33336); earlier windows retained. Native accessibility cannot bind the environment's Python app, so no independent visible-window verification is claimed.

## 2026-10-15 - Card-title-only Review accent

- `gui-retro-card-title-accent` completed [gui]: restore cyan page headings and field captions, retain restrained amber branding, and restrict the new muted red-orange (#df7960) to card titles. Review-only under G02 revision43; root register/report updated. ARCH-002 review reuses existing palette tokens and one scoped selector, with no new dependencies, state or tests.
- Existing offscreen appearance/theme checks3 passed/484 deselected; scoped Ruff/format, Win32 mypy and boundaries695/zero violations pass with existing cohesion advisories. Wide render visually inspected; Standard round-trip pixels identical. Dated evidence in `reports/runtime-evidence-2026-10-15/retro-console/card-title-accent/context.json`. Fresh native Review launched via standard script (exec session17879); earlier windows not force-closed. Native accessibility unavailable; no Windows/rig acceptance. Concurrent work preserved.


## 2026-10-15 - Plain numeric arena pose fields

- `protocol-arena-numeric-inputs` completed [gui]: G01 revision189 replaces all six XYZ/yaw/pitch/roll type selectors with plain numeric inputs. Imported condition references remain read-only saved values. ARCH-002 review simplifies the focused pose helper by removing union-schema plumbing from these fields, preserving canonical reads, row alignment and existing model validation; no new dependencies or runtime changes.
- Validation: offscreen owning selection (`-p no:faulthandler -k 'arena_xyz_orientation or family_advanced_controls_preserve_hidden_state or protocol_arena_limits_default'`)8 passed/479 deselected; final default/edit/alignment/condition preservation regression1 passed/486 deselected. Scoped Ruff/format2 files, Win32 mypy1 source, boundaries695/zero violations and whitespace pass. Explicit widget cleanup/capture exits0; image/source context retained in reports/runtime-evidence-2026-10-15/protocol-arena-settings/plain-numbers-context.json. Current report/register updated, concurrent style/backend work preserved.
- Fresh desktop Review running on Protocol with arena Advanced settings enabled when present (exec session82354). Native accessibility remains unable to bind the environment's Python app; no native Windows/rig or independent visible-window acceptance claimed.


## 2026-10-15 - Remove Dashboard Recordings explanatory text

- `dashboard-recordings-copy` completed [gui]: remove the metadata/scientific-data sentence from the shared Recordings card under G01. ARCH-002 review deletes the unused label construction in the existing focused module; no dependencies, state or recording behavior changes. Updated the current owning report; concurrent changes preserved.
- Validation: offscreen card construction confirms the sentence is absent and stimulus recording stays selected. Scoped Ruff/format and Win32 mypy1 source pass; boundaries695/zero violations and whitespace pass. No new tests for this cosmetic removal; no native Windows/rig acceptance.
- Started a fresh desktop Review through scripts/start_gui.py for Dashboard inspection (exec session44830), retaining earlier windows. Native accessibility remains unavailable for this environment Python app; no independent visible-window verification claimed.


## 2026-10-15 - Shared arena Advanced settings columns

- `protocol-advanced-column-alignment` completed [gui]: G01 revision190 applies common equal-width column stops to all arena Advanced settings inputs: movement mode above Position and wall clearance above Orientation; descriptive geometry text spans both columns. Existing outer Layer alignment and plain XYZ/Euler inputs remain. ARCH-002 review factors the concrete shared grid into the existing layouts helper, with no state/dependency changes; the mode dropdown can shrink at narrow widths.
- Validation: owning offscreen pose/hidden-state/arena-limits selection8 passed/479 deselected; final alignment/default/edit regression1 passed/486 deselected after the narrow-mode sizing refinement. It checks matching column starts/widths and pose row heights at720/1280. Scoped Ruff/format4 files, Win32 mypy3 sources, boundaries695/zero violations, edited Markdown targets/anchors and whitespace pass. Successful offscreen capture/cleanup is visually inspected and retained with source provenance in reports/runtime-evidence-2026-10-15/protocol-arena-settings/aligned-advanced-context.json. No native Windows/rig acceptance.
- Current report/register updated and concurrent styling/backend work retained. Fresh desktop Review launched on Protocol with arena Advanced settings enabled when present (exec session5684); native accessibility remains unavailable, so no independent visible-window verification claimed.

## 2026-10-15 - Review Dashboard instrument details

- `gui-retro-instrument-details` completed [gui]: add numbered uppercase card headers, one aligned HUD value column, square action controls, labelled current-view readiness lamps with subtle halos, and fine terminal edge graduations. Retain the restrained red-orange titles and blue/cyan/green palette. Dashboard-only Review Retro scope under G02 revision44; no embedded plots or synthetic telemetry. ARCH-002 reuses appearance/component owners and extracts HUD presentation refresh from view application; no dependencies or new test modules.
- Validation: owning appearance/theme/HUD/Standard-parity selection10 passed/477 deselected; extended existing appearance test verifies header/HUD restoration, view/draft/log retention, lamp text/readiness and click immunity. Scoped Ruff/format5 files, Win32 mypy4 sources, boundaries695/zero violations and whitespace pass. Wide/narrow renders inspected, Standard round-trip pixels identical; evidence in reports/runtime-evidence-2026-10-15/retro-console/instrument-details/context.json. Removed left-side bezel ticks after capture showed proximity to text; final ticks stay at the right edge. Existing unrelated cohesion advisories remain.
- Fresh native Review launched via scripts/start_gui.py (session28790), retaining prior windows. Native accessibility remains unavailable for this Python app; no Windows/rig acceptance. Current report/register updated and concurrent Protocol/backend edits preserved.

## 2026-10-15 - Unnumbered Retro card titles

- `gui-retro-remove-numbering` completed [gui]: remove automatic numbering from Review Dashboard Retro headers while retaining uppercase red-orange titles and the existing terminal markings. G02 revision45/register/report updated. ARCH-002 review simplifies the existing transform by removing enumeration; no new components, state or dependencies. Broader terminal design ideas remain suggestions.
- Existing appearance tests2 passed/485 deselected; scoped Ruff/format2 files, Win32 mypy1 source, boundaries695/zero violations with existing unrelated cohesion advisories, and whitespace pass. Fresh Review launched through scripts/start_gui.py (session6055), earlier windows retained. No new screenshot capture, native accessibility or Windows/rig acceptance. Concurrent work preserved.

## 2026-10-15 - Review Dashboard terminal markings

- `gui-retro-terminal-markings` completed [gui]: add subtle card/console edge ticks with every fifth longer, dashed rules between HUD/session sections, cyan active-input corner brackets, bracketed actual status captions and a segmented current-trial strip with exact index/count. Strip hides when count is unavailable; large counts use at most24 segments and never claim completion. Review Retro Dashboard only under G02 revision46. ARCH-002 extracts existing console painting into a focused retro-instrument module and retains editor ownership/scalar position inputs; no dependencies, timers or experiment state changes.
- Validation: existing owning appearance/theme/HUD/Standard-parity selection10 passed/477 deselected. Extended appearance test checks text/combo focus, mouse transparency and continued typing, style/draft/log/gate preservation, and zero/mid/final/large-count position states. Scoped Ruff/format5 files, Win32 mypy4 sources, boundaries696/zero violations and whitespace pass; existing unrelated size advisories remain. Wide/narrow, focused-editor and active-trial fixture captures inspected, Standard round-trip pixels identical. Dated hashes/method/results in reports/runtime-evidence-2026-10-15/retro-console/terminal-markings/context.json.
- Fresh native Review launched via scripts/start_gui.py (session10674), retaining earlier windows. Native accessibility remains unavailable; no Windows/rig acceptance. Root register/current report updated and concurrent edits preserved.


## 2026-10-15 - Repair empty arena mode after missing height

- `protocol-arena-mode-failure` completed [gui]: owner screenshot shows 3D mode with empty asset/motion controls. Reproduced locally with unset subject height: mode became3D, arena controls false, error string empty. The previously added height requirement failed inside change_type after active_mode advanced; show_rows then cleared its error. Validate height before switching, keep original mode/program/controls on rejection and show an action-time warning. G01 revision191/register/report updated. ARCH-002 review uses the existing validation path; no dependencies or extra state. Prior window drafts retained.
- Validation: offscreen owning mode-failure/default/gain selection5 passed/483 deselected; new regression proves old-mode retention, warning, successful67.5 mm retry with asset chooser and switching back. Initial final assertion mistakenly expected inactive arena drafts to prevent returning; corrected to the accepted mode-draft preservation behavior. Scoped Ruff/format2 files, Win32 mypy1 source, boundaries696/zero violations, edited Markdown links/anchors and whitespace pass. Pre-fix probe ran on the dirty working tree; exact pre-fix fingerprint was not retained. No native Windows/rig acceptance.
- Fresh desktop Review launched on Protocol with the fix (session97684); existing windows kept for unsaved edits. Native accessibility remains unavailable for this Python app; no independent visible-window verification claimed.

## 2026-10-15 - Keep dashed dividers only in the HUD

- `gui-retro-hud-only-divider` completed [gui]: remove main-card dashed rules, preserving the HUD rule and edge ticks in Review Retro. G02 revision47/register/report updated. ARCH-002 removes unused section-anchor state and imports; no new dependencies or behavior.
- Scoped Ruff/format and Win32 mypy2 sources pass; boundaries696/zero violations with existing unrelated cohesion advisories, whitespace pass. Wide capture confirms the requested divider placement; Standard round-trip pixels identical. Dated capture context in reports/runtime-evidence-2026-10-15/retro-console/hud-only-divider/context.json. No new tests for this cosmetic removal. Fresh desktop Review launched (session71475), previous windows retained. No native accessibility or Windows/rig acceptance; concurrent Protocol/backend edits preserved.


## 2026-10-15 - Git sync repair in progress

- `git-sync-repair` [repo] [gui] [visual_stimulus] Found main ahead1/behind2 with an interrupted merge and34 unmerged paths. Retained original conflicted working files in ignored `.tmp/git-sync-original-conflicts`. Reconciled markers, retained later local G01/V15 calibration owners and incoming independent changes, assigned review_scale_factor Protobuf field12 alongside projection11, regenerated bindings and refreshed the combined policy digest. Index remains unmerged; no merge commit or push.
- Validation: full Win32 mypy passes791 sources. Ruff passed before a final constant addition; its import-order warning was fixed. Format check911 files passes; boundaries696 modules/zero violations with existing cohesion advisories. Permitted backend run:1521 passed,16 failed,4 skipped,4 deselected; failures identify remaining calibration/test integration and one lifecycle fixture. GUI run interrupted after partial progress/failures; no pass claimed. Earlier attempted backend commands named nonexistent contract directories; subsequent collection errors were repaired. Restricted test runs stalled and were interrupted. Logs are temporary under `.tmp/git-sync-*`; no native/rig acceptance.
- Automatic approval review rejected the next multi-file calibration source/test restoration because it could discard incoming work beyond explicit Git-sync authorization. Awaiting owner approval; rejected command made no edits. Remote read also failed in restricted execution (`getaddrinfo() thread failed to start`).


## 2026-10-15 - Approved Git merge reconciliation validated

- `git-sync-repair` [repo] [gui] [visual_stimulus] Owner explicitly approved retaining local pixel-size/offset calibration and independent incoming changes, including completing validation and sync. All34 conflicts are resolved and staged. Retained local G01/V15 numeric persistence, affine crops and diagnostic assets; preserved incoming required evidence/review scaling, arena settings, Retro appearance, camera pins and scaled-display identity. Camera direct pin edits reuse the existing draft and locks alongside the identity-fenced dialog. Mode-change merge preserves quiet invalid drafts and the explicit missing-height warning. E14 policy15/digest and Protobuf projection11/review_scale_factor12 are coherent; bindings regenerated from source.
- ARCH-002 review keeps focused existing owners, original deadlines/resource identity and optional-worker periodic sync; no dependency/process/whole-runtime references added. Updated G01 revision205 and E14 revision211 with matching register. Kept the local affine regressions over superseded margin/keystone/seam cases and interactive-legend coverage over obsolete plot-toggle controls. Corrected three arena-height fixtures and a renamed group label; source review found the incoming mode warning had inadvertently exposed unfinished fade drafts, now covered by existing regressions.
- Final validation: all non-GUI tests1737 passed/4 skipped/26 deselected; all offscreen GUI509 passed; final Visual Stimulus327 passed/1 deselected; focused merge GUI29 passed. Ruff, format911, Win32 mypy791, boundaries695/zero violations,114 register entries,1575 Markdown links/anchors, edited TOML/JSON and whitespace pass. Existing cohesive-module size advisories remain. Initial16 backend failures and6 broad GUI integration failures, restricted-runner stalls and intermediate reruns are retained/assessed in reports/runtime-evidence-2026-10-15/git-sync. No native/rig acceptance. Earlier approval blocker is resolved; merge commit and remote sync are next.


## 2026-10-15 - Git sync repaired and verified

- `git-sync-repair` completed [repo] [gui] [visual_stimulus]: merge763fcb013e2cad20f050dd2935b31aa003d281bf preserves parents8a51da4/cd49658 and pushed successfully to GitHub main. Verified clean working tree, HEAD=origin/main and ahead/behind0/0; MERGE_HEAD is absent. Final validation remains1737 backend passes and509 GUI passes with the recorded exclusions/limits. Removed the completed TODO entry after recording this outcome. Evidence context records the verified merge; this bookkeeping increment changes no implementation.
