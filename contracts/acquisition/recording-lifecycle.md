# Recording launch and producer cutoffs

Derived from [A07–A09](../../docs/architecture/acquisition.md) and
[E05/E11](../../docs/architecture/experiment.md). These are contracts, not runtime
or rig evidence. Capture and recording are threads of one camera worker (A02).

Metadata is required for every active experiment camera. With `metadata_only=true`,
Setup skips encoder discovery/conversion, PrepareTrial allocates only bounded records
and the writer, and Schedule retains the JSONL path without launching a child.
Release, source admission, Started, cutoff and durable completion follow the same
lifecycle below. No MP4 obligation, pixel pool, video mapping or recording-drop
claim exists in this mode. Sessionless manual preview remains unsaved.

## Launch ordering

1. Setup validates resolved tools/settings, source conversion and attachments, starts
   continuous acquisition and confirms usable delivery under A10. Trial admission stays sealed.
2. PrepareTrial confirms prior closure and prepares the recording thread, its
   in-process queue, private buffers and encoding plan. No FFmpeg process or trial
   file exists yet. Ready confirms this preparation; it cannot claim NVENC
   initialization or encoding.
3. ScheduleTrial supplies T, normal end and final output paths. On accepting it
   (about T − E05 start lead), the camera worker registers/launches a fresh FFmpeg
   process with those paths, the injected raw stdin input arguments at the nominal
   rate and the prepared [recording identity](recording-identity.md) MP4 tags through
   the shared launch helper, and confirms containment. Record the exact MP4 path it
   may create. Feed no frames before T; an empty/unwritten MP4 is the only pre-T file.
   ReleaseTrial must match and meet E05 cutoffs. Blocking launch/I/O remains outside
   control/health. No dummy frames or another launch deadline.
4. At T, after valid release and no cancellation, create `_frames.jsonl` with its header
   line (the recording identity and the [camera-clock descriptor](camera-clock.md)) and
   begin real input to the already running encoder. No trial frames or frame log before
   T.
5. Camera admission remains independent of the encoder. Recording Started still
   requires real in-trial frame/accounting processing by T + 250 ms, not successful
   launch. Launch/initialization failure before T is a required failure before
   release: it interrupts under E06, never a late start; never retry with another
   codec or T.

If the schedule is cancelled, the session interrupted or release fails before T,
fence input, terminate the pre-launched FFmpeg through existing supervision and delete
only the MP4 at its recorded path if that child created it; an unexpected file at
that path is kept and reported under E06. Never abandon an unconfirmed child. A worker
that never began trial work reports unstarted obligations, not fabricated success.

## Camera cutoff

The capture thread seals admission once, recording
`min(local_admission_stop_ns, scheduled_end_ns)`. Normal completion uses the
scheduled end. Preserve frames already received/admitted before that cutoff; exclude
later receipts. Do not use Abort issuance or recording-thread time to retrospectively
change membership. Stop requests carry issuance and cause, not a replacement recording
end; the obsolete request field/tag is reserved in both public and worker Protobuf
messages. Never revise a confirmed cutoff on repeated Stop.

The worker's Stopped evidence includes `recording_end_monotonic_ns` separately from
its actual device/activity-stop time, reported to the coordinator (E08/O2: no direct
worker copy to the supervisor). Stopped stays prompt: it never waits for the recording
thread to drain. Stop/Interrupt fences future execution but does not discard already
admitted frames; the recording thread drains them.

Normal trial end stops only admission and the enabled Trial-state HIGH. On the SDK
owner, seal rings and the old recording queue after the last admitted record, retain
bounded excluded receipts observed before sealing, and detach that trial's recording
buffers. SDK acquisition and camera trigger phase continue; no purge or rearm occurs.
Normal Stopped confirms trial activity ended and required Trial state LOW, without
claiming physical camera stop. It never waits for an arbitrary intertrial drain.

Session cancellation/end, Abort/interruption and required faults physically stop
capture. Deliver camera OFF terminal evidence separately under exact session scope;
then drain excluded buffered results for the prepared margin, retaining the original
deadline. Failed/missing OFF cannot prove successful output stop. Free-running cameras
stop generation promptly. The configured margin covers exposure, transfer/SDK allowance
and one frame period; it is not inferred from an empty queue or nominal bandwidth.
Control handoffs yield and resume the same drain generation/cutoff/margin, retaining
counts without flushing or sealing an incomplete marker. Cleanup waits for this
continuation. Physical stop, bounded retrieval and file closure remain distinct;
no repeated Stop, OFF reply or empty retrieval starts a fresh timeout.

## End marker

After all in-trial frame records and applicable bounded excluded observations are sealed,
the capture thread enqueues exactly one in-process end marker behind the last record. It
carries the in-trial received count, the cutoff, the post-cutoff excluded count,
optional last native counter, separate admission-stop or physical capture-stop
observation and a scoped post-cutoff accounting flag. Normal continuous closure has
no physical capture-stop time: its admission observation must match the retained
normal Stopped proof and its cutoff must equal scheduled end. This path cannot repair
an interrupted trial's missing physical-stop proof. Nothing follows the marker for
that trial. Count excluded retrieved
results plus disjoint countable purge discards; never count an image twice. Unknown
purge/SDK-stop discards make the total `null` and accounting incomplete, not zero.
Missing native last-counter evidence alone does not make accounting incomplete; never
derive counts by subtracting wrapped/reset counters.

