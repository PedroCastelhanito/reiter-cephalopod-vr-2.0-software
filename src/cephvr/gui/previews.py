"""External preview workspace; acquisition retains native windows and pixels."""

from dataclasses import replace

from PyQt6.QtCore import QByteArray, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QHideEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, label
from cephvr.gui.layouts import snap_tool_window
from cephvr.gui.theme import SIZES
from cephvr.gui.view import PreviewView


class PreviewDialog(QDialog):
    visibility_requested = pyqtSignal(str, bool)

    def __init__(self, parent: QWidget, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        saved = (
            settings.value("windows/preview-selector") if settings is not None else None
        )
        self.saved_geometry = saved if isinstance(saved, QByteArray) else QByteArray()
        self._opened = False
        self.setWindowTitle("Previews")
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.setMinimumSize(600, 450)
        self.resize(900, 700)
        self.setWindowModality(Qt.WindowModality.NonModal)
        body = QVBoxLayout(self)
        body.setContentsMargins(*([SIZES.compact_card_padding] * 4))
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.card = Card("Preview sources", compact=True)
        self.rows = QGridLayout()
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setHorizontalSpacing(SIZES.field_x_gap)
        self.rows.setVerticalSpacing(0)
        self.rows.setColumnStretch(0, 1)
        self.card.body.addLayout(self.rows)
        self.scroll_area.setWidget(self.card)
        self.scroll_area.setMaximumHeight(200)
        body.addWidget(self.scroll_area)
        self.preview_host = QWidget(self)
        self.preview_layout = QVBoxLayout(self.preview_host)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.empty_hint = label(
            "Select streams above to show their previews.", wrap=True
        )
        self.empty_hint.setObjectName("PreviewWorkspaceEmpty")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_layout.addWidget(self.empty_hint)
        body.addWidget(self.preview_host, 1)
        self.views: dict[str, PreviewView] = {}
        self.controls: dict[str, QCheckBox] = {}
        self.statuses: dict[str, QLabel] = {}
        self.names: dict[str, QLabel] = {}
        self.allowed = False

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
        self.raise_()
        self.activateWindow()

    def hideEvent(self, event: QHideEvent | None) -> None:
        self.saved_geometry = self.saveGeometry()
        if self.settings is not None:
            self.settings.setValue("windows/preview-selector", self.saved_geometry)
            self.settings.sync()
        super().hideEvent(event)

    def apply_views(
        self, views: tuple[PreviewView, ...], *, allowed: bool, sample: bool
    ) -> None:
        self.allowed = allowed
        self.setWindowTitle("Previews · review" if sample else "Previews")
        if not self.controls or tuple(self.views) != tuple(view.key for view in views):
            while (item := self.rows.takeAt(0)) is not None:
                if (widget := item.widget()) is not None:
                    widget.deleteLater()
            self.controls.clear()
            self.statuses.clear()
            self.names.clear()
            if views:
                self.rows.addWidget(label("SOURCE", "selector-heading"), 0, 0)
                self.rows.addWidget(label("SHOW", "selector-heading"), 0, 2)
            for index, view in enumerate(views, start=1):
                name = label(view.name, "selector-source")
                control = QCheckBox()
                control.setProperty("role", "viewer-toggle")
                control.setAccessibleName(view.name)
                name.setBuddy(control)
                control.clicked.connect(
                    lambda checked, key=view.key: self.request(key, checked)
                )
                status = label("", "muted")
                self.rows.addWidget(name, index, 0)
                self.rows.addWidget(status, index, 1)
                self.rows.addWidget(control, index, 2, Qt.AlignmentFlag.AlignCenter)
                self.names[view.key] = name
                self.controls[view.key] = control
                self.statuses[view.key] = status
            if not views:
                self.rows.addWidget(
                    label("No preview sources available.", wrap=True), 0, 0
                )

        self.views = {view.key: view for view in views}
        self.refresh()

    def refresh(self) -> None:
        for key, view in self.views.items():
            control = self.controls[key]
            self.names[key].setText(view.name)
            control.setAccessibleName(view.name)
            control.setChecked(view.visible)
            control.setEnabled(
                self.allowed and view.active and view.available and not view.pending
            )
            self.names[key].setEnabled(view.active and view.available)
            text = (
                "Waiting for viewer…"
                if view.pending
                else view.reason
                if view.reason
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
        self.card.ensurePolished()
        self.rows.invalidate()
        self.rows.activate()
        screen = self.screen()
        available = (
            screen.availableGeometry().size() if screen is not None else self.size()
        )
        margin = 2 * SIZES.compact_card_padding
        width = (
            max(
                (
                    self.names[key].sizeHint().width()
                    + 42
                    + (
                        self.statuses[key].sizeHint().width() + SIZES.field_x_gap
                        if self.statuses[key].text()
                        else 0
                    )
                    for key in self.controls
                ),
                default=220,
            )
            + margin
            + 2 * SIZES.card_padding
            + 2 * SIZES.field_x_gap
        )
        self.card.body.activate()
        height = self.card.sizeHint().height() + margin + 4
        self.scroll_area.setFixedHeight(min(height, 200))
        self.setMinimumWidth(min(max(600, width), available.width()))

    def request(self, key: str, visible: bool) -> None:
        view = self.views.get(key)
        if (
            view is None
            or not self.allowed
            or not view.active
            or not view.available
            or view.pending
        ):
            self.refresh()
            return
        self.views[key] = replace(view, pending=True)
        self.refresh()
        self.visibility_requested.emit(key, visible)
