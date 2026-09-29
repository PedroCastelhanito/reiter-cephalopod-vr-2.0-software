# Tracking frame-pipeline review — 2026-09-26

Static review of the CephVR 1.0 source and the current 2.0 declarations. No latency,
throughput, hardware compatibility or scientific accuracy was measured. CephVR 1.0
runtime code was left unchanged. The owner accepted the recommended approach and optimizations. Current rules live
in T07/T08/T11 and the execution contract; this report retains the review evidence.

Current scope is owned by [T04](../docs/architecture/tracking.md#t04): water optical
flow or fin/tissue optical flow, one selected per session, sharing the pipeline.
The fin-undulation method contract and policy/settings were removed. Old IDs remain
superseded anchors only. The undeployed family ID is now `fin_flow`; `fin_undulation`
is not an alias and its old method settings are not silently migrated.

## What one frame does today

Reference files below belong to the sibling CephVR 1.0 repository.

1. The shared-memory reader copies a slot into owned bytes, checks slot metadata
   around the read, and the source constructs a NumPy view over those bytes:
   [reader](../../reiter-cephalopod-vr-software/protocol/src/protocol/shared_memory.py),
   `SharedMemoryFrameSequenceReader.get_next`, and
   [source](../../reiter-cephalopod-vr-software/protocol/src/tracking_backend/runtime/video_source.py),
   `SharedFrameSequenceSource.read`. `np.frombuffer` is a view here, not another
   full-image copy. The existing copy protects against producer overwrite.
2. The source loop handles preview/completions and submits the frame to an ordered
   capture queue. The prepare worker crops/resizes/converts it and creates an owned
   grayscale copy before fanning out to ordered flow and independently droppable pose:
   [engine](../../reiter-cephalopod-vr-software/protocol/src/tracking_backend/pipeline/engine.py),
   `_run_prepare_stage`; [preparation](../../reiter-cephalopod-vr-software/protocol/src/tracking_backend/preprocessing/pipeline.py),
   `prepare_frame_and_gray`. Depending on the configured preprocessing engine, resize
   can upload to GPU and download back before flow uploads again.
3. The pose worker estimates landmarks and geometry and publishes a snapshot. The
   flow worker samples the available snapshot without waiting for same-frame pose.
   This asynchronous separation is already useful and should be preserved. Pose
   exceptions currently leave the prior snapshot in place; 2.0's T09 invalid-observation
   history and age rules are stricter and must not regress to that behavior.
4. [NVIDIA flow](../../reiter-cephalopod-vr-software/protocol/src/tracking_backend/flow/estimation.py),
   `_compute_nvidia_of_dense_flow`, caches its OpenCV NVIDIA object and ping-pongs two
   GPU input buffers. After the baseline, the previous image is already resident;
   only the new image uploads. Keep this optimization. The function converts SHORT2
   output to float on GPU, then downloads the native-grid field to CPU. Optional
   cost is also downloaded.
5. `_flow_vectors_from_dense` then masks and spatially bins the field using CPU
   OpenCV/NumPy; the locomotion estimator receives the reduced measurements.
   Separately, `_advance_flow_state` copies the already-owned grayscale image again.
   The two grayscale copies are visible in this concurrent path; removing either in
   isolation would be unsafe for other callers without fixing ownership first.
6. CPU locomotion runs, results enter a completed queue, and the source loop drains
   them, admits motion records and publishes feedback:
   [runtime manager](../../reiter-cephalopod-vr-software/protocol/src/tracking_backend/runtime/runtime_manager.py),
   `_run_source_loop`, `_consume_completed_result` and
   `_publish_motion_estimate`. Publication is nonblocking, but completion handling
   shares the source loop. `_put_ordered` can wait repeatedly for queue space until
   stop, so bounded queue length alone does not bound result age.

## Adopted implementation direction

The accepted frame path, buffer ownership, cache keys, CPU/GPU transfers, library
bindings and preview/publication separation now have one authoritative home:
[optimized execution binding](../contracts/tracking/execution.md#optimized-frame-path),
with [NVIDIA and ONNX bindings](../contracts/tracking/method-bindings.md).
[T08](../docs/architecture/tracking.md#t08) owns execution placement; T07/T11 own
flow and model handling. The initial CPU estimator receives native SHORT2 samples.
A native grid occupies `4 * ceil(W/g) * ceil(H/g)` bytes before row pitch; float32
vectors would occupy twice that. This byte-count comparison is not a latency claim.
Future GPU estimation remains possible behind the method interface, not a second
initial execution path. No throughput or accuracy result is implied by acceptance.

NVIDIA's [SDK header](https://github.com/NVIDIA/NVIDIAOpticalFlowSDK/blob/master/nvOpticalFlowCommon.h)
defines GRAYSCALE8 and SHORT2; its [CUDA example](https://developer.nvidia.com/blog/an-introduction-to-the-nvidia-optical-flow-sdk/)
shows grayscale input and two-buffer reuse. The current
[programming guide](https://docs.nvidia.com/video-technologies/optical-flow-sdk/nvofa-programming-guide/index.html)
describes explicit CUDA I/O streams and capability checks. Those API facts support the
binding, not a performance claim for this rig.

ORT's [I/O binding documentation](https://onnxruntime.ai/docs/performance/tune-performance/iobinding.html)
explains implicit CPU/device copies and reusable output bindings. Its
[CUDA provider options](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)
require deliberate stream and synchronization configuration. GPU-resident end-to-end
processing remains a later optimization candidate, not an initial dependency.

## Remaining local work and rig checks

The common pool/lease and CPU-flow interfaces are declared. Current work is to review
these contracts under [GOV-001](../architecture.md#gov-001). Runtime providers remain
future implementation work; shared estimator ports/settings/evidence and composition are
bound in the [pipeline catalogue](../contracts/tracking/pipeline-catalogue.md). The
[contour extraction contract](../contracts/tracking/contour-landmarks.md) is now bound.
[Fin sampling and explicit proxy reuse](../contracts/tracking/fin-flow.md) are now bound. Scope acceptance is not a runnable
fin estimator. The shared architecture does not require a new scientific method round
before these ordinary implementation contracts can progress.

On the rig, compare camera receipt → feedback publication and receipt → actual display,
including upper-tail latency, queue age, reset/drop counts, pose age, valid-result rate,
CPU/GPU/transfer time and memory. Test both tracking options together with four-view VR
and recording. Compare scientific behavior using matched recorded inputs and live rig
trials, retaining source identity and parameter differences. Faster isolated flow is not
proof that the whole experiment performs better. These remain E15 rig verification;
no simulated-backend milestone is added.
