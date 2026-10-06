"""Authenticated unary RPC ingress for one registered camera worker (A02/E08)."""

from __future__ import annotations

from collections.abc import Mapping

import grpc
from google.protobuf.message import Message

from cephvr.acquisition.identity import camera_for_process_role
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.auth import AuthenticationError, require_authenticated_peer
from cephvr.shared.clock import host_time_ns
from cephvr.shared.transport_deadlines import (
    DeadlineMetadataError,
    parse_deadline_metadata,
)

from .ports import WorkerOperationOwner
from .state import WorkerState
from .terminal_scope import (
    command_work_key,
    terminal_target,
    terminal_target_matches,
)

_SAFETY_METHODS = frozenset(
    {
        "InterruptSession",
        "Cleanup",
        "Shutdown",
        "StopTrial",
        "StopPreview",
        "CancelSetup",
    }
)
_NO_WORK_METHODS = frozenset(
    {
        "PreparePreview",
        "StartPreview",
        "StopPreview",
        "EditCamera",
        "ResolveCameraConfiguration",
        "GetState",
        "GetRetainedResult",
        "Cleanup",
        "Shutdown",
    }
)
_TRIAL_METHODS = frozenset(
    {
        "PrepareTrial",
        "ScheduleTrial",
        "ReleaseTrial",
        "RecordPulseEvidence",
        "StopTrial",
    }
)
_OWNER_TERMINAL_EVIDENCE_METHODS = frozenset({"RecordPulseEvidence"})


