"""Frontend shell with shared status columns and local configuration pages."""

from PyQt6.QtCore import QEvent, QSettings
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
from cephvr.gui.view import DashboardView

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
        self.page_layout = body
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
        self.recordings = RecordingsCard(self.devices.cameras)
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
        header_controls = (
            self.page_title,
            self.dashboard.preview_button,
        )
        for header_widget in header_controls:
            header_widget.ensurePolished()
        self.page_header.setFixedHeight(
            max(control.sizeHint().height() for control in header_controls)
        )
        self.preview_slot = PreviewSlot()
        body.addWidget(self.stack, 1)
        self.devices.tabs.currentChanged.connect(self.update_preview_slot)
        self.update_preview_slot()
        layout.addWidget(page, 1)
        self.navigation.idClicked.connect(self.select_page)
        self.apply_view(DashboardView())
        self.appearance = DashboardAppearance(
            self, self.dashboard, self.page_header, settings
        )

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
        if status is not None and self.preview_slot.parentWidget() is not status:
            column = status.layout()
            assert isinstance(column, QVBoxLayout)
            column.addWidget(self.preview_slot, 1)
        self.preview_slot.setVisible(status is not None)

    def apply_view(self, view: DashboardView) -> None:
        self.dashboard.apply_view(view)
        self.devices.apply_view(view)
        self.recordings.apply_view(view)
        self.protocol.apply_view(view)
        self.tracking.apply_view(view)
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
