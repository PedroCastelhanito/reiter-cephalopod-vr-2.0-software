"""Worker command/state boundary; graphics ownership stays on RenderOwner."""

from __future__ import annotations

from collections.abc import Callable

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.shared.identity import require_uuid4
from cephvr.visual_stimulus.coordinator.ports import PeerPort
from cephvr.visual_stimulus.transport.messages import worker_command
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus

from .owner import RenderOwner


class VisualStimulusWorkerRuntime:
    def __init__(
        self,
        context: visual_stimulus.WorkerContext,
        supervisor: pb.ProcessIdentity,
        owner: RenderOwner,
        reports: PeerPort,
        ledger: CommandLedger,
        *,
        clock: Callable[[], int] = host_time_ns,
        delivery_failed: Callable[[BaseException], None] | None = None,
    ) -> None:
        self.context = visual_stimulus.WorkerContext.FromString(
            context.SerializeToString()
        )
        self.supervisor, self.owner, self.reports, self.ledger, self.clock = (
            supervisor,
            owner,
            reports,
            ledger,
            clock,
        )
        self.interrupted = False
        self.retained: dict[tuple[str, str], visual_stimulus.WorkerLifecycle] = {}
        self.display = pb.VisualStimulusDisplayView()
        self.shutdown_deadline_ns: int | None = None
        self.command_ids: set[str] = set()
        self.delivery_failed = delivery_failed

    def validate_command(self, method: str, request: Message) -> None:
        command = worker_command(request)
        require_uuid4(command.command_id)
        if (
            command.target.worker != self.context.worker
            or command.target.owner != self.context.owner
        ):
            raise ValueError("wrong renderer/owner generation")
        from cephvr.visual_stimulus.transport.boundary import SAFETY

        if command.issuer not in (
            (self.context.owner, self.supervisor)
            if method in SAFETY
            else (self.context.owner,)
        ):
            raise ValueError("renderer caller is not an authorized owner")
        recoverable_calibration = (
            method
            in {
                "OpenDisplayCalibration",
                "CloseDisplayCalibration",
            }
            and self.context.work.WhichOneof("work") is None
        )
        sessionless_diagnostic_safety = (
            method in {"Cleanup", "Shutdown", "InterruptSession", "CancelSetup"}
            and self.context.work.WhichOneof("work") is None
        )
        if (
            self.interrupted
            and method
            not in SAFETY
            | {
                "SetupSession",
                "InitializeDisplay",
                "ConfirmRecipePublication",
            }
            and not recoverable_calibration
        ):
            raise ValueError("renderer session is permanently fenced")
        if (
            method
            not in {
                "InitializeDisplay",
                "SetupSession",
                "Shutdown",
                "OpenDisplayCalibration",
                "CloseDisplayCalibration",
            }
            and command.target.work != self.context.work
        ):
            work = command.target.work
            if (
                work.WhichOneof("work") != "trial"
                or work.trial.session != self.context.work.session
            ):
                raise ValueError("renderer command targets another session")
        if (
            method
            not in {
                "InitializeDisplay",
                "SetupSession",
                "Shutdown",
                "OpenDisplayCalibration",
                "CloseDisplayCalibration",
            }
            and not (command.issuer == self.supervisor and method in SAFETY)
            and not sessionless_diagnostic_safety
            and command.target.configuration_revision
            != self.context.configuration_revision
        ):
            raise ValueError("renderer configuration revision mismatch")

    async def execute(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        self.validate_command(method, request)
        command = worker_command(request)
        self.command_ids.add(command.command_id)
        if method == "Shutdown":
            self.shutdown_deadline_ns = min(
                self.shutdown_deadline_ns or deadline_ns, deadline_ns
            )
        if method in {"InterruptSession", "CancelSetup", "Cleanup", "Shutdown"}:
            self.interrupted = True
        if method in {"InitializeDisplay", "SetupSession"}:
            self.context.CopyFrom(command.target)
            self.interrupted = False
        elif method in {"OpenDisplayCalibration", "CloseDisplayCalibration"}:
            self.interrupted = False
            self.owner.cancelled.clear()
        try:
            await self.owner.submit(method, request, deadline_ns)
            outcome = pb.OperationState(
                context=pb.OperationContext(command_id=command.command_id),
                command=method,
                work=command.target.work,
                complete=True,
                succeeded=True,
            )
        except Exception as exc:
            self.interrupted = True
            self.owner.cancel()
            outcome = pb.OperationState(
                context=pb.OperationContext(command_id=command.command_id),
                command=method,
                work=command.target.work,
                complete=True,
                succeeded=False,
                failure=pb.Failure(
                    code="VISUAL_STIMULUS_OPERATION", message=str(exc)[:2048]
                ),
            )
        self.ledger.complete_executor(
            command.command_id, outcome.SerializeToString(), self.clock()
        )
        try:
            await self.reports.receipt(
                "ReportWorkerOperation",
                visual_stimulus.WorkerOperation(
                    source=command.target, operation=outcome
                ),
                deadline_ns=deadline_ns,
            )
        except Exception as exc:
            # Receipt loss cannot rewrite an already observed executor outcome.
            self.interrupted = True
            self.owner.cancel()
            if self.delivery_failed is not None:
                self.delivery_failed(exc)
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED, command_id=command.command_id
        )

    async def query(self, method: str, request: Message) -> Message:
        if (
            not isinstance(request, visual_stimulus.WorkerQuery)
            or request.target.worker != self.context.worker
            or request.target.owner != self.context.owner
        ):
            raise ValueError("wrong renderer query generation")
        result = visual_stimulus.WorkerState(
            context=self.context,
            interrupted=self.interrupted,
            retained_lifecycle=list(self.retained.values()),
            display=self.display,
        )
        if request.HasField("command_id"):
            record = self.ledger.get(request.command_id)
            result.command_known = record is not None
            if record is not None:
                if record.result:
                    result.admission.ParseFromString(record.result)
                if record.executor_result:
                    result.operation.ParseFromString(record.executor_result)
        return result

    async def report(
        self, method: str, request: Message, *, ingress_ns: int
    ) -> pb.ReportReceipt:
        raise ValueError("renderer hosts no inbound report endpoints")

    async def retain_and_report(
        self, report: visual_stimulus.WorkerLifecycle, deadline_ns: int
    ) -> None:
        kind = report.report.WhichOneof("report")
        if kind is None:
            raise ValueError("empty lifecycle report")
        payload = getattr(report.report, kind)
        command = (
            payload.operation.command_id
            if kind == "cleanup"
            else payload.context.operation.command_id
        )
        key = (kind, command)
        old = self.retained.get(key)
        if old is not None and old != report:
            raise ValueError("immutable worker lifecycle changed")
        self.ledger.reserve_payload(
            "lifecycle:" + kind + ":" + command,
            report.ByteSize(),
            work_key=(
                record.work_key
                if (record := self.ledger.get(command)) is not None
                else command
            ),
            priority=kind == "cleanup",
        )
        self.retained[key] = report
        if (
            kind == "cleanup"
            and all(item.released for item in report.report.cleanup.resources)
            and all(
                item.closure
                in {
                    pb.OUTPUT_CLOSURE_CLOSED,
                    pb.OUTPUT_CLOSURE_FAILED,
                    pb.OUTPUT_CLOSURE_NOT_STARTED,
                }
                and item.HasField("artifact_present")
                for item in report.report.cleanup.outputs
            )
        ):
            scopes = {
                record.work_key
                for command_id in self.command_ids
                if (record := self.ledger.get(command_id)) is not None
            }
            for scope in scopes:
                self.ledger.finalize_work(scope, self.clock())
        await self.reports.receipt(
            "ReportWorkerLifecycle", report, deadline_ns=deadline_ns
        )

    def prune_retained(self) -> None:
        self.ledger.prune(self.clock())
        self.command_ids = {
            command_id
            for command_id in self.command_ids
            if self.ledger.get(command_id) is not None
        }
        self.retained = {
            key: value
            for key, value in self.retained.items()
            if self.ledger.get(key[1]) is not None
        }

    async def failed_command(
        self,
        method: str,
        command: wire.BackendCommand,
        outcome: pb.OperationState,
        deadline_ns: int,
    ) -> None:
        self.interrupted = True
        self.owner.cancel()
        context = visual_stimulus.WorkerContext.FromString(
            self.context.SerializeToString()
        )
        context.work.CopyFrom(command.work)
        await self.reports.receipt(
            "ReportWorkerOperation",
            visual_stimulus.WorkerOperation(source=context, operation=outcome),
            deadline_ns=deadline_ns,
        )
