"""Display-only benchmark widgets; private buffers and one optional GL canvas."""

from __future__ import annotations

import time

import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QWidget


class FrameMetrics:
    def __init__(self) -> None:
        self.sequence = -1
        self.generated = 0.0
        self.painted = (-1, 0.0)
        self.reset()

    def reset(self) -> None:
        self.last_presented = -1
        self.last_swap = 0.0
        self.ages: list[float] = []
        self.swap_intervals: list[float] = []
        self.skipped = 0

    def presented(self) -> None:
        sequence, generated = self.painted
        if sequence == self.last_presented or sequence < 0:
            return
        now = time.perf_counter()
        self.ages.append((now - generated) * 1000)
        if self.last_presented >= 0:
            self.swap_intervals.append((now - self.last_swap) * 1000)
            self.skipped += max(0, sequence - self.last_presented - 1)
        self.last_presented, self.last_swap = sequence, now


class OwnedFrames:
    """GUI-thread-owned copies; source memory may be reused after accept returns."""

    def __init__(self, streams: int, pixels: int, channels: int) -> None:
        self.arrays = [
            np.zeros((pixels, pixels, channels), np.uint8) for _ in range(streams)
        ]
        image_format = (
            QImage.Format.Format_Grayscale8
            if channels == 1
            else QImage.Format.Format_RGB888
        )
        self.images = [
            QImage(a.data, pixels, pixels, a.strides[0], image_format)
            for a in self.arrays
        ]

    def accept(self, frames: list[np.ndarray]) -> None:
        if len(frames) != len(self.arrays):
            raise ValueError("Stream count changed")
        for target, source in zip(self.arrays, frames, strict=True):
            if source.shape != target.shape or source.dtype != target.dtype:
                raise ValueError("Image layout changed")
            np.copyto(target, source)


class BaselineCanvas(QOpenGLWidget):
    """Retain the original per-stream QImage-copy/QPainter comparison."""

    def __init__(self, paints: list, result: dict) -> None:
        super().__init__()
        self.metrics = FrameMetrics()
        self.image = QImage()
        self.paints, self.result = paints, result
        self.frameSwapped.connect(self.metrics.presented)

    def submit(self, frames: list[np.ndarray], sequence: int, generated: float) -> None:
        frame = frames[0]
        image_format = (
            QImage.Format.Format_Grayscale8
            if frame.shape[2] == 1
            else QImage.Format.Format_RGB888
        )
        self.image = QImage(
            frame.data, frame.shape[1], frame.shape[0], frame.strides[0], image_format
        ).copy()
        self.metrics.sequence, self.metrics.generated = sequence, generated
        self.update()

    def initializeGL(self) -> None:
        from OpenGL.GL import GL_RENDERER, GL_VENDOR, glGetString

        self.result.update(
            renderer=glGetString(GL_RENDERER).decode(),
            vendor=glGetString(GL_VENDOR).decode(),
        )

    def paintGL(self) -> None:
        begin = time.perf_counter()
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        side = min(self.width(), self.height())
        painter.drawImage(QRectF((self.width() - side) / 2, 0, side, side), self.image)
        painter.end()
        self.metrics.painted = self.metrics.sequence, self.metrics.generated
        self.paints.append((time.perf_counter() - begin) * 1000)


def rectangles(width: int, height: int, streams: int) -> list[QRectF]:
    cell = (width - 6 * (streams - 1)) / streams
    side = min(cell, height)
    return [
        QRectF(i * (cell + 6) + (cell - side) / 2, 0, side, side)
        for i in range(streams)
    ]


class RasterCanvas(QWidget):
    def __init__(self, streams: int, pixels: int, channels: int, paints: list) -> None:
        super().__init__()
        self.frames = OwnedFrames(streams, pixels, channels)
        self.metrics = FrameMetrics()
        self.paints = paints
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def submit(self, frames: list[np.ndarray], sequence: int, generated: float) -> None:
        self.frames.accept(frames)
        self.metrics.sequence, self.metrics.generated = sequence, generated
        self.update()

    def paintEvent(self, event) -> None:
        begin = time.perf_counter()
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for rect, image in zip(
            rectangles(self.width(), self.height(), len(self.frames.images)),
            self.frames.images,
            strict=True,
        ):
            painter.drawImage(rect, image)
        painter.end()
        self.metrics.painted = self.metrics.sequence, self.metrics.generated
        self.metrics.presented()
        self.paints.append((time.perf_counter() - begin) * 1000)


