"""Prepared shared-ring capture resources for one camera worker (A03/A10)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from cephvr.acquisition.buffers.pixel_pool import PixelBufferPool
from cephvr.acquisition.buffers.queue import RecordingQueue
from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.buffers.ring import SharedRing
from cephvr.acquisition.camera.types import (
    CameraAdapter,
    CameraSettings,
    FrameTiming,
    PixelLayout,
    PurgeEvidence,
)
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.worker.capture import CameraCaptureLoop, CaptureWindow
from cephvr.acquisition.worker.frame_diagnostics import FrameDiagnosticTracker
from cephvr.acquisition.worker.warnings import WarningOccurrence
from cephvr.shared.clock import host_time_ns


class WorkerCaptureResources:
    """Own exact producer attachments and the single serialized capture loop."""

    def __init__(
        self,
        adapter: CameraAdapter,
        worker: acq.WorkerContext,
        warning_occurrence: Callable[[WarningOccurrence], None],
    ) -> None:
        self.adapter = adapter
        self.worker = worker
        self.warning_occurrence = warning_occurrence
        self.layout: PixelLayout | None = None
        self.capture: CameraCaptureLoop | None = None
        self._rings: dict[int, SharedRing] = {}
        self._window: CaptureWindow | None = None
        self._frame_timeout_ns = 0
        self._sdk_buffer_count = 0
        self._timing: FrameTiming | None = None
        self._locked_settings: CameraSettings | None = None
        self._active = False
        self._preview_max_hz: float | None = None
        self._session_preview = False
        self._scheduled_start_ns: int | None = None
        self._scheduled_end_ns: int | None = None
        self._released = False
        self._cutoff_reached = False
        self._attachments: tuple[acq.AttachedResource, ...] = ()
        self._released_attachments: list[acq.AttachedResource] = []
        self._diagnostics: FrameDiagnosticTracker | None = None
        self._first_trial_frame: Callable[[FrameRecord], None] = lambda _: None
        self._session_run_id: UUID | None = None
        self._preview_run_id: UUID | None = None
        self._scheduled_run_id: UUID | None = None
        self._admission_stop_ns: int | None = None
        self._stop_deadline_ns: int | None = None
        self._drain_until_ns: int | None = None
        self._capture_handoff: Callable[[], bool] = lambda: True

    @property
    def active(self) -> bool:
        return self._active

    @property
    def admission_stop_ns(self) -> int | None:
        return self._admission_stop_ns

    @property
    def requires_external_trigger(self) -> bool:
        return self._timing == "external_trigger"

    @property
    def frame_silence_timeout_ns(self) -> int:
        return self._frame_timeout_ns

    def prepare(
        self,
        payload: acq.CameraWorkerSetupPayload,
        *,
        preview_run_id: str | None = None,
        session_preview: bool = False,
    ) -> tuple[acq.AttachedResource, ...]:
        if self.capture is not None or self._rings:
            raise RuntimeError("prior worker capture resources are not released")
        self._released_attachments.clear()
        if (
            not payload.HasField("capture")
            or not payload.capture.HasField("sdk_buffer_count")
            or not payload.capture.HasField("frame_silence_timeout_ns")
        ):
            raise ValueError("capture payload lacks resolved buffer and silence limits")
        if (
            payload.capture.sdk_buffer_count <= 0
            or payload.capture.frame_silence_timeout_ns <= 0
        ):
            raise ValueError("capture buffer and silence limits must be positive")
        if not payload.HasField("device") or not payload.device.HasField(
            "frame_timing"
        ):
            raise ValueError("camera Setup lacks an applied frame timing")
        if not payload.device.HasField("settings"):
            raise ValueError("camera Setup lacks confirmed applied settings")
        timing = _frame_timing(payload.device.frame_timing)
        expected_settings = _settings_from_setup(payload.device.settings)
        actual_settings = self.adapter.read_settings()
        actual_timing = self.adapter.read_frame_timing()
        if actual_settings != expected_settings or actual_timing != timing:
            raise ValueError(
                "camera readback differs from the controller-confirmed Setup state"
            )
        layout = self.adapter.read_layout()
        _validate_layout(payload.layout, layout)
        self.adapter.configure_capture(timing, payload.capture.sdk_buffer_count)
        self._sdk_buffer_count = payload.capture.sdk_buffer_count
        self._timing = timing
        self._locked_settings = expected_settings
        self._frame_timeout_ns = payload.capture.frame_silence_timeout_ns
        self._preview_max_hz = (
            payload.capture.session_preview_max_hz
            if payload.capture.HasField("session_preview_max_hz")
            and payload.capture.session_preview_max_hz > 0
            else None
        )
        self._session_preview = session_preview
        self._preview_run_id = _uuid_or_none(preview_run_id)
        clock = (
            payload.camera_clock
            if payload.HasField("camera_clock")
            else camera_pb2.CameraClockDescriptor()
        )
        timestamp_available = (
            payload.native_timestamp_available
            if payload.HasField("native_timestamp_available")
            else clock.timestamp_source not in {"", "unavailable"}
        )
        counter_available = (
            payload.native_counter_available
            if payload.HasField("native_counter_available")
            else clock.counter_source not in {"", "unavailable"}
        )
        self._diagnostics = FrameDiagnosticTracker(
            clock,
            timestamp_available=timestamp_available,
            counter_available=counter_available,
        )
        for diagnostic in self._diagnostics.initial_unavailable():
            self.warning_occurrence(
                WarningOccurrence(
                    diagnostic.code,
                    host_time_ns(),
                    diagnostic.native_code,
                    diagnostic.details or "",
                )
            )
        try:
            attached: list[acq.AttachedResource] = []
            for attachment in payload.outputs:
                ring = self._attach_output(
                    attachment, layout, preview_run_id=preview_run_id
                )
                kind = attachment.buffer.kind
                self._rings[kind] = ring
                if attachment.buffer.HasField("session"):
                    self._session_run_id = UUID(attachment.buffer.session.session_id)
                attached.append(
                    acq.AttachedResource(
                        resource_id=attachment.buffer.allocation_id,
                        transfer_id=attachment.sync.transfer_id,
                    )
                )
            tracking = self._rings.get(acq.FRAME_BUFFER_KIND_TRACKING)
            preview = self._rings.get(acq.FRAME_BUFFER_KIND_PREVIEW)
            preview_expected = session_preview or preview_run_id is not None
            if preview_expected != (preview is not None):
                raise ValueError(
                    "preview ring does not match the requested capture mode"
                )
            self.layout = layout
            self.capture = CameraCaptureLoop(
                adapter=self.adapter,
                layout=layout,
                wait_timeout_ns=self._wait_timeout,
                frame_silence_timeout_ns=self._frame_timeout_ns,
                tracking_ring=tracking,
                preview_ring=preview,
                session_preview=session_preview,
                preview_max_hz=self._preview_max_hz,
                recording_window=lambda: self._window,
                warning_occurrence=self.warning_occurrence,
                diagnostics_for=self._diagnostics.observe,
                first_trial_frame=self._first_trial_frame,
            )
            self._attachments = tuple(attached)
            return tuple(attached)
        except BaseException:
            self.release()
            raise

    def set_first_trial_frame_callback(
        self, callback: Callable[[FrameRecord], None]
    ) -> None:
        self._first_trial_frame = callback
        if self.capture is not None:
            self.capture.first_trial_frame = callback

    def set_capture_handoff(self, callback: Callable[[], bool]) -> None:
        self._capture_handoff = callback

    def should_continue_drain(self) -> bool:
        return self._capture_handoff()

    def start(self) -> None:
        if self.capture is None or self.layout is None:
            raise RuntimeError("capture outputs are not prepared")
        if self._active:
            raise RuntimeError("camera capture is already running")
        run_id: UUID | None
        for ring in self._rings.values():
            if self._preview_run_id is not None:
                run_id = self._preview_run_id
            else:
                run_id = self._scheduled_run_id
            if run_id is None:
                raise RuntimeError("capture output has no exact run identity")
            ring.open_admission(run_id)
        if self._timing is None or self._sdk_buffer_count <= 0:
            raise RuntimeError("capture timing was not confirmed during Setup")
        if self._timing == "external_trigger":
            self.adapter.arm_external_trigger()
        else:
            self.adapter.start_free_running()
        self._active = True

    def set_window(self, window: CaptureWindow | None) -> None:
        self._window = window

    def install_recording(
        self, queue: RecordingQueue, pixel_pool: PixelBufferPool
    ) -> None:
        capture = self.capture
        if capture is None or self._active:
            raise RuntimeError("recording buffers require prepared, stopped capture")
        if pixel_pool.capacity < queue.capacity_frames + 2:
            raise ValueError("recording pool does not cover queue and in-flight slots")
        capture.recording_queue = queue
        capture.pixel_pool = pixel_pool

    def begin_trial(self) -> None:
        capture = self.capture
        if capture is None or self._active:
            raise RuntimeError("trial counters require prepared, stopped capture")
        capture.reset_trial_counters()
        if self._diagnostics is not None:
            self._diagnostics.reset()

    def prepare_trial(
        self,
        run_id: UUID,
        deadline_ns: int,
        *,
        should_continue_drain: Callable[[], bool],
    ) -> PurgeEvidence:
        """Verify the locked capture state and prepare this trial before Ready."""
        if self.capture is None or self._active:
            raise RuntimeError("trial preparation requires stopped prepared capture")
        if self._timing is None or self._locked_settings is None:
            raise RuntimeError("confirmed camera capture state is unavailable")
        if run_id.int == 0 or run_id.version != 4:
            raise ValueError("trial run identity must be a nonzero UUIDv4")
        for ring in self._rings.values():
            if ring.run_id != run_id or not ring.input_sealed:
                raise RuntimeError(
                    "shared ring was not reset and sealed for this exact trial"
                )

        # Compare fresh device state to the confirmed Setup baseline. A mismatch
        # requires a new resolution/adoption; this path never repairs drift.
        if self.adapter.read_settings() != self._locked_settings:
            raise ValueError("camera settings drifted after confirmed Setup")
        if self.adapter.read_frame_timing() != self._timing:
            raise ValueError("camera trigger mode drifted after confirmed Setup")
        expected_layout = self.layout
        if expected_layout is None:
            raise RuntimeError("confirmed camera image layout is unavailable")
        current_layout = self.adapter.read_layout()
        if not _same_layout(expected_layout, current_layout):
            raise ValueError("camera image layout drifted after confirmed Setup")

        purged = self.adapter.purge_stale_frames(
            deadline_ns, should_continue_drain=should_continue_drain
        )
        if not purged.accounting_complete:
            raise RuntimeError("stale SDK frame accounting is incomplete")
        self.adapter.configure_capture(self._timing, self._sdk_buffer_count)
        if self._timing == "external_trigger":
            # Coordinator gates PrepareTrial on confirmed MCU output OFF.
            self.adapter.arm_external_trigger()

        self._scheduled_run_id = run_id
        self.begin_trial()
        return purged

    def remove_recording(self) -> None:
        capture = self.capture
        if capture is not None:
            capture.recording_queue = None
            capture.pixel_pool = None

    def schedule(self, start_ns: int, end_ns: int, run_id: UUID) -> None:
        if self.capture is None or self._scheduled_start_ns is not None:
            raise RuntimeError("capture is not prepared or already scheduled")
        if run_id.int == 0 or run_id.version != 4:
            raise ValueError("trial run identity must be a nonzero UUIDv4")
        self._scheduled_run_id = run_id
        self._scheduled_start_ns, self._scheduled_end_ns = start_ns, end_ns
        self._released = False
        self._cutoff_reached = False
        self._admission_stop_ns = None
        self._stop_deadline_ns = None

    def release_schedule(self) -> None:
        if self._scheduled_start_ns is None:
            raise RuntimeError("capture has no retained schedule")
        self._released = True

    def cancel_schedule(self) -> None:
        """Fence a released pre-T schedule before it can start capture later."""
        if self._active:
            raise RuntimeError("active capture schedule cannot be cancelled")
        self._scheduled_start_ns = None
        self._scheduled_end_ns = None
        self._scheduled_run_id = None
        self._released = False
        self._window = None

    def next_deadline_ns(self) -> int | None:
        if self._scheduled_start_ns is not None and not self._active:
            return self._scheduled_start_ns
        if (
            self._scheduled_end_ns is not None
            and self._window is not None
            and not self._cutoff_reached
        ):
            return self._scheduled_end_ns
        return None

    def advance_due_stage(self, now_ns: int | None = None) -> None:
        now = host_time_ns() if now_ns is None else now_ns
        if (
            self._scheduled_start_ns is not None
            and not self._active
            and now >= self._scheduled_start_ns
        ):
            if not self._released:
                raise RuntimeError("scheduled start arrived before exact release")
            self.start()
            assert self._scheduled_end_ns is not None
            self.set_window(
                CaptureWindow(self._scheduled_start_ns, self._scheduled_end_ns)
            )
        if self._window is not None and self._scheduled_end_ns is not None:
            if now >= self._scheduled_end_ns:
                # Keep the window through the post-cutoff drain so every later
                # retrieved result is counted as excluded from this trial.
                self._cutoff_reached = True

    def capture_once(self, handoff: Callable[[], bool]) -> bool:
        capture = self.capture
        if capture is None:
            return False
        return capture.capture_once(handoff)

    def stop(
        self,
        deadline_ns: int,
        *,
        drain_margin_ns: int = 0,
        terminal_off_confirmed: bool = True,
        activity_stopped: Callable[[int], None] | None = None,
    ) -> object:
        if drain_margin_ns < 0:
            raise ValueError("post-cutoff drain margin cannot be negative")
        if self._admission_stop_ns is None:
            self._admission_stop_ns = host_time_ns()
        admission_stop_ns = self._admission_stop_ns
        if self._stop_deadline_ns is None:
            self._stop_deadline_ns = deadline_ns
        else:
            deadline_ns = min(deadline_ns, self._stop_deadline_ns)
        window = self._window
        if window is not None:
            self.set_window(
                CaptureWindow(window.start_ns, min(window.end_ns, admission_stop_ns))
            )
        self._cutoff_reached = True
        for ring in self._rings.values():
            ring.seal()
        timing = self._timing
        generation_stopped = False
        if self._active:
            generation_stopped = self.adapter.begin_terminal_drain()
        if (
            generation_stopped
            and terminal_off_confirmed
            and activity_stopped is not None
        ):
            activity_stopped(host_time_ns())
        margin_start = admission_stop_ns
        if timing == "external_trigger":
            if terminal_off_confirmed:
                margin_start = host_time_ns()
            else:
                generation_stopped = False
        margin_end = margin_start + drain_margin_ns
        drain_complete = (
            self._active
            and generation_stopped
            and terminal_off_confirmed
            and margin_end <= deadline_ns
        )
        if drain_complete:
            self._drain_until_ns = margin_end
            interrupted = False

            def handoff() -> bool:
                nonlocal interrupted
                permitted = self._capture_handoff()
                interrupted = not permitted
                return permitted

            while host_time_ns() < margin_end:
                if self.capture is None:
                    drain_complete = False
                    break
                self.capture.capture_once(handoff)
                if interrupted or host_time_ns() >= deadline_ns:
                    drain_complete = False
                    break
            if drain_complete and host_time_ns() >= margin_end:
                self.adapter.confirm_drain_margin()
            else:
                drain_complete = False
        self._drain_until_ns = None
        evidence = self.adapter.stop_capture(
            deadline_ns, should_continue_drain=self._capture_handoff
        )
        self._active = False
        self.set_window(None)
        self._scheduled_start_ns = None
        self._scheduled_end_ns = None
        self._scheduled_run_id = None
        self._released = False
        self._cutoff_reached = False
        return evidence

    def release(self) -> tuple[acq.AttachedResource, ...]:
        first_error: BaseException | None = None
        for kind, ring in tuple(self._rings.items()):
            try:
                resource_id = ring.descriptor.allocation_id
            except BaseException as exc:
                resource_id = ""
                if first_error is None:
                    first_error = exc
            try:
                ring.seal()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
            try:
                ring.close()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
                continue
            self._rings.pop(kind, None)
            for attachment in self._attachments:
                if attachment.resource_id == resource_id and all(
                    prior.resource_id != attachment.resource_id
                    for prior in self._released_attachments
                ):
                    saved = acq.AttachedResource()
                    saved.CopyFrom(attachment)
                    self._released_attachments.append(saved)
                    break
        if first_error is not None:
            raise first_error
        if self._rings:
            raise RuntimeError("one or more capture rings remain unreconciled")
        self.capture = None
        self.layout = None
        self._diagnostics = None
        self._session_run_id = None
        self._preview_run_id = None
        self._scheduled_run_id = None
        self._sdk_buffer_count = 0
        self._timing = None
        released = tuple(self._released_attachments)
        self._attachments = ()
        return released

    def _wait_timeout(self) -> int:
        timeout = self._frame_timeout_ns
        capture = self.capture
        if capture is not None and self._drain_until_ns is None:
            window = self._window
            baseline = capture.last_usable_ns
            if window is not None:
                baseline = max(baseline, window.start_ns)
            if baseline > 0:
                timeout = min(
                    timeout,
                    max(0, baseline + self._frame_timeout_ns - host_time_ns()),
                )
        if self._drain_until_ns is not None:
            now = host_time_ns()
            limits = [self._drain_until_ns]
            if self._stop_deadline_ns is not None:
                limits.append(self._stop_deadline_ns)
            timeout = min(timeout, max(0, min(limits) - now))
            return timeout
        deadline = self.next_deadline_ns()
        if deadline is not None:
            timeout = min(timeout, max(0, deadline - host_time_ns()))
        return timeout

    def _attach_output(
        self,
        attachment: acq.FrameBufferAttachment,
        layout: PixelLayout,
        *,
        preview_run_id: str | None,
    ) -> SharedRing:
        descriptor = attachment.buffer
        if descriptor.producer != self.worker.worker:
            raise ValueError("worker output descriptor names a different producer")
        if descriptor.camera != self.worker.camera:
            raise ValueError("worker output descriptor names another camera role")
        if descriptor.kind not in {
            acq.FRAME_BUFFER_KIND_TRACKING,
            acq.FRAME_BUFFER_KIND_PREVIEW,
        }:
            raise ValueError("worker output descriptor has an unsupported ring kind")
        if descriptor.HasField("preview"):
            if (
                preview_run_id is None
                or descriptor.preview.acquisition_run_id != preview_run_id
            ):
                raise ValueError("preview output has a stale manual run scope")
        elif not descriptor.HasField("session"):
            raise ValueError("worker output has no valid session or preview scope")
        return SharedRing.attach(attachment, layout, self.worker.worker)


def _validate_layout(
    descriptor: camera_pb2.CameraImageLayout, actual: PixelLayout
) -> None:
    if (
        descriptor.width != actual.width
        or descriptor.height != actual.height
        or descriptor.pixel_format != actual.pixel_format.sdk_name
        or descriptor.row_stride_bytes != actual.row_stride_bytes
        or descriptor.image_payload_bytes != actual.image_payload_bytes
    ):
        raise ValueError("worker camera layout differs from confirmed image descriptor")


def _same_layout(left: PixelLayout, right: PixelLayout) -> bool:
    return (
        left.width == right.width
        and left.height == right.height
        and left.pixel_format.sdk_name == right.pixel_format.sdk_name
        and left.row_stride_bytes == right.row_stride_bytes
        and left.image_payload_bytes == right.image_payload_bytes
    )


def _settings_from_setup(source: camera_pb2.CameraSettings) -> CameraSettings:
    from cephvr.acquisition.worker.camera_resolution import settings_from_wire

    return settings_from_wire(source)


def _frame_timing(value: int) -> FrameTiming:
    if value == camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER:
        return "external_trigger"
    if value == camera_pb2.FRAME_TIMING_FREE_RUNNING:
        return "free_running"
    raise ValueError("camera frame timing is unspecified")


def _uuid_or_none(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ValueError("capture run identity is not a UUID") from exc
    if parsed.int == 0 or parsed.version != 4:
        raise ValueError("capture run identity must be a nonzero UUIDv4")
    return parsed
