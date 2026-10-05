"""Bounded, approximate CPU arena view for planning; physical rendering stays backend-owned."""

from collections import OrderedDict
from math import dist
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPolygonF, QTransform

from cephvr.gui.trial_preview_media import PreviewMedia
from cephvr.gui.trial_preview_plan import PreviewLayer
from cephvr.gui.trial_preview_surfaces import PreviewGeometry
from cephvr.visual_stimulus.rendering.arena import arena_model_matrix
from cephvr.visual_stimulus.rendering.color import linear_to_srgb
from cephvr.visual_stimulus.resources.glb import GLBScene, parse_glb


def transform(matrix: Any, point: tuple[float, ...]) -> tuple[float, float, float]:
    return tuple(
        sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3] for r in range(3)
    )


class PreviewArenas:
    def __init__(self) -> None:
        self.scenes: OrderedDict[str, GLBScene] = OrderedDict()
        self.textures: dict[tuple[str, int], QImage] = {}
        self.errors: dict[str, str] = {}

    def get(self, asset: str, media: PreviewMedia) -> GLBScene:
        if asset in self.scenes:
            self.scenes.move_to_end(asset)
            return self.scenes[asset]
        if asset in self.errors:
            raise ValueError(self.errors[asset])
        try:
            return self.load(asset, media)
        except (ValueError, OSError) as error:
            self.errors[asset] = str(error)
            raise

    def load(self, asset: str, media: PreviewMedia) -> GLBScene:
        path = media.path(asset)

        def read(source: Path) -> bytes:
            with source.open("rb") as stream:
                data = stream.read(16_777_217)
            if len(data) > 16_777_216:
                raise ValueError("Planning arena exceeds 16 MiB")
            return data

        def resolve(uri: str) -> bytes:
            target = (path.parent / uri).resolve()
            target.relative_to(media.root)
            return read(target)

        scene = parse_glb(
            read(path), max_bytes=16_777_216, max_elements=100_000, resolve=resolve
        )
        triangles = sum(len(p.indices) // 3 for n in scene.nodes for p in n.primitives)
        if triangles > 4000:
            raise ValueError(
                "Planning preview supports up to 4000 arena triangles; use a reduced preview asset"
            )
        self.scenes[asset] = scene
        if len(self.scenes) > 2:
            old, _ = self.scenes.popitem(last=False)
            self.textures = {k: v for k, v in self.textures.items() if k[0] != old}
        return scene


def draw_arena(
    painter: QPainter,
    rect: QRectF,
    face: str,
    layer: PreviewLayer,
    media: PreviewMedia,
    geometry: PreviewGeometry,
) -> None:
    assert layer.setting.kind == "arena"
    surface = geometry.surfaces.get(face)
    eye = geometry.observer
    if surface is None or not surface.corners or eye is None:
        raise ValueError("Set rig/screen geometry to preview the 3D arena")
    arenas = getattr(media, "arenas", None)
    if arenas is None:
        arenas = PreviewArenas()
        media.arenas = arenas
    scene = arenas.get(str(layer.setting.asset_id), media)
    model = arena_model_matrix(layer.setting, dict(layer.values))
    bl, br, _, tl = surface.corners
    right = tuple((br[i] - bl[i]) / surface.width for i in range(3))
    up = tuple((tl[i] - bl[i]) / surface.height for i in range(3))
    normal = (
        right[1] * up[2] - right[2] * up[1],
        right[2] * up[0] - right[0] * up[2],
        right[0] * up[1] - right[1] * up[0],
    )

    def dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    plane = dot(tuple(bl[i] - eye[i] for i in range(3)), normal)

    def project(point: tuple[float, ...]) -> QPointF | None:
        ray = tuple(point[i] - eye[i] for i in range(3))
        denominator = dot(ray, normal)
        if abs(denominator) < 1e-9 or plane / denominator <= 0:
            return None
        location = tuple(
            eye[i] + plane / denominator * ray[i] - bl[i] for i in range(3)
        )
        return QPointF(
            rect.left() + dot(location, right) / surface.width * rect.width(),
            rect.bottom() - dot(location, up) / surface.height * rect.height(),
        )

    triangles = []
    for node in scene.nodes:
        matrix = tuple(
            tuple(node.matrix[c * 4 + r] for c in range(4)) for r in range(4)
        )
        for primitive in node.primitives:
            vertices = [
                transform(model, transform(matrix, p)) for p in primitive.positions
            ]
            projected = [project(p) for p in vertices]
            material = (
                scene.materials[primitive.material_index]
                if primitive.material_index is not None
                else None
            )
            for i in range(0, len(primitive.indices), 3):
                ids = primitive.indices[i : i + 3]
                points = [projected[k] for k in ids]
                if any(p is None for p in points):
                    continue
                depth = sum(dist(eye, vertices[k]) for k in ids) / 3
                triangles.append((depth, points, material, primitive, ids))
    painter.setPen(Qt.PenStyle.NoPen)
    for _depth, points, material, primitive, ids in sorted(
        triangles, key=lambda item: item[0], reverse=True
    ):
        polygon = QPolygonF(points)
        rgb = material.base_color_factor[:3] if material else (1, 1, 1)
        painter.setBrush(
            QColor.fromRgbF(*(max(0, min(1, linear_to_srgb(float(c)))) for c in rgb))
        )
        painter.drawPolygon(polygon)
        if material and material.texture_index is not None and primitive.texcoords:
            key = (str(layer.setting.asset_id), material.texture_index)
            if key not in arenas.textures:
                arenas.textures[key] = QImage.fromData(
                    scene.textures[material.texture_index].image
                )
            texture = arenas.textures[key]
            source = QPolygonF(
                [
                    QPointF(
                        primitive.texcoords[k][0] * texture.width(),
                        primitive.texcoords[k][1] * texture.height(),
                    )
                    for k in ids
                ]
            )
            source.append(source[0] + source[2] - source[1])
            target = QPolygonF(points)
            target.append(target[0] + target[2] - target[1])
            matrix2d = QTransform()
            if QTransform.quadToQuad(source, target, matrix2d):
                painter.save()
                clip = QPainterPath()
                clip.addPolygon(polygon)
                painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
                painter.setTransform(matrix2d, True)
                painter.drawImage(QPointF(), texture)
                painter.restore()
