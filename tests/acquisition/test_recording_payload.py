from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from cephvr.acquisition.coordinator.recording_payload import build_recording_settings
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.acquisition.worker.recording_preparation import TrialRecordingPreparation
from cephvr.control.v1 import types_pb2 as control


@pytest.mark.parametrize("running", [False, True])
def test_recording_setup_uses_configured_rate_before_pulses_start(
    running: bool,
) -> None:
    observation = mcu.MicrocontrollerObservation(
        connection_id="connection", request_id="configure", observed_monotonic_ns=1
    )
    observation.state.configuration_valid = True
    observation.state.behavioral.enabled = True
    observation.state.behavioral.running = running
    observation.state.behavioral.applied_frequency_hz = 30
    assert TrialRecordingPreparation._applied_pulse_rate(
        observation, camera.CAMERA_ROLE_BEHAVIORAL
    ) == (30, "applied_mcu_rate")
    observation.state.behavioral.ClearField("applied_frequency_hz")
    with pytest.raises(ValueError, match="rate is not applied"):
        TrialRecordingPreparation._applied_pulse_rate(
            observation, camera.CAMERA_ROLE_BEHAVIORAL
        )


def _inputs() -> tuple[
    control.AcquisitionSettings,
    camera.CameraResolvedState,
    runtime.AcquisitionFilePolicies,
]:
    settings = control.AcquisitionSettings(
        recording_queue_frames=10,
        recording_startup_allowance_ms=150,
        recording_options=runtime.AcquisitionRecordingOptions(
            pending_records_capacity=10000,
            diagnostic_tail_max_lines=100,
            diagnostic_tail_max_bytes=65536,
        ),
    )
    settings.behavioral.enabled = True
    settings.behavioral.save_video = True
    settings.behavioral.device.device_id = "camera-1"
    settings.behavioral.ffmpeg_args.values.extend(("-c:v", "h264_nvenc"))
    resolved = camera.CameraResolvedState(
        device=camera.CameraDeviceIdentity(
            configured_id="camera-1", physical_id="physical-camera-1"
        ),
        applied=camera.CameraDeviceConfiguration(device_id="camera-1"),
        layout=camera.CameraImageLayout(width=640, height=480, pixel_format="Mono8"),
    )
    policies = runtime.AcquisitionFilePolicies(
        frame_log_sync_interval_ns=1_000_000_000,
        video_sync_interval_ns=1_000_000_000,
        fragment_target_ns=1_000_000_000,
        encoder_stall_timeout_ns=10_000_000_000,
    )
    policies.cameras.add(camera=camera.CAMERA_ROLE_BEHAVIORAL)
    return settings, resolved, policies


def test_recording_payload_resolves_tools_depth_and_queue(tmp_path: Path) -> None:
    ffmpeg, ffprobe = tmp_path / "ffmpeg.exe", tmp_path / "ffprobe.exe"
    ffmpeg.touch()
    ffprobe.touch()
    settings, resolved, policies = _inputs()
    tools = {"ffmpeg": str(ffmpeg), "ffprobe": str(ffprobe)}

    result = build_recording_settings(
        settings,
        resolved,
        policies,
        camera.CAMERA_ROLE_BEHAVIORAL,
        session_config_reference="config-revision-7",
        nominal_frame_rate_hz=30.0,
        executable_lookup=tools.get,
    )

    assert result is not None
    assert result.ffmpeg_executable == str(ffmpeg.resolve())
    assert result.ffprobe_executable == str(ffprobe.resolve())
    assert result.recording_bit_depth == 8
    assert result.recording_queue_frames == 10
    assert tuple(result.ffmpeg_args) == ("-c:v", "h264_nvenc")


def test_recording_payload_rejects_depth_identity_and_policy_ambiguity(
    tmp_path: Path,
) -> None:
    ffmpeg, ffprobe = tmp_path / "ffmpeg.exe", tmp_path / "ffprobe.exe"
    ffmpeg.touch()
    ffprobe.touch()
    tools = {"ffmpeg": str(ffmpeg), "ffprobe": str(ffprobe)}
    settings, resolved, policies = _inputs()
    resolved.layout.pixel_format = "Mono12"
    with pytest.raises(ValueError, match="source depth"):
        build_recording_settings(
            settings,
            resolved,
            policies,
            camera.CAMERA_ROLE_BEHAVIORAL,
            session_config_reference="config",
            nominal_frame_rate_hz=30.0,
            executable_lookup=tools.get,
        )

    settings.behavioral.recording_bit_depth = 10
    resolved.device.configured_id = "other-camera"
    with pytest.raises(ValueError, match="identity"):
        build_recording_settings(
            settings,
            resolved,
            policies,
            camera.CAMERA_ROLE_BEHAVIORAL,
            session_config_reference="config",
            nominal_frame_rate_hz=30.0,
            executable_lookup=tools.get,
        )

    resolved.device.configured_id = "camera-1"
    policies.cameras.add(camera=camera.CAMERA_ROLE_BEHAVIORAL)
    with pytest.raises(ValueError, match="not unique"):
        build_recording_settings(
            settings,
            resolved,
            policies,
            camera.CAMERA_ROLE_BEHAVIORAL,
            session_config_reference="config",
            nominal_frame_rate_hz=30.0,
            executable_lookup=tools.get,
        )


def test_disabled_or_save_off_camera_needs_no_encoder_discovery() -> None:
    settings, resolved, policies = _inputs()
    settings.behavioral.save_video = False
    assert (
        build_recording_settings(
            settings,
            resolved,
            policies,
            camera.CAMERA_ROLE_BEHAVIORAL,
            session_config_reference="unused",
            nominal_frame_rate_hz=30.0,
            executable_lookup=lambda _name: None,
        )
        is None
    )


@pytest.mark.parametrize(
    "mono,depth,expected",
    [
        (True, 8, "gray"),
        (False, 8, "rgb24"),
        (True, 10, "gray16le"),
        (False, 10, "rgb48le"),
    ],
)
def test_locked_recording_selects_canonical_ffmpeg_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mono: bool,
    depth: int,
    expected: str,
) -> None:
    from cephvr.acquisition.recording import session_prepare
    from cephvr.acquisition.v1 import messages_pb2 as acq
    from tests.acquisition.test_recording_paths import _identity, _reservation

    identity = _identity()
    recorded = []

    def validate(args, **kwargs):
        recorded.append(kwargs["input_pixel_format"])
        return SimpleNamespace()

    monkeypatch.setattr(session_prepare, "validate_arguments", validate)
    settings = acq.RecordingSettings(
        video_sync_interval_ns=1,
        fragment_target_ns=1,
        encoder_stall_timeout_ns=1,
        frame_log_sync_interval_ns=1,
        pending_records_capacity=1,
        recording_queue_frames=1,
        recording_bit_depth=depth,
        ffmpeg_executable=str(tmp_path / "ffmpeg.exe"),
    )
    _, pixels, actual = session_prepare.prepare_recording(
        settings,
        camera.CameraImageLayout(width=2, height=2),
        identity,
        _reservation(identity),
        SimpleNamespace(pending_records_capacity=1, capacity_frames=1),
        SimpleNamespace(
            layout=SimpleNamespace(
                width=2,
                height=2,
                pixel_format=SimpleNamespace(
                    channel_layout="mono8" if mono else "rgb8"
                ),
            )
        ),
        SimpleNamespace(),
        role="behavioral",
    )
    assert actual == expected and recorded == [expected]
    assert len(pixels) == 4 * (1 if mono else 3) * (1 if depth == 8 else 2)
