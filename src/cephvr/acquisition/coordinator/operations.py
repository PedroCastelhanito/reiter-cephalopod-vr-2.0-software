"""Typed command operations required by acquisition's existing protobuf services."""

from __future__ import annotations

from typing import Protocol

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control


class CoordinatorOperations(Protocol):
    """Feature operations behind the authenticated gRPC service boundary."""

    identity: control.ProcessIdentity

    async def report_dispatch_failure(
        self,
        method: str,
        command: wire.BackendCommand,
        outcome: control.OperationState,
        deadline_ns: int,
    ) -> None: ...

    async def apply_incident_scope(
        self, request: wire.IncidentScopeRequest, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def setup_session(
        self, request: wire.SetupSessionRequest, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def cancel_setup(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def prepare_trial(
        self, request: wire.PrepareTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def schedule_trial(
        self, request: wire.ScheduleTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def release_trial(
        self, request: wire.ReleaseTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def stop_trial(
        self, request: wire.StopTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def abort_trial(
        self, request: wire.StopTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def interrupt_session(
        self, request: wire.InterruptSessionRequest, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def get_state(
        self, request: wire.BackendQuery, *, deadline_ns: int
    ) -> control.ParticipantState: ...
    async def get_retained_result(
        self, request: wire.RetainedResultQuery, *, deadline_ns: int
    ) -> wire.RetainedResult: ...
    async def cleanup(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def shutdown(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...

    async def confirm_tracking_input(
        self, request: wire.TrackingInputConfirmation, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def apply_camera_settings(
        self, request: wire.AcquisitionCameraSettingsCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def apply_pulse_configuration(
        self, request: wire.AcquisitionPulseCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def report_preview_consumer_state(
        self, request: wire.PreviewConsumerReport, *, deadline_ns: int
    ) -> control.ReportReceipt: ...
    async def execute_camera_command(
        self, request: wire.AcquisitionCameraCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def execute_microcontroller_command(
        self, request: wire.AcquisitionMicrocontrollerCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def confirm_configuration(
        self, request: wire.AcquisitionConfigurationConfirmation, *, deadline_ns: int
    ) -> control.CommandAdmission: ...

    async def report_worker_warnings(
        self, request: acq.WorkerWarningReport, *, deadline_ns: int, ingress_ns: int
    ) -> control.ReportReceipt: ...
    async def report_worker_operation(
        self, request: acq.WorkerOperationReport, *, deadline_ns: int, ingress_ns: int
    ) -> control.ReportReceipt: ...
    async def report_worker_lifecycle(
        self, request: acq.WorkerLifecycleEvidence, *, deadline_ns: int, ingress_ns: int
    ) -> control.ReportReceipt: ...
    async def report_worker_heartbeat(
        self, request: control.HeartbeatReport, *, deadline_ns: int, ingress_ns: int
    ) -> control.ReportReceipt: ...
