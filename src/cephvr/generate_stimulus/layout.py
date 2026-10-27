"""Shared authoring presentation using the operator GUI's native components."""

from collections.abc import Callable

import numpy as np
from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QAction, QImage, QKeySequence, QPixmap, QResizeEvent
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, button, combo, field, label
from cephvr.gui.formatting import caption_caps, card_caption
from cephvr.gui.layouts import ResponsiveColumns, column
from cephvr.gui.theme import SIZES, minimal_frames, retro_console

from .fields import humanize
from .properties import FACES
from .viewport import ArenaViewport

VIEWPORT_HINT = (
    "Drag to orbit · right-drag to pan · scroll to zoom · click a surface to select it"
)


class PreviewImage(QLabel):
    """Aspect-preserving preview of display-ready RGB8 pixels, dimmed when stale."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.pixels: np.ndarray | None = None
        self.image: QImage | None = None
        self.shown: tuple[int, int, int] | None = None
        self.dimmer = QGraphicsOpacityEffect(self)
        self.dimmer.setOpacity(0.35)
        self.dimmer.setEnabled(False)
        self.setGraphicsEffect(self.dimmer)

    def set_pixels(self, pixels: np.ndarray) -> None:
        self.pixels = np.ascontiguousarray(pixels)
        height, width = self.pixels.shape[:2]
        self.image = QImage(
            self.pixels.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888
        ).copy()
        self.shown = None
        self.refresh()

    def refresh(self) -> None:
        image = self.image
        if image is None:
            return
        ratio = self.devicePixelRatioF()
        size = self.size() * ratio
        key = (id(image), size.width(), size.height())
        if key == self.shown:
            return
        self.shown = key
        pixmap = QPixmap.fromImage(
            image.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        pixmap.setDevicePixelRatio(ratio)
        self.setPixmap(pixmap)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.refresh()


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
        actions: list[
            tuple[str, Callable[[], object], QKeySequence.StandardKey | None]
        ],
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
        self.legacy_note = label("", "error", wrap=True)
        self.legacy_note.hide()
        files.body.addWidget(self.legacy_note)
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
        self.face = combo(tuple(humanize(face) for face in FACES))
        for row_index, face in enumerate(FACES):
            self.face.setItemData(row_index, face)
        self.preview_mode = combo(("Tile preview", "Calibrated screen"))
        self.index = QSpinBox()
        self.index.setRange(0, 2**31 - 1)
        self.face_field = field("Screen", self.face)
        self.mode_field = field("View", self.preview_mode)
        self.index_field = field("Pattern index", self.index)
        self.preview_controls = QWidget()
        controls_rows = QVBoxLayout(self.preview_controls)
        controls_rows.setContentsMargins(0, 0, 0, 0)
        controls_rows.setSpacing(SIZES.body_gap)
        # Hidden fields leave no gap, so a lone View control spans the card.
        pair = QHBoxLayout()
        pair.setSpacing(SIZES.field_x_gap)
        pair.addWidget(self.face_field)
        pair.addWidget(self.mode_field)
        controls_rows.addLayout(pair)
        controls_rows.addWidget(self.index_field)
        preview.body.addWidget(self.preview_controls)
        self.preview_note = label("", "error", wrap=True)
        self.preview_note.hide()
        preview.body.addWidget(self.preview_note)
        self.fit_button = button("Fit arena")
        self.fit_button.clicked.connect(lambda: self.viewport.fit())
        self.arena_controls = QWidget()
        arena_row = QHBoxLayout(self.arena_controls)
        arena_row.setContentsMargins(0, 0, 0, 0)
        arena_row.setSpacing(SIZES.field_x_gap)
        arena_row.addWidget(label(VIEWPORT_HINT, "muted", wrap=True), 1)
        arena_row.addWidget(self.fit_button)
        preview.body.addWidget(self.arena_controls)
        self.image = PreviewImage("Edit a recipe to preview it")
        self.image.setObjectName("AssetPreviewPixels")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(140, 140)
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.viewport = ArenaViewport()
        self.viewport.setMinimumSize(80, 160)
        self.viewport.setToolTip(VIEWPORT_HINT)
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
