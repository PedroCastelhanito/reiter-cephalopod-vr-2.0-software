from __future__ import annotations

from types import SimpleNamespace

import pytest

from cephvr.platform.windows.jobs import (
    WAIT_OBJECT_0,
    WAIT_TIMEOUT,
    WindowsJobs,
    WindowsLaunchError,
)


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
