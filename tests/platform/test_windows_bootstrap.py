from __future__ import annotations

import asyncio
import threading

import pytest

import cephvr.platform.windows.bootstrap as bootstrap
from cephvr.platform.windows.jobs import WindowsLaunchError
from cephvr.shared.clock import host_time_ns


@pytest.mark.asyncio
async def test_bootstrap_writer_retains_attempt_until_blocking_write_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, release = threading.Event(), threading.Event()
    written: list[tuple[int, dict[str, object]]] = []

    def write(handle: int, descriptor: dict[str, object]) -> None:
        written.append((handle, descriptor))
        started.set()
        assert release.wait(timeout=2)

    monkeypatch.setattr(bootstrap, "write_bootstrap", write)
    attempt = bootstrap.BootstrapPipeWrite(37, {"generation": "worker"})
    attempt.start()
    assert await asyncio.to_thread(started.wait, 1)

    with pytest.raises(TimeoutError, match="remains in progress"):
        await attempt.wait(host_time_ns() + 10_000_000)
    assert not attempt.completed.is_set()
    assert written == [(37, {"generation": "worker"})]

    release.set()
    await attempt.wait(host_time_ns() + 2_000_000_000)
    assert attempt.completed.is_set()


@pytest.mark.asyncio
async def test_bootstrap_writer_preserves_worker_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_handle: int, _descriptor: dict[str, object]) -> None:
        raise OSError("pipe closed")

    monkeypatch.setattr(bootstrap, "write_bootstrap", fail)
    attempt = bootstrap.BootstrapPipeWrite(41, {})
    attempt.start()

    with pytest.raises(WindowsLaunchError, match="pipe closed") as error:
        await attempt.wait(host_time_ns() + 2_000_000_000)
    assert isinstance(error.value.__cause__, OSError)


def test_managed_entry_rebinds_hashlib_fallback_to_openssl() -> None:
    from types import SimpleNamespace

    from cephvr.platform.windows.python_entry import accelerate_hashlib
    from cephvr.platform.windows.python_runtime import PythonRuntimeError

    def digest(module: str) -> object:
        return SimpleNamespace(__module__=module)

    fallback = SimpleNamespace(sha256=digest("_sha256"))
    reloads: list[object] = []

    def reload(module):
        reloads.append(module)
        module.sha256 = digest("_hashlib")
        return module

    accelerate_hashlib(fallback, reload)  # type: ignore[arg-type]
    assert reloads == [fallback] and fallback.sha256.__module__ == "_hashlib"

    accelerate_hashlib(fallback, reload)  # type: ignore[arg-type]
    assert reloads == [fallback]

    unavailable = SimpleNamespace(sha256=digest("_sha256"))
    with pytest.raises(PythonRuntimeError, match="OpenSSL provider"):
        accelerate_hashlib(unavailable, lambda module: module)  # type: ignore[arg-type]

    accelerate_hashlib()
