"""Prepare one camera session and its trials from confirmed worker inputs (A02)."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.shared.clock import host_time_ns

from .camera_configuration import WorkerCameraConfiguration
from .capture_runtime import WorkerCaptureResources
from .ports import command_from
from .state import WorkerBootstrap, WorkerState
from .trial_lifecycle import WorkerTrialLifecycle


class WorkerSessionPreparation:
    """Own readiness for one prepared session and exact per-trial reuse checks."""

    def __init__(
        self,
        bootstrap: WorkerBootstrap,
        state: WorkerState,
        camera_configuration: WorkerCameraConfiguration,
        captures: WorkerCaptureResources,
        *,
        begin_warning_scope: Callable[..., None],
        verify_wait: Callable[[int], None],
        report_lifecycle: Callable[[object, acq.WorkerLifecycleEvidence, int], None],
    ) -> None:
        self.bootstrap = bootstrap
        self.state = state
        self.camera_configuration = camera_configuration
        self.captures = captures
        self._begin_warning_scope = begin_warning_scope
        self._verify_wait = verify_wait
        self._report_lifecycle = report_lifecycle
        self.session_ready = False
        self._pending_ready: (
            tuple[acq.WorkerSetupSession, int, int, acq.WorkerLifecycleEvidence] | None
        ) = None

    def setup_session(
        self,
        request: object,
        deadline_ns: int,
        trial: WorkerTrialLifecycle,
    ) -> None:
        self.camera_configuration.require_adopted_setup(request)
        if not isinstance(request, acq.WorkerSetupSession) or not request.HasField(
            "camera"
        ):
            raise ValueError("session Setup payload is missing")
        policy = self.bootstrap.file_policy
        if (
            not policy.HasField("post_cutoff_drain_margin_ns")
            or policy.post_cutoff_drain_margin_ns <= 0
        ):
            raise ValueError(
                "camera Setup lacks a positive post-cutoff drain allowance"
            )
        self._begin_warning_scope(
            request.command.target.work,
            configuration_revision=request.configuration_revision,
        )
        trial.pulse_required = bool(
            request.camera.HasField("pulse_configuration")
            and request.camera.pulse_configuration.state.trial_state.enabled
        )
        attached = self.captures.prepare(
            request.camera,
            session_preview=request.camera.capture.session_preview_max_hz > 0,
        )
        self._verify_wait(deadline_ns)
        trial.recording_preparation.prepare_session(request)
        ready = acq.WorkerLifecycleEvidence()
        ready.ready.configuration_revision = request.configuration_revision
        ready.ready.required_checks_passed = True
        for resource in attached:
            ready.ready.attached_resources.add().CopyFrom(resource)
        started_ns = host_time_ns()
        self.captures.start_session()
        self.captures.readiness_deadline_ns = deadline_ns
        self._pending_ready = (request, deadline_ns, started_ns, ready)

    def first_usable_frame(self, record: object) -> bool:
        pending = self._pending_ready
        if pending is None:
            return False
        if not isinstance(record, FrameRecord) or not record.valid_image:
            raise TypeError("session readiness requires a usable camera frame")
        request, deadline_ns, started_ns, ready = pending
        if record.acquisition_time_ns < started_ns:
            return False
        if host_time_ns() >= deadline_ns or record.acquisition_time_ns >= deadline_ns:
            raise TimeoutError("usable camera delivery missed original Setup deadline")
        self._pending_ready = None
        self.captures.readiness_deadline_ns = None
        self.session_ready = True
        self._report_lifecycle(request, ready, deadline_ns)
        return True

    @property
    def readiness_deadline_ns(self) -> int | None:
        return self._pending_ready[1] if self._pending_ready is not None else None

    def advance_due_stage(self) -> None:
        deadline = self.readiness_deadline_ns
        if deadline is not None and host_time_ns() >= deadline:
            self._pending_ready = None
            self.captures.readiness_deadline_ns = None
            raise TimeoutError("usable camera delivery missed original Setup deadline")

    def prepare_trial(
        self,
        request: object,
        deadline_ns: int,
        trial: WorkerTrialLifecycle,
    ) -> None:
        self.require_ready_session(request)
        if not isinstance(request, acq.WorkerPrepareTrial):
            raise TypeError("trial preparation has the wrong protobuf type")
        self._begin_warning_scope(request.command.target.work)
        trial.prepare_trial_state(request, deadline_ns)
        trial.recording_preparation.prepare_trial(request, deadline_ns)
        trial.trial_prepared = True
        evidence = acq.WorkerLifecycleEvidence()
        evidence.ready.configuration_revision = (
            self.state.confirmed_configuration_revision
        )
        evidence.ready.required_checks_passed = True
        self._report_lifecycle(request, evidence, deadline_ns)

    def cancel_setup(self) -> None:
        self.session_ready = False
        self._pending_ready = None
        self.captures.readiness_deadline_ns = None

    def require_ready_session(self, request: object) -> None:
        command = command_from(request)
        if not command.target.HasField("work"):
            raise ValueError("trial operation has no exact work context")
        if not self.session_ready:
            raise RuntimeError("worker session is not prepared")
        required = getattr(request, "required_configuration_revision", None)
        if (
            required is not None
            and required != self.state.confirmed_configuration_revision
        ):
            raise RuntimeError("trial configuration revision is stale")
