"""Manual device access and retained status delivery."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_session_access import (
    manual_configuration_available,
)
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    PulseRecord,
    SessionRecord,
    SessionSlot,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.v1 import runtime_pb2
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger


def _id() -> str:
    return str(uuid4())


class _Controller:
    def __init__(self) -> None:
        self.reports: list[wire.AcquisitionDeviceStatusReport] = []

    async def report_acquisition_device_status(
        self,
        request: wire.AcquisitionDeviceStatusReport,
        *,
        deadline_ns: int,
    ) -> control.ReportReceipt:
        _ = deadline_ns
        retained = wire.AcquisitionDeviceStatusReport.FromString(
            request.SerializeToString(deterministic=True)
        )
        self.reports.append(retained)
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)


def test_device_status_retry_replays_original_report_and_is_queryable() -> None:
    controller = _Controller()
    command_id = _id()
    generation = _id()
    ledger = CommandLedger(
        generation,
        10_000,
        max_records=8,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    ledger.admit(
        command_id,
        b"ApplyCameraSettings\0request",
        1,
        work_key=command_id,
        deadline_ns=10_000,
    )
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=generation
        ),
        process=control.ProcessIdentity(role="acquisition", generation=generation),
        controller=control.ProcessIdentity(role="controller", generation=_id()),
        supervisor=control.ProcessIdentity(role="supervisor", generation=_id()),
        tracking=control.ProcessIdentity(role="tracking", generation=_id()),
    )
    clock = [10]
    reporter = ManualDeviceStatusReporter(
        identity=identity,
        controller=controller,  # type: ignore[arg-type]
        commands=ledger,
        pulse=PulseRecord(
            observation=mcu.MicrocontrollerObservation(
                state=mcu.MicrocontrollerState(
                    behavioral=mcu.PulseOutputState(enabled=True, running=True)
                )
            )
        ),
        clock=lambda: clock[0],
    )
    command = wire.BackendCommand(
        command_id=command_id,
        work=control.WorkContext(),
    )
    reporter.reserve(command)

    async def report_twice() -> None:
        first = await reporter.report(
            command,
            command_name="apply_camera_settings",
            succeeded=True,
            deadline_ns=1000,
        )
        clock[0] = 20
        second = await reporter.report(
            command,
            command_name="apply_camera_settings",
            succeeded=True,
            deadline_ns=1000,
        )
        assert first.result == control.COMMAND_RESULT_ACCEPTED
        assert second.result == control.COMMAND_RESULT_ACCEPTED

    asyncio.run(report_twice())
    assert len(controller.reports) == 2
    assert controller.reports[0] == controller.reports[1]
    assert controller.reports[0].views.state_revision == 1
    assert controller.reports[0].views.observed_monotonic_ns == 10
    for role in ("behavioral", "tracking"):
        view = getattr(controller.reports[0].views, role)
        for field in (
            "device_open",
            "preview_running",
            "preview_prepared",
            "cleanup_pending",
        ):
            assert view.HasField(field)
            assert not getattr(view, field)
    prior = reporter.begin_device_access(camera.CAMERA_ROLE_BEHAVIORAL, "serial")
    assert prior.device.configured_id == "serial"
    assert reporter._views[camera.CAMERA_ROLE_BEHAVIORAL].cleanup_pending
    assert not reporter._views[camera.CAMERA_ROLE_TRACKING].cleanup_pending
    reporter.complete_connection_test(camera.CAMERA_ROLE_BEHAVIORAL, prior)
    assert not reporter._views[camera.CAMERA_ROLE_BEHAVIORAL].cleanup_pending
    assert controller.reports[0].views.pulses.state.behavioral.enabled
    assert controller.reports[0].views.pulses.state.behavioral.running
    retained = reporter.get_report(command_id)
    assert retained == controller.reports[0]

    from cephvr.controller.device.release_evidence import stop_preview_confirmed

    resolved = camera.CameraResolvedState()
    resolved.device.configured_id = "serial"
    resolved.applied.settings.SetInParent()
    reporter.resolve_camera(camera.CAMERA_ROLE_BEHAVIORAL, resolved, device_open=False)
    view = reporter._views[camera.CAMERA_ROLE_BEHAVIORAL]
    assert stop_preview_confirmed(view, "finished-run")
    reporter.update_camera_state(camera.CAMERA_ROLE_BEHAVIORAL, device_open=False)
    assert stop_preview_confirmed(view, "finished-run")


def _session() -> SessionRecord:
    return SessionRecord(
        work=control.WorkContext(
            session=control.SessionContext(
                session_id="00000000-0000-4000-8000-000000000001"
            )
        ),
        operation=control.OperationContext(
            command_id="00000000-0000-4000-8000-000000000002"
        ),
        configuration_revision=4,
        required_cameras=set(),
    )


def test_manual_configuration_requires_local_cleanup_proof_not_delivery_receipt() -> (
    None
):
    slot = SessionSlot()
    assert manual_configuration_available(slot)

    session = _session()
    slot.current = session
    assert not manual_configuration_available(slot)

    session.cleanup_complete = True
    assert manual_configuration_available(slot)
    assert slot.current is session


def test_connection_check_retains_unknown_cleanup_until_worker_confirms() -> None:
    from cephvr.acquisition.v1 import camera_pb2 as camera

    reporter = ManualDeviceStatusReporter(
        identity=CoordinatorIdentity(
            backend=control.BackendContext(),
            process=control.ProcessIdentity(),
            controller=control.ProcessIdentity(),
            supervisor=control.ProcessIdentity(),
            tracking=control.ProcessIdentity(),
        ),
        controller=_Controller(),
        commands=CommandLedger(
            _id(),
            10_000,
            max_records=8,
            max_bytes=1_000_000,
            result_reservation_bytes=4096,
        ),
        pulse=PulseRecord(),
        clock=lambda: 10,
    )
    role = camera.CAMERA_ROLE_BEHAVIORAL
    prior = reporter.begin_device_access(role, "CAM-1")
    assert not prior.device_open
    assert reporter._views[role].cleanup_pending
    # A failed worker operation leaves this flag in the reported device view.
    reporter.complete_connection_test(role, prior)
    assert not reporter._views[role].cleanup_pending
    assert not reporter._views[role].device_open


def test_manual_command_installs_current_draft_but_rejects_stale_or_owned_changes() -> (
    None
):
    from types import SimpleNamespace

    from cephvr.acquisition.coordinator.manual_configuration import ManualConfiguration

    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=_id()
        ),
        process=control.ProcessIdentity(),
        controller=control.ProcessIdentity(role="controller", generation=_id()),
        supervisor=control.ProcessIdentity(),
        tracking=control.ProcessIdentity(),
    )
    configuration = ConfigurationRecord(
        control.AcquisitionSettings(), runtime_pb2.AcquisitionFilePolicies(), revision=1
    )
    configuration.settings.pulses.port = "COM8"
    owned = [False]
    owner = ManualConfiguration(
        configuration,
        identity,
        SessionSlot(),
        SimpleNamespace(owns_hardware=lambda: owned[0]),
        lambda: 10,
    )
    request = wire.AcquisitionMicrocontrollerCommand(
        configuration_revision=2, kind=wire.MICROCONTROLLER_COMMAND_KIND_CONNECT
    )
    request.command.command_id = _id()
    request.command.parent_operation.command_id = _id()
    request.command.issuer.CopyFrom(identity.controller)
    request.command.target.CopyFrom(identity.backend)
    request.settings.pulses.port = "COM9"
    request.requested.CopyFrom(request.settings.pulses)
    assert owner.install(request, 100) is None
    assert configuration.revision == 2 and configuration.settings.pulses.port == "COM9"
    request.configuration_revision = 1
    request.settings.pulses.port = "COM7"
    assert owner.install(request, 100).result == control.COMMAND_RESULT_REJECTED
    request.configuration_revision = 3
    owned[0] = True
    assert owner.install(request, 100).result == control.COMMAND_RESULT_REJECTED
    assert configuration.settings.pulses.port == "COM9"
    request.settings.CopyFrom(configuration.settings)
    assert owner.install(request, 100) is None  # unrelated controller revision
    assert configuration.revision == 3
