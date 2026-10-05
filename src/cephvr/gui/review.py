"""Local frontend entry point, deliberately separate from managed GUI bootstrap."""

import argparse
import sys
from dataclasses import replace

from PyQt6.QtCore import QObject, QRect, QSettings, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QCloseEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.projectors import DisplayInfo
from cephvr.gui.review_draft import draft_path, load_review_draft, save_review_draft
from cephvr.gui.review_mcu import ReviewMcu
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase, PreviewView, review_view
from cephvr.gui.window import DashboardWindow


class ReviewDashboardWindow(DashboardWindow):
    """Keep local review drafts across normal review-window closure."""

    closing = pyqtSignal()

    def __init__(
        self, *, sample: bool = False, settings: QSettings | None = None
    ) -> None:
        super().__init__(sample=sample, settings=settings)
        self._restore_failed = False

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        if getattr(self, "_restore_failed", False):
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle("Previous review draft is unreadable")
            dialog.setText("Saving now would replace the unreadable draft.")
            replace = dialog.addButton(
                "Replace with current draft", QMessageBox.ButtonRole.AcceptRole
            )
            dialog.addButton(
                "Close and preserve old draft", QMessageBox.ButtonRole.DestructiveRole
            )
            dialog.exec()
            if dialog.clickedButton() is not replace:
                self.closing.emit()
                super().closeEvent(event)
                return
            self._restore_failed = False
        while True:
            try:
                save_review_draft(self, draft_path())
                break
            except (OSError, TypeError, ValueError) as exc:
                dialog = QMessageBox(self)
                dialog.setIcon(QMessageBox.Icon.Warning)
                dialog.setWindowTitle("Review draft not saved")
                dialog.setText("The last review configuration could not be saved.")
                dialog.setInformativeText(str(exc))
                retry = dialog.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
                dialog.addButton(
                    "Close without saving", QMessageBox.ButtonRole.DestructiveRole
                )
                dialog.exec()
                if dialog.clickedButton() is not retry:
                    break
        self.closing.emit()
        super().closeEvent(event)


