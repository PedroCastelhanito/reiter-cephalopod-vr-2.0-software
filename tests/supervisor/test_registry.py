"""Exact launch identity, containment, capacity and idempotent release."""

from __future__ import annotations

from uuid import uuid4

import pytest

from cephvr.acquisition.identity import FFMPEG_ROLE
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import (
    HostClockCompatibilityError,
    describe_host_clock,
)
from cephvr.supervisor.registry import LaunchError, LaunchRegistry
from cephvr.visual_stimulus.identity import FFMPEG_ROLE as VISUAL_STIMULUS_FFMPEG_ROLE
from tests.supervisor.support import Native

from .support import EXE, WORK, WORKER_ROLE, _identity, _launch

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


def _gui_launch(
    registry: LaunchRegistry, native: Native, *, pid: int = 42
) -> wire.LaunchState:
    owner = _identity("supervisor")
    child = _identity("gui")
    plan = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=owner,
        child=child,
        executable=EXE,
        python_worker=True,
        stop_method="grpc_shutdown",
    )
    state = registry.plan(plan)
    native.jobs[state.containment_job_name] = [(pid, pid + 100, EXE)]
    registry.confirm(
        wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=plan.command_id,
            owner=owner,
            child=child,
            pid=pid,
            creation_time_100ns=pid + 100,
        ),
        describe_host_clock(),
    )
    return registry.confirm(
        wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=plan.command_id,
            owner=owner,
            child=child,
            pid=pid,
            creation_time_100ns=pid + 100,
            endpoint=f"127.0.0.1:{50000 + pid}",
            host_clock=types.HostClockDescriptor(
                clock_id=describe_host_clock().clock_id,
                implementation=describe_host_clock().implementation,
                monotonic=describe_host_clock().monotonic,
                adjustable=describe_host_clock().adjustable,
                resolution_s=describe_host_clock().resolution_s,
            ),
        ),
        describe_host_clock(),
    )


def test_gui_release_requires_empty_native_job_and_is_idempotent() -> None:
    native = Native()
    registry = LaunchRegistry(native, 15_000_000_000)
    released: list[wire.LaunchState] = []
    registry.on_release(released.append)
    alive = _gui_launch(registry, native)
    assert registry.release_gui_if_empty(alive.plan.command_id).phase == alive.phase
    assert not released

    native.jobs[alive.containment_job_name] = []
    first = registry.release_gui_if_empty(alive.plan.command_id)
    again = registry.release_gui_if_empty(alive.plan.command_id)
    assert first.phase == again.phase == wire.LAUNCH_PHASE_RELEASED
    assert len(released) == 1


def test_gui_release_keeps_unknown_native_membership_unconfirmed() -> None:
    native = Native()
    registry = LaunchRegistry(native, 15_000_000_000)
    state = _gui_launch(registry, native)
    del native.jobs[state.containment_job_name]
    with pytest.raises(LaunchError, match="membership could not be verified"):
        registry.release_gui_if_empty(state.plan.command_id)
    assert (
        registry._entries[state.plan.command_id].state.phase
        != wire.LAUNCH_PHASE_RELEASED
    )


def test_capacity_preserves_replay_through_work_finalization_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = Native()
    now = 100
    monkeypatch.setattr("cephvr.supervisor.registry.host_time_ns", lambda: now)
    registry = LaunchRegistry(native, 15_000_000_000, max_launches=1, retention_ns=100)
    owner = _identity("acquisition")
    state = _launch(registry, native, owner, _identity(WORKER_ROLE), 1, python=True)
    native.jobs[state.containment_job_name] = []
    released = registry.release(state.plan.command_id, obligations_met=True)
    assert registry.plan(state.plan) == released

    now = 1_000
    next_request = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=owner,
        child=_identity(WORKER_ROLE),
        executable=EXE,
        python_worker=True,
        stop_method="grpc_shutdown",
    )
    with pytest.raises(LaunchError, match="capacity"):
        registry.plan(next_request)

    # Released work remains pinned until the exact session is finalized.
    now = 2_000
    registry.finalize_work(WORK.session.session_id, finalized_ns=now)
    now = 2_099
    with pytest.raises(LaunchError, match="capacity"):
        registry.plan(next_request)
    now = 2_101
    admitted = registry.plan(next_request)
    assert admitted.plan.command_id == next_request.command_id
    assert state.plan.command_id not in registry._entries

    # Finalization may precede exact worker exit; the retention window starts
    # only once both finalization and release have happened.
    later = LaunchRegistry(native, 15_000_000_000, max_launches=1, retention_ns=100)
    now = 3_000
    delayed_release = _launch(
        later, native, owner, _identity(WORKER_ROLE), 10, python=True
    )
    later.finalize_work(WORK.session.session_id, finalized_ns=3_100)
    now = 3_200
    native.jobs[delayed_release.containment_job_name] = []
    later.release(delayed_release.plan.command_id, obligations_met=True)
    now = 3_299
    with pytest.raises(LaunchError, match="capacity"):
        later.plan(next_request)
    now = 3_301
    assert later.plan(next_request).plan.command_id == next_request.command_id


