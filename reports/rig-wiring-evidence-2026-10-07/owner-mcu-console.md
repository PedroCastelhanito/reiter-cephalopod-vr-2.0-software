# Owner-supplied managed MCU diagnostic evidence

Received 2026-10-07 (Asia/Tokyo) from the owner's runtime GUI console paste.
Source revision, controller generation, test duration, raw serial replies and
independent physical observations were not supplied. This was not an agent-run
repeat. The console explicitly identifies the controller route.

```text
Requested Projector flip: pin D2, rising-edge input observation through controller.
projector-flip: running, 0 rising edges reported.
mcu: Completed
projector-flip: stopped, 120 rising edges reported.
mcu: Completed
Requested Trial state: pin D9, active-high output test through controller.
trial-state: running, 0 rising edges reported.
mcu: Completed
trial-state: stopped, 0 rising edges reported.
mcu: Completed
Requested Behavior cam: pin D10, requested 30 Hz output test through controller.
camera-40065509: running, 0 rising edges reported.
mcu: Completed
camera-40065509: stopped, 0 rising edges reported.
mcu: Completed
```

All three diagnostic Start/Stop pairs report completion. D2 reports 120 observed
rising edges; the paste alone does not identify their physical source or rate.
Under the then-installed protocol 2 (before the owner's later revision of
[A11](../../docs/architecture/acquisition.md#a11)), output diagnostics reported
zero edges. Thus these D9/D10 zero counts were expected and do not
measure output level, pulse rate or camera reception. The D10 rate is requested
30 Hz, not a measurement. Earlier agent-run ordinary Status/Stop failures remain
separate evidence; this paste covers diagnostic operations only. Physical
correlation and remaining acceptance stay in the [rig checklist](../rig-verification.md).
