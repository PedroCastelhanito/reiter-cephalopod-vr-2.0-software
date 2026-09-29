"""Authority exit boundaries use exact native evidence without assuming closure."""

from __future__ import annotations

import uuid

import pytest

from cephvr.controller.authority import (
    ManagedJob,
    managed_jobs_from_bootstrap,
    shutdown_owned_jobs,
)


class NativeEvidence:
    def __init__(self, *, unknown: bool = False) -> None:
        self.unknown = unknown
        self.members = {
            "backend": [(41, 100, "python.exe"), (42, 200, "ffmpeg.exe")],
            "gui": [(50, 300, "python.exe")],
        }
        self.retained: set[tuple[int, int]] = set()
        self.terminated: list[tuple[int, int]] = []

    def inspect_launch_job(self, name: str) -> list[tuple[int, int, str]]:
        if self.unknown:
            raise OSError("membership lookup unavailable")
        return self.members[name]

    def retain_exact(
        self, pid: int, creation_time_100ns: int, executable: str
    ) -> object:
        self.retained.add((pid, creation_time_100ns))
        return object()

    def process_running(self, pid: int, creation_time_100ns: int) -> bool:
        assert (pid, creation_time_100ns) in self.retained
        return True

    def terminate_exact(self, pid: int, creation_time_100ns: int) -> None:
        assert (pid, creation_time_100ns) in self.retained
        self.terminated.append((pid, creation_time_100ns))
        for name, values in self.members.items():
            self.members[name] = [
                value for value in values if value[:2] != (pid, creation_time_100ns)
            ]


@pytest.mark.asyncio
async def test_descendants_are_retained_and_exited_before_gui_group() -> None:
    now = 1_000
    sleeps = []

    async def advance(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += int(seconds * 1e9)

    native = NativeEvidence()
    failures = await shutdown_owned_jobs(
        native,
        [
            ManagedJob("vr", "generation", "backend"),
            ManagedJob("gui", "generation", "gui"),
        ],
        absolute_deadline_ns=now + 20_000_000_000,
        graceful_exit_ns=5_000_000_000,
        terminate_exit_ns=2_000_000_000,
        clock=lambda: now,
        sleep=advance,
    )
    assert not failures
    assert native.terminated == [(41, 100), (42, 200), (50, 300)]
    assert all(seconds <= 0.05 for seconds in sleeps)
    assert now == 10_000_001_000


@pytest.mark.asyncio
async def test_unknown_membership_never_becomes_verified_absence_or_unbounded_wait() -> (
    None
):
    now = 1

    async def advance(seconds: float) -> None:
        nonlocal now
        now += max(1, int(seconds * 1e9))

    native = NativeEvidence(unknown=True)
    failures = await shutdown_owned_jobs(
        native,
        [ManagedJob("vr", "generation", "backend")],
        absolute_deadline_ns=2_000_000_001,
        graceful_exit_ns=5_000_000_000,
        terminate_exit_ns=2_000_000_000,
        clock=lambda: now,
        sleep=advance,
    )
    assert failures == (
        "owned process membership unconfirmed: membership lookup unavailable",
    )
    assert not native.terminated
    assert now == 2_000_000_001


def test_bootstrap_job_inventory_is_exact_and_never_accepts_outer_job() -> None:
    values = [
        {
            "role": role,
            "generation": str(uuid.uuid4()),
            "job_name": f"Local\\CephVR2-{uuid.uuid4()}",
        }
        for role in ("acquisition", "vr", "tracking", "gui")
    ]
    assert len(managed_jobs_from_bootstrap(values)) == 4
    with pytest.raises(ValueError):
        managed_jobs_from_bootstrap(values[:-1])
    values[0]["job_name"] = "application-123"
    with pytest.raises(ValueError):
        managed_jobs_from_bootstrap(values)
