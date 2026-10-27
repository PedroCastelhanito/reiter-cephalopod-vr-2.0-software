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
        workspace_visible: Callable[[], bool] = lambda: True,
    ) -> None:
        self.snapshot = snapshot
        self.cameras = cameras
        self.queue_camera = queue_camera
        self.placement = placement
        self.workspace_visible = workspace_visible
        self._reported: dict[int, int] = {}
        self._layouts: dict[str, tuple[str, bytes]] = {}
        self._suppression: dict[int, tuple[str, bool | None]] = {}
        self._pending_hides: dict[str, int] = {}
        self.layout_timer = QTimer(cameras)
        self.layout_timer.setInterval(200)
        self.layout_timer.timeout.connect(self.relayout)
        self.layout_timer.start()

    @property
    def can_operate(self) -> bool:
        return bool(
            not self.cameras.operation_pending
            and self.cameras.view.connected
            and self.cameras.view.has_control
        )

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
        if not visible:
            self._pending_hides[key] = role
            self._hide_next()
            return
        self._pending_hides.pop(key, None)
        kind = rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
        try:
            options = (
                {"placement": self.placement(key)} if self.placement is not None else {}
            )
        except Exception as exc:
            self.cameras.console.appendPlainText(
                f"Preview placement unavailable: {exc}"
            )
            return
        if not self.queue_camera(role, kind, **options):
            self.cameras.console.appendPlainText(
                "Preview request was not sent. Wait for the current camera action "
                "to finish and the controller to connect, then try again."
            )

    def snap(self, key: str) -> None:
        if self.placement is None or not self.can_operate:
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
                    "Preview position was not changed. Wait for the current camera "
                    "action to finish and the controller to connect, then try again."
                )
        except Exception as exc:
            self.cameras.console.appendPlainText(f"Preview snap failed: {exc}")

    def relayout(self) -> None:
        """Submit changed display hints serially through ordinary command authority."""
        if self._pending_hides:
            self._hide_next()
            return
        state = self.snapshot()
        if state is None or not self.can_operate:
            return
        if self._sync_workspace_visibility(state):
            return
        if self.placement is None or not self.workspace_visible():
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

    def workspace_changed(self) -> None:
        """Apply the current visible preview-slot state without changing Show state."""
        state = self.snapshot()
        if state is not None and self.can_operate:
            self._sync_workspace_visibility(state)

    def command_finished(self, action: str, success: bool, _message: str) -> None:
        if action == "camera" and not success:
            self._suppression = {
                role: (run_id, None)
                for role, (run_id, _suppressed) in self._suppression.items()
            }

    def _sync_workspace_visibility(self, state: pb.Snapshot) -> bool:
        if self.placement is None:
            return False
        workspace_visible = self.workspace_visible()
        active: dict[int, tuple[str, bool]] = {}
        for camera in self.cameras.drafts:
            role = CAMERA_ROLES.get(camera.role)
            if role is None:
                continue
            device = getattr(state.acquisition_devices, camera_role_name(role))
            if not (
                device.preview_running
                and device.preview_visible
                and device.preview_run_id
            ):
                continue
            suppressed = not workspace_visible
            identity = device.preview_run_id, suppressed
            active[role] = identity
            applied = self._suppression.get(role)
            if applied is not None and applied[0] != device.preview_run_id:
                applied = None
                if not suppressed:
                    self._suppression[role] = identity
                    continue
            if applied is None and role not in self._suppression and not suppressed:
                # New viewers start visible; failures retain an explicit unknown state.
                self._suppression[role] = identity
                continue
            if applied == identity:
                continue
            try:
                hint = rpc.PreviewWindowPlacement.FromString(self.placement(camera.key))
            except (DecodeError, ValueError, RuntimeError):
                continue
            hint.update_existing_only = True
            hint.camera_display_suppressed = suppressed
            if self.queue_camera(
                role,
                rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
                placement=hint.SerializeToString(),
            ):
                self._suppression[role] = identity
            return True
        self._suppression = {
            role: identity
            for role, identity in self._suppression.items()
            if active.get(role) is not None and active[role][0] == identity[0]
        }
        return False

    def _hide_next(self) -> None:
        """Close requests take priority over layout; cameras share one command slot."""
        if not self.can_operate or not self._pending_hides:
            return
        key, role = next(iter(self._pending_hides.items()))
        if self.queue_camera(role, rpc.CAMERA_COMMAND_KIND_HIDE_PREVIEW):
            del self._pending_hides[key]

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
        self._suppression.clear()
        self._pending_hides.clear()
