"""Validation for the accepted Setup request and its active camera roles."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    SessionRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control


def validate_setup_request(
    request: wire.SetupSessionRequest,
    deadline_ns: int,
    *,
    identity: CoordinatorIdentity,
    configuration: ConfigurationRecord,
    clock: Callable[[], int],
) -> SessionRecord:
    command = request.command
    if clock() >= deadline_ns:
        raise TimeoutError("acquisition Setup deadline expired before admission")
    if (
        not command.command_id
        or command.issuer != identity.controller
        or command.target != identity.backend
        or command.work.WhichOneof("work") != "session"
        or not request.plan.HasField("context")
        or request.plan.context != command.work.session
        or request.settings.backend_name != "acquisition"
        or not request.settings.enabled
        or request.settings.WhichOneof("settings") != "acquisition"
        or not request.HasField("acquisition_policies")
        or not request.acquisition_policies.HasField("contract_version")
    ):
        raise ValueError(
            "acquisition Setup request differs from accepted identity/configuration"
        )
    settings = request.settings.acquisition
    if (
        request.acquisition_policies.contract_version
        != configuration.file_policies.contract_version
    ):
        raise ValueError("acquisition file policy version differs from loaded policy")
    active = enabled_cameras_from_settings(settings)
    if camera.CAMERA_ROLE_EYE_TRACKING in active:
        raise ValueError(
            "Eye tracking capture requires wired external triggering; "
            "source, rate and controller integration remain pending"
        )
    if not active:
        raise ValueError("acquisition Setup requires at least one enabled camera")
    tracking_required = tracking_backend_enabled(request.plan)
    if tracking_required and camera.CAMERA_ROLE_TRACKING not in active:
        raise ValueError("enabled tracking backend requires the tracking camera")
    reserved_outputs = _acquisition_outputs(request, identity)
    return SessionRecord(
        work=control.WorkContext(session=command.work.session),
        operation=control.OperationContext(command_id=command.command_id),
        configuration_revision=request.plan.configuration_revision,
        required_cameras=active,
        requested_configuration_revision=request.plan.configuration_revision,
        reserved_outputs=reserved_outputs,
        tracking_required=tracking_required,
        setup_deadline_ns=deadline_ns,
    )


def _acquisition_outputs(
    request: wire.SetupSessionRequest, identity: CoordinatorIdentity
) -> list[control.OutputPlan]:
    settings = request.settings.acquisition
    cameras = {
        "behavioral": settings.behavioral,
        "tracking": settings.tracking,
        "eye_tracking": settings.eye_tracking,
    }
    saved: list[control.OutputPlan] = []
    keys: set[str] = set()
    for output in request.plan.outputs:
        if output.backend.backend_name != "acquisition":
            continue
        if (
            output.backend != identity.backend
            or not output.output_key
            or output.output_key in keys
            or not output.output_tag
            or not output.extension
            or not output.HasField("trial")
            or output.trial.session != request.plan.context
            or output.HasField("path")
        ):
            raise ValueError("Setup acquisition output reservation is malformed")
        keys.add(output.output_key)
        role = next(
            (
                name
                for name in cameras
                if output.output_tag in {f"{name}_cam", f"{name}_cam_frames"}
            ),
            None,
        )
        if role is None:
            raise ValueError("Setup contains an unsupported acquisition output tag")
        setting = cameras[role]
        if not (
            setting.HasField("enabled")
            and setting.enabled
            and setting.HasField("save_video")
            and setting.save_video
        ):
            raise ValueError("Setup reserves output for an inactive camera writer")
        expected_extension = "mp4" if output.output_tag.endswith("_cam") else "jsonl"
        expected_key = f"{output.trial.trial_id}:acquisition:{output.output_tag}"
        if output.extension != expected_extension or output.output_key != expected_key:
            raise ValueError("Setup acquisition output identity differs from E04")
        saved.append(control.OutputPlan.FromString(output.SerializeToString()))
    if request.plan.trials:
        expected = {
            f"{trial.context.trial_id}:acquisition:{tag}"
            for trial in request.plan.trials
            for role, setting in cameras.items()
            if setting.HasField("enabled")
            and setting.enabled
            and setting.HasField("save_video")
            and setting.save_video
            for tag in (f"{role}_cam", f"{role}_cam_frames")
        }
        if keys != expected:
            raise ValueError(
                "Setup output reservations differ from resolved saving roles"
            )
    return saved


def enabled_cameras_from_settings(settings: control.AcquisitionSettings) -> set[int]:
    return {
        role
        for role, item in (
            (camera.CAMERA_ROLE_BEHAVIORAL, settings.behavioral),
            (camera.CAMERA_ROLE_TRACKING, settings.tracking),
            (camera.CAMERA_ROLE_EYE_TRACKING, settings.eye_tracking),
        )
        if item.HasField("enabled") and item.enabled
    }


def tracking_backend_enabled(plan: control.PreparedSession) -> bool:
    return any(
        item.backend_name == "tracking" and item.enabled
        for item in plan.configuration.backends
    )