On a bounded drain failure, seal and enqueue available evidence only after the capture
loop is quiescent and cannot add old-trial records. Leave actual stop time absent if
unconfirmed and mark incomplete drain honestly. If the capture thread cannot safely
seal, the marker remains missing; finalization reports incomplete/unconfirmed output
under its original deadline. A late pretrial purge cannot revise a sealed trial. The
marker does not release pending records or establish durability.

Schema6 labels normal post-cutoff counts `admission_snapshot` with the observation
time; they do not claim total late/intertrial/physical-stop accounting. Physical-stop
counts retain their separate scope. Preserve only observed last pretrial, first/last
admitted and first excluded native/host records; absent boundary context stays null.
The header binds session/camera to exact worker capture generation. No restart is
allowed in that generation, and unverified absolute frame/pulse offsets stay null.

Successful normal closure requires the end marker with complete scoped accounting,
the camera's matching admission Stopped proof and, when enabled, terminal Trial-state
ON/OFF observations delivered by trial-scoped `RecordPulseEvidence`. This applies to
free-running and external cameras alike. Session-scoped camera OFF serves physical
cleanup and cannot replace Trial-state evidence. Record failures as terminal outcomes with absent ACK/
application proof; receiving a failure is not successful device stopping. The
recording thread retains the evidence for the completion line rather than closing
first. Missing required evidence at the original deadline yields incomplete/
unconfirmed output; close what can safely be closed without extending that deadline.
Persist available evidence and use E06's incident policy: isolated data loss can be
promptable, while unsafe/unconfirmed execution that cannot be isolated requires stopping.

## Persistent timing and failure

The completion line, appended once at closure, stores the producer cutoff, final
received count, accounting completion, post-cutoff accounting and pulse outcomes under
[frame_log_schema.toml](frame_log_schema.toml); unknown values are `null`. After a crash
the frame log has no completion line, which means incomplete. A08 records sequential
images once at the nominal playback rate, without slot omissions or padding; playback
duration need not match trial duration. Real timing comes from source-frame records.

Actual device/pulse stopping, input sealing, accounting completion and durable closure
remain separate obligations. The acquisition aggregate retains per-camera cutoffs
in shared Stopped evidence rather than replacing them with the latest camera's time.
E11 governs other producers and the controller's summary end. Missing proof preserves
uncertainty and the E06 incident classification; all deadlines retain original
issuance/phase anchors. Missing data alone does not force a session interruption.

## Online completion and external file validation

The recording thread maintains bounded accounting as it works: next source ID,
received count, pending records, appended frame-line count, frames written to FFmpeg and
observed encoder/write errors/progress. Advance counters on the corresponding
successful operation, not queue admission. A pipe write or generic encoder progress
value is not proof that a matching encoded frame survives in the file. Do not retain a
second per-frame history for later whole-file comparison or insert validation I/O into
the capture thread.

After the end marker, drain queued frames and records. Reconcile: received IDs are
exactly 0..N-1, every frame line has been appended once, no queued writes remain, and
the marker count/cutoff matches the Stopped evidence. This uses state maintained while
writing, not a reread of the frame log or MP4. A known mismatch or failed required write
remains an E06 failure, never a deferred validation warning.

Set `accounting_complete` only after that reconciliation and successful append of all
frame lines. A matched N=0 needs no fabricated lines; existing A10 frame-health and
Started failures still apply. Interrupted trials can have complete accounting for their
confirmed partial interval. Count invalidity (`null`) is different from a zero count.

Finalization closes FFmpeg's stdin, observes its successful finalization/exit,
appends the completion line, syncs the frame log and video storage, closes owned
handles and reports exact closure results. Encoder-owned MP4 conversion remains
ordinary finalization, not a CephVR verification pass. Existing errors, no-progress
monitoring and E06 deadlines still apply. Synchronization failure must not be ignored.
Only then may Finished satisfy the next-trial gate; permitted all-dropped recordings
retain A07's warning/no-fabricated-video behavior through the explicit
[empty-video completion predicate](empty-video.md). Report content, artifact presence
and closure separately; a known encoder or storage failure cannot qualify as empty
success. No created artifact is deleted to manufacture the absent-artifact case.

Do not run ffprobe/sample-table inspection, packet/frame count scans, frame-log rereads,
frame-line/timestamp comparison or decoding during capture, finalization, the next trial
or session end. There is no recovery tool. File-content validation is external post hoc
work, unrelated to CephVR runtime: no validation process, progress state, control RPC,
background task, skip switch, readiness dependency or runtime gate. Closed/Finished does
not claim that such inspection passed. Configuration/argument/ capability checks,
required live-input validation, ownership/identity checks and successful writer
operations remain runtime obligations.
