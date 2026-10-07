"""Launcher registration, shutdown backstops and verified process absence."""

from __future__ import annotations

import queue
import time
from uuid import uuid4

import pytest

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control_types
from cephvr.launcher.decisions import (
    LOST_KEY,
    MAX_LINE_BYTES,
    LauncherDecisions,
    parse_notification_line,
)
from cephvr.launcher.entrypoint import launcher_command
from cephvr.launcher.gui_relaunch import (
    GuiLaunchRegistration,
    GuiRelaunchCoordinator,
    GuiRelaunchDispatcher,
    _exact_gui_released,
)
from cephvr.launcher.main import _retain_until_empty
from cephvr.platform.windows.jobs import WindowsLaunchError
from cephvr.shared.clock import host_time_ns

SUP = "s" * 8


CTL = "c" * 8


S = 1_000_000_000


def _decisions() -> LauncherDecisions:
    return LauncherDecisions(
        supervisor_generation=SUP,
        controller_generation=CTL,
        backstop_ns=90 * S,
        registration_window_ns=15 * S,
        launched_ns=0,
    )


def _register(pid: int = 7, created: int = 9, channel: str = "supervisor") -> dict:
    return {
        "kind": "register_controller",
        "_channel": channel,
        "supervisor_generation": SUP,
        "controller_generation": CTL,
        "pid": pid,
        "creation_time_100ns": created,
    }


def test_registration_window_starts_at_bootstrap_completion() -> None:
    d = _decisions()
    d.bootstrap_finished(40 * S, ok=True)  # slow bootstrap; window restarts
    d.tick(50 * S)
    assert d.shutdown_deadline_ns is None
    assert d.on_register_controller(54 * S, _register()) == (7, 9)


def test_late_registration_is_refused_and_backstop_stays_armed() -> None:
    d = _decisions()
    d.bootstrap_finished(1 * S, ok=True)
    d.tick(17 * S)
    assert d.shutdown_deadline_ns == 17 * S + 90 * S
    assert d.on_register_controller(17 * S, _register()) is None
    assert d.controller is None


def test_bootstrap_failure_arms_backstop() -> None:
    d = _decisions()
    d.bootstrap_finished(2 * S, ok=False)
    assert d.shutdown_deadline_ns == 92 * S


def test_hung_bootstrap_is_bounded_by_the_same_window() -> None:
    d = _decisions()
    d.tick(16 * S)
    assert d.shutdown_deadline_ns == 106 * S


def test_registration_requires_supervisor_channel_and_generations() -> None:
    d = _decisions()
    assert d.on_register_controller(S, _register(channel="controller")) is None
    bad = _register()
    bad["controller_generation"] = "other"
    assert d.on_register_controller(S, bad) is None


def test_second_different_controller_arms_backstop() -> None:
    d = _decisions()
    d.controller_acknowledged(7, 9)
    assert d.on_register_controller(2 * S, _register()) is None
    assert d.shutdown_deadline_ns is None
    assert d.on_register_controller(2 * S, _register(pid=8)) is None
    assert d.shutdown_deadline_ns == 92 * S


def test_supervisor_channel_loss_arms_but_controller_loss_only_records() -> None:
    d = _decisions()
    d.on_channel_lost(S, "controller", "malformed JSON")
    assert d.shutdown_deadline_ns is None
    assert d.lost_channels == {"controller": "malformed JSON"}
    d.on_channel_lost(2 * S, "supervisor", "eof")
    assert d.shutdown_deadline_ns == 92 * S


def test_shutdown_deadline_is_min_of_claim_and_backstop() -> None:
    d = _decisions()
    d.on_shutdown(
        S,
        {
            "_channel": "supervisor",
            "supervisor_generation": SUP,
            "deadline_monotonic_ns": 10 * S,
        },
    )
    assert d.shutdown_deadline_ns == 10 * S
    d.on_shutdown(
        S,
        {
            "_channel": "controller",
            "supervisor_generation": SUP,
            "controller_generation": "x",
        },
    )
    assert d.shutdown_deadline_ns == 10 * S


