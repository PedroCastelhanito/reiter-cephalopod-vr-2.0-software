"""Shared responsive placement with stable editor ownership."""

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QFrame, QGridLayout, QScrollArea, QVBoxLayout, QWidget

from cephvr.gui.theme import SIZES


def column() -> tuple[QWidget, QVBoxLayout]:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SIZES.card_gap)
    return widget, layout


def fit_window_to_screen(window: QWidget) -> None:
    screen = window.screen()
    if screen is not None:
        area = screen.availableGeometry()
        inset = 2 * SIZES.page_margin
        window.resize(
            min(window.width(), area.width() - inset),
            min(window.height(), area.height() - inset),
        )


def tool_window_position(anchor: QRect, size: QSize, area: QRect) -> QPoint:
    """Prefer the right-hand gap; keep the tool on the anchor's available screen."""
    return QPoint(
        max(
            area.left(),
            min(
                anchor.right() + 1 + SIZES.tool_window_gap,
                area.right() + 1 - size.width(),
            ),
        ),
        max(area.top(), min(anchor.top(), area.bottom() + 1 - size.height())),
    )


def snap_tool_window(main: QWidget, tool: QWidget) -> None:
    """Position visible native frames, accounting for platform title-bar offsets."""
    screen = main.screen()
    if screen is None:
        return
    area = screen.availableGeometry()
    frame = tool.frameGeometry()
    extra = frame.size() - tool.size()
    tool.resize(
        min(tool.width(), max(1, area.width() - extra.width())),
        min(tool.height(), max(1, area.height() - extra.height())),
    )
    target = tool_window_position(
        main.frameGeometry(), tool.frameGeometry().size(), area
    )
    for _ in range(2):
        offset = target - tool.frameGeometry().topLeft()
        if offset.isNull():
            break
        tool.move(tool.pos() + offset)


class ResponsiveColumns(QWidget):
    """Place control and status columns side by side, or stack on narrow windows."""

    def __init__(self, left: QWidget, right: QWidget) -> None:
        super().__init__()
        self.columns = (left, right)
        self.config_scroll = QScrollArea()
        self.config_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.config_scroll.setWidgetResizable(True)
        self.config_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.config_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.config_scroll.setWidget(left)
        self.config_scroll.setMinimumSize(0, 0)
        self.scrollers = (self.config_scroll, right)
        self.mode = ""
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(SIZES.column_gap)
        self.arrange(SIZES.wide_breakpoint)

    def arrange(self, width: int) -> None:
        mode = "wide" if width >= SIZES.wide_breakpoint else "stacked"
        if mode == self.mode:
            return
        self.mode = mode
        for index, widget in enumerate(self.scrollers):
            self.grid.removeWidget(widget)
            widget.setMinimumWidth(0)
            widget.setMaximumWidth(16777215)
            self.grid.setColumnStretch(index, 0)
            self.grid.setColumnMinimumWidth(index, 0)
        left, right = self.scrollers
        self.grid.setRowStretch(0, 1)
        self.grid.setRowStretch(1, 0 if mode == "wide" else 1)
        if mode == "wide":
            left.setMinimumWidth(SIZES.controls_min_width)
            left.setMaximumWidth(SIZES.controls_max_width)
            right.setMinimumWidth(SIZES.status_min_width)
            for index, widget in enumerate(self.scrollers):
                self.grid.addWidget(widget, 0, index)
                self.grid.setColumnStretch(index, 1)
        else:
            for index, widget in enumerate(self.scrollers):
                self.grid.addWidget(widget, index, 0)
            self.grid.setColumnStretch(0, 1)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 0)

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.arrange(self.width())
