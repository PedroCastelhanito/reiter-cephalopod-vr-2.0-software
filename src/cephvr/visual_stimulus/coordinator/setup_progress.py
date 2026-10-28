"""Validate and relay meaningful renderer Setup progress under E06/E08."""

from cephvr.control.v1 import types_pb2 as pb

from .ports import PeerPort
from .state import CommandLink


async def relay_setup_progress(
    link: CommandLink,
    operation: pb.OperationState,
    *,
    live: bool,
    ingress_ns: int,
    backend: pb.BackendContext,
    controller: PeerPort,
) -> None:
    if (
        link.method != "SetupSession"
        or operation.command != "SetupSession"
        or operation.work != link.child.target.work
        or not live
        or operation.HasField("succeeded")
        or operation.HasField("failure")
        or len(operation.progress.encode("utf-8")) > 2048
    ):
        raise ValueError("progress outside live Setup")
    if link.setup_inactivity is not None:
        link.setup_inactivity.advance(
            operation.progress_sequence, operation.progress, ingress_ns
        )
        link.deadline_ns = link.setup_inactivity.deadline_ns
    progress = pb.OperationState.FromString(operation.SerializeToString())
    progress.context.command_id = link.parent.command_id
    progress.work.CopyFrom(link.parent.work)
    await controller.receipt(
        "ReportLifecycle",
        pb.LifecycleReport(
            operation=pb.BackendOperationReport(source=backend, operation=progress)
        ),
        deadline_ns=link.deadline_ns,
    )
