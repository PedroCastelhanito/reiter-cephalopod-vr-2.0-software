from __future__ import annotations

from cephvr.launcher.main import _retain_until_empty
from cephvr.platform.windows.jobs import WindowsLaunchError
from cephvr.shared.clock import host_time_ns


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
