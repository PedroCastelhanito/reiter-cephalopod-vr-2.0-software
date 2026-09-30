"""Typed boundaries to registered peers; importing them starts no runtime."""

from __future__ import annotations

from typing import Protocol

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.synchronization.v1 import spikeglx_pb2
from cephvr.tracking.v1 import services_pb2 as tracking_svc


class BackendPort(Protocol):
    context: pb.BackendContext

    async def setup_session(
        self, request: svc.SetupSessionRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def cancel_setup(
        self, request: svc.BackendCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def prepare_trial(
        self, request: svc.PrepareTrialRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def schedule_trial(
        self, request: svc.ScheduleTrialRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def release_trial(
        self, request: svc.ReleaseTrialRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def interrupt_session(
        self, request: svc.InterruptSessionRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def cleanup(
        self, request: svc.BackendCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def get_state(
        self, request: svc.BackendQuery, *, deadline_ns: int
    ) -> pb.ParticipantState: ...
    async def bind_tracking_data(
        self, request: tracking_svc.TrackingDataBinding, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def confirm_tracking_input(
        self, request: svc.TrackingInputConfirmation, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def report_preview_consumer_state(
        self, request: svc.PreviewConsumerReport
    ) -> pb.ReportReceipt: ...
    async def apply_incident_scope(
        self, request: svc.IncidentScopeRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def get_retained_result(
        self, request: svc.RetainedResultQuery, *, deadline_ns: int
    ) -> svc.RetainedResult: ...
    async def confirm_configuration(
        self, request: svc.AcquisitionConfigurationConfirmation, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def initialize_display(
        self, request: svc.VRDisplayInitializationRequest, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def execute_camera_command(
        self, request: svc.AcquisitionCameraCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...


class SupervisorPort(Protocol):
    async def register_context(
        self, request: svc.RegisterContextRequest
    ) -> svc.RegistrationReceipt: ...
    async def request_shutdown(
        self, request: svc.ApplicationShutdownRequest
    ) -> pb.CommandAdmission: ...
    async def report_preview_consumer_state(
        self, request: svc.PreviewConsumerReport
    ) -> pb.ReportReceipt: ...


class SpikeGLXPort(Protocol):
    async def prepare(
        self, configuration: pb.ExperimentConfiguration, session: pb.SessionContext
    ) -> spikeglx_pb2.SpikeGLXPreparation: ...
    async def verify_before_start(self) -> bool: ...
    async def start_and_verify_writing(self) -> bool: ...
    async def stop_expected_run(self) -> bool: ...
