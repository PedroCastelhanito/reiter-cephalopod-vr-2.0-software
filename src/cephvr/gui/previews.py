"""In-Dashboard preview workspace; acquisition retains native windows and pixels."""

from dataclasses import replace

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
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
        self.toggle_bar.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.toolbar = QGridLayout(self.toggle_bar)
        self.toolbar.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.toolbar.setContentsMargins(0, 6, 0, 7)
        self.toolbar.setHorizontalSpacing(16)
        self.toolbar.setVerticalSpacing(6)
        self.toolbar_title = label("Previews", "eyebrow")
        self.toolbar.addWidget(self.toolbar_title, 0, 0)
        self.toolbar.setColumnStretch(3, 1)
        self.video_toggle = QCheckBox("Video")
        self.video_toggle.setAccessibleName("Video previews")
        self.video_toggle.setToolTip(
            "Show the video stream section; hiding it closes open viewers "
            "(capture continues)"
        )
        self.video_toggle.setChecked(
            settings.value("windows/preview-video-visible", True, type=bool)
            if settings is not None
            else True
        )
        self.advanced_toggle = QCheckBox("Advanced")
        self.advanced_toggle.setAccessibleName("Advanced previews")
        self.advanced_toggle.setToolTip(
            "Show stimulus preview, motion dials, arena map and size lanes"
        )
        self.advanced_toggle.setChecked(
            settings.value("windows/preview-advanced-visible", False, type=bool)
            if settings is not None
            else False
        )
        # Keep master switches visible so hidden selectors can be restored.
        self.video_row = QWidget()
        self.video_choices = QHBoxLayout(self.video_row)
        self.video_choices.setContentsMargins(0, 0, 0, 0)
        self.video_choices.setSpacing(6)
        self.video_choices.addWidget(self.video_toggle)
        self.video_choices.addStretch(1)
        self.advanced_row = QWidget()
        self.advanced_choices = QGridLayout(self.advanced_row)
        self.advanced_choices.setContentsMargins(0, 0, 0, 0)
        self.advanced_choices.setHorizontalSpacing(6)
        self.advanced_choices.setVerticalSpacing(6)
        self.advanced_controls = QWidget(self.advanced_row)
        self.advanced_control_row = QHBoxLayout(self.advanced_controls)
        self.advanced_control_row.setContentsMargins(0, 0, 0, 0)
        self.advanced_control_row.setSpacing(6)
        self.advanced_control_row.addWidget(self.advanced_toggle)
        self.plots_toggle = QPushButton("Plots")
        self.plots_toggle.setCheckable(True)
        self.plots_toggle.setChecked(True)
        self.plots_toggle.setProperty("role", "preview-choice")
        self.plots_toggle.setToolTip("Show plots for the selected projectors")
        self.advanced_control_row.addWidget(self.plots_toggle)
        self.projector_row = QWidget(self.advanced_row)
        self.projector_choices = QHBoxLayout(self.projector_row)
        self.projector_choices.setContentsMargins(0, 0, 0, 0)
        self.projector_choices.setSpacing(6)
        self.advanced_choices.addWidget(self.advanced_controls, 0, 0)
        self.advanced_choices.addWidget(self.projector_row, 0, 1)
        self.toolbar.addWidget(self.video_row, 0, 1)
        self.toolbar.addWidget(self.advanced_row, 0, 2)
        self.projector_controls: dict[str, QPushButton] = {}
        self.controls: dict[str, QPushButton] = {}
        self.waiting: set[str] = set()
        self._viewer_closures: set[str] = set()
        self.stimulus_suspended = False
        # Keep status above the resizable stream/plot sections.
        self.timeline = StimulusTimeline()
        self.timeline.cards_changed.connect(self.rebuild_projector_controls)
        self.timeline.plots.removeWidget(self.timeline.motion_section)
        self.stimulus_area = StimulusPreviewArea(self.timeline)
        self.stimulus_area.projectors_changed.connect(self.rebuild_projector_controls)
        self.details_layout.addWidget(self.stimulus_area, 1)
        self.details.caption.setText("Stimulus")
        self.preview_host = Card("Video", self, grow=True)
        self.preview_layout = self.preview_host.body
        self.preview_layout.setSpacing(SIZES.field_y_gap)
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
        self.content.addWidget(self.top_host)
        self.content.addWidget(self.timeline_card)
        self.content.addWidget(self.toggle_bar)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(16)
        self.splitter.setOpaqueResize(True)
        self.splitter.addWidget(self.preview_host)
        self.splitter.addWidget(self.details)
        self._camera_fraction = 0.5
        self.splitter.splitterMoved.connect(self._remember_split)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        handle = self.splitter.handle(1)
        assert handle is not None
        handle.setToolTip("Drag to resize previews and plots")
        self.content.addWidget(self.splitter, 1)
        self.set_video_visible(self.video_toggle.isChecked(), close_viewers=False)
        self.set_advanced_visible(self.advanced_toggle.isChecked())
        self.video_toggle.toggled.connect(self.set_video_visible)
        self.advanced_toggle.toggled.connect(self.set_advanced_visible)
        self.plots_toggle.toggled.connect(self.set_plots_visible)
        self.views: dict[str, PreviewView] = {}
        # Status text is shown inside each source's frame by the preview slot.
        self.statuses: dict[str, str] = {}
        self.hints: dict[str, QLabel] = {}
        self.names: dict[str, QLabel] = {}
        self.source_widgets: dict[str, QWidget] = {}
        self.recording_enabled: dict[str, bool] = {}
        self.allowed = False
        self.reserve_configured = False
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
        self.reflow_toolbar()

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.reflow_toolbar()

    def reflow_toolbar(self) -> None:
        """Wrap whole groups using their styled widths, without hiding switches."""
        advanced_width = self.reflow_advanced_choices()
        required = (
            self.toolbar_title.sizeHint().width()
            + (0 if self.video_row.isHidden() else self.video_row.sizeHint().width())
            + advanced_width
            + 3 * self.toolbar.horizontalSpacing()
        )
        wrapped = self.width() < required
        row, column, column_span = (1, 0, 4) if wrapped else (0, 2, 1)
        index = self.toolbar.indexOf(self.advanced_row)
        if self.toolbar.getItemPosition(index) != (row, column, 1, column_span):
            self.toolbar.removeWidget(self.advanced_row)
            self.toolbar.addWidget(self.advanced_row, row, column, 1, column_span)

    def reflow_advanced_choices(self) -> int:
        """Keep Advanced, Stimulus and Plots together; wrap projectors when needed."""
        controls = (
            self.advanced_toggle,
            self.controls.get("stimulus"),
            self.plots_toggle,
            *self.projector_controls.values(),
        )
        for control in controls:
            if control is None:
                continue
            control.ensurePolished()
        projectors_visible = any(
            not control.isHidden() for control in self.projector_controls.values()
        )
        natural_width = self.advanced_controls.sizeHint().width()
        if projectors_visible:
            natural_width += (
                self.advanced_choices.horizontalSpacing()
                + self.projector_row.sizeHint().width()
            )
        margins = self.advanced_choices.contentsMargins()
        available = max(
            1,
            self.toggle_bar.width() - margins.left() - margins.right(),
        )
        wrapped = projectors_visible and natural_width > available
        row, column, column_span = (1, 0, 2) if wrapped else (0, 1, 1)
        index = self.advanced_choices.indexOf(self.projector_row)
        if self.advanced_choices.getItemPosition(index) != (
            row,
            column,
            1,
            column_span,
        ):
            self.advanced_choices.removeWidget(self.projector_row)
            self.advanced_choices.addWidget(
                self.projector_row, row, column, 1, column_span
            )
        return natural_width

    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        # Size the projector rail once the splitter has real geometry.
        if not self._opened:
            self._opened = True
            if self.advanced_toggle.isChecked():
                self.set_advanced_visible(True)

    def set_advanced_visible(self, visible: bool, *, persist: bool = True) -> None:
        self.timeline.set_advanced(visible and self.plots_toggle.isChecked())
        self.plots_toggle.setVisible(visible)
        self.details.setVisible(True)
        self.stimulus_area.rebuild()
        for control in self.projector_controls.values():
            control.setEnabled(visible)
            control.setVisible(visible)
        if hasattr(self, "views"):
            if not visible:
                self.stimulus_suspended = False
                self.waiting.discard("stimulus")
                view = self.views.get("stimulus")
                if view is not None and (view.visible or view.pending):
                    self._viewer_closures.add("stimulus")
                    self._close_viewers()
            self.refresh()
        if visible:
            self.split_sections()
        if persist and self.settings is not None:
            self.settings.setValue("windows/preview-advanced-visible", visible)

    def set_plots_visible(self, visible: bool) -> None:
        self.timeline.set_advanced(visible and self.advanced_toggle.isChecked())
        self.stimulus_area.update_instruments()
        self.reflow_toolbar()

    def set_video_visible(self, visible: bool, *, close_viewers: bool = True) -> None:
        """Show or hide the stream section; hiding closes open viewers, not capture."""
        self.preview_host.setVisible(visible)
        if visible:
            self.split_sections()
        elif close_viewers:
            self.waiting.intersection_update({"stimulus"})
            self._viewer_closures.update(
                key
                for key, view in self.views.items()
                if key != "stimulus" and (view.visible or view.pending)
            )
            self._close_viewers()
        if hasattr(self, "views"):
            self.refresh()
        if self.settings is not None:
            self.settings.setValue("windows/preview-video-visible", visible)

    def split_sections(self) -> None:
        """Start evenly; subsequent visibility changes retain the operator's split."""
        if self.preview_host.isHidden() or self.details.isHidden():
            return
        width = max(1, self.splitter.width() - self.splitter.handleWidth())
        camera_width = round(width * self._camera_fraction)
        self.splitter.setSizes([camera_width, max(1, width - camera_width)])

    def close_viewers(self) -> None:
        """Close visible/pending viewers and cancel deferred opens, retaining layout choices."""
        self.waiting.clear()
        self.stimulus_suspended = False
        self._viewer_closures.update(
            key for key, view in self.views.items() if view.visible or view.pending
        )
        self._close_viewers()
        self.refresh()

    def _close_viewers(self) -> None:
        """Finish a hide request after any in-flight viewer command."""
        self._viewer_closures.intersection_update(self.views)
        for key in tuple(self._viewer_closures):
            view = self.views.get(key)
            if view is None:
                continue
            if view.pending:
                continue
            if not view.visible:
                self._viewer_closures.discard(key)
            elif self.allowed and view.available:
                self._viewer_closures.discard(key)
                self.request(key, False)

    def _remember_split(self, _position: int, _index: int) -> None:
        sizes = self.splitter.sizes()
        if all(sizes):
            self._camera_fraction = sizes[0] / sum(sizes)

    def apply_views(
        self,
        views: tuple[PreviewView, ...],
        *,
        allowed: bool,
        reserve_configured: bool = False,
    ) -> None:
        self.allowed = allowed
        self.reserve_configured = reserve_configured
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
                # Stimulus uses the renderer-owned rig view, alongside instruments.
                caption = {
                    "Behavior cam": "Behavior",
                    "Tracking cam": "Tracking",
                    "Visual stimulus": "Stimulus",
                }.get(view.name, view.name)
                control = QPushButton(caption)
                control.setCheckable(True)
                control.setProperty("role", "preview-choice")
                control.setAccessibleName(view.name)
                name.setBuddy(control)
                control.clicked.connect(
                    lambda checked, key=view.key: self.request(key, checked)
                )
                hint = label("", "muted")
                row.addWidget(name, 1)
                row.addWidget(hint)
                layout.addLayout(row)
                if view.key == "stimulus":
                    self.advanced_control_row.insertWidget(1, control)
                else:
                    self.video_choices.insertWidget(
                        self.video_choices.count() - 1, control
                    )
                panel.hide()
                self.source_widgets[view.key] = panel
                self.names[view.key] = name
                self.controls[view.key] = control
                self.hints[view.key] = hint
                self.statuses[view.key] = ""
                set_glow(name, self.glow)

        self.views = {view.key: view for view in views}
        if "stimulus" not in self.views:
            self.stimulus_suspended = False
        self.stimulus_area.apply_view(self.views.get("stimulus"), allowed)
        self.waiting.intersection_update(self.views)
        self.refresh()
        self.reflow_toolbar()
        camera_requested = False
        for key in self.views:
            if key not in self.waiting:
                continue
            view = self.views[key]
            if view.visible:
                self.waiting.discard(key)
            elif view.available and not view.pending:
                # Cameras share one command slot; retain the remaining selections.
                if key != "stimulus" and camera_requested:
                    continue
                self.request(key, True)
                camera_requested |= key != "stimulus"
        self.sync_projector_visibility()
        self._close_viewers()

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
                if key == "stimulus":
                    self.stimulus_suspended = False
            control.setChecked(
                view.visible
                or key in self.waiting
                or (key == "stimulus" and self.stimulus_suspended)
            )
            eligible = (
                self.allowed
                and (
                    self.advanced_toggle.isChecked()
                    if key == "stimulus"
                    else self.video_toggle.isChecked()
                )
                and view.active
                and (self.recording_enabled.get(key, True) or view.visible)
            )
            # Pending includes placement updates; keep the toolbar geometry stable.
            control.setEnabled(eligible and not view.pending)
            control.setVisible(eligible)
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
                if not view.visible or view.pending
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
            if key == "stimulus" and control.isEnabled():
                control.setToolTip(
                    "Show projection previews in the selected Combined or "
                    "Per-projector layout. " + control.toolTip()
                )
            self.names[key].setToolTip(control.toolTip())
        had_camera_area = not self.preview_host.isHidden()
        has_camera_video = any(
            key != "stimulus"
            and (
                (view.active and self.recording_enabled.get(key, True))
                or view.visible
                or view.pending
            )
            for key, view in self.views.items()
        )
        self.video_row.setVisible(has_camera_video)
        has_camera_area = self.video_toggle.isChecked() and (
            (self.reserve_configured and has_camera_video)
            or any(
                key != "stimulus"
                and (view.visible or view.pending or key in self.waiting)
                for key, view in self.views.items()
            )
        )
        self.preview_host.setVisible(has_camera_area)
        stimulus = self.views.get("stimulus")
        self.stimulus_area.set_projection_visible(
            self.advanced_toggle.isChecked()
            and bool(
                stimulus
                and (
                    stimulus.visible
                    or stimulus.pending
                    or "stimulus" in self.waiting
                    or self.stimulus_suspended
                )
            )
        )
        if has_camera_area and not had_camera_area:
            self.split_sections()
        self.reflow_toolbar()

    def request(
        self, key: str, visible: bool, *, retain_selection: bool = False
    ) -> None:
        view = self.views.get(key)
        if (
            view is None
            or not self.allowed
            or (visible and not view.active)
            or view.pending
            or (visible and not self.recording_enabled.get(key, True))
        ):
            self.refresh()
            return
        if key == "stimulus":
            if not retain_selection:
                self.stimulus_suspended = False
            if visible and not any(
                self.timeline.projector_visible(name)
                for name in self.stimulus_area.projectors
            ):
                self.stimulus_suspended = True
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

    def set_projector_visible(self, name: str, visible: bool) -> None:
        self.timeline.set_projector_visible(name, visible)
        self.stimulus_area.rebuild()
        self.sync_projector_visibility()

    def sync_projector_visibility(self) -> None:
        """Suspend the native viewer when no projector is selected, retaining intent."""
        view = self.views.get("stimulus")
        if view is None or not self.allowed or not self.advanced_toggle.isChecked():
            return
        selected = any(
            self.timeline.projector_visible(name)
            for name in self.stimulus_area.projectors
        )
        if not selected:
            self.stimulus_suspended |= (
                view.visible or view.pending or "stimulus" in self.waiting
            )
            self.waiting.discard("stimulus")
            if view.visible and not view.pending:
                self.request("stimulus", False, retain_selection=True)
        elif self.stimulus_suspended and not view.pending:
            self.stimulus_suspended = False
            self.request("stimulus", True)
        self.refresh()

    def rebuild_projector_controls(self) -> None:
        """One Advanced toggle per projector; hiding one frees its grid space."""
        if tuple(self.projector_controls) == self.stimulus_area.projectors:
            return
        for control in self.projector_controls.values():
            control.hide()
            control.deleteLater()
        self.projector_controls.clear()
        for name in self.stimulus_area.projectors:
            control = QPushButton(name)
            control.setCheckable(True)
            control.setProperty("role", "preview-choice")
            control.setEnabled(self.advanced_toggle.isChecked())
            control.setChecked(self.timeline.projector_visible(name))
            control.toggled.connect(
                lambda visible, key=name: self.set_projector_visible(key, visible)
            )
            self.projector_choices.addWidget(control)
            control.setVisible(control.isEnabled())
            self.projector_controls[name] = control
        self.reflow_toolbar()
        if hasattr(self, "views"):
            self.sync_projector_visibility()


def stream_caption(owner: QWidget, name: str, *, wrap: bool = False) -> str:
    """Stream heading; with `wrap`, non-breaking spaces keep brackets with words."""
    left, right = ("<", ">") if minimal_frames(owner) else ("[", "]")
    space = "\xa0" if wrap else " "
    return f"{left}{space}{name.upper()}{space}{right}"
