"""Canonical program helpers for local timeline editing; no runtime ownership."""

from dataclasses import dataclass
from math import isfinite

from cephvr.visual_stimulus.config.models.program_model import (
    AngularSpace,
    Constant,
    Epoch,
    Explicit,
    Fixed,
    Grating,
    Group,
    Hold,
    Initial2D,
    Instance,
    Motion2D,
    Node,
    Program,
    Rate,
    Scene,
    TextureSettings,
    Time,
)


@dataclass
class TrialDraft:
    name: str
    program: Program
    path: str = ""
    stimulus_seed_decimal: str = ""
    gap_after_seconds: str = ""
    arena_boundaries_json: str = ""


def blank_program() -> Program:
    return Program(
        format_version=2,
        assets=(),
        instances=(),
        input_channels=(),
        scenes=(
            Scene(
                scene_id="blank",
                background_linear_rgb=(0.0, 0.0, 0.0),
                arena_instance_id=None,
                layer_instance_ids=(),
            ),
        ),
        duration=Explicit(kind="explicit_epochs"),
        sequence=(
            Epoch(
                kind="epoch",
                epoch_id="Epoch_1",
                scene_id="blank",
                duration=Fixed(kind="fixed", duration=Time(seconds="60")),
                settings=(),
            ),
        ),
    )


def review_program() -> Program:
    """Explicit design-review fixture, never a device/default configuration."""
    base = blank_program()

    def constant(value: float) -> Constant:
        return Constant(kind="constant", value=value)

    hold = Hold(kind="hold")
    texture = TextureSettings(
        kind="texture",
        instance_id="flow",
        space=AngularSpace(
            kind="visual_angle",
            frame_id="rig",
            frame_to_rig_xyzw=(0.0, 0.0, 0.0, 1.0),
            surfaces=("left", "right"),
        ),
        initial=Initial2D(x=0.0, y=0.0, rotation_deg=0.0),
        width=constant(90),
        height=constant(90),
        opacity=constant(1),
        motion=Motion2D(x=hold, y=hold, rotation=hold),
        reset=True,
        assignments=(),
        feedback=(),
        pattern=Grating(kind="sine_grating", frequency=constant(0.05)),
        initial_phase_x_cycles=0.0,
        initial_phase_y_cycles=0.0,
        phase_x=Rate(kind="rate", function=constant(1.5)),
        phase_y=hold,
        mean_linear_rgb=(0.5, 0.5, 0.5),
        modulation_linear_rgb=(0.5, 0.5, 0.5),
        contrast=constant(1),
    )
    return base.model_copy(
        update={
            "instances": (Instance(instance_id="flow", family="texture"),),
            "scenes": (
                *base.scenes,
                Scene(
                    scene_id="flow",
                    background_linear_rgb=(0.0, 0.0, 0.0),
                    arena_instance_id=None,
                    layer_instance_ids=("flow",),
                ),
            ),
            "sequence": (
                Epoch(
                    kind="epoch",
                    epoch_id="Baseline",
                    scene_id="blank",
                    duration=Fixed(kind="fixed", duration=Time(seconds="5")),
                    settings=(),
                ),
                Epoch(
                    kind="epoch",
                    epoch_id="Flow",
                    scene_id="flow",
                    duration=Fixed(kind="fixed", duration=Time(seconds="20")),
                    settings=(texture,),
                ),
                Epoch(
                    kind="epoch",
                    epoch_id="Recovery",
                    scene_id="blank",
                    duration=Fixed(kind="fixed", duration=Time(seconds="35")),
                    settings=(),
                ),
            ),
        }
    )


def node_name(node: Node) -> str:
    return node.epoch_id if isinstance(node, Epoch) else node.group_id


def duration(node: Node) -> float | None:
    if isinstance(node, Epoch):
        return (
            node.duration.duration.ns() / 1e9
            if isinstance(node.duration, Fixed)
            else None
        )
    values = [duration(child) for child in node.body]
    if any(value is None for value in values):
        return None
    try:
        total = (
            sum(value for value in values if value is not None)
            * node.repetitions
            * (len(node.conditions.rows) if node.conditions else 1)
        )
    except OverflowError:
        return None
    return total if isfinite(total) else None


def node_surfaces(node: Node) -> set[str]:
    if isinstance(node, Group):
        return set().union(*(node_surfaces(child) for child in node.body))
    surfaces: set[str] = set()
    for setting in node.settings:
        if setting.kind == "arena":
            surfaces.add("World")
        elif isinstance(setting.space, AngularSpace):
            surfaces.update(face.title() for face in setting.space.surfaces)
        else:
            surfaces.update(
                mapping.surface_id.title() for mapping in setting.space.mappings
            )
    return surfaces


def sequence_summary(nodes: tuple[Node, ...]) -> str:
    times = [duration(item) for item in nodes]
    if any(value is None for value in times):
        return f"{len(times)} blocks · duration resolved at Setup"
    return f"{len(times)} blocks · {sum(t for t in times if t is not None):g} s"
