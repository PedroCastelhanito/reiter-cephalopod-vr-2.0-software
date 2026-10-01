"""Command-ledger-backed retention for exact acquisition device dispositions."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from cephvr.control.v1 import services_pb2 as svc
from cephvr.controller.state import CameraOperation, DeviceState
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger

_STATUS_RESERVATION_BYTES = 65_536


class CameraStatusRetention:
    """Reserve bounded exact status evidence before each camera-side effect."""

    def __init__(
        self, device: DeviceState, clock: Callable[[], int] = host_time_ns
    ) -> None:
        self.device = device
        self.clock = clock
        self.ledger: CommandLedger | None = None

    def bind_ledger(self, ledger: CommandLedger) -> None:
        if self.ledger is not None and self.ledger is not ledger:
            raise RuntimeError("camera status retention ledger is already bound")
        self.ledger = ledger

    def reserve(self, operation: CameraOperation) -> None:
        ledger = self._require_ledger()
        record = ledger.get(operation.operator_id)
        internal = record is None
        if record is None:
            # Owner-loss cleanup creates a camera operation outside the public
            # command gate; reserve an exact synthetic command in the same ledger,
            # from the safety reserve so ordinary budget exhaustion cannot block it.
            work_key = operation.child_id
            ledger.admit(
                operation.child_id,
                b"internal-camera-operation\0" + operation.child_id.encode(),
                self.clock(),
                work_key=work_key,
                priority=True,
            )
            operation.internal_retention = True
        else:
            work_key = record.work_key
        key = _reservation_key(operation.child_id)
        try:
            ledger.reserve_payload(
                key, _STATUS_RESERVATION_BYTES, work_key=work_key, priority=internal
            )
        except (RuntimeError, ValueError):
            if internal:
                ledger.complete(
                    operation.child_id,
                    b"camera operation retention rejected",
                    self.clock(),
                )
                ledger.finalize_work(work_key, self.clock())
            raise
        operation.status_reservation_key = key
        operation.status_work_key = work_key
        self.device.camera_operations[operation.child_id] = operation

    def find(self, command_id: str) -> CameraOperation | None:
        self.prune()
        operation = self.device.camera_operations.get(command_id)
        if operation is None:
            return None
        ledger = self._require_ledger()
        if not ledger.has_payload(operation.status_reservation_key):
            return None
        return operation

    def retain_terminal(
        self,
        operation: CameraOperation,
        report: svc.AcquisitionDeviceStatusReport,
    ) -> None:
        if report.ByteSize() > _STATUS_RESERVATION_BYTES:
            raise ValueError("camera device status exceeds its retained reservation")
        if (
            operation.final_status is not None
            and operation.final_status.SerializeToString(deterministic=True)
            != report.SerializeToString(deterministic=True)
        ):
            raise ValueError("camera command terminal status changed")
        operation.final_status = deepcopy(report)

    def release_unstarted(self, operation: CameraOperation) -> None:
        ledger = self._require_ledger()
        if operation.status_reservation_key:
            ledger.release_payload(operation.status_reservation_key)
        self.device.camera_operations.pop(operation.child_id, None)
        if operation.internal_retention and operation.status_work_key:
            ledger.complete(
                operation.child_id, b"camera operation not dispatched", self.clock()
            )
            ledger.finalize_work(operation.status_work_key, self.clock())

    def retire_operation(self, operation: CameraOperation) -> None:
        """Free the active slot under the caller's lifecycle lock, retaining evidence.

        Manual effects stay admitted in case an expired command was delivered.
        Callers own the terminal/timeout decision and verify the active operation.
        """
        self.device.completed_camera_operation = operation
        self.complete_internal(operation)
        self.device.camera_operation = None
        self.device.camera_operation_changed.set()

    def complete_internal(self, operation: CameraOperation) -> None:
        if not operation.internal_retention or not operation.status_work_key:
            return
        ledger = self._require_ledger()
        record = ledger.get(operation.child_id)
        if record is not None and record.completed_ns is None:
            ledger.complete(
                operation.child_id, b"camera operation complete", self.clock()
            )
        ledger.finalize_work(operation.status_work_key, self.clock())

    def prune(self) -> None:
        ledger = self.ledger
        if ledger is None:
            return
        ledger.prune(self.clock())
        active = self.device.camera_operation
        for command_id, operation in tuple(self.device.camera_operations.items()):
            if operation is active:
                continue
            if not ledger.has_payload(operation.status_reservation_key):
                self.device.camera_operations.pop(command_id, None)

    def _require_ledger(self) -> CommandLedger:
        if self.ledger is None:
            raise RuntimeError(
                "camera status retention is not bound to command admission"
            )
        return self.ledger


def _reservation_key(command_id: str) -> str:
    return "camera-device-status:" + command_id
