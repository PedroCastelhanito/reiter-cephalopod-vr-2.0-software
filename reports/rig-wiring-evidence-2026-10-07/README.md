# Windows GUI wiring execution evidence — 2026-10-07

Source: clean initial HEAD `08d146d0d97847cb3f395144886fc175dc627487`.
For the original execution, the only implementation-tool change is the generated SWIG wrapper exclusion in
`pyproject.toml`; Protobuf bindings were regenerated with the owning tool.
`source-sha256.json` captures tested inputs after that correction; post-run
comparison finds no changes, including operator TOMLs and local history/drafts.
`preflight.json` and `environment-freeze.txt` identify Windows, Python 3.11.15,
Basler serials, COM ports, stable displays and GPU UUIDs. Dates use Asia/Tokyo.

This directory retains raw execution evidence. Current findings and pending work
belong in [runtime](../runtime.md#current-scope-and-review),
[acquisition](../acquisition.md#current-windows-wiring-checks),
[Tracking](../tracking.md), [Visual Stimulus](../visual_stimulus.md), and the
[single rig worklist](../rig-verification.md).

Latest placement follow-up: [preview snap context](preview-snap-context.json)
retains the owner's top-right placement report, passive live GUI bounds, six GUI/
one native failures before repair, ten GUI/549 integration passes (two skips),
and four final native/reader passes. Right-space fitting and visible-frame alignment
are repaired; the reopened owner's runtime was preserved, so restart and actual
camera/mixed-DPI inspection remain pending in the acquisition report and rig list.

Later [owner-supplied controller MCU console](owner-mcu-console.md) reports completed
D2/D9/D10 diagnostic Start/Stop pairs with 120 D2 rising edges. Revision, generation
and duration are unknown. Output zero counts were expected under protocol 2; this does
not supersede the separate agent-run ordinary Status/Stop failures below or prove
physical waveform/receiver acceptance.

| Method / retained evidence | Actual result and scope |
| --- | --- |
| [Replacement repair context](replacement-context.json), `replacement-after.xml`, `replacement-integration.xml`, `replacement-native-endpoint.xml` | 37 launcher passes; 219 affected integration passes/one privilege skip; three real private endpoint/event passes with delayed publication and missing initial runtime directory. Owner's exact command displays Y/N; N preserves current runtime. Original owner's missing endpoint path/timing remains unknown; no new live Y/termination/device acceptance claimed. |
| [Preview presentation context](preview-presentation-context.json), `preview-presentation-tests.xml`, `preview-presentation-native.xml`, `preview-presentation-gui.xml` | Policy-15 implementation: 549 acquisition/controller/client passes, two privilege skips; eight selected offscreen GUI passes. Real isolated HighGUI windows verify square geometry/initial physical placement, cached-frame wheel/reset redraw and X closure without producer stop. Owner runtime preserved; full restart, actual GUI/DPI and physical-camera presentation acceptance remain open. |
| `tools/test_on_rig.ps1 -OutputDirectory reports/rig-wiring-evidence-2026-10-07/automated` | Initial run: stale generated bindings cause mypy/pytest collection failure; other runner steps, including AMD64 build, pass. Raw step logs, summary and collection JUnit retained. |
| `.venv/Scripts/python.exe tools/generate_contracts.py` | 19 Protobuf sources generated; no hand-edited bindings. |
| Same runner with `automated-regenerated` output | Static/contracts/schema/build steps run; mypy initially includes generated SWIG wrapper. Native Qt pytest process exits `-1073741819` with access violation in GUI fixture teardown. It does not complete assertions or emit final JUnit. |
| `QT_QPA_PLATFORM=offscreen` then `.venv/Scripts/python.exe -m pytest tests -q -ra -m "not rig" --junitxml reports/rig-wiring-evidence-2026-10-07/windows-offscreen.xml` | 1,252 passed, nine GUI failures, four Windows symlink-privilege skips, one deselection, 138.86 s. Complete traceback/JUnit retained. Eight failures concern layout/clipping; one is normalized Qt versus native path spelling. |
| `.venv/Scripts/python.exe -m mypy --platform win32 src/cephvr` | Pass, 683 sources after generated wrapper exclusion; handwritten native adapters remain checked. |
| Ruff / format / boundaries | Pass, 793 formatted files; initial boundary inventory includes 598 modules because generated SWIG wrapper was present, zero violations. Existing cohesive-owner size advisories remain as reviewed in current backend reports. |
| Pure Tracking / Visual Stimulus contracts and schema drift | 48 Tracking and 42 Visual Stimulus tests pass; 19 Tracking and 11 Visual Stimulus schemas match. |
| `.venv/Scripts/python.exe -m pytest tests/tracking/test_windows_native.py -q -ra --junitxml reports/rig-wiring-evidence-2026-10-07/nvof.xml` | One rig-marked GPU flow/lease test passes, 0.48 s. No camera/full-load/scientific inference. |
| `.venv/Scripts/python.exe scripts/start_runtime_gui.py` | First generation `2358c318-bbdb-4bca-b277-0f3dfa8a4cce` registers seven roles and remains idle for over an hour during desktop approval delay. Automatic GUI control later appears in snapshot. |
| Computer-use selection / capture | Windows list finds the actual managed Dashboard; capture times out waiting for app approval. No screenshot, mouse action, normal GUI close or viewer acceptance claimed. |
| `managed_check.py <generation>` | Read-only SpikeGLX connection times out; normal unheld claim is rejected while GUI owns control. Retained first outcome, no blind retry. Late native connect failure appears in `runtime.stderr.log`. |
| `managed_check.py <generation> managed-device-check` | Explicit takeover and saved endpoint/inventory readback pass. COM8 Connect/CAPS passes; Status/Stop fail required-result evidence. Both camera connection checks and two Behavior Start/Stop cycles pass. Tracking enable/BehaviorSquid import/Finish editing pass; Start fails. Camera-worker heartbeat faults cause shutdown; restoration is rejected while camera ownership remains. Exact fault receipt proves all owned processes absent. |
| `relaunch_check.py` using observed GUI PID 29916 and retained native creation identity | Exact prior GUI absent; `--reopen-gui` yields fresh PID 8632 in unchanged application/controller generation `2d972776-71cf-4dc6-b823-b9b19eb02c3b`. Reconnect modal acknowledgement and normal close remain unverified. |
| Interactive duplicate runtime invocation, N then Y | N prints `Existing runtime left running.` and preserves endpoint. Y prints `Stopping the existing runtime; waiting for confirmed process exit…`; old exact receipt confirms absence before successor `610449a5-553e-4ea5-bf26-ebf7afe0b3fb`. Endpoint/process inventories and receipts retained. |
| `.venv/Scripts/python.exe -m cephvr.client.main --controller-generation 610449a5-553e-4ea5-bf26-ebf7afe0b3fb --json --takeover shutdown` | Completed/succeeded true. Final exact receipt, absent managed processes and free application guard independently verified. |
| `tracking_receiver.py` after confirmed process absence | First probe stops before pulses because managed cleanup left FrameStart Off. Repeat restores the selected PFS's explicit On mode, captures 81 valid frames in two seconds at requested 60 Hz, and receives matched ON/OFF. Camera/serial owners close; pre-probe Off mode is restored afterward. This does not prove sustained cadence or waveform timing. |

No full session, scientific recording, projector presentation, pulse-map write,
firmware upload or remote SpikeGLX mutation ran. Untimed calibration requires an
accepted exported profile/arena, asset root and output assignments; none was supplied.
Managed Tracking diagnostics/annotation remain blocked by capture/heartbeat faults.
Electrical/optical instruments, scientific settings, privileged symlink execution,
encoder compatibility and full-workload acceptance remain pending under existing
deferrals. Built packages are reproducible outputs; build logs and hashes are retained
before removing duplicate package artifacts during cleanup.

Follow-up: [MCU output feedback correction](mcu-output-feedback.md) records six
focused GUI passes and the owner's SpikeGLX observation method. Physical results
are pending. The frozen-source manifest above belongs to the original run; this
GUI correction and concurrent preview repairs change the later working tree.

Latest MCU follow-up: [generated-transition counting](mcu-counted-diagnostics.md)
records the owner-selected protocol 3 implementation, firmware image and local
validation. Matching manual installation and actual board count tests are pending;
earlier protocol 2 output-zero results remain historical evidence.

Subsequent [owner camera test failure and configuration repair](mcu-camera-diagnostic-repair.md)
retain the exact no-D10-pulses observation, missing CONFIGURE reproduction,
underlying-error preservation and controller protocol-version correction. Seven
targeted and 526 acquisition/controller/client cases pass (two privilege skips).
Live readback failed authentication; runtime restart, upload and board retest have
not run. Earlier successful adapter runs did not cover these defects.

Camera follow-up retains the [owner console](owner-preview-console.txt) and
[read-only live snapshot](user-preview-snapshot.json), controller
`205bc097-d44b-4d88-9325-19ad87630566`. The snapshot contains a camera timeout but
does not identify its command kind; the supplied console has no timestamp/generation.
No control claim, camera command, settings edit or runtime restart was performed
for this follow-up. Source repair assessment lives in the
[current acquisition report](../acquisition.md#current-windows-wiring-checks).
Before-repair JUnit: `preview-before.xml` (four failures) and
`preview-rejection-before.xml` (two failures). Focused after-repair files retain
five and two passes. Final `preview-owner-final.xml` / `.log`: 495 passed, two
symlink-privilege skips; `preview-gui-final.xml` / `.log`: 13 passes, including the
native Windows reader. Offscreen Qt and isolated test state do not establish
actual camera viewing. Current patch/input hashes are recorded separately in
`preview-repair-sha256.json`; the earlier 958-file manifest remains historical.
`preview-repair-context.json` records methods/limits. Follow-up
`preview-repair-cleanup.json` retains verified workspace cache/bytecode removal:
64 directories, 766 files, 32,527,493 bytes. The active owner runtime, installed
dependencies, external temporary files, settings and unique evidence were preserved.

## Backend-owned OpenCV camera display

Later [authorized installation and actual camera retest](mcu-installation-and-preview.md)
verifies protocol-3 upload/CAPS, D9/D10/D11 generated counts and Behavior native
window ownership/Hide/close/reopen/Stop. Tracking revision adoption is repaired
(535 integration passes/two skips), but its health shutdown recurs after preparation.
The original prepared/uninstalled statements above retain their earlier scope;
current installation status is complete, while Tracking/physical acceptance remains open.

The owner reports repaired Preview works and requests backend-owned OpenCV windows
as in CephVR1.0. A10 revision 53/G01 revision 121 and policy 14 govern the change;
concurrent MCU protocol 3 is retained. `opencv-context.json` records current inputs,
methods, package/build evidence and limits. `opencv-owner-final.xml` / `.log` pass
526 cases with two privilege skips; `opencv-gui-final.xml` / `.log` pass 17 selected
GUI/bridge cases. `opencv-first-image-tests.xml` / `.log` pass 64 final focused cases
after first-image and synchronous close-observation refinements. The native test
uses two real Win32 HighGUI windows and isolated capacity-one rings, verifies latest
pixels, native X and unaffected producers; no physical camera or serial device is used.
The earlier initial/owner/native JUnit captures intermediate fixture/expectation
failures with their historical scope. `opencv-build.log` and
`opencv-boundaries.log` retain packaging and 602-module/zero-violation checks.
The GUI headless package was replaced with pinned OpenCV 4.13.0.92 WIN32UI.
`opencv-cleanup.json` retains disposable workspace cleanup; installed environments,
active runtime DLLs, operator data, compiled native bindings and unique evidence
remain. Full runtime restart is coordinated with the pending matching MCU firmware
installation; physical-camera OpenCV viewing/heartbeat/Tracking remain open.

Shared OpenCV dependency compatibility: `opencv-tracking-tests.xml` / `.log` pass
72 existing Tracking cases, with one rig-marked workload deselected (2.30 s). No
Tracking algorithm or scientific/native GPU acceptance changes.
