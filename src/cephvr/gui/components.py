"""Small themed components with explicit widget ownership."""

from math import ceil

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPaintEvent,
    QPen,
    QRegion,
    QResizeEvent,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.theme import COLORS, SIZES


def label(text: str, role: str = "hint", *, wrap: bool = False) -> QLabel:
    result = QLabel(text)
    result.setProperty("role", role)
    result.setWordWrap(wrap)
    return result


class InlineMessage(QLabel):
    """Show validation text without reserving space for an empty message."""

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("role", "hint")
        self.setWordWrap(True)
        self.hide()

    def setText(self, text: str | None) -> None:  # noqa: N802
        super().setText(text)
        self.setVisible(bool(text))

    def clear(self) -> None:
        self.setText("")


def button(text: str, role: str = "secondary", *, hint: str = "") -> QPushButton:
    result = QPushButton(text)
    result.setProperty("role", role)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    result.setToolTip(hint)
    return result


def equal_row_height(*controls: QWidget) -> None:
    """Match row control heights; compact indicators are explicit exceptions."""
    for control in controls:
        control.ensurePolished()
    height = max(control.sizeHint().height() for control in controls)
    for control in controls:
        control.setFixedHeight(height)


class SelectionBox(QComboBox):
    """Draw a consistent dropdown affordance across native widget styles."""

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QPen(QColor(COLORS.muted if self.isEnabled() else COLORS.disabled), 1.5)
        )
        x, y = self.width() - 14, self.height() / 2
        painter.drawLine(QPointF(x - 4, y - 2), QPointF(x, y + 2))
        painter.drawLine(QPointF(x, y + 2), QPointF(x + 4, y - 2))


def combo(options: tuple[str, ...]) -> QComboBox:
    result = SelectionBox()
    result.setProperty("chevron", True)
    result.addItems(options)
    result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return result


def decimal_field(value: float, suffix: str = "") -> QDoubleSpinBox:
    result = QDoubleSpinBox()
    result.setRange(0.1, 86400)
    result.setDecimals(1)
    result.setValue(value)
    result.setSuffix(suffix)
    result.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    return result


def field(title: str, editor: QWidget, *, hint: str = "") -> QWidget:
    result = QWidget()
    result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    layout = QVBoxLayout(result)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    caption = label(title, "label")
    caption.setBuddy(editor)
    caption.setToolTip(hint)
    editor.setToolTip(hint)
    layout.addWidget(caption)
    layout.addWidget(editor)
    return result


class Card(QFrame):
    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        grow: bool = False,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding if grow else QSizePolicy.Policy.Maximum,
        )
        self.body = QVBoxLayout(self)
        padding = SIZES.compact_card_padding if compact else SIZES.card_padding
        self.body.setContentsMargins(padding, 0, padding, padding)
        self.body.setSpacing(10)
        self.header = QHBoxLayout()
        self.header.setContentsMargins(
            0, 0, 0, SIZES.compact_card_top if compact else SIZES.card_top
        )
        self.caption = label(title, "title")
        self.caption.setContentsMargins(6, 0, 6, 0)
        self.caption.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.header.addWidget(self.caption)
        self.header.addStretch()
        self.body.addLayout(self.header)

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame = QRectF(self.rect()).adjusted(0.5, 0, -0.5, -0.5)
        frame.setTop(self.caption.geometry().center().y() + 0.5)
        painter.setBrush(QColor(COLORS.card))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(frame, SIZES.card_radius, SIZES.card_radius)
        # Interrupt only the outline; keep the surface continuous beneath the title.
        painter.setClipRegion(
            QRegion(self.rect()).subtracted(QRegion(self.caption.geometry()))
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(COLORS.border), 1))
        painter.drawRoundedRect(frame, SIZES.card_radius, SIZES.card_radius)


