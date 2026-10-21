"""External preview workspace; acquisition retains native windows and pixels."""

from dataclasses import replace

from PyQt6.QtCore import QByteArray, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QHideEvent, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, FittedConsole, label
from cephvr.gui.layouts import snap_tool_window
from cephvr.gui.preview_log import PreviewLog
from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.retro_overlay import set_glow
from cephvr.gui.system_controls import SystemControls
from cephvr.gui.theme import SIZES, retro_console
from cephvr.gui.view import PreviewView


def recording_state(output_status: str) -> tuple[str, str]:
    """Map controller output-closure evidence to a lamp state and caption."""
    if output_status in {"Last reported outputs open", "Open"}:
        return "recording", "● REC"
    if output_status == "Closing":
        return "waiting", "◐ CLOSING"
    if output_status in {"Failed", "Unconfirmed"}:
        return "fault", f"▲ OUTPUT {output_status.upper()}"
    return "idle", ""


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
        self.setObjectName("PreviewWorkspace")
        self.setWindowTitle("Previews")
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        # Height comes from the layout, so a small window never clips a frame row.
        self.setMinimumWidth(600)
        self.resize(1440, 960)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(*([SIZES.compact_card_padding] * 4))
        self.content.setSpacing(16)
        self.details = QWidget(self)
        self.details_layout = QVBoxLayout(self.details)
        self.details_layout.setContentsMargins(0, 0, 0, 0)
        self.details_layout.setSpacing(SIZES.field_y_gap)
        self.top_host = QWidget(self)
        self.top_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self.top = QGridLayout(self.top_host)
        self.top.setContentsMargins(0, 0, 0, 0)
        self.top.setHorizontalSpacing(SIZES.field_x_gap)
        self.top.setVerticalSpacing(SIZES.field_y_gap)
        self.hud = FittedConsole()
        self.hud.setProperty("terminal", "telemetry")
        self.hud.setAccessibleName("Experiment status")
        self.recording_lamp = label("", "rec-lamp")
        self.recording_lamp.setAccessibleName("Recording status")
        # Workspace-wide view options stay with the timeline.
        self.toggle_bar = QFrame()
        self.toggle_bar.setObjectName("PreviewToggles")
        toolbar = QHBoxLayout(self.toggle_bar)
        toolbar.setContentsMargins(10, 4, 10, 4)
        toolbar.setSpacing(SIZES.field_x_gap)
        self.advanced_toggle = QCheckBox("Advanced previews")
        self.advanced_toggle.setToolTip("Show motion dials, arena map and size lanes")
        self.advanced_toggle.setChecked(
            settings.value("windows/preview-advanced-visible", False, type=bool)
            if settings is not None
            else False
        )
        toolbar.addWidget(self.advanced_toggle)
        self.set_output_status("")
        # Keep status above the resizable stream/plot sections.
        self.timeline = StimulusTimeline()
        self.timeline.plots.removeWidget(self.timeline.motion_section)
        self.details_layout.addWidget(self.timeline.motion_section, 1)
        self.preview_host = QWidget(self)
        self.preview_layout = QVBoxLayout(self.preview_host)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.empty_hint = label("No enabled streams in this experiment.", wrap=True)
        self.empty_hint.setObjectName("PreviewWorkspaceEmpty")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_layout.addWidget(self.empty_hint)
        self.session_controls = SystemControls(compact=True)
        self.session_controls.header.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.hud_card = Card("HUD", compact=True)
        self.hud_card.header.addWidget(self.recording_lamp)
        self.hud_card.body.addWidget(self.hud)
        self.log_card = Card("Console", compact=True)
        self.log_tail = PreviewLog()
        self.log_card.body.addWidget(self.log_tail)
        for column, card in enumerate(
            (self.session_controls, self.hud_card, self.log_card)
        ):
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            if card is not self.session_controls:
                card.body.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.top.addWidget(card, 0, column)
        for column, stretch in enumerate((2, 3, 5)):
            self.top.setColumnStretch(column, stretch)
        self.timeline.body.insertWidget(
            0, self.toggle_bar, 0, Qt.AlignmentFlag.AlignRight
        )
        self.content.addWidget(self.top_host)
        self.content.addWidget(self.timeline)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(16)
        self.splitter.setOpaqueResize(True)
        self.splitter.addWidget(self.preview_host)
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)
        handle = self.splitter.handle(1)
        assert handle is not None
        handle.setToolTip("Drag to resize previews and plots")
        self.content.addWidget(self.splitter, 1)
        self.set_advanced_visible(self.advanced_toggle.isChecked())
        self.advanced_toggle.toggled.connect(self.set_advanced_visible)
        self.views: dict[str, PreviewView] = {}
        self.controls: dict[str, QCheckBox] = {}
        # Status text is shown inside each source's frame by the preview slot.
        self.statuses: dict[str, str] = {}
        self.hints: dict[str, QLabel] = {}
        self.names: dict[str, QLabel] = {}
        self.source_widgets: dict[str, QWidget] = {}
        self.recording_enabled: dict[str, bool] = {}
        self.allowed = False
        self.glow = False

    def restyle(self, glow: bool | None = None) -> None:
        """Apply the CRT heading glow to stream and projector headings."""
        if glow is not None:
            self.glow = glow
        for name in self.names.values():
            set_glow(name, self.glow)
        self.timeline.restyle(self.glow)
        self.log_tail.set_entry_prompts(retro_console(self))
        self.log_tail.fit_height()

    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        if not self._opened and self.advanced_toggle.isChecked():
            self.set_advanced_visible(True)

    def set_output_status(self, output_status: str) -> None:
        state, caption = recording_state(output_status)
        lamp = self.recording_lamp
        lamp.setText(caption)
        # Only REC, closing and output faults are shown; idle has no lamp.
        lamp.setVisible(state != "idle")
        lamp.setToolTip(
            f"Controller output evidence: {output_status or 'none reported'}"
        )
        if lamp.property("state") != state:
            lamp.setProperty("state", state)
            style = lamp.style()
            if style is not None:
                style.unpolish(lamp)
                style.polish(lamp)

    def set_advanced_visible(self, visible: bool) -> None:
        self.timeline.set_advanced(visible)
        self.details.setVisible(visible)
        if visible:
            width = max(1, self.splitter.width() - self.splitter.handleWidth())
            self.splitter.setSizes([width * 2 // 3, width // 3])
        if self.settings is not None:
            self.settings.setValue("windows/preview-advanced-visible", visible)

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
            self.hints.clear()
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
                hint = label("", "muted")
                row.addWidget(name, 1)
                row.addWidget(hint)
                row.addWidget(control)
                layout.addLayout(row)
                panel.hide()
                self.source_widgets[view.key] = panel
                self.names[view.key] = name
                self.controls[view.key] = control
                self.hints[view.key] = hint
                self.statuses[view.key] = ""
                set_glow(name, self.glow)

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
            # Non-breaking spaces keep each bracket with its word when the heading wraps.
            self.names[key].setText(f"[ {view.name.upper()} ]")
            control.setAccessibleName(view.name)
            control.setChecked(view.visible)
            control.setEnabled(
                self.allowed
                and view.active
                and view.available
                and not view.pending
                and (self.recording_enabled.get(key, True) or view.visible)
            )
            recording = self.recording_enabled.get(key, True)
            # Unavailable-before-Setup sources keep a bright heading; the frame says why.
            self.names[key].setEnabled(view.active and recording)
            # Hint only where the frame text cannot: observers, or an open viewer
            # covering it. Waiting frames keep a fixed heading while polling.
            hint = (
                ""
                if control.isEnabled()
                else "no control"
                if not self.allowed
                else ""
                if not view.visible
                else "closing…"
                if view.pending
                else "unavailable"
            )
            self.hints[key].setText(hint)
            self.hints[key].setVisible(bool(hint))
            text = (
                "Video recording is off"
                if not recording
                else view.reason
                if view.reason
                else "Waiting for viewer…"
                if view.pending and not view.visible
                else ""
            )
            self.statuses[key] = text
            self.hints[key].setToolTip(text)
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
