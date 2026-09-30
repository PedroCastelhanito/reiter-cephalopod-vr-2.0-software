"""Bounded, retryable worker resource cleanup and evidence (A02/E08)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.worker.capture_runtime import WorkerCaptureResources
from cephvr.acquisition.worker.recording_runtime import WorkerRecordingRuntime
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns

from .ports import command_from
from .state import WorkerState


@dataclass(slots=True)
class PendingWorkerCleanup:
    operation: str
    request: object
    deadline_ns: int
    report: acq.WorkerOperationReport


class WorkerCleanupLifecycle:
    """Own cleanup continuation state without proxying the operation executor."""

    def __init__(
        self,
        state: WorkerState,
        adapter: BaslerCameraAdapter,
        captures: WorkerCaptureResources,
        recording: WorkerRecordingRuntime | None,
        *,
        capacity: int,
        extra_resources: Callable[[], Mapping[str, bool]],
        report_lifecycle: Callable[[object, acq.WorkerLifecycleEvidence, int], None],
        report_operation: Callable[[acq.WorkerOperationReport, int], None],
        shutdown: Callable[[int], None],
        recording_reconciled: Callable[[], None],
        external_wake: Callable[[], None],
    ) -> None:
        if capacity <= 0:
            raise ValueError("cleanup continuation capacity must be positive")
        self.state = state
        self.adapter = adapter
        self.captures = captures
        self.recording = recording
        self.capacity = capacity
        self.extra_resources = extra_resources
        self.report_lifecycle = report_lifecycle
        self.report_operation = report_operation
        self.shutdown = shutdown
        self.recording_reconciled = recording_reconciled
        self.external_wake = external_wake
        self._pending: list[PendingWorkerCleanup] = []
        self._future: Future[list[control.OutputResult]] | None = None
        self.outputs: list[control.OutputResult] = []
        self._ambient_deadline_ns: int | None = None

    def begin(self, deadline_ns: int) -> None:
        runtime = self.recording
        if runtime is None or not runtime.enabled or self._future is not None:
            return
        self._future = runtime.fail_cleanup(deadline_ns=deadline_ns)
        self._future.add_done_callback(lambda _future: self.external_wake())

    def begin_ambient_release(self, deadline_ns: int) -> None:
        """Close worker-owned resources after recording reconciliation on loss."""
        if self._ambient_deadline_ns is None:
            self._ambient_deadline_ns = deadline_ns
        self.begin(self._ambient_deadline_ns)

    def begin_operation(
        self,
        operation: str,
        request: object,
        deadline_ns: int,
        report: acq.WorkerOperationReport,
    ) -> bool:
        if not self._reconcile(deadline_ns):
            if len(self._pending) >= self.capacity:
                raise RuntimeError("retained cleanup continuation capacity is full")
            self._pending.append(
                PendingWorkerCleanup(operation, request, deadline_ns, report)
            )
            return False
        self._release(operation, request, deadline_ns)
        return True

    def advance(self) -> None:
        if not self._pending:
            self._advance_ambient_release()
            return
        pending = self._pending[0]
        failure: control.Failure | None = None
        try:
            if not self._reconcile(pending.deadline_ns):
                if host_time_ns() < pending.deadline_ns:
                    return
                raise TimeoutError("recording cleanup exceeded its original deadline")
            self._release(pending.operation, pending.request, pending.deadline_ns)
            if host_time_ns() >= pending.deadline_ns:
                raise TimeoutError("cleanup completed after its original deadline")
            succeeded = True
        except BaseException as exc:
            failure = control.Failure(code=_failure_code(exc), message=str(exc)[:2048])
            succeeded = False
        command = command_from(pending.request)
        self.state.complete_operation(
            command.command_id,
            succeeded=succeeded,
            progress="complete" if succeeded else "failed",
            now_ns=host_time_ns(),
            failure=failure,
            retained_result=pending.report,
        )
        self.report_operation(pending.report, pending.deadline_ns)
        if succeeded:
            self.state.finalize_scope(command.target.work, host_time_ns())
            if pending.operation in {"Cleanup", "Shutdown"}:
                self.state.finalize_terminal_command(command.command_id, host_time_ns())
        self._pending.pop(0)

    def _advance_ambient_release(self) -> None:
        deadline = self._ambient_deadline_ns
        if deadline is None:
            return
        if not self._reconcile(deadline):
            return
        self.captures.release()
        self.adapter.release_device()
        self._ambient_deadline_ns = None

    def _reconcile(self, deadline_ns: int) -> bool:
        runtime = self.recording
        if runtime is None or not runtime.enabled:
            return True
        if self._future is None:
            self.begin(deadline_ns)
        future = self._future
        if future is None or not future.done():
            return False
        try:
            results = future.result()
        except BaseException:
            if host_time_ns() >= deadline_ns:
                raise
            self._future = None
            self.begin(deadline_ns)
            return False
        self.outputs = [
            control.OutputResult.FromString(
                result.SerializeToString(deterministic=True)
            )
            for result in results
        ]
        runtime.recycle_finished(deadline_ns)
        self._future = None
        self.recording_reconciled()
        return True

    def _release(self, operation: str, request: object, deadline_ns: int) -> None:
        released = self.captures.release()
        self.adapter.release_device()
        evidence = acq.WorkerLifecycleEvidence()
        evidence.cleanup.outputs.extend(self.outputs)
        evidence.cleanup.resources.add(
            resource=f"camera-device:{self.state.context.worker.generation}",
            released=True,
        )
        for item in released:
            evidence.cleanup.resources.add(resource=item.resource_id, released=True)
        for resource, is_released in sorted(self.extra_resources().items()):
            evidence.cleanup.resources.add(resource=resource, released=is_released)
        self.report_lifecycle(request, evidence, deadline_ns)
        if operation == "Shutdown":
            self.shutdown(deadline_ns)


def _failure_code(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "DEADLINE_EXCEEDED"
    if isinstance(exc, ValueError):
        return "INVALID_REQUEST"
    return "WORKER_OPERATION_FAILED"