def test_parse_reports_each_violation_and_strips_reserved_key() -> None:
    assert parse_notification_line(b"") == "eof"
    assert isinstance(parse_notification_line(b"x" * (MAX_LINE_BYTES + 1)), str)
    assert isinstance(parse_notification_line(b'{"a":1}'), str)  # unterminated
    assert isinstance(parse_notification_line(b"not json\n"), str)
    assert isinstance(parse_notification_line(b"[1]\n"), str)
    parsed = parse_notification_line(b'{"kind":"x","' + LOST_KEY.encode() + b'":"y"}\n')
    assert parsed == {"kind": "x"}


def test_gui_relaunch_requires_exact_registered_release() -> None:
    supervisor_generation = str(uuid4())
    generation = str(uuid4())
    command_id = str(uuid4())
    current = GuiLaunchRegistration(
        supervisor_generation, generation, command_id, 42, 99
    )
    state = wire.LaunchState(
        plan=wire.PlanLaunchRequest(
            command_id=current.launch_command_id,
            owner=control_types.ProcessIdentity(
                role="supervisor", generation=supervisor_generation
            ),
            child=control_types.ProcessIdentity(
                role="gui", generation=current.generation
            ),
        ),
        phase=wire.LAUNCH_PHASE_RELEASED,
        pid=current.pid,
        creation_time_100ns=current.creation_time_100ns,
    )
    assert _exact_gui_released(state, current)
    assert not _exact_gui_released(
        state,
        GuiLaunchRegistration(supervisor_generation, str(uuid4()), command_id, 42, 99),
    )
    assert not _exact_gui_released(
        state,
        GuiLaunchRegistration(supervisor_generation, generation, command_id, 42, 100),
    )
    state.phase = wire.LAUNCH_PHASE_CLEANUP_REQUIRED
    assert not _exact_gui_released(state, current)


def test_gui_registration_notification_is_closed_and_identity_bound() -> None:
    supervisor_generation = str(uuid4())
    generation = str(uuid4())
    command_id = str(uuid4())
    note = {
        "kind": "register_gui_launch",
        "_channel": "supervisor",
        "supervisor_generation": supervisor_generation,
        "child_generation": generation,
        "launch_command_id": command_id,
        "pid": 42,
        "creation_time_100ns": 99,
    }
    assert GuiLaunchRegistration.from_notification(note).pid == 42
    with pytest.raises(WindowsLaunchError, match="invalid GUI registration"):
        GuiLaunchRegistration.from_notification({**note, "unexpected": True})


def test_uncertain_gui_relaunch_retains_identity_and_only_reconciles() -> None:
    supervisor_generation = str(uuid4())
    current = GuiLaunchRegistration(
        supervisor_generation, str(uuid4()), str(uuid4()), 41, 77
    )
    coordinator = GuiRelaunchCoordinator()
    assert coordinator.registered(current)

    launch = coordinator.request(deadline_ns=20_000, now_ns=10)
    assert launch is not None and not launch.reconcile_only
    assert launch.attempt.previous == current
    assert not coordinator.completed(launch, None)
    assert coordinator.attempt == launch.attempt

    query = coordinator.request(deadline_ns=20_000, now_ns=15)
    assert query is not None and query.reconcile_only
    assert query.attempt == launch.attempt
    assert not coordinator.completed(query, None)

    expired_query = coordinator.request(deadline_ns=30_000, now_ns=21_000)
    assert expired_query is not None and expired_query.reconcile_only
    assert expired_query.attempt.deadline_ns == launch.attempt.deadline_ns

    unrelated = GuiLaunchRegistration(
        supervisor_generation, str(uuid4()), str(uuid4()), 42, 78
    )
    assert not coordinator.registered(unrelated)
    successor = GuiLaunchRegistration(
        supervisor_generation,
        launch.attempt.child_generation,
        launch.attempt.launch_command_id,
        43,
        79,
    )
    assert coordinator.registered(successor)
    assert coordinator.current == successor
    assert coordinator.attempt is None
    assert not coordinator.completed(query, successor)

    next_launch = coordinator.request(deadline_ns=20_000, now_ns=16)
    assert next_launch is not None and not next_launch.reconcile_only
    assert next_launch.attempt.previous == successor
    coordinator.shutdown()
    assert coordinator.request(deadline_ns=20_000, now_ns=17) is None


