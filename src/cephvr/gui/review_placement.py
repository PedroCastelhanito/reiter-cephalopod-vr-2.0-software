"""Local placement fixture showing independent screen patches, without output calls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QDialog, QGridLayout, QLabel, QVBoxLayout, QWidget

from cephvr.gui.projector_geometry import FACES
from cephvr.gui.theme import colors_for
from cephvr.visual_stimulus.rendering.photodiode import photodiode_level

if TYPE_CHECKING:
    from cephvr.gui.projector_pulses import ProjectorPulses


class ReviewPlacement(QDialog):
    def __init__(self, timing: ProjectorPulses) -> None:
        super().__init__(timing.window())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Photodiode placement · local review")
        self.resize(720, 460)
        self.timing = timing
        self.index = 0
        layout = QGridLayout(self)
        self.screens = []
        for index, face in enumerate(FACES):
            cell = QWidget()
            body = QVBoxLayout(cell)
            body.addWidget(QLabel(face))
            canvas = PulseCanvas(self, face)
            self.screens.append(canvas)
            body.addWidget(canvas, 1)
            layout.addWidget(cell, index // 2, index % 2)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(17)

    def advance(self) -> None:
        self.index += 1
        self.update_patches()

    def update_patches(self) -> None:
        for canvas in self.screens:
            canvas.update()


class PulseCanvas(QWidget):
    def __init__(self, preview: ReviewPlacement, face: str) -> None:
        super().__init__()
        self.preview = preview
        self.face = face
        self.setMinimumSize(160, 100)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(colors_for(self).window))
        timing = self.preview.timing
        try:
            size = timing.resolutions().get(self.face)
            patch = timing.patches(strict=False).get(self.face)
            if size is None or patch is None:
                return
            width, height = size
            scale = min(self.width() / width, self.height() / height)
            x = (self.width() - width * scale) / 2
            y = (self.height() - height * scale) / 2
            for rect, color in (
                (patch.background_rect, "black"),
                (
                    patch.rect,
                    "white"
                    if photodiode_level(self.preview.index, timing.pulse_mode)
                    else "black",
                ),
            ):
                if rect is not None:
                    if rect.x + rect.width > width or rect.y + rect.height > height:
                        return
                    painter.fillRect(
                        QRectF(
                            x + rect.x * scale,
                            y + (height - rect.y - rect.height) * scale,
                            rect.width * scale,
                            rect.height * scale,
                        ),
                        QColor(color),
                    )
        except ValueError:
            return
