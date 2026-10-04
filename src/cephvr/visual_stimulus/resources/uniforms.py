"""Canonical layouts for the built-in renderer's shader inputs."""

from __future__ import annotations

from collections.abc import Iterator

from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.evidence_model import UniformLayout
from cephvr.visual_stimulus.config.models.program_model import Node, Program

_SHADER = "cephvr-linear-scene-v1"
_SCALARS = ("opacity", "contrast")
_VECTORS = ("mean_rgb", "modulation_rgb", "frequency", "phase", "period")


def build_uniform_layouts(
    program: Program, display: DisplayProfile | None = None
) -> tuple[UniformLayout, ...]:
    """Declare shader values, including each instance's mapped surface quad."""
    layouts: list[UniformLayout] = []
    seen: set[str] = set()
    for instance_id in sorted(
        {
            setting.instance_id
            for node in _walk(program.sequence)
            for setting in (node.settings if node.kind == "epoch" else ())
            if setting.kind != "arena"
        }
    ):
        for name in _SCALARS:
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
            for setting in (node.settings if node.kind == "epoch" else ())
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
