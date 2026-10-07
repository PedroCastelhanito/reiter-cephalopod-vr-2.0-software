# MCU diagnostic feedback and receiver observation

Historical preliminary display correction; superseded by the owner's selected
[MCU generated-transition counting](mcu-counted-diagnostics.md). Results below retain
their original scope and do not validate the later firmware counter.

Date: 2026-10-07 (Asia/Tokyo). Working tree based on `08d146d`; this follow-up
includes uncommitted edits and concurrent camera-preview work. It is not the
original frozen-source full-suite run.

Owner request: test physical D2/D9/D10 signals, using the open SpikeGLX display.
Source inspection found that the GUI displayed the protocol 2 input-only `edges`
counter for every diagnostic. That version returned zero for output diagnostics;
firmware did generate those outputs. The [A11 contract](../../contracts/acquisition/microcontroller.md)
has since advanced to protocol 3 with generated output counts.

Change: the existing panel displays firmware-reported HIGH/LOW for Trial state,
running/stopped pulse output for camera tests, and counted rising edges for the
projector input. Output feedback asks the operator to observe the receiving device.
No wire, firmware, output timing, ownership or dependency changes. No new test
module; this reversible presentation correction uses existing behavior coverage.

Validation:

- `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -ra -k 'live_review_microcontroller_routes_bounded_tests or managed_microcontroller_emits_controller_intents or managed_microcontroller_forwards_only_saved_pin or managed_camera_pin_test_uses_saved_role_signal or pin_test_stop_toggle_and_invalidation or managed_mcu_pending_completion_and_final_status' --junitxml reports/rig-wiring-evidence-2026-10-07/mcu-output-feedback.xml`: **6 passed, 285 deselected, 4.59 s**. [Console](mcu-output-feedback-tests.log) and [JUnit](mcu-output-feedback.xml) retained.
- Ruff and format check of `src/cephvr/gui/microcontroller.py`: pass.
- Windows-target mypy of `src/cephvr/gui`: **124 source files pass**.
- `tools/check_backend_boundaries.py`: **598 modules, zero violations**. Existing
  size advisories remain; the focused MCU panel does not trigger one.
- `git diff --check`: pass.

Native process inventory confirms an active managed GUI and acquisition worker.
No takeover, serial open, output command or GUI restart was performed here.
The live GUI uses previously loaded code until its next restart; its tests still
generate signals under the same existing contract.

The owner was asked to observe one test at a time on its mapped SpikeGLX receiving
channel: D9 HIGH then LOW within two seconds; D10 requested 30 Hz, nominal 50% duty,
then LOW; D2 edge accumulation while the projector flip source is active.
Receiving channel IDs and observed waveforms have not yet been supplied. These
local software checks do not establish physical signal or camera-reception passes.
Remaining work stays in the [rig checklist](../rig-verification.md#managed-device-gui).
