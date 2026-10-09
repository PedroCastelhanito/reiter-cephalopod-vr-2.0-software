"""Bounded controller delivery and retention of aggregated trial reports (E08)."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import cast

from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import (
    SessionRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger


class TrialReportDelivery:
    """Retain report attempts on the trial and output evidence on its session."""

    def __init__(
        self,
        *,
        session_slot: SessionSlot,
        workers: dict[int, WorkerRecord],
        controller: ControllerPort,
        commands: CommandLedger,
        clock: Callable[[], int],
    ) -> None:
        self.session_slot = session_slot
        self.workers = workers
        self.controller = controller
        self.commands = commands
        self.clock = clock

    async def deliver(
        self,
        trial: TrialRecord,
        kind: str,
        report: control.StartedReport | control.StoppedReport | control.FinishedReport,
        deadline_ns: int,
    ) -> control.ReportReceipt:
        now = self.clock()
        if now > deadline_ns:
            return control.ReportReceipt(
                result=control.COMMAND_RESULT_REJECTED,
                failure=control.Failure(
                    code="LIFECYCLE_CUTOFF",
                    message="retained lifecycle deadline expired",
                ),
            )
        attempts = trial.lifecycle_report_attempts.get(kind, 0)
        if attempts >= 3:
            return _rejected(
                "LIFECYCLE_UNCONFIRMED", "controller did not accept report"
            )
        trial.lifecycle_report_attempts[kind] = attempts + 1
        lifecycle = control.LifecycleReport()
        if kind == "started":
            lifecycle.started.CopyFrom(cast(control.StartedReport, report))
        elif kind == "stopped":
            lifecycle.stopped.CopyFrom(cast(control.StoppedReport, report))
        else:
            finished = cast(control.FinishedReport, report)
            lifecycle.finished.CopyFrom(finished)
            session = self.session_slot.current
            if not _owns_trial(session, trial) or finished.context.work != trial.work:
                return _rejected(
                    "STALE_FINISHED", "Finished output retention lost its session scope"
                )
            assert session is not None
            try:
                for output in finished.outputs:
                    plans = [
                        item
                        for item in session.reserved_outputs
                        if item.output_key == output.output_key
                    ]
                    if len(plans) != 1:
                        raise ValueError(
                            "Finished output is outside the exact Setup reservation"
                        )
                    tag = plans[0].output_tag
                    role = (
                        camera.CAMERA_ROLE_BEHAVIORAL
                        if tag.startswith("behavioral_cam")
                        else camera.CAMERA_ROLE_TRACKING
                        if tag.startswith("tracking_cam")
                        else camera.CAMERA_ROLE_EYE_TRACKING
                        if tag.startswith("eye_tracking_cam")
                        else 0
                    )
                    worker = self.workers.get(role)
                    if worker is None or worker.commands is None:
                        raise ValueError(
                            "Finished output has no registered retention owner"
                        )
                    session.retain_output_result(output, worker.commands)
            except (ValueError, RuntimeError) as exc:
                return _rejected("FINISHED_RETENTION", str(exc))
        receipt = await self.controller.report_lifecycle(
            lifecycle, deadline_ns=deadline_ns
        )
        if receipt.result == control.COMMAND_RESULT_ACCEPTED:
            if kind == "started":
                trial.started_report = deepcopy(cast(control.StartedReport, report))
                trial.pending_started_report = None
            elif kind == "stopped":
                trial.stopped_report = deepcopy(cast(control.StoppedReport, report))
                trial.pending_stopped_report = None
            else:
                trial.finished_report = deepcopy(cast(control.FinishedReport, report))
                trial.pending_finished_report = None
                session = self.session_slot.current
                if _owns_trial(session, trial):
                    try:
                        self.commands.finalize_work(
                            trial.work.trial.trial_id, self.clock()
                        )
                    except ValueError:
                        # A local/internal trial may have only payload retention.
                        pass
        return receipt


def _owns_trial(session: SessionRecord | None, trial: TrialRecord) -> bool:
    return (
        session is not None
        and session.trial is trial
        and session.work.HasField("session")
        and trial.work.HasField("trial")
        and session.work.session == trial.work.trial.session
    )


def _rejected(code: str, message: str) -> control.ReportReceipt:
    return control.ReportReceipt(
        result=control.COMMAND_RESULT_REJECTED,
        failure=control.Failure(code=code, message=message[:2048]),
    )
