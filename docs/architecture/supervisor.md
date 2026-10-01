# Supervisor

[Overview and decision register](../../architecture.md) ·
[System contracts](system-contracts.md)

The supervisor owns process launch/containment, health, interruption and the
independent emergency report. The controller owns the output reservation and central
metadata writing under the shared E04 storage record below. Process supervision and
failure handling also follow the cross-component rules linked below.

## Governing decisions

- [E08 — Processes and control transport](system-contracts.md#e08): launch ownership,
  registration, health, interruption and application shutdown.
- [E06 — Stop and recovery](system-contracts.md#e06): deadlines, cleanup and fallback
  ownership.
- [E04 — Recording and metadata](#e04): controller metadata writer and reservation,
  supervisor emergency reports.
- [E03 — GUI recovery](gui.md#e03): reconnect policy (no automatic GUI relaunch).
- [E14 — Backend configuration](system-contracts.md#e14): default-file ownership.

Backend-owned camera/recording descendants follow [A02](acquisition.md#a02).

Configuration: [supervisor_config.toml](../../config/backends/supervisor_config.toml).

## Decisions

<a id="e04"></a>
### E04 — Recording layout, identity, and metadata

**Status:** Accepted · **Revision:** 87

**Identity and files**

- Allocate canonical lowercase, hyphenated UUIDv4 session and planned trial IDs when
  Setup is accepted, before fan-out. Reuse them within that attempt/session;
  cancellation, failure or invalidated Ready retires them. Retries/reconnects preserve
  IDs; new Setup allocates new ones. Trial numbers are one-based; within-trial
  shuffled presentations share the trial occurrence's ID.
- The owner's overall experimental-data root is `cephvr-data`; each session below it
  contains `protocol-data` and `spikeglx-data`. All CephVR trial files and central
  metadata share `protocol-data`; keep their HHMMSS names without ID/trial-number
  suffixes. Planned trials are minute-scale under E05; full identities stay in
  metadata. `spikeglx-data` holds the native ephys recording tree transferred later
  from the ephys computer under E09/E12.

```text
cephvr-data/<setup_YYYYMMDD>_<experiment_slug>/<subject>-<setup_HHMMSS>/
  protocol-data/
    SESSION_CONFIG.json
    SESSION_LOG.jsonl
    SCHEMA.json
    <subject>_<trial_start_HHMMSS>_LOG.json
    <subject>_<trial_start_HHMMSS>_<output_tag>.<extension>
  spikeglx-data/
    <native SpikeGLX run folder(s), transferred after acquisition>
```

- `session_directory` in shared preparation/reservation/recovery contracts is the
  session root. Derive `protocol-data` once in the shared path resolver; all local
  output plans resolve there. Keep the reservation lock/marker at the session root.
  Create/validate both child namespaces at Setup without creating trial/ephys files.
  The local reservation does not lock the ephys computer or prove later transfer.
  CephVR cleanup/collision handling must not implicitly delete or overwrite imported
  SpikeGLX files. E12 owns remote path/run identity and native suffix conventions;
  the local camera filename rule does not rename SpikeGLX's native file set.
- Camera tags are `behavioral_cam` / `tracking_cam`, with `.mp4` and `_frames.jsonl`
  (A07); the tracking backend's record is `_tracking.jsonl` (T19). No device-serial
  suffix; device identity belongs in metadata. Stimulus files use the same trial
  prefix: `_stimulus_LOG.json` (always), `_stimulus_frames.jsonl` and `_stimulus.mp4`
  (E13 saving On). V03/V13 own the plan and evidence; no separate recipe file is
  written.
- At accepted Setup, capture a local-wall/host-monotonic anchor and the fixed local
  IANA timezone. Setup date/time names directories; authoritative T derives the
  common trial filename prefix and descriptive event wall times. Writers never use
  open time. Later OS clock/timezone edits cannot alter this session's mapping.
- Record RFC3339 wall timestamps with numeric offset, IANA zone and the Setup anchor
  (`session_setup_wall_time`, `session_setup_monotonic_ns`) in session config; no UTC
  duplicate. Monotonic ns controls software; SpikeGLX pulses align scientific data
  (SYS-004).
- The controller reserves the session directory/output namespace during Setup,
  locally in the same process as its metadata writer, and holds an OS-exclusive lock
  through finalization/confirmed cleanup. Reservation/release are controller-local
  (no RPC); supervisor registration does neither. A persistent marker binds schema,
  session and controller generation; lock ownership, not PID/marker alone,
  establishes live ownership. If the controller dies the OS releases the lock, the
  marker stays unfinished and the next startup recovers it. Clean finalization marks
  complete, syncs the marker, then releases.
  On Windows, a canonical-namespace OS guard precedes filesystem mutation and stays
  held while the file-lock descriptor must close for directory quarantine; failed
  quarantine retains exclusive ownership and unfinished evidence until explicit
  release. Guard ownership is handle-based, not thread-affine, and OS-released on
  process death. This accommodates Windows' prohibition on renaming a directory
  containing open files without an unprotected ownership gap.
- Complete collision checks before Ready. Existing files require a modal/listed-path
  Continue/Cancel choice from the control holder. Continue authorizes deletion only
  of listed files, followed by revalidation/reservation; Cancel preserves files and
  cancels Setup. Apart from Setup-cancellation cleanup below, no directory/unlisted-
  file deletion or overwrite prompt; Starting-phase stops keep E06's written
  metadata. Unexpected later collisions fail as storage/invariant errors.
- Live locks block reuse. An available lock with an unfinished/corrupt/inconsistent
  marker requires recovery resolution while preserving files. Cancelled or failed
  Setup (SettingUp/Ready) deletes everything that attempt created: its marker,
  `protocol-data/`, `spikeglx-data/`, the session directory and a parent experiment
  directory it created, then releases the lock. Record each created path at creation;
  delete only recorded, still-empty paths. A pre-existing or unexpected file found
  there is kept, reported and becomes a cleanup blocker.

**Central metadata**

| File | Contents / publication |
| --- | --- |
| `SESSION_CONFIG.json` | Schema, IDs, fixed trial order, minimal provenance and resolved active setup; freeze/write/sync at Start |
| `<prefix>_LOG.json` | Schema, IDs/trial number, session-config reference, trial protocol/planned epochs/resolved seeds; publish at actual trial start with `complete: false`. At trial end replace atomically with the outcome and an output index: every reserved output's file, owner, format and schema version, presence, closure state and counts, built from reservations and Finished evidence. A crash leaves the start version |
| `SCHEMA.json` | Every output file's fields, units and clocks, generated at Start from the same schema definitions the writers use; each file still carries its own `schema_version` |
| `SESSION_LOG.jsonl` | Append-only concise lifecycle, commands, overrides, errors, incident decisions and recovery results |
| Backend files | Actual frames, tracking, behavior, presentations, device timing and scientific quality |

- Use readable UTF-8 JSON with explicit units and `schema_version: 1`. Shared setup
  appears once. Include active Visual Stimulus setup even with Save Visual Stimulus data off; omit inactive/
  unused/default dumps. Provenance is supervisor/active-backend software versions
  only, not GUI/Git/Python/package inventories. Assets log filenames/extensions only,
  not paths/hashes/sizes/times/copies. Central logs do not contain scientific
  histories.
- [V13](visual_stimulus.md#v13) adds a scoped Visual Stimulus-owned replay manifest in the always-retained
  `_stimulus_LOG.json` for content fingerprints and replay-relevant
  renderer/decoder/graphics provenance; it references verified external originals
  without automatic asset copying. Central trial metadata retains its verified
  reference, seed and compact occurrence summary under E07; the full plan is not
  duplicated.
- Each JSONL event is one complete newline-terminated object. Key order:
  `monotonic_ns`, `wall_time`, `event_type`, `source`, then applicable
  `trial_number`, `outcome`, `details`. Session-config owns log schema/session
  identity; no per-line schema/session/trial IDs or sequence. Physical line order is
  append order; occurrence timestamps need not be append order. No periodic
  status/heartbeat/frame/RPC dumps.
- Event catalog: `session_started`, `trial_started`, `trial_finished`,
  `session_ended`, `command_accepted`, `setup_override`, `error`, `recovery`,
  `spikeglx_started`, `spikeglx_stopped` (E12 run name in details; failures stay
  `error`), and `incident_decision` for E06 operator choices and terminal
  unanswered/automatic-stop dispositions. Trial outcomes `completed`/`interrupted`;
  session `completed`/`stopped`/`interrupted`; recovery `completed`/`failed`. Other
  events omit outcome. Interruption remains a lifecycle outcome.
- After activation, sync `session_started` before any trial; pre-activation
  cancellation creates none. Emit `trial_started` on first valid Started evidence
  from any participant, with `monotonic_ns` = the trial boundary T (not evidence
  receipt); retain partial outputs if another fails, without fabricating a
  nonstarter's recording.
- Required details: command name; override check and space/query/conflict evidence;
  error component/code/short message; recovery component/action/final result. Emit
  one recovery event after completion, not at attempt start or for intermediate
  retries. `incident_decision` includes incident ID/revision, affected scope and
  disposition; operator choices also include authenticated client ID and exact
  Continue/Abort. Automatic stopping/unanswered termination must not be recorded as
  operator consent. Normal lifecycle events omit details; add closure issues not
  already explained by error.
- Persist E06 incident identity/revision, affected functions/data, initial error,
  material escalation and each `incident_decision`. Active incidents are referenced
  in new trial logs, with later changes attributed in SESSION_LOG. Continued trials
  keep explicit missing/failed output evidence; continuing never declares data
  complete or rewrites configuration.
- Persist accepted Stop after trial, withdrawal and Abort with resulting outcomes.
  Keep Setup overrides in memory until Start creates a session log; append after
  `session_started`. Failed/cancelled Setup creates no session log. Routine
  rejection, retries and volatile command-cache contents stay out of logs/emergency
  reports.

**Durability and storage**

- One serialized writer thread inside the controller owns SESSION_CONFIG, central
  trial LOGs and SESSION_LOG. Submit exact immutable validated documents locally;
  each submission binds the controller's exact work/operation and original deadline
  to a retained noncancellable completion, which the controller consumes and retires
  explicitly. Late sync retains its missed-deadline result. Completions update
  controller state through its existing event queue. No
  metadata-writing RPC, supervisor writer queue or second writer. Bound accepted
  unsynced work, including the active write, to **256 operations / 64 MiB**
  serialized. Overflow rejects immediately as persistence failure; never block
  control/health, evict accepted work or silently drop required metadata.
- Required write/append, flush and OS sync share a **5 s** deadline from submission,
  including queue admission/wait. Success follows sync. Failure blocks unstarted work
  or enters E06 incident handling for active work; graceful output closure cannot
  depend on error-log success. Bounds/settings live in experiment_config.toml.
- Never retry an uncertain append or launch another writer against its files.
  Verified late exact-operation evidence may resolve Unconfirmed to Synced/Failed,
  preserving timeout and any Interrupted outcome. Next trial needs prior Finished and
  synced completion.
- Before clean reservation release, the controller seals/drains/closes its writer and
  combines its final metadata results with verified backend Cleanup evidence; an RPC
  request or process exit is not metadata sync proof. On controller loss, preserve
  last confirmed results and mark unknown work unconfirmed; never take over its
  normal files. E08 automatic shutdown and the emergency report remain independent.
  [Writer contract](../../contracts/central-metadata.md) binds this.
- Normal-storage failure, or controller/supervisor loss under E08, triggers one
  compact best-effort independent report under `<software-root>/reports/`, owned by
  the supervisor, or by the surviving controller if the supervisor is confirmed lost.
  Its **5 s** submission deadline cannot delay interruption.
- Startup inspects known unfinished sessions only after the supervisor confirms old
  application processes absent and the controller acquires available locks. The
  controller keeps one atomic owner-private unfinished-session pointer at reservation
  acquisition and removes it only after verified completion or cancelled-Setup cleanup.
  A Start cancelled before activation keeps written metadata and completes the marker
  as `not_activated`. After verified old-process absence, a pointer whose namespace is
  gone (or only a marker-less cleanup quarantine remains) is cleared with a warning.
  The new supervisor returns the prior launcher receipt bound to the pointer's old
  controller/supervisor generations; missing proof remains a blocker. The
  controller owns any repair writes through the same serialized writer under the
  bounded explicit recovery operation. Append evidence-based recovery, including
  missing terminal trial/session outcomes, to intact logs; preserve corrupt/incomplete
  logs and use a separate report. Recovery-written terminal and recovery events use
  the current application's observation clock and label the original trial/session
  end time unconfirmed; they never retroactively timestamp scientific closure.
  Retain any unconfirmed SpikeGLX stop prominently
  with its expected endpoint/run; never silently stop/adopt a running remote
  acquisition or infer stop from local exit (E12). Then complete the marker and
  release the reservation. Never automatically resume a session.
- Query recording-destination free space during Setup only, with a **5 s** limit.
  Below **10,000,000,000 bytes**, or unknown after query failure, requires
  Continue/Cancel with value/reason. Continue cannot override confirmed storage
  failure. No automatic pretrial or in-recording space checks.

**Other-backend work:** Visual Stimulus and tracking output names/formats are bound (V28, T19).
Visual Stimulus [artifact names/ownership](../../contracts/visual_stimulus/runtime-bindings.md#output-reservation-and-replay-artifacts)
use this same namespace/reservation/start-time rule, with no duplicate metadata
writer and no trial file created during Setup.
