"""Exact launch identity, containment, capacity and idempotent release."""

from __future__ import annotations

from uuid import uuid4

import pytest

from cephvr.acquisition.identity import FFMPEG_ROLE
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import (
    HostClockCompatibilityError,
    describe_host_clock,
)
from cephvr.supervisor.registry import LaunchError, LaunchRegistry
from cephvr.visual_stimulus.identity import FFMPEG_ROLE as VISUAL_STIMULUS_FFMPEG_ROLE
from tests.supervisor.support import Native

from .support import EXE, WORKER_ROLE, _identity, _launch

# Idempotent release and retained launch capacity.


def test_release_is_idempotent_and_never_resurrects() -> None:
    native = Native()
    registry = LaunchRegistry(native, 15_000_000_000)
    seen: list[wire.LaunchState] = []
    registry.on_release(seen.append)
    state = _launch(
        registry,
        native,
        _identity("acquisition"),
        _identity(WORKER_ROLE),
        1,
        python=True,
    )
    native.jobs[state.containment_job_name] = []
    first = registry.release(state.plan.command_id, obligations_met=True)
    again = registry.release(state.plan.command_id, obligations_met=True)
    assert first.phase == again.phase == wire.LAUNCH_PHASE_RELEASED
    assert registry.refresh(state.plan.command_id).phase == wire.LAUNCH_PHASE_RELEASED
    assert len(seen) == 1


def test_capacity_counts_only_live_launches_and_replay_survives_until_pruned() -> None:
    native = Native()
    registry = LaunchRegistry(native, 15_000_000_000, max_launches=3)
    owner = _identity("acquisition")
    released = []
    for pid in range(1, 8):
        state = _launch(
            registry, native, owner, _identity(WORKER_ROLE), pid, python=True
        )
        native.jobs[state.containment_job_name] = []
        registry.release(state.plan.command_id, obligations_met=True)
        released.append(state)
    assert len(registry._entries) <= 3
    live = [
        _launch(registry, native, owner, _identity(WORKER_ROLE), 20 + i, python=True)
        for i in range(3)
    ]
    # Only live launches fill capacity: a fourth live launch is refused.
    with pytest.raises(LaunchError, match="capacity"):
        registry.plan(
            wire.PlanLaunchRequest(
                command_id=str(uuid4()),
                owner=owner,
                child=_identity(WORKER_ROLE),
                executable=EXE,
                python_worker=True,
                stop_method="grpc_shutdown",
            )
        )
    assert all(item.plan.command_id in registry._entries for item in live)
    # A retained released entry still replays its exact plan idempotently.
    registry2 = LaunchRegistry(native, 15_000_000_000, max_launches=4)
    state = _launch(registry2, native, owner, _identity(WORKER_ROLE), 90, python=True)
    native.jobs[state.containment_job_name] = []
    registry2.release(state.plan.command_id, obligations_met=True)
    assert registry2.plan(state.plan).phase == wire.LAUNCH_PHASE_RELEASED


def test_tolerant_states_keep_other_entries_when_one_job_is_unreadable() -> None:
    native = Native()
    registry = LaunchRegistry(native, 15_000_000_000)
    good = _launch(
        registry,
        native,
        _identity("acquisition"),
        _identity(WORKER_ROLE),
        1,
        python=True,
    )
    bad = _launch(
        registry,
        native,
        _identity("acquisition_behavioral_worker"),
        _identity(FFMPEG_ROLE),
        2,
        python=False,
    )
    del native.jobs[bad.containment_job_name]  # inspection now fails for this job
    with pytest.raises(LaunchError):
        registry.states()
    states = {s.plan.command_id: s for s in registry.states(tolerant=True)}
    assert states[good.plan.command_id].phase == good.phase
    assert states[bad.plan.command_id].phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED


class RegistryNative:
    def __init__(self) -> None:
        self.jobs: dict[str, list[tuple[int, int, str]]] = {}
        self.closed: set[str] = set()
        self.retained: set[tuple[int, int, str]] = set()

    def create_launch_job(self, name: str) -> None:
        self.jobs[name] = []

    def inspect_launch_job(self, name: str) -> list[tuple[int, int, str]]:
        return list(self.jobs[name])

    def process_running(self, pid: int, creation_time_100ns: int) -> bool:
        return any(
            (pid, creation_time_100ns, executable) in members
            for members in self.jobs.values()
            for _, _, executable in members
        )

    def terminate_exact(self, pid: int, creation_time_100ns: int) -> None:
        for members in self.jobs.values():
            members[:] = [x for x in members if x[:2] != (pid, creation_time_100ns)]

    def close_launch_job(self, name: str) -> None:
        self.closed.add(name)

    def release_process(self, pid: int, creation_time_100ns: int) -> None:
        pass

    def retain_exact(
        self, pid: int, creation_time_100ns: int, executable: str
    ) -> object:
        self.retained.add((pid, creation_time_100ns, executable))
        return object()


