"""Controller outbound ports for registered top-level backend coordinators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import grpc

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.auth import Principal
from cephvr.shared.identity import require_uuid4
from cephvr.shared.transport_deadlines import deadline_metadata, remaining_seconds
from cephvr.tracking.v1 import services_pb2 as tracking_svc
from cephvr.tracking.v1 import services_pb2_grpc as tracking_rpc


@dataclass(frozen=True)
class BackendRegistration:
    backend_name: str
    backend_generation: str
    endpoint: str
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.backend_name not in {"acquisition", "vr", "tracking"}:
            raise ValueError("unsupported top-level backend name")
        require_uuid4(self.backend_generation)
        if (
            not self.endpoint.startswith("127.0.0.1:")
            or not self.endpoint[10:].isdigit()
        ):
            raise ValueError("backend endpoint must be explicit IPv4 loopback")
        port = int(self.endpoint[10:])
        if not 0 < port <= 65535 or not self.token:
            raise ValueError("backend endpoint or protected token invalid")


class GrpcBackendPort:
    def __init__(
        self,
        registration: BackendRegistration,
        principal: Principal,
        *,
        max_message_bytes: int,
    ) -> None:
        self.registration = registration
        self.context = pb.BackendContext(
            backend_name=registration.backend_name,
            backend_generation=registration.backend_generation,
        )
        self.principal = principal
        self.channel = grpc.aio.insecure_channel(
            registration.endpoint,
            options=(
                ("grpc.max_receive_message_length", max_message_bytes),
                ("grpc.max_send_message_length", max_message_bytes),
            ),
        )
        self.stub = rpc.BackendServiceStub(self.channel)  # type: ignore[no-untyped-call]
        self.acquisition = (
            rpc.AcquisitionConfigurationServiceStub(self.channel)  # type: ignore[no-untyped-call]
            if registration.backend_name == "acquisition"
            else None
        )
        self.tracking = (
            tracking_rpc.TrackingPreparationServiceStub(self.channel)  # type: ignore[no-untyped-call]
            if registration.backend_name == "tracking"
            else None
        )
        self.vr = (
            rpc.VRConfigurationServiceStub(self.channel)  # type: ignore[no-untyped-call]
            if registration.backend_name == "vr"
            else None
        )

    async def _call(self, method: object, request: object, deadline_ns: int) -> object:
        timeout = remaining_seconds(deadline_ns)
        if timeout <= 0:
            raise TimeoutError("original backend operation deadline expired")
        return await method(  # type: ignore[operator]
            request,
            metadata=(*self.principal.metadata(), deadline_metadata(deadline_ns)),
            timeout=timeout,
        )

    async def setup_session(
        self, request: svc.SetupSessionRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self._call(self.stub.SetupSession, request, deadline_ns),
        )

    async def cancel_setup(
        self, request: svc.BackendCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self._call(self.stub.CancelSetup, request, deadline_ns),
        )

    async def prepare_trial(
        self, request: svc.PrepareTrialRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self._call(self.stub.PrepareTrial, request, deadline_ns),
        )

    async def schedule_trial(
        self, request: svc.ScheduleTrialRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self._call(self.stub.ScheduleTrial, request, deadline_ns),
        )

    async def release_trial(
        self, request: svc.ReleaseTrialRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self._call(self.stub.ReleaseTrial, request, deadline_ns),
        )

    async def interrupt_session(
        self, request: svc.InterruptSessionRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self._call(self.stub.InterruptSession, request, deadline_ns),
        )

    async def cleanup(
        self, request: svc.BackendCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self._call(self.stub.Cleanup, request, deadline_ns),
        )

    async def get_state(
        self, request: svc.BackendQuery, *, deadline_ns: int
    ) -> pb.ParticipantState:
        return cast(
            pb.ParticipantState,
            await self._call(self.stub.GetState, request, deadline_ns),
        )

    async def bind_tracking_data(
        self, request: tracking_svc.TrackingDataBinding, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        if self.tracking is None:
            raise RuntimeError("tracking preparation endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self._call(self.tracking.BindData, request, deadline_ns),
        )

    async def confirm_tracking_input(
        self, request: svc.TrackingInputConfirmation, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        if self.acquisition is None:
            raise RuntimeError("acquisition configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self._call(
                self.acquisition.ConfirmTrackingInput, request, deadline_ns
            ),
        )

    async def report_preview_consumer_state(
        self, request: svc.PreviewConsumerReport
    ) -> pb.ReportReceipt:
        if self.acquisition is None:
            raise RuntimeError("acquisition preview endpoint unavailable")
        return cast(
            pb.ReportReceipt,
            await self.acquisition.ReportPreviewConsumerState(
                request, metadata=self.principal.metadata()
            ),
        )

    async def apply_incident_scope(
        self, request: svc.IncidentScopeRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self._call(self.stub.ApplyIncidentScope, request, deadline_ns),
        )

    async def get_retained_result(
        self, request: svc.RetainedResultQuery, *, deadline_ns: int
    ) -> svc.RetainedResult:
        return cast(
            svc.RetainedResult,
            await self._call(self.stub.GetRetainedResult, request, deadline_ns),
        )

    async def confirm_configuration(
        self, request: svc.AcquisitionConfigurationConfirmation, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        if self.acquisition is None:
            raise RuntimeError("acquisition configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self._call(
                self.acquisition.ConfirmConfiguration, request, deadline_ns
            ),
        )

    async def execute_camera_command(
        self, request: svc.AcquisitionCameraCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        if self.acquisition is None:
            raise RuntimeError("acquisition configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self._call(
                self.acquisition.ExecuteCameraCommand, request, deadline_ns
            ),
        )

    async def apply_camera_settings(
        self, request: svc.AcquisitionCameraSettingsCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        if self.acquisition is None:
            raise RuntimeError("acquisition configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self._call(
                self.acquisition.ApplyCameraSettings, request, deadline_ns
            ),
        )

    async def apply_pulse_configuration(
        self, request: svc.AcquisitionPulseCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        if self.acquisition is None:
            raise RuntimeError("acquisition configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self._call(
                self.acquisition.ApplyPulseConfiguration, request, deadline_ns
            ),
        )

    async def initialize_display(
        self, request: svc.VRDisplayInitializationRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        if self.vr is None:
            raise RuntimeError("VR configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self._call(self.vr.InitializeDisplay, request, deadline_ns),
        )

    async def shutdown(
        self, request: svc.BackendCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self._call(self.stub.Shutdown, request, deadline_ns),
        )

    async def close(self) -> None:
        await self.channel.close()


class GrpcSupervisorPort:
    def __init__(self, stub: rpc.SupervisorServiceStub, principal: Principal) -> None:
        self.stub = stub
        self.principal = principal

    async def register_context(
        self, request: svc.RegisterContextRequest
    ) -> svc.RegistrationReceipt:
        return cast(
            svc.RegistrationReceipt,
            await self.stub.RegisterContext(
                request, metadata=self.principal.metadata()
            ),
        )

    async def request_shutdown(
        self, request: svc.ApplicationShutdownRequest
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.RequestApplicationShutdown(
                request, metadata=self.principal.metadata()
            ),
        )

    async def report_preview_consumer_state(
        self, request: svc.PreviewConsumerReport
    ) -> pb.ReportReceipt:
        return cast(
            pb.ReportReceipt,
            await self.stub.ReportPreviewConsumerState(
                request, metadata=self.principal.metadata()
            ),
        )
