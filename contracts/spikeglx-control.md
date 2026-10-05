# SpikeGLX control contract

Authority: [E12/E09](../docs/architecture/synchronization.md),
[SYS-004](../architecture.md#sys-004), [E04](../docs/architecture/supervisor.md#e04),
[E05](../docs/architecture/experiment.md#e05) and
[E06/E08](../docs/architecture/system-contracts.md). Wire types:
[spikeglx.proto](cephvr/synchronization/v1/spikeglx.proto); client boundary:
[spikeglx_client.pyi](spikeglx_client.pyi); reference native keys/codes:
[spikeglx_mapping_reference.json](spikeglx_mapping_reference.json). A read-only
controller connection diagnostic is implemented; the session lifecycle client
remains unimplemented and unverified.

## Owner, transport and security

The controller owns the only SpikeGLX client. It uses the official SpikeGLX SDK Python
wrapper against SpikeGLX's own command server on the ephys computer, reached over
the dedicated rig↔ephys Ethernet link. There is no ephys-side CephVR process,
listener, TLS identity, second configuration file or supervisor client. SDK calls run
on one controller I/O thread, serialized, with results returned to the lifecycle loop
as events (E08); a blocked call never blocks health, control or interruption handling.

Installation requirements, verified on the rig rather than by CephVR: the command
server listens only on the dedicated-link interface, and the ephys Windows firewall
admits its port only from the rig's link address. The rig's `synchronization_config.toml`
holds `[spikeglx] address` (required, no default) and `port` (default 4142, SpikeGLX's
standard command-server port; confirm on the rig).

The managed GUI's Test connection sends an authenticated, read-only controller RPC.
The controller uses the saved endpoint and official SDK wrapper/DLL from the local
SDK package, with at most one outstanding diagnostic and a five-second response
bound. It reports version, running/saving state, run name when validated and data
directory. A timed-out native call remains in flight and blocks another diagnostic
until it finishes. This check neither mutates SpikeGLX nor establishes Setup readiness.

Every mutating call (setRunName, startRun, stopRun) has one absolute deadline from
`native_call_timeout_s`. A timeout means unknown execution: query isRunning/getRunName
before any further mutation and never repeat startRun blindly. Read-only calls may be
retried within their original deadline. Never kill or restart SpikeGLX.

## Participation

Pairing is the synchronization backend's `BackendSettings.enabled`. A paired session
has one session-scoped required participant with no per-trial Ready, Started, Stopped
or Finished obligation; its gates are Setup, the first-trial writing gate, the
in-session monitor and finalization. An unpaired Setup records a warning in the
session log that CephVR cannot verify pulse recording (no prompt) and makes no
SpikeGLX calls.

## Setup

1. Connect; read getVersion; reject a version without a matching mapping reference.
2. Require isRunning = false. An already running acquisition blocks Ready; it is
   never stopped, renamed or adopted.
3. Read getParams (plus the applicable imec/OneBox groups), enumerate streams per
   family and read each stream's sample rate, acquired channels and saved channels
   (getStreamSaveChans). Require gate and trigger modes that start saving on startRun
   (reference codes: `immediate`); anything else blocks Ready with the setting named.
4. Check `[pulse_inventory]` against the saved channels (E12). Read getDataDir.
5. Set the run name `<experiment_slug>_<subject>_<setup_YYYYMMDD>_<setup_HHMMSS>`
   (E04 Setup anchor; characters restricted to `[A-Za-z0-9_-]`) and read it back.
6. Return `SpikeGLXPreparation` for SESSION_CONFIG.json: version, run name, data
   directory, streams/rates/saved channels, gate/trigger modes and resolved pulse
   channels. No opaque parameter dump. Setup creates no recording.

Before startRun, reread the same settings; any change other than the managed run name
fails the attempt. Acquisition settings stay operator-owned in SpikeGLX.

## Start and writing gate

After `session_started` is synchronized (E05), issue startRun. The first trial may be
released only after, within `writing_start_timeout_s`, isSaving is true, getRunName
matches, and every stream with saved channels shows an increasing getStreamSampleCount
between two observations. Failure or timeout interrupts the activated session without
creating a trial. This is online progress evidence, not file-content or pulse proof.

## During the session

Every `observation_interval_s`, query isRunning, isSaving, run name and each saved
stream's sample count (one bounded attempt, at most one outstanding). Each saved stream
keeps the time of its last confirmed sample advance, starting at the writing gate. Any
of these opens or updates the E06 runtime incident (Continue/Abort):

- a saved stream with no confirmed advance for `no_progress_timeout_s`;
- saving or running confirmed false;
- a changed run name;
- a sample counter that decreased (reset).

An unreachable server or failed query is simply no confirmed advance; there is no
separate unknown state. Reconnect on the next observation. A late reply cannot undo an
incident or interruption. The incident clears when every saved stream has advanced
again. Continue accepts the reported loss/uncertainty; it never proves recording.
Recording continues across trials and gaps; never restart or adopt the remote run.
Keep concise current incident status, not a session-log entry per retry.

## Stop and cleanup

On normal completion, Stop after trial, Abort or failure, stop the paired run during
session finalization independently of local output closure:

- For an active/ending trial, `stop_due_ns = local_stopped_deadline_ns + stop_margin_ns`.
  Use the existing E05 normal-end or earliest interruption deadline; early Stopped
  reports do not shorten the margin. The margin gives SpikeGLX time to record the final
  optical transition; it does not prove the photodiode observed it.
- With no trial involved (between trials, pretrial start/writing-gate failure), stop
  immediately once any uncertain start has been reconciled.
- If trial activity is uncertain, interrupt all possibly active local producers and use
  that interruption's Stopped deadline plus margin.
- Before stopRun, query a fresh run identity: the running run must match the session's
  run name and data directory. A different run is never stopped or adopted. If idle and
  no start is unresolved, stopping is already confirmed.
- A later isRunning = false confirms acquisition stopped; native file finalization
  remains SpikeGLX-owned and is never reported as CephVR CLOSED. Stop confirmation does
  not require saving or sample progress.

`[monitor] stop_margin_s` (default 1 s, nonnegative, exact-nanosecond; tune on
the rig) and native_call_timeout_s must satisfy: stop_evidence_allowance_ns + margin +
3 × native_call_timeout_ns fits within trial_finished.initial_ns + the shared
ControlPolicies.recovery_ns. This reserves identity check, stop and confirmation
without extending E05; uncertain-start reconciliation uses the same budget.

Failure or timeout leaves an E06 cleanup blocker. If the controller is lost (E08 full
shutdown), no CephVR process can stop the run: the emergency report and next-startup
warning name the expected address and run and state that SpikeGLX may still be
recording and must be stopped in SpikeGLX. Leaving it running loses no data. Next
startup never silently adopts or stops a running SpikeGLX acquisition. Neither network
failure nor local exit establishes that remote acquisition ended.

Operating restriction: from Setup through cleanup the operator does not change
SpikeGLX settings or runs. The native API cannot enforce this; detected changes are
required failures under the rules above.

## Records and clocks

SESSION_CONFIG.json records `SpikeGLXPreparation`. The session log records a confirmed
start (`spikeglx_started`, after the writing gate) and confirmed stop (`spikeglx_stopped`)
with the run name; failures use `error`/`recovery` events.
Command/response times are rig host-clock control evidence (SYS-004); they do not
align clocks or prove a pulse was recorded. The operator transfers the native run
tree into E04's `spikeglx-data/` folder afterwards (E09).

## Rig verification

Installed SDK/SpikeGLX versions, command-server port, interface binding and firewall
rule, run-name collision behavior, startRun-to-saving latency, sample-count behavior per
stream, stopRun completion, unknown-run rejection, stop margin against the last
photodiode edge, and link loss (recovery before/after the no-progress timeout, one
stalled stream while others advance, counter resets, late replies after interruption).
See [rig verification](../reports/rig-verification.md).
