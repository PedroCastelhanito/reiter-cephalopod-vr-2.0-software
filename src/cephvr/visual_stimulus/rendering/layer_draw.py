"""Draw one 2D layer and capture its exact mapped shader inputs."""

from __future__ import annotations

import struct
from collections.abc import Sequence
from typing import Any

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.rendering.evidence import (
    clip_vertex_components,
    float32_words,
)
from cephvr.visual_stimulus.rendering.image_fit import (
    SCREEN_IMAGE_FITS,
    screen_image_frame,
)
from cephvr.visual_stimulus.rendering.scene_resources import (
    PreparedSceneOutput as _OutputScene,
)
from cephvr.visual_stimulus.rendering.types import InstanceSnapshot


def draw_layer(
    moderngl: Any,
    frame: _OutputScene,
    artifact: PreparedTrial,
    gpu_resources: dict[str, Any],
    output_id: str,
    mapping_id: str,
    snapshot: InstanceSnapshot,
    normalized: list[tuple[float, float]],
) -> Any:
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
    field = None
    if settings.kind == "texture" and settings.pattern.kind == "image_tile":
        field = frame.field_programs.get(str(settings.pattern.asset_id))
        if field is not None:
            if settings.space.kind != "physical_surface":
                raise ValueError(
                    "Physical texture fields require millimetre coordinates"
                )
            program, array = field
    if settings.kind in ("image", "video"):
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
                profile = next(
                    p
                    for p in artifact.geometric_calibration
                    if p.mapping_id == mapping_id
                )
                normalized, image_pixels = screen_image_frame(profile)
                program["image_target_pixels"].value = image_pixels
                if settings.fit == "fold":
                    from cephvr.visual_stimulus.rendering.image_fold import (
                        calibrated_fold_map,
                    )

                    fold = calibrated_fold_map(
                        artifact.display.geometry,
                        artifact.geometric_calibration,
                        profile,
                    )
                    program["image_fold_map"].write(struct.pack("6f", *fold))
        if settings.kind == "image" and settings.sparse_noise is not None:
            mode = 10
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
                if "field_extent_mm" in program:
                    program["field_extent_mm"].value = (
                        float(values["width"]),
                        float(values["height"]),
                    )
                if "field_phase_mm" in program:
                    program["field_phase_mm"].value = (
                        float(values.get("phase_x", 0))
                        * float(values.get("period_x", 1)),
                        float(values.get("phase_y", 0))
                        * float(values.get("period_y", 1)),
                    )
            else:
                mode = 4
                texture = gpu_resources[
                    f"{artifact.identity.resource_generation}:{pattern.asset_id}"
                ][output_index]
    program["mode"].value = mode
    program["grating_sharpness"].value = getattr(
        getattr(settings, "pattern", None), "feature_sharpness", 0.0
    )
    program["mean_rgb"].value = _vector(
        values.get("mean_rgb"),
        getattr(
            settings,
            "mean_linear_rgb",
            getattr(
                getattr(settings, "sparse_noise", None),
                "background_linear_rgb",
                (0.0, 0.0, 0.0),
            ),
        ),
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
    array.render(mode=moderngl.TRIANGLE_STRIP)
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
    result = [UniformSnapshot(layout.binding_id, float32_words(components))]
    if field is not None:
        for name, components in (
            ("field_extent_mm", (float(values["width"]), float(values["height"]))),
            (
                "field_phase_mm",
                (
                    float(values.get("phase_x", 0)) * float(values.get("period_x", 1)),
                    float(values.get("phase_y", 0)) * float(values.get("period_y", 1)),
                ),
            ),
        ):
            field_layout = next(
                item
                for item in artifact.uniform_layouts
                if item.instance_id == snapshot.instance_id
                and item.output_id == output_id
                and item.name == f"{name}_{mapping_id}"
            )
            result.append(
                UniformSnapshot(field_layout.binding_id, float32_words(components))
            )
    if image_pixels is not None:
        image_layout = next(
            item
            for item in artifact.uniform_layouts
            if item.instance_id == snapshot.instance_id
            and item.output_id == output_id
            and item.name == f"image_target_pixels_{mapping_id}"
        )
        result.append(
            UniformSnapshot(image_layout.binding_id, float32_words(image_pixels))
        )
    if fold is not None:
        fold_layout = next(
            item
            for item in artifact.uniform_layouts
            if item.instance_id == snapshot.instance_id
            and item.output_id == output_id
            and item.name == f"image_fold_map_{mapping_id}"
        )
        result.append(UniformSnapshot(fold_layout.binding_id, float32_words(fold)))
    return tuple(result)


def _vector(value: Any, fallback: Sequence[float]) -> tuple[float, ...]:
    if isinstance(value, (tuple, list)):
        return tuple(float(component) for component in value)
    return tuple(float(component) for component in fallback)
