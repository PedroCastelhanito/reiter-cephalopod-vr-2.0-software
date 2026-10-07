"""Own detached camera preview readers and their exact attachment identities."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QWidget

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.camera_viewer import CameraViewer, PreviewReader
from cephvr.gui.cameras import CamerasPanel
from cephvr.gui.controller_bridge import ControllerBridge


class ManagedPreviewViewers(QObject):
    """Bind viewer windows to one controller snapshot and buffer attachment."""

    def __init__(
        self,
        parent: QWidget,
        bridge: ControllerBridge,
        snapshot: Callable[[], pb.Snapshot | None],
        on_change: Callable[[], None],
        cameras: CamerasPanel,
    ) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.snapshot = snapshot
        self.on_change = on_change
        self.cameras = cameras
        self.viewers: dict[
            int, tuple[CameraViewer, PreviewReader, acq.FrameBufferAttachment, str]
        ] = {}
        bridge.attachment_received.connect(self.attach)

    def disconnected(self) -> None:
        for viewer, _, _, _ in tuple(self.viewers.values()):
            viewer.close()

    def preview_visibility(self, key: str, visible: bool) -> None:
        role = self._role(key)
        if role is None:
            return
        if visible:
            current = self.viewers.get(role)
            if current is not None:
                current[0].show()
            else:
                self.bridge.request(
                    "camera",
                    role=role,
                    kind=rpc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
                )
        elif role in self.viewers:
            self.viewers[role][0].close()

    def viewer_state(self, role: int, running: bool, run_id: str) -> bool:
        current = self.viewers.get(role)
        if current is not None and (not running or run_id != current[3]):
            current[0].close()
            return False
        return current is not None and current[0].isVisible()

    def attach(self, role: int, raw: bytes, release_only: bool) -> None:
        attachment = acq.FrameBufferAttachment.FromString(raw)
        state = self.snapshot()
        if state is None:
            return
        device = (
            state.acquisition_devices.behavioral
            if role == 1
            else state.acquisition_devices.tracking
        )
        run_id = device.preview_run_id
        if release_only:
            self.bridge.request(
                "viewer_state",
                attachment=attachment,
                run_id=run_id,
                result=rpc.PREVIEW_CONSUMER_RESULT_RELEASED,
            )
            return
        settings = next(
            (
                entry.acquisition
                for entry in state.configuration_values.current.backends
                if entry.backend_name == "acquisition" and entry.enabled
            ),
            None,
        )
        bits = (
            settings.preview_output_bit_depth
            if settings is not None and settings.HasField("preview_output_bit_depth")
            else 8
        )
        reader = PreviewReader(attachment, bits, run_id)
        viewer = CameraViewer(
            reader, "Behavior camera" if role == 1 else "Tracking camera"
        )
        self.viewers[role] = (viewer, reader, attachment, run_id)
        reader.attached.connect(
            lambda: self.bridge.request(
                "viewer_state",
                attachment=attachment,
                run_id=run_id,
                result=rpc.PREVIEW_CONSUMER_RESULT_ATTACHED,
            )
        )
        reader.released.connect(
            lambda: self.bridge.request(
                "viewer_state",
                attachment=attachment,
                run_id=run_id,
                result=rpc.PREVIEW_CONSUMER_RESULT_RELEASED,
            )
        )
        reader.failed.connect(
            lambda message: self.bridge.command_finished.emit("viewer", False, message)
        )
        reader.failed.connect(
            lambda _message: self.bridge.request(
                "viewer_state",
                attachment=attachment,
                run_id=run_id,
                result=rpc.PREVIEW_CONSUMER_RESULT_FAILED,
            )
        )
        reader.finished.connect(lambda: self._finished(role, reader))
        reader.start()
        viewer.show()

    def _finished(self, role: int, reader: PreviewReader) -> None:
        current = self.viewers.get(role)
        if current is not None and current[1] is reader:
            self.viewers.pop(role)
            self.on_change()

    def _role(self, key: str) -> int | None:
        return next(
            (
                {"Behavior cam": 1, "Tracking cam": 2}.get(camera.role)
                for camera in self.cameras.drafts
                if camera.key == key
            ),
            None,
        )

    def shutdown(self) -> None:
        for viewer, reader, _, _ in tuple(self.viewers.values()):
            viewer.close()
            reader.wait(2000)
