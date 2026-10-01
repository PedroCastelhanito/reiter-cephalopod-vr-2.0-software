"""Controller-selected E06 scopes require exact retained worker isolation proof."""

from __future__ import annotations

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb

from .state import State


def validate_incident(state: State, request: wire.IncidentScopeRequest) -> bool:
    incident = request.incident
    setup = state.setup
    previous = state.incident_revisions.get(incident.incident_id, 0)
    ready = next(
        (
            report.ready
            for (kind, _), report in state.reports.items()
            if kind == "ready"
            and report.ready.context.work.WhichOneof("work") == "session"
        ),
        None,
    )
    if (
        setup is None
        or ready is None
        or request.command.work != setup.command.work
        or incident.work != setup.command.work
        or not incident.incident_id
        or incident.revision != previous + 1
        or (previous == 0 and len(state.incident_revisions) >= 64)
    ):
        raise ValueError("incident session/revision is not current")
    functions = {item.resource_id: item for item in ready.prepared_functions}
    affected = set(incident.affected_resources)
    if (
        not affected
        or len(affected) != len(incident.affected_resources)
        or not affected <= functions.keys()
    ):
        raise ValueError("incident contains unknown or repeated prepared resources")
    if incident.disposition in {
        pb.RUNTIME_INCIDENT_DISPOSITION_ABORT_SELECTED,
        pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP,
    }:
        return False
    if incident.disposition != pb.RUNTIME_INCIDENT_DISPOSITION_CONTINUE_SELECTED:
        raise ValueError("incident disposition is not actionable")
    heartbeat = state.worker_heartbeat
    if (
        not incident.continuation_available
        or heartbeat is None
        or not heartbeat.HasField("active_error")
        or incident.first_observed_monotonic_ns <= 0
        or heartbeat.sent_monotonic_ns < incident.last_observed_monotonic_ns
    ):
        return False
    error = heartbeat.active_error
    if not error.HasField("isolation") or (
        error.error_id not in incident.error_ids
        and error.incident_episode_id != incident.incident_id
    ):
        return False
    proof = error.isolation
    if (
        not proof.leases_released_or_quarantined
        or proof.verified_monotonic_ns < incident.last_observed_monotonic_ns
        or not affected <= set(proof.affected_resource_ids)
    ):
        return False
    closed = set(proof.fenced_resource_ids)
    if proof.feedback_hold_active:
        closed.update(proof.feedback_hold_resource_ids)
    closure = {
        key
        for affected_id in affected
        for key in functions[affected_id].affected_closure_resource_ids
    }
    if not closure <= functions.keys() or not closure <= closed:
        return False
    if any(functions[key].essential_to_stimulus_control for key in closure):
        return False
    for key in closure:
        function = functions[key]
        if heartbeat.source not in function.authorized_reporters:
            return False
        if function.feedback_hold_required_on_loss and (
            not proof.feedback_hold_active
            or key not in proof.feedback_hold_resource_ids
        ):
            return False
    continuing = {
        item.resource_id
        for item in heartbeat.continuing_functions
        if item.observed_monotonic_ns >= incident.last_observed_monotonic_ns
        and all(
            item.HasField(field) and getattr(item, field)
            for field in (
                "functioning",
                "schedule_valid",
                "host_clock_valid",
                "control_path_valid",
            )
        )
    }
    return {
        key
        for key, item in functions.items()
        if item.essential_to_stimulus_control and key not in closure
    } <= continuing
