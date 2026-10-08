"""Session Setup's camera-resolution/adoption barrier (E07/E08/A01/A02)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.coordinator.configuration_resolution import (
    confirmed_matches_resolution,
)
from cephvr.acquisition.coordinator.session_catalogue import SessionCatalogue
from cephvr.acquisition.coordinator.session_preparation import SessionPreparation
from cephvr.acquisition.coordinator.session_tracking import SessionTrackingConfirmation
from cephvr.acquisition.coordinator.session_validation import validate_setup_request
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
    PulseRecord,
    ResourceRecord,
    SessionRecord,
    SessionSlot,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.clock import host_time_ns


class SessionSetup:
    """Resolve all active devices, report once, and await controller adoption."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        configuration: ConfigurationRecord,
        session_slot: SessionSlot,
        pulse: PulseRecord,
        workers: WorkerRegistry,
        serial: SerialOwnerPort,
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        resource_port: ResourcePort,
        controller: ControllerPort,
        supervisor: SupervisorPort,
        session_config_reference: Callable[[wire.SetupSessionRequest], str],
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.configuration = configuration
        self.session_slot = session_slot
        self.pulse = pulse
        self.workers = workers
        self.serial = serial
        self.resources = resources
        self.resource_ledger = resource_ledger
        self.resource_port = resource_port
        self.controller = controller
        self.supervisor = supervisor
        self.session_config_reference = session_config_reference
        self.lock = lock
        self._setup_lock = asyncio.Lock()
        self.clock = clock
        self.catalogue = SessionCatalogue(
            identity=identity,
            session_slot=session_slot,
            supervisor=supervisor,
            lock=lock,
            commands=workers.commands,
            clock=clock,
        )
        self.tracking_confirmation = SessionTrackingConfirmation(
            identity=identity,
            session_slot=session_slot,
            resources=resources,
            resource_ledger=resource_ledger,
            clock=clock,
        )
        self.preparation = SessionPreparation(
            identity=identity,
            configuration=configuration,
            session_slot=session_slot,
            pulse=pulse,
            workers=workers,
            serial=serial,
            resources=resources,
            resource_ledger=resource_ledger,
            resource_port=resource_port,
            controller=controller,
            catalogue=self.catalogue,
            session_config_reference=session_config_reference,
            clock=clock,
        )

    async def resolve_and_adopt(
        self, request: wire.SetupSessionRequest, *, deadline_ns: int
    ) -> SessionRecord:
        async with self._setup_lock:
            return await self._resolve_and_adopt(request, deadline_ns=deadline_ns)

    async def _resolve_and_adopt(
        self, request: wire.SetupSessionRequest, *, deadline_ns: int
    ) -> SessionRecord:
        """Launch workers and complete the required controller readback roundtrip.

        This method returns only after the existing controller validator has adopted
        the resolved camera state via ConfirmConfiguration. It does not treat worker
        command acceptance or serial CONFIGURE readback as camera/Setup readiness.
        """
        session = validate_setup_request(
            request,
            deadline_ns,
            identity=self.identity,
            configuration=self.configuration,
            clock=self.clock,
        )
        async with self.lock:
            current = self.session_slot.current
            if current is not None and not current.cleanup_complete:
                raise RuntimeError("prior acquisition session still has obligations")
        session.reserve_cleanup_evidence(self.workers.commands)
        try:
            if current is not None:
                await self.workers.retire_completed_session(
                    current.work, deadline_ns=deadline_ns
                )
            async with self.lock:
                if self.session_slot.current is not current:
                    raise RuntimeError("prior session changed before Setup retirement")
                if current is not None:
                    self.session_slot.retain_completed(current, self.workers.commands)
                self.session_slot.current = session
                self.configuration.settings.CopyFrom(request.settings.acquisition)
                self.configuration.file_policies.CopyFrom(request.acquisition_policies)
                self.configuration.revision = request.plan.configuration_revision
                self.session_slot.interrupted = False
        except BaseException:
            if self.session_slot.current is not session:
                session.release_cleanup_proof(self.workers.commands)
            raise

        try:
            await self.catalogue.publish_catalogue(session, deadline_ns=deadline_ns)
            self._require_live_setup(session, deadline_ns)
            await self.preparation.retire_manual_workers(deadline_ns)
            self._require_live_setup(session, deadline_ns)
            await self.preparation.configure_pulses(request, deadline_ns)
            self._require_live_setup(session, deadline_ns)
            records = await self.preparation.launch_workers(
                session, request, deadline_ns
            )
            self._require_live_setup(session, deadline_ns)
            await self.preparation.resolve_cameras(
                session, request, records, deadline_ns
            )
            self._require_live_setup(session, deadline_ns)
            remaining = max(0, deadline_ns - self.clock()) / 1_000_000_000
            if remaining <= 0:
                raise TimeoutError("controller readback adoption missed Setup deadline")
            await asyncio.wait_for(session.resolution_confirmed.wait(), remaining)
            if session.interrupted or session.setup_cancelled:
                raise RuntimeError("Setup was cancelled before configuration adoption")
            await self.preparation.prepare_workers(
                session, request, records, deadline_ns
            )
            await self._wait_worker_setup(records, deadline_ns)
            self._require_live_setup(session, deadline_ns)
            remaining = max(0, deadline_ns - self.clock()) / 1_000_000_000
            if remaining <= 0:
                raise TimeoutError("camera worker Setup missed its original deadline")
            await asyncio.wait_for(session.ready_confirmed.wait(), remaining)
            if session.interrupted or session.setup_cancelled:
                raise RuntimeError("Setup was cancelled before aggregate Ready")
            receipt = await self.controller.report_lifecycle(
                control.LifecycleReport(
                    operation=control.BackendOperationReport(
                        source=self.identity.backend,
                        operation=control.OperationState(
                            context=session.operation,
                            command="setup_session",
                            work=session.work,
                            complete=True,
                            succeeded=True,
                        ),
                    )
                ),
                deadline_ns=deadline_ns,
            )
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError("controller rejected aggregate Setup completion")
            return session
        except BaseException:
            session.setup_cancelled = True
            await self.cancel(session, deadline_ns=deadline_ns)
            raise

    async def _wait_worker_setup(
        self, records: tuple[WorkerRecord, ...], deadline_ns: int
    ) -> None:
        for worker in records:
            operation = worker.setup_operation
            if operation is None:
                raise RuntimeError("camera worker Setup operation was not retained")
            child = worker.child_operations[operation.command_id]
            result = await wait_child_operation(
                child, deadline_ns, self.lock, self.clock
            )
            if not result.succeeded:
                raise RuntimeError(
                    f"camera role {worker.context.camera} Setup failed: "
                    f"{result.failure.code}: {result.failure.message}"
                )

    async def confirm_configuration(
        self,
        request: wire.AcquisitionConfigurationConfirmation,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        """Accept only the controller's exact adoption of this Setup resolution."""
        session = self.session_slot.current
        if session is None or session.setup_cancelled or session.interrupted:
            return _rejected(
                request.command.command_id, "STALE_SETUP", "no live Setup adoption"
            )
        if (
            self.clock() > (session.setup_deadline_ns or 0)
            or session.setup_deadline_ns is None
            or deadline_ns != session.setup_deadline_ns
        ):
            return _rejected(
                request.command.command_id,
                "SETUP_DEADLINE",
                "configuration confirmation missed its original deadline",
            )
        if (
            request.command.target != self.identity.backend
            or request.command.issuer != self.identity.controller
            or request.command.work.WhichOneof("work") != "session"
            or request.command.work.session != session.work.session
            or request.resolution_operation != session.operation
            or not request.HasField("requested_configuration_revision")
            or request.requested_configuration_revision
            != session.requested_configuration_revision
            or not request.HasField("confirmed_configuration_revision")
            or request.confirmed_configuration_revision < session.configuration_revision
            or not request.HasField("confirmed")
        ):
            return _rejected(
                request.command.command_id,
                "CONFIGURATION_IDENTITY",
                "confirmation differs from this exact acquisition Setup",
            )
        expected_cameras = _enabled_cameras(session)
        resolution = session.resolved_report
        if (
            resolution is None
            or {entry.camera for entry in resolution.cameras} != expected_cameras
        ):
            return _rejected(
                request.command.command_id,
                "CONFIGURATION_CAMERAS",
                "confirmed resolution camera set differs from Setup",
            )
        confirmed = control.AcquisitionSettings.FromString(
            request.confirmed.SerializeToString(deterministic=True)
        )
        if not confirmed_matches_resolution(
            confirmed,
            resolution,
            session.pulse_resolution,
            expected_cameras,
            request.confirmed_pulses if request.HasField("confirmed_pulses") else None,
        ):
            return _rejected(
                request.command.command_id,
                "CONFIGURATION_VALUES",
                "controller confirmation does not preserve the requested camera values",
            )
        async with self.lock:
            if (
                self.session_slot.current is not session
                or session.setup_cancelled
                or session.interrupted
                or self.clock() > (session.setup_deadline_ns or 0)
            ):
                return _rejected(
                    request.command.command_id,
                    "STALE_SETUP",
                    "Setup changed while configuration confirmation was admitted",
                )
            if session.resolution_confirmed.is_set():
                if (
                    session.confirmed_revision
                    != request.confirmed_configuration_revision
                    or session.confirmed_settings != confirmed
                ):
                    return _rejected(
                        request.command.command_id,
                        "CONFIGURATION_CONFLICT",
                        "confirmed configuration changed after adoption",
                    )
            else:
                session.confirmed_settings = confirmed
                session.confirmed_revision = request.confirmed_configuration_revision
                session.configuration_revision = (
                    request.confirmed_configuration_revision
                )
                session.resolution_confirmed.set()
                self.configuration.revision = request.confirmed_configuration_revision
                self.configuration.settings.CopyFrom(confirmed)
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )

    async def confirm_tracking_input(
        self, request: wire.TrackingInputConfirmation, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.tracking_confirmation.confirm_tracking_input(
            request, deadline_ns=deadline_ns
        )

    async def cancel(self, session: SessionRecord, *, deadline_ns: int) -> None:
        """Fence the Setup generation and retain worker cleanup failures."""
        if session.cleanup_deadline_ns is None:
            session.cleanup_deadline_ns = deadline_ns
        else:
            session.cleanup_deadline_ns = min(session.cleanup_deadline_ns, deadline_ns)
        session.setup_cancelled = True
        session.resolution_confirmed.set()
        for record in tuple(self.workers.workers.values()):
            if record.launch.work.WhichOneof("work") != "session":
                continue
            if (
                record.launch.work.session != session.work.session
                or record.port is None
            ):
                continue
            try:
                command, _child, port = retain_worker_command(
                    record,
                    work=session.work,
                    parent_operation=session.operation,
                    kind="cancel_setup",
                    deadline_ns=deadline_ns,
                    configuration_revision=session.configuration_revision,
                )
                await port.cancel_setup(command, deadline_ns=deadline_ns)
            except Exception:
                # The WorkerRecord and launch intent remain retained for supervisor
                # recovery; cancellation delivery is not treated as closure proof.
                record.alive = True

    def _require_live_setup(self, session: SessionRecord, deadline_ns: int) -> None:
        if (
            self.session_slot.current is not session
            or session.setup_cancelled
            or session.interrupted
            or self.clock() >= deadline_ns
        ):
            raise RuntimeError("Setup was fenced or expired before the next stage")


def _enabled_cameras(session: SessionRecord) -> set[int]:
    return session.required_cameras


def _running_roles(observation: object) -> tuple[int, ...]:
    if not isinstance(observation, mcu.MicrocontrollerObservation):
        return ()
    state = observation.state
    result = []
    for role, value in (
        (camera.CAMERA_ROLE_BEHAVIORAL, state.behavioral),
        (camera.CAMERA_ROLE_TRACKING, state.tracking),
    ):
        if value.HasField("enabled") and value.enabled:
            result.append(role)
    return tuple(result)


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
