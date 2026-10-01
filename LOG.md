# Development log

Append dated entries in chronological order; newest entries are at the bottom.
Keep each entry brief: context, action/change or finding, then verification and limits.
Use affected-backend tags and reference a TODO task ID when applicable. Detailed
evidence stays in the linked backend report. Maintenance rules and the tag vocabulary
live in [AGENTS.md](AGENTS.md#task-and-change-tracking).

This log starts on 2026-09-30; it is not a reconstruction of earlier repository history.

## 2026-09-30

### [repo] Establish task and change tracking

- Context: the owner requested a shared task list and a concise log that agents maintain for code work, report changes and findings.
- Changes: created root TODO/LOG files, seeded TODO from explicitly unresolved runtime findings and linked the existing rig worklist. Added agent maintenance rules, README navigation and the GOV-001 tracking convention.
- Verification: checked local links, task ID uniqueness, matching GOV-001 revision/register and whitespace. Documentation only; runtime tests were not run for this change.

### [repo] Share agent guidance across ChatGPT/Codex and Claude

- Context: `shared-model-guidance`; the owner requested instructions usable by both model families.
- Changes: made AGENTS.md explicitly canonical for both, added a CLAUDE.md import, and scoped the Luna delegation preference to ChatGPT/Codex with a configured-model path for Claude. Existing architecture and TODO/LOG obligations are preserved.
- Verification: checked local links, the import target and whitespace; confirmed import syntax against [Claude Code documentation](https://code.claude.com/docs/en/memory#import-additional-files). Documentation only; loading in a live Claude session was not tested. Task complete.

### [repo] Align Codex guidance with OpenAI documentation

- Context: `codex-documented-guidance`; the owner requested the documented OpenAI instruction format.
- Changes: kept AGENTS.md as plain Markdown, clarified scope/discovery, added a repository map and scoped setup/validation commands, and added Code Review Rules following [OpenAI's guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md). Existing governance and tracking instructions remain intact; CLAUDE.md still imports the shared file.
- Verification: checked links/anchors, command paths, Markdown fences and whitespace; confirmed the prior governance sections were preserved verbatim. The file is 18,233 bytes, below the documented default 32 KiB combined instruction limit on its own. No runtime tests or fresh-session discovery test were run for this documentation change. Task complete.

### [supervisor] Second ARCH-002 simplification pass

- Context: `supervisor-simplification-pass2`; the owner asked for a backend simplification review starting with the supervisor, with an action table agreed before edits. Four increments were delegated to Sonnet coders and reviewed here against a pre-refactor snapshot.
- Changes: shared work-scope comparator, live-phase and role constants; registry/registration/health/recovery tidy-ups; one `WorkerControl` interface for acquisition and Visual Stimulus (cleanup module merged, `acquisition_shutdown.py` renamed `acquisition_worker.py`); `shutdown_owned` split into steps (541 to 505 lines); `GrpcOutbound` extends the worker transport (319 to 202 lines) and the port declares `close`/`retire_worker_generation`. Supervisor source 5,208 to 5,013 lines, 21 to 20 modules; a smaller saving than the roughly 10% first estimated. `startup.py`, `main.py` and `registry.confirm()` were left alone on purpose.
- Verification: 110 supervisor/transport tests, Ruff, Windows-target mypy, boundary checker and whitespace passed after every increment; 188-case integration run passed. A tracking test failed once during validation while the Tracking runtime was being edited elsewhere and passed after that edit; it was not caused by this work. Raw evidence: [pass 2](reports/runtime-evidence-2026-09-30/supervisor-simplification-pass2.txt). Local only; no rig/Windows run. Two accepted observable differences are listed in [the report](reports/runtime.md#current-scope-and-review). Nothing committed.

## 2026-10-01

### [tracking] Simplification baseline and ownership cleanup

- Context: `tracking-simplification`; reviewed the existing runtime under ARCH-002 and T08/T09. No added dependency is justified. Preserved the dirty working tree and captured a pre-edit source/test snapshot.
- Changes: removed unused history/feedback fields and shared pose-thread geometry retirement. Added borrowed-history and normal/failure thread-ownership regressions.
- Verification: baseline 28 passed, one rig case deselected; first increment 31 passed, one deselected. Ruff/format, Windows-target mypy (59 files) and boundaries (450 modules, zero violations) passed. Initial sandbox run hit six loopback-bind setup errors; the authorized loopback run passed. E15 rig acceptance remains separate. Audit continues in [the tracking report](reports/tracking.md).

### [tracking] Complete movement simplification and regression audit

- Context: `tracking-simplification`, T08/T09/T19 and ARCH-002; movement repeated input reset handling and mixed execution with scientific record formatting.
- Changes: shared discard/reset handling, extracted a value-only recording formatter, and added regression cases to the existing processing/recording modules. Preserved native ownership, generations, deadlines, exact payloads and record-before-feedback ordering. Updated the current report and corrected stale provider-status prose in the tracking contract index. No package, algorithm, schema or policy change.
- Verification: 42 tracking tests passed (one rig case deselected); full local suite 736 passed, 6 skipped, 2 deselected; 48 tracking contract tests passed. Ruff/format, Windows-target mypy (60 source files), boundaries (451 modules, zero violations) and whitespace passed. One intermediate import-order lint error was fixed. [Dated evidence](reports/tracking-evidence-2026-10-01/README.md) records provenance, audit diff and results. E15 native/scientific acceptance remains pending. Task complete; existing work preserved and nothing committed.

### [controller] Second ARCH-002 simplification pass

- Context: `controller-simplification-pass2`; the owner asked for the backend simplification review to continue with the controller, with an action table agreed before edits. Four read-only audits fed a 13-item plan; seven increments were delegated to Sonnet coders and each was reviewed against a pre-change snapshot (the safety-critical cleanup dispatch and AbortNow/Shutdown precondition were re-traced line by line).
- Changes: removed unread wiring, the static file-policy chain and the `recovery_log_done` hook; single owners for warning retention, rejected receipts/admissions, `Attempt` predicates and the backend-name set; deduplicated backend command wrappers, safety admission, reservation finish, trial-log documents, admission failure handling, report retention and backend cleanup dispatch; moved startup-recovery install, authority capture, manual-cleanup warning and the safety precondition out of `ControllerRuntime` (527 to 422 lines); extracted `setup_resolution.py` (an intermediate split had pushed `setup_execution.py` to 530 lines, now 423); split oversized Setup/interruption/completion/configuration functions; shared test fixtures. Controller source 16,494 to 16,297 lines (about 1%, smaller than the first estimates), tests 7,069 to 6,991; two new small modules. `assembly.py`, `startup/application.py`, `transport/ingress.py` and the authority/evidence state machines were left alone on purpose.
- Verification: 379 controller/consumer tests, Ruff, Windows-target mypy, boundary checker and whitespace passed after every increment; whole-repository suite 736 passed, 6 skipped, 2 deselected. Raw evidence: [pass 2](reports/runtime-evidence-2026-10-01/controller-simplification-pass2.txt). Local only; no rig/Windows run. One accepted observable difference (bounded in-memory warnings) is listed in [the report](reports/runtime.md#current-scope-and-review). Unverified audit observations are recorded in TODO `controller-audit-observations`. Nothing committed.

### [acquisition] [visual_stimulus] [tracking] [controller] [supervisor] Cross-backend ARCH-002 audit

- Context: `backend-simplification-review`; the owner requested a fresh structure, duplication, naming and comment audit across implemented backends, with changes only when behavior and ownership remain intact.
- Changes: inventoried shared and backend package/test layouts and reviewed acquisition, controller/supervisor, Tracking and Visual Stimulus cohesion reports and representative runtime owners. No broad helper extraction or module renaming met ARCH-002. Removed Visual Stimulus's write-only `NativeRecording.video_sync_factory` attribute; kept the constructor input and `EncoderTrialOwner` transfer unchanged. Updated owning reports and retained source/check evidence in [the Visual Stimulus evidence record](reports/visual-stimulus-evidence-2026-10-01/simplification.txt).
- Verification: Visual Stimulus tests passed **121**, with **1 deselected**, after the sandbox's loopback bind restriction was lifted; the initial sandbox run had 5 environment-only bind failures. Ruff, format (134 files), Windows-target mypy (119 files), boundary check (453 modules, zero violations, 16 reviewed size warnings), and `git diff --check` passed. Independent final review is pending; Windows-native/hardware/rig validation remains under E15.

### [visual_stimulus] Complete cross-backend ARCH-002 audit

- Outcome: Sol and Astra independently reviewed the final source and documentation changes and found no remaining actionable issues. Their reviews confirmed the attribute was unread and that the constructor continues to pass the factory to its focused owner; reviewers checked the recorded test/static outcomes but did not rerun pytest.
- Verification: Rechecked local links/anchors and whitespace after review; all passed. The `backend-simplification-review` task is complete for this audit. Windows-native, GPU, hardware and full-workload checks remain deferred to rig verification under E15.

### [repo] Clarify repository convention reminders

- Context: `agent-guidance-reminders`; the owner approved four concise reminders after reviewing current instruction coverage and configured tooling.
- Changes: linked the project-layout guide from the repository map; pointed contributors to checked-in formatting/lint/type/pytest settings, including scoped exceptions; clarified that the boundary checker's >500-line notices prompt cohesion review rather than impose a cap; and added brief intent-focused comment/docstring guidance. CLAUDE.md continues to import AGENTS.md without duplicated rules.
- Review: Astra and Sol independently approved the final actual delta with no actionable findings. Sol confirmed the TODO context link resolves and CLAUDE.md is unchanged.
- Verification: Local Markdown links/anchors and baseline-relative whitespace checks passed for AGENTS.md, TODO.md and LOG.md; `git diff --check` passed. No runtime suite was applicable. Task complete; CLAUDE.md remains an import of AGENTS.md.
