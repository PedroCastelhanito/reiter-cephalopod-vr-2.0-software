"""Build the exact coordinator-owned fault scopes retained for a Setup session."""

from __future__ import annotations

from cephvr.acquisition.state import SessionRecord, WorkerRecord
from cephvr.control.v1 import types_pb2 as control


def role_prepared_functions(
    session: SessionRecord,
    role_name: str,
    worker: WorkerRecord,
    owner: control.ProcessIdentity,
) -> list[control.PreparedFunctionScope]:
    """Return identical Ready and worker-Setup declarations for one exact role."""
    if session.confirmed_settings is None:
        raise RuntimeError("Setup settings were not adopted")
    setting = getattr(session.confirmed_settings, role_name)
    output_prefix = f"{role_name}_cam"
    output_keys = sorted(
        output.output_key
        for output in session.reserved_outputs
        if output.output_tag in {output_prefix, f"{output_prefix}_frames"}
    )
    recording_key = (
        f"{role_name}.recording"
        if setting.HasField("save_video") and setting.save_video
        else None
    )
    capture_key = f"{role_name}.capture"
    capture_closure = [capture_key]
    if recording_key is not None:
        capture_closure.append(recording_key)
    capture_closure.extend(output_keys)

    scopes: list[control.PreparedFunctionScope] = []
    capture = control.PreparedFunctionScope(
        resource_id=capture_key,
        essential_to_stimulus_control=False,
        feedback_hold_required_on_loss=(
            role_name == "tracking" and session.tracking_required
        ),
        bounded_uncertainty_supported=False,
        lifecycle_sources=(role_name,),
    )
    capture.owner.CopyFrom(owner)
    capture.affected_closure_resource_ids.extend(capture_closure)
    capture.authorized_reporters.add().CopyFrom(worker.launch.worker)
    scopes.append(capture)

    if recording_key is not None:
        recording = control.PreparedFunctionScope(
            resource_id=recording_key,
            essential_to_stimulus_control=False,
            feedback_hold_required_on_loss=False,
            bounded_uncertainty_supported=False,
        )
        recording.owner.CopyFrom(owner)
        recording.affected_closure_resource_ids.extend([recording_key, *output_keys])
        recording.authorized_reporters.add().CopyFrom(worker.launch.worker)
        scopes.append(recording)

    for output_key in output_keys:
        output_scope = control.PreparedFunctionScope(
            resource_id=output_key,
            essential_to_stimulus_control=False,
            feedback_hold_required_on_loss=False,
            bounded_uncertainty_supported=False,
        )
        output_scope.owner.CopyFrom(owner)
        output_scope.affected_closure_resource_ids.append(output_key)
        output_scope.authorized_reporters.add().CopyFrom(worker.launch.worker)
        scopes.append(output_scope)
    return scopes