def test_gui_relaunch_deadline_expires_before_attempt_creation() -> None:
    current = GuiLaunchRegistration(str(uuid4()), str(uuid4()), str(uuid4()), 42, 99)
    coordinator = GuiRelaunchCoordinator()
    assert coordinator.registered(current)
    assert coordinator.request(deadline_ns=10, now_ns=10) is None


def test_gui_relaunch_dispatch_keeps_launcher_loop_live_during_rpc_and_shutdown() -> (
    None
):
    from threading import Event

    supervisor = str(uuid4())
    current = GuiLaunchRegistration(supervisor, str(uuid4()), str(uuid4()), 42, 99)
    coordinator = GuiRelaunchCoordinator()
    assert coordinator.registered(current)
    rpc_entered = Event()
    release_rpc = Event()

    def delayed_rpc(_work):
        rpc_entered.set()
        assert release_rpc.wait(2)
        return None

    dispatcher = GuiRelaunchDispatcher(coordinator, delayed_rpc)
    work = dispatcher.request(deadline_ns=20_000, now_ns=10)
    assert work is not None
    try:
        assert rpc_entered.wait(1)
        # This is the launcher loop's next safety iteration while the RPC is
        # still blocked: process shutdown/loss evidence and stop future starts.
        safety_events = queue.Queue()
        safety_events.put({"kind": "channel_lost", "_channel": "controller"})
        assert safety_events.get_nowait()["kind"] == "channel_lost"
        dispatcher.shutdown()
        assert dispatcher.request(deadline_ns=30_000, now_ns=20) is None
        assert dispatcher.poll() == ()
    finally:
        release_rpc.set()
    deadline = time.monotonic() + 1
    results = ()
    while not results and time.monotonic() < deadline:
        results = dispatcher.poll()
        time.sleep(0.001)
    assert results[0].work == work
    assert coordinator.attempt == work.attempt
    assert coordinator.current == current


def test_gui_relaunch_definite_pre_admission_failure_allows_fresh_explicit_attempt() -> (
    None
):
    supervisor = str(uuid4())
    current = GuiLaunchRegistration(supervisor, str(uuid4()), str(uuid4()), 42, 99)
    coordinator = GuiRelaunchCoordinator()
    assert coordinator.registered(current)
    first = coordinator.request(deadline_ns=20_000, now_ns=10)
    assert first is not None and not first.reconcile_only
    assert not coordinator.completed(first, None, definite_failure=True)
    second = coordinator.request(deadline_ns=30_000, now_ns=20)
    assert second is not None and not second.reconcile_only
    assert second.attempt.launch_command_id != first.attempt.launch_command_id


def test_gui_relaunch_post_submission_failure_keeps_exact_attempt_for_query() -> None:
    from cephvr.platform.windows.jobs import WindowsLaunchError

    supervisor = str(uuid4())
    current = GuiLaunchRegistration(supervisor, str(uuid4()), str(uuid4()), 42, 99)
    coordinator = GuiRelaunchCoordinator()
    assert coordinator.registered(current)

    def lost_reply(_work):
        raise WindowsLaunchError("reply lost after PlanLaunch submission")

    dispatcher = GuiRelaunchDispatcher(coordinator, lost_reply)
    work = dispatcher.request(deadline_ns=20_000, now_ns=10)
    assert work is not None and not work.reconcile_only
    deadline = time.monotonic() + 1
    results = ()
    while not results and time.monotonic() < deadline:
        results = dispatcher.poll()
        time.sleep(0.001)
    assert results and not results[0].definite_failure
    assert coordinator.attempt == work.attempt
    query = coordinator.request(deadline_ns=30_000, now_ns=20)
    assert query is not None and query.reconcile_only
    assert query.attempt == work.attempt


