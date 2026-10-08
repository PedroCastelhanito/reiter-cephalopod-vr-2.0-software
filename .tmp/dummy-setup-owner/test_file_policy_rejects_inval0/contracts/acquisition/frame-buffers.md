# Frame-buffer attachment, ownership and reuse

Derived from [A03/A04/A09](../../docs/architecture/acquisition.md) and
[E06/E08](../../docs/architecture/system-contracts.md). Wire descriptors are in
[messages.proto](../cephvr/acquisition/v1/messages.proto); the byte layout is
[frame_buffers.toml](frame_buffers.toml). These are internal contract declarations,
not an implemented or rig-verified IPC layer.

Shared mapping ownership and native cancellation use [native-transport.md](../native-transport.md).
This contract owns camera layouts, seqlock slot policy, the in-process recording queue
and the Win32 named event binding.

## Allocation and attachment

Shared memory carries pixels only to other processes: the tracking ring and the
preview latest-frame slot. Each allocation has one camera producer and one coordinator
owner. The tracking ring has one fixed consumer. Preview has one slot and zero or one
attached viewer; its descriptor has no fixed consumer. The exact registered viewer is
bound by its transfer target/ledger. Capture does not wait for a viewer, and attachment
or normal detachment does not replace the slot, its scope or producer preparation. All
process identities, session or preview-run scope, camera role, confirmed configuration
revision, native layout and capacity must match the registered preparation. Names are
not independent authority. A restarted process must not attach using its predecessor's
identity. Every replacement allocation gets a fresh UUID and memory name.

The coordinator allocates only after actual settings/layout adoption. Derive offsets,
pixel stride and total required bytes from the versioned layout; reject overflow,
nonpositive dimensions/capacity, unsupported native formats and inconsistent payload
sizes. The OS mapping may be larger due to page rounding; it must cover all declared
bytes. Padding beyond the declared image payload is never interpreted as image data.
The header allocation UUID, magic/version/kind/capacity must match the descriptor.

For each target, send the ring's descriptor with its memory and event names. The
target opens those exact named objects, attaches memory, verifies layout, and
allocates its private working storage before reporting AttachedResource. The
coordinator compares reports against the expected exact resource/transfer IDs;
another participant's acknowledgement cannot satisfy a missing attachment.
For the independently launched tracking consumer, the
[shared Setup handoff](../data-preparation.md) carries the descriptor and exact consumer
confirmation before acquisition Ready; camera-worker readiness cannot acknowledge it.
Only needed resources exist: no tracking ring without an active tracking consumer, no
recording queue without saving. Manual preview gets a slot for each explicitly started
Configuration preview, even without a viewer, with preview-run scope. Session preview
gets one session-scoped slot per enabled camera only when `session_preview_max_hz > 0`.
Reject a kind/scope mismatch. Stop/release manual preview before Setup; never reuse
its allocation for a session.

## Seqlock slots

The producer is the only writer. It never locks, reserves or waits for a reader. To
publish, it picks slot `sequence % capacity`, makes the slot generation odd, writes
metadata and native pixels, makes the generation even, updates `published_count`
and signals the ring event. Alignment is not an atomicity claim; the generation
recheck is the only consistency test. There is no pointer or Python object in the
shared layout, and 64-bit counters never wrap within a session.

A reader notes an even generation, copies the slot metadata and pixels into private
memory, then rechecks the generation and expected `sequence`. A changed or odd
generation, or a newer sequence, means a torn or lapped read: discard the copy and
count a skipped delivery. Readers never modify shared memory. There is no retry,
per-frame lock, copy timeout or abandoned-lock case.

Tracking reads sequences in order. A lapped read is a skipped tracking delivery under
A04: advance to the newest published sequence and apply the reset-to-newest rule. Keep
a discontinuity epoch with frames; the producer advances it for tracking-affecting
gaps and invalid frames, not recording-only losses, before publishing post-gap input.
A consumer handles epoch changes before processing post-gap input. If a reset has
already superseded a private copy, discard that copy before processing; an
already-running algorithm call cannot be revoked by ring metadata. Detailed
algorithm/result invalidation stays with A06/tracking design. The consumer also
applies its frame-age check immediately before processing.

