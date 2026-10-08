from __future__ import annotations

import json
import shutil

import pytest

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.tracking_codec import (
    decode_tracking_settings,
    encode_diagnostic_draft,
    encode_tracking_draft,
)
from cephvr.shared.config import ConfigurationError
from cephvr.tracking.config.diagnostics import resolve_diagnostic
from cephvr.tracking.configuration import (
    load_defaults,
    load_file_policies,
    resolve_settings,
    validate_configuration,
)
from cephvr.tracking.types import ImageLayout
from cephvr.tracking.v1 import services_pb2 as tracking_wire

from .support import ROOT, manual_settings


def candidate(settings: pb.TrackingSettings) -> pb.ExperimentConfiguration:
    value = pb.ExperimentConfiguration()
    value.backends.add(backend_name="tracking", enabled=True, tracking=settings)
    value.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition.behavioral.enabled = True
    return value


def test_defaults_leave_scientific_inputs_unset_and_load_exact_file_limits():
    settings = load_defaults(ROOT)
    assert settings.pipeline_id == "water_flow"
    assert not settings.HasField("input_camera_role")
    assert not settings.HasField("subject_reference")
    assert not settings.HasField("pose_search_region")
    assert settings.pose_mode == pb.TRACKING_POSE_MODE_MANUAL
    assert not settings.HasField("manual_pose")
    assert all(stage.stage_id != "pose" for stage in settings.stages)
    draft = decode_tracking_settings(settings)
    assert draft["image_size"] == [0, 0]
    assert draft["annotations"]["Manual pose"] == []
    automatic = resolve_settings(
        ROOT, pb.TrackingSettings(pose_mode=pb.TRACKING_POSE_MODE_AUTOMATIC)
    )
    assert automatic.pose_mode == pb.TRACKING_POSE_MODE_AUTOMATIC
    contour = json.loads(automatic.stages[0].settings_json)
    assert "threshold_level" not in contour
    policy = load_file_policies(ROOT)
    assert policy.maximum_input_frame_age_ns == 250_000_000
    assert policy.result_capacity == 10
    assert policy.recording.max_pending_records == 4096


def _diagnostic_layout(width: int = 100, height: int = 100) -> ImageLayout:
    return ImageLayout(
        width, height, width * 2, "gray", "uint16", 12, "msb", 0, 4095, "source"
    )


def test_diagnostic_resolver_allows_empty_mask_and_dormant_incomplete_pose():
    settings = load_defaults(ROOT)
    settings.input_camera_role = camera_pb2.CAMERA_ROLE_TRACKING
    # A flow-only probe must not consume or validate dormant manual pose fields.
    settings.manual_pose.image_width_px = 1
    settings.manual_pose.image_height_px = 1
    result = resolve_diagnostic(
        settings,
        (tracking_wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,),
        _diagnostic_layout(),
        max_bytes=1_000_000,
    )
    assert [item.state for item in result.status] == [
        tracking_wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
    ]
    assert [definition.stage_id for definition, _model in result.pipeline.stages] == [
        "image_flow"
    ]

    empty = resolve_diagnostic(settings, (), _diagnostic_layout(), max_bytes=1_000_000)
    assert empty.status == ()
    assert empty.pipeline.stages == ()


def test_diagnostic_resolution_does_not_require_experiment_backend_enabled():
    settings = manual_settings()
    settings.input_camera_role = camera_pb2.CAMERA_ROLE_TRACKING
    backend = pb.BackendSettings(
        backend_name="tracking", enabled=False, tracking=settings
    )
    assert not backend.enabled
    result = resolve_diagnostic(
        backend.tracking,
        (tracking_wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,),
        _diagnostic_layout(),
        max_bytes=1_000_000,
    )
    assert (
        result.status[0].state
        == tracking_wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
    )


