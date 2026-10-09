"""Shared terminal status and parent-operation reporting for manual commands."""

from __future__ import annotations

from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import CoordinatorIdentity
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control


class ManualOperationResults:
    """Publish one exact device snapshot before completing its parent command."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        controller: ControllerPort,
        device_status: ManualDeviceStatusReporter,
    ) -> None:
        self.identity = identity
        self.controller = controller
        self.device_status = device_status

    async def complete(
        self,
        command: wire.BackendCommand,
        *,
        command_name: str,
        deadline_ns: int,
        status_code: str,
        status_failure: str,
        parent_code: str,
        parent_failure: str,
        exported_pfs_path: str | None = None,
    ) -> control.CommandAdmission:
        status = await self.device_status.report(
            command,
            command_name=command_name,
            succeeded=True,
            deadline_ns=deadline_ns,
            exported_pfs_path=exported_pfs_path,
        )
        if status.result != control.COMMAND_RESULT_ACCEPTED:
            return _rejected(command, status_code, status_failure)
        receipt = await self.controller.report_lifecycle(
            control.LifecycleReport(
                operation=control.BackendOperationReport(
                    source=self.identity.backend,
                    operation=control.OperationState(
                        context=control.OperationContext(command_id=command.command_id),
                        command=command_name,
                        work=command.work,
                        complete=True,
                        succeeded=True,
                    ),
                )
            ),
            deadline_ns=deadline_ns,
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            return _rejected(command, parent_code, parent_failure)
        self.device_status.finalize_command(command.command_id)
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=command.command_id,
        )

    async def report_failure(
        self,
        command: wire.BackendCommand,
        *,
        command_name: str,
        deadline_ns: int,
        failure: str,
    ) -> None:
        try:
            retained = self.device_status.get_report(command.command_id)
            if retained is not None:
                if self.device_status.clock() >= deadline_ns:
                    return
                await self.controller.report_acquisition_device_status(
                    retained, deadline_ns=deadline_ns
                )
                return
            await self.device_status.report(
                command,
                command_name=command_name,
                succeeded=False,
                deadline_ns=deadline_ns,
                failure=failure,
            )
        except (RuntimeError, TimeoutError, ValueError):
            return

    async def report_operation_failure(
        self,
        command: wire.BackendCommand,
        *,
        command_name: str,
        deadline_ns: int,
        code: str,
        failure: str,
    ) -> bool:
        """Retain the exact failed parent outcome before releasing its owner."""
        status = self.device_status.get_report(command.command_id)
        if (
            status is None
            or status.result.succeeded
            or self.device_status.clock() >= deadline_ns
        ):
            return False
        try:
            receipt = await self.controller.report_lifecycle(
                control.LifecycleReport(
                    operation=control.BackendOperationReport(
                        source=self.identity.backend,
                        operation=control.OperationState(
                            context=control.OperationContext(
                                command_id=command.command_id
                            ),
                            command=command_name,
                            work=command.work,
                            complete=True,
                            succeeded=False,
                            failure=control.Failure(code=code, message=failure[:2048]),
                        ),
                    )
                ),
                deadline_ns=deadline_ns,
            )
        except (RuntimeError, TimeoutError, ValueError):
            return False
        return receipt.result == control.COMMAND_RESULT_ACCEPTED


def _rejected(
    command: wire.BackendCommand, code: str, message: str
) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command.command_id,
        failure=control.Failure(code=code, message=message),
    )
