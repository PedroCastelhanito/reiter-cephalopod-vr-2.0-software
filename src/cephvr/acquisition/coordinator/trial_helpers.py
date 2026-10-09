"""Pure identity, output-plan, and terminal-closure predicates for trials."""

from __future__ import annotations

from collections.abc import Iterable

from cephvr.acquisition.coordinator.session_payloads import role_name
from cephvr.acquisition.state import SessionRecord, TrialRecord
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.control.v1 import types_pb2 as control


def _camera_output_keys(trial: TrialRecord, role: int) -> set[str]:
    prefix = role_name(role) + "_cam"
    return {
        item.output_key
        for item in trial.outputs
        if item.backend.backend_name == "acquisition"
        and item.output_tag.startswith(prefix)
    }


def _outputs_match(
    prepared: list[control.OutputPlan],
    scheduled: Iterable[control.OutputPlan],
    backend: control.BackendContext,
) -> bool:
    requested = [item for item in scheduled if item.backend == backend]
    if len(requested) != len([item for item in prepared if item.backend == backend]):
        return False
    expected = {item.output_key: item for item in prepared if item.backend == backend}
    for item in requested:
        saved = expected.get(item.output_key)
        if (
            saved is None
            or item.output_tag != saved.output_tag
            or item.extension != saved.extension
            or item.trial != saved.trial
            or not item.HasField("path")
        ):
            return False
    return len(requested) == len(expected)


def _external_roles(session: SessionRecord) -> tuple[int, ...]:
    """Select required cameras whose confirmed timing needs MCU pulse evidence."""
    settings = session.confirmed_settings
    roles = []
    for role, name in (
        (camera.CAMERA_ROLE_BEHAVIORAL, "behavioral"),
        (camera.CAMERA_ROLE_TRACKING, "tracking"),
        (camera.CAMERA_ROLE_EYE_TRACKING, "eye_tracking"),
    ):
        if role not in session.required_cameras:
            continue
        device = getattr(settings, name).device
        if (
            device.HasField("frame_timing")
            and device.frame_timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
        ):
            roles.append(role)
    return tuple(roles)


def _trial_finished(trial: TrialRecord) -> bool:
    report = trial.finished_report
    if report is None or not report.trial_activity_stopped:
        return False
    expected = {
        item.output_key: item
        for item in trial.outputs
        if item.backend.backend_name == "acquisition"
    }
    observed = {item.output_key: item for item in report.outputs}
    if len(observed) != len(report.outputs) or set(observed) != set(expected):
        return False
    for key, plan in expected.items():
        result = observed[key]
        if not plan.HasField("path") or not plan.path or result.path != plan.path:
            return False
        if result.failure.ByteSize() or not result.HasField("artifact_present"):
            return False
        if (
            plan.output_tag in {"behavioral_cam", "tracking_cam", "eye_tracking_cam"}
            and plan.extension == "mp4"
        ):
            if (
                result.visual_stimulus_review_video_content
                != control.VISUAL_STIMULUS_REVIEW_VIDEO_CONTENT_UNSPECIFIED
                or result.camera_video_content
                not in {
                    control.CAMERA_VIDEO_CONTENT_NO_FRAMES,
                    control.CAMERA_VIDEO_CONTENT_FRAMES_SUBMITTED,
                }
            ):
                return False
            never_created = (
                result.camera_video_content == control.CAMERA_VIDEO_CONTENT_NO_FRAMES
                and not result.artifact_present
                and result.closure == control.OUTPUT_CLOSURE_NOT_STARTED
            )
            if not (
                result.closure == control.OUTPUT_CLOSURE_CLOSED
                and result.artifact_present
                or never_created
                and _frame_log_closed(expected, observed, plan)
            ):
                return False
        elif (
            result.closure != control.OUTPUT_CLOSURE_CLOSED
            or not result.artifact_present
            or result.camera_video_content != control.CAMERA_VIDEO_CONTENT_UNSPECIFIED
            or result.visual_stimulus_review_video_content
            != control.VISUAL_STIMULUS_REVIEW_VIDEO_CONTENT_UNSPECIFIED
        ):
            return False
    return True


def _frame_log_closed(
    expected: dict[str, control.OutputPlan],
    observed: dict[str, control.OutputResult],
    video_plan: control.OutputPlan,
) -> bool:
    tag = video_plan.output_tag + "_frames"
    details = [
        plan
        for plan in expected.values()
        if plan.backend == video_plan.backend
        and plan.trial == video_plan.trial
        and plan.output_tag == tag
        and plan.extension == "jsonl"
    ]
    if len(details) != 1:
        return False
    result = observed[details[0].output_key]
    return bool(
        result.closure == control.OUTPUT_CLOSURE_CLOSED
        and result.HasField("artifact_present")
        and result.artifact_present
        and not result.failure.ByteSize()
    )


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )


def _continuation_incidents_match(
    confirmed: dict[str, control.RuntimeIncident],
    supplied: Iterable[control.RuntimeIncident],
) -> bool:
    """Require each trial plan to carry the exact controller-confirmed scopes."""
    items = tuple(supplied)
    if len(items) != len({item.incident_id for item in items}):
        return False
    observed = {item.incident_id: item for item in items}
    if set(observed) != set(confirmed):
        return False
    return all(
        observed[key].SerializeToString(deterministic=True)
        == incident.SerializeToString(deterministic=True)
        for key, incident in confirmed.items()
    )
