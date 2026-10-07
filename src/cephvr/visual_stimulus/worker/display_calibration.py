"""Sessionless V01 renderer calibration operation on the existing GL owner."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.identity import require_uuid4
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.resources.display_calibration import (
    PreparedDisplayCalibration,
)
from cephvr.visual_stimulus.v1 import messages_pb2 as messages
from cephvr.visual_stimulus.v1 import runtime_pb2 as view
from cephvr.visual_stimulus.worker.ports import EnginePort, PreparationPort, ReportPort


@dataclass(slots=True)
class _OpenJob:
    request: messages.OpenDisplayCalibrationCommand
    deadline_ns: int
    result: Future[PreparedDisplayCalibration]
    completion: Future[None]
    thread: threading.Thread
    timed_out: bool = False
    failure_reported: bool = False
    cleanup_command: messages.WorkerCommand | None = None
    cleanup_deadline_ns: int | None = None
    close_completion: Future[None] | None = None


class DisplayCalibrationOwner:
    """Own immutable diagnostic input and truthful Active/Idle evidence."""

    def __init__(
        self,
        *,
        worker: pb.ProcessIdentity,
        controller: pb.ProcessIdentity,
        backend: pb.BackendContext,
        engine: EnginePort,
        preparation: PreparationPort,
        reports: ReportPort,
        display_profile: Callable[[], DisplayProfile | None],
        set_display_profile: Callable[[DisplayProfile | None], None],
        clock: Callable[[], int],
    ) -> None:
        self.worker = worker
        self.controller = controller
        self.backend = backend
        self.engine = engine
        self.preparation = preparation
        self.reports = reports
        self.display_profile = display_profile
        self.set_display_profile = set_display_profile
        self.clock = clock
        self.job: _OpenJob | None = None
        self.active_id = ""
        self.active_profile: DisplayProfile | None = None
        self.profile_sha256 = ""
        self.arena_sha256 = ""
        self.prepared: PreparedDisplayCalibration | None = None
        self.revision = 0
        self.evidence = view.DisplayCalibrationEvidence(
            state=view.DISPLAY_CALIBRATION_STATE_IDLE,
            idle=True,
            resources_closed=True,
        )

    def open(
        self, request: messages.OpenDisplayCalibrationCommand, deadline_ns: int
    ) -> Future[None]:
        require_uuid4(request.diagnostic_id)
        if self.job is not None:
            raise RuntimeError("display calibration preparation is already pending")
        if self.evidence.state != view.DISPLAY_CALIBRATION_STATE_IDLE:
            raise RuntimeError("previous display calibration is not confirmed Idle")
        if (
            hashlib.sha256(request.profile_json.encode("utf-8")).hexdigest()
            != request.profile_sha256
        ):
            raise ValueError("canonical display profile digest mismatch")
        from cephvr.visual_stimulus.config.models.display_profile import (
            parse_display_json,
        )

        profile = parse_display_json(request.profile_json, max_bytes=16_777_216)
        if not request.HasField("policies") or not request.policies.HasField("limits"):
            raise ValueError("calibration resource limits are unavailable")
        result: Future[PreparedDisplayCalibration] = Future()
        completion: Future[None] = Future()

        def prepare() -> None:
            try:
                operation = getattr(
                    self.preparation, "prepare_display_calibration", None
                )
                if operation is None:
                    raise RuntimeError(
                        "protected calibration arena preparation is unavailable"
                    )
                result.set_result(
                    operation(request, lambda _key, _path: None, deadline_ns)
                )
            except BaseException as exc:
                result.set_exception(exc)

        self.active_id = request.diagnostic_id
        self.active_profile = profile
        thread = threading.Thread(
            target=prepare, name="cephvr-display-calibration-prepare", daemon=True
        )
        self.job = _OpenJob(request, deadline_ns, result, completion, thread)
        self.evidence = view.DisplayCalibrationEvidence(
            diagnostic_id=request.diagnostic_id,
            controller_generation=self.controller.generation,
            renderer_generation=self.worker.generation,
            configuration_revision=request.command.target.configuration_revision,
            state=view.DISPLAY_CALIBRATION_STATE_PREPARING,
            observed_monotonic_ns=self.clock(),
            profile_sha256=request.profile_sha256,
            arena_sha256=request.arena_sha256,
        )
        thread.start()
        return completion

    def advance(self, now_ns: int) -> int | None:
        job = self.job
        if job is None:
            return None
        if job.cleanup_command is not None:
            if not job.result.done() or job.thread.is_alive():
                return now_ns + 1_000_000
            try:
                prepared = job.result.result()
            except BaseException as exc:
                self.evidence.state = view.DISPLAY_CALIBRATION_STATE_UNKNOWN
                self.evidence.idle = False
                self.evidence.resources_closed = False
                self.evidence.observed_monotonic_ns = self.clock()
                self.evidence.failure_code = "CALIBRATION_PREPARE_CLEANUP"
                self.evidence.failure_message = str(exc)[:1024]
                cleanup_deadline = job.cleanup_deadline_ns or job.deadline_ns
                closed = False
                if job.close_completion is not None:
                    closed = self._close_incomplete(
                        job.cleanup_command or job.request.command,
                        cleanup_deadline,
                    )
                else:
                    try:
                        self._report(job.cleanup_command, cleanup_deadline)
                    except Exception:
                        pass  # Evidence state below carries the outcome; report is best effort.
                if not job.completion.done():
                    job.completion.set_exception(exc)
                self.job = None
                if job.close_completion is not None and not job.close_completion.done():
                    if closed:
                        job.close_completion.set_result(None)
                    else:
                        job.close_completion.set_exception(
                            RuntimeError("pending calibration closure remains unknown")
                        )
                return None
            self.prepared = prepared
            self.active_profile = prepared.display
            closed = self._safe_release_sources(prepared)
            cleanup_deadline = job.cleanup_deadline_ns or job.deadline_ns
            within_deadline = self.clock() < cleanup_deadline
            if closed:
                self.set_display_profile(prepared.previous_display)
            self.evidence = view.DisplayCalibrationEvidence(
                diagnostic_id=self.active_id,
                controller_generation=self.controller.generation,
                renderer_generation=self.worker.generation,
                configuration_revision=job.request.command.target.configuration_revision,
                state=(
                    view.DISPLAY_CALIBRATION_STATE_IDLE
                    if closed and within_deadline
                    else view.DISPLAY_CALIBRATION_STATE_UNKNOWN
                ),
                observed_monotonic_ns=self.clock(),
                profile_sha256=job.request.profile_sha256,
                arena_sha256=job.request.arena_sha256,
                presented=False,
                idle=closed,
                resources_closed=closed,
            )
            if not closed:
                self.evidence.failure_code = "CALIBRATION_SOURCE_CLOSE"
                self.evidence.failure_message = (
                    "protected calibration sources remain owned"
                )
            elif not within_deadline:
                self.evidence.failure_code = "CALIBRATION_CLEANUP_DEADLINE"
                self.evidence.failure_message = (
                    "protected sources closed after the cleanup deadline"
                )
            self._report(job.cleanup_command, cleanup_deadline)
            if not job.completion.done():
                job.completion.set_exception(
                    InterruptedError("calibration Open was superseded by cleanup")
                )
            self.job = None
            if closed and within_deadline:
                self.active_id = ""
                self.active_profile = None
                self.prepared = None
            if job.close_completion is not None and not job.close_completion.done():
                if closed and within_deadline:
                    job.close_completion.set_result(None)
                else:
                    job.close_completion.set_exception(
                        RuntimeError("pending calibration closure remains unknown")
                    )
            return None
        if now_ns >= job.deadline_ns:
            job.timed_out = True
            self._mark_unknown(
                job, TimeoutError("display calibration missed its original deadline")
            )
            if not job.result.done() or job.thread.is_alive():
                return now_ns + 10_000_000
            try:
                late_prepared = job.result.result()
            except BaseException:
                self.job = None
                return None
            self.prepared = late_prepared
            self.active_profile = late_prepared.display
            self._safe_release_sources(late_prepared)
            self.job = None
            return None
        try:
            if not job.result.done() or job.thread.is_alive():
                return now_ns + 1_000_000
            prepared = job.result.result()
            self.prepared = prepared
            display = prepared.display
            present = getattr(self.engine, "present_display_calibration", None)
            if present is None:
                raise RuntimeError(
                    "renderer has no sessionless calibration presentation path"
                )
            activities = tuple(present(display, prepared))
            expected = {item.output_id for item in display.active_outputs}
            observed = {item.output_id for item in activities}
            if (
                observed != expected
                or len(activities) != len(expected)
                or any(
                    item.error or item.swap_return_ns < item.swap_entry_ns
                    for item in activities
                )
                or self.clock() >= job.deadline_ns
            ):
                raise RuntimeError(
                    "calibration scene lacks actual presentation evidence for every output"
                )
            self.set_display_profile(display)
            self.profile_sha256 = job.request.profile_sha256
            self.arena_sha256 = job.request.arena_sha256
            self.revision = job.request.command.target.configuration_revision
            self.evidence = view.DisplayCalibrationEvidence(
                diagnostic_id=self.active_id,
                controller_generation=self.controller.generation,
                renderer_generation=self.worker.generation,
                configuration_revision=self.revision,
                state=view.DISPLAY_CALIBRATION_STATE_ACTIVE,
                observed_monotonic_ns=self.clock(),
                profile_sha256=self.profile_sha256,
                arena_sha256=self.arena_sha256,
                presented=True,
                idle=False,
                resources_closed=False,
            )
            self._report(job.request.command, job.deadline_ns)
            job.completion.set_result(None)
            self.job = None
        except BaseException as exc:
            self._mark_unknown(job, exc)
            self.job = None
        return None

    def request_cleanup(
        self, command: messages.WorkerCommand, deadline_ns: int
    ) -> None:
        job = self.job
        if job is None:
            return
        if job.cleanup_command is None:
            job.cleanup_command = messages.WorkerCommand.FromString(
                command.SerializeToString()
            )
            job.cleanup_deadline_ns = deadline_ns
        else:
            job.cleanup_deadline_ns = min(
                job.cleanup_deadline_ns or deadline_ns, deadline_ns
            )

    def close_for_cleanup(
        self, command: messages.WorkerCommand, deadline_ns: int
    ) -> None:
        if self.job is not None:
            raise RuntimeError("calibration preparation is still in flight")
        if self.evidence.state == view.DISPLAY_CALIBRATION_STATE_IDLE:
            return
        if not self.active_id:
            raise RuntimeError("calibration resource closure remains unknown")
        if self.prepared is None:
            if not self._close_incomplete(command, deadline_ns):
                raise RuntimeError("incomplete calibration inputs remain owned")
            return
        self.close(
            messages.CloseDisplayCalibrationCommand(
                command=command, diagnostic_id=self.active_id
            ),
            deadline_ns,
        )

    def close(
        self, request: messages.CloseDisplayCalibrationCommand, deadline_ns: int
    ) -> Future[None] | None:
        require_uuid4(request.diagnostic_id)
        if request.diagnostic_id != self.active_id:
            raise RuntimeError("exact active calibration identity is unavailable")
        if self.job is not None:
            if self.job.close_completion is None:
                self.job.close_completion = Future()
            self.request_cleanup(request.command, deadline_ns)
            return self.job.close_completion
        if self.prepared is None:
            self.close_for_cleanup(request.command, deadline_ns)
            return None
        if self.clock() >= deadline_ns:
            raise TimeoutError("display calibration close missed its original deadline")
        display = self.active_profile
        if display is None:
            raise RuntimeError("active calibration profile is unavailable")
        prepared = self.prepared
        if prepared is None:
            raise RuntimeError("protected calibration preparation is unresolved")
        close = getattr(self.engine, "close_display_calibration", None)
        if close is None:
            raise RuntimeError("renderer has no calibration closure path")
        activities, released = close(display, prepared)
        expected = {item.output_id for item in display.active_outputs}
        if (
            {item.output_id for item in activities} != expected
            or any(
                item.error or item.swap_return_ns < item.swap_entry_ns
                for item in activities
            )
            or not released
            or self.clock() >= deadline_ns
        ):
            self.evidence.state = view.DISPLAY_CALIBRATION_STATE_UNKNOWN
            self.evidence.idle = False
            self.evidence.resources_closed = False
            self.evidence.observed_monotonic_ns = self.clock()
            self.evidence.failure_code = "CALIBRATION_CLOSE"
            self.evidence.failure_message = (
                "Idle or protected renderer resources remain unconfirmed"
            )
            self._report(request.command, deadline_ns)
            raise RuntimeError(self.evidence.failure_message)
        sources_closed = self._safe_release_sources(prepared)
        if not sources_closed or self.clock() >= deadline_ns:
            self.evidence.state = view.DISPLAY_CALIBRATION_STATE_UNKNOWN
            self.evidence.idle = True
            self.evidence.resources_closed = False
            self.evidence.observed_monotonic_ns = self.clock()
            self.evidence.failure_code = "CALIBRATION_SOURCE_CLOSE"
            self.evidence.failure_message = "protected calibration sources remain owned"
            self._report(request.command, deadline_ns)
            raise RuntimeError(self.evidence.failure_message)
        self.evidence.state = view.DISPLAY_CALIBRATION_STATE_IDLE
        self.evidence.observed_monotonic_ns = self.clock()
        self.evidence.idle = True
        self.evidence.resources_closed = True
        self.evidence.presented = False
        self.evidence.ClearField("failure_code")
        self.evidence.ClearField("failure_message")
        self.set_display_profile(prepared.previous_display)
        self._report(request.command, deadline_ns, display=display)
        self.active_id = ""
        self.active_profile = None
        self.prepared = None
        return None

    def _close_incomplete(
        self,
        command: messages.WorkerCommand,
        deadline_ns: int,
        *,
        report: bool = True,
    ) -> bool:
        retry = getattr(self.preparation, "retry_incomplete_display_calibration", None)
        closed = retry is not None and bool(retry(deadline_ns))
        closed = closed and self.clock() < deadline_ns
        display = self.active_profile
        if display is None:
            return False
        if closed:
            self.evidence.state = view.DISPLAY_CALIBRATION_STATE_IDLE
            self.evidence.observed_monotonic_ns = self.clock()
            self.evidence.presented = False
            self.evidence.idle = True
            self.evidence.resources_closed = True
            self.evidence.ClearField("failure_code")
            self.evidence.ClearField("failure_message")
            if report:
                self._report(command, deadline_ns, display=display)
            self.active_id = ""
            self.active_profile = None
            return True
        self.evidence.state = view.DISPLAY_CALIBRATION_STATE_UNKNOWN
        self.evidence.observed_monotonic_ns = self.clock()
        self.evidence.idle = False
        self.evidence.resources_closed = False
        self.evidence.failure_code = "CALIBRATION_SOURCE_CLOSE"
        self.evidence.failure_message = "protected calibration sources remain owned"
        if report:
            try:
                self._report(command, deadline_ns, display=display)
            except Exception:
                pass  # Failure is already in the evidence record; the report is best effort.
        return False

    def _report(
        self,
        command: messages.WorkerCommand,
        deadline_ns: int,
        *,
        display: DisplayProfile | None = None,
    ) -> None:
        profile = display or self.active_profile or self.display_profile()
        if profile is None:
            raise RuntimeError("display profile unavailable for calibration evidence")
        report = pb.VisualStimulusDisplayView(
            source=self.worker,
            backend=self.backend,
            controller=self.controller,
            command_id=command.command_id,
            requested_revision=command.target.configuration_revision,
            applied_revision=command.target.configuration_revision,
            observed_monotonic_ns=self.clock(),
            complete=True,
        )
        report.outputs.extend(
            view.OutputInitialization(output_id=item.output_id)
            for item in profile.active_outputs
        )
        report.calibration.CopyFrom(self.evidence)
        self.reports.send("ReportDisplay", report, deadline_ns)

    def _mark_unknown(self, job: _OpenJob, error: BaseException) -> None:
        self.evidence.state = view.DISPLAY_CALIBRATION_STATE_UNKNOWN
        self.evidence.observed_monotonic_ns = self.clock()
        self.evidence.failure_code = "CALIBRATION_OPEN"
        self.evidence.failure_message = str(error)[:1024]
        if not job.completion.done():
            job.completion.set_exception(error)
        if not job.failure_reported:
            try:
                self._report(job.request.command, job.deadline_ns)
            except Exception:
                pass  # The open failure is retained in the evidence record.
            job.failure_reported = True

    def _safe_release_sources(self, prepared: object) -> bool:
        release_sources = getattr(self.preparation, "release_display_calibration", None)
        if release_sources is None:
            return False
        try:
            return bool(release_sources(prepared))
        except Exception:
            return False
