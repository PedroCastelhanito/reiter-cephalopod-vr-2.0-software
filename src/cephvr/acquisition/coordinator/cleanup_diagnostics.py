"""Bounded reasons for incomplete camera-worker cleanup proof (E06)."""

from __future__ import annotations

from cephvr.acquisition.identity import camera_role_name
from cephvr.acquisition.state import WorkerRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


def missing_worker_cleanup_failure(worker: WorkerRecord) -> str:
    return (
        f"{worker.launch.worker.role} camera worker generation "
        f"{worker.launch.worker.generation} cleanup retained evidence is missing"
    )[:512]


def worker_cleanup_failure(
    worker: WorkerRecord, evidence: acq.WorkerCleanupEvidence
) -> str | None:
    identity = (
        f"{camera_role_name(worker.context.camera)} camera worker "
        f"generation {worker.launch.worker.generation}"
    )

    def incomplete(detail: str) -> str:
        return f"{identity} cleanup {detail}"[:512]

    expected = (
        {item.resource_id for item in worker.setup_ready.attached_resources}
        if worker.setup_ready is not None
        else set()
    )
    if worker.preview is not None and worker.preview.allocation_id is not None:
        expected.add(worker.preview.allocation_id)
    expected.add(f"camera-device:{worker.launch.worker.generation}")
    releases = {item.resource: item for item in evidence.resources}
    if len(releases) != len(evidence.resources):
        return incomplete("has duplicate native resource release evidence")
    for resource in sorted(expected - set(releases)):
        return incomplete(f"is missing native resource release evidence for {resource}")
    for resource, release in releases.items():
        if not release.released:
            return incomplete(f"native resource remains unreleased: {resource}")
        if release.failure.code or release.failure.message or release.HasField("path"):
            return incomplete(
                f"native resource release evidence is invalid: {resource}"
            )
    if len({item.output_key for item in evidence.outputs}) != len(evidence.outputs):
        return incomplete("has duplicate output closure evidence")
    for item in evidence.outputs:
        if not item.output_key:
            return incomplete("has output closure evidence without an output identity")
        if not item.HasField("artifact_present"):
            return incomplete(
                f"is missing artifact status for output {item.output_key}"
            )
        if item.closure == control.OUTPUT_CLOSURE_CLOSED:
            if not item.artifact_present:
                return incomplete(
                    f"is missing the closed output artifact {item.output_key}"
                )
            if item.failure.ByteSize():
                return incomplete(
                    f"has invalid closure evidence for output {item.output_key}"
                )
        elif item.closure == control.OUTPUT_CLOSURE_FAILED:
            if not item.failure.code or not item.failure.message:
                return incomplete(
                    f"has an incomplete failed-closure reason for output {item.output_key}"
                )
        elif item.closure == control.OUTPUT_CLOSURE_NOT_STARTED:
            if (
                item.artifact_present
                or item.failure.ByteSize()
                or item.camera_video_content
                not in {
                    control.CAMERA_VIDEO_CONTENT_UNSPECIFIED,
                    control.CAMERA_VIDEO_CONTENT_NO_FRAMES,
                }
            ):
                return incomplete(
                    f"has invalid not-started output evidence for {item.output_key}"
                )
        else:
            return incomplete(f"has unknown output closure state for {item.output_key}")
    return None
