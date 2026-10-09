"""Typed owner proof required before releasing a retired camera worker (E08)."""

from cephvr.acquisition.identity import camera_for_process_role
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.shared.cleanup_outputs import cleanup_output_discharged
from cephvr.shared.identity import require_uuid4


def camera_cleanup_proof_matches(
    proof: wire.AcquisitionWorkerCleanupProof, expected: acq.WorkerContext
) -> bool:
    """Check exact worker/work binding and nonempty cleanup completion evidence."""
    operation = proof.operation
    cleanup = proof.cleanup
    try:
        require_uuid4(cleanup.operation.command_id)
    except ValueError:
        return False
    if (
        operation.source != expected
        or cleanup.source != expected
        or operation.operation.command != "Cleanup"
        or not operation.operation.complete
        or not operation.operation.HasField("succeeded")
        or not operation.operation.succeeded
        or operation.operation.failure.code
        or operation.operation.failure.message
        or operation.operation.context.command_id != cleanup.operation.command_id
        or operation.operation.work != expected.work
        or cleanup.WhichOneof("evidence") != "cleanup"
        or not cleanup.HasField("state_revision")
    ):
        return False
    resources = cleanup.cleanup.resources
    outputs = cleanup.cleanup.outputs
    resource_names = [item.resource for item in resources]
    output_keys = [item.output_key for item in outputs]
    if (
        len(resource_names) != len(set(resource_names))
        or any(
            not item.resource
            or not item.released
            or item.failure.code
            or item.failure.message
            for item in resources
        )
        or len(output_keys) != len(set(output_keys))
        or any(
            not item.output_key or not cleanup_output_discharged(item)
            for item in outputs
        )
        or not resources
        and not outputs
    ):
        return False
    return True


def camera_release_request_matches(
    request: wire.ConfirmLaunchRequest,
    plan: wire.PlanLaunchRequest,
    state: wire.LaunchState,
) -> bool:
    """Bind owner cleanup proof to one exact retired camera process generation."""
    try:
        camera = camera_for_process_role(plan.child.role)
    except ValueError:
        return False
    if (
        plan.owner.role != "acquisition"
        or not plan.python_worker
        or state.phase
        not in (wire.LAUNCH_PHASE_OPERATIONAL, wire.LAUNCH_PHASE_CLEANUP_REQUIRED)
        or (
            state.phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
            and state.failure.code != "CHILD_EXITED"
        )
        or request.owner != plan.owner
        or request.child != plan.child
        or not request.HasField("pid")
        or not request.HasField("creation_time_100ns")
        or not state.HasField("pid")
        or not state.HasField("creation_time_100ns")
        or request.pid != state.pid
        or request.creation_time_100ns != state.creation_time_100ns
        or request.HasField("endpoint")
        or request.HasField("host_clock")
        or request.HasField("creation_failed_without_child")
        or request.native_cleanup_complete
    ):
        return False
    expected = acq.WorkerContext(worker=plan.child, owner=plan.owner, camera=camera)
    if plan.HasField("work"):
        expected.work.CopyFrom(plan.work)
    return camera_cleanup_proof_matches(request.acquisition_worker_cleanup, expected)
