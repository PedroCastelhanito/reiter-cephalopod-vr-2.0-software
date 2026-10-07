"""Explicit same-generation GUI relaunch through its persistent supervisor (E03/E08)."""

from __future__ import annotations

import queue
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

import grpc

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.jobs import WindowsLaunchError
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.shared.identity import require_uuid4
from cephvr.shared.transport_deadlines import deadline_metadata, remaining_seconds


@dataclass(frozen=True)
class GuiLaunchRegistration:
    supervisor_generation: str
    generation: str
    launch_command_id: str
    pid: int
    creation_time_100ns: int

    def __post_init__(self) -> None:
        require_uuid4(self.supervisor_generation)
        require_uuid4(self.generation)
        require_uuid4(self.launch_command_id)
        if self.pid <= 0 or self.creation_time_100ns <= 0:
            raise WindowsLaunchError("invalid GUI process identity")

    @classmethod
    def from_notification(cls, note: dict[str, object]) -> GuiLaunchRegistration:
        required = {
            "supervisor_generation",
            "child_generation",
            "launch_command_id",
            "pid",
            "creation_time_100ns",
        }
        if (
            set(note) != required | {"kind", "_channel"}
            or note.get("kind") != "register_gui_launch"
            or note.get("_channel") != "supervisor"
        ):
            raise WindowsLaunchError("invalid GUI registration notification")
        values = (
            note["supervisor_generation"],
            note["child_generation"],
            note["launch_command_id"],
        )
        if any(not isinstance(value, str) or not value for value in values):
            raise WindowsLaunchError("incomplete GUI registration identity")
        pid, created = note["pid"], note["creation_time_100ns"]
        if type(pid) is not int or pid <= 0 or type(created) is not int or created <= 0:
            raise WindowsLaunchError("invalid GUI process identity")
        return cls(str(values[0]), str(values[1]), str(values[2]), pid, created)


@dataclass(frozen=True)
class GuiRelaunchAttempt:
    """Exact successor identity retained when the PlanLaunch reply is uncertain."""

    supervisor_generation: str
    previous: GuiLaunchRegistration
    launch_command_id: str
    child_generation: str
    deadline_ns: int

    def __post_init__(self) -> None:
        require_uuid4(self.supervisor_generation)
        require_uuid4(self.launch_command_id)
        require_uuid4(self.child_generation)
        if self.previous.supervisor_generation != self.supervisor_generation:
            raise WindowsLaunchError("GUI relaunch belongs to another supervisor")
        if self.deadline_ns <= 0:
            raise WindowsLaunchError("GUI relaunch deadline is invalid")

    @classmethod
    def create(
        cls, current: GuiLaunchRegistration, *, deadline_ns: int
    ) -> GuiRelaunchAttempt:
        return cls(
            current.supervisor_generation,
            current,
            str(uuid4()),
            str(uuid4()),
            deadline_ns,
        )

    def matches(self, registration: GuiLaunchRegistration) -> bool:
        return (
            registration.supervisor_generation == self.supervisor_generation
            and registration.launch_command_id == self.launch_command_id
            and registration.generation == self.child_generation
        )


@dataclass(frozen=True)
class GuiRelaunchWork:
    attempt: GuiRelaunchAttempt
    reconcile_only: bool


@dataclass(frozen=True)
class GuiRelaunchResult:
    work: GuiRelaunchWork
    registration: GuiLaunchRegistration | None
    error: str
    definite_failure: bool = False
    terminal_released: bool = False


@dataclass(frozen=True)
class GuiRelaunchReleased:
    """The exact uncertain attempt reached authoritative RELEASED state."""

    attempt: GuiRelaunchAttempt


