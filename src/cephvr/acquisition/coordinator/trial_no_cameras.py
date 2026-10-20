"""Trial-state-only lifecycle evidence; never fabricate camera callbacks or files."""

from cephvr.acquisition.coordinator.trial_delivery import TrialReportDelivery
from cephvr.acquisition.coordinator.trial_validation import (
    finished_cutoff_ns,
    pulse_off_satisfies_trial,
    valid_pulse,
)
from cephvr.acquisition.state import SessionRecord, TrialRecord
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import types_pb2 as control


async def report_trial_state_only(
    session: SessionRecord,
    trial: TrialRecord,
    backend: control.BackendContext,
    policies: control.ControlPolicies,
    delivery: TrialReportDelivery,
    now: int,
) -> None:
    if (
        session.required_cameras
        or session.confirmed_settings is None
        or not session.confirmed_settings.pulses.trial_state_enabled
        or session.trial is not trial
    ):
        raise RuntimeError(
            "camera-free lifecycle requires a locked trial-state-only session"
        )
    context = control.ReportContext(
        backend=backend, work=trial.work, operation=trial.preparation
    )
    if trial.stop is None:
        pulse = trial.pulse_on
        if trial.started_report is not None or not valid_pulse(
            pulse,
            command=mcu.PULSE_BOUNDARY_COMMAND_ON,
            boundary_ns=trial.start_monotonic_ns,
        ):
            return
        assert pulse is not None
        report = control.StartedReport(
            context=context,
            actual_start_monotonic_ns=pulse.acknowledged_monotonic_ns,
            acquisition_pulse_on=pulse,
        )
        trial.pending_started_report = report
        receipt = await delivery.deliver(
            trial,
            "started",
            report,
            (trial.start_monotonic_ns or 0) + policies.start_evidence_allowance_ns,
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("controller rejected trial-state Started evidence")
        return
    if not pulse_off_satisfies_trial(trial):
        return
    if trial.outputs:
        raise RuntimeError("camera-free trial unexpectedly owns camera outputs")
    if trial.stopped_report is None:
        report_stop = control.StoppedReport(
            context=context,
            actual_stop_monotonic_ns=now,
            trial_activity_stopped=True,
            recording_interval_sealed=True,
            acquisition_pulse_off=trial.pulse_off,
        )
        trial.pending_stopped_report = report_stop
        receipt = await delivery.deliver(
            trial, "stopped", report_stop, trial.stop_deadline_ns or 0
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("controller rejected trial-state Stopped evidence")
    if trial.finished_report is None:
        report_finish = control.FinishedReport(
            context=context, trial_activity_stopped=True
        )
        trial.pending_finished_report = report_finish
        receipt = await delivery.deliver(
            trial,
            "finished",
            report_finish,
            finished_cutoff_ns(trial, policies.trial_finished.initial_ns, now),
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("controller rejected trial-state Finished evidence")
