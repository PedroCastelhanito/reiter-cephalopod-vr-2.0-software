"""Loopback gRPC front door for the authoritative controller (E02/E03/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from pathlib import Path
from typing import Literal

import grpc

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.receipts import rejected_admission, rejected_receipt
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.transport.admission import CommandAdmissionGate
from cephvr.controller.transport.auth import ClientAuthentication
from cephvr.controller.transport.ingress import BoundedReportIngress
from cephvr.shared.auth import AuthenticationError, require_authenticated_peer
from cephvr.synchronization.diagnostic import SpikeGLXDiagnostic


class ExperimentControllerService(rpc.ExperimentControllerServiceServicer):
    """Every RPC authenticates protected metadata before touching controller state."""

    def __init__(
        self,
        runtime: ControllerRuntime,
        *,
        client_authentication: ClientAuthentication,
        peer_tokens: Mapping[str, tuple[str, str]],
        max_pending_events: int = 1024,
        max_pending_payload_bytes: int = 67_108_864,
        max_message_bytes: int = 16_777_216,
        command_retention_ns: int = 300_000_000_000,
        spikeglx_diagnostic: SpikeGLXDiagnostic | None = None,
    ) -> None:
        self.runtime = runtime
        self.client_authentication = client_authentication
        self.peer_tokens = dict(peer_tokens)
        self.spikeglx_diagnostic = spikeglx_diagnostic
        self._commands = CommandAdmissionGate(
            runtime,
            max_pending_events=max_pending_events,
            max_pending_payload_bytes=max_pending_payload_bytes,
            command_retention_ns=command_retention_ns,
        )
        runtime.bind_camera_status_retention(self._commands.retention_ledger)
        self._reports = BoundedReportIngress(
            runtime,
            max_pending_events=max_pending_events,
            max_pending_payload_bytes=max_pending_payload_bytes,
            max_message_bytes=max_message_bytes,
        )

    async def aclose(self) -> None:
        self._commands.stop_accepting()
        self._reports.stop_accepting()
        await asyncio.gather(self._reports.aclose(), self._commands.aclose())

    async def _client(self, context: grpc.aio.ServicerContext, client_id: str) -> None:
        if not client_id:
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED, "client identity required"
            )
        try:
            await self.client_authentication(
                client_id,
                self.runtime.generation,
                context.peer(),
                context.invocation_metadata(),
            )
        except (AuthenticationError, ValueError) as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))

    async def _peer(
        self, context: grpc.aio.ServicerContext, role: str, generation: str
    ) -> None:
        trusted = self.peer_tokens.get(role)
        if trusted is None or trusted[0] != generation:
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED, "unregistered process generation"
            )
            raise AssertionError("abort returned")
        try:
            require_authenticated_peer(
                context.peer(),
                context.invocation_metadata(),
                expected_role=role,
                expected_generation=trusted[0],
                expected_token=trusted[1],
            )
        except (AuthenticationError, ValueError) as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))

    async def _admit_safety(
        self,
        name: str,
        kind: Literal["abort", "shutdown"],
        request: svc.OperatorCommand,
        operation: Callable[[], Awaitable[pb.CommandAdmission]],
    ) -> pb.CommandAdmission:
        command_id = request.operator.command_id
        try:
            fresh = self._commands.fresh(name, command_id)
        except ValueError as exc:
            return rejected_admission(command_id, "ADMISSION", str(exc))
        if fresh:
            error = await self.runtime.safety_command_precondition(request, kind)
            if error:
                return rejected_admission(command_id, "PRECONDITION", error)
        return await self._commands.admit(name, command_id, request, operation)

    async def GetSnapshot(
        self, request: svc.SnapshotRequest, context: grpc.aio.ServicerContext
    ) -> pb.Snapshot:
        await self._client(context, request.client_id)
        return await self.runtime.snapshot()

    async def WatchState(
        self, request: svc.WatchRequest, context: grpc.aio.ServicerContext
    ) -> AsyncIterator[pb.Snapshot]:
        await self._client(context, request.client_id)
        try:
            watch = await self.runtime.open_watch(request.client_id, request.watch_id)
        except ValueError as exc:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
        try:
            while True:
                view = await watch.queue.get()
                await self.runtime.delivered_watch_view(watch, view.state_revision)
                yield view
        finally:
            await self.runtime.close_watch(watch)

    async def AcquireControl(
        self, request: svc.ControlClaim, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.client_id)
        return await self._commands.admit(
            "AcquireControl",
            request.command_id,
            request,
            lambda: self.runtime.claim(request),
        )

    async def TakeOverControl(
        self, request: svc.ControlClaim, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.client_id)
        return await self._commands.admit(
            "TakeOverControl",
            request.command_id,
            request,
            lambda: self.runtime.claim(request, takeover=True),
        )

    async def ReleaseControl(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._commands.admit(
            "ReleaseControl",
            request.operator.command_id,
            request,
            lambda: self.runtime.release_control(request),
        )

    async def UpdateConfiguration(
        self, request: svc.UpdateConfigurationRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.command.operator.client_id)
        return await self._commands.admit(
            "UpdateConfiguration",
            request.command.operator.command_id,
            request,
            lambda: self.runtime.update_configuration(request),
        )

    async def Setup(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._commands.admit(
            "Setup",
            request.operator.command_id,
            request,
            lambda: self.runtime.setup(request),
        )

    async def CancelSetup(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._commands.admit(
            "CancelSetup",
            request.operator.command_id,
            request,
            lambda: self.runtime.cancel_setup(request),
        )

    async def StartSession(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._commands.admit(
            "StartSession",
            request.operator.command_id,
            request,
            lambda: self.runtime.start_session(request),
        )

    async def StopAfterTrial(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._commands.admit(
            "StopAfterTrial",
            request.operator.command_id,
            request,
            lambda: self.runtime.stop_after_trial(request),
        )

    async def CancelStopAfterTrial(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._commands.admit(
            "CancelStopAfterTrial",
            request.operator.command_id,
            request,
            lambda: self.runtime.stop_after_trial(request, cancel=True),
        )

    async def AbortNow(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._admit_safety(
            "AbortNow", "abort", request, lambda: self.runtime.abort_now(request)
        )

    async def NewSession(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._commands.admit(
            "NewSession",
            request.operator.command_id,
            request,
            lambda: self.runtime.new_session(request),
        )

    async def ReportLifecycle(
        self, request: pb.LifecycleReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        ingress_ns = self.runtime.clock()
        kind = request.WhichOneof("report")
        if kind is None:
            return rejected_receipt("INVALID", "empty report")
        payload = getattr(request, kind)
        if kind == "cleanup":
            role, generation = payload.source.role, payload.source.generation
        elif kind == "operation":
            role, generation = (
                payload.source.backend_name,
                payload.source.backend_generation,
            )
        else:
            role, generation = (
                payload.context.backend.backend_name,
                payload.context.backend.backend_generation,
            )
        await self._peer(context, role, generation)
        return await self._reports.enqueue("lifecycle", request, ingress_ns)

    async def ReportInterruption(
        self, request: svc.InterruptionReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        ingress_ns = self.runtime.clock()
        await self._peer(context, "supervisor", request.supervisor.generation)
        return await self._reports.enqueue("interruption", request, ingress_ns)

    async def ReportHeartbeat(
        self, request: pb.HeartbeatReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        ingress_ns = self.runtime.clock()
        await self._peer(context, "supervisor", request.source.generation)
        return await self.runtime.supervisor_heartbeat(request, ingress_ns)

    async def ReportSupervisorStatus(
        self, request: svc.SupervisorStatusReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        ingress_ns = self.runtime.clock()
        await self._peer(context, "supervisor", request.supervisor.generation)
        return await self.runtime.supervisor_status(request, ingress_ns)

    async def RespondToPrompt(
        self, request: svc.PromptResponse, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.command.operator.client_id)
        return await self._commands.admit(
            "RespondToPrompt",
            request.command.operator.command_id,
            request,
            lambda: self.runtime.respond_to_prompt(request),
        )

    async def SaveConfigurationHistory(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._commands.admit(
            "SaveConfigurationHistory",
            request.operator.command_id,
            request,
            lambda: self.runtime.save_configuration_history(request),
        )

    async def ShutdownApplication(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._admit_safety(
            "ShutdownApplication",
            "shutdown",
            request,
            lambda: self.runtime.shutdown_application(request),
        )

    async def ReportDataPreparation(
        self, request: svc.DataPreparationReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        ingress_ns = self.runtime.clock()
        await self._peer(
            context,
            request.source.backend.backend_name,
            request.source.backend.backend_generation,
        )
        return await self._reports.enqueue("preparation", request, ingress_ns)

    async def ReportVisualStimulusDisplay(
        self, request: pb.VisualStimulusDisplayView, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        await self._peer(
            context, request.backend.backend_name, request.backend.backend_generation
        )
        return await self._reports.enqueue(
            "projection:display", request, self.runtime.clock()
        )

    async def ExecuteCameraCommand(
        self, request: svc.CameraCommandRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.command.operator.client_id)
        return await self._commands.admit(
            "ExecuteCameraCommand",
            request.command.operator.command_id,
            request,
            lambda: self.runtime.execute_camera_command(request),
        )

    async def ExecuteMicrocontrollerCommand(
        self,
        request: svc.MicrocontrollerCommandRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb.CommandAdmission:
        await self._client(context, request.command.operator.client_id)
        return await self._commands.admit(
            "ExecuteMicrocontrollerCommand",
            request.command.operator.command_id,
            request,
            lambda: self.runtime.execute_microcontroller_command(request),
        )

    async def CheckSpikeGLXConnection(
        self,
        request: svc.SpikeGLXConnectionQuery,
        context: grpc.aio.ServicerContext,
    ) -> svc.SpikeGLXConnectionResult:
        await self._client(context, request.client_id)
        if self.spikeglx_diagnostic is None:
            return svc.SpikeGLXConnectionResult(error="SpikeGLX diagnostic unavailable")
        return await self.spikeglx_diagnostic.check()

    async def GetPreviewAttachment(
        self, request: svc.PreviewAttachmentQuery, context: grpc.aio.ServicerContext
    ) -> svc.PreviewAttachmentResult:
        await self._client(context, request.client_id)
        return await self.runtime.get_preview_attachment(request)

    async def ReportPreviewAttachment(
        self, request: svc.PreviewAttachmentReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        await self._peer(
            context, request.source.backend_name, request.source.backend_generation
        )
        return await self._reports.enqueue(
            "projection:preview", request, self.runtime.clock()
        )

    async def ReportPreviewConsumerState(
        self, request: svc.PreviewConsumerReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        await self._client(context, request.client_id)
        return await self.runtime.report_preview_consumer_state(request)

    async def ReportAcquisitionResolution(
        self,
        request: svc.AcquisitionResolutionReport,
        context: grpc.aio.ServicerContext,
    ) -> pb.ReportReceipt:
        await self._peer(
            context, request.source.backend_name, request.source.backend_generation
        )
        return await self._reports.enqueue("resolution", request, self.runtime.clock())

    async def ReportAcquisitionDeviceStatus(
        self,
        request: svc.AcquisitionDeviceStatusReport,
        context: grpc.aio.ServicerContext,
    ) -> pb.ReportReceipt:
        await self._peer(
            context,
            request.views.source.backend_name,
            request.views.source.backend_generation,
        )
        return await self._reports.enqueue(
            "projection:devices", request, self.runtime.clock()
        )

    async def ReportAcquisitionWarnings(
        self, request: svc.AcquisitionWarningReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        await self._peer(
            context, request.source.backend_name, request.source.backend_generation
        )
        return await self._reports.enqueue(
            "projection:warnings", request, self.runtime.clock()
        )


async def start_controller_server(
    runtime: ControllerRuntime,
    *,
    port: int,
    max_message_bytes: int,
    client_authentication: ClientAuthentication,
    peer_tokens: Mapping[str, tuple[str, str]],
    max_pending_events: int = 1024,
    max_pending_payload_bytes: int = 67_108_864,
    command_retention_ns: int = 300_000_000_000,
    software_root: Path | None = None,
) -> grpc.aio.Server:
    if not 0 < port <= 65535 or max_message_bytes <= 0:
        raise ValueError("invalid controller endpoint settings")
    server = grpc.aio.server(
        options=(
            ("grpc.max_receive_message_length", max_message_bytes),
            ("grpc.max_send_message_length", max_message_bytes),
        )
    )
    servicer = ExperimentControllerService(
        runtime,
        client_authentication=client_authentication,
        peer_tokens=peer_tokens,
        max_pending_events=max_pending_events,
        max_pending_payload_bytes=max_pending_payload_bytes,
        max_message_bytes=max_message_bytes,
        command_retention_ns=command_retention_ns,
        spikeglx_diagnostic=SpikeGLXDiagnostic(software_root)
        if software_root is not None
        else None,
    )
    rpc.add_ExperimentControllerServiceServicer_to_server(servicer, server)  # type: ignore[no-untyped-call]
    bound4 = server.add_insecure_port(f"127.0.0.1:{port}")
    if bound4 != port:
        await servicer.aclose()
        raise RuntimeError("configured controller loopback port unavailable")
    try:
        await server.start()
    except BaseException:
        await servicer.aclose()
        raise

    async def close_after_stop() -> None:
        try:
            await server.wait_for_termination()
        finally:
            await servicer.aclose()

    asyncio.create_task(close_after_stop())
    return server
