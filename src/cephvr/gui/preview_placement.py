"""Display-only placement hints for acquisition-owned camera windows."""

from math import ceil

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QGuiApplication,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.gui.components import StatusColumn, button, label
from cephvr.gui.previews import PreviewDialog
from cephvr.gui.retro_instruments import blink
from cephvr.gui.theme import colors_for, retro_console
from cephvr.gui.view import PreviewView
from cephvr.platform.windows.preview_owner import gui_window_identity
from cephvr.platform.windows.window_coordinates import (
    client_point_to_screen,
    operator_window_geometry,
    preview_frame_extra,
)


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
        self.target = QWidget(self)
        self.target.setObjectName("ExternalPreviewSlot")
        self.target.setAccessibleName("Preview window placement")
        self.snap_button = button("Snap")
        self.snap_button.setParent(self.target)
        self.snap_button.setToolTip("Restore this preview's grid position and size.")
        self.placeholder = NoSignal(self.target, self.snap_button)
        self.placeholder.hide()

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

    def fit_target(self) -> None:
        scale = self.devicePixelRatioF()
        extra_width, extra_height = preview_frame_extra(scale)
        width_extra, height_extra = (
            ceil(extra_width / scale),
            ceil(extra_height / scale),
        )
        heading = self.caption.sizeHint().height() + 8
        self.setMinimumHeight(heading + 8 + 128 + height_extra)
        self.caption.setGeometry(0, 0, self.width(), heading - 8)
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
        self.placeholder.setGeometry(self.target.rect())
        self.snap_button.adjustSize()
        self.snap_button.move(
            (self.target.width() - self.snap_button.width()) // 2,
            (self.target.height() - self.snap_button.height()) // 2,
        )
        self.update()


class PreviewSlot(QWidget):
    """Arrange open source-specific footprints for simultaneous native viewers."""

    snap_requested = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        self.frames: dict[str, PreviewFrame] = {}
        self.sources: tuple[PreviewView, ...] = ()
        self.set_sources(())

    @property
    def target(self) -> QWidget:
        return next(iter(self.frames.values())).target

    @property
    def caption(self) -> QLabel:
        return next(iter(self.frames.values())).caption

    def set_sources(self, sources: tuple[PreviewView, ...]) -> None:
        self.sources = sources
        self.arrange(tuple(item for item in sources if item.visible))

    def arrange(self, sources: tuple[PreviewView, ...]) -> None:
        requested = {item.key: item.name for item in sources}
        if not requested:
            requested = {"": "Preview"}
        if tuple(requested) == tuple(self.frames):
            return
        for frame in self.frames.values():
            self.grid.removeWidget(frame)
            frame.setParent(None)
            frame.deleteLater()
        self.frames = {}
        columns = min(2, len(requested))
        for index, (key, name) in enumerate(requested.items()):
            frame = PreviewFrame()
            frame.target.setProperty("preview_source", key)
            frame.snap_button.setEnabled(bool(key))
            frame.snap_button.clicked.connect(
                lambda _checked=False, source=key: self.snap_requested.emit(source)
            )
            frame.empty = not key
            if key:
                frame.caption.setText(f"[ {name.upper()} ]")
            self.frames[key] = frame
            self.grid.addWidget(
                frame, index // columns, index % columns, 1, 2 if columns == 1 else 1
            )
        self.updateGeometry()

    def target_for(self, key: str) -> QWidget:
        if not key:
            return self.target
        frame = self.frames.get(key)
        if frame is None:
            raise ValueError("Preview source is not available on this page")
        return frame.target


def square_preview_placement(
    anchor: QRect, area: QRect, scale: float = 1.0
) -> rpc.PreviewWindowPlacement:
    # Reserve non-client frame space before fitting the square image area.
    reserve = round(64 * scale)
    side = max(
        128,
        min(round(640 * scale), 2048, area.width() - reserve, area.height() - reserve),
    )
    frame_width = round(16 * scale)
    vertical_space = area.bottom() + 1 - anchor.top() - reserve
    if vertical_space >= 128:
        side = min(side, vertical_space)
    right = anchor.right() + 1
    right_space = area.right() + 1 - right - frame_width
    left_space = anchor.left() - area.left() - frame_width
    if right_space >= 128:
        side = min(side, right_space)
        x = right
    elif left_space >= 128:
        side = min(side, left_space)
        x = anchor.left() - side - frame_width
    else:
        x = right
    width = side + frame_width
    x = max(area.left(), min(x, area.right() + 1 - width))
    y = max(area.top(), min(anchor.top(), area.bottom() + 1 - side - reserve))
    return rpc.PreviewWindowPlacement(x=x, y=y, side=side)


def _activate_ancestor_layouts(widget: QWidget) -> None:
    ancestors = []
    current: QWidget | None = widget
    while current is not None:
        ancestors.append(current)
        current = current.parentWidget()
    # Propagate changed size hints up, then distribute the resulting geometry down.
    for item in (*ancestors, *reversed(ancestors)):
        layout = item.layout()
        if layout is not None:
            layout.activate()
    for frame in widget.findChildren(PreviewFrame):
        frame.fit_target()


