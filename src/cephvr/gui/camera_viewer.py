"""A10 latest-frame viewer; the acquisition worker retains camera ownership."""

from __future__ import annotations

import threading
from uuid import UUID

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout

from cephvr.acquisition.buffers.ring import SharedRing
from cephvr.acquisition.camera.native_formats import pylon_pixel_format
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.shared.pixels.preparer import PixelPreparer
from cephvr.shared.pixels.types import PixelLayout


class PreviewReader(QThread):
    """Wait for frames and keep only the newest pending GUI image."""

    changed = pyqtSignal()
    attached = pyqtSignal()
    failed = pyqtSignal(str)
    released = pyqtSignal()

    def __init__(
        self,
        attachment: acq.FrameBufferAttachment,
        output_bits: int = 8,
        run_id: str | None = None,
    ) -> None:
        super().__init__()
        self.attachment = attachment
        self.output_bits = output_bits
        self.run_id = run_id
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: tuple[bytes, int, int, int, str] | None = None
        self._pending = False

    def take_latest(self) -> tuple[bytes, int, int, int, str] | None:
        with self._lock:
            latest = self._latest
            self._pending = False
            return latest

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        ring: SharedRing | None = None
        attached = False
        failed = False
        try:
            if self.output_bits != 8:
                raise ValueError(
                    f"Preview output depth {self.output_bits} is unsupported by the GUI image path"
                )
            descriptor = self.attachment.buffer
            image = descriptor.image
            layout = PixelLayout(
                image.width,
                image.height,
                pylon_pixel_format(image.pixel_format),
                image.row_stride_bytes,
                image.image_payload_bytes,
            )
            ring = SharedRing.attach(
                self.attachment, layout, self.attachment.sync.target
            )
            preparer = PixelPreparer(layout)
            pixels = bytearray(layout.image_payload_bytes)
            scope = descriptor.WhichOneof("scope")
            if scope == "preview":
                run_id = UUID(descriptor.preview.acquisition_run_id)
            elif scope == "session" and self.run_id:
                run_id = UUID(self.run_id)
            else:
                raise ValueError("Preview run identity was not supplied")
            attached = True
            self.attached.emit()
            last = -1
            while not self._stop.is_set() and not ring.retired:
                count = ring.published_count
                if count > 0 and count - 1 != last:
                    sequence = count - 1
                    read = ring.read_into(sequence, pixels, expected_run_id=run_id)
                    if read.status == "frame":
                        prepared = preparer.prepare_preview(pixels, self.output_bits)
                        frame = (
                            bytes(prepared.data),
                            prepared.width,
                            prepared.height,
                            prepared.row_stride_bytes,
                            prepared.channel_order,
                        )
                        with self._lock:
                            self._latest = frame
                            if not self._pending:
                                self._pending = True
                                self.changed.emit()
                        last = sequence
                        continue
                    if read.status == "retired":
                        break
                ring.wait(500_000_000)
        except Exception as exc:
            failed = True
            self.failed.emit(str(exc))
        finally:
            if ring is not None:
                try:
                    ring.close()
                except Exception as exc:
                    failed = True
                    self.failed.emit(f"Viewer mapping cleanup failed: {exc}")
                if attached and not failed:
                    self.released.emit()


class CameraViewer(QDialog):
    closed = pyqtSignal()

    def __init__(self, reader: PreviewReader, title: str) -> None:
        super().__init__()
        self.reader = reader
        self.setWindowTitle(title)
        self.resize(960, 700)
        layout = QVBoxLayout(self)
        self.image = QLabel("Waiting for camera frames…")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image)
        reader.changed.connect(self.update_image)

    def update_image(self) -> None:
        latest = self.reader.take_latest()
        if latest is None:
            return
        pixels, width, height, stride, order = latest
        fmt = (
            QImage.Format.Format_Grayscale8
            if order == "gray"
            else QImage.Format.Format_RGB888
        )
        image = QImage(pixels, width, height, stride, fmt).copy()
        self.image.setPixmap(
            QPixmap.fromImage(image).scaled(
                self.image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )

    def closeEvent(self, event: object) -> None:  # noqa: N802
        self.reader.stop()
        self.closed.emit()
        super().closeEvent(event)  # type: ignore[arg-type]
