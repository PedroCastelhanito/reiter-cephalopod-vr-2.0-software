"""Per-worker recording state machine. File writes and encoder I/O stay on owner thread."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.recording.encoding import (
    EncoderCapabilities,
    ResolvedEncoding,
)
from cephvr.acquisition.recording.frame_log import (
    FileSync,
    FrameLogWriter,
)
from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.recording.paths import (
    RecordingPaths,
    resolve_recording_paths,
)
from cephvr.acquisition.recording.progress_watchdog import EncoderProgressWatchdog
from cephvr.acquisition.recording.session_cleanup import (
    cancel_before_start as cancel_scheduled_before_start,
)
from cephvr.acquisition.recording.session_cleanup import (
    close_failed_recording,
)
from cephvr.acquisition.recording.session_cleanup import (
    unlaunched_outputs as _unlaunched_outputs,
)
from cephvr.acquisition.recording.session_completion import (
    finish_recording,
    terminal_capture_proof,
)
from cephvr.acquisition.recording.session_contracts import (
    EncoderLauncher,
    EncoderProcess,
    EndMarkerSource,
    PixelBufferPool,
    PulseEvidence,
    QueueEntry,
    RecordingCompletionContext,
    RecordingFailure,
    RecordingQueue,
    VideoSync,
    VideoSyncFactory,
    WarningOccurrence,
)
from cephvr.acquisition.recording.session_diagnostics import RecordingDiagnostics
from cephvr.acquisition.recording.session_finalizer import FinalizationProgress
from cephvr.acquisition.recording.session_prepare import prepare_recording
from cephvr.acquisition.recording.session_pump import (
    SubmittedFrameLogFailure,
    write_ordered_entry,
    write_trailing_slots,
)
from cephvr.acquisition.recording.session_schedule import launch_scheduled_encoder
from cephvr.acquisition.recording.session_storage import (
    observe_video_identity,
    stat_identity,
    sync_due,
    write_deadline,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.pixels.preparer import PixelPreparer


class RecordingSession:
    """One A07 thread owns each camera's queue, MP4 and append-only frame log."""

    def __init__(
        self,
        settings: acq.RecordingSettings,
        layout: camera.CameraImageLayout,
        identity: RecordingIdentity,
        paths: RecordingPaths,
        queue: RecordingQueue,
        pixel_pool: PixelBufferPool,
        pixel_preparer: PixelPreparer,
        capabilities: EncoderCapabilities,
        launcher: EncoderLauncher,
        video_sync_factory: VideoSyncFactory,
        frame_log_sync: FileSync,
        *,
        role: str,
        nominal_frame_rate_hz: float,
        nominal_rate_source: str,
        warning_occurrence: WarningOccurrence,
        started_observed: Callable[[int], None],
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self.settings = acq.RecordingSettings.FromString(settings.SerializeToString())
        self.layout = camera.CameraImageLayout.FromString(layout.SerializeToString())
        self.identity = identity
        self.paths = paths
        self.queue = queue
        self.pixel_pool = pixel_pool
        self.pixel_preparer = pixel_preparer
        self.capabilities = capabilities
        self.launcher = launcher
        self.video_sync_factory = video_sync_factory
        self.frame_log_sync = frame_log_sync
        self.role = role
        self.nominal_frame_rate_hz = nominal_frame_rate_hz
        self.nominal_rate_source = nominal_rate_source
        self.warning_occurrence = warning_occurrence
        self.started_observed = started_observed
        self.clock_ns = clock_ns
        self._prepared = False
        self._scheduled: acq.WorkerSchedule | None = None
        self._released = False
        self._started = False
        self._started_observation_ns: int | None = None
        self._release_deadline_ns: int | None = None
        self._active_io_deadline_ns: int | None = None
        self._finished = False
        self._encoder: EncoderProcess | None = None
        self._encoding: ResolvedEncoding | None = None
        self._video_path: Path | None = None
        self._frame_log_path: Path | None = None
        self._video_identity: object | None = None
        self._video_sync: VideoSync | None = None
        self._frame_log: FrameLogWriter | None = None
        self._watchdog: EncoderProgressWatchdog | None = None
        self._received = 0
        self._submitted = 0
        self._logged = 0
        self._last_frame_id = -1
        self._diagnostics = RecordingDiagnostics(warning_occurrence)
        self._error: str | None = None
        self._last_video_sync_ns = 0
        self._prepared_buffer: bytearray | None = None
        self._input_pixel_format = ""
        self._finish_arguments: tuple[object, ...] | None = None
        self._original_finish_deadline_ns: int | None = None
        self._finish_results: list[control.OutputResult] | None = None
        self._finalization = FinalizationProgress()

    def prepare(self) -> None:
        if self._prepared:
            raise RecordingFailure("recording thread already prepared")
        self._encoding, self._prepared_buffer, self._input_pixel_format = (
            prepare_recording(
                self.settings,
                self.layout,
                self.identity,
                self.paths,
                self.queue,
                self.pixel_preparer,
                self.capabilities,
                role=self.role,
            )
        )
        self._prepared = True

    def schedule(self, schedule: acq.WorkerSchedule, *, deadline_ns: int) -> None:
        if not self._prepared or self._scheduled is not None or self._encoding is None:
            raise RecordingFailure(
                "ScheduleTrial requires one fresh prepared recording"
            )
        if not schedule.HasField("start_monotonic_ns") or not schedule.HasField(
            "end_monotonic_ns"
        ):
            raise RecordingFailure("schedule lacks trial interval")
        self._scheduled = acq.WorkerSchedule.FromString(
            schedule.SerializeToString(deterministic=True)
        )
        self._video_path, self._frame_log_path = resolve_recording_paths(
            self.paths, self.role, self.identity, schedule
        )
        (
            self._video_path,
            self._frame_log_path,
            self._encoder,
            self._watchdog,
        ) = launch_scheduled_encoder(
            self.settings,
            self.layout,
            self.identity,
            self.paths,
            schedule,
            self.queue,
            self.launcher,
            self._encoding,
            role=self.role,
            nominal_frame_rate_hz=self.nominal_frame_rate_hz,
            fragment_target_ns=int(self.settings.fragment_target_ns),
            clock_ns=self.clock_ns,
            deadline_ns=deadline_ns,
        )
        # Creation proof is established later by the encoder's exclusive -n output open.

    def release(self, release: acq.WorkerRelease, *, deadline_ns: int) -> None:
        if self._scheduled is None or self._encoder is None or self._released:
            raise RecordingFailure("ReleaseTrial has no unique retained schedule")
        if self.clock_ns() >= deadline_ns:
            raise RecordingFailure("ReleaseTrial missed its original cutoff")
        command = self._scheduled.command
        if (
            release.schedule_operation.command_id != command.command_id
            or not release.HasField("command")
            or not release.command.HasField("target")
            or release.command.target.SerializeToString(deterministic=True)
            != command.target.SerializeToString(deterministic=True)
            or not release.HasField("start_monotonic_ns")
            or not release.HasField("end_monotonic_ns")
            or release.start_monotonic_ns != self._scheduled.start_monotonic_ns
            or release.end_monotonic_ns != self._scheduled.end_monotonic_ns
        ):
            raise RecordingFailure(
                "ReleaseTrial does not match exact retained schedule"
            )
        self._released = True
        self._release_deadline_ns = deadline_ns

    @property
    def started_observation_ns(self) -> int | None:
        """First real in-trial record accounting; launch/header creation is insufficient."""
        return self._started_observation_ns

    def process_available(self, *, timeout: float = 0.0, max_entries: int = 64) -> int:
        """Process ordered queue entries; no capture or control thread performs I/O."""
        if not self._released or self._encoder is None:
            return 0
        if max_entries <= 0:
            raise ValueError("recording processing quantum must be positive")
        processed = 0
        first = True
        while processed < max_entries:
            entry = self.queue.dequeue(timeout if first else 0.0)
            first = False
            if entry is None:
                break
            try:
                self._process_entry(entry)
            except BaseException as exc:
                self._error = f"{type(exc).__name__}: {exc}"
                # A failed frame remains failed accounting, but its in-flight
                # payload slot must be returned so bounded cleanup can proceed.
                recycled = self.queue.complete(entry.record)
                if recycled is not None:
                    self.pixel_pool.release(recycled)
                raise RecordingFailure(self._error) from exc
            recycled = self.queue.complete(entry.record)
            if recycled is not None:
                self.pixel_pool.release(recycled)
            processed += 1
            self._sync_due()
            self._check_progress()
        self._sync_due()
        self._check_progress()
        return processed

    def run(
        self,
        end_marker: EndMarkerSource,
        pulse_evidence: Callable[[], PulseEvidence],
        completion_context: Callable[[], RecordingCompletionContext],
        *,
        deadline_ns: int,
    ) -> list[control.OutputResult]:
        """Drain until the capture-owned terminal marker, then close exact outputs."""
        if not self._released:
            raise RecordingFailure("recording driver requires a matched ReleaseTrial")
        while True:
            abort = end_marker.abort_request()
            if abort is not None:
                kind, abort_deadline_ns = abort
                if kind == "cancel_before_start":
                    return self.cancel_before_start(deadline_ns=abort_deadline_ns)
                if kind == "failed_cleanup":
                    return self.fail_cleanup(deadline_ns=abort_deadline_ns)
            completion_deadline = end_marker.completion_deadline_ns
            self._active_io_deadline_ns = completion_deadline or int(deadline_ns)
            if self._frame_log is None:
                self._observe_video_identity()
            if (
                self._frame_log is None
                and self._scheduled is not None
                and self.clock_ns() >= self._scheduled.start_monotonic_ns
            ):
                self._create_trial_outputs()
            self.process_available(timeout=0.05, max_entries=32)
            end = end_marker.poll()
            if (
                completion_deadline is not None
                and self.clock_ns() >= completion_deadline
            ):
                return self.fail_cleanup(deadline_ns=completion_deadline)
            if end is None and self.clock_ns() >= deadline_ns:
                return self.fail_cleanup(deadline_ns=deadline_ns)
            if (
                end is not None
                and self.queue.pending_records == 0
                and self.queue.waiting_pixels == 0
            ):
                return self.finish(
                    end,
                    pulse_evidence(),
                    completion_context(),
                    deadline_ns=completion_deadline or deadline_ns,
                )

    def finish(
        self,
        end: CaptureEndMarker,
        pulses: PulseEvidence,
        completion: RecordingCompletionContext,
        *,
        deadline_ns: int,
    ) -> list[control.OutputResult]:
        if self._finished:
            if self._finish_results is not None:
                return list(self._finish_results)
            raise RecordingFailure("recording is already finished without results")
        if self._error is not None:
            raise RecordingFailure(
                "recording cannot retry terminal input after a prior failure"
            )
        if self._encoder is None or self._frame_log is None:
            raise RecordingFailure("recording is incomplete")
        arguments = (end, pulses, completion)
        if self._finish_arguments is None:
            self._finish_arguments = arguments
            self._original_finish_deadline_ns = deadline_ns
            self._active_io_deadline_ns = deadline_ns
        elif self._finish_arguments != arguments:
            raise RecordingFailure(
                "recording finish retry differs from its retained terminal evidence"
            )
        assert self._scheduled is not None
        if self.queue.pending_records or self.queue.waiting_pixels:
            raise RecordingFailure(
                "cannot append completion while records remain queued"
            )
        original_deadline = self._original_finish_deadline_ns
        assert original_deadline is not None
        assert self._scheduled is not None
        assert self._video_path is not None and self._frame_log_path is not None
        stop_matches, timing_valid, accounting_complete = terminal_capture_proof(
            end,
            completion,
            schedule=self._scheduled,
            received=self._received,
            logged=self._logged,
            last_frame_id=self._last_frame_id,
        )
        cutoff_ns = (
            end.recording_end_monotonic_ns
            if stop_matches and timing_valid and accounting_complete
            else None
        )

        def trailing_slot_submitted() -> None:
            self._submitted += 1
            if self._watchdog is not None:
                self._watchdog.note_input_submitted()
            self._check_progress()
            self._sync_due()
            self._observe_video_identity()

        if (
            cutoff_ns is not None
            and self._frame_log.last_video_source is not None
            and self._prepared_buffer is not None
            and self._encoder is not None
        ):
            if self._watchdog is None:
                raise RecordingFailure(
                    "recording encoder progress watchdog is unavailable"
                )
            final_slots = self._frame_log.video_grid.slots_before(cutoff_ns)
            with self._watchdog.active_input_work():
                try:
                    write_trailing_slots(
                        final_slots,
                        frame_log=self._frame_log,
                        encoder=self._encoder,
                        prepared_buffer=self._prepared_buffer,
                        write_deadline=self._write_deadline,
                        on_slot_submitted=trailing_slot_submitted,
                    )
                except SubmittedFrameLogFailure as exc:
                    self._error = f"{type(exc).__name__}: {exc}"
                    raise
        self._finish_results, self._video_sync = finish_recording(
            end,
            pulses,
            completion,
            schedule=self._scheduled,
            received=self._received,
            submitted=self._submitted,
            logged=self._logged,
            last_frame_id=self._last_frame_id,
            diagnostics=self._diagnostics,
            encoder=self._encoder,
            frame_log=self._frame_log,
            video_sync=self._video_sync,
            finalization=self._finalization,
            video_path=self._video_path,
            frame_log_path=self._frame_log_path,
            video_identity=self._video_identity,
            observe_video=self._observe_video_identity,
            stat_identity=self._stat_identity,
            clock_ns=self.clock_ns,
            original_deadline_ns=original_deadline,
            cleanup_deadline_ns=deadline_ns,
        )
        self._finished = True
        return list(self._finish_results)

    def fail_cleanup(self, *, deadline_ns: int) -> list[control.OutputResult]:
        """Close owned resources after frame processing fails, without normal evidence."""
        if self._finished:
            return list(self._finish_results or ())
        self.launcher.terminate_unconfirmed(deadline_ns=deadline_ns)
        if self._scheduled is None:
            if self._encoder is not None or self._frame_log is not None:
                raise RecordingFailure("unscheduled recording retains output resources")
            self._finish_results = []
            self._finished = True
            return []
        if self._video_path is None or self._frame_log_path is None:
            raise RecordingFailure("failed cleanup lacks resolved scheduled paths")
        if self._encoder is None:
            if self._frame_log is not None or self._video_sync is not None:
                raise RecordingFailure("failed schedule retains unowned output handles")
            results = _unlaunched_outputs(
                self._scheduled,
                self._video_path,
                self._frame_log_path,
                stat_identity=self._stat_identity,
            )
            self._finish_results = results
            self._finished = True
            return list(results)
        results, self._video_sync = close_failed_recording(
            self._scheduled,
            self._video_path,
            self._frame_log_path,
            queue=self.queue,
            pool=self.pixel_pool,
            encoder=self._encoder,
            frame_log=self._frame_log,
            video_sync=self._video_sync,
            finalization=self._finalization,
            submitted=self._submitted,
            observe_video=self._observe_video_identity,
            stat_identity=self._stat_identity,
            clock_ns=self.clock_ns,
            deadline_ns=deadline_ns,
        )
        self._finish_results = results
        self._finished = True
        return list(results)

    def cancel_before_start(self, *, deadline_ns: int) -> list[control.OutputResult]:
        """Stop a scheduled encoder and remove only its proven, created MP4."""
        if self._finished:
            raise RecordingFailure("pre-T cancellation is no longer allowed")
        self.launcher.terminate_unconfirmed(deadline_ns=deadline_ns)
        schedule = self._scheduled
        if (
            self._scheduled is not None
            and self.clock_ns() >= self._scheduled.start_monotonic_ns
        ):
            raise RecordingFailure(
                "pre-T cancellation cannot change a post-T recording"
            )
        results, self._video_sync = cancel_scheduled_before_start(
            schedule,
            self._video_path,
            self._frame_log_path,
            encoder=self._encoder,
            video_sync=self._video_sync,
            observe_video=self._observe_video_identity,
            stat_identity=self._stat_identity,
            delete_created_video=(
                lambda path, identity, limit: self.video_sync_factory.delete_exact(
                    path, identity, deadline_ns=limit
                )
            ),
            deadline_ns=deadline_ns,
        )
        self._finished = True
        return results

    def _process_entry(self, entry: QueueEntry) -> None:
        if self._frame_log is None or self._encoder is None:
            self._create_trial_outputs()
        assert self._frame_log is not None and self._encoder is not None
        if self._scheduled is None or self._prepared_buffer is None:
            raise RecordingFailure("recording was not scheduled or prepared")

        def start_accounting() -> None:
            if not self._started:
                self._started = True
                self._started_observation_ns = self.clock_ns()
                self.started_observed(self._started_observation_ns)

        def record_diagnostics(record: FrameRecord) -> None:
            for diagnostic in record.diagnostics:
                self._diagnostics.record_frame(record, diagnostic)

        def slot_submitted() -> None:
            self._submitted += 1
            if self._watchdog is not None:
                self._watchdog.note_input_submitted()
            self._check_progress()
            self._sync_due()
            self._observe_video_identity()

        frame_id = entry.record.frame_id
        write_ordered_entry(
            entry,
            expected_frame_id=self._last_frame_id + 1,
            schedule=self._scheduled,
            frame_log=self._frame_log,
            encoder=self._encoder,
            pixel_preparer=self.pixel_preparer,
            prepared_buffer=self._prepared_buffer,
            target_bits=int(self.settings.recording_bit_depth),
            on_started=start_accounting,
            write_deadline=self._write_deadline,
            record_diagnostic=record_diagnostics,
            on_video_slot_submitted=slot_submitted,
        )
        self._last_frame_id = frame_id
        self._received += 1
        self._logged += 1
        self._observe_video_identity()

    def _create_trial_outputs(self) -> None:
        assert self._scheduled is not None and self._video_path is not None
        assert self._frame_log_path is not None
        if self.clock_ns() < self._scheduled.start_monotonic_ns:
            raise RecordingFailure(
                "frame arrived before T; recording admission is invalid"
            )
        self._observe_video_identity()
        frame_log = FrameLogWriter(
            self._frame_log_path,
            self.identity,
            start_ns=self._scheduled.start_monotonic_ns,
            nominal_frame_rate_hz=self.nominal_frame_rate_hz,
            nominal_rate_source=self.nominal_rate_source,
            sync_interval_ns=int(self.settings.frame_log_sync_interval_ns),
            syncer=self.frame_log_sync,
        )
        # Keep ownership before any file creation or header append can fail.
        self._frame_log = frame_log
        frame_log.create()

    def _observe_video_identity(self) -> VideoSync | None:
        observation = observe_video_identity(
            self._encoder,
            self._video_path,
            self._video_identity,
            self._video_sync,
            self._last_video_sync_ns,
            factory=self.video_sync_factory,
            clock_ns=self.clock_ns,
        )
        self._video_identity = observation.identity
        self._video_sync = observation.sync
        self._last_video_sync_ns = observation.last_sync_ns
        return self._video_sync

    def _sync_due(self) -> None:
        self._last_video_sync_ns = sync_due(
            self._frame_log,
            self._video_sync,
            self._last_video_sync_ns,
            int(self.settings.video_sync_interval_ns),
            self.clock_ns(),
        )

    def _check_progress(self) -> None:
        if self._watchdog is None:
            return
        self._watchdog.check()

    def _write_deadline(self) -> int:
        """Bound a blocking stdin write by original finalization and stall budgets."""
        if self._scheduled is None:
            raise RecordingFailure("recording has no retained schedule")
        return write_deadline(
            self._watchdog,
            self._active_io_deadline_ns,
            int(self._scheduled.end_monotonic_ns),
        )

    def _stat_identity(self, path: Path) -> object | None:
        return stat_identity(path, self.video_sync_factory)
