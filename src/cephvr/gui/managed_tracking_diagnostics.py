"""Exact-scope GUI orchestration for pre-experiment Tracking diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QWidget

from cephvr.client.session import ClientError
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.controller_bridge import ControllerBridge
from cephvr.gui.tracking import TrackingPage
from cephvr.gui.tracking_live import (
    TrackingDiagnosticPresentation,
    TrackingDiagnosticViewer,
    tracking_diagnostic_presentation,
)
from cephvr.tracking.v1 import services_pb2 as tracking_rpc


def begin_request_options(
    snapshot: pb.Snapshot,
    settings: pb.TrackingSettings,
    selected_stages: tuple[int, ...],
) -> dict[str, object]:
    """Freeze the accepted camera preview identity with the local draft."""
    revision = snapshot.configuration.revision
    if (
        not snapshot.HasField("configuration_values")
        or snapshot.configuration_values.revision != revision
        or not snapshot.HasField("acquisition_devices")
        or not snapshot.acquisition_devices.tracking.preview_running
        or not snapshot.acquisition_devices.tracking.preview_run_id
        or snapshot.acquisition_devices.tracking.applied_configuration_revision
        != revision
    ):
        raise ClientError(
            "Start the assigned Tracking camera preview at the accepted configuration first."
        )
    known = {
        tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_POSE,
        tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
        tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
        tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
        tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION,
    }
    if (
        len(set(selected_stages)) != len(selected_stages)
        or not set(selected_stages) <= known
    ):
        raise ClientError("Select valid Tracking diagnostic stages.")
    return {
        "expected_revision": revision,
        "preview_run_id": snapshot.acquisition_devices.tracking.preview_run_id,
        "selected_stages": selected_stages,
        "diagnostic_settings": settings.SerializeToString(deterministic=True),
    }


def close_request_options(snapshot: pb.Snapshot) -> dict[str, object]:
    if (
        not snapshot.HasField("tracking_diagnostic")
        or not snapshot.tracking_diagnostic.diagnostic_id
        or not snapshot.tracking_diagnostic.preview_run_id
        or snapshot.tracking_diagnostic.configuration_revision
        != snapshot.configuration.revision
    ):
        raise ClientError("No current Tracking diagnostic is available to close.")
    diagnostic = snapshot.tracking_diagnostic
    return {
        "expected_revision": diagnostic.configuration_revision,
        "diagnostic_id": diagnostic.diagnostic_id,
        "preview_run_id": diagnostic.preview_run_id,
    }


class ManagedTrackingDiagnostics(QObject):
    """Own one viewer and coalesce read-only frame polling for the active diagnostic."""

    def __init__(
        self,
        parent: QWidget,
        bridge: ControllerBridge,
        page: TrackingPage,
        snapshot: Callable[[], pb.Snapshot | None],
        asset_root: Callable[[], str],
        can_control: Callable[[], bool],
    ) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.page = page
        self.snapshot = snapshot
        self.asset_root = asset_root
        self.can_control = can_control
        self.viewer: TrackingDiagnosticViewer | None = None
        self._current_presentation: TrackingDiagnosticPresentation | None = None
        self._presentation_connection: tuple[int, str] | None = None
        self._poll_pending = False
        self._viewer_open = False
        self._identity: tuple[str, int, str] | None = None
        self._detached_identity: tuple[str, int, str] | None = None
        self._begin_pending = False
        self._close_requested: tuple[str, int, str] | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.poll)
        page.diagnostic_requested.connect(self.begin)
        page.diagnostic_close_requested.connect(self.close_diagnostic)
        page.diagnostic_viewer_requested.connect(self.open_viewer)
        bridge.tracking_frame_received.connect(self.install_frame)
        bridge.command_finished.connect(self.command_finished)
        bridge.operation_finished.connect(self.operation_finished)

    def begin(self) -> None:
        if not self.can_control():
            self._show_status(
                "Take control and review reconnect status before starting a diagnostic."
            )
            return
        snapshot = self.snapshot()
        if snapshot is None or not snapshot.HasField("configuration_values"):
            self._show_status(
                "Controller configuration is not synchronized.",
                can_begin=snapshot is not None and self._can_begin(snapshot),
            )
            return
        tracking = next(
            (
                backend.tracking
                for backend in snapshot.configuration_values.current.backends
                if backend.backend_name == "tracking"
                and backend.WhichOneof("settings") == "tracking"
            ),
            pb.TrackingSettings(),
        )
        try:
            settings, stages = self.page.diagnostic_configuration(
                tracking, asset_root=self.asset_root()
            )
            options = begin_request_options(snapshot, settings, stages)
        except (ClientError, ValueError, TypeError) as error:
            self._show_status(str(error), can_begin=self._can_begin(snapshot))
            return
        if not self.bridge.request("begin_tracking_diagnostic", **options):
            self._show_status(
                "Tracking diagnostic command queue is unavailable.",
                can_begin=True,
            )
            return
        self._begin_pending = True
        self.page.install_diagnostic_status(
            active=False,
            pending=True,
            message="Waiting for controller admission",
            can_begin=False,
        )

    def close_diagnostic(self) -> None:
        if not self.can_control():
            self._show_status("Take control before closing the diagnostic.")
            return
        snapshot = self.snapshot()
        if snapshot is None:
            self._show_status("Controller state is unavailable.")
            return
        try:
            options = close_request_options(snapshot)
        except ClientError as error:
            self._show_status(str(error))
            return
        if not self.bridge.request("close_tracking_diagnostic", **options):
            self._show_status("Tracking diagnostic close queue is unavailable.")
            return
        self._close_requested = (
            str(options["diagnostic_id"]),
            int(str(options["expected_revision"])),
            str(options["preview_run_id"]),
        )
        self.page.install_diagnostic_status(
            active=False,
            pending=True,
            message="Waiting for confirmed diagnostic closure",
            can_begin=False,
            viewer_available=self._viewer_open,
            pending_label="Stopping diagnostic…",
        )

    def install_snapshot(self, snapshot: pb.Snapshot | None) -> None:
        if snapshot is None or not snapshot.HasField("tracking_diagnostic"):
            self._identity = None
            self._current_presentation = None
            self._presentation_connection = None
            self.timer.stop()
            pending = self._begin_pending or self._close_requested is not None
            self.page.install_diagnostic_status(
                active=False,
                pending=pending,
                message=(
                    "Waiting for diagnostic status"
                    if pending
                    else "No active diagnostic"
                ),
                can_begin=snapshot is not None and not pending and self.can_control(),
                pending_label=(
                    "Stopping diagnostic…"
                    if self._close_requested is not None
                    else "Starting diagnostic…"
                ),
            )
            return
        diagnostic = snapshot.tracking_diagnostic
        if diagnostic.configuration_revision != snapshot.configuration.revision:
            self._identity = None
            self._current_presentation = None
            self._presentation_connection = None
            self.timer.stop()
            self._show_status("Diagnostic belongs to an older configuration")
            return
        identity = (
            diagnostic.diagnostic_id,
            diagnostic.configuration_revision,
            diagnostic.preview_run_id,
        )
        is_new = identity != self._identity
        if is_new:
            self._current_presentation = None
            self._presentation_connection = None
            self._detached_identity = None
            self._close_requested = None
            self._begin_pending = False
        if diagnostic.closed:
            self._close_requested = None
            self._begin_pending = False
        closing = self._close_requested == identity and not diagnostic.closed
        self._identity = identity
        text = diagnostic.failure or self._stage_status(diagnostic)
        pending = closing or (not diagnostic.active and not diagnostic.closed)
        viewer_ready = bool(
            diagnostic.active
            and diagnostic.tracking_endpoint
            and diagnostic.HasField("tracking_process")
        )
        self.page.install_diagnostic_status(
            active=diagnostic.active and not closing,
            pending=pending,
            message=text,
            last_duration_ns=diagnostic.last_duration_ns,
            maximum_duration_ns=diagnostic.maximum_duration_ns,
            can_begin=diagnostic.closed and self.can_control(),
            can_close=self.can_control(),
            viewer_available=viewer_ready,
            pending_label="Stopping diagnostic…" if closing else "Starting diagnostic…",
        )
        if viewer_ready:
            if is_new and self._detached_identity != identity:
                self._open_viewer()
            if self._viewer_open:
                self.timer.start()
            else:
                self.timer.stop()
        else:
            self.timer.stop()
        if diagnostic.closed or diagnostic.failure:
            self.page.diagnostic_viewer_button.setEnabled(False)

    def poll(self) -> None:
        snapshot = self.snapshot()
        if snapshot is None or not snapshot.HasField("tracking_diagnostic"):
            return
        diagnostic = snapshot.tracking_diagnostic
        identity = (
            diagnostic.diagnostic_id,
            diagnostic.configuration_revision,
            diagnostic.preview_run_id,
        )
        if (
            identity != self._identity
            or not diagnostic.active
            or not diagnostic.tracking_endpoint
            or not diagnostic.HasField("tracking_process")
            or self._poll_pending
            or not self._viewer_open
        ):
            return
        self._poll_pending = self.bridge.request(
            "tracking_diagnostic_frame",
            expected_revision=diagnostic.configuration_revision,
            diagnostic_id=diagnostic.diagnostic_id,
            preview_run_id=diagnostic.preview_run_id,
            tracking_endpoint=diagnostic.tracking_endpoint,
            tracking_generation=diagnostic.tracking_process.generation,
        )

    def install_frame(self, epoch: int, generation: str, raw: bytes) -> None:
        self._poll_pending = False
        if self.viewer is None or self.snapshot() is None:
            return
        snapshot = self.snapshot()
        if snapshot is None or not snapshot.HasField("tracking_diagnostic"):
            return
        diagnostic = snapshot.tracking_diagnostic
        if (epoch, generation) != (
            self.bridge.connection_epoch,
            snapshot.controller_generation,
        ):
            return
        try:
            frame = tracking_rpc.TrackingDiagnosticFrame.FromString(raw)
            presentation = tracking_diagnostic_presentation(
                frame,
                diagnostic_id=diagnostic.diagnostic_id,
                configuration_revision=diagnostic.configuration_revision,
                preview_run_id=diagnostic.preview_run_id,
                maximum_image_bytes=max(1, self.bridge.max_message_bytes - 65_536),
            )
        except (ValueError, TypeError) as error:
            self.viewer.show_unavailable(str(error))
            return
        if not diagnostic.source_camera_serial:
            self.viewer.show_unavailable("Tracking camera identity is unavailable")
            return
        self._current_presentation = presentation
        self._presentation_connection = (epoch, generation)
        self.viewer.show_presentation(
            presentation,
            status=self._stage_status(diagnostic),
            last_duration_ns=diagnostic.last_duration_ns,
            maximum_duration_ns=diagnostic.maximum_duration_ns,
        )

    def command_finished(self, action: str, success: bool, message: str) -> None:
        if action == "tracking_diagnostic_frame":
            self._poll_pending = False
            if not success and self.viewer is not None:
                self.viewer.show_unavailable(message)

    def operation_finished(
        self, action: str, command_id: str, status: str, message: str
    ) -> None:
        del command_id
        if action not in {
            "begin_tracking_diagnostic",
            "close_tracking_diagnostic",
        }:
            return
        snapshot = self.snapshot()
        if action == "begin_tracking_diagnostic" and status == "rejected":
            self._begin_pending = False
        if action == "close_tracking_diagnostic" and status == "rejected":
            self._close_requested = None
        if snapshot is not None and snapshot.HasField("tracking_diagnostic"):
            self.install_snapshot(snapshot)
            return
        self.page.install_diagnostic_status(
            active=False,
            pending=status != "rejected",
            message=message,
            can_begin=status == "rejected" and self.can_control(),
            pending_label="Starting diagnostic…"
            if action == "begin_tracking_diagnostic"
            else "Stopping diagnostic…",
        )

    def _open_viewer(self) -> None:
        snapshot = self.snapshot()
        if (
            snapshot is None
            or not snapshot.HasField("tracking_diagnostic")
            or not snapshot.tracking_diagnostic.active
        ):
            return
        if self.viewer is None:
            self.viewer = TrackingDiagnosticViewer(cast(QWidget | None, self.parent()))
            self.viewer.detached.connect(self._viewer_detached)
            self.viewer.use_frame_requested.connect(self.freeze_current_frame)
        self._viewer_open = True
        self._detached_identity = None
        self.viewer.show_unavailable("Waiting for the first exact-source frame")
        self.viewer.show()
        self.viewer.raise_()
        self.page.diagnostic_viewer_button.setEnabled(True)

    def open_viewer(self) -> None:
        self._open_viewer()

    def freeze_current_frame(self) -> None:
        """Copy only the operator-selected image whose diagnostic scope is current."""
        snapshot = self.snapshot()
        presentation = self._current_presentation
        if (
            snapshot is None
            or not snapshot.HasField("tracking_diagnostic")
            or presentation is None
            or self._presentation_connection
            != (self.bridge.connection_epoch, snapshot.controller_generation)
        ):
            self.page.status.console.appendPlainText(
                "There is no exact-source frame to freeze yet."
            )
            return
        diagnostic = snapshot.tracking_diagnostic
        if (
            presentation.diagnostic_id != diagnostic.diagnostic_id
            or presentation.configuration_revision != diagnostic.configuration_revision
            or presentation.preview_run_id != diagnostic.preview_run_id
            or diagnostic.configuration_revision != snapshot.configuration.revision
            or not diagnostic.source_camera_serial
            or not diagnostic.closed
            and not diagnostic.active
        ):
            self.page.status.console.appendPlainText(
                "The displayed frame no longer matches the current diagnostic."
            )
            return
        try:
            self.page.freeze_diagnostic_frame(
                presentation, camera_serial=diagnostic.source_camera_serial
            )
        except ValueError as error:
            self.page.status.console.appendPlainText(str(error))
            return
        self.page.status.console.appendPlainText(
            "Frozen the selected acquired Tracking frame for local annotation. "
            "Close the diagnostic before editing Tracking settings."
        )

    def _viewer_detached(self) -> None:
        self._viewer_open = False
        self._poll_pending = False
        self.timer.stop()
        self._detached_identity = self._identity
        snapshot = self.snapshot()
        self.page.diagnostic_viewer_button.setEnabled(
            bool(
                snapshot
                and snapshot.HasField("tracking_diagnostic")
                and snapshot.tracking_diagnostic.active
            )
        )

    def _show_status(self, message: str, *, can_begin: bool = False) -> None:
        self.page.install_diagnostic_status(
            active=False, pending=False, message=message, can_begin=can_begin
        )
        if self.viewer is not None:
            self.viewer.show_unavailable(message)

    @staticmethod
    def _can_begin(snapshot: pb.Snapshot | None) -> bool:
        return (
            snapshot is None
            or not snapshot.HasField("tracking_diagnostic")
            or snapshot.tracking_diagnostic.closed
        )

    @staticmethod
    def _stage_status(diagnostic: pb.TrackingDiagnosticState) -> str:
        if not diagnostic.stages:
            return "Image and preprocessing only"
        return " · ".join(
            f"{pb.TrackingDiagnosticStage.Name(item.stage).removeprefix('TRACKING_DIAGNOSTIC_STAGE_').lower()}: "
            f"{pb.TrackingDiagnosticStageState.Name(item.state).removeprefix('TRACKING_DIAGNOSTIC_STAGE_STATE_').lower()}"
            + (f" ({item.reason})" if item.reason else "")
            for item in diagnostic.stages
        )
