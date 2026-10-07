# Controller and supervisor status

Updated: 2026-10-07. Implementation/source review is recorded for the controller,
supervisor, launcher, headless client and shared/native helpers. Local results below
have their original scope; Windows and full-workload acceptance remain pending.
[ARCH-001/002](../architecture.md#arch-001) owns scope and structure;
[E04](../docs/architecture/supervisor.md#e04) and
[E05/E07](../docs/architecture/experiment.md) and
[E06/E08](../docs/architecture/system-contracts.md#e08) own behavior.

## Current scope and review

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

The retained source review identifies these open items; they were not re-audited
during documentation consolidation. The controller does not yet apply camera/pulse
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

Remaining observations from the 2026-10-01 controller audit (not fixed):
`setup_admission.py` and `start.py` write `control.operations` entries directly,
bypassing `operation()`'s duplicate-ID helper; ingress duplicate handling still needs
review, and capacity is checked by `authorized()`. Terminal timestamp retention was
repaired and regression-tested in the authorized phase. A shutdown before activation does
not cancel pending Setup prompt futures the way `cancel_setup` does; and `cancel_attempt`
appends its reservation warning outside the lifecycle lock. Two state fields have no
reader in source and need an owner decision before removal: `default_intertrial_gap_ns`
(still validated from the configuration file) and `DeviceState.completed_camera_operation`
(only tests read it). `transport/ingress.py` has no direct test.

Recovery and native acceptance cases have one home in the
[rig worklist](rig-verification.md#runtime-recovery-and-regression-coverage).
Missing required participants fail explicitly; this report does not establish an
operational experiment or authorize firmware, GUI or tracking implementation.

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

Protocol type/Load/Save as sits beside Assets. Recordings now sits on Dashboard below
Session config, in two columns with adjacent checkbox/label pairs. Camera and Visual Stimulus video switches are independent of
required lifecycle metadata and acquisition/rendering. Tracking follows closed-loop
or Tracking velocities, with no Protocol tracking-status indicator; saved video choices
survive camera disablement. Device control remains in Devices. The review fixture
explicitly starts velocity saving Off without changing T14's saved/file default On.

The planner places a 208-pixel Trials list beside the fixed-height Trial timeline, with
full-width Epoch editor with inline Batch generate / Batch edit tabs below. Add/Delete sit at the foot of the trial list; draft
selection and existing deletion confirmation/history semantics are preserved.

- **Trial timeline:** a single full-program bar shows duration-proportional expanded
  epochs. Matching ordered stimulus settings, resolved asset records, projector mappings
  and background share a deterministic muted color; names/durations and scene/instance
  identifiers are excluded. Colors are visual cues, not new serialized types. Below,
  the overview spans from the projector labels to the right edge of their rows,
  with 16 additional logical pixels before current-epoch details. The
  current-occurrence name/duration precedes one row per enabled projector with ordered
  layers, asset names and compact motion/size/playback descriptions. Blank backgrounds
  are explicit, custom motion is labeled and elided text has full hover text.
  Click/Shift/Ctrl-or-Command select one/range/multiple source epochs across groups. No creation or parameter controls remain in this card. Repeated occurrences
  select the shared source, identified by the editor; example shuffle uses authoring
  seed zero, never Setup's retained seed. Unresolved timing shows sequence order.
  The card stays 366 logical pixels high, including its centered count/duration footer;
  additional layers scroll internally. The old resize grip and its unused helper were removed.
  Overview expansion is bounded to 2000 occurrences; exceeding this reports the limit
  rather than silently truncating. No enabled outputs shows an All row for offline inspection.
- **Batch generate tab:** local reference composition supports prepared files,
  a compact reference grid per projector with independently selected layers/assets,
  family-specific motion, looming or playback cells, exact duration and optional
  numeric variation rows with explicit lists or bounded sweeps. Paired lists or crossed combinations generate individually
  editable canonical source epochs with an optional persisted batch label.
  Repetition uses listed V08 child-block groups; count/duration preview precedes
  explicit insertion. Beginning/end, before/after a selected top-level block,
  replacement and interval distribution preserve groups, remap imported identities
  and validate the resulting trial
  atomically. Short reference durations do not prematurely apply E05's whole-trial
  minimum; final trial validation still enforces it. Generation supports at most 512
  condition combinations and 2000 expanded occurrences per operation. These are GUI
  operation bounds, not runtime policy. Variation rules target explicit reference
  layers and reject stale targets after composition changes.
  The authoring controls now place stimulus mode beside clock-formatted duration,
  compact three-digit repetitions, label and insertion; generation has no Order
  control. Epoch tab wheel gestures are ignored. The compact projector asset field
  accepts a pasted path from another row, validates it within the Assets folder and
  shows the full path while focused. File selection no longer leaves a success line;
  redundant section headings were removed. This follows G01 revision 72 and
  keeps the CephVR1 reference/variation/options and explicit batch-edit target flow.
  Windows traces found unparented reference-grid labels and projector dropdowns being
  shown as transient top-level windows. The grid now parents labels/controls before
  showing them and does not show projector selectors early. A visible launch with four
  simulated projectors, followed by mode and value updates, traced only Dashboard.
- **Batch edit tab:** Epochs and Parameter share a row. Duration has one epoch-wide
  clock value without a projector or layer selector. For stimulus parameters, each
  projector row has its own layer selector and corresponding value or asset picker;
  the arena uses one rig-wide row. Targets can be the timeline selection, all source
  epochs or a saved batch label. Mixed values are labeled; only edited projector
  rows change on one atomic Apply.
  Supported batch fields are
  shared duration, prepared asset, family-appropriate speed/direction/angular motion,
  playback start, opacity and symmetric linear looming start/end/growth duration.
  Batch file replacement supports texture exports and preserves physical speed when
  their declared tile dimensions change. Missing layers, incompatible units or invalid
  values reject the operation without partially committing earlier epochs. Untouched
  settings, overlays and other projector content remain intact. Pending changes block
  target/selection changes and saving until applied/discarded. One-source All parameters
  retains the complete custom function/state/feedback/input editors; complex imported
  functions remain intact rather than being approximated by the compact fields.

Structural Actions and layer controls stay in Epoch editor. Rename/duplicate/reorder/
remove require a single source; bulk parameter edits use Edit selected. Projector-local
mutations detach shared 2D content without changing remaining projector identities or
stack order. Arena remains rig-wide. Shared epoch boundaries and physical geometry are
unchanged. Group controls still support existing nested repeat/condition programs,
paired/product generation and reloadable custom condition values. V07 reset/continuity
settings are preserved; new independent instances do not promise inherited phase.
Undo/Redo keeps bounded per-trial history (40 snapshots) inside Actions. Trial deletion
confirms the named local draft, preserves files and leaves a blank draft when deleting
the last. Expanded sequence has Close. No table authoring, HUD/log, embedded rendering,
texture-design form, additional serialized grammar or backend dependency was added.

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
identities are remapped, the expanded result is bounded to 2000 epochs and failures
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
stacking rule. Camera HUD shows selected identity, participation, local connection/
preview status and requested trigger/PFS draft state. These are no hardware readbacks.
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
owned remain blocked by the current E07 controller guard; `owned-camera-edits`
tracks live-edit adoption. The final source trace found that accepted drafts previously never reached manual
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
activity log. Screen calibration/Synchronization/Rig geometry sections beneath inventory
keep cards fitted to their content. Independent pulse visibility/placement and
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
