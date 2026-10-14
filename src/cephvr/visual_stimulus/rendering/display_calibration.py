"""GL-owner resources and V15 presentation for sessionless arena calibration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.rendering.arena_gpu import ArenaGPUSet, upload_arena
from cephvr.visual_stimulus.rendering.output_masks import clear_regions
from cephvr.visual_stimulus.rendering.reference_bars import draw_reference_bars
from cephvr.visual_stimulus.rendering.scene_resources import (
    PreparedCalibrationOutput,
    SceneOutputBuilder,
)
from cephvr.visual_stimulus.resources.display_calibration import (
    PreparedDisplayCalibration,
)


def _smallest_triangle_area(
    mesh: tuple[tuple[float, float, float, float], ...],
    rows: int,
    columns: int,
    sign: int,
) -> float:
    """Smallest output triangle area in the profile's orientation (negative if folded)."""
    smallest = float("inf")
    for row in range(rows - 1):
        for column in range(columns - 1):
            a = mesh[row * columns + column]
            b = mesh[row * columns + column + 1]
            c = mesh[(row + 1) * columns + column]
            d = mesh[(row + 1) * columns + column + 1]
            for first, second, third in ((a, b, d), (a, d, c)):
                area = (second[2] - first[2]) * (third[3] - first[3]) - (
                    second[3] - first[3]
                ) * (third[2] - first[2])
                smallest = min(smallest, sign * area)
    return smallest


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

    def update(self, adjustments: dict[str, tuple[tuple[float, float], ...]]) -> None:
        """Validate all quadrilaterals before writing the already-owned GL buffers."""
        import struct

        from cephvr.visual_stimulus.config.calibration_adjustments import (
            LIVE_ADJUSTABLE_VIEWS,
            CalibrationAdjustmentRejected,
            corner_cross_products,
            projective_mesh,
            validated_adjustments,
        )

        if (
            self.display is None
            or self.prepared is None
            or self.display.calibration_view not in LIVE_ADJUSTABLE_VIEWS
        ):
            raise CalibrationAdjustmentRejected(
                "Live adjustment requires an active frame/grid or seam presentation"
            )
        adjustments = validated_adjustments(
            (key, tuple(coordinate for point in points for coordinate in point))
            for key, points in adjustments.items()
        )
        mappings = {item.mapping_id: item for item in self.display.active_mappings}
        writes = []
        for mapping_id, points in adjustments.items():
            if mapping_id not in mappings:
                raise CalibrationAdjustmentRejected(
                    "Live adjustment targets an unknown calibration mapping"
                )
            mapping = mappings[mapping_id]
            profile = self.prepared.display_calibration.content[mapping_id]
            if (
                not isinstance(profile, GeometricProfile)
                or not profile.calibration_id.startswith("diagnostic_")
                or profile.mask is not None
                or profile.weight is not None
            ):
                raise CalibrationAdjustmentRejected(
                    "Live adjustment requires a GUI diagnostic mapping"
                )
            rows, columns = profile.rows, profile.columns
            original = tuple(
                profile.vertices[index].xy
                for index in (0, columns - 1, (rows - 1) * columns, rows * columns - 1)
            )
            if (
                corner_cross_products(points)[0] * corner_cross_products(original)[0]
                <= 0
            ):
                raise CalibrationAdjustmentRejected(
                    "Live adjustment cannot change axis inversion"
                )
            mesh = projective_mesh(points, rows, columns)
            sign = 1 if corner_cross_products(points)[0] > 0 else -1
            if _smallest_triangle_area(mesh, rows, columns, sign) <= (
                profile.triangle_area_tolerance
            ):
                raise CalibrationAdjustmentRejected(
                    "Live adjustment violates the protected mesh area tolerance"
                )
            frame = self.frames[mapping.output_id]
            coordinates: list[float] = []
            for source, (_u, _v, x, y) in zip(profile.vertices, mesh, strict=True):
                coordinates.extend(
                    (
                        source.uv[0],
                        source.uv[1],
                        2
                        * (mapping.viewport.x + x * mapping.viewport.width)
                        / frame.width
                        - 1,
                        2
                        * (mapping.viewport.y + y * mapping.viewport.height)
                        / frame.height
                        - 1,
                    )
                )
            data = struct.pack(f"{len(coordinates)}f", *coordinates)
            encoded = struct.unpack(f"{len(coordinates)}f", data)
            last = len(profile.vertices) - 1
            if (
                encoded[2] == encoded[4 * (columns - 1) + 2]
                or encoded[3] == encoded[4 * last + 3]
            ):
                raise CalibrationAdjustmentRejected(
                    "Live adjustment collapses at GPU vertex precision"
                )
            writes.append((frame, frame.warp_vertex_buffers[mapping_id], data))
        for frame, buffer, data in writes:
            frame.activate()
            buffer.write(data)

    def _render(
        self, display: DisplayProfile, prepared: PreparedDisplayCalibration
    ) -> None:
        output_specs = {output.output_id: output for output in display.active_outputs}
        for output_id, frame in self.frames.items():
            frame.activate()
            context = frame.context
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
                    guide=(
                        None
                        if bars is None or bars.guide_width_px is None
                        else (bars.guide_width_px, bars.guide_height_px or 0)
                    ),
                )
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
