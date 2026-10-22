"""Small themed components with explicit widget ownership."""

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPaintEvent,
    QPen,
    QRegion,
    QResizeEvent,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.consoles import Console as Console
from cephvr.gui.consoles import FittedConsole as FittedConsole
from cephvr.gui.consoles import LogConsole as LogConsole
from cephvr.gui.formatting import HudRows, hud_text
from cephvr.gui.retro_instruments import (
    corner_brackets,
    double_frame,
    paint_status_lamp,
)
from cephvr.gui.table_header import TableHeader
from cephvr.gui.theme import SIZES, colors_for, minimal_frames, retro_console


def label(text: str, role: str = "hint", *, wrap: bool = False) -> QLabel:
    result = QLabel(text)
    result.setProperty("role", role)
    result.setWordWrap(wrap)
    return result


class Button(QPushButton):
    """Push button whose Retro console label is painted; text() stays unchanged."""

    def retro_label(self) -> str | None:
        role = self.property("role")
        if (
            not self.text()
            or role == "icon"
            or self.text() in ("+", "×", "−", "…")
            or not retro_console(self)
        ):
            return None
        if role == "navigation":
            if minimal_frames(self):
                return f"< {self.text()} >" if self.isChecked() else self.text()
            return ("> " if self.isChecked() else "  ") + self.text()
        text = self.text().upper()
        return f"[ {text} ]"

    def sizeHint(self) -> QSize:
        size = super().sizeHint()
        if self.retro_label() is not None and self.property("role") != "navigation":
            size.setWidth(size.width() + self.fontMetrics().horizontalAdvance("[  ]"))
        return size

    def paintEvent(self, event: QPaintEvent | None) -> None:
        label_text = self.retro_label()
        if label_text is None:
            super().paintEvent(event)
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = label_text
        if (
            self.property("role") == "navigation"
            and minimal_frames(self)
            and self.isChecked()
        ):
            # Paint the leading bracket before the icon, not inside Qt's text label.
            icon = QIcon(option.icon)
            option.text = ""
            option.icon = QIcon()
            painter = QStylePainter(self)
            painter.drawControl(QStyle.ControlElement.CE_PushButton, option)
            painter.setPen(QColor(colors_for(self).coral))
            x = 12
            prefix = self.fontMetrics().horizontalAdvance("< ")
            painter.drawText(
                QRectF(x, 0, prefix, self.height()), Qt.AlignmentFlag.AlignVCenter, "< "
            )
            x += prefix
            icon.paint(
                painter,
                x,
                (self.height() - self.iconSize().height()) // 2,
                self.iconSize().width(),
                self.iconSize().height(),
            )
            x += self.iconSize().width() + 6
            painter.drawText(
                QRectF(x, 0, self.width() - x - 8, self.height()),
                Qt.AlignmentFlag.AlignVCenter,
                f"{self.text()} >",
            )
            painter.end()
        else:
            QStylePainter(self).drawControl(QStyle.ControlElement.CE_PushButton, option)
        if self.property("role") == "navigation" and minimal_frames(self):
            # Bright brackets mark the current page; dim ones preview a hovered page.
            colors = colors_for(self)
            ink = colors.accent if self.isChecked() else colors.border
            if self.isChecked() or self.underMouse():
                corner_brackets(
                    QPainter(self),
                    QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                    QColor(ink),
                    10,
                )


def button(text: str, role: str = "secondary", *, hint: str = "") -> QPushButton:
    result = Button(text)
    result.setProperty("role", role)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    result.setToolTip(hint)
    return result


def toggle_button(text: str, role: str = "secondary", *, hint: str = "") -> QPushButton:
    """Checkable button that shows its on state with a filled background."""
    result = button(text, role, hint=hint)
    result.setCheckable(True)
    result.setProperty("toggle", "on")
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

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = colors_for(self)
        painter.setPen(
            QPen(QColor(colors.muted if self.isEnabled() else colors.disabled), 1.5)
        )
        x, y = self.width() - 14, self.height() / 2
        painter.drawLine(QPointF(x - 4, y - 2), QPointF(x, y + 2))
        painter.drawLine(QPointF(x, y + 2), QPointF(x + 4, y - 2))


