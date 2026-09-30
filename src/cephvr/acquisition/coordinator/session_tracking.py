"""Exact Setup tracking-input attachment and cleanup confirmation (A03/E08)."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.state import (
    CoordinatorIdentity,
    ResourceRecord,
    SessionSlot,
)
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.clock import host_time_ns


class SessionTrackingConfirmation:
    """Adopt exact controller attachment and registered-transfer release evidence."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.resources = resources
        self.resource_ledger = resource_ledger
        self.clock = clock

    async def confirm_tracking_input(
        self,
        request: wire.TrackingInputConfirmation,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        """Accept exact tracking attachment or transfer-release evidence."""
        session = self.session_slot.current
        kind = request.WhichOneof("evidence")
        if kind == "tracking_cleanup":
            cleanup = request.tracking_cleanup
            if (
                session is None
                or self.clock() > deadline_ns
                or request.command.issuer
                not in (
                    self.identity.controller,
                    self.identity.supervisor,
                )
                or request.command.target != self.identity.backend
                or request.command.work != session.work
                or session.tracking_input_report is None
                or cleanup.source != self.identity.tracking
                or cleanup.work != session.work
                or not cleanup.operation.command_id
                or cleanup.verified_monotonic_ns <= 0
                or not cleanup.trial_activity_stopped
                or not cleanup.HasField("cleanup_resources_revision")
                or cleanup.cleanup_resources_revision == 0
            ):
                return _rejected(
                    request.command.command_id,
                    "TRACKING_CLEANUP_SCOPE",
                    "tracking cleanup does not match the registered Setup transfer",
                )
            attachment = session.tracking_input_report.tracking_input
            resource = self.resources.get(attachment.buffer.allocation_id)
            if resource is None:
                return _rejected(
                    request.command.command_id,
                    "TRACKING_CLEANUP_RESOURCE",
                    "registered tracking input allocation is not retained",
                )
            releases = [
                item
                for item in cleanup.resources
                if item.resource == attachment.buffer.allocation_id
            ]
            if (
                len(releases) != 1
                or not releases[0].released
                or releases[0].failure.code
                or releases[0].failure.message
            ):
                return _rejected(
                    request.command.command_id,
                    "TRACKING_CLEANUP_RELEASE",
                    "cleanup must prove release of the exact registered input resource",
                )
            snapshot = self.resource_ledger.snapshot(resource.ledger_key)
            expected_transfer = attachment.sync.transfer_id
            matches = [
                transfer
                for transfer in snapshot.transfers
                if transfer.transfer_id == expected_transfer
                and transfer.peer_instance_id == self.identity.tracking.generation
                and transfer.attached
            ]
            if len(matches) != 1:
                return _rejected(
                    request.command.command_id,
                    "TRACKING_CLEANUP_TRANSFER",
                    "cleanup does not match the registered tracking consumer transfer",
                )
            prior_cleanup = session.tracking_cleanup_confirmation
            if prior_cleanup is not None and prior_cleanup != request:
                return _rejected(
                    request.command.command_id,
                    "TRACKING_CLEANUP_CONFLICT",
                    "tracking transfer already has different cleanup evidence",
                )
            if session.cleanup_deadline_ns is None:
                session.cleanup_deadline_ns = deadline_ns
            if deadline_ns != session.cleanup_deadline_ns:
                return _rejected(
                    request.command.command_id,
                    "TRACKING_CLEANUP_DEADLINE",
                    "tracking cleanup evidence changed its original deadline",
                )
            retained_cleanup = wire.TrackingInputConfirmation()
            retained_cleanup.CopyFrom(request)
            session.tracking_cleanup_confirmation = retained_cleanup
            self.resource_ledger.confirm_release(
                resource.ledger_key,
                peer_instance_id=self.identity.tracking.generation,
                transfer_id=expected_transfer,
            )
            session.tracking_cleanup_confirmed.set()
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=request.command.command_id,
            )

        if kind != "tracking_evidence":
            return _rejected(
                request.command.command_id,
                "TRACKING_INPUT_CONFIRMATION",
                "exactly one tracking evidence payload is required",
            )
        tracking = request.tracking_evidence
        source = tracking.source
        if (
            session is None
            or session.setup_cancelled
            or session.interrupted
            or self.clock() > deadline_ns
            or request.command.issuer != self.identity.controller
            or request.command.target != self.identity.backend
            or request.command.work != session.work
            or request.configuration_revision != session.confirmed_revision
            or source.backend.backend_name != "tracking"
            or source.backend.backend_generation != self.identity.tracking.generation
            or source.work != session.work
            or source.operation.command_id == ""
            or tracking.configuration_revision != session.confirmed_revision
            or tracking.WhichOneof("payload") != "tracking"
            or not tracking.tracking.data_attached
            or not tracking.tracking.HasField("attached_input")
            or session.tracking_input_report is None
            or tracking.tracking.attached_input.resource_id
            != session.tracking_input_report.tracking_input.buffer.allocation_id
            or tracking.tracking.attached_input.transfer_id
            != session.tracking_input_report.tracking_input.sync.transfer_id
        ):
            return _rejected(
                request.command.command_id,
                "TRACKING_INPUT_CONFIRMATION",
                "tracking evidence does not confirm this Setup attachment",
            )
        prior = session.tracking_input_confirmation
        if prior is not None and prior != request:
            return _rejected(
                request.command.command_id,
                "TRACKING_INPUT_CONFLICT",
                "tracking input was already confirmed with different evidence",
            )
        retained = wire.TrackingInputConfirmation()
        retained.CopyFrom(request)
        session.tracking_input_confirmation = retained
        session.tracking_input_confirmed.set()
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
