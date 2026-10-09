"""Sessionless connected-camera edits and PFS operations (A10/E07)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.coordinator.configuration_resolution import (
    ConfigurationResolution,
)
from cephvr.acquisition.coordinator.manual_device_commands import ManualDeviceCommands
from cephvr.acquisition.coordinator.manual_device_recovery import ManualDeviceRecovery
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_operation_results import (
    ManualOperationResults,
)
from cephvr.acquisition.coordinator.manual_pulse_observation import (
    clear_observation,
    invalidate_released_idle_proof,
    retain_applied_pulse_state,
    retain_observation,
)
from cephvr.acquisition.coordinator.manual_pulses import (
    PreviewPulseControl,
    _active_external_previews,
)
from cephvr.acquisition.coordinator.manual_session_access import (
    manual_command_valid,
    retire_completed_manual_session,
)
from cephvr.acquisition.coordinator.session_payloads import camera_policy, role_name
from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.ports import ControllerPort, WorkerPort
from cephvr.acquisition.state import (
    ChildOperation,
    ConfigurationRecord,
    CoordinatorIdentity,
    PausedPreview,
    PulseRecord,
    SessionSlot,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.microcontroller import SerialOwnerPort


class ManualDevices:
    """Apply validated edits only to already-owned sessionless camera workers.

    The controller owns validation and command admission. This component owns the
    worker SDK operation, exact readback report, and wait for controller adoption.
    Offline roles are deliberately not opened by an ordinary settings edit.
    """

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        configuration: ConfigurationRecord,
        session_slot: SessionSlot,
        workers: WorkerRegistry,
        controller: ControllerPort,
        resolution: ConfigurationResolution,
        device_status: ManualDeviceStatusReporter,
        pulse: PulseRecord,
        serial: SerialOwnerPort,
        preview: PreviewPulseControl,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.configuration = configuration
        self.session_slot = session_slot
        self.workers = workers
        self.results = ManualOperationResults(
            identity=identity, controller=controller, device_status=device_status
        )
        self.resolution = resolution
        self.device_status = device_status
        self.pulse = pulse
        self.serial = serial
        self.preview = preview
        self.lock = lock
        self.clock = clock
        self.recovery = ManualDeviceRecovery(
            workers=workers,
            resolution=resolution,
            pulse=pulse,
            serial=serial,
            clock=clock,
        )
        self.commands = ManualDeviceCommands(
            identity=identity,
            configuration=configuration,
            session_slot=session_slot,
            workers=workers,
            resolution=resolution,
            device_status=device_status,
            results=self.results,
            lock=lock,
            clock=clock,
        )

    def bind_retained_operation_reconciler(
        self,
        reconcile: Callable[
            [WorkerRecord, ChildOperation, acq.WorkerRetainedResult, int, int],
            Awaitable[bool],
        ],
    ) -> None:
        """Bind the evidence owner used by fresh-caller recovery."""
        self.recovery.bind_retained_operation_reconciler(reconcile)

    async def apply(
        self,
        request: wire.AcquisitionCameraSettingsCommand,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        command = request.command
        if not request.HasField("configuration_revision"):
            return _rejected(
                command.command_id,
                "CAMERA_EDIT_REVISION",
                "camera edit lacks an explicit configuration revision",
            )
        if not request.HasField("accepted_base_revision") or not request.HasField(
            "accepted_base_settings"
        ):
            return _rejected(
                command.command_id,
                "CAMERA_EDIT_BASE",
                "camera edit lacks the accepted controller configuration base",
            )
        if not manual_command_valid(
            command,
            revision=request.configuration_revision,
            expected_revision=request.accepted_base_revision,
            identity=self.identity,
            session_slot=self.session_slot,
            now_ns=self.clock(),
            deadline_ns=deadline_ns,
        ):
            return _rejected(
                command.command_id, "STALE_CAMERA_EDIT", "camera edit is stale"
            )
        # An empty batch is the exact readback barrier for unrelated edits to a
        # full controller draft. It still requires a live, revision-bound manual
        # command and is confirmed by the controller before this command succeeds.
        roles = [item.camera for item in request.cameras]
        if len(set(roles)) != len(roles) or any(
            role
            not in (
                camera.CAMERA_ROLE_BEHAVIORAL,
                camera.CAMERA_ROLE_TRACKING,
                camera.CAMERA_ROLE_EYE_TRACKING,
            )
            for role in roles
        ):
            return _rejected(
                command.command_id,
                "CAMERA_EDIT_ROLES",
                "camera roles are invalid or duplicated",
            )
        revision = request.configuration_revision
        assert revision is not None
        if request.file_policies != self.configuration.file_policies:
            return _rejected(
                command.command_id,
                "CAMERA_EDIT_POLICY",
                "camera edit policy differs from the loaded controller policy",
            )
        try:
            self.device_status.reserve(command)
        except (RuntimeError, ValueError) as exc:
            return _rejected(command.command_id, "DEVICE_STATUS_CAPACITY", str(exc))
        try:
            await retire_completed_manual_session(
                self.session_slot, self.workers, deadline_ns=deadline_ns
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            return _rejected(command.command_id, "SESSION_RETIREMENT", str(exc))
        try:
            await self.recovery.retry_pending_claim_release(deadline_ns)
            await self.recovery.recover_failed_device_work(deadline_ns)
            await self.resolution.retire_failed_if_quiescent()
            if request.HasField("pulses") and not request.pulses.HasField("requested"):
                raise ValueError("pulse edit lacks a complete requested configuration")
            revision = request.configuration_revision
            assert revision is not None
            expected_pulses = request.HasField("pulses")
            requested_pulses = request.pulses.requested if expected_pulses else None
            active_roles = _active_external_previews(
                self.workers.workers, self.configuration.settings
            )
            requested_active_roles = _requested_external_previews(
                request, self.configuration.settings, active_roles
            )
            preview_roles = tuple(
                role
                for role, worker in self.workers.workers.items()
                if worker.preview is not None and worker.preview.started
            )
            pause_roles: set[int] = {
                int(role) for role in roles if int(role) in preview_roles
            }
            if expected_pulses:
                pause_roles.update(int(role) for role in active_roles)
            required_preview_runs: dict[int, str] = {}
            for role in pause_roles:
                worker = self.workers.workers.get(role)
                if worker is not None and worker.preview is not None:
                    required_preview_runs[role] = worker.preview.run_id
            required_pulse_roles: set[int] = (
                {
                    int(camera.CAMERA_ROLE_BEHAVIORAL),
                    int(camera.CAMERA_ROLE_TRACKING),
                }
                if expected_pulses
                else set(active_roles).union(requested_active_roles)
            )
            if expected_pulses and (
                request.pulses.behavioral_active
                != (camera.CAMERA_ROLE_BEHAVIORAL in requested_active_roles)
                or request.pulses.tracking_active
                != (camera.CAMERA_ROLE_TRACKING in requested_active_roles)
            ):
                raise ValueError(
                    "pulse active mask differs from running external previews"
                )
            await self.resolution.begin(
                command,
                expected_cameras=set(roles),
                request_revision=revision,
                deadline_ns=deadline_ns,
                expected_pulses=expected_pulses,
                requested_pulses=requested_pulses,
                allow_empty=not roles and not expected_pulses,
                accepted_base_revision=request.accepted_base_revision,
                accepted_base_settings=request.accepted_base_settings,
                device_work_quiescent=lambda: self.recovery.device_work_quiescent(
                    parent_command_id=command.command_id,
                    required_preview_runs=required_preview_runs,
                    required_pulse_roles=required_pulse_roles,
                ),
                preexisting_work_quiescent=self.recovery.prior_device_work_quiescent,
            )
            payloads = self._build_apply_payloads(request, deadline_ns)
            preview_token: tuple[PausedPreview, ...] = ()
            if pause_roles:
                preview_token = await self.preview.pause_for_pulse_change(
                    tuple(sorted(pause_roles)),
                    deadline_ns=deadline_ns,
                    parent_operation=control.OperationContext(
                        command_id=command.command_id
                    ),
                )
            quiesced_roles = tuple(
                sorted(set(active_roles).intersection(int(role) for role in roles))
            )
            if quiesced_roles:
                if self.pulse.observation is None:
                    invalidate_released_idle_proof(self.pulse)
                    retain_observation(
                        self.pulse,
                        await self.serial.connect(deadline_ns=deadline_ns),
                    )
                try:
                    invalidate_released_idle_proof(self.pulse)
                    evidence = await self.serial.off(
                        quiesced_roles,
                        scheduled_boundary_ns=None,
                        stop_issued_ns=None,
                        deadline_ns=deadline_ns,
                    )
                    retain_applied_pulse_state(
                        self.pulse, evidence, deadline_ns=deadline_ns
                    )
                except Exception:
                    try:
                        retain_observation(
                            self.pulse,
                            await self.serial.status(deadline_ns=deadline_ns),
                        )
                    except Exception:
                        clear_observation(self.pulse)
                    raise
            if not roles and not expected_pulses:
                receipt = await self.resolution.report_if_ready(
                    control.OperationContext(command_id=command.command_id)
                )
                if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                    raise RuntimeError(
                        "controller rejected configuration-only resolution"
                    )
            receipts = await asyncio.gather(
                *(
                    port.edit_camera(payload, deadline_ns=deadline_ns)
                    for _role, _child, port, payload in payloads
                )
            )
            if any(item.result != control.COMMAND_RESULT_ACCEPTED for item in receipts):
                raise RuntimeError("one or more camera edit commands were rejected")
            states = await asyncio.gather(
                *(
                    wait_child_operation(child, deadline_ns, self.lock, self.clock)
                    for _role, child, _port, _payload in payloads
                )
            )
            for role, child, _port, _payload in payloads:
                if child.resolved_camera is not None:
                    self.device_status.resolve_camera(
                        role,
                        child.resolved_camera,
                        device_open=True,
                        cleanup_pending=True,
                    )
            if any(not item.succeeded for item in states):
                raise RuntimeError("one or more camera edits failed")
            for _role, child, _port, _payload in payloads:
                if child.resolved_camera is None:
                    raise RuntimeError("camera edit has no retained resolved state")
            if expected_pulses:
                assert requested_pulses is not None
                if self.pulse.observation is None:
                    invalidate_released_idle_proof(self.pulse)
                    retain_observation(
                        self.pulse,
                        await self.serial.connect(deadline_ns=deadline_ns),
                    )
                try:
                    invalidate_released_idle_proof(self.pulse)
                    observation = await self.serial.configure(
                        requested_pulses,
                        active_roles=requested_active_roles,
                        deadline_ns=deadline_ns,
                        resolution_operation=control.OperationContext(
                            command_id=command.command_id
                        ),
                        requested_configuration_revision=revision,
                    )
                except Exception:
                    try:
                        retain_observation(
                            self.pulse,
                            await self.serial.status(deadline_ns=deadline_ns),
                        )
                    except Exception:
                        clear_observation(self.pulse)
                    raise
                receipt = await self.resolution.set_pulse_resolution(
                    control.OperationContext(command_id=command.command_id),
                    mcu.PulseConfigurationResolution(
                        requested_configuration_revision=revision,
                        requested=requested_pulses,
                        behavioral_active=(
                            camera.CAMERA_ROLE_BEHAVIORAL in requested_active_roles
                        ),
                        tracking_active=(
                            camera.CAMERA_ROLE_TRACKING in requested_active_roles
                        ),
                        applied=observation,
                    ),
                )
                if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                    raise RuntimeError("controller rejected MCU readback")
            if expected_pulses:
                retain_observation(
                    self.pulse,
                    mcu.MicrocontrollerObservation.FromString(
                        observation.SerializeToString(deterministic=True)
                    ),
                )
            await self.resolution.wait_confirmed(
                control.OperationContext(command_id=command.command_id),
                deadline_ns=deadline_ns,
            )
            if preview_token:
                resolved_by_role = {
                    role: child.resolved_camera
                    for role, child, _port, _payload in payloads
                    if child.resolved_camera is not None
                }
                preview_token = tuple(
                    PausedPreview(
                        item.role,
                        resolved_by_role.get(item.role, item.resolved),
                        item.output_bits,
                    )
                    for item in preview_token
                )
                await self.preview.resume_after_pulse_change(
                    preview_token,
                    deadline_ns=deadline_ns,
                    parent_operation=control.OperationContext(
                        command_id=command.command_id
                    ),
                )
            for role, child, _port, _payload in payloads:
                assert child.resolved_camera is not None
                worker = self.workers.workers[role]
                preview = worker.preview
                if (
                    preview is not None
                    and preview.started
                    and preview.resolved_camera is not None
                ):
                    self.device_status.resolve_camera(
                        role,
                        preview.resolved_camera,
                        device_open=True,
                        preview_prepared=preview.preparation is not None,
                        preview_running=True,
                        preview_run_id=preview.run_id,
                        configuration_revision=preview.configuration_revision,
                    )
                    continue
                self.device_status.resolve_camera(
                    role,
                    child.resolved_camera,
                    device_open=True,
                    configuration_revision=self.configuration.revision,
                )
            completion = await self.results.complete(
                command,
                command_name="ApplyCameraSettings",
                deadline_ns=deadline_ns,
                status_code="DEVICE_STATUS",
                status_failure="controller rejected camera status",
                parent_code="PARENT_REPORT",
                parent_failure="controller rejected camera completion",
            )
            await self.resolution.retire(
                control.OperationContext(command_id=command.command_id)
            )
            return completion
        except asyncio.CancelledError:
            operation = control.OperationContext(command_id=command.command_id)
            try:
                await self.resolution.cancel(operation)
            except (RuntimeError, ValueError):
                pass
            await self.results.report_failure(
                command,
                command_name="ApplyCameraSettings",
                deadline_ns=deadline_ns,
                failure="camera settings operation was cancelled",
            )
            raise
        except Exception as exc:
            detail = str(exc) or type(exc).__name__
            operation = control.OperationContext(command_id=command.command_id)
            try:
                await self.resolution.cancel(operation)
            except (RuntimeError, ValueError):
                pass
            await self.results.report_failure(
                command,
                command_name="ApplyCameraSettings",
                deadline_ns=deadline_ns,
                failure=detail,
            )
            await self.results.report_operation_failure(
                command,
                command_name="ApplyCameraSettings",
                deadline_ns=deadline_ns,
                code="CAMERA_EDIT_FAILED",
                failure=detail,
            )
            reconcile = getattr(self.resolution, "retire_failed_if_quiescent", None)
            if callable(reconcile):
                await reconcile(operation)
            return _rejected(command.command_id, "CAMERA_EDIT_FAILED", detail)

    async def retire_failed_edit(self, command_id: str) -> None:
        await self.recovery.retire_failed_edit(command_id)

    async def execute(
        self,
        request: wire.AcquisitionCameraCommand,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        return await self.commands.execute(request, deadline_ns=deadline_ns)

    def _build_apply_payloads(
        self,
        request: wire.AcquisitionCameraSettingsCommand,
        deadline_ns: int,
    ) -> list[tuple[int, ChildOperation, WorkerPort, acq.WorkerEditCamera]]:
        payloads = []
        for item in request.cameras:
            if not item.HasField("requested") or not item.requested.device_id:
                raise ValueError("camera edit lacks a complete assigned device")
            worker = self.workers.workers.get(item.camera)
            if worker is None or worker.context.work.WhichOneof("work") is not None:
                raise ValueError("camera edit cannot implicitly open an offline device")
            policy = camera_policy(request.file_policies, item.camera)
            if item.transport != policy.transport:
                raise ValueError("edit transport differs from resolved file policy")
            child, operation, port = retain_worker_command(
                worker,
                work=None,
                parent_operation=control.OperationContext(
                    command_id=request.command.command_id
                ),
                kind="apply_camera",
                deadline_ns=deadline_ns,
                configuration_revision=request.configuration_revision,
                requested_device_id=item.requested.device_id,
            )
            payload = acq.WorkerEditCamera(
                command=child,
                configuration_revision=request.configuration_revision,
                kind=acq.CAMERA_EDIT_KIND_APPLY_SETTINGS,
                requested=item.requested,
                transport=item.transport,
            )
            payloads.append((int(item.camera), operation, port, payload))
        return payloads


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )


def _requested_external_previews(
    request: wire.AcquisitionCameraSettingsCommand,
    settings: control.AcquisitionSettings,
    active_roles: tuple[int, ...],
) -> tuple[int, ...]:
    """Retain only running previews that remain externally triggered after edit."""
    requested = {item.camera: item.requested for item in request.cameras}
    selected = []
    for raw_role in active_roles:
        role = cast(camera.CameraRole, raw_role)
        configured = requested.get(role)
        if configured is None:
            configured = getattr(
                settings,
                role_name(role),
            ).device
        if (
            configured.HasField("frame_timing")
            and configured.frame_timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
        ):
            selected.append(role)
    return tuple(selected)
