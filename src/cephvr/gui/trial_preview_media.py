"""Bounded on-demand preview images and window-owned video decoders."""

from collections import OrderedDict
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QImage, QImageReader

from cephvr.visual_stimulus.config.models.program_model import Program


class PreviewMedia(QObject):
    changed = pyqtSignal()

    def __init__(self, program: Program, root: str, parent: QObject) -> None:
        super().__init__(parent)
        self.paths = {a.asset_id: a.logical_path for a in program.assets}
        self.root = Path(root).resolve()
        self.images: OrderedDict[str, QImage] = OrderedDict()
        self.errors: dict[str, str] = {}
        self.videos: dict[str, tuple[Any, Any]] = {}
        self.frames: dict[str, QImage] = {}
        self.arenas: Any = None

    def path(self, asset: str) -> Path:
        path = (self.root / self.paths[asset]).resolve()
        path.relative_to(self.root)
        return path

    def image(self, asset: str) -> QImage:
        if asset in self.images:
            self.images.move_to_end(asset)
            return self.images[asset]
        try:
            reader = QImageReader(str(self.path(asset)))
            size = reader.size()
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
            self.images.popitem(last=False)
        return image

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
        self.frames.clear()
        self.arenas = None
