"""Controller-to-renderer lifecycle binding; no per-frame traffic (V01/E08)."""

from __future__ import annotations

import hashlib
from uuid import uuid4

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.identity import require_uuid4
from cephvr.visual_stimulus.transport.messages import backend_command
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus_runtime

from .state import CommandLink, Identity, State


def bind_command(
    identity: Identity, state: State, method: str, request: Message, deadline_ns: int
) -> tuple[Message, CommandLink]:
    if isinstance(
        request,
        (
            wire.VisualStimulusDisplayInitializationRequest,
            wire.VisualStimulusDisplayCalibrationOpenRequest,
            wire.VisualStimulusDisplayCalibrationCloseRequest,
        ),
    ):
        parent = wire.BackendCommand(
            command_id=request.command_id, issuer=request.issuer, target=request.target
        )
        revision = request.configuration_revision
    else:
        parent = backend_command(request)
        revision = (
            request.plan.configuration_revision
            if isinstance(request, wire.SetupSessionRequest)
            else (
                state.setup.plan.configuration_revision
                if state.setup
                else (
                    state.display.calibration.configuration_revision
                    if state.display is not None
                    and state.display.HasField("calibration")
                    and method
                    in {"Cleanup", "Shutdown", "InterruptSession", "CancelSetup"}
                    else 0
                )
            )
        )
    child = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=identity.process,
        target=visual_stimulus.WorkerContext(
            worker=identity.worker,
            owner=identity.process,
            work=parent.work,
            configuration_revision=revision,
        ),
        parent_operation=pb.OperationContext(command_id=parent.command_id),
        deadline_monotonic_ns=deadline_ns,
    )
    link = CommandLink(
        method,
        wire.BackendCommand.FromString(parent.SerializeToString()),
        child,
        deadline_ns,
        (
            request.diagnostic_id
            if isinstance(
                request,
                (
                    wire.VisualStimulusDisplayCalibrationOpenRequest,
                    wire.VisualStimulusDisplayCalibrationCloseRequest,
                ),
            )
            else ""
        ),
    )
    if (
        method in {"Cleanup", "Shutdown", "InterruptSession", "CancelSetup"}
        and state.setup is None
        and state.display is not None
    ):
        link.output_ids = frozenset(item.output_id for item in state.display.outputs)
    if isinstance(request, wire.VisualStimulusDisplayInitializationRequest):
        initialization = visual_stimulus.InitializeDisplay(
            command=child,
            display=request.display,
            limits=request.limits,
            policies=request.policies,
        )
        if request.HasField("asset_root"):
            initialization.asset_root = request.asset_root
        if request.HasField("pacing_refresh_hz"):
            initialization.pacing_refresh_hz = request.pacing_refresh_hz
        if request.HasField("pacing_output_id"):
            initialization.pacing_output_id = request.pacing_output_id
        return initialization, link
    if isinstance(request, wire.VisualStimulusDisplayCalibrationOpenRequest):
        if state.setup is not None:
            raise ValueError("display calibration is unavailable during a session")
        if (
            state.display is not None
            and state.display.HasField("calibration")
            and state.display.calibration.state
            != visual_stimulus_runtime.DISPLAY_CALIBRATION_STATE_IDLE
        ):
            raise ValueError("previous display calibration is not confirmed Idle")
        if (
            not request.policies.HasField("limits")
            or not request.policies.limits.HasField("max_document_bytes")
            or request.policies.limits.max_document_bytes == 0
            or not request.profile_json
            or len(request.profile_json.encode("utf-8"))
            > request.policies.limits.max_document_bytes
            or hashlib.sha256(request.profile_json.encode("utf-8")).hexdigest()
            != request.profile_sha256
        ):
            raise ValueError("calibration profile identity or limit is invalid")
        from cephvr.visual_stimulus.config.models.display_profile import (
            parse_display_json,
        )

        profile = parse_display_json(
            request.profile_json,
            max_bytes=request.policies.limits.max_document_bytes,
        )
        link.output_ids = frozenset(item.output_id for item in profile.active_outputs)
        return visual_stimulus.OpenDisplayCalibrationCommand(
            command=child,
            diagnostic_id=request.diagnostic_id,
            profile_json=request.profile_json,
            profile_sha256=request.profile_sha256,
            asset_root=request.asset_root,
            arena_relative_path=request.arena_relative_path,
            arena_size_bytes=request.arena_size_bytes,
            arena_sha256=request.arena_sha256,
            policies=request.policies,
        ), link
    if isinstance(request, wire.VisualStimulusDisplayCalibrationCloseRequest):
        if state.setup is not None:
            raise ValueError("display calibration cannot close during a session")
        pending_open = next(
            (
                existing
                for existing in reversed(tuple(state.links.values()))
                if existing.method == "OpenDisplayCalibration"
                and existing.diagnostic_id == request.diagnostic_id
            ),
            None,
        )
        if pending_open is not None:
            link.output_ids = pending_open.output_ids
        elif state.display is not None:
            link.output_ids = frozenset(
                item.output_id for item in state.display.outputs
            )
        if not link.output_ids:
            raise ValueError("calibration output identities are unavailable")
        return visual_stimulus.CloseDisplayCalibrationCommand(
            command=child, diagnostic_id=request.diagnostic_id
        ), link
    if isinstance(request, wire.SetupSessionRequest):
        return visual_stimulus.WorkerSetup(
            command=child,
            session=request.plan,
            settings=request.settings.visual_stimulus,
            policies=request.visual_stimulus_policies,
            feedback_attachment=request.feedback_attachment,
        ), link
    if isinstance(request, wire.PrepareTrialRequest):
        prepared = state.prepared.get(request.plan.context.trial_id)
        if (
            prepared is None
            or prepared.trial != request.plan.context
            or prepared.handle != request.plan.resolved_stimulus.prepared
        ):
            raise ValueError("trial does not match retained preparation")
        return visual_stimulus.WorkerPrepareTrial(
            command=child,
            trial=request.plan,
            prepared=prepared.handle,
            outputs=request.outputs,
        ), link
    if isinstance(request, wire.ScheduleTrialRequest):
        prepared = state.prepared.get(parent.work.trial.trial_id)
        if prepared is None:
            raise ValueError("trial preparation absent")
        return visual_stimulus.WorkerSchedule(
            command=child,
            prepared=prepared.handle,
            start_monotonic_ns=request.start_monotonic_ns,
            normal_end_monotonic_ns=request.normal_end_monotonic_ns,
            trial_file_prefix=request.trial_file_prefix,
            outputs=request.outputs,
        ), link
    if isinstance(request, wire.ReleaseTrialRequest):
        scheduled = next(
            (
                x
                for x in state.links.values()
                if x.method == "ScheduleTrial"
                and x.parent.command_id == request.schedule_operation.command_id
            ),
            None,
        )
        if scheduled is None:
            raise ValueError("release has no matching scheduled operation")
        return visual_stimulus.WorkerRelease(
            command=child,
            schedule_operation=pb.OperationContext(
                command_id=scheduled.child.command_id
            ),
            start_monotonic_ns=request.start_monotonic_ns,
            normal_end_monotonic_ns=request.normal_end_monotonic_ns,
        ), link
    if isinstance(request, (wire.StopTrialRequest, wire.InterruptSessionRequest)):
        return visual_stimulus.WorkerStop(
            command=child,
            issued_monotonic_ns=request.issued_monotonic_ns,
            cause=request.reason,
        ), link
    if isinstance(request, wire.BackendCommand):
        return child, link
    raise ValueError(f"unsupported Visual Stimulus command {method}")


