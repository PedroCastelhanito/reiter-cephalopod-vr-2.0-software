# Camera result, command and deadline wait

Derived from [A02](../../docs/architecture/acquisition.md#a02) and
[E06/E08](../../docs/architecture/system-contracts.md). This is an adapter/worker
contract, not implemented timing or SDK compatibility evidence.

## Single owner and wakeup

Retain Basler OneByOne and GrabLoop_ProvidedByUser. The existing camera lifecycle/data
owner alone starts/stops grabbing, retrieves/releases images and applies camera
settings. Existing control/health handlers admit commands into its synchronized
handoff and signal a process-local manual-reset wake event. They do not call camera
methods to interrupt a blocked retrieval. Signaling this event is synchronization,
not camera access. No extra thread, process, callback producer or image queue.

The adapter wraps the camera's GetGrabResultWaitObject and the local wake event in
pylon's WaitObjects container and uses WaitForAny. Use a signalable SDK/native event
compatible with that binding. Validate the chosen pypylon/Windows binding supports
both events, an unambiguous frame/control outcome and releasing the Python GIL while
waiting so the control thread can run. The pinned Python binding uses
`WaitForAny(timeout)` without an output pointer, then checks the existing manual-reset
control event; control wins if both are signaled. No undocumented SWIG pointer
conversion is required. Missing compatibility fails preparation explicitly; no silent
fallback to 1 ms polling or a different capture topology.

On Windows, the typed `native/acquisition` bridge constructs the SDK WaitObject
from the native HANDLE with duplication enabled. Stock pypylon 26.3.1 rejects a
Python integer for that constructor and omits WaitObjectEx. The bridge imports the
SDK WaitObject type through SWIG's pylon type table; Python neither casts nor
manufactures SDK pointers. The original event remains worker-owned and the SDK
owns its duplicate. Build with `tools/build_pylon_wait.py`; missing/incompatible
native bindings fail preparation. This bounded SDK exception follows SYS-003.

The common adapter interface exposes wait_for_frame_or_control(timeout_ns) plus a
thread-safe wake_control() signal; wait outcomes are frame, control or timeout.
clear_control_wake() is called only by the lifecycle owner under the handoff lock
when no unprocessed command remains. Enqueue and signal under that same lock.
This prevents a command arriving between inspection and event reset from losing
its wakeup. A manual-reset signal stays set until acknowledged; never reset it
blindly after returning from wait. Signals may coalesce; the command queue/state,
not the number of wakeups, determines pending work. Dispose wait resources only
after the owner and all signaling users have stopped accessing them.

## Loop and deadlines

1. Inspect pending commands and host deadlines before waiting or taking another
   frame. Apply stop/interruption first when pending; no frame stream can starve it.
2. Set the relative wait budget from the nearest applicable absolute local boundary,
   frame-health or operation deadline using host_time_ns(). When already due, handle
   the deadline without waiting. While idle/not grabbing, wait on control/deadline
   alone; never wait on an invalid or permanently signaled camera-result object.
3. Block until either event or the timeout. Adapt positive nanoseconds to SDK whole
   milliseconds by ceiling; this adds less than one SDK tick to the requested wait,
   not a 1 ms recurring cap. Recheck the unchanged absolute deadline on return.
   OS/SDK scheduling can add latency; this is not an exact wake-time guarantee.
4. On every wake, inspect commands/deadlines before frame retrieval, regardless of
   which event satisfied WaitForAny. If work remains permitted and a result is ready,
   call RetrieveResult(0, TimeoutHandling_Return). A ready signal is not a reserved
   image; None means return to predicate checking, not a camera failure by itself.
5. Stamp host receipt immediately after a returned result, then enforce the actual
   admission cutoff before copying/publishing. Release each SDK result once, including
   excluded late frames. Process one result, then recheck commands and deadlines.

The adapter's existing retrieve(timeout_ns) accepts zero; this path always uses zero
because waiting is separate. Eliminate the old per-call 1 ms cap. Do not spin on an
empty result, sleep at a nominal camera rate or reset health deadlines on empty wakes.
A repeatable signaled-without-result SDK inconsistency is diagnosed as SDK_STATE
through the existing failure path, not hidden by a busy loop. Received invalid images
retain A04/A07 accounting; callback arrival time never substitutes for host receipt.

At cutoff, apply recording-lifecycle.md's bounded excluded-frame drain on this same
owner/wait path. Sealed trial admission forbids frame-record/pixel publication but does
not immediately disable retrieval of late/buffered results. Include OFF-outcome wakeup,
drain end and original stop/finalization deadlines in the wait predicate. Terminal
purge/stop return counted discard evidence; never flush invisibly or busy-poll for it.

Scheduled T/end and producer-local interruption cutoffs retain E05/E11 meanings;
rounding a wait does not extend an admitted trial. GIL release, event lifetime,
lost-wakeup avoidance and command priority are implementation checks. Actual latency,
CPU use and rig throughput remain E15 verification work.

References: [Basler multiple-event example](https://docs.baslerweb.com/pylonapi/cpp/pylon_advanced_topics#waiting-for-multiple-events)
and [pypylon release notes](https://github.com/basler/pypylon/releases).
