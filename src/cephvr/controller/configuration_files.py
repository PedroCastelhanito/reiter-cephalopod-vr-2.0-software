"""Accepted E14 controller/supervisor file schemas and fixed-policy validation."""

from pathlib import Path

from cephvr.shared.clock import HOST_CLOCK_ID
from cephvr.shared.config import LoadedPair, load_pair

_EXPERIMENT_CONFIG_KEYS = frozenset(
    {
        "assets.asset_root",
        "rpc.port",
        "rpc.max_message_bytes",
        "control.max_retained_incidents",
        "control.command_record_retention_after_finalization_s",
        "event_queue.max_pending_events",
        "event_queue.max_pending_payload_bytes",
        "timeouts.recovery_s",
        "timeouts.setup.initial_s",
        "timeouts.setup_cancel.initial_s",
        "timeouts.trial_ready.initial_s",
        "timeouts.trial_finished.initial_s",
        "timeouts.supervisor_registration.initial_s",
        "configuration_validation.timeout_s",
        "configuration_history.save_timeout_s",
        "storage.space_query_timeout_s",
        "storage.low_space_warning_bytes",
        "protocol.default_intertrial_gap_s",
        "timing.start_lead_time_ms",
        "timing.controller_release_cutoff_before_start_ms",
        "timing.backend_release_cutoff_before_start_ms",
        "timing.start_lateness_tolerance_ms",
        "timing.stop_report_timeout_ms",
        "metadata.max_pending_operations",
        "metadata.max_pending_bytes",
        "metadata.completion_timeout_s",
    }
)

_EXPERIMENT_POLICY_KEYS = frozenset(
    {
        "gpu_placement.render_projection_tracking",
        "gpu_placement.video_encoding",
        "gpu_placement.operator_display_gui",
        "gpu_placement.automatic_adapter_fallback",
        "state_delivery.configuration_values",
        "protocol.minimum_trial_duration_s",
        "recording_interval.interruption_cutoff",
        "recording_interval.file_integrity_validation",
        "host_clock.clock_id",
        "host_clock.python_api",
        "host_clock.origin",
        "host_clock.unit",
        "runtime_incidents.continuable_failure",
        "runtime_incidents.while_pending",
        "runtime_incidents.blocking_failure",
        "runtime_incidents.continuation_scope",
        "control_lease.liveness",
        "control_lease.disconnection",
        "control_lease.reconnection",
        "control_lease.cli",
        "metadata.writer_owner",
        "metadata.output_reservation_owner",
        "metadata.completion",
        "metadata.uncertain_write",
        "configuration_validation.commit",
        "configuration_validation.unavailable_or_timeout",
        "configuration_validation.invalid_values",
        "configuration_validation.late_result",
        "configuration_validation.history",
        "recovery.missed_deadline",
        "incident_history.reconnect_warnings",
        "trial_command_delivery.max_transport_retries",
        "defaults.engineering_limits",
        "defaults.scientific_and_rig_inputs",
    }
)

_SUPERVISOR_CONFIG_KEYS = frozenset(
    {
        "rpc.port",
        "health.heartbeat_interval_s",
        "health.silence_timeout_s",
        "emergency_report.completion_timeout_s",
        "shutdown.graceful_process_exit_s",
        "shutdown.terminate_process_exit_s",
        "shutdown.application_shutdown_backstop_s",
    }
)

_SUPERVISOR_POLICY_KEYS = frozenset(
    {
        "processes.launch_policy",
        "processes.registration",
        "processes.windows.contained_backends",
        "processes.windows.containment",
        "processes.windows.kill_on_job_close",
        "processes.windows.application_job_owner",
        "processes.windows.application_job_kill_on_close",
        "processes.windows.application_job_handle",
        "processes.windows.application_replacement",
        "processes.windows.authority_loss_shutdown",
        "health.controller_monitor",
        "health.supervisor_monitor",
        "health.coordinator_authority_watch",
        "health.worker_health",
        "health.silence_recovery",
        "health.controller_loss_action",
        "storage.normal_metadata_writer",
        "storage.output_reservation",
        "storage.controller_loss",
        "status_delivery.mode",
        "status_delivery.pending",
        "status_delivery.revision_gaps",
        "gui_process.automatic_relaunch",
        "recovery.backend_reuse",
        "recovery.actions",
        "recovery.authority",
        "recovery.stuck_process",
        "shutdown.application_backstop",
    }
)


