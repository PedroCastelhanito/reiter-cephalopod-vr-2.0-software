"""Pinned pypylon joint result/control wait with manual-reset command priority."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event
from typing import Any, Literal

from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.platform.windows.events import ManualResetEvent

WaitOutcome = Literal["frame", "control", "timeout"]


class PylonWaitGate:
    """Own SDK wait wrappers; only the camera owner binds or removes wait objects."""

    def __init__(self) -> None:
        self._event: ManualResetEvent | None = None
        self._waits: Any | None = None
        self._control_waits: Any | None = None
        self._control_wait: Any | None = None
        self._camera_wait: Any | None = None
        self._pylon: Any | None = None
        self.initialize_event()

    def initialize_event(self) -> None:
        """Create the native command wake before endpoint registration or SDK load."""
        if self._event is None:
            self._event = ManualResetEvent.create()

    def probe(self, camera: Any, pylon: Any) -> None:
        """Check the exact 26.3.1 no-index wait binding before Setup Ready."""
        self.initialize_event()
        event = ManualResetEvent.create()
        control_wait: Any | None = None
        camera_wait = camera.GetGrabResultWaitObject()
        if not camera_wait.IsValid():
            event.close()
            raise CameraAdapterError(
                "SDK_UNAVAILABLE", "pypylon grab-result wait object is invalid"
            )
        waits = pylon.WaitObjects()
        control_only: Any | None = None
        self._pylon = pylon
        try:
            # A stopped camera may keep its result wait object signaled. The probe
            # verifies the Python no-index overload with our private event and does
            # not interpret the inactive camera object's signal as a result.
            event.set()
            control_wait = pylon.WaitObject(event.native_handle, True)
            waits.Add(camera_wait)
            waits.Add(control_wait)
            ready = waits.WaitForAny(0)
            if not ready or not event.is_set():
                raise CameraAdapterError(
                    "SDK_UNAVAILABLE", "pypylon cannot wait on Win32 control event"
                )
            control_only = pylon.WaitObjects()
            control_only.Add(control_wait)
            if not control_only.WaitForAny(0):
                raise CameraAdapterError(
                    "SDK_UNAVAILABLE", "pypylon control-only wait is unavailable"
                )
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise CameraAdapterError(
                "SDK_UNAVAILABLE", f"pypylon joint wait binding is incompatible: {exc}"
            ) from exc
        finally:
            waits.RemoveAll()
            if control_only is not None:
                control_only.RemoveAll()
            event.close()

    def bind(self, camera: Any, pylon: Any) -> None:
        self.remove()
        if self._event is None:
            raise CameraAdapterError(
                "SDK_STATE", "control event was not probed during setup"
            )
        event = self._event
        self._pylon = pylon
        self._camera_wait = camera.GetGrabResultWaitObject()
        self._control_wait = pylon.WaitObject(event.native_handle, True)
        if not self._camera_wait.IsValid() or not self._control_wait.IsValid():
            self.remove()
            raise CameraAdapterError(
                "SDK_UNAVAILABLE", "joint wait contains an invalid wait object"
            )
        self._waits = pylon.WaitObjects()
        self._waits.Add(self._camera_wait)
        self._waits.Add(self._control_wait)

    def wait(self, timeout_ns: int) -> WaitOutcome:
        if timeout_ns < 0:
            raise ValueError("wait timeout must be nonnegative")
        if self._waits is None or self._event is None:
            raise CameraAdapterError("SDK_STATE", "joint wait is not active")
        timeout_ms = min((timeout_ns + 999_999) // 1_000_000, 0xFFFFFFFE)
        try:
            if not self._waits.WaitForAny(timeout_ms):
                return "timeout"
            return "control" if self._event.is_set() else "frame"
        except Exception as exc:
            raise CameraAdapterError(
                "SDK_FAILURE", f"Basler joint wait failed: {exc}"
            ) from exc

    def wake(self) -> None:
        if self._event is None:
            raise CameraAdapterError(
                "SDK_STATE", "control wake event is not initialized"
            )
        self._event.set()

    def wait_control(self, timeout_ns: int) -> bool:
        if timeout_ns < 0:
            raise ValueError("control wait timeout must be nonnegative")
        if self._control_waits is None:
            # Before camera preparation, the already-created command event still
            # wakes Resolve/Edit/Cleanup. This waits on that event directly; the
            # active capture path always uses the SDK joint WaitObjects binding.
            if self._event is None:
                raise CameraAdapterError("SDK_STATE", "control event is unavailable")
            return self._event.wait(timeout_ns)
        timeout_ms = min((timeout_ns + 999_999) // 1_000_000, 0xFFFFFFFE)
        try:
            return bool(self._control_waits.WaitForAny(timeout_ms))
        except Exception as exc:
            raise CameraAdapterError(
                "SDK_FAILURE", f"Basler control-only wait failed: {exc}"
            ) from exc

    def verify_blocking_control_wakeup(
        self,
        schedule_wake: Callable[[Callable[[], None]], Event],
        timeout_ns: int,
    ) -> None:
        """Prove a blocked SDK wait releases the GIL for the control event loop."""
        if timeout_ns <= 0 or self._pylon is None:
            raise CameraAdapterError(
                "SDK_UNAVAILABLE", "blocking SDK control wait is not prepared"
            )
        event = ManualResetEvent.create()
        waits: Any | None = None
        try:
            wait_object = self._pylon.WaitObject(event.native_handle, True)
            waits = self._pylon.WaitObjects()
            waits.Add(wait_object)
            acknowledgement = schedule_wake(event.set)
        except Exception as exc:
            event.close()
            raise CameraAdapterError(
                "SDK_UNAVAILABLE", f"pypylon wait handshake setup failed: {exc}"
            ) from exc
        timeout_ms = min((timeout_ns + 999_999) // 1_000_000, 0xFFFFFFFE)
        try:
            ready = waits.WaitForAny(timeout_ms)
            if not ready or not event.is_set() or not acknowledgement.is_set():
                raise CameraAdapterError(
                    "SDK_UNAVAILABLE",
                    "pypylon blocking control wait did not release the GIL",
                )
        except CameraAdapterError:
            raise
        except Exception as exc:
            raise CameraAdapterError(
                "SDK_UNAVAILABLE", f"pypylon blocking wait handshake failed: {exc}"
            ) from exc
        finally:
            if waits is not None:
                waits.RemoveAll()
            event.close()

    def clear(self) -> None:
        if self._event is not None:
            self._event.clear()

    def remove(self) -> None:
        waits, self._waits = self._waits, None
        if waits is not None:
            waits.RemoveAll()
        self._camera_wait = None
        self._control_wait = None
        self._pylon = None

    def close(self) -> None:
        self.remove()
        if self._control_waits is not None:
            self._control_waits.RemoveAll()
            self._control_waits = None
        if self._event is not None:
            self._event.close()
            self._event = None
