# Projector brightness adjustment

[G01](../docs/architecture/gui.md#g01) owns the explicit operator action;
[E02](../docs/architecture/experiment.md#e02) and
[E08](../docs/architecture/system-contracts.md#e08) retain controller authority.

`AdjustProjectorBrightness` accepts an OperatorCommand, the exact configuration
revision and integer `current_ma` from 101 through 2500. It is admitted only in
Configuration with control, no startup blocker, pending manual device work or
configuration transaction. It uses the existing manual-device operation slot,
command-ID retention and Setup time budget. Repeat admission of an identical ID
returns its retained receipt without another SDK invocation. Ready/session phases
reject adjustment. No startup, Load or Setup path applies brightness automatically.

The bundled 32-bit Windows PowerShell helper loads the installed TI DLP EVM GUI
3.2.0.6 DLLs from APPDATA, requests I2C access at address 0x36 and sets manual LED
control, equal RGB currents and enabled RGB LEDs on every discovered interface.
USB interfaces are not mapped to Windows display IDs, assignments or Use flags.
The TI GUI must be closed to avoid access contention. No SDK libraries are bundled.

Each interface must confirm readback equal to the requested current. Following the
owner-provided Desktop reference, a request above 1023 with all three channels
reading 1023 is reported explicitly as clamped, rather than as the requested current.
Discovery of no interfaces, SDK exceptions, readback mismatch, partial confirmation
or release failure completes unsuccessfully with diagnostic output. Successful
completion retains per-interface identity/readback in operation progress.
The requested number is a manual draft, not saved calibration or measured luminance.

The controller launches the helper without a console window. Timeout/cancellation
kills and reaps the child before its operation can release the manual-device gate.
Timeout and partial failures leave actual brightness unconfirmed or partly changed;
there is no automatic retry or rollback. Process termination is not proof of physical
LED current or USB bus recovery. Physical verification remains E15 rig work.
