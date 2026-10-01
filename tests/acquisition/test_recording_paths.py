from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.recording.paths import RecordingPaths, resolve_recording_paths
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


def _identity() -> RecordingIdentity:
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
        session_id, trial_id, 1, "behavioral", "device-17", "config.json", clock
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
                ("behavioral_cam", "mp4"),
                ("behavioral_cam_frames", "jsonl"),
            )
        ),
        backend.backend_generation,
    )


def test_valid_backend_context_and_exact_scheduled_paths_are_accepted(
    tmp_path: Path,
) -> None:
    identity = _identity()
    plans = _reservation(identity)
    plans.validate("behavioral", identity)
    prefix = tmp_path / "trial"
    schedule = acq.WorkerSchedule(
        command=acq.WorkerCommand(
            target=acq.WorkerContext(
                camera=camera.CAMERA_ROLE_BEHAVIORAL,
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

    assert resolve_recording_paths(plans, "behavioral", identity, schedule) == (
        Path(f"{prefix}_behavioral_cam.mp4"),
        Path(f"{prefix}_behavioral_cam_frames.jsonl"),
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