def plan(*, python_worker: bool = False) -> wire.PlanLaunchRequest:
    return wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=types.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        child=types.ProcessIdentity(role="controller", generation=str(uuid4())),
        executable="C:\\Python311\\python.exe",
        python_worker=python_worker,
        stop_method="grpc_shutdown",
    )


def confirmation(
    plan: wire.PlanLaunchRequest, *, pid: int = 42, created: int = 1234
) -> wire.ConfirmLaunchRequest:
    return wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=plan.command_id,
        owner=plan.owner,
        child=plan.child,
        pid=pid,
        creation_time_100ns=created,
    )


@pytest.mark.parametrize(
    "role", ["controller", "gui", "acquisition", "visual_stimulus", "tracking"]
)
def test_top_level_self_owner_rejected_before_job_creation(role: str) -> None:
    native = RegistryNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    request = plan()
    request.owner.role = request.child.role = role
    with pytest.raises(LaunchError, match="top-level launch owner is invalid") as error:
        registry.plan(request)
    assert error.value.code == "INVALID_OWNER"
    assert not native.jobs


@pytest.mark.parametrize("os_confirmed", [False, True])
@pytest.mark.parametrize("field", ["endpoint", "host_clock"])
def test_native_confirmation_rejects_python_fields(
    os_confirmed: bool, field: str
) -> None:
    native = RegistryNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    request = plan()
    state = registry.plan(request)
    native.jobs[state.containment_job_name] = [(42, 1234, request.executable)]
    clock = describe_host_clock()
    os_request = confirmation(request)
    if os_confirmed:
        state = registry.confirm(os_request, clock)
        assert registry.confirm(os_request, clock) == state
    invalid = confirmation(request)
    if field == "endpoint":
        invalid.endpoint = "127.0.0.1:50099"
    else:
        invalid.host_clock.SetInParent()
    with pytest.raises(
        LaunchError, match="native helper has no Python endpoint"
    ) as error:
        registry.confirm(invalid, clock)
    assert error.value.code == "INVALID_NATIVE_CONFIRMATION"
    assert registry.refresh(request.command_id).phase == state.phase
    if os_confirmed:
        operational = registry.confirm(confirmation(request), clock)
        assert operational.phase == wire.LAUNCH_PHASE_OPERATIONAL
        assert registry.confirm(os_request, clock) == operational


def test_exact_membership_and_retain_until_cleanup() -> None:
    native = RegistryNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    request = plan()
    state = registry.plan(request)
    assert registry.plan(request) == state
    native.jobs[state.containment_job_name] = [(42, 1234, request.executable)]
    os_confirmed = registry.confirm(confirmation(request), describe_host_clock())
    assert os_confirmed.phase == wire.LAUNCH_PHASE_OS_CONFIRMED
    confirmed = registry.confirm(confirmation(request), describe_host_clock())
    assert confirmed.phase == wire.LAUNCH_PHASE_OPERATIONAL
    with pytest.raises(LaunchError, match="still contains"):
        registry.release(request.command_id, obligations_met=True)
    native.jobs[state.containment_job_name] = []
    with pytest.raises(LaunchError, match="not verified"):
        registry.release(request.command_id, obligations_met=False)
    released = registry.release(request.command_id, obligations_met=True)
    assert released.phase == wire.LAUNCH_PHASE_RELEASED
    assert state.containment_job_name in native.closed


def test_visual_stimulus_ffmpeg_child_must_belong_to_exact_renderer_work() -> None:
    registry = LaunchRegistry(RegistryNative(), 15_000_000_000)
    request = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=_identity("visual_stimulus"),
        child=_identity(VISUAL_STIMULUS_FFMPEG_ROLE),
        executable=EXE,
        stop_method="owner_stdin_eof",
        parent_operation=types.OperationContext(command_id=str(uuid4())),
        work=types.WorkContext(session=types.SessionContext(session_id=str(uuid4()))),
    )
    with pytest.raises(LaunchError, match="exact renderer owner"):
        registry.plan(request)
    request.owner.CopyFrom(_identity("visual_stimulus_renderer"))
    assert registry.plan(request).plan.child == request.child


