"""E14 acquisition file schema and fixed policy-version binding."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from cephvr.shared.config import ConfigurationError, LoadedPair, load_pair

POLICY_VERSION = 11
CONTRACT_VERSION = 1
_POLICY_SHA256 = "912f0daa25b278df03b5e59ad06fdb86eeaa512515b0a7b6415b483a39caa342"

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
    microcontroller.port microcontroller.baud_rate microcontroller.ack_timeout_ms
    microcontroller.stop_completion_margin_ms microcontroller.keepalive_interval_s
    microcontroller.communication_timeout_s
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
    cameras.transport_tuning cameras.transport_settings_source
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
    microcontroller.firmware_target_scope microcontroller.firmware_installation
    microcontroller.boot_behavior microcontroller.command_format
    microcontroller.acknowledgement microcontroller.argument_style
    microcontroller.output_field_names microcontroller.text_field_limits
    microcontroller.field_values microcontroller.request_ids
    microcontroller.request_id_format microcontroller.error_code_format
    microcontroller.unmatched_reply microcontroller.port_resolution
    microcontroller.reconnect_preparation microcontroller.startup_readiness
    microcontroller.connection_reset microcontroller.stop_priority
    microcontroller.boundary_scheduling microcontroller.trial_boundary_timing
    microcontroller.stop_budget_validation microcontroller.trial_boundary_commands
    microcontroller.first_pulse microcontroller.stop_behavior microcontroller.pulse_polarity
    microcontroller.inactive_level microcontroller.protocol_compatibility
    microcontroller.protocol_version microcontroller.capability_source
    microcontroller.capability_query microcontroller.capability_reply
    microcontroller.capability_refresh microcontroller.pin_identifier_format
    microcontroller.unknown_command_fields microcontroller.max_outstanding_requests
    microcontroller.serial_channel microcontroller.max_line_bytes
    microcontroller.frequency_format microcontroller.frequency_resolution_hz
    microcontroller.configuration_handshake microcontroller.configuration_record_owner
    microcontroller.frequency_quantization microcontroller.frequency_adjustment
    microcontroller.frequency_readback_precision microcontroller.configuration_update
    microcontroller.disabled_output_fields microcontroller.configuration_while_running
    microcontroller.keepalive_reply microcontroller.status_reply
    microcontroller.pulse_counters microcontroller.watchdog_status_clear
    microcontroller.command_timeout_action microcontroller.pulse_generation
    microcontroller.pulse_scheduler microcontroller.clock_source
    microcontroller.duty_cycle microcontroller.communication_loss_action
    microcontroller.output_mapping
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
    """.split()
)

_FIXED_POLICY: dict[str, object] = {
    "microcontroller.protocol_version": 1,
    "microcontroller.max_outstanding_requests": 1,
    "microcontroller.max_line_bytes": 512,
    "microcontroller.frequency_resolution_hz": Decimal("0.1"),
    "microcontroller.trial_boundary_timing": "host_dispatch_at_trial_boundaries",
    "microcontroller.stop_budget_validation": "outstanding_request_off_camera_and_report",
    "microcontroller.command_timeout_action": "report_without_retry",
    "microcontroller.pulse_generation": "microcontroller",
    "microcontroller.output_mapping": "per_camera",
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
    policy = dict(pair.policy)
    policy.pop("policy_version", None)
    encoded = json.dumps(
        policy,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: (
            format(item, "f") if isinstance(item, Decimal) else str(item)
        ),
    ).encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != _POLICY_SHA256:
        raise ConfigurationError(
            "acquisition fixed-policy declarations differ from policy version 11"
        )
    _validate_operator_structure(pair.config)
    return pair


def _validate_operator_structure(config: Mapping[str, Any]) -> None:
    cameras = config.get("cameras")
    if not isinstance(cameras, dict):
        raise ConfigurationError("acquisition config requires [cameras] tables")
    unexpected = cameras.keys() - {"behavioral", "tracking"}
    if unexpected:
        raise ConfigurationError(
            f"unknown camera roles in acquisition config: {sorted(unexpected)}"
        )
    accepted_transport = {"DeviceLinkThroughputLimitMode", "DeviceLinkThroughputLimit"}
    for role in ("behavioral", "tracking"):
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
