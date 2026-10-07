"""T02/E08 exact state and authority checks before retained command admission."""

from __future__ import annotations

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.identity import require_uuid4
from cephvr.tracking.config.validation import validate_settings
from cephvr.tracking.transport.boundary import SAFETY, command_of
from cephvr.tracking.v1 import services_pb2 as tracking

from .state import Identity, State


def validate(
    identity: Identity, state: State, method: str, request: Message, now: int
) -> None:
    command = command_of(request)
    require_uuid4(command.command_id)
    if command.target != identity.backend or command.issuer not in (
        identity.controller,
        identity.supervisor,
    ):
        raise ValueError(
            "command target or issuer generation differs from registered identities"
        )
    if command.issuer == identity.supervisor and method not in SAFETY:
        raise ValueError("supervisor can issue only safety commands")
    if method == "BeginDiagnostic" and isinstance(
        request, tracking.TrackingDiagnosticCommand
    ):
        if (
            command.issuer != identity.controller
            or request.configuration_revision == 0
            or request.frames.buffer.configuration_revision
            != request.configuration_revision
            or request.frames.buffer.preview.controller != identity.controller
            or request.authorized_gui_viewer.role != "gui"
            or not request.authorized_gui_viewer.generation
        ):
            raise ValueError("diagnostic command scope or viewer authorization differs")
        return
    if method == "CloseDiagnostic" and isinstance(
        request, tracking.CloseTrackingDiagnosticCommand
    ):
        if command.issuer != identity.controller:
            raise ValueError("only controller can close a diagnostic")
        return
    if method == "SetupSession" and isinstance(request, wire.SetupSessionRequest):
        if state.setup is not None and (
            state.cleanup is None
            or not state.cleanup.trial_activity_stopped
            or not all(item.released for item in state.cleanup.resources)
            or any(
                item.closure == pb.OUTPUT_CLOSURE_UNCONFIRMED
                for item in state.cleanup.outputs
            )
        ):
            raise ValueError("prior preparation still owns resources")
        if (
            request.command.work.WhichOneof("work") != "session"
            or request.command.work.session != request.plan.context
            or request.plan.context.controller_generation
            != identity.controller.generation
        ):
            raise ValueError("Setup session/controller binding mismatch")
        require_uuid4(request.plan.context.session_id)
        if (
            request.settings.backend_name != "tracking"
            or not request.settings.enabled
            or not request.HasField("tracking_policies")
        ):
            raise ValueError(
                "Setup requires enabled Tracking and resolved file policies"
            )
        validate_settings(request.settings.tracking)
        return
    if method == "Shutdown" and state.setup is None:
        return
    if state.setup is None:
        raise ValueError("command requires retained Setup")
    session = (
        command.work.session
        if command.work.WhichOneof("work") == "session"
        else command.work.trial.session
    )
    if session != state.setup.plan.context:
        raise ValueError("command names another session generation")
    if isinstance(request, wire.IncidentScopeRequest):
        incident = request.incident
        previous = state.incident_revisions.get(incident.incident_id, 0)
        if (
            command.issuer != identity.controller
            or command.work != state.setup.command.work
            or incident.work != command.work
            or state.ready is None
            or not incident.incident_id
            or incident.revision != previous + 1
            or (previous == 0 and len(state.incident_revisions) >= 64)
            or list(incident.affected_resources) != ["tracking"]
            or incident.disposition
            not in (
                pb.RUNTIME_INCIDENT_DISPOSITION_ABORT_SELECTED,
                pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP,
                pb.RUNTIME_INCIDENT_DISPOSITION_CONTINUE_SELECTED,
            )
        ):
            raise ValueError(
                "incident authority, scope, revision or disposition is invalid"
            )
    if method in SAFETY:
        if command.work.WhichOneof("work") == "trial" and (
            state.trial is None or command.work.trial != state.trial.plan.context
        ):
            raise ValueError("safety command names another trial")
        return
    if isinstance(request, tracking.TrackingDataBinding):
        if (
            state.interrupted
            or request.preparation_generation
            != state.preparation.preparation_generation
            or request.configuration_revision != state.setup.plan.configuration_revision
        ):
            raise ValueError("source binding is stale or preparation is sealed")
        descriptor = request.frames.buffer
        if (
            descriptor.consumer != identity.process
            or request.frames.sync.target != identity.process
            or descriptor.session != session
            or descriptor.configuration_revision != request.configuration_revision
            or descriptor.camera != state.setup.settings.tracking.input_camera_role
        ):
            raise ValueError(
                "source attachment identity/layout scope differs from selected camera"
            )
        from cephvr.acquisition.v1.messages_pb2 import FRAME_BUFFER_KIND_TRACKING

        if descriptor.kind != FRAME_BUFFER_KIND_TRACKING:
            raise ValueError("Tracking requires its ordered acquisition ring")
        if command.parent_operation.command_id != state.setup.command.command_id:
            raise ValueError("source handoff has another Setup parent")
        payload = request.frames.SerializeToString(deterministic=True)
        if state.frames_digest is not None and state.frames_digest != payload:
            raise ValueError("conflicting source descriptor under preparation identity")
        if state.ready is not None and state.frames_digest != payload:
            raise ValueError("source preparation is sealed")
        return
    if state.ready is None or state.interrupted:
        raise ValueError("native preparation is not Ready")
    if isinstance(request, wire.PrepareTrialRequest):
        if state.trial is not None and state.finished is None:
            raise ValueError("previous trial is not Finished")
        if (
            request.configuration_revision != state.setup.plan.configuration_revision
            or request.plan.context != command.work.trial
            or request.plan.context.session != state.setup.plan.context
        ):
            raise ValueError("trial configuration/session differs from prepared Setup")
        if (
            request.plan.context
            not in [trial.context for trial in state.setup.plan.trials]
            or request.plan.resolved_duration_ns <= 0
        ):
            raise ValueError(
                "trial is absent from prepared session or lacks resolved duration"
            )
        return
    if (
        state.trial is None
        or command.work.WhichOneof("work") != "trial"
        or command.work.trial != state.trial.plan.context
    ):
        raise ValueError("command has no exact prepared trial")
    if isinstance(request, wire.ScheduleTrialRequest):
        if (
            state.schedule is not None
            or request.start_monotonic_ns <= now
            or request.normal_end_monotonic_ns - request.start_monotonic_ns
            != state.trial.plan.resolved_duration_ns
        ):
            raise ValueError(
                "schedule is late, duplicated or changes resolved duration"
            )
        return
    if isinstance(request, wire.ReleaseTrialRequest):
        schedule = state.schedule
        if (
            schedule is None
            or state.release is not None
            or request.schedule_operation.command_id != schedule.command.command_id
            or (request.start_monotonic_ns, request.normal_end_monotonic_ns)
            != (schedule.start_monotonic_ns, schedule.normal_end_monotonic_ns)
        ):
            raise ValueError("Release differs from retained schedule")
        if (
            now
            >= request.start_monotonic_ns
            - state.setup.plan.policies.backend_release_offset_ns
        ):
            raise ValueError("original backend Release deadline expired")
        return
    raise ValueError("unsupported Tracking operation")
