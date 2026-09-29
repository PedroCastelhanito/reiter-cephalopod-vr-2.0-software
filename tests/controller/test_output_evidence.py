"""The accepted empty-video cases cannot discharge unknown or failed writers."""

from __future__ import annotations

import pytest

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.evidence import outputs_satisfied


def _outputs(owner: str) -> tuple[list[pb.OutputPlan], list[pb.OutputResult]]:
    tags = (
        [("behavioral_cam", "mp4"), ("behavioral_cam_frames", "jsonl")]
        if owner == "acquisition"
        else [
            ("stimulus", "mp4"),
            ("stimulus_frames", "jsonl"),
            ("stimulus_LOG", "json"),
        ]
    )
    plans = [
        pb.OutputPlan(
            backend=pb.BackendContext(backend_name=owner, backend_generation="exact"),
            output_key=tag,
            output_tag=tag,
            extension=extension,
            path=f"/reserved/{tag}.{extension}",
        )
        for tag, extension in tags
    ]
    results = [
        pb.OutputResult(
            output_key=plan.output_key,
            path=plan.path,
            closure=pb.OUTPUT_CLOSURE_CLOSED,
            artifact_present=True,
        )
        for plan in plans
    ]
    return plans, results


@pytest.mark.parametrize("owner", ["acquisition", "vr"])
@pytest.mark.parametrize("never_created", [False, True])
def test_exact_empty_video_with_closed_detailed_records_is_satisfied(
    owner: str, never_created: bool
) -> None:
    plans, results = _outputs(owner)
    video = results[0]
    field = (
        "camera_video_content" if owner == "acquisition" else "vr_review_video_content"
    )
    setattr(video, field, 2)  # The separately typed NO_FRAMES values.
    if never_created:
        video.artifact_present = False
        video.closure = pb.OUTPUT_CLOSURE_NOT_STARTED
    assert outputs_satisfied(plans, results)
    results[1].closure = pb.OUTPUT_CLOSURE_UNCONFIRMED
    assert not outputs_satisfied(plans, results)


@pytest.mark.parametrize("owner", ["acquisition", "vr"])
def test_video_evidence_rejects_unknown_presence_failure_conflicts_and_missing_pairs(
    owner: str,
) -> None:
    plans, results = _outputs(owner)
    video = results[0]
    field = (
        "camera_video_content" if owner == "acquisition" else "vr_review_video_content"
    )
    for invalid in (0, 1, 123):
        setattr(video, field, invalid)
        assert not outputs_satisfied(plans, results)
    setattr(video, field, 3)  # FRAMES_SUBMITTED.
    assert outputs_satisfied(plans, results)
    video.ClearField("artifact_present")
    assert not outputs_satisfied(plans, results)
    video.artifact_present = False
    video.closure = pb.OUTPUT_CLOSURE_NOT_STARTED
    assert not outputs_satisfied(plans, results)
    setattr(video, field, 2)
    assert outputs_satisfied(plans, results)
    video.failure.message = "known encoder error without a machine code"
    assert not outputs_satisfied(plans, results)
    video.ClearField("failure")
    other = (
        "vr_review_video_content" if owner == "acquisition" else "camera_video_content"
    )
    setattr(video, other, 2)
    assert not outputs_satisfied(plans, results)
    video.ClearField(other)
    assert not outputs_satisfied(plans[:1], results[:1])


def test_exact_identity_and_unavailable_obligations_are_not_silent_omissions() -> None:
    plans, results = _outputs("vr")
    results[0].vr_review_video_content = pb.VR_REVIEW_VIDEO_CONTENT_FRAMES_SUBMITTED
    assert outputs_satisfied(plans, results)
    assert not outputs_satisfied(plans, results + [results[0]])
    results[1].path = "/other/file"
    assert not outputs_satisfied(plans, results)
    results[1].path = plans[1].path
    results[0].closure = pb.OUTPUT_CLOSURE_FAILED
    results[0].failure.code = "ISOLATED_WRITER_FAILURE"
    assert not outputs_satisfied(plans, results)
    assert outputs_satisfied(plans, results, unavailable={plans[0].output_key})
    assert not outputs_satisfied(plans, results[1:], unavailable={plans[0].output_key})


def test_video_fields_and_never_created_exception_cannot_leak_to_tracking() -> None:
    plan = pb.OutputPlan(
        backend=pb.BackendContext(backend_name="tracking"),
        output_key="tracking",
        output_tag="tracking",
        extension="jsonl",
        path="/tracking",
    )
    result = pb.OutputResult(
        output_key="tracking",
        path="/tracking",
        closure=pb.OUTPUT_CLOSURE_CLOSED,
        artifact_present=True,
    )
    assert outputs_satisfied([plan], [result])
    result.camera_video_content = pb.CAMERA_VIDEO_CONTENT_NO_FRAMES
    assert not outputs_satisfied([plan], [result])
    result.ClearField("camera_video_content")
    result.artifact_present = False
    result.closure = pb.OUTPUT_CLOSURE_NOT_STARTED
    assert not outputs_satisfied([plan], [result])
