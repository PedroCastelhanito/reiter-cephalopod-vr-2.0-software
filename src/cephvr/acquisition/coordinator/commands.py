"""Create exact child worker commands and retain their coordinator parentage."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from cephvr.acquisition.identity import camera_for_process_role
from cephvr.acquisition.ports import WorkerPort
from cephvr.acquisition.state import ChildOperation, WorkerRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


def retain_worker_command(
    record: WorkerRecord,
    *,
    work: control.WorkContext | None,
    parent_operation: control.OperationContext,
    kind: str,
    deadline_ns: int,
    configuration_revision: int = 0,
    requested_device_id: str | None = None,
) -> tuple[acq.WorkerCommand, ChildOperation, WorkerPort]:
    """Pin the child ID, exact context and parent before any outbound RPC."""
    if record.port is None:
        raise RuntimeError("worker has no registered endpoint")
    if record.commands is None:
        raise RuntimeError("worker has no shared command-retention ledger")
    if not parent_operation.command_id or not kind:
        raise ValueError("worker child command requires parent and operation kind")
    if configuration_revision < 0:
        raise ValueError("worker child configuration revision cannot be negative")
    if deadline_ns <= 0:
        raise ValueError("worker child deadline must be a positive host timestamp")
    launch_work = record.launch.work
    if not _work_within_launch(work, launch_work):
        raise ValueError("worker child work escapes its exact launch scope")
    context = acq.WorkerContext(
        worker=record.launch.worker,
        owner=record.launch.owner,
        camera=camera_for_process_role(record.launch.worker.role),
    )
    if work is not None:
        context.work.CopyFrom(work)
    command_id = str(uuid4())
    parent = control.OperationContext(command_id=parent_operation.command_id)
    child = ChildOperation(
        command_id=command_id,
        camera=context.camera,
        work=control.WorkContext(),
        parent_operation=parent,
        kind=kind,
        configuration_revision=configuration_revision,
        requested_device_id=requested_device_id,
        deadline_ns=deadline_ns,
    )
    if work is not None:
        child.work.CopyFrom(work)
    request = acq.WorkerCommand(
        command_id=command_id,
        issuer=record.launch.owner,
        target=context,
        parent_operation=parent,
    )
    ledger = record.commands
    now_ns = host_time_ns()
    ledger.prune(now_ns)
    record.prune_child_operations()
    retention_scope = _child_retention_scope(child.work, command_id)
    safety = kind in {
        "cancel_setup",
        "cleanup",
        "interrupt_session",
        "interrupt",
        "release_trial",
        "record_pulse_evidence",
        "shutdown",
        "stop_preview",
        "stop_trial",
    }
    retention_key = (
        f"acquisition-child:{record.launch.worker.generation}:{retention_scope}:"
        f"{'safety' if safety else 'ordinary'}"
    )
    child.retained_size = (
        4096 + request.ByteSize() + context.ByteSize() + ledger.result_reservation_bytes
    )
    retained_size = child.retained_size + sum(
        item.retained_size
        for item in record.child_operations.values()
        if item.retention_key == retention_key
    )
    ledger.reserve_payload(
        retention_key,
        retained_size,
        work_key=retention_scope,
        priority=safety,
    )
    child.retention_key = retention_key
    record.child_operations[command_id] = child
    return request, child, record.port


def _child_retention_scope(work: control.WorkContext, command_id: str) -> str:
    selected = work.WhichOneof("work")
    if selected == "session":
        return work.session.session_id
    if selected == "trial":
        return work.trial.session.session_id
    return command_id


def _work_within_launch(
    work: control.WorkContext | None, launch_work: control.WorkContext
) -> bool:
    if work is None:
        return launch_work.WhichOneof("work") is None
    selected = work.WhichOneof("work")
    launch_selected = launch_work.WhichOneof("work")
    if selected is None:
        return launch_selected is None
    if launch_selected is None:
        return False
    if launch_selected == "session":
        if selected == "session":
            return work.session == launch_work.session
        if selected == "trial":
            return work.trial.session == launch_work.session
        return False
    return selected == "trial" and work.trial == launch_work.trial


async def wait_child_operation(
    child: ChildOperation,
    deadline_ns: int,
    lock: asyncio.Lock,
    clock: Callable[[], int] = host_time_ns,
) -> control.OperationState:
    """Wait for the one retained child under its original absolute deadline."""
    while True:
        async with lock:
            state = child.report
            if state is not None and state.complete:
                if state.context.command_id != child.command_id:
                    raise RuntimeError("worker completed another child operation")
                if (
                    child.report_ingress_ns is None
                    or child.deadline_ns is None
                    or child.report_ingress_ns > deadline_ns
                    or child.report_ingress_ns > child.deadline_ns
                ):
                    raise TimeoutError(
                        "worker completion arrived after its original deadline"
                    )
                return control.OperationState.FromString(
                    state.SerializeToString(deterministic=True)
                )
            child.updated.clear()
        timeout = max(0, deadline_ns - clock()) / 1_000_000_000
        if timeout <= 0:
            raise TimeoutError("worker operation missed its original deadline")
        await asyncio.wait_for(child.updated.wait(), timeout)
