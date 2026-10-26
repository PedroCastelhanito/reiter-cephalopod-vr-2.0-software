"""Blank HighGUI windows for local layout review only."""

import sys
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QPoint, QTimer
from PyQt6.QtGui import QGuiApplication

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.gui.preview_follow import PreviewOwner, bind_preview_owner
from cephvr.gui.preview_placement import cocoa_preview_position
from cephvr.platform.windows.preview_caption import color_preview_caption
from cephvr.platform.windows.preview_creation import StagedPreviewWindow
from cephvr.platform.windows.window_coordinates import (
    blank_preview_caption,
    position_preview_frame,
    preview_window_handle,
)
from cephvr.shared.preview_geometry import PreviewGeometryGuard


class ReviewPreviews(QObject):
    def __init__(
        self,
        parent: QObject,
        placement: Callable[[str], rpc.PreviewWindowPlacement],
        closed: Callable[[str], None],
        report: Callable[[str], None],
        owner_handle: Callable[[], int] | None = None,
        owner_minimized: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.placement = placement
        self.closed = closed
        self.report = report
        self.owner_handle = owner_handle
        self.owner_minimized = owner_minimized
        self.owners: dict[str, PreviewOwner] = {}
        self.owner_handles: dict[str, int] = {}
        self.suspended: set[str] = set()
        self.windows: dict[str, tuple[str, Any]] = {}
        self.guards: dict[str, PreviewGeometryGuard] = {}
        self.placements: dict[str, bytes] = {}
        self.layout_errors: dict[str, str] = {}
        self.refs: dict[str, str | int] = {}
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll_windows)

    def visibility(self, key: str, name: str, visible: bool) -> bool:
        import cv2
        import numpy as np

        if not visible:
            entry = self.windows.pop(key, None)
            self._release_owner(key)
            if entry is not None:
                try:
                    cv2.destroyWindow(entry[0])
                    cv2.waitKey(1)
                except cv2.error as exc:
                    self.report(f"Preview close failed: {exc}")
                    try:
                        if cv2.getWindowProperty(entry[0], cv2.WND_PROP_VISIBLE) >= 1:
                            self.windows[key] = entry
                            return True
                    except cv2.error:
                        pass
            if not self.windows:
                self.timer.stop()
            return False
        if key in self.windows:
            return True
        title = f"LOCAL REVIEW - {name} - blank preview"
        try:
            placement = self.placement(key)
            side = placement.side
            frame = np.zeros((side, side, 3), dtype=np.uint8)
            with StagedPreviewWindow(title) as staged:
                cv2.namedWindow(title, cv2.WINDOW_NORMAL)
                cv2.imshow(title, frame)
                cv2.waitKey(1)
                self._place(cv2, title, placement, linked=False)
                self.windows[key] = (title, frame)
                if self.owner_handle is not None:
                    self.owner_handles[key] = self.owner_handle()
                    self.owners[key] = bind_preview_owner(
                        title, self.owner_handles[key]
                    )
                    guard = PreviewGeometryGuard()
                    guard.arranged(
                        self.owners[key].geometry(),
                        self.owners[key].placement_revision(),
                    )
                    self.guards[key] = guard
                self.placements[key] = placement.SerializeToString()
                self.refs[key] = self._blank_caption(cv2, title)
                minimized = (
                    self.owner_minimized()
                    if self.owner_minimized is not None
                    else False
                )
                staged.show(not minimized)
            self.timer.start()
            return True
        except Exception as exc:
            self.windows.pop(key, None)
            self._release_owner(key)
            try:
                cv2.destroyWindow(title)
            except cv2.error:
                pass
            self.report(f"Synthetic preview failed: {exc}")
            return False

    def snap(self, key: str) -> None:
        """Explicitly restore an existing viewer without reopening a closed one."""
        import cv2

        self.poll_windows()
        entry = self.windows.get(key)
        owner = self.owners.get(key)
        if entry is None or owner is None:
            return
        try:
            placement = self.placement(key)
            self._place(cv2, entry[0], placement, linked=True)
            guard = PreviewGeometryGuard()
            guard.arranged(owner.geometry(), owner.placement_revision())
            self.guards[key] = guard
            self.placements[key] = placement.SerializeToString()
        except Exception as exc:
            self.report(f"Preview snap failed: {exc}")

    def poll_windows(self) -> None:
        import cv2

        cv2.waitKey(1)
        for key, (title, _frame) in tuple(self.windows.items()):
            owner = self.owners.get(key)
            try:
                minimized = (
                    self.owner_minimized() if self.owner_minimized is not None else None
                )
                if owner is not None:
                    handle = self.owner_handle() if self.owner_handle is not None else 0
                    if handle and handle != self.owner_handles.get(key):
                        owner.retarget(handle)
                        self.owner_handles[key] = handle
                        self.guards[key].arranged(
                            owner.geometry(), owner.placement_revision()
                        )
                    if owner.sync(minimized):
                        self.suspended.add(key)
                        continue
                    if key in self.suspended:
                        self.suspended.discard(key)
                        self.guards[key].arranged(
                            owner.geometry(), owner.placement_revision()
                        )
                        self.placements.pop(key, None)
            except Exception as exc:
                self.report(f"Preview owner link failed: {exc}")
                if not self.visibility(key, "", False):
                    self.closed(key)
                continue
            try:
                visible = cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) >= 1
            except cv2.error:
                visible = False
            if not visible:
                del self.windows[key]
                self._release_owner(key)
                self.closed(key)
                continue
            if owner is not None:
                self._relayout(key, title, owner, cv2)
        if not self.windows:
            self.timer.stop()

    def _place(
        self,
        cv: Any,
        title: str,
        placement: rpc.PreviewWindowPlacement,
        *,
        linked: bool,
        ref: str | int | None = None,
    ) -> None:
        cv.resizeWindow(title, placement.side, placement.side)
        cv.waitKey(1)
        if sys.platform == "win32":
            color_preview_caption(
                preview_window_handle(title) if ref is None else int(ref), placement
            )
            position_preview_frame(
                title if ref is None else ref,
                placement.x,
                placement.y,
                topmost=not linked,
            )
        else:
            cv.moveWindow(title, placement.x, placement.y)
            if sys.platform == "darwin":
                cv.waitKey(1)
                primary = QGuiApplication.primaryScreen()
                screen = QGuiApplication.screenAt(QPoint(placement.x, placement.y))
                if primary is not None and screen is not None:
                    x, y = cocoa_preview_position(
                        placement.x,
                        placement.y,
                        primary.geometry().height(),
                        screen.availableGeometry().height(),
                    )
                    cv.moveWindow(title, x, y)
        cv.waitKey(1)

    def _relayout(self, key: str, title: str, owner: PreviewOwner, cv: Any) -> None:
        try:
            guard = self.guards[key]
            if not guard.observe(owner.geometry(), owner.placement_revision()):
                return
            placement = self.placement(key)
            serialized = placement.SerializeToString()
            if serialized != self.placements.get(key):
                self._place(cv, title, placement, linked=True, ref=self.refs.get(key))
                guard.arranged(owner.geometry(), owner.placement_revision())
                self.placements[key] = serialized
            self.layout_errors.pop(key, None)
        except Exception as exc:
            message = str(exc)
            if self.layout_errors.get(key) != message:
                self.report(f"Preview layout retained: {message}")
                self.layout_errors[key] = message

    def _blank_caption(self, cv: Any, title: str) -> str | int:
        """Names live on the preview card; Win32 then addresses the window by handle."""
        if sys.platform == "win32":
            handle = preview_window_handle(title)
            blank_preview_caption(handle)
            return handle
        cv.setWindowTitle(title, "")
        return title

    def _release_owner(self, key: str) -> None:
        self.suspended.discard(key)
        self.owner_handles.pop(key, None)
        self.refs.pop(key, None)
        self.guards.pop(key, None)
        self.placements.pop(key, None)
        self.layout_errors.pop(key, None)
        owner = self.owners.pop(key, None)
        if owner is not None:
            try:
                owner.close()
            except Exception as exc:
                self.report(f"Preview owner cleanup failed: {exc}")

    def close(self) -> None:
        for key in tuple(self.windows):
            self.visibility(key, "", False)
