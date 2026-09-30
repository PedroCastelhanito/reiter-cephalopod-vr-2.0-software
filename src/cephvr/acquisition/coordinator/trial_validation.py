"""Pure worker lifecycle, pulse and output evidence predicates (E05/E11)."""

from __future__ import annotations

from cephvr.acquisition.coordinator.session_payloads import role_name
from cephvr.acquisition.state import SessionRecord, TrialRecord, WorkerRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import types_pb2 as control


class TrialLifecycleValidation:
    """Validate exact evidence using explicit retained worker/session records."""

    def validate_started(
        self,
        worker: WorkerRecord,
        evidence: acq.WorkerLifecycleEvidence,
        session: SessionRecord | None,
        trial: TrialRecord | None,
        *,
        ingress_ns: int,
        allowance_ns: int,
    ) -> None:
        item = evidence.started
        child = worker.child_operations.get(evidence.operation.command_id)
        cutoff = (
            trial.start_monotonic_ns + allowance_ns
            if trial is not None and trial.start_monotonic_ns is not None
            else 0
        )
        callbacks = [
            activity
            for activity in item.first_activity
            if activity.kind == "camera_callback"
        ]
        setting = (
            getattr(session.confirmed_settings, role_name(worker.context.camera))
            if session is not None and session.confirmed_settings is not None
            else None
        )
        recording = [
            activity
            for activity in item.first_activity
            if activity.kind == "recording_input_processing"
        ]
        recording_scope_unavailable = bool(
            session is not None
            and f"{role_name(worker.context.camera)}.recording"
            in session.unavailable_resources
        )
        if (
            session is None
            or trial is None
            or evidence.source.work != trial.work
            or cutoff <= 0
            or ingress_ns > cutoff
            or worker.context.camera not in session.required_cameras
            or child is None
            or child.kind != "schedule_trial"
            or worker.trial is None
            or worker.trial.schedule != evidence.operation
            or not item.HasField("actual_start_monotonic_ns")
            or len(callbacks) != 1
            or not callbacks[0].HasField("device_evidence")
            or not callbacks[0].device_evidence.HasField("camera")
            or callbacks[0].device_evidence.camera != worker.context.camera
            or callbacks[0].device_evidence.producer != worker.launch.worker
            or callbacks[0].observed_monotonic_ns != item.actual_start_monotonic_ns
            or not (trial.start_monotonic_ns or 0)
            <= callbacks[0].observed_monotonic_ns
            <= ingress_ns
            or setting is None
            or (
                setting.HasField("save_video")
                and setting.save_video
                and not recording_scope_unavailable
                and len(recording) != 1
            )
            or (
                recording
                and (
                    recording[0].observed_monotonic_ns
                    < callbacks[0].observed_monotonic_ns
                    or recording[0].observed_monotonic_ns > ingress_ns
                    or recording[0].observed_monotonic_ns > cutoff
                    or not recording[0].HasField("device_evidence")
                    or not recording[0].device_evidence.HasField("camera")
                    or recording[0].device_evidence.camera != worker.context.camera
                    or recording[0].device_evidence.producer != worker.launch.worker
                )
            )
            or any(
                activity.kind not in {"camera_callback", "recording_input_processing"}
                for activity in item.first_activity
            )
            or len(item.first_activity) != len(callbacks) + len(recording)
        ):
            raise ValueError(
                "Started evidence lacks exact camera callback and required recording activity"
            )

    def validate_stopped(
        self,
        worker: WorkerRecord,
        evidence: acq.WorkerLifecycleEvidence,
        session: SessionRecord | None,
        trial: TrialRecord | None,
        *,
        ingress_ns: int,
    ) -> None:
        child = worker.child_operations.get(evidence.operation.command_id)
        item = evidence.stopped
        cutoff = trial.stop_deadline_ns if trial is not None else None
        needs_recording_seal = bool(
            trial is not None
            and any(
                output.backend.backend_name == "acquisition"
                and output.extension == "mp4"
                and output.output_tag.startswith(
                    role_name(worker.context.camera) + "_cam"
                )
                for output in trial.outputs
            )
        )
        if (
            session is None
            or trial is None
            or evidence.source.work != trial.work
            or cutoff is None
            or ingress_ns > cutoff
            or worker.trial is None
            or worker.trial.stop is None
            or worker.trial.stop.command_id != evidence.operation.command_id
            or child is None
            or child.kind != "stop_trial"
            or not item.HasField("activity_stopped")
            or not item.activity_stopped
            or not item.HasField("actual_stop_monotonic_ns")
            or not item.HasField("recording_end_monotonic_ns")
            or item.recording_end_monotonic_ns <= 0
            or item.actual_stop_monotonic_ns > cutoff
            or (needs_recording_seal and not item.recording_interval_sealed)
        ):
            raise ValueError("Stopped evidence differs from its retained stop cutoff")

    def validate_finished(
        self,
        worker: WorkerRecord,
        evidence: acq.WorkerLifecycleEvidence,
        session: SessionRecord | None,
        trial: TrialRecord | None,
    ) -> None:
        child = worker.child_operations.get(evidence.operation.command_id)
        item = evidence.finished
        expected = (
            {
                output.output_key: output
                for output in trial.outputs
                if output.backend.backend_name == "acquisition"
                and output.output_tag.startswith(
                    role_name(worker.context.camera) + "_cam"
                )
            }
            if trial is not None
            else {}
        )
        keys = [output.output_key for output in item.outputs]
        outputs_valid = len(keys) == len(set(keys)) and set(keys) == set(expected)
        if outputs_valid:
            outputs_valid = all(
                output.path == expected[output.output_key].path
                and expected[output.output_key].HasField("path")
                and output.closure
                in {
                    control.OUTPUT_CLOSURE_CLOSED,
                    control.OUTPUT_CLOSURE_FAILED,
                    control.OUTPUT_CLOSURE_NOT_STARTED,
                }
                and output.HasField("artifact_present")
                for output in item.outputs
            )
        if (
            session is None
            or trial is None
            or evidence.source.work != trial.work
            or worker.trial is None
            or worker.trial.stop is None
            or worker.trial.stop.command_id != evidence.operation.command_id
            or child is None
            or child.kind != "stop_trial"
            or not item.HasField("activity_stopped")
            or not item.activity_stopped
            or not outputs_valid
        ):
            raise ValueError("Finished evidence differs from its exact output plans")


