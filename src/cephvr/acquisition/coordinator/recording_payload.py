"""Build the saving camera's complete immutable recording Setup payload."""

from __future__ import annotations

import math
import shutil
from collections.abc import Callable
from pathlib import Path

from cephvr.acquisition.camera.native_formats import pylon_pixel_format
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.control.v1 import types_pb2 as control

ExecutableLookup = Callable[[str], str | None]


def build_recording_settings(
    settings: control.AcquisitionSettings,
    resolved: camera.CameraResolvedState,
    file_policies: runtime.AcquisitionFilePolicies,
    role: camera.CameraRole,
    *,
    session_config_reference: str,
    nominal_frame_rate_hz: float,
    executable_lookup: ExecutableLookup = shutil.which,
) -> acq.RecordingSettings | None:
    """Resolve recording policy and tools for one controller-confirmed camera.

    Saving-off cameras need neither encoder discovery nor capability setup. For a
    saving camera this binds only data already resolved by configuration/Setup;
    recording validation and device capability admission remain worker-owned.
    """
    selected = _selected_camera(settings, role)
    if not selected.HasField("enabled") or not selected.enabled:
        return None
    if not selected.HasField("save_video") or not selected.save_video:
        return None
    _validate_resolved_device(selected, resolved)
    if not selected.HasField("ffmpeg_args"):
        raise ValueError(f"{_role_name(role)} recording arguments are unresolved")
    if not session_config_reference or "\x00" in session_config_reference:
        raise ValueError("session configuration reference must be nonempty text")
    session_config_reference.encode("utf-8", "strict")
    if not math.isfinite(nominal_frame_rate_hz) or nominal_frame_rate_hz <= 0:
        raise ValueError("recording nominal frame rate must be finite and positive")

    _camera_policy(file_policies, role)
    for field in (
        "frame_log_sync_interval_ns",
        "video_sync_interval_ns",
        "fragment_target_ns",
        "encoder_stall_timeout_ns",
    ):
        if not file_policies.HasField(field) or getattr(file_policies, field) <= 0:
            raise ValueError(f"acquisition file policy {field} is unresolved")
    if not settings.HasField("recording_options"):
        raise ValueError("acquisition recording options are unresolved")
    options = settings.recording_options
    for field in (
        "pending_records_capacity",
        "diagnostic_tail_max_lines",
        "diagnostic_tail_max_bytes",
    ):
        if not options.HasField(field) or getattr(options, field) <= 0:
            raise ValueError(f"recording option {field} must be present and positive")
    if (
        not settings.HasField("recording_queue_frames")
        or settings.recording_queue_frames <= 0
    ):
        raise ValueError("recording queue capacity is unresolved")

    depth = _recording_depth(selected, resolved)
    queue_frames = _queue_capacity(settings, nominal_frame_rate_hz)
    result = acq.RecordingSettings(
        ffmpeg_executable=_resolve_executable("ffmpeg", executable_lookup),
        ffprobe_executable=_resolve_executable("ffprobe", executable_lookup),
        ffmpeg_args=selected.ffmpeg_args.values,
        session_config_reference=session_config_reference,
        video_sync_interval_ns=file_policies.video_sync_interval_ns,
        fragment_target_ns=file_policies.fragment_target_ns,
        encoder_stall_timeout_ns=file_policies.encoder_stall_timeout_ns,
        frame_log_sync_interval_ns=file_policies.frame_log_sync_interval_ns,
        pending_records_capacity=options.pending_records_capacity,
        diagnostic_tail_max_lines=options.diagnostic_tail_max_lines,
        diagnostic_tail_max_bytes=options.diagnostic_tail_max_bytes,
        recording_queue_frames=queue_frames,
        recording_bit_depth=depth,
    )
    return result


def _selected_camera(
    settings: control.AcquisitionSettings, role: camera.CameraRole
) -> camera.CameraSessionSettings:
    if role == camera.CAMERA_ROLE_BEHAVIORAL:
        return settings.behavioral
    if role == camera.CAMERA_ROLE_TRACKING:
        return settings.tracking
    raise ValueError(f"unsupported acquisition camera role {role}")


def _validate_resolved_device(
    selected: camera.CameraSessionSettings, resolved: camera.CameraResolvedState
) -> None:
    if not selected.HasField("device") or not selected.device.device_id:
        raise ValueError("selected camera has no confirmed device ID")
    if (
        not resolved.HasField("device")
        or not resolved.device.configured_id
        or not resolved.device.physical_id
    ):
        raise ValueError("resolved camera has no physical device identity")
    if selected.device.device_id != resolved.device.configured_id:
        raise ValueError("resolved camera identity differs from confirmed settings")
    if (
        not resolved.HasField("applied")
        or resolved.applied.device_id != selected.device.device_id
    ):
        raise ValueError(
            "resolved applied camera settings differ from confirmed device"
        )
    if not resolved.HasField("layout") or not resolved.layout.pixel_format:
        raise ValueError("resolved camera image format is unavailable")


def _recording_depth(
    selected: camera.CameraSessionSettings, resolved: camera.CameraResolvedState
) -> int:
    if selected.HasField("recording_bit_depth"):
        result = int(selected.recording_bit_depth)
    else:
        result = pylon_pixel_format(resolved.layout.pixel_format).effective_bits
    if result not in (8, 10):
        raise ValueError(
            "recording source depth must resolve to 8 or 10 bits; choose an explicit supported conversion"
        )
    return result


def _queue_capacity(
    settings: control.AcquisitionSettings, nominal_frame_rate_hz: float
) -> int:
    result = int(settings.recording_queue_frames)
    if settings.HasField("recording_startup_allowance_ms"):
        allowance = int(settings.recording_startup_allowance_ms)
        if allowance <= 0:
            raise ValueError("recording startup allowance must be positive")
        result = max(
            result,
            math.ceil(nominal_frame_rate_hz * allowance / 1000.0),
        )
    if result <= 0 or result > (1 << 32) - 1:
        raise ValueError("resolved recording queue capacity exceeds uint32")
    return result


def _camera_policy(
    policies: runtime.AcquisitionFilePolicies, role: camera.CameraRole
) -> runtime.CameraFilePolicy:
    matches = [item for item in policies.cameras if item.camera == role]
    if len(matches) != 1:
        raise ValueError(
            f"recording policy for camera {_role_name(role)} is not unique"
        )
    return matches[0]


def _resolve_executable(name: str, lookup: ExecutableLookup) -> str:
    candidate = lookup(name)
    if not candidate:
        raise ValueError(f"required executable {name!r} was not found on PATH")
    path = Path(candidate).resolve(strict=True)
    if not path.is_absolute() or not path.is_file():
        raise ValueError(f"resolved {name} path is not an existing regular file")
    return str(path)


def _role_name(role: camera.CameraRole) -> str:
    return camera.CameraRole.Name(role).lower().removeprefix("camera_role_")