class ReviewControls(QObject):
    """Keep optional fixture inspection in the View menu, outside the Dashboard."""

    def __init__(
        self,
        window: DashboardWindow,
        *,
        simulate_projectors: bool = False,
        real_devices: bool = False,
    ) -> None:
        super().__init__(window)
        menu_bar = window.menuBar()
        assert menu_bar is not None
        menu = menu_bar.addMenu("View")
        assert menu is not None
        phases = menu.addMenu("Preview session state")
        assert phases is not None
        group = QActionGroup(self)
        group.setExclusive(True)
        self.phase = Phase.CONFIGURATION
        self.phase_actions: dict[Phase, QAction] = {}
        self.observer = QAction("Observer", self)
        self.observer.setCheckable(True)
        for phase in Phase:
            action = QAction(phase.value, self)
            action.setCheckable(True)
            group.addAction(action)
            phases.addAction(action)
            action.triggered.connect(
                lambda checked=False, value=phase: self.set_phase(value)
            )
            self.phase_actions[phase] = action
        menu.addAction(self.observer)
        self.observer.toggled.connect(lambda checked: self.set_phase(self.phase))
        self.phase_actions[self.phase].setChecked(True)
        self.window = window
        self.review_mcu: ReviewMcu | None = None
        if real_devices:
            panel = window.devices.microcontroller
            panel.live_review = True
            self.review_mcu = ReviewMcu()
            self.review_mcu.connection_result.connect(self.mcu_connection_result)
            self.review_mcu.diagnostic_result.connect(panel.set_diagnostic)
            self.review_mcu.command_failed.connect(panel.set_test_failure)
            panel.connection_requested.connect(self.test_mcu_connection)
            panel.pin_test_requested.connect(self.test_mcu_pin)
            if isinstance(window, ReviewDashboardWindow):
                window.closing.connect(self.review_mcu.shutdown)
            self.review_mcu.start()
        window.dashboard.action_requested.connect(
            lambda action: window.dashboard.log_console.appendPlainText(
                f"LOCAL REVIEW · {action} selected; no command sent."
            )
        )
        window.dashboard.preview_requested.connect(self.preview_visibility)
        cameras = window.devices.cameras
        cameras.real_devices = real_devices
        if real_devices:
            cameras.console.setPlainText(
                "Discovering attached cameras; no camera opened."
            )
            cameras.drafts = []
            cameras.populate_inventory()
            cameras.load_selected()
            cameras.drafts_changed.emit()
        cameras.participation_changed.connect(self.refresh_preview_sources)
        cameras.preview_requested.connect(self.preview_visibility)
        self.backend_actions: dict[str, QAction] = {}
        activity = menu.addMenu("Review active backends")
        assert activity is not None
        for key, title in (
            ("tracking", "Tracking pipeline"),
            ("stimulus", "Visual stimulus"),
        ):
            action = QAction(title, self)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(self.refresh_preview_sources)
            activity.addAction(action)
            self.backend_actions[key] = action
        self.backend_actions["tracking"].setEnabled(False)
        self.backend_actions["tracking"].setToolTip(
            "Derived from Protocol type and Tracking velocities"
        )
        window.protocol.participation_changed.connect(self.refresh_preview_sources)
        window.apply_view(review_view(self.phase))
        self.refresh_preview_sources()
        if simulate_projectors:
            window.devices.microcontroller.simulated_inventory = True
            window.devices.microcontroller.request("Scan ports")
            projectors = window.devices.projectors
            faces = ("Front", "Left", "Right", "Bottom")
            projectors.review_displays = tuple(
                DisplayInfo(
                    f"review-projector-{face.lower()}",
                    f"Simulated {face} projector",
                    str(index + 1),
                    QRect((index % 2) * 1920, (index // 2) * 1080, 1920, 1080),
                )
                for index, face in enumerate(faces)
            )
            projectors.assignments.update(
                (display.identity, face)
                for display, face in zip(projectors.review_displays, faces, strict=True)
            )
            projectors.request("Refresh displays")
            window.setWindowTitle(window.windowTitle() + " · 4 simulated projectors")
        elif real_devices:
            window.devices.projectors.request("Refresh displays")
            cameras.refresh_inventory()
            window.devices.microcontroller.request("Scan ports")
            window.setWindowTitle(window.windowTitle() + " · rig device review")
        window.dashboard.log_console.setPlainText(
            "Sample subject loaded.\nNo controller connection."
        )

    def test_mcu_connection(self) -> None:
        if self.review_mcu is not None:
            self.review_mcu.request(
                "connect",
                port=str(self.window.devices.microcontroller.port.currentData()),
            )

    def test_mcu_pin(self, key: str, start: bool) -> None:
        if self.review_mcu is None:
            return
        if not start:
            self.review_mcu.request("stop", key=key)
            return
        panel = self.window.devices.microcontroller
        camera = next((item for item in panel.camera_rows if item.key == key), None)
        editor = (
            panel.trial_pin
            if key == "trial-state"
            else panel.flip_pin
            if key == "projector-flip"
            else panel.pin_editors[key]
        )
        self.review_mcu.request(
            "start",
            key=key,
            port=str(panel.port.currentData()),
            pin=editor.text().strip(),
            role=camera.role if camera is not None else "",
            frequency_hz=float(camera.frequency) if camera is not None else None,
        )

    def mcu_connection_result(self, success: bool, message: str) -> None:
        panel = self.window.devices.microcontroller
        panel.connection_pending = False
        panel.refresh_tests()
        panel.console.appendPlainText(message)
        if success:
            port = str(panel.port.currentData())
            panel.status_column.hud.setPlainText(
                f"CONNECTION  Connected\nPORT        {port}\n{message}\n"
                "TRIGGER TEST Awaiting pin test"
            )
        else:
            panel.status_column.hud.setPlainText(
                f"CONNECTION  Failed\n{message}\nTRIGGER TEST Not tested"
            )

    def set_phase(self, phase: Phase) -> None:
        self.phase = phase
        self.phase_actions[phase].setChecked(True)
        self.window.apply_view(
            replace(
                review_view(phase, observer=self.observer.isChecked()),
                previews=self.window.dashboard.view.previews,
            )
        )

    def refresh_preview_sources(self) -> None:
        tracking_action = self.backend_actions["tracking"]
        tracking_action.blockSignals(True)
        tracking_action.setChecked(self.window.protocol.tracking_active)
        tracking_action.blockSignals(False)
        dashboard = self.window.dashboard
        previous = {item.key: item for item in dashboard.view.previews}
        cameras = sorted(
            self.window.devices.cameras.drafts,
            key=lambda item: {"Behavior cam": 0, "Tracking cam": 1}.get(item.role, 2),
        )
        sources = [
            (c.key, c.role, c.enabled) for c in cameras if c.role != "Unassigned"
        ]
        sources.extend(
            (key, name, self.backend_actions[key].isChecked())
            for key, name in (("tracking", "Tracking"), ("stimulus", "Visual stimulus"))
        )
        previews = tuple(
            PreviewView(
                key,
                name,
                active=active,
                available=True,
                reason="",
                visible=active and key in previous and previous[key].visible,
            )
            for key, name, active in sources
        )
        self.window.apply_view(replace(dashboard.view, previews=previews))

    def preview_visibility(self, key: str, visible: bool) -> None:
        dashboard = self.window.dashboard
        source = next((p for p in dashboard.view.previews if p.key == key), None)
        if (
            not dashboard.view.has_control
            or not source
            or not source.active
            or not source.available
        ):
            return
        self.window.apply_view(
            replace(
                dashboard.view,
                previews=tuple(
                    replace(item, visible=visible) if item.key == key else item
                    for item in dashboard.view.previews
                ),
            )
        )
        dashboard.log_console.appendPlainText(
            f"LOCAL REVIEW · {key} sample visibility {'on' if visible else 'off'}; "
            "no viewer command sent."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open the CephVR2.0 Dashboard frontend."
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Show labeled sample data and review state controls.",
    )
    parser.add_argument(
        "--simulated-devices",
        action="store_true",
        help="Use isolated device fixtures (the review default).",
    )
    parser.add_argument(
        "--real-devices",
        action="store_true",
        help="Explicitly inspect attached local devices without a managed controller.",
    )
    args = parser.parse_args()
    if args.simulated_devices and args.real_devices:
        parser.error("Select either simulated or real devices")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("CephVR2.0 Dashboard")
    apply_theme(app)
    window_class = ReviewDashboardWindow if args.review else DashboardWindow
    window = window_class(sample=args.review, settings=QSettings("CephVR", "Frontend"))
    if args.review:
        ReviewControls(
            window,
            simulate_projectors=not args.real_devices,
            real_devices=args.real_devices,
        )
        try:
            if load_review_draft(window, draft_path()):
                window.dashboard.log_console.appendPlainText(
                    "Local review draft restored; no controller configuration applied."
                )
            if not args.real_devices:
                window.devices.microcontroller.request("Scan ports")
        except (
            OSError,
            UnicodeError,
            TypeError,
            ValueError,
            KeyError,
            IndexError,
            AttributeError,
        ) as exc:
            if isinstance(window, ReviewDashboardWindow):
                window._restore_failed = True
            QMessageBox.warning(
                window,
                "Review draft not restored",
                f"The saved review draft was preserved but could not be restored: {exc}",
            )
    fit_window_to_screen(window)
    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
