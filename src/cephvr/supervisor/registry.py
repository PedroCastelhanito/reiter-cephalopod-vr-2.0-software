"""Generation-bound managed-process launch registry (E08)."""

from __future__ import annotations

import ntpath
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from cephvr.acquisition.identity import ACQUISITION_WORKER_ROLES
from cephvr.acquisition.identity import FFMPEG_ROLES as ACQ_FFMPEG_ROLES
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import (
    HostClockDescriptor,
    descriptor_from_wire,
    host_time_ns,
    validate_host_clock,
)
from cephvr.shared.identity import require_uuid4
from cephvr.visual_stimulus.identity import FFMPEG_ROLES as VISUAL_STIMULUS_FFMPEG_ROLES

LIVE_PHASES = (wire.LAUNCH_PHASE_OPERATIONAL, wire.LAUNCH_PHASE_CLEANUP_REQUIRED)
BACKEND_ROLES = frozenset({"acquisition", "visual_stimulus", "tracking"})
TOP_LEVEL_ROLES = BACKEND_ROLES | {"controller", "gui"}


class LaunchError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


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
    released_seq: int = 0


def _snapshot(entry: _Entry) -> wire.LaunchState:
    return wire.LaunchState.FromString(entry.state.SerializeToString())


def _identity_key(process: types.ProcessIdentity) -> tuple[str, str]:
    return process.role, process.generation


class LaunchRegistry:
    """No PID/name guesswork: each dedicated job must hold exactly its child."""

    def __init__(
        self, native: NativeLaunches, silence_timeout_ns: int, max_launches: int = 1024
    ) -> None:
        if silence_timeout_ns <= 0:
            raise ValueError("silence_timeout_ns must be positive")
        self.native = native
        self.silence_timeout_ns = silence_timeout_ns
        self.max_launches = max_launches
        self._entries: dict[str, _Entry] = {}
        self._release_seq = 0
        self._release_listeners: list[Callable[[wire.LaunchState], None]] = []

    def on_release(self, listener: Callable[[wire.LaunchState], None]) -> None:
        """Notify once per launch when it transitions to RELEASED."""
        self._release_listeners.append(listener)

    def _prune_released(self) -> None:
        """Drop the oldest RELEASED entries (replay window ends at capacity)."""
        released = sorted(
            (
                (entry.released_seq, command_id)
                for command_id, entry in self._entries.items()
                if entry.state.phase == wire.LAUNCH_PHASE_RELEASED
            )
        )
        for _, command_id in released:
            if len(self._entries) < self.max_launches:
                break
            del self._entries[command_id]

    @staticmethod
    def _validate_plan(request: wire.PlanLaunchRequest) -> None:
        require_uuid4(request.command_id)
        require_uuid4(request.owner.generation)
        require_uuid4(request.child.generation)
        if not request.owner.role or not request.child.role or not request.executable:
            raise LaunchError(
                "INVALID_LAUNCH", "owner, child and executable are required"
            )
        if not ntpath.isabs(request.executable):
            raise LaunchError(
                "INVALID_EXECUTABLE", "launch executable must be an absolute path"
            )
        if request.stop_method not in {"grpc_shutdown", "owner_stdin_eof"}:
            raise LaunchError("INVALID_STOP_METHOD", "unsupported child stop method")
        if request.python_worker and request.stop_method != "grpc_shutdown":
            raise LaunchError(
                "INVALID_STOP_METHOD", "Python child requires gRPC shutdown"
            )
        if request.child.role == "supervisor":
            raise LaunchError("INVALID_CHILD", "launcher alone creates supervisor")
        if request.child.role in VISUAL_STIMULUS_FFMPEG_ROLES:
            if request.owner.role != "visual_stimulus_renderer" or not request.HasField(
                "work"
            ):
                raise LaunchError(
                    "INVALID_OWNER",
                    "Visual Stimulus media children require their exact renderer owner and work",
                )
        if (
            request.child.role in ACQ_FFMPEG_ROLES
            and request.owner.role not in ACQUISITION_WORKER_ROLES
        ):
            raise LaunchError(
                "INVALID_OWNER",
                "acquisition media children require an acquisition worker owner",
            )
        if request.child.role in TOP_LEVEL_ROLES and request.owner.role != "supervisor":
            raise LaunchError("INVALID_OWNER", "top-level launch owner is invalid")
        if request.HasField("work") and not request.HasField("parent_operation"):
            raise LaunchError(
                "MISSING_OPERATION", "work-scoped launch requires parent operation"
            )

    def plan(self, request: wire.PlanLaunchRequest) -> wire.LaunchState:
        self._validate_plan(request)
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
            self._prune_released()
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
                    and entry.plan.owner.role in ACQUISITION_WORKER_ROLES
                ):
                    # A camera-owned encoder normally exits at EOF. Its exact
                    # worker must retain output closure before this launch can
                    # be released; process exit alone is not a helper failure.
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
        if entry.state.phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED:
            if previous_confirmation is not None:
                return _snapshot(entry)
            raise LaunchError(
                "CLEANUP_REQUIRED", "planned child requires reconciliation"
            )
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
        self._release_seq += 1
        entry.released_seq = self._release_seq
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
