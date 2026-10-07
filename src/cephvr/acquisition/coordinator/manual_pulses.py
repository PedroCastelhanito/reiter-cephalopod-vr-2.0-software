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

    async def execute_diagnostic(
        self, request: wire.AcquisitionMicrocontrollerCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        command = request.command
        if (
            self.clock() >= deadline_ns
            or not command.command_id
            or command.issuer != self.identity.controller
            or command.target != self.identity.backend
            or not command.HasField("parent_operation")
            or not command.parent_operation.command_id
            or command.work.WhichOneof("work") is not None
            or not request.HasField("configuration_revision")
            or request.configuration_revision < self.configuration.revision
            or not manual_configuration_available(self.session_slot)
            or not request.requested.HasField("port")
            or request.requested.port != self.configuration.settings.pulses.port
            or any(
                worker.preview and worker.preview.started
                for worker in self.workers.values()
            )
            or request.kind
            not in {
                wire.MICROCONTROLLER_COMMAND_KIND_CONNECT,
                wire.MICROCONTROLLER_COMMAND_KIND_START,
                wire.MICROCONTROLLER_COMMAND_KIND_STATUS,
                wire.MICROCONTROLLER_COMMAND_KIND_STOP,
            }
        ):
            return _rejected(
                command.command_id,
                "MCU_UNAVAILABLE",
                "MCU diagnostic is stale or unavailable",
            )
        if request.kind == wire.MICROCONTROLLER_COMMAND_KIND_START:
            selection = _selected_diagnostic(request.signal, request.requested)
            if selection is None:
                return _rejected(
                    command.command_id,
                    "MCU_PIN",
                    "signal has no enabled pin assignment",
                )
        elif request.signal != control.MICROCONTROLLER_SIGNAL_KIND_UNSPECIFIED:
            return _rejected(
                command.command_id, "MCU_SIGNAL", "only Start selects a signal"
            )
        try:
            self.device_status.reserve(command)
            await retire_completed_manual_session(
                self.session_slot, self.worker_registry, deadline_ns=deadline_ns
            )
            if (
                request.kind == wire.MICROCONTROLLER_COMMAND_KIND_CONNECT
                or self.pulse.observation is None
                or self.pulse.observation.port != request.requested.port
            ):
                self.pulse.observation = await self.serial.connect(
                    deadline_ns=deadline_ns
                )
            if request.kind == wire.MICROCONTROLLER_COMMAND_KIND_CONNECT:
                self.device_status.clear_diagnostic()
            elif request.kind == wire.MICROCONTROLLER_COMMAND_KIND_START:
                assert selection is not None
                kind, pin, frequency = selection
                if frequency is not None:
                    self.pulse.observation = await self.serial.configure(
                        request.requested,
                        active_roles=(kind,),
                        deadline_ns=deadline_ns,
                    )
                active, _, _, edges = await self.serial.diagnostic_start(
                    kind, pin, frequency_hz=frequency, deadline_ns=deadline_ns
                )
                self.device_status.set_diagnostic(request.signal, pin, active, edges)
            else:
                active, kind, pin, edges = (
                    await self.serial.diagnostic_status(deadline_ns=deadline_ns)
                    if request.kind == wire.MICROCONTROLLER_COMMAND_KIND_STATUS
                    else await self.serial.diagnostic_stop(deadline_ns=deadline_ns)
                )
                signal = _signal_for_kind(kind)
                self.device_status.set_diagnostic(signal, pin, active, edges)
            receipt = await self.device_status.report(
                command,
                command_name="execute_microcontroller_command",
                succeeded=True,
                deadline_ns=deadline_ns,
            )
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                return _rejected(
                    command.command_id, "MCU_STATUS", "controller rejected MCU status"
                )
            self.device_status.finalize_command(command.command_id)
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=command.command_id,
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            try:
                await self.results.report_failure(
                    command,
                    command_name="execute_microcontroller_command",
                    deadline_ns=deadline_ns,
                    failure=str(exc),
                )
            except (RuntimeError, TimeoutError, ValueError):
                pass
            return _rejected(command.command_id, "MCU_COMMAND_FAILED", str(exc))

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


def _selected_diagnostic(
    signal: int, requested: camera.CameraPulseConfiguration
) -> tuple[str, str, float | None] | None:
    fixed = {
        int(control.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE): "trial_state",
        int(control.MICROCONTROLLER_SIGNAL_KIND_PROJECTOR_FLIP): "projector_flip",
    }
    if signal in fixed:
        kind = fixed[signal]
        if not getattr(requested, f"{kind}_enabled") or not requested.HasField(
            f"{kind}_pin"
        ):
            return None
        return kind, getattr(requested, f"{kind}_pin"), None
    role = {
        int(control.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL): "behavioral",
        int(control.MICROCONTROLLER_SIGNAL_KIND_TRACKING): "tracking",
    }.get(signal)
    if role is None:
        return None
    pulse = getattr(requested, role)
    if not pulse.HasField("pin") or not pulse.HasField("requested_frequency_hz"):
        return None
    return role, pulse.pin, pulse.requested_frequency_hz


def _signal_for_kind(kind: str) -> int:
    return {
        "trial_state": control.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE,
        "projector_flip": control.MICROCONTROLLER_SIGNAL_KIND_PROJECTOR_FLIP,
        "behavioral": control.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL,
        "tracking": control.MICROCONTROLLER_SIGNAL_KIND_TRACKING,
    }[kind]


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
