"""Generation-bound managed-process launch registry (E08)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from cephvr.acquisition.identity import ACQUISITION_WORKER_ROLES
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.controller.microcontroller.identity import FIRMWARE_UPLOAD_ROLE
from cephvr.shared.clock import (
    HostClockDescriptor,
    descriptor_from_wire,
    host_time_ns,
    validate_host_clock,
)
from cephvr.shared.commands import DEFAULT_COMMAND_RETENTION_NS
from cephvr.shared.identity import require_uuid4
from cephvr.supervisor.camera_release import camera_release_request_matches
from cephvr.supervisor.launch_validation import (
    BACKEND_ROLES as BACKEND_ROLES,
)
from cephvr.supervisor.launch_validation import (
    TOP_LEVEL_ROLES as TOP_LEVEL_ROLES,
)
from cephvr.supervisor.launch_validation import (
    LaunchError as LaunchError,
)
from cephvr.supervisor.launch_validation import (
    launch_work_key,
    validate_plan,
)
from cephvr.visual_stimulus.identity import FFMPEG_ROLES as VISUAL_STIMULUS_FFMPEG_ROLES

LIVE_PHASES = (wire.LAUNCH_PHASE_OPERATIONAL, wire.LAUNCH_PHASE_CLEANUP_REQUIRED)


class NativeLaunches(Protocol):
    """Small OS boundary. The Windows implementation retains all opened handles."""

    def create_launch_job(self, name: str) -> None: ...

    def inspect_launch_job(self, name: str) -> list[tuple[int, int, str]]: ...

    def process_running(self, pid: int, creation_time_100ns: int) -> bool: ...

    def terminate_exact(self, pid: int, creation_time_100ns: int) -> None: ...

    def close_launch_job(self, name: str) -> None: ...

    def release_process(self, pid: int, creation_time_100ns: int) -> None: ...

    def retain_exact(
        self, pid: int, creation_time_100ns: int, executable: str
    ) -> object: ...


@dataclass
class _Entry:
    plan: wire.PlanLaunchRequest
    state: wire.LaunchState
    deadline_ns: int
    os_confirm_command_id: str | None = None
    confirmations: dict[str, bytes] = field(default_factory=dict)
    released_ns: int | None = None
    work_key: str | None = None
    camera_cleanup_proof: bytes | None = None


def _snapshot(entry: _Entry) -> wire.LaunchState:
    return wire.LaunchState.FromString(entry.state.SerializeToString())


def _identity_key(process: types.ProcessIdentity) -> tuple[str, str]:
    return process.role, process.generation


class LaunchRegistry:
    """No PID/name guesswork: each dedicated job must hold exactly its child."""

    def __init__(
        self,
        native: NativeLaunches,
        silence_timeout_ns: int,
        max_launches: int = 1024,
        retention_ns: int = DEFAULT_COMMAND_RETENTION_NS,
    ) -> None:
        if silence_timeout_ns <= 0 or retention_ns <= 0 or max_launches <= 0:
            raise ValueError("launch timeouts and capacity must be positive")
        self.native = native
        self.silence_timeout_ns = silence_timeout_ns
        self.max_launches = max_launches
        self.retention_ns = retention_ns
        self._entries: dict[str, _Entry] = {}
        self._finalized_work: dict[str, int] = {}
        self._release_listeners: list[Callable[[wire.LaunchState], None]] = []

    def on_release(self, listener: Callable[[wire.LaunchState], None]) -> None:
        """Notify once per launch when it transitions to RELEASED."""
        self._release_listeners.append(listener)

    def finalize_work(self, work_key: str, finalized_ns: int | None = None) -> None:
        """Start replay retention for a completed session work scope."""
        require_uuid4(work_key)
        now_ns = host_time_ns() if finalized_ns is None else finalized_ns
        prior = self._finalized_work.setdefault(work_key, now_ns)
        now_ns = prior
        self._prune_released(now_ns)

    def _prune_released(self, now_ns: int) -> None:
        """Remove only RELEASED plans past their E08 replay-retention window."""
        expired = []
        for command_id, entry in self._entries.items():
            if entry.state.phase != wire.LAUNCH_PHASE_RELEASED:
                continue
            finalized_ns = self._finalized_work.get(entry.work_key or "")
            retention_start_ns = (
                max(entry.released_ns, finalized_ns)
                if finalized_ns is not None and entry.released_ns is not None
                else entry.released_ns
                if entry.work_key is None
                else None
            )
            if (
                retention_start_ns is not None
                and now_ns > retention_start_ns + self.retention_ns
            ):
                expired.append(command_id)
        for command_id in expired:
            del self._entries[command_id]
        retained_work_keys = {
            entry.work_key
            for entry in self._entries.values()
            if entry.work_key is not None
        }
        for work_key in tuple(self._finalized_work):
            if work_key not in retained_work_keys:
                del self._finalized_work[work_key]

    def plan(self, request: wire.PlanLaunchRequest) -> wire.LaunchState:
        validate_plan(request)
        self._prune_released(host_time_ns())
        prior = self._entries.get(request.command_id)
        if prior:
            if prior.plan.SerializeToString(
                deterministic=True
            ) != request.SerializeToString(deterministic=True):
                raise LaunchError(
                    "COMMAND_ID_REUSED", "launch command ID has changed payload"
                )
            return self.refresh(request.command_id)
        if len(self._entries) >= self.max_launches:
            raise LaunchError("LAUNCH_CAPACITY", "retained launch capacity exhausted")
        if any(
            _identity_key(entry.plan.child) == _identity_key(request.child)
            and entry.state.phase != wire.LAUNCH_PHASE_RELEASED
            for entry in self._entries.values()
        ):
            raise LaunchError(
                "CHILD_ALREADY_PLANNED", "child generation already has a launch"
            )
        name = f"Local\\CephVR2-{uuid4()}"
        try:
            self.native.create_launch_job(name)
        except Exception as exc:
            raise LaunchError(
                "CONTAINMENT_FAILED", "planned job creation failed"
            ) from exc
        state = wire.LaunchState(
            plan=request,
            phase=wire.LAUNCH_PHASE_PLANNED,
            containment_job_name=name,
        )
        self._entries[request.command_id] = _Entry(
            plan=wire.PlanLaunchRequest.FromString(request.SerializeToString()),
            state=state,
            deadline_ns=host_time_ns() + self.silence_timeout_ns,
            work_key=launch_work_key(request) if request.HasField("work") else None,
        )
        return wire.LaunchState.FromString(state.SerializeToString())

    def refresh(self, command_id: str) -> wire.LaunchState:
        entry = self._get(command_id)
        if entry.state.phase == wire.LAUNCH_PHASE_RELEASED:
            return _snapshot(entry)
        members = self._members(entry)
        if len(members) > 1 and entry.state.phase == wire.LAUNCH_PHASE_PLANNED:
            self._block(entry, "AMBIGUOUS_JOB", "planned job has multiple children")
        # A member before confirmation remains a tracked starting obligation;
        # only an expired deadline or owner loss turns it into cleanup-required.
        if entry.state.phase in (
            wire.LAUNCH_PHASE_OS_CONFIRMED,
            wire.LAUNCH_PHASE_OPERATIONAL,
        ):
            if not members or not self._running(entry):
                if (
                    entry.plan.stop_method == "owner_stdin_eof"
                    and (
                        entry.plan.owner.role in ACQUISITION_WORKER_ROLES
                        or (
                            entry.plan.owner.role == "visual_stimulus_renderer"
                            and entry.plan.child.role in VISUAL_STIMULUS_FFMPEG_ROLES
                        )
                    )
                    or entry.plan.child.role == FIRMWARE_UPLOAD_ROLE
                ):
                    # Normal helper exit still requires its owning backend
                    # to confirm exact native/resource closure before release.
                    return _snapshot(entry)
                self._block(
                    entry,
                    "CHILD_EXITED",
                    f"registered {entry.plan.child.role} PID {entry.state.pid} exited; "
                    "cleanup evidence remains required",
                )
        if (
            entry.state.phase
            in (wire.LAUNCH_PHASE_PLANNED, wire.LAUNCH_PHASE_OS_CONFIRMED)
            and host_time_ns() >= entry.deadline_ns
        ):
            self._block(entry, "LAUNCH_TIMEOUT", "launch registration deadline expired")
        return _snapshot(entry)

    def planned_request(self, command_id: str) -> wire.PlanLaunchRequest:
        """Return immutable launch identity before any native inspection."""
        entry = self._get(command_id)
        return wire.PlanLaunchRequest.FromString(entry.plan.SerializeToString())

    def confirm(
        self, request: wire.ConfirmLaunchRequest, expected_clock: HostClockDescriptor
    ) -> wire.LaunchState:
        """Adopt exact planned process ownership before accepting operational evidence."""
        require_uuid4(request.command_id)
        entry = self._get(request.launch_command_id)
        canonical = request.SerializeToString(deterministic=True)
        previous_confirmation = entry.confirmations.get(request.command_id)
        if previous_confirmation is not None and previous_confirmation != canonical:
            raise LaunchError(
                "COMMAND_ID_REUSED", "confirmation command ID has changed payload"
            )
        if (
            previous_confirmation is not None
            and entry.state.phase == wire.LAUNCH_PHASE_RELEASED
        ):
            return _snapshot(entry)
        if previous_confirmation is None and len(entry.confirmations) >= 8:
            raise LaunchError(
                "CONFIRM_CAPACITY", "launch confirmation record capacity exhausted"
            )
        if _identity_key(entry.plan.owner) != _identity_key(
            request.owner
        ) or _identity_key(entry.plan.child) != _identity_key(request.child):
            raise LaunchError(
                "WRONG_GENERATION", "launch identities differ from retained plan"
            )
        if (
            entry.state.phase
            in (wire.LAUNCH_PHASE_PLANNED, wire.LAUNCH_PHASE_OS_CONFIRMED)
            and host_time_ns() >= entry.deadline_ns
        ):
            raise self._block(
                entry, "LAUNCH_TIMEOUT", "launch registration deadline expired"
            )
        has_camera_cleanup = request.HasField("acquisition_worker_cleanup")
        if (
            entry.state.phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
            and not request.native_cleanup_complete
            and not has_camera_cleanup
        ):
            if previous_confirmation is not None:
                return _snapshot(entry)
            raise LaunchError(
                "CLEANUP_REQUIRED", "planned child requires reconciliation"
            )
        if request.native_cleanup_complete:
            if (
                entry.plan.child.role != FIRMWARE_UPLOAD_ROLE
                or request.HasField("pid") != entry.state.HasField("pid")
                or request.HasField("creation_time_100ns")
                != entry.state.HasField("creation_time_100ns")
                or request.pid != entry.state.pid
                or request.creation_time_100ns != entry.state.creation_time_100ns
                or request.HasField("endpoint")
                or request.HasField("host_clock")
                or request.creation_failed_without_child
            ):
                raise LaunchError(
                    "INVALID_NATIVE_RELEASE",
                    "firmware cleanup must match the retained exact child",
                )
            released = self.release(request.launch_command_id, obligations_met=True)
            entry.confirmations[request.command_id] = canonical
            return released
        if has_camera_cleanup:
            self._release_camera_worker(request, entry, canonical)
            return _snapshot(entry)
        members = self._members(entry)
        if (
            request.HasField("creation_failed_without_child")
            and request.creation_failed_without_child
        ):
            if members:
                self._block(
                    entry,
                    "UNCONFIRMED_CHILD",
                    "creation failure reported with a child in job",
                )
                raise LaunchError("UNCONFIRMED_CHILD", "planned job is not empty")
            self._block(
                entry,
                request.failure.code or "CREATE_FAILED",
                request.failure.message or "child creation failed",
            )
            return self.refresh(request.launch_command_id)
        if not request.HasField("pid") or not request.HasField("creation_time_100ns"):
            raise LaunchError(
                "MISSING_PROCESS_ID", "PID and process creation time are required"
            )
        matched = (
            entry.state.phase != wire.LAUNCH_PHASE_PLANNED or len(members) == 1
        ) and any(
            member[:2] == (request.pid, request.creation_time_100ns)
            and os.path.normcase(os.path.abspath(member[2]))
            == os.path.normcase(os.path.abspath(entry.plan.executable))
            for member in members
        )
        if not matched:
            self._block(
                entry,
                "PROCESS_MISMATCH",
                "job membership, executable or creation time mismatch",
            )
            raise LaunchError(
                "PROCESS_MISMATCH", "child identity not verified in planned job"
            )
        if entry.state.phase == wire.LAUNCH_PHASE_PLANNED:
            try:
                self.native.retain_exact(
                    request.pid, request.creation_time_100ns, entry.plan.executable
                )
            except Exception as exc:
                raise self._block(
                    entry,
                    "PROCESS_RETAIN_FAILED",
                    "exact child handle could not be retained",
                ) from exc
        entry.state.pid = request.pid
        entry.state.creation_time_100ns = request.creation_time_100ns
        if not self._running(entry):
            raise self._block(entry, "CHILD_EXITED", "child exited before confirmation")
        if entry.state.phase == wire.LAUNCH_PHASE_OPERATIONAL:
            if (
                request.HasField("endpoint")
                and request.endpoint != entry.state.endpoint
            ):
                raise LaunchError("COMMAND_ID_REUSED", "endpoint confirmation changed")
            if (
                request.HasField("host_clock")
                and request.host_clock != entry.state.host_clock
            ):
                raise LaunchError(
                    "COMMAND_ID_REUSED", "host clock confirmation changed"
                )
            entry.confirmations[request.command_id] = canonical
            return self.refresh(request.launch_command_id)
        if (
            entry.plan.python_worker
            and entry.state.phase == wire.LAUNCH_PHASE_PLANNED
            and request.HasField("endpoint")
        ):
            raise LaunchError(
                "WRONG_STAGE",
                "Python endpoint cannot precede OS confirmation and resume",
            )
        if not entry.plan.python_worker and (
            request.HasField("endpoint") or request.HasField("host_clock")
        ):
            raise LaunchError(
                "INVALID_NATIVE_CONFIRMATION",
                "native helper has no Python endpoint or clock",
            )
        if entry.state.phase == wire.LAUNCH_PHASE_PLANNED:
            entry.state.phase = wire.LAUNCH_PHASE_OS_CONFIRMED
            entry.os_confirm_command_id = request.command_id
            entry.confirmations[request.command_id] = canonical
            return self.refresh(request.launch_command_id)
        if entry.plan.python_worker:
            if not request.HasField("endpoint"):
                entry.confirmations[request.command_id] = canonical
                return self.refresh(request.launch_command_id)
            if not request.endpoint.startswith(("127.0.0.1:", "[::1]:")):
                raise LaunchError(
                    "INVALID_ENDPOINT", "Python child endpoint must be loopback"
                )
            if not request.HasField("host_clock"):
                raise LaunchError(
                    "MISSING_CLOCK", "Python child host clock is required"
                )
            validate_host_clock(
                descriptor_from_wire(request.host_clock), expected_clock
            )
            entry.state.endpoint = request.endpoint
            entry.state.host_clock.CopyFrom(request.host_clock)
        else:
            if request.command_id == entry.os_confirm_command_id:
                entry.confirmations[request.command_id] = canonical
                return self.refresh(request.launch_command_id)
        entry.state.phase = wire.LAUNCH_PHASE_OPERATIONAL
        entry.confirmations[request.command_id] = canonical
        return self.refresh(request.launch_command_id)

    def _release_camera_worker(
        self,
        request: wire.ConfirmLaunchRequest,
        entry: _Entry,
        canonical: bytes,
    ) -> None:
        if not camera_release_request_matches(request, entry.plan, entry.state):
            raise LaunchError(
                "INVALID_WORKER_CLEANUP",
                "retained Cleanup proof is incomplete or mismatched",
            )
        proof = request.acquisition_worker_cleanup.SerializeToString(deterministic=True)
        if (
            entry.camera_cleanup_proof is not None
            and entry.camera_cleanup_proof != proof
        ):
            raise LaunchError(
                "COMMAND_ID_REUSED",
                "camera cleanup proof changed after retirement acknowledgement",
            )
        members = self._members(entry)
        running = self._running(entry)
        if members or running:
            if (
                entry.state.phase == wire.LAUNCH_PHASE_OPERATIONAL
                and len(members) == 1
                and members[0][:2] == (entry.state.pid, entry.state.creation_time_100ns)
                and os.path.normcase(os.path.abspath(members[0][2]))
                == os.path.normcase(os.path.abspath(entry.plan.executable))
                and running
            ):
                # Retain exact owner-verified cleanup before Shutdown. This
                # narrowly authorizes the ensuing exact worker exit.
                if entry.camera_cleanup_proof is None:
                    entry.camera_cleanup_proof = proof
                entry.confirmations[request.command_id] = canonical
                return
            raise LaunchError(
                "PROCESS_STILL_RUNNING",
                "camera worker process/job absence is unconfirmed",
            )
        if entry.camera_cleanup_proof is None:
            raise LaunchError(
                "MISSING_CLEANUP_ACK",
                "camera worker exit preceded its cleanup acknowledgement",
            )
        self.release(entry.plan.command_id, obligations_met=True)
        entry.confirmations[request.command_id] = canonical

    def camera_cleanup_acknowledged(self, command_id: str) -> bool:
        """Return whether this exact launch retained its owner's Cleanup proof."""
        entry = self._entries.get(command_id)
        return bool(
            entry is not None
            and entry.camera_cleanup_proof is not None
            and entry.plan.child.role in ACQUISITION_WORKER_ROLES
        )

    def release(self, command_id: str, obligations_met: bool) -> wire.LaunchState:
        entry = self._get(command_id)
        if entry.state.phase == wire.LAUNCH_PHASE_RELEASED:
            # Idempotent: the job is already closed, never re-inspect it.
            return _snapshot(entry)
        if self._members(entry):
            raise LaunchError("PROCESS_STILL_RUNNING", "job still contains a child")
        if not obligations_met:
            raise LaunchError(
                "CLEANUP_REQUIRED", "resource/output obligations are not verified"
            )
        self.native.close_launch_job(entry.state.containment_job_name)
        if entry.state.HasField("pid"):
            self.native.release_process(
                entry.state.pid, entry.state.creation_time_100ns
            )
        entry.state.phase = wire.LAUNCH_PHASE_RELEASED
        entry.released_ns = host_time_ns()
        if entry.work_key is not None:
            self._prune_released(entry.released_ns)
        released = _snapshot(entry)
        for listener in self._release_listeners:
            listener(released)
        return released

    def release_gui_if_empty(self, command_id: str) -> wire.LaunchState:
        """Release a GUI launch only after its exact native job is empty."""
        entry = self._get(command_id)
        if entry.plan.child.role != "gui":
            raise LaunchError("WRONG_ROLE", "only GUI launches use this release path")
        state = self.refresh(command_id)
        if state.phase == wire.LAUNCH_PHASE_RELEASED:
            return state
        if (
            state.phase != wire.LAUNCH_PHASE_CLEANUP_REQUIRED
            or not state.HasField("pid")
            or not state.HasField("creation_time_100ns")
        ):
            return state
        if self._members(entry):
            return _snapshot(entry)
        return self.release(command_id, obligations_met=True)

    def states(self, *, tolerant: bool = False) -> list[wire.LaunchState]:
        """Refresh every launch; tolerant callers get a failed entry's blocked state."""
        if not tolerant:
            return [self.refresh(command_id) for command_id in list(self._entries)]
        result = []
        for command_id in list(self._entries):
            try:
                result.append(self.refresh(command_id))
            except LaunchError:
                result.append(_snapshot(self._entries[command_id]))
        return result

    def _get(self, command_id: str) -> _Entry:
        try:
            return self._entries[command_id]
        except KeyError as exc:
            raise LaunchError(
                "UNKNOWN_LAUNCH", "launch command ID is not registered"
            ) from exc

    def _members(self, entry: _Entry) -> list[tuple[int, int, str]]:
        try:
            return self.native.inspect_launch_job(entry.state.containment_job_name)
        except Exception as exc:
            raise self._block(
                entry,
                "JOB_INSPECTION_FAILED",
                f"planned job membership could not be verified: {exc}",
            ) from exc

    def _running(self, entry: _Entry) -> bool:
        try:
            return self.native.process_running(
                entry.state.pid, entry.state.creation_time_100ns
            )
        except Exception as exc:
            raise self._block(
                entry,
                "PROCESS_INSPECTION_FAILED",
                "exact child process state is unknown",
            ) from exc

    @staticmethod
    def _block(entry: _Entry, code: str, message: str) -> LaunchError:
        entry.state.phase = wire.LAUNCH_PHASE_CLEANUP_REQUIRED
        entry.state.failure.CopyFrom(types.Failure(code=code, message=message))
        return LaunchError(code, message)
