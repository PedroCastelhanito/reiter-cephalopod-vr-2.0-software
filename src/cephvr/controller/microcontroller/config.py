"""Pure controller-owned Microcontroller defaults and fixed policy (A11/E14)."""

from decimal import Decimal
from pathlib import Path

from cephvr.acquisition.v1 import runtime_pb2
from cephvr.shared.config import (
    ConfigurationError,
    LoadedPair,
    load_pair,
    policy_digest,
)

_POLICY_SHA256 = "b343c4b860f27c77843cb846b5d293fb3e2107b5a5598aef1051bffd99b1051f"

_CONFIG_KEYS = frozenset(
    [
        "microcontroller.baud_rate",
        "microcontroller.ack_timeout_ms",
        "microcontroller.stop_completion_margin_ms",
        "microcontroller.keepalive_interval_s",
        "microcontroller.communication_timeout_s",
        "microcontroller.port",
        "microcontroller.trial_state_pin",
        "microcontroller.trial_state_enabled",
        "microcontroller.projector_flip_pin",
        "microcontroller.projector_flip_enabled",
    ]
)
_EXPECTED: dict[str, object] = {
    "microcontroller.firmware_target_scope": "rig_board_first",
    "microcontroller.firmware_installation": "explicit_configuration_upload",
    "microcontroller.firmware_upload_tool": "arduino_cli",
    "microcontroller.firmware_upload_board": "arduino:avr:uno",
    "microcontroller.firmware_upload_image": "intel_hex_application",
    "microcontroller.firmware_upload_source": "arduino_sketch_or_compiled_image",
    "microcontroller.firmware_source_max_bytes": 8388608,
    "microcontroller.firmware_source_max_entries": 256,
    "microcontroller.firmware_upload_verify": True,
    "microcontroller.firmware_upload_cleanup_reserve_ns": 2000000000,
    "microcontroller.boot_behavior": "outputs_off_require_configuration",
    "microcontroller.command_format": "newline_ascii",
    "microcontroller.acknowledgement": "after_application_with_state",
    "microcontroller.argument_style": "named_fields",
    "microcontroller.output_field_names": "camera_roles",
    "microcontroller.text_field_limits": "message_bound_only",
    "microcontroller.field_values": "tokens_and_numbers",
    "microcontroller.request_ids": "connection_id_counter",
    "microcontroller.request_id_format": "combined_field",
    "microcontroller.error_code_format": "symbolic",
    "microcontroller.unmatched_reply": "discard_keep_deadline",
    "microcontroller.port_resolution": "configured_only",
    "microcontroller.reconnect_preparation": "outputs_off_fresh_configuration",
    "microcontroller.startup_readiness": "bounded_read_only_probes",
    "microcontroller.connection_reset": "no_deliberate_extra_reset",
    "microcontroller.stop_priority": "before_unsent_requests",
    "microcontroller.boundary_scheduling": "reserve_before_scheduled_commands",
    "microcontroller.trial_boundary_timing": "host_dispatch_at_trial_boundaries",
    "microcontroller.stop_budget_validation": "outstanding_request_off_camera_and_report",
    "microcontroller.trial_boundary_commands": "grouped_active_outputs",
    "microcontroller.first_pulse": "immediate_on_application",
    "microcontroller.stop_behavior": "immediate_inactive",
    "microcontroller.pulse_polarity": "active_high",
    "microcontroller.inactive_level": "low",
    "microcontroller.protocol_compatibility": "exact_version",
    "microcontroller.protocol_version": 3,
    "microcontroller.capability_source": "firmware",
    "microcontroller.capability_query": "CAPS",
    "microcontroller.capability_reply": "single_bounded_reply",
    "microcontroller.capability_refresh": "connection_and_setup",
    "microcontroller.pin_identifier_format": "firmware_token",
    "microcontroller.unknown_command_fields": "reject_command",
    "microcontroller.max_outstanding_requests": 1,
    "microcontroller.serial_channel": "protocol_only",
    "microcontroller.max_line_bytes": 512,
    "microcontroller.frequency_format": "decimal_hz",
    "microcontroller.frequency_resolution_hz": Decimal("0.1"),
    "microcontroller.configuration_handshake": "configure_apply_report",
    "microcontroller.configuration_record_owner": "host_requested_and_applied",
    "microcontroller.frequency_quantization": "nearest_achievable_report_applied",
    "microcontroller.frequency_adjustment": "warn_without_confirmation",
    "microcontroller.frequency_readback_precision": "preserve_reported_frequency",
    "microcontroller.configuration_update": "complete",
    "microcontroller.disabled_output_fields": "enabled_only",
    "microcontroller.configuration_while_running": "stop_apply_restore_running",
    "microcontroller.keepalive_reply": "compact_status",
    "microcontroller.status_reply": "state_and_applied_configuration",
    "microcontroller.pulse_counters": False,
    "microcontroller.diagnostic_edge_counts": "input_observed_output_generated",
    "microcontroller.watchdog_status_clear": "successful_configuration",
    "microcontroller.command_timeout_action": "report_without_retry",
    "microcontroller.pulse_generation": "microcontroller",
    "microcontroller.pulse_scheduler": "hardware_timer",
    "microcontroller.clock_source": "local",
    "microcontroller.duty_cycle": Decimal("0.5"),
    "microcontroller.communication_loss_action": "stop_pulses",
    "microcontroller.output_mapping": "per_camera",
}


