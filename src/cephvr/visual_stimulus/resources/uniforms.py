"""Canonical layouts for the built-in renderer's shader inputs."""

from __future__ import annotations

from collections.abc import Iterator

from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.evidence_model import UniformLayout
from cephvr.visual_stimulus.config.models.program_model import Node, Program
from cephvr.visual_stimulus.resources.physical_field import (
    candidate_assets,
    epoch_settings,
)

_SHADER = "cephvr-linear-scene-v1"
_SCALARS = ("opacity", "contrast")
_VECTORS = ("mean_rgb", "modulation_rgb", "frequency", "phase", "period")


def build_uniform_layouts(
    program: Program,
    display: DisplayProfile | None = None,
    physical_field_assets: frozenset[str] = frozenset(),
) -> tuple[UniformLayout, ...]:
    """Declare shader values, including each instance's mapped surface quad."""
    layouts: list[UniformLayout] = []
    seen: set[str] = set()
    screen_images: dict[str, set[str]] = {}
    fold_images: dict[str, set[str]] = {}
    field_instances: set[str] = set()
    grating_instances: set[str] = set()
    for node in _walk(program.sequence):
        for setting in epoch_settings(node) if node.kind == "epoch" else ():
            if setting.kind == "texture" and setting.grating:
                grating_instances.add(setting.instance_id)
            if (
                setting.kind == "texture"
                and setting.pattern.kind == "image_tile"
                and physical_field_assets
                # Any drawable candidate (table row or Asset rule) may be a field.
                and any(
                    not isinstance(asset_id, str) or asset_id in physical_field_assets
                    for asset_id in candidate_assets(node, setting)
                )
            ):
                field_instances.add(setting.instance_id)
            if setting.kind == "image" and setting.fit in {"resize", "source", "fold"}:
                surfaces = (
                    {m.surface_id for m in setting.space.mappings}
                    if setting.space.kind == "physical_surface"
                    else set(setting.space.surfaces)
                )
                screen_images.setdefault(setting.instance_id, set()).update(surfaces)
                if setting.fit == "fold":
                    fold_images.setdefault(setting.instance_id, set()).update(surfaces)
    for instance_id in sorted(
        {
            setting.instance_id
            for node in _walk(program.sequence)
            for setting in (epoch_settings(node) if node.kind == "epoch" else ())
            if setting.kind != "arena"
        }
    ):
        scalar_names = _SCALARS + (
            ("grating_sharpness",) if instance_id in grating_instances else ()
        )
        for name in scalar_names:
            binding = f"{instance_id}-{name}"
            if binding in seen:
                continue
            layouts.append(
                UniformLayout(
                    binding_id=binding,
                    instance_id=instance_id,
                    output_id=None,
                    shader_resource_id=_SHADER,
                    name=name,
                    scalar_type="float32",
                    shape=(),
                )
            )
            seen.add(binding)
        if display is not None:
            for mapping in display.active_mappings:
                binding = f"{instance_id}-{mapping.mapping_id}-clip"
                if binding in seen:
                    continue
                layouts.append(
                    UniformLayout(
                        binding_id=binding,
                        instance_id=instance_id,
                        output_id=mapping.output_id,
                        shader_resource_id=_SHADER,
                        name=f"clip_vertices_{mapping.mapping_id}",
                        scalar_type="float32",
                        shape=(4, 2),
                    )
                )
                seen.add(binding)
                if instance_id in field_instances:
                    for name in ("field_extent_mm", "field_phase_mm"):
                        layouts.append(
                            UniformLayout(
                                binding_id=f"{instance_id}-{mapping.mapping_id}-{name}",
                                instance_id=instance_id,
                                output_id=mapping.output_id,
                                shader_resource_id=_SHADER,
                                name=f"{name}_{mapping.mapping_id}",
                                scalar_type="float32",
                                shape=(2,),
                            )
                        )
                if mapping.surface_id in screen_images.get(instance_id, set()):
                    layouts.append(
                        UniformLayout(
                            binding_id=f"{instance_id}-{mapping.mapping_id}-image-pixels",
                            instance_id=instance_id,
                            output_id=mapping.output_id,
                            shader_resource_id=_SHADER,
                            name=f"image_target_pixels_{mapping.mapping_id}",
                            scalar_type="float32",
                            shape=(2,),
                        )
                    )
                if mapping.surface_id in fold_images.get(instance_id, set()):
                    layouts.append(
                        UniformLayout(
                            binding_id=f"{instance_id}-{mapping.mapping_id}-crop",
                            instance_id=instance_id,
                            output_id=mapping.output_id,
                            shader_resource_id=_SHADER,
                            name=f"image_crop_origin_{mapping.mapping_id}",
                            scalar_type="float32",
                            shape=(2,),
                        )
                    )
                    layouts.append(
                        UniformLayout(
                            binding_id=f"{instance_id}-{mapping.mapping_id}-fold",
                            instance_id=instance_id,
                            output_id=mapping.output_id,
                            shader_resource_id=_SHADER,
                            name=f"image_fold_map_{mapping.mapping_id}",
                            scalar_type="float32",
                            shape=(3, 2),
                        )
                    )
        for name in _VECTORS:
            binding = f"{instance_id}-{name}"
            if binding in seen:
                continue
            layouts.append(
                UniformLayout(
                    binding_id=binding,
                    instance_id=instance_id,
                    output_id=None,
                    shader_resource_id=_SHADER,
                    name=name,
                    scalar_type="float32",
                    shape=(3 if name.endswith("rgb") else 2,),
                )
            )
            seen.add(binding)
    for instance_id in sorted(
        {
            setting.instance_id
            for node in _walk(program.sequence)
            for setting in (epoch_settings(node) if node.kind == "epoch" else ())
            if setting.kind == "arena"
        }
    ):
        binding = f"{instance_id}-arena-model"
        layouts.append(
            UniformLayout(
                binding_id=binding,
                instance_id=instance_id,
                output_id=None,
                shader_resource_id="cephvr-linear-arena-v1",
                name="arena_model_matrix",
                scalar_type="float32",
                shape=(4, 4),
            )
        )
    return tuple(layouts)


def _walk(nodes: tuple[Node, ...]) -> Iterator[Node]:
    for node in nodes:
        yield node
        if node.kind == "group":
            yield from _walk(node.body)


def validate_image_layouts(
    layouts: tuple[UniformLayout, ...],
    display: DisplayProfile | None,
    content: dict[str, object],
) -> None:
    """Validate consumed fixed-screen image mappings before publishing resources."""
    from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
    from cephvr.visual_stimulus.rendering.image_fit import screen_image_frame
    from cephvr.visual_stimulus.rendering.image_fold import calibrated_fold_map

    screen_mappings = {
        item.name.removeprefix("image_target_pixels_")
        for item in layouts
        if item.name.startswith("image_target_pixels_")
    }
    fold_mappings = {
        item.name.removeprefix("image_fold_map_")
        for item in layouts
        if item.name.startswith("image_fold_map_")
    }
    profiles = [item for item in content.values() if isinstance(item, GeometricProfile)]
    for profile in profiles:
        if profile.mapping_id in screen_mappings:
            screen_image_frame(profile)
        if profile.mapping_id in fold_mappings:
            if display is None:
                raise ValueError("Fold requires display calibration")
            calibrated_fold_map(display.geometry, profiles, profile)
