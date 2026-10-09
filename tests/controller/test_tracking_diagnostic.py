from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.tracking_diagnostic import TrackingDiagnosticController
from cephvr.controller.device.tracking_diagnostic_state import (
    copy_status,
    matches_status,
)
from cephvr.tracking.v1 import services_pb2 as tracking


def transfer() -> svc.PreviewAttachmentResult:
    allocation, transfer_id = str(uuid4()), str(uuid4())
    return svc.PreviewAttachmentResult(
        available=True,
        attachment=acq.FrameBufferAttachment(
            buffer=acq.FrameBufferDescriptor(allocation_id=allocation),
            sync=acq.RingSyncNames(transfer_id=transfer_id),
        ),
    )


def status(
    attachment: svc.PreviewAttachmentResult,
    *,
    active: bool,
    closed: bool,
) -> tracking.TrackingDiagnosticState:
    return tracking.TrackingDiagnosticState(
        diagnostic_id="diagnostic",
        configuration_revision=7,
        preview_run_id="run",
        acquisition_run_id="run",
        active=active,
        close_confirmed=closed,
        tracking_frames=acq.AttachedResource(
            resource_id=attachment.attachment.buffer.allocation_id,
            transfer_id=attachment.attachment.sync.transfer_id,
        ),
    )


def test_status_match_requires_exact_diagnostic_and_transfer_identity() -> None:
    attachment = transfer()
    expected = pb.TrackingDiagnosticState(
        diagnostic_id="diagnostic", configuration_revision=7, preview_run_id="run"
    )
    exact = status(attachment, active=False, closed=True)
    assert matches_status(exact, expected, attachment)
    exact.tracking_frames.transfer_id = str(uuid4())
    assert not matches_status(exact, expected, attachment)


def test_backend_close_flag_does_not_mark_controller_transfer_closed() -> None:
    destination = pb.TrackingDiagnosticState(closed=False)
    copy_status(destination, status(transfer(), active=False, closed=True))
    assert destination.active is False
    assert destination.closed is False


@pytest.mark.asyncio
async def test_begin_and_close_reconcile_until_exact_backend_state_arrives() -> None:
    attachment = transfer()
    responses = [
        status(attachment, active=False, closed=False),
        status(attachment, active=True, closed=False),
    ]

    class Backend:
        async def get_tracking_diagnostic_state(self, _query, *, deadline_ns):
            return responses.pop(0)

    owner = TrackingDiagnosticController.__new__(TrackingDiagnosticController)
    owner.generation = str(uuid4())
    owner.clock = lambda: 100
    result = await owner._wait_for_status(
        Backend(),
        pb.TrackingDiagnosticState(
            diagnostic_id="diagnostic", configuration_revision=7, preview_run_id="run"
        ),
        attachment,
        pb.ProcessIdentity(role="gui", generation=str(uuid4())),
        1_000_000_000,
        active=True,
    )
    assert result is not None and result.active
    assert not responses


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_field", ["configuration_edit", "camera_operation"])
async def test_begin_rejects_while_camera_configuration_is_owned(
    owner_field: str,
) -> None:
    controller = TrackingDiagnosticController.__new__(TrackingDiagnosticController)
    controller._authorize = lambda _command: ""
    controller.lifecycle = SimpleNamespace(
        lock=asyncio.Lock(),
        attempt=None,
        session=pb.SessionState(phase=pb.SESSION_PHASE_CONFIGURATION),
    )
    controller.configuration = SimpleNamespace(revision=7)
    controller.device = SimpleNamespace(configuration_edit=None, camera_operation=None)
    setattr(controller.device, owner_field, object())
    command = svc.OperatorCommand()
    command.operator.command_id = str(uuid4())

    admission = await controller.begin(
        svc.BeginTrackingDiagnosticRequest(
            command=command, expected_configuration_revision=7
        )
    )

    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert "camera configuration or camera operation" in admission.failure.message


