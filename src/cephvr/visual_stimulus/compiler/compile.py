"""Pure program-to-PreparedTrial compilation after resource preparation (V03–V08)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass

from pydantic import BaseModel

from cephvr.visual_stimulus.compiler.durations import (
    DURATION_IMPLEMENTATION,
    DURATION_SAMPLER_ID,
    resolve_durations,
)
from cephvr.visual_stimulus.compiler.expansion import (
    ORDER_IMPLEMENTATION,
    expand_program,
)
from cephvr.visual_stimulus.compiler.transitions import compile_boundaries
from cephvr.visual_stimulus.config.models.artifact_models import (
    CompiledEpoch,
    CurveTruncation,
    PreparedTrial,
    ResourceManifest,
    ReviewEncoding,
)
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.evidence_model import Identity, UniformLayout
from cephvr.visual_stimulus.config.models.program_model import (
    ArenaSettings,
    AssetChoice,
    Constant,
    Explicit,
    Function,
    ImageSettings,
    ImageTile,
    Keyframes,
    Motion,
    PlanarFeedback,
    Program,
    Ramp,
    Ref,
    Settings,
    Sine,
    TargetTotal,
    TextureSettings,
    TrialArenaBoundaries,
    VideoSettings,
    parse_program_json,
)
from cephvr.visual_stimulus.resources.budget import PreparationBudget

MODEL_COMPATIBILITY = "cephvr-visual-stimulus-model-v2"
RENDERER_COMPATIBILITY = "cephvr-visual-stimulus-renderer-v1"
COMPILER_COMPATIBILITY = "cephvr-visual-stimulus-compiler-v1"


@dataclass(frozen=True)
class CompileContext:
    """Exact immutable inputs supplied by controller and prepared resource providers."""

    identity: Identity
    display: DisplayProfile
    arena_boundaries: TrialArenaBoundaries
    manifest: ResourceManifest
    seed_decimal: str
    source_json: str
    uniform_layouts: tuple[UniformLayout, ...] = ()
    review_encoding: ReviewEncoding | None = None
    saving: bool = False
    model_compatibility: str = MODEL_COMPATIBILITY
    renderer_compatibility: str = RENDERER_COMPATIBILITY
    compiler_compatibility: str = COMPILER_COMPATIBILITY


def serialize_prepared_trial(plan: PreparedTrial) -> bytes:
    """Return the exact compact, sorted UTF-8 JSON bytes retained for its digest."""
    payload = plan.model_dump(mode="json")
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def prepared_digest(plan: PreparedTrial) -> tuple[str, int, bytes]:
    """Return SHA-256, byte length, and canonical artifact bytes as one result."""
    encoded = serialize_prepared_trial(plan)
    return hashlib.sha256(encoded).hexdigest(), len(encoded), encoded


def _duration_plan(program: Program) -> TargetTotal | None:
    if isinstance(program.duration, Explicit):
        return None
    return program.duration


def _truncations(
    settings: tuple[Settings, ...], duration_ns: int
) -> tuple[CurveTruncation, ...]:
    """Retain keyframe curves whose final authored knot is cut by this epoch."""
    result: list[CurveTruncation] = []

    def walk(value: object, path: str) -> None:
        if isinstance(value, Keyframes):
            knots = value.knots
            final_ns = knots[-1].time.ns()
            if final_ns > duration_ns:
                result.append(
                    CurveTruncation(
                        settings_path=path,
                        final_keyframe_ns=final_ns,
                        epoch_end_ns=duration_ns,
                    )
                )
            return
        if isinstance(value, BaseModel):
            for name in type(value).model_fields:
                walk(getattr(value, name), f"{path}.{name}" if path else name)
        elif isinstance(value, (tuple, list)):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    for setting_index, setting in enumerate(settings):
        walk(setting, f"settings[{setting_index}]")
    return tuple(result)


def _validate_writers(settings: tuple[Settings, ...], epoch_index: int) -> None:
    for block in settings:
        bindings = [item.binding_id for item in block.feedback]
        if len(bindings) != len(set(bindings)):
            raise ValueError(
                f"epoch[{epoch_index}].{block.instance_id}: duplicate feedback binding"
            )
        by_target: dict[str, list[str]] = {}
        for binding in block.feedback:
            if isinstance(binding, PlanarFeedback):
                for target in ("x", "y"):
                    by_target.setdefault(target, []).append("movement_integration")
            else:
                by_target.setdefault(binding.target, []).append(binding.operation)
        if isinstance(block, ArenaSettings):
            motion_fields: dict[str, Motion] = {
                "x": block.motion.x,
                "y": block.motion.y,
                "yaw": block.motion.yaw,
            }
            direct_fields = {"x": "x", "y": "y", "yaw": "yaw"}
        else:
            motion_fields = {
                "x": block.motion.x,
                "y": block.motion.y,
                "rotation": block.motion.rotation,
            }
            direct_fields = {"x": "x", "y": "y", "rotation": "rotation"}
            if isinstance(block, TextureSettings):
                motion_fields.update(
                    {"phase_x": block.phase_x, "phase_y": block.phase_y}
                )
                direct_fields.update({"phase_x": "phase_x", "phase_y": "phase_y"})
        for target, writers in by_target.items():
            direct = [writer for writer in writers if writer == "direct_value"]
            movement = [
                writer for writer in writers if writer == "movement_integration"
            ]
            if len(direct) > 1 or (direct and movement):
                raise ValueError(
                    f"epoch[{epoch_index}].{block.instance_id}.{target}: competing feedback writers"
                )
            motion_name = direct_fields.get(target)
            motion = motion_fields.get(motion_name) if motion_name else None
            if direct and motion is not None and motion.kind != "hold":
                raise ValueError(
                    f"epoch[{epoch_index}].{block.instance_id}.{target}: direct feedback conflicts with programmed motion"
                )
            if movement and motion is not None and motion.kind == "trajectory":
                raise ValueError(
                    f"epoch[{epoch_index}].{block.instance_id}.{target}: movement conflicts with absolute trajectory"
                )


def _check_ranges(
    settings: tuple[Settings, ...], epoch_index: int, duration_ns: int
) -> None:
    from cephvr.visual_stimulus.config.models.parameter_catalogue import (
        PARAMETER_RANGES,
        check_range,
    )
    from cephvr.visual_stimulus.config.models.program_model import Keyframes

    def numeric(value: float | Ref) -> float:
        if isinstance(value, Ref):
            raise ValueError(
                "condition references must be resolved before range checks"
            )
        return float(value)

    def values(function: Function) -> tuple[float, ...]:
        if isinstance(function, Constant):
            return (numeric(function.value),)
        if isinstance(function, Ramp):
            initial = numeric(function.initial)
            terminal = initial + numeric(function.slope_per_s) * (
                duration_ns / 1_000_000_000
            )
            return initial, terminal
        if isinstance(function, Sine):
            mean = numeric(function.mean)
            amplitude = numeric(function.amplitude)
            frequency = numeric(function.frequency_hz)
            phase = numeric(function.phase_cycles)
            end_cycles = phase + frequency * (duration_ns / 1_000_000_000)
            phases = [phase, end_cycles]
            for landmark in (0.25, 0.75):
                first = math.ceil(min(phase, end_cycles) - landmark)
                last = math.floor(max(phase, end_cycles) - landmark)
                if first <= last:
                    phases.append(landmark + first)
            return tuple(
                mean + amplitude * math.sin(2 * math.pi * cycle) for cycle in phases
            )
        if isinstance(function, Keyframes):
            return tuple(numeric(knot.value) for knot in function.knots)
        return ()

    def check_function(name: str, function: Function, path: str) -> None:
        if name not in PARAMETER_RANGES:
            return
        for value in values(function):
            if not math.isfinite(value):
                raise ValueError(f"{path}: resolved function is not finite")
            check_range(name, value, path)

    for block in settings:
        fields: tuple[str, ...] = (
            ("width", "height", "opacity")
            if not isinstance(block, ArenaSettings)
            else ()
        )
        if isinstance(block, TextureSettings):
            fields += ("contrast",)
        for field in fields:
            function = getattr(block, field)
            check_function(
                field, function, f"epoch[{epoch_index}].{block.instance_id}.{field}"
            )
        if isinstance(block, TextureSettings):
            pattern_fields: tuple[str, ...] = {
                "sine_grating": ("frequency",),
                "square_grating": ("frequency",),
                "checkerboard": ("frequency_x", "frequency_y"),
                "image_tile": ("period_x", "period_y"),
            }[block.pattern.kind]
            for field in pattern_fields:
                check_function(
                    field,
                    getattr(block.pattern, field),
                    f"epoch[{epoch_index}].{block.instance_id}.pattern.{field}",
                )
        for assignment in block.assignments:
            value = assignment.value
            if (
                isinstance(value, (int, float))
                and assignment.target in PARAMETER_RANGES
            ):
                check_range(
                    assignment.target,
                    value,
                    f"epoch[{epoch_index}].{block.instance_id}.assignments.{assignment.target}",
                )


def _check_asset_resources(
    program: Program,
    epochs: list[CompiledEpoch],
    manifest: ResourceManifest,
) -> None:
    """Require each referenced authored asset to bind to prepared bytes."""
    declared = {asset.asset_id: asset.profile for asset in program.assets}
    resources = {
        resource.fingerprint.resource_id: resource for resource in manifest.resources
    }
    required: set[str] = set()

    def add_asset(asset_id: AssetChoice) -> None:
        if isinstance(asset_id, Ref):
            raise ValueError("condition asset reference remains after expansion")
        required.add(asset_id)

    for epoch in epochs:
        for settings in epoch.settings:
            if isinstance(settings, (ImageSettings, VideoSettings, ArenaSettings)):
                add_asset(settings.asset_id)
            elif isinstance(settings, TextureSettings) and isinstance(
                settings.pattern, ImageTile
            ):
                add_asset(settings.pattern.asset_id)
    expected_kind = {
        "png_uint_v1": "image",
        "tiff_uint_v1": "image",
        "jpeg8_v1": "image",
        "mp4_h264_sdr8_v1": "video",
        "matroska_ffv1_v3_uint_v1": "video",
        "glb2_static_unlit_v1": "arena",
    }
    for asset_id in required:
        resource = resources.get(asset_id)
        profile = declared.get(asset_id)
        if resource is None or profile is None:
            raise ValueError(
                f"asset {asset_id!r} has no prepared resource manifest entry"
            )
        if resource.profile_id != profile or resource.kind != expected_kind[profile]:
            raise ValueError(
                f"asset {asset_id!r} prepared resource profile does not match source"
            )
        if resource.fingerprint.logical_path != next(
            asset.logical_path for asset in program.assets if asset.asset_id == asset_id
        ):
            raise ValueError(
                f"asset {asset_id!r} prepared logical path does not match source"
            )


def validate_program_semantics(
    program: Program, *, max_expanded_epochs: int, seed_decimal: str = "0"
) -> tuple[str, ...]:
    """Run reachable condition expansion and pure unit/writer/range validation."""
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)", seed_decimal):
        raise ValueError("seed_decimal must be canonical nonnegative decimal text")
    expanded = expand_program(
        program, seed_decimal=seed_decimal, max_expanded_epochs=max_expanded_epochs
    )
    duration_result = resolve_durations(
        tuple(item.source.duration for item in expanded),
        _duration_plan(program),
        seed_decimal,
    )
    from cephvr.visual_stimulus.compiler.warnings import predicts_color_excursion

    predicted = any(
        value < 0 or value > 1
        for scene in program.scenes
        for value in scene.background_linear_rgb
    )
    for index, (occurrence, duration_ns) in enumerate(
        zip(expanded, duration_result.durations_ns, strict=True)
    ):
        _validate_writers(occurrence.settings, index)
        _check_ranges(occurrence.settings, index, duration_ns)
        predicted |= predicts_color_excursion(occurrence.settings, duration_ns)
    return (
        (
            (
                "Authored source RGB/contrast may exceed the linear output range; "
                "finite excursions are clipped without rescaling. Actual affected outputs "
                "are established by runtime GPU diagnostics."
            ),
        )
        if predicted
        else ()
    )


def compile_trial(
    program: Program,
    context: CompileContext,
    *,
    max_expanded_epochs: int,
    max_prepared_plan_bytes: int | None = None,
    preparation_budget: PreparationBudget | None = None,
) -> PreparedTrial:
    """Compile a fully validated source with already prepared resource artifacts."""
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)", context.seed_decimal):
        raise ValueError("seed_decimal must be canonical nonnegative decimal text")
    parsed_source = parse_program_json(
        context.source_json, max_bytes=max(len(context.source_json.encode("utf-8")), 1)
    )
    if parsed_source != program:
        raise ValueError("source_json does not describe the supplied Program")
    expanded = expand_program(
        program,
        seed_decimal=context.seed_decimal,
        max_expanded_epochs=max_expanded_epochs,
    )
    duration_result = resolve_durations(
        tuple(item.source.duration for item in expanded),
        _duration_plan(program),
        context.seed_decimal,
        budget=preparation_budget,
    )
    compiled_epochs: list[CompiledEpoch] = []
    cursor = 0
    for index, (occurrence, duration_ns, origin) in enumerate(
        zip(
            expanded, duration_result.durations_ns, duration_result.origins, strict=True
        )
    ):
        settings = occurrence.settings
        _validate_writers(settings, index)
        _check_ranges(settings, index, duration_ns)
        end = cursor + duration_ns
        if end > (1 << 63) - 1:
            raise OverflowError("prepared trial timeline exceeds signed int64")
        compiled_epochs.append(
            CompiledEpoch(
                occurrence_index=index,
                source_epoch_id=occurrence.source.epoch_id,
                duration_origin=origin,
                lineage=occurrence.lineage,
                scene_id=occurrence.source.scene_id,
                start_ns=cursor,
                end_ns=end,
                truncated_curves=_truncations(settings, duration_ns),
                settings=settings,
            )
        )
        cursor = end
    _check_asset_resources(program, compiled_epochs, context.manifest)
    if context.saving != (context.review_encoding is not None):
        raise ValueError("review encoding presence must match the saving setting")
    source_bytes = context.source_json.encode("utf-8")
    prepared = PreparedTrial(
        format_version=2,
        identity=context.identity,
        source=program,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        display=context.display,
        seed_decimal=context.seed_decimal,
        order_implementation=ORDER_IMPLEMENTATION,
        duration_implementation=DURATION_IMPLEMENTATION,
        duration_sampler_id=duration_result.sampler_id or DURATION_SAMPLER_ID,
        epochs=tuple(compiled_epochs),
        boundaries=compile_boundaries(compiled_epochs),
        arena_boundaries=context.arena_boundaries,
        manifest=context.manifest,
        uniform_layouts=context.uniform_layouts,
        model_compatibility=context.model_compatibility,
        renderer_compatibility=context.renderer_compatibility,
        compiler_compatibility=context.compiler_compatibility,
        review_encoding=context.review_encoding,
    )
    if max_prepared_plan_bytes is not None:
        actual = len(serialize_prepared_trial(prepared))
        if actual > max_prepared_plan_bytes:
            raise ValueError(
                f"prepared artifact is {actual} bytes; limit is {max_prepared_plan_bytes}"
            )
    return prepared
