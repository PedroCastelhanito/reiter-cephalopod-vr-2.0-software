"""Per-trial recording assembly using the shared bounded writer (A07/A08)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import Future
from pathlib import Path
from typing import TypeVar

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.buffers.pixel_pool import PixelBufferPool
from cephvr.acquisition.buffers.queue import RecordingQueue
from cephvr.acquisition.recording.capabilities import inspect_encoder
from cephvr.acquisition.recording.encoder import SupervisedEncoderLauncher
from cephvr.acquisition.recording.encoder_probe import SupervisedCapabilityProbe
from cephvr.acquisition.recording.encoding import EncoderCapabilities
from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.recording.paths import RecordingPaths
from cephvr.acquisition.recording.session import RecordingSession
from cephvr.acquisition.recording.session_contracts import (
    PulseEvidence,
    RecordingCompletionContext,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.worker.recording_handoff import RecordingCompletionHandoff
from cephvr.acquisition.worker.recording_thread import RecordingOwnerThread
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.file_sync import (
    WindowsFileSyncOwner,
    WindowsFrameLogSync,
    WindowsVideoSyncFactory,
)
from cephvr.platform.windows.nvenc_capabilities import NvencProbeOwner
from cephvr.shared.pixels.preparer import PixelPreparer
from cephvr.shared.pixels.types import PixelLayout
from cephvr.shared.transport_deadlines import remaining_seconds

_T = TypeVar("_T")


class WorkerRecordingRuntime:
    """Own exact per-worker encoder/storage dependencies and one recording thread."""

    def __init__(
        self,
        *,
        worker: acq.WorkerContext,
        file_sync_owner: WindowsFileSyncOwner,
        video_sync_factory: WindowsVideoSyncFactory,
        launcher: SupervisedEncoderLauncher,
        writer: RecordingOwnerThread,
        nvenc: NvencProbeOwner,
        trial_finished_allowance_ns: int,
    ) -> None:
        self.worker = worker
        self.file_sync_owner = file_sync_owner
        self.video_sync_factory = video_sync_factory
        self.launcher = launcher
        self.writer = writer
        self.nvenc = nvenc
        if trial_finished_allowance_ns <= 0:
            raise ValueError("trial finished allowance must be positive")
        self.trial_finished_allowance_ns = trial_finished_allowance_ns
        self._settings: acq.RecordingSettings | None = None
        self._capabilities: EncoderCapabilities | None = None
        self._preparer: PixelPreparer | None = None
        self._queue: RecordingQueue | None = None
        self._pool: PixelBufferPool | None = None
        self._session_id = ""
        self._device_id = ""
        self._camera_clock: camera.CameraClockDescriptor | None = None
        self._role = _camera_role(worker.camera)
        self._started = False
        self._installed = False
        self._handoff: RecordingCompletionHandoff | None = None
        self._run_future: Future[list[types.OutputResult]] | None = None
        self._normal_finish_deadline_ns: int | None = None
        self._install_future: Future[None] | None = None
        self._prepare_future: Future[None] | None = None
        self._pending_session: RecordingSession | None = None

    @property
    def enabled(self) -> bool:
        return self._settings is not None

    @property
    def cleanup_blocked(self) -> bool:
        return self.file_sync_owner.cleanup_blocked

    @property
    def recording_queue(self) -> RecordingQueue | None:
        return self._queue

    @property
    def pixel_pool(self) -> PixelBufferPool | None:
        return self._pool

    @property
    def completion_deadline_ns(self) -> int | None:
        """Retained normal finish budget derived from T_end and locked policy."""
        return self._normal_finish_deadline_ns

    def prepare_session(
        self,
        settings: acq.RecordingSettings,
        layout: camera.CameraImageLayout,
        native_layout: PixelLayout,
        work: types.WorkContext,
        parent_operation: types.OperationContext,
        *,
        session_id: str,
        device_id: str,
        camera_clock: camera.CameraClockDescriptor,
        role: str,
        nominal_rate_hz: float,
        nominal_rate_source: str,
        warning_occurrence: Callable[
            [str, str | None, str | None, int, int | None], None
        ],
        capability_resource_released: Callable[[str, bool], None],
        deadline_ns: int,
    ) -> None:
        if self._settings is not None:
            raise RuntimeError("recording capabilities are already prepared")
        _validate_recording_settings(settings)
        if (
            work.WhichOneof("work") != "session"
            or work.session.session_id != session_id
        ):
            raise ValueError("recording capability probe requires exact Setup session")
        if role != self._role or not device_id or camera_clock.device_id != device_id:
            raise ValueError("recording Setup identity differs from exact worker")
        self.launcher.bind_operation(work, parent_operation)
        probe = SupervisedCapabilityProbe(
            self.launcher,
            work,
            parent_operation,
            capability_resource_released,
        )
        codec = _codec(settings.ffmpeg_args)
        try:
            capabilities = inspect_encoder(
                settings.ffmpeg_executable,
                codec=codec,
                nvenc_owner=self.nvenc,
                probe=probe,
                deadline_ns=deadline_ns,
            )
        except BaseException as original:
            try:
                probe.retry_cleanup(deadline_ns=deadline_ns)
            except BaseException as cleanup_error:
                original.add_note(f"FFmpeg probe cleanup remains: {cleanup_error}")
            try:
                self.nvenc.retry_cleanup(deadline_ns=deadline_ns)
            except BaseException as cleanup_error:
                original.add_note(f"NVENC probe cleanup remains: {cleanup_error}")
            raise
        self._preparer = PixelPreparer(native_layout)
        self._settings = acq.RecordingSettings.FromString(
            settings.SerializeToString(deterministic=True)
        )
        self._capabilities = capabilities
        self._session_id = session_id
        self._device_id = device_id
        self._camera_clock = camera.CameraClockDescriptor.FromString(
            camera_clock.SerializeToString(deterministic=True)
        )
        self._nominal_rate_hz = nominal_rate_hz
        self._nominal_rate_source = nominal_rate_source
        self._warning_occurrence = warning_occurrence
        self._layout = camera.CameraImageLayout.FromString(
            layout.SerializeToString(deterministic=True)
        )

    def prepare_trial(
        self,
        plans: tuple[types.OutputPlan, ...],
        trial_identity: RecordingIdentity,
        deadline_ns: int,
        *,
        started_observed: Callable[[int], None],
    ) -> None:
        if (
            self._settings is None
            or self._preparer is None
            or self._capabilities is None
            or self._layout is None
        ):
            raise RuntimeError("session recording capabilities are not prepared")
        if (
            self._session_id != trial_identity.session_id
            or self._role != trial_identity.camera_role
            or self._device_id != trial_identity.device_id
            or trial_identity.session_config_reference
            != self._settings.session_config_reference
            or self._camera_clock is None
            or self._camera_clock.SerializeToString(deterministic=True)
            != trial_identity.camera_clock.SerializeToString(deterministic=True)
        ):
            raise ValueError("trial recording identity differs from confirmed session")
        if self._installed:
            raise RuntimeError("prior trial recording has not been recycled")
        queue = RecordingQueue(
            int(self._settings.recording_queue_frames),
            int(self._settings.pending_records_capacity),
        )
        pool = PixelBufferPool(
            self._preparer.layout.image_payload_bytes,
            queue.capacity_frames + 2,
        )
        session = RecordingSession(
            self._settings,
            self._layout,
            trial_identity,
            RecordingPaths(plans, self.worker.owner.generation),
            queue,
            pool,
            self._preparer,
            self._capabilities,
            self.launcher,
            self.video_sync_factory,
            WindowsFrameLogSync(),
            role=self._role,
            nominal_frame_rate_hz=self._nominal_rate_hz,
            nominal_rate_source=self._nominal_rate_source,
            warning_occurrence=self._warning_occurrence,
            started_observed=started_observed,
        )
        if not self._started:
            self.writer.start()
            self._started = True
        # Retain all local ownership before crossing the async thread boundary.
        self._installed = True
        self._queue, self._pool = queue, pool
        self._handoff = RecordingCompletionHandoff()
        self._run_future = None
        self._pending_session = session
        self._install_future = self.writer.install(session)
        self._wait(self._install_future, deadline_ns)
        self._prepare_future = self.writer.prepare()
        self._wait(self._prepare_future, deadline_ns)

    def schedule(self, request: acq.WorkerSchedule, *, deadline_ns: int) -> None:
        self._wait(self.writer.schedule(request, deadline_ns=deadline_ns), deadline_ns)
        if not request.HasField("end_monotonic_ns"):
            raise ValueError("retained recording schedule lacks its normal end")
        self._normal_finish_deadline_ns = (
            request.end_monotonic_ns + self.trial_finished_allowance_ns
        )
        if self._handoff is None:
            raise RuntimeError("recording trial has no completion handoff")
        self._handoff.set_normal_deadline(self._normal_finish_deadline_ns)

    def release(self, request: acq.WorkerRelease, *, deadline_ns: int) -> None:
        self._wait(self.writer.release(request, deadline_ns=deadline_ns), deadline_ns)
        if self._handoff is None or self._run_future is not None:
            raise RuntimeError("recording driver has no fresh terminal handoff")
        if self._normal_finish_deadline_ns is None:
            raise RuntimeError("recording driver lacks its retained finish budget")
        self._run_future = self.writer.run(
            self._handoff,
            self._handoff.pulse_evidence,
            self._handoff.completion_context,
            deadline_ns=self._normal_finish_deadline_ns,
        )

    def finish(
        self,
        marker: CaptureEndMarker,
        pulses: PulseEvidence,
        completion: RecordingCompletionContext,
        *,
        deadline_ns: int,
    ) -> Future[list[types.OutputResult]]:
        if self._queue is None or self._pool is None or self._handoff is None:
            raise RuntimeError("recording trial is not prepared")
        if self._run_future is None:
            raise RuntimeError("recording owner has not started at ReleaseTrial")
        self._queue.close()
        self._handoff.publish(marker, pulses, completion, deadline_ns=deadline_ns)
        return self._run_future

    @property
    def run_future(self) -> Future[list[types.OutputResult]] | None:
        """Future retained since ReleaseTrial; completion callbacks run off-camera."""
        return self._run_future

    def completed_results(self) -> list[types.OutputResult]:
        """Read the result only after the retained Future has completed."""
        future = self._run_future
        if future is None or not future.done():
            raise RuntimeError("recording result is not complete")
        return future.result()

    def cancel_before_start(
        self, *, deadline_ns: int
    ) -> Future[list[types.OutputResult]]:
        if self._handoff is None:
            raise RuntimeError("recording driver is not active")
        if self._queue is not None:
            self._queue.close()
        if self._run_future is None:
            self._ensure_install_submitted()
            self._run_future = self.writer.cancel_before_start(deadline_ns=deadline_ns)
        else:
            self._handoff.request_abort("cancel_before_start", deadline_ns=deadline_ns)
        return self._run_future

    def recycle_finished(self, deadline_ns: int) -> None:
        if self._run_future is None or not self._run_future.done():
            raise RuntimeError("recording writer has not reported terminal evidence")
        if self._queue is not None and self._queue.pending_records:
            raise RuntimeError("recording queue still has unaccounted rows")
        if self._pool is not None:
            self._pool.close()
        self._wait(self.writer.remove_finished(), deadline_ns)
        self._installed = False
        self._queue = None
        self._pool = None
        self._handoff = None
        self._run_future = None
        self._normal_finish_deadline_ns = None
        self._install_future = None
        self._prepare_future = None
        self._pending_session = None

    def fail_cleanup(self, *, deadline_ns: int) -> Future[list[types.OutputResult]]:
        """Signal the active pump, then queue an idempotent cleanup retry."""
        if self._queue is not None:
            self._queue.close()
        if self._handoff is not None and self._run_future is not None:
            self._handoff.request_abort("failed_cleanup", deadline_ns=deadline_ns)
        self._ensure_install_submitted()
        cleanup = self.writer.fail_cleanup(deadline_ns=deadline_ns)
        self._run_future = cleanup
        return cleanup

    def _ensure_install_submitted(self) -> None:
        if self._install_future is None and self._pending_session is not None:
            self._install_future = self.writer.install(self._pending_session)

    def close(self, timeout_s: float | None) -> bool:
        if self.file_sync_owner.cleanup_blocked:
            self.file_sync_owner.retry_cleanup()
        closed = self.writer.close(timeout_s)
        if closed and not self._installed and self._preparer is not None:
            self._preparer.close()
            self._preparer = None
        return closed

    @staticmethod
    def _wait(future: Future[_T], deadline_ns: int) -> _T:
        return future.result(timeout=remaining_seconds(deadline_ns))


def _validate_recording_settings(settings: acq.RecordingSettings) -> None:
    for field in (
        "video_sync_interval_ns",
        "fragment_target_ns",
        "encoder_stall_timeout_ns",
        "frame_log_sync_interval_ns",
        "pending_records_capacity",
        "diagnostic_tail_max_lines",
        "diagnostic_tail_max_bytes",
        "recording_bit_depth",
        "recording_queue_frames",
    ):
        if not settings.HasField(field) or getattr(settings, field) <= 0:
            raise ValueError(f"recording settings lack positive {field}")
    if not Path(settings.ffmpeg_executable).is_absolute():
        raise ValueError("FFmpeg executable path must be absolute")


def _codec(arguments: Iterable[str]) -> str:
    values: tuple[str, ...] = tuple(arguments)
    for index, item in enumerate(values[:-1]):
        if item == "-c:v":
            codec = values[index + 1]
            if codec in {"h264_nvenc", "hevc_nvenc", "av1_nvenc"}:
                return codec
            raise ValueError("recording codec is outside the accepted NVENC policy")
    raise ValueError("recording arguments do not select an explicit codec")


def _camera_role(value: int) -> str:
    role = camera.CameraRole.Name(value).lower().removeprefix("camera_role_")
    if role not in {"behavioral", "tracking", "eye_tracking"}:
        raise ValueError("worker camera role is unsupported")
    return role
