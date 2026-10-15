"""GL-owner resources and V15 presentation for sessionless arena calibration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from cephvr.visual_stimulus.config.calibration_placement import (
    PLACEMENT_VIEWS,
    CalibrationPlacement,
)
from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.rendering.arena_gpu import ArenaGPUSet, upload_arena
from cephvr.visual_stimulus.rendering.output_masks import clear_regions
from cephvr.visual_stimulus.rendering.reference_bars import (
    draw_reference_bars,
    draw_valid_frame,
)
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
        self.valid_areas: dict[str, tuple[float, float, float, float]] = {}
        self.placement: CalibrationPlacement | None = None
        self.photodiode_index = 0

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
        if display.calibration_view in PLACEMENT_VIEWS:
            self.placement = CalibrationPlacement.from_display(display)
            self.placement.validate_display(display, allow_empty_pulse=True)
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

    def update(
        self,
        adjustments: dict[str, tuple[tuple[float, float], ...]] | CalibrationPlacement,
    ) -> None:
        """Validate all rectangles before writing the already-owned GL buffers."""
        from cephvr.visual_stimulus.config.calibration_adjustments import (
            CalibrationAdjustmentRejected,
            validated_adjustments,
        )

        if isinstance(adjustments, CalibrationPlacement):
            if (
                self.display is None
                or self.display.calibration_view not in PLACEMENT_VIEWS
            ):
                raise CalibrationAdjustmentRejected(
                    "Placement update requires an active placement preview"
                )
            adjustments.validate_display(self.display)
            self.placement = adjustments
            return

        if (
            self.display is None
            or self.prepared is None
            or self.display.calibration_view != "frame_grid"
        ):
            raise CalibrationAdjustmentRejected(
                "Live adjustment requires an active frame/grid presentation"
            )
        points = validated_adjustments(
            (key, tuple(v for p in value for v in p))
            for key, value in adjustments.items()
        )
        mappings = {m.mapping_id: m for m in self.display.active_mappings}
        pending = {}
        for key, corners in points.items():
            if key not in mappings:
                raise CalibrationAdjustmentRejected(
                    "Live adjustment targets an unknown calibration mapping"
                )
            profile = self.prepared.display_calibration.content[key]
            if (
                not isinstance(profile, GeometricProfile)
                or profile.rows != 2
                or profile.columns != 2
                or not profile.calibration_id.startswith("diagnostic_")
                or profile.mask is not None
                or profile.weight is not None
            ):
                raise CalibrationAdjustmentRejected(
                    "Live adjustment requires a GUI diagnostic affine mapping"
                )
            xs, ys = [p[0] for p in corners], [p[1] for p in corners]
            bounds = min(xs), min(ys), max(xs), max(ys)
            frame = self.frames[mappings[key].output_id]
            if (bounds[2] - bounds[0]) * frame.width < 1 or (
                bounds[3] - bounds[1]
            ) * frame.height < 1:
                raise CalibrationAdjustmentRejected(
                    "Valid area must cover at least one output pixel on each axis"
                )
            pending[key] = bounds
        import struct

        from cephvr.visual_stimulus.config.calibration_adjustments import (
            affine_vertices,
        )

        writes = []
        for key, bounds in pending.items():
            profile = self.prepared.display_calibration.content[key]
            assert isinstance(profile, GeometricProfile)
            a, b, c = profile.vertices[:3]
            sx = (b.xy[0] - a.xy[0]) / (b.uv[0] - a.uv[0])
            sy = (c.xy[1] - a.xy[1]) / (c.uv[1] - a.uv[1])
            vertices = affine_vertices(
                sx, sy, (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
            )
            frame = self.frames[mappings[key].output_id]
            data = struct.pack(
                "16f",
                *(
                    value
                    for v in vertices
                    for value in (*v["uv"], 2 * v["xy"][0] - 1, 2 * v["xy"][1] - 1)
                ),
            )
            encoded = struct.unpack("16f", data)
            if (
                encoded[0] == encoded[4]
                or encoded[1] == encoded[9]
                or encoded[2] == encoded[6]
                or encoded[3] == encoded[11]
            ):
                raise CalibrationAdjustmentRejected(
                    "Valid-area translation collapses at GPU vertex precision"
                )
            writes.append((frame, key, data))
        for frame, key, data in writes:
            self.outputs[mappings[key].output_id].activate()
            frame.warp_vertex_buffers[key].write(data)
        self.valid_areas.update(pending)

    def _render(
        self, display: DisplayProfile, prepared: PreparedDisplayCalibration
    ) -> None:
        output_specs = {output.output_id: output for output in display.active_outputs}
        for output_id, frame in self.frames.items():
            frame.activate()
            context = frame.context
            if display.calibration_view in PLACEMENT_VIEWS:
                from .calibration_placement import draw_placement
                from .photodiode import photodiode_level

                assert self.placement is not None
                context.disable(self.moderngl.BLEND | self.moderngl.DEPTH_TEST)
                draw_placement(
                    context,
                    frame,
                    display.calibration_view,
                    output_id,
                    self.placement,
                    photodiode_level(self.photodiode_index),
                )
                continue
            if display.calibration_view == "reference_bars":
                frame.device_fbo.use()
                context.viewport = (0, 0, frame.width, frame.height)
                context.scissor = None
                context.disable(self.moderngl.BLEND)
                frame.device_fbo.clear(0.0, 0.0, 0.0, 1.0)
                bars = output_specs[output_id].reference_bars
                draw_reference_bars(
                    context,
                    frame.width,
                    frame.height,
                    x_px=None if bars is None else bars.x_length_px,
                    y_px=None if bars is None else bars.y_length_px,
                )
                screen = getattr(context, "screen", None)
                if screen is not None:
                    context.copy_framebuffer(screen, frame.device_fbo)
                continue
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
                frame.warp_program["valid_area"].value = self.valid_areas.get(
                    mapping.mapping_id, profile.valid_area or (0.0, 0.0, 1.0, 1.0)
                )
                frame.warp_program["output_size"].value = (frame.width, frame.height)
                frame.warp_program["has_mask"].value = int(profile.mask is not None)
                frame.warp_program["has_weight"].value = int(profile.weight is not None)
                frame.surface_textures[mapping.mapping_id].use(0)
                frame.warp_mask_textures[mapping.mapping_id].use(1)
                frame.warp_weight_textures[mapping.mapping_id].use(2)
                frame.warp_arrays[mapping.mapping_id].render(
                    mode=self.moderngl.TRIANGLES
                )

            if output_specs[output_id].blackout_zones:
                clear_regions(
                    context,
                    frame.output_fbo.clear,
                    output_specs[output_id].blackout_zones,
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
            for mapping in display.active_mappings:
                if mapping.output_id == output_id:
                    profile = prepared.display_calibration.content[mapping.mapping_id]
                    assert isinstance(profile, GeometricProfile)
                    bounds = self.valid_areas.get(
                        mapping.mapping_id, profile.valid_area
                    )
                    if bounds is not None:
                        draw_valid_frame(context, frame.width, frame.height, bounds)
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
            self.valid_areas.clear()
            self.placement = None
            self.photodiode_index = 0
        return tuple(errors)
