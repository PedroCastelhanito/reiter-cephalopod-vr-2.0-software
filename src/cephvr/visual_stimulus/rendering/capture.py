"""Asynchronous PBO readback for review-video composites."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Any, cast

from cephvr.visual_stimulus.config.models.artifact_models import ReviewEncoding
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
void main() { color = vec4(texture(source_tex, uv).rgb, 0.0); }
"""


@dataclass(slots=True)
class _Pending:
    gl: Any
    pbo: int
    sync: Any
    byte_count: int


class ReviewCapture:
    """Own capture-only FBOs/PBO fences; polling never waits on the GPU."""

    def __init__(self) -> None:
        self._pending: list[_Pending] = []
        self._context: Any | None = None
        self._dimensions: tuple[int, int] | None = None
        self._shared: tuple[Any, ...] = ()

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
        import moderngl

        context = cast(Any, cast(Any, outputs[0].texture_handle).ctx)
        if context is None:
            raise RuntimeError("review output texture has no owning GL context")
        width, height = encoding.composite_width, encoding.composite_height
        self._ensure_compositor(context, width, height)
        if self._context is not context:
            raise RuntimeError("review capture must use one shared GL context")
        _texture, framebuffer, program, _buffer, array = self._shared
        by_id = {item.output_id: item for item in outputs}
        framebuffer.use()
        cast(Any, context).viewport = (0, 0, width, height)
        framebuffer.clear(0, 0, 0, 0)
        program["source_tex"].value = 0
        for tile in encoding.tiles:
            rendered = by_id[tile.output_id]
            cast(Any, rendered.texture_handle).use(0)
            rect = tile.rect
            cast(Any, context).viewport = (rect.x, rect.y, rect.width, rect.height)
            array.render(mode=moderngl.TRIANGLE_STRIP)
        cast(Any, context).viewport = (0, 0, width, height)
        byte_count = width * height * 4
        pbo = 0
        sync = None
        try:
            pbo = GL.glGenBuffers(1)
            GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, framebuffer.glo)
            GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0)
            GL.glBindBuffer(GL.GL_PIXEL_PACK_BUFFER, pbo)
            GL.glBufferData(
                GL.GL_PIXEL_PACK_BUFFER, byte_count, None, GL.GL_STREAM_READ
            )
            read_type = (
                GL.GL_UNSIGNED_BYTE
                if encoding.native_pixel_format == "rgba8_bottom_up"
                else GL.GL_UNSIGNED_INT_2_10_10_10_REV
            )
            GL.glReadPixels(
                0, 0, width, height, GL.GL_RGBA, read_type, ctypes.c_void_p(0)
            )
            sync = GL.glFenceSync(GL.GL_SYNC_GPU_COMMANDS_COMPLETE, 0)
            GL.glFlush()
            pending = _Pending(GL, pbo, sync, byte_count)
            self._pending.append(pending)
            return pending
        except BaseException:
            GL.glBindBuffer(GL.GL_PIXEL_PACK_BUFFER, 0)
            if sync is not None:
                GL.glDeleteSync(sync)
            if pbo:
                GL.glDeleteBuffers(1, [pbo])
            raise

    def _ensure_compositor(self, context: Any, width: int, height: int) -> None:
        if self._shared:
            if self._context is not context or self._dimensions != (width, height):
                raise RuntimeError(
                    "review compositor cannot change context or dimensions"
                )
            return
        created: list[Any] = []
        try:
            texture = context.texture((width, height), 4, dtype="f4")
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
        except BaseException:
            for resource in reversed(created):
                resource.release()
            raise
        self._context = context
        self._dimensions = (width, height)
        self._shared = tuple(created)

    def poll(self, pending: object) -> bytes | None:
        if not isinstance(pending, _Pending) or pending not in self._pending:
            raise TypeError("invalid pending review capture")
        gl = pending.gl
        result = gl.glClientWaitSync(pending.sync, 0, 0)
        if result not in (gl.GL_ALREADY_SIGNALED, gl.GL_CONDITION_SATISFIED):
            if result == gl.GL_WAIT_FAILED:
                raise RuntimeError("review-composite readback fence failed")
            return None
        gl.glBindBuffer(gl.GL_PIXEL_PACK_BUFFER, pending.pbo)
        pixels = gl.glGetBufferSubData(gl.GL_PIXEL_PACK_BUFFER, 0, pending.byte_count)
        gl.glBindBuffer(gl.GL_PIXEL_PACK_BUFFER, 0)
        gl.glDeleteSync(pending.sync)
        gl.glDeleteBuffers(1, [pending.pbo])
        self._pending.remove(pending)
        return bytes(pixels)

    def cancel(self, pending: object) -> bool:
        """Delete GL-owned capture objects on the owner thread.

        OpenGL defers destruction of objects still referenced by queued commands;
        deleting the names here is therefore a bounded cancellation operation.
        Keep the owner registered if any deletion raises so shutdown can retry.
        """
        if not isinstance(pending, _Pending) or pending not in self._pending:
            raise TypeError("invalid pending review capture")
        pending.gl.glDeleteSync(pending.sync)
        pending.gl.glDeleteBuffers(1, [pending.pbo])
        self._pending.remove(pending)
        return True

    def release(self) -> None:
        for pending in tuple(self._pending):
            gl = pending.gl
            gl.glDeleteSync(pending.sync)
            gl.glDeleteBuffers(1, [pending.pbo])
        self._pending.clear()
        for resource in reversed(self._shared):
            resource.release()
        self._shared = ()
        self._context = None
        self._dimensions = None


def struct_quad() -> bytes:
    import struct

    return struct.pack("16f", -1, -1, 0, 0, 1, -1, 1, 0, -1, 1, 0, 1, 1, 1, 1, 1)
