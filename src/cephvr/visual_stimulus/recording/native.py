"""Concrete Schedule-scoped Visual Stimulus recording owner for one renderer worker."""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Any
from uuid import uuid4

from cephvr.control.v1 import services_pb2_grpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows.encoder_process import WindowsEncoderProcess
from cephvr.platform.windows.file_sync import (
    WindowsFileSyncOwner,
    WindowsFrameLogSync,
    WindowsVideoSyncFactory,
)
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.platform.windows.nvenc_capabilities import NvencProbeOwner
from cephvr.shared.auth import Principal
from cephvr.shared.supervised_encoder import SupervisedEncoderLauncher
from cephvr.visual_stimulus.config.models.artifact_models import (
    PreparedTrial,
    ReviewEncoding,
)
from cephvr.visual_stimulus.config.models.evidence_model import (
    ArtifactRef,
    Completion,
    EncoderOutcome,
    EvidenceRecord,
    FeedbackEvidence,
    Header,
)
from cephvr.visual_stimulus.identity import FFMPEG_PROBE_ROLE, FFMPEG_ROLES
from cephvr.visual_stimulus.rendering.types import (
    DiagnosticSnapshot,
    RenderPort,
    RenderUpdate,
    ResourceReleaseReport,
)
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

from .capture import RecordingCounts, RecordingWorker
from .capture_runtime import RecordingCaptureRuntime
from .encoder_owner import EncoderTrialOwner
from .encoding_probe import resolve_review_encoding
from .evidence import EvidenceWriter
from .evidence_records import CaptureDisposition
from .outcomes import (
    closed_results,
    failed_results,
    not_started_results,
    uncertain_pre_header_results,
)
from .recipe import PreparedRecipe, prepare_recipe
from .session import RecordingSession, WindowsEncoderInputAdapter


