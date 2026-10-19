"""Asynchronous PBO readback for review-video composites."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Any, cast

from cephvr.visual_stimulus.config.models.artifact_models import (
    ReviewEncoding,
    ReviewLayout,
)
from cephvr.visual_stimulus.rendering.types import RenderedOutput

_VERTEX = """#version 430
in vec2 in_position;
in vec2 in_uv;
out vec2 uv;
void main() { uv = in_uv; gl_Position = vec4(in_position, 0.0, 1.0); }
"""
_FRAGMENT = """#version 430
in vec2 uv;
out vec4 color;
uniform sampler2D source_tex;
uniform vec4 source_rect;
uniform int rotate_clockwise;
uniform bvec2 mirror_axes;
void main() {
    vec2 half_pixel = 0.5 / vec2(textureSize(source_tex, 0));
    vec2 sample_uv = uv;
    if (rotate_clockwise == 90) sample_uv = vec2(1.0 - uv.y, uv.x);
    else if (rotate_clockwise == 180) sample_uv = 1.0 - uv;
    else if (rotate_clockwise == 270) sample_uv = vec2(uv.y, 1.0 - uv.x);
    if (mirror_axes.x) sample_uv.x = 1.0 - sample_uv.x;
    if (mirror_axes.y) sample_uv.y = 1.0 - sample_uv.y;
    vec2 point = clamp(source_rect.xy + sample_uv * source_rect.zw,
                       source_rect.xy + half_pixel,
                       source_rect.xy + source_rect.zw - half_pixel);
    color = vec4(texture(source_tex, point).rgb, 0.0);
}
"""


@dataclass(slots=True, eq=False)
class _Buffer:
    gl: Any
    pbo: int
    byte_count: int


@dataclass(slots=True, eq=False)
class _Pending:
    buffer: _Buffer
    sync: Any = None
    failed: bool = False


class ReviewCapture:
    """Own capture-only FBOs/PBO fences; polling never waits on the GPU."""

    def __init__(self) -> None:
        self._pending: list[_Pending] = []
        self._available: list[_Buffer] = []
        self._context: Any | None = None
        self._dimensions: tuple[int, int, str] | None = None
        self._shared: list[Any] = []
        self._labels: dict[tuple[str, int], Any] = {}

    def capture(
        self,
        outputs: tuple[RenderedOutput, ...],
        encoding: ReviewEncoding,
    ) -> _Pending:
        if not outputs:
            raise ValueError("review capture requires rendered outputs")
        try:
            from OpenGL import GL
        except ImportError as exc:
            raise RuntimeError(
                "the Visual Stimulus graphics extra must include PyOpenGL for asynchronous PBO capture"
            ) from exc

        context = cast(Any, cast(Any, outputs[0].texture_handle).ctx)
        if context is None:
            raise RuntimeError("review output texture has no owning GL context")
        width, height = encoding.composite_width, encoding.composite_height
        self._ensure_compositor(context, width, height, encoding.native_pixel_format)
        if self._context is not context:
            raise RuntimeError("review capture must use one shared GL context")
        _texture, framebuffer, program, _buffer, array, _flipped, readback = (
            self._shared
        )
        self.compose(outputs, encoding)
        byte_count = width * height * 4
        # The upstream capture reservation bounds pending+CPU-owned frames. Reusing
        # idle buffers first keeps this pool at that admitted concurrency high-water.
        buffer = (
            self._available.pop() if self._available else _Buffer(GL, 0, byte_count)
        )
        pending = _Pending(buffer)
        self._pending.append(pending)
        try:
            if not buffer.pbo:
                buffer.pbo = GL.glGenBuffers(1)
                if not buffer.pbo:
                    raise RuntimeError("review readback buffer allocation failed")
                GL.glBindBuffer(GL.GL_PIXEL_PACK_BUFFER, buffer.pbo)
                GL.glBufferData(
                    GL.GL_PIXEL_PACK_BUFFER, byte_count, None, GL.GL_STREAM_READ
                )
            else:
                GL.glBindBuffer(GL.GL_PIXEL_PACK_BUFFER, buffer.pbo)
            self._orient_for_readback(GL, framebuffer, readback, width, height)
            GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, readback.glo)
            GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0)
            read_type = (
                GL.GL_UNSIGNED_BYTE
                if encoding.native_pixel_format == "rgba8_top_down"
                else GL.GL_UNSIGNED_INT_2_10_10_10_REV
            )
            GL.glReadPixels(
                0, 0, width, height, GL.GL_RGBA, read_type, ctypes.c_void_p(0)
            )
            pending.sync = GL.glFenceSync(GL.GL_SYNC_GPU_COMMANDS_COMPLETE, 0)
            if not pending.sync:
                pending.sync = None
                raise RuntimeError("review readback fence creation failed")
            GL.glFlush()
            return pending
        except BaseException:
            pending.failed = True
            try:
                self.cancel(pending)
            except Exception:
                pass  # Retain exact failed ownership for release retry.
            raise
        finally:
            GL.glBindBuffer(GL.GL_PIXEL_PACK_BUFFER, 0)
            framebuffer.use()

    def compose(self, outputs: tuple[RenderedOutput, ...], layout: ReviewLayout) -> Any:
        """Compose declared crops/rotations; preview and recording supply separate layouts."""
        import moderngl

        if not outputs:
            raise ValueError("review requires rendered outputs")
        context = cast(Any, outputs[0].texture_handle).ctx
        pixel_format = getattr(layout, "native_pixel_format", None) or (
            "rgba8_top_down"
            if max(t.source_code_bits for t in layout.tiles) == 8
            else "r10g10b10a2_le_top_down"
        )
        self._ensure_compositor(
            context, layout.composite_width, layout.composite_height, pixel_format
        )
        texture, framebuffer, program, _buffer, array, _flipped, _readback = (
            self._shared
        )
        by_id = {item.output_id: item for item in outputs}
        framebuffer.use()
        framebuffer.clear(0, 0, 0, 0)
        program["source_tex"].value = 0
        for tile in layout.tiles:
            program["mirror_axes"].value = (
                layout.layout_kind == "preview" and tile.label in {"Left", "Right"},
                layout.layout_kind == "preview" and tile.label == "Bottom",
            )
            program["rotate_clockwise"].value = tile.rotation_clockwise_degrees
            rendered = by_id[tile.output_id]
            cast(Any, rendered.texture_handle).use(0)
            crop = tile.source_rect
            program["source_rect"].value = (
                (0.0, 0.0, 1.0, 1.0)
                if crop is None
                else (
                    crop.x / rendered.width,
                    crop.y / rendered.height,
                    crop.width / rendered.width,
                    crop.height / rendered.height,
                )
            )
            rect = tile.rect
            context.viewport = (rect.x, rect.y, rect.width, rect.height)
            array.render(mode=moderngl.TRIANGLE_STRIP)
            if layout.layout_version == 2 and tile.cell is not None and tile.label:
                from cephvr.visual_stimulus.config.review_layout import LABEL_HEIGHT

                cell = tile.cell
                self._label(context, tile.label, cell.width).use(0)
                program["rotate_clockwise"].value = 0
                program["mirror_axes"].value = (False, False)
                program["source_rect"].value = (0.0, 0.0, 1.0, 1.0)
                context.viewport = (
                    cell.x,
                    cell.y + cell.height - LABEL_HEIGHT,
                    cell.width,
                    LABEL_HEIGHT,
                )
                array.render(mode=moderngl.TRIANGLE_STRIP)
        context.viewport = (0, 0, layout.composite_width, layout.composite_height)
        return texture

    def _label(self, context: Any, label: str, width: int) -> Any:
        from PIL import Image, ImageDraw, ImageFont

        from cephvr.visual_stimulus.config.review_layout import LABEL_HEIGHT

        key = label, width
        if key not in self._labels:
            image = Image.new("RGB", (width, LABEL_HEIGHT))
            draw = ImageDraw.Draw(image)
            font = ImageFont.load_default(size=16)
            draw.text(
                (width / 2, LABEL_HEIGHT / 2),
                label,
                font=font,
                fill="white",
                anchor="mm",
            )
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            self._labels[key] = context.texture(
                image.size, 3, image.tobytes(), alignment=1
            )
        return self._labels[key]

    @staticmethod
    def _orient_for_readback(
        gl: Any, source: Any, target: Any, width: int, height: int
    ) -> None:
        # Flip completed pixels, not texture sampling: even mixed-size/downsampled
        # tiles and black margins retain the original composite's numeric codes.
        scissor = gl.glIsEnabled(gl.GL_SCISSOR_TEST)
        try:
            if scissor:
                gl.glDisable(gl.GL_SCISSOR_TEST)
            gl.glBindFramebuffer(gl.GL_READ_FRAMEBUFFER, source.glo)
            gl.glReadBuffer(gl.GL_COLOR_ATTACHMENT0)
            gl.glBindFramebuffer(gl.GL_DRAW_FRAMEBUFFER, target.glo)
            gl.glDrawBuffer(gl.GL_COLOR_ATTACHMENT0)
            gl.glBlitFramebuffer(
                0,
                0,
                width,
                height,
                0,
                height,
                width,
                0,
                gl.GL_COLOR_BUFFER_BIT,
                gl.GL_NEAREST,
            )
        finally:
            if scissor:
                gl.glEnable(gl.GL_SCISSOR_TEST)

    def _ensure_compositor(
        self, context: Any, width: int, height: int, pixel_format: str
    ) -> None:
        if pixel_format not in {"rgba8_top_down", "r10g10b10a2_le_top_down"}:
            raise ValueError("unsupported review-composite pixel format")
        dimensions = (width, height, pixel_format)
        if self._shared:
            if self._context is not context or self._dimensions != dimensions:
                raise RuntimeError(
                    "review compositor cannot change context or dimensions"
                )
            if len(self._shared) != 7:
                raise RuntimeError("review compositor has unreleased partial resources")
            return
        self._context = context
        self._dimensions = dimensions
        created = self._shared
        try:
            # Match the already selected 8-bit recording representation before
            # readback; float-to-byte glReadPixels stalls the native driver.
            dtype = "f1" if pixel_format == "rgba8_top_down" else "f4"
            texture = context.texture((width, height), 4, dtype=dtype)
            created.append(texture)
            framebuffer = context.framebuffer(color_attachments=(texture,))
            created.append(framebuffer)
            program = context.program(vertex_shader=_VERTEX, fragment_shader=_FRAGMENT)
            created.append(program)
            buffer = context.buffer(struct_quad())
            created.append(buffer)
            array = context.vertex_array(
                program, [(buffer, "2f 2f", "in_position", "in_uv")]
            )
            created.append(array)
            flipped = context.texture((width, height), 4, dtype=dtype)
            created.append(flipped)
            readback = context.framebuffer(color_attachments=(flipped,))
            created.append(readback)
        except BaseException:
            # Keep partially created resources registered if deletion itself fails.
            try:
                self.release()
            except Exception:
                pass
            raise

    def _require_pending(self, pending: object) -> _Pending:
        if not isinstance(pending, _Pending) or pending not in self._pending:
            raise TypeError("invalid pending review capture")
        return pending

    def poll(self, pending: object) -> bytearray | None:
        pending = self._require_pending(pending)
        if pending.failed:
            raise RuntimeError("review readback failed; cleanup is required")
        buffer = pending.buffer
        gl = buffer.gl
        try:
            try:
                result = gl.glClientWaitSync(pending.sync, 0, 0)
                if result not in (gl.GL_ALREADY_SIGNALED, gl.GL_CONDITION_SATISFIED):
                    if result == gl.GL_WAIT_FAILED:
                        raise RuntimeError("review-composite readback fence failed")
                    return None
                gl.glBindBuffer(gl.GL_PIXEL_PACK_BUFFER, buffer.pbo)
                pointer = gl.glMapBufferRange(
                    gl.GL_PIXEL_PACK_BUFFER, 0, buffer.byte_count, gl.GL_MAP_READ_BIT
                )
                address = ctypes.cast(pointer, ctypes.c_void_p).value
                if address is None:
                    raise RuntimeError("review-composite readback mapping failed")
                try:
                    pixels = bytearray(
                        (ctypes.c_ubyte * buffer.byte_count).from_address(address)
                    )
                finally:
                    unmapped = gl.glUnmapBuffer(gl.GL_PIXEL_PACK_BUFFER)
                if not unmapped:
                    raise RuntimeError(
                        "review-composite readback mapping was corrupted"
                    )
                gl.glDeleteSync(pending.sync)
                pending.sync = None
            finally:
                gl.glBindBuffer(gl.GL_PIXEL_PACK_BUFFER, 0)
        except BaseException:
            pending.failed = True
            raise
        # Only retire ownership after every fallible GL restoration succeeds.
        self._pending.remove(pending)
        self._available.append(buffer)
        return pixels

    def cancel(self, pending: object) -> bool:
        """Discard pending storage, never recycle a potentially unfinished transfer."""
        pending = self._require_pending(pending)
        pending.failed = True
        if pending.sync is not None:
            pending.buffer.gl.glDeleteSync(pending.sync)
            pending.sync = None
        self._delete_buffer(pending.buffer)
        self._pending.remove(pending)
        return True

    @staticmethod
    def _delete_buffer(buffer: _Buffer) -> None:
        if buffer.pbo:
            buffer.gl.glDeleteBuffers(1, [buffer.pbo])
            buffer.pbo = 0

    def release(self) -> None:
        for pending in tuple(self._pending):
            self.cancel(pending)
        while self._available:
            self._delete_buffer(self._available[-1])
            self._available.pop()
        for key, label in tuple(self._labels.items()):
            label.release()
            del self._labels[key]
        while self._shared:
            self._shared[-1].release()
            self._shared.pop()
        self._context = None
        self._dimensions = None


def struct_quad() -> bytes:
    import struct

    return struct.pack("16f", -1, -1, 0, 0, 1, -1, 1, 0, -1, 1, 0, 1, 1, 1, 1, 1)
