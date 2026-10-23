"""Read-only epoch timeline and time-aligned planned value lanes."""

from collections.abc import Callable
from math import ceil, floor, log10

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QHelpEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import QToolTip, QWidget

from cephvr.gui.formatting import duration
from cephvr.gui.preview_motion_data import MotionEpoch, MotionTrace
from cephvr.gui.theme import colors_for, minimal_frames

WINDOW_S = 60.0
PLOT_LEFT = 64
# Clearance above the largest planned value so traces never sit on the frame.
HEADROOM = 1.1


def plot_ticks(maximum: float, intervals: int = 5) -> tuple[float, ...]:
    """Round the scale to readable multiples of five or ten, with a visible zero."""
    desired = max(5.0, maximum / intervals)
    power = 10 ** floor(log10(desired))
    step = next(factor * power for factor in (1, 2, 5, 10) if factor * power >= desired)
    return tuple(
        float(index * step) for index in range(max(1, ceil(maximum / step)) + 1)
    )


def time_window(elapsed: float | None) -> tuple[float, float]:
    """Pin trial start to the left edge until current time reaches the center."""
    start = max(0.0, (elapsed or 0.0) - WINDOW_S / 2)
    return start, start + WINDOW_S


def current_epoch(epochs: tuple[MotionEpoch, ...], time: float | None) -> int | None:
    if time is None:
        return None
    index = next((i for i, e in enumerate(epochs) if e.start <= time < e.end), None)
    if index is None and epochs and time == epochs[-1].end:
        return len(epochs) - 1
    return index


class TimeAxis(QWidget):
    """Shared 60 s mapping, hover readout and click-to-inspect for aligned rows."""

    time_selected = pyqtSignal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.epochs: tuple[MotionEpoch, ...] = ()
        self.elapsed: float | None = None
        self.right_margin = 24
        self.message = ""
        self.readout_lines: Callable[[float], list[str]] | None = None

    def plot_bounds(self) -> QRectF:
        return QRectF(
            PLOT_LEFT, 0, max(1, self.width() - PLOT_LEFT - self.right_margin), 1
        )

    def x_at(self, time: float) -> float:
        bounds = self.plot_bounds()
        start, end = time_window(self.elapsed)
        return bounds.left() + (time - start) / (end - start) * bounds.width()

    def time_at(self, x: float) -> float:
        bounds = self.plot_bounds()
        start, end = time_window(self.elapsed)
        time = start + (x - bounds.left()) / bounds.width() * (end - start)
        return max(0.0, min(self.epochs[-1].end, time))

    def readout(self, time: float) -> str:
        index = current_epoch(self.epochs, time)
        heading = duration(time)
        if index is not None:
            heading += f" · {self.epochs[index].name}"
        lines = [heading]
        if self.readout_lines is not None:
            lines.extend(self.readout_lines(time))
        return "\n".join(lines)

    def hovering(self, position: QPointF) -> bool:
        bounds = self.plot_bounds()
        return (
            bool(self.epochs)
            and not self.message
            and bounds.left() <= position.x() <= bounds.right()
        )

    def event(self, event: QEvent | None) -> bool:
        # Hovering replaces the static tooltip with planned values there.
        if isinstance(event, QHelpEvent) and self.hovering(QPointF(event.pos())):
            QToolTip.showText(
                event.globalPos(), self.readout(self.time_at(event.pos().x())), self
            )
            return True
        return super().event(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and QToolTip.isVisible():
            if self.hovering(event.position()):
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    self.readout(self.time_at(event.position().x())),
                    self,
                )
            else:
                QToolTip.hideText()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if (
            event is not None
            and event.button() == Qt.MouseButton.LeftButton
            and self.hovering(event.position())
        ):
            self.time_selected.emit(self.time_at(event.position().x()))
        super().mousePressEvent(event)

    def draw_cursor(self, painter: QPainter, top: float, bottom: float) -> None:
        start, end = time_window(self.elapsed)
        if self.elapsed is not None and start <= self.elapsed <= end:
            # Pixel-centre the 1 px cursor so antialiasing keeps it crisp.
            x = round(self.x_at(self.elapsed)) + 0.5
            painter.setPen(QPen(QColor(colors_for(self).label), 1))
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))


