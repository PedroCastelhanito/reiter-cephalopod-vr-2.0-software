"""Native Windows contract checks using only owned temporary children/files.

These tests require a real Windows process API. They never touch rig devices,
recording destinations, running CephVR processes, or a shared application job.
"""

from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import subprocess
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from datetime import datetime
from multiprocessing.shared_memory import SharedMemory
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

from cephvr.controller.metadata.reservation import OutputReservation  # noqa: E402
from cephvr.controller.metadata.types import StorageError  # noqa: E402
from cephvr.platform.windows.atomics import (  # noqa: E402
    NativeAtomicError,
    atomic_compare_exchange_u64,
    atomic_load_u64,
)
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
from cephvr.platform.windows.paths import extended_path  # noqa: E402
from cephvr.platform.windows.python_runtime import (  # noqa: E402
    module_arguments,
    prepare_python_runtime,
    resolve_python_executable,
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


def _increment_shared_atomic(name: str, increments: int) -> None:
    shared = SharedMemory(name=name)
    buffer = shared.buf
    assert buffer is not None
    try:
        for _ in range(increments):
            while True:
                current = atomic_load_u64(buffer, 0)
                if atomic_compare_exchange_u64(buffer, 0, current, current + 1):
                    break
    finally:
        buffer.release()
        shared.close()


def _try_reservation_from_process(
    root: str,
    experiment: str,
    subject: str,
    session_id: str,
    generation: str,
    anchor: str,
    result: multiprocessing.Queue[tuple[str, str]],
) -> None:
    reservation = OutputReservation(
        Path(root),
        experiment,
        subject,
        session_id,
        generation,
        datetime.fromisoformat(anchor),
    )
    try:
        reservation.acquire()
    except StorageError as exc:
        result.put(("blocked", str(exc)))
    else:
        result.put(("acquired", ""))
        reservation.cancel()


def _hold_reservation_until_terminated(
    root: str,
    experiment: str,
    subject: str,
    session_id: str,
    generation: str,
    anchor: str,
    ready: multiprocessing.Event,
) -> None:
    reservation = OutputReservation(
        Path(root),
        experiment,
        subject,
        session_id,
        generation,
        datetime.fromisoformat(anchor),
    )
    reservation.acquire()
    ready.set()
    time.sleep(30)


def test_native_atomic_compare_exchange_validates_and_observes_words() -> None:
    shared = SharedMemory(create=True, size=16)
    buffer = shared.buf
    assert buffer is not None
    try:
        assert atomic_load_u64(buffer, 0) == 0
        assert atomic_compare_exchange_u64(buffer, 0, 0, 7)
        assert not atomic_compare_exchange_u64(buffer, 0, 0, 9)
        assert atomic_load_u64(buffer, 0) == 7
        with pytest.raises(NativeAtomicError, match="unaligned"):
            atomic_load_u64(buffer, 1)
        with pytest.raises(NativeAtomicError, match="signed range"):
            atomic_compare_exchange_u64(buffer, 0, 1 << 63, 0)
    finally:
        buffer.release()
        shared.close()
        shared.unlink()


def test_native_atomic_compare_exchange_serializes_independent_processes() -> None:
    shared = SharedMemory(create=True, size=16)
    buffer = shared.buf
    assert buffer is not None
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_increment_shared_atomic, args=(shared.name, 2_000))
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(20)
        assert all(not process.is_alive() for process in processes)
        assert [process.exitcode for process in processes] == [0, 0]
        assert atomic_load_u64(buffer, 0) == 4_000
    finally:
        failed_to_stop = False
        for process in processes:
            if process.is_alive():
                process.terminate()
            if process.pid is not None:
                process.join(5)
                failed_to_stop |= process.is_alive()
                if not process.is_alive():
                    process.close()
        buffer.release()
        shared.close()
        shared.unlink()
        assert not failed_to_stop, "owned atomic test process did not exit"


