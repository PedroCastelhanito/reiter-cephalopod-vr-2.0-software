# COM8 Arduino Uno upload and handshake — 2026-10-05

Source state: `fe1825fbe70625521fd77979ae19ee873fe57ba6` plus uncommitted
CephVR2 MCU changes. Board enumeration: Arduino UNO on COM8, FQBN
`arduino:avr:uno`. Arduino CLI 1.5.1, AVR core 1.8.8.

- Before upload, `avrdude 6.3.0-arduino17` read the ATmega328P flash through
  COM8 into `legacy-com8-flash.hex` (78,861 bytes; SHA-256
  `10B0055F8B7F9070537EA8E58DA757D6AA7F1D5774D6A5E58F889C05F034A85B`).
  This preserves flash contents, not a complete rollback of EEPROM/fuses or a
  source sketch.
- The Uno build of `firmware/uno/cephvr2_mcu/cephvr2_mcu.ino` used 10,920
  flash bytes and 1,112 global SRAM bytes. `cephvr2-com8-upload.hex` is the
  exact uploaded file (30,732 bytes; SHA-256
  `83AC07F92814FCFEAE0DF8C3C7E60EF00A4C217F96FDEB0A8182B5276BD0A126`).
- The owner-authorized upload used `arduino-cli upload -p COM8 --fqbn
  arduino:avr:uno --input-file .mcu-build/cephvr2_mcu.ino.hex --verify` and
  exited 0. This is upload verification, not electrical acceptance.
- A read-only direct CAPS returned `protocol=2 firmware=cephvr2_uno_1`,
  D2–D13 pins, D2/D3 input pins, 0.1–100.0 Hz, and 500–10000 ms watchdog
  bounds. After a host serial read-path repair, the actual `SerialOwner.connect`
  returned matched CAPS and STATUS on COM8: configuration invalid, watchdog
  stopped false, both camera outputs disabled/stopped, malformed and unmatched
  reply counts zero. The port was closed afterward.

The owner assigned Trial state D9, Projector flip D2, behavioral camera D10 and
tracking camera D11 on 2026-10-05. A subsequent direct `SerialOwnerBridge` check
on COM8 used the loaded 115200-baud/100 ms ACK policy: CAPS returned protocol 2,
firmware `cephvr2_uno_1` and input pins D2/D3, with both camera outputs stopped.
`DIAG_START kind=projector_flip pin=D2 duration_ms=2000` returned active true,
zero edges; after 2.1 s, `DIAG_STATUS` returned active false, zero edges. The port
was closed. This confirms the bounded input command and timeout, but no projector
flips were observed and no electrical level was measured. The owner subsequently
confirmed the projector was off during this test, so zero edges were expected.
Source state is the
same HEAD above plus uncommitted pin/config/host changes; this was not a GUI RPC.

No CONFIGURE, ON, output diagnostic, physical voltage, camera pulse, or GUI pin-test
command was run. Attached rig wiring and destination channels were not inspected.
