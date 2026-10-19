"""Pure E07/E12 validation; host settings and native readback belong to Setup."""

from __future__ import annotations

from cephvr.control.v1 import types_pb2 as pb


def validate_configuration(
    candidate: pb.ExperimentConfiguration,
) -> pb.ValidationResult:
    """Check pairing's typed envelope without reading files or contacting SpikeGLX."""
    result = pb.ValidationResult(
        completed=True,
        valid=True,
        component="synchronization",
        configuration_module_version="synchronization-config-v1",
    )
    selected = [
        backend
        for backend in candidate.backends
        if backend.backend_name == "synchronization"
    ]
    if len(selected) > 1:
        code, message = "DUPLICATE_BACKEND", "synchronization appears more than once"
    elif selected and selected[0].WhichOneof("settings") not in (
        None,
        "synchronization",
    ):
        code, message = "INVALID_SETTINGS", "synchronization settings kind mismatch"
    else:
        # E12 exposes only BackendSettings.enabled; the typed settings are empty.
        return result
    result.valid = False
    result.issues.add(
        component="synchronization",
        field_path="backends.synchronization",
        failure=pb.Failure(code=code, message=message),
    )
    return result
