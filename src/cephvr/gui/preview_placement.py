"""Initial display-only placement hints for acquisition-owned camera windows."""

from math import ceil

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QGuiApplication, QResizeEvent
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.gui.components import Card, label
from cephvr.platform.windows.window_coordinates import (
    client_point_to_screen,
    operator_window_geometry,
    preview_frame_extra,
)


class PreviewSlot(Card):
    """Reserve the initial detached frame's footprint below the card heading."""

    def __init__(self) -> None:
        super().__init__("Preview")
        self.setMinimumWidth(200)
        self.setMaximumWidth(658)
        self.body.setContentsMargins(8, 0, 8, 8)
        self.body.setSpacing(4)
        self.header.setContentsMargins(0, 0, 0, 0)
        self.target = QWidget()
        self.target.setObjectName("ExternalPreviewSlot")
        layout = QVBoxLayout(self.target)
        hint = label("Preview windows open here", "muted")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        self.body.addWidget(self.target)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        scale = self.devicePixelRatioF()
        extra_width, extra_height = preview_frame_extra(scale)
        side = max(
            128,
            min(round(640 * scale), round((self.width() - 16) * scale) - extra_width),
        )
        height = ceil((side + extra_height) / scale)
        self.target.setFixedHeight(height)
        self.setFixedHeight(self.header.sizeHint().height() + 4 + height + 8)


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


def preview_window_placement(main: QWidget) -> rpc.PreviewWindowPlacement:
    slot = main.findChild(QWidget, "ExternalPreviewSlot")
    screen = main.screen()
    area = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)
    slot_rect = (
        QRect(slot.mapToGlobal(QPoint()), slot.size())
        if slot is not None and slot.isVisible()
        else None
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
    side = max(
        128,
        min(
            round(640 * scale),
            2048,
            bounds.width() - extra_width,
            bounds.height() - extra_height,
        ),
    )
    return rpc.PreviewWindowPlacement(x=bounds.x(), y=bounds.y(), side=side)
