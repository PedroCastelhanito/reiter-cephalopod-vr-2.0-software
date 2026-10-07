# CephVR2 Arduino Uno firmware

`cephvr2_mcu/cephvr2_mcu.ino` implements the acquisition A11 serial protocol v3
for the Arduino Uno. Owner-authorized manual uploads to COM8 ran on 2026-10-05
and 2026-10-07. The current protocol-3 image, pre-upload flash backup, verified
upload and matching board CAPS are recorded in
[installation evidence](../../reports/rig-wiring-evidence-2026-10-07/mcu-installation-and-preview.md).
The [earlier protocol-2 evidence](../../reports/mcu-evidence-2026-10-05/README.md)
retains its original image and flash readback.

Build with the installed Arduino AVR core:

```powershell
& 'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe' compile --fqbn arduino:avr:uno firmware/uno/cephvr2_mcu
```

The host must use 115200 baud. Camera and trial-state outputs can use D2–D13;
the projector-flip rising-edge input must use D2 or D3, the Uno external
interrupt pins. One diagnostic can run for at most two seconds. The firmware
counts actual generated output rising transitions, including the initial HIGH;
Trial state's held-HIGH test counts one. Camera counters increment at the timer's
HIGH writes, not from requested rate or elapsed time. Input diagnostics count
observed rising edges. Counts persist after Stop until a new test, with atomic
readback and uint32 saturation. Protocol 3 requires a matching manual firmware
update before the updated host can connect; the prior uploaded image was protocol 2.
The firmware
leaves outputs LOW at boot, on diagnostic completion, after OFF and on watchdog
stop. A successful protocol response confirms only firmware state; electrical
levels, pulse timing, polarity at the connected device and captured edges still
need rig verification.

## Rig wiring to confirm

| Signal | Uno side | Other side | Current status |
| --- | --- | --- | --- |
| Host serial | COM8 USB | Rig PC USB | Protocol-3 CAPS/STATUS verified 2026-10-07 |
| Trial state | D9 output and GND | Recorder digital input and signal ground | Pin assigned; destination channel and 5 V tolerance unconfirmed |
| Projector flip | D2 input and GND | Projector flip source and signal ground | Pin assigned; bounded input test counted zero edges; source voltage unconfirmed |
| Behavioral trigger | D10 output and GND | Behavioral camera trigger input and signal ground | Pin assigned; electrical test and preview pending |
| Tracking trigger | D11 output and GND | Tracking camera trigger input and signal ground | Pin assigned; electrical test and preview pending |

Confirm the destination input tolerates the Uno's 5 V logic and the flip source
is safe for an Uno input before attaching signal wires. Save the actual pin
assignments in the GUI, then use its bounded Test/Stop controls while observing
the receiving instrument. The input test counts rising edges and never drives
the flip line. The output test drives Trial state HIGH for at most two seconds;
its displayed result is firmware evidence, so verify the physical level at the
receiving input separately.

Firmware installation remains manual under A11. Check connected wiring before
any later replacement.
