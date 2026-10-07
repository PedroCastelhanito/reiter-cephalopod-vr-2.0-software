"""E07/E14 controller file values and pure validator availability."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import (
    controller_validators,
    load_controller_configuration,
    validate_experiment_candidate,
)
from cephvr.shared.config import ConfigurationError

_REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("age", "size", "valid"),
    [
        (0.0, 1.0, True),
        (float("nan"), 1.0, False),
        (-1.0, 1.0, False),
        (1.0, 0.0, False),
        (1.0, float("inf"), False),
    ],
)
def test_subject_metadata_numeric_bounds(age: float, size: float, valid: bool) -> None:
    candidate = pb.ExperimentConfiguration()
    candidate.subject_metadata.age_dph = age
    candidate.subject_metadata.size_mm = size

    result = validate_experiment_candidate(candidate)

    assert result.valid is valid
    assert candidate.subject_metadata.HasField("age_dph")
    assert candidate.subject_metadata.HasField("size_mm")


def _copy_pairs(root: Path) -> None:
    for relative in (
        "config/backends/experiment_config.toml",
        "contracts/policy/experiment_policy.toml",
        "config/backends/supervisor_config.toml",
        "contracts/policy/supervisor_policy.toml",
        "config/backends/acquisition_config.toml",
        "contracts/policy/acquisition_policy.toml",
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_REPOSITORY / relative, destination)


def test_loader_binds_exact_file_timing_and_budget(tmp_path: Path) -> None:
    _copy_pairs(tmp_path)
    loaded = load_controller_configuration(tmp_path)
    assert loaded.controller_port == 50051
    assert loaded.supervisor_startup.port == 50052
    assert loaded.policies.start_lead_ns == 500_000_000
    assert loaded.policies.backend_release_offset_ns == 50_000_000
    assert loaded.limits_kwargs["setup_ns"] == 60_000_000_000
    assert loaded.max_pending_payload_bytes >= 4 * loaded.max_message_bytes
    assert loaded.default_intertrial_gap_ns == 0
    assert not loaded.configuration.HasField("mode")


def test_loader_preserves_explicit_saved_false(tmp_path: Path) -> None:
    _copy_pairs(tmp_path)
    history = tmp_path / "config/last_configuration.json"
    history.write_text(
        json.dumps(
            {
                "format_version": 1,
                "configuration": {
                    "backends": [
                        {
                            "backendName": "visual_stimulus",
                            "enabled": True,
                            "visual_stimulus": {"saveVisualStimulusData": False},
                        }
                    ]
                },
            }
        )
    )
    loaded = load_controller_configuration(tmp_path)
    assert loaded.configuration.backends[0].visual_stimulus.HasField(
        "save_visual_stimulus_data"
    )
    assert (
        loaded.configuration.backends[0].visual_stimulus.save_visual_stimulus_data
        is False
    )


def test_loader_preserves_explicit_acquisition_false_and_empty_arguments(
    tmp_path: Path,
) -> None:
    _copy_pairs(tmp_path)
    history = tmp_path / "config/last_configuration.json"
    history.write_text(
        json.dumps(
            {
                "format_version": 1,
                "configuration": {
                    "backends": [
                        {
                            "backendName": "acquisition",
                            "enabled": False,
                            "acquisition": {
                                "behavioral": {
                                    "enabled": False,
                                    "saveVideo": False,
                                    "ffmpegArgs": {"values": []},
                                }
                            },
                        }
                    ]
                },
            }
        )
    )
    loaded = load_controller_configuration(tmp_path)
    acquisition = next(
        item.acquisition
        for item in loaded.configuration.backends
        if item.backend_name == "acquisition"
    )
    assert acquisition.behavioral.HasField("enabled")
    assert acquisition.behavioral.enabled is False
    assert acquisition.behavioral.HasField("save_video")
    assert acquisition.behavioral.save_video is False
    assert acquisition.behavioral.HasField("ffmpeg_args")
    assert not acquisition.behavioral.ffmpeg_args.values
    assert acquisition.tracking.ffmpeg_args.values


def test_loader_rejects_removed_key_and_policy_mismatch(tmp_path: Path) -> None:
    _copy_pairs(tmp_path)
    config = tmp_path / "config/backends/experiment_config.toml"
    config.write_text(config.read_text() + "\n[obsolete]\nreconnect_grace_s = 1\n")
    with pytest.raises(ConfigurationError, match="obsolete.reconnect_grace_s"):
        load_controller_configuration(tmp_path)
    _copy_pairs(tmp_path)
    policy = tmp_path / "contracts/policy/experiment_policy.toml"
    policy.write_text(
        policy.read_text().replace("policy_version = 8", "policy_version = 9", 1)
    )
    with pytest.raises(ConfigurationError, match="policy_version mismatch"):
        load_controller_configuration(tmp_path)


def test_enabled_backend_without_pure_validator_is_unavailable() -> None:
    candidate = pb.ExperimentConfiguration(
        backends=[pb.BackendSettings(backend_name="visual_stimulus", enabled=True)]
    )
    results = {
        name: validator(candidate)
        for name, validator in controller_validators().items()
    }
    assert results["experiment"].completed
    assert not results["visual_stimulus"].completed
    assert results["visual_stimulus"].unavailable_reason.code == "VALIDATOR_UNAVAILABLE"
    assert results["tracking"].completed  # Disabled work has no validator obligation.


def test_loader_rejects_fractional_nanosecond_duration(tmp_path: Path) -> None:
    _copy_pairs(tmp_path)
    config = tmp_path / "config/backends/experiment_config.toml"
    config.write_text(
        config.read_text().replace(
            "start_lead_time_ms = 500", "start_lead_time_ms = 500.0000000001"
        )
    )
    with pytest.raises(ConfigurationError, match="start_lead_time_ms"):
        load_controller_configuration(tmp_path)


@pytest.mark.parametrize(
    ("relative", "old", "new"),
    [
        (
            "contracts/policy/experiment_policy.toml",
            "automatic_adapter_fallback = false",
            "automatic_adapter_fallback = true",
        ),
        (
            "contracts/policy/experiment_policy.toml",
            'continuable_failure = "operator_continue_or_abort"',
            'continuable_failure = "automatic_continue"',
        ),
        (
            "contracts/policy/supervisor_policy.toml",
            "application_job_kill_on_close = true",
            "application_job_kill_on_close = false",
        ),
    ],
)
def test_loader_rejects_unimplemented_fixed_policy(
    tmp_path: Path, relative: str, old: str, new: str
) -> None:
    _copy_pairs(tmp_path)
    policy = tmp_path / relative
    policy.write_text(policy.read_text().replace(old, new, 1))
    with pytest.raises(ConfigurationError, match="fixed policy"):
        load_controller_configuration(tmp_path)


def test_corrupt_saved_history_kept_and_reported_without_fabricating_mode(
    tmp_path: Path,
) -> None:
    _copy_pairs(tmp_path)
    history = tmp_path / "config/last_configuration.json"
    original = '{"format_version":1,"format_version":1,"configuration":{}}'
    history.write_text(original)
    loaded = load_controller_configuration(tmp_path)
    assert loaded.history_warning is not None
    assert "duplicate JSON member" in loaded.history_warning
    assert not loaded.configuration.HasField("mode")
    assert history.read_text() == original


def test_saved_history_bound_uses_configured_message_limit(tmp_path: Path) -> None:
    _copy_pairs(tmp_path)
    config = tmp_path / "config/backends/experiment_config.toml"
    config.write_text(
        config.read_text().replace(
            "max_message_bytes = 16_777_216", "max_message_bytes = 1024"
        )
    )
    (tmp_path / "config/last_configuration.json").write_bytes(b" " * 1025)
    loaded = load_controller_configuration(tmp_path)
    assert loaded.history_warning is not None
    assert "exceeds control message limit" in loaded.history_warning


def test_unknown_empty_toml_table_is_rejected(tmp_path: Path) -> None:
    _copy_pairs(tmp_path)
    config = tmp_path / "config/backends/experiment_config.toml"
    config.write_text(config.read_text() + "\n[unsupported_empty_section]\n")
    with pytest.raises(ConfigurationError, match="unsupported_empty_section"):
        load_controller_configuration(tmp_path)
