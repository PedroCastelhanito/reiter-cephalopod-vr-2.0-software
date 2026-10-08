# Windows change review and rig checks — 2026-10-08

Source baseline: `7ba43b1c438734ecc98ed7648831d7aed19c5626`; reviewed changes
`e4c653c..7ba43b1`. Tests after repair use this checkout plus the uncommitted
patch recorded in [final context](context.json). The later camera-selection and
Tracking corrections below have separate source contexts; this full-suite context
retains its earlier tree. Governing rules are
[A10/A11](../../docs/architecture/acquisition.md#a11),
[E08/E15](../../docs/architecture/system-contracts.md#e15) and
[ARCH-002](../../architecture.md#arch-002). These are bounded device/native checks;
remaining acceptance is in the [single rig checklist](../rig-verification.md).
Methods are retained as executable Python scripts beside their raw outputs.

## Results

| Check | Result and scope |
| --- | --- |
| Windows suite before repair | 1456 pass, 12 fail, 4 privilege skips, 1 rig deselection; [raw log](automated/pytest.log). |
| Windows suite after repair | **1463 pass, 8 fail, 5 privilege skips, 1 rig deselection**; [log](final-tree-tests.log), [JUnit](final-tree-tests.xml). The eight failures are existing GUI layout/clipping cases. |
| Static/contracts/build | Baseline syntax, Ruff/format, Win32 mypy (709 sources), boundaries, Tracking 48 tests/19 schemas, Visual Stimulus 42 tests/11 schemas, AMD64 wheel/sdist build pass. Final affected Ruff/format (52 files), mypy (47 sources), boundaries (617 modules/zero violations) and whitespace pass. [Runner summary](automated/summary.json). |
| MCU with acquisition disabled | COM8 protocol 3 / `cephvr2_uno_2`; D9 Test/Status/Stop retains **1** rise, D10 **13**, D11 **25**. Camera tests ran about 0.4 s at requested 30/60 Hz; D9 automatic two-second timeout retains 1/inactive. These are generated transitions, not measured electrical frequency. [Results](managed-mcu.json), [method](managed_mcu.py). |
| Managed firmware | Controller-supervised verified HEX upload and selected checked-in `.ino` compile/upload both succeed. Fresh connections report both camera outputs stopped and volatile configuration invalid. Known HEX digest `0e4d05e6466328f26b33866793d895d65943ea4dfbd35165a2a090f2023bf630`; sketch snapshot digest `977533f2d5e8e3065b726fbda972f34c48036bbcf1df1c899afeaf8b52b621cf`. |
| Compiler rejection/control release | Deliberate compiler error reports failure, leaves the exact COM connection unchanged, and confirms helper/private-storage cleanup. A following active D9 test is stopped by control release; MCU observation and cleanup-pending clear. [Results](managed-failure.json), [method](managed_failure.py). |
| Behavior camera | Both native identity checks pass. GUI Connect dispatch starts capture and Show together; two Behavior cycles sustain visible capture over five seconds, then Disconnect releases camera/window/trigger claim. Actual acquisition-owned image frames start at **(1449,0)** and, after moving GUI, **(1473,24)**, exactly beside its visible right/top edge. [Results](managed-cameras.json), [method](managed_cameras.py), [first image](behavior-preview.png), [moved-GUI image](behavior_moved-preview.png). Image content inspected; dark scene visibility does not prove scientific image quality or sustained 30 Hz. |
| Tracking camera | Two actual Connect/Show/Disconnect cycles pass after exact two-ring readiness/release repair, each with six seconds of capture. BehaviorSquid import/readback, settings restoration and normal shutdown succeed. Earlier rejected Starts and fault exits remain historical evidence. [Current diagnosis/results](#tracking-connect-and-release-correction), [final raw results](tracking-health-complete.json). |
| GPU | Existing real RTX 5060 Ti CUDA/NVOF same-image lease smoke: one pass, 0.43 s. [Log](gpu-smoke.log). No camera/scientific/full-load acceptance. |
| Firmware watchdog/D2 | Isolated after verified application exit: both camera outputs acknowledge ON, then report watchdog-stopped/running false after **3.431453 s** without host commands, with configured 3000 ms watchdog. Matched OFF and serial close succeed. D2 read-only Start/Status/Stop succeeds with **0** observed edges; no projector source is established. [Results](board-watchdog.json), [method](board_watchdog.py). No precise watchdog latency or electrical LOW measurement. |
| SpikeGLX/projectors | Saved `169.254.240.108:4142` inventory read succeeds; diagnostic times out and later logs TCP failure/unretrieved future exception. No remote mutation. [Results](spikeglx-readonly.json), [runtime stderr](failure-runtime.stderr.log). Inventory finds only the 1920×1080 operator display, no active projector outputs; saved projector profile/assignments are unset. Optical Launch/Close remains untested. |
| Final cleanup | Exact normal Shutdown and [application guard/COM/helper/temp checks](tracking-health-native-cleanup.json) confirm final Tracking-test release; [latest cache cleanup](tracking-health-cleanup.json) removes 63 targets/1706 files/23,947,750 bytes. Prior [shutdown](final-exit-receipt.json), [native checks](final-native-cleanup.json) and [cleanup](cleanup.json) retain their original scope. Runtime and capture are stopped. |

## Later camera-selection correction

The owner requested that selecting a camera display that camera's settings.
Managed discovery could restore serial-based assignments without changing the
controller configuration revision, leaving the selected fields stale. Checkbox
clicks also enabled their camera while leaving another row selected. Under G01,
reload the selected fields after assignment restoration and select the row on its
Use-checkbox click; retain silent loading and independent per-camera drafts.

Both selected rows fail before the inventory repair
([log](camera-selection-before.log)); both checkbox directions fail before the
click repair ([log](camera-checkbox-before.log)). Final native Windows Qt/offscreen
camera/PFS selection: **27 pass / 295 deselected, 7.30 s**
([log](camera-selection-after.log), [JUnit](camera-selection-after.xml)). Ruff and
format pass three affected files, Win32 mypy passes two sources, and boundaries
inspect 617 modules with zero violations. The 550-line Cameras panel remains a
cohesive UI surface; the added line wires its existing checkbox/row selection.
Managed projection remains in its focused binding module with no new dependency.

The first sandboxed regression run could not create pytest's default temporary
directory; an explicit workspace test directory resolved it. A broader sandboxed
Qt run stalled without output and was interrupted; permitted native UI execution
passes. This increment uses local fixtures, opens no physical camera and restarts
no runtime. The full-suite and physical results above predate this increment; its
[separate source context](camera-selection-context.json) and
[cleanup](camera-selection-cleanup.json) retain that boundary.

## Repairs and failed attempts

Three focused product repairs preserve existing policy/deadlines and ownership:

- Firmware reconnect incorrectly sent DIAG_STOP when the fresh serial owner had no
  diagnostic. A realistic stub reproduces both upload-success failures before repair
  ([before](firmware-regression-before.log)); remove the invalid call and retain fresh
  CAPS/STATUS outputs-off verification.
- Native child-pipe construction passed nine arguments to the eight-argument bound
  Windows API. Actual managed upload reproduced this before helper launch
  ([first board attempt](managed-mcu-first.json)). Remove the extra buffer-size argument;
  both native pipe directions now transfer bytes and close their exact handles.
- Device close sent DIAG_STOP after diagnostics were already stopped/cleared, leaving
  control-loss cleanup fenced and preventing camera Connect
  ([first camera attempt](managed-cameras-first.json)). Stop only a currently active
  diagnostic, retaining camera OFF evidence, uncertain-close fencing and exact release
  retry. The active/inactive owning regression fails before repair
  ([before](owner-close-before.log)) and passes afterward
  ([107-case integration](owner-close-after.log)). Final review also retains an
  unacknowledged diagnostic Start as uncertain until confirmed Stop/cleanup;
  the extended selection passes [108 cases](uncertain-diagnostic-final.log).
  This guard has regression coverage; no physical missing-ACK injection ran.

The native test initially used the wrong cleanup method/read-only write buffer;
corrected before its 118-case pass. Optional image capture initially failed because
Pillow is absent; cleanup/restore succeeded and capture reran with installed Qt
([probe evidence](camera-capture-probe-error.json)). An early relaunch raced normal
asynchronous shutdown and reached the existing-runtime prompt; it sent no answer and
did not replace that generation. Restart followed its exact absence receipt.
No dependencies, policy defaults, scientific settings or firmware source were changed.

Test-only corrections normalize Qt/Path separators, skip symlink privilege 1314
explicitly, inject a deterministic clock for late-write outcome classification, and
await already-asynchronous coordinator Shutdown settlement within the existing bound.
They do not weaken runtime health limits. Existing GUI clipping,
SpikeGLX reachability/late-future handling, physical timing/LOW/receiver correlation,
mixed-DPI/selector/button interaction, assigned projector/optical and deferred
scientific/encoder/full-workload acceptance remain open.

The existing flash was backed up before managed upload
([readback](mcu-before-managed-upload.hex), [log](mcu-flash-backup.log)); SHA256
`c195c0ae35ee88e7f9d5e3acb50d4c2c2229000b2893f2e8ec6e666166fe60b8`.
This preserves flash only, not EEPROM/fuses or full rollback. Arduino CLI 1.5.1 and
installed Uno AVR tools were used; no tool/core installation ran.

## Tracking Connect and release correction

Owner's later Connect crash (Oct8) follows an accepted PFS import. Exact emergency
and exit evidence confirm a contained runtime shutdown, not PFS rejection. The old
`COORDINATOR_HEALTH_LOST` text incorrectly implied a heartbeat timeout for every
worker report failure. Retaining the existing dispatcher/heartbeat failure reason
exposes `INVALID_EVIDENCE: manual preview Ready differs from its exact preparation`.
Tracking prepares a display producer ring and an ordered Tracking producer ring;
the old readiness validator demanded one. A Ready-only repair opens/captures but
then exposes the same one-ring assumption in release validation. Both are repaired
under A03/A10/E08; health/deadline/fencing policy and scientific settings are unchanged.
The focused evidence helper checks exact allocation/worker/transfer sets and validates
all releases before committing any ledger release. ARCH-002 keeps native ledger
ownership intact, reduces the lifecycle validator and adds no dependency or runtime
back-reference. Worker execution remains the existing cohesive lifecycle assembly;
its size advisory does not justify changing ownership/deadlines in this fix.

Raw failure history remains together with exact exits: the
[owner emergency](../emergency-664981107120200-0c49f213-851d-4d48-b79c-a516824f436c.json)
and [owner exit](owner-tracking-fault-exit-receipt.json);
[instrumented Ready rejection](../emergency-665584458861700-b282e0ad-acc2-4ca7-af65-3e0f0ff9bb81.json)
and [fifth probe](tracking-health-fifth.json);
[Ready-only cleanup rejection](../emergency-665743883795100-1318479d-e74d-461a-99b9-c835ee87fb55.json)
and [partial-repair probe](tracking-health-repaired.json).
The first probe had an incorrect dispatcher principal argument and sent no PFS
command; its separately retained supervisor process-inspection error is not the
Tracking cause. Later heartbeat-only diagnostics did not expose report rejection.
Every controlled restart followed exact prior-generation absence; earlier rejected
restores and fault shutdowns retain their own outcomes. Probe logs/exit receipts are
retained in this directory rather than rewritten as passes.

Final generation `f4128e9d-2218-41e5-b17d-143f91383072` passes actual controller-owned
BehaviorSquid import/readback for serial 40747103 and two GUI-dispatch Connect/Show/
Disconnect cycles, each with six seconds of physical capture, visible preview and
no pending cleanup. Both Stops, original-settings restoration and normal Shutdown
succeed; control release has no failure. This invokes the GUI command path, not
physical button clicks, ordered Tracking diagnostics or scientific recording.
[Method](tracking_health_probe.py), [results](tracking-health-complete.json),
[log](tracking-health-complete.log), [runtime stderr](tracking-health-runtime-7.stderr.log),
[exact exit](tracking-health-complete-exit.json),
[native cleanup proof](tracking-health-native-cleanup.json).

Owning regressions reproduce the Ready bug before repair (two fail/14 pass), then
cover exact Ready and cleanup sets, missing/duplicate/wrong transfer/released proofs,
both camera roles and no partial ledger release after a bad second proof: 48 pass.
Three dispatcher cases check accepted/rejected/transport outcomes, draining/fencing
and specific bounded health evidence. Final acquisition and affected camera/config
controller suite: **363 pass, one platform skip, 2.75 s** with native/loopback permission
([log](tracking-health-tests.log), [JUnit](tracking-health-tests.xml)). An initial
sandboxed async attempt stalled and was interrupted; the permitted run passes
without relaxed assertions. Ruff/format pass eight files, Win32 mypy passes six
sources ([results](tracking-health-static.json)); boundaries inspect 618 modules,
zero violations. The earlier full suite was not repeated on this newer tree.
[Separate source hashes and method context](tracking-health-context.json),
[current cumulative source patch](tracking-health.patch) preserve that scope.

Runtime/capture remain stopped. Final native checks confirm free/released application
guard, exclusive COM8 open/close, no owned runtime/tool processes and no private
firmware directories. No board command is sent by that cleanup probe. Remove only
verified workspace caches and the explicitly created test-temporary directory;
retain all unique raw, emergency/recovery and scientific/native/environment files.
[Separate cleanup manifest](tracking-health-cleanup.json) preserves prior manifests.

## Ino upload native job correction

Later owner upload crash records
[JOB_INSPECTION_FAILED](../emergency-667347656846800-36ea453b-0734-4ce1-89fa-95542448de5f.json),
controller `c54bc934-6250-478a-910e-9c88920a8274`; its
[exact exit](ino-crash-owner-exit.json) confirms all owned processes absent.
The small emergency does not retain native failure detail or establish whether the
owner's chosen sketch reached flashing. The controlled
[reproducer](ino_upload_probe.py) uses the previously verified checked-in protocol-3
`firmware/uno/cephvr2_mcu/cephvr2_mcu.ino`, not an inferred owner-selected external file.
The first harness attempt used an incorrect source path, sent no upload and exited
normally ([result](ino-upload-baseline.json), [exit](ino-upload-baseline-exit.json)).
After exact absence/free guard, the corrected actual GUI command path reproduces
`QueryFullProcessImageNameW ... WinError 5` for a compiler job member, followed by
`TerminateJobObject ... WinError 5` during uploader cleanup
([stderr](ino-upload-reproduce.stderr.log), [result](ino-upload-reproduce.json),
[exact exit](ino-upload-reproduce-exit.json)).

Under E08/A11, the shared Windows API owner now permits a bounded one-millisecond
wait for the exact open process's exit signal after a failed identity query. Only a
signaled handle proves absence; a live/unknown process still fails within the
existing three inspection passes. This covers image teardown before process exit
signaling without treating access denied as absence or changing health policy.
Reopened launch jobs now request JOB_OBJECT_TERMINATE alongside existing rights:
the owner already performs bounded termination, but its handle lacked that right.
The native regression reproduces WinError 5 before repair and passes afterward.
[Microsoft access-right requirement](https://learn.microsoft.com/en-us/windows/win32/procthread/job-object-security-and-access-rights).
ARCH-002 retains focused exact-handle responsibilities, with no new dependency,
ownership layer, policy, source sketch or scientific setting. Tests extend the
existing job behavior module; persistent live-query and failed-termination cases
remain. A new fixture initially expected one rather than two repeated member checks;
corrected before the final pass.

The exit-check-only repair passes three actual compile/verified-upload cycles
([results](ino-upload-exitwait.json), [stderr](ino-upload-exitwait.stderr.log),
[exit](ino-upload-exitwait-exit.json)). Final generation
`4226bad4-92db-4001-879c-1149c49dea8e` passes two more cycles with both repairs, then a
deliberately invalid sketch returns its compiler error with the exact serial
connection retained and no pending cleanup. Normal Shutdown and control release
succeed ([results](ino-upload-final.json), [stderr](ino-upload-final.stderr.log),
[exact exit](ino-upload-final-exit.json)). No configuration edits, pulse diagnostic,
scientific session or remote SpikeGLX action ran. The test exercises GUI dispatch,
not physical chooser/button interaction or arbitrary external sketches.

Final affected command runs platform job, supervisor, controller MCU-owner and
shared supervised-launch tests with native/loopback permission: **199 pass, one
platform/privilege skip, 2.79 s** ([log](ino-upload-tests.log), [JUnit](ino-upload-tests.xml)).
Ruff/format pass two files, Win32 mypy passes one source and boundaries inspect 619
modules with zero violations ([static output](ino-upload-static.json)). The shared
tree also contains another chat's projector-assignment work; this narrow suite does
not supersede earlier full-suite evidence.
[Exact source hashes and command context](ino-upload-context.json),
[two-file source patch](ino-upload.patch) preserve this increment separately.

Initial final-exit inspection finds guard/COM/tool release but one older private
firmware staging directory ([raw check](ino-upload-native-cleanup-initial.json)).
Its unique [staged HEX](ino-upload-fault-staged.hex) is archived before removal of
the exact inactive one-file directory ([manifest](ino-upload-private-cleanup.json)).
The first removal check stops before deletion because short and long Windows temp
paths differ; resolving the pinned basename against the long temp root verifies
the target before removal. Final native check proves no private staging directory,
no runtime/tool processes and released guard/COM ([proof](ino-upload-native-cleanup.json),
[method](ino_upload_native_cleanup.py)). Runtime remains stopped. Workspace cache
and explicitly created pytest-temporary cleanup use a
[separate manifest](ino-upload-cleanup.json); raw evidence, environments, scientific
files and emergency/recovery receipts remain preserved. Interrupted-flash and
full-load acceptance remain in the single rig checklist.
