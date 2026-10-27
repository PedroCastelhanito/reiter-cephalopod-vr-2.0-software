"""Pure camera-view merging; authenticated source and byte budgets stay with the store."""

from math import isfinite

from cephvr.acquisition.identity import CAMERA_NAMES, camera_role_name
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.identity import require_uuid4
from cephvr.shared.preview_rates import valid_rates


def merge_devices(
    incoming: pb.AcquisitionDeviceViews,
    previous: pb.AcquisitionDeviceViews | None,
    *,
    session_id: str = "",
) -> pb.AcquisitionDeviceViews:
    adopted = pb.AcquisitionDeviceViews.FromString(incoming.SerializeToString())
    for name in CAMERA_NAMES:
        getattr(adopted, name).ClearField("acquisition_rate")
    if previous:
        for name in CAMERA_NAMES:
            prior, current = getattr(previous, name), getattr(adopted, name)
            rate = prior.acquisition_rate
            if prior.HasField("acquisition_rate") and (
                session_id
                and rate.acquisition_run_id == session_id
                and (
                    current.preview_run_id != session_id
                    or not current.device.configured_id
                    or current.device.configured_id == rate.device_id
                )
                or not session_id
                and current.device_open
                and current.preview_running
                and not current.cleanup_pending
                and current.preview_run_id == rate.acquisition_run_id
                and (
                    not current.device.configured_id
                    or current.device.configured_id == rate.device_id
                )
            ):
                current.acquisition_rate.CopyFrom(rate)
            if (
                current.preview_run_id == prior.preview_run_id
                and current.preview_visibility_revision
                < prior.preview_visibility_revision
            ):
                current.preview_visible = prior.preview_visible
                current.preview_visibility_revision = prior.preview_visibility_revision
                current.preview_failure = prior.preview_failure
                current.rates.CopyFrom(prior.rates)
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
        or report.HasField("camera_acquisition_rate")
        or observation.camera not in (1, 2, 3)
        or observation.revision == 0
        or observation.observed_monotonic_ns <= 0
        or previous is None
        or len(observation.failure.encode("utf-8")) > 2048
    ):
        raise ValueError("preview visibility observation shape is invalid")
    if (
        observation.HasField("rates")
        and observation.rates.ByteSize()
        and not valid_rates(
            observation.rates.source_fps
            if observation.rates.HasField("source_fps")
            else None,
            observation.rates.preview_fps
            if observation.rates.HasField("preview_fps")
            else None,
            observation.rates.observed_monotonic_ns,
        )
    ):
        raise ValueError("invalid preview rates")
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
        if (observation.visible, observation.failure, observation.rates) != (
            device.preview_visible,
            device.preview_failure,
            device.rates,
        ):
            raise ValueError("preview visibility revision changed payload")
        return None
    device.preview_visible = observation.visible
    device.preview_visibility_revision = observation.revision
    device.preview_failure = observation.failure
    device.ClearField("rates")
    if observation.visible:
        device.rates.CopyFrom(observation.rates)
    return adopted


def merge_camera_acquisition_rate(
    report: rpc.AcquisitionDeviceStatusReport,
    previous: pb.AcquisitionDeviceViews | None,
    *,
    session: pb.SessionContext | None,
    expected_device_id: str,
    ingress_ns: int,
    health_silence_ns: int,
) -> pb.AcquisitionDeviceViews | None:
    rate = report.camera_acquisition_rate
    if (
        report.HasField("operation")
        or report.HasField("result")
        or report.HasField("preview_visibility")
        or report.HasField("exported_pfs_path")
        or report.views != pb.AcquisitionDeviceViews(source=report.views.source)
        or rate.camera not in (1, 2, 3)
        or not expected_device_id
        or rate.device_id != expected_device_id
        or rate.observed_monotonic_ns <= 0
        or rate.valid_until_monotonic_ns
        != rate.observed_monotonic_ns + health_silence_ns
        or not rate.observed_monotonic_ns <= ingress_ns < rate.valid_until_monotonic_ns
        or not rate.HasField("received_fps")
        or not isfinite(rate.received_fps)
        or rate.received_fps < 0
    ):
        raise ValueError("camera acquisition-rate observation is invalid")
    require_uuid4(rate.acquisition_run_id)
    work_kind = report.work.WhichOneof("work")
    report_session = (
        report.work.session
        if work_kind == "session"
        else report.work.trial.session
        if work_kind == "trial"
        else None
    )
    if report_session is not None and report_session != session:
        raise ValueError("camera acquisition rate work differs from current session")
    adopted = (
        pb.AcquisitionDeviceViews.FromString(previous.SerializeToString())
        if previous is not None
        else pb.AcquisitionDeviceViews(source=report.views.source)
    )
    target = getattr(adopted, camera_role_name(rate.camera))
    if session is not None:
        if rate.acquisition_run_id != session.session_id:
            raise ValueError("camera acquisition rate targets another session")
    elif (
        target.preview_run_id != rate.acquisition_run_id
        or not target.device_open
        or not target.preview_running
        or target.cleanup_pending
    ):
        raise ValueError("camera acquisition rate targets a retired preview")
    if (
        (session is None or target.preview_run_id == session.session_id)
        and target.device.configured_id
        and target.device.configured_id != rate.device_id
    ):
        raise ValueError("camera acquisition rate device identity differs")
    prior = target.acquisition_rate
    if prior.acquisition_run_id == rate.acquisition_run_id:
        if prior.observed_monotonic_ns > rate.observed_monotonic_ns:
            return None
        if prior.observed_monotonic_ns == rate.observed_monotonic_ns:
            if prior != rate:
                raise ValueError("camera acquisition rate timestamp changed payload")
            return None
    target.acquisition_rate.CopyFrom(rate)
    return adopted
