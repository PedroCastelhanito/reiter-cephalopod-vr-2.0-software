"""Build complete session cleanup reports from retained owner evidence (E06/E08)."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.ports import ResourcePort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    ResourceRecord,
    SessionRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.cleanup_outputs import cleanup_output_discharged
from cephvr.shared.clock import host_time_ns


class CleanupReportBuilder:
    """Validate every catalogued release/output before creating the report."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        workers: dict[int, WorkerRecord],
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        resource_port: ResourcePort,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.workers = workers
        self.resources = resources
        self.resource_ledger = resource_ledger
        self.resource_port = resource_port
        self.clock = clock

    def build(
        self,
        session: SessionRecord,
        command_id: str,
        worker_cleanup: dict[int, acq.WorkerCleanupEvidence],
        serial_released: bool,
    ) -> control.CleanupReport:
        worker_releases: dict[str, control.ProcessIdentity] = {}
        for role, evidence in worker_cleanup.items():
            record = self.workers[role]
            for release in evidence.resources:
                if release.released:
                    worker_releases[release.resource] = record.launch.worker
        releases: list[control.ResourceRelease] = []
        for obligation in session.cleanup_resources:
            resource_id = obligation.resource
            if resource_id.startswith("microcontroller-claim:"):
                if not serial_released:
                    raise ValueError(
                        "Microcontroller claim lacks OFF and controller-release proof"
                    )
            elif obligation.owner in (
                item.launch.worker for item in self.workers.values()
            ):
                if worker_releases.get(resource_id) != obligation.owner:
                    raise ValueError(
                        f"worker resource {resource_id} lacks exact release proof"
                    )
            elif resource_id in self.resources:
                self._close_ring(resource_id)
            else:
                raise ValueError(
                    f"catalogued resource {resource_id} has no retained owner proof"
                )
            releases.append(
                control.ResourceRelease(resource=resource_id, released=True)
            )

        outputs: dict[str, control.OutputResult] = {}
        for plan in session.reserved_outputs:
            result = session.output_results.get(plan.output_key)
            if result is None:
                if plan.output_key in session.dispatched_output_keys:
                    raise ValueError(
                        f"dispatched output {plan.output_key} has no closure result"
                    )
                result = control.OutputResult(
                    output_key=plan.output_key,
                    closure=control.OUTPUT_CLOSURE_NOT_STARTED,
                    artifact_present=False,
                )
                if plan.output_tag in {"behavioral_cam", "tracking_cam"}:
                    result.camera_video_content = control.CAMERA_VIDEO_CONTENT_NO_FRAMES
            if not cleanup_output_discharged(result):
                raise ValueError(
                    f"output {plan.output_key} lacks cleanup closure proof"
                )
            outputs[plan.output_key] = result
        if len(outputs) != len(session.reserved_outputs):
            raise ValueError(
                "cleanup report does not cover the complete output reservation"
            )
        report = control.CleanupReport(
            source=self.identity.process,
            work=session.work,
            operation=control.OperationContext(command_id=command_id),
            verified_monotonic_ns=self.clock(),
            trial_activity_stopped=True,
            cleanup_resources_revision=session.cleanup_resources_revision,
        )
        report.resources.extend(releases)
        report.outputs.extend(outputs[key] for key in sorted(outputs))
        return report

    def _close_ring(self, allocation_id: str) -> None:
        resource = self.resources[allocation_id]
        if resource.native_state == "released":
            return
        if not self.resource_ledger.may_close_owner(resource.ledger_key):
            raise ValueError(f"ring {allocation_id} still has an unreleased transfer")
        if resource.native_state != "absent":
            self.resource_port.release_ring(allocation_id)
        self.resource_ledger.confirm_owner_release(resource.ledger_key)
        resource.native_state = "released"
