"""Advanced preview instruments: motion dials and the arena world map."""

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, radians, sin

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from cephvr.gui.preview_motion_data import DialSample
from cephvr.gui.theme import colors_for

AXIS_LABELS = {
    # Texture dials keep the local display: 0°/+X down and 90°/+Y right.
    "texture": ("180°", "0°", "90°", "270°"),
    "tracking": ("fwd", "back", "right", "left"),
}
TOOLTIPS = {
    "texture": "Planned local motion: 0° (+X) points down; 90° (+Y) points right. "
    "Arrow length is speed against the rings; the outer ring is signed angular speed.",
    "tracking": "Forward points up and rightward lateral motion right. Arrow length "
    "is speed against the rings; the outer ring is signed angular speed. "
    "Values: forward, animal-left, angular speed (positive CCW).",
}


def screen_vector(sample: DialSample) -> tuple[float, float]:
    """Map a sample vector to screen x-right/y-down for its dial orientation."""
    a, b = sample.vector or (0.0, 0.0)
    return (b, a) if sample.form == "texture" else (-b, -a)


def vector_text(sample: DialSample) -> str:
    if sample.message:
        return sample.message
    if sample.vector is None:
        orientation = sample.orientation_deg
        return f"0 {sample.unit}" + (
            f" · {orientation % 360:.3g}°" if orientation is not None else ""
        )
    a, b = sample.vector
    if sample.form == "texture":
        direction = degrees(atan2(b, a)) % 360
        return f"{hypot(a, b):.3g} {sample.unit} · {direction:.3g}°"
    return f"{a:.3g} · {b:.3g} {sample.unit}"


def rotation_text(sample: DialSample) -> str:
    speed = sample.angular_speed
    if speed is None:
        return "—"
    return f"{speed:.3g}°/s"


def dial_readout(sample: DialSample) -> str:
    """Keep unavailable observations explicit and numeric values on one row."""
    if sample.message:
        return sample.message
    return f"{vector_text(sample)} · {rotation_text(sample)}"


class MotionDial(QWidget):
    SIZE = 204
    HEIGHT = 232

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(self.SIZE, self.HEIGHT)
        self.sample: DialSample | None = None
        self.setAccessibleName("Motion dial")

    def set_sample(self, sample: DialSample) -> None:
        self.sample = sample
        self.setToolTip(TOOLTIPS[sample.form])
        self.setAccessibleName(f"{sample.name} motion dial")
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = colors_for(self)
        painter.fillRect(self.rect(), QColor(colors.console))
        sample = self.sample
        if sample is None:
            return
        color = QColor(getattr(colors, sample.color))
        painter.setPen(color)
        painter.drawText(
            QRectF(4, 2, self.width() - 8, 18),
            Qt.AlignmentFlag.AlignCenter,
            painter.fontMetrics().elidedText(
                sample.name, Qt.TextElideMode.ElideRight, self.width() - 8
            ),
        )
        center = QPointF(self.width() / 2, 104)
        radius = 54.0
        painter.setPen(QPen(QColor(colors.border), 1))
        painter.drawEllipse(center, radius, radius)
        painter.setPen(QPen(QColor(colors.border), 1, Qt.PenStyle.DotLine))
        painter.drawEllipse(center, radius / 2, radius / 2)
        painter.drawLine(center - QPointF(radius, 0), center + QPointF(radius, 0))
        painter.drawLine(center - QPointF(0, radius), center + QPointF(0, radius))
        painter.setPen(QColor(colors.label))
        up, down, right, left = AXIS_LABELS[sample.form]
        x, y = center.x(), center.y()
        for text, box, align in (
            (
                up,
                QRectF(x - 20, y - radius - 30, 40, 16),
                Qt.AlignmentFlag.AlignHCenter,
            ),
            (
                down,
                QRectF(x - 20, y + radius + 14, 40, 16),
                Qt.AlignmentFlag.AlignHCenter,
            ),
            (right, QRectF(x + radius + 4, y - 8, 40, 16), Qt.AlignmentFlag.AlignLeft),
            (left, QRectF(x - radius - 44, y - 8, 40, 16), Qt.AlignmentFlag.AlignRight),
        ):
            painter.drawText(box, align | Qt.AlignmentFlag.AlignVCenter, text)
        if sample.scale > 0:
            painter.drawText(
                QRectF(center.x() + 4, center.y() - radius + 2, radius, 14),
                Qt.AlignmentFlag.AlignLeft,
                f"{sample.scale:g}",
            )
        ring = radius + 9
        painter.setPen(QPen(QColor(colors.border), 4))
        painter.drawEllipse(center, ring, ring)
        if sample.angular_speed and sample.rotation_scale > 0:
            fraction = min(1.0, abs(sample.angular_speed) / sample.rotation_scale)
            sweep = max(12.0, 270 * fraction) * (1 if sample.angular_speed > 0 else -1)
            path = QPainterPath()
            path.arcMoveTo(
                QRectF(center.x() - ring, center.y() - ring, 2 * ring, 2 * ring), 90
            )
            path.arcTo(
                QRectF(center.x() - ring, center.y() - ring, 2 * ring, 2 * ring),
                90,
                sweep,
            )
            painter.setPen(QPen(color, 4, cap=Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
        if sample.vector is not None and sample.scale > 0 and not sample.message:
            dx, dy = screen_vector(sample)
            length = hypot(dx, dy)
            reach = min(1.0, length / sample.scale) * radius
            tip = center + QPointF(dx / length * reach, dy / length * reach)
            angle = atan2(dy, dx)
            painter.setPen(QPen(color, 2.5))
            painter.drawLine(center, tip)
            back = tip - QPointF(cos(angle) * 9, sin(angle) * 9)
            normal = QPointF(-sin(angle) * 4, cos(angle) * 4)
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([tip, back + normal, back - normal]))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QColor(colors.text if not sample.message else colors.label))
        text = dial_readout(sample)
        painter.drawText(
            QRectF(4, 192, self.width() - 8, 18),
            Qt.AlignmentFlag.AlignCenter,
            painter.fontMetrics().elidedText(
                text, Qt.TextElideMode.ElideRight, self.width() - 8
            ),
        )


