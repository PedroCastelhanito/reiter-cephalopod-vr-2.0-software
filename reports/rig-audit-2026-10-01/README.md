# Windows rig audit evidence — 2026-10-01

Source: clean HEAD `826984255e0a8469afccbda2dcaf8c642b528b33` before audit.
The initial audit changed only documentation/evidence and generated environment/build artifacts.
The installed native DLL remains untracked; no commit or ignore rule was added.
The initial audit changed no handwritten implementation, configuration, firmware or scientific setting.
Subsequent owner-authorized repairs are recorded separately in LOG and repair-prefixed
evidence files here; the original audit outcomes below retain their original scope.
Governing scope: [E15](../../docs/architecture/system-contracts.md#e15),
[SYS-002/003](../../architecture.md#sys-002), [ARCH-002](../../architecture.md#arch-002).
Current findings belong in owning backend reports; remaining acceptance belongs in
[the rig worklist](../rig-verification.md).

## One-time symlink follow-up

The owner requested deletion of exactly two POSIX-mode tests; native unsafe-DACL coverage remains. Final actual elevated execution passed **759 tests, zero failures or skips**, including all Windows/rig markers and all four symlink cases. [Full stdout](python-runtime-elevated-final-full.log), [JUnit](python-runtime-elevated-final-full.xml), [backend counts](symlink-final-counts.json) and [commands/token/cleanup completion](python-runtime-elevated-final-completion.json) are the latest snapshot. Controller 202, supervisor 106, shared 52, platform 46, acquisition 171, Tracking 43, Visual Stimulus 123, launcher 10 and client 6 passed. This final elevated run used dedicated workspace basetemp; the prior default-temp standard-token suite passed 755 with four symlink privilege skips ([stdout](symlink-standard-full.log), [JUnit](symlink-standard-full.xml)). No persistent OS setting, Developer Mode or privilege policy changed.

One-time elevation exposed a genuine prepared-interpreter startup dependency gap: the owned child exited 0xC0000135 before Python code ran. The first elevated full attempt ([stdout](symlink-elevated-full.log), [JUnit](symlink-elevated-full.xml)) had 758 passes/one failure; [isolated diagnostic](symlink-elevated-retry-managed-python.log) captured the exact exit. [PE imports](symlink-python-startup-imports.log) and [base file hashes](symlink-python-startup-locations.json) identify matching-base VCRUNTIME140.dll and zlib.dll. Preparation now copies only these finite startup dependencies with exact source/copy provenance; zlib remains optional for base distributions that omit it. Missing/stale/mismatched artifacts fail explicitly. The same five-second native proof retains exact PID/image, job membership, venv imports and inherited bootstrap assertions; owned standard handles now preserve startup diagnostics. Final provenance/native proof passed [two cases](python-runtime-elevated-final-focused.log).

The initial RunAs request was cancelled; approved retries used actual High-integrity administrator tokens, retained in [final token evidence](python-runtime-elevated-final-token.log). A Medium-token outside-sandbox attempt hit pytest-current access denial after elevated default-temp runs. Final elevated cleanup removed only traced pytest-17/18, their validated current link and dedicated scratch. Normal Medium-token default-temp provenance/native proof then [passed two cases](symlink-medium-default-temp.log), confirming restored access. Scoped lint/format/type and boundary checks pass. [Package build](symlink-package.log) and [inspection](symlink-package-inspection.json) confirm current runtime source, both native DLLs and the Windows x64 wheel tag; its disposable outputs were removed. [Updated runtime manifest](symlink-final-runtime-manifest.json) retains startup provenance. Prior repair-source artifacts below remain historical; the final follow-up source is captured separately in symlink-source artifacts.
## Repair snapshot before symlink follow-up

Audit items 1–4 and 6 are repaired. Encoder item 5 is explicitly owner-deferred;
its code/settings/toolchain were unchanged. Final source is the baseline above plus
uncommitted repairs. The default-temp full command included every Windows and rig
marker: **755 passed, 6 skipped, 761 collected**. No failed bodies remain.
[Final stdout](repair-final2-pytest.log), [JUnit](repair-final2-pytest.xml) and
[parsed backend/skip matrix](repair-final-counts.json) record that earlier snapshot.

| Backend | Passed | Skipped |
| --- | ---: | ---: |
| Acquisition | 171 | 0 |
| Controller | 200 | 2 |
| Supervisor | 106 | 0 |
| Tracking | 43 | 0 |
| Visual Stimulus | 123 | 0 |
| Windows platform | 45 | 1 |
| Shared | 51 | 3 |
| Launcher | 10 | 0 |
| Client | 6 | 0 |
| **Total** | **755** | **6** |

Four skips in that earlier snapshot require unavailable symlink privilege (controller root, controller
lock, native reparse lock and shared recovery pointer). Two retain POSIX mode tests
(operator credential and world-readable recovery rejection). Native owned-file
Everyone-read DACL rejection passes. Portable duplicate-field rejection now runs on
Windows; the original audit's six skips included that POSIX-only fixture, while
the final six instead include the isolated root-symlink parameter. No OS privileges
or Developer Mode were changed, and that earlier snapshot did not execute symlink coverage.

The native atomic helper passes cross-process visibility and ring regressions.
Managed Python proof verifies exact executing PID/image, one live job member, fresh
venv imports and inherited bootstrap. Guarded cancellation, alias exclusion,
process-death release and recovery persistence pass with default Windows paths.
Terminal timestamps use the existing operation owner. Media types narrow actual
PyAV/TIFF interfaces; generated unsigned TIFF pixels match exactly and float input
is rejected. This is bounded implementation evidence, not full experiment acceptance.

Final [Ruff](repair-final3-ruff.log), [format (627 files)](repair-final3-format.log),
[mypy (525 files)](repair-final2-mypy.log), [boundaries](repair-final-boundaries.log),
[syntax](repair-final-syntax.log) and [dependencies](repair-final-pip-check.log) pass.
Tracking [48 tests](repair-final-tracking-contracts.log)/[19 schemas](repair-final-tracking-schema.log)
and Visual Stimulus [40 tests](repair-final-vs-contracts.log)/[11 schemas](repair-final-vs-schema.log) pass.
The [final build](repair-final2-package-build.log) and
[content/tag/hash inspection](repair-final2-package-inspection.json) verify both DLLs,
managed runtime modules, native source in the sdist, and a non-pure
`cp311-cp311-win_amd64` wheel. [Runtime hashes](repair-native-runtime-hashes.txt) and
[prepared manifest](repair-python-runtime-manifest.json) retain artifact provenance.
No Linux runtime was available; portable paths were source-reviewed and exercised
on Windows, without claiming Linux execution.

```powershell
.venv/Scripts/python.exe -m pytest tests -q -rs --junitxml reports/rig-audit-2026-10-01/repair-final2-pytest.xml
.venv/Scripts/python.exe -m ruff check src tests tools setup.py
.venv/Scripts/python.exe -m ruff format --check src tests tools setup.py
.venv/Scripts/python.exe -m mypy --platform win32 src/cephvr
.venv/Scripts/python.exe tools/check_backend_boundaries.py
.venv/Scripts/python.exe -m unittest discover -s contracts/tracking -p 'test_*.py'
.venv/Scripts/python.exe contracts/tracking/schema_check.py
.venv/Scripts/python.exe -m unittest discover -s contracts/visual_stimulus/tests -p 'test_*.py'
.venv/Scripts/python.exe contracts/visual_stimulus/generate_schemas.py --check
.venv/Scripts/python.exe -m build --no-isolation --outdir .repair-package-final
```

Other rigs require Python 3.11 AMD64, declared extras, MSVC x64/CMake, CUDA and
actual NVIDIA Optical Flow API 2 headers. Reproduction entry:
`./tools/test_on_rig.ps1 -Install -Rig -BuildTrackingNative -NvofSdkRoot <API2-header-root>`.
Install builds atomics and prepares the exact interpreter; Tracking remains an
explicit build. Atomic rebuild commands are `cmake -S native/windows -B <owned-build-dir> -A x64`,
`cmake --build <owned-build-dir> --config Release`, and
`cmake --install <owned-build-dir> --config Release --prefix src`.
These are reproducible commands; original atomic compiler stdout/build-directory
provenance was not saved in this bundle. The installed helper and passing native
tests are independently evidenced. See the tool guide for CMake discovery.

Failed attempts remain historical: [first final suite](repair-final-pytest.log)
had one fixed-sleep heartbeat failure; later formatting-only changes passed the
final check without changing behavior. Initial fixture/source failures and sandbox
ACL restrictions were corrected or rerun with authorized escalation. No silent
skip or test weakening was used. Current acceptance limits remain in the rig worklist.

Cleanup: [recorded removals](repair-cleanup.log) cover inspected `.repair-tmp`
(including disposable package builds), `.tmp-luna-c`, empty `.codex-pytest-tmp`, and
the [23 small D storage fixture files](repair-storage-temp-inventory.json) under
`.tmp-luna-d`. Initial recursive cleanup was automatically rejected because the
`.codex` scratch contents/provenance had not been verified; read-only inspection
established it was empty and the narrower cleanup passed. Fresh `.venv`, prepared
interpreter/manifest and both untracked native DLLs remain reusable. Preexisting
ignored caches/dist and default pytest directories 12/13/14 were retained because
exact run mapping was not established; no blanket deletion was performed.

Baseline-relative [tracked patch](repair-source.patch),
[new source/native files](repair-new-files.zip) and
[file/hash manifest](repair-source-manifest.json) preserve the dirty source snapshot.
Optional-library missing-import scopes preserve the minimal-dev static baseline
without suppressing installed types; absent-extra runtime was not executed.
The last changes were test formatting and that static configuration only; installed
mypy and package metadata were rechecked after them without another behavior run.

## Environment and methods

Created fresh repository `.venv` from existing Python 3.11.15 at
`C:\Users\ReiterU_PC\miniforge3\envs\CephVR\python.exe`, without copying legacy packages.
Installed editable `.[dev,acquisition,visual_stimulus,tracking]` successfully; see
[install](install.log), [ensurepip](ensurepip.log), [freeze](environment-freeze.txt)
and [dependency consistency](pip-check.log). Sandbox denied ensurepip temporary writes
both in user temp and repository temp; authorized escalation succeeded. Raw first
failed stdout was not saved to a file; the tool transcript retains it.

Ran `tools/test_on_rig.ps1 -OutputDirectory reports/rig-audit-2026-10-01/automated`
with authorized Windows/native/filesystem/loopback permission. It completed every
step; [summary](automated/summary.json) and per-step logs retain outcomes.
Combined runner stdout was delivered through tools but not saved successfully.
Then built the existing native adapter with installed VS2022 CMake/MSVC 19.44,
CUDA Toolkit 12.8.61 and existing NVOF API 2.0 headers; [configure](native-configure.log),
[build](native-build.log), [install](native-install.log). MSBuild warned that the
intermediate directory was under TEMP; the build succeeded. The installed DLL and
fresh environment remain for reuse. Only the verified audit-created `.audit-tmp`
directory was removed, including its native build, test temp, pip cache and encoded
scratch file. Preexisting ignored caches/build files were not indiscriminately removed.
Audit-generated wheel/sdist copies under `automated/packages` were also removed after
[retaining hashes](package-sha256.txt); the package-build log remains. Runner summary
steps with no stdout have a factual placeholder log stating the recorded exit status.

Native reproduction commands (installed VS2022 CMake executable):
`cmake -S native/tracking -B .audit-tmp/tracking-native -A x64
-DNVOF_SDK_ROOT=C:/Dev/software/OpenCV_NVIDIAOF/opencv-build/3rdparty/NVIDIAOpticalFlowSDK_2_0_Headers/NVIDIAOpticalFlowSDK-edb50da3cf849840d680249aa6dbef248ebce2ca`,
`cmake --build .audit-tmp/tracking-native --config Release`,
`cmake --install .audit-tmp/tracking-native --config Release --prefix src`.
Installed artifact: `src/cephvr/tracking/native/cephvr_nvof.dll`;
[SHA256 and absolute path](native-dll-sha256.txt). Other machines must locate their
installed API2 headers/toolchain explicitly; these paths are inventory, not defaults.

Full suite command: `.venv/Scripts/python.exe -m pytest tests -q -rs --junitxml
reports/rig-audit-2026-10-01/full-pytest.xml --basetemp .audit-tmp/full-pytest`.
Results: [stdout](full-pytest.log), [JUnit](full-pytest.xml).
Focused command: `pytest tests/platform/test_windows_native_on_rig.py
tests/tracking/test_windows_native.py -q -rs --basetemp .audit-tmp/native-focused`;
[8 passed, 1 skipped](native-focused.log), including the NVIDIA rig smoke.

## Initial audit outcomes

| Owner | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Acquisition | 166 | 5 | 0 |
| Controller | 189 | 10 | 1 |
| Supervisor | 104 | 2 | 0 |
| Tracking | 42 | 1 | 0 |
| Visual Stimulus | 122 | 0 | 0 |
| Shared | 50 | 0 | 4 |
| Platform | 38 | 0 | 1 |
| Launcher | 10 | 0 | 0 |
| Client | 6 | 0 | 0 |
| **Total** | **727** | **18** | **6** |

751 cases collected; 745 test bodies ran and 6 skipped. Initial runner excluded the sole rig case and had
723 passed, 21 failed, 6 skipped, 1 deselected. Four initial CreateFileW error-3
failures disappeared with shorter basetemp; supervisor recovery failed in the full
rerun but passed in isolation. Keep both snapshots: the run is not globally passing.
Six skips: two controller/platform symlink privileges, one shared symlink privilege,
and three POSIX-only mode/permission fixtures. No assertion was weakened.

Syntax, Ruff, format (623 files), boundaries (453 modules, zero violations, 16
cohesion notices), Tracking contracts (48), Visual Stimulus contracts (40), Visual
Stimulus schema check and sdist/wheel build passed. Windows-target mypy failed with
52 errors in three Visual Stimulus media modules when actual optional packages were
installed. Tracking schema check failed, but [the explicit UTF-8 probe](audit-probes.log)
shows ellipse schema exactly matches its canonical model: default Windows decoding,
not stale declarations, causes the mismatch. Packaging-build success does not certify
native DLL inclusion or wheel deployment.

## Initial findings and bounded probes

- Acquisition ring tests fail because kernel32 does not export the requested
  `InterlockedCompareExchange64` symbol. This is a runtime native binding blocker;
  retain cross-process atomic/fence semantics in the repair, not Python/GIL access.
- Windows reservation cancellation fails renaming a session directory while its
  lock is held (WinError 5). Two startup recovery tests fail at persistence; exact
  writer cause remains unconfirmed. One storage replacement fixture attempts an
  open-file rename and gets WinError 32. Preserve ownership and truthful uncertainty.
- [Interpreter process tree](automated/interpreter-process-tree.log) and the isolated
  [probe source](audit_probes.py)/[result](audit-probes.log) show venv redirector and
  executing base-interpreter child in the owned job. Actual code PID reports venv
  `sys.executable`, but OS image is the base interpreter; configured-image
  `retain_exact` rejects that code process. No full managed app was started.
- The same probe uses public Setup method with authorization and backend preparation
  stubbed, then the real Ready transition. It confirms completed Setup has no finish
  timestamp and survives post-finalization retention pruning. Start success and Setup
  failure have analogous source-confirmed writes; they were not behaviorally probed.
  Capacity bypass was not established: `authorized()` checks capacity under the lock.
  Early probe attempts failed at missing test import and inconsistent fixture backend
  identity; subsequent corrected probe succeeded. Their stdout was overwritten in
  the evidence file and remains only in the tool transcript; no test/backend failed
  in those setup attempts.
- Five recording-root cases fail constructing an unnecessary symlink before selecting
  the parameter case; one recording path case assumes POSIX absolute paths. These are
  fixture portability problems. Supervisor heartbeat and Tracking Finished-delivery
  assertions fail again in [focused rerun](failure-focused.log); the latter observes
  local finished state before outbound delivery. Runtime guarantees versus fixture
  timing require focused repair/coverage, not looser deadlines. Supervisor recovery
  failure is not consistently reproduced (focused rerun passed).
- Read-only Basler [enumeration](camera-enumeration.log) sees serials 40065509 and
  40747103 with expected models. No camera was opened/captured/reconfigured.
  Fresh [GPU inventory](nvidia-gpus.csv) confirms RTX5060 Ti ordinal0 and RTX2080 Ti
  ordinal1, UUIDs matching owner assignments, driver617.14. Native smoke uses random
  128x128 same-image input, checks lease/readback/closure, not accuracy or throughput.
- PATH [FFmpeg](ffmpeg-version.txt)/[ffprobe](ffprobe-version.txt) are both 4.3.2
  from 2021. Three generated128x128 H.264 frames on explicit GPU1 failed at NVENC
  preset configuration with unsupported param12; [exact result](encoder-smoke.log).
  This pair is not a validated production toolchain. No production codec/settings
  were changed and no output-content/runtime acceptance was inferred.

## Initial recommendations and continuing limits

Repair ring atomic binding, interpreter exact identity and reservation/recovery
Windows behavior first, then route terminal transitions through the existing
`complete_operation` owner. Repair fixture portability/delivery synchronization,
explicit schema encoding and actual-package media typing; use a deliberate compatible
FFmpeg pair. Existing behavior-specific test files are justified; no redundant test
module was found to delete. Avoid another broad size-only refactor.

GUI and SpikeGLX integration are not implemented under the build order, not failing
backends. Full managed startup is source-gated on missing `cephvr.gui.main` before
native launch. Automatic approval review rejected invoking `run_launcher` because
it could start managed services/hardware if that gate were passed; the invocation
was not executed. Read-only source inspection supports the gate claim.

Full camera/encoder/rendering/tracking workload, projection/optical/calibration,
electrical pulse evidence, MCU firmware and SpikeGLX acceptance remain open. Missing
final ROI/depth, output surface/calibration, actual pulse inventory/wiring and remote
SpikeGLX setup prevent truthful execution; no guessed scientific defaults were used.
Fresh machine inventory is [OS](os.json), [CPU](cpu.json) and [tool paths](tool-paths.txt).

## Earlier repair increments

The owner subsequently authorized audit items 1–4 and 6; encoder item 5 remains
deferred to the owner. Initial audit counts above remain the original snapshot.
Repairs use the same baseline plus the working-tree changes; nothing is committed.

Setup terminal transitions and successful Start now use the existing operation
completion owner. The focused controller regression run passed 21 cases; the
Windows-target controller type check passed 74 files. These are implementation
checks, not a full managed experiment.

The native atomic repair uses a small documented MSVC intrinsic export behind the
existing Python interface. The owning cross-process/native and acquisition ring
checks passed **14**, with **1** Windows symlink privilege skip:

```powershell
.venv/Scripts/python.exe -m pytest tests/acquisition/test_worker_ring_regressions.py tests/platform/test_windows_native_on_rig.py -q -rs --basetemp .repair-tmp/native-b
.venv/Scripts/python.exe -m build --no-isolation --outdir .repair-tmp/packages-b
.venv/Scripts/python.exe -m ruff check setup.py src/cephvr/platform/windows/atomics.py tests/platform/test_windows_native_on_rig.py
.venv/Scripts/python.exe -m ruff format --check setup.py src/cephvr/platform/windows/atomics.py tests/platform/test_windows_native_on_rig.py
```

[Native/ring results](repair-b-native-ring.log),
[package build](repair-b-package-build.log), and
[package inspection with hashes](repair-b-package-inspection.log) retain outcomes.
The wheel contains both native DLLs, is non-pure and tagged
`cp311-cp311-win_amd64`; the sdist includes the Windows atomic C++/CMake source and
packaging helper. The [runner parser check](repair-b-powershell-parser.log) passed.
An initial retirement diagnostic expectation failed despite correct retired/sealed
state; the owning test now asserts the actual public stale/retired diagnostic.
An initial package inspection was sandbox-denied and then passed with authorized
escalation. The final complete-suite snapshot above supersedes these intermediate counts.
