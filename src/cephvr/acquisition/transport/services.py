"""Existing acquisition gRPC services with generation and deadline admission."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping

import grpc
from google.protobuf.message import Message

from cephvr.acquisition.coordinator.operations import CoordinatorOperations
from cephvr.acquisition.identity import ACQUISITION_WORKER_ROLES
from cephvr.acquisition.transport.admission import CommandAdmissionTransport
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import services_pb2_grpc as acq_rpc
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc as control_rpc
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.auth import AuthenticationError, require_authenticated_peer
from cephvr.shared.clock import host_time_ns
from cephvr.shared.transport_deadlines import (
    DeadlineMetadataError,
    parse_deadline_metadata,
)


class _ServiceBase:
    def __init__(
        self,
        operations: CoordinatorOperations,
        credentials: MutableMapping[tuple[str, str], str],
        admission: CommandAdmissionTransport,
    ) -> None:
        self.operations = operations
        # This is the one startup-owned registration map, shared by transport.
        self.credentials = credentials
        self.admission = admission

    async def _dispatch(
        self,
        context: grpc.aio.ServicerContext,
        request: Message,
        command: wire.BackendCommand,
        method: str,
        handler: Callable[[int], Awaitable[control.CommandAdmission]],
        *,
        caller_roles: frozenset[str] = frozenset(("controller",)),
    ) -> control.CommandAdmission:
        await self._authenticate(context, command.issuer, caller_roles=caller_roles)
        deadline_ns = await self._deadline(context)
        return await self.admission.dispatch(
            method,
            request,
            command,
            deadline_ns,
            lambda *, deadline_ns: handler(deadline_ns),
            priority=method
            in {
                "CancelSetup",
                "StopTrial",
                "AbortTrial",
                "InterruptSession",
                "Cleanup",
                "Shutdown",
            },
        )

    async def _authenticate(
        self,
        context: grpc.aio.ServicerContext,
        source: control.ProcessIdentity,
        *,
        caller_roles: frozenset[str] | None = None,
    ) -> None:
        token = self.credentials.get((source.role, source.generation))
        if (
            token is None
            or caller_roles is not None
            and source.role not in caller_roles
        ):
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED, "unregistered caller generation"
            )
            raise AssertionError("unreachable")
        try:
            require_authenticated_peer(
                context.peer(),
                context.invocation_metadata(),
                expected_role=source.role,
                expected_generation=source.generation,
                expected_token=token,
            )
        except AuthenticationError as exc:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))

    async def _authenticate_metadata(
        self,
        context: grpc.aio.ServicerContext,
        *,
        caller_roles: frozenset[str],
    ) -> control.ProcessIdentity:
        metadata = dict(
            (key, value)
            for key, value in context.invocation_metadata()
            if key in {"x-cephvr-role", "x-cephvr-generation"}
        )
        role, generation = (
            metadata.get("x-cephvr-role"),
            metadata.get("x-cephvr-generation"),
        )
        if role is None or generation is None or role not in caller_roles:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED, "caller identity is not authorized"
            )
        identity = control.ProcessIdentity(role=role, generation=generation)
        await self._authenticate(context, identity, caller_roles=caller_roles)
        return identity

    async def _deadline(self, context: grpc.aio.ServicerContext) -> int:
        try:
            return parse_deadline_metadata(context.invocation_metadata())
        except DeadlineMetadataError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
            raise AssertionError("unreachable") from exc


class AcquisitionBackendService(_ServiceBase, control_rpc.BackendServiceServicer):
    """The public owner RPCs on the acquisition coordinator endpoint."""

    def __init__(
        self,
        operations: CoordinatorOperations,
        credentials: MutableMapping[tuple[str, str], str],
        admission: CommandAdmissionTransport,
    ) -> None:
        super().__init__(operations, credentials, admission)

    async def ApplyIncidentScope(
        self, request: wire.IncidentScopeRequest, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "ApplyIncidentScope",
            lambda deadline: self.operations.apply_incident_scope(
                request, deadline_ns=deadline
            ),
        )

    async def SetupSession(
        self, request: wire.SetupSessionRequest, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "SetupSession",
            lambda deadline: self.operations.setup_session(
                request, deadline_ns=deadline
            ),
        )

    async def CancelSetup(
        self, request: wire.BackendCommand, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request,
            "CancelSetup",
            lambda deadline: self.operations.cancel_setup(
                request, deadline_ns=deadline
            ),
            caller_roles=frozenset(("controller", "supervisor")),
        )

    async def PrepareTrial(
        self, request: wire.PrepareTrialRequest, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "PrepareTrial",
            lambda deadline: self.operations.prepare_trial(
                request, deadline_ns=deadline
            ),
        )

    async def ScheduleTrial(
        self, request: wire.ScheduleTrialRequest, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "ScheduleTrial",
            lambda deadline: self.operations.schedule_trial(
                request, deadline_ns=deadline
            ),
        )

    async def ReleaseTrial(
        self, request: wire.ReleaseTrialRequest, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "ReleaseTrial",
            lambda deadline: self.operations.release_trial(
                request, deadline_ns=deadline
            ),
        )

    async def StopTrial(
        self, request: wire.StopTrialRequest, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "StopTrial",
            lambda deadline: self.operations.stop_trial(request, deadline_ns=deadline),
        )

    async def AbortTrial(
        self, request: wire.StopTrialRequest, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "AbortTrial",
            lambda deadline: self.operations.abort_trial(request, deadline_ns=deadline),
        )

    async def InterruptSession(
        self, request: wire.InterruptSessionRequest, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "InterruptSession",
            lambda deadline: self.operations.interrupt_session(
                request, deadline_ns=deadline
            ),
            caller_roles=frozenset(("controller", "supervisor")),
        )

    async def GetState(
        self, request: wire.BackendQuery, context: grpc.aio.ServicerContext
    ) -> control.ParticipantState:
        await self._authenticate_metadata(
            context, caller_roles=frozenset(("controller", "supervisor"))
        )
        return await self.operations.get_state(
            request, deadline_ns=await self._deadline(context)
        )

    async def GetRetainedResult(
        self, request: wire.RetainedResultQuery, context: grpc.aio.ServicerContext
    ) -> wire.RetainedResult:
        await self._authenticate_metadata(
            context, caller_roles=frozenset(("controller", "supervisor"))
        )
        return await self.operations.get_retained_result(
            request, deadline_ns=await self._deadline(context)
        )

    async def Cleanup(
        self, request: wire.BackendCommand, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request,
            "Cleanup",
            lambda deadline: self.operations.cleanup(request, deadline_ns=deadline),
            caller_roles=frozenset(("controller", "supervisor")),
        )

    async def Shutdown(
        self, request: wire.BackendCommand, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request,
            "Shutdown",
            lambda deadline: self.operations.shutdown(request, deadline_ns=deadline),
            caller_roles=frozenset(("controller", "supervisor")),
        )


class AcquisitionConfigurationService(
    _ServiceBase, control_rpc.AcquisitionConfigurationServiceServicer
):
    """Controller-only in-process configuration/device operations."""

    def __init__(
        self,
        operations: CoordinatorOperations,
        credentials: MutableMapping[tuple[str, str], str],
        admission: CommandAdmissionTransport,
    ) -> None:
        super().__init__(operations, credentials, admission)

    async def ConfirmTrackingInput(
        self, request: wire.TrackingInputConfirmation, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "ConfirmTrackingInput",
            lambda deadline: self.operations.confirm_tracking_input(
                request, deadline_ns=deadline
            ),
        )

    async def ApplyCameraSettings(
        self,
        request: wire.AcquisitionCameraSettingsCommand,
        context: grpc.aio.ServicerContext,
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "ApplyCameraSettings",
            lambda deadline: self.operations.apply_camera_settings(
                request, deadline_ns=deadline
            ),
        )

    async def ApplyPulseConfiguration(
        self, request: wire.AcquisitionPulseCommand, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "ApplyPulseConfiguration",
            lambda deadline: self.operations.apply_pulse_configuration(
                request, deadline_ns=deadline
            ),
        )

    async def ReportPreviewConsumerState(
        self, request: wire.PreviewConsumerReport, context: grpc.aio.ServicerContext
    ) -> control.ReportReceipt:
        await self._authenticate_metadata(
            context, caller_roles=frozenset(("controller",))
        )
        return await self.operations.report_preview_consumer_state(
            request, deadline_ns=await self._deadline(context)
        )

    async def ExecuteCameraCommand(
        self, request: wire.AcquisitionCameraCommand, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "ExecuteCameraCommand",
            lambda deadline: self.operations.execute_camera_command(
                request, deadline_ns=deadline
            ),
        )

    async def ExecuteMicrocontrollerCommand(
        self,
        request: wire.AcquisitionMicrocontrollerCommand,
        context: grpc.aio.ServicerContext,
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "ExecuteMicrocontrollerCommand",
            lambda deadline: self.operations.execute_microcontroller_command(
                request, deadline_ns=deadline
            ),
        )

    async def ConfirmConfiguration(
        self,
        request: wire.AcquisitionConfigurationConfirmation,
        context: grpc.aio.ServicerContext,
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "ConfirmConfiguration",
            lambda deadline: self.operations.confirm_configuration(
                request, deadline_ns=deadline
            ),
        )

    async def AttachTrackingDiagnosticInput(
        self,
        request: wire.AcquisitionTrackingDiagnosticAttachmentCommand,
        context: grpc.aio.ServicerContext,
    ) -> control.CommandAdmission:
        return await self._dispatch(
            context,
            request,
            request.command,
            "AttachTrackingDiagnosticInput",
            lambda deadline: self.operations.attach_tracking_diagnostic_input(
                request, deadline_ns=deadline
            ),
        )


class AcquisitionCoordinatorService(
    _ServiceBase, acq_rpc.AcquisitionCoordinatorServiceServicer
):
    """Authenticated private reports emitted by exact registered workers."""

    def __init__(
        self,
        operations: CoordinatorOperations,
        credentials: MutableMapping[tuple[str, str], str],
        admission: CommandAdmissionTransport,
    ) -> None:
        super().__init__(operations, credentials, admission)

    async def _worker(
        self,
        context: grpc.aio.ServicerContext,
        source: acq.WorkerContext,
    ) -> int:
        await self._authenticate(
            context,
            source.worker,
            caller_roles=ACQUISITION_WORKER_ROLES,
        )
        return await self._deadline(context)

    async def ReportWorkerWarnings(
        self, request: acq.WorkerWarningReport, context: grpc.aio.ServicerContext
    ) -> control.ReportReceipt:
        ingress_ns = host_time_ns()
        return await self.operations.report_worker_warnings(
            request,
            deadline_ns=await self._worker(context, request.source),
            ingress_ns=ingress_ns,
        )

    async def ReportWorkerOperation(
        self, request: acq.WorkerOperationReport, context: grpc.aio.ServicerContext
    ) -> control.ReportReceipt:
        ingress_ns = host_time_ns()
        return await self.operations.report_worker_operation(
            request,
            deadline_ns=await self._worker(context, request.source),
            ingress_ns=ingress_ns,
        )

    async def ReportWorkerLifecycle(
        self, request: acq.WorkerLifecycleEvidence, context: grpc.aio.ServicerContext
    ) -> control.ReportReceipt:
        ingress_ns = host_time_ns()
        return await self.operations.report_worker_lifecycle(
            request,
            deadline_ns=await self._worker(context, request.source),
            ingress_ns=ingress_ns,
        )

    async def ReportWorkerHeartbeat(
        self, request: control.HeartbeatReport, context: grpc.aio.ServicerContext
    ) -> control.ReportReceipt:
        ingress_ns = host_time_ns()
        await self._authenticate(
            context,
            request.source,
            caller_roles=ACQUISITION_WORKER_ROLES,
        )
        return await self.operations.report_worker_heartbeat(
            request,
            deadline_ns=await self._deadline(context),
            ingress_ns=ingress_ns,
        )
