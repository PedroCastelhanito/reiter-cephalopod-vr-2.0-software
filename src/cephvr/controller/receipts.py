"""Rejected command admissions and report receipts with one failure shape."""

from __future__ import annotations

from cephvr.control.v1 import types_pb2 as pb


def rejected_receipt(code: str, message: str) -> pb.ReportReceipt:
    return pb.ReportReceipt(
        result=pb.COMMAND_RESULT_REJECTED,
        failure=pb.Failure(code=code, message=message),
    )


def rejected_admission(command_id: str, code: str, message: str) -> pb.CommandAdmission:
    return pb.CommandAdmission(
        result=pb.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=pb.Failure(code=code, message=message),
    )
