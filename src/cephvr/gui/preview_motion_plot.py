"""Read-only speed timeline and synchronized polar motion instrument."""

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

from cephvr.gui.formatting import duration
from cephvr.gui.preview_motion_data import MotionEpoch, MotionTrace, PolarSample
from cephvr.gui.theme import colors_for


def plot_ticks(maximum: float, intervals: int = 5) -> tuple[float, ...]:
    """Round the scale to readable multiples of five or ten, with a visible zero."""
    desired = max(5.0, maximum / intervals)
    power = 10 ** floor(log10(desired))
    step = next(factor * power for factor in (1, 2, 5, 10) if factor * power >= desired)
    return tuple(
        float(index * step) for index in range(max(1, ceil(maximum / step)) + 1)
    )


def time_window(elapsed: float | None) -> tuple[float, float]:
    start = (elapsed or 0.0) - 15.0
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
        width = max(1, self.width() - 128)
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
        self.traces: list[MotionTrace] = []
        self.errors: list[str] = []
        self.elapsed: float | None = None
        self.message = "Select a trial with stimulus motion."
        self.setAccessibleName("Planned stimulus speed against trial time")

    def plot_bounds(self) -> QRectF:
        return QRectF(64, 25, max(1, self.width() - 128), max(1, self.height() - 59))

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
                    max(
                        0.0,
                        min(
                            self.epochs[-1].end,
                            start
                            + (event.position().x() - bounds.left())
                            / bounds.width()
                            * (end - start),
                        ),
                    )
                )
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = colors_for(self)
        painter.fillRect(self.rect(), QColor(colors.console))
        painter.setPen(QColor(colors.label))
        painter.drawText(
            70,
            16,
            "Speed"
            + (" · some sources unavailable (see legend)" if self.errors else ""),
        )
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
        units = list(dict.fromkeys(trace.unit for trace in self.traces)) or ["mm/s"]
        scales = {
            unit: plot_ticks(
                max(
                    (
                        v
                        for trace in self.traces
                        if trace.unit == unit
                        for segment in trace.segments
                        for _, v in segment
                    ),
                    default=0,
                )
            )
            for unit in units
        }

        def point(t: float, value: float, unit: str = units[0]) -> QPointF:
            ticks = scales[unit]
            padding = ticks[1] * 0.12
            return QPointF(
                bounds.left() + (t - start) / (end - start) * bounds.width(),
                bounds.bottom()
                - (value + padding) / (ticks[-1] + padding) * bounds.height(),
            )

        for axis, unit in enumerate(units):
            painter.setPen(QColor(colors.muted))
            painter.save()
            painter.translate(
                12 if axis == 0 else self.width() - 12, bounds.center().y()
            )
            painter.rotate(-90)
            painter.drawText(
                QRectF(-bounds.height() / 2, -10, bounds.height(), 20),
                Qt.AlignmentFlag.AlignCenter,
                unit,
            )
            painter.restore()
            for value in scales[unit]:
                y = point(start, value, unit).y()
                if axis == 0:
                    painter.setPen(QPen(QColor(colors.border), 1, Qt.PenStyle.DotLine))
                    painter.drawLine(
                        QPointF(bounds.left(), y), QPointF(bounds.right(), y)
                    )
                painter.setPen(QColor(colors.muted))
                painter.drawText(
                    QRectF(0 if axis == 0 else bounds.right() + 5, y - 9, 54, 18),
                    Qt.AlignmentFlag.AlignRight
                    if axis == 0
                    else Qt.AlignmentFlag.AlignLeft,
                    f"{value:g}",
                )
        label_width = painter.fontMetrics().horizontalAdvance(duration(max(0, end))) + 8
        interval = max(5, ceil(label_width * (end - start) / bounds.width() / 5) * 5)
        for tick_time in range(
            max(0, ceil(start / interval) * interval),
            floor(end / interval) * interval + 1,
            interval,
        ):
            x = point(tick_time, 0).x()
            painter.setPen(QColor(colors.muted))
            painter.drawText(
                QRectF(x - 40, bounds.bottom() + 5, 80, 20),
                Qt.AlignmentFlag.AlignCenter,
                duration(tick_time),
            )
        painter.drawText(self.width() - 125, self.height() - 2, "Time (hh:mm:ss)")
        painter.save()
        painter.setClipRect(bounds.adjusted(0, -2, 0, 2))
        for trace in self.traces:
            painter.setPen(QPen(QColor(getattr(colors, trace.color)), 2))
            previous: tuple[float, float] | None = None
            for segment in trace.segments:
                path = QPainterPath()
                for index, (t, value) in enumerate(segment):
                    if index:
                        path.lineTo(point(t, value, trace.unit))
                    elif previous is not None and previous[0] == t:
                        path.moveTo(point(*previous, trace.unit))
                        path.lineTo(point(t, value, trace.unit))
                    else:
                        path.moveTo(point(t, value, trace.unit))
                painter.drawPath(path)
                previous = segment[-1] if segment else None
                if segment and segment[-1][0] == (self.elapsed or 0.0):
                    painter.setBrush(QColor(getattr(colors, trace.color)))
                    painter.drawEllipse(point(*segment[-1], trace.unit), 2.5, 2.5)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.restore()
        if self.elapsed is not None and start <= self.elapsed <= end:
            x = point(self.elapsed, 0).x()
            painter.setPen(QPen(QColor(colors.coral), 2))
            painter.drawText(
                QRectF(min(max(x - 40, bounds.left()), bounds.right() - 80), 3, 80, 18),
                Qt.AlignmentFlag.AlignCenter,
                duration(self.elapsed),
            )


