# Launcher restoration — 2026-10-23

Source: dirty working tree based on59a973ac3ffc6fb331bbee1d93c6b283d6b90474.
Governing rules: [E08](../../../docs/architecture/system-contracts.md#e08),
[E03](../../../docs/architecture/gui.md#e03) and
[ARCH-002](../../../architecture.md#arch-002).

## Finding and repair

At investigation start, native Win32_Process inventory contained no Python/CephVR
runtime processes. The owner-private [stale descriptor](stale-launcher.json)
remained, but its GUI-relaunch event could not be opened (Win32 error2), and there
was no application-exit receipt for its controller generation. A GUI-only reopen
cannot signal an event whose owning launcher has disappeared. Descriptor presence
is not liveness or successful cleanup evidence.

The saved descriptor was written11:28:27. The VS Code Python Environments log
(`20261023T105521/window1/exthost/ms-python.vscode-python-envs/Python Environments.log`)
records a separate normal `scripts/start_runtime_gui.py` start at11:28:27.112,
after starts at11:12:46,11:13:01 and11:13:04. Thus the stale generation was not the
earlier GUI-only reopen generation. Application Error records in11:00–12:00 contain
Python Qt/SIP crashes associated in time with the separate test/probe work, but
none identifies the stale launcher's command/identity. Security process-exit audit
query4689 returned no matching events. The exact launcher termination mechanism
cannot be established from retained evidence; no user action, native crash or
splash regression is asserted as its cause.

`request_gui_relaunch` now translates NativeEventError into WindowsLaunchError,
which the existing command handler renders as an actionable CLI error instead of
a traceback. It preserves the native error and recommends normal startup if the
runtime has stopped. It does not delete state, create an event, retry or start a
second runtime. The small existing replacement module remains the owner; no new
state, dependencies or architecture decision is required.

[Real stale-event output](stale-reopen-output.txt): repaired command exits2,
includes `OpenEventW failed: 2` and normal-start guidance, without a traceback.

## Full native launch and GUI-only restoration

The normal command `python scripts/start_runtime_gui.py` starts all default roles
at14:16:58–59. [Initial native processes](full-launch-processes.json) contain the
launcher, supervisor, controller, acquisition, Visual Stimulus, Tracking, GUI and
renderer; no no-Tracking omission or simulated devices. The GUI reports Controller
connected at14:17:04 and Configuration, trial0/3. Saved projectors are not detected
by Windows, so the expected display-initialization notice is acknowledged without
changing settings, Setup or a trial. Running processes do not establish device
readiness or successful projection.

The first verification was interrupted by physical Escape; no further UI input
was sent until the owner explicitly resumed it. The resumed sequence:

1. Read authenticated [Configuration state](resumed-before-close.json), open and
   immediately close a handle to the live launcher event without signaling it,
   and retain [before identities](resumed-before-close-processes.json).
2. Use native Alt+F4 on the Dashboard, allowing its normal history-save/close path.
   [Closed-GUI inventory](gui-closed-processes.json) has no GUI process; all10 other
   PID/CreationDate/command identities are unchanged. Authenticated
   [controller state](gui-closed.json) remains accessible and the event opens.
3. Run `python scripts/start_runtime_gui.py --reopen-gui` (exit0; empty
   [request output](verified-reopen-output.txt)). [Launcher output](full-launch-output.txt)
   confirms a fresh GUI in the existing application generation.
4. Native inspection observes Controller connected at14:20:23 and Configuration,
   trial0/3. Acknowledge the retained display notice with Return, leaving the GUI
   open. [After identities](gui-reopened-processes.json) and
   [authenticated state](gui-reopened.json) pass the
   [comparison](gui-restoration-comparison.json): GUI PID51444 becomes53692;
   all10 other identities stay unchanged, controller generation remains
   `6e2a7425-30fd-4bdc-97d5-f90b1c05e4de`, and launcher event remains reachable.

The10 unchanged processes include script/venv forwarding processes, launcher,
supervisor, controller, acquisition, Visual Stimulus, Tracking and renderer. The
native GUI screenshots were displayed and inspected through Computer Use; they
are not embedded as if they were the separate earlier startup frame recording.
[Snapshot source](snapshot.py) uses the normal authenticated GetSnapshot endpoint,
provisions/removes only a temporary observing client and claims no control.
Empty participants in Configuration are not backend health/readiness evidence;
native process inventories establish the process-preservation claim.

[Final state](final-state.json), [final process inventory](final-processes.json)
and [checks](final-checks.json), collected another105s after the reopen snapshot,
confirm the same restored process identities, accessible launcher event and
Configuration state. `config/last_configuration.json` is byte-for-byte unchanged
from its hash captured before the full native launch. The app and GUI are left open.

## Validation and limits

- `python -m pytest tests/launcher -q --basetemp=.local-startup-restoration-final --junitxml=reports/runtime-evidence-2026-10-23/launcher-restoration/launcher-tests.xml`:
  [59 passed](launcher-tests.xml),0.41s. Extended existing behavior tests cover
  exact-event success, missing-event and access-denied errors, clear CLI output
  and absence of automatic full-runtime fallback.
- Ruff check/format on replacement.py/test_lifecycle.py pass. Initial format check
  requested test wrapping; formatting was applied before the final passing checks.
- Win32 mypy on launcher:8 sources pass. Backend boundaries:751 modules,
  zero violations; pre-existing size advisories concern other modules.
- No Setup, trial, camera capture, hardware command, projector reconfiguration or
  shutdown fault injection. Full native application startup and same-generation
  GUI restoration are verified; hardware readiness, alternate-DPI/monitor and
  historical untraced-exit cause remain separate limits.
