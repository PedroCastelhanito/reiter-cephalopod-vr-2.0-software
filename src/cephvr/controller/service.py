"""Loopback gRPC front door for the authoritative controller (E02/E03/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import cast

import grpc
from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.runtime import ControllerRuntime
from cephvr.shared.auth import AuthenticationError, require_authenticated_peer
from cephvr.shared.commands import CommandCapacityError, CommandConflict, CommandLedger
from cephvr.shared.credentials import CredentialError, CredentialStore
from cephvr.shared.ingress import BoundedEventIngress, IngressOverload

ClientAuthentication = Callable[[str, str, str, object], Awaitable[None]]


def credential_store_authentication(
    store: CredentialStore, *, timeout_s: float = 2.0
) -> ClientAuthentication:
    """Resolve a bounded local credential outside the lifecycle state loop."""

    async def authenticate(
        client_id: str, controller_generation: str, peer: str, metadata: object
    ) -> None:
        if controller_generation != store.controller_generation:
            raise AuthenticationError("controller generation mismatch")
        try:
            principal = await asyncio.wait_for(
                asyncio.to_thread(store.lookup, client_id), timeout_s
            )
        except (TimeoutError, CredentialError, ValueError) as exc:
            raise AuthenticationError("operator credential unavailable") from exc
        if principal is None:
            raise AuthenticationError("operator credential missing")
        require_authenticated_peer(
            peer,
            cast(list[tuple[str, str]], metadata),
            expected_role=principal.role,
            expected_generation=principal.generation,
            expected_token=principal.token,
        )

    return authenticate


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
    ) -> None:
        self.runtime = runtime
        self.client_authentication = client_authentication
        self.peer_tokens = dict(peer_tokens)
        self._ledger = CommandLedger(
            runtime.generation,
            command_retention_ns,
            max_records=max_pending_events,
            max_bytes=max_pending_payload_bytes,
            result_reservation_bytes=4096,
        )
        self._abort_ledger = CommandLedger(
            runtime.generation,
            command_retention_ns,
            max_records=8,
            max_bytes=65_536,
            result_reservation_bytes=4096,
        )
        self._shutdown_ledger = CommandLedger(
            runtime.generation,
            command_retention_ns,
            max_records=8,
            max_bytes=65_536,
            result_reservation_bytes=4096,
        )
        self._pending_commands: dict[str, asyncio.Future[pb.CommandAdmission]] = {}
        self._command_tasks: set[asyncio.Task[None]] = set()
        self._closed = False
        self._setup_work_key: str | None = None
        self._session_work_key: str | None = None
        self._camera_work_keys: set[str] = set()
        self._ingress: BoundedEventIngress[
            tuple[str, object, int, asyncio.Future[pb.ReportReceipt]]
        ] = BoundedEventIngress(
            max_pending_events,
            max_pending_payload_bytes,
            max_interruption_payload_bytes=max_message_bytes,
        )
        self._ingress_event = asyncio.Event()
        self._active_report_future: asyncio.Future[pb.ReportReceipt] | None = None
        self._event_task = asyncio.create_task(self._drain_ingress())
        self._ledger_task = asyncio.create_task(self._ledger_housekeeping())

    async def _ledger_housekeeping(self) -> None:
        while True:
            await asyncio.sleep(1)
            self._retire_clean_work()
            for key in tuple(self._camera_work_keys):
                operation = self.runtime._operations.get(key)
                if operation is not None and operation.complete:
                    self._ledger.finalize_work(key, self.runtime.clock())
                    self._camera_work_keys.discard(key)
            self._ledger.prune(self.runtime.clock())
            self._abort_ledger.prune(self.runtime.clock())
            self._shutdown_ledger.prune(self.runtime.clock())

    def _retire_clean_work(self) -> None:
        if (
            not self.runtime.session.cleanup_confirmed
            or self.runtime.session.phase
            not in (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_ENDED)
        ):
            return
        for key in (self._setup_work_key, self._session_work_key):
            if key is not None:
                try:
                    self._ledger.finalize_work(key, self.runtime.clock())
                except ValueError:
                    pass
                for ledger in (self._abort_ledger, self._shutdown_ledger):
                    try:
                        ledger.finalize_work(key, self.runtime.clock())
                    except ValueError:
                        pass
        self._setup_work_key = None
        self._session_work_key = None

    async def _command(
        self,
        name: str,
        command_id: str,
        request: Message,
        action: Callable[[], Awaitable[pb.CommandAdmission]],
    ) -> pb.CommandAdmission:
        if self._closed:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=command_id,
                failure=pb.Failure(
                    code="SHUTDOWN", message="controller service is closing"
                ),
            )
        canonical = (
            name.encode() + b"\0" + request.SerializeToString(deterministic=True)
        )
        ledger = (
            self._abort_ledger
            if name == "AbortNow"
            else self._shutdown_ledger
            if name == "ShutdownApplication"
            else self._ledger
        )
        other_ledgers = tuple(
            other
            for other in (self._ledger, self._abort_ledger, self._shutdown_ledger)
            if other is not ledger
        )
        synchronous = name in {
            "AcquireControl",
            "TakeOverControl",
            "ReleaseControl",
            "UpdateConfiguration",
            "RespondToPrompt",
            "SaveConfigurationHistory",
            "NewSession",
        }
        work_key = (
            command_id
            if synchronous
            or name in {"Setup", "ExecuteCameraCommand"}
            or self.runtime.attempt is None
            else self.runtime.attempt.context.session_id
        )
        try:
            if any(other.get(command_id) is not None for other in other_ledgers):
                raise CommandConflict(
                    "command ID already belongs to another admission lane"
                )
            admission = ledger.admit(
                command_id, canonical, self.runtime.clock(), work_key=work_key
            )
        except (ValueError, CommandConflict, CommandCapacityError) as exc:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=command_id,
                failure=pb.Failure(code="ADMISSION", message=str(exc)),
            )
        if admission.replayed:
            if admission.record.result is not None:
                return pb.CommandAdmission.FromString(admission.record.result)
            pending = self._pending_commands.get(command_id)
            if pending is not None:
                return await asyncio.shield(pending)
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=command_id,
                failure=pb.Failure(
                    code="PENDING", message="matching command admission is pending"
                ),
            )
        future: asyncio.Future[pb.CommandAdmission] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_commands[command_id] = future
        task = asyncio.create_task(
            self._execute_command(
                ledger, name, command_id, work_key, synchronous, action, future
            )
        )
        self._command_tasks.add(task)
        task.add_done_callback(self._command_tasks.discard)
        return await asyncio.shield(future)

    async def _execute_command(
        self,
        ledger: CommandLedger,
        name: str,
        command_id: str,
        work_key: str,
        synchronous: bool,
        action: Callable[[], Awaitable[pb.CommandAdmission]],
        future: asyncio.Future[pb.CommandAdmission],
    ) -> None:
        try:
            result = await action()
            ledger.complete(
                command_id,
                result.SerializeToString(deterministic=True),
                self.runtime.clock(),
            )
            if synchronous or result.result == pb.COMMAND_RESULT_REJECTED:
                ledger.finalize_work(work_key, self.runtime.clock())
            elif name == "Setup":
                self._setup_work_key = work_key
                if self.runtime.attempt is not None:
                    self._session_work_key = self.runtime.attempt.context.session_id
            elif name == "ExecuteCameraCommand":
                self._camera_work_keys.add(work_key)
            elif self.runtime.attempt is not None:
                self._session_work_key = self.runtime.attempt.context.session_id
            if name == "NewSession" and result.result == pb.COMMAND_RESULT_ACCEPTED:
                self._retire_clean_work()
            if not future.done():
                future.set_result(result)
        except asyncio.CancelledError:
            result = pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=command_id,
                failure=pb.Failure(
                    code="SHUTDOWN",
                    message="controller service closed before admission completed",
                ),
            )
            ledger.complete(
                command_id,
                result.SerializeToString(deterministic=True),
                self.runtime.clock(),
            )
            ledger.finalize_work(work_key, self.runtime.clock())
            if not future.done():
                future.set_result(result)
            raise
        except Exception as exc:
            result = pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=command_id,
                failure=pb.Failure(code="INTERNAL", message=str(exc)),
            )
            ledger.complete(
                command_id,
                result.SerializeToString(deterministic=True),
                self.runtime.clock(),
            )
            ledger.finalize_work(work_key, self.runtime.clock())
            if not future.done():
                future.set_result(result)
        finally:
            self._pending_commands.pop(command_id, None)

    async def _drain_ingress(self) -> None:
        while True:
            await self._ingress_event.wait()
            while (item := self._ingress.take()) is not None:
                kind, request, ingress_ns, future = item.event
                self._active_report_future = future
                try:
                    if kind == "lifecycle":
                        result = await self.runtime.report_lifecycle(
                            cast(pb.LifecycleReport, request), ingress_ns
                        )
                    elif kind == "preparation":
                        result = await self.runtime.report_data_preparation(
                            cast(svc.DataPreparationReport, request), ingress_ns
                        )
                    elif kind == "resolution":
                        result = await self.runtime.report_acquisition_resolution(
                            cast(svc.AcquisitionResolutionReport, request), ingress_ns
                        )
                    elif kind.startswith("projection:"):
                        result = await self.runtime.report_projection(
                            kind.removeprefix("projection:"),
                            cast(Message, request),
                            ingress_ns,
                        )
                    else:
                        result = await self.runtime.report_interruption(
                            cast(svc.InterruptionReport, request)
                        )
                except Exception as exc:
                    result = pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(code="INTERNAL", message=str(exc)),
                    )
                if not future.done():
                    future.set_result(result)
                self._active_report_future = None
            self._ingress_event.clear()

    async def _enqueue_report(
        self, kind: str, request: Message, ingress_ns: int
    ) -> pb.ReportReceipt:
        if self._closed:
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="SHUTDOWN", message="controller service is closing"
                ),
            )
        future: asyncio.Future[pb.ReportReceipt] = (
            asyncio.get_running_loop().create_future()
        )
        serialized = request.SerializeToString(deterministic=True)
        try:
            if kind == "interruption":
                fresh = self._ingress.put_interruption(
                    serialized, (kind, request, ingress_ns, future)
                )
                if not fresh:
                    return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            else:
                accepted = self._ingress.put(
                    serialized,
                    (kind, request, ingress_ns, future),
                    essential=kind in {"lifecycle", "preparation", "resolution"},
                    ingress_ns=ingress_ns,
                )
                if not accepted:
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="OVERLOAD", message="controller report ingress full"
                        ),
                    )
        except IngressOverload as exc:
            if self.runtime.attempt is not None:
                self.runtime._spawn(
                    self.runtime._interrupt(
                        self.runtime.attempt,
                        f"essential controller ingress exhausted: {exc}",
                    )
                )
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(code="OVERLOAD", message=str(exc)),
            )
        self._ingress_event.set()
        return await future

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        closing = pb.ReportReceipt(
            result=pb.COMMAND_RESULT_REJECTED,
            failure=pb.Failure(
                code="SHUTDOWN",
                message="controller service closed before report processing",
            ),
        )
        while (item := self._ingress.take()) is not None:
            future = item.event[3]
            if not future.done():
                future.set_result(closing)
        if (
            self._active_report_future is not None
            and not self._active_report_future.done()
        ):
            self._active_report_future.set_result(closing)
        tasks = (self._event_task, self._ledger_task, *tuple(self._command_tasks))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for pending_command in self._pending_commands.values():
            if not pending_command.done():
                pending_command.set_result(
                    pb.CommandAdmission(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="SHUTDOWN", message="controller service closed"
                        ),
                    )
                )

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
        return await self._command(
            "AcquireControl",
            request.command_id,
            request,
            lambda: self.runtime.claim(request),
        )

    async def TakeOverControl(
        self, request: svc.ControlClaim, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.client_id)
        return await self._command(
            "TakeOverControl",
            request.command_id,
            request,
            lambda: self.runtime.claim(request, takeover=True),
        )

    async def ReleaseControl(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._command(
            "ReleaseControl",
            request.operator.command_id,
            request,
            lambda: self.runtime.release_control(request),
        )

    async def UpdateConfiguration(
        self, request: svc.UpdateConfigurationRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.command.operator.client_id)
        return await self._command(
            "UpdateConfiguration",
            request.command.operator.command_id,
            request,
            lambda: self.runtime.update_configuration(request),
        )

    async def Setup(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._command(
            "Setup",
            request.operator.command_id,
            request,
            lambda: self.runtime.setup(request),
        )

    async def CancelSetup(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._command(
            "CancelSetup",
            request.operator.command_id,
            request,
            lambda: self.runtime.cancel_setup(request),
        )

    async def StartSession(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._command(
            "StartSession",
            request.operator.command_id,
            request,
            lambda: self.runtime.start_session(request),
        )

    async def StopAfterTrial(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._command(
            "StopAfterTrial",
            request.operator.command_id,
            request,
            lambda: self.runtime.stop_after_trial(request),
        )

    async def CancelStopAfterTrial(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._command(
            "CancelStopAfterTrial",
            request.operator.command_id,
            request,
            lambda: self.runtime.stop_after_trial(request, cancel=True),
        )

    async def AbortNow(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        try:
            fresh = self._abort_ledger.get(request.operator.command_id) is None
        except ValueError as exc:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=request.operator.command_id,
                failure=pb.Failure(code="ADMISSION", message=str(exc)),
            )
        if fresh:
            async with self.runtime._lock:
                error = self.runtime._authorized(request, safety="abort")
                if (
                    error
                    or self.runtime.attempt is None
                    or self.runtime.session.phase
                    not in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
                ):
                    return pb.CommandAdmission(
                        result=pb.COMMAND_RESULT_REJECTED,
                        command_id=request.operator.command_id,
                        failure=pb.Failure(
                            code="PRECONDITION", message=error or "Abort unavailable"
                        ),
                    )
        return await self._command(
            "AbortNow",
            request.operator.command_id,
            request,
            lambda: self.runtime.abort_now(request),
        )

    async def NewSession(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._command(
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
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(code="INVALID", message="empty report"),
            )
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
        return await self._enqueue_report("lifecycle", request, ingress_ns)

    async def ReportInterruption(
        self, request: svc.InterruptionReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        ingress_ns = self.runtime.clock()
        await self._peer(context, "supervisor", request.supervisor.generation)
        return await self._enqueue_report("interruption", request, ingress_ns)

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
        return await self._command(
            "RespondToPrompt",
            request.command.operator.command_id,
            request,
            lambda: self.runtime.respond_to_prompt(request),
        )

    async def SaveConfigurationHistory(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        return await self._command(
            "SaveConfigurationHistory",
            request.operator.command_id,
            request,
            lambda: self.runtime.save_configuration_history(request),
        )

    async def ShutdownApplication(
        self, request: svc.OperatorCommand, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.operator.client_id)
        try:
            fresh = self._shutdown_ledger.get(request.operator.command_id) is None
        except ValueError as exc:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=request.operator.command_id,
                failure=pb.Failure(code="ADMISSION", message=str(exc)),
            )
        if fresh:
            async with self.runtime._lock:
                error = self.runtime._authorized(request, safety="shutdown")
                if error or self.runtime.session.shutdown_requested:
                    return pb.CommandAdmission(
                        result=pb.COMMAND_RESULT_REJECTED,
                        command_id=request.operator.command_id,
                        failure=pb.Failure(
                            code="PRECONDITION",
                            message=error or "shutdown already requested",
                        ),
                    )
        return await self._command(
            "ShutdownApplication",
            request.operator.command_id,
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
        return await self._enqueue_report("preparation", request, ingress_ns)

    async def ReportVRDisplay(
        self, request: pb.VRDisplayView, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        await self._peer(
            context, request.backend.backend_name, request.backend.backend_generation
        )
        return await self._enqueue_report(
            "projection:display", request, self.runtime.clock()
        )

    async def ExecuteCameraCommand(
        self, request: svc.CameraCommandRequest, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        await self._client(context, request.command.operator.client_id)
        return await self._command(
            "ExecuteCameraCommand",
            request.command.operator.command_id,
            request,
            lambda: self.runtime.execute_camera_command(request),
        )

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
        return await self._enqueue_report(
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
        return await self._enqueue_report("resolution", request, self.runtime.clock())

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
        return await self._enqueue_report(
            "projection:devices", request, self.runtime.clock()
        )

    async def ReportAcquisitionWarnings(
        self, request: svc.AcquisitionWarningReport, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        await self._peer(
            context, request.source.backend_name, request.source.backend_generation
        )
        return await self._enqueue_report(
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
