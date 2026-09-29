# Rig verification — outstanding checks

Latest development handoff:
[hardware evidence and implementation constraints](rig-handoff-2026-09-29/README.md).
Camera roles/rates are now owner-confirmed (behavioral 40065509 at 30 Hz; tracking
40747103 at 60 Hz). Final ROI/depth, surface mapping and SpikeGLX address remain
explicitly deferred. The 2080 Ti format checks and current camera rate limits in
that handoff do not close the full-workload checks below.

Status: rig access established on 2026-09-29. Start with the later
[rig handoff](rig-handoff-2026-09-29/README.md) and
[evidence review](rig-evidence-review-2026-09-29.md); the
[initial audit and repair follow-up](rig-audit-2026-09-29.md) retain earlier snapshots.
Owner camera assignments/rates and repaired RTX 2080 Ti availability are established.
Small concurrent encodes and selected three-frame full-resolution encodes passed;
known codec/size failures are recorded. Four outputs are detected on the RTX 5060 Ti
at 60 Hz; physical surface mapping and optical/presentation verification remain open. The
full-workload, optical, electrical and CephVR2.0 lifecycle checks below remain open;
no CephVR2.0 backend runtime is implemented or validated.
Continue rig-independent decisions under [GOV-001](../architecture.md#gov-001).

This is a verification worklist, not another decision log. Governing rules are
[A08](../docs/architecture/acquisition.md#a08) and
[E15](../docs/architecture/system-contracts.md#e15). These checks are explicitly
tracked separately from installation discovery and dependency smoke checks.

| Check | Evidence required |
| --- | --- |
| Final camera operating points | Under A10, choose the owner-deferred ROI/source/recording precision, then re-read payload, chunks, transport limits and applicable resulting-rate nodes. Resolve behavioral 30 Hz's saved 368,640,000 B/s payload demand versus 360,000,000 B/s limit explicitly; no guessed higher limit or lower cadence. Verify simultaneous externally triggered 30/60 Hz capture with native counters and saved pulse evidence. Different USB host controllers and tracking's 71.803 Hz estimate do not prove sustained rates. |
| Production encoder/tool combination | Under A08/E13/SYS-003, resolve a deliberate compatible FFmpeg/ffprobe pair on the fresh environment PATH. The tested FFmpeg 7.1 / ffprobe 4.3.2 combination is not that deployment baseline. Verify final camera post-filter and VR composite dimensions/depth on the RTX 2080 Ti; retain the handoff's H.264 width/10-bit and AV1 failures. Run both cameras plus composite with rendering/tracking, measuring drops, transfer cost, queue occupancy and finalization. Three static frames and small concurrent sessions do not close this check. |
| Pulse inventory and wiring | Under E12/SYS-004, fill `[pulse_inventory]` from the actual OneBox wiring and verify each camera trigger and the photodiode appears on its mapped saved channel/bit, including edge polarity and a reassigned-role Setup. The Setup check proves configuration only. |
| VR multi-output lifecycle/pacing | Under V15/V20/E05, measure both configured presentation modes with all outputs and full tracking/recording load. Verify per-output Started evidence within the existing 250 ms allowance, Idle transitions and late/in-flight submission handling; software swaps are not optical proof. |
| VR startup Idle | Under V19/E08, check valid saved settings, first-run/missing outputs or profiles, partial window/context failure and cleanup, stale configuration results, Setup reuse/replacement and GUI/headless issue visibility. No guessed black/default calibration or false session Ready. |
| VR geometry, photometry and photodiode | Verify surface/observer geometry, output mapping, calibrated/uncalibrated profiles, marker placement/levels and optical sequence/timing under V15/V22/V23. Include same-level marker boundaries with no edge. |
| VR media decode and profiles | Under V04/V11, verify PNG/TIFF source-depth preservation, JPEG/H.264 interpretation, FFV1 and static GLB supported/rejected profiles, exact media endpoints/VFR selection and independent instances. Exercise aggregate decoder/codec thread and memory limits, callbacks/logging, stale generation rejection, leases, cancellation/hung native work and all four outputs with tracking/recording. No measured throughput or decoder fault isolation is claimed. |
| VR protected assets | Under V04/V13, verify protected streaming sources on the actual storage/decoder combination, independent instance cursors, dependency coverage, external write/replacement attempts and release after cancellation/owner loss. Prepared-memory reuse and relocated replay must use the identified content; no periodic trial-time hashing or archive is introduced. |
| VR linear color and measured tables | Under V04/V21/V23, verify source transfer/range/channels and 8/16-bit preservation, float32 composition/premultiplied alpha/filtering, named clipping flags, curve interpolation and one-time correction. Measure each output's response and actual code precision; check manual/driver/projector conditions, no double gamma, Idle/marker consistency and distinct marker light levels. Independent channel tables alone do not prove cross-projector color matching or spatial uniformity. |
| VR output precision and custom encoding | Under V20/E13, verify requested versus actual RGB8/RGB10 buffers, final code preservation, calibration matching and the real driver/cable/projector path. Exercise the single composite lossy argument validation, actual encoder compatibility at the composite resolution, explicit review conversion and encoder load/failure while preserving live rendering and required state evidence. Under SYS-002, confirm the now-operational RTX 2080 Ti sustains three concurrent NVENC sessions (two cameras plus one VR composite) at planned rates while the RTX 5060 Ti renders/tracks and AMD integrated graphics serves the operator display/GUI. Verify actual adapter identities, explicit FFmpeg device selection and host-transfer costs; the earlier RTX 5060 Ti encoder probes do not validate this placement. Normal runtime still performs no file-content validation. |
| SpikeGLX session control | Under E12 and the [control contract](../contracts/spikeglx-control.md): installed SDK/SpikeGLX versions; command server bound to the dedicated link and firewall admitting only the rig; readback, gate/trigger-mode rejection and run-name collision behavior; startRun-to-saving latency and per-stream sample-count progress (including one stalled stream) to set the writing/no-progress bounds; stopRun completion; timed-out mutation reconciliation; Abort/link-loss behavior including transient recovery, per-stream deadline expiry, late replies and counter reset detection; command-server port (default 4142); stop margin against the final photodiode edge; controller-loss emergency warning naming the run for manual stopping. Acknowledgements are not pulse timing. |
| VR scene composition and geometric correction | Under V02/V15, exercise one arena plus ordered alpha overlays, overlay independence from arena depth, covered-instance continuity and invalid composition rejection. Verify imported mesh coverage/orientation/fold rejection, masks and weighted overlaps, immutable session mappings, photodiode stage order and final-output recording/replay. Establish calibration accuracy through the actual optical path and resource cost on all outputs; no automatic calibration or optical-model guarantee is selected. |
| VR review video and fragmented MP4 | Under E13, verify the constant-rate raw stdin input at the pacing output's nominal refresh sustains the composite resolution, video frame n maps to the n-th admitted render group in the evidence, tile placement/scale matches the recorded layout and admission drops shorten playback without duplicated frames. Exercise fragmented output, keyframe/fragment resource bounds, reader compatibility and drain/sync/close without ordinary-MP4 conversion or file-validation passes. |
| Empty VR review video and explicit depth conversion | Under V12/E13, exercise an all-dropped composite with complete required records, warnings, truthful artifact presence and successful cleanup. Reject empty-input encoder errors, missing-created artifacts and unknown results as normal completion. Verify explicit RGB10-to-8-bit review conversion and rejection of silent negotiation while live output/replay retain their selected precision. Normal runtime does not inspect completed-file contents. |
| VR capture and durability | Verify per-group composite admission, compositing/PBO readback cost on the render thread, recording-thread and FFmpeg throughput within the renderer's process/GIL, ScheduleTrial FFmpeg launch with no frames before T and pre-T cancellation cleanup, required state/metadata retention and failures under V12/V13/V28; test periodic sync, sync failure, an incomplete final JSON line and replay labelled "partial, up to render group N". Preserve Unconfirmed crashed-video outcomes. |
| Acquisition electrical/serial behavior | Verify trigger levels/edges, MCU board/pin capabilities, OFF/watchdog behavior, serial latency and DTR/RTS reconnect/reset under A10/A11; do not infer pulse-to-frame edge mapping from host receipts. |
| Acquisition platform bindings | Verify frame-log flush/OS sync on the selected filesystem and SDK/native conversion under A07/A10, and the A03 seqlock slots plus Win32 named event adapter across spawned and independently launched consumers, including torn/lapped-read skips under load and a killed producer. |
| VR feedback freshness | Tune and validate the 350 ms engineering default maximum under [V26](../docs/architecture/vr.md#v26) with the full rig workload. Measure host-receipt-to-application age separately from optical latency; verify local stale-result rejection, fresh-result resumption within the same generation, producer-marker generation exclusion and logged hold/resumption. No passing evidence is supplied. |
| FFmpeg raw input path | Verify raw stdin input (`-f rawvideo`, resolved pixel format/size, nominal `-framerate`) for the selected native pixel/conversion paths sustains the planned rates. Confirm video frame count equals non-dropped frame lines, no duplicated/padded frames and a final frame of one nominal period. Record exact tested versions, arguments and camera formats. |
| Consumer precision and encoder compatibility | Verify native unpacking/alignment and source-depth RGB/grayscale preparation under the [pixel contract](../contracts/acquisition/pixel-processing.md), including high-bit-depth sources. Confirm the actual selected codec/output bit depth and color representation; no silent lower-depth conversion or widened 8-bit data labelled original-depth. Preview alone uses the approved display scaling. Keep lossy compression quality separate from representation bit depth. Verify the explicit per-camera output pixel format under A08, including detection of encoder format substitution. Check requested versus actual range/matrix conversion and output tags using known pixel values; tags alone do not prove the conversion. Verify that lower-depth output settings reject higher-depth sources until explicitly compatible arguments are provided. |
| Basler conversion mappings | Exercise the declared [SDK registry](../contracts/acquisition/sdk-mappings.md): native packing/stride, Bayer patterns and edges, private buffer lifetime, effective depth and preview scaling. Record actual device/SDK support; unsupported mappings must fail explicitly. |
| Windows ownership and cleanup | Exercise the shared [acquisition/VR launch contract](../contracts/windows-launch.md) and acquisition [I/O/sync contracts](../contracts/acquisition/windows-resources.md), including owner death at every launch stage, partial handle transfer, blocked pipe/stdin cancellation, process identity reuse, encoder sharing and failed storage sync. Require truthful cleanup blockers. |
| Runtime finalization boundary | Under A07/E05, verify bounded online accounting, encoder finalization, sync and close without a separate file-validation pass. Measure drain/closure delay before the next trial. Output-content inspection belongs to external post hoc or development verification, never an automatic runtime validator. |
| Empty camera video | Verify the all-dropped case with actual input/muxer behavior: complete frame log with its completion line, truthful artifact presence/closure and grouped warning. Reject encoder failure disguised as empty success, missing-created artifacts and unknown closure; retain Interrupted/health outcomes. |
| MCU host boundary binding | Verify grouped ON/OFF dispatch at host T/end, reserved-channel drain, command/reply timestamps, Abort during an outstanding request and late OFF evidence. Validate report deadlines independently from physical pulse/exposure delay; no early compensation or shifted recording interval. |
| Encoder pre-T launch and cancel cleanup | Under A08, with both cameras enabled, verify FFmpeg launch/registration at ScheduleTrial acceptance completes before T, no frames reach it before T, and first real input, recording-queue occupancy/drops and Started deadlines at T. Measure T-to-first-encoded-input latency (including any encoder initialization FFmpeg defers until its first frame) and confirm zero start-up drops without `recording_startup_allowance_ms`. Exercise pre-T launch/initialization failure (interrupts before release), and schedule cancellation, interruption and release failure before T: the child is terminated, only its own created MP4 is deleted and an unexpected file is kept and reported. Ready alone is not encoder initialization evidence. |
| Producer-local interruption | Delay stop delivery across cameras. Verify each camera worker's recording thread uses its capture cutoff, preserves prior admitted frame records, never substitutes request time, and keeps a missing cutoff unconfirmed. |
| Camera clock provenance | Verify selected source/unit readback, descriptor transfer and frame-log header clock fields against actual models/configurations; include unknown units, missing samples, reset/wrap and source changes. No host-clock calibration or inferred device semantics. |
| Recording identity survival | Verify acquisition-owned tags match frame-log header/session identities through hybrid MP4 writing, normal finalization and interrupted (crash-truncated) writing. Missing/damaged/cross-paired tags must remain unverified; checks here are development work, never a runtime validation pass. |

Exercise both representative generated input and camera recordings on the rig after
the main architecture is established. Keep sample outputs and comparison results as
evidence. An unsuccessful check requires a revised implementation proposal or an
explicit decision change; do not silently loosen timing requirements. Missing/crashed
outputs must remain uncertain rather than being counted as a passing result.

Other runtime, performance and durability verification remains required by E15;
this list records the specific items deferred here, not a completed test plan.

VR declaration closure: the constant-rate review timing (frame n = n-th admitted render
group) is bound in [encoding options](../contracts/vr/encoding-options.md#review-timing).
The existing encoder input-format/throughput deferral is unchanged; no successful test
is implied. Full declaration status is in the
[VR contract index](../contracts/vr/README.md).

Application shutdown verification under E08: nested job membership for every backend
and partial helper launch; sole non-inherited outer handle; controller, supervisor,
both-authority and launcher failure; graceful cleanup followed by bounded escalation;
no unrelated process termination; unresolved output/SpikeGLX evidence retained at
next startup. Verify actual process absence and machine-guard release separately
from file closure. These checks remain pending runtime implementation and execution.

E06 operator-incident verification remains pending: confirm popup/reconnect/headless
behavior without shifting stimulus clocks; isolate camera/recording/tracking/ephys
failures while retaining truthful missing-data outcomes; abort and new blocking faults
override pending/stale Continue; repeated faults coalesce without losing scope; initial
readiness and healthy-function gates remain enforced; decision persistence and emergency
failure paths work within existing bounds. No runtime UI or fault-isolation behavior is
claimed by the declarations.

## Acquisition terminal accounting and serial stop budgets

- Verify A07/A10/A11 bounded post-cutoff retrieval, countable SDK purge/stop discards,
  optional native counter availability and complete terminal pulse evidence before sync.
- Resolve per-camera exposure/transport/SDK/frame-period drain allowances and verify
  actual stop/report delivery, including Abort behind an outstanding serial request.
  The 100 ms ACK / 50 ms completion reserve within 250 ms is an engineering allocation,
  not measured feasibility. No trial extension, output-file scan or runtime validation
  worker is authorized. See [MCU contract](../contracts/acquisition/microcontroller.md).

## Tracking delivery resets and exact pose geometry

- Verify [A06/T08/T09/T45](../docs/architecture/tracking.md): delivery overflow preserves
  continuous flow/filter state, actual camera gaps rebuild it, retained poses still pass
  age/order checks, and discarded movement is never replayed.
- Verify bounded pose/geometry history and native leases under reset/cutoff/concurrent
  consumers. Measure exact geometry construction's effect on pose cadence and movement
  throughput; no tolerance approximation or performance guarantee is accepted.
