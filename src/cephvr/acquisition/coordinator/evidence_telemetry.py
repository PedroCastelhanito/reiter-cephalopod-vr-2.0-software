"""Retain bounded worker warning views and heartbeat health snapshots."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.coordinator.evidence_helpers import (
    _report_rejected,
    _work_within_launch,
    record_for_source,
)
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import SessionRecord, WorkerRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger


class WorkerTelemetryReports:
    def __init__(
        self,
        *,
        backend: control.BackendContext,
        workers: dict[int, WorkerRecord],
        commands: CommandLedger,
        current_session: Callable[[], SessionRecord | None],
        controller: ControllerPort,
        lock: asyncio.Lock,
    ) -> None:
        self.backend = backend
        self.workers = workers
        self.commands = commands
        self.current_session = current_session
        self.controller = controller
        self.lock = lock

    def _record(self, source: acq.WorkerContext) -> WorkerRecord:
        return record_for_source(source, self.workers)

    async def report_warnings(
        self,
        report: acq.WorkerWarningReport,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        try:
            record = self._record(report.source)
            view = report.view
            if (
                view.producer != report.source.worker
                or view.camera != report.source.camera
                or view.work != report.source.work
            ):
                raise ValueError("warning view differs from registered worker context")
            if ingress_ns > deadline_ns:
                raise ValueError("worker warning report missed its original deadline")
            async with self.lock:
                if not record.retain_warning_view(view, self.commands):
                    return _report_rejected(
                        "STALE_WARNING", "worker warning revision is stale"
                    )
            return await self.controller.report_acquisition_warnings(
                wire.AcquisitionWarningReport(source=self.backend, view=view),
                deadline_ns=deadline_ns,
            )
        except (ValueError, RuntimeError) as exc:
            return _report_rejected("INVALID_WARNING", str(exc))

    async def report_heartbeat(
        self,
        heartbeat: control.HeartbeatReport,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        try:
            if ingress_ns > deadline_ns:
                raise ValueError("worker heartbeat missed its original deadline")
            record = next(
                item
                for item in self.workers.values()
                if item.launch.worker == heartbeat.source
            )
            if (
                not _work_within_launch(heartbeat.work, record.launch.work)
                or len(heartbeat.health_summary) > 2048
            ):
                raise ValueError("worker heartbeat differs from its registered context")
            session = self.current_session()
            if session is not None and _work_within_launch(
                heartbeat.work, session.work
            ):
                expected_work = (
                    session.trial.work if session.trial is not None else session.work
                )
                if heartbeat.work != expected_work:
                    raise ValueError("worker heartbeat carries stale acquisition work")
            elif record.launch.work.WhichOneof("work") is None and (
                heartbeat.work.WhichOneof("work") is not None
            ):
                raise ValueError(
                    "sessionless worker heartbeat cannot claim session work"
                )
            previous = record.heartbeat
            if previous is not None:
                if heartbeat.sent_monotonic_ns < previous.sent_monotonic_ns:
                    raise ValueError("worker heartbeat timestamp moved backwards")
                if heartbeat.sent_monotonic_ns == previous.sent_monotonic_ns:
                    if previous != heartbeat:
                        raise ValueError(
                            "same worker heartbeat timestamp changed payload"
                        )
                    return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
            saved = control.HeartbeatReport.FromString(
                heartbeat.SerializeToString(deterministic=True)
            )
            async with self.lock:
                record.heartbeat = saved
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
        except StopIteration:
            return _report_rejected(
                "UNREGISTERED_WORKER", "worker heartbeat is unregistered"
            )
        except ValueError as exc:
            return _report_rejected("INVALID_HEARTBEAT", str(exc))
