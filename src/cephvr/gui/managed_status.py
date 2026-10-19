"""Bounded projections of authoritative controller snapshots for the GUI."""

from __future__ import annotations

import re
from time import perf_counter_ns

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.view import DashboardView, Phase, PreviewView

_PHASES = {
    pb.SESSION_PHASE_CONFIGURATION: Phase.CONFIGURATION,
    pb.SESSION_PHASE_SETTING_UP: Phase.SETTING_UP,
    pb.SESSION_PHASE_READY: Phase.READY,
    pb.SESSION_PHASE_STARTING: Phase.STARTING,
    pb.SESSION_PHASE_RUNNING: Phase.RUNNING,
    pb.SESSION_PHASE_FINALIZING: Phase.FINALIZING,
    pb.SESSION_PHASE_ENDED: Phase.ENDED,
}
_BACKENDS = {
    "acquisition": "Cameras",
    "visual_stimulus": "Visual stimulus",
    "tracking": "Tracking",
}


def dashboard_view(
    state: pb.Snapshot,
    client_id: str,
    previews: tuple[PreviewView, ...],
    *,
    configuration_wired: bool = False,
) -> DashboardView:
    """Project only facts represented in the current authoritative snapshot."""
    phase = _PHASES.get(state.session.phase, Phase.CONFIGURATION)
    statuses = {label: "Unavailable" for label in _BACKENDS.values()}
    for participant in state.participants:
        label = _BACKENDS.get(participant.process.role)
        if label is not None:
            ready = (
                participant.connected
                and participant.process_running
                and participant.ready.required_checks_passed
                and participant.ready.configuration_revision
                == state.configuration.revision
            )
            statuses[label] = (
                "Ready"
                if ready
                else participant.health
                if participant.process_running or participant.connected
                else "Not running"
            )
    now = perf_counter_ns()
    elapsed = None
    remaining = None
    trial_duration = None
    if state.trial.HasField("start_monotonic_ns") and state.trial.HasField(
        "scheduled_end_monotonic_ns"
    ):
        trial_duration = (
            max(
                0,
                state.trial.scheduled_end_monotonic_ns - state.trial.start_monotonic_ns,
            )
            / 1_000_000_000
        )
    if state.trial.HasField("start_monotonic_ns"):
        end_ns = (
            state.trial.actual_end_monotonic_ns
            if state.trial.HasField("actual_end_monotonic_ns")
            else now
        )
        elapsed = max(0, end_ns - state.trial.start_monotonic_ns) / 1_000_000_000
    if state.trial.HasField("scheduled_end_monotonic_ns") and phase in {
        Phase.STARTING,
        Phase.RUNNING,
    }:
        remaining = max(0, state.trial.scheduled_end_monotonic_ns - now) / 1_000_000_000
    trial_index = (
        state.trial.context.trial_number if state.trial.HasField("context") else 0
    )
    trial_count = state.session.trial_count
    if not trial_count and state.HasField("configuration_values"):
        trial_count = len(state.configuration_values.current.trials)
    output = "No output closure evidence"
    closures = [
        result.closure
        for participant in state.participants
        for result in participant.outputs
    ]
    if closures:
        if pb.OUTPUT_CLOSURE_FAILED in closures:
            output = "Failed"
        elif pb.OUTPUT_CLOSURE_UNCONFIRMED in closures:
            output = "Unconfirmed"
        elif pb.OUTPUT_CLOSURE_CLOSING in closures:
            output = "Closing"
        elif all(value == pb.OUTPUT_CLOSURE_CLOSED for value in closures):
            output = "Last reported outputs closed"
        elif pb.OUTPUT_CLOSURE_OPEN in closures:
            output = "Last reported outputs open"
    reservation_status = "Not started"
    if state.HasField("reservation"):
        reservation = state.reservation
        reservation_status = (
            "Recovery required"
            if reservation.recovery_required
            else "Released"
            if reservation.released
            else "Reserved"
            if reservation.ready_for_outputs
            else "Preparing"
        )
    metadata_states = {item.state for item in state.metadata}
    metadata = (
        "Failed"
        if pb.METADATA_PERSISTENCE_FAILED in metadata_states
        else "Unconfirmed"
        if pb.METADATA_PERSISTENCE_UNCONFIRMED in metadata_states
        else "Pending"
        if pb.METADATA_PERSISTENCE_PENDING in metadata_states
        else "Synced"
        if pb.METADATA_PERSISTENCE_SYNCED in metadata_states
        else "Not started"
    )
    outcome = "—"
    if state.session.HasField("outcome"):
        outcome = (
            pb.SessionOutcome.Name(state.session.outcome)
            .removeprefix("SESSION_OUTCOME_")
            .title()
        )
    elif state.trial.HasField("outcome"):
        outcome = (
            pb.TrialOutcome.Name(state.trial.outcome)
            .removeprefix("TRIAL_OUTCOME_")
            .title()
        )
    return DashboardView(
        phase=phase,
        connected=True,
        has_control=state.control.holder_client_id == client_id,
        configuration_wired=configuration_wired,
        trial_index=trial_index,
        trial_count=trial_count,
        elapsed_s=elapsed,
        remaining_s=remaining,
        trial_duration_s=trial_duration,
        outcome=outcome,
        camera_status=statuses["Cameras"],
        stimulus_status=statuses["Visual stimulus"],
        tracking_status=statuses["Tracking"],
        output_status=output,
        reservation_status=reservation_status,
        metadata_status=metadata,
        previews=previews,
    )


