# Compact tracking recording

Authority: [T14/T15/T19](../../docs/architecture/tracking.md#t14). This contract governs
the runtime writer; it is not a measured durability guarantee.

## Ownership and admission

One internal writer thread in T08's tracking process owns a trial-scoped file reserved
under E04: `<prefix>_tracking.jsonl` in `protocol-data`. Use the authoritative trial
prefix and E11 interval; acquisition's tracking-camera video/frame-log files stay separate.
Declare/reserve the path during Setup without opening trial files. Saving Off creates
no writer/file dependency. No new process, database, scientific controller relay or
supervisor scientific writer is introduced.

Pose/movement/control producers enqueue immutable compact observations and events through
one bounded admission boundary. Admission order gives the line order; each payload also
retains its own occurrence/source time. Admit a pose observation before making it visible
to movement selection so dependent lines never reference an unadmitted pose. Baselines,
invalid observations and reset/discard events remain scientific records. The A06 Visual Stimulus queue
is independent: a result discarded there is not removed from this record stream.

The writer serializes each typed record once to one line. Bound both queued and in-flight
records by count and retained bytes; account serialized copies and buffers until released.
Reserve finite bookkeeping capacity for failure/cutoff/count records during Setup. Never
borrow acquisition storage for an unbounded writer backlog. Admission cannot block
movement on disk or durable sync. Failure to admit required evidence interrupts via
E06/E10; do not evict older records, report success or create a rescue queue.
Control/health remain responsive independently of writer progress under T08.

## Line format and content

The file is UTF-8 JSON Lines: each record is one compact JSON object followed by LF,
appended only. Use finite numbers, no duplicate keys, no raw LF inside a line and no
arbitrary object deserialization. There is no envelope, framing, per-line sequence field
or checksum; [record_codec.py](record_codec.py) is the pure line helper. Line one is the
header: `stream_kind=tracking`, `schema_version=2`, session/trial IDs, exact writer
generation and prepared tracking/source identity. A reader rejects an unsupported stream
kind/schema rather than interpreting tracking lines as Visual Stimulus evidence.
Movement feedback and registered stage payloads are decoded JSON objects under
[records.md](records.md), with no base64 or escaped stage-payload strings.

Line kinds are header, pose observation, movement result, reset, discard accounting and
trial completion. Each dependent line refers only to already-declared identities/
observations. Pose identity/timestamps/selection evidence follow T09/T17; result lineage
follows A05/A06 and the existing Visual Stimulus feedback boundary; every reset is one line with its
reset_generation and causes. Keep physical units, validity and missing values explicit.
Do not add dense flow, masks or image histories. [records.md](records.md) owns exact
independent payloads/limits. Estimator-dependent quality fields are bound in the
[pipeline catalogue](pipeline-catalogue.md#evidence); do not duplicate schemas here.

## Resource configuration and synchronization

[TrackingRecordingSettings](../cephvr/tracking/v1/recording.proto) is the resolved copy of
these file-only tracking_config.toml values, delivered in TrackingFilePolicies.recording
and mandatory only when saving is enabled:

| Setting under recording | Rule |
| --- | --- |
| sync_interval_s | Positive finite; exact positive int64 nanoseconds. |
| write_progress_timeout_s | Positive finite; exact positive int64 nanoseconds. |
| max_pending_records | Positive uint32, including active work and reserved bookkeeping. |
| max_pending_bytes | Positive uint64 within allocation/platform limits; all retained buffers. |
| max_record_bytes | Positive uint32 bound on one serialized line excluding LF; enough for every supported required record. |

E14 supplies these engineering starting limits. Setup validates compatible bounds,
serialization storage and reserved capacity: one maximum line plus LF must fit in
max_pending_bytes with room for at least four such lines. Count queued and active writer
work against the same byte/count limits; whichever is reached first controls admission.
The full count capacity need not fit when every line is maximum-sized. These fields cannot
be overridden by trial protocols or session edits; save_tracking_data remains an ordinary
session switch. Pose-history capacity is separately bounded and its live geometry/storage
still counts against FileLimits.max_native_bytes. These limits never supply scientific
age/quality thresholds or establish rig throughput.

The writer appends continuously and requests an OS sync every sync_interval_s while
unsynced bytes exist, including when frame arrivals stop, and at closure. It reports last
append progress and last confirmed sync separately. The progress timeout bounds
continuously outstanding append/sync work from its start/last actual progress; an idle
stream with no work is not a storage fault. The timer for pending work cannot be reset by
heartbeats or new admissions. A failed/timed-out operation follows E06; keep handles/
resources alive until the owning native work is reconciled or stopped.

Feedback delivery never waits for individual line durability. The sync interval is not a
maximum data-loss bound: queued records and writes/sync in progress can be lost. At trial
cutoff, seal admission after producers reconcile their admitted observations and
accounting, drain, append the validated completion line, sync and close without waiting
for a periodic tick. Report exact E06 closure evidence; a completion line cannot prove the
later success of its own file's sync/close. No file reread is part of this path.

## Crash state and reading

After a crash the file is valid up to its last complete line; readers discard an
incomplete final line (bytes after the last LF). Readable lines do not prove file closure,
successful sync or complete trial coverage; a missing completion line means the trial
record is partial. There is no recovery tool, repair, live or between-trial reread or
session restart. Runtime/rig verification is still outstanding under E15.
