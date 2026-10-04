"""Pure Visual Stimulus configuration loading and validation (V19, E07, E14)."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any

from cephvr.control.v1 import types_pb2
from cephvr.shared.config import ConfigurationError, LoadedPair, load_pair
from cephvr.visual_stimulus.compiler import validate_program_semantics
from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Group,
    Program,
    TrialArenaBoundaries,
    parse_program_json,
)
from cephvr.visual_stimulus.config.models.schema_common import parse_json
from cephvr.visual_stimulus.v1 import runtime_pb2

_POLICY_VERSION = 7
_CONTRACT_VERSION = 1
_MAX_DOCUMENT_BYTES = 16_777_216
_MAX_EXPANDED_EPOCHS = 100_000
_POLICY_SHA256 = "52e8307df79be66861ed29964d67e43b64a36a06b04f7dfd1cbee9129dcf55be"
_CONFIG_KEYS = frozenset(
    """
    rpc.port
    resources.max_document_bytes resources.max_expanded_epochs
    resources.max_prepared_plan_bytes resources.max_asset_cpu_bytes
    resources.max_asset_gpu_bytes resources.decoder_threads
    resources.codec_threads_per_context resources.codec_threads_total
    resources.decoder_contexts resources.decoded_frames_per_instance
    resources.decoded_bytes_total resources.decoder_working_bytes_total
    resources.capture_slots resources.recording_bytes_total
    resources.evidence_pending_bytes
    recording_runtime.record_sync_interval_s recording_runtime.video_sync_interval_s
    recording_runtime.fragment_target_s recording_runtime.encoder_stall_timeout_s
    recording_runtime.record_stall_timeout_s feedback.max_result_age_ms
    recording.save_visual_stimulus_data recording.ffmpeg_args
    """.split()
)
_POLICY_KEYS = frozenset(
    """
    runtime.process_layout runtime.rendering_library runtime.window_library
    projection.method projection.surfaces projection.observer_position_policy
    projection.geometric_correction projection.optional_correction_inputs
    programs.authoring_model programs.scene_composition programs.storage_format
    programs.model_library programs.schema_source programs.validation_policy
    programs.execution_input programs.trial_plan_retention programs.coordinate_spaces
    programs.parameter_animation programs.animation_clock programs.duration_modes
    programs.trial_duration_source programs.random_duration_distribution
    programs.random_duration_repeats programs.epoch_state programs.absent_instance_state
    programs.trial_state programs.group_order_modes programs.group_order_default
    assets.source_stability assets.protection_failure assets.image_profiles
    assets.video_profiles assets.arena_profile
    arena.source_policy arena.boundary_source arena.movement_modes
    arena.boundary_response arena.shading
    idle.content idle.startup idle.invalid_startup_configuration
    video.preparation video.decoder_library video.decoder_execution
    video.decoder_context_ownership video.codec_thread_policy video.end_behaviors
    video.end_behavior_default video.late_frame_policy video.unavailable_frame_policy
    timing.missed_presentation_policy presentation.supported_modes
    presentation.default_mode presentation.supported_rgb_bits_per_channel
    presentation.precision_policy presentation.quantization
    photodiode.pattern_family photodiode.pattern_version photodiode.marker_levels
    photodiode.period_frames photodiode.reset_at color.working_space
    color.composition_format color.alpha color.output_correction
    color.uncalibrated_encoding photometric_calibration.supported_modes
    photometric_calibration.model photometric_calibration.interpolation
    output_range.policy recording.plan_log_suffix recording.evidence_suffix
    recording.video_suffix recording.plan_log_owner recording.video_source
    recording.video_layout recording.tile_order recording.tile_grid_columns
    recording.tile_scale recording.tile_resampling recording.composite_depth
    recording.encoder_sessions recording.recording_execution recording.readback
    recording.encoder_launch recording.video_fidelity recording.framework
    recording.args_scope recording.args_ownership recording.argument_contract
    recording.container recording.review_timing recording.review_frame_mapping
    recording.frame_duplication recording.mp4_mode recording.review_depth_policy
    recording.empty_video_policy recording.overload_policy recording.evidence_format
    recording.record_durability recording.evidence_layout recording.crash_state
    recording.crash_recovery recording.crashed_review_video
    replay.source replay.export_fidelity replay.asset_retention replay.fingerprint
    replay.fingerprint_cache replay.partial_replay replay.verification
    feedback.mapping feedback.operations feedback.invalid_input_policy
    feedback.epoch_attribution feedback.motion_composition feedback.stale_result_policy
    feedback.age_reference tracking_results.consumption
    """.split()
)
_LIMIT_FIELDS = (
    "max_document_bytes",
    "max_expanded_epochs",
    "max_prepared_plan_bytes",
    "max_asset_cpu_bytes",
    "max_asset_gpu_bytes",
    "decoder_threads",
    "codec_threads_per_context",
    "codec_threads_total",
    "decoder_contexts",
    "decoded_frames_per_instance",
    "decoded_bytes_total",
    "decoder_working_bytes_total",
    "capture_slots",
    "recording_bytes_total",
    "evidence_pending_bytes",
)


def _paths(root: Path) -> tuple[Path, Path]:
    return (
        root / "config" / "backends" / "visual_stimulus_config.toml",
        root / "contracts" / "policy" / "visual_stimulus_policy.toml",
    )


def _load_pair(root: Path) -> LoadedPair:
    config_path, policy_path = _paths(Path(root))
    pair = load_pair(
        config_path,
        policy_path,
        allowed_config_keys=_CONFIG_KEYS,
        allowed_policy_keys=_POLICY_KEYS,
        allowed_empty_tables={
            "projection",
            "programs",
            "assets",
            "idle",
            "video",
            "presentation",
            "photodiode",
            "color",
            "photometric_calibration",
        },
        expected_policy={
            "runtime.process_layout": "coordinator_and_render_worker_with_recording_thread_when_saving"
        },
    )
    if pair.policy_version != _POLICY_VERSION:
        raise ConfigurationError(
            f"Visual Stimulus policy_version must be {_POLICY_VERSION}"
        )
    if hashlib.sha256(policy_path.read_bytes()).hexdigest() != _POLICY_SHA256:
        raise ConfigurationError(
            "Visual Stimulus fixed policy content differs from implementation"
        )
    return pair


def _positive_integer(table: dict[str, Any], name: str, path: str) -> int:
    value = table.get(name)
    if type(value) is not int or value <= 0:
        raise ConfigurationError(f"{path} must be a positive integer")
    return value


def _duration_ns(value: object, path: str, scale: int) -> int:
    if type(value) is int:
        decimal = Decimal(value)
    elif isinstance(value, Decimal):
        decimal = value
    else:
        raise ConfigurationError(f"{path} must be positive")
    if decimal <= 0:
        raise ConfigurationError(f"{path} must be positive")
    ns = decimal * scale
    if ns != ns.to_integral_value() or ns >= 1 << 63:
        raise ConfigurationError(
            f"{path} must be an exact positive int64 nanosecond value"
        )
    return int(ns)


def load_defaults(root: Path) -> types_pb2.VisualStimulusSettings:
    """Load operator-owned session defaults while preserving optional presence."""
    pair = _load_pair(Path(root))
    config = pair.config
    result = types_pb2.VisualStimulusSettings()
    recording = config.get("recording", {})
    if "save_visual_stimulus_data" in recording:
        value = recording["save_visual_stimulus_data"]
        if type(value) is not bool:
            raise ConfigurationError(
                "recording.save_visual_stimulus_data must be Boolean"
            )
        result.save_visual_stimulus_data = value
    if "ffmpeg_args" in recording:
        args = recording["ffmpeg_args"]
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise ConfigurationError("recording.ffmpeg_args must be a string array")
        result.review_ffmpeg_args.extend(args)
    return result


def load_file_policies(root: Path) -> runtime_pb2.VisualStimulusFilePolicies:
    """Resolve versioned file-only resource and timing policies."""
    pair = _load_pair(Path(root))
    result = runtime_pb2.VisualStimulusFilePolicies(contract_version=_CONTRACT_VERSION)
    limits = pair.config.get("resources", {})
    for field in _LIMIT_FIELDS:
        setattr(
            result.limits, field, _positive_integer(limits, field, f"resources.{field}")
        )
    timing = pair.config.get("recording_runtime", {})
    for source, target in (
        ("record_sync_interval_s", "record_sync_interval_ns"),
        ("video_sync_interval_s", "video_sync_interval_ns"),
        ("fragment_target_s", "fragment_target_ns"),
        ("encoder_stall_timeout_s", "encoder_stall_timeout_ns"),
        ("record_stall_timeout_s", "record_stall_timeout_ns"),
    ):
        if source in timing:
            setattr(
                result,
                target,
                _duration_ns(
                    timing[source], f"recording_runtime.{source}", 1_000_000_000
                ),
            )
    age = pair.config.get("feedback", {}).get("max_result_age_ms")
    if age is not None:
        result.max_result_age_ns = _duration_ns(
            age, "feedback.max_result_age_ms", 1_000_000
        )
    return result


def validate_display_profile(
    profile_json: str, *, max_bytes: int = _MAX_DOCUMENT_BYTES
) -> frozenset[str]:
    """Validate the saved display profile without touching graphics devices."""
    profile = parse_display_json(profile_json, max_bytes=max_bytes)
    return frozenset(output.output_id for output in profile.active_outputs)


def validate_configuration(
    candidate: types_pb2.ExperimentConfiguration,
    *,
    max_document_bytes: int = _MAX_DOCUMENT_BYTES,
    max_expanded_epochs: int = _MAX_EXPANDED_EPOCHS,
) -> types_pb2.ValidationResult:
    """Validate Visual Stimulus's typed operator settings without opening graphics/media devices."""
    result = types_pb2.ValidationResult(
        completed=True,
        valid=True,
        component="visual_stimulus",
        configuration_module_version="visual-stimulus-config-v2",
    )
    selected = [
        backend
        for backend in candidate.backends
        if backend.backend_name == "visual_stimulus"
    ]
    if len(selected) > 1:
        _issue(
            result,
            "backends.visual_stimulus",
            "DUPLICATE_BACKEND",
            "Visual Stimulus settings appear more than once",
        )
        return result
    if not selected:
        return result
    backend = selected[0]
    if backend.WhichOneof("settings") != "visual_stimulus":
        _issue(
            result,
            "backends.visual_stimulus",
            "MISSING_SETTINGS",
            "Visual Stimulus backend has no typed settings",
        )
        return result
    settings = backend.visual_stimulus
    if settings.HasField("display"):
        try:
            validate_display_profile(
                settings.display.profile_json, max_bytes=max_document_bytes
            )
        except (ValueError, TypeError) as exc:
            _issue(
                result,
                "backends.visual_stimulus.display.profile_json",
                "INVALID_DISPLAY_PROFILE",
                str(exc),
            )
    if (
        settings.HasField("save_visual_stimulus_data")
        and settings.save_visual_stimulus_data
        and not settings.review_ffmpeg_args
    ):
        _issue(
            result,
            "backends.visual_stimulus.review_ffmpeg_args",
            "MISSING_ENCODING_ARGS",
            "saving requires the complete accepted FFmpeg argument list",
        )

    for index, trial in enumerate(candidate.trials):
        prefix = f"trials[{index}].stimulus"
        if not trial.HasField("stimulus") or not trial.stimulus.HasField("program"):
            _issue(
                result,
                f"{prefix}.program",
                "MISSING_PROGRAM",
                "every trial requires a stimulus program",
            )
            continue
        source = trial.stimulus.program.program_json
        try:
            program = parse_program_json(source, max_bytes=max_document_bytes)
            seed = (
                trial.stimulus.stimulus_seed_decimal
                if trial.stimulus.HasField("stimulus_seed_decimal")
                else "0"
            )
            warnings = validate_program_semantics(
                program,
                max_expanded_epochs=max_expanded_epochs,
                seed_decimal=seed,
            )
            for warning in warnings:
                issue = result.issues.add(
                    component="visual_stimulus", field_path=f"{prefix}.program"
                )
                issue.failure.code = "PREDICTABLE_CLIPPING"
                issue.failure.message = warning
        except (ValueError, TypeError, OverflowError) as exc:
            _issue(
                result, f"{prefix}.program.program_json", "INVALID_PROGRAM", str(exc)
            )
            continue
        if not trial.stimulus.HasField("arena_boundaries"):
            _issue(
                result,
                f"{prefix}.arena_boundaries",
                "MISSING_ARENA_BOUNDARIES",
                "every trial requires an explicit arena-boundary document",
            )
        else:
            try:
                parse_json(
                    TrialArenaBoundaries,
                    trial.stimulus.arena_boundaries.boundaries_json,
                    max_bytes=max_document_bytes,
                )
            except (ValueError, TypeError) as exc:
                _issue(
                    result,
                    f"{prefix}.arena_boundaries",
                    "INVALID_ARENA_BOUNDARIES",
                    str(exc),
                )
        if (
            candidate.HasField("mode")
            and candidate.mode == types_pb2.SESSION_MODE_OPEN_LOOP
            and _program_has_feedback(program)
        ):
            _issue(
                result,
                f"{prefix}.program",
                "FEEDBACK_REQUIRES_CLOSED_LOOP",
                "open-loop trials cannot declare stimulus feedback",
            )
    return result


def _issue(
    result: types_pb2.ValidationResult, field: str, code: str, message: str
) -> None:
    item = result.issues.add(component="visual_stimulus", field_path=field)
    item.failure.code = code
    item.failure.message = message
    result.valid = False


def _program_has_feedback(program: Program) -> bool:
    """Return whether any authored epoch declares a tracking feedback binding."""

    def nodes_have_feedback(nodes: tuple[Epoch | Group, ...]) -> bool:
        for node in nodes:
            if isinstance(node, Group):
                if nodes_have_feedback(node.body):
                    return True
            elif any(getattr(setting, "feedback", ()) for setting in node.settings):
                return True
        return False

    return nodes_have_feedback(program.sequence)
