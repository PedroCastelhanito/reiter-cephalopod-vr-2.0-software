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

## Verification recorded

Focused tests ran during implementation for shared helpers, controller state logic,
filesystem ownership, supervisor registry, and real local gRPC transport. Those
intermediate results do not constitute a pass for the final combined tree.

Final checks on 2026-09-29:

| Check | Actual result |
| --- | --- |
| `ruff check src tests tools` | Passed |
| `ruff format --check src tests tools` | Passed; 83 handwritten files formatted |
| `mypy --platform win32 src/cephvr` | Passed; 55 source files |
| `compileall -q src tests tools` | Passed |
| TOML parsing | All 15 configuration, policy and project files parsed |
| `python -m build --no-isolation` | Source archive and wheel built successfully |
| Package contents | Wheel source bytes match the final tree; 4 entry points and 18 generated type stubs; source archive retains 18 authoritative schemas |

These checks do not execute the final runtime suite or Windows APIs. The interrupted
trial path now waits bounded closure evidence, retains unknown outputs explicitly,
persists the Interrupted outcome once, and joins accepted recovery writes before
sealing. Its new regression tests await rig execution.

The owner requested the full run on the rig. New native Windows tests and the PowerShell
runner are prepared but have not been executed on Windows. See the
[test handoff](runtime-rig-test-handoff.md); record actual logs, failures, and skips there
before promoting platform behavior to verified.

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

Acquisition, VR, tracking, GUI and the E12 synchronization client are not implemented
by this stage. Their providers and wire interfaces are integration boundaries;
missing required modules fail explicitly. No fabricated Ready, successful recording,
or simulated-backend milestone is supplied.

Native Windows execution, hardware timing, actual device/encoder operation and full
experimental behavior remain unverified under
[E15](../docs/architecture/system-contracts.md#e15). The reviewed code is accepted for
the rig verification stage; full runtime acceptance is pending the Windows results.
Architecture acceptance alone does not establish implementation acceptance.