def load_control_files(root: Path) -> tuple[LoadedPair, LoadedPair]:
    experiment = load_pair(
        root / "config/backends/experiment_config.toml",
        root / "contracts/policy/experiment_policy.toml",
        allowed_config_keys=_EXPERIMENT_CONFIG_KEYS,
        allowed_policy_keys=_EXPERIMENT_POLICY_KEYS,
        expected_policy={
            "gpu_placement.render_projection_tracking": "nvidia_geforce_rtx_5060_ti",
            "gpu_placement.video_encoding": "nvidia_geforce_rtx_2080_ti",
            "gpu_placement.operator_display_gui": "amd_radeon_ryzen_9_9950x_integrated",
            "gpu_placement.automatic_adapter_fallback": False,
            "state_delivery.configuration_values": (
                "snapshot_and_stream_revision_change"
            ),
            "protocol.minimum_trial_duration_s": 60,
            "recording_interval.interruption_cutoff": "producer_local_admission_stop",
            "recording_interval.file_integrity_validation": "external_post_hoc",
            "host_clock.clock_id": HOST_CLOCK_ID,
            "host_clock.python_api": "time.perf_counter_ns",
            "host_clock.origin": "system_wide_unshifted",
            "host_clock.unit": "ns",
            "runtime_incidents.continuable_failure": "operator_continue_or_abort",
            "runtime_incidents.while_pending": "continue_original_timeline",
            "runtime_incidents.blocking_failure": "automatic_stop_and_inform",
            "runtime_incidents.continuation_scope": "isolated_function_loss_no_restart_or_protocol_change",
            "control_lease.liveness": "exact_live_watch_subscription",
            "control_lease.disconnection": "release_invalidate_generation",
            "control_lease.reconnection": "observer_automatic_unheld_claim_explicit_takeover",
            "control_lease.cli": "acquire_execute_release",
            "trial_command_delivery.max_transport_retries": 1,
            "metadata.writer_owner": "controller_serialized_background_thread",
            "metadata.output_reservation_owner": "controller_local_lock_and_marker",
            "metadata.completion": "local_event_after_sync",
            "metadata.uncertain_write": "no_retry_or_takeover",
            "configuration_validation.commit": "only_after_successful_current_validation",
            "configuration_validation.unavailable_or_timeout": "reject_warn_preserve_current",
            "configuration_validation.invalid_values": "reject_with_field_issues_preserve_current",
            "configuration_validation.late_result": "never_commit_after_expiry_or_state_change",
            "configuration_validation.history": "single_current_configuration_no_rollback",
            "recovery.missed_deadline": (
                "single_state_query_within_shared_recovery_budget"
            ),
            "incident_history.reconnect_warnings": "snapshot_retained_bounded_no_history_rpc",
            "defaults.engineering_limits": "configurable_workload_checked_starting_values",
            "defaults.scientific_and_rig_inputs": "explicit_no_fabricated_values",
        },
    )
    supervisor = load_pair(
        root / "config/backends/supervisor_config.toml",
        root / "contracts/policy/supervisor_policy.toml",
        allowed_config_keys=_SUPERVISOR_CONFIG_KEYS,
        allowed_policy_keys=_SUPERVISOR_POLICY_KEYS,
        expected_policy={
            "processes.launch_policy": "backend_owned_children",
            "processes.registration": "planned_then_confirmed",
            "processes.windows.contained_backends": [
                "acquisition",
                "visual_stimulus",
                "tracking",
            ],
            "processes.windows.containment": "job_objects",
            "processes.windows.kill_on_job_close": False,
            "processes.windows.application_job_owner": "persistent_launcher",
            "processes.windows.application_job_kill_on_close": True,
            "processes.windows.application_job_handle": "sole_noninherited_launcher_handle",
            "processes.windows.application_replacement": "terminal_confirmation_exact_owner_exit_receipt_then_guard",
            "processes.windows.authority_loss_shutdown": "automatic_bounded_graceful_then_application_job_termination",
            "health.controller_monitor": "supervisor_process_handle_and_heartbeat_silence",
            "health.supervisor_monitor": "controller_heartbeat_silence",
            "health.coordinator_authority_watch": "os_process_handles_controller_and_supervisor",
            "health.worker_health": "worker_to_coordinator_aggregated_in_coordinator_heartbeat",
            "health.silence_recovery": "none_silence_is_loss",
            "health.controller_loss_action": (
                "independent_idempotent_cleanup_then_application_shutdown"
            ),
            "storage.normal_metadata_writer": "controller",
            "storage.output_reservation": "controller",
            "storage.controller_loss": "emergency_report_no_normal_writer_takeover",
            "status_delivery.mode": "complete_view_on_change_and_reconnect",
            "status_delivery.pending": "coalesce_latest_bounded",
            "status_delivery.revision_gaps": "accept_newer_full_view",
            "gui_process.automatic_relaunch": "none_operator_relaunches_from_launcher",
            "recovery.backend_reuse": "full_application_restart_after_cleanup",
            "recovery.actions": ["retry_graceful_cleanup"],
            "recovery.authority": "controller_verified_control_lease_only",
            "recovery.stuck_process": "shutdown_application",
            "shutdown.application_backstop": "startup_only_setting_checked_at_setup",
        },
    )
    return experiment, supervisor
