"""Read-only recovery of exact acquisition-owned camera edit status."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.ports import BackendPort
from cephvr.shared.deadlines import remaining_seconds

ReportDevices = Callable[
    [str, Message, int | None], Coroutine[Any, Any, pb.ReportReceipt]
]


async def recover_owned_edit_status(
    *,
    backend: BackendPort,
    operation_id: str,
    source: pb.BackendContext,
    work: pb.WorkContext,
    report_devices: ReportDevices | None,
    clock: Callable[[], int],
    deadline_ns: int,
) -> bool:
    """Query and route one exact terminal Apply result without replaying work."""
    if report_devices is None or source != backend.context or clock() >= deadline_ns:
        return False
    query = svc.RetainedResultQuery(
        query=svc.BackendQuery(target=source, work=work),
        command_id=operation_id,
    )
    try:
        retained = await asyncio.wait_for(
            backend.get_retained_result(query, deadline_ns=deadline_ns),
            remaining_seconds(deadline_ns, clock=clock),
        )
        if (
            not retained.found
            or retained.backend != source
            or retained.work != work
            or not retained.HasField("acquisition_device_result")
        ):
            return False
        status = retained.acquisition_device_result
        if (
            status.views.source != source
            or status.operation.command_id != operation_id
            or status.work != work
            or status.result.context.command_id != operation_id
            or status.result.work != work
            or status.result.command != "ApplyCameraSettings"
            or not status.result.complete
            or not status.result.HasField("succeeded")
        ):
            return False
        if retained.HasField("operation") and (
            retained.operation.context.command_id != operation_id
            or retained.operation.work != work
            or retained.operation.command != "ApplyCameraSettings"
            or not retained.operation.complete
            or not retained.operation.HasField("succeeded")
            or retained.operation.succeeded != status.result.succeeded
        ):
            return False
        receipt = await report_devices("devices", status, clock())
        return receipt.result == pb.COMMAND_RESULT_ACCEPTED and clock() < deadline_ns
    except Exception:
        return False