def test_expired_uncertain_relaunch_uses_bounded_read_only_reconciliation(
    monkeypatch,
) -> None:
    from cephvr.launcher import gui_relaunch

    supervisor_generation = str(uuid4())
    attempt = gui_relaunch.GuiRelaunchAttempt.create(
        GuiLaunchRegistration(
            supervisor_generation, str(uuid4()), str(uuid4()), 42, 99
        ),
        deadline_ns=1,
    )
    expected = GuiLaunchRegistration(
        supervisor_generation,
        attempt.child_generation,
        attempt.launch_command_id,
        43,
        100,
    )
    state = wire.LaunchState(
        plan=wire.PlanLaunchRequest(
            command_id=attempt.launch_command_id,
            owner=control_types.ProcessIdentity(
                role="supervisor", generation=supervisor_generation
            ),
            child=control_types.ProcessIdentity(
                role="gui", generation=attempt.child_generation
            ),
        ),
        phase=wire.LAUNCH_PHASE_OPERATIONAL,
        pid=expected.pid,
        creation_time_100ns=expected.creation_time_100ns,
    )
    calls = []

    class Channel:
        def close(self):
            pass

    class Stub:
        def __init__(self, _channel):
            pass

        def GetLaunchState(self, query, *, metadata, timeout):
            calls.append((query, metadata, timeout))
            return state

        def PlanLaunch(self, *_args, **_kwargs):
            raise AssertionError("reconciliation must never re-plan")

    monkeypatch.setattr(gui_relaunch.grpc, "insecure_channel", lambda _: Channel())
    monkeypatch.setattr(gui_relaunch.services_pb2_grpc, "SupervisorServiceStub", Stub)
    assert (
        gui_relaunch.reconcile_relaunch(
            supervisor_port=1234,
            supervisor=control_types.ProcessIdentity(
                role="supervisor", generation=supervisor_generation
            ),
            supervisor_token="token",
            attempt=attempt,
        )
        == expected
    )
    assert len(calls) == 1
    query, metadata, timeout = calls[0]
    assert query.launch_command_id == attempt.launch_command_id
    assert timeout == 2.0
    assert not any(key == "x-cephvr-deadline-monotonic-ns" for key, _ in metadata)


def test_exact_released_reconciliation_retires_attempt_for_next_explicit_click(
    monkeypatch,
) -> None:
    from cephvr.launcher import gui_relaunch

    supervisor_generation = str(uuid4())
    current = GuiLaunchRegistration(
        supervisor_generation, str(uuid4()), str(uuid4()), 42, 99
    )
    coordinator = GuiRelaunchCoordinator()
    assert coordinator.registered(current)
    launch = coordinator.request(deadline_ns=100, now_ns=10)
    assert launch is not None
    assert not coordinator.completed(launch, None)
    query = coordinator.request(deadline_ns=1_000, now_ns=101)
    assert query is not None and query.reconcile_only

    state = wire.LaunchState(
        plan=wire.PlanLaunchRequest(
            command_id=query.attempt.launch_command_id,
            owner=control_types.ProcessIdentity(
                role="supervisor", generation=supervisor_generation
            ),
            child=control_types.ProcessIdentity(
                role="gui", generation=query.attempt.child_generation
            ),
        ),
        phase=wire.LAUNCH_PHASE_RELEASED,
        pid=43,
        creation_time_100ns=100,
    )

    class Channel:
        def close(self):
            pass

    class Stub:
        def __init__(self, _channel):
            pass

        def GetLaunchState(self, _query, **_kwargs):
            return state

    monkeypatch.setattr(gui_relaunch.grpc, "insecure_channel", lambda _: Channel())
    monkeypatch.setattr(gui_relaunch.services_pb2_grpc, "SupervisorServiceStub", Stub)
    released = gui_relaunch.reconcile_relaunch(
        supervisor_port=1234,
        supervisor=control_types.ProcessIdentity(
            role="supervisor", generation=supervisor_generation
        ),
        supervisor_token="token",
        attempt=query.attempt,
    )
    assert released == gui_relaunch.GuiRelaunchReleased(query.attempt)
    assert not coordinator.completed(
        query,
        None,
        terminal_released=isinstance(released, gui_relaunch.GuiRelaunchReleased),
    )
    assert coordinator.attempt is None

    next_click = coordinator.request(deadline_ns=2_000, now_ns=102)
    assert next_click is not None and not next_click.reconcile_only
    assert next_click.attempt.launch_command_id != query.attempt.launch_command_id

    state.plan.command_id = str(uuid4())
    mismatched = gui_relaunch.reconcile_relaunch(
        supervisor_port=1234,
        supervisor=control_types.ProcessIdentity(
            role="supervisor", generation=supervisor_generation
        ),
        supervisor_token="token",
        attempt=query.attempt,
    )
    assert mismatched is None


