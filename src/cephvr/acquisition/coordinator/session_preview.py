"""Optional session viewers over the existing rate-capped latest-frame slots."""

from collections.abc import Callable

from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_operation_results import (
    ManualOperationResults,
)
from cephvr.acquisition.coordinator.manual_preview_window import execute_preview_window
from cephvr.acquisition.coordinator.preview_windows import PreviewWindows
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    ResourceRecord,
    SessionSlot,
    WorkerPreview,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb


class SessionPreview:
    """Attach readers only; capture, pulses and session buffer ownership stay unchanged."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        sessions: SessionSlot,
        resources: dict[str, ResourceRecord],
        windows: PreviewWindows,
        status: ManualDeviceStatusReporter,
        results: ManualOperationResults,
        clock: Callable[[], int],
    ) -> None:
        self.identity = identity
        self.sessions = sessions
        self.resources = resources
        self.windows = windows
        self.status = status
        self.results = results
        self.clock = clock

    async def execute(
        self, request: rpc.AcquisitionCameraCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        session = self.sessions.current
        command = request.command
        scope = command.work.WhichOneof("work")
        context = (
            command.work.trial.session if scope == "trial" else command.work.session
        )
        if (
            session is None
            or session.cleanup_complete
            or session.interrupted
            or self.clock() >= deadline_ns
            or command.issuer != self.identity.controller
            or command.target != self.identity.backend
            or not command.command_id
            or not command.parent_operation.command_id
            or scope not in {"trial", "session"}
            or context != session.work.session
            or request.preview_run_id != context.session_id
            or request.configuration_revision != session.confirmed_revision
            or request.camera not in session.required_cameras
            or request.kind
            not in {
                rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
                rpc.CAMERA_COMMAND_KIND_HIDE_PREVIEW,
            }
        ):
            return pb.CommandAdmission(
                command_id=command.command_id,
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="SESSION_PREVIEW",
                    message="Session preview identity or lifetime differs",
                ),
            )
        resource = next(
            (
                item
                for item in self.resources.values()
                if item.attachment.buffer.kind == acq.FRAME_BUFFER_KIND_PREVIEW
                and item.attachment.buffer.WhichOneof("scope") == "session"
                and item.attachment.buffer.session == context
                and item.attachment.buffer.camera == request.camera
                and item.ring is not None
            ),
            None,
        )
        resolved = session.camera_resolutions.get(request.camera)
        if resource is None or resolved is None or session.confirmed_settings is None:
            return pb.CommandAdmission(
                command_id=command.command_id,
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="SESSION_PREVIEW", message="Session preview slot unavailable"
                ),
            )
        self.status.reserve(command)
        self.status.resolve_camera(
            request.camera,
            resolved,
            device_open=True,
            preview_prepared=True,
            preview_running=True,
            preview_run_id=context.session_id,
            configuration_revision=session.confirmed_revision,
        )
        preview = WorkerPreview(
            run_id=context.session_id,
            configuration_revision=request.configuration_revision,
            allocation_id=resource.attachment.buffer.allocation_id,
            preview_output_bit_depth=session.confirmed_settings.preview_output_bit_depth,
            started=True,
        )
        return await execute_preview_window(
            request, preview, self.windows, self.results, deadline_ns=deadline_ns
        )
