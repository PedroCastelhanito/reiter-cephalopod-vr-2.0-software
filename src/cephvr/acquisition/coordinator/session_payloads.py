"""Build and dispatch locked camera-worker Setup payloads."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable

from cephvr.acquisition.coordinator.commands import retain_worker_command
from cephvr.acquisition.coordinator.prepared_functions import role_prepared_functions
from cephvr.acquisition.coordinator.session_resources import allocate_camera_outputs
from cephvr.acquisition.ports import ControllerPort, ResourcePort
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    ResourceRecord,
    SessionRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger


async def prepare_worker_payloads(
    session: SessionRecord,
    request: wire.SetupSessionRequest,
    records: tuple[WorkerRecord, ...],
    deadline_ns: int,
    *,
    identity: CoordinatorIdentity,
    configuration: ConfigurationRecord,
    resources: dict[str, ResourceRecord],
    resource_ledger: NativeResourceLedger,
    resource_port: ResourcePort,
    controller: ControllerPort,
    session_config_reference: Callable[[wire.SetupSessionRequest], str],
    is_live: Callable[[], bool],
    clock: Callable[[], int],
    declare_resource: Callable[[control.ProcessIdentity, str], Awaitable[None]],
) -> None:
    if session.confirmed_settings is None or session.confirmed_revision is None:
        raise RuntimeError("controller configuration adoption is missing")
    if not is_live():
        raise RuntimeError("Setup was cancelled before output allocation")
    physical_ids = [
        session.camera_resolutions[role].device.physical_id
        for role in session.required_cameras
        if role in session.camera_resolutions
    ]
    if len(physical_ids) != len(session.required_cameras) or any(
        not physical_id for physical_id in physical_ids
    ):
        raise ValueError("Setup camera readback is missing a physical device identity")
    if len(set(physical_ids)) != len(physical_ids):
        raise ValueError("two enabled camera roles resolve to the same physical device")
    tracking_input: acq.FrameBufferAttachment | None = None
    payloads: list[tuple[WorkerRecord, acq.WorkerSetupSession]] = []
    from cephvr.acquisition.coordinator.recording_payload import (
        build_recording_settings,
    )

    session.prepared_functions = {
        worker.context.camera: role_prepared_functions(
            session,
            role_name(worker.context.camera),
            worker,
            identity.process,
        )
        for worker in records
    }

    for worker in records:
        role = worker.context.camera
        resolved = session.camera_resolutions.get(role)
        if resolved is None:
            raise RuntimeError(f"camera role {role} has no accepted readback")
        file_policy = camera_policy(configuration.file_policies, role)
        validate_post_cutoff_margin(
            file_policy,
            resolved,
            nominal_frame_rate(
                role,
                getattr(session.confirmed_settings, role_name(role)),
                resolved,
                session.pulse_resolution,
            ),
            role,
        )
        outputs, tracking = await allocate_camera_outputs(
            session=session,
            worker=worker,
            resolved=resolved,
            tracking_consumer=identity.tracking,
            tracking_required=session.tracking_required,
            settings=session.confirmed_settings,
            resources=resources,
            ledger=resource_ledger,
            port=resource_port,
            declare_resource=declare_resource,
        )
        if tracking is not None:
            if tracking_input is not None:
                raise RuntimeError("Setup allocated more than one tracking ring")
            tracking_input = tracking
        camera_setup = acq.CameraWorkerSetupPayload()
        setting = getattr(session.confirmed_settings, role_name(role))
        camera_setup.device.CopyFrom(setting.device)
        camera_setup.transport.CopyFrom(file_policy.transport)
        camera_setup.layout.CopyFrom(resolved.layout)
        if not setting.HasField("sdk_buffer_count"):
            raise ValueError(f"camera role {role} has no resolved SDK buffer count")
        camera_setup.capture.sdk_buffer_count = setting.sdk_buffer_count
        if not file_policy.HasField("frame_silence_timeout_ns"):
            raise ValueError(
                f"camera role {role} has no resolved frame-silence timeout"
            )
        camera_setup.capture.frame_silence_timeout_ns = (
            file_policy.frame_silence_timeout_ns
        )
        if session.confirmed_settings.HasField("session_preview_max_hz"):
            camera_setup.capture.session_preview_max_hz = (
                session.confirmed_settings.session_preview_max_hz
            )
        camera_setup.native_timestamp_available = resolved.native_timestamp_available
        camera_setup.native_counter_available = resolved.native_counter_available
        camera_setup.camera_clock.CopyFrom(resolved.camera_clock)
        recording = build_recording_settings(
            session.confirmed_settings,
            resolved,
            configuration.file_policies,
            role,
            session_config_reference=session_config_reference(request),
            nominal_frame_rate_hz=nominal_frame_rate(
                role, setting, resolved, session.pulse_resolution
            ),
        )
        if recording is not None:
            camera_setup.recording.CopyFrom(recording)
            if (
                setting.device.HasField("frame_timing")
                and setting.device.frame_timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
            ):
                if session.pulse_resolution is None:
                    raise ValueError(
                        "external-trigger recording has no applied pulse configuration"
                    )
                camera_setup.pulse_configuration.CopyFrom(
                    session.pulse_resolution.applied
                )
        camera_setup.outputs.extend(outputs)
        camera_setup.owned_functions.extend(session.prepared_functions.get(role, ()))
        child, operation, _port = retain_worker_command(
            worker,
            work=session.work,
            parent_operation=session.operation,
            kind="setup_session",
            deadline_ns=deadline_ns,
            configuration_revision=session.confirmed_revision,
            requested_device_id=setting.device.device_id,
        )
        worker.setup_operation = control.OperationContext(
            command_id=operation.command_id
        )
        payloads.append(
            (
                worker,
                acq.WorkerSetupSession(
                    command=child,
                    camera=camera_setup,
                    configuration_revision=session.confirmed_revision,
                ),
            )
        )
    if tracking_input is not None:
        data = wire.DataPreparationReport(
            source=control.ReportContext(
                backend=identity.backend,
                work=session.work,
                operation=session.operation,
            ),
            configuration_revision=session.confirmed_revision,
            report_revision=1,
            tracking_input=tracking_input,
        )
        retained = wire.DataPreparationReport()
        retained.CopyFrom(data)
        session.tracking_input_report = retained
        receipt = await controller.report_data_preparation(
            data, deadline_ns=deadline_ns
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("controller rejected acquisition tracking input")
        remaining = max(0, deadline_ns - clock()) / 1_000_000_000
        if remaining <= 0:
            raise TimeoutError("tracking input confirmation missed Setup deadline")
        await asyncio.wait_for(session.tracking_input_confirmed.wait(), remaining)
        if not is_live():
            raise RuntimeError(
                "Setup was cancelled before tracking attachment adoption"
            )
    if not is_live():
        raise RuntimeError("Setup was cancelled before worker Setup dispatch")
    results = await asyncio.gather(
        *(
            worker.port.setup_session(payload, deadline_ns=deadline_ns)
            for worker, payload in payloads
            if worker.port is not None
        )
    )
    if len(results) != len(payloads) or any(
        item.result != control.COMMAND_RESULT_ACCEPTED for item in results
    ):
        raise RuntimeError("one or more camera worker Setup commands were rejected")


def camera_policy(
    policies: runtime.AcquisitionFilePolicies, role: int
) -> runtime.CameraFilePolicy:
    matches = [item for item in policies.cameras if item.camera == role]
    if len(matches) != 1:
        raise ValueError(f"acquisition file policy for camera {role} is not unique")
    result = runtime.CameraFilePolicy()
    result.CopyFrom(matches[0])
    return result


def role_name(role: int) -> str:
    if role == camera.CAMERA_ROLE_BEHAVIORAL:
        return "behavioral"
    if role == camera.CAMERA_ROLE_TRACKING:
        return "tracking"
    raise ValueError(f"unsupported acquisition camera role {role}")


def nominal_frame_rate(
    role: int,
    settings: camera.CameraSessionSettings,
    resolved: camera.CameraResolvedState,
    pulse_resolution: mcu.PulseConfigurationResolution | None,
) -> float:
    if (
        settings.device.HasField("frame_timing")
        and settings.device.frame_timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
    ):
        if pulse_resolution is None:
            return 0.0
        output = (
            pulse_resolution.applied.state.behavioral
            if role == camera.CAMERA_ROLE_BEHAVIORAL
            else pulse_resolution.applied.state.tracking
        )
        if output.HasField("applied_frequency_hz") and output.applied_frequency_hz > 0:
            return float(output.applied_frequency_hz)
        return 0.0
    actual = resolved.applied.settings
    if actual.HasField("frame_rate_hz") and actual.frame_rate_hz > 0:
        return float(actual.frame_rate_hz)
    return 0.0


def validate_post_cutoff_margin(
    policy: runtime.CameraFilePolicy,
    resolved: camera.CameraResolvedState,
    frame_rate_hz: float,
    role: int,
) -> None:
    """Require the declared drain margin to cover the known exposure and frame."""
    settings = resolved.applied.settings
    if (
        not policy.HasField("post_cutoff_drain_margin_ns")
        or policy.post_cutoff_drain_margin_ns <= 0
        or not settings.HasField("exposure_us")
        or not math.isfinite(settings.exposure_us)
        or settings.exposure_us <= 0
        or not math.isfinite(frame_rate_hz)
        or frame_rate_hz <= 0
    ):
        raise ValueError(
            f"camera role {role} needs confirmed exposure/rate and drain policy"
        )
    required_ns = math.ceil(settings.exposure_us * 1000) + math.ceil(
        1_000_000_000 / frame_rate_hz
    )
    if policy.post_cutoff_drain_margin_ns < required_ns:
        raise ValueError(
            f"camera role {role} post-cutoff drain margin is below exposure plus one frame"
        )
