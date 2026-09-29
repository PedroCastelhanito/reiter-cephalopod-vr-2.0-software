"""Atomic camera readback adoption into the controller's configuration (E07/A10)."""

from __future__ import annotations

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.projections import ProjectionError


def resolved_configuration(
    current: pb.ExperimentConfiguration,
    report: rpc.AcquisitionResolutionReport,
    *,
    source: pb.BackendContext,
    work: pb.WorkContext,
    operation_id: str,
    revision: int,
    expected_cameras: frozenset[int],
    expect_pulses: bool,
) -> pb.ExperimentConfiguration:
    """Build a proposal; caller validates it and atomically rechecks before commit.

    The runtime must match this to an outstanding camera/Setup command, acknowledge
    the adopted revision to acquisition, and only then let allocation/export resume.
    Device observation reports never call this function.
    """
    if (
        report.source != source
        or source.backend_name != "acquisition"
        or report.work != work
        or report.operation.command_id != operation_id
        or not report.HasField("requested_configuration_revision")
        or report.requested_configuration_revision != revision
        or report.HasField("pulses") != expect_pulses
    ):
        raise ProjectionError("resolution does not match the outstanding batch")
    entries = {entry.camera: entry.result for entry in report.cameras}
    if len(entries) != len(report.cameras) or entries.keys() != expected_cameras:
        raise ProjectionError("resolution camera set differs from the requested batch")
    if not expected_cameras <= {
        camera.CAMERA_ROLE_BEHAVIORAL,
        camera.CAMERA_ROLE_TRACKING,
    }:
        raise ProjectionError("resolution camera role is invalid")
    candidate = pb.ExperimentConfiguration.FromString(current.SerializeToString())
    backends = [
        entry for entry in candidate.backends if entry.backend_name == "acquisition"
    ]
    if len(backends) != 1 or backends[0].WhichOneof("settings") != "acquisition":
        raise ProjectionError("current acquisition configuration is ambiguous")
    settings = backends[0].acquisition
    roles = {
        camera.CAMERA_ROLE_BEHAVIORAL: settings.behavioral,
        camera.CAMERA_ROLE_TRACKING: settings.tracking,
    }
    physical_ids: set[str] = set()
    for role, resolved in entries.items():
        requested = roles[role].device
        if (
            not resolved.HasField("configuration_revision")
            or resolved.configuration_revision != revision
            or not requested.device_id
            or resolved.device.configured_id != requested.device_id
            or resolved.applied.device_id != requested.device_id
            or not resolved.device.physical_id
            or resolved.device.physical_id in physical_ids
            or not resolved.HasField("applied")
            or not resolved.HasField("capabilities")
            or not resolved.HasField("layout")
            or not resolved.HasField("transport")
        ):
            raise ProjectionError("camera readback identity/revision is incomplete")
        physical_ids.add(resolved.device.physical_id)
        roles[role].device.CopyFrom(resolved.applied)
    if expect_pulses:
        pulses = report.pulses
        if (
            not pulses.HasField("requested_configuration_revision")
            or pulses.requested_configuration_revision != revision
            or pulses.requested != settings.pulses
            or not pulses.HasField("behavioral_active")
            or not pulses.HasField("tracking_active")
            or not pulses.HasField("applied")
        ):
            raise ProjectionError("pulse readback cannot replace requested timing")
        # Applied firmware frequency is diagnostic evidence. Preserve requested
        # operator frequencies exactly; do not overwrite them with rounded readback.
    return candidate
