"""Static Review instrument decoration; no device or experiment ownership."""

import hashlib
from collections.abc import Callable

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication,
    QPlainTextEdit,
    QRadioButton,
    QStyle,
    QStyleOptionTab,
    QTabBar,
    QWidget,
)

from cephvr.gui.log_colors import log_block_is_error
from cephvr.gui.theme import (
    PHOSPHOR_TAB_DIM,
    SIZES,
    Palette,
    minimal_frames,
    retro_colors,
    retro_console,
    retro_tints,
)


class Blink(QObject):
    """Shared cursor phase; solid when the platform disables cursor flashing."""

    toggled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(QApplication.instance())
        self.on = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        flash = QApplication.cursorFlashTime()
        if flash > 1:
            self.timer.start(flash // 2)

    def tick(self) -> None:
        self.on = not self.on
        self.toggled.emit()

    def restart(self) -> None:
        """Show the cursor solid after editing, then resume blinking."""
        self.on = True
        if self.timer.isActive():
            self.timer.start()
        self.toggled.emit()


_blink: Blink | None = None


def blink() -> Blink:
    global _blink
    if _blink is None:
        _blink = Blink()
    return _blink


def prompt_cursor(console: QPlainTextEdit) -> None:
    """Block cursor after the last log line, or after the empty-log placeholder."""
    document = console.document()
    viewport = console.viewport()
    assert document is not None and viewport is not None
    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.MoveOperation.End)
    rect = console.cursorRect(cursor)
    if document.isEmpty():
        rect.translate(
            console.fontMetrics().horizontalAdvance(console.placeholderText()), 0
        )
    block = QRectF(
        rect.left(),
        rect.top(),
        console.fontMetrics().horizontalAdvance(" "),
        rect.height(),
    )
    if viewport.rect().contains(block.toRect()):
        QPainter(viewport).fillRect(block, QColor(retro_colors(console).accent))


def tile_tint(key: str, owner: QWidget) -> QColor:
    """Stable identity tint for a stimulus type, drawn from the Retro tint set."""
    index = int.from_bytes(hashlib.sha256(key.encode()).digest()[:2], "big")
    tints = retro_tints(owner)
    return QColor(tints[index % len(tints)])


def blend(base: str, ink: QColor, amount: float) -> QColor:
    """Mix ink into a surface color; amount 0 is the surface, 1 is the ink."""
    surface = QColor(base)
    return QColor.fromRgbF(
        *(
            getattr(surface, channel)() * (1 - amount)
            + getattr(ink, channel)() * amount
            for channel in ("redF", "greenF", "blueF")
        )
    )


def unselected_epoch_brush(tint: QColor, colors: Palette) -> QColor:
    """Dim tinted fill for an unselected Retro epoch tile."""
    return blend(colors.card, tint, 0.18)


def dashed_rule(
    painter: QPainter, colors: Palette, left: float, right: float, y: float
) -> None:
    ink = QColor(colors.border)
    ink.setAlpha(120)
    painter.setPen(QPen(ink, 1, Qt.PenStyle.DashLine))
    painter.drawLine(QPointF(left, y), QPointF(right, y))


def card_marks(painter: QPainter, frame: QRectF, colors: Palette) -> None:
    ink = QColor(colors.focus)
    ink.setAlpha(90)
    painter.setPen(QPen(ink, 1))
    for index, y in enumerate(
        range(int(frame.top()) + 24, int(frame.bottom()) - 12, 24)
    ):
        length = 8 if index % 5 == 4 else 4
        painter.drawLine(QPointF(frame.right() - length, y), QPointF(frame.right(), y))


def corner_brackets(
    painter: QPainter, frame: QRectF, ink: QColor, length: float = 16
) -> None:
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(ink, 1))
    for point, dx, dy in (
        (frame.topLeft(), 1, 1),
        (frame.topRight(), -1, 1),
        (frame.bottomLeft(), 1, -1),
        (frame.bottomRight(), -1, -1),
    ):
        painter.drawLine(point, point + QPointF(length * dx, 0))
        painter.drawLine(point, point + QPointF(0, length * dy))


def centre_segments(painter: QPainter, frame: QRectF, ink: QColor) -> None:
    """Short centred edge lines for open instrument frames (30% of each edge)."""
    painter.setPen(QPen(ink, 1))
    centre, half_x, half_y = frame.center(), frame.width() * 0.15, frame.height() * 0.15
    for y in (frame.top(), frame.bottom()):
        painter.drawLine(
            QPointF(centre.x() - half_x, y), QPointF(centre.x() + half_x, y)
        )
    for x in (frame.left(), frame.right()):
        painter.drawLine(
            QPointF(x, centre.y() - half_y), QPointF(x, centre.y() + half_y)
        )


