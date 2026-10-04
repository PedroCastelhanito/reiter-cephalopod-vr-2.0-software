"""Retained GL allocations for prepared output scenes (V15–V18)."""

from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from cephvr.visual_stimulus.config.models.artifact_models import (
    GeometricProfile,
    Grid,
    PreparedTrial,
)
from cephvr.visual_stimulus.config.models.display_profile import PixelRect
from cephvr.visual_stimulus.config.models.photometric_profile import PhotometricProfile
from cephvr.visual_stimulus.config.models.program_model import VideoSettings
from cephvr.visual_stimulus.rendering.arena_draw import ArenaOutputDrawer
from cephvr.visual_stimulus.rendering.diagnostics import DiagnosticRing
from cephvr.visual_stimulus.rendering.shaders import (
    _LAYER_FRAGMENT,
    _LAYER_VERTEX,
    _OUTPUT_FRAGMENT,
    _QUAD_VERTEX,
    _WARP_FRAGMENT,
)
from cephvr.visual_stimulus.rendering.upload import upload_linear_image
from cephvr.visual_stimulus.resources.assets import PreparedResourceBundle
from cephvr.visual_stimulus.resources.video_index import VideoIndex


class SceneOutput(Protocol):
    context: Any
    width: int
    height: int
    bits: int
    activate: Callable[[], None]


@dataclass(slots=True)
class PreparedSceneOutput:
    context: Any
    width: int
    height: int
    bits: int
    activate: Callable[[], None]
    diagnostics: DiagnosticRing
    owned_resources: list[Any]
    surface_textures: dict[str, Any]
    surface_fbos: dict[str, Any]
    surface_depth: dict[str, Any]
    video_textures: dict[tuple[str, str], Any]
    video_frames: dict[tuple[str, str], int]
    output_texture: Any
    output_fbo: Any
    device_texture: Any
    device_fbo: Any
    quad_buffer: Any
    quad_array: Any
    output_quad_array: Any
    layer_program: Any
    warp_program: Any
    output_program: Any
    arena_drawer: ArenaOutputDrawer
    warp_arrays: dict[str, Any]
    warp_mask_textures: dict[str, Any]
    warp_weight_textures: dict[str, Any]
    lut_texture: Any


