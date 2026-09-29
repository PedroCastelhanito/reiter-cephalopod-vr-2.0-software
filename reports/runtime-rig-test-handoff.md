# Controller and supervisor test handoff

The owner selected the rig for the full test run on 2026-09-29. This is an execution
guide, not an architecture decision or a passing test report. Governing rules are
[ARCH-001/002](../architecture.md#arch-001), [E04](../docs/architecture/supervisor.md#e04),
[E05/E07](../docs/architecture/experiment.md), and
[E06/E08/E15](../docs/architecture/system-contracts.md).

## Prepare the rig checkout

The prepared `dist/cephvr-controller-supervisor-20260929.zip` contains the current
source checkout and this guide, excluding Git metadata, generated bindings, caches,
build output and local environments. Extract its `cephvr` folder to a new location
on the rig. The neighboring `.sha256` file identifies the transfer artifact.

Alternatively, transfer the current software folder, including `src`, `tests`, `tools`, `contracts`,
`config`, and packaging files. Do not copy the development machine's `.venv`, caches,
`build`, or `dist`; Python environments contain platform-specific binaries. The work
has not been committed or pushed, so cloning a remote alone does not obtain these files.
Keep any rig-specific configuration values and existing experimental recordings.

Install Python 3.11 on Windows if it is not already available. Use a new environment
in this project; keep the legacy CephVR environment separate under
[SYS-003](../architecture.md#sys-003). Close other test invocations using the same
checkout. The native tests use unique guards/jobs and temporary directories.

From PowerShell in the software root:

```powershell
.\tools\test_on_rig.ps1 -Install
```

`-Install` explicitly enables creating `.venv` and downloading/installing this
project's development dependencies. Later runs reuse that environment:

```powershell
.\tools\test_on_rig.ps1
```

If PowerShell's script policy blocks this local script, use a process-scoped launch:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\test_on_rig.ps1 -Install
```

This command does not change the machine's persistent execution policy.

## What the runner checks

| Check | Evidence produced |
| --- | --- |
| Python/package prerequisites | Python 3.11 and generated control bindings import successfully |
| Syntax, Ruff, Windows-target mypy | Handwritten code parses and meets configured static checks |
| Existing contract checks | Pure tracking and VR declarations remain consistent; these are separate from runtime behavior |
| Shared/controller/supervisor unit tests | Identity, bounds, deadlines, leases, evidence, reservations, and isolated failure-path logic |
| Loopback gRPC integration | Actual local controller/client transport, authentication and state-stream behavior |
| Native Windows tests | Creation-time nested jobs, retained exact process identity, kill-on-close, bootstrap pipes, ACLs, durable publication and role guards |
| Package build | Source archive builds a wheel with generated bindings using the installed compiler |

Native tests launch only their own temporary Python children. They do not start
the managed CephVR application, open cameras/projectors, or command SpikeGLX. A
Windows symlink-specific check may skip when the account lacks symlink creation
privileges; inspect the reported reason rather than treating the skip as a pass.

Success means every runner step exits zero and pytest reports no failures or errors.
Any skipped test remains unverified. Collect the actual result before accepting
platform behavior. The PowerShell runner and native assertions have not been executed
on the macOS development host.

## Results to retain

The runner prints its result directory, by default:

```text
%LOCALAPPDATA%\CephVR2\TestRuns\<timestamp>\
  prerequisites.log
  syntax.log
  ruff.log
  format.log
  mypy-win32.log
  contracts-tracking.log
  contracts-vr.log
  pytest.log
  pytest.xml
  package.log
  packages/
  summary.json
```

The first installation also writes `install.log`. Preserve the entire directory for
review; `summary.json` shows step exit codes and `pytest.xml` records individual
tests and skips. A custom destination can be supplied with `-OutputDirectory`.

## Remaining experiment verification

Passing this suite is acceptance evidence for the implemented controller/supervisor
and platform paths. It is not a successful experiment. Acquisition, VR, tracking,
GUI, and the synchronization client remain separate implementation stages; managed
startup explicitly fails while required modules are absent. There is no simulated
backend mode to substitute for them.

Hardware-marked tests require `-Rig`; the runner first checks that such tests actually
exist. Camera/MCU behavior, GPU assignment, rendering timing, encoder input-format and
throughput feasibility, real remote-recording behavior, and physical durability remain
the tasks in [rig-verification.md](rig-verification.md). Preserve its explicit deferrals
until actual results exist. Review the current
[implementation report](runtime-implementation-review.md) alongside test results.
