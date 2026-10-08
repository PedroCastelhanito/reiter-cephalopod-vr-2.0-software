"""Exact producer attachment and release evidence for manual camera previews."""

from __future__ import annotations

from cephvr.acquisition.state import ResourceRecord, WorkerPreview, WorkerRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.platform.windows.resource_ledger import NativeResourceLedger


class ManualPreviewEvidence:
    def __init__(
        self, resources: dict[str, ResourceRecord], ledger: NativeResourceLedger
    ) -> None:
        self.resources = resources
        self.ledger = ledger

    @staticmethod
    def _attachments(
        preview: WorkerPreview | None,
    ) -> list[tuple[str, acq.FrameBufferAttachment]]:
        if (
            preview is None
            or preview.allocation_id is None
            or preview.worker_attachment is None
        ):
            raise ValueError("manual preview producer attachment is incomplete")
        expected = [(preview.allocation_id, preview.worker_attachment)]
        if preview.tracking_allocation_id is not None:
            if preview.tracking_worker_attachment is None:
                raise ValueError("manual Tracking producer attachment is incomplete")
            expected.append(
                (preview.tracking_allocation_id, preview.tracking_worker_attachment)
            )
        elif preview.tracking_worker_attachment is not None:
            raise ValueError("manual Tracking allocation identity is incomplete")
        if len({allocation for allocation, _ in expected}) != len(expected):
            raise ValueError("manual preview allocations must be distinct")
        return expected

    def _resource(
        self,
        worker: WorkerRecord,
        allocation: str,
        attachment: acq.FrameBufferAttachment,
    ) -> ResourceRecord | None:
        resource = self.resources.get(allocation)
        if (
            resource is None
            or attachment.buffer.allocation_id != allocation
            or resource.attachment.buffer.producer != worker.launch.worker
            or resource.attachment.buffer.owner != worker.launch.owner
            or resource.attachment.sync.target != worker.launch.worker
            or resource.attachment.sync.transfer_id != attachment.sync.transfer_id
        ):
            return None
        return resource

    def attachments_match(
        self, worker: WorkerRecord, ready: acq.WorkerReadyEvidence
    ) -> bool:
        try:
            expected = self._attachments(worker.preview)
        except ValueError:
            return False
        provided = {
            item.resource_id: item.transfer_id for item in ready.attached_resources
        }
        if len(provided) != len(ready.attached_resources) or set(provided) != {
            allocation for allocation, _ in expected
        }:
            return False
        for allocation, attachment in expected:
            transfer = provided[allocation]
            resource = self._resource(worker, allocation, attachment)
            if resource is None or transfer != attachment.sync.transfer_id:
                return False
            snapshot = self.ledger.snapshot(resource.ledger_key)
            if not any(
                item.peer_instance_id == worker.launch.worker.generation
                and item.transfer_id == transfer
                and not item.released
                and not item.attached
                for item in snapshot.transfers
            ):
                return False
        return True

    def confirm_cleanup(
        self, worker: WorkerRecord, cleanup: acq.WorkerCleanupEvidence, *, exact: bool
    ) -> None:
        """Validate every release before committing any producer transfer release."""
        expected = self._attachments(worker.preview)
        provided = {item.resource: item for item in cleanup.resources}
        if len(provided) != len(cleanup.resources) or (
            exact and set(provided) != {allocation for allocation, _ in expected}
        ):
            raise ValueError(
                "manual preview cleanup differs from its exact ring releases"
            )
        retained = []
        for allocation, attachment in expected:
            release = provided.get(allocation)
            resource = self._resource(worker, allocation, attachment)
            if (
                release is None
                or not release.released
                or release.failure.code
                or release.failure.message
                or release.HasField("path")
                or resource is None
            ):
                raise ValueError(
                    "manual preview cleanup does not prove its exact ring release"
                )
            snapshot = self.ledger.snapshot(resource.ledger_key)
            if not any(
                item.peer_instance_id == worker.launch.worker.generation
                and item.transfer_id == attachment.sync.transfer_id
                for item in snapshot.transfers
            ):
                raise ValueError(
                    "manual preview producer release transfer is not retained"
                )
            retained.append((resource.ledger_key, attachment.sync.transfer_id))
        for key, transfer in retained:
            self.ledger.confirm_release(
                key,
                peer_instance_id=worker.launch.worker.generation,
                transfer_id=transfer,
            )