def has_retained_review(state: pb.Snapshot) -> bool:
    """Whether important retained evidence should block the reconnect flow."""
    return bool(
        state.errors
        or state.runtime_incidents
        or state.prompts
        or any(_important_recovery(item) for item in state.recoveries)
        or any(
            not _routine_configuration_warning(state, item) for item in state.warnings
        )
        or any(
            operation.HasField("failure")
            or (
                operation.complete
                and (not operation.HasField("succeeded") or not operation.succeeded)
            )
            for operation in state.operations
        )
    )


def has_retained_history(state: pb.Snapshot) -> bool:
    """Whether any retained event is available for optional history review."""
    return bool(
        state.retained_truncated
        or state.errors
        or state.recoveries
        or state.runtime_incidents
        or state.prompts
        or state.warnings
        or state.operations
    )


def _important_recovery(recovery: pb.RecoveryState) -> bool:
    """Keep active, failed, unknown, and internally inconsistent recoveries visible."""
    return not (
        recovery.outcome == pb.RECOVERY_OUTCOME_COMPLETED
        and recovery.HasField("completion_monotonic_ns")
        and recovery.completion_monotonic_ns > 0
        and not recovery.HasField("failure")
    )


def _routine_configuration_warning(state: pb.Snapshot, warning: pb.Warning) -> bool:
    """Match only the controller's exact nonfatal completed-validation warning."""
    for validation in state.configuration.edit_validation:
        if (
            not validation.completed
            or not validation.valid
            or not validation.issues
            or validation.configuration_revision != state.configuration.revision
        ):
            continue
        expected = pb.Warning(
            warning_id=(
                f"configuration:{state.configuration.revision}:"
                f"{validation.component}:nonfatal"
            ),
            component=validation.component,
            message="Configuration has nonfatal preparation warnings",
        )
        expected.issues.extend(validation.issues)
        if warning == expected:
            return True
    return False


def retained_ack_required_for(
    state: pb.Snapshot,
    identity: tuple[int, str],
    acknowledged_identity: tuple[int, str] | None,
) -> bool:
    """Require review of retained incidents once per synchronized connection."""
    return has_retained_review(state) and acknowledged_identity != identity


def action_label(action: str) -> str:
    """Give command keys a readable label without losing unknown action names."""
    if action == "set_spikeglx_enabled":
        return "SpikeGLX pairing"
    known = {
        "ExecuteCameraCommand": "Camera",
        "ExecuteMicrocontrollerCommand": "Microcontroller",
        "StartupRecovery": "Recovery",
        "StartSession": "Session",
        "InitializeDisplay": "Visual stimulus",
        "CancelSetup": "Setup",
        "ShutdownApplication": "Shutdown",
        "SaveConfigurationHistory": "Shutdown",
        "setup": "Setup",
        "start": "Start",
        "stop": "Stop",
        "cancel_setup": "Cancel setup",
        "calibration": "Calibration",
        "respond_prompt": "Respond to prompt",
        "spikeglx_inventory_update": "SpikeGLX inventory update",
        "spikeglx_connection": "SpikeGLX connection",
        "get_spikeglx_inventory": "Read SpikeGLX inventory",
        "mcu": "MCU command",
        "mcu_upload": "MCU upload",
        "test_cameras": "Camera test",
        "save_camera_settings": "Save camera settings",
        "save_mcu_pins": "Save MCU pins",
        "save_configuration_history": "Save configuration",
    }
    if action in known:
        return known[action]
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", action).replace("_", " ")
    words = words.strip()
    return words[:1].upper() + words[1:] if words else "Command"


