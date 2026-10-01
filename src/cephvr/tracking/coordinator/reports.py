"""Retain facts before delivery; receipts never substitute for native completion."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.commands import CommandLedger

from .state import Identity, State


class PeerPort(Protocol):
    async def receipt(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.ReportReceipt: ...


class Reports:
    def __init__(
        self,
        identity: Identity,
        state: State,
        controller: PeerPort,
        supervisor: PeerPort,
        ledger: CommandLedger,
        clock: Callable[[], int],
    ) -> None:
        (
            self.identity,
            self.state,
            self.controller,
            self.supervisor,
            self.ledger,
            self.clock,
        ) = identity, state, controller, supervisor, ledger, clock

    def context(self, command: wire.BackendCommand) -> pb.ReportContext:
        return pb.ReportContext(
            backend=self.identity.backend,
            work=command.work,
            operation=pb.OperationContext(command_id=command.command_id),
        )

    async def lifecycle(self, report: pb.LifecycleReport, deadline: int) -> None:
        kind = report.WhichOneof("report")
        if kind in ("ready", "started", "stopped", "finished", "cleanup"):
            value = getattr(report, kind)
            context = value if kind == "cleanup" else value.context
            work = context.work
            command = context.operation.command_id
            key = f"tracking:{command}:{kind}"
            scope = (
                work.trial.trial_id
                if work.HasField("trial")
                else work.session.session_id
            )
            self.ledger.reserve_payload(
                key, report.ByteSize(), work_key=scope, priority=kind == "cleanup"
            )
            self.state.retained[key] = pb.LifecycleReport.FromString(
                report.SerializeToString()
            )
            if kind == "finished" or (
                kind == "cleanup"
                and value.trial_activity_stopped
                and all(item.released for item in value.resources)
            ):
                if self.ledger.get(command) is not None:
                    self.ledger.finalize_work(scope, self.clock())
        deliveries = [
            self.controller.receipt("ReportLifecycle", report, deadline_ns=deadline)
        ]
        if kind == "cleanup":
            deliveries.append(
                self.supervisor.receipt("ReportLifecycle", report, deadline_ns=deadline)
            )
        for result in await asyncio.gather(*deliveries, return_exceptions=True):
            if isinstance(result, BaseException):
                raise result

    def prune(self) -> None:
        self.ledger.prune(self.clock())
        for key in tuple(self.state.retained):
            if not self.ledger.has_payload(key):
                del self.state.retained[key]

    async def operation(
        self, method: str, command: wire.BackendCommand, deadline: int
    ) -> None:
        operation = pb.OperationState(
            context=pb.OperationContext(command_id=command.command_id),
            command=method,
            work=command.work,
            complete=True,
            succeeded=True,
        )
        self.ledger.complete_executor(
            command.command_id, operation.SerializeToString(), self.clock()
        )
        await self.lifecycle(
            pb.LifecycleReport(
                operation=pb.BackendOperationReport(
                    source=self.identity.backend, operation=operation
                )
            ),
            deadline,
        )

    async def preparation(self, deadline: int) -> None:
        state = self.state
        assert state.setup is not None
        revision = (
            1
            if state.preparation_report is None
            else state.preparation_report.report_revision + 1
        )
        state.preparation_report = wire.DataPreparationReport(
            source=self.context(state.setup.command),
            configuration_revision=state.setup.plan.configuration_revision,
            report_revision=revision,
            tracking=state.preparation,
        )
        await self.controller.receipt(
            "ReportDataPreparation", state.preparation_report, deadline_ns=deadline
        )

    async def heartbeat(self, deadline: int) -> None:
        state = self.state
        report = pb.HeartbeatReport(
            source=self.identity.process,
            work=state.work(),
            sent_monotonic_ns=self.clock(),
            health_summary="failed" if state.error else "responsive",
            cleanup_resources_revision=state.resource_revision,
            cleanup_resources=state.resources,
        )
        if state.trial is None:
            report.session_phase = state.session_phase
        else:
            report.trial_phase = state.trial_phase
        if state.error is not None:
            report.active_error.CopyFrom(state.error)
        await self.supervisor.receipt("ReportHeartbeat", report, deadline_ns=deadline)

    async def resources(
        self, names: tuple[tuple[str, str | None], ...], deadline: int
    ) -> None:
        if self.state.ready is not None:
            raise ValueError("Ready sealed native resource catalogue")
        existing = {item.resource for item in self.state.resources}
        for name, path in names:
            if name in existing:
                continue
            self.state.resources.append(
                pb.ResourceObligation(
                    owner=self.identity.process, resource=name, path=path
                )
            )
            existing.add(name)
            self.state.resource_revision += 1
        await self.heartbeat(deadline)
