"""Reduced-resolution 2D screen composition for read-only protocol planning."""

from math import cos, radians, sin

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPaintEvent,
    QPolygonF,
    QTransform,
)
from PyQt6.QtWidgets import QWidget

from cephvr.gui.stimulus_scope import surfaces
from cephvr.gui.trial_preview_media import PreviewMedia
from cephvr.gui.trial_preview_plan import PreviewLayer
from cephvr.gui.trial_preview_surfaces import PreviewGeometry
from cephvr.visual_stimulus.rendering.color import linear_to_srgb
from cephvr.visual_stimulus.rendering.layer_projection import (
    angular_corners,
    physical_corners,
)
from cephvr.visual_stimulus.rendering.motion import evaluate_function
from cephvr.visual_stimulus.rendering.types import InstanceSnapshot


def image_quad(image: QImage, points: list[QPointF], painter: QPainter) -> None:
    source = QPolygonF(
        [
            QPointF(0, image.height()),
            QPointF(image.width(), image.height()),
            QPointF(image.width(), 0),
            QPointF(0, 0),
        ]
    )
    transform = QTransform()
    if QTransform.quadToQuad(source, QPolygonF(points), transform):
        painter.setTransform(transform, True)
        painter.drawImage(QPointF(), image)


class PreviewCanvas(QWidget):
    def __init__(
        self, face: str, media: PreviewMedia, geometry: PreviewGeometry
    ) -> None:
        super().__init__()
        self.face, self.media, self.rig_geometry = face, media, geometry
        self.layers: tuple[PreviewLayer, ...] = ()
        self.background = QColor("black")
        self.local_ns = 0
        self.setMinimumSize(180, 130)
        self.setAccessibleName(f"{face} stimulus preview")

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#090f15"))
        surface = self.rig_geometry.surfaces.get(self.face)
        aspect = surface.width / surface.height if surface else 4 / 3
        target = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        width, height = (
            min(target.width(), target.height() * aspect),
            min(target.height(), target.width() / aspect),
        )
        rect = QRectF(
            target.center().x() - width / 2,
            target.center().y() - height / 2,
            width,
            height,
        )
        self.draw_content(painter, rect)

    def frame_image(self) -> QImage:
        surface = self.rig_geometry.surfaces.get(self.face)
        aspect = surface.width / surface.height if surface else 4 / 3
        width, height = int(min(512, 512 * aspect)), int(min(512, 512 / aspect))
        image = QImage(
            max(1, width), max(1, height), QImage.Format.Format_ARGB32_Premultiplied
        )
        image.fill(self.background)
        painter = QPainter(image)
        self.draw_content(painter, QRectF(0, 0, image.width(), image.height()))
        painter.end()
        return self.correct_frame(image)

    def correct_frame(self, image: QImage) -> QImage:
        surface = self.rig_geometry.surfaces.get(self.face)
        correction = surface.correction if surface else None
        if correction is None:
            return image
        output = QImage(image.size(), image.format())
        output.fill(QColor("black"))
        painter = QPainter(output)
        if correction.error:
            painter.setPen(QColor("#d6dfe7"))
            painter.drawText(
                QRectF(output.rect()).adjusted(8, 8, -8, -8),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                correction.error,
            )
        else:
            source = QPolygonF(
                [
                    QPointF(0, image.height()),
                    QPointF(image.width(), image.height()),
                    QPointF(image.width(), 0),
                    QPointF(0, 0),
                ]
            )
            target = QPolygonF(
                [
                    QPointF(x * image.width(), (1 - y) * image.height())
                    for x, y in correction.corners
                ]
            )
            transform = QTransform()
            if QTransform.quadToQuad(source, target, transform):
                painter.setTransform(transform)
                painter.drawImage(QPointF(0, 0), image)
        painter.end()
        return output

    def draw_content(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self.background)
        painter.setClipRect(rect)
        errors = []
        for layer in self.layers:
            setting = layer.setting
            if setting.kind != "arena" and self.face.lower() not in surfaces(
                setting.model_dump(mode="json")
            ):
                continue
            painter.save()
            try:
                if setting.kind == "arena":
                    from cephvr.gui.trial_preview_arena import draw_arena

                    draw_arena(
                        painter, rect, self.face, layer, self.media, self.rig_geometry
                    )
                else:
                    self.draw_layer(painter, rect, layer)
            except (ValueError, RuntimeError, KeyError, OSError) as error:
                errors.append(str(error))
            painter.restore()
        if errors:
            painter.setPen(QColor("#d6dfe7"))
            painter.drawText(
                rect.adjusted(12, 12, -12, -12),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "\n".join(dict.fromkeys(errors)),
            )

    def draw_layer(self, painter: QPainter, rect: QRectF, layer: PreviewLayer) -> None:
        setting, values = layer.setting, layer.values
        if setting.kind == "arena":
            return
        if setting.kind == "texture":
            if setting.pattern.kind != "image_tile":
                raise ValueError(
                    "Prepared image textures are required for this planning preview"
                )
            asset = str(setting.pattern.asset_id)
        else:
            asset = str(setting.asset_id)
        if setting.kind == "video":
            identity = f"{setting.instance_id}:{asset}"
            image = self.media.video(
                identity,
                asset,
                values["playback"] + max(0, self.local_ns) / 1e9,
                setting.end_behavior,
            )
        else:
            image = self.media.image(asset)
        if image.isNull():
            if asset in self.media.errors:
                raise ValueError(
                    f"{self.media.paths.get(asset, asset)}: {self.media.errors[asset]}"
                )
            if setting.kind == "video":
                return
            raise ValueError(f"Cannot read {self.media.paths.get(asset, asset)}")
        width, height = values["width"], values["height"]
        if min(width, height) <= 0:
            return
        if setting.kind == "texture":
            assert setting.pattern.kind == "image_tile"
            # Fixed resolution independent of epoch count; brush tiling never creates per-tile widgets.
            texture = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
            texture.fill(Qt.GlobalColor.transparent)
            tile = QPainter(texture)
            brush = QBrush(image)
            px = (
                evaluate_function(setting.pattern.period_x, self.local_ns) / width * 512
            )
            py = (
                evaluate_function(setting.pattern.period_y, self.local_ns)
                / height
                * 512
            )
            if min(px, py) <= 0:
                tile.end()
                raise ValueError("Texture periods must be positive")
            transform = QTransform()
            transform.translate(-values["phase_x"] * px, values["phase_y"] * py)
            transform.scale(px / image.width(), py / image.height())
            brush.setTransform(transform)
            tile.fillRect(texture.rect(), brush)
            tile.end()
            image = texture
        painter.setOpacity(max(0, min(1, values["opacity"])))
        surface = self.rig_geometry.surfaces.get(self.face)
        if surface and surface.corners:
            snapshot = InstanceSnapshot(
                setting.instance_id, setting.kind, True, tuple(values.items()), setting
            )
            artifact = self.rig_geometry.artifact()
            if setting.space.kind == "visual_angle":
                corners = angular_corners(artifact, snapshot, self.face.lower())
            else:
                surface_mapping = next(
                    m
                    for m in setting.space.mappings
                    if m.surface_id == self.face.lower()
                )
                corners = physical_corners(
                    artifact, snapshot, self.face.lower(), surface_mapping
                )
        else:
            if setting.space.kind == "visual_angle":
                # A local angular content view is explicit until physical planes are configured.
                sx, sy = 90.0, 90.0
                mapping = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
            else:
                sx, sy = (surface.width, surface.height) if surface else (100.0, 100.0)
                mapping = next(
                    m
                    for m in setting.space.mappings
                    if m.surface_id == self.face.lower()
                ).matrix
            determinant = mapping[0][0] * mapping[1][1] - mapping[0][1] * mapping[1][0]
            if abs(determinant) < 1e-12:
                raise ValueError("Singular stimulus mapping")
            angle = radians(values["rotation"])
            corners = []
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                x = (
                    values["x"]
                    + a * width / 2 * cos(angle)
                    - b * height / 2 * sin(angle)
                    - mapping[0][2]
                )
                y = (
                    values["y"]
                    + a * width / 2 * sin(angle)
                    + b * height / 2 * cos(angle)
                    - mapping[1][2]
                )
                corners.append(
                    (
                        2 * (mapping[1][1] * x - mapping[0][1] * y) / determinant / sx,
                        2 * (-mapping[1][0] * x + mapping[0][0] * y) / determinant / sy,
                    )
                )
        points = [
            QPointF(
                rect.center().x() + x * rect.width() / 2,
                rect.center().y() - y * rect.height() / 2,
            )
            for x, y in corners
        ]
        image_quad(image, points, painter)

    def present(
        self,
        layers: tuple[PreviewLayer, ...],
        local_ns: int,
        background: tuple[float, float, float],
    ) -> None:
        self.layers, self.local_ns = layers, local_ns
        self.background = QColor.fromRgbF(
            *(max(0, min(1, linear_to_srgb(c))) for c in background)
        )
        self.update()