def test_wrong_creation_time_blocks_instead_of_guessing_pid() -> None:
    native = RegistryNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    request = plan()
    state = registry.plan(request)
    native.jobs[state.containment_job_name] = [(42, 9999, request.executable)]
    with pytest.raises(LaunchError, match="not verified"):
        registry.confirm(confirmation(request), describe_host_clock())
    blocked = registry.refresh(request.command_id)
    assert blocked.phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
    assert blocked.failure.code == "PROCESS_MISMATCH"


def test_creation_failure_cannot_hide_partial_child() -> None:
    native = RegistryNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    request = plan()
    state = registry.plan(request)
    native.jobs[state.containment_job_name] = [(42, 1234, request.executable)]
    failed = confirmation(request)
    failed.creation_failed_without_child = True
    with pytest.raises(LaunchError, match="not empty"):
        registry.confirm(failed, describe_host_clock())
    assert registry.refresh(request.command_id).failure.code == "UNCONFIRMED_CHILD"


def test_python_endpoint_requires_present_clock_fields() -> None:
    native = RegistryNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    request = plan(python_worker=True)
    state = registry.plan(request)
    native.jobs[state.containment_job_name] = [(42, 1234, request.executable)]
    assert (
        registry.confirm(confirmation(request), describe_host_clock()).phase
        == wire.LAUNCH_PHASE_OS_CONFIRMED
    )
    endpoint = confirmation(request)
    endpoint.endpoint = "127.0.0.1:50051"
    endpoint.host_clock.clock_id = describe_host_clock().clock_id
    endpoint.host_clock.implementation = describe_host_clock().implementation
    with pytest.raises(HostClockCompatibilityError, match="missing host clock"):
        registry.confirm(endpoint, describe_host_clock())


def test_exact_confirmation_replay_is_stable_after_operational() -> None:
    native = RegistryNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    request = plan()
    state = registry.plan(request)
    native.jobs[state.containment_job_name] = [(42, 1234, request.executable)]
    first = confirmation(request)
    second = confirmation(request)
    registry.confirm(first, describe_host_clock())
    operational = registry.confirm(second, describe_host_clock())
    assert operational.phase == wire.LAUNCH_PHASE_OPERATIONAL
    assert registry.confirm(second, describe_host_clock()) == operational
    second.pid = 43
    with pytest.raises(LaunchError, match="changed payload"):
        registry.confirm(second, describe_host_clock())


def test_uninspectable_job_is_not_treated_as_empty() -> None:
    native = RegistryNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    request = plan()
    state = registry.plan(request)
    native.jobs[state.containment_job_name] = []

    def inaccessible(name: str) -> list[tuple[int, int, str]]:
        raise PermissionError("job query denied")

    native.inspect_launch_job = inaccessible  # type: ignore[method-assign]
    with pytest.raises(LaunchError, match="could not be verified"):
        registry.release(request.command_id, obligations_met=True)
    assert state.containment_job_name not in native.closed


def test_registered_child_remains_valid_with_nested_descendant() -> None:
    native = RegistryNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    request = plan()
    state = registry.plan(request)
    native.jobs[state.containment_job_name] = [(42, 1234, request.executable)]
    os_stage = confirmation(request)
    registry.confirm(os_stage, describe_host_clock())
    operational_stage = confirmation(request)
    registry.confirm(operational_stage, describe_host_clock())
    assert (42, 1234, request.executable) in native.retained
    native.jobs[state.containment_job_name].append(
        (43, 1235, "C:\\Python311\\worker.exe")
    )
    assert registry.refresh(request.command_id).phase == wire.LAUNCH_PHASE_OPERATIONAL
    assert (
        registry.confirm(operational_stage, describe_host_clock()).phase
        == wire.LAUNCH_PHASE_OPERATIONAL
    )
    native.jobs[state.containment_job_name] = [(43, 1235, "C:\\Python311\\worker.exe")]
    assert (
        registry.refresh(request.command_id).phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
    )
    with pytest.raises(LaunchError, match="still contains"):
        registry.release(request.command_id, obligations_met=True)
