"""E02/E03 live-watch lease loss preserves accepted controller work."""

from __future__ import annotations

from uuid import uuid4

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.leases import ControlLeases
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    ConfigurationState,
    ControllerLimits,
    ControlState,
    IncidentState,
    LifecycleState,
    LimitsState,
    MetadataState,
    SupervisorState,
    Watch,
)


def _limits() -> ControllerLimits:
    return ControllerLimits(
        setup_ns=1,
        setup_cancel_ns=1,
        ready_ns=1,
        finished_ns=1,
        registration_ns=1,
        recovery_ns=1,
        metadata_ns=1,
        validation_ns=1,
        lead_ns=3,
        controller_release_ns=2,
        backend_release_ns=1,
        start_evidence_ns=1,
        stop_evidence_ns=1,
        max_metadata_operations=4,
        max_metadata_bytes=1,
        history_ns=1,
        space_query_ns=1,
        low_space_bytes=1,
        max_watchers=8,
    )


def _components() -> tuple[
    str,
    LifecycleState,
    ControlState,
    SnapshotPublisher,
    ControlOperations,
    ControlLeases,
]:
    generation = str(uuid4())
    lifecycle = LifecycleState()
    control = ControlState()
    configuration = ConfigurationState(
        pb.ExperimentConfiguration(), pb.ControlPolicies()
    )
    limits = LimitsState(_limits())
    publisher = SnapshotPublisher(
        generation=generation,
        clock=lambda: 1,
        configuration=configuration,
        lifecycle=lifecycle,
        control=control,
        metadata=MetadataState(max_operations=4),
        supervisor=SupervisorState(last_seen_ns=1),
        incidents=IncidentState(),
        projections=ProjectionStore(
            generation, {}, max_entries=8, max_payload_bytes=4096
        ),
        limits=limits,
    )
    operations = ControlOperations(
        lifecycle=lifecycle,
        configuration=configuration,
        control=control,
        generation=generation,
        max_operation_records=16,
        clock=lambda: 1,
    )
    leases = ControlLeases(
        lifecycle=lifecycle,
        control=control,
        operations=operations,
        publisher=publisher,
        generation=generation,
    )
    return generation, lifecycle, control, publisher, operations, leases


async def _installed_watch(publisher: SnapshotPublisher, client_id: str) -> Watch:
    watch = await publisher.open_watch(client_id, str(uuid4()))
    initial = await watch.queue.get()
    await publisher.delivered_watch_view(watch, initial.state_revision)
    return watch


def _claim(generation: str, watch: Watch) -> svc.ControlClaim:
    return svc.ControlClaim(
        client_id=watch.client_id,
        watch_id=watch.watch_id,
        command_id=str(uuid4()),
        controller_generation=generation,
        synchronized_state_revision=watch.installed_revision,
    )


def _command(
    generation: str, client_id: str, control_generation: str
) -> svc.OperatorCommand:
    return svc.OperatorCommand(
        controller_generation=generation,
        operator=pb.OperatorContext(
            client_id=client_id,
            control_generation=control_generation,
            command_id=str(uuid4()),
        ),
    )


@pytest.mark.parametrize(
    "phase", [pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_RUNNING]
)
async def test_watch_loss_releases_control_and_keeps_accepted_work(
    phase: pb.SessionPhase,
) -> None:
    generation, lifecycle, control, publisher, operations, leases = _components()
    lifecycle.session.phase = phase
    watch = await _installed_watch(publisher, str(uuid4()))
    claim = await leases.claim(_claim(generation, watch))
    assert claim.result == pb.COMMAND_RESULT_ACCEPTED
    assert control.owner is not None
    stale = _command(generation, watch.client_id, control.owner[2])
    assert operations.authorized(stale) == ""
    accepted = operations.operation(str(uuid4()), "AcceptedWork")
    revision = control.revision

    await publisher.close_watch(watch)

    assert control.owner is None
    assert lifecycle.manual_control_cleanup_pending is (
        phase == pb.SESSION_PHASE_CONFIGURATION
    )
    assert control.revision > revision
    assert lifecycle.session.phase == phase
    assert control.operations[accepted.context.command_id] is accepted
    assert any(
        item.context.command_id == accepted.context.command_id
        for item in publisher.build_snapshot().operations
    )
    assert (
        operations.authorized(stale)
        == "controller generation or control lease mismatch"
    )

    reopened = await _installed_watch(publisher, watch.client_id)
    assert control.owner is None  # Reconnection begins as an observer.
    assert (
        await leases.claim(_claim(generation, reopened))
    ).result == pb.COMMAND_RESULT_ACCEPTED
    assert control.owner is not None
    assert control.owner[2] != stale.operator.control_generation
    assert lifecycle.manual_control_cleanup_pending is (
        phase == pb.SESSION_PHASE_CONFIGURATION
    )
    assert accepted.context.command_id in control.operations


async def test_takeover_and_release_invalidate_old_generation() -> None:
    generation, lifecycle, control, publisher, operations, leases = _components()
    first = await _installed_watch(publisher, str(uuid4()))
    second = await _installed_watch(publisher, str(uuid4()))
    assert (
        await leases.claim(_claim(generation, first))
    ).result == pb.COMMAND_RESULT_ACCEPTED
    assert control.owner is not None
    old_command = _command(generation, first.client_id, control.owner[2])
    assert (
        await leases.claim(_claim(generation, second))
    ).result == pb.COMMAND_RESULT_REJECTED

    latest = await second.queue.get()
    await publisher.delivered_watch_view(second, latest.state_revision)
    assert (
        await leases.claim(_claim(generation, second), takeover=True)
    ).result == pb.COMMAND_RESULT_ACCEPTED
    assert not lifecycle.manual_control_cleanup_pending
    assert control.owner is not None
    current_command = _command(generation, second.client_id, control.owner[2])
    assert operations.authorized(old_command) == "control lease mismatch"
    assert operations.authorized(current_command) == ""

    retained = operations.operation(str(uuid4()), "AcceptedWork")
    assert (
        await leases.release_control(current_command)
    ).result == pb.COMMAND_RESULT_ACCEPTED
    assert control.owner is None
    assert lifecycle.manual_control_cleanup_pending
    assert retained.context.command_id in control.operations
    assert (
        operations.authorized(current_command)
        == "controller generation or control lease mismatch"
    )
