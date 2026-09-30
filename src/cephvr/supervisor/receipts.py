"""Typed supervisor command and report receipts."""

from __future__ import annotations

from cephvr.control.v1 import types_pb2 as types


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


def report_rejected(code: str, message: str) -> types.ReportReceipt:
    return types.ReportReceipt(
        result=types.COMMAND_RESULT_REJECTED,
        failure=types.Failure(code=code, message=message),
    )


def report_accepted() -> types.ReportReceipt:
    return types.ReportReceipt(result=types.COMMAND_RESULT_ACCEPTED)
