from __future__ import annotations

import json
import tomllib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cephvr.acquisition.recording.frame_log import FrameLogWriter
from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.recording.paths import RecordingPaths, resolve_recording_paths
from cephvr.acquisition.recording_schema import get_writer_schemas
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


def _identity(role: str = "behavioral") -> RecordingIdentity:
    session_id, trial_id = str(uuid4()), str(uuid4())
    clock = camera.CameraClockDescriptor(
        device_id="device-17",
        timestamp_source="unavailable",
        timestamp_semantics="raw",
        reset_semantics="per-process",
        wrap_semantics="unknown",
        unavailable_reason="SDK unavailable",
        counter_source="unavailable",
        counter_semantics="raw",
        counter_width_bits=0,
        counter_wrap_semantics="unknown",
        counter_unavailable_reason="SDK unavailable",
        conversion_available=False,
    )
    return RecordingIdentity(
        session_id, trial_id, 1, role, "device-17", "config.json", clock
    )


def _reservation(identity: RecordingIdentity) -> RecordingPaths:
    trial = control.TrialContext(
        session=control.SessionContext(session_id=identity.session_id),
        trial_id=identity.trial_id,
        trial_number=identity.trial_number,
    )
    backend = control.BackendContext(
        backend_name="acquisition", backend_generation=str(uuid4())
    )
    return RecordingPaths(
        tuple(
            control.OutputPlan(
                backend=backend,
                output_key=f"{identity.trial_id}:acquisition:{tag}",
                trial=trial,
                output_tag=tag,
                extension=extension,
            )
            for tag, extension in (
                (f"{identity.camera_role}_cam", "mp4"),
                (f"{identity.camera_role}_cam_frames", "jsonl"),
            )
        ),
        backend.backend_generation,
    )


@pytest.mark.parametrize("role", ["behavioral", "tracking", "eye_tracking"])
def test_valid_backend_context_and_exact_scheduled_paths_are_accepted(
    tmp_path: Path,
    role: str,
) -> None:
    identity = _identity(role)
    plans = _reservation(identity)
    plans.validate(role, identity)
    prefix = tmp_path / "trial"
    schedule = acq.WorkerSchedule(
        command=acq.WorkerCommand(
            target=acq.WorkerContext(
                camera=camera.CameraRole.Value(f"CAMERA_ROLE_{role.upper()}"),
                work=control.WorkContext(
                    trial=control.TrialContext(
                        session=control.SessionContext(session_id=identity.session_id),
                        trial_id=identity.trial_id,
                        trial_number=identity.trial_number,
                    )
                ),
            )
        ),
        start_monotonic_ns=100,
        end_monotonic_ns=200,
        trial_file_prefix=str(prefix),
        outputs=plans.outputs,
    )
    for item in schedule.outputs:
        item.path = f"{prefix}_{item.output_tag}.{item.extension}"

    assert resolve_recording_paths(plans, role, identity, schedule) == (
        Path(f"{prefix}_{role}_cam.mp4"),
        Path(f"{prefix}_{role}_cam_frames.jsonl"),
    )


def test_non_acquisition_backend_context_is_rejected() -> None:
    identity = _identity()
    plans = _reservation(identity)
    plans.outputs[0].backend.backend_name = "tracking"
    with pytest.raises(ValueError, match="exact acquisition work identity"):
        plans.validate("behavioral", identity)


def test_stale_backend_generation_is_rejected() -> None:
    identity = _identity()
    plans = _reservation(identity)
    stale = RecordingPaths(plans.outputs, str(uuid4()))
    with pytest.raises(ValueError, match="exact acquisition work identity"):
        stale.validate("behavioral", identity)


@pytest.mark.parametrize("available", [False, True])
def test_recording_clock_accepts_schema_text_and_checks_explicit_conversion(
    available: bool,
) -> None:
    identity = _identity()
    if available:
        identity.camera_clock.conversion_available = True
        identity.camera_clock.tick_period_ns_numerator = 1
        identity.camera_clock.tick_period_ns_denominator = 1
        identity.camera_clock.unavailable_reason = ""
        identity.camera_clock.counter_unavailable_reason = ""
    identity.validate()
    identity.camera_clock.timestamp_source = ""
    with pytest.raises(ValueError, match="timestamp_source is invalid"):
        identity.validate()
    identity.camera_clock.timestamp_source = "SDK"
    identity.camera_clock.ClearField("conversion_available")
    with pytest.raises(ValueError, match="conversion availability is unspecified"):
        identity.validate()


def test_frame_log_header_matches_declared_and_planned_cadence_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "camera_frames.jsonl"
    writer = FrameLogWriter(
        path,
        _identity(),
        start_ns=1_000_000_000,
        nominal_frame_rate_hz=30,
        nominal_rate_source="applied_mcu_rate",
        sync_interval_ns=1_000_000_000,
        syncer=SimpleNamespace(sync=lambda _: None),
    )
    writer.create()
    writer.close_failed()  # A header alone is deliberately not completed recording.
    header = json.loads(path.read_text().splitlines()[0])
    declaration = tomllib.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts/acquisition/frame_log_schema.toml"
        ).read_text()
    )
    planned = get_writer_schemas()["acquisition", "behavioral_cam_frames", "jsonl"]
    assert (
        header["schema_version"]
        == declaration["schema_version"]
        == planned.schema_version
        == 3
    )
    assert "video_frame" in declaration["format"]["line_types"]
    assert "source_host_receipt_ns" in planned.fields["video_frame"]
