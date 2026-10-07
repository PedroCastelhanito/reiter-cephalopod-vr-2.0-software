# Tracking method configuration and native bindings

Authority: [T01/T06/T07/T11/T17/T18](../../docs/architecture/tracking.md#t01).
Canonical pure types: [method_models.py](method_models.py); generated schemas have the
same basenames as SCHEMAS there. [methods.proto](../cephvr/tracking/v1/methods.proto)
transports them as registered StageConfiguration documents under [T27](stages.md). No SDK/runtime implementation is claimed.

## Common image interpretation

Read source pixels only through the existing A01/A03 shared conversion/copy contract.
Release acquisition slots before computation; all subsequent CPU/GPU consumers hold
bounded private-buffer leases. Interpret MSB alignment and effective source range from
[the common pixel contract](../acquisition/pixel-processing.md), not observed min/max.
A01 supplies grayscale or RGB with original precision; keep this prepared image distinct
from each algorithm's declared tensor/byte feature representation. Do not widen an
8-bit-reduced image and call it native-depth. No preview dependency or camera SDK owner.

Optional T01 preprocessing first crops the configured acquired-pixel rectangle, then
uses OpenCV `INTER_AREA` into a preallocated private array with unchanged dtype.
Output dimensions are `max(1, (crop_dimension * scale_percent + 50) // 100)` for the
integer 10–100 percent selection. Retain the actual independent x/y scales after
rounding; pixel centres invert as `source = crop_origin + (processed + 0.5) / scale - 0.5`.
Normalize pose, flow positions and vectors back to acquired-image coordinates before
source-coordinate geometry and locomotion estimation. Source annotations retain their
original dimensions and source lineage. Crop/scale changes invalidate temporal
baselines; native/shared/recorded camera pixels remain unchanged. This transform does
not apply image-plane millimetres to T35/T38 output units.

## Threshold/contour adapter

T18 threshold/polarity operate on full-precision grayscale within T16's search rectangle.
Use 8-connected foreground components (OpenCV connectedComponentsWithStats, CV_32S labels),
external boundaries from findContours RETR_EXTERNAL/CHAIN_APPROX_SIMPLE on each accepted
component. No morphological closing, background subtraction or temporal learning is
silently introduced. Component area counts foreground pixels (not bounding-box/convex-hull
area). Discard components outside explicit inclusive minimum_area_px2/maximum_area_px2,
and components touching the search boundary, whose silhouette is clipped.

For each remaining component obtain T10's triplet through the shared ContourGeometry
boundary in [runtime_types.pyi](runtime_types.pyi). Reject nonfinite/out-of-frame,
collinear or below-limit geometry before T17 ranking. Axis length is the distance from
tip to base midpoint; base width is left-to-right-base distance; triangle area is half
the absolute 2D cross product. Limits are inclusive, positive and in px/px²; they are
quality gates, not a locomotion fit or physical calibration. Score eligible
contour candidates by their foreground pixel area: largest eligible component wins;
T17's coordinate tie rule still applies. This is an area ranking, not a model confidence.
No surviving candidate yields an invalid observation; native method errors follow E06.

T06's [contour landmark binding](contour-landmarks.md) specifies mask-moment orientation,
reference direction resolution, directional extremes and rejection/tie rules. Use
ContourSettings v2 and threshold_contour implementation 2. The earlier incomplete v1
schema cannot become Ready by inventing an axis-quality setting. No anatomical search
regions, ellipse fitting or previous-frame landmark prediction are introduced.

## ONNX adapter: one exported tensor contract

For the initial keypoint implementation, `ModelSettings.manifest` resolves under E07's asset root to ModelManifest JSON. All paths
are portable relative paths; resolve model/weight paths relative to the manifest directory,
reject traversal/symlink escape, duplicates and undeclared ONNX external-data references.
Read/hash bounded assets once at Setup; retain loaded bytes/native session for the session.
Do not re-open/hash/re-export models per trial. Record content IDs in the tracking file
header when saving; E04 central metadata retains only permitted filenames/setup settings,
not a package inventory or automatic model copy.

Export outside CephVR to `onnx_triplet_v1`: one float32 NCHW input [1,C,H,W], C=1 gray or
C=3 RGB, fixed manifest dimensions; one float32 output [1,K,10], 0<=K<=maximum_candidates.
The three landmarks carry T21 anatomical meanings from [pose.md](pose.md#common-landmark-coordinates).
Rows are [candidate_score, tip_x,tip_y,tip_score, left_x,left_y,left_score,
right_x,right_y,right_score]. Coordinates are tensor pixel centres, scores finite in [0,1].
The export wrapper handles model-specific decoding and duplicate suppression; CephVR has
no YOLO-version heuristics, arbitrary output maps, plugin imports or direct PyTorch runner.
A zero candidate_score is reserved for an unused row and is always excluded before
application thresholds. Dynamic K=0 represents no detections. Nonempty rows require
a positive candidate score; a zero configured threshold never admits padding.

Preprocessing is aspect-preserving letterbox: r=min(W/crop_width,H/crop_height), rounded
resized dimensions floor(original*r+0.5), each at least 1 and at most the target dimension.
Use bilinear centre-aligned resizing, with left/top padding floor(remaining/2) and right/
bottom receiving the extra pixel. Normalize interpreted source code to [0,1] using the
prepared declared source maximum, then channelwise (fraction-mean)/std. Pad with explicit
manifest fractions before normalization. Preserve fractional grayscale/demosaic values;
no per-frame contrast normalization. Apply clamp-to-edge at crop bounds for interpolation.
RGB source order and normalization arrays must match
the export's training preparation. Export compatibility is verified before Ready.

Invert using the actual rounded x/y resize scales, centre convention
source_x=(tensor_x-pad_left+0.5)/scale_x-0.5+crop_x, likewise y. Reject padding/out-of-search
landmarks rather than clamping. Require every keypoint score and candidate score to pass
its inclusive configured threshold, then the shared LandmarkQuality limits; T17 chooses
the highest row score. A malformed tensor/shape is a method contract failure, not an
ordinary no-animal detection. No model/shape/threshold numeric defaults are guessed.

Load ONNX Runtime with explicit CUDA provider on ModelSettings.device_ordinal; verify
the same adopted physical NVIDIA device for pose, flow and rendering under SYS-002. Require CUDA
actually active, disable run-time provider retry/fallback and retain resolved provider
placement. CPU shape/control operators selected by the prepared graph are allowed;
CPU-only inference or a compute graph silently moved to CPU is not. The supported exported
graph's tensor compute must have CUDA kernels. Validate the retained placement against
the prepared optimized graph: CPU nodes may only derive/manipulate shape/index metadata
and their dependencies; any CPU operation on image activations/model weights fails Setup.
This must be checked for the supported export, not inferred from the provider list.
Do not dynamically alter provider placement after Start. Use a single prepared session,
one pose job in flight, reusable tensors, and GPU completion before releasing input/output.
Share no mutable native context across movement and pose threads.
Prepare letterbox/normalization on CPU into reusable pose-worker buffers; transfer only
admitted jobs. Keep the bounded [1,K,10] candidate output on CPU for the declared selection
and coordinate mapping. Reuse device/host tensor allocations where the prepared shape
permits; ONNX I/O binding is appropriate for explicitly reusable device buffers, not a
reason to add a second GPU preprocessing runtime. Dynamic K is bounded by the manifest;
account its maximum allocation at Setup. Required completion/synchronization still precedes
reuse; no automatic switch of execution provider or cross-worker mutable tensor sharing.


## NVIDIA OF CUDA adapter

Use the SDK CUDA interface from the installed NVIDIA driver (`NvOFAPICreateInstanceCuda`,
`NvCreateOpticalFlowCuda`), with serialized ownership by the movement worker. A small native
ABI shim is permitted under SYS-003 for SDK structures/context ownership; it is not another
backend/process/provider. Query API/device capabilities and buffer formats before NvOFInit;
validate requested grid 1/2/4, preset, maximum dimensions and allocation budgets on that
actual device. No guessing supported grid or silently substituting a preset/provider.

SDK input is 8-bit. FlowSettings must explicitly declare
`declared_full_range_gray8_v1`: from original-depth grayscale fraction f in [0,1], generate
q=floor(255*f+0.5). This is algorithm-specific quantization, not a change to native capture,
recording, shared buffers or the precision-preserving common preparation. No automatic
histogram mapping. Use NV_OF_BUFFER_FORMAT_GRAYSCALE8 directly, with one byte per
pixel and the actual SDK row pitch. Do not expand identical grayscale codes into
ABGR channels. Validate format initialization/allocation on the installed SDK/driver
and device before Ready; fail explicitly if unsupported, without format fallback.
No resizing/downsampling of the input is implied. NVIDIA’s
[SDK header](https://github.com/NVIDIA/NVIDIAOpticalFlowSDK/blob/master/nvOpticalFlowCommon.h)
and [CUDA example](https://developer.nvidia.com/blog/an-introduction-to-the-nvidia-optical-flow-sdk/)
define/show this native grayscale input; this does not prove rig throughput.

Compute forward displacement from earlier to later source frame, native SHORT2 S10.5
(two signed int16 components, divide by 32 for input-pixel displacement). Grid dimensions
are ceil(width/grid_step), ceil(height/grid_step). Keep SDK pitch/cell footprint explicit;
partial edge cells are clipped to input bounds. Retain grid output; do not upsample merely
for storage or silently label grid cells as independent per-pixel measurements. GPU output
stays leased until the readback consuming it completes. Optional SDK UINT8 cost is a method
quality diagnostic (higher is worse), not a probability. The optional raw-cost gate is
bound in [flow-quality.md](flow-quality.md); no adaptive cost normalization is used.

Allocate two persistent input buffers and prepared output/readback storage.
The [baseline operation](#baseline-and-pair-operation-contract) uploads its image without
computing a displacement. On each subsequent valid pair,
verify the retained GPU input belongs to the supplied earlier frame and current generation;
upload the later frame once and swap input roles after completion. A mismatched cached
identity cannot substitute for the supplied frame. Reset invalidates retained identity
and hints before establishing a new baseline; old native work keeps its buffers until done.

The initial adapter returns FlowLease(memory_domain="host", storage_format="int16x2",
component_scale=1/32) for a native-grid SHORT2 readback, with original pitch/lineage.
Copy native grid rows once into bounded reusable host storage; optionally copy UINT8 cost
once when enabled. Preserve signed components and SDK byte order explicitly. Do not run
GPU float conversion, upsampling or spatial reduction before readback. CPU code decodes
scale using vectorized operations into reusable scratch or chunks, preserving raw samples.
Source interval division remains estimator-owned and is not part of the native displacement.

compute_pair enqueues flow and readback; wait_complete covers both, within the existing
movement deadline. The [operation and host-buffer contracts](#baseline-and-pair-operation-contract)
below bind completion, native availability and legal reuse. The GPU output can be reused
after readback completion, but host storage remains leased through CPU estimation. Initial
ordered execution needs no second GPU estimator or runtime-selected alternate placement.

Pair frames only within the same trial/source/processing generation, with positive source
interval and no discarded camera gap. First frame after a processing reset is baseline
only. Delivery-only overflow changes no native identities, baseline or hints. Temporal
hints follow the explicit setting, disabled after processing reset/gap; external
hints/global-flow/ROI/bidirectional modes are not introduced. Reset gates old work and
clears native history without freeing in-flight buffers. Close waits for native completion,
frees buffers, destroys the OF handle and then retires the owning CUDA resources. Native
close timeout/failure follows T08/E06 rather than declaring a daemon-thread exit successful.
No dense flow or cost fields are saved under T15.

The [pipeline catalogue](pipeline-catalogue.md) binds the selected geometry, proxy and
motion channels under T12/T04. The adapter returns pixel displacement and timestamps,
never physical animal velocity inferred by the adapter.

Primary references: [NVIDIA OF SDK](https://docs.nvidia.com/video-technologies/optical-flow-sdk/nvofa-programming-guide/index.html),
[CUDA EP](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html),
[OpenCV component/contour APIs](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html).


## Baseline and pair operation contract

These direct calls belong to the existing movement worker and FlowMethod declaration;
there is no new stage, queue or control RPC. Preparation binds the source allocation,
layout/transform and method session once. Each call additionally checks the exact trial
WorkContext, processing generation and source identity. Internal reset_generation/
generation fields denote calculation identity, not the current FeedbackResult generation. A retained frame from another binding
cannot satisfy a request merely because its frame number matches.

| Operation | Preconditions and result |
| --- | --- |
| establish_baseline(frame, deadline_host_ns) | After preparation/reset, upload the admitted frame into the retained input slot. Return true only after that upload has completed; create no flow lease or displacement. Repeating the same completed baseline is idempotent. Replacing it requires the existing reset path. |
| compute_pair(earlier, later) | Require the retained input to match earlier exactly, an ordered contiguous pair and positive source interval. Enqueue only the later upload, forward flow and host readback. Return the identified FlowLease; its bytes are not yet readable. |
| wait_complete(lease, deadline_host_ns) | Return true only after this lease's native computation and required readbacks finish, then retain its later input for the next pair. False means completion was not established by the deadline; it does not mean an ordinary invalid observation or permission to free storage. |
| host_view(lease) | After successful completion, expose only matching borrowed read-only buffers under the layout checks below. |
| release(lease) | Exactly once after all CPU consumers finish. Retire the host views; this does not discard the retained GPU input needed for the next pair. |
| reset(generation) / close(deadline_host_ns) | Follow execution/lifecycle gating and native ownership. Clear retained identities/hints at reset, and confirm all native work and releases before successful close. |

One baseline upload or pair can be outstanding on the initial ordered adapter. Reconcile
its native completion and host consumers before another baseline/pair operation. Timeout,
malformed input, mismatched lease or native failure follows E06. Neither timeout nor a
cancellation request makes the buffers reusable. The control path can gate publication
while the native owner is busy; it must not destroy that owner's context concurrently.
First-pair hint suppression after a processing reset remains the existing NVIDIA rule above.

## Completed host-buffer contract

FlowLease declares WorkContext, processing generation, exact earlier/later SourceFrames,
mapping_id, grid dimensions, storage format, byte_order, component_scale, row pitch and
native buffer identities. Its mapping_id must match the adapter's prepared mapping for
the bound source layout/transform. HostFlowView carries the matching lease_id and retains
no independent ownership. All byte views are contiguous read-only memory spans; typed
array views may have row padding. No host-native byte-order assumption is permitted.

Before constructing any typed view, check positive dimensions, supported storage and
finite positive component scale. For displacement, row_bytes = grid_width * 2 *
component_bytes; for UINT8 cost or validity, row_bytes = grid_width. Require pitch >=
row_bytes and available_bytes >= (grid_height - 1) * pitch + row_bytes, with checked
integer arithmetic within prepared allocation bounds. Row padding is not measured data.
Cost identity, schema, pitch and bytes are either all present or all absent; a configured
cost gate requires their presence. The initial NVIDIA cost schema is
tracking.nvof-cost-u8.v1: one raw UINT8 per native cell, higher values worse, without
normalization. Optional-buffer consistency is checked before estimator access.

Native validity is separate from cost and T41 screening. If the adapter reports per-cell
unavailability, validity_buffer_id, validity_row_pitch_bytes and validity_bytes must all
be present and describe one UINT8 0/1 per grid cell (0 unavailable, 1 available). If all
are absent, the adapter declares every cell in this successfully completed grid available;
it cannot conceal known unavailable cells. Do not fabricate a mask from flow magnitude,
zero components, cost thresholds or missing readback. A failed native call/readback is an
E06 failure, not a grid of ordinary unavailable measurements. Nonfinite numeric values
remain separately classified by T41. This transient port supports native evidence only;
it adds no selectable flow method, dense recording or new scientific quality rule.

Decode signed components and component_scale into bounded estimator scratch only after
completion. Division by source time stays estimator-owned. Cost/validity can be read as
strided views; padding alone does not require another readback or contiguous CPU copy.
Lease release invalidates all views, including optional buffers. Reset or cutoff cannot
release or overwrite any storage still used by a native or CPU consumer.
