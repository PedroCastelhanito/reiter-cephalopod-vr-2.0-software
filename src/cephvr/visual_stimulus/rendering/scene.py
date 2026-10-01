"""ModernGL linear scene composition and calibrated output mapping shaders."""

from __future__ import annotations

import struct
from collections.abc import Sequence
from typing import Any

from cephvr.visual_stimulus.config.models.artifact_models import (
    GeometricProfile,
    PreparedTrial,
    ReviewEncoding,
)
from cephvr.visual_stimulus.config.models.program_model import Scene
from cephvr.visual_stimulus.rendering.evidence import (
    clip_vertex_components,
    float32_words,
    uniform_values,
)
from cephvr.visual_stimulus.rendering.layer_projection import (
    angular_corners,
    physical_corners,
)
from cephvr.visual_stimulus.rendering.scene_resources import (
    PreparedSceneOutput as _OutputScene,
)
from cephvr.visual_stimulus.rendering.scene_resources import (
    SceneOutputBuilder,
)
from cephvr.visual_stimulus.rendering.types import (
    DiagnosticSnapshot,
    InstanceSnapshot,
    RenderedOutput,
    RenderPassResult,
    UniformSnapshot,
)
from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes
from cephvr.visual_stimulus.resources.assets import PreparedResourceBundle


