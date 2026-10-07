"""Detached image-coordinate annotation tool for the Tracking frontend draft."""

from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QImage,
    QImageReader,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from cephvr.gui.components import button, combo, equal_row_height, label
from cephvr.gui.layouts import snap_tool_window
from cephvr.gui.notices import FormNotice
from cephvr.gui.theme import COLORS

POINTS = {
    "Reference points": ("Anterior", "Posterior", "Animal-left", "Animal-right"),
    "Manual pose": (
        "Posterior mantle tip",
        "Left anterior mantle tip",
        "Right anterior mantle tip",
    ),
    "Search region": (),
    "Input crop": (),
    "Distance reference": ("Point A", "Point B"),
}


class AnnotationCanvas(QWidget):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(280, 240)
        self.image = QImage()
        self.mode = "Reference points"
        self.index = 0
        self.points: dict[str, list[list[float]]] = {key: [] for key in POINTS}
        self.origin: QPointF | None = None
        self.setCursor(Qt.CursorShape.CrossCursor)

    def image_rect(self) -> QRectF:
        if self.image.isNull():
            return QRectF()
        available = QRectF(self.rect()).adjusted(20, 20, -20, -20)
        scale = min(
            available.width() / self.image.width(),
            available.height() / self.image.height(),
        )
        size = QPointF(self.image.width() * scale, self.image.height() * scale)
        return QRectF(available.center() - size / 2, available.center() + size / 2)

    def coordinate(self, point: QPointF) -> QPointF | None:
        rect = self.image_rect()
        if rect.isEmpty() or not rect.contains(point):
            return None
        return QPointF(
            min(
                self.image.width() - 1,
                (point.x() - rect.x()) / rect.width() * self.image.width(),
            ),
            min(
                self.image.height() - 1,
                (point.y() - rect.y()) / rect.height() * self.image.height(),
            ),
        )

    def mousePressEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is None or event.button() != Qt.MouseButton.LeftButton:
            return
        point = self.coordinate(event.position())
        if point is None:
            return
        if not POINTS[self.mode]:
            self.origin = point
            return
        points = self.points[self.mode]
        target = min(self.index, len(points))
        value = [round(point.x(), 1), round(point.y(), 1)]
        if target < len(points):
            points[target] = value
        else:
            points.append(value)
        self.index = min(target + 1, len(POINTS[self.mode]) - 1)
        self.changed.emit()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is None or self.origin is None:
            return
        end = self.coordinate(event.position())
        start, self.origin = self.origin, None
        if (
            end is not None
            and abs(start.x() - end.x()) >= 1
            and abs(start.y() - end.y()) >= 1
        ):
            self.points[self.mode] = [
                [round(min(start.x(), end.x())), round(min(start.y(), end.y()))],
                [round(max(start.x(), end.x())), round(max(start.y(), end.y()))],
            ]
            self.changed.emit()
            self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(COLORS.input))
        if self.image.isNull():
            painter.setPen(QColor(COLORS.muted))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Load a camera frame to place points\nand define the search region",
            )
            return
        rect = self.image_rect()
        painter.drawImage(rect, self.image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for mode, points in self.points.items():
            painter.setPen(
                QPen(
                    QColor(COLORS.accent if mode == self.mode else COLORS.projection), 2
                )
            )
            mapped = [
                QPointF(
                    rect.x() + x / self.image.width() * rect.width(),
                    rect.y() + y / self.image.height() * rect.height(),
                )
                for x, y in points
            ]
            if not POINTS[mode]:
                if len(mapped) == 2:
                    painter.drawRect(QRectF(mapped[0], mapped[1]))
                continue
            if mode == "Distance reference" and len(mapped) == 2:
                painter.drawLine(mapped[0], mapped[1])
            for index, point in enumerate(mapped):
                painter.drawEllipse(point, 5, 5)
                painter.drawText(point + QPointF(9, -9), POINTS[mode][index])


class TrackingAnnotation(QDialog):
    changed = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tracking · Reference frame")
        self.resize(850, 650)
        self.notice = FormNotice()
        self.notice.setParent(self)
        self.path = ""
        self.image_size = [0, 0]
        self.source_lineage: dict[str, int | str] | None = None
        body = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.mode = combo(tuple(POINTS))
        self.point = combo(POINTS["Reference points"])
        self.load = button("Load frame")
        self.clear = button("Clear")
        toolbar.addWidget(self.mode, 1)
        toolbar.addWidget(self.point, 1)
        toolbar.addWidget(self.load)
        toolbar.addWidget(self.clear)
        equal_row_height(self.mode, self.point, self.load, self.clear)
        body.addLayout(toolbar)
        self.canvas = AnnotationCanvas()
        body.addWidget(self.canvas, 1)
        self.caption = label(
            "Load a reference image or freeze an acquired Tracking frame.", wrap=True
        )
        body.addWidget(self.caption)
        self.mode.currentTextChanged.connect(self.select_mode)
        self.point.currentIndexChanged.connect(
            lambda index: setattr(self.canvas, "index", index)
        )
        self.canvas.changed.connect(self.updated)
        self.clear.clicked.connect(self.clear_current)
        self.load.clicked.connect(self.load_frame)

    def select_mode(self, mode: str) -> None:
        self.canvas.mode = mode
        self.point.clear()
        self.point.addItems(POINTS[mode])
        self.point.setVisible(bool(POINTS[mode]))
        self.canvas.index = 0
        self.canvas.update()

    def open_mode(self, mode: str) -> None:
        self.mode.setCurrentText(mode)
        if not self.isVisible():
            self.show()
            parent = self.parentWidget()
            assert parent is not None
            snap_tool_window(parent, self)
        self.raise_()
        self.activateWindow()

    def updated(self) -> None:
        self.point.setCurrentIndex(self.canvas.index)
        self.changed.emit()

    def clear_current(self) -> None:
        self.canvas.points[self.canvas.mode] = []
        self.canvas.index = 0
        self.updated()
        self.canvas.update()

    def reset(self) -> None:
        self.path = ""
        self.image_size = [0, 0]
        self.source_lineage = None
        self.canvas.image = QImage()
        self.canvas.points = {key: [] for key in POINTS}
        self.updated()
        self.canvas.update()

    def load_frame(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Reference frame",
            self.path,
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not path:
            return
        reader = QImageReader(path)
        size = reader.size()
        if (
            size.width() <= 0
            or size.height() <= 0
            or size.width() * size.height() > 50_000_000
        ):
            self.notice.warn(
                "Image is unreadable or exceeds 50 megapixels.", "Reference frame"
            )
            return
        image = reader.read()
        if image.isNull():
            self.notice.warn(reader.errorString(), "Reference frame")
            return
        # A different frame cannot silently inherit anatomical annotations.
        self.reset()
        self.path = path
        self.canvas.image = image
        self.image_size = [image.width(), image.height()]
        self.caption.setText(
            f"{Path(path).name} · {image.width()} × {image.height()} px · reference image"
        )
        self.canvas.update()
        self.changed.emit()

    def install_acquired_source(
        self,
        image: QImage,
        *,
        camera_serial: str,
        configuration_revision: int,
        preview_run_id: str,
        source_frame_id: int,
        source_host_receipt_ns: int,
    ) -> None:
        """Freeze one copied acquired frame and clear annotations from another source."""
        if image.isNull() or not camera_serial or not preview_run_id:
            raise ValueError("A current Tracking camera frame is required.")
        if configuration_revision <= 0 or source_frame_id < 0:
            raise ValueError("Tracking frame identity is invalid.")
        lineage: dict[str, int | str] = {
            "camera_serial": camera_serial,
            "configuration_revision": configuration_revision,
            "preview_run_id": preview_run_id,
            "source_frame_id": source_frame_id,
            "source_host_receipt_ns": source_host_receipt_ns,
        }
        if self.source_lineage != lineage or self.image_size != [
            image.width(),
            image.height(),
        ]:
            self.canvas.points = {key: [] for key in POINTS}
            self.canvas.index = 0
        self.source_lineage = lineage
        self.path = ""
        self.canvas.image = image.copy()
        self.image_size = [image.width(), image.height()]
        self.caption.setText(
            f"Frozen acquired frame · {camera_serial} · frame {source_frame_id} · "
            f"{image.width()} × {image.height()} px · configuration {configuration_revision}"
        )
        self.canvas.update()
        self.changed.emit()
