"""Local frontend entry point, deliberately separate from managed GUI bootstrap."""

import argparse
import sys
from dataclasses import replace

from PyQt6.QtCore import QObject, QRect, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QCloseEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from cephvr.gui.preview_placement import preview_window_placement
from cephvr.gui.projectors import DisplayInfo
from cephvr.gui.protocol_document import blank_program, review_program
from cephvr.gui.review_draft import draft_path, load_review_draft, save_review_draft
from cephvr.gui.splash import StartupSplash
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase, PreviewView, review_view
from cephvr.gui.window import DashboardWindow

# Simulated session progression per command: (phase, delay before entering, ms).
SIMULATED_STEPS: dict[str, tuple[tuple[Phase, int], ...]] = {
    "Setup": ((Phase.SETTING_UP, 0), (Phase.READY, 1200)),
    "Cancel Setup": ((Phase.CONFIGURATION, 0),),
    "Start": ((Phase.STARTING, 0), (Phase.RUNNING, 800)),
    "Stop after trial": (
        (Phase.STOPPING, 0),
        (Phase.FINALIZING, 800),
        (Phase.ENDED, 800),
    ),
    "Abort now": ((Phase.STOPPING, 0), (Phase.FINALIZING, 800), (Phase.ENDED, 800)),
    "New session": ((Phase.CONFIGURATION, 0),),
}


class ReviewDashboardWindow(DashboardWindow):
    """Keep local review drafts across normal review-window closure."""

    closing = pyqtSignal()

    def __init__(
        self,
        *,
        sample: bool = False,
        settings: QSettings | None = None,
        device_review: bool = True,
    ) -> None:
        super().__init__(sample=sample, settings=settings, device_review=device_review)
        self._restore_failed = False

    def closeEvent(self, event: QCloseEvent | None) -> None:
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
        fake_previews: bool = False,
    ) -> None:
        super().__init__(window)
        menu_bar = window.menuBar()
        assert menu_bar is not None
        # Share the window's own View menu rather than adding a second one.
        menu = next(
            (item.menu() for item in menu_bar.actions() if item.text() == "View"), None
        ) or menu_bar.addMenu("View")
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
        self.preview_windows = None
        if fake_previews:
            from cephvr.gui.review_preview import ReviewPreviews

            self.preview_windows = ReviewPreviews(
                self,
                lambda key: preview_window_placement(window, key),
                lambda key: self._set_preview_visibility(key, False),
                window.devices.cameras.console.appendPlainText,
                owner_handle=lambda: int(
                    (window.preview_slot.window() or window).winId()
                ),
                owner_minimized=lambda: (
                    window.isMinimized()
                    or (window.preview_slot.window() or window).isMinimized()
                    or not (window.preview_slot.window() or window).isVisible()
                ),
            )
            window.preview_slot.snap_requested.connect(
                lambda key: (
                    self.preview_windows.snap(key)
                    if self.preview_windows is not None
                    and window.dashboard.view.has_control
                    else None
                )
            )
            if isinstance(window, ReviewDashboardWindow):
                window.closing.connect(self.preview_windows.close)
            app = QApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(self.preview_windows.close)
        self.simulation = 0
        window.dashboard.action_requested.connect(self.simulate_action)
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

    def simulate_action(self, action: str) -> None:
        """Walk a dummy session through phases; no command or backend is involved."""
        self.window.dashboard.log_console.appendPlainText(
            f"LOCAL REVIEW · {action} selected; simulated session, no command sent."
        )
        if action == "Start":
            self.show_sample_motion()
        self.simulation += 1
        token = self.simulation
        delay = 0
        for phase, wait in SIMULATED_STEPS.get(action, ()):
            delay += wait
            QTimer.singleShot(
                delay, lambda phase=phase: self.advance_simulation(token, phase)
            )

    def show_sample_motion(self) -> None:
        """Give the dummy run an epoch timeline and dials without touching saved edits."""
        editor = self.window.protocol.editor
        draft = editor.drafts[editor.index]
        if draft.program == blank_program():
            editor.set_program(review_program())
            self.window.dashboard.log_console.appendPlainText(
                "LOCAL REVIEW · sample trial program loaded for the preview timeline."
            )
        workspace = self.window.dashboard.preview_workspace
        if not workspace.advanced_toggle.isChecked():
            # Review-only: show the dials without changing the saved preference.
            workspace.advanced_toggle.blockSignals(True)
            workspace.advanced_toggle.setChecked(True)
            workspace.advanced_toggle.blockSignals(False)
            workspace.set_advanced_visible(True, persist=False)

    def advance_simulation(self, token: int, phase: Phase) -> None:
        # A newer command or a manual phase choice supersedes pending steps.
        if token == self.simulation:
            self.set_phase(phase, manual=False)

    def set_phase(self, phase: Phase, *, manual: bool = True) -> None:
        if manual:
            self.simulation += 1
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
        if self.preview_windows is not None:
            active_keys = {item.key for item in previews if item.active}
            for key in tuple(self.preview_windows.windows):
                if key not in active_keys:
                    self.preview_windows.visibility(key, "", False)
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
        if self.preview_windows is not None:
            visible = self.preview_windows.visibility(key, source.name, visible)
        self._set_preview_visibility(key, visible)
        dashboard.log_console.appendPlainText(
            f"LOCAL REVIEW · {key} sample visibility {'on' if visible else 'off'}; "
            + (
                "synthetic viewer only."
                if self.preview_windows
                else "no viewer command sent."
            )
        )

    def _set_preview_visibility(self, key: str, visible: bool) -> None:
        dashboard = self.window.dashboard
        self.window.apply_view(
            replace(
                dashboard.view,
                previews=tuple(
                    replace(item, visible=visible) if item.key == key else item
                    for item in dashboard.view.previews
                ),
            )
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
        "--fake-previews",
        action="store_true",
        help="Open blank OpenCV windows (default in isolated Review).",
    )
    parser.add_argument(
        "--real-devices",
        action="store_true",
        help="Explicitly inspect attached local devices without a managed controller.",
    )
    args = parser.parse_args()
    if args.simulated_devices and args.real_devices:
        parser.error("Select either simulated or real devices")
    if args.fake_previews and (not args.review or args.real_devices):
        parser.error("--fake-previews requires --review with simulated devices")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("CephVR2.0 Dashboard")
    settings = QSettings("CephVR", "Frontend")
    splash = StartupSplash(settings)
    splash.begin()
    apply_theme(app)
    window_class = ReviewDashboardWindow if args.review else DashboardWindow
    window = window_class(sample=args.review, settings=settings)
    if args.review:
        ReviewControls(
            window,
            simulate_projectors=not args.real_devices,
            real_devices=args.real_devices,
            fake_previews=not args.real_devices,
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
    splash.reveal(window)
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
