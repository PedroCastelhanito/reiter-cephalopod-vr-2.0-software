"""Registered native media/helper launch with exact Windows process/pipe ownership."""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.byte_stream import (
    InheritedEndpoint,
    OverlappedPipe,
    PipeConstructionOwner,
)
from cephvr.platform.windows.encoder_process import (
    WindowsEncoderProcess,
    _remaining,
    _wait_process,
)
from cephvr.platform.windows.file_sync import WindowsFileSyncOwner
from cephvr.platform.windows.jobs import SuspendedProcess, WindowsJobs
from cephvr.shared.auth import Principal
from cephvr.shared.encoder_errors import EncoderLaunchError
from cephvr.shared.transport_deadlines import deadline_metadata

FFMPEG_ROLE = "acquisition_ffmpeg"
FFMPEG_PROBE_ROLE = "acquisition_ffmpeg_probe"


ProcessFactory = Callable[..., WindowsEncoderProcess]


@dataclass
class _LaunchAttempt:
    launch_id: str
    request: wire.PlanLaunchRequest
    metadata: tuple[tuple[str, str], ...]
    endpoints: list[InheritedEndpoint] = field(default_factory=list)
    pipe_owner: PipeConstructionOwner = field(default_factory=PipeConstructionOwner)
    process: SuspendedProcess | None = None
    job_name: str | None = None
    plan_requested: bool = False
    no_child_confirmed: bool = False
    process_exit_observed: bool = False
    job_empty_observed: bool = False
    process_released: bool = False
    job_released: bool = False


