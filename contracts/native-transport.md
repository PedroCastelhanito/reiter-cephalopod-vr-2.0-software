# Shared native transport mechanisms

Authority: [E08](../docs/architecture/system-contracts.md#e08), with backend policy
owned by [acquisition](acquisition/frame-buffers.md) and [VR](vr/runtime-bindings.md).
[Native interfaces](native_transport.pyi) describe small imported helpers, not a new
service, universal queue or running Windows implementation.

## Shared implementation boundary

Use one implementation of bounded message pipes, mapping open/attach/release, native
I/O cancellation and the resource-ownership ledger. Existing launch helpers remain
owned by [windows-launch.md](windows-launch.md). Helpers receive the already adopted
backend descriptor and limits; they never read another configuration file or choose
queue capacities, required participants, overflow behavior or stopping policy.

Use Windows message-mode named pipes, one bounded serialized Protobuf message per OS
message with send_bytes/recv_bytes semantics. VR feedback result/credit paths use
this adapter; VR recording and acquisition have no cross-process pipe (V12, A07). No extra VR length-prefix codec and no Python
object unpickling. Preserve existing message payload types, source/generation identities,
sequence numbers, final counts and acknowledgements. Byte-stream FFmpeg stdin is a
separate adapter over the same cancellation primitive; it is not message-mode media input.

Use overlapped reads/writes with one in-flight operation per direction. Retain the exact
OVERLAPPED/event/buffer until completion. The receiver allocates only its configured
maximum; ERROR_MORE_DATA/oversize is failure, never unbounded reassembly. Include a
stop event and earliest existing deadline in waits. Cancellation seals admission,
requests CancelIoEx for the exact operation, and observes completion before releasing
its storage/handle. ERROR_NOT_FOUND or a successful cancellation request is not proof
of observed completion. Broken/partially delivered messages retire that pipe; never
silently redeliver into another generation or release backend permits speculatively.

An unavoidable synchronous library call stays in its owning data thread. Where supported,
request CancelSynchronousIo for that thread and still wait for completion. If it cannot
finish, retain its resources and report cleanup blocked under E06; no automatic worker
kill or claim that cancelling a Python future released native storage. Control/health
work remains independently responsive. Do not use pipe FlushFileBuffers as cancellation
or file-durability evidence.

Mappings are page-file-backed, in the Local namespace with fresh registered identities.
Restrict names/pipes to the authorized process-tree security context, authenticate the
registered peer/generation and startup nonce, and check size/offset overflow before attach.
Backend-specific descriptor/header validation still precedes use. Native device keys and
process-local HANDLE values are not portable resource IDs. Retain exact owner process
instance, resource identity, transfer/attachment state and release evidence in one ledger.
Never close a possibly reused remote numeric handle. An untransferred duplicate may be
closed locally; uncertain remote ownership needs verified reconciliation/process exit.
Unmap/close only after consumers and native I/O have ceased using the storage. Repeated
cleanup is idempotent; a timeout cannot grant permission to reuse a live allocation.

## Backend responsibilities stay separate

| Backend path | Rules supplied by its owner, not by the helper |
| --- | --- |
| Acquisition tracking/preview | A03 seqlock slots, reset-to-newest/latest-slot policies, Win32 named event adapter and attachment rules. Recording stays in-process. |
| VR recording | V12 drop-incoming admission, in-process PBO capture slots, distinct required-evidence capacity. Recording stays in-process. |
| Tracking results to VR | A06 ordered pending capacity, generation-scoped credits/discards and finite batch. |

Never force these paths into one ring implementation or import a camera overload policy
into VR. Backend data threads call the potentially waiting pipe helper; render
and control event loops retain their existing bounded admission and health obligations.
This sharing reduces native mechanism duplication without claiming new latency guarantees.

Storage sync stays in [backend storage contracts](acquisition/windows-resources.md),
not the pipe helper. Windows behavior, cancellation/cleanup and workload performance still
need runtime implementation and rig verification. Declaration checks cannot establish them.
