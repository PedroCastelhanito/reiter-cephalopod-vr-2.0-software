# CephVR2 Arduino Uno firmware

`cephvr2_mcu/cephvr2_mcu.ino` implements the acquisition A11 serial protocol v2
for the Arduino Uno. The owner authorized one manual upload to COM8 on
2026-10-05; the verified image and pre-upload flash readback are preserved in
[`reports/mcu-evidence-2026-10-05`](../../reports/mcu-evidence-2026-10-05/README.md).

Build with the installed Arduino AVR core:

```powershell
& 'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe' compile --fqbn arduino:avr:uno firmware/uno/cephvr2_mcu
```

The host must use 115200 baud. Camera and trial-state outputs can use D2–D13;
the projector-flip rising-edge input must use D2 or D3, the Uno external
interrupt pins. One diagnostic can run for at most two seconds. The firmware
leaves outputs LOW at boot, on diagnostic completion, after OFF and on watchdog
stop. A successful protocol response confirms only firmware state; electrical
levels, pulse timing, polarity at the connected device and captured edges still
need rig verification.

## Rig wiring to confirm

| Signal | Uno side | Other side | Current status |
| --- | --- | --- | --- |
| Host serial | COM8 USB | Rig PC USB | Connected; CAPS/STATUS passed |
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
