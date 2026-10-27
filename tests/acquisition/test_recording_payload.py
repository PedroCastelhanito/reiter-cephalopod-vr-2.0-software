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
from tests.acquisition.support import _identity, _reservation


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
    resolved.layout.pixel_format = "Mono12"  # No video conversion required.
    result = build_recording_settings(
        settings,
        resolved,
        policies,
        camera.CAMERA_ROLE_BEHAVIORAL,
        session_config_reference="config",
        nominal_frame_rate_hz=30.0,
        executable_lookup=lambda _: pytest.fail("encoder discovery with video off"),
    )
    assert result is not None and result.metadata_only
    assert result.pending_records_capacity == 10000
    assert not result.ffmpeg_executable and not result.ffmpeg_args
    settings.behavioral.enabled = False
    assert (
        build_recording_settings(
            settings,
            resolved,
            policies,
            camera.CAMERA_ROLE_BEHAVIORAL,
            session_config_reference="config",
            nominal_frame_rate_hz=30.0,
        )
        is None
    )


@pytest.mark.parametrize("source_bits", [8, 10, 12, 16])
@pytest.mark.parametrize("target_bits", [8, 10])
def test_recording_pixel_preparation_matches_uint64_sdk_reference(
    source_bits: int, target_bits: int
) -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("pypylon")

    from cephvr.acquisition.camera.native_formats import pylon_pixel_format
    from cephvr.shared.pixels.preparer import PixelPreparer
    from cephvr.shared.pixels.scaling import scale_full_range_into
    from cephvr.shared.pixels.types import PixelLayout

    maximum = (1 << source_bits) - 1
    samples = np.array(
        [0, 1, maximum // 4, maximum // 3, maximum // 2, maximum - 1, maximum, 0],
        dtype=np.uint8 if source_bits == 8 else "<u2",
    )
    source = bytearray(samples.tobytes())
    container_bits = 8 if source_bits == 8 else 16
    layout = PixelLayout(
        width=samples.size,
        height=1,
        pixel_format=pylon_pixel_format(f"Mono{source_bits}"),
        row_stride_bytes=samples.size * (container_bits // 8),
        image_payload_bytes=len(source),
    )
    preparer = PixelPreparer(layout)
    image = preparer._convert(source)
    target_container_bits = 8 if target_bits == 8 else 16
    expected = bytearray(samples.size * (target_container_bits // 8))
    try:
        sdk_pixels = np.frombuffer(
            image.GetBuffer(), dtype=np.uint8 if source_bits == 8 else "<u2"
        )
        assert sdk_pixels[-2] == (255 if source_bits == 8 else 65535)
        if source_bits == target_bits:
            expected[:] = memoryview(image.GetBuffer()).cast("B")
        else:
            scale_full_range_into(
                np,
                image,
                memoryview(expected),
                source_bits,
                preparer._container_bits,
                target_bits,
                target_container_bits,
                np.empty(samples.size, dtype=np.uint64),
            )
    finally:
        image.Release()

    assert preparer._scale_scratch.dtype == np.dtype(np.uint32)
    assert preparer._scale_scratch.size == samples.size
    output = bytearray(len(expected))
    try:
        prepared = preparer.prepare_recording_into(
            source, output, target_bits=target_bits
        )
    finally:
        preparer.close()
    assert output == expected
    assert prepared.effective_bits == target_bits
    assert prepared.container_bits == target_container_bits
    assert prepared.alignment == ("full" if target_bits == 8 else "msb")
    if target_bits == 10 and source_bits != target_bits:
        output_samples = np.frombuffer(output, dtype="<u2")
        assert np.all(output_samples <= 1023 << 6)
        assert np.all(output_samples & 0x3F == 0)


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