class NativeRecording:
    """One in-process recorder and one supervisor-registered FFmpeg child per trial.

    The GL owner calls ``before_render`` and ``rendered``. Readback is admitted before
    capture and never waits on the encoder. A dedicated RecordingSession thread owns
    evidence I/O, FFmpeg stdin, and final closure.
    """

    def __init__(
        self,
        *,
        ffmpeg_executable: Path | None,
        supervisor: services_pb2_grpc.SupervisorServiceStub,
        owner: Principal,
        owner_identity: pb.ProcessIdentity,
        windows_jobs: WindowsJobs,
        file_sync_owner: WindowsFileSyncOwner,
        renderer: RenderPort,
        video_sync_factory: WindowsVideoSyncFactory,
        nvenc_owner: NvencProbeOwner | None = None,
        review_input_pixel_format: str | None = None,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        if ffmpeg_executable is not None and not ffmpeg_executable.is_absolute():
            raise ValueError("FFmpeg executable must be an absolute prepared path")
        self.ffmpeg_executable = ffmpeg_executable
        self.nvenc_owner = nvenc_owner
        self.review_input_pixel_format = review_input_pixel_format
        self.launcher = SupervisedEncoderLauncher(
            supervisor=supervisor,
            owner=owner,
            owner_identity=owner_identity,
            windows_jobs=windows_jobs,
            file_sync_owner=file_sync_owner,
            process_factory=WindowsEncoderProcess,
            allowed_roles=FFMPEG_ROLES,
            probe_roles=frozenset({FFMPEG_PROBE_ROLE}),
            clock_ns=clock_ns,
        )
        self.renderer = renderer
        self.clock_ns = clock_ns
        self.encoder_owner = EncoderTrialOwner(
            self.launcher, video_sync_factory, clock_ns=clock_ns
        )
        self.saving = False
        self.capture_slots = 0
        self.evidence_pending_bytes = 0
        self.fragment_target_ns = 0
        self.record_sync_interval_ns = 0
        self.video_sync_interval_ns = 0
        self.encoder_stall_timeout_ns = 0
        self.record_stall_timeout_ns = 0
        self._artifact: PreparedTrial | None = None
        self._recipes: dict[str, PreparedRecipe] = {}
        self._configured_max_recipe_bytes = 0
        self._schedule: visual_stimulus.WorkerSchedule | None = None
        self._video_path: Path | None = None
        self._evidence_path: Path | None = None
        self._recipe_path: Path | None = None
        self._session: RecordingSession | None = None
        self._worker: RecordingWorker | None = None
        self._capture_runtime: RecordingCaptureRuntime | None = None
        self._cutoff_ns: int | None = None
        self._finish_deadline_ns: int | None = None
        self._cancelled = False
        self._output_results: tuple[pb.OutputResult, ...] | None = None
        self._encoder_exit: int | None = None
        self._video_sync_ok = False
        self._artifact_present: bool | None = None
        self._writer_generation = str(uuid4())
        self._announce: Callable[[str, str | None], None] | None = None
        self._setup_deadline_ns = 0
        self._setup_work: pb.WorkContext | None = None
        self._setup_parent_operation: pb.OperationContext | None = None
        self._announced_keys: set[str] = set()
        self._probe_aggregate_key: str | None = None
        self._probe_released: set[str] = set()
        self._probe_failed = False
        self._resolved_review_encoding: ReviewEncoding | None = None
        self._header_published = False
        self._released_keys: set[str] = set()
        self._owner_key: str | None = None
        self._capture_key: str | None = None
        self._child_key: str | None = None

    def configure(
        self,
        request: visual_stimulus.WorkerSetup,
        announce: Callable[[str, str | None], None],
        deadline_ns: int,
    ) -> None:
        if self._schedule is not None:
            if self._output_results is None:
                raise RuntimeError(
                    "recording resources remain from the preceding session"
                )
            self._reset_trial_state()
        self._recipes.clear()
        self._resolved_review_encoding = None
        self._announced_keys.clear()
        self._probe_aggregate_key = None
        self._probe_released.clear()
        self._probe_failed = False
        self._released_keys.clear()
        self._owner_key = self._capture_key = self._child_key = None
        self.saving = bool(request.settings.save_visual_stimulus_data)
        self._announce = announce
        self._setup_deadline_ns = deadline_ns
        self._setup_work = request.command.target.work
        self._setup_parent_operation = request.command.parent_operation
        limits, policy = request.policies.limits, request.policies
        if self.saving:
            if self.ffmpeg_executable is None:
                raise FileNotFoundError(
                    "Save Visual Stimulus data is On but FFmpeg was not resolved"
                )
            if self.nvenc_owner is None:
                raise ValueError("saving requires an NVENC capability owner")
            if not limits.HasField("capture_slots") or not limits.HasField(
                "evidence_pending_bytes"
            ):
                raise ValueError(
                    "Visual Stimulus recording capacities must be explicitly prepared"
                )
            if (
                not limits.HasField("max_prepared_plan_bytes")
                or limits.max_prepared_plan_bytes == 0
            ):
                raise ValueError(
                    "Visual Stimulus prepared recipe byte limit must be explicitly set"
                )
            if not all(
                policy.HasField(name)
                for name in (
                    "record_sync_interval_ns",
                    "video_sync_interval_ns",
                    "fragment_target_ns",
                    "encoder_stall_timeout_ns",
                    "record_stall_timeout_ns",
                )
            ):
                raise ValueError(
                    "Visual Stimulus recording timing policy is incomplete"
                )
            if deadline_ns <= self.clock_ns():
                raise TimeoutError("Visual Stimulus recording Setup deadline expired")
            self.capture_slots = limits.capture_slots
            self.evidence_pending_bytes = limits.evidence_pending_bytes
            self.fragment_target_ns = policy.fragment_target_ns
            self.record_sync_interval_ns = policy.record_sync_interval_ns
            self.video_sync_interval_ns = policy.video_sync_interval_ns
            self.encoder_stall_timeout_ns = policy.encoder_stall_timeout_ns
            self.record_stall_timeout_ns = policy.record_stall_timeout_ns
            self._configured_max_recipe_bytes = limits.max_prepared_plan_bytes
            self._owner_key = f"recording-owner:{self._writer_generation}"
            self._capture_key = f"recording-capture-slots:{self._writer_generation}"
            self._register_resource(self._owner_key, announce)
            self._register_resource(self._capture_key, announce)

    def review_encoding_provider(
        self,
        display: Any,
        ffmpeg_args: tuple[str, ...],
        limits: Any,
        announce: Callable[[str, str | None], None],
    ) -> ReviewEncoding:
        """Probe installed FFmpeg/NVENC evidence, then freeze the E13 plan at Setup."""
        if not self.saving:
            raise RuntimeError(
                "review encoder provider was called with Save Visual Stimulus data Off"
            )
        if self._resolved_review_encoding is not None:
            return self._resolved_review_encoding
        del limits
        if (
            self.ffmpeg_executable is None
            or self._setup_work is None
            or self._setup_parent_operation is None
        ):
            raise RuntimeError(
                "review encoder probe lacks Setup identity or FFmpeg path"
            )
        if self.nvenc_owner is None:
            raise RuntimeError("NVENC capability owner is not initialized")

        def register(key: str) -> None:
            self._register_resource(key, announce)
            self._probe_aggregate_key = key

        def report(key: str, success: bool) -> None:
            if success:
                self._probe_released.add(key)
            else:
                self._probe_failed = True

        encoding, _key = resolve_review_encoding(
            executable=self.ffmpeg_executable,
            display=display,
            ffmpeg_args=ffmpeg_args,
            launcher=self.launcher,
            nvenc_owner=self.nvenc_owner,
            work=self._setup_work,
            parent_operation=self._setup_parent_operation,
            deadline_ns=self._setup_deadline_ns,
            register_resource=register,
            report_probe_resource=report,
            input_pixel_format=self.review_input_pixel_format,
        )
        if self._probe_failed:
            raise RuntimeError("FFmpeg capability helper cleanup was not confirmed")
        self._resolved_review_encoding = encoding
        return encoding

    def prepare_artifacts(
        self, artifacts: tuple[PreparedTrial, ...], deadline_ns: int
    ) -> Future[None] | None:
        if not self.saving:
            return None
        future: Future[None] = Future()

        def prepare() -> None:
            try:
                recipes: dict[str, PreparedRecipe] = {}
                for artifact in artifacts:
                    if self.clock_ns() >= deadline_ns:
                        raise TimeoutError(
                            "Visual Stimulus recipe preparation missed Setup deadline"
                        )
                    recipes[artifact.identity.trial_id] = prepare_recipe(
                        artifact, max_bytes=self._configured_max_recipe_bytes
                    )
                self._recipes = recipes
                future.set_result(None)
            except BaseException as exc:
                future.set_exception(exc)

        threading.Thread(
            target=prepare, name="visual-stimulus-recipe-prepare", daemon=True
        ).start()
        return future

    def schedule(
        self, request: visual_stimulus.WorkerSchedule, artifact: PreparedTrial
    ) -> Future[None] | None:
        if not self.saving:
            return None
        if self._schedule is not None:
            if self._output_results is None:
                raise RuntimeError("preceding recording has not reached output closure")
            self._reset_trial_state()
        if artifact.identity.trial_id not in self._recipes:
            raise RuntimeError("Setup did not precompute this trial's recipe bytes")
        encoding = artifact.review_encoding
        if encoding is None:
            raise ValueError("saving requires Setup-prepared ReviewEncoding")
        plans = {item.output_tag: item for item in request.outputs}
        required = {
            "stimulus_LOG": "json",
            "stimulus_frames": "jsonl",
            "stimulus": "mp4",
        }
        if {tag: item.extension for tag, item in plans.items()} != required:
            raise ValueError(
                "Schedule must reserve exact recipe/evidence/review-video outputs"
            )
        for item in plans.values():
            if not item.HasField("path") or not Path(item.path).is_absolute():
                raise ValueError(
                    "Schedule output path must be an assigned absolute path"
                )
        self._artifact, self._schedule = artifact, request
        self._recipe_path = Path(plans["stimulus_LOG"].path)
        self._evidence_path = Path(plans["stimulus_frames"].path)
        self._video_path = Path(plans["stimulus"].path)
        if not request.command.HasField(
            "target"
        ) or not request.command.target.HasField("work"):
            raise ValueError("Schedule lacks exact renderer work identity")
        self.launcher.bind_operation(
            request.command.target.work,
            request.command.parent_operation,
        )
        if self._announce is None:
            raise RuntimeError("Schedule has no cleanup catalogue registrar")
        self._child_key = f"ffmpeg-child:{artifact.identity.trial_id}:{uuid4()}"
        self._register_resource(self._child_key, self._announce)
        from .encoding import build_review_argv

        if self.ffmpeg_executable is None:
            raise RuntimeError("review FFmpeg executable disappeared after Setup")
        argv = build_review_argv(
            self.ffmpeg_executable,
            encoding,
            self._video_path,
            fragment_target_ns=self.fragment_target_ns,
        )
        launch_future: Future[None] = Future()
        evidence = EvidenceWriter(
            max_pending_bytes=self.evidence_pending_bytes,
            sync_file=(
                WindowsFrameLogSync().sync
                if sys.platform == "win32"
                else lambda stream: os.fsync(stream.fileno())
            ),
        )
        adapter = WindowsEncoderInputAdapter(
            None,
            write_deadline_ns=lambda: self._io_deadline(self.encoder_stall_timeout_ns),
            close_deadline_ns=lambda: self._io_deadline(self.encoder_stall_timeout_ns),
        )
        self._worker = RecordingWorker(
            capture_slots=self.capture_slots, evidence=evidence, encoder=adapter
        )
        self._session = RecordingSession(
            worker=self._worker,
            evidence=evidence,
            evidence_path=self._evidence_path,
            recipe_path=self._recipe_path,
            max_queued_evidence_bytes=self.evidence_pending_bytes,
            finalizer=self._finalize,
            startup=lambda: self._launch_child(argv, request, adapter, launch_future),
            sync_interval_ns=self.record_sync_interval_ns,
            periodic_sync=self._periodic_video_sync,
            failure_cleanup=self._failure_cleanup,
            clock_ns=self.clock_ns,
        )
        self._capture_runtime = RecordingCaptureRuntime(
            self.renderer,
            self._session,
            encoding,
            evidence_pending_bytes=self.evidence_pending_bytes,
            capture_slots=self.capture_slots,
        )
        self._worker.on_submitted = lambda frame: self._enqueue_capture_update(
            frame.group_id,
            "input_submitted",
            frame.video_frame_index,
            None,
            terminal=True,
        )
        return launch_future

    def _io_deadline(self, timeout_ns: int) -> int:
        deadline = self.clock_ns() + timeout_ns
        if self._finish_deadline_ns is not None:
            deadline = min(deadline, self._finish_deadline_ns)
        return deadline

    def _reset_trial_state(self) -> None:
        if self._output_results is not None and self._child_key is not None:
            self._released_keys.add(self._child_key)
        self._artifact = None
        self._schedule = None
        self._video_path = self._evidence_path = self._recipe_path = None
        self.encoder_owner.reset()
        self._child_key = None
        self._session = None
        self._worker = None
        self._capture_runtime = None
        self._cutoff_ns = self._finish_deadline_ns = None
        self._cancelled = False
        self._output_results = None
        self._encoder_exit = None
        self._video_sync_ok = False
        self._artifact_present = None
        self._writer_generation = str(uuid4())
        self._header_published = False

    def _register_resource(
        self, key: str, announce: Callable[[str, str | None], None]
    ) -> None:
        if key in self._announced_keys:
            return
        announce(key, None)
        self._announced_keys.add(key)

    def _launch_child(
        self,
        argv: list[str],
        request: visual_stimulus.WorkerSchedule,
        adapter: WindowsEncoderInputAdapter,
        future: Future[None],
    ) -> None:
        try:
            if self._video_path is None:
                raise RuntimeError("scheduled review-video output path is unavailable")
            self.encoder_owner.start(argv, request, self._video_path, adapter)
            future.set_result(None)
        except BaseException as exc:
            future.set_exception(exc)
            raise

    def publication(self, report: visual_stimulus.WorkerRecipePublication) -> None:
        if not self.saving:
            return
        if self._session is None or self._artifact is None or self._schedule is None:
            raise RuntimeError("recipe publication arrived before scheduled recorder")
        if not report.published or report.prepared != self._schedule.prepared:
            raise ValueError(
                "recipe publication did not confirm this prepared generation"
            )
        if Path(report.path) != self._recipe_path:
            raise ValueError(
                "recipe publication path differs from reserved Schedule path"
            )
        artifact = self._artifact
        schedule = self._schedule
        recipe = self._recipes[artifact.identity.trial_id]
        if recipe.sha256 != report.prepared.plan_sha256:
            raise ValueError(
                "published recipe digest differs from the retained Setup bytes"
            )

        def build_header() -> tuple[Header, ArtifactRef]:
            receipt = ArtifactRef(
                relative_path=Path(report.path).name,
                sha256=recipe.sha256,
                byte_length=recipe.byte_length,
                schema_id="cephvr.visual_stimulus.prepared_trial.v2",
            )
            header = Header(
                kind="header",
                format_version=1,
                identity=artifact.identity,
                writer_generation=self._writer_generation,
                recipe=receipt,
                trial_start_host_ns=schedule.start_monotonic_ns,
                required_output_ids=tuple(
                    item.output_id for item in artifact.display.active_outputs
                ),
                renderer_compatibility=artifact.renderer_compatibility,
            )
            return header, receipt

        self._session.publish_header_factory(build_header)
        self._header_published = True

    def before_render(self) -> None:
        if not self.saving or self._capture_runtime is None:
            return
        self._capture_runtime.before_render()

    def rendered(self, update: RenderUpdate) -> None:
        if not self.saving or self._capture_runtime is None or self._artifact is None:
            return
        try:
            self._capture_runtime.rendered(update)
        finally:
            if update.feedback_evidence:
                self._capture_runtime.feedback_snapshots(update.feedback_evidence)

    def diagnostics(self, records: tuple[DiagnosticSnapshot, ...]) -> None:
        if not self.saving or self._capture_runtime is None:
            return
        self._capture_runtime.diagnostics(records)

    def feedback(self, records: tuple[FeedbackEvidence, ...]) -> None:
        if not self.saving or self._capture_runtime is None:
            return
        self._capture_runtime.feedback(records)

    def _enqueue_capture_update(
        self,
        group_id: int,
        disposition: CaptureDisposition,
        frame_index: int | None,
        failure: str | None,
        *,
        terminal: bool = False,
    ) -> None:
        if self._capture_runtime is None:
            return
        self._capture_runtime.enqueue_capture_update(
            group_id,
            disposition,
            frame_index,
            failure,
            terminal=terminal,
        )

    def begin_finish(self, cutoff_ns: int, deadline_ns: int) -> None:
        if not self.saving:
            self._output_results = ()
            return
        if self._session is None:
            raise RuntimeError("scheduled recording is missing")
        self._cutoff_ns, self._finish_deadline_ns = cutoff_ns, deadline_ns
        if self._capture_runtime is not None:
            self._capture_runtime.cancel_pending("capture_unresolved_at_cutoff")
            self._capture_runtime.close_feedback_intervals(cutoff_ns)
        self._session.begin_finish(cutoff_ns=cutoff_ns, deadline_ns=deadline_ns)

    def begin_cancel(self, deadline_ns: int) -> None:
        if not self.saving:
            self._output_results = ()
            return
        self._cancelled = True
        self._cutoff_ns, self._finish_deadline_ns = self.clock_ns(), deadline_ns
        if self._capture_runtime is not None:
            self._capture_runtime.close_feedback_intervals(self._cutoff_ns)
        if self._session is None:
            self._output_results = failed_results(
                self._schedule,
                "FFmpeg Schedule launch did not establish a recording session",
            )
            return
        if self._capture_runtime is not None:
            self._capture_runtime.cancel_pending("capture_cancelled")
        self._session.begin_cancel(deadline_ns=deadline_ns)

    def poll_finished(self) -> tuple[pb.OutputResult, ...] | None:
        if self._output_results is not None:
            return self._output_results
        if not self.saving:
            return ()
        if self._session is None:
            return None
        try:
            result = self._session.poll_finished()
        except Exception as exc:
            self._output_results = failed_results(self._schedule, str(exc))
            return self._output_results
        if result is None:
            return None
        if not self._header_published:
            self._output_results = self._pre_header_results()
            return self._output_results
        assert self._schedule is not None and self._worker is not None
        self._output_results = closed_results(
            self._schedule,
            self._worker.counts(),
            evidence_closed=result.evidence_closed,
            cutoff_known=self._cutoff_ns is not None,
            encoder_cleanup_confirmed=self.encoder_owner.cleanup_complete,
            encoder_exit=self._encoder_exit,
            video_sync_closed=self._video_sync_ok,
            artifact_present=self._artifact_present,
            artifact_created_by_session=(
                self.encoder_owner.process.output_creation_identity is not None
                if self.encoder_owner.process is not None
                else None
            ),
        )
        return self._output_results

    def review_summary(self) -> vp.ReviewRecordingSummary | None:
        """Return compact counts after Save-On output closure for FinishedReport."""
        if not self.saving or self._artifact is None or self._worker is None:
            return None
        counts = self._worker.counts()
        return vp.ReviewRecordingSummary(
            trial_id=self._artifact.identity.trial_id,
            render_groups=(
                self._capture_runtime.state_count
                if self._capture_runtime is not None
                else 0
            ),
            recording_capacity_drops=counts.capacity_drop_count,
        )

    def _pre_header_results(self) -> tuple[pb.OutputResult, ...]:
        """Classify Schedule cancellation before released T without inventing files."""
        if (
            self._schedule is None
            or self._video_path is None
            or self._evidence_path is None
        ):
            return ()
        process_closed = self.encoder_owner.cleanup_complete
        absent = not self._video_path.exists() and not self._evidence_path.exists()
        if process_closed and absent:
            return not_started_results(self._schedule)
        return uncertain_pre_header_results(
            self._schedule, self._video_path, self._evidence_path
        )

    def cleanup(self, deadline_ns: int) -> ResourceReleaseReport:
        """Return exact local resource release evidence without blocking the GL owner."""

        if self._capture_runtime is not None and self._capture_runtime.pending:
            self._capture_runtime.cancel_pending("capture_cleanup")
        if self._session is not None and self._output_results is None:
            self.begin_cancel(deadline_ns)
            try:
                result = self._session.poll_finished()
            except RuntimeError:
                result = None
            if result is not None:
                self._output_results = failed_results(
                    self._schedule, "recording was interrupted during cleanup"
                )
        released_set: set[str] = set()
        outstanding: set[str] = set()
        session_pending = self._session is not None and self._output_results is None
        child_closed = (
            self.encoder_owner.cleanup_complete
            if self.encoder_owner.process is not None
            else not self.encoder_owner.launch_attempted
            or self.encoder_owner.cleanup_confirmed
        )
        capture_pending = (
            self._capture_runtime is not None and self._capture_runtime.pending
        )
        for key, closed in (
            (
                self._probe_aggregate_key,
                self._probe_aggregate_key in self._probe_released,
            ),
            (self._child_key, child_closed),
            (self._owner_key, not session_pending),
            (self._capture_key, not (capture_pending or session_pending)),
        ):
            if key is not None:
                (released_set if closed else outstanding).add(key)
        outstanding.intersection_update(self._announced_keys)
        released_set.intersection_update(self._announced_keys)
        self._released_keys.update(released_set)
        if not outstanding:
            self._reset_trial_state()
            self._recipes.clear()
            self._resolved_review_encoding = None
        return ResourceReleaseReport(
            released=tuple(sorted(self._released_keys)),
            outstanding=tuple(sorted(outstanding)),
        )

    def _finalize(self, counts: RecordingCounts) -> tuple[bytes, bytes]:
        schedule = self._schedule
        if schedule is None or self._video_path is None:
            raise RuntimeError("recording process ownership is absent")
        deadline = self._finish_deadline_ns or schedule.command.deadline_monotonic_ns
        result = self.encoder_owner.finalize(self._video_path, deadline)
        self._encoder_exit = result.exit_code
        self._video_sync_ok = result.file_sync_and_close_confirmed
        self._artifact_present = result.artifact_present
        encoder = EncoderOutcome(
            kind="encoder_outcome",
            admitted_count=counts.admitted_count,
            input_submitted_count=counts.input_submitted_count,
            capacity_drop_count=counts.capacity_drop_count,
            final_input_group_id=counts.final_input_group_id,
            cutoff_host_ns=self._cutoff_ns,
            exit_code=self._encoder_exit,
            eof_sent=True,
            drain_confirmed=self._encoder_exit == 0,
        )
        completion = Completion(
            kind="completion",
            cutoff_host_ns=self._cutoff_ns or self.clock_ns(),
            last_group_id=(
                self._capture_runtime.last_group_id
                if self._capture_runtime is not None
                else None
            ),
            state_count=(
                self._capture_runtime.state_count
                if self._capture_runtime is not None
                else 0
            ),
            submission_attempt_count=(
                self._capture_runtime.submission_count
                if self._capture_runtime is not None
                else 0
            ),
            capture_admission_count=counts.admitted_count,
            capture_drop_count=counts.capacity_drop_count,
            unresolved_attempt_count=0,
            outcome="interrupted" if self._cancelled else "completed",
        )
        return EvidenceWriter._encode(
            EvidenceRecord(payload=encoder)
        ), EvidenceWriter._encode(EvidenceRecord(payload=completion))

    def _periodic_video_sync(self) -> None:
        if self._video_path is None:
            return
        self.encoder_owner.periodic_sync(
            self._video_path, interval_ns=self.video_sync_interval_ns
        )

    def _failure_cleanup(self) -> None:
        deadline = self._finish_deadline_ns
        if deadline is None and self._schedule is not None:
            deadline = self._schedule.command.deadline_monotonic_ns
        if deadline is not None:
            self.encoder_owner.cleanup(deadline)
