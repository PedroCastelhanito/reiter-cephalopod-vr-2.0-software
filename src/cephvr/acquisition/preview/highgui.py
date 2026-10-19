"""One native window and private latest-frame reader, owned by acquisition (A10)."""

from __future__ import annotations

import importlib
import sys
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any
from uuid import UUID

from cephvr.acquisition.buffers.ring import RingAllocationError, SharedRing
from cephvr.acquisition.camera.native_formats import pylon_pixel_format
from cephvr.acquisition.preview.viewport import SquareViewport
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.platform.windows.preview_owner import WindowsPreviewOwner
from cephvr.platform.windows.window_coordinates import (
    blank_preview_caption,
    physical_coordinates,
    position_preview_frame,
    preview_window_handle,
)
from cephvr.shared.pixels.preparer import PixelPreparer, PreparedImage
from cephvr.shared.pixels.types import PixelLayout
from cephvr.shared.preview_geometry import PreviewGeometryGuard


def display_array(image: PreparedImage, numpy: Any) -> Any:
    """Expose private full-range pixels with OpenCV's color channel order."""
    dtype = numpy.uint8 if image.container_bits == 8 else numpy.uint16
    shape = (
        (image.height, image.width)
        if image.channels == 1
        else (image.height, image.width, image.channels)
    )
    frame = numpy.frombuffer(image.data, dtype=dtype).reshape(shape)
    return frame if image.channel_order == "gray" else frame[:, :, ::-1].copy()


