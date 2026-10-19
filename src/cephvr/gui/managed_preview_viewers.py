"""Send window intents; acquisition owns camera readers and OpenCV windows."""

from __future__ import annotations

from collections.abc import Callable

from google.protobuf.message import DecodeError
from PyQt6.QtCore import QTimer

from cephvr.acquisition.identity import camera_role_name
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.camera_inventory import CAMERA_ROLES
from cephvr.gui.cameras import CamerasPanel


class ManagedPreviewViewers:
    def __init__(
        self,
        snapshot: Callable[[], pb.Snapshot | None],
        cameras: CamerasPanel,
        queue_camera: Callable[..., bool],
        placement: Callable[[str], bytes] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.cameras = cameras
        self.queue_camera = queue_camera
        self.placement = placement
        self._reported: dict[int, int] = {}
        self._layouts: dict[str, tuple[str, bytes]] = {}
        self.layout_timer = QTimer(cameras)
        self.layout_timer.setInterval(200)
        self.layout_timer.timeout.connect(self.relayout)
        self.layout_timer.start()

    def preview_visibility(self, key: str, visible: bool) -> None:
        role = next(
            (
                CAMERA_ROLES.get(camera.role)
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
                {"placement": self.placement(key)}
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

    def snap(self, key: str) -> None:
        if self.placement is None or not self.cameras.can_operate:
            return
        role = next(
            (
                CAMERA_ROLES.get(camera.role)
                for camera in self.cameras.drafts
                if camera.key == key
            ),
            None,
        )
        if role is None:
            return
        try:
            hint = rpc.PreviewWindowPlacement.FromString(self.placement(key))
            hint.update_existing_only = True
            hint.snap_to_grid = True
            if not self.queue_camera(
                role,
                rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
                placement=hint.SerializeToString(),
            ):
                self.cameras.console.appendPlainText(
                    "Preview snap was not sent: camera command pending or controller unavailable."
                )
        except Exception as exc:
            self.cameras.console.appendPlainText(f"Preview snap failed: {exc}")

    def relayout(self) -> None:
        """Submit changed display hints serially through ordinary command authority."""
        state = self.snapshot()
        if state is None or self.placement is None or not self.cameras.can_operate:
            return
        visible = {
            source.key for source in self.cameras.view.previews if source.visible
        }
        self._layouts = {
            key: value for key, value in self._layouts.items() if key in visible
        }
        for camera in self.cameras.drafts:
            role = CAMERA_ROLES.get(camera.role)
            if camera.key not in visible or role is None:
                continue
            device = getattr(state.acquisition_devices, camera_role_name(role))
            if not device.preview_running or not device.preview_visible:
                continue
            try:
                hint = rpc.PreviewWindowPlacement.FromString(self.placement(camera.key))
            except (DecodeError, ValueError, RuntimeError):
                continue
            hint.update_existing_only = True
            payload = hint.SerializeToString()
            identity = device.preview_run_id, payload
            if self._layouts.get(camera.key) == identity:
                continue
            if self.queue_camera(
                role, rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW, placement=payload
            ):
                self._layouts[camera.key] = identity
            return

    def viewer_state(self, role: int, running: bool, run_id: str) -> bool:
        state = self.snapshot()
        if state is None:
            return False
        device = getattr(state.acquisition_devices, camera_role_name(role))
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
        self._layouts.clear()
