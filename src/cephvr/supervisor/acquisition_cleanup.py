"""Exact acquisition-worker cleanup forwarding and retained-result verification."""

from __future__ import annotations

from uuid import uuid4

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.supervisor.ports import SupervisorOutbound


class AcquisitionWorkerCleanup:
    """Own idempotent worker cleanup command identities for supervisor shutdown."""

    def __init__(
        self,
        *,
        outbound: SupervisorOutbound,
        issuer: types.ProcessIdentity,
        command_ids: dict[tuple[str, str], str],
    ) -> None:
        self.outbound = outbound
        self.issuer = types.ProcessIdentity.FromString(
            issuer.SerializeToString(deterministic=True)
        )
        self.command_ids = command_ids

    async def reconcile(
        self,
        launch: wire.LaunchState,
        worker: acq.WorkerContext,
        *,
        deadline_ns: int,
    ) -> None:
        """Retry exact cleanup, then require exact retained success evidence.

        Returns only when the worker retained a succeeded Cleanup; any other
        outcome raises so the caller cannot mistake it for completion.
        """
        key = (worker.worker.role, worker.worker.generation)
        command_id = self.command_ids.get(key)
        if command_id is None:
            command_id = str(uuid4())
            self.command_ids[key] = command_id
        command = acq.WorkerCommand(
            command_id=command_id,
            issuer=self.issuer,
            target=worker,
            parent_operation=types.OperationContext(command_id=command_id),
        )
        admission = await self.outbound.cleanup_worker(
            launch, command, deadline_ns=deadline_ns
        )
        if admission.result != types.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(f"worker cleanup not accepted: {admission.failure.code}")
        retained = await self.outbound.get_worker_retained_result(
            launch,
            acq.WorkerRetainedResultQuery(
                query=acq.WorkerQuery(target=worker), command_id=command_id
            ),
            deadline_ns=deadline_ns,
        )
        if (
            not retained.found
            or retained.source.worker != worker.worker
            or retained.source.owner != worker.owner
            or retained.source.camera != worker.camera
            or retained.source.work != worker.work
            or not retained.HasField("operation")
            or retained.operation.operation.context.command_id != command_id
            or not retained.operation.operation.complete
            or not retained.operation.operation.HasField("succeeded")
            or not retained.operation.operation.succeeded
        ):
            raise RuntimeError("worker cleanup result is not retained as succeeded")
