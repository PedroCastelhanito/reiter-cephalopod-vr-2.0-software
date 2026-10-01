"""Authenticated Visual Stimulus RPC admission; mechanism reuse without backend policy sharing."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Protocol

import grpc
from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.admission import CommandAdmissionTransport
from cephvr.shared.auth import AuthenticationError, require_authenticated_peer
from cephvr.shared.transport_deadlines import (
    DeadlineMetadataError,
    parse_deadline_metadata,
)
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus

from .messages import backend_command, worker_command

SAFETY = frozenset(
    {
        "CancelSetup",
        "StopTrial",
        "AbortTrial",
        "InterruptSession",
        "Cleanup",
        "Shutdown",
    }
)


class Operations(Protocol):
    async def execute(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def query(self, method: str, request: Message) -> Message: ...
    async def report(
        self, method: str, request: Message, *, ingress_ns: int
    ) -> pb.ReportReceipt: ...
    def validate_command(self, method: str, request: Message) -> None: ...
    async def failed_command(
        self,
        method: str,
        command: wire.BackendCommand,
        outcome: pb.OperationState,
        deadline_ns: int,
    ) -> None: ...


class Boundary:
    def __init__(
        self,
        operations: Operations,
        credentials: MutableMapping[tuple[str, str], str],
        admission: CommandAdmissionTransport,
        *,
        worker: bool = False,
    ) -> None:
        self.operations = operations
        self.credentials = credentials
        self.admission = admission
        self.worker = worker

    async def authenticate(
        self,
        context: grpc.aio.ServicerContext,
        roles: frozenset[str],
        source: pb.ProcessIdentity | None = None,
    ) -> None:
        metadata = context.invocation_metadata()
        fields = dict(metadata)
        role = fields.get("x-cephvr-role")
        generation = fields.get("x-cephvr-generation")
        token = self.credentials.get((str(role), str(generation)))
        if (
            token is None
            or role not in roles
            or (
                source is not None
                and (source.role, source.generation) != (role, generation)
            )
        ):
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "unregistered Visual Stimulus peer or mismatched source",
            )
            return
        try:
            require_authenticated_peer(
                context.peer(),
                metadata,
                expected_role=str(role),
                expected_generation=str(generation),
                expected_token=token,
            )
        except AuthenticationError as exc:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))

    async def command(
        self, method: str, request: Message, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        native = (
            worker_command(request)
            if self.worker
            else (
                request
                if isinstance(request, wire.VisualStimulusDisplayInitializationRequest)
                else backend_command(request)
            )
        )
        owner = "visual_stimulus" if self.worker else "controller"
        roles = (
            frozenset({owner, "supervisor"}) if method in SAFETY else frozenset({owner})
        )
        await self.authenticate(context, roles, native.issuer)
        try:
            deadline = parse_deadline_metadata(context.invocation_metadata())
            if isinstance(
                native,
                (
                    visual_stimulus.WorkerCommand,
                    wire.VisualStimulusDisplayInitializationRequest,
                ),
            ):
                if native.deadline_monotonic_ns <= 0:
                    raise ValueError("positive original command deadline required")
                deadline = min(deadline, native.deadline_monotonic_ns)
            if not self.admission.is_retained(native.command_id):
                self.operations.validate_command(method, request)
        except (DeadlineMetadataError, ValueError) as exc:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=native.command_id,
                failure=pb.Failure(code="VISUAL_STIMULUS_ADMISSION", message=str(exc)),
            )
        if isinstance(native, visual_stimulus.WorkerCommand):
            command = wire.BackendCommand(
                command_id=native.command_id,
                issuer=native.issuer,
                target=pb.BackendContext(
                    backend_name=native.target.worker.role,
                    backend_generation=native.target.worker.generation,
                ),
                work=native.target.work,
                parent_operation=native.parent_operation,
            )
        elif isinstance(native, wire.VisualStimulusDisplayInitializationRequest):
            command = wire.BackendCommand(
                command_id=native.command_id, issuer=native.issuer, target=native.target
            )
        else:
            command = native
        return await self.admission.dispatch(
            method,
            request,
            command,
            deadline,
            lambda *, deadline_ns: self.operations.execute(
                method, request, deadline_ns=deadline_ns
            ),
            priority=method in SAFETY,
        )

    async def query(
        self, method: str, request: Message, context: grpc.aio.ServicerContext
    ) -> Message:
        await self.authenticate(
            context,
            frozenset({"visual_stimulus", "supervisor"})
            if self.worker
            else frozenset({"controller", "supervisor"}),
        )
        try:
            return await self.operations.query(method, request)
        except ValueError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
            raise AssertionError("unreachable") from exc

    async def report(
        self, method: str, request: Message, context: grpc.aio.ServicerContext
    ) -> pb.ReportReceipt:
        from cephvr.shared.clock import host_time_ns

        ingress = host_time_ns()
        source = (
            request.source.worker
            if isinstance(request, visual_stimulus.WorkerOperation)
            else request.source
            if isinstance(
                request,
                (
                    visual_stimulus.WorkerLifecycle,
                    pb.VisualStimulusDisplayView,
                    pb.HeartbeatReport,
                ),
            )
            else pb.ProcessIdentity()
        )
        await self.authenticate(
            context, frozenset({"visual_stimulus_renderer"}), source
        )
        try:
            return await self.operations.report(method, request, ingress_ns=ingress)
        except (ValueError, RuntimeError) as exc:
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(code="VISUAL_STIMULUS_EVIDENCE", message=str(exc)),
            )
