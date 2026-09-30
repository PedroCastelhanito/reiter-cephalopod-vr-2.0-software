# Controller and supervisor implementation review

Status: code review complete; prepared for full automated execution on
the Windows rig. This report records implementation and validation status, not another
decision register. [ARCH-001/002](../architecture.md#arch-001) owns scope and structure.

## Scope written

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

Three GPT-6 Sol agents implemented the delegated areas. The supervising model reviewed
their code and required corrections before acceptance, including exact cleanup fences,
partial-Setup resource accounting, missing command outcomes, cancellation races,
empty-video completion, actual Started/Stopped evidence, retained process ownership,
launcher startup/shutdown bounds, and metadata ownership/durability handling. Final
integration review also covered explicit startup recovery, persistent remote-stop
uncertainty, worker ancestry, command-result retention, incident progression, and
preserving the original shutdown deadline.

## Modular refactor review

The owner's 2026-09-29 instruction to review complexity before every coding increment
is recorded in [ARCH-002](../architecture.md#arch-002). This pass implements the
approved modular plan within E04–E08; no additional backend functionality or
framework dependency was added.

- Controller ownership is separated into control, lifecycle, device, incident,
  metadata, transport and startup modules. Supervisor ownership is separated into
  registration, health, recovery, shutdown, status, outbound transport and startup.
  See [development navigation](../docs/development.md) for the directory map.
- Components receive specific typed records, peer interfaces and named operations.
  They share authoritative records and the original synchronization objects. Setup
  replaces `LimitsState.current`, so subsequent operations observe reloaded limits;
  consumers do not retain stale startup copies.
- Coordinators retain the application API and task supervision. RPC authentication,
  replay lanes and bounded report ingress remain in transport. Runtime queries
  replace transport/startup access to private dictionaries and locks.
- Durable metadata writing, output reservation, persistence coordination and trial
  logging have separate owners. Superseded `storage.py` and `devices.py` were removed;
  callers and tests use owning component interfaces without compatibility wrappers.
- Setup, camera commands, trial execution and supervisor registration use named
  stages. Existing launch registry and evidence predicates remain focused helpers.
  The standard library and existing dependencies suffice for this restructuring.

Three lower-model agents performed separate extractions under primary-model review.
The review compared against a saved copy of the initial working tree, including its
uncommitted changes. Storage classes/functions matched after mechanical helper
renames. Reviewed lifecycle extractions retained branch, lock and await ordering;
additional stage calls were checked for early-return and exception behavior. Review
caught and corrected a shadowed activity helper, stale limits injection, a warning
retention change, and a changed shutdown error string before acceptance. These static
comparisons are evidence of preservation, not execution of the behavior.

The controller module entry point also now calls its existing CLI when launched with
`python -m cephvr.controller.main`, as the supervisor already expects. The missing
module guard was an existing startup defect. A regression check is prepared for the rig.

## Verification recorded

A 2026-09-29/30 review (Sonnet audits, Opus verification) fixed defects in
command admission, lifecycle finalization, metadata durability, recovery, device
evidence, supervisor health/shutdown, helper release and the launcher. The rules those
fixes refine are recorded under [E04](../docs/architecture/supervisor.md#e04) and
[E08](../docs/architecture/system-contracts.md#e08), and in the
[Windows launch](../contracts/windows-launch.md) and
[central metadata](../contracts/central-metadata.md) contracts. Each fix has a focused
regression test, now retained in its owning behavior module under `tests/`
(see the test consolidation record below).

Earlier portable (macOS, mocked native API) results, run 2026-09-30 before
the backend audit below:

| Check | Command | Result |
| --- | --- | --- |
| Tests | `python -m pytest tests -q` (`asyncio_mode = "auto"`) | Controller, supervisor, shared, platform, launcher and client pass except 7 tests blocked by the acquisition `unknown config keys basler/recording.tools` loader failure; acquisition tests are owned by the [acquisition review](acquisition-implementation-review.md); Windows-native tests skip |
| Lint/format | `ruff check src tests tools`; `ruff format --check src tests tools` | Passed |
| Types | `mypy --platform win32` | Passed, 323 source files |
| Boundaries | `python tools/check_backend_boundaries.py` | 0 violations; size reviews below |

No native Windows, device or rig behavior was executed; those checks remain under
[E15](../docs/architecture/system-contracts.md#e15) and the
[test handoff](runtime-rig-test-handoff.md). The first rig run should also record the
Windows venv interpreter process tree listed in [rig verification](rig-verification.md).

Size reviews (over 500 lines, cohesive): controller `assembly.py` (single component
graph), `runtime.py` and `lifecycle/interruption.py` (interrupt/finalize joins), and
supervisor `shutdown.py` (ordered shutdown). Extracting finalization and shutdown
interruption helpers is the next split if these change again.

Open items, not defects of reviewed code: the controller does not yet apply camera/pulse
edits to owned editing/preview cameras (contracts/acquisition/configuration-control.md);
until it does, such edits are rejected while a camera is owned. Setup and manual
camera readback still use separate resolution/adoption paths. Supervisor worker
launches are never released, so their registry entries persist for the run.

Known low-severity limits left for a later pass: after accepted shutdown intent the
supervisor checks for controller loss at shutdown entry and before backend Shutdown,
not continuously; a pending backend-exit expiry or launch timeout can still raise a
safety fence during shutdown; a PlanLaunch replayed after its released entry is
pruned (only at registry capacity) plans anew; and a mid-session late-Finished
`recovery` event makes startup inspection treat an intact log as unconfirmed (the
safe fallback).

## Recovery limits to exercise on the rig

- Startup repair requires the prior launcher's durable receipt proving all owned
  processes absent. A missing receipt preserves the blocker; a free lock or missing
  process name does not replace that proof.
- Combined configuration/log inspection is bounded to the configured metadata byte
  capacity (currently 64 MiB). Oversized, corrupt, or incomplete administrative logs
  are preserved and described in a separate recovery report. This path does not
  certify scientific outputs or reconstruct their closure.
- Recovery appends label timestamps as observations by the new application, with
  actual historical end times unconfirmed. Unknown remote SpikeGLX stopping remains
  visible with the saved endpoint/run when available.
- An uncertain recovery append is not retried in the same application. Failed
  durable pointer publication blocks reservation release and another Setup.

## Acceptance boundary

This record covers the controller/supervisor stage. The subsequent acquisition
host implementation has its own [review](acquisition-implementation-review.md) and
[rig handoff](acquisition-rig-test-handoff.md).

Acquisition, VR, tracking, GUI and the E12 synchronization client are not implemented
by this stage. Their providers and wire interfaces are integration boundaries;
missing required modules fail explicitly. No fabricated Ready, successful recording,
or simulated-backend milestone is supplied.

Native Windows execution, hardware timing, actual device/encoder operation and full
experimental behavior remain unverified under
[E15](../docs/architecture/system-contracts.md#e15). The reviewed code is accepted for
the rig verification stage; full runtime acceptance is pending the Windows results.
Architecture acceptance alone does not establish implementation acceptance.


## Backend code audit — 2026-09-30

The owner requested a review of comments, oversized/unnecessary code, complexity,
compatibility and file count. This pass scanned all 323 handwritten Python source
modules, inspected dependencies, duplicate definitions, unreferenced symbols and
large-module responsibilities, then reviewed and corrected the concrete findings
below. Generated bindings were excluded from manual editing. The scope includes
controller, supervisor, acquisition and their launcher/client/shared/native helpers;
it is a structural and targeted source audit, not an exhaustive behavioral proof.
Existing uncommitted work was preserved against a saved starting-tree snapshot.

### Findings corrected

| Finding | Change and governing rule |
| --- | --- |
| Shipped acquisition configuration had unsupported empty `basler` and `recording.tools` sections, causing strict loading to reject it | Removed those obsolete sections. TOML comparison confirms every setting and policy version is unchanged; static comparison now matches the owning allowlist. Existing loader regressions remain prepared for the rig. [E07/E14](../docs/architecture/system-contracts.md#e14) |
| Native NVENC maximum dimensions were collected but never consumed by encoding validation | Require positive device limits for the exact codec/pixel format and check the resolved post-filter width and height before preparation succeeds. Explicit scaling is evaluated; no automatic resize or fallback. [A08](../docs/architecture/acquisition.md#a08) |
| Full FFmpeg help could add another encoder's private option values/ranges, including forced-IDR support | Parse selected-encoder help separately; take only the supported common fields from the `AVCodecContext` section. This follows FFmpeg's [generic/private AVOption distinction](https://ffmpeg.org/ffmpeg.html#AVOptions). [A08](../docs/architecture/acquisition.md#a08) |
| Invalid lookahead text escaped as raw `ValueError`; very large bitrate text could become infinity | Validate individual options before device comparisons, reject nonfinite rates and translate oversized integer conversion failures into `EncodingOptionsError`. Source-layout errors use the same public validation boundary. [A08](../docs/architecture/acquisition.md#a08) |
| GPU discovery lacked a platform guard and malformed UUID/missing driver exports escaped its declared error boundary | Normalize these to `WindowsLaunchError`, retaining exact UUID selection and required RTX 2080 Ti placement. Python documents [Windows DLL loading and missing-symbol failures](https://docs.python.org/3.11/library/ctypes.html#loading-shared-libraries); no driver fallback was added. [SYS-002](../architecture.md#sys-002) |

### Simplification, comments and file count

Under [ARCH-002](../architecture.md#arch-002), the simpler viable changes use existing
modules and the standard library; no dependency or framework was added.

- `shared/incidents.py` mixed shared proof validation with mutable controller
  retention. Moved `IncidentRegistry` and its two owner-specific exceptions into
  `controller/incident/registry.py`; callers import that owner directly. The shared
  file shrank from 820 to 549 lines. AST comparison confirms the moved classes'
  executable bodies are unchanged, including capacity checks and commit order.
- `validate_arguments` shrank from 253 to 124 lines. Token parsing, native feature
  checks and metadata-key checks are named stages in the same file. Color enums
  share the existing option-validation table, and redundant checks were removed.
  This simplifies the validation path while retaining its explicit restrictions.
- Consolidated the duplicate externally triggered camera predicate and duplicate
  sessionless command-admission predicate into their existing helper owners.
- Removed four unreferenced acquisition protocols and one unused camera-resource
  key helper after repository-wide reference checks. Live peer interfaces remain.
- Merged the 12-line `worker/requests.py` accessor into `worker/ports.py`. The new
  incident owner offsets that removal: runtime source-module count remains 323.
  Tiny error/protocol modules with multiple consumers and public configuration,
  schema and state exports remain justified boundaries. Generated bindings and
  package initializers are required structure, not redundant backend implementations.
- Every handwritten source module now has a module docstring. Added concise intent
  comments/docstrings at the touched validation, evidence-admission, recovery and
  ownership boundaries. Straightforward delegates and field assignments were not
  padded with repetitive comments.

Fifteen files still exceed the 500-line review threshold. The boundary tool reports
12 backend files; manual inventory also covers the three shared/native files.
Remaining cohesion exceptions are bounded by responsibility:

| Area | Why the current boundary is retained |
| --- | --- |
| Controller `assembly.py`/`runtime.py`, acquisition `runtime.py` | Explicit component wiring and thin public operations; extracting more delegates would add indirection without separating state ownership |
| Controller `lifecycle/interruption.py`, supervisor `shutdown.py` | Existing interruption/finalization and ordered shutdown joins retain their original deadlines and ownership; peer operations already live in separate components |
| Acquisition `camera/basler.py`, `microcontroller/owner.py` | One SDK/serial lifetime per owner; settings, metadata, waits, parsing and I/O are already delegated |
| Acquisition `worker/capture_runtime.py`, `worker/execution.py`, `worker/service.py` | Prepared native attachment lifetime, serialized operation dispatch and RPC admission respectively; capture, stopping, reporting and recording have separate owners |
| Acquisition `recording/session.py`, `coordinator/trial_lifecycle.py` | Recording sequencing and exact lifecycle evidence joins; process, file, filter and validation helpers already have separate modules |
| Shared `incidents.py`, native `jobs.py`/`security.py` | Pure E06 topology/proof checks after registry extraction; exact Windows process/job ownership and ACL/handle operations with their ABI declarations |

These exceptions do not permit unrelated additions. Further behavioral refactoring
should be driven by a concrete responsibility split and the rig regression results,
not a target file count. Other unreferenced public shared/native helpers were identified
as candidates, not removed solely on textual reference counts; future contract users
and API obligations need review before removing those surfaces.

### Verification and limits

- Ruff lint and formatting: passed across `src`, `tests`, `tools` (439 files).
- Strict Windows-target mypy: passed for 323 source modules and the two new/extended
  regression modules (325 checked together). Test imports were corrected during
  static verification; no missing-import suppression was added.
- Backend dependency checker: 269 modules, zero violations; size warnings reviewed above.
- Python source compilation and parsing of all 15 backend config/policy/project TOMLs
  passed. The acquisition config's leaf values are unchanged and its keys/empty
  tables now match the owning schema allowlist.
- Installed environment dependency consistency (`pip check`): passed. This does not
  validate the Windows acquisition extra, SDK/driver ABI or a deployment lockfile.
- Source distribution and wheel build with existing dependencies (`--no-isolation`):
  passed, including binding generation. Package contents include the new incident
  owner and exclude the removed request-accessor module.
- Test discovery: 483 tests collected successfully. Added 22 regression cases for
  selected-encoder option isolation, post-filter dimensions, invalid numeric/metadata
  arguments, and GPU selection/error boundaries. Existing configuration and incident
  tests cover the corrected config and relocated owner.
- Working-tree whitespace and the audit-only diff were reviewed against the starting
  snapshot; the incident extraction was additionally compared by AST.

No test bodies or native/hardware operations were executed in this audit. The owner
selected the Windows rig for behavioral verification under
[E15](../docs/architecture/system-contracts.md#e15); run `tools/test_on_rig.ps1` there.
The earlier seven loader-blocked test results above remain historical results,
not rerun passes. Actual FFmpeg help from the installed build, driver exports,
SDK wait/GIL behavior, encoding throughput and full experiment behavior remain rig
checks. The existing deferred backends and hardware inputs remain outside this pass.

## Test consolidation — 2026-09-30

The owner requested stable test organization and a rule for future contributions.
[ARCH-002 revision 5](../architecture.md#arch-002) owns that rule; `AGENTS.md` and the
[development guide](../docs/development.md#checks) direct contributors to it. This
pass changes test organization and navigation only; runtime code is unchanged.

| Owner | Test modules before | After |
| --- | ---: | ---: |
| Acquisition | 40 | 22 |
| Controller | 37 | 23 |
| Supervisor | 10 | 7 |
| Shared | 7 | 7 |
| Platform | 7 | 5 |
| Launcher | 2 | 1 |
| Client | 2 | 2 |
| **Total** | **105** | **67** |

All 24 fix-named modules were absorbed into behavior owners or renamed for their
distinct responsibility. Mixed supervisor review bundles now live with registration,
registry, health, status, recovery, shutdown and outbound tests. Related acquisition
tests share modules for configuration, preview, pulse evidence, recording, session
preparation and worker admission. Shared command-ledger tests have one owner.
Controller and supervisor reuse their existing support modules; test-to-test imports
were eliminated. No fixture framework, dependency or extra support file was added.
Both rig handoffs now reference the current module names.

Review retained the 501-line controller lifecycle-command module because its cases
share interruption/finalization ownership and one active-attempt fixture. The
591-line acquisition worker-foundations module was not extended. Its queue, warning
and capture cases remain available for a later responsibility split if changed;
neither size is a reason to add unrelated tests. Existing runtime size exceptions
from the backend audit remain unchanged.

Validation against a snapshot of the pre-consolidation working tree:

- Pytest collection retained all **483 locally collected cases**, with identical
  case names, markers and fixture dependencies. The native Windows test module and
  the ring module's platform skip remained byte-for-byte unchanged.
- AST comparison preserved all **451 test functions** and **678 original top-level
  definitions**, allowing the explicit helper renames and identical-helper merges.
  A further **3,218 module-binding comparisons** checked that moved definitions
  still reference their original helpers/imports or equivalent UUID wrappers.
- Ruff lint and formatting passed for source, tests and tools; all 74 test/support
  modules compiled. Windows-target mypy passed for 323 runtime modules and for the
  combined runtime/acquisition-test scope (346 modules). The test-only mypy command
  omitted source discovery; rerunning with `src/cephvr tests/acquisition` resolved
  that invocation issue without suppressing errors or changing configuration.
- The backend boundary check reported **0 violations** across 269 modules. No
  imports between test modules or stale documentation references to removed test
  files remain.

Collection and static equivalence do not establish behavioral success. No test bodies
were run in this consolidation; execution remains on the Windows rig under
[E15](../docs/architecture/system-contracts.md#e15), using `tools/test_on_rig.ps1`.