class StatusIndicator(QRadioButton):
    """Independent readiness lamp; user input cannot change backend evidence."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.setProperty("role", "status-indicator")
        self.setAutoExclusive(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.set_status("Unavailable")

    def set_status(self, status: str) -> None:
        self.setChecked(status == "Ready")
        description = f"{self.text()} · {status}"
        self.setToolTip(description)
        self.setAccessibleName(description)

    def nextCheckState(self) -> None:  # noqa: N802
        pass


class Console(QPlainTextEdit):
    def __init__(self, *, lines: int = 6, grow: bool = True) -> None:
        super().__init__()
        self.setProperty("role", "console")
        self.setReadOnly(True)
        self.setMaximumBlockCount(256)
        height = lines * (SIZES.console_font + 5) + 32
        if grow:
            self.setMinimumHeight(height)
        else:
            self.setFixedHeight(height)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding if grow else QSizePolicy.Policy.Fixed,
        )

    def sizeHint(self) -> QSize:  # noqa: N802
        size = super().sizeHint()
        size.setHeight(self.minimumHeight())
        return size


class FittedConsole(Console):
    """Fit the rendered text, including wrapped lines, without consuming spare height."""

    def __init__(self) -> None:
        super().__init__(lines=1, grow=False)
        self.textChanged.connect(self.fit_height)

    def fit_height(self) -> None:
        document = self.document()
        assert document is not None
        layout = document.documentLayout()
        assert layout is not None
        block = document.begin()
        height = 2 * (self.frameWidth() + document.documentMargin())
        while block.isValid():
            height += layout.blockBoundingRect(block).height()
            block = block.next()
        target = ceil(height)
        if self.height() != target:
            self.setFixedHeight(target)

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fit_height()


class LogConsole(Console):
    """Follow new messages only while the reader is already at the bottom."""

    def __init__(self, *, lines: int = 7) -> None:
        super().__init__(lines=lines)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WordWrap)

    def appendPlainText(self, text: str | None) -> None:  # noqa: N802
        if not text:
            return
        vertical = self.verticalScrollBar()
        horizontal = self.horizontalScrollBar()
        assert vertical is not None and horizontal is not None
        following = vertical.value() >= vertical.maximum()
        x = horizontal.value()
        anchor = self.firstVisibleBlock()
        document = self.document()
        assert document is not None
        preceding_lines = 0
        block = document.begin()
        while block.isValid() and block != anchor:
            preceding_lines += block.lineCount()
            block = block.next()
        line_offset = max(0, vertical.value() - preceding_lines)
        super().appendPlainText(text)
        position = 0
        if not following and anchor.isValid():
            block = document.begin()
            while block.isValid() and block != anchor:
                position += block.lineCount()
                block = block.next()
            position += line_offset
        vertical.setValue(vertical.maximum() if following else position)
        horizontal.setValue(x)


class StatusColumn(QWidget):
    """Shared fitted HUD above a log that consumes the remaining column height."""

    def __init__(self, title: str = "Runtime HUD") -> None:
        super().__init__()
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(SIZES.card_gap)
        self.hud_card = Card(title)
        self.hud = FittedConsole()
        self.hud_card.body.addWidget(self.hud)
        self.log_card = Card("Activity log", grow=True)
        self.console = LogConsole()
        self.log_card.body.addWidget(self.console, 1)
        body.addWidget(self.hud_card)
        body.addWidget(self.log_card, 1)


class ActionHeader(QHeaderView):
    """Reserve the final table section for a compact, accessible header action."""

    def __init__(self, action: QPushButton) -> None:
        super().__init__(Qt.Orientation.Horizontal)
        self.action = action
        action.setParent(self.viewport())
        self.sectionResized.connect(self.place_action)
        self.geometriesChanged.connect(self.place_action)

    def place_action(self) -> None:
        if self.count():
            section = self.count() - 1
            self.action.move(
                self.sectionViewportPosition(section)
                + (self.sectionSize(section) - self.action.width()) // 2,
                (self.height() - self.action.height()) // 2,
            )

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.place_action()
