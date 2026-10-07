"""Typed Tracking diagnostic configuration and status projection helpers."""

from __future__ import annotations

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.tracking.v1 import services_pb2 as tracking


def tracking_settings(
    configuration: pb.ExperimentConfiguration,
) -> pb.BackendSettings | None:
    matches = [
        item for item in configuration.backends if item.backend_name == "tracking"
    ]
    if len(matches) != 1 or matches[0].WhichOneof("settings") != "tracking":
        return None
    return matches[0]


def copy_status(
    destination: pb.TrackingDiagnosticState, source: tracking.TrackingDiagnosticState
) -> None:
    destination.diagnostic_id = source.diagnostic_id
    destination.configuration_revision = source.configuration_revision
    destination.preview_run_id = source.preview_run_id
    destination.acquisition_run_id = source.acquisition_run_id
    destination.input_frames = source.input_frames
    destination.evaluated_frames = source.evaluated_frames
    destination.lapped_frames = source.lapped_frames
    destination.last_duration_ns = source.last_processing_duration_ns or 0
    destination.maximum_duration_ns = source.max_processing_duration_ns or 0
    destination.failure = (
        source.failure_message if source.HasField("failure_message") else ""
    )
    destination.active = source.active
    # Backend closure alone does not release the controller's exact Acquisition
    # transfer. The controller sets `closed` only after both release receipts.
    del destination.stages[:]
    for item in source.stages:
        destination.stages.add(
            stage=item.stage, state=item.state, reason=item.reason or ""
        )


def reject(command_id: str, message: str) -> pb.CommandAdmission:
    return pb.CommandAdmission(
        command_id=command_id,
        result=pb.COMMAND_RESULT_REJECTED,
        failure=pb.Failure(code="TRACKING_DIAGNOSTIC", message=message),
    )


def matches_status(
    status: tracking.TrackingDiagnosticState,
    expected: pb.TrackingDiagnosticState,
    attachment: svc.PreviewAttachmentResult | None,
) -> bool:
    return bool(
        attachment is not None
        and attachment.available
        and status.diagnostic_id == expected.diagnostic_id
        and status.configuration_revision == expected.configuration_revision
        and status.preview_run_id == expected.preview_run_id
        and status.acquisition_run_id == expected.preview_run_id
        and status.tracking_frames.resource_id
        == attachment.attachment.buffer.allocation_id
        and status.tracking_frames.transfer_id == attachment.attachment.sync.transfer_id
    )