def validate(identity: Identity, state: State, method: str, request: Message) -> None:
    command = backend_command(request)
    require_uuid4(command.command_id)
    if command.target != identity.backend:
        raise ValueError("wrong Visual Stimulus backend generation")
    expected = (
        (identity.controller, identity.supervisor)
        if method
        in {
            "CancelSetup",
            "InterruptSession",
            "Cleanup",
            "Shutdown",
            "StopTrial",
            "AbortTrial",
        }
        else (identity.controller,)
    )
    if command.issuer not in expected:
        raise ValueError("wrong Visual Stimulus authority generation")
    recoverable_calibration = (
        method
        in {
            "OpenDisplayCalibration",
            "CloseDisplayCalibration",
        }
        and state.setup is None
    )
    if (
        state.interrupted
        and method
        not in {
            "Cleanup",
            "Shutdown",
            "InterruptSession",
            "CancelSetup",
            "StopTrial",
            "AbortTrial",
            "SetupSession",
            "InitializeDisplay",
        }
        and not recoverable_calibration
    ):
        raise ValueError("interrupted Visual Stimulus session is permanently fenced")
    if isinstance(request, wire.SetupSessionRequest):
        if state.setup is not None and (
            state.cleanup is None
            or not state.cleanup.trial_activity_stopped
            or any(not item.released for item in state.cleanup.resources)
            or any(
                item.closure
                not in {
                    pb.OUTPUT_CLOSURE_CLOSED,
                    pb.OUTPUT_CLOSURE_FAILED,
                    pb.OUTPUT_CLOSURE_NOT_STARTED,
                }
                or not item.HasField("artifact_present")
                for item in state.cleanup.outputs
            )
        ):
            raise ValueError("previous Visual Stimulus session has unresolved cleanup")
        if (
            command.work.WhichOneof("work") != "session"
            or command.work.session != request.plan.context
        ):
            raise ValueError("Setup context differs from allocated session")
        if (
            request.settings.backend_name != "visual_stimulus"
            or request.settings.WhichOneof("settings") != "visual_stimulus"
        ):
            raise ValueError("typed Visual Stimulus settings required")
        closed = request.plan.configuration.mode == pb.SESSION_MODE_CLOSED_LOOP
        if closed != request.HasField("feedback_attachment"):
            raise ValueError("feedback attachment must match session mode")
    elif isinstance(request, wire.VisualStimulusDisplayInitializationRequest):
        if state.setup is not None and state.cleanup is None:
            raise ValueError(
                "display initialization forbidden during session preparation"
            )
    elif isinstance(request, wire.VisualStimulusDisplayCalibrationOpenRequest):
        if state.setup is not None:
            raise ValueError("display calibration unavailable during a session")
        if (
            state.display is not None
            and state.display.HasField("calibration")
            and state.display.calibration.state
            != visual_stimulus_runtime.DISPLAY_CALIBRATION_STATE_IDLE
        ):
            raise ValueError("previous display calibration is not confirmed Idle")
    elif isinstance(request, wire.VisualStimulusDisplayCalibrationCloseRequest):
        if state.setup is not None:
            raise ValueError("display calibration close unavailable during a session")
        evidence = (
            state.display.calibration
            if state.display is not None and state.display.HasField("calibration")
            else None
        )
        matching_open = any(
            link.method == "OpenDisplayCalibration"
            and link.diagnostic_id == request.diagnostic_id
            and bool(link.output_ids)
            for link in state.links.values()
        )
        projected_active = (
            evidence is not None
            and evidence.diagnostic_id == request.diagnostic_id
            and evidence.state
            in {
                visual_stimulus_runtime.DISPLAY_CALIBRATION_STATE_ACTIVE,
                visual_stimulus_runtime.DISPLAY_CALIBRATION_STATE_UNKNOWN,
            }
        )
        if (
            evidence is not None
            and evidence.diagnostic_id == request.diagnostic_id
            and evidence.state == visual_stimulus_runtime.DISPLAY_CALIBRATION_STATE_IDLE
        ):
            matching_open = False
        if not (projected_active or matching_open):
            raise ValueError("display calibration identity is not current")
    elif (
        method in {"Cleanup", "Shutdown", "InterruptSession", "CancelSetup"}
        and state.setup is None
    ):
        calibration = (
            state.display.calibration
            if (state.display is not None and state.display.HasField("calibration"))
            else None
        )
        if calibration is None or calibration.state not in {
            visual_stimulus_runtime.DISPLAY_CALIBRATION_STATE_PREPARING,
            visual_stimulus_runtime.DISPLAY_CALIBRATION_STATE_ACTIVE,
            visual_stimulus_runtime.DISPLAY_CALIBRATION_STATE_CLOSING,
            visual_stimulus_runtime.DISPLAY_CALIBRATION_STATE_UNKNOWN,
        }:
            raise ValueError("sessionless safety command has no open calibration")
    elif method not in {"Shutdown"}:
        if state.setup is None:
            raise ValueError("Visual Stimulus session is not prepared")
        work = command.work
        session = (
            work.trial.session if work.WhichOneof("work") == "trial" else work.session
        )
        if session != state.setup.plan.context:
            raise ValueError("stale Visual Stimulus session")
