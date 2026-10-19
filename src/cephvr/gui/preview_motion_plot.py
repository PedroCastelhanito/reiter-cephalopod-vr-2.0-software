"""Read-only speed timeline and synchronized polar motion instrument."""

from dataclasses import dataclass
from math import ceil, cos, floor, log10, radians, sin

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import QWidget

from cephvr.gui.theme import colors_for
from cephvr.visual_stimulus.config.models.program_model import Settings


@dataclass(frozen=True)
class MotionEpoch:
    start: float
    end: float
    name: str
    settings: tuple[Settings, ...]


def plot_ticks(maximum: float, intervals: int = 5) -> tuple[float, ...]:
    """Round the scale to readable multiples of five or ten, with a visible zero."""
    desired = max(5.0, maximum / intervals)
    power = 10 ** floor(log10(desired))
    step = next(factor * power for factor in (1, 2, 5, 10) if factor * power >= desired)
    return tuple(
        float(index * step) for index in range(max(1, ceil(maximum / step)) + 1)
    )


def time_window(elapsed: float | None) -> tuple[float, float]:
    start = max(0.0, (elapsed or 0.0) - 30.0)
    return start, start + 30.0


class EpochStrip(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(26)
        self.epochs: tuple[MotionEpoch, ...] = ()
        self.elapsed: float | None = None
        self.setAccessibleName("Stimulus epoch markers")

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        colors = colors_for(self)
        painter.setPen(QColor(colors.muted))
        painter.drawText(4, 18, "Epoch")
        if not self.epochs:
            return
        start, end = time_window(self.elapsed)
        width = max(1, self.width() - 82)
        for index, epoch in enumerate(self.epochs):
            visible_start, visible_end = max(start, epoch.start), min(end, epoch.end)
            if visible_end <= visible_start:
                continue
            left = 64 + (visible_start - start) / (end - start) * width
            span = (visible_end - visible_start) / (end - start) * width
            rect = QRectF(left, 2, span, 22)
            painter.fillRect(rect, QColor(colors.active if index % 2 else colors.card))
            painter.setPen(QColor(colors.border))
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
            if span > 24:
                painter.setPen(QColor(colors.label))
                text = painter.fontMetrics().elidedText(
                    epoch.name, Qt.TextElideMode.ElideRight, int(span - 8)
                )
                painter.drawText(
                    rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, text
                )


class MotionPlot(QWidget):
    time_selected = pyqtSignal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(200, 140)
        self.epochs: tuple[MotionEpoch, ...] = ()
        self.traces: list[tuple[tuple[float, float], ...]] = []
        self.elapsed: float | None = None
        self.message = "Select a trial with stimulus motion."
        self.unit = "mm/s"
        self.setAccessibleName("Planned stimulus speed against trial time")

    def plot_bounds(self) -> QRectF:
        return QRectF(64, 25, max(1, self.width() - 82), max(1, self.height() - 59))

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if (
            event is not None
            and event.button() == Qt.MouseButton.LeftButton
            and self.epochs
        ):
            bounds = self.plot_bounds()
            if bounds.contains(event.position()):
                start, end = time_window(self.elapsed)
                self.time_selected.emit(
                    start
                    + (event.position().x() - bounds.left())
                    / bounds.width()
                    * (end - start)
                )
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = colors_for(self)
        painter.fillRect(self.rect(), QColor(colors.console))
        painter.setPen(QColor(colors.label))
        painter.drawText(8, 16, f"Speed ({self.unit})")
        if self.message:
            painter.setPen(QColor(colors.muted))
            painter.drawText(
                self.rect().adjusted(20, 22, -20, -8),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self.message,
            )
            return
        bounds = self.plot_bounds()
        start, end = time_window(self.elapsed)
        ticks = plot_ticks(
            max((v for trace in self.traces for _, v in trace), default=0)
        )
        padding = ticks[1] * 0.12

        def point(t: float, value: float) -> QPointF:
            return QPointF(
                bounds.left() + (t - start) / (end - start) * bounds.width(),
                bounds.bottom()
                - (value + padding) / (ticks[-1] + padding) * bounds.height(),
            )

        for value in ticks:
            y = point(0, value).y()
            painter.setPen(QPen(QColor(colors.border), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(bounds.left(), y), QPointF(bounds.right(), y))
            painter.setPen(QColor(colors.muted))
            painter.drawText(
                QRectF(0, y - 9, 54, 18), Qt.AlignmentFlag.AlignRight, f"{value:g}"
            )
        for tick_time in range(ceil(start / 5) * 5, floor(end / 5) * 5 + 1, 5):
            x = point(tick_time, 0).x()
            painter.setPen(QColor(colors.muted))
            painter.drawText(
                QRectF(x - 28, bounds.bottom() + 5, 56, 20),
                Qt.AlignmentFlag.AlignCenter,
                f"{tick_time:g}",
            )
        painter.drawText(self.width() - 70, self.height() - 2, "Time (s)")
        painter.save()
        painter.setClipRect(bounds.adjusted(0, -2, 0, 2))
        painter.setPen(QPen(QColor(colors.accent), 2))
        for trace in self.traces:
            path = QPainterPath()
            for index, (t, value) in enumerate(trace):
                if index:
                    path.lineTo(point(t, value))
                else:
                    path.moveTo(point(t, value))
            painter.drawPath(path)
        painter.restore()
        if self.elapsed is not None and start <= self.elapsed <= end:
            x = point(self.elapsed, 0).x()
            painter.setPen(QPen(QColor(colors.coral), 2))
            painter.drawLine(QPointF(x, bounds.top()), QPointF(x, bounds.bottom()))
            painter.drawText(
                QRectF(min(max(x - 32, bounds.left()), bounds.right() - 64), 3, 64, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{self.elapsed:g} s",
            )


class PolarMotionPlot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(240, 190)
        self.setMaximumWidth(340)
        self.direction: float | None = None
        self.angular_speed: float | None = None
        self.message = "Select a stimulus"
        self.rotation_message = ""
        self.setAccessibleName("Local motion direction and angular speed")
        self.setToolTip(
            "Direction uses the programmed local axes: 0° (+X) points down; 90° (+Y) points right. The outer ring shows signed angular speed, not texture angle."
        )

    @staticmethod
    def arrow(painter: QPainter, tip: QPointF, angle: float) -> None:
        back = tip - QPointF(cos(angle) * 9, -sin(angle) * 9)
        normal = QPointF(sin(angle) * 4, cos(angle) * 4)
        painter.drawPolygon(QPolygonF([tip, back + normal, back - normal]))

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = colors_for(self)
        painter.fillRect(self.rect(), QColor(colors.console))
        painter.setPen(QColor(colors.label))
        painter.drawText(
            QRectF(0, 3, self.width(), 20),
            Qt.AlignmentFlag.AlignCenter,
            "Motion direction",
        )
        radius = max(30.0, min(self.width() / 2 - 25, (self.height() - 83) / 2))
        center = QPointF(self.width() / 2, 27 + radius)
        inner = radius - 24

        def point(angle: float, distance: float) -> QPointF:
            return center + QPointF(cos(angle) * distance, -sin(angle) * distance)

        painter.setPen(QPen(QColor(colors.border), 1))
        painter.drawEllipse(center, radius, radius)
        painter.drawEllipse(center, inner, inner)
        for angle in (0, 90, 180, 270):
            rad = radians(angle - 90)
            painter.setPen(QPen(QColor(colors.border), 1))
            painter.drawLine(center, point(rad, inner))
            pos = point(rad, inner + 12)
            painter.setPen(QColor(colors.muted))
            painter.drawText(
                QRectF(pos.x() - 15, pos.y() - 8, 30, 16),
                Qt.AlignmentFlag.AlignCenter,
                str(angle),
            )
        if self.direction is not None:
            rad = radians(self.direction - 90)
            tip = point(rad, inner * 0.85)
            painter.setPen(QPen(QColor(colors.accent), 2))
            painter.setBrush(QColor(colors.accent))
            painter.drawLine(center, tip)
            self.arrow(painter, tip, rad)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.angular_speed:
            sign = 1 if self.angular_speed > 0 else -1
            angles = [radians(35 + sign * i * 3) for i in range(41)]
            path = QPainterPath(point(angles[0], radius))
            for arc_angle in angles[1:]:
                path.lineTo(point(arc_angle, radius))
            painter.setPen(QPen(QColor(colors.projection), 3))
            painter.drawPath(path)
            painter.setBrush(QColor(colors.projection))
            self.arrow(
                painter, point(angles[-1], radius), angles[-1] + sign * radians(90)
            )
        painter.setPen(QColor(colors.accent))
        text = self.message or (
            f"{self.direction % 360:.3g}°"
            if self.direction is not None
            else "No translation"
        )
        painter.drawText(
            QRectF(4, self.height() - 49, self.width() - 8, 21),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )
        painter.setPen(QColor(colors.projection))
        rotation = self.rotation_message or (
            f"Rotation {self.angular_speed:+.3g} °/s · {'CCW' if self.angular_speed > 0 else 'CW'}"
            if self.angular_speed
            else "Rotation 0 °/s"
            if self.angular_speed == 0
            else "Rotation unavailable"
        )
        painter.drawText(
            QRectF(4, self.height() - 27, self.width() - 8, 24),
            Qt.AlignmentFlag.AlignCenter,
            rotation,
        )
