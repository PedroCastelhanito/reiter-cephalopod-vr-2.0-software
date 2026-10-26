"""Advanced preview instruments: motion dials and the arena world map."""

from dataclasses import dataclass, replace
from math import atan2, cos, degrees, hypot, radians, sin

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from cephvr.gui.preview_motion_data import DialSample
from cephvr.gui.theme import SIZES, colors_for, minimal_frames, projector_marker_colors
from cephvr.visual_stimulus.config.rig_coordinates import signed_degrees

AXIS_LABELS = {
    # Subject directions use the same screen orientation on every projector.
    "texture": ("Front\n90°", "Back\n−90°", "Right\n0°", "Left\n180°"),
    "tracking": ("fwd", "back", "right", "left"),
}
TOOLTIPS = {
    "texture": "Planned arena motion: Back −90° down; Right 0° right; Front 90° up; Left 180° left. "
    "Each projector shows its own motion in arena coordinates. "
    "Arrow length is speed against the rings; the outer ring is signed angular speed.",
    "tracking": "Forward points up and rightward lateral motion right. Arrow length "
    "is speed against the rings; the outer ring is signed angular speed. "
    "Values: forward, animal-left, angular speed (positive CCW).",
}


def screen_vector(sample: DialSample) -> tuple[float, float]:
    """Map a sample vector to screen x-right/y-down for its dial orientation."""
    a, b = sample.vector or (0.0, 0.0)
    if sample.form == "texture":
        b *= sample.display_direction_sign
        angle = radians(sample.display_rotation_deg)
        return b * cos(angle) + a * sin(angle), a * cos(angle) - b * sin(angle)
    return -b, -a


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
        dx, dy = screen_vector(sample)
        direction = signed_degrees(degrees(atan2(-dy, dx)))
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


def instrument_painter(
    widget: QWidget,
    height: int | None = None,
    width: int = 204,
    *,
    centered: bool = False,
) -> QPainter:
    """Fit the complete instrument, including labels, without stretching its axes."""
    painter = QPainter(widget)
    height = height or MotionDial.HEIGHT
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(widget.rect(), QColor(colors_for(widget).console))
    scale = min(widget.width() / width, widget.height() / height)
    # Amber phosphor keeps instruments directly under their section heading.
    top = (
        0
        if minimal_frames(widget) and not centered
        else (widget.height() - height * scale) / 2
    )
    painter.translate((widget.width() - width * scale) / 2, top)
    painter.scale(scale, scale)
    # Match preview info text; enlarging the plot must not enlarge its lettering.
    font = QFont(widget.font())
    text_scale = max(1.0, scale)
    font.setPointSizeF(SIZES.label_font * 72 / widget.logicalDpiY() / text_scale)
    if font.letterSpacingType() == QFont.SpacingType.AbsoluteSpacing:
        font.setLetterSpacing(
            font.letterSpacingType(), font.letterSpacing() / text_scale
        )
    painter.setFont(font)
    return painter