def test_prepared_python_runtime_rejects_stale_or_mismatched_files(
    tmp_path: Path,
) -> None:
    home = tmp_path / "base"
    scripts = tmp_path / "venv" / "Scripts"
    home.mkdir()
    scripts.mkdir(parents=True)
    (scripts.parent / "pyvenv.cfg").write_text(f"home = {home}\n", encoding="utf-8")
    base_executable = home / "python.exe"
    base_dll = home / "python311.dll"
    base_executable.write_bytes(b"base executable")
    base_dll.write_bytes(b"matching runtime dll")
    (home / "VCRUNTIME140.dll").write_bytes(b"matching runtime support")
    (home / "zlib.dll").write_bytes(b"matching optional zlib")
    wrapper = prepare_python_runtime(scripts.parent, base_executable, base_dll)
    assert wrapper.read_bytes() == base_executable.read_bytes()
    assert (scripts / "python311.dll").read_bytes() == base_dll.read_bytes()
    assert (scripts / "VCRUNTIME140.dll").read_bytes() == b"matching runtime support"
    assert (scripts / "zlib.dll").read_bytes() == b"matching optional zlib"
    wrapper.unlink()
    with pytest.raises(RuntimeError, match="changed"):
        resolve_python_executable(scripts / "python.exe")
    prepare_python_runtime(scripts.parent, base_executable, base_dll)

    manifest = scripts / "cephvr-python.runtime.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["base_executable"] = str(home / "other-python.exe")
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed|provenance"):
        resolve_python_executable(wrapper)

    prepare_python_runtime(scripts.parent, base_executable, base_dll)
    manifest.unlink()
    with pytest.raises(RuntimeError, match="manifest unavailable"):
        resolve_python_executable(scripts / "python.exe")
    prepare_python_runtime(scripts.parent, base_executable, base_dll)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_payload["startup_dlls"][1]["base_sha256"] = "stale"
    manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="startup DLL (provenance|copy differs)"):
        resolve_python_executable(wrapper)
    prepare_python_runtime(scripts.parent, base_executable, base_dll)
    (scripts / "zlib.dll").write_bytes(b"changed startup dependency")
    with pytest.raises(RuntimeError, match="startup DLL (provenance|copy differs)"):
        resolve_python_executable(wrapper)
    prepare_python_runtime(scripts.parent, base_executable, base_dll)
    (scripts / "python311.dll").write_bytes(b"changed runtime dll")
    with pytest.raises(RuntimeError, match="changed|provenance"):
        resolve_python_executable(wrapper)
    prepare_python_runtime(scripts.parent, base_executable, base_dll)
    (home / "zlib.dll").unlink()
    with pytest.raises(RuntimeError, match="unexpected prepared startup DLL"):
        prepare_python_runtime(scripts.parent, base_executable, base_dll)


def test_managed_python_entry_preserves_identity_prefix_and_bootstrap(
    tmp_path: Path,
) -> None:
    runtime = resolve_python_executable(Path(sys.executable))
    job = f"cephvr-python-runtime-{uuid4()}"
    native = WindowsJobs()
    native.create_launch_job(job)
    read, write = create_bootstrap_pipe()
    read_open = True
    write_open = True
    result_path = tmp_path / "runtime-probe.json"
    release_path = tmp_path / "runtime-probe.release"
    stdout_path = tmp_path / "runtime-probe.stdout.log"
    stderr_path = tmp_path / "runtime-probe.stderr.log"
    stdin_stream = open(os.devnull, "rb", buffering=0)
    stdout_stream = stdout_path.open("wb", buffering=0)
    stderr_stream = stderr_path.open("wb", buffering=0)
    standard_handles = tuple(
        msvcrt.get_osfhandle(stream.fileno())
        for stream in (stdin_stream, stdout_stream, stderr_stream)
    )
    for handle in standard_handles:
        os.set_handle_inheritable(handle, True)
    child = None
    try:
        child = native.launch_suspended(
            str(runtime),
            module_arguments(
                "tests.platform.test_windows_native_on_rig",
                ["--managed-runtime-probe", "--bootstrap-handle", str(read)],
            ),
            [job],
            (read, *standard_handles),
            stdin_handle=standard_handles[0],
            stdout_handle=standard_handles[1],
            stderr_handle=standard_handles[2],
        )
        close_handle(read)
        read_open = False
        write_bootstrap(
            write,
            {
                "marker": "inherited-bootstrap",
                "result": str(result_path),
                "release": str(release_path),
            },
        )
        write_open = False
        native.resume(child)
        deadline = time.monotonic() + 5.0
        while not result_path.is_file() and time.monotonic() < deadline:
            time.sleep(0.025)
        if not result_path.is_file():
            running = native.process_running(child.pid, child.creation_time_100ns)
            if running:
                child_state = "still running at probe timeout"
            else:
                exit_code = wintypes.DWORD()
                assert native.api.GetExitCodeProcess(
                    child.process_handle, ctypes.byref(exit_code)
                )
                child_state = f"exited with code {exit_code.value}"
            raise AssertionError(
                "managed interpreter did not publish its probe result; "
                f"child {child_state}; stdout={stdout_path.read_text(encoding='utf-8', errors='replace')!r}; "
                f"stderr={stderr_path.read_text(encoding='utf-8', errors='replace')!r}"
            )
        members = native.inspect_launch_job(job)
        assert len(members) == 1
        assert members[0][:2] == (child.pid, child.creation_time_100ns)
        assert Path(members[0][2]).resolve() == runtime.resolve()
        retained = native.retain_exact(
            child.pid, child.creation_time_100ns, str(runtime)
        )
        assert retained.pid == child.pid
        observed = json.loads(result_path.read_text(encoding="utf-8"))
        assert observed["pid"] == child.pid
        assert Path(observed["image"]).resolve() == runtime.resolve()
        assert Path(observed["prefix"]).resolve() == Path(sys.prefix).resolve()
        assert observed["marker"] == "inherited-bootstrap"
        assert observed["grpc"]
        assert (
            Path(observed["grpc_file"])
            .resolve()
            .is_relative_to(Path(sys.prefix).resolve() / "Lib" / "site-packages")
        )
        release_path.write_text("release", encoding="utf-8")
        assert native.wait_process_exit(child.pid, child.creation_time_100ns, 15_000)
    finally:
        if read_open:
            close_handle(read)
        if write_open:
            close_handle(write)
        if child is not None:
            if native.process_running(child.pid, child.creation_time_100ns):
                release_path.write_text("release", encoding="utf-8")
                native.terminate_job(job)
                native.wait_process_exit(child.pid, child.creation_time_100ns, 5_000)
            native.release_process(child.pid, child.creation_time_100ns)
        if job in native.jobs:
            native.close_launch_job(job)
        stdin_stream.close()
        stdout_stream.close()
        stderr_stream.close()