class HighGuiPreview:
    """Run all calls for this Win32 window on its owning thread.

    The bounded event wait pumps native messages even without frames. Arriving
    frames wake it immediately; neither a software rate limiter nor a backlog is used.
    """

    def __init__(
        self,
        attachment: acq.FrameBufferAttachment,
        output_bits: int,
        title: str,
        on_closed: Callable[[HighGuiPreview], None],
        placement: rpc.PreviewWindowPlacement | None = None,
    ) -> None:
        self.attachment = attachment
        self.output_bits = output_bits
        self.title = title
        self.on_closed = on_closed
        self.placement = (
            None
            if placement is None
            else rpc.PreviewWindowPlacement.FromString(placement.SerializeToString())
        )
        self.ready: Future[None] = Future()
        self.done: Future[bool] = Future()
        self.failure = ""
        self.visible = False
        self.native_handle = 0  # Win32 HWND; the title is blank once the window opens.
        self._layout_lock = threading.Lock()
        self._pending_placement: rpc.PreviewWindowPlacement | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=title, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def update_placement(self, placement: rpc.PreviewWindowPlacement) -> None:
        """Coalesce display hints; only the HighGUI owner thread touches windows."""
        with self._layout_lock:
            pending_snap = (
                self._pending_placement is not None
                and self._pending_placement.snap_to_grid
            )
            self._pending_placement = rpc.PreviewWindowPlacement.FromString(
                placement.SerializeToString()
            )
            self._pending_placement.snap_to_grid |= pending_snap

    def _take_placement(self) -> rpc.PreviewWindowPlacement | None:
        with self._layout_lock:
            placement, self._pending_placement = self._pending_placement, None
            return placement

    def _run(self) -> None:
        try:
            with physical_coordinates():
                self._run_window()
        except Exception as exc:
            self.failure = str(exc)
            if not self.ready.done():
                self.ready.set_exception(RuntimeError(self.failure))
            if not self.done.done():
                self.done.set_result(True)
                self.on_closed(self)

    def _run_window(self) -> None:
        ring: Any = None
        cv: Any = None
        window = False
        closed = True
        owner: WindowsPreviewOwner | None = None
        geometry = PreviewGeometryGuard()
        try:
            if self.output_bits != 8:
                raise ValueError("OpenCV preview currently supports 8 bits per channel")
            cv = importlib.import_module("cv2")
            numpy = importlib.import_module("numpy")
            descriptor = self.attachment.buffer
            image = descriptor.image
            layout = PixelLayout(
                image.width,
                image.height,
                pylon_pixel_format(image.pixel_format),
                image.row_stride_bytes,
                image.image_payload_bytes,
            )
            if descriptor.WhichOneof("scope") != "preview":
                raise ValueError("OpenCV viewer requires an exact manual preview run")
            run_id = UUID(descriptor.preview.acquisition_run_id)
            ring = SharedRing.attach(
                self.attachment, layout, self.attachment.sync.target
            )
            preparer = PixelPreparer(layout)
            pixels = bytearray(layout.image_payload_bytes)
            side = self.placement.side if self.placement is not None else 640
            viewport = SquareViewport(layout.width, layout.height, side)

            def mouse(event: int, x: int, y: int, flags: int, _param: object) -> None:
                if event == cv.EVENT_MOUSEWHEEL:
                    viewport.wheel(x, y, flags)
                elif event == cv.EVENT_LBUTTONDBLCLK:
                    viewport.reset()

            cv.namedWindow(self.title, cv.WINDOW_NORMAL)
            window = True
            cv.imshow(self.title, numpy.zeros((side, side), numpy.uint8))
            cv.resizeWindow(self.title, side, side)
            cv.setMouseCallback(self.title, mouse)
            cv.waitKey(1)
            if self.placement is not None:
                position_preview_frame(self.title, self.placement.x, self.placement.y)
                if self.placement.gui_window_handle:
                    owner = WindowsPreviewOwner(
                        self.title,
                        self.placement.gui_window_handle,
                        self.placement.gui_process_id,
                        self.placement.gui_process_creation_time_100ns,
                    )
            # The card names the source; Win32 later positions by handle, not title.
            native: str | int = self.title
            if sys.platform == "win32":
                native = self.native_handle = preview_window_handle(self.title)
                blank_preview_caption(native)
            owner_minimized = owner.sync() if owner is not None else False
            if (
                not owner_minimized
                and cv.getWindowProperty(self.title, cv.WND_PROP_VISIBLE) < 1
            ):
                raise RuntimeError("OpenCV window did not become visible")
            if owner is not None:
                geometry.arranged(owner.geometry())
            self.visible = True
            last = -1
            frame_wakeup = True
            latest: Any = None
            while not self._stop.is_set() and not ring.retired:
                # Check X before imshow: imshow must never recreate a user-closed window.
                cv.waitKey(1)
                placement = self._take_placement()
                if (
                    owner is not None
                    and placement is not None
                    and self.placement is not None
                ):
                    same_process = (
                        placement.gui_process_id,
                        placement.gui_process_creation_time_100ns,
                    ) == (
                        self.placement.gui_process_id,
                        self.placement.gui_process_creation_time_100ns,
                    )
                    if not same_process:
                        placement = None
                    elif (
                        placement.gui_window_handle != self.placement.gui_window_handle
                    ):
                        owner.retarget(placement.gui_window_handle)
                        self.placement.gui_window_handle = placement.gui_window_handle
                        geometry.arranged(owner.geometry())
                was_minimized = owner_minimized
                owner_minimized = owner.sync() if owner is not None else False
                if was_minimized and not owner_minimized and owner is not None:
                    geometry.arranged(owner.geometry())
                    if placement is None:
                        placement = self.placement
                if owner_minimized and placement is not None:
                    with self._layout_lock:
                        if self._pending_placement is None:
                            self._pending_placement = placement
                        else:
                            self._pending_placement.snap_to_grid |= (
                                placement.snap_to_grid
                            )
                if owner_minimized:
                    viewport.dirty = True
                if not owner_minimized and not self._visible(cv):
                    self.visible = False
                    break
                if owner is not None and not owner_minimized:
                    automatic = geometry.observe(owner.geometry())
                    if (
                        placement is not None
                        and (automatic or placement.snap_to_grid)
                        and self.placement is not None
                    ):
                        identity = (
                            "gui_window_handle",
                            "gui_process_id",
                            "gui_process_creation_time_100ns",
                        )
                        if all(
                            getattr(placement, field) == getattr(self.placement, field)
                            for field in identity
                        ):
                            cv.resizeWindow(self.title, placement.side, placement.side)
                            cv.waitKey(1)
                            position_preview_frame(
                                native, placement.x, placement.y, topmost=False
                            )
                            viewport.resize(placement.side)
                            geometry = PreviewGeometryGuard()
                            geometry.arranged(owner.geometry())
                            self.placement = placement
                            self.placement.snap_to_grid = False
                if not owner_minimized and viewport.dirty and latest is not None:
                    cv.imshow(self.title, viewport.render(latest, cv, numpy))
                count = ring.published_count if frame_wakeup else 0
                if count > 0 and count - 1 != last:
                    sequence = count - 1
                    read = ring.read_into(sequence, pixels, expected_run_id=run_id)
                    if read.status == "frame":
                        prepared = preparer.prepare_preview(pixels, self.output_bits)
                        latest = display_array(prepared, numpy)
                        if not owner_minimized:
                            cv.imshow(self.title, viewport.render(latest, cv, numpy))
                        if not self.ready.done():
                            cv.waitKey(1)
                            if not owner_minimized and not self._visible(cv):
                                raise RuntimeError(
                                    "OpenCV window closed before first image"
                                )
                            self.ready.set_result(None)
                        last = sequence
                        continue
                    if read.status == "retired":
                        break
                frame_wakeup = ring.wait(10_000_000)
        except Exception as exc:
            if isinstance(exc, RingAllocationError):
                ring = exc.partial
            self.failure = str(exc)
        finally:
            if owner is not None:
                try:
                    owner.close()
                except Exception as exc:
                    self.failure = f"Preview GUI owner cleanup failed: {exc}"
                    closed = False
            if window:
                try:
                    # A native X may already have destroyed it.
                    try:
                        cv.destroyWindow(self.title)
                    except cv.error as exc:
                        if "NULL window" not in str(exc):
                            raise
                    cv.waitKey(1)
                    if self._visible(cv):
                        raise RuntimeError(
                            "OpenCV window remains visible after destroy"
                        )
                    self.visible = False
                except Exception as exc:
                    self.failure = f"OpenCV window cleanup unconfirmed: {exc}"
                    closed = False
            if ring is not None:
                try:
                    ring.close()
                except Exception as exc:
                    self.failure = f"Preview mapping cleanup unconfirmed: {exc}"
                    closed = False
            if not self.ready.done():
                self.ready.set_exception(
                    RuntimeError(self.failure or "Preview closed before ready")
                )
            self.done.set_result(closed)
            self.on_closed(self)

    def _visible(self, cv: Any) -> bool:
        try:
            return bool(cv.getWindowProperty(self.title, cv.WND_PROP_VISIBLE) >= 1)
        except cv.error as exc:
            # Win32 HighGUI also reports a destroyed X window as a null-window error.
            if "NULL window" in str(exc):
                return False
            raise
