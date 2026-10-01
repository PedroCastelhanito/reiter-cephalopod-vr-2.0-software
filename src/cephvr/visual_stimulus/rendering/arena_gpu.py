"""GL-owned static mesh buffers and prepared texture bindings for GLB arenas."""

from __future__ import annotations

import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any

from cephvr.visual_stimulus.resources.glb import GLBPrimitive, GLBScene
from cephvr.visual_stimulus.resources.media import ImagePixels


@dataclass(slots=True)
class ArenaPrimitiveBuffers:
    vertex_buffer: Any | None
    index_buffer: Any | None
    index_count: int
    material_index: int | None

    def release(self) -> None:
        if self.index_buffer is not None:
            self.index_buffer.release()
            self.index_buffer = None
        if self.vertex_buffer is not None:
            self.vertex_buffer.release()
            self.vertex_buffer = None


@dataclass(slots=True)
class ArenaOutputBuffers:
    context: Any
    activate: Callable[[], None] | None
    primitives: list[ArenaPrimitiveBuffers]
    textures: dict[int, ArenaMaterialTextures]

    def release(self) -> None:
        if self.activate is not None:
            self.activate()
        for index in range(len(self.primitives) - 1, -1, -1):
            self.primitives[index].release()
            del self.primitives[index]
        for index, texture in reversed(tuple(self.textures.items())):
            texture.release()
            del self.textures[index]


@dataclass(slots=True)
class ArenaMaterialTextures:
    premultiplied: Any | None = None
    opaque: Any | None = None

    def release(self) -> None:
        failures = []
        for attribute in ("opaque", "premultiplied"):
            texture = getattr(self, attribute)
            if texture is None:
                continue
            try:
                texture.release()
                setattr(self, attribute, None)
            except Exception as exc:
                failures.append(str(exc))
        if failures:
            raise RuntimeError(
                "arena material textures remain owned: " + "; ".join(failures)
            )


@dataclass(slots=True)
class ArenaGPUSet:
    scene: GLBScene
    outputs: dict[str, ArenaOutputBuffers]

    def release(self) -> None:
        for key in reversed(tuple(self.outputs)):
            self.outputs[key].release()
            del self.outputs[key]


def upload_arena(
    scene: GLBScene,
    outputs: Mapping[str, Any],
    prepared_content: Mapping[str, object],
    asset_id: str,
    upload_texture: Callable[[str, Any, ImagePixels, bool, Callable[[Any], None]], Any],
    retain: Callable[[ArenaGPUSet], None] | None = None,
) -> ArenaGPUSet:
    """Allocate bounded typed GLB arrays per shared output context."""
    owner = ArenaGPUSet(scene, {})
    if retain is not None:
        retain(owner)
    try:
        for output_id, output in outputs.items():
            context = output.context
            primitives: list[ArenaPrimitiveBuffers] = []
            textures: dict[int, ArenaMaterialTextures] = {}
            output_buffers = ArenaOutputBuffers(
                context, getattr(output, "activate", None), primitives, textures
            )
            owner.outputs[output_id] = output_buffers
            activate = getattr(output, "activate", None)
            if callable(activate):
                activate()
            for index, _texture in enumerate(scene.textures):
                pixels = prepared_content.get(f"{asset_id}:texture:{index}")
                if not isinstance(pixels, ImagePixels):
                    raise ValueError(f"prepared arena texture {index} is missing")
                variants = ArenaMaterialTextures()
                textures[index] = variants

                variants.premultiplied = upload_texture(
                    output_id,
                    context,
                    pixels,
                    False,
                    partial(_retain_texture_variant, variants, "premultiplied"),
                )
                _configure_sampler(variants.premultiplied, _texture)

                variants.opaque = upload_texture(
                    output_id,
                    context,
                    pixels,
                    True,
                    partial(_retain_texture_variant, variants, "opaque"),
                )
                _configure_sampler(variants.opaque, _texture)
            for node in scene.nodes:
                for primitive in node.primitives:
                    values = _interleaved_vertices(node.matrix, primitive)
                    vertex = context.buffer(struct.pack(f"{len(values)}f", *values))
                    primitive_owner = ArenaPrimitiveBuffers(
                        vertex,
                        None,
                        len(primitive.indices),
                        primitive.material_index,
                    )
                    primitives.append(primitive_owner)
                    primitive_owner.index_buffer = context.buffer(
                        struct.pack(f"{len(primitive.indices)}I", *primitive.indices)
                    )
        return owner
    except BaseException:
        # The retained owner remains available to NativePort cleanup, including
        # resources allocated immediately before an exception.
        raise


def _interleaved_vertices(
    node_matrix: tuple[float, ...], primitive: GLBPrimitive
) -> tuple[float, ...]:
    values: list[float] = []
    for index, position in enumerate(primitive.positions):
        x, y, z = position
        world = (
            node_matrix[0] * x
            + node_matrix[4] * y
            + node_matrix[8] * z
            + node_matrix[12],
            node_matrix[1] * x
            + node_matrix[5] * y
            + node_matrix[9] * z
            + node_matrix[13],
            node_matrix[2] * x
            + node_matrix[6] * y
            + node_matrix[10] * z
            + node_matrix[14],
        )
        source_uv = (
            primitive.texcoords[index]
            if primitive.texcoords is not None
            else (0.0, 0.0)
        )
        # Image upload uses bottom-left rows while glTF UV origin is top-left.
        uv = (source_uv[0], 1.0 - source_uv[1])
        color = (
            primitive.colors[index]
            if primitive.colors is not None
            else (1.0, 1.0, 1.0, 1.0)
        )
        rgba = (*color[:3], color[3] if len(color) == 4 else 1.0)
        values.extend((*world, *uv, *rgba))
    return tuple(values)


def _retain_texture_variant(
    owner: ArenaMaterialTextures, variant: str, texture: Any
) -> None:
    if variant == "opaque":
        owner.opaque = texture
    elif variant == "premultiplied":
        owner.premultiplied = texture
    else:
        raise ValueError("unknown arena texture variant")


def _configure_sampler(texture: Any, sampler: Any) -> None:
    """Apply the bounded glTF sampler values directly to the GL texture."""
    try:
        from OpenGL import GL
    except ImportError as exc:
        raise RuntimeError("PyOpenGL is required for prepared arena samplers") from exc
    if sampler.min_filter in (9984, 9985, 9986, 9987):
        texture.build_mipmaps()
    texture.filter = (sampler.min_filter, sampler.mag_filter)
    GL.glBindTexture(GL.GL_TEXTURE_2D, texture.glo)
    try:
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, sampler.wrap_s)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, sampler.wrap_t)
    finally:
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