def retained_summary(state: pb.Snapshot) -> str:
    """Show all actionable retained state and collapse routine successes."""
    groups: list[list[str]] = []
    lines: list[str] = []
    if state.retained_truncated:
        lines.append("Older resolved entries are no longer retained.")

    # Keep every current incident, prompt, recovery, and warning visible even when
    # the retained operation list is full of routine completed work.
    if state.errors:
        group = ["Retained errors:"]
        groups.append(group)
    else:
        group = []
    for error in state.errors:
        detail = error.failure.message if error.HasField("failure") else "Error"
        group.append(f"  • {detail}")
    if state.recoveries:
        group = ["Recoveries:"]
        groups.append(group)
    for recovery in state.recoveries:
        group.append(f"  • {recovery.progress or action_label(recovery.action)}")
    if state.runtime_incidents:
        group = ["Incidents:"]
        groups.append(group)
    for incident in state.runtime_incidents:
        group.append(f"  • {incident.consequence}")
    if state.prompts:
        group = ["Pending choices:"]
        groups.append(group)
    for prompt in state.prompts:
        choices = ", ".join(prompt.permitted_choices)
        group.append(f"  • {prompt.explanation} ({choices})")
    if state.warnings:
        group = ["Warnings:"]
        groups.append(group)
    for warning in state.warnings:
        group.append(f"  • {warning.message}")

    completed = 0
    actionable: list[str] = []
    for operation in state.operations:
        result = (
            "in progress"
            if not operation.complete
            else "completed"
            if operation.HasField("succeeded") and operation.succeeded
            else "failed"
            if operation.HasField("succeeded")
            else "completion unknown"
        )
        if result == "completed":
            completed += 1
            continue
        description = f"{action_label(operation.command)} — {result}"
        if operation.progress:
            description += f"; {operation.progress}"
        if operation.HasField("failure"):
            description += f"; {operation.failure.message}"
        actionable.append(f"  • {description}")
    if actionable:
        groups.append(["Operations needing attention:", *actionable])
    if completed:
        groups.append([f"Completed operations: {completed}"])
    lines.extend("\n".join(section) for section in groups)
    if not lines:
        lines.append("No controller incidents or warnings are currently retained.")
    return "\n\n".join(lines)


def retained_details(state: pb.Snapshot, *, routine_limit: int = 40) -> str:
    """Expose exact retained diagnostics, bounding only routine success history."""
    lines: list[str] = []
    if state.HasField("retained_since_monotonic_ns"):
        lines.append(
            "Retained since controller monotonic ns: "
            f"{state.retained_since_monotonic_ns}"
        )
    for error in state.errors:
        failure = error.failure.message if error.HasField("failure") else "Error"
        code = f" ({error.failure.code})" if error.HasField("failure") else ""
        lines.append(f"Error {error.error_id}{code}: {failure}")
    for recovery in state.recoveries:
        lines.append(
            f"Recovery {recovery.attempt_id} ({recovery.action}): {recovery.progress}; "
            "outcome: "
            + pb.RecoveryOutcome.Name(recovery.outcome)
            .removeprefix("RECOVERY_OUTCOME_")
            .lower()
            + (
                f"; failure: {recovery.failure.message}"
                if recovery.HasField("failure")
                else ""
            )
        )
    for incident in state.runtime_incidents:
        lines.append(f"Incident {incident.incident_id}: {incident.consequence}")
    for prompt in state.prompts:
        lines.append(
            f"Prompt {prompt.prompt_id}: {prompt.explanation}; "
            f"permitted choices: {', '.join(prompt.permitted_choices)}"
        )
    for warning in state.warnings:
        lines.append(f"Warning {warning.warning_id}: {warning.message}")
    routine = [
        operation
        for operation in state.operations
        if operation.complete
        and operation.HasField("succeeded")
        and operation.succeeded
    ]
    actionable = [
        operation
        for operation in state.operations
        if not (
            operation.complete
            and operation.HasField("succeeded")
            and operation.succeeded
        )
    ]
    for operation in actionable + routine[:routine_limit]:
        outcome = (
            "in progress"
            if not operation.complete
            else "succeeded"
            if operation.HasField("succeeded") and operation.succeeded
            else "failed"
            if operation.HasField("succeeded")
            else "completion unknown"
        )
        failure = ""
        if operation.HasField("failure"):
            failure = f"; failure: {operation.failure.message}" + (
                f" (code: {operation.failure.code})" if operation.failure.code else ""
            )
        lines.append(
            f"Command {operation.command} [{operation.context.command_id}]: "
            + outcome
            + (f"; progress: {operation.progress}" if operation.progress else "")
            + failure
        )
    omitted = len(routine) - routine_limit
    if omitted > 0:
        lines.append(f"{omitted} additional completed operation details omitted.")
    if state.retained_truncated:
        lines.append("Older resolved entries are no longer retained.")
    return "\n".join(lines) or "No additional technical details are retained."
