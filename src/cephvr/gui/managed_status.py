"""Bounded projections of authoritative controller snapshots for the GUI."""

from __future__ import annotations

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
    """Whether the synchronized view contains entries requiring reconnect review."""
    return bool(
        state.errors
        or state.recoveries
        or state.runtime_incidents
        or state.prompts
        or state.warnings
    )


def retained_ack_required_for(
    state: pb.Snapshot,
    identity: tuple[int, str],
    acknowledged_identity: tuple[int, str] | None,
) -> bool:
    """Require review of retained incidents once per synchronized connection."""
    return has_retained_review(state) and acknowledged_identity != identity


def retained_summary(state: pb.Snapshot) -> str:
    """Show every unresolved item before a bounded operation-history excerpt."""
    lines: list[str] = []
    if state.retained_truncated:
        lines.append("Older resolved entries were evicted while disconnected.")

    # Keep every current incident, prompt, recovery, and warning visible even when
    # the retained operation list is full of routine completed work.
    for error in state.errors:
        identity = f" [{error.error_id}]" if error.error_id else ""
        detail = error.failure.message if error.HasField("failure") else "Error"
        lines.append(f"Error{identity}: {detail}")
    for recovery in state.recoveries:
        lines.append(f"Recovery: {recovery.progress or recovery.action}")
    for incident in state.runtime_incidents:
        lines.append(f"Incident: {incident.consequence}")
    for prompt in state.prompts:
        choices = ", ".join(prompt.permitted_choices)
        lines.append(
            f"Pending choice [{prompt.prompt_id}]: {prompt.explanation} [{choices}]"
        )
    for warning in state.warnings:
        lines.append(f"Warning: {warning.message}")

    operation_limit = 40
    for operation in state.operations[:operation_limit]:
        command_id = operation.context.command_id
        result = (
            "running"
            if not operation.complete
            else "succeeded"
            if operation.HasField("succeeded") and operation.succeeded
            else "failed"
            if operation.HasField("succeeded")
            else "completion unknown"
        )
        lines.append(
            f"Command {operation.command} [{command_id}]: {result}"
            + (f" · {operation.progress}" if operation.progress else "")
            + (
                f" · {operation.failure.message}"
                if operation.HasField("failure")
                else ""
            )
        )
    omitted_operations = max(0, len(state.operations) - operation_limit)
    if omitted_operations:
        lines.append(
            f"{omitted_operations} additional retained operation entries omitted from this view."
        )
    if not lines:
        lines.append("No controller incidents or warnings are currently retained.")
    return "\n".join(lines)
