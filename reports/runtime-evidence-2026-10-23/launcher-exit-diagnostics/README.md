# Launcher exit diagnostics — 2026-10-23

Source: dirty worktree based on59a973ac3ffc6fb331bbee1d93c6b283d6b90474.
Owner request: add minimal diagnostics while leaving the current runtime running.
Governing decision: [E08rev181](../../../docs/architecture/system-contracts.md#e08).

Each future launcher, after acquiring the application guard, creates an owner-private
`%USERPROFILE%/.cephvr2/runtime/diagnostics/launcher-<controller-generation>.log`.
Sparse JSON lines include UTC/monotonic times, launcher/parent PIDs, generations,
supervisor identity, observed shutdown/registration/channel/process-loss triggers,
deadlines, cleanup entry, exit-receipt publication and return/exception outcome.
Python exceptions add tracebacks. The stdlib fault handler writes native stacks
to the same file only if no handler was already installed; otherwise the existing
handler is preserved and the start record says native_faults_to_log=false.

No credentials or bootstrap payloads are logged. Writes are flushed, not fsynced
per event; this is process-exit evidence, not a power-loss durability guarantee.
Log I/O failures warn without changing cleanup/exception propagation. No periodic
polling, new product processes, policy knobs, automatic deletion or changes to
containment/deadlines. Logs are not proof of process absence or output closure;
the existing exact exit receipt remains authoritative. Forced termination may
leave only the last flushed record; it cannot identify the external killer.

ARCH-002 review: diagnostic I/O/fault-handler lifetime has its own focused module;
main remains the assembly owner of existing lifecycle decisions and adds only
sparse event wiring. No whole-runtime back-reference or new authoritative state.
Owning lifecycle tests were extended instead of adding a per-change test module.

Validation:

- `python -m pytest tests/launcher -q --basetemp=.local-startup-exit-diagnostics --junitxml=reports/runtime-evidence-2026-10-23/launcher-exit-diagnostics/tests.xml`:
  [63 passed](tests.xml),0.54s. Covers flushed identities/triggers, normal return,
  RuntimeError/KeyboardInterrupt propagation, log-open/write failures and preserving
  a pre-existing fault handler. Test fault-handler installation is mocked to avoid
  touching pytest's existing handler; owner-private file publication is real.
- Separate short-lived native Python smoke process uses the actual helper/private
  file creation and `faulthandler.dump_traceback`, then raises/catches a deliberate
  RuntimeError. Its [log](native-smoke/diagnostics/launcher-e4925cce-7388-48be-928a-d7fb3d56e4ac.log)
  contains the shutdown marker, thread stack, exception exit marker and traceback;
  the original exception propagates. No deliberate native crash or app launch.
- Ruff check/format launcher/tests:11 formatted files; Win32 mypy9 launcher sources
  pass. Backend boundary checker:751 modules,zero violations; existing size
  advisories remain. Whitespace passes.
- [Before](runtime-before.json)/[after](runtime-after.json) native Win32_Process
  inventories and [comparison](runtime-comparison.json) confirm all11 baseline
  PID/CreationDate/command identities unchanged. No live-runtime signal, GUI input,
  restart, device action or configuration change was made.

The current launcher predates this change. Integrated production log creation and
native fatal-exit handling remain unverified until a later owner-planned launch;
there is no request or schedule to restart it automatically. The historical stale
launcher's exact termination cause remains unknown.
