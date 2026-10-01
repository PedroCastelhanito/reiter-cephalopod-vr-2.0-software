"""Controller checks for exact E05/A07/V12 output completion evidence.

The owning backend certifies writer accounting and ownership in OutputResult.
These checks interpret that online evidence; they do not inspect file contents or
replace the independent Started, Stopped, health, deadline and cleanup gates.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Set

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2 as pulses
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.identity import require_uuid4
from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus

ProcessKey = tuple[str, str]


def started_satisfied(
    report: pb.StartedReport,
    *,
    target_ns: int,
    ingress_ns: int,
    allowance_ns: int,
    camera_roles: Set[int] = frozenset(),
    external_camera_roles: Set[int] = frozenset(),
    allowed_producers: Set[ProcessKey] = frozenset(),
    visual_stimulus_outputs: Set[str] = frozenset(),
    source_producers: Mapping[str, ProcessKey] | None = None,
) -> bool:
    """Actual first work for the entire expected source set, within original T."""
    if (
        not 0
        < target_ns
        <= report.actual_start_monotonic_ns
        <= ingress_ns
        <= target_ns + allowance_ns
    ):
        return False
    role = report.context.backend.backend_name
    observed: set[int | str] = set()
    for activity in report.first_required_activity:
        if (
            not report.actual_start_monotonic_ns
            <= activity.observed_monotonic_ns
            <= ingress_ns
        ):
            return False
        device = activity.device_evidence
        if role == "acquisition":
            if (
                activity.kind != "camera_callback"
                or not device.HasField("camera")
                or device.camera
                not in {camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING}
                or device.HasField("visual_stimulus_output")
                or device.HasField("tracking_evaluation")
                or (device.producer.role, device.producer.generation)
                not in allowed_producers
            ):
                return False
            key: int | str = device.camera
            source = (
                "behavioral"
                if device.camera == camera.CAMERA_ROLE_BEHAVIORAL
                else "tracking"
            )
            if source_producers is not None and source_producers.get(source) != (
                device.producer.role,
                device.producer.generation,
            ):
                return False
        elif role == "visual_stimulus":
            output = device.visual_stimulus_output
            if (
                activity.kind != "visual_stimulus_presentation_call"
                or device.HasField("camera")
                or device.HasField("tracking_evaluation")
                or device.HasField("producer")
                or not output.output_id
                or output.submission != visual_stimulus.SUBMISSION_OUTCOME_RETURNED
                or not output.HasField("swap_entry_ns")
                or not output.HasField("swap_return_ns")
                or not target_ns
                <= output.swap_entry_ns
                <= output.swap_return_ns
                <= activity.observed_monotonic_ns
            ):
                return False
            key = output.output_id
        elif role == "tracking":
            evaluation = device.tracking_evaluation
            if (
                activity.kind != "tracking_frame_evaluation"
                or device.HasField("camera")
                or device.HasField("visual_stimulus_output")
                or device.HasField("producer")
                or not evaluation.HasField("source_frame_id")
                or evaluation.disposition not in {"baseline_only", "invalid", "valid"}
                or not target_ns
                <= evaluation.source_host_receipt_ns
                <= activity.observed_monotonic_ns
            ):
                return False
            try:
                require_uuid4(evaluation.reset_generation)
            except ValueError:
                return False
            key = "tracking"
        else:
            return False
        if key in observed:
            return False
        observed.add(key)
    expected: Set[int | str]
    if role == "acquisition":
        expected = camera_roles
        if external_camera_roles:
            pulse = report.acquisition_pulse_on
            if (
                pulse.command != pulses.PULSE_BOUNDARY_COMMAND_ON
                or pulse.outcome != pulses.PULSE_COMMAND_OUTCOME_APPLIED
                or not pulse.applied
                or not pulse.HasField("scheduled_boundary_monotonic_ns")
                or pulse.scheduled_boundary_monotonic_ns != target_ns
                or not pulse.HasField("dispatched_monotonic_ns")
                or not pulse.HasField("acknowledged_monotonic_ns")
                or not target_ns
                <= pulse.dispatched_monotonic_ns
                <= pulse.acknowledged_monotonic_ns
                <= ingress_ns
                or not pulse.HasField("behavioral_selected")
                or not pulse.HasField("tracking_selected")
                or pulse.behavioral_selected
                != (camera.CAMERA_ROLE_BEHAVIORAL in external_camera_roles)
                or pulse.tracking_selected
                != (camera.CAMERA_ROLE_TRACKING in external_camera_roles)
            ):
                return False
    elif role == "visual_stimulus":
        expected = visual_stimulus_outputs
    else:
        expected = {"tracking"}
    return bool(expected) and observed == expected


def stopped_satisfied(
    report: pb.StoppedReport,
    *,
    target_ns: int,
    end_ns: int,
    ingress_ns: int,
    allowance_ns: int,
    interruption_issued_ns: int = 0,
    expected_sources: Set[str],
    allowed_producers: Set[ProcessKey],
    external_camera_roles: Set[int] = frozenset(),
    source_producers: Mapping[str, ProcessKey] | None = None,
) -> bool:
    """All actual local admission cutoffs; interruption is not a fabricated cutoff."""
    boundary = interruption_issued_ns or end_ns
    if (
        not 0 < target_ns < end_ns
        or not 0
        < report.actual_stop_monotonic_ns
        <= ingress_ns
        <= boundary + allowance_ns
        or not report.trial_activity_stopped
        or not report.HasField("recording_interval_sealed")
        or not report.recording_interval_sealed
        or not interruption_issued_ns
        and report.actual_stop_monotonic_ns < end_ns
        or report.context.backend.backend_name == "visual_stimulus"
        and (
            not report.HasField("visual_stimulus_idle")
            or not report.visual_stimulus_idle
        )
    ):
        return False
    sources: set[str] = set()
    for evidence in report.producer_ends:
        if (
            evidence.source_id in sources
            or (evidence.producer.role, evidence.producer.generation)
            not in allowed_producers
            or source_producers is not None
            and source_producers.get(evidence.source_id)
            != (evidence.producer.role, evidence.producer.generation)
            or not target_ns
            <= evidence.end_monotonic_ns
            <= min(end_ns, report.actual_stop_monotonic_ns)
            or not interruption_issued_ns
            and evidence.end_monotonic_ns != end_ns
        ):
            return False
        sources.add(evidence.source_id)
    if not expected_sources or sources != expected_sources:
        return False
    if external_camera_roles:
        pulse = report.acquisition_pulse_off
        if (
            report.context.backend.backend_name != "acquisition"
            or pulse.command != pulses.PULSE_BOUNDARY_COMMAND_OFF
            or pulse.outcome != pulses.PULSE_COMMAND_OUTCOME_APPLIED
            or not pulse.applied
            or not pulse.HasField("dispatched_monotonic_ns")
            or not pulse.HasField("acknowledged_monotonic_ns")
            or not 0
            < pulse.dispatched_monotonic_ns
            <= pulse.acknowledged_monotonic_ns
            <= report.actual_stop_monotonic_ns
            or not pulse.HasField("behavioral_selected")
            or not pulse.HasField("tracking_selected")
            or pulse.behavioral_selected
            != (camera.CAMERA_ROLE_BEHAVIORAL in external_camera_roles)
            or pulse.tracking_selected
            != (camera.CAMERA_ROLE_TRACKING in external_camera_roles)
        ):
            return False
        if interruption_issued_ns:
            if pulse.stop_issued_monotonic_ns != interruption_issued_ns:
                return False
        elif pulse.scheduled_boundary_monotonic_ns != end_ns:
            return False
    return True


def outputs_satisfied(
    expected: Iterable[pb.OutputPlan],
    results: Iterable[pb.OutputResult],
    *,
    unavailable: Set[str] = frozenset(),
) -> bool:
    """Require every exact reservation, including explicitly unavailable outputs.

    ``unavailable`` comes only from a confirmed E06 incident scope. Its failed
    outputs stay failed; this predicate never relabels them as successful files.
    An empty-video exception also requires the paired detailed outputs in the
    registered obligation set, with independent successful completion evidence.
    """
    plans = list(expected)
    evidence = list(results)
    by_key = {plan.output_key: plan for plan in plans}
    actual = {result.output_key: result for result in evidence}
    if (
        len(by_key) != len(plans)
        or len(actual) != len(evidence)
        or set(by_key) != set(actual)
        or any(not key for key in by_key)
    ):
        return False
    for key, plan in by_key.items():
        result = actual[key]
        if not plan.HasField("path") or not plan.path or result.path != plan.path:
            return False
        if key in unavailable:
            if result.closure != pb.OUTPUT_CLOSURE_FAILED or not result.failure.code:
                return False
            continue
        if result.failure.ByteSize() or not result.HasField("artifact_present"):
            return False
        camera_video = (
            plan.backend.backend_name == "acquisition"
            and plan.output_tag in {"behavioral_cam", "tracking_cam"}
            and plan.extension == "mp4"
        )
        visual_stimulus_video = (
            plan.backend.backend_name == "visual_stimulus"
            and plan.output_tag == "stimulus"
            and plan.extension == "mp4"
        )
        content: int
        valid_contents: set[int]
        no_frames: int
        if camera_video:
            if (
                result.visual_stimulus_review_video_content
                != pb.VISUAL_STIMULUS_REVIEW_VIDEO_CONTENT_UNSPECIFIED
            ):
                return False
            content = result.camera_video_content
            valid_contents = {
                pb.CAMERA_VIDEO_CONTENT_NO_FRAMES,
                pb.CAMERA_VIDEO_CONTENT_FRAMES_SUBMITTED,
            }
            no_frames = pb.CAMERA_VIDEO_CONTENT_NO_FRAMES
            required_details = {(f"{plan.output_tag}_frames", "jsonl")}
        elif visual_stimulus_video:
            if result.camera_video_content != pb.CAMERA_VIDEO_CONTENT_UNSPECIFIED:
                return False
            content = result.visual_stimulus_review_video_content
            valid_contents = {
                pb.VISUAL_STIMULUS_REVIEW_VIDEO_CONTENT_NO_FRAMES,
                pb.VISUAL_STIMULUS_REVIEW_VIDEO_CONTENT_FRAMES_SUBMITTED,
            }
            no_frames = pb.VISUAL_STIMULUS_REVIEW_VIDEO_CONTENT_NO_FRAMES
            required_details = {("stimulus_LOG", "json"), ("stimulus_frames", "jsonl")}
        else:
            if (
                plan.extension == "mp4"
                or result.camera_video_content != pb.CAMERA_VIDEO_CONTENT_UNSPECIFIED
                or result.visual_stimulus_review_video_content
                != pb.VISUAL_STIMULUS_REVIEW_VIDEO_CONTENT_UNSPECIFIED
                or result.closure != pb.OUTPUT_CLOSURE_CLOSED
                or not result.artifact_present
            ):
                return False
            continue
        if content not in valid_contents:
            return False
        normal = result.artifact_present and result.closure == pb.OUTPUT_CLOSURE_CLOSED
        never_created = (
            content == no_frames
            and not result.artifact_present
            and result.closure == pb.OUTPUT_CLOSURE_NOT_STARTED
        )
        if not (normal or never_created):
            return False
        details = [
            other
            for other in plans
            if other.backend == plan.backend
            and other.trial == plan.trial
            and (other.output_tag, other.extension) in required_details
        ]
        if (
            len(details) != len(required_details)
            or {(other.output_tag, other.extension) for other in details}
            != required_details
        ):
            return False
        if any(
            other.output_key in unavailable
            or actual[other.output_key].closure != pb.OUTPUT_CLOSURE_CLOSED
            or not actual[other.output_key].HasField("artifact_present")
            or not actual[other.output_key].artifact_present
            or actual[other.output_key].failure.ByteSize()
            for other in details
        ):
            return False
    return True
