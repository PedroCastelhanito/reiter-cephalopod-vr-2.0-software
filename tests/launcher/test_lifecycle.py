"""Launcher registration, shutdown backstops and verified process absence."""

from __future__ import annotations

from cephvr.launcher.decisions import (
    LOST_KEY,
    MAX_LINE_BYTES,
    LauncherDecisions,
    parse_notification_line,
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
