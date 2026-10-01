# Tracking execution and method boundary

Authority: [T07–T09](../../docs/architecture/tracking.md#t07), with shared control/cleanup
under [E08/E06](../../docs/architecture/system-contracts.md#e08), input under A03/A04 and
result delivery under A06. This is an implementation contract, not a running backend.

## One process and bounded internal work

The single tracking process implements the existing shared backend lifecycle service
on its configured loopback port. Supervisor launch,
process identity, host clock, health, containment and native resource helpers are shared;
threads are internal implementation owners, not separately registered backend processes.
The process owns the selected camera-ring attachment and A06 direct result connection.
No camera is reopened and no image or scientific result is relayed through the controller.

Keep control/health handling independent of native computation and storage. One ordered
movement worker consumes admitted camera frames, preserving the exact frame-pair lineage
and reset generation. Share prepared read-only input storage only while every consumer
holds its lease; otherwise copy into a bounded private pose buffer before releasing it.
Acquisition frame-ring, frame-age and overload semantics remain A03/A04's rules.

In automatic mode the existing pose worker owns its estimator, geometry method and native resources, with
at most one computation in flight and one waiting image. Newer images replace only the
waiting image; they cannot overwrite in-flight storage. Skipping a superseded pose job
is independent of movement-frame delivery. The method must explicitly support its image
sampling/reset semantics; do not silently advance temporal model state across gaps.
Manual mode creates no pose worker, loads no automatic method and uses prepared geometry.

Each native context stays on its owning thread. Native/GPU completion, rather than a
Python task's return or cancellation request alone, determines when buffers are reusable.
At processing reset/cutoff gate movement publication, retire incompatible work and complete
or reconcile in-flight consumers under E06. Late completion cannot publish into a new
trial/processing generation for movement. Same-binding pose completions follow the
separate T09 eligibility rules below. Delivery-only overflow preserves native calculation state
and eligible pose work/history under feedback-delivery.md. Do not release GPU memory under a running call or declare success merely
because a daemon thread can exit. Thread failure/progress failure is a backend failure;
responsive health handling alone is not useful tracking progress. No automatic estimator
restart, process split or fallback is implied by blocked cleanup.

## Optimized frame path

This is T08's accepted initial execution binding for both T04 options. CPU preparation,
geometry, estimation and filtering use NumPy/OpenCV alongside the shared A01 conversion
provider. NVIDIA OF and automatic ONNX model inference retain their GPU providers.
There is one movement worker, no separate preparation/geometry/estimator queue and no
CPU/GPU placement selector. Resolve stage methods and typed settings once at Setup.
No model loading, provider discovery or JSON parsing belongs in the frame loop.

1. Check A04 source generation/order/age before admission. Copy native bytes from the
   acquired slot into private bounded storage and release the slot before conversion
   or native computation. Use the common converter after release. This is one native
   snapshot; transformations can require additional private destinations, not additional
   acquisition reads. A04 retains its reset-to-latest behavior on age/overflow/gaps.
2. Prepare only the shared source-depth representation and required flow features.
   Keep mono single-channel. Reuse an already compatible representation as a read-only
   view; allocate from prepared reusable storage when dtype/layout/conversion demands
   it. The 8-bit flow feature cannot become the higher-precision pose input. RGB is
   materialized only for consumers whose prepared contract requires it.
3. Offer the immutable source-depth frame to T09's latest-pending pose mailbox.
   Replacement releases only the waiting lease; the in-flight lease remains held.
   The pose worker prepares its model crop/tensor or contour input independently.
   After candidate selection it builds exact geometry for that observation and posts
   one immutable PoseGeometryObservation. Invalid observations remain in history with
   no usable geometry; never retain an older valid pair in their place. Completion time
   covers geometry construction as well as pose inference. Movement selects an eligible
   completed pair without waiting for the offered frame.
4. The movement worker establishes the first admitted frame through the explicit
   [baseline operation](method-bindings.md#baseline-and-pair-operation-contract), then
   submits exact ordered pairs to the prepared NVIDIA adapter. Retain the current GPU
   input for the next pair; only the newly admitted image is uploaded after baseline.
   Wait for that pair's native computation/readback completion,
   not a process-wide GPU fence. Host lease consumption follows the method binding.
5. Snapshot the eligible pose/geometry pair and check its current age/validity. Borrow
   its exact geometry, obtain estimator-owned section/flow association, and run the
   selected estimator over all required
   native-grid measurements. CPU vectorized/chunked operations may use reusable
   scratch arrays; no Python object per vector or pre-estimator bin averaging.
   Native displacement scaling and source-dt conversion retain their separate units.
6. Finish the compact result with exact source/pose/reset lineage. When saving, admit
   its required evidence under the recording contract before exposing a dependent
   result; admission failure follows E06, without silently proceeding as recorded.
   Publish through A06 directly from the movement path, independent of the camera
   polling/UI loop and disk synchronization. The existing result queue/reset owner
   handles overflow; no extra completed-image queue or controller relay is added.
7. Release scratch, flow and frame leases only after their last consumer completes.
   Baseline-only, invalid and reset evaluations retain existing reporting/record rules.
   Recheck processing identity and cutoff before construction/publication, and stamp
   the current reset_generation under feedback-delivery.md. Never republish or retag
   a retired result; delivery-only overflow need not discard an unfinished valid computation. No optimization changes source intervals or Visual Stimulus hold.

### Buffer ownership and bounds

Setup derives finite storage from prepared source/layouts, maximum model tensor shapes,
flow grid/pitch and existing work bounds, within FileLimits.max_native_bytes. Include
native snapshots, transformed images, CPU scratch, CPU flow/cost readback, GPU inputs/
outputs, retained geometry and in-flight work. Prepare reusable destinations at Setup;
no dynamic pool growth, unbounded cache or steady-state full-image allocation fallback.
NumPy strided views/ufunc destinations and supported OpenCV `dst` arguments avoid
unnecessary temporaries; the shared SDK converter remains the native-format authority.

The movement owner tracks references for current/previous frames and automatic-pose
waiting/in-flight frames. These roles may alias the same immutable storage; budget for
simultaneously distinct frames. No consumer writes through a shared read-only view.
The movement owner serializes retain/release; pose completion returns its lease to
that owner. Native completion, not Python reference destruction, authorizes GPU reuse.
`TrackingInputs.retain_private` and `release_private` bind this boundary. Keep the
previous CPU lease while required by `compute_pair`; do not make another defensive
copy of already owned pixels. One lease per holder is released exactly once.

Exhaustion is not authority to overwrite, grow memory or silently skip ordered work.
Apply A04's declared input-overload/reset boundary, retire waiting old work and retain
in-flight leases until completion. Reset/cutoff cannot reclaim running native storage.
A permanently held resource/unfinished computation follows existing progress deadlines
and E06. Control/health handling remains responsive; there is no unbounded queue wait.

Optional preview first obtains its own bounded destination; otherwise omit that preview.
Copy a sampled image into that destination, then let preview render overlays/encode on
its own work path. Do not retain movement/pose/flow leases while waiting for the UI.
Preview drops cannot drop movement evidence. No full-image debug work is required when
no preview is admitted. Scientific recording receives compact immutable payloads only;
writer failure/overload retains its existing required-evidence failure semantics.

### Geometry cache

The pose worker constructs one exact immutable geometry object for each valid automatic
observation before publishing the pair. Manual geometry is constructed during Setup.
Movement never calls GeometryMethod.compute for an automatic observation and never waits
for a newer pose. Estimator-owned sectioning/flow-cell association may cache by the exact
selected geometry identity, prepared mapping and section/region settings; data-dependent
screening, coverage and controls are evaluated for every pair. No tolerance-based reuse
across distinct observations, approximate dimensions or second geometry queue.

Bound pose/geometry history by the existing pose-history count AND prepared native-byte
budget, including one build in flight and retiring consumer leases. Preallocate/reuse
storage for the maximum prepared geometry sizes; reject a preparation that cannot fit.
Evict oldest unreferenced history under T09, never overwrite borrowed masks or allocate
an overflow pool. GeometryMethod owns its storage on the pose thread; the host returns
last-consumer releases through the existing ownership handoff, with no extra worker.
Keep at most one active estimator association plus retiring in-flight references.

Cache keys use the exact observation/manual ID, preparation/trial/source binding,
layout/coordinate transform and resolved method/settings identity. Delivery or movement
processing resets alone do not change a still-eligible pose's geometry identity. Trial/
source/preparation changes retire incompatible observations and associations. Every use
rechecks age/invalidity even on a cache hit; never select past a newer invalid observation.
Manual arrays may be reused across trial contexts when unchanged, but no trial inherits
movement/filter state. Water and fin association/settings cannot substitute for each other.

## Pose selection and evidence

Pose observations carry their source frame identity/order/host receipt, completion time,
trial/source/preparation, original processing generation, valid/invalid disposition
and the paired geometry reference. Keep a
bounded history including invalid observations; a single latest-valid cache would hide
invalidity or lose the eligible predecessor when pose runs ahead of movement. The configured
history count bounds retained observations; retire oldest entries when full without making
movement wait. A referenced observation remains immutable for its in-flight consumer;
include these leases in preparation's finite storage accounting.

For each movement evaluation, snapshot completed observations and choose the greatest
source-frame order no later than the newest contributing movement frame, within the same
trial/source/preparation. Processing-generation equality is not a pose eligibility
requirement; preserve original provenance. Never use a future-frame observation. Do not skip a newer
eligible invalid observation to reuse an older valid one. If bounded history no longer
contains an eligible observation, report missing pose rather than fabricating alignment.

Read shared host time at selection and compute `pose_age_ns = check_host_ns -
pose_source_host_receipt_ns`. Accept equality with the configured maximum. This bound
includes processing delay; it is separate from A04 input age and V26 Visual Stimulus-result age.
Negative/missing timing evidence is a contract failure, not an ordinary fresh/invalid
estimate. No eligible pose, invalid pose or excess age makes pose-dependent movement
invalid. Retain reason, pose identity/source, check time, age/limit and movement-frame
lineage with the result; a missing pose has absent identity/age, never invented zeros.
Manual results reference the prepared manual geometry and declare manual origin; they
do not fabricate per-frame pose inference or apply an automatic-pose age limit.

Clear history and gate incompatible in-flight observations at trial/source/preparation
boundaries. Delivery and movement resets retain eligible history and pose jobs; a
late same-binding pose completion remains subject to cutoff/age/order checks. A returning valid
pose does not authorize a movement interval spanning invalid/discarded data; rebuild any
required baseline under A06/V25/V26. Missing pose is not permission to drop unaccounted
result records or apply remembered velocity. Independent pose-use and record schemas are bound in [records.md](records.md);
estimator-specific geometry/quality remains with T12/T04.

## Estimator input boundary

[T33/T34](estimator-input.md) retain all available in-band provider-grid flow samples,
positions/section association and separate T09 pose evidence. Use the same movement
worker and native leases; geometry/sectioning introduces no early reduction or implicit
motion compensation. Estimator-specific use is bound by the
[pipeline catalogue](pipeline-catalogue.md) under T12/T04.

## Flow-method extension boundary

Keep the small internal method interface in [runtime_types.pyi](runtime_types.pyi),
including preparation, explicit baseline establishment, pair computation/completion,
lease access/release, reset and close. The [operation contract](method-bindings.md#baseline-and-pair-operation-contract)
binds their ordering and outcomes. Preparation receives typed method settings and the validated input
layout and checks actual capabilities. Pair computation takes explicitly identified
frames and returns flow with declared coordinates/units, validity and source lineage.
Processing reset invalidates flow/filter temporal state; delivery reset invokes no method
reset. Pose/geometry resets follow their trial/source/preparation binding. Close confirms native work/consumers have
finished before releasing resources. GPU completion/ownership must be explicit where
computation is asynchronous. Model/flow adapter threads never own session authority.

Implement only NVIDIA Optical Flow now. Resolve its concrete adapter through T27's explicit typed registry before processing; no dynamic discovery, third-party plugin system, DIS/PIV stubs, dependency
imports or speculative alternate execution paths. A future justified method implements
this same boundary and adds its typed settings/capability checks and explicit supported
selection. E14 policy/version and retained implementation identity change with it; the
pipeline's camera, lifecycle, pose scheduling and result ownership need not be rewritten.
The [native method binding](method-bindings.md), [typed internal interfaces](runtime_types.pyi)
and [lifecycle binding](lifecycle.md) complete this declaration. NVIDIA OF runtime
integration and rig behavior remain unimplemented/unverified.

[Stage registration](stages.md) applies the same replaceable boundary to pose, geometry,
estimators and filtering. It does not change worker scheduling or source ownership.