def test_rejected_plan_with_cleanup_obligation_keeps_exact_relaunch_identity(
    monkeypatch,
) -> None:
    from cephvr.launcher import gui_relaunch

    supervisor_generation = str(uuid4())
    previous = GuiLaunchRegistration(
        supervisor_generation, str(uuid4()), str(uuid4()), 42, 99
    )
    coordinator = GuiRelaunchCoordinator()
    assert coordinator.registered(previous)
    work = coordinator.request(
        deadline_ns=host_time_ns() + 10_000_000_000, now_ns=host_time_ns()
    )
    assert work is not None
    previous_state = wire.LaunchState(
        plan=wire.PlanLaunchRequest(
            command_id=previous.launch_command_id,
            owner=control_types.ProcessIdentity(
                role="supervisor", generation=supervisor_generation
            ),
            child=control_types.ProcessIdentity(
                role="gui", generation=previous.generation
            ),
        ),
        phase=wire.LAUNCH_PHASE_RELEASED,
        pid=previous.pid,
        creation_time_100ns=previous.creation_time_100ns,
    )
    retained_state = wire.LaunchState(
        plan=wire.PlanLaunchRequest(
            command_id=work.attempt.launch_command_id,
            owner=control_types.ProcessIdentity(
                role="supervisor", generation=supervisor_generation
            ),
            child=control_types.ProcessIdentity(
                role="gui", generation=work.attempt.child_generation
            ),
        ),
        phase=wire.LAUNCH_PHASE_CLEANUP_REQUIRED,
        pid=43,
        creation_time_100ns=100,
    )
    plans = []

    class Channel:
        def close(self):
            pass

    class Stub:
        def __init__(self, _channel):
            pass

        def GetLaunchState(self, query, **_kwargs):
            assert query.launch_command_id == previous.launch_command_id
            return previous_state

        def PlanLaunch(self, request, **_kwargs):
            plans.append(request.command_id)
            return wire.LaunchReceipt(
                admission=control_types.CommandAdmission(
                    result=control_types.COMMAND_RESULT_REJECTED,
                    failure=control_types.Failure(
                        code="PROCESS_MISMATCH", message="cleanup remains required"
                    ),
                ),
                state=retained_state,
            )

    monkeypatch.setattr(gui_relaunch.grpc, "insecure_channel", lambda _: Channel())
    monkeypatch.setattr(gui_relaunch.services_pb2_grpc, "SupervisorServiceStub", Stub)
    dispatcher = GuiRelaunchDispatcher(
        coordinator,
        lambda selected: gui_relaunch.request_relaunch(
            supervisor_port=1234,
            supervisor=control_types.ProcessIdentity(
                role="supervisor", generation=supervisor_generation
            ),
            supervisor_token="secret",
            interpreter="python.exe",
            attempt=selected.attempt,
        ),
    )
    dispatcher.start(work)
    deadline = time.monotonic() + 1
    results = ()
    while not results and time.monotonic() < deadline:
        results = dispatcher.poll()
        time.sleep(0.001)
    assert results and not results[0].definite_failure
    assert plans == [work.attempt.launch_command_id]
    assert coordinator.attempt == work.attempt
    next_work = coordinator.request(
        deadline_ns=host_time_ns() + 10_000_000_000, now_ns=host_time_ns()
    )
    assert next_work is not None and next_work.reconcile_only
    assert next_work.attempt == work.attempt


