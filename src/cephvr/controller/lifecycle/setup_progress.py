"""Nonterminal Setup feedback, separate from Ready and completion evidence."""

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.receipts import rejected_receipt
from cephvr.controller.state import Attempt


def retain_setup_progress(
    attempt: Attempt, payload: pb.BackendOperationReport, phase: int, ingress_ns: int
) -> pb.ReportReceipt:
    operation = payload.operation
    name = payload.source.backend_name
    backend = attempt.required.get(name)
    if (
        backend is None
        or payload.source != backend.context
        or operation.context.command_id != attempt.setup_operations.get(name)
        or operation.command != "SetupSession"
        or operation.work.WhichOneof("work") != "session"
        or operation.work.session != attempt.context
        or operation.complete
        or operation.succeeded
        or operation.HasField("failure")
        or not operation.progress
        or len(operation.progress.encode("utf-8")) > 2048
        or phase != pb.SESSION_PHASE_SETTING_UP
        or attempt.cancel_requested
        or attempt.interrupted
        or name in attempt.ready
        or operation.context.command_id in attempt.scope_results
        or ingress_ns > attempt.setup_deadline_ns
    ):
        return rejected_receipt("EVIDENCE", "unexpected Setup progress")
    attempt.setup_progress[name] = operation.progress
    return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
