"""Cleanup closure permits exact never-started output plans only."""

from __future__ import annotations

from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.cleanup_outputs import cleanup_output_discharged


def test_cleanup_never_started_requires_explicit_absence_and_no_failure() -> None:
    result = control.OutputResult(
        output_key="trial:acquisition:behavioral_cam",
        closure=control.OUTPUT_CLOSURE_NOT_STARTED,
        artifact_present=False,
    )

    assert cleanup_output_discharged(result)


def test_cleanup_never_started_rejects_unknown_or_present_artifact() -> None:
    omitted = control.OutputResult(
        output_key="trial:acquisition:behavioral_cam",
        closure=control.OUTPUT_CLOSURE_NOT_STARTED,
    )
    present = control.OutputResult(
        output_key="trial:acquisition:behavioral_cam",
        closure=control.OUTPUT_CLOSURE_NOT_STARTED,
        artifact_present=True,
    )

    assert not cleanup_output_discharged(omitted)
    assert not cleanup_output_discharged(present)


def test_cleanup_failed_output_is_retained_as_failure() -> None:
    result = control.OutputResult(
        output_key="trial:acquisition:behavioral_cam",
        closure=control.OUTPUT_CLOSURE_FAILED,
        artifact_present=False,
        failure=control.Failure(code="ENCODER_FAILED", message="close failed"),
    )

    assert cleanup_output_discharged(result)
