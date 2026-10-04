"""Local frontend entry point, deliberately separate from managed GUI bootstrap."""

import argparse
import sys
from dataclasses import replace

from PyQt6.QtCore import QObject, QRect, QSettings
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QApplication

from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.projectors import DisplayInfo
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase, PreviewView, review_view
from cephvr.gui.window import DashboardWindow


class ReviewControls(QObject):
    """Keep optional fixture inspection in the View menu, outside the Dashboard."""

    def __init__(
        self, window: DashboardWindow, *, simulate_projectors: bool = False
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
        window.dashboard.action_requested.connect(
            lambda action: window.dashboard.log_console.appendPlainText(
                f"LOCAL REVIEW · {action} selected; no command sent."
            )
        )
        window.dashboard.preview_requested.connect(self.preview_visibility)
        cameras = window.devices.cameras
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
            projectors = window.devices.projectors
            faces = ("Front", "Left", "Right", "Bottom")
            projectors.review_displays = tuple(
                DisplayInfo(
                    f"review-projector-{face.lower()}",
                    f"Simulated {face} projector",
                    str(index + 2),
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
        window.dashboard.log_console.setPlainText(
            "Sample subject loaded.\nNo controller connection."
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
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("CephVR2.0 Dashboard")
    apply_theme(app)
    window = DashboardWindow(
        sample=args.review, settings=QSettings("CephVR", "Frontend")
    )
    if args.review:
        ReviewControls(window, simulate_projectors=True)
    fit_window_to_screen(window)
    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
