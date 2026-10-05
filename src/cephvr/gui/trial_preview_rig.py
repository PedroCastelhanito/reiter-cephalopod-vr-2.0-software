"""Rig-space playback using the device diagram's placement and rotation rules."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
    QTransform,
)

from cephvr.gui.projector_optics import Point3, ProjectionFootprint
from cephvr.gui.tank_diagram import TankDiagram
from cephvr.gui.theme import COLORS
from cephvr.gui.trial_preview_canvas import PreviewCanvas
from cephvr.gui.trial_preview_surfaces import PreviewGeometry


class PreviewRig(TankDiagram):
    def __init__(
        self, geometry: PreviewGeometry, canvases: dict[str, PreviewCanvas]
    ) -> None:
        super().__init__()
        self.snapshot = geometry
        self.rig = geometry.rig
        self.canvases = canvases
        self.frames: dict[str, QImage] = {}
        self.face_labels: dict[str, QPointF] = {}
        self.enabled_faces = tuple(canvases)
        self.visible_elements["projection"] = False
        self.visible_elements["subject"] = False
        self.setAccessibleName("Trial stimuli on configured rig screens")
        self.setToolTip("Drag to rotate · Double-click to reset view")
        # Home view keeps the rig’s Left/Right identities on their familiar image sides.
        self.azimuth = 25.0

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        super().mouseDoubleClickEvent(event)
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.azimuth = 25.0
            self.update()

    def invalidate_frames(self) -> None:
        self.frames.clear()
        self.update()

    def screen_planes(self) -> dict[str, list[Point3]]:
        return {
            face: list(surface.corners)
            for face, surface in self.snapshot.surfaces.items()
            if surface.corners
        }

    def footprints(
        self, faces: dict[str, list[Point3]]
    ) -> dict[str, ProjectionFootprint]:
        return {}

    def draw_legend(self, painter: QPainter) -> float:
        return 0.0

    def draw_screen(self, painter: QPainter, face: str, polygon: QPolygonF) -> None:
        enabled = face in self.canvases
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(COLORS.accent if enabled else COLORS.muted), 1.5))
        if enabled:
            image = self.frames[face]
            source = QPolygonF(
                [
                    QPointF(0, image.height()),
                    QPointF(image.width(), image.height()),
                    QPointF(image.width(), 0),
                    QPointF(0, 0),
                ]
            )
            transform = QTransform()
            if QTransform.quadToQuad(source, polygon, transform):
                painter.save()
                painter.setTransform(transform, True)
                painter.drawImage(QPointF(0, 0), image)
                painter.restore()
        painter.drawPolygon(polygon)
        self.face_labels[face if enabled else f"{face} · Off"] = (
            polygon.boundingRect().center()
        )
        painter.restore()

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        # Rotation reuses composed frames; only playback/media/seek invalidates them.
        for face, canvas in self.canvases.items():
            if face not in self.frames:
                self.frames[face] = canvas.frame_image()
        if self.rig is None or not self.screen_planes():
            painter = QPainter(self)
            painter.setPen(QColor(COLORS.muted))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "Configure tank, subject and screen geometry in Devices → Projectors\nto preview stimuli on the rig.",
            )
            return
        self.face_labels.clear()
        super().paintEvent(event)
        painter = QPainter(self)
        for title, center in self.face_labels.items():
            width = painter.fontMetrics().horizontalAdvance(title) + 16
            rect = QRectF(center.x() - width / 2, center.y() - 13, width, 26)
            painter.setBrush(QColor("#090f15"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 5, 5)
            painter.setPen(QColor(COLORS.text))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, title)
