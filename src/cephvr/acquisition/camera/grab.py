"""Pypylon grab-result validation and one-owner lifetime wrapper (A01/A07/A09)."""

from __future__ import annotations

from typing import Any

from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.acquisition.camera.features import sdk_failure
from cephvr.acquisition.camera.native_formats import native_pixel_format
from cephvr.acquisition.camera.records import GrabResultRecord
from cephvr.acquisition.camera.types import (
    NativeMetadataSupport,
    PixelLayout,
    TransportInterface,
)


def wrap_grab_result(
    result: Any,
    pylon: Any,
    interface: TransportInterface,
    metadata: NativeMetadataSupport | None,
) -> GrabResultRecord:
    """Validate one image plane and expose its SDK buffer only until release()."""
    try:
        if not result.GrabSucceeded():
            return GrabResultRecord(
                valid_image=False,
                pixels=None,
                layout=None,
                camera_frame_counter=None,
                camera_timestamp_ns=None,
                error_code=str(result.GetErrorCode()),
                error_message=str(result.GetErrorDescription()),
                release_sdk_result=result.Release,
            )
        pixel_type = int(result.GetPixelType())
        native = native_pixel_format(pylon, pixel_type)
        width, height = int(result.GetWidth()), int(result.GetHeight())
        padding = int(result.GetPaddingX())
        row_min = int(pylon.ComputeBufferSize(pixel_type, width, 1))
        stride = row_min + padding
        image_size = int(result.GetImageSize())
        if width <= 0 or height <= 0 or padding < 0 or stride * height != image_size:
            raise CameraAdapterError(
                "INVALID_LAYOUT", "grab result image plane is inconsistent"
            )
        payload = memoryview(result.GetBuffer())
        if payload.nbytes < image_size:
            raise CameraAdapterError(
                "INVALID_LAYOUT", "grab result buffer is shorter than image plane"
            )
        layout = PixelLayout(width, height, native, stride, image_size)
        descriptor = metadata.camera_clock if metadata is not None else None
        counter_source = (
            descriptor.counter_source if descriptor is not None else "unavailable"
        )
        timestamp_source = (
            descriptor.timestamp_source if descriptor is not None else "unavailable"
        )
        counter_value = (
            _result_chunk_value(result, "ChunkFramecounter")
            if counter_source == "ChunkFramecounter"
            else result.GetBlockID()
            if counter_source == "CGrabResultData.GetBlockID"
            else None
        )
        counter = (
            _chunk_counter(counter_value)
            if counter_source == "ChunkFramecounter"
            else _counter(counter_value, interface)
        )
        timestamp_value = (
            _result_chunk_value(result, "ChunkTimestamp")
            if timestamp_source == "ChunkTimestamp"
            else result.GetTimeStamp()
            if timestamp_source == "CGrabResultData.GetTimeStamp"
            else None
        )
        ticks = (
            _timestamp(timestamp_value)
            if timestamp_source == "CGrabResultData.GetTimeStamp"
            else _chunk_timestamp(timestamp_value)
        )
        timestamp_ns = _to_ns(ticks, metadata)
        return GrabResultRecord(
            valid_image=True,
            pixels=payload[:image_size],
            layout=layout,
            camera_frame_counter=counter,
            camera_timestamp_ns=timestamp_ns,
            error_code=None,
            error_message=None,
            release_sdk_result=result.Release,
        )
    except CameraAdapterError:
        result.Release()
        raise
    except Exception as exc:
        result.Release()
        raise CameraAdapterError(
            "SDK_FAILURE", f"Basler grab result read failed: {exc}"
        ) from exc


def _counter(value: Any, interface: TransportInterface) -> int | None:
    if interface not in ("usb3", "gige"):
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value == (1 << 64) - 1:
        return None
    if interface == "gige" and (value == 0 or value > 65535):
        return None
    return value if 0 <= value < (1 << 64) else None


def _chunk_counter(value: Any) -> int | None:
    return (
        value
        if isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value < (1 << 64)
        else None
    )


def _timestamp(value: Any) -> int | None:
    # GetTimeStamp documents zero as unsupported. UINT64_MAX is not documented
    # as a timestamp sentinel and must be preserved as device evidence.
    if not isinstance(value, int) or isinstance(value, bool) or value == 0:
        return None
    return value if 0 <= value < (1 << 64) else None


def _chunk_timestamp(value: Any) -> int | None:
    return _chunk_counter(value)


def _result_chunk_value(result: Any, name: str) -> int | None:
    try:
        if not result.IsChunkDataAvailable():
            return None
        node = result.GetChunkNode(name)
        if node is None:
            return None
        genicam = __import__("pypylon.genicam", fromlist=["genicam"])
        if not genicam.IsAvailable(node) or not genicam.IsReadable(node):
            return None
        value = node.GetValue()
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    except Exception as exc:
        # Optional chunk absence is frame-local metadata unavailability, not image
        # corruption or a reason to switch source mid-run.
        if type(exc).__name__ in {
            "TimeoutException",
            "DeviceRemovedException",
            "AccessException",
        }:
            raise sdk_failure("chunk_read", exc, field_path=name) from exc
        return None


def _to_ns(ticks: int | None, metadata: NativeMetadataSupport | None) -> int | None:
    if ticks is None or metadata is None or not metadata.timestamp_available:
        return None
    descriptor = metadata.camera_clock
    numerator, denominator = (
        descriptor.tick_period_ns_numerator,
        descriptor.tick_period_ns_denominator,
    )
    if numerator is None or denominator is None or denominator <= 0:
        raise CameraAdapterError(
            "INVALID_SETTING", "camera timestamp descriptor has invalid ratio"
        )
    value = (ticks * numerator + denominator // 2) // denominator
    return value if value < (1 << 63) else None
