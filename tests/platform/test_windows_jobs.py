"""Exact process identity, job membership races and retained handles."""

from __future__ import annotations

import ctypes
from types import SimpleNamespace

import pytest

from cephvr.platform.windows.jobs import (
    ERROR_INVALID_PARAMETER,
    WAIT_OBJECT_0,
    WAIT_TIMEOUT,
    WindowsJobs,
    WindowsLaunchError,
)


class FakeApi:
    """Job PID lists per enumeration pass; pids in `gone` fail OpenProcess with 87."""

    def __init__(self, passes: list[list[int]]) -> None:
        self.passes = passes
        self.pass_index = 0
        self.gone: set[int] = set()
        self.denied: set[int] = set()
        self.exited_after_open: set[int] = set()
        self.last_error = 0
        self.terminated: list[int] = []
        self.terminate_ok = True
        self.closed: list[int] = []

    def QueryInformationJobObject(self, job, kind, buf, size, _ret) -> bool:  # noqa: N802
        pids = self.passes[min(self.pass_index, len(self.passes) - 1)]
        self.pass_index += 1
        word = ctypes.sizeof(ctypes.c_size_t)
        ctypes.memmove(buf, len(pids).to_bytes(4, "little") * 2, 8)
        for index, pid in enumerate(pids):
            ctypes.memmove(
                ctypes.addressof(buf) + 8 + index * word,
                pid.to_bytes(word, "little"),
                word,
            )
        return True

    def OpenProcess(self, rights, inherit, pid) -> int:  # noqa: N802
        if pid in self.gone:
            self.last_error = ERROR_INVALID_PARAMETER
            return 0
        if pid in self.denied:
            self.last_error = 5
            return 0
        return pid

    def QueryFullProcessImageNameW(self, handle, flags, path, size) -> bool:  # noqa: N802
        if handle in self.exited_after_open:
            return False
        path.value = "member.exe"
        return True

    def WaitForSingleObject(self, handle, timeout) -> int:  # noqa: N802
        return WAIT_OBJECT_0 if handle in self.exited_after_open else WAIT_TIMEOUT

    def CloseHandle(self, handle) -> bool:  # noqa: N802
        self.closed.append(handle)
        return True

    def TerminateProcess(self, handle, code) -> bool:  # noqa: N802
        self.terminated.append(handle)
        return self.terminate_ok


def make_jobs(api: FakeApi) -> WindowsJobs:
    jobs = object.__new__(WindowsJobs)
    jobs.api = api
    jobs.jobs = {"job": 1}
    jobs.processes = {}
    jobs._last_error = lambda: api.last_error  # type: ignore[method-assign]
    jobs._creation_time = lambda handle: 1000 + handle  # type: ignore[method-assign]
    return jobs


def test_member_exiting_between_enumeration_and_open_is_absent() -> None:
    api = FakeApi([[10, 11], [10]])
    api.gone = {11}
    members = make_jobs(api).inspect_launch_job("job")
    assert [(pid, created) for pid, created, _ in members] == [(10, 1010)]


def test_member_exiting_after_open_is_absent() -> None:
    api = FakeApi([[10, 11], [10, 11]])
    api.exited_after_open = {11}
    members = make_jobs(api).inspect_launch_job("job")
    assert [pid for pid, _, _ in members] == [10]


def test_reenumerates_until_two_passes_agree() -> None:
    api = FakeApi([[10, 11, 12], [10, 11], [10, 11]])
    members = make_jobs(api).inspect_launch_job("job")
    assert [pid for pid, _, _ in members] == [10, 11]
    assert api.pass_index == 3


def test_unstable_membership_is_bounded() -> None:
    api = FakeApi([[1], [1, 2], [1, 2, 3], [1, 2, 3, 4]])
    members = make_jobs(api).inspect_launch_job("job")
    assert api.pass_index == 3
    assert [pid for pid, _, _ in members] == [1, 2, 3]


def test_other_open_error_still_raises() -> None:
    api = FakeApi([[10]])
    api.denied = {10}
    with pytest.raises(WindowsLaunchError, match="OpenProcess failed: WinError 5"):
        make_jobs(api).inspect_launch_job("job")


def test_terminate_of_exited_process_counts_as_absent() -> None:
    api = FakeApi([[]])
    api.gone = {10}
    make_jobs(api).terminate_exact(10, 1010)  # no raise
    api = FakeApi([[]])
    api.terminate_ok = False
    api.exited_after_open = {11}
    jobs = make_jobs(api)
    jobs._creation_time = lambda handle: 5  # type: ignore[method-assign]
    jobs.terminate_exact(11, 5)
    assert api.terminated == [11]


def test_terminate_failure_of_live_process_raises() -> None:
    api = FakeApi([[]])
    api.terminate_ok = False
    api.last_error = 5
    jobs = make_jobs(api)
    jobs._creation_time = lambda handle: 5  # type: ignore[method-assign]
    with pytest.raises(WindowsLaunchError, match="TerminateProcess"):
        jobs.terminate_exact(11, 5)


def test_process_gone_is_not_running() -> None:
    api = FakeApi([[]])
    api.gone = {10}
    assert make_jobs(api).process_running(10, 1010) is False


def test_process_exit_uses_handle_wait_not_exit_code() -> None:
    jobs = object.__new__(WindowsJobs)
    api = SimpleNamespace(wait_result=WAIT_OBJECT_0)
    api.WaitForSingleObject = lambda handle, timeout: api.wait_result
    api.CloseHandle = lambda handle: True
    jobs.api = api
    jobs._open_exact = lambda pid, created: (123, False)
    assert jobs.process_running(42, 100) is False
    api.wait_result = WAIT_TIMEOUT
    assert jobs.process_running(42, 100) is True


def test_query_failure_is_unknown_not_absence() -> None:
    jobs = object.__new__(WindowsJobs)
    jobs._open_exact = lambda pid, created: (_ for _ in ()).throw(
        WindowsLaunchError("access denied")
    )
    with pytest.raises(WindowsLaunchError, match="access denied"):
        jobs.process_running(42, 100)


def test_new_process_handle_is_closed_when_creation_query_fails() -> None:
    jobs = object.__new__(WindowsJobs)
    closed: list[int] = []
    jobs.api = SimpleNamespace(
        OpenProcess=lambda rights, inherit, pid: 123,
        CloseHandle=lambda handle: closed.append(handle),
    )
    jobs.processes = {}
    jobs._creation_time = lambda handle: (_ for _ in ()).throw(
        WindowsLaunchError("creation query denied")
    )
    with pytest.raises(WindowsLaunchError, match="creation query denied"):
        jobs._open_exact(42, 100)
    assert closed == [123]
