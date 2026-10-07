"""Initial display-only placement hints for acquisition-owned camera windows."""

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.platform.windows.window_coordinates import operator_window_geometry


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
    if QGuiApplication.platformName() == "windows":
        anchor_bounds, area_bounds, scale = operator_window_geometry(int(main.winId()))
        return square_preview_placement(
            QRect(*anchor_bounds), QRect(*area_bounds), scale
        )
    screen = main.screen()
    area = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)
    return square_preview_placement(main.frameGeometry(), area)
