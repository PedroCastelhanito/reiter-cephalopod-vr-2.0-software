# Guidance for CephVR2.0 contributors and AI agents

This file applies to this directory and its descendants.

## Architecture is the starting point

- The owner has explicitly authorized runtime implementation and tests for the
  experiment controller, supervisor and acquisition host backend, including their
  required shared helpers, launcher, native mechanisms and headless client.
  Acquisition firmware, flashing and other backend runtimes remain outside this
  stage. Follow GOV-001 and ARCH-001;
  other backend implementation stages still need owner selection. Existing
  declarative schemas, interfaces and contract checks remain authoritative inputs,
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
  moving to another backend. Discuss tracking last under GOV-001. Keep hardware inputs
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

- Use Luna models for delegated code writing. The supervising model establishes
  interfaces, reviews each increment and resolves integration issues before acceptance.

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
  size warnings and document cohesive exceptions in the implementation report.
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
- Follow E15's rig-first behavioral verification plan: the owner will test after
  the main architecture is established. Do not introduce a simulated-backend
  milestone without a new request. Encoder input-format and throughput feasibility
  (acquisition and VR) checks are explicitly deferred to rig verification
  in reports/rig-verification.md; continue other acquisition contracts. Do not treat
  deferred feasibility as proven or silently choose an input container. Check contract
  syntax and consistency, keeping those checks distinct from runtime/rig validation.
- Do not infer current machine specifications or performance guarantees from old
  benchmarks. Document evidence and its limits.