class ModernGLSceneRenderer:
    """Compose linear surfaces, calibrate each output and expose final textures.

    This provider owns scene shader/program/FBO resources only; GLFW/context ownership
    remains in ModernGLPort. All methods are called on that one GL owner thread.
    """

    def __init__(self) -> None:
        self._artifacts: dict[str, PreparedTrial] = {}
        self._outputs: dict[str, dict[str, _OutputScene]] = {}
        self._active_trial_id: str | None = None
        self._resource_builder = SceneOutputBuilder()
        self._resources: dict[str, dict[str, Any]] = {}
        self._gpu_resources: dict[str, dict[str, Any]] = {}
        self._moderngl: Any | None = None
        self._clipped: set[tuple[str, str]] = set()
        from cephvr.visual_stimulus.rendering.capture import ReviewCapture

        self._review_capture = ReviewCapture()

    def bind_graphics_api(self, moderngl: Any) -> None:
        if self._moderngl is not None and self._moderngl is not moderngl:
            raise RuntimeError("scene renderer cannot change graphics API instances")
        self._moderngl = moderngl

    @property
    def diagnostics_pending(self) -> bool:
        outputs = self._outputs.get(self._active_trial_id or "", {})
        return any(frame.diagnostics.pending for frame in outputs.values())

    def poll_diagnostics(self) -> tuple[DiagnosticSnapshot, ...]:
        completed: list[DiagnosticSnapshot] = []
        outputs = self._outputs.get(self._active_trial_id or "", {})
        for frame in outputs.values():
            frame.activate()
            completed.extend(frame.diagnostics.poll())
        return tuple(completed)

    def prepare_trial(
        self,
        artifact: PreparedTrial,
        resources: PreparedResourceBundle,
        outputs: dict[str, Any],
        gpu_resources: dict[str, Any],
    ) -> None:
        trial_id = artifact.identity.trial_id
        output_scenes: dict[str, _OutputScene] = {}
        self._outputs[trial_id] = output_scenes
        self._artifacts[trial_id] = artifact
        self._resources[trial_id] = resources.prepared_content
        self._gpu_resources[trial_id] = self._resource_builder.prepare_trial(
            artifact, resources, outputs, gpu_resources, output_scenes
        )

    def render_group(
        self,
        scene_envelope: tuple[Scene, bool, int, str, int, int, int],
        state: Sequence[InstanceSnapshot],
        outputs: dict[str, _OutputScene],
        gpu_resources: dict[str, Any],
    ) -> RenderPassResult:
        assert self._moderngl is not None
        (
            scene,
            marker_high,
            marker_index,
            trial_id,
            group_id,
            epoch_index,
            evaluation_host_ns,
        ) = scene_envelope
        self._active_trial_id = trial_id
        artifact = self._artifacts[trial_id]
        trial_outputs = self._outputs[trial_id]
        trial_resources = self._resources[trial_id]
        trial_gpu_resources = self._gpu_resources[trial_id]
        snapshots = {item.instance_id: item for item in state}
        outputs_rendered = []
        uniforms_by_id = {}
        for snapshot in state:
            if snapshot.settings is not None and snapshot.settings.kind == "arena":
                uniforms_by_id.update(uniform_values(artifact, snapshot))
        for output_id, output_context in outputs.items():
            output_context.activate()
            frame = trial_outputs[output_id]
            context = frame.context
            frame.diagnostics.begin(
                group_id, output_id, epoch_index, evaluation_host_ns
            )
            for snapshot in state:
                decoded = snapshot.decoded_frame
                if snapshot.settings is None or snapshot.settings.kind != "video":
                    continue
                if decoded is None or snapshot.media_selection is None:
                    continue
                asset_id = snapshot.settings.asset_id
                if not isinstance(asset_id, str):
                    raise RuntimeError(
                        "prepared video instance has no resolved asset id"
                    )
                video_key = (snapshot.instance_id, asset_id)
                previous = frame.video_frames.get(video_key)
                if previous == snapshot.media_selection.source_frame_index:
                    continue
                frame.video_textures[video_key].write(linear_rgba_bytes(decoded))
                frame.video_frames[video_key] = (
                    snapshot.media_selection.source_frame_index
                )
            # One linear RGBA32F target per projected surface; draw order is the
            # prepared scene order and all four faces share the same instance state.
            for mapping in (
                item
                for item in artifact.display.mappings
                if item.output_id == output_id
            ):
                target = frame.surface_fbos[mapping.mapping_id]
                target.use()
                context.viewport = (0, 0, target.size[0], target.size[1])
                context.enable(self._moderngl.BLEND)
                context.blend_func = (
                    self._moderngl.ONE,
                    self._moderngl.ONE_MINUS_SRC_ALPHA,
                )
                bg = tuple(scene.background_linear_rgb)
                target.clear(bg[0], bg[1], bg[2], 1.0, depth=1.0)
                self._draw_scene_layers(
                    frame,
                    artifact,
                    output_id,
                    mapping,
                    scene,
                    snapshots,
                    trial_gpu_resources,
                    uniforms_by_id,
                )
            frame.output_fbo.use()
            context.viewport = (0, 0, output_context.width, output_context.height)
            frame.output_fbo.clear(0, 0, 0, 1)
            context.disable(self._moderngl.DEPTH_TEST)
            context.enable(self._moderngl.BLEND)
            context.blend_func = (self._moderngl.ONE, self._moderngl.ONE)
            frame.warp_program["scene_tex"].value = 0
            for mapping in (
                item
                for item in artifact.display.mappings
                if item.output_id == output_id
            ):
                texture = frame.surface_textures[mapping.mapping_id]
                texture.use(0)
                profile = trial_resources[mapping.mapping_id]
                self._bind_warp_profile(frame, profile)
                frame.warp_mask_textures[mapping.mapping_id].use(1)
                frame.warp_weight_textures[mapping.mapping_id].use(2)
                frame.warp_arrays[mapping.mapping_id].render(
                    mode=self._moderngl.TRIANGLES
                )
            self._apply_output(
                frame, artifact, output_id, bool(marker_high), marker_index
            )
            frame.diagnostics.end()
            outputs_rendered.append(
                RenderedOutput(
                    output_id,
                    output_context.width,
                    output_context.height,
                    output_context.bits,
                    frame.device_texture,
                )
            )
        media = tuple(
            snapshot.media_selection
            for snapshot in state
            if snapshot.media_selection is not None
        )
        return RenderPassResult(
            tuple(outputs_rendered),
            tuple(uniforms_by_id.values()),
            media,
            (),
        )

    def _draw_scene_layers(
        self,
        frame: _OutputScene,
        artifact: PreparedTrial,
        output_id: str,
        mapping: Any,
        scene: Scene,
        snapshots: dict[str, InstanceSnapshot],
        gpu_resources: dict[str, Any],
        uniforms_by_id: dict[str, UniformSnapshot],
    ) -> None:
        """Draw the optional arena first, then the prepared bottom-to-top layers."""
        arena_id = scene.arena_instance_id
        if arena_id is not None:
            arena = snapshots.get(arena_id)
            if (
                arena is None
                or arena.settings is None
                or arena.settings.kind != "arena"
            ):
                raise RuntimeError(f"prepared arena instance {arena_id} is missing")
            uniforms_by_id.update(uniform_values(artifact, arena))
            if arena.active:
                self._draw_arena(
                    frame,
                    artifact,
                    output_id,
                    mapping.mapping_id,
                    mapping.surface_id,
                    arena,
                    gpu_resources,
                )

        for instance_id in scene.layer_instance_ids:
            snapshot = snapshots.get(instance_id)
            if snapshot is None or snapshot.settings is None or not snapshot.active:
                continue
            settings = snapshot.settings
            if settings.kind == "arena":
                raise RuntimeError("prepared arena cannot appear in 2D scene layers")
            surface_map = None
            if settings.space.kind == "physical_surface":
                surface_map = next(
                    (
                        item
                        for item in settings.space.mappings
                        if item.surface_id == mapping.surface_id
                    ),
                    None,
                )
                if surface_map is None:
                    continue
            elif mapping.surface_id not in settings.space.surfaces:
                continue
            if surface_map is not None:
                normalized = physical_corners(
                    artifact, snapshot, mapping.surface_id, surface_map
                )
                uniforms_by_id.update(uniform_values(artifact, snapshot))
            else:
                normalized = angular_corners(artifact, snapshot, mapping.surface_id)
                uniforms_by_id.update(uniform_values(artifact, snapshot))
            clip_uniform = self._draw_layer(
                frame,
                artifact,
                gpu_resources,
                output_id,
                mapping.mapping_id,
                snapshot,
                normalized,
            )
            uniforms_by_id[clip_uniform.binding_id] = clip_uniform

    def _draw_arena(
        self,
        frame: _OutputScene,
        artifact: PreparedTrial,
        output_id: str,
        mapping_id: str,
        surface_id: str,
        snapshot: InstanceSnapshot,
        gpu_resources: dict[str, Any],
    ) -> None:
        frame.arena_drawer.draw(
            context=frame.context,
            moderngl=self._moderngl,
            target=frame.surface_fbos[mapping_id],
            artifact=artifact,
            output_id=output_id,
            surface_id=surface_id,
            snapshot=snapshot,
            gpu_resources=gpu_resources,
        )

    def _draw_layer(
        self,
        frame: _OutputScene,
        artifact: PreparedTrial,
        gpu_resources: dict[str, Any],
        output_id: str,
        mapping_id: str,
        snapshot: InstanceSnapshot,
        normalized: list[tuple[float, float]],
    ) -> Any:
        settings = snapshot.settings
        if settings is None:
            raise RuntimeError("prepared instance snapshot has no settings")
        assert self._moderngl is not None
        values = dict(snapshot.state)
        array = frame.quad_array
        program = frame.layer_program
        mode = 0
        texture = None
        if settings.kind in ("image", "video"):
            asset_id = settings.asset_id
            if settings.kind == "video":
                asset_id = settings.asset_id
                if not isinstance(asset_id, str):
                    raise RuntimeError(
                        "prepared video instance has no resolved asset id"
                    )
                texture = frame.video_textures.get((snapshot.instance_id, asset_id))
            else:
                textures = gpu_resources.get(
                    f"{artifact.identity.resource_generation}:{asset_id}"
                )
                if textures is None:
                    raise RuntimeError(
                        f"prepared GPU texture {asset_id} is unavailable"
                    )
                texture = textures[self._output_index(artifact, output_id)]
            if texture is None:
                raise RuntimeError(f"prepared GPU texture {asset_id} is unavailable")
        else:
            if settings.kind != "texture":
                raise RuntimeError("arena settings cannot be drawn as a 2D layer")
            pattern = settings.pattern
            if pattern.kind == "sine_grating":
                mode = 1
            elif pattern.kind == "square_grating":
                mode = 2
            elif pattern.kind == "checkerboard":
                mode = 3
            else:
                mode = 4
                texture = gpu_resources[
                    f"{artifact.identity.resource_generation}:{pattern.asset_id}"
                ][self._output_index(artifact, output_id)]
        program["mode"].value = mode
        program["mean_rgb"].value = _vector(
            values.get("mean_rgb"),
            getattr(settings, "mean_linear_rgb", (0.0, 0.0, 0.0)),
        )
        program["modulation_rgb"].value = _vector(
            values.get("modulation_rgb"),
            getattr(settings, "modulation_linear_rgb", (0.0, 0.0, 0.0)),
        )
        program["contrast"].value = float(values.get("contrast", 1.0))
        program["opacity"].value = float(values.get("opacity", 1.0))
        pattern_obj = settings.pattern if settings.kind == "texture" else None
        frequency_pair = (
            float(values.get("frequency", 0.0)) * float(values.get("width", 1.0)),
            0.0,
        )
        if pattern_obj is not None and pattern_obj.kind == "checkerboard":
            frequency_pair = (
                float(values.get("frequency_x", 0.0)) * float(values["width"]),
                float(values.get("frequency_y", 0.0)) * float(values["height"]),
            )
        period_pair = (
            float(values.get("width", 1.0)) / float(values.get("period_x", 1.0)),
            float(values.get("height", 1.0)) / float(values.get("period_y", 1.0)),
        )
        program["frequency"].value = _vector(values.get("frequency"), frequency_pair)
        program["period"].value = _vector(values.get("period"), period_pair)
        program["phase"].value = _vector(
            values.get("phase"),
            (
                float(values.get("phase_x", 0.0)),
                float(values.get("phase_y", 0.0)),
            ),
        )
        components = clip_vertex_components(normalized)
        program["clip_vertices"].write(struct.pack("8f", *components))
        program["image_tex"].value = 0
        if texture is not None:
            texture.use(0)
        array.render(mode=self._moderngl.TRIANGLE_STRIP)
        from cephvr.visual_stimulus.rendering.types import UniformSnapshot

        layout = next(
            (
                item
                for item in artifact.uniform_layouts
                if item.instance_id == snapshot.instance_id
                and item.output_id == output_id
                and item.name == f"clip_vertices_{mapping_id}"
            ),
            None,
        )
        if layout is None:
            raise RuntimeError(
                "prepared shader layout omits the mapped surface clip uniform"
            )
        return UniformSnapshot(layout.binding_id, float32_words(components))

    @staticmethod
    def _output_index(artifact: PreparedTrial, output_id: str) -> int:
        return tuple(item.output_id for item in artifact.display.outputs).index(
            output_id
        )

    def _bind_warp_profile(
        self, frame: _OutputScene, profile: GeometricProfile
    ) -> None:
        frame.warp_program["has_mask"].value = int(profile.mask is not None)
        frame.warp_program["has_weight"].value = int(profile.weight is not None)
        frame.warp_program["scene_tex"].value = 0
        frame.warp_program["mask_tex"].value = 1
        frame.warp_program["weight_tex"].value = 2

    def _apply_output(
        self,
        frame: _OutputScene,
        artifact: PreparedTrial,
        output_id: str,
        marker_high: bool,
        marker_index: int,
    ) -> None:
        context = frame.context
        assert self._moderngl is not None
        frame.device_fbo.use()
        context.viewport = (
            0,
            0,
            frame.output_texture.size[0],
            frame.output_texture.size[1],
        )
        frame.output_program["source_tex"].value = 0
        frame.output_program["lut_tex"].value = 1
        context.disable(self._moderngl.BLEND)
        frame.output_program["calibrated"].value = int(
            artifact.display.photometric_mode == "calibrated"
        )
        frame.output_program["lut_size"].value = max(2, frame.lut_texture.size[0])
        patch = artifact.display.photodiode_patch
        marker_output = output_id == artifact.display.photodiode_output_id
        frame.output_program["marker_active"].value = float(
            marker_output and patch is not None
        )
        if patch is not None:
            output = next(
                item for item in artifact.display.outputs if item.output_id == output_id
            )
            low, high = patch.rect.x / output.width_px, patch.rect.y / output.height_px
            right = (patch.rect.x + patch.rect.width) / output.width_px
            top = (patch.rect.y + patch.rect.height) / output.height_px
            frame.output_program["marker_rect"].value = (low, high, right, top)
            frame.output_program["marker_rgb"].value = tuple(
                patch.high_linear_rgb if marker_high else patch.low_linear_rgb
            )
        frame.output_texture.use(0)
        frame.lut_texture.use(1)
        frame.output_quad_array.render(mode=self._moderngl.TRIANGLE_STRIP)
        screen = getattr(context, "screen", None)
        if screen is not None:
            context.copy_framebuffer(screen, frame.device_fbo)

    def capture_review_composite(
        self,
        slot: object,
        outputs: tuple[RenderedOutput, ...],
        encoding: ReviewEncoding,
    ) -> object:
        del slot
        return self._review_capture.capture(outputs, encoding)

    def poll_review_capture(self, pending: object) -> bytes | None:
        return self._review_capture.poll(pending)

    def cancel_review_capture(self, pending: object) -> bool:
        return self._review_capture.cancel(pending)

    def release(self) -> None:
        failures: list[str] = []
        try:
            self._review_capture.release()
        except Exception as exc:
            failures.append(f"review capture: {exc}")
        for trial_outputs in self._outputs.values():
            for output in trial_outputs.values():
                output.activate()
                try:
                    output.diagnostics.release()
                except Exception as exc:
                    failures.append(f"diagnostic ring: {exc}")
                failures.extend(_release_owned(output.owned_resources, "trial output"))
        for key, (activate, resources) in tuple(
            self._resource_builder.partial_allocations.items()
        ):
            try:
                activate()
                failures.extend(_release_owned(resources, f"partial output {key[1]}"))
                if not resources:
                    del self._resource_builder.partial_allocations[key]
            except Exception as exc:
                failures.append(f"partial output {key[1]} activation: {exc}")
        if failures:
            raise RuntimeError("scene resources remain owned: " + "; ".join(failures))
        self._resource_builder.partial_allocations.clear()
        self._outputs.clear()
        self._artifacts.clear()
        self._resources.clear()
        self._gpu_resources.clear()


def _vector(value: Any, fallback: Sequence[float]) -> tuple[float, ...]:
    if isinstance(value, (tuple, list)):
        return tuple(float(component) for component in value)
    return tuple(float(component) for component in fallback)


def _release_owned(resources: list[Any], label: str) -> list[str]:
    failures: list[str] = []
    for resource in reversed(tuple(resources)):
        try:
            resource.release()
            for index in range(len(resources) - 1, -1, -1):
                if resources[index] is resource:
                    del resources[index]
                    break
        except Exception as exc:
            failures.append(f"{label}: {exc}")
    return failures