def double_frame(painter: QPainter, frame: QRectF, owner: QWidget) -> None:
    """Retro card extras inside an already drawn outline: inner line, marks, corners.
    Amber phosphor adds bright corner brackets; open frames (`openFrame`) replace the
    outline with centred edge segments."""
    colors = retro_colors(owner)
    if minimal_frames(owner):
        if owner.property("openFrame") is True:
            centre_segments(painter, frame, QColor(colors.border))
        corner_brackets(painter, frame, QColor(colors.accent))
        return
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(colors.border), 1))
    painter.drawRect(frame.adjusted(3, 3, -3, -3))
    card_marks(painter, frame, colors)
    painter.setPen(QPen(QColor(colors.accent), 1))
    for corner, direction in ((frame.bottomLeft(), 1), (frame.bottomRight(), -1)):
        painter.drawLine(corner, corner + QPointF(9 * direction, 0))
        painter.drawLine(corner, corner + QPointF(0, -9))


def terminal_marks(console: QPlainTextEdit, event: QPaintEvent) -> None:
    viewport = console.viewport()
    assert viewport is not None
    painter = QPainter(viewport)
    colors = retro_colors(console)
    ink = QColor(colors.focus)
    ink.setAlpha(70)
    painter.setPen(ink)
    for index, y in enumerate(range(8, viewport.height() - 8, 20)):
        length = 8 if index % 5 == 4 else 4
        painter.drawLine(viewport.width() - 2 - length, y, viewport.width() - 2, y)
    if console.property("terminal") != "telemetry":
        return
    block = console.firstVisibleBlock()
    while block.isValid():
        rect = console.blockBoundingGeometry(block).translated(console.contentOffset())
        if rect.top() > viewport.height():
            break
        if rect.bottom() >= 0 and not block.text():
            dashed_rule(painter, colors, 4, viewport.width() - 16, rect.center().y())
        block = block.next()


class PromptGutter(QWidget):
    """'>' column in a console's left viewport margin; text blocks stay unmodified."""

    def __init__(self, console: QPlainTextEdit) -> None:
        super().__init__(console)
        self.console = console
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        console.updateRequest.connect(lambda *_: self.update())
        self.hide()

    def place(self, width: int) -> None:
        viewport = self.console.viewport()
        assert viewport is not None
        self.setGeometry(viewport.x() - width, viewport.y(), width, viewport.height())
        self.setVisible(width > 0)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        console = self.console
        painter = QPainter(self)
        painter.setFont(console.font())
        telemetry = console.property("terminal") == "telemetry"
        colors = retro_colors(console)
        block = console.firstVisibleBlock()
        while block.isValid():
            rect = console.blockBoundingGeometry(block).translated(
                console.contentOffset()
            )
            if rect.top() > self.height():
                break
            layout = block.layout()
            if rect.bottom() >= 0 and block.text() and layout and layout.lineCount():
                line = layout.lineAt(0)
                error = not telemetry and log_block_is_error(block)
                painter.setPen(QColor(colors.error if error else colors.console_text))
                painter.drawText(QPointF(2, rect.top() + line.y() + line.ascent()), ">")
            block = block.next()


class TabMarkers(QWidget):
    """Amber tabs have a leading `>` and a coral trailing `<` when selected. Tabs keep native
    behaviour and text; `hover_changed` lets the owner recolour icons."""

    hover_changed = pyqtSignal()

    def __init__(self, bar: QTabBar) -> None:
        super().__init__(bar)
        self.bar = bar
        self.hover = -1
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        bar.setMouseTracking(True)
        bar.installEventFilter(self)
        bar.currentChanged.connect(lambda *_: self.update())
        self.setGeometry(bar.rect())

    def set_hover(self, index: int) -> None:
        if index != self.hover:
            self.hover = index
            self.update()
            self.hover_changed.emit()

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if event is not None:
            kind = event.type()
            if kind in {QEvent.Type.Resize, QEvent.Type.Show}:
                self.setGeometry(self.bar.rect())
                self.raise_()
            elif kind == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
                self.set_hover(self.bar.tabAt(event.position().toPoint()))
            elif kind == QEvent.Type.Leave:
                self.set_hover(-1)
        return False

    def marker_rect(self, index: int, *, trailing: bool = False) -> QRectF:
        """Equal gaps around Qt's rendered tab title, including its icon."""
        option = QStyleOptionTab()
        self.bar.initStyleOption(option, index)
        style = self.bar.style()
        assert style is not None
        rect = style.subElementRect(
            QStyle.SubElement.SE_TabBarTabText, option, self.bar
        )
        metrics = self.bar.fontMetrics()
        text = metrics.elidedText(option.text, self.bar.elideMode(), rect.width())
        width = metrics.horizontalAdvance(text)
        left = rect.center().x() - width / 2
        right = rect.center().x() + width / 2
        if not option.icon.isNull():
            left -= option.iconSize.width() + 4
        left = right + 6 if trailing else left - 6 - 12
        return QRectF(left, rect.top(), 12, rect.height())

    def paintEvent(self, event: QPaintEvent | None) -> None:
        if not minimal_frames(self.bar):
            return
        colors = retro_colors(self.bar)
        painter = QPainter(self)
        font = QFont(self.bar.font())
        font.setPixelSize(SIZES.label_font + 3)
        painter.setFont(font)
        current = self.bar.currentIndex()
        for index in range(self.bar.count()):
            ink = (
                colors.coral
                if index == current
                else colors.text
                if index == self.hover
                else PHOSPHOR_TAB_DIM
            )
            painter.setPen(QColor(ink))
            painter.drawText(
                self.marker_rect(index),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                ">",
            )
            if index == current:
                painter.drawText(
                    self.marker_rect(index, trailing=True),
                    Qt.AlignmentFlag.AlignVCenter,
                    "<",
                )


