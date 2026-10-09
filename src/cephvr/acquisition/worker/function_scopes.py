"""Validate the exact worker fault catalogue carried by resolved Setup (E06)."""

from __future__ import annotations

from collections.abc import Iterable

from cephvr.acquisition.identity import camera_role_name
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


def validate_camera_function_scopes(
    payload: acq.CameraWorkerSetupPayload,
    context: acq.WorkerContext,
) -> tuple[control.PreparedFunctionScope, ...]:
    """Check owner, reporter, role source and complete transitive closures."""
    if not context.HasField("owner") or not context.HasField("worker"):
        raise ValueError("camera worker context lacks exact owner or worker identity")
    role = camera_role_name(context.camera)
    if not role:
        raise ValueError("camera worker function catalogue has an unknown camera role")
    expected_capture = f"{role}.capture"
    expected_recording = f"{role}.recording"
    copied: list[control.PreparedFunctionScope] = []
    by_id: dict[str, control.PreparedFunctionScope] = {}
    for scope in payload.owned_functions:
        if not scope.resource_id or scope.resource_id in by_id:
            raise ValueError("worker function catalogue has an empty or duplicate key")
        if not scope.HasField("owner") or scope.owner != context.owner:
            raise ValueError("worker function scope has another logical owner")
        reporters = tuple(scope.authorized_reporters)
        if reporters != (context.worker,):
            raise ValueError("worker function scope lacks its exact sole reporter")
        closure = tuple(scope.affected_closure_resource_ids)
        if (
            not closure
            or len(set(closure)) != len(closure)
            or scope.resource_id not in closure
        ):
            raise ValueError("worker function scope has an invalid closure")
        saved = control.PreparedFunctionScope()
        saved.CopyFrom(scope)
        by_id[saved.resource_id] = saved
        copied.append(saved)
    if expected_capture not in by_id:
        raise ValueError("Setup function catalogue omits the camera capture scope")
    capture = by_id[expected_capture]
    if tuple(capture.lifecycle_sources) != (role,):
        raise ValueError("camera capture scope has a mismatched lifecycle source")
    saving = payload.HasField("recording")
    outputs = set(by_id).difference({expected_capture, expected_recording})
    if saving:
        if expected_recording not in by_id:
            raise ValueError("saving Setup omits the camera recording fault scope")
        recording = by_id[expected_recording]
        if recording.lifecycle_sources:
            raise ValueError("recording scope cannot claim camera lifecycle sources")
        expected_closure = {expected_recording, *outputs}
        if set(recording.affected_closure_resource_ids) != expected_closure:
            raise ValueError("recording fault scope does not close over its outputs")
        if set(capture.affected_closure_resource_ids) != {
            expected_capture,
            expected_recording,
            *outputs,
        }:
            raise ValueError("camera capture fault scope has an incomplete closure")
        for output_id in outputs:
            output = by_id[output_id]
            if output.lifecycle_sources or tuple(
                output.affected_closure_resource_ids
            ) != (output_id,):
                raise ValueError("output scope must close only over itself")
    elif expected_recording in by_id or outputs:
        raise ValueError("non-saving Setup includes recording output fault scopes")
    elif tuple(capture.affected_closure_resource_ids) != (expected_capture,):
        raise ValueError("non-saving capture scope must close only over itself")
    for scope in copied:
        if any(
            resource not in by_id for resource in scope.affected_closure_resource_ids
        ):
            raise ValueError("worker function closure references an undeclared key")
    return tuple(copied)


def recording_scope_resources(
    scopes: Iterable[control.PreparedFunctionScope], camera: int
) -> tuple[str, ...]:
    role = camera_role_name(camera)
    key = f"{role}.recording"
    for scope in scopes:
        if scope.resource_id == key:
            return tuple(scope.affected_closure_resource_ids)
    return ()