class SceneOutputBuilder:
    """Prepare per-output shader, warp and video resources with cleanup owners first."""

    def __init__(self) -> None:
        self.partial_allocations: dict[
            tuple[str, str], tuple[Callable[[], None], list[Any]]
        ] = {}

    def prepare_trial(
        self,
        artifact: PreparedTrial,
        resources: PreparedResourceBundle,
        outputs: dict[str, SceneOutput],
        gpu_resources: dict[str, Any],
        output_target: dict[str, PreparedSceneOutput],
    ) -> dict[str, Any]:
        trial_id = artifact.identity.trial_id
        resource_content = resources.prepared_content
        generation = artifact.identity.resource_generation
        scoped_gpu_resources = {
            f"{generation}:{resource.fingerprint.resource_id}": gpu_resources[
                f"{generation}:{resource.fingerprint.resource_id}"
            ]
            for resource in artifact.manifest.resources
            if f"{generation}:{resource.fingerprint.resource_id}" in gpu_resources
        }
        trial_outputs = output_target
        for output_id, output in outputs.items():
            output.activate()
            owned: list[Any] = []
            self.partial_allocations[(trial_id, output_id)] = (output.activate, owned)

            def track(resource: Any, owner: list[Any] = owned) -> Any:
                owner.append(resource)
                return resource

            context = output.context
            width, height = output.width, output.height
            diagnostics = DiagnosticRing(context, track)
            mappings = [
                mapping
                for mapping in artifact.display.active_mappings
                if mapping.output_id == output_id
            ]
            surface_textures: dict[str, Any] = {}
            surface_fbos: dict[str, Any] = {}
            surface_depth: dict[str, Any] = {}
            video_textures: dict[tuple[str, str], Any] = {}
            video_frames: dict[tuple[str, str], int] = {}
            warp_arrays: dict[str, Any] = {}
            warp_mask_textures: dict[str, Any] = {}
            warp_weight_textures: dict[str, Any] = {}
            layer_program = track(
                context.program(
                    vertex_shader=_LAYER_VERTEX, fragment_shader=_LAYER_FRAGMENT
                )
            )
            warp_program = track(
                context.program(
                    vertex_shader=self._warp_vertex(), fragment_shader=_WARP_FRAGMENT
                )
            )
            output_program = track(
                context.program(
                    vertex_shader=_QUAD_VERTEX, fragment_shader=_OUTPUT_FRAGMENT
                )
            )
            arena_drawer = ArenaOutputDrawer(
                context,
                output_id,
                scoped_gpu_resources,
                retain=track,
            )
            quad_buffer = track(context.buffer(self._quad_bytes()))
            quad_array = track(
                context.vertex_array(layer_program, [(quad_buffer, "8x 2f", "in_uv")])
            )
            output_quad_array = track(
                context.vertex_array(
                    output_program, [(quad_buffer, "2f 2f", "in_position", "in_uv")]
                )
            )
            for mapping in mappings:
                viewport = mapping.viewport
                texture = track(
                    context.texture((viewport.width, viewport.height), 4, dtype="f4")
                )
                depth = track(
                    context.depth_renderbuffer((viewport.width, viewport.height))
                )
                framebuffer = track(
                    context.framebuffer(
                        color_attachments=(texture,), depth_attachment=depth
                    )
                )
                surface_textures[mapping.mapping_id] = texture
                surface_fbos[mapping.mapping_id] = framebuffer
                surface_depth[mapping.mapping_id] = depth
                profile = cast(GeometricProfile, resource_content[mapping.mapping_id])
                warp_arrays[mapping.mapping_id] = self._make_warp_array(
                    context, warp_program, profile, viewport, width, height, track
                )
                warp_mask_textures[mapping.mapping_id] = self._make_grid_texture(
                    context, profile.mask, track
                )
                warp_weight_textures[mapping.mapping_id] = self._make_grid_texture(
                    context, profile.weight, track
                )
            final_texture = track(context.texture((width, height), 4, dtype="f4"))
            final_fbo = track(context.framebuffer(color_attachments=(final_texture,)))
            device_texture = track(context.texture((width, height), 4, dtype="f4"))
            device_fbo = track(context.framebuffer(color_attachments=(device_texture,)))
            calibrated = artifact.display.photometric_mode == "calibrated"
            photometric_profile = cast(
                PhotometricProfile | None, resource_content.get(output_id)
            )
            if calibrated and photometric_profile is None:
                raise ValueError(f"calibrated output {output_id} has no prepared LUT")
            lut = (
                self._make_lut_texture(context, photometric_profile, track)
                if photometric_profile is not None
                else track(context.texture((2, 1), 3, bytes(24), dtype="f4"))
            )
            video_instances: set[tuple[str, str]] = set()
            for epoch in artifact.epochs:
                for setting in epoch.settings:
                    if isinstance(setting, VideoSettings):
                        asset_id = setting.asset_id
                        if not isinstance(asset_id, str):
                            raise ValueError(
                                "prepared video asset reference is unresolved"
                            )
                        video_instances.add((setting.instance_id, asset_id))
            for instance_id, asset_id in sorted(video_instances):
                index = resource_content.get(asset_id)
                if not isinstance(index, VideoIndex):
                    raise ValueError(
                        f"video {asset_id} lacks its prepared initial frame"
                    )
                key = (instance_id, asset_id)
                video_textures[key] = upload_linear_image(
                    context, index.initial_pixels, retain=track
                )
                video_frames[key] = index.frames[0].index
            trial_outputs[output_id] = PreparedSceneOutput(
                context,
                width,
                height,
                output.bits,
                output.activate,
                diagnostics,
                owned,
                surface_textures,
                surface_fbos,
                surface_depth,
                video_textures,
                video_frames,
                final_texture,
                final_fbo,
                device_texture,
                device_fbo,
                quad_buffer,
                quad_array,
                output_quad_array,
                layer_program,
                warp_program,
                output_program,
                arena_drawer,
                warp_arrays,
                warp_mask_textures,
                warp_weight_textures,
                lut,
            )
            del self.partial_allocations[(trial_id, output_id)]
        return scoped_gpu_resources

    @staticmethod
    def _warp_vertex() -> str:
        return """#version 430
in vec2 in_source;
in vec2 in_position;
out vec2 uv;
void main() { uv = in_source; gl_Position = vec4(in_position,0.0,1.0); }
"""

    @staticmethod
    def _quad_bytes() -> bytes:
        return struct.pack("16f", -1, -1, 0, 0, 1, -1, 1, 0, -1, 1, 0, 1, 1, 1, 1, 1)

    def _make_warp_array(
        self,
        context: Any,
        program: Any,
        profile: GeometricProfile,
        viewport: PixelRect,
        width: int,
        height: int,
        track: Callable[[Any], Any],
    ) -> Any:
        import numpy as np

        vertices: list[float] = []
        for item in profile.vertices:
            px = viewport.x + item.xy[0] * viewport.width
            py = viewport.y + item.xy[1] * viewport.height
            vertices.extend(
                (item.uv[0], item.uv[1], 2 * px / width - 1, 2 * py / height - 1)
            )
        indices: list[int] = []
        for row in range(profile.rows - 1):
            for column in range(profile.columns - 1):
                a = row * profile.columns + column
                b, c, d = a + 1, a + profile.columns, a + profile.columns + 1
                indices.extend((a, b, d, a, d, c))
        vertex_buffer = track(
            context.buffer(np.asarray(vertices, dtype=np.float32).tobytes())
        )
        index_buffer = track(
            context.buffer(np.asarray(indices, dtype=np.uint32).tobytes())
        )
        return track(
            context.vertex_array(
                program,
                [(vertex_buffer, "2f 2f", "in_source", "in_position")],
                index_buffer,
            )
        )

    @staticmethod
    def _make_lut_texture(
        context: Any, profile: PhotometricProfile, track: Callable[[Any], Any]
    ) -> Any:
        import numpy as np

        values = np.asarray(
            tuple(zip(profile.red, profile.green, profile.blue, strict=True)),
            dtype=np.float32,
        )
        texture = track(
            context.texture((len(values), 1), 3, values.tobytes(), dtype="f4")
        )
        texture.filter = (0x2601, 0x2601)
        texture.repeat_x = False
        return texture

    @staticmethod
    def _make_grid_texture(
        context: Any, grid: Grid | None, track: Callable[[Any], Any]
    ) -> Any:
        import numpy as np

        if grid is None:
            values = np.ones((1, 1), dtype=np.float32)
        else:
            values = np.asarray(grid.values, dtype=np.float32).reshape(
                (grid.rows, grid.columns)
            )
        texture = track(
            context.texture(
                (values.shape[1], values.shape[0]), 1, values.tobytes(), dtype="f4"
            )
        )
        texture.filter = (0x2601, 0x2601)
        texture.repeat_x = False
        texture.repeat_y = False
        return texture
