"""First real camera/recording activity evidence for one scheduled trial (A08)."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock

from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control

from .state import WorkerBootstrap, WorkerState


class TrialActivityEvidence:
    """Pair exact camera and recording activity before publishing Started."""

    def __init__(
        self,
        bootstrap: WorkerBootstrap,
        state: WorkerState,
        source: Callable[[acq.WorkerContext], acq.WorkerContext],
        report_lifecycle: Callable[[object, acq.WorkerLifecycleEvidence, int], None],
    ) -> None:
        self.bootstrap = bootstrap
        self.state = state
        self.source = source
        self.report_lifecycle = report_lifecycle
        self._lock = Lock()
        self._camera: control.ActivityEvidence | None = None
        self._recording: control.ActivityEvidence | None = None

    def reset(self) -> None:
        with self._lock:
            self._camera = None
            self._recording = None

    def camera_frame(self, record: FrameRecord) -> None:
        activity = control.ActivityEvidence(
            kind="camera_callback",
            observed_monotonic_ns=record.acquisition_time_ns,
        )
        activity.device_evidence.camera = self.bootstrap.context.camera
        activity.device_evidence.producer.CopyFrom(self.bootstrap.context.worker)
        if record.camera_frame_counter is not None:
            activity.native_counter = record.camera_frame_counter
        with self._lock:
            self._camera = activity

    def recording_frame(self, observed_ns: int) -> None:
        activity = control.ActivityEvidence(
            kind="recording_input_processing", observed_monotonic_ns=observed_ns
        )
        activity.device_evidence.camera = self.bootstrap.context.camera
        activity.device_evidence.producer.CopyFrom(self.bootstrap.context.worker)
        with self._lock:
            self._recording = activity

    def publish_if_ready(
        self, schedule: acq.WorkerSchedule | None, *, recording_required: bool
    ) -> None:
        if schedule is None:
            return
        with self._lock:
            camera_activity = self._camera
            recording_activity = self._recording
            if camera_activity is None or (
                recording_required and recording_activity is None
            ):
                return
            self._camera = None
            self._recording = None
        evidence = acq.WorkerLifecycleEvidence()
        evidence.started.actual_start_monotonic_ns = (
            camera_activity.observed_monotonic_ns
        )
        evidence.started.first_activity.add().CopyFrom(camera_activity)
        if recording_activity is not None:
            evidence.started.first_activity.add().CopyFrom(recording_activity)
        command = schedule.command
        evidence.source.CopyFrom(self.source(command.target))
        evidence.operation.command_id = command.command_id
        evidence.state_revision = self.state.state_revision + 1
        deadline_ns = (
            schedule.start_monotonic_ns
            + self.bootstrap.control_policies.start_evidence_allowance_ns
        )
        self.report_lifecycle(schedule, evidence, deadline_ns)
