"""Partial, diagnostic-only validation and runnable stage resolution (T08/T20)."""

from __future__ import annotations

from dataclasses import dataclass

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as control
from cephvr.tracking.config.annotations import manual, reference, search
from cephvr.tracking.config.models.methods import (
    ArcSectionSettings,
    ContourSettings,
    EllipseSettings,
    ExponentialSmoothingSettings,
    FinFlowSettings,
    FinRegionSettings,
    FlowSettings,
    LocalMedianSettings,
    ModelSettings,
    SectionFlowSupportSettings,
    StageConfiguration,
    WaterFlowSettings,
)
from cephvr.tracking.config.pipeline import CHANNELS, PIPELINES, ResolvedPipeline
from cephvr.tracking.config.stages import StageSpec, builtin_registry
from cephvr.tracking.config.validation import _validate_spatial_settings
from cephvr.tracking.types import ImageLayout
from cephvr.tracking.v1 import methods_pb2 as methods
from cephvr.tracking.v1 import services_pb2 as wire
from cephvr.visual_stimulus.config.models.schema_common import Model, parse_json


@dataclass(frozen=True)
class DiagnosticResolution:
    pipeline: ResolvedPipeline
    status: tuple[wire.TrackingDiagnosticStageStatus, ...]
    quality: DiagnosticEstimatorInputs | None = None


class DiagnosticEstimatorInputs(Model):
    """Typed quality inputs; locomotion-only estimator fields remain optional."""

    schema_version: int
    sections: ArcSectionSettings
    quality: LocalMedianSettings
    support: SectionFlowSupportSettings | None = None
    smoothing: ExponentialSmoothingSettings | None = None
    fin_region: FinRegionSettings | None = None


_DEPENDENCIES = {
    wire.TRACKING_DIAGNOSTIC_STAGE_POSE: (),
    wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION: (
        wire.TRACKING_DIAGNOSTIC_STAGE_POSE,
    ),
    wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW: (),
    wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY: (
        wire.TRACKING_DIAGNOSTIC_STAGE_POSE,
        wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
        wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
    ),
    wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION: (
        wire.TRACKING_DIAGNOSTIC_STAGE_POSE,
        wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
        wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
        wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
    ),
}


