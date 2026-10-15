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
        # Profile of the last confirmed-closed diagnostic, for repeated Close evidence.
        self.closed_profile: DisplayProfile | None = None
        self.profile_sha256 = ""
        self.arena_sha256 = ""
        self.prepared: PreparedDisplayCalibration | None = None
        # True while a prepared input exists that was never presented (late Open).
        self.unpresented = False
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
        self.evidence = self._build_evidence(
            request, view.DISPLAY_CALIBRATION_STATE_PREPARING
        )
        thread.start()
        return completion

    def advance(self, now_ns: int) -> int | None:
        job = self.job
        if job is None:
            self._advance_pulse()
            return None
        if job.cleanup_command is not None:
            if not job.result.done() or job.thread.is_alive():
                return now_ns + 1_000_000
            try:
                prepared = job.result.result()
            except BaseException as exc:
                self._mark(
                    view.DISPLAY_CALIBRATION_STATE_UNKNOWN,
                    idle=False,
                    closed=False,
                    code="CALIBRATION_PREPARE_CLEANUP",
                    message=str(exc),
                )
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
            self.evidence = self._build_evidence(
                job.request,
                view.DISPLAY_CALIBRATION_STATE_IDLE
                if closed and within_deadline
                else view.DISPLAY_CALIBRATION_STATE_UNKNOWN,
                calibration_view=self.active_profile.calibration_view
                if self.active_profile is not None
                else "",
                idle=closed,
                closed=closed,
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
                self._release_identity()
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
            # The late preparation was never presented, so the renderer is unchanged.
            self.prepared = late_prepared
            self.active_profile = late_prepared.display
            self.unpresented = True
            self.job = None
            self._close_unpresented(job.request.command, job.deadline_ns)
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
            self.evidence = self._build_evidence(
                job.request,
                view.DISPLAY_CALIBRATION_STATE_ACTIVE,
                calibration_view=display.calibration_view,
                presented=True,
            )
            self._report(job.request.command, job.deadline_ns)
            job.completion.set_result(None)
            self.job = None
        except BaseException as exc:
            self._mark_unknown(job, exc)
            self.job = None
        return None

    def _advance_pulse(self) -> None:
        display = self.active_profile
        if (
            self.evidence.state != view.DISPLAY_CALIBRATION_STATE_ACTIVE
            or display is None
            or display.calibration_view != "photodiode_placement"
            or self.prepared is None
        ):
            return
        try:
            activities = self.engine.present_display_calibration(display, self.prepared)
            expected = {item.output_id for item in display.active_outputs}
            if (
                {item.output_id for item in activities} != expected
                or len(activities) != len(expected)
                or any(
                    item.error or item.swap_return_ns < item.swap_entry_ns
                    for item in activities
                )
            ):
                raise RuntimeError("photodiode preview presentation failed")
        except BaseException as exc:
            self._mark(
                view.DISPLAY_CALIBRATION_STATE_UNKNOWN,
                idle=False,
                closed=False,
                presented=False,
                code="CALIBRATION_PULSE",
                message=str(exc),
            )
            raise

    def update(
        self, request: messages.UpdateDisplayCalibrationCommand, deadline_ns: int
    ) -> None:
        from cephvr.visual_stimulus.config.calibration_adjustments import (
            CalibrationAdjustmentRejected,
        )
        from cephvr.visual_stimulus.worker.calibration_adjustments import (
            update_presentation,
        )

        if self.job is not None or self.active_id != request.diagnostic_id:
            raise CalibrationAdjustmentRejected(
                "Live update targets an inactive or stale calibration"
            )
        update_presentation(
            request,
            deadline_ns,
            prepared=self.prepared,
            display=self.active_profile,
            evidence=self.evidence,
            engine=self.engine,
            clock=self.clock,
            report=self._report,
        )

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
        if (
            request.diagnostic_id != self.active_id
            and request.diagnostic_id == self.evidence.diagnostic_id
            and self.evidence.state == view.DISPLAY_CALIBRATION_STATE_IDLE
            and self.evidence.resources_closed
        ):
            # Closure already confirmed (e.g. a late Open was closed); repeat the evidence.
            self._report(request.command, deadline_ns, display=self.closed_profile)
            return None
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
        if self.unpresented:
            if not self._close_unpresented(request.command, deadline_ns):
                raise RuntimeError(self.evidence.failure_message)
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
            self._mark(
                view.DISPLAY_CALIBRATION_STATE_UNKNOWN,
                idle=False,
                closed=False,
                code="CALIBRATION_CLOSE",
                message="Idle or protected renderer resources remain unconfirmed",
            )
            self._report(request.command, deadline_ns)
            raise RuntimeError(self.evidence.failure_message)
        sources_closed = self._safe_release_sources(prepared)
        if not sources_closed or self.clock() >= deadline_ns:
            self._mark(
                view.DISPLAY_CALIBRATION_STATE_UNKNOWN,
                idle=True,
                closed=False,
                code="CALIBRATION_SOURCE_CLOSE",
                message="protected calibration sources remain owned",
            )
            self._report(request.command, deadline_ns)
            raise RuntimeError(self.evidence.failure_message)
        self._mark(
            view.DISPLAY_CALIBRATION_STATE_IDLE, idle=True, closed=True, presented=False
        )
        self.set_display_profile(prepared.previous_display)
        self._report(request.command, deadline_ns, display=display)
        self._release_identity()
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
            self._mark(
                view.DISPLAY_CALIBRATION_STATE_IDLE,
                idle=True,
                closed=True,
                presented=False,
            )
            if report:
                self._report(command, deadline_ns, display=display)
            self._release_identity()
            return True
        self._mark(
            view.DISPLAY_CALIBRATION_STATE_UNKNOWN,
            idle=False,
            closed=False,
            code="CALIBRATION_SOURCE_CLOSE",
            message="protected calibration sources remain owned",
        )
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

    def _build_evidence(
        self,
        request: messages.OpenDisplayCalibrationCommand,
        state: view.DisplayCalibrationState,
        *,
        calibration_view: str = "",
        presented: bool = False,
        idle: bool = False,
        closed: bool = False,
    ) -> view.DisplayCalibrationEvidence:
        """Fresh evidence for one Open request, stamped with the current identities."""
        return view.DisplayCalibrationEvidence(
            diagnostic_id=self.active_id,
            calibration_view=calibration_view,
            controller_generation=self.controller.generation,
            renderer_generation=self.worker.generation,
            configuration_revision=request.command.target.configuration_revision,
            state=state,
            observed_monotonic_ns=self.clock(),
            profile_sha256=request.profile_sha256,
            arena_sha256=request.arena_sha256,
            presented=presented,
            idle=idle,
            resources_closed=closed,
        )

    def _mark(
        self,
        state: view.DisplayCalibrationState,
        *,
        idle: bool | None = None,
        closed: bool | None = None,
        presented: bool | None = None,
        code: str = "",
        message: str = "",
    ) -> None:
        """Update the retained evidence; no code clears any previous failure."""
        evidence = self.evidence
        evidence.state = state
        evidence.observed_monotonic_ns = self.clock()
        if idle is not None:
            evidence.idle = idle
        if closed is not None:
            evidence.resources_closed = closed
        if presented is not None:
            evidence.presented = presented
        if code:
            evidence.failure_code = code
            evidence.failure_message = message[:1024]
        else:
            evidence.ClearField("failure_code")
            evidence.ClearField("failure_message")

    def _release_identity(self) -> None:
        """Forget the exact diagnostic after its closure is confirmed."""
        self.closed_profile = self.active_profile
        self.active_id = ""
        self.active_profile = None
        self.prepared = None
        self.unpresented = False

    def _close_unpresented(
        self, command: messages.WorkerCommand, deadline_ns: int
    ) -> bool:
        """Release a preparation that never reached the renderer, then confirm Idle."""
        prepared = self.prepared
        closed = prepared is not None and self._safe_release_sources(prepared)
        if closed:
            self._mark(
                view.DISPLAY_CALIBRATION_STATE_IDLE,
                idle=True,
                closed=True,
                presented=False,
            )
        else:
            self._mark(
                view.DISPLAY_CALIBRATION_STATE_UNKNOWN,
                idle=True,
                closed=False,
                code="CALIBRATION_SOURCE_CLOSE",
                message="protected calibration sources remain owned",
            )
        try:
            self._report(command, deadline_ns)
        except Exception:
            pass  # The evidence record carries the outcome; the report is best effort.
        if closed:
            self._release_identity()
        return closed

    def _mark_unknown(self, job: _OpenJob, error: BaseException) -> None:
        self._mark(
            view.DISPLAY_CALIBRATION_STATE_UNKNOWN,
            code="CALIBRATION_OPEN",
            message=str(error),
        )
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
