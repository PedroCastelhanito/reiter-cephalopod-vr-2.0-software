"""E08 exact peer identity, original deadlines and shared retained admissions."""

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

SAFETY = frozenset(
    {
        "CancelSetup",
        "StopTrial",
        "AbortTrial",
        "InterruptSession",
        "Cleanup",
        "Shutdown",
        "ApplyIncidentScope",
    }
)


class Operations(Protocol):
    def validate_command(self, method: str, request: Message) -> None: ...
    async def execute(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def query(self, method: str, request: Message) -> Message: ...
    async def failed_command(
        self,
        method: str,
        command: wire.BackendCommand,
        outcome: pb.OperationState,
        deadline_ns: int,
    ) -> None: ...


def command_of(request: Message) -> wire.BackendCommand:
    if isinstance(request, wire.BackendCommand):
        return request
    value = getattr(request, "command", None)
    if not isinstance(value, wire.BackendCommand):
        raise ValueError("request has no backend command")
    return value


class Boundary:
    def __init__(
        self,
        operations: Operations,
        credentials: MutableMapping[tuple[str, str], str],
        admission: CommandAdmissionTransport,
    ) -> None:
        self.operations, self.credentials, self.admission = (
            operations,
            credentials,
            admission,
        )

    async def authenticate(
        self,
        context: grpc.aio.ServicerContext,
        roles: frozenset[str],
        source: pb.ProcessIdentity | None = None,
    ) -> None:
        metadata = context.invocation_metadata()
        fields = dict(metadata)
        role, generation = (
            str(fields.get("x-cephvr-role")),
            str(fields.get("x-cephvr-generation")),
        )
        token = self.credentials.get((role, generation))
        if (
            token is None
            or role not in roles
            or source is not None
            and (source.role, source.generation) != (role, generation)
        ):
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "unregistered Tracking peer or mismatched source",
            )
            return
        try:
            require_authenticated_peer(
                context.peer(),
                metadata,
                expected_role=role,
                expected_generation=generation,
                expected_token=token,
            )
        except AuthenticationError as exc:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))

    async def command(
        self, method: str, request: Message, context: grpc.aio.ServicerContext
    ) -> pb.CommandAdmission:
        command = command_of(request)
        await self.authenticate(
            context,
            frozenset({"controller", "supervisor"})
            if method in SAFETY
            else frozenset({"controller"}),
            command.issuer,
        )
        try:
            deadline = parse_deadline_metadata(context.invocation_metadata())
            if not self.admission.is_retained(command.command_id):
                self.operations.validate_command(method, request)
        except (ValueError, DeadlineMetadataError) as exc:
            return pb.CommandAdmission(
                command_id=command.command_id,
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(code="TRACKING_ADMISSION", message=str(exc)),
            )
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
        source = command_of(request).issuer if method == "GetPreparation" else None
        await self.authenticate(
            context, frozenset({"controller", "supervisor"}), source
        )
        try:
            return await self.operations.query(method, request)
        except ValueError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
            raise AssertionError("unreachable") from exc
