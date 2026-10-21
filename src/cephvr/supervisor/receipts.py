"""Typed supervisor command and report receipts."""

from __future__ import annotations

from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns


def failure(error: Exception) -> types.Failure:
    return types.Failure(
        code=getattr(error, "code", "INVALID_REQUEST"), message=str(error)
    )


def rejected(command_id: str, error: Exception) -> types.CommandAdmission:
    return types.CommandAdmission(
        result=types.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=failure(error),
    )


def accepted(command_id: str) -> types.CommandAdmission:
    return types.CommandAdmission(
        result=types.COMMAND_RESULT_ACCEPTED, command_id=command_id
    )


def require_accepted(
    admission: types.CommandAdmission,
    what: str,
    *,
    worker: types.ProcessIdentity | None = None,
    work: types.WorkContext | None = None,
    command_id: str = "",
    deadline_ns: int | None = None,
) -> None:
    """Raise unless a worker command admission was accepted."""
    if admission.result != types.COMMAND_RESULT_ACCEPTED:
        context = ""
        if worker is not None and work is not None:
            session = work.trial.session if work.HasField("trial") else work.session
            context = (
                f"; worker={worker.role[:128]}/{worker.generation[:64]}, "
                f"command_id={command_id[:64]}, "
                f"controller={session.controller_generation[:64]}, "
                f"session={session.session_id[:64]}, trial={work.trial.trial_id[:64]}, "
                f"deadline_ns={deadline_ns}, observed_ns={host_time_ns()}"
            )
        raise RuntimeError(
            f"{what} not accepted: {admission.failure.code}{context}; "
            f"reason={repr(admission.failure.message[:512])[:512]}"
        )


def report_rejected(code: str, message: str) -> types.ReportReceipt:
    return types.ReportReceipt(
        result=types.COMMAND_RESULT_REJECTED,
        failure=types.Failure(code=code, message=message),
    )


def report_accepted() -> types.ReportReceipt:
    return types.ReportReceipt(result=types.COMMAND_RESULT_ACCEPTED)
