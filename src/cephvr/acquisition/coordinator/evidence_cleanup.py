"""Exact worker cleanup and output-result retention (E06/E08)."""

from __future__ import annotations

from cephvr.acquisition.state import ResourceRecord, SessionRecord, WorkerRecord
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.commands import CommandLedger


class WorkerCleanupEvidence:
    def __init__(
        self,
        *,
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        commands: CommandLedger,
    ) -> None:
        self.resources = resources
        self.resource_ledger = resource_ledger
        self.commands = commands

    def retain(
        self,
        session: SessionRecord,
        worker: WorkerRecord,
        cleanup: acq.WorkerCleanupEvidence,
    ) -> None:
        """Accept exact producer/device releases and retain output closure results."""
        if worker.setup_ready is None or worker.commands is None:
            raise ValueError("session cleanup lacks retained Setup ownership")
        releases: dict[str, control.ResourceRelease] = {}
        for release in cleanup.resources:
            if not release.resource or release.resource in releases:
                raise ValueError("session cleanup repeats or omits a resource key")
            releases[release.resource] = release
        expected: dict[str, str] = {
            item.resource_id: item.transfer_id
            for item in worker.setup_ready.attached_resources
        }
        device_key = f"camera-device:{worker.launch.worker.generation}"
        expected[device_key] = ""
        for resource_id in expected:
            release_claim = releases.get(resource_id)
            if (
                release_claim is None
                or not release_claim.released
                or release_claim.failure.code
                or release_claim.failure.message
                or release_claim.HasField("path")
            ):
                raise ValueError(
                    "session cleanup does not prove exact ownership release"
                )
        result_keys: set[str] = set()
        role_prefix = (
            "behavioral_cam"
            if worker.context.camera == camera_pb2.CAMERA_ROLE_BEHAVIORAL
            else "tracking_cam"
        )
        for result in cleanup.outputs:
            if (
                result.output_key in result_keys
                or result.output_key
                not in {item.output_key for item in session.reserved_outputs}
                or not any(
                    item.output_key == result.output_key
                    and item.output_tag in {role_prefix, f"{role_prefix}_frames"}
                    for item in session.reserved_outputs
                )
                or not result.HasField("artifact_present")
            ):
                raise ValueError(
                    "session cleanup output differs from its role reservation"
                )
            result_keys.add(result.output_key)
        for resource_id, transfer_id in expected.items():
            if resource_id == device_key:
                continue
            resource = self.resources.get(resource_id)
            if resource is None:
                raise ValueError("Setup cleanup names an unretained ring allocation")
            if not any(
                item.peer_instance_id == worker.launch.worker.generation
                and item.transfer_id == transfer_id
                and item.attached
                for item in self.resource_ledger.snapshot(resource.ledger_key).transfers
            ):
                raise ValueError(
                    "worker cleanup transfer differs from exact Setup Ready"
                )
        session.preflight_output_results(tuple(cleanup.outputs), self.commands)
        for resource_id, transfer_id in expected.items():
            if resource_id == device_key:
                continue
            resource = self.resources[resource_id]
            snapshot = self.resource_ledger.snapshot(resource.ledger_key)
            transfer = next(
                item
                for item in snapshot.transfers
                if item.peer_instance_id == worker.launch.worker.generation
                and item.transfer_id == transfer_id
            )
            if not transfer.released:
                self.resource_ledger.confirm_release(
                    resource.ledger_key,
                    peer_instance_id=worker.launch.worker.generation,
                    transfer_id=transfer_id,
                )
        for result in cleanup.outputs:
            session.retain_output_result(result, worker.commands)
