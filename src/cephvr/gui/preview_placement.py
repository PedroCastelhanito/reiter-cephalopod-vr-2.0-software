"""Display-only placement hints for acquisition-owned camera windows."""

from math import ceil

from PyQt6.QtCore import QPoint, QRect, pyqtSignal
from PyQt6.QtGui import (
    QGuiApplication,
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
from cephvr.gui.components import StatusColumn
from cephvr.gui.preview_frame import PreviewFrame
from cephvr.gui.previews import PreviewDialog
from cephvr.gui.view import PreviewView
from cephvr.platform.windows.preview_owner import gui_window_identity
from cephvr.platform.windows.window_coordinates import (
    client_point_to_screen,
    operator_window_geometry,
    preview_frame_extra,
)


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
        self.arranged_sources: tuple[PreviewView, ...] = ()
        self.reserve_active = False
        self.columns = 0
        self.set_sources(())

    @property
    def target(self) -> QWidget:
        return next(iter(self.frames.values())).target

    @property
    def caption(self) -> QLabel:
        return next(iter(self.frames.values())).caption

    def set_sources(
        self, sources: tuple[PreviewView, ...], *, reserve_active: bool = False
    ) -> None:
        self.sources = sources
        self.reserve_active = reserve_active
        self.arrange(self.eligible_sources())

    def eligible_sources(self) -> tuple[PreviewView, ...]:
        return tuple(
            item
            for item in self.sources
            if item.visible or item.pending or (self.reserve_active and item.active)
        )

    def arrange(self, sources: tuple[PreviewView, ...]) -> None:
        self.arranged_sources = sources
        requested = {item.key: item.name for item in sources}
        if not requested:
            requested = {"": "Preview"}
        columns = self.grid_columns(len(requested))
        reflow = tuple(requested) != tuple(self.frames) or columns != self.columns
        self.columns = columns
        previous = self.frames
        for key, old_frame in previous.items():
            if reflow:
                self.grid.removeWidget(old_frame)
            if key not in requested:
                old_frame.setParent(None)
                old_frame.deleteLater()
        self.frames = {}
        for col in range(3):
            self.grid.setColumnStretch(col, 1 if col < columns else 0)
        for row in range(self.grid.rowCount()):
            self.grid.setRowStretch(row, 0)
        by_key = {source.key: source for source in sources}
        for index, (key, name) in enumerate(requested.items()):
            frame = previous.get(key)
            if frame is None:
                frame = PreviewFrame()
                frame.target.setProperty("preview_source", key)
                frame.snap_button.setEnabled(bool(key))
                frame.snap_button.clicked.connect(
                    lambda _checked=False, source=key: self.snap_requested.emit(source)
                )
            frame.empty = not key
            source = by_key.get(key)
            waiting = bool(
                self.reserve_active and source is not None and not source.visible
            )
            frame.status.setVisible(waiting)
            frame.status.setText(
                "Opening preview…"
                if source and source.pending
                else source.reason
                if source and source.reason
                else "Ready · select Show"
            )
            frame.snap_button.setVisible(not waiting)
            if key:
                frame.caption.setText(f"[ {name.upper()} ]")
            self.frames[key] = frame
            if reflow:
                self.grid.addWidget(
                    frame,
                    index // columns,
                    index % columns,
                    1,
                    2 if columns == 1 and not self.reserve_active else 1,
                )
            self.grid.setRowStretch(index // columns, 1)
        self.updateGeometry()

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        if self.reserve_active and self.grid_columns(len(self.frames)) != self.columns:
            self.arrange(self.arranged_sources)

    def grid_columns(self, count: int) -> int:
        if not self.reserve_active:
            return min(2, max(1, count))
        maximum = min(3, max(1, count), max(1, (self.width() + 8) // 208))
        return max(
            range(1, maximum + 1),
            key=lambda columns: (
                min(
                    self.width() / columns - 24,
                    self.height() / ceil(max(1, count) / columns) - 54,
                ),
                -columns,
            ),
        )

    def attach_controls(self, workspace: PreviewDialog, *, external: bool) -> None:
        workspace.attach_controls(
            {key: frame.header for key, frame in self.frames.items()}
            if external
            else {}
        )
        for key, frame in self.frames.items():
            frame.caption.setVisible(
                not external or key not in workspace.source_widgets
            )
            if (
                external
                and key in workspace.statuses
                and workspace.statuses[key].text()
            ):
                frame.status.hide()
            frame.fit_target()

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
    previous = area.eligible_sources() if area is not None else ()
    prospective = area is not None and any(
        item.key == key and not item.visible for item in area.sources
    )
    if prospective:
        assert area is not None
        area.arrange(
            tuple(item for item in area.sources if item in previous or item.key == key)
        )
        if isinstance(host_window, PreviewDialog):
            area.attach_controls(host_window, external=True)
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
            if isinstance(host_window, PreviewDialog):
                area.attach_controls(host_window, external=True)
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