def _camera_cleanup_proof(
    worker: wire.LaunchState,
    *,
    include_resource: bool = True,
    output_closure: int | None = None,
) -> wire.AcquisitionWorkerCleanupProof:
    source = acq.WorkerContext(
        worker=worker.plan.child,
        owner=worker.plan.owner,
        work=WORK,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    cleanup_id = str(uuid4())
    operation = acq.WorkerOperationReport(
        source=source,
        operation=types.OperationState(
            context=types.OperationContext(command_id=cleanup_id),
            command="Cleanup",
            work=WORK,
            complete=True,
            succeeded=True,
        ),
    )
    cleanup = acq.WorkerLifecycleEvidence(
        source=source,
        operation=types.OperationContext(command_id=cleanup_id),
        state_revision=1,
    )
    cleanup.cleanup.SetInParent()
    if include_resource:
        cleanup.cleanup.resources.add(resource="camera-device", released=True)
    if output_closure is not None:
        cleanup.cleanup.outputs.add(output_key="camera-video", closure=output_closure)
    return wire.AcquisitionWorkerCleanupProof(operation=operation, cleanup=cleanup)


def test_camera_release_requires_exact_retained_cleanup_and_empty_job() -> None:
    native = Native()
    registry = LaunchRegistry(native, 15_000_000_000)
    worker = _launch(
        registry,
        native,
        _identity("acquisition"),
        _identity(WORKER_ROLE),
        1,
        python=True,
    )
    request = wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=worker.plan.command_id,
        owner=worker.plan.owner,
        child=worker.plan.child,
        pid=1,
        creation_time_100ns=101,
        acquisition_worker_cleanup=_camera_cleanup_proof(worker),
    )
    acknowledged = registry.confirm(request, describe_host_clock())
    assert acknowledged.phase == wire.LAUNCH_PHASE_OPERATIONAL
    assert registry.camera_cleanup_acknowledged(worker.plan.command_id)
    assert (
        registry.confirm(request, describe_host_clock()).phase
        == wire.LAUNCH_PHASE_OPERATIONAL
    )
    changed_proof = wire.ConfirmLaunchRequest.FromString(request.SerializeToString())
    changed_proof.command_id = str(uuid4())
    changed_proof.acquisition_worker_cleanup.cleanup.state_revision += 1
    with pytest.raises(LaunchError, match="proof changed"):
        registry.confirm(changed_proof, describe_host_clock())
    native.jobs[worker.containment_job_name] = []
    assert (
        registry.refresh(worker.plan.command_id).phase
        == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
    )
    released = registry.confirm(request, describe_host_clock())
    assert released.phase == wire.LAUNCH_PHASE_RELEASED
    assert (
        registry.confirm(request, describe_host_clock()).phase
        == wire.LAUNCH_PHASE_RELEASED
    )


@pytest.mark.parametrize("include_resource", [False, True])
def test_camera_release_rejects_incomplete_proof_or_live_job(
    include_resource: bool,
) -> None:
    native = Native()
    registry = LaunchRegistry(native, 15_000_000_000)
    worker = _launch(
        registry,
        native,
        _identity("acquisition"),
        _identity(WORKER_ROLE),
        2,
        python=True,
    )
    if include_resource:
        native.jobs[worker.containment_job_name] = [(2, 102, worker.plan.executable)]
    else:
        native.jobs[worker.containment_job_name] = []
    if include_resource:
        registry._block(
            registry._entries[worker.plan.command_id],
            "TEST_RETIRED",
            "exercise live-job release rejection",
        )
    assert (
        registry.refresh(worker.plan.command_id).phase
        == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
    )
    request = wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=worker.plan.command_id,
        owner=worker.plan.owner,
        child=worker.plan.child,
        pid=2,
        creation_time_100ns=102,
        acquisition_worker_cleanup=_camera_cleanup_proof(
            worker, include_resource=include_resource
        ),
    )
    with pytest.raises(LaunchError):
        registry.confirm(request, describe_host_clock())
    assert (
        registry._entries[worker.plan.command_id].state.phase
        == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
    )


def test_camera_release_accepts_failed_output_cleanup_but_rejects_unknown_closure() -> (
    None
):
    for closure, accepted in (
        (types.OUTPUT_CLOSURE_FAILED, True),
        (types.OUTPUT_CLOSURE_UNCONFIRMED, False),
    ):
        native = Native()
        registry = LaunchRegistry(native, 15_000_000_000)
        worker = _launch(
            registry,
            native,
            _identity("acquisition"),
            _identity(WORKER_ROLE),
            3,
            python=True,
        )
        request = wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=worker.plan.command_id,
            owner=worker.plan.owner,
            child=worker.plan.child,
            pid=3,
            creation_time_100ns=103,
            acquisition_worker_cleanup=_camera_cleanup_proof(
                worker, include_resource=False, output_closure=closure
            ),
        )
        if accepted:
            assert (
                registry.confirm(request, describe_host_clock()).phase
                == wire.LAUNCH_PHASE_OPERATIONAL
            )
            native.jobs[worker.containment_job_name] = []
            registry.refresh(worker.plan.command_id)
            assert (
                registry.confirm(request, describe_host_clock()).phase
                == wire.LAUNCH_PHASE_RELEASED
            )
        else:
            with pytest.raises(LaunchError, match="incomplete or mismatched"):
                registry.confirm(request, describe_host_clock())


