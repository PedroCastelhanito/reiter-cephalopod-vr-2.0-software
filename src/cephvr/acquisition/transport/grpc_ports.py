"""Authenticated, original-deadline gRPC adapters for acquisition peers."""

from __future__ import annotations

from typing import cast

import grpc

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import services_pb2_grpc as acq_rpc
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc as control_rpc
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.shared.transport_deadlines import deadline_metadata, remaining_seconds


class _AuthenticatedPort:
    def __init__(self, channel: grpc.aio.Channel, principal: Principal) -> None:
        self._channel = channel
        self._principal = principal

    def _metadata(self, deadline_ns: int) -> tuple[tuple[str, str], ...]:
        if deadline_ns <= host_time_ns():
            raise TimeoutError("peer operation deadline expired")
        return (*self._principal.metadata(), deadline_metadata(deadline_ns))

    @staticmethod
    def _timeout(deadline_ns: int) -> float:
        timeout = remaining_seconds(deadline_ns)
        if timeout <= 0:
            raise TimeoutError("peer operation deadline expired")
        return timeout


class GrpcWorkerPort(_AuthenticatedPort):
    """One private channel bound to a registered worker generation."""

    def __init__(
        self,
        channel: grpc.aio.Channel,
        principal: Principal,
        context: acq.WorkerContext,
    ) -> None:
        super().__init__(channel, principal)
        if (
            principal.role != context.owner.role
            or principal.generation != context.owner.generation
        ):
            raise ValueError("worker owner principal differs from exact context")
        self.context = acq.WorkerContext.FromString(context.SerializeToString())
        self._stub = acq_rpc.AcquisitionWorkerServiceStub(channel)  # type: ignore[no-untyped-call]

    async def _request(self, method: str, request: object, deadline_ns: int) -> object:
        rpc = getattr(self._stub, method)
        return await rpc(
            request,
            metadata=self._metadata(deadline_ns),
            timeout=self._timeout(deadline_ns),
        )

    async def prepare_preview(
        self, request: acq.WorkerPreparePreview, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("PreparePreview", request, deadline_ns),
        )

    async def start_preview(
        self, request: acq.WorkerStartPreview, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("StartPreview", request, deadline_ns),
        )

    async def stop_preview(
        self, request: acq.WorkerStopPreview, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("StopPreview", request, deadline_ns),
        )

    async def edit_camera(
        self, request: acq.WorkerEditCamera, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("EditCamera", request, deadline_ns),
        )

    async def resolve_camera_configuration(
        self, request: acq.WorkerResolveCamera, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("ResolveCameraConfiguration", request, deadline_ns),
        )

    async def get_state(
        self, request: acq.WorkerQuery, *, deadline_ns: int
    ) -> acq.WorkerState:
        return cast(
            acq.WorkerState, await self._request("GetState", request, deadline_ns)
        )

    async def get_retained_result(
        self, request: acq.WorkerRetainedResultQuery, *, deadline_ns: int
    ) -> acq.WorkerRetainedResult:
        return cast(
            acq.WorkerRetainedResult,
            await self._request("GetRetainedResult", request, deadline_ns),
        )

    async def setup_session(
        self, request: acq.WorkerSetupSession, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("SetupSession", request, deadline_ns),
        )

    async def cancel_setup(
        self, request: acq.WorkerCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("CancelSetup", request, deadline_ns),
        )

    async def prepare_trial(
        self, request: acq.WorkerPrepareTrial, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("PrepareTrial", request, deadline_ns),
        )

    async def schedule_trial(
        self, request: acq.WorkerSchedule, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("ScheduleTrial", request, deadline_ns),
        )

    async def release_trial(
        self, request: acq.WorkerRelease, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("ReleaseTrial", request, deadline_ns),
        )

    async def record_pulse_evidence(
        self, request: acq.WorkerPulseEvidence, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await self._request("RecordPulseEvidence", request, deadline_ns),
        )

    async def stop_trial(
        self, request: acq.WorkerStop, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("StopTrial", request, deadline_ns),
        )

    async def interrupt_session(
        self, request: acq.WorkerInterrupt, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("InterruptSession", request, deadline_ns),
        )

    async def cleanup(
        self, request: acq.WorkerCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("Cleanup", request, deadline_ns),
        )

    async def shutdown(
        self, request: acq.WorkerCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return cast(
            control.CommandAdmission,
            await self._request("Shutdown", request, deadline_ns),
        )

    async def close(self) -> None:
        await self._channel.close()


class GrpcSupervisorPort(_AuthenticatedPort):
    """Acquisition owner calls into its already registered supervisor."""

    def __init__(self, channel: grpc.aio.Channel, principal: Principal) -> None:
        super().__init__(channel, principal)
        self._stub = control_rpc.SupervisorServiceStub(channel)  # type: ignore[no-untyped-call]

    async def _request(self, method: str, request: object, deadline_ns: int) -> object:
        return await getattr(self._stub, method)(
            request,
            metadata=self._metadata(deadline_ns),
            timeout=self._timeout(deadline_ns),
        )

    async def plan_launch(
        self, request: wire.PlanLaunchRequest, *, deadline_ns: int
    ) -> wire.LaunchReceipt:
        return cast(
            wire.LaunchReceipt, await self._request("PlanLaunch", request, deadline_ns)
        )

    async def confirm_launch(
        self, request: wire.ConfirmLaunchRequest, *, deadline_ns: int
    ) -> wire.LaunchReceipt:
        return cast(
            wire.LaunchReceipt,
            await self._request("ConfirmLaunch", request, deadline_ns),
        )

    async def get_launch_state(
        self, request: wire.LaunchQuery, *, deadline_ns: int
    ) -> wire.LaunchState:
        return cast(
            wire.LaunchState,
            await self._request("GetLaunchState", request, deadline_ns),
        )

    async def register_context(
        self, request: wire.RegisterContextRequest, *, deadline_ns: int
    ) -> wire.RegistrationReceipt:
        return cast(
            wire.RegistrationReceipt,
            await self._request("RegisterContext", request, deadline_ns),
        )

    async def report_lifecycle(
        self, request: control.LifecycleReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await self._request("ReportLifecycle", request, deadline_ns),
        )

    async def report_error(
        self, request: control.ErrorReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await self._request("ReportError", request, deadline_ns),
        )

    async def report_heartbeat(
        self, request: control.HeartbeatReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await self._request("ReportHeartbeat", request, deadline_ns),
        )

    async def close(self) -> None:
        await self._channel.close()


class GrpcControllerPort(_AuthenticatedPort):
    """Acquisition reports retained device and worker facts to its controller."""

    def __init__(self, channel: grpc.aio.Channel, principal: Principal) -> None:
        super().__init__(channel, principal)
        self._stub = control_rpc.ExperimentControllerServiceStub(channel)  # type: ignore[no-untyped-call]

    async def _request(self, method: str, request: object, deadline_ns: int) -> object:
        return await getattr(self._stub, method)(
            request,
            metadata=self._metadata(deadline_ns),
            timeout=self._timeout(deadline_ns),
        )

    async def report_lifecycle(
        self, request: control.LifecycleReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await self._request("ReportLifecycle", request, deadline_ns),
        )

    async def report_acquisition_resolution(
        self, request: wire.AcquisitionResolutionReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await self._request("ReportAcquisitionResolution", request, deadline_ns),
        )

    async def report_acquisition_device_status(
        self, request: wire.AcquisitionDeviceStatusReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await self._request("ReportAcquisitionDeviceStatus", request, deadline_ns),
        )

    async def report_acquisition_warnings(
        self, request: wire.AcquisitionWarningReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await self._request("ReportAcquisitionWarnings", request, deadline_ns),
        )

    async def report_preview_attachment(
        self, request: wire.PreviewAttachmentReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await self._request("ReportPreviewAttachment", request, deadline_ns),
        )

    async def report_data_preparation(
        self, request: wire.DataPreparationReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await self._request("ReportDataPreparation", request, deadline_ns),
        )

    async def close(self) -> None:
        await self._channel.close()