def test_output_reservation_path_guard_covers_lock_close_and_aliases(
    tmp_path: Path,
) -> None:
    context = multiprocessing.get_context("spawn")
    root = tmp_path.resolve()
    experiment, subject = "guard", "subject"
    session_id, generation = str(uuid4()), str(uuid4())
    anchor = datetime(2026, 1, 2, 3, 4, 5)
    reservation = OutputReservation(
        root, experiment, subject, session_id, generation, anchor
    )
    reservation.protocol_directory.mkdir(parents=True)
    reservation.spikeglx_directory.mkdir()
    assert reservation.acquire() == []
    outcomes = context.Queue()
    children: list[multiprocessing.Process] = []
    close_lock = reservation._release_byte_lock

    def interleave_competitor() -> None:
        close_lock()
        child = context.Process(
            target=_try_reservation_from_process,
            args=(
                extended_path(root),
                experiment,
                subject,
                session_id,
                generation,
                anchor.isoformat(),
                outcomes,
            ),
        )
        children.append(child)
        child.start()
        status = outcomes.get(timeout=10)
        child.join(10)
        assert not child.is_alive()
        assert child.exitcode == 0
        assert status[0] == "blocked" and "locked" in status[1]

    reservation._release_byte_lock = interleave_competitor  # type: ignore[method-assign]
    try:
        reservation.cancel()
    finally:
        reservation._release_byte_lock = close_lock  # type: ignore[method-assign]
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join(5)
            if child.is_alive():
                pytest.fail("owned path-guard competitor did not exit")
            child.close()
        outcomes.close()
        outcomes.join_thread()
        reservation.release()


def test_output_reservation_guard_releases_when_owner_process_dies(
    tmp_path: Path,
) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    root = tmp_path.resolve()
    experiment, subject = "death", "subject"
    session_id, generation = str(uuid4()), str(uuid4())
    anchor = datetime(2026, 1, 2, 3, 4, 5)
    owner = context.Process(
        target=_hold_reservation_until_terminated,
        args=(
            str(root),
            experiment,
            subject,
            session_id,
            generation,
            anchor.isoformat(),
            ready,
        ),
    )
    owner.start()
    try:
        assert ready.wait(10)
        owner.terminate()
        owner.join(10)
        assert not owner.is_alive()
        assert owner.exitcode is not None
        recovered = OutputReservation.open_existing(
            root
            / f"{anchor.strftime('%Y%m%d')}_{experiment}"
            / f"subject-{anchor.strftime('%H%M%S')}",
            session_id,
            generation,
        )
        try:
            assert recovered.held
            assert not recovered.inspect_marker().complete
        finally:
            recovered.release()
    finally:
        if owner.is_alive():
            owner.terminate()
            owner.join(5)
        assert not owner.is_alive(), "owned reservation process did not exit"
        owner.close()


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


def test_broad_dacl_is_rejected_for_owned_recovery_record(tmp_path: Path) -> None:
    record = tmp_path / "private-recovery.json"
    create_owner_only(record, b'{"owned":true}')
    grant = subprocess.run(
        ["icacls", str(record), "/grant", "*S-1-1-0:R"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert grant.returncode == 0, grant.stderr or grant.stdout
    with pytest.raises(WindowsSecurityError, match="ACL|access|owner|private"):
        verify_owner_only(record)


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


if __name__ == "__main__" and "--managed-runtime-probe" in sys.argv:
    handle_index = sys.argv.index("--bootstrap-handle") + 1
    descriptor = read_bootstrap(int(sys.argv[handle_index]))
    import grpc

    result_path = Path(str(descriptor["result"]))
    temporary = result_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "image": sys.executable,
                "prefix": sys.prefix,
                "marker": descriptor["marker"],
                "grpc": grpc.__version__,
                "grpc_file": grpc.__file__,
            }
        ),
        encoding="utf-8",
    )
    temporary.replace(result_path)
    release = Path(str(descriptor["release"]))
    deadline = time.monotonic() + 15
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.025)
