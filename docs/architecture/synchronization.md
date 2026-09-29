# Synchronization backend

[Overview and decision register](../../architecture.md) ·
[System contracts](system-contracts.md)

The controller starts and stops SpikeGLX on the ephys computer for paired sessions
through SpikeGLX's own command server over the dedicated Ethernet link (E12).
Scientific alignment is external post hoc work under
[SYS-004](../../architecture.md#sys-004). Camera-trigger microcontroller control
belongs to [acquisition](acquisition.md#a10). The
[SpikeGLX control contract](../../contracts/spikeglx-control.md) binds calls, records
and failure handling; no client is implemented or rig-verified.

Configuration:
[synchronization_config.toml](../../config/backends/synchronization_config.toml).

## Decisions

<a id="e09"></a>
### E09 — Current SpikeGLX operation

**Status:** Accepted · **Revision:** 4

- SpikeGLX acquires electrophysiology and synchronization inputs on the ephys
  computer, writing to its local storage. Session configuration/start/stop is
  coordinated from the rig computer under E12 over the existing Ethernet link.
- Existing camera/VR owners retain their timing/event evidence. Scientific alignment
  and normal file-content validation stay external post hoc; do not introduce a
  separate alignment process or live ephys data-transfer requirement.
- Hardware pulses retain scientific timing authority under SYS-004. Network
  command/response times are control evidence, not simultaneous sampling guarantees.
- After recording, the operator transfers the original SpikeGLX file set into E04's
  session `spikeglx-data` folder; no automatic transfer.

<a id="e12"></a>
### E12 — Remote SpikeGLX control

**Status:** Accepted · **Revision:** 17

- **Owner and transport:** the controller owns the only SpikeGLX client (no
  supervisor fallback), using the official SDK Python wrapper against SpikeGLX's
  command server. Calls run serialized on a controller I/O thread and never block the
  lifecycle loop, health or interruption. No ephys-side CephVR process, listener or
  TLS identity. Security is an installation requirement: the command server listens
  only on the dedicated-link interface and the ephys firewall admits only the rig's
  address.
- **Participation:** pairing is the synchronization backend's per-session enabled
  flag. New configurations default to paired (E10), editable as `[backend] enabled`
  in synchronization_config.toml. A paired session has one session-scoped required
  participant, exempt from E05's per-trial Ready/Started/Stopped/Finished obligations.
  Recording spans all trials and gaps; never restart it per trial.
- **Setup:** require an idle SpikeGLX (never stop, rename or adopt a running
  acquisition), read back version, streams, saved channels and gate/trigger modes,
  require modes that save on startRun, check the pulse inventory, set and read back
  the session run name, and read the data directory. Acquisition settings stay
  operator-owned in SpikeGLX; a change before start fails the attempt. Record the
  readback and the exact configured command-server address/port used for the
  prepared connection in `SESSION_CONFIG.json`; missing endpoint evidence blocks
  paired Ready and later recovery reports it as unknown, not a guessed current value.
- **Pulse inventory:** `synchronization_config.toml` `[pulse_inventory]` maps each
  alignment role (behavioral/tracking camera triggers, photodiode) to stream, stream
  index, saved channel and optional digital bit; camera roles use OneBox. The
  operator reassigns roles by editing that table; it is reread at each Setup without
  restart. Required roles are every enabled externally triggered camera plus the
  photodiode; an unmapped role, wrong stream or unsaved channel blocks Ready. An
  unpaired session records a Setup warning in the session log, with no prompt, that
  CephVR cannot verify pulse recording. The check proves saved-channel configuration,
  not wiring or recorded pulses.
- **Start:** after `session_started` is synchronized, call startRun. Release the first
  trial only after isSaving, a matching run name and increasing sample counts on every
  saved stream within the configured writing-start bound; failure interrupts the
  activated session without creating a trial.
- **During the session:** every `observation_interval_s`, query running, saving, run
  name and each saved stream's sample count. A saved stream with no confirmed advance
  for `no_progress_timeout_s`, saving/running confirmed off, a changed run name or a
  counter reset opens/updates E06's incident prompt. An unreachable server counts as
  no confirmed advance (no separate unknown state). Stop automatically only if
  coordinated local execution cannot continue. Never restart/adopt the remote run.
  Setup, first-start/writing and stop retain their own absolute bounds.
- **Stop:** on session end involving an active/ending trial, issue stopRun at E05's
  local Stopped deadline plus `stop_margin_s` (default **1 s**, configurable; extra
  recording time so SpikeGLX captures the final projector/photodiode transition),
  never earlier merely because software Stopped reports arrived. If trial activity is
  uncertain, interrupt possible producers and use the interruption Stopped deadline
  plus margin. If no trial is involved (between trials or a failed first-start/writing
  gate), stop immediately after resolving any uncertain start. Stay within the
  existing finalization bound; do not wait for local file closure. Never stop a
  different run.
- **Stop confirmation:** a later isRunning = false confirms stopped acquisition;
  native file finalization stays delegated to SpikeGLX and is never reported as CephVR
  CLOSED. Unconfirmed stopping remains a cleanup blocker and is retained in the
  emergency/startup report if E08 automatic shutdown exits, with a warning that
  SpikeGLX may still be recording.
- **Controller loss:** nothing stops the run; a local application exit cannot stop a
  remote run by itself. The emergency report and next-startup warning name the
  expected address and run for manual stopping in SpikeGLX; leaving it running loses
  no data.
- **Uncertain calls:** a timed-out mutating call has unknown outcome; query before any
  further mutation and never repeat startRun blindly. Never kill or restart SpikeGLX.
- **Endpoint and verification:** `[spikeglx] address` is required (installation
  input); `port` defaults to 4142, SpikeGLX's standard command-server port. Versions,
  bounds, wiring and the stop margin require rig verification, not a software claim
  that the final physical photodiode transition was recorded.
