"""Controller-backed camera intent and snapshot projection (A10/G01)."""

from collections.abc import Callable

from PyQt6.QtCore import QObject

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.cameras import CamerasPanel
from cephvr.gui.controller_bridge import ControllerBridge
from cephvr.gui.view import PreviewView

_CAMERAS = {"Behavior cam": 1, "Tracking cam": 2}


class ManagedCameras(QObject):
    """Keep inventory/configuration views distinct from confirmed capture state."""

    def __init__(
        self,
        panel: CamerasPanel,
        bridge: ControllerBridge,
        viewer_state: Callable[[int, bool, str], bool],
        preview_placement: Callable[[], bytes] | None = None,
    ) -> None:
        super().__init__(panel)
        self.panel = panel
        self.bridge = bridge
        self.viewer_state = viewer_state
        self.preview_placement = preview_placement
        self._camera_revision = -1
        self.pending = ""
        self.configured_tests: list[tuple[int, str]] = []
        panel.connection_requested.connect(self.camera_connection)
        panel.enable_requested.connect(self.set_camera_enabled)
        panel.settings_requested.connect(self.save_camera_settings)
        panel.preset_import_requested.connect(self.import_preset)
        panel.role_requested.connect(self.assign_role)
        panel.test_requested.connect(self.test_enabled)

    def role(self, key: str) -> int | None:
        return next(
            (
                _CAMERAS.get(draft.role)
                for draft in self.panel.drafts
                if draft.key == key
            ),
            None,
        )

    def queue(self, action: str, **options: object) -> bool:
        if self.pending or not self.bridge.request(action, **options):
            return False
        self.pending = action
        self.panel.operation_pending = True
        self.panel.refresh_controls()
        return True

    def finished(self, action: str, success: bool, message: str) -> None:
        if action != self.pending:
            return
        self.pending = ""
        self.panel.operation_pending = False
        self.panel.pending_enable.clear()
        self.panel.console.appendPlainText(f"{action}: {message}")
        self.panel.refresh_controls()

    def disconnected(self) -> None:
        self._camera_revision = -1
        self.pending = ""
        self.panel.operation_pending = False
        self.panel.pending_enable.clear()
        self.configured_tests.clear()
        self.panel.has_configured_tests = False

    def test_enabled(self) -> None:
        if self.configured_tests:
            self.queue("test_cameras", cameras=list(self.configured_tests))

    def assign_role(self, serial: str, role: str) -> None:
        if not self.queue("assign_camera_role", serial=serial, role=role):
            self.panel.console.appendPlainText(
                "Role was not sent: controller unavailable or busy."
            )

    def install(self, state: pb.Snapshot) -> tuple[PreviewView, ...]:
        cameras = self.panel
        current = state.configuration_values.current
        mcu_settings = next(
            (
                entry.acquisition
                for entry in current.backends
                if entry.backend_name == "acquisition"
            ),
            None,
        )
        camera_settings = next(
            (
                entry.acquisition
                for entry in current.backends
                if entry.backend_name == "acquisition" and entry.enabled
            ),
            None,
        )
        self.configured_tests = (
            [
                (role, setting.device.device_id)
                for role, setting in (
                    (1, camera_settings.behavioral),
                    (2, camera_settings.tracking),
                )
                if setting.enabled and setting.device.device_id
            ]
            if camera_settings is not None
            else []
        )
        cameras.has_configured_tests = bool(self.configured_tests)
        camera_config_changed = state.configuration.revision != self._camera_revision
        draft_changed = camera_config_changed
        selected_config_changed = camera_config_changed
        if mcu_settings is not None and not cameras.snapshot_draft:
            assignments = {
                mcu_settings.behavioral.device.device_id: "Behavior cam",
                mcu_settings.tracking.device.device_id: "Tracking cam",
            }
            for draft in cameras.drafts:
                expected_role = assignments.get(draft.serial, "Unassigned")
                role_changed = draft.role != expected_role
                draft_changed = draft_changed or role_changed
                if role_changed:
                    draft.role = expected_role
                    if draft is cameras.selected:
                        selected_config_changed = True
                    row = cameras.drafts.index(draft)
                    item = cameras.table.item(row, 2)
                    if item is not None:
                        item.setText(expected_role)
                if expected_role in _CAMERAS and (
                    camera_config_changed or role_changed
                ):
                    assigned_camera = (
                        mcu_settings.behavioral
                        if expected_role == "Behavior cam"
                        else mcu_settings.tracking
                    )
                    timing = assigned_camera.device.frame_timing
                    draft.values["trigger_clock"] = (
                        "External controller"
                        if timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
                        else "Internal clock"
                        if timing == camera.FRAME_TIMING_FREE_RUNNING
                        else ""
                    )
                    draft.values["trigger_source"] = (
                        assigned_camera.device.settings.trigger_source
                        if assigned_camera.device.settings.HasField("trigger_source")
                        else ""
                    )
                    draft.values["pfs_imported"] = (
                        "yes"
                        if assigned_camera.device.HasField("pfs_baseline")
                        else "no"
                    )
                    draft.values["preset"] = (
                        assigned_camera.device.pfs_source_filename
                        if assigned_camera.device.HasField("pfs_source_filename")
                        else ""
                    )
                    pulse = (
                        mcu_settings.pulses.behavioral
                        if expected_role == "Behavior cam"
                        else mcu_settings.pulses.tracking
                    )
                    if pulse.HasField("requested_frequency_hz"):
                        draft.values["trigger_frequency_hz"] = (
                            f"{pulse.requested_frequency_hz:g}"
                        )
                    else:
                        draft.values.pop("trigger_frequency_hz", None)
        self._camera_revision = state.configuration.revision
        if selected_config_changed and not cameras.snapshot_draft:
            cameras.load_selected()
        preview_views: list[PreviewView] = []
        for draft in cameras.drafts:
            role = _CAMERAS.get(draft.role)
            if role is None:
                continue
            configured = (
                (camera_settings.behavioral if role == 1 else camera_settings.tracking)
                if camera_settings is not None
                else None
            )
            assigned = bool(configured and configured.device.device_id == draft.serial)
            if not cameras.snapshot_draft:
                draft.enabled = bool(assigned and configured and configured.enabled)
            if cameras.pending_enable.get(draft.serial) == draft.enabled:
                cameras.pending_enable.pop(draft.serial, None)
            device = (
                state.acquisition_devices.behavioral
                if role == 1
                else state.acquisition_devices.tracking
            )
            if cameras.snapshot_draft and mcu_settings is not None:
                reported = next(
                    (
                        view
                        for settings, view in (
                            (
                                mcu_settings.behavioral,
                                state.acquisition_devices.behavioral,
                            ),
                            (mcu_settings.tracking, state.acquisition_devices.tracking),
                        )
                        if settings.device.device_id == draft.serial
                    ),
                    None,
                )
                draft.connected = bool(
                    reported and (reported.device_open or reported.cleanup_pending)
                )
                draft.capture_running = bool(reported and reported.preview_running)
            else:
                draft.connected = bool(
                    assigned and (device.device_open or device.cleanup_pending)
                )
                draft.capture_running = bool(assigned and device.preview_running)
            visible = self.viewer_state(
                role, device.preview_running, device.preview_run_id
            )
            preview_views.append(
                PreviewView(
                    draft.key,
                    draft.role,
                    visible=visible,
                    available=assigned and bool(device.preview_running),
                    active=assigned and draft.enabled,
                    reason="Assign this camera in controller configuration"
                    if not assigned
                    else "",
                )
            )
        if draft_changed and not cameras.snapshot_draft:
            cameras.drafts_changed.emit()
        return tuple(preview_views)

    def discard_snapshot_draft(self, state: pb.Snapshot) -> None:
        """Explicit controller reload restores camera configuration before Tracking."""
        self.panel.snapshot_draft = False
        self._camera_revision = -1
        self.install(state)

    def camera_connection(self, key: str, start: bool) -> None:
        if start and self.panel.snapshot_draft:
            self.panel.console.appendPlainText(
                "Submit the loaded GUI camera draft before starting capture."
            )
            return
        role = self.role(key)
        if role is None:
            return
        draft = next(draft for draft in self.panel.drafts if draft.key == key)
        if (
            start
            and draft.values.get("preset")
            and draft.values.get("pfs_imported") != "yes"
        ):
            self.panel.console.appendPlainText(
                "Select the PFS file to import it through the camera SDK before starting capture."
            )
            return
        options: dict[str, object] = {}
        if start:
            options["show_preview"] = True
            if self.preview_placement is not None:
                try:
                    options["placement"] = self.preview_placement()
                except Exception as exc:
                    self.panel.console.appendPlainText(
                        f"Preview placement unavailable: {exc}"
                    )
                    return
        self.queue(
            "camera",
            role=role,
            kind=rpc.CAMERA_COMMAND_KIND_START_PREVIEW
            if start
            else rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW
            if any(
                draft.key == key and draft.capture_running
                for draft in self.panel.drafts
            )
            else rpc.CAMERA_COMMAND_KIND_FINISH_EDITING,
            **options,
        )

    def set_camera_enabled(self, serial: str, enabled: bool) -> None:
        if not self.queue("set_camera_enabled", serial=serial, enabled=enabled):
            cameras = self.panel
            cameras.pending_enable.pop(serial, None)
            cameras.refresh_controls()
            cameras.console.appendPlainText(
                "Camera setting was not sent; controller connection is unavailable."
            )

    def import_preset(
        self, serial: str, clock: str, source: str, preset: str, rate: str
    ) -> None:
        self.save_camera_settings(
            serial, clock, source, preset, rate, import_preset=True
        )

    def save_camera_settings(
        self,
        serial: str,
        clock: str,
        source: str,
        preset: str,
        rate: str,
        *,
        import_preset: bool = False,
    ) -> None:
        if not self.queue(
            "save_camera_settings",
            import_preset=import_preset,
            serial=serial,
            clock=clock,
            source=source,
            preset=preset,
            rate=rate,
        ):
            self.panel.console.appendPlainText(
                "Camera settings were not sent; controller connection is unavailable."
            )
