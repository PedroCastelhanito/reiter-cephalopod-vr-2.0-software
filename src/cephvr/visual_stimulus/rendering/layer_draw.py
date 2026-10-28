"""Draw one 2D layer and capture its exact mapped shader inputs."""

from __future__ import annotations

import struct
from collections.abc import Sequence
from typing import Any

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.rendering.evidence import (
    clip_vertex_components,
    float32_words,
    layer_uniform_values,
)
from cephvr.visual_stimulus.rendering.image_fit import SCREEN_IMAGE_FITS
from cephvr.visual_stimulus.rendering.layer_cache import LayerCache
from cephvr.visual_stimulus.rendering.scene_resources import (
    PreparedSceneOutput as _OutputScene,
)
from cephvr.visual_stimulus.rendering.types import InstanceSnapshot, UniformSnapshot


def draw_layer(
    moderngl: Any,
    frame: _OutputScene,
    artifact: PreparedTrial,
    gpu_resources: dict[str, Any],
    output_id: str,
    mapping_id: str,
    snapshot: InstanceSnapshot,
    normalized: list[tuple[float, float]],
    cache: LayerCache | None = None,
) -> Any:
    layers = LayerCache.for_artifact(artifact, cache)
    output_index = tuple(o.output_id for o in artifact.display.active_outputs).index(
        output_id
    )
    settings = snapshot.settings
    if settings is None:
        raise RuntimeError("prepared instance snapshot has no settings")
    assert moderngl is not None
    values = dict(snapshot.state)
    array = frame.quad_array
    program = frame.layer_program
    mode = 0
    texture = None
    image_pixels = None
    fold = None
    crop_origin = None
    field = None
    field_values: dict[str, tuple[float, float]] = {}
    if settings.kind == "texture" and settings.pattern.kind == "image_tile":
        field = frame.field_programs.get(str(settings.pattern.asset_id))
        if field is not None:
            if settings.space.kind != "physical_surface":
                raise ValueError(
                    "Physical texture fields require millimetre coordinates"
                )
            program, array = field
    if settings.kind == "sparse_noise":
        # Grid-resolution RGBA8 cells; the shader scales and composites the background.
        mode = 10
        if snapshot.sparse_textures is None:
            raise RuntimeError("sparse-noise snapshot has no streamed texture")
        texture = snapshot.sparse_textures[output_index]
        if texture is None:
            raise RuntimeError("sparse-noise texture is absent for this output")
    elif settings.kind in ("image", "video"):
        if settings.kind == "image":
            mode = {
                "resize": 0,
                "source": 7,
                "fold": 8,
                "stretch": 0,
                "contain": 5,
                "cover": 6,
            }[settings.fit]
            if settings.fit in SCREEN_IMAGE_FITS:
                corners, image_pixels = layers.screen_frame(mapping_id)
                normalized = list(corners)
                program["image_target_pixels"].value = image_pixels
                if settings.fit == "fold":
                    fold = layers.fold_map(mapping_id)
                    crop = gpu_resources.get(
                        f"{artifact.identity.resource_generation}:{settings.asset_id}:crops",
                        {},
                    ).get(output_id)
                    if crop is not None:
                        mode = 12
                        crop_origin = (float(crop.x), float(crop.y))
                        program["image_crop_origin"].value = crop_origin
                    program["image_fold_map"].write(struct.pack("6f", *fold))
        asset_id = settings.asset_id
        if settings.kind == "video":
            asset_id = settings.asset_id
            if not isinstance(asset_id, str):
                raise RuntimeError("prepared video instance has no resolved asset id")
            texture = frame.video_textures.get((snapshot.instance_id, asset_id))
        else:
            textures = gpu_resources.get(
                f"{artifact.identity.resource_generation}:{asset_id}"
            )
            if textures is None:
                raise RuntimeError(f"prepared GPU texture {asset_id} is unavailable")
            texture = textures[output_index]
        if texture is None:
            raise RuntimeError(f"prepared GPU texture {asset_id} is unavailable")
    else:
        if settings.kind != "texture":
            raise RuntimeError("arena settings cannot be drawn as a 2D layer")
        pattern = settings.pattern
        if settings.grating and pattern.kind in ("sine_grating", "square_grating"):
            mode = 11
        elif pattern.kind == "sine_grating":
            mode = 1
        elif pattern.kind == "square_grating":
            mode = 2
        elif pattern.kind == "checkerboard":
            mode = 3
        else:
            if field is not None:
                mode = 9
                field_values = {
                    "field_extent_mm": (
                        float(values["width"]),
                        float(values["height"]),
                    ),
                    "field_phase_mm": (
                        float(values.get("phase_x", 0))
                        * float(values.get("period_x", 1)),
                        float(values.get("phase_y", 0))
                        * float(values.get("period_y", 1)),
                    ),
                }
                for name, value in field_values.items():
                    if name in program:
                        program[name].value = value
            else:
                mode = 4
                texture = gpu_resources[
                    f"{artifact.identity.resource_generation}:{pattern.asset_id}"
                ][output_index]
    program["mode"].value = mode
    shader = layer_uniform_values(settings, values)
    program["grating_sharpness"].value = shader["grating_sharpness"][0]
    program["mean_rgb"].value = shader["mean_rgb"]
    program["modulation_rgb"].value = shader["modulation_rgb"]
    program["contrast"].value = shader["contrast"][0]
    program["opacity"].value = shader["opacity"][0]
    program["frequency"].value = shader["frequency"]
    program["period"].value = shader["period"]
    program["phase"].value = shader["phase"]
    components = clip_vertex_components(normalized)
    program["clip_vertices"].write(struct.pack("8f", *components))
    program["image_tex"].value = 0
    if texture is not None:
        texture.use(0)
    array.render(mode=moderngl.TRIANGLE_STRIP)
    mapped: dict[str, Sequence[float]] = {"clip_vertices": components, **field_values}
    if image_pixels is not None:
        mapped["image_target_pixels"] = image_pixels
    if fold is not None:
        mapped["image_fold_map"] = fold
    if crop_origin is not None:
        mapped["image_crop_origin"] = crop_origin
    result = []
    for name, words in mapped.items():
        layout = layers.layout(
            snapshot.instance_id,
            output_id,
            f"{name}_{mapping_id}",
            detail=(
                "prepared shader layout omits the mapped surface clip uniform"
                if name == "clip_vertices"
                else None
            ),
        )
        result.append(UniformSnapshot(layout.binding_id, float32_words(words)))
    return tuple(result)
