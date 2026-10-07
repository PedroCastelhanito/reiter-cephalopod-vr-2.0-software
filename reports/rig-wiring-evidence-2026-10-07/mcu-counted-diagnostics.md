# MCU-generated transition counts — prepared installation

Date: 2026-10-07 (Asia/Tokyo). Base revision `08d146d` plus uncommitted counted
diagnostic and concurrent camera-preview work. The owner explicitly selected
counting generated transitions on the MCU. [A11 revision 37](../../docs/architecture/acquisition.md#a11)
and acquisition policy 13 govern protocol 3 / `cephvr2_uno_2`.
Concurrent owner-requested camera-viewer work later advances the shared policy/config
binding to 14, retaining protocol 3 and the diagnostic counter rule. The 45 owning
MCU/configuration cases [pass again](mcu-counted-current-policy.xml), 1.35 s;
[console](mcu-counted-current-policy-tests.log). The original nine-input manifest
retains policy 13 provenance: its three policy/config binding files subsequently
change; counter firmware/parser/panel and owning tests remain unchanged at recheck.

Subsequent owner testing reports no camera pulses. The
[camera diagnostic repair](mcu-camera-diagnostic-repair.md) configures the selected
output before DIAG_START and preserves the rejection reason. It also corrects
controller Connect's hardcoded protocol-2 completion check, missed by the suite
below. Seven targeted and 526 affected-owner cases now pass (two privilege skips).
The compiled image remains unchanged and uninstalled; this corrects the earlier
host-readiness assessment without claiming board acceptance.

The firmware's existing diagnostic counter increments after actual HIGH writes,
including the first HIGH. Camera Timer1 transitions increment only for the active
diagnostic pin; ordinary preview/session outputs do not count. Trial state's held
HIGH counts one. Input diagnostics retain interrupt-observed rising edges. Atomic
counter reset/readback and uint32 saturation preserve a final count after explicit
Stop/timeout until the next test. The initial HIGH write/count precedes publishing
the output as running to the timer ISR. No rate-times-duration estimate is used.

Host parsing accepts generated camera counts, requires Trial state's one rise,
rejects invalid/zero output counts and rejects protocol 2 at connection before any
diagnostic. Existing controller `rising_edges` projection and managed/local GUI
paths carry the count without a new process, RPC or authoritative state copy.
GUI labels output counts as generated transitions and input counts as observed
edges. This verifies generation logic, not electrical reception.

Validation retained here:

| Method | Result |
| --- | --- |
| Owning MCU protocol/owner plus configuration tests | [45 passed](mcu-counted-protocol.xml), 1.07 s; [console](mcu-counted-protocol-tests.log). Includes nonzero/invalid/saturated camera counts, Trial state semantics and old-version rejection/port closure. |
| Acquisition/controller/client suite, native Windows and authenticated loopback access | [508 passed, two symlink-privilege skips](mcu-counted-integration.xml), 8.05 s; [console](mcu-counted-integration-tests.log). |
| Six existing GUI diagnostic/control cases, offscreen | [6 passed, 285 deselected](mcu-counted-gui.xml), 3.82 s; [console](mcu-counted-gui-tests.log). Adds generated-count assertions in the owning scenario. |
| Ruff / format over acquisition/GUI source and owning tests | Pass; 331 files already formatted. |
| Windows-target mypy over acquisition/GUI source | Pass, 305 sources. |
| Backend boundaries / whitespace | 598 modules, zero violations; `git diff --check` passes. Existing owner size advisories remain; counting reuses the focused parser/panel and existing counter without dependencies or extra states. |
| Arduino CLI compile, FQBN `arduino:avr:uno` | Pass; 11,078 flash bytes / 1,112 SRAM bytes. [Build log](mcu-counted-firmware-build.log). |

The initial restricted runs stalled in existing asyncio-based owner tests and were
interrupted. The native-permitted repeat completed without exclusions or weakened
assertions. No board or runtime command was part of those test-adapter runs. No
on-board Timer1/physical count result is claimed before installation.

Prepared non-bootloader upload image:
[cephvr2_mcu.ino.hex](mcu-counted-firmware/cephvr2_mcu.ino.hex), 31,178 file bytes,
SHA-256 `0e4d05e6466328f26b33866793d895d65943ea4dfbd35165a2a090f2023bf630`.
[Build metadata](mcu-counted-firmware.json) and
[nine source/input hashes](mcu-counted-source-sha256.json) are retained. These hashes
identify the captured inputs for this follow-up, not a new full-repository freeze.

Installation has not run. The owner has an active managed runtime with COM8/device
ownership; releasing it and uploading resets the board and interrupts current checks.
The new host requires matching protocol 3 firmware on its next restart. Manual
installation under A11 remains the installation mechanism; no automatic flashing
feature is added. Before the manual upload, preserve current flash, confirm process
absence/serial release, upload this exact image with verification, then check CAPS
and bounded D9/camera/D2 diagnostics. Board counts and electrical/SpikeGLX correlation
stay open in the [single rig checklist](../rig-verification.md#managed-device-gui).

Cleanup removes the verified untracked build directory and workspace caches/bytecode:
65 targets, 830 files, 32,352,178 bytes. [Inventory](mcu-counted-cleanup.json) retains
per-target counts; image, ELF/build outputs, logs and all unique evidence are preserved.
No installed dependency, tracked source, operator data or active runtime is removed.
