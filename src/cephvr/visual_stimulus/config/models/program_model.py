"""Canonical V02–V08 program declaration and pure structural/reference validation.

Setup additionally runs semantic preparation in stimulus-schema.md (resource, function
range, coordinate, writer, duration and compatibility checks). No renderer/device I/O.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from cephvr.visual_stimulus.config.categories import Category, validate_category

from .authoring import SubgroupDraft
from .parameter_catalogue import ConditionUnit, InputUnit, validate_settings_units
from .repetition import AssetRepetitionRule, Repetition
from .schema_common import (
    MINIMUM_TRIAL_DURATION_NS,
    FrameId,
    Model,
    PositiveInt,
    UnitQuaternion,
    Vec3,
    Version1,
    Version2,
    parse_json,
    portable_path,
)
from .schema_common import ProgramId as Id
from .schema_common import SurfaceId as Surface
from .sparse_noise_appearance import SparseNoiseAppearance

Finite = float
Family = Literal["image", "video", "texture", "arena", "sparse_noise"]


class Time(Model):
    seconds: Annotated[
        str, Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]+)?$", max_length=32)
    ]

    @model_validator(mode="after")
    def precise(self) -> Self:
        self.ns()
        return self

    def ns(self) -> int:
        whole, _, fraction = self.seconds.partition(".")
        if any(x != "0" for x in fraction[9:]):
            raise ValueError("time exceeds whole-nanosecond precision")
        n = int(whole) * 1_000_000_000 + int((fraction[:9] + "000000000")[:9])
        if n > (1 << 63) - 1:
            raise ValueError("time exceeds signed int64")
        return n


class Ref(Model):
    kind: Literal["condition"]
    group_id: Id
    column_id: Id


Number = Finite | Ref
AssetChoice = Id | Ref


class Constant(Model):
    kind: Literal["constant"]
    value: Number


class Ramp(Model):
    kind: Literal["ramp"]
    initial: Number
    slope_per_s: Number


class Sine(Model):
    kind: Literal["sine"]
    mean: Number
    amplitude: Number
    frequency_hz: Number
    phase_cycles: Number


class Knot(Model):
    time: Time
    value: Number


class Keyframes(Model):
    kind: Literal["keyframes"]
    interpolation: Literal["linear", "step"]
    knots: Annotated[tuple[Knot, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def order(self) -> Self:
        t = [k.time.ns() for k in self.knots]
        if t[0] != 0 or any(a >= b for a, b in pairwise(t)):
            raise ValueError("keyframes start at zero and increase strictly")
        return self


Function = Annotated[Constant | Ramp | Sine | Keyframes, Field(discriminator="kind")]


class Hold(Model):
    kind: Literal["hold"]


class Rate(Model):
    kind: Literal["rate"]
    function: Function


class Trajectory(Model):
    kind: Literal["trajectory"]
    function: Function


Motion = Annotated[Hold | Rate | Trajectory, Field(discriminator="kind")]


class SurfaceMap(Model):
    surface_id: Surface
    # q = matrix * [surface_x_mm,surface_y_mm,1], shared stimulus-plane mm.
    matrix: tuple[tuple[Finite, Finite, Finite], tuple[Finite, Finite, Finite]]


class PhysicalSpace(Model):
    kind: Literal["physical_surface"]
    frame_id: FrameId
    mappings: Annotated[tuple[SurfaceMap, ...], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        unique([m.surface_id for m in self.mappings])
        return self


class AngularSpace(Model):
    kind: Literal["visual_angle"]
    frame_id: FrameId
    # Explicit unit quaternion xyzw, local frame to physical rig frame.
    frame_to_rig_xyzw: UnitQuaternion
    surfaces: Annotated[tuple[Surface, ...], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        unique(list(self.surfaces))
        return self


Space = Annotated[PhysicalSpace | AngularSpace, Field(discriminator="kind")]


class Initial2D(Model):
    x: Number
    y: Number
    rotation_deg: Number


class Motion2D(Model):
    x: Motion
    y: Motion
    rotation: Motion


class Assignment(Model):
    target: Literal["x", "y", "rotation", "phase_x", "phase_y", "yaw", "playback"]
    value: Number | Time  # Playback requires exact Time; other targets use Number.

    @model_validator(mode="after")
    def playback_time(self) -> Self:
        if (self.target == "playback") != isinstance(self.value, Time):
            raise ValueError(
                "playback assignment requires exact Time; other targets require Number"
            )
        return self


class Feedback(Model):
    binding_id: Id
    source_channel: Id
    target: Literal[
        "x",
        "y",
        "rotation",
        "phase_x",
        "phase_y",
        "yaw",
        "width",
        "height",
        "opacity",
        "contrast",
        "frequency",
        "frequency_x",
        "frequency_y",
        "period_x",
        "period_y",
    ]
    operation: Literal["direct_value", "movement_integration"]
    gain: Function
    offset: Function

    def channel_ids(self) -> tuple[str, ...]:
        return (self.source_channel,)


class PlanarFeedback(Model):
    # V24: ordered anatomical_body forward/sideways pair onto the enclosing arena's
    # world x/y at the current heading, with independent gains and no rate bias.
    binding_id: Id
    operation: Literal["heading_relative_planar_integration"]
    forward_channel: Id
    sideways_channel: Id
    gain: Function
    sideways_gain: Function | None = None

    def channel_ids(self) -> tuple[str, ...]:
        return (self.forward_channel, self.sideways_channel)


ArenaFeedback = Annotated[Feedback | PlanarFeedback, Field(discriminator="operation")]


class InputChannel(Model):
    channel_id: Id
    stream_id: Id
    value_kind: Literal["absolute", "displacement", "interval_average_rate"]
    unit: InputUnit
    frame_id: FrameId


class LayerBase(Model):
    instance_id: Id
    space: Space
    initial: Initial2D
    width: Function
    height: Function
    opacity: Function
    motion: Motion2D
    reset: bool
    assignments: tuple[Assignment, ...]
    feedback: tuple[Feedback, ...]


class ImageSettings(LayerBase):
    kind: Literal["image"]
    asset_id: AssetChoice
    sampling: Literal["nearest", "linear"]

    # Preserve the appearance of programs authored before image fitting existed.
    fit: Literal["resize", "source", "fold", "contain", "cover", "stretch"] = "stretch"


class SparseNoiseSettings(LayerBase):
    """Seeded patterns generated during playback; no image assets (V04).

    Compilation resolves the complete-cell grid from the display and replaces width
    and height with its physical extent.
    """

    kind: Literal["sparse_noise"]
    appearance: SparseNoiseAppearance
    pattern_count: PositiveInt
    pattern_duration: Time

    @model_validator(mode="after")
    def sparse_layer(self) -> Self:
        if not 0 < self.pattern_duration.ns() * self.pattern_count <= (1 << 63) - 1:
            raise ValueError("Sparse-noise pattern duration must be positive")
        if not isinstance(self.space, PhysicalSpace) or len(self.space.mappings) != 1:
            raise ValueError("Sparse noise requires one physical screen mapping")
        return self

    def pattern_at(self, local_ns: int) -> int:
        """Pattern index at epoch-local time, holding the last pattern at exhaustion."""
        return min(
            max(0, local_ns) // self.pattern_duration.ns(), self.pattern_count - 1
        )


class VideoSettings(LayerBase):
    kind: Literal["video"]
    asset_id: AssetChoice
    sampling: Literal["nearest", "linear"]
    initial_playback: Time
    end_behavior: Literal["hold_final_frame", "loop"]


class Grating(Model):
    feature_sharpness: Annotated[float, Field(ge=0, le=1)] = 0.0
    kind: Literal["sine_grating", "square_grating"]
    frequency: Function


class Checkerboard(Model):
    kind: Literal["checkerboard"]
    frequency_x: Function
    frequency_y: Function


class ImageTile(Model):
    kind: Literal["image_tile"]
    asset_id: AssetChoice
    period_x: Function
    period_y: Function
    sampling: Literal["nearest", "linear"]


Pattern = Annotated[Grating | Checkerboard | ImageTile, Field(discriminator="kind")]


class TextureSettings(LayerBase):
    linked_to: Id | None = None
    grating: bool = False
    uniform: bool = False
    kind: Literal["texture"]
    pattern: Pattern
    initial_phase_x_cycles: Number
    initial_phase_y_cycles: Number
    phase_x: Motion
    phase_y: Motion
    mean_linear_rgb: tuple[Number, Number, Number]
    modulation_linear_rgb: tuple[Number, Number, Number]
    contrast: Function

    @model_validator(mode="after")
    def grating_source(self) -> Self:
        if self.uniform and (
            self.grating
            or not isinstance(self.pattern, Grating)
            or self.linked_to is not None
            or not isinstance(self.contrast, Constant)
            or self.contrast.value != 0
            or any(
                not isinstance(m, Hold)
                for m in (
                    self.phase_x,
                    self.phase_y,
                    self.motion.x,
                    self.motion.y,
                    self.motion.rotation,
                )
            )
            or any(binding.target != "opacity" for binding in self.feedback)
        ):
            raise ValueError(
                "Uniform requires zero contrast and stationary independent color"
            )
        if self.grating and (
            not isinstance(self.pattern, (ImageTile, Grating))
            or not isinstance(self.space, PhysicalSpace)
            or not isinstance(self.phase_x, Hold)
            or not isinstance(self.phase_y, Hold)
            or not isinstance(self.motion.rotation, Hold)
        ):
            raise ValueError(
                "Grating requires an independent physical image tile with fixed orientation"
            )
        if (
            self.grating
            and isinstance(self.pattern, Grating)
            and (
                not isinstance(self.pattern.frequency, Constant)
                or not isinstance(self.pattern.frequency.value, (int, float))
                or self.pattern.frequency.value <= 0
            )
        ):
            raise ValueError(
                "Inline Grating requires a positive constant spatial frequency"
            )
        if (
            self.grating
            and isinstance(self.pattern, Grating)
            and self.pattern.kind != "sine_grating"
        ):
            # Marked rendering is shaped by feature_sharpness alone, so kind would be ignored.
            raise ValueError(
                "Inline Grating requires pattern kind sine_grating; "
                "use feature_sharpness 1 for a square wave"
            )
        if self.grating and self.linked_to is None:
            from cephvr.visual_stimulus.config.grating import validate_motion

            validate_motion(self.model_dump(mode="json"))
        return self


class Pose(Model):
    position_mm: tuple[Number, Number]
    yaw_deg: Number


class ArenaMotion(Model):
    x: Motion
    y: Motion
    yaw: Motion


class ArenaSettings(Model):
    kind: Literal["arena"]
    instance_id: Id
    asset_id: AssetChoice
    world_frame_id: FrameId
    asset_to_world: tuple[
        tuple[Finite, Finite, Finite, Finite],
        tuple[Finite, Finite, Finite, Finite],
        tuple[Finite, Finite, Finite, Finite],
        tuple[Finite, Finite, Finite, Finite],
    ]
    initial: Pose
    fixed_height_mm: Number
    fixed_pitch_deg: Number
    fixed_roll_deg: Number
    motion: ArenaMotion
    reset: bool
    assignments: tuple[Assignment, ...]
    feedback: tuple[ArenaFeedback, ...]


Settings = Annotated[
    ImageSettings
    | VideoSettings
    | TextureSettings
    | ArenaSettings
    | SparseNoiseSettings,
    Field(discriminator="kind"),
]


class ColorOverride(Model):
    transfer: Literal["linear", "srgb", "bt709"]
    primaries: Literal["rec709_d65"]
    range: Literal["full", "limited"]
    matrix: Literal["rgb", "bt601", "bt709"]
    chroma_location: Literal["none", "left", "center", "topleft"]
    reason: Annotated[str, Field(min_length=1)]


class Asset(Model):
    asset_id: Id
    logical_path: str
    color_override: ColorOverride | None
    profile: Literal[
        "png_uint_v1",
        "tiff_uint_v1",
        "jpeg8_v1",
        "cephvr1_texture_json_v1",
        "cephvr_grating_json_v1",
        "mp4_h264_sdr8_v1",
        "matroska_ffv1_v3_uint_v1",
        "glb2_static_unlit_v1",
    ]

    @field_validator("logical_path")
    @classmethod
    def path(cls, v: str) -> str:
        return portable_path(v)


class Instance(Model):
    instance_id: Id
    family: Family


class Scene(Model):
    scene_id: Id
    background_linear_rgb: Vec3
    arena_instance_id: Id | None
    layer_instance_ids: tuple[Id, ...]


class Fixed(Model):
    kind: Literal["fixed"]
    duration: Time

    @model_validator(mode="after")
    def positive(self) -> Self:
        if self.duration.ns() == 0:
            raise ValueError("duration must be positive")
        return self


class Random(Model):
    kind: Literal["random"]


Duration = Annotated[Fixed | Random, Field(discriminator="kind")]


class Explicit(Model):
    kind: Literal["explicit_epochs"]


class TargetTotal(Model):
    kind: Literal["target_total_random_epochs"]
    total: Time
    minimum: Time
    maximum: Time

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if not 0 < self.minimum.ns() <= self.maximum.ns() or self.total.ns() == 0:
            raise ValueError("invalid target duration/bounds")
        if self.total.ns() < MINIMUM_TRIAL_DURATION_NS:
            raise ValueError(
                "target trial duration is below the E05 minimum trial duration"
            )
        return self


DurationPlan = Annotated[Explicit | TargetTotal, Field(discriminator="kind")]


class Column(Model):
    column_id: Id
    value_type: Literal["number", "asset_id"]
    unit: ConditionUnit | None


class Cell(Model):
    column_id: Id
    value: Finite | Id


class Row(Model):
    row_id: Id
    cells: tuple[Cell, ...]


class Conditions(Model):
    columns: Annotated[tuple[Column, ...], Field(min_length=1)]
    rows: Annotated[tuple[Row, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def rectangular(self) -> Self:
        unique([x.column_id for x in self.columns])
        unique([x.row_id for x in self.rows])
        for column in self.columns:
            if (column.value_type == "number") != (column.unit is not None):
                raise ValueError(
                    "numeric columns require units; asset columns have no units"
                )
        columns = {x.column_id: x for x in self.columns}
        for row in self.rows:
            for cell in row.cells:
                col = columns.get(cell.column_id)
                if col is not None and (
                    (col.value_type == "number") != isinstance(cell.value, float)
                ):
                    raise ValueError("condition cell type mismatch")
            unique([x.column_id for x in row.cells])
            if {x.column_id for x in row.cells} != {x.column_id for x in self.columns}:
                raise ValueError("every row requires exactly the declared columns")
        return self


class Epoch(Model):
    kind: Literal["epoch"]
    epoch_id: Id
    batch_label: str = Field(default="", max_length=128)
    batch_id: Id | None = None
    subgroup_draft: SubgroupDraft | None = None
    scene_id: Id
    duration: Duration
    settings: tuple[Settings, ...]
    repetition_rules: tuple[Repetition, ...] = ()
    repetition_settings: Annotated[
        tuple[tuple[Settings, ...], ...], Field(max_length=2000)
    ] = ()


class Group(Model):
    kind: Literal["group"]
    group_id: Id
    repetitions: PositiveInt
    order: Literal["as_listed", "shuffle_each_repetition"]
    order_unit: Literal["child_blocks", "condition_rows"]
    conditions: Conditions | None
    body: Annotated[tuple[Node, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def pairing(self) -> Self:
        if (self.conditions is not None) != (self.order_unit == "condition_rows"):
            raise ValueError(
                "condition-row units require a table; child blocks do not have one"
            )
        return self


Node = Annotated[Epoch | Group, Field(discriminator="kind")]
Group.model_rebuild()


def unique(ids: list[str]) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate identity")


def refs(value: object) -> Iterator[Ref]:
    if isinstance(value, Ref):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from refs(getattr(value, name))
    elif isinstance(value, tuple):
        for item in value:
            yield from refs(item)


def _accept_legacy_category(schema: dict[str, JsonValue]) -> None:
    """Publish the loader-normalized legacy value so external validation matches."""
    branches = schema.get("anyOf")
    for branch in branches if isinstance(branches, list) else ():
        names = branch.get("enum") if isinstance(branch, dict) else None
        if isinstance(names, list):
            names.append("texture_drift")
    schema["description"] = (
        "`texture_drift` is a legacy alias that loads as `media_presentation`."
    )


class Program(Model):
    format_version: Version2
    category: Category | None = Field(
        default=None, json_schema_extra=_accept_legacy_category
    )

    @field_validator("category", mode="before")
    @classmethod
    def legacy_category(cls, value: object) -> object:
        return "media_presentation" if value == "texture_drift" else value

    assets: tuple[Asset, ...]
    instances: tuple[Instance, ...]
    scenes: Annotated[tuple[Scene, ...], Field(min_length=1)]
    input_channels: tuple[InputChannel, ...]
    duration: DurationPlan
    sequence: Annotated[tuple[Node, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def references(self) -> Self:
        validate_category(self)
        for xs in (
            [x.asset_id for x in self.assets],
            [x.instance_id for x in self.instances],
            [x.scene_id for x in self.scenes],
            [x.channel_id for x in self.input_channels],
        ):
            unique(xs)
        inst = {x.instance_id: x.family for x in self.instances}
        scenes = {x.scene_id: x for x in self.scenes}
        assets = {x.asset_id: x.profile for x in self.assets}
        channels = {x.channel_id for x in self.input_channels}
        for scene in self.scenes:
            ids = list(scene.layer_instance_ids) + (
                [scene.arena_instance_id] if scene.arena_instance_id else []
            )
            unique(ids)
            if any(i not in inst for i in ids):
                raise ValueError("unknown scene instance")
            if scene.arena_instance_id and inst[scene.arena_instance_id] != "arena":
                raise ValueError("arena slot requires arena")
            if any(inst[i] == "arena" for i in scene.layer_instance_ids):
                raise ValueError("2D layers cannot contain arenas")
        node_ids: set[str] = set()

        def walk(
            nodes: tuple[Node, ...], scope: dict[str, Conditions], repetitions: int = 0
        ) -> None:
            for node in nodes:
                nid = node.epoch_id if isinstance(node, Epoch) else node.group_id
                if nid in node_ids:
                    raise ValueError("duplicate epoch/group identity")
                node_ids.add(nid)
                if isinstance(node, Group):
                    child = dict(scope)
                    if node.conditions is not None:
                        child[node.group_id] = node.conditions
                    walk(node.body, child, node.repetitions)
                    continue
                if node.scene_id not in scenes:
                    raise ValueError("unknown epoch scene")
                scene = scenes[node.scene_id]
                active = set(scene.layer_instance_ids)
                if scene.arena_instance_id:
                    active.add(scene.arena_instance_id)
                if (
                    node.repetition_settings
                    and len(node.repetition_settings) != repetitions
                ):
                    raise ValueError(
                        "Repetition settings must match the enclosing group repetitions"
                    )
                if node.repetition_rules:
                    if not repetitions or node.repetition_settings:
                        raise ValueError(
                            "Random repetition rules need a group and cannot accompany a settings table"
                        )
                    keys = [(r.instance_id, r.parameter) for r in node.repetition_rules]
                    if len(keys) != len(set(keys)) or any(
                        r.instance_id not in active for r in node.repetition_rules
                    ):
                        raise ValueError(
                            "Random rules require distinct active instance parameters"
                        )
                settings_sets = (node.settings, *node.repetition_settings)
                from cephvr.visual_stimulus.config.texture_links import (
                    link_failure,
                    validate_links,
                )

                for settings in settings_sets:
                    try:
                        validate_links(settings)
                    except ValueError as exc:
                        raise link_failure(
                            node.epoch_id, settings, self.category, exc
                        ) from exc
                    ids = [x.instance_id for x in settings]
                    unique(ids)
                    if set(ids) != active:
                        raise ValueError(
                            "complete settings required for exactly active instances"
                        )
                if isinstance(self.duration, Explicit) and isinstance(
                    node.duration, Random
                ):
                    raise ValueError("random duration requires target-total mode")
                for block in (b for settings in settings_sets for b in settings):
                    if inst[block.instance_id] != block.kind:
                        raise ValueError("instance/settings family mismatch")
                    sources = []
                    if isinstance(block, (ImageSettings, VideoSettings, ArenaSettings)):
                        sources.append((block.asset_id, block.kind))
                    if isinstance(block, TextureSettings) and isinstance(
                        block.pattern, ImageTile
                    ):
                        sources.append((block.pattern.asset_id, "image"))
                    for rule in node.repetition_rules:
                        if (
                            isinstance(rule, AssetRepetitionRule)
                            and rule.instance_id == block.instance_id
                        ):
                            if block.kind == "arena" or not sources:
                                raise ValueError(
                                    "Asset variations require an image, video or image-tile texture"
                                )
                            if isinstance(block, TextureSettings) and block.grating:
                                if len(rule.grating_periods_mm) != len(rule.asset_ids):
                                    raise ValueError(
                                        "Grating Asset choices require their spatial periods"
                                    )
                            elif rule.grating_periods_mm:
                                raise ValueError(
                                    "Asset spatial periods require Grating"
                                )
                            sources.extend(
                                (aid, sources[0][1]) for aid in rule.asset_ids
                            )
                    for aid, kind in sources:
                        allowed = {
                            "image": {
                                "png_uint_v1",
                                "tiff_uint_v1",
                                "jpeg8_v1",
                                "cephvr1_texture_json_v1",
                                "cephvr_grating_json_v1",
                            },
                            "video": {"mp4_h264_sdr8_v1", "matroska_ffv1_v3_uint_v1"},
                            "arena": {"glb2_static_unlit_v1"},
                        }[kind]
                        if isinstance(block, TextureSettings) and block.grating:
                            allowed = {"cephvr_grating_json_v1"}
                        if isinstance(aid, Ref):
                            table = scope.get(aid.group_id)
                            if table is None:
                                raise ValueError(
                                    "asset reference outside enclosing condition scope"
                                )
                            column = next(
                                (
                                    c
                                    for c in table.columns
                                    if c.column_id == aid.column_id
                                ),
                                None,
                            )
                            if column is None or column.value_type != "asset_id":
                                raise ValueError(
                                    "asset reference requires asset_id column"
                                )
                            candidates = [
                                c.value
                                for row in table.rows
                                for c in row.cells
                                if c.column_id == aid.column_id
                            ]
                        else:
                            candidates = [aid]
                        if any(
                            not isinstance(candidate, str)
                            or assets.get(candidate) not in allowed
                            for candidate in candidates
                        ):
                            raise ValueError("unknown or wrong-family asset")
                    unique([x.binding_id for x in block.feedback])
                    unique([x.target for x in block.assignments])
                    if any(
                        c not in channels
                        for x in block.feedback
                        for c in x.channel_ids()
                    ):
                        raise ValueError("unknown feedback channel")
                    for ref in refs(block):
                        if ref.group_id not in scope or ref.column_id not in {
                            c.column_id for c in scope[ref.group_id].columns
                        }:
                            raise ValueError(
                                "condition reference outside active enclosing scope"
                            )
                    validate_settings_units(
                        block, scope, {c.channel_id: c for c in self.input_channels}
                    )

        walk(self.sequence, {})
        if (
            isinstance(self.duration, Explicit)
            and explicit_total_ns(self.sequence) < MINIMUM_TRIAL_DURATION_NS
        ):
            raise ValueError(
                "explicit trial duration is below the E05 minimum trial duration"
            )
        return self


def explicit_total_ns(nodes: tuple[Node, ...]) -> int:
    """Order-independent expanded sum of fixed epoch durations (explicit mode only)."""
    total = 0
    for node in nodes:
        if isinstance(node, Epoch):
            total += (
                node.duration.duration.ns() if isinstance(node.duration, Fixed) else 0
            )
        else:
            total += (
                node.repetitions
                * (len(node.conditions.rows) if node.conditions else 1)
                * explicit_total_ns(node.body)
            )
        if total > (1 << 63) - 1:
            raise ValueError("expanded duration exceeds signed int64 nanoseconds")
    return total


def parse_program_json(source: str, *, max_bytes: int, max_depth: int = 64) -> Program:
    if type(max_depth) is not int or max_depth <= 0:
        raise ValueError("positive integer nesting budget required")
    return parse_json(
        Program, source, max_bytes=max_bytes, max_depth=min(max_depth, 64)
    )


class UnrestrictedRegion(Model):
    kind: Literal["unrestricted"]


class ConvexPolygon(Model):
    kind: Literal["convex_polygon_xy"]
    vertices_mm: Annotated[tuple[tuple[Finite, Finite], ...], Field(min_length=3)]
    margin_mm: Annotated[Finite, Field(ge=0)]

    @model_validator(mode="after")
    def convex(self) -> Self:
        points = self.vertices_mm
        if len(set(points)) != len(points):
            raise ValueError("duplicate polygon vertex")
        for i, a in enumerate(points):
            b = points[(i + 1) % len(points)]
            for j, c in enumerate(points):
                if j in (i, (i + 1) % len(points)):
                    continue
                if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 0:
                    raise ValueError(
                        "polygon must be strictly convex and counterclockwise"
                    )
        return self


class ArenaFileRegion(Model):
    kind: Literal["arena_file"]
    margin_mm: Annotated[Finite, Field(ge=0)] = 30.0


Region = Annotated[
    UnrestrictedRegion | ConvexPolygon | ArenaFileRegion, Field(discriminator="kind")
]


class ArenaBoundary(Model):
    instance_id: Id
    world_frame_id: FrameId
    region: Region


class TrialArenaBoundaries(Model):
    format_version: Version1
    bindings: tuple[ArenaBoundary, ...]

    @model_validator(mode="after")
    def identities(self) -> Self:
        unique([b.instance_id for b in self.bindings])
        return self
