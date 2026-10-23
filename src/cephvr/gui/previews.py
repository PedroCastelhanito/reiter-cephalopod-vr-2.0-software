"""In-Dashboard preview workspace; acquisition retains native windows and pixels."""

from dataclasses import replace

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
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
from cephvr.gui.preview_log import PreviewLog
from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.retro_overlay import set_glow
from cephvr.gui.stimulus_preview_area import StimulusPreviewArea
from cephvr.gui.theme import SIZES, minimal_frames, retro_console
from cephvr.gui.view import PreviewView


class PreviewWorkspace(QWidget):
    """Runtime Dashboard body: controls, HUD and console above timeline and streams."""

    visibility_requested = pyqtSignal(str, bool)

    def __init__(
        self, parent: QWidget | None, settings: QSettings | None = None
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self._opened = False
        self.setObjectName("PreviewWorkspace")
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(16)
        # Advanced instruments share one Projectors card; each projector is a section.
        self.details = Card("Projectors", self, grow=True)
        self.details_layout = self.details.body
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
        # Workspace-wide view options share a separate section below the timeline.
        self.toggle_bar = QFrame()
        self.toggle_bar.setObjectName("PreviewToggles")
        toolbar = QHBoxLayout(self.toggle_bar)
        toolbar.setContentsMargins(10, 4, 10, 4)
        toolbar.setSpacing(SIZES.field_x_gap)
        self.video_toggle = QCheckBox("Video previews")
        self.video_toggle.setToolTip(
            "Show the video stream section; hiding it closes open viewers "
            "(capture continues)"
        )
        self.video_toggle.setChecked(
            settings.value("windows/preview-video-visible", True, type=bool)
            if settings is not None
            else True
        )
        toolbar.addWidget(self.video_toggle)
        self.advanced_toggle = QCheckBox("Advanced previews")
        self.advanced_toggle.setToolTip("Show motion dials, arena map and size lanes")
        self.advanced_toggle.setChecked(
            settings.value("windows/preview-advanced-visible", False, type=bool)
            if settings is not None
            else False
        )
        toolbar.addWidget(self.advanced_toggle)
        # Per-item selectors: one row per enabled master toggle.
        self.video_row = QWidget()
        self.video_choices = QHBoxLayout(self.video_row)
        self.video_choices.setContentsMargins(0, 0, 0, 0)
        self.video_choices.setSpacing(SIZES.field_x_gap * 2)
        self.video_choices.addWidget(label("Video", "label"))
        self.video_choices.addStretch(1)
        self.advanced_row = QWidget()
        self.advanced_choices = QHBoxLayout(self.advanced_row)
        self.advanced_choices.setContentsMargins(0, 0, 0, 0)
        self.advanced_choices.setSpacing(SIZES.field_x_gap * 2)
        self.advanced_choices.addWidget(label("Advanced", "label"))
        self.advanced_choices.addStretch(1)
        self.projector_controls: dict[str, QCheckBox] = {}
        self.controls: dict[str, QCheckBox] = {}
        self.waiting: set[str] = set()
        # Keep status above the resizable stream/plot sections.
        self.timeline = StimulusTimeline()
        self.timeline.cards_changed.connect(self.rebuild_projector_controls)
        self.timeline.plots.removeWidget(self.timeline.motion_section)
        self.stimulus_area = StimulusPreviewArea(self.timeline)
        self.details_layout.addWidget(self.stimulus_area, 1)
        self.details.caption.setText("Stimulus")
        self.preview_host = QWidget(self)
        self.preview_layout = QVBoxLayout(self.preview_host)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.empty_hint = label("No enabled streams in this experiment.", wrap=True)
        self.empty_hint.setObjectName("PreviewWorkspaceEmpty")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_layout.addWidget(self.empty_hint)
        self.hud_card = Card("HUD", compact=True)
        self.hud_card.body.addWidget(self.hud)
        self.log_card = Card("LOG console", compact=True)
        self.log_tail = PreviewLog()
        self.log_card.body.addWidget(self.log_tail)
        # Column 0 hosts the Dashboard's own System controls while this body shows.
        for column, card in ((1, self.hud_card), (2, self.log_card)):
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            card.body.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.top.addWidget(card, 0, column)
        for column, stretch in enumerate((3, 3, 5)):
            self.top.setColumnStretch(column, stretch)
        self.timeline_card = Card("Timeline", self)
        self.timeline_card.body.addWidget(self.timeline)
        self.controls_card = Card("Preview controls", self, compact=True)
        self.controls_card.header.addWidget(self.toggle_bar)
        self.controls_card.body.addWidget(self.video_row)
        self.controls_card.body.addWidget(self.advanced_row)
        self.content.addWidget(self.top_host)
        self.content.addWidget(self.timeline_card)
        self.content.addWidget(self.controls_card)
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
        self.set_video_visible(self.video_toggle.isChecked(), close_viewers=False)
        self.set_advanced_visible(self.advanced_toggle.isChecked())
        self.video_toggle.toggled.connect(self.set_video_visible)
        self.advanced_toggle.toggled.connect(self.set_advanced_visible)
        self.views: dict[str, PreviewView] = {}
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
        # Size the projector rail once the splitter has real geometry.
        if not self._opened:
            self._opened = True
            if self.advanced_toggle.isChecked():
                self.set_advanced_visible(True)

    def set_advanced_visible(self, visible: bool, *, persist: bool = True) -> None:
        self.timeline.set_advanced(visible)
        self.details.setVisible(True)
        self.stimulus_area.rebuild()
        self.advanced_row.setVisible(visible and bool(self.projector_controls))
        if visible:
            self.split_sections()
        if persist and self.settings is not None:
            self.settings.setValue("windows/preview-advanced-visible", visible)

    def set_video_visible(self, visible: bool, *, close_viewers: bool = True) -> None:
        """Show or hide the stream section; hiding closes open viewers, not capture."""
        self.preview_host.setVisible(visible)
        self.video_row.setVisible(visible and bool(self.controls))
        if visible:
            self.split_sections()
        elif close_viewers:
            self.waiting.clear()
            for key, view in tuple(self.views.items()):
                if view.visible:
                    self.request(key, False)
            self.refresh()
        if self.settings is not None:
            self.settings.setValue("windows/preview-video-visible", visible)

    def split_sections(self) -> None:
        """Reserve a camera column beside the category-aware stimulus area."""
        if self.preview_host.isHidden() or self.details.isHidden():
            return
        width = max(1, self.splitter.width() - self.splitter.handleWidth())
        camera_width = (
            max(420 if len(self.views) > 3 else 220, width // 4)
            if hasattr(self, "views")
            else width // 4
        )
        self.splitter.setSizes([camera_width, max(1, width - camera_width)])

    def apply_views(self, views: tuple[PreviewView, ...], *, allowed: bool) -> None:
        self.allowed = allowed
        if not self.controls or tuple(self.views) != tuple(view.key for view in views):
            for widget in self.source_widgets.values():
                widget.hide()
                widget.deleteLater()
            for control in self.controls.values():
                control.hide()
                control.deleteLater()
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
                # The stream's toggle lives in the Preview controls Video row; checking it
                # opens the native viewer and gives the stream a frame.
                control = QCheckBox(view.name)
                control.setProperty("role", "viewer-toggle")
                control.setAccessibleName(view.name)
                name.setBuddy(control)
                control.clicked.connect(
                    lambda checked, key=view.key: self.request(key, checked)
                )
                hint = label("", "muted")
                row.addWidget(name, 1)
                row.addWidget(hint)
                layout.addLayout(row)
                self.video_choices.insertWidget(self.video_choices.count() - 1, control)
                panel.hide()
                self.source_widgets[view.key] = panel
                self.names[view.key] = name
                self.controls[view.key] = control
                self.hints[view.key] = hint
                self.statuses[view.key] = ""
                set_glow(name, self.glow)

        self.views = {view.key: view for view in views}
        self.stimulus_area.apply_view(self.views.get("stimulus"), allowed)
        self.waiting.intersection_update(self.views)
        self.video_row.setVisible(self.video_toggle.isChecked() and bool(self.controls))
        self.refresh()
        for key in tuple(self.waiting):
            view = self.views[key]
            if view.visible:
                self.waiting.discard(key)
            elif view.available and not view.pending:
                self.request(key, True)

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
            self.names[key].setText(stream_caption(self, view.name, wrap=True))
            control.setAccessibleName(view.name)
            if not (
                self.allowed and view.active and self.recording_enabled.get(key, True)
            ):
                self.waiting.discard(key)
            control.setChecked(view.visible or key in self.waiting)
            control.setEnabled(
                self.allowed
                and view.active
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
        had_camera_area = not self.preview_host.isHidden()
        has_camera_area = self.video_toggle.isChecked() and any(
            key != "stimulus" and (view.visible or view.pending or key in self.waiting)
            for key, view in self.views.items()
        )
        self.preview_host.setVisible(has_camera_area)
        if has_camera_area and not had_camera_area:
            self.split_sections()

    def request(self, key: str, visible: bool) -> None:
        view = self.views.get(key)
        if (
            view is None
            or not self.allowed
            or not view.active
            or view.pending
            or (visible and not self.recording_enabled.get(key, True))
        ):
            self.refresh()
            return
        if not view.available:
            if visible:
                self.waiting.add(key)
            else:
                self.waiting.discard(key)
            self.refresh()
            return
        self.waiting.discard(key)
        self.views[key] = replace(view, pending=True)
        self.refresh()
        self.visibility_requested.emit(key, visible)

    def rebuild_projector_controls(self) -> None:
        """One Advanced toggle per projector; hiding one frees its grid space."""
        for control in self.projector_controls.values():
            control.hide()
            control.deleteLater()
        self.projector_controls.clear()
        for name in self.timeline.projector_names():
            control = QCheckBox(name)
            control.setProperty("role", "viewer-toggle")
            control.setChecked(self.timeline.projector_visible(name))
            control.toggled.connect(
                lambda visible, key=name: self.timeline.set_projector_visible(
                    key, visible
                )
            )
            self.advanced_choices.insertWidget(
                self.advanced_choices.count() - 1, control
            )
            self.projector_controls[name] = control
        self.advanced_row.setVisible(
            self.advanced_toggle.isChecked() and bool(self.projector_controls)
        )


def stream_caption(owner: QWidget, name: str, *, wrap: bool = False) -> str:
    """Stream heading; with `wrap`, non-breaking spaces keep brackets with words."""
    left, right = ("<", ">") if minimal_frames(owner) else ("[", "]")
    space = "\xa0" if wrap else " "
    return f"{left}{space}{name.upper()}{space}{right}"
