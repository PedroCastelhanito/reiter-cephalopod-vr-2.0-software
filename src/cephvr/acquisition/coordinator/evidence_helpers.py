"""Shared exact-context helpers for acquisition worker evidence owners."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.identity import camera_for_process_role
from cephvr.acquisition.state import SessionRecord, WorkerRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


def _latest_evidence(
    worker: WorkerRecord, work: control.WorkContext, kind: str
) -> acq.WorkerLifecycleEvidence | None:
    matches = [
        evidence
        for (work_key, _, evidence_kind), evidence in worker.lifecycle_evidence.items()
        if evidence_kind == kind and evidence.source.work == work and work_key
    ]
    return max(matches, key=lambda item: item.state_revision) if matches else None


def _work_within_launch(work: control.WorkContext, launch: control.WorkContext) -> bool:
    work_kind, launch_kind = work.WhichOneof("work"), launch.WhichOneof("work")
    if launch_kind is None:
        return work_kind is None
    if launch_kind == "session":
        if work_kind == "session":
            return work.session == launch.session
        if work_kind == "trial":
            return work.trial.session == launch.session
        return False
    return work == launch


def record_for_source(
    source: acq.WorkerContext, workers: dict[int, WorkerRecord]
) -> WorkerRecord:
    camera = camera_for_process_role(source.worker.role)
    record = workers.get(camera)
    if record is None:
        raise ValueError("worker generation is not registered")
    if (
        source.worker != record.launch.worker
        or source.owner != record.launch.owner
        or source.camera != camera
        or not _work_within_launch(source.work, record.launch.work)
    ):
        raise ValueError("worker report differs from its exact registered context")
    return record


def matching_session(
    work: control.WorkContext, current_session: Callable[[], SessionRecord | None]
) -> SessionRecord | None:
    session = current_session()
    if session is None:
        return None
    selected = work.WhichOneof("work")
    if selected == "session" and work == session.work:
        return session
    if selected == "trial" and session.trial is not None and work == session.trial.work:
        return session
    return None


def _report_rejected(code: str, message: str) -> control.ReportReceipt:
    return control.ReportReceipt(
        result=control.COMMAND_RESULT_REJECTED,
        failure=control.Failure(code=code, message=message[:2048]),
    )
