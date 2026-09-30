"""Acquisition configuration loading, validation and readback adoption."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from cephvr.acquisition.config.validation import validate_configuration
from cephvr.acquisition.configuration import load_defaults, load_file_policies
from cephvr.acquisition.coordinator.configuration_resolution import (
    ConfigurationResolution,
    confirmed_matches_resolution,
)
from cephvr.acquisition.state import ConfigurationRecord, CoordinatorIdentity
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2
from cephvr.control.v1 import types_pb2 as control
from cephvr.controller.configuration import controller_validators
from cephvr.shared.config import ConfigurationError

_ROOT = Path(__file__).resolve().parents[2]


def test_defaults_preserve_unset_hardware_values() -> None:
    settings = load_defaults(_ROOT)

    assert settings.behavioral.enabled is True
    assert settings.tracking.enabled is False
    assert settings.HasField("pulses")
    assert not settings.pulses.HasField("port")
    assert settings.pulses.behavioral.HasField("requested_frequency_hz")
    assert not settings.pulses.behavioral.HasField("pin")
    assert not settings.behavioral.device.settings.HasField("trigger_source")
    assert not settings.behavioral.device.settings.HasField("exposure_us")
    assert not settings.behavioral.device.settings.HasField("roi")


def test_operator_trigger_source_is_loaded_only_when_present(tmp_path: Path) -> None:
    root = _copy_configuration(tmp_path)
    config_path = root / "config/backends/acquisition_config.toml"
    original = config_path.read_text(encoding="utf-8")
    assert not load_defaults(root).behavioral.device.settings.HasField("trigger_source")
    config_path.write_text(
        original.replace(
            'trigger_selector = "frame_start"',
            'trigger_selector = "frame_start"\ntrigger_source = "Line1"',
            1,
        ),
        encoding="utf-8",
    )
    assert load_defaults(root).behavioral.device.settings.trigger_source == "Line1"


def test_pfs_source_filename_is_provenance_only_and_is_not_opened(
    tmp_path: Path,
) -> None:
    root = _copy_configuration(tmp_path)
    config_path = root / "config/backends/acquisition_config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            'device_id = "40065509"',
            'device_id = "40065509"\npfs_source_filename = "missing preset.pfs"',
            1,
        ),
        encoding="utf-8",
    )

    device = load_defaults(root).behavioral.device

    assert device.pfs_source_filename == "missing preset.pfs"
    assert not device.HasField("pfs_baseline")


def test_file_policies_resolve_exact_units_and_preserve_deferred_margin() -> None:
    policies = load_file_policies(_ROOT)

    assert policies.contract_version == 1
    assert policies.serial_baud_rate == 115200
    assert policies.serial_ack_timeout_ns == 100_000_000
    behavioral = next(
        item
        for item in policies.cameras
        if item.camera == camera_pb2.CAMERA_ROLE_BEHAVIORAL
    )
    assert behavioral.frame_silence_timeout_ns == 1_000_000_000
    assert not behavioral.HasField("post_cutoff_drain_margin_ns")


def test_validation_rejects_duplicate_active_pin_and_empty_encoder_list() -> None:
    experiment = types_pb2.ExperimentConfiguration()
    backend = experiment.backends.add(backend_name="acquisition")
    settings = backend.acquisition
    settings.behavioral.enabled = True
    settings.behavioral.save_video = True
    settings.behavioral.device.device_id = "camera-a"
    settings.behavioral.device.frame_timing = camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
    settings.behavioral.device.settings.trigger_source = "Line1"
    settings.tracking.enabled = True
    settings.tracking.device.device_id = "camera-b"
    settings.tracking.device.frame_timing = camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
    settings.tracking.device.settings.trigger_source = "Line1"
    for role in (settings.pulses.behavioral, settings.pulses.tracking):
        role.pin = "D2"
        role.requested_frequency_hz = 30.0

    result = validate_configuration(experiment)

    assert not result.valid
    codes = {issue.failure.code for issue in result.issues}
    assert "DUPLICATE_PIN" in codes
    assert "ENCODER_ARGUMENTS_REQUIRED" in codes


def test_missing_required_device_ids_do_not_report_a_duplicate() -> None:
    experiment = types_pb2.ExperimentConfiguration()
    backend = experiment.backends.add(backend_name="acquisition")
    backend.acquisition.behavioral.enabled = True

    result = validate_configuration(experiment)

    codes = {issue.failure.code for issue in result.issues}
    assert "DEVICE_REQUIRED" in codes
    assert "DUPLICATE_DEVICE" not in codes


def test_controller_accepts_acquisition_validator_identity() -> None:
    experiment = types_pb2.ExperimentConfiguration()
    experiment.backends.add(backend_name="acquisition", enabled=True)

    result = controller_validators({"acquisition": validate_configuration})[
        "acquisition"
    ](experiment)

    assert result.component == "acquisition"
    assert result.configuration_module_version == "acquisition-config-v1"
    assert result.completed


def test_loader_rejects_unknown_camera_roles_and_missing_required_limits(
    tmp_path: Path,
) -> None:
    root = _copy_configuration(tmp_path)
    config_path = root / "config/backends/acquisition_config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n[cameras.extra]\nenabled = false\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="unknown camera roles"):
        load_defaults(root)

    root = _copy_configuration(tmp_path / "missing-limit")
    config_path = root / "config/backends/acquisition_config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("baud_rate = 115200\n", "", 1),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="baud_rate"):
        load_file_policies(root)


def test_file_policy_rejects_invalid_watchdog_relationship_and_resolution(
    tmp_path: Path,
) -> None:
    root = _copy_configuration(tmp_path)
    config_path = root / "config/backends/acquisition_config.toml"
    original = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        original.replace("keepalive_interval_s = 1", "keepalive_interval_s = 3", 1),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="keepalive"):
        load_file_policies(root)

    config_path.write_text(
        original.replace(
            "communication_timeout_s = 3", "communication_timeout_s = 3.0000001", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="millisecond"):
        load_file_policies(root)


def _copy_configuration(destination: Path) -> Path:
    shutil.copytree(_ROOT / "config", destination / "config")
    shutil.copytree(_ROOT / "contracts", destination / "contracts")
    return destination


class _Controller:
    async def report_acquisition_resolution(
        self, *_: object, **__: object
    ) -> control.ReportReceipt:
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)


def test_controller_shaped_confirmation_uses_original_command_as_parent() -> None:
    async def scenario() -> None:
        controller = control.ProcessIdentity(
            role="controller", generation="controller-1"
        )
        backend = control.BackendContext(
            backend_name="acquisition", backend_generation="acq-1"
        )
        identity = CoordinatorIdentity(
            backend=backend,
            process=control.ProcessIdentity(role="acquisition", generation="acq-1"),
            controller=controller,
            supervisor=control.ProcessIdentity(
                role="supervisor", generation="supervisor-1"
            ),
            tracking=control.ProcessIdentity(role="tracking", generation="tracking-1"),
        )
        current_settings = control.AcquisitionSettings()
        record = ConfigurationRecord(
            settings=current_settings,
            file_policies=runtime.AcquisitionFilePolicies(),
            revision=5,
        )
        resolution = ConfigurationResolution(
            identity=identity,
            configuration=record,
            controller=_Controller(),  # type: ignore[arg-type]
            lock=asyncio.Lock(),
            clock=lambda: 10,
        )
        original_command = wire.BackendCommand(
            command_id="resolution-command",
            issuer=controller,
            target=backend,
            parent_operation=control.OperationContext(command_id="operator-parent"),
        )
        operation = await resolution.begin(
            original_command,
            expected_cameras={camera.CAMERA_ROLE_BEHAVIORAL},
            request_revision=5,
            deadline_ns=100,
        )
        pending = resolution._pending
        assert pending is not None
        applied = camera.CameraDeviceConfiguration(device_id="device-17")
        report = wire.AcquisitionResolutionReport(
            source=backend,
            operation=operation,
            requested_configuration_revision=5,
        )
        report.cameras.add(
            camera=camera.CAMERA_ROLE_BEHAVIORAL,
            result=camera.CameraResolvedState(applied=applied),
        )
        pending.report.CopyFrom(report)
        pending.report_sending = True
        confirmed = control.AcquisitionSettings()
        confirmed.behavioral.device.CopyFrom(applied)
        request = wire.AcquisitionConfigurationConfirmation(
            command=wire.BackendCommand(
                command_id="confirmation-command",
                issuer=controller,
                target=backend,
                parent_operation=control.OperationContext(
                    command_id=original_command.command_id
                ),
            ),
            resolution_operation=operation,
            requested_configuration_revision=5,
            confirmed_configuration_revision=6,
            confirmed=confirmed,
        )
        admitted = await resolution.confirm(request, deadline_ns=100)
        assert admitted.result == control.COMMAND_RESULT_ACCEPTED
        assert record.revision == 6

    asyncio.run(scenario())


def test_confirmation_must_match_every_reported_camera_and_pulse_readback() -> None:
    applied = camera.CameraDeviceConfiguration(
        device_id="device-17", frame_timing=camera.FRAME_TIMING_FREE_RUNNING
    )
    resolved = camera.CameraResolvedState(applied=applied)
    report = wire.AcquisitionResolutionReport()
    report.cameras.add(camera=camera.CAMERA_ROLE_BEHAVIORAL, result=resolved)
    confirmed = control.AcquisitionSettings()
    confirmed.behavioral.device.CopyFrom(applied)

    assert confirmed_matches_resolution(
        confirmed,
        report,
        None,
        {camera.CAMERA_ROLE_BEHAVIORAL},
        None,
    )

    confirmed.behavioral.device.device_id = "replacement"
    assert not confirmed_matches_resolution(
        confirmed,
        report,
        None,
        {camera.CAMERA_ROLE_BEHAVIORAL},
        None,
    )

    pulse_resolution = mcu.PulseConfigurationResolution(
        requested_configuration_revision=4
    )
    pulse_resolution.applied.connection_id = "serial-generation-1"
    assert not confirmed_matches_resolution(
        control.AcquisitionSettings(
            behavioral=camera.CameraSessionSettings(device=applied)
        ),
        report,
        pulse_resolution,
        {camera.CAMERA_ROLE_BEHAVIORAL},
        None,
    )
    assert confirmed_matches_resolution(
        control.AcquisitionSettings(
            behavioral=camera.CameraSessionSettings(device=applied)
        ),
        report,
        pulse_resolution,
        {camera.CAMERA_ROLE_BEHAVIORAL},
        pulse_resolution,
    )