class PolarMotionPlot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(240, 190)
        self.setMaximumWidth(380)
        self.samples: list[PolarSample] = []
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
            "Direction & rotation",
        )
        footer = max(1, len(self.samples)) * 22 + 28
        radius = max(
            30.0, min(self.width() / 2 - 25, (self.height() - 32 - footer) / 2)
        )
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
        table_top = self.height() - footer
        painter.setPen(QColor(colors.border))
        painter.drawLine(12, table_top, self.width() - 12, table_top)
        painter.setPen(QColor(colors.muted))
        for left, width, title in (
            (12, self.width() * 0.4 - 12, "Source"),
            (
                self.width() * 0.4,
                self.width() * 0.23,
                "Direction" if self.width() >= 300 else "Dir.",
            ),
            (self.width() * 0.63, self.width() * 0.37 - 12, "Rotation"),
        ):
            painter.drawText(
                QRectF(left, table_top + 4, width, 18),
                Qt.AlignmentFlag.AlignLeft,
                title,
            )
        for index, sample in enumerate(self.samples):
            color = QColor(getattr(colors, sample.color))
            painter.setPen(QPen(color, 2))
            painter.setBrush(color)
            if sample.direction is not None:
                rad = radians(sample.direction - 90)
                tip = point(rad, inner * (0.9 - index * 0.08))
                painter.drawLine(center, tip)
                self.arrow(painter, tip, rad)
            if sample.angular_speed:
                sign = 1 if sample.angular_speed > 0 else -1
                ring = radius - index * 4
                angles = [radians(35 + sign * i * 3) for i in range(41)]
                path = QPainterPath(point(angles[0], ring))
                for arc_angle in angles[1:]:
                    path.lineTo(point(arc_angle, ring))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
                painter.setBrush(color)
                self.arrow(
                    painter, point(angles[-1], ring), angles[-1] + sign * radians(90)
                )
            direction = (
                f"{sample.direction:.3g}°"
                if sample.direction is not None
                else "Still"
                if sample.message == "No translation"
                else "—"
            )
            rotation = (
                f"{abs(sample.angular_speed):.3g}°/s {'CCW' if sample.angular_speed > 0 else 'CW'}"
                if sample.angular_speed
                else "0°/s"
                if sample.angular_speed == 0
                else "—"
            )
            for left, width, text in (
                (12, self.width() * 0.4 - 16, sample.name.split(" · ")[0]),
                (self.width() * 0.4, self.width() * 0.23, direction),
                (self.width() * 0.63, self.width() * 0.37 - 12, rotation),
            ):
                painter.drawText(
                    QRectF(left, table_top + 25 + index * 22, width, 20),
                    Qt.AlignmentFlag.AlignLeft,
                    painter.fontMetrics().elidedText(
                        text, Qt.TextElideMode.ElideRight, int(width)
                    ),
                )
        if not self.samples:
            painter.setPen(QColor(colors.muted))
            painter.drawText(
                QRectF(4, table_top + 25, self.width() - 8, 18),
                Qt.AlignmentFlag.AlignCenter,
                "No sources selected",
            )
