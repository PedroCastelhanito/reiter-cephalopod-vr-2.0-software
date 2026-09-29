"""Native Windows contract checks using only owned temporary children/files.

These tests require a real Windows process API. They never touch rig devices,
recording destinations, running CephVR processes, or a shared application job.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.windows
if sys.platform != "win32":
    pytest.skip(
        "native Windows process/resource checks require Windows",
        allow_module_level=True,
    )

import msvcrt  # noqa: E402

from cephvr.platform.windows.bootstrap import (  # noqa: E402
    close_handle,
    create_bootstrap_pipe,
    create_control_pipe,
    read_bootstrap,
    write_bootstrap,
)
from cephvr.platform.windows.durable import (  # noqa: E402
    create_synced,
    replace_synced,
)
from cephvr.platform.windows.guard import SingleInstanceGuard  # noqa: E402
from cephvr.platform.windows.jobs import (  # noqa: E402
    WindowsJobs,
    WindowsLaunchError,
)
from cephvr.platform.windows.security import (  # noqa: E402
    WindowsSecurityError,
    create_owner_only,
    create_owner_only_directory,
    open_owner_only_lock,
    verify_owner_only,
)
from cephvr.shared.clock import host_time_ns  # noqa: E402
from cephvr.shared.recovery import ApplicationExitReceipt, RecoveryStore  # noqa: E402


def _until(predicate: Callable[[], bool], *, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.025)
    assert predicate(), "owned test child did not reach expected OS state"


def _inheritable(handle: int) -> bool:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetHandleInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.GetHandleInformation.restype = wintypes.BOOL
    flags = wintypes.DWORD()
    assert kernel.GetHandleInformation(handle, ctypes.byref(flags))
    return bool(flags.value & 1)


def _synced(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def test_creation_time_containment_and_outer_job_shutdown() -> None:
    native = WindowsJobs()
    observer = WindowsJobs()
    outer = native.create_application_job()
    inner = f"cephvr-pytest-{uuid4()}"
    native.create_launch_job(inner)
    child = None
    try:
        with pytest.raises(WindowsLaunchError, match="containment job"):
            native.launch_suspended(sys.executable, ["-c", "pass"], [])
        child = native.launch_suspended(
            sys.executable,
            ["-c", "import time; time.sleep(60)"],
            [outer, inner],
        )
        # This is inspected before ResumeThread: assignment was at creation.
        assert any(
            pid == child.pid and created == child.creation_time_100ns
            for pid, created, _ in native.inspect_launch_job(outer)
        )
        assert any(
            pid == child.pid and created == child.creation_time_100ns
            for pid, created, _ in native.inspect_launch_job(inner)
        )
        assert native.process_running(child.pid, child.creation_time_100ns)
        with pytest.raises(WindowsLaunchError, match="creation time differs"):
            native.process_running(child.pid, child.creation_time_100ns + 1)
        observer.open_launch_job(inner)
        retained = observer.retain_exact(
            child.pid, child.creation_time_100ns, child.executable
        )
        assert retained.process_handle
        assert observer.process_running(child.pid, child.creation_time_100ns)
        native.resume(child)
        native.close_launch_job(outer)
        _until(lambda: not native.process_running(child.pid, child.creation_time_100ns))
        assert not observer.process_running(child.pid, child.creation_time_100ns)
        _until(lambda: not native.inspect_launch_job(inner))
    finally:
        if outer in native.jobs:
            native.terminate_job(outer)
            native.close_launch_job(outer)
        if inner in native.jobs:
            native.terminate_job(inner)
            native.close_launch_job(inner)
        if child is not None:
            observer.release_process(child.pid, child.creation_time_100ns)
            native.release_process(child.pid, child.creation_time_100ns)
        if inner in observer.jobs:
            observer.close_launch_job(inner)


def test_exit_code_259_is_not_mistaken_for_running() -> None:
    native = WindowsJobs()
    job = f"cephvr-pytest-{uuid4()}"
    native.create_launch_job(job)
    child = None
    try:
        child = native.launch_suspended(
            sys.executable, ["-c", "import os; os._exit(259)"], [job]
        )
        native.resume(child)
        _until(lambda: not native.process_running(child.pid, child.creation_time_100ns))
    finally:
        native.terminate_job(job)
        native.close_launch_job(job)
        if child is not None:
            native.release_process(child.pid, child.creation_time_100ns)


def test_bootstrap_framing_and_restricted_pipe_inheritance() -> None:
    read, write = create_bootstrap_pipe()
    assert _inheritable(read)
    assert not _inheritable(write)
    expected = {"generation": str(uuid4()), "tokens": ["private", "bounded"]}
    write_bootstrap(write, expected)  # Owns and closes the write HANDLE.
    assert read_bootstrap(read) == expected  # Owns and closes the read HANDLE.

    control_read, control_write = create_control_pipe()
    try:
        assert not _inheritable(control_read)
        assert _inheritable(control_write)
    finally:
        close_handle(control_read)
        close_handle(control_write)

    broken_read, broken_write = create_bootstrap_pipe()
    fd = msvcrt.open_osfhandle(broken_write, os.O_WRONLY)
    try:
        assert os.write(fd, b"\x05") == 1
    finally:
        os.close(fd)
    with pytest.raises(WindowsLaunchError, match="before length"):
        read_bootstrap(broken_read)


def test_atomic_owner_only_acl_and_renamable_lock(tmp_path: Path) -> None:
    private = tmp_path / "private"
    create_owner_only_directory(private)
    verify_owner_only(private)
    credential = private / "credential"
    create_owner_only(credential, b"secret")
    verify_owner_only(credential)
    assert credential.read_bytes() == b"secret"

    lock = private / "session.lock"
    fd, created = open_owner_only_lock(lock)
    assert created
    second_fd = -1
    try:
        verify_owner_only(lock)
        second_fd, created_again = open_owner_only_lock(lock)
        assert not created_again
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        try:
            tombstone = private / "retired.lock"
            os.replace(lock, tombstone)
            verify_owner_only(tombstone)
        finally:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        if second_fd >= 0:
            os.close(second_fd)
        os.close(fd)


def test_reparse_lock_target_is_rejected_when_symlinks_are_available(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private"
    create_owner_only_directory(private)
    target = private / "target.lock"
    fd, created = open_owner_only_lock(target)
    assert created
    os.close(fd)
    link = private / "linked.lock"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("Windows symlink privilege or Developer Mode is unavailable")
    with pytest.raises(WindowsSecurityError, match="reparse|link"):
        verify_owner_only(link)
    with pytest.raises(WindowsSecurityError, match="regular file"):
        open_owner_only_lock(link)


def test_application_exit_receipt_is_durable_and_private(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    store = RecoveryStore(runtime_root)
    controller_generation, supervisor_generation = str(uuid4()), str(uuid4())
    receipt = ApplicationExitReceipt(
        controller_generation=controller_generation,
        supervisor_generation=supervisor_generation,
        observed_monotonic_ns=host_time_ns(),
        all_owned_processes_absent=True,
    )
    store.write_exit_receipt(receipt)
    path = runtime_root / "recovery" / f"application-exit-{controller_generation}.json"
    verify_owner_only(path)
    assert store.read_exit_receipt(controller_generation) == receipt
    assert store.read_exit_receipt(str(uuid4())) is None


def test_write_through_same_directory_publication(tmp_path: Path) -> None:
    destination = tmp_path / "SESSION_CONFIG.json"
    first = tmp_path / "first.tmp"
    _synced(first, b'{"revision":1}')
    create_synced(first, destination)
    assert destination.read_bytes() == b'{"revision":1}'
    assert not first.exists()

    collision = tmp_path / "collision.tmp"
    _synced(collision, b"collision")
    with pytest.raises(WindowsLaunchError):
        create_synced(collision, destination)
    assert destination.read_bytes() == b'{"revision":1}'
    assert collision.exists()

    replacement = tmp_path / "replacement.tmp"
    _synced(replacement, b'{"revision":2}')
    replace_synced(replacement, destination)
    assert destination.read_bytes() == b'{"revision":2}'
    assert not replacement.exists()


def test_role_guard_rejects_second_owner_and_releases() -> None:
    role = f"pytest-{uuid4().hex}"
    with SingleInstanceGuard(role):
        with pytest.raises(WindowsLaunchError, match="already running"):
            SingleInstanceGuard(role)
    with SingleInstanceGuard(role):
        pass