class AcquisitionWorkerService(rpc.AcquisitionWorkerServiceServicer):
    """Authenticate every request, pin its first deadline and enqueue owner work."""

    def __init__(
        self,
        state: WorkerState,
        owner: WorkerOperationOwner,
        peer_tokens: Mapping[str, tuple[str, str]],
    ) -> None:
        self.state = state
        self.owner = owner
        self.peer_tokens = dict(peer_tokens)

    async def _authenticate(
        self, context: grpc.aio.ServicerContext, issuer: control.ProcessIdentity
    ) -> int:
        trusted = self.peer_tokens.get(issuer.role)
        if trusted is None or trusted[0] != issuer.generation:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "unregistered issuer")
            raise AssertionError("abort returned")
        try:
            require_authenticated_peer(
                context.peer(),
                context.invocation_metadata(),
                expected_role=issuer.role,
                expected_generation=issuer.generation,
                expected_token=trusted[1],
            )
            deadline_ns = parse_deadline_metadata(context.invocation_metadata())
            if deadline_ns <= host_time_ns():
                await context.abort(
                    grpc.StatusCode.DEADLINE_EXCEEDED,
                    "original absolute deadline has expired",
                )
            return deadline_ns
        except (AuthenticationError, DeadlineMetadataError, ValueError) as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))
            raise AssertionError("abort returned") from exc

    async def _admit(
        self,
        name: str,
        request: Message,
        command: acq.WorkerCommand,
        context: grpc.aio.ServicerContext,
    ) -> control.CommandAdmission:
        if not self.state.registered:
            return _rejected("", "NOT_REGISTERED", "worker endpoint is not registered")
        if not command.HasField("issuer") or not command.HasField("target"):
            return _rejected(
                command.command_id, "INVALID_REQUEST", "issuer and target are required"
            )
        deadline_ns = await self._authenticate(context, command.issuer)
        limits = self.state.limits
        if limits is None:
            return _rejected(
                command.command_id, "NOT_READY", "worker control limits are absent"
            )
        if request.ByteSize() > limits.max_message_bytes:
            return _rejected(
                command.command_id,
                "RESOURCE_EXHAUSTED",
                "request exceeds the adopted worker message limit",
            )
        large_result = name == "ResolveCameraConfiguration" or (
            name == "EditCamera"
            and isinstance(request, acq.WorkerEditCamera)
            and request.kind
            in (
                acq.CAMERA_EDIT_KIND_APPLY_SETTINGS,
                acq.CAMERA_EDIT_KIND_IMPORT_PFS,
            )
        )
        if not _same_worker(
            command.target,
            self.state.context,
            allow_missing_work=name in _NO_WORK_METHODS,
        ):
            return _rejected(
                command.command_id,
                "STALE_CONTEXT",
                "request targets another worker generation",
            )
        safety = name in _SAFETY_METHODS
        if command.issuer == self.state.context.owner:
            pass
        elif safety and command.issuer == self.state.supervisor:
            pass
        else:
            return _rejected(
                command.command_id,
                "UNAUTHORIZED",
                "issuer cannot perform this worker operation",
            )
        if not command.command_id:
            return _rejected(
                command.command_id, "INVALID_REQUEST", "command ID is required"
            )
        if not _valid_scope(name, command.target):
            return _rejected(
                command.command_id,
                "INVALID_REQUEST",
                "operation has an invalid work scope",
            )
        try:
            canonical = (
                name.encode("ascii")
                + b"\0"
                + request.SerializeToString(deterministic=True)
            )
        except (ValueError, TypeError, AttributeError) as exc:
            return _rejected(command.command_id, "INVALID_REQUEST", str(exc))
        with self.state.lock:
            existing = self.state.commands.get(command.command_id)
            if existing is not None:
                try:
                    admission = self.state.commands.admit(
                        command.command_id,
                        canonical,
                        host_time_ns(),
                        work_key=command_work_key(
                            name, command.command_id, _work_key(command.target)
                        ),
                        deadline_ns=deadline_ns,
                        priority=(
                            name in _SAFETY_METHODS
                            or name == "StopTrial"
                            or name in _OWNER_TERMINAL_EVIDENCE_METHODS
                        ),
                        result_reservation_bytes=(
                            limits.large_result_reservation_bytes
                            if large_result
                            else None
                        ),
                    )
                except (ValueError, TypeError, RuntimeError) as exc:
                    return _rejected(command.command_id, "INVALID_REQUEST", str(exc))
                return (
                    _accepted(command.command_id)
                    if admission.replayed
                    else _rejected(
                        command.command_id,
                        "INVALID_REQUEST",
                        "retained command mismatch",
                    )
                )
            if (
                self.state.interrupted
                and name not in _SAFETY_METHODS
                and name not in _OWNER_TERMINAL_EVIDENCE_METHODS
            ):
                return _rejected(
                    command.command_id,
                    "WORKER_FENCED",
                    "worker admission is fenced after a retained health or owner failure",
                )
            if len(self.state.operations) >= self.state.max_retained_views:
                return _rejected(
                    command.command_id,
                    "RESOURCE_EXHAUSTED",
                    "retained worker operation capacity is full",
                )
            try:
                ticket = self.owner.reserve(name, request, deadline_ns)
            except Exception as exc:
                return _rejected(command.command_id, "RESOURCE_EXHAUSTED", str(exc))
            try:
                admission = self.state.commands.admit(
                    command.command_id,
                    canonical,
                    host_time_ns(),
                    work_key=command_work_key(
                        name, command.command_id, _work_key(command.target)
                    ),
                    deadline_ns=deadline_ns,
                    priority=(
                        name in _SAFETY_METHODS
                        or name == "StopTrial"
                        or name in _OWNER_TERMINAL_EVIDENCE_METHODS
                    ),
                    result_reservation_bytes=(
                        limits.large_result_reservation_bytes if large_result else None
                    ),
                )
            except (ValueError, TypeError, RuntimeError) as exc:
                ticket.cancel()
                return _rejected(command.command_id, "INVALID_REQUEST", str(exc))
            if admission.replayed:
                ticket.cancel()
                return _accepted(command.command_id)
            operation = control.OperationState(
                context=control.OperationContext(command_id=command.command_id),
                command=name,
                work=command.target.work,
                complete=False,
                progress="accepted",
            )
            self.state.operations[command.command_id] = operation
            self.state.state_revision += 1
            ticket.commit()
        return _accepted(command.command_id)

    async def PreparePreview(
        self, request: acq.WorkerPreparePreview, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("PreparePreview", request, request.command, context)

    async def StartPreview(
        self, request: acq.WorkerStartPreview, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("StartPreview", request, request.command, context)

    async def StopPreview(
        self, request: acq.WorkerStopPreview, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("StopPreview", request, request.command, context)

    async def EditCamera(
        self, request: acq.WorkerEditCamera, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("EditCamera", request, request.command, context)

    async def ResolveCameraConfiguration(
        self, request: acq.WorkerResolveCamera, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit(
            "ResolveCameraConfiguration", request, request.command, context
        )

    async def GetState(
        self, request: acq.WorkerQuery, context: grpc.aio.ServicerContext
    ) -> acq.WorkerState:
        caller = _caller_from_metadata(context)
        await self._authenticate(context, caller)
        if caller not in (self.state.context.owner, self.state.supervisor):
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED, "caller cannot query this worker"
            )
        if not _same_worker(
            request.target, self.state.context, allow_missing_work=True
        ):
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "query targets another worker"
            )
        try:
            return self.snapshot(request.target)
        except OverflowError as exc:
            await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, str(exc))
            raise AssertionError("abort returned") from exc

    async def GetRetainedResult(
        self, request: acq.WorkerRetainedResultQuery, context: grpc.aio.ServicerContext
    ) -> acq.WorkerRetainedResult:
        target = request.query.target
        caller = _caller_from_metadata(context)
        await self._authenticate(context, caller)
        if caller not in (self.state.context.owner, self.state.supervisor):
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED, "caller cannot query this worker"
            )
        if not _same_worker(
            target,
            self.state.context,
            allow_missing_work=(
                not target.HasField("work") and not self.state.context.HasField("work")
            ),
        ):
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "query targets another worker"
            )
        result = acq.WorkerRetainedResult(source=self.state.context)
        if target.HasField("work"):
            result.source.work.CopyFrom(target.work)
        with self.state.lock:
            record = self.state.commands.get(request.command_id)
            if record is None:
                return result
            terminal_scoped = terminal_target(record) is not None
            matches_query = (
                terminal_target_matches(record, request.command_id, target)
                if terminal_scoped
                else record.work_key == _work_key(target)
            )
            if not matches_query:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    "command is not retained for queried work",
                )
            result.found = True
            result.admission.result = control.COMMAND_RESULT_ACCEPTED
            result.admission.command_id = request.command_id
            operation = self.state.operations.get(request.command_id)
            if operation is not None:
                if record.result is not None:
                    try:
                        result.operation.ParseFromString(record.result)
                    except Exception as exc:
                        await context.abort(
                            grpc.StatusCode.INTERNAL,
                            "retained worker operation result is malformed",
                        )
                        raise AssertionError("abort returned") from exc
                else:
                    result.operation.source.CopyFrom(self.state.context)
                    result.operation.operation.CopyFrom(operation)
                    result.operation.state_revision = self.state.state_revision
            for evidence in self.state.lifecycle.values():
                if (
                    evidence.operation.command_id == request.command_id
                    and evidence.source == target
                ):
                    result.lifecycle.add().CopyFrom(evidence)
        return result

    async def SetupSession(
        self, request: acq.WorkerSetupSession, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("SetupSession", request, request.command, context)

    async def CancelSetup(
        self, request: acq.WorkerCommand, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("CancelSetup", request, request, context)

    async def PrepareTrial(
        self, request: acq.WorkerPrepareTrial, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("PrepareTrial", request, request.command, context)

    async def ScheduleTrial(
        self, request: acq.WorkerSchedule, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("ScheduleTrial", request, request.command, context)

    async def ReleaseTrial(
        self, request: acq.WorkerRelease, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("ReleaseTrial", request, request.command, context)

    async def RecordPulseEvidence(
        self, request: acq.WorkerPulseEvidence, context: grpc.aio.ServicerContext
    ) -> control.ReportReceipt:
        if not request.HasField("command"):
            return control.ReportReceipt(
                result=control.COMMAND_RESULT_REJECTED,
                failure=control.Failure(
                    code="INVALID_REQUEST", message="command is required"
                ),
            )
        admission = await self._admit(
            "RecordPulseEvidence", request, request.command, context
        )
        receipt = control.ReportReceipt(result=admission.result)
        if admission.HasField("failure"):
            receipt.failure.CopyFrom(admission.failure)
        return receipt

    async def StopTrial(
        self, request: acq.WorkerStop, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("StopTrial", request, request.command, context)

    async def InterruptSession(
        self, request: acq.WorkerInterrupt, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("InterruptSession", request, request.command, context)

    async def Cleanup(
        self, request: acq.WorkerCommand, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("Cleanup", request, request, context)

    async def Shutdown(
        self, request: acq.WorkerCommand, context: grpc.aio.ServicerContext
    ) -> control.CommandAdmission:
        return await self._admit("Shutdown", request, request, context)

    def snapshot(self, target: acq.WorkerContext) -> acq.WorkerState:
        with self.state.lock:
            state = acq.WorkerState(
                source=self.state.context,
                state_revision=self.state.state_revision,
                confirmed_configuration_revision=self.state.confirmed_configuration_revision,
            )
            for evidence in self.state.lifecycle.values():
                if (
                    target.HasField("work")
                    and evidence.source.HasField("work")
                    and evidence.source.work == target.work
                ) or (
                    not target.HasField("work") and not evidence.source.HasField("work")
                ):
                    state.lifecycle.add().CopyFrom(evidence)
            for operation in self.state.operations.values():
                if target.HasField("work"):
                    if not operation.HasField("work") or operation.work != target.work:
                        continue
                elif (
                    operation.HasField("work")
                    and operation.work.WhichOneof("work") is not None
                ):
                    continue
                view = control.OperationState()
                view.CopyFrom(operation)
                state.operations.add().CopyFrom(view)
            warning_views = (
                self.state.warnings.views(target.work)
                if self.state.warnings is not None and target.HasField("work")
                else self.state.warnings.views()
                if self.state.warnings is not None
                else ()
            )
            for warning_view in warning_views:
                state.warning_views.add().CopyFrom(warning_view)
            if state.ByteSize() > self.state.commands.max_bytes:
                raise OverflowError(
                    "worker state snapshot exceeds retained command byte budget"
                )
        return state


def _same_worker(
    requested: acq.WorkerContext,
    registered: acq.WorkerContext,
    *,
    allow_missing_work: bool,
) -> bool:
    try:
        camera_role = camera_for_process_role(registered.worker.role)
    except ValueError:
        return False
    same_identity = (
        requested.worker == registered.worker
        and requested.owner == registered.owner
        and requested.camera == registered.camera == camera_role
    )
    if not same_identity:
        return False
    if requested.HasField("work"):
        return registered.HasField("work") and _same_session(
            requested.work, registered.work
        )
    return allow_missing_work


def _same_session(left: control.WorkContext, right: control.WorkContext) -> bool:
    left_kind, right_kind = left.WhichOneof("work"), right.WhichOneof("work")
    if left_kind == "session" and right_kind == "session":
        return left.session == right.session
    if left_kind == "trial" and right_kind == "trial":
        return left.trial.session == right.trial.session
    if left_kind == "trial" and right_kind == "session":
        return left.trial.session == right.session
    if left_kind == "session" and right_kind == "trial":
        return left.session == right.trial.session
    return False


def _valid_scope(name: str, target: acq.WorkerContext) -> bool:
    if not target.HasField("work"):
        return name in _NO_WORK_METHODS
    kind = target.work.WhichOneof("work")
    if name in _TRIAL_METHODS:
        return bool(kind == "trial")
    if name in {"SetupSession", "CancelSetup", "InterruptSession"}:
        return bool(kind == "session")
    return bool(kind in {"session", "trial"})


def _work_key(context: acq.WorkerContext) -> str:
    if context.HasField("work"):
        kind = context.work.WhichOneof("work")
        if kind == "trial":
            return context.work.trial.trial_id
        if kind == "session":
            return context.work.session.session_id
    return context.worker.generation


def _caller_from_metadata(context: grpc.aio.ServicerContext) -> control.ProcessIdentity:
    metadata = {item.key.lower(): item.value for item in context.invocation_metadata()}
    return control.ProcessIdentity(
        role=str(metadata.get("x-cephvr-role", "")),
        generation=str(metadata.get("x-cephvr-generation", "")),
    )


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message),
    )


def _accepted(command_id: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_ACCEPTED,
        command_id=command_id,
    )
