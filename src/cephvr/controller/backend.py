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

    async def setup_session(
        self, request: svc.SetupSessionRequest
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.SetupSession(request, metadata=self.principal.metadata()),
        )

    async def cancel_setup(self, request: svc.BackendCommand) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.CancelSetup(request, metadata=self.principal.metadata()),
        )

    async def prepare_trial(
        self, request: svc.PrepareTrialRequest
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.PrepareTrial(request, metadata=self.principal.metadata()),
        )

    async def schedule_trial(
        self, request: svc.ScheduleTrialRequest
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.ScheduleTrial(request, metadata=self.principal.metadata()),
        )

    async def release_trial(
        self, request: svc.ReleaseTrialRequest
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.ReleaseTrial(request, metadata=self.principal.metadata()),
        )

    async def interrupt_session(
        self, request: svc.InterruptSessionRequest
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.InterruptSession(
                request, metadata=self.principal.metadata()
            ),
        )

    async def cleanup(self, request: svc.BackendCommand) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.Cleanup(request, metadata=self.principal.metadata()),
        )

    async def get_state(self, request: svc.BackendQuery) -> pb.ParticipantState:
        return cast(
            pb.ParticipantState,
            await self.stub.GetState(request, metadata=self.principal.metadata()),
        )

    async def bind_tracking_data(
        self, request: tracking_svc.TrackingDataBinding
    ) -> pb.CommandAdmission:
        if self.tracking is None:
            raise RuntimeError("tracking preparation endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self.tracking.BindData(request, metadata=self.principal.metadata()),
        )

    async def confirm_tracking_input(
        self, request: svc.TrackingInputConfirmation
    ) -> pb.CommandAdmission:
        if self.acquisition is None:
            raise RuntimeError("acquisition configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self.acquisition.ConfirmTrackingInput(
                request, metadata=self.principal.metadata()
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
        self, request: svc.IncidentScopeRequest
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.ApplyIncidentScope(
                request, metadata=self.principal.metadata()
            ),
        )

    async def get_retained_result(
        self, request: svc.RetainedResultQuery
    ) -> svc.RetainedResult:
        return cast(
            svc.RetainedResult,
            await self.stub.GetRetainedResult(
                request, metadata=self.principal.metadata()
            ),
        )

    async def confirm_configuration(
        self, request: svc.AcquisitionConfigurationConfirmation
    ) -> pb.CommandAdmission:
        if self.acquisition is None:
            raise RuntimeError("acquisition configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self.acquisition.ConfirmConfiguration(
                request, metadata=self.principal.metadata()
            ),
        )

    async def execute_camera_command(
        self, request: svc.AcquisitionCameraCommand
    ) -> pb.CommandAdmission:
        if self.acquisition is None:
            raise RuntimeError("acquisition configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self.acquisition.ExecuteCameraCommand(
                request, metadata=self.principal.metadata()
            ),
        )

    async def apply_camera_settings(
        self, request: svc.AcquisitionCameraSettingsCommand
    ) -> pb.CommandAdmission:
        if self.acquisition is None:
            raise RuntimeError("acquisition configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self.acquisition.ApplyCameraSettings(
                request, metadata=self.principal.metadata()
            ),
        )

    async def apply_pulse_configuration(
        self, request: svc.AcquisitionPulseCommand
    ) -> pb.CommandAdmission:
        if self.acquisition is None:
            raise RuntimeError("acquisition configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self.acquisition.ApplyPulseConfiguration(
                request, metadata=self.principal.metadata()
            ),
        )

    async def initialize_display(
        self, request: svc.VRDisplayInitializationRequest
    ) -> pb.CommandAdmission:
        if self.vr is None:
            raise RuntimeError("VR configuration endpoint unavailable")
        return cast(
            pb.CommandAdmission,
            await self.vr.InitializeDisplay(
                request, metadata=self.principal.metadata()
            ),
        )

    async def shutdown(self, request: svc.BackendCommand) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.Shutdown(request, metadata=self.principal.metadata()),
        )

    async def close(self) -> None:
        await self.channel.close()
