# Independent audit assessment

Reviewed against the current repository on 2026-09-23. This is an evidence/work
assessment, not a replacement decision log. The pasted audit's line numbers may
shift after corrections; links below identify the governing artifacts. Accepted
policies remain authoritative. No backend or rig behavior has been tested here.

## Assessment

The audit's main conclusion holds: accepted policies and numerous declared contracts
do not establish a complete implementation contract. Controller/supervisor policy is
largely settled. Acquisition's identified local declaration gaps are now bound;
VR schema/interface declarations are indexed in contracts/vr/README.md. The consequential policy items identified by this audit are now
settled in the owning decisions linked below; their contract and runtime completion
remain distinct from policy acceptance.
Severity labels describe possible implementation consequences, not an observed
failure in an existing CephVR2.0 runtime.

| Audit claim | Assessment and disposition |
| --- | --- |
| C1: duplicate duration authority | Confirmed schema mismatch in [control types](../contracts/cephvr/control/v1/types.proto). Fixed within V06/E05: reserve/remove editable duration, add VR-owned resolved duration, require matching schedule arithmetic against the prepared plan. The former schema allowed a conflicting source; no runtime exists to prove that scheduling actually read that field. |
| H1: unnamed host clock | Confirmed original gap; now bound by [E08](../docs/architecture/system-contracts.md#e08) and the [host-clock contract](../contracts/host-clock.md), including process compatibility and storage identity. This closes the API declaration gap, not runtime integration or rig validation. A08's 1 microsecond MP4 grid is quantization, not proof of host measurement or scheduling accuracy; checking clock resolution alone cannot establish those guarantees. |
| H2: controller-loss fallback | Original gap now bound in [controller health](../contracts/controller-health.md) under E08: independent supervisor/coordinator monitors, existing bounded recovery and convergent lifecycle cleanup. This closes the declaration gap, not runtime integration or failure testing. |
| H3: VR Started and timing misses | Lifecycle evidence is incomplete. E05's 250 ms liveness limit takes precedence; V10 does not waive required liveness. Define each required output's software presentation evidence. A successful swap return is not confirmed physical illumination; correct that wording instead of claiming optical confirmation. |
| H4: VR tags/files | Confirmed missing concrete reservation/format bindings in [recorded outputs](../contracts/vr/recorded-outputs.md). Tag names are routine details. A per-trial replay manifest alone does not solve oversized program/plan retention with Save VR data Off; the E07/E04 setup-artifact binding must also be completed. |
| H5: reset-notification delay | Plausible transport/progress hazard, not a proven inevitable reset loop. [Feedback](../contracts/vr/feedback.md) already coalesces pending requests and gates generations. Concrete delivery/admission still needs binding. Moving notification into a lossy result queue is not automatically sufficient: overflow must never erase the prerequisite notification. Preserve ordered results, generation fencing and a reliable reset boundary; choose mechanisms as local transport work unless a guarantee must change. |
| H6: VR trial membership | The evaluation timestamp exists in [presentation](../contracts/vr/presentation.md); its common use for membership/capture still needs binding. Also define the final submission cutoff: evaluation inside the trial must not silently authorize displaying a late trial frame after Idle/cutoff. A single timestamp rule alone does not resolve in-flight multi-output work. |
| H7: sample alignment | Original registry ambiguity reconciled in [pixel processing](../contracts/acquisition/pixel-processing.md#prepared-alignment-and-preview-scaling), SDK mappings and preview: native alignment stays unchanged, prepared high-depth images use explicit MSB alignment, and preview interprets the declared range before scaling. No intermediate LSB buffer is required. Claimed 4-bit loss remains a conditional wrong-conversion consequence, not measured data loss; runtime/SDK verification remains outstanding. |
| H8: HDF5 completion | Original gap now bound in schema (hdf5_schema.toml, removed 2026-09-27) and [recording lifecycle](../contracts/acquisition/recording-lifecycle.md). Final count and completion describe online accounting, never later sync/close or persisted integrity. A07/E05 defer normal file validation to external post hoc work; explicit recovery still verifies its claimed prefix. |
| H9: MCU boundary B | Original gap bound in the [MCU timing contract](../contracts/acquisition/microcontroller.md#host-boundary-and-evidence-binding): normal dispatch targets T/end, independent producer cutoff, interruption handling and typed host observations. No simultaneous physical edge/cutoff claim; synchronization and rig verification remain outstanding. |
| H10: mutable assets | Source-stability and failure/release rules are now bound by V04's [asset lifetime](../contracts/vr/asset-lifetime.md): prepared immutable resources or protected streaming handles, covering dependencies before use. No automatic asset archive or post-use hashing substitute. Platform/decoder implementation and verification remain outstanding. |
| H11: completion claims | Original overstatement corrected. The shared clock/controller-loss and audited acquisition declarations are now bound, including empty-video and MCU timing evidence. Runtime/rig claims remain excluded; VR and later backend contracts are still incomplete. |
| M: VR port and containment | Missing port/worker endpoints are routine bindings. The accepted [E08 amendment](../docs/architecture/system-contracts.md#e08) now extends the shared Job Object mechanism to VR; use the shared launch contract, not a second containment implementation. Port 50054 is a proposal, not an accepted value. |
| M: VR progress/RPCs | Confirmed declaration gap; fill typed interfaces/progress evidence under existing E06/E08, not a new liveness-policy questionnaire. |
| M: ordering reproducibility | Confirmed: V08 promises a versioned independent ordering stream, but [durations](../contracts/vr/durations.md) only concretely binds its own RNG stream. Specify ordering/seed derivation and retain resolved plans; seed reuse alone is insufficient. |
| M: VR video/record correspondence | Confirmed missing frame-to-sample mapping, timestamp/container and closure bindings. These are separate from accepted lossy-review and replay policies. |
| M: required VR records | Confirmed distributed requirements without a complete schema/inventory. Consolidate required fields/record kinds; losing mandatory metadata remains fatal under V12. |
| M: A05 endpoint | [Feedback](../contracts/vr/feedback.md) distinguishes application check from output incorporation, and [presentation](../contracts/vr/presentation.md) defines per-output swap observations. Their concrete association/record schema is missing; do not conflate the V26 age guard with optical/end-to-end latency. |
| M: acquisition code/clock/PFS/warnings | Stable code catalogue, typed occurrence aggregation and report bindings are now declared in [diagnostics](../contracts/acquisition/diagnostics.md). [Camera-clock provenance](../contracts/acquisition/camera-clock.md) and the retained in-memory PFS adapter binding in [camera settings](../contracts/acquisition/camera-settings.md#retained-pfs-application-binding) are now declared. Declarations do not establish runtime delivery or recording correctness. |
| M: MP4 pair identity | Original declaration gap closed in [recording identity](../contracts/acquisition/recording-identity.md): acquisition writes existing IDs to MP4/HDF5 and explicit recovery checks them against session metadata. Unknown/mismatched identity fails verification. Runtime and crash-survival validation remain outstanding. |
| M: editable MP4 timescale | Not an unresolved numeric policy: [encoding options](../contracts/acquisition/encoding-options.md) already rejects values other than the accepted denominator. A fixed value inside editable args needs enforcement, not another choice. |
| M: 1 ms retrieve wait | Original 1 ms recurring cap replaced by [capture-wait](../contracts/acquisition/capture-wait.md): joint SDK result/control/deadline wait and nonblocking retrieval, with command checks between frames. SDK binding/GIL/wakeup and rig performance verification remain outstanding; no measured performance problem or improvement is claimed. |
| M: all-dropped video | Bound in [empty-video results](../contracts/acquisition/empty-video.md): content, artifact presence and closure are independent; A07's narrow never-created case requires complete accounting/cleanup. Encoder/storage failure and unknown evidence cannot qualify. Runtime/empty-input compatibility remains unverified. |
| M: launch-at-T buffer loss | Plausible risk, explicitly listed for rig verification. No measured startup latency/frame rate proves drops at every trial. A08 now launches FFmpeg before T (no frames before T); the rig check remains and the optional allowance stays unset. Do not silently resize or assert unavoidable loss. |
| M: rig checklist | Confirmed incomplete consolidated checklist. Add named VR and acquisition platform/electrical cases without claiming they are newly accepted policies or completed tests. |
| Low: stale text/duplication | Several stale notes confirmed and corrected in this pass. Remove redundant unresolved statements, but keep E14's intentionally requested TOML policy declarations. Repetition in a schema/config binding is not automatically a competing authority. V22 pattern keys must validate against version 1 rather than accept arbitrary edits. |
| Low: proto details | Role mappings, repeated-field equality checks, controller-only readback adoption and inactive gzip-level handling are bound in [configuration bindings](../contracts/acquisition/configuration-bindings.md#matching-duplicated-representations). No case-folded role guesses or competing settings authority; implementation validation remains outstanding. |
| Validation/tooling claim | No compiler was installed in the initial environments checked in this review. That does not disprove a previous compile. Re-run compilation with a temporary isolated toolchain; report its actual result rather than equating absent tooling with invalid schemas. |

Clock source verification: [CPython 3.12 pytime.c](https://github.com/python/cpython/blob/3.12/Python/pytime.c)
and [Python 3.12 time documentation](https://docs.python.org/3.12/library/time.html).
The latter documents system-wide Windows perf_counter behavior from Python 3.10.

## Decisions versus direct contract work

The preview scope and VR recording crash guarantees are now owned by
[A03](../docs/architecture/acquisition.md#a03) and [V28](../docs/architecture/vr.md#v28).
[E08](../docs/architecture/system-contracts.md#e08) owns the accepted VR containment
extension; [V19](../docs/architecture/vr.md#v19) owns accepted startup presentation.
Their dependent contracts/configuration declarations are reconciled. Acquisition's existing all-dropped-video
behavior and its explicit wire/completion representation are now bound in A07/E05.
No further consequential policy choice is identified in this audit. Remaining local
contract work is not rig-deferred. Tracking design stays last; this assessment does
not replace the owning decisions or claim contract completeness.

Do not reopen E13's accepted live review recordings merely because offline rendering
is possible. Likewise keep the user-requested config policy declarations and explicit
rig/encoder deferrals; the audit's optional simplifications are not authorization.

## Validation in this review

At the time of this review, the control/acquisition Protobuf files compiled together successfully (all protos under contracts/cephvr now compile together)
with isolated grpcio-tools 1.84.0 / protobuf 7.36.2 installed under `/tmp`, including
the revised duration schema. The project environment was not modified. Edited TOML,
decision-register revisions and local links/anchors passed static checks. This is
schema validation only, not implemented scheduling, storage or rig behavior.

## Changes and next work

This pass fixes the duration authority binding and targeted stale status/navigation and the consolidated rig-verification checklist.
The remaining confirmed gaps above are still work, not silently implemented policy
changes. Current open work is tracked in the backend contract worklists and the
root Current position; declarations do not deliver an implementation.
Use owning contracts/worklists for implementation; this report preserves the audit
assessment rather than duplicating each governing rule.
