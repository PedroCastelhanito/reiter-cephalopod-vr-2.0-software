"""Own asynchronous display preparation and GL-thread Idle confirmation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from typing import Protocol

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.configuration import resolve_pacing_profile
from cephvr.visual_stimulus.rendering.native_display import DisplayUnavailableError
from cephvr.visual_stimulus.rendering.types import DisplayInitialization
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp
from cephvr.visual_stimulus.worker.display_initialization import (
    DisplayPreparationJob,
    begin_display_preparation,
    complete_display_preparation,
)
from cephvr.visual_stimulus.worker.ports import EnginePort, PreparationPort, ReportPort


class DisplayCleanup(Protocol):
    def __call__(
        self, command: visual_stimulus.WorkerCommand, *, deadline_ns: int
    ) -> pb.CleanupReport: ...


class DisplayOwner:
    """Keep display readiness and resource operations outside trial lifecycle state."""

    def __init__(
        self,
        *,
        worker: pb.ProcessIdentity,
        controller: pb.ProcessIdentity,
        backend: pb.BackendContext,
        engine: EnginePort,
        preparation: PreparationPort,
        reports: ReportPort,
        announce: Callable[
            [visual_stimulus.WorkerCommand | None, int, str, str | None], None
        ],
        release_resource: Callable[[str], None],
        cleanup: DisplayCleanup,
        cancelled: Callable[[], bool],
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.worker = worker
        self.controller = controller
        self.backend = backend
        self.engine = engine
        self.preparation = preparation
        self.reports = reports
        self.announce = announce
        self.release_resource = release_resource
        self.cleanup = cleanup
        self.cancelled = cancelled
        self.clock = clock
        self.job: DisplayPreparationJob | None = None
        self.ready = False
        self.profile: DisplayProfile | None = None

    def initialize(
        self, request: visual_stimulus.InitializeDisplay, deadline_ns: int
    ) -> Future[None]:
        if self.job is not None or self.ready:
            raise RuntimeError("display initialization is already pending or complete")
        display = resolve_pacing_profile(
            request.display.profile_json,
            max_bytes=request.limits.max_document_bytes,
            refresh_hz=(
                request.pacing_refresh_hz
                if request.HasField("pacing_refresh_hz")
                else None
            ),
            output_id=(
                request.pacing_output_id
                if request.HasField("pacing_output_id")
                else None
            ),
        )
        request.display.profile_json = display.model_dump_json()
        self.profile = display
        for output in display.active_outputs:
            self.announce(
                request.command,
                deadline_ns,
                "display:" + output.output_id,
                None,
            )
        job = begin_display_preparation(
            request,
            display,
            self.preparation,
            lambda key, path: self.announce(request.command, deadline_ns, key, path),
            deadline_ns,
        )
        self.job = job
        return job.completion

    def advance(self, now_ns: int) -> tuple[bool, int | None]:
        """Service windows and finish only on the GL owner; return next due time."""
        windows_active = self.engine.service_display()
        job = self.job
        if job is None:
            return windows_active, None
        try:
            done = complete_display_preparation(
                job,
                self.preparation,
                now_ns=now_ns,
                report=lambda display, observed: self._report_idle(
                    job.request, display, observed, job.deadline_ns
                ),
            )
            if not done:
                return windows_active, now_ns + 1_000_000
            self.release_resource(job.resource_key)
            self.job = None
        except BaseException as exc:
            if job.thread is None or not job.thread.is_alive():
                self.release_resource(job.resource_key)
            self.job = None
            if isinstance(exc, DisplayUnavailableError):
                try:
                    self._reject_unavailable(job, exc)
                except BaseException as failure:
                    job.completion.set_exception(failure)
                    raise
            else:
                job.completion.set_exception(exc)
                raise
        return windows_active, None

    def _reject_unavailable(
        self, job: DisplayPreparationJob, error: DisplayUnavailableError
    ) -> None:
        # Only verified sessionless cleanup makes this a configuration rejection.
        self.ready = False
        if self.cancelled():
            raise InterruptedError("display initialization was cancelled")
        if self.clock() >= job.deadline_ns:
            raise TimeoutError("display rejection missed its retained deadline")
        released = self.cleanup(job.request.command, deadline_ns=job.deadline_ns)
        # Retain discharged obligations until Setup promotes them or shutdown
        # retires them: native owners can repeat their exact release receipts.
        if self.clock() >= job.deadline_ns:
            raise TimeoutError("display cleanup missed its retained deadline")
        if self.cancelled():
            raise InterruptedError(
                "display initialization was cancelled during cleanup"
            )
        view = pb.VisualStimulusDisplayView(
            source=self.worker,
            backend=self.backend,
            controller=self.controller,
            command_id=job.request.command.command_id,
            requested_revision=job.request.command.target.configuration_revision,
            observed_monotonic_ns=self.clock(),
            complete=True,
            resources=released.resources,
        )
        view.issues.add(
            component="visual_stimulus",
            field_path="backends.visual_stimulus.display.profile_json",
            failure=pb.Failure(
                code=error.code,
                message=f"{error}. {error.remedy}",
            ),
        )
        # The coordinator must retain exact rejection/closure before operation failure.
        self.reports.confirm("ReportDisplay", view, job.deadline_ns)
        self.profile = None
        job.completion.set_exception(error)

    def invalidate_for_setup(self) -> None:
        self.ready = False

    def mark_ready(self) -> None:
        self.ready = True

    def cleanup_confirmed_or_unknown(self) -> None:
        # Cleanup begins by revoking readiness; resource reports decide confirmation.
        self.ready = False

    def _report_idle(
        self,
        request: visual_stimulus.InitializeDisplay,
        display: DisplayProfile,
        observed: DisplayInitialization,
        deadline_ns: int,
    ) -> None:
        activities = {item.output_id: item for item in observed.idle_activity}
        bits = {item[0]: item[1:] for item in observed.observed_rgb_bits}
        intervals = dict(observed.requested_swap_intervals)
        if set(activities) != {
            item.output_id for item in display.active_outputs
        } or any(
            item.error or item.swap_return_ns < item.swap_entry_ns
            for item in activities.values()
        ):
            raise RuntimeError("Idle submission missing for required display output")
        view = pb.VisualStimulusDisplayView(
            source=self.worker,
            backend=self.backend,
            controller=self.controller,
            command_id=request.command.command_id,
            requested_revision=request.command.target.configuration_revision,
            applied_revision=request.command.target.configuration_revision,
            observed_monotonic_ns=self.clock(),
            complete=True,
        )
        for output in display.active_outputs:
            activity = activities[output.output_id]
            view.outputs.add(
                output_id=output.output_id,
                resources_ready=True,
                requested_rgb_bits=output.rgb_bits_per_channel,
                observed_rgb_bits=bits[output.output_id],
                requested_swap_interval=intervals[output.output_id],
                idle_swap_entry_ns=activity.swap_entry_ns,
                idle_swap_return_ns=activity.swap_return_ns,
                idle_submission=vp.SUBMISSION_OUTCOME_RETURNED,
            )
        self.ready = True
        self.reports.send("ReportDisplay", view, deadline_ns)