def test_diagnostic_resolver_marks_missing_pose_descendants_but_runs_flow():
    settings = load_defaults(ROOT)
    settings.input_camera_role = camera_pb2.CAMERA_ROLE_TRACKING
    selected = (
        tracking_wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION,
        tracking_wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
        tracking_wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
        tracking_wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
        tracking_wire.TRACKING_DIAGNOSTIC_STAGE_POSE,
    )
    result = resolve_diagnostic(
        settings, selected, _diagnostic_layout(), max_bytes=1_000_000
    )
    states = {item.stage: item.state for item in result.status}
    assert (
        states[tracking_wire.TRACKING_DIAGNOSTIC_STAGE_POSE]
        == tracking_wire.TRACKING_DIAGNOSTIC_STAGE_STATE_UNAVAILABLE
    )
    assert (
        states[tracking_wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION]
        == tracking_wire.TRACKING_DIAGNOSTIC_STAGE_STATE_UNAVAILABLE
    )
    assert (
        states[tracking_wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY]
        == tracking_wire.TRACKING_DIAGNOSTIC_STAGE_STATE_UNAVAILABLE
    )
    assert (
        states[tracking_wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION]
        == tracking_wire.TRACKING_DIAGNOSTIC_STAGE_STATE_UNAVAILABLE
    )
    assert (
        states[tracking_wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW]
        == tracking_wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
    )


def test_diagnostic_flow_quality_uses_only_typed_quality_and_sampling_inputs():
    settings = manual_settings()
    settings.input_camera_role = camera_pb2.CAMERA_ROLE_TRACKING
    estimator = next(item for item in settings.stages if item.stage_id == "estimator")
    document = json.loads(estimator.settings_json)
    partial = {key: document[key] for key in ("schema_version", "sections", "quality")}
    estimator.settings_json = json.dumps(partial)
    result = resolve_diagnostic(
        settings,
        (
            tracking_wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
            tracking_wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
            tracking_wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
            tracking_wire.TRACKING_DIAGNOSTIC_STAGE_POSE,
        ),
        _diagnostic_layout(),
        max_bytes=1_000_000,
    )
    assert result.quality is not None
    assert result.quality.sections.count == document["sections"]["count"]
    assert (
        result.quality.quality.minimum_neighbors
        == document["quality"]["minimum_neighbors"]
    )
    assert all(
        definition.stage_id != "estimator"
        for definition, _model in result.pipeline.stages
    )


def test_partial_diagnostic_codec_tracks_fin_region_and_clears_it_for_water():
    selected = (
        tracking_wire.TRACKING_DIAGNOSTIC_STAGE_POSE,
        tracking_wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
        tracking_wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
        tracking_wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
    )
    base = manual_settings()
    fin_draft = decode_tracking_settings(base)
    fin_draft["pipeline"] = "Fin flow"
    fin_draft["analysis_drafts"]["Fin flow"].update(fin_offset="45", fin_span="90")

    first_fin = encode_diagnostic_draft(base, fin_draft, selected)
    estimator = next(item for item in first_fin.stages if item.stage_id == "estimator")
    assert json.loads(estimator.settings_json)["fin_region"] == {
        "schema_version": 1,
        "offset_degrees": 45.0,
        "span_degrees": 90.0,
    }
    first_result = resolve_diagnostic(
        first_fin, selected, _diagnostic_layout(), max_bytes=1_000_000
    )
    assert first_result.quality is not None
    assert first_result.quality.fin_region is not None
    assert first_result.quality.fin_region.offset_degrees == 45
    assert first_result.quality.fin_region.span_degrees == 90

    changed_fin = decode_tracking_settings(first_fin)
    changed_fin["analysis_drafts"]["Fin flow"].update(fin_offset="60", fin_span="120")
    second_fin = encode_diagnostic_draft(first_fin, changed_fin, selected)
    second_estimator = next(
        item for item in second_fin.stages if item.stage_id == "estimator"
    )
    second_document = json.loads(second_estimator.settings_json)
    assert second_document["fin_region"]["offset_degrees"] == 60
    assert second_document["fin_region"]["span_degrees"] == 120
    second_result = resolve_diagnostic(
        second_fin, selected, _diagnostic_layout(), max_bytes=1_000_000
    )
    assert second_result.quality is not None
    assert second_result.quality.fin_region is not None
    assert second_result.quality.fin_region.offset_degrees == 60
    assert second_result.quality.fin_region.span_degrees == 120

    water_draft = decode_tracking_settings(second_fin)
    water_draft["pipeline"] = "Water flow"
    water_settings = encode_diagnostic_draft(second_fin, water_draft, selected)
    water_estimator = next(
        item for item in water_settings.stages if item.stage_id == "estimator"
    )
    assert "fin_region" not in json.loads(water_estimator.settings_json)
    water_result = resolve_diagnostic(
        water_settings, selected, _diagnostic_layout(), max_bytes=1_000_000
    )
    assert water_result.quality is not None
    assert water_result.quality.fin_region is None


