# Tracking status

Current source audit (2026-10-09, `0aebf47`): Luna reviewed physical-unit conversion,
configuration and recording paths; Sol interpreted the findings and Astra reviewed
the synthesis. No additional actionable Tracking defect was established. The owning
configuration/processing/recording selection passes 80 tests, contract discovery 48,
and all 19 generated schemas match. [Audit evidence and limits](review-evidence-2026-10-09/context.json)
retain model reports and current-check provenance; no scientific/native/full-load
acceptance is implied. Tracking camera run43 delivery is acquisition evidence with
velocities disabled, not a Tracking algorithm or feedback acceptance test. Oct9 repair
validation repeats all 48 contract cases and 19 schema matches;
[combined local results](review-evidence-2026-10-09/implementation-context.json)
retain their scope separately from scientific/rig acceptance.

Current measured-reference implementation (2026-10-08, `physical-reference-calibration`)
follows [T19/T20](../docs/architecture/tracking.md#t20),
[T35/T38](../docs/architecture/tracking.md#t38) and
[T08](../docs/architecture/tracking.md#t08). Enabled experiment Tracking and runnable
locomotion diagnostics require complete camera distance endpoints/known mm with
matching source dimensions. Pipeline version 2 divides filtered pixel translation
by acquired-image px/mm and converts filtered radians/s to degrees/s before both
record admission and feedback publication. Header/output schema 3 identifies mm/s,
mm/s and deg/s; pixel-space stage evidence, exact settings (including calibration),
timing, lineage, ordering and original writer/resource ownership are preserved.
Tracking policy/config version is 43. Active Visual Stimulus input units/quantity/body
frame must match, with explicit old declaration/gain edits; disabled consumers do not
validate stale stimulus programs. No old recording or gain is silently converted.

ARCH-002 adds a focused numerical unit adapter without changing estimator math,
filter/quality state, dependencies, processes or deadlines. Extend existing behavior
tests for required scale, diagnostic independence, exact admission/publication
conversion and preserved raw evidence. Session/diagnostic size advisories remain
cohesive preparation/execution owners; only one scale value is added to MovementPorts.
Affected Tracking/GUI/Visual Stimulus/controller tests pass **658 / one skip / three
deselections**; two default/pacing assertions are excluded because another chat's
temporary native dummy setting selects calibration_front. The first broad run retains
their failures and a corrected stale GUI unit-conflict fixture. Post-review checks
pass 57 configuration/recording and four GUI cases. All 48 Tracking contract checks,
19 Tracking and 11 Visual Stimulus schema checks, lint/format (348 files), Win32 mypy
(322 sources) and boundaries (625 modules, zero violations) pass.
[Raw JUnit, commands and source hashes](tracking-evidence-2026-10-08/physical-reference-context.json).
Camera image-plane scale does not establish swimming velocity or depth/distortion
correction. No native/hardware/scientific/full-load acceptance ran; see the
[rig checklist](rig-verification.md). Earlier decoded-schema-2 evidence below retains
its historical source/unit scope.

Decoded-file implementation (2026-10-08, `tracking-decoded-records`) follows accepted
[T15/T19 revision 4](../docs/architecture/tracking.md#t15). Header/output schema 2
stores `feedback_result` as descriptor-owned standard Protobuf JSON and registered
stage `payload` as nested objects. Protobuf int64/uint64 fields remain decimal
strings; optional zero remains distinct from absent. Unknown wire/JSON fields,
unknown enum values, nonfinite values and noncanonical representations are rejected.
Internal payloads remain immutable compact text; the existing writer charges both
expanded object workspace and serialization copies against its byte limit.
Prepared-method/settings header text/digest, transport, units, record ordering,
writer ownership and original deadlines remain. No old recording is rewritten;
unsupported header schemas fail explicitly.

ARCH-002 extracts the small object/descriptor adapter into a focused lightweight
model helper and extends the owning recording tests. There is no dependency,
independent feedback field inventory, new process or whole-runtime reference.
Recording and queue files remain cohesive; unchanged Tracking processing/diagnostic
size advisories retain their existing scope. Final Tracking/controller planning/
metadata integration passes **113 / one rig deselection in 3.65 s**, including real
file output, Protobuf round trips, 64-bit extrema, optional zero, mutable-copy/source
isolation, malformed representations, schema rejection and expanded-workspace
admission. All 48 contract checks and 19 generated-schema drift checks pass.
Ruff/format pass 74 files; Windows-target mypy passes 66 sources; boundaries inspect
620 modules with zero violations. An initial sandboxed runtime suite stalls and is
interrupted; permitted authenticated-loopback runs supersede it. Initial missing
temporary parent/old-format assertions, a fixture's nonexistent PID field, static
annotation errors and contract pytest import discovery are corrected or superseded
by owning unittest discovery, without weakening runtime assertions.
[Dated raw results and source context](tracking-evidence-2026-10-08/decoded-records-context.json)
retain the JUnit scope. No runtime restart, hardware/scientific session, full-load
benchmark or crash-durability acceptance ran. Remaining E15 checks stay in the
[rig checklist](rig-verification.md); video padding remains separate open work.

Latest [2026-10-08 Windows/device checks](rig-wiring-evidence-2026-10-08/README.md)
at `7ba43b1` plus focused repairs pass camera identity and owner-approved BehaviorSquid
PFS import/readback. Two physical Tracking Connect/Show/Disconnect cycles now pass,
with six seconds of visible capture each and confirmed camera/both producer-ring
release. The fault was a one-ring assumption in Ready and cleanup validation;
specific rejected-report evidence now survives the existing health path. Settings
restoration and exact normal shutdown/guard/COM cleanup pass. Acquisition/affected
controller checks pass 363 with one skip; affected static checks pass.
[Current diagnosis and scope](rig-wiring-evidence-2026-10-08/README.md#tracking-connect-and-release-correction).
The real RTX 5060 Ti CUDA/NVOF smoke passes one test (0.43 s); the earlier full Windows
suite has 1463 passes and eight existing GUI failures and predates this repair.
Ordered Tracking diagnostics, native GUI clicks/DPI, scientific and full-load
acceptance remain in the [single rig checklist](rig-verification.md).
The earlier protocol-3/preview retest below retains its original scope.

The owner-requested camera OpenCV windows replace the shared headless dependency
with `opencv-python==4.13.0.92` (WIN32UI), keeping Tracking algorithms and pixel
contracts unchanged. Existing Tracking tests pass **72**, with one rig-marked
workload deselected (2.30 s). This is dependency/implementation compatibility,
not native GPU or real camera diagnostic acceptance.
[Current display evidence](rig-wiring-evidence-2026-10-07/opencv-context.json).

Current Windows check (2026-10-07, `08d146d`): the existing rig-marked native
NVIDIA flow/lease smoke passes (one test, 0.48 s). The owner-selected BehaviorSquid
PFS imports through the actual controller. A direct two-second D11/Line2 receiver
check yields 81 valid native frames with matched ON/OFF and closed camera/serial
owners. Managed capture fails amid camera-worker `COORDINATOR_HEALTH_LOST` faults,
so exact-frame annotation, image-only/flow diagnostics, viewer closure and
simultaneous/full-workload acceptance remain unverified. See
[current acquisition evidence](acquisition.md#current-windows-wiring-checks) and
[dated methods/results](rig-wiring-evidence-2026-10-07/README.md). Bounded receiver
and GPU results establish neither sustained 60 Hz nor scientific accuracy.

Updated: 2026-10-07. Current frontend, configuration and diagnostic scope is owned by
[G01](../docs/architecture/gui.md#g01), [T08](../docs/architecture/tracking.md#t08),
[T01/T20](../docs/architecture/tracking.md#t20) and
[A03/A10](../docs/architecture/acquisition.md#a03). Scientific settings and native/full-load
acceptance retain their existing deferrals; image scale is not physical swimming velocity.

The managed configuration codecs and private crop/downscale implementation passed
Sol review. Acquired-image coordinates, original reference dimensions, actual-axis
transforms, native precision/cost bounds and asset-relative paths are preserved.
Strict E07 experiment validation remains separate from diagnostic-only drafts.
All 48 pure contract checks pass. Final combined runtime/static checks are accepted
in the [wiring assessment](runtime.md#current-scope-and-review).

The diagnostic backend slice is accepted by Sol for development. Empty-mask image-only,
flow-only, pose-only and partial quality paths resolve selected runnable stages without
inventing unrelated scientific settings. Manual capture publishes native frames and
discontinuities to the ordered preview-scoped Tracking ring. Original Begin/Close and
recovery deadlines, exact source/status identity and both release receipts govern
closure; unused attachments before any attempted Begin are cancelled truthfully.
DiagnosticService receives its focused owner. No trial, scientific file or Visual
Stimulus feedback is fabricated for diagnostics.

Luna and Sol independently passed 99 affected acquisition worker/manual-preview,
controller diagnostic and Tracking tests, with one deselected and loopback permitted.
Sol's authenticated gateway probe passed empty-mask Begin through the actual pipeline,
returned frame 17 with 10,000 image bytes and confirmed exact Close without extending
the original deadline; only the Windows ring boundary was adapted. Scoped Ruff/format,
Windows-target mypy and boundary checks pass. [Raw repair output](runtime-wiring-evidence-2026-10-06/luna-tracking-diagnostics-sol-repairs-2026-10-07.log)
and [command/provenance metadata](runtime-wiring-evidence-2026-10-06/baseline-context.json)
retain the evidence. Prior defects and intermediate failures remain in LOG.

Sol and Astra accept the assembled GUI binding and focused transport/codec extraction.
Astra's partial Fin quality finding is repaired and verified through the production
resolver: current wedge edits are honored and Water clears inherited Fin support.
The binding uses the controller's exact registered Tracking endpoint, E08 owner-private
GUI credentials, bounded same-frame image/overlays, coalesced timing and explicit viewer
detachment/reopening. Acquired-frame annotation copies exact source identity/dimensions;
no draft changes automatically or crosses source identity. Pending or unconfirmed Close
keeps Begin/editing locked. Configuration and Setup atomic commits now recheck unclosed
diagnostic ownership so revision changes cannot strand its Close identity.

Local managed wide/narrow visual inspection is complete. Final combined development checks pass. Windows/native throughput and scientific
accuracy remain distinct; current results are in
the [wiring assessment](runtime.md#current-scope-and-review), with all outstanding rig
work in the [single checklist](rig-verification.md). Existing scientific/full-load
deferrals remain unchanged.

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

GUI integration status (2026-10-07): [E10](../docs/architecture/experiment.md#e10)
and [T14](../docs/architecture/tracking.md#t14) now derive participation from
closed-loop or Record velocities. The local draft, preview gate and managed
configuration codec now implement that derivation, verified in the accepted wiring
review. The review fixture explicitly selects saving Off; T14's persisted/default
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
