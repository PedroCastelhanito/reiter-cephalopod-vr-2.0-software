# Manual protocol-3 installation and native camera retest — 2026-10-07

Source: HEAD `08d146d0d97847cb3f395144886fc175dc627487` plus the current
uncommitted MCU/OpenCV work and worker adoption repair. Dates use Asia/Tokyo.
The [owner console](owner-mcu-version-console.txt) reports a successful Behavior
identity check followed by host rejection of MCU protocol 2; its generation and
timing are unknown. The owner explicitly authorized shutdown, current-flash backup,
manual upload, restart and retest in this chat. Governing rules are
[A11](../../docs/architecture/acquisition.md#a11),
[A10](../../docs/architecture/acquisition.md#a10) and
[E07](../../docs/architecture/experiment.md#e07).

## Installation and board evidence

- Authenticated normal shutdown of controller `028d0e0b-7e6e-47e8-8814-07818b27489d`
  succeeds; `mcu-update-exit-receipt.json` confirms exact all-owned-process absence.
  Arduino CLI enumeration identifies Uno `1344A474130351F057D6` on COM8,
  FQBN `arduino:avr:uno`.
- AVRDUDE 6.3.0-arduino17 reads the ATmega328P flash before replacement.
  `mcu-before-protocol3-flash.hex` SHA-256:
  `dcc0f4d1c7f50c45115bf45c591d6df8d4bc6d77f52ba9e0785736678716e19a`.
  This preserves flash contents, not EEPROM/fuses or a source sketch.
  The raw command output is `mcu-update-backup.log`.
- `arduino-cli upload -p COM8 --fqbn arduino:avr:uno --input-file
  reports/rig-wiring-evidence-2026-10-07/mcu-counted-firmware/cephvr2_mcu.ino.hex
  --verify` exits zero. The image was rehashed immediately before upload:
  `0e4d05e6466328f26b33866793d895d65943ea4dfbd35165a2a090f2023bf630`.
  `mcu-update-upload.log` retains CLI output. Original build metadata's
  `uploaded=false` describes its preparation time, not this later installation.
- `mcu_protocol3_board_check.py` / `mcu-update-board.json` / `.log` run the actual
  SerialOwner, with original serial deadlines. CAPS reports protocol 3,
  `cephvr2_uno_2`, stopped/unconfigured startup outputs. Two bounded D9 tests count
  one rise each. D10 resets to one and increases to 18 in each cycle; D11 resets to
  one and increases to 35/36. Stop retains final counts. Matched OFF confirms both
  camera outputs stopped; serial ownership closes. These are firmware-generated
  transition observations, not electrical levels, receiver counts or rate accuracy.

## Managed camera evidence and remaining failure

`mcu_preview_retest.py` uses authenticated controller commands and exact active
manual run IDs, with no recording/session or scientific-settings change. Named
JSON files retain snapshots and command outcomes; logs retain the method output.

- Controller `27c3499c-55b2-4784-a116-ec8b531f1939`:
  `mcu-update-managed.json` / `.log` retain successful MCU Connect and both Basler
  identity checks. Behavior 40065509 Start, Show, Hide, Show, native WM_CLOSE,
  Show and Stop all complete successfully. Native title/handle/PID observation
  identifies acquisition coordinator PID 9320 as window owner, separate from Qt GUI.
  Show's first-image barrier confirms a converted acquired image reached the window.
  Hide/native close snapshots retain the same running capture/run ID; Stop leaves
  capture stopped, cleanup false and native window absent. WM_CLOSE is posted to
  the observed HighGUI handle; this is native message testing, not a physical mouse
  click or visual assessment of scene quality. Idle MCU Status/Stop reject with
  `no pin diagnostic is active`, rather than incomplete result evidence.
- Tracking Start resolves its saved BehaviorSquid readback but initially fails
  `preview preparation configuration revision is stale`. The controller's changed
  readback advances the revision, while the worker retained the requested revision.
  Worker camera configuration now validates unchanged/next adopted revision and
  exact retained device/transport/layout/timestamp/counter/clock facts before
  preview preparation. The existing comparator is shared with session Setup;
  Setup retains its stricter next-revision requirement. No deadline or identity
  check is relaxed. ARCH-002 reuses focused ownership and existing behavior tests.
- Focused adapter/admission/preview checks pass 54 (0.67 s). Acquisition/controller/
  client integration passes 535, two symlink-privilege skips (8.68 s). Ruff/format
  pass three changed files; Windows mypy passes 185 acquisition sources; boundaries
  check 602 modules, zero violations. Raw JUnit/logs are `mcu-preview-adoption.*`,
  `mcu-preview-integration.*`, `mcu-preview-mypy.log`, `mcu-preview-boundaries.log`.
- After exact normal shutdown/restart, controller
  `d0bcd52b-88db-4011-98d7-947d454fe86f` passes managed MCU Connect, D9 Test,
  Status and Stop, plus both camera identity checks. Tracking passes preparation
  but Start is rejected, then the existing `COORDINATOR_HEALTH_LOST` shutdown
  recurs. `mcu-preview-repaired-managed.json` / `.log` and
  `mcu-preview-repaired-runtime.stderr.log` retain those results.
  `mcu-preview-fault-exit-receipt.json` confirms exact all-owned-process absence.
  Actual Tracking window/ordered-consumer, sustained health and full workload
  acceptance remain open in the [single rig checklist](../rig-verification.md).
- Restored test controller `3b888e38-9328-4863-9098-5f6f8b417891`:
  `mcu_managed_pulse_check.py` / `mcu-handoff-diagnostics.json` / `.log` pass
  managed D10/D11 Test/Status/Stop, confirming configure-before-test with the actual
  board. D10 status/Stop retains 11 generated rises; D11 status shows 21 and Stop
  retains 22. D9 Test then Status after 2.1 seconds confirms firmware automatic
  timeout with active false and one rise. `mcu-handoff-snapshot.json` retains both
  cameras closed/stopped, no preview cleanup pending and inactive diagnostic.
  This generation is normally shut down afterward to restore fresh GUI authority.

Final GUI controller `73987d0f-0d80-4f63-a646-3dba430048bb` is restored in
Configuration. `mcu-final-endpoint.json`, `mcu-final-snapshot.json` and
`mcu-final-processes.json` retain the exact generation, no current errors and seven
managed processes including GUI. No capture command is issued in this generation.
Its retained Visual Stimulus display-unavailable warning leaves control unheld
pending normal GUI review/acknowledgement; no acknowledgement is fabricated.
The known missing projector settings/acceptance remain deferred in the rig list.
The Tracking fault's unique supervisor emergency record is preserved at
[the original report path](../emergency-601837177195700-513bfcb0-d962-4a67-a1c8-396b5ecedfff.json).

`mcu-install-cleanup.json` records initial removal of 64 verified untracked workspace
cache/bytecode targets, 767 files / 18,393,474 bytes. Verification then detects
ordinary CLI/restart bytecode regeneration; `mcu-install-cleanup-final.json` records
54 further removals, 613 files / 7,257,417 bytes. Total removal is 1,380 files /
25,650,891 bytes (24.5 MiB). Final verification finds the recorded targets absent;
the active runtime may create new caches later. No root tmp/build/cache directory
remains at verification. Environment/native binaries, current settings, active process
files, uploaded image, pre-upload backup and unique evidence are preserved.
`mcu-installed-context.json` records six current source/settings hashes, image/backup
hashes, JUnit counts and cleanup totals. `mcu-installation-handoff-verification.log`
records document-link and evidence checks; the original source manifests remain historical.

Firmware installation and Behavior native window ownership are verified in the
stated scopes. D2 receiver correlation, electrical/waveform measurements and
Tracking preview acceptance are still pending. Current reports/TODO own follow-up;
the existing health failure was not repaired by this increment.

Later owner instruction, "yes, stop it": controller
`73987d0f-0d80-4f63-a646-3dba430048bb` normally shuts down via authenticated
`--takeover shutdown`; command `3a756a6c-ff00-46ed-bb16-204fb7aa92fa` completes
successfully ([result](owner-requested-stop.log)). Its
[exact exit receipt](owner-requested-stop-receipt.json) confirms all owned processes
absent; independent [native process inventory](owner-requested-stop-processes.json)
finds zero managed Python processes, and the application guard is free. Runtime
is left stopped. The earlier restoration above is historical to that installation
increment; no further firmware upload, device test or restart occurs for this stop.
