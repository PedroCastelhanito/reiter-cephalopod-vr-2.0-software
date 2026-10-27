"""Frontend shell with shared status columns and local configuration pages."""

import json

from PyQt6.QtCore import QEvent, QSettings, QSize, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.appearance import DashboardAppearance
from cephvr.gui.components import StatusColumn, button, label
from cephvr.gui.dashboard import RUNTIME_PHASES, Dashboard
from cephvr.gui.devices import DevicesPage
from cephvr.gui.gui_snapshot import GuiSnapshot, SnapshotPages
from cephvr.gui.notices import StatusEvent
from cephvr.gui.preview_placement import PreviewSlot
from cephvr.gui.protocol import ProtocolPage
from cephvr.gui.recordings import RecordingsCard
from cephvr.gui.stimulus_authoring import StimulusAuthoringPage
from cephvr.gui.theme import SIZES, load_terminal_font
from cephvr.gui.tracking import TrackingPage
from cephvr.gui.trial_preview import TrialPreview
from cephvr.gui.trial_preview_surfaces import PreviewGeometry
from cephvr.gui.view import DashboardView, Phase
from cephvr.visual_stimulus.config.models.display_profile import Geometry

PAGES = ("Dashboard", "Protocol", "Devices", "Tracking", "Generate assets")