class SupervisedEncoderLauncher:
    """Launch adapter bound to one accepted operation and its optional work context."""

    def __init__(
        self,
        *,
        supervisor: services_pb2_grpc.SupervisorServiceStub,
        owner: Principal,
        owner_identity: types.ProcessIdentity,
        windows_jobs: WindowsJobs,
        file_sync_owner: WindowsFileSyncOwner,
        process_factory: ProcessFactory = WindowsEncoderProcess,
        allowed_roles: frozenset[str] = frozenset((FFMPEG_ROLE, FFMPEG_PROBE_ROLE)),
        probe_roles: frozenset[str] = frozenset((FFMPEG_PROBE_ROLE,)),
        diagnostic_tail_max_lines: int = 100,
        diagnostic_tail_max_bytes: int = 64 * 1024,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        registered_plan: Callable[[wire.PlanLaunchRequest], None] | None = None,
        stop_method: str = "owner_stdin_eof",
    ) -> None:
        if (
            owner.role != owner_identity.role
            or owner.generation != owner_identity.generation
        ):
            raise ValueError(
                "supervised FFmpeg owner credentials differ from process identity"
            )
        if diagnostic_tail_max_lines <= 0 or diagnostic_tail_max_bytes <= 0:
            raise ValueError("encoder diagnostic tail limits must be positive")
        self.supervisor = supervisor
        self.owner = owner
        self.owner_identity = types.ProcessIdentity.FromString(
            owner_identity.SerializeToString()
        )
        self.windows_jobs = windows_jobs
        self.file_sync_owner = file_sync_owner
        self.process_factory = process_factory
        self.allowed_roles = allowed_roles
        self.probe_roles = probe_roles
        self.tail_lines = diagnostic_tail_max_lines
        self.tail_bytes = diagnostic_tail_max_bytes
        self.clock_ns = clock_ns
        self.registered_plan = registered_plan
        self.stop_method = stop_method
        self._work: types.WorkContext | None = None
        self._parent_operation: types.OperationContext | None = None
        self._partial: list[_LaunchAttempt] = []

    def bind_schedule(self, schedule: Any) -> None:
        if not schedule.command.HasField(
            "target"
        ) or not schedule.command.target.HasField("work"):
            raise EncoderLaunchError("ScheduleTrial lacks exact worker work context")
        self.bind_operation(
            schedule.command.target.work, schedule.command.parent_operation
        )

    @property
    def pending_plans(self) -> tuple[wire.PlanLaunchRequest, ...]:
        """Return exact partial launch identities without exposing credentials."""
        return tuple(
            wire.PlanLaunchRequest.FromString(item.request.SerializeToString())
            for item in self._partial
            if item.plan_requested
        )

    def bind_operation(
        self, work: types.WorkContext, parent_operation: types.OperationContext
    ) -> None:
        """Bind the owning operation and optional session/trial before contained launch."""
        self._work = types.WorkContext.FromString(work.SerializeToString())
        self._parent_operation = types.OperationContext.FromString(
            parent_operation.SerializeToString()
        )

    def launch(
        self,
        argv: Sequence[str],
        *,
        deadline_ns: int,
        role: str = FFMPEG_ROLE,
        output_path: Path | None = None,
        capture_stdout: bool = False,
        negotiation: object | None = None,
    ) -> WindowsEncoderProcess:
        if self._work is None or self._parent_operation is None:
            raise EncoderLaunchError(
                "FFmpeg launcher must bind exact ScheduleTrial context"
            )
        if not argv or not Path(argv[0]).is_absolute():
            raise EncoderLaunchError("FFmpeg launch requires an absolute executable")
        if self.clock_ns() >= deadline_ns:
            raise TimeoutError("FFmpeg schedule launch deadline already expired")
        launch_id = str(uuid4())
        if role not in self.allowed_roles:
            raise EncoderLaunchError("unsupported FFmpeg helper child role")
        is_probe = role in self.probe_roles
        if is_probe and output_path is not None:
            raise EncoderLaunchError("FFmpeg capability probe cannot own an output")
        if not is_probe and output_path is None:
            output_path = Path(argv[-1])
        output_absent_before_launch = False
        if not is_probe:
            if output_path is None or self.file_sync_owner.identity_for_path(
                output_path
            ):
                raise EncoderLaunchError(
                    "FFmpeg output path was not absent at exact launch admission"
                )
            output_absent_before_launch = True
        child = types.ProcessIdentity(role=role, generation=str(uuid4()))
        child_token = secrets.token_urlsafe(32)
        request = wire.PlanLaunchRequest(
            command_id=launch_id,
            owner=self.owner_identity,
            child=child,
            parent_operation=self._parent_operation,
            executable=argv[0],
            python_worker=False,
            stop_method=self.stop_method,
        )
        if self._work.WhichOneof("work") is not None:
            request.work.CopyFrom(self._work)
        metadata = (
            *self.owner.metadata(),
            deadline_metadata(deadline_ns),
            ("x-cephvr-child-token", child_token),
        )
        attempt = _LaunchAttempt(launch_id, request, metadata)
        # Publish local ownership before creating any OS resources or contacting
        # the supervisor. Partial stages remain visible to bounded cleanup.
        self._partial.append(attempt)
        try:
            input_pipe = OverlappedPipe.create_child_endpoint(
                parent_writable=True, owner=attempt.pipe_owner, deadline_ns=deadline_ns
            )
            attempt.endpoints.append(input_pipe)
            progress_pipe = OverlappedPipe.create_child_endpoint(
                parent_writable=False, owner=attempt.pipe_owner, deadline_ns=deadline_ns
            )
            attempt.endpoints.append(progress_pipe)
            stderr_pipe = OverlappedPipe.create_child_endpoint(
                parent_writable=False, owner=attempt.pipe_owner, deadline_ns=deadline_ns
            )
            attempt.endpoints.append(stderr_pipe)
        except BaseException:
            self._close_attempt_endpoints(attempt, deadline_ns=deadline_ns)
            if not attempt.endpoints and not attempt.pipe_owner.cleanup_blocked:
                self._partial.remove(attempt)
            raise
        endpoints = tuple(attempt.endpoints)
        attempt.plan_requested = True
        state = self._plan(request, metadata, deadline_ns)
        if state.phase != wire.LAUNCH_PHASE_PLANNED or not state.containment_job_name:
            raise EncoderLaunchError(
                "supervisor did not retain a fresh planned FFmpeg job"
            )
        if self.registered_plan is not None:
            self.registered_plan(
                wire.PlanLaunchRequest.FromString(request.SerializeToString())
            )
        job_name = state.containment_job_name
        attempt.job_name = job_name
        self.windows_jobs.open_launch_job(job_name)
        inherited = tuple(endpoint.child_handle for endpoint in endpoints)
        try:
            process = self.windows_jobs.launch_suspended(
                argv[0],
                list(argv[1:]),
                [job_name],
                inherited,
                stdin_handle=input_pipe.child_handle,
                stdout_handle=progress_pipe.child_handle,
                stderr_handle=stderr_pipe.child_handle,
            )
        except BaseException as exc:
            attempt.no_child_confirmed = self._confirm_no_child(
                request, launch_id, metadata, deadline_ns
            )
            if attempt.no_child_confirmed:
                self._cleanup_no_child_attempt(attempt, deadline_ns=deadline_ns)
            raise EncoderLaunchError(
                f"contained FFmpeg creation failed: {exc}"
            ) from exc
        attempt.process = process
        confirmed = self._confirm_phase(
            request, launch_id, process, deadline_ns, wire.LAUNCH_PHASE_OS_CONFIRMED
        )
        if not confirmed:
            # The exact child/job/pipe ownership remains retained for cleanup; no resume.
            raise EncoderLaunchError("supervisor OS confirmation is unconfirmed")
        if not self._confirm_phase(
            request, launch_id, process, deadline_ns, wire.LAUNCH_PHASE_OPERATIONAL
        ):
            raise EncoderLaunchError(
                "supervisor native-child operational confirmation is unconfirmed"
            )
        # Operational is the second registry identity observation, not a claim
        # that the suspended FFmpeg process has begun encoding.
        self.windows_jobs.resume(process)
        for endpoint in endpoints:
            endpoint.close_child_copy()
        worker = self.process_factory(
            supervisor=self.supervisor,
            owner=self.owner,
            owner_identity=self.owner_identity,
            windows_jobs=self.windows_jobs,
            launch_id=launch_id,
            child=process,
            job_name=job_name,
            input_pipe=input_pipe.parent,
            progress_pipe=progress_pipe.parent,
            stderr_pipe=stderr_pipe.parent,
            output_path=output_path,
            output_absent_before_launch=output_absent_before_launch,
            capture_stdout=capture_stdout,
            negotiation=negotiation,
            file_sync_owner=self.file_sync_owner,
            diagnostic_tail_max_lines=self.tail_lines,
            diagnostic_tail_max_bytes=self.tail_bytes,
            clock_ns=self.clock_ns,
        )
        worker.start_readers()
        self._partial.remove(attempt)
        return worker

    def terminate_unconfirmed(self, *, deadline_ns: int) -> None:
        """Retain blockers unless exact unconfirmed children are observed exited."""
        for attempt in tuple(self._partial):
            if attempt.process is not None:
                child = attempt.process
                if not attempt.process_exit_observed:
                    self.windows_jobs.terminate_exact(
                        child.pid, child.creation_time_100ns
                    )
                    _wait_process(child, deadline_ns, self.clock_ns)
                    attempt.process_exit_observed = True
                if attempt.job_name is not None:
                    if (
                        not attempt.job_empty_observed
                        and self.windows_jobs.inspect_launch_job(attempt.job_name)
                    ):
                        raise EncoderLaunchError(
                            "unconfirmed FFmpeg descendants remain in the exact job"
                        )
                    attempt.job_empty_observed = True
                self._close_attempt_endpoints(attempt, deadline_ns=deadline_ns)
                if attempt.endpoints or attempt.pipe_owner.cleanup_blocked:
                    raise EncoderLaunchError(
                        "FFmpeg pipe handle cleanup is unconfirmed"
                    )
                if not attempt.process_released:
                    self.windows_jobs.release_process(
                        child.pid, child.creation_time_100ns
                    )
                    attempt.process_released = True
                if attempt.job_name is not None and not attempt.job_released:
                    self.windows_jobs.close_launch_job(attempt.job_name)
                    attempt.job_released = True
                self._partial.remove(attempt)
                continue
            if attempt.plan_requested and not attempt.no_child_confirmed:
                state = self.supervisor.GetLaunchState(
                    wire.LaunchQuery(
                        requester=self.owner_identity,
                        launch_command_id=attempt.launch_id,
                    ),
                    metadata=(*self.owner.metadata(), deadline_metadata(deadline_ns)),
                    timeout=_remaining(self.clock_ns, deadline_ns),
                )
                if state.plan.SerializeToString(
                    deterministic=True
                ) != attempt.request.SerializeToString(deterministic=True):
                    raise EncoderLaunchError(
                        "retained launch record resolves to a different supervisor plan"
                    )
                attempt.job_name = state.containment_job_name or None
                attempt.no_child_confirmed = self._confirm_no_child(
                    attempt.request,
                    attempt.launch_id,
                    attempt.metadata,
                    deadline_ns,
                )
            if attempt.no_child_confirmed or not attempt.plan_requested:
                self._cleanup_no_child_attempt(attempt, deadline_ns=deadline_ns)

    def _cleanup_no_child_attempt(
        self, attempt: _LaunchAttempt, *, deadline_ns: int
    ) -> None:
        self._close_attempt_endpoints(attempt, deadline_ns=deadline_ns)
        if attempt.job_name is not None:
            self.windows_jobs.close_launch_job(attempt.job_name)
        if not attempt.endpoints and not attempt.pipe_owner.cleanup_blocked:
            self._partial.remove(attempt)

    @staticmethod
    def _close_attempt_endpoints(attempt: _LaunchAttempt, *, deadline_ns: int) -> None:
        try:
            attempt.pipe_owner.retry_cleanup(deadline_ns=deadline_ns)
        except BaseException:
            pass  # The owner retains blockers; the caller checks cleanup_blocked.
        remaining: list[InheritedEndpoint] = []
        for endpoint in attempt.endpoints:
            try:
                endpoint.close_child_copy()
                endpoint.close_parent()
            except BaseException:
                remaining.append(endpoint)
        attempt.endpoints[:] = remaining

    def _plan(
        self,
        request: wire.PlanLaunchRequest,
        metadata: tuple[tuple[str, str], ...],
        deadline_ns: int,
    ) -> wire.LaunchState:
        try:
            receipt = self.supervisor.PlanLaunch(
                request,
                metadata=metadata,
                timeout=_remaining(self.clock_ns, deadline_ns),
            )
            if receipt.admission.command_id != request.command_id:
                raise EncoderLaunchError(
                    "PlanLaunch receipt has a different command ID"
                )
            if receipt.admission.result == types.COMMAND_RESULT_ACCEPTED:
                return cast(wire.LaunchState, receipt.state)
            raise EncoderLaunchError(receipt.admission.failure.message)
        except EncoderLaunchError:
            raise
        except Exception as exc:
            # Query exactly this operation after transport uncertainty; never respawn.
            try:
                state = self.supervisor.GetLaunchState(
                    wire.LaunchQuery(
                        requester=self.owner_identity,
                        launch_command_id=request.command_id,
                    ),
                    metadata=(*self.owner.metadata(), deadline_metadata(deadline_ns)),
                    timeout=_remaining(self.clock_ns, deadline_ns),
                )
            except Exception as query_error:
                raise EncoderLaunchError(
                    f"PlanLaunch uncertain and exact state unavailable: {query_error}"
                ) from exc
            if state.plan.SerializeToString(
                deterministic=True
            ) != request.SerializeToString(deterministic=True):
                raise EncoderLaunchError(
                    "GetLaunchState returned a different launch plan"
                ) from exc
            return cast(wire.LaunchState, state)

    def _confirm_phase(
        self,
        request: wire.PlanLaunchRequest,
        launch_id: str,
        child: SuspendedProcess,
        deadline_ns: int,
        phase: int,
    ) -> bool:
        """Confirm the exact child at ``phase``; after an RPC failure query that state."""
        confirm = wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=launch_id,
            owner=self.owner_identity,
            child=request.child,
            pid=child.pid,
            creation_time_100ns=child.creation_time_100ns,
        )
        try:
            receipt = self.supervisor.ConfirmLaunch(
                confirm,
                metadata=(*self.owner.metadata(), deadline_metadata(deadline_ns)),
                timeout=_remaining(self.clock_ns, deadline_ns),
            )
            return bool(
                receipt.admission.result == types.COMMAND_RESULT_ACCEPTED
                and receipt.state.phase == phase
                and receipt.state.pid == child.pid
                and receipt.state.creation_time_100ns == child.creation_time_100ns
            )
        except Exception:
            try:
                state = self.supervisor.GetLaunchState(
                    wire.LaunchQuery(
                        requester=self.owner_identity, launch_command_id=launch_id
                    ),
                    metadata=(*self.owner.metadata(), deadline_metadata(deadline_ns)),
                    timeout=_remaining(self.clock_ns, deadline_ns),
                )
            except Exception:
                return False
            return bool(
                state.phase == phase
                and state.pid == child.pid
                and state.creation_time_100ns == child.creation_time_100ns
            )

    def _confirm_no_child(
        self,
        request: wire.PlanLaunchRequest,
        launch_id: str,
        metadata: tuple[tuple[str, str], ...],
        deadline_ns: int,
    ) -> bool:
        try:
            receipt = self.supervisor.ConfirmLaunch(
                wire.ConfirmLaunchRequest(
                    command_id=str(uuid4()),
                    launch_command_id=launch_id,
                    owner=self.owner_identity,
                    child=request.child,
                    creation_failed_without_child=True,
                ),
                metadata=(*self.owner.metadata(), deadline_metadata(deadline_ns)),
                timeout=_remaining(self.clock_ns, deadline_ns),
            )
            return bool(receipt.admission.result == types.COMMAND_RESULT_ACCEPTED)
        except Exception:
            # Preserve the supervisor's planned job as a cleanup obligation.
            return False

    def retry_storage_cleanup(self) -> None:
        """Reconcile retained native storage handles for this worker."""
        self.file_sync_owner.retry_cleanup()
