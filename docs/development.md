# Development

[ARCH-002](../architecture.md#arch-002) owns package boundaries and formatting.
[SYS-003](../architecture.md#sys-003) owns the Python environment.
[ARCH-001](../architecture.md#arch-001) records the authorized implementation stage.
This guide documents commands and navigation; architecture remains authoritative.

## Project layout

```text
pyproject.toml              Package, dependency and tool configuration
src/cephvr/
  controller/              Lifecycle, RPC service, configuration and metadata
  supervisor/              Registration, health, interruption and shutdown
  acquisition/             Camera workers, frame paths, recording and MCU host control
  launcher/                Persistent application containment owner
  client/                  Headless control client and command-line interface
  shared/                  Process-local identity, deadline and control helpers
  platform/windows/        Native jobs, process handles, guards, pipes and ACLs
  <component>/v1/          Generated Protobuf/gRPC bindings; never hand-edit
tests/<owner>/             Focused local runtime and integration tests
tools/                     Binding generation and package build hooks
contracts/                 Authoritative schemas, interfaces and fixed policies
config/                    Operator settings and ignored local history
docs/                      Architecture and supporting guides
reports/                   Reviews, rig evidence and emergency reports
```

Within each backend, `runtime.py` exposes application operations and supervises tasks.
The controller delegates explicit component construction to `assembly.py`; its typed
assembly inputs stay at this composition boundary.
`state.py` holds authoritative records; `ports.py` defines outbound peer interfaces.
Components receive their specific records and operations, with the existing event
loop and synchronization. RPC adapters authenticate and delegate through public
application operations. They do not reach into private runtime state.

| Controller area | Responsibilities |
| --- | --- |
| `control/` | Client control, retained operation outcomes and current views |
| `lifecycle/` | Setup, handoffs, evidence waits, trials, interruption and cleanup |
| `device/` | Camera commands/readback, previews and display initialization |
| `incident/` | Incident admission, bounded retention/operator choices and confirmed scope changes |
| `metadata/` | Reservations, durable file publication, bounded writer, completion tracking and trial logs |
| `transport/` | Authentication, bounded command replay and priority report admission |
| `startup/` | Bootstrap validation, provider discovery, application assembly and authority monitoring |

Supervisor operations live in focused `registration`, `health`, `recovery`, `shutdown`
and `status` modules. `registry` owns exact launch records; `outbound` implements peer
RPCs; `service` authenticates inbound calls; `startup` assembles process resources;
`main` enters the CLI. These modules share records and explicit operations, with
no back-reference to the whole runtime.

Acquisition navigation:

| Area | Responsibilities |
| --- | --- |
| `configuration.py`, `config/` | Controller providers, operator defaults, fixed policies and lightweight validation |
| `coordinator/`, `state.py`, `ports.py` | Worker ownership, exact report admission and logical-backend lifecycle |
| `worker/` | Serialized camera ownership, command handoff, capture and worker services |
| `camera/` | Exact-device SDK access, settings, capabilities, native metadata and joint waits |
| `buffers/` | Native layouts, shared rings, private pixel pools and bounded recording accounting |
| `recording/`, `recording_schema.py` | Encoder validation/launch, frame logs, output identity and durable closure |
| `microcontroller/` | Bounded protocol parsing, serial ownership and pulse evidence |
| `transport/` | Authentication, original deadlines, command retention and outbound RPC adapters |
| `shared/pixels/` | Reusable conversion with consumer-owned buffers and converter state |
| `platform/windows/` | Native mappings/events, atomic slots, cancellable streams and exact-file synchronization |

Acquisition `state.py` exports the authoritative records from `coordinator/state/`;
it does not duplicate them. Within `coordinator/`, session catalogue publication, camera preparation and tracking
confirmation are separate from trial preparation, Schedule/Release and termination.
Manual device readback, previews, viewer transfers and pulse changes have their own
components. Cleanup joins exact worker, output and native-resource evidence.
Within `worker/`, the serialized operation coordinator delegates capture, preview,
trial stop, recording completion, warnings and report delivery. These components
share the owning state records; extraction must not create another source of truth.

The current stage implements acquisition host code, following the controller/supervisor
refactor. See the [acquisition implementation review](../reports/acquisition-implementation-review.md)
for its current acceptance and verification status. VR, tracking, synchronization and
GUI runtimes remain separate stages. Generated message bindings alone do not implement
those components. Managed
application startup reports missing required modules and exits; there is no replacement
backend or fabricated Ready state. The application is not ready for experiments until
its required components and Windows/rig checks are complete.

## Environment

Create a fresh Python 3.11 environment, separate from the legacy CephVR environment.
From the software root:

```powershell
# Windows PowerShell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

```sh
# macOS/Linux with Python 3.11 installed
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Below, `python` means that environment's interpreter. Editable installs and wheel builds
regenerate the bindings using the compiler pinned in `pyproject.toml`. After editing a
schema during development, regenerate without reinstalling:

```sh
python tools/generate_contracts.py
```

The build backend delegates packaging to setuptools after generation. Source archives
include the authoritative `.proto` files and build tools; wheels contain generated
Python and type stubs. Source packages include only `src/cephvr`. Existing declarative
Python models in `contracts/` are not copied into competing runtime models.

Runtime dependencies and development tools are declared in `pyproject.toml`. This is
not a validated Windows deployment lockfile. Config and policy files remain in the
software checkout; pass that checkout as `--software-root`. A wheel alone does not
contain a complete rig installation.

The acquisition hardware dependencies are a separate extra. On the Windows rig,
install `.[dev,acquisition]` in the project environment. The pypylon, NumPy and
pySerial pins come from rig inventory; pinning them does not establish compatibility
or performance. FFmpeg remains an external PATH prerequisite under A08.

## Checks

```sh
python -m ruff check src tests tools
python -m ruff format --check src tests tools
python tools/check_backend_boundaries.py
python -m mypy --platform win32
python -m build
```

Apply formatting with `python -m ruff format src tests tools`. The Windows target is
explicit for static checking of native API declarations; it does not execute Windows
code. Generated bindings are excluded from handwritten-code checks. Existing contract
checks remain separate and follow the [contract index](../contracts/README.md).

The module-boundary check parses source without importing or executing it. It rejects
feature imports of runtime/entry/service modules and private runtime access. Files
over 500 lines produce a cohesion-review warning, not an automatic failure or a
target to split arbitrarily. Record justified exceptions in the implementation review.

Prepared tests cover pure invariants, filesystem ownership, state transitions and real
loopback gRPC calls. The owner selected the rig for behavioral execution, including
these hardware-independent tests. Injected collaborators in unit tests do not supply a simulated
backend product mode. Windows tests use the `windows` marker and require Windows;
hardware tests use `rig` and require the prepared rig. Markers alone do not establish
coverage. Record actual commands/results in implementation and rig reports.

Follow [ARCH-002](../architecture.md#arch-002) when adding or organizing tests.
Choose the owning backend and existing behavior module first: controller admission,
Setup, lifecycle or evidence; acquisition configuration, capture, recording or cleanup;
supervisor registration, recovery or shutdown. Shared mechanisms and native platform
boundaries have their own directories. Reused controller and supervisor setup lives
in their existing support modules. Test modules do not import other test modules.
For a reorganization, compare `python -m pytest --collect-only -q` before and after,
including case names, markers and fixture dependencies. Collection checks discovery
and imports; it does not run assertions or replace the rig run.

[E15](architecture/system-contracts.md#e15) governs behavioral verification. Passing
local tests or compilation does not prove Windows containment, hardware timing, device
behavior, GPU placement, encoder throughput or physical storage durability.

The owner selected the Windows rig for the full automated test run. From PowerShell
in the software root, use `./tools/test_on_rig.ps1 -Install` for the first run, then
`./tools/test_on_rig.ps1` for subsequent runs. The script creates a fresh project
Python 3.11 environment only with `-Install`; it does not use the legacy CephVR
environment. It runs static checks and all non-hardware tests, including native
Windows tests, the existing pure contract checks, and the package build. It saves
logs, `summary.json`, and `pytest.xml` under
`$env:LOCALAPPDATA/CephVR2/TestRuns/<timestamp>`.

See the [runtime test handoff](../reports/runtime-rig-test-handoff.md) for transfer,
expected results, and the distinction between native platform tests and a complete
experiment. `-Rig` is reserved for actual hardware-marked tests and refuses to imply
hardware coverage when no such tests have been implemented.

## Later backend integration points

The controller loads these providers from an installed backend package. They must
use the owning contract models and writer definitions; none is a device simulator.

| Module | Provider | Role |
| --- | --- | --- |
| `cephvr.<backend>.configuration` | `validate_configuration(candidate)` | Pure E07 validation, returning `ValidationResult` |
| `cephvr.<backend>.configuration` | `load_file_policies(software_root)` | Strict owning TOML/policy loader, returning its typed policy message |
| `cephvr.vr.configuration` | `validate_display_profile(profile_json)` | Pure V19 validation, returning the exact nonempty `frozenset` of output IDs |
| `cephvr.<backend>.recording_schema` | `get_writer_schemas()` | Mapping of `(backend, output_tag, extension)` to `controller.planning.WriterSchema`, shared with actual writers |
| `cephvr.synchronization.client` | `create_controller_client(software_root=..., controller_generation=...)` | Controller-owned E12 client implementing `controller.ports.SpikeGLXPort`; constructor does not begin remote work |

Missing required providers produce explicit unavailable results. Definitions alone
are insufficient for device readiness, successful output creation, or runtime acceptance.

## Entry points

`cephvr` owns Windows application containment and launches the supervisor.
`cephvr-supervisor` and `cephvr-controller` consume protected inherited bootstrap
handles supplied by their registered owner. They are not standalone experiment modes.
Use `--help` for their current options.

`cephvr-control` uses the same controller RPCs and live control lease as the GUI:

```sh
cephvr-control --software-root /path/to/software --controller-generation <exact-running-generation> status
```

Mutating commands establish a live state stream and acquire control. Taking control
from another client requires `--takeover`. The CLI reports command IDs and distinguishes
admission, completion, required input and an unconfirmed transport outcome. It never
reissues ambiguous work automatically. Bootstrap secrets stay out of command lines,
configuration and logs.

Local environments, generated bindings, caches, build outputs and
`config/last_configuration.json` are ignored by Git. Evidence in `reports/` remains
visible. [E04](architecture/supervisor.md#e04) owns experimental output locations.
