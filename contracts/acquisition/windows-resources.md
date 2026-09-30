# Windows launch, I/O and resource cleanup

Derived from [E06/E08](../../docs/architecture/system-contracts.md) and
[A02/A03/A07/A08](../../docs/architecture/acquisition.md). This defines the native
adapter contract. Implementation status and static evidence are recorded in the
[implementation review](../../reports/acquisition-implementation-review.md);
Windows behavior and deployment compatibility require rig verification.
Reuse the shared helper; it is not a new launcher service.

## Launch registration and partial children

Use the shared [Windows launch contract](../windows-launch.md) for planned jobs,
creation-time membership, partial-child registration and graceful cleanup. Acquisition
FFmpeg follows A08's pre-T launch (no frames before T) and cancel-before-T cleanup. The sections below bind acquisition-specific
I/O and storage resources; VR uses the same launch mechanism without importing them.

## FFmpeg stdin and cancellation

There is no cross-process accounting pipe: capture-to-recording handoff is in-process
(A07). FFmpeg stdin uses a parent overlapped writer endpoint and a child ordinary
readable stdin handle; progress/stderr use independently drained bounded readers. The
recording thread writes raw frames to that endpoint through the shared
[native cancellation helpers](../native-transport.md) and waits outside control/health
threads. Normal finalization drains allowed input then closes stdin for EOF.
Failure/cancel uses the same pending-operation cancellation/join discipline. Do not
use pipe FlushFileBuffers as a durability or cancellation primitive: it can wait for
the peer. Input format/throughput feasibility remains a rig check (A08).

## Ownership ledger and storage synchronization

The [shared resource ledger](../native-transport.md) owns native transfer/release
mechanics. [Frame buffers](frame-buffers.md) supplies acquisition's layouts and
Win32 named event binding; SDK views and recording resources register in the same
ledger. Keep recording/preview/tracking policy with A03/A04/A07.

For the frame log, append complete lines with ordinary buffered writes, flush the
Python file object, then request FlushFileBuffers on its underlying Windows HANDLE
(converted from the verified CRT descriptor) every `sync_interval_s` and at closure.
Missing access fails preparation capability checks/operation; never treat a Python
flush as OS sync.

For video, open a separate nontruncating GENERIC_WRITE synchronization handle for the
same file identity, with sharing compatible with the encoder's live handle. Verify
sharing as soon as the encoder creates the trial output; no pre-T dummy file. At each
due interval call FlushFileBuffers on that file, independently of encoder writes and
fragment cadence. At closure wait for encoder exit/final index, reopen if necessary,
verify the same file identity, sync and close. Sharing/access/sync failure is a storage
failure, not a reason to skip periodic synchronization or restart the encoder.

Run sync work off control threads, never overlap a second sync on the same file.
An overdue operation remains pending; do not create an unbounded sync queue. Lifecycle
and storage-progress deadlines still apply; cancellation failure retains the blocker.
Success covers bytes flushed by libraries and written by the OS, not encoder-buffered
frames or an asserted maximum-loss interval. Filesystem/hardware durability, live
sharing compatibility and worst-case cancellation latency need rig evidence.

Primary platform references: [creation-time job list](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute),
[handle inheritance](https://learn.microsoft.com/en-us/windows/win32/procthread/creating-processes),
[CancelIoEx](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex),
[synchronous versus asynchronous I/O](https://learn.microsoft.com/en-us/windows/win32/fileio/synchronous-and-asynchronous-i-o),
[FlushFileBuffers](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers).
