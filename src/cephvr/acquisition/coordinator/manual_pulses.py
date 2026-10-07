"""Sessionless pulse-setting adoption for manual preview outputs (A10/A11)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from cephvr.acquisition.coordinator.configuration_resolution import (
    ConfigurationResolution,
)
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_operation_results import (
    ManualOperationResults,
)
from cephvr.acquisition.coordinator.manual_pulse_observation import release_idle_claim
from cephvr.acquisition.coordinator.manual_session_access import (
    manual_configuration_available,
    retire_completed_manual_session,
)
from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.ports import ControllerPort, SerialOwnerPort
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    PausedPreview,
    PulseRecord,
    SessionSlot,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class PreviewPulseControl(Protocol):
    """Stop/recreate affected preview runs around shared MCU reconfiguration."""

    async def pause_for_pulse_change(
        self, roles: tuple[int, ...], *, deadline_ns: int
    ) -> tuple[PausedPreview, ...]: ...

    async def resume_after_pulse_change(
        self, token: tuple[PausedPreview, ...], *, deadline_ns: int
    ) -> None: ...


class ManualPulses:
    """Configure the MCU using the complete live external-preview mask.

    No timer or raw serial operation is exposed. Requested settings stay distinct
    from the firmware observation and are adopted only through ConfigurationResolution.
    """

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        configuration: ConfigurationRecord,
        session_slot: SessionSlot,
        pulse: PulseRecord,
        workers: WorkerRegistry,
        serial: SerialOwnerPort,
        controller: ControllerPort,
        resolution: ConfigurationResolution,
        device_status: ManualDeviceStatusReporter,
        preview: PreviewPulseControl,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.configuration = configuration
        self.session_slot = session_slot
        self.pulse = pulse
        self.worker_registry = workers
        self.workers = workers.workers
        self.serial = serial
        self.results = ManualOperationResults(
            identity=identity, controller=controller, device_status=device_status
        )
        self.resolution = resolution
        self.device_status = device_status
        self.preview = preview
        self.lock = lock
        self.clock = clock

    async def apply(
        self,
        request: wire.AcquisitionPulseCommand,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        command = request.command
        if (
            self.clock() >= deadline_ns
            or not command.command_id
            or command.issuer != self.identity.controller
            or command.target != self.identity.backend
            or command.work.WhichOneof("work") is not None
            or not command.HasField("parent_operation")
            or not command.parent_operation.command_id
            or not request.HasField("configuration_revision")
            or request.configuration_revision != self.configuration.revision
            or request.file_policies != self.configuration.file_policies
            or not request.HasField("application")
            or not request.application.HasField("requested")
            or not manual_configuration_available(self.session_slot)
        ):
            return _rejected(
                command.command_id,
                "STALE_PULSE_EDIT",
                "pulse edit is stale or malformed",
            )
        try:
            self.device_status.reserve(command)
        except (RuntimeError, ValueError) as exc:
            return _rejected(command.command_id, "DEVICE_STATUS_CAPACITY", str(exc))
        try:
            await retire_completed_manual_session(
                self.session_slot, self.worker_registry, deadline_ns=deadline_ns
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            return _rejected(command.command_id, "SESSION_RETIREMENT", str(exc))
        active_roles = _active_external_previews(
            self.workers, self.configuration.settings
        )
        if (
            request.application.HasField("behavioral_active")
            and request.application.behavioral_active
            != (camera.CAMERA_ROLE_BEHAVIORAL in active_roles)
        ) or (
            request.application.HasField("tracking_active")
            and request.application.tracking_active
            != (camera.CAMERA_ROLE_TRACKING in active_roles)
        ):
            return _rejected(
                command.command_id,
                "PULSE_ACTIVE_MASK",
                "requested MCU active mask differs from running external previews",
            )

        preview_token: tuple[PausedPreview, ...] | None = None
        operation = control.OperationContext(command_id=command.command_id)
        try:
            await self.resolution.begin(
                command,
                expected_cameras=set(),
                request_revision=request.configuration_revision,
                deadline_ns=deadline_ns,
                expected_pulses=True,
                requested_pulses=request.application.requested,
            )
            if active_roles:
                preview_token = await self.preview.pause_for_pulse_change(
                    active_roles, deadline_ns=deadline_ns
                )
            if self.pulse.observation is None:
                await self.serial.connect(deadline_ns=deadline_ns)
            observation = await self.serial.configure(
                request.application.requested,
                active_roles=tuple(active_roles),
                deadline_ns=deadline_ns,
            )
            pulse_resolution = mcu.PulseConfigurationResolution(
                requested_configuration_revision=request.configuration_revision,
                requested=request.application.requested,
                behavioral_active=(camera.CAMERA_ROLE_BEHAVIORAL in active_roles),
                tracking_active=(camera.CAMERA_ROLE_TRACKING in active_roles),
                applied=observation,
            )
            receipt = await self.resolution.set_pulse_resolution(
                operation, pulse_resolution
            )
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError("controller did not accept MCU readback")
            await self.resolution.wait_confirmed(operation, deadline_ns=deadline_ns)
            await self.resolution.retire(operation)
            self.pulse.observation = mcu.MicrocontrollerObservation.FromString(
                observation.SerializeToString(deterministic=True)
            )
            if preview_token is not None:
                await self.preview.resume_after_pulse_change(
                    preview_token, deadline_ns=deadline_ns
                )
            if not active_roles:
                await release_idle_claim(
                    self.pulse, self.serial, deadline_ns=deadline_ns
                )
            self._project_live_previews()
            return await self.results.complete(
                command,
                command_name="apply_pulse_configuration",
                deadline_ns=deadline_ns,
                status_code="PULSE_STATUS",
                status_failure="controller rejected device status",
                parent_code="PULSE_REPORT",
                parent_failure="controller rejected pulse completion",
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            try:
                self._project_live_previews()
                await self.results.report_failure(
                    command,
                    command_name="apply_pulse_configuration",
                    deadline_ns=deadline_ns,
                    failure=str(exc),
                )
            except (RuntimeError, TimeoutError, ValueError):
                pass
            try:
                await self.resolution.cancel(operation)
                await self.resolution.retire(operation)
            except (RuntimeError, ValueError):
                pass
            return _rejected(command.command_id, "PULSE_EDIT_FAILED", str(exc))

    def _project_live_previews(self) -> None:
        for role, worker in self.workers.items():
            preview = worker.preview
            if preview is None or preview.resolved_camera is None:
                continue
            self.device_status.resolve_camera(
                role,
                preview.resolved_camera,
                device_open=True,
                preview_prepared=preview.preparation is not None,
                preview_running=preview.started,
                preview_run_id=preview.run_id,
                cleanup_pending=preview.stopping,
                configuration_revision=preview.configuration_revision,
            )


def _active_external_previews(
    workers: dict[int, WorkerRecord], settings: control.AcquisitionSettings
) -> tuple[int, ...]:
    selected = []
    for role, setting in (
        (camera.CAMERA_ROLE_BEHAVIORAL, settings.behavioral),
        (camera.CAMERA_ROLE_TRACKING, settings.tracking),
    ):
        worker = workers.get(role)
        if (
            worker is not None
            and worker.preview is not None
            and worker.preview.started
            and setting.HasField("device")
            and setting.device.frame_timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
        ):
            selected.append(role)
    return tuple(selected)


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        command_id=command_id,
        result=control.COMMAND_RESULT_REJECTED,
        failure=control.Failure(code=code, message=message),
    )
