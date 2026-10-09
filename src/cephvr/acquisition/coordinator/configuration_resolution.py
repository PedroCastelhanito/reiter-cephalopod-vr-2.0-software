"""Shared worker-readback and controller-confirmation barrier (A10/E07)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

from cephvr.acquisition.identity import camera_for_process_role
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import (
    ChildOperation,
    ConfigurationRecord,
    CoordinatorIdentity,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.transport_deadlines import remaining_seconds


class ConfigurationResolution:
    """Own one exact readback batch until the controller adopts its values.

    Setup continues to own its existing `SessionRecord` handshake. This helper is
    for Configuration-only device edits, preview preparation, and PFS operations.
    It deliberately permits one unresolved batch at a time because configuration
    revisions and camera SDK access are serialized by the coordinator.
    """

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        configuration: ConfigurationRecord,
        controller: ControllerPort,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.configuration = configuration
        self.controller = controller
        self.lock = lock
        self.clock = clock
        self._pending: _PendingResolution | None = None

    async def begin(
        self,
        command: wire.BackendCommand,
        *,
        expected_cameras: set[int],
        request_revision: int,
        deadline_ns: int,
        expected_pulses: bool = False,
        requested_pulses: camera.CameraPulseConfiguration | None = None,
        allow_empty: bool = False,
        accepted_base_revision: int | None = None,
        accepted_base_settings: control.AcquisitionSettings | None = None,
        device_work_quiescent: Callable[[], bool] | None = None,
        preexisting_work_quiescent: Callable[[], bool] | None = None,
    ) -> control.OperationContext:
        if (
            self.clock() >= deadline_ns
            or not command.command_id
            or command.issuer != self.identity.controller
            or command.target != self.identity.backend
            or command.work.WhichOneof("work") is not None
            or not command.HasField("parent_operation")
            or not command.parent_operation.command_id
            or (
                request_revision != self.configuration.revision
                and accepted_base_revision is None
            )
            or (not expected_cameras and not expected_pulses and not allow_empty)
            or not expected_cameras.issubset(
                {camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING}
            )
            or expected_pulses != (requested_pulses is not None)
        ):
            raise ValueError("manual resolution request is stale or malformed")
        async with self.lock:
            if self._pending is not None:
                raise RuntimeError("another configuration readback is unresolved")
            if accepted_base_revision is not None or accepted_base_settings is not None:
                if (
                    accepted_base_revision is None
                    or accepted_base_settings is None
                    or accepted_base_revision != request_revision
                ):
                    raise ValueError("accepted configuration base is incomplete")
                if (
                    preexisting_work_quiescent is None
                    or not preexisting_work_quiescent()
                ):
                    raise RuntimeError(
                        "prior camera device work is not terminal and quiescent"
                    )
                base = control.AcquisitionSettings.FromString(
                    accepted_base_settings.SerializeToString(deterministic=True)
                )
                if accepted_base_revision < self.configuration.revision:
                    raise ValueError("accepted configuration base decreases revision")
                if accepted_base_revision == self.configuration.revision:
                    if base.SerializeToString(deterministic=True) != (
                        self.configuration.settings.SerializeToString(
                            deterministic=True
                        )
                    ):
                        raise ValueError("accepted configuration base conflicts")
                else:
                    self.configuration.settings.CopyFrom(base)
                    self.configuration.revision = accepted_base_revision
            operation = control.OperationContext(command_id=command.command_id)
            self._pending = _PendingResolution(
                command=wire.BackendCommand.FromString(
                    command.SerializeToString(deterministic=True)
                ),
                operation=operation,
                request_revision=request_revision,
                deadline_ns=deadline_ns,
                expected_cameras=frozenset(expected_cameras),
                expected_pulses=expected_pulses,
                requested_pulses=(
                    camera.CameraPulseConfiguration.FromString(
                        requested_pulses.SerializeToString(deterministic=True)
                    )
                    if requested_pulses is not None
                    else None
                ),
                device_work_quiescent=device_work_quiescent,
            )
            return control.OperationContext(command_id=operation.command_id)

    async def report_if_ready(
        self, operation: control.OperationContext
    ) -> control.ReportReceipt:
        """Send an empty exact batch for a configuration-only revision update."""
        async with self.lock:
            pending = self._require_pending(operation)
            if pending.expected_cameras or pending.expected_pulses:
                raise ValueError("only an empty configuration batch uses this report")
            report = self._complete_report_if_ready(pending)
        if report is None:
            raise RuntimeError("empty configuration report was not ready")
        return await self._send_report(report, pending)

    async def accept_camera(
        self,
        worker: WorkerRecord,
        child: ChildOperation,
        resolved: camera.CameraResolvedState,
        *,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        report: wire.AcquisitionResolutionReport | None = None
        async with self.lock:
            pending = self._require_pending(child.parent_operation)
            role = camera_for_process_role(worker.launch.worker.role)
            if (
                role not in pending.expected_cameras
                or worker.launch.work.WhichOneof("work") is not None
                or child.camera != role
                or child.work.WhichOneof("work") is not None
                or child.parent_operation != pending.operation
                or child.configuration_revision != pending.request_revision
                or child.deadline_ns != pending.deadline_ns
                or ingress_ns > pending.deadline_ns
                or child.requested_device_id is None
                or not resolved.HasField("device")
                or resolved.device.configured_id != child.requested_device_id
                or resolved.applied.device_id != child.requested_device_id
                or not resolved.HasField("layout")
            ):
                raise ValueError("camera readback differs from its retained operation")
            previous = pending.cameras.get(role)
            if previous is not None and previous != resolved:
                raise ValueError("camera readback changed for one operation")
            pending.cameras[role] = camera.CameraResolvedState.FromString(
                resolved.SerializeToString(deterministic=True)
            )
            report = self._complete_report_if_ready(pending)
        if report is None:
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
        return await self._send_report(report, pending)

    async def set_pulse_resolution(
        self,
        operation: control.OperationContext,
        resolution: mcu.PulseConfigurationResolution,
    ) -> control.ReportReceipt:
        async with self.lock:
            pending = self._require_pending(operation)
            if not pending.expected_pulses:
                raise ValueError("pulse readback was not requested by this operation")
            if (
                pending.requested_pulses is None
                or resolution.requested != pending.requested_pulses
                or resolution.requested_configuration_revision
                != pending.request_revision
            ):
                raise ValueError("pulse readback differs from the exact request")
            if pending.pulses is not None and pending.pulses != resolution:
                raise ValueError("pulse readback changed for one operation")
            pending.pulses = mcu.PulseConfigurationResolution.FromString(
                resolution.SerializeToString(deterministic=True)
            )
            report = self._complete_report_if_ready(pending)
        if report is None:
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
        return await self._send_report(report, pending)

    async def wait_confirmed(
        self,
        operation: control.OperationContext,
        *,
        deadline_ns: int,
    ) -> control.AcquisitionSettings:
        async with self.lock:
            pending = self._require_pending(operation)
        await asyncio.wait_for(
            pending.confirmed.wait(),
            remaining_seconds(min(deadline_ns, pending.deadline_ns)),
        )
        if pending.failure is not None:
            raise RuntimeError(pending.failure)
        if pending.confirmed_settings is None:
            raise RuntimeError("configuration confirmation completed without values")
        return control.AcquisitionSettings.FromString(
            pending.confirmed_settings.SerializeToString(deterministic=True)
        )

    async def confirm(
        self,
        request: wire.AcquisitionConfigurationConfirmation,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        command = request.command
        async with self.lock:
            pending = self._pending
            if (
                pending is None
                or not request.HasField("resolution_operation")
                or request.resolution_operation != pending.operation
                or not request.HasField("requested_configuration_revision")
                or request.requested_configuration_revision != pending.request_revision
                or not request.HasField("confirmed_configuration_revision")
                or request.confirmed_configuration_revision < pending.request_revision
                or not request.HasField("confirmed")
                or pending.failure is not None
                or command.issuer != self.identity.controller
                or command.target != self.identity.backend
                or command.work.WhichOneof("work") is not None
                or command.parent_operation != pending.operation
                or self.clock() >= min(deadline_ns, pending.deadline_ns)
                or not (pending.report_sending or pending.report_accepted)
            ):
                return _rejected(
                    command.command_id,
                    "STALE_CONFIGURATION_CONFIRMATION",
                    "confirmation does not match the live manual resolution",
                )
            if pending.confirmed_settings is not None:
                if (
                    pending.confirmed_revision
                    != request.confirmed_configuration_revision
                    or pending.confirmed_settings != request.confirmed
                ):
                    return _rejected(
                        command.command_id,
                        "CONFIGURATION_CONFLICT",
                        "confirmed configuration changed after adoption",
                    )
                return control.CommandAdmission(
                    result=control.COMMAND_RESULT_ACCEPTED,
                    command_id=command.command_id,
                )
            if not confirmed_matches_resolution(
                request.confirmed,
                pending.report,
                pending.pulses,
                set(pending.expected_cameras),
                request.confirmed_pulses
                if request.HasField("confirmed_pulses")
                else None,
            ):
                return _rejected(
                    command.command_id,
                    "CONFIGURATION_VALUES",
                    "confirmed settings do not match the reported camera readback",
                )
            saved = control.AcquisitionSettings.FromString(
                request.confirmed.SerializeToString(deterministic=True)
            )
            pending.confirmed_settings = saved
            pending.confirmed_revision = request.confirmed_configuration_revision
            pending.confirmed.set()
            self.configuration.settings.CopyFrom(saved)
            self.configuration.revision = request.confirmed_configuration_revision
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=command.command_id,
        )

    async def cancel(self, operation: control.OperationContext) -> None:
        async with self.lock:
            pending = self._pending
            if pending is None or pending.operation != operation:
                return
            pending.failure = "configuration readback was cancelled"
            pending.confirmed.set()

    async def retire(self, operation: control.OperationContext) -> None:
        async with self.lock:
            pending = self._require_pending(operation)
            if not pending.confirmed.is_set():
                raise RuntimeError("configuration resolution is not terminal")
            self._pending = None

    async def retire_failed_if_quiescent(
        self, operation: control.OperationContext | None = None
    ) -> bool:
        """Release a canceled edit only after its retained device work is quiet."""
        async with self.lock:
            pending = self._pending
            if (
                pending is None
                or pending.failure is None
                or not pending.confirmed.is_set()
                or (operation is not None and pending.operation != operation)
                or pending.device_work_quiescent is None
                or not pending.device_work_quiescent()
            ):
                return False
            self._pending = None
            return True

    async def failed_operation(self) -> control.OperationContext | None:
        """Return the exact canceled edit identity for read-only recovery queries."""
        async with self.lock:
            pending = self._pending
            if (
                pending is None
                or pending.failure is None
                or not pending.confirmed.is_set()
            ):
                return None
            return control.OperationContext.FromString(
                pending.operation.SerializeToString(deterministic=True)
            )

    async def _send_report(
        self,
        report: wire.AcquisitionResolutionReport,
        pending: _PendingResolution,
    ) -> control.ReportReceipt:
        try:
            receipt = await self.controller.report_acquisition_resolution(
                report, deadline_ns=pending.deadline_ns
            )
        except BaseException:
            async with self.lock:
                if self._pending is pending:
                    pending.report_sending = False
            raise
        if receipt.result == control.COMMAND_RESULT_ACCEPTED:
            async with self.lock:
                if self._pending is pending:
                    pending.report_accepted = True
                    pending.report_sending = False
        else:
            async with self.lock:
                if self._pending is pending:
                    pending.report_sending = False
        return receipt

    def _complete_report_if_ready(
        self, pending: _PendingResolution
    ) -> wire.AcquisitionResolutionReport | None:
        if (
            pending.report_accepted
            or pending.report_sending
            or set(pending.cameras) != set(pending.expected_cameras)
            or (pending.expected_pulses and pending.pulses is None)
        ):
            return None
        pending.report_sending = True
        report = wire.AcquisitionResolutionReport(
            source=self.identity.backend,
            work=pending.command.work,
            operation=pending.operation,
            requested_configuration_revision=pending.request_revision,
        )
        for role in sorted(pending.cameras):
            report.cameras.add().CopyFrom(
                wire.CameraResolutionEntry(
                    camera=cast(camera.CameraRole, role),
                    result=pending.cameras[role],
                )
            )
        if pending.pulses is not None:
            report.pulses.CopyFrom(pending.pulses)
        pending.report = report
        return wire.AcquisitionResolutionReport.FromString(
            report.SerializeToString(deterministic=True)
        )

    def _require_pending(
        self, operation: control.OperationContext
    ) -> _PendingResolution:
        pending = self._pending
        if pending is None or pending.operation != operation:
            raise ValueError("configuration operation is not the retained live batch")
        return pending


@dataclass
class _PendingResolution:
    command: wire.BackendCommand
    operation: control.OperationContext
    request_revision: int
    deadline_ns: int
    expected_cameras: frozenset[int]
    expected_pulses: bool
    requested_pulses: camera.CameraPulseConfiguration | None
    device_work_quiescent: Callable[[], bool] | None = None
    cameras: dict[int, camera.CameraResolvedState] = field(default_factory=dict)
    pulses: mcu.PulseConfigurationResolution | None = None
    report: wire.AcquisitionResolutionReport = field(
        default_factory=wire.AcquisitionResolutionReport
    )
    report_sending: bool = False
    report_accepted: bool = False
    confirmed: asyncio.Event = field(default_factory=asyncio.Event)
    failure: str | None = None
    confirmed_settings: control.AcquisitionSettings | None = None
    confirmed_revision: int | None = None


def confirmed_matches_resolution(
    confirmed: control.AcquisitionSettings,
    resolution: wire.AcquisitionResolutionReport,
    pulse_resolution: mcu.PulseConfigurationResolution | None,
    roles: set[int],
    confirmed_pulses: mcu.PulseConfigurationResolution | None,
) -> bool:
    selected = {
        camera.CAMERA_ROLE_BEHAVIORAL: "behavioral",
        camera.CAMERA_ROLE_TRACKING: "tracking",
    }
    entries = {item.camera: item.result for item in resolution.cameras}
    for role in roles:
        role_enum = cast(camera.CameraRole, role)
        value = getattr(confirmed, selected[role_enum])
        resolved = entries.get(role_enum)
        if (
            resolved is None
            or not value.HasField("device")
            or value.device != resolved.applied
        ):
            return False
    if pulse_resolution is None:
        return confirmed_pulses is None
    return confirmed_pulses is not None and confirmed_pulses == pulse_resolution


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
