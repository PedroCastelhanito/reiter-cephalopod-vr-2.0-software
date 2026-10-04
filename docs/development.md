# Development

[ARCH-002](../architecture.md#arch-002) owns package boundaries and formatting.
[SYS-003](../architecture.md#sys-003) owns the Python environment.
[ARCH-001](../architecture.md#arch-001) records the authorized implementation stage.
This guide documents commands and navigation; architecture remains authoritative.
Offline stimulus replay/export belongs to analysis software under V13. The experiment
package provides live execution and the saved recipe/evidence consumed by analysis.

## Project layout

```text
pyproject.toml              Package, dependency and tool configuration
src/cephvr/
  controller/              Lifecycle, RPC service, configuration and metadata
  supervisor/              Registration, health, interruption and shutdown
  acquisition/             Camera workers, frame paths, recording and MCU host control
  visual_stimulus/          Stimulus preparation, live rendering and evidence recording
  tracking/                Tracking configuration, native methods, runtime and recording
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
refactor. See the [acquisition implementation review](../reports/acquisition.md)
for its current acceptance and verification status. Visual Stimulus, tracking, synchronization and
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

## Dashboard frontend review

The native Dashboard uses the [shared GUI formatting rules](architecture/gui.md#g02).
On the Windows rig, install the GUI extra with `python -m pip install -e '.[dev,gui]'`.
For an existing macOS source environment, install its declared PyQt6 version directly;
the complete package's native DLLs are intentionally restricted to AMD64 Windows.

```sh
# Existing repository Python environment; no controller or devices are launched.
python scripts/start_gui.py
# Optional disconnected view, without local review controls:
python scripts/start_gui.py --read-only
# Equivalent module entry for review:
python -m cephvr.gui.review --review
```

The script selects the repository's `.venv` Python on Windows/macOS/Linux and works
from any working directory when called by its full path. Local review currently loads
four simulated 1920 × 1080 projector displays (2–5), assigned Front/Left/Right/Bottom.
Their Devices checkboxes drive the Protocol lanes, and Refresh retains this sample
inventory and its local choices. These are authoring fixtures, not hardware discovery;
`--read-only` does not load them.

The design review is identified in the window title and permits local subject edits.
Phase/observer inspection lives in the View menu. Session buttons report local intent
only. Dashboard currently shows a review candidate with horizontal read-only readiness
indicators inside System controls, above a full-width Setup button and equal Start/Stop
buttons. Phase appears in the content-height HUD only; the Activity log fills remaining height; subject age reads Age (dph). Setup requests New session from Ended. Stop cancels preparation in
Setting up/Ready, or opens Stop now / Stop after trial / Cancel during a session.
Stop now interrupts an active trial; the other option finishes it. Selections retain
current phase/control gates; Cancel or dismissal sends no intent.
Camera experiment enablement lives in Devices. Dashboard has a two-column Recordings
card below Session config for camera/stimulus video and Tracking velocities, and no
trial-plan editor or separate progress card. The top-right Previews button toggles a modeless selector; no open-window count is shown. First opening uses the
12-pixel gap/top alignment; later openings restore saved position from local
CephVR/Frontend GUI preferences and fit the compact selector to its current rows. The selector uses
labeled local visibility fixtures; it does not open runtime viewers or call devices. Close inspection windows
after checking changes, then reopen the reviewed GUI for the owner to inspect.
Devices has icon subtabs for Cameras, Microcontroller, Projectors and SpikeGLX with local
draft fields and review-only check actions. Visual Stimulus and Tracking remain placeholders. Omitting `--review` shows a disconnected,
read-only frontend. Neither mode is the managed GUI bootstrap or an experiment mode;
controller transport, control leases and runtime viewers remain unfinished.

Camera frontend review uses two labelled sample devices with per-device drafts and
experiment checkboxes. The View → Review active backends menu exercises protocol
preview gating until Protocol integration exists. Disabled sources remain dimmed.
Camera configuration sits below the inventory: role, trigger source, requested
Microcontroller trigger frequency and PFS path/Browse. Configure detailed parameters in
PylonViewer. Browse reads FrameStart trigger hints to update the dropdown, but never
applies SDK settings. Unknown hints remain unset. Microcontroller Scan ports and
Projectors Refresh displays enumerate local OS devices without opening hardware.
Only discovered COM ports are listed. Inputs (Projector flip) precedes Outputs
(Trial state/camera triggers). Rows contain pin and per-element Test controls, with
fixed rising-edge input and active-high Trial state; camera rates stay in Cameras. Projectors uses a compact
assignment table and desktop-layout diagram; Windows display indices are unavailable
on other systems and still need rig verification. These remain unsaved drafts;
trigger tests report not tested.
All pages
and subtabs share a fitted HUD above an expanding Activity log in the right column.

Dashboard output paths have an existing-folder picker and compact unfocused display
with full-path tooltips. Activity logs preserve the retained entry being read and
follow new entries only when already at the bottom. These controls edit local drafts.

Portable widget checks run with `QT_QPA_PLATFORM=offscreen python -m pytest tests/gui -q`
(set the environment variable separately in PowerShell). These tests and local
screenshots do not establish Windows integration or full-workload rig acceptance.

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

See the [runtime test handoff](../reports/rig-verification.md) for transfer,
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
| `cephvr.visual_stimulus.configuration` | `validate_display_profile(profile_json)` | Pure V19 validation, returning the exact nonempty `frozenset` of output IDs |
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
