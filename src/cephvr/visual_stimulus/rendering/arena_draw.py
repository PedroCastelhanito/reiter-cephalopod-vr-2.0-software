"""Per-output GLB arena draw resources and calibrated physical projection."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.rendering.arena import (
    arena_model_matrix,
    off_axis_view_projection,
)
from cephvr.visual_stimulus.rendering.arena_gpu import ArenaGPUSet
from cephvr.visual_stimulus.rendering.shaders import _ARENA_FRAGMENT, _ARENA_VERTEX
from cephvr.visual_stimulus.rendering.types import InstanceSnapshot


class ArenaOutputDrawer:
    """Own arena programs/VAOs for one current GL context."""

    def __init__(
        self,
        context: Any,
        output_id: str,
        gpu_resources: dict[str, Any],
        *,
        retain: Callable[[Any], Any],
    ) -> None:
        self.program: Any | None = None
        self.arrays: dict[tuple[str, int], Any] = {}
        retain(self)
        self.program = context.program(
            vertex_shader=_ARENA_VERTEX, fragment_shader=_ARENA_FRAGMENT
        )
        for resource_id, gpu_set in gpu_resources.items():
            if not isinstance(gpu_set, ArenaGPUSet):
                continue
            output = gpu_set.outputs.get(output_id)
            if output is None:
                raise ValueError(
                    f"arena {resource_id} has no buffers for output {output_id}"
                )
            for index, primitive in enumerate(output.primitives):
                key = (resource_id, index)
                self.arrays[key] = None
                self.arrays[key] = context.vertex_array(
                    self.program,
                    [
                        (
                            primitive.vertex_buffer,
                            "3f 2f 4f",
                            "in_position",
                            "in_uv",
                            "in_color",
                        )
                    ],
                    primitive.index_buffer,
                    index_element_size=4,
                )

    def draw(
        self,
        *,
        context: Any,
        moderngl: Any,
        target: Any,
        artifact: PreparedTrial,
        output_id: str,
        surface_id: str,
        snapshot: InstanceSnapshot,
        gpu_resources: dict[str, Any],
    ) -> None:
        settings = snapshot.settings
        if self.program is None:
            raise RuntimeError("arena output drawer has been released")
        if settings is None or settings.kind != "arena":
            raise RuntimeError("arena draw requires prepared arena settings")
        key = f"{artifact.identity.resource_generation}:{settings.asset_id}"
        gpu_set = gpu_resources.get(key)
        if not isinstance(gpu_set, ArenaGPUSet):
            raise RuntimeError(
                f"prepared arena GPU resources {settings.asset_id} are unavailable"
            )
        output_buffers = gpu_set.outputs.get(output_id)
        if output_buffers is None:
            raise RuntimeError(f"prepared arena has no output buffers for {output_id}")
        surface = next(
            (
                item
                for item in artifact.display.geometry.surfaces
                if item.surface_id == surface_id
            ),
            None,
        )
        if surface is None:
            raise RuntimeError(f"physical surface {surface_id} is not prepared")
        self.program["model"].write(
            _matrix_bytes(arena_model_matrix(settings, dict(snapshot.state)))
        )
        self.program["view_projection"].write(
            _matrix_bytes(off_axis_view_projection(artifact.display, surface))
        )
        self._draw_primitives(
            context=context,
            moderngl=moderngl,
            gpu_set=gpu_set,
            output_buffers=output_buffers,
            resource_id=key,
        )

    def draw_calibration(
        self,
        *,
        context: Any,
        moderngl: Any,
        display: object,
        output_id: str,
        surface_id: str,
        resource_id: str,
        gpu_resources: dict[str, Any],
    ) -> None:
        """Draw a static protected arena without constructing trial artifacts."""
        from types import SimpleNamespace

        from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile

        if self.program is None or not isinstance(display, DisplayProfile):
            raise RuntimeError("calibration display or arena program is unavailable")
        gpu_set = gpu_resources.get(resource_id)
        if not isinstance(gpu_set, ArenaGPUSet):
            raise RuntimeError(
                "protected calibration arena GPU resources are unavailable"
            )
        output_buffers = gpu_set.outputs.get(output_id)
        if output_buffers is None:
            raise RuntimeError(f"calibration arena has no buffers for {output_id}")
        surface = next(
            (
                item
                for item in display.geometry.surfaces
                if item.surface_id == surface_id
            ),
            None,
        )
        if surface is None:
            raise RuntimeError(f"physical surface {surface_id} is unavailable")
        identity = (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        pose = SimpleNamespace(
            asset_to_world=identity,
            fixed_height_mm=0.0,
            fixed_pitch_deg=0.0,
            fixed_roll_deg=0.0,
        )
        self.program["model"].write(
            _matrix_bytes(arena_model_matrix(pose, {"x": 0.0, "y": 0.0, "yaw": 0.0}))
        )
        self.program["view_projection"].write(
            _matrix_bytes(off_axis_view_projection(display, surface))
        )
        self._draw_primitives(
            context=context,
            moderngl=moderngl,
            gpu_set=gpu_set,
            output_buffers=output_buffers,
            resource_id=resource_id,
        )

    def _draw_primitives(
        self,
        *,
        context: Any,
        moderngl: Any,
        gpu_set: ArenaGPUSet,
        output_buffers: Any,
        resource_id: str,
    ) -> None:
        if self.program is None:
            raise RuntimeError("arena output drawer has been released")
        self.program["base_color_tex"].value = 0
        context.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        context.depth_func = "<="
        try:
            for index, primitive in enumerate(output_buffers.primitives):
                material = (
                    gpu_set.scene.materials[primitive.material_index]
                    if primitive.material_index is not None
                    else None
                )
                self.program["has_base_color_tex"].value = int(
                    material is not None and material.texture_index is not None
                )
                self.program["base_color_factor"].value = (
                    material.base_color_factor
                    if material is not None
                    else (1.0, 1.0, 1.0, 1.0)
                )
                self.program["alpha_mask"].value = int(
                    material is not None and material.alpha_mode == "MASK"
                )
                self.program["alpha_cutoff"].value = (
                    material.alpha_cutoff if material else 0.5
                )
                if material is not None and material.texture_index is not None:
                    variants = output_buffers.textures[material.texture_index]
                    texture = (
                        variants.premultiplied
                        if material.alpha_mode == "MASK"
                        else variants.opaque
                    )
                    if texture is None:
                        raise RuntimeError(
                            "prepared arena material texture is unavailable"
                        )
                    texture.use(0)
                if material is not None and material.double_sided:
                    context.disable(moderngl.CULL_FACE)
                else:
                    context.enable(moderngl.CULL_FACE)
                self.arrays[(resource_id, index)].render(mode=moderngl.TRIANGLES)
        finally:
            context.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)

    def release(self) -> None:
        failures = []
        for key, array in reversed(tuple(self.arrays.items())):
            if array is None:
                del self.arrays[key]
                continue
            try:
                array.release()
                del self.arrays[key]
            except Exception as exc:
                failures.append(str(exc))
        if not self.arrays and self.program is not None:
            try:
                self.program.release()
                self.program = None
            except Exception as exc:
                failures.append(str(exc))
        if failures:
            raise RuntimeError(
                "arena output drawer remains owned: " + "; ".join(failures)
            )


def _matrix_bytes(matrix: Any) -> bytes:
    import struct

    return struct.pack(
        "16f",
        *(matrix[row][column] for column in range(4) for row in range(4)),
    )
