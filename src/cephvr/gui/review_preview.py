"""Blank HighGUI windows for local layout review only."""

import sys
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QPoint, QTimer
from PyQt6.QtGui import QGuiApplication

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.gui.preview_placement import cocoa_preview_position
from cephvr.platform.windows.window_coordinates import position_preview_frame


class ReviewPreviews(QObject):
    def __init__(
        self,
        parent: QObject,
        placement: Callable[[], rpc.PreviewWindowPlacement],
        closed: Callable[[str], None],
        report: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self.placement = placement
        self.closed = closed
        self.report = report
        self.windows: dict[str, tuple[str, Any]] = {}
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll_windows)

    def visibility(self, key: str, name: str, visible: bool) -> bool:
        import cv2
        import numpy as np

        if not visible:
            entry = self.windows.pop(key, None)
            if entry is not None:
                cv2.destroyWindow(entry[0])
                cv2.waitKey(1)
            if not self.windows:
                self.timer.stop()
            return False
        if key in self.windows:
            return True
        title = f"LOCAL REVIEW - {name} - blank preview"
        try:
            placement = self.placement()
            side = placement.side
            frame = np.zeros((side, side, 3), dtype=np.uint8)
            cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)
            cv2.imshow(title, frame)
            cv2.waitKey(1)
            if sys.platform == "win32":
                position_preview_frame(title, placement.x, placement.y)
            else:
                cv2.moveWindow(title, placement.x, placement.y)
                if sys.platform == "darwin":
                    # The first move chooses the target screen; Cocoa uses that
                    # screen's work-height origin for the final position.
                    cv2.waitKey(1)
                    primary = QGuiApplication.primaryScreen()
                    screen = QGuiApplication.screenAt(QPoint(placement.x, placement.y))
                    if primary is not None and screen is not None:
                        x, y = cocoa_preview_position(
                            placement.x,
                            placement.y,
                            primary.geometry().height(),
                            screen.availableGeometry().height(),
                        )
                        cv2.moveWindow(title, x, y)
            self.windows[key] = (title, frame)
            self.timer.start()
            return True
        except Exception as exc:
            try:
                cv2.destroyWindow(title)
            except cv2.error:
                pass
            self.report(f"Synthetic preview failed: {exc}")
            return False

    def poll_windows(self) -> None:
        import cv2

        cv2.waitKey(1)
        for key, (title, _frame) in tuple(self.windows.items()):
            try:
                visible = cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) >= 1
            except cv2.error:
                visible = False
            if not visible:
                del self.windows[key]
                self.closed(key)
                continue
        if not self.windows:
            self.timer.stop()

    def close(self) -> None:
        for key in tuple(self.windows):
            self.visibility(key, "", False)
