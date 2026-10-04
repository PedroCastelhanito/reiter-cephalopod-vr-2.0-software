# Tracking status

Final Windows repair snapshot (2026-10-01, baseline HEAD
`826984255e0a8469afccbda2dcaf8c642b528b33` plus uncommitted repairs): 43 passed,
including the native NVIDIA same-image lease smoke built with
MSVC 19.44/CUDA 12.8.61/API 2 headers. Fresh inventory confirms RTX 5060 Ti ordinal 0.
The 128x128 smoke proves bounded native lease/readback/closure only. Finished
ordering now waits for actual outbound delivery. All 48 contract tests and 19 JSON
schemas pass; explicit UTF-8 fixes platform decoding without changing declarations.
[Evidence](rig-audit-2026-10-01/README.md) retains scope/results;
[scientific/full-load acceptance](rig-verification.md) remains open.

Updated: 2026-10-01. Tracking runtime implementation is selected under
[ARCH-001](../architecture.md#arch-001), before GUI and SpikeGLX integration.
Native adapters and the backend runtime are now implemented. Local checks below are
implementation evidence; bounded native checks pass, while full camera/model and
scientific acceptance remain pending.
The source review below was recorded on 2026-09-26; its source revision was not retained.

The historical review compared CephVR 1.0 source with the then-current 2.0 declarations. No latency,
throughput, hardware compatibility or scientific accuracy was measured. CephVR 1.0
runtime code was left unchanged. The owner accepted the recommended approach and optimizations. Current rules live
in T07/T08/T11 and the execution contract; this report retains the review evidence.

Current scope is owned by [T04](../docs/architecture/tracking.md#t04): water optical
flow or fin/tissue optical flow, one selected per session, sharing the pipeline.
The fin-undulation method contract and policy/settings were removed. Old IDs remain
superseded anchors only. The undeployed family ID is now `fin_flow`; `fin_undulation`
is not an alias and its old method settings are not silently migrated.

GUI integration note (2026-10-03): [E10](../docs/architecture/experiment.md#e10)
and [T14](../docs/architecture/tracking.md#t14) now derive participation from
closed-loop or Record velocities. The local GUI draft and preview gate implement
that derivation; managed configuration/default resolution and runtime adoption remain
pending. The review fixture explicitly selects saving Off; T14's persisted/default
settings are not overwritten. [Frontend evidence](runtime.md#dashboard-frontend-implementation).

## Implementation and local validation

The runtime now lives under `src/cephvr/tracking`, with `cephvr-tracking` as the
managed entry point. It uses the canonical settings/evidence models and existing
control/authentication, command retention, deadlines, resource accounting, camera
conversion and Windows transport mechanisms. The SDK ABI shim is in
`native/tracking`; it is compiled separately on Windows. Setup fails explicitly
when required native libraries, assets, device identity or resources are unavailable.

| Implemented responsibility | Owning rules and evidence |
| --- | --- |
| Source attachment and fixed private frame pool | A03/T08, checked ordered snapshots and immutable reference-counted leases |
| Manual/contour/ONNX pose and completed observation history | T06/T09/T11/T17, invalid/stale observations cannot fall back to older valid pose |
| Reusable geometry raster/lease storage, distance band, arc sections and fin selection | T25–T32/T04, full intended and visible coverage retained |
| NVIDIA CUDA flow adapter | T07/T33/T34, two GPU inputs, upload only the newer frame, native SHORT2 readback and explicit completion |
| Screening, water/fin response and interval-average filtering | T40–T45/T04, original-neighbour screening and exact source-time intervals |
| Direct bounded feedback and exact credits | A06/T08, delivery resets preserve processing state; native writes retain immutable ownership |
| Recording thread and producer cutoff | T19, record-before-feedback, bounded admission, idle-period fsync, explicit failed/unconfirmed closure |
| Setup/BindData/trial control, health and cleanup | E05/E06/E08, retained authenticated commands, independent progress checks and registered resources |

T33 revision 3 declares the owner's selected mapping: **native block estimate at
the represented block centre**, including partial edge blocks. It is not a mean
of independently measured pixel vectors. The convention is in prepared-method
metadata and the scientific Header. Tracking policy is version 42. T08 revision 6
and `contracts/data-preparation.md` bind the one missing protected handoff:
SetupSessionRequest tag 8 carries the exact registered renderer generation for
closed-loop pipe authentication. Existing wire tags are preserved.

Under [ARCH-002](../architecture.md#arch-002), configuration, numerical methods,
processing ownership, recording, feedback and control transport remain separate.
The 2026-10-01 simplification review found three focused opportunities, now implemented:

| Finding | Change and preserved behavior |
| --- | --- |
| Unused bookkeeping and repeated geometry retirement | Removed the unread history retirement flag and delivery generation field; the history lists and TrialGate remain the actual owners. One pose helper releases unborrowed geometry on the pose thread, including failure cleanup (T08/T09). |
| Repeated input discard/reset paths | One private method handles overflow, old frames and camera gaps. It retains discard-before-release, feedback retirement before generation reset, baseline release and latest-frame recovery; pose history and original deadlines are unchanged (T08/T09). |
| Movement execution also formats scientific records | A value-only helper in `recording/results.py` formats the exact Protobuf and stage evidence. Movement retains the publication lock, admission checks, sequencing and record-before-feedback/first-activity ordering (T08/T19). |

`processing/movement.py` is now 308 lines rather than 355; the extracted formatter
is 73 lines. This is a cohesion improvement, not a claim of a net source-size or
performance reduction. No additional package is justified: existing Python,
Protobuf/Pydantic and numerical helpers cover the mechanisms. Native adapters,
scientific algorithms, RPC/schema/configuration and policy remain unchanged.
The boundary checker reports no Tracking violation or size warning. Added regression
cases extend the existing processing and recording test modules; no new test module
or runtime back-reference was introduced.

The 2026-10-01 cross-backend ARCH-002 sweep rechecked Tracking's package ownership and
transport boundaries. Tracking and Visual Stimulus use the same authentication
lookup/check shape and shared `require_authenticated_peer`; broader RPC-boundary
consolidation is not justified because their command/worker admission and deadline
policies differ. No further Tracking refactor was identified in this sweep.

Geometry storage is prepared once with finite lease slots; outline prefix summation
is linear rather than repeatedly summing each prefix. CephVR 1.0's useful asynchronous
pose and persistent GPU input pattern are retained, without its stale-pose fallback,
extra grayscale copy or GPU float-grid expansion. No performance improvement has been
measured on this machine.

Local validation uses real numerical/movement/recording and gRPC runtime code, with
small injected camera/GPU boundaries. It covers Save On/Off, baseline/paired movement,
pre-onset Abort, conflicting/stale commands, retained lifecycle evidence, failed cleanup,
pose history, exact credits, clipping/support, source-depth conversion and writer failure.
A real supervisor service test exercises registration and heartbeat resource catalogues;
it exposed and fixed the required revision-zero empty catalogue before creation.
Existing controller/acquisition/Visual Stimulus communication tests remain regressions;
this is not a combined live camera/GPU/renderer experiment test.

Historical local checks on 2026-09-30: **675 tests passed, 7 platform/rig tests skipped** across
Tracking and the relevant existing backend/shared suites (28 Tracking tests passed,
one rig test skipped). **48** Tracking contract tests passed; **19** Tracking and
**11** Visual Stimulus schemas match. All **57** generated binding files match their
authoritative Protobuf. Ruff and formatting pass; Windows-target mypy passes across
**519** files. The boundary checker covers **450** modules with zero violations and
no Tracking size warning; existing cohesion warnings belong to the other backends
and retain their respective review reports. Source/wheel builds and lightweight
configuration import checks pass. These totals describe the uncommitted working tree,
including other ongoing backend work.

Current audit validation on 2026-10-01: the pre-edit baseline passed **28 Tracking
tests**, the ownership increment **31**, and the final increment **42**, each with
one rig case deselected. New cases cover multiple borrowed observations, pose-thread
release after failure, gaps with/without a frame, expired input, ordered reset evidence,
preserved pose history, cutoff/stale-generation rejection, failed record admission,
first activity and exact scientific payload/stage formatting. The full local `tests/`
suite passed **736 tests**, with **6 skipped and 2 deselected**; the **48 Tracking
contract tests** also passed. Ruff/format and Windows-target mypy (**60 Tracking source
files**) passed, and the boundary checker reports **451 modules, zero violations**.

The suite includes concurrent pre-existing repository work and is not a clean-HEAD
comparison. Initial sandbox-only transport errors were resolved by permitting test
loopback sockets. [Dated evidence](tracking-evidence-2026-10-01/README.md) retains
commands/results, the exact audit source diff and pre/post source hashes against the
initial dirty-tree snapshot. These checks establish local regression evidence only.

That development snapshot had no native DLL build or GPU smoke. The later rig audit
above built the shim and passed bounded native flow execution. CUDA/ONNX inference,
protected Windows assets, named-pipe cancellation, actual camera conversion and
combined closed-loop throughput still have no acceptance evidence.

## Windows execution handoff

Prerequisites: Python 3.11 x64, MSVC x64 build tools, CMake 3.24+, CUDA Toolkit,
NVIDIA Optical Flow **API 2.0 headers**, the compatible NVIDIA driver and the declared
RTX 5060 Ti. The shim deliberately rejects other header ABIs instead of compiling
with an unreviewed layout. Header sources are NVIDIA's
[common API](https://github.com/NVIDIA/NVIDIAOpticalFlowSDK/blob/master/nvOpticalFlowCommon.h)
and [CUDA API](https://github.com/NVIDIA/NVIDIAOpticalFlowSDK/blob/master/nvOpticalFlowCuda.h).
ONNX pose additionally needs the CUDA/cuDNN versions required by the installed
[ONNX Runtime CUDA provider](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html),
an exported manifest/model/weights, and measured subject/search/quality settings.
The camera path uses the acquisition pypylon installation. Missing scientific inputs
remain unset; do not fill them with test fixtures for an experiment.

From an x64 developer PowerShell in the repository:

```powershell
.\tools\test_on_rig.ps1 -Install -BuildTrackingNative -NvofSdkRoot C:\SDKs\OpticalFlowAPI2
.\.venv\Scripts\python.exe -m pytest -q tests/tracking -m 'not rig'
.\.venv\Scripts\python.exe -m pytest -q tests/tracking/test_windows_native.py -m rig
```

The first command builds/installs `cephvr_nvof.dll` and runs automated checks; it does
not launch an experiment. The explicit rig-marked test prepares the real native
provider, uploads a fixed test image, executes a pair, reads native output and checks
lease closure. It is a native smoke test, not a scientific flow-accuracy assertion.
Build wheels on Windows after installing the shim if distributing a compiled adapter.
A source-only wheel cannot make Tracking Ready until that DLL is installed.

Full managed launch additionally requires the next GUI implementation stage: the
launcher currently requires `cephvr.gui.main`. The standalone native smoke test above
does not. Once that prerequisite is met, run the following explicit procedures with
the managed launcher/headless client and retained session files; retain configurations, console logs, controller/
supervisor states and output files with each result:

1. Adopt the actual camera layout and selected processing GPU; test manual, contour and
   model modes. Verify missing/wrong model assets, GPU ordinal, unsupported grid and
   source format fail Setup without Ready. Verify protected assets cannot change while
   prepared; release permits replacement after Cleanup.
2. Test Save Off and Save On, open loop and closed loop. Confirm no tracking file before
   released onset; first completed baseline/invalid evaluation produces Started. Compare
   retained pose/flow lineage and declared block positions against controlled image
   motion, both water and fin modes. Measure scientific direction/scale independently.
3. Slow native processing and feedback consumption separately. Verify exact source/reset
   generations, no stale-pose fallback, held Visual Stimulus feedback, bounded storage
   and responsive control/health. Test wrong consumer generation/nonce, pipe EOF,
   cancellation with pending I/O and native completion after a stop deadline.
4. Abort before onset and during activity; terminate Tracking, controller and supervisor
   separately. Verify finalization keeps the original deadline, reports unreleased native
   ownership truthfully and acquisition retains its ring until matching release/exit.
5. Exercise unwritable/full storage, stalled writes and fsync failure. Keep Header/result/
   reset/discard/Completion records, distinguish closed failure from unknown closure,
   and confirm output failure cannot fabricate a complete scientific record.
6. Run acquisition plus Visual Stimulus and Tracking under the intended rate/resolution,
   models and saving mode. Measure GPU/CPU/native-library memory, latency and sustained
   throughput; verify physical GPU placement and final cleanup before experiment use.

Remaining rig evidence is tracked with E15 in
[rig-verification.md](rig-verification.md). GUI remains the next implementation stage;
SpikeGLX, acquisition firmware and analysis retain their existing deferrals.

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

## Contract review evidence

| Boundary | Finding and current owner |
| --- | --- |
| Acquisition → tracking → Visual Stimulus Setup | Missing metadata/confirmation routes are now declared in the [Setup handoff](../contracts/data-preparation.md). Independent Ready gates no longer need to form a dependency cycle. |
| First tracking activity | [Flow operations](../contracts/tracking/method-bindings.md#baseline-and-pair-operation-contract) and [lifecycle](../contracts/tracking/lifecycle.md) distinguish completed baseline from usable movement and require actual evaluation for Started. |
| Invalid pose or inadequate flow support | [Execution](../contracts/tracking/execution.md) and [proxy](../contracts/tracking/water-flow-proxy.md) already prohibit older-valid fallback, stale controls and filter continuation through invalid intervals; [Visual Stimulus feedback](../contracts/visual_stimulus/feedback.md) owns holding applied movement. |
| Reset supersession and credits | R1A is accepted and bound in [feedback delivery](../contracts/tracking/feedback-delivery.md): monotonic generation markers, skip superseded transport markers, preserve the saved local chain, and credit each exact entry once. |
| Stopping and recording | [Stop ordering](../contracts/tracking/lifecycle.md#producer-cutoff-late-work-and-finalization) now binds local cutoff, commit versus retirement, late pose/result evidence, ring leftovers, truthful Stopped and later file closure. No runtime file reread is authorized. |
| Resource retirement | [Frame-buffer ownership](../contracts/acquisition/frame-buffers.md#cleanup-and-failure) and [E06](../docs/architecture/system-contracts.md#e06) require matched release/native completion; cancellation or pipe EOF alone is insufficient. |

The integration review records declaration closure for the listed Setup, reset/credit
and stop/late-completion findings, not exhaustive runtime validation. Its date,
command transcript and source revision were not recorded. Current contracts are
indexed in the [tracking catalogue](../contracts/tracking/README.md); their existence
does not implement the runtime or prove a scientific estimator.

## Remaining work and limitations

Runtime providers and local behavioral tests are implemented; native Windows/GPU,
full-workload and matched-input scientific acceptance remain outstanding under
[E15](../docs/architecture/system-contracts.md#e15). The simplification audit changes
no scientific-method decision and provides no native timing or accuracy guarantee.
Remaining acceptance work is tracked in
[rig verification](rig-verification.md#tracking-delivery-resets-and-exact-pose-geometry).
