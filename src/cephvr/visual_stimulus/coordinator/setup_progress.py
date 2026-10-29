"""Validate and relay meaningful renderer Setup progress under E06/E08."""

import re

from cephvr.control.v1 import types_pb2 as pb

from .ports import PeerPort
from .state import CommandLink

_BUNDLE_ID = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}")


def stale_bundle_ids(operation: pb.OperationState) -> set[str]:
    """Bounded V04 stale Fold bundle IDs a renderer progress report offers."""
    bundles = operation.stale_image_bundles
    ids = {item.bundle_id for item in bundles}
    if (
        len(bundles) > 64
        or len(ids) != len(bundles)
        or not all(_BUNDLE_ID.fullmatch(item) for item in ids)
        or any(
            len(item.sources) > 16
            or any(not name or len(name.encode("utf-8")) > 512 for name in item.sources)
            for item in bundles
        )
    ):
        raise ValueError("stale image bundle report outside its contract bounds")
    return ids


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
    stale_bundle_ids(operation)
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
