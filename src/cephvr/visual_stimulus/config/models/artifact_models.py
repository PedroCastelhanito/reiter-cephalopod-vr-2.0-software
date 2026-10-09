"""Canonical Visual Stimulus prepared/resource/calibration/evidence/export artifact declarations.

Generated JSON schemas share Program/Settings definitions. Runtime providers and
semantic validation obligations are bound in stimulus-schema.md and runtime-bindings.md; no GPU/file I/O.
"""

from __future__ import annotations

from math import isqrt
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from .display_profile import DisplayProfile, Output, PixelRect
from .evidence_model import Identity, UniformLayout
from .program_model import ArenaSettings, Program, Settings, TrialArenaBoundaries, refs
from .schema_common import (
    MINIMUM_TRIAL_DURATION_NS,
    NS,
    U32,
    U64,
    Digest,
    Model,
    Name,
    OrientationDegrees,
    OutputId,
    Version1,
    Version2,
    parse_json,
    portable_path,
)
from .schema_common import PositiveInt as Pos
from .schema_common import ProgramId as Id
from .schema_common import SurfaceId as Surface
from .schema_common import UnitValue as Unit


class Fingerprint(Model):
    resource_id: Id
    logical_path: str
    subresource: str | None
    sha256: Digest
    bytes: U64

    @field_validator("logical_path")
    @classmethod
    def path(cls, v: str) -> str:
        return portable_path(v)


class Interpretation(Model):
    interpretation_id: Id
    width: Pos
    height: Pos
    source_component_bits: tuple[Pos, ...]
    pixel_format: str
    channel_order: tuple[str, ...]
    row_origin: Literal["top_left", "bottom_left"]
    source_alpha: Literal["none", "straight", "associated"]
    transfer: Literal["linear", "srgb", "bt709"]
    primaries: Literal["rec709_d65"]
    range: Literal["full", "limited"]
    matrix: Literal["rgb", "bt601", "bt709"]
    chroma_location: Literal["none", "left", "center", "topleft"]
    orientation_degrees: OrientationDegrees
    mirror_x: bool
    sample_aspect_numerator: Pos
    sample_aspect_denominator: Pos
    resolution_origin: Literal[
        "source_metadata", "explicit_override", "gltf_base_color"
    ]
    effective_override_reason: str | None


class Resource(Model):
    fingerprint: Fingerprint
    kind: Literal["image", "video", "arena", "geometry", "photometric", "shader"]
    profile_id: str
    dependencies: tuple[Id, ...]
    interpretation: Interpretation | None
    cpu_bytes: U64
    gpu_bytes: U64
    provider_compatibility: str


class GroupVisit(Model):
    group_id: Id
    repetition_index: U32
    unit_id: Id
    visit_index: U32


class CurveTruncation(Model):
    settings_path: str
    final_keyframe_ns: NS
    epoch_end_ns: NS


class CompiledEpoch(Model):
    occurrence_index: U32
    source_epoch_id: Id
    duration_origin: Literal["fixed", "sampled", "uniquely_constrained"]
    lineage: tuple[GroupVisit, ...]
    scene_id: Id
    start_ns: NS
    end_ns: NS
    truncated_curves: tuple[CurveTruncation, ...]
    settings: tuple[Settings, ...]  # Fully substituted complete source blocks.

    @model_validator(mode="after")
    def resolved(self) -> Self:
        if self.end_ns <= self.start_ns:
            raise ValueError("nonpositive epoch")
        if any(refs(self.settings)):
            raise ValueError("prepared settings cannot contain condition references")
        return self


class Transition(Model):
    instance_id: Id
    action: Literal[
        "initialize",
        "continue",
        "pause",
        "resume",
        "reset",
        "restart_incompatible",
        "deactivate",
    ]  # deactivate: terminal normal end only.
    reason: str
    next_settings_index: U32 | None
    assignment_indices: tuple[U32, ...]


class Boundary(Model):
    time_ns: NS
    before: U32 | None
    after: U32 | None
    operations: tuple[Transition, ...]


class ReviewTiming(
    Model
):  # E13: constant rate; frame n is the n-th admitted render group.
    pacing_output_id: OutputId | None = None  # Null for common-rate all-output VSync.
    rate_numerator: Pos
    rate_denominator: Pos
    implementation: str
    capability_evidence_id: Id


class CompositeTile(Model):
    output_id: OutputId
    rect: PixelRect  # Bottom-left-origin rectangle inside the composite.
    source_code_bits: Literal[8, 10]


