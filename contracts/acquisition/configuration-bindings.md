# Acquisition configuration binding

[E07/E14](../../architecture.md#e07) govern ownership and precedence. This contract
completes the acquisition-specific routing into the existing typed configuration,
Setup and worker messages. It defines a loader/validator; none is implemented yet.
Wire declarations: [runtime](../cephvr/acquisition/v1/runtime.proto),
[camera](../cephvr/acquisition/v1/camera.proto), [workers](../cephvr/acquisition/v1/messages.proto).

## Resolution and validation

The controller's lightweight acquisition configuration module reads the owning TOML
at Setup; acquisition receives the resulting immutable settings and file policies.
No worker rereads defaults. Configuration preview/PFS/pulse preparation resolves the
same relevant file policies before device access, while preserving the current
configuration revision. Fresh Setup rereads files and replaces that prepared state.
Unknown fields, types, policies or contract versions fail with a FieldIssue.

acquisition_config.toml holds only the configurable keys below (E14). Fixed policy
declarations live in [acquisition_policy.toml](../policy/acquisition_policy.toml),
checked against the implementation's contract constants before preparation; the
operator file's `policy_version` must match it, and editing the operator file cannot
redefine accepted policies. New fields require a binding and an E14 classification;
there is no ignored-key bucket or arbitrary dictionary over gRPC.
The recording confirmation and encoder closure policies require online accounting,
finalization, sync and close; they never enable output-file scans. The common
external post hoc validation boundary is owned by experiment configuration under E05.
No runtime validation worker or extra readiness dependency is implied.
In the policy file, `cameras.prepared_high_depth_alignment` is the fixed `msb` contract constant
used by the common conversion module and prepared consumer descriptors. Validate it
before preparation; it adds no selectable wire mode and never changes native layout.
`workers.capture_wait`, `diagnostics.diagnostic_codes` and `diagnostics.warning_grouping`
are likewise fixed contract constants for the capture loop and diagnostic module,
validated before preparation. They add no operator modes or duplicated wire settings;
shared ControlPolicies provide lifecycle deadlines; startup health policy provides
the cadence (E08), without duplicating it in session payloads.
`recording.frame_log.native_clock_provenance` and `recording.frame_log.pair_identity` are
fixed bindings to camera-clock.md and recording-identity.md. Validate their declarations;
actual descriptors/identities come from typed camera results and existing contexts,
not operator strings or independent recording-thread lookups.
`recording.empty_video_result` and `microcontroller.trial_boundary_timing` are fixed
bindings to empty-video.md and microcontroller.md. They add no selectable failure
mode, local timeout copy or firmware-timing override; existing shared budgets apply.
Unassigned hardware fields may be absent but are required when their active path needs
them. Absence is never substituted with zero, an empty identity or discovery order.

| Source | Typed destination / consumer |
| --- | --- |
| `rpc.port` | Acquisition startup only, 1..65535; service restart required. Not a session override. |
| `cameras.<role>.enabled`, `save_video`, `sdk_buffer_count`, `ffmpeg_args`, `recording_bit_depth` | Corresponding CameraSessionSettings fields; arguments replace the complete list. |
| `cameras.<role>.device_id`, `frame_timing`, `unaligned_free_running`, exposure/gain/ROI/pixel/trigger settings and retained PFS baseline | CameraDeviceConfiguration/CameraSettings; camera-settings.md owns unit/schema mappings and readback adoption. Camera role names are fixed. |
| `cameras.<role>.microcontroller_pin`, `pulse_frequency_hz`; configured serial port | CameraPulseConfiguration; requested values stay distinct from applied MCU evidence. |
| Microcontroller Trial state and Projector flip pin/enabled controls | CameraPulseConfiguration.trial_state_pin/projector_flip_pin and corresponding enabled fields; disabled drafts retain their pins, while active assignments must be unique. CAPS validates device support before testing. |
| `buffers.tracking_ring_frames` | AcquisitionSettings.tracking_ring_frames; shared tracking ring capacity where a tracking consumer needs it. Preview capacity remains its fixed single slot. |
| `buffers.recording_queue_frames`, `recording_startup_allowance_ms` | AcquisitionSettings.recording_queue_frames / recording_startup_allowance_ms; resolved RecordingSettings.recording_queue_frames = max(recording_queue_frames, ceil(frame_rate_hz × recording_startup_allowance_ms / 1000)) per camera at Setup, frame rate being the applied MCU or free-running rate, with its memory reported. Absent allowance: recording_queue_frames only. |
| `recording.pending_records_capacity` | AcquisitionSettings.recording_options.pending_records_capacity; RecordingSettings.pending_records_capacity. |
| `recording.diagnostics.max_lines`, `max_bytes` | recording_options.diagnostic_tail_max_lines / diagnostic_tail_max_bytes. |
| `preview.output_bit_depth` | AcquisitionSettings.preview_output_bit_depth; passed to viewer preparation; validate actual converter/viewer support. |
| `preview.session_preview_max_hz` | AcquisitionSettings.session_preview_max_hz; CameraCaptureSettings.session_preview_max_hz. Finite, ≥ 0; 0 allocates no session preview slot. |
| `cameras.<role>.transport`, `frame_silence_timeout_s` | CameraFilePolicy.transport / frame_silence_timeout_ns; transport and control/health timing are file-only. |
| `cameras.<role>.post_cutoff_drain_margin_ms` | CameraFilePolicy.post_cutoff_drain_margin_ns; active capture requires an explicit positive rig allowance covering exposure + transfer/SDK delivery + one applied frame period. File-only, not a trial override. |
| `microcontroller.stop_completion_margin_ms` | AcquisitionFilePolicies.serial_stop_completion_margin_ns; file-only stop/drain/dispatch/report reserve inside the shared E05 allowance. |
| `recording.sync_interval_s`, `recording.storage.video_sync_interval_s` | frame_log_sync_interval_ns / video_sync_interval_ns. |
| `recording.encoding.fragment_target_s`, `recording.health.stall_timeout_s` | fragment_target_ns / encoder_stall_timeout_ns. |
| `microcontroller.baud_rate`, `ack_timeout_ms`, `keepalive_interval_s`, `communication_timeout_s` | serial_baud_rate / serial_ack_timeout_ns / serial_keepalive_interval_ns / serial_communication_timeout_ns. |

`recording_bit_depth` is an optional operator/session value, exactly 8 or 10. No
implicit default authorizes reduction: absence preserves source effective depth and
fails active recording preparation if unsupported. Resolve from confirmed layout and
validate the full argument path under encoding-options.md. Send the resolved depth to
RecordingSettings.recording_bit_depth; native camera/tracking layouts remain unchanged.
Record source depth, resolved target and pixel-processing.md's mapping in the existing
active-camera session configuration, together with effective FFmpeg arguments. Save
Off preserves the requested setting without requiring encoder capability checks.

Camera source fields may originate in typed saved/operator configuration rather than
TOML when no default is assigned. PFS contents remain backend-produced under A10, not
arbitrary operator data. Every non-timing configurable setting uses E07 precedence:
explicit valid saved/operator values, then owning defaults, then permitted camera
readback for unresolved device features. File-only paths reject operator overrides.
Inactive-camera ordinary values remain editable/preserved but do not cause device
opening, tool discovery or output creation. Validate dependencies to decide activation.

A03 ring writers never wait. Reject the removed `buffers.admission_lock_timeout_ms`
and `buffers.capacity_frames` keys; no lock timeout is distributed to workers.

Use exact decimal-to-nanosecond conversion for seconds/milliseconds, require a
positive integer representable in int64, and reject sub-nanosecond/infinite values;
do not silently round control deadlines. Counts are positive uint32, excluding Python
bool-as-int coercion. Check checked multiplication and total allocation sizes against
platform limits before allocation.
Validate serial keepalive < communication timeout and the existing scheduled-boundary
reservation inequalities and microcontroller.md's whole-Abort stop-budget inequality.
Check the camera drain allowance against confirmed exposure and frame period plus the
rig transfer bound, and against the applicable stop/finalization budgets; no missing
bound is silently zero. SDK timing/rig verification remains pending. Fixed policy
`cameras.post_cutoff_retrieval`, `microcontroller.stop_budget_validation` and
`recording.frame_log.capture_completion` bind these contracts, not runtime mode selectors.
MCU protocol/version, maximum wire line, frequency grid and
duty cycle retain their fixed A11 definitions; no alternate host-selected protocol.

## Matching duplicated representations

Map camera role strings exactly: `behavioral` to CAMERA_ROLE_BEHAVIORAL and `tracking`
to CAMERA_ROLE_TRACKING. Reject unknown/UNSPECIFIED roles, case-folded substitutes or
mismatches between enclosing worker context, ring descriptor, output identity and
per-camera settings. No role is inferred from a filename or source-list position.

Requested operator settings and backend readback are different stages, not competing
authorities. Only the controller adopts successful resolution into the confirmed
revision; final worker payloads must equal that adopted active-camera state. Check
physical device identity, effective settings/layout, transport readback, metadata
availability and the shared camera-clock descriptor across their repeated locations.
Missing optional values remain missing until the owning resolution/default rule
supplies them; false and zero retain presence. A mismatch fails preparation rather
than choosing whichever field arrived last. Descriptive status cannot mutate settings.

Do not erase reusable settings to remove a harmless inactive field. Existing message-level generation/revision checks
and requested-versus-applied MCU semantics remain unchanged.

## Distribution and logging

SetupSessionRequest carries AcquisitionFilePolicies only to acquisition; shared
ControlPolicies retain their existing owner and budget fields. The coordinator
constructs each worker's payload as follows:

| Recipient | Binding |
| --- | --- |
| Camera worker capture | Confirmed device/settings/layout + that role's transport, sdk_buffer_count, silence timeout and session preview cap; only its actual tracking/preview attachments. |
| Camera worker recording (saving only) | RecordingSettings: resolved recording_bit_depth, ffmpeg_args, executables, frame-log/video sync, fragment/stall intervals, queue and pending-record capacities, diagnostic bounds and session-config reference. |
| MCU owner (coordinator) | Confirmed requested/applied pulse settings plus resolved serial policies; no camera worker opens the port. |
| Preview consumer | Existing attachment/identity plus resolved output depth; common module's fixed conversion rules. |

Resources carry exact confirmed configuration revision and registered process
identities. File policy version mismatch blocks Setup. The worker validates relevant
values/role/layout but does not repeat the controller's precedence resolution.
Protocol policies stay compiled fixed behavior, not a menu of unsupported wire values.

Log active resolved acquisition settings through E04's existing backend configuration
entry: public values, applicable file policies and camera readback, with original
TOML units/names for readability. Exclude inactive roles, raw handles, credentials,
PFS contents and a dependency inventory. Keep existing effective argument list and
file-only values, without a second custom tuning object in user configuration.
Startup ports are service context, not per-trial settings. Requested/applied MCU rates
remain distinct. Reusable history preserves operator settings/PFS under E07; reloading
history cannot replace current file-only policies. No new configuration log is added.