class GuiRelaunchDispatcher:
    """Run supervisor RPCs off the launcher safety loop and retain outcomes."""

    def __init__(
        self,
        coordinator: GuiRelaunchCoordinator,
        perform: Callable[
            [GuiRelaunchWork], GuiLaunchRegistration | GuiRelaunchReleased | None
        ],
    ) -> None:
        self.coordinator = coordinator
        self.perform = perform
        self.results: queue.Queue[GuiRelaunchResult] = queue.Queue(maxsize=4)

    def request(self, *, deadline_ns: int, now_ns: int) -> GuiRelaunchWork | None:
        work = self.coordinator.request(deadline_ns=deadline_ns, now_ns=now_ns)
        if work is None:
            return None
        self.start(work)
        return work

    def start(self, work: GuiRelaunchWork) -> None:
        threading.Thread(
            target=self._run,
            args=(work,),
            daemon=True,
            name="cephvr-gui-relaunch",
        ).start()

    def _run(self, work: GuiRelaunchWork) -> None:
        try:
            outcome = self.perform(work)
            if isinstance(outcome, GuiRelaunchReleased):
                result = GuiRelaunchResult(work, None, "", terminal_released=True)
            else:
                result = GuiRelaunchResult(work, outcome, "")
        except GuiRelaunchNotSubmitted as exc:
            result = GuiRelaunchResult(work, None, str(exc), definite_failure=True)
        except Exception as exc:
            result = GuiRelaunchResult(work, None, str(exc))
        self.results.put(result)

    def poll(self) -> tuple[GuiRelaunchResult, ...]:
        completed: list[GuiRelaunchResult] = []
        for _ in range(4):
            try:
                result = self.results.get_nowait()
            except queue.Empty:
                break
            self.coordinator.completed(
                result.work,
                result.registration,
                definite_failure=result.definite_failure,
                terminal_released=result.terminal_released,
            )
            completed.append(result)
        return tuple(completed)

    def shutdown(self) -> None:
        self.coordinator.shutdown()


class GuiRelaunchCoordinator:
    """Serialize explicit relaunch attempts and reconcile late exact evidence."""

    def __init__(self) -> None:
        self.current: GuiLaunchRegistration | None = None
        self.attempt: GuiRelaunchAttempt | None = None
        self.worker_running = False
        self.shutdown_started = False

    def registered(self, registration: GuiLaunchRegistration) -> bool:
        attempt = self.attempt
        if attempt is not None:
            if not attempt.matches(registration):
                return False
            self.current = registration
            self.attempt = None
            return True
        if self.current is None:
            self.current = registration
            return True
        return registration == self.current

    def request(
        self, *, deadline_ns: int, now_ns: int | None = None
    ) -> GuiRelaunchWork | None:
        now = host_time_ns() if now_ns is None else now_ns
        if self.shutdown_started or self.worker_running or deadline_ns <= now:
            return None
        if self.attempt is not None:
            self.worker_running = True
            return GuiRelaunchWork(self.attempt, reconcile_only=True)
        if self.current is None:
            return None
        self.attempt = GuiRelaunchAttempt.create(self.current, deadline_ns=deadline_ns)
        self.worker_running = True
        return GuiRelaunchWork(self.attempt, reconcile_only=False)

    def completed(
        self,
        work: GuiRelaunchWork,
        registration: GuiLaunchRegistration | None,
        *,
        definite_failure: bool = False,
        terminal_released: bool = False,
    ) -> bool:
        self.worker_running = False
        if self.attempt != work.attempt:
            return False
        if definite_failure:
            self.attempt = None
            return False
        if terminal_released and work.reconcile_only:
            self.attempt = None
            return False
        if registration is None:
            return False
        if not work.attempt.matches(registration):
            return False
        self.current = registration
        self.attempt = None
        return True

    def shutdown(self) -> None:
        self.shutdown_started = True


class GuiRelaunchNotSubmitted(WindowsLaunchError):
    """The attempt is proven not to have reached PlanLaunch admission."""


def _exact_gui_released(
    state: wire.LaunchState, current: GuiLaunchRegistration
) -> bool:
    return (
        state.plan.command_id == current.launch_command_id
        and state.plan.owner.role == "supervisor"
        and state.plan.owner.generation == current.supervisor_generation
        and state.plan.child.role == "gui"
        and state.plan.child.generation == current.generation
        and state.HasField("pid")
        and state.pid == current.pid
        and state.HasField("creation_time_100ns")
        and state.creation_time_100ns == current.creation_time_100ns
        and state.phase == wire.LAUNCH_PHASE_RELEASED
    )


