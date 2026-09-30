"""Typed protobuf/camera boundary for exact worker resolution (A01/A10)."""

from __future__ import annotations

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.camera.types import (
    CameraCapabilities,
    CameraDeviceIdentity,
    CameraGain,
    CameraRoi,
    CameraSettings,
    EnumCapability,
    FloatCapability,
    FrameTiming,
    GainCapability,
    IntegerCapability,
    NativeMetadataSupport,
    PfsSnapshot,
    PixelLayout,
    TransportOverride,
    TransportSettings,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq


def resolve_camera(
    adapter: BaslerCameraAdapter,
    request: acq.WorkerResolveCamera,
) -> camera.CameraResolvedState:
    """Open only the assigned device, apply its request, and serialize actual readback."""
    if not request.HasField("configuration_revision"):
        raise ValueError("camera resolution requires a configuration revision")
    if not request.HasField("requested") or not request.requested.device_id:
        raise ValueError("camera resolution requires the assigned device")
    requested = request.requested
    adapter.open(requested.device_id)
    if requested.HasField("pfs_baseline"):
        adapter.apply_pfs_snapshot(PfsSnapshot(requested.pfs_baseline.text))
    applied = adapter.apply_settings(settings_from_wire(requested.settings))
    if not requested.HasField("frame_timing"):
        raise ValueError("assigned camera frame timing is unresolved")
    frame_timing = _frame_timing_from_wire(requested.frame_timing)
    # Apply and read back TriggerMode at resolution so the adopted applied record
    # cannot claim free-run merely because TriggerSource still names a line.
    adapter.configure_capture(frame_timing, 1)
    transport = adapter.apply_transport_settings(
        transport_from_wire(request.transport)
        if request.HasField("transport")
        else TransportSettings(())
    )
    metadata = adapter.configure_native_metadata()
    layout = adapter.read_layout()
    return resolved_state_to_wire(
        configuration_revision=request.configuration_revision,
        device=adapter.read_device_identity(),
        requested_device=requested,
        applied=applied.actual,
        capabilities=adapter.capabilities(),
        transport=transport,
        layout=layout,
        metadata=metadata,
        effective_exposure_us=applied.effective_exposure_us,
    )


def resolve_imported_camera(
    adapter: BaslerCameraAdapter,
    requested_device: camera.CameraDeviceConfiguration,
    configuration_revision: int,
) -> camera.CameraResolvedState:
    """Serialize actual post-import readback without reapplying old settings."""
    applied = adapter.read_settings()
    timing = adapter.read_frame_timing()
    requested = camera.CameraDeviceConfiguration()
    requested.CopyFrom(requested_device)
    requested.settings.CopyFrom(settings_to_wire(applied))
    requested.frame_timing = (
        camera.FRAME_TIMING_EXTERNAL_TRIGGER
        if timing == "external_trigger"
        else camera.FRAME_TIMING_FREE_RUNNING
    )
    requested.pfs_baseline.text = adapter.capture_pfs_snapshot().text
    transport = adapter.apply_transport_settings(TransportSettings(()))
    metadata = adapter.configure_native_metadata()
    layout = adapter.read_layout()
    return resolved_state_to_wire(
        configuration_revision=configuration_revision,
        device=adapter.read_device_identity(),
        requested_device=requested,
        applied=applied,
        capabilities=adapter.capabilities(),
        transport=transport,
        layout=layout,
        metadata=metadata,
        effective_exposure_us=applied.exposure_us,
    )


def settings_from_wire(source: camera.CameraSettings) -> CameraSettings:
    gain: CameraGain | None = None
    if source.HasField("gain"):
        value_kind = source.gain.WhichOneof("value")
        if value_kind == "decimal_value":
            value: int | float = source.gain.decimal_value
        elif value_kind == "integer_value":
            value = source.gain.integer_value
        else:
            raise ValueError("camera gain value is required")
        gain = CameraGain(
            value,
            source.gain.unit,
            source.gain.selector if source.gain.HasField("selector") else None,
        )
    roi = None
    if source.HasField("roi"):
        roi = CameraRoi(
            source.roi.width if source.roi.HasField("width") else None,
            source.roi.height if source.roi.HasField("height") else None,
            source.roi.offset_x if source.roi.HasField("offset_x") else None,
            source.roi.offset_y if source.roi.HasField("offset_y") else None,
        )
    return CameraSettings(
        source.exposure_us if source.HasField("exposure_us") else None,
        gain,
        source.frame_rate_hz if source.HasField("frame_rate_hz") else None,
        roi,
        source.pixel_format if source.HasField("pixel_format") else None,
        source.trigger_selector if source.HasField("trigger_selector") else None,
        source.trigger_source if source.HasField("trigger_source") else None,
        source.trigger_activation if source.HasField("trigger_activation") else None,
        source.exposure_duration_mode
        if source.HasField("exposure_duration_mode")
        else None,
    )


def _frame_timing_from_wire(value: int) -> FrameTiming:
    if value == camera.FRAME_TIMING_EXTERNAL_TRIGGER:
        return "external_trigger"
    if value == camera.FRAME_TIMING_FREE_RUNNING:
        return "free_running"
    raise ValueError("assigned camera frame timing is unspecified")


def transport_from_wire(source: camera.CameraTransportSettings) -> TransportSettings:
    result: list[TransportOverride] = []
    for override in source.overrides:
        kind = override.WhichOneof("value")
        if kind == "boolean":
            value: bool | int | float | str = override.boolean
        elif kind == "integer":
            value = override.integer
        elif kind == "decimal":
            value = override.decimal
        elif kind == "enum_symbol":
            value = override.enum_symbol
        else:
            raise ValueError(f"transport override {override.sdk_name!r} has no value")
        result.append(TransportOverride(override.sdk_name, value))
    return TransportSettings(tuple(result))


def resolved_state_to_wire(
    *,
    configuration_revision: int,
    device: CameraDeviceIdentity,
    requested_device: camera.CameraDeviceConfiguration,
    applied: CameraSettings,
    capabilities: CameraCapabilities,
    transport: TransportSettings,
    layout: PixelLayout,
    metadata: NativeMetadataSupport,
    effective_exposure_us: float | None,
) -> camera.CameraResolvedState:
    result = camera.CameraResolvedState(configuration_revision=configuration_revision)
    result.device.CopyFrom(device_to_wire(device))
    result.applied.CopyFrom(requested_device)
    result.applied.settings.CopyFrom(settings_to_wire(applied))
    result.capabilities.CopyFrom(capabilities_to_wire(capabilities))
    result.transport.CopyFrom(transport_to_wire(transport))
    result.layout.width = layout.width
    result.layout.height = layout.height
    result.layout.pixel_format = layout.pixel_format.sdk_name
    result.layout.row_stride_bytes = layout.row_stride_bytes
    result.layout.image_payload_bytes = layout.image_payload_bytes
    result.native_timestamp_available = metadata.timestamp_available
    result.native_counter_available = metadata.frame_counter_available
    result.camera_clock.CopyFrom(clock_to_wire(metadata))
    for warning in metadata.warnings:
        item = result.metadata_diagnostics.add(
            code=warning.code,
            details=warning.details,
        )
        if warning.sdk_code is not None:
            item.sdk_code = warning.sdk_code
        result.metadata_warnings.append(warning.details)
    if effective_exposure_us is not None:
        result.effective_exposure_us = effective_exposure_us
    return result


def settings_to_wire(source: CameraSettings) -> camera.CameraSettings:
    result = camera.CameraSettings()
    if source.exposure_us is not None:
        result.exposure_us = source.exposure_us
    if source.gain is not None:
        if isinstance(source.gain.value, int):
            result.gain.integer_value = source.gain.value
        else:
            result.gain.decimal_value = source.gain.value
        result.gain.unit = source.gain.unit
        if source.gain.selector is not None:
            result.gain.selector = source.gain.selector
    if source.frame_rate_hz is not None:
        result.frame_rate_hz = source.frame_rate_hz
    if source.roi is not None:
        for name in ("width", "height", "offset_x", "offset_y"):
            value = getattr(source.roi, name)
            if value is not None:
                setattr(result.roi, name, value)
    for name in (
        "pixel_format",
        "trigger_selector",
        "trigger_source",
        "trigger_activation",
        "exposure_duration_mode",
    ):
        value = getattr(source, name)
        if value is not None:
            setattr(result, name, value)
    return result


def device_to_wire(source: CameraDeviceIdentity) -> camera.CameraDeviceIdentity:
    return camera.CameraDeviceIdentity(
        configured_id=source.configured_id,
        physical_id=source.physical_id,
        model=source.model,
        transport_interface=source.transport_interface,
    )


def capabilities_to_wire(source: CameraCapabilities) -> camera.CameraCapabilities:
    result = camera.CameraCapabilities()
    _float_to_wire(source.exposure_us, result.exposure_us)
    _gain_to_wire(source.gain, result.gain)
    _float_to_wire(source.frame_rate_hz, result.frame_rate_hz)
    for name in ("width", "height", "offset_x", "offset_y"):
        _integer_to_wire(getattr(source.roi, name), getattr(result.roi, name))
    for name in (
        "pixel_format",
        "trigger_selector",
        "trigger_source",
        "trigger_activation",
        "exposure_duration_mode",
    ):
        _enum_to_wire(getattr(source, name), getattr(result, name))
    if source.trigger_rate_limit.maximum_hz is not None:
        result.trigger_rate_limit.maximum_hz = source.trigger_rate_limit.maximum_hz
    result.trigger_rate_limit.evidence = source.trigger_rate_limit.evidence
    return result


def transport_to_wire(source: TransportSettings) -> camera.CameraTransportSettings:
    result = camera.CameraTransportSettings()
    for item in source.overrides:
        override = result.overrides.add(sdk_name=item.sdk_name)
        if isinstance(item.value, bool):
            override.boolean = item.value
        elif isinstance(item.value, int):
            override.integer = item.value
        elif isinstance(item.value, float):
            override.decimal = item.value
        else:
            override.enum_symbol = item.value
    return result


def clock_to_wire(source: NativeMetadataSupport) -> camera.CameraClockDescriptor:
    value = source.camera_clock
    result = camera.CameraClockDescriptor(
        device_id=value.device_id,
        timestamp_source=value.timestamp_source,
        timestamp_semantics=value.timestamp_semantics,
        reset_semantics=value.reset_semantics,
        wrap_semantics=value.wrap_semantics,
        unavailable_reason=value.unavailable_reason,
        counter_source=value.counter_source,
        counter_semantics=value.counter_semantics,
        counter_wrap_semantics=value.counter_wrap_semantics,
        counter_unavailable_reason=value.counter_unavailable_reason,
    )
    result.conversion_available = value.conversion_available
    if value.tick_period_ns_numerator is not None:
        result.tick_period_ns_numerator = value.tick_period_ns_numerator
    if value.tick_period_ns_denominator is not None:
        result.tick_period_ns_denominator = value.tick_period_ns_denominator
    if value.counter_width_bits is not None:
        result.counter_width_bits = value.counter_width_bits
    return result


def _float_to_wire(source: FloatCapability, target: camera.FloatCapability) -> None:
    target.access = _access(source.access)
    target.unit = source.unit
    for name in ("minimum", "maximum", "increment"):
        value = getattr(source, name)
        if value is not None:
            setattr(target, name, value)


def _integer_to_wire(
    source: IntegerCapability, target: camera.IntegerCapability
) -> None:
    target.access = _access(source.access)
    target.unit = source.unit
    for name in ("minimum", "maximum", "increment"):
        value = getattr(source, name)
        if value is not None:
            setattr(target, name, value)


def _enum_to_wire(source: EnumCapability, target: camera.EnumCapability) -> None:
    target.access = _access(source.access)
    for choice in source.choices:
        target.choices.add(value=choice.value, sdk_symbol=choice.sdk_symbol)


def _gain_to_wire(source: GainCapability, target: camera.GainCapability) -> None:
    if isinstance(source.numeric, FloatCapability):
        _float_to_wire(source.numeric, target.decimal)
    elif isinstance(source.numeric, IntegerCapability):
        _integer_to_wire(source.numeric, target.integer)
    _enum_to_wire(source.selector, target.selector)


def _access(value: str) -> camera.FeatureAccess:
    mapping = {
        "unavailable": camera.FeatureAccess.FEATURE_ACCESS_UNAVAILABLE,
        "read_only": camera.FeatureAccess.FEATURE_ACCESS_READ_ONLY,
        "read_write": camera.FeatureAccess.FEATURE_ACCESS_READ_WRITE,
    }
    try:
        return mapping[value]
    except KeyError as exc:
        raise ValueError(f"unsupported camera feature access {value!r}") from exc
