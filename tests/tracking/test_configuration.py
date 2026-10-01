from __future__ import annotations

import json
import shutil

import pytest

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.config import ConfigurationError
from cephvr.tracking.configuration import (
    load_defaults,
    load_file_policies,
    resolve_settings,
    validate_configuration,
)

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
    contour = json.loads(settings.stages[0].settings_json)
    assert "threshold_level" not in contour
    policy = load_file_policies(ROOT)
    assert policy.maximum_input_frame_age_ns == 250_000_000
    assert policy.result_capacity == 10
    assert policy.recording.max_pending_records == 4096


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
    config.write_text(original.replace("policy_version = 42", "policy_version = 43"))
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
assert 'tracking' in _installed_validators()
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