Preview consumption follows [preview control](preview-control.md#attach-or-close-a-viewer):
read the newest published sequence and skip obsolete frames. Manual preview publishes
every valid frame; session preview publishes the newest valid in-trial frame at most
at `session_preview_max_hz`, from the capture thread. Normal viewer detachment releases
its own mapping/handles, leaving the slot and producer running. Frame IDs retain their
source ordering and camera/trial or preview-run scope. Invalid images have accounting
but no pixel slot. Optional camera timing/count validity bits are not saved/drop flags.

## In-process recording queue

When saving, the capture thread hands each admitted valid frame's pixels, and every
received in-trial frame's record, to the recording thread through a bounded in-process
queue of the resolved `recording_queue_frames`. The capture thread never waits: when
the queue is full it drops the oldest waiting frame's pixels, marks its record dropped
and enqueues the new frame. The frame being written to FFmpeg is never removed. Records
awaiting append are bounded by `pending_records_capacity`; exhaustion is an A07 logging
failure. Queue admission is never a saved confirmation.

## Trial reset and stopping

The owner performs normal reset only after the prior producer run, consumer copies,
recording drain/accounting and required closure have finished. Collect matching
completion evidence first. With the producer quiescent, install the new trial UUID,
reset `published_count` and discontinuity metadata, and keep input sealed. Manual
preview has a separate run lifetime and does not participate in trial reset.
Session settings, allocation identity and physical capacity stay fixed.

WorkerPrepareTrial checks this exact binding and prior completion before fresh Ready.
It does not itself grant start. Only authorized execution at T opens admission.
The initially sealed bit is not evidence that an unstarted trial has completed.
At normal/early Stop, the producer seals at its [E11 cutoff](recording-lifecycle.md),
rejects out-of-interval receipts, completes any already-admitted publication/queue
handoff, sets input_sealed and signals the event. Consumers may read remaining
published frames after sealing. The capture thread's end marker and verified Finished
remain separate obligations; a sealed ring proves neither. Tracking additionally obeys
its own [admission cutoff](../tracking/lifecycle.md#producer-cutoff-late-work-and-finalization):
it does not start new estimates after that gate merely to drain this ring. Unread
tracking frames were not necessarily admitted tracking observations; acquisition
retains source accounting.

## Win32 wakeup event (A03)

One small ctypes adapter over public kernel32 calls (CreateEventW/OpenEventW,
WaitForSingleObject, SetEvent, CloseHandle). No private CPython state, pickled
primitives or version-specific reconstruction ABI.

- Per shared ring: one auto-reset event meaning "inspect shared state", not one frame.
  Only the registered consumer data owner waits on it; producer/control threads
  signal it but never consume its wakeups. Every wait has a deadline and rechecks
  `published_count`, flags and cancellation. Publication, sealing, reset and stop
  all signal it. Replacing a consumer requires the previous waiter to have exited.
- The coordinator creates each event with a unique per-allocation name in the
  `Local\` namespace (`cephvr-<allocation_uuid>-event`), failing if the name already
  exists, and restricts access to the current user. Consumers open the exact name from
  their prepared descriptor; a name alone never authorizes attachment, and a mismatch
  with the descriptor's allocation UUID is rejected.
- On partial attachment, close each handle opened by that attachment exactly once.
  Handle values and object names stay out of session/trial logs and public snapshots.

Control and progress monitoring remain independent of the data path. A dead/stuck
participant uses progress monitoring and allocation retirement, not repair.

## Cleanup and failure

Stop publication, finish local copies, drop exported views, then close mappings and
event handles. Record per-participant release against registered obligations; owner
closes its mapping after all users release or exit. On Windows, mapping lifetime ends
when the last handle closes; unlink is not deletion.

Producer failure retires the ring and its event. Retirement is first recorded outside
the ring in owner/supervisor resource state; setting the retired flag or signaling the
event is best effort. Readers of a retired ring discard in-flight copies. Unconfirmed
resources block new Setup under E06; replacement uses fresh memory and events after
cleanup. No automatic worker kill/restart is added.

[Windows resources](windows-resources.md) specifies native cancellation, ownership
and launch cleanup. That adapter still needs implementation and rig evidence. Sources:
[Python shared memory](https://docs.python.org/3/library/multiprocessing.shared_memory.html),
[Win32 event objects](https://learn.microsoft.com/en-us/windows/win32/sync/event-objects),
[WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject).
