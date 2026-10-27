"""Shared authoring presentation using the operator GUI's native components."""

from collections.abc import Callable

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QResizeEvent
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, button, combo, field
from cephvr.gui.formatting import caption_caps, card_caption
from cephvr.gui.layouts import ResponsiveColumns, column
from cephvr.gui.theme import SIZES, minimal_frames, retro_console

from .viewport import ArenaViewport


class PreviewImage(QLabel):
    resized = pyqtSignal()

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.resized.emit()


class AuthoringLayout(QMainWindow):
    def changeEvent(self, event: QEvent | None) -> None:
        super().changeEvent(event)
        if event is not None and event.type() == QEvent.Type.StyleChange:
            QTimer.singleShot(0, self.refresh_captions)

    def refresh_captions(self) -> None:
        retro = retro_console(self)
        phosphor = retro and minimal_frames(self)
        for card in self.findChildren(Card):
            title = card.property("authoringTitle")
            if title is None:
                title = card.caption.text()
                card.setProperty("authoringTitle", title)
            card.caption.setText(
                card_caption(
                    str(title),
                    retro=retro,
                    phosphor=phosphor,
                    nested=card.property("nestedCard") is True,
                )
            )
        for caption in self.findChildren(QLabel):
            if caption.property("role") != "label":
                continue
            text = caption.property("authoringLabel")
            if text is None:
                text = caption.text()
                caption.setProperty("authoringLabel", text)
            caption.setText(caption_caps(str(text)) if phosphor else str(text))

    def build_layout(
        self,
        actions: list[tuple[str, Callable[[], None], QKeySequence.StandardKey | None]],
    ) -> None:
        self.status = QStatusBar(self)
        self.status.setSizeGripEnabled(False)
        self.setStatusBar(self.status)
        controls, controls_layout = column()
        files = Card("Design files")
        grid = QGridLayout()
        grid.setSpacing(SIZES.field_x_gap)
        self.file_actions = []
        for index, (name, slot, key) in enumerate(actions):
            action = QAction(name, self)
            action.triggered.connect(slot)
            if key is not None:
                action.setShortcut(key)
                action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(action)
            control = button(name)
            control.clicked.connect(action.trigger)
            action.changed.connect(
                lambda a=action, c=control: c.setEnabled(a.isEnabled())
            )
            grid.addWidget(control, index // 2, index % 2)
            self.file_actions.append(action)
        files.body.addLayout(grid)
        controls_layout.addWidget(files)
        self.tabs = QTabBar()
        for name in ("Textures", "Arenas"):
            self.tabs.addTab(name)
        self.tabs.setExpanding(True)
        self.tabs.setDrawBase(False)
        self.tabs.setUsesScrollButtons(False)
        controls_layout.addWidget(self.tabs)
        # The column owns scrolling; only the active property content is replaced.
        self.properties = QWidget()
        self.property_layout = QVBoxLayout(self.properties)
        self.property_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(self.properties)
        controls_layout.addStretch()
        preview = Card("Preview", grow=True)
        self.face = combo(("front", "left", "right", "bottom"))
        self.preview_mode = combo(("Tile preview", "Calibrated screen"))
        self.index = QSpinBox()
        self.index.setRange(0, 2**31 - 1)
        self.face_field = field("Screen", self.face)
        self.mode_field = field("View", self.preview_mode)
        self.index_field = field("Pattern index", self.index)
        self.preview_controls = QWidget()
        row = QGridLayout(self.preview_controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SIZES.field_x_gap)
        row.addWidget(self.face_field, 0, 0)
        row.addWidget(self.mode_field, 0, 1)
        row.addWidget(self.index_field, 1, 0, 1, 2)
        preview.body.addWidget(self.preview_controls)
        self.fit_button = button("Fit arena")
        self.fit_button.clicked.connect(lambda: self.viewport.fit())
        preview.header.addWidget(self.fit_button)
        self.image = PreviewImage("Edit a recipe to preview it")
        self.image.setObjectName("AssetPreviewPixels")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(80, 80)
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.viewport = ArenaViewport()
        self.viewport.setMinimumSize(80, 80)
        preview.body.addWidget(self.image, 1)
        preview.body.addWidget(self.viewport, 1)
        self.columns = ResponsiveColumns(controls, preview)
        shell = QWidget()
        layout = QVBoxLayout(shell)
        margin = SIZES.page_margin if self.isWindow() else 0
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addWidget(self.columns)
        self.setCentralWidget(shell)

    def set_properties(self, panel: QWidget) -> None:
        while self.property_layout.count():
            item = self.property_layout.takeAt(0)
            assert item is not None
            old = item.widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        self.property_layout.addWidget(panel)
        self.refresh_captions()
