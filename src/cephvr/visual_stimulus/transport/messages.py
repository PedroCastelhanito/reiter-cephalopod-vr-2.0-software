"""Normalize published commands without weakening their typed identity fields."""

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus


def backend_command(request: Message) -> wire.BackendCommand:
    if isinstance(request, wire.BackendCommand):
        return request
    if isinstance(request, wire.VisualStimulusDisplayInitializationRequest):
        return wire.BackendCommand(
            command_id=request.command_id, issuer=request.issuer, target=request.target
        )
    if isinstance(
        request,
        (
            wire.VisualStimulusDisplayCalibrationOpenRequest,
            wire.VisualStimulusDisplayCalibrationCloseRequest,
        ),
    ):
        return wire.BackendCommand(
            command_id=request.command_id,
            issuer=request.issuer,
            target=request.target,
        )
    if isinstance(
        request,
        (
            wire.SetupSessionRequest,
            wire.PrepareTrialRequest,
            wire.ScheduleTrialRequest,
            wire.ReleaseTrialRequest,
            wire.StopTrialRequest,
            wire.InterruptSessionRequest,
            wire.IncidentScopeRequest,
        ),
    ):
        return request.command
    raise ValueError("message is not a published backend command")


def worker_command(request: Message) -> visual_stimulus.WorkerCommand:
    if isinstance(request, visual_stimulus.WorkerCommand):
        return request
    if isinstance(
        request,
        (
            visual_stimulus.InitializeDisplay,
            visual_stimulus.WorkerSetup,
            visual_stimulus.WorkerPrepareTrial,
            visual_stimulus.WorkerSchedule,
            visual_stimulus.WorkerRelease,
            visual_stimulus.WorkerStop,
            visual_stimulus.WorkerRecipePublication,
            visual_stimulus.OpenDisplayCalibrationCommand,
            visual_stimulus.CloseDisplayCalibrationCommand,
        ),
    ):
        return request.command
    raise ValueError("message is not a published renderer command")
