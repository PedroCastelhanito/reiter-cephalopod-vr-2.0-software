"""Operator-chosen deletion of stale Fold bundles relayed in this Setup (V04)."""

from pathlib import Path

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.resources.image_bundle_store import (
    BundleStore,
    StoredBundle,
)

from .state import State


def validate_deletion(state: State, request: wire.StaleImageBundleDeletion) -> None:
    ids = list(request.bundle_ids)
    if not ids or len(ids) > 64 or len(set(ids)) != len(ids):
        raise ValueError("stale bundle deletion needs 1-64 unique bundle IDs")
    if not set(ids) <= state.stale_bundles:
        raise ValueError("bundle was not reported stale in this Setup")
    if state.active_trial is not None:
        raise ValueError("stale bundle questions are dismissed at Start")


def delete_stale_bundles(
    state: State, request: wire.StaleImageBundleDeletion
) -> pb.OperationState:
    """Delete each requested folder; the stale entries were never opened for reading."""
    assert state.setup is not None
    store = BundleStore(Path(state.setup.plan.configuration.asset_root))
    failures = []
    for bundle_id in request.bundle_ids:
        try:
            store.delete(StoredBundle(store.root / bundle_id, None))
            state.stale_bundles.discard(bundle_id)
        except OSError as exc:
            failures.append(f"{bundle_id}: {exc}")
    operation = pb.OperationState(
        context=pb.OperationContext(command_id=request.command.command_id),
        command="DeleteStaleImageBundles",
        work=request.command.work,
        complete=True,
        succeeded=not failures,
        progress=f"Deleted {len(request.bundle_ids) - len(failures)} old Fold bundles",
    )
    if failures:
        operation.failure.CopyFrom(
            pb.Failure(
                code="VISUAL_STIMULUS_BUNDLE_DELETE",
                message="; ".join(failures)[:2048],
            )
        )
    return operation
