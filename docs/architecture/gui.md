# GUI client

[Overview and decision register](../../architecture.md) ·
[System contracts](system-contracts.md)

GUI connection and control rules. The controller remains authoritative; the GUI is a
client.

Related: [controller authority](experiment.md#e02),
[process startup/shutdown and state transport](system-contracts.md#e08).

Configuration: [gui_config.toml](../../config/backends/gui_config.toml).

## Decisions

<a id="e03"></a>
### E03 — GUI disconnection and control lease

**Status:** Accepted · **Revision:** 28

- **Closure and loss:** intentional GUI closure is allowed. GUI connection loss or
  crash never pauses, stops, restarts, or resumes the experiment. Unexpected
  connection loss produces a warning and triggers reconnection.
- **One GUI:** run at most one GUI process; ignore GUI launch requests while it is
  running. No automatic GUI relaunch and no standby GUI: after a crash the operator
  reopens it from the normal launcher while the experiment continues. Headless
  clients may still observe state concurrently.
- **Incidents:** during experiment execution, show E06's single updating incident
  window. Continuable incidents offer Continue session / Abort session while the
  original timeline runs; blocking incidents explain automatic stopping and allow
  acknowledgement. Restore retained incidents after reconnect, coalesce repeats and
  never block backend work. Closing the window is not consent; decisions use the
  existing control lease and revision-checked RespondToPrompt binding in the
  [incident contract](../../contracts/operator-incidents.md).
- **Control lease:** exactly one client holds the control lease required for
  configuration, Setup, Start, Stop after trial, Abort now, and other state-changing
  operator commands. Scope each lease to the controller process/generation and
  session.
- **Lease liveness:** the holder's exact open `WatchState` subscription is its lease
  liveness; there is no renewal call or reconnect reservation. On observed
  stream/transport loss, atomically release control and invalidate its generation.
  Accepted commands/operations and active experiments continue; in-flight commands
  not yet admitted recheck authority. Manual preview and retained camera editing
  connections follow A10's [control-loss cleanup rules](acquisition.md#a10).
- **Take control:** every new/reconnected/reopened GUI subscription starts as an
  observer. Install current state/configuration, acknowledge existing reconnect
  warnings, then require explicit **Take control** to acquire or replace the lease.
  This atomic action may replace the old lease at any time and invalidates its
  generation. No recovery tokens, replacement credentials, grace timer or automatic
  lease restoration.
- **State views:** `WatchState` sends one consistent current control-state view on
  connection and whenever that state changes. Clients replace their control view
  atomically; reconnecting starts from fresh state, without replaying events or
  merging patches. Keep the GUI Synchronizing/read-only until it installs the initial
  view and its matching configuration. `GetSnapshot` remains a read-only one-shot
  query; do not poll it periodically.
- **View identity:** identify views by controller generation and increasing state
  revision. Revisions may skip; reject older views without treating a skipped revision
  as missing work. Configuration values arrive with the first view of each stream and
  whenever their revision changes (E08); within that stream, a view without values
  uses the values installed at its revision. Never reuse values across streams.
  Missing/mismatched configuration invalidates the view; remain read-only and
  resubscribe. Command admission still revalidates authority, configuration and
  lifecycle.
- **Reconnect warnings:** built from the Snapshot's retained errors, recoveries and
  runtime incidents for the current Setup/session, bounded by
  `[control].max_retained_incidents` (default 256; oldest resolved entries evicted
  first, active incidents never). The Snapshot reports the retained coverage start and
  truncation; do not imply a complete history of a longer absence. There is no
  separate history RPC. Exclude scientific data, raw RPCs and unchanged heartbeats.
- **Warning modal:** after synchronization following an unexpected disconnect or
  crash, show a modal warning. Keep state-changing GUI controls disabled until the
  operator acknowledges it. Acknowledgement changes only GUI state: it does not pause
  execution, clear errors, recover or claim a lease, or alter controller state.
- **Reconnect schedule:** after unexpected controller-connection loss, the GUI retries
  immediately, then after 1, 2, and 5 seconds, and every 5 seconds thereafter, until
  connected or the GUI is intentionally closed. A successful connection resets the
  schedule. Retry duration does not extend control ownership. E08 automatic
  application shutdown overrides this loop after confirmed controller/supervisor loss;
  display the shutdown reason while alive without delaying process exit.
