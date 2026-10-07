"""Decode one bounded exact-source Tracking diagnostic frame for the GUI."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cephvr.acquisition.camera.native_formats import pylon_pixel_format
from cephvr.shared.pixels.preparer import PixelPreparer
from cephvr.shared.pixels.types import PixelLayout
from cephvr.tracking.v1 import services_pb2 as tracking


@dataclass(frozen=True)
class TrackingDiagnosticPresentation:
    image: QImage
    diagnostic_id: str
    configuration_revision: int
    preview_run_id: str
    source_frame_id: int
    source_host_receipt_ns: int
    produced_monotonic_ns: int
    points: tuple[tuple[int, str, float, float], ...]
    rectangles: tuple[tuple[int, str, float, float, float, float], ...]
    vectors: tuple[tuple[int, str, float, float, float, float], ...]
    labels: tuple[tuple[int, str], ...]
    overlays_truncated: bool


class TrackingDiagnosticViewer(QDialog):
    """Read-only detached viewer; each paint uses one exact-frame presentation."""

    detached = pyqtSignal()
    use_frame_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tracking diagnostic")
        self.resize(900, 680)
        layout = QVBoxLayout(self)
        self.image = QLabel("Waiting for the first Tracking diagnostic frame")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image, 1)
        self.status = QLabel("Pre-Setup diagnostic")
        self.timing = QLabel("Last — · maximum —")
        layout.addWidget(self.status)
        layout.addWidget(self.timing)
        actions = QHBoxLayout()
        self.use_frame = QPushButton("Use this frame for annotation")
        self.use_frame.setEnabled(False)
        self.use_frame.clicked.connect(self.use_frame_requested.emit)
        actions.addWidget(self.use_frame)
        actions.addStretch()
        layout.addLayout(actions)

    def show_presentation(
        self,
        presentation: TrackingDiagnosticPresentation,
        *,
        status: str,
        last_duration_ns: int,
        maximum_duration_ns: int,
    ) -> None:
        canvas = presentation.image.copy()
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = (QColor("#38bdf8"), QColor("#fbbf24"), QColor("#fb7185"))
        for _stage, name, x, y in presentation.points:
            painter.setPen(QPen(colors[0], max(1, canvas.width() / 400)))
            radius = max(3.0, canvas.width() / 160)
            painter.drawEllipse(
                int(x - radius), int(y - radius), int(radius * 2), int(radius * 2)
            )
            painter.drawText(int(x + radius), int(y - radius), name)
        for _stage, name, x, y, width, height in presentation.rectangles:
            painter.setPen(QPen(colors[1], max(1, canvas.width() / 500)))
            painter.drawRect(int(x), int(y), int(width), int(height))
            painter.drawText(int(x), int(y), name)
        for _stage, name, x0, y0, x1, y1 in presentation.vectors:
            painter.setPen(QPen(colors[2], max(1, canvas.width() / 600)))
            painter.drawLine(int(x0), int(y0), int(x1), int(y1))
            painter.drawText(int(x1), int(y1), name)
        painter.end()
        self.image.setPixmap(
            QPixmap.fromImage(canvas).scaled(
                self.image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )
        self.use_frame.setEnabled(True)
        diagnostic_labels = " · ".join(text for _stage, text in presentation.labels)
        suffix = " · overlays truncated" if presentation.overlays_truncated else ""
        self.status.setText(
            f"{status} · frame {presentation.source_frame_id}"
            + (f" · {diagnostic_labels}" if diagnostic_labels else "")
            + suffix
        )
        self.timing.setText(
            f"Last {last_duration_ns / 1_000_000:.2f} ms · "
            f"maximum {maximum_duration_ns / 1_000_000:.2f} ms"
        )

    def show_unavailable(self, status: str) -> None:
        self.image.clear()
        self.image.setText(status)
        self.use_frame.setEnabled(False)
        self.status.setText(status)
        self.timing.setText("Last — · maximum —")

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802
        self.detached.emit()
        super().closeEvent(event)


def tracking_diagnostic_presentation(
    frame: tracking.TrackingDiagnosticFrame,
    *,
    diagnostic_id: str,
    configuration_revision: int,
    preview_run_id: str,
    maximum_image_bytes: int,
) -> TrackingDiagnosticPresentation:
    """Convert a matching bounded response without changing reference draft data."""
    if not frame.available:
        raise ValueError(frame.unavailable_reason or "diagnostic image is unavailable")
    if (
        frame.diagnostic_id != diagnostic_id
        or frame.configuration_revision != configuration_revision
        or frame.preview_run_id != preview_run_id
    ):
        raise ValueError("diagnostic frame is outside the current preview scope")
    image = frame.image
    if (
        not image.HasField("width")
        or not image.HasField("height")
        or not image.HasField("row_stride_bytes")
        or not image.HasField("image_payload_bytes")
        or image.width <= 0
        or image.height <= 0
        or image.image_payload_bytes <= 0
        or image.image_payload_bytes > maximum_image_bytes
        or len(frame.image_bytes) != image.image_payload_bytes
    ):
        raise ValueError("diagnostic image layout or byte bound is invalid")
    layout = PixelLayout(
        image.width,
        image.height,
        pylon_pixel_format(image.pixel_format),
        image.row_stride_bytes,
        image.image_payload_bytes,
    )
    prepared = PixelPreparer(layout).prepare_preview(frame.image_bytes, 8)
    qimage_format = (
        QImage.Format.Format_Grayscale8
        if prepared.channel_order == "gray"
        else QImage.Format.Format_RGB888
    )
    qimage = QImage(
        bytes(prepared.data),
        prepared.width,
        prepared.height,
        prepared.row_stride_bytes,
        qimage_format,
    ).copy()
    if qimage.isNull():
        raise ValueError("diagnostic image could not be decoded")
    return TrackingDiagnosticPresentation(
        image=qimage,
        diagnostic_id=frame.diagnostic_id,
        configuration_revision=frame.configuration_revision,
        preview_run_id=frame.preview_run_id,
        source_frame_id=frame.source_frame_id,
        source_host_receipt_ns=frame.source_host_receipt_ns,
        produced_monotonic_ns=frame.produced_monotonic_ns,
        points=tuple(
            (item.stage, item.label, item.x_px, item.y_px) for item in frame.points
        ),
        rectangles=tuple(
            (
                item.stage,
                item.label,
                item.x_px,
                item.y_px,
                item.width_px,
                item.height_px,
            )
            for item in frame.rectangles
        ),
        vectors=tuple(
            (
                item.stage,
                item.label,
                item.start_x_px,
                item.start_y_px,
                item.end_x_px,
                item.end_y_px,
            )
            for item in frame.vectors
        ),
        labels=tuple((item.stage, item.text) for item in frame.labels),
        overlays_truncated=frame.overlays_truncated,
    )
