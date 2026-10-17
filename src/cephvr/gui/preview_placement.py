"""Initial display-only placement hints for acquisition-owned camera windows."""

import sys
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

_MINIMUM_FRAME_WIDTH = 200 if sys.platform == "darwin" else 0


class PreviewSlot(Card):
    """Reserve the initial detached frame's footprint below the card heading."""

    def __init__(self) -> None:
        super().__init__("Preview", grow=True)
        self.setMinimumWidth(max(200, _MINIMUM_FRAME_WIDTH + 16))
        self.setMinimumHeight(180)
        self.body.setContentsMargins(8, 0, 8, 8)
        self.body.setSpacing(4)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
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
        heading = self.header.sizeHint().height() + 12
        self.setMinimumHeight(max(180, heading + ceil((128 + extra_height) / scale)))
        width_side = min(
            round(640 * scale), round((self.width() - 16) * scale) - extra_width
        )
        self.setMaximumHeight(heading + ceil((width_side + extra_height) / scale))
        side = max(
            128,
            min(width_side, round((self.height() - heading) * scale) - extra_height),
        )
        height = ceil((side + extra_height) / scale)
        self.target.setFixedHeight(height)


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
    side = min(
        round(640 * scale),
        2048,
        bounds.width() - extra_width,
        bounds.height() - extra_height,
    )
    frame_width = max(side + extra_width, _MINIMUM_FRAME_WIDTH)
    if side < 128 or frame_width > bounds.width():
        raise ValueError(
            "Preview card has insufficient visible space for a preview window"
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
