# Visual Stimulus decoder ownership and local delivery

Governing rule: [V11](../../docs/architecture/visual_stimulus.md#v11). This binds PyAV/FFmpeg CPU
decoding on background threads in the existing rendering-worker process. There is
no decoder process, per-frame RPC or coordinator pixel relay. Local API declarations
are in [decoder_types.pyi](decoder_types.pyi); no decoder runtime is implemented.

## Context and scheduling ownership

The rendering worker's media subsystem owns a bounded set of Python-created decoder
threads and assigns each container/codec context to one serialized owner. Open, read,
demux, decode, seek, flush and close for a context execute on that owner; never call
close/seek concurrently from control or rendering threads. Each independently moving
video instance has its own playback/decode cursor, even when asset bytes are shared.
Bound admitted contexts across current and prepared future content, not just threads.

Use a bounded demand mailbox per admitted session. New target updates may replace
older unstarted requests for the same instance; the request always carries prepared
resource generation, playback generation and monotonically increasing request ID.
An updated generation supersedes old pending work and cannot be erased by an older
request. No queue of one task per render update and no per-epoch thread creation.
A context never executes on two workers concurrently. Fairly service runnable
contexts; a full output queue or paused instance is parked rather than blocking
an owner thread that has other runnable work.

Set explicit positive limits for Python decoder threads, admitted contexts and
FFmpeg codec threads, including an aggregate codec-thread limit. Do not retain
FFmpeg/PyAV's auto-all-core thread count independently for each instance. Count
codec buffers, conversion workspace, decoded queues, renderer-held images and GPU
resources separately; frame-count limits alone do not bound memory. Numeric defaults
remain unset until the Visual Stimulus resource binding is completed. Missing/invalid required
limits must block Setup rather than infer available capacity from CPU count alone.
No hardware decoder, GPU sharing adapter or claim of measured throughput is selected.

## Source and frame delivery

Open the [protected source](asset-lifetime.md) through a seekable read adapter accepted
by PyAV. Hashing and decode use the same protected object identity. Give independent
contexts independent cursors; retain protection across Ready and later planned uses.
No OpenCV VideoCapture or pathname reopen fallback, implicit FPS default, in-trial
whole-file revalidation or automatic source transcode. Cap native working storage
through admitted profiles/dimensions, context count and explicit codec settings.

Publish owned decoded frames into bounded in-process queues. A frame descriptor
contains instance/resource/playback generation, source stream/frame identity, source
PTS/time base, half-open presentation interval and complete pixel representation.
The receiving render loop never waits for a target frame or performs disk/decode work.
It consumes prepared frames and applies V09/V10 selection, holds and skip behavior.
Media PTS is a source clock, not host time; retain both source and application lineage
in the later detailed evidence binding. Never renumber selected frames to hide skips.

After publication, neither decoder nor conversion code mutates the published pixels.
Use a lease/reference to the owning frame allocation until the renderer has finished
using it for upload. A NumPy view alone is not evidence of independent pixel lifetime.
If a later upload path reads asynchronously, retain the allocation until its transfer
completion evidence. Recycle only released storage; reserve bytes before allocation
and include simultaneously live source/conversion/destination buffers in admission.
No unbounded temporary conversion or rescue queue when the normal queue is full.

Prepared generation rejects stale results after fresh Setup. Playback generation
separately rejects outdated decode work after loops/resets. A V10 permitted hold
may retain the instance's prior valid image; evidence keeps that image's actual source
and generation rather than relabeling it as the new target. A new/invalid instance
cannot borrow another instance's image. Decode reference frames as required without
presenting every obsolete frame.

## Readiness, health and cancellation

Setup must resolve a valid media timeline/end image and prepare initial content under
V09/V11 before the applicable Ready gate. Required upcoming content uses bounded
prefetch preparation, not blocking decode at epoch transitions. Demand and queue
states distinguish no work, capacity wait, decoding, prepared data and confirmed
failure; EOF counts as normal only at the validated video endpoint. A live decoder
thread is not evidence of progress, and a full queue is not a stalled codec.

Control cancellation fences new demand and signals owners; it does not call PyAV
close beneath an active decode. Owners stop at safe boundaries, discard unpublished
stale work, close codec/container objects, then release their protected streams.
Wake parked workers on cancellation or capacity release. Cleanup uses E06/E08's
existing absolute bounds and reports unfinished ownership truthfully. Python threads
cannot be force-killed safely; a stuck/native-crashed decoder may require containing
the rendering-worker process. No silent decoder replacement or session continuation.

PyAV Python-I/O callbacks and FFmpeg logging callbacks require implementation care:
configure a supported logging/callback path before codec threads start and verify
that it cannot deadlock on the GIL or call GUI/control code. Core native decode calls
release the GIL, but this is not a guarantee of zero render-thread contention or
bounded I/O latency. Aggregate worker health/safety paths retain E08 independence.
Report native decode/read failures through the existing required-backend path; temporary
target lateness alone retains V10 rather than inventing a new abort policy.

## Local declaration boundary

The local API specifies atomic nonblocking demand publication, nonblocking frame
polling, explicit lease release, retained failure status and cancel request. It does
not create a second lifecycle state machine: full worker preparation/Ready/Stopped/
Finished messages remain governed by E05/E08 and need their Visual Stimulus payload binding.
Detailed record schemas, source-index discovery, codec logging adapter, resource
limits and platform runtime remain local work. Static stub parsing is not runtime
or rig validation. Full-workload performance and cancellation verification remain E15.

Implementation reference: [PyAV CodecContext](https://github.com/PyAV-Org/PyAV/blob/main/av/codec/context.py)
documents unsafe concurrent decode and exposes codec thread controls; native calls
release the GIL. Pin and verify the actual build during implementation, not from a
floating documentation URL alone.
