"""Manual preview prepare, usable-frame start evidence and bounded stop (A10)."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns

from .capture_runtime import WorkerCaptureResources
from .state import WorkerState


class WorkerPreviewLifecycle:
    """Own preview command state without retaining the whole worker executor."""

    def __init__(
        self,
        state: WorkerState,
        captures: WorkerCaptureResources,
        adapter: BaslerCameraAdapter,
        *,
        begin_warning_scope: Callable[..., None],
        complete_warning_scope: Callable[[], None],
        verify_wait: Callable[[int], None],
        operation_deadline: Callable[[str], int],
        report_lifecycle: Callable[[object, acq.WorkerLifecycleEvidence, int], None],
        owner_failure: Callable[[BaseException], None],
        recovery_ns: int,
        clock_ns: Callable[[], int] = host_time_ns,
    ) -> None:
        self.state = state
        self.captures = captures
        self.adapter = adapter
        self._begin_warning_scope = begin_warning_scope
        self._complete_warning_scope = complete_warning_scope
        self._verify_wait = verify_wait
        self._operation_deadline = operation_deadline
        self._report_lifecycle = report_lifecycle
        self._owner_failure = owner_failure
        self._recovery_ns = recovery_ns
        self._clock_ns = clock_ns
        self.manual_preview = False
        self.run_id: str | None = None
        self._start_request: acq.WorkerStartPreview | None = None
        self._start_deadline_ns: int | None = None

    @property
    def next_deadline_ns(self) -> int | None:
        return self._start_deadline_ns

    def prepare(self, request: object) -> None:
        if not isinstance(request, acq.WorkerPreparePreview):
            raise TypeError("preview preparation request has the wrong type")
        if not request.HasField("camera") or not request.HasField(
            "configuration_revision"
        ):
            raise ValueError("preview preparation requires confirmed camera payload")
        if (
            request.configuration_revision
            != self.state.confirmed_configuration_revision
        ):
            raise RuntimeError("preview preparation configuration revision is stale")
        self._begin_warning_scope(
            control.WorkContext(),
            configuration_revision=request.configuration_revision,
            preview_run_id=request.preview_run_id,
        )
        attached = self.captures.prepare(
            request.camera,
            preview_run_id=request.preview_run_id,
            session_preview=False,
        )
        deadline_ns = self._operation_deadline(request.command.command_id)
        self._verify_wait(deadline_ns)
        self.manual_preview = True
        self.run_id = request.preview_run_id
        ready = acq.WorkerLifecycleEvidence()
        ready.ready.configuration_revision = request.configuration_revision
        ready.ready.required_checks_passed = True
        for resource in attached:
            ready.ready.attached_resources.add().CopyFrom(resource)
        self._report_lifecycle(request, ready, deadline_ns)

    def start(self, request: object) -> None:
        if not isinstance(request, acq.WorkerStartPreview):
            raise TypeError("preview start request has the wrong type")
        if not self.manual_preview:
            raise RuntimeError("preview resources were not prepared")
        if request.preview_run_id != self.run_id:
            raise RuntimeError("preview start does not match prepared preview run")
        if self._start_request is not None:
            raise RuntimeError("preview start is already awaiting a usable frame")
        deadline_ns = self._operation_deadline(request.command.command_id)
        self._start_request = acq.WorkerStartPreview.FromString(
            request.SerializeToString(deterministic=True)
        )
        self._start_deadline_ns = deadline_ns
        self.captures.start()

    def stop(self, request: object, deadline_ns: int) -> None:
        if not isinstance(request, acq.WorkerStopPreview):
            raise TypeError("preview stop request has the wrong type")
        if not self.run_id or request.preview_run_id != self.run_id:
            raise RuntimeError("preview stop does not match the retained preview run")
        if self.captures.active:
            self.captures.stop(deadline_ns)
        released = self.captures.release()
        self._complete_warning_scope()
        self.manual_preview = False
        self.run_id = None
        self._start_request = None
        self._start_deadline_ns = None
        if request.release_device:
            self.adapter.release_device()
        evidence = acq.WorkerLifecycleEvidence()
        evidence.stopped.actual_stop_monotonic_ns = self._clock_ns()
        evidence.stopped.activity_stopped = True
        evidence.stopped.recording_interval_sealed = True
        self._report_lifecycle(request, evidence, deadline_ns)
        if released:
            cleanup = acq.WorkerLifecycleEvidence()
            for resource in released:
                cleanup.cleanup.resources.add(
                    resource=resource.resource_id, released=True
                )
            self._report_lifecycle(request, cleanup, deadline_ns)

    def first_usable_frame(self, record: object) -> bool:
        request = self._start_request
        if (
            not isinstance(record, FrameRecord)
            or not self.manual_preview
            or request is None
        ):
            return False
        deadline_ns = self._start_deadline_ns
        if deadline_ns is None:
            raise RuntimeError("preview start lost its retained deadline")
        evidence = acq.WorkerLifecycleEvidence()
        evidence.started.actual_start_monotonic_ns = record.acquisition_time_ns
        activity = evidence.started.first_activity.add()
        activity.kind = "camera_callback"
        activity.observed_monotonic_ns = record.acquisition_time_ns
        activity.device_evidence.camera = self.state.context.camera
        activity.device_evidence.producer.CopyFrom(self.state.context.worker)
        self._start_request = None
        self._start_deadline_ns = None
        self._report_lifecycle(request, evidence, deadline_ns)
        return True

    def advance_due_stage(self) -> None:
        deadline_ns = self._start_deadline_ns
        if self._start_request is None or deadline_ns is None:
            return
        if self._clock_ns() < deadline_ns:
            return
        self._start_request = None
        self._start_deadline_ns = None
        self.manual_preview = False
        self.run_id = None
        with self.state.lock:
            self.state.interrupted = True
        cleanup_deadline = self._clock_ns() + self._recovery_ns
        if self.captures.active:
            self.captures.stop(cleanup_deadline)
        self.captures.release()
        self.adapter.release_device()
        self._owner_failure(
            TimeoutError("manual preview produced no usable frame by its deadline")
        )

    def fence(self) -> None:
        """Forget pending preview evidence while owner reconciles native resources."""
        self._start_request = None
        self._start_deadline_ns = None
        self.manual_preview = False
        self.run_id = None
