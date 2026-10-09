"""Recover exact pending sessionless camera work before accepting new edits."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from cephvr.acquisition.coordinator.configuration_resolution import (
    ConfigurationResolution,
)
from cephvr.acquisition.coordinator.manual_pulse_observation import release_idle_claim
from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.ports import SerialOwnerPort
from cephvr.acquisition.state import ChildOperation, PulseRecord, WorkerRecord
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class ManualDeviceRecovery:
    """Own retained-result reconciliation and the camera-work quiescence proof."""

    def __init__(
        self,
        *,
        workers: WorkerRegistry,
        resolution: ConfigurationResolution,
        pulse: PulseRecord,
        serial: SerialOwnerPort,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.workers = workers
        self.resolution = resolution
        self.pulse = pulse
        self.serial = serial
        self.clock = clock
        self._reconcile_retained_operation: (
            Callable[
                [WorkerRecord, ChildOperation, acq.WorkerRetainedResult, int, int],
                Awaitable[bool],
            ]
            | None
        ) = None

    def bind_retained_operation_reconciler(
        self,
        reconcile: Callable[
            [WorkerRecord, ChildOperation, acq.WorkerRetainedResult, int, int],
            Awaitable[bool],
        ],
    ) -> None:
        """Bind the evidence owner used by fresh-caller recovery."""
        self._reconcile_retained_operation = reconcile

    def device_work_quiescent(
        self,
        *,
        parent_command_id: str | None = None,
        required_preview_runs: dict[int, str] | None = None,
        required_pulse_roles: set[int] | None = None,
    ) -> bool:
        if self.pulse.claim_release_pending:
            return False
        relevant = {"apply_camera", "stop_preview", "prepare_preview", "start_preview"}
        for worker in self.workers.workers.values():
            preview = worker.preview
            if preview is not None and preview.stopping:
                return False
            if preview is not None:
                if (
                    required_preview_runs is not None
                    and required_preview_runs.get(worker.context.camera)
                    == preview.run_id
                ):
                    return False
            for child in worker.child_operations.values():
                if child.kind not in relevant:
                    continue
                if (
                    parent_command_id is not None
                    and child.parent_operation.command_id != parent_command_id
                ):
                    continue
                if child.report is None or not child.report.complete:
                    return False
                if (
                    preview is not None
                    and child.kind
                    in {
                        "stop_preview",
                        "prepare_preview",
                        "start_preview",
                    }
                    and child.command_id
                    in {
                        operation.command_id
                        for operation in (
                            preview.stop_operation,
                            preview.preparation,
                            preview.start_operation,
                        )
                        if operation is not None
                    }
                ):
                    return False
        if required_pulse_roles:
            observation = self.pulse.observation
            if observation is not None and observation.HasField("state"):
                state = observation.state
            elif (
                observation is None
                and self.pulse.released_idle_state is not None
                and self.pulse.released_idle_connection_id
            ):
                state = self.pulse.released_idle_state
            else:
                return False
            for role in required_pulse_roles:
                output = (
                    state.behavioral
                    if role == camera.CAMERA_ROLE_BEHAVIORAL
                    else state.tracking
                )
                if not output.HasField("running") or output.running:
                    return False
        return True

    async def recover_failed_device_work(self, deadline_ns: int) -> None:
        operation = await self.resolution.failed_operation()
        reconcile = self._reconcile_retained_operation
        if operation is None or reconcile is None:
            return
        relevant = {"apply_camera", "stop_preview", "prepare_preview", "start_preview"}
        for worker in self.workers.workers.values():
            if worker.port is None:
                continue
            for child in tuple(worker.child_operations.values()):
                if (
                    child.parent_operation != operation
                    or child.kind not in relevant
                    or child.deadline_ns is None
                    or child.report is not None
                    and child.report.complete
                ):
                    continue
                try:
                    retained = await worker.port.get_retained_result(
                        acq.WorkerRetainedResultQuery(
                            query=acq.WorkerQuery(target=worker.context),
                            command_id=child.command_id,
                        ),
                        deadline_ns=deadline_ns,
                    )
                    await reconcile(
                        worker,
                        child,
                        retained,
                        deadline_ns,
                        self.clock(),
                    )
                except (RuntimeError, TimeoutError, ValueError):
                    # An unavailable or expired query leaves the old ownership
                    # unresolved; it never authorizes a new SDK command.
                    continue

    async def retry_pending_claim_release(self, deadline_ns: int) -> None:
        """Retry only the same confirmed-OFF serial CLOSE under a fresh bound."""
        if self.pulse.claim_release_pending:
            await release_idle_claim(self.pulse, self.serial, deadline_ns=deadline_ns)

    def prior_device_work_quiescent(self) -> bool:
        """Reject a lagging accepted base while an earlier worker stage is live."""
        if self.pulse.claim_release_pending:
            return False
        relevant = {"apply_camera", "stop_preview", "prepare_preview", "start_preview"}
        for worker in self.workers.workers.values():
            preview = worker.preview
            if preview is not None and preview.stopping:
                return False
            if preview is not None and not preview.started:
                return False
            for child in worker.child_operations.values():
                if child.kind not in relevant:
                    continue
                if child.report is None or not child.report.complete:
                    return False
                if child.kind in {"prepare_preview", "start_preview"} and (
                    not child.report.HasField("succeeded") or not child.report.succeeded
                ):
                    return False
            if preview is not None:
                start = preview.start_operation
                start_child = (
                    worker.child_operations.get(start.command_id)
                    if start is not None
                    else None
                )
                if (
                    start_child is None
                    or start_child.report is None
                    or not start_child.report.complete
                    or not start_child.report.HasField("succeeded")
                    or not start_child.report.succeeded
                    or not any(
                        item.operation == start
                        and item.WhichOneof("evidence") == "started"
                        for item in worker.lifecycle_evidence.values()
                    )
                ):
                    return False
        return True

    async def retire_failed_edit(self, command_id: str) -> None:
        """Release only after relevant worker SDK and preview work is terminal."""
        await self.resolution.retire_failed_if_quiescent(
            control.OperationContext(command_id=command_id)
        )
