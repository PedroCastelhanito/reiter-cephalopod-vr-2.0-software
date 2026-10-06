# Live device connection evidence — 2026-10-06

Source: `7b250de613c9d3568932eb648974d9e4964c2c35`, with the current
health, participation, worker-admission and native-shutdown fixes. The direct JSON records the health source
SHA256. Commands used the repository Windows Python 3.11.15 environment; timestamps
in the JSON are Asia/Tokyo. Applicable rules: [A10/A11](../../docs/architecture/acquisition.md#a11),
[G01](../../docs/architecture/gui.md#g01), [E08/E15](../../docs/architecture/system-contracts.md#e15).
Current assessments belong in [acquisition](../acquisition.md) and
[runtime](../runtime.md#dashboard-frontend-implementation).

## Results and method

- Latest preview investigation: [reported snapshot](preview-failure-snapshot.json),
  [SDK resolution probe](preview_resolution_probe.py), [successful repaired SDK
  resolution](preview-resolution-probe.json), and [managed restore/connections](preview-bridge-managed-check.json).
  The initial direct probe was blocked by exclusive managed camera ownership;
  after authenticated application shutdown, resolution reproduced WaitObject's
  integer-HANDLE TypeError. The typed bridge repairs that constructor, with no
  grabbing/pulses during the resolution probe. Native wait test verifies duplicate
  lifetime and a Python thread waking a blocked SDK wait. Portable affected suite:
  410 passed/2 skipped/1 native deselected; native plus preview checks: 6 passed;
  final focused ownership checks: 29 passed. [Windows wheel build](preview-bridge-wheel-build.log)
  and [source/wheel build](preview-bridge-package-build.log) succeed and contain
  both generated bridge artifacts. The 26.6 wheel was inspected only, not installed;
  it still omits WaitObjectEx. Stock 26.3.1 remains pinned. The owner subsequently
  authorized Behavior-only D10/Line4 pulse/preview checking. Later startup
  [stderr](preview-final-runtime.stderr.log) again records independent heartbeat
  rejection; it is not a camera-binding failure or a resolved native startup issue.

- `.venv/Scripts/python.exe direct_connections.py` from this directory's script
  path: [real readback](direct-connections.json), Arduino Uno COM8 protocol 2,
  firmware `cephvr2_uno_1`, stopped outputs, zero malformed/unmatched replies,
  confirmed serial close. pylon 11.4.0.1134 opens and closes serials
  `40065509` / acA4112-30uc and `40747103` / a2A2464-77umPRO. The unavailable
  tracking TriggerActivation node is reported explicitly. No node writes or capture.
- `.venv/Scripts/python.exe scripts/start_runtime_gui.py`: initial sandbox launch
  failed on stale `CAMERA_COMMAND_KIND_TEST_CONNECTION` bindings and restricted
  credential/recovery writes. `.venv/Scripts/python.exe tools/generate_contracts.py`
  regenerated all 19 schemas. Further launches used the normal launcher outside
  the sandbox, retaining stdout/stderr here.
- [Initial managed checks](initial-managed-connections.json) and
  [second attempt](second-managed-connections.json): authenticated MCU Connect
  succeeded. STATUS was an invalid diagnostic-status query without a preceding
  pin test; its failure is not a firmware connection failure. Acquisition then
  caused shutdown with MICROCONTROLLER_KEEPALIVE_WINDOW_EXHAUSTED; raw emergency
  reports remain at their runtime-created paths:
  [first](../emergency-491358901832100-dedfa149-a465-4286-ac71-f59b4987d7b9.json),
  [second](../emergency-491448521718600-44340f54-ca3c-4de2-aca8-8aa16f1867b9.json).
- Corrected health scheduling skips only a proven unconfigured, zero-watchdog,
  stopped-output observation. Later configured obligations and uncertain/running
  output failures retain their existing deadlines. ARCH-002 review reused the
  current health owner and observation; no dependency, process or policy was added.
- [Third](third-managed-connections.json) and
  [fourth](fourth-managed-connections.json) attempts could not reach acquisition;
  raw stderr shows native job-inspection error 5. [Latest managed attempt](managed-connections.json)
  passed MCU Connect and the temporary diagnostic configuration update, then the
  behavioral camera command exceeded the probe's 12-second wait. Its empty error
  text means TimeoutError, not success. The next camera command and restoration
  were rejected because an operation was still pending. The generation subsequently
  exited with CHILD_EXITED; complete controller-backed camera release is unconfirmed.
  No configuration history save was requested.

- Current follow-up: [flags-only enablement](enablement-runtime.json) accepts both
  cameras with absent trigger sources, survives 25 seconds and restores the draft.
  Method: `.venv/Scripts/python.exe enablement_runtime.py <generation>` against
  the normal managed launcher; no camera open, capture or pulses in this probe.
  Earlier [first run](enablement-first-runtime.json) exited; subsequent acquisition
  diagnostics isolated WORKER_HEARTBEAT_SILENCE during worker PlanLaunch. Temporary
  stage tracing showed failure before process creation and was removed. Source
  review found missing protected child-token metadata and explicitly empty work.
  Both are repaired under E08/A02; rejected PlanLaunch now reaches the command owner.
- Current [managed connection result](managed-connections.json) supersedes earlier
  failures: COM8 Connect and both camera TEST_CONNECTION commands succeed; both
  cameras report device_open=false and original configuration restoration succeeds.
  Command: `.venv/Scripts/python.exe managed_connections.py <generation>`.
  [Runtime stderr](worker-launch-fixed.stderr.log) retains subsequent diagnostics.
  Prior failed results remain in managed-before-enablement.json,
  managed-second-enablement.json, managed-silence-diagnostic.json and
  managed-worker-launch-before-fix.json. No pulse or capture command was issued.

## Validation and limitations

- Pending-operation follow-up: [blocked snapshot](pending-camera-snapshot.json)
  retains repeated failed ReleaseManualCameraState operations while Behavior is
  closed and Tracking is absent. A fresh coordinator now publishes explicit initial
  closed states for both roles. Access still marks only its role pending; controller
  unknown-state cleanup checks remain strict. Worker small edits use the existing
  normal result reservation; full settings/PFS resolution keeps the large one.
- [Combined live result](lease-camera-recheck.json), from
  `.venv/Scripts/python.exe lease_camera_recheck.py <generation>`, restores the
  preserved idle draft, imports/finishes Behavior PFS, checks both cameras, releases
  control, reacquires and checks both again. Four connection commands, PFS import,
  draft restoration and both cleanup operations pass. Both cameras are closed/no
  preview/no cleanup pending. Control released; GUI/runtime left running. Initial
  lease-only success remains in lease-camera-initial-recheck.json; an expanded
  sequence rejection remains in lease-capacity-failed-recheck.json. One intervening
  launch failed on SUPERVISOR_HEARTBEAT_FAILED (lease-heartbeat-failed-recheck.json
  and lease-capacity-fixed-runtime.stderr.log), independent of the final pass;
  the underlying native startup finding remains open. Final regression suite:
  acquisition/controller 408 passed, 2 skipped; focused status/cleanup/admission
  30 passed. Scoped Ruff/mypy and backend boundaries pass.

- Behavior-camera PFS follow-up: [initial readback](settings-readback.json) reproduces
  unsupported float Gain GetInc; [initial import](pfs-resolution.json) records the
  absent BslEffectiveExposureTime lookup. [Fixed SDK resolution](pfs-resolution-fixed.json)
  passes the selected PFS import and full readback, with no capture/pulses and camera
  release. Under A10/E07, optional nodes/increments remain absent; required features
  and other SDK errors still fail. Basler's [IFloat interface](https://docs.baslerweb.com/pylonapi/cpp/struct_gen_api_1_1_i_float)
  documents HasInc as the condition for a constant increment.
- [Managed PFS check](managed-pfs-check.json), produced by
  `.venv/Scripts/python.exe managed_pfs_check.py <generation>`, restores the preserved
  operator draft after authenticated ShutdownApplication/restart, then imports its
  selected PFS through the existing controller API and finishes editing. All pass;
  serial 40065509 reports Line4, applied revision 3, device_open=false,
  cleanup_pending=false and lease released. The GUI/runtime is left running.
  Acquisition/controller suite: 406 passed, 2 skipped (`--basetemp .tpfsall06`);
  focused new regressions: 34 passed. Scoped lint/format/mypy and boundaries pass.

- Current acquisition suite: 194 passed with `--basetemp .ta08`. Controller,
  supervisor, platform and launcher portable suite: 356 passed, 2 skipped,
  15 deselected (`--basetemp .t07`); supervisor diagnostic rerun 106 passed.
  Focused GUI: 4 passed, 203 deselected; two actual Windows containment/managed
  Python identity checks pass. Ruff lint/format, Windows-target mypy (188 sources)
  and boundaries (555 modules, zero violations) pass. Scoped whitespace checks
  avoid pre-existing inaccessible tracked test artifacts. The original WinError 5
  OS cause is unproven; retry and unknown-membership shutdown behavior are tested.

- Owning coordinator tests: 19 passed, including stopped/running/missing-state
  regressions. `.venv/Scripts/python.exe -m pytest tests/acquisition tests/controller
  -q -m "not windows and not rig" -p no:cacheprovider --basetemp
  .local-device-connections-elevated-20261006`: [395 passed, 2 skipped, one Windows
  path-length failure](pytest.log). The failing configuration test then passed with
  `--basetemp .t06`: [focused rerun](pytest-short-path.log). The initial sandbox
  broad run was blocked by protected pytest temporary-directory ACLs.
- Scoped Ruff lint/format, Windows-target mypy on health.py and backend boundaries
  pass (555 modules, zero violations). Existing size advisories concern untouched
  cohesive owners; health remains below the advisory threshold. Whitespace checks
  are scoped to touched files because older tracked test artifacts are inaccessible
  inside the sandbox.
- Both devices have FrameStart Off. Behavioral readback: Line4, 1760×3000 BayerRG8,
  25 ms exposure. Tracking: Software, 2448×2048 Mono8, 5 ms exposure. These are
  observed values, not selected operating points or external-trigger acceptance.
- Electrical pin destinations, 5 V compatibility/shared ground, actual frames,
  MCU-to-camera trigger delivery, preview, waveform/receiver evidence and full
  application shutdown remain unverified. Connection-test camera closure passes.
  The owner was asked for wiring/voltage confirmation
  before output tests. Full acceptance remains in the existing
  [rig checklist](../rig-verification.md#managed-device-gui).
# Runtime namespace repair, 2026-10-06

Legacy frame-rate overwrite follow-up: `patch_legacy_camera_start.py` applies the
authorized focused startup fix and owning regressions in the installed editable
Basler dependency (HEAD `70906e60223b42af8b85820ca27ed28a9701da2f`, with existing
adapter/settings-test edits preserved). It is a dated one-time patch, not a runtime
hook. Actual CephVR environment dependency tests: 10 passed; legacy connect/trigger
tests: nine passed. Selected Behavior PFS readback now contains
`AcquisitionFrameRateEnable=0`; the agent did not edit that file. Real triggered
30 Hz acceptance remains untested after the correction; restart imports the fix.

Owner requested restoring CephVR1.0 GUI startup while keeping 2.0 closed.
Source: current uncommitted tree over HEAD
`7b250de613c9d3568932eb648974d9e4964c2c35`; see
[E08](../../docs/architecture/system-contracts.md#e08) and
[current runtime assessment](../runtime.md#current-scope-and-review).
The legacy startup traceback stops in controller.log PermissionError retries
before window.show; direct access returns WinError 5. Runtime namespaces collided.

- `repair_runtime_namespace.ps1` is the executed one-time migration, not an
  automatic startup migration. It preflights private ACLs, rejects reparse points
  and occupied targets, checks absolute source/destination parents, moves only
  canonical generation directories/recovery, and verifies exact ACL/hash retention.
- `runtime-namespace-repair-result.txt` retains the intermediate failed Set-Acl
  attempt after migration; it does not represent the final repair outcome.
- `restore_legacy_runtime_access.py` completes the DACL-only owner inheritance
  repair and verifies all migrated entries remain private and controller.log opens.
  Native execution prints its success; no secret values are emitted.
- Native process/window inspection after normal legacy launch verifies one
  Experiment OS Dashboard with populated controls and a protocol.controller process.
  CephVR2.0 remains absent. No experiment, camera capture or protocol Setup/Start
  was requested. GUI startup is verified; hardware acceptance is separate.
- `pytest tests/shared/test_invariants.py -q --basetemp=.tlegacyfix06`: 10 passed.
  Scoped Ruff lint/format and Windows-target mypy pass; boundaries: 556 modules,
  zero violations, pre-existing cohesion advisories.

# Behavior preview recheck and owner stop, 2026-10-06

Source: uncommitted tree over `7b250de613c9d3568932eb648974d9e4964c2c35`.
Current assessment: [acquisition](../acquisition.md#preview-recheck-stopped-by-owner-2026-10-06).

- `mcu-preview-legacy-response.json` records legacy boot and rejected CAPS on COM8.
  Owner confirmed legacy firmware and requested the new firmware installation.
  `pre-preview-legacy-com8-flash.hex` and `pre-preview-flash-backup.txt` preserve
  the original flash and successful backup method (not EEPROM/fuses).
- `preview-firmware-upload.txt`: Arduino CLI Uno COM8 upload with `--verify`,
  exit 0, using the existing 2026-10-05 image, SHA256
  `83AC07F92814FCFEAE0DF8C3C7E60EF00A4C217F96FDEB0A8182B5276BD0A126`.
  `mcu_preview_recheck.py` / JSON retain post-upload protocol 2 CAPS/STATUS.
- `behavior_direct_trigger.py` / `behavior-direct-trigger.json`: real Behavior
  40065509, FrameStart On/Line4, COM8 D10 requested 30 Hz, Tracking disabled.
  Two-second receiver test obtained 41 SDK frames; ON/OFF applied and owners
  closed. This is receiver proof, not 30 fps or electrical waveform acceptance.
- `behavior-preview-before-stop-evidence-fix.json`: earlier managed Start passed,
  Stop failed for incomplete evidence. Subsequent stdout/stderr retain failures.
  `preview-callback-trace.stdout` shows retained ready/started evidence and frames.
  Final `behavior-preview-check.json` records generation
  `2dd0392f-54f9-4c83-a733-3ea0549872ef` and Start `exact completion missing`.
  Final GUI viewer/managed Stop acceptance is pending. Tracing was removed.
- Owner stopped further work. Authenticated ShutdownApplication command
  `675730af-63c7-4086-aadb-37dd8dff5c9e` was admitted; subsequent native inventory
  found no CephVR2 processes and direct guard acquire/release printed `guard free`.
  EOF notices alone do not establish full graceful closure acceptance.
- `development-cleanup-manifest.json` records 42 directories / 6,640 files /
  201,368,736 bytes removed after workspace/reparse-point preflight. Includes 81
  tracked fixture artifacts. Experiments, configs, production bridge and evidence
  preserved. Small caches/temp directories recreated by later checks remain.
- Focused preview/status/controller tests: 32 passed before final warning-ledger
  regression revision; protected-temp ACL failures preceded the successful run.
  Final expanded validation was not run because the owner stopped the task.

