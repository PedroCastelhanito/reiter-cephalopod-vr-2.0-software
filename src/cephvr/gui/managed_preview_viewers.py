"""Send window intents; acquisition owns camera readers and OpenCV windows."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.cameras import CamerasPanel


class ManagedPreviewViewers:
    def __init__(
        self,
        snapshot: Callable[[], pb.Snapshot | None],
        cameras: CamerasPanel,
        queue_camera: Callable[..., bool],
        placement: Callable[[], bytes] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.cameras = cameras
        self.queue_camera = queue_camera
        self.placement = placement
        self._reported: dict[int, int] = {}

    def preview_visibility(self, key: str, visible: bool) -> None:
        role = next(
            (
                {"Behavior cam": 1, "Tracking cam": 2}.get(camera.role)
                for camera in self.cameras.drafts
                if camera.key == key
            ),
            None,
        )
        if role is None:
            return
        kind = (
            rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
            if visible
            else rpc.CAMERA_COMMAND_KIND_HIDE_PREVIEW
        )
        try:
            options = (
                {"placement": self.placement()}
                if visible and self.placement is not None
                else {}
            )
        except Exception as exc:
            self.cameras.console.appendPlainText(
                f"Preview placement unavailable: {exc}"
            )
            return
        if not self.queue_camera(role, kind, **options):
            self.cameras.console.appendPlainText(
                "Preview was not sent: camera command pending or controller unavailable."
            )

    def viewer_state(self, role: int, running: bool, run_id: str) -> bool:
        state = self.snapshot()
        if state is None:
            return False
        device = (
            state.acquisition_devices.behavioral
            if role == 1
            else state.acquisition_devices.tracking
        )
        if device.preview_visibility_revision != self._reported.get(role):
            self._reported[role] = device.preview_visibility_revision
            if device.preview_failure:
                self.cameras.console.appendPlainText(
                    f"Camera preview: {device.preview_failure}"
                )
        return bool(
            running and run_id == device.preview_run_id and device.preview_visible
        )

    def disconnected(self) -> None:
        self._reported.clear()
