"""GL-owner resources and V15 presentation for sessionless arena calibration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.rendering.arena_gpu import ArenaGPUSet, upload_arena
from cephvr.visual_stimulus.rendering.reference_bars import draw_reference_bars
from cephvr.visual_stimulus.rendering.scene_resources import (
    PreparedCalibrationOutput,
    SceneOutputBuilder,
)
from cephvr.visual_stimulus.resources.display_calibration import (
    PreparedDisplayCalibration,
)


class DisplayCalibrationRenderer:
    """Own temporary calibration GL state without constructing an experiment trial."""

    _RESOURCE_KEY = "display-calibration:arena"

    def __init__(
        self,
        outputs: Mapping[str, Any],
        moderngl: Any,
        announce: Callable[[str, str | None], None],
        upload_texture: Callable[..., Any],
    ) -> None:
        self.outputs = outputs
        self.moderngl = moderngl
        self.announce = announce
        self.upload_texture = upload_texture
        self.builder = SceneOutputBuilder()
        self.gpu_resources: dict[str, Any] = {}
        self.frames: dict[str, PreparedCalibrationOutput] = {}
        self.display: DisplayProfile | None = None
        self.prepared: PreparedDisplayCalibration | None = None
        self._arena_gpu: ArenaGPUSet | None = None

    def present(
        self, display: DisplayProfile, prepared: PreparedDisplayCalibration
    ) -> None:
        if prepared.display != display:
            raise ValueError("calibration profile differs from its prepared input")
        if self.display is not None and (
            self.display != display or self.prepared is not prepared
        ):
            raise RuntimeError(
                "another display calibration still owns renderer resources"
            )
        if self.display is None:
            self._prepare(display, prepared)
        assert self.prepared is prepared
        self._render(display, prepared)

    def _prepare(
        self, display: DisplayProfile, prepared: PreparedDisplayCalibration
    ) -> None:
        self.announce("visual_stimulus:gpu:" + self._RESOURCE_KEY, None)
        self.display = display
        self.prepared = prepared
        self.gpu_resources[self._RESOURCE_KEY] = None

        def retain(arena: ArenaGPUSet) -> None:
            self._arena_gpu = arena
            self.gpu_resources[self._RESOURCE_KEY] = arena

        self._arena_gpu = upload_arena(
            prepared.arena.scene,
            self.outputs,
            prepared.arena.textures,
            "display_calibration_arena",
            self.upload_texture,
            retain=retain,
        )
        self.frames = self.builder.prepare_display_calibration(
            display, prepared.display_calibration, self.outputs, self.gpu_resources
        )

    def _render(
        self, display: DisplayProfile, prepared: PreparedDisplayCalibration
    ) -> None:
        for output_id, frame in self.frames.items():
            frame.activate()
            context = frame.context
            from OpenGL import GL

            frame.diagnostic_flags.write(bytes(16))
            GL.glBindBufferBase(
                GL.GL_SHADER_STORAGE_BUFFER, 3, frame.diagnostic_flags.glo
            )
            for mapping in display.active_mappings:
                if mapping.output_id != output_id:
                    continue
                target = frame.surface_fbos[mapping.mapping_id]
                target.use()
                context.viewport = (
                    0,
                    0,
                    mapping.viewport.width,
                    mapping.viewport.height,
                )
                context.scissor = None
                context.enable(self.moderngl.DEPTH_TEST)
                target.clear(0.0, 0.0, 0.0, 1.0, depth=1.0)
                frame.arena_drawer.draw_calibration(
                    context=context,
                    moderngl=self.moderngl,
                    display=display,
                    output_id=output_id,
                    surface_id=mapping.surface_id,
                    resource_id=self._RESOURCE_KEY,
                    gpu_resources=self.gpu_resources,
                )

            frame.output_fbo.use()
            context.viewport = (0, 0, frame.width, frame.height)
            frame.output_fbo.clear(0.0, 0.0, 0.0, 1.0)
            context.disable(self.moderngl.DEPTH_TEST)
            context.enable(self.moderngl.BLEND)
            context.blend_func = (self.moderngl.ONE, self.moderngl.ONE)
            frame.warp_program["scene_tex"].value = 0
            frame.warp_program["mask_tex"].value = 1
            frame.warp_program["weight_tex"].value = 2
            for mapping in display.active_mappings:
                if mapping.output_id != output_id:
                    continue
                profile = prepared.display_calibration.content[mapping.mapping_id]
                if not isinstance(profile, GeometricProfile):
                    raise RuntimeError("protected geometric profile is unavailable")
                frame.warp_program["has_mask"].value = int(profile.mask is not None)
                frame.warp_program["has_weight"].value = int(profile.weight is not None)
                frame.surface_textures[mapping.mapping_id].use(0)
                frame.warp_mask_textures[mapping.mapping_id].use(1)
                frame.warp_weight_textures[mapping.mapping_id].use(2)
                frame.warp_arrays[mapping.mapping_id].render(
                    mode=self.moderngl.TRIANGLES
                )

            frame.device_fbo.use()
            context.disable(self.moderngl.BLEND)
            frame.output_program["source_tex"].value = 0
            frame.output_program["lut_tex"].value = 1
            frame.output_program["calibrated"].value = int(
                display.photometric_mode == "calibrated"
            )
            frame.output_program["lut_size"].value = max(2, frame.lut_texture.size[0])
            frame.output_program["marker_active"].value = 0.0
            frame.output_program["marker_rect"].value = (0.0, 0.0, 0.0, 0.0)
            frame.output_program["marker_rgb"].value = (0.0, 0.0, 0.0)
            frame.output_texture.use(0)
            frame.lut_texture.use(1)
            frame.output_quad_array.render(mode=self.moderngl.TRIANGLE_STRIP)
            draw_reference_bars(context, frame.width, frame.height)
            screen = getattr(context, "screen", None)
            if screen is not None:
                context.copy_framebuffer(screen, frame.device_fbo)

    def release(self) -> tuple[str, ...]:
        """Release VAOs/FBOs and arena buffers on each output's owning context."""
        errors = list(self.builder.release_display_calibration())
        self.frames = self.builder.calibration_outputs
        if self._arena_gpu is not None:
            try:
                self._arena_gpu.release()
            except Exception as exc:
                errors.append(f"{self._RESOURCE_KEY}:{exc}")
            else:
                self._arena_gpu = None
                self.gpu_resources.pop(self._RESOURCE_KEY, None)
        if not errors and not self.frames and self._arena_gpu is None:
            self.display = None
            self.prepared = None
        return tuple(errors)