def resolve_diagnostic(
    settings: control.TrackingSettings,
    selected: tuple[int, ...],
    source: ImageLayout,
    *,
    max_bytes: int,
) -> DiagnosticResolution:
    """Validate only selected runnable stages; experiment validation stays strict."""
    if settings.input_camera_role != camera_pb2.CAMERA_ROLE_TRACKING:
        raise ValueError("diagnostic input_camera_role must be the Tracking camera")
    _validate_spatial_settings(settings)
    if settings.HasField("image_scale") and (
        settings.image_scale.image_width_px,
        settings.image_scale.image_height_px,
    ) != (source.width, source.height):
        raise ValueError("image scale dimensions differ from the acquired source")
    if settings.HasField("preprocessing"):
        crop = settings.preprocessing.crop_region
        if settings.preprocessing.crop_enabled and (
            crop.x_px + crop.width_px > source.width
            or crop.y_px + crop.height_px > source.height
        ):
            raise ValueError("preprocessing crop exceeds acquired source")

    selected_set = set(selected)
    if len(selected_set) != len(selected) or not selected_set <= set(_DEPENDENCIES):
        raise ValueError("unknown or duplicate diagnostic stage")
    statuses: list[wire.TrackingDiagnosticStageStatus] = []
    runnable: set[int] = set()
    registry = builtin_registry()
    if len({item.stage_id for item in settings.stages}) != len(settings.stages):
        raise ValueError("duplicate Tracking stage settings")
    entries = {item.stage_id: item for item in settings.stages}
    pose_ready = False
    pose_mode = settings.pose_mode
    quality_inputs: DiagnosticEstimatorInputs | None = None
    resolved_stages: list[tuple[StageSpec, Model]] = []
    # Evaluate in dependency order, independent of wire/request ordering.
    order = (
        wire.TRACKING_DIAGNOSTIC_STAGE_POSE,
        wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
        wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
        wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
        wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION,
    )
    for stage in order:
        if stage not in selected_set:
            continue
        if stage == wire.TRACKING_DIAGNOSTIC_STAGE_POSE:
            if pose_mode not in (
                control.TRACKING_POSE_MODE_MANUAL,
                control.TRACKING_POSE_MODE_AUTOMATIC,
            ):
                raise ValueError("pose_mode must be manual or automatic")
            pose_ready = _pose_ready(settings, pose_mode, source)
        missing = [
            dependency
            for dependency in _DEPENDENCIES[stage]
            if dependency not in runnable
        ]
        if stage == wire.TRACKING_DIAGNOSTIC_STAGE_POSE and not pose_ready:
            statuses.append(
                _unavailable(stage, "pose annotations or source reference are absent")
            )
            continue
        if missing:
            statuses.append(
                _unavailable(stage, "required diagnostic prerequisite is unavailable")
            )
            continue
        try:
            if (
                stage == wire.TRACKING_DIAGNOSTIC_STAGE_POSE
                and pose_mode == control.TRACKING_POSE_MODE_AUTOMATIC
            ):
                selected_method = entries.get("pose")
                if selected_method is None:
                    raise ValueError(
                        "stages.pose: selected automatic pose method is missing"
                    )
                spec, model = registry.resolve(
                    _stage_config(selected_method), max_bytes=max_bytes
                )
                if not isinstance(model, (ContourSettings, ModelSettings)):
                    raise ValueError("stages.pose: incompatible settings model")
                resolved_stages.append((spec, model))
            elif stage == wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW:
                flow = entries.get("image_flow")
                if flow is None:
                    raise ValueError(
                        "stages.image_flow: selected flow settings are missing"
                    )
                spec, model = registry.resolve(_stage_config(flow), max_bytes=max_bytes)
                if not isinstance(model, FlowSettings):
                    raise ValueError("stages.image_flow: incompatible flow settings")
                resolved_stages.append((spec, model))
            elif stage == wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION:
                geometry = entries.get("geometry")
                if geometry is None:
                    raise ValueError(
                        "stages.geometry: sampling geometry settings are missing"
                    )
                spec, model = registry.resolve(
                    _stage_config(geometry), max_bytes=max_bytes
                )
                if not isinstance(model, EllipseSettings):
                    raise ValueError("stages.geometry: incompatible geometry settings")
                resolved_stages.append((spec, model))
            elif stage in (
                wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
                wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION,
            ):
                estimator = entries.get("estimator")
                if estimator is None:
                    raise ValueError("stages.estimator: estimator settings are missing")
                try:
                    spec = registry.declaration(
                        estimator.stage_id, estimator.implementation_id
                    )
                except ValueError:
                    raise ValueError(
                        "stages.estimator: unsupported estimator declaration"
                    ) from None
                if spec.settings_schema_id != estimator.settings_schema_id:
                    raise ValueError("stages.estimator: settings schema mismatch")
                if stage == wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION:
                    complete = registry.resolve(
                        _stage_config(estimator), max_bytes=max_bytes
                    )[1]
                    if not isinstance(complete, (WaterFlowSettings, FinFlowSettings)):
                        raise ValueError(
                            "stages.estimator: locomotion requires full estimator settings"
                        )
                    resolved_stages.append((spec, complete))
                    quality_inputs = DiagnosticEstimatorInputs.model_validate(
                        complete.model_dump()
                    )
                else:
                    quality_inputs = parse_json(
                        DiagnosticEstimatorInputs,
                        estimator.settings_json,
                        max_bytes=max_bytes,
                    )
                    if (
                        spec.implementation_id == "fin_flow_proxy"
                        and quality_inputs.fin_region is None
                    ):
                        raise ValueError(
                            "stages.estimator.fin_region: required for fin sampling"
                        )
                    flow_model = next(
                        (
                            model
                            for binding, model in resolved_stages
                            if binding.stage_id == "image_flow"
                        ),
                        None,
                    )
                    if (
                        quality_inputs.quality.maximum_native_cost is not None
                        and isinstance(flow_model, FlowSettings)
                        and not flow_model.output_cost
                    ):
                        raise ValueError(
                            "stages.image_flow.output_cost: required by native-cost quality gate"
                        )
        except (ValueError, TypeError) as exc:
            raise ValueError(str(exc)) from exc
        runnable.add(stage)
        statuses.append(
            wire.TrackingDiagnosticStageStatus(
                stage=wire.TrackingDiagnosticStage.Name(stage),
                state=wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE,
            )
        )

    pipeline_id = settings.pipeline_id or "water_flow"
    if wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION in runnable:
        if not settings.HasField("pipeline_id"):
            raise ValueError("pipeline_id is required by selected locomotion")
        estimator_spec = next(
            (spec for spec, _model in resolved_stages if spec.stage_id == "estimator"),
            None,
        )
        expected_estimator = PIPELINES.get(settings.pipeline_id)
        if (
            expected_estimator is None
            or estimator_spec is None
            or estimator_spec.implementation_id != expected_estimator.estimator_id
        ):
            raise ValueError(
                "pipeline_id and estimator implementation are incompatible"
            )
    elif pipeline_id not in PIPELINES:
        pipeline_id = "water_flow"
    try:
        definition = PIPELINES[pipeline_id]
    except KeyError as exc:
        raise ValueError("unsupported diagnostic pipeline") from exc
    resolved = ResolvedPipeline(definition, tuple(resolved_stages), CHANNELS)
    return DiagnosticResolution(resolved, tuple(statuses), quality_inputs)


def _stage_config(value: methods.StageConfiguration) -> StageConfiguration:
    return StageConfiguration(
        stage_id=value.stage_id,
        implementation_id=value.implementation_id,
        settings_schema_id=value.settings_schema_id,
        settings_json=value.settings_json,
    )


def _pose_ready(
    settings: control.TrackingSettings, pose_mode: int, source: ImageLayout
) -> bool:
    if pose_mode == control.TRACKING_POSE_MODE_MANUAL:
        if not settings.HasField("manual_pose"):
            return False
        if (
            settings.manual_pose.image_width_px,
            settings.manual_pose.image_height_px,
        ) != (source.width, source.height):
            raise ValueError("manual pose dimensions differ from acquired source")
        manual(settings.manual_pose)
        return True
    if pose_mode == control.TRACKING_POSE_MODE_AUTOMATIC:
        if not settings.HasField("subject_reference"):
            return False
        if reference(settings.subject_reference) != (source.width, source.height):
            raise ValueError("subject reference dimensions differ from acquired source")
        if not settings.HasField("pose_search_region"):
            return False
        search(settings.pose_search_region, source.width, source.height)
        return True
    return False


def _unavailable(stage: int, reason: str) -> wire.TrackingDiagnosticStageStatus:
    return wire.TrackingDiagnosticStageStatus(
        stage=wire.TrackingDiagnosticStage.Name(stage),
        state=wire.TRACKING_DIAGNOSTIC_STAGE_STATE_UNAVAILABLE,
        reason=reason,
    )
