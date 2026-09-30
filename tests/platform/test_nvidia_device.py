"""GPU resolution failures stay explicit; no driver or hardware is loaded here."""

import ctypes
from types import SimpleNamespace

import pytest

import cephvr.platform.windows.nvidia_device as nvidia_device
from cephvr.platform.windows.jobs import WindowsLaunchError

GPU_UUID = "GPU-00000000-0000-4000-8000-000000000001"


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