def test_diagnostic_rejects_consumed_source_mismatch_and_invalid_flow():
    settings = manual_settings()
    settings.input_camera_role = camera_pb2.CAMERA_ROLE_TRACKING
    settings.manual_pose.image_width_px = 99
    with pytest.raises(ValueError, match="manual pose dimensions"):
        resolve_diagnostic(
            settings,
            (tracking_wire.TRACKING_DIAGNOSTIC_STAGE_POSE,),
            _diagnostic_layout(),
            max_bytes=1_000_000,
        )
    settings.manual_pose.image_width_px = 100
    flow = next(item for item in settings.stages if item.stage_id == "image_flow")
    flow.settings_json = "{}"
    with pytest.raises(ValueError, match="FlowSettings"):
        resolve_diagnostic(
            settings,
            (tracking_wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,),
            _diagnostic_layout(),
            max_bytes=1_000_000,
        )


def test_typed_tracking_settings_decode_without_losing_false_or_annotations():
    settings = manual_settings()
    settings.preprocessing.crop_enabled = False
    settings.preprocessing.scale_percent = 75
    settings.image_scale.image_width_px = 100
    settings.image_scale.image_height_px = 100
    settings.image_scale.distance_start.x_px = 0
    settings.image_scale.distance_start.y_px = 0
    settings.image_scale.distance_end.x_px = 10
    settings.image_scale.distance_end.y_px = 0
    settings.image_scale.distance_mm = 5
    settings.image_scale.pixels_per_mm = 2

    draft = decode_tracking_settings(settings, camera_serial="CAM-1")

    assert draft["camera"] == "CAM-1"
    assert draft["preprocessing"] == {
        "crop_enabled": False,
        "scale_percent": 75,
        "region": [0, 0, 0, 0],
    }
    assert draft["image_size"] == [100, 100]
    assert draft["annotations"]["Manual pose"] == [
        [20.0, 50.0],
        [70.0, 30.0],
        [70.0, 70.0],
    ]
    assert draft["annotations"]["Distance reference"] == [
        [0.0, 0.0],
        [10.0, 0.0],
    ]
    encoded = encode_tracking_draft(settings, draft)
    assert encoded.preprocessing.HasField("crop_enabled")
    assert not encoded.preprocessing.crop_enabled
    assert encoded.preprocessing.scale_percent == 75
    assert encoded.image_scale.distance_start.x_px == 0
    installed = decode_tracking_settings(encoded, camera_serial="CAM-1")
    again = encode_tracking_draft(encoded, installed)
    assert {
        stage.stage_id: json.loads(stage.settings_json) for stage in encoded.stages
    } == {stage.stage_id: json.loads(stage.settings_json) for stage in again.stages}


