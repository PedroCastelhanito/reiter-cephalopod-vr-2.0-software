"""Canonical planned motion and projector source grouping for dashboard previews."""

from collections import Counter
from dataclasses import dataclass
from math import hypot

from cephvr.visual_stimulus.compiler.expansion import expand_program
from cephvr.visual_stimulus.config.models.program_model import (
    Constant,
    Fixed,
    Group,
    Hold,
    Program,
    Rate,
    Settings,
    TextureSettings,
)
from cephvr.visual_stimulus.rendering.motion import evaluate_function


@dataclass(frozen=True)
class MotionEpoch:
    start: float
    end: float
    name: str
    settings: tuple[Settings, ...]


def motion_epochs(program: Program, seed: str) -> tuple[MotionEpoch, ...]:
    """Use canonical expansion without inventing unresolved timing or order."""
    pending = list(program.sequence)
    while pending:
        node = pending.pop()
        if isinstance(node, Group):
            if node.order == "shuffle_each_repetition" and not seed:
                raise ValueError("Set a stimulus seed to preview shuffled order.")
            pending.extend(node.body)
    epochs = []
    elapsed = 0.0
    for occurrence in expand_program(
        program, seed_decimal=seed or "0", max_expanded_epochs=2000
    ):
        source = occurrence.source
        if not isinstance(source.duration, Fixed):
            raise ValueError("Variable epoch timing is resolved at Setup.")
        end = elapsed + source.duration.duration.ns() / 1e9
        epochs.append(MotionEpoch(elapsed, end, source.epoch_id, occurrence.settings))
        elapsed = end
    return tuple(epochs)


def planned_velocity(setting: Settings, local_ns: int) -> tuple[float, float]:
    """Match the speed editor's units; unsupported motion stays explicitly unknown."""
    if setting.feedback:
        raise ValueError("Feedback-driven speed requires live renderer evidence.")
    motions = (setting.motion.x, setting.motion.y)
    if isinstance(setting, TextureSettings):
        if setting.linked_to:
            raise ValueError(
                f"Linked motion follows {setting.linked_to}; select its reference."
            )
        if not all(isinstance(item, Hold) for item in motions):
            raise ValueError(
                "Combined texture translation and phase motion is not plotted."
            )
        motions = (setting.phase_x, setting.phase_y)
    rates = []
    for motion in motions:
        if isinstance(motion, Hold):
            rates.append(0.0)
        elif isinstance(motion, Rate):
            rates.append(evaluate_function(motion.function, local_ns))
        else:
            raise ValueError(
                "Position trajectories have no speed trace in this preview."
            )
    if isinstance(setting, TextureSettings):
        pattern = setting.pattern
        if pattern.kind == "image_tile":
            periods = (
                evaluate_function(pattern.period_x, local_ns),
                evaluate_function(pattern.period_y, local_ns),
            )
        else:
            fx = evaluate_function(
                pattern.frequency_x
                if pattern.kind == "checkerboard"
                else pattern.frequency,
                local_ns,
            )
            fy = (
                evaluate_function(pattern.frequency_y, local_ns)
                if pattern.kind == "checkerboard"
                else fx
            )
            if fx <= 0 or fy <= 0:
                raise ValueError("Texture frequency must be positive to plot speed.")
            periods = (1 / fx, 1 / fy)
            if pattern.kind != "checkerboard":
                rates[1] = 0.0  # Gratings vary only along their local X axis.
        rates = [-rate * period for rate, period in zip(rates, periods, strict=True)]
    return rates[0], rates[1]


def planned_speed(setting: Settings, local_ns: int) -> float:
    return hypot(*planned_velocity(setting, local_ns))


def planned_rotation(setting: Settings, local_ns: int) -> float:
    if setting.feedback:
        raise ValueError("Feedback-driven rotation requires live renderer evidence.")
    motion = setting.motion.yaw if setting.kind == "arena" else setting.motion.rotation
    if isinstance(motion, Hold):
        return 0.0
    if isinstance(motion, Rate):
        return evaluate_function(motion.function, local_ns)
    raise ValueError("Angle trajectories have no angular speed trace in this preview.")


def projector_name(setting: Settings) -> str:
    if setting.kind == "arena":
        return "Arena"
    surfaces = (
        tuple(mapping.surface_id for mapping in setting.space.mappings)
        if setting.space.kind == "physical_surface"
        else setting.space.surfaces
    )
    return " + ".join(surface.title() for surface in surfaces)


@dataclass(frozen=True)
class MotionSource:
    key: tuple[str, str, int]
    name: str
    unit: str
    reference: bool
    settings: tuple[Settings | None, ...]


def has_motion(setting: Settings) -> bool:
    motions = [
        setting.motion.x,
        setting.motion.y,
        setting.motion.yaw if setting.kind == "arena" else setting.motion.rotation,
    ]
    if isinstance(setting, TextureSettings):
        motions.extend((setting.phase_x, setting.phase_y))
    return bool(setting.feedback) or any(
        not isinstance(motion, Hold)
        and not (
            isinstance(motion, Rate)
            and isinstance(motion.function, Constant)
            and motion.function.value == 0
        )
        for motion in motions
    )


def motion_sources(epochs: tuple[MotionEpoch, ...]) -> tuple[MotionSource, ...]:
    """Group projector layers across epochs; static baselines do not un-link followers."""
    grouped: dict[tuple[str, str, int], list[Settings | None]] = {}
    references = set()
    followers = set()
    moving = set()
    independent = set()
    for index, epoch in enumerate(epochs):
        reference_ids = {
            s.linked_to
            for s in epoch.settings
            if isinstance(s, TextureSettings) and s.linked_to
        }
        counts: Counter[tuple[str, str]] = Counter()
        for setting in epoch.settings:
            name = projector_name(setting)
            unit = (
                "mm/s"
                if setting.kind == "arena" or setting.space.kind == "physical_surface"
                else "deg/s"
            )
            counts[(name, unit)] += 1
            key = (name, unit, counts[(name, unit)])
            grouped.setdefault(key, [None] * len(epochs))[index] = setting
            if isinstance(setting, TextureSettings) and setting.linked_to:
                followers.add(key)
            else:
                independent.add(key)
                if has_motion(setting):
                    moving.add(key)
            if setting.instance_id in reference_ids:
                references.add(key)
    sources = []
    for key, settings in grouped.items():
        if key not in independent or (
            key in followers and key not in moving and key not in references
        ):
            continue
        name, unit, layer = key
        if layer > 1:
            name += f" · layer {layer}"
        if key in references:
            name += " · reference"
        sources.append(
            MotionSource(key, name, unit, key in references, tuple(settings))
        )
    return tuple(sorted(sources, key=lambda source: (not source.reference, source.key)))


@dataclass(frozen=True)
class MotionTrace:
    name: str
    unit: str
    color: str
    segments: tuple[tuple[tuple[float, float], ...], ...]


@dataclass(frozen=True)
class PolarSample:
    name: str
    color: str
    direction: float | None
    angular_speed: float | None
    message: str = ""
