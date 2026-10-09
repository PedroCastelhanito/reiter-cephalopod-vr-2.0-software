"""E14 acquisition file schema and fixed policy-version binding."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cephvr.acquisition.identity import CAMERA_NAMES
from cephvr.shared.config import (
    ConfigurationError,
    LoadedPair,
    load_pair,
    policy_digest,
)

POLICY_VERSION = 20
CONTRACT_VERSION = 1
_POLICY_SHA256 = "84257769b7d8ece6196e5e0e7b030b183b0976b57231503ef64e6781ec5599ad"

_CONFIG_KEYS = frozenset(
    """
    rpc.port
    cameras.*.device_id cameras.*.pulse_frequency_hz cameras.*.microcontroller_pin
    cameras.*.sdk_buffer_count cameras.*.frame_timing cameras.*.unaligned_free_running
    cameras.*.trigger_selector cameras.*.trigger_source cameras.*.trigger_activation
    cameras.*.exposure_duration_mode cameras.*.frame_silence_timeout_s
    cameras.*.post_cutoff_drain_margin_ms cameras.*.enabled cameras.*.save_video
    cameras.*.ffmpeg_args cameras.*.recording_bit_depth
    cameras.*.exposure_us cameras.*.gain cameras.*.gain_unit cameras.*.gain_selector
    cameras.*.pfs_source_filename
    cameras.*.frame_rate_hz cameras.*.pixel_format
    cameras.*.roi.width cameras.*.roi.height cameras.*.roi.offset_x cameras.*.roi.offset_y
    cameras.*.transport.*
    buffers.tracking_ring_frames buffers.recording_queue_frames
    buffers.recording_startup_allowance_ms
    recording.pending_records_capacity recording.sync_interval_s
    recording.encoding.fragment_target_s recording.health.stall_timeout_s
    recording.diagnostics.max_lines recording.diagnostics.max_bytes
    recording.storage.video_sync_interval_s
    preview.output_bit_depth preview.session_preview_max_hz
    """.split()
)

# The allowlist is deliberately static: newly declared policy keys are rejected
# until their implementation binding is reviewed.
_POLICY_KEYS = frozenset(
    """
    platform.target_os
    workers.start_method workers.lifetime workers.health_reporting
    workers.process_layout workers.control_transport workers.control_service
    workers.setup_payload workers.camera_setup_execution
    workers.trial_preparation_payload workers.port_assignment workers.control_execution
    workers.capture_wait
    cameras.roles cameras.transport_tuning cameras.transport_settings_source
    cameras.transport_parameter_names cameras.transport_interfaces
    cameras.pretrial_validation cameras.pixel_format_support
    cameras.image_format_implementation cameras.pixel_processing_location
    cameras.native_conversion_provider cameras.prepared_high_depth_alignment
    cameras.settings_representation cameras.capability_source
    cameras.missing_feature_values cameras.settings_apply_failure
    cameras.frame_id_origin cameras.sdk_access cameras.sdk_delivery cameras.grab_loop
    cameras.setting_readback_mismatch cameras.assignment cameras.role_device_policy
    cameras.unknown_trigger_rate_limit cameras.acquisition_mode
    cameras.external_trigger_preparation cameras.stale_buffer_cleanup
    cameras.post_cutoff_retrieval cameras.exposure_mode cameras.gain_mode
    basler.preset_format basler.preset_required basler.advanced_settings
    basler.session_preset_storage basler.preset_import_compatibility
    basler.preset_device_access basler.preset_connection_open
    basler.preset_connection_lifetime basler.preset_editing_completion
    basler.preset_setup_transition basler.preset_export_pending_edits
    basler.preset_control_loss basler.unsaved_preset_changes
    frames.native_metadata_setup frames.invalid_image_action frames.hardware_counter_gap_action
    frames.hardware_counter_discontinuity_action frames.payload_format frames.payload_layout
    frames.id_scope frames.non_trial_id_scope
    timing.host_timestamp_point timing.host_timestamp_regression_action timing.trial_membership
    buffers.allocation_api buffers.shared_rings buffers.recording_transfer
    buffers.setup_allocation buffers.naming buffers.layout_metadata buffers.lifetime
    buffers.owner buffers.synchronization buffers.writer_wait buffers.wakeup_primitive
    buffers.lapped_read_action buffers.crashed_participant_action buffers.read_mode
    buffers.working_buffer_allocation
    recording.output_tag recording.frame_log_video_column recording.metadata_policy
    recording.frame_records_format recording.saved_confirmation recording.empty_video_action
    recording.empty_video_result recording.buffer_full_action recording.drop_selection
    recording.frame_log.schema recording.frame_log.frames_file recording.frame_log.diagnostics
    recording.frame_log.diagnostic_details_overflow recording.frame_log.pair_identity
    recording.frame_log.native_missing_values recording.frame_log.native_timestamp_unit
    recording.frame_log.native_clock_provenance recording.frame_log.native_timestamp_unavailable
    recording.frame_log.invalid_image_row recording.frame_log.video_correspondence
    recording.frame_log.row_write_policy recording.frame_log.pending_records_owner
    recording.frame_log.metadata_transport recording.frame_log.capture_completion
    recording.frame_log.append_schedule recording.frame_log.crash_state recording.frame_log.recovery
    recording.tools.discovery recording.tools.version_policy recording.tools.version_mismatch
    recording.encoding.started_evidence recording.encoding.lifetime recording.encoding.preparation
    recording.encoding.pre_start_cancel recording.encoding.pixel_conversion
    recording.encoding.input_representation recording.encoding.bit_depth_policy
    recording.encoding.supported_recording_bit_depths recording.encoding.recording_depth_mapping
    recording.encoding.output_pixel_format_policy recording.encoding.bayer_output
    recording.encoding.framework recording.encoding.acceleration recording.encoding.input_connection
    recording.encoding.input_packaging recording.encoding.input_writer
    recording.encoding.input_frame_source recording.encoding.input_flush
    recording.encoding.input_compression recording.encoding.args_scope
    recording.encoding.args_ownership recording.encoding.container recording.encoding.mp4_mode
    recording.encoding.faststart recording.encoding.playback_timing
    recording.encoding.nominal_rate_source recording.encoding.frame_duplication
    recording.encoding.b_frames recording.encoding.final_frame_duration
    recording.health.progress_monitor recording.health.stall_action
    recording.diagnostics.retention recording.diagnostics.failure_output
    recording.validation.argument_policy recording.validation.argument_conflict_policy
    recording.validation.duplicate_scalar_options recording.validation.filter_policy
    recording.validation.filter_graph_policy recording.validation.transform_parameters
    recording.validation.supported_filters recording.validation.encoder_probe
    recording.validation.closure
    diagnostics.transport_summary diagnostics.transport_summary_status
    diagnostics.warning_grouping diagnostics.diagnostic_codes
    preview.allow_session_disabled_camera preview.failure_scope preview.stop_action
    preview.control_loss_action preview.setting_change preview.capacity_frames
    preview.buffer_lifetime preview.session_preview preview.viewer_attachment
    preview.busy_action preview.timing preview.drive_external_pulses
    preview.pulse_frequency preview.frame_selection preview.color_conversion
    preview.conversion_implementation preview.brightness_scaling
    preview.manual_outside_session preview.session_preview_gates_nothing
    preview.stop_before_setup
    preview.window_presentation
    """.split()
)

_FIXED_POLICY: dict[str, object] = {
    "cameras.roles": list(CAMERA_NAMES),
    "cameras.prepared_high_depth_alignment": "msb",
    "cameras.post_cutoff_retrieval": "terminal_off_then_bounded_drain",
    "workers.capture_wait": "frame_command_or_deadline",
    "recording.frame_log.capture_completion": "single_end_marker_after_drain_with_independent_stop_and_pulse_evidence",
    "recording.empty_video_result": "explicit_content_presence_and_closure",
}


def _load_pair(root: Path) -> LoadedPair:
    pair = load_pair(
        root / "config/backends/acquisition_config.toml",
        root / "contracts/policy/acquisition_policy.toml",
        allowed_config_keys=_CONFIG_KEYS,
        allowed_policy_keys=_POLICY_KEYS,
        expected_policy=_FIXED_POLICY,
    )
    if pair.policy_version != POLICY_VERSION:
        raise ConfigurationError(
            f"acquisition policy_version must be {POLICY_VERSION}, got {pair.policy_version}"
        )
    if policy_digest(pair.policy) != _POLICY_SHA256:
        raise ConfigurationError(
            f"acquisition fixed-policy declarations differ from policy version {POLICY_VERSION}"
        )
    _validate_operator_structure(pair.config)
    return pair


def _validate_operator_structure(config: Mapping[str, Any]) -> None:
    cameras = config.get("cameras")
    if not isinstance(cameras, dict):
        raise ConfigurationError("acquisition config requires [cameras] tables")
    unexpected = cameras.keys() - set(CAMERA_NAMES)
    if unexpected:
        raise ConfigurationError(
            f"unknown camera roles in acquisition config: {sorted(unexpected)}"
        )
    accepted_transport = {"DeviceLinkThroughputLimitMode", "DeviceLinkThroughputLimit"}
    for role in CAMERA_NAMES:
        camera = cameras.get(role)
        if not isinstance(camera, dict):
            raise ConfigurationError(f"cameras.{role} table is required")
        transport = camera.get("transport", {})
        if not isinstance(transport, dict):
            raise ConfigurationError(f"cameras.{role}.transport must be a table")
        unknown_transport = transport.keys() - accepted_transport
        if unknown_transport:
            raise ConfigurationError(
                f"unsupported cameras.{role}.transport keys: {sorted(unknown_transport)}"
            )
    rpc = config.get("rpc")
    if (
        not isinstance(rpc, dict)
        or type(rpc.get("port")) is not int
        or not 1 <= rpc["port"] <= 65535
    ):
        raise ConfigurationError("rpc.port must be an integer in 1..65535")
