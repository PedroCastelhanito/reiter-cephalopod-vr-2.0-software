"""Static Review instrument decoration; no device or experiment ownership."""

from math import ceil

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QPlainTextEdit, QWidget

from cephvr.gui.theme import RETRO_COLORS, retro_console


def dashed_rule(painter: QPainter, left: float, right: float, y: float) -> None:
    ink = QColor(RETRO_COLORS.border)
    ink.setAlpha(120)
    painter.setPen(QPen(ink, 1, Qt.PenStyle.DashLine))
    painter.drawLine(QPointF(left, y), QPointF(right, y))


def card_marks(painter: QPainter, frame: QRectF) -> None:
    ink = QColor(RETRO_COLORS.focus)
    ink.setAlpha(90)
    painter.setPen(QPen(ink, 1))
    for index, y in enumerate(
        range(int(frame.top()) + 24, int(frame.bottom()) - 12, 24)
    ):
        length = 8 if index % 5 == 4 else 4
        painter.drawLine(QPointF(frame.right() - length, y), QPointF(frame.right(), y))


def terminal_marks(console: QPlainTextEdit, event: QPaintEvent) -> None:
    viewport = console.viewport()
    assert viewport is not None
    painter = QPainter(viewport)
    ink = QColor(RETRO_COLORS.focus)
    ink.setAlpha(7)
    painter.setPen(ink)
    area = event.rect()
    for y in range(area.top() - area.top() % 4, area.bottom() + 1, 4):
        painter.drawLine(area.left(), y, area.right(), y)
    ink.setAlpha(70)
    painter.setPen(ink)
    for index, y in enumerate(range(8, viewport.height() - 8, 20)):
        length = 8 if index % 5 == 4 else 4
        painter.drawLine(viewport.width() - 2 - length, y, viewport.width() - 2, y)
    if console.property("terminal") == "telemetry":
        block = console.firstVisibleBlock()
        while block.isValid():
            rect = console.blockBoundingGeometry(block).translated(
                console.contentOffset()
            )
            if rect.top() > viewport.height():
                break
            if not block.text() and rect.bottom() >= 0:
                dashed_rule(painter, 4, viewport.width() - 16, rect.center().y())
            block = block.next()


class FocusBrackets(QWidget):
    """Mouse-transparent corners on an existing editor; preserve native editing."""

    def __init__(self, editor: QWidget) -> None:
        super().__init__(editor)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        editor.installEventFilter(self)
        self.refresh()

    def refresh(self) -> None:
        editor = self.parentWidget()
        assert editor is not None
        self.setGeometry(editor.rect())
        self.setVisible(
            retro_console(editor) and editor.hasFocus() and editor.isEnabled()
        )
        self.raise_()
        self.update()

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() in {
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
            QEvent.Type.Resize,
            QEvent.Type.EnabledChange,
            QEvent.Type.Show,
        }:
            self.refresh()
        return False

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor(RETRO_COLORS.accent), 2))
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        for point, dx, dy in (
            (rect.topLeft(), 1, 1),
            (rect.topRight(), -1, 1),
            (rect.bottomLeft(), 1, -1),
            (rect.bottomRight(), -1, -1),
        ):
            painter.drawLine(point, point + QPointF(7 * dx, 0))
            painter.drawLine(point, point + QPointF(0, 7 * dy))


class TrialPosition(QWidget):
    """Bounded segment count with exact current-trial text, not a completion claim."""

    def __init__(self) -> None:
        super().__init__()
        self.index = 0
        self.count = 0
        self.setFixedHeight(37)
        self.setToolTip("Current trial position in the session.")
        self.hide()

    def set_position(self, index: int, count: int) -> None:
        self.index, self.count = index, count
        self.setAccessibleName(f"Trial position {index} of {count}")
        self.setVisible(retro_console(self) and count > 0)
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        if self.count <= 0:
            return
        painter = QPainter(self)
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QColor(RETRO_COLORS.label))
        painter.drawText(0, 11, "TRIAL POSITION")
        painter.drawText(
            self.rect().adjusted(0, 0, 0, -20),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            f"{self.index} / {self.count}",
        )
        segments = min(self.count, 24)
        position = ceil(max(0, min(self.index, self.count)) * segments / self.count)
        gap = 4
        width = (self.width() - gap * (segments - 1) - 1) / segments
        for index in range(segments):
            painter.setPen(QColor(RETRO_COLORS.border))
            painter.setBrush(
                QColor(
                    RETRO_COLORS.mirror
                    if index == position - 1
                    else RETRO_COLORS.primary
                    if index < position
                    else RETRO_COLORS.input
                )
            )
            painter.drawRect(QRectF(index * (width + gap) + 0.5, 23, width, 9))
