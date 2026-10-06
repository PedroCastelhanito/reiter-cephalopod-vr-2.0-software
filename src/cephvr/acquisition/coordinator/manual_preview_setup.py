"""Build one run-scoped preview setup from confirmed camera facts (A10)."""

from __future__ import annotations

from cephvr.acquisition.state import WorkerPreview
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.control.v1 import types_pb2 as control


def build_preview_payload(
    setting: camera.CameraSessionSettings,
    policy: runtime.CameraFilePolicy,
    resolved: camera.CameraResolvedState,
    attachment: acq.FrameBufferAttachment,
) -> acq.CameraWorkerSetupPayload:
    if not setting.HasField("sdk_buffer_count"):
        raise ValueError("manual preview requires a resolved SDK buffer count")
    if not policy.HasField("frame_silence_timeout_ns"):
        raise ValueError("manual preview requires a resolved capture silence timeout")
    payload = acq.CameraWorkerSetupPayload(
        device=resolved.applied,
        transport=resolved.transport,
        layout=resolved.layout,
        outputs=[attachment],
        native_timestamp_available=resolved.native_timestamp_available,
        native_counter_available=resolved.native_counter_available,
        camera_clock=resolved.camera_clock,
    )
    payload.capture.sdk_buffer_count = setting.sdk_buffer_count
    payload.capture.frame_silence_timeout_ns = policy.frame_silence_timeout_ns
    role = {
        camera.CAMERA_ROLE_BEHAVIORAL: "behavioral",
        camera.CAMERA_ROLE_TRACKING: "tracking",
    }.get(attachment.buffer.camera)
    if role is None:
        raise ValueError("manual preview requires an exact camera role")
    capture_id = f"{role}.capture"
    payload.owned_functions.add().CopyFrom(
        control.PreparedFunctionScope(
            resource_id=capture_id,
            owner=attachment.buffer.owner,
            authorized_reporters=[attachment.buffer.producer],
            lifecycle_sources=[role],
            affected_closure_resource_ids=[capture_id],
        )
    )
    return payload


def new_worker_preview(
    run_id: str,
    revision: int,
    attachment: acq.FrameBufferAttachment,
    resolved: camera.CameraResolvedState,
    output_bits: int,
) -> WorkerPreview:
    return WorkerPreview(
        run_id=run_id,
        configuration_revision=revision,
        allocation_id=attachment.buffer.allocation_id,
        preview_output_bit_depth=output_bits,
        resolved_camera=camera.CameraResolvedState.FromString(
            resolved.SerializeToString(deterministic=True)
        ),
        worker_attachment=acq.FrameBufferAttachment.FromString(
            attachment.SerializeToString(deterministic=True)
        ),
        attachment=acq.FrameBufferAttachment.FromString(
            attachment.SerializeToString(deterministic=True)
        ),
    )
