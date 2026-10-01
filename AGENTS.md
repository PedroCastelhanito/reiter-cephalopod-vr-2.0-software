# AGENTS.md

Repository instructions for CephVR2.0 contributors, OpenAI ChatGPT/Codex agents
and Anthropic Claude agents. CephVR2.0 is a Python experiment-control system with
Windows-native device/process ownership and separate rig acceptance.

## Scope and instruction precedence

- This root file governs the repository. Check for more specific instructions in
  the directories containing files you edit. Deeper instructions take precedence
  within their scope; direct system/developer/user instructions take precedence
  over repository guidance.
- Codex discovers `AGENTS.override.md` before `AGENTS.md` in each directory, loading
  at most one file per directory from the project root to its working directory.
  Do not add a root override that unintentionally hides these shared rules.
- Keep this file as ordinary Markdown. Read linked documents when directed below;
  links are references, not a substitute for reading their contents. Root
  [CLAUDE.md](CLAUDE.md) imports this same guidance for Claude Code.
- Use the current client's available tools and permissions. Report unavailable
  checks accurately; never claim a read, action or test result without evidence.

Format and discovery reference: [OpenAI's AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

## Repository map

- `src/cephvr/<owner>/`: backend implementation; `shared/` contains common helpers
  and `platform/windows/` contains native mechanisms.
- `tests/<owner>/`: owning behavior tests; extend these before adding test modules.
- `contracts/` and `config/`: interface/policy declarations and operator settings.
- `architecture.md`, `docs/architecture/`, `reports/`, `TODO.md` and `LOG.md`:
  decisions, current evidence, open work and activity history, respectively.
- For package and module navigation, see the development guide's
  [project layout](docs/development.md#project-layout).
- Generated files under `src/cephvr/<owner>/v1/` are not hand-edited. Change the
  owning `.proto` and run `python tools/generate_contracts.py` when needed.

## Setup and validation commands

Use the repository's Python 3.11 environment. Below, `python` means
`.venv/bin/python` on macOS/Linux or `.venv/Scripts/python.exe` on Windows.
For a fresh environment, follow [the development guide](docs/development.md#environment)
and install the declared development dependencies with `python -m pip install -e ".[dev]"`.
Use backend extras only when required; dependency versions belong in `pyproject.toml`.
The checked-in `.editorconfig` and `pyproject.toml` are the source of truth for
formatting, lint, type-check and pytest settings, including scoped exceptions; follow
their configuration instead of adding ad hoc local overrides.

Run checks for the affected owner first, then relevant integration tests. For example,
a supervisor change uses:

```sh
python -m pytest tests/supervisor -q -m "not windows and not rig"
python -m ruff check src/cephvr/supervisor tests/supervisor
python -m ruff format --check src/cephvr/supervisor tests/supervisor
python -m mypy --platform win32 src/cephvr/supervisor
python tools/check_backend_boundaries.py
git diff --check
```

Replace the supervisor paths with the affected owner(s). Run appropriate contract
checks for contract edits and `python -m build` for packaging changes. Documentation-only
changes need link/anchor and whitespace checks, not an unrelated runtime suite.
Report actual commands, outcomes and blockers. Windows-target mypy is static analysis;
local passes do not close E15 rig checks. Authenticated transport tests need loopback
socket permission; do not weaken their assertions to bypass an environment restriction.

## Architecture is the starting point

- The owner has selected Tracking implementation next, followed by GUI and finally
  SpikeGLX integration. Existing controller, supervisor, acquisition host and Visual
  Stimulus work and required shared helpers remain authorized. Firmware/flashing is
  deferred; analysis software and offline replay/export are deferred much later.
  Follow GOV-001 and ARCH-001. Declarative contracts remain authoritative inputs,
  not proof of implemented or rig-validated behavior.

- Read [architecture.md](architecture.md), [system contracts](docs/architecture/system-contracts.md),
  and the relevant backend pages in `docs/architecture/` before design or code changes.
- Those documents together are authoritative, with one home per decision. Use the root
  register to locate IDs. Supporting guides/reports are navigation and planning aids;
  the old CephVR project is reference material.
- Accepted decisions guide implementation within their stated scope. Proposed,
  Open, and Deferred entries are not permission to implement those choices.
  Superseded and Rejected entries explain history and do not govern current code.
- Preserve decision IDs and anchors. Cite applicable IDs in substantive code-change
  descriptions and explain how relevant validation checks the agreed behavior.

## Decisions and changes

- Keep architecture records concise: one current rule per decision, stated as owner,
  behavior, limits and failure response. Replace existing bullets when refining them.
  Reference shared rules; do not repeat config-key inventories or explanatory history.
  Keep detailed wire/schema definitions in contracts. Operator TOMLs hold only settings
  an operator may change; fixed policy declarations live in the versioned
  `contracts/policy/<backend>_policy.toml` (E14). A normal amendment should change
  only a few focused bullets.
  Reports must link to current decisions instead of accumulating another decision log.
- Ask only about critical unresolved backend choices affecting experiment behavior,
  data integrity, ownership, failure guarantees or scope. Apply the same decision
  depth across backends. Under GOV-001, apply accepted shared rules and reuse
  compatible contracts/helpers without asking again; link their owning decisions.
  Do not generalize another backend's specific behavior merely because it exists.
  Raise only a concrete conflict with required backend behavior, identifying the
  rule, consequence and smallest necessary exception; continue unaffected work.
  Routine field names, schema/RPC structure and implementation mechanics are agent
  work, not approval questions.
- Record each choice in its owning `docs/architecture/<backend>.md` record;
  cross-component rules belong in `docs/architecture/system-contracts.md` and global
  rules in root `architecture.md`. Update the root register with every revision.
  Keep worker rules with their owning backend and link common rules without copying.
  Do not create competing records in README files, guides or reports.
- Follow GOV-001: first review simpler alternatives that satisfy the requirements.
  Present the simpler viable approach as an option and recommend it when it meets
  the same requirements. Add states, fields, processes or coordination only for a
  concrete need. Keep the owner-requested architectural-policy declarations in
  their `contracts/policy/` files; do not invent additional supported policy choices.
- Follow GOV-001: present two critical unresolved decisions at a time when available,
  each with options and an explained recommendation; explain complex choices
  individually. Never invent minor choices merely to fill the next pair.
  Complete acquisition's rig-independent choices and implementation contracts before
  moving to another backend. Follow the owner-selected build order in ARCH-001. Keep hardware inputs
  and rig verification pending under
  their existing deferrals; local contract work is not deferred. Acquisition includes concrete schemas,
  worker interfaces, device mappings and recording mechanisms. Resolve routine details
  within accepted rules; do not treat high-level agreement as implementation readiness. Do not treat open recommendations as settled; retain explicit
  owner-approved deferrals.
- After each accepted choice or pair, record it and continue the authorized work.
  Present the next pair only when critical backend choices remain; otherwise complete
  routine contracts/details autonomously without another approval round. Do not wait
  for "next", fabricate questions, or accept unanswered critical recommendations.
  Keep option comparisons out of architecture records. Partial answers accept only
  those entries; preserve explicit owner-approved deferrals and backend build order.
- User instructions take precedence. If the owner explicitly revises a decision,
  update the record and carry out the authorized work without asking for the same
  approval again. Routine contract formalization needs no additional approval.
  Routine coding is autonomous only within an explicitly authorized coding phase;
  acceptance of a design alone does not start that phase.
- If necessary work conflicts with an accepted decision and the user has not
  resolved that conflict, explain the specific decision and ask for the missing
  architectural choice. Continue independent work that does not require the answer.
- Do not promote unanswered recommendations to Accepted. Keep design acceptance,
  implementation status, and actual validation results distinct.
- Make architecture amendments alongside the affected implementation when both are
  in scope. Replace the current rule under the same ID for refinements; do not keep
  historical discussion or rejected alternatives in architecture records.

## Reports and verification evidence

- Follow [GOV-001](architecture.md#gov-001)'s reporting convention: maintain one
  current report per backend area in `reports/runtime.md` (controller/supervisor and
  shared helpers), `reports/acquisition.md`, `reports/visual_stimulus.md` and `reports/tracking.md`.
  Update these in place; do not create files or append sections per audit/review round.
- Keep reports focused on current scope, unresolved findings, review evidence,
  validation results and limitations. Link governing decision IDs and contracts;
  do not copy policy inventories or maintain another decision history.
- Use `reports/rig-verification.md` as the single outstanding rig checklist and
  execution guide. Backend reports link to it instead of duplicating handoffs,
  procedures or deferred checks. Preserve explicit owner-approved deferrals.
- Preserve dated raw evidence and its contextual assessment together in dated
  evidence directories. Record date, source revision when known, command/method,
  outcome and validation scope; label missing provenance and historical results.
  Never turn source review, collection or static checks into runtime/rig passes.
- When consolidating, retain unresolved findings, unique evidence and useful source
  references, update incoming links, and remove redundant resolved commentary.
  Git retains review history; do not create a parallel archive of narrative reports.
  These rules concern development reports, not E04 runtime emergency/recovery outputs.

## Task and change tracking

- Read root [TODO.md](TODO.md) and the recent entries in [LOG.md](LOG.md) at task
  start, alongside the governing architecture and relevant backend report. Use
  these same files across agents; do not create separate per-agent task lists/logs.
- TODO is the current work queue: one concise action/completion condition per entry,
  a stable descriptive task ID, affected-backend tags and a link to supporting
  context. Use its In progress, Next, Blocked and Deferred sections. In-progress
  work names its owner/chat when known; blocked/deferred entries state the reason.
  Reuse an existing task before adding one. A TODO entry does not grant permission
  to implement a proposed decision or start a deferred stage.
- Use the same tags in both files: `[controller]`, `[supervisor]`, `[acquisition]`,
  `[visual_stimulus]`, `[tracking]`, `[gui]`, `[spikeglx]`, `[launcher]`, `[shared]`.
  Tag every affected area; `[repo]` is for repository-wide tooling/documentation.
  Report edits use the backend tags of their subject, not a separate report tag.
- Update TODO whenever work starts, its status changes, a follow-up is discovered,
  or a task completes. Record new findings promptly with their source and validation
  status; distinguish an observed defect from an unverified concern. Keep detailed
  findings/evidence in the owning report and link them from the task.
- Append a dated LOG entry for each coherent action or work increment, including
  code/report edits, reviews, investigations, validation, failed attempts and new
  findings. Briefly record context, what changed or was learned, and checks/limits;
  include the task ID when applicable. Group related tool calls into one entry and
  state when a review found nothing actionable. Do not record every shell command
  or recursively log edits made solely to maintain TODO/LOG.
- Before handing work back, reconcile both files with actual results. Remove a
  completed task from TODO only after LOG records its outcome and verification;
  leave partial/blocked work open. Record cancellation or supersession before
  removing a task. Do not mark a task complete merely because an attempt ended.
- Re-read the relevant entries immediately before editing; preserve concurrent
  agents' entries and ownership. Append log history rather than rewriting it;
  identify corrections explicitly. These files index work under GOV-001 and do
  not duplicate architecture decisions, backend reports or the rig checklist.

## Backend default files

- Read [config/backends/README.md](config/backends/README.md) and E14 before changing
  default configuration files. Keep one owning definition for each shared policy;
  do not copy heartbeat/timeouts into several independently editable files.
- Store only accepted values. Keep unresolved timing, device and algorithm choices
  unset. File presence does not enable a backend or accept a proposed topology.
- Classify every key under E14: a value an operator may change goes in
  `config/backends/<backend>_config.toml`; a fixed rule, selected library/algorithm or
  list of supported options goes in `contracts/policy/<backend>_policy.toml`. Changing a
  policy value needs its governing decision and a `policy_version` bump in both files.
- Update governing architecture when changing policy; encoding tuning defaults live
  in per-camera FFmpeg arguments/comments, not separate architecture decisions.
  Preserve explicit saved values and seeds, Setup validation,
  Start locking, and active-backend-only JSON logs in future implementation.
- Parse edited TOML and check values/units against the relevant accepted decisions.
  Do not claim a loader, runtime validation or rig measurements exist until they do.

## Work discipline

- For delegated code writing in ChatGPT/Codex, prefer Luna when available. In Claude,
  use the owner's configured Claude model; if a preferred model is unavailable, use
  a suitable available model without assuming cross-provider access. Follow explicit
  owner model selections. This preference does not itself authorize delegation.
  The supervising agent establishes interfaces, reviews each increment and resolves
  integration issues before acceptance, regardless of provider.

- Before every coding increment, apply [ARCH-002](architecture.md#arch-002)'s
  simplification and dependency review to the affected code, including agent-written
  code. Address concrete bloat before adding behavior; report validation limits.
- Keep the repository modular and easy to maintain, test and change under ARCH-002.
  Avoid large files when cohesive modules are possible; extract separable
  responsibilities before extending oversized files, with explicit interfaces and
  preserved state ownership.
- Apply ARCH-002's dependency boundaries: feature modules use focused records and
  explicit operations, never whole-runtime back-references. Run
  `python tools/check_backend_boundaries.py` alongside static checks; review its
  size warnings and document cohesive exceptions in the implementation report. Its
  warnings for backend source files over 500 lines prompt a cohesion review; they
  are not a file-size cap. Split only separable responsibilities under ARCH-002.
- Apply [ARCH-002](architecture.md#arch-002)'s test organization rule before adding
  tests: extend the owning behavior module by default and justify any new module
  by responsibility or fixture/platform needs. Do not add per-fix test files.
  When consolidating, compare collection and preserve scenarios, markers and
  fixture isolation; keep E15's execution boundary unchanged.
- Inspect existing files and version-control status before editing; preserve work
  made by the user or another agent.
- GPU workload placement follows SYS-002: RTX 5060 Ti rendering/projection/tracking
  GPU work, RTX 2080 Ti video encoding, and AMD integrated graphics for the operator
  display/GUI. SpikeGLX remains on the separate computer under SYS-001.
- Consult [SYS-003](architecture.md#sys-003) for the Python backend-language policy
  and its treatment of compiled dependencies and justified exceptions.
- Follow E15: run lightweight local implementation and authenticated communication
  tests; native Windows, hardware and full-workload acceptance run on the rig. Do not introduce a simulated-backend
  milestone without a new request. Encoder input-format and throughput feasibility
  (acquisition and Visual Stimulus) checks are explicitly deferred to rig verification
  in reports/rig-verification.md; continue other acquisition contracts. Do not treat
  deferred feasibility as proven or silently choose an input container. Check contract
  syntax and consistency, keeping those checks distinct from runtime/rig validation.
- Do not infer current machine specifications or performance guarantees from old
  benchmarks. Document evidence and its limits.
- Keep inline comments concise and use them for intent, constraints or non-obvious
  invariants; do not restate the code. Docstrings should explain behavior or
  interfaces briefly.

## Code Review Rules

- Flag behavior that conflicts with accepted decision IDs or changes deferred scope
  without authorization. Cite the owning decision and the concrete consequence.
- Check that refactors preserve original deadlines, exact process/generation identity,
  resource ownership and truthful output/cleanup evidence. Request focused behavioral
  coverage when those guarantees change; local tests cannot establish rig equivalence.
- Flag whole-runtime back-references, duplicated policy/state and generated-code edits
  under ARCH-002. Prefer existing focused helpers and owning behavior test modules.
- Verify that changed behavior, unresolved findings and validation limits reach the
  owning report and TODO/LOG. Distinguish pre-existing issues from changes introduced
  by the patch; leave routine formatting checks to the automated tools.
