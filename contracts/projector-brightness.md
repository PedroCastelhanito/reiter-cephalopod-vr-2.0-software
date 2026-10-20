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

The controller plans `controller_projector_brightness` with its exact admitted operator
operation and no session/trial work. The existing E08 launcher creates it suspended,
confirms PID/creation time/executable/job containment and resumes only after the
supervisor confirms registration. No console, Ready or heartbeat is used. One original
Setup deadline covers planning, creation, SDK execution, pipe drain, native job absence
and supervisor release. Reserve two seconds from that same budget for cleanup.
Cancellation/timeout terminates the exact job and descendants, drains/reaps within
that budget, and confirms the retained exact plan/process through native_cleanup_complete.
A partial launch remains retained until reconciled. The manual-device slot cannot
release while the worker thread or exact process/job/pipe cleanup is unconfirmed.
There is no automatic retry or deadline extension. Process termination is not proof
of physical LED current or USB bus recovery; physical verification remains E15 rig work.

## Structured result and experiment evidence

The helper emits exactly one `CEPHVR_BRIGHTNESS_RESULT=` UTF-8 JSON line after interface
processing, separate from human diagnostics. Version1 binds `requested_ma`, positive
`discovered_interfaces` (at most64), `success` and one `interfaces` entry per discovered
index in order. Each entry records `index`, `name`, `id`, `readback_ma` (red/green/blue
integer mA or null), `clamped` (bool or null), `confirmed`, `release_confirmed` and
`error`. Identity/error strings are bounded to2048 characters; captured native output
uses the existing bounded pipe owner. Missing/duplicate/malformed/overflowed output,
missing interfaces, contradictory confirmation or nonzero exit fails the operation.
A complete partial-failure aggregate retains successful and failed interfaces; an
incomplete/stuck helper cannot synthesize success from a prose tail. Only exact RGB
readback or the existing explicit1023 clamp can set confirmed=true. SDK USB release
and native process cleanup are separate evidence.

Latest admitted attempt evidence is frozen at Start into existing SESSION_CONFIG.json
under `projector_brightness`; each trial LOG already references that file. SCHEMA.json
self-describes the additive version1 record. [Central metadata](central-metadata.md#projector-brightness)
owns exact fields/meaning. No new file, history stream, saved calibration, automatic
application or claim of current physical brightness is introduced. GUI progress retains
human diagnostics; machine JSON stays in experiment evidence.