def test_project_launcher_forwards_explicit_gui_relaunch_flag(tmp_path) -> None:
    root = tmp_path / "repo"
    python = root / ".venv" / "Scripts" / "python.exe"
    assert launcher_command(root, python, reopen_gui=True) == [
        str(python),
        "-m",
        "cephvr.launcher.main",
        "--reopen-gui",
    ]
    assert "--reopen-gui" not in launcher_command(root, python, reopen_gui=False)


def test_runtime_gui_script_bootstraps_from_outside_repo_without_installed_package(
    tmp_path,
) -> None:
    import os
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "start_runtime_gui.py"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--reopen-gui" in result.stdout


class Native:
    def __init__(self) -> None:
        self.terminated = False
        self.queries = 0

    def inspect_launch_job(self, name: str) -> list[tuple[int, int, str]]:
        assert name == "application"
        self.queries += 1
        if self.queries == 1:
            raise WindowsLaunchError("transient query failure")
        return [] if self.terminated else [(42, 10, "C:\\Python311\\python.exe")]

    def terminate_job(self, name: str) -> None:
        assert name == "application"
        self.terminated = True


def test_guard_waits_for_verified_absence_after_unknown_membership() -> None:
    native = Native()
    _retain_until_empty(native, "application", host_time_ns() - 1, 1_000_000_000)  # type: ignore[arg-type]
    assert native.terminated
    assert native.queries >= 2


class ReplacementEvent:
    def __init__(self) -> None:
        self.signaled = False
        self.closed = False

    def __enter__(self) -> ReplacementEvent:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def set(self) -> None:
        self.signaled = True


def _replacement_fixture(monkeypatch, tmp_path):
    import uuid
    from types import SimpleNamespace

    from cephvr.launcher import replacement
    from cephvr.platform.windows.guard import InstanceAlreadyRunning

    record = replacement.LauncherEndpoint(
        str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()), S
    )
    event = ReplacementEvent()
    requests = []
    receipt = SimpleNamespace(supervisor_generation=record.supervisor_generation)

    def guard(role):
        assert role == "application"
        requests.append(role)
        if not event.signaled:
            raise InstanceAlreadyRunning("application instance already running")
        return "new guard"

    monkeypatch.setattr(replacement, "SingleInstanceGuard", guard)
    monkeypatch.setattr(replacement.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(replacement, "_existing_endpoint", lambda root: record)
    monkeypatch.setattr(replacement.AutoResetEvent, "open", lambda *args: event)
    monkeypatch.setattr(
        replacement,
        "RecoveryStore",
        lambda root: SimpleNamespace(read_exit_receipt=lambda generation: receipt),
    )
    return replacement, event, requests, record


def test_duplicate_decline_preserves_existing_runtime(monkeypatch, tmp_path) -> None:
    import pytest

    replacement, event, requests, _ = _replacement_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "N")
    with pytest.raises(replacement.ReplacementDeclined, match="left running"):
        replacement.acquire_application_guard(tmp_path)
    assert not event.signaled
    assert event.closed
    assert len(requests) == 1


def test_duplicate_yes_waits_for_exact_exit_then_acquires(
    monkeypatch, tmp_path
) -> None:
    replacement, event, requests, _ = _replacement_fixture(monkeypatch, tmp_path)
    answers = iter(("wrong", " y "))
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert replacement.acquire_application_guard(tmp_path) == "new guard"
    assert event.signaled and event.closed
    assert len(requests) == 2


def test_duplicate_eof_declines(monkeypatch, tmp_path) -> None:
    import pytest

    replacement, event, requests, _ = _replacement_fixture(monkeypatch, tmp_path)

    def eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    with pytest.raises(replacement.ReplacementDeclined):
        replacement.acquire_application_guard(tmp_path)
    assert not event.signaled and len(requests) == 1


