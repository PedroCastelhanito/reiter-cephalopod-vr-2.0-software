# Visual Stimulus display and worker control binding

Authority: [V01](../../docs/architecture/visual_stimulus.md#v01), [V12](../../docs/architecture/visual_stimulus.md#v12)
and [V19](../../docs/architecture/visual_stimulus.md#v19); shared authority, registration, deadlines
and interruption remain [E05–E08](../../docs/architecture/system-contracts.md#e08).
The [messages](../cephvr/visual_stimulus/v1/messages.proto), [private services](../cephvr/visual_stimulus/v1/services.proto)
and [runtime fields](../cephvr/visual_stimulus/v1/runtime.proto) define the service boundaries.
Implementation and validation status is recorded in [the Visual Stimulus report](../../reports/visual_stimulus.md).
The [canonical program/prepared model](stimulus-schema.md), [capture/evidence paths](runtime-bindings.md) and [evidence schema](evidence-format.md) supply the companion definitions.

## Naming and client compatibility

Use `cephvr.visual_stimulus.v1` for generated backend payloads and services, and
`VisualStimulus*` for public service/message types. Backend configuration selects
`visual_stimulus`; the save field is `save_visual_stimulus_data` (JSON
`saveVisualStimulusData`). Rebuild all clients against the renamed sources and update
saved/session configuration keys together. Protobuf field numbers are retained;
RPC full names and JSON/type names change. Program/PreparedTrial remain format 2,
while renderer/compiler/schema compatibility identifiers follow the package name.
External analysis consumers must check the recorded compatibility identifiers.

## Display configuration and startup

[DisplayProfile](../../src/cephvr/visual_stimulus/config/models/display_profile.py) is the canonical
lightweight display model; the contract Python module re-exports it for compatibility;
[its JSON Schema](display-profile.schema.json) is generated, never independently edited.
VisualStimulusSettings carries the complete profile as UTF-8 JSON in DisplayConfiguration. GUI,
headless, saved history and backend use parse_display_json with the same resolved byte
limit. Reject duplicate keys, coercions, unsupported fields/versions, nonfinite numbers,
invalid geometry and broken references. Output identities and prepared indices follow authored order, never device enumeration; presentation order is bound in runtime-bindings.md. Asset references are portable root-relative logical paths; opening/protection,
content validation and operating-condition/capability comparisons remain Setup work.
Uncalibrated mode may retain a stored photometric reference but does not load/apply
it; calibrated mode requires a compatible profile for every required output.

Each output has `enabled` (default true for existing profiles). Full rig geometry,
output declarations and mappings remain stored; only enabled outputs/mappings
participate in resource preparation, rendering, presentation and recording. Disabled
outputs do not require connected devices or loaded calibration assets. At least one
output must be enabled. `pacing_output_id` independently selects an active timing
output; legacy profiles may use their enabled photodiode target when this is absent.
`photodiode_enabled` defaults true for existing profiles. When false, retain
`photodiode_output_id`/patch without target availability, enablement or bounds checks;
no patch is drawn. Enabled pulses require valid active placement at Setup. There is
no implicit relocation of either marker or pacing. A participation change needs fresh preparation.

The model binds four surfaces in millimetres with explicit corner ordering, one fixed
observer, clipping distances/tolerances, physical outputs, viewports and imported
geometric/photometric references. Idle RGB is linear Rec.709/D65; finite excursions
follow V21. Profiles do not contain trial epochs, tracking gains or program assets.
[GeometricProfile](geometric-profile.schema.json) and [coverage checks](runtime-bindings.md) bind imported content; a passing display reference cannot substitute for them.

Startup uses controller-authorized InitializeDisplay on VisualStimulusConfigurationService. Bind
controller/backend/renderer generations, command ID and current configuration revision;
no session/trial work is created. The coordinator dispatches renderer InitializeDisplay
with the same parent operation and the remaining shared Setup budget. Normal commands
come from the registered owner; the supervisor may independently cancel/clean/shut down
through its E08 authority. The renderer rejects display initialization during prepared
or active session work. A repeated request is idempotent, not another initialization.

The renderer launch is registered before session work exists and remains owned by the
exact Visual Stimulus backend generation. Supervisor safety dispatch discovers that persistent
launch, queries its retained current work/revision, and rejects a different session.
Each safety command carries its original absolute deadline in both the worker message
and transport metadata; retries retain the original payload. Cleanup admission alone
is insufficient: reconcile the exact retained executor outcome within that deadline.

The public request's optional `asset_root` (tag 9) and private request's `asset_root`
(tag 5) carry the same controller-selected root without reinterpretation. It is required
when display dependencies need it; no software-directory fallback or trial inputs are
introduced by startup. Existing published field numbers remain unchanged.

Only display/Idle assets are opened. Display model validation permits absent trial-patch
geometry at startup; mixed pacing still requires a designated output. Full Setup calls
require_trial_marker, then validates distinct resulting patch code values under the
actual output correction. Missing trial assets/recording settings cannot block startup
Idle. Missing display dependencies do; no invented fallback color/profile/output.

Renderer VisualStimulusDisplayView reports the applied revision only after all required
outputs have confirmed resource checks and returned Idle submission calls. Retain each
output's observed RGB framebuffer bits, requested interval, swap observations, issues,
cleanup obligations and original observation time. Returned means software submission
only. On partial failure, applied_revision is absent for this attempt and resources are
released through the same path; absence of a field is unknown, not successful cleanup.
The controller retains the view in Snapshot.visual_stimulus_display, separately from session Ready.

The coordinator forwards the exact worker evidence; it cannot upgrade failed/unknown
outputs. Validate source against registered worker and command, configuration and
controller generations. Older evidence cannot validate a newer edit. Keep the last
successful applied display revision distinct from the current attempted revision;
a failed attempt does not erase truthful prior-resource evidence or claim old Idle is
still valid. Controller edits do not reconfigure live output. Explicit Setup revalidates
and reuses/replaces resources; there is no new retry UI or automatic polling loop.

## Session/trial lifecycle

| Stage | Renderer | Recording thread when saving On |
| --- | --- | --- |
| SetupSession | Validate display/program resources; retain immutable prepared identities and live Idle. | Validate arguments, output reservations and bounded capture/evidence resources; create no trial files. |
| PrepareTrial | Retain the exact trial plan/duration, prepared initial state and required initial media; acknowledge required resources. | Prepare the trial's paths, encoder configuration and capture slots. |
| ScheduleTrial | Verify end minus start equals retained resolved duration and epoch sum. Retain schedule; no execution. | On acceptance, launch FFmpeg off the render thread with the final paths; no frames before T. Launch failure is a required failure before release. |
| ReleaseTrial | Validate the exact retained schedule and shared release deadline; initialize trial state at T. | Feed frames and write evidence only at or after T under E11. Cancellation before T terminates FFmpeg and deletes only the file it created. |
| StopTrial | Seal trial updates/admission at the real cutoff; return to valid Idle. Report cutoff to the coordinator (E08/O2). | Drain admitted in-interval samples and required evidence, then finalize/sync/close with exact output results. |
| InterruptSession | Fence the session permanently, retire pending release, begin immediate local stop/cleanup. | Fence new work and begin bounded drain/finalization independently. |
| Cleanup | Release registered trial/session resources; resident valid Idle/display resources may remain under V19. | Release capture slots, FFmpeg and files only with exact closure/release evidence. |
| Shutdown | Cancel initialization/work, gracefully release all owned display/GPU/window resources and exit. | Gracefully close owned files/children before the renderer exits under E08. |

Same-host deadlines are absolute host_time_ns values, bounded by the parent's original
remaining budget. Retries, RPC cancellation and repeated stop causes do not extend them.
Closed-loop SetupSessionRequest carries feedback_attachment through the
[shared Setup handoff](../data-preparation.md); the coordinator passes it unchanged to
renderer WorkerSetup and requires the actual tracking peer handshake before Ready.
WorkerSetup carries existing PreparedSession/VisualStimulusSettings and resolved VisualStimulusFilePolicies;
PreparedHandle identifies compiler/model/resources and retained immutable plan bytes.
Matching a handle is necessary but not evidence that media/resources were prepared.
Setup sends one bounded immutable `PreparedArtifact` with its exact `TrialContext`
through `WorkerOperation` tags 5 and 6. The coordinator verifies content hash, size,
version, identities and controller summary against those bytes before aggregate Ready.
At or after confirmed released onset, the coordinator publishes those bytes and sends
`ConfirmRecipePublication` with the exact handle/path/result. This separately retained
command gates the dependent evidence header; it does not replace Release, repeat
compilation or extend a deadline. Recipe, evidence and review-video closure stay separate.
[PreparedTrial](stimulus-schema.md) binds the full typed plan, retained inside Visual Stimulus and identified to the controller by ResolvedStimulusPlan.prepared (PreparedHandle), with schedule/hash agreement required. No per-epoch or per-frame coordinator RPCs.

Worker lifecycle uses the shared Ready/Started/Stopped/Finished/Cleanup payloads plus
an explicit source process identity and prepared generation. Ready/Started go to the
coordinator for aggregation. Workers deliver Stopped/Finished/Cleanup only to the
coordinator, which validates registration and exact obligations; after coordinator
loss the supervisor reconciles through the worker's GetState (E08/O2). Worker reports do not impersonate aggregate backend readiness;
the coordinator reports aggregate lifecycle through existing ReportLifecycle endpoints.
Heartbeats go to the coordinator (ReportWorkerHeartbeat) and errors directly to supervisor under E08; neither its delivery nor a
coordinator round trip gates emergency local stopping.

The renderer's retained cutoff binds the real cutoff, final render group and exact
output set; unknown cutoffs remain absent. Sealing admission is separate from draining
and output closure. The recording thread drains admitted captures and pending evidence
lines within existing finalization bounds, not waiting for a quiet queue or RPC success.
Missing required lines are required-evidence failure. [Capture/evidence paths](runtime-bindings.md)
bind this in-process path; it still requires runtime implementation.

GetState reconciles retained command/evidence without resetting clocks or starting work.
An unknown command never authorizes blindly replaying an uncertain release. Save Off
has no recording/capture/encoding obligations; the coordinator still writes and closes
the required stimulus log under runtime-bindings.md. Finished includes compact per-output timing
summaries even with Save Off, plus one ReviewRecordingSummary for the composite when saving; detailed scientific histories never enter these RPCs.

## Resource policy binding

VisualStimulusFilePolicies is controller-resolved from visual_stimulus_config.toml, file-only and locked by E07.
[resources] keys map one-to-one to ResourceLimits; counts and byte capacities are positive
integers, checked against protobuf widths and allocation overflow before use. Missing
limits fail the path that needs them. Display-only startup uses document/CPU/GPU limits;
program expansion adds epoch/plan limits; video inputs add decoder/context/frame limits;
saving adds capture/evidence limits and recording progress/sync intervals. Save Off
and programs without videos do not require irrelevant settings or allocate their buffers.

[feedback] max_result_age_ms (default 350, configurable, positive) maps to
VisualStimulusFilePolicies.max_result_age_ns using exact decimal milliseconds-to-positive-int64-
nanoseconds conversion. Closed-loop Setup requires a valid value; reject precision
loss/overflow. Open-loop preparation does not require this field. The renderer
receives the value locked at Start.

[recording_runtime] uses positive finite *_s fields for record_sync_interval,
video_sync_interval, fragment_target, encoder_stall_timeout and record_stall_timeout.
Convert decimal seconds to exact positive int64 nanoseconds once; reject excess precision
or overflow. Sync intervals are progress scheduling, not proof of bounded crash loss.
No health/lifecycle timing is copied here. Decoder threads are bounded both per context
and in aggregate; aggregate CPU/GPU/memory reservations include staging, leased frames,
codec working memory and metadata, not just one ring's slots. E14 engineering defaults
live in the owning TOML. At Setup, validate aggregate planned native/CPU/GPU storage,
context/thread limits and one complete render group's evidence plus bounded updates.
Require evidence_pending_bytes to hold at least one complete render-group line plus
its bounded late-update reservations. Validate thread totals (simultaneously active codec
contexts times per-context threads within codec_threads_total) without spawning more
threads than budgeted. Declared context capacity is not simultaneous decode activity.
Reject excess rather than silently grow, shrink content or guess device capacity;
positive defaults alone do not establish feasibility or sustained throughput.

The public coordinator port belongs to [rpc].port in visual_stimulus_config.toml, required at startup;
worker ports remain OS-assigned registered private ports. The default is 50054 (E08);
startup rejects absence/conflict instead of choosing an ephemeral public port.
No new worker/process or cross-backend defaults are introduced.

## Verification boundary

Schema generation, pure display validation and Protobuf compilation can be checked
locally. Native output capability, profile contents, window/GPU resource release,
worker dispatch, transport integration and rig behavior are not established by these
checks. Continue the explicit worklist; this does not declare Visual Stimulus fully implemented.
