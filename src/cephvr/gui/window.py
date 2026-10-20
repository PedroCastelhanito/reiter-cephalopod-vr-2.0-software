"""Frontend shell with shared status columns and local configuration pages."""

from PyQt6.QtCore import QEvent, QSettings
from PyQt6.QtGui import QAction, QCloseEvent
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

from cephvr.gui.appearance import DashboardAppearance, load_terminal_font
from cephvr.gui.components import StatusColumn, button, label
from cephvr.gui.dashboard import Dashboard
from cephvr.gui.devices import DevicesPage
from cephvr.gui.gui_snapshot import GuiSnapshot, SnapshotPages
from cephvr.gui.notices import StatusEvent
from cephvr.gui.preview_placement import PreviewSlot
from cephvr.gui.protocol import ProtocolPage
from cephvr.gui.recordings import RecordingsCard
from cephvr.gui.theme import SIZES
from cephvr.gui.tracking import TrackingPage
from cephvr.gui.trial_preview import TrialPreview
from cephvr.gui.trial_preview_surfaces import PreviewGeometry
from cephvr.gui.view import DashboardView, Phase

PAGES = ("Dashboard", "Protocol", "Devices", "Tracking")


class DashboardWindow(QMainWindow):
    def __init__(
        self,
        *,
        sample: bool = False,
        settings: QSettings | None = None,
        device_review: bool = False,
    ) -> None:
        super().__init__()
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
        sidebar_layout.setSpacing(8)
        sidebar_layout.addWidget(label("CephVR", "brand"))
        sidebar_layout.addSpacing(24)
        self.navigation = QButtonGroup(self)
        self.page_buttons = []
        for index, name in enumerate(PAGES):
            control = button(name, "navigation")
            control.setCheckable(True)
            self.navigation.addButton(control, index)
            sidebar_layout.addWidget(control)
            self.page_buttons.append(control)
        self.page_buttons[0].setChecked(True)
        sidebar_layout.addStretch()
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
        self.recordings = RecordingsCard(
            self.devices.cameras, self.devices.spikeglx.pairing
        )
        dashboard_controls = self.dashboard.columns[0].layout()
        assert isinstance(dashboard_controls, QVBoxLayout)
        dashboard_controls.insertWidget(2, self.recordings)
        self.protocol = ProtocolPage(self.recordings, sample=sample)
        subject_height = self.devices.projectors.rig_editor.fields["subject_z"]
        composer = self.protocol.editor.subgroup.composer
        subject_height.textChanged.connect(composer.set_subject_height)
        composer.set_subject_height(subject_height.text())
        self.trial_preview: TrialPreview | None = None
        self.protocol.editor.output_preview_requested.connect(self.open_trial_preview)
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
        header.addWidget(self.dashboard.preview_button)
        self.preview_slot = PreviewSlot()
        self.recordings.changed.connect(self.update_preview_slot)
        self.dashboard.preview_dialog.opened.connect(self.update_preview_timeline)
        self.protocol.editor.changed.connect(self.update_preview_timeline)
        body.addWidget(self.stack, 1)
        self.devices.tabs.currentChanged.connect(self.update_preview_slot)
        self.update_preview_slot()
        layout.addWidget(page, 1)
        self.navigation.idClicked.connect(self.select_page)
        self.apply_view(DashboardView())
        self.appearance = DashboardAppearance(
            self, self.dashboard, self.page_header, settings
        )
        self.install_view_menu(settings)

    def install_view_menu(self, settings: QSettings | None) -> None:
        """Layout trials live in View; Style stays about appearance only."""
        menu_bar = self.menuBar()
        assert menu_bar is not None
        menu = menu_bar.addMenu("View")
        assert menu is not None
        self.side_rail_action = QAction("Devices side navigation", menu)
        self.side_rail_action.setCheckable(True)
        self.side_rail_action.setToolTip(
            "Show devices and their sections as one list beside the Devices page."
        )
        self.side_rail_action.setChecked(
            settings.value("devices/side_rail", False, type=bool) if settings else False
        )
        self.side_rail_action.toggled.connect(
            lambda enabled: self.set_side_rail(enabled, settings)
        )
        menu.addAction(self.side_rail_action)
        self.devices.set_side_rail(self.side_rail_action.isChecked())

    def set_side_rail(self, enabled: bool, settings: QSettings | None) -> None:
        self.devices.set_side_rail(enabled)
        if settings is not None:
            settings.setValue("devices/side_rail", enabled)
            settings.sync()

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self.tracking.annotation.close()
        super().closeEvent(event)

    def customEvent(self, event: QEvent | None) -> None:
        if isinstance(event, StatusEvent):
            self.dashboard.log_console.appendPlainText(event.text)
        else:
            super().customEvent(event)

    def select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.page_title.setText(PAGES[index].upper())
        self.dashboard.preview_button.setVisible(index == 0)
        self.update_preview_slot()

    def update_preview_slot(self) -> None:
        page = self.stack.currentIndex()
        status: StatusColumn | None = None
        if page == 0:
            status = self.dashboard.status_column
        elif page == 2 and self.devices.tabs.currentIndex() == 0:
            status = self.devices.cameras.status_column
        elif page == 3:
            status = self.tracking.status
        workspace = self.dashboard.preview_dialog
        workspace.recording_enabled = {
            camera.key: self.recordings.record[camera.key].isChecked()
            for camera in self.devices.cameras.drafts
        }
        workspace.refresh()
        host = workspace.preview_host if page == 0 else status
        if page != 0:
            workspace.hide()
        if host is not None and self.preview_slot.parentWidget() is not host:
            column = host.layout()
            assert isinstance(column, QVBoxLayout)
            column.addWidget(self.preview_slot, 1)
        sources = self.dashboard.view.previews
        if page == 0:
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
        self.preview_slot.set_sources(sources, reserve_active=page == 0)
        self.preview_slot.attach_controls(workspace, external=page == 0)
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
            status is not None
            and any(
                item.visible or item.pending or (page == 0 and item.active)
                for item in sources
            )
        )

    def update_preview_timeline(self) -> None:
        editor = self.protocol.editor
        view = self.dashboard.view
        index = view.trial_index - 1 if view.trial_index else editor.index
        timeline = self.dashboard.preview_dialog.timeline
        if not 0 <= index < len(editor.drafts):
            timeline.clear("Current trial program unavailable.")
            return
        draft = editor.drafts[index]
        timeline.set_program(
            draft.exported_program, draft.stimulus_seed_decimal, draft.name
        )
        timeline.set_playback(
            view.elapsed_s if view.connected or view.sample else None,
            running=(view.connected or view.sample)
            and view.phase in {Phase.RUNNING, Phase.STOPPING},
        )

    def apply_view(self, view: DashboardView) -> None:
        self.dashboard.apply_view(view)
        self.devices.apply_view(view)
        self.recordings.apply_view(view)
        self.protocol.apply_view(view)
        self.tracking.apply_view(view)
        self.update_preview_slot()
        if self.dashboard.preview_dialog.isVisible():
            self.update_preview_timeline()
        self.config_files.set_enabled(self.snapshots.available())
        if not self.protocol.can_edit and self.trial_preview is not None:
            self.trial_preview.close()

    def open_trial_preview(self) -> None:
        if self.trial_preview is not None:
            self.trial_preview.raise_()
            self.trial_preview.activateWindow()
            return
        editor = self.protocol.editor
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
        self.trial_preview.show()
