"""Schedule-bound final output path resolution (A07/E11)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.recording.session_contracts import RecordingFailure
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


@dataclass(frozen=True)
class RecordingPaths:
    """Reserved protocol-data namespace and symbolic plans; no trial filename."""

    outputs: tuple[control.OutputPlan, ...]
    backend_generation: str

    def validate(self, role: str, identity: RecordingIdentity) -> None:
        if role not in {"behavioral", "tracking", "eye_tracking"}:
            raise ValueError("invalid recording role")
        if not self.backend_generation:
            raise ValueError("recording reservation lacks its acquisition generation")
        expected = {f"{role}_cam": "mp4", f"{role}_cam_frames": "jsonl"}
        keys = [item.output_key for item in self.outputs]
        tags = [item.output_tag for item in self.outputs]
        if len(set(keys)) != len(keys) or len(set(tags)) != len(tags):
            raise ValueError("recording reservation contains duplicate outputs")
        matches = {item.output_tag: item.extension for item in self.outputs}
        if matches != expected:
            raise ValueError(
                "recording reservation must contain exact MP4/frame-log pair"
            )
        for item in self.outputs:
            if (
                not item.HasField("backend")
                or item.backend.backend_name != "acquisition"
                or item.backend.backend_generation != self.backend_generation
                or item.trial.trial_id != identity.trial_id
                or item.trial.trial_number != identity.trial_number
                or item.trial.session.session_id != identity.session_id
            ):
                raise ValueError(
                    "recording reservation lacks exact acquisition work identity"
                )
            if (
                item.output_key
                != f"{item.trial.trial_id}:acquisition:{item.output_tag}"
            ):
                raise ValueError(
                    "recording reservation output key differs from its work identity"
                )
            if item.HasField("path"):
                raise ValueError(
                    "recording preparation cannot retain final trial paths"
                )


def resolve_recording_paths(
    paths: RecordingPaths,
    role: str,
    identity: RecordingIdentity,
    schedule: acq.WorkerSchedule,
) -> tuple[Path, Path]:
    if not schedule.HasField("command") or not schedule.command.HasField("target"):
        raise RecordingFailure("ScheduleTrial lacks exact worker target context")
    target = schedule.command.target
    role_name = (
        camera.CameraRole.Name(target.camera).lower().removeprefix("camera_role_")
    )
    if role_name != role:
        raise RecordingFailure(
            "scheduled camera role differs from prepared recording owner"
        )
    if target.work.WhichOneof("work") != "trial":
        raise RecordingFailure("ScheduleTrial lacks exact trial work context")
    work_trial = target.work.trial
    if (
        work_trial.trial_id != identity.trial_id
        or work_trial.trial_number != identity.trial_number
        or work_trial.session.session_id != identity.session_id
    ):
        raise RecordingFailure(
            "ScheduleTrial work differs from prepared recording identity"
        )
    if not schedule.trial_file_prefix:
        raise RecordingFailure("scheduled trial prefix is missing")
    prefix = Path(schedule.trial_file_prefix)
    if not prefix.is_absolute():
        raise RecordingFailure("trial prefix must be an authoritative absolute path")
    protocol_directory = prefix.parent.resolve()
    if len({item.output_key for item in paths.outputs}) != len(paths.outputs):
        raise RecordingFailure("recording reservation contains duplicate keys")
    if len({item.output_tag for item in paths.outputs}) != len(paths.outputs):
        raise RecordingFailure("recording reservation contains duplicate tags")
    if len({item.output_key for item in schedule.outputs}) != len(schedule.outputs):
        raise RecordingFailure("schedule contains duplicate output keys")
    if len({item.output_tag for item in schedule.outputs}) != len(schedule.outputs):
        raise RecordingFailure("schedule contains duplicate output tags")
    planned = {item.output_key: item for item in paths.outputs}
    scheduled = {item.output_key: item for item in schedule.outputs}
    if set(planned) != set(scheduled):
        raise RecordingFailure(
            "scheduled camera output set differs from reserved plans"
        )
    resolved: dict[str, Path] = {}
    for key, reserved in planned.items():
        item = scheduled[key]
        if (
            item.output_tag != reserved.output_tag
            or item.extension != reserved.extension
            or item.backend != reserved.backend
            or item.trial.SerializeToString(deterministic=True)
            != reserved.trial.SerializeToString(deterministic=True)
        ):
            raise RecordingFailure("scheduled output identity differs from reservation")
        if not item.HasField("path"):
            raise RecordingFailure("scheduled output path is missing")
        path = Path(item.path)
        if not path.is_absolute() or path.parent.resolve() != protocol_directory:
            raise RecordingFailure("scheduled output escaped scheduled protocol-data")
        resolved[item.output_tag] = path
    for tag, path in resolved.items():
        extension = next(
            item.extension for item in planned.values() if item.output_tag == tag
        )
        expected = Path(f"{prefix}_{tag}.{extension}")
        if path != expected:
            raise RecordingFailure(
                "scheduled output path does not match the shared trial prefix"
            )
    for item in schedule.outputs:
        if (
            item.trial.trial_id != identity.trial_id
            or item.trial.trial_number != identity.trial_number
            or item.trial.session.session_id != identity.session_id
        ):
            raise RecordingFailure("scheduled output belongs to another trial")
        if (
            not item.HasField("backend")
            or item.backend.backend_name != "acquisition"
            or not item.backend.backend_generation
        ):
            raise RecordingFailure("scheduled output is not owned by acquisition")
        expected_key = f"{identity.trial_id}:acquisition:{item.output_tag}"
        if item.output_key != expected_key:
            raise RecordingFailure(
                "scheduled output key differs from exact acquisition work"
            )
    return resolved[f"{role}_cam"], resolved[f"{role}_cam_frames"]
