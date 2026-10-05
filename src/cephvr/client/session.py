"""E02 headless client with an exact live WatchState control lease."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

import grpc

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import services_pb2_grpc as transport
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.auth import Principal


class ClientError(RuntimeError):
    """The requested command or authoritative state could not be confirmed."""

    def __init__(self, message: str, *, command_id: str | None = None) -> None:
        super().__init__(message)
        self.command_id = command_id


@dataclass(frozen=True)
class CommandOutcome:
    command_id: str
    complete: bool
    succeeded: bool | None
    needs_input: bool = False
    failure: str = ""


class StateViews:
    """Install complete views and retain configuration only within one stream."""

    def __init__(self) -> None:
        self.current: pb.Snapshot | None = None

    def install(self, view: pb.Snapshot) -> None:
        previous = self.current
        if previous is not None:
            if previous.controller_generation != view.controller_generation:
                raise ClientError("Controller generation changed; resynchronize.")
            if view.state_revision <= previous.state_revision:
                return
        if not view.HasField("configuration_values"):
            if previous is None or (
                previous.configuration.revision != view.configuration.revision
            ):
                raise ClientError("State view lacks its matching configuration.")
        elif view.configuration_values.revision != view.configuration.revision:
            raise ClientError("State/configuration revisions do not match.")
        installed = pb.Snapshot()
        installed.CopyFrom(view)
        if not installed.HasField("configuration_values"):
            assert previous is not None
            installed.configuration_values.CopyFrom(previous.configuration_values)
        self.current = installed


class HeadlessClient:
    """Use the same controller RPCs and authority as a GUI client."""

    def __init__(
        self,
        channel: Any,
        principal: Principal,
        *,
        rpc_timeout_s: float = 5.0,
        on_snapshot: Callable[[pb.Snapshot], None] | None = None,
    ) -> None:
        stub_factory = cast(
            Callable[[Any], Any], transport.ExperimentControllerServiceStub
        )
        self.stub = stub_factory(channel)
        self.principal = principal
        self.rpc_timeout_s = rpc_timeout_s
        self.on_snapshot = on_snapshot
        self.views = StateViews()
        self.watch_id = ""
        self._changed = asyncio.Condition()
        self._reader: asyncio.Task[None] | None = None
        self._failure: BaseException | None = None
        self._watch: Any = None
        self.release_failure: str | None = None

    @property
    def snapshot(self) -> pb.Snapshot:
        if self.views.current is None:
            raise ClientError("WatchState has not synchronized.")
        return self.views.current

    async def get_snapshot(self) -> pb.Snapshot:
        result = await self.stub.GetSnapshot(
            rpc.SnapshotRequest(client_id=self.principal.generation),
            metadata=self.principal.metadata(),
            timeout=self.rpc_timeout_s,
        )
        fresh = StateViews()
        fresh.install(result)
        return cast(pb.Snapshot, fresh.current)

    async def _read(self) -> None:
        try:
            async for view in self._watch:
                async with self._changed:
                    self.views.install(view)
                    if self.on_snapshot is not None and self.views.current is not None:
                        self.on_snapshot(self.views.current)
                    self._changed.notify_all()
            raise ClientError("WatchState closed before completion was confirmed.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            async with self._changed:
                self._failure = exc
                self._changed.notify_all()

    async def _wait(
        self, predicate: Callable[[pb.Snapshot], bool], *, allow_closed: bool = False
    ) -> pb.Snapshot:
        async with self._changed:
            while True:
                if (
                    allow_closed
                    and self.views.current is not None
                    and predicate(self.snapshot)
                ):
                    return self.snapshot
                if self._failure is not None:
                    raise ClientError(f"State synchronization failed: {self._failure}")
                if self.views.current is not None and predicate(self.snapshot):
                    return self.snapshot
                await self._changed.wait()

    async def _admit(self, method: str, request: Any) -> pb.CommandAdmission:
        call = cast(
            Callable[..., Awaitable[pb.CommandAdmission]], getattr(self.stub, method)
        )
        if isinstance(request, rpc.ControlClaim):
            command_id = request.command_id
        elif isinstance(request, rpc.OperatorCommand):
            command_id = request.operator.command_id
        else:
            command_id = request.command.operator.command_id
        try:
            result = await call(
                request, metadata=self.principal.metadata(), timeout=self.rpc_timeout_s
            )
        except grpc.RpcError as exc:
            raise ClientError(
                "Command admission is unconfirmed after transport failure; "
                "query the retained command ID before issuing replacement work.",
                command_id=command_id,
            ) from exc
        if result.command_id != command_id:
            raise ClientError(
                "Admission command identity mismatch.", command_id=command_id
            )
        if result.result != pb.COMMAND_RESULT_ACCEPTED:
            raise ClientError(
                f"{result.failure.code}: {result.failure.message}",
                command_id=command_id,
            )
        return result

    def operator_command(self) -> rpc.OperatorCommand:
        state = self.snapshot
        if state.control.holder_client_id != self.principal.generation:
            raise ClientError("This client no longer holds control.")
        command = rpc.OperatorCommand(
            operator=pb.OperatorContext(
                client_id=self.principal.generation,
                control_generation=state.control.control_generation,
                command_id=str(uuid4()),
            ),
            controller_generation=state.controller_generation,
        )
        if state.trial.HasField("context") and state.trial.context.trial_id:
            command.expected_work.trial.CopyFrom(state.trial.context)
        elif state.session.HasField("context") and state.session.context.session_id:
            command.expected_work.session.CopyFrom(state.session.context)
        return command

    @asynccontextmanager
    async def observe(self) -> AsyncIterator[None]:
        self.views = StateViews()
        self._failure = None
        self.release_failure = None
        self.watch_id = str(uuid4())
        self._watch = self.stub.WatchState(
            rpc.WatchRequest(
                client_id=self.principal.generation, watch_id=self.watch_id
            ),
            metadata=self.principal.metadata(),
        )
        self._reader = asyncio.create_task(self._read())
        try:
            await asyncio.wait_for(self._wait(lambda _: True), self.rpc_timeout_s)
            yield
        finally:
            try:
                if self._failure is None and self.views.current is not None:
                    if (
                        self.snapshot.control.holder_client_id
                        == self.principal.generation
                    ):
                        try:
                            await self._admit("ReleaseControl", self.operator_command())
                        except ClientError as exc:
                            # Closing this exact watch also relinquishes its lease.
                            # Release failure must not replace the command outcome
                            # or mask the original exception from the caller.
                            self.release_failure = str(exc)
            finally:
                self._watch.cancel()
                self._reader.cancel()
                try:
                    await self._reader
                except asyncio.CancelledError:
                    pass

    async def claim_control(self, *, takeover: bool = False) -> None:
        state = self.snapshot
        claim = rpc.ControlClaim(
            client_id=self.principal.generation,
            command_id=str(uuid4()),
            controller_generation=state.controller_generation,
            synchronized_state_revision=state.state_revision,
            watch_id=self.watch_id,
        )
        if state.session.context.session_id:
            claim.session_id = state.session.context.session_id
        await self._admit("TakeOverControl" if takeover else "AcquireControl", claim)
        await asyncio.wait_for(
            self._wait(
                lambda s: s.control.holder_client_id == self.principal.generation
            ),
            self.rpc_timeout_s,
        )

    @asynccontextmanager
    async def control(self, *, takeover: bool = False) -> AsyncIterator[None]:
        async with self.observe():
            await self.claim_control(takeover=takeover)
            yield

    async def execute(
        self, method: str, request: Any | None = None, *, wait: bool = True
    ) -> CommandOutcome:
        admission = await self._admit(
            method, self.operator_command() if request is None else request
        )
        if not wait:
            return CommandOutcome(admission.command_id, False, None)
        return await self.wait_result(admission.command_id)

    async def wait_result(self, command_id: str) -> CommandOutcome:
        state = await self._wait(
            lambda s: (
                any(
                    op.context.command_id == command_id and op.complete
                    for op in s.operations
                )
                or any(p.operation.command_id == command_id for p in s.prompts)
            ),
            allow_closed=True,
        )
        for operation in state.operations:
            if operation.context.command_id == command_id and operation.complete:
                return CommandOutcome(
                    command_id,
                    True,
                    operation.succeeded if operation.HasField("succeeded") else None,
                    failure=(
                        f"{operation.failure.code}: {operation.failure.message}"
                        if operation.HasField("failure")
                        else ""
                    ),
                )
        return CommandOutcome(command_id, False, None, needs_input=True)

    async def cancel_current_work(self) -> CommandOutcome:
        phase = self.snapshot.session.phase
        if phase in (pb.SESSION_PHASE_SETTING_UP, pb.SESSION_PHASE_READY):
            return await self.execute("CancelSetup")
        if phase in (
            pb.SESSION_PHASE_STARTING,
            pb.SESSION_PHASE_RUNNING,
            pb.SESSION_PHASE_FINALIZING,
        ):
            return await self.execute("AbortNow")
        raise ClientError("Current state has no cancellable Setup or active session.")


def loopback_channel(port: int, max_message_bytes: int) -> Any:
    if not 1 <= port <= 65535 or max_message_bytes <= 0:
        raise ValueError("Invalid loopback port or message limit.")
    return grpc.aio.insecure_channel(
        f"127.0.0.1:{port}",
        options=[
            ("grpc.max_send_message_length", max_message_bytes),
            ("grpc.max_receive_message_length", max_message_bytes),
        ],
    )
