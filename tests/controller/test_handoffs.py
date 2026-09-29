"""Controller-owned descriptor and projection regressions; no devices are opened."""

from uuid import uuid4

import pytest

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acquisition
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.preparation import PreparationError, PreparationHandoff
from cephvr.controller.projections import ProjectionError, ProjectionStore
from cephvr.controller.resolution import resolved_configuration


def uid() -> str:
    return str(uuid4())


def setup():
    session = pb.SessionContext(controller_generation=uid(), session_id=uid())
    peers = {
        name: pb.BackendContext(backend_name=name, backend_generation=uid())
        for name in ("acquisition", "tracking", "vr")
    }
    commands = {name: uid() for name in peers}
    handoff = PreparationHandoff(
        session,
        3,
        peers,
        commands,
        camera=camera.CAMERA_ROLE_TRACKING,
        closed_loop=True,
        max_payload_bytes=65536,
    )
    frames = rpc.DataPreparationReport(
        source=pb.ReportContext(
            backend=peers["acquisition"],
            work=pb.WorkContext(session=session),
            operation=pb.OperationContext(command_id=commands["acquisition"]),
        ),
        configuration_revision=3,
        report_revision=1,
    )
    attachment = frames.tracking_input
    attachment.buffer.allocation_id = uid()
    attachment.buffer.owner.CopyFrom(
        pb.ProcessIdentity(
            role="acquisition",
            generation=peers["acquisition"].backend_generation,
        )
    )
    attachment.buffer.producer.CopyFrom(
        pb.ProcessIdentity(role="camera", generation=uid())
    )
    consumer = pb.ProcessIdentity(
        role="tracking", generation=peers["tracking"].backend_generation
    )
    attachment.buffer.consumer.CopyFrom(consumer)
    attachment.buffer.camera = camera.CAMERA_ROLE_TRACKING
    attachment.buffer.kind = acquisition.FRAME_BUFFER_KIND_TRACKING
    attachment.buffer.session.CopyFrom(session)
    attachment.buffer.configuration_revision = 3
    attachment.buffer.shared_memory_name = "private mapping"
    attachment.buffer.layout_version = 1
    attachment.buffer.capacity_frames = 4
    attachment.buffer.allocation_bytes = 4096
    attachment.buffer.image.SetInParent()
    attachment.sync.transfer_id = uid()
    attachment.sync.target.CopyFrom(consumer)
    attachment.sync.event_name = "private event"
    report = rpc.DataPreparationReport(
        source=pb.ReportContext(
            backend=peers["tracking"],
            work=pb.WorkContext(session=session),
            operation=pb.OperationContext(command_id=commands["tracking"]),
        ),
        configuration_revision=3,
        report_revision=1,
    )
    report.tracking.preparation_generation = uid()
    report.tracking.configuration_revision = 3
    return handoff, frames, report


def test_handoff_is_acyclic_and_requires_exact_attachment_proof() -> None:
    handoff, frames, report = setup()
    handoff.accept(report)
    assert not handoff.can_bind_input
    handoff.accept(frames)
    assert handoff.can_bind_input
    assert not handoff.can_confirm_input
    assert not handoff.can_prepare_vr
    report.report_revision = 2
    report.tracking.data_attached = True
    report.tracking.attached_input.resource_id = (
        frames.tracking_input.buffer.allocation_id
    )
    report.tracking.attached_input.transfer_id = uid()
    with pytest.raises(PreparationError, match="another input"):
        handoff.accept(report)
    report.tracking.attached_input.transfer_id = frames.tracking_input.sync.transfer_id
    handoff.accept(report)
    assert handoff.can_confirm_input
    assert not handoff.can_prepare_vr


def test_changed_retry_replacement_and_retirement_cannot_restore_setup() -> None:
    handoff, frames, report = setup()
    handoff.accept(frames)
    handoff.accept(report)
    assert not handoff.accept(report)
    report.tracking.preparation_generation = uid()
    with pytest.raises(PreparationError, match="changed payload"):
        handoff.accept(report)
    report.report_revision += 1
    with pytest.raises(PreparationError, match="generation changed"):
        handoff.accept(report)
    handoff.retire()
    with pytest.raises(PreparationError, match="retired"):
        handoff.accept(frames)
    assert not handoff.can_bind_input
    assert handoff.frames is not None  # Cleanup obligation is retained.


def store() -> ProjectionStore:
    return ProjectionStore(
        uid(),
        {
            "acquisition": pb.BackendContext(
                backend_name="acquisition", backend_generation=uid()
            )
        },
        max_entries=8,
        max_payload_bytes=65536,
    )