def empty_video_exception(
    plans: list[control.OutputPlan],
    results: list[control.OutputResult],
    missing: control.OutputResult,
) -> bool:
    plan = next((item for item in plans if item.output_key == missing.output_key), None)
    if (
        plan is None
        or plan.extension != "mp4"
        or plan.output_tag not in {"behavioral_cam", "tracking_cam"}
        or missing.camera_video_content != control.CAMERA_VIDEO_CONTENT_NO_FRAMES
        or missing.artifact_present
        or missing.failure.ByteSize()
    ):
        return False
    detail_tag = plan.output_tag + "_frames"
    details = [
        item
        for item in plans
        if item.backend == plan.backend
        and item.trial == plan.trial
        and item.output_tag == detail_tag
        and item.extension == "jsonl"
    ]
    if len(details) != 1:
        return False
    detail = next(
        (item for item in results if item.output_key == details[0].output_key), None
    )
    return bool(
        detail is not None
        and detail.closure == control.OUTPUT_CLOSURE_CLOSED
        and detail.artifact_present
        and not detail.failure.ByteSize()
    )


def valid_pulse(
    evidence: mcu.PulseCommandEvidence | None,
    *,
    command: mcu.PulseBoundaryCommand,
    boundary_ns: int | None,
) -> bool:
    return bool(
        evidence is not None
        and evidence.command == command
        and evidence.outcome == mcu.PULSE_COMMAND_OUTCOME_APPLIED
        and evidence.HasField("applied")
        and evidence.applied
        and evidence.HasField("acknowledged_monotonic_ns")
        and (
            boundary_ns is None
            or evidence.scheduled_boundary_monotonic_ns == boundary_ns
        )
    )


def pulse_off_satisfies_trial(trial: TrialRecord) -> bool:
    evidence = trial.pulse_off
    if valid_pulse(
        evidence,
        command=mcu.PULSE_BOUNDARY_COMMAND_OFF,
        boundary_ns=trial.end_monotonic_ns,
    ):
        return True
    return bool(
        trial.stop_issued_ns is not None
        and valid_pulse(
            evidence,
            command=mcu.PULSE_BOUNDARY_COMMAND_OFF,
            boundary_ns=None,
        )
        and evidence is not None
        and evidence.HasField("stop_issued_monotonic_ns")
        and evidence.stop_issued_monotonic_ns == trial.stop_issued_ns
    )


def finished_cutoff_ns(trial: TrialRecord, allowance_ns: int, ingress_ns: int) -> int:
    stop_time = trial.stop_issued_ns or trial.end_monotonic_ns or ingress_ns
    return stop_time + allowance_ns


def finished_is_timely(trial: TrialRecord, allowance_ns: int, ingress_ns: int) -> bool:
    return ingress_ns <= finished_cutoff_ns(trial, allowance_ns, ingress_ns)