@dataclass(frozen=True)
class MapSample:
    name: str
    color: str
    path: tuple[tuple[tuple[float, float], ...], ...]
    pose: tuple[float, float, float] | None
    extent: tuple[float, float, float, float]
    message: str = ""


class WorldMap(QWidget):
    """Top-down planned virtual-world path so far and current arena pose."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(MotionDial.SIZE, MotionDial.HEIGHT)
        self.sample: MapSample | None = None
        self.setAccessibleName("Arena world map")
        self.setToolTip("Planned virtual-world position, x right and y up, in mm.")

    def set_sample(self, sample: MapSample) -> None:
        self.sample = sample
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = colors_for(self)
        painter.fillRect(self.rect(), QColor(colors.console))
        sample = self.sample
        if sample is None:
            return
        color = QColor(getattr(colors, sample.color))
        painter.setPen(color)
        painter.drawText(
            QRectF(4, 2, self.width() - 8, 18),
            Qt.AlignmentFlag.AlignCenter,
            painter.fontMetrics().elidedText(
                f"{sample.name} · world", Qt.TextElideMode.ElideRight, self.width() - 8
            ),
        )
        frame = QRectF(12, 30, self.width() - 24, 150)
        painter.setPen(QPen(QColor(colors.border), 1))
        painter.drawRect(frame)
        left, bottom, right, top = sample.extent
        span = max(right - left, top - bottom, 1e-9)
        scale = min(frame.width(), frame.height()) * 0.9 / span
        middle = ((left + right) / 2, (bottom + top) / 2)

        def point(x: float, y: float) -> QPointF:
            return frame.center() + QPointF(
                (x - middle[0]) * scale, -(y - middle[1]) * scale
            )

        faded = QColor(color)
        faded.setAlpha(150)
        painter.setPen(QPen(faded, 1.5, Qt.PenStyle.DashLine))
        for segment in sample.path:
            if len(segment) > 1:
                path = QPainterPath(point(*segment[0]))
                for x, y in segment[1:]:
                    path.lineTo(point(x, y))
                painter.drawPath(path)
        readout = sample.message
        if sample.pose is not None and not sample.message:
            x, y, yaw = sample.pose
            heading = radians(yaw)
            # V24 forward (-sin yaw, cos yaw) in world x-right/y-up, drawn y-down.
            forward = QPointF(-sin(heading), -cos(heading))
            side = QPointF(-forward.y(), forward.x())
            tip = point(x, y)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPolygon(
                QPolygonF(
                    [
                        tip + forward * 9,
                        tip - forward * 6 + side * 5,
                        tip - forward * 6 - side * 5,
                    ]
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            readout = f"x {x:.4g} · y {y:.4g} mm · yaw {yaw % 360:.3g}°"
        painter.setPen(QColor(colors.text if not sample.message else colors.label))
        painter.drawText(
            QRectF(4, 192, self.width() - 8, 36),
            Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
            readout,
        )
