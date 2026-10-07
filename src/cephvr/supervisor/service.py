"""Authenticated supervisor gRPC admission and loopback service (E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import grpc

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.auth import AuthenticationError, require_authenticated_peer
from cephvr.shared.clock import HostClockDescriptor, host_time_ns
from cephvr.shared.transport_deadlines import parse_deadline_metadata
from cephvr.supervisor.health import HealthMonitor
from cephvr.supervisor.receipts import (
    accepted,
    rejected,
    report_accepted,
    report_rejected,
)
from cephvr.supervisor.recovery import RecoveryCoordinator
from cephvr.supervisor.registration import RegistrationCoordinator
from cephvr.supervisor.registry import BACKEND_ROLES, LaunchError, LaunchRegistry
from cephvr.supervisor.shutdown import ShutdownCoordinator
from cephvr.supervisor.status import StatusPublisher


class SupervisorService(services_pb2_grpc.SupervisorServiceServicer):
    def __init__(
        self,
        *,
        identity: types.ProcessIdentity,
        controller: types.ProcessIdentity,
        credentials: dict[tuple[str, str], str],
        registry: LaunchRegistry,
        registration: RegistrationCoordinator,
        health: HealthMonitor,
        recovery: RecoveryCoordinator,
        shutdown: ShutdownCoordinator,
        status: StatusPublisher,
        lock: asyncio.Lock,
        clock: HostClockDescriptor,
        max_message_bytes: int,
    ) -> None:
        self.identity = identity
        self.controller = controller
        self.credentials = credentials
        self.registry = registry
        self.registration = registration
        self.health = health
        self.recovery = recovery
        self.shutdown = shutdown
        self.status = status
        self.lock = lock
        self.clock = clock
        self.max_message_bytes = max_message_bytes
        self.gui_launch_handler: (
            Callable[
                [wire.PlanLaunchRequest, wire.LaunchState, str, int],
                Awaitable[wire.LaunchState],
            ]
            | None
        ) = None

    async def _authenticate(
        self, context: grpc.aio.ServicerContext, source: types.ProcessIdentity
    ) -> None:
        key = source.role, source.generation
        token = self.credentials.get(key)
        if token is None:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED, "unregistered process generation"
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

    async def _reject(
        self, context: grpc.aio.ServicerContext, error: Exception
    ) -> None:
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))

    async def PlanLaunch(
        self, request: wire.PlanLaunchRequest, context: grpc.aio.ServicerContext
    ) -> wire.LaunchReceipt:
        await self._authenticate(context, request.owner)
        if (
            # Workers own their helpers (e.g. camera worker -> FFmpeg).
            not self.registration.source_registered(request.owner, allow_worker=True)
            and request.owner != self.identity
        ):
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, "owner is not registered"
            )
        if request.HasField("work") and not self.registration.same_work(request.work):
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, "work context differs"
            )
        child_key = request.child.role, request.child.generation
        child_tokens = [
            value
            for key, value in context.invocation_metadata()
            if key == "x-cephvr-child-token"
        ]
        known = self.credentials.get(child_key)
        if len(child_tokens) > 1 or (
            known is None and (len(child_tokens) != 1 or not child_tokens[0])
        ):
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "one protected child token is required",
            )
        if known is not None and child_tokens and child_tokens[0] != known:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "child token differs from registration",
            )
        try:
            # Helper release is the health monitor's job, never a launch-path wait.
            deadline_ns = parse_deadline_metadata(context.invocation_metadata())
            if deadline_ns <= host_time_ns():
                raise LaunchError("EXPIRED", "PlanLaunch arrived after its deadline")
            async with self.lock:
                state = self.registry.plan(request)
                if known is None:
                    self.credentials[child_key] = child_tokens[0]
            if request.child.role == "gui" and self.gui_launch_handler is not None:
                token = known or child_tokens[0]
                state = await self.gui_launch_handler(
                    request, state, token, deadline_ns
                )
            self.status.changed()
            return wire.LaunchReceipt(
                admission=accepted(request.command_id), state=state
            )
        except (LaunchError, ValueError) as exc:
            return wire.LaunchReceipt(admission=rejected(request.command_id, exc))

    async def ConfirmLaunch(
        self, request: wire.ConfirmLaunchRequest, context: grpc.aio.ServicerContext
    ) -> wire.LaunchReceipt:
        try:
            # The owner confirms the OS stage; a Python child confirms its own
            # bootstrap endpoint after resume. Both remain bound to the one plan.
            # Authenticate before touching the registry or native inspection.
            confirmer = request.child if request.HasField("endpoint") else request.owner
            await self._authenticate(context, confirmer)
            planned = self.registry.refresh(request.launch_command_id)
            if request.child == self.controller and request.HasField("endpoint"):
                try:
                    await asyncio.wait_for(
                        self.shutdown.state.controller_ack.wait(), timeout=15
                    )
                except TimeoutError as exc:
                    raise LaunchError(
                        "LAUNCHER_ACK_TIMEOUT",
                        "launcher did not retain controller handle",
                    ) from exc
            if confirmer == request.child and planned.phase not in (
                wire.LAUNCH_PHASE_OS_CONFIRMED,
                wire.LAUNCH_PHASE_OPERATIONAL,
            ):
                raise LaunchError(
                    "WRONG_STAGE",
                    "child endpoint confirmation requires OS confirmation",
                )
            async with self.lock:
                state = self.registry.confirm(request, self.clock)
                if (
                    state.phase == wire.LAUNCH_PHASE_OPERATIONAL
                    and planned.phase != wire.LAUNCH_PHASE_OPERATIONAL
                    and request.child.role in BACKEND_ROLES | {"controller"}
                ):
                    self.health.state.last_heartbeat[
                        (request.child.role, request.child.generation)
                    ] = host_time_ns()
            self.status.changed()
            return wire.LaunchReceipt(
                admission=accepted(request.command_id), state=state
            )
        except (LaunchError, ValueError) as exc:
            return wire.LaunchReceipt(admission=rejected(request.command_id, exc))

    async def GetLaunchState(
        self, request: wire.LaunchQuery, context: grpc.aio.ServicerContext
    ) -> wire.LaunchState:
        await self._authenticate(context, request.requester)
        try:
            plan = self.registry.planned_request(request.launch_command_id)
            if request.requester not in (plan.owner, self.controller, self.identity):
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED, "not launch owner"
                )
            state = self.registry.refresh(request.launch_command_id)
            if (
                request.requester == self.identity
                and state.plan.child.role == "gui"
                and state.phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
            ):
                state = self.registry.release_gui_if_empty(request.launch_command_id)
                self.status.changed()
            return state
        except LaunchError as exc:
            await self._reject(context, exc)
            raise AssertionError("unreachable") from exc

    async def RegisterContext(
        self, request: wire.RegisterContextRequest, context: grpc.aio.ServicerContext
    ) -> wire.RegistrationReceipt:
        await self._authenticate(context, request.context.controller)
        return await self.registration.register_context(request)

    async def ReportHeartbeat(
        self, request: types.HeartbeatReport, context: grpc.aio.ServicerContext
    ) -> types.ReportReceipt:
        ingress_ns = host_time_ns()
        await self._authenticate(context, request.source)
        return await self.health.report_heartbeat(request, ingress_ns)

    async def ReportError(
        self, request: types.ErrorReport, context: grpc.aio.ServicerContext
    ) -> types.ReportReceipt:
        await self._authenticate(context, request.source)
        return await self.health.report_error(request)

    async def ReportLifecycle(
        self, request: types.LifecycleReport, context: grpc.aio.ServicerContext
    ) -> types.ReportReceipt:
        if request.WhichOneof("report") != "cleanup":
            return report_rejected(
                "INVALID_LIFECYCLE", "supervisor accepts top-level Cleanup only"
            )
        await self._authenticate(context, request.cleanup.source)
        ingress_ns = host_time_ns()
        try:
            deadline_ns = parse_deadline_metadata(context.invocation_metadata())
        except ValueError as exc:
            return report_rejected("INVALID_DEADLINE", str(exc))
        if ingress_ns > deadline_ns:
            return report_rejected(
                "EXPIRED", "Cleanup arrived after its original deadline"
            )
        return await self.recovery.report_lifecycle(
            request, deadline_ns=deadline_ns, ingress_ns=ingress_ns
        )

    async def ReportPreviewConsumerState(
        self, request: wire.PreviewConsumerReport, context: grpc.aio.ServicerContext
    ) -> types.ReportReceipt:
        await self._authenticate(context, request.consumer)
        if request.result == wire.PREVIEW_CONSUMER_RESULT_ATTACHED:
            return report_rejected("INVALID_PREVIEW", "ATTACHED belongs to controller")
        if (
            not self.registration.source_registered(request.consumer, allow_worker=True)
            or request.controller_generation != self.controller.generation
        ):
            return report_rejected(
                "WRONG_CONTEXT", "preview consumer is not registered"
            )
        return report_accepted()

    async def GetRecoveryState(
        self, request: wire.RecoveryQuery, context: grpc.aio.ServicerContext
    ) -> wire.RecoverySnapshot:
        await self._authenticate(context, self.controller)
        try:
            return await self.recovery.get_recovery_state(request)
        except ValueError as exc:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
            raise AssertionError("unreachable") from exc

    async def ExecuteRecoveryAction(
        self, request: wire.RecoveryActionRequest, context: grpc.aio.ServicerContext
    ) -> types.CommandAdmission:
        await self._authenticate(context, self.controller)
        return await self.recovery.execute_recovery_action(request)

    async def RequestApplicationShutdown(
        self,
        request: wire.ApplicationShutdownRequest,
        context: grpc.aio.ServicerContext,
    ) -> types.CommandAdmission:
        await self._authenticate(context, self.controller)
        return await self.shutdown.request_application_shutdown(request)


async def start_supervisor_server(
    service: SupervisorService, port: int
) -> grpc.aio.Server:
    if not 1 <= port <= 65535:
        raise ValueError("invalid supervisor port")
    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", service.max_message_bytes),
            ("grpc.max_receive_message_length", service.max_message_bytes),
        ]
    )
    services_pb2_grpc.add_SupervisorServiceServicer_to_server(service, server)  # type: ignore[no-untyped-call]
    for host in ("127.0.0.1", "[::1]"):
        if server.add_insecure_port(f"{host}:{port}") == 0:
            raise RuntimeError(f"supervisor loopback port {port} unavailable on {host}")
    await server.start()
    return server
