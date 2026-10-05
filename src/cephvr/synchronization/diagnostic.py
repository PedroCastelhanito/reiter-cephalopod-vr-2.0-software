"""Controller-owned, read-only SpikeGLX command-server diagnostic (E12/G01)."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import threading
import tomllib
from concurrent.futures import Future
from ctypes import byref, c_bool, c_char_p
from pathlib import Path
from types import ModuleType

from cephvr.control.v1 import services_pb2 as rpc


def _sdk_package(software_root: Path) -> Path:
    configured = os.environ.get("CEPHVR_SPIKEGLX_SDK_DIR")
    if configured:
        return Path(configured)
    return software_root / ".local-spikeglx-sdk/Windows/Python/sglx_pkg"


def _load_sdk(package: Path) -> ModuleType:
    source = package / "sglx.py"
    dll = package / "SglxApi.dll"
    if not source.is_file() or not dll.is_file():
        raise RuntimeError(
            "Official SpikeGLX SDK unavailable; install sglx.py and SglxApi.dll "
            f"in {package}"
        )
    spec = importlib.util.spec_from_file_location("_cephvr_spikeglx_sdk", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Official SpikeGLX SDK Python wrapper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    with os.add_dll_directory(str(package)):
        spec.loader.exec_module(module)
    return module


def _text(value: bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if value else ""


def _required(ok: bool, sdk: ModuleType, handle: int, call: str) -> None:
    if not ok:
        error = _text(sdk.c_sglx_getError(handle))
        raise RuntimeError(f"{call}: {error or 'SpikeGLX SDK call failed'}")


def _read_once(software_root: Path) -> rpc.SpikeGLXConnectionResult:
    with (software_root / "config/backends/synchronization_config.toml").open(
        "rb"
    ) as stream:
        settings = tomllib.load(stream)
    endpoint = settings["spikeglx"]
    address, port = endpoint["address"], endpoint["port"]
    if (
        not isinstance(address, str)
        or not address
        or type(port) is not int
        or not 0 < port <= 65535
    ):
        raise ValueError("SpikeGLX command-server endpoint is invalid")
    result = rpc.SpikeGLXConnectionResult(address=address, port=port)
    sdk = _load_sdk(_sdk_package(software_root))
    handle = sdk.c_sglx_createHandle()
    if not handle:
        raise RuntimeError("SpikeGLX SDK could not create a connection handle")
    try:
        _required(
            sdk.c_sglx_connect(handle, address.encode("utf-8"), port),
            sdk,
            handle,
            "connect",
        )
        result.connected = True
        result.version = _text(sdk.c_sglx_getVersion(handle))
        if not result.version:
            raise RuntimeError("SpikeGLX SDK returned no version")
        running, saving = c_bool(), c_bool()
        _required(
            sdk.c_sglx_isRunning(byref(running), handle), sdk, handle, "isRunning"
        )
        _required(sdk.c_sglx_isSaving(byref(saving), handle), sdk, handle, "isSaving")
        result.running, result.saving = running.value, saving.value
        run_name, data_dir = c_char_p(), c_char_p()
        # getRunName fails before SpikeGLX's first Verify | Save; connection is still valid.
        if sdk.c_sglx_getRunName(byref(run_name), handle):
            result.run_name = _text(run_name.value)
        _required(
            sdk.c_sglx_getDataDir(byref(data_dir), handle, 0),
            sdk,
            handle,
            "getDataDir",
        )
        result.data_directory = _text(data_dir.value)
        return result
    finally:
        try:
            sdk.c_sglx_close(handle)
        finally:
            sdk.c_sglx_destroyHandle(handle)


class SpikeGLXDiagnostic:
    """One daemon I/O thread at a time; a timeout leaves its call in flight."""

    def __init__(self, software_root: Path, timeout_s: float = 5.0) -> None:
        self.software_root = software_root
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self._pending: Future[rpc.SpikeGLXConnectionResult] | None = None

    async def check(self) -> rpc.SpikeGLXConnectionResult:
        with self._lock:
            if self._pending is not None and not self._pending.done():
                return rpc.SpikeGLXConnectionResult(
                    error="A previous SpikeGLX connection check is still in progress"
                )
            future: Future[rpc.SpikeGLXConnectionResult] = Future()
            self._pending = future

        def read() -> None:
            try:
                future.set_result(_read_once(self.software_root))
            except Exception as exc:
                future.set_result(rpc.SpikeGLXConnectionResult(error=str(exc)))

        threading.Thread(target=read, name="spikeglx-diagnostic", daemon=True).start()
        try:
            return await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(future)), self.timeout_s
            )
        except TimeoutError:
            return rpc.SpikeGLXConnectionResult(
                error="SpikeGLX connection check timed out; remote state is unknown"
            )