class TextureCanvas(QOpenGLWidget):
    def __init__(
        self, streams: int, pixels: int, channels: int, paints: list, result: dict
    ) -> None:
        super().__init__()
        self.frames = OwnedFrames(streams, pixels, channels)
        self.metrics = FrameMetrics()
        self.paints, self.result = paints, result
        self.channels = channels
        self.resources: list = []
        self.textures: list = []
        self.uploaded = -1
        self.uploads = 0
        self.frameSwapped.connect(self.metrics.presented)

    def submit(self, frames: list[np.ndarray], sequence: int, generated: float) -> None:
        self.frames.accept(frames)
        self.metrics.sequence, self.metrics.generated = sequence, generated
        self.update()

    def initializeGL(self) -> None:
        import moderngl

        self.ctx = moderngl.create_context()
        self.result.update(
            renderer=self.ctx.info["GL_RENDERER"], vendor=self.ctx.info["GL_VENDOR"]
        )
        self.program = self.ctx.program(
            vertex_shader="""
            #version 330
            in vec2 position;
            out vec2 uv;
            void main() {
                gl_Position = vec4(position, 0, 1);
                uv = vec2((position.x + 1) / 2, (1 - position.y) / 2);
            }
        """,
            fragment_shader="""
            #version 330
            uniform sampler2D image;
            uniform bool grayscale;
            in vec2 uv;
            out vec4 color;
            void main() {
                vec3 value = texture(image, uv).rgb;
                color = vec4(grayscale ? vec3(value.r) : value, 1);
            }
        """,
        )
        self.resources.append(self.program)
        buffer = self.ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], "f4"))
        self.resources.append(buffer)
        self.vao = self.ctx.simple_vertex_array(self.program, buffer, "position")
        self.resources.append(self.vao)
        self.program["image"].value = 0
        self.program["grayscale"].value = self.channels == 1
        for frame in self.frames.arrays:
            texture = self.ctx.texture((frame.shape[1], frame.shape[0]), self.channels)
            texture.filter = moderngl.LINEAR, moderngl.LINEAR
            self.textures.append(texture)
            self.resources.append(texture)
        self.context().aboutToBeDestroyed.connect(self.release)

    def paintGL(self) -> None:
        import moderngl
        from OpenGL import GL

        begin = time.perf_counter()
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.defaultFramebufferObject())
        GL.glClearColor(0, 0, 0, 1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        if self.metrics.sequence < 0:
            return
        if self.uploaded != self.metrics.sequence:
            for texture, frame in zip(self.textures, self.frames.arrays, strict=True):
                texture.write(frame, alignment=1)
                self.uploads += 1
            self.uploaded = self.metrics.sequence
        scale = self.devicePixelRatioF()
        for rect, texture in zip(
            rectangles(self.width(), self.height(), len(self.textures)),
            self.textures,
            strict=True,
        ):
            self.ctx.viewport = (
                round(rect.x() * scale),
                round((self.height() - rect.bottom()) * scale),
                round(rect.width() * scale),
                round(rect.height() * scale),
            )
            texture.use(0)
            self.vao.render(mode=moderngl.TRIANGLE_STRIP)
        self.metrics.painted = self.metrics.sequence, self.metrics.generated
        self.paints.append((time.perf_counter() - begin) * 1000)

    def release(self) -> None:
        if self.resources:
            self.makeCurrent()
            while self.resources:
                self.resources.pop().release()
            self.doneCurrent()


def verify_owned_frames() -> None:
    for channels in (1, 3):
        frames = OwnedFrames(2, 128, channels)
        source = [np.full((128, 128, channels), 201, np.uint8) for _ in range(2)]
        addresses = [a.ctypes.data for a in frames.arrays]
        frames.accept(source)
        source[0].fill(0)
        assert frames.images[0].pixelColor(10, 10).red() == 201
        frames.accept(source)
        assert frames.images[0].pixelColor(10, 10).red() == 0
        assert addresses == [a.ctypes.data for a in frames.arrays]
    rects = rectangles(1128, 398, 3)
    assert len(rects) == 3 and rects[-1].right() <= 1128
