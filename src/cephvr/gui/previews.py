"""External preview workspace; acquisition retains native windows and pixels."""

from dataclasses import replace

from PyQt6.QtCore import QByteArray, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QHideEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import FittedConsole, label
from cephvr.gui.layouts import snap_tool_window
from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.theme import SIZES
from cephvr.gui.view import PreviewView


class PreviewDialog(QDialog):
    visibility_requested = pyqtSignal(str, bool)
    opened = pyqtSignal()

    def __init__(self, parent: QWidget, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        saved = (
            settings.value("windows/preview-workspace")
            if settings is not None
            else None
        )
        self.saved_geometry = saved if isinstance(saved, QByteArray) else QByteArray()
        self._opened = False
        self.setWindowTitle("Previews")
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.setMinimumSize(600, 450)
        self.resize(1440, 960)
        self.setWindowModality(Qt.WindowModality.NonModal)
        body = QVBoxLayout(self)
        body.setContentsMargins(*([SIZES.compact_card_padding] * 4))
        self.hud = FittedConsole()
        self.hud.setProperty("terminal", "telemetry")
        self.hud.setAccessibleName("Experiment status")
        body.addWidget(self.hud)
        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        self.timeline_toggle = QCheckBox("Stimulus timeline")
        self.timeline_toggle.setToolTip(
            "Show the planned stimulus speed and direction plots"
        )
        self.timeline_toggle.setChecked(
            settings.value("windows/preview-timeline-visible", True, type=bool)
            if settings is not None
            else True
        )
        toolbar.addWidget(self.timeline_toggle)
        body.addLayout(toolbar)
        self.preview_host = QWidget(self)
        self.preview_layout = QVBoxLayout(self.preview_host)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.empty_hint = label("No enabled streams in this experiment.", wrap=True)
        self.empty_hint.setObjectName("PreviewWorkspaceEmpty")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_layout.addWidget(self.empty_hint)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.preview_host)
        self.timeline = StimulusTimeline()
        self.splitter.addWidget(self.timeline)
        self.splitter.setHandleWidth(12)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([520, 380])
        body.addWidget(self.splitter, 1)
        self.timeline.setVisible(self.timeline_toggle.isChecked())
        self.timeline_toggle.toggled.connect(self.set_timeline_visible)
        self.views: dict[str, PreviewView] = {}
        self.controls: dict[str, QCheckBox] = {}
        self.statuses: dict[str, QLabel] = {}
        self.names: dict[str, QLabel] = {}
        self.source_widgets: dict[str, QWidget] = {}
        self.recording_enabled: dict[str, bool] = {}
        self.allowed = False

    def set_timeline_visible(self, visible: bool) -> None:
        self.timeline.setVisible(visible)
        if self.settings is not None:
            self.settings.setValue("windows/preview-timeline-visible", visible)

    def show_saved(self, main: QWidget) -> None:
        if not self.isVisible():
            restored = (
                self._opened
                or bool(self.saved_geometry)
                and self.restoreGeometry(self.saved_geometry)
            )
            self.fit_contents()
            self.show()
            self._opened = True
            if not restored:
                snap_tool_window(main, self)
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self.opened.emit()

    def reject(self) -> None:
        self.hide()

    def closeEvent(self, event: QCloseEvent | None) -> None:
        # Keep the native owner HWND alive for acquisition-owned viewers.
        if event is not None:
            event.ignore()
        self.hide()

    def hideEvent(self, event: QHideEvent | None) -> None:
        self.saved_geometry = self.saveGeometry()
        if self.settings is not None:
            self.settings.setValue("windows/preview-workspace", self.saved_geometry)
            self.settings.sync()
        super().hideEvent(event)

    def apply_views(
        self, views: tuple[PreviewView, ...], *, allowed: bool, sample: bool
    ) -> None:
        self.allowed = allowed
        self.setWindowTitle("Previews · review" if sample else "Previews")
        if not self.controls or tuple(self.views) != tuple(view.key for view in views):
            for widget in self.source_widgets.values():
                widget.hide()
                widget.deleteLater()
            self.controls.clear()
            self.statuses.clear()
            self.names.clear()
            self.source_widgets.clear()
            for view in views:
                panel = QWidget(self)
                layout = QVBoxLayout(panel)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(2)
                row = QHBoxLayout()
                name = label(view.name, "eyebrow", wrap=True)
                control = QCheckBox("Show")
                control.setProperty("role", "viewer-toggle")
                control.setAccessibleName(view.name)
                name.setBuddy(control)
                control.clicked.connect(
                    lambda checked, key=view.key: self.request(key, checked)
                )
                status = label("", "muted", wrap=True)
                row.addWidget(name, 1)
                row.addWidget(control)
                layout.addLayout(row)
                layout.addWidget(status)
                panel.hide()
                self.source_widgets[view.key] = panel
                self.names[view.key] = name
                self.controls[view.key] = control
                self.statuses[view.key] = status

        self.views = {view.key: view for view in views}
        self.refresh()

    def attach_controls(self, hosts: dict[str, QWidget]) -> None:
        """Keep controls alive when source frames disappear or move to Devices."""
        for key, panel in self.source_widgets.items():
            host = hosts.get(key)
            parent = host if host is not None else self
            if panel.parentWidget() is not parent:
                panel.setParent(parent)
                if host is not None:
                    layout = host.layout()
                    assert isinstance(layout, QVBoxLayout)
                    layout.addWidget(panel)
            panel.setVisible(host is not None)

    def refresh(self) -> None:
        for key, view in self.views.items():
            control = self.controls[key]
            control.setMinimumWidth(control.sizeHint().width())
            self.names[key].setText(f"[ {view.name.upper()} ]")
            control.setAccessibleName(view.name)
            control.setChecked(view.visible)
            control.setEnabled(
                self.allowed
                and view.active
                and view.available
                and not view.pending
                and (self.recording_enabled.get(key, True) or view.visible)
            )
            self.names[key].setEnabled(
                view.active and view.available and self.recording_enabled.get(key, True)
            )
            text = (
                "Video recording is off"
                if not self.recording_enabled.get(key, True)
                else view.reason
                if view.reason
                else "Waiting for viewer…"
                if view.pending
                else ""
            )
            self.statuses[key].setText(text)
            self.statuses[key].setVisible(bool(text))
            control.setToolTip(
                "Inactive for experiment"
                if not view.active
                else text
                if self.allowed
                else "Operator control required"
            )
            self.names[key].setToolTip(control.toolTip())
        if self.isVisible():
            self.fit_contents()

    def fit_contents(self) -> None:
        screen = self.screen()
        available = (
            screen.availableGeometry().size() if screen is not None else self.size()
        )
        self.setMinimumWidth(min(660, available.width()))

    def request(self, key: str, visible: bool) -> None:
        view = self.views.get(key)
        if (
            view is None
            or not self.allowed
            or not view.active
            or not view.available
            or view.pending
            or (visible and not self.recording_enabled.get(key, True))
        ):
            self.refresh()
            return
        self.views[key] = replace(view, pending=True)
        self.refresh()
        self.visibility_requested.emit(key, visible)