class MotionDial(QWidget):
    SIZE = 204
    HEIGHT = 232

    def __init__(self) -> None:
        super().__init__()
        self.resize(self.SIZE, self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.sample: DialSample | None = None
        self.setAccessibleName("Motion dial")

    def sizeHint(self) -> QSize:
        return QSize(MotionDial.SIZE, MotionDial.HEIGHT)

    def set_sample(self, sample: DialSample) -> None:
        sample = replace(
            sample,
            color=projector_marker_colors(self).get(
                sample.name.split(" · ")[0], sample.color
            ),
        )
        self.sample = sample
        self.setToolTip(TOOLTIPS[sample.form])
        self.setAccessibleName(f"{sample.name} motion dial")
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = instrument_painter(self)
        colors = colors_for(self)
        sample = self.sample
        if sample is None:
            return
        center, ring, radius = self.draw_axes(painter, sample)
        self.draw_marker(painter, sample, center, ring, radius)
        painter.setPen(QColor(colors.text if not sample.message else colors.label))
        text = dial_readout(sample)
        painter.drawText(
            QRectF(4, 192, MotionDial.SIZE - 8, 18),
            Qt.AlignmentFlag.AlignCenter,
            painter.fontMetrics().elidedText(
                text, Qt.TextElideMode.ElideRight, MotionDial.SIZE - 8
            ),
        )

    def draw_axes(
        self, painter: QPainter, sample: DialSample
    ) -> tuple[QPointF, float, float]:
        colors = colors_for(self)
        center = QPointF(MotionDial.SIZE / 2, 104)
        up, down, right, left = AXIS_LABELS[sample.form]
        label_width = max(
            painter.fontMetrics().horizontalAdvance(t)
            for label in (right, left)
            for t in label.splitlines()
        )
        # Reserve text width, a 6px gap, the 2px ring stroke and 4px edge padding.
        ring = min(63.0, MotionDial.SIZE / 2 - label_width - 12)
        radius = ring - 9
        label_edge = ring + 8
        painter.setPen(QPen(QColor(colors.border), 1))
        painter.drawEllipse(center, radius, radius)
        painter.setPen(QPen(QColor(colors.border), 1, Qt.PenStyle.DotLine))
        painter.drawEllipse(center, radius / 2, radius / 2)
        painter.drawLine(center - QPointF(radius, 0), center + QPointF(radius, 0))
        painter.drawLine(center - QPointF(0, radius), center + QPointF(0, radius))
        painter.setPen(QColor(colors.label))
        x, y = center.x(), center.y()
        for text, box, align in (
            (
                up,
                QRectF(x - 24, y - label_edge - 32, 48, 32),
                Qt.AlignmentFlag.AlignHCenter,
            ),
            (
                down,
                QRectF(x - 24, y + label_edge, 48, 32),
                Qt.AlignmentFlag.AlignHCenter,
            ),
            (
                right,
                QRectF(x + label_edge, y - 16, label_width, 32),
                Qt.AlignmentFlag.AlignLeft,
            ),
            (
                left,
                QRectF(x - label_edge - label_width, y - 16, label_width, 32),
                Qt.AlignmentFlag.AlignRight,
            ),
        ):
            painter.drawText(box, align | Qt.AlignmentFlag.AlignVCenter, text)
        if sample.scale > 0:
            painter.drawText(
                QRectF(center.x() + 4, center.y() - radius + 2, radius, 14),
                Qt.AlignmentFlag.AlignLeft,
                f"{sample.scale:.1f}",
            )
        pen = QPen(QColor(colors.border), 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawEllipse(center, ring, ring)
        return center, ring, radius

    def draw_marker(
        self,
        painter: QPainter,
        sample: DialSample,
        center: QPointF,
        ring: float,
        radius: float,
    ) -> None:
        colors = colors_for(self)
        color = QColor(
            projector_marker_colors(self).get(
                sample.name.split(" · ")[0], getattr(colors, sample.color, sample.color)
            )
        )
        pen = QPen(color, 2, cap=Qt.PenCapStyle.RoundCap)
        pen.setCosmetic(True)
        head_scale = max(1.0, abs(painter.transform().m11()))

        def arrowhead(tip: QPointF, direction: QPointF) -> None:
            back = tip - direction * (7 / head_scale)
            normal = QPointF(-direction.y(), direction.x()) * (3.5 / head_scale)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([tip, back + normal, back - normal]))
            painter.setBrush(Qt.BrushStyle.NoBrush)

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
            painter.setPen(pen)
            painter.drawPath(path)
            angle = radians(90 + sweep)
            sign = 1 if sweep > 0 else -1
            arrowhead(
                path.currentPosition(), QPointF(-sin(angle) * sign, -cos(angle) * sign)
            )
        if sample.vector is not None and sample.scale > 0 and not sample.message:
            dx, dy = screen_vector(sample)
            length = hypot(dx, dy)
            if not length:
                return
            reach = min(1.0, length / sample.scale) * radius
            tip = center + QPointF(dx / length * reach, dy / length * reach)
            angle = atan2(dy, dx)
            painter.setPen(pen)
            painter.drawLine(center, tip)
            arrowhead(tip, QPointF(cos(angle), sin(angle)))


class SharedMotionDial(MotionDial):
    """Compatible vectors share axes and scales above a projector parameter table."""

    TABLE_WIDTH = 360
    HEADERS = ("Projector", "Speed", "Direction", "Angular")

    def __init__(self) -> None:
        super().__init__()
        self.samples: tuple[DialSample, ...] = ()
        self.setAccessibleName("Shared projector directions")

    def set_samples(self, samples: tuple[DialSample, ...]) -> None:
        colors = projector_marker_colors(self)
        order = {name: index for index, name in enumerate(colors)}
        samples = tuple(
            sorted(samples, key=lambda s: order.get(s.name.split(" · ")[0], 4))
        )
        self.samples = tuple(
            replace(
                sample,
                color=colors.get(sample.name.split(" · ")[0], sample.color),
            )
            for sample in samples
        )
        self.setToolTip(
            "Planned projector motion on shared axes; colors identify projectors.\n"
            + "\n".join(f"{s.name}: {dial_readout(s)}" for s in self.samples)
        )
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self.TABLE_WIDTH, 236 + len(self.samples) * 24)

    def parameter_rows(self) -> tuple[tuple[str, str, str, str], ...]:
        rows = []
        for sample in self.samples:
            name = sample.name.split(" · ")[0]
            if sample.message:
                rows.append((name, sample.message, "—", "—"))
                continue
            speed = hypot(*(sample.vector or (0.0, 0.0)))
            direction = sample.orientation_deg
            if sample.vector is not None and speed:
                dx, dy = screen_vector(sample)
                direction = signed_degrees(degrees(atan2(-dy, dx)))
            rows.append(
                (
                    name,
                    f"{speed:.3g} {sample.unit}",
                    f"{direction:.3g}°" if direction is not None else "—",
                    rotation_text(sample),
                )
            )
        return tuple(rows)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = instrument_painter(
            self, self.sizeHint().height(), self.TABLE_WIDTH, centered=True
        )
        if not self.samples:
            return
        scale = max(s.scale for s in self.samples)
        turns = max(s.rotation_scale for s in self.samples)
        common = replace(self.samples[0], scale=scale, rotation_scale=turns)
        painter.save()
        painter.translate((self.TABLE_WIDTH - self.SIZE) / 2, 0)
        center, ring, radius = self.draw_axes(painter, common)
        for index, sample in enumerate(self.samples):
            self.draw_marker(
                painter,
                replace(sample, scale=scale, rotation_scale=turns),
                center,
                ring - index * 3,
                radius,
            )
        painter.restore()
        colors = colors_for(self)
        columns = (0, 94, 194, 282, self.TABLE_WIDTH)
        for row, values in enumerate((self.HEADERS, *self.parameter_rows())):
            y = 204 + row * 24
            painter.setPen(QPen(QColor(colors.border), 1))
            painter.drawLine(QPointF(0, y + 23), QPointF(self.TABLE_WIDTH, y + 23))
            for column, text in enumerate(values):
                painter.setPen(
                    QColor(
                        colors.label
                        if row == 0
                        else projector_marker_colors(self).get(
                            self.samples[row - 1].name.split(" · ")[0],
                            self.samples[row - 1].color,
                        )
                    )
                )
                width = columns[column + 1] - columns[column] - 8
                painter.drawText(
                    QRectF(columns[column] + 4, y, width, 23),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    painter.fontMetrics().elidedText(
                        text, Qt.TextElideMode.ElideRight, width
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
        self.resize(MotionDial.SIZE, MotionDial.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.sample: MapSample | None = None
        self.setAccessibleName("Arena world map")
        self.setToolTip("Planned virtual-world position, x right and y up, in mm.")

    def sizeHint(self) -> QSize:
        return QSize(MotionDial.SIZE, MotionDial.HEIGHT)

    def set_sample(self, sample: MapSample) -> None:
        self.sample = sample
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = instrument_painter(self)
        colors = colors_for(self)
        sample = self.sample
        if sample is None:
            return
        color = QColor(getattr(colors, sample.color))
        painter.setPen(color)
        frame = QRectF(12, 30, MotionDial.SIZE - 24, 150)
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
            QRectF(4, 192, MotionDial.SIZE - 8, 36),
            Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
            readout,
        )
