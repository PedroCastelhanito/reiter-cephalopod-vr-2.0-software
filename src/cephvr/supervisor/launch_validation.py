"""Pure validation for immutable E08 launch plans."""

from __future__ import annotations

import ntpath

from cephvr.acquisition.identity import ACQUISITION_WORKER_ROLES
from cephvr.acquisition.identity import FFMPEG_ROLES as ACQ_FFMPEG_ROLES
from cephvr.control.v1 import services_pb2 as wire
from cephvr.controller.microcontroller.identity import FIRMWARE_UPLOAD_ROLE
from cephvr.shared.identity import require_uuid4
from cephvr.visual_stimulus.identity import FFMPEG_ROLES as VISUAL_STIMULUS_FFMPEG_ROLES

BACKEND_ROLES = frozenset({"acquisition", "visual_stimulus", "tracking"})
TOP_LEVEL_ROLES = BACKEND_ROLES | {"controller", "gui"}


class LaunchError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def launch_work_key(request: wire.PlanLaunchRequest) -> str:
    kind = request.work.WhichOneof("work")
    if kind == "session":
        return require_uuid4(request.work.session.session_id)
    if kind == "trial":
        return require_uuid4(request.work.trial.session.session_id)
    raise LaunchError("INVALID_WORK", "launch work must identify a session")


def validate_plan(request: wire.PlanLaunchRequest) -> None:
    require_uuid4(request.command_id)
    require_uuid4(request.owner.generation)
    require_uuid4(request.child.generation)
    if not request.owner.role or not request.child.role or not request.executable:
        raise LaunchError("INVALID_LAUNCH", "owner, child and executable are required")
    if not ntpath.isabs(request.executable):
        raise LaunchError(
            "INVALID_EXECUTABLE", "launch executable must be an absolute path"
        )
    if request.stop_method not in {"grpc_shutdown", "owner_stdin_eof"} and not (
        request.child.role == FIRMWARE_UPLOAD_ROLE
        and request.stop_method == "owner_job_terminate"
    ):
        raise LaunchError("INVALID_STOP_METHOD", "unsupported child stop method")
    if request.python_worker and request.stop_method != "grpc_shutdown":
        raise LaunchError("INVALID_STOP_METHOD", "Python child requires gRPC shutdown")
    if request.child.role == "supervisor":
        raise LaunchError("INVALID_CHILD", "launcher alone creates supervisor")
    if request.child.role == FIRMWARE_UPLOAD_ROLE and (
        request.owner.role != "controller"
        or request.python_worker
        or request.stop_method != "owner_job_terminate"
        or request.HasField("work")
        or not request.parent_operation.command_id
    ):
        raise LaunchError(
            "INVALID_OWNER",
            "firmware upload requires its controller Configuration owner and operation",
        )
    if request.child.role == FIRMWARE_UPLOAD_ROLE:
        require_uuid4(request.parent_operation.command_id)
    if request.child.role in VISUAL_STIMULUS_FFMPEG_ROLES:
        if request.owner.role != "visual_stimulus_renderer" or not request.HasField(
            "work"
        ):
            raise LaunchError(
                "INVALID_OWNER",
                "Visual Stimulus media children require their exact renderer owner and work",
            )
    if (
        request.child.role in ACQ_FFMPEG_ROLES
        and request.owner.role not in ACQUISITION_WORKER_ROLES
    ):
        raise LaunchError(
            "INVALID_OWNER",
            "acquisition media children require an acquisition worker owner",
        )
    if request.child.role in TOP_LEVEL_ROLES and request.owner.role != "supervisor":
        raise LaunchError("INVALID_OWNER", "top-level launch owner is invalid")
    if request.HasField("work") and not request.HasField("parent_operation"):
        raise LaunchError(
            "MISSING_OPERATION", "work-scoped launch requires parent operation"
        )
    if request.HasField("work"):
        launch_work_key(request)