def test_duplicate_noninteractive_does_not_signal(monkeypatch, tmp_path) -> None:
    import pytest

    replacement, event, _, _ = _replacement_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(replacement.sys.stdin, "isatty", lambda: False)
    with pytest.raises(replacement.ReplacementDeclined, match="interactive"):
        replacement.acquire_application_guard(tmp_path)
    assert not event.signaled


def test_duplicate_without_exit_receipt_never_acquires_new_guard(
    monkeypatch, tmp_path
) -> None:
    from types import SimpleNamespace

    import pytest

    replacement, event, requests, _ = _replacement_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "Y")
    monkeypatch.setattr(
        replacement,
        "RecoveryStore",
        lambda root: SimpleNamespace(read_exit_receipt=lambda generation: None),
    )
    times = iter((0, 0, 2 * S))
    monkeypatch.setattr(replacement, "host_time_ns", lambda: next(times))
    monkeypatch.setattr(replacement.time, "sleep", lambda _: None)
    with pytest.raises(WindowsLaunchError, match="could not be confirmed"):
        replacement.acquire_application_guard(tmp_path)
    assert event.signaled and event.closed
    assert len(requests) == 1


def test_duplicate_rejects_wrong_supervisor_exit_receipt(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    import pytest

    replacement, _, requests, _ = _replacement_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "Y")
    monkeypatch.setattr(
        replacement,
        "RecoveryStore",
        lambda root: SimpleNamespace(
            read_exit_receipt=lambda generation: SimpleNamespace(
                supervisor_generation="different generation"
            )
        ),
    )
    with pytest.raises(WindowsLaunchError, match="generation mismatch"):
        replacement.acquire_application_guard(tmp_path)
    assert len(requests) == 1


def test_duplicate_competing_launcher_does_not_replace_successor(
    monkeypatch, tmp_path
) -> None:
    import pytest

    from cephvr.platform.windows.guard import InstanceAlreadyRunning

    replacement, event, _, _ = _replacement_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "Y")

    def busy(_):
        raise InstanceAlreadyRunning("another launcher acquired the guard")

    monkeypatch.setattr(replacement, "SingleInstanceGuard", busy)
    times = iter((0, 0, 2 * S))
    monkeypatch.setattr(replacement, "host_time_ns", lambda: next(times))
    monkeypatch.setattr(replacement.time, "sleep", lambda _: None)
    with pytest.raises(WindowsLaunchError, match="could not be confirmed"):
        replacement.acquire_application_guard(tmp_path)
    assert event.signaled and event.closed


def test_free_guard_never_prompts_or_discovers(monkeypatch, tmp_path) -> None:
    from cephvr.launcher import replacement

    monkeypatch.setattr(replacement, "SingleInstanceGuard", lambda _: "guard")
    monkeypatch.setattr(
        "builtins.input", lambda _: (_ for _ in ()).throw(AssertionError())
    )
    assert replacement.acquire_application_guard(tmp_path) == "guard"


def test_endpoint_uses_fresh_identity_and_removes_private_descriptor(
    monkeypatch, tmp_path
) -> None:
    from uuid import uuid4

    from cephvr.launcher import replacement

    event = ReplacementEvent()
    event.wait = lambda _: False
    event.close = lambda: setattr(event, "closed", True)
    monkeypatch.setattr(replacement.AutoResetEvent, "create", lambda _: event)
    root = tmp_path / "runtime"
    with replacement.ReplacementEndpoint(root, str(uuid4()), str(uuid4()), S) as owner:
        installed = replacement._existing_endpoint(root)
        assert installed == owner.record
        assert not owner.requested()
    assert event.closed
    assert not (root / "launcher.json").exists()


def test_old_launcher_without_endpoint_requires_manual_shutdown(tmp_path) -> None:
    import pytest

    from cephvr.launcher.replacement import _existing_endpoint
    from cephvr.shared.credentials import _ensure_directory

    root = tmp_path / "old-runtime"
    _ensure_directory(root)
    with pytest.raises(WindowsLaunchError, match="no replacement endpoint"):
        _existing_endpoint(root)
