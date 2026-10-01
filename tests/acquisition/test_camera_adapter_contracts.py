"""Exact SDK selection, required camera features and native pixel layouts."""

from __future__ import annotations

from threading import Event
from types import SimpleNamespace

import pytest

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.acquisition.camera.native_formats import (
    device_pixel_format,
    native_pixel_format,
    pylon_pixel_format,
)
from cephvr.acquisition.camera.wait import PylonWaitGate


@pytest.fixture(autouse=True)
def native_control_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cephvr.acquisition.camera.wait.ManualResetEvent.create", Event)


def test_adapter_construction_does_not_load_pypylon() -> None:
    adapter = BaslerCameraAdapter()
    assert adapter._pylon is None
    assert adapter._camera is None


def test_sdk_version_mismatch_is_explicit_and_does_not_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = BaslerCameraAdapter()
    imports: list[str] = []
    monkeypatch.setattr(
        "cephvr.acquisition.camera.basler.importlib.metadata.version",
        lambda _name: "26.4.0",
    )

    monkeypatch.setattr(
        "cephvr.acquisition.camera.basler.importlib.import_module",
        lambda name: imports.append(name),
    )
    with pytest.raises(CameraAdapterError, match="expected 26.3.1") as failure:
        adapter._sdk()
    assert failure.value.code == "SDK_UNAVAILABLE"
    assert imports == []


def test_idle_control_wait_keeps_native_deadline_wake_and_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    class NativeEvent:
        closed = False
        signaled = False

        def wait(self, timeout_ns: int) -> bool:
            calls.append(timeout_ns)
            return self.signaled

        def set(self) -> None:
            self.signaled = True

        def clear(self) -> None:
            self.signaled = False

        def close(self) -> None:
            self.closed = True

    event = NativeEvent()
    monkeypatch.setattr(
        "cephvr.acquisition.camera.wait.ManualResetEvent.create", lambda: event
    )
    gate = PylonWaitGate()
    assert not gate.wait_control(123_456)
    gate.wake()
    assert gate.wait_control(0)
    gate.clear()
    assert not gate.wait_control(789)
    with pytest.raises(ValueError, match="nonnegative"):
        gate.wait_control(-1)
    assert calls == [123_456, 0, 789]
    gate.close()
    gate.close()
    assert event.closed
    with pytest.raises(CameraAdapterError, match="unavailable"):
        gate.wait_control(0)


@pytest.mark.parametrize("control_ready", [False, True])
def test_joint_wait_retains_control_priority_and_rounding(control_ready: bool) -> None:
    gate = PylonWaitGate()
    waits: list[int] = []

    def wait(timeout: int) -> bool:
        waits.append(timeout)
        return True

    gate._waits = SimpleNamespace(WaitForAny=wait)
    if control_ready:
        gate.wake()
    assert gate.wait(1_000_001) == ("control" if control_ready else "frame")
    assert waits == [2]


def test_open_uses_exact_assigned_serial_not_enumeration_order() -> None:
    class DeviceInfo:
        def __init__(self, serial: str) -> None:
            self.serial = serial

        def GetSerialNumber(self) -> str:
            return self.serial

        def GetDeviceClass(self) -> str:
            return "BaslerUsb"

    first, assigned = DeviceInfo("other"), DeviceInfo("assigned")

    class Camera:
        opened = False

        def Open(self) -> None:
            self.opened = True

    native_camera = Camera()

    class Factory:
        def EnumerateDevices(self) -> tuple[DeviceInfo, DeviceInfo]:
            return first, assigned

        def CreateDevice(self, info: DeviceInfo) -> DeviceInfo:
            assert info is assigned
            return info

    factory = Factory()
    pylon = SimpleNamespace(
        TlFactory=SimpleNamespace(GetInstance=lambda: factory),
        InstantCamera=lambda _device: native_camera,
    )
    adapter = BaslerCameraAdapter()
    adapter._pylon = pylon

    adapter.open("assigned")

    assert native_camera.opened
    assert adapter._device_id == "assigned"
    assert adapter._interface == "usb3"


def test_trigger_timing_selects_and_verifies_exact_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    values = {"TriggerSelector": "FrameStart", "TriggerMode": "Off"}
    nodes = object()
    fake_camera = SimpleNamespace(GetNodeMap=lambda: nodes)
    adapter = BaslerCameraAdapter()
    adapter._camera = fake_camera
    adapter._device_info = object()
    adapter._opened = True
    monkeypatch.setattr(
        "cephvr.acquisition.camera.basler.get_node",
        lambda _nodes, name: object() if name in values else None,
    )
    monkeypatch.setattr(
        "cephvr.acquisition.camera.basler.set_enum",
        lambda _nodes, name, value: _set_enum(calls, values, name, value),
    )
    monkeypatch.setattr(
        "cephvr.acquisition.camera.basler.read_value",
        lambda _nodes, name: values.get(name),
    )

    assert adapter.read_frame_timing() == "free_running"
    assert calls == [("TriggerSelector", "FrameStart")]


def test_missing_trigger_mode_blocks_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = BaslerCameraAdapter()
    adapter._camera = SimpleNamespace(GetNodeMap=lambda: object())
    adapter._device_info = object()
    adapter._opened = True
    monkeypatch.setattr(
        "cephvr.acquisition.camera.basler.get_node",
        lambda _nodes, name: object() if name == "TriggerSelector" else None,
    )
    with pytest.raises(CameraAdapterError, match="TriggerMode readback is unavailable"):
        adapter.read_frame_timing()


def _set_enum(
    calls: list[tuple[str, str]], values: dict[str, str], name: str, value: str
) -> None:
    calls.append((name, value))
    values[name] = value


def test_rgb_pylon_name_and_device_symbol_resolve_same_layout() -> None:
    native = pylon_pixel_format("RGB8packed", sdk_value=17)
    device = device_pixel_format("RGB8")
    assert native == device
    assert native.sdk_name == "RGB8packed"
    assert native.sdk_value == 17


def test_native_color_result_uses_pylon_registry_not_device_symbol_registry() -> None:
    pylon = SimpleNamespace(PixelType_BGR10packed=42)
    result = native_pixel_format(pylon, 42)
    assert result == pylon_pixel_format("BGR10packed")
    assert result.sdk_name == "BGR10packed"
