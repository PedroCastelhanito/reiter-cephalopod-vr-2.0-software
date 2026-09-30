"""Concrete adapter records implementing the camera contract protocols."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cephvr.acquisition.camera.types import CameraSettings, PixelLayout


@dataclass(frozen=True, slots=True)
class SettingAdjustmentRecord:
    field: str
    requested_display: str
    actual_display: str


@dataclass(frozen=True, slots=True)
class SettingsReadbackRecord:
    actual: CameraSettings
    adjustments: tuple[SettingAdjustmentRecord, ...]
    effective_exposure_us: float | None


class GrabResultRecord:
    """Own one SDK grab result and expose its pixels only until release."""

    def __init__(
        self,
        *,
        valid_image: bool,
        pixels: memoryview | None,
        layout: PixelLayout | None,
        camera_frame_counter: int | None,
        camera_timestamp_ns: int | None,
        error_code: str | None,
        error_message: str | None,
        release_sdk_result: Callable[[], None],
    ) -> None:
        self.valid_image = valid_image
        self.pixels = pixels
        self.layout = layout
        self.camera_frame_counter = camera_frame_counter
        self.camera_timestamp_ns = camera_timestamp_ns
        self.error_code = error_code
        self.error_message = error_message
        self._release_sdk_result = release_sdk_result
        self._released = False

    def release(self) -> None:
        if self._released:
            raise RuntimeError("SDK grab result may be released exactly once")
        self._release_sdk_result()
        self._released = True
