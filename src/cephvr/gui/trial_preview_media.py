"""Bounded on-demand preview images and window-owned video decoders."""

from collections import OrderedDict
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColorSpace, QImage, QImageReader

from cephvr.visual_stimulus.config.media_profiles import TEXTURE_RECIPE_PROFILES
from cephvr.visual_stimulus.config.models.program_model import Program


class PreviewMedia(QObject):
    changed = pyqtSignal()

    def __init__(self, program: Program, root: str, parent: QObject) -> None:
        super().__init__(parent)
        self.assets = {a.asset_id: a for a in program.assets}
        self.paths = {a.asset_id: a.logical_path for a in program.assets}
        self.root = Path(root).resolve()
        self.images: OrderedDict[str, QImage] = OrderedDict()
        self.image_sizes: dict[str, tuple[int, int]] = {}
        self.errors: dict[str, str] = {}
        self.videos: dict[str, tuple[Any, Any]] = {}
        self.frames: dict[str, QImage] = {}
        self.arenas: Any = None
        self.field_recipes: dict[str, Any] = {}

    def path(self, asset: str) -> Path:
        path = (self.root / self.paths[asset]).resolve()
        path.relative_to(self.root)
        return path

    def image(self, asset: str) -> QImage:
        if asset in self.images:
            self.images.move_to_end(asset)
            return self.images[asset]
        try:
            if self.assets[asset].profile in TEXTURE_RECIPE_PROFILES:
                image = self.recipe_image(asset)
                self.image_sizes[asset] = (image.width(), image.height())
            else:
                reader = QImageReader(str(self.path(asset)))
                size = reader.size()
                self.image_sizes[asset] = (size.width(), size.height())
                if size.width() * size.height() > 64_000_000:
                    raise ValueError("Preview image exceeds 64 megapixels")
                size.scale(1024, 1024, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(size)
                image = reader.read()
                if image.isNull():
                    raise ValueError(reader.errorString())
        except (KeyError, OSError, ValueError) as error:
            self.errors[asset] = str(error)
            image = QImage()
        self.images[asset] = image
        if len(self.images) > 16:
            removed, _ = self.images.popitem(last=False)
            self.image_sizes.pop(removed, None)
        return image

    def recipe_image(self, asset: str) -> QImage:
        from cephvr.visual_stimulus.config.models.schema_common import (
            DEFAULT_DOCUMENT_BYTES,
        )
        from cephvr.visual_stimulus.resources.texture_recipe import (
            generate_texture_recipe,
            parse_texture_recipe,
        )

        with self.path(asset).open("rb") as stream:
            raw = stream.read(DEFAULT_DOCUMENT_BYTES + 1)
        from cephvr.visual_stimulus.resources.grating_recipe import interpreted_recipe

        recipe = interpreted_recipe(
            parse_texture_recipe(raw, max_texture_pixels=1024 * 1024),
            self.assets[asset].profile,
        )
        if recipe.physical_field:
            override = self.assets[asset].color_override
            if override is not None and override.transfer != "linear":
                raise ValueError("Physical texture fields require linear color")
            self.field_recipes[asset] = recipe
        pixels = generate_texture_recipe(recipe)
        height, width, _ = pixels.shape
        image = QImage(
            pixels.tobytes(),
            width,
            height,
            pixels.strides[0],
            QImage.Format.Format_RGB888,
        ).copy()
        override = self.assets[asset].color_override
        transfer = override.transfer if override else "linear"
        if transfer not in ("linear", "srgb"):
            raise ValueError(f"Recipe preview does not support {transfer} transfer")
        image.setColorSpace(
            QColorSpace(
                QColorSpace.NamedColorSpace.SRgbLinear
                if transfer == "linear"
                else QColorSpace.NamedColorSpace.SRgb
            )
        )
        return image.convertedToColorSpace(
            QColorSpace(QColorSpace.NamedColorSpace.SRgb)
        )

    def field_image(
        self, asset: str, width: float, height: float, phase_mm: tuple[float, float]
    ) -> QImage:
        from cephvr.visual_stimulus.resources.texture_recipe import (
            generate_texture_recipe,
        )

        recipe = self.field_recipes[asset]
        pixels = generate_texture_recipe(
            recipe,
            extent_mm=(width, height),
            sample_size=(512, 512),
            offset_mm=phase_mm,
        )
        image = QImage(
            pixels.tobytes(), 512, 512, 512 * 3, QImage.Format.Format_RGB888
        ).copy()
        image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgbLinear))
        return image.convertedToColorSpace(
            QColorSpace(QColorSpace.NamedColorSpace.SRgb)
        )

    def video(self, identity: str, asset: str, seconds: float, at_end: str) -> QImage:
        if identity not in self.videos:
            try:
                from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink

                player = QMediaPlayer(self)
                sink = QVideoSink(self)
                player.setVideoSink(sink)
                sink.videoFrameChanged.connect(
                    lambda frame, key=identity: self.receive(key, frame.toImage())
                )
                player.errorOccurred.connect(
                    lambda _code, message, key=asset: self.errors.__setitem__(
                        key, message
                    )
                )
                player.setSource(QUrl.fromLocalFile(str(self.path(asset))))
                player.play()
                self.videos[identity] = (player, sink)
            except (ImportError, OSError, KeyError, ValueError) as error:
                self.errors[asset] = str(error)
                return QImage()
        player, _ = self.videos[identity]
        duration = player.duration()
        position = max(0, round(seconds * 1000))
        if duration > 0 and position >= duration:
            if at_end == "hide":
                return QImage()
            position = position % duration if at_end == "loop" else max(0, duration - 1)
        if abs(player.position() - position) > 25:
            player.setPosition(position)
        return self.frames.get(identity, QImage())

    def receive(self, identity: str, image: QImage) -> None:
        if not image.isNull():
            if identity in self.videos:
                self.videos[identity][0].pause()
            self.frames[identity] = image.scaled(
                1024, 1024, Qt.AspectRatioMode.KeepAspectRatio
            )
            self.changed.emit()

    def retain_videos(self, identities: set[str]) -> None:
        for key in tuple(self.videos):
            if key not in identities:
                player, sink = self.videos.pop(key)
                player.stop()
                player.deleteLater()
                sink.deleteLater()
                self.frames.pop(key, None)

    def close(self) -> None:
        self.retain_videos(set())
        self.images.clear()
        self.field_recipes.clear()
        self.frames.clear()
        self.arenas = None