def load_microcontroller_pair(root: Path) -> LoadedPair:
    pair = load_pair(
        root / "config/backends/microcontroller_config.toml",
        root / "contracts/policy/microcontroller_policy.toml",
        allowed_config_keys=_CONFIG_KEYS,
        allowed_policy_keys=frozenset(_EXPECTED),
        expected_policy=_EXPECTED,
    )
    if pair.policy_version != 1:
        raise ConfigurationError("Microcontroller policy_version must be 1")
    if policy_digest(pair.policy) != _POLICY_SHA256:
        raise ConfigurationError(
            "Microcontroller fixed-policy declarations differ from version 1"
        )
    return pair


def load_serial_policies(root: Path) -> runtime_pb2.AcquisitionFilePolicies:
    values = load_microcontroller_pair(root).config["microcontroller"]
    result = runtime_pb2.AcquisitionFilePolicies(contract_version=1)
    fields = {
        "serial_baud_rate": ("baud_rate", 1),
        "serial_ack_timeout_ns": ("ack_timeout_ms", 1_000_000),
        "serial_keepalive_interval_ns": ("keepalive_interval_s", 1_000_000_000),
        "serial_communication_timeout_ns": ("communication_timeout_s", 1_000_000_000),
        "serial_stop_completion_margin_ns": ("stop_completion_margin_ms", 1_000_000),
    }
    for field, (key, scale) in fields.items():
        if key not in values:
            raise ConfigurationError(f"microcontroller.{key} is required")
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            raise ConfigurationError(f"microcontroller.{key} must be a positive number")
        resolved = Decimal(value) * scale
        if (
            resolved <= 0
            or resolved != resolved.to_integral_value()
            or resolved >= 1 << 63
        ):
            raise ConfigurationError(
                f"microcontroller.{key} is outside exact positive bounds"
            )
        setattr(result, field, int(resolved))
    if result.serial_baud_rate >= 1 << 32:
        raise ConfigurationError("Microcontroller baud rate is outside uint32")
    if result.serial_keepalive_interval_ns >= result.serial_communication_timeout_ns:
        raise ConfigurationError(
            "microcontroller keepalive must be shorter than communication timeout"
        )
    if (
        result.serial_communication_timeout_ns % 1_000_000
        or result.serial_communication_timeout_ns // 1_000_000 >= 1 << 32
    ):
        raise ConfigurationError(
            "Microcontroller watchdog must be an exact uint32 millisecond value"
        )
    return result
