"""Lazy pypylon 26.3.1 adapter for one explicitly assigned Basler camera."""

from __future__ import annotations

import importlib
import importlib.metadata
from collections.abc import Callable
from threading import Event
from typing import Any

from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.acquisition.camera.features import (
    get_node,
    read_value,
    set_enum,
)
from cephvr.acquisition.camera.grab import wrap_grab_result
from cephvr.acquisition.camera.metadata import native_metadata
from cephvr.acquisition.camera.native_formats import native_pixel_format
from cephvr.acquisition.camera.settings import (
    apply_settings,
    capabilities,
    read_settings,
)
from cephvr.acquisition.camera.transport import (
    apply_transport_settings,
    read_transport_counters,
)
from cephvr.acquisition.camera.types import (
    CameraCapabilities,
    CameraDeviceIdentity,
    CameraSettings,
    FrameTiming,
    GrabResult,
    NativeMetadataSupport,
    PfsSnapshot,
    PixelLayout,
    PurgeEvidence,
    SettingsReadback,
    TransportCounters,
    TransportInterface,
    TransportSettings,
)
from cephvr.acquisition.camera.wait import PylonWaitGate, WaitOutcome
from cephvr.shared.clock import host_time_ns

_EXPECTED_PYPYLON = "26.3.1"


