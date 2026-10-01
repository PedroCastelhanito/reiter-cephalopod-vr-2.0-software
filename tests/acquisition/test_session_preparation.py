"""Session preparation validation and manual-owner handoff."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest

from cephvr.acquisition.coordinator.session_preparation import SessionPreparation
from cephvr.acquisition.coordinator.session_validation import validate_setup_request
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    PulseRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control


class _SerialOwner:
    def __init__(self) -> None:
        self.closed = False

    async def close(self, *, deadline_ns: int) -> None:
        assert deadline_ns == 500
        self.closed = True


def test_session_handoff_closes_manual_serial_owner_without_camera_workers() -> None:
    owner = _SerialOwner()
    pulse = PulseRecord(observation=mcu.MicrocontrollerObservation(port="COM7"))
    preparation = cast(
        SessionPreparation,
        SimpleNamespace(
            workers=SimpleNamespace(workers={}),
            pulse=pulse,
            serial=owner,
            clock=lambda: 100,
        ),
    )

    asyncio.run(SessionPreparation.retire_manual_workers(preparation, deadline_ns=500))

    assert owner.closed
    assert pulse.observation is None


def _setup_request(
    *, tracking_backend: bool = False
) -> tuple[wire.SetupSessionRequest, ConfigurationRecord, CoordinatorIdentity]:
    controller = control.ProcessIdentity(role="controller", generation="controller-1")
    supervisor = control.ProcessIdentity(role="supervisor", generation="supervisor-1")
    tracking = control.ProcessIdentity(role="tracking", generation="tracking-1")
    backend = control.BackendContext(
        backend_name="acquisition", backend_generation="acquisition-1"
    )
    session = control.SessionContext(session_id="session-1")
    policies = runtime.AcquisitionFilePolicies(contract_version=11)
    settings = control.AcquisitionSettings()
    settings.behavioral.enabled = True
    request = wire.SetupSessionRequest(
        command=wire.BackendCommand(
            command_id="setup-1",
            issuer=controller,
            target=backend,
            work=control.WorkContext(session=session),
        ),
        settings=control.BackendSettings(
            backend_name="acquisition", enabled=True, acquisition=settings
        ),
        acquisition_policies=policies,
        plan=control.PreparedSession(
            context=session,
            configuration_revision=0,
        ),
    )
    if tracking_backend:
        request.plan.configuration.backends.add(backend_name="tracking", enabled=True)
    configuration = ConfigurationRecord(
        settings=control.AcquisitionSettings(), file_policies=policies
    )
    identity = CoordinatorIdentity(
        backend=backend,
        process=control.ProcessIdentity(role="acquisition", generation="acquisition-1"),
        controller=controller,
        supervisor=supervisor,
        tracking=tracking,
    )
    return request, configuration, identity


def test_setup_accepts_zero_revision_when_tracking_is_inactive() -> None:
    request, configuration, identity = _setup_request()
    result = validate_setup_request(
        request,
        100,
        identity=identity,
        configuration=configuration,
        clock=lambda: 1,
    )
    assert result.configuration_revision == 0
    assert not result.tracking_required


def test_setup_requires_tracking_camera_only_for_enabled_tracking_backend() -> None:
    request, configuration, identity = _setup_request(tracking_backend=True)
    with pytest.raises(ValueError, match="requires the tracking camera"):
        validate_setup_request(
            request,
            100,
            identity=identity,
            configuration=configuration,
            clock=lambda: 1,
        )


def test_tracking_camera_alone_does_not_imply_a_tracking_consumer() -> None:
    request, configuration, identity = _setup_request()
    request.settings.acquisition.tracking.enabled = True
    result = validate_setup_request(
        request,
        100,
        identity=identity,
        configuration=configuration,
        clock=lambda: 1,
    )
    assert camera.CAMERA_ROLE_TRACKING in result.required_cameras
    assert not result.tracking_required


def test_setup_retains_exact_acquisition_output_reservations() -> None:
    request, configuration, identity = _setup_request()
    request.settings.acquisition.behavioral.save_video = True
    trial = request.plan.trials.add(
        context=control.TrialContext(
            session=request.plan.context,
            trial_id="trial-1",
            trial_number=1,
        )
    )
    del trial
    for tag, extension in (
        ("behavioral_cam", "mp4"),
        ("behavioral_cam_frames", "jsonl"),
    ):
        request.plan.outputs.add(
            backend=identity.backend,
            output_key=f"trial-1:acquisition:{tag}",
            trial=request.plan.trials[0].context,
            output_tag=tag,
            extension=extension,
        )

    result = validate_setup_request(
        request,
        100,
        identity=identity,
        configuration=configuration,
        clock=lambda: 1,
    )

    assert [item.output_key for item in result.reserved_outputs] == [
        "trial-1:acquisition:behavioral_cam",
        "trial-1:acquisition:behavioral_cam_frames",
    ]


def test_setup_rejects_incomplete_output_closure_before_ready() -> None:
    request, configuration, identity = _setup_request()
    request.settings.acquisition.behavioral.save_video = True
    request.plan.trials.add(
        context=control.TrialContext(
            session=request.plan.context,
            trial_id="trial-1",
            trial_number=1,
        )
    )
    request.plan.outputs.add(
        backend=identity.backend,
        output_key="trial-1:acquisition:behavioral_cam",
        trial=request.plan.trials[0].context,
        output_tag="behavioral_cam",
        extension="mp4",
    )

    with pytest.raises(ValueError, match="reservations differ"):
        validate_setup_request(
            request,
            100,
            identity=identity,
            configuration=configuration,
            clock=lambda: 1,
        )
