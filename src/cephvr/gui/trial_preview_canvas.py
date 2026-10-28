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
from cephvr.gui.theme import colors_for
from cephvr.gui.trial_preview_image import fitted_image as fitted_image
from cephvr.gui.trial_preview_image import folded_image
from cephvr.gui.trial_preview_image import screen_image as screen_image
from cephvr.gui.trial_preview_media import PreviewMedia
from cephvr.gui.trial_preview_plan import PreviewLayer
from cephvr.gui.trial_preview_surfaces import PreviewGeometry
from cephvr.visual_stimulus.config.models.program_model import SparseNoiseSettings
from cephvr.visual_stimulus.rendering.color import linear_to_srgb
from cephvr.visual_stimulus.rendering.image_fit import (
    SCREEN_IMAGE_FITS,
    valid_image_corners,
)
from cephvr.visual_stimulus.rendering.layer_projection import (
    angular_corners,
    covering_texture,
    physical_corners,
)
from cephvr.visual_stimulus.rendering.motion import evaluate_function
from cephvr.visual_stimulus.rendering.types import InstanceSnapshot
from cephvr.visual_stimulus.resources.sparse_noise import grid_for_extent, pattern_rgba
from cephvr.visual_stimulus.resources.sparse_noise_stream import (
    MAX_GRID_CELLS,
    layer_recipe,
)


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
        self.setObjectName("TrialPreviewPixels")
        self.face, self.media, self.rig_geometry = face, media, geometry
        self.layers: tuple[PreviewLayer, ...] = ()
        self.background = QColor("black")
        self.local_ns = 0
        self.setMinimumSize(180, 130)
        self.setAccessibleName(f"{face} stimulus preview")

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(colors_for(self).window))
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
        output = self.correct_frame(image)
        surface = self.rig_geometry.surfaces.get(self.face)
        if surface is not None:
            painter = QPainter(output)
            for x, y, mask_width, mask_height in surface.blackout_zones:
                painter.fillRect(
                    QRectF(
                        x * output.width(),
                        (1 - y - mask_height) * output.height(),
                        mask_width * output.width(),
                        mask_height * output.height(),
                    ),
                    QColor("black"),
                )
            if surface.marker_rect is not None:
                # Placement illustration; submission-index alternation is renderer-owned.
                x, y, mask_width, mask_height = surface.marker_rect
                painter.fillRect(
                    QRectF(
                        x * output.width(),
                        (1 - y - mask_height) * output.height(),
                        mask_width * output.width(),
                        mask_height * output.height(),
                    ),
                    QColor("white"),
                )
            painter.end()
        return output

    def correct_frame(self, image: QImage) -> QImage:
        surface = self.rig_geometry.surfaces.get(self.face)
        correction = surface.correction if surface else None
        if correction is None:
            return image
        size = image.size()
        if self.face == "Bottom":
            size.transpose()
        output = QImage(size, image.format())
        output.fill(QColor("black"))
        painter = QPainter(output)
        if correction.error:
            painter.setPen(QColor(colors_for(self).text))
            painter.drawText(
                QRectF(output.rect()).adjusted(8, 8, -8, -8),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                correction.error,
            )
        else:
            source = QPolygonF(
                [
                    QPointF(u * image.width(), (1 - v) * image.height())
                    for u, v in (
                        correction.source_uv or ((0, 0), (1, 0), (1, 1), (0, 1))
                    )
                ]
            )
            target = QPolygonF(
                [
                    QPointF(x * output.width(), (1 - y) * output.height())
                    for x, y in correction.corners
                ]
            )
            transform = QTransform()
            if QTransform.quadToQuad(source, target, transform):
                if correction.valid_area is not None:
                    x0, y0, x1, y1 = correction.valid_area
                    painter.setClipRect(
                        QRectF(
                            x0 * output.width(),
                            (1 - y1) * output.height(),
                            (x1 - x0) * output.width(),
                            (y1 - y0) * output.height(),
                        )
                    )
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
            painter.setPen(QColor(colors_for(self).text))
            painter.drawText(
                rect.adjusted(12, 12, -12, -12),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "\n".join(dict.fromkeys(errors)),
            )

    def sparse_image(
        self, setting: SparseNoiseSettings, values: dict[str, float]
    ) -> tuple[QImage, tuple[float, float]]:
        """Generated pattern over its background, plus the grid's physical extent (mm)."""
        recipe = layer_recipe(setting)
        surface = self.rig_geometry.surfaces.get(self.face)
        width, height = (
            (surface.width, surface.height)
            if surface
            else (values["width"], values["height"])
        )
        grid = grid_for_extent(
            recipe, recipe.surfaces[0], width, height, max_cells=MAX_GRID_CELLS
        )
        index = setting.pattern_at(self.local_ns)

        def build() -> QImage:
            pixels = pattern_rgba(recipe, grid, index)
            pattern = QImage(
                pixels,
                grid.columns,
                grid.rows,
                grid.columns * 4,
                QImage.Format.Format_RGBA8888_Premultiplied,
            )
            image = QImage(pattern.size(), QImage.Format.Format_ARGB32_Premultiplied)
            gray = linear_to_srgb(setting.appearance.background_linear)
            image.fill(QColor.fromRgbF(gray, gray, gray))
            compose = QPainter(image)
            compose.drawImage(0, 0, pattern)
            compose.end()
            return image

        key = (recipe.model_dump_json(), grid, index)
        return self.media.sparse_pattern(key, build), (grid.width_mm, grid.height_mm)

    def draw_layer(self, painter: QPainter, rect: QRectF, layer: PreviewLayer) -> None:
        setting, values = layer.setting, layer.values
        inline_grating = (
            setting.kind == "texture"
            and setting.grating
            and setting.pattern.kind != "image_tile"
        )
        if inline_grating:
            # Sample the visible field, not an ever-growing translated raster.
            angle = radians(values["rotation"])
            phase = values["phase_x"] - values["frequency"] * (
                values["x"] * cos(angle) + values["y"] * sin(angle)
            )
            values = dict(values, x=0.0, y=0.0, phase_x=phase % 1.0)
        surface = self.rig_geometry.surfaces.get(self.face)
        if surface and surface.corners:
            snapshot = covering_texture(
                self.rig_geometry.artifact(),
                InstanceSnapshot(
                    setting.instance_id,
                    setting.kind,
                    True,
                    tuple(values.items()),
                    setting,
                ),
                self.face.lower(),
            )
            values = {key: float(value) for key, value in snapshot.state}
        if setting.kind == "arena":
            return
        uniform = setting.kind == "texture" and setting.uniform
        if uniform or inline_grating:
            asset = ""
        elif setting.kind == "texture":
            if setting.pattern.kind != "image_tile":
                raise ValueError(
                    "Prepared image textures are required for this planning preview"
                )
            asset = str(setting.pattern.asset_id)
        elif setting.kind == "sparse_noise":
            asset = ""
        else:
            asset = str(setting.asset_id)
        if inline_grating:
            assert setting.kind == "texture"
            from cephvr.gui.grating_image import grating_image

            image = grating_image(setting, values)
        elif uniform:
            assert setting.kind == "texture"
            image = QImage(1, 1, QImage.Format.Format_RGB32)
            image.fill(
                QColor.fromRgbF(
                    *(
                        linear_to_srgb(float(c))
                        for c in setting.mean_linear_rgb
                        if isinstance(c, (int, float))
                    )
                )
            )
        elif setting.kind == "sparse_noise":
            image, extent = self.sparse_image(setting, values)
            values = dict(values, width=extent[0], height=extent[1])
        elif setting.kind == "video":
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
        if setting.kind == "image" and setting.fit in SCREEN_IMAGE_FITS:
            surface = self.rig_geometry.surfaces.get(self.face)
            if setting.fit == "source" and (
                surface is None or surface.image_pixels is None
            ):
                raise ValueError(
                    "Assign a projector resolution to preview Source pixels"
                )
            target = (
                surface.image_pixels if surface and surface.image_pixels else (1, 1)
            )
            if setting.fit == "fold":
                image = folded_image(
                    image,
                    self.media.image_sizes[asset],
                    self.rig_geometry.image_fold_map(self.face),
                    target,
                )
            else:
                image = screen_image(
                    image, setting.fit, self.media.image_sizes[asset], target
                )
            painter.setOpacity(max(0, min(1, values["opacity"])))
            correction = surface.correction if surface else None
            if correction and correction.corners and correction.source_uv:
                corners = valid_image_corners(
                    correction.source_uv,
                    correction.corners,
                    correction.valid_area or (0.0, 0.0, 1.0, 1.0),
                )
                points = [
                    QPointF(
                        rect.center().x() + x * rect.width() / 2,
                        rect.center().y() - y * rect.height() / 2,
                    )
                    for x, y in corners
                ]
                image_quad(image, points, painter)
            else:
                painter.drawImage(rect, image)
            return
        width, height = values["width"], values["height"]
        if min(width, height) <= 0:
            return
        if setting.kind == "image":
            image = fitted_image(image, setting.fit, width, height)
        if setting.kind == "texture" and asset in self.media.field_recipes:
            if setting.space.kind != "physical_surface":
                raise ValueError(
                    "Physical texture fields require millimetre coordinates"
                )
            image = self.media.field_image(
                asset,
                width,
                height,
                (
                    values["phase_x"] * values["period_x"],
                    values["phase_y"] * values["period_y"],
                ),
            )
        elif setting.kind == "texture" and not uniform and not inline_grating:
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
            transform.translate(-values["phase_x"] * px, 512 + values["phase_y"] * py)
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
