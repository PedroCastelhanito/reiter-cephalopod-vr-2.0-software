"""Coordinator assembly and existing acquisition service operations (A02/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.coordinator.authority_failure import (
    CoordinatorAuthorityFailure,
)
from cephvr.acquisition.coordinator.cleanup import CoordinatorCleanup
from cephvr.acquisition.coordinator.configuration_resolution import (
    ConfigurationResolution,
)
from cephvr.acquisition.coordinator.evidence import WorkerEvidenceCoordinator
from cephvr.acquisition.coordinator.health import AcquisitionHealth
from cephvr.acquisition.coordinator.incidents import IncidentScopeOwner
from cephvr.acquisition.coordinator.manual_configuration import ManualConfiguration
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_devices import ManualDevices
from cephvr.acquisition.coordinator.manual_preview import ManualPreview
from cephvr.acquisition.coordinator.manual_preview_pulse import (
    ManualPreviewPulseLifecycle,
)
from cephvr.acquisition.coordinator.manual_pulses import ManualPulses
from cephvr.acquisition.coordinator.operations import CoordinatorOperations
from cephvr.acquisition.coordinator.queries import CoordinatorQueries
from cephvr.acquisition.coordinator.session import SessionSetup
from cephvr.acquisition.coordinator.shutdown import CoordinatorShutdown
from cephvr.acquisition.coordinator.trial_lifecycle import TrialLifecycleReports
from cephvr.acquisition.coordinator.trials import TrialCoordinator
from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.ports import (
    ControllerPort,
    ResourcePort,
    SerialOwnerPort,
    SupervisorPort,
)
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    CoordinatorState,
    TrialRecord,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


class AcquisitionCoordinatorRuntime(CoordinatorOperations):
    """Compose focused feature owners over one authoritative coordinator state."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        configuration: ConfigurationRecord,
        control_policies: control.ControlPolicies,
        commands: CommandLedger,
        resource_ledger: NativeResourceLedger,
        workers: WorkerRegistry,
        controller: ControllerPort,
        supervisor: SupervisorPort,
        serial: SerialOwnerPort,
        resource_port: ResourcePort,
        session_config_reference: Callable[[wire.SetupSessionRequest], str],
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity.process
        self.coordinator_identity = identity
        self.configuration = configuration
        self.control_policies = control.ControlPolicies.FromString(
            control_policies.SerializeToString(deterministic=True)
        )
        self.commands = commands
        self.resource_ledger = resource_ledger
        self.workers = workers
        self.controller = controller
        self.supervisor = supervisor
        self.serial = serial
        self.resource_port = resource_port
        self.clock = clock
        self.lock = asyncio.Lock()
        self._last_error: control.ErrorReport | None = None
        self.state = CoordinatorState(
            identity=identity,
            configuration=configuration,
            workers=workers.workers,
            launches=workers.launches,
            resource_ledger=resource_ledger,
            commands=commands,
            control_policies=self.control_policies,
        )
        self.configuration_resolution = ConfigurationResolution(
            identity=identity,
            configuration=configuration,
            controller=controller,
            lock=self.lock,
            clock=clock,
        )
        self.device_status = ManualDeviceStatusReporter(
            identity=identity,
            controller=controller,
            commands=commands,
            pulse=self.state.pulse,
            clock=clock,
        )
        self.manual_configuration = ManualConfiguration(
            configuration, identity, self.state.session_slot, self.device_status, clock
        )
        self.queries = CoordinatorQueries(
            identity=identity,
            session_slot=self.state.session_slot,
            workers=self.state.workers,
            commands=commands,
            device_status=self.device_status,
            current_error=lambda: self._last_error,
            clock=clock,
        )
        self.manual_preview = ManualPreview(
            identity=identity,
            configuration=configuration,
            session_slot=self.state.session_slot,
            pulse=self.state.pulse,
            workers=workers,
            serial=serial,
            resources=self.state.resources,
            resource_ledger=resource_ledger,
            resource_port=resource_port,
            controller=controller,
            commands=commands,
            resolution=self.configuration_resolution,
            device_status=self.device_status,
            lock=self.lock,
            clock=clock,
        )
        self.manual_preview_pulse = ManualPreviewPulseLifecycle(
            identity=identity,
            configuration=configuration,
            workers=workers.workers,
            pulse=self.state.pulse,
            device_status=self.device_status,
            serial=serial,
            resources=self.state.resources,
            resource_ledger=resource_ledger,
            resource_port=resource_port,
            transfers=self.manual_preview.transfers,
            lock=self.lock,
            clock=clock,
        )
        self.manual_preview.start_flow.bind_pulse_lifecycle(self.manual_preview_pulse)
        self.manual_devices = ManualDevices(
            identity=identity,
            configuration=configuration,
            session_slot=self.state.session_slot,
            workers=workers,
            controller=controller,
            resolution=self.configuration_resolution,
            device_status=self.device_status,
            lock=self.lock,
            clock=clock,
        )
        self.manual_pulses = ManualPulses(
            identity=identity,
            configuration=configuration,
            session_slot=self.state.session_slot,
            pulse=self.state.pulse,
            workers=workers,
            serial=serial,
            controller=controller,
            resolution=self.configuration_resolution,
            device_status=self.device_status,
            preview=self.manual_preview_pulse,
            lock=self.lock,
            clock=clock,
        )
        self.session = SessionSetup(
            identity=identity,
            configuration=configuration,
            session_slot=self.state.session_slot,
            pulse=self.state.pulse,
            workers=workers,
            serial=serial,
            resources=self.state.resources,
            resource_ledger=resource_ledger,
            resource_port=resource_port,
            controller=controller,
            supervisor=supervisor,
            session_config_reference=session_config_reference,
            lock=self.lock,
            clock=clock,
        )
        self.cleanup_owner = CoordinatorCleanup(
            identity=identity,
            session_slot=self.state.session_slot,
            workers=self.state.workers,
            resources=self.state.resources,
            pulse=self.state.pulse,
            resource_ledger=resource_ledger,
            commands=commands,
            resource_port=resource_port,
            serial=serial,
            controller=controller,
            supervisor=supervisor,
            worker_cleanup_complete=workers.cleanup_complete,
            lock=self.lock,
            clock=clock,
        )
        self.trial_lifecycle = TrialLifecycleReports(
            identity=identity,
            session_slot=self.state.session_slot,
            workers=self.state.workers,
            controller=controller,
            policies=self.control_policies,
            commands=commands,
            lock=self.lock,
            clock=clock,
        )
        self.trials = TrialCoordinator(
            identity=identity,
            session_slot=self.state.session_slot,
            workers=self.state.workers,
            resources=self.state.resources,
            serial=serial,
            pulse=self.state.pulse,
            serial_ack_timeout_ns=(configuration.file_policies.serial_ack_timeout_ns),
            start_evidence_allowance_ns=self.control_policies.start_evidence_allowance_ns,
            lifecycle_delivery_ns=self.control_policies.trial_finished.initial_ns,
            stop_evidence_allowance_ns=self.control_policies.stop_evidence_allowance_ns,
            controller=controller,
            lifecycle=self.trial_lifecycle,
            prior_completion_confirmed=self._prior_completion_confirmed,
            lock=self.lock,
            clock=clock,
        )
        self.shutdown_owner = CoordinatorShutdown(
            identity=identity,
            session_slot=self.state.session_slot,
            session_cancel=self.session,
            trial_stop=self.trials,
            cleanup=self.cleanup_owner,
            clock=clock,
        )
        self.shutdown_requested = self.shutdown_owner.shutdown_requested
        self.authority_failure = CoordinatorAuthorityFailure(
            identity=identity,
            session_slot=self.state.session_slot,
            workers=self.state.workers,
            supervisor=supervisor,
            shutdown=self.shutdown_owner,
            retain_error=self._retain_error,
            clock=clock,
        )
        self.evidence = WorkerEvidenceCoordinator(
            backend=identity.backend,
            owner=identity.process,
            settings=configuration.settings,
            workers=self.state.workers,
            resources=self.state.resources,
            resource_ledger=resource_ledger,
            commands=commands,
            current_session=lambda: self.state.session_slot.current,
            controller=controller,
            lock=self.lock,
            control_policies=self.control_policies,
            configuration_resolution=self.configuration_resolution,
            trial_lifecycle=self.trial_lifecycle,
        )
        self.incidents = IncidentScopeOwner(
            identity=identity,
            session_slot=self.state.session_slot,
            workers=self.state.workers,
            controller=controller,
            session_setup=self.session,
            trials=self.trials,
            lock=self.lock,
            clock=clock,
        )
        self.health = AcquisitionHealth(
            identity=identity,
            workers=self.state.workers,
            commands=commands,
            session_slot=self.state.session_slot,
            pulse=self.state.pulse,
            supervisor=supervisor,
            serial=serial,
            heartbeat_interval_ns=workers.heartbeat_interval_ns,
            health_silence_ns=workers.health_silence_ns,
            recovery_ns=self.control_policies.recovery_ns,
            serial_keepalive_interval_ns=configuration.file_policies.serial_keepalive_interval_ns,
            serial_communication_timeout_ns=configuration.file_policies.serial_communication_timeout_ns,
            serial_ack_timeout_ns=configuration.file_policies.serial_ack_timeout_ns,
            catalogue_lock=self.session.catalogue.catalogue_lock,
            failure_handler=self.authority_failure.health_failure,
            clock=clock,
        )

    async def apply_incident_scope(
        self, request: wire.IncidentScopeRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.incidents.apply(request, deadline_ns=deadline_ns)

    async def report_dispatch_failure(
        self,
        method: str,
        command: wire.BackendCommand,
        outcome: control.OperationState,
        deadline_ns: int,
    ) -> None:
        """Push the exact retained terminal rejection without changing admission."""
        if deadline_ns <= 0:
            return
        report = control.LifecycleReport(
            operation=control.BackendOperationReport(
                source=self.coordinator_identity.backend,
                operation=control.OperationState(
                    context=outcome.context,
                    command=method,
                    work=command.work,
                    complete=True,
                    succeeded=False,
                    failure=outcome.failure,
                ),
            )
        )
        await self.controller.report_lifecycle(report, deadline_ns=deadline_ns)

    async def setup_session(
        self, request: wire.SetupSessionRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        await self.session.resolve_and_adopt(request, deadline_ns=deadline_ns)
        return _accepted(request.command.command_id)

    async def cancel_setup(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        session = self.state.session_slot.current
        if (
            session is None
            or request.issuer != self.coordinator_identity.controller
            or request.target != self.coordinator_identity.backend
            or request.work != session.work
            or (
                request.HasField("parent_operation")
                and request.parent_operation != session.operation
            )
            or self.clock() >= deadline_ns
        ):
            return _rejected(
                request.command_id, "CANCEL_SETUP", "Setup cancellation is stale"
            )
        await self.session.cancel(session, deadline_ns=deadline_ns)
        return _accepted(request.command_id)

    async def prepare_trial(
        self, request: wire.PrepareTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.trials.prepare(request, deadline_ns=deadline_ns)

    async def schedule_trial(
        self, request: wire.ScheduleTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.trials.schedule(request, deadline_ns=deadline_ns)

    async def release_trial(
        self, request: wire.ReleaseTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.trials.release(request, deadline_ns=deadline_ns)

    async def stop_trial(
        self, request: wire.StopTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.trials.stop(request, deadline_ns=deadline_ns)

    async def abort_trial(
        self, request: wire.StopTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.trials.stop(request, deadline_ns=deadline_ns, aborted=True)

    async def interrupt_session(
        self, request: wire.InterruptSessionRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.trials.interrupt_session(request, deadline_ns=deadline_ns)

    async def confirm_tracking_input(
        self, request: wire.TrackingInputConfirmation, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.session.confirm_tracking_input(
            request, deadline_ns=deadline_ns
        )

    async def confirm_configuration(
        self,
        request: wire.AcquisitionConfigurationConfirmation,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        session = self.state.session_slot.current
        if (
            session is not None
            and request.resolution_operation == session.operation
            and request.command.work == session.work
        ):
            return await self.session.confirm_configuration(
                request, deadline_ns=deadline_ns
            )
        return await self.configuration_resolution.confirm(
            request, deadline_ns=deadline_ns
        )

    async def apply_camera_settings(
        self, request: wire.AcquisitionCameraSettingsCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.manual_devices.apply(request, deadline_ns=deadline_ns)

    async def apply_pulse_configuration(
        self, request: wire.AcquisitionPulseCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.manual_pulses.apply(request, deadline_ns=deadline_ns)

    async def execute_camera_command(
        self, request: wire.AcquisitionCameraCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        rejected = self.manual_configuration.install(request, deadline_ns)
        if rejected is not None:
            return rejected
        if request.kind in {
            wire.CAMERA_COMMAND_KIND_START_PREVIEW,
            wire.CAMERA_COMMAND_KIND_STOP_PREVIEW,
            wire.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
        }:
            return await self.manual_preview.execute(request, deadline_ns=deadline_ns)
        return await self.manual_devices.execute(request, deadline_ns=deadline_ns)

    async def execute_microcontroller_command(
        self, request: wire.AcquisitionMicrocontrollerCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        rejected = self.manual_configuration.install(request, deadline_ns)
        if rejected is not None:
            return rejected
        return await self.manual_pulses.execute_diagnostic(
            request, deadline_ns=deadline_ns
        )

    async def report_preview_consumer_state(
        self, request: wire.PreviewConsumerReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return await self.manual_preview.report_consumer(
            request, deadline_ns=deadline_ns
        )

    async def report_worker_warnings(
        self,
        request: acq.WorkerWarningReport,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        return await self.evidence.report_warnings(
            request, deadline_ns=deadline_ns, ingress_ns=ingress_ns
        )

    async def report_worker_operation(
        self,
        request: acq.WorkerOperationReport,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        return await self.evidence.report_operation(
            request, deadline_ns=deadline_ns, ingress_ns=ingress_ns
        )

    async def report_worker_lifecycle(
        self,
        request: acq.WorkerLifecycleEvidence,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        return await self.evidence.report_lifecycle(
            request, deadline_ns=deadline_ns, ingress_ns=ingress_ns
        )

    async def report_worker_heartbeat(
        self,
        request: control.HeartbeatReport,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        return await self.evidence.report_heartbeat(
            request, deadline_ns=deadline_ns, ingress_ns=ingress_ns
        )

    async def get_state(
        self, request: wire.BackendQuery, *, deadline_ns: int
    ) -> control.ParticipantState:
        return await self.queries.get_state(request, deadline_ns=deadline_ns)

    async def get_retained_result(
        self, request: wire.RetainedResultQuery, *, deadline_ns: int
    ) -> wire.RetainedResult:
        return await self.queries.get_retained_result(request, deadline_ns=deadline_ns)

    async def cleanup(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.shutdown_owner.cleanup_session(
            request, deadline_ns=deadline_ns
        )

    async def shutdown(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.shutdown_owner.request_shutdown(
            request, deadline_ns=deadline_ns
        )

    async def authority_lost(
        self, role: str, *, deadline_ns: int, observation_failed: bool = False
    ) -> None:
        await self.authority_failure.authority_lost(
            role, deadline_ns=deadline_ns, observation_failed=observation_failed
        )

    async def health_failure(
        self,
        source: control.ProcessIdentity,
        work: control.WorkContext,
        failure: control.Failure,
        deadline_ns: int,
    ) -> None:
        await self.authority_failure.health_failure(source, work, failure, deadline_ns)

    def _retain_error(self, error: control.ErrorReport) -> None:
        self._last_error = control.ErrorReport.FromString(
            error.SerializeToString(deterministic=True)
        )

    def _prior_completion_confirmed(self, trial: TrialRecord) -> bool:
        if trial.finished_report is None:
            return False
        for record in self.state.workers.values():
            worker_trial = record.trial
            if worker_trial is None or worker_trial.preparation is None:
                continue
            if not any(
                evidence.source.work == trial.work
                and evidence.WhichOneof("evidence") == "finished"
                and evidence.finished.activity_stopped
                for evidence in record.lifecycle_evidence.values()
            ):
                return False
        return True


def _accepted(command_id: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_ACCEPTED, command_id=command_id
    )


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