@pytest.mark.parametrize("pipeline", ["Water flow", "Fin flow"])
@pytest.mark.parametrize("method", ["Manual", "Threshold + contour", "Keypoint model"])
def test_tracking_codec_round_trips_mode_pipeline_and_stage_documents(
    pipeline, method, tmp_path
):
    settings = manual_settings()
    flow_stage = next(
        stage for stage in settings.stages if stage.stage_id == "image_flow"
    )
    flow_document = json.loads(flow_stage.settings_json)
    flow_document["output_cost"] = True
    flow_stage.settings_json = json.dumps(
        flow_document, sort_keys=True, separators=(",", ":")
    )
    estimator_stage = next(
        stage for stage in settings.stages if stage.stage_id == "estimator"
    )
    estimator_document = json.loads(estimator_stage.settings_json)
    estimator_document["quality"]["maximum_native_cost"] = 17
    estimator_stage.settings_json = json.dumps(
        estimator_document, sort_keys=True, separators=(",", ":")
    )

    draft = decode_tracking_settings(settings)
    draft["image_size"] = [100, 100]
    draft["annotations"]["Reference points"] = [
        [90.0, 50.0],
        [10.0, 50.0],
        [50.0, 30.0],
        [50.0, 70.0],
    ]
    draft["annotations"]["Search region"] = [[5, 7], [95, 97]]
    draft["pipeline"] = pipeline
    draft["choices"]["pose_method"] = method
    draft["fields"].update(
        threshold="40",
        minimum_area="5",
        maximum_area="1000",
        anisotropy="0.2",
        axis_length="10",
        base_width="3",
        triangle_area="1",
        model_manifest=str(tmp_path / "pose.json"),
        candidate_score="0.3",
        landmark_score="0.4",
        fin_offset="0",
        fin_span="30",
    )
    draft["analysis_drafts"][pipeline] = {
        key: draft["fields"][key] for key in draft["analysis_drafts"][pipeline]
    }

    first = encode_tracking_draft(settings, draft, asset_root=str(tmp_path))
    if method == "Manual":
        assert not first.HasField("pose_search_region")
        assert first.HasField("manual_pose")
    else:
        assert first.pose_search_region.x_px == 5
        assert first.pose_search_region.y_px == 7
        assert first.pose_search_region.width_px == 90
        assert first.pose_search_region.height_px == 90
        assert not first.HasField("manual_pose")
    assert (
        json.loads(
            next(
                stage for stage in first.stages if stage.stage_id == "estimator"
            ).settings_json
        )["quality"]["maximum_native_cost"]
        == 17
    )
    installed = decode_tracking_settings(first, camera_serial="CAM-1")
    if method != "Manual":
        assert installed["annotations"]["Search region"] == [[5, 7], [95, 97]]
    second = encode_tracking_draft(first, installed, asset_root=str(tmp_path))
    assert {
        stage.stage_id: json.loads(stage.settings_json) for stage in first.stages
    } == {stage.stage_id: json.loads(stage.settings_json) for stage in second.stages}


def test_saved_false_and_complete_method_settings_are_preserved():
    settings = manual_settings()
    before = settings.SerializeToString()
    resolved = resolve_settings(ROOT, settings)
    assert resolved.SerializeToString() == before
    assert settings.SerializeToString() == before
    assert not resolved.save_tracking_data
    assert all(stage.stage_id != "pose" for stage in resolved.stages)
    assert validate_configuration(candidate(resolved)).valid


def test_fin_pipeline_requires_explicit_wedge():
    settings = manual_settings()
    settings.pipeline_id = "fin_flow"
    del settings.stages[:]
    settings = resolve_settings(ROOT, settings)
    result = validate_configuration(candidate(settings))
    assert not result.valid
    assert "offset_degrees" in result.issues[0].failure.message


def test_unknown_method_and_unavailable_selected_camera_fail_without_fallback():
    settings = manual_settings()
    value = candidate(settings)
    value.backends[1].acquisition.behavioral.enabled = False
    assert not validate_configuration(value).valid
    settings.stages[0].implementation_id = "arbitrary_plugin"
    assert not validate_configuration(candidate(settings)).valid


