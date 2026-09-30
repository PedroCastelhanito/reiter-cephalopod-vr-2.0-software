"""Worker-side camera resolution and edit/readback operations (A01/A10)."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.camera.types import PfsSnapshot
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq

from .camera_resolution import resolve_camera, resolve_imported_camera
from .function_scopes import validate_camera_function_scopes
from .state import WorkerState


class WorkerCameraConfiguration:
    """Retain only the accepted device-resolution result and its revision."""

    def __init__(
        self,
        adapter: BaslerCameraAdapter,
        state: WorkerState,
        manual_preview: Callable[[], bool],
    ) -> None:
        self.adapter = adapter
        self.state = state
        self.manual_preview = manual_preview
        self._resolved: camera.CameraResolvedState | None = None

    def resolve(self, request: acq.WorkerResolveCamera) -> camera.CameraResolvedState:
        resolved = resolve_camera(self.adapter, request)
        self._retain(resolved)
        return resolved

    def edit(
        self, request: acq.WorkerEditCamera, report: acq.WorkerOperationReport
    ) -> None:
        kind = request.kind
        if kind == acq.CAMERA_EDIT_KIND_APPLY_SETTINGS:
            if not request.HasField("requested"):
                raise ValueError("camera edit requires a complete requested device")
            self.adapter.open(request.requested.device_id)
            if request.requested.HasField("pfs_baseline"):
                self.adapter.apply_pfs_snapshot(
                    PfsSnapshot(request.requested.pfs_baseline.text)
                )
            resolved = acq.WorkerResolveCamera(
                configuration_revision=request.configuration_revision,
                requested=request.requested,
            )
            if request.HasField("transport"):
                resolved.transport.CopyFrom(request.transport)
            state = resolve_camera(self.adapter, resolved)
            report.resolved_camera.CopyFrom(state)
            self._retain(state)
        elif kind == acq.CAMERA_EDIT_KIND_IMPORT_PFS:
            if not request.HasField("path"):
                raise ValueError("PFS import requires a path")
            current = self._resolved
            if current is None:
                raise RuntimeError("PFS import requires an assigned resolved camera")
            self.adapter.import_pfs(request.path)
            imported = resolve_imported_camera(
                self.adapter, current.applied, request.configuration_revision
            )
            report.resolved_camera.CopyFrom(imported)
            self._retain(imported)
        elif kind == acq.CAMERA_EDIT_KIND_EXPORT_PFS:
            if not request.HasField("path"):
                raise ValueError("PFS export requires a destination path")
            self.adapter.export_pfs(request.path)
            report.exported_pfs_path = request.path
        elif kind == acq.CAMERA_EDIT_KIND_FINISH_EDITING:
            if not self.manual_preview():
                self.adapter.release_device()
        else:
            raise ValueError("camera edit kind is unspecified or unsupported")

    def require_adopted_setup(self, request: object) -> None:
        if not isinstance(request, acq.WorkerSetupSession):
            raise TypeError("session setup request has the wrong type")
        if not request.HasField("configuration_revision"):
            raise ValueError("session Setup requires a configuration revision")
        resolved = self._resolved
        if resolved is None or not resolved.HasField("configuration_revision"):
            raise RuntimeError("session Setup has no retained camera resolution")
        if request.configuration_revision != resolved.configuration_revision + 1:
            raise RuntimeError("session Setup is not the adopted camera revision")
        if not request.HasField("camera"):
            raise ValueError("session Setup lacks the accepted camera payload")
        payload = request.camera
        if (
            payload.device.SerializeToString(deterministic=True)
            != resolved.applied.SerializeToString(deterministic=True)
            or payload.transport.SerializeToString(deterministic=True)
            != resolved.transport.SerializeToString(deterministic=True)
            or payload.layout.SerializeToString(deterministic=True)
            != resolved.layout.SerializeToString(deterministic=True)
            or payload.native_timestamp_available != resolved.native_timestamp_available
            or payload.native_counter_available != resolved.native_counter_available
            or payload.camera_clock.SerializeToString(deterministic=True)
            != resolved.camera_clock.SerializeToString(deterministic=True)
        ):
            raise ValueError("session Setup differs from the retained camera result")
        self.install_owned_functions(payload)
        self.state.confirmed_configuration_revision = request.configuration_revision

    def install_owned_functions(self, payload: acq.CameraWorkerSetupPayload) -> None:
        scopes = validate_camera_function_scopes(payload, self.state.context)
        self.state.install_prepared_functions(scopes)

    def _retain(self, resolved: camera.CameraResolvedState) -> None:
        self._resolved = camera.CameraResolvedState.FromString(
            resolved.SerializeToString(deterministic=True)
        )
        if resolved.HasField("configuration_revision"):
            self.state.confirmed_configuration_revision = (
                resolved.configuration_revision
            )