class DashboardWindow(QMainWindow):
    def __init__(
        self,
        *,
        sample: bool = False,
        settings: QSettings | None = None,
        device_review: bool = False,
        tracking_available: bool = True,
    ) -> None:
        super().__init__()
        self.tracking_available = tracking_available
        # Font registration invalidates Qt metrics; do it before sizing controls.
        load_terminal_font()
        self.setWindowTitle(
            "CephVR2.0 — Dashboard" + (" · design review" if sample else "")
        )
        self.resize(1440, 940)
        self.setMinimumSize(720, 620)
        shell = QWidget()
        shell.setObjectName("Shell")
        self.setCentralWidget(shell)
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(SIZES.sidebar_width)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 24, 12, 18)
        sidebar_layout.setSpacing(16)
        sidebar_layout.addWidget(label("CephVR", "brand"))
        sidebar_layout.addSpacing(24)
        self.navigation = QButtonGroup(self)
        self.page_buttons = []
        for index, name in enumerate(PAGES):
            control = button(name, "navigation")
            control.setProperty(
                "iconName",
                ("dashboard", "protocol", "devices", "tracking", "geometry")[index],
            )
            control.setIconSize(QSize(20, 20))
            control.setCheckable(True)
            self.navigation.addButton(control, index)
            sidebar_layout.addWidget(control)
            self.page_buttons.append(control)
        self.page_buttons[0].setChecked(True)
        self.page_buttons[3].setVisible(tracking_available)
        sidebar_layout.addStretch()
        self.generate_stimulus_button = self.page_buttons[4]
        sidebar_layout.addWidget(label("VERSION 2.0", "muted"))
        layout.addWidget(sidebar)
        page = QWidget()
        page.setObjectName("Page")
        body = QVBoxLayout(page)
        body.setContentsMargins(*([SIZES.page_margin] * 4))
        body.setSpacing(SIZES.card_gap)
        self.page_header = QWidget()
        header = QHBoxLayout(self.page_header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(SIZES.column_gap)
        self.page_title = label("DASHBOARD", "eyebrow")
        header.addWidget(self.page_title)
        body.addWidget(self.page_header)
        self.stack = QStackedWidget()
        self.dashboard = Dashboard(sample=sample, settings=settings)
        self.dashboard_scroll = self.dashboard.scrollers[0]
        self.stack.addWidget(self.dashboard)
        self.devices = DevicesPage(
            sample=sample, settings=settings, review=device_review
        )
        for index, section in ((0, self.dashboard), (2, self.devices)):
            section.rail.setFixedWidth(SIZES.sidebar_width - 56)
            section.rail.setIconSize(QSize(16, 16))
            section.rail.setFixedHeight(40 * len(section.rail.devices))
            sidebar_layout.insertWidget(
                sidebar_layout.indexOf(self.page_buttons[index]) + 1,
                section.rail,
                alignment=Qt.AlignmentFlag.AlignRight,
            )
            section.rail.chosen.connect(
                lambda _device, _section, page=index: self.select_page(page)
            )
        self.recordings = RecordingsCard(
            self.devices.cameras, self.devices.spikeglx.pairing
        )
        dashboard_controls = self.dashboard.columns[0].layout()
        assert isinstance(dashboard_controls, QVBoxLayout)
        dashboard_controls.insertWidget(2, self.recordings)
        self.protocol = ProtocolPage(
            self.recordings, sample=sample, tracking_available=tracking_available
        )
        self.geometry_text = ""
        self.geometry_cache: Geometry | None = None
        subject_height = self.devices.projectors.rig_editor.fields["subject_z"]
        composer = self.protocol.editor.subgroup.composer
        subject_height.textChanged.connect(composer.set_subject_height)
        composer.set_subject_height(subject_height.text())
        self.trial_preview: TrialPreview | None = None
        self.protocol.editor.output_preview_requested.connect(self.open_trial_preview)
        self.protocol.editor.changed.connect(self.update_trial_preview_stale)
        self.protocol.assets.folders["root"].editor.textChanged.connect(
            lambda path: setattr(self.devices.projectors, "asset_root", path)
        )
        self.devices.projectors.asset_root = self.protocol.assets.folders[
            "root"
        ].editor.text()
        self.devices.projectors.outputs_changed.connect(
            lambda: self.protocol.editor.timeline.set_screens(
                self.devices.projectors.enabled_screens
            )
        )
        self.protocol.editor.timeline.set_screens(
            self.devices.projectors.enabled_screens
        )
        self.stack.addWidget(self.protocol)
        self.stack.addWidget(self.devices)
        self.tracking = TrackingPage(self.devices.cameras)
        self.stack.addWidget(self.tracking)
        self.authoring_page = StimulusAuthoringPage()
        self.stack.addWidget(self.authoring_page)
        self.snapshots = GuiSnapshot(
            SnapshotPages(
                self.dashboard,
                self.devices,
                self.protocol,
                self.recordings,
                self.tracking,
            )
        )
        self.config_files = self.snapshots.files(self)
        for control in (self.config_files.load_button, self.config_files.save_button):
            control.setParent(self)
            control.hide()
        header.addStretch()
        self.preview_slot = PreviewSlot()
        self.recordings.changed.connect(self.update_preview_slot)
        self.protocol.participation_changed.connect(self.update_backend_indicators)
        self.devices.cameras.drafts_changed.connect(self.update_backend_indicators)
        self.dashboard.runtime_layout_shown.connect(self.update_preview_timeline)
        self.dashboard.layout_switched.connect(self.update_preview_slot)
        self.protocol.editor.changed.connect(self.update_preview_timeline)
        body.addWidget(self.stack, 1)
        self.devices.tabs.currentChanged.connect(self.update_preview_slot)
        self.update_preview_slot()
        layout.addWidget(page, 1)
        self.navigation.idClicked.connect(self.navigate_page)
        self.apply_view(DashboardView())
        self.appearance = DashboardAppearance(
            self, self.dashboard, self.page_header, settings
        )
        self.devices.set_side_rail(True)
        self.dashboard.set_side_rail(True)
        self.refresh_side_navigation()

    def refresh_side_navigation(self) -> None:
        for index, section in ((0, self.dashboard), (2, self.devices)):
            section.rail.setVisible(section.side_rail)
            section.rail.set_navigation_active(self.stack.currentIndex() == index)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is None:
            return
        if not self.confirm_authoring_close():
            event.ignore()
            return
        self.authoring_page.shutdown()
        self.tracking.annotation.close()
        super().closeEvent(event)

    def confirm_authoring_close(self) -> bool:
        return self.authoring_page.confirm_close()

    def customEvent(self, event: QEvent | None) -> None:
        if isinstance(event, StatusEvent):
            self.dashboard.log_console.appendPlainText(event.text)
        else:
            super().customEvent(event)

    def select_page(self, index: int) -> None:
        if index == 3 and not self.tracking_available:
            return
        if index != 0 and self.dashboard.view.phase in RUNTIME_PHASES:
            self.page_buttons[self.stack.currentIndex()].setChecked(True)
            return
        if index == 4 and not self.prepare_stimulus_authoring():
            self.page_buttons[self.stack.currentIndex()].setChecked(True)
            return
        self.stack.setCurrentIndex(index)
        self.page_buttons[index].setChecked(True)
        self.page_title.setText(PAGES[index].upper())
        self.refresh_side_navigation()
        self.update_preview_slot()

    def navigate_page(self, index: int) -> None:
        if index == 0:
            self.dashboard.preview_workspace.close_viewers()
            self.dashboard.set_runtime_layout(False)
            if self.trial_preview is not None:
                self.trial_preview.close()
        self.select_page(index)

    def update_backend_indicators(self) -> None:
        indicators = self.dashboard.backend_indicators
        indicators["Cameras"].setVisible(
            any(camera.enabled for camera in self.devices.cameras.drafts)
        )
        indicators["Tracking"].setVisible(
            self.tracking_available and self.protocol.tracking_active
        )

    def update_preview_slot(self) -> None:
        page = self.stack.currentIndex()
        status: StatusColumn | None = None
        if page == 0:
            status = self.dashboard.status_column
        elif page == 2 and self.devices.tabs.currentIndex() == 0:
            status = self.devices.cameras.status_column
        elif page == 3:
            status = self.tracking.status
        workspace = self.dashboard.preview_workspace
        # The workspace hosts previews on the Dashboard only while a session runs.
        embedded = page == 0 and self.dashboard.runtime_layout
        workspace.recording_enabled = {
            camera.key: self.recordings.record[camera.key].isChecked()
            for camera in self.devices.cameras.drafts
        }
        workspace.refresh()
        host = workspace.preview_host if embedded else None if page == 0 else status
        # Park the slot in the (possibly hidden) workspace until a page hosts it.
        parking = host if host is not None else workspace.preview_host
        if self.preview_slot.parentWidget() is None or (
            host is not None and self.preview_slot.parentWidget() is not host
        ):
            column = parking.layout()
            assert isinstance(column, QVBoxLayout)
            column.addWidget(self.preview_slot, 1)
        sources = self.dashboard.view.previews
        if embedded:
            sources = tuple(source for source in sources if source.key != "stimulus")
        if embedded:
            sources = tuple(
                source
                for source in sources
                if workspace.recording_enabled.get(source.key, True)
                or source.visible
                or source.pending
            )
        workspace.empty_hint.setVisible(
            not any(item.active or item.visible or item.pending for item in sources)
        )
        if page == 2:
            enabled = {
                camera.key for camera in self.devices.cameras.drafts if camera.enabled
            }
            sources = tuple(source for source in sources if source.key in enabled)
        self.preview_slot.set_sources(
            sources,
            reserve_active=embedded,
            reserve_configured=embedded and workspace.reserve_configured,
        )
        self.preview_slot.attach_controls(workspace, external=embedded)
        for key, frame in self.preview_slot.frames.items():
            frame.snap_button.setEnabled(bool(key) and self.dashboard.view.has_control)
        for column_status in (
            self.dashboard.status_column,
            self.devices.cameras.status_column,
            self.tracking.status,
        ):
            compact = column_status is host and any(
                item.visible or item.pending for item in sources
            )
            column_status.console.set_preview_compact(compact)
            layout = column_status.layout()
            assert isinstance(layout, QVBoxLayout)
            layout.setStretchFactor(column_status.log_card, 0 if compact else 1)
        self.preview_slot.setVisible(
            host is not None
            and any(
                item.visible or item.pending or (embedded and item.active)
                for item in sources
            )
        )

    def update_preview_timeline(self) -> None:
        editor = self.protocol.editor
        view = self.dashboard.view
        # Sample views carry fixed trial numbers; show the edited draft instead.
        index = (
            view.trial_index - 1
            if view.trial_index and not view.sample
            else editor.index
        )
        timeline = self.dashboard.preview_workspace.timeline
        if not 0 <= index < len(editor.drafts):
            timeline.clear("Current trial program unavailable.")
            return
        draft = editor.drafts[index]
        try:
            geometry = self.stimulus_geometry()
        except (ValueError, TypeError):
            geometry = None
        timeline.set_program(
            draft.exported_program, draft.stimulus_seed_decimal, draft.name, geometry
        )
        self.dashboard.preview_workspace.stimulus_area.set_projectors(
            editor.timeline.screens
        )
        timeline.set_playback(
            view.elapsed_s
            if (view.connected or view.sample)
            and view.phase
            in {Phase.RUNNING, Phase.STOPPING, Phase.FINALIZING, Phase.ENDED}
            else None,
            running=(view.connected or view.sample)
            and view.phase in {Phase.RUNNING, Phase.STOPPING},
        )

    def stimulus_geometry(self) -> Geometry:
        projectors = self.devices.projectors
        profile = projectors.calibration_files.profile
        payload = (
            projectors.rig_editor.geometry_payload(projectors.screen_editor.drafts)
            if projectors._geometry_dirty or profile is None
            else profile.get("geometry")
        )
        text = json.dumps(payload)
        if text != self.geometry_text:  # Revalidate only when the inputs changed.
            self.geometry_cache = Geometry.model_validate_json(text)
            self.geometry_text = text
        assert self.geometry_cache is not None
        return self.geometry_cache

    def open_stimulus_authoring(self) -> None:
        self.select_page(4)

    def prepare_stimulus_authoring(self) -> bool:
        from pathlib import Path

        try:
            try:
                geometry = self.stimulus_geometry()
            except ValueError:
                geometry = None
            root = Path(self.protocol.assets.folders["root"].editor.text() or ".")
            self.authoring_page.open_editor(root, geometry)
            return True
        except (OSError, RuntimeError, ImportError) as error:
            QMessageBox.warning(self, "Cannot open stimulus authoring", str(error))
            return False

    def apply_view(self, view: DashboardView) -> None:
        self.dashboard.apply_view(view)
        self.devices.apply_view(view)
        self.recordings.apply_view(view)
        self.protocol.apply_view(view)
        self.tracking.apply_view(view)
        running = view.phase in RUNTIME_PHASES
        for control in (
            *self.page_buttons[1:],
            self.devices.rail,
            self.devices.tabs,
            self.devices.projectors.setup_tabs,
            self.tracking.tabs,
        ):
            control.setEnabled(not running)
        if running and self.stack.currentIndex() != 0:
            self.select_page(0)
        self.update_backend_indicators()
        self.update_preview_slot()
        if self.dashboard.runtime_layout:
            self.update_preview_timeline()
        self.config_files.set_enabled(self.snapshots.available())
        if not self.protocol.can_edit and self.trial_preview is not None:
            self.trial_preview.close()

    def update_trial_preview_stale(self) -> None:
        if self.trial_preview is not None:
            self.trial_preview.set_stale(
                self.trial_preview.program != self.protocol.editor.program
            )

    def open_trial_preview(self) -> None:
        editor = self.protocol.editor
        if self.trial_preview is not None:
            if self.trial_preview.program == editor.program:
                self.trial_preview.raise_()
                self.trial_preview.activateWindow()
                return
            self.trial_preview.close()  # Rebuild from the current program.
        if self.trial_preview is not None:
            return
        projectors = self.devices.projectors
        resolutions = {
            projectors.assignments[key]: projectors.display_pixels.get(
                key, (rect.width(), rect.height())
            )
            for key, (_, rect) in zip(
                projectors.keys, projectors.diagram.outputs, strict=True
            )
            if projectors.assignments.get(key) in editor.timeline.screens
        }
        try:
            geometry = PreviewGeometry.from_drafts(
                projectors.rig_editor.dimensions(),
                projectors.screen_editor.drafts,
                resolutions,
                projectors.timing.preview_overlays(
                    resolutions, projectors.pulse_face()
                ),
            )
            self.trial_preview = TrialPreview(
                editor.program,
                editor.timeline.screens,
                self.protocol.assets.folders["root"].editor.text(),
                geometry,
                editor,
                editor.timeline.index,
            )
        except (ValueError, OSError) as error:
            QMessageBox.information(self, "Trial preview", str(error))
            return
        self.trial_preview.finished.connect(
            lambda: setattr(self, "trial_preview", None)
        )
        self.trial_preview.refresh_requested.connect(self.open_trial_preview)
        self.trial_preview.show()
