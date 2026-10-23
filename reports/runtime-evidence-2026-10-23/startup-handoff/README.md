# Native startup handoff — 2026-10-23

Source: dirty working tree based on59a973ac3ffc6fb331bbee1d93c6b283d6b90474.
Tested splash.py SHA256:
`f9d8c60c5cb7de44d7381d57608cb2893add32974b6d9b6381805407d57bd641`.
Governing rule: [G02](../../../docs/architecture/gui.md#g02), startup amendment135;
current assessment: [Runtime](../../runtime.md#startup-splash-preview).

The shared reveal path maximizes at opacity0, processes native expose/layout events
after construction, synchronously repaints the actual window, restores opacity,
then finishes the splash. It no longer discards a hidden grab or queues another
maximize. The three-theme owning test asserts first-paint opacity0/maximized and
restored opacity1, in addition to existing Show ordering/style assertions.

Repository Python3.11 validation:

- `python -m pytest tests/gui/test_dashboard.py -q -k "startup_splash or startup_bootstrap or splash_moves" --basetemp=.pytest-startup-handoff-check2`:
  8 passed,840 deselected,12.72s with the default offscreen platform.
- `QT_QPA_PLATFORM=windows` and the same pytest module with
  `-k startup_splash_hides_construction --basetemp=.pytest-startup-handoff-native`:
  3 passed,845 deselected,8.61s. Output includes a handled Windows HRESULT
  `0x8001010d` diagnostic at splash.begin; all assertions complete.
- Ruff check/format on splash.py and the owning test module; Win32 mypy splash.py;
  backend boundaries751 modules/zero violations and whitespace checks pass.
  Existing boundary size advisories concern other source modules.

## Foreground native probe

Run from the repository root with the repository Python:

```text
python -X faulthandler -u reports/runtime-evidence-2026-10-23/startup-handoff/native_probe.py
```

[Probe source](native_probe.py) uses native Qt6.11, actual DashboardWindow and
StartupSplash.reveal with isolated INI preferences, no sample devices, controller
or backend connections. It automatically launches Standard, Retro and Amber, each
for4s. Temporary topmost flags keep the tested windows visible despite foreground
desktop activity; these flags are test instrumentation, not a product change.
Its bundled FFmpeg diagnostic capture requests60fps,1920x1080 primary operator
display (DELL S2721HS, available1920x1032),30s. No experiment operation occurs.

[Output](native-verified-output.txt) records all three reveals and event loop exit0;
the command exits0. A handled `0x8001010d` appears before the launches.
[Native paint records](native-probe-results.json) have first-paint opacity0 and
maximized=true for all three themes (assert-checked after the run).
[Recording](native-verified.mp4) and [contact sheet](native-verified-contact.png)
include all three populated dashboards. The contact sheet was visually inspected.

[Frame analysis](native-verified-analysis.json):1627 decoded frames, actual average
54.2333fps. For every frame, sample the client rectangle x0:1920,y30:1030 on a4px
grid; classify a sampled pixel as white only if all decoded channels exceed235.
Zero frames exceed90% white; maximum fraction0.002 (0.2%). This is desktop capture
evidence, not a guarantee about sub-frame scanout or alternate display conditions.
Frame times in this analysis use index/average rate and are approximate.

## Managed launches and earlier attempts

The idle managed application was closed through its normal GUI save/close path.
`python scripts/start_runtime_gui.py --reopen-gui` reopens the GUI in the same
controller generation. Native inspection observed populated Configuration, trial0/3
and Controller connected at11:22:55 and11:24:03; no Setup/trial/device operations.
Later window inventory no longer contained the managed Dashboard; its departure
was not traced, so no final sustained-availability claim is made. A final restoration
request failed with `NativeEventError: OpenEventW failed: 2` opening the launcher's
GUI-relaunch event. The command exited1 and no managed Dashboard appeared during
a bounded15s window observation. No fresh full runtime was launched; the cause of
the event/GUI departure is unresolved and separate from handoff presentation proof.

Earlier retained desktop recordings (`managed-reopen*`, `managed-foreground`,
`native-three-styles`, `native-foreground-probe`, `native-topmost`) are incomplete,
occluded or exploratory and are not presentation acceptance. An attempted analysis
before the second recorder finalized failed with an incomplete MP4; the completed
recording was subsequently analyzed. Two interactive probes exited without usable
transition evidence. The first automatic probe reached all three reveals, then
hit a Qt finalization access violation; explicit deferred deletion/removal of its
event filter produces the clean final run above. These are probe limitations,
not established backend failures. The initial offscreen test observer referenced
its target before initialization, exiting1; initializing it before installation
fixed that test-only error before the passing run.

At the end of this initial run, full-runtime launch and restoration remained
unverified. The later [launcher restoration evidence](../launcher-restoration/README.md)
records the diagnostic repair, successful full native startup and GUI-only
close/reopen with unchanged backend identities. Alternate monitor/DPI, CRT-off and
controller-unavailable variants remain in the [single rig checklist](../../rig-verification.md).