class ReviewEncoding(
    Model
):  # E13: one tiled composite, one encoder (recorded-outputs.md#tiled-composite).
    composite_width: Pos
    composite_height: Pos
    scale_denominator: Pos  # Tile = output size // k; Setup checks k is minimal for the encoder maximum.
    tiles: Annotated[tuple[CompositeTile, ...], Field(min_length=1)]
    native_pixel_format: Literal["rgba8_bottom_up", "r10g10b10a2_le_bottom_up"]
    input_pixel_format: str
    encoder_pixel_format: str
    encoder_gpu_ordinal: Annotated[int, Field(ge=0)]
    force_idr: bool
    effective_ffmpeg_args: tuple[str, ...]
    timing: ReviewTiming


def tile_layout(
    outputs: tuple[Output, ...], k: int, composite_height: int
) -> list[tuple[str, int, int, int, int]]:
    """Fixed layout: output order, row-major, ceil(sqrt(n)) columns, top-left in each cell."""
    n = len(outputs)
    cols = isqrt(n - 1) + 1 if n else 1
    size = [(o.width_px // k, o.height_px // k) for o in outputs]
    widths = [max(size[i][0] for i in range(c, n, cols)) for c in range(min(cols, n))]
    heights = [
        max(size[i][1] for i in range(r * cols, min(n, (r + 1) * cols)))
        for r in range(-(-n // cols))
    ]
    tiles = []
    for i, (o, (w, h)) in enumerate(zip(outputs, size, strict=True)):
        r, c = divmod(i, cols)
        top = sum(heights[:r])  # Rows run downward; rect y is bottom-left origin.
        tiles.append((o.output_id, sum(widths[:c]), composite_height - top - h, w, h))
    return tiles


class PreparedTrial(Model):
    format_version: Version2
    identity: Identity
    source: Program
    source_sha256: Digest
    display: DisplayProfile
    seed_decimal: Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*)$")]
    order_implementation: str
    duration_implementation: str
    duration_sampler_id: str
    epochs: Annotated[tuple[CompiledEpoch, ...], Field(min_length=1)]
    boundaries: tuple[Boundary, ...]
    arena_boundaries: TrialArenaBoundaries
    manifest: ResourceManifest
    uniform_layouts: tuple[UniformLayout, ...]
    model_compatibility: str
    renderer_compatibility: str
    compiler_compatibility: str
    review_encoding: ReviewEncoding | None  # None only with saving Off.

    @property
    def resolved_duration_ns(self) -> int:
        return self.epochs[-1].end_ns

    @model_validator(mode="after")
    def timeline(self) -> Self:
        cursor = 0
        for i, e in enumerate(self.epochs):
            if e.occurrence_index != i or e.start_ns != cursor:
                raise ValueError("noncontiguous prepared epochs")
            cursor = e.end_ns
        if cursor < MINIMUM_TRIAL_DURATION_NS:
            raise ValueError("trial is shorter than the E05 minimum trial duration")
        expected_boundaries = [e.start_ns for e in self.epochs] + [cursor]
        if [b.time_ns for b in self.boundaries] != expected_boundaries:
            raise ValueError("one boundary per epoch and terminal boundary required")
        *inner, terminal = self.boundaries
        if any(op.action == "deactivate" for b in inner for op in b.operations):
            raise ValueError("deactivate is reserved for the terminal boundary")
        final = [x.instance_id for x in self.epochs[-1].settings]
        if sorted(op.instance_id for op in terminal.operations) != sorted(final) or any(
            op.action != "deactivate"
            or op.next_settings_index is not None
            or op.assignment_indices
            for op in terminal.operations
        ):
            raise ValueError(
                "terminal boundary must deactivate exactly the final active instances"
            )
        self.display.require_trial_marker()  # Validate independent pacing and optional marker.
        if (r := self.review_encoding) is not None:
            if any(
                o.width_px // r.scale_denominator < 1
                or o.height_px // r.scale_denominator < 1
                for o in self.display.active_outputs
            ):
                raise ValueError("composite scale leaves an empty tile")
            expected_tiles = tile_layout(
                self.display.active_outputs, r.scale_denominator, r.composite_height
            )
            actual = [
                (t.output_id, t.rect.x, t.rect.y, t.rect.width, t.rect.height)
                for t in r.tiles
            ]
            if actual != expected_tiles or any(
                t.rect.x + t.rect.width > r.composite_width or t.rect.y < 0
                for t in r.tiles
            ):
                raise ValueError(
                    "review composite must tile every display output in the fixed layout"
                )
            bits = [o.rgb_bits_per_channel for o in self.display.active_outputs]
            if [
                t.source_code_bits for t in r.tiles
            ] != bits or r.native_pixel_format != (
                "rgba8_bottom_up" if max(bits) == 8 else "r10g10b10a2_le_bottom_up"
            ):
                raise ValueError(
                    "composite depth must be the largest output depth, with tile source depths retained"
                )
            d = self.display
            if r.timing.pacing_output_id != d.selected_pacing_output_id:
                raise ValueError(
                    "review timing must preserve the configured pacing identity"
                )
            numerator, denominator = d.review_refresh_rate()
            if (
                r.timing.rate_numerator * denominator
                != numerator * r.timing.rate_denominator
            ):
                raise ValueError(
                    "review frame rate must equal the configured nominal refresh rate"
                )
        arenas: dict[str, set[str]] = {}
        for e in self.epochs:
            for x in e.settings:
                if isinstance(x, ArenaSettings):
                    arenas.setdefault(x.instance_id, set()).add(x.world_frame_id)
        bound = {
            b.instance_id: b.world_frame_id for b in self.arena_boundaries.bindings
        }
        if set(bound) != set(arenas) or any(
            frames != {bound[i]} for i, frames in arenas.items()
        ):
            raise ValueError(
                "exactly one matching-frame arena boundary is required for every used arena instance"
            )
        return self


class Grid(Model):
    rows: Annotated[int, Field(ge=2)]
    columns: Annotated[int, Field(ge=2)]
    values: tuple[Unit, ...]
    sampling: Literal["bilinear"]

    @model_validator(mode="after")
    def count(self) -> Self:
        if len(self.values) != self.rows * self.columns:
            raise ValueError("scalar grid size mismatch")
        return self


class Vertex(Model):
    uv: tuple[Unit, Unit]
    xy: tuple[Unit, Unit]


class GeometricProfile(Model):
    format_version: Version1
    calibration_id: Name
    mapping_id: Name
    surface_id: Surface
    output_id: OutputId
    output_width: Pos
    output_height: Pos
    viewport: PixelRect
    rows: Annotated[int, Field(ge=2)]
    columns: Annotated[int, Field(ge=2)]
    vertices: tuple[Vertex, ...]
    orientation: Literal["preserving", "mirrored"]
    diagonal: Literal["bottom_left_to_top_right"]
    mask: Grid | None
    weight: Grid | None
    overlap_group: Id | None
    intended_coverage: Annotated[
        tuple[tuple[Unit, Unit], ...], Field(min_length=3)
    ]  # Ordered simple polygon in viewport XY.
    coverage_tolerance: Annotated[float, Field(gt=0)]
    triangle_area_tolerance: Annotated[float, Field(gt=0)]

    @model_validator(mode="after")
    def grid(self) -> Self:
        if len(self.vertices) != self.rows * self.columns:
            raise ValueError("vertex count mismatch")
        if (
            self.viewport.x + self.viewport.width > self.output_width
            or self.viewport.y + self.viewport.height > self.output_height
        ):
            raise ValueError("viewport exceeds output")
        sign = 1 if self.orientation == "preserving" else -1

        def area(
            a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
        ) -> float:
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

        for row in range(self.rows - 1):
            for col in range(self.columns - 1):
                a = row * self.columns + col
                b = a + 1
                c = a + self.columns
                d = c + 1
                for i, j, k in ((a, b, d), (a, d, c)):
                    verts = [self.vertices[x] for x in (i, j, k)]
                    if area(*(v.uv for v in verts)) <= self.triangle_area_tolerance:
                        raise ValueError("invalid source triangle")
                    if (
                        sign * area(*(v.xy for v in verts))
                        <= self.triangle_area_tolerance
                    ):
                        raise ValueError("folded/degenerate output triangle")
        return self


class ComponentProvenance(Model):
    role: Literal[
        "renderer",
        "shader",
        "image_decoder",
        "video_decoder",
        "arena_importer",
        "color_transform",
        "graphics_driver",
        "gpu",
        "os",
    ]
    implementation: str
    version: str
    content_sha256: Digest | None


class ResourceManifest(Model):
    format_version: Version1
    resources: tuple[Resource, ...]
    provenance: tuple[ComponentProvenance, ...]

    @model_validator(mode="after")
    def references(self) -> Self:
        ids = [r.fingerprint.resource_id for r in self.resources]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate resource")
        known = set(ids)
        graph = {r.fingerprint.resource_id: r.dependencies for r in self.resources}
        if any(d not in known for deps in graph.values() for d in deps):
            raise ValueError("missing resource dependency")
        state = {}  # Iterative DFS: 1 visiting, 2 done; no recursion limit on long chains.
        for root in graph:
            if root in state:
                continue
            state[root] = 1
            stack = [(root, iter(graph[root]))]
            while stack:
                node, deps = stack[-1]
                d = next(deps, None)
                if d is None:
                    state[node] = 2
                    stack.pop()
                elif state.get(d) == 1:
                    raise ValueError("resource dependency cycle")
                elif d not in state:
                    state[d] = 1
                    stack.append((d, iter(graph[d])))
        return self


PreparedTrial.model_rebuild()


def parse_prepared_json(source: str, *, max_bytes: int) -> PreparedTrial:
    return parse_json(PreparedTrial, source, max_bytes=max_bytes, max_depth=80)