def test_warning_retries_preserve_absolute_counts_and_complete_scope() -> None:
    view = store()
    view.set_scope(pb.WorkContext(), 3)
    producer = pb.ProcessIdentity(role="camera", generation=uid())
    report = rpc.AcquisitionWarningReport(source=view.peers["acquisition"])
    report.view.CopyFrom(
        pb.AcquisitionWarningView(
            producer=producer,
            camera=camera.CAMERA_ROLE_BEHAVIORAL,
            configuration_revision=3,
            warning_revision=1,
        )
    )
    warning = report.view.warnings.add(
        warning_id=uid(), component="acquisition", message="frame was invalid"
    )
    warning.acquisition_occurrence.CopyFrom(
        pb.AcquisitionWarningOccurrence(
            source=producer,
            camera=camera.CAMERA_ROLE_BEHAVIORAL,
            configuration_revision=3,
            code="INVALID_IMAGE",
            count=2,
            first_observed_monotonic_ns=10,
            last_observed_monotonic_ns=20,
        )
    )
    assert view.accept_warnings(report)
    assert not view.accept_warnings(report)
    snapshot = pb.Snapshot()
    view.install_public(snapshot)
    assert snapshot.warnings[0].acquisition_occurrence.count == 2
    report.view.warning_revision = 2
    report.view.warnings[0].acquisition_occurrence.count = 1
    with pytest.raises(ProjectionError, match="regressed"):
        view.accept_warnings(report)
    report.view.ClearField("warnings")
    with pytest.raises(ProjectionError, match="disappeared"):
        view.accept_warnings(report)
    view.set_scope(pb.WorkContext(), 4)
    assert not view.warnings


def test_preview_transfer_is_private_and_retired_attachment_only_releases() -> None:
    view = store()
    operation, run = uid(), uid()
    consumer = pb.ProcessIdentity(role="gui", generation=uid())
    view.expect_preview(operation, consumer, run, camera.CAMERA_ROLE_BEHAVIORAL)
    report = rpc.PreviewAttachmentReport(
        source=view.peers["acquisition"],
        operation=pb.OperationContext(command_id=operation),
    )
    attachment = report.attachment
    attachment.buffer.allocation_id = uid()
    attachment.buffer.owner.CopyFrom(
        pb.ProcessIdentity(
            role="acquisition", generation=report.source.backend_generation
        )
    )
    attachment.buffer.kind = acquisition.FRAME_BUFFER_KIND_PREVIEW
    attachment.buffer.camera = camera.CAMERA_ROLE_BEHAVIORAL
    attachment.buffer.shared_memory_name = "secret mapping"
    attachment.buffer.preview.controller.CopyFrom(
        pb.ProcessIdentity(role="controller", generation=view.generation)
    )
    attachment.buffer.preview.acquisition_run_id = run
    attachment.sync.transfer_id = uid()
    attachment.sync.target.CopyFrom(consumer)
    attachment.sync.event_name = "secret event"
    view.retire_preview(run)
    assert view.accept_preview(report)
    query = rpc.PreviewAttachmentQuery(
        client_id=consumer.generation,
        consumer=consumer,
        controller_generation=view.generation,
        preview_run_id=run,
    )
    result = view.preview(query)
    assert result.available and result.release_only
    public = pb.Snapshot()
    view.install_public(public)
    assert b"secret" not in public.SerializeToString()
    query.consumer.generation = uid()
    with pytest.raises(ProjectionError, match="identity differs"):
        view.preview(query)
    released = rpc.PreviewConsumerReport(
        client_id=consumer.generation,
        consumer=consumer,
        controller_generation=view.generation,
        preview_run_id=run,
        allocation_id=attachment.buffer.allocation_id,
        transfer_id=attachment.sync.transfer_id,
        result=rpc.PREVIEW_CONSUMER_RESULT_ATTACHED,
    )
    with pytest.raises(ProjectionError, match="retired"):
        view.preview_result(released)
    released.result = rpc.PREVIEW_CONSUMER_RESULT_RELEASED
    assert view.preview_result(released)
    assert not view.preview_result(released)


def test_camera_readback_is_atomic_and_preserves_requested_pulse_frequency() -> None:
    configuration = pb.ExperimentConfiguration()
    backend = configuration.backends.add(backend_name="acquisition", enabled=True)
    backend.acquisition.behavioral.enabled = True
    backend.acquisition.behavioral.device.device_id = "camera-serial"
    backend.acquisition.pulses.behavioral.requested_frequency_hz = 60.1
    source = pb.BackendContext(backend_name="acquisition", backend_generation=uid())
    operation = uid()
    report = rpc.AcquisitionResolutionReport(
        source=source,
        requested_configuration_revision=7,
        operation=pb.OperationContext(command_id=operation),
    )
    readback = report.cameras.add(camera=camera.CAMERA_ROLE_BEHAVIORAL).result
    readback.configuration_revision = 7
    readback.device.configured_id = "camera-serial"
    readback.device.physical_id = "physical-serial"
    readback.applied.device_id = "camera-serial"
    readback.capabilities.SetInParent()
    readback.transport.SetInParent()
    readback.layout.SetInParent()
    report.pulses.requested_configuration_revision = 7
    report.pulses.requested.CopyFrom(backend.acquisition.pulses)
    report.pulses.behavioral_active = True
    report.pulses.tracking_active = False
    report.pulses.applied.SetInParent()
    expected = dict(
        source=source,
        work=pb.WorkContext(),
        operation_id=operation,
        revision=7,
        expected_cameras=frozenset({camera.CAMERA_ROLE_BEHAVIORAL}),
        expect_pulses=True,
    )
    result = resolved_configuration(configuration, report, **expected)
    assert (
        result.backends[0].acquisition.pulses.behavioral.requested_frequency_hz == 60.1
    )
    before = configuration.SerializeToString()
    report.requested_configuration_revision = 8
    with pytest.raises(ProjectionError, match="outstanding batch"):
        resolved_configuration(configuration, report, **expected)
    assert configuration.SerializeToString() == before