def preview_window_placement(
    main: QWidget, key: str = ""
) -> rpc.PreviewWindowPlacement:
    """Measure the open-frame layout without retaining speculative visibility."""
    area = main.findChild(PreviewSlot)
    host_window = area.window() if area is not None else None
    if isinstance(host_window, PreviewDialog):
        host_window.fit_contents()
    previous = (
        tuple(item for item in area.sources if item.visible) if area is not None else ()
    )
    prospective = area is not None and any(
        item.key == key and not item.visible for item in area.sources
    )
    if prospective:
        assert area is not None
        area.arrange(
            tuple(item for item in area.sources if item.visible or item.key == key)
        )
    frame = area.frames.get(key) if area is not None else None
    slot = (
        frame.target
        if frame is not None
        else area.target
        if area is not None and not key
        else None
    )
    card = area if slot is not None else None
    owner = card.parentWidget() if card is not None else None
    empty_hint = (
        owner.findChild(QLabel, "PreviewWorkspaceEmpty") if owner is not None else None
    )
    empty_hidden = empty_hint.isHidden() if empty_hint is not None else True
    if prospective and empty_hint is not None:
        empty_hint.hide()
    measuring = bool(
        card is not None and card.isHidden() and owner is not None and owner.isVisible()
    )
    log_compact = (
        owner.console.preview_compact if isinstance(owner, StatusColumn) else False
    )
    log_scroll = (
        owner.console.verticalScrollBar() if isinstance(owner, StatusColumn) else None
    )
    log_position = log_scroll.value() if log_scroll is not None else 0
    if measuring:
        assert card is not None and owner is not None
        if isinstance(owner, StatusColumn):
            owner.console.set_preview_compact(True, follow=False)
            layout = owner.layout()
            assert isinstance(layout, QVBoxLayout)
            layout.setStretchFactor(owner.log_card, 0)
        card.show()
    if card is not None:
        _activate_ancestor_layouts(card)
    try:
        host = (slot.window() or main) if slot is not None else main
        placement = _preview_window_placement(host, slot)
        if QGuiApplication.platformName() == "windows":
            hwnd, pid, creation = gui_window_identity(int(host.winId()))
            placement.gui_window_handle = hwnd
            placement.gui_process_id = pid
            placement.gui_process_creation_time_100ns = creation
        return placement
    finally:
        if empty_hint is not None:
            empty_hint.setVisible(not empty_hidden)
        if prospective:
            assert area is not None
            area.arrange(previous)
        if measuring:
            assert card is not None and owner is not None
            card.hide()
            if isinstance(owner, StatusColumn):
                owner.console.set_preview_compact(log_compact, follow=False)
                layout = owner.layout()
                assert isinstance(layout, QVBoxLayout)
                layout.setStretchFactor(owner.log_card, 0 if log_compact else 1)
            _activate_ancestor_layouts(card)
            if log_scroll is not None:
                log_scroll.setValue(log_position)
        elif prospective and area is not None:
            _activate_ancestor_layouts(area)


def _preview_window_placement(
    main: QWidget, slot: QWidget | None
) -> rpc.PreviewWindowPlacement:
    screen = main.screen()
    area = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)
    slot_rect = (
        QRect(slot.mapToGlobal(QPoint()), slot.size()) if slot is not None else None
    )
    if QGuiApplication.platformName() == "windows":
        anchor_bounds, area_bounds, scale = operator_window_geometry(int(main.winId()))
        if slot_rect is not None:
            assert slot is not None
            offset = slot.mapTo(main, QPoint())
            x, y = client_point_to_screen(
                int(main.winId()), round(offset.x() * scale), round(offset.y() * scale)
            )
            slot_rect = QRect(
                x,
                y,
                round(slot_rect.width() * scale),
                round(slot_rect.height() * scale),
            )
            return slot_preview_placement(slot_rect, QRect(*area_bounds), scale)
        return square_preview_placement(
            QRect(*anchor_bounds), QRect(*area_bounds), scale
        )
    if slot_rect is not None:
        return slot_preview_placement(slot_rect, area)
    return square_preview_placement(main.frameGeometry(), area)


def slot_preview_placement(
    slot: QRect, area: QRect, scale: float = 1.0
) -> rpc.PreviewWindowPlacement:
    """Fit the detached square and its native frame within the reserved area."""
    bounds = slot.intersected(area)
    extra_width, extra_height = preview_frame_extra(scale)
    side = min(
        2048,
        bounds.width() - extra_width,
        bounds.height() - extra_height,
    )
    frame_width = side + extra_width
    if side < 128 or frame_width > bounds.width():
        raise ValueError(
            "Preview frame has insufficient visible space for a preview window"
        )
    return rpc.PreviewWindowPlacement(
        x=bounds.x() + (bounds.width() - frame_width) // 2,
        y=bounds.y() + (bounds.height() - side - extra_height) // 2,
        side=side,
    )


def cocoa_preview_position(
    x: int, y: int, primary_height: int, current_work_height: int
) -> tuple[int, int]:
    """Convert Qt top-origin coordinates to HighGUI Cocoa's work-height origin."""
    return x, y - (primary_height - current_work_height)
