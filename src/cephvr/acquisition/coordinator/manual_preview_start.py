"""The staged manual-preview start workflow (A03/A10)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.coordinator.configuration_resolution import (
    ConfigurationResolution,
)
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_preview_resources import (
    allocate_manual_preview_slot,
    allocate_manual_tracking_slot,
)
from cephvr.acquisition.coordinator.manual_preview_setup import (
    build_preview_payload,
    new_worker_preview,
)
from cephvr.acquisition.coordinator.manual_pulse_observation import (
    retain_applied_pulse_state,
)
from cephvr.acquisition.ports import ResourcePort, SerialOwnerPort
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    PausedPreview,
    PulseRecord,
    ResourceRecord,
    WorkerPreview,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.clock import host_time_ns


class PreviewPulseLifecycle(Protocol):
    async def pause_for_pulse_change(
        self, roles: tuple[int, ...], *, deadline_ns: int
    ) -> tuple[PausedPreview, ...]: ...

    async def resume_after_pulse_change(
        self, token: tuple[PausedPreview, ...], *, deadline_ns: int
    ) -> None: ...


class ManualPreviewStart:
    """Resolve, prepare, and start one preview using the retained command budget."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        configuration: ConfigurationRecord,
        pulse: PulseRecord,
        serial: SerialOwnerPort,
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        resource_port: ResourcePort,
        resolution: ConfigurationResolution,
        device_status: ManualDeviceStatusReporter,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.configuration = configuration
        self.pulse = pulse
        self.serial = serial
        self.resources = resources
        self.resource_ledger = resource_ledger
        self.resource_port = resource_port
        self.resolution = resolution
        self.device_status = device_status
        self.lock = lock
        self.clock = clock
        self.pulse_lifecycle: PreviewPulseLifecycle | None = None

    def bind_pulse_lifecycle(self, lifecycle: PreviewPulseLifecycle) -> None:
        """Bind the composed preview lifecycle used for cross-camera MCU edits."""
        if self.pulse_lifecycle is not None:
            raise RuntimeError("manual preview pulse lifecycle is already bound")
        self.pulse_lifecycle = lifecycle

    async def start(
        self,
        request: wire.AcquisitionCameraCommand,
        worker: WorkerRecord,
        setting: camera.CameraSessionSettings,
        policy: runtime.CameraFilePolicy,
        external_roles: tuple[int, ...],
        run_id: str,
        deadline_ns: int,
    ) -> None:
        pause_roles = tuple(role for role in external_roles if role != request.camera)
        paused: tuple[PausedPreview, ...] = ()
        if pause_roles:
            if self.pulse_lifecycle is None:
                raise RuntimeError(
                    "cross-camera external preview lifecycle is unavailable"
                )
            paused = await self.pulse_lifecycle.pause_for_pulse_change(
                pause_roles, deadline_ns=deadline_ns
            )
        try:
            resolved, revision = await self._resolve_camera_and_pulses(
                request, worker, setting, policy, external_roles, deadline_ns
            )
            if paused:
                assert self.pulse_lifecycle is not None
                await self.pulse_lifecycle.resume_after_pulse_change(
                    paused, deadline_ns=deadline_ns
                )
                paused = ()
            self.device_status.resolve_camera(
                int(request.camera),
                resolved,
                device_open=True,
                configuration_revision=revision,
            )
            preview = await self._prepare_preview_run(
                request,
                worker,
                setting,
                policy,
                resolved,
                run_id,
                revision,
                deadline_ns,
            )
            new_role = (
                (int(request.camera),) if request.camera in external_roles else ()
            )
            await self._start_prepared_preview(
                request, worker, preview, new_role, deadline_ns
            )
        except BaseException:
            if paused and self.pulse_lifecycle is not None:
                await self.pulse_lifecycle.resume_after_pulse_change(
                    paused, deadline_ns=deadline_ns
                )
            raise

    async def _resolve_camera_and_pulses(
        self,
        request: wire.AcquisitionCameraCommand,
        worker: WorkerRecord,
        setting: camera.CameraSessionSettings,
        policy: runtime.CameraFilePolicy,
        external_roles: tuple[int, ...],
        deadline_ns: int,
    ) -> tuple[camera.CameraResolvedState, int]:
        """Resolve exact SDK state and adopt its external-trigger MCU evidence."""
        command = request.command
        role = request.camera
        await self.resolution.begin(
            command,
            expected_cameras={role},
            request_revision=request.configuration_revision,
            deadline_ns=deadline_ns,
            expected_pulses=bool(external_roles),
            requested_pulses=(
                self.configuration.settings.pulses if external_roles else None
            ),
        )
        resolve_command, resolve_child, resolve_port = retain_worker_command(
            worker,
            work=None,
            parent_operation=control.OperationContext(command_id=command.command_id),
            kind="resolve_camera",
            deadline_ns=deadline_ns,
            configuration_revision=request.configuration_revision,
            requested_device_id=setting.device.device_id,
        )
        resolve = acq.WorkerResolveCamera(
            command=resolve_command,
            requested=setting.device,
            transport=policy.transport,
            configuration_revision=request.configuration_revision,
        )
        self.device_status.begin_device_access(int(role), setting.device.device_id)
        receipt = await resolve_port.resolve_camera_configuration(
            resolve, deadline_ns=deadline_ns
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(
                f"{receipt.failure.code}: {receipt.failure.message}"
                if receipt.HasField("failure")
                else "camera resolution was not admitted"
            )
        state = await wait_child_operation(
            resolve_child, deadline_ns, self.lock, self.clock
        )
        resolved = resolve_child.resolved_camera
        if not state.succeeded:
            raise RuntimeError(
                state.failure.message
                if state.failure.message
                else "camera resolution failed"
            )
        if resolved is None:
            raise RuntimeError("camera resolution lacks successful SDK evidence")
        if external_roles:
            if self.pulse.observation is None:
                await self.serial.connect(deadline_ns=deadline_ns)
            observation = await self.serial.configure(
                self.configuration.settings.pulses,
                active_roles=external_roles,
                deadline_ns=deadline_ns,
            )
            self.pulse.observation = mcu.MicrocontrollerObservation.FromString(
                observation.SerializeToString(deterministic=True)
            )
            pulse_resolution = mcu.PulseConfigurationResolution(
                requested_configuration_revision=request.configuration_revision,
                requested=self.configuration.settings.pulses,
                behavioral_active=(camera.CAMERA_ROLE_BEHAVIORAL in external_roles),
                tracking_active=(camera.CAMERA_ROLE_TRACKING in external_roles),
                applied=observation,
            )
            pulse_receipt = await self.resolution.set_pulse_resolution(
                control.OperationContext(command_id=command.command_id),
                pulse_resolution,
            )
            if pulse_receipt.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    pulse_receipt.failure.message or "pulse/camera readback rejected"
                )
        await self.resolution.wait_confirmed(
            control.OperationContext(command_id=command.command_id),
            deadline_ns=deadline_ns,
        )
        await self.resolution.retire(
            control.OperationContext(command_id=command.command_id)
        )
        return resolved, self.configuration.revision

    async def _prepare_preview_run(
        self,
        request: wire.AcquisitionCameraCommand,
        worker: WorkerRecord,
        setting: camera.CameraSessionSettings,
        policy: runtime.CameraFilePolicy,
        resolved: camera.CameraResolvedState,
        run_id: str,
        configuration_revision: int,
        deadline_ns: int,
    ) -> WorkerPreview:
        """Reserve the exact frame ring, retain preview state, and await Ready."""
        attachment, _resource = await allocate_manual_preview_slot(
            worker=worker,
            resolved=resolved,
            controller=self.identity.controller,
            run_id=run_id,
            configuration_revision=configuration_revision,
            resources=self.resources,
            ledger=self.resource_ledger,
            resource_port=self.resource_port,
        )
        tracking_attachment = None
        tracking_worker_attachment = None
        if request.camera == camera.CAMERA_ROLE_TRACKING:
            capacity = self.configuration.settings.tracking_ring_frames
            if capacity <= 0:
                raise ValueError("tracking ring capacity must be positive")
            (
                tracking_worker_attachment,
                tracking_attachment,
            ) = await allocate_manual_tracking_slot(
                worker=worker,
                resolved=resolved,
                controller=self.identity.controller,
                tracking_consumer=self.identity.tracking,
                run_id=run_id,
                configuration_revision=configuration_revision,
                capacity_frames=capacity,
                resources=self.resources,
                ledger=self.resource_ledger,
                resource_port=self.resource_port,
            )
        preview = new_worker_preview(
            run_id,
            configuration_revision,
            attachment,
            resolved,
            request.preview_output_bit_depth,
            tracking_attachment=tracking_attachment,
            tracking_worker_attachment=tracking_worker_attachment,
        )
        worker.preview = preview
        command = request.command
        prep_command, prep_child, prep_port = retain_worker_command(
            worker,
            work=None,
            parent_operation=control.OperationContext(command_id=command.command_id),
            kind="prepare_preview",
            deadline_ns=deadline_ns,
            configuration_revision=configuration_revision,
            requested_device_id=setting.device.device_id,
        )
        preview.preparation = control.OperationContext(command_id=prep_child.command_id)
        payload = build_preview_payload(
            setting,
            policy,
            resolved,
            attachment,
            tracking_attachment=tracking_worker_attachment,
        )
        prepare = acq.WorkerPreparePreview(
            command=prep_command,
            configuration_revision=configuration_revision,
            preview_run_id=run_id,
            camera=payload,
        )
        receipt = await prep_port.prepare_preview(prepare, deadline_ns=deadline_ns)
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("manual preview preparation was rejected")
        state = await wait_child_operation(
            prep_child, deadline_ns, self.lock, self.clock
        )
        if not state.succeeded:
            raise RuntimeError(
                state.failure.message or "manual preview preparation failed"
            )
        self.device_status.update_camera_state(
            int(request.camera),
            device_open=True,
            preview_prepared=True,
            preview_running=False,
            preview_run_id=run_id,
        )
        return preview

    async def _start_prepared_preview(
        self,
        request: wire.AcquisitionCameraCommand,
        worker: WorkerRecord,
        preview: WorkerPreview,
        external_roles: tuple[int, ...],
        deadline_ns: int,
    ) -> None:
        """Start the Ready run, apply pulse ON, then require first-frame evidence."""
        command = request.command
        start_command, start_child, start_port = retain_worker_command(
            worker,
            work=None,
            parent_operation=control.OperationContext(command_id=command.command_id),
            kind="start_preview",
            deadline_ns=deadline_ns,
            configuration_revision=preview.configuration_revision,
        )
        preview.start_operation = control.OperationContext(
            command_id=start_child.command_id
        )
        start = acq.WorkerStartPreview(
            command=start_command,
            preparation=preview.preparation,
            configuration_revision=preview.configuration_revision,
            preview_run_id=preview.run_id,
        )
        receipt = await start_port.start_preview(start, deadline_ns=deadline_ns)
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("manual preview start was rejected")
        state = await wait_child_operation(
            start_child, deadline_ns, self.lock, self.clock
        )
        if not state.succeeded:
            raise RuntimeError(state.failure.message or "manual preview start failed")
        if external_roles:
            evidence = await self.serial.on(
                external_roles,
                scheduled_boundary_ns=None,
                deadline_ns=deadline_ns,
            )
            retain_applied_pulse_state(self.pulse, evidence, deadline_ns=deadline_ns)
        await _wait_event(preview.started_event, deadline_ns, self.clock)
        if not preview.started:
            raise RuntimeError("manual preview has no retained first usable frame")
        if preview.resolved_camera is None:
            raise RuntimeError("manual preview has no retained resolved device state")
        self.device_status.resolve_camera(
            int(request.camera),
            preview.resolved_camera,
            device_open=True,
            preview_prepared=True,
            preview_running=True,
            preview_run_id=preview.run_id,
            configuration_revision=preview.configuration_revision,
        )


async def _wait_event(
    event: asyncio.Event, deadline_ns: int, clock: Callable[[], int]
) -> None:
    remaining = max(0, deadline_ns - clock()) / 1_000_000_000
    if remaining <= 0:
        raise TimeoutError("preview first-frame evidence missed its retained deadline")
    await asyncio.wait_for(event.wait(), remaining)
