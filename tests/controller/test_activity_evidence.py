"""E05/E11 first activity and producer cutoff evidence stays source-specific."""

from __future__ import annotations

import uuid

import pytest

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


def test_free_running_camera_trial_requires_confirmed_high_and_low_marker() -> None:
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu

    producer = pb.ProcessIdentity(role="camera-worker", generation=str(uuid.uuid4()))
    started = pb.StartedReport(actual_start_monotonic_ns=1000)
    started.context.backend.backend_name = "acquisition"
    started.first_required_activity.add(
        kind="camera_callback",
        observed_monotonic_ns=1001,
        device_evidence=pb.DeviceProgressEvidence(
            camera=camera.CAMERA_ROLE_BEHAVIORAL, producer=producer
        ),
    )
    start_args = dict(
        target_ns=1000,
        ingress_ns=1010,
        allowance_ns=250,
        camera_roles={camera.CAMERA_ROLE_BEHAVIORAL},
        allowed_producers={(producer.role, producer.generation)},
        trial_state_required=True,
    )
    assert not started_satisfied(started, **start_args)
    pulse = started.acquisition_pulse_on
    pulse.CopyFrom(
        mcu.PulseCommandEvidence(
            command=mcu.PULSE_BOUNDARY_COMMAND_ON,
            outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
            applied=True,
            trial_state_selected=True,
            behavioral_selected=False,
            tracking_selected=False,
            eye_tracking_selected=False,
            scheduled_boundary_monotonic_ns=1000,
            dispatched_monotonic_ns=1000,
            acknowledged_monotonic_ns=1005,
        )
    )
    pulse.resulting_state.trial_state.enabled = True
    pulse.resulting_state.trial_state.running = True
    assert started_satisfied(started, **start_args)
    pulse.resulting_state.trial_state.running = False
    assert not started_satisfied(started, **start_args)

    stopped = pb.StoppedReport(
        actual_stop_monotonic_ns=2010,
        trial_activity_stopped=True,
        recording_interval_sealed=True,
    )
    stopped.context.backend.backend_name = "acquisition"
    stopped.producer_ends.add(
        producer=producer, source_id="behavioral", end_monotonic_ns=2000
    )
    pulse = stopped.acquisition_pulse_off
    pulse.CopyFrom(started.acquisition_pulse_on)
    pulse.command = mcu.PULSE_BOUNDARY_COMMAND_OFF
    pulse.scheduled_boundary_monotonic_ns = 2000
    pulse.dispatched_monotonic_ns = 2000
    pulse.acknowledged_monotonic_ns = 2005
    stop_args = dict(
        target_ns=1000,
        end_ns=2000,
        ingress_ns=2020,
        allowance_ns=250,
        expected_sources={"behavioral"},
        allowed_producers={(producer.role, producer.generation)},
        trial_state_required=True,
    )
    assert stopped_satisfied(stopped, **stop_args)
    pulse.resulting_state.trial_state.running = True
    assert not stopped_satisfied(stopped, **stop_args)
    pulse.resulting_state.trial_state.ClearField("running")
    assert not stopped_satisfied(stopped, **stop_args)


def test_normal_trial_boundaries_keep_all_camera_outputs_unselected() -> None:
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu

    producer = pb.ProcessIdentity(role="camera-worker", generation=str(uuid.uuid4()))
    started = pb.StartedReport(actual_start_monotonic_ns=1_000)
    started.context.backend.backend_name = "acquisition"
    started.first_required_activity.add(
        kind="camera_callback",
        observed_monotonic_ns=1_001,
        device_evidence=pb.DeviceProgressEvidence(
            camera=camera.CAMERA_ROLE_BEHAVIORAL, producer=producer
        ),
    )
    start_args = dict(
        target_ns=1_000,
        ingress_ns=1_010,
        allowance_ns=250,
        camera_roles={camera.CAMERA_ROLE_BEHAVIORAL},
        external_camera_roles={camera.CAMERA_ROLE_BEHAVIORAL},
        allowed_producers={(producer.role, producer.generation)},
    )
    assert started_satisfied(started, **start_args)
    started.acquisition_pulse_on.CopyFrom(
        mcu.PulseCommandEvidence(
            behavioral_selected=True,
            tracking_selected=False,
            eye_tracking_selected=False,
        )
    )
    assert not started_satisfied(started, **start_args)

    stopped = pb.StoppedReport(
        actual_stop_monotonic_ns=2_010,
        trial_activity_stopped=True,
        recording_interval_sealed=True,
        producer_ends=[
            pb.ProducerRecordingEnd(
                producer=producer, source_id="behavioral", end_monotonic_ns=2_000
            )
        ],
    )
    stopped.context.backend.backend_name = "acquisition"
    stop_args = dict(
        target_ns=1_000,
        end_ns=2_000,
        ingress_ns=2_020,
        allowance_ns=250,
        expected_sources={"behavioral"},
        allowed_producers={(producer.role, producer.generation)},
        external_camera_roles={camera.CAMERA_ROLE_BEHAVIORAL},
    )
    assert stopped_satisfied(stopped, **stop_args)
    stopped.acquisition_pulse_off.CopyFrom(
        mcu.PulseCommandEvidence(
            behavioral_selected=True,
            tracking_selected=False,
            eye_tracking_selected=False,
        )
    )
    assert not stopped_satisfied(stopped, **stop_args)


@pytest.mark.parametrize(
    "field",
    ["behavioral_selected", "tracking_selected", "eye_tracking_selected"],
)
def test_interruption_off_requires_exact_external_roles_and_trial_state(
    field: str,
) -> None:
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu

    producer = pb.ProcessIdentity(role="camera-worker", generation=str(uuid.uuid4()))
    report = pb.StoppedReport(
        actual_stop_monotonic_ns=1_550,
        trial_activity_stopped=True,
        recording_interval_sealed=True,
        producer_ends=[
            pb.ProducerRecordingEnd(
                producer=producer, source_id="behavioral", end_monotonic_ns=1_450
            )
        ],
    )
    report.context.backend.backend_name = "acquisition"
    pulse = report.acquisition_pulse_off
    pulse.CopyFrom(
        mcu.PulseCommandEvidence(
            command=mcu.PULSE_BOUNDARY_COMMAND_OFF,
            outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
            applied=True,
            behavioral_selected=True,
            tracking_selected=False,
            eye_tracking_selected=False,
            trial_state_selected=True,
            dispatched_monotonic_ns=1_451,
            acknowledged_monotonic_ns=1_460,
            stop_issued_monotonic_ns=1_500,
            resulting_state=mcu.MicrocontrollerState(
                trial_state=mcu.PulseOutputState(enabled=True, running=False)
            ),
        )
    )
    args = dict(
        target_ns=1_000,
        end_ns=2_000,
        ingress_ns=1_600,
        allowance_ns=250,
        interruption_issued_ns=1_500,
        expected_sources={"behavioral"},
        allowed_producers={(producer.role, producer.generation)},
        external_camera_roles={camera.CAMERA_ROLE_BEHAVIORAL},
        trial_state_required=True,
    )
    assert stopped_satisfied(report, **args)
    setattr(pulse, field, True if field != "behavioral_selected" else False)
    assert not stopped_satisfied(report, **args)