class EpochTimeline(TimeAxis):
    """Epoch blocks with current-epoch progress, a cursor and trial-time ticks."""

    STRIP_TOP = 2
    STRIP_HEIGHT = 24

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(50)
        self.setAccessibleName("Stimulus epoch timeline")

    def plot_bounds(self) -> QRectF:
        bounds = super().plot_bounds()
        return QRectF(bounds.left(), self.STRIP_TOP, bounds.width(), self.STRIP_HEIGHT)

    def tick_label(self, seconds: float) -> str:
        text = duration(seconds)
        return text if time_window(self.elapsed)[1] >= 3600 else text[3:]

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = colors_for(self)
        bounds = self.plot_bounds()
        painter.setPen(QColor(colors.label))
        painter.drawText(
            QRectF(4, bounds.top(), PLOT_LEFT - 8, bounds.height()),
            Qt.AlignmentFlag.AlignVCenter,
            "Epoch",
        )
        if self.message or not self.epochs:
            painter.drawText(
                bounds.adjusted(0, 0, 0, 24),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self.message or "No epochs",
            )
            return
        start, end = time_window(self.elapsed)
        current = current_epoch(self.epochs, self.elapsed)
        progress = QColor(colors.accent)
        progress.setAlpha(55 if minimal_frames(self) else 90)
        for index, epoch in enumerate(self.epochs):
            visible_start, visible_end = max(start, epoch.start), min(end, epoch.end)
            if visible_end <= visible_start:
                continue
            left, right = self.x_at(visible_start), self.x_at(visible_end)
            rect = QRectF(left, bounds.top(), right - left, bounds.height())
            painter.fillRect(
                rect, QColor(colors.active if index == current else colors.card)
            )
            if index == current and self.elapsed is not None:
                filled = self.x_at(min(max(self.elapsed, visible_start), visible_end))
                painter.fillRect(
                    QRectF(left, rect.top(), filled - left, rect.height()), progress
                )
                painter.setPen(QColor(colors.accent))
                painter.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
            else:
                painter.setPen(QColor(colors.border))
                painter.drawLine(rect.topLeft(), rect.bottomLeft())
            if rect.width() > 24:
                painter.setPen(
                    QColor(colors.text if index == current else colors.label)
                )
                text = painter.fontMetrics().elidedText(
                    epoch.name, Qt.TextElideMode.ElideRight, int(rect.width() - 8)
                )
                painter.drawText(
                    rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, text
                )
        painter.setPen(QColor(colors.label))
        label_width = (
            painter.fontMetrics().horizontalAdvance(self.tick_label(max(0, end))) + 16
        )
        interval = max(5, ceil(label_width * (end - start) / bounds.width() / 5) * 5)
        drawn_right = -float(label_width)
        for tick_time in range(
            max(0, ceil(start / interval) * interval),
            floor(end / interval) * interval + 1,
            interval,
        ):
            x = self.x_at(tick_time)
            text = self.tick_label(tick_time)
            half = painter.fontMetrics().horizontalAdvance(text) / 2
            # Keep edge labels on-widget; skip one that would then touch its neighbour.
            center = min(x, self.width() - half - 2)
            if center - half < drawn_right + 8:
                continue
            drawn_right = center + half
            painter.drawLine(
                QPointF(x, bounds.bottom()), QPointF(x, bounds.bottom() + 3)
            )
            painter.drawText(
                QRectF(center - 40, bounds.bottom() + 4, 80, 20),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )
        # The tick axis already gives current time, so the cursor has no label.
        self.draw_cursor(painter, 0, bounds.bottom() + 3)


class TraceLane(TimeAxis):
    """Planned value traces aligned to the epoch timeline (used for size)."""

    def __init__(self, quantity: str) -> None:
        super().__init__()
        self.quantity = quantity
        self.setFixedHeight(110)
        self.traces: list[MotionTrace] = []
        self.setAccessibleName(
            f"Planned stimulus {quantity.lower()} against trial time"
        )

    @property
    def units(self) -> list[str]:
        return list(dict.fromkeys(trace.unit for trace in self.traces)) or ["deg"]

    @property
    def lane_margin(self) -> int:
        """Reserve the right gutter only for a second unit's scale."""
        return PLOT_LEFT if len(self.units) > 1 else 24

    def plot_bounds(self) -> QRectF:
        return QRectF(
            PLOT_LEFT,
            8,
            max(1, self.width() - PLOT_LEFT - self.right_margin),
            max(1, self.height() - 16),
        )

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = colors_for(self)
        painter.fillRect(self.rect(), QColor(colors.console))
        painter.setPen(QColor(colors.label))
        if self.message:
            painter.drawText(
                self.rect().adjusted(20, 4, -20, -4),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self.message,
            )
            return
        bounds = self.plot_bounds()
        units = self.units
        scales = {
            unit: plot_ticks(
                HEADROOM
                * max(
                    (
                        v
                        for trace in self.traces
                        if trace.unit == unit
                        for segment in (*trace.segments, *trace.planned)
                        for _, v in segment
                    ),
                    default=0,
                ),
                intervals=3,
            )
            for unit in units
        }

        def point(t: float, value: float, unit: str = units[0]) -> QPointF:
            ticks = scales[unit]
            padding = ticks[1] * 0.12
            return QPointF(
                self.x_at(t),
                bounds.bottom()
                - (value + padding) / (ticks[-1] + padding) * bounds.height(),
            )

        start = time_window(self.elapsed)[0]
        for axis, unit in enumerate(units):
            painter.setPen(QColor(colors.label))
            painter.save()
            painter.translate(
                12 if axis == 0 else self.width() - 12, bounds.center().y()
            )
            painter.rotate(-90)
            painter.drawText(
                QRectF(-bounds.height() / 2, -10, bounds.height(), 20),
                Qt.AlignmentFlag.AlignCenter,
                f"{self.quantity} ({unit})",
            )
            painter.restore()
            for value in scales[unit]:
                y = point(start, value, unit).y()
                if axis == 0:
                    painter.setPen(QPen(QColor(colors.border), 1, Qt.PenStyle.DotLine))
                    painter.drawLine(
                        QPointF(bounds.left(), y), QPointF(bounds.right(), y)
                    )
                painter.setPen(QColor(colors.label))
                painter.drawText(
                    QRectF(0 if axis == 0 else bounds.right() + 5, y - 9, 54, 18),
                    Qt.AlignmentFlag.AlignRight
                    if axis == 0
                    else Qt.AlignmentFlag.AlignLeft,
                    f"{value:g}",
                )
        painter.save()
        painter.setClipRect(bounds.adjusted(0, -2, 0, 2))
        for trace in self.traces:
            color = QColor(getattr(colors, trace.color))
            planned = QColor(color)
            planned.setAlpha(110)
            for pen, segments in (
                (QPen(planned, 1.5, Qt.PenStyle.DashLine), trace.planned),
                (QPen(color, 2), trace.segments),
            ):
                painter.setPen(pen)
                previous: tuple[float, float] | None = None
                for segment in segments:
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
        painter.restore()
        self.draw_cursor(painter, bounds.top(), bounds.bottom())