def request_relaunch(
    *,
    supervisor_port: int,
    supervisor: types.ProcessIdentity,
    supervisor_token: str,
    interpreter: str,
    attempt: GuiRelaunchAttempt,
) -> GuiLaunchRegistration:
    """Plan a fresh GUI only after the registry confirms exact prior release."""
    if (
        supervisor.role != "supervisor"
        or supervisor.generation != attempt.supervisor_generation
    ):
        raise GuiRelaunchNotSubmitted("GUI registration belongs to another supervisor")
    authority = Principal("supervisor", supervisor.generation, supervisor_token)
    channel = None
    submitted = False
    try:
        channel = grpc.insecure_channel(f"127.0.0.1:{supervisor_port}")
        stub = services_pb2_grpc.SupervisorServiceStub(channel)  # type: ignore[no-untyped-call]
        timeout_s = remaining_seconds(attempt.deadline_ns)
        if timeout_s <= 0:
            raise TimeoutError("GUI relaunch deadline expired")
        old_state = stub.GetLaunchState(
            wire.LaunchQuery(
                requester=supervisor,
                launch_command_id=attempt.previous.launch_command_id,
            ),
            metadata=authority.metadata(),
            timeout=timeout_s,
        )
        if not _exact_gui_released(old_state, attempt.previous):
            raise WindowsLaunchError("the exact prior GUI process is not released")
        timeout_s = remaining_seconds(attempt.deadline_ns)
        if timeout_s <= 0:
            raise TimeoutError("GUI relaunch deadline expired")
        child_token = secrets.token_urlsafe(48)
        request = wire.PlanLaunchRequest(
            command_id=attempt.launch_command_id,
            owner=supervisor,
            child=types.ProcessIdentity(
                role="gui", generation=attempt.child_generation
            ),
            executable=interpreter,
            python_worker=True,
            stop_method="grpc_shutdown",
        )
        submitted = True
        receipt = stub.PlanLaunch(
            request,
            metadata=(
                *authority.metadata(),
                ("x-cephvr-child-token", child_token),
                deadline_metadata(attempt.deadline_ns),
            ),
            timeout=timeout_s,
        )
        if receipt.admission.result != types.COMMAND_RESULT_ACCEPTED:
            raise WindowsLaunchError(
                "supervisor rejected GUI relaunch: "
                + (receipt.admission.failure.message or receipt.admission.failure.code)
            )
        registration = _registration_from_state(receipt.state, attempt)
        if registration is None:
            raise WindowsLaunchError("supervisor did not confirm the new GUI process")
        return registration
    except GuiRelaunchNotSubmitted:
        raise
    except Exception as exc:
        if not submitted:
            raise GuiRelaunchNotSubmitted(str(exc)) from exc
        raise
    finally:
        if channel is not None:
            channel.close()


def _registration_from_state(
    state: wire.LaunchState, attempt: GuiRelaunchAttempt
) -> GuiLaunchRegistration | None:
    if (
        state.plan.command_id != attempt.launch_command_id
        or state.plan.owner.role != "supervisor"
        or state.plan.owner.generation != attempt.supervisor_generation
        or state.plan.child.role != "gui"
        or state.plan.child.generation != attempt.child_generation
        or not state.HasField("pid")
        or not state.HasField("creation_time_100ns")
        or state.phase
        not in (wire.LAUNCH_PHASE_OS_CONFIRMED, wire.LAUNCH_PHASE_OPERATIONAL)
    ):
        return None
    return GuiLaunchRegistration(
        attempt.supervisor_generation,
        attempt.child_generation,
        attempt.launch_command_id,
        state.pid,
        state.creation_time_100ns,
    )


def _exact_attempt_released(
    state: wire.LaunchState, attempt: GuiRelaunchAttempt
) -> bool:
    return (
        state.plan.command_id == attempt.launch_command_id
        and state.plan.owner.role == "supervisor"
        and state.plan.owner.generation == attempt.supervisor_generation
        and state.plan.child.role == "gui"
        and state.plan.child.generation == attempt.child_generation
        and state.phase == wire.LAUNCH_PHASE_RELEASED
        and (not state.HasField("pid") or state.pid > 0)
        and (not state.HasField("creation_time_100ns") or state.creation_time_100ns > 0)
    )


def reconcile_relaunch(
    *,
    supervisor_port: int,
    supervisor: types.ProcessIdentity,
    supervisor_token: str,
    attempt: GuiRelaunchAttempt,
) -> GuiLaunchRegistration | GuiRelaunchReleased | None:
    """Query the exact uncertain attempt; never submit another PlanLaunch."""
    if (
        supervisor.role != "supervisor"
        or supervisor.generation != attempt.supervisor_generation
    ):
        raise WindowsLaunchError("GUI registration belongs to another supervisor")
    # This is a read-only reconciliation budget, separate from the immutable
    # PlanLaunch deadline. It permits a later explicit request to inspect an
    # attempt whose reply was lost without extending or replaying that attempt.
    timeout_s = 2.0
    authority = Principal("supervisor", supervisor.generation, supervisor_token)
    channel = grpc.insecure_channel(f"127.0.0.1:{supervisor_port}")
    stub = services_pb2_grpc.SupervisorServiceStub(channel)  # type: ignore[no-untyped-call]
    try:
        state = stub.GetLaunchState(
            wire.LaunchQuery(
                requester=supervisor,
                launch_command_id=attempt.launch_command_id,
            ),
            metadata=authority.metadata(),
            timeout=timeout_s,
        )
        if _exact_attempt_released(state, attempt):
            return GuiRelaunchReleased(attempt)
        return _registration_from_state(state, attempt)
    finally:
        channel.close()