@pytest.mark.asyncio
async def test_release_requires_both_exact_owner_receipts() -> None:
    controller = TrackingDiagnosticController.__new__(TrackingDiagnosticController)
    controller.generation = str(uuid4())
    controller.clock = lambda: 100
    controller.lifecycle = SimpleNamespace(lock=asyncio.Lock())
    controller.projections = SimpleNamespace(preview_result=lambda _report: None)

    class Recipient:
        def __init__(self, accepted: bool) -> None:
            self.accepted = accepted
            self.reports: list[svc.PreviewConsumerReport] = []

        async def report_preview_consumer_state(self, report):
            self.reports.append(report)
            await asyncio.sleep(0)
            return pb.ReportReceipt(
                result=(
                    pb.COMMAND_RESULT_ACCEPTED
                    if self.accepted
                    else pb.COMMAND_RESULT_REJECTED
                )
            )

    acquisition, supervisor = Recipient(True), Recipient(False)
    controller.backends = {"acquisition": acquisition}
    controller.supervisor_peer = supervisor
    attachment = transfer().attachment
    with pytest.raises(RuntimeError, match="rejected"):
        await controller._report_release(
            pb.ProcessIdentity(role="tracking", generation=str(uuid4())),
            "run",
            attachment,
            deadline=1_000_000_000,
        )
    assert acquisition.reports[0].result == svc.PREVIEW_CONSUMER_RESULT_RELEASED
    assert supervisor.reports[0].result == svc.PREVIEW_CONSUMER_RESULT_RELEASED

    controller.supervisor_peer = Recipient(True)
    await controller._report_release(
        pb.ProcessIdentity(role="tracking", generation=str(uuid4())),
        "run",
        attachment,
        deadline=1_000_000_000,
    )


@pytest.mark.asyncio
async def test_close_retains_controller_ownership_when_release_receipt_is_rejected():
    attachment = transfer()
    expected = pb.TrackingDiagnosticState(
        diagnostic_id="diagnostic", configuration_revision=7, preview_run_id="run"
    )
    closed_status = status(attachment, active=False, closed=True)

    class Backend:
        context = pb.BackendContext(
            backend_name="tracking", backend_generation=str(uuid4())
        )

        async def close_tracking_diagnostic(self, _request, *, deadline_ns):
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

        async def get_tracking_diagnostic_state(self, _request, *, deadline_ns):
            return closed_status

    class Recipient:
        def __init__(self, accepted: bool):
            self.accepted = accepted

        async def report_preview_consumer_state(self, _report):
            return pb.ReportReceipt(
                result=(
                    pb.COMMAND_RESULT_ACCEPTED
                    if self.accepted
                    else pb.COMMAND_RESULT_REJECTED
                )
            )

    owner = TrackingDiagnosticController.__new__(TrackingDiagnosticController)
    owner.generation = str(uuid4())
    owner.clock = lambda: 100
    owner.lifecycle = SimpleNamespace(lock=asyncio.Lock())
    owner.projections = SimpleNamespace(preview_result=lambda _report: None)
    owner.control = SimpleNamespace(tracking_diagnostic=expected)
    owner._attachment = attachment
    owner._publish_locked = lambda: None
    owner.backends = {"acquisition": Recipient(False)}
    owner.supervisor_peer = Recipient(True)
    backend = Backend()
    result = await owner._close_owned(
        expected,
        backend,
        attachment,
        pb.ProcessIdentity(role="gui", generation=str(uuid4())),
        str(uuid4()),
        1_000_000_000,
    )
    assert "rejected" in result
    assert not owner.control.tracking_diagnostic.closed
    assert owner._attachment is attachment

    owner.backends["acquisition"] = Recipient(True)
    result = await owner._close_owned(
        expected,
        backend,
        attachment,
        pb.ProcessIdentity(role="gui", generation=str(uuid4())),
        str(uuid4()),
        1_000_000_000,
    )
    assert result == ""
    assert owner.control.tracking_diagnostic.closed
    assert owner._attachment is None
