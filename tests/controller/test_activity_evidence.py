"""E05/E11 first activity and producer cutoff evidence stays source-specific."""

from __future__ import annotations

import uuid

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.evidence import started_satisfied, stopped_satisfied
from cephvr.tracking.v1 import methods_pb2 as tracking
from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus


def test_visual_stimulus_started_requires_returned_activity_for_every_prepared_output() -> (
    None
):
    report = pb.StartedReport(actual_start_monotonic_ns=1_000)
    report.context.backend.backend_name = "visual_stimulus"
    for output_id in ("left", "right"):
        report.first_required_activity.add(
            kind="visual_stimulus_presentation_call",
            observed_monotonic_ns=1_030,
            device_evidence=pb.DeviceProgressEvidence(
                visual_stimulus_output=visual_stimulus.OutputActivity(
                    output_id=output_id,
                    swap_entry_ns=1_010,
                    swap_return_ns=1_025,
                    submission=visual_stimulus.SUBMISSION_OUTCOME_RETURNED,
                )
            ),
        )
    kwargs = dict(
        target_ns=1_000,
        ingress_ns=1_040,
        allowance_ns=250,
        visual_stimulus_outputs={"left", "right"},
    )
    assert started_satisfied(report, **kwargs)
    report.first_required_activity[
        1
    ].device_evidence.visual_stimulus_output.submission = (
        visual_stimulus.SUBMISSION_OUTCOME_UNKNOWN
    )
    assert not started_satisfied(report, **kwargs)
    del report.first_required_activity[1:]
    assert not started_satisfied(report, **kwargs)


def test_camera_started_cannot_use_one_worker_twice_or_an_unregistered_generation() -> (
    None
):
    producer = pb.ProcessIdentity(role="camera-worker", generation=str(uuid.uuid4()))
    report = pb.StartedReport(actual_start_monotonic_ns=1_000)
    report.context.backend.backend_name = "acquisition"
    activity = report.first_required_activity.add(
        kind="camera_callback",
        observed_monotonic_ns=1_001,
        device_evidence=pb.DeviceProgressEvidence(
            camera=camera.CAMERA_ROLE_BEHAVIORAL, producer=producer
        ),
    )
    kwargs = dict(
        target_ns=1_000,
        ingress_ns=1_010,
        allowance_ns=250,
        camera_roles={camera.CAMERA_ROLE_BEHAVIORAL},
        allowed_producers={(producer.role, producer.generation)},
    )
    assert started_satisfied(report, **kwargs)
    report.first_required_activity.add().CopyFrom(activity)
    assert not started_satisfied(report, **kwargs)
    del report.first_required_activity[1:]
    activity.device_evidence.producer.generation = str(uuid.uuid4())
    assert not started_satisfied(report, **kwargs)


def test_tracking_baseline_only_evaluation_with_frame_zero_is_real_activity() -> None:
    report = pb.StartedReport(actual_start_monotonic_ns=1_000)
    report.context.backend.backend_name = "tracking"
    activity = report.first_required_activity.add(
        kind="tracking_frame_evaluation",
        observed_monotonic_ns=1_010,
        device_evidence=pb.DeviceProgressEvidence(
            tracking_evaluation=tracking.TrackingFirstEvaluation(
                source_frame_id=0,
                source_host_receipt_ns=1_005,
                reset_generation=str(uuid.uuid4()),
                disposition="baseline_only",
            )
        ),
    )
    assert started_satisfied(
        report, target_ns=1_000, ingress_ns=1_020, allowance_ns=250
    )
    activity.device_evidence.tracking_evaluation.ClearField("source_frame_id")
    assert not started_satisfied(
        report, target_ns=1_000, ingress_ns=1_020, allowance_ns=250
    )
    activity.device_evidence.tracking_evaluation.source_frame_id = 0
    assert not started_satisfied(
        report, target_ns=1_000, ingress_ns=1_251, allowance_ns=250
    )


def test_interruption_retains_actual_local_cutoff_before_global_issuance() -> None:
    producer = pb.ProcessIdentity(role="tracking", generation=str(uuid.uuid4()))
    report = pb.StoppedReport(
        actual_stop_monotonic_ns=1_450,
        trial_activity_stopped=True,
        recording_interval_sealed=True,
        producer_ends=[
            pb.ProducerRecordingEnd(
                producer=producer, source_id="tracking", end_monotonic_ns=1_430
            )
        ],
    )
    report.context.backend.backend_name = "tracking"
    kwargs = dict(
        target_ns=1_000,
        end_ns=2_000,
        ingress_ns=1_550,
        allowance_ns=250,
        interruption_issued_ns=1_500,
        expected_sources={"tracking"},
        allowed_producers={(producer.role, producer.generation)},
    )
    assert stopped_satisfied(report, **kwargs)
    report.producer_ends[0].end_monotonic_ns = 1_501
    assert not stopped_satisfied(report, **kwargs)
    report.producer_ends.clear()
    assert not stopped_satisfied(report, **kwargs)


def test_normal_stop_requires_scheduled_cutoff_and_visual_stimulus_idle() -> None:
    producer = pb.ProcessIdentity(role="renderer", generation=str(uuid.uuid4()))
    report = pb.StoppedReport(
        actual_stop_monotonic_ns=2_010,
        trial_activity_stopped=True,
        recording_interval_sealed=True,
        visual_stimulus_idle=True,
        producer_ends=[
            pb.ProducerRecordingEnd(
                producer=producer, source_id="renderer", end_monotonic_ns=2_000
            )
        ],
    )
    report.context.backend.backend_name = "visual_stimulus"
    kwargs = dict(
        target_ns=1_000,
        end_ns=2_000,
        ingress_ns=2_020,
        allowance_ns=250,
        expected_sources={"renderer"},
        allowed_producers={(producer.role, producer.generation)},
    )
    assert stopped_satisfied(report, **kwargs)
    report.producer_ends[0].end_monotonic_ns = 2_001
    assert not stopped_satisfied(report, **kwargs)
    report.producer_ends[0].end_monotonic_ns = 2_000
    report.ClearField("visual_stimulus_idle")
    assert not stopped_satisfied(report, **kwargs)
