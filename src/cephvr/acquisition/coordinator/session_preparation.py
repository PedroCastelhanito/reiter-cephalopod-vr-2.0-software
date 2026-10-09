"""Setup's pulse, camera-resolution, and worker preparation workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import cast

from cephvr.acquisition.coordinator.commands import retain_worker_command
from cephvr.acquisition.coordinator.manual_pulse_observation import (
    clear_observation,
    invalidate_released_idle_proof,
    retain_applied_pulse_state,
    retain_observation,
)
from cephvr.acquisition.coordinator.session_catalogue import SessionCatalogue
from cephvr.acquisition.coordinator.session_payloads import (
    camera_policy,
    prepare_worker_payloads,
    role_name,
)
from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.ports import ControllerPort, ResourcePort, SerialOwnerPort
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
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.clock import host_time_ns


class SessionPreparation:
    """Run exact setup preparation stages with explicit state/ports."""

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
        catalogue: SessionCatalogue,
        session_config_reference: Callable[[wire.SetupSessionRequest], str],
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
        self.catalogue = catalogue
        self.session_config_reference = session_config_reference
        self.clock = clock

    async def configure_pulses(
        self, request: wire.SetupSessionRequest, deadline_ns: int
    ) -> None:
        settings = request.settings.acquisition
        active_roles = tuple(
            role
            for role, item in (
                (camera.CAMERA_ROLE_BEHAVIORAL, settings.behavioral),
                (camera.CAMERA_ROLE_TRACKING, settings.tracking),
            )
            if item.HasField("enabled")
            and item.enabled
            and item.device.HasField("frame_timing")
            and item.device.frame_timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
        )
        if not active_roles:
            return
        if not settings.pulses.HasField("port") or not settings.pulses.port:
            raise ValueError("external-trigger cameras require a configured MCU port")
        session = self.session_slot.current
        if session is None:
            raise RuntimeError("pulse Setup has no current session")
        await self.catalogue.declare_resource(
            session,
            self.identity.process,
            f"microcontroller-claim:{settings.pulses.port}",
            deadline_ns=deadline_ns,
        )
        invalidate_released_idle_proof(self.pulse)
        observation = await self.serial.connect(deadline_ns=deadline_ns)
        retain_observation(self.pulse, observation)
        invalidate_released_idle_proof(self.pulse)
        configured = await self.serial.configure(
            settings.pulses,
            active_roles=active_roles,
            deadline_ns=deadline_ns,
        )
        retain_observation(self.pulse, configured)
        applied = mcu.MicrocontrollerObservation()
        applied.CopyFrom(configured)
        resolution = mcu.PulseConfigurationResolution(
            requested_configuration_revision=request.plan.configuration_revision,
            requested=settings.pulses,
            behavioral_active=camera.CAMERA_ROLE_BEHAVIORAL in active_roles,
            tracking_active=camera.CAMERA_ROLE_TRACKING in active_roles,
            applied=applied,
        )
        if self.session_slot.current is not None:
            self.session_slot.current.pulse_resolution = resolution

    async def retire_manual_workers(self, deadline_ns: int) -> None:
        """Stop any manual preview before serial Configure or session Setup."""
        manual_roles = tuple(
            cast(camera.CameraRole, role)
            for role, record in tuple(self.workers.workers.items())
            if record.context.work.WhichOneof("work") is None
        )
        if not manual_roles and self.pulse.observation is None:
            return
        if self.pulse.observation is not None:
            selected = _running_roles(self.pulse.observation)
            if selected:
                evidence = await self.serial.off(
                    selected,
                    scheduled_boundary_ns=None,
                    stop_issued_ns=self.clock(),
                    deadline_ns=deadline_ns,
                )
                if evidence.outcome != mcu.PULSE_COMMAND_OUTCOME_APPLIED:
                    raise RuntimeError(
                        "manual MCU outputs lack exact OFF acknowledgement"
                    )
                retain_applied_pulse_state(
                    self.pulse, evidence, deadline_ns=deadline_ns
                )
        for role in manual_roles:
            await self.workers.retire_sessionless_worker(role, deadline_ns=deadline_ns)
        # A manual preview may have opened the owner even when its last readback
        # showed no enabled outputs. Close it before session catalogue ownership
        # begins so a free-run Setup cannot leave an uncatalogued serial port.
        if self.pulse.observation is not None:
            invalidate_released_idle_proof(self.pulse)
            await self.serial.close(deadline_ns=deadline_ns)
            clear_observation(self.pulse)

    async def launch_workers(
        self,
        session: SessionRecord,
        request: wire.SetupSessionRequest,
        deadline_ns: int,
    ) -> tuple[WorkerRecord, ...]:
        self._require_live(session, deadline_ns)
        launch_tasks = [
            self.workers.launch(
                cast(camera.CameraRole, role),
                session.work,
                session.operation,
                deadline_ns=deadline_ns,
                policies=request.plan.policies,
                file_policy=camera_policy(
                    request.acquisition_policies,
                    cast(camera.CameraRole, role),
                ),
            )
            for role in sorted(session.required_cameras)
        ]
        outcomes = await asyncio.gather(*launch_tasks, return_exceptions=True)
        failures = [item for item in outcomes if isinstance(item, BaseException)]
        if failures:
            cancellation = next(
                (item for item in failures if isinstance(item, asyncio.CancelledError)),
                None,
            )
            if cancellation is not None:
                raise cancellation
            raise RuntimeError(
                "one or more camera worker launches failed: "
                + "; ".join(str(item) for item in failures)
            )
        self._require_live(session, deadline_ns)
        return tuple(cast(WorkerRecord, item) for item in outcomes)

    async def resolve_cameras(
        self,
        session: SessionRecord,
        request: wire.SetupSessionRequest,
        records: tuple[WorkerRecord, ...],
        deadline_ns: int,
    ) -> None:
        self._require_live(session, deadline_ns)
        applications = {
            cast(camera.CameraRole, role): getattr(
                request.settings.acquisition, role_name(role)
            )
            for role in session.required_cameras
        }
        by_role = {record.context.camera: record for record in records}
        if set(by_role) != session.required_cameras:
            raise RuntimeError("registered camera worker set differs from Setup roles")
        for role in sorted(session.required_cameras):
            self._require_live(session, deadline_ns)
            worker = by_role[cast(camera.CameraRole, role)]
            await self.catalogue.declare_resource(
                session,
                worker.launch.worker,
                f"camera-device:{worker.launch.worker.generation}",
                deadline_ns=deadline_ns,
            )
        dispatch = []
        for role in sorted(session.required_cameras):
            role_enum = cast(camera.CameraRole, role)
            settings = applications[role_enum]
            if not settings.HasField("device") or not settings.device.device_id:
                raise ValueError(f"camera role {role} has no assigned device ID")
            policy = camera_policy(request.acquisition_policies, role_enum)
            child, _operation, port = retain_worker_command(
                by_role[role_enum],
                work=session.work,
                parent_operation=session.operation,
                kind="resolve_camera",
                deadline_ns=deadline_ns,
                configuration_revision=session.configuration_revision,
                requested_device_id=settings.device.device_id,
            )
            resolve = acq.WorkerResolveCamera(
                command=child,
                requested=settings.device,
                configuration_revision=session.configuration_revision,
            )
            resolve.transport.CopyFrom(policy.transport)
            dispatch.append((port, resolve))
        calls = [
            port.resolve_camera_configuration(resolve, deadline_ns=deadline_ns)
            for port, resolve in dispatch
        ]
        outcomes = await asyncio.gather(*calls, return_exceptions=True)
        self._require_live(session, deadline_ns)
        failures = [item for item in outcomes if isinstance(item, BaseException)]
        if failures:
            raise RuntimeError(
                "one or more camera resolution calls failed: "
                + "; ".join(str(item) for item in failures)
            )
        receipts = tuple(cast(control.CommandAdmission, item) for item in outcomes)
        rejected = [
            item for item in receipts if item.result != control.COMMAND_RESULT_ACCEPTED
        ]
        if rejected:
            raise RuntimeError(
                "one or more acquisition camera resolutions were rejected"
            )

    async def prepare_workers(
        self,
        session: SessionRecord,
        request: wire.SetupSessionRequest,
        records: tuple[WorkerRecord, ...],
        deadline_ns: int,
    ) -> None:
        self._require_live(session, deadline_ns)
        await prepare_worker_payloads(
            session,
            request,
            records,
            deadline_ns,
            identity=self.identity,
            configuration=self.configuration,
            resources=self.resources,
            resource_ledger=self.resource_ledger,
            resource_port=self.resource_port,
            controller=self.controller,
            session_config_reference=self.session_config_reference,
            clock=self.clock,
            is_live=lambda: (
                self.session_slot.current is session
                and not session.setup_cancelled
                and not session.interrupted
            ),
            declare_resource=lambda owner, resource: self.catalogue.declare_resource(
                session, owner, resource, deadline_ns=deadline_ns
            ),
        )

    def _require_live(self, session: SessionRecord, deadline_ns: int) -> None:
        if (
            self.session_slot.current is not session
            or session.setup_cancelled
            or session.interrupted
            or self.clock() >= deadline_ns
        ):
            raise RuntimeError("Setup was fenced or expired before its next effect")


def _running_roles(observation: object) -> tuple[int, ...]:
    if not isinstance(observation, mcu.MicrocontrollerObservation):
        return ()
    state = observation.state
    return tuple(
        role
        for role, output in (
            (camera.CAMERA_ROLE_BEHAVIORAL, state.behavioral),
            (camera.CAMERA_ROLE_TRACKING, state.tracking),
        )
        if output.HasField("enabled") and output.enabled
    )
