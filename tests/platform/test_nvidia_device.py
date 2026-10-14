"""GPU resolution failures stay explicit; no driver or hardware is loaded here."""

import ctypes
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

import cephvr.platform.windows.nvidia_device as nvidia_device
from cephvr.platform.windows.jobs import WindowsLaunchError

GPU_UUID = "GPU-00000000-0000-4000-8000-000000000001"


def test_graphics_preferences_are_per_image_and_verified(monkeypatch, tmp_path):
    import sys

    from cephvr.platform.windows.graphics_preferences import (
        configure_graphics_preference,
        preference_value,
    )

    assert preference_value(
        "Other=enabled;GpuPreference=1;", high_performance=True
    ) == ("Other=enabled;GpuPreference=2;")
    values = {}
    writes = []

    def query(_key, name):
        if name not in values:
            raise FileNotFoundError
        return values[name], 1

    def write(_key, name, _reserved, _kind, value):
        writes.append(name)
        values[name] = value

    registry = SimpleNamespace(
        HKEY_CURRENT_USER=0,
        KEY_READ=1,
        KEY_WRITE=2,
        REG_SZ=1,
        CreateKeyEx=lambda *_args: nullcontext(None),
        QueryValueEx=query,
        SetValueEx=write,
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)
    gui = tmp_path / "cephvr-python.exe"
    renderer = tmp_path / "cephvr-renderer.exe"
    configure_graphics_preference(gui, high_performance=False)
    configure_graphics_preference(renderer, high_performance=True)
    configure_graphics_preference(renderer, high_performance=True)
    assert writes == [str(gui.resolve()), str(renderer.resolve())]
    assert values[str(gui.resolve())] == "GpuPreference=1;"
    assert values[str(renderer.resolve())] == "GpuPreference=2;"
    registry.SetValueEx = lambda *_args: None
    with pytest.raises(WindowsLaunchError, match="read-back differs"):
        configure_graphics_preference(gui, high_performance=True)


def test_renderer_image_is_distinct_and_rejects_modified_bytes(monkeypatch, tmp_path):
    from cephvr.platform.windows import graphics_preferences, python_runtime

    source = tmp_path / "cephvr-python.exe"
    source.write_bytes(b"verified interpreter")
    preferences = []
    monkeypatch.setattr(python_runtime, "resolve_python_executable", lambda _p: source)
    monkeypatch.setattr(
        graphics_preferences,
        "configure_graphics_preference",
        lambda path, **kw: preferences.append((path, kw)),
    )
    renderer = python_runtime.resolve_renderer_executable(Path("python.exe"))
    assert renderer.name == "cephvr-renderer.exe"
    assert renderer.read_bytes() == source.read_bytes()
    assert preferences == [(renderer, {"high_performance": True})]
    renderer.write_bytes(b"modified image")
    with pytest.raises(python_runtime.PythonRuntimeError, match="stale"):
        python_runtime.resolve_renderer_executable(source)
    assert len(preferences) == 1


def test_wrong_live_opengl_adapter_is_distinct_from_driver_failure(monkeypatch):
    monkeypatch.setattr(nvidia_device, "sys", SimpleNamespace(platform="win32"))
    selected = nvidia_device.NvidiaDevice(0, GPU_UUID, "NVIDIA GeForce RTX 5060 Ti")
    monkeypatch.setattr(nvidia_device, "_enumerate_cuda_devices", lambda: [selected])
    with pytest.raises(nvidia_device.OpenGLAdapterMismatch, match="AMD Radeon"):
        nvidia_device.verify_opengl_rendering_device(
            "AMD Radeon", "ATI Technologies Inc."
        )
    assert (
        nvidia_device.verify_opengl_rendering_device(selected.name, "NVIDIA")
        == selected
    )

    def failed_driver():
        raise WindowsLaunchError("cuInit failed")

    monkeypatch.setattr(nvidia_device, "_enumerate_cuda_devices", failed_driver)
    with pytest.raises(WindowsLaunchError, match="cuInit failed") as failure:
        nvidia_device.verify_opengl_rendering_device(selected.name, "NVIDIA")
    assert not isinstance(failure.value, nvidia_device.OpenGLAdapterMismatch)


def test_malformed_uuid_fails_before_native_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nvidia_device, "sys", SimpleNamespace(platform="win32"))

    def unexpected_discovery() -> list[nvidia_device.NvidiaDevice]:
        raise AssertionError("invalid configured identity must not load CUDA")

    monkeypatch.setattr(nvidia_device, "_enumerate_cuda_devices", unexpected_discovery)
    with pytest.raises(WindowsLaunchError, match="UUID is malformed"):
        nvidia_device.resolve_cuda_ordinal("not-a-uuid")


def test_discovery_on_unsupported_platform_raises_preparation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nvidia_device, "sys", SimpleNamespace(platform="darwin"))
    with pytest.raises(WindowsLaunchError, match="requires Windows"):
        nvidia_device.discover_encoder_device()


@pytest.mark.parametrize("missing_export", [False, True])
def test_missing_cuda_library_or_export_raises_preparation_error(
    monkeypatch: pytest.MonkeyPatch, missing_export: bool
) -> None:
    monkeypatch.setattr(nvidia_device, "sys", SimpleNamespace(platform="win32"))

    def load_driver(name: str) -> object:
        assert name == "nvcuda.dll"
        if missing_export:
            return SimpleNamespace()
        raise OSError("driver unavailable")

    monkeypatch.setattr(ctypes, "WinDLL", load_driver, raising=False)
    with pytest.raises(WindowsLaunchError, match="driver API is unavailable"):
        nvidia_device.discover_encoder_device()


def test_uuid_selection_uses_the_adopted_device_not_list_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nvidia_device, "sys", SimpleNamespace(platform="win32"))
    selected = nvidia_device.NvidiaDevice(1, GPU_UUID, "NVIDIA GeForce RTX 2080 Ti")
    other = nvidia_device.NvidiaDevice(
        0, "GPU-00000000-0000-4000-8000-000000000002", "NVIDIA GeForce RTX 5060 Ti"
    )
    monkeypatch.setattr(
        nvidia_device, "_enumerate_cuda_devices", lambda: [other, selected]
    )
    assert nvidia_device.resolve_cuda_ordinal(GPU_UUID) == selected
    with pytest.raises(WindowsLaunchError, match="not the RTX 2080 Ti"):
        nvidia_device.resolve_cuda_ordinal(other.uuid)


def test_absent_uuid_never_falls_back_to_an_available_encoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nvidia_device, "sys", SimpleNamespace(platform="win32"))
    available = nvidia_device.NvidiaDevice(1, GPU_UUID, "NVIDIA GeForce RTX 2080 Ti")
    monkeypatch.setattr(nvidia_device, "_enumerate_cuda_devices", lambda: [available])
    with pytest.raises(WindowsLaunchError, match="resolved to 0 CUDA devices"):
        nvidia_device.resolve_cuda_ordinal("GPU-00000000-0000-4000-8000-000000000002")
