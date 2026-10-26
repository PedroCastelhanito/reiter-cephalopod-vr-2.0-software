"""Shared recording fixtures used by path and payload tests."""

from uuid import uuid4

from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.recording.paths import RecordingPaths
from cephvr.acquisition.v1 import camera_pb2 as camera
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