def test_camera_process_exit_without_cleanup_proof_does_not_release() -> None:
    native = Native()
    registry = LaunchRegistry(native, 15_000_000_000)
    worker = _launch(
        registry,
        native,
        _identity("acquisition"),
        _identity(WORKER_ROLE),
        4,
        python=True,
    )
    native.jobs[worker.containment_job_name] = []
    registry.refresh(worker.plan.command_id)
    request = wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=worker.plan.command_id,
        owner=worker.plan.owner,
        child=worker.plan.child,
        pid=4,
        creation_time_100ns=104,
    )
    with pytest.raises(LaunchError, match="requires reconciliation"):
        registry.confirm(request, describe_host_clock())
    assert (
        registry._entries[worker.plan.command_id].state.phase
        == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
    )


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


@pytest.mark.parametrize(
    "role", ["visual_stimulus_ffmpeg", "visual_stimulus_ffmpeg_probe"]
)
def test_renderer_eof_helper_exit_retains_cleanup_without_process_fault(role):
    native = RegistryNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    request = plan()
    request.owner.role = "visual_stimulus_renderer"
    request.child.role = role
    request.stop_method = "owner_stdin_eof"
    request.work.session.CopyFrom(
        types.SessionContext(
            controller_generation=str(uuid4()), session_id=str(uuid4())
        )
    )
    request.parent_operation.command_id = str(uuid4())
    state = registry.plan(request)
    native.jobs[state.containment_job_name] = [(42, 1234, request.executable)]
    registry.confirm(confirmation(request), describe_host_clock())
    registry.confirm(confirmation(request), describe_host_clock())
    native.jobs[state.containment_job_name] = []
    observed = registry.refresh(request.command_id)
    assert observed.phase == wire.LAUNCH_PHASE_OPERATIONAL
    assert not observed.HasField("failure")
    with pytest.raises(LaunchError, match="not verified"):
        registry.release(request.command_id, obligations_met=False)
    assert (
        registry.release(request.command_id, obligations_met=True).phase
        == wire.LAUNCH_PHASE_RELEASED
    )


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


@pytest.mark.parametrize("confirmed", [False, True])
def test_firmware_cleanup_is_exact_owner_scoped_and_requires_empty_job(
    confirmed,
) -> None:
    from cephvr.controller.microcontroller.identity import FIRMWARE_UPLOAD_ROLE

    native = Native()
    registry = LaunchRegistry(native, 15_000_000_000)
    owner, child = _identity("controller"), _identity(FIRMWARE_UPLOAD_ROLE)
    plan = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=owner,
        child=child,
        executable=EXE,
        stop_method="owner_job_terminate",
        parent_operation=types.OperationContext(command_id=str(uuid4())),
    )
    state = registry.plan(plan)
    receipt = wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=plan.command_id,
        owner=owner,
        child=child,
        native_cleanup_complete=True,
    )
    if confirmed:
        native.jobs[state.containment_job_name] = [(42, 142, EXE)]
        registry.confirm(
            wire.ConfirmLaunchRequest(
                command_id=str(uuid4()),
                launch_command_id=plan.command_id,
                owner=owner,
                child=child,
                pid=42,
                creation_time_100ns=142,
            ),
            describe_host_clock(),
        )
        receipt.pid, receipt.creation_time_100ns = 42, 142
    else:
        native.jobs[state.containment_job_name] = [(42, 142, EXE)]
    with pytest.raises(LaunchError, match="job still contains"):
        registry.confirm(receipt, describe_host_clock())
    if confirmed:
        wrong = wire.ConfirmLaunchRequest.FromString(receipt.SerializeToString())
        wrong.creation_time_100ns = 143
        with pytest.raises(LaunchError, match="exact child"):
            registry.confirm(wrong, describe_host_clock())
    native.jobs[state.containment_job_name] = []
    assert registry.refresh(plan.command_id).phase != wire.LAUNCH_PHASE_CLEANUP_REQUIRED
    result = registry.confirm(receipt, describe_host_clock())
    assert result.phase == wire.LAUNCH_PHASE_RELEASED
    assert registry.confirm(receipt, describe_host_clock()) == result
    invalid = wire.PlanLaunchRequest.FromString(plan.SerializeToString())
    invalid.command_id = str(uuid4())
    invalid.owner.CopyFrom(_identity("acquisition"))
    with pytest.raises(LaunchError, match="Configuration owner"):
        registry.plan(invalid)
