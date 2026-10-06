"""Exact SDK selection, required camera features and native pixel layouts."""

from __future__ import annotations

from threading import Event
from types import SimpleNamespace

import pytest

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.acquisition.camera.features import capability, read_value, write_value
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


def test_absent_sdk_node_is_optional_only_for_readback() -> None:
    class LogicalErrorException(Exception):
        pass

    def missing(_):
        raise LogicalErrorException("Node not existing (file 'genicam_wrap.cpp')")

    nodes = SimpleNamespace(GetNode=missing)
    assert read_value(nodes, "BslEffectiveExposureTime") is None
    with pytest.raises(CameraAdapterError, match="required mapped feature"):
        write_value(nodes, "TriggerSource", "Line4")


def test_other_sdk_lookup_failure_is_not_hidden() -> None:
    class LogicalErrorException(Exception):
        pass

    def invalid(_):
        raise LogicalErrorException("Device state is invalid")

    with pytest.raises(CameraAdapterError, match="Device state is invalid"):
        read_value(SimpleNamespace(GetNode=invalid), "Gain")


@pytest.mark.parametrize("has_increment", [False, True])
def test_float_capability_respects_optional_increment(
    monkeypatch, has_increment
) -> None:
    def increment():
        assert has_increment, "GetInc is invalid without a constant increment"
        return 0.1

    node = SimpleNamespace(
        GetValue=lambda: 2.0,
        GetMin=lambda: 0.0,
        GetMax=lambda: 12.0,
        HasInc=lambda: has_increment,
        GetInc=increment,
    )
    monkeypatch.setattr("cephvr.acquisition.camera.features.available", lambda _: True)
    monkeypatch.setattr("cephvr.acquisition.camera.features.readable", lambda _: True)
    monkeypatch.setattr("cephvr.acquisition.camera.features.writable", lambda _: True)
    result = capability(SimpleNamespace(GetNode=lambda _: node), "Gain", unit="dB")
    assert result.increment == (0.1 if has_increment else None)
    assert result.minimum == 0.0
    assert result.maximum == 12.0


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


@pytest.mark.parametrize("already_open", [False, True])
@pytest.mark.parametrize("serial", ["CAM-1", "wrong"])
def test_connection_check_verifies_identity_and_preserves_existing_owner(
    already_open: bool,
    serial: str,
) -> None:
    from cephvr.acquisition.v1 import messages_pb2 as acq
    from cephvr.acquisition.worker.camera_configuration import WorkerCameraConfiguration

    calls: list[str] = []
    adapter = SimpleNamespace(
        device_open=already_open,
        open=lambda device: calls.append(f"open:{device}"),
        read_device_identity=lambda: SimpleNamespace(physical_id=serial),
        release_device=lambda: calls.append("close"),
    )
    owner = WorkerCameraConfiguration(adapter, SimpleNamespace(), lambda: False)
    request = acq.WorkerEditCamera(kind=acq.CAMERA_EDIT_KIND_TEST_CONNECTION)
    request.requested.device_id = "CAM-1"
    if serial == "wrong":
        with pytest.raises(RuntimeError, match="identity differs"):
            owner.edit(request, acq.WorkerOperationReport())
    else:
        owner.edit(request, acq.WorkerOperationReport())
    assert calls == ["open:CAM-1"] + ([] if already_open else ["close"])


def test_connection_check_never_reports_success_after_release_failure() -> None:
    from cephvr.acquisition.v1 import messages_pb2 as acq
    from cephvr.acquisition.worker.camera_configuration import WorkerCameraConfiguration

    def failed_close() -> None:
        raise RuntimeError("native close failed")

    owner = WorkerCameraConfiguration(
        SimpleNamespace(
            device_open=False,
            open=lambda _: None,
            read_device_identity=lambda: SimpleNamespace(physical_id="CAM-1"),
            release_device=failed_close,
        ),
        SimpleNamespace(),
        lambda: False,
    )
    request = acq.WorkerEditCamera(kind=acq.CAMERA_EDIT_KIND_TEST_CONNECTION)
    request.requested.device_id = "CAM-1"
    with pytest.raises(RuntimeError, match="native close failed"):
        owner.edit(request, acq.WorkerOperationReport())


def test_first_pfs_import_opens_assigned_camera_and_retains_sdk_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.acquisition.v1 import camera_pb2 as camera
    from cephvr.acquisition.v1 import messages_pb2 as acq
    from cephvr.acquisition.worker import camera_configuration as module

    calls = []
    adapter = SimpleNamespace(
        open=lambda serial: calls.append(("open", serial)),
        import_pfs=lambda path: calls.append(("import", path)),
    )
    resolved = camera.CameraResolvedState(configuration_revision=4)
    resolved.applied.device_id = "CAM-1"
    resolved.applied.pfs_baseline.text = "SDK snapshot"
    monkeypatch.setattr(
        module, "resolve_imported_camera", lambda adapter, requested, revision: resolved
    )
    owner = module.WorkerCameraConfiguration(adapter, SimpleNamespace(), lambda: False)
    request = acq.WorkerEditCamera(
        kind=acq.CAMERA_EDIT_KIND_IMPORT_PFS,
        path="preset.pfs",
        configuration_revision=4,
    )
    request.requested.device_id = "CAM-1"
    report = acq.WorkerOperationReport()
    owner.edit(request, report)
    assert calls == [("open", "CAM-1"), ("import", "preset.pfs")]
    assert report.resolved_camera.applied.pfs_baseline.text == "SDK snapshot"
