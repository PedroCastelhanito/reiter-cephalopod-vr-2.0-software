"""Prepare exact Fold samples on the GL owner, before calibration/compositing."""

import hashlib
import struct
from collections.abc import Callable, Mapping
from typing import Any

from cephvr.visual_stimulus.resources.image_source import ImageSource, PixelBuffer

from .evidence import clip_vertex_components
from .shaders import _LAYER_FRAGMENT, _LAYER_VERTEX

_BAKE_FRAGMENT = _LAYER_FRAGMENT.replace(
    "mark_alpha(sample_value.a, sample_value.rgb);", "color = sample_value; return;", 1
)
# Persistent bundle keys bind the exact bake shaders (V04).
BAKE_ALGORITHM = (
    "fold-bake-v1:"
    + hashlib.sha256((_LAYER_VERTEX + _BAKE_FRAGMENT).encode()).hexdigest()
)


class FoldBaker:
    def __init__(self, outputs: Mapping[str, Any]) -> None:
        self.outputs = outputs
        self.owned: list[tuple[Any, Any]] = []
        self.output: Any = None
        self.program: Any = None
        self.vao: Any = None
        self.texture: Any = None
        self.target: Any = None
        self.fbo: Any = None

    def device_identity(self) -> dict[str, str]:
        """GPU name and driver of the baking context, for bundle keys."""
        info = next(iter(self.outputs.values())).context.info
        return {
            name: str(info.get(name, ""))
            for name in ("GL_VENDOR", "GL_RENDERER", "GL_VERSION")
        }

    def close(self) -> None:
        while self.owned:
            output, resource = self.owned[-1]
            output.activate()
            resource.release()
            self.owned.pop()
        self.output = self.program = self.vao = None
        self.texture = self.target = self.fbo = None

    def _own(self, resource: Any) -> Any:
        self.owned.append((self.output, resource))
        return resource

    def _release(self, resource: Any) -> None:
        resource.release()
        self.owned.remove((self.output, resource))

    def bake(
        self, source: ImageSource, pixels: PixelBuffer, check: Callable[[], None]
    ) -> bytearray:
        """Reuse one source texture and framebuffer until the batch owner closes."""
        import moderngl

        try:
            check()
            if self.output is None:
                self.output = self.outputs[source.output_crops[0].output_id]
            self.output.activate()
            ctx = self.output.context
            if self.program is None:
                self.program = self._own(
                    ctx.program(
                        vertex_shader=_LAYER_VERTEX, fragment_shader=_BAKE_FRAGMENT
                    )
                )
                vbo = self._own(ctx.buffer(struct.pack("8f", 0, 0, 1, 0, 0, 1, 1, 1)))
                self.vao = self._own(
                    ctx.vertex_array(self.program, [(vbo, "2f", "in_uv")])
                )
                flags = self._own(ctx.buffer(bytes(16)))
                flags.bind_to_storage_buffer(3)
                self.program["mode"].value = 8
                self.program["image_tex"].value = 0
            size = (source.width, source.height)
            if self.texture is not None and self.texture.size != size:
                self._release(self.texture)
                self.texture = None
            if self.texture is None:
                self.texture = self._own(ctx.texture(size, 4, dtype="f4"))
                self.texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
                self.texture.repeat_x = self.texture.repeat_y = False
            self.texture.write(pixels)
            target_size = tuple(
                max(c.target[i] for c in source.output_crops) for i in (0, 1)
            )
            if self.target is not None:
                target_size = tuple(
                    max(a, b)
                    for a, b in zip(target_size, self.target.size, strict=True)
                )
                if target_size != self.target.size:
                    self._release(self.fbo)
                    self._release(self.target)
                    self.fbo = self.target = None
            if self.target is None:
                self.target = self._own(ctx.texture(target_size, 4, dtype="f4"))
                self.fbo = self._own(ctx.framebuffer([self.target]))
            ctx.scissor = None
            ctx.disable(moderngl.BLEND | moderngl.DEPTH_TEST | moderngl.CULL_FACE)
            self.texture.use(0)
            self.fbo.use()
            result = bytearray(source.gpu_bytes)
            view = memoryview(result)
            for crop in source.output_crops:
                check()
                self.program["clip_vertices"].write(
                    struct.pack("8f", *clip_vertex_components(crop.corners))
                )
                self.program["image_fold_map"].write(struct.pack("6f", *crop.fold))
                ctx.viewport = (0, 0, *crop.target)
                self.fbo.clear()
                self.vao.render(moderngl.TRIANGLE_STRIP)
                count = crop.width * crop.height * 16
                self.fbo.read_into(
                    view[crop.offset : crop.offset + count],
                    viewport=(crop.x, crop.y, crop.width, crop.height),
                    components=4,
                    dtype="f4",
                    alignment=1,
                )
            check()
            return result
        except BaseException:
            self.close()
            raise
