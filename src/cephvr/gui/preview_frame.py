"""Native preview footprints and inline source-control layout."""

from math import ceil

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent, QPen, QResizeEvent
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from cephvr.gui.components import button, label
from cephvr.gui.retro_instruments import blink
from cephvr.gui.theme import colors_for, retro_console
from cephvr.platform.windows.window_coordinates import preview_frame_extra


def bracket(painter: QPainter, rect: QRect, color: str, arm: int) -> None:
    """Full-height `[ ]` edges with horizontal arms at the top and bottom."""
    painter.setPen(QPen(QColor(color), 1))
    for x, direction in ((rect.left(), 1), (rect.right(), -1)):
        painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.drawLine(x, rect.top(), x + direction * arm, rect.top())
        painter.drawLine(x, rect.bottom(), x + direction * arm, rect.bottom())


class NoSignal(QWidget):
    """Retro placeholder in the log's `-- NO ENTRIES --` idiom, above the Snap button.

    A transparent child: the native-window target paints an opaque themed background.
    """

    def __init__(self, target: QWidget, snap: QWidget) -> None:
        super().__init__(target)
        self.snap = snap
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        blink().toggled.connect(self.refresh)

    def refresh(self) -> None:
        if self.isVisible():
            self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        if not retro_console(self):
            return
        colors = colors_for(self)
        painter = QPainter(self)
        metrics = painter.fontMetrics()
        text = "-- NO SIGNAL --"
        block = metrics.horizontalAdvance(" ")
        left = (self.width() - metrics.horizontalAdvance(text) - block) // 2
        base = self.height() // 2 - self.snap.height()
        painter.setPen(QColor(colors.muted))
        painter.drawText(left, base, text)
        if blink().on:
            painter.fillRect(
                left + metrics.horizontalAdvance(text),
                base - metrics.ascent(),
                block,
                metrics.height(),
                QColor(colors.accent),
            )


class PreviewFrame(QWidget):
    """Bracketed native-window footprint, separate from the ordinary cards."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PreviewWindowFrame")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(200)
        self.setMinimumHeight(192)
        self.caption = label("[ PREVIEW ]", "eyebrow")
        self.caption.setParent(self)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header = QWidget(self)
        self.header_layout = QVBoxLayout(self.header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.header_layout.addWidget(self.caption)
        self.minimum_heading = 0
        self.target = QWidget(self)
        self.target.setObjectName("ExternalPreviewSlot")
        self.target.setAccessibleName("Preview window placement")
        self.snap_button = button("Snap")
        self.snap_button.setParent(self.target)
        self.snap_button.setToolTip("Restore this preview's grid position and size.")
        self.placeholder = NoSignal(self.target, self.snap_button)
        self.placeholder.hide()
        self.status = label("", "muted", wrap=True)
        self.status.setParent(self.target)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.hide()

    @property
    def empty(self) -> bool:
        return self.placeholder.isVisibleTo(self)

    @empty.setter
    def empty(self, value: bool) -> None:
        self.placeholder.setVisible(value)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        colors = colors_for(self)
        retro = retro_console(self)
        rect = self.target.geometry().adjusted(-2, -2, 2, 2)
        if retro:
            # Doubled corner brackets echo the Retro card frame; the native window
            # covers the interior, so the second line sits outside the footprint.
            bracket(painter, rect.adjusted(-3, -3, 3, 3), colors.border, 22)
        bracket(
            painter, rect, colors.accent if retro else colors.focus, 16 if retro else 12
        )

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.fit_target()

    def required_heading(self) -> int:
        return (
            max(
                self.header.sizeHint().height(),
                self.header_layout.totalHeightForWidth(
                    max(128, min(self.width() - 16, max(260, self.height() - 64)))
                ),
            )
            + 8
        )

    def fit_target(self) -> None:
        scale = self.devicePixelRatioF()
        extra_width, extra_height = preview_frame_extra(scale)
        width_extra, height_extra = (
            ceil(extra_width / scale),
            ceil(extra_height / scale),
        )
        heading = max(self.minimum_heading, self.required_heading())
        self.setMinimumHeight(heading + 8 + 128 + height_extra)
        side = max(
            0,
            min(
                int(2048 / scale),
                self.width() - 16 - width_extra,
                self.height() - heading - 8 - height_extra,
            ),
        )
        width = side + width_extra
        self.target.setGeometry(
            (self.width() - width) // 2,
            heading + max(0, (self.height() - heading - 8 - side - height_extra) // 2),
            width,
            side + height_extra,
        )
        header_width = max(width, min(self.width() - 16, 260))
        self.header.setGeometry(
            (self.width() - header_width) // 2, 0, header_width, heading - 8
        )
        self.header_layout.activate()
        self.placeholder.setGeometry(self.target.rect())
        self.status.setGeometry(
            8,
            8,
            max(0, self.target.width() - 16),
            max(0, self.target.height() - 16),
        )
        self.snap_button.adjustSize()
        self.snap_button.move(
            (self.target.width() - self.snap_button.width()) // 2,
            (self.target.height() - self.snap_button.height()) // 2,
        )
        self.update()