class BaslerCameraAdapter:
    """Owns a single camera and all its mutable pypylon objects on the caller thread."""

    def __init__(self) -> None:
        self._pylon: Any | None = None
        self._camera: Any | None = None
        self._device_id: str | None = None
        self._device_info: Any | None = None
        self._opened = False
        self._interface: TransportInterface | None = None
        self._timing: str | None = None
        self._grabbing = False
        self._wait_gate = PylonWaitGate()
        self._native_metadata: NativeMetadataSupport | None = None
        self._last_purge_evidence: PurgeEvidence | None = None
        self._terminal_generation_stopped = False
        self._drain_margin_confirmed = False

    def open(self, device_id: str) -> None:
        if not device_id:
            raise CameraAdapterError("INVALID_SETTING", "camera device ID is required")
        if self._camera is not None:
            if self._device_id == device_id and self._opened:
                return
            raise CameraAdapterError(
                "SDK_STATE", "adapter retains unresolved camera ownership"
            )
        pylon = self._sdk()
        try:
            factory = pylon.TlFactory.GetInstance()
            matches = [
                info
                for info in factory.EnumerateDevices()
                if _serial(info) == device_id
            ]
            if len(matches) != 1:
                raise CameraAdapterError(
                    "DEVICE_UNAVAILABLE",
                    f"assigned Basler serial {device_id!r} matched {len(matches)} devices",
                )
            info = matches[0]
            interface = _transport_interface(info)
            camera = pylon.InstantCamera(factory.CreateDevice(info))
            # Retain native ownership before the effectful Open call. A failed Close
            # must remain retryable through this adapter instance.
            self._camera, self._device_info = camera, info
            self._device_id, self._interface = device_id, interface
            try:
                camera.Open()
                self._opened = True
            except Exception as open_error:
                try:
                    camera.Close()
                except Exception as close_error:
                    raise CameraAdapterError(
                        "CLEANUP_UNCONFIRMED",
                        f"camera open failed and Close is unresolved: {close_error}",
                    ) from open_error
                self._clear_device_ownership()
                raise
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("open", exc) from exc

    @property
    def device_open(self) -> bool:
        """Whether this owner has successfully opened its retained device."""
        return self._opened

    def read_device_identity(self) -> CameraDeviceIdentity:
        camera, info = self._require_open()
        try:
            serial = _serial(info)
            model = str(info.GetModelName())
            if not serial or not model:
                raise CameraAdapterError("SDK_STATE", "Basler identity is incomplete")
            return CameraDeviceIdentity(
                self._device_id or "", serial, model, self._interface or "usb3"
            )
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("read_device_identity", exc) from exc

    @property
    def is_grabbing(self) -> bool:
        """Whether this adapter currently owns an active acquisition stream."""
        return self._grabbing

    def capabilities(self) -> CameraCapabilities:
        camera, _ = self._require_open()
        try:
            return capabilities(camera, self._sdk())
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("capabilities", exc) from exc

    def apply_settings(self, settings: CameraSettings) -> SettingsReadback:
        camera, _ = self._require_open()
        try:
            return apply_settings(camera, settings, self._sdk())
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("apply_settings", exc) from exc

    def read_settings(self) -> CameraSettings:
        camera, _ = self._require_open()
        try:
            return read_settings(camera)
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("read_settings", exc) from exc

    def read_frame_timing(self) -> FrameTiming:
        camera, _ = self._require_open()
        try:
            nodes = camera.GetNodeMap()
            selector = get_node(nodes, "TriggerSelector")
            mode = get_node(nodes, "TriggerMode")
            if selector is None or mode is None:
                raise CameraAdapterError(
                    "UNSUPPORTED_FEATURE", "TriggerMode readback is unavailable"
                )
            set_enum(nodes, "TriggerSelector", "FrameStart")
            if read_value(nodes, "TriggerSelector") != "FrameStart":
                raise CameraAdapterError(
                    "SDK_STATE", "TriggerSelector readback differs"
                )
            value = read_value(nodes, "TriggerMode")
            if value == "On":
                return "external_trigger"
            if value == "Off":
                return "free_running"
            raise CameraAdapterError(
                "UNSUPPORTED_FEATURE", f"TriggerMode {value!r} is unsupported"
            )
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("read_frame_timing", exc) from exc

    def apply_transport_settings(
        self, settings: TransportSettings
    ) -> TransportSettings:
        camera, _ = self._require_open()
        if self._grabbing:
            raise CameraAdapterError(
                "SDK_STATE", "transport settings require stopped capture"
            )
        try:
            return apply_transport_settings(
                camera,
                self._interface or "usb3",
                settings,
                importlib.import_module("pypylon.genicam"),
            )
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("apply_transport_settings", exc) from exc

    def read_transport_counters(self) -> TransportCounters:
        camera, _ = self._require_open()
        try:
            return read_transport_counters(camera)
        except Exception as exc:
            raise _sdk_error("read_transport_counters", exc) from exc

    def configure_native_metadata(self) -> NativeMetadataSupport:
        camera, _ = self._require_open()
        try:
            result = native_metadata(
                camera, self._device_id or "", self._interface or "usb3"
            )
            self._native_metadata = result
            return result
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("configure_native_metadata", exc) from exc

    def read_layout(self) -> PixelLayout:
        camera, _ = self._require_open()
        try:
            nodes = camera.GetNodeMap()
            symbol = read_value(nodes, "PixelFormat")
            if symbol is None:
                raise CameraAdapterError(
                    "INVALID_LAYOUT", "camera PixelFormat is unreadable"
                )
            from cephvr.acquisition.camera.native_formats import device_pixel_type

            pixel_type = device_pixel_type(self._sdk(), str(symbol))
            width_value, height_value = (
                read_value(nodes, "Width"),
                read_value(nodes, "Height"),
            )
            if not isinstance(width_value, int) or not isinstance(height_value, int):
                raise CameraAdapterError(
                    "INVALID_LAYOUT", "camera dimensions are unreadable"
                )
            width, height = width_value, height_value
            if width <= 0 or height <= 0:
                raise CameraAdapterError(
                    "INVALID_LAYOUT", "camera dimensions must be positive"
                )
            pylon = self._sdk()
            base_stride = int(pylon.ComputeBufferSize(pixel_type, width, 1))
            padding = int(pylon.ComputePaddingX(base_stride, pixel_type, width))
            row_bytes = int(pylon.ComputeBufferSize(pixel_type, width, 1, padding))
            image_bytes = row_bytes * height
            native = native_pixel_format(self._sdk(), pixel_type)
            return PixelLayout(width, height, native, row_bytes, image_bytes)
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("read_layout", exc) from exc

    def configure_capture(self, timing: FrameTiming, sdk_buffer_count: int) -> None:
        camera, _ = self._require_open()
        if self._grabbing:
            raise CameraAdapterError("SDK_STATE", "capture is already active")
        if timing not in ("external_trigger", "free_running") or sdk_buffer_count < 1:
            raise CameraAdapterError(
                "INVALID_SETTING", "invalid capture timing or SDK buffer count"
            )
        if (
            self._last_purge_evidence is not None
            and not self._last_purge_evidence.accounting_complete
        ):
            raise CameraAdapterError(
                "DRAIN_ACCOUNTING_UNAVAILABLE",
                "prior capture has unknown SDK-buffer discard accounting",
            )
        try:
            self._set_trigger_state(
                "On" if timing == "external_trigger" else "Off", "FrameStart"
            )
            camera.MaxNumBuffer.SetValue(sdk_buffer_count)
            actual = int(camera.MaxNumBuffer.GetValue())
            if actual != sdk_buffer_count:
                raise CameraAdapterError(
                    "INVALID_SETTING", "SDK buffer count readback differs"
                )
            self._timing = timing
            self._terminal_generation_stopped = False
            self._drain_margin_confirmed = False
            self._wait_gate.probe(camera, self._sdk())
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("configure_capture", exc) from exc

    def purge_stale_frames(
        self,
        deadline_monotonic_ns: int,
        *,
        should_continue_drain: Callable[[], bool],
    ) -> PurgeEvidence:
        if not self._grabbing:
            return self._last_purge_evidence or PurgeEvidence(0, None, True)
        try:
            camera, _ = self._require_open()
            result = self._drain_and_stop(
                camera, deadline_monotonic_ns, should_continue_drain
            )
            self._last_purge_evidence = result
            return result
        except Exception as exc:
            raise _sdk_error("purge_stale_frames", exc) from exc

    def begin_terminal_drain(self) -> bool:
        """Stop device generation while preserving SDK result retrieval."""
        if not self._grabbing:
            return False
        camera, _ = self._require_open()
        try:
            self._terminal_generation_stopped = self._stop_device_generation(camera)
            self._drain_margin_confirmed = False
            return self._terminal_generation_stopped
        except Exception as exc:
            raise _sdk_error("begin_terminal_drain", exc) from exc

    def confirm_drain_margin(self) -> None:
        if not self._terminal_generation_stopped or not self._grabbing:
            raise CameraAdapterError(
                "SDK_STATE", "terminal drain margin lacks a stopped generation"
            )
        self._drain_margin_confirmed = True

    def arm_external_trigger(self) -> None:
        camera, _ = self._require_open()
        if self._timing != "external_trigger":
            raise CameraAdapterError(
                "SDK_STATE", "camera was not configured for external triggering"
            )
        if self._grabbing:
            return
        try:
            self._set_trigger_state("On", "FrameStart")
            camera.StartGrabbing(
                self._sdk().GrabStrategy_OneByOne, self._sdk().GrabLoop_ProvidedByUser
            )
            self._grabbing = True
            self._timing = "external_trigger"
            self._install_waits()
        except Exception as exc:
            raise _sdk_error("arm_external_trigger", exc) from exc

    def start_free_running(self) -> None:
        camera, _ = self._require_open()
        if self._timing != "free_running":
            raise CameraAdapterError(
                "SDK_STATE", "camera was not configured for free-running capture"
            )
        if self._grabbing:
            raise CameraAdapterError(
                "SDK_STATE", "free-running camera is already grabbing"
            )
        try:
            self._set_trigger_state("Off", "FrameStart")
            camera.StartGrabbing(
                self._sdk().GrabStrategy_OneByOne, self._sdk().GrabLoop_ProvidedByUser
            )
            self._grabbing = True
            self._timing = "free_running"
            self._install_waits()
        except Exception as exc:
            raise _sdk_error("start_free_running", exc) from exc

    def wait_for_frame_or_control(self, timeout_ns: int) -> WaitOutcome:
        if not self._grabbing:
            raise CameraAdapterError(
                "SDK_STATE", "cannot wait while capture is stopped"
            )
        return self._wait_gate.wait(timeout_ns)

    def wake_control(self) -> None:
        self._wait_gate.wake()

    def clear_control_wake(self) -> None:
        self._wait_gate.clear()

    def wait_for_control(self, timeout_ns: int) -> bool:
        return self._wait_gate.wait_control(timeout_ns)

    def verify_blocking_wait_wakeup(
        self,
        schedule_wake: Callable[[Callable[[], None]], Event],
        timeout_ns: int,
    ) -> None:
        self._wait_gate.verify_blocking_control_wakeup(schedule_wake, timeout_ns)

    def retrieve(self, timeout_ns: int) -> GrabResult | None:
        if not self._grabbing:
            return None
        if timeout_ns < 0:
            raise ValueError("retrieve timeout must be nonnegative")
        timeout_ms = min((timeout_ns + 999_999) // 1_000_000, 0xFFFFFFFE)
        pylon = self._sdk()
        result: Any | None = None
        wrapper_owns_release = False
        try:
            camera, _ = self._require_open()
            result = camera.RetrieveResult(
                int(timeout_ms), pylon.TimeoutHandling_Return
            )
            if result is None:
                return None
            if not result.IsValid():
                result.Release()
                result = None
                return None
            wrapper_owns_release = True
            return self._wrap_grab_result(result)
        except Exception as exc:
            try:
                if result is not None and not wrapper_owns_release:
                    result.Release()
            except Exception:
                pass  # Best effort: the retrieve failure below is the reported error.
            raise _sdk_error("retrieve", exc) from exc

    def stop_capture(
        self,
        deadline_monotonic_ns: int,
        *,
        should_continue_drain: Callable[[], bool],
    ) -> PurgeEvidence:
        if not self._grabbing:
            return self._last_purge_evidence or PurgeEvidence(0, None, True)
        try:
            camera, _ = self._require_open()
            result = self._drain_and_stop(
                camera, deadline_monotonic_ns, should_continue_drain
            )
            self._last_purge_evidence = result
            return result
        except Exception as exc:
            raise _sdk_error("stop_capture", exc) from exc

    def close(self) -> None:
        self.release_device()
        self.close_control()

    def close_control(self) -> None:
        """Close only the native control event after the owner thread has joined."""
        self._wait_gate.close()

    def release_device(self) -> None:
        """Close the assigned device while preserving the worker control event."""
        camera = self._camera
        if camera is None:
            return
        try:
            if self._grabbing:
                camera.StopGrabbing()
                self._grabbing = False
            self._wait_gate.remove()
            if camera.IsOpen():
                camera.Close()
            self._clear_device_ownership()
        except Exception as exc:
            raise _sdk_error("close", exc) from exc

    def apply_pfs_snapshot(self, snapshot: PfsSnapshot) -> SettingsReadback:
        camera, _ = self._require_open()
        try:
            self._sdk().FeaturePersistence.LoadFromString(
                snapshot.text, camera.GetNodeMap(), True
            )
            return _settings_readback(self.read_settings(), camera)
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("apply_pfs_snapshot", exc) from exc

    def capture_pfs_snapshot(self) -> PfsSnapshot:
        camera, _ = self._require_open()
        try:
            return PfsSnapshot(
                str(self._sdk().FeaturePersistence.SaveToString(camera.GetNodeMap()))
            )
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("capture_pfs_snapshot", exc) from exc

    def import_pfs(self, path: str) -> SettingsReadback:
        camera, _ = self._require_open()
        try:
            self._sdk().FeaturePersistence.Load(path, camera.GetNodeMap(), True)
            return _settings_readback(self.read_settings(), camera)
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("import_pfs", exc) from exc

    def export_pfs(self, new_path: str) -> None:
        camera, _ = self._require_open()
        try:
            self._sdk().FeaturePersistence.Save(new_path, camera.GetNodeMap())
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise _sdk_error("export_pfs", exc) from exc

    def _wrap_grab_result(self, result: Any) -> GrabResult:
        return wrap_grab_result(
            result, self._sdk(), self._interface or "usb3", self._native_metadata
        )

    def _drain_and_stop(
        self,
        camera: Any,
        deadline_ns: int,
        should_continue_drain: Callable[[], bool],
    ) -> PurgeEvidence:
        retrieved_count = 0
        last_counter: int | None = None
        terminal_known = (
            self._terminal_generation_stopped or self._stop_device_generation(camera)
        )
        margin_confirmed = self._drain_margin_confirmed
        drained_to_empty = False
        stopped_in_time = False
        try:
            if not terminal_known:
                # Without an applicable AcquisitionStop command, draining while the
                # device keeps generating is unbounded and cannot prove closure.
                camera.StopGrabbing()
                stopped_in_time = host_time_ns() <= deadline_ns
                self._grabbing = False
                self._wait_gate.remove()
                _ = stopped_in_time
                return PurgeEvidence(None, None, False)
            while True:
                if host_time_ns() >= deadline_ns or not should_continue_drain():
                    break
                ready = int(camera.NumReadyBuffers.GetValue())
                if ready == 0:
                    drained_to_empty = True
                    break
                result = self.retrieve(0)
                if result is None:
                    break
                if result.camera_frame_counter is not None:
                    last_counter = result.camera_frame_counter
                result.release()
                retrieved_count += 1
            camera.StopGrabbing()
            stopped_in_time = host_time_ns() <= deadline_ns
            self._grabbing = False
            self._wait_gate.remove()
            if int(camera.NumReadyBuffers.GetValue()) != 0:
                terminal_known = False
        except Exception as exc:
            raise _sdk_error("drain_and_stop", exc) from exc
        # The SDK may flush buffers internally on StopGrabbing. No pinned counter
        # exposes that hidden portion, so the total and accounting outcome stay
        # unknown even after the observable result queue drains.
        accounting_complete = (
            terminal_known and margin_confirmed and drained_to_empty and stopped_in_time
        )
        if accounting_complete:
            return PurgeEvidence(retrieved_count, last_counter, True)
        return PurgeEvidence(None, last_counter, False)

    def _stop_device_generation(self, camera: Any) -> bool:
        node = get_node(camera.GetNodeMap(), "AcquisitionStop")
        if node is None:
            return False
        genicam = importlib.import_module("pypylon.genicam")
        if not genicam.IsWritable(node):
            return False
        execute = getattr(node, "Execute", None)
        if not callable(execute):
            return False
        execute()
        return True

    def _set_trigger_state(self, mode: str, selector: str) -> None:
        camera, _ = self._require_open()
        nodes = camera.GetNodeMap()
        if (
            get_node(nodes, "TriggerMode") is None
            or get_node(nodes, "TriggerSelector") is None
        ):
            raise CameraAdapterError(
                "UNSUPPORTED_FEATURE", "TriggerMode and TriggerSelector are required"
            )
        set_enum(nodes, "TriggerSelector", selector)
        if read_value(nodes, "TriggerSelector") != selector:
            raise CameraAdapterError("SDK_STATE", "TriggerSelector readback differs")
        set_enum(nodes, "TriggerMode", mode)
        if read_value(nodes, "TriggerMode") != mode:
            raise CameraAdapterError("SDK_STATE", "TriggerMode readback differs")

    def _install_waits(self) -> None:
        camera, _ = self._require_open()
        self._wait_gate.bind(camera, self._sdk())

    def _sdk(self) -> Any:
        if self._pylon is None:
            try:
                version = importlib.metadata.version("pypylon")
                if version != _EXPECTED_PYPYLON:
                    raise CameraAdapterError(
                        "SDK_UNAVAILABLE",
                        f"pypylon {version} is unsupported; expected {_EXPECTED_PYPYLON}",
                    )
                self._pylon = importlib.import_module("pypylon.pylon")
            except CameraAdapterError:
                raise
            except Exception as exc:
                raise CameraAdapterError(
                    "SDK_UNAVAILABLE",
                    f"pypylon {_EXPECTED_PYPYLON} is unavailable: {exc}",
                ) from exc
        return self._pylon

    def _require_open(self) -> tuple[Any, Any]:
        if self._camera is None or self._device_info is None or not self._opened:
            raise CameraAdapterError("SDK_STATE", "assigned camera is not open")
        return self._camera, self._device_info

    def _clear_device_ownership(self) -> None:
        self._camera = None
        self._device_info = None
        self._device_id = None
        self._interface = None
        self._opened = False


def _serial(info: Any) -> str:
    return str(info.GetSerialNumber())


def _transport_interface(info: Any) -> TransportInterface:
    value = str(info.GetDeviceClass())
    if value == "BaslerUsb":
        return "usb3"
    if value == "BaslerGigE":
        return "gige"
    raise CameraAdapterError(
        "UNSUPPORTED_FEATURE", f"unsupported Basler transport class {value!r}"
    )


def _settings_readback(settings: CameraSettings, camera: Any) -> SettingsReadback:
    from cephvr.acquisition.camera.records import SettingsReadbackRecord

    nodes = camera.GetNodeMap()
    exposure = read_value(nodes, "BslEffectiveExposureTime")
    if not isinstance(exposure, (int, float)) or isinstance(exposure, bool):
        exposure = read_value(nodes, "EffectiveExposureTime")
    effective = (
        float(exposure)
        if isinstance(exposure, (int, float)) and not isinstance(exposure, bool)
        else None
    )
    return SettingsReadbackRecord(settings, (), effective)


def _sdk_error(operation: str, exc: Exception) -> CameraAdapterError:
    name = type(exc).__name__
    code = {
        "TimeoutException": "SDK_TIMEOUT",
        "DeviceRemovedException": "DEVICE_UNAVAILABLE",
        "AccessException": "SDK_ACCESS",
        "LogicalErrorException": "SDK_STATE",
        "OutOfMemoryException": "RESOURCE_EXHAUSTED",
    }.get(name, "SDK_FAILURE")
    return CameraAdapterError(code, f"Basler SDK {operation} failed ({name}): {exc}")
