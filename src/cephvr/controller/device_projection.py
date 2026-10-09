"""Pure camera-view merging; authenticated source and byte budgets stay with the store."""

from cephvr.acquisition.identity import CAMERA_NAMES, camera_role_name
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb


def merge_devices(
    incoming: pb.AcquisitionDeviceViews, previous: pb.AcquisitionDeviceViews | None
) -> pb.AcquisitionDeviceViews:
    adopted = pb.AcquisitionDeviceViews.FromString(incoming.SerializeToString())
    if previous:
        for name in CAMERA_NAMES:
            prior, current = getattr(previous, name), getattr(adopted, name)
            if (
                current.preview_run_id == prior.preview_run_id
                and current.preview_visibility_revision
                < prior.preview_visibility_revision
            ):
                current.preview_visible = prior.preview_visible
                current.preview_visibility_revision = prior.preview_visibility_revision
                current.preview_failure = prior.preview_failure
    return adopted


def merge_preview_visibility(
    report: rpc.AcquisitionDeviceStatusReport,
    previous: pb.AcquisitionDeviceViews | None,
) -> pb.AcquisitionDeviceViews | None:
    observation = report.preview_visibility
    if (
        report.HasField("operation")
        or report.HasField("result")
        or report.HasField("work")
        or report.HasField("exported_pfs_path")
        or observation.camera not in (1, 2, 3)
        or observation.revision == 0
        or observation.observed_monotonic_ns <= 0
        or previous is None
        or len(observation.failure.encode("utf-8")) > 2048
    ):
        raise ValueError("preview visibility observation shape is invalid")
    adopted = pb.AcquisitionDeviceViews.FromString(previous.SerializeToString())
    device = getattr(adopted, camera_role_name(observation.camera))
    if (
        device.preview_run_id != observation.preview_run_id
        or not device.preview_running
    ):
        raise ValueError("preview visibility targets a retired camera run")
    if observation.revision < device.preview_visibility_revision:
        return None
    if observation.revision == device.preview_visibility_revision:
        if (observation.visible, observation.failure) != (
            device.preview_visible,
            device.preview_failure,
        ):
            raise ValueError("preview visibility revision changed payload")
        return None
    device.preview_visible = observation.visible
    device.preview_visibility_revision = observation.revision
    device.preview_failure = observation.failure
    return adopted