def combo(options: tuple[str, ...]) -> QComboBox:
    result = SelectionBox()
    result.setProperty("chevron", True)
    result.addItems(options)
    result.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
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
    caption = label(title, "label", wrap=True)
    caption.setSizePolicy(
        QSizePolicy.Policy.Ignored, caption.sizePolicy().verticalPolicy()
    )
    caption.setBuddy(editor)
    caption.setToolTip(hint)
    editor.setToolTip(hint)
    if isinstance(editor, QLineEdit):
        editor.setSizePolicy(
            QSizePolicy.Policy.Ignored, editor.sizePolicy().verticalPolicy()
        )
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

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame = QRectF(self.rect()).adjusted(0.5, 0, -0.5, -0.5)
        frame.setTop(self.caption.geometry().center().y() + 0.5)
        colors = colors_for(self)
        radius = 0 if retro_console(self) else SIZES.card_radius
        phosphor = minimal_frames(self) and retro_console(self)
        if phosphor and self.property("nestedCard") is True:
            return  # nested cards read as subsections: no fill, outline or brackets
        # Amber phosphor recesses cards to the log surface; open frames drop the outline.
        painter.setBrush(QColor(colors.console if phosphor else colors.card))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(frame, radius, radius)
        # Interrupt only the outline; keep the surface continuous beneath the title.
        gaps = QRegion(self.caption.geometry())
        if phosphor:
            # Header actions (e.g. Preview) interrupt the top line like the title.
            for index in range(self.header.count()):
                item = self.header.itemAt(index)
                widget = item.widget() if item is not None else None
                if widget is not None and widget.isVisible():
                    gaps = gaps.united(QRegion(widget.geometry().adjusted(-4, 0, 4, 0)))
        painter.setClipRegion(QRegion(self.rect()).subtracted(gaps))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if not (phosphor and self.property("openFrame") is True):
            painter.setPen(QPen(QColor(colors.border), 1))
            painter.drawRoundedRect(frame, radius, radius)
        if retro_console(self):
            double_frame(painter, frame, self)


class StatusIndicator(QRadioButton):
    """Independent readiness lamp; user input cannot change backend evidence."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.setProperty("role", "status-indicator")
        self.setAutoExclusive(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.set_status("Unavailable")

    def paintEvent(self, event: QPaintEvent | None) -> None:
        if retro_console(self):
            paint_status_lamp(self, self.status)
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        style = self.style()
        assert style is not None
        inset = style.pixelMetric(QStyle.PixelMetric.PM_ExclusiveIndicatorWidth)
        inset += style.pixelMetric(QStyle.PixelMetric.PM_RadioButtonLabelSpacing)
        option.text = self.fontMetrics().elidedText(
            option.text, Qt.TextElideMode.ElideRight, max(0, self.width() - inset)
        )
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_RadioButton, option)

    def set_status(self, status: str) -> None:
        self.status = status
        self.setChecked(status == "Ready")
        description = f"{self.text()} · {status}"
        self.setToolTip(description)
        self.setAccessibleName(description)
        self.update()

    def nextCheckState(self) -> None:
        pass


class StatusColumn(QWidget):
    """Shared fitted HUD above a log that consumes the remaining column height."""

    def __init__(self) -> None:
        super().__init__()
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(SIZES.card_gap)
        self.rows: HudRows = ()
        self.hud_card = Card("HUD")
        self.hud_card.setProperty("openFrame", True)
        self.hud = FittedConsole()
        self.hud.setProperty("terminal", "telemetry")
        self.hud_card.body.addWidget(self.hud)
        self.log_card = Card("LOG console", grow=True)
        self.log_card.setProperty("openFrame", True)
        self.console = LogConsole()
        self.log_minimum_height = self.console.minimumHeight()
        self.log_card.body.addWidget(self.console, 1)
        body.addWidget(self.hud_card)
        body.addWidget(self.log_card, 1)

    def set_rows(self, rows: HudRows) -> None:
        self.rows = rows
        self.render_hud()

    def update_row(self, key: str, value: str) -> None:
        rows = tuple(row for row in self.rows if row is None or row[0] != key)
        self.set_rows((*rows, (key, value)))

    def render_hud(self) -> None:
        self.hud.setPlainText(hud_text(self.rows, retro=retro_console(self)))


class ActionHeader(TableHeader):
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

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.place_action()