class ColumnHeader(QWidget):
    """Dim column titles in a log's top viewport margin, aligned to its text columns.

    The owner supplies the titles so category-width changes realign them; log text
    blocks are never modified."""

    def __init__(self, console: QPlainTextEdit, titles: Callable[[], str]) -> None:
        super().__init__(console)
        self.console = console
        self.titles = titles
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        console.updateRequest.connect(lambda *_: self.update())
        self.hide()

    def place(self, height: int) -> None:
        viewport = self.console.viewport()
        assert viewport is not None
        self.setGeometry(0, viewport.y() - height, self.console.width(), height)
        self.setVisible(height > 0)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        console = self.console
        viewport = console.viewport()
        document = console.document()
        assert viewport is not None and document is not None
        colors = retro_colors(console)
        painter = QPainter(self)
        painter.setFont(console.font())
        ink = QColor(colors.muted)
        ink.setAlpha(170)
        painter.setPen(ink)
        left = viewport.x() + document.documentMargin()
        baseline = (self.height() + console.fontMetrics().ascent()) / 2 - 2
        painter.drawText(QPointF(left, baseline), self.titles())
        rule = QColor(colors.border)
        painter.setPen(QPen(rule, 1, Qt.PenStyle.DashLine))
        painter.drawLine(
            QPointF(left, self.height() - 1.5),
            QPointF(self.width() - 16, self.height() - 1.5),
        )


def paint_status_lamp(indicator: QRadioButton, status: str) -> None:
    colors = retro_colors(indicator)
    ink = (
        colors.ready
        if status == "Ready"
        else colors.error
        if status.casefold() in {"fault", "failed", "error", "unhealthy"}
        else colors.waiting
        if status.casefold() in {"not prepared", "preparing", "waiting", "connected"}
        else colors.muted
    )
    painter = QPainter(indicator)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    lamp = QColor(ink)
    halo = QColor(lamp)
    halo.setAlpha(45)
    glyph = (
        "●"
        if ink == colors.ready
        else "▲"
        if ink == colors.error
        else "◐"
        if ink == colors.waiting
        else "○"
    )
    if indicator.property("crtGlow") is True:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QRectF(0, 4, 14, 14))
    painter.setPen(lamp)
    painter.drawText(QRectF(0, 2, 14, 18), Qt.AlignmentFlag.AlignCenter, glyph)
    width = max(0, indicator.width() - 18)
    painter.setPen(QColor(colors.label))
    painter.drawText(
        18,
        14,
        indicator.fontMetrics().elidedText(
            indicator.text().upper(), Qt.TextElideMode.ElideRight, width
        ),
    )
    font = painter.font()
    font.setPixelSize(10)
    painter.setFont(font)
    painter.setPen(lamp)
    painter.drawText(
        18,
        30,
        painter.fontMetrics().elidedText(
            f"[{status.upper()}]", Qt.TextElideMode.ElideRight, width
        ),
    )


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
        painter.setPen(QPen(QColor(retro_colors(self).accent), 2))
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        for point, dx, dy in (
            (rect.topLeft(), 1, 1),
            (rect.topRight(), -1, 1),
            (rect.bottomLeft(), 1, -1),
            (rect.bottomRight(), -1, -1),
        ):
            painter.drawLine(point, point + QPointF(7 * dx, 0))
            painter.drawLine(point, point + QPointF(0, 7 * dy))