def test_disabled_tracking_retains_incomplete_saved_settings():
    value = candidate(load_defaults(ROOT))
    value.backends[0].enabled = False
    before = value.SerializeToString()
    assert validate_configuration(value).valid
    assert value.SerializeToString() == before


def test_file_policy_mismatch_and_unknown_operator_keys_fail(tmp_path):
    (tmp_path / "config/backends").mkdir(parents=True)
    (tmp_path / "contracts/policy").mkdir(parents=True)
    for path in (
        "config/backends/tracking_config.toml",
        "contracts/policy/tracking_policy.toml",
    ):
        shutil.copyfile(ROOT / path, tmp_path / path)
    config = tmp_path / "config/backends/tracking_config.toml"
    original = config.read_text()
    config.write_text(original.replace("policy_version = 43", "policy_version = 44"))
    with pytest.raises(ConfigurationError, match="mismatch"):
        load_defaults(tmp_path)
    config.write_text(original + "\nunknown_algorithm = true\n")
    with pytest.raises(ConfigurationError, match="unknown config"):
        load_defaults(tmp_path)


def test_controller_discovers_lightweight_tracking_exports_without_native_imports():
    import subprocess
    import sys

    check = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from cephvr.controller.startup.providers import _installed_validators, _installed_file_policies
from cephvr.tracking.recording_schema import get_writer_schemas
from pathlib import Path
assert 'tracking' in _installed_validators(Path.cwd())
assert 'tracking' in _installed_file_policies(Path.cwd(),frozenset({'tracking'}))
assert ('tracking','tracking','jsonl') in get_writer_schemas()
assert not {'numpy','cv2','onnxruntime','pypylon'} & sys.modules.keys()
""",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr


@pytest.mark.parametrize(
    "change", ["absent", "partial", "zero", "inconsistent", "source"]
)
def test_tracking_requires_matching_camera_distance_calibration(change):
    settings = manual_settings()
    if change == "absent":
        settings.ClearField("image_scale")
    elif change == "partial":
        settings.image_scale.ClearField("distance_end")
    elif change == "zero":
        settings.image_scale.distance_mm = 0
    elif change == "inconsistent":
        settings.image_scale.pixels_per_mm = 5
    else:
        settings.image_scale.image_width_px = 101
    configuration = candidate(settings)
    assert not validate_configuration(configuration).valid
    configuration.backends[0].enabled = False
    assert validate_configuration(configuration).valid


@pytest.mark.parametrize("unit", ["px/s", "mm/s"])
def test_tracking_checks_stimulus_units_without_reinterpreting_old_gains(unit):
    from tests.visual_stimulus.support import fixture_source

    configuration = candidate(manual_settings())
    visual = configuration.backends.add(backend_name="visual_stimulus", enabled=True)
    program = json.loads(fixture_source())
    program["input_channels"] = [
        dict(
            channel_id="forward_drive",
            stream_id="tracking",
            value_kind="interval_average_rate",
            unit=unit,
            frame_id="anatomical_body",
        )
    ]
    configuration.trials.add().stimulus.program.program_json = json.dumps(program)
    before = configuration.SerializeToString(deterministic=True)
    validation = validate_configuration(configuration)
    assert validation.valid == (unit == "mm/s")
    assert configuration.SerializeToString(deterministic=True) == before
    if not validation.valid:
        assert "gain explicitly" in validation.issues[0].failure.message
    visual.enabled = False
    assert validate_configuration(configuration).valid


def test_flow_only_diagnostic_allows_no_scale_but_locomotion_requires_it():
    settings = manual_settings()
    settings.input_camera_role = camera_pb2.CAMERA_ROLE_TRACKING
    settings.ClearField("image_scale")
    resolve_diagnostic(
        settings,
        (tracking_wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,),
        _diagnostic_layout(),
        max_bytes=1_000_000,
    )
    with pytest.raises(ValueError, match="image_scale"):
        resolve_diagnostic(
            settings, tuple(range(1, 6)), _diagnostic_layout(), max_bytes=1_000_000
        )
