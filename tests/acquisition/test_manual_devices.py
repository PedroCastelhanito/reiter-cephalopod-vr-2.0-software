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
    CoordinatorIdentity,
    PulseRecord,
    SessionRecord,
    SessionSlot,
)
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
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
    assert controller.reports[0].views.pulses.state.behavioral.enabled
    assert controller.reports[0].views.pulses.state.behavioral.running
    retained = reporter.get_report(command_id)
    assert retained == controller.reports[0]


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
