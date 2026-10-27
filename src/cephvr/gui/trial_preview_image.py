"""Bounded image fit and unfolded-source sampling for planning previews."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPolygonF, QTransform

from cephvr.visual_stimulus.rendering.image_fit import (
    fitted_uv_scale,
    source_rectangles,
)


def fitted_image(image: QImage, fit: str, width: float, height: float) -> QImage:
    """Preview the shader's centered fit within the authored image rectangle."""
    sx, sy = fitted_uv_scale(fit, image.width() / image.height(), width / height)
    if (sx, sy) == (1.0, 1.0):
        return image
    aspect = width / height
    output = QImage(
        max(1, round(512 * min(1.0, aspect))),
        max(1, round(512 * min(1.0, 1.0 / aspect))),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    output.fill(Qt.GlobalColor.transparent)
    painter = QPainter(output)
    if fit == "contain":
        target = QRectF(
            output.width() * (1.0 - 1.0 / sx) / 2,
            output.height() * (1.0 - 1.0 / sy) / 2,
            output.width() / sx,
            output.height() / sy,
        )
        painter.drawImage(target, image, QRectF(image.rect()))
    else:
        source = QRectF(
            image.width() * (1.0 - sx) / 2,
            image.height() * (1.0 - sy) / 2,
            image.width() * sx,
            image.height() * sy,
        )
        painter.drawImage(QRectF(output.rect()), image, source)
    painter.end()
    return output


def screen_image(
    image: QImage, fit: str, original: tuple[int, int], target: tuple[int, int]
) -> QImage:
    """Scale the preview only; select the source crop using original pixel counts."""
    if fit == "resize":
        return image
    crop, padding = source_rectangles(original, target)
    scale = 512 / max(target)
    output = QImage(
        max(1, round(target[0] * scale)),
        max(1, round(target[1] * scale)),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    output.fill(Qt.GlobalColor.transparent)
    painter = QPainter(output)
    painter.drawImage(
        QRectF(
            padding[0] / target[0] * output.width(),
            padding[1] / target[1] * output.height(),
            padding[2] / target[0] * output.width(),
            padding[3] / target[1] * output.height(),
        ),
        image,
        QRectF(
            crop[0] / original[0] * image.width(),
            crop[1] / original[1] * image.height(),
            crop[2] / original[0] * image.width(),
            crop[3] / original[1] * image.height(),
        ),
    )
    painter.end()
    return output


def folded_image(
    image: QImage,
    original: tuple[int, int],
    mapping: tuple[float, ...],
    target: tuple[int, int],
) -> QImage:
    """Render the same source-pixel affine map as the Fold shader at preview size."""
    scale = 512 / max(target)
    output = QImage(
        max(1, round(target[0] * scale)),
        max(1, round(target[1] * scale)),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    output.fill(Qt.GlobalColor.transparent)
    x, y, ux, uy, vx, vy = mapping
    source = QPolygonF(
        [
            QPointF(
                (x + u * ux + v * vx) / original[0] * image.width(),
                (y + u * uy + v * vy) / original[1] * image.height(),
            )
            for u, v in ((0, 0), (1, 0), (1, 1), (0, 1))
        ]
    )
    destination = QPolygonF(
        [
            QPointF(0, output.height()),
            QPointF(output.width(), output.height()),
            QPointF(output.width(), 0),
            QPointF(0, 0),
        ]
    )
    transform = QTransform()
    if not QTransform.quadToQuad(source, destination, transform):
        raise ValueError("Fold source mapping is degenerate")
    painter = QPainter(output)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setTransform(transform)
    painter.drawImage(QPointF(), image)
    painter.end()
    return output
